# CodePerfect Audit

CodePerfect Audit is an AI-powered clinical coding audit system designed to analyze medical notes and validate ICD-10 and CPT codes before claim submission. The system helps reduce revenue leakage, improve coding accuracy, and support compliance in healthcare billing workflows.

---

## Overview

The platform processes clinical notes through a multi-stage AI pipeline and compares human-entered codes with AI-generated codes. It identifies discrepancies, highlights missing or incorrect codes, and provides supporting evidence from the clinical text.

---

## Live Deployment

Frontend:  
https://codeperfect-audit.vercel.app  

Backend API:  
https://codeperfect-audit.onrender.com  

Embedding Service (Hugging Face):  
https://adithya3003-codeperfect-embeddings.hf.space/embed  

---


##  Architecture

```
Clinical Note
     ↓
Clinical Reader Agent   ← Gemini + structured prompt
     ↓
Structured Clinical Facts
     ↓
Coding Logic Agent      ← RAG (ChromaDB) + Gemini reasoning
     ↓
AI-Generated Codes (with confidence scores)
     ↓
Auditor Agent           ← Gemini + deterministic set comparison
     ↓
Discrepancy Report
     ↓
Evidence Highlighter    ← SentenceIndexer (deterministic)
     ↓
Frontend Dashboard      ← React + Vite
```

---

##  Project Structure

```
CodePerfectAuditor/
├── backend/
│   ├── main.py                       
│   ├── config.py                      
│   ├── api/routes.py                  
│   ├── agents/
│   │   ├── clinical_reader.py        
│   │   ├── coding_logic.py            
│   │   ├── auditor.py                
│   │   └── evidence_agent.py         
│   ├── services/
│   │   ├── agent_orchestrator.py     
│   │   ├── rag_engine.py             
│   │   ├── embedding_service.py      
│   │   └── guideline_loader.py   
│   ├── database/
│   │   ├── models.py                 
│   │   └── db.py                     
│   ├── utils/
│   │   ├── sentence_indexer.py       
│   │   ├── text_processing.py        
│   │   └── logging.py               
│   └── prompts/
│       ├── clinical_reader_prompt.txt
│       ├── coding_logic_prompt.txt
│       └── auditor_prompt.txt
├── frontend/
│   ├── src/
│   │   ├── pages/Dashboard.jsx       
│   │   ├── components/
│   │   │   ├── UploadNote.jsx        
│   │   │   ├── CodeInput.jsx         
│   │   │   └── AuditResults.jsx    
│   │   └── services/api.js         
│   ├── package.json
│   └── vite.config.js
├── data/
│   ├── icd10_codes.csv                
│   ├── cpt_codes.csv                
│   └── coding_guidelines/            
├── scripts/
│   └── ingest_guidelines.py          
├── tests/
│   ├── conftest.py
│   ├── test_clinical_reader.py
│   ├── test_coding_logic.py
│   └── test_auditor.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

##  Quick Start (Local)

### 1. Prerequisites

## Tech Stack

### Backend
- FastAPI
- Gemini API (LLM reasoning)
- Neon PostgreSQL (cloud database)
- SQLAlchemy

### Frontend
- React + Vite
- Axios
- Hosted on Vercel

### AI / ML
- Gemini (LLM)
- MiniLM-L6-v2 (embeddings via Hugging Face)
- Retrieval-Augmented Generation (RAG)

### 2. Clone & configure

```bash
cd d:/Desktop/virtusa_jatayu/CodePerfectAuditor

# Copy the env template and fill in your OpenAI key
copy .env.example backend\.env
# Edit backend\.env and set: OPENAI_API_KEY=sk-your-real-key
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
# Also install test dependencies:
pip install pytest pytest-asyncio
```

### 4. Ingest reference data into ChromaDB

Run this **once** before starting the server:

```bash
cd d:/Desktop/virtusa_jatayu/CodePerfectAuditor
python scripts/ingest_guidelines.py
```


### 5. Start the backend

```bash
cd d:/Desktop/virtusa_jatayu/CodePerfectAuditor/backend
uvicorn main:app --reload --port 8000
```


### 6. Start the frontend

```bash
cd d:/Desktop/virtusa_jatayu/CodePerfectAuditor/frontend
npm install
npm run dev
```


##  Docker (with PostgreSQL)

```bash
cd d:/Desktop/virtusa_jatayu/CodePerfectAuditor

# Set your key in .env first
copy .env.example .env
# Edit .env: Gemini_API_KEY=sk-...

docker-compose up --build


##  Testing

```bash
cd d:/Desktop/virtusa_jatayu/CodePerfectAuditor
pytest tests/ -v
```

---

## 🔌 API Reference

### `POST /api/v1/audit`

**Request:**
```json
{
  "note_text": "Patient presents with uncontrolled hypertension and type 2 diabetes. Underwent laparoscopic cholecystectomy.",
  "human_codes": ["I10"]
}
```

**Response:**
```json
{
  "audit_id": 1,
  "ai_codes": [
    { "code": "I10",   "description": "Essential hypertension", "type": "ICD-10", "confidence": 0.95 },
    { "code": "E11.9", "description": "Type 2 DM", "type": "ICD-10", "confidence": 0.90 },
    { "code": "47562", "description": "Laparoscopic cholecystectomy", "type": "CPT", "confidence": 0.88 }
  ],
  "low_confidence_codes": [],
  "discrepancies": [
    { "code": "E11.9",  "type": "missed_code",  "message": "...", "severity": "high" },
    { "code": "47562",  "type": "missed_code",  "message": "...", "severity": "high" },
    { "code": "I10",    "type": "correct_code", "message": "...", "severity": "low" }
  ],
  "evidence": [
    { "code": "I10",  "sentence_id": 0, "sentence_text": "Patient presents with uncontrolled hypertension...", "start_char": 0, "end_char": 51 }
  ],
  "summary": "Human coder missed 2 codes...",
  "timestamp": "2025-01-01T00:00:00"
}
```

### `GET /api/v1/health`

```json
{
  "status": "ok",
  "database": "connected",
  "vector_db": "connected",
  "service": "CodePerfectAuditor",
  "version": "1.0.0"
}

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| GEMINI_API_KEY | required | Your Gemini API key |
| GEMINI_MODEL | gemini-1.5-pro | Model used for agent reasoning |
| DATABASE_URL | Neon PostgreSQL | Connection string for Neon database |
| EMBEDDING_MODEL | all-MiniLM-L6-v2 | Sentence transformer model for embeddings |
| MIN_CODE_CONFIDENCE | 0.65 | Confidence threshold for filtering codes |
| RAG_TOP_K | 10 | Number of top results retrieved in RAG |

---

## Key Design Decisions

| Feature | Implementation |
|---------|---------------|
| Agent orchestration | AgentOrchestrator with sequential multi-agent pipeline and shared state |
| Evidence highlighting | SentenceIndexer with deterministic character span mapping |
| Confidence threshold | Low-confidence codes are separated for manual review |
| Deterministic fallback | Auditor agent uses set-based comparison if AI response fails |
| Database | Neon PostgreSQL for scalable cloud storage |
| Structured logging | JSON-based logging for observability and debugging |
| Retry logic | Agents retry up to AGENT_MAX_RETRIES on failure |
