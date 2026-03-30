"""
tests/test_auditor.py – Unit tests for the AuditorAgent.

Tests cover both the GPT-4 path (mocked) and the deterministic fallback.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

HUMAN_CODES = ["I10"]
AI_CODES = [
    {"code": "I10",   "description": "Essential hypertension", "type": "ICD-10", "confidence": 0.95},
    {"code": "E11.9", "description": "Type 2 DM", "type": "ICD-10", "confidence": 0.90},
    {"code": "47562", "description": "Lap chole", "type": "CPT", "confidence": 0.88},
]

SAMPLE_AUDITOR_RESPONSE = {
    "discrepancies": [
        {"code": "I10",   "type": "correct_code",  "message": "Correct.", "severity": "low"},
        {"code": "E11.9", "type": "missed_code",   "message": "Missed DM2.", "severity": "high"},
        {"code": "47562", "type": "missed_code",   "message": "Missed procedure.", "severity": "high"},
    ],
    "summary": "Human coder missed comorbidity codes.",
}


def _mock_response(content: str):
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
async def test_compare_codes_gpt_path():
    """AuditorAgent should return GPT-classified discrepancies on success."""
    with patch("agents.auditor.AsyncOpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create = AsyncMock(
            return_value=_mock_response(json.dumps(SAMPLE_AUDITOR_RESPONSE))
        )
        from agents.auditor import AuditorAgent
        agent = AuditorAgent()
        result = await agent.compare_codes(HUMAN_CODES, AI_CODES, "Note text.")

    assert result["success"] is True
    assert len(result["data"]["discrepancies"]) == 3
    assert result["data"]["summary"] == "Human coder missed comorbidity codes."


@pytest.mark.asyncio
async def test_compare_codes_deterministic_fallback():
    """Should use set-based comparison when GPT raises an exception."""
    with patch("agents.auditor.AsyncOpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create = AsyncMock(side_effect=Exception("API error"))
        from agents.auditor import AuditorAgent
        agent = AuditorAgent()
        result = await agent.compare_codes(HUMAN_CODES, AI_CODES)

    assert result["success"] is True
    types_by_code = {d["code"]: d["type"] for d in result["data"]["discrepancies"]}
    assert types_by_code.get("I10")   == "correct_code"
    assert types_by_code.get("E11.9") == "missed_code"
    assert types_by_code.get("47562") == "missed_code"


def test_deterministic_compare_all_three_types():
    """Exercise all three classification types in a single call."""
    from agents.auditor import _deterministic_compare
    human = ["I10", "J99.0"]
    ai = [
        {"code": "I10",   "confidence": 0.95, "description": "Hypertension"},
        {"code": "E11.9", "confidence": 0.90, "description": "Type 2 DM"},
    ]
    disc = _deterministic_compare(human, ai)
    types = {d["code"]: d["type"] for d in disc}
    assert types["I10"]   == "correct_code"
    assert types["E11.9"] == "missed_code"
    assert types["J99.0"] == "unsupported_code"


def test_deterministic_compare_normalizes_codes():
    """Human codes like 'e119' should normalise and match 'E11.9' in AI list."""
    from agents.auditor import _deterministic_compare
    human = ["e119"]
    ai = [{"code": "E11.9", "confidence": 0.90, "description": "Type 2 DM"}]
    disc = _deterministic_compare(human, ai)
    types = {d["code"]: d["type"] for d in disc}
    assert types.get("E11.9") == "correct_code"
