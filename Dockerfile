# ── CodePerfectAuditor – Backend Dockerfile ───────────────────────────────────
FROM python:3.11-slim

LABEL maintainer="CodePerfectAuditor"
LABEL description="Agentic AI Medical Coding Auditor – Backend"

# Environment
ENV PYTHONPATH=/app/backend \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # Store SentenceTransformer model cache inside the image layer
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/sentence_transformers \
    TRANSFORMERS_CACHE=/app/.cache/transformers

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install dependencies (cache layer)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Pre-download MiniLM model at build time (avoids first-request delay)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy project
COPY backend/ ./backend/
COPY backend/data/ ./data/
COPY scripts/ ./scripts/

# Create required directories
RUN mkdir -p /app/chroma_store /app/logs

# Expose port
EXPOSE 8000

# Healthcheck — extra start-period for model warm-up
HEALTHCHECK --interval=20s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Run app
WORKDIR /app/backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]