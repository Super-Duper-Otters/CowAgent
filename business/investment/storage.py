# encoding:utf-8
import os
import sqlite3
from pathlib import Path

from config import get_appdata_dir


def _storage_root() -> Path:
    env_root = os.environ.get("COWAGENT_INVESTMENT_STORAGE_ROOT")
    if env_root:
        return Path(env_root)
    return Path(get_appdata_dir()) / "investment"


def get_storage_dirs() -> dict[str, Path]:
    root = _storage_root()
    return {
        "root": root,
        "uploads": root / "uploads",
        "generated": root / "generated",
        "technical_analysis": root / "technical-analysis",
    }


def get_db_path() -> Path:
    env_path = os.environ.get("COWAGENT_INVESTMENT_DB_PATH")
    if env_path:
        return Path(env_path)
    return _storage_root() / "investment.db"


def get_connection() -> sqlite3.Connection:
    initialize_storage()
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def initialize_storage() -> None:
    dirs = get_storage_dirs()
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    if not os.environ.get("COWAGENT_INVESTMENT_DATABASE_URL", "").strip():
        db_path = get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
    from .db import get_engine
    from .schema import metadata

    metadata.create_all(get_engine())
