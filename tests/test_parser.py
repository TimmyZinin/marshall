"""Tests for the message parser."""
import json
import pytest
from unittest.mock import AsyncMock, patch

from src.parser.llm import _extract_json
from src.parser.prompt import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE


def test_extract_json_plain():
    result = _extract_json('{"trip_id": "4521", "status": "problem"}')
    assert result["trip_id"] == "4521"
    assert result["status"] == "problem"


def test_extract_json_with_code_fence():
    text = '```json\n{"trip_id": "4521", "skip": true}\n```'
    result = _extract_json(text)
    assert result["skip"] is True


def test_extract_json_with_whitespace():
    text = '  \n  {"confidence": 0.95}  \n  '
    result = _extract_json(text)
    assert result["confidence"] == 0.95


def test_extract_json_invalid():
    with pytest.raises(json.JSONDecodeError):
        _extract_json("not json at all")


def test_system_prompt_contains_fields():
    assert "trip_id" in SYSTEM_PROMPT
    assert "route_from" in SYSTEM_PROMPT
    assert "urgency" in SYSTEM_PROMPT
    assert "confidence" in SYSTEM_PROMPT


def test_user_prompt_template():
    result = USER_PROMPT_TEMPLATE.format(
        sender_name="Иванов А.П.",
        chat_name="Диспетчерская WB",
        text="Рейс 4521, стою в пробке",
    )
    assert "Иванов А.П." in result
    assert "Диспетчерская WB" in result
    assert "Рейс 4521" in result
