# encoding:utf-8
"""Opt-in PostgreSQL integration tests for investment business storage.

Local run example:
docker run --name cowagent-pg -e POSTGRES_PASSWORD=cowagent -e POSTGRES_USER=cowagent -e POSTGRES_DB=cowagent -p 5432:5432 -d postgres:16
$env:COWAGENT_TEST_POSTGRES_URL="postgresql+psycopg://cowagent:cowagent@127.0.0.1:5432/cowagent"
py -m pytest tests/integration/test_business_postgres.py -q
"""

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


pytestmark = pytest.mark.skipif(
    not os.environ.get("COWAGENT_TEST_POSTGRES_URL"),
    reason="COWAGENT_TEST_POSTGRES_URL not configured",
)


@pytest.fixture()
def business_postgres_env(tmp_path, monkeypatch):
    pg_url = os.environ["COWAGENT_TEST_POSTGRES_URL"]
    schema_name = f"cowagent_it_{uuid4().hex}"
    url = make_url(pg_url)
    schema_url = url.set(
        query={
            **dict(url.query),
            "options": f"-csearch_path={schema_name}",
        },
    ).render_as_string(hide_password=False)
    admin_engine = create_engine(pg_url, future=True)
    with admin_engine.begin() as conn:
        conn.execute(text(f'create schema "{schema_name}"'))

    monkeypatch.setenv("COWAGENT_INVESTMENT_DATABASE_URL", schema_url)
    monkeypatch.setenv("COWAGENT_BUSINESS_STORAGE_ROOT", str(tmp_path / "storage"))

    from business.schema import db as db
    from business.schema import storage as storage
    db.reset_engine_for_tests()
    storage._MIGRATED_DATABASE_URL = None
    storage.initialize_storage()
    try:
        yield
    finally:
        db.reset_engine_for_tests()
        storage._MIGRATED_DATABASE_URL = None
        with admin_engine.begin() as conn:
            conn.execute(text(f'drop schema if exists "{schema_name}" cascade'))
        admin_engine.dispose()


