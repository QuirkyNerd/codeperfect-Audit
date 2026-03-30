"""
config.py – Central application configuration for CodePerfectAuditor.

Loads settings from environment variables / .env file using pydantic-settings.
All agents and services import from this module to avoid hardcoded values.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application-wide settings loaded from environment variables or .env file."""

    gemini_api_key: str = Field(..., env="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-1.5-flash", env="GEMINI_MODEL")
    embedding_model: str = Field(default="all-MiniLM-L6-v2", env="EMBEDDING_MODEL")
    database_url: str = Field(
        default="sqlite+aiosqlite:///./codeperfect.db", env="DATABASE_URL"
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0", env="REDIS_URL"
    )
    use_redis: bool = Field(default=True, env="USE_REDIS")

    phi_encryption_key: str = Field(default="", env="PHI_ENCRYPTION_KEY")

    chroma_persist_dir: str = Field(
        default="./chroma_store", env="CHROMA_PERSIST_DIR"
    )
    chroma_collection_icd: str = Field(
        default="icd10_codes", env="CHROMA_COLLECTION_ICD"
    )
    chroma_collection_cpt: str = Field(
        default="cpt_codes", env="CHROMA_COLLECTION_CPT"
    )
    chroma_collection_guidelines: str = Field(
        default="coding_guidelines", env="CHROMA_COLLECTION_GUIDELINES"
    )
    chroma_collection_symptoms: str = Field(
        default="symptoms", env="CHROMA_COLLECTION_SYMPTOMS"
    )
    rag_hybrid_alpha: float = Field(default=0.8, env="RAG_HYBRID_ALPHA", description="Vector score weight")
    rag_hybrid_beta: float = Field(default=0.2, env="RAG_HYBRID_BETA", description="Keyword score weight")

    rag_top_k: int = Field(default=10, env="RAG_TOP_K")

    min_code_confidence: float = Field(default=0.65, env="MIN_CODE_CONFIDENCE")

    agent_max_retries: int = Field(default=2, env="AGENT_MAX_RETRIES")

    rate_limit_requests: int = Field(default=10, env="RATE_LIMIT_REQUESTS")
    rate_limit_window_seconds: int = Field(default=60, env="RATE_LIMIT_WINDOW_SECONDS")

    cache_max_size: int = Field(default=128, env="CACHE_MAX_SIZE")

    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:3000"],
        env="CORS_ORIGINS",
    )

    data_dir: str = Field(default="/app/backend/data", env="DATA_DIR")
    prompts_dir: str = Field(default="/app/backend/prompts", env="PROMPTS_DIR")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }
settings = Settings()