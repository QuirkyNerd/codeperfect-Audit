import asyncio
import sys
import os

# Set up path so we can import backend modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.coding_logic import CodingLogicAgent
from services.rag_engine import RAGEngine

TEST_CASES = [
    "Type 2 diabetes mellitus without complications",
    "Type 2 diabetes with peripheral neuropathy",
    "CKD stage 3b",
    "Hypertension, diabetes type 2, obesity",
    "Acute on chronic systolic heart failure",
    "Patient has Type 2 diabetes with peripheral neuropathy, acute on chronic systolic heart failure, CKD stage 3b, morbid obesity, and mixed hyperlipidemia. Procedure performed: laparoscopic cholecystectomy."
]

async def main():
    agent = CodingLogicAgent()
    print("\n" + "="*80)
    print("RUNNING FINAL VALIDATION MODE TESTS")
    print("="*80 + "\n")
    
    for i, case in enumerate(TEST_CASES, 1):
        print(f"\n--- TEST {i} ---")
        print(f"INPUT:  {case}")
        result = await agent.analyze(case)
        codes = [c['code'] for c in result.get("data", {}).get("codes", [])]
        print(f"OUTPUT: {codes}")
        
if __name__ == "__main__":
    asyncio.run(main())
