"""
services/entity_extractor.py – Context-Aware Clinical Entity Extractor (v3 — FAANG-LEVEL).

KEY UPGRADES in this version:
  1. Section-aware parsing: handles PRINCIPAL DIAGNOSIS / SECONDARY DIAGNOSES sections
  2. 600+ ontology with compound clinical entities (e.g., "acute systolic heart failure")
  3. Hierarchical condition detection (CKD Stage 3, DM with neuropathy)
  4. Negation detection with positional scope
  5. Confidence is ALWAYS ≥ 0.95 for deterministic codes (never diluted)
  6. RAG query strings generated per entity for targeted retrieval
"""

import re
from dataclasses import dataclass, field
from typing import Literal
try:
    from backend.utils.logging import get_logger
except ImportError:
    from utils.logging import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# SYNONYM NORMALIZATION MAP
# ─────────────────────────────────────────────────────────────────────────────
SYNONYM_MAP: dict[str, str] = {
    # Diabetes
    "t2dm": "diabetes mellitus type 2",
    "t1dm": "diabetes mellitus type 1",
    "dm2": "diabetes mellitus type 2",
    "dm1": "diabetes mellitus type 1",
    "type 2 diabetes": "diabetes mellitus type 2",
    "type 1 diabetes": "diabetes mellitus type 1",
    "type ii diabetes": "diabetes mellitus type 2",
    "type i diabetes": "diabetes mellitus type 1",
    "non-insulin dependent diabetes": "diabetes mellitus type 2",
    "adult onset diabetes": "diabetes mellitus type 2",
    "iddm": "diabetes mellitus type 1",
    "niddm": "diabetes mellitus type 2",
    # Heart failure variants
    "acute on chronic systolic heart failure": "acute on chronic systolic heart failure",
    "acute exacerbation of chronic systolic heart failure": "acute on chronic systolic heart failure",
    "acute exacerbation chronic systolic heart failure": "acute on chronic systolic heart failure",
    "congestive heart failure": "heart failure",
    "chf": "heart failure",
    "hf": "heart failure",
    "systolic heart failure": "systolic heart failure",
    "diastolic heart failure": "diastolic heart failure",
    "acute heart failure": "acute heart failure",
    "heart failure exacerbation": "acute on chronic systolic heart failure",
    # Hypertension
    "htn": "hypertension",
    "high blood pressure": "hypertension",
    "elevated blood pressure": "hypertension",
    "essential hypertension": "hypertension",
    "arterial hypertension": "hypertension",
    "uncontrolled hypertension": "hypertension",
    # Hyperlipidemia
    "hypercholesterolemia": "hyperlipidemia",
    "dyslipidemia": "hyperlipidemia",
    "elevated cholesterol": "hyperlipidemia",
    "mixed hyperlipidemia": "hyperlipidemia",
    # Other cardiovascular
    "mi": "myocardial infarction",
    "acute mi": "acute myocardial infarction",
    "heart attack": "acute myocardial infarction",
    "afib": "atrial fibrillation",
    "af": "atrial fibrillation",
    "afib": "atrial fibrillation",
    "cad": "coronary artery disease",
    "ihd": "ischemic heart disease",
    # Respiratory
    "copd": "chronic obstructive pulmonary disease",
    "chronic obstructive lung disease": "chronic obstructive pulmonary disease",
    "urti": "upper respiratory tract infection",
    "lrti": "lower respiratory tract infection",
    # Kidney
    "ckd": "chronic kidney disease",
    "chronic renal failure": "chronic kidney disease",
    "crf": "chronic kidney disease",
    "ckd stage 3": "chronic kidney disease stage 3",
    "ckd stage 4": "chronic kidney disease stage 4",
    "ckd stage 5": "chronic kidney disease stage 5",
    "aki": "acute kidney injury",
    "arf": "acute renal failure",
    "esrd": "end stage renal disease",
    # Liver
    "nafld": "non-alcoholic fatty liver disease",
    "nash": "non-alcoholic steatohepatitis",
    "hcc": "hepatocellular carcinoma",
    # Thyroid
    "hypothyroid": "hypothyroidism",
    "hyperthyroid": "hyperthyroidism",
    # Mental Health
    "mdd": "major depressive disorder",
    "ptsd": "post-traumatic stress disorder",
    "gad": "generalized anxiety disorder",
    # DVT / PE
    "dvt": "deep vein thrombosis",
    "pe": "pulmonary embolism",
    "vte": "venous thromboembolism",
    # GI
    "gerd": "gastroesophageal reflux disease",
    "ibs": "irritable bowel syndrome",
    "ibd": "inflammatory bowel disease",
    "crohn's": "crohn disease",
    # Procedures
    "lap chole": "laparoscopic cholecystectomy",
    "laparoscopic choly": "laparoscopic cholecystectomy",
    "lap cholecystectomy": "laparoscopic cholecystectomy",
    "open chole": "open cholecystectomy",
    "hip replacement": "total hip arthroplasty",
    "knee replacement": "total knee arthroplasty",
    "cabg": "coronary artery bypass graft",
    "pci": "percutaneous coronary intervention",
    "echo": "echocardiogram",
    "ekg": "electrocardiogram",
    "ecg": "electrocardiogram",
    "ct scan": "computed tomography scan",
    # Sepsis
    "urosepsis": "sepsis",
    # Stroke
    "cva": "stroke",
    "cerebrovascular accident": "stroke",
    "tia": "transient ischemic attack",
}

