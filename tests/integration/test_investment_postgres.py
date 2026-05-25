# encoding:utf-8
"""Opt-in PostgreSQL integration tests for investment business storage.

Local run example:
docker run --name cowagent-pg -e POSTGRES_PASSWORD=cowagent -e POSTGRES_USER=cowagent -e POSTGRES_DB=cowagent -p 5432:5432 -d postgres:16
$env:COWAGENT_TEST_POSTGRES_URL="postgresql+psycopg://cowagent:cowagent@127.0.0.1:5432/cowagent"
py -m pytest tests/integration/test_investment_postgres.py -q
"""

import os
from uuid import uuid4

import pytest


pytestmark = pytest.mark.skipif(
    not os.environ.get("COWAGENT_TEST_POSTGRES_URL"),
    reason="COWAGENT_TEST_POSTGRES_URL not configured",
)


@pytest.fixture()
def investment_postgres_env(tmp_path, monkeypatch):
    pg_url = os.environ["COWAGENT_TEST_POSTGRES_URL"]
    monkeypatch.setenv("COWAGENT_INVESTMENT_DATABASE_URL", pg_url)
    monkeypatch.setenv("COWAGENT_INVESTMENT_STORAGE_ROOT", str(tmp_path / "storage"))

    from business.investment import db, storage

    db.reset_engine_for_tests()
    storage.initialize_storage()
    try:
        yield
    finally:
        db.reset_engine_for_tests()


def test_postgres_runs_critical_investment_flows(investment_postgres_env, tmp_path):
    from sqlalchemy import inspect

    from business.investment import storage
    from business.investment.config_service import get_config, save_config
    from business.investment.constants import ErrorCode, ServiceType, Status
    from business.investment.daily_content import create_content_draft, get_latest_effective_content, set_content_effective
    from business.investment.db import get_engine
    from business.investment.records import (
        create_request_record,
        fail_request_record,
        get_request_record,
        list_request_records,
        succeed_request_record,
    )
    from business.investment.stock_resolver import list_stock_symbols, refresh_stock_symbols, resolve_stock
    from business.investment.user_service import create_user, get_user_by_openid, verify_permission

    suffix = uuid4().hex

    storage.initialize_storage()
    inspector = inspect(get_engine())
    assert inspector.has_table("investment_configs")
    assert inspector.has_table("investment_users")
    assert inspector.has_table("investment_request_records")
    assert inspector.has_table("investment_daily_contents")
    assert inspector.has_table("investment_output_files")
    assert inspector.has_table("investment_stock_symbols")

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
