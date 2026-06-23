# encoding:utf-8
from importlib import import_module

from business.schema.tables import *  # noqa: F401,F403

_tables = import_module("business.schema.tables")


def __getattr__(name):
    return getattr(_tables, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_tables)))
