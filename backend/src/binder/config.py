"""Binder configuration, read from the environment (BINDER_ prefix)."""

import os
import sys
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    """Usual application data location on each operating system."""
    home = Path.home()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        return (Path(base) if base else home / "AppData" / "Local") / "Binder"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Binder"
    base = os.environ.get("XDG_DATA_HOME")
    return (Path(base) if base else home / ".local" / "share") / "binder"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BINDER_", env_file=".env", extra="ignore")

    data_dir: Path = _default_data_dir()
    # Encryption key. When absent, a key is generated in data_dir/key (mode 0600).
    db_key: str | None = None

    ollama_url: str = "http://localhost:11434"
    llm_model: str = "qwen3.5:9b"
    # Disables the LLM entirely (tests, machines without Ollama).
    llm_enabled: bool = True
    # Generous: on CPU only, a 9B model takes 1 to 3 minutes per document.
    llm_timeout: float = 300.0
    # Context window asked of Ollama (its default, 4096 tokens, silently cuts the start of an
    # agent conversation: system prompt, tools, page images).
    llm_context: int = 16384
    # How long Ollama keeps the model in memory after a request (fast follow-up questions).
    llm_keep_alive: str = "30m"
    # Vision: scans and photos are also shown to the model as images, when it supports them.
    llm_vision: bool = True
    # Small multilingual model for semantic search ("proof of address" finds the EDF bill).
    embed_model: str = "qwen3-embedding:0.6b"
    # Reasoning before each agent step (slower, rarely better on short requests).
    llm_think: bool = False

    # Background automatic import (watched folder, mailbox).
    auto_import: bool = True

    # Desktop app update at launch, from GitHub releases.
    auto_update: bool = True
    update_url: str = "https://api.github.com/repos/Razigue/Binder/releases/latest"

    # System locale override, e.g. "fr_FR" (default: detected from the operating system).
    locale: str | None = None

    host: str = "127.0.0.1"
    # Required in a cookie by the API when set (the desktop app draws one at each launch).
    access_token: str | None = None
    port: int = 8765
    # Phone scanning: HTTPS server on the local network, open only during a scan session.
    scan_port: int = 8766

    @property
    def db_path(self) -> Path:
        return self.data_dir / "binder.db"

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"


@lru_cache
def get_settings() -> Settings:
    return Settings()
