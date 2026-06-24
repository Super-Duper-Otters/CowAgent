# encoding:utf-8
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import and_, desc, func, or_, select, update

from business.schema.db import connect, row_to_dict
from business.schema.tables import investment_products


PRODUCT_STATUS_ACTIVE = "active"
PRODUCT_STATUS_INVALIDATED = "invalidated"
PRODUCT_STATUS_ARCHIVED = "archived"
PRODUCT_STATUS_FAILED = "failed"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _json_list(values: list[str] | None) -> str:
    return json.dumps(values or [], ensure_ascii=False)


def _json_object(value: dict | str | None) -> str:
    if value is None:
        return "{}"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _load_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        loaded = json.loads(value)
    except Exception:
        return []
    if isinstance(loaded, list):
        return [str(item) for item in loaded]
    return []


def _load_metadata(value: str | None) -> dict | str:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except Exception:
        return value
    return loaded if isinstance(loaded, dict) else value


def _text(value) -> str:
    return str(value or "").strip()


def product_logical_key(
    *,
    business_type: str,
    target_key: str,
    business_date: str,
    version_fingerprint: str,
) -> str:
    parts = [
        _text(business_type),
        _text(target_key).upper(),
        _text(business_date),
        _text(version_fingerprint),
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"{parts[0]}:{parts[1]}:{parts[2]}:{digest}"


def _row_to_product(row) -> dict:
    item = row_to_dict(row)
    metadata_value = item.get("product_metadata")
    if metadata_value is None:
        metadata_value = item.get("metadata")
    return {
        "product_id": item["product_id"],
        "business_type": item["business_type"],
        "target_key": item["target_key"],
        "target_label": item.get("target_label") or "",
        "business_date": item.get("business_date") or "",
        "logical_key": item["logical_key"],
        "version_fingerprint": item.get("version_fingerprint") or "",
        "status": item["status"],
        "source_request_id": item.get("source_request_id") or "",
        "source_content_id": item.get("source_content_id") or "",
        "source_cache_key": item.get("source_cache_key") or "",
        "source_type": item.get("source_type") or "",
        "source_files": _load_list(item.get("source_files")),
        "output_files": _load_list(item.get("output_files")),
        "text_content": item.get("text_content") or "",
        "metadata": _load_metadata(metadata_value),
        "hit_count": int(item.get("hit_count") or 0),
        "expires_at": item.get("expires_at") or "",
        "effective_at": item.get("effective_at") or "",
        "invalidated_at": item.get("invalidated_at") or "",
        "archived_at": item.get("archived_at") or "",
        "created_at": item.get("created_at") or "",
        "updated_at": item.get("updated_at") or "",
    }


def _expires_at_condition(now: str):
    return or_(
        investment_products.c.expires_at.is_(None),
        investment_products.c.expires_at == "",
        investment_products.c.expires_at > now,
    )


def _files_available(paths: list[str]) -> bool:
    return all(Path(path).is_file() for path in paths)


def _active_product_conditions(
    *,
    business_type: str,
    target_key: str,
    business_date: str = "",
    version_fingerprint: str = "",
) -> list:
    conditions = [
        investment_products.c.business_type == _text(business_type),
        investment_products.c.target_key == _text(target_key),
        investment_products.c.status == PRODUCT_STATUS_ACTIVE,
    ]
    if business_date:
        conditions.append(investment_products.c.business_date == _text(business_date))
    if version_fingerprint:
        conditions.append(investment_products.c.version_fingerprint == _text(version_fingerprint))
    return conditions


def create_product(
    *,
    business_type: str,
    target_key: str,
    target_label: str = "",
    business_date: str = "",
    version_fingerprint: str = "",
    status: str = PRODUCT_STATUS_ACTIVE,
    source_request_id: str = "",
    source_content_id: str = "",
    source_cache_key: str = "",
    source_type: str = "",
    source_files: list[str] | None = None,
    output_files: list[str] | None = None,
    text_content: str = "",
    metadata: dict | str | None = None,
    expires_at: str = "",
    effective_at: str = "",
    archived_at: str = "",
) -> dict:
    now = _now()
    logical_key = product_logical_key(
        business_type=business_type,
        target_key=target_key,
        business_date=business_date,
        version_fingerprint=version_fingerprint,
    )
    product_id = f"prod_{uuid4().hex}"
    values = {
        "product_id": product_id,
        "business_type": _text(business_type),
        "target_key": _text(target_key),
        "target_label": _text(target_label),
        "business_date": _text(business_date),
        "logical_key": logical_key,
        "version_fingerprint": _text(version_fingerprint),
        "status": _text(status) or PRODUCT_STATUS_ACTIVE,
        "source_request_id": _text(source_request_id),
        "source_content_id": _text(source_content_id),
        "source_cache_key": _text(source_cache_key),
        "source_type": _text(source_type),
        "source_files": _json_list(source_files),
        "output_files": _json_list(output_files),
        "text_content": text_content or "",
        "product_metadata": _json_object(metadata),
        "hit_count": 0,
        "expires_at": _text(expires_at),
        "effective_at": _text(effective_at),
        "invalidated_at": "",
        "archived_at": _text(archived_at),
        "created_at": now,
        "updated_at": now,
    }
    with connect() as conn:
        conn.execute(investment_products.insert().values(**values))
        row = conn.execute(select(investment_products).where(investment_products.c.product_id == product_id)).fetchone()
    return _row_to_product(row)


def find_active_product(
    *,
    business_type: str,
    target_key: str,
    business_date: str = "",
    version_fingerprint: str = "",
) -> dict | None:
    now = _now()
    conditions = _active_product_conditions(
        business_type=business_type,
        target_key=target_key,
        business_date=business_date,
        version_fingerprint=version_fingerprint,
    )
    conditions.append(_expires_at_condition(now))
    stmt = (
        select(investment_products)
        .where(and_(*conditions))
        .order_by(desc(investment_products.c.effective_at), desc(investment_products.c.created_at))
        .limit(1)
    )
    with connect() as conn:
        row = conn.execute(stmt).fetchone()
    if row is None:
        return None
    product = _row_to_product(row)
    if not _files_available(product["output_files"]):
        _invalidate_product_if_unchanged(product)
        return None
    return product


def invalidate_active_products(
    *,
    business_type: str,
    target_key: str,
    business_date: str = "",
    version_fingerprint: str = "",
) -> int:
    now = _now()
    conditions = _active_product_conditions(
        business_type=business_type,
        target_key=target_key,
        business_date=business_date,
        version_fingerprint=version_fingerprint,
    )
    with connect() as conn:
        return int(
            conn.execute(
                update(investment_products)
                .where(and_(*conditions))
                .values(
                    status=PRODUCT_STATUS_INVALIDATED,
                    invalidated_at=now,
                    updated_at=now,
                )
            ).rowcount
            or 0
        )


def increment_product_hit(product_id: str) -> None:
    with connect() as conn:
        conn.execute(
            update(investment_products)
            .where(investment_products.c.product_id == product_id)
            .values(
                hit_count=investment_products.c.hit_count + 1,
                updated_at=_now(),
            )
        )


def _invalidate_product_if_unchanged(product: dict) -> bool:
    now = _now()
    with connect() as conn:
        return bool(
            conn.execute(
                update(investment_products)
                .where(
                    investment_products.c.product_id == product["product_id"],
                    investment_products.c.status == PRODUCT_STATUS_ACTIVE,
                    investment_products.c.output_files == _json_list(product["output_files"]),
                    investment_products.c.updated_at == product["updated_at"],
                    investment_products.c.version_fingerprint == product["version_fingerprint"],
                )
                .values(
                    status=PRODUCT_STATUS_INVALIDATED,
                    invalidated_at=now,
                    updated_at=now,
                )
            ).rowcount
        )


def list_products_page(
    *,
    page: int = 1,
    page_size: int = 50,
    include_invalidated: bool = False,
    business_type: str = "",
    target_key: str = "",
    business_date: str = "",
    start_date: str = "",
    end_date: str = "",
) -> tuple[list[dict], int]:
    page = max(1, int(page or 1))
    page_size = max(1, int(page_size or 50))
    offset = (page - 1) * page_size
    conditions = []
    if business_type:
        conditions.append(investment_products.c.business_type == _text(business_type))
    if target_key:
        conditions.append(investment_products.c.target_key == _text(target_key))
    if business_date:
        conditions.append(investment_products.c.business_date == _text(business_date))
    else:
        if start_date:
            conditions.append(investment_products.c.business_date >= _text(start_date))
        if end_date:
            conditions.append(investment_products.c.business_date <= _text(end_date))
    if not include_invalidated:
        conditions.append(investment_products.c.status == PRODUCT_STATUS_ACTIVE)
    stmt = select(investment_products)
    count_stmt = select(func.count()).select_from(investment_products)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))
    stmt = stmt.order_by(desc(investment_products.c.created_at), desc(investment_products.c.product_id)).limit(page_size).offset(offset)
    with connect() as conn:
        total = int(conn.execute(count_stmt).scalar_one() or 0)
        rows = conn.execute(stmt).fetchall()
    return [_row_to_product(row) for row in rows], total
