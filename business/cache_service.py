# encoding:utf-8
"""CowAgent business cache facade.

The storage schema is still the existing investment cache table, but new
business handlers should depend on this module instead of investment internals.
"""

from business.investment.business_cache import (
    clear_business_cache,
    get_cached_business_result,
    invalidate_business_cache,
    write_business_cache,
)
from business.investment.cache_service import (
    CACHE_STATUS_ACTIVE,
    CACHE_STATUS_INVALIDATED,
    CacheEntry,
    build_cache_key,
    clear_cache_entries,
    find_cache_entry,
    find_cache_entry_by_key,
    find_latest_cache_entry,
    increment_cache_hit,
    invalidate_cache_entry,
    list_cache_entries,
    list_cache_entries_page,
    list_generated_history_market_dates,
    list_generated_history_page,
    version_fingerprint,
    write_cache_entry,
)

