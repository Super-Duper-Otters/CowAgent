# encoding:utf-8
import hashlib
import itertools
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import and_, desc, func, or_, select, update

from business.schema.db import connect, row_to_dict
from business.schema.tables import investment_products, investment_request_records


PRODUCT_STATUS_ACTIVE = "active"
PRODUCT_STATUS_INVALIDATED = "invalidated"
PRODUCT_STATUS_ARCHIVED = "archived"
PRODUCT_STATUS_FAILED = "failed"
_PRODUCT_ID_COUNTER = itertools.count(1)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _canonical_utc_timestamp(value: str) -> str:
    text = _text(value)
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid timestamp: {text}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def _new_product_id() -> str:
    return f"prod_{next(_PRODUCT_ID_COUNTER):020d}_{uuid4().hex}"


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


def _keyword_like_pattern(keyword: str) -> str:
    text = _text(keyword).lower()
    text = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{text}%"


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
    canonical_now = _canonical_utc_timestamp(now)
    return or_(
        investment_products.c.expires_at.is_(None),
        investment_products.c.expires_at == "",
        investment_products.c.expires_at > canonical_now,
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


def _product_values(
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
    created_at: str = "",
    updated_at: str = "",
) -> tuple[str, dict]:
    now = _now()
    logical_key = product_logical_key(
        business_type=business_type,
        target_key=target_key,
        business_date=business_date,
        version_fingerprint=version_fingerprint,
    )
    product_id = _new_product_id()
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
        "expires_at": _canonical_utc_timestamp(expires_at),
        "effective_at": _text(effective_at),
        "invalidated_at": "",
        "archived_at": _text(archived_at),
        "created_at": _text(created_at) or now,
        "updated_at": _text(updated_at) or now,
    }
    return product_id, values


def _create_product_on_connection(conn, **kwargs) -> dict:
    product_id, values = _product_values(**kwargs)
    conn.execute(investment_products.insert().values(**values))
    row = conn.execute(select(investment_products).where(investment_products.c.product_id == product_id)).fetchone()
    return _row_to_product(row)


def _existing_product_for_source(
    *,
    source_request_id: str = "",
    source_cache_key: str = "",
    source_content_id: str = "",
    conn=None,
) -> dict | None:
    conditions = []
    if source_request_id:
        conditions.append(investment_products.c.source_request_id == _text(source_request_id))
    if source_cache_key:
        conditions.append(investment_products.c.source_cache_key == _text(source_cache_key))
    if source_content_id:
        conditions.append(investment_products.c.source_content_id == _text(source_content_id))
    if not conditions:
        return None
    stmt = select(investment_products).where(or_(*conditions)).order_by(desc(investment_products.c.created_at)).limit(1)
    if conn is not None:
        row = conn.execute(stmt).fetchone()
        return _row_to_product(row) if row is not None else None
    with connect() as active_conn:
        row = active_conn.execute(stmt).fetchone()
        return _row_to_product(row) if row is not None else None


def product_exists_for_source(
    *,
    source_request_id: str = "",
    source_cache_key: str = "",
    source_content_id: str = "",
    conn=None,
) -> bool:
    return _existing_product_for_source(
        source_request_id=source_request_id,
        source_cache_key=source_cache_key,
        source_content_id=source_content_id,
        conn=conn,
    ) is not None


def _request_product_business_type(service_type: str, module_key: str) -> str:
    if _text(service_type) == "unmatched" and _text(module_key):
        return f"component:{_text(module_key)}"
    return _text(service_type)


def _is_effective_content_delivery_request(item: dict) -> bool:
    action_type = _text(item.get("action_type"))
    if action_type:
        return action_type == "deliver_effective_content"
    return _text(item.get("service_type")) in {"rate", "convertible_bond"}


def _request_product_target(item: dict, explicit_target: str = "", explicit_label: str = "") -> tuple[str, str]:
    target_key = (
        _text(explicit_target)
        or _text(item.get("normalized_target"))
        or _text(item.get("stock_code"))
        or _text(item.get("module_key"))
        or _text(item.get("raw_input"))
    )
    target_label = (
        _text(explicit_label)
        or _text(item.get("stock_name"))
        or _text(item.get("normalized_target"))
        or _text(item.get("stock_code"))
        or _text(item.get("raw_input"))
        or target_key
    )
    return target_key, target_label


