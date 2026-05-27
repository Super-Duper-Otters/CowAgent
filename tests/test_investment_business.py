# encoding:utf-8
import base64
from datetime import UTC, datetime, timedelta
from io import BytesIO
from collections import OrderedDict
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from types import SimpleNamespace
import sys
from uuid import uuid4
from zipfile import ZipFile

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def test_investment_schema_declares_all_tables():
    from business.investment.schema import metadata

    assert {
        "investment_users",
        "investment_request_records",
        "investment_daily_contents",
        "investment_output_files",
        "investment_configs",
        "investment_stock_symbols",
    }.issubset(metadata.tables)


def _xlsx_bytes(headers, rows):
    values = [list(map(str, headers))]
    values.extend([["" if value is None else str(value) for value in row] for row in rows])
    shared_strings = []
    shared_index = {}

    def shared(value):
        if value not in shared_index:
            shared_index[value] = len(shared_strings)
            shared_strings.append(value)
        return shared_index[value]

    def column_name(index):
        name = ""
        while index:
            index, remainder = divmod(index - 1, 26)
            name = chr(65 + remainder) + name
        return name

    sheet_rows = []
    for row_index, row in enumerate(values, start=1):
        cells = []
        for col_index, value in enumerate(row, start=1):
            cell_ref = f"{column_name(col_index)}{row_index}"
            cells.append(f'<c r="{cell_ref}" t="s"><v>{shared(value)}</v></c>')
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    shared_xml = "".join(f"<si><t>{value}</t></si>" for value in shared_strings)
    data = BytesIO()
    with ZipFile(data, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Users" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetData>{"".join(sheet_rows)}</sheetData>
</worksheet>""",
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(shared_strings)}" uniqueCount="{len(shared_strings)}">{shared_xml}</sst>""",
        )
    return data.getvalue()


@pytest.fixture()
def investment_env(tmp_path, monkeypatch):
    from business.investment import db, storage

    base_url = os.environ.get("COWAGENT_TEST_POSTGRES_URL") or db.DEFAULT_DATABASE_URL
    schema_name = f"cowagent_test_{uuid4().hex}"
    url = make_url(base_url)
    schema_url = url.set(
        query={
            **dict(url.query),
            "options": f"-csearch_path={schema_name}",
        },
    ).render_as_string(hide_password=False)

    admin_engine = create_engine(base_url, future=True)
    with admin_engine.begin() as conn:
        conn.execute(text(f'create schema "{schema_name}"'))

    monkeypatch.setenv("COWAGENT_INVESTMENT_DATABASE_URL", schema_url)
    monkeypatch.setenv("COWAGENT_INVESTMENT_STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.delenv("COWAGENT_INVESTMENT_DB_PATH", raising=False)

    db.reset_engine_for_tests()
    storage._MIGRATED_DATABASE_URL = None
    storage.initialize_storage()
    try:
        yield tmp_path
    finally:
        db.reset_engine_for_tests()
        storage._MIGRATED_DATABASE_URL = None
        with admin_engine.begin() as conn:
            conn.execute(text(f'drop schema if exists "{schema_name}" cascade'))
        admin_engine.dispose()


def test_investment_database_url_defaults_to_docker_postgres(monkeypatch):
    from business.investment import db

    monkeypatch.delenv("COWAGENT_INVESTMENT_DATABASE_URL", raising=False)
    monkeypatch.delenv("COWAGENT_INVESTMENT_DB_PATH", raising=False)

    url = db.get_database_url()

    assert url == "postgresql+psycopg://cowagent:cowagent@127.0.0.1:55432/cowagent_investment"


def test_investment_database_url_prefers_postgres_env(investment_env, monkeypatch):
    from business.investment import db

    monkeypatch.setenv("COWAGENT_INVESTMENT_DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/cowagent")

    assert db.get_database_url() == "postgresql+psycopg://u:p@localhost:5432/cowagent"


def test_investment_database_url_rejects_sqlite_env(monkeypatch):
    from business.investment import db

    monkeypatch.setenv("COWAGENT_INVESTMENT_DATABASE_URL", "sqlite:///tmp/investment.db")

    with pytest.raises(ValueError, match="PostgreSQL"):
        db.get_database_url()


def test_investment_database_url_rejects_sqlite_config(monkeypatch):
    import config

    from business.investment import db

    monkeypatch.delenv("COWAGENT_INVESTMENT_DATABASE_URL", raising=False)
    monkeypatch.setattr(config, "conf", lambda: {"investment_database_url": "sqlite:///tmp/investment.db"})

    with pytest.raises(ValueError, match="PostgreSQL"):
        db.get_database_url()


def test_storage_initializes_schema_with_alembic_upgrade(tmp_path, monkeypatch):
    from business.investment import migrations, schema, storage

    monkeypatch.setenv("COWAGENT_INVESTMENT_STORAGE_ROOT", str(tmp_path / "storage"))
    calls = []

    monkeypatch.setattr(migrations, "upgrade", lambda revision="head": calls.append(revision))
    monkeypatch.setattr(schema.metadata, "create_all", lambda bind: pytest.fail("initialize_storage must use Alembic"))

    storage.initialize_storage()

    assert calls == ["head"]
    assert (tmp_path / "storage" / "uploads").is_dir()
    assert (tmp_path / "storage" / "generated").is_dir()
    assert (tmp_path / "storage" / "technical-analysis").is_dir()


def test_investment_migration_smoke_creates_schema(investment_env):
    from business.investment import storage
    from business.investment.db import get_engine
    from sqlalchemy import inspect

    storage.initialize_storage()
    inspector = inspect(get_engine())

    assert inspector.has_table("investment_users")
    assert inspector.has_table("investment_stock_symbols")


def test_investment_alembic_runner_exposes_upgrade():
    from business.investment import migrations

    assert callable(migrations.upgrade)
    assert migrations.alembic_config_path().name == "alembic.ini"


def test_config_service_uses_investment_db_connection_helpers():
    from business.investment import config_service

    assert not hasattr(config_service, "get_connection")


def test_user_service_uses_investment_db_connection_helpers():
    from business.investment import user_service

    assert not hasattr(user_service, "get_connection")


def test_records_service_uses_investment_db_connection_helpers():
    from business.investment import records

    assert not hasattr(records, "get_connection")


def test_daily_content_service_uses_investment_db_connection_helpers():
    from business.investment import daily_content

    assert not hasattr(daily_content, "get_connection")


def test_stock_resolver_uses_investment_db_connection_helpers():
    from business.investment import stock_resolver

    assert not hasattr(stock_resolver, "get_connection")


def test_health_uses_investment_db_connection_helpers():
    from business.investment import health

    assert not hasattr(health, "get_connection")


def test_config_service_direct_call_initializes_storage_schema(investment_env):
    from business.investment import db
    from business.investment.config_service import get_config, save_config
    from sqlalchemy import inspect

    db.reset_engine_for_tests()

    save_config("tushare.token", "direct-token", operator_role="admin")

    assert get_config("tushare.token") == "direct-token"
    assert inspect(db.get_engine()).has_table("investment_configs")


def test_config_masks_sensitive_values_and_checks_permissions(investment_env, monkeypatch):
    from business.investment.config_service import (
        can_modify_config,
        get_config,
        mask_sensitive_value,
        save_config,
        safe_log_value,
    )

    monkeypatch.setattr("business.investment.config_service.conf", lambda: {"tushare_token": "fallback-token"})

    assert get_config("tushare.token") == "fallback-token"
    save_config("tushare.token", "ts-1234567890abcdef", operator_role="admin")
    assert get_config("tushare.token") == "ts-1234567890abcdef"
    assert mask_sensitive_value("ts-1234567890abcdef") == "ts-1**********cdef"
    assert "ts-1234567890abcdef" not in safe_log_value("tushare.token", "ts-1234567890abcdef")
    assert mask_sensitive_value("abc") == "***"
    assert can_modify_config("tushare.token", "uploader") is False
    assert can_modify_config("tushare.token", "admin") is True


def test_investment_config_rejects_model_and_wechatmp_keys_without_persisting(investment_env):
    from sqlalchemy import select

    from business.investment import db
    from business.investment.config_service import get_config, save_config, save_configs
    from business.investment.schema import investment_configs

    forbidden = {
        "model.name": "investment-model",
        "model.api_key": "sk-investment-secret",
        "wechatmp.app_id": "wx-investment",
        "wechatmp.token": "wx-token",
    }

    for key, value in forbidden.items():
        with pytest.raises(ValueError, match="Investment config"):
            save_config(key, value, operator_role="admin")

    with pytest.raises(ValueError, match="Investment config"):
        save_configs(forbidden, operator_role="admin")

    with db.connect() as conn:
        rows = conn.execute(select(investment_configs.c.config_key)).fetchall()
    assert {row[0] for row in rows}.isdisjoint(forbidden)
    assert get_config("tushare.token", "") == ""


def test_web_console_config_save_preserves_masked_investment_sensitive_values(investment_env):
    from business.investment.config_service import get_config, get_configs, save_configs

    token = "ts-console-secret-1234567890"
    save_configs({"tushare.token": token, "router.enable_agent_fallback": False}, operator_role="admin")

    masked = get_configs(["tushare.token", "router.enable_agent_fallback"], masked=True)
    save_configs(
        {
            "tushare.token": masked["tushare.token"],
            "router.enable_agent_fallback": True,
        },
        operator_role="admin",
    )

    assert get_config("tushare.token") == token
    assert get_config("router.enable_agent_fallback") is True


def _call_investment_json_handler(monkeypatch, handler, *, params=None, body=None):
    from channel.web import web_channel

    auth_calls = []
    monkeypatch.setattr(web_channel, "_require_auth", lambda: auth_calls.append(True))
    monkeypatch.setattr(web_channel.web, "input", lambda **_defaults: SimpleNamespace(**(params or {})))
    monkeypatch.setattr(web_channel.web, "data", lambda: json.dumps(body or {}, ensure_ascii=False).encode("utf-8"))
    monkeypatch.setattr(web_channel.web.ctx, "headers", [], raising=False)

    raw = handler()
    payload = json.loads(raw)
    assert auth_calls == [True]
    return payload


def test_web_investment_config_returns_masked_tushare_token(investment_env, monkeypatch):
    from business.investment.config_service import save_config
    from channel.web.web_channel import InvestmentConfigHandler

    save_config("tushare.token", "ts-web-secret-1234567890", operator_role="admin")

    payload = _call_investment_json_handler(monkeypatch, InvestmentConfigHandler().GET)

    assert payload["status"] == "success"
    assert payload["configs"]["tushare.token"] == "ts-w**********7890"
    assert "ts-web-secret-1234567890" not in json.dumps(payload, ensure_ascii=False)


def test_web_investment_config_excludes_and_rejects_global_model_and_wechatmp_keys(investment_env, monkeypatch):
    from sqlalchemy import select

    from business.investment import db
    from business.investment.schema import investment_configs
    from channel.web.web_channel import InvestmentConfigHandler

    body = {
        "configs": {
            "model.name": "bad-investment-model",
            "model.api_key": "sk-bad-investment",
            "wechatmp.app_id": "wx-bad",
            "tushare.token": "ts-web-secret-1234567890",
        },
        "operator_role": "admin",
    }

    post_payload = _call_investment_json_handler(monkeypatch, InvestmentConfigHandler().POST, body=body)

    assert post_payload["status"] == "error"
    assert "model.name" in post_payload["message"]
    assert "wechatmp.app_id" in post_payload["message"]
    with db.connect() as conn:
        keys = {
            row[0]
            for row in conn.execute(select(investment_configs.c.config_key)).fetchall()
        }
    assert keys.isdisjoint({"model.name", "model.api_key", "wechatmp.app_id"})
    assert "tushare.token" not in keys

    get_payload = _call_investment_json_handler(monkeypatch, InvestmentConfigHandler().GET)
    assert get_payload["status"] == "success"
    assert "tushare.token" in get_payload["configs"]
    assert not any(key.startswith(("model.", "wechatmp.")) for key in get_payload["configs"])


def test_web_stock_query_returns_matches_and_stats_without_refresh(investment_env, monkeypatch):
    from business.investment import stock_resolver
    from channel.web.web_channel import InvestmentStocksHandler

    stock_resolver.refresh_stock_symbols(
        [
            {"code": "300502.SZ", "name": "新易盛", "market": "SZ", "source": "seed"},
            {"code": "600519.SH", "name": "贵州茅台", "market": "SH", "source": "seed"},
        ],
        source="seed",
    )
    monkeypatch.setattr(stock_resolver, "refresh_from_auto", lambda: pytest.fail("query must not refresh"))
    monkeypatch.setattr(stock_resolver, "refresh_from_akshare", lambda: pytest.fail("query must not refresh"))
    monkeypatch.setattr(stock_resolver, "refresh_from_tushare", lambda: pytest.fail("query must not refresh"))

    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentStocksHandler().GET,
        params={"name": "新易盛", "limit": "20"},
    )

    assert payload["status"] == "success"
    assert [item["code"] for item in payload["stocks"]] == ["300502.SZ"]
    assert payload["stats"]["total"] == 2
    assert payload["stats"]["source_count"] == 1


