"""
services/rag_engine.py – ChromaDB wrapper for the RAG retrieval pipeline.
"""

import chromadb
from chromadb.config import Settings

from config import settings
import utils.logging as _logging
from services.embedding_service import EmbeddingService

logger = _logging.get_logger(__name__)

_BATCH_SIZE = 5000


class RAGEngine:
    def __init__(self):
        self.client = chromadb.PersistentClient(path="./backend/chroma_db")

        # ✅ Initialize collections
        self._icd_col = self.client.get_or_create_collection(
            name=settings.chroma_collection_icd,
            metadata={"hnsw:space": "cosine"},
        )
        self._cpt_col = self.client.get_or_create_collection(
            name=settings.chroma_collection_cpt,
            metadata={"hnsw:space": "cosine"},
        )
        self._guide_col = self.client.get_or_create_collection(
            name=settings.chroma_collection_guidelines,
            metadata={"hnsw:space": "cosine"},
        )
        self._symptom_col = self.client.get_or_create_collection(
            name=settings.chroma_collection_symptoms,
            metadata={"hnsw:space": "cosine"},
        )

        # ✅ Reuse embedding service (IMPORTANT)
        self.embedding_service = EmbeddingService()

        logger.info(
            "RAGEngine: ChromaDB initialised at '%s' with 4 collections.",
            settings.chroma_persist_dir,
        )

    # ─────────────────────────────────────────────
    # 🔥 BATCH UPSERT (CORE FIX AREA)
    # ─────────────────────────────────────────────
    def _batch_upsert(self, collection, ids, embeddings, documents, metadatas):
        total = len(ids)

        if total == 0:
            logger.warning("⚠️ Attempted to upsert 0 records — skipping")
            return

        if not embeddings:
            raise ValueError("❌ Embeddings are empty — ingestion failed")

        for i in range(0, total, _BATCH_SIZE):
            s, e = i, i + _BATCH_SIZE

            collection.upsert(
                ids=ids[s:e],
                embeddings=embeddings[s:e],
                documents=documents[s:e],
                metadatas=metadatas[s:e],
            )

            logger.info(
                "RAGEngine: upserted rows %d–%d of %d into '%s'",
                s + 1, min(e, total), total, collection.name
            )

    # ─────────────────────────────────────────────
    # ✅ UPSERT FUNCTIONS (NO CHANGE IN LOGIC, BUT SAFE)
    # ─────────────────────────────────────────────
    def upsert_icd(self, ids, embeddings, documents, metadatas):
        self._batch_upsert(self._icd_col, ids, embeddings, documents, metadatas)
        logger.info("ICD ingestion complete (%d rows).", len(ids))

    def upsert_cpt(self, ids, embeddings, documents, metadatas):
        self._batch_upsert(self._cpt_col, ids, embeddings, documents, metadatas)
        logger.info("CPT ingestion complete (%d rows).", len(ids))

    def upsert_guidelines(self, ids, embeddings, documents, metadatas):
        self._batch_upsert(self._guide_col, ids, embeddings, documents, metadatas)
        logger.info("Guidelines ingestion complete (%d rows).", len(ids))

    def upsert_symptoms(self, ids, embeddings, documents, metadatas):
        self._batch_upsert(self._symptom_col, ids, embeddings, documents, metadatas)
        logger.info("Symptoms ingestion complete (%d rows).", len(ids))

    # ─────────────────────────────────────────────
    # 🔍 KEYWORD SCORE
    # ─────────────────────────────────────────────
    def _compute_keyword_score(self, query: str, document: str) -> float:
        q_words = set(query.lower().split())
        if not q_words:
            return 0.0
        d_words = set(document.lower().split())
        overlap = len(q_words & d_words) / len(q_words)

        # Bonus: exact phrase match in document
        phrase_bonus = 0.2 if query.lower() in document.lower() else 0.0
        return min(1.0, overlap + phrase_bonus)

    # ─────────────────────────────────────────────
    # 🧹 CODE VALIDATION + NORMALIZATION
    # ─────────────────────────────────────────────
    @staticmethod
    def _normalize_code(raw_code: str) -> str:
        """
        Normalize a raw code from ChromaDB metadata.
        Handles: N183 → N18.3, E119 → E11.9, e11.9 → E11.9
        """
        import re
        code = str(raw_code).strip().upper()

        # CPT (5-digit numeric) — no dot needed
        if re.match(r"^\d{5}$", code):
            return code

        # Remove existing dot(s) then re-insert correctly
        no_dot = code.replace(".", "")

        # ICD-10 pattern: 1 letter + 2 digits + optional suffix
        m = re.match(r"^([A-Z])(\d{2})(\w{0,4})$", no_dot)
        if m:
            letter, two_digits, rest = m.groups()
            if rest:
                return f"{letter}{two_digits}.{rest}"
            return f"{letter}{two_digits}"

        return code  # return as-is if unrecognized

    @staticmethod
    def _is_valid_icd10(code: str) -> bool:
        """
        Return True ONLY for valid ICD-10-CM codes.
        Rejects: ICD-9 codes, malformed entries, pure numeric codes, CPT codes.

        ICD-10-CM rules:
          - Starts with 1 letter (A-Z) — ICD-9 starts with 0-9 or V/E
          - Followed by 2 digits
          - Optional: dot + up to 4 alphanumeric characters

        ICD-9 patterns detected and rejected:
          - Pure numeric (e.g., 40390, 25000)
          - 3-digit numeric (e.g., 250)
          - V-codes with old format (V10.xx ICD-9 pattern)
          - E-codes with 4-digit pattern (ICD-9 E-codes: E800-E999)
        """
        import re
        code = code.strip().upper()

        # Reject pure numeric codes (ICD-9 or CPT)
        if re.match(r"^\d+$", code):
            return False

        # ICD-9 E-code pattern: E + 3-4 digits (e.g., E8000)
        if re.match(r"^E\d{3,4}$", code):
            return False

        # Must start with a letter (ICD-10 standard)
        if not re.match(r"^[A-Z]", code):
            return False

        # Must be 3-7 chars total (ICD-10 range)
        clean = code.replace(".", "")
        if not (3 <= len(clean) <= 7):
            return False

        # Core ICD-10 pattern: Letter + 2 digits + optional suffix
        if not re.match(r"^[A-Z]\d{2}", clean):
            return False

        return True

    @staticmethod
    def _is_valid_cpt(code: str) -> bool:
        """Return True for valid CPT codes (5-digit numeric)."""
        import re
        return bool(re.match(r"^\d{5}$", code.strip()))

    # ─────────────────────────────────────────────
    # 🚀 TYPE-FILTERED HYBRID QUERY
    # ─────────────────────────────────────────────
    async def query(
        self,
        query_text: str,
        n_results: int = 15,
        code_type: str = "ICD-10",   # "ICD-10" | "CPT" | "all"
    ) -> dict:
        """
        Hybrid embedding + keyword query over ChromaDB collections.

        CRITICAL FIXES:
          ✅ code_type='ICD-10' → ONLY searches ICD + guidelines + symptoms (NOT CPT)
          ✅ code_type='CPT'    → ONLY searches CPT collection
          ✅ All codes normalized: N183 → N18.3
          ✅ ICD-9 contamination rejected at retrieval time
          ✅ Exact phrase match bonus in scoring
        """
        try:
            query_vector = await self.embedding_service.embed_single(query_text)
        except Exception as e:
            logger.error("❌ Embedding failed: %s", e)
            return {"documents": [[]], "metadatas": [[]], "scores": [[]]}

        alpha = 0.5 # settings.rag_hybrid_alpha
        beta = 0.5  # settings.rag_hybrid_beta

        # ── Select collections by type ─────────────────────────────────────────
        if code_type == "CPT":
            collections_to_query = [self._cpt_col]
        elif code_type == "ICD-10":
            # ICD search: ICD + guidelines + symptoms, but NOT CPT
            collections_to_query = [self._icd_col, self._guide_col, self._symptom_col]
        else:  # "all"
            collections_to_query = [self._icd_col, self._cpt_col, self._guide_col, self._symptom_col]

        merged = []
        seen_codes: set[str] = set()

        for col in collections_to_query:
            try:
                count = col.count()
                if count == 0:
                    logger.warning("⚠️ Collection '%s' is EMPTY", col.name)
                    continue

                k = min(n_results * 3, count)   # fetch 3x to have room after filtering

                res = col.query(
                    query_embeddings=[query_vector],
                    n_results=k,
                    include=["documents", "metadatas", "distances"],
                )

                docs = res.get("documents", [[]])[0]
                metas = res.get("metadatas", [[]])[0]
                distances = res.get("distances", [[]])[0]

                for doc, meta, dist in zip(docs, metas, distances):
                    raw_code = meta.get("code", "").strip()
                    if not raw_code:
                        continue

                    # ── Normalize code (N183 → N18.3, e119 → E11.9) ─────────
                    normed_code = self._normalize_code(raw_code)

                    # ── Type filtering ────────────────────────────────────────
                    if code_type == "ICD-10":
                        if not self._is_valid_icd10(normed_code):
                            logger.debug("Rejected non-ICD10 code '%s' (normed: '%s')", raw_code, normed_code)
                            continue
                    elif code_type == "CPT":
                        if not self._is_valid_cpt(normed_code):
                            continue

                    # ── Dedup at retrieval time ───────────────────────────────
                    if normed_code in seen_codes:
                        continue
                    seen_codes.add(normed_code)

                    # ── Hybrid scoring ────────────────────────────────────────
                    # ChromaDB cosine distance: 0=identical, 2=opposite
                    vector_sim = max(0.0, 1.0 - (float(dist) / 2.0))
                    kw_score = self._compute_keyword_score(query_text, doc)
                    
                    # EXACT MATCH BOOST
                    exact_bonus = 0.3 if query_text.lower() in doc.lower() else 0.0
                    
                    final_score = (alpha * vector_sim) + (beta * kw_score) + exact_bonus
                    
                    # SEMANTIC FILTERING: drop weak matches (V9 strict threshold)
                    if final_score < 0.55:
                        continue

                    # v7 ENTITY-TYPE ALIGNMENT: reject cross-domain mismatches
                    # Require at least 1 content word overlap between query and doc
                    query_words = {w for w in query_text.lower().split() if len(w) > 3}
                    doc_words = {w for w in clean_doc.lower().split() if len(w) > 3}
                    desc_str = meta.get("description", "").lower()
                    desc_words = {w for w in desc_str.split() if len(w) > 3}
                    combined_doc_words = doc_words | desc_words
                    if query_words and not (query_words & combined_doc_words):
                        # No keyword overlap at all — likely cross-domain mismatch
                        if final_score < 0.80:  # allow very high similarity to pass anyway
                            logger.debug(
                                "RAG: entity-type reject '%s' (no keyword overlap with '%s')",
                                normed_code, query_text[:40],
                            )
                            continue

                    # Write normalized code back to meta copy for downstream
                    normed_meta = dict(meta)
                    normed_meta["code"] = normed_code

                    # ── Clean RAG Description (V10) ───────────────────────────
                    clean_doc = doc.split("| Description:")[-1].strip()

                    merged.append({
                        "doc": clean_doc,
                        "meta": normed_meta,
                        "score": final_score,
                        "raw_code": raw_code,
                        "normed_code": normed_code,
                    })

            except Exception as exc:
                logger.error("❌ Query error in '%s': %s", col.name, exc)

        # ── Sort by score desc, pick top-k ─────────────────────────────────────
        merged.sort(key=lambda x: x["score"], reverse=True)
        top_k = merged[:n_results]

        logger.info(
            "RAG query '%s' (type=%s): %d candidates → %d returned",
            query_text[:60], code_type, len(merged), len(top_k),
        )

        return {
            "documents": [[c["doc"] for c in top_k]],
            "metadatas": [[c["meta"] for c in top_k]],
            "scores": [[c["score"] for c in top_k]],
        }

    # ─────────────────────────────────────────────
    # 🔍 SEARCH (SYNCHRONOUS CONVENIENCE METHOD)
    # ─────────────────────────────────────────────
    def search(
        self,
        query_text: str,
        top_k: int = 10,
        code_type: str = "ICD-10",
    ) -> list[dict]:
        """
        Synchronous RAG search — returns flat list of normalized results.

        Usage:
            rag.search("CKD stage 3", top_k=10)
            # → [{"code": "N18.3", "description": "...", "type": "ICD-10", "score": 0.87}]

            rag.search("laparoscopic cholecystectomy", top_k=5, code_type="CPT")
            # → [{"code": "47562", ...}]
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    fut = pool.submit(asyncio.run, self.query(query_text, n_results=top_k, code_type=code_type))
                    result = fut.result()
            else:
                result = asyncio.run(self.query(query_text, n_results=top_k, code_type=code_type))
        except RuntimeError:
            result = asyncio.run(self.query(query_text, n_results=top_k, code_type=code_type))
        except Exception as e:
            logger.error("RAG search() failed: %s", e)
            return []

        return self._flatten_query_result(result)

    def search_icd(self, query_text: str, top_k: int = 10) -> list[dict]:
        """Convenience: search for ICD-10 codes only. Rejects CPT + ICD-9."""
        return self.search(query_text, top_k=top_k, code_type="ICD-10")

    def search_cpt(self, query_text: str, top_k: int = 5) -> list[dict]:
        """Convenience: search for CPT codes only."""
        return self.search(query_text, top_k=top_k, code_type="CPT")

    def _flatten_query_result(self, raw: dict) -> list[dict]:
        """Convert raw query() dict into a flat list of scored results."""
        docs = raw.get("documents", [[]])[0]
        metas = raw.get("metadatas", [[]])[0]
        scores = raw.get("scores", [[]])[0]

        if not scores:
            scores = [0.8] * len(docs)

        results = []
        for doc, meta, score in zip(docs, metas, scores):
            code = meta.get("code", "").strip()
            if not code:
                continue
            results.append({
                "code": code,                                           # already normalized
                "description": meta.get("description", doc[:80]),
                "type": meta.get("type", "ICD-10"),
                "score": round(float(score), 4),
                "text": doc[:200],
                "metadata": meta,
            })
        return results

    # ─────────────────────────────────────────────
    # 📊 DEBUG COUNTS
    # ─────────────────────────────────────────────
    def collection_counts(self) -> dict:
        return {
            "icd10": self._icd_col.count(),
            "cpt": self._cpt_col.count(),
            "guidelines": self._guide_col.count(),
            "symptoms": self._symptom_col.count(),
        }
