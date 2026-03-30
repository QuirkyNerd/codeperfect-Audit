import hashlib
import httpx

try:
    from backend.utils.logging import get_logger
except ImportError:
    from utils.logging import get_logger

logger = get_logger(__name__)

_MAX_CACHE = 50000
_embed_cache: dict[str, list[float]] = {}

HF_EMBED_URL = "https://adithya3003-codeperfect-embeddings.hf.space/embed"


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cache_get(text: str) -> list[float] | None:
    return _embed_cache.get(_cache_key(text))


def _cache_set(text: str, vector: list[float]) -> None:
    if len(_embed_cache) < _MAX_CACHE:
        _embed_cache[_cache_key(text)] = vector


class EmbeddingService:
    def __init__(self):
        self.url = HF_EMBED_URL
        logger.info("EmbeddingService: using HuggingFace remote embeddings")

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
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    self.url,
                    json={"texts": miss_texts}
                )

                if response.status_code != 200:
                    raise RuntimeError(
                        f"Embedding API failed: {response.status_code} {response.text}"
                    )

                vectors: list[list[float]] = response.json()["embeddings"]

            for idx, text, vec in zip(miss_indices, miss_texts, vectors):
                _cache_set(text, vec)
                results[idx] = vec

            logger.info(
                "EmbeddingService: fetched %d embeddings (%d cache hits)",
                len(miss_texts),
                len(texts) - len(miss_texts),
            )

        return results  # type: ignore

    async def embed_single(self, text: str) -> list[float]:
        cached = _cache_get(text)
        if cached is not None:
            return cached

        result = await self.embed_texts([text])
        return result[0]