def create_product_from_success_request(
    request_id: str,
    *,
    target_key: str = "",
    target_label: str = "",
    business_date: str = "",
    version_fingerprint: str = "",
    conn=None,
) -> dict | None:
    normalized_request_id = _text(request_id)
    if not normalized_request_id:
        return None

    def _create(product_conn) -> dict | None:
        existing = _existing_product_for_source(source_request_id=normalized_request_id, conn=product_conn)
        if existing is not None:
            return existing
        row = product_conn.execute(
            select(investment_request_records).where(investment_request_records.c.request_id == normalized_request_id)
        ).fetchone()
        if row is None:
            return None
        item = row_to_dict(row)
        if _text(item.get("status")) != "success":
            return None
        if _is_effective_content_delivery_request(item):
            return None
        output_files = [path for path in _load_list(item.get("output_files")) if Path(path).is_file()]
        if not output_files:
            return None
        service_type = _text(item.get("service_type"))
        module_key = _text(item.get("module_key"))
        business_type = _request_product_business_type(service_type, module_key)
        if not business_type:
            return None
        resolved_target_key, resolved_target_label = _request_product_target(item, target_key, target_label)
        if not resolved_target_key:
            return None
        resolved_business_date = _text(business_date) or _text(item.get("market_date")) or _text(item.get("created_at"))[:10]
        resolved_version = _text(version_fingerprint) or _text(item.get("cache_key")) or normalized_request_id
        return _create_product_on_connection(
            product_conn,
            business_type=business_type,
            target_key=resolved_target_key,
            target_label=resolved_target_label,
            business_date=resolved_business_date,
            version_fingerprint=resolved_version,
            source_type="request",
            source_request_id=normalized_request_id,
            source_cache_key=_text(item.get("cache_key")),
            output_files=output_files,
            effective_at=_text(item.get("created_at")),
            created_at=_text(item.get("created_at")),
            updated_at=_text(item.get("updated_at")),
            metadata={"module_key": module_key} if module_key else {},
        )

    if conn is not None:
        return _create(conn)
    with connect() as product_conn:
        return _create(product_conn)


def _legacy_content_product_status(status: str) -> str:
    status_map = {
        "generated": PRODUCT_STATUS_ACTIVE,
        "effective": PRODUCT_STATUS_ACTIVE,
        "archived": PRODUCT_STATUS_ARCHIVED,
        "generate_failed": PRODUCT_STATUS_FAILED,
        "invalidated": PRODUCT_STATUS_INVALIDATED,
    }
    return status_map.get(_text(status), "")