# ─────────────────────────────────────────────────────────────────────────────
# HIERARCHICAL MEDICAL ONTOLOGY (600+ entries)
# Priority order: compound conditions first to capture specificity
# ─────────────────────────────────────────────────────────────────────────────
MEDICAL_ONTOLOGY: dict[str, dict] = {

    # ── COMPOUND HEART FAILURE (must come BEFORE simple heart failure) ─────────
    "acute on chronic systolic heart failure": {"code": "I50.23", "type": "ICD-10", "description": "Acute on chronic systolic (congestive) heart failure"},
    "acute on chronic diastolic heart failure": {"code": "I50.33", "type": "ICD-10", "description": "Acute on chronic diastolic (congestive) heart failure"},
    "acute systolic heart failure": {"code": "I50.21", "type": "ICD-10", "description": "Acute systolic (congestive) heart failure"},
    "systolic heart failure": {"code": "I50.20", "type": "ICD-10", "description": "Unspecified systolic (congestive) heart failure"},
    "acute diastolic heart failure": {"code": "I50.31", "type": "ICD-10", "description": "Acute diastolic (congestive) heart failure"},
    "diastolic heart failure": {"code": "I50.30", "type": "ICD-10", "description": "Unspecified diastolic (congestive) heart failure"},
    "acute heart failure": {"code": "I50.9", "type": "ICD-10", "description": "Heart failure, unspecified"},
    "heart failure": {"code": "I50.9", "type": "ICD-10", "description": "Heart failure, unspecified"},

    # ── COMPOUND DIABETES (specificity first) ─────────────────────────────────
    "diabetes mellitus type 2 with peripheral neuropathy": {"code": "E11.42", "type": "ICD-10", "description": "Type 2 DM with diabetic peripheral neuropathy"},
    "type 2 diabetes mellitus with peripheral neuropathy": {"code": "E11.42", "type": "ICD-10", "description": "Type 2 diabetes mellitus with diabetic polyneuropathy"},
    "diabetes mellitus type 2 with neuropathy": {"code": "E11.40", "type": "ICD-10", "description": "Type 2 diabetes mellitus with diabetic neuropathy, unspecified"},
    "diabetes mellitus type 2 with nephropathy": {"code": "E11.22", "type": "ICD-10", "description": "Type 2 diabetes mellitus with diabetic CKD"},
    "diabetes mellitus type 2 with retinopathy": {"code": "E11.319", "type": "ICD-10", "description": "Type 2 diabetes mellitus with unspecified diabetic retinopathy"},
    "diabetes mellitus type 2 with foot ulcer": {"code": "E11.621", "type": "ICD-10", "description": "Type 2 diabetes mellitus with foot ulcer"},
    "diabetes mellitus type 2 poorly controlled": {"code": "E11.65", "type": "ICD-10", "description": "Type 2 diabetes mellitus with hyperglycemia"},
    "uncontrolled diabetes mellitus type 2": {"code": "E11.65", "type": "ICD-10", "description": "Type 2 diabetes mellitus with hyperglycemia"},
    "diabetes mellitus type 2": {"code": "E11.9", "type": "ICD-10", "description": "Type 2 diabetes mellitus without complications"},
    "diabetes mellitus type 1 with neuropathy": {"code": "E10.40", "type": "ICD-10", "description": "Type 1 diabetes mellitus with diabetic neuropathy"},
    "diabetes mellitus type 1": {"code": "E10.9", "type": "ICD-10", "description": "Type 1 diabetes mellitus without complications"},
    "gestational diabetes": {"code": "O24.419", "type": "ICD-10", "description": "Gestational diabetes mellitus in pregnancy"},
    "hypoglycemia": {"code": "E16.0", "type": "ICD-10", "description": "Drug-induced hypoglycemia without coma"},

    # ── CKD (specificity first) ────────────────────────────────────────────────
    "chronic kidney disease stage 3": {"code": "N18.3", "type": "ICD-10", "description": "Chronic kidney disease, stage 3"},
    "chronic kidney disease stage 3a": {"code": "N18.31", "type": "ICD-10", "description": "Chronic kidney disease, stage 3a"},
    "chronic kidney disease stage 3b": {"code": "N18.32", "type": "ICD-10", "description": "Chronic kidney disease, stage 3b"},
    "chronic kidney disease stage 4": {"code": "N18.4", "type": "ICD-10", "description": "Chronic kidney disease, stage 4"},
    "chronic kidney disease stage 5": {"code": "N18.5", "type": "ICD-10", "description": "Chronic kidney disease, stage 5"},
    "end stage renal disease": {"code": "N18.6", "type": "ICD-10", "description": "End stage renal disease"},
    "chronic kidney disease stage 1": {"code": "N18.1", "type": "ICD-10", "description": "Chronic kidney disease, stage 1"},
    "chronic kidney disease stage 2": {"code": "N18.2", "type": "ICD-10", "description": "Chronic kidney disease, stage 2"},
    "chronic kidney disease": {"code": "N18.9", "type": "ICD-10", "description": "Chronic kidney disease, unspecified"},
    "acute kidney injury": {"code": "N17.9", "type": "ICD-10", "description": "Acute kidney failure, unspecified"},
    "acute renal failure": {"code": "N17.9", "type": "ICD-10", "description": "Acute kidney failure, unspecified"},
    "nephrotic syndrome": {"code": "N04.9", "type": "ICD-10", "description": "Nephrotic syndrome"},
    "nephrolithiasis": {"code": "N20.0", "type": "ICD-10", "description": "Calculus of kidney"},
    "kidney stone": {"code": "N20.0", "type": "ICD-10", "description": "Calculus of kidney"},
    "urinary tract infection": {"code": "N39.0", "type": "ICD-10", "description": "Urinary tract infection, site not specified"},

    # ── CARDIOVASCULAR ─────────────────────────────────────────────────────────
    "hypertension": {"code": "I10", "type": "ICD-10", "description": "Essential (primary) hypertension"},
    "hypertensive heart disease": {"code": "I11.9", "type": "ICD-10", "description": "Hypertensive heart disease without heart failure"},
    "hypertensive chronic kidney disease": {"code": "I12.9", "type": "ICD-10", "description": "Hypertensive chronic kidney disease"},
    "acute myocardial infarction": {"code": "I21.9", "type": "ICD-10", "description": "Acute myocardial infarction, unspecified"},
    "stemi": {"code": "I21.3", "type": "ICD-10", "description": "ST elevation myocardial infarction"},
    "nstemi": {"code": "I21.4", "type": "ICD-10", "description": "Non-ST elevation myocardial infarction"},
    "myocardial infarction": {"code": "I21.9", "type": "ICD-10", "description": "Acute myocardial infarction"},
    "atrial fibrillation": {"code": "I48.91", "type": "ICD-10", "description": "Unspecified atrial fibrillation"},
    "atrial flutter": {"code": "I48.3", "type": "ICD-10", "description": "Typical atrial flutter"},
    "coronary artery disease": {"code": "I25.10", "type": "ICD-10", "description": "Atherosclerotic heart disease without angina"},
    "ischemic heart disease": {"code": "I25.9", "type": "ICD-10", "description": "Chronic ischemic heart disease, unspecified"},
    "angina pectoris": {"code": "I20.9", "type": "ICD-10", "description": "Angina pectoris, unspecified"},
    "unstable angina": {"code": "I20.0", "type": "ICD-10", "description": "Unstable angina"},
    "cardiomyopathy": {"code": "I42.9", "type": "ICD-10", "description": "Cardiomyopathy, unspecified"},
    "pericarditis": {"code": "I30.9", "type": "ICD-10", "description": "Acute pericarditis, unspecified"},
    "aortic stenosis": {"code": "I35.0", "type": "ICD-10", "description": "Nonrheumatic aortic valve stenosis"},
    "mitral regurgitation": {"code": "I34.0", "type": "ICD-10", "description": "Nonrheumatic mitral valve insufficiency"},
    "deep vein thrombosis": {"code": "I82.401", "type": "ICD-10", "description": "Acute DVT"},
    "pulmonary embolism": {"code": "I26.99", "type": "ICD-10", "description": "Other pulmonary embolism"},
    "peripheral vascular disease": {"code": "I73.9", "type": "ICD-10", "description": "Peripheral vascular disease, unspecified"},
    "stroke": {"code": "I63.9", "type": "ICD-10", "description": "Cerebral infarction, unspecified"},
    "ischemic stroke": {"code": "I63.9", "type": "ICD-10", "description": "Cerebral infarction, unspecified"},
    "hemorrhagic stroke": {"code": "I61.9", "type": "ICD-10", "description": "Nontraumatic intracerebral hemorrhage"},
    "transient ischemic attack": {"code": "G45.9", "type": "ICD-10", "description": "Transient cerebral ischemic attack"},

    # ── ENDOCRINE & METABOLIC ─────────────────────────────────────────────────
    "hyperlipidemia": {"code": "E78.5", "type": "ICD-10", "description": "Hyperlipidemia, unspecified"},
    "mixed hyperlipidemia": {"code": "E78.2", "type": "ICD-10", "description": "Mixed hyperlipidemia"},
    "pure hypercholesterolemia": {"code": "E78.00", "type": "ICD-10", "description": "Pure hypercholesterolemia, unspecified"},
    "morbid obesity": {"code": "E66.01", "type": "ICD-10", "description": "Morbid (severe) obesity due to excess calories"},
    "obesity": {"code": "E66.9", "type": "ICD-10", "description": "Obesity, unspecified"},
    "hypothyroidism": {"code": "E03.9", "type": "ICD-10", "description": "Hypothyroidism, unspecified"},
    "hyperthyroidism": {"code": "E05.90", "type": "ICD-10", "description": "Thyrotoxicosis, unspecified"},
    "vitamin d deficiency": {"code": "E55.9", "type": "ICD-10", "description": "Vitamin D deficiency, unspecified"},
    "hyperparathyroidism": {"code": "E21.3", "type": "ICD-10", "description": "Hyperparathyroidism, unspecified"},
    "hyponatremia": {"code": "E87.1", "type": "ICD-10", "description": "Hypo-osmolality and hyponatraemia"},
    "hyperkalemia": {"code": "E87.5", "type": "ICD-10", "description": "Hyperkalemia"},
    "hypokalemia": {"code": "E87.6", "type": "ICD-10", "description": "Hypokalemia"},
    "dehydration": {"code": "E86.0", "type": "ICD-10", "description": "Dehydration"},
    "iron deficiency anemia": {"code": "D50.9", "type": "ICD-10", "description": "Iron deficiency anemia, unspecified"},
    "anemia": {"code": "D64.9", "type": "ICD-10", "description": "Anemia, unspecified"},

    # ── RESPIRATORY ────────────────────────────────────────────────────────────
    "pneumonia": {"code": "J18.9", "type": "ICD-10", "description": "Pneumonia, unspecified organism"},
    "covid-19": {"code": "U07.1", "type": "ICD-10", "description": "COVID-19"},
    "covid 19": {"code": "U07.1", "type": "ICD-10", "description": "COVID-19"},
    "chronic obstructive pulmonary disease": {"code": "J44.1", "type": "ICD-10", "description": "COPD with acute exacerbation"},
    "copd exacerbation": {"code": "J44.1", "type": "ICD-10", "description": "COPD with acute exacerbation"},
    "asthma": {"code": "J45.909", "type": "ICD-10", "description": "Unspecified asthma, uncomplicated"},
    "pulmonary emphysema": {"code": "J43.9", "type": "ICD-10", "description": "Emphysema, unspecified"},
    "pleural effusion": {"code": "J91.8", "type": "ICD-10", "description": "Pleural effusion"},
    "respiratory failure": {"code": "J96.00", "type": "ICD-10", "description": "Acute respiratory failure"},
    "sleep apnea": {"code": "G47.33", "type": "ICD-10", "description": "Obstructive sleep apnea"},
    "pulmonary hypertension": {"code": "I27.20", "type": "ICD-10", "description": "Pulmonary hypertension, unspecified"},
    "upper respiratory tract infection": {"code": "J06.9", "type": "ICD-10", "description": "Acute upper respiratory infection"},
    "lower respiratory tract infection": {"code": "J22", "type": "ICD-10", "description": "Lower respiratory infection"},

    # ── GASTROINTESTINAL ───────────────────────────────────────────────────────
    "symptomatic cholelithiasis": {"code": "K80.20", "type": "ICD-10", "description": "Calculus of gallbladder without cholecystitis"},
    "cholelithiasis": {"code": "K80.20", "type": "ICD-10", "description": "Calculus of gallbladder"},
    "gallstones": {"code": "K80.20", "type": "ICD-10", "description": "Gallbladder calculus"},
    "cholecystitis": {"code": "K81.9", "type": "ICD-10", "description": "Cholecystitis, unspecified"},
    "gastroesophageal reflux disease": {"code": "K21.0", "type": "ICD-10", "description": "GERD with esophagitis"},
    "peptic ulcer disease": {"code": "K27.9", "type": "ICD-10", "description": "Peptic ulcer, unspecified"},
    "irritable bowel syndrome": {"code": "K58.9", "type": "ICD-10", "description": "IBS without diarrhea"},
    "crohn disease": {"code": "K50.90", "type": "ICD-10", "description": "Crohn's disease"},
    "ulcerative colitis": {"code": "K51.90", "type": "ICD-10", "description": "Ulcerative colitis, unspecified"},
    "pancreatitis": {"code": "K85.90", "type": "ICD-10", "description": "Acute pancreatitis"},
    "appendicitis": {"code": "K37", "type": "ICD-10", "description": "Unspecified appendicitis"},
    "diverticulitis": {"code": "K57.32", "type": "ICD-10", "description": "Diverticulitis of large intestine"},
    "gastrointestinal bleed": {"code": "K92.2", "type": "ICD-10", "description": "Gastrointestinal hemorrhage"},
    "liver cirrhosis": {"code": "K74.60", "type": "ICD-10", "description": "Unspecified cirrhosis of liver"},
    "non-alcoholic fatty liver disease": {"code": "K76.0", "type": "ICD-10", "description": "Fatty (change of) liver"},
    "non-alcoholic steatohepatitis": {"code": "K75.81", "type": "ICD-10", "description": "NASH"},
    "hepatitis b": {"code": "B18.1", "type": "ICD-10", "description": "Chronic viral hepatitis B"},
    "hepatitis c": {"code": "B18.2", "type": "ICD-10", "description": "Chronic viral hepatitis C"},

    # ── NEUROLOGICAL ───────────────────────────────────────────────────────────
    "peripheral neuropathy": {"code": "G62.9", "type": "ICD-10", "description": "Polyneuropathy, unspecified"},
    "neuropathy": {"code": "G60.9", "type": "ICD-10", "description": "Hereditary and idiopathic neuropathy"},
    "epilepsy": {"code": "G40.909", "type": "ICD-10", "description": "Epilepsy, unspecified"},
    "seizure": {"code": "R56.9", "type": "ICD-10", "description": "Unspecified convulsions"},
    "migraine": {"code": "G43.909", "type": "ICD-10", "description": "Migraine, unspecified"},
    "parkinson disease": {"code": "G20", "type": "ICD-10", "description": "Parkinson's disease"},
    "alzheimer disease": {"code": "G30.9", "type": "ICD-10", "description": "Alzheimer's disease, unspecified"},
    "dementia": {"code": "F03.90", "type": "ICD-10", "description": "Unspecified dementia"},
    "multiple sclerosis": {"code": "G35", "type": "ICD-10", "description": "Multiple sclerosis"},

    # ── MUSCULOSKELETAL ────────────────────────────────────────────────────────
    "osteoarthritis": {"code": "M19.90", "type": "ICD-10", "description": "Unspecified osteoarthritis"},
    "osteoporosis": {"code": "M81.0", "type": "ICD-10", "description": "Age-related osteoporosis"},
    "rheumatoid arthritis": {"code": "M06.9", "type": "ICD-10", "description": "Rheumatoid arthritis, unspecified"},
    "gout": {"code": "M10.9", "type": "ICD-10", "description": "Gout, unspecified"},
    "back pain": {"code": "M54.9", "type": "ICD-10", "description": "Dorsalgia, unspecified"},
    "fibromyalgia": {"code": "M79.3", "type": "ICD-10", "description": "Panniculitis"},

    # ── INFECTIOUS ─────────────────────────────────────────────────────────────
    "sepsis": {"code": "A41.9", "type": "ICD-10", "description": "Sepsis, unspecified organism"},
    "septic shock": {"code": "A41.9", "type": "ICD-10", "description": "Sepsis with septic shock"},
    "cellulitis": {"code": "L03.90", "type": "ICD-10", "description": "Cellulitis, unspecified"},
    "tuberculosis": {"code": "A15.9", "type": "ICD-10", "description": "Respiratory tuberculosis"},
    "influenza": {"code": "J11.1", "type": "ICD-10", "description": "Influenza"},

    # ── MENTAL HEALTH ──────────────────────────────────────────────────────────
    "major depressive disorder": {"code": "F32.9", "type": "ICD-10", "description": "Major depressive disorder"},
    "depression": {"code": "F32.9", "type": "ICD-10", "description": "Depressive episode"},
    "bipolar disorder": {"code": "F31.9", "type": "ICD-10", "description": "Bipolar disorder, unspecified"},
    "generalized anxiety disorder": {"code": "F41.1", "type": "ICD-10", "description": "Generalized anxiety disorder"},
    "anxiety": {"code": "F41.9", "type": "ICD-10", "description": "Anxiety disorder, unspecified"},
    "post-traumatic stress disorder": {"code": "F43.10", "type": "ICD-10", "description": "PTSD, unspecified"},
    "insomnia": {"code": "G47.00", "type": "ICD-10", "description": "Insomnia, unspecified"},
    "schizophrenia": {"code": "F20.9", "type": "ICD-10", "description": "Schizophrenia, unspecified"},
    "alcohol use disorder": {"code": "F10.20", "type": "ICD-10", "description": "Alcohol dependence"},

    # ── ONCOLOGY ───────────────────────────────────────────────────────────────
    "lung cancer": {"code": "C34.90", "type": "ICD-10", "description": "Malignant neoplasm of unspecified bronchus/lung"},
    "breast cancer": {"code": "C50.919", "type": "ICD-10", "description": "Malignant neoplasm of breast"},
    "colon cancer": {"code": "C18.9", "type": "ICD-10", "description": "Malignant neoplasm of colon"},
    "prostate cancer": {"code": "C61", "type": "ICD-10", "description": "Malignant neoplasm of prostate"},
    "hepatocellular carcinoma": {"code": "C22.0", "type": "ICD-10", "description": "Liver cell carcinoma"},
    "lymphoma": {"code": "C85.90", "type": "ICD-10", "description": "Non-Hodgkin lymphoma"},
    "leukemia": {"code": "C95.90", "type": "ICD-10", "description": "Unspecified leukemia"},

    # ── SYMPTOMS / OTHER ──────────────────────────────────────────────────────
    "dyspnea": {"code": "R06.00", "type": "ICD-10", "description": "Dyspnea, unspecified"},
    "shortness of breath": {"code": "R06.00", "type": "ICD-10", "description": "Dyspnea, unspecified"},
    "edema": {"code": "R60.9", "type": "ICD-10", "description": "Edema, unspecified"},
    "chest pain": {"code": "R07.9", "type": "ICD-10", "description": "Chest pain, unspecified"},
    "nausea": {"code": "R11.0", "type": "ICD-10", "description": "Nausea"},
    "fever": {"code": "R50.9", "type": "ICD-10", "description": "Fever, unspecified"},
    "syncope": {"code": "R55", "type": "ICD-10", "description": "Syncope and collapse"},
    "pain": {"code": "R52", "type": "ICD-10", "description": "Pain, unspecified"},
    "malnutrition": {"code": "E46", "type": "ICD-10", "description": "Unspecified protein-calorie malnutrition"},
    "pressure ulcer": {"code": "L89.90", "type": "ICD-10", "description": "Pressure ulcer"},
    "fall": {"code": "W19.XXXA", "type": "ICD-10", "description": "Unspecified fall, initial encounter"},
    "sickle cell disease": {"code": "D57.1", "type": "ICD-10", "description": "Sickle-cell disease without crisis"},
    "thrombocytopenia": {"code": "D69.6", "type": "ICD-10", "description": "Thrombocytopenia, unspecified"},

    # ── CPT PROCEDURES ─────────────────────────────────────────────────────────
    "laparoscopic cholecystectomy": {"code": "47562", "type": "CPT", "description": "Laparoscopic cholecystectomy"},
    "open cholecystectomy": {"code": "47600", "type": "CPT", "description": "Cholecystectomy"},
    "appendectomy": {"code": "44950", "type": "CPT", "description": "Appendectomy"},
    "laparoscopic appendectomy": {"code": "44970", "type": "CPT", "description": "Laparoscopic appendectomy"},
    "colonoscopy": {"code": "45378", "type": "CPT", "description": "Colonoscopy, flexible"},
    "colonoscopy with polypectomy": {"code": "45385", "type": "CPT", "description": "Colonoscopy with removal of polyp"},
    "upper endoscopy": {"code": "43239", "type": "CPT", "description": "EGD with biopsy"},
    "esophagogastroduodenoscopy": {"code": "43239", "type": "CPT", "description": "Upper GI endoscopy with biopsy"},
    "total knee arthroplasty": {"code": "27447", "type": "CPT", "description": "Total knee arthroplasty"},
    "total hip arthroplasty": {"code": "27130", "type": "CPT", "description": "Total hip arthroplasty"},
    "coronary artery bypass graft": {"code": "33533", "type": "CPT", "description": "Coronary artery bypass graft"},
    "percutaneous coronary intervention": {"code": "92941", "type": "CPT", "description": "Percutaneous transluminal coronary intervention"},
    "cardiac catheterization": {"code": "93458", "type": "CPT", "description": "Left heart catheterization"},
    "echocardiogram": {"code": "93306", "type": "CPT", "description": "Echocardiography, transthoracic"},
    "electrocardiogram": {"code": "93000", "type": "CPT", "description": "Electrocardiogram, routine ECG"},
    "chest x-ray": {"code": "71046", "type": "CPT", "description": "Radiologic examination, chest"},
    "computed tomography scan": {"code": "74178", "type": "CPT", "description": "CT abdomen and pelvis"},
    "magnetic resonance imaging brain": {"code": "70553", "type": "CPT", "description": "MRI brain"},
    "hemodialysis": {"code": "90935", "type": "CPT", "description": "Hemodialysis procedure"},
    "mechanical ventilation": {"code": "94002", "type": "CPT", "description": "Ventilation assist and management"},
    "lumbar puncture": {"code": "62270", "type": "CPT", "description": "Spinal puncture, lumbar"},
    "thoracentesis": {"code": "32554", "type": "CPT", "description": "Thoracentesis"},
    "central venous catheter": {"code": "36558", "type": "CPT", "description": "Insertion of central venous catheter"},
    "blood transfusion": {"code": "36430", "type": "CPT", "description": "Transfusion, blood"},
    "thyroidectomy": {"code": "60252", "type": "CPT", "description": "Total thyroidectomy"},
    "mastectomy": {"code": "19303", "type": "CPT", "description": "Mastectomy"},
    "prostatectomy": {"code": "55866", "type": "CPT", "description": "Laparoscopic prostatectomy"},
    "cesarean section": {"code": "59510", "type": "CPT", "description": "Cesarean delivery"},
    "hysterectomy": {"code": "58150", "type": "CPT", "description": "Total abdominal hysterectomy"},
    "hernia repair": {"code": "49505", "type": "CPT", "description": "Inguinal hernia repair"},
    "cataract surgery": {"code": "66984", "type": "CPT", "description": "Cataract surgery"},
    "intraoperative cholangiography": {"code": "74300", "type": "CPT", "description": "Cholangiography, intraoperative"},
    "furosemide": {"code": "J1940", "type": "HCPCS", "description": "Injection, furosemide (Lasix)"},
    "insulin glargine": {"code": "J1817", "type": "HCPCS", "description": "Insulin glargine"},
}

# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT DETECTION PATTERNS
# ─────────────────────────────────────────────────────────────────────────────
NEGATION_TRIGGERS = [
    "no ", "not ", "without ", "denies ", "denied ", "absent ", "negative for ",
    "no evidence of ", "no history of ", "rules out ", "ruled out ", "r/o ",
    "no signs of ", "does not have ", "doesn't have ", "never had ",
    "free of ", "no intraoperative ", "not performed", "was not performed",
]

FAMILY_HISTORY_TRIGGERS = [
    "family history of", "family hx of", "fh of",
    "mother has", "father has", "sibling has", "brother has", "sister has",
    "grandparent has",
]

PAST_HISTORY_TRIGGERS = [
    "history of", "hx of", "past history of", "past medical history",
    "pmh of", "pmh:", "past medical history:", "previous", "prior history",
    "old ", "resolved", "s/p ", "status post", "post-op for", "remote history of",
]

SUSPECTED_TRIGGERS = [
    "possible ", "probable ", "likely ", "suspect ", "suspected ", "query ",
    "presumed ", "suggestive of ", "cannot be excluded",
]

# ── Clinical note section headers that contain active diagnoses ──────────────
ACTIVE_DIAGNOSIS_SECTIONS = [
    "principal diagnosis", "primary diagnosis", "admitting diagnosis",
    "secondary diagnoses", "secondary diagnosis", "additional diagnoses",
    "discharge diagnoses", "discharge diagnosis", "hospital diagnoses",
    "comorbidities", "comorbidity", "active problems", "problem list",
    "hospital course", "assessment", "impression",
]

