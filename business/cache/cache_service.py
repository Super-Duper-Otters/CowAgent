# encoding:utf-8
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import and_, desc, func, or_, select, update

from business.config.constants import ServiceType, Status
from business.schema.db import connect, row_to_dict
from business.schema.tables import investment_cache_entries, investment_daily_contents


CACHE_STATUS_ACTIVE = "active"
CACHE_STATUS_INVALIDATED = "invalidated"
DEFAULT_LATEST_CACHE_FALLBACK_DAYS = 7

SERVICE_KEYWORD_LABELS = {
    ServiceType.TECHNICAL_ANALYSIS: "技术分析 技术分析内容",
    ServiceType.RATE: "利率 利率内容",
    ServiceType.CONVERTIBLE_BOND: "转债 可转债 转债内容",
}


@dataclass
class CacheEntry:
    cache_key: str
    service_type: ServiceType
    normalized_target: str
    market_date: str
    version_fingerprint: str
    output_files: list[str]
    artifact_owner_id: str = ""
    status: str = CACHE_STATUS_ACTIVE
    hit_count: int = 0
    created_at: str = ""
    updated_at: str = ""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _today() -> date:
    return date.today()


def version_fingerprint(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(str(part or "").encode("utf-8"))
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()[:16]}"


def build_cache_key(
    service_type: ServiceType,
    normalized_target: str,
    market_date: str,
    version: str,
) -> str:
    raw = "|".join([str(service_type), normalized_target.upper(), market_date, version])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"{service_type}:{normalized_target.upper()}:{market_date}:{digest}"


def _json_list(values: list[str]) -> str:
    return json.dumps(values or [], ensure_ascii=False)


def _load_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        return list(json.loads(value))
    except Exception:
        return []


def _row_to_entry(row) -> CacheEntry:
    item = row_to_dict(row)
    return CacheEntry(
        cache_key=item["cache_key"],
        service_type=ServiceType(item["service_type"]),
        normalized_target=item["normalized_target"] or "",
        market_date=item["market_date"] or "",
        version_fingerprint=item["version_fingerprint"] or "",
        output_files=_load_list(item["output_files"]),
        artifact_owner_id=item.get("artifact_owner_id") or "",
        status=item["status"] or CACHE_STATUS_ACTIVE,
        hit_count=int(item.get("hit_count") or 0),
        created_at=item.get("created_at") or "",
        updated_at=item.get("updated_at") or "",
    )


def _cache_entry_to_history(entry: CacheEntry) -> dict:
    return {
        "source_type": "cache",
        "cache_key": entry.cache_key,
        "service_type": str(entry.service_type),
        "normalized_target": entry.normalized_target,
        "market_date": entry.market_date,
        "effective_date": entry.market_date,
        "version_fingerprint": entry.version_fingerprint,
        "output_files": entry.output_files,
        "artifact_owner_id": entry.artifact_owner_id,
        "status": entry.status,
        "hit_count": entry.hit_count,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }


def _content_target_label(service_type: ServiceType) -> str:
    if service_type == ServiceType.RATE:
        return "利率内容"
    if service_type == ServiceType.CONVERTIBLE_BOND:
        return "转债内容"
    return "后台内容"


def _content_row_to_history(row) -> dict:
    item = row_to_dict(row)
    service_type = ServiceType(item["service_type"])
    output_image = item.get("output_image") or ""
    effective_date = item.get("effective_date") or ""
    content_version = int(item.get("content_version") or 1)
    status = item.get("status") or ""
    if _content_expires_at_expired(item.get("expires_at") or ""):
        status = CACHE_STATUS_INVALIDATED
    return {
        "source_type": "content",
        "cache_key": "",
        "content_id": item["content_id"],
        "service_type": str(service_type),
        "normalized_target": _content_target_label(service_type),
        "market_date": effective_date,
        "effective_date": effective_date,
        "version_fingerprint": f"v{content_version}",
        "output_files": [output_image] if output_image else [],
        "output_image": output_image,
        "source_files": _load_list(item.get("source_files")),
        "source_text": item.get("source_text") or "",
        "generated_text": item.get("generated_text") or "",
        "artifact_owner_id": item["content_id"],
        "status": status,
        "hit_count": 0,
        "operator": item.get("operator") or "",
        "created_at": item.get("created_at") or "",
        "updated_at": item.get("updated_at") or item.get("created_at") or "",
        "content_version": content_version,
        "expires_at": item.get("expires_at") or "",
    }


