"""
tests/test_coding_logic.py – Unit tests for the CodingLogicAgent.

Mocks both AsyncOpenAI and RAGEngine to avoid external API calls.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

SAMPLE_CLINICAL_FACTS = {
    "diagnoses": [{"entity": "Essential hypertension", "evidence_sentence": "Hypertension noted."}],
    "procedures": [{"entity": "Laparoscopic cholecystectomy", "evidence_sentence": "Lap chole done."}],
    "comorbidities": [{"entity": "Type 2 diabetes mellitus", "evidence_sentence": "DM2 noted."}],
    "medications": [],
    "clinical_summary": "Hypertension and DM2 patient with lap chole.",
    "evidence_sentences": {},
}

SAMPLE_CODE_RESPONSE = {
    "codes": [
        {"code": "I10",   "description": "Essential hypertension", "type": "ICD-10", "confidence": 0.95, "rationale": "Documented."},
        {"code": "E11.9", "description": "Type 2 DM", "type": "ICD-10", "confidence": 0.90, "rationale": "Documented."},
        {"code": "47562", "description": "Lap chole", "type": "CPT", "confidence": 0.88, "rationale": "Procedure."},
        {"code": "Z87.0", "description": "History code", "type": "ICD-10", "confidence": 0.40, "rationale": "Low."},
    ]
}

MOCK_RAG = {"documents": [[]], "metadatas": [[]]}


def _mock_response(content: str):
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
async def test_generate_codes_splits_by_confidence():
    """Codes above 0.65 should be in codes; below 0.65 in low_confidence_codes."""
    with patch("agents.coding_logic.AsyncOpenAI") as MockClient, \
         patch("agents.coding_logic.RAGEngine") as MockRAG:
        MockRAG.return_value.query.return_value = MOCK_RAG
        instance = MockClient.return_value
        instance.chat.completions.create = AsyncMock(
            return_value=_mock_response(json.dumps(SAMPLE_CODE_RESPONSE))
        )
        from agents.coding_logic import CodingLogicAgent
        agent = CodingLogicAgent()
        result = await agent.generate_codes(SAMPLE_CLINICAL_FACTS)

    assert result["success"] is True
    data = result["data"]
    assert len(data["codes"]) == 3
    assert len(data["low_confidence_codes"]) == 1
    assert data["low_confidence_codes"][0]["code"] == "Z87.0"


@pytest.mark.asyncio
async def test_generate_codes_normalizes_codes():
    """Codes like E119 should be normalised to E11.9."""
    raw_response = {"codes": [
        {"code": "e119", "description": "Type 2 DM", "type": "ICD-10", "confidence": 0.90, "rationale": ""},
    ]}
    with patch("agents.coding_logic.AsyncOpenAI") as MockClient, \
         patch("agents.coding_logic.RAGEngine") as MockRAG:
        MockRAG.return_value.query.return_value = MOCK_RAG
        instance = MockClient.return_value
        instance.chat.completions.create = AsyncMock(
            return_value=_mock_response(json.dumps(raw_response))
        )
        from agents.coding_logic import CodingLogicAgent
        agent = CodingLogicAgent()
        result = await agent.generate_codes(SAMPLE_CLINICAL_FACTS)

    assert result["success"] is True
    assert result["data"]["codes"][0]["code"] == "E11.9"


@pytest.mark.asyncio
async def test_generate_codes_empty_facts():
    """Empty clinical facts should produce empty codes without crashing."""
    empty = {"diagnoses":[],"procedures":[],"comorbidities":[],"medications":[],
             "clinical_summary":"","evidence_sentences":{}}
    with patch("agents.coding_logic.AsyncOpenAI") as MockClient, \
         patch("agents.coding_logic.RAGEngine") as MockRAG:
        MockRAG.return_value.query.return_value = MOCK_RAG
        instance = MockClient.return_value
        instance.chat.completions.create = AsyncMock(
            return_value=_mock_response(json.dumps({"codes": []}))
        )
        from agents.coding_logic import CodingLogicAgent
        agent = CodingLogicAgent()
        result = await agent.generate_codes(empty)

    assert result["success"] is True
    assert result["data"]["codes"] == []
