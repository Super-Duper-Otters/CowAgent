# encoding:utf-8
"""Compatibility wrapper for the CowAgent business router."""

from business.router import (
    DEFAULT_UNMATCHED_PROMPT,
    RUNNING_JOB_PROMPT,
    BusinessReply,
    RouteResult,
    _customer_metadata,
    handle_text_message,
    parse_route,
)

__all__ = [
    "DEFAULT_UNMATCHED_PROMPT",
    "RUNNING_JOB_PROMPT",
    "BusinessReply",
    "RouteResult",
    "_customer_metadata",
    "handle_text_message",
    "parse_route",
]
