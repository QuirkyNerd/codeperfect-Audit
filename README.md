# 🏥 CodePerfectAuditor

> **Agentic AI Medical Coding Audit System** – Reads clinical notes and audits ICD-10 / CPT billing codes before claims are submitted, ensuring revenue integrity and compliance.

---

## 🏗️ Architecture

```
Clinical Note
     ↓
Clinical Reader Agent   ← GPT-4 + structured prompt
     ↓
Structured Clinical Facts
     ↓
Coding Logic Agent      ← RAG (ChromaDB) + GPT-4 reasoning
     ↓
AI-Generated Codes (with confidence scores)
     ↓
Auditor Agent           ← GPT-4 + deterministic set comparison
     ↓
Discrepancy Report
     ↓
Evidence Highlighter    ← SentenceIndexer (deterministic)
     ↓
Frontend Dashboard      ← React + Vite
```

---

## 📁 Project Structure

```
CodePerfectAuditor/
├── backend/
│   ├── main.py                        # FastAPI entrypoint
│   ├── config.py                      # Pydantic-settings configuration
│   ├── api/routes.py                  # POST /audit, GET /health
│   ├── agents/
│   │   ├── clinical_reader.py         # Agent 1: Extract medical entities
│   │   ├── coding_logic.py            # Agent 2: RAG + GPT code generation
│   │   ├── auditor.py                 # Agent 3: Code comparison & classification
│   │   └── evidence_agent.py          # Agent 4: Sentence span highlighting
│   ├── services/
│   │   ├── agent_orchestrator.py      # Pipeline controller
│   │   ├── rag_engine.py              # ChromaDB wrapper
│   │   ├── embedding_service.py       # OpenAI embedding batching
│   │   └── guideline_loader.py        # CSV + guideline ingestion
│   ├── database/
│   │   ├── models.py                  # SQLAlchemy ORM models
│   │   └── db.py                      # Async session + init_db
│   ├── utils/
│   │   ├── sentence_indexer.py        # Reliable char-span indexer
│   │   ├── text_processing.py         # Text normalization helpers
│   │   └── logging.py                 # JSON-structured logger
│   └── prompts/
│       ├── clinical_reader_prompt.txt
│       ├── coding_logic_prompt.txt
│       └── auditor_prompt.txt
├── frontend/
│   ├── src/
│   │   ├── pages/Dashboard.jsx        # Main page
│   │   ├── components/
│   │   │   ├── UploadNote.jsx         # Clinical note textarea
│   │   │   ├── CodeInput.jsx          # Tag-style code input
│   │   │   └── AuditResults.jsx       # Results: codes, discrepancies, evidence
│   │   └── services/api.js            # Axios client
│   ├── package.json
│   └── vite.config.js
├── data/
│   ├── icd10_codes.csv                # 50+ ICD-10 codes for ChromaDB
│   ├── cpt_codes.csv                  # 30+ CPT codes for ChromaDB
│   └── coding_guidelines/             # CMS guideline text snippets
├── scripts/
│   └── ingest_guidelines.py           # One-time ChromaDB ingestion
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

## ⚡ Quick Start (Local)

### 1. Prerequisites

- Python 3.11+
- Node.js 18+
- An **OpenAI API key** with GPT-4 access

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

Expected output:
```
✅ Ingestion complete!
   ICD-10 codes:        55 documents
   CPT codes:           30 documents
   Guideline snippets:  3 documents
```

### 5. Start the backend

```bash
cd d:/Desktop/virtusa_jatayu/CodePerfectAuditor/backend
uvicorn main:app --reload --port 8000
```

API docs available at: http://localhost:8000/docs

### 6. Start the frontend

```bash
cd d:/Desktop/virtusa_jatayu/CodePerfectAuditor/frontend
npm install
npm run dev
```

Open: **http://localhost:5173**

---

## 🐳 Docker (with PostgreSQL)

```bash
cd d:/Desktop/virtusa_jatayu/CodePerfectAuditor

# Set your key in .env first
copy .env.example .env
# Edit .env: OPENAI_API_KEY=sk-...

docker-compose up --build
```

Backend: http://localhost:8000  
Swagger UI: http://localhost:8000/docs

---

## 🧪 Testing

```bash
cd d:/Desktop/virtusa_jatayu/CodePerfectAuditor
pytest tests/ -v
```

Tests use mocked OpenAI calls – no real API key needed to run tests.

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
```

---

## ⚙️ Configuration

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | **required** | Your OpenAI API key |
| `OPENAI_MODEL` | `gpt-4-1106-preview` | GPT model for agents |
| `DATABASE_URL` | SQLite | PostgreSQL URL for production |
| `CHROMA_PERSIST_DIR` | `./chroma_store` | ChromaDB storage directory |
| `MIN_CODE_CONFIDENCE` | `0.65` | Confidence threshold for codes |
| `RAG_TOP_K` | `10` | Top-K results per RAG query |

---

## 🛡️ Key Design Decisions

| Feature | Implementation |
|---|---|
| **Agent orchestration** | `AgentOrchestrator` with sequential pipeline + shared state |
| **Evidence highlighting** | `SentenceIndexer` pre-builds char offsets; no fragile string search at runtime |
| **Confidence threshold** | Codes below `MIN_CODE_CONFIDENCE` go to a review queue, not the audit report |
| **Deterministic fallback** | AuditorAgent uses set-based comparison if GPT fails |
| **Database** | SQLite by default; swap to PostgreSQL with one env variable |
| **Structured logging** | All agents emit JSON log lines for aggregator compatibility |
| **Retry logic** | Each agent retries up to `AGENT_MAX_RETRIES` times on failure |
