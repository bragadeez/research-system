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

    # ── Embeddings (source ranking only) ─────────────────────────────────────
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"

    # ── Server ───────────────────────────────────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    def ensure_dirs(self):
        for path in [self.EXPORT_PATH, "./data"]:
            os.makedirs(path, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
