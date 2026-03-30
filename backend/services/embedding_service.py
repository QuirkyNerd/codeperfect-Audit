"""
services/embedding_service.py – Local SentenceTransformer embedding service.

Uses all-MiniLM-L6-v2 (384-dim) running FULLY LOCALLY.
No external API calls. No Gemini. No internet required after first load.

Features:
  - Synchronous encode() wrapped for async pipeline compatibility
  - Per-text SHA-256 cache (up to 50K entries, ~75 MB max)
  - Batch support: embed_texts() → List[List[float]]
  - Single support: embed_single() → List[float]
"""

import asyncio
import hashlib
from functools import partial

from sentence_transformers import SentenceTransformer

try:
    from backend.utils.logging import get_logger
except ImportError:
    from utils.logging import get_logger

logger = get_logger(__name__)

# ── Model singleton ───────────────────────────────────────────────────────────
# Loaded once at module import. Downloads ~90 MB on first run, then cached.
_MODEL_NAME = "all-MiniLM-L6-v2"
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("EmbeddingService: loading '%s' (first run may download model).", _MODEL_NAME)
        _model = SentenceTransformer(_MODEL_NAME)
        logger.info("EmbeddingService: model loaded. Embedding dim = %d.", _model.get_sentence_embedding_dimension())
    return _model


# ── In-process cache ──────────────────────────────────────────────────────────
_MAX_CACHE = 50_000
_embed_cache: dict[str, list[float]] = {}


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cache_get(text: str) -> list[float] | None:
    return _embed_cache.get(_cache_key(text))


def _cache_set(text: str, vector: list[float]) -> None:
    if len(_embed_cache) < _MAX_CACHE:
        _embed_cache[_cache_key(text)] = vector


class EmbeddingService:
    """
    Local embedding generator using SentenceTransformer (all-MiniLM-L6-v2).
    Embedding dimension: 384.
    """

    def __init__(self):
        self.model = _get_model()

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Embed multiple texts. Cache hits are returned instantly;
        misses are batch-encoded locally (no API call).
        """
        if not texts:
            return []

        results: list[list[float] | None] = [None] * len(texts)
        miss_indices: list[int] = []
        miss_texts:   list[str] = []

        for i, text in enumerate(texts):
            cached = _cache_get(text)
            if cached is not None:
                results[i] = cached
            else:
                miss_indices.append(i)
                miss_texts.append(text)

        if miss_texts:
            # Run CPU-bound encoding in thread executor to not block event loop
            loop = asyncio.get_event_loop()
            encode_fn = partial(self.model.encode, miss_texts, batch_size=128, show_progress_bar=False)
            vectors_np = await loop.run_in_executor(None, encode_fn)
            vectors: list[list[float]] = [v.tolist() for v in vectors_np]

            for idx, text, vec in zip(miss_indices, miss_texts, vectors):
                _cache_set(text, vec)
                results[idx] = vec

            logger.info(
                "EmbeddingService: encoded %d texts (%d cache hits).",
                len(miss_texts), len(texts) - len(miss_texts),
            )

        return results  # type: ignore[return-value]

    async def embed_single(self, text: str) -> list[float]:
        """Embed a single query string."""
        cached = _cache_get(text)
        if cached is not None:
            return cached

        loop = asyncio.get_event_loop()
        encode_fn = partial(self.model.encode, [text], show_progress_bar=False)
        vectors_np = await loop.run_in_executor(None, encode_fn)
        vec = vectors_np[0].tolist()
        _cache_set(text, vec)
        return vec