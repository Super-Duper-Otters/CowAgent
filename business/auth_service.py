# encoding:utf-8
import sys
from business.accounts import auth_service as _module
_name = __name__
globals().update(_module.__dict__)
sys.modules[_name] = _module


