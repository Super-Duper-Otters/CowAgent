# encoding:utf-8
from pathlib import Path

from .storage import get_storage_dirs


def builtin_components_root() -> Path:
    return Path.cwd() / "builtin" / "components"


def runtime_components_root() -> Path:
    return get_storage_dirs()["root"] / "components"


def runtime_component_root(component_key: str) -> Path:
    return runtime_components_root() / Path(str(component_key or "").strip()).name


def runtime_versions_root(component_key: str) -> Path:
    return runtime_component_root(component_key) / "versions"
