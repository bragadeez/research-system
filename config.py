import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Gemini (planning / synthesis / critique / extraction) ─────────────────
    GEMINI_API_KEY: str
    GEMINI_API_KEYS: str | None = None
    GEMINI_HIGH_REASONING_MODEL: str = "gemini-3.5-flash"
    GEMINI_VOLUME_MODEL: str = "gemini-3.1-flash-lite"
    GEMINI_MODEL: str = "gemini-3.5-flash"
    GEMINI_TEMPERATURE: float = 0.1

    # ── Groq (unused fallback) ────────────────────────────────────────────────
    GROQ_API_KEY: str | None = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # ── Research tuning ──────────────────────────────────────────────────────
    MAX_SUBTOPICS: int = 5
    MIN_SUBTOPICS: int = 3
    MAX_SECTIONS: int = 6
    MAX_PER_DOMAIN: int = 3
    MAX_RAW_SOURCES: int = 60
    MAX_ITERATIONS: int = 2             # critic-triggered retry loops
    CONFIDENCE_THRESHOLD: float = 0.65  # below this → retry

    # ── Search Providers ─────────────────────────────────────────────────────
    TAVILY_API_KEY: str | None = None
    SERPER_API_KEY: str | None = None

    # ── Storage ──────────────────────────────────────────────────────────────
    DB_PATH: str = "./data/research.db"
    EXPORT_PATH: str = "./exports"

    # ── Embeddings (source ranking + RAG) ─────────────────────────────────────
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"

    # ── Server ───────────────────────────────────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # ── Research Heavy Mode ───────────────────────────────────────────────────
    HEAVY_PAPER_THRESHOLD: int = 10        # top-K papers kept after citation scoring
    HEAVY_MIN_CITATIONS: int = 0           # minimum citations to include (0 = include all, ranked)
    HEAVY_MAX_SEARCH_RESULTS: int = 25     # fetch this many before filtering to top-K
    OPENALEX_EMAIL: str = "research@scholarnode.ai"  # required for OpenAlex polite pool

    # ── RAG Chatbot ───────────────────────────────────────────────────────────
    CHROMA_PATH: str = "./data/chroma"     # ChromaDB persistence directory
    RAG_CHUNK_SIZE: int = 800              # characters per chunk
    RAG_CHUNK_OVERLAP: int = 150           # overlap between chunks
    RAG_TOP_K: int = 5                     # retrieved chunks per query
    RAG_MAX_HISTORY: int = 6              # conversation turns kept in memory

    def ensure_dirs(self):
        for path in [self.EXPORT_PATH, "./data", self.CHROMA_PATH]:
            os.makedirs(path, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