def test_web_stock_refresh_dispatches_sources_and_reports_failures(investment_env, monkeypatch):
    from business.investment import stock_resolver
    from channel.web.web_channel import InvestmentStocksRefreshHandler

    monkeypatch.setattr(stock_resolver, "refresh_from_akshare", lambda: 3)
    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentStocksRefreshHandler().POST,
        body={"source": "akshare"},
    )
    assert payload["status"] == "success"
    assert payload["result"] == {"akshare": {"count": 3}}
    assert "stats" in payload

    monkeypatch.setattr(stock_resolver, "refresh_from_tushare", lambda: (_ for _ in ()).throw(RuntimeError("ts failed")))
    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentStocksRefreshHandler().POST,
        body={"source": "tushare"},
    )
    assert payload["status"] == "error"
    assert payload["message"] == "ts failed"

    monkeypatch.setattr(stock_resolver, "refresh_from_auto", lambda: {"akshare": {"error": "ak failed"}, "tushare": {"count": 4}})
    payload = _call_investment_json_handler(monkeypatch, InvestmentStocksRefreshHandler().POST, body={})
    assert payload["status"] == "success"
    assert payload["result"] == {"akshare": {"error": "ak failed"}, "tushare": {"count": 4}}


def test_web_daily_content_generate_marks_generating_before_background_task(investment_env, monkeypatch):
    from business.investment.constants import ServiceType, Status
    from business.investment.daily_content import create_rate_content_draft
    from business.investment.records import get_content_record
    from channel.web.web_channel import InvestmentDailyContentGenerateHandler

    content_id = create_rate_content_draft(source_text="rate source")
    calls = []

    def fake_generate_content(task_content_id):
        calls.append(task_content_id)
        return SimpleNamespace(
            success=True,
            content_id=task_content_id,
            generated_text="",
            output_image="",
            output_files=[],
            error_code=None,
            user_prompt="",
            detail="",
        )

    monkeypatch.setattr("business.investment.daily_content.generate_content", fake_generate_content)

    payload = _call_investment_json_handler(
        monkeypatch,
        lambda: InvestmentDailyContentGenerateHandler().POST(content_id),
    )

    assert payload["status"] == "success"
    assert payload["content_id"] == content_id
    assert payload["generation_status"] == "started"
    assert get_content_record(content_id).service_type == ServiceType.RATE
    assert get_content_record(content_id).status == Status.GENERATING


def test_web_daily_content_get_returns_current_effective_content(investment_env, tmp_path, monkeypatch):
    from business.investment.constants import ServiceType
    from business.investment.daily_content import create_content_draft, set_content_effective
    from channel.web.web_channel import InvestmentDailyContentHandler

    image = tmp_path / "rate-current.png"
    image.write_bytes(b"png")
    older_image = tmp_path / "rate-older.png"
    older_image.write_bytes(b"png")
    older_id = create_content_draft(ServiceType.RATE, source_text="older", operator="operator-old")
    current_id = create_content_draft(ServiceType.RATE, source_text="current", operator="operator-current")
    set_content_effective(older_id, str(older_image), operator="operator-old")
    set_content_effective(current_id, str(image), operator="operator-current")

    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentDailyContentHandler().GET,
        params={"service_type": "rate", "limit": "50"},
    )

    assert payload["status"] == "success"
    assert payload["current_effective"]["content_id"] == current_id
    assert payload["current_effective"]["service_type"] == ServiceType.RATE
    assert payload["current_effective"]["status"] == "effective"
    assert payload["current_effective"]["output_image"] == str(image)
    assert payload["current_effective"]["operator"] == "operator-current"


def test_user_service_permission_edges_and_upsert(investment_env):
    from business.investment.constants import ErrorCode, ServiceType
    from business.investment.user_service import (
        ImportUserRow,
        create_user,
        import_users,
        verify_permission,
    )

    assert verify_permission("missing", ServiceType.RATE).allowed is False
    assert verify_permission("missing", ServiceType.RATE).error_code == ErrorCode.UNAUTHORIZED

    create_user("disabled", enabled=False, allowed_services=[ServiceType.ALL])
    assert verify_permission("disabled", ServiceType.RATE).error_code == ErrorCode.USER_DISABLED

    create_user("limited", enabled=True, allowed_services=[ServiceType.RATE])
    assert verify_permission("limited", ServiceType.CONVERTIBLE_BOND).error_code == ErrorCode.UNAUTHORIZED

    create_user(
        "expired",
        enabled=True,
        allowed_services=[ServiceType.ALL],
        auth_end_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
    )
    assert verify_permission("expired", ServiceType.RATE).error_code == ErrorCode.AUTH_EXPIRED

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    assert verify_permission("ok", ServiceType.TECHNICAL_ANALYSIS).allowed is True

    result = import_users([
        ImportUserRow(openid="ok", name="updated", allowed_services="利率"),
        ImportUserRow(openid="new", name="new user", allowed_services="全部"),
    ])
    assert result.created == 1
    assert result.updated == 1
    assert verify_permission("ok", ServiceType.RATE).allowed is True
    assert verify_permission("ok", ServiceType.CONVERTIBLE_BOND).allowed is False


def test_user_service_crud_list_and_all_service_contract(investment_env):
    from business.investment.constants import ServiceType
    from business.investment.user_service import create_user, disable_user, get_user_by_openid, list_users, update_user, verify_permission

    user_id = create_user(
        "crud-openid",
        name="Alice",
        institution="Inst A",
        mobile="13800000000",
        enabled=True,
        allowed_services=["全部"],
        auth_start_at="2026-01-01T00:00:00",
        auth_end_at="2026-12-31T23:59:59",
        remark="first",
    )

    created = get_user_by_openid("crud-openid")
    assert created is not None
    assert created.id == user_id
    assert created.name == "Alice"
    assert [item for item in created.allowed_services or []] == [ServiceType.ALL]
    assert list_users(enabled=True, openid="crud") == [created]
    assert verify_permission("crud-openid", ServiceType.TECHNICAL_ANALYSIS).allowed is True
    assert verify_permission("crud-openid", ServiceType.RATE).allowed is True
    assert verify_permission("crud-openid", ServiceType.CONVERTIBLE_BOND).allowed is True

    update_user("crud-openid", name="Alice B", allowed_services=["利率"], remark="updated")
    updated = get_user_by_openid("crud-openid")
    assert updated is not None
    assert updated.name == "Alice B"
    assert updated.remark == "updated"
    assert verify_permission("crud-openid", ServiceType.RATE).allowed is True
    assert verify_permission("crud-openid", ServiceType.CONVERTIBLE_BOND).allowed is False

    disable_user("crud-openid")
    assert list_users(enabled=False, openid="crud")[0].enabled is False


def test_user_service_excel_import_maps_fields_and_permissions_take_effect(investment_env):
    from business.investment.constants import ServiceType
    from business.investment.user_service import create_user, get_user_by_openid, import_users_from_excel, parse_users_excel, verify_permission

    create_user("existing-openid", name="old", allowed_services=["利率"])
    payload = _xlsx_bytes(
        [
            "openid",
            "name",
            "institution",
            "mobile",
            "enabled",
            "allowed_services",
            "auth_start_at",
            "auth_end_at",
            "remark",
        ],
        [
            [
                "existing-openid",
                "Existing New",
                "Inst B",
                "13900000000",
                "是",
                "转债",
                "2026-01-01T00:00:00",
                "2026-12-31T23:59:59",
                "renewed",
            ],
            [
                "new-openid",
                "New User",
                "Inst C",
                "13700000000",
                "true",
                "全部",
                "",
                "",
                "created",
            ],
        ],
    )

    rows = parse_users_excel(payload)
    assert [row.openid for row in rows] == ["existing-openid", "new-openid"]
    assert rows[0].name == "Existing New"
    assert rows[0].institution == "Inst B"
    assert rows[0].mobile == "13900000000"
    assert rows[0].enabled is True
    assert rows[0].allowed_services == "转债"
    assert rows[0].auth_start_at == datetime(2026, 1, 1, 0, 0)
    assert rows[0].auth_end_at == datetime(2026, 12, 31, 23, 59, 59)
    assert rows[0].remark == "renewed"

    result = import_users_from_excel(payload)
    assert result.created == 1
    assert result.updated == 1
    existing = get_user_by_openid("existing-openid")
    new_user = get_user_by_openid("new-openid")
    assert existing is not None
    assert existing.name == "Existing New"
    assert new_user is not None
    assert new_user.name == "New User"
    assert verify_permission("existing-openid", ServiceType.CONVERTIBLE_BOND).allowed is True
    assert verify_permission("existing-openid", ServiceType.RATE).allowed is False
    assert verify_permission("new-openid", ServiceType.TECHNICAL_ANALYSIS).allowed is True


def test_records_save_failure_success_and_order(investment_env):
    from business.investment.constants import ErrorCode, ServiceType
    from business.investment.records import (
        create_request_record,
        fail_request_record,
        get_request_record,
        list_request_records,
        succeed_request_record,
    )

    first = create_request_record("openid", "利率", ServiceType.RATE)
    succeed_request_record(first, output_files=["/tmp/rate.png"], elapsed_ms=12)
    second = create_request_record("openid", "转债", ServiceType.CONVERTIBLE_BOND)
    fail_request_record(second, ErrorCode.NO_CONTENT, "今日内容尚未更新，请稍后再试。", "no active content", 5)

    assert get_request_record(first).output_files == ["/tmp/rate.png"]
    failed = get_request_record(second)
    assert failed.error_code == ErrorCode.NO_CONTENT
    assert failed.error_message == "no active content"
    assert [record.request_id for record in list_request_records(limit=2)] == [second, first]


def test_old_generating_request_records_are_flagged_without_mutating_status(investment_env):
    from business.investment.constants import ServiceType, Status
    from business.investment.db import connect
    from business.investment.records import create_request_record, get_request_record, list_request_records

    request_id = create_request_record("openid", "新易盛 技术分析", ServiceType.TECHNICAL_ANALYSIS)
    old_created_at = (datetime.now(UTC) - timedelta(minutes=31)).isoformat(timespec="microseconds")
    with connect() as conn:
        conn.execute(
            text(
                "update investment_request_records "
                "set created_at = :created_at, updated_at = :updated_at "
                "where request_id = :request_id"
            ),
            {"created_at": old_created_at, "updated_at": old_created_at, "request_id": request_id},
        )

    record = list_request_records(limit=1)[0]
    persisted = get_request_record(request_id)

    assert record.request_id == request_id
    assert record.status == Status.GENERATING
    assert record.status_warning == "未完成/可能超时"
    assert persisted.status == Status.GENERATING


