# encoding:utf-8
from importlib import import_module

from business.artifacts.artifacts import *  # noqa: F401,F403

_artifacts = import_module("business.artifacts.artifacts")


def __getattr__(name):
    return getattr(_artifacts, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_artifacts)))
