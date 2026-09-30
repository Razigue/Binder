"""Configuration de Binder, lue depuis l'environnement (préfixe BINDER_)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    return Path.home() / ".local" / "share" / "binder"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BINDER_", env_file=".env", extra="ignore")

    data_dir: Path = _default_data_dir()
    # Clé de chiffrement. Si absente, une clé est générée dans data_dir/key (droits 0600).
    db_key: str | None = None

    ollama_url: str = "http://localhost:11434"
    llm_model: str = "qwen3.5:9b"
    # Désactive complètement le LLM (tests, machines sans Ollama).
    llm_enabled: bool = True
    # Large : sur CPU seul, un modèle 9B met 1 à 3 minutes par document.
    llm_timeout: float = 300.0

    host: str = "127.0.0.1"
    port: int = 8765

    @property
    def db_path(self) -> Path:
        return self.data_dir / "binder.db"

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"


@lru_cache
def get_settings() -> Settings:
    return Settings()
