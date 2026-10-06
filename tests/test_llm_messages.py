from orchestrator.llm.base import Message, ToolCall
from orchestrator.llm.messages import normalize_tool_scratch, repair_messages_for_tool_api


def test_normalize_keeps_assistant_tool_calls_awaiting_hitl_response() -> None:
    scratch = [
        Message(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id="req-1", name="request_replenishment_approval", args={})],
        ),
    ]
    out = normalize_tool_scratch(scratch)
    assert len(out) == 1
    assert out[0].tool_calls[0].id == "req-1"


def test_normalize_drops_orphan_tool_messages() -> None:
    scratch = [
        Message(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id="req-1", name="request_replenishment_approval", args={})],
        ),
        Message(role="tool", tool_call_id="req-1", content='{"ok": true}'),
        Message(role="tool", tool_call_id="orphan", content='{"bad": true}'),
    ]
    out = normalize_tool_scratch(scratch)
    tool_ids = [m.tool_call_id for m in out if m.role == "tool"]
    assert tool_ids == ["req-1"]


def test_repair_drops_tool_without_preceding_assistant_tool_calls() -> None:
    messages = [
        Message(role="user", content="task brief"),
        Message(role="assistant", content="done"),
        Message(role="tool", tool_call_id="req-1", content='{"ok": true}'),
    ]
    out = repair_messages_for_tool_api(messages)
    assert [m.role for m in out] == ["user", "assistant"]


def test_repair_keeps_valid_tool_chain_for_api() -> None:
    messages = [
        Message(role="user", content="task brief"),
        Message(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id="req-1", name="request_replenishment_approval", args={})],
        ),
        Message(role="tool", tool_call_id="req-1", content='{"status": "approved"}'),
        Message(role="assistant", content="Leadership selected SUP-01."),
    ]
    out = repair_messages_for_tool_api(messages)
    assert [m.role for m in out] == ["user", "assistant", "tool", "assistant"]
