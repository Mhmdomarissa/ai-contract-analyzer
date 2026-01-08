# Contract Clause Testing Lab - Backend

This is the backend API for the Contract Clause Testing Lab, providing LLM-powered clause comparison and analysis.

## 🎯 Purpose

This is a **conflict detection and analysis lab**. Document parsing and clause extraction features have been removed and will be integrated separately later.

## 🏗️ Architecture

```
backend/
├── app/
│   ├── api/v1/
│   │   ├── endpoints/
│   │   │   ├── compare.py           # 1-to-1 clause comparison
│   │   │   ├── batch_compare.py     # 1-to-N batch comparison
│   │   │   ├── all_vs_all_compare.py # N-to-N with self-check
│   │   │   └── chat.py              # AI chatbot
│   │   └── api.py                   # Router configuration
│   ├── core/
│   │   └── config.py                # App settings
│   ├── services/                    # (empty - cleaned up)
│   ├── utils/                       # Shared utilities
│   └── main.py                      # FastAPI entry point
├── pyproject.toml                   # Dependencies
└── Dockerfile                       # Container config
```

## ✨ Features

### 1. Single Clause Comparison (1→1)
**Endpoint:** `POST /api/v1/compare/clauses`

Compare two clauses with a custom prompt.

**Request:**
```json
{
  "clause_a": "Contract term A...",
  "clause_b": "Contract term B...",
  "prompt": "Compare these clauses for conflicts..."
}
```

**Response:**
```json
{
  "response": "Analysis from LLM...",
  "model": "qwen2.5:32b"
}
```

### 2. Batch Comparison (1→N)
**Endpoint:** `POST /api/v1/compare/batch`

Compare one clause against multiple clauses.

**Request:**
```json
{
  "reference_clause": "Main clause...",
  "clauses_to_compare": ["Clause 1...", "Clause 2...", "Clause 3..."],
  "prompt": "Check for conflicts..."
}
```

**Response:** Streams results via Server-Sent Events (SSE).

### 3. All-vs-All Comparison (N→N)
**Endpoint:** `POST /api/v1/compare/all-vs-all`

Compare all clauses against each other, including self-consistency checks.

**Request:**
```json
{
  "clauses": ["Clause 1...", "Clause 2...", "Clause N..."],
  "pair_prompt": "Compare these two clauses...",
  "self_prompt": "Check this clause for internal conflicts..."
}
```

**Features:**
- Generates N*(N+1)/2 comparisons (N self-checks + N*(N-1)/2 pairs)
- Concurrent processing with semaphore (2 parallel LLM calls)
- Batch processing (10 comparisons per batch)
- Real-time SSE streaming
- Robust conflict detection with 3-tier priority system

**Response:** Streams comparison results via SSE.

### 4. AI Chatbot
**Endpoint:** `POST /api/v1/chat/send`

Interactive chat with Qwen2.5 for clause analysis.

## 🔧 Configuration

Set the following environment variables in `backend/.env`:

```bash
# LLM Configuration
OLLAMA_BASE_URL=http://51.112.105.60:11434
OLLAMA_MODEL=qwen2.5:32b

# API Configuration
API_V1_STR=/api/v1
PROJECT_NAME=Contract Clause Testing Lab
```

## 🚀 Running Locally

```bash
# Install dependencies
cd backend
pip install -e .

# Run server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 🐳 Docker

```bash
# Build
docker compose build api

# Run
docker compose up -d api
```

## 📊 Performance

- **Concurrent processing**: 2 parallel LLM calls (configurable via `MAX_CONCURRENT_LLM_CALLS`)
- **Batch size**: 10 comparisons per batch
- **Typical speed**: ~5 seconds per comparison (with 2x concurrency)
- **Conflict detection**: 3-tier priority system (structured format → explicit phrases → fallback)

## 🔮 Future Integration

This lab is designed to receive new parsing and extraction code. The clean modular structure allows easy integration of:
- Document parsers (PDF, DOCX, etc.)
- Clause extraction algorithms
- Storage and retrieval systems

## 🛠️ Development Notes

- All database code has been removed (no models, CRUD, migrations)
- Document processing services removed
- Celery worker tasks removed
- Only LLM communication logic remains
- Clean, minimal codebase focused on comparison/analysis

## 📝 API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