def test_postgres_runs_critical_business_flows(business_postgres_env, tmp_path):
    from sqlalchemy import inspect

    from business.schema import storage as storage
    from business.config.config_service import get_config, save_config
    from business.config.constants import ErrorCode, ServiceType, Status
    from business.content.daily_content import create_content_draft, get_latest_effective_content, set_content_effective
    from business.schema.db import get_engine
    from business.records.records import (
        create_request_record,
        fail_request_record,
        get_request_record,
        list_request_records,
        succeed_request_record,
    )
    from business.content.stock_resolver import list_stock_symbols, refresh_stock_symbols, resolve_stock
    from business.accounts.user_service import create_user, get_user_by_openid, verify_permission

    suffix = uuid4().hex

    storage.initialize_storage()
    inspector = inspect(get_engine())
    assert inspector.has_table("configs")
    assert inspector.has_table("customers")
    assert inspector.has_table("request_records")
    assert inspector.has_table("content_records")
    assert inspector.has_table("artifacts")
    assert inspector.has_table("cache_entries")
    assert inspector.has_table("operation_audits")
    assert inspector.has_table("stock_symbols")
    assert inspector.has_table("alembic_version")
    with get_engine().connect() as conn:
        alembic_versions = [row[0] for row in conn.exec_driver_sql("select version_num from alembic_version").fetchall()]
    assert "20260527_0008" in alembic_versions
    request_record_columns = {column["name"] for column in inspector.get_columns("request_records")}
    assert {"normalized_target", "stock_code", "stock_name", "cache_key", "cache_hit"}.issubset(request_record_columns)
    daily_content_columns = {column["name"] for column in inspector.get_columns("content_records")}
    assert {
        "effective_date",
        "expires_at",
        "content_version",
        "direct_output_mode",
        "auto_effective_after_generate",
        "archived_at",
        "input_prompt",
    }.issubset(daily_content_columns)
    assert not inspector.has_table("internal_call_records")
    ai_audit_columns = {column["name"] for column in inspector.get_columns("ai_generation_audits")}
    assert {"input_prompt"}.issubset(ai_audit_columns)
    output_file_columns = {column["name"] for column in inspector.get_columns("artifacts")}
    assert {"artifact_role", "file_size", "file_hash", "version_tag"}.issubset(output_file_columns)
    cache_columns = {column["name"] for column in inspector.get_columns("cache_entries")}
    assert {
        "cache_key",
        "service_type",
        "normalized_target",
        "market_date",
        "version_fingerprint",
        "output_files",
        "artifact_owner_id",
        "status",
        "hit_count",
    }.issubset(cache_columns)
    cache_indexes = {index["name"]: tuple(index.get("column_names") or []) for index in inspector.get_indexes("cache_entries")}
    assert cache_indexes["idx_cache_entries_lookup"] == (
        "service_type",
        "normalized_target",
        "market_date",
        "version_fingerprint",
        "status",
    )
    assert cache_indexes["idx_cache_entries_service_date"] == ("service_type", "market_date", "status")
    assert inspector.has_table("products")
    product_columns = {column["name"] for column in inspector.get_columns("products")}
    assert {
        "product_id",
        "business_type",
        "target_key",
        "target_label",
        "business_date",
        "logical_key",
        "version_fingerprint",
        "status",
        "source_request_id",
        "source_content_id",
        "source_cache_key",
        "source_type",
        "source_files",
        "output_files",
        "text_content",
        "metadata",
        "hit_count",
        "expires_at",
        "effective_at",
        "invalidated_at",
        "archived_at",
        "created_at",
        "updated_at",
    }.issubset(product_columns)
    stock_pk = inspector.get_pk_constraint("stock_symbols").get("constrained_columns") or []
    stock_unique_columns = {
        tuple(item.get("column_names") or [])
        for item in inspector.get_unique_constraints("stock_symbols")
    }
    stock_unique_columns.update(
        tuple(index.get("column_names") or [])
        for index in inspector.get_indexes("stock_symbols")
        if index.get("unique")
    )
    assert stock_pk == ["code"] or ("code",) in stock_unique_columns

    secret_key = f"integration.secret.{suffix}"
    secret_value = f"sk-pg-{suffix}"
    save_config(secret_key, secret_value, operator_role="admin", operator="pg-test")
    assert get_config(secret_key) == secret_value
    assert get_config(secret_key, masked=True) == f"{secret_value[:4]}**********{secret_value[-4:]}"

    openid = f"pg-user-{suffix}"
    user_id = create_user(
        openid,
        name="PG Test User",
        enabled=True,
        allowed_services=[ServiceType.ALL],
        remark="postgres integration",
    )
    user = get_user_by_openid(openid)
    assert user is not None
    assert user.id == user_id
    assert verify_permission(openid, ServiceType.RATE).allowed is True

    image = tmp_path / f"rate-{suffix}.png"
    image.write_bytes(b"pg-rate-card")
    content_id = create_content_draft(
        ServiceType.RATE,
        source_files=[f"/upload/{suffix}.xlsx"],
        source_text=f"rate source {suffix}",
        operator="pg-test",
    )
    set_content_effective(content_id, str(image), operator="pg-test")
    latest = get_latest_effective_content(ServiceType.RATE)
    assert latest.success is True
    assert latest.content_id == content_id
    assert latest.output_image == str(image)

    stock_code = f"39{int(suffix[:8], 16) % 10000:04d}.SZ"
    stock_name = f"PGTestStock{suffix[:12]}"
    assert refresh_stock_symbols(
        [
            {
                "code": stock_code,
                "name": stock_name,
                "market": "SZ",
                "ts_code": stock_code,
                "source": f"pg-test-{suffix}",
            }
        ],
        source=f"pg-test-{suffix}",
    ) == 1
    assert resolve_stock(stock_name, auto_refresh_on_miss=False) == (stock_code, None)
    stocks = list_stock_symbols(stock_name, limit=5)
    assert stocks[0]["name"] == stock_name
    assert stocks[0]["source"] == f"pg-test-{suffix}"

    success_request_id = create_request_record(openid, "利率", ServiceType.RATE)
    succeed_request_record(success_request_id, output_files=[str(image)], elapsed_ms=123)
    success_record = get_request_record(success_request_id)
    assert success_record.status == Status.SUCCESS
    assert success_record.output_files == [str(image)]

    failed_request_id = create_request_record(openid, "unknown", ServiceType.UNMATCHED)
    fail_request_record(failed_request_id, ErrorCode.INPUT_ERROR, detail=f"bad input {suffix}", elapsed_ms=7)
    failed_record = get_request_record(failed_request_id)
    assert failed_record.status == Status.FAILED
    assert failed_record.error_code == ErrorCode.INPUT_ERROR
    assert failed_record.user_prompt

    recent_ids = {record.request_id for record in list_request_records(limit=10)}
    assert {success_request_id, failed_request_id}.issubset(recent_ids)
