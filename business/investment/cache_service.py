# encoding:utf-8
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import and_, desc, insert, select, update

from .constants import ServiceType
from .db import connect, row_to_dict
from .schema import investment_cache_entries


CACHE_STATUS_ACTIVE = "active"
CACHE_STATUS_INVALIDATED = "invalidated"


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


def _files_available(paths: list[str]) -> bool:
    return bool(paths) and all(Path(path).is_file() for path in paths)


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
        return None
    return entry


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
        updated = conn.execute(
            update(investment_cache_entries)
            .where(investment_cache_entries.c.cache_key == cache_key)
            .values(**values)
        ).rowcount
        if not updated:
            conn.execute(insert(investment_cache_entries).values(**values, created_at=now, hit_count=0))
    return CacheEntry(
        cache_key=cache_key,
        service_type=service_type,
        normalized_target=normalized_target,
        market_date=market_date,
        version_fingerprint=version_fingerprint,
        output_files=output_files,
        artifact_owner_id=artifact_owner_id,
        status=CACHE_STATUS_ACTIVE,
        hit_count=0,
        created_at=now,
        updated_at=now,
    )


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
    conditions = []
    if service_type is not None:
        conditions.append(investment_cache_entries.c.service_type == str(service_type))
    if market_date:
        conditions.append(investment_cache_entries.c.market_date == market_date)
    if not include_invalidated:
        conditions.append(investment_cache_entries.c.status == CACHE_STATUS_ACTIVE)
    stmt = select(investment_cache_entries)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.order_by(desc(investment_cache_entries.c.updated_at)).limit(limit)
    with connect() as conn:
        rows = conn.execute(stmt).fetchall()
    return [_row_to_entry(row) for row in rows]
