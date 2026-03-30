"""
services/guideline_loader.py – Full dataset ingestion into ChromaDB.

Ingests ALL knowledge datasets using Gemini text-embedding-004:

  ICD Collection  → icd10_codes.csv + d_icd_diagnoses.csv + icd10_order_codes.csv
  CPT Collection  → cpt_codes.csv
  Guidelines      → coding_guidelines.txt (chunked, 800 chars)
  Symptoms        → symptom_dataset.csv   (symptom + question pairs)

Each document format:
  Codes       → "Code: X | Description: Y"
  Guidelines  → raw text chunk
  Symptoms    → "Symptom: X | Q: Y"

Metadata schema:
  { type: "ICD"|"CPT"|"GUIDELINE"|"SYMPTOM", code: str|None, source: str }
"""

import csv
import textwrap
from pathlib import Path

from services.rag_engine import RAGEngine
from services.embedding_service import EmbeddingService
from config import settings
try:
    from backend.utils.logging import get_logger
except ImportError:
    from utils.logging import get_logger

logger = get_logger(__name__)

# Gemini safe batch size (100 texts per embed call)
_EMBED_BATCH = 100


class GuidelineLoader:
    """
    Loads and embeds all knowledge datasets into ChromaDB via Gemini embeddings.
    """

    def __init__(self):
        self.rag = RAGEngine()
        self.embedder = EmbeddingService()
        self.data_dir = Path(settings.data_dir).resolve()

        logger.info("GuidelineLoader: data_dir = %s", self.data_dir)
        if not self.data_dir.exists():
            raise RuntimeError(f"Data directory not found: {self.data_dir}")

    # ── Public entry point ────────────────────────────────────────────────────

    async def load_all(self) -> dict:
        """Ingest all datasets. Returns row counts per collection."""
        logger.info("=== Starting full knowledge-base ingestion ===")

        icd_count  = await self._load_icd_all()
        cpt_count  = await self._load_cpt()
        guide_count = await self._load_guidelines()
        sym_count  = await self._load_symptoms()

        summary = {
            "icd10":      icd_count,
            "cpt":        cpt_count,
            "guidelines": guide_count,
            "symptoms":   sym_count,
        }
        logger.info("=== Ingestion complete: %s ===", summary)
        return summary

    # ── ICD Collection (merge-first: one doc per unique code) ─────────────────

    async def _load_icd_all(self) -> int:
        """
        Merge all ICD source files into a single deduplicated code map.

        Priority / order:
          1. d_icd_diagnoses.csv   – PRIMARY (authoritative)
          2. icd10_order_codes.csv – enrichment
          3. icd10_codes.csv       – enrichment

        Per code: descriptions from enrichment files are appended WITHOUT duplicates.
        """

        files = [
            ("d_icd_diagnoses.csv",   True),
            ("icd10_order_codes.csv", False),
            ("icd10_codes.csv",       False),
        ]

        icd_map: dict[str, dict] = {}

        for fname, is_primary in files:
            path = self.data_dir / fname
            if not path.exists():
                logger.warning("ICD file not found, skipping: %s", path)
                continue

            rows = self._read_csv(path)
            staged = 0

            for r in rows:
                code = (r.get("code") or r.get("Code") or "").strip().upper()
                desc = (
                    r.get("description") or r.get("Description")
                    or r.get("long_description") or ""
                ).strip()

                if not code or not desc:
                    continue

                if code not in icd_map:
                    icd_map[code] = {"desc": desc, "sources": [fname]}
                else:
                    # ✅ FIXED: Smart deduplicated merging
                    existing_desc = icd_map[code]["desc"]

                    parts = set(existing_desc.split(" | "))
                    parts.add(desc.strip())

                    icd_map[code]["desc"] = " | ".join(parts)

                    if fname not in icd_map[code]["sources"]:
                        icd_map[code]["sources"].append(fname)

                staged += 1

            logger.info("Processed %d ICD rows from %s", staged, fname)

        if not icd_map:
            logger.warning("No ICD rows to ingest.")
            return 0

        texts, ids, metas = [], [], []
        seen_texts: set[str] = set()

        for code, entry in icd_map.items():
            doc = f"Code: {code} | Description: {entry['desc']}"

            if len(doc.strip()) < 20:
                continue

            if doc in seen_texts:
                continue
            seen_texts.add(doc)

            texts.append(doc)
            ids.append(f"icd_{code}")
            metas.append({
                "type":   "ICD",
                "code":   code,
                "source": ",".join(entry["sources"]),
            })

        logger.info(
            "ICD merge complete: %d unique codes → %d documents",
            len(icd_map), len(texts),
        )

        if not texts:
            return 0

        await self._embed_and_upsert(
            texts, ids, metas,
            upsert_fn=self.rag.upsert_icd,
            label="ICD",
        )
        return len(texts)

    # ── CPT Collection ────────────────────────────────────────────────────────

    async def _load_cpt(self) -> int:
        path = self.data_dir / "cpt_codes.csv"
        if not path.exists():
            logger.warning("CPT file not found: %s", path)
            return 0

        texts, ids, metas = [], [], []
        seen_texts: set[str] = set()

        for r in self._read_csv(path):
            code = (
                r.get("code") or r.get("CPT") or r.get("cpt")
                or r.get("HCPCS") or r.get("HCPC") or ""
            ).strip().upper()

            desc = (
                r.get("description") or r.get("Description")
                or r.get("LONG DESCRIPTION") or r.get("desc") or ""
            ).strip()

            if not code or not desc:
                continue

            doc = f"Code: {code} | Description: {desc}"

            if len(doc.strip()) < 20 or doc in seen_texts:
                continue

            seen_texts.add(doc)

            texts.append(doc)
            ids.append(f"cpt_{code}")
            metas.append({"type": "CPT", "code": code, "source": "cpt_codes.csv"})

        if not texts:
            return 0

        await self._embed_and_upsert(texts, ids, metas, self.rag.upsert_cpt, "CPT")
        return len(texts)

    # ── Guidelines ────────────────────────────────────────────────────────────

    async def _load_guidelines(self) -> int:
        folder = self.data_dir / "coding_guidelines"
        single = self.data_dir / "coding_guidelines.txt"

        raw_chunks = []

        if folder.exists():
            for txt in sorted(folder.glob("*.txt")):
                content = txt.read_text(encoding="utf-8", errors="replace").strip()
                for i, chunk in enumerate(self._chunk_text(content)):
                    raw_chunks.append((f"guide_{txt.stem}_{i}", chunk, txt.name))
        elif single.exists():
            content = single.read_text(encoding="utf-8", errors="replace").strip()
            for i, chunk in enumerate(self._chunk_text(content)):
                raw_chunks.append((f"guide_{i}", chunk, "coding_guidelines.txt"))
        else:
            return 0

        texts, ids, metas = [], [], []
        seen_texts: set[str] = set()

        for doc_id, chunk, src in raw_chunks:
            if len(chunk.strip()) < 20 or chunk in seen_texts:
                continue

            seen_texts.add(chunk)

            texts.append(chunk)
            ids.append(doc_id)
            metas.append({"type": "GUIDELINE", "source": src})

        if not texts:
            return 0

        await self._embed_and_upsert(texts, ids, metas, self.rag.upsert_guidelines, "GUIDELINE")
        return len(texts)

    # ── Symptoms ─────────────────────────────────────────────────────────────

    async def _load_symptoms(self) -> int:
        path = self.data_dir / "symptom_dataset.csv"
        if not path.exists():
            return 0

        texts, ids, metas = [], [], []
        seen_texts: set[str] = set()

        for i, r in enumerate(self._read_csv(path)):
            symptom  = (r.get("symptoms") or r.get("symptom") or "").strip()
            question = (r.get("question") or r.get("Question") or "").strip()

            if not symptom and not question:
                continue

            if symptom and question:
                doc = f"Symptom: {symptom} | Q: {question}"
            elif symptom:
                doc = f"Symptom: {symptom}"
            else:
                doc = f"Q: {question}"

            if len(doc.strip()) < 20 or doc in seen_texts:
                continue

            seen_texts.add(doc)

            texts.append(doc)
            ids.append(f"sym_{i}")
            metas.append({"type": "SYMPTOM", "source": "symptom_dataset.csv"})

        if not texts:
            return 0

        await self._embed_and_upsert(texts, ids, metas, self.rag.upsert_symptoms, "SYMPTOM")
        return len(texts)

    # ── Shared embedding ─────────────────────────────────────────────────────

    async def _embed_and_upsert(self, texts, ids, metas, upsert_fn, label: str):
        total = len(texts)
        all_embeddings = []

        for i in range(0, total, _EMBED_BATCH):
            batch = texts[i : i + _EMBED_BATCH]
            embs = await self.embedder.embed_texts(batch)
            all_embeddings.extend(embs)

        upsert_fn(ids=ids, embeddings=all_embeddings, documents=texts, metadatas=metas)

    # ── Utilities ────────────────────────────────────────────────────────────

    @staticmethod
    def _chunk_text(text: str, width: int = 800):
        return [
            c for c in textwrap.wrap(
                text, width=width,
                break_long_words=False,
                break_on_hyphens=False,
            )
            if c.strip()
        ]

    @staticmethod
    def _read_csv(path: Path):
        rows = []
        with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append({
                    (k.strip() if k else ""): (v.strip() if v else "")
                    for k, v in row.items()
                })
        return rows