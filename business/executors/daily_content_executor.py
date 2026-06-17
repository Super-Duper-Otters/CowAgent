# encoding:utf-8
from business.constants import ServiceType


def get_daily_content_business(service_type: ServiceType, *, module_key: str = ""):
    from business.daily_content import get_latest_effective_content

    return get_latest_effective_content(service_type, module_key=module_key)
