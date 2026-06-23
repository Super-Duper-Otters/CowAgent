# encoding:utf-8
from importlib import import_module

from business.records.records import *  # noqa: F401,F403

_records = import_module("business.records.records")


def __getattr__(name):
    return getattr(_records, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_records)))
