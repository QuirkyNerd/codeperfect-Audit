"""
services/clinical_rules_config.py — SPECIAL-CASE OVERRIDES ONLY (v2.0)

DESIGN PRINCIPLE:
  The SelectionEngine derives 90% of its rules AUTOMATICALLY from ICD-10 structure:
    - Prefix hierarchy: N18.32 automatically suppresses N18.3, N18. → group "N18"
    - Combination code dominance: compound codes auto-suppress their components
    - Auto-grouping: first 3 chars of ICD code = group key

  This file provides OVERRIDES for cases the auto-engine cannot infer:
    - Clinical exclusivity (E10.* must not appear when E11.x is confirmed)
    - Cross-prefix suppression (E11.42 suppresses G62.9 — different prefix families)
    - Explicit compound condition mappings (DM2 + neuropathy → E11.42)
    - Category hard-rejects (pregnancy codes when no pregnancy entity)
    - Known noise patterns (nephrotic syndrome leaking into CKD queries)

ADDING NEW RULES: just append to the appropriate section.
NO code changes to selection_engine.py are needed.
"""

from __future__ import annotations
import re as _re


# ─────────────────────────────────────────────────────────────────────────────
# UTILITY — clean RAG document text that leaks "Code: E109 | Description: ..."
# Call on the `doc` / description field from ChromaDB before presenting.
# ─────────────────────────────────────────────────────────────────────────────

def clean_rag_description(raw: str) -> str:
    """Strip 'Code: XX | Description: ' noise from ChromaDB document text."""
    # Remove patterns like "Code: E11.9 | Description: " or "Code: E11.9 |"
    cleaned = _re.sub(r"(?i)code:\s*[A-Z0-9.]+\s*\|?\s*(?:description:)?\s*", "", raw)
    # Remove leading/trailing whitespace and pipes
    cleaned = cleaned.strip().strip("|").strip()
    return cleaned if cleaned else raw.strip()



# ─────────────────────────────────────────────────────────────────────────────
# COMPOUND RULES — Declarative condition-pair → result code
# ─────────────────────────────────────────────────────────────────────────────
# Fields:
#   id:           unique identifier
#   entity_signals: any of these phrases must appear in note (normalized, case-insensitive)
#                   uses partial matching (e.g. "neuropath" matches "neuropathy"/"neuropathic")
#   entity_all:   ALL of these must be present (AND logic across entries)
#   trigger_prefixes: at least one code from these prefixes must be in candidate pool
#   result:       ICD-10 code to inject (goes into PROTECTED set)
#   result_desc:  human-readable description
#   result_group: group key for this result (= first 3 chars of result code normally)
#   priority:     higher = evaluated first (0-10)
#   eliminate_prefixes: remove ALL codes with these prefixes (unless protected)
#   eliminate_codes:    remove these exact codes (unless protected)

