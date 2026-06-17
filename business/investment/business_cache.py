# encoding:utf-8
from business.constants import ServiceType


def get_cached_business_result(
    *,
    cache_key: str = "",
    service_type: ServiceType | None = None,
    normalized_target: str = "",
    version_fingerprint: str = "",
    market_date: str = "",
    require_files: bool = True,
):
    from .cache_service import find_cache_entry, find_cache_entry_by_key

    if cache_key:
        return find_cache_entry_by_key(cache_key, require_files=require_files)
    if service_type is None:
        return None
    return find_cache_entry(
        service_type=service_type,
        normalized_target=normalized_target,
        version_fingerprint=version_fingerprint,
        market_date=market_date,
        require_files=require_files,
    )


def write_business_cache(
    *,
    cache_key: str,
    service_type: ServiceType,
    normalized_target: str,
    market_date: str,
    version_fingerprint: str,
    output_files: list[str],
    artifact_owner_id: str = "",
):
    from .cache_service import write_cache_entry

    return write_cache_entry(
        cache_key=cache_key,
        service_type=service_type,
        normalized_target=normalized_target,
        market_date=market_date,
        version_fingerprint=version_fingerprint,
        output_files=output_files,
        artifact_owner_id=artifact_owner_id,
    )


def invalidate_business_cache(cache_key: str) -> bool:
    from .cache_service import invalidate_cache_entry

    return invalidate_cache_entry(cache_key)


def clear_business_cache(*, service_type: ServiceType | None = None, market_date: str = "") -> int:
    from .cache_service import clear_cache_entries

    return clear_cache_entries(service_type=service_type, market_date=market_date)