def test_request_records_api_includes_generating_timeout_warning(investment_env, monkeypatch):
    from business.investment.constants import ServiceType
    from business.investment.db import connect
    from business.investment.records import create_request_record
    from channel.web.web_channel import InvestmentRequestRecordsHandler

    request_id = create_request_record("openid", "新易盛 技术分析", ServiceType.TECHNICAL_ANALYSIS)
    old_created_at = (datetime.now(UTC) - timedelta(minutes=31)).isoformat(timespec="microseconds")
    with connect() as conn:
        conn.execute(
            text(
                "update investment_request_records "
                "set created_at = :created_at, updated_at = :updated_at "
                "where request_id = :request_id"
            ),
            {"created_at": old_created_at, "updated_at": old_created_at, "request_id": request_id},
        )

    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentRequestRecordsHandler().GET,
        params={"limit": "50"},
    )
    record = payload["records"][0]

    assert record["request_id"] == request_id
    assert record["status"] == "generating"
    assert record["status_warning"] == "未完成/可能超时"


def test_batch_01_service_results_share_contract_fields(investment_env):
    from business.investment.ai_generation import AIGenerationResult
    from business.investment.daily_content import DailyContentResult
    from business.investment.render_service import RenderResult
    from business.investment.router import BusinessReply
    from business.investment.technical_analysis import TechnicalAnalysisResult

    required = {"success", "error_code", "user_prompt", "detail", "output_files"}
    results = [
        AIGenerationResult(success=False),
        RenderResult(success=False),
        TechnicalAnalysisResult(success=False),
        DailyContentResult(success=False),
        BusinessReply(handled=True, success=False, reply_text="", output_files=[], service_type="rate"),
    ]

    for result in results:
        assert required.issubset(result.__dataclass_fields__)


def test_success_request_records_output_files_table(investment_env):
    from business.investment.constants import ServiceType
    from business.investment.db import connect
    from business.investment.records import record_success_request

    request_id = record_success_request("openid", "利率", ServiceType.RATE, ["/tmp/rate.png"], elapsed_ms=3)

    with connect() as conn:
        rows = conn.execute(
            text(
                "select owner_id, file_path, file_type, service_type "
                "from investment_output_files where owner_id = :request_id"
            ),
            {"request_id": request_id},
        ).mappings().all()

    assert [dict(row) for row in rows] == [
        {
            "owner_id": request_id,
            "file_path": "/tmp/rate.png",
            "file_type": "image",
            "service_type": ServiceType.RATE,
        }
    ]


def test_ai_and_renderer_failures_record_sanitized_backend_detail(investment_env, monkeypatch):
    from business.investment import config_service
    from business.investment.config_service import safe_log_value
    from business.investment.constants import ServiceType
    from business.investment.daily_content import create_content_draft, regenerate_content
    from business.investment.records import get_content_record

    api_key = "sk-live-secret-1234567890"
    monkeypatch.setattr(config_service, "conf", lambda: {"custom_api_key": api_key})

    ai_content_id = create_content_draft(ServiceType.RATE, source_text="rate")
    ai_result = regenerate_content(
        ai_content_id,
        lambda _service_type, _source_text: SimpleNamespace(success=False, detail=f"upstream rejected {api_key}"),
        lambda _service_type, _text: SimpleNamespace(success=True, image_path="/tmp/unused.png"),
    )
    ai_record = get_content_record(ai_content_id)
    assert ai_result.success is False
    assert "upstream rejected" in ai_record.error_message
    assert api_key not in ai_record.error_message

    render_content_id = create_content_draft(ServiceType.RATE, source_text="rate")
    render_result = regenerate_content(
        render_content_id,
        lambda _service_type, _source_text: SimpleNamespace(success=True, text="standard"),
        lambda _service_type, _text: SimpleNamespace(success=False, detail=f"renderer failed with {api_key}"),
    )
    render_record = get_content_record(render_content_id)
    assert render_result.success is False
    assert "renderer failed" in render_record.error_message
    assert api_key not in render_record.error_message
    assert api_key not in safe_log_value("model.api_key", api_key)


def test_ai_generation_uses_global_model_params_and_ignores_legacy_investment_rows(investment_env, monkeypatch):
    from business.investment.ai_generation import (
        AIGenerationRequest,
        generate_convertible_bond_text,
        generate_rate_text,
        generate_technical_analysis_text,
    )
    from business.investment import config_service, db
    from business.investment.config_service import save_configs
    from business.investment.constants import ServiceType, Status

    api_key = "sk-global-contract-1234567890"
    monkeypatch.setattr(
        config_service,
        "conf",
        lambda: {
            "bot_type": "custom",
            "model": "global-model",
            "custom_api_base": "https://global.example/v1",
            "custom_api_key": api_key,
            "temperature": 0.25,
        },
    )
    now = datetime.now(UTC).isoformat(timespec="microseconds")
    with db.connect() as conn:
        for key, value in {
            "model.provider": "legacy-provider",
            "model.name": "legacy-model",
            "model.api_base": "https://legacy.example/v1",
            "model.api_key": "sk-legacy-secret",
            "model.temperature": 0.99,
        }.items():
            db.upsert_config(conn, key, json.dumps(value), now, "legacy")
    save_configs(
        {
            "prompt.technical_analysis": "TA prompt",
            "prompt.rate": "Rate prompt",
            "prompt.convertible_bond": "CB prompt",
        },
        operator_role="admin",
    )

    seen: list[AIGenerationRequest] = []

    class FakeAdapter:
        def generate(self, request: AIGenerationRequest) -> str:
            seen.append(request)
            return f"standard:{request.service_type}:{request.prompt}:{request.source_text}"

    ta = generate_technical_analysis_text("ta report", adapter=FakeAdapter())
    rate = generate_rate_text("rate source", adapter=FakeAdapter())
    cb = generate_convertible_bond_text("cb source", adapter=FakeAdapter())

    assert [request.service_type for request in seen] == [
        ServiceType.TECHNICAL_ANALYSIS,
        ServiceType.RATE,
        ServiceType.CONVERTIBLE_BOND,
    ]
    assert [request.prompt for request in seen] == ["TA prompt", "Rate prompt", "CB prompt"]
    assert all(request.model_provider == "custom" for request in seen)
    assert all(request.model_name == "global-model" for request in seen)
    assert all(request.api_base == "https://global.example/v1" for request in seen)
    assert all(request.api_key == api_key for request in seen)
    assert all(request.temperature == 0.25 for request in seen)

    assert ta.success is True
    assert ta.status == Status.SUCCESS
    assert ta.service_type == ServiceType.TECHNICAL_ANALYSIS
    assert ta.source_text == "ta report"
    assert ta.generated_text == "standard:technical_analysis:TA prompt:ta report"
    assert ta.text == ta.generated_text
    assert ta.failure_reason == ""
    assert api_key not in str(ta.model_params)
    assert ta.model_params == {
        "provider": "custom",
        "model": "global-model",
        "api_base": "https://global.example/v1",
        "api_key": "sk-g**********7890",
        "temperature": 0.25,
    }
    assert rate.generated_text == "standard:rate:Rate prompt:rate source"
    assert cb.generated_text == "standard:convertible_bond:CB prompt:cb source"


def test_technical_analysis_default_prompt_matches_signal_card_renderer_contract(investment_env, monkeypatch):
    from business.investment import config_service
    from business.investment.ai_generation import build_generation_request
    from business.investment.constants import ServiceType

    monkeypatch.setattr(
        config_service,
        "conf",
        lambda: {
            "bot_type": "custom",
            "model": "global-model",
            "custom_api_base": "https://global.example/v1",
            "custom_api_key": "sk-global-contract-1234567890",
        },
    )

    request = build_generation_request(ServiceType.TECHNICAL_ANALYSIS, "ta report")

    for required in (
        "标的：",
        "信号方向：",
        "最新收盘：",
        "行情日期：",
        "趋势研判",
        "核心关键位",
        "强压力：",
        "强支撑：",
        "实操指引",
        "授权剩余时间：",
        "数据来源：",
        "业务对接：",
    ):
        assert required in request.prompt
    assert "禁止输出 Markdown 表格" in request.prompt
    assert "只输出卡片正文" in request.prompt


@pytest.mark.parametrize(
    ("global_config", "expected"),
    [
        (
            {
                "bot_type": "zhipu",
                "model": "glm-5.1",
                "zhipu_ai_api_base": "https://zhipu.example/v4",
                "zhipu_ai_api_key": "sk-zhipu",
                "temperature": 0.41,
            },
            {
                "provider": "zhipu",
                "model": "glm-5.1",
                "api_base": "https://zhipu.example/v4",
                "api_key": "sk-zhipu",
                "temperature": 0.41,
            },
        ),
        (
            {
                "bot_type": "",
                "model": "glm-5.1",
                "zhipu_ai_api_base": "https://zhipu-inferred.example/v4",
                "zhipu_ai_api_key": "sk-zhipu-inferred",
            },
            {
                "provider": "zhipu",
                "model": "glm-5.1",
                "api_base": "https://zhipu-inferred.example/v4",
                "api_key": "sk-zhipu-inferred",
                "temperature": 0.7,
            },
        ),
        (
            {
                "bot_type": "",
                "model": "qwen3-max",
                "dashscope_api_base": "https://dashscope.example/compatible-mode/v1",
                "dashscope_api_key": "sk-dashscope",
            },
            {
                "provider": "dashscope",
                "model": "qwen3-max",
                "api_base": "https://dashscope.example/compatible-mode/v1",
                "api_key": "sk-dashscope",
                "temperature": 0.7,
            },
        ),
        (
            {
                "use_linkai": True,
                "linkai_api_base": "https://link.example",
                "linkai_api_key": "sk-linkai",
                "model": "gpt-5.4-mini",
            },
            {
                "provider": "linkai",
                "model": "gpt-5.4-mini",
                "api_base": "https://link.example/v1",
                "api_key": "sk-linkai",
                "temperature": 0.7,
            },
        ),
        (
            {
                "bot_type": "deepseek",
                "model": "deepseek-v4-flash",
                "deepseek_api_base": "https://deepseek.example/v1",
                "custom_api_key": "sk-custom-should-not-be-used",
            },
            {
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
                "api_base": "https://deepseek.example/v1",
                "api_key": "",
                "temperature": 0.7,
            },
        ),
    ],
)
def test_global_model_config_resolves_configured_and_inferred_providers(monkeypatch, global_config, expected):
    from business.investment import config_service
    from business.investment.ai_generation import _global_model_config

    monkeypatch.setattr(config_service, "conf", lambda: global_config)

    assert _global_model_config() == expected


def test_ai_generation_sends_image_source_files_as_multimodal_content(investment_env, tmp_path, monkeypatch):
    from business.investment import config_service
    from business.investment.ai_generation import ExistingModelAdapter, generate_rate_text

    image_bytes = b"\x89PNG\r\n\x1a\nimage"
    image_path = tmp_path / "rate-source.png"
    image_path.write_bytes(image_bytes)
    monkeypatch.setattr(
        config_service,
        "conf",
        lambda: {
            "bot_type": "custom",
            "model": "vision-model",
            "custom_api_base": "https://model.example/v1",
            "custom_api_key": "sk-image-source-1234567890",
        },
    )

    class FakeClient:
        def __init__(self):
            self.calls = []

        def chat_completions(self, **kwargs):
            self.calls.append(kwargs)
            return {"choices": [{"message": {"content": "standard rate text"}}]}

    client = FakeClient()

    result = generate_rate_text("", source_files=[str(image_path)], adapter=ExistingModelAdapter(client=client))

    assert result.success is True
    messages = client.calls[0]["messages"]
    assert messages[1]["role"] == "user"
    content = messages[1]["content"]
    assert content[0]["type"] == "text"
    assert str(image_path) in content[0]["text"]
    assert content[1] == {
        "type": "image_url",
        "image_url": {
            "url": f"data:image/png;base64,{base64.b64encode(image_bytes).decode('ascii')}",
        },
    }


