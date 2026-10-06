from __future__ import annotations

import json
import re
from typing import Any


def sanitize_json_text(text: str) -> str:
    stripped = text.strip()
    fence = re.match(r"^```(?:json)?\s*\n?(.*)\n?```\s*$", stripped, re.DOTALL | re.IGNORECASE)
    payload = fence.group(1).strip() if fence else stripped
    cleaned: list[str] = []
    for ch in payload:
        if ch in "\n\r\t":
            cleaned.append(ch)
        elif ord(ch) < 32:
            cleaned.append(" ")
        else:
            cleaned.append(ch)
    return "".join(cleaned)


def parse_json_object(text: str) -> dict[str, Any]:
    payload = sanitize_json_text(text)
    if not payload:
        raise ValueError("empty JSON payload")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        start = payload.find("{")
        end = payload.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(sanitize_json_text(payload[start : end + 1]))
        else:
            raise
    if not isinstance(data, dict):
        raise ValueError("JSON value must be an object")
    return data
