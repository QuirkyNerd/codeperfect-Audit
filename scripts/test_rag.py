import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

from backend.services.rag_engine import RAGEngine

rag = RAGEngine()

results = rag.query("hypertension", n_results=5)

print("\n=== RAG RESULTS ===\n")
print(results)