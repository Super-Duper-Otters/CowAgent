# encoding:utf-8
import os
from pathlib import Path

from config import get_appdata_dir

_MIGRATED_DATABASE_URL: str | None = None


def _storage_root() -> Path:
    env_root = os.environ.get("COWAGENT_INVESTMENT_STORAGE_ROOT")
    if env_root:
        return Path(env_root)
    return Path(get_appdata_dir()) / "investment"


def get_storage_dirs() -> dict[str, Path]:
    root = _storage_root()
    return {
        "root": root,
        "files": root / "files",
        "tmp": root / "tmp",
    }


def get_db_path() -> Path:
    env_path = os.environ.get("COWAGENT_INVESTMENT_DB_PATH")
    if env_path:
        return Path(env_path)
    return _storage_root() / "investment.db"


def get_connection():
    initialize_storage()
    from business.investment.db import get_engine

    return get_engine().raw_connection()


def initialize_storage() -> None:
    global _MIGRATED_DATABASE_URL
    dirs = get_storage_dirs()
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    from business.investment import migrations
    from business.investment.db import get_database_url

    database_url = get_database_url()
    if _MIGRATED_DATABASE_URL != database_url:
        migrations.upgrade("head")
        _MIGRATED_DATABASE_URL = database_url
        from business.investment.file_migration import migrate_legacy_files_to_unified_storage

        migrate_legacy_files_to_unified_storage()
