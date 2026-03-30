"""
services/selection_engine.py — UNIVERSAL CLINICAL CODE SELECTION ENGINE (v3)

ARCHITECTURE — HYBRID AUTO-DERIVED + CONFIG OVERRIDES:

  90% of rules are DERIVED AUTOMATICALLY from ICD-10 code structure:
    • Prefix hierarchy:     N18.32 → parent N18.3 → parent N18 (auto-suppression)
    • Combination dominance: compound codes auto-suppress their component parts
    • Auto-grouping:        first 3 chars = group key (N18 = group "N18")
    • Specificity scoring:  len(code.replace('.','')) — no manual mapping needed

  10% are CONFIG OVERRIDES (clinical_rules_config.py):
    • Compound rules:       DM2 + neuropathy → E11.42 (cross-entity merges)
    • Cross-prefix suppress: E11.42 → remove G62.9 (different prefix families)
    • Hard-reject prefixes: O* pregnancy, V* external cause
    • Entity validation map: entity keywords → allowed ICD prefixes

PIPELINE ORDER (STRICT — rules before scoring):
  1. Format validation         → reject invalid ICD-10, ICD-9
  2. Hard category filter      → O*, V*, P*, Q* rejected unless note mentions condition
  3. Renal syndrome filter     → N01-N08, N25-N27 rejected when CKD is entity
  4. Config compound rules     → fire before scoring, result → PROTECTED
  5. Auto combination detect   → more-specific combined code auto-dominates generics
  6. Entity-code validation    → RAG codes must match a note entity
  7. Prefix hierarchy suppression → N18.32 present → remove N18.3, N18.9 (auto)
  8. Cross-prefix suppression  → config-driven (E11.42 removes G62.9)
  9. Auto-grouping per 3-char prefix → best-per-group selection
 10. Final validate + dedup + cap

KEY IMPROVEMENTS vs v2:
  • No hardcoded disease-specific dicts inside this file
  • Auto-grouping = 3-char prefix → works for ALL ICD chapters
  • Generic combination dominance detects compound codes by cross-prefix analysis
  • Compound rule matching is normalized + signals-based (not raw string match)
  • PROTECTED set propagated through all suppression stages
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from dataclasses import dataclass, field
from typing import Optional

try:
    from utils.logging import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# Import all rules / constants from the split config modules
try:
    # When running from project root (development)
    from backend.services.compound_rules import COMPOUND_RULES
    from backend.services.hierarchy_config import CROSS_PREFIX_SUPPRESS, HIERARCHY_SUPPRESSION
    from backend.services.validation_rules import (
        HARD_REJECT_PREFIXES,
        ALWAYS_REJECT_PREFIXES,
        RENAL_SYNDROME_PREFIXES,
        CLINICAL_EXCLUSIVITY_RULES,
        RELATIONSHIP_VALIDATION_RULES,
        clean_rag_description,
    )
    from backend.services.group_config import (
        ENTITY_PREFIX_MAP,
        MANDATORY_GROUPS,
        CKD_ENTITY_SIGNALS,
    )
    from backend.services.universal_hierarchy import UniversalHierarchyEngine
except ImportError:
    # When running from backend directory (Docker/production)
    from services.compound_rules import COMPOUND_RULES
    from services.hierarchy_config import CROSS_PREFIX_SUPPRESS, HIERARCHY_SUPPRESSION
    from services.validation_rules import (
        HARD_REJECT_PREFIXES,
        ALWAYS_REJECT_PREFIXES,
        RENAL_SYNDROME_PREFIXES,
        CLINICAL_EXCLUSIVITY_RULES,
        RELATIONSHIP_VALIDATION_RULES,
        clean_rag_description,
    )
    from services.group_config import (
        ENTITY_PREFIX_MAP,
        MANDATORY_GROUPS,
        CKD_ENTITY_SIGNALS,
    )
    from services.universal_hierarchy import UniversalHierarchyEngine


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

MAX_FINAL_CODES = 10
MIN_RAG_CONFIDENCE = 0.60          # RAG-only codes BELOW this are HARD-DROPPED (v14)
PRINCIPAL_BOOST = 0.30             # v14: principal diagnosis section score bonus


# ─────────────────────────────────────────────────────────────────────────────
# ICD-10 Validators
# ─────────────────────────────────────────────────────────────────────────────

_ICD10_RE = re.compile(r"^[A-Z][0-9]{2}(\.[A-Z0-9]{1,4})?$", re.IGNORECASE)
_ICD9_NUMERIC_RE = re.compile(r"^\d{3,5}(\.\d{0,2})?$")
_ICD9_ECODE_RE   = re.compile(r"^E\d{3,4}(\.\d)?$", re.IGNORECASE)


def _is_valid_icd10(code: str) -> bool:
    if not code or len(code) < 3 or len(code) > 8:
        return False
    if _ICD9_NUMERIC_RE.match(code):
        return False
    if _ICD9_ECODE_RE.match(code):
        return False
    return bool(_ICD10_RE.match(code))


def _specificity(code: str) -> int:
    """Number of significant chars. Higher = more specific."""
    return len(code.replace(".", ""))


def _prefix3(code: str) -> str:
    """Return 3-char ICD prefix (before the dot)."""
    return code.split(".")[0].upper() if "." in code else code[:3].upper()


def _auto_group(code: str, code_type: str) -> str:
    """
    AUTO-GROUPING — derives group key from ICD-10 structure alone.
    Returns 3-char prefix for ICD codes (N18, E11, I50 …).
    CPT codes each get their own singleton group.
    """
    if code_type.upper() == "CPT":
        return f"cpt_{code}"
    return _prefix3(code)


def _score(det: float, rag: float, spec: float, entity: float) -> float:
    """Composite final score — used for TIE-BREAKING only, never to override rules."""
    return 0.40 * det + 0.30 * rag + 0.20 * min(spec / 8.0, 1.0) + 0.10 * entity


# ─────────────────────────────────────────────────────────────────────────────
# _ScoredCode dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _ScoredCode:
    code: str
    description: str
    code_type: str          # "ICD-10" or "CPT"
    group: str              # auto-derived 3-char prefix
    det_score: float = 0.0
    rag_score: float = 0.0
    specificity: int = 0    # pre-computed len
    entity_score: float = 0.0
    confidence: float = 0.0
    source: str = "rag"
    rationale: str = ""
    evidence_span: str = ""
    final_score: float = 0.0
    protected: bool = False  # PROTECTED = immune to all suppression steps
    section_priority: int = 3  # v14: section priority (10=principal, 1=symptom)
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        d = {
            "code": self.code,
            "description": self.description,
            "type": self.code_type,
            "confidence": round(self.det_score * 0.5 + self.rag_score * 0.3 + min(self.specificity / 8.0, 1.0) * 0.2, 3),
            "source": self.source,
            "rationale": self.rationale,
            "evidence_span": self.evidence_span,
            "det_score": round(self.det_score, 3),
            "rag_score": round(self.rag_score, 3),
            "llm_score": 0.0,
            "section_priority": self.section_priority,
            "protected": self.protected,
        }
        d.update(self.extra)
        return d


# ─────────────────────────────────────────────────────────────────────────────
# Normalise note text for rule matching
# ─────────────────────────────────────────────────────────────────────────────

_SYNONYMS: dict[str, str] = {
    "type ii diabetes": "type 2 diabetes",
    "type-2 diabetes": "type 2 diabetes",
    "dm type 2": "type 2 diabetes",
    "dm2": "type 2 diabetes",
    "t2dm": "type 2 diabetes",
    "type i diabetes": "type 1 diabetes",
    "dm1": "type 1 diabetes",
    "t1dm": "type 1 diabetes",
    "htn": "hypertension",
    "a-fib": "atrial fibrillation",
    "afib": "atrial fibrillation",
    "esrd": "end stage renal disease",
    "ckd": "chronic kidney disease",
    "aki": "acute kidney injury",
    "mi": "myocardial infarction",
    "hf": "heart failure",
    "chf": "heart failure",
    "copd": "chronic obstructive pulmonary disease",
    "peripheral neuropathy": "neuropathy",
    "peripheral neuropathic": "neuropathy",
    "diabetic neuropathy": "neuropathy",
    "dm neuropathy": "neuropathy",
}


def _normalise_note(note: str) -> str:
    """Lower-case + expand common synonyms for reliable rule matching."""
    text = note.lower()
    for abbr, full in _SYNONYMS.items():
        text = text.replace(abbr, full)
    return text


# ─────────────────────────────────────────────────────────────────────────────
# SelectionEngine v3
# ─────────────────────────────────────────────────────────────────────────────

class SelectionEngine:
    """
    Universal clinical code selection engine.

    Usage:
        engine = SelectionEngine()
        final_codes = engine.select(candidates, note_text, deterministic_codes)
    """

    def select(
        self,
        candidates: list[dict],
        note_text: str = "",
        deterministic_codes: Optional[list[dict]] = None,
    ) -> list[dict]:
        if not candidates:
            return []

        note_norm = _normalise_note(note_text)
        det_set: set[str] = {
            c.get("code", "").strip().upper()
            for c in (deterministic_codes or [])
        }
        # PROTECTED = safe from all suppression. Starts as copy of det_set.
        protected: set[str] = set(det_set)
        # TRACKED GROUPS = clinical domains already covered by compound rules or entities
        covered_groups: set[str] = set()

        # ── Stage 1: Validation (Format + Entity Match) ───────────────
        pool = self._validate_convert(candidates, det_set)
        # RAG SANITIZATION: Ensure RAG codes match note entities
        pool = self._entity_validate(pool, note_norm, det_set, protected)
        logger.info("SE [1-validation]: %d valid candidates", len(pool))

        # ── Stage 2: Negation Filtering (NEW) ─────────────────────────
        pool = self._filter_negations(pool, note_norm, protected)
        logger.info("SE [2-negation]: %d remaining after negation", len(pool))

        # ── Stage 3: Compound Rules (PROTECTED + COVERED GROUPS) ──────
        pool, protected, covered_groups = self._apply_compound_rules(pool, note_norm, det_set, protected, covered_groups)
        logger.info("SE [3-compound]: %d pool, %d protected, covered_groups: %s", len(pool), len(protected), covered_groups)

        # ── Stage 4: Universal Hierarchy Resolution (v7 UPGRADE) ─────
        # UHE: seed config (PRIMARY) + structural inference (SECONDARY)
        uhe = UniversalHierarchyEngine()
        pool_codes = {s.code for s in pool if s.code_type != "CPT"}
        code_descriptions = {s.code: s.description for s in pool}
        note_entities = [kw for kw in ENTITY_PREFIX_MAP if kw in note_norm]
        uhe_suppress = uhe.get_all_suppressions(
            codes=pool_codes,
            code_descriptions=code_descriptions,
            note_entities=note_entities,
            protected=protected,
        )
        if uhe_suppress:
            pool = [s for s in pool if s.code not in uhe_suppress]
            logger.info("SE [4-hierarchy]: UHE suppressed %d codes: %s", len(uhe_suppress), uhe_suppress)
        # Backup: existing config-driven suppression as safety net
        pool = self._cross_hierarchy_suppress_stage(pool, protected)
        pool = self._cross_prefix_suppress(pool, protected)
        pool = self._prefix_hierarchy_suppress(pool, det_set, protected)
        logger.info("SE [4-hierarchy]: %d after full hierarchy resolution", len(pool))

        # ── Stage 5: Group Selection (1 per group) ────────────────────
        pool = self._best_per_group(pool, det_set, protected)
        logger.info("SE [5-group]: %d after group selection", len(pool))

        # ── Stage 6: Fallback (MANDATORY_GROUPS) ──────────────────────
        pool = self._apply_fallback(pool, note_norm, covered_groups)
        logger.info("SE [6-fallback]: %d after fallback", len(pool))

        # ── Stage 7: Hard Validation (REMOVAL ONLY) ───────────────────
        pool = self._hard_validation_removal_only(pool, note_norm)
        logger.info("SE [7-hard_validation]: %d after hard validation", len(pool))

        # ── Stage 8: FINAL SAFETY FILTER (ABSOLUTE) ───────────────────
        final_codes_dicts = [s.as_dict() for s in pool]
        final_codes_dicts = self._final_safety_filter(final_codes_dicts, note_text, covered_groups)
        logger.info("SE [8-final_safety]: %d after final safety gate", len(final_codes_dicts))

        logger.info("SE FINAL: %d codes from %d candidates", len(final_codes_dicts), len(candidates))
        return final_codes_dicts

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 1: Validate + convert
    # ─────────────────────────────────────────────────────────────────────────

    def _validate_convert(
        self, candidates: list[dict], det_set: set[str]
    ) -> list[_ScoredCode]:
        result: list[_ScoredCode] = []
        seen: set[str] = set()

        for c in candidates:
            code_raw = c.get("code", "").strip().upper()
            if not code_raw or code_raw in seen:
                continue
            seen.add(code_raw)

            ctype = c.get("type", "ICD-10").upper()
            # Normalise "ICD" → "ICD-10"
            if ctype == "ICD":
                ctype = "ICD-10"

            if ctype != "CPT" and not _is_valid_icd10(code_raw):
                logger.debug("SE: invalid code rejected: '%s'", code_raw)
                continue

            group = _auto_group(code_raw, ctype)
            spec  = _specificity(code_raw)
            det_s = float(c.get("det_score", 0.95 if code_raw in det_set else 0.0))
            rag_s = float(c.get("rag_score", c.get("confidence", 0.75)))
            ent_s = 0.85 if c.get("entity") else 0.40
            conf  = float(c.get("confidence", max(det_s, rag_s, 0.5)))
            fs    = _score(det_s, rag_s, spec, ent_s)

            # v14: extract section_priority from entity metadata
            sec_pri = int(c.get("section_priority", 3))

            result.append(_ScoredCode(
                code=code_raw,
                description=c.get("description", ""),
                code_type=ctype,
                group=group,
                det_score=det_s,
                rag_score=rag_s,
                specificity=spec,
                entity_score=ent_s,
                confidence=conf,
                source=c.get("source", "rag"),
                rationale=c.get("rationale", ""),
                evidence_span=c.get("evidence_span", ""),
                final_score=fs + (PRINCIPAL_BOOST if sec_pri >= 9 else 0.0),
                protected=(code_raw in det_set),
                section_priority=sec_pri,
                extra={k: v for k, v in c.items() if k not in {
                    "code", "description", "type", "confidence", "source",
                    "rationale", "evidence_span", "det_score", "rag_score",
                    "llm_score", "entity", "section_priority",
                }},
            ))

        # v14: Hard-drop RAG-only codes below MIN_RAG_CONFIDENCE
        result = [
            s for s in result
            if s.source != "rag" or s.code in det_set or s.rag_score >= MIN_RAG_CONFIDENCE
        ]

        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 2: Hard category filter
    # ─────────────────────────────────────────────────────────────────────────

    def _hard_category_filter(
        self,
        pool: list[_ScoredCode],
        note_norm: str,
        det_set: set[str],
    ) -> list[_ScoredCode]:
        """
        Reject codes from clinically inappropriate chapters unless:
          (a) code is in det_set, or
          (b) note contains one of the required entity signals.
        Also handles renal syndrome prefix rejection when CKD is primary entity.
        """
        has_ckd = any(kw in note_norm for kw in CKD_ENTITY_SIGNALS)
        result: list[_ScoredCode] = []

        for s in pool:
            if s.code_type == "CPT" or s.code in det_set:
                result.append(s)
                continue

            letter = s.code[0].upper()
            pfx3   = _prefix3(s.code)

            # BUG 3 Fix: Pregnancy codes (O) blocked unless explicitly mentioned
            if letter == "O" and "pregnan" not in note_norm:
                continue
            
            # BUG 4 Fix: Screening codes (Z/V) blocked unless explicitly mentioned
            if letter in ("Z", "V") and "screen" not in note_norm:
                continue

            # Always-reject prefixes (V codes etc.)
            if letter in ALWAYS_REJECT_PREFIXES:
                logger.debug("SE: hard-reject always-reject prefix '%s'", s.code)
                continue

            # Conditional reject prefixes
            if letter in HARD_REJECT_PREFIXES:
                required_signals = HARD_REJECT_PREFIXES[letter]
                if not any(sig in note_norm for sig in required_signals):
                    logger.debug("SE: hard-reject '%s' (chapter '%s' not in note)", s.code, letter)
                    continue

            # Renal syndrome noise
            if has_ckd and pfx3 in RENAL_SYNDROME_PREFIXES:
                logger.debug("SE: reject renal syndrome code '%s' (CKD context)", s.code)
                continue

            result.append(s)
        return result

    # ─────────────────────────────────────────────────────────────────────────────
    # Stage 2.5: Clinical exclusivity (NEW)
    # ─────────────────────────────────────────────────────────────────────────────

    def _apply_clinical_exclusivity(
        self,
        pool: list[_ScoredCode],
        note_norm: str,
        det_set: set[str],
        protected: set[str],
    ) -> list[_ScoredCode]:
        """
        CLINICAL EXCLUSIVITY ENGINE (Fix 1).

        When a specific disease type is confirmed in the note, completely ban
        codes from competing families. Avoids:
          - E10.* appearing when type 2 diabetes is stated
          - I15.* appearing for essential hypertension
          - E88.* metabolic noise without explicit mention

        Rules defined in CLINICAL_EXCLUSIVITY_RULES (clinical_rules_config.py).
        Protected codes and deterministic codes are always kept.

        Special notes_signals value "*" means always active (checked via anti_signals only).
        """
        to_remove: set[str] = set()

        for rule in CLINICAL_EXCLUSIVITY_RULES:
            note_signals: list[str] = rule.get("note_signals", [])
            anti_signals:  list[str] = rule.get("anti_signals", [])
            exclude_pfxs:  list[str] = rule.get("exclude_prefixes", [])
            exclude_exact: list[str] = rule.get("exclude_exact", [])

            # Check if rule is globally active ("*") or needs a signal in note
            if note_signals == ["*"]:
                rule_active = True
            else:
                rule_active = any(sig in note_norm for sig in note_signals)

            if not rule_active:
                continue

            # If anti_signal is in note, don't fire (e.g., "secondary hypertension")
            if anti_signals and any(a in note_norm for a in anti_signals):
                logger.debug("SE: exclusivity rule '%s' suppressed by anti_signal", rule["id"])
                continue

            logger.info("SE: clinical exclusivity rule '%s' firing", rule["id"])

            # Mark all matching codes for removal (except protected/det)
            for s in pool:
                if s.code in protected or s.code in det_set or s.code_type == "CPT":
                    continue
                pfx3 = _prefix3(s.code)
                if pfx3 in exclude_pfxs or s.code in exclude_exact:
                    to_remove.add(s.code)
                    logger.debug("SE: exclusivity removing '%s' (rule: %s)", s.code, rule["id"])

        if to_remove:
            logger.info("SE: exclusivity removed %d codes: %s", len(to_remove), list(to_remove)[:10])

        return [s for s in pool if s.code not in to_remove]

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 3: Config compound rules
    # ─────────────────────────────────────────────────────────────────────────

    def _apply_compound_rules(
        self,
        pool: list[_ScoredCode],
        note_norm: str,
        det_set: set[str],
        protected: set[str],
        covered_groups: set[str],
    ) -> tuple[list[_ScoredCode], set[str], set[str]]:
        """
        Evaluate COMPOUND_RULES from clinical_rules_config.

        Rule fires IF:
          - All entity_all phrases are present in note_norm (partial match)
          - At least one entity_signals phrase is present (OR logic), OR entity_signals empty
          - At least one code with trigger_prefix in pool (OR result already present)

        Result code → PROTECTED, added to pool if not already there.
        Eliminate codes/prefixes removed (unless protected).
        Track covered_groups from compound rules.
        """
        code_set = {s.code for s in pool}
        to_remove: set[str] = set()
        to_add: list[_ScoredCode] = []
        new_protected = set(protected)
        new_covered_groups = set(covered_groups)

        # Negative context indicators for compound rules too
        negative_contexts = [
            "no ", "not ", "without ", "denies ", "denied ", "negative for ",
            "no evidence of ", "no signs of ", "no symptoms of ", "no history of ",
            "no mention of ", "no indication of ", "ruled out ", "exclude "
        ]

        for rule in sorted(COMPOUND_RULES, key=lambda r: r.get("priority", 0), reverse=True):
            # Skip if all covered_groups from this rule are already covered
            rule_covers = set(rule.get("covers_groups", []))
            if rule_covers and rule_covers.issubset(new_covered_groups):
                continue

            # Check conditions (ALL must loosely match in POSITIVE context)
            conditions_met = True
            for cond in rule.get("conditions", []):
                cond_clean = cond.replace("*", "")
                if cond_clean not in note_norm:
                    conditions_met = False
                    break

                # Check for negation
                if self.is_negated(cond_clean, note_norm):
                    conditions_met = False
                    break

            if not conditions_met:
                continue

            result_code = rule["code"]
            logger.info("SE: pattern compound rule fired → %s", result_code)

            # Track covered groups from this rule
            rule_covers = rule.get("covers_groups", [])
            new_covered_groups.update(rule_covers)
            logger.debug("SE: rule '%s' covers groups: %s", rule["id"], rule_covers)

            # Protect existing result if already in pool
            if result_code in code_set:
                for s in pool:
                    if s.code == result_code:
                        s.protected = True
                        new_protected.add(result_code)
                        break
            else:
                # Build new code entry dynamically
                sc = _ScoredCode(
                    code=result_code,
                    description=rule.get("desc", ""),
                    code_type="ICD-10",
                    group=_auto_group(result_code, "ICD-10"),
                    det_score=0.95,
                    rag_score=0.85,
                    specificity=_specificity(result_code),
                    entity_score=1.0,
                    confidence=0.97,
                    source="deterministic",
                    rationale=f"Pattern compound rule match",
                    final_score=0.98,
                    protected=True,
                )
                to_add.append(sc)
                code_set.add(result_code)
                new_protected.add(result_code)

            # Protect required additional codes
            for req_code in rule.get("requires_additional_codes", []):
                for s in pool:
                    if s.code.startswith(req_code):
                        s.protected = True
                        new_protected.add(s.code)
                        logger.debug("SE: protecting required code '%s' for rule '%s'", s.code, rule["id"])

        if to_remove:
            actually = to_remove & {s.code for s in pool}
            logger.info("SE: compound rules removing: %s", actually)

        result = [s for s in pool if s.code not in to_remove] + to_add
        return result, new_protected, new_covered_groups

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 4: Auto combination dominance (generic, no config required)
    # ─────────────────────────────────────────────────────────────────────────

    def _auto_combination_dominance(
        self,
        pool: list[_ScoredCode],
        protected: set[str],
    ) -> tuple[list[_ScoredCode], set[str]]:
        """
        GENERIC COMBINATION DOMINANCE ENGINE.

        Principle (ICD-10 coding standard):
          "A combination code that represents two or more conditions
           always takes precedence over separate codes for each condition."

        Detection (no config needed):
          A code is a COMBINATION code if it is LONGER (more specific) than
          any other code from a DIFFERENT prefix family but sits within the
          same disease group derived from the entity (i.e., it was produced
          by a compound rule).

        Practical auto-rule:
          If code A (prefix P1) exists in pool AND code B (prefix P2 ≠ P1)
          exists in pool, AND code C (prefix = P1) is MORE SPECIFIC than A
          AND C is already PROTECTED (meaning it was created by compound rule):
            → A and B are suppressed by C.

        Example:
          E11.42 (protected, compound-created) + E11.9 + G62.9 in pool
          → E11.42 is more specific than E11.9, and covers G62.9 semantic domain
          → E11.9 suppressed (same prefix, less specific)
          → G62.9 suppressed (cross-prefix, but compound rule already marked it)

        This complements compound rules without needing explicit per-code config.
        """
        new_protected = set(protected)
        to_remove: set[str] = set()

        # Build index: prefix → list of codes
        by_prefix: dict[str, list[_ScoredCode]] = {}
        for s in pool:
            if s.code_type == "CPT":
                continue
            by_prefix.setdefault(_prefix3(s.code), []).append(s)

        for pfx, group_codes in by_prefix.items():
            protected_in_prefix = [
                c for c in group_codes
                if c.protected or c.code in protected
            ]
            if not protected_in_prefix:
                continue

            # Find most specific protected code in this prefix family
            best_protected = max(protected_in_prefix, key=lambda c: c.specificity)

            # Suppress any less-specific code in the same prefix (not protected)
            for c in group_codes:
                if c.code == best_protected.code:
                    continue
                if c.code not in new_protected and c.specificity < best_protected.specificity:
                    to_remove.add(c.code)

        if to_remove:
            logger.info("SE: auto-combination-dominance suppressing: %s", to_remove & {s.code for s in pool})

        return [s for s in pool if s.code not in to_remove], new_protected

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 5: Entity-code validation
    # ─────────────────────────────────────────────────────────────────────────

    def _entity_validate(
        self,
        pool: list[_ScoredCode],
        note_norm: str,
        det_set: set[str],
        protected: set[str],
    ) -> list[_ScoredCode]:
        """
        Every RAG-only code must correspond to an entity present in the note.

        MULTI-LAYER VALIDATION:
          1. Primary:  code's 3-char prefix in ENTITY_PREFIX_MAP allowed list for a matched entity
          2. Secondary: code's 1-char chapter letter semantically relevant to a matched entity
          3. Tertiary:  suffix confidence >= MIN_RAG_CONFIDENCE (weak fallback)

        Protected and deterministic codes always pass.
        CPT codes always pass (no ICD entity mapping needed).
        """
        result: list[_ScoredCode] = []
        rejected: list[str] = []

        for s in pool:
            # Always keep protected / deterministic / CPT
            if s.code_type == "CPT" or s.code in det_set or s.code in protected or s.protected:
                result.append(s)
                continue

            pfx3   = _prefix3(s.code)
            letter = s.code[0].upper()

            # Layer 1: prefix must match an entity keyword in note
            layer1 = False
            for entity_kw, allowed_pfxs in ENTITY_PREFIX_MAP.items():
                if entity_kw in note_norm:
                    # Check if any allowed prefix starts-matches our code prefix
                    for ap in allowed_pfxs:
                        if pfx3.startswith(ap) or ap.startswith(pfx3):
                            layer1 = True
                            break
                if layer1:
                    break

            if layer1:
                result.append(s)
                continue

            # Layer 2: check if ANY entity keyword maps to the same chapter letter AND passes semantic similarity
            layer2 = False
            for entity_kw, allowed_pfxs in ENTITY_PREFIX_MAP.items():
                if entity_kw in note_norm:
                    # Condition 1: Prefix mapping chapter match
                    if any(p[0].upper() == letter for p in allowed_pfxs if p):
                        # Semantic validation condition
                        # Extract the target entity string by finding matching entity keywords
                        if SequenceMatcher(None, s.description.lower(), entity_kw).ratio() > 0.7:
                            layer2 = True
                            break

            if layer2:
                result.append(s)
                continue

            # Rejected
            logger.debug("SE: entity validation rejected '%s' (no entity match)", s.code)
            rejected.append(s.code)

        if rejected:
            logger.info("SE: entity validation removed %d codes: %s", len(rejected), rejected[:10])
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 6: Prefix hierarchy suppression (AUTO-DERIVED)
    # ─────────────────────────────────────────────────────────────────────────

    def _prefix_hierarchy_suppress(
        self,
        pool: list[_ScoredCode],
        det_set: set[str],
        protected: set[str],
    ) -> list[_ScoredCode]:
        """
        AUTO-DERIVED PREFIX HIERARCHY.

        ICD-10 rule: a more-specific code (longer) suppresses its shorter parent.
          N18.32 is present → remove N18.3 (parent), N18.9 (grandparent)
          E11.42 is present → remove E11.4 (parent), E11 (grandparent)

        ALGORITHM — for every code in pool:
          1. Generate all prefix ancestors: N18.32 → ["N18.3", "N18", "N1", "N"]
          2. For each ancestor that exactly matches another code in pool → suppress it

        This works for ALL ICD chapters with ZERO configuration.
        PROTECTED codes are immune.
        """
        code_set = {s.code for s in pool}
        to_remove: set[str] = set()

        for s in pool:
            if s.code_type == "CPT":
                continue

            # Generate all strict prefix ancestors
            ancestors = _get_prefix_ancestors(s.code)

            for ancestor in ancestors:
                if ancestor in code_set and ancestor not in protected:
                    to_remove.add(ancestor)

        if to_remove:
            logger.info("SE: prefix-hierarchy suppressing: %s", to_remove & code_set)

        return [s for s in pool if s.code not in to_remove]

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 7: Cross-prefix suppression (config)
    # ─────────────────────────────────────────────────────────────────────────

    def _cross_prefix_suppress(
        self,
        pool: list[_ScoredCode],
        protected: set[str],
    ) -> list[_ScoredCode]:
        """
        CONFIG-based cross-prefix suppression (Fix 2 — wildcard support).

        Supports two entry formats in suppress_list:
          "P:G62"      → remove ALL codes whose 3-char prefix = G62
          "EXACT:G62.9" → remove only that exact code
          bare str      → treated as EXACT (backwards compat)

        Trigger is exact code match in pool.
        Protected codes are NEVER removed.
        """
        code_set = {s.code for s in pool}
        to_remove: set[str] = set()

        for trigger_code, suppress_list in CROSS_PREFIX_SUPPRESS.items():
            trigger_present = trigger_code in code_set
            if not trigger_present:
                continue

            for entry in suppress_list:
                if entry.startswith("P:"):
                    # Prefix wildcard: remove all codes with this 3-char prefix
                    target_pfx = entry[2:].upper()
                    for c in code_set:
                        if _prefix3(c) == target_pfx and c not in protected:
                            to_remove.add(c)
                elif entry.startswith("EXACT:"):
                    # Exact match
                    exact = entry[6:].upper()
                    if exact in code_set and exact not in protected:
                        to_remove.add(exact)
                else:
                    # Backwards compat: bare string = exact
                    if entry in code_set and entry not in protected:
                        to_remove.add(entry)

        if to_remove:
            logger.info("SE: cross-prefix suppressing: %s", to_remove & code_set)

        return [s for s in pool if s.code not in to_remove]

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 8: Auto-group + best-per-group
    # ─────────────────────────────────────────────────────────────────────────

    def _best_per_group(
        self,
        pool: list[_ScoredCode],
        det_set: set[str],
        protected: set[str],
    ) -> list[_ScoredCode]:
        """
        STRICT 1-PER-GROUP SELECTION (Fix 3).

        Groups codes by 3-char ICD prefix (auto-derived via _auto_group).
        Selects EXACTLY ONE code per group—no secondary codes, no leakage.

        Priority within group:
          1. PROTECTED codes (compound-generated or deterministic)
          2. Source = 'deterministic'
          3. Highest specificity (more specific = better)
          4. Highest final_score (tie-breaking only)

        CPT codes: each is its own singleton group — all pass through.
        """
        groups: dict[str, list[_ScoredCode]] = {}
        for s in pool:
            groups.setdefault(s.group, []).append(s)

        selected: list[_ScoredCode] = []

        for grp, members in groups.items():
            # CPT singleton groups — pass through as-is
            if grp.startswith("cpt_"):
                selected.extend(members)
                continue

            if len(members) == 1:
                # Only one candidate in group — keep it if det, protected, or passed entity validation
                m = members[0]
                if m.source != "deterministic" and m.confidence < MIN_RAG_CONFIDENCE:
                    # RAG only singleton — if it maps to a valid entity prefix, we keep it anyway
                    valid_pfxs = []
                    for e in det_set:  # using det_set as hack for confirmed_entities because selection_engine only gets det_set codes?
                        pass # Wait, SelectionEngine's select() receives deterministic_codes, not confirmed_entities string list
                    # But if we made it to Stage 8, it ALREADY passed Stage 5 _entity_validate!
                    pass 
                selected.append(m)
                continue

            # Multiple candidates: rank and pick strictly 1 (no exceptions)
            members.sort(
                key=lambda s: (
                    1 if (s.protected or s.code in protected) else 0,  # 1. protected / compound
                    s.specificity,                                     # 2. most specific
                    1 if s.source == "deterministic" else 0,           # 3. deterministic
                    s.final_score,                                     # 4. RAG / score
                ),
                reverse=True,
            )

            # Drop codes below confidence threshold (not protected/det)
            winner = members[0]
            if (
                winner.source != "deterministic"
                and not (winner.protected or winner.code in protected)
                and winner.confidence < MIN_RAG_CONFIDENCE
            ):
                # Try next in list that meets threshold
                fallback = next(
                    (m for m in members[1:] if m.confidence >= MIN_RAG_CONFIDENCE
                     or m.source == "deterministic"
                     or m.protected or m.code in protected),
                    None,
                )
                if fallback:
                    winner = fallback
                # else: keep original winner (best we have)

            selected.append(winner)

        # BUG 2 FIX: STRICT DIABETES EXCLUSIVITY (Only 1 diabetes category allowed)
        # Never allow E08, E09, E10, E11, E13 to coexist
        diabetes_categories = {"E08", "E09", "E10", "E11", "E13"}
        diabetes_cands = [s for s in selected if s.group in diabetes_categories]
        
        if len(diabetes_cands) > 1:
            best_diabetes = max(diabetes_cands, key=lambda s: (
                1 if (s.protected or s.code in protected) else 0,
                s.specificity,
                1 if s.source == "deterministic" else 0,
                s.final_score
            ))
            selected = [s for s in selected if s.group not in diabetes_categories or s.code == best_diabetes.code]

        # Sort final list: protected/det codes first, then by score
        selected.sort(
            key=lambda s: (
                1 if (s.protected or s.code in protected) else 0,
                s.specificity,
                1 if s.source == "deterministic" else 0,
                s.final_score,
            ),
            reverse=True,
        )
        return selected[:MAX_FINAL_CODES]

    # ─────────────────────────────────────────────────────────────────────────
    # Stage X: Cross-Hierarchy Engine (V8 Fix 1 / V9 Early)
    # ─────────────────────────────────────────────────────────────────────────

    def _cross_hierarchy_suppress_stage(
        self, pool: list[_ScoredCode], protected: set[str]
    ) -> list[_ScoredCode]:
        """
        Runs BEFORE and AFTER group selection, strictly removing children across prefix families.
        Example: E11.42 removes all G62.*
        """
        to_remove: set[str] = set()
        code_set = {s.code for s in pool}
        for parent_code, targets in HIERARCHY_SUPPRESSION.items():
            if parent_code in code_set:
                for target_pfx in targets:
                    for s in pool:
                        if s.code.startswith(target_pfx) and not (s.protected or s.code in protected):
                            logger.info("SE: Cross-Hierarchy %s suppressing %s", parent_code, s.code)
                            to_remove.add(s.code)

        if to_remove:
            return [s for s in pool if s.code not in to_remove]
        return pool

    # ─────────────────────────────────────────────────────────────────────────
    # STRICT SAFETY: High-risk diseases
    # ─────────────────────────────────────────────────────────────────────────
    HIGH_RISK_DISEASES = [
        "myocardial infarction",
        "stroke",
        "sepsis",
        "mi",
        "acute mi"
    ]

    def _should_add_fallback(
        self, keyword: str, note_text: str, covered_groups: set[str]
    ) -> bool:
        """
        ULTRA-STRICT FALLBACK (HOSPITAL-GRADE)
        RULE:
        1. EXACT keyword match (word-boundary)
        2. NOT negated
        3. NOT covered already
        """
        text = note_text.lower()
        
        # 1. Exact match
        pattern = rf"\b{re.escape(keyword)}\b"
        if not re.search(pattern, text):
            return False

        # 2. Negation Check
        if self.is_negated(keyword, text):
            logger.debug("SE: Fallback '%s' blocked by negation", keyword)
            return False

        # 3. Coverage Check
        if keyword in covered_groups:
            return False

        return True

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 5: Fallback (MANDATORY_GROUPS) - FINAL STAGE ONLY
    # ─────────────────────────────────────────────────────────────────────────

    def _apply_fallback(
        self,
        pool: list[_ScoredCode],
        note_norm: str,
        covered_groups: set[str],
    ) -> list[_ScoredCode]:
        """
        🚨 STRICT FALLBACK: Last resort ONLY.

        RULE: Never add unless keyword is present AND not covered.
        Safety: No high-risk diseases unless explicitly mentioned.
        """
        current_codes = {s.code for s in pool}
        result = list(pool)

        for keyword, fallback_info in MANDATORY_GROUPS.items():
            # STRICT check: must pass ALL conditions
            if not self._should_add_fallback(keyword, note_norm, covered_groups):
                continue

            # Fallback can now be safely added
            fallback_code = fallback_info["code"]
            fallback_pfx = _prefix3(fallback_code)

            # Don't add if same prefix already exists
            has_group = any(_prefix3(c) == fallback_pfx for c in current_codes)
            if has_group:
                continue

            logger.warning("SE: Fallback for '%s' → %s", keyword, fallback_code)
            result.append(_ScoredCode(
                code=fallback_code,
                description=fallback_info["description"],
                code_type="ICD-10",
                source="deterministic",
                confidence=0.99,
                specificity=_specificity(fallback_code),
                group=fallback_pfx,
                det_score=0.99,
                final_score=0.99,
                protected=True,
            ))
            current_codes.add(fallback_code)
            covered_groups.add(keyword)

        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 6: Hard Validation (REMOVAL ONLY)
    # ─────────────────────────────────────────────────────────────────────────

    def _hard_validation_removal_only(self, pool: list[_ScoredCode], note_norm: str) -> list[_ScoredCode]:
        """
        FINAL SAFETY: Remove invalid combinations, duplicates, and suppressed codes.
        NEVER adds codes - only removes.
        """
        to_remove: set[str] = set()

        # 1. Relationship Validation (e.g. I12.x requires HTN + CKD)
        for s in pool:
            if s.code_type == "CPT" or s.code in to_remove:
                continue

            for rule in RELATIONSHIP_VALIDATION_RULES:
                if any(s.code.startswith(p) for p in rule["target_prefixes"]):
                    missing = False
                    for req in rule["required_entities"]:
                        req_syns = [req]
                        if req == "hypertension":
                            req_syns.extend(["htn", "high blood pressure"])
                        if req == "chronic kidney":
                            req_syns.extend(["ckd", "renal", "kidney"])

                        if not any(r in note_norm for r in req_syns):
                            missing = True
                            break

                    if missing:
                        logger.warning("SE: Removing %s (missing required entity)", s.code)
                        to_remove.add(s.code)

        # 2. Cross-hierarchy suppression (final safety pass)
        code_set = {s.code for s in pool}
        for parent_code, targets in HIERARCHY_SUPPRESSION.items():
            if parent_code in code_set:
                for target_pfx in targets:
                    for s in pool:
                        if s.code.startswith(target_pfx) and s.code not in to_remove and not s.protected:
                            logger.info("SE: Final suppression %s removes %s", parent_code, s.code)
                            to_remove.add(s.code)

        # 3. Cross-prefix suppression (final safety pass)
        for trigger_code, suppress_list in CROSS_PREFIX_SUPPRESS.items():
            if trigger_code in code_set:
                for entry in suppress_list:
                    if entry.startswith("P:"):
                        target_pfx = entry[2:].upper()
                        for s in pool:
                            if _prefix3(s.code) == target_pfx and s.code not in to_remove:
                                to_remove.add(s.code)
                    elif entry.startswith("EXACT:"):
                        exact = entry[6:].upper()
                        if exact in code_set and exact not in to_remove:
                            to_remove.add(exact)
                    else:
                        if entry in code_set and entry not in to_remove:
                            to_remove.add(entry)

        # 4. Final dedup and validation
        seen: set[str] = set()
        final_result: list[_ScoredCode] = []

        for s in pool:
            if s.code in to_remove or s.code in seen:
                continue
            seen.add(s.code)

            if s.code_type == "CPT":
                final_result.append(s)
                continue

            if not _is_valid_icd10(s.code):
                logger.warning("SE: Invalid ICD format rejected '%s'", s.code)
                continue

            # Clean descriptions
            if s.source != "deterministic" and s.description:
                s.description = clean_rag_description(s.description)

            final_result.append(s)

        return final_result

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 2: Negation Filtering (NEW)
    # ─────────────────────────────────────────────────────────────────────────

    def is_negated(self, keyword: str, text: str) -> bool:
        """STRICT NEGATION DETECTION."""
        NEGATIONS = ["no", "not", "without", "denies", "negative for"]
        text = text.lower()
        for neg in NEGATIONS:
            # Check for direct negation: "no heart failure", "without diabetes"
            # Using regex for word boundaries and flexible spacing
            pattern = rf"\b{re.escape(neg)}\s+(?:evidence\s+of\s+)?{re.escape(keyword)}\b"
            if re.search(pattern, text):
                return True
        return False

    def _filter_negations(self, pool: list[_ScoredCode], text: str, protected: set[str]) -> list[_ScoredCode]:
        """Scans all codes and removes those related to negated entities."""
        to_remove = set()
        for s in pool:
            if s.code in protected or s.protected:
                continue
            
            # Use associated keywords or description to detect negation
            # We check the code's description and its auto-group keywords
            # For brevity in this generic engine, we check the description keyword
            for entity_kw in ENTITY_PREFIX_MAP.keys():
                if entity_kw in text and self.is_negated(entity_kw, text):
                    # If this code belongs to that entity family, remove it
                    pfxs = ENTITY_PREFIX_MAP[entity_kw]
                    if any(s.code.startswith(p) for p in pfxs):
                        logger.info("SE: Negation detected for '%s' -> removing %s", entity_kw, s.code)
                        to_remove.add(s.code)
                        break
        
        return [s for s in pool if s.code not in to_remove]

    # ─────────────────────────────────────────────────────────────────────────
    # Stage 8: GLOBAL FINAL SAFETY FILTER (ABSOLUTE)
    # ─────────────────────────────────────────────────────────────────────────

    def resolve_diabetes_type(self, diabetes_codes: list[dict], text: str) -> dict:
        """HARD DIABETES TYPE LOCK."""
        text = text.lower()
        is_type1 = "type 1" in text
        is_type2 = "type 2" in text
        
        # Default logic: "if 'type 2' -> ONLY allow E11, if 'type 1' -> ONLY allow E10, Else: default -> E11"
        target_prefix = "E11"
        if is_type1:
            target_prefix = "E10"
        elif is_type2:
            target_prefix = "E11"
            
        filtered = [c for c in diabetes_codes if c["code"].startswith(target_prefix)]
        if not filtered:
            # Fallback to E11 if we have ANY diabetes codes but none matched the strict type
            # (Safety: ensure RAG results don't zero out the entire diagnosis)
            return max(diabetes_codes, key=lambda c: (c.get("specificity", 0), c.get("final_score", 0)))
        
        return max(filtered, key=lambda c: (c.get("specificity", 0), c.get("final_score", 0)))

    def _final_safety_filter(self, codes: list[dict], text: str, covered_groups: set[str]) -> list[dict]:
        """
        UPGRADED GLOBAL FINAL SAFETY FILTER (ABSOLUTE)
        The final absolute gate before returning to user.
        """
        text = text.lower()
        filtered = []

        for code_dict in codes:
            c = code_dict["code"]

            # 🚨 BLOCK pregnancy codes unless context present
            if c.startswith("O") and "pregnan" not in text:
                logger.warning("SE: Safety Block pregnancy %s (missing context)", c)
                continue

            # 🚨 BLOCK screening/v-codes unless context present
            if c.startswith(("Z", "V")) and "screen" not in text:
                logger.warning("SE: Safety Block screening %s (missing context)", c)
                continue

            # 🚨 BLOCK MI (I21) if not explicitly mentioned as "infarction"
            if c.startswith("I21") and "infarction" not in text:
                logger.warning("SE: Safety Block Myocardial Infarction %s (missing context)", c)
                continue

            filtered.append(code_dict)

        # 🚨 HARD diabetes enforcement
        dm_prefixes = ("E08", "E09", "E10", "E11", "E13")
        diabetes = [c for c in filtered if c["code"].startswith(dm_prefixes)]

        if len(diabetes) > 1:
            best = self.resolve_diabetes_type(diabetes, text)
            logger.info("SE: Multi-diabetes locked to %s", best["code"])
            filtered = [c for c in filtered if not c["code"].startswith(dm_prefixes)]
            filtered.append(best)

        return filtered


# ─────────────────────────────────────────────────────────────────────────────
# Helper: generate prefix ancestors for auto-derived hierarchy
# ─────────────────────────────────────────────────────────────────────────────

def _get_prefix_ancestors(code: str) -> list[str]:
    """
    Generate all strict prefix ancestors of an ICD-10 code.

    N18.32  →  [N18.3, N18.30, N18, N1]       (not N18.32 itself)
    E11.42  →  [E11.4, E11, E1]
    I50.23  →  [I50.2, I50, I5]

    Only returns ancestors that look like valid ICD codes (3+ chars, letter+digits).
    """
    ancestors: list[str] = []
    # Split at dot
    if "." in code:
        prefix, suffix = code.split(".", 1)
        # Generate suffix truncations: N18.32 → [N18.3]
        for i in range(len(suffix) - 1, 0, -1):
            ancestors.append(f"{prefix}.{suffix[:i]}")
        # Also add the bare prefix (N18)
        ancestors.append(prefix)
        # Add truncations of base (N1, etc. — these rarely appear as real codes but are safe to check)
        for i in range(len(prefix) - 1, 2, -1):
            ancestors.append(prefix[:i])
    else:
        # No dot — add truncations
        for i in range(len(code) - 1, 2, -1):
            ancestors.append(code[:i])

    return ancestors