def backfill_products_from_legacy_sources(conn=None) -> dict[str, int]:
    from business.schema.tables import investment_daily_contents

    def _backfill(product_conn) -> dict[str, int]:
        created_cache = 0
        created_content = 0
        created_request = 0

        content_rows = product_conn.execute(select(investment_daily_contents)).fetchall()
        for row in content_rows:
            item = row_to_dict(row)
            content_id = str(item.get("content_id") or "")
            if not content_id or product_exists_for_source(source_content_id=content_id, conn=product_conn):
                continue
            status = str(item.get("status") or "")
            product_status = _legacy_content_product_status(status)
            output_image = str(item.get("output_image") or "")
            generated_text = str(item.get("generated_text") or "")
            if not product_status or not (output_image or generated_text):
                continue
            _create_product_on_connection(
                product_conn,
                business_type=str(item.get("service_type") or ""),
                target_key=str(item.get("service_type") or ""),
                target_label=str(item.get("service_type") or ""),
                business_date=str(item.get("effective_date") or ""),
                version_fingerprint=f"v{item.get('content_version') or 1}",
                source_type="content",
                source_content_id=content_id,
                output_files=[output_image] if output_image else [],
                text_content=generated_text,
                status=product_status,
                expires_at=str(item.get("expires_at") or ""),
                effective_at=str(item.get("effective_at") or item.get("created_at") or ""),
                created_at=str(item.get("created_at") or ""),
                updated_at=str(item.get("updated_at") or ""),
            )
            created_content += 1

        request_rows = product_conn.execute(select(investment_request_records)).fetchall()
        for row in request_rows:
            item = row_to_dict(row)
            request_id = str(item.get("request_id") or "")
            if not request_id or product_exists_for_source(source_request_id=request_id, conn=product_conn):
                continue
            product = create_product_from_success_request(request_id, conn=product_conn)
            if product is not None:
                created_request += 1
        return {"cache_created": created_cache, "content_created": created_content, "request_created": created_request}

    if conn is not None:
        return _backfill(conn)
    with connect() as product_conn:
        return _backfill(product_conn)


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
    with connect() as conn:
        return _create_product_on_connection(
            conn,
            business_type=business_type,
            target_key=target_key,
            target_label=target_label,
            business_date=business_date,
            version_fingerprint=version_fingerprint,
            status=status,
            source_request_id=source_request_id,
            source_content_id=source_content_id,
            source_cache_key=source_cache_key,
            source_type=source_type,
            source_files=source_files,
            output_files=output_files,
            text_content=text_content,
            metadata=metadata,
            expires_at=expires_at,
            effective_at=effective_at,
            archived_at=archived_at,
        )


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
        .order_by(
            desc(investment_products.c.effective_at),
            desc(investment_products.c.created_at),
            desc(investment_products.c.product_id),
        )
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


