"""
utils/gemini_client.py – Centralised Gemini REST API client.

Uses the Gemini REST API directly (no SDK dependency conflicts).
Enforces JSON output mode at the API level so no post-hoc parsing hacks needed.

Features:
  - responseMimeType: "application/json" → forces pure JSON output from model
  - temperature=0.0 → deterministic, reduced hallucination
  - Synchronous function wrapped for use in async pipeline via run_in_executor
  - Retry loop with 1-second backoff
  - Raises RuntimeError on total failure (no silent swallowing)
"""

import asyncio
import time
from functools import partial

import requests

from config import settings
from utils.logging import get_logger

logger = get_logger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
_API_KEY = settings.gemini_api_key
_MODEL   = settings.gemini_model   # e.g. "gemini-1.5-flash"
_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_MAX_OUTPUT_TOKENS = 2048
_TIMEOUT_SEC = 45


def _call_gemini_sync(prompt: str, max_retries: int = 2) -> str:
    """
    Synchronous Gemini REST call with JSON mode enforced.

    Args:
        prompt:      Full prompt text (system instruction + user content merged).
        max_retries: Number of retry attempts on transient errors.

    Returns:
        Raw JSON string from the model (guaranteed non-empty on success).

    Raises:
        RuntimeError: If all attempts fail.
    """
    url = f"{_BASE_URL}/{_MODEL}:generateContent?key={_API_KEY}"
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.0,           # deterministic
            "maxOutputTokens": _MAX_OUTPUT_TOKENS,
            "responseMimeType": "application/json",  # ENFORCES JSON OUTPUT
        },
    }

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 2):
        try:
            logger.info("GeminiClient: attempt %d / %d → %s", attempt, max_retries + 1, _MODEL)
            resp = requests.post(url, json=payload, timeout=_TIMEOUT_SEC)

            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")

            data = resp.json()
            candidates = data.get("candidates", [])

            if not candidates:
                # Model was blocked or returned nothing — check promptFeedback
                feedback = data.get("promptFeedback", {})
                raise ValueError(f"No candidates returned. Feedback: {feedback}")

            finish_reason = candidates[0].get("finishReason", "")
            if finish_reason not in ("STOP", "MAX_TOKENS", ""):
                raise ValueError(f"Unexpected finishReason: {finish_reason}")

            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                raise ValueError("No parts in candidate content")

            text = parts[0].get("text", "").strip()
            if not text:
                raise ValueError("Empty text in response part")

            logger.info("GeminiClient: success (%d chars)", len(text))
            return text

        except Exception as exc:
            last_error = exc
            logger.warning("GeminiClient: attempt %d failed: %s", attempt, exc)
            if attempt <= max_retries:
                time.sleep(1)

    raise RuntimeError(f"All Gemini attempts failed. Last error: {last_error}")


async def generate_json_async(prompt: str, max_retries: int = 2) -> str:
    """
    Async wrapper: runs the synchronous Gemini REST call in a thread executor
    so it does not block the FastAPI event loop.

    Returns:
        Raw JSON string from the model.
    """
    loop = asyncio.get_event_loop()
    fn = partial(_call_gemini_sync, prompt, max_retries)
    return await loop.run_in_executor(None, fn)


# Backward-compatibility alias (kept for any code that still imports this)
def generate_with_fallback(prompt: str, max_retries: int = 2) -> str:
    """Synchronous convenience wrapper. Prefer generate_json_async() in async contexts."""
    return _call_gemini_sync(prompt, max_retries)