COMPOUND_RULES: list[dict] = [
    # ── DIABETES TYPE 2 COMPLICATIONS ────────────────────────────────────────

    {
        "id": "DM2_PERIPHERAL_NEUROPATHY",
        "entity_all": ["diabet", "neuropath"],         # "neuropathy", "neuropathic"
        "entity_signals": ["type 2", "t2dm", "dm2", "dm 2"],
        "trigger_prefixes": ["E11"],
        "result": "E11.42",
        "result_desc": "Type 2 diabetes mellitus with diabetic peripheral neuropathy, unspecified",
        "result_group": "E11",
        "priority": 10,
        "eliminate_prefixes": ["G57", "G58", "G59", "G60", "G61", "G62", "G63", "G64"],
        "eliminate_codes": ["E11.9", "E11.40", "E11.41", "E11.638", "E11.628", "E11.49", "E13.8"],
    },
    {
        "id": "DM2_MONONEUROPATHY",
        "entity_all": ["diabet", "mononeuropath"],
        "entity_signals": ["type 2", "t2dm", "dm2"],
        "trigger_prefixes": ["E11"],
        "result": "E11.41",
        "result_desc": "Type 2 diabetes mellitus with diabetic mononeuropathy",
        "result_group": "E11",
        "priority": 9,
        "eliminate_prefixes": ["G57", "G58"],
        "eliminate_codes": ["E11.9", "E11.40"],
    },
    {
        "id": "DM2_CKD",
        "entity_all": ["diabet", "chronic kidney"],
        "entity_signals": ["type 2", "t2dm", "dm2", "dm 2"],
        "trigger_prefixes": ["E11", "N18"],
        "result": "E11.22",
        "result_desc": "Type 2 diabetes mellitus with diabetic chronic kidney disease",
        "result_group": "E11",
        "priority": 8,
        "eliminate_prefixes": [],
        "eliminate_codes": ["E11.65", "E11.9"],
    },
    {
        "id": "DM2_NEPHROPATHY",
        "entity_all": ["diabet", "nephropath"],
        "entity_signals": ["type 2", "t2dm"],
        "trigger_prefixes": ["E11"],
        "result": "E11.21",
        "result_desc": "Type 2 diabetes mellitus with diabetic nephropathy",
        "result_group": "E11",
        "priority": 8,
        "eliminate_prefixes": [],
        "eliminate_codes": ["E11.9"],
    },
    {
        "id": "DM2_RETINOPATHY_BACKGROUND",
        "entity_all": ["diabet", "retinopathy"],
        "entity_signals": ["background", "mild", "moderate", "without macular"],
        "trigger_prefixes": ["E11"],
        "result": "E11.319",
        "result_desc": "Type 2 diabetes mellitus with unspecified diabetic retinopathy without macular edema",
        "result_group": "E11",
        "priority": 7,
        "eliminate_prefixes": [],
        "eliminate_codes": ["E11.9", "E11.31", "E11.39"],
    },
    {
        "id": "DM2_FOOT_ULCER",
        "entity_all": ["diabet", "foot ulcer"],
        "entity_signals": ["type 2", "t2dm"],
        "trigger_prefixes": ["E11"],
        "result": "E11.621",
        "result_desc": "Type 2 diabetes mellitus with foot ulcer",
        "result_group": "E11",
        "priority": 7,
        "eliminate_prefixes": [],
        "eliminate_codes": ["E11.9", "E11.62"],
    },

    # ── HEART FAILURE SUBTYPES ────────────────────────────────────────────────

    {
        "id": "HF_ACUTE_ON_CHRONIC_SYSTOLIC",
        "entity_all": ["acute on chronic systolic"],
        "entity_signals": ["heart failure", "cardiac failure"],
        "trigger_prefixes": ["I50"],
        "result": "I50.23",
        "result_desc": "Acute on chronic systolic (congestive) heart failure",
        "result_group": "I50",
        "priority": 10,
        "eliminate_prefixes": [],
        "eliminate_codes": ["I50.9", "I50.20", "I50.21", "I50.40", "I50.41", "I50.43"],
    },
    {
        "id": "HF_ACUTE_ON_CHRONIC_DIASTOLIC",
        "entity_all": ["acute on chronic diastolic"],
        "entity_signals": ["heart failure"],
        "trigger_prefixes": ["I50"],
        "result": "I50.33",
        "result_desc": "Acute on chronic diastolic (congestive) heart failure",
        "result_group": "I50",
        "priority": 10,
        "eliminate_prefixes": [],
        "eliminate_codes": ["I50.9", "I50.30", "I50.31", "I50.40", "I50.41"],
    },
    {
        "id": "HF_ACUTE_SYSTOLIC",
        "entity_all": ["acute systolic"],
        "entity_signals": ["heart failure"],
        "trigger_prefixes": ["I50"],
        "result": "I50.21",
        "result_desc": "Acute systolic (congestive) heart failure",
        "result_group": "I50",
        "priority": 9,
        "eliminate_prefixes": [],
        "eliminate_codes": ["I50.9", "I50.20", "I50.40", "I50.43"],
    },
    {
        "id": "HF_CHRONIC_SYSTOLIC",
        "entity_all": ["chronic systolic"],
        "entity_signals": ["heart failure"],
        "trigger_prefixes": ["I50"],
        "result": "I50.22",
        "result_desc": "Chronic systolic (congestive) heart failure",
        "result_group": "I50",
        "priority": 8,
        "eliminate_prefixes": [],
        "eliminate_codes": ["I50.9", "I50.20"],
    },

    # ── CKD STAGE-SPECIFIC ─────────────────────────────────────────────────────

    {
        "id": "CKD_STAGE_3B",
        "entity_all": ["stage 3b"],
        "entity_signals": ["chronic kidney", "ckd", "renal"],
        "trigger_prefixes": ["N18"],
        "result": "N18.32",
        "result_desc": "Chronic kidney disease, stage 3b",
        "result_group": "N18",
        "priority": 10,
        "eliminate_prefixes": ["N01", "N02", "N03", "N04", "N05", "N06", "N07", "N08", "N25", "N26", "N27"],
        "eliminate_codes": ["N18.9", "N18.30", "N18.3", "N18.31"],
    },
    {
        "id": "CKD_STAGE_3A",
        "entity_all": ["stage 3a"],
        "entity_signals": ["chronic kidney", "ckd", "renal"],
        "trigger_prefixes": ["N18"],
        "result": "N18.31",
        "result_desc": "Chronic kidney disease, stage 3a",
        "result_group": "N18",
        "priority": 10,
        "eliminate_prefixes": ["N01", "N02", "N03", "N04", "N05", "N06", "N07", "N08", "N25", "N26", "N27"],
        "eliminate_codes": ["N18.9", "N18.30", "N18.3", "N18.32"],
    },
    {
        "id": "CKD_STAGE_3",
        "entity_all": ["stage 3"],
        "entity_signals": ["chronic kidney", "ckd", "renal"],
        "trigger_prefixes": ["N18"],
        "result": "N18.3",
        "result_desc": "Chronic kidney disease, stage 3 unspecified",
        "result_group": "N18",
        "priority": 9,
        "eliminate_prefixes": ["N01", "N02", "N03", "N04", "N05", "N06", "N07", "N08", "N25", "N26", "N27"],
        "eliminate_codes": ["N18.9", "N18.30"],
    },
    {
        "id": "CKD_STAGE_4",
        "entity_all": ["stage 4"],
        "entity_signals": ["chronic kidney", "ckd"],
        "trigger_prefixes": ["N18"],
        "result": "N18.4",
        "result_desc": "Chronic kidney disease, stage 4",
        "result_group": "N18",
        "priority": 9,
        "eliminate_prefixes": ["N01", "N02", "N03", "N04", "N05", "N06", "N07", "N08", "N25", "N26", "N27"],
        "eliminate_codes": ["N18.9", "N18.3"],
    },
    {
        "id": "CKD_STAGE_5_ESRD",
        "entity_all": ["esrd"],
        "entity_signals": ["end stage renal", "end-stage renal", "stage 5"],
        "trigger_prefixes": ["N18"],
        "result": "N18.6",
        "result_desc": "End stage renal disease",
        "result_group": "N18",
        "priority": 10,
        "eliminate_prefixes": ["N01", "N02", "N03", "N04", "N05", "N06", "N07", "N08", "N25", "N26", "N27"],
        "eliminate_codes": ["N18.9", "N18.3", "N18.4", "N18.5"],
    },

    # ── HYPERTENSION COMPLICATIONS ────────────────────────────────────────────

    {
        "id": "HTN_WITH_HEART_FAILURE",
        "entity_all": ["hypertension", "heart failure"],
        "entity_signals": ["hypertensive"],
        "trigger_prefixes": ["I11", "I50"],
        "result": "I11.0",
        "result_desc": "Hypertensive heart disease with heart failure",
        "result_group": "I11",
        "priority": 8,
        "eliminate_prefixes": [],
        "eliminate_codes": ["I11.9"],
    },
    {
        "id": "HTN_WITH_CKD",
        "entity_all": ["hypertension", "chronic kidney"],
        "entity_signals": ["hypertensive"],
        "trigger_prefixes": ["I12", "N18"],
        "result": "I12.9",
        "result_desc": "Hypertensive chronic kidney disease with stage 1-4 or unspecified CKD",
        "result_group": "I12",
        "priority": 7,
        "eliminate_prefixes": [],
        "eliminate_codes": ["I10"],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# CLINICAL EXCLUSIVITY RULES (NEW — FIX 1)
# When a specific diabetes type or condition is confirmed, certain code prefixes
# are COMPLETELY EXCLUDED, regardless of RAG or scoring results.
#
# Format:
#   note_signals:  ANY of these phrases in note → rule fires (partial match)
#   exclude_prefixes: remove ALL codes starting with these 3-char prefixes
#   exclude_exact:    also remove these exact codes
#   protect_prefixes: these prefixes are ALLOWED (whitelist) — optional
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# CROSS-PREFIX SUPPRESSION OVERRIDES (UPDATED — FIX 2: supports prefix wildcards)
#
# Format: {trigger_code_or_prefix: ["P:G62", "EXACT:G62.9", ...]}
#   "P:XYZ"      = remove ALL codes with 3-char prefix XYZ
#   "EXACT:X.YZ" = remove only this exact code
#   bare string  = treated as EXACT (backward compat)
# ─────────────────────────────────────────────────────────────────────────────

CROSS_PREFIX_SUPPRESS: dict[str, list[str]] = {
    # Diabetic neuropathy compound code → suppress ALL standalone neuropathy families
    "E11.42": ["P:G57", "P:G58", "P:G59", "P:G60", "P:G61", "P:G62", "P:G63", "P:G64"],
    "E11.41": ["P:G57", "P:G56"],
    # Diabetic retinopathy → suppress standalone retinal codes
    "E11.319": ["EXACT:H35.00"],
    "E11.3519": ["EXACT:H35.31"],
    # Diabetic CKD → suppress general CKD unspecified
    "E11.22": ["EXACT:N18.9"],
    # Hypertensive CKD → suppress plain essential hypertension (already have I12.x)
    "I12.9":  ["EXACT:I10"],
    "I13.0":  ["EXACT:I10", "EXACT:I11.9", "EXACT:I50.9"],
    "I13.2":  ["EXACT:I10", "EXACT:I11.9", "EXACT:I50.9"],
    "I11.0":  ["EXACT:I10"],
}

# ─────────────────────────────────────────────────────────────────────────────
# CROSS-HIERARCHY SUPPRESSION ENGINE (NEW — V8 FIX 1)
# ─────────────────────────────────────────────────────────────────────────────

HIERARCHY_SUPPRESSION: dict[str, list[str]] = {
    "E11.42": ["G62", "G60", "G61", "G56"],
    "E11.40": ["G62", "G60", "G61", "G56"],
    "E11.22": ["N18"],
    "I12": ["I10", "N18"],
    "I13": ["I10", "I11", "I12", "I50", "N18"]
}

# ─────────────────────────────────────────────────────────────────────────────
# MANDATORY GROUPS COMPLETENESS (NEW — V8 FIX 6)
# ─────────────────────────────────────────────────────────────────────────────

MANDATORY_GROUPS = {
    "diabetes":          {"code": "E11.9", "desc": "Type 2 diabetes mellitus without complications"},
    "hypertension":      {"code": "I10", "desc": "Essential (primary) hypertension"},
    "chronic kidney":    {"code": "N18.9", "desc": "Chronic kidney disease, unspecified"},
    "ckd":               {"code": "N18.9", "desc": "Chronic kidney disease, unspecified"},
    "heart failure":     {"code": "I50.9", "desc": "Heart failure, unspecified"},
    "neuropathy":        {"code": "G62.9", "desc": "Polyneuropathy, unspecified"},
    "obesity":           {"code": "E66.9", "desc": "Obesity, unspecified"},
    "lipid":             {"code": "E78.5", "desc": "Hyperlipidemia, unspecified"}
}


# ─────────────────────────────────────────────────────────────────────────────
# HARD-REJECT CATEGORIES
# Codes starting with these prefixes are rejected UNLESS the note contains
# one of the required keywords. Empty list = reject always (unless det_set).
# ─────────────────────────────────────────────────────────────────────────────

HARD_REJECT_PREFIXES: dict[str, list[str]] = {
    "O":  ["pregnan", "obstetric", "maternal", "antepartum", "postpartum", "labour", "labor", "gestation", "trimester"],
    "V":  [],    # vehicle/external cause — never valid in a medical coding note
    "P":  ["neonat", "perinatal", "newborn", "premature", "infant"],
    "Q":  ["congenital", "malformation", "anomaly", "genetic"],
}

# These are always rejected unless explicitly in det_set (even if keyword present)
ALWAYS_REJECT_PREFIXES: set[str] = {"V"}

# N01–N08, N25–N27 are nephrotic/nephritic syndrome codes that leak into
# CKD RAG results. Rejected when CKD is the primary entity.
RENAL_SYNDROME_PREFIXES: set[str] = {
    "N01", "N02", "N03", "N04", "N05", "N06", "N07", "N08",
    "N25", "N26", "N27",
}

CKD_ENTITY_SIGNALS: list[str] = [
    "chronic kidney", "ckd", "renal disease", "nephropathy",
    "kidney disease", "renal failure", "kidney failure",
]


# ─────────────────────────────────────────────────────────────────────────────
# ENTITY-TO-PREFIX COVERAGE MAP
# Maps normalized entity keywords to allowed ICD-10 3-char prefixes.
# Used to validate that RAG-only codes map to something mentioned in the note.
# Auto-derived hierarchy covers same-prefix; this covers cross-prefix alignment.
# ─────────────────────────────────────────────────────────────────────────────

ENTITY_PREFIX_MAP: dict[str, list[str]] = {
    # Diabetes
    "diabet": ["E10", "E11", "E13", "E08", "E09"],
    "dm2": ["E11"], "dm1": ["E10"],
    "t2dm": ["E11"], "t1dm": ["E10"],
    # CKD / Renal
    "chronic kidney": ["N18"],
    "ckd": ["N18"],
    "renal failure": ["N18", "N17", "N19"],
    "kidney disease": ["N18", "N17"],
    "nephropathy": ["N18", "E11", "E10"],
    "aki": ["N17"],
    # Heart
    "heart failure": ["I50"],
    "cardiac failure": ["I50"],
    "heart attack": ["I21"], "ami": ["I21"],
    "myocardial infarct": ["I21", "I22"],
    "stemi": ["I21"], "nstemi": ["I21"],
    "cad": ["I25"], "coronary": ["I25"],
    "angina": ["I20"],
    "atrial fibrillation": ["I48"], "afib": ["I48"], "a-fib": ["I48"],
    # Hypertension
    "hypertension": ["I10", "I11", "I12", "I13"],
    "htn": ["I10", "I11", "I12", "I13"],
    "high blood pressure": ["I10"],
    # Neuropathy (standalone — valid only without diabetes context)
    "neuropath": ["G60", "G61", "G62", "G63", "E11", "E10"],
    "peripheral neuropath": ["G62", "E11"],
    # Obesity / Metabolic
    "obesi": ["E66"],
    "overweight": ["E66"], "bmi": ["Z68"],
    "hyperlipid": ["E78"], "dyslipid": ["E78"],
    "cholesterol": ["E78"], "triglyc": ["E78"],
    "gout": ["M10"], "hyperuricemia": ["E79"],
    # Liver
    "cirrhosis": ["K74"], "hepatitis": ["K72", "B18", "B19"],
    "fatty liver": ["K76"], "nash": ["K75"],
    # Lung / Respiratory
    "copd": ["J44"], "emphysema": ["J43"],
    "asthma": ["J45"], "bronchospasm": ["J45"],
    "pneumonia": ["J18", "J15", "J13"],
    "respiratory failure": ["J96"],
    "pulmonary embolism": ["I26"], "pe": ["I26"],
    "dvt": ["I82"], "deep vein thrombosis": ["I82"],
    # Sepsis
    "sepsis": ["A41", "A40"],
    "bacteremia": ["A41"],
    # Anemia
    "anemia": ["D50", "D51", "D63", "D64"],
    "iron deficiency": ["D50"],
    # Stroke
    "stroke": ["I63", "I64"], "cerebral infarct": ["I63"],
    "tia": ["G45"],
    # GI
    "cholelith": ["K80"], "gallstone": ["K80"],
    "cholecystitis": ["K81"],
    "appendicitis": ["K37"],
    "pancreatitis": ["K85", "K86"],
    # Skin
    "cellulitis": ["L03"],
    "pressure ulcer": ["L89"],
    # MSK
    "back pain": ["M54"], "lumbalgia": ["M54"],
    "arthritis": ["M05", "M06", "M15", "M16", "M17"],
    "osteoporosis": ["M80", "M81"],
    "fracture": ["S", "M80"],
    "fall": ["W"],
    # Mental
    "depression": ["F32", "F33"],
    "anxiety": ["F41"],
    "bipolar": ["F31"],
    "schizophrenia": ["F20"],
    # Oncology (generic)
    "cancer": ["C"],
    "malignant": ["C"],
    "tumor": ["C", "D"],
    "neoplasm": ["C", "D"],
    # Pediatric
    "dehydration": ["E86"],
    "electrolyte": ["E87"],
    # Procedures (CPT — entity validation bypassed for CPT codes)
}

# ─────────────────────────────────────────────────────────────────────────────
# RELATIONSHIP VALIDATION RULES (NEW — FIX 2)
# Ensure combination codes only appear when all underlying conditions are present.
# ─────────────────────────────────────────────────────────────────────────────

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