def test_ai_generation_retries_transient_model_connection_errors(investment_env, monkeypatch):
    from business.investment import config_service
    from business.investment.ai_generation import ExistingModelAdapter, generate_rate_text
    from models.openai.openai_http_client import OpenAIHTTPError

    monkeypatch.setattr(
        config_service,
        "conf",
        lambda: {
            "bot_type": "custom",
            "model": "mimo-v2.5",
            "custom_api_base": "https://model.example/v1",
            "custom_api_key": "sk-retry-source-1234567890",
        },
    )

    class FlakyClient:
        def __init__(self):
            self.calls = 0

        def chat_completions(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise OpenAIHTTPError(0, {}, "Connection error: SSL EOF")
            return {"choices": [{"message": {"content": "standard rate text"}}]}

    client = FlakyClient()

    result = generate_rate_text("rate source", adapter=ExistingModelAdapter(client=client))

    assert result.success is True
    assert result.text == "standard rate text"
    assert client.calls == 2


def test_ai_generation_extracts_image_text_before_final_card_prompt(investment_env, tmp_path, monkeypatch):
    from business.investment import config_service
    from business.investment.ai_generation import ExistingModelAdapter, generate_rate_text

    image_path = tmp_path / "rate-source.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nimage")
    monkeypatch.setattr(
        config_service,
        "conf",
        lambda: {
            "bot_type": "custom",
            "model": "vision-model",
            "custom_api_base": "https://model.example/v1",
            "custom_api_key": "sk-image-source-1234567890",
        },
    )

    class FakeClient:
        def __init__(self):
            self.calls = []

        def chat_completions(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return {"choices": [{"message": {"content": "OCR: 2026-05-25 108.970 入场（3/8）"}}]}
            return {"choices": [{"message": {"content": "standard rate card text"}}]}

    client = FakeClient()

    result = generate_rate_text("", source_files=[str(image_path)], adapter=ExistingModelAdapter(client=client))

    assert result.success is True
    assert result.text == "standard rate card text"
    assert len(client.calls) == 2
    assert any(block.get("type") == "image_url" for block in client.calls[0]["messages"][1]["content"])
    assert client.calls[1]["messages"][1]["content"] == (
        "以下是上传图片的识别结果，请据此生成标准卡片文本。禁止要求用户再提供原文；"
        "缺失字段按系统要求填“——”。\n\nOCR: 2026-05-25 108.970 入场（3/8）"
    )


def test_ai_generation_blank_configured_prompt_falls_back_to_default(investment_env):
    from business.investment.ai_generation import AIGenerationRequest, generate_rate_text
    from business.investment.config_service import save_config

    save_config("prompt.rate", "", operator_role="admin")
    seen: list[AIGenerationRequest] = []

    class FakeAdapter:
        def generate(self, request: AIGenerationRequest) -> str:
            seen.append(request)
            return "standard rate text"

    result = generate_rate_text("rate source", adapter=FakeAdapter())

    assert result.success is True
    assert seen[0].prompt
    assert "必须只输出卡片正文" in seen[0].prompt
    assert "当日核心信号" in seen[0].prompt


def test_ai_generation_normalizes_semicolon_rate_text_for_renderer(investment_env):
    from business.investment.ai_generation import AIGenerationRequest, generate_rate_text

    class FakeAdapter:
        def generate(self, request: AIGenerationRequest) -> str:
            return (
                "标的：T主力合约；最新收盘：108.970元；行情日期：2026-05-25；分析模型：交易性择时日度信号跟踪；"
                "当日核心信号：当前维持入场信号，复合策略信号稳定在3/8；复合策略信号：入场（3/8）；"
                "多头：单均线、双均线、通道过滤；空头：阶距、隔夜共振；日度主线：空头子信号共振提示短期需保持谨慎；"
                "周度全景复盘：近一周复合策略信号由6/8逐步降至3/8；近一周整体信号：偏谨慎入场；"
                "周度主线：多头动能收敛；授权剩余时间：——；业务对接：联系人：辛仑豪/刘静烨，13681991121；数据来源：Wind"
            )

    result = generate_rate_text("rate source", adapter=FakeAdapter())

    assert result.success is True
    assert "📊 当日核心信号\n复合策略信号：入场（3/8）" in result.text
    assert "多头：单均线、双均线、通道过滤；空头：阶距、隔夜共振" in result.text
    assert "📊 周度全景复盘\n近一周整体信号：偏谨慎入场" in result.text
    assert result.generated_text == result.text


def test_ai_generation_normalizes_multiline_inline_rate_text_for_renderer(investment_env):
    from business.investment.ai_generation import AIGenerationRequest, generate_rate_text

    class FakeAdapter:
        def generate(self, request: AIGenerationRequest) -> str:
            return """标的：T主力合约
最新收盘：108.970元
行情日期：2026-05-25
分析模型：交易性择时日度信号跟踪
当日核心信号：复合策略信号入场（3/8），模型整体偏多格局未变
复合策略信号：入场（3/8）
多头：单均线、双均线、通道过滤；空头：阶距、隔夜共振
日度主线：继续跟随量化模型
周度全景复盘：近一周复合策略信号回落至3/8
近一周整体信号：入场为主
周度主线：多头主线未变
授权剩余时间：——
业务对接：幸仁豪 / 刘静怡 / 13681991121"""

    result = generate_rate_text("rate source", adapter=FakeAdapter())

    assert result.success is True
    assert "📊 当日核心信号\n复合策略信号：入场（3/8）" in result.text
    assert "▪️复合策略信号入场（3/8），模型整体偏多格局未变" in result.text
    assert "📊 周度全景复盘\n近一周整体信号：入场为主" in result.text


def test_ai_generation_failures_and_health_check_sanitize_model_config(investment_env, monkeypatch):
    from business.investment import config_service
    from business.investment.ai_generation import AIGenerationRequest, generate_rate_text
    from business.investment.constants import ErrorCode, Status
    from business.investment.health import run_health_checks

    api_key = "sk-ai-failure-1234567890"
    monkeypatch.setattr(config_service, "conf", lambda: {"bot_type": "custom", "custom_api_key": api_key})

    class FailingAdapter:
        def generate(self, request: AIGenerationRequest) -> str:
            raise RuntimeError(f"upstream rejected key {request.api_key}")

    result = generate_rate_text("rate source", adapter=FailingAdapter())

    assert result.success is False
    assert result.status == Status.FAILED
    assert result.error_code == ErrorCode.SYSTEM_ERROR
    assert "upstream rejected" in result.failure_reason
    assert result.failure_reason == result.detail
    assert api_key not in result.detail
    assert api_key not in str(result.model_params)

    model_health = next(item for item in run_health_checks() if item.name == "model_config")
    assert model_health.ok is False
    assert "model.name missing" in model_health.detail
    assert "model.api_base missing" in model_health.detail
    assert "model.api_key" not in model_health.detail or api_key not in model_health.detail


def test_model_health_check_accepts_global_config_fallback(investment_env, monkeypatch):
    from business.investment import config_service
    from business.investment.health import run_health_checks

    api_key = "sk-global-fallback-1234567890"
    monkeypatch.setattr(
        config_service,
        "conf",
        lambda: {
            "bot_type": "custom",
            "model": "fallback-model",
            "custom_api_base": "https://fallback.example/v1",
            "custom_api_key": api_key,
        },
    )

    model_health = next(item for item in run_health_checks() if item.name == "model_config")

    assert model_health.ok is True
    assert api_key not in model_health.detail


def test_ai_generation_configured_adapter_uses_existing_model_http_client(investment_env, monkeypatch):
    from business.investment import config_service
    from business.investment.ai_generation import ExistingModelAdapter, generate_rate_text
    from business.investment.config_service import save_configs

    monkeypatch.setattr(
        config_service,
        "conf",
        lambda: {
            "bot_type": "custom",
            "model": "configured-model",
            "custom_api_base": "https://configured.example/v1",
            "custom_api_key": "sk-http-client-1234567890",
            "temperature": 0.33,
        },
    )
    save_configs({"prompt.rate": "Configured rate prompt"}, operator_role="admin")

    class FakeClient:
        def __init__(self):
            self.calls = []

        def chat_completions(self, **kwargs):
            self.calls.append(kwargs)
            return {"choices": [{"message": {"content": "standard rate text"}}]}

    client = FakeClient()

    result = generate_rate_text("rate source", adapter=ExistingModelAdapter(client=client))

    assert result.success is True
    assert result.generated_text == "standard rate text"
    assert client.calls == [
        {
            "api_key": "sk-http-client-1234567890",
            "api_base": "https://configured.example/v1",
            "model": "configured-model",
            "messages": [
                {"role": "system", "content": "Configured rate prompt"},
                {"role": "user", "content": "rate source"},
            ],
            "temperature": 0.33,
            "stream": False,
        }
    ]


def test_technical_analysis_failure_records_sanitized_backend_detail(investment_env, monkeypatch):
    from business.investment import config_service
    from business.investment.constants import ErrorCode, ServiceType
    from business.investment.records import list_request_records
    from business.investment.router import handle_text_message
    from business.investment.technical_analysis import TechnicalAnalysisResult
    from business.investment.user_service import create_user

    api_key = "sk-ta-secret-1234567890"
    monkeypatch.setattr(config_service, "conf", lambda: {"custom_api_key": api_key})
    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])

    reply = handle_text_message(
        "ok",
        "300502.SZ 技术分析",
        technical_analysis_handler=lambda _openid, _raw_input, _target: TechnicalAnalysisResult(
            False,
            error_code=ErrorCode.TECHNICAL_ANALYSIS_FAILED,
            detail=f"skill crashed while using {api_key}",
        ),
    )

    record = list_request_records(limit=1)[0]
    assert reply.success is False
    assert record.error_code == ErrorCode.TECHNICAL_ANALYSIS_FAILED
    assert "skill crashed" in record.error_message
    assert api_key not in record.error_message


def test_technical_analysis_uses_skill_cli_symbol_and_saves_all_outputs(investment_env, tmp_path, monkeypatch):
    from business.investment import technical_analysis
    from business.investment.technical_analysis import TechnicalAnalysisRequest, run_technical_analysis

    request = TechnicalAnalysisRequest(openid="ok", raw_input="300502.SZ 技术分析", target_text="300502.SZ")
    assert request.openid == "ok"
    assert request.raw_input == "300502.SZ 技术分析"
    assert request.target_text == "300502.SZ"

    calls = []
    report = tmp_path / "300502_技术分析报告_2026-05-25.md"
    chart = tmp_path / "300502_TA_2026-05-25.png"
    report.write_text("# 技术分析报告\n\n核心观点", encoding="utf-8")
    chart.write_bytes(b"chart")

    def fake_skill(symbol, output_dir):
        calls.append(("skill", symbol, output_dir.name))
        return report, chart

    def fake_ai(report_text):
        calls.append(("ai", report_text))
        return SimpleNamespace(success=True, text="signal card standard text")

    def fake_render(standard_text, output_path):
        calls.append(("render", standard_text, Path(output_path).name))
        Path(output_path).write_bytes(b"card")
        return SimpleNamespace(success=True, image_path=str(output_path), detail="")

    monkeypatch.setattr(technical_analysis, "_run_skill", fake_skill)
    monkeypatch.setattr(technical_analysis, "generate_technical_analysis_text", fake_ai)
    monkeypatch.setattr(technical_analysis, "render_technical_analysis_card", fake_render)

    result = run_technical_analysis("ok", "300502.SZ 技术分析")

    assert result.success is True
    assert calls == [
        ("skill", "300502", "300502_SZ"),
        ("ai", "# 技术分析报告\n\n核心观点"),
        ("render", "signal card standard text", "300502_SZ_signal_card.png"),
    ]
    assert result.report_path == str(report)
    assert result.main_chart_path == str(chart)
    assert result.signal_card_path.endswith("300502_SZ_signal_card.png")
    assert result.output_files == [result.signal_card_path, str(chart), str(report)]


