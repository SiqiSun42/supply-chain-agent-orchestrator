"""OpenAI provider built on the official `openai` SDK (Chat Completions + tools)."""

from __future__ import annotations

import json
import time
from typing import Any, Literal

import openai
from pydantic import BaseModel, ValidationError

from orchestrator.llm.base import (
    LLMError,
    LLMProvider,
    LLMResponse,
    Message,
    PromptContext,
    ToolCall,
    ToolSpec,
    Usage,
)
from orchestrator.llm.json_parse import parse_json_object
from orchestrator.llm.messages import repair_messages_for_tool_api

StructuredMode = Literal["auto", "native", "json"]


def reasoning_content_from_message(msg: Message) -> str:
    if msg.raw:
        for block in msg.raw:
            if isinstance(block, dict) and "reasoning_content" in block:
                return str(block.get("reasoning_content") or "")
    return ""


def capture_assistant_extras(choice: Any) -> list[dict[str, Any]] | None:
    reasoning = getattr(choice, "reasoning_content", None)
    model_dump = getattr(choice, "model_dump", None)
    if reasoning is None and callable(model_dump):
        reasoning = model_dump(exclude_none=False).get("reasoning_content")
    if reasoning is None:
        return None
    return [{"reasoning_content": reasoning}]


def to_openai_messages(
    system: str,
    messages: list[Message],
    *,
    reasoning_compat: bool = False,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for msg in messages:
        if msg.role == "user":
            out.append({"role": "user", "content": msg.content})
        elif msg.role == "assistant":
            item: dict[str, Any] = {"role": "assistant", "content": msg.content or None}
            if reasoning_compat:
                item["reasoning_content"] = reasoning_content_from_message(msg)
            if msg.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.name, "arguments": json.dumps(c.args)},
                    }
                    for c in msg.tool_calls
                ]
            out.append(item)
        else:
            out.append({"role": "tool", "tool_call_id": msg.tool_call_id, "content": msg.content})
    return out


def _is_openai_official_base_url(base_url: str | None) -> bool:
    if not base_url:
        return True
    normalized = base_url.lower().rstrip("/")
    return "api.openai.com" in normalized


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        supervisor_model: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 4096,
        timeout: float = 120.0,
        structured_mode: StructuredMode = "auto",
        client: Any | None = None,
    ) -> None:
        super().__init__(model, supervisor_model)
        self.max_tokens = max_tokens
        self.base_url = base_url
        self.structured_mode = structured_mode
        self._compat_api = not _is_openai_official_base_url(base_url)
        self.client = client or openai.OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    def _token_limit_kwargs(self) -> dict[str, int]:
        if self._compat_api:
            return {"max_tokens": self.max_tokens}
        return {"max_completion_tokens": self.max_tokens}

    def _call(self, fn: Any, **kwargs: Any) -> tuple[Any, float]:
        start = time.perf_counter()
        try:
            response = fn(**kwargs)
        except openai.RateLimitError as exc:
            raise LLMError(f"OpenAI rate limit exceeded: {exc.message}") from exc
        except openai.APIStatusError as exc:
            raise LLMError(f"OpenAI API error {exc.status_code}: {exc.message}") from exc
        except openai.APIConnectionError as exc:
            raise LLMError("Could not reach the OpenAI API") from exc
        return response, (time.perf_counter() - start) * 1000

    @staticmethod
    def _usage(response: Any) -> Usage:
        usage = getattr(response, "usage", None)
        if usage is None:
            return Usage()
        return Usage(
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        )

    @staticmethod
    def _is_response_format_error(exc: LLMError) -> bool:
        msg = str(exc).lower()
        return "response_format" in msg or "json_schema" in msg

    def _structured_native[T: BaseModel](
        self,
        *,
        system: str,
        messages: list[Message],
        schema: type[T],
        model: str,
    ) -> tuple[T, LLMResponse]:
        response, latency = self._call(
            self.client.chat.completions.parse,
            model=model,
            messages=to_openai_messages(system, messages, reasoning_compat=self._compat_api),
            response_format=schema,
            **self._token_limit_kwargs(),
        )
        message = response.choices[0].message
        if getattr(message, "refusal", None):
            raise LLMError(f"The model refused: {message.refusal}")
        parsed = message.parsed
        if parsed is None:
            raise LLMError(f"Model did not return a valid {schema.__name__}")
        meta = LLMResponse(
            content=parsed.model_dump_json(),
            usage=self._usage(response),
            model=model,
            latency_ms=latency,
        )
        return parsed, meta

    def _uses_json_object_response_format(self) -> bool:
        if self._compat_api:
            return True
        return self.structured_mode in ("json", "auto")

    def _structured_json[T: BaseModel](
        self,
        *,
        system: str,
        messages: list[Message],
        schema: type[T],
        model: str,
    ) -> tuple[T, LLMResponse]:
        schema_hint = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        system_json = (
            f"{system}\n\n"
            f"Respond with a single JSON object (json output, no markdown fences). "
            f"The object must validate against this JSON schema:\n"
            f"{schema_hint}"
        )
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": to_openai_messages(
                system_json, messages, reasoning_compat=self._compat_api
            ),
            **self._token_limit_kwargs(),
            "response_format": {"type": "json_object"},
        }
        response, latency = self._call(self.client.chat.completions.create, **kwargs)
        message = response.choices[0].message
        content = (message.content or "").strip()
        try:
            parsed = schema.model_validate(parse_json_object(content))
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            raise LLMError(f"Model did not return valid JSON: {exc}") from exc
        meta = LLMResponse(
            content=parsed.model_dump_json(),
            usage=self._usage(response),
            model=model,
            latency_ms=latency,
        )
        return parsed, meta

    def chat(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec],
        context: PromptContext,
    ) -> LLMResponse:
        model = self.model_for(context.agent)
        safe_messages = repair_messages_for_tool_api(messages)
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": to_openai_messages(
                system, safe_messages, reasoning_compat=self._compat_api
            ),
            **self._token_limit_kwargs(),
        }
        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
        response, latency = self._call(self.client.chat.completions.create, **kwargs)
        choice = response.choices[0].message
        calls: list[ToolCall] = []
        for call in choice.tool_calls or []:
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"__invalid_json__": call.function.arguments}
            calls.append(ToolCall(id=call.id, name=call.function.name, args=args))
        return LLMResponse(
            content=(choice.content or "").strip(),
            tool_calls=calls,
            usage=self._usage(response),
            model=model,
            latency_ms=latency,
            raw=capture_assistant_extras(choice),
        )

    def structured[T: BaseModel](
        self,
        *,
        system: str,
        messages: list[Message],
        schema: type[T],
        context: PromptContext,
    ) -> tuple[T, LLMResponse]:
        model = self.model_for(context.agent)
        if self._uses_json_object_response_format():
            return self._structured_json(
                system=system, messages=messages, schema=schema, model=model
            )
        if self.structured_mode == "native":
            return self._structured_native(
                system=system, messages=messages, schema=schema, model=model
            )
        try:
            return self._structured_native(
                system=system, messages=messages, schema=schema, model=model
            )
        except LLMError as exc:
            if self._is_response_format_error(exc):
                return self._structured_json(
                    system=system, messages=messages, schema=schema, model=model
                )
            raise
