"""
services/validator.py - Post-LLM Anti-Hallucination validation layer.
Throws out or flags codes hallucinated by the LLM by confirming physical existence within the Vector Database.
"""
from services.rag_engine import RAGEngine
try:
    from backend.utils.logging import get_logger
except ImportError:
    from utils.logging import get_logger

logger = get_logger(__name__)

class AntiHallucinationValidator:
    def __init__(self):
        self.rag = RAGEngine()
        # To be valid, the exact code must exist, or the generated description must be highly similar.
        self.similarity_threshold = 0.50

    async def validate_codes(self, ai_codes: list[dict]) -> list[dict]:
        """
        Verify each AI suggested code actually exists in the RAG Index.
        Flags hallucinations.
        """
        validated_codes = []
        for code_entry in ai_codes:
            code = code_entry.get("code")
            desc = code_entry.get("description", "")
            
            # Query vector database directly with the code text
            results = await self.rag.query(f"{code} {desc}", n_results=5)
            
            # Extract returned metadatas which contain the actual code
            found_meta = results.get("metadatas", [[]])[0]
            
            # Check if our exact code is in the top 5 retrieved
            actual_codes = [m.get("code") for m in found_meta]
            if code in actual_codes:
                validated_codes.append(code_entry)
            else:
                logger.warning(f"AntiHallucinationValidator: Hallucinated code removed: {code}")
                # We could append with a zeroed confidence, but dropping it entirely is safer 
                # for strict compliance requirements.
        
        return validated_codes
