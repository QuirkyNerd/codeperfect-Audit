"""
agents/coding_logic.py – RAG-FIRST 3-Layer Coding Engine (v4 — CRITICAL FIX).

ARCHITECTURE (CORRECTED ORDER):
  Layer 1: EntityExtractor  → deterministic codes + entity-level RAG queries
  Layer 2: RAG Retrieval    → queried PER ENTITY (not full text), top_k=15
  Layer 3: LLM Reasoning    → ONLY selects/explains from final candidate pool

CRITICAL FIXES in v4:
  ✅ RAG queries per entity (not full note)
  ✅ ClinicalReaderAgent completely removed from the critical path
  ✅ LLM failure returns deterministic + RAG codes (NO collapse)
  ✅ Deterministic confidence always ≥ 0.95 (not diluted)
  ✅ top_k = 15 for RAG (was 5)
  ✅ Reranking step: pick highest-specificity code per entity
  ✅ Candidate pool = union(deterministic, RAG)
  ✅ LLM CANNOT drop deterministic codes
"""

import json
import os
import re

try:
    # When running from project root (development)
    from backend.config import settings
    from backend.services.rag_engine import RAGEngine
    from backend.services.entity_extractor import EntityExtractor
    from backend.services.rule_engine import RuleEngine
    from backend.services.selection_engine import SelectionEngine
    from backend.services.clinical_filter import ClinicalRelevanceFilter, ClinicalEntityFilter, EntityClassifier, ClinicalGroundingEngine
    from backend.utils.logging import get_logger
    from backend.utils.code_normalizer import normalize_code
    from backend.utils.gemini_client import generate_json_async
except ImportError:
    # When running from backend directory (Docker/production)
    from config import settings
    from services.rag_engine import RAGEngine
    from services.entity_extractor import EntityExtractor
    from services.rule_engine import RuleEngine
    from services.selection_engine import SelectionEngine
    from services.clinical_filter import ClinicalRelevanceFilter, ClinicalEntityFilter, EntityClassifier, ClinicalGroundingEngine
    from utils.logging import get_logger
    from utils.code_normalizer import normalize_code
    from utils.gemini_client import generate_json_async

logger = get_logger(__name__)

_PROMPT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "prompts", "coding_logic_prompt.txt"
)
_EXPLANATION_PROMPT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "prompts", "clinical_explanation_prompt.txt"
)

RAG_TOP_K = 15  # CRITICAL: must be 10-20 for medical


def _load_prompt(path: str, fallback: str = "") -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return fallback


def _build_result(success: bool, data=None, error: str | None = None, tokens: int = 0) -> dict:
    return {"success": success, "data": data, "error": error, "tokens_used": tokens}


