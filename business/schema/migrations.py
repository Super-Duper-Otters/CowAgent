# encoding:utf-8
from pathlib import Path

from alembic import command
from alembic.config import Config


def _alembic_option_value(value: str) -> str:
    return value.replace("%", "%%")


def alembic_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "migrations" / "business" / "alembic.ini"


def upgrade(revision: str = "head", database_url: str | None = None) -> None:
    config = Config(str(alembic_config_path()))
    if database_url:
        config.set_main_option("sqlalchemy.url", _alembic_option_value(database_url))
    command.upgrade(config, revision)
