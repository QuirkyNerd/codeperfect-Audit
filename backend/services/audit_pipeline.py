"""
services/audit_pipeline.py – RAG-First 5-Stage Pipeline with Clinical Rule Engine (v5).

PIPELINE ORDER:
  Step 0: EntityExtractor        – ontology + section-aware entity extraction
  Step 1: CodingLogicAgent       – RAG + Deterministic + SelectionEngine
  Step 1b: RuleEngine            – clinical rules, CPT validation, final dedup
  Step 2: AuditorAgent           – compare AI vs human codes, classify discrepancies
  Step 3: ExplanationAgent       – Gemini clinical audit explanation (structured)
  Step 4: EvidenceHighlighter    – link each code to text spans

DESIGN:
  - All pipeline stages have fallback — system never collapses on a single failure
  - Deterministic codes are always in output even if every LLM call fails
  - Rule engine stages mutate the same ai_codes reference passed to AuditorAgent
  - Gemini is used ONLY for explanation (not code generation)
  - No emojis in any log or label output
"""

import json
import time
from typing import Any, AsyncGenerator

try:
    from backend.agents.coding_logic import CodingLogicAgent
    from backend.agents.auditor import AuditorAgent
    from backend.agents.evidence_agent import EvidenceHighlighterAgent
    from backend.services.entity_extractor import EntityExtractor
    from backend.services.rule_engine import RuleEngine
    from backend.utils.phi_masker import PHIMasker
    from backend.utils.logging import get_logger
    from backend.utils.gemini_client import generate_json_async
except ImportError:
    from agents.coding_logic import CodingLogicAgent
    from agents.auditor import AuditorAgent
    from agents.evidence_agent import EvidenceHighlighterAgent
    from services.entity_extractor import EntityExtractor
    from services.rule_engine import RuleEngine
    from utils.phi_masker import PHIMasker
    from utils.logging import get_logger
    from utils.gemini_client import generate_json_async

logger = get_logger(__name__)


def _load_explanation_prompt() -> str:
    import os
    paths = [
        os.path.join(os.path.dirname(__file__), "..", "prompts", "clinical_explanation_prompt.txt"),
        "prompts/clinical_explanation_prompt.txt",
    ]
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            continue
    return "Write a professional clinical coding audit summary with at least 5 structured points."


_EXPLANATION_PROMPT = _load_explanation_prompt()


class PipelineStep:
    def __init__(self, name: str, label: str = ""):
        self.name = name
        self.label = label or name
        self.status: str = "pending"
        self.duration_ms: float = 0.0
        self.error: str | None = None

    def to_dict(self) -> dict:
        return {
            "step": self.name,
            "label": self.label,
            "status": self.status,
            "duration_ms": round(self.duration_ms, 1),
            "error": self.error,
        }


def _build_structured_explanation_context(
    note_text: str,
    ai_codes: list[dict],
    discrepancies: list[dict],
) -> str:
    """
    Build a structured, human-readable context block for the Gemini explanation prompt.
    Includes: note summary, final code set, discrepancies, rule engine adjustments.
    """
    # Note summary — first 500 chars gives sufficient clinical context
    note_summary = note_text[:500].strip()

    # Format validated codes
    code_lines = []
    for c in ai_codes[:12]:
        code   = c.get("code", "")
        desc   = c.get("description", "")
        src    = c.get("source", "")
        conf   = int(c.get("confidence", 0) * 100)
        rationale = c.get("rationale", "")
        # Strip internal rule annotations from rationale before sending to Gemini
        rationale_clean = rationale.replace("[RULE:", "(Rule:").strip()
        line = f"  {code}  {desc}  [confidence {conf}%, source: {src}]"
        if rationale_clean:
            line += f"\n    Basis: {rationale_clean[:120]}"
        code_lines.append(line)
    codes_block = "\n".join(code_lines) if code_lines else "  (none)"

    # Format discrepancies
    disc_lines = []
    for d in discrepancies[:10]:
        dtype = d.get("type", "")
        code  = d.get("code", "")
        msg   = d.get("message", "")
        sev   = d.get("severity", "")
        disc_lines.append(f"  [{dtype.upper()} | {sev.upper()}] {code}: {msg}")
    disc_block = "\n".join(disc_lines) if disc_lines else "  (none)"

    # Identify rule-engine adjustments from rationale annotations
    rule_adjustments = []
    for c in ai_codes:
        rationale = c.get("rationale", "")
        if "(Rule:" in rationale or "RULE:" in rationale:
            rule_adjustments.append(f"  {c.get('code', '')}: {c.get('description', '')}")
    adjustments_block = "\n".join(rule_adjustments) if rule_adjustments else "  (none)"

    return f"""CLINICAL NOTE SUMMARY:
{note_summary}

VALIDATED CODE SET:
{codes_block}

CODING DISCREPANCIES (vs human coder):
{disc_block}

RULE ENGINE ADJUSTMENTS APPLIED:
{adjustments_block}"""


