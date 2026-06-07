# encoding:utf-8
from ..constants import ServiceType


def get_daily_content_business(service_type: ServiceType):
    from ..daily_content import get_latest_effective_content

    return get_latest_effective_content(service_type)
