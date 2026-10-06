"""Provider adapters, exercised with fake SDK clients (no network)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from orchestrator.agents.contracts import RouteDecision
from orchestrator.llm.anthropic_provider import AnthropicProvider, to_anthropic_messages
from orchestrator.llm.base import Message, PromptContext, ToolCall, ToolSpec
from orchestrator.llm.openai_provider import OpenAIProvider, to_openai_messages

SCRATCH = [
    Message(role="user", content="task"),
    Message(
        role="assistant",
        content="looking",
        tool_calls=[
            ToolCall(id="a", name="calculator", args={"expression": "1+1"}),
            ToolCall(id="b", name="current_time", args={}),
        ],
    ),
    Message(role="tool", tool_call_id="a", content='{"result": 2}'),
    Message(role="tool", tool_call_id="b", content='{"iso": "now"}', is_error=True),
]


def test_anthropic_message_conversion_merges_tool_results() -> None:
    out = to_anthropic_messages(SCRATCH)
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert [b["type"] for b in out[1]["content"]] == ["text", "tool_use", "tool_use"]
    assert [b["tool_use_id"] for b in out[2]["content"]] == ["a", "b"]
    assert out[2]["content"][1]["is_error"] is True


def test_anthropic_replays_raw_blocks() -> None:
    raw = [{"type": "thinking", "thinking": "", "signature": "sig"}, {"type": "text", "text": "x"}]
    out = to_anthropic_messages([Message(role="assistant", content="x", raw=raw)])
    assert out[0]["content"] == raw


def test_openai_message_conversion() -> None:
    out = to_openai_messages("sys", SCRATCH)
    assert out[0] == {"role": "system", "content": "sys"}
    assert out[2]["tool_calls"][0]["function"]["arguments"] == '{"expression": "1+1"}'
    assert [m["role"] for m in out[3:]] == ["tool", "tool"]


def test_openai_message_conversion_reasoning_compat() -> None:
    from orchestrator.llm.base import Message

    stored = Message(
        role="assistant",
        content="call tools",
        raw=[{"reasoning_content": "internal chain-of-thought"}],
    )
    synthetic = Message(role="assistant", content="done")
    out = to_openai_messages("sys", [stored, synthetic], reasoning_compat=True)
    assert out[1]["reasoning_content"] == "internal chain-of-thought"
    assert out[2]["reasoning_content"] == ""


def test_openai_provider_stores_reasoning_raw() -> None:
    def create(**kwargs: Any) -> Any:
        message = SimpleNamespace(
            content="ok",
            tool_calls=[],
            reasoning_content="thought",
            model_dump=lambda **_: {"reasoning_content": "thought", "content": "ok"},
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )

    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    provider = OpenAIProvider(
        api_key="x",
        model="deepseek-reasoner",
        base_url="https://api.deepseek.com",
        client=fake,
    )
    result = provider.chat(
        system="s",
        messages=[Message(role="user", content="hi")],
        tools=[],
        context=PromptContext(task="hi", agent="ops"),
    )
    assert result.raw == [{"reasoning_content": "thought"}]
    replay = to_openai_messages(
        "s",
        [Message(role="user", content="hi"), Message(role="assistant", content="ok", raw=result.raw)],
        reasoning_compat=True,
    )
    assert replay[2]["reasoning_content"] == "thought"


class _Block(SimpleNamespace):
    def model_dump(self, **_: Any) -> dict[str, Any]:
        return dict(self.__dict__)


def test_anthropic_provider_parses_tool_calls() -> None:
    captured: dict[str, Any] = {}

    def create(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return SimpleNamespace(
            stop_reason="tool_use",
            usage=SimpleNamespace(input_tokens=11, output_tokens=7),
            content=[
                _Block(type="text", text="Let me compute."),
                _Block(type="tool_use", id="t1", name="calculator", input={"expression": "2*3"}),
            ],
        )

    fake = SimpleNamespace(messages=SimpleNamespace(create=create))
    provider = AnthropicProvider(api_key="x", model="claude-sonnet-5", client=fake)
    spec = ToolSpec(name="calculator", description="d", parameters={"type": "object"})
    result = provider.chat(
        system="s",
        messages=[Message(role="user", content="hi")],
        tools=[spec],
        context=PromptContext(task="hi", agent="analyst"),
    )
    assert captured["model"] == "claude-sonnet-5"
    assert "temperature" not in captured
    assert captured["tools"][0]["input_schema"] == {"type": "object"}
    assert result.tool_calls == [ToolCall(id="t1", name="calculator", args={"expression": "2*3"})]
    assert result.usage.input_tokens == 11
    assert result.raw and result.raw[1]["type"] == "tool_use"


def test_openai_provider_structured_output_uses_supervisor_model() -> None:
    captured: dict[str, Any] = {}
    decision = RouteDecision(next="researcher", instructions="look", reasoning="r")

    def parse(**kwargs: Any) -> Any:
        captured.update(kwargs)
        message = SimpleNamespace(parsed=decision, refusal=None)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3),
        )

    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))
    provider = OpenAIProvider(
        api_key="x",
        model="gpt-worker",
        supervisor_model="gpt-router",
        structured_mode="native",
        client=fake,
    )
    parsed, meta = provider.structured(
        system="s",
        messages=[Message(role="user", content="hi")],
        schema=RouteDecision,
        context=PromptContext(task="hi", agent="supervisor"),
    )
    assert parsed.next == "researcher"
    assert captured["model"] == "gpt-router"
    assert captured["response_format"] is RouteDecision
    assert meta.usage.output_tokens == 3


def test_structured_json_uses_json_object_response_format() -> None:
    captured: dict[str, Any] = {}

    def create(**kwargs: Any) -> Any:
        captured.update(kwargs)
        message = SimpleNamespace(
            content='{"next": "ops", "instructions": "x", "reasoning": "r"}'
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )

    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    provider = OpenAIProvider(
        api_key="x",
        model="deepseek-flash",
        base_url="https://api.deepseek.com",
        structured_mode="json",
        client=fake,
    )
    provider.structured(
        system="route",
        messages=[Message(role="user", content="task")],
        schema=RouteDecision,
        context=PromptContext(task="task", agent="supervisor"),
    )
    assert captured["response_format"] == {"type": "json_object"}
    assert "json" in captured["messages"][0]["content"].lower()


def test_openai_structured_json_mode_for_compat_api() -> None:
    captured: dict[str, Any] = {}

    def create(**kwargs: Any) -> Any:
        captured.update(kwargs)
        message = SimpleNamespace(
            content='{"next": "ops", "instructions": "query inventory", "reasoning": "db read"}'
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3),
        )

    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create, parse=create)))
    provider = OpenAIProvider(
        api_key="x",
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        structured_mode="json",
        client=fake,
    )
    parsed, _meta = provider.structured(
        system="s",
        messages=[Message(role="user", content="hi")],
        schema=RouteDecision,
        context=PromptContext(task="hi", agent="supervisor"),
    )
    assert parsed.next == "ops"
    assert captured["response_format"] == {"type": "json_object"}
    assert "max_tokens" in captured
    assert "max_completion_tokens" not in captured
