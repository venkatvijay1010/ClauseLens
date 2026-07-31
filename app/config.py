"""Environment-backed settings with safe, offline defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    upload_dir: Path
    max_upload_bytes: int
    max_extracted_chars: int
    max_sections_per_version: int
    max_changed_sections: int
    max_assessment_calls: int
    llm_provider: str
    ollama_base_url: str
    ollama_model: str
    openai_api_key: str | None
    openai_model: str
    llm_timeout_seconds: float


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./docudiff.db"),
        upload_dir=Path(os.getenv("UPLOAD_DIR", "./uploads")),
        max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", "5242880")),
        max_extracted_chars=int(os.getenv("MAX_EXTRACTED_CHARS", "500000")),
        max_sections_per_version=int(os.getenv("MAX_SECTIONS_PER_VERSION", "250")),
        max_changed_sections=int(os.getenv("MAX_CHANGED_SECTIONS", "100")),
        max_assessment_calls=int(os.getenv("MAX_ASSESSMENT_CALLS", "10")),
        llm_provider=os.getenv("LLM_PROVIDER", "heuristic").lower(),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "gemma3"),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "15")),
    )
