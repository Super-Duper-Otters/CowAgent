# encoding:utf-8
import sys
from business.content import daily_content as _module
_name = __name__
globals().update(_module.__dict__)
sys.modules[_name] = _module


