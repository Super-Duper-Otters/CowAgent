# encoding:utf-8
from business.schema.tables import *  # noqa: F401,F403
from business.schema import tables as _tables


def __getattr__(name):
    return getattr(_tables, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_tables)))