def _archive_active_products_on_connection(
    conn,
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
    return int(
        conn.execute(
            update(investment_products)
            .where(and_(*conditions))
            .values(
                status=PRODUCT_STATUS_ARCHIVED,
                archived_at=now,
                updated_at=now,
            )
        ).rowcount
        or 0
    )


def archive_active_products(
    *,
    business_type: str,
    target_key: str,
    business_date: str = "",
    version_fingerprint: str = "",
    conn=None,
) -> int:
    if conn is not None:
        return _archive_active_products_on_connection(
            conn,
            business_type=business_type,
            target_key=target_key,
            business_date=business_date,
            version_fingerprint=version_fingerprint,
        )
    with connect() as product_conn:
        return _archive_active_products_on_connection(
            product_conn,
            business_type=business_type,
            target_key=target_key,
            business_date=business_date,
            version_fingerprint=version_fingerprint,
        )


def create_product_archiving_active(*, conn=None, **kwargs) -> dict:
    def _create(product_conn) -> dict:
        _archive_active_products_on_connection(
            product_conn,
            business_type=kwargs["business_type"],
            target_key=kwargs["target_key"],
            business_date=kwargs.get("business_date", ""),
        )
        return _create_product_on_connection(product_conn, **kwargs)

    if conn is not None:
        return _create(conn)
    with connect() as product_conn:
        return _create(product_conn)


def _invalidate_prior_active_products_on_connection(
    conn,
    *,
    business_type: str,
    target_key: str,
    exclude_product_id: str,
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
    conditions.append(investment_products.c.product_id != _text(exclude_product_id))
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


def invalidate_active_products_except(
    *,
    business_type: str,
    target_key: str,
    exclude_product_id: str,
    business_date: str = "",
    version_fingerprint: str = "",
) -> int:
    with connect() as conn:
        return _invalidate_prior_active_products_on_connection(
            conn,
            business_type=business_type,
            target_key=target_key,
            business_date=business_date,
            version_fingerprint=version_fingerprint,
            exclude_product_id=exclude_product_id,
        )


def replace_active_product(
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
    conn=None,
) -> dict:
    def _replace(product_conn) -> dict:
        product = _create_product_on_connection(
            product_conn,
            business_type=business_type,
            target_key=target_key,
            target_label=target_label,
            business_date=business_date,
            version_fingerprint=version_fingerprint,
            status=status,
            source_request_id=source_request_id,
            source_content_id=source_content_id,
            source_cache_key=source_cache_key,
            source_type=source_type,
            source_files=source_files,
            output_files=output_files,
            text_content=text_content,
            metadata=metadata,
            expires_at=expires_at,
            effective_at=effective_at,
            archived_at=archived_at,
        )
        _invalidate_prior_active_products_on_connection(
            product_conn,
            business_type=business_type,
            target_key=target_key,
            business_date=business_date,
            version_fingerprint=version_fingerprint,
            exclude_product_id=product["product_id"],
        )
        return product

    if conn is not None:
        return _replace(conn)
    with connect() as product_conn:
        return _replace(product_conn)


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


def invalidate_product_if_unchanged(product: dict) -> bool:
    return _invalidate_product_if_unchanged(product)


def invalidate_product(product_id: str) -> bool:
    normalized_product_id = _text(product_id)
    if not normalized_product_id:
        return False
    now = _now()
    with connect() as conn:
        return bool(
            conn.execute(
                update(investment_products)
                .where(
                    and_(
                        investment_products.c.product_id == normalized_product_id,
                        investment_products.c.status != PRODUCT_STATUS_INVALIDATED,
                    )
                )
                .values(
                    status=PRODUCT_STATUS_INVALIDATED,
                    invalidated_at=now,
                    updated_at=now,
                )
            ).rowcount
        )


def _product_scope_conditions(
    *,
    business_type: str = "",
    business_date: str = "",
    start_date: str = "",
    end_date: str = "",
) -> list:
    conditions = []
    if business_type:
        conditions.append(investment_products.c.business_type == _text(business_type))
    if business_date:
        conditions.append(investment_products.c.business_date == _text(business_date))
    else:
        if start_date:
            conditions.append(investment_products.c.business_date >= _text(start_date))
        if end_date:
            conditions.append(investment_products.c.business_date <= _text(end_date))
    return conditions


def invalidate_products_by_scope(
    *,
    business_type: str = "",
    business_date: str = "",
    start_date: str = "",
    end_date: str = "",
) -> int:
    conditions = _product_scope_conditions(
        business_type=business_type,
        business_date=business_date,
        start_date=start_date,
        end_date=end_date,
    )
    conditions.append(investment_products.c.status == PRODUCT_STATUS_ACTIVE)
    now = _now()
    stmt = (
        update(investment_products)
        .where(and_(*conditions))
        .values(
            status=PRODUCT_STATUS_INVALIDATED,
            invalidated_at=now,
            updated_at=now,
        )
    )
    with connect() as conn:
        return int(conn.execute(stmt).rowcount or 0)


def invalidate_products_by_source(*, source_content_id: str = "", source_cache_key: str = "", conn=None) -> int:
    normalized_source_content_id = _text(source_content_id)
    normalized_source_cache_key = _text(source_cache_key)
    conditions = []
    if normalized_source_content_id:
        conditions.append(investment_products.c.source_content_id == normalized_source_content_id)
    if normalized_source_cache_key:
        conditions.append(investment_products.c.source_cache_key == normalized_source_cache_key)
    if not conditions:
        return 0

    def _invalidate(product_conn) -> int:
        now = _now()
        return int(
            product_conn.execute(
                update(investment_products)
                .where(
                    and_(
                        or_(*conditions),
                        investment_products.c.status == PRODUCT_STATUS_ACTIVE,
                    )
                )
                .values(
                    status=PRODUCT_STATUS_INVALIDATED,
                    invalidated_at=now,
                    updated_at=now,
                )
            ).rowcount
            or 0
        )

    if conn is not None:
        return _invalidate(conn)
    with connect() as product_conn:
        return _invalidate(product_conn)


def update_products_expires_at_by_source(*, source_content_id: str, expires_at: str = "", conn=None) -> int:
    normalized_source_content_id = _text(source_content_id)
    if not normalized_source_content_id:
        return 0
    canonical_expires_at = _canonical_utc_timestamp(expires_at)

    def _update(product_conn) -> int:
        now = _now()
        values = {
            "expires_at": canonical_expires_at,
            "updated_at": now,
        }
        if canonical_expires_at and canonical_expires_at <= now:
            values.update(
                status=PRODUCT_STATUS_INVALIDATED,
                invalidated_at=now,
            )
        return int(
            product_conn.execute(
                update(investment_products)
                .where(
                    and_(
                        investment_products.c.source_content_id == normalized_source_content_id,
                        investment_products.c.status != PRODUCT_STATUS_INVALIDATED,
                    )
                )
                .values(**values)
            ).rowcount
            or 0
        )

    if conn is not None:
        return _update(conn)
    with connect() as product_conn:
        return _update(product_conn)


def find_active_product_by_id(product_id: str) -> dict | None:
    normalized_product_id = _text(product_id)
    if not normalized_product_id:
        return None
    now = _now()
    stmt = (
        select(investment_products)
        .where(
            and_(
                investment_products.c.product_id == normalized_product_id,
                investment_products.c.status == PRODUCT_STATUS_ACTIVE,
                _expires_at_condition(now),
            )
        )
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


def _product_to_cache_entry_dict(product: dict) -> dict:
    return {
        "product_id": str(product.get("product_id") or ""),
        "cache_key": str(product.get("source_cache_key") or ""),
        "service_type": str(product.get("business_type") or ""),
        "normalized_target": str(product.get("target_key") or ""),
        "market_date": str(product.get("business_date") or ""),
        "version_fingerprint": str(product.get("version_fingerprint") or ""),
        "output_files": list(product.get("output_files") or []),
        "artifact_owner_id": str(product.get("source_request_id") or ""),
        "status": str(product.get("status") or ""),
        "hit_count": int(product.get("hit_count") or 0),
        "created_at": str(product.get("created_at") or ""),
        "updated_at": str(product.get("updated_at") or ""),
    }


def find_product_cache_entry_by_key(cache_key: str, *, require_files: bool = True) -> dict | None:
    normalized_cache_key = _text(cache_key)
    if not normalized_cache_key:
        return None
    now = _now()
    stmt = (
        select(investment_products)
        .where(
            and_(
                investment_products.c.source_cache_key == normalized_cache_key,
                investment_products.c.status == PRODUCT_STATUS_ACTIVE,
                _expires_at_condition(now),
            )
        )
        .order_by(desc(investment_products.c.updated_at), desc(investment_products.c.created_at))
        .limit(1)
    )
    with connect() as conn:
        row = conn.execute(stmt).fetchone()
    if row is None:
        return None
    product = _row_to_product(row)
    if require_files and not _files_available(product["output_files"]):
        _invalidate_product_if_unchanged(product)
        return None
    return _product_to_cache_entry_dict(product)


def find_product_cache_entry(
    *,
    service_type,
    normalized_target: str,
    version_fingerprint: str,
    market_date: str = "",
    require_files: bool = True,
) -> dict | None:
    if not market_date:
        return None
    now = _now()
    stmt = (
        select(investment_products)
        .where(
            and_(
                investment_products.c.business_type == str(service_type),
                investment_products.c.target_key == _text(normalized_target),
                investment_products.c.business_date == _text(market_date),
                investment_products.c.version_fingerprint == _text(version_fingerprint),
                investment_products.c.status == PRODUCT_STATUS_ACTIVE,
                _expires_at_condition(now),
            )
        )
        .order_by(desc(investment_products.c.updated_at), desc(investment_products.c.created_at))
        .limit(1)
    )
    with connect() as conn:
        row = conn.execute(stmt).fetchone()
    if row is None:
        return None
    product = _row_to_product(row)
    if require_files and not _files_available(product["output_files"]):
        _invalidate_product_if_unchanged(product)
        return None
    return _product_to_cache_entry_dict(product)


def find_active_product_by_source_content_id(source_content_id: str) -> dict | None:
    normalized_source_content_id = _text(source_content_id)
    if not normalized_source_content_id:
        return None
    now = _now()
    stmt = (
        select(investment_products)
        .where(
            and_(
                investment_products.c.source_content_id == normalized_source_content_id,
                investment_products.c.status == PRODUCT_STATUS_ACTIVE,
                _expires_at_condition(now),
            )
        )
        .order_by(
            desc(investment_products.c.effective_at),
            desc(investment_products.c.created_at),
            desc(investment_products.c.product_id),
        )
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
    keyword: str = "",
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
    normalized_keyword = _text(keyword).lower()
    if normalized_keyword:
        pattern = _keyword_like_pattern(normalized_keyword)
        conditions.append(
            or_(
                func.lower(investment_products.c.product_id).like(pattern, escape="\\"),
                func.lower(investment_products.c.business_type).like(pattern, escape="\\"),
                func.lower(investment_products.c.target_key).like(pattern, escape="\\"),
                func.lower(investment_products.c.target_label).like(pattern, escape="\\"),
                func.lower(investment_products.c.business_date).like(pattern, escape="\\"),
                func.lower(investment_products.c.version_fingerprint).like(pattern, escape="\\"),
                func.lower(investment_products.c.source_request_id).like(pattern, escape="\\"),
                func.lower(investment_products.c.source_content_id).like(pattern, escape="\\"),
                func.lower(investment_products.c.source_cache_key).like(pattern, escape="\\"),
                func.lower(investment_products.c.source_type).like(pattern, escape="\\"),
                func.lower(investment_products.c.text_content).like(pattern, escape="\\"),
            )
        )
    if not include_invalidated:
        conditions.append(investment_products.c.status == PRODUCT_STATUS_ACTIVE)
        conditions.append(_expires_at_condition(_now()))
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


def list_products_cache_history_page(
    *,
    page: int = 1,
    page_size: int = 50,
    include_invalidated: bool = False,
    business_type: str = "",
    target_key: str = "",
    business_date: str = "",
    start_date: str = "",
    end_date: str = "",
    keyword: str = "",
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
    normalized_keyword = _text(keyword).lower()
    if normalized_keyword:
        pattern = _keyword_like_pattern(normalized_keyword)
        conditions.append(
            or_(
                func.lower(investment_products.c.product_id).like(pattern, escape="\\"),
                func.lower(investment_products.c.business_type).like(pattern, escape="\\"),
                func.lower(investment_products.c.target_key).like(pattern, escape="\\"),
                func.lower(investment_products.c.target_label).like(pattern, escape="\\"),
                func.lower(investment_products.c.business_date).like(pattern, escape="\\"),
                func.lower(investment_products.c.version_fingerprint).like(pattern, escape="\\"),
                func.lower(investment_products.c.source_request_id).like(pattern, escape="\\"),
                func.lower(investment_products.c.source_content_id).like(pattern, escape="\\"),
                func.lower(investment_products.c.source_cache_key).like(pattern, escape="\\"),
                func.lower(investment_products.c.source_type).like(pattern, escape="\\"),
                func.lower(investment_products.c.text_content).like(pattern, escape="\\"),
            )
        )
    if not include_invalidated:
        conditions.append(investment_products.c.status == PRODUCT_STATUS_ACTIVE)
        conditions.append(_expires_at_condition(_now()))
    stmt = select(investment_products)
    count_stmt = select(func.count()).select_from(investment_products)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))
    stmt = (
        stmt.order_by(
            desc(investment_products.c.updated_at),
            desc(investment_products.c.business_date),
            desc(investment_products.c.created_at),
            desc(investment_products.c.product_id),
        )
        .limit(page_size)
        .offset(offset)
    )
    with connect() as conn:
        total = int(conn.execute(count_stmt).scalar_one() or 0)
        rows = conn.execute(stmt).fetchall()
    return [_row_to_product(row) for row in rows], total


def list_product_business_dates(business_type: str = "", include_invalidated: bool = False) -> list[str]:
    conditions = [investment_products.c.business_date != ""]
    if business_type:
        conditions.append(investment_products.c.business_type == _text(business_type))
    if not include_invalidated:
        conditions.append(investment_products.c.status == PRODUCT_STATUS_ACTIVE)
        conditions.append(_expires_at_condition(_now()))
    stmt = (
        select(investment_products.c.business_date)
        .where(and_(*conditions))
        .distinct()
        .order_by(desc(investment_products.c.business_date))
    )
    with connect() as conn:
        return [str(row[0]) for row in conn.execute(stmt).fetchall() if row[0]]