async def _generate_explanation(
    note_text: str,
    ai_codes: list[dict],
    discrepancies: list[dict],
) -> str:
    """
    Generate a structured clinical audit explanation via Gemini.
    Enforces 5-minimum structured sections with CDI-specialist tone.
    Returns plain text; never returns AI-style generic phrases.
    """
    try:
        context_block = _build_structured_explanation_context(note_text, ai_codes, discrepancies)

        prompt = f"""{_EXPLANATION_PROMPT}

{context_block}

Return ONLY valid JSON: {{"explanation": "..."}}"""

        import asyncio
        raw = await asyncio.wait_for(
            generate_json_async(prompt),
            timeout=15.0,
        )
        if not raw or not raw.strip():
            raise ValueError("Empty response from Gemini")

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            import re
            cleaned = re.sub(r"^```[json]*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned)

        parsed = json.loads(cleaned)
        explanation = parsed.get("explanation", "")

        # ── Sections 1 & 5: Structural & Consistency Validation ──
        headers = ["FINAL CODE SET", "CODING ADJUSTMENTS", "CLINICAL JUSTIFICATION", "SUMMARY OF FINDINGS"]
        has_headers = all(h in explanation for h in headers)
        
        lower_exp = explanation.lower()
        has_ai_phrases = any(p in lower_exp for p in [
            "as an ai", "i am an ai", "the system identified", "the ai found", "ai identified"
        ])
        
        if not has_headers:
            logger.warning("Gemini explanation missing required structural headers. Using fallback.")
            return _build_deterministic_explanation(ai_codes, discrepancies)
            
        if has_ai_phrases:
            logger.warning("Gemini explanation contained generic AI phrases. Using fallback.")
            return _build_deterministic_explanation(ai_codes, discrepancies)

        # Quality gate: reject explanations shorter than 200 chars or under 3 newlines
        if len(explanation) < 200 or explanation.count("\n") < 2:
            logger.warning("Gemini explanation too short or unstructured — using deterministic fallback.")
            return _build_deterministic_explanation(ai_codes, discrepancies)

        return explanation

    except Exception as exc:
        logger.warning("ExplanationAgent failed: %s. Using deterministic fallback.", exc)
        return _build_deterministic_explanation(ai_codes, discrepancies)


def _build_deterministic_explanation(
    ai_codes: list[dict],
    discrepancies: list[dict],
) -> str:
    """
    Deterministic fallback explanation when Gemini is unavailable.
    Structured in 4 sections to match audit report format.
    Never generic — always references specific codes and findings.
    """
    icd_codes = [c for c in ai_codes if c.get("type", "ICD-10") != "CPT"]
    cpt_codes = [c for c in ai_codes if c.get("type", "") == "CPT"]
    missed    = [d for d in discrepancies if d.get("type") == "missed_code"]
    unsupported = [d for d in discrepancies if d.get("type") == "unsupported_code"]

    lines = []

    # Section 1 — Final Code Set
    if icd_codes:
        code_str = "; ".join(
            f"{c.get('code')} ({c.get('description', '')})"
            for c in icd_codes[:6]
        )
        lines.append(f"FINAL CODE SET\nThe following diagnosis codes were validated: {code_str}.")

    if cpt_codes:
        cpt_str = "; ".join(f"{c.get('code')} ({c.get('description', '')})" for c in cpt_codes[:4])
        lines.append(f"Procedure codes assigned: {cpt_str}.")

    # Section 2 — Coding Adjustments
    rule_adjusted = [c for c in ai_codes if "(Rule:" in (c.get("rationale") or "")]
    if rule_adjusted:
        adj_str = "; ".join(
            f"{c.get('code')} — {c.get('description', '')}"
            for c in rule_adjusted[:4]
        )
        lines.append(f"CODING ADJUSTMENTS\nThe following codes were upgraded or corrected per clinical guidelines: {adj_str}.")

    # Section 3 — Clinical Justification
    if missed:
        miss_str = "; ".join(f"{d.get('code')} ({d.get('message', '')})" for d in missed[:3])
        lines.append(f"CLINICAL JUSTIFICATION\nCodes identified as missed by the human coder: {miss_str}. These represent potential undercoding risk.")
    if unsupported:
        unsup_str = "; ".join(f"{d.get('code')}" for d in unsupported[:3])
        lines.append(f"Codes submitted by the human coder without sufficient clinical documentation: {unsup_str}.")

    # Section 4 — Summary
    lines.append(
        f"SUMMARY\nAudit complete. {len(ai_codes)} code(s) validated. "
        f"{len(missed)} missed and {len(unsupported)} unsupported code(s) identified. "
        "Review discrepancy table for case-level details."
    )

    return "\n\n".join(lines)


class AuditPipeline:

    def __init__(self):
        self.entity_extractor     = EntityExtractor()
        self.coding_logic         = CodingLogicAgent()
        self.auditor              = AuditorAgent()
        self.evidence_highlighter = EvidenceHighlighterAgent()

    async def run_stream(
        self,
        note_text: str,
        human_codes: list[str],
    ) -> AsyncGenerator[dict[str, Any], None]:

        t_total = time.time()
        tokens_total = 0
        pipeline_log: list[dict] = []

        masked_note = PHIMasker.mask(note_text)
        yield {"event": "info", "data": "PHI masking complete. Launching clinical audit pipeline."}

        ai_codes: list[dict] = []
        discrepancies: list[dict] = []
        evidence: list[dict] = []
        summary: str = ""
        deterministic_codes: list[dict] = []
        explanation: str = ""

        # ── Step 0: Entity Extraction ─────────────────────────────────
        step0 = PipelineStep("EntityExtractorAgent", "Extracting Clinical Entities")
        yield {"event": "step_start", "data": step0.to_dict()}
        t0 = time.time()
        try:
            extraction_result = self.entity_extractor.extract(masked_note)
            deterministic_codes = extraction_result.get("deterministic_codes", [])
            rag_queries = extraction_result.get("rag_queries", [])
            step0.duration_ms = (time.time() - t0) * 1000
            step0.status = "success"
            logger.info(
                "Step0: %d deterministic codes, %d RAG queries generated",
                len(deterministic_codes), len(rag_queries),
            )
        except Exception as exc:
            step0.duration_ms = (time.time() - t0) * 1000
            step0.status = "failed"
            step0.error = str(exc)
            deterministic_codes = []
            rag_queries = []
            logger.error("EntityExtractor failed: %s", exc)
        pipeline_log.append(step0.to_dict())
        yield {"event": "step_end", "data": step0.to_dict()}

        # ── Step 1: RAG + Deterministic Code Mapping ──────────────────
        step1 = PipelineStep("CodingLogicAgent", "RAG + Deterministic Code Mapping")
        yield {"event": "step_start", "data": step1.to_dict()}
        t0 = time.time()

        clinical_facts_minimal = {
            "raw_note_text": masked_note,
            "clinical_summary": masked_note[:1500],
            "evidence_sentences": {},
            "diagnoses": [
                {"entity": c.get("entity", ""), "evidence_sentence": c.get("evidence_span", "")}
                for c in deterministic_codes
            ],
            "procedures": [
                {"entity": c.get("entity", ""), "evidence_sentence": c.get("evidence_span", "")}
                for c in deterministic_codes if c.get("type") == "CPT"
            ],
        }

        result1 = {"success": False, "data": None, "tokens_used": 0}
        try:
            result1 = await self.coding_logic.generate_codes(clinical_facts_minimal)
            step1.duration_ms = (time.time() - t0) * 1000

            if result1["success"] and result1["data"]:
                raw_codes = result1["data"].get("codes", [])
                # Inject deterministic codes (they always win)
                ai_codes = RuleEngine.inject_deterministic_codes(raw_codes, deterministic_codes)
                # Apply ICD hierarchy upgrade rules (pre-existing)
                ai_codes = RuleEngine.apply_hierarchy_rules(masked_note, ai_codes)
                step1.status = "success"
            else:
                ai_codes = deterministic_codes
                step1.status = "partial"
                step1.error = result1.get("error", "CodingLogic returned no data")
                logger.warning("CodingLogicAgent returned no data — using deterministic codes only.")
        except Exception as exc:
            step1.duration_ms = (time.time() - t0) * 1000
            step1.status = "failed"
            step1.error = str(exc)
            ai_codes = deterministic_codes
            logger.error("CodingLogicAgent exception: %s — falling back to deterministic codes.", exc)

        tokens_total += result1.get("tokens_used", 0)
        pipeline_log.append(step1.to_dict())
        yield {"event": "step_end", "data": step1.to_dict()}

        # ── Step 1b: Rule Engine (Clinical Rules + CPT + Final Validation) ──
        step1b = PipelineStep("RuleEngine", "Applying Clinical Coding Rules")
        yield {"event": "step_start", "data": step1b.to_dict()}
        t0 = time.time()
        try:
            # CRITICAL: reassign ai_codes so downstream stages see corrected codes
            ai_codes = RuleEngine.apply_clinical_rules(ai_codes, masked_note)
            ai_codes = RuleEngine.apply_cpt_rules(ai_codes, masked_note)
            ai_codes = RuleEngine.apply_final_validation(ai_codes)
            step1b.duration_ms = (time.time() - t0) * 1000
            step1b.status = "success"
            logger.info("RuleEngine complete: %d validated codes", len(ai_codes))
        except Exception as exc:
            step1b.duration_ms = (time.time() - t0) * 1000
            step1b.status = "failed"
            step1b.error = str(exc)
            logger.error("RuleEngine failed: %s — codes passed through unmodified.", exc)
        pipeline_log.append(step1b.to_dict())
        yield {"event": "step_end", "data": step1b.to_dict()}

        # ── Step 2: Auditor (compare AI vs human codes) ───────────────
        step2 = PipelineStep("AuditorAgent", "Auditing Human vs Validated Codes")
        yield {"event": "step_start", "data": step2.to_dict()}
        t0 = time.time()
        try:
            # ai_codes is now the rule-engine-validated set
            result2 = await self.auditor.compare_codes(human_codes, ai_codes, masked_note)
            step2.duration_ms = (time.time() - t0) * 1000
            if result2.get("success") and result2.get("data"):
                discrepancies = result2["data"].get("discrepancies", [])
                summary = result2["data"].get("summary", "")
                step2.status = "success"
            else:
                step2.status = "partial"
                step2.error = result2.get("error")
            tokens_total += result2.get("tokens_used", 0)
        except Exception as exc:
            step2.duration_ms = (time.time() - t0) * 1000
            step2.status = "failed"
            step2.error = str(exc)
            logger.error("AuditorAgent failed: %s", exc)
        pipeline_log.append(step2.to_dict())
        yield {"event": "step_end", "data": step2.to_dict()}

        # ── Step 3: Clinical Explanation (Gemini — structured output) ─
        step3 = PipelineStep("ExplanationAgent", "Generating Clinical Audit Explanation")
        yield {"event": "step_start", "data": step3.to_dict()}
        t0 = time.time()
        try:
            explanation = await _generate_explanation(masked_note, ai_codes, discrepancies)
            step3.duration_ms = (time.time() - t0) * 1000
            step3.status = "success"
        except Exception as exc:
            step3.duration_ms = (time.time() - t0) * 1000
            step3.status = "failed"
            step3.error = str(exc)
            explanation = _build_deterministic_explanation(ai_codes, discrepancies)
            logger.warning("ExplanationAgent failed: %s — using deterministic explanation.", exc)
        pipeline_log.append(step3.to_dict())
        yield {"event": "step_end", "data": step3.to_dict()}

        # ── Step 4: Evidence Highlighter ──────────────────────────────
        step4 = PipelineStep("EvidenceHighlighterAgent", "Linking Evidence Spans")
        yield {"event": "step_start", "data": step4.to_dict()}
        t0 = time.time()
        try:
            result4 = self.evidence_highlighter.highlight_evidence(
                masked_note, ai_codes, clinical_facts_minimal,
            )
            step4.duration_ms = (time.time() - t0) * 1000
            if result4.get("success"):
                evidence = result4.get("data", [])
                step4.status = "success"
            else:
                step4.status = "partial"
                step4.error = result4.get("error")
        except Exception as exc:
            step4.duration_ms = (time.time() - t0) * 1000
            step4.status = "failed"
            step4.error = str(exc)
            logger.warning("EvidenceHighlighter failed: %s", exc)
        pipeline_log.append(step4.to_dict())
        yield {"event": "step_end", "data": step4.to_dict()}

        # ── Section 3: Evidence Consistency Check ─────────────────────
        # If no valid evidence found for a code, downgrade confidence
        if step4.status == "success" and evidence:
            evidenced_codes = {ev.get("code", "").upper() for ev in evidence}
            for c in ai_codes:
                code_str = c.get("code", "").upper()
                if code_str not in evidenced_codes:
                    old_conf = c.get("confidence", 0)
                    new_conf = max(0.0, old_conf - 0.20)
                    c["confidence"] = new_conf
                    c["rationale"] = (c.get("rationale") or "") + " [WARNING: Weak support — no explicit evidence span found]"
                    logger.info("AuditPipeline[evidence_check]: downgraded %s confidence %.2f -> %.2f", code_str, old_conf, new_conf)

        # ── Section 6: Final Sanity Check ─────────────────────────────
        # Final safety filter to guarantee no duplicates or conflicting pairs leak through
        ai_codes = RuleEngine.apply_final_validation(ai_codes)
        
        if not explanation:
            explanation = _build_deterministic_explanation(ai_codes, discrepancies)

        total_ms = (time.time() - t_total) * 1000
        logger.info(
            "AuditPipeline v5 complete: %d codes, %d discrepancies, %.1fms",
            len(ai_codes), len(discrepancies), total_ms,
        )

        yield {
            "event": "complete",
            "data": {
                "ai_codes": ai_codes,
                "low_confidence_codes": [],
                "discrepancies": discrepancies,
                "evidence": evidence,
                "summary": summary,
                "explanation": explanation,
                "pipeline_log": pipeline_log,
                "tokens_used": tokens_total,
                "deterministic_codes_count": len(deterministic_codes),
            },
        }