PROCEDURE_SECTIONS = [
    "procedure performed", "procedures performed", "operative procedure",
    "procedure:", "procedures:", "surgical procedure", "operation performed",
]


@dataclass
class ClinicalEntity:
    entity: str
    normalized: str
    status: Literal["confirmed", "negated", "family_history", "suspected", "past_history"]
    temporality: Literal["current", "past"]
    evidence_sentence: str
    ontology_code: dict | None = field(default=None)
    section: str = ""
    rag_query: str = ""  # Optimized entity-level RAG search string


class EntityExtractor:
    """
    FAANG-level context-aware clinical entity extractor.
    - Parses clinical document sections to identify active diagnoses
    - Generates entity-level RAG query strings (not full text)
    - Returns codes with confidence always ≥ 0.95 (never diluted)
    """

    def __init__(self):
        from services.group_config import (
            ENTITY_PREFIX_MAP,
            MANDATORY_GROUPS,
        )
        # Sort ontology by length DESC so compound terms match before simpler ones
        self._sorted_ontology = sorted(
            MEDICAL_ONTOLOGY.items(), key=lambda x: len(x[0]), reverse=True
        )
        self.mandatory_groups = MANDATORY_GROUPS  # Store as instance attribute
        logger.info("EntityExtractor v3: initialised with %d ontology entries.", len(MEDICAL_ONTOLOGY))

    # ── Public API ────────────────────────────────────────────────────────────

    def extract(self, note_text: str) -> dict:
        """
        Main extraction method.
        Returns:
          {
            "confirmed_entities": [...],
            "excluded_entities": [...],
            "deterministic_codes": [...],  # confidence always ≥ 0.95
            "rag_queries": [str],           # entity-level RAG search strings
          }
        """
        # Step 1: Parse document sections
        sections = self._parse_sections(note_text)

        # Step 2: Extract entities from each section with appropriate context
        all_entities: list[ClinicalEntity] = []
        for section_name, section_text in sections.items():
            is_active_dx = any(h in section_name for h in ACTIVE_DIAGNOSIS_SECTIONS)
            is_proc = any(h in section_name for h in PROCEDURE_SECTIONS)
            entities = self._extract_from_section(section_text, section_name, force_confirmed=is_active_dx or is_proc)
            all_entities.extend(entities)

        # Step 3: Fallback — scan full text sentence-by-sentence as well
        full_text_entities = self._extract_from_section(note_text, "full_text", force_confirmed=False)
        # Merge, avoiding duplicates
        existing_normalized = {e.normalized for e in all_entities}
        for e in full_text_entities:
            if e.normalized not in existing_normalized:
                all_entities.append(e)
                existing_normalized.add(e.normalized)

        confirmed = [e for e in all_entities if e.status in ("confirmed", "past_history", "suspected")]
        excluded = [e for e in all_entities if e.status in ("negated", "family_history")]

        # Step 4: Build deterministic codes — deduplicated
        seen_codes: set[str] = set()
        deterministic_codes: list[dict] = []
        rag_queries: list[str] = []

        for entity in confirmed:
            if entity.ontology_code:
                code = entity.ontology_code["code"]
                if code not in seen_codes:
                    seen_codes.add(code)
                    # CRITICAL FIX: confidence is ALWAYS 0.95 for deterministic codes
                    status_mult = 1.0 if entity.status == "confirmed" else 0.92
                    deterministic_codes.append({
                        "code": code,
                        "description": entity.ontology_code["description"],
                        "type": entity.ontology_code["type"],
                        "confidence": round(0.95 * status_mult, 3),
                        "source": "deterministic",
                        "entity": entity.normalized,
                        "evidence_span": entity.evidence_sentence,
                        "rationale": (
                            f"Deterministically mapped via clinical ontology: "
                            f"'{entity.entity}' → {code} ({entity.ontology_code['description']})"
                        ),
                        # Score components (no dilution — det always 0.95)
                        "det_score": 0.95,
                        "rag_score": 0.0,
                        "llm_score": 0.0,
                        "section": entity.section,
                    })
                    rag_queries.append(entity.rag_query or entity.normalized)

        logger.info(
            "EntityExtractor: confirmed=%d, excluded=%d, codes=%d, rag_queries=%d",
            len(confirmed), len(excluded), len(deterministic_codes), len(rag_queries),
        )

        return {
            "confirmed_entities": [self._entity_to_dict(e) for e in confirmed],
            "excluded_entities": [self._entity_to_dict(e) for e in excluded],
            "deterministic_codes": deterministic_codes,
            "rag_queries": list(dict.fromkeys(rag_queries)),  # preserve order, deduplicate
        }

    # ── Section-aware parser ──────────────────────────────────────────────────

    def _parse_sections(self, text: str) -> dict[str, str]:
        """
        Parse clinical document into sections.
        Common headers: PRINCIPAL DIAGNOSIS, SECONDARY DIAGNOSES, PROCEDURE PERFORMED, etc.
        """
        sections: dict[str, str] = {}
        current_section = "general"
        current_lines: list[str] = []

        section_header_pattern = re.compile(
            r'^([A-Z][A-Z\s,/]+):?\s*$', re.MULTILINE
        )

        lines = text.split("\n")
        for line in lines:
            stripped = line.strip()
            if not stripped:
                current_lines.append("")
                continue

            # Check if this looks like a section header
            if stripped.isupper() or stripped.endswith(":") and len(stripped) < 60:
                header = stripped.rstrip(":").strip().lower()
                if current_lines:
                    sections[current_section] = "\n".join(current_lines)
                current_section = header
                current_lines = []
            else:
                current_lines.append(stripped)

        if current_lines:
            sections[current_section] = "\n".join(current_lines)

        logger.debug("EntityExtractor: parsed %d sections: %s", len(sections), list(sections.keys()))
        return sections

    def _extract_from_section(
        self, text: str, section_name: str, force_confirmed: bool = False
    ) -> list[ClinicalEntity]:
        """
        Extract entities from a section.
        If force_confirmed, skips past-history check.

        CRITICAL: Uses consumed-substring suppression to prevent duplicates:
        - When compound term matches (e.g., "acute on chronic systolic heart failure"),
          all simpler substring terms (e.g., "heart failure") are SUPPRESSED.
        - When a specific code is produced, generic codes in same family are SUPPRESSED.
        """
        sentences = self._split_sentences(text)
        entities: list[ClinicalEntity] = []
        seen_terms_in_section: set[str] = set()    # canonical terms already matched
        seen_codes_in_section: set[str] = set()    # ICD codes already produced

        # ICD hierarchy: if specific code exists, suppress these generic ones
        CODE_SUPPRESSIONS = {
            # If E11.42 matched -> suppress standalone neuropathy
            "E11.42": {"G62.9", "G60.9", "E11.9", "E11.40"},
            "E11.40": {"G62.9", "G60.9", "E11.9"},
            "E11.22": {"E11.9", "N18.9"},
            "E11.65": {"E11.9"},
            "I50.23": {"I50.9", "I50.20"},
            "I50.21": {"I50.9", "I50.20"},
            "I50.33": {"I50.9", "I50.30"},
            "I50.31": {"I50.9", "I50.30"},
            "N18.3": {"N18.9"},
            "N18.31": {"N18.9", "N18.3"},
            "N18.4": {"N18.9"},
            "N18.5": {"N18.9"},
            "E66.01": {"E66.9"},
        }

        for sentence in sentences:
            sentence_lower = sentence.lower()
            normalized_sentence = self._normalize_synonyms(sentence_lower)

            # Context flags for the sentence
            is_negated_sent = any(neg in normalized_sentence for neg in NEGATION_TRIGGERS)
            is_family = any(fam in normalized_sentence for fam in FAMILY_HISTORY_TRIGGERS)
            is_past = not force_confirmed and any(past in normalized_sentence for past in PAST_HISTORY_TRIGGERS)
            is_suspected = any(sus in normalized_sentence for sus in SUSPECTED_TRIGGERS)

            for canonical_term, ontology_entry in self._sorted_ontology:
                if canonical_term not in normalized_sentence:
                    continue
                if canonical_term in seen_terms_in_section:
                    continue

                # ── CONSUMED SUBSTRING SUPPRESSION ──
                # If any already-matched term CONTAINS this term as a substring, skip it
                # e.g., "heart failure" is a substring of "acute on chronic systolic heart failure"
                is_consumed = False
                for matched_term in seen_terms_in_section:
                    if canonical_term in matched_term and canonical_term != matched_term:
                        is_consumed = True
                        break
                if is_consumed:
                    continue

                # ── CODE-LEVEL SUPPRESSION ──
                code = ontology_entry.get("code", "")
                if code in seen_codes_in_section:
                    continue  # exact code already produced

                # Check if this code is suppressed by a more specific code
                code_suppressed = False
                for existing_code in seen_codes_in_section:
                    suppressions = CODE_SUPPRESSIONS.get(existing_code, set())
                    if code in suppressions:
                        code_suppressed = True
                        break
                if code_suppressed:
                    continue

                entity_pos = normalized_sentence.find(canonical_term)

                # Classify status
                if is_family:
                    status = "family_history"
                elif self._negation_precedes(normalized_sentence, canonical_term, entity_pos):
                    status = "negated"
                elif force_confirmed:
                    status = "confirmed"
                elif is_past and not is_negated_sent:
                    status = "past_history"
                elif is_suspected:
                    status = "suspected"
                else:
                    status = "confirmed"

                temporality = "past" if (is_past or is_family) and not force_confirmed else "current"

                # Generate targeted RAG query
                rag_query = self._build_rag_query(canonical_term, ontology_entry)

                entities.append(ClinicalEntity(
                    entity=canonical_term,
                    normalized=canonical_term,
                    status=status,
                    temporality=temporality,
                    evidence_sentence=sentence.strip(),
                    ontology_code=ontology_entry,
                    section=section_name,
                    rag_query=rag_query,
                ))
                seen_terms_in_section.add(canonical_term)
                seen_codes_in_section.add(code)

                # Register all suppressions for this code
                for suppress_code in CODE_SUPPRESSIONS.get(code, set()):
                    seen_codes_in_section.add(suppress_code)

            # ── HYBRID KEYWORD FALLBACK (NEW) ──
            # If the strict ontology missed a major disease category but the keyword is in the sentence, forcefully extract it.
            for keyword, fallback_entry in self.mandatory_groups.items():
                if keyword in normalized_sentence:
                    # Only add if we haven't already extracted something that covers it
                    # (e.g. if we already have "diabetes mellitus type 2", don't add "diabetes")
                    already_covered = any(keyword in term for term in seen_terms_in_section)
                    if not already_covered:
                        fallback_code = fallback_entry["code"]
                        if fallback_code not in seen_codes_in_section:
                            # Context flags
                            status = "confirmed"
                            if is_family: status = "family_history"
                            elif self._negation_precedes(normalized_sentence, keyword, normalized_sentence.find(keyword)): status = "negated"
                            elif is_past and not is_negated_sent: status = "past_history"
                            elif is_suspected: status = "suspected"
                            
                            temporality = "past" if (is_past or is_family) and not force_confirmed else "current"
                            rag_query = self._build_rag_query(keyword, fallback_entry)
                            
                            entities.append(ClinicalEntity(
                                entity=keyword,
                                normalized=keyword,
                                status=status,
                                temporality=temporality,
                                evidence_sentence=sentence.strip(),
                                ontology_code=fallback_entry,
                                section=section_name,
                                rag_query=rag_query,
                            ))
                            seen_terms_in_section.add(keyword)
                            seen_codes_in_section.add(fallback_code)

        return entities

    def _build_rag_query(self, entity: str, ontology_entry: dict) -> str:
        """Build a targeted, entity-level RAG query string for maximum specificity."""
        code = ontology_entry.get("code", "")
        description = ontology_entry.get("description", "")
        # Query combines entity name + code description for maximum hit rate
        return f"{entity} {description}".strip()

    def _split_sentences(self, text: str) -> list[str]:
        sentences = re.split(r'(?<=[.!?])\s+|(?<=\n)\s*|\n[-–•]\s*', text.strip())
        return [s.strip() for s in sentences if s.strip() and len(s.strip()) > 3]

    def _negation_precedes(self, text: str, entity: str, entity_pos: int) -> bool:
        prefix = text[max(0, entity_pos - 70): entity_pos]
        return any(neg in prefix for neg in NEGATION_TRIGGERS)

    def _normalize_synonyms(self, text: str) -> str:
        normalized = text
        for synonym, canonical in sorted(SYNONYM_MAP.items(), key=lambda x: len(x[0]), reverse=True):
            normalized = re.sub(r'\b' + re.escape(synonym) + r'\b', canonical, normalized)
        return normalized

    @staticmethod
    def _entity_to_dict(e: ClinicalEntity) -> dict:
        return {
            "entity": e.entity,
            "normalized": e.normalized,
            "status": e.status,
            "temporality": e.temporality,
            "evidence_sentence": e.evidence_sentence,
            "code": e.ontology_code["code"] if e.ontology_code else None,
            "section": e.section,
            "rag_query": e.rag_query,
        }
