# encoding:utf-8
"""CowAgent business job deduplication facade."""

from business.investment.job_service import (
    JobStartResult,
    find_running_cache_job,
    find_running_job,
    start_cache_job_if_absent,
    start_job_if_absent,
    start_job_if_absent_with_metadata,
)

