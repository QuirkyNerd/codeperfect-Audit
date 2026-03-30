#!/usr/bin/env python
"""
scripts/ingest_guidelines.py – Full knowledge-base ingestion for CodePerfectAuditor.

Populates ChromaDB with ALL datasets:
  • icd10_codes.csv + d_icd_diagnoses.csv + icd10_order_codes.csv  → icd10_codes collection
  • cpt_codes.csv                                                   → cpt_codes collection
  • coding_guidelines.txt                                           → coding_guidelines collection
  • symptom_dataset.csv                                             → symptoms collection

Prerequisites:
  • GEMINI_API_KEY must be set in .env
  • Run AFTER wiping chroma_store if switching embedding models

Usage (local):
  cd d:/Desktop/virtusa_jatayu/CodePerfectAuditor
  python scripts/ingest_guidelines.py

Usage (Docker):
  docker compose exec backend python /app/scripts/ingest_guidelines.py
"""

import asyncio
import sys
import os

# Add backend/ to Python path so imports resolve correctly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from services.guideline_loader import GuidelineLoader
from utils.logging import get_logger

logger = get_logger("ingest_guidelines")


async def main():
    logger.info("=== CodePerfectAuditor – Knowledge Base Ingestion ===")
    logger.info("Datasets: icd10_codes, d_icd_diagnoses, icd10_order_codes, cpt_codes, coding_guidelines, symptom_dataset")

    try:
        loader = GuidelineLoader()
        counts = await loader.load_all()

        print("\n✅ Ingestion complete!")
        print(f"  ICD codes loaded        : {counts.get('icd10', 0):>8,}")
        print(f"  CPT codes loaded        : {counts.get('cpt', 0):>8,}")
        print(f"  Guideline chunks loaded : {counts.get('guidelines', 0):>8,}")
        print(f"  Symptom entries loaded  : {counts.get('symptoms', 0):>8,}")
        total = sum(counts.values())
        print(f"  ─────────────────────────────────────")
        print(f"  Total documents         : {total:>8,}")
        print("\n🚀 Vector database ready. You can now start the backend.\n")

    except Exception as e:
        logger.exception("Ingestion failed: %s", str(e))
        print(f"\n❌ Ingestion failed: {e}")
        print("Check that GEMINI_API_KEY is set and data files exist in backend/data/.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())