def test_stock_resolver_resolves_codes_names_and_business_prompts(investment_env, monkeypatch):
    from business.investment import stock_resolver
    from business.investment.constants import ErrorCode, user_message
    from business.investment.stock_resolver import (
        list_stock_symbols,
        refresh_stock_symbols,
        resolve_stock as core_resolve_stock,
        stock_dictionary_stats,
    )
    from business.investment.technical_analysis import resolve_stock as technical_resolve_stock
    from business.investment.technical_analysis import run_technical_analysis

    monkeypatch.setattr(stock_resolver, "refresh_from_auto", lambda: {})
    inserted = refresh_stock_symbols(
        [
            {"code": "300502.SZ", "name": "新易盛", "market": "SZ", "ts_code": "300502.SZ"},
            {"code": "000001.SZ", "name": "重名", "market": "SZ"},
            {"code": "600001.SH", "name": "重名", "market": "SH", "source": "row-source"},
        ],
        source="test-source",
    )

    assert inserted == 3
    assert core_resolve_stock("300502") == ("300502.SZ", None)
    assert core_resolve_stock("300502.SZ") == ("300502.SZ", None)
    assert core_resolve_stock("600519.SH") == ("600519.SH", None)
    assert core_resolve_stock("新易盛") == ("300502.SZ", None)
    assert core_resolve_stock("不存在的股票") == (None, ErrorCode.STOCK_NOT_FOUND)
    assert core_resolve_stock("重名") == (None, ErrorCode.STOCK_AMBIGUOUS)
    assert technical_resolve_stock("新易盛") == ("300502.SZ", None)
    assert [row["code"] for row in list_stock_symbols("新", limit=5)] == ["300502.SZ"]
    assert stock_dictionary_stats()["total"] == 3

    not_found = run_technical_analysis("ok", "不存在的股票 技术分析")
    ambiguous_symbol, ambiguous_error = technical_resolve_stock("重名")

    assert not_found.success is False
    assert not_found.error_code == ErrorCode.STOCK_NOT_FOUND
    assert not_found.user_prompt == user_message(ErrorCode.STOCK_NOT_FOUND)
    assert ambiguous_symbol is None
    assert ambiguous_error == ErrorCode.STOCK_AMBIGUOUS
    assert user_message(ambiguous_error) == "股票名称匹配到多个标的，请改用股票代码。"


def test_stock_resolver_auto_refreshes_once_for_name_miss_then_resolves(investment_env, monkeypatch):
    from business.investment import stock_resolver

    calls = []

    def fake_refresh():
        calls.append("refresh")
        stock_resolver.refresh_stock_symbols(
            [{"code": "300502.SZ", "name": "新易盛", "market": "SZ", "source": "fake"}],
            source="fake",
        )
        return {"fake": {"count": 1}}

    monkeypatch.setattr(stock_resolver, "refresh_from_auto", fake_refresh)

    assert stock_resolver.resolve_stock("新易盛") == ("300502.SZ", None)
    assert calls == ["refresh"]


def test_stock_resolver_auto_refresh_miss_respects_flag_errors_and_codes(investment_env, monkeypatch):
    from business.investment import stock_resolver
    from business.investment.constants import ErrorCode

    calls = []

    def fake_refresh():
        calls.append("refresh")
        raise RuntimeError("refresh failed")

    monkeypatch.setattr(stock_resolver, "refresh_from_auto", fake_refresh)

    assert stock_resolver.resolve_stock("新易盛", auto_refresh_on_miss=False) == (None, ErrorCode.STOCK_NOT_FOUND)
    assert stock_resolver.resolve_stock("新易盛") == (None, ErrorCode.STOCK_NOT_FOUND)
    assert stock_resolver.resolve_stock("300502") == ("300502.SZ", None)
    assert stock_resolver.resolve_stock("300502.SZ") == ("300502.SZ", None)
    assert calls == ["refresh"]


def test_stock_resolver_auto_refresh_reports_ambiguous_after_refresh(investment_env, monkeypatch):
    from business.investment import stock_resolver
    from business.investment.constants import ErrorCode

    def fake_refresh():
        stock_resolver.refresh_stock_symbols(
            [
                {"code": "000001.SZ", "name": "重名", "market": "SZ"},
                {"code": "600001.SH", "name": "重名", "market": "SH"},
            ],
            source="fake",
        )
        return {"fake": {"count": 2}}

    monkeypatch.setattr(stock_resolver, "refresh_from_auto", fake_refresh)

    assert stock_resolver.resolve_stock("重名") == (None, ErrorCode.STOCK_AMBIGUOUS)


class _FakeDataFrame:
    def __init__(self, rows):
        self._rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return self._rows


def test_stock_resolver_refreshes_from_akshare_fake_dataframe(investment_env, monkeypatch):
    from business.investment import stock_resolver

    fake_akshare = SimpleNamespace(
        stock_info_a_code_name=lambda: _FakeDataFrame(
            [
                {"code": "600519", "name": "贵州茅台"},
                {"代码": "300502", "名称": "新易盛"},
            ]
        )
    )
    monkeypatch.setitem(sys.modules, "akshare", fake_akshare)

    assert stock_resolver.refresh_from_akshare() == 2

    rows = {row["code"]: row for row in stock_resolver.list_stock_symbols(limit=10)}
    assert rows["600519.SH"]["name"] == "贵州茅台"
    assert rows["600519.SH"]["market"] == "SH"
    assert rows["600519.SH"]["source"] == "akshare"
    assert rows["300502.SZ"]["name"] == "新易盛"
    assert rows["300502.SZ"]["market"] == "SZ"
    assert rows["300502.SZ"]["source"] == "akshare"


def test_stock_resolver_refreshes_large_symbol_batch(investment_env):
    from business.investment import stock_resolver

    rows = [
        {"code": f"{index:06d}.SZ", "name": f"Test Stock {index}", "market": "SZ"}
        for index in range(6000)
    ]

    assert stock_resolver.refresh_stock_symbols(rows, source="large-batch") == 6000
    assert stock_resolver.stock_dictionary_stats()["total"] == 6000


def test_stock_resolver_tushare_token_priority_and_masking(investment_env, tmp_path, monkeypatch):
    from business.investment import stock_resolver
    from business.investment.config_service import get_config, save_config

    monkeypatch.setattr(stock_resolver.Path, "home", lambda: tmp_path)
    (tmp_path / ".tushare_token").write_text("file-token-1234567890", encoding="utf-8")
    monkeypatch.setenv("TUSHARE_TOKEN", "env-token-1234567890")

    assert stock_resolver.get_tushare_token() == "env-token-1234567890"

    save_config("tushare.token", "config-token-1234567890", operator_role="admin")

    assert stock_resolver.get_tushare_token() == "config-token-1234567890"
    assert stock_resolver.get_tushare_token(masked=True) == "conf**********7890"
    assert get_config("tushare.token", masked=True) == "conf**********7890"


def test_stock_resolver_tushare_token_falls_back_to_file(investment_env, tmp_path, monkeypatch):
    from business.investment import stock_resolver

    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.setattr(stock_resolver.Path, "home", lambda: tmp_path)
    (tmp_path / ".tushare_token").write_text("file-token-1234567890\n", encoding="utf-8")

    assert stock_resolver.get_tushare_token() == "file-token-1234567890"


def test_stock_resolver_refresh_from_tushare_requires_token(investment_env, tmp_path, monkeypatch):
    from business.investment import stock_resolver

    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.setattr(stock_resolver.Path, "home", lambda: tmp_path)

    with pytest.raises(RuntimeError, match="tushare token not configured"):
        stock_resolver.refresh_from_tushare()


def test_stock_resolver_refreshes_from_tushare_fake_dataframe(investment_env, monkeypatch):
    from business.investment import stock_resolver
    from business.investment.config_service import save_config

    calls = []

    class FakePro:
        def stock_basic(self, **kwargs):
            calls.append(kwargs)
            return _FakeDataFrame(
                [
                    {"ts_code": "600519.SH", "symbol": "600519", "name": "贵州茅台", "exchange": "SSE"},
                    {"ts_code": "300502.SZ", "symbol": "300502", "name": "新易盛", "exchange": "SZSE"},
                ]
            )

    fake_tushare = SimpleNamespace(pro_api=lambda token: calls.append({"token": token}) or FakePro())
    monkeypatch.setitem(sys.modules, "tushare", fake_tushare)
    save_config("tushare.token", "config-token-1234567890", operator_role="admin")

    assert stock_resolver.refresh_from_tushare() == 2

    assert calls == [
        {"token": "config-token-1234567890"},
        {"exchange": "", "list_status": "L", "fields": "ts_code,symbol,name,exchange"},
    ]
    rows = {row["code"]: row for row in stock_resolver.list_stock_symbols(limit=10)}
    assert rows["600519.SH"]["ts_code"] == "600519.SH"
    assert rows["600519.SH"]["market"] == "SH"
    assert rows["600519.SH"]["source"] == "tushare"
    assert rows["300502.SZ"]["ts_code"] == "300502.SZ"
    assert rows["300502.SZ"]["market"] == "SZ"
    assert rows["300502.SZ"]["source"] == "tushare"


def test_stock_resolver_auto_reports_source_counts_and_errors(investment_env, monkeypatch):
    from business.investment import stock_resolver

    monkeypatch.setattr(stock_resolver, "refresh_from_akshare", lambda: 2)
    monkeypatch.setattr(stock_resolver, "get_tushare_token", lambda masked=False: "token")
    monkeypatch.setattr(stock_resolver, "refresh_from_tushare", lambda: 3)

    assert stock_resolver.refresh_from_auto() == {"akshare": {"count": 2}, "tushare": {"count": 3}}

    monkeypatch.setattr(stock_resolver, "refresh_from_akshare", lambda: (_ for _ in ()).throw(RuntimeError("ak failed")))
    monkeypatch.setattr(stock_resolver, "refresh_from_tushare", lambda: (_ for _ in ()).throw(RuntimeError("ts failed")))

    assert stock_resolver.refresh_from_auto() == {
        "akshare": {"error": "ak failed"},
        "tushare": {"error": "ts failed"},
    }


def test_refresh_investment_stocks_script_dispatches_sources(investment_env, monkeypatch, capsys):
    from scripts import refresh_investment_stocks

    calls = []
    monkeypatch.setattr(refresh_investment_stocks.storage, "initialize_storage", lambda: calls.append("init"))
    monkeypatch.setattr(refresh_investment_stocks.stock_resolver, "refresh_from_auto", lambda: calls.append("auto") or {"akshare": {"count": 2}})
    monkeypatch.setattr(refresh_investment_stocks.stock_resolver, "refresh_from_akshare", lambda: calls.append("akshare") or 3)
    monkeypatch.setattr(refresh_investment_stocks.stock_resolver, "refresh_from_tushare", lambda: calls.append("tushare") or 4)

    assert refresh_investment_stocks.main(["--source", "auto", "--json"]) == 0
    assert refresh_investment_stocks.main(["--source", "akshare", "--json"]) == 0
    assert refresh_investment_stocks.main(["--source", "tushare", "--json"]) == 0

    assert calls == ["init", "auto", "init", "akshare", "init", "tushare"]
    payloads = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
    assert [payload["source"] for payload in payloads] == ["auto", "akshare", "tushare"]
    assert [payload["count"] for payload in payloads] == [2, 3, 4]
    assert all(payload["success"] is True for payload in payloads)
    assert all("db_path" in payload for payload in payloads)