class CodingLogicAgent:

    def __init__(self):
        self.model_name = settings.gemini_model
        self.rag = RAGEngine()
        self.entity_extractor = EntityExtractor()
        self.selection_engine = SelectionEngine()  # ← NEW: final decision layer
        self.system_prompt = _load_prompt(
            _PROMPT_PATH,
            "You are a CPC medical coder. Return JSON with 'codes' list.",
        )
        self._rag_cache: dict[str, list] = {}  # entity-level cache
        logger.info("CodingLogicAgent v5: RAG-first + SelectionEngine initialised.")

    # ─────────────────────────────────────────────────────────────────────────
    # Layer 1: Deterministic extraction (always succeeds)
    # ─────────────────────────────────────────────────────────────────────────
    def _layer1_deterministic(self, note_text: str) -> tuple[list[dict], list[dict], list[str]]:
        """
        Run EntityExtractor over raw note.
        Returns: (deterministic_codes, confirmed_entities, rag_queries)
        Confidence is always ≥ 0.95 — never diluted downstream.
        """
        result = self.entity_extractor.extract(note_text)
        det_codes = result.get("deterministic_codes", [])
        entities = result.get("confirmed_entities", [])
        rag_queries = result.get("rag_queries", [])

        logger.info(
            "Layer1 Deterministic: %d codes, %d confirmed entities, %d RAG queries",
            len(det_codes), len(entities), len(rag_queries),
        )
        return det_codes, entities, rag_queries

    # ─────────────────────────────────────────────────────────────────────────
    # Layer 2: RAG — queried PER ENTITY, top_k=15, with caching + reranking
    # ─────────────────────────────────────────────────────────────────────────
    async def _layer2_rag_entity_level(
        self,
        rag_queries: list[str],
        deterministic_codes: list[dict],
    ) -> tuple[list[dict], dict[str, float]]:
        """
        CRITICAL: RAG is queried for EACH entity independently.

        ✅ rag.query("type 2 diabetes mellitus with neuropathy", top_k=15)
        ✅ rag.query("chronic kidney disease stage 3", top_k=15)
        ✅ NOT rag.query(full_note)

        Returns: (rag_codes list, {code: rag_score} map)
        """
        det_code_strs = {c.get("code", "").upper() for c in deterministic_codes}
        rag_codes: list[dict] = []
        rag_scores: dict[str, float] = {}
        seen_codes: set[str] = set()

        # Also mark all deterministic codes as RAG-confirmed if we find them
        for c in deterministic_codes:
            rag_scores[c["code"].upper()] = 0.0  # will be updated if RAG confirms

        for query in rag_queries[:20]:  # max 20 entity queries per operation
            # Check entity-level cache
            cache_key = query.lower().strip()
            if cache_key in self._rag_cache:
                results_docs = self._rag_cache[cache_key]
            else:
                try:
                    # code_type='ICD-10' → never returns CPT or ICD-9 codes
                    raw = await self.rag.query(query, n_results=RAG_TOP_K, code_type="ICD-10")
                    docs = raw.get("documents", [[]])[0]
                    metas = raw.get("metadatas", [[]])[0]
                    # Use 'scores' (hybrid similarity from RAG engine, 0-1 range)
                    scores = raw.get("scores", [[]])[0]

                    # If scores unavailable, fallback to equal weight per result
                    if not scores:
                        scores = [0.8] * len(docs)

                    results_docs = list(zip(docs, metas, scores))
                    self._rag_cache[cache_key] = results_docs
                except Exception as e:
                    logger.warning("RAG query failed for '%s': %s", query, e)
                    results_docs = []

            for doc, meta, score in results_docs:
                code = meta.get("code", "").strip().upper()
                if not code:
                    continue

                rag_score = round(min(float(score), 1.0), 3)

                # Update rag_score for deterministic codes (confirms them)
                if code in det_code_strs:
                    existing = rag_scores.get(code, 0.0)
                    rag_scores[code] = max(existing, rag_score)
                    continue  # already in deterministic pool

                if code in seen_codes:
                    # Update score if better hit
                    for c in rag_codes:
                        if c["code"].upper() == code:
                            c["rag_score"] = max(c["rag_score"], rag_score)
                    continue

                seen_codes.add(code)

                rag_codes.append({
                    "code": code,
                    "description": meta.get("description", doc[:80]),
                    "type": meta.get("type", "ICD-10"),
                    "confidence": round(max(rag_score, 0.75), 3),  # RAG-supported ≥ 0.75
                    "source": "rag",
                    "entity": query,
                    "evidence_span": doc[:150],
                    "rationale": f"Retrieved from RAG for entity '{query}' with similarity {rag_score:.2f}",
                    "det_score": 0.0,
                    "rag_score": rag_score,
                    "llm_score": 0.0,
                })

        # Reranking: sort RAG codes by rag_score DESC, keep top 30
        rag_codes = sorted(rag_codes, key=lambda c: c["rag_score"], reverse=True)[:30]

        logger.info(
            "Layer2 RAG: %d entity queries → %d new RAG codes, %d det codes confirmed",
            len(rag_queries), len(rag_codes), sum(1 for v in rag_scores.values() if v > 0),
        )
        return rag_codes, rag_scores

    # ─────────────────────────────────────────────────────────────────────────
    # Layer 3 (NEW): LLM — EXPLANATION ONLY, NO CODE GENERATION, NO RETRIES
    # ─────────────────────────────────────────────────────────────────────────
    async def _layer3_llm_explanation(
        self,
        selected_codes: list[dict],
        note_text: str,
    ) -> tuple[list[dict], int]:
        """
        Single-shot LLM call for EXPLANATION ONLY.

        LLM CANNOT:
          - Add or remove codes
          - Change code values
          - Override SelectionEngine decisions

        LLM CAN:
          - Enrich rationale text
          - Add evidence_span from the note
          - Set llm_score

        No retries — if it fails, selected_codes are returned unchanged.
        """
        if not selected_codes:
            return selected_codes, 0

        # Build a compact code list for the prompt
        codes_summary = json.dumps(
            [
                {
                    "code": c["code"],
                    "description": c.get("description", ""),
                    "source": c.get("source", ""),
                }
                for c in selected_codes
            ],
            indent=2,
        )
        note_excerpt = note_text[:1500]

        prompt = (
            "You are a Certified Professional Coder (CPC). "
            "The ICD-10 codes below have ALREADY been selected by a deterministic selection engine. "
            "DO NOT add, remove, or change any code. "
            "Your ONLY task: for each code, write a brief clinical rationale (1-2 sentences) "
            "and identify the evidence_span (exact short phrase from the note).\n\n"
            f"SELECTED CODES:\n{codes_summary}\n\n"
            f"CLINICAL NOTE (excerpt):\n{note_excerpt}\n\n"
            "Return ONLY valid JSON — same codes array with 'rationale', 'evidence_span', and "
            "'llm_score' (0.0-1.0) added to each entry. No other changes.\n"
            '{"codes": [{"code": "E11.42", "rationale": "...", "evidence_span": "...", "llm_score": 0.95}]}'
        )

        try:
            raw = await generate_json_async(prompt)
            if not raw or not raw.strip():
                raise ValueError("Empty LLM response")

            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```[json]*\n?", "", cleaned)
                cleaned = re.sub(r"\n?```$", "", cleaned)

            parsed = json.loads(cleaned)
            llm_codes = parsed.get("codes", [])

            # Merge LLM explanations into selected codes by code key
            llm_by_code = {c.get("code", "").upper(): c for c in llm_codes}
            for sc in selected_codes:
                key = sc["code"].upper()
                if key in llm_by_code:
                    lcl = llm_by_code[key]
                    if lcl.get("rationale"):
                        sc["rationale"] = lcl["rationale"]
                    if lcl.get("evidence_span"):
                        sc["evidence_span"] = lcl["evidence_span"]
                    sc["llm_score"] = float(lcl.get("llm_score", 0.0))

            logger.info("Layer3 LLM explanation: enriched %d codes (single call)", len(selected_codes))
            return selected_codes, 0

        except Exception as e:
            # Non-fatal: explanation is optional. Return codes without enrichment.
            logger.warning("LLM explanation call failed (codes still returned): %s", e)
            return selected_codes, 0

    # ─────────────────────────────────────────────────────────────────────────
    # Public: generate_codes
    # ─────────────────────────────────────────────────────────────────────────
    async def generate_codes(self, clinical_facts: dict) -> dict:
        logger.info("CodingLogicAgent v5: starting RAG-first + SelectionEngine pipeline.")

        # Reconstruct note text for entity extraction
        note_text = clinical_facts.get("clinical_summary", "")
        evidence_sentences = clinical_facts.get("evidence_sentences", {})
        raw_note = clinical_facts.get("raw_note_text", note_text)
        if evidence_sentences:
            extra = " ".join(str(v) for v in evidence_sentences.values())
            note_text = f"{raw_note} {extra}".strip()
        else:
            note_text = raw_note or note_text

        # ── Layer 1: Deterministic ──────────────────────────────────────────
        det_codes, confirmed_entities, rag_queries = self._layer1_deterministic(note_text)

        # ── NEW v14: Entity Classification + Pre-RAG Clinical Filter ────────
        # Convert confirmed_entities to dicts for the filter
        entity_dicts = []
        for ent in confirmed_entities:
            if isinstance(ent, dict):
                entity_dicts.append(ent)
            else:
                entity_dicts.append({
                    "entity": getattr(ent, "entity", str(ent)),
                    "section": getattr(ent, "section", "default"),
                    "code": getattr(ent, "ontology_code", {}).get("code", "") if isinstance(getattr(ent, "ontology_code", None), dict) else "",
                    "rag_query": getattr(ent, "rag_query", ""),
                    "status": getattr(ent, "status", "confirmed"),
                })

        # Classify + prune BEFORE RAG queries
        filtered_entities, filtered_rag_queries, filtered_det_codes = (
            ClinicalEntityFilter.filter_entities(entity_dicts, rag_queries, det_codes)
        )

        logger.info(
            "v14 PreRAG Filter: %d→%d entities, %d→%d rag_queries, %d→%d det_codes",
            len(confirmed_entities), len(filtered_entities),
            len(rag_queries), len(filtered_rag_queries),
            len(det_codes), len(filtered_det_codes),
        )

        # ── Layer 2: RAG (entity-level, RAG-FIRST) — now with PRUNED queries
        rag_codes, rag_scores = await self._layer2_rag_entity_level(
            filtered_rag_queries, filtered_det_codes
        )

        # Stamp rag_scores onto det_codes + lock confidence >= 0.95
        for code_dict in filtered_det_codes:
            c_key = code_dict["code"].upper()
            code_dict["rag_score"] = rag_scores.get(c_key, 0.0)
            code_dict["confidence"] = max(code_dict.get("confidence", 0.95), 0.95)

        # Apply rule-engine hierarchy upgrades (e.g., DM+stage upgrade)
        facts_str = str(clinical_facts) + " " + note_text
        det_codes_upgraded = RuleEngine.apply_hierarchy_rules(facts_str, filtered_det_codes)

        # Build unified candidate pool (det union RAG, no duplicates)
        det_code_strs = {c.get("code", "").upper() for c in det_codes_upgraded}
        candidate_pool = list(det_codes_upgraded)
        for rc in rag_codes:
            if rc["code"].upper() not in det_code_strs:
                candidate_pool.append(rc)

        logger.info(
            "Candidate pool: %d det + %d RAG-only = %d total candidates",
            len(det_codes_upgraded), len(rag_codes), len(candidate_pool),
        )

        # ── v7 NEW: Clinical Grounding Layer (AFTER RAG, BEFORE SelectionEngine) ──
        # Build entity_classes dict from the filtered entities
        entity_classes_map: dict[str, str] = {}
        for ent in filtered_entities:
            if isinstance(ent, dict):
                ent_text = ent.get("entity", "")
            else:
                ent_text = str(ent)
            entity_class = EntityClassifier.classify(ent_text.lower())
            if entity_class:
                entity_classes_map[ent_text.lower()] = entity_class

        note_entity_strings = [
            ent.get("entity", str(ent)) if isinstance(ent, dict) else str(ent)
            for ent in filtered_entities
        ]

        grounded_pool = ClinicalGroundingEngine.ground_candidates(
            rag_candidates=candidate_pool,
            note_entities=note_entity_strings,
            entity_classes=entity_classes_map,
            note_text=note_text,
        )

        logger.info(
            "v7 Grounding: %d candidates → %d grounded (rejected %d ungrounded)",
            len(candidate_pool), len(grounded_pool), len(candidate_pool) - len(grounded_pool),
        )

        # ── SelectionEngine (clinically correct final codes) ────────────────
        selected_codes = self.selection_engine.select(
            candidates=grounded_pool,
            note_text=note_text,
            deterministic_codes=det_codes_upgraded,
        )

        logger.info(
            "SelectionEngine: %d candidates -> %d pre-filter codes",
            len(candidate_pool), len(selected_codes),
        )

        # ── v14 POST-SELECTION: ClinicalRelevanceFilter (final cap) ─────────
        selected_codes = ClinicalRelevanceFilter.filter_codes(selected_codes, note_text)

        logger.info("ClinicalFilter: final output has %d codes", len(selected_codes))

        # ── Layer 3: LLM explanation only (SINGLE call, no retries) ─────────
        explained_codes, tokens = await self._layer3_llm_explanation(
            selected_codes, note_text
        )

        # Identify low-confidence codes as those the selection engine dropped
        selected_strs = {c.get("code", "").upper() for c in explained_codes}
        low_conf = [
            c for c in candidate_pool
            if c.get("code", "").upper() not in selected_strs
            and float(c.get("confidence", 0)) < 0.70
        ][:5]  # cap low_conf list at 5

        logger.info(
            "CodingLogicAgent v5 complete: %d final codes, %d low-conf candidates",
            len(explained_codes), len(low_conf),
        )

        return _build_result(
            success=True,
            data={
                "codes": explained_codes,
                "low_confidence_codes": low_conf,
            },
            tokens=tokens,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public: process(note) — SINGLE-CALL API
    # ─────────────────────────────────────────────────────────────────────────
    async def process(self, note: str) -> dict:
        """
        MAIN PUBLIC API for testing and direct invocation.

        Usage:
            agent = CodingLogicAgent()
            result = await agent.process(note_text)

        Accepts raw clinical note text, runs the full 3-layer pipeline
        (deterministic → RAG → LLM), and returns structured output.
        """
        clinical_facts = {
            "raw_note_text": note,
            "clinical_summary": note[:1500],
            "evidence_sentences": {},
        }
        return await self.generate_codes(clinical_facts)

    # Aliases for discoverability
    async def analyze(self, note: str) -> dict:
        """Alias for process()."""
        return await self.process(note)

    async def run(self, note: str) -> dict:
        """Alias for process()."""
        return await self.process(note)

    def run_sync(self, note: str) -> dict:
        """
        SYNCHRONOUS wrapper for scripts and notebooks.

        Usage (no async needed):
            agent = CodingLogicAgent()
            result = agent.run_sync(note_text)
            codes = result["data"]["codes"]
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Running inside Jupyter or existing event loop — use thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(asyncio.run, self.process(note)).result()
            return asyncio.run(self.process(note))
        except RuntimeError:
            return asyncio.run(self.process(note))


    # ─────────────────────────────────────────────────────────────────────────
    # ICD HIERARCHY DEDUPLICATION (CRITICAL)
    # ─────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _deduplicate_hierarchy(codes: list[dict]) -> list[dict]:
        """
        Remove generic ICD codes when a more specific one exists.

        Rules:
        - Same code prefix (e.g., E11) → keep highest specificity
        - I50.9 removed if I50.21/I50.23 etc. present
        - E11.9 removed if E11.42/E11.40 etc. present
        - N18.9 removed if N18.3 etc. present
        - G62.9/G60.9 removed if E11.42 (diabetic neuropathy) present
        - Do NOT remove codes from different disease families
        """
        if not codes:
            return codes

        # ICD hierarchy: generic → specific (more digits after dot = more specific)
        # Priority: code with more decimal digits wins within same prefix
        GENERIC_TO_SPECIFIC = {
            # Heart failure hierarchy
            "I50.9": ["I50.21", "I50.23", "I50.20", "I50.31", "I50.33", "I50.30"],
            # Diabetes hierarchy
            "E11.9": ["E11.40", "E11.42", "E11.22", "E11.319", "E11.621", "E11.65"],
            "E10.9": ["E10.40", "E10.42"],
            # CKD hierarchy
            "N18.9": ["N18.1", "N18.2", "N18.3", "N18.31", "N18.32", "N18.4", "N18.5", "N18.6"],
        }

        # These standalone neuropathy codes should be removed if diabetic neuropathy code exists
        SUPERSEDED_BY = {
            "G62.9": ["E11.42", "E11.40", "E10.42", "E10.40"],
            "G60.9": ["E11.42", "E11.40", "E10.42", "E10.40"],
        }

        code_strs = {c.get("code", "").upper() for c in codes}

        codes_to_remove: set[str] = set()

        # Rule 1: Remove generic when specific exists
        for generic, specifics in GENERIC_TO_SPECIFIC.items():
            if generic.upper() in code_strs:
                for specific in specifics:
                    if specific.upper() in code_strs:
                        codes_to_remove.add(generic.upper())
                        break

        # Rule 2: Remove standalone neuropathy if diabetic neuropathy exists
        for superseded, supersedes_list in SUPERSEDED_BY.items():
            if superseded.upper() in code_strs:
                for supersedes in supersedes_list:
                    if supersedes.upper() in code_strs:
                        codes_to_remove.add(superseded.upper())
                        break

        # Rule 3: Within same 3-char prefix, keep most specific
        prefix_codes: dict[str, list[dict]] = {}
        for c in codes:
            code = c.get("code", "").upper()
            if not code or c.get("type", "").upper() == "CPT":
                continue  # Don't compare CPT codes this way
            prefix = code.split(".")[0] if "." in code else code[:3]
            prefix_codes.setdefault(prefix, []).append(c)

        for prefix, group in prefix_codes.items():
            if len(group) > 1:
                # Sort by specificity: longer code string = more specific
                group.sort(key=lambda x: len(x.get("code", "")), reverse=True)
                # Keep the most specific (first after sort), mark rest for removal
                for g in group[1:]:
                    code = g.get("code", "").upper()
                    # Only remove if it's truly a generic version (same prefix)
                    most_specific = group[0].get("code", "").upper()
                    if code != most_specific and len(code) < len(most_specific):
                        codes_to_remove.add(code)

        if codes_to_remove:
            logger.info("Deduplication: removing generic codes: %s", codes_to_remove)

        return [c for c in codes if c.get("code", "").upper() not in codes_to_remove]