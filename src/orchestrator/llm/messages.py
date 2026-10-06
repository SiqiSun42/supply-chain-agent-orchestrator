from __future__ import annotations

from orchestrator.llm.base import Message


def normalize_tool_scratch(scratch: list[Message]) -> list[Message]:
    if not scratch:
        return scratch
    out: list[Message] = []
    i = 0
    while i < len(scratch):
        msg = scratch[i]
        if msg.role != "assistant" or not msg.tool_calls:
            out.append(msg)
            i += 1
            continue
        call_ids = [c.id for c in msg.tool_calls]
        tools_by_id: dict[str, Message] = {}
        j = i + 1
        while j < len(scratch) and scratch[j].role == "tool":
            tool_msg = scratch[j]
            if tool_msg.tool_call_id:
                tools_by_id[tool_msg.tool_call_id] = tool_msg
            j += 1
        answered_ids = [cid for cid in call_ids if cid in tools_by_id]
        if not answered_ids:
            out.append(msg)
            i += 1
            continue
        kept_calls = [c for c in msg.tool_calls if c.id in answered_ids]
        out.append(
            Message(
                role="assistant",
                content=msg.content,
                tool_calls=kept_calls,
                raw=msg.raw,
            )
        )
        for call in kept_calls:
            out.append(tools_by_id[call.id])
        i = j
    return out


def repair_messages_for_tool_api(messages: list[Message]) -> list[Message]:
    normalized = normalize_tool_scratch(messages)
    out: list[Message] = []
    active_tool_ids: set[str] = set()
    for msg in normalized:
        if msg.role == "assistant":
            if active_tool_ids:
                out = _drop_unanswered_assistant_tool_calls(out, active_tool_ids)
                active_tool_ids = set()
            out.append(msg)
            active_tool_ids = {c.id for c in msg.tool_calls}
        elif msg.role == "tool":
            tid = msg.tool_call_id or ""
            if tid in active_tool_ids:
                out.append(msg)
                active_tool_ids.discard(tid)
        else:
            if active_tool_ids:
                out = _drop_unanswered_assistant_tool_calls(out, active_tool_ids)
                active_tool_ids = set()
            out.append(msg)
    if active_tool_ids:
        out = _drop_unanswered_assistant_tool_calls(out, active_tool_ids)
    return out


def _drop_unanswered_assistant_tool_calls(
    messages: list[Message], unanswered_ids: set[str]
) -> list[Message]:
    if not messages or not unanswered_ids:
        return messages
    out = list(messages)
    for idx in range(len(out) - 1, -1, -1):
        msg = out[idx]
        if msg.role != "assistant" or not msg.tool_calls:
            continue
        remaining = [c for c in msg.tool_calls if c.id in unanswered_ids]
        if not remaining:
            continue
        kept = [c for c in msg.tool_calls if c.id not in unanswered_ids]
        if kept:
            out[idx] = Message(
                role="assistant",
                content=msg.content,
                tool_calls=kept,
                raw=msg.raw,
            )
        else:
            out[idx] = Message(role="assistant", content=msg.content or "", raw=msg.raw)
        break
    return out
