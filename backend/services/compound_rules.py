# services/compound_rules.py

SEED_COMPOUND_RULES: list[dict] = [
    # ── DIABETES TYPE 2 COMPLICATIONS ────────────────────────────────────────
    {
        "id": "DM2_PERIPHERAL_NEUROPATHY",
        "conditions": ["type 2", "diabet", "neuropath"],
        "code": "E11.42",
        "desc": "Type 2 diabetes mellitus with diabetic peripheral neuropathy, unspecified",
        "suppresses": ["G57", "G58", "G59", "G60", "G61", "G62", "G63", "G64", "E11.9", "E11.40", "E11.41", "E11.638", "E11.628", "E11.49", "E13.8"],
        "covers_groups": ["neuropathy", "diabet", "dm2", "type 2 diabetes"]
    },
    {
        "id": "DM2_MONONEUROPATHY",
        "conditions": ["type 2", "diabet", "mononeuropath"],
        "code": "E11.41",
        "desc": "Type 2 diabetes mellitus with diabetic mononeuropathy",
        "suppresses": ["G57", "G58", "E11.9", "E11.40"],
        "covers_groups": ["neuropathy", "diabet", "dm2"]
    },
    {
        "id": "DM2_CKD",
        "conditions": ["type 2", "diabet", "chronic kidney"],
        "code": "E11.22",
        "desc": "Type 2 diabetes mellitus with diabetic chronic kidney disease",
        "suppresses": ["E11.65", "E11.9"],
        "requires_additional_codes": ["N18"],
        "covers_groups": ["ckd", "chronic kidney", "diabet", "dm2"]
    },
    {
        "id": "DM2_NEPHROPATHY",
        "conditions": ["type 2", "diabet", "nephropath"],
        "code": "E11.21",
        "desc": "Type 2 diabetes mellitus with diabetic nephropathy",
        "suppresses": ["E11.9"],
        "covers_groups": ["nephropathy", "diabet", "dm2"]
    },
    {
        "id": "DM2_RETINOPATHY_BACKGROUND",
        "conditions": ["diabet", "retinopathy", "background"],
        "code": "E11.319",
        "desc": "Type 2 diabetes mellitus with unspecified diabetic retinopathy without macular edema",
        "suppresses": ["E11.9", "E11.31", "E11.39"],
        "covers_groups": ["retinopathy", "diabet", "dm2"]
    },
    {
        "id": "DM2_FOOT_ULCER",
        "conditions": ["type 2", "diabet", "foot ulcer"],
        "code": "E11.621",
        "desc": "Type 2 diabetes mellitus with foot ulcer",
        "suppresses": ["E11.9", "E11.62"],
        "covers_groups": ["ulcer", "foot ulcer", "diabet", "dm2"]
    },

    # ── HEART FAILURE SUBTYPES ────────────────────────────────────────────────
    {
        "id": "HF_ACUTE_ON_CHRONIC_SYSTOLIC",
        "conditions": ["acute on chronic systolic", "heart failure"],
        "code": "I50.23",
        "desc": "Acute on chronic systolic (congestive) heart failure",
        "suppresses": ["I50.9", "I50.20", "I50.21", "I50.40", "I50.41", "I50.43"],
        "covers_groups": ["heart failure", "chf"]
    },
    {
        "id": "HF_ACUTE_ON_CHRONIC_DIASTOLIC",
        "conditions": ["acute on chronic diastolic", "heart failure"],
        "code": "I50.33",
        "desc": "Acute on chronic diastolic (congestive) heart failure",
        "suppresses": ["I50.9", "I50.30", "I50.31", "I50.40", "I50.41"],
        "covers_groups": ["heart failure", "chf"]
    },
    {
        "id": "HF_ACUTE_SYSTOLIC",
        "conditions": ["acute systolic", "heart failure"],
        "code": "I50.21",
        "desc": "Acute systolic (congestive) heart failure",
        "suppresses": ["I50.9", "I50.20", "I50.40", "I50.43"],
        "covers_groups": ["heart failure", "chf"]
    },
    {
        "id": "HF_CHRONIC_SYSTOLIC",
        "conditions": ["chronic systolic", "heart failure"],
        "code": "I50.22",
        "desc": "Chronic systolic (congestive) heart failure",
        "suppresses": ["I50.9", "I50.20"],
        "covers_groups": ["heart failure", "chf"]
    },

    # ── CKD STAGE-SPECIFIC ─────────────────────────────────────────────────────
    {
        "id": "CKD_STAGE_3B",
        "conditions": ["stage 3b", "chronic kidney"],
        "code": "N18.32",
        "desc": "Chronic kidney disease, stage 3b",
        "suppresses": ["N01", "N02", "N03", "N04", "N05", "N06", "N07", "N08", "N25", "N26", "N27", "N18.9", "N18.30", "N18.3", "N18.31"],
        "covers_groups": ["ckd", "chronic kidney", "renal disease"]
    },
    {
        "id": "CKD_STAGE_3A",
        "conditions": ["stage 3a", "chronic kidney"],
        "code": "N18.31",
        "desc": "Chronic kidney disease, stage 3a",
        "suppresses": ["N01", "N02", "N03", "N04", "N05", "N06", "N07", "N08", "N25", "N26", "N27", "N18.9", "N18.30", "N18.3", "N18.32"],
        "covers_groups": ["ckd", "chronic kidney", "renal disease"]
    },
    {
        "id": "CKD_STAGE_3",
        "conditions": ["stage 3", "chronic kidney"],
        "code": "N18.3",
        "desc": "Chronic kidney disease, stage 3 unspecified",
        "suppresses": ["N01", "N02", "N03", "N04", "N05", "N06", "N07", "N08", "N25", "N26", "N27", "N18.9", "N18.30"],
        "covers_groups": ["ckd", "chronic kidney", "renal disease"]
    },
    {
        "id": "CKD_STAGE_4",
        "conditions": ["stage 4", "chronic kidney"],
        "code": "N18.4",
        "desc": "Chronic kidney disease, stage 4",
        "suppresses": ["N01", "N02", "N03", "N04", "N05", "N06", "N07", "N08", "N25", "N26", "N27", "N18.9", "N18.3"],
        "covers_groups": ["ckd", "chronic kidney", "renal disease"]
    },
    {
        "id": "CKD_STAGE_5_ESRD",
        "conditions": ["esrd"],
        "code": "N18.6",
        "desc": "End stage renal disease",
        "suppresses": ["N01", "N02", "N03", "N04", "N05", "N06", "N07", "N08", "N25", "N26", "N27", "N18.9", "N18.3", "N18.4", "N18.5"],
        "covers_groups": ["ckd", "chronic kidney", "esrd", "renal disease"]
    },

    # ── HYPERTENSION COMPLICATIONS ────────────────────────────────────────────
    {
        "id": "HTN_WITH_HEART_FAILURE",
        "conditions": ["hypertension", "heart failure"],
        "code": "I11.0",
        "desc": "Hypertensive heart disease with heart failure",
        "suppresses": ["I11.9"],
        "covers_groups": ["hypertension", "htn", "heart failure", "chf"]
    },
    {
        "id": "HTN_WITH_CKD",
        "conditions": ["hypertension", "chronic kidney"],
        "code": "I12.9",
        "desc": "Hypertensive chronic kidney disease with stage 1-4 or unspecified CKD",
        "suppresses": ["I10"],
        "covers_groups": ["hypertension", "htn", "ckd", "chronic kidney"]
    },
]

