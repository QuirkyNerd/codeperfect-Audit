"""
utils/logging.py – Structured logger factory for CodePerfectAuditor.

Every module should call `get_logger(__name__)` for a named logger.
Logs are emitted as JSON lines to stdout (container-friendly, aggregator-ready).

Correlation ID support
----------------------
Each HTTP request sets a unique request_id via `set_request_context()`.
The JSON formatter automatically includes it in every log line emitted
during that request, enabling full pipeline tracing without passing IDs
explicitly through every function call.

Usage:
    # In the FastAPI middleware / endpoint:
    from utils.logging import set_request_context
    set_request_context(request_id="abc-123", document_id=42)

    # In any agent / service module:
    logger = get_logger(__name__)
    logger.info("Processing…")  # → includes request_id & document_id automatically
"""

import logging
import json
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# ── Context variables (per-async-task; safe under async concurrency) ──────────
_request_id_var: ContextVar[str] = ContextVar("request_id", default="")
_document_id_var: ContextVar[int] = ContextVar("document_id", default=-1)  # -1 = unset
_agent_name_var: ContextVar[str] = ContextVar("agent_name", default="")


def set_request_context(
    *,
    request_id: str = "",
    document_id: Optional[int] = None,
    agent_name: str = "",
) -> None:
    """
    Bind correlation IDs to the current async task context.

    Call this once at the start of each HTTP request (or pipeline stage) to
    have all subsequent log lines automatically include the IDs.

    Args:
        request_id:  UUID string identifying the HTTP request.
        document_id: DB primary key of the Document being audited.
        agent_name:  Current agent name (updated per pipeline stage).
    """
    if request_id:
        _request_id_var.set(request_id)
    if document_id is not None:
        _document_id_var.set(document_id)
    if agent_name:
        _agent_name_var.set(agent_name)


def new_request_id() -> str:
    """Generate a fresh UUID4 request ID string."""
    return str(uuid.uuid4())


class _JSONFormatter(logging.Formatter):
    """
    Custom logging formatter that outputs log records as JSON lines.

    Each line includes: ts, level, logger, msg, request_id, document_id, agent_name.

    Example output:
      {"ts":"2025-01-01T00:00:00Z","level":"INFO","logger":"agents.clinical_reader",
       "msg":"Extracting entities","request_id":"a1b2-...","document_id":7,"agent_name":"ClinicalReaderAgent"}
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Inject correlation IDs from context vars
        rid = _request_id_var.get()
        did = _document_id_var.get()
        aname = _agent_name_var.get()
        if rid:
            payload["request_id"] = rid
        if did != -1:
            payload["document_id"] = did
        if aname:
            payload["agent_name"] = aname

        # exc_info is a 3-tuple or None; only format when all three parts are non-None.
        if record.exc_info and record.exc_info[0] is not None:
            payload["exc"] = self.formatException(record.exc_info)  # type: ignore[arg-type]

        return json.dumps(payload)


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Return a named logger configured with JSON + correlation ID formatting.

    Args:
        name:  Logger name (pass __name__ from calling module).
        level: Logging level (default INFO).

    Returns:
        Configured logging.Logger instance.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False

    return logger
