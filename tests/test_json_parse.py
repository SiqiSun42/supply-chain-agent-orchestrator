import pytest

from orchestrator.llm.json_parse import parse_json_object


def test_parse_json_strips_control_characters() -> None:
    raw = '{"next": "ops", "instructions": "go", "reasoning": "ok\u0000here"}'
    data = parse_json_object(raw)
    assert data["next"] == "ops"
    assert "ok" in data["reasoning"]


def test_parse_json_from_markdown_fence() -> None:
    raw = '```json\n{"next": "FINISH", "instructions": "", "reasoning": "done"}\n```'
    data = parse_json_object(raw)
    assert data["next"] == "FINISH"


def test_parse_json_empty_raises() -> None:
    with pytest.raises(ValueError):
        parse_json_object("   ")
