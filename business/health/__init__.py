# encoding:utf-8
from importlib import import_module

from business.health.health import *  # noqa: F401,F403

_health = import_module("business.health.health")

_PATCHABLE_NAMES = (
    "_dependency_available",
    "_has_chinese_font",
    "_check_playwright_chromium",
    "_run_technical_analysis_smoke",
    "_run_renderer_smoke_checks",
    "importlib",
)


def _sync_patchable_names():
    for name in _PATCHABLE_NAMES:
        if name in globals():
            setattr(_health, name, globals()[name])


def run_health_checks(*args, **kwargs):
    _sync_patchable_names()
    return _health.run_health_checks(*args, **kwargs)


def _check_dependency(*args, **kwargs):
    _sync_patchable_names()
    return _health._check_dependency(*args, **kwargs)


def __getattr__(name):
    return getattr(_health, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_health)))