def _content_expires_at_expired(expires_at: str, *, now: str | None = None) -> bool:
    text = str(expires_at or "").strip()
    if not text:
        return False
    now_text = now or _now()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        parsed_now = datetime.fromisoformat(now_text.replace("Z", "+00:00"))
    except ValueError:
        return text <= now_text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    if parsed_now.tzinfo is None:
        parsed_now = parsed_now.replace(tzinfo=UTC)
    return parsed <= parsed_now


def _history_sort_key(entry: dict) -> tuple[str, str]:
    return (str(entry.get("updated_at") or entry.get("created_at") or ""), str(entry.get("market_date") or ""))


def _keyword_like_pattern(keyword: str) -> str:
    text = str(keyword or "").strip()
    text = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{text}%"


def _service_keyword_matches(service_column, keyword: str) -> list:
    text = str(keyword or "").strip().lower()
    if not text:
        return []
    matches = []
    for service_type, label in SERVICE_KEYWORD_LABELS.items():
        if text in str(service_type).lower() or text in label.lower():
            matches.append(service_column == str(service_type))
    return matches


def _keyword_match_condition(keyword: str, columns: list, service_column):
    text = str(keyword or "").strip()
    if not text:
        return None
    pattern = _keyword_like_pattern(text)
    conditions = [column.ilike(pattern, escape="\\") for column in columns]
    conditions.extend(_service_keyword_matches(service_column, text))
    return or_(*conditions)


def _content_history_conditions(
    *,
    service_type: ServiceType | None = None,
    market_date: str = "",
    start_date: str = "",
    end_date: str = "",
    keyword: str = "",
    include_invalidated: bool = False,
) -> list:
    conditions = []
    if service_type is not None:
        if service_type == ServiceType.TECHNICAL_ANALYSIS:
            conditions.append(investment_daily_contents.c.service_type == "__none__")
        else:
            conditions.append(investment_daily_contents.c.service_type == str(service_type))
    else:
        conditions.append(
            investment_daily_contents.c.service_type.in_(
                [str(ServiceType.RATE), str(ServiceType.CONVERTIBLE_BOND)]
            )
        )
    if market_date:
        conditions.append(investment_daily_contents.c.effective_date == market_date)
    else:
        if start_date:
            conditions.append(investment_daily_contents.c.effective_date >= start_date)
        if end_date:
            conditions.append(investment_daily_contents.c.effective_date <= end_date)
    if not include_invalidated:
        conditions.append(
            investment_daily_contents.c.status.in_([str(Status.GENERATED), str(Status.EFFECTIVE)])
        )
        now = _now()
        conditions.append(
            investment_daily_contents.c.expires_at.is_(None)
            | (investment_daily_contents.c.expires_at == "")
            | (investment_daily_contents.c.expires_at > now)
        )
    keyword_condition = _keyword_match_condition(
        keyword,
        [
            investment_daily_contents.c.content_id,
            investment_daily_contents.c.service_type,
            investment_daily_contents.c.source_files,
            investment_daily_contents.c.source_text,
            investment_daily_contents.c.generated_text,
            investment_daily_contents.c.output_image,
            investment_daily_contents.c.status,
            investment_daily_contents.c.operator,
            investment_daily_contents.c.effective_date,
            investment_daily_contents.c.expires_at,
        ],
        investment_daily_contents.c.service_type,
    )
    if keyword_condition is not None:
        conditions.append(keyword_condition)
    return conditions


def _list_content_history_page(
    *,
    limit: int,
    service_type: ServiceType | None = None,
    market_date: str = "",
    start_date: str = "",
    end_date: str = "",
    keyword: str = "",
    include_invalidated: bool = False,
) -> tuple[list[dict], int]:
    conditions = _content_history_conditions(
        service_type=service_type,
        market_date=market_date,
        start_date=start_date,
        end_date=end_date,
        keyword=keyword,
        include_invalidated=include_invalidated,
    )
    stmt = select(investment_daily_contents)
    count_stmt = select(func.count()).select_from(investment_daily_contents)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))
    stmt = stmt.order_by(desc(investment_daily_contents.c.updated_at)).limit(max(1, int(limit or 1)))
    with connect() as conn:
        total = int(conn.execute(count_stmt).scalar_one() or 0)
        rows = conn.execute(stmt).fetchall()
    return [_content_row_to_history(row) for row in rows], total


