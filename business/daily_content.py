# encoding:utf-8
"""CowAgent business content facade.

The storage implementation still lives under the investment package during the
migration, but runtime callers should depend on this module.
"""

from business.investment.daily_content import (
    create_content_draft,
    generate_content,
    get_latest_effective_content,
    mark_expired_daily_contents_invalidated,
    mark_generation_started,
    save_source_file,
    set_content_effective,
    update_content_source,
    update_generation_failure,
    update_generation_success,
)
