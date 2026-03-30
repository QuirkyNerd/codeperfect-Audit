import asyncio
import hashlib
from functools import partial

try:
    from backend.utils.logging import get_logger
except ImportError:
    from utils.logging import get_logger

from main import model

logger = get_logger(__name__)

_MAX_CACHE = 50000
_embed_cache: dict[str, list[float]] = {}


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cache_get(text: str) -> list[float] | None:
    return _embed_cache.get(_cache_key(text))


def _cache_set(text: str, vector: list[float]) -> None:
    if len(_embed_cache) < _MAX_CACHE:
        _embed_cache[_cache_key(text)] = vector


class EmbeddingService:
    def __init__(self):
        if model is None:
            raise RuntimeError("Embedding model not initialized")
        self.model = model
        logger.info("EmbeddingService: using preloaded model")

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        results: list[list[float] | None] = [None] * len(texts)
        miss_indices: list[int] = []
        miss_texts: list[str] = []

        for i, text in enumerate(texts):
            cached = _cache_get(text)
            if cached is not None:
                results[i] = cached
            else:
                miss_indices.append(i)
                miss_texts.append(text)

        if miss_texts:
            loop = asyncio.get_event_loop()
            encode_fn = partial(
                self.model.encode,
                miss_texts,
                batch_size=128,
                show_progress_bar=False
            )

            vectors_np = await loop.run_in_executor(None, encode_fn)
            vectors: list[list[float]] = [v.tolist() for v in vectors_np]

            for idx, text, vec in zip(miss_indices, miss_texts, vectors):
                _cache_set(text, vec)
                results[idx] = vec

            logger.info(
                "EmbeddingService: encoded %d texts (%d cache hits)",
                len(miss_texts),
                len(texts) - len(miss_texts),
            )

        return results  # type: ignore

    async def embed_single(self, text: str) -> list[float]:
        cached = _cache_get(text)
        if cached is not None:
            return cached

        loop = asyncio.get_event_loop()
        encode_fn = partial(self.model.encode, [text], show_progress_bar=False)

        vectors_np = await loop.run_in_executor(None, encode_fn)
        vec = vectors_np[0].tolist()

        _cache_set(text, vec)
        return vec