def test_refresh_investment_stocks_script_exits_one_when_all_sources_fail(investment_env, monkeypatch, capsys):
    from scripts import refresh_investment_stocks

    monkeypatch.setattr(refresh_investment_stocks.storage, "initialize_storage", lambda: None)
    monkeypatch.setattr(
        refresh_investment_stocks.stock_resolver,
        "refresh_from_auto",
        lambda: {"akshare": {"error": "ak failed"}, "tushare": {"error": "ts failed"}},
    )

    assert refresh_investment_stocks.main(["--source", "auto", "--json"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["source"] == "auto"
    assert payload["success"] is False
    assert payload["count"] == 0
    assert "akshare: ak failed" in payload["error"]
    assert "tushare: ts failed" in payload["error"]


def test_refresh_investment_stocks_script_reports_single_source_exceptions(investment_env, monkeypatch, capsys):
    from scripts import refresh_investment_stocks

    monkeypatch.setattr(refresh_investment_stocks.storage, "initialize_storage", lambda: None)
    monkeypatch.setattr(
        refresh_investment_stocks.stock_resolver,
        "refresh_from_akshare",
        lambda: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
    )

    assert refresh_investment_stocks.main(["--source", "akshare", "--json"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["source"] == "akshare"
    assert payload["success"] is False
    assert payload["count"] == 0
    assert payload["error"] == "provider unavailable"


def test_refresh_investment_stocks_script_runs_by_file_path():
    repo_root = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [sys.executable, "scripts/refresh_investment_stocks.py", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--source" in result.stdout


def test_sqlite_to_pg_migration_rejects_missing_sqlite_file(tmp_path):
    from scripts import migrate_investment_sqlite_to_pg

    missing = tmp_path / "missing.db"

    with pytest.raises(FileNotFoundError, match="SQLite source does not exist"):
        migrate_investment_sqlite_to_pg.migrate_sqlite_to_postgres(
            missing,
            "postgresql+psycopg://user:secret@localhost:5432/cowagent",
        )


def test_sqlite_to_pg_migration_rejects_non_postgresql_url(tmp_path):
    from scripts import migrate_investment_sqlite_to_pg

    sqlite_path = tmp_path / "investment.db"
    sqlite_path.write_bytes(b"")

    with pytest.raises(ValueError, match="target URL must be PostgreSQL"):
        migrate_investment_sqlite_to_pg.migrate_sqlite_to_postgres(
            sqlite_path,
            f"sqlite:///{tmp_path / 'target.db'}",
        )


def test_sqlite_to_pg_migration_reads_all_tables_and_upserts(tmp_path, monkeypatch):
    from sqlalchemy import create_engine

    from business.investment import schema
    from scripts import migrate_investment_sqlite_to_pg

    sqlite_path = tmp_path / "investment.db"
    engine = create_engine(f"sqlite:///{sqlite_path}", future=True)
    schema.metadata.create_all(engine)
    now = "2026-05-25T10:00:00"
    with engine.begin() as conn:
        conn.execute(
            schema.investment_users.insert(),
            {
                "id": 1,
                "openid": "openid-1",
                "name": "Alice",
                "enabled": 1,
                "allowed_services": "[\"rate\"]",
                "created_at": now,
                "updated_at": now,
            },
        )
        conn.execute(
            schema.investment_request_records.insert(),
            {
                "request_id": "request-1",
                "openid": "openid-1",
                "raw_input": "利率",
                "service_type": "rate",
                "status": "success",
                "created_at": now,
                "updated_at": now,
            },
        )
        conn.execute(
            schema.investment_daily_contents.insert(),
            {
                "content_id": "content-1",
                "service_type": "rate",
                "status": "draft",
                "created_at": now,
                "updated_at": now,
            },
        )
        conn.execute(
            schema.investment_output_files.insert(),
            {
                "id": 1,
                "owner_id": "content-1",
                "file_path": "/tmp/rate.png",
                "file_type": "image",
                "service_type": "rate",
                "created_at": now,
            },
        )
        conn.execute(
            schema.investment_configs.insert(),
            {
                "config_key": "model.api_key",
                "config_value": "sk-test-secret",
                "updated_at": now,
                "updated_by": "admin",
            },
        )
        conn.execute(
            schema.investment_configs.insert(),
            {
                "config_key": "wechatmp.token",
                "config_value": "wx-test-token",
                "updated_at": now,
                "updated_by": "admin",
            },
        )
        conn.execute(
            schema.investment_configs.insert(),
            {
                "config_key": "tushare.token",
                "config_value": "ts-test-token",
                "updated_at": now,
                "updated_by": "admin",
            },
        )
        conn.execute(
            schema.investment_stock_symbols.insert(),
            {
                "code": "300502.SZ",
                "name": "新易盛",
                "market": "SZ",
                "ts_code": "300502.SZ",
                "source": "seed",
                "updated_at": now,
            },
        )

    tables = migrate_investment_sqlite_to_pg.read_sqlite_tables(sqlite_path)
    assert list(tables) == [
        "investment_users",
        "investment_request_records",
        "investment_daily_contents",
        "investment_output_files",
        "investment_configs",
        "investment_stock_symbols",
    ]
    assert {name: len(rows) for name, rows in tables.items()} == {
        **{name: 1 for name in tables},
        "investment_configs": 3,
    }

    calls = []

    class FakeConnection:
        dialect = SimpleNamespace(name="postgresql")

        def execute(self, statement):
            calls.append(("execute", statement))

    class FakeBegin:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeEngine:
        def begin(self):
            return FakeBegin()

    monkeypatch.setattr(schema.metadata, "create_all", lambda conn: pytest.fail("migration target schema must be built by Alembic"))
    monkeypatch.setattr(
        migrate_investment_sqlite_to_pg,
        "upgrade_investment_schema",
        lambda pg_url: calls.append(("alembic_upgrade", pg_url)),
        raising=False,
    )
    monkeypatch.setattr(
        migrate_investment_sqlite_to_pg.investment_db,
        "upsert_config",
        lambda conn, key, value, updated_at, updated_by: calls.append(("config", key, value, updated_at, updated_by)),
    )
    monkeypatch.setattr(
        migrate_investment_sqlite_to_pg.investment_db,
        "upsert_stock_symbols",
        lambda conn, rows: calls.append(("stocks", rows)),
    )

    summary = migrate_investment_sqlite_to_pg.copy_tables_to_postgres(
        "postgresql+psycopg://user:secret@localhost:5432/cowagent",
        tables,
        engine_factory=lambda url, future: calls.append(("engine", url, future)) or FakeEngine(),
    )

    assert summary == {
        **{name: 1 for name in tables},
        "investment_configs": 1,
    }
    assert ("engine", "postgresql+psycopg://user:secret@localhost:5432/cowagent", True) in calls
    assert ("alembic_upgrade", "postgresql+psycopg://user:secret@localhost:5432/cowagent") in calls
    assert calls.index(("alembic_upgrade", "postgresql+psycopg://user:secret@localhost:5432/cowagent")) < next(
        index for index, call in enumerate(calls) if call[0] in {"execute", "config", "stocks"}
    )
    assert any(call[:3] == ("config", "tushare.token", "ts-test-token") for call in calls)
    assert not any(call[:2] == ("config", "model.api_key") for call in calls)
    assert not any(call[:2] == ("config", "wechatmp.token") for call in calls)
    assert any(call[0] == "stocks" and call[1][0]["code"] == "300502.SZ" for call in calls)
    assert len([call for call in calls if call[0] == "execute"]) == 6


def test_sqlite_to_pg_migration_resets_postgres_sequences_after_copy(monkeypatch):
    from scripts import migrate_investment_sqlite_to_pg

    calls = []

    class FakeConnection:
        dialect = SimpleNamespace(name="postgresql")

        def execute(self, statement):
            calls.append(("execute", statement))

    class FakeBegin:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeEngine:
        def begin(self):
            return FakeBegin()

    monkeypatch.setattr(
        migrate_investment_sqlite_to_pg,
        "upgrade_investment_schema",
        lambda pg_url: calls.append(("alembic_upgrade", pg_url)),
        raising=False,
    )
    monkeypatch.setattr(
        migrate_investment_sqlite_to_pg.schema.metadata,
        "create_all",
        lambda conn: pytest.fail("migration target schema must be built by Alembic"),
    )
    monkeypatch.setattr(
        migrate_investment_sqlite_to_pg.investment_db,
        "upsert_stock_symbols",
        lambda conn, rows: calls.append(("stocks", rows)),
    )

    tables = OrderedDict((name, []) for name in migrate_investment_sqlite_to_pg.TABLE_NAMES)
    tables["investment_users"] = [
        {
            "id": 7,
            "openid": "openid-7",
            "name": "Alice",
            "enabled": 1,
            "allowed_services": "[\"rate\"]",
            "created_at": "2026-05-25T10:00:00",
            "updated_at": "2026-05-25T10:00:00",
        }
    ]
    tables["investment_output_files"] = [
        {
            "id": 11,
            "owner_id": "content-1",
            "file_path": "/tmp/rate.png",
            "file_type": "image",
            "service_type": "rate",
            "created_at": "2026-05-25T10:00:00",
        }
    ]

    migrate_investment_sqlite_to_pg.copy_tables_to_postgres(
        "postgresql+psycopg://user:secret@localhost:5432/cowagent",
        tables,
        engine_factory=lambda url, future: FakeEngine(),
    )

    executed_sql = [str(call[1]) for call in calls if call[0] == "execute"]
    sequence_sql = [sql for sql in executed_sql if "setval" in sql]

    assert len(sequence_sql) == 2
    assert "pg_get_serial_sequence('investment_users', 'id')" in sequence_sql[0]
    assert "pg_get_serial_sequence('investment_output_files', 'id')" in sequence_sql[1]
    assert all("(select count(*)" in sql and "> 0" in sql for sql in sequence_sql)
    assert executed_sql.index(sequence_sql[0]) > 1
    assert executed_sql.index(sequence_sql[1]) > 1


def test_sqlite_to_pg_migration_output_does_not_include_pg_url(tmp_path, monkeypatch, capsys):
    from scripts import migrate_investment_sqlite_to_pg

    sqlite_path = tmp_path / "investment.db"
    sqlite_path.write_bytes(b"")
    pg_url = "postgresql+psycopg://user:super-secret-password@localhost:5432/cowagent"

    monkeypatch.setattr(
        migrate_investment_sqlite_to_pg,
        "migrate_sqlite_to_postgres",
        lambda sqlite_arg, pg_arg: {
            "status": "success",
            "tables": {"investment_users": 1},
        },
    )

    assert migrate_investment_sqlite_to_pg.main(["--sqlite", str(sqlite_path), "--pg", pg_url]) == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload == {"status": "success", "tables": {"investment_users": 1}}
    assert pg_url not in output
    assert "super-secret-password" not in output


def test_tushare_token_config_permission_is_sensitive(investment_env):
    from business.investment.config_service import can_modify_config, save_config

    assert can_modify_config("tushare.token", "uploader") is False
    assert can_modify_config("tushare.token", "operator") is False
    assert can_modify_config("tushare.token", "technical_admin") is True

    with pytest.raises(PermissionError):
        save_config("tushare.token", "blocked-token", operator_role="operator")


def test_technical_analysis_sh_suffix_enters_skill_and_failures_return_business_prompts(investment_env, tmp_path, monkeypatch):
    from business.investment import technical_analysis
    from business.investment.constants import ErrorCode, user_message
    from business.investment.technical_analysis import run_technical_analysis

    report = tmp_path / "600519_技术分析报告_2026-05-25.md"
    chart = tmp_path / "600519_TA_2026-05-25.png"
    report.write_text("ta report", encoding="utf-8")
    chart.write_bytes(b"chart")
    calls = []

    def fake_skill(symbol, _output_dir):
        calls.append(symbol)
        return report, chart

    monkeypatch.setattr(technical_analysis, "_run_skill", fake_skill)
    monkeypatch.setattr(
        technical_analysis,
        "generate_technical_analysis_text",
        lambda _report_text: SimpleNamespace(success=False, detail="model failed"),
    )

    ai_failed = run_technical_analysis("ok", "600519.SH 技术分析")

    assert calls == ["600519"]
    assert ai_failed.success is False
    assert ai_failed.error_code == ErrorCode.TECHNICAL_ANALYSIS_FAILED
    assert ai_failed.user_prompt == user_message(ErrorCode.TECHNICAL_ANALYSIS_FAILED)

    monkeypatch.setattr(
        technical_analysis,
        "generate_technical_analysis_text",
        lambda _report_text: SimpleNamespace(success=True, text="standard"),
    )
    monkeypatch.setattr(
        technical_analysis,
        "render_technical_analysis_card",
        lambda _standard_text, _output_path: SimpleNamespace(success=False, detail="renderer failed"),
    )

    render_failed = run_technical_analysis("ok", "600519.SH 技术分析")

    assert render_failed.success is False
    assert render_failed.error_code == ErrorCode.IMAGE_GENERATION_FAILED
    assert render_failed.user_prompt == user_message(ErrorCode.IMAGE_GENERATION_FAILED)

    calls.clear()
    def successful_render(_standard_text, output_path):
        Path(output_path).write_bytes(b"card")
        return SimpleNamespace(success=True, image_path=output_path, detail="")

    monkeypatch.setattr(technical_analysis, "render_technical_analysis_card", successful_render)

    standard_code = run_technical_analysis("ok", "600519 技术分析")

    assert standard_code.success is True
    assert calls == ["600519"]


def test_router_records_technical_analysis_report_chart_and_card_paths(investment_env, tmp_path):
    from business.investment.constants import ServiceType
    from business.investment.records import list_request_records
    from business.investment.router import handle_text_message
    from business.investment.technical_analysis import TechnicalAnalysisResult
    from business.investment.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    card = str(tmp_path / "card.png")
    chart = str(tmp_path / "chart.png")
    report = str(tmp_path / "report.md")

    reply = handle_text_message(
        "ok",
        "300502.SZ 技术分析",
        technical_analysis_handler=lambda _openid, _raw_input, _target: TechnicalAnalysisResult(
            True,
            signal_card_path=card,
            main_chart_path=chart,
            report_path=report,
            output_files=[card, chart, report],
        ),
    )

    record = list_request_records(limit=1)[0]
    assert reply.success is True
    assert reply.output_files == [card, chart]
    assert record.output_files == [card, chart, report]


def test_daily_content_activation_and_query(investment_env, tmp_path):
    from business.investment.constants import ErrorCode, ServiceType
    from business.investment.daily_content import (
        create_content_draft,
        get_latest_effective_content,
        set_content_effective,
    )

    empty = get_latest_effective_content(ServiceType.RATE)
    assert empty.success is False
    assert empty.error_code == ErrorCode.NO_CONTENT

    first_img = tmp_path / "first.png"
    second_img = tmp_path / "second.png"
    first_img.write_bytes(b"png")
    second_img.write_bytes(b"png2")

    first = create_content_draft(ServiceType.RATE, source_text="first")
    second = create_content_draft(ServiceType.RATE, source_text="second")
    set_content_effective(first, str(first_img), operator="admin")
    set_content_effective(second, str(second_img), operator="admin")

    latest = get_latest_effective_content(ServiceType.RATE)
    assert latest.success is True
    assert latest.output_image == str(second_img)


def test_daily_content_create_upload_generate_and_failure_records(investment_env):
    from business.investment.constants import ErrorCode, ServiceType, Status
    from business.investment.daily_content import (
        create_convertible_bond_content_draft,
        create_rate_content_draft,
        generate_content,
        update_content_source,
    )
    from business.investment.records import get_content_record

    content_id = create_rate_content_draft(source_files=["/upload/original.xlsx"], source_text="old", operator="operator-a")
    update_content_source(content_id, source_files=["/upload/latest.xlsx"], source_text="updated rate data")

    calls = []

    def fake_ai(service_type, source_text):
        calls.append(("ai", service_type, source_text))
        return SimpleNamespace(success=True, text="standard rate text")

    def fake_renderer(service_type, standard_text):
        calls.append(("renderer", service_type, standard_text))
        return SimpleNamespace(success=True, image_path="/generated/rate.png")

    result = generate_content(content_id, ai_generator=fake_ai, renderer=fake_renderer)

    assert result.success is True
    assert result.generated_text == "standard rate text"
    assert result.output_image == "/generated/rate.png"
    assert calls == [
        ("ai", ServiceType.RATE, "updated rate data"),
        ("renderer", ServiceType.RATE, "standard rate text"),
    ]

    record = get_content_record(content_id)
    assert record.service_type == ServiceType.RATE
    assert record.source_files == ["/upload/latest.xlsx"]
    assert record.source_text == "updated rate data"
    assert record.generated_text == "standard rate text"
    assert record.output_image == "/generated/rate.png"
    assert record.status == Status.GENERATED
    assert record.error_message == ""

    failed_id = create_convertible_bond_content_draft(source_text="cb data\n\njoke", operator="operator-b")
    failed = generate_content(
        failed_id,
        ai_generator=lambda _service_type, _source_text: SimpleNamespace(success=False, detail="model rejected payload"),
        renderer=fake_renderer,
    )
    failed_record = get_content_record(failed_id)
    assert failed.success is False
    assert failed.error_code == ErrorCode.SYSTEM_ERROR
    assert failed_record.service_type == ServiceType.CONVERTIBLE_BOND
    assert failed_record.status == Status.GENERATE_FAILED
    assert failed_record.error_message == "model rejected payload"


def test_daily_content_default_generation_passes_uploaded_source_files(investment_env, tmp_path, monkeypatch):
    from business.investment.constants import ServiceType
    from business.investment.daily_content import create_rate_content_draft, generate_content

    uploaded = tmp_path / "uploaded-rate.png"
    uploaded.write_bytes(b"png")
    content_id = create_rate_content_draft(source_files=[str(uploaded)], source_text="", operator="operator-a")
    captured = {}

    def fake_generate_standard_text(service_type, source_text, *, source_files=None):
        captured["service_type"] = service_type
        captured["source_text"] = source_text
        captured["source_files"] = source_files
        return SimpleNamespace(success=True, text="standard rate text")

    monkeypatch.setattr(
        "business.investment.ai_generation.generate_standard_text",
        fake_generate_standard_text,
    )

    result = generate_content(
        content_id,
        renderer=lambda _service_type, _text: SimpleNamespace(success=True, image_path="/generated/rate.png"),
    )

    assert result.success is True
    assert captured == {
        "service_type": ServiceType.RATE,
        "source_text": "",
        "source_files": [str(uploaded)],
    }


def test_daily_content_default_image_generation_renders_png_with_fake_model(investment_env, tmp_path, monkeypatch):
    from business.investment import config_service
    from business.investment.config_service import save_configs
    from business.investment.constants import ServiceType
    from business.investment.daily_content import create_rate_content_draft, generate_content
    from business.investment.records import get_content_record

    source_image = tmp_path / "uploaded-rate.png"
    source_image.write_bytes(b"\x89PNG\r\n\x1a\nimage")
    output_dir = tmp_path / "generated"
    monkeypatch.setattr(
        config_service,
        "conf",
        lambda: {
            "bot_type": "custom",
            "model": "vision-model",
            "custom_api_base": "https://model.example/v1",
            "custom_api_key": "sk-e2e-image-1234567890",
        },
    )
    save_configs(
        {"render.output_dir": str(output_dir)},
        operator_role="admin",
    )
    standard_text = Path("skills/signal-card-renderer/examples/bond_sample.txt").read_text(encoding="utf-8")

    class FakeClient:
        def __init__(self):
            self.calls = []

        def chat_completions(self, **kwargs):
            self.calls.append(kwargs)
            user_content = kwargs["messages"][1]["content"]
            if len(self.calls) == 1:
                assert any(block.get("type") == "image_url" for block in user_content)
                return {"choices": [{"message": {"content": "OCR: 2026-05-25 108.970 入场（3/8）"}}]}
            assert "必须只输出卡片正文" in kwargs["messages"][0]["content"]
            assert "OCR: 2026-05-25 108.970 入场（3/8）" in user_content
            return {"choices": [{"message": {"content": standard_text}}]}

    fake_client = FakeClient()
    monkeypatch.setattr(
        "models.openai.openai_http_client.get_default_client",
        lambda: fake_client,
    )

    content_id = create_rate_content_draft(source_files=[str(source_image)], source_text="", operator="operator-a")
    result = generate_content(content_id)

    assert result.success is True
    assert Path(result.output_image).is_file()
    assert Path(result.output_image).stat().st_size > 0
    assert result.output_image == str(output_dir / f"{ServiceType.RATE}_card.png")
    assert get_content_record(content_id).output_image == result.output_image
    assert fake_client.calls


def test_daily_content_records_filter_by_service_type_for_console_pages(investment_env):
    from business.investment.constants import ServiceType
    from business.investment.daily_content import create_convertible_bond_content_draft, create_rate_content_draft
    from business.investment.records import list_content_records

    rate_id = create_rate_content_draft(source_text="rate")
    cb_id = create_convertible_bond_content_draft(source_text="cb")

    rate_records = list_content_records(service_type=ServiceType.RATE)
    cb_records = list_content_records(service_type=ServiceType.CONVERTIBLE_BOND)

    assert [record.content_id for record in rate_records] == [rate_id]
    assert [record.content_id for record in cb_records] == [cb_id]


def test_daily_content_upload_saves_files_under_investment_upload_dir(investment_env):
    from business.investment.constants import ServiceType
    from business.investment.daily_content import save_source_file

    saved = save_source_file(ServiceType.RATE, "rates.xlsx", b"rate-data")

    assert Path(saved).read_bytes() == b"rate-data"
    assert investment_env / "storage" / "uploads" in Path(saved).parents

    with pytest.raises(ValueError):
        save_source_file(ServiceType.RATE, "../escape.txt", b"bad")


def test_daily_content_regenerate_updates_output_and_only_latest_is_effective(investment_env):
    from business.investment.constants import ServiceType, Status
    from business.investment.daily_content import (
        create_rate_content_draft,
        generate_content,
        get_latest_effective_content,
        regenerate_content,
        set_content_effective,
    )
    from business.investment.records import get_content_record

    first_id = create_rate_content_draft(source_text="first")
    second_id = create_rate_content_draft(source_text="second")

    generate_content(
        first_id,
        ai_generator=lambda _service_type, _source_text: SimpleNamespace(success=True, text="first text"),
        renderer=lambda _service_type, _text: SimpleNamespace(success=True, image_path="/generated/first.png"),
    )
    generate_content(
        second_id,
        ai_generator=lambda _service_type, _source_text: SimpleNamespace(success=True, text="second text"),
        renderer=lambda _service_type, _text: SimpleNamespace(success=True, image_path="/generated/second.png"),
    )
    set_content_effective(first_id, operator="operator-a")
    set_content_effective(second_id, operator="operator-b")

    assert get_content_record(first_id).status == Status.ARCHIVED
    assert get_content_record(second_id).status == Status.EFFECTIVE
    assert get_latest_effective_content(ServiceType.RATE).output_image == "/generated/second.png"

    regenerated = regenerate_content(
        second_id,
        ai_generator=lambda _service_type, _source_text: SimpleNamespace(success=True, text="second text regenerated"),
        renderer=lambda _service_type, _text: SimpleNamespace(success=True, image_path="/generated/second-v2.png"),
    )

    assert regenerated.success is True
    assert regenerated.generated_text == "second text regenerated"
    assert regenerated.output_image == "/generated/second-v2.png"
    updated_record = get_content_record(second_id)
    assert updated_record.generated_text == "second text regenerated"
    assert updated_record.output_image == "/generated/second-v2.png"
    assert updated_record.status == Status.GENERATED


def test_daily_content_convertible_bond_no_effective_content_prompt(investment_env):
    from business.investment.constants import ErrorCode, ServiceType
    from business.investment.daily_content import get_latest_effective_content

    empty = get_latest_effective_content(ServiceType.CONVERTIBLE_BOND)
    assert empty.success is False
    assert empty.error_code == ErrorCode.NO_CONTENT
    assert empty.user_prompt == "今日内容尚未更新，请稍后再试。"


def test_render_service_validates_output_files(investment_env, tmp_path):
    from business.investment.constants import ErrorCode, ServiceType
    from business.investment.render_service import RenderRequest, render_card

    output = tmp_path / "card.png"

    def fake_renderer(_request, target):
        Path(target).write_bytes(b"png")

    result = render_card(
        RenderRequest(service_type=ServiceType.RATE, standard_text="text", output_path=str(output)),
        renderer=fake_renderer,
    )
    assert result.success is True
    assert result.image_path == str(output)

    def empty_renderer(_request, target):
        Path(target).write_bytes(b"")

    failed = render_card(
        RenderRequest(service_type=ServiceType.RATE, standard_text="text", output_path=str(output)),
        renderer=empty_renderer,
    )
    assert failed.success is False
    assert failed.error_code == ErrorCode.IMAGE_GENERATION_FAILED


def test_render_service_contract_uses_configured_templates_and_output_dir(investment_env, tmp_path):
    from business.investment.config_service import save_configs
    from business.investment.constants import ServiceType, Status
    from business.investment.render_service import RenderRequest, render_card

    template_ta = tmp_path / "template_ta.html"
    template_bond = tmp_path / "template_bond.html"
    template_cb = tmp_path / "template_cb.html"
    for template in (template_ta, template_bond, template_cb):
        template.write_text("<html></html>", encoding="utf-8")
    output_dir = tmp_path / "rendered"
    save_configs(
        {
            "render.template_ta_path": str(template_ta),
            "render.template_rate_path": str(template_bond),
            "render.template_cb_path": str(template_cb),
            "render.output_dir": str(output_dir),
        },
        operator_role="admin",
    )
    calls = []

    def fake_renderer(request, target):
        calls.append((request.service_type, request.standard_text, request.output_dir, request.output_path, request.template_path, target))
        Path(target).write_bytes(b"png")

    result = render_card(
        RenderRequest(service_type=ServiceType.CONVERTIBLE_BOND, standard_text="cb standard text"),
        renderer=fake_renderer,
    )

    assert result.success is True
    assert result.status == Status.SUCCESS
    assert result.service_type == ServiceType.CONVERTIBLE_BOND
    assert result.standard_text == "cb standard text"
    assert result.output_dir == str(output_dir)
    assert result.output_path == result.image_path
    assert result.image_path.startswith(str(output_dir))
    assert result.failure_reason == ""
    assert calls == [
        (
            ServiceType.CONVERTIBLE_BOND,
            "cb standard text",
            str(output_dir),
            result.output_path,
            str(template_cb),
            result.output_path,
        )
    ]


def test_render_health_check_reports_renderer_template_and_chromium_details(investment_env, tmp_path, monkeypatch):
    from business.investment import health
    from business.investment.config_service import save_configs

    missing_renderer = tmp_path / "missing-render-card.py"
    missing_ta = tmp_path / "missing-template-ta.html"
    missing_bond = tmp_path / "missing-template-bond.html"
    missing_cb = tmp_path / "missing-template-cb.html"
    save_configs(
        {
            "render.renderer_path": str(missing_renderer),
            "render.template_ta_path": str(missing_ta),
            "render.template_rate_path": str(missing_bond),
            "render.template_cb_path": str(missing_cb),
        },
        operator_role="admin",
    )
    monkeypatch.setattr(
        health,
        "_check_playwright_chromium",
        lambda: health.HealthItem("playwright_chromium", False, "chromium executable missing: C:/missing/chrome.exe"),
        raising=False,
    )

    items = {item.name: item for item in health.run_health_checks()}

    assert items["signal_card_renderer"].ok is False
    assert str(missing_renderer) in items["signal_card_renderer"].detail
    assert items["template_ta"].ok is False
    assert str(missing_ta) in items["template_ta"].detail
    assert items["template_bond"].ok is False
    assert str(missing_bond) in items["template_bond"].detail
    assert items["template_cb"].ok is False
    assert str(missing_cb) in items["template_cb"].detail
    assert items["playwright_chromium"].ok is False
    assert "chromium executable missing" in items["playwright_chromium"].detail


def test_health_check_reports_stock_dictionary_and_tushare_token_without_leaking_secret(investment_env):
    from business.investment.config_service import save_config
    from business.investment.health import run_health_checks
    from business.investment.stock_resolver import refresh_stock_symbols

    save_config("tushare.token", "ts-health-secret-1234567890", operator_role="admin")
    refresh_stock_symbols(
        [
            {"code": "300502.SZ", "name": "新易盛", "market": "SZ", "source": "seed"},
            {"code": "600519.SH", "name": "贵州茅台", "market": "SH", "source": "seed"},
        ],
        source="seed",
    )

    items = {item.name: item for item in run_health_checks()}
    details = "\n".join(item.detail for item in items.values())

    assert items["stock_dictionary_table"].ok is True
    assert items["stock_dictionary_table"].detail == "exists"
    assert items["stock_dictionary_count"].ok is True
    assert items["stock_dictionary_count"].detail == "2"
    assert items["stock_dictionary_latest"].ok is True
    assert items["stock_dictionary_latest"].detail
    assert items["stock_dictionary_latest_source"].ok is True
    assert items["stock_dictionary_latest_source"].detail == "seed"
    assert items["tushare_token"].ok is True
    assert items["tushare_token"].detail == "configured"
    assert "ts-health-secret-1234567890" not in details


def test_health_check_reports_missing_and_unwritable_directories(investment_env, tmp_path, monkeypatch):
    from business.investment import health
    from business.investment.config_service import save_configs

    missing_upload = tmp_path / "missing-upload"
    generated_dir = tmp_path / "generated"
    generated_dir.mkdir()
    save_configs(
        {
            "storage.upload_dir": str(missing_upload),
            "storage.generated_dir": str(generated_dir),
        },
        operator_role="admin",
    )

    items = {item.name: item for item in health.run_health_checks()}

    assert items["upload_dir"].ok is False
    assert f"directory does not exist: {missing_upload}" == items["upload_dir"].detail

    def fail_mkstemp(*_args, **_kwargs):
        raise PermissionError("readonly")

    monkeypatch.setattr(health.tempfile, "mkstemp", fail_mkstemp)

    items = {item.name: item for item in health.run_health_checks()}

    assert items["generated_dir"].ok is False
    assert "directory not writable" in items["generated_dir"].detail
    assert "readonly" in items["generated_dir"].detail


def test_health_check_reports_all_dependencies_available(investment_env, tmp_path, monkeypatch):
    from business.investment import health
    from business.investment import config_service
    from business.investment.config_service import save_configs
    from business.investment.stock_resolver import refresh_stock_symbols

    files = {
        "technical_analysis.skill_path": tmp_path / "analyze_universal.py",
        "render.renderer_path": tmp_path / "render_card.py",
        "render.template_ta_path": tmp_path / "template_ta.html",
        "render.template_rate_path": tmp_path / "template_bond.html",
        "render.template_cb_path": tmp_path / "template_cb.html",
    }
    for path in files.values():
        path.write_text("ok", encoding="utf-8")
    upload_dir = tmp_path / "uploads"
    generated_dir = tmp_path / "generated"
    upload_dir.mkdir()
    generated_dir.mkdir()
    monkeypatch.setattr(
        config_service,
        "conf",
        lambda: {
            "bot_type": "custom",
            "model": "model",
            "custom_api_base": "https://model.example/v1",
            "custom_api_key": "sk-health-ok-1234567890",
        },
    )
    save_configs(
        {
            **{key: str(path) for key, path in files.items()},
            "storage.upload_dir": str(upload_dir),
            "storage.generated_dir": str(generated_dir),
            "tushare.token": "ts-health-ok-1234567890",
        },
        operator_role="admin",
    )
    monkeypatch.setattr(
        health,
        "_check_playwright_chromium",
        lambda: health.HealthItem("playwright_chromium", True, "chromium ok"),
        raising=False,
    )
    refresh_stock_symbols(
        [{"code": "300502.SZ", "name": "新易盛", "market": "SZ", "source": "seed"}],
        source="seed",
    )

    items = {item.name: item for item in health.run_health_checks()}

    assert all(item.ok for item in items.values())


def test_router_handles_rate_success_unauthorized_and_miss(investment_env, tmp_path):
    from business.investment.constants import ErrorCode
    from business.investment.constants import ServiceType
    from business.investment.daily_content import create_content_draft, set_content_effective
    from business.investment.records import list_request_records
    from business.investment.router import DEFAULT_UNMATCHED_PROMPT, handle_text_message, parse_route
    from business.investment.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    image = tmp_path / "rate.png"
    image.write_bytes(b"png")
    content_id = create_content_draft(ServiceType.RATE, source_text="rate")
    set_content_effective(content_id, str(image), operator="admin")

    assert parse_route("300502.SZ 技术分析").service_type == ServiceType.TECHNICAL_ANALYSIS
    assert parse_route("利率").service_type == ServiceType.RATE
    assert parse_route("转债").service_type == ServiceType.CONVERTIBLE_BOND
    assert parse_route("hello").matched is False

    success = handle_text_message("ok", "利率")
    assert success.success is True
    assert success.output_files == [str(image)]
    assert "[图片:" in success.reply_text

    denied = handle_text_message("missing", "利率")
    assert denied.success is False
    assert denied.reply_text == "您暂未开通该服务，如需开通请联系服务人员。"

    bypassed = handle_text_message("missing", "利率", skip_permission=True)
    assert bypassed.success is True
    assert bypassed.output_files == [str(image)]

    miss = handle_text_message("ok", "hello")
    assert miss.success is False
    assert miss.handled is True
    assert miss.reply_text == DEFAULT_UNMATCHED_PROMPT
    miss_record = list_request_records(limit=1)[0]
    assert miss_record.service_type == ServiceType.UNMATCHED
    assert miss_record.error_code == ErrorCode.INPUT_ERROR
    assert miss_record.user_prompt == DEFAULT_UNMATCHED_PROMPT


def test_router_can_explicitly_fallback_to_general_agent_for_unmatched_text(investment_env):
    from business.investment.config_service import save_config
    from business.investment.router import DEFAULT_UNMATCHED_PROMPT, handle_text_message

    save_config("router.enable_agent_fallback", True, operator_role="admin")

    miss = handle_text_message("ok", "hello")

    assert miss.success is False
    assert miss.handled is False
    assert miss.reply_text == DEFAULT_UNMATCHED_PROMPT


def test_web_channel_routes_investment_commands_without_permission_check(investment_env, tmp_path):
    from bridge.reply import ReplyType
    from business.investment.constants import ServiceType
    from business.investment.daily_content import create_content_draft, set_content_effective
    from channel.web.web_channel import WebChannel, _build_investment_web_reply

    image = tmp_path / "rate card.png"
    image.write_bytes(b"png")
    content_id = create_content_draft(ServiceType.RATE, source_text="rate")
    set_content_effective(content_id, str(image), operator="admin")

    reply = _build_investment_web_reply("web-session-without-user", "利率")

    assert reply is not None
    assert reply.type == ReplyType.TEXT
    assert "![rate card.png](/api/file?path=" in reply.content
    assert "%20" in reply.content
    assert "[图片:" not in reply.content
    assert _build_investment_web_reply("web-session", "普通聊天") is None
    assert WebChannel().channel_type == "web"
