import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Gemini ──────────────────────────────────────────────────────────────
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_TEMPERATURE: float = 0.1

    # ── Ollama (local LLM — free, no API key) ────────────────────────────────
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "glm4"          # run: ollama list  to check your name
    OLLAMA_ENABLED: bool = True
    OLLAMA_TIMEOUT: int = 30

    # ── Research tuning ──────────────────────────────────────────────────────
    MAX_SUBTOPICS: int = 5
    MIN_SUBTOPICS: int = 3
    MAX_SECTIONS: int = 6
    MAX_PER_DOMAIN: int = 3
    MAX_RAW_SOURCES: int = 60
    MAX_ITERATIONS: int = 2             # critic-triggered retry loops
    CONFIDENCE_THRESHOLD: float = 0.65  # below this → retry

    # ── Storage ──────────────────────────────────────────────────────────────
    EVIDENCE_STORE_PATH: str = "./data/evidence_store"
    DB_PATH: str = "./data/research.db"
    EXPORT_PATH: str = "./exports"

    # ── Embeddings ───────────────────────────────────────────────────────────
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"

    # ── Server ───────────────────────────────────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    def ensure_dirs(self):
        for path in [self.EVIDENCE_STORE_PATH, self.EXPORT_PATH, "./data"]:
            os.makedirs(path, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
