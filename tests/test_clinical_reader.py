"""
tests/test_clinical_reader.py – Unit tests for the ClinicalReaderAgent.

All tests mock OpenAI calls — no real API key is required.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

SAMPLE_GPT_RESPONSE = {
    "diagnoses": [
        {"entity": "Essential hypertension", "evidence_sentence": "Patient has uncontrolled hypertension."}
    ],
    "procedures": [
        {"entity": "Laparoscopic cholecystectomy", "evidence_sentence": "Lap chole performed 2025-01-17."}
    ],
    "comorbidities": [
        {"entity": "Type 2 diabetes mellitus", "evidence_sentence": "Type 2 DM noted."}
    ],
    "medications": [
        {"entity": "Furosemide", "evidence_sentence": "Furosemide 40 mg daily prescribed."}
    ],
    "clinical_summary": "Hypertension and DM2 patient with lap chole.",
}

SAMPLE_NOTE = (
    "Patient has uncontrolled hypertension. "
    "Type 2 DM noted. "
    "Lap chole performed 2025-01-17. "
    "Furosemide 40 mg daily prescribed."
)


def _mock_response(content: str):
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
async def test_extract_entities_success():
    """Should return structured medical entities from a valid GPT JSON response."""
    with patch("agents.clinical_reader.AsyncOpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create = AsyncMock(
            return_value=_mock_response(json.dumps(SAMPLE_GPT_RESPONSE))
        )
        from agents.clinical_reader import ClinicalReaderAgent
        agent = ClinicalReaderAgent()
        result = await agent.extract_medical_entities(SAMPLE_NOTE)

    assert result["success"] is True
    data = result["data"]
    assert len(data["diagnoses"]) == 1
    assert data["diagnoses"][0]["entity"] == "Essential hypertension"
    assert "Essential hypertension" in data["evidence_sentences"]


@pytest.mark.asyncio
async def test_extract_handles_json_error():
    """Should return failure result on persistent JSON decode errors."""
    with patch("agents.clinical_reader.AsyncOpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create = AsyncMock(
            return_value=_mock_response("not valid json {{{{")
        )
        from agents.clinical_reader import ClinicalReaderAgent
        agent = ClinicalReaderAgent()
        result = await agent.extract_medical_entities(SAMPLE_NOTE)

    assert "success" in result


@pytest.mark.asyncio
async def test_extract_empty_note():
    """Should gracefully handle empty GPT response for a minimal note."""
    empty = {"diagnoses": [], "procedures": [], "comorbidities": [],
             "medications": [], "clinical_summary": "No findings."}
    with patch("agents.clinical_reader.AsyncOpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create = AsyncMock(
            return_value=_mock_response(json.dumps(empty))
        )
        from agents.clinical_reader import ClinicalReaderAgent
        agent = ClinicalReaderAgent()
        result = await agent.extract_medical_entities("Brief visit.")

    assert result["success"] is True
    assert result["data"]["diagnoses"] == []
