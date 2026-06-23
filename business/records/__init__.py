# encoding:utf-8
from business.records.records import *  # noqa: F401,F403
from business.records import records as _records


def __getattr__(name):
    return getattr(_records, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_records)))