def _files_available(paths: list[str]) -> bool:
    return bool(paths) and all(Path(path).is_file() for path in paths)


def _market_date_in_fallback_window(market_date: str, *, reference_date: date, max_age_days: int) -> bool:
    try:
        parsed = date.fromisoformat(market_date)
    except ValueError:
        return False
    age_days = (reference_date - parsed).days
    return 0 <= age_days <= max_age_days


def find_cache_entry(
    *,
    service_type: ServiceType,
    normalized_target: str,
    version_fingerprint: str,
    market_date: str = "",
    require_files: bool = True,
) -> CacheEntry | None:
    if not market_date:
        return None
    conditions = [
        investment_cache_entries.c.service_type == str(service_type),
        investment_cache_entries.c.normalized_target == normalized_target,
        investment_cache_entries.c.market_date == market_date,
        investment_cache_entries.c.version_fingerprint == version_fingerprint,
        investment_cache_entries.c.status == CACHE_STATUS_ACTIVE,
    ]
    stmt = (
        select(investment_cache_entries)
        .where(and_(*conditions))
        .order_by(desc(investment_cache_entries.c.market_date), desc(investment_cache_entries.c.updated_at))
        .limit(1)
    )
    with connect() as conn:
        row = conn.execute(stmt).fetchone()
    if row is None:
        return None
    entry = _row_to_entry(row)
    if require_files and not _files_available(entry.output_files):
        _invalidate_cache_entry_if_unchanged(entry)
        return None
    return entry


def find_cache_entry_by_key(
    cache_key: str,
    *,
    require_files: bool = True,
) -> CacheEntry | None:
    if not cache_key:
        return None
    stmt = (
        select(investment_cache_entries)
        .where(
            investment_cache_entries.c.cache_key == cache_key,
            investment_cache_entries.c.status == CACHE_STATUS_ACTIVE,
        )
        .limit(1)
    )
    with connect() as conn:
        row = conn.execute(stmt).fetchone()
    if row is None:
        return None
    entry = _row_to_entry(row)
    if require_files and not _files_available(entry.output_files):
        _invalidate_cache_entry_if_unchanged(entry)
        return None
    return entry


def find_latest_cache_entry(
    *,
    service_type: ServiceType,
    normalized_target: str,
    version_fingerprint: str,
    max_age_days: int = DEFAULT_LATEST_CACHE_FALLBACK_DAYS,
    require_files: bool = True,
) -> CacheEntry | None:
    conditions = [
        investment_cache_entries.c.service_type == str(service_type),
        investment_cache_entries.c.normalized_target == normalized_target,
        investment_cache_entries.c.version_fingerprint == version_fingerprint,
        investment_cache_entries.c.status == CACHE_STATUS_ACTIVE,
    ]
    stmt = (
        select(investment_cache_entries)
        .where(and_(*conditions))
        .order_by(desc(investment_cache_entries.c.market_date), desc(investment_cache_entries.c.updated_at))
    )
    reference_date = _today()
    with connect() as conn:
        rows = conn.execute(stmt).fetchall()
    for row in rows:
        entry = _row_to_entry(row)
        if not _market_date_in_fallback_window(
            entry.market_date,
            reference_date=reference_date,
            max_age_days=max_age_days,
        ):
            continue
        if require_files and not _files_available(entry.output_files):
            _invalidate_cache_entry_if_unchanged(entry)
            continue
        return entry
    return None


def increment_cache_hit(cache_key: str) -> None:
    with connect() as conn:
        conn.execute(
            update(investment_cache_entries)
            .where(investment_cache_entries.c.cache_key == cache_key)
            .values(
                hit_count=investment_cache_entries.c.hit_count + 1,
                updated_at=_now(),
            )
        )


