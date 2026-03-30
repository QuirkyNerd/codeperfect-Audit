# services/validation_rules.py
import re as _re

def clean_rag_description(raw: str) -> str:
    """Strip 'Code: XX | Description: ' noise from ChromaDB document text."""
    # Remove patterns like "Code: E11.9 | Description: " or "Code: E11.9 |"
    cleaned = _re.sub(r"(?i)code:\s*[A-Z0-9.]+\s*\|?\s*(?:description:)?\s*", "", raw)
    # Remove leading/trailing whitespace and pipes
    cleaned = cleaned.strip().strip("|").strip()
    return cleaned if cleaned else raw.strip()



CLINICAL_EXCLUSIVITY_RULES: list[dict] = [
    # ── TYPE 2 DIABETES → remove Type 1 (E10.*) and Other (E13.*) ──────────
    {
        "id": "DM_TYPE2_EXCLUSIVITY",
        "note_signals": ["type 2 diabetes", "t2dm", "dm2", "dm 2", "type ii diabetes"],
        "exclude_prefixes": ["E10", "E13", "E08", "E09"],
        "exclude_exact": [],
        "description": "Only E11.* allowed when Type 2 diabetes is confirmed",
    },
    # ── TYPE 1 DIABETES → remove Type 2 (E11.*) and Other (E13.*) ──────────
    {
        "id": "DM_TYPE1_EXCLUSIVITY",
        "note_signals": ["type 1 diabetes", "t1dm", "dm1", "type i diabetes"],
        "exclude_prefixes": ["E11", "E13", "E08", "E09"],
        "exclude_exact": [],
        "description": "Only E10.* allowed when Type 1 diabetes is confirmed",
    },
    # ── ESSENTIAL HYPERTENSION → remove secondary HTN (I15.*) ──────────────
    # (Only fires if note does NOT also say "secondary" or "renovascular" etc.)
    {
        "id": "HTN_ESSENTIAL_EXCLUSIVITY",
        "note_signals": ["hypertension", "htn", "high blood pressure"],
        "anti_signals": ["secondary hypertension", "renovascular", "renal hypertension",
                         "endocrine hypertension", "I15"],
        "exclude_prefixes": ["I15"],
        "exclude_exact": [],
        "description": "I15 (secondary HTN) blocked unless secondary HTN explicitly stated",
    },
    # ── NO METABOLIC SYNDROME MENTIONED → block E88.x cluttering ───────────
    {
        "id": "METABOLIC_NOISE_FILTER",
        "note_signals": ["*"],   # always active
        "anti_signals": ["metabolic syndrome", "e88", "metabolic disorder"],
        "exclude_prefixes": ["E88"],
        "exclude_exact": [],
        "description": "E88.x removed unless metabolic syndrome explicitly in note",
    },
]


HARD_REJECT_PREFIXES: dict[str, list[str]] = {
    "O":  ["pregnan", "obstetric", "maternal", "antepartum", "postpartum", "labour", "labor", "gestation", "trimester"],
    "V":  [],    # vehicle/external cause — never valid in a medical coding note
    "P":  ["neonat", "perinatal", "newborn", "premature", "infant"],
    "Q":  ["congenital", "malformation", "anomaly", "genetic"],
}


ALWAYS_REJECT_PREFIXES: set[str] = {"V"}


RENAL_SYNDROME_PREFIXES: set[str] = {
    "N01", "N02", "N03", "N04", "N05", "N06", "N07", "N08",
    "N25", "N26", "N27",
}


RELATIONSHIP_VALIDATION_RULES: list[dict] = [
    {
        "id": "HYPERTENSIVE_CKD",
        "target_prefixes": ["I12", "I13"],
        "required_entities": ["hypertension", "chronic kidney"],
        "description": "Hypertensive CKD requires mention of both HTN and CKD",
    },
    {
        "id": "HYPERTENSIVE_HEART_DISEASE",
        "target_prefixes": ["I11", "I13"],
        "required_entities": ["hypertension", "heart failure"],
        "description": "Hypertensive heart disease requires mention of both HTN and HF",
    }
]

