"""
PaperSignal — Central Configuration
All tunables live here. Nothing is hardcoded in business logic.
"""
'''
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List
from pathlib import Path

ROOT = Path(__file__).parent.parent


class Settings(BaseSettings):

    # ── App ──────────────────────────────────────────────────────────
    APP_NAME: str = "PaperSignal"
    ENV: str = Field(default="development")
    LOG_LEVEL: str = "INFO"

    # ── Database ─────────────────────────────────────────────────────
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./papersignal.db")
    CHROMA_PATH: str = Field(default=str(ROOT / "data" / "chroma"))
    CHROMA_COLLECTION: str = "papers"

    # ── ArXiv Scraper ────────────────────────────────────────────────
    ARXIV_CATEGORIES: List[str] = Field(default=["cs.AI", "cs.LG", "cs.CL", "cs.CV", "stat.ML"])
    ARXIV_MAX_RESULTS: int = 100
    ARXIV_POLL_HOURS: int = 6
    ARXIV_DAYS_BACK: int = 7

    # ── Embeddings ───────────────────────────────────────────────────
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_BATCH_SIZE: int = 32

    # ── Clustering ───────────────────────────────────────────────────
    HDBSCAN_MIN_CLUSTER_SIZE: int = 3
    HDBSCAN_MIN_SAMPLES: int = 2
    UMAP_N_COMPONENTS: int = 5
    UMAP_N_NEIGHBORS: int = 10

    # ── Velocity Scoring ─────────────────────────────────────────────
    GITHUB_TOKEN: str = ""
    VELOCITY_WINDOW_DAYS: int = 7
    VELOCITY_STAR_WEIGHT: float = 0.6
    VELOCITY_CITATION_WEIGHT: float = 0.4

    # ── LLMs (Phase 2) ───────────────────────────────────────────────
    GROQ_API_KEY: str = Field(default="")
    OPENAI_API_KEY: str = Field(default="")

    # Agent 1 & 3 — fast tasks (classify, summarize)
    GROQ_FAST_MODEL: str = "llama-3.3-70b-versatile"
    # Final fallback
    OPENAI_FALLBACK_MODEL: str = "gpt-4o-mini"

    LLM_MAX_TOKENS: int = 1024
    RAG_TOP_K: int = 5

    # ── Phase 3 — HuggingFace Models ─────────────────────────────────
    HF_API_KEY: str = ""
    # Agent 2 — DeepSeek-R1 reasoning via HF inference router
    HF_REASONING_MODEL: str = "deepseek-ai/DeepSeek-R1-Distill-Llama-8B:nscale"
    # Hype detector — GRPO fine-tuned model
    HF_HYPE_MODEL: str = "shau1905/papersignal-hype-detector"

    # ── API ───────────────────────────────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_RELOAD: bool = False

    class Config:
        env_file = str(ROOT / ".env")
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()'''


"""
Paper2Signal — Central Configuration
All tunables live here. Nothing is hardcoded in business logic.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List
from pathlib import Path

ROOT = Path(__file__).parent.parent


class Settings(BaseSettings):

    # ── App ──────────────────────────────────────────────────────────
    APP_NAME: str = "Paper2Signal"
    ENV: str = Field(default="development")
    LOG_LEVEL: str = "INFO"

    # ── Database ─────────────────────────────────────────────────────
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./papersignal.db")
    CHROMA_PATH: str = Field(default=str(ROOT / "data" / "chroma"))
    CHROMA_COLLECTION: str = "papers"

    # ── ArXiv Scraper ────────────────────────────────────────────────
    ARXIV_CATEGORIES: List[str] = Field(
        default=["cs.AI", "cs.LG", "cs.CL", "cs.CV", "stat.ML"]
    )
    ARXIV_MAX_RESULTS: int = 100
    ARXIV_POLL_HOURS: int = 6
    ARXIV_DAYS_BACK: int = 7

    # ── Embeddings ───────────────────────────────────────────────────
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_BATCH_SIZE: int = 32

    # ── Clustering ───────────────────────────────────────────────────
    HDBSCAN_MIN_CLUSTER_SIZE: int = 3
    HDBSCAN_MIN_SAMPLES: int = 2
    UMAP_N_COMPONENTS: int = 5
    UMAP_N_NEIGHBORS: int = 10

    # ── Velocity Scoring ─────────────────────────────────────────────
    GITHUB_TOKEN: str = ""
    VELOCITY_WINDOW_DAYS: int = 7
    VELOCITY_STAR_WEIGHT: float = 0.6
    VELOCITY_CITATION_WEIGHT: float = 0.4

    # ── LLMs ─────────────────────────────────────────────────────────
    GROQ_API_KEY: str = Field(default="")
    OPENAI_API_KEY: str = Field(default="")

    # Agent 1 & 3 — fast tasks
    GROQ_FAST_MODEL: str = "llama-3.3-70b-versatile"
    # Fallback
    OPENAI_FALLBACK_MODEL: str = "gpt-4o-mini"

    LLM_MAX_TOKENS: int = 1024
    RAG_TOP_K: int = 5

    # ── HuggingFace Models ────────────────────────────────────────────
    HF_API_KEY: str = ""
    # Agent 2 — DeepSeek-R1 reasoning via HF router
    HF_REASONING_MODEL: str = "deepseek-ai/DeepSeek-R1-Distill-Llama-8B:nscale"
    # Hype detector — GRPO fine-tuned model
    HF_HYPE_MODEL: str = "shau1905/papersignal-hype-detector"

    # ── PageIndex — deep paper chat ───────────────────────────────────
    # Get key at: pageindex.ai
    # Used for: full PDF indexing + reasoning-based chat
    PAGEINDEX_API_KEY: str = ""

    # ── API ───────────────────────────────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_RELOAD: bool = False

    class Config:
        env_file = str(ROOT / ".env")
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()