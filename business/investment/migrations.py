# encoding:utf-8
from pathlib import Path

from alembic import command
from alembic.config import Config


def alembic_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "migrations" / "investment" / "alembic.ini"


def upgrade(revision: str = "head") -> None:
    command.upgrade(Config(str(alembic_config_path())), revision)