# Alias for backwards compatibility — SEED rules are PRIMARY
COMPOUND_RULES = SEED_COMPOUND_RULES


# ─────────────────────────────────────────────────────────────────────────────
# DYNAMIC COMPOUND DETECTOR (v7)
# ─────────────────────────────────────────────────────────────────────────────
# STRICT: requires BOTH entities confirmed in note text.
# NEVER infers compound codes from description alone.
# Only fires for codes NOT already covered by SEED rules.

import re

# Combination patterns in ICD-10 descriptions
_COMBINATION_PATTERNS = [
    re.compile(r"(.+?)\s+with\s+(.+)", re.IGNORECASE),
    re.compile(r"(.+?)\s+due\s+to\s+(.+)", re.IGNORECASE),
    re.compile(r"(.+?)\s+in\s+(.+)", re.IGNORECASE),
    re.compile(r"(.+?)\s+associated\s+with\s+(.+)", re.IGNORECASE),
    re.compile(r"(.+?)\s+complicated\s+by\s+(.+)", re.IGNORECASE),
]


class DynamicCompoundDetector:
    """
    Detects combination codes from RAG results.

    CRITICAL SAFETY RULES:
      1. SEED_COMPOUND_RULES fire FIRST (primary, clinically validated)
      2. Dynamic detection requires DUAL ENTITY CONFIRMATION in note text
      3. NO description-only inference (clinically unsafe)
      4. Only fires for codes NOT covered by seed rules
    """

    @staticmethod
    def _is_seed_covered(code: str) -> bool:
        """Check if a code is already covered by a seed compound rule."""
        for rule in SEED_COMPOUND_RULES:
            if rule["code"] == code:
                return True
        return False

    @staticmethod
    def detect_compounds(
        rag_candidates: list[dict],
        note_entities: list[str],
        note_text: str,
    ) -> list[dict]:
        """
        Detect compound/combination codes from RAG results.

        Returns list of compound matches:
        {
            "code": "E11.22",
            "description": "...",
            "conditions_matched": ["diabetes", "chronic kidney"],
            "suppresses_prefixes": ["E11.9"],
            "source": "dynamic_compound",
        }

        STRICT: both conditions must be confirmed entities in the note.
        """
        note_lower = note_text.lower()
        entity_set = {e.lower() for e in note_entities}
        compounds: list[dict] = []
        seen_codes: set[str] = set()

        for candidate in rag_candidates:
            code = candidate.get("code", "").strip().upper()
            desc = candidate.get("description", "").lower()

            if not code or not desc:
                continue
            if code in seen_codes:
                continue
            if DynamicCompoundDetector._is_seed_covered(code):
                continue  # already handled by seed rules

            # Try to match combination patterns
            for pattern in _COMBINATION_PATTERNS:
                match = pattern.match(desc)
                if not match:
                    continue

                condition_a = match.group(1).strip()
                condition_b = match.group(2).strip()

                # STRICT DUAL ENTITY CONFIRMATION:
                # Both conditions must appear in note entities or note text
                a_confirmed = False
                b_confirmed = False

                for entity in entity_set:
                    # Check if entity matches condition A
                    a_words = {w for w in condition_a.split() if len(w) > 3}
                    if a_words and any(w in entity for w in a_words):
                        a_confirmed = True
                    elif condition_a[:6] in entity or entity in condition_a:
                        a_confirmed = True

                    # Check if entity matches condition B
                    b_words = {w for w in condition_b.split() if len(w) > 3}
                    if b_words and any(w in entity for w in b_words):
                        b_confirmed = True
                    elif condition_b[:6] in entity or entity in condition_b:
                        b_confirmed = True

                if not (a_confirmed and b_confirmed):
                    continue  # REJECT: both conditions must be confirmed

                # Also verify both conditions are in the actual note text
                a_in_note = any(w in note_lower for w in condition_a.split() if len(w) > 3)
                b_in_note = any(w in note_lower for w in condition_b.split() if len(w) > 3)
                if not (a_in_note and b_in_note):
                    continue  # REJECT: both must appear in note

                # Build compound match
                pfx3 = code.split(".")[0] if "." in code else code[:3]
                compounds.append({
                    "code": code,
                    "description": candidate.get("description", desc),
                    "type": "ICD-10",
                    "conditions_matched": [condition_a, condition_b],
                    "suppresses_prefixes": [f"{pfx3}.9"],  # suppress generic same-family
                    "source": "dynamic_compound",
                    "confidence": 0.92,
                    "protected": True,
                })
                seen_codes.add(code)
                break  # first pattern match wins

        return compounds