def write_cache_entry(
    *,
    cache_key: str,
    service_type: ServiceType,
    normalized_target: str,
    market_date: str,
    version_fingerprint: str,
    output_files: list[str],
    artifact_owner_id: str = "",
) -> CacheEntry:
    now = _now()
    values = {
        "cache_key": cache_key,
        "service_type": str(service_type),
        "normalized_target": normalized_target,
        "market_date": market_date,
        "version_fingerprint": version_fingerprint,
        "output_files": _json_list(output_files),
        "artifact_owner_id": artifact_owner_id,
        "status": CACHE_STATUS_ACTIVE,
        "updated_at": now,
    }
    with connect() as conn:
        table = investment_cache_entries
        from sqlalchemy.dialects.postgresql import insert

        stmt = insert(table).values(**values, created_at=now, hit_count=0)
        stmt = stmt.on_conflict_do_update(
            index_elements=[table.c.cache_key],
            set_={
                "service_type": stmt.excluded.service_type,
                "normalized_target": stmt.excluded.normalized_target,
                "market_date": stmt.excluded.market_date,
                "version_fingerprint": stmt.excluded.version_fingerprint,
                "output_files": stmt.excluded.output_files,
                "artifact_owner_id": stmt.excluded.artifact_owner_id,
                "status": stmt.excluded.status,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        conn.execute(stmt)
        row = conn.execute(select(table).where(table.c.cache_key == cache_key)).fetchone()
    return _row_to_entry(row)


def invalidate_cache_entry(cache_key: str) -> bool:
    with connect() as conn:
        return bool(
            conn.execute(
                update(investment_cache_entries)
                .where(
                    investment_cache_entries.c.cache_key == cache_key,
                    investment_cache_entries.c.status == CACHE_STATUS_ACTIVE,
                )
                .values(status=CACHE_STATUS_INVALIDATED, updated_at=_now())
            ).rowcount
        )


def _invalidate_cache_entry_if_unchanged(entry: CacheEntry) -> bool:
    with connect() as conn:
        return bool(
            conn.execute(
                update(investment_cache_entries)
                .where(
                    investment_cache_entries.c.cache_key == entry.cache_key,
                    investment_cache_entries.c.status == CACHE_STATUS_ACTIVE,
                    investment_cache_entries.c.output_files == _json_list(entry.output_files),
                    investment_cache_entries.c.updated_at == entry.updated_at,
                    investment_cache_entries.c.version_fingerprint == entry.version_fingerprint,
                    investment_cache_entries.c.artifact_owner_id == entry.artifact_owner_id,
                )
                .values(status=CACHE_STATUS_INVALIDATED, updated_at=_now())
            ).rowcount
        )


def clear_cache_entries(*, service_type: ServiceType | None = None, market_date: str = "") -> int:
    conditions = [investment_cache_entries.c.status == CACHE_STATUS_ACTIVE]
    if service_type is not None:
        conditions.append(investment_cache_entries.c.service_type == str(service_type))
    if market_date:
        conditions.append(investment_cache_entries.c.market_date == market_date)
    with connect() as conn:
        return int(
            conn.execute(
                update(investment_cache_entries)
                .where(and_(*conditions))
                .values(status=CACHE_STATUS_INVALIDATED, updated_at=_now())
            ).rowcount
            or 0
        )


def list_cache_entries(
    *,
    limit: int = 50,
    service_type: ServiceType | None = None,
    market_date: str = "",
    include_invalidated: bool = False,
) -> list[CacheEntry]:
    entries, _total = list_cache_entries_page(
        page=1,
        page_size=limit,
        service_type=service_type,
        market_date=market_date,
        include_invalidated=include_invalidated,
    )
    return entries


def list_cache_entries_page(
    *,
    page: int = 1,
    page_size: int = 50,
    service_type: ServiceType | None = None,
    market_date: str = "",
    start_date: str = "",
    end_date: str = "",
    keyword: str = "",
    include_invalidated: bool = False,
) -> tuple[list[CacheEntry], int]:
    page = max(1, int(page or 1))
    page_size = max(1, int(page_size or 50))
    offset = (page - 1) * page_size
    conditions = []
    if service_type is not None:
        conditions.append(investment_cache_entries.c.service_type == str(service_type))
    if market_date:
        conditions.append(investment_cache_entries.c.market_date == market_date)
    else:
        if start_date:
            conditions.append(investment_cache_entries.c.market_date >= start_date)
        if end_date:
            conditions.append(investment_cache_entries.c.market_date <= end_date)
    if not include_invalidated:
        conditions.append(investment_cache_entries.c.status == CACHE_STATUS_ACTIVE)
    keyword_condition = _keyword_match_condition(
        keyword,
        [
            investment_cache_entries.c.cache_key,
            investment_cache_entries.c.service_type,
            investment_cache_entries.c.normalized_target,
            investment_cache_entries.c.market_date,
            investment_cache_entries.c.version_fingerprint,
            investment_cache_entries.c.output_files,
            investment_cache_entries.c.artifact_owner_id,
            investment_cache_entries.c.status,
        ],
        investment_cache_entries.c.service_type,
    )
    if keyword_condition is not None:
        conditions.append(keyword_condition)
    stmt = select(investment_cache_entries)
    count_stmt = select(func.count()).select_from(investment_cache_entries)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))
    stmt = stmt.order_by(desc(investment_cache_entries.c.updated_at)).limit(page_size).offset(offset)
    with connect() as conn:
        total = int(conn.execute(count_stmt).scalar_one() or 0)
        rows = conn.execute(stmt).fetchall()
    return [_row_to_entry(row) for row in rows], total


