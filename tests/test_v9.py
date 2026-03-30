import asyncio
from services.selection_engine import SelectionEngine
from services.entity_extractor import EntityExtractor
from services.rag_engine import RAGEngine

async def test_v9():
    extractor = EntityExtractor()
    rag = RAGEngine()
    selector = SelectionEngine()

    test_cases = [
        ("DM2 only", "Patient has type 2 diabetes mellitus."),
        ("DM2 + neuropathy", "Patient has DM2 and peripheral neuropathy."),
        ("CKD stage 3b", "Patient has CKD stage 3b."),
        ("HTN + DM2 + obesity", "Patient diagnosed with hypertension, type 2 diabetes, and obesity."),
        ("HF acute on chronic", "Acute on chronic systolic heart failure."),
        ("FULL CASE", "Patient has type 2 diabetes with neuropathy, acute on chronic systolic heart failure, CKD stage 3, obesity, and hyperlipidemia. Procedure: laparoscopic cholecystectomy.")
    ]

    for name, text in test_cases:
        print(f"\n--- Testing: {name} ---")
        extraction = extractor.extract(text)
        entities = extraction.get("entities", [])
        print(f"Entities extracted: {[e['text'] for e in entities]}")

        candidates = []
        for e in entities:
            res = await rag.query(e['text'], n_results=15, code_type=e.get('type', 'ICD-10'))
            docs = res.get('documents', [[]])[0]
            metas = res.get('metadatas', [[]])[0]
            scores = res.get('scores', [[]])[0]
            for doc, meta, score in zip(docs, metas, scores):
                candidates.append({
                    "code": meta.get("code"),
                    "description": doc,
                    "type": meta.get("type"),
                    "score": score,
                    "confidence": score,
                    "source": "rag",
                    "entity": e['text']
                })
        
        deterministic = extraction.get("deterministic_codes", [])
        final = selector.select(candidates, text, deterministic)
        print(f"Final Codes: {[c['code'] for c in final]}")

if __name__ == "__main__":
    asyncio.run(test_v9())
