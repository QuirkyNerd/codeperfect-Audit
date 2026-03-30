# services/group_config.py

MANDATORY_GROUPS = {

    # ─────────────────────────────────────────
    # ENDOCRINE / METABOLIC
    # ─────────────────────────────────────────
    "diabetes": {"code": "E11.9", "type": "ICD-10", "description": "Type 2 diabetes mellitus without complications"},
    "dm2": {"code": "E11.9", "type": "ICD-10", "description": "Type 2 diabetes mellitus"},
    "hyperglycemia": {"code": "R73.9", "type": "ICD-10", "description": "Hyperglycemia, unspecified"},
    "hypoglycemia": {"code": "E16.2", "type": "ICD-10", "description": "Hypoglycemia, unspecified"},
    "thyroid": {"code": "E07.9", "type": "ICD-10", "description": "Thyroid disorder, unspecified"},
    "hypothyroidism": {"code": "E03.9", "type": "ICD-10", "description": "Hypothyroidism, unspecified"},
    "hyperthyroidism": {"code": "E05.90", "type": "ICD-10", "description": "Thyrotoxicosis, unspecified"},
    "obesity": {"code": "E66.9", "type": "ICD-10", "description": "Obesity, unspecified"},
    "overweight": {"code": "E66.3", "type": "ICD-10", "description": "Overweight"},
    "metabolic syndrome": {"code": "E88.81", "type": "ICD-10", "description": "Metabolic syndrome"},
    "lipid": {"code": "E78.5", "type": "ICD-10", "description": "Hyperlipidemia, unspecified"},
    "hyperlipidemia": {"code": "E78.5", "type": "ICD-10", "description": "Hyperlipidemia, unspecified"},

    # ─────────────────────────────────────────
    # CARDIOVASCULAR
    # ─────────────────────────────────────────
    "hypertension": {"code": "I10", "type": "ICD-10", "description": "Essential hypertension"},
    "htn": {"code": "I10", "type": "ICD-10", "description": "Hypertension"},
    "heart failure": {"code": "I50.9", "type": "ICD-10", "description": "Heart failure, unspecified"},
    "chf": {"code": "I50.9", "type": "ICD-10", "description": "Congestive heart failure"},
    "coronary artery disease": {"code": "I25.10", "type": "ICD-10", "description": "CAD without angina"},
    "cad": {"code": "I25.10", "type": "ICD-10", "description": "Coronary artery disease"},
    "myocardial infarction": {"code": "I21.9", "type": "ICD-10", "description": "Acute myocardial infarction"},
    "arrhythmia": {"code": "I49.9", "type": "ICD-10", "description": "Cardiac arrhythmia, unspecified"},
    "atrial fibrillation": {"code": "I48.91", "type": "ICD-10", "description": "Atrial fibrillation"},
    "angina": {"code": "I20.9", "type": "ICD-10", "description": "Angina pectoris"},
    "cardiomyopathy": {"code": "I42.9", "type": "ICD-10", "description": "Cardiomyopathy, unspecified"},

    # ─────────────────────────────────────────
    # RENAL
    # ─────────────────────────────────────────
    "chronic kidney": {"code": "N18.9", "type": "ICD-10", "description": "CKD unspecified"},
    "ckd": {"code": "N18.9", "type": "ICD-10", "description": "Chronic kidney disease"},
    "acute kidney": {"code": "N17.9", "type": "ICD-10", "description": "Acute kidney failure"},
    "aki": {"code": "N17.9", "type": "ICD-10", "description": "Acute kidney injury"},
    "renal failure": {"code": "N19", "type": "ICD-10", "description": "Unspecified kidney failure"},
    "proteinuria": {"code": "R80.9", "type": "ICD-10", "description": "Proteinuria, unspecified"},

    # ─────────────────────────────────────────
    # RESPIRATORY
    # ─────────────────────────────────────────
    "copd": {"code": "J44.9", "type": "ICD-10", "description": "Chronic obstructive pulmonary disease"},
    "asthma": {"code": "J45.909", "type": "ICD-10", "description": "Asthma, unspecified"},
    "pneumonia": {"code": "J18.9", "type": "ICD-10", "description": "Pneumonia, unspecified"},
    "respiratory failure": {"code": "J96.90", "type": "ICD-10", "description": "Respiratory failure"},
    "bronchitis": {"code": "J20.9", "type": "ICD-10", "description": "Acute bronchitis"},
    "covid": {"code": "U07.1", "type": "ICD-10", "description": "COVID-19"},
    "tuberculosis": {"code": "A15.9", "type": "ICD-10", "description": "Pulmonary tuberculosis"},

    # ─────────────────────────────────────────
    # NEUROLOGY
    # ─────────────────────────────────────────
    "stroke": {"code": "I63.9", "type": "ICD-10", "description": "Cerebral infarction"},
    "cva": {"code": "I63.9", "type": "ICD-10", "description": "Stroke"},
    "seizure": {"code": "R56.9", "type": "ICD-10", "description": "Seizure, unspecified"},
    "epilepsy": {"code": "G40.909", "type": "ICD-10", "description": "Epilepsy"},
    "neuropathy": {"code": "G62.9", "type": "ICD-10", "description": "Polyneuropathy"},
    "parkinson": {"code": "G20", "type": "ICD-10", "description": "Parkinson disease"},
    "alzheimer": {"code": "G30.9", "type": "ICD-10", "description": "Alzheimer disease"},
    "dementia": {"code": "F03.90", "type": "ICD-10", "description": "Dementia"},

    # ─────────────────────────────────────────
    # GASTROINTESTINAL
    # ─────────────────────────────────────────
    "gerd": {"code": "K21.9", "type": "ICD-10", "description": "GERD"},
    "gastritis": {"code": "K29.70", "type": "ICD-10", "description": "Gastritis"},
    "ulcer": {"code": "K27.9", "type": "ICD-10", "description": "Peptic ulcer"},
    "hepatitis": {"code": "K75.9", "type": "ICD-10", "description": "Hepatitis"},
    "cirrhosis": {"code": "K74.60", "type": "ICD-10", "description": "Cirrhosis"},
    "cholecystitis": {"code": "K81.9", "type": "ICD-10", "description": "Cholecystitis"},
    "gallstones": {"code": "K80.20", "type": "ICD-10", "description": "Cholelithiasis"},
    "pancreatitis": {"code": "K85.9", "type": "ICD-10", "description": "Acute pancreatitis"},

    # ─────────────────────────────────────────
    # INFECTIONS / GENERAL
    # ─────────────────────────────────────────
    "sepsis": {"code": "A41.9", "type": "ICD-10", "description": "Sepsis"},
    "infection": {"code": "B99.9", "type": "ICD-10", "description": "Infection, unspecified"},
    "uti": {"code": "N39.0", "type": "ICD-10", "description": "Urinary tract infection"},
    "cellulitis": {"code": "L03.90", "type": "ICD-10", "description": "Cellulitis"},
    "abscess": {"code": "L02.91", "type": "ICD-10", "description": "Cutaneous abscess"},

    # ─────────────────────────────────────────
    # MUSCULOSKELETAL
    # ─────────────────────────────────────────
    "arthritis": {"code": "M19.90", "type": "ICD-10", "description": "Osteoarthritis"},
    "back pain": {"code": "M54.9", "type": "ICD-10", "description": "Back pain"},
    "fracture": {"code": "S52.90XA", "type": "ICD-10", "description": "Fracture unspecified"},
    "osteoporosis": {"code": "M81.0", "type": "ICD-10", "description": "Osteoporosis"},

    # ─────────────────────────────────────────
    # HEMATOLOGY
    # ─────────────────────────────────────────
    "anemia": {"code": "D64.9", "type": "ICD-10", "description": "Anemia"},
    "iron deficiency": {"code": "D50.9", "type": "ICD-10", "description": "Iron deficiency anemia"},
    "coagulopathy": {"code": "D68.9", "type": "ICD-10", "description": "Coagulation defect"},

    # ─────────────────────────────────────────
    # PSYCHIATRIC
    # ─────────────────────────────────────────
    "depression": {"code": "F32.9", "type": "ICD-10", "description": "Depression"},
    "anxiety": {"code": "F41.9", "type": "ICD-10", "description": "Anxiety disorder"},
    "bipolar": {"code": "F31.9", "type": "ICD-10", "description": "Bipolar disorder"},
    "schizophrenia": {"code": "F20.9", "type": "ICD-10", "description": "Schizophrenia"},

    # ─────────────────────────────────────────
    # GENERAL SYMPTOMS (fallback safety)
    # ─────────────────────────────────────────
    "pain": {"code": "R52", "type": "ICD-10", "description": "Pain, unspecified"},
    "fever": {"code": "R50.9", "type": "ICD-10", "description": "Fever"},
    "fatigue": {"code": "R53.83", "type": "ICD-10", "description": "Fatigue"},
    "nausea": {"code": "R11.0", "type": "ICD-10", "description": "Nausea"},
    "vomiting": {"code": "R11.10", "type": "ICD-10", "description": "Vomiting"},
}


CKD_ENTITY_SIGNALS: list[str] = [
    "chronic kidney", "ckd", "renal disease", "nephropathy",
    "kidney disease", "renal failure", "kidney failure",
]


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