def list_generated_history_page(
    *,
    page: int = 1,
    page_size: int = 50,
    service_type: ServiceType | None = None,
    market_date: str = "",
    start_date: str = "",
    end_date: str = "",
    keyword: str = "",
    include_invalidated: bool = False,
) -> tuple[list[dict], int]:
    from business.content.daily_content import mark_expired_daily_contents_invalidated

    mark_expired_daily_contents_invalidated()
    page = max(1, int(page or 1))
    page_size = max(1, int(page_size or 50))
    offset = (page - 1) * page_size
    source_limit = offset + page_size
    cache_entries, _cache_total = list_cache_entries_page(
        page=1,
        page_size=source_limit,
        service_type=service_type,
        market_date=market_date,
        start_date=start_date,
        end_date=end_date,
        keyword=keyword,
        include_invalidated=include_invalidated,
    )
    history = [_cache_entry_to_history(entry) for entry in cache_entries]
    content_history, content_total = _list_content_history_page(
        limit=source_limit,
        service_type=service_type,
        market_date=market_date,
        start_date=start_date,
        end_date=end_date,
        keyword=keyword,
        include_invalidated=include_invalidated,
    )
    history.extend(content_history)
    history.sort(key=_history_sort_key, reverse=True)
    total = _cache_total + content_total
    return history[offset : offset + page_size], total


def list_cache_market_dates(
    *,
    limit: int = 30,
    service_type: ServiceType | None = None,
    include_invalidated: bool = False,
) -> list[str]:
    conditions = [investment_cache_entries.c.market_date != ""]
    if service_type is not None:
        conditions.append(investment_cache_entries.c.service_type == str(service_type))
    if not include_invalidated:
        conditions.append(investment_cache_entries.c.status == CACHE_STATUS_ACTIVE)
    stmt = (
        select(investment_cache_entries.c.market_date)
        .where(and_(*conditions))
        .distinct()
        .order_by(desc(investment_cache_entries.c.market_date))
        .limit(limit)
    )
    with connect() as conn:
        rows = conn.execute(stmt).fetchall()
    return [str(row_to_dict(row).get("market_date") or "") for row in rows if row_to_dict(row).get("market_date")]


def list_generated_history_market_dates(
    *,
    limit: int = 30,
    service_type: ServiceType | None = None,
    include_invalidated: bool = False,
) -> list[str]:
    from business.content.daily_content import mark_expired_daily_contents_invalidated

    mark_expired_daily_contents_invalidated()
    dates = set(list_cache_market_dates(limit=limit, service_type=service_type, include_invalidated=include_invalidated))
    if service_type == ServiceType.TECHNICAL_ANALYSIS:
        return sorted(dates, reverse=True)[:limit]
    content_conditions = _content_history_conditions(
        service_type=service_type,
        include_invalidated=include_invalidated,
    )
    content_conditions.append(investment_daily_contents.c.effective_date != "")
    stmt = (
        select(investment_daily_contents.c.effective_date)
        .where(and_(*content_conditions))
        .distinct()
        .order_by(desc(investment_daily_contents.c.effective_date))
        .limit(limit)
    )
    with connect() as conn:
        rows = conn.execute(stmt).fetchall()
    dates.update(str(row_to_dict(row).get("effective_date") or "") for row in rows if row_to_dict(row).get("effective_date"))
    return sorted(dates, reverse=True)[:limit]


from business.cache.business_cache import (  # noqa: E402
    clear_business_cache,
    get_cached_business_result,
    invalidate_business_cache,
    write_business_cache,
)
from business.cache.cache_policy import technical_analysis_cache_expired_after_close  # noqa: E402
