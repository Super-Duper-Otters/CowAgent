# encoding:utf-8
import sys
from business.content import prompt_to_image_handler as _module
_name = __name__
globals().update(_module.__dict__)
sys.modules[_name] = _module


