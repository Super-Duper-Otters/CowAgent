# encoding:utf-8
import base64
from datetime import UTC, datetime, timedelta
from io import BytesIO
from collections import OrderedDict
import json
import os
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace
import sys
from uuid import uuid4
from zipfile import ZipFile

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def _beijing_today() -> str:
    return (datetime.now(UTC) + timedelta(hours=8)).date().isoformat()


def test_business_schema_declares_all_tables():
    from business.schema.tables import metadata

    assert {
        "customers",
        "admins",
        "admin_sessions",
        "request_records",
        "content_records",
        "artifacts",
        "configs",
        "stock_symbols",
        "operation_audits",
        "ai_generation_audits",
        "products",
    }.issubset(metadata.tables)
    assert "internal_call_records" not in metadata.tables

    assert {
        "created_by_admin_id",
        "created_by_username",
        "updated_by_admin_id",
        "updated_by_username",
        "deleted_at",
        "deleted_by_admin_id",
        "deleted_by_username",
        "delete_reason",
    }.issubset(metadata.tables["customers"].columns.keys())
    assert {
        "created_by_admin_id",
        "created_by_username",
        "created_by_role",
        "updated_by_admin_id",
        "updated_by_username",
        "updated_by_role",
        "published_by_admin_id",
        "published_by_username",
        "published_by_role",
        "expires_at",
        "auto_effective_after_generate",
        "input_prompt",
    }.issubset(metadata.tables["content_records"].columns.keys())
    assert {
        "operator_admin_id",
        "operator_username",
        "operator_role",
        "operation_category",
        "result_status",
        "error_code",
        "error_message",
        "elapsed_ms",
        "before_state",
        "after_state",
        "request_ip",
        "user_agent",
    }.issubset(metadata.tables["operation_audits"].columns.keys())
    assert {
        "updated_by_admin_id",
        "updated_by_username",
        "updated_by_role",
    }.issubset(metadata.tables["configs"].columns.keys())
    assert "owner_type" in metadata.tables["artifacts"].columns
    assert "generation_records" not in metadata.tables
    assert {
        "entry_type",
        "action_type",
        "actor_type",
        "actor_id",
        "actor_name",
        "actor_role",
    }.issubset(metadata.tables["request_records"].columns.keys())
    assert {
        "audit_id",
        "entry_type",
        "service",
        "action_type",
        "actor_type",
        "business_record_type",
        "business_record_id",
        "provider",
        "model",
        "input_prompt",
        "result",
    }.issubset({column.name for column in metadata.tables["ai_generation_audits"].columns})
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
    }.issubset({column.name for column in metadata.tables["products"].columns})
    assert {
        "idx_products_source_cache_key",
        "idx_products_source_content_id",
    }.issubset({index.name for index in metadata.tables["products"].indexes})


def test_business_schema_no_longer_defines_cache_entries_table():
    from business.schema.tables import metadata

    assert "products" in metadata.tables
    assert "cache_entries" not in metadata.tables


def test_business_schema_uses_simplified_physical_column_names():
    from business.schema.tables import metadata

    physical_names = {
        table_name: {column.name for column in metadata.tables[table_name].columns}
        for table_name in (
            "request_records",
            "content_records",
            "artifacts",
            "operation_audits",
        )
    }

    assert {"service", "outputs", "error"}.issubset(physical_names["request_records"])
    assert {"service", "sources", "input_text", "output_text", "output_image_path", "error"}.issubset(
        physical_names["content_records"]
    )
    assert {"service"}.issubset(physical_names["artifacts"])
    assert {"category", "result", "error"}.issubset(physical_names["operation_audits"])

    assert {"service_type", "output_files", "error_message"}.isdisjoint(physical_names["request_records"])
    assert {"service_type", "source_files", "source_text", "generated_text", "output_image", "error_message"}.isdisjoint(
        physical_names["content_records"]
    )
    assert {"service_type"}.isdisjoint(physical_names["artifacts"])
    assert {"operation_category", "result_status", "error_message"}.isdisjoint(physical_names["operation_audits"])


def test_business_migration_removes_generation_records_table(business_env):
    from sqlalchemy import inspect
    from business.schema.db import get_engine

    tables = set(inspect(get_engine()).get_table_names())

    assert "generation_records" not in tables
    assert "internal_call_records" not in tables
    assert "ai_generation_audits" in tables


def test_product_backfill_migration_revision_exists():
    path = Path("migrations/business/versions/20260624_0027_backfill_products.py")
    text = path.read_text(encoding="utf-8")
    assert 'revision = "20260624_0027"' in text
    assert 'down_revision = "20260624_0026"' in text
    assert "backfill_products_from_legacy_sources" in text


def test_drop_cache_entries_migration_preserves_legacy_cache_rows(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    from business.schema import db as db
    from business.schema import migrations as migrations

    base_url = os.environ.get("COWAGENT_TEST_POSTGRES_URL") or db.DEFAULT_DATABASE_URL
    schema_name = f"cowagent_cache_drop_{uuid4().hex}"
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
    monkeypatch.setenv("COWAGENT_BUSINESS_STORAGE_ROOT", str(tmp_path / "storage"))
    db.reset_engine_for_tests()
    try:
        migrations.upgrade("20260624_0026")
        engine = db.get_engine()
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into cache_entries (
                        cache_key, service, normalized_target, market_date,
                        version_fingerprint, outputs, artifact_owner_id,
                        status, hit_count, created_at, updated_at
                    ) values (
                        'legacy-cache-before-drop', 'technical_analysis', '300502.SZ', '2026-06-25',
                        'legacy-v1', '["/tmp/legacy-cache.png"]', 'legacy-request',
                        'active', 7, '2026-06-25T01:00:00+00:00', '2026-06-25T02:00:00+00:00'
                    )
                    """
                )
            )

        migrations.upgrade("head")

        inspector = inspect(engine)
        assert not inspector.has_table("cache_entries")
        with engine.begin() as conn:
            product = conn.execute(
                text("select * from products where source_cache_key = 'legacy-cache-before-drop'")
            ).mappings().one()
        assert product["business_type"] == "technical_analysis"
        assert product["target_key"] == "300502.SZ"
        assert product["business_date"] == "2026-06-25"
        assert product["version_fingerprint"] == "legacy-v1"
        assert product["output_files"] == '["/tmp/legacy-cache.png"]'
        assert product["source_request_id"] == "legacy-request"
        assert product["hit_count"] == 7

        config = Config(str(migrations.alembic_config_path()))
        config.set_main_option("sqlalchemy.url", schema_url.replace("%", "%%"))
        command.downgrade(config, "20260624_0027")

        inspector = inspect(engine)
        assert inspector.has_table("cache_entries")
        with engine.begin() as conn:
            cache = conn.execute(
                text("select * from cache_entries where cache_key = 'legacy-cache-before-drop'")
            ).mappings().one()
        assert cache["service"] == "technical_analysis"
        assert cache["normalized_target"] == "300502.SZ"
        assert cache["market_date"] == "2026-06-25"
        assert cache["version_fingerprint"] == "legacy-v1"
        assert cache["outputs"] == '["/tmp/legacy-cache.png"]'
        assert cache["artifact_owner_id"] == "legacy-request"
        assert cache["status"] == "active"
        assert cache["hit_count"] == 7
    finally:
        db.reset_engine_for_tests()
        with admin_engine.begin() as conn:
            conn.execute(text(f'drop schema if exists "{schema_name}" cascade'))
        admin_engine.dispose()


def test_business_migration_transfers_generation_records_to_new_tables(tmp_path, monkeypatch):
    from sqlalchemy import inspect
    from business.schema import db as db
    from business.schema import migrations as migrations
    base_url = os.environ.get("COWAGENT_TEST_POSTGRES_URL") or db.DEFAULT_DATABASE_URL
    schema_name = f"cowagent_migration_{uuid4().hex}"
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
    monkeypatch.setenv("COWAGENT_BUSINESS_STORAGE_ROOT", str(tmp_path / "storage"))
    db.reset_engine_for_tests()
    try:
        migrations.upgrade("20260609_0018")
        engine = db.get_engine()
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    create table generation_records (
                        generation_id text primary key,
                        content_id text not null,
                        service text not null,
                        operator_id integer,
                        operator_name text,
                        operator_role text,
                        input_text text,
                        sources text not null,
                        result text not null,
                        error_code text,
                        error text,
                        output_text text,
                        outputs text not null,
                        elapsed_ms integer,
                        created_at text not null,
                        updated_at text not null
                    )
                    """
                )
            )
            conn.execute(text("create index idx_generation_records_content_created on generation_records (content_id, created_at)"))
            conn.execute(text("create index idx_generation_records_service_created on generation_records (service, created_at)"))
            conn.execute(text("create index idx_generation_records_operator_created on generation_records (operator_name, created_at)"))
            conn.execute(
                text(
                    """
                    insert into generation_records (
                        generation_id, content_id, service, operator_id, operator_name, operator_role,
                        input_text, sources, result, error_code, error, output_text, outputs,
                        elapsed_ms, created_at, updated_at
                    ) values (
                        'legacy-generation-1', 'legacy-content-1', 'rate', 7, 'ops', 'content_operator',
                        'legacy input', '["/tmp/source.png"]', 'success', '', '', 'legacy output',
                        '["/tmp/output.png"]', 33, '2026-06-10T00:00:00+00:00', '2026-06-10T00:00:01+00:00'
                    )
                    """
                )
            )

        migrations.upgrade("head")

        inspector = inspect(engine)
        assert "generation_records" not in set(inspector.get_table_names())
        assert "internal_call_records" not in set(inspector.get_table_names())
        with engine.begin() as conn:
            request = conn.execute(text("select * from request_records where request_id = 'legacy-generation-1'")).mappings().one()
            audit = conn.execute(text("select * from ai_generation_audits where business_record_id = 'legacy-generation-1'")).mappings().one()
        assert request["entry_type"] == "internal_call"
        assert request["service"] == "rate"
        assert request["action_type"] == "generate"
        assert request["actor_name"] == "ops"
        assert request["status"] == "success"
        assert request["outputs"] == '["/tmp/output.png"]'
        assert audit["business_record_type"] == "request"
        assert audit["business_record_id"] == "legacy-generation-1"
        assert audit["result"] == "success"
        assert audit["output_text"] == "legacy output"
    finally:
        db.reset_engine_for_tests()
        with admin_engine.begin() as conn:
            conn.execute(text(f'drop schema if exists "{schema_name}" cascade'))


def test_business_auth_service_hashes_passwords_and_checks_role_permissions(business_env):
    from business.accounts.auth_service import (
        authenticate_admin,
        create_admin_session,
        create_admin_user,
        get_admin_session,
        hash_password,
        require_permission,
        verify_password,
    )

    password_hash = hash_password("secret-pass")

    assert password_hash.startswith("pbkdf2_sha256$")
    assert "secret-pass" not in password_hash
    assert verify_password("secret-pass", password_hash) is True
    assert verify_password("wrong-pass", password_hash) is False

    user_id = create_admin_user("operator-a", "secret-pass", role="content_operator")
    assert authenticate_admin("operator-a", "wrong-pass") is None
    admin = authenticate_admin("operator-a", "secret-pass")
    assert admin is not None
    assert admin.id == user_id
    assert admin.role == "content_operator"

    token = create_admin_session(admin)
    session = get_admin_session(token)
    assert session is not None
    assert session.username == "operator-a"
    assert session.role == "content_operator"
    assert require_permission(session, "content.upload").allowed is True
    assert require_permission(session, "content.publish").allowed is True
    assert require_permission(session, "content.write").allowed is True
    assert require_permission(session, "content.effective").allowed is True
    assert require_permission(session, "customers.write").allowed is False
    assert require_permission(session, "admin_users.write").allowed is False
    assert require_permission(session, "audits.read").allowed is False
    assert require_permission(session, "config.write").allowed is False

    with pytest.raises(ValueError, match="unsupported admin role"):
        create_admin_user("legacy-poster-a", "poster-pass", role="poster")
    with pytest.raises(ValueError, match="unsupported admin role"):
        create_admin_user("legacy-tech-a", "tech-pass", role="technical_admin")


def test_technical_operator_only_has_config_permissions(business_env):
    from business.accounts.auth_service import authenticate_admin, create_admin_user, require_permission

    create_admin_user("tech-ops-a", "tech-pass", role="technical_operator")

    admin = authenticate_admin("tech-ops-a", "tech-pass")
    assert admin is not None
    assert admin.role == "technical_operator"
    assert require_permission(admin, "config.read").allowed is True
    assert require_permission(admin, "config.write").allowed is True
    assert require_permission(admin, "customers.read").allowed is False
    assert require_permission(admin, "admin_users.read").allowed is False
    assert require_permission(admin, "content.read").allowed is False
    assert require_permission(admin, "skills.read").allowed is False
    assert require_permission(admin, "stocks.read").allowed is False
    assert require_permission(admin, "health.read").allowed is False


def test_business_migrations_seed_default_admin_and_posters(business_env):
    from business.accounts.auth_service import authenticate_admin

    admin = authenticate_admin("admin", "password")
    assert admin is not None
    assert admin.role == "admin"

    for username in ("poster1", "poster2", "poster3"):
        poster = authenticate_admin(username, "password")
        assert poster is not None
        assert poster.role == "content_operator"


def test_admin_user_service_lists_updates_and_resets_password(business_env):
    from business.accounts.auth_service import (
        authenticate_admin,
        create_admin_user,
        list_admin_users,
        reset_admin_password,
        update_admin_user,
    )

    create_admin_user("ops-a", "old-pass", role="content_operator")

    users = {user.username: user for user in list_admin_users()}
    assert users["ops-a"].role == "content_operator"
    assert users["ops-a"].enabled is True
    assert "password_hash" not in users["ops-a"].__dict__

    update_admin_user("ops-a", role="admin", enabled=False)
    assert authenticate_admin("ops-a", "old-pass") is None
    disabled = {user.username: user for user in list_admin_users()}["ops-a"]
    assert disabled.role == "admin"
    assert disabled.enabled is False

    update_admin_user("ops-a", enabled=True)
    reset_admin_password("ops-a", "new-pass")
    assert authenticate_admin("ops-a", "old-pass") is None
    reset_user = authenticate_admin("ops-a", "new-pass")
    assert reset_user is not None
    assert reset_user.role == "admin"

    with pytest.raises(ValueError, match="not found"):
        update_admin_user("missing-admin", enabled=False)
    with pytest.raises(ValueError, match="not found"):
        reset_admin_password("missing-admin", "new-pass")

    from business.schema.db import connect
    from business.schema.tables import admins

    update_admin_user("ops-a", role="content_operator")
    create_admin_user("solo-admin", "admin-pass", role="admin")
    with connect() as conn:
        conn.execute(
            admins.update()
            .where(admins.c.username != "solo-admin")
            .values(enabled=0)
        )
    with pytest.raises(ValueError, match="last enabled admin"):
        update_admin_user("solo-admin", role="content_operator")
    with pytest.raises(ValueError, match="last enabled admin"):
        update_admin_user("solo-admin", enabled=False)


def test_web_business_api_enforces_admin_roles(business_env, monkeypatch):
    from business.audit.audit_service import list_operation_audits
    from business.accounts.auth_service import authenticate_admin, create_admin_session, create_admin_user
    from business.records.records import get_content_record
    from channel.web import web_channel
    from channel.web.web_channel import (
        InvestmentAdminUserPasswordHandler,
        InvestmentAdminUserStatusHandler,
        InvestmentAdminUsersHandler,
        InvestmentConfigHandler,
        InvestmentDailyContentHandler,
        InvestmentHealthHandler,
        InvestmentUsersHandler,
    )

    create_admin_user("admin-a", "admin-pass", role="admin")
    create_admin_user("operator-a", "operator-pass", role="content_operator")
    create_admin_user("tech-a", "tech-pass", role="technical_operator")
    admin_token = create_admin_session(authenticate_admin("admin-a", "admin-pass"))
    operator_token = create_admin_session(authenticate_admin("operator-a", "operator-pass"))
    tech_token = create_admin_session(authenticate_admin("tech-a", "tech-pass"))

    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(web_channel.web, "input", lambda **kwargs: SimpleNamespace(openid="", enabled=""))

    def use_token(token):
        monkeypatch.setattr(web_channel.web, "cookies", lambda: {"cow_investment_session": token})

    monkeypatch.setattr(
        web_channel.web,
        "data",
        lambda: json.dumps({
            "openid": "openid-a",
            "name": "Alice",
            "allowed_services": ["全部"],
            "auth_start_at": "2026-01-01T00:00:00",
            "auth_end_at": "2099-12-31T23:59:59",
        }).encode("utf-8"),
    )
    use_token(operator_token)
    monkeypatch.setattr(web_channel.web.ctx, "headers", [], raising=False)
    with pytest.raises(web_channel.web.HTTPError) as denied_error:
        InvestmentUsersHandler().POST()
    denied = json.loads(denied_error.value.data)
    assert denied["status"] == "error"
    assert denied["code"] == "permission_denied"

    use_token(admin_token)
    created = json.loads(InvestmentUsersHandler().POST())
    assert created["status"] == "success"
    assert created["action"] == "created"

    use_token(tech_token)
    monkeypatch.setattr(
        web_channel.web,
        "data",
        lambda: json.dumps({"configs": {"router.enable_agent_fallback": True}}).encode("utf-8"),
    )
    config = json.loads(InvestmentConfigHandler().POST())
    assert config["status"] == "success"
    with pytest.raises(web_channel.web.HTTPError) as tech_health_error:
        InvestmentHealthHandler().GET()
    tech_health_denied = json.loads(tech_health_error.value.data)
    assert tech_health_denied["status"] == "error"
    assert tech_health_denied["permission"] == "health.read"

    use_token(operator_token)
    with pytest.raises(web_channel.web.HTTPError) as poster_config_error:
        InvestmentConfigHandler().GET()
    poster_denied = json.loads(poster_config_error.value.data)
    assert poster_denied["status"] == "error"
    assert poster_denied["code"] == "permission_denied"
    assert poster_denied["permission"] == "config.read"

    with pytest.raises(web_channel.web.HTTPError) as poster_admin_error:
        InvestmentAdminUsersHandler().GET()
    poster_admin_denied = json.loads(poster_admin_error.value.data)
    assert poster_admin_denied["status"] == "error"
    assert poster_admin_denied["code"] == "permission_denied"

    monkeypatch.setattr(
        web_channel.web,
        "data",
        lambda: json.dumps({"service_type": "利率", "source_text": "rate source", "operator": "forged-admin"}).encode("utf-8"),
    )
    content = json.loads(InvestmentDailyContentHandler().POST())
    assert content["status"] == "success"
    assert get_content_record(content["content_id"]).operator == "operator-a"

    use_token(admin_token)
    monkeypatch.setattr(web_channel.web, "input", lambda **kwargs: SimpleNamespace())
    admin_users = json.loads(InvestmentAdminUsersHandler().GET())
    assert admin_users["status"] == "success"
    assert any(item["username"] == "admin-a" and item["role"] == "admin" for item in admin_users["users"])
    assert all("password" not in item for item in admin_users["users"])

    monkeypatch.setattr(
        web_channel.web,
        "data",
        lambda: json.dumps({"username": "ops-web", "password": "ops-pass", "role": "technical_operator"}).encode("utf-8"),
    )
    created_admin = json.loads(InvestmentAdminUsersHandler().POST())
    assert created_admin["status"] == "success"
    assert created_admin["action"] == "created"
    assert authenticate_admin("ops-web", "ops-pass").role == "technical_operator"

    monkeypatch.setattr(
        web_channel.web,
        "data",
        lambda: json.dumps({"username": "ops-web", "role": "admin"}).encode("utf-8"),
    )
    updated_admin = json.loads(InvestmentAdminUsersHandler().POST())
    assert updated_admin["status"] == "success"
    assert updated_admin["action"] == "updated"
    assert authenticate_admin("ops-web", "ops-pass").role == "admin"

    missing_admin = json.loads(InvestmentAdminUserStatusHandler().POST("missing-web", "disable"))
    assert missing_admin["status"] == "error"

    disabled_admin = json.loads(InvestmentAdminUserStatusHandler().POST("ops-web", "disable"))
    assert disabled_admin["status"] == "success"
    assert authenticate_admin("ops-web", "ops-pass") is None

    enabled_admin = json.loads(InvestmentAdminUserStatusHandler().POST("ops-web", "enable"))
    assert enabled_admin["status"] == "success"
    monkeypatch.setattr(
        web_channel.web,
        "data",
        lambda: json.dumps({"password": "reset-pass"}).encode("utf-8"),
    )
    reset_admin = json.loads(InvestmentAdminUserPasswordHandler().POST("ops-web"))
    assert reset_admin["status"] == "success"
    assert authenticate_admin("ops-web", "reset-pass").role == "admin"

    audits = list_operation_audits(limit=20, target_type="admin_user", target_id="ops-web")
    actions = [audit.action for audit in audits]
    assert "admin_user.create" in actions
    assert "admin_user.update" in actions
    assert "admin_user.disable" in actions
    assert "admin_user.reset_password" in actions


def test_business_auth_me_allows_content_operator_without_customer_or_audit_permission(business_env, monkeypatch):
    from business.accounts.auth_service import authenticate_admin, create_admin_session, create_admin_user
    from channel.web import web_channel
    from channel.web.web_channel import InvestmentAuthMeHandler

    create_admin_user("operator-a", "operator-pass", role="content_operator")
    token = create_admin_session(authenticate_admin("operator-a", "operator-pass"))

    monkeypatch.setattr(web_channel.web, "cookies", lambda: {"cow_investment_session": token})
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)

    payload = json.loads(InvestmentAuthMeHandler().GET())

    assert payload["status"] == "success"
    assert payload["admin"]["role"] == "content_operator"
    assert "content.upload" in payload["admin"]["permissions"]
    assert "content.publish" in payload["admin"]["permissions"]
    assert "content.write" in payload["admin"]["permissions"]
    assert "customers.write" not in payload["admin"]["permissions"]
    assert "audits.read" not in payload["admin"]["permissions"]


def test_web_business_auth_falls_back_to_web_password_until_admin_exists(business_env, monkeypatch):
    from business.schema.db import connect
    from business.schema.tables import admin_sessions, admins
    from business.accounts.auth_service import create_admin_user
    from channel.web import web_channel

    with connect() as conn:
        conn.execute(admin_sessions.delete())
        conn.execute(admins.delete())

    monkeypatch.setattr(web_channel, "_check_auth", lambda: True)
    monkeypatch.setattr(web_channel.web, "cookies", lambda: {})

    fallback = web_channel._require_investment_permission("customers.write")
    assert fallback.role == "admin"
    assert fallback.bootstrap is True

    create_admin_user("admin-a", "admin-pass", role="admin")
    denied = web_channel._investment_permission_error("customers.write")
    assert denied["status"] == "error"
    assert denied["code"] == "unauthorized"


def test_admin_login_with_web_password_enabled_also_authenticates_console(business_env, monkeypatch):
    from business.accounts.auth_service import create_admin_user
    from channel.web import web_channel
    from channel.web.web_channel import AuthCheckHandler, AuthLoginHandler

    create_admin_user("admin-a", "admin-pass", role="admin")
    cookies = {}
    headers = []

    monkeypatch.setattr(web_channel, "conf", lambda: {"web_password": "legacy-pass", "web_session_expire_days": 30})
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: headers.append(args))
    monkeypatch.setattr(
        web_channel.web,
        "setcookie",
        lambda name, value, **_kwargs: cookies.__setitem__(name, value),
    )
    monkeypatch.setattr(
        web_channel.web,
        "data",
        lambda: json.dumps({"username": "admin-a", "password": "admin-pass"}).encode("utf-8"),
    )

    login_payload = json.loads(AuthLoginHandler().POST())

    assert login_payload["status"] == "success"
    assert cookies["cow_investment_session"]
    assert cookies["cow_auth_token"]

    monkeypatch.setattr(web_channel.web, "cookies", lambda: cookies)
    check_payload = json.loads(AuthCheckHandler().GET())

    assert check_payload["status"] == "success"
    assert check_payload["authenticated"] is True
    web_channel._require_auth()


def test_chat_page_redirects_to_login_when_console_session_missing(monkeypatch):
    from channel.web import web_channel
    from channel.web.web_channel import ChatHandler

    redirects = []

    def fake_seeother(target):
        redirects.append(target)
        raise RuntimeError(target)

    monkeypatch.setattr(web_channel, "_check_console_auth", lambda: False)
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(web_channel.web, "seeother", fake_seeother)
    monkeypatch.setattr(web_channel.web.ctx, "fullpath", "/chat?view=invest-records", raising=False)

    with pytest.raises(RuntimeError):
        ChatHandler().GET()

    assert redirects == ["/login?next=%2Fchat%3Fview%3Dinvest-records"]


def test_web_message_api_requires_console_admin_login(monkeypatch):
    from channel.web import web_channel
    from channel.web.web_channel import MessageHandler

    class FakeWebChannel:
        def post_message(self):
            return "unexpected"

    monkeypatch.setattr(web_channel, "_check_console_auth", lambda: False)
    monkeypatch.setattr(web_channel, "_require_auth", lambda: None)
    monkeypatch.setattr(web_channel, "WebChannel", lambda: FakeWebChannel())
    monkeypatch.setattr(web_channel.web.ctx, "headers", [], raising=False)

    with pytest.raises(web_channel.web.HTTPError) as exc_info:
        MessageHandler().POST()

    payload = json.loads(exc_info.value.data)
    assert payload["status"] == "error"
    assert payload["message"] == "Unauthorized"


def test_login_page_redirects_authenticated_user_to_next_path(monkeypatch):
    from channel.web import web_channel
    from channel.web.web_channel import LoginPageHandler

    redirects = []

    def fake_seeother(target):
        redirects.append(target)
        raise RuntimeError(target)

    monkeypatch.setattr(web_channel, "_check_console_auth", lambda: True)
    monkeypatch.setattr(web_channel.web, "input", lambda **kwargs: SimpleNamespace(next="/chat"))
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(web_channel.web, "seeother", fake_seeother)

    with pytest.raises(RuntimeError):
        LoginPageHandler().GET()

    assert redirects == ["/chat"]


def test_content_operator_session_denies_records_and_cache(business_env, monkeypatch):
    from business.accounts.auth_service import authenticate_admin, create_admin_session, create_admin_user
    from channel.web import web_channel
    from channel.web.web_channel import InvestmentCacheHandler, InvestmentRequestRecordsHandler

    create_admin_user("operator-a", "operator-pass", role="content_operator")
    token = create_admin_session(authenticate_admin("operator-a", "operator-pass"))

    monkeypatch.setattr(web_channel.web, "cookies", lambda: {"cow_investment_session": token})
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(web_channel.web, "input", lambda **_defaults: SimpleNamespace(limit="20"))
    monkeypatch.setattr(web_channel.web.ctx, "headers", [], raising=False)

    with pytest.raises(web_channel.web.HTTPError) as records_denied_error:
        InvestmentRequestRecordsHandler().GET()
    records_denied = json.loads(records_denied_error.value.data)
    assert records_denied["status"] == "error"
    assert records_denied["code"] == "permission_denied"
    assert records_denied["permission"] == "records.read"

    with pytest.raises(web_channel.web.HTTPError) as denied_error:
        InvestmentCacheHandler().GET()
    denied = json.loads(denied_error.value.data)
    assert denied["status"] == "error"
    assert denied["code"] == "permission_denied"
    assert denied["permission"] == "cache.read"


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



def test_business_database_url_defaults_to_docker_postgres(monkeypatch):
    from business.schema import db as db
    monkeypatch.delenv("COWAGENT_INVESTMENT_DATABASE_URL", raising=False)
    url = db.get_database_url()

    assert url == "postgresql+psycopg://cowagent:cowagent@127.0.0.1:55400/cowagent_investment"


def test_business_database_url_prefers_postgres_env(business_env, monkeypatch):
    from business.schema import db as db
    monkeypatch.setenv("COWAGENT_INVESTMENT_DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/cowagent")

    assert db.get_database_url() == "postgresql+psycopg://u:p@localhost:5432/cowagent"


def test_business_database_url_rejects_sqlite_env(monkeypatch):
    from business.schema import db as db
    monkeypatch.setenv("COWAGENT_INVESTMENT_DATABASE_URL", "sqlite:///tmp/investment.db")

    with pytest.raises(ValueError, match="PostgreSQL"):
        db.get_database_url()


def test_business_database_url_rejects_sqlite_config(monkeypatch):
    import config

    from business.schema import db as db
    monkeypatch.delenv("COWAGENT_INVESTMENT_DATABASE_URL", raising=False)
    monkeypatch.setattr(config, "conf", lambda: {"investment_database_url": "sqlite:///tmp/investment.db"})

    with pytest.raises(ValueError, match="PostgreSQL"):
        db.get_database_url()


def test_storage_initializes_schema_with_alembic_upgrade(tmp_path, monkeypatch):
    from business.schema import migrations as migrations
    from business.schema import tables as schema
    from business.schema import storage as storage
    monkeypatch.setenv("COWAGENT_BUSINESS_STORAGE_ROOT", str(tmp_path / "storage"))
    calls = []

    monkeypatch.setattr(migrations, "upgrade", lambda revision="head": calls.append(revision))
    monkeypatch.setattr(schema.metadata, "create_all", lambda bind: pytest.fail("initialize_storage must use Alembic"))

    storage.initialize_storage()

    assert calls == ["head"]
    assert (tmp_path / "storage" / "files").is_dir()
    assert (tmp_path / "storage" / "tmp").is_dir()


def test_business_migration_smoke_creates_schema(business_env):
    from business.schema import storage as storage
    from business.schema.db import get_engine
    from sqlalchemy import inspect
    from sqlalchemy import text

    storage.initialize_storage()
    engine = get_engine()
    inspector = inspect(engine)

    assert inspector.has_table("customers")
    assert inspector.has_table("stock_symbols")
    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            legacy_names = conn.execute(
                text(
                    """
                    select conname as name
                    from pg_constraint
                    where connamespace = current_schema()::regnamespace
                      and conname like 'investment_%'
                    union all
                    select relname as name
                    from pg_class
                    where relnamespace = current_schema()::regnamespace
                      and relkind in ('i', 'I')
                      and (relname like 'investment_%' or relname like 'idx_investment_%')
                    """
                )
            ).scalars().all()
        assert legacy_names == []


def test_request_events_record_customer_request_lifecycle(business_env):
    from business.config.constants import ServiceType
    from business.audit.event_service import list_request_events, record_request_event
    from business.records.records import create_request_record

    request_id = create_request_record("openid-events", "新易盛 技术分析", ServiceType.TECHNICAL_ANALYSIS)

    event_id = record_request_event(
        request_id=request_id,
        openid="openid-events",
        channel="wechatmp",
        event_type="reply_image_sent",
        message_type="image",
        content="技术分析主图",
        media_id="media-1",
        file_path="/tmp/card.png",
        source_type="request",
        source_id=request_id,
        result="success",
        error="",
    )

    events = list_request_events(request_id=request_id, event_type="reply_image_sent")

    assert event_id
    assert len(events) == 1
    assert events[0].request_id == request_id
    assert events[0].openid == "openid-events"
    assert events[0].channel == "wechatmp"
    assert events[0].event_type == "reply_image_sent"
    assert events[0].message_type == "image"
    assert events[0].content == "技术分析主图"
    assert events[0].media_id == "media-1"
    assert events[0].file_path == "/tmp/card.png"
    assert events[0].source_type == "request"
    assert events[0].source_id == request_id
    assert events[0].result == "success"
    assert events[0].error == ""
    assert events[0].created_at


def test_request_records_emit_lifecycle_events(business_env):
    from business.config.constants import ErrorCode, ServiceType
    from business.audit.event_service import list_request_events
    from business.records.records import (
        create_request_record,
        fail_request_record,
        mark_request_delivered,
        succeed_request_record,
    )

    success_id = create_request_record("openid-life", "利率", ServiceType.RATE)
    succeed_request_record(success_id, output_files=[], elapsed_ms=12)
    mark_request_delivered(success_id)

    failed_id = create_request_record("openid-life", "转债", ServiceType.CONVERTIBLE_BOND)
    fail_request_record(failed_id, ErrorCode.NO_CONTENT, detail="no content", elapsed_ms=3)

    success_events = list_request_events(request_id=success_id)
    failed_events = list_request_events(request_id=failed_id)

    assert [event.event_type for event in success_events] == [
        "request_received",
        "generation_success",
        "delivery_success",
    ]
    assert all(event.openid == "openid-life" for event in success_events)
    assert success_events[0].channel == "business"
    assert success_events[0].content == "利率"
    assert success_events[1].result == "success"
    assert success_events[2].result == "success"
    assert [event.event_type for event in failed_events] == ["request_received", "generation_failed"]
    assert failed_events[1].result == "failed"
    assert failed_events[1].error == "no content"


def test_fail_request_record_preserves_artifact_index_rows(business_env, tmp_path):
    from business.config.constants import ErrorCode, ServiceType
    from business.records.records import (
        create_request_record,
        fail_request_record,
        list_output_files,
        record_output_file,
    )

    request_id = create_request_record("openid-artifact-fail", "新易盛 技术分析", ServiceType.TECHNICAL_ANALYSIS)
    output_file = tmp_path / "signal-card.png"
    output_file.write_bytes(b"png")
    record_output_file(
        request_id,
        str(output_file),
        "image",
        ServiceType.TECHNICAL_ANALYSIS,
        artifact_role="signal_card",
    )

    fail_request_record(request_id, ErrorCode.SYSTEM_ERROR, detail="late failure", elapsed_ms=9)

    artifacts = list_output_files(request_id)
    assert len(artifacts) == 1
    assert artifacts[0]["file_path"] == str(output_file)


def test_external_request_record_declares_entry_and_actor(business_env):
    from business.config.constants import ActionType, ActorType, EntryType, ServiceType
    from business.records.records import create_request_record, get_request_record

    request_id = create_request_record("openid-entry", "利率", ServiceType.RATE)

    record = get_request_record(request_id)

    assert record.entry_type == EntryType.EXTERNAL_REQUEST
    assert record.action_type == ActionType.DELIVER_EFFECTIVE_CONTENT
    assert record.actor_type == ActorType.CUSTOMER
    assert record.actor_id == "openid-entry"
    assert record.actor_name == ""
    assert record.actor_role == ""


def test_internal_call_entries_are_separate_from_external_requests(business_env):
    from business.config.constants import ActionType, ActorType, EntryType, ServiceType, Status
    from business.records.records import create_business_workflow_record, finish_business_workflow_record, get_request_record, list_request_records

    request_id = create_business_workflow_record(
        entry_type=EntryType.INTERNAL_CALL,
        service_type=ServiceType.RATE,
        action_type=ActionType.GENERATE,
        actor_type=ActorType.ADMIN,
        actor_id="7",
        actor_name="ops",
        actor_role="content_operator",
        raw_input="rate input",
    )
    finish_business_workflow_record(request_id, status=Status.SUCCESS, output_files=["/tmp/rate-card.png"], elapsed_ms=31)

    record = get_request_record(request_id)

    assert list_request_records(entry_type=EntryType.EXTERNAL_REQUEST, limit=10) == []
    assert [item.request_id for item in list_request_records(entry_type=EntryType.INTERNAL_CALL, limit=10)] == [request_id]
    assert record.request_id == request_id
    assert record.entry_type == EntryType.INTERNAL_CALL
    assert record.service_type == ServiceType.RATE
    assert record.action_type == ActionType.GENERATE
    assert record.actor_type == ActorType.ADMIN
    assert record.actor_id == "7"
    assert record.actor_name == "ops"
    assert record.actor_role == "content_operator"
    assert record.status == Status.SUCCESS
    assert record.raw_input == "rate input"
    assert record.output_files == ["/tmp/rate-card.png"]
    assert record.elapsed_ms == 31


def test_ai_generation_audit_records_common_generation_metadata(business_env):
    from business.audit.ai_generation_audit import (
        finish_ai_generation_audit,
        get_ai_generation_audit,
        start_ai_generation_audit,
    )
    from business.config.constants import ActionType, ActorType, EntryType, ServiceType

    audit_id = start_ai_generation_audit(
        entry_type=EntryType.INTERNAL_CALL,
        service_type=ServiceType.RATE,
        action_type=ActionType.GENERATE,
        actor_type=ActorType.ADMIN,
        actor_id="8",
        actor_name="ops-ai",
        actor_role="content_operator",
        business_record_type="internal_call",
        business_record_id="call-1",
        input_text="rate source",
        sources=["/tmp/source.png"],
        provider="test-provider",
        model="test-model",
    )
    finish_ai_generation_audit(
        audit_id,
        result="success",
        output_text="standard text",
        outputs=["/tmp/card.png"],
        elapsed_ms=45,
    )

    record = get_ai_generation_audit(audit_id)

    assert record is not None
    assert record.entry_type == EntryType.INTERNAL_CALL
    assert record.service_type == ServiceType.RATE
    assert record.action_type == ActionType.GENERATE
    assert record.actor_type == ActorType.ADMIN
    assert record.actor_id == "8"
    assert record.actor_name == "ops-ai"
    assert record.actor_role == "content_operator"
    assert record.business_record_type == "internal_call"
    assert record.business_record_id == "call-1"
    assert record.input_text == "rate source"
    assert record.sources == ["/tmp/source.png"]
    assert record.provider == "test-provider"
    assert record.model == "test-model"
    assert record.result == "success"
    assert record.output_text == "standard text"
    assert record.outputs == ["/tmp/card.png"]
    assert record.elapsed_ms == 45


def test_operation_audit_infers_final_record_categories(business_env):
    from business.audit.audit_service import list_operation_audits, record_operation_audit

    cases = [
        ("customer.update", "customer", "customer"),
        ("admin.create", "admin", "admin"),
        ("skill.update", "skill", "skill"),
        ("content.generate", "daily_content", "content"),
        ("generation.run", "generation", "generation"),
        ("config.update", "config", "config"),
        ("cache.clear", "cache", "cache"),
        ("stock.refresh", "stock", "stock"),
        ("export.request_records", "export", "export"),
        ("health.check", "health", "health"),
        ("system.cleanup", "system", "system"),
    ]

    for action, target_type, _expected in cases:
        record_operation_audit(action, target_type, action)

    audits = list_operation_audits(limit=20)
    by_action = {audit.action: audit.operation_category for audit in audits}

    for action, _target_type, expected in cases:
        assert by_action[action] == expected


def test_daily_content_generation_records_backend_entry_in_business_records(business_env, tmp_path):
    from sqlalchemy import text

    from business.config.constants import ActionType, ActorType, EntryType, ServiceType
    from business.content.daily_content import create_rate_content_draft, generate_content
    from business.audit.ai_generation_audit import list_ai_generation_audits_for_business
    from business.schema.db import connect
    from business.records.records import get_content_record, list_request_records_page

    content_id = create_rate_content_draft(source_text="rate input", source_files=["/tmp/source.png"])
    actor = SimpleNamespace(id=8, username="ops-generate", role="content_operator")
    output_image = tmp_path / "rate-card.png"

    def fake_ai(service_type, source_text, source_files=None):
        assert service_type == ServiceType.RATE
        assert source_text == "rate input"
        assert source_files == ["/tmp/source.png"]
        return SimpleNamespace(success=True, text="rate output", prompt="rate input prompt v2")

    def fake_renderer(service_type, generated_text):
        assert service_type == ServiceType.RATE
        assert generated_text == "rate output"
        output_image.write_bytes(b"rate")
        return SimpleNamespace(success=True, image_path=str(output_image))

    result = generate_content(content_id, ai_generator=fake_ai, renderer=fake_renderer, actor=actor)
    records, total = list_request_records_page(
        service_type=ServiceType.RATE,
        entry_type=EntryType.INTERNAL_CALL,
    )
    content = get_content_record(content_id)

    assert result.success is True
    assert result.input_prompt == "rate input prompt v2"
    assert content.input_prompt == "rate input prompt v2"
    assert total == 1
    record = records[0]
    ai_audits = list_ai_generation_audits_for_business("request", record.request_id)
    assert record.entry_type == EntryType.INTERNAL_CALL
    assert record.action_type == ActionType.GENERATE
    assert record.actor_type == ActorType.ADMIN
    assert record.actor_id == "8"
    assert record.actor_name == "ops-generate"
    assert record.actor_role == "content_operator"
    assert record.service_type == ServiceType.RATE
    assert record.status.value == "success"
    assert record.raw_input == "rate input"
    assert record.output_files == result.output_files
    assert record.elapsed_ms is not None
    assert len(ai_audits) == 1
    assert ai_audits[0].business_record_type == "request"
    assert ai_audits[0].business_record_id == record.request_id
    assert ai_audits[0].actor_name == "ops-generate"
    assert ai_audits[0].input_text == "rate input"
    assert ai_audits[0].input_prompt == "rate input prompt v2"
    assert ai_audits[0].output_text == "rate output"


def test_request_records_api_includes_request_event_timeline(business_env, monkeypatch):
    from business.config.constants import ServiceType
    from business.audit.event_service import record_request_event
    from business.records.records import create_request_record
    from channel.web.web_channel import InvestmentRequestRecordsHandler

    request_id = create_request_record("openid-events-api", "利率", ServiceType.RATE)
    record_request_event(
        request_id=request_id,
        openid="openid-events-api",
        channel="wechat",
        event_type="customer_confirm",
        message_type="text",
        content="1",
        result="accepted",
    )

    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentRequestRecordsHandler().GET,
        params={"keyword": "openid-events-api", "page": "1", "page_size": "20"},
    )

    assert payload["status"] == "success"
    assert [record["request_id"] for record in payload["records"]] == [request_id]
    event_types = [event["event_type"] for event in payload["records"][0]["events"]]
    assert event_types == ["request_received", "customer_confirm"]
    assert payload["records"][0]["events"][1]["content"] == "1"


def test_business_records_api_filters_internal_entry_type(business_env, monkeypatch):
    from business.config.constants import ActionType, ActorType, EntryType, ServiceType, Status
    from business.records.records import create_business_workflow_record, finish_business_workflow_record
    from channel.web.web_channel import (
        InvestmentContentRecordsHandler,
        InvestmentRequestRecordsHandler,
    )

    request_id = create_business_workflow_record(
        entry_type=EntryType.INTERNAL_CALL,
        service_type=ServiceType.RATE,
        action_type=ActionType.GENERATE,
        actor_type=ActorType.ADMIN,
        actor_id="9",
        actor_name="ops-api",
        actor_role="admin",
        raw_input="rate input",
    )
    finish_business_workflow_record(
        request_id,
        status=Status.SUCCESS,
        output_files=["/tmp/rate-output.png"],
        error_message="rate output",
        elapsed_ms=88,
    )

    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentRequestRecordsHandler().GET,
        params={"service_type": "rate", "entry_type": "internal_call", "page": "1", "page_size": "20"},
    )

    assert payload["status"] == "success"
    assert [record["request_id"] for record in payload["records"]] == [request_id]
    assert payload["records"][0]["entry_type"] == "internal_call"
    assert payload["records"][0]["record_type"] == "business_record"
    assert payload["records"][0]["actor_name"] == "ops-api"
    assert payload["records"][0]["actor_type"] == "admin"
    assert payload["records"][0]["action_type"] == "generate"
    assert payload["records"][0]["status"] == "success"
    assert payload["records"][0]["output_files"] == ["/tmp/rate-output.png"]
    assert payload["pagination"] == {"page": 1, "page_size": 20, "total": 1, "total_pages": 1}

    content_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentContentRecordsHandler().GET,
        params={"service_type": "rate", "page": "1", "page_size": "20"},
    )
    assert content_payload["records"] == []
    assert content_payload["pagination"] == {"page": 1, "page_size": 20, "total": 0, "total_pages": 1}


def test_business_alembic_runner_exposes_upgrade():
    from business.schema import migrations as migrations
    assert callable(migrations.upgrade)
    path = migrations.alembic_config_path()
    assert path.name == "alembic.ini"
    assert path.parent.name == "business"


def test_config_service_uses_business_db_connection_helpers():
    from business.config import config_service as config_service
    assert not hasattr(config_service, "get_connection")


def test_user_service_uses_business_db_connection_helpers():
    from business.accounts import user_service as user_service
    assert not hasattr(user_service, "get_connection")


def test_records_service_uses_business_db_connection_helpers():
    from business.records import records as records
    assert not hasattr(records, "get_connection")


def test_daily_content_service_uses_business_db_connection_helpers():
    from business.content import daily_content as daily_content
    assert not hasattr(daily_content, "get_connection")


def test_stock_resolver_uses_business_db_connection_helpers():
    from business.content import stock_resolver as stock_resolver
    assert not hasattr(stock_resolver, "get_connection")


def test_health_uses_business_db_connection_helpers():
    from business.health import health as health
    assert not hasattr(health, "get_connection")


def test_config_service_direct_call_initializes_storage_schema(business_env):
    from business.schema import db as db
    from business.config.config_service import get_config, save_config
    from sqlalchemy import inspect

    db.reset_engine_for_tests()

    save_config("tushare.token", "direct-token", operator_role="admin")

    assert get_config("tushare.token") == "direct-token"
    assert inspect(db.get_engine()).has_table("configs")


def test_business_config_service_uses_existing_config_storage(business_env):
    from business.config.config_service import get_config, save_config

    save_config("prompt.rate", "business prompt", operator_role="admin")
    assert get_config("prompt.rate") == "business prompt"

    save_config("prompt.convertible_bond", "convertible bond prompt", operator_role="admin")
    assert get_config("prompt.convertible_bond") == "convertible bond prompt"


def test_config_masks_sensitive_values_and_checks_permissions(business_env, monkeypatch):
    from business.config.config_service import (
        can_modify_config,
        get_config,
        mask_sensitive_value,
        save_config,
        safe_log_value,
    )

    monkeypatch.setattr("business.config.config_service.conf", lambda: {"tushare_token": "fallback-token"})

    assert get_config("tushare.token") == "fallback-token"
    save_config("tushare.token", "ts-1234567890abcdef", operator_role="admin")
    assert get_config("tushare.token") == "ts-1234567890abcdef"
    assert mask_sensitive_value("ts-1234567890abcdef") == "ts-1**********cdef"
    assert "ts-1234567890abcdef" not in safe_log_value("tushare.token", "ts-1234567890abcdef")
    assert mask_sensitive_value("abc") == "***"
    assert can_modify_config("tushare.token", "uploader") is False
    assert can_modify_config("tushare.token", "content_operator") is False
    assert can_modify_config("tushare.token", "technical_operator") is True
    assert can_modify_config("tushare.token", "admin") is True


def test_business_user_message_uses_reply_config_defaults(business_env):
    from business.config.constants import ErrorCode, user_message

    assert user_message(ErrorCode.UNAUTHORIZED) == "您暂未开通该服务，如需开通请联系服务人员。"
    assert user_message(ErrorCode.SYSTEM_ERROR) == "系统暂时繁忙，请稍后重试。"


def test_business_user_message_can_be_overridden_from_database(business_env):
    from business.config.config_service import save_config
    from business.config.constants import ErrorCode, user_message

    save_config("reply.investment.unauthorized", "请联系客户经理开通权限。", operator_role="admin", operator="pytest")

    assert user_message(ErrorCode.UNAUTHORIZED) == "请联系客户经理开通权限。"
    assert user_message(ErrorCode.SYSTEM_ERROR) == "系统暂时繁忙，请稍后重试。"


def test_business_user_message_uses_config_service_before_reply_defaults(business_env):
    from business.config.config_service import save_config
    from business.config.constants import ErrorCode, user_message

    save_config("reply.investment.no_content", "业务内容稍后更新。", operator_role="admin", operator="pytest")

    assert user_message(ErrorCode.NO_CONTENT) == "业务内容稍后更新。"


def test_web_open_chat_config_is_admin_only(business_env):
    from business.config.config_service import can_modify_config, get_config, save_config

    assert get_config("router.enable_web_open_chat", False) is False
    assert can_modify_config("router.enable_web_open_chat", "technical_operator") is False
    assert can_modify_config("router.enable_web_open_chat", "admin") is True

    with pytest.raises(PermissionError):
        save_config("router.enable_web_open_chat", True, operator_role="technical_operator")

    save_config("router.enable_web_open_chat", True, operator_role="admin")
    assert get_config("router.enable_web_open_chat") is True


def test_business_config_rejects_model_and_wechatmp_keys_without_persisting(business_env):
    from sqlalchemy import select

    from business.schema import db as db
    from business.config.config_service import get_config, save_config, save_configs
    from business.schema.tables import configs

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
        rows = conn.execute(select(configs.c.config_key)).fetchall()
    assert {row[0] for row in rows}.isdisjoint(forbidden)
    assert get_config("tushare.token", "") == ""


def test_web_console_config_save_preserves_masked_business_sensitive_values(business_env):
    from business.config.config_service import get_config, get_configs, save_configs

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


def test_business_skill_loader_reads_builtin_packages_and_excludes_cowagent_skills(business_env):
    from business.components.skill_registry import list_investment_skills

    keys = {item["skill_key"] for item in list_investment_skills()}

    assert {"technical-analysis", "rate", "convertible-bond", "signal-card-renderer"} <= keys
    assert "image-generation" not in keys
    assert "knowledge-wiki" not in keys


def test_business_builtin_components_have_explicit_component_types(business_env):
    from business.components.registry import get_business_definition

    assert get_business_definition("technical-analysis").component_type == "active_script"
    assert get_business_definition("rate").component_type == "active_prompt"
    assert get_business_definition("convertible-bond").component_type == "active_prompt"
    assert get_business_definition("signal-card-renderer").component_type == "passive_script"


def test_content_strategy_components_are_manifest_backed():
    from business.components.registry import get_business_definition

    rate = get_business_definition("rate")
    bond = get_business_definition("convertible-bond")

    assert rate.handler_type == "daily_content"
    assert rate.generation_mode == "pre_generated"
    assert rate.delivery_mode == "direct"
    assert rate.content_enabled is True
    assert rate.routable is True
    assert rate.default_triggers == ("利率",)

    assert bond.handler_type == "daily_content"
    assert bond.generation_mode == "pre_generated"
    assert bond.delivery_mode == "direct"
    assert bond.content_enabled is True
    assert bond.routable is True
    assert bond.default_triggers == ("转债",)


def test_component_paths_define_builtin_and_runtime_roots(business_env):
    from business.components.paths import (
        builtin_components_root,
        runtime_component_root,
        runtime_components_root,
        runtime_versions_root,
    )
    from business.schema.storage import get_storage_dirs

    assert builtin_components_root() == Path.cwd() / "builtin" / "components"
    assert runtime_components_root() == get_storage_dirs()["root"] / "components"
    assert runtime_component_root("technical-analysis") == get_storage_dirs()["root"] / "components" / "technical-analysis"
    assert runtime_versions_root("technical-analysis") == get_storage_dirs()["root"] / "components" / "technical-analysis" / "versions"


def test_builtin_component_manifests_are_clean_and_complete():
    technical = json.loads((Path("builtin/components/technical-analysis/component.json")).read_text(encoding="utf-8"))
    renderer = json.loads((Path("builtin/components/signal-card-renderer/component.json")).read_text(encoding="utf-8"))

    assert technical["component_key"] == "technical-analysis"
    assert technical["entry"] == "scripts/analyze_universal.py"
    assert technical["component_type"] == "active_script"
    assert technical["default_triggers"] == ["技术分析"]
    assert technical["config_key"] == "technical_analysis.skill_path"

    assert renderer["component_key"] == "signal-card-renderer"
    assert renderer["entry"] == "scripts/render_card.py"
    assert renderer["component_type"] == "passive_script"
    assert renderer["routable"] is False
    assert renderer["config_key"] == "render.renderer_path"


def test_default_component_runtime_paths_use_builtin_components(business_env):
    from business.components.registry import get_business_definition
    from business.config.constants import ServiceType
    from business.content.render_service import (
        DEFAULT_RENDERER_PATH,
        DEFAULT_TEMPLATE_BOND_PATH,
        DEFAULT_TEMPLATE_CB_PATH,
        DEFAULT_TEMPLATE_TA_PATH,
        template_for_service,
    )
    from business.content.technical_analysis import _configured_skill_path

    technical = get_business_definition("technical-analysis")
    renderer = get_business_definition("signal-card-renderer")

    assert Path(technical.default_script_path).resolve() == (Path.cwd() / "builtin/components/technical-analysis/scripts/analyze_universal.py").resolve()
    assert Path(renderer.default_script_path).resolve() == (Path.cwd() / "builtin/components/signal-card-renderer/scripts/render_card.py").resolve()
    assert Path(DEFAULT_RENDERER_PATH).as_posix() == "builtin/components/signal-card-renderer/scripts/render_card.py"
    assert Path(DEFAULT_TEMPLATE_TA_PATH).as_posix() == "builtin/components/signal-card-renderer/assets/template_ta.html"
    assert Path(DEFAULT_TEMPLATE_BOND_PATH).as_posix() == "builtin/components/signal-card-renderer/assets/template_bond.html"
    assert Path(DEFAULT_TEMPLATE_CB_PATH).as_posix() == "builtin/components/signal-card-renderer/assets/template_cb.html"
    assert template_for_service(ServiceType.TECHNICAL_ANALYSIS) == DEFAULT_TEMPLATE_TA_PATH
    assert _configured_skill_path().resolve().is_file()
    assert "skills" not in _configured_skill_path().resolve().parts


def test_business_component_trigger_ownership(business_env):
    from business.components.registry import get_business_definition

    assert get_business_definition("technical-analysis").uses_triggers is True
    assert get_business_definition("rate").uses_triggers is True
    assert get_business_definition("convertible-bond").uses_triggers is True
    assert get_business_definition("signal-card-renderer").uses_triggers is False


def test_component_service_lists_components_by_type(business_env):
    from business.components.service import list_components

    items = {item["component_key"]: item for item in list_components()}

    assert items["technical-analysis"]["component_type"] == "active_script"
    assert items["technical-analysis"]["uses_triggers"] is True
    assert items["technical-analysis"]["versioned"] is True
    assert items["rate"]["component_type"] == "active_prompt"
    assert items["rate"]["versioned"] is False
    assert items["signal-card-renderer"]["component_type"] == "passive_script"
    assert items["signal-card-renderer"]["uses_triggers"] is False


def test_component_service_marks_content_modules():
    from business.components.service import list_components

    by_key = {item["component_key"]: item for item in list_components()}

    assert by_key["rate"]["content_enabled"] is True
    assert by_key["rate"]["generation_mode"] == "pre_generated"
    assert by_key["convertible-bond"]["content_enabled"] is True
    assert by_key["signal-card-renderer"]["content_enabled"] is False


def test_component_service_includes_prompt_and_version_data(business_env):
    from business.components.service import list_components
    from business.config.config_service import save_config

    save_config("prompt.rate", "rate prompt v1", operator_role="admin")
    items = {item["component_key"]: item for item in list_components()}

    assert items["rate"]["creation_method"] == "builtin"
    assert items["rate"]["prompt"] == {}
    assert items["rate"]["settings"]["prompt"] == "rate prompt v1"
    assert items["rate"]["versions"] == []
    assert items["technical-analysis"]["versions"]
    assert items["signal-card-renderer"]["versions"]


def test_manual_prompt_component_create_generates_runtime_manifest(business_env):
    from business.components.registry import get_business_definition, match_business
    from business.components.paths import runtime_component_root
    from business.components.service import create_prompt_component, list_components

    created = create_prompt_component(
        {
            "component_key": "macro-commentary",
            "label": "宏观点评",
            "match_type": "suffix",
            "default_triggers": ["宏观点评"],
            "prompt": {
                "template": "请基于用户输入生成宏观点评：{target_text}",
                "output_type": "markdown",
            },
            "enabled": True,
        },
        operator_role="admin",
        operator="pytest",
    )

    manifest = json.loads((runtime_component_root("macro-commentary") / "component.json").read_text(encoding="utf-8"))
    definition = get_business_definition("macro-commentary")
    components = {item["component_key"]: item for item in list_components()}
    matched = match_business("新能源 宏观点评")

    assert created["component_key"] == "macro-commentary"
    assert manifest["creation_method"] == "manual_prompt"
    assert manifest["component_type"] == "active_prompt"
    assert manifest["handler_type"] == "prompt_component"
    assert manifest["prompt"]["template"] == "请基于用户输入生成宏观点评：{target_text}"
    assert definition.prompt["output_type"] == "markdown"
    assert components["macro-commentary"]["prompt"]["template"].startswith("请基于")
    assert components["macro-commentary"]["settings"]["triggers"] == ["宏观点评"]
    assert matched is not None
    assert matched.business_key == "macro-commentary"
    assert matched.target_text == "新能源"


def test_runtime_component_can_be_deleted_but_builtin_component_is_protected(business_env):
    import json

    import pytest

    from business.components.paths import runtime_component_root
    from business.components.service import delete_runtime_component, list_components

    component_dir = runtime_component_root("macro-delete")
    component_dir.mkdir(parents=True, exist_ok=True)
    (component_dir / "component.json").write_text(
        json.dumps(
            {
                "component_key": "macro-delete",
                "label": "可删除宏观组件",
                "service_type": "unmatched",
                "match_type": "prefix",
                "default_triggers": ["可删除宏观"],
                "handler_type": "prompt_to_image",
                "routable": True,
                "prompt_key": "prompt.macro_delete",
                "template_key": "rate",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (component_dir / "versions" / "v1").mkdir(parents=True, exist_ok=True)

    assert "macro-delete" in {item["component_key"] for item in list_components()}

    deleted = delete_runtime_component("macro-delete", operator_role="admin", operator="pytest")

    assert deleted["component_key"] == "macro-delete"
    assert deleted["deleted"] is True
    assert not component_dir.exists()
    assert "macro-delete" not in {item["component_key"] for item in list_components()}
    with pytest.raises(ValueError, match="builtin"):
        delete_runtime_component("rate", operator_role="admin", operator="pytest")


def test_runtime_component_definition_overrides_builtin_definition(business_env):
    from business.components.registry import get_business_definition
    from business.components.paths import runtime_component_root

    component_dir = runtime_component_root("technical-analysis")
    component_dir.mkdir(parents=True, exist_ok=True)
    (component_dir / "component.json").write_text(
        json.dumps(
            {
                "component_key": "technical-analysis",
                "label": "技术分析自定义名称",
                "description": "运行期覆盖定义",
                "service_type": "technical_analysis",
                "match_type": "suffix",
                "default_triggers": ["技术分析", "TA"],
                "handler_type": "builtin_technical_analysis",
                "entry": "scripts/analyze_universal.py",
                "routable": True,
                "config_key": "technical_analysis.skill_path",
                "script_name": "analyze_universal.py",
                "storage_name": "technical-analysis",
                "component_type": "active_script",
                "prompt_key": "prompt.technical_analysis",
                "renderer_component_key": "signal-card-renderer",
                "template_key": "technical_analysis",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    definition = get_business_definition("technical-analysis")

    assert definition.label == "技术分析自定义名称"
    assert definition.default_triggers == ("技术分析", "TA")
    assert definition.uses_triggers is True


def test_skill_versions_list_only_new_runtime_versions(business_env):
    from business.components.paths import runtime_versions_root
    from business.schema.storage import get_storage_dirs
    from business.components.skill_versions import list_versions

    new_version = runtime_versions_root("technical-analysis") / "skill-new"
    old_version = get_storage_dirs()["root"] / "skills" / "technical-analysis" / "skill-old"
    for version_dir, version_id in ((new_version, "skill-new"), (old_version, "skill-old")):
        script = version_dir / "scripts" / "analyze_universal.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("print('ok')", encoding="utf-8")
        (version_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "skill_key": "technical-analysis",
                    "version_id": version_id,
                    "source": "upload",
                    "original_filename": "technical-analysis.zip",
                    "uploaded_at": "2026-06-16T00:00:00+00:00",
                    "operator": "tester",
                    "script_path": str(script),
                    "storage_path": str(version_dir),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    versions = list_versions("technical-analysis")
    version_ids = [item["version_id"] for item in versions]

    assert "builtin-default" in version_ids
    assert "skill-new" in version_ids
    assert "skill-old" not in version_ids
    assert Path(versions[version_ids.index("skill-new")]["storage_path"]) == new_version


def test_business_skill_loader_applies_web_trigger_override(business_env):
    from business.config.config_service import save_config
    from business.config.constants import ServiceType
    from business.components.skill_registry import match_investment_skill

    save_config("skill.rate.triggers", ["今日利率"], operator_role="admin", operator="pytest")

    assert match_investment_skill("利率") is None
    matched = match_investment_skill("今日利率")
    assert matched is not None
    assert matched.skill_key == "rate"
    assert matched.service_type == ServiceType.RATE


def test_business_skill_loader_extracts_suffix_target(business_env):
    from business.config.config_service import save_config
    from business.config.constants import ServiceType
    from business.components.skill_registry import match_investment_skill

    save_config("skill.technical-analysis.triggers", ["走势分析"], operator_role="admin", operator="pytest")

    matched = match_investment_skill("300502.SZ 走势分析")
    assert matched is not None
    assert matched.skill_key == "technical-analysis"
    assert matched.service_type == ServiceType.TECHNICAL_ANALYSIS
    assert matched.target_text == "300502.SZ"


def test_uploaded_business_skill_package_appears_in_registry(business_env, tmp_path):
    from business.components.paths import runtime_component_root, runtime_versions_root
    from business.config.config_service import get_config
    from business.config.constants import ServiceType
    from business.components.skill_registry import list_investment_skills, match_investment_skill
    from business.components.skill_versions import save_package_upload

    package = tmp_path / "macro.zip"
    skill_md = """---
name: macro-analysis
description: 宏观分析投研 Skill
investment:
  label: 宏观分析
  enabled: true
  routable: true
  service_type: macro_analysis
  match_type: exact
  triggers:
    - 宏观
  handler_type: script
  entry: scripts/macro_analysis.py
  output_mode: text
---
# Macro Analysis
"""
    script = "import json\nprint(json.dumps({'success': True, 'reply_text': 'macro ok', 'output_files': []}, ensure_ascii=False))\n"
    with ZipFile(package, "w") as archive:
        archive.writestr("SKILL.md", skill_md)
        archive.writestr("scripts/macro_analysis.py", script)

    uploaded = save_package_upload("macro.zip", package.read_bytes(), operator="pytest")

    keys = {item["skill_key"] for item in list_investment_skills()}
    assert "macro-analysis" in keys
    component_root = runtime_component_root("macro-analysis")
    version_root = runtime_versions_root("macro-analysis") / uploaded["version_id"]
    assert (component_root / "component.json").is_file()
    assert (version_root / "SKILL.md").is_file()
    assert (version_root / "scripts" / "macro_analysis.py").is_file()
    assert get_config("skill.macro-analysis.script_path") == str(version_root / "scripts" / "macro_analysis.py")
    matched = match_investment_skill("宏观")
    assert matched is not None
    assert matched.skill_key == "macro-analysis"
    assert matched.service_type == ServiceType.UNMATCHED


def test_component_import_preview_reads_standard_skill_zip(business_env, tmp_path):
    from business.components.import_service import preview_skill_zip

    package = tmp_path / "ta.zip"
    skill_md = """---
name: ta-pattern
description: 技术分析导入样板
---
# 技术分析
根据标的输出 Markdown 报告和主图。
"""
    with ZipFile(package, "w") as archive:
        archive.writestr("技术分析v0.2/SKILL.md", skill_md)
        archive.writestr("技术分析v0.2/README.md", "# 技术分析 README\n")
        archive.writestr("技术分析v0.2/scripts/analyze_universal.py", "print('ok')\n")
        archive.writestr("技术分析v0.2/scripts/indicator_query.py", "print('query')\n")

    result = preview_skill_zip("技术分析v0.2.zip", package.read_bytes(), operator="pytest")

    preview = result["import"]
    assert preview["import_id"].startswith("import-")
    assert preview["root_dir"] == "技术分析v0.2"
    assert preview["skill_name"] == "ta-pattern"
    assert preview["description"] == "技术分析导入样板"
    assert "技术分析v0.2/scripts/analyze_universal.py" in preview["scripts"]
    assert preview["skill_summary"].startswith("# 技术分析")
    assert preview["readme_summary"].startswith("# 技术分析 README")


def test_component_import_preview_rejects_path_escape_zip(business_env, tmp_path):
    import pytest

    from business.components.import_service import preview_skill_zip

    package = tmp_path / "unsafe.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr("../escape/SKILL.md", "# unsafe\n")

    with pytest.raises(ValueError, match="unsafe zip member path"):
        preview_skill_zip("unsafe.zip", package.read_bytes(), operator="pytest")


def test_component_import_create_generates_runtime_component(business_env, tmp_path):
    from business.components.import_service import create_component_from_import, preview_skill_zip
    from business.components.paths import runtime_component_root
    from business.components.service import list_components
    from business.config.config_service import get_config

    package = tmp_path / "ta.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr("技术分析v0.2/SKILL.md", "# 技术分析\n")
        archive.writestr("技术分析v0.2/scripts/analyze_universal.py", "print('ok')\n")

    preview = preview_skill_zip("技术分析v0.2.zip", package.read_bytes(), operator="pytest")["import"]
    created = create_component_from_import(
        preview["import_id"],
        {
            "component_key": "ta-imported",
            "label": "技术分析导入组件",
            "description": "从 Skill ZIP 表单创建",
            "component_type": "active_script",
            "match_type": "suffix",
            "default_triggers": ["技术分析"],
            "entry": "技术分析v0.2/scripts/analyze_universal.py",
            "execution": {
                "command": ["python", "{entry}", "--symbol", "{target_text}", "--output", "{work_dir}"],
                "outputs": {
                    "report": {"type": "markdown", "pattern": "*技术分析报告*.md"},
                    "main_chart": {"type": "image", "pattern": "*_TA_*.png"},
                },
                "default_output": "report",
            },
            "reply": {"outputs": ["report"]},
            "archive": {"outputs": ["report", "main_chart"]},
        },
        operator="pytest",
    )

    component_root = runtime_component_root("ta-imported")
    version_root = component_root / "versions" / created["version_id"]
    component_manifest = json.loads((component_root / "component.json").read_text(encoding="utf-8"))
    version_manifest = json.loads((version_root / "manifest.json").read_text(encoding="utf-8"))

    assert created["component_key"] == "ta-imported"
    assert component_manifest["handler_type"] == "command_script"
    assert component_manifest["component_type"] == "active_script"
    assert component_manifest["execution"]["default_output"] == "report"
    assert version_manifest["component_key"] == "ta-imported"
    assert (version_root / "技术分析v0.2" / "scripts" / "analyze_universal.py").is_file()
    assert get_config("skill.ta-imported.script_path") == str(version_root / "技术分析v0.2" / "scripts" / "analyze_universal.py")

    components = {item["component_key"]: item for item in list_components()}
    assert components["ta-imported"]["label"] == "技术分析导入组件"
    assert components["ta-imported"]["execution"]["default_output"] == "report"


def test_component_import_create_prompt_component_from_no_script_zip(business_env, tmp_path):
    from business.components.import_service import create_component_from_import, preview_skill_zip
    from business.components.paths import runtime_component_root
    from business.components.service import list_components

    package = tmp_path / "prompt.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "prompt-only/SKILL.md",
            "---\nname: prompt-only\n"
            "description: 无脚本提示词组件\n---\n"
            "# 宏观点评\n根据用户输入生成投研点评。\n",
        )
        archive.writestr("prompt-only/README.md", "# 使用说明\n这是一个无脚本提示词组件。\n")

    preview = preview_skill_zip("prompt.zip", package.read_bytes(), operator="pytest")["import"]
    created = create_component_from_import(
        preview["import_id"],
        {
            "component_key": "macro-from-zip",
            "label": "ZIP 宏观点评",
            "component_type": "active_prompt",
            "match_type": "suffix",
            "default_triggers": ["宏观点评"],
            "prompt": {
                "template": "请基于 Skill 说明和用户输入生成点评：{target_text}",
                "output_type": "markdown",
            },
        },
        operator="pytest",
    )

    manifest = json.loads((runtime_component_root("macro-from-zip") / "component.json").read_text(encoding="utf-8"))
    components = {item["component_key"]: item for item in list_components()}

    assert preview["scripts"] == []
    assert created["component_key"] == "macro-from-zip"
    assert created["version_id"] == ""
    assert manifest["creation_method"] == "zip"
    assert manifest["component_type"] == "active_prompt"
    assert manifest["handler_type"] == "prompt_component"
    assert manifest["prompt"]["template"].startswith("请基于 Skill")
    assert components["macro-from-zip"]["prompt"]["output_type"] == "markdown"


def test_component_import_create_rejects_missing_preview(business_env):
    import pytest

    from business.components.import_service import create_component_from_import

    with pytest.raises(ValueError, match="component import not found"):
        create_component_from_import(
            "import-missing",
            {
                "component_key": "macro-missing",
                "component_type": "active_prompt",
                "default_triggers": ["宏观点评"],
                "prompt": {"template": "hi {target_text}"},
            },
            operator="pytest",
        )


def test_command_script_executor_collects_default_markdown_output(tmp_path):
    from business.execution.command_script_executor import run_command_script_component

    script = tmp_path / "scripts" / "analyze_universal.py"
    script.parent.mkdir()
    script.write_text(
        "import argparse\n"
        "from pathlib import Path\n"
        "parser=argparse.ArgumentParser()\n"
        "parser.add_argument('--symbol')\n"
        "parser.add_argument('--output')\n"
        "args=parser.parse_args()\n"
        "out=Path(args.output)\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "(out / f'{args.symbol}_技术分析报告.md').write_text('# 报告\\n' + args.symbol, encoding='utf-8')\n"
        "(out / f'{args.symbol}_TA_main.png').write_bytes(b'png')\n",
        encoding="utf-8",
    )
    definition = type(
        "Definition",
        (),
        {
            "business_key": "ta-imported",
            "config_key": "",
            "entry": str(script),
            "execution": {
                "command": ["python", "{entry}", "--symbol", "{target_text}", "--output", "{work_dir}"],
                "outputs": {
                    "report": {"type": "markdown", "pattern": "*技术分析报告*.md"},
                    "main_chart": {"type": "image", "pattern": "*_TA_*.png"},
                },
                "default_output": "report",
            },
            "reply": {"outputs": ["report"]},
            "archive": {"outputs": ["report", "main_chart"]},
            "postprocess": {"enabled": False},
        },
    )()

    result = run_command_script_component(definition, "openid", "300502.SZ 技术分析", "300502.SZ")

    assert result.success is True
    assert result.reply_text == "# 报告\n300502.SZ"
    assert result.reply_files == []
    assert len(result.archive_files) == 2
    assert result.outputs["report"].type == "markdown"
    assert result.outputs["main_chart"].type == "image"


def test_command_script_executor_requires_default_output(tmp_path):
    from business.execution.command_script_executor import run_command_script_component

    script = tmp_path / "run.py"
    script.write_text("print('no outputs')\n", encoding="utf-8")
    definition = type(
        "Definition",
        (),
        {
            "business_key": "bad-component",
            "config_key": "",
            "entry": str(script),
            "execution": {
                "command": ["python", "{entry}"],
                "outputs": {"report": {"type": "markdown", "pattern": "*.md"}},
                "default_output": "report",
            },
            "reply": {"outputs": ["report"]},
            "archive": {"outputs": ["report"]},
            "postprocess": {"enabled": False},
        },
    )()

    result = run_command_script_component(definition, "openid", "坏组件", "")

    assert result.success is False
    assert "default output missing" in result.detail


def test_prompt_component_executor_renders_template_and_returns_markdown(monkeypatch):
    from business.execution.prompt_component_executor import run_prompt_component

    calls = []

    class FakeAdapter:
        def generate(self, request):
            calls.append(request)
            return "## 宏观点评\n新能源景气度改善。"

    definition = type(
        "Definition",
        (),
        {
            "business_key": "macro-commentary",
            "prompt": {
                "template": "请基于用户输入生成宏观点评：{target_text}\n原文：{raw_input}",
                "output_type": "markdown",
            },
        },
    )()

    result = run_prompt_component(definition, "openid", "新能源 宏观点评", "新能源", adapter=FakeAdapter())

    assert result.success is True
    assert result.reply_text == "## 宏观点评\n新能源景气度改善。"
    assert result.output_type == "markdown"
    assert calls[0].source_text == "新能源"
    assert calls[0].prompt == "请基于用户输入生成宏观点评：新能源\n原文：新能源 宏观点评"


def test_prompt_component_executes_from_business_route_and_records_module_key(business_env, monkeypatch):
    from business.records.business_records import get_request_record
    from business.components.service import create_prompt_component
    from business.config.constants import ServiceType
    from business.routing.router import handle_text_message
    from business.accounts.user_service import create_user
    import business.execution.prompt_component_executor as prompt_executor

    class FakeAdapter:
        def generate(self, request):
            return f"宏观点评结果：{request.source_text}"

    monkeypatch.setattr(prompt_executor, "ExistingModelAdapter", lambda: FakeAdapter())
    create_user("customer-openid", enabled=True, allowed_services=[ServiceType.ALL])
    create_prompt_component(
        {
            "component_key": "macro-commentary",
            "label": "宏观点评",
            "match_type": "suffix",
            "default_triggers": ["宏观点评"],
            "prompt": {"template": "请点评：{target_text}", "output_type": "markdown"},
            "enabled": True,
        },
        operator_role="admin",
        operator="pytest",
    )

    reply = handle_text_message("customer-openid", "新能源 宏观点评")

    assert reply.success is True
    assert reply.reply_text == "宏观点评结果：新能源"
    assert reply.module_key == "macro-commentary"
    record = get_request_record(reply.request_id)
    assert record.module_key == "macro-commentary"
    assert record.output_files == []


def test_command_script_component_executes_from_business_route(business_env, tmp_path):
    from business.records.business_records import get_request_record, list_artifact_packages_page
    from business.components.import_service import create_component_from_import, preview_skill_zip
    from business.config.constants import ServiceType
    from business.products.product_service import list_products_page
    from business.routing.router import handle_text_message
    from business.accounts.user_service import create_user

    create_user("customer-openid", enabled=True, allowed_services=[ServiceType.ALL])
    script = (
        "import argparse\n"
        "from pathlib import Path\n"
        "parser=argparse.ArgumentParser()\n"
        "parser.add_argument('--symbol')\n"
        "parser.add_argument('--output')\n"
        "args=parser.parse_args()\n"
        "out=Path(args.output)\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "(out / f'{args.symbol}_技术分析报告.md').write_text('导入报告:' + args.symbol, encoding='utf-8')\n"
        "(out / f'{args.symbol}_TA_main.png').write_bytes(b'png')\n"
    )
    package = tmp_path / "ta.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr("技术分析v0.2/SKILL.md", "# 技术分析\n")
        archive.writestr("技术分析v0.2/scripts/analyze_universal.py", script)
    preview = preview_skill_zip("技术分析v0.2.zip", package.read_bytes(), operator="pytest")["import"]
    create_component_from_import(
        preview["import_id"],
        {
            "component_key": "technical-analysis",
            "label": "技术分析路由组件",
            "component_type": "active_script",
            "match_type": "suffix",
            "default_triggers": ["技术分析"],
            "entry": "技术分析v0.2/scripts/analyze_universal.py",
            "execution": {
                "command": ["python", "{entry}", "--symbol", "{target_text}", "--output", "{work_dir}"],
                "outputs": {
                    "report": {"type": "markdown", "pattern": "*技术分析报告*.md"},
                    "main_chart": {"type": "image", "pattern": "*_TA_*.png"},
                },
                "default_output": "report",
            },
            "reply": {"outputs": ["report"]},
            "archive": {"outputs": ["report", "main_chart"]},
        },
        operator="pytest",
    )

    reply = handle_text_message("customer-openid", "300502.SZ 技术分析")

    assert reply.success is True
    assert reply.reply_text == "导入报告:300502.SZ"
    assert reply.output_files == []
    assert reply.module_key == "technical-analysis"
    record = get_request_record(reply.request_id)
    assert record.module_key == "technical-analysis"
    assert len(record.output_files) == 2
    products, total = list_products_page(include_invalidated=True, business_type="component:technical-analysis")
    assert total == 1
    assert products[0]["source_type"] == "request"
    assert products[0]["source_request_id"] == reply.request_id
    assert products[0]["output_files"] == record.output_files

    packages, package_total = list_artifact_packages_page(service_type="component:technical-analysis")
    assert package_total == 1
    assert packages[0]["source_type"] == "product"
    assert packages[0]["source_request_id"] == reply.request_id
    assert packages[0]["files"]


def test_command_script_component_can_postprocess_default_output_once(business_env, tmp_path):
    from business.records.business_records import get_request_record, list_artifact_folder_nodes, list_artifact_packages_page
    from business.components.import_service import create_component_from_import, preview_skill_zip
    from business.config.constants import ActorType, EntryType, ServiceType
    from business.products.product_service import list_products_page
    from business.routing.router import handle_text_message
    from business.schema.storage import get_storage_dirs
    from business.accounts.user_service import create_user

    create_user("customer-openid", enabled=True, allowed_services=[ServiceType.ALL])

    renderer_package = tmp_path / "renderer.zip"
    renderer_script = (
        "import argparse\n"
        "from pathlib import Path\n"
        "parser=argparse.ArgumentParser()\n"
        "parser.add_argument('--text')\n"
        "parser.add_argument('--output')\n"
        "args=parser.parse_args()\n"
        "Path(args.output).write_bytes(('card:' + args.text).encode('utf-8'))\n"
    )
    with ZipFile(renderer_package, "w") as archive:
        archive.writestr("signal-card-renderer/SKILL.md", "# renderer\n")
        archive.writestr("signal-card-renderer/scripts/render_card.py", renderer_script)
    renderer_preview = preview_skill_zip("renderer.zip", renderer_package.read_bytes(), operator="pytest")["import"]
    create_component_from_import(
        renderer_preview["import_id"],
        {
            "component_key": "signal-card-renderer",
            "label": "信号卡渲染",
            "component_type": "passive_script",
            "entry": "signal-card-renderer/scripts/render_card.py",
            "execution": {
                "command": ["python", "{entry}", "--text", "{input_text}", "--output", "{output_file}"],
                "outputs": {"image": {"type": "image", "pattern": "*.png"}},
            },
            "reply": {"outputs": ["image"]},
            "archive": {"outputs": ["image"]},
        },
        operator="pytest",
    )

    ta_package = tmp_path / "ta.zip"
    ta_script = (
        "import argparse\n"
        "from pathlib import Path\n"
        "parser=argparse.ArgumentParser()\n"
        "parser.add_argument('--symbol')\n"
        "parser.add_argument('--output')\n"
        "args=parser.parse_args()\n"
        "out=Path(args.output)\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "(out / f'{args.symbol}_技术分析报告.md').write_text('后处理报告:' + args.symbol, encoding='utf-8')\n"
        "(out / f'{args.symbol}_TA_main.png').write_bytes(b'chart')\n"
    )
    with ZipFile(ta_package, "w") as archive:
        archive.writestr("技术分析v0.2/SKILL.md", "# 技术分析\n")
        archive.writestr("技术分析v0.2/scripts/analyze_universal.py", ta_script)
    ta_preview = preview_skill_zip("技术分析v0.2.zip", ta_package.read_bytes(), operator="pytest")["import"]
    create_component_from_import(
        ta_preview["import_id"],
        {
            "component_key": "technical-analysis",
            "label": "技术分析路由组件",
            "component_type": "active_script",
            "match_type": "suffix",
            "default_triggers": ["技术分析"],
            "entry": "技术分析v0.2/scripts/analyze_universal.py",
            "execution": {
                "command": ["python", "{entry}", "--symbol", "{target_text}", "--output", "{work_dir}"],
                "outputs": {
                    "report": {"type": "markdown", "pattern": "*技术分析报告*.md"},
                    "main_chart": {"type": "image", "pattern": "*_TA_*.png"},
                },
                "default_output": "report",
            },
            "postprocess": {
                "enabled": True,
                "component_key": "signal-card-renderer",
                "input": "report",
                "output": "signal_card",
            },
            "reply": {"outputs": ["signal_card", "main_chart"]},
            "archive": {"outputs": ["signal_card", "main_chart", "report"]},
        },
        operator="pytest",
    )

    reply = handle_text_message(
        "web-session",
        "300502.SZ 技术分析",
        skip_permission=True,
        record_context={
            "entry_type": EntryType.INTERNAL_CALL,
            "actor_type": ActorType.ADMIN,
            "actor_id": "admin",
            "actor_name": "admin",
            "actor_role": "admin",
        },
    )

    assert reply.success is True
    assert reply.reply_text == ""
    assert len(reply.output_files) == 2
    assert all(Path(path).is_file() for path in reply.output_files)
    assert all("component-runs" not in Path(path).parts for path in reply.output_files)
    assert any("signal_card" in Path(path).name for path in reply.output_files)
    record = get_request_record(reply.request_id)
    assert len(record.output_files) == 3
    assert set(reply.output_files).issubset(set(record.output_files))
    component_root = get_storage_dirs()["files"] / "components" / "technical-analysis"
    assert all(Path(path).resolve().is_relative_to(component_root.resolve()) for path in record.output_files)
    products, product_total = list_products_page(include_invalidated=True, business_type="component:technical-analysis")
    assert product_total == 1
    product = products[0]
    assert product["source_type"] == "request"
    assert product["source_request_id"] == reply.request_id
    assert product["output_files"] == record.output_files

    service_nodes, _total = list_artifact_folder_nodes(level="service")
    component_node = next(node for node in service_nodes if node["key"] == "component:technical-analysis")
    assert component_node["label"] == "技术分析路由组件"

    packages, total = list_artifact_packages_page(service_type="component:technical-analysis")
    assert total == 1
    assert packages[0]["source_type"] == "product"
    assert packages[0]["service_type"] == "component:technical-analysis"
    assert packages[0]["service_label"] == "技术分析路由组件"
    assert packages[0]["module_key"] == "technical-analysis"
    assert packages[0]["package_id"] == product["product_id"]
    assert packages[0]["source_request_id"] == reply.request_id
    assert packages[0]["files"]

    package_detail, detail_total = list_artifact_packages_page(package_id=reply.request_id)
    assert detail_total == 1
    assert package_detail[0]["source_type"] == "product"
    assert package_detail[0]["service_label"] == "技术分析路由组件"
    assert package_detail[0]["module_key"] == "technical-analysis"
    assert package_detail[0]["package_id"] == product["product_id"]
    assert package_detail[0]["source_request_id"] == reply.request_id
    assert len(package_detail[0]["files"]) >= 2


def test_uploaded_business_skill_package_rejects_unsafe_skill_key(business_env, tmp_path):
    import pytest

    from business.components.skill_versions import save_package_upload

    package = tmp_path / "unsafe.zip"
    skill_md = """---
name: ../escape
description: unsafe
investment:
  label: Unsafe
  triggers: [unsafe]
  handler_type: script
  entry: scripts/run.py
---
# Unsafe
"""
    with ZipFile(package, "w") as archive:
        archive.writestr("SKILL.md", skill_md)
        archive.writestr("scripts/run.py", "print('{}')\n")

    with pytest.raises(ValueError, match="unsafe investment skill key"):
        save_package_upload("unsafe.zip", package.read_bytes(), operator="pytest")


def test_uploaded_script_business_skill_executes_from_route(business_env, tmp_path):
    from business.config.constants import ServiceType
    from business.routing.router import handle_text_message
    from business.components.skill_versions import save_package_upload
    from business.accounts.user_service import create_user
    import business.components.skill_registry as investment_skill_registry

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    package = tmp_path / "macro.zip"
    skill_md = """---
name: macro-script
description: 宏观分析投研 Skill
investment:
  label: 宏观脚本
  enabled: true
  routable: true
  service_type: macro_analysis
  match_type: exact
  triggers:
    - 宏观脚本
  handler_type: script
  entry: scripts/macro.py
  output_mode: text
---
# Macro
"""
    script = "import json\nprint(json.dumps({'success': True, 'reply_text': 'macro script ok', 'output_files': []}, ensure_ascii=False))\n"
    with ZipFile(package, "w") as archive:
        archive.writestr("SKILL.md", skill_md)
        archive.writestr("scripts/macro.py", script)

    save_package_upload("macro.zip", package.read_bytes(), operator="pytest")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        investment_skill_registry,
        "get_skill_definition",
        lambda *_args, **_kwargs: pytest.fail("runtime script execution must not use investment skill registry"),
    )

    try:
        reply = handle_text_message("ok", "宏观脚本")
    finally:
        monkeypatch.undo()

    assert reply.handled is True
    assert reply.success is True
    assert reply.service_type == ServiceType.UNMATCHED
    assert reply.reply_text == "macro script ok"


def test_uploaded_script_component_archives_outputs_under_component_namespace(business_env, tmp_path):
    from business.accounts.user_service import create_user
    from business.components.skill_versions import save_package_upload
    from business.config.constants import ServiceType
    from business.records.business_records import get_request_record
    from business.routing.router import handle_text_message
    from business.schema.storage import get_storage_dirs

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    package = tmp_path / "testcomponent.zip"
    skill_md = """---
name: testcomponent
description: Test component
investment:
  label: Test Component
  enabled: true
  routable: true
  service_type: unmatched
  match_type: exact
  triggers:
    - testcomponent
  handler_type: script
  entry: scripts/run.py
  output_mode: text
---
# Test Component
"""
    script = (
        "import json\n"
        "from pathlib import Path\n"
        "payload=json.loads(__import__('sys').stdin.read() or '{}')\n"
        "out=Path(__file__).parent / 'testcomponent-output.txt'\n"
        "out.write_text('component output:' + payload.get('raw_input', ''), encoding='utf-8')\n"
        "print(json.dumps({'success': True, 'reply_text': 'ok', 'output_files': [str(out)]}, ensure_ascii=False))\n"
    )
    with ZipFile(package, "w") as archive:
        archive.writestr("SKILL.md", skill_md)
        archive.writestr("scripts/run.py", script)

    save_package_upload("testcomponent.zip", package.read_bytes(), operator="pytest")

    reply = handle_text_message("ok", "testcomponent")

    assert reply.handled is True
    assert reply.success is True
    assert reply.module_key == "testcomponent"
    record = get_request_record(reply.request_id)
    assert record.module_key == "testcomponent"
    assert len(record.output_files) == 1
    component_root = get_storage_dirs()["files"] / "components" / "testcomponent"
    assert Path(record.output_files[0]).resolve().is_relative_to(component_root.resolve())


def test_web_technical_analysis_script_component_returns_uploaded_text(business_env, tmp_path):
    from bridge.reply import ReplyType
    from business.components.skill_versions import save_package_upload
    from channel.web.web_channel import _build_investment_web_reply

    package = tmp_path / "ta-text.zip"
    component_json = {
        "component_key": "technical-analysis",
        "label": "技术分析文本测试组件",
        "description": "技术分析脚本组件测试",
        "service_type": "technical_analysis",
        "match_type": "suffix",
        "default_triggers": ["技术分析"],
        "handler_type": "script",
        "entry": "scripts/analyze_universal.py",
        "output_mode": "text",
        "routable": True,
        "config_key": "technical_analysis.skill_path",
        "script_name": "analyze_universal.py",
        "storage_name": "technical-analysis",
        "component_type": "active_script",
    }
    script = (
        "import json, sys\n"
        "payload=json.loads(sys.stdin.read() or '{}')\n"
        "print(json.dumps({'success': True, 'reply_text': 'WEB_TEXT_COMPONENT:' + payload.get('target_text', ''), 'output_files': []}, ensure_ascii=False))\n"
    )
    with ZipFile(package, "w") as archive:
        archive.writestr("component.json", json.dumps(component_json, ensure_ascii=False))
        archive.writestr("scripts/analyze_universal.py", script)

    save_package_upload("ta-text.zip", package.read_bytes(), operator="pytest")

    reply = _build_investment_web_reply("web-admin-session", "300502.SZ 技术分析")

    assert reply is not None
    assert reply.type == ReplyType.TEXT
    assert reply.content == "WEB_TEXT_COMPONENT:300502.SZ"


def test_web_technical_analysis_uses_active_version_manifest_when_root_manifest_missing(business_env, tmp_path):
    from bridge.reply import ReplyType
    from business.components.paths import runtime_component_root
    from business.components.skill_versions import save_package_upload
    from channel.web.web_channel import _build_investment_web_reply

    package = tmp_path / "ta-text.zip"
    component_json = {
        "component_key": "technical-analysis",
        "label": "技术分析文本测试组件",
        "description": "技术分析脚本组件测试",
        "service_type": "technical_analysis",
        "match_type": "suffix",
        "default_triggers": ["技术分析"],
        "handler_type": "script",
        "entry": "scripts/analyze_universal.py",
        "output_mode": "text",
        "routable": True,
        "config_key": "technical_analysis.skill_path",
        "script_name": "analyze_universal.py",
        "storage_name": "technical-analysis",
        "component_type": "active_script",
    }
    script = (
        "import json, sys\n"
        "payload=json.loads(sys.stdin.read() or '{}')\n"
        "print(json.dumps({'success': True, 'reply_text': 'ACTIVE_VERSION_MANIFEST:' + payload.get('target_text', ''), 'output_files': []}, ensure_ascii=False))\n"
    )
    with ZipFile(package, "w") as archive:
        archive.writestr("component.json", json.dumps(component_json, ensure_ascii=False))
        archive.writestr("scripts/analyze_universal.py", script)

    save_package_upload("ta-text.zip", package.read_bytes(), operator="pytest")
    (runtime_component_root("technical-analysis") / "component.json").unlink()

    reply = _build_investment_web_reply("web-admin-session", "300502.SZ 技术分析")

    assert reply is not None
    assert reply.type == ReplyType.TEXT
    assert reply.content == "ACTIVE_VERSION_MANIFEST:300502.SZ"


def test_business_reply_technical_analysis_script_component_returns_uploaded_text(business_env, tmp_path):
    from bridge.context import Context, ContextType
    from bridge.reply import ReplyType
    from business.routing.business_router import build_business_reply
    from business.config.constants import ServiceType
    from business.components.skill_versions import save_package_upload
    from business.accounts.user_service import create_user

    create_user("customer-openid", enabled=True, allowed_services=[ServiceType.ALL])
    package = tmp_path / "ta-text.zip"
    component_json = {
        "component_key": "technical-analysis",
        "label": "技术分析文本测试组件",
        "description": "技术分析脚本组件测试",
        "service_type": "technical_analysis",
        "match_type": "suffix",
        "default_triggers": ["技术分析"],
        "handler_type": "script",
        "entry": "scripts/analyze_universal.py",
        "output_mode": "text",
        "routable": True,
        "config_key": "technical_analysis.skill_path",
        "script_name": "analyze_universal.py",
        "storage_name": "technical-analysis",
        "component_type": "active_script",
    }
    script = (
        "import json, sys\n"
        "payload=json.loads(sys.stdin.read() or '{}')\n"
        "print(json.dumps({'success': True, 'reply_text': 'CHAT_TEXT_COMPONENT:' + payload.get('target_text', ''), 'output_files': []}, ensure_ascii=False))\n"
    )
    with ZipFile(package, "w") as archive:
        archive.writestr("component.json", json.dumps(component_json, ensure_ascii=False))
        archive.writestr("scripts/analyze_universal.py", script)

    save_package_upload("ta-text.zip", package.read_bytes(), operator="pytest")
    context = Context(ContextType.TEXT, "300502.SZ 技术分析")
    context["session_id"] = "customer-openid"

    reply = build_business_reply(context)

    assert reply is not None
    assert reply.type == ReplyType.TEXT
    assert reply.content == "CHAT_TEXT_COMPONENT:300502.SZ"


def test_business_skill_upload_python_file_creates_version_and_activates_it(business_env):
    from pathlib import Path

    from business.config.config_service import get_config
    from business.components.skill_versions import list_versions, save_upload

    result = save_upload("signal-card-renderer", "render_card.py", b"print('renderer v1')", operator="tester")

    script_path = Path(result["script_path"])
    assert result["version_id"].startswith("skill-")
    assert result["skill_key"] == "signal-card-renderer"
    assert script_path.name == "render_card.py"
    assert script_path.parent.name == "scripts"
    assert script_path.read_text(encoding="utf-8") == "print('renderer v1')"
    assert (script_path.parents[1] / "assets" / "template_ta.html").is_file()
    assert get_config("render.renderer_path") == str(script_path)

    versions = list_versions("signal-card-renderer")
    uploaded = [item for item in versions if item["version_id"] == result["version_id"]][0]
    assert uploaded["active"] is True
    assert uploaded["source"] == "upload"
    assert any(item["version_id"] == "builtin-default" for item in versions)


def test_business_skill_upload_zip_rejects_path_escape_and_requires_script(business_env):
    from io import BytesIO
    from zipfile import ZipFile

    import pytest

    from business.components.skill_versions import save_upload

    unsafe = BytesIO()
    with ZipFile(unsafe, "w") as archive:
        archive.writestr("../escape.py", "bad")
        archive.writestr("scripts/render_card.py", "print('ok')")
    with pytest.raises(ValueError, match="unsafe"):
        save_upload("signal-card-renderer", "skill.zip", unsafe.getvalue(), operator="tester")

    missing = BytesIO()
    with ZipFile(missing, "w") as archive:
        archive.writestr("README.md", "no script")
    with pytest.raises(ValueError, match="render_card.py"):
        save_upload("signal-card-renderer", "skill.zip", missing.getvalue(), operator="tester")


def test_business_skill_version_activation_switches_between_upload_and_builtin(business_env):
    from business.config.config_service import get_config
    from business.components.skill_versions import activate_version, list_versions, save_upload

    uploaded = save_upload("signal-card-renderer", "render_card.py", b"print('renderer v2')", operator="tester")

    activate_version("signal-card-renderer", "builtin-default", operator="tester")

    assert get_config("render.renderer_path", "") == ""
    builtin = [item for item in list_versions("signal-card-renderer") if item["version_id"] == "builtin-default"][0]
    assert builtin["active"] is True

    activate_version("signal-card-renderer", uploaded["version_id"], operator="tester")

    assert get_config("render.renderer_path") == uploaded["script_path"]


def test_business_skill_uploaded_version_can_be_deleted_and_active_delete_falls_back_to_builtin(business_env):
    import pytest

    from business.config.config_service import get_config
    from business.components.skill_versions import delete_version, list_versions, save_upload

    uploaded = save_upload("technical-analysis", "analyze_universal.py", b"print('ta delete')", operator="tester")
    assert get_config("technical_analysis.skill_path") == uploaded["script_path"]

    deleted = delete_version("technical-analysis", uploaded["version_id"], operator="tester")

    assert deleted["version_id"] == uploaded["version_id"]
    assert get_config("technical_analysis.skill_path", "") == ""
    assert uploaded["version_id"] not in [item["version_id"] for item in list_versions("technical-analysis")]

    with pytest.raises(ValueError, match="builtin"):
        delete_version("technical-analysis", "builtin-default", operator="tester")


def test_business_skill_versions_include_loaded_skills(business_env):
    from pathlib import Path

    from business.config.config_service import get_config
    from business.components.skill_versions import activate_version, list_all_skills, save_upload
    from business.components.registry import get_business_definition

    technical = save_upload("technical-analysis", "analyze_universal.py", b"print('ta v1')", operator="tester")
    renderer = save_upload("signal-card-renderer", "render_card.py", b"print('renderer v1')", operator="tester")

    assert Path(technical["script_path"]).name == "analyze_universal.py"
    assert Path(renderer["script_path"]).name == "render_card.py"
    assert get_config("technical_analysis.skill_path") == technical["script_path"]
    assert get_config("render.renderer_path") == renderer["script_path"]

    payload = list_all_skills()
    by_key = {item["skill"]["skill_key"]: item for item in payload}
    assert {"technical-analysis", "signal-card-renderer", "rate", "convertible-bond"} <= set(by_key)
    assert by_key["technical-analysis"]["versions"][0]["version_id"] == "builtin-default"
    assert by_key["signal-card-renderer"]["versions"][0]["version_id"] == "builtin-default"
    assert by_key["rate"]["versions"] == []
    assert by_key["convertible-bond"]["versions"] == []

    activate_version("technical-analysis", "builtin-default", operator="tester")
    assert get_config("technical_analysis.skill_path", "") == ""
    assert get_business_definition("technical-analysis").handler_type == "builtin_technical_analysis"


def test_web_business_skill_handlers_list_upload_and_activate_versions(business_env, monkeypatch):
    from business.config.config_service import get_config
    from channel.web import web_channel
    from channel.web.web_channel import (
        InvestmentSkillActivateHandler,
        InvestmentSkillDeleteHandler,
        InvestmentSkillUploadHandler,
        InvestmentSkillVersionsHandler,
    )

    _login_default_investment_admin(monkeypatch)
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)

    get_payload = json.loads(InvestmentSkillVersionsHandler().GET())

    assert get_payload["status"] == "success"
    assert {"technical-analysis", "signal-card-renderer", "rate", "convertible-bond"} <= {
        item["skill"]["skill_key"] for item in get_payload["skills"]
    }

    upload_file = SimpleNamespace(filename="analyze_universal.py", value=b"print('web technical')")
    monkeypatch.setattr(web_channel, "_raw_web_input", lambda: {"file": upload_file, "operator": "tester"})

    upload_payload = json.loads(InvestmentSkillUploadHandler().POST("technical-analysis"))

    assert upload_payload["status"] == "success"
    assert upload_payload["version"]["active"] is True
    assert get_config("technical_analysis.skill_path") == upload_payload["version"]["script_path"]

    monkeypatch.setattr(web_channel.web, "data", lambda: json.dumps({"operator": "tester"}).encode("utf-8"))
    activate_payload = json.loads(InvestmentSkillActivateHandler().POST("technical-analysis", "builtin-default"))

    assert activate_payload["status"] == "success"
    assert activate_payload["version"]["active"] is True
    assert get_config("technical_analysis.skill_path", "") == ""

    renderer_file = SimpleNamespace(filename="render_card.py", value=b"print('web renderer')")
    monkeypatch.setattr(web_channel, "_raw_web_input", lambda: {"file": renderer_file, "operator": "tester"})
    renderer_payload = json.loads(InvestmentSkillUploadHandler().POST("signal-card-renderer"))
    deleted_payload = json.loads(
        InvestmentSkillDeleteHandler().POST("signal-card-renderer", renderer_payload["version"]["version_id"])
    )

    assert deleted_payload["status"] == "success"
    assert deleted_payload["deleted"]["version_id"] == renderer_payload["version"]["version_id"]
    assert get_config("render.renderer_path", "") == ""


def test_web_user_disable_button_updates_permission_path(business_env, monkeypatch):
    from business.config.constants import ErrorCode, ServiceType
    from business.routing.router import handle_text_message
    from business.accounts.user_service import create_user, get_user_by_openid
    from channel.web import web_channel
    from channel.web.web_channel import InvestmentUserDisableHandler

    create_user("disable-button-openid", enabled=True, allowed_services=[ServiceType.ALL])
    _login_default_investment_admin(monkeypatch)
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr("business.content.technical_analysis.run_technical_analysis", lambda *_args, **_kwargs: pytest.fail("disabled user must not enter technical analysis"))

    payload = json.loads(InvestmentUserDisableHandler().POST("disable-button-openid"))
    reply = handle_text_message("disable-button-openid", "300502.SZ 技术分析")

    assert payload["status"] == "success"
    assert get_user_by_openid("disable-button-openid").enabled is False
    assert reply.success is False
    assert reply.error_code == ErrorCode.USER_DISABLED
    assert reply.reply_text == "您的服务已停用，如需恢复请联系服务人员。"


def test_web_customer_search_enable_and_audits_use_customer_permissions(business_env, monkeypatch):
    from business.audit.audit_service import list_operation_audits
    from business.config.constants import ServiceType
    from business.accounts.user_service import create_user, get_user_by_openid
    from channel.web import web_channel
    from channel.web.web_channel import InvestmentUserStatusHandler, InvestmentUsersHandler

    _login_default_investment_admin(monkeypatch, username="audit-admin")
    create_user(
        "search-openid",
        name="Search Alice",
        institution="North Fund",
        mobile="13800138000",
        enabled=False,
        allowed_services=[ServiceType.RATE],
    )
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(web_channel.web, "input", lambda **_defaults: SimpleNamespace(keyword="North", enabled=""))
    monkeypatch.setattr(web_channel.web.ctx, "headers", [], raising=False)

    listed = json.loads(InvestmentUsersHandler().GET())
    assert [user["openid"] for user in listed["users"]] == ["search-openid"]

    enabled = json.loads(InvestmentUserStatusHandler().POST("search-openid", "enable"))
    assert enabled["status"] == "success"
    assert get_user_by_openid("search-openid").enabled is True

    audits = list_operation_audits(limit=10, target_type="customer", target_id="search-openid")
    assert [audit.action for audit in audits][:1] == ["customer.enable"]
    assert audits[0].operator == "audit-admin"


def test_web_customer_create_audit_binds_session_admin_not_body_operator(business_env, monkeypatch):
    from business.audit.audit_service import list_operation_audits
    from business.accounts.auth_service import authenticate_admin
    from business.schema.db import connect
    from channel.web import web_channel
    from channel.web.web_channel import InvestmentUsersHandler

    _login_default_investment_admin(monkeypatch, username="session-admin")
    admin = authenticate_admin("session-admin", "password")
    assert admin is not None
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(web_channel.web.ctx, "headers", [], raising=False)
    monkeypatch.setattr(
        web_channel.web,
        "data",
        lambda: json.dumps({
            "openid": "actor-openid",
            "name": "Actor Customer",
            "allowed_services": ["全部"],
            "auth_start_at": "2026-01-01T00:00:00",
            "auth_end_at": "2099-12-31T23:59:59",
            "operator": "spoofed-operator",
        }).encode("utf-8"),
    )

    payload = json.loads(InvestmentUsersHandler().POST())

    assert payload["status"] == "success"
    audit = list_operation_audits(limit=1, target_type="customer", target_id="actor-openid")[0]
    assert audit.operator == "session-admin"
    assert audit.operator_admin_id == admin.id
    assert audit.operator_username == "session-admin"
    assert audit.operator_role == "admin"
    assert audit.operation_category == "customer"
    assert audit.result_status == "success"
    assert audit.error_code == ""
    assert audit.error_message == ""
    assert audit.before_state == {}
    assert audit.after_state["openid"] == "actor-openid"
    assert audit.after_state["name"] == "Actor Customer"
    with connect() as conn:
        row = conn.execute(
            text(
                "select created_by_admin_id, created_by_username, updated_by_admin_id, updated_by_username "
                "from customers where openid = 'actor-openid'"
            )
        ).fetchone()
    assert row is not None
    assert row.created_by_admin_id == admin.id
    assert row.created_by_username == "session-admin"
    assert row.updated_by_admin_id == admin.id
    assert row.updated_by_username == "session-admin"


def test_web_user_management_apis_support_keyword_and_pagination(business_env, monkeypatch):
    from business.accounts.auth_service import create_admin_user
    from business.config.constants import ServiceType
    from business.accounts.user_service import create_user
    from channel.web import web_channel
    from channel.web.web_channel import InvestmentAdminUsersHandler, InvestmentUsersHandler

    _login_default_investment_admin(monkeypatch)
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(web_channel.web.ctx, "headers", [], raising=False)

    for index in range(5):
        create_user(
            f"customer-page-{index}",
            name=f"Paged Customer {index}",
            institution="North Fund" if index < 4 else "South Fund",
            mobile=f"1380000000{index}",
            allowed_services=[ServiceType.ALL],
        )

    monkeypatch.setattr(
        web_channel.web,
        "input",
        lambda **_defaults: SimpleNamespace(keyword="North", enabled="", page="2", page_size="2"),
    )
    customers = json.loads(InvestmentUsersHandler().GET())

    assert customers["status"] == "success"
    assert customers["pagination"] == {"page": 2, "page_size": 2, "total": 4, "total_pages": 2}
    assert len(customers["users"]) == 2
    assert all("North" in user["institution"] for user in customers["users"])

    for index in range(5):
        role = "admin" if index == 0 else "content_operator"
        create_admin_user(f"ops-page-{index}", "password", role=role)

    monkeypatch.setattr(
        web_channel.web,
        "input",
        lambda **_defaults: SimpleNamespace(keyword="ops-page", page="2", page_size="2"),
    )
    admins = json.loads(InvestmentAdminUsersHandler().GET())

    assert admins["status"] == "success"
    assert admins["pagination"] == {"page": 2, "page_size": 2, "total": 5, "total_pages": 3}
    assert [user["username"] for user in admins["users"]] == ["ops-page-2", "ops-page-3"]


def test_web_customer_keyword_search_keeps_rows_and_total_consistent(business_env, monkeypatch):
    from business.config.constants import ServiceType
    from business.accounts.user_service import create_user
    from channel.web import web_channel
    from channel.web.web_channel import InvestmentUsersHandler

    _login_default_investment_admin(monkeypatch)
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(web_channel.web.ctx, "headers", [], raising=False)

    create_user("1o92zVw4BYH2qai", name="A", allowed_services=[ServiceType.ALL])
    create_user("o92zVw4BYH2qaib", name="B", allowed_services=[ServiceType.ALL])
    create_user("runtime-user-62b63e3cca25", name="Runtime", allowed_services=[ServiceType.ALL])
    monkeypatch.setattr(
        web_channel.web,
        "input",
        lambda **_defaults: SimpleNamespace(keyword="92", enabled="", page="1", page_size="20"),
    )

    payload = json.loads(InvestmentUsersHandler().GET())

    assert payload["status"] == "success"
    assert payload["pagination"]["total"] == 2
    assert [user["openid"] for user in payload["users"]] == ["o92zVw4BYH2qaib", "1o92zVw4BYH2qai"]


def test_web_customer_keyword_search_supports_field_categories(business_env, monkeypatch):
    from business.config.constants import ServiceType
    from business.accounts.user_service import create_user
    from channel.web import web_channel
    from channel.web.web_channel import InvestmentUsersHandler

    _login_default_investment_admin(monkeypatch)
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(web_channel.web.ctx, "headers", [], raising=False)

    create_user("openid-name-hit", name="分类客户", mobile="13800000000", allowed_services=[ServiceType.ALL])
    create_user("分类-openid-only", name="OpenID Only", mobile="13900000000", allowed_services=[ServiceType.ALL])
    create_user("service-rate-hit", name="普通客户", mobile="13700000000", allowed_services=[ServiceType.RATE])
    create_user("name-rate-only", name="利率客户", mobile="13600000000", allowed_services=[ServiceType.ALL])

    monkeypatch.setattr(
        web_channel.web,
        "input",
        lambda **_defaults: SimpleNamespace(keyword="分类", keyword_field="name", enabled="", page="1", page_size="20"),
    )
    name_payload = json.loads(InvestmentUsersHandler().GET())

    assert name_payload["status"] == "success"
    assert name_payload["pagination"]["total"] == 1
    assert [user["openid"] for user in name_payload["users"]] == ["openid-name-hit"]

    monkeypatch.setattr(
        web_channel.web,
        "input",
        lambda **_defaults: SimpleNamespace(keyword="利率", keyword_field="service", enabled="", page="1", page_size="20"),
    )
    service_payload = json.loads(InvestmentUsersHandler().GET())

    assert service_payload["status"] == "success"
    assert service_payload["pagination"]["total"] == 1
    assert [user["openid"] for user in service_payload["users"]] == ["service-rate-hit"]

    monkeypatch.setattr(
        web_channel.web,
        "input",
        lambda **_defaults: SimpleNamespace(keyword="利率", keyword_field="all", enabled="", page="1", page_size="20"),
    )
    all_payload = json.loads(InvestmentUsersHandler().GET())

    assert all_payload["status"] == "success"
    assert all_payload["pagination"]["total"] == 2


def test_router_authenticates_before_parsing_unmatched_input(business_env, monkeypatch):
    import pytest

    from business.config.constants import ErrorCode, ServiceType
    import business.routing.router as router
    from business.routing.router import DEFAULT_UNMATCHED_PROMPT, handle_text_message
    from business.accounts.user_service import create_user

    monkeypatch.setattr(router, "parse_route", lambda _raw_input: pytest.fail("unauthorized input must not be parsed"))

    denied = handle_text_message("missing-openid", "hello")

    assert denied.success is False
    assert denied.error_code == ErrorCode.UNAUTHORIZED
    assert denied.reply_text == "您暂未开通该服务，如需开通请联系服务人员。"

    create_user("ok-unmatched-openid", enabled=True, allowed_services=[ServiceType.RATE])
    monkeypatch.setattr(
        router,
        "parse_route",
        lambda raw_input: router.RouteResult(False, ServiceType.UNMATCHED, raw_input, error_code=ErrorCode.INPUT_ERROR),
    )

    miss = handle_text_message("ok-unmatched-openid", "hello")

    assert miss.success is False
    assert miss.error_code == ErrorCode.INPUT_ERROR
    assert miss.reply_text == DEFAULT_UNMATCHED_PROMPT


def test_web_user_edit_updates_existing_user_permissions(business_env, monkeypatch):
    from business.config.constants import ErrorCode, ServiceType
    from business.accounts.user_service import create_user, verify_permission
    from channel.web import web_channel
    from channel.web.web_channel import InvestmentUsersHandler

    create_user("edit-button-openid", enabled=True, allowed_services=[ServiceType.ALL])
    _login_default_investment_admin(monkeypatch)
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(web_channel.web.ctx, "env", {"CONTENT_TYPE": "application/json"}, raising=False)
    monkeypatch.setattr(
        web_channel.web,
        "data",
        lambda: json.dumps(
            {
                "openid": "edit-button-openid",
                "name": "Edited",
                "institution": "Edited Inst",
                "enabled": True,
                "allowed_services": ["利率"],
                "auth_start_at": "2026-01-01T00:00:00",
                "auth_end_at": "2099-12-31T23:59:59",
            },
            ensure_ascii=False,
        ).encode("utf-8"),
    )

    payload = json.loads(InvestmentUsersHandler().POST())

    assert payload["status"] == "success"
    assert payload["action"] == "updated"
    assert verify_permission("edit-button-openid", ServiceType.RATE).allowed is True
    technical = verify_permission("edit-button-openid", ServiceType.TECHNICAL_ANALYSIS)
    assert technical.allowed is False
    assert technical.error_code == ErrorCode.UNAUTHORIZED


def test_business_skill_settings_post_updates_triggers_and_enabled(business_env, monkeypatch):
    from business.config.config_service import get_config
    from channel.web import web_channel
    from channel.web.web_channel import InvestmentSkillSettingsHandler

    _login_default_investment_admin(monkeypatch)
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        web_channel.web,
        "data",
        lambda: json.dumps(
            {
                "enabled": False,
                "triggers": ["今日利率", "利率观察"],
                "operator": "pytest",
            },
            ensure_ascii=False,
        ).encode("utf-8"),
    )

    payload = json.loads(InvestmentSkillSettingsHandler().POST("rate"))

    assert payload["status"] == "success"
    assert get_config("skill.rate.enabled") is False
    assert get_config("skill.rate.triggers") == ["今日利率", "利率观察"]


def test_component_settings_save_updates_active_prompt_component(business_env, monkeypatch):
    from business.components.registry import get_business_definition, resolve_triggers
    from business.config.config_service import get_config
    from channel.web import web_channel
    from channel.web.web_channel import InvestmentComponentSettingsHandler

    _login_default_investment_admin(monkeypatch)
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        web_channel.web,
        "data",
        lambda: json.dumps(
            {
                "enabled": False,
                "triggers": ["今日利率", "利率观察"],
                "prompt": "updated rate prompt",
            },
            ensure_ascii=False,
        ).encode("utf-8"),
    )

    payload = json.loads(InvestmentComponentSettingsHandler().POST("rate"))

    assert payload["status"] == "success"
    assert payload["component"]["component_key"] == "rate"
    assert get_config("skill.rate.enabled") is False
    assert resolve_triggers(get_business_definition("rate")) == ("今日利率", "利率观察")
    assert get_config("prompt.rate") == "updated rate prompt"


def test_component_settings_rejects_triggers_for_passive_component(business_env, monkeypatch):
    from channel.web import web_channel
    from channel.web.web_channel import InvestmentComponentSettingsHandler

    _login_default_investment_admin(monkeypatch)
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        web_channel.web,
        "data",
        lambda: json.dumps({"triggers": ["渲染"]}, ensure_ascii=False).encode("utf-8"),
    )

    payload = json.loads(InvestmentComponentSettingsHandler().POST("signal-card-renderer"))

    assert payload["status"] == "error"
    assert "triggers" in payload["message"]


def test_component_settings_updates_runtime_command_script_manifest(business_env, monkeypatch):
    from business.components.paths import runtime_component_root
    from channel.web import web_channel
    from channel.web.web_channel import InvestmentComponentSettingsHandler

    _login_default_investment_admin(monkeypatch)
    component_dir = runtime_component_root("editable-command")
    component_dir.mkdir(parents=True, exist_ok=True)
    (component_dir / "component.json").write_text(
        json.dumps(
            {
                "component_key": "editable-command",
                "label": "旧名称",
                "service_type": "unmatched",
                "match_type": "suffix",
                "default_triggers": ["旧"],
                "handler_type": "command_script",
                "entry": "sample/scripts/run_text.py",
                "routable": True,
                "config_key": "skill.editable-command.script_path",
                "script_name": "run_text.py",
                "storage_name": "editable-command",
                "component_type": "active_script",
                "execution": {
                    "command": ["python", "{entry}", "--symbol", "{target_text}", "--output", "{work_dir}"],
                    "outputs": {"result": {"type": "text", "pattern": "result.txt"}},
                    "default_output": "result",
                },
                "postprocess": {"enabled": False},
                "reply": {"outputs": ["result"]},
                "archive": {"outputs": ["result"]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        web_channel.web,
        "data",
        lambda: json.dumps(
            {
                "component_config": {
                    "label": "新名称",
                    "match_type": "exact",
                    "execution": {
                        "command": ["python", "{entry}", "--input", "{target_text}", "--output", "{work_dir}"],
                        "outputs": {"result": {"type": "text", "pattern": "result.txt"}},
                        "default_output": "result",
                    },
                    "postprocess": {"enabled": False},
                    "reply": {"outputs": ["result"]},
                    "archive": {"outputs": ["result"]},
                }
            },
            ensure_ascii=False,
        ).encode("utf-8"),
    )

    payload = json.loads(InvestmentComponentSettingsHandler().POST("editable-command"))
    manifest = json.loads((component_dir / "component.json").read_text(encoding="utf-8"))

    assert payload["status"] == "success"
    assert manifest["label"] == "新名称"
    assert manifest["match_type"] == "exact"
    assert manifest["execution"]["command"][2] == "--input"
    assert payload["component"]["label"] == "新名称"


def test_component_settings_updates_runtime_prompt_component_manifest(business_env, monkeypatch):
    from business.components.service import create_prompt_component
    from business.components.paths import runtime_component_root
    from channel.web import web_channel
    from channel.web.web_channel import InvestmentComponentSettingsHandler

    _login_default_investment_admin(monkeypatch)
    create_prompt_component(
        {
            "component_key": "editable-prompt",
            "label": "旧提示词组件",
            "match_type": "suffix",
            "default_triggers": ["旧点评"],
            "prompt": {"template": "旧模板：{target_text}", "output_type": "markdown"},
            "enabled": True,
        },
        operator_role="admin",
        operator="pytest",
    )
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        web_channel.web,
        "data",
        lambda: json.dumps(
            {
                "triggers": ["新点评"],
                "component_config": {
                    "label": "新提示词组件",
                    "match_type": "prefix",
                    "prompt": {"template": "新模板：{target_text}", "output_type": "text"},
                    "reply": {"outputs": ["text"]},
                    "archive": {"outputs": ["text"]},
                },
            },
            ensure_ascii=False,
        ).encode("utf-8"),
    )

    payload = json.loads(InvestmentComponentSettingsHandler().POST("editable-prompt"))
    manifest = json.loads((runtime_component_root("editable-prompt") / "component.json").read_text(encoding="utf-8"))

    assert payload["status"] == "success"
    assert manifest["label"] == "新提示词组件"
    assert manifest["match_type"] == "prefix"
    assert manifest["prompt"] == {"template": "新模板：{target_text}", "output_type": "text"}
    assert payload["component"]["settings"]["triggers"] == ["新点评"]


def test_prompt_component_create_web_api(business_env, monkeypatch):
    from business.components.paths import runtime_component_root
    from channel.web import investment_handlers, web_channel
    from channel.web.web_channel import InvestmentPromptComponentHandler

    _login_default_investment_admin(monkeypatch)
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        web_channel.web,
        "data",
        lambda: json.dumps(
            {
                "component_key": "macro-web",
                "label": "Web 宏观点评",
                "match_type": "suffix",
                "default_triggers": ["宏观点评"],
                "prompt": {"template": "请点评：{target_text}", "output_type": "markdown"},
                "enabled": True,
            },
            ensure_ascii=False,
        ).encode("utf-8"),
    )

    payload = json.loads(InvestmentPromptComponentHandler().POST())
    manifest = json.loads((runtime_component_root("macro-web") / "component.json").read_text(encoding="utf-8"))

    assert "/api/investment/components/prompt" in investment_handlers.INVESTMENT_API_URLS
    assert payload["status"] == "success"
    assert payload["component"]["component_key"] == "macro-web"
    assert manifest["creation_method"] == "manual_prompt"
    assert manifest["handler_type"] == "prompt_component"


def test_component_settings_rejects_manifest_update_for_builtin_component(business_env, monkeypatch):
    from channel.web import web_channel
    from channel.web.web_channel import InvestmentComponentSettingsHandler

    _login_default_investment_admin(monkeypatch)
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        web_channel.web,
        "data",
        lambda: json.dumps({"component_config": {"label": "不允许"}}).encode("utf-8"),
    )

    payload = json.loads(InvestmentComponentSettingsHandler().POST("rate"))

    assert payload["status"] == "error"
    assert "runtime command components" in payload["message"]


def test_business_skill_settings_audit_records_before_and_after_values(business_env, monkeypatch):
    from business.audit.audit_service import list_operation_audits
    from business.config.config_service import save_config
    from channel.web import web_channel
    from channel.web.web_channel import InvestmentSkillSettingsHandler

    save_config("skill.rate.enabled", True, operator_role="admin", operator="seed")
    save_config("skill.rate.triggers", ["利率"], operator_role="admin", operator="seed")
    _login_default_investment_admin(monkeypatch)
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        web_channel.web,
        "data",
        lambda: json.dumps(
            {
                "enabled": False,
                "triggers": ["今日利率", "利率观察"],
            },
            ensure_ascii=False,
        ).encode("utf-8"),
    )

    payload = json.loads(InvestmentSkillSettingsHandler().POST("rate"))
    audits = list_operation_audits(action="skill.settings.update", target_type="investment_skill", target_id="rate", limit=5)

    assert payload["status"] == "success"
    assert audits[0].before_state == {"skill.rate.enabled": True, "skill.rate.triggers": ["利率"]}
    assert audits[0].after_state == {"skill.rate.enabled": False, "skill.rate.triggers": ["今日利率", "利率观察"]}
    assert audits[0].operator_username == "admin"


def _login_default_investment_admin(monkeypatch, *, username="admin", password="password"):
    from business.accounts.auth_service import authenticate_admin, create_admin_session, create_admin_user
    from channel.web import web_channel

    admin = authenticate_admin(username, password)
    if admin is None:
        create_admin_user(username, password, role="admin")
        admin = authenticate_admin(username, password)
    assert admin is not None
    token = create_admin_session(admin)
    monkeypatch.setattr(web_channel.web, "cookies", lambda: {"cow_investment_session": token})
    monkeypatch.setattr(web_channel.web.ctx, "headers", [], raising=False)
    return token


def _call_investment_json_handler(monkeypatch, handler, *, params=None, body=None):
    from channel.web import web_channel

    _login_default_investment_admin(monkeypatch)
    monkeypatch.setattr(web_channel.web, "input", lambda **defaults: SimpleNamespace(**{**defaults, **(params or {})}))
    monkeypatch.setattr(web_channel.web, "data", lambda: json.dumps(body or {}, ensure_ascii=False).encode("utf-8"))
    monkeypatch.setattr(web_channel.web.ctx, "headers", [], raising=False)

    raw = handler()
    payload = json.loads(raw)
    return payload


def _call_investment_bytes_handler(monkeypatch, handler, *, params=None):
    from channel.web import web_channel

    _login_default_investment_admin(monkeypatch)
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(web_channel.web, "input", lambda **defaults: SimpleNamespace(**{**defaults, **(params or {})}))
    monkeypatch.setattr(web_channel.web.ctx, "headers", [], raising=False)
    raw = handler()
    assert isinstance(raw, bytes)
    return raw


def test_web_business_config_returns_masked_tushare_token(business_env, monkeypatch):
    from business.config.config_service import save_config
    from channel.web.web_channel import InvestmentConfigHandler

    save_config("tushare.token", "ts-web-secret-1234567890", operator_role="admin")

    payload = _call_investment_json_handler(monkeypatch, InvestmentConfigHandler().GET)

    assert payload["status"] == "success"
    assert payload["configs"]["tushare.token"] == "ts-w**********7890"
    assert "ts-web-secret-1234567890" not in json.dumps(payload, ensure_ascii=False)


def test_web_business_config_returns_reply_text_metadata(business_env, monkeypatch):
    from channel.web.web_channel import InvestmentConfigHandler

    payload = _call_investment_json_handler(monkeypatch, InvestmentConfigHandler().GET)

    assert payload["status"] == "success"
    assert "reply_texts" in payload
    assert any(group["title"] == "公众号处理状态" for group in payload["reply_texts"]["groups"])
    assert payload["reply_texts"]["definitions"]["reply.wechatmp.pending_result_invalidated"]["label"] == "待领取内容失效提示"
    assert "reply.wechatmp.pending_result_invalidated" in payload["configs"]
    assert payload["configs"]["reply.wechatmp.pending_result_invalidated"] == "内容已失效，请重新发起请求。"
    assert payload["reply_texts"]["definitions"]["reply.wechatmp.immediate_ack"]["label"] == "收到请求提示"
    assert payload["configs"]["reply.wechatmp.immediate_ack"] == "收到，正在处理，请稍候。请等待30-40s后回复1获取\n{pending_summary}"
    assert payload["reply_texts"]["definitions"]["reply.wechatmp.immediate_ack"]["placeholders"] == ["pending_summary"]
    assert payload["reply_texts"]["definitions"]["reply.wechatmp.technical_running_new_request"]["label"] == "运行中重复技术分析提示"
    assert payload["reply_texts"]["definitions"]["reply.wechatmp.technical_running_new_request"]["placeholders"] == ["running_title"]
    assert payload["reply_texts"]["definitions"]["reply.wechatmp.technical_ready"]["label"] == "技术分析可领取提示"
    assert payload["reply_texts"]["definitions"]["reply.wechatmp.technical_ready"]["placeholders"] == ["target"]
    assert payload["reply_texts"]["definitions"]["reply.wechatmp.pending_summary"]["label"] == "待领取内容摘要"
    assert payload["reply_texts"]["definitions"]["reply.wechatmp.pending_summary"]["placeholders"] == ["items"]
    assert "reply.wechatmp.technical_ack" not in payload["reply_texts"]["definitions"]
    assert "reply.wechatmp.technical_cache_hit" not in payload["reply_texts"]["definitions"]
    assert "reply.wechatmp.unmatched" not in payload["reply_texts"]["definitions"]


def test_web_business_config_saves_reply_text_values(business_env, monkeypatch):
    from business.config.config_service import get_config
    from channel.web.web_channel import InvestmentConfigHandler

    body = {"configs": {"reply.wechatmp.pending_result_invalidated": "结果已失效，请重新发起。"}}
    payload = _call_investment_json_handler(monkeypatch, InvestmentConfigHandler().POST, body=body)

    assert payload["status"] == "success"
    assert get_config("reply.wechatmp.pending_result_invalidated") == "结果已失效，请重新发起。"


def test_web_business_config_audit_records_before_and_after_values(business_env, monkeypatch):
    from business.audit.audit_service import list_operation_audits
    from business.config.config_service import save_config
    from channel.web.web_channel import InvestmentConfigHandler

    save_config("reply.wechatmp.pending_result_invalidated", "旧提示", operator_role="admin", operator="seed")

    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentConfigHandler().POST,
        body={"configs": {"reply.wechatmp.pending_result_invalidated": "新提示"}},
    )
    audits = list_operation_audits(action="config.update", target_type="investment_config", limit=5)

    assert payload["status"] == "success"
    assert audits[0].before_state == {"reply.wechatmp.pending_result_invalidated": "旧提示"}
    assert audits[0].after_state == {"reply.wechatmp.pending_result_invalidated": "新提示"}
    assert audits[0].operator_username == "admin"


def test_web_business_config_excludes_and_rejects_global_model_and_wechatmp_keys(business_env, monkeypatch):
    from sqlalchemy import select

    from business.schema import db as db
    from business.schema.tables import configs
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
            for row in conn.execute(select(configs.c.config_key)).fetchall()
        }
    assert keys.isdisjoint({"model.name", "model.api_key", "wechatmp.app_id"})
    assert "tushare.token" not in keys

    get_payload = _call_investment_json_handler(monkeypatch, InvestmentConfigHandler().GET)
    assert get_payload["status"] == "success"
    assert "tushare.token" in get_payload["configs"]
    assert not any(key.startswith(("model.", "wechatmp.")) for key in get_payload["configs"])


def test_web_stock_query_returns_matches_and_stats_without_refresh(business_env, monkeypatch):
    from business.content import stock_resolver as stock_resolver
    import business.content.stock_resolver as web_stock_resolver
    from channel.web.web_channel import InvestmentStocksHandler

    stock_resolver.refresh_stock_symbols(
        [
            {"code": "300502.SZ", "name": "新易盛", "market": "SZ", "source": "seed"},
            {"code": "600519.SH", "name": "贵州茅台", "market": "SH", "source": "seed"},
        ],
        source="seed",
    )
    monkeypatch.setattr(web_stock_resolver, "refresh_all_symbols_from_tushare", lambda: pytest.fail("query must not refresh"))
    monkeypatch.setattr(web_stock_resolver, "refresh_a_share_symbols_from_tushare", lambda: pytest.fail("query must not refresh"))
    monkeypatch.setattr(web_stock_resolver, "refresh_hk_symbols_from_tushare", lambda: pytest.fail("query must not refresh"))
    monkeypatch.setattr(web_stock_resolver, "refresh_us_symbols_from_tushare", lambda: pytest.fail("query must not refresh"))

    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentStocksHandler().GET,
        params={"name": "新易盛", "limit": "20"},
    )

    assert payload["status"] == "success"
    assert [item["code"] for item in payload["stocks"]] == ["300502.SZ"]
    assert payload["stats"]["total"] == 2
    assert payload["stats"]["source_count"] == 1


def test_web_stock_refresh_dispatches_sources_and_reports_failures(business_env, monkeypatch):
    import business.content.stock_resolver as stock_resolver
    from channel.web.web_channel import InvestmentStocksRefreshHandler

    monkeypatch.setattr(stock_resolver, "refresh_a_share_symbols_from_tushare", lambda: 3)
    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentStocksRefreshHandler().POST,
        body={"source": "a_share"},
    )
    assert payload["status"] == "success"
    assert payload["result"] == {"a_share": {"count": 3}}
    assert "stats" in payload

    monkeypatch.setattr(stock_resolver, "refresh_hk_symbols_from_tushare", lambda: (_ for _ in ()).throw(RuntimeError("hk failed")))
    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentStocksRefreshHandler().POST,
        body={"source": "hk"},
    )
    assert payload["status"] == "error"
    assert payload["message"] == "hk failed"

    monkeypatch.setattr(stock_resolver, "refresh_all_symbols_from_tushare", lambda: {"a_share": {"error": "a failed"}, "hk": {"count": 4}, "us": {"count": 5}})
    payload = _call_investment_json_handler(monkeypatch, InvestmentStocksRefreshHandler().POST, body={})
    assert payload["status"] == "success"
    assert payload["result"] == {"a_share": {"error": "a failed"}, "hk": {"count": 4}, "us": {"count": 5}}


def test_business_record_cleanup_dry_run_and_execute_remove_useless_records(business_env):
    from business.schema.db import connect
    from business.records.cleanup import cleanup_useless_business_records
    from business.schema.tables import (
        admin_sessions,
        configs,
        content_records,
        request_records,
        stock_symbols,
    )

    with connect() as conn:
        conn.execute(
            configs.insert(),
            {
                "config_key": "runtime.pg.test.cleanup",
                "config_value": "temp",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "updated_by": "pytest",
            },
        )
        conn.execute(
            stock_symbols.insert(),
            {
                "code": "000000.SZ",
                "name": "测试股票",
                "market": "SZ",
                "source": "runtime-test",
                "updated_at": "2026-01-01T00:00:00+00:00",
            },
        )
        conn.execute(
            admin_sessions.insert(),
            {
                "session_id": "expired-session",
                "user_id": 1,
                "token_hash": "expired-token-hash",
                "created_at": "2026-01-01T00:00:00+00:00",
                "expires_at": "2026-01-02T00:00:00+00:00",
            },
        )
        conn.execute(
            request_records.insert(),
            {
                "request_id": "old-unmatched-cleanup",
                "openid": "cleanup-openid",
                "raw_input": "nonsense",
                "service_type": "unmatched",
                "status": "failed",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            },
        )
        conn.execute(
            content_records.insert(),
            {
                "content_id": "old-failed-content-cleanup",
                "service_type": "rate",
                "source_files": "[]",
                "source_text": "old failed content",
                "generated_text": "",
                "output_image": "",
                "status": "generate_failed",
                "error_message": "failed",
                "operator": "pytest",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "content_version": 1,
            },
        )
    dry_run = cleanup_useless_business_records(now="2026-06-02T00:00:00+00:00", dry_run=True)
    assert dry_run["runtime_test_configs"] == 1
    assert dry_run["runtime_test_stocks"] == 1
    assert dry_run["expired_admin_sessions"] == 1
    assert "old_exception_requests" not in dry_run
    assert "old_failed_contents" not in dry_run
    assert "stale_invalid_cache_entries" not in dry_run

    with connect() as conn:
        assert conn.execute(text("select count(*) from configs where config_key = 'runtime.pg.test.cleanup'")).scalar_one() == 1

    executed = cleanup_useless_business_records(now="2026-06-02T00:00:00+00:00", dry_run=False)
    assert executed == dry_run
    with connect() as conn:
        assert conn.execute(text("select count(*) from configs where config_key = 'runtime.pg.test.cleanup'")).scalar_one() == 0
        assert conn.execute(text("select count(*) from stock_symbols where source = 'runtime-test'")).scalar_one() == 0
        assert conn.execute(text("select count(*) from admin_sessions where session_id = 'expired-session'")).scalar_one() == 0
        assert conn.execute(text("select count(*) from request_records where request_id = 'old-unmatched-cleanup'")).scalar_one() == 1
        assert conn.execute(text("select count(*) from content_records where content_id = 'old-failed-content-cleanup'")).scalar_one() == 1


def test_cleanup_does_not_delete_products_or_legacy_product_sources(business_env, tmp_path):
    from business.products.product_service import create_product, list_products_page
    from business.records.cleanup import cleanup_useless_business_records
    from business.schema.db import connect
    from business.schema.tables import content_records, request_records

    product_file = tmp_path / "cleanup-product.png"
    product_file.write_bytes(b"product")

    product = create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="新易盛",
        business_date="2026-06-24",
        version_fingerprint="cleanup-v1",
        source_request_id="cleanup-source-request",
        source_content_id="cleanup-source-content",
        source_cache_key="cleanup-source-cache",
        source_type="request",
        output_files=[str(product_file)],
        text_content="cleanup product",
    )

    with connect() as conn:
        conn.execute(
            request_records.insert(),
            {
                "request_id": "cleanup-source-request",
                "openid": "cleanup-openid",
                "raw_input": "300502.SZ 技术分析",
                "service_type": "technical_analysis",
                "status": "success",
                "output_files": "[]",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            },
        )
        conn.execute(
            content_records.insert(),
            {
                "content_id": "cleanup-source-content",
                "service_type": "rate",
                "source_files": "[]",
                "source_text": "cleanup source",
                "generated_text": "cleanup generated",
                "output_image": str(product_file),
                "status": "effective",
                "operator": "pytest",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "content_version": 1,
            },
        )
    cleanup_useless_business_records(now="2026-06-02T00:00:00+00:00", dry_run=False)

    products, total = list_products_page(include_invalidated=True, business_type="technical_analysis")
    assert total == 1
    assert products[0]["product_id"] == product["product_id"]
    assert products[0]["output_files"] == [str(product_file)]
    with connect() as conn:
        assert conn.execute(text("select count(*) from request_records where request_id = 'cleanup-source-request'")).scalar_one() == 1
        assert conn.execute(text("select count(*) from content_records where content_id = 'cleanup-source-content'")).scalar_one() == 1


def test_web_daily_content_generate_marks_generating_before_background_task(business_env, monkeypatch):
    from business.config.constants import ServiceType, Status
    from business.content.daily_content import create_rate_content_draft
    from business.records.records import get_content_record
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

    monkeypatch.setattr("business.content.daily_content.generate_content", fake_generate_content)

    payload = _call_investment_json_handler(
        monkeypatch,
        lambda: InvestmentDailyContentGenerateHandler().POST(content_id),
    )

    assert payload["status"] == "success"
    assert payload["content_id"] == content_id
    assert payload["generation_status"] == "started"
    assert get_content_record(content_id).service_type == ServiceType.RATE
    assert get_content_record(content_id).status == Status.GENERATING


def test_web_daily_content_create_binds_session_admin_not_body_operator(business_env, monkeypatch):
    from business.audit.audit_service import list_operation_audits
    from business.accounts.auth_service import authenticate_admin, create_admin_session, create_admin_user
    from business.schema.db import connect
    from channel.web import web_channel
    from channel.web.web_channel import InvestmentDailyContentHandler

    create_admin_user("content-session", "content-pass", role="content_operator")
    admin = authenticate_admin("content-session", "content-pass")
    assert admin is not None
    token = create_admin_session(admin)
    monkeypatch.setattr(web_channel.web, "cookies", lambda: {"cow_investment_session": token})
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(web_channel.web.ctx, "headers", [], raising=False)
    monkeypatch.setattr(
        web_channel.web,
        "data",
        lambda: json.dumps({
            "service_type": "rate",
            "source_text": "content source",
            "operator": "spoofed-content-operator",
            "expires_at": "2026-06-05T00:00",
        }).encode("utf-8"),
    )

    payload = json.loads(InvestmentDailyContentHandler().POST())

    assert payload["status"] == "success"
    content_id = payload["content_id"]
    with connect() as conn:
        row = conn.execute(
            text(
                "select operator, created_by_admin_id, created_by_username, created_by_role, "
                "updated_by_admin_id, updated_by_username, updated_by_role, expires_at "
                "from content_records where content_id = :content_id"
            ),
            {"content_id": content_id},
        ).fetchone()
    assert row is not None
    assert row.operator == "content-session"
    assert row.created_by_admin_id == admin.id
    assert row.created_by_username == "content-session"
    assert row.created_by_role == "content_operator"
    assert row.updated_by_admin_id == admin.id
    assert row.updated_by_username == "content-session"
    assert row.updated_by_role == "content_operator"
    assert row.expires_at == "2026-06-04T16:00:00.000000+00:00"
    audit = list_operation_audits(limit=1, target_type="daily_content", target_id=content_id)[0]
    assert audit.action == "content.create"
    assert audit.operator == "content-session"
    assert audit.operator_admin_id == admin.id
    assert audit.operation_category == "content"


def test_web_daily_content_get_returns_current_effective_content(business_env, tmp_path, monkeypatch):
    from pathlib import Path

    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, set_content_effective
    from business.schema.storage import get_storage_dirs
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
    current_output = Path(payload["current_effective"]["output_image"])
    assert current_output != image
    assert current_output.is_file()
    assert current_output.read_bytes() == b"png"
    assert current_output.resolve().is_relative_to(get_storage_dirs()["files"].resolve())
    assert payload["current_effective"]["operator"] == "operator-current"


def test_web_daily_content_get_returns_history_artifacts(business_env, tmp_path, monkeypatch):
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, update_generation_success
    from channel.web.web_channel import InvestmentDailyContentHandler

    image = tmp_path / "rate-history.png"
    image.write_bytes(b"history-png")
    content_id = create_content_draft(
        ServiceType.RATE,
        source_text="history source text",
        operator="operator-history",
        effective_date="2026-06-03",
    )
    update_generation_success(content_id, "history generated text", str(image))

    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentDailyContentHandler().GET,
        params={"service_type": "rate", "limit": "50"},
    )

    history = next(content for content in payload["contents"] if content["content_id"] == content_id)
    assert history["source_text"] == "history source text"
    assert history["generated_text"] == "history generated text"
    assert history["output_artifacts"]
    assert history["output_artifacts"][0]["artifact_role"] == "output_image"
    assert history["output_artifacts"][0]["file_path"] == history["output_image"]


def test_set_content_effective_archives_external_output_image(business_env, tmp_path):
    from pathlib import Path

    from business.config.constants import ServiceType, Status
    from business.content.daily_content import create_content_draft, set_content_effective
    from business.records.records import get_content_record, list_output_files
    from business.schema.storage import get_storage_dirs

    image = tmp_path / "rate_card.png"
    image.write_bytes(b"legacy-rate-card")
    content_id = create_content_draft(
        ServiceType.RATE,
        source_text="legacy image",
        operator="operator-effective",
        effective_date="2026-06-04",
    )

    set_content_effective(content_id, str(image), operator="operator-effective")

    record = get_content_record(content_id)
    artifacts = list_output_files(content_id)
    assert record.status == Status.EFFECTIVE
    assert record.output_image != str(image)
    assert Path(record.output_image).is_file()
    assert Path(record.output_image).read_bytes() == b"legacy-rate-card"
    assert Path(record.output_image).resolve().is_relative_to(get_storage_dirs()["files"].resolve())
    output_parts = Path(record.output_image).parts
    files_index = output_parts.index("files")
    assert output_parts[files_index + 1 : files_index + 5] == (
        str(ServiceType.RATE),
        "2026-06-04",
        "content",
        content_id,
    )
    assert Path(record.output_image).name.startswith("output_image_rate_card_")
    assert artifacts
    assert artifacts[0]["artifact_role"] == "output_image"
    assert artifacts[0]["file_path"] == record.output_image


def test_list_content_records_filters_by_effective_date(business_env):
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft
    from business.records.records import list_content_records

    create_content_draft(ServiceType.RATE, source_text="old rate", effective_date="2026-05-28")
    expected_id = create_content_draft(ServiceType.RATE, source_text="today rate", effective_date="2026-05-29")
    create_content_draft(ServiceType.CONVERTIBLE_BOND, source_text="today cb", effective_date="2026-05-29")

    records = list_content_records(
        service_type=ServiceType.RATE,
        effective_date="2026-05-29",
    )

    assert [record.content_id for record in records] == [expected_id]
    assert {record.effective_date for record in records} == {"2026-05-29"}


def test_web_content_handlers_accept_effective_date_filter(business_env, monkeypatch):
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft
    from channel.web.web_channel import InvestmentContentRecordsHandler, InvestmentDailyContentHandler

    old_id = create_content_draft(ServiceType.RATE, source_text="old rate", effective_date="2026-05-28")
    expected_id = create_content_draft(ServiceType.RATE, source_text="today rate", effective_date="2026-05-29")

    daily_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentDailyContentHandler().GET,
        params={"service_type": "rate", "limit": "20", "effective_date": "2026-05-29"},
    )
    records_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentContentRecordsHandler().GET,
        params={"service_type": "rate", "limit": "20", "effective_date": "2026-05-29"},
    )

    assert [content["content_id"] for content in daily_payload["contents"]] == [expected_id]
    assert [record["content_id"] for record in records_payload["records"]] == [expected_id]
    assert old_id not in {content["content_id"] for content in daily_payload["contents"]}


def test_web_content_handlers_sanitize_limit_and_reject_unmatched_service_type(business_env, monkeypatch):
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft
    from channel.web.web_channel import InvestmentContentRecordsHandler, InvestmentDailyContentHandler

    rate_id = create_content_draft(ServiceType.RATE, source_text="rate", effective_date="2026-05-29")
    cb_id = create_content_draft(ServiceType.CONVERTIBLE_BOND, source_text="cb", effective_date="2026-05-29")

    invalid_limit_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentDailyContentHandler().GET,
        params={"service_type": "rate", "limit": "bad"},
    )
    negative_limit_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentContentRecordsHandler().GET,
        params={"service_type": "rate", "limit": "-10"},
    )
    oversized_limit_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentDailyContentHandler().GET,
        params={"service_type": "rate", "limit": "9999"},
    )
    unmatched_daily_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentDailyContentHandler().GET,
        params={"service_type": "unknown-service", "limit": "20"},
    )
    unmatched_records_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentContentRecordsHandler().GET,
        params={"service_type": "unknown-service", "limit": "20"},
    )

    assert invalid_limit_payload["status"] == "success"
    assert [content["content_id"] for content in invalid_limit_payload["contents"]] == [rate_id]
    assert negative_limit_payload["status"] == "success"
    assert len(negative_limit_payload["records"]) == 1
    assert oversized_limit_payload["status"] == "success"
    assert [content["content_id"] for content in oversized_limit_payload["contents"]] == [rate_id]
    assert unmatched_daily_payload["contents"] == []
    assert unmatched_daily_payload["current_effective"] is None
    assert unmatched_records_payload["records"] == []
    assert cb_id not in {content["content_id"] for content in oversized_limit_payload["contents"]}


def test_web_records_handlers_sanitize_invalid_limit(business_env, monkeypatch):
    from business.audit.audit_service import record_operation_audit
    from business.config.constants import ServiceType
    from business.records.records import create_request_record
    from channel.web.web_channel import InvestmentOperationAuditsHandler, InvestmentRequestRecordsHandler

    request_id = create_request_record("openid", "利率", ServiceType.RATE)
    audit_id = record_operation_audit("created", "request", request_id, operator="tester")

    records_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentRequestRecordsHandler().GET,
        params={"limit": "bad"},
    )
    audits_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentOperationAuditsHandler().GET,
        params={"limit": "bad"},
    )

    assert records_payload["status"] == "success"
    assert [record["request_id"] for record in records_payload["records"]] == [request_id]
    assert audits_payload["status"] == "success"
    assert [audit["audit_id"] for audit in audits_payload["audits"]] == [audit_id]


def test_request_records_page_returns_total_offset_and_api_pagination(business_env, monkeypatch):
    from business.config.constants import ServiceType
    from business.schema.db import connect
    from business.records.records import create_request_record, list_request_records_page
    from channel.web.web_channel import InvestmentRequestRecordsHandler

    request_ids = [
        create_request_record(f"openid-page-{index}", f"分页请求 {index}", ServiceType.RATE)
        for index in range(5)
    ]
    with connect() as conn:
        for index, request_id in enumerate(request_ids):
            conn.execute(
                text(
                    "update request_records "
                    "set created_at = :created_at, updated_at = :created_at "
                    "where request_id = :request_id"
                ),
                {"created_at": f"2026-05-29T00:0{index}:00+00:00", "request_id": request_id},
            )

    records, total = list_request_records_page(page=2, page_size=2, service_type=ServiceType.RATE, keyword="分页请求")
    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentRequestRecordsHandler().GET,
        params={"page": "2", "page_size": "2", "service_type": "rate", "keyword": "分页请求"},
    )
    capped_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentRequestRecordsHandler().GET,
        params={"page": "1", "page_size": "9999", "service_type": "rate", "keyword": "分页请求"},
    )

    assert total == 5
    assert [record.request_id for record in records] == [request_ids[2], request_ids[1]]
    assert [record["request_id"] for record in payload["records"]] == [request_ids[2], request_ids[1]]
    assert payload["pagination"] == {"page": 2, "page_size": 2, "total": 5, "total_pages": 3}
    assert capped_payload["pagination"]["page_size"] == 200
    assert capped_payload["pagination"]["total"] == 5


def test_request_records_page_filters_by_openid_or_mobile(business_env):
    from business.config.constants import ServiceType
    from business.records.records import create_request_record, list_request_records_page, succeed_request_record
    from business.accounts.user_service import create_user

    create_user("openid-a", name="Alice", institution="Inst A", mobile="13800000000", enabled=True, allowed_services=[ServiceType.ALL])
    create_user("openid-b", name="Bob", institution="Inst B", mobile="13900000000", enabled=True, allowed_services=[ServiceType.ALL])
    first = create_request_record("openid-a", "新易盛 技术分析", ServiceType.TECHNICAL_ANALYSIS)
    second = create_request_record("openid-b", "利率", ServiceType.RATE)
    succeed_request_record(first, output_files=["/tmp/a.png"], elapsed_ms=1)
    succeed_request_record(second, output_files=["/tmp/b.png"], elapsed_ms=1)

    by_openid, total_openid = list_request_records_page(page=1, page_size=20, customer="openid-a")
    by_mobile, total_mobile = list_request_records_page(page=1, page_size=20, customer="13900000000")
    by_name, total_name = list_request_records_page(page=1, page_size=20, customer="Alice")
    by_institution, total_institution = list_request_records_page(page=1, page_size=20, customer="Inst B")

    assert total_openid == 1
    assert [record.openid for record in by_openid] == ["openid-a"]
    assert total_mobile == 1
    assert [record.openid for record in by_mobile] == ["openid-b"]
    assert total_name == 1
    assert [record.openid for record in by_name] == ["openid-a"]
    assert total_institution == 1
    assert [record.openid for record in by_institution] == ["openid-b"]


def test_request_records_page_unknown_service_returns_empty(business_env):
    from business.config.constants import ServiceType
    from business.records.records import create_request_record, list_request_records_page, succeed_request_record

    request_id = create_request_record("openid", "利率", ServiceType.RATE)
    succeed_request_record(request_id, output_files=["/tmp/rate.png"], elapsed_ms=1)

    records, total = list_request_records_page(page=1, page_size=20, service_type="unknown-service")

    assert records == []
    assert total == 0


def test_content_records_page_returns_total_and_filter_pagination(business_env, monkeypatch):
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft
    from business.schema.db import connect
    from business.records.records import list_content_records_page
    from channel.web.web_channel import InvestmentContentRecordsHandler

    content_ids = [
        create_content_draft(ServiceType.RATE, source_text=f"分页内容 {index}", effective_date="2026-05-29")
        for index in range(5)
    ]
    create_content_draft(ServiceType.CONVERTIBLE_BOND, source_text="excluded", effective_date="2026-05-29")
    with connect() as conn:
        for index, content_id in enumerate(content_ids):
            conn.execute(
                text(
                    "update content_records "
                    "set created_at = :created_at, updated_at = :created_at "
                    "where content_id = :content_id"
                ),
                {"created_at": f"2026-05-29T01:0{index}:00+00:00", "content_id": content_id},
            )

    records, total = list_content_records_page(
        page=2,
        page_size=2,
        service_type=ServiceType.RATE,
        effective_date="2026-05-29",
    )
    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentContentRecordsHandler().GET,
        params={"page": "2", "page_size": "2", "service_type": "rate", "effective_date": "2026-05-29"},
    )

    assert total == 5
    assert [record.content_id for record in records] == [content_ids[2], content_ids[1]]
    assert [record["content_id"] for record in payload["records"]] == [content_ids[2], content_ids[1]]
    assert payload["pagination"] == {"page": 2, "page_size": 2, "total": 5, "total_pages": 3}


def test_operation_audits_page_returns_total_and_filter_pagination(business_env, monkeypatch):
    from business.audit.audit_service import list_operation_audits_page, record_operation_audit
    from business.schema.db import connect
    from channel.web.web_channel import InvestmentOperationAuditsHandler

    audit_ids = [
        record_operation_audit("cache.invalidate", "investment_cache_entry", f"cache-{index}", operator="page-ops")
        for index in range(5)
    ]
    record_operation_audit("config.update", "investment_config", "excluded", operator="page-ops")
    with connect() as conn:
        for index, audit_id in enumerate(audit_ids):
            conn.execute(
                text("update operation_audits set created_at = :created_at where audit_id = :audit_id"),
                {"created_at": f"2026-05-29T02:0{index}:00+00:00", "audit_id": audit_id},
            )

    audits, total = list_operation_audits_page(
        page=2,
        page_size=2,
        action="cache.invalidate",
        operator="page-ops",
        keyword="cache-",
    )
    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentOperationAuditsHandler().GET,
        params={"page": "2", "page_size": "2", "action": "cache.invalidate", "operator": "page-ops", "keyword": "cache-"},
    )

    assert total == 5
    assert [audit.audit_id for audit in audits] == [audit_ids[2], audit_ids[1]]
    assert [audit["audit_id"] for audit in payload["audits"]] == [audit_ids[2], audit_ids[1]]
    assert payload["pagination"] == {"page": 2, "page_size": 2, "total": 5, "total_pages": 3}


def test_operation_audit_records_admin_actor_fields(business_env):
    from business.audit.audit_service import AdminActor, list_operation_audits, record_operation_audit

    audit_id = record_operation_audit(
        "customer.update",
        "customer",
        "openid-actor",
        actor=AdminActor(admin_id=42, username="actor-admin", role="admin"),
        detail={"changed": ["mobile"]},
        result_status="failed",
        error_code="VALIDATION_ERROR",
        error_message="mobile invalid",
        elapsed_ms=123,
        before_state={"mobile": "13800138000"},
        after_state={"mobile": "bad-mobile"},
    )

    audit = list_operation_audits(limit=1, target_type="customer", target_id="openid-actor")[0]
    assert audit.audit_id == audit_id
    assert audit.operator == "actor-admin"
    assert audit.operator_admin_id == 42
    assert audit.operator_username == "actor-admin"
    assert audit.operator_role == "admin"
    assert audit.operation_category == "customer"
    assert audit.result_status == "failed"
    assert audit.error_code == "VALIDATION_ERROR"
    assert audit.error_message == "mobile invalid"
    assert audit.elapsed_ms == 123
    assert audit.before_state == {"mobile": "13800138000"}
    assert audit.after_state == {"mobile": "bad-mobile"}


def test_cache_entries_page_returns_total_and_filter_pagination(business_env, monkeypatch):
    from business.cache.cache_service import build_cache_key, list_cache_entries_page, write_cache_entry
    from business.config.constants import ServiceType
    from business.products.product_service import backfill_products_from_legacy_sources
    from business.schema.db import connect
    from channel.web.web_channel import InvestmentCacheHandler

    cache_keys = []
    for index in range(5):
        cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, f"30050{index}.SZ", "2026-05-29", "v1")
        cache_keys.append(cache_key)
        write_cache_entry(
            cache_key=cache_key,
            service_type=ServiceType.TECHNICAL_ANALYSIS,
            normalized_target=f"30050{index}.SZ",
            market_date="2026-05-29",
            version_fingerprint="v1",
            output_files=[f"/tmp/card-{index}.png"],
        )
    write_cache_entry(
        cache_key=build_cache_key(ServiceType.RATE, "RATE", "2026-05-29", "v1"),
        service_type=ServiceType.RATE,
        normalized_target="RATE",
        market_date="2026-05-29",
        version_fingerprint="v1",
        output_files=["/tmp/rate.png"],
    )
    with connect() as conn:
        for index, cache_key in enumerate(cache_keys):
            conn.execute(
                text("update products set updated_at = :updated_at where source_cache_key = :cache_key"),
                {"updated_at": f"2026-05-29T03:0{index}:00+00:00", "cache_key": cache_key},
            )

    entries, total = list_cache_entries_page(
        page=2,
        page_size=2,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        market_date="2026-05-29",
    )
    backfill_result = backfill_products_from_legacy_sources()
    assert backfill_result["cache_created"] == 0

    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={"page": "2", "page_size": "2", "service_type": "technical_analysis", "market_date": "2026-05-29"},
    )

    assert total == 5
    assert [entry.cache_key for entry in entries] == [cache_keys[2], cache_keys[1]]
    assert [entry["cache_key"] for entry in payload["entries"]] == [cache_keys[2], cache_keys[1]]
    assert all(entry["source_type"] == "product" for entry in payload["entries"])
    assert all(entry["product_source_type"] == "cache" for entry in payload["entries"])
    assert payload["pagination"] == {"page": 2, "page_size": 2, "total": 5, "total_pages": 3}
    assert payload["market_dates"] == ["2026-05-29"]


def test_cache_handler_without_market_date_returns_history_across_dates(business_env, monkeypatch):
    from business.cache.cache_service import build_cache_key, write_cache_entry
    from business.config.constants import ServiceType
    from business.products.product_service import backfill_products_from_legacy_sources
    from channel.web.web_channel import InvestmentCacheHandler

    write_cache_entry(
        cache_key=build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300500.SZ", "2026-05-28", "v1"),
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300500.SZ",
        market_date="2026-05-28",
        version_fingerprint="v1",
        output_files=["/tmp/card-old.png"],
    )
    write_cache_entry(
        cache_key=build_cache_key(ServiceType.RATE, "RATE", "2026-06-03", "v1"),
        service_type=ServiceType.RATE,
        normalized_target="RATE",
        market_date="2026-06-03",
        version_fingerprint="v1",
        output_files=["/tmp/rate-new.png"],
    )
    backfill_result = backfill_products_from_legacy_sources()
    assert backfill_result["cache_created"] == 0

    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={"page": "1", "page_size": "20"},
    )

    assert {entry["market_date"] for entry in payload["entries"]} == {"2026-05-28", "2026-06-03"}
    assert all(entry["source_type"] == "product" for entry in payload["entries"])
    assert payload["market_dates"] == ["2026-06-03", "2026-05-28"]
    assert payload["pagination"]["total"] == 2


def test_cache_handler_keyword_search_filters_backend_results_and_total(business_env, monkeypatch, tmp_path):
    from business.cache.cache_service import build_cache_key, list_generated_history_page, write_cache_entry
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, update_generation_success
    from business.products.product_service import backfill_products_from_legacy_sources
    from channel.web.web_channel import InvestmentCacheHandler

    write_cache_entry(
        cache_key=build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-06-05", "v1"),
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-06-05",
        version_fingerprint="v1",
        output_files=["/tmp/target-300502-card.png"],
    )
    write_cache_entry(
        cache_key=build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "601288.SH", "2026-06-05", "v1"),
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="601288.SH",
        market_date="2026-06-05",
        version_fingerprint="v1",
        output_files=["/tmp/agri-bank-card.png"],
    )
    rate_image = tmp_path / "rate-keyword-result.png"
    rate_image.write_bytes(b"rate")
    content_id = create_content_draft(
        ServiceType.RATE,
        source_text="公开市场净投放 keyword-match",
        effective_date="2026-06-05",
        operator="ops",
    )
    update_generation_success(content_id, "利率生成结果 keyword-match", str(rate_image))

    entries, total = list_generated_history_page(page=1, page_size=20, keyword="keyword-match")
    backfill_result = backfill_products_from_legacy_sources()
    assert backfill_result["cache_created"] == 0
    assert backfill_result["content_created"] == 1

    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={"page": "1", "page_size": "20", "keyword": "keyword-match"},
    )

    assert total == 1
    assert [entry["content_id"] for entry in entries] == [content_id]
    assert payload["pagination"]["total"] == 1
    assert [entry["content_id"] for entry in payload["entries"]] == [content_id]
    assert payload["entries"][0]["source_type"] == "product"
    assert payload["entries"][0]["product_source_type"] == "content"

    code_entries, code_total = list_generated_history_page(page=1, page_size=20, keyword="300502")
    assert code_total == 1
    assert code_entries[0]["normalized_target"] == "300502.SZ"

    code_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={"page": "1", "page_size": "20", "keyword": "300502"},
    )
    assert code_payload["pagination"]["total"] == 1
    assert code_payload["entries"][0]["normalized_target"] == "300502.SZ"
    assert code_payload["entries"][0]["source_type"] == "product"


def test_cache_handler_merges_product_rows_and_dedupes_legacy_sources(business_env, monkeypatch, tmp_path):
    from business.cache.cache_service import build_cache_key, write_cache_entry
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, update_generation_success
    from business.products import product_service
    from channel.web.web_channel import InvestmentCacheHandler

    product_cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-06-24", "v1")
    product = product_service.create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="新易盛",
        business_date="2026-06-24",
        version_fingerprint="v1",
        source_request_id="request-product",
        source_cache_key=product_cache_key,
        source_type="cache",
        output_files=["/tmp/product-card.png"],
    )
    write_cache_entry(
        cache_key=product_cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-06-24",
        version_fingerprint="v1",
        output_files=["/tmp/legacy-card.png"],
        artifact_owner_id="request-legacy",
    )
    legacy_cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "601288.SH", "2026-06-24", "v1")
    write_cache_entry(
        cache_key=legacy_cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="601288.SH",
        market_date="2026-06-24",
        version_fingerprint="v1",
        output_files=["/tmp/legacy-only-card.png"],
        artifact_owner_id="request-legacy-only",
    )
    backfill_result = product_service.backfill_products_from_legacy_sources()
    assert backfill_result["cache_created"] == 0

    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={"page": "1", "page_size": "20", "service_type": "technical_analysis", "market_date": "2026-06-24"},
    )

    assert payload["status"] == "success"
    assert payload["pagination"]["total"] == 2
    assert [entry["cache_key"] for entry in payload["entries"]].count(product_cache_key) == 1
    product_entry = next(entry for entry in payload["entries"] if entry["cache_key"] == product_cache_key)
    assert product_entry["source_type"] == "product"
    assert product_entry["product_id"] != product["product_id"]
    assert product_entry["service_type"] == "technical_analysis"
    assert product_entry["business_type"] == "technical_analysis"
    assert product_entry["normalized_target"] == "300502.SZ"
    assert product_entry["target_key"] == "300502.SZ"
    assert product_entry["market_date"] == "2026-06-24"
    assert product_entry["business_date"] == "2026-06-24"
    assert product_entry["artifact_owner_id"] == "request-legacy"
    assert product_entry["output_files"] == ["/tmp/legacy-card.png"]
    legacy_entry = next(entry for entry in payload["entries"] if entry["cache_key"] == legacy_cache_key)
    assert legacy_entry["source_type"] == "product"
    assert legacy_entry["product_source_type"] == "cache"
    assert legacy_entry["source_cache_key"] == legacy_cache_key
    assert legacy_entry["artifact_owner_id"] == "request-legacy-only"

    rate_image = tmp_path / "rate-legacy.png"
    rate_image.write_bytes(b"rate")
    content_id = create_content_draft(
        ServiceType.RATE,
        source_text="公开市场净投放",
        effective_date="2026-06-24",
        operator="ops",
    )
    update_generation_success(content_id, "利率生成结果", str(rate_image))
    content_product = product_service.create_product(
        business_type="rate",
        target_key="RATE",
        target_label="利率内容",
        business_date="2026-06-24",
        version_fingerprint="v1",
        source_content_id=content_id,
        source_type="content",
        output_files=["/tmp/product-rate-card.png"],
    )

    content_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={"page": "1", "page_size": "20", "service_type": "rate", "market_date": "2026-06-24"},
    )

    assert content_payload["status"] == "success"
    assert content_payload["pagination"]["total"] == 1
    assert content_payload["entries"][0]["source_type"] == "product"
    assert content_payload["entries"][0]["product_id"] == content_product["product_id"]
    assert content_payload["entries"][0]["content_id"] == content_id
    assert content_payload["entries"][0]["artifact_owner_id"] == content_id

    product_service.invalidate_product(product_entry["product_id"])
    invalidated_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={"page": "1", "page_size": "20", "service_type": "technical_analysis", "market_date": "2026-06-24"},
    )

    assert invalidated_payload["status"] == "success"
    assert invalidated_payload["pagination"]["total"] == 1
    assert invalidated_payload["entries"][0]["cache_key"] == legacy_cache_key
    assert invalidated_payload["entries"][0]["source_type"] == "product"

    invalidated_visible_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={
            "page": "1",
            "page_size": "20",
            "service_type": "technical_analysis",
            "market_date": "2026-06-24",
            "include_invalidated": "1",
        },
    )

    assert invalidated_visible_payload["status"] == "success"
    assert invalidated_visible_payload["pagination"]["total"] == 3
    invalidated_product_entry = next(
        entry for entry in invalidated_visible_payload["entries"] if entry["product_id"] == product["product_id"]
    )
    assert invalidated_product_entry["source_type"] == "product"
    assert invalidated_product_entry["status"] == "invalidated"
    invalidated_current_entry = next(
        entry for entry in invalidated_visible_payload["entries"] if entry["product_id"] == product_entry["product_id"]
    )
    assert invalidated_current_entry["source_type"] == "product"
    assert invalidated_current_entry["status"] == "invalidated"
    assert any(
        entry["cache_key"] == legacy_cache_key and entry["source_type"] == "product"
        for entry in invalidated_visible_payload["entries"]
    )


def test_cache_handler_keyword_search_reads_product_cache_payload(business_env, monkeypatch):
    from business.cache.cache_service import build_cache_key, write_cache_entry
    from business.config.constants import ServiceType
    from business.products import product_service
    from channel.web.web_channel import InvestmentCacheHandler

    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-06-24", "v1")
    product_service.create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="新易盛",
        business_date="2026-06-24",
        version_fingerprint="v1",
        source_cache_key=cache_key,
        source_type="cache",
        output_files=["/tmp/product-card.png"],
    )
    write_cache_entry(
        cache_key=cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-06-24",
        version_fingerprint="v1",
        output_files=["/tmp/legacy-only-keyword-card.png"],
        artifact_owner_id="legacy-only-keyword-owner",
    )

    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={
            "page": "1",
            "page_size": "20",
            "service_type": "technical_analysis",
            "market_date": "2026-06-24",
            "keyword": "legacy-only-keyword",
        },
    )

    assert payload["status"] == "success"
    assert payload["pagination"]["total"] == 1
    assert payload["entries"][0]["source_type"] == "product"
    assert payload["entries"][0]["source_cache_key"] == cache_key
    assert payload["entries"][0]["output_files"] == ["/tmp/legacy-only-keyword-card.png"]

    product_keyword_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={
            "page": "1",
            "page_size": "20",
            "service_type": "technical_analysis",
            "market_date": "2026-06-24",
            "keyword": "300502",
        },
    )

    assert product_keyword_payload["status"] == "success"
    assert product_keyword_payload["pagination"]["total"] == 1
    assert product_keyword_payload["entries"][0]["source_type"] == "product"
    assert product_keyword_payload["entries"][0]["cache_key"] == cache_key


def test_cache_handler_merged_products_keep_pagination_totals(business_env, monkeypatch):
    from business.cache.cache_service import build_cache_key, write_cache_entry
    from business.cache import cache_service
    from business.config.constants import ServiceType
    from business.products import product_service
    from channel.web.web_channel import InvestmentCacheHandler

    duplicate_cache_keys = []
    for index in range(3):
        cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, f"30050{index}.SZ", "2026-06-24", "v1")
        duplicate_cache_keys.append(cache_key)
        product_service.create_product(
            business_type="technical_analysis",
            target_key=f"30050{index}.SZ",
            target_label=f"产品{index}",
            business_date="2026-06-24",
            version_fingerprint="v1",
            source_cache_key=cache_key,
            source_type="cache",
            output_files=[f"/tmp/product-card-{index}.png"],
        )
        write_cache_entry(
            cache_key=cache_key,
            service_type=ServiceType.TECHNICAL_ANALYSIS,
            normalized_target=f"30050{index}.SZ",
            market_date="2026-06-24",
            version_fingerprint="v1",
            output_files=[f"/tmp/legacy-card-{index}.png"],
        )
    for index in range(2):
        write_cache_entry(
            cache_key=build_cache_key(ServiceType.TECHNICAL_ANALYSIS, f"60128{index}.SH", "2026-06-24", "v1"),
            service_type=ServiceType.TECHNICAL_ANALYSIS,
            normalized_target=f"60128{index}.SH",
            market_date="2026-06-24",
            version_fingerprint="v1",
            output_files=[f"/tmp/legacy-only-card-{index}.png"],
        )
    backfill_result = product_service.backfill_products_from_legacy_sources()
    assert backfill_result["cache_created"] == 0
    for index in range(4):
        product_service.create_product(
            business_type="technical_analysis",
            target_key=f"68800{index}.SH",
            target_label=f"仅产品{index}",
            business_date="2026-06-24",
            version_fingerprint="v1",
            output_files=[f"/tmp/product-only-card-{index}.png"],
        )

    original_list_products_page = product_service.list_products_cache_history_page
    product_page_sizes = []

    def guarded_list_products_page(*args, **kwargs):
        product_page_sizes.append(int(kwargs.get("page_size") or 0))
        assert int(kwargs.get("page_size") or 0) <= 6
        return original_list_products_page(*args, **kwargs)

    monkeypatch.setattr(product_service, "list_products_cache_history_page", guarded_list_products_page)
    monkeypatch.setattr(
        cache_service,
        "list_generated_history_page",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy full-fetch path should not be used")),
    )

    page_one = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={"page": "1", "page_size": "2", "service_type": "technical_analysis", "market_date": "2026-06-24"},
    )
    page_three = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={"page": "3", "page_size": "2", "service_type": "technical_analysis", "market_date": "2026-06-24"},
    )
    page_two = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={"page": "2", "page_size": "2", "service_type": "technical_analysis", "market_date": "2026-06-24"},
    )

    assert page_one["status"] == "success"
    assert page_one["pagination"] == {"page": 1, "page_size": 2, "total": 9, "total_pages": 5}
    assert len(page_one["entries"]) == 2
    assert page_two["status"] == "success"
    assert page_two["pagination"] == {"page": 2, "page_size": 2, "total": 9, "total_pages": 5}
    assert len(page_two["entries"]) == 2
    assert page_three["status"] == "success"
    assert page_three["pagination"] == {"page": 3, "page_size": 2, "total": 9, "total_pages": 5}
    assert len(page_three["entries"]) == 2
    assert max(product_page_sizes) <= 6
    returned_entries = [entry for payload in (page_one, page_two, page_three) for entry in payload["entries"]]
    assert all(entry["source_type"] == "product" for entry in returned_entries)
    for cache_key in duplicate_cache_keys:
        assert [entry["source_cache_key"] for entry in returned_entries].count(cache_key) <= 1


def test_cache_handler_product_page_uses_updated_order_for_bounded_fetch(business_env, monkeypatch):
    from business.config.constants import ServiceType
    from business.products import product_service
    from channel.web.web_channel import InvestmentCacheHandler

    products = []
    for index in range(3):
        products.append(
            product_service.create_product(
                business_type="technical_analysis",
                target_key=f"30050{index}.SZ",
                target_label=f"产品{index}",
                business_date="2026-06-24",
                version_fingerprint="v1",
                output_files=[f"/tmp/product-card-{index}.png"],
            )
        )

    product_service.increment_product_hit(products[0]["product_id"])

    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={"page": "1", "page_size": "1", "service_type": str(ServiceType.TECHNICAL_ANALYSIS), "market_date": "2026-06-24"},
    )

    assert payload["status"] == "success"
    assert payload["pagination"]["total"] == 3
    assert payload["entries"][0]["source_type"] == "product"
    assert payload["entries"][0]["product_id"] == products[0]["product_id"]


def test_cache_handler_clamps_excessive_page_for_merged_history(business_env, monkeypatch):
    from channel.web.web_channel import InvestmentCacheHandler

    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={"page": "999999", "page_size": "1", "service_type": "technical_analysis"},
    )

    assert payload["status"] == "success"
    assert payload["pagination"]["page"] == 500


def test_artifact_package_tree_groups_shared_technical_outputs_by_cache_key(business_env, monkeypatch, tmp_path):
    from business.cache.cache_service import build_cache_key
    from business.config.constants import ServiceType
    from business.products.product_service import create_product
    from business.schema.db import connect
    from business.records.records import create_request_record, get_request_record, list_artifact_packages_page, succeed_request_record
    from business.schema.tables import investment_products
    from channel.web.web_channel import InvestmentArtifactPackagesHandler

    signal = tmp_path / "signal-card.png"
    chart = tmp_path / "main-chart.png"
    report = tmp_path / "report.md"
    signal.write_bytes(b"signal")
    chart.write_bytes(b"chart")
    report.write_text("markdown report", encoding="utf-8")

    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-06-08", "version-a")
    first_request_id = create_request_record(
        "openid-a",
        "新易盛 技术分析",
        ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        stock_code="300502.SZ",
        stock_name="新易盛",
        market_date="2026-06-08",
        cache_key=cache_key,
    )
    succeed_request_record(
        first_request_id,
        output_files=[str(signal), str(chart), str(report)],
        elapsed_ms=120,
        artifact_roles={str(signal): "signal_card", str(chart): "main_chart", str(report): "markdown_report"},
        normalized_target="300502.SZ",
        stock_code="300502.SZ",
        stock_name="新易盛",
        market_date="2026-06-08",
        cache_key=cache_key,
    )
    first_record = get_request_record(first_request_id)
    second_request_id = create_request_record(
        "openid-b",
        "300502.SZ 技术分析",
        ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        stock_code="300502.SZ",
        stock_name="新易盛",
        market_date="2026-06-08",
        cache_key=cache_key,
        cache_hit=True,
    )
    succeed_request_record(
        second_request_id,
        output_files=first_record.output_files,
        elapsed_ms=5,
        cache_hit=True,
        normalized_target="300502.SZ",
        stock_code="300502.SZ",
        stock_name="新易盛",
        market_date="2026-06-08",
        cache_key=cache_key,
    )
    product = create_product(
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        target_key="300502.SZ",
        target_label="300502.SZ 新易盛",
        business_date="2026-06-08",
        version_fingerprint="version-a",
        source_type="cache",
        source_request_id=first_request_id,
        source_cache_key=cache_key,
        output_files=first_record.output_files,
        effective_at="2026-06-08T08:00:00+00:00",
    )
    with connect() as conn:
        conn.execute(
            investment_products.update()
            .where(investment_products.c.product_id == product["product_id"])
            .values(created_at="2026-06-08T08:00:00+00:00", updated_at="2026-06-08T08:00:00+00:00")
        )

    packages, total = list_artifact_packages_page(
        page=1,
        page_size=20,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        start_date="2026-06-08",
        end_date="2026-06-08",
    )
    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentArtifactPackagesHandler().GET,
        params={"service_type": "technical_analysis", "start_date": "2026-06-08", "end_date": "2026-06-08"},
    )

    assert total == 1
    package = packages[0]
    assert package["package_id"] == product["product_id"]
    assert package["source_cache_key"] == cache_key
    assert package["display_path"] == ["技术分析", "2026-06-08", "300502.SZ 新易盛"]
    assert package["related_request_ids"] == [first_request_id]
    assert package["created_from_request_id"] == first_request_id
    assert [file["group"] for file in package["files"]] == ["output", "output", "intermediate"]
    assert all(file["virtual_path"].startswith(("output/", "intermediate/")) for file in package["files"])
    assert len([file for file in package["files"] if file.get("file_path")]) == 3
    assert all(first_request_id not in file["virtual_path"] for file in package["files"])
    assert payload["status"] == "success"
    assert payload["pagination"]["total"] == 1
    assert payload["packages"][0]["package_id"] == product["product_id"]
    assert payload["packages"][0]["source_cache_key"] == cache_key
    assert payload["tree"][0]["dir"] == "2026-06-08"
    assert payload["tree"][0]["children"][0]["dir"] == "300502.SZ 新易盛"
    assert [group["dir"] for group in payload["tree"][0]["children"][0]["children"]] == ["output", "intermediate"]


def test_artifact_packages_include_unified_products_without_legacy_cache_or_content(business_env, tmp_path):
    from business.products.product_service import create_product
    from business.records.records import list_artifact_packages_page

    image = tmp_path / "card.png"
    report = tmp_path / "report.md"
    image.write_text("image", encoding="utf-8")
    report.write_text("report", encoding="utf-8")
    product = create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="300502 新易盛",
        business_date="2026-06-24",
        version_fingerprint="v1",
        output_files=[str(image), str(report)],
        source_type="request",
        source_request_id="req-product",
    )

    packages, total = list_artifact_packages_page(
        service_type="technical_analysis",
        start_date="2026-06-24",
        end_date="2026-06-24",
    )

    assert total == 1
    assert packages[0]["package_id"] == product["product_id"]
    assert packages[0]["source_type"] == "product"
    assert packages[0]["file_count"] == 2


def test_artifact_packages_do_not_query_cache_entries_for_product_sources(business_env, tmp_path):
    from business.config.constants import ServiceType
    from business.products.product_service import create_product
    from business.records import records

    output = tmp_path / "artifact-product-only.png"
    output.write_text("artifact", encoding="utf-8")
    create_product(
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        target_key="300502.SZ",
        target_label="300502.SZ",
        business_date="2026-06-25",
        version_fingerprint="vf-artifact-product-only",
        status="active",
        source_cache_key="legacy-cache-key-for-display-only",
        source_type="cache",
        output_files=[str(output)],
    )

    packages, total = records.list_artifact_packages_page(service_type=ServiceType.TECHNICAL_ANALYSIS)

    assert total == 1
    assert packages[0]["source_type"] == "product"
    assert packages[0]["source_cache_key"] == "legacy-cache-key-for-display-only"
    assert packages[0]["file_count"] == 1


def test_generated_history_api_reads_products_not_cache_entries_after_cache_retirement(business_env, tmp_path):
    from business.config.constants import ServiceType
    from business.products.product_service import create_product
    from business.records.records import list_artifact_packages_page

    output = tmp_path / "history-product-only.png"
    output.write_text("history", encoding="utf-8")
    create_product(
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        target_key="300502.SZ",
        target_label="300502.SZ",
        business_date="2026-06-25",
        version_fingerprint="vf-history-product-only",
        status="active",
        source_type="request",
        source_request_id="req-history-product-only",
        output_files=[str(output)],
    )

    packages, total = list_artifact_packages_page(service_type=ServiceType.TECHNICAL_ANALYSIS)

    assert total == 1
    assert packages[0]["source_type"] == "product"
    assert packages[0]["product_id"]


def test_artifact_packages_normalize_service_aliases_for_product_sources(business_env, tmp_path):
    from business.products.product_service import create_product
    from business.records.records import list_artifact_folder_nodes, list_artifact_packages_page

    output = tmp_path / "artifact-alias-product.png"
    output.write_text("alias", encoding="utf-8")
    create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="300502.SZ",
        business_date="2026-06-25",
        version_fingerprint="vf-artifact-alias",
        status="active",
        source_cache_key="technical-analysis-alias-cache-key",
        source_type="cache",
        output_files=[str(output)],
    )

    packages, total = list_artifact_packages_page(service_type="技术分析")
    folder_packages, folder_total = list_artifact_folder_nodes(
        level="package",
        service_type="技术分析",
        date="2026-06-25",
    )

    assert total == 1
    assert packages[0]["source_cache_key"] == "technical-analysis-alias-cache-key"
    assert folder_total == 1
    assert folder_packages[0]["package_id"] == packages[0]["package_id"]


def test_product_artifact_package_dates_use_business_date_for_folder_metadata(business_env, tmp_path):
    from business.products.product_service import create_product
    from business.records.records import list_artifact_folder_nodes, list_artifact_packages_page
    from business.schema.db import connect
    from business.schema.tables import investment_products

    output = tmp_path / "product-card.png"
    output.write_text("product", encoding="utf-8")
    product = create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="300502 新易盛",
        business_date="2026-06-24",
        version_fingerprint="v1",
        output_files=[str(output)],
        source_type="request",
        source_request_id="req-product-date",
    )
    with connect() as conn:
        conn.execute(
            investment_products.update()
            .where(investment_products.c.product_id == product["product_id"])
            .values(created_at="2026-06-25T08:00:00+00:00", updated_at="2026-06-25T08:00:00+00:00")
        )

    packages, total = list_artifact_packages_page(service_type="technical_analysis")
    active_packages, active_total = list_artifact_packages_page(
        service_type="technical_analysis",
        status_category="active",
    )
    detail_packages, detail_total = list_artifact_packages_page(package_id=product["product_id"])
    folder_packages, folder_total = list_artifact_folder_nodes(
        level="package",
        service_type="technical_analysis",
        date="2026-06-24",
    )

    assert total == 1
    assert detail_total == 1
    assert folder_total == 1
    for package in (packages[0], detail_packages[0], folder_packages[0]):
        assert package["package_id"] == product["product_id"]
        assert package["market_date"] == "2026-06-24"
        assert package["generated_at"] == "2026-06-25T08:00:00+00:00"
        assert package["generated_date"] == "2026-06-25"
        assert package["business_date"] == "2026-06-24"
        assert package["display_path"][1] == "2026-06-24"


def test_artifact_browser_lists_only_product_packages_after_backfill(business_env, tmp_path):
    from business.cache.cache_service import build_cache_key, write_cache_entry
    from business.config.constants import ServiceType
    from business.products.product_service import backfill_products_from_legacy_sources
    from business.records.records import list_artifact_packages_page

    output = tmp_path / "legacy-card.png"
    output.write_text("legacy", encoding="utf-8")
    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-06-20", "v1")
    write_cache_entry(
        cache_key=cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-06-20",
        version_fingerprint="v1",
        output_files=[str(output)],
    )
    backfill_products_from_legacy_sources()

    packages, total = list_artifact_packages_page(service_type="technical_analysis")

    assert total == 1
    assert packages[0]["source_type"] == "product"
    assert packages[0]["file_count"] == 1


def test_artifact_product_package_output_files_have_path_file_urls_without_artifact_rows(business_env, tmp_path):
    from urllib.parse import quote

    from business.products.product_service import create_product
    from business.records.records import list_artifact_packages_page

    image = tmp_path / "card.png"
    report = tmp_path / "report.md"
    image.write_text("image", encoding="utf-8")
    report.write_text("report", encoding="utf-8")
    product = create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="300502 新易盛",
        business_date="2026-06-24",
        version_fingerprint="v1",
        output_files=[str(image), str(report)],
        source_type="request",
        source_request_id="req-product-files",
    )

    packages, total = list_artifact_packages_page(package_id=product["product_id"])

    output_files = [file for file in packages[0]["files"] if file.get("file_path")]
    assert total == 1
    assert len(output_files) == 2
    assert output_files[0]["file_url"] == f"/api/file?path={quote(str(image))}"
    assert output_files[1]["file_url"] == f"/api/file?path={quote(str(report))}"


def test_artifact_product_package_detail_does_not_surface_legacy_request_raw_input(business_env, tmp_path):
    from business.config.constants import ServiceType
    from business.products.product_service import create_product
    from business.records.records import create_request_record, list_artifact_packages_page, succeed_request_record

    output = tmp_path / "product-card.png"
    output.write_text("product", encoding="utf-8")
    request_id = create_request_record(
        "openid-product-input",
        "legacy request raw input",
        ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-06-24",
    )
    succeed_request_record(
        request_id,
        output_files=[str(output)],
        elapsed_ms=20,
        normalized_target="300502.SZ",
        market_date="2026-06-24",
    )
    product = create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="300502 新易盛",
        business_date="2026-06-24",
        version_fingerprint="v1",
        output_files=[str(output)],
        source_type="request",
        source_request_id=request_id,
    )

    packages, total = list_artifact_packages_page(package_id=product["product_id"])

    assert total == 1
    assert packages[0]["package_id"] == product["product_id"]
    assert [file["virtual_path"] for file in packages[0]["files"]] == ["output/product-card.png"]
    assert all(file.get("artifact_role") != "raw_input" for file in packages[0]["files"])


def test_artifact_product_packages_and_folders_default_to_active_non_expired_products(business_env, tmp_path):
    from business.products.product_service import (
        PRODUCT_STATUS_ARCHIVED,
        PRODUCT_STATUS_FAILED,
        PRODUCT_STATUS_INVALIDATED,
        create_product,
    )
    from business.records.records import list_artifact_folder_nodes, list_artifact_packages_page

    output = tmp_path / "active-card.png"
    output.write_text("active", encoding="utf-8")
    active = create_product(
        business_type="technical_analysis",
        target_key="ACTIVE.SZ",
        target_label="active product",
        business_date="2026-06-24",
        version_fingerprint="active",
        output_files=[str(output)],
    )
    for status in (PRODUCT_STATUS_INVALIDATED, PRODUCT_STATUS_ARCHIVED, PRODUCT_STATUS_FAILED):
        create_product(
            business_type="technical_analysis",
            target_key=f"{status.upper()}.SZ",
            target_label=f"{status} product",
            business_date="2026-06-24",
            version_fingerprint=status,
            status=status,
            output_files=[str(output)],
        )
    create_product(
        business_type="technical_analysis",
        target_key="EXPIRED.SZ",
        target_label="expired product",
        business_date="2026-06-24",
        version_fingerprint="expired",
        expires_at="2000-01-01T00:00:00+00:00",
        output_files=[str(output)],
    )

    packages, total = list_artifact_packages_page(service_type="technical_analysis")
    active_packages, active_total = list_artifact_packages_page(
        service_type="technical_analysis",
        status_category="active",
    )
    services, service_total = list_artifact_folder_nodes(level="service")
    dates, date_total = list_artifact_folder_nodes(level="date", service_type="technical_analysis", month="2026-06")
    folder_packages, folder_package_total = list_artifact_folder_nodes(
        level="package",
        service_type="technical_analysis",
        date="2026-06-24",
    )

    assert total == 5
    assert {package["package_id"] for package in packages} >= {active["product_id"]}
    assert active_total == 1
    assert [package["package_id"] for package in active_packages] == [active["product_id"]]
    assert service_total == 1
    assert services[0]["count"] == 5
    assert date_total == 1
    assert dates[0]["count"] == 5
    assert folder_package_total == 5
    assert active["product_id"] in {package["package_id"] for package in folder_packages}


def test_artifact_product_keyword_filters_escape_like_wildcards(business_env, tmp_path):
    from business.products.product_service import create_product
    from business.records.records import list_artifact_folder_nodes, list_artifact_packages_page

    product_file = tmp_path / "card.png"
    product_file.write_text("product", encoding="utf-8")
    percent_product = create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="needle%target",
        business_date="2026-06-24",
        version_fingerprint="v1",
        output_files=[str(product_file)],
    )
    underscore_product = create_product(
        business_type="technical_analysis",
        target_key="300503.SZ",
        target_label="needle_target",
        business_date="2026-06-24",
        version_fingerprint="v1",
        output_files=[str(product_file)],
    )
    create_product(
        business_type="technical_analysis",
        target_key="300504.SZ",
        target_label="needleAtarget",
        business_date="2026-06-24",
        version_fingerprint="v1",
        output_files=[str(product_file)],
    )

    percent_packages, percent_total = list_artifact_packages_page(
        service_type="technical_analysis",
        start_date="2026-06-24",
        end_date="2026-06-24",
        keyword="needle%",
    )
    percent_dates, percent_date_total = list_artifact_folder_nodes(
        level="date",
        service_type="technical_analysis",
        month="2026-06",
        keyword="needle%",
    )
    underscore_packages, underscore_total = list_artifact_packages_page(
        service_type="technical_analysis",
        start_date="2026-06-24",
        end_date="2026-06-24",
        keyword="needle_",
    )
    underscore_dates, underscore_date_total = list_artifact_folder_nodes(
        level="date",
        service_type="technical_analysis",
        month="2026-06",
        keyword="needle_",
    )

    assert percent_total == 1
    assert percent_packages[0]["package_id"] == percent_product["product_id"]
    assert percent_date_total == 1
    assert percent_dates[0]["count"] == 1
    assert underscore_total == 1
    assert underscore_packages[0]["package_id"] == underscore_product["product_id"]
    assert underscore_date_total == 1
    assert underscore_dates[0]["count"] == 1


def test_artifact_packages_keyword_filter_excludes_legacy_cache_when_product_is_not_visible(business_env, tmp_path):
    from business.products.product_service import create_product
    from business.records.records import list_artifact_folder_nodes, list_artifact_packages_page

    product_file = tmp_path / "product-card.png"
    product_file.write_text("product", encoding="utf-8")
    create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="300502 新易盛",
        business_date="2026-06-24",
        version_fingerprint="v1",
        output_files=[str(product_file)],
        source_type="request",
        source_cache_key="technical_analysis:300502.SZ:2026-06-24:v1",
    )

    packages, total = list_artifact_packages_page(
        service_type="technical_analysis",
        start_date="2026-06-24",
        end_date="2026-06-24",
        keyword="legacy-keyword",
    )
    dates, date_total = list_artifact_folder_nodes(
        level="date",
        service_type="technical_analysis",
        month="2026-06",
        keyword="legacy-keyword",
    )

    assert total == 0
    assert packages == []
    assert date_total == 0
    assert dates == []


def test_artifact_folder_hierarchy_includes_product_only_packages(business_env, monkeypatch, tmp_path):
    from business.products.product_service import create_product
    from business.records.records import list_artifact_folder_nodes
    from channel.web.web_channel import InvestmentArtifactFoldersHandler

    product_file = tmp_path / "product-card.png"
    product_file.write_text("product", encoding="utf-8")
    product = create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="300502 新易盛",
        business_date="2026-06-24",
        version_fingerprint="v1",
        output_files=[str(product_file)],
        source_type="request",
        source_request_id="req-product-only",
    )

    services, service_total = list_artifact_folder_nodes(level="service")
    years, year_total = list_artifact_folder_nodes(level="year", service_type="technical_analysis")
    months, month_total = list_artifact_folder_nodes(level="month", service_type="technical_analysis", year="2026")
    dates, date_total = list_artifact_folder_nodes(level="date", service_type="technical_analysis", month="2026-06")
    packages, package_total = list_artifact_folder_nodes(
        level="package",
        service_type="technical_analysis",
        date="2026-06-24",
    )
    date_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentArtifactFoldersHandler().GET,
        params={"level": "date", "service_type": "technical_analysis", "month": "2026-06"},
    )

    assert service_total == 1
    assert services[0]["key"] == "technical_analysis"
    assert year_total == 1
    assert years[0]["key"] == "2026"
    assert month_total == 1
    assert months[0]["key"] == "2026-06"
    assert date_total == 1
    assert dates[0]["key"] == "2026-06-24"
    assert package_total == 1
    assert packages[0]["package_id"] == product["product_id"]
    assert date_payload["status"] == "success"
    assert date_payload["nodes"][0]["key"] == "2026-06-24"


def test_artifact_folder_product_and_cache_same_bucket_merge_count_and_updated_at(business_env, tmp_path):
    from business.products.product_service import create_product
    from business.records.records import list_artifact_folder_nodes
    from business.schema.db import connect
    from business.schema.tables import investment_products

    product_file = tmp_path / "product-card.png"
    cache_file = tmp_path / "cache-card.png"
    product_file.write_text("product", encoding="utf-8")
    cache_file.write_text("cache", encoding="utf-8")
    product = create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="300502 新易盛",
        business_date="2026-06-24",
        version_fingerprint="v1",
        output_files=[str(product_file)],
        source_type="request",
        source_request_id="req-product-bucket",
    )
    cache_product = create_product(
        business_type="technical_analysis",
        target_key="600000.SH",
        target_label="600000.SH",
        business_date="2026-06-24",
        version_fingerprint="v1",
        source_type="cache",
        source_cache_key="technical_analysis:600000.SH:2026-06-24:v1",
        output_files=[str(cache_file)],
    )
    with connect() as conn:
        conn.execute(
            investment_products.update()
            .where(investment_products.c.product_id == product["product_id"])
            .values(updated_at="2026-06-24T09:00:00+00:00")
        )
        conn.execute(
            investment_products.update()
            .where(investment_products.c.product_id == cache_product["product_id"])
            .values(created_at="2026-06-24T08:00:00+00:00", updated_at="2026-06-24T10:00:00+00:00")
        )

    dates, total = list_artifact_folder_nodes(level="date", service_type="technical_analysis", month="2026-06")

    assert total == 1
    assert dates[0]["key"] == "2026-06-24"
    assert dates[0]["count"] == 2
    assert dates[0]["updated_at"] == "2026-06-24T10:00:00+00:00"


def test_artifact_folder_api_returns_lightweight_directory_summaries(business_env, monkeypatch):
    from business.cache.cache_service import build_cache_key, write_cache_entry
    from business.config.constants import ServiceType
    from business.products.product_service import backfill_products_from_legacy_sources
    from business.schema.db import connect
    from business.schema.tables import investment_products
    from business.records.records import list_artifact_folder_nodes
    from channel.web.web_channel import InvestmentArtifactFoldersHandler

    for market_date, target, generated_at in [
        ("2026-05-31", "MAY", "2026-04-30T08:00:00+00:00"),
        ("2026-06-07", "JUN-A", "2026-06-07T08:00:00+00:00"),
        ("2026-06-08", "JUN-B", "2026-06-09T08:00:00+00:00"),
        ("2027-01-02", "NEXT", "2027-01-03T08:00:00+00:00"),
    ]:
        cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, target, market_date, "v1")
        write_cache_entry(
            cache_key=cache_key,
            service_type=ServiceType.TECHNICAL_ANALYSIS,
            normalized_target=target,
            market_date=market_date,
            version_fingerprint="v1",
            output_files=[f"/tmp/{target}.png", f"/tmp/{target}.md"],
        )
        with connect() as conn:
            conn.execute(
                investment_products.update()
                .where(investment_products.c.source_cache_key == cache_key)
                .values(created_at=generated_at, updated_at=generated_at)
            )
    backfill_products_from_legacy_sources()

    months, month_total = list_artifact_folder_nodes(
        level="month",
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        year="2026",
    )
    days, day_total = list_artifact_folder_nodes(
        level="date",
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        month="2026-06",
    )
    packages, package_total = list_artifact_folder_nodes(
        level="package",
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        date="2026-06-08",
        page=1,
        page_size=20,
    )
    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentArtifactFoldersHandler().GET,
        params={"level": "month", "service_type": "technical_analysis", "year": "2026"},
    )
    package_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentArtifactFoldersHandler().GET,
        params={"level": "package", "service_type": "technical_analysis", "date": "2026-06-08"},
    )

    assert month_total == 2
    assert [(node["key"], node["count"]) for node in months] == [("2026-06", 2), ("2026-05", 1)]
    assert day_total == 2
    assert [(node["key"], node["count"]) for node in days] == [("2026-06-08", 1), ("2026-06-07", 1)]
    assert package_total == 1
    assert packages[0]["level"] == "package"
    assert packages[0]["source_type"] == "product"
    assert packages[0]["business_date"] == "2026-06-08"
    assert packages[0]["normalized_target"] == "JUN-B"
    assert "files" not in packages[0]
    assert payload["status"] == "success"
    assert payload["nodes"][0]["key"] == "2026-06"
    assert "packages" not in payload
    assert package_payload["status"] == "success"
    assert package_payload["nodes"][0]["source_type"] == "product"
    assert package_payload["nodes"][0]["business_date"] == "2026-06-08"
    assert package_payload["nodes"][0]["normalized_target"] == "JUN-B"


def test_artifact_folder_api_includes_daily_content_records(business_env, monkeypatch, tmp_path):
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, update_generation_success
    from business.products.product_service import backfill_products_from_legacy_sources
    from business.schema.db import connect
    from business.schema.tables import investment_daily_contents, investment_output_files
    from business.records.records import list_artifact_folder_nodes, list_artifact_packages_page
    from channel.web.web_channel import InvestmentArtifactFoldersHandler, InvestmentArtifactPackagesHandler

    rate_image = tmp_path / "rate-history.png"
    rate_image.write_bytes(b"rate-history")
    rate_content_id = create_content_draft(
        ServiceType.RATE,
        source_text="rate source text",
        effective_date="2026-06-08",
        operator="ops",
    )
    update_generation_success(rate_content_id, "rate generated text", str(rate_image))
    with connect() as conn:
        conn.execute(
            investment_daily_contents.update()
            .where(investment_daily_contents.c.content_id == rate_content_id)
            .values(updated_at="2026-06-10T08:00:00+00:00")
        )
        conn.execute(
            investment_output_files.update()
            .where(investment_output_files.c.owner_id == rate_content_id)
            .values(created_at="2026-06-10T08:00:00+00:00")
        )

    cb_image = tmp_path / "cb-history.png"
    cb_image.write_bytes(b"cb-history")
    cb_content_id = create_content_draft(
        ServiceType.CONVERTIBLE_BOND,
        source_text="cb source text",
        effective_date="2026-06-07",
        operator="ops",
    )
    update_generation_success(cb_content_id, "cb generated text", str(cb_image))
    with connect() as conn:
        conn.execute(
            investment_daily_contents.update()
            .where(investment_daily_contents.c.content_id == cb_content_id)
            .values(updated_at="2026-06-09T08:00:00+00:00")
        )
        conn.execute(
            investment_output_files.update()
            .where(investment_output_files.c.owner_id == cb_content_id)
            .values(created_at="2026-06-09T08:00:00+00:00")
        )
    backfill_products_from_legacy_sources()

    services, service_total = list_artifact_folder_nodes(level="service", page=1, page_size=20)
    rate_months, month_total = list_artifact_folder_nodes(level="month", service_type=ServiceType.RATE, year="2026")
    rate_days, day_total = list_artifact_folder_nodes(level="date", service_type=ServiceType.RATE, month="2026-06")
    rate_packages, package_total = list_artifact_folder_nodes(level="package", service_type=ServiceType.RATE, date="2026-06-08")
    detail_packages, detail_total = list_artifact_packages_page(package_id=rate_content_id, page=1, page_size=1)

    service_keys = {node["key"] for node in services}
    assert service_total == 2
    assert {"rate", "convertible_bond"} <= service_keys
    assert month_total == 1
    assert rate_months[0]["key"] == "2026-06"
    assert rate_days[0]["key"] == "2026-06-08"
    assert day_total == 1
    assert package_total == 1
    assert rate_packages[0]["source_type"] == "product"
    assert rate_packages[0]["label"] == "rate"
    assert rate_packages[0]["business_date"] == "2026-06-08"
    assert detail_total == 1
    assert detail_packages[0]["source_type"] == "product"
    assert detail_packages[0]["source_content_id"] == rate_content_id
    assert detail_packages[0]["business_date"] == "2026-06-08"
    assert detail_packages[0]["file_count"] == 1
    virtual_paths = [file["virtual_path"] for file in detail_packages[0]["files"]]
    assert virtual_paths[0].startswith("output/output_image_rate-history_")
    assert virtual_paths[0].endswith(".png")
    assert virtual_paths[1] == "intermediate/generated_text.txt"
    assert detail_packages[0]["files"][1]["content"] == "rate generated text"

    folder_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentArtifactFoldersHandler().GET,
        params={"level": "package", "service_type": "rate", "date": "2026-06-08"},
    )
    package_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentArtifactPackagesHandler().GET,
        params={"package_id": rate_content_id, "page_size": "1"},
    )

    assert folder_payload["status"] == "success"
    assert folder_payload["nodes"][0]["source_type"] == "product"
    assert package_payload["status"] == "success"
    assert package_payload["packages"][0]["source_content_id"] == rate_content_id
    assert package_payload["packages"][0]["files"][0]["file_url"].startswith("/api/file?path=")
    assert cb_content_id


def test_artifact_history_includes_unused_daily_content_without_product_backfill(business_env, tmp_path):
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, set_content_effective, update_generation_success
    from business.records.business_records import list_artifact_folder_nodes, list_artifact_packages_page

    active_image = tmp_path / "rate-active.png"
    unused_image = tmp_path / "rate-unused.png"
    active_image.write_bytes(b"active")
    unused_image.write_bytes(b"unused")

    active_id = create_content_draft(ServiceType.RATE, source_text="rate active", effective_date="2026-06-26")
    unused_id = create_content_draft(ServiceType.RATE, source_text="rate unused", effective_date="2026-06-26")
    set_content_effective(active_id, str(active_image), effective_date="2026-06-26", operator="ops")
    update_generation_success(unused_id, "unused generated text", str(unused_image))

    packages, total = list_artifact_packages_page(
        page=1,
        page_size=20,
        service_type=ServiceType.RATE,
        start_date="2026-06-26",
        end_date="2026-06-26",
    )
    nodes, node_total = list_artifact_folder_nodes(
        level="package",
        service_type=ServiceType.RATE,
        date="2026-06-26",
        page=1,
        page_size=20,
    )

    assert total == 2
    assert any(item.get("source_content_id") == active_id for item in packages)
    assert any(item.get("package_id") == unused_id for item in packages)
    assert {item["display_status"] for item in packages} == {"active", "unused"}
    assert {item["display_status_label"] for item in packages} == {"有效", "未使用"}
    assert node_total == 2
    assert any(item.get("source_content_id") == active_id for item in nodes)
    assert any(item.get("package_id") == unused_id for item in nodes)


def test_artifact_history_status_category_filters_all_sources(business_env, tmp_path):
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, invalidate_content, update_generation_success
    from business.products.product_service import PRODUCT_STATUS_ACTIVE, PRODUCT_STATUS_INVALIDATED, create_product
    from business.records.business_records import list_artifact_folder_nodes, list_artifact_packages_page

    product_file = tmp_path / "ta-active.png"
    unused_file = tmp_path / "rate-unused.png"
    invalidated_file = tmp_path / "rate-invalidated.png"
    product_file.write_bytes(b"product")
    unused_file.write_bytes(b"unused")
    invalidated_file.write_bytes(b"invalidated")

    active_product = create_product(
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        target_key="300502.SZ",
        target_label="300502 新易盛",
        business_date="2026-06-26",
        version_fingerprint="v1",
        status=PRODUCT_STATUS_ACTIVE,
        output_files=[str(product_file)],
    )
    invalidated_product = create_product(
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        target_key="600000.SH",
        target_label="600000 浦发银行",
        business_date="2026-06-26",
        version_fingerprint="v1",
        status=PRODUCT_STATUS_INVALIDATED,
        output_files=[str(product_file)],
    )
    unused_id = create_content_draft(ServiceType.RATE, source_text="rate unused", effective_date="2026-06-26")
    invalidated_id = create_content_draft(ServiceType.RATE, source_text="rate invalidated", effective_date="2026-06-26")
    update_generation_success(unused_id, "unused generated text", str(unused_file))
    update_generation_success(invalidated_id, "invalidated generated text", str(invalidated_file))
    invalidate_content(invalidated_id, operator="ops")

    active_packages, active_total = list_artifact_packages_page(
        page=1,
        page_size=20,
        start_date="2026-06-26",
        end_date="2026-06-26",
        status_category="active",
    )
    unused_nodes, unused_total = list_artifact_folder_nodes(
        level="package",
        date="2026-06-26",
        page=1,
        page_size=20,
        status_category="unused",
    )
    invalidated_packages, invalidated_total = list_artifact_packages_page(
        page=1,
        page_size=20,
        start_date="2026-06-26",
        end_date="2026-06-26",
        status_category="invalid",
    )

    assert active_total == 1
    assert active_packages[0]["package_id"] == active_product["product_id"]
    assert active_packages[0]["display_status_label"] == "有效"
    assert unused_total == 1
    assert unused_nodes[0]["package_id"] == unused_id
    assert unused_nodes[0]["display_status_label"] == "未使用"
    assert invalidated_total == 2
    assert {item["package_id"] for item in invalidated_packages} == {
        invalidated_product["product_id"],
        invalidated_id,
    }
    assert {item["display_status_label"] for item in invalidated_packages} == {"失效"}


def test_artifact_history_marks_technical_analysis_product_invalid_after_market_update(
    business_env,
    tmp_path,
    monkeypatch,
):
    import business.cache.cache_policy as cache_policy

    from business.config.constants import ServiceType
    from business.products.product_service import create_product
    from business.records.business_records import list_artifact_folder_nodes, list_artifact_packages_page

    output = tmp_path / "ta-old.png"
    output.write_bytes(b"old-ta")
    product = create_product(
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        target_key="600519.SH",
        target_label="600519 贵州茅台",
        business_date="2026-06-25",
        version_fingerprint="v1",
        source_type="cache",
        source_cache_key="technical_analysis:600519.SH:2026-06-25:v1",
        output_files=[str(output)],
    )
    monkeypatch.setattr(cache_policy, "technical_analysis_cache_expired_after_close", lambda *_args, **_kwargs: True)

    packages, total = list_artifact_packages_page(
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        package_id=product["product_id"],
    )
    dates, date_total = list_artifact_folder_nodes(
        level="date",
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        month="2026-06",
        status_category="invalid",
    )

    assert total == 1
    assert packages[0]["display_status"] == "invalid"
    assert packages[0]["display_status_label"] == "失效"
    assert date_total == 1
    assert dates[0]["key"] == "2026-06-25"


def test_daily_content_new_effective_archives_previous_effective_across_dates(business_env, tmp_path):
    from business.config.constants import ServiceType, Status
    from business.content.daily_content import create_content_draft, set_content_effective
    from business.products.product_service import PRODUCT_STATUS_ARCHIVED, PRODUCT_STATUS_ACTIVE, list_products_page
    from business.records.business_records import list_artifact_packages_page
    from business.records.records import get_content_record

    first_image = tmp_path / "first-rate.png"
    second_image = tmp_path / "second-rate.png"
    first_image.write_bytes(b"first")
    second_image.write_bytes(b"second")
    first_id = create_content_draft(ServiceType.RATE, source_text="first", effective_date="2026-06-25")
    second_id = create_content_draft(ServiceType.RATE, source_text="second", effective_date="2026-06-26")

    set_content_effective(first_id, str(first_image), effective_date="2026-06-25", operator="ops")
    set_content_effective(second_id, str(second_image), effective_date="2026-06-26", operator="ops")

    products, total = list_products_page(include_invalidated=True, business_type=str(ServiceType.RATE))
    by_content_id = {product["source_content_id"]: product for product in products}
    packages, package_total = list_artifact_packages_page(service_type=ServiceType.RATE, page_size=20)

    assert get_content_record(first_id).status == Status.ARCHIVED
    assert get_content_record(second_id).status == Status.EFFECTIVE
    assert total == 2
    assert by_content_id[first_id]["status"] == PRODUCT_STATUS_ARCHIVED
    assert by_content_id[second_id]["status"] == PRODUCT_STATUS_ACTIVE
    assert package_total == 2
    assert {item["source_content_id"]: item["display_status_label"] for item in packages} == {
        first_id: "失效",
        second_id: "有效",
    }


def test_cache_entries_api_filters_by_market_date_range(business_env, monkeypatch):
    from business.cache.cache_service import build_cache_key, list_cache_entries_page, write_cache_entry
    from business.config.constants import ServiceType
    from business.products.product_service import backfill_products_from_legacy_sources
    from channel.web.web_channel import InvestmentCacheHandler

    for market_date, target in [
        ("2026-04-30", "APR"),
        ("2026-05-01", "MAY-A"),
        ("2026-05-31", "MAY-B"),
        ("2026-06-01", "JUN"),
    ]:
        write_cache_entry(
            cache_key=build_cache_key(ServiceType.TECHNICAL_ANALYSIS, target, market_date, "v1"),
            service_type=ServiceType.TECHNICAL_ANALYSIS,
            normalized_target=target,
            market_date=market_date,
            version_fingerprint="v1",
            output_files=[f"/tmp/{target}.png"],
        )

    entries, total = list_cache_entries_page(
        page=1,
        page_size=20,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        start_date="2026-05-01",
        end_date="2026-05-31",
    )
    backfill_result = backfill_products_from_legacy_sources()
    assert backfill_result["cache_created"] == 0

    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={
            "page": "1",
            "page_size": "20",
            "service_type": "technical_analysis",
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
        },
    )

    assert total == 2
    assert {entry.market_date for entry in entries} == {"2026-05-01", "2026-05-31"}
    assert {entry["market_date"] for entry in payload["entries"]} == {"2026-05-01", "2026-05-31"}
    assert all(entry["source_type"] == "product" for entry in payload["entries"])
    assert all(entry["product_source_type"] == "cache" for entry in payload["entries"])
    assert payload["pagination"]["total"] == 2


def test_generated_content_history_api_combines_cache_and_daily_content_records(business_env, monkeypatch, tmp_path):
    from business.cache.cache_service import build_cache_key, list_generated_history_page, write_cache_entry
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, update_generation_success
    from business.products.product_service import backfill_products_from_legacy_sources
    from channel.web.web_channel import InvestmentCacheHandler

    write_cache_entry(
        cache_key=build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "601288.SH", "2026-06-01", "v1"),
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="601288.SH",
        market_date="2026-06-01",
        version_fingerprint="v1",
        output_files=["/tmp/601288-card.png"],
    )
    rate_image = tmp_path / "rate-card.png"
    rate_image.write_bytes(b"rate-card")
    rate_content_id = create_content_draft(
        ServiceType.RATE,
        source_text="rate source",
        effective_date="2026-06-05",
        operator="ops",
    )
    update_generation_success(rate_content_id, "rate generated", str(rate_image))
    cb_image = tmp_path / "cb-card.png"
    cb_image.write_bytes(b"cb-card")
    cb_content_id = create_content_draft(
        ServiceType.CONVERTIBLE_BOND,
        source_text="cb source",
        effective_date="2026-05-31",
        operator="ops",
    )
    update_generation_success(cb_content_id, "cb generated", str(cb_image))

    legacy_entries, legacy_total = list_generated_history_page(
        page=1,
        page_size=20,
        start_date="2026-06-01",
        end_date="2026-06-30",
    )
    backfill_result = backfill_products_from_legacy_sources()
    assert legacy_total == 2
    assert {entry["source_type"] for entry in legacy_entries} == {"cache", "content"}
    assert backfill_result["cache_created"] == 0
    assert backfill_result["content_created"] == 2

    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={"page": "1", "page_size": "20", "start_date": "2026-06-01", "end_date": "2026-06-30"},
    )

    assert payload["pagination"]["total"] == 2
    services = {entry["service_type"] for entry in payload["entries"]}
    assert services == {"technical_analysis", "rate"}
    assert all(entry["source_type"] == "product" for entry in payload["entries"])
    rate_entry = next(entry for entry in payload["entries"] if entry["service_type"] == "rate")
    assert rate_entry["product_source_type"] == "content"
    assert rate_entry["content_id"] == rate_content_id
    assert rate_entry["market_date"] == "2026-06-05"
    assert rate_entry["normalized_target"] == "rate"
    assert rate_entry["status"] == "active"
    assert rate_entry["generated_text"] == "rate generated"
    assert len(rate_entry["output_files"]) == 1
    assert "rate-card" in rate_entry["output_files"][0]
    assert "2026-06-05" in payload["market_dates"]


def test_generated_content_history_treats_expired_daily_content_as_invalidated(business_env, tmp_path):
    from business.cache.cache_service import list_generated_history_market_dates, list_generated_history_page
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, update_generation_success

    expired_image = tmp_path / "expired-rate.png"
    expired_image.write_bytes(b"expired-rate")
    expired_id = create_content_draft(
        ServiceType.RATE,
        source_text="expired rate",
        effective_date="2026-06-04",
        expires_at="2000-01-01T00:00",
        operator="ops",
    )
    update_generation_success(expired_id, "expired generated", str(expired_image))

    active_image = tmp_path / "active-rate.png"
    active_image.write_bytes(b"active-rate")
    active_id = create_content_draft(
        ServiceType.RATE,
        source_text="active rate",
        effective_date="2026-06-05",
        operator="ops",
    )
    update_generation_success(active_id, "active generated", str(active_image))

    active_entries, active_total = list_generated_history_page(
        page=1,
        page_size=20,
        service_type=ServiceType.RATE,
        start_date="2026-06-04",
        end_date="2026-06-05",
    )
    assert active_total == 1
    assert [entry["content_id"] for entry in active_entries] == [active_id]
    assert list_generated_history_market_dates(service_type=ServiceType.RATE) == ["2026-06-05"]

    all_entries, all_total = list_generated_history_page(
        page=1,
        page_size=20,
        service_type=ServiceType.RATE,
        start_date="2026-06-04",
        end_date="2026-06-05",
        include_invalidated=True,
    )
    assert all_total == 2
    expired_entry = next(entry for entry in all_entries if entry["content_id"] == expired_id)
    assert expired_entry["status"] == "invalidated"
    assert list_generated_history_market_dates(service_type=ServiceType.RATE, include_invalidated=True) == [
        "2026-06-05",
        "2026-06-04",
    ]


def test_generated_content_history_paginates_sources_without_bulk_fetch(business_env, tmp_path):
    import inspect

    from business.cache import cache_service as cache_service
    from business.cache.cache_service import build_cache_key, list_generated_history_page, write_cache_entry
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, update_generation_success

    for index in range(3):
        write_cache_entry(
            cache_key=build_cache_key(ServiceType.TECHNICAL_ANALYSIS, f"60128{index}.SH", "2026-06-05", "v1"),
            service_type=ServiceType.TECHNICAL_ANALYSIS,
            normalized_target=f"60128{index}.SH",
            market_date="2026-06-05",
            version_fingerprint="v1",
            output_files=[f"/tmp/60128{index}.png"],
        )
    for index in range(3):
        image = tmp_path / f"rate-{index}.png"
        image.write_bytes(f"rate-{index}".encode())
        content_id = create_content_draft(
            ServiceType.RATE,
            source_text=f"rate source {index}",
            effective_date="2026-06-05",
            operator="ops",
        )
        update_generation_success(content_id, f"rate generated {index}", str(image))

    entries, total = list_generated_history_page(page=2, page_size=2, market_date="2026-06-05")

    assert total == 6
    assert len(entries) == 2
    assert {entry["source_type"] for entry in entries}.issubset({"cache", "content"})
    source = inspect.getsource(cache_service.list_generated_history_page)
    assert "page_size=10000" not in source
    assert "offset + page_size" in source


def test_request_records_api_filters_and_prefers_mobile_customer_display(business_env, monkeypatch):
    from business.config.constants import ErrorCode, ServiceType
    from business.schema.db import connect
    from business.records.records import create_request_record, fail_request_record, succeed_request_record
    from business.accounts.user_service import create_user
    from channel.web.web_channel import InvestmentRequestRecordsHandler

    create_user(
        "openid-mobile",
        name="Mobile Customer",
        institution="Inst Mobile",
        mobile="13900000000",
        allowed_services=[ServiceType.ALL],
    )
    create_user("openid-plain", name="Plain Customer", allowed_services=[ServiceType.ALL])
    included = create_request_record("openid-mobile", "新易盛 技术分析", ServiceType.TECHNICAL_ANALYSIS)
    succeed_request_record(included, output_files=["/tmp/card.png"], elapsed_ms=18, stock_name="新易盛")
    failed = create_request_record("openid-plain", "利率", ServiceType.RATE)
    fail_request_record(failed, ErrorCode.NO_CONTENT, detail="no active content", elapsed_ms=3)

    with connect() as conn:
        conn.execute(
            text(
                "update request_records "
                "set created_at = :created_at, updated_at = :created_at "
                "where request_id = :request_id"
            ),
            {"created_at": "2026-05-29T01:00:00+00:00", "request_id": included},
        )
        conn.execute(
            text(
                "update request_records "
                "set created_at = :created_at, updated_at = :created_at "
                "where request_id = :request_id"
            ),
            {"created_at": "2026-05-30T01:00:00+00:00", "request_id": failed},
        )

    mobile_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentRequestRecordsHandler().GET,
        params={
            "service_type": "technical_analysis",
            "status": "success",
            "keyword": "13900000000",
            "start_date": "2026-05-29",
            "end_date": "2026-05-29",
            "limit": "20",
        },
    )
    openid_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentRequestRecordsHandler().GET,
        params={"keyword": "openid-plain", "limit": "20"},
    )

    assert mobile_payload["status"] == "success"
    assert [record["request_id"] for record in mobile_payload["records"]] == [included]
    assert mobile_payload["records"][0]["customer_mobile"] == "13900000000"
    assert mobile_payload["records"][0]["customer_display"] == "13900000000"
    assert mobile_payload["records"][0]["customer_name"] == "Mobile Customer"
    assert mobile_payload["records"][0]["institution"] == "Inst Mobile"
    assert [record["request_id"] for record in openid_payload["records"]] == [failed]
    assert openid_payload["records"][0]["customer_mobile"] == ""
    assert openid_payload["records"][0]["customer_display"] == "openid-plain"


def test_web_record_endpoints_filter_main_fields_with_realistic_web_input(business_env, monkeypatch):
    from business.audit.audit_service import record_operation_audit
    from business.cache.cache_service import build_cache_key, write_cache_entry
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft
    from business.products.product_service import backfill_products_from_legacy_sources
    from business.schema.db import connect
    from business.records.records import create_request_record
    from channel.web import web_channel
    from channel.web.web_channel import (
        InvestmentCacheHandler,
        InvestmentContentRecordsHandler,
        InvestmentOperationAuditsHandler,
        InvestmentRequestRecordsHandler,
    )

    rate_request_id = create_request_record("openid-rate", "利率", ServiceType.RATE)
    ta_request_id = create_request_record("openid-ta", "300502.SZ 技术分析", ServiceType.TECHNICAL_ANALYSIS)
    rate_content_id = create_content_draft(ServiceType.RATE, source_text="rate", effective_date="2026-05-31")
    cb_content_id = create_content_draft(ServiceType.CONVERTIBLE_BOND, source_text="cb", effective_date="2026-05-31")
    audit_id = record_operation_audit(
        "cache.invalidate",
        "investment_cache_entry",
        target_id="rate-cache",
        operator="rate-operator",
        detail={"reason": "rate filter check"},
    )
    excluded_audit_id = record_operation_audit(
        "config.update",
        "investment_config",
        target_id="router",
        operator="other-operator",
        detail={"reason": "other"},
    )
    rate_cache_key = build_cache_key(ServiceType.RATE, "RATE", "2026-05-31", "v1")
    ta_cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-05-31", "v1")
    write_cache_entry(
        cache_key=rate_cache_key,
        service_type=ServiceType.RATE,
        normalized_target="RATE",
        market_date="2026-05-31",
        version_fingerprint="v1",
        output_files=["/tmp/rate.png"],
    )
    write_cache_entry(
        cache_key=ta_cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-05-31",
        version_fingerprint="v1",
        output_files=["/tmp/ta.png"],
    )
    backfill_result = backfill_products_from_legacy_sources()
    assert backfill_result["cache_created"] == 0
    with connect() as conn:
        for request_id in (rate_request_id, ta_request_id):
            conn.execute(
                text(
                    "update request_records "
                    "set created_at = :created_at, updated_at = :created_at "
                    "where request_id = :request_id"
                ),
                {"created_at": "2026-05-31T01:00:00+00:00", "request_id": request_id},
            )
        for current_audit_id in (audit_id, excluded_audit_id):
            conn.execute(
                text("update operation_audits set created_at = :created_at where audit_id = :audit_id"),
                {"created_at": "2026-05-31T02:00:00+00:00", "audit_id": current_audit_id},
            )

    _login_default_investment_admin(monkeypatch)
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)

    def call(handler, params):
        monkeypatch.setattr(
            web_channel.web,
            "input",
            lambda **defaults: SimpleNamespace(**({**defaults, **params})),
        )
        return json.loads(handler())

    requests_payload = call(
        InvestmentRequestRecordsHandler().GET,
        {
            "service_type": "rate",
            "keyword": "利率",
            "start_date": "2026-05-31",
            "end_date": "2026-05-31",
            "page": "1",
            "page_size": "80",
        },
    )
    contents_payload = call(
        InvestmentContentRecordsHandler().GET,
        {"service_type": "rate", "effective_date": "2026-05-31", "page": "1", "page_size": "80"},
    )
    cache_payload = call(
        InvestmentCacheHandler().GET,
        {"service_type": "rate", "market_date": "2026-05-31", "page": "1", "page_size": "80"},
    )
    audits_payload = call(
        InvestmentOperationAuditsHandler().GET,
        {
            "action": "cache.invalidate",
            "target_type": "investment_cache_entry",
            "target_id": "rate-cache",
            "operator": "rate-operator",
            "keyword": "rate filter",
            "start_date": "2026-05-31",
            "end_date": "2026-05-31",
            "page": "1",
            "page_size": "80",
        },
    )

    assert [record["request_id"] for record in requests_payload["records"]] == [rate_request_id]
    assert ta_request_id not in {record["request_id"] for record in requests_payload["records"]}
    assert requests_payload["pagination"]["total"] == 1
    assert [record["content_id"] for record in contents_payload["records"]] == [rate_content_id]
    assert cb_content_id not in {record["content_id"] for record in contents_payload["records"]}
    assert contents_payload["pagination"]["total"] == 1
    assert [entry["cache_key"] for entry in cache_payload["entries"]] == [rate_cache_key]
    assert ta_cache_key not in {entry["cache_key"] for entry in cache_payload["entries"]}
    assert cache_payload["pagination"]["total"] == 1
    assert [audit["audit_id"] for audit in audits_payload["audits"]] == [audit_id]
    assert excluded_audit_id not in {audit["audit_id"] for audit in audits_payload["audits"]}
    assert audits_payload["pagination"]["total"] == 1


def test_internal_request_records_api_filters_by_keyword_and_date_range(business_env, monkeypatch):
    from business.config.constants import ActionType, ActorType, EntryType, ServiceType, Status
    from business.schema.db import connect
    from business.records.records import create_business_workflow_record, finish_business_workflow_record
    from channel.web.web_channel import InvestmentContentRecordsHandler, InvestmentRequestRecordsHandler

    included = create_business_workflow_record(
        entry_type=EntryType.INTERNAL_CALL,
        service_type=ServiceType.RATE,
        action_type=ActionType.GENERATE,
        actor_type=ActorType.ADMIN,
        actor_name="Alice",
        raw_input="monthly-liquidity-input",
    )
    finish_business_workflow_record(
        included,
        status=Status.SUCCESS,
        error_message="monthly-liquidity-output",
        output_files=["/tmp/rate.png"],
        elapsed_ms=12,
    )
    excluded = create_business_workflow_record(
        entry_type=EntryType.INTERNAL_CALL,
        service_type=ServiceType.RATE,
        action_type=ActionType.GENERATE,
        actor_type=ActorType.ADMIN,
        actor_name="Bob",
        raw_input="other-rate-input",
    )
    finish_business_workflow_record(
        excluded,
        status=Status.SUCCESS,
        error_message="other-rate-output",
        output_files=["/tmp/other-rate.png"],
    )

    with connect() as conn:
        conn.execute(
            text("update request_records set created_at = :created_at, updated_at = :created_at where request_id = :request_id"),
            {"created_at": "2026-05-15T02:00:00+00:00", "request_id": included},
        )
        conn.execute(
            text("update request_records set created_at = :created_at, updated_at = :created_at where request_id = :request_id"),
            {"created_at": "2026-06-15T02:00:00+00:00", "request_id": excluded},
        )

    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentRequestRecordsHandler().GET,
        params={
            "service_type": "rate",
            "entry_type": "internal_call",
            "keyword": "monthly-liquidity",
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
            "page": "1",
            "page_size": "80",
        },
    )

    assert payload["pagination"]["total"] == 1
    assert [record["request_id"] for record in payload["records"]] == [included]
    assert excluded not in {record.get("request_id") for record in payload["records"]}
    assert payload["records"][0]["entry_type"] == "internal_call"

    content_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentContentRecordsHandler().GET,
        params={
            "service_type": "rate",
            "keyword": "monthly-liquidity",
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
            "page": "1",
            "page_size": "80",
        },
    )

    assert content_payload["pagination"]["total"] == 0
    assert content_payload["records"] == []


def test_operation_audits_api_filters_by_operator_action_keyword_and_date(business_env, monkeypatch):
    from business.audit.audit_service import record_operation_audit
    from business.schema.db import connect
    from channel.web.web_channel import InvestmentOperationAuditsHandler

    included = record_operation_audit(
        "cache.invalidate",
        "investment_cache_entry",
        "cache-a",
        operator="ops-a",
        detail={"reason": "refresh stale cache"},
    )
    excluded = record_operation_audit(
        "config.update",
        "investment_config",
        "router.enable_web_open_chat",
        operator="ops-b",
        detail={"reason": "config change"},
    )

    with connect() as conn:
        conn.execute(
            text(
                "update operation_audits "
                "set created_at = :created_at "
                "where audit_id = :audit_id"
            ),
            {"created_at": "2026-05-29T02:00:00+00:00", "audit_id": included},
        )
        conn.execute(
            text(
                "update operation_audits "
                "set created_at = :created_at "
                "where audit_id = :audit_id"
            ),
            {"created_at": "2026-05-30T02:00:00+00:00", "audit_id": excluded},
        )

    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentOperationAuditsHandler().GET,
        params={
            "action": "cache.invalidate",
            "operator": "ops-a",
            "target_type": "investment_cache_entry",
            "keyword": "stale",
            "start_date": "2026-05-29",
            "end_date": "2026-05-29",
            "limit": "20",
        },
    )

    assert payload["status"] == "success"
    assert [audit["audit_id"] for audit in payload["audits"]] == [included]
    assert excluded not in {audit["audit_id"] for audit in payload["audits"]}


def test_business_web_api_end_to_end_smoke_without_external_services(business_env, tmp_path, monkeypatch):
    from business.accounts.auth_service import authenticate_admin, create_admin_session, create_admin_user
    from business.content.daily_content import update_generation_success
    from business.records.records import get_content_record
    from business.routing.router import handle_text_message
    from channel.web import web_channel
    from channel.web.web_channel import (
        InvestmentDailyContentEffectiveHandler,
        InvestmentDailyContentExpiryHandler,
        InvestmentDailyContentGenerateHandler,
        InvestmentDailyContentHandler,
        InvestmentDailyContentInvalidateHandler,
        InvestmentHealthHandler,
        InvestmentRequestRecordsExportHandler,
        InvestmentRequestRecordsHandler,
        InvestmentUsersHandler,
    )

    create_admin_user("admin-e2e", "admin-pass", role="admin")
    create_admin_user("readonly-e2e", "readonly-pass", role="readonly")
    admin_token = create_admin_session(authenticate_admin("admin-e2e", "admin-pass"))
    readonly_token = create_admin_session(authenticate_admin("readonly-e2e", "readonly-pass"))
    headers = []
    current_params = {}
    current_body = {}
    current_token = admin_token

    monkeypatch.setattr(web_channel.web, "header", lambda name, value: headers.append((name, value)))
    monkeypatch.setattr(web_channel.web, "cookies", lambda: {"cow_investment_session": current_token})
    monkeypatch.setattr(web_channel.web, "input", lambda **_defaults: SimpleNamespace(**current_params))
    monkeypatch.setattr(web_channel.web, "data", lambda: json.dumps(current_body, ensure_ascii=False).encode("utf-8"))
    monkeypatch.setattr(web_channel.web.ctx, "headers", [], raising=False)
    monkeypatch.setattr(web_channel.web.ctx, "env", {"CONTENT_TYPE": "application/json"}, raising=False)

    def call_json(handler, *, params=None, body=None, token=None):
        nonlocal current_params, current_body, current_token
        current_params = params or {}
        current_body = body or {}
        current_token = token or admin_token
        return json.loads(handler())

    customer = {
        "openid": "openid-e2e",
        "name": "E2E Customer",
        "institution": "E2E Inst",
        "enabled": True,
        "allowed_services": ["全部"],
        "auth_start_at": "2026-01-01T00:00:00",
        "auth_end_at": "2099-12-31T23:59:59",
    }
    with pytest.raises(web_channel.web.HTTPError) as denied_error:
        call_json(InvestmentUsersHandler().POST, body=customer, token=readonly_token)
    denied = json.loads(denied_error.value.data)
    assert denied["code"] == "permission_denied"
    assert denied["permission"] == "customers.write"

    created = call_json(InvestmentUsersHandler().POST, body=customer)
    assert created["status"] == "success"
    assert created["action"] == "created"
    listed_users = call_json(InvestmentUsersHandler().GET, params={"enabled": "true", "openid": "openid-e2e"})
    assert [user["openid"] for user in listed_users["users"]] == ["openid-e2e"]

    generated_image = tmp_path / "generated-rate.png"
    generated_image.write_bytes(b"rate")
    draft = call_json(
        InvestmentDailyContentHandler().POST,
        body={"service_type": "利率", "source_text": "rate source", "operator": "admin-e2e"},
    )
    content_id = draft["content_id"]

    class ImmediateThread:
        def __init__(self, target, **_kwargs):
            self.target = target

        def start(self):
            self.target()

    def fake_generate_content(task_content_id):
        update_generation_success(task_content_id, "rate generated", str(generated_image))
        return SimpleNamespace(success=True, content_id=task_content_id, generated_text="rate generated", output_image=str(generated_image), output_files=[str(generated_image)])

    monkeypatch.setattr(web_channel.threading, "Thread", ImmediateThread)
    monkeypatch.setattr("business.content.daily_content.generate_content", fake_generate_content)
    generated = call_json(lambda: InvestmentDailyContentGenerateHandler().POST(content_id))
    assert generated["status"] == "success"
    assert generated["generation_status"] == "started"
    generated_record = get_content_record(content_id)
    assert generated_record.output_image != str(generated_image)
    assert Path(generated_record.output_image).is_file()
    assert Path(generated_record.output_image).read_bytes() == b"rate"

    effective = call_json(
        lambda: InvestmentDailyContentEffectiveHandler().POST(content_id),
            body={"operator": "admin-e2e", "effective_date": _beijing_today()},
    )
    assert effective["status"] == "success"
    current = call_json(InvestmentDailyContentHandler().GET, params={"service_type": "rate", "limit": "20"})
    assert current["current_effective"]["content_id"] == content_id
    expiry = call_json(
        lambda: InvestmentDailyContentExpiryHandler().PATCH(content_id),
        body={"expires_at": "2099-01-01T00:00"},
    )
    assert expiry["status"] == "success"
    assert get_content_record(content_id).expires_at == "2098-12-31T16:00:00.000000+00:00"
    cleared_expiry = call_json(
        lambda: InvestmentDailyContentExpiryHandler().PATCH(content_id),
        body={"expires_at": ""},
    )
    assert cleared_expiry["status"] == "success"
    assert get_content_record(content_id).expires_at == ""

    cb_image = tmp_path / "cb-current.png"
    cb_image.write_bytes(b"cb")
    cb_draft = call_json(
        InvestmentDailyContentHandler().POST,
        body={
            "service_type": "转债",
            "source_text": "cb source",
            "generated_text": "cb generated",
            "output_image": str(cb_image),
            "operator": "admin-e2e",
                "effective_date": _beijing_today(),
        },
    )
    call_json(lambda: InvestmentDailyContentEffectiveHandler().POST(cb_draft["content_id"]), body={"operator": "admin-e2e"})

    rate_reply = handle_text_message("openid-e2e", "利率")
    cb_reply = handle_text_message("openid-e2e", "转债")
    assert rate_reply.success is True
    assert rate_reply.output_files == [get_content_record(content_id).output_image]
    assert cb_reply.success is True
    assert cb_reply.output_files == [get_content_record(cb_draft["content_id"]).output_image]

    invalidated = call_json(lambda: InvestmentDailyContentInvalidateHandler().POST(content_id))
    assert invalidated["status"] == "success"
    assert invalidated["invalidated"] is True
    assert get_content_record(content_id).status == "invalidated"

    records = call_json(InvestmentRequestRecordsHandler().GET, params={"limit": "20"})
    assert {record["raw_input"] for record in records["records"]} >= {"利率", "转债"}
    assert any(artifact["artifact_role"] == "output_image" for record in records["records"] for artifact in record["output_artifacts"])

    health_calls = []
    monkeypatch.setattr(
        "business.health.health.run_health_checks",
        lambda run_smoke=False: health_calls.append(run_smoke)
        or [SimpleNamespace(name="database", ok=True, detail="ok", level="ok")],
    )
    health = call_json(InvestmentHealthHandler().GET, params={"smoke": "1"})
    assert health["status"] == "success"
    assert health["run_smoke"] is True
    assert health_calls == [True]

    headers.clear()
    export_date = datetime.now(UTC).date().isoformat()
    nonlocal_params = {"start_date": export_date, "end_date": export_date, "service_type": "", "year": "", "month": "", "quarter": ""}
    current_params = nonlocal_params
    exported = InvestmentRequestRecordsExportHandler().GET()
    rows = _xlsx_sheet_rows(exported)
    assert rows[0][:5] == ["请求时间", "OpenID", "客户姓名", "机构", "原始输入"]
    assert any(row[1:5] == ["openid-e2e", "E2E Customer", "E2E Inst", "利率"] for row in rows[1:])
    assert ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") in headers


def test_user_service_permission_edges_and_upsert(business_env):
    from business.config.constants import ErrorCode, ServiceType
    from business.accounts.user_service import (
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

    create_user(
        "not-started",
        enabled=True,
        allowed_services=[ServiceType.ALL],
        auth_start_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
        auth_end_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=10),
    )
    assert verify_permission("not-started", ServiceType.RATE).error_code == ErrorCode.UNAUTHORIZED

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


def test_user_service_crud_list_and_all_service_contract(business_env):
    from business.config.constants import ServiceType
    from business.accounts.user_service import create_user, disable_user, get_user_by_openid, list_users, update_user, verify_permission

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


def test_user_services_normalize_all_when_all_or_every_business_service_selected(business_env):
    from business.config.constants import ServiceType
    from business.accounts.user_service import create_user, get_user_by_openid, update_user

    create_user(
        "all-plus-specific",
        allowed_services=["全部", "技术分析", "利率"],
    )
    all_plus_specific = get_user_by_openid("all-plus-specific")
    assert all_plus_specific is not None
    assert all_plus_specific.allowed_services == [ServiceType.ALL]

    create_user(
        "all-specific",
        allowed_services=["技术分析", "利率", "转债"],
    )
    all_specific = get_user_by_openid("all-specific")
    assert all_specific is not None
    assert all_specific.allowed_services == [ServiceType.ALL]

    update_user("all-specific", allowed_services=["技术分析", "利率"])
    partial = get_user_by_openid("all-specific")
    assert partial is not None
    assert partial.allowed_services == [ServiceType.TECHNICAL_ANALYSIS, ServiceType.RATE]


def test_user_service_excel_import_maps_fields_and_permissions_take_effect(business_env):
    from business.config.constants import ServiceType
    from business.accounts.user_service import create_user, get_user_by_openid, import_users_from_excel, parse_users_excel, verify_permission

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
                "2026-12-31",
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
    assert rows[0].auth_start_at == datetime(2025, 12, 31, 16, 0)
    assert rows[0].auth_end_at == datetime(2026, 12, 30, 16, 0)
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


def test_user_service_excel_import_accepts_minimal_mobile_template_with_beijing_dates(business_env):
    from datetime import datetime
    from business.accounts.user_service import import_users_from_excel, parse_users_excel, get_user_by_openid

    payload = _xlsx_bytes(
        ["手机号", "服务权限", "授权开始日期", "授权结束日期"],
        [["13800138000", "利率", "2026-06-01", "2026-12-31"]],
    )

    rows = parse_users_excel(payload)

    assert len(rows) == 1
    assert rows[0].openid.startswith("pending-mobile-13800138000-")
    assert rows[0].mobile == "13800138000"
    assert rows[0].allowed_services == "利率"
    assert rows[0].auth_start_at == datetime(2026, 5, 31, 16, 0)
    assert rows[0].auth_end_at == datetime(2026, 12, 30, 16, 0)

    result = import_users_from_excel(payload)
    assert result.created == 1
    assert get_user_by_openid(rows[0].openid) is not None


def test_user_service_excel_import_accepts_excel_date_cells_as_beijing_dates(business_env):
    from datetime import datetime
    from io import BytesIO

    from openpyxl import Workbook

    from business.accounts.user_service import parse_users_excel

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["手机号", "服务权限", "授权开始日期", "授权结束日期"])
    sheet.append(["13800138000", "利率", datetime(2026, 6, 1), datetime(2026, 12, 31)])
    output = BytesIO()
    workbook.save(output)

    rows = parse_users_excel(output.getvalue())

    assert rows[0].auth_start_at == datetime(2026, 5, 31, 16, 0)
    assert rows[0].auth_end_at == datetime(2026, 12, 30, 16, 0)


def test_user_service_excel_import_reports_invalid_date_with_row_and_field(business_env):
    from business.accounts.user_service import parse_users_excel

    payload = _xlsx_bytes(
        ["手机号", "服务权限", "授权开始日期", "授权结束日期"],
        [["13800138000", "利率", "2026-06-01", "2026-6-122"]],
    )

    with pytest.raises(ValueError) as error:
        parse_users_excel(payload)

    message = str(error.value)
    assert "Excel row 2 invalid date field: auth_end_at" in message
    assert "YYYY-MM-DD" in message
    assert "unconverted data remains" not in message

    invalid_month_payload = _xlsx_bytes(
        ["手机号", "服务权限", "授权开始日期", "授权结束日期"],
        [["13800138000", "利率", "2026-06-01", "2026-13-01"]],
    )
    with pytest.raises(ValueError) as month_error:
        parse_users_excel(invalid_month_payload)

    assert "Excel row 2 invalid date field: auth_end_at" in str(month_error.value)

    short_number_payload = _xlsx_bytes(
        ["手机号", "服务权限", "授权开始日期", "授权结束日期"],
        [["13800138000", "利率", "2026-06-01", "1"]],
    )
    with pytest.raises(ValueError) as number_error:
        parse_users_excel(short_number_payload)

    assert "Excel row 2 invalid date field: auth_end_at" in str(number_error.value)


def test_user_service_excel_import_requires_authorization_start_end_and_services(business_env):
    from business.accounts.user_service import parse_users_excel

    missing_start = _xlsx_bytes(
        ["手机号", "服务权限", "授权结束日期"],
        [["13800138000", "利率", "2026-12-31"]],
    )
    with pytest.raises(ValueError) as start_error:
        parse_users_excel(missing_start)
    assert "auth_start_at" in str(start_error.value)

    missing_service = _xlsx_bytes(
        ["手机号", "授权开始日期", "授权结束日期"],
        [["13800138000", "2026-06-01", "2026-12-31"]],
    )
    with pytest.raises(ValueError) as service_error:
        parse_users_excel(missing_service)
    assert "allowed_services" in str(service_error.value)

    blank_values = _xlsx_bytes(
        ["手机号", "服务权限", "授权开始日期", "授权结束日期"],
        [["13800138000", "", "", ""]],
    )
    with pytest.raises(ValueError) as blank_error:
        parse_users_excel(blank_values)
    message = str(blank_error.value)
    assert "allowed_services" in message or "auth_start_at" in message or "auth_end_at" in message


def test_user_import_template_headers_are_parseable(business_env):
    from business.records.export_service import export_users_import_template_xlsx
    from business.accounts.user_service import parse_users_excel

    rows = parse_users_excel(export_users_import_template_xlsx())

    assert len(rows) == 1
    assert rows[0].openid.startswith("pending-mobile-13800000000-")
    assert rows[0].allowed_services == "全部"


def test_web_user_import_parses_before_confirm_and_then_commits(business_env, monkeypatch):
    from business.config.constants import ServiceType
    from business.accounts.user_service import create_user, get_user_by_openid
    from channel.web import web_channel
    from channel.web.web_channel import InvestmentUsersImportHandler

    create_user("existing-import", name="Old", allowed_services=[ServiceType.RATE])
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
            ["existing-import", "Existing New", "Inst A", "13800000000", "启用", "全部", "2026-06-01", "2026-12-31", "updated"],
            ["new-import", "New User", "Inst B", "13900000000", "启用", "利率", "2026-06-01", "2026-12-31", "created"],
        ],
    )

    _login_default_investment_admin(monkeypatch)
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(web_channel.web.ctx, "headers", [], raising=False)
    monkeypatch.setattr(
        web_channel.web.webapi,
        "rawinput",
        lambda **_kwargs: {"file": SimpleNamespace(filename="customers.xlsx", value=payload), "commit": "false"},
    )

    parsed = json.loads(InvestmentUsersImportHandler().POST())

    assert parsed["status"] == "success"
    assert parsed["committed"] is False
    assert parsed["parsed"] == 2
    assert parsed["new_users"] == 1
    assert parsed["created"] == 0
    assert parsed["updated"] == 0
    assert [row["openid"] for row in parsed["preview"]] == ["existing-import", "new-import"]
    assert get_user_by_openid("existing-import").name == "Old"
    assert get_user_by_openid("new-import") is None

    monkeypatch.setattr(
        web_channel.web.webapi,
        "rawinput",
        lambda **_kwargs: {"file": SimpleNamespace(filename="customers.xlsx", value=payload), "commit": "true"},
    )
    committed = json.loads(InvestmentUsersImportHandler().POST())

    assert committed["status"] == "success"
    assert committed["committed"] is True
    assert committed["parsed"] == 2
    assert committed["new_users"] == 1
    assert committed["created"] == 1
    assert committed["updated"] == 1
    assert get_user_by_openid("existing-import").name == "Existing New"
    assert get_user_by_openid("new-import").name == "New User"


def test_records_save_failure_success_and_order(business_env):
    from business.config.constants import ErrorCode, ServiceType
    from business.records.records import (
        append_request_warning,
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

    append_request_warning(first, "微信图片上传失败：Error code: 40164, message: invalid ip 14.153.6.203 not in whitelist")
    warned = get_request_record(first)
    assert "40164" in warned.error_message
    assert "14.153.6.203" in warned.status_warning


def test_request_record_delivery_status_is_business_facing(business_env):
    from business.config.constants import ErrorCode, ServiceType
    from business.records.records import (
        append_request_warning,
        create_request_record,
        fail_request_record,
        get_request_record,
        mark_request_delivered,
        succeed_request_record,
    )

    generated = create_request_record("openid", "技术分析", ServiceType.TECHNICAL_ANALYSIS)
    succeed_request_record(generated, output_files=["/tmp/report.png"], elapsed_ms=10)
    assert get_request_record(generated).delivery_status == "待客户领取"

    mark_request_delivered(generated)
    delivered = get_request_record(generated)
    assert delivered.delivery_status == "已交付"
    assert delivered.delivery_detail == "客户已收到结果"
    assert delivered.error_message == ""
    assert delivered.status_warning == ""

    append_request_warning(generated, "图片上传失败：Error code: 40164")
    failed_delivery = get_request_record(generated)
    assert failed_delivery.delivery_status == "交付异常"
    assert failed_delivery.delivery_detail == "图片上传失败：Error code: 40164"

    failed = create_request_record("openid", "利率", ServiceType.RATE)
    fail_request_record(failed, ErrorCode.NO_CONTENT, "今日内容尚未更新，请稍后再试。", "no active content", 5)
    failed_record = get_request_record(failed)
    assert failed_record.delivery_status == "未交付"
    assert failed_record.delivery_detail == "no active content"


def test_passive_reply_validation_rejects_invalidated_product_source(business_env, tmp_path):
    from types import SimpleNamespace

    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, invalidate_content, set_content_effective
    from business.products.product_service import list_products_page
    from channel.wechatmp.passive_reply import _cached_result_source_is_valid

    image = tmp_path / "rate.png"
    image.write_bytes(b"rate")
    content_id = create_content_draft(ServiceType.RATE, source_text="rate")
    set_content_effective(content_id, str(image), effective_date="2026-06-24", operator="ops")

    products, total = list_products_page(business_type=str(ServiceType.RATE))
    assert total == 1
    cached_result = SimpleNamespace(source_type="product", source_id=products[0]["product_id"])

    assert _cached_result_source_is_valid(cached_result) is True

    invalidate_content(content_id, operator="ops")

    assert _cached_result_source_is_valid(cached_result) is False


def test_export_request_records_hides_internal_delivery_marker(business_env):
    from business.config.constants import ServiceType
    from business.records.export_service import export_request_records_xlsx
    from business.records.records import create_request_record, mark_request_delivered, succeed_request_record

    request_id = create_request_record("openid", "利率", ServiceType.RATE)
    succeed_request_record(request_id, output_files=[], elapsed_ms=12)
    mark_request_delivered(request_id)

    rows = _xlsx_sheet_rows(export_request_records_xlsx("", "", service_type="rate"))

    assert rows[1][4] == "利率"
    assert rows[1][10] in ("", None)
    assert "[delivery:delivered]" not in str(rows[1])


def test_old_generating_request_records_are_flagged_without_mutating_status(business_env):
    from business.config.constants import ServiceType, Status
    from business.schema.db import connect
    from business.records.records import create_request_record, get_request_record, list_request_records

    request_id = create_request_record("openid", "新易盛 技术分析", ServiceType.TECHNICAL_ANALYSIS)
    old_created_at = (datetime.now(UTC) - timedelta(minutes=31)).isoformat(timespec="microseconds")
    with connect() as conn:
        conn.execute(
            text(
                "update request_records "
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


def test_job_service_reuses_running_technical_analysis_record(business_env):
    from business.config.constants import ServiceType
    from business.health.job_service import find_running_job, start_job_if_absent
    from business.records.records import succeed_request_record

    first = start_job_if_absent("openid", "300502.SZ 技术分析", ServiceType.TECHNICAL_ANALYSIS)
    duplicate = start_job_if_absent("openid", "300502.SZ 技术分析", ServiceType.TECHNICAL_ANALYSIS)

    assert first.created is True
    assert duplicate.created is False
    assert duplicate.record.request_id == first.record.request_id
    assert find_running_job("openid", "300502.SZ 技术分析").request_id == first.record.request_id

    succeed_request_record(first.record.request_id, output_files=["/tmp/signal.png", "/tmp/chart.png"], elapsed_ms=12)
    next_job = start_job_if_absent("openid", "300502.SZ 技术分析", ServiceType.TECHNICAL_ANALYSIS)

    assert next_job.created is True
    assert next_job.record.request_id != first.record.request_id


def test_job_service_reuses_running_cache_job_across_users(business_env):
    from business.config.constants import ServiceType
    from business.health.job_service import find_running_cache_job, start_cache_job_if_absent
    from business.records.records import succeed_request_record

    cache_key = "technical_analysis:300502.SZ:2026-05-25:v1"

    first = start_cache_job_if_absent(
        "openid-a",
        "300502.SZ 技术分析",
        ServiceType.TECHNICAL_ANALYSIS,
        cache_key,
        normalized_target="300502.SZ",
        market_date="2026-05-25",
    )
    duplicate = start_cache_job_if_absent(
        "openid-b",
        "新易盛 技术分析",
        ServiceType.TECHNICAL_ANALYSIS,
        cache_key,
        normalized_target="300502.SZ",
        market_date="2026-05-25",
    )

    assert first.created is True
    assert duplicate.created is False
    assert duplicate.record.request_id == first.record.request_id
    assert find_running_cache_job(cache_key, ServiceType.TECHNICAL_ANALYSIS).request_id == first.record.request_id
    assert first.record.cache_key == cache_key
    assert first.record.normalized_target == "300502.SZ"
    assert first.record.market_date == "2026-05-25"

    succeed_request_record(first.record.request_id, output_files=["/tmp/signal.png", "/tmp/chart.png"], elapsed_ms=12)
    next_job = start_cache_job_if_absent(
        "openid-b",
        "新易盛 技术分析",
        ServiceType.TECHNICAL_ANALYSIS,
        cache_key,
        normalized_target="300502.SZ",
        market_date="2026-05-25",
    )

    assert next_job.created is True
    assert next_job.record.request_id != first.record.request_id


def test_job_service_marks_stale_running_cache_job_failed_and_allows_new_job(business_env):
    from business.config.constants import ServiceType, Status
    from business.schema.db import connect
    from business.health.job_service import find_running_cache_job, start_cache_job_if_absent
    from business.records.records import get_request_record

    cache_key = "technical_analysis:300502.SZ:2026-05-25:v1"
    first = start_cache_job_if_absent(
        "openid-a",
        "300502.SZ 技术分析",
        ServiceType.TECHNICAL_ANALYSIS,
        cache_key,
        normalized_target="300502.SZ",
        market_date="2026-05-25",
    )
    stale_time = (datetime.now(UTC) - timedelta(minutes=31)).isoformat(timespec="microseconds")
    with connect() as conn:
        conn.execute(
            text(
                "update request_records "
                "set created_at=:created_at, updated_at=:created_at where request_id=:request_id"
            ),
            {"created_at": stale_time, "request_id": first.record.request_id},
        )

    assert find_running_cache_job(cache_key, ServiceType.TECHNICAL_ANALYSIS) is None
    assert get_request_record(first.record.request_id).status == Status.FAILED

    next_job = start_cache_job_if_absent(
        "openid-b",
        "新易盛 技术分析",
        ServiceType.TECHNICAL_ANALYSIS,
        cache_key,
        normalized_target="300502.SZ",
        market_date="2026-05-25",
    )

    assert next_job.created is True
    assert next_job.record.request_id != first.record.request_id


def test_job_service_allows_different_cache_keys_to_run_together(business_env):
    from business.config.constants import ServiceType
    from business.health.job_service import start_cache_job_if_absent

    first = start_cache_job_if_absent(
        "openid-a",
        "300502.SZ 2026-05-25 技术分析",
        ServiceType.TECHNICAL_ANALYSIS,
        "technical_analysis:300502.SZ:2026-05-25:v1",
        normalized_target="300502.SZ",
        market_date="2026-05-25",
    )
    second = start_cache_job_if_absent(
        "openid-b",
        "300502.SZ 2026-05-26 技术分析",
        ServiceType.TECHNICAL_ANALYSIS,
        "technical_analysis:300502.SZ:2026-05-26:v1",
        normalized_target="300502.SZ",
        market_date="2026-05-26",
    )

    assert first.created is True
    assert second.created is True
    assert second.record.request_id != first.record.request_id


def test_technical_analysis_exception_marks_record_failed_and_unblocks_running_job(business_env, monkeypatch):
    from business.config import config_service as config_service
    from business.config.constants import ErrorCode, ServiceType, Status
    from business.health.job_service import find_running_job
    from business.records.records import get_content_record, list_request_records
    from business.routing.router import handle_text_message
    from business.accounts.user_service import create_user

    monkeypatch.setattr(config_service, "conf", lambda: {"custom_api_key": "sk-secret-123"})
    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])

    reply = handle_text_message(
        "ok",
        "300502.SZ 技术分析",
        technical_analysis_handler=lambda *_args: (_ for _ in ()).throw(RuntimeError("backend boom sk-secret-123")),
    )

    record = list_request_records(limit=1)[0]
    assert reply.success is False
    assert reply.error_code == ErrorCode.SYSTEM_ERROR
    assert record.status == Status.FAILED
    assert record.error_code == ErrorCode.SYSTEM_ERROR
    assert "backend boom" in record.error_message
    assert "sk-secret-123" not in record.error_message
    assert find_running_job("ok", "300502.SZ 技术分析", ServiceType.TECHNICAL_ANALYSIS) is None


def test_router_delegates_technical_analysis_to_cowagent_business_handler(business_env, monkeypatch):
    from business.config.constants import ServiceType
    from business.routing.router import BusinessReply, handle_text_message
    from business.accounts.user_service import create_user
    import business.execution.technical_analysis_executor as investment_ta_executor
    import business.content.technical_analysis_handler as cowagent_ta_handler

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    monkeypatch.setattr(
        investment_ta_executor,
        "prepare_technical_analysis_business_context",
        lambda *_args, **_kwargs: pytest.fail("router must not directly prepare investment technical analysis"),
    )
    calls = []

    def fake_handler(openid, raw_input, route, **kwargs):
        calls.append((openid, raw_input, route.target_text, bool(kwargs.get("customer_metadata") is not None)))
        return BusinessReply(
            True,
            True,
            "[图片: /tmp/signal.png]",
            ["/tmp/signal.png"],
            ServiceType.TECHNICAL_ANALYSIS,
            request_id="request-from-cowagent-handler",
        )

    monkeypatch.setattr(cowagent_ta_handler, "handle_technical_analysis", fake_handler)

    reply = handle_text_message("ok", "300502.SZ 技术分析")

    assert reply.success is True
    assert reply.request_id == "request-from-cowagent-handler"
    assert calls == [("ok", "300502.SZ 技术分析", "300502.SZ", True)]


def test_job_service_ignores_stale_running_technical_analysis_record(business_env):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import text

    from business.config.constants import ServiceType, Status
    from business.schema.db import connect
    from business.health.job_service import find_running_job, start_job_if_absent
    from business.records.records import create_request_record, get_request_record

    old_id = create_request_record("openid", "300502.SZ 技术分析", ServiceType.TECHNICAL_ANALYSIS)
    stale_time = (datetime.now(UTC) - timedelta(minutes=31)).isoformat(timespec="microseconds")
    with connect() as conn:
        conn.execute(
            text("update request_records set created_at=:created_at, updated_at=:created_at where request_id=:request_id"),
            {"created_at": stale_time, "request_id": old_id},
        )

    assert find_running_job("openid", "300502.SZ 技术分析", ServiceType.TECHNICAL_ANALYSIS) is None
    assert get_request_record(old_id).status == Status.FAILED

    next_job = start_job_if_absent("openid", "300502.SZ 技术分析", ServiceType.TECHNICAL_ANALYSIS)

    assert next_job.created is True
    assert next_job.record.request_id != old_id


def test_job_service_concurrent_start_creates_single_running_job(business_env):
    from concurrent.futures import ThreadPoolExecutor

    from business.config.constants import ServiceType
    from business.health.job_service import start_job_if_absent
    from business.records.records import get_content_record, list_request_records

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _index: start_job_if_absent("openid", "300502.SZ 技术分析", ServiceType.TECHNICAL_ANALYSIS),
                range(2),
            )
        )

    assert sum(1 for result in results if result.created) == 1
    assert len({result.record.request_id for result in results}) == 1
    records = list_request_records(limit=10)
    running = [record for record in records if record.raw_input == "300502.SZ 技术分析"]
    assert len(running) == 1


def test_router_concurrent_technical_analysis_reuses_running_job_without_duplicate_handler(
    business_env,
    tmp_path,
):
    from concurrent.futures import ThreadPoolExecutor
    import time

    from business.config.constants import ServiceType
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.content.technical_analysis import TechnicalAnalysisResult
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    card = tmp_path / "signal.png"
    chart = tmp_path / "chart.png"
    report = tmp_path / "report.md"
    card.write_bytes(b"card")
    chart.write_bytes(b"chart")
    report.write_text("report", encoding="utf-8")
    calls = []

    def slow_handler(_openid, _raw_input, _target):
        calls.append(_target)
        time.sleep(0.2)
        return TechnicalAnalysisResult(
            True,
            signal_card_path=str(card),
            main_chart_path=str(chart),
            report_path=str(report),
            output_files=[str(card), str(chart), str(report)],
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(
            pool.map(
                lambda _index: handle_text_message(
                    "ok",
                    "300502.SZ 技术分析",
                    technical_analysis_handler=slow_handler,
                ),
                range(2),
            )
        )

    assert len(calls) == 1
    assert sum(1 for reply in replies if reply.success) == 1
    waiting = [reply for reply in replies if not reply.success]
    assert len(waiting) == 1
    assert waiting[0].reply_text == "正在运行，请稍候。"
    records = [record for record in list_request_records(limit=10) if record.raw_input == "300502.SZ 技术分析"]
    assert len(records) == 1


def test_router_concurrent_technical_analysis_reuses_running_cache_job_across_users(
    business_env,
    tmp_path,
    monkeypatch,
):
    from concurrent.futures import ThreadPoolExecutor
    import time

    from business.content import technical_analysis as technical_analysis
    from business.config.constants import ServiceType
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.content.technical_analysis import TechnicalAnalysisResult
    from business.accounts.user_service import create_user

    create_user("openid-a", enabled=True, allowed_services=[ServiceType.ALL])
    create_user("openid-b", enabled=True, allowed_services=[ServiceType.ALL])
    card = tmp_path / "signal.png"
    chart = tmp_path / "chart.png"
    report = tmp_path / "report.md"
    card.write_bytes(b"card")
    chart.write_bytes(b"chart")
    report.write_text("report", encoding="utf-8")
    calls = []

    monkeypatch.setattr(
        technical_analysis,
        "_versions",
        lambda: ("sha256:program-v1", "sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1"),
    )

    class FakeResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "300502.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="2026-05-25", known=True, source="fake")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", FakeResolver, raising=False)

    def slow_handler(_openid, _raw_input, _target):
        calls.append(_openid)
        time.sleep(0.2)
        return TechnicalAnalysisResult(
            True,
            signal_card_path=str(card),
            main_chart_path=str(chart),
            report_path=str(report),
            output_files=[str(card), str(chart), str(report)],
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(
            pool.map(
                lambda openid: handle_text_message(
                    openid,
                    "300502.SZ 技术分析",
                    technical_analysis_handler=slow_handler,
                ),
                ["openid-a", "openid-b"],
            )
        )

    assert len(calls) == 1
    assert sum(1 for reply in replies if reply.success) == 1
    waiting = [reply for reply in replies if not reply.success]
    assert len(waiting) == 1
    assert waiting[0].reply_text == "正在运行，请稍候。"
    records = [record for record in list_request_records(limit=10) if record.raw_input == "300502.SZ 技术分析"]
    assert len(records) == 1
    assert records[0].cache_key
    assert records[0].normalized_target == "300502.SZ"
    assert records[0].market_date == "2026-05-25"


def test_request_records_api_includes_generating_timeout_warning(business_env, monkeypatch):
    from business.config.constants import ServiceType
    from business.schema.db import connect
    from business.records.records import create_request_record
    from channel.web.web_channel import InvestmentRequestRecordsHandler

    request_id = create_request_record("openid", "新易盛 技术分析", ServiceType.TECHNICAL_ANALYSIS)
    old_created_at = (datetime.now(UTC) - timedelta(minutes=31)).isoformat(timespec="microseconds")
    with connect() as conn:
        conn.execute(
            text(
                "update request_records "
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


def test_batch_01_service_results_share_contract_fields(business_env):
    from business.audit.ai_generation import AIGenerationResult
    from business.content.daily_content import DailyContentResult
    from business.content.render_service import RenderResult
    from business.routing.router import BusinessReply
    from business.content.technical_analysis import TechnicalAnalysisResult

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


def test_success_request_records_output_files_table(business_env):
    from business.config.constants import ServiceType
    from business.schema.db import connect
    from business.records.records import record_success_request

    request_id = record_success_request("openid", "利率", ServiceType.RATE, ["/tmp/rate.png"], elapsed_ms=3)

    with connect() as conn:
        rows = conn.execute(
            text(
                "select owner_id, file_path, file_type, service "
                "from artifacts where owner_id = :request_id"
            ),
            {"request_id": request_id},
        ).mappings().all()

    assert [dict(row) for row in rows] == [
        {
            "owner_id": request_id,
            "file_path": "/tmp/rate.png",
            "file_type": "image",
            "service": ServiceType.RATE,
        }
    ]


def test_success_request_archives_generated_images_and_documents(business_env, tmp_path):
    from business.config.constants import ServiceType
    from business.records.records import create_request_record, get_request_record, list_output_files, succeed_request_record
    from business.schema.storage import get_storage_dirs

    image = tmp_path / "rate_card.png"
    report = tmp_path / "rate_report.md"
    image.write_bytes(b"image-v1")
    report.write_text("report-v1", encoding="utf-8")
    request_id = create_request_record("openid", "利率", ServiceType.RATE)

    succeed_request_record(
        request_id,
        output_files=[str(image), str(report)],
        elapsed_ms=3,
        artifact_roles={str(image): "output_image", str(report): "markdown_report"},
    )

    record = get_request_record(request_id)
    artifacts = list_output_files(request_id)
    files_root = get_storage_dirs()["files"]

    assert len(record.output_files or []) == 2
    assert all(Path(path).is_file() for path in record.output_files or [])
    assert all(Path(path).resolve().is_relative_to(files_root.resolve()) for path in record.output_files or [])
    for path in record.output_files or []:
        parts = Path(path).parts
        files_index = parts.index("files")
        assert parts[files_index + 1] == str(ServiceType.RATE)
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[files_index + 2])
        assert parts[files_index + 3] == "request"
        assert parts[files_index + 4] == request_id
    assert record.output_files != [str(image), str(report)]
    assert Path(record.output_files[0]).read_bytes() == b"image-v1"
    assert Path(record.output_files[1]).read_text(encoding="utf-8") == "report-v1"
    assert [(item["file_path"], item["file_type"], item["artifact_role"]) for item in artifacts] == [
        (record.output_files[0], "image", "output_image"),
        (record.output_files[1], "markdown", "markdown_report"),
    ]
    assert all(item["file_id"] for item in artifacts)
    assert all(item["file_url"].startswith("/api/file?id=") for item in artifacts)


def test_legacy_output_paths_migrate_to_unified_files_dir(business_env):
    from business.cache.cache_service import find_cache_entry_by_key, write_cache_entry
    from business.config.constants import ServiceType
    from business.schema.db import connect
    from business.schema.file_migration import migrate_legacy_files_to_unified_storage
    from business.content.daily_content import create_content_draft
    from business.records.records import create_request_record, get_content_record, get_request_record, list_output_files, record_output_file
    from business.schema.storage import get_storage_dirs

    legacy_dir = get_storage_dirs()["root"] / "generated" / "archive" / "legacy"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy_file = legacy_dir / "legacy-card.png"
    legacy_file.write_bytes(b"legacy-card")
    legacy_source = legacy_dir / "legacy-source.png"
    legacy_source.write_bytes(b"legacy-source")
    request_id = create_request_record("openid", "技术分析", ServiceType.TECHNICAL_ANALYSIS)
    content_id = create_content_draft(
        ServiceType.RATE,
        source_files=[str(legacy_source)],
        source_text="legacy",
        effective_date="2026-06-07",
    )
    old_files_dir = get_storage_dirs()["files"] / "rate" / "content" / content_id / "output_image"
    old_files_dir.mkdir(parents=True, exist_ok=True)
    old_files_output = old_files_dir / "old-files-card.png"
    old_files_output.write_bytes(b"old-files-card")
    with connect() as conn:
        conn.execute(
            text("update request_records set outputs = :files where request_id = :request_id"),
            {"files": json.dumps([str(legacy_file)]), "request_id": request_id},
        )
        conn.execute(
            text("update content_records set output_image_path = :path where content_id = :content_id"),
            {"path": str(old_files_output), "content_id": content_id},
        )
    record_output_file(
        request_id,
        str(legacy_file),
        None,
        ServiceType.TECHNICAL_ANALYSIS,
        artifact_role="signal_card",
    )
    write_cache_entry(
        cache_key="technical_analysis:legacy:2026-06-07:v1",
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="legacy",
        market_date="2026-06-07",
        version_fingerprint="v1",
        output_files=[str(legacy_file)],
        artifact_owner_id=request_id,
    )

    changed = migrate_legacy_files_to_unified_storage()

    record = get_request_record(request_id)
    artifacts = list_output_files(request_id)
    content = get_content_record(content_id)
    source_artifacts = [item for item in list_output_files(content_id) if item["artifact_role"] == "source_image"]
    cache_entry = find_cache_entry_by_key("technical_analysis:legacy:2026-06-07:v1")
    assert changed == 3
    assert record.output_files and Path(record.output_files[0]).is_file()
    assert Path(record.output_files[0]).resolve().is_relative_to(get_storage_dirs()["files"].resolve())
    assert not legacy_file.exists()
    assert artifacts[0]["file_path"] == record.output_files[0]
    assert cache_entry is not None
    assert cache_entry.output_files == record.output_files
    assert content.source_files and Path(content.source_files[0]).resolve().is_relative_to(get_storage_dirs()["files"].resolve())
    assert content.output_image and Path(content.output_image).resolve().is_relative_to(get_storage_dirs()["files"].resolve())
    output_parts = Path(content.output_image).parts
    files_index = output_parts.index("files")
    assert output_parts[files_index + 1 : files_index + 5] == (
        "rate",
        "2026-06-07",
        "content",
        content_id,
    )
    assert not old_files_output.exists()
    assert not legacy_source.exists()
    assert len(source_artifacts) == 1
    assert source_artifacts[0]["file_path"] == content.source_files[0]
    assert source_artifacts[0]["file_url"].startswith("/api/file?id=")


def test_request_records_save_audit_metadata(business_env):
    from business.config.constants import ServiceType
    from business.records.records import create_request_record, get_request_record, succeed_request_record

    request_id = create_request_record(
        "openid",
        "新易盛 技术分析",
        ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        stock_code="300502.SZ",
        stock_name="新易盛",
        customer_name="Alice",
        institution="Inst A",
        market_date="2026-05-25",
        cache_key="ta:300502.SZ:2026-05-25",
        cache_hit=True,
        program_version="sha256:program12345678",
        ta_version="sha256:ta123456789012",
        renderer_version="sha256:renderer123456",
        template_version="sha256:template123456",
    )
    succeed_request_record(request_id, output_files=[], elapsed_ms=12)

    record = get_request_record(request_id)

    assert record.normalized_target == "300502.SZ"
    assert record.stock_code == "300502.SZ"
    assert record.stock_name == "新易盛"
    assert record.customer_name == "Alice"
    assert record.institution == "Inst A"
    assert record.market_date == "2026-05-25"
    assert record.cache_key == "ta:300502.SZ:2026-05-25"
    assert record.cache_hit is True
    assert record.program_version == "sha256:program12345678"
    assert record.ta_version == "sha256:ta123456789012"
    assert record.renderer_version == "sha256:renderer123456"
    assert record.template_version == "sha256:template123456"


def test_unauthorized_request_service_type_is_normalized_and_labeled():
    from business.config.constants import SERVICE_LABELS, ServiceType, normalize_service

    assert ServiceType.UNAUTHORIZED_REQUEST == "unauthorized_request"
    assert SERVICE_LABELS[ServiceType.UNAUTHORIZED_REQUEST] == "无权限请求"
    assert normalize_service("unauthorized_request") == ServiceType.UNAUTHORIZED_REQUEST
    assert normalize_service("无权限请求") == ServiceType.UNAUTHORIZED_REQUEST


def _xlsx_sheet_rows(content: bytes) -> list[list[object]]:
    from openpyxl import load_workbook

    workbook = load_workbook(BytesIO(content))
    sheet = workbook.active
    return [list(row) for row in sheet.iter_rows(values_only=True)]


def test_export_date_range_helpers_return_inclusive_bounds():
    from business.records.export_service import month_range, quarter_range

    assert month_range(2026, 2) == ("2026-02-01T00:00:00", "2026-02-28T23:59:59")
    assert month_range(2024, 2) == ("2024-02-01T00:00:00", "2024-02-29T23:59:59")
    assert quarter_range(2026, 2) == ("2026-04-01T00:00:00", "2026-06-30T23:59:59")


def test_business_date_bound_treats_plain_dates_as_beijing_days():
    from channel.web.web_channel import _investment_date_bound, _investment_month_bounds, _investment_quarter_bounds

    assert _investment_date_bound("2026-05-31") == "2026-05-30T16:00:00"
    assert _investment_date_bound("2026-05-31", end=True) == "2026-05-31T15:59:59.999999"
    assert _investment_date_bound("2026-05-31T12:30:00") == "2026-05-31T12:30:00"
    assert _investment_date_bound("2026-05-31 12:30:00", end=True) == "2026-05-31 12:30:00"
    assert _investment_month_bounds(2026, 5) == ("2026-04-30T16:00:00", "2026-05-31T15:59:59.999999")
    assert _investment_quarter_bounds(2026, 2) == ("2026-03-31T16:00:00", "2026-06-30T15:59:59.999999")


def test_request_records_export_api_forces_external_request_entry_type(business_env, monkeypatch):
    from business.config.constants import ActionType, ActorType, EntryType, ServiceType, Status
    from business.records.records import (
        create_business_workflow_record,
        create_request_record,
        finish_business_workflow_record,
        succeed_request_record,
    )
    from channel.web.web_channel import InvestmentRequestRecordsExportHandler

    external_id = create_request_record("openid-export", "利率", ServiceType.RATE)
    succeed_request_record(external_id, output_files=["/tmp/external.png"], elapsed_ms=1)
    internal_id = create_business_workflow_record(
        entry_type=EntryType.INTERNAL_CALL,
        service_type=ServiceType.RATE,
        action_type=ActionType.GENERATE,
        actor_type=ActorType.ADMIN,
        actor_name="ops-export",
        raw_input="backend export source",
    )
    finish_business_workflow_record(
        internal_id,
        status=Status.SUCCESS,
        output_files=["/tmp/internal.png"],
        elapsed_ms=1,
    )

    payload = _call_investment_bytes_handler(
        monkeypatch,
        InvestmentRequestRecordsExportHandler().GET,
        params={"entry_type": "internal_call"},
    )
    rows = _xlsx_sheet_rows(payload)

    assert len(rows) == 2
    assert rows[1][1] == "openid-export"
    assert rows[1][4] == "利率"
    assert all("backend export source" not in [str(cell) for cell in row] for row in rows)


def test_export_request_records_xlsx_filters_and_includes_audit_fields(business_env):
    from business.config.constants import ErrorCode, ServiceType
    from business.schema.db import connect
    from business.records.export_service import export_request_records_xlsx
    from business.records.records import create_request_record, fail_request_record, succeed_request_record

    older = create_request_record("old-openid", "利率", ServiceType.RATE)
    succeed_request_record(older, output_files=["/tmp/old.png"], elapsed_ms=1)
    included = create_request_record(
        "openid-a",
        "新易盛 技术分析",
        ServiceType.TECHNICAL_ANALYSIS,
        stock_code="300502.SZ",
        stock_name="新易盛",
        customer_name="Alice",
        institution="Inst A",
        cache_hit=True,
        program_version="sha256:program",
        template_version="sha256:template",
    )
    succeed_request_record(included, output_files=["/tmp/card.png"], elapsed_ms=15)
    failed = create_request_record("openid-b", "贵州茅台 技术分析", ServiceType.TECHNICAL_ANALYSIS)
    fail_request_record(failed, ErrorCode.STOCK_NOT_FOUND, detail="not found", elapsed_ms=5)

    with connect() as conn:
        conn.execute(
            text(
                "update request_records "
                "set created_at = :created_at, updated_at = :created_at "
                "where request_id = :request_id"
            ),
            {"created_at": "2026-04-30T23:59:59", "request_id": older},
        )
        conn.execute(
            text(
                "update request_records "
                "set created_at = :created_at, updated_at = :created_at "
                "where request_id = :request_id"
            ),
            {"created_at": "2026-05-10T08:00:00", "request_id": included},
        )
        conn.execute(
            text(
                "update request_records "
                "set created_at = :created_at, updated_at = :created_at "
                "where request_id = :request_id"
            ),
            {"created_at": "2026-06-01T00:00:00", "request_id": failed},
        )

    rows = _xlsx_sheet_rows(
        export_request_records_xlsx(
            "2026-05-01T00:00:00",
            "2026-05-31T23:59:59",
            service_type=ServiceType.TECHNICAL_ANALYSIS,
            status="success",
            keyword="Alice",
        )
    )

    assert rows == [
        [
            "请求时间",
            "OpenID",
            "客户姓名",
            "机构",
            "原始输入",
            "服务类型",
            "股票代码",
            "股票名称",
            "状态",
            "错误码",
            "错误原因",
            "缓存命中",
            "输出文件",
            "耗时毫秒",
            "程序版本",
            "模板版本",
        ],
        [
            "2026-05-10T08:00:00",
            "openid-a",
            "Alice",
            "Inst A",
            "新易盛 技术分析",
            "technical_analysis",
            "300502.SZ",
            "新易盛",
            "success",
            None,
            None,
            "是",
            "/tmp/card.png",
            15,
            "sha256:program",
            "sha256:template",
        ],
    ]


def test_export_request_records_xlsx_filters_by_service_customer_and_range(business_env):
    from business.config.constants import ServiceType
    from business.schema.db import connect
    from business.records.export_service import export_request_records_xlsx
    from business.records.records import create_request_record, succeed_request_record
    from business.accounts.user_service import create_user

    create_user("openid-a", name="Alice", mobile="13800000000", enabled=True, allowed_services=[ServiceType.ALL])
    create_user("openid-b", name="Bob", mobile="13900000000", enabled=True, allowed_services=[ServiceType.ALL])
    included = create_request_record("openid-a", "新易盛 技术分析", ServiceType.TECHNICAL_ANALYSIS, stock_name="新易盛")
    wrong_service = create_request_record("openid-a", "利率", ServiceType.RATE)
    wrong_user = create_request_record("openid-b", "贵州茅台 技术分析", ServiceType.TECHNICAL_ANALYSIS)
    succeed_request_record(included, output_files=["/tmp/card.png"], elapsed_ms=1)
    succeed_request_record(wrong_service, output_files=["/tmp/rate.png"], elapsed_ms=1)
    succeed_request_record(wrong_user, output_files=["/tmp/other.png"], elapsed_ms=1)
    with connect() as conn:
        for request_id in [included, wrong_service, wrong_user]:
            conn.execute(
                text(
                    "update request_records "
                    "set created_at = '2026-05-10T08:00:00' "
                    "where request_id = :request_id"
                ),
                {"request_id": request_id},
            )

    rows = _xlsx_sheet_rows(
        export_request_records_xlsx(
            "2026-05-01T00:00:00",
            "2026-05-31T23:59:59",
            service_type=ServiceType.TECHNICAL_ANALYSIS,
            customer="13800000000",
        )
    )

    assert len(rows) == 2
    assert rows[1][1] == "openid-a"
    assert rows[1][4] == "新易盛 技术分析"


def test_request_records_keyword_search_matches_event_details(business_env):
    from business.config.constants import ServiceType
    from business.audit.event_service import record_request_event
    from business.records.records import create_request_record, list_request_records_page, succeed_request_record

    included = create_request_record("openid-event", "新易盛 技术分析", ServiceType.TECHNICAL_ANALYSIS)
    excluded = create_request_record("openid-other", "贵州茅台 技术分析", ServiceType.TECHNICAL_ANALYSIS)
    succeed_request_record(included, output_files=["/tmp/card.png"], elapsed_ms=1)
    succeed_request_record(excluded, output_files=["/tmp/other.png"], elapsed_ms=1)
    record_request_event(
        request_id=included,
        openid="openid-event",
        channel="wechatmp",
        event_type="reply_image_sent",
        message_type="image",
        content="客户回复 1 后发送 exclusive-event-card.png",
        file_path="/tmp/exclusive-event-card.png",
        result="success",
    )

    records, total = list_request_records_page(page=1, page_size=20, keyword="exclusive-event-card")

    assert total == 1
    assert [record.request_id for record in records] == [included]


def test_export_request_records_xlsx_uses_same_keyword_search_as_request_page(business_env):
    from business.config.constants import ServiceType
    from business.audit.event_service import record_request_event
    from business.records.export_service import export_request_records_xlsx
    from business.records.records import create_request_record, list_request_records_page, succeed_request_record

    included = create_request_record("openid-export-event", "利率", ServiceType.RATE)
    excluded = create_request_record("openid-export-other", "利率", ServiceType.RATE)
    succeed_request_record(included, output_files=["/tmp/rate.png"], elapsed_ms=1)
    succeed_request_record(excluded, output_files=["/tmp/other-rate.png"], elapsed_ms=1)
    record_request_event(
        request_id=included,
        openid="openid-export-event",
        channel="wechatmp",
        event_type="customer_confirm",
        message_type="text",
        content="客户确认导出一致性 unique-export-event",
        result="success",
    )

    page_records, page_total = list_request_records_page(page=1, page_size=20, service_type=ServiceType.RATE, keyword="unique-export-event")
    rows = _xlsx_sheet_rows(export_request_records_xlsx("", "", service_type=ServiceType.RATE, keyword="unique-export-event"))

    assert page_total == 1
    assert [record.openid for record in page_records] == ["openid-export-event"]
    assert [row[1] for row in rows[1:]] == ["openid-export-event"]


def test_export_request_records_xlsx_unknown_service_returns_only_header(business_env):
    from business.config.constants import ServiceType
    from business.records.export_service import export_request_records_xlsx
    from business.records.records import create_request_record, succeed_request_record

    request_id = create_request_record("openid", "利率", ServiceType.RATE)
    succeed_request_record(request_id, output_files=["/tmp/rate.png"], elapsed_ms=1)

    rows = _xlsx_sheet_rows(export_request_records_xlsx("", "", service_type="unknown-service"))

    assert rows == [
        [
            "请求时间",
            "OpenID",
            "客户姓名",
            "机构",
            "原始输入",
            "服务类型",
            "股票代码",
            "股票名称",
            "状态",
            "错误码",
            "错误原因",
            "缓存命中",
            "输出文件",
            "耗时毫秒",
            "程序版本",
            "模板版本",
        ]
    ]


def test_export_request_records_xlsx_empty_records_contains_only_header(business_env):
    from business.records.export_service import export_request_records_xlsx

    rows = _xlsx_sheet_rows(export_request_records_xlsx("2026-05-01T00:00:00", "2026-05-31T23:59:59"))

    assert len(rows) == 1
    assert rows[0][0] == "请求时间"


def test_export_users_xlsx_filters_enabled_users(business_env):
    from business.config.constants import ServiceType
    from business.records.export_service import export_users_xlsx
    from business.accounts.user_service import create_user

    create_user(
        "enabled-openid",
        name="Enabled",
        institution="Inst A",
        mobile="13800000000",
        enabled=True,
        allowed_services=[ServiceType.RATE],
        auth_start_at="2026-01-01T00:00:00",
        auth_end_at="2026-12-31T23:59:59",
        remark="ok",
    )
    create_user("disabled-openid", name="Disabled", enabled=False, allowed_services=[ServiceType.ALL])

    rows = _xlsx_sheet_rows(export_users_xlsx(enabled=True))

    assert rows == [
        ["OpenID", "姓名", "机构", "手机号", "状态", "服务权限", "授权开始", "授权结束", "备注"],
        [
            "enabled-openid",
            "Enabled",
            "Inst A",
            "13800000000",
            "启用",
            "rate",
            "2026-01-01T00:00:00",
            "2026-12-31T23:59:59",
            "ok",
        ],
    ]


def test_web_export_handlers_return_xlsx_downloads(business_env, monkeypatch):
    from channel.web import web_channel
    from channel.web.web_channel import InvestmentRequestRecordsExportHandler, InvestmentUsersExportHandler

    headers = []
    _login_default_investment_admin(monkeypatch)
    monkeypatch.setattr(web_channel.web, "header", lambda name, value: headers.append((name, value)))
    monkeypatch.setattr(
        web_channel.web,
        "input",
        lambda **_defaults: SimpleNamespace(start_date="2026-05-01", end_date="2026-05-31", service_type="", enabled=""),
    )

    request_data = InvestmentRequestRecordsExportHandler().GET()

    assert isinstance(request_data, bytes)
    assert _xlsx_sheet_rows(request_data)[0][0] == "请求时间"
    assert ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") in headers
    assert any(
        name == "Content-Disposition" and "investment-requests" in value and value.endswith(".xlsx\"")
        for name, value in headers
    )

    headers.clear()
    monkeypatch.setattr(web_channel.web, "input", lambda **_defaults: SimpleNamespace(enabled="true"))

    user_data = InvestmentUsersExportHandler().GET()

    assert isinstance(user_data, bytes)
    assert _xlsx_sheet_rows(user_data)[0][0] == "OpenID"
    assert ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") in headers
    assert any(
        name == "Content-Disposition" and "investment-users" in value and value.endswith(".xlsx\"")
        for name, value in headers
    )


def test_artifact_service_records_role_size_hash_and_version(business_env, tmp_path):
    from business.artifacts.artifact_service import record_artifact
    from business.config.constants import ServiceType
    from business.schema.db import connect
    from business.versioning import file_fingerprint

    artifact = tmp_path / "card.png"
    artifact.write_bytes(b"card-bytes")

    record_artifact(
        "request-1",
        str(artifact),
        "signal_card",
        ServiceType.TECHNICAL_ANALYSIS,
        version_tag="sha256:renderer123456",
    )

    with connect() as conn:
        row = conn.execute(
            text(
                "select owner_id, file_path, file_type, service, artifact_role, file_size, file_hash, version_tag "
                "from artifacts where owner_id = :owner_id"
            ),
            {"owner_id": "request-1"},
        ).mappings().one()

    assert row["file_path"] == str(artifact)
    assert row["file_type"] == "image"
    assert row["service"] == ServiceType.TECHNICAL_ANALYSIS
    assert row["artifact_role"] == "signal_card"
    assert row["file_size"] == len(b"card-bytes")
    assert row["file_hash"] == file_fingerprint(str(artifact))
    assert row["version_tag"] == "sha256:renderer123456"
    assert file_fingerprint(str(tmp_path / "missing.png")).startswith("missing:")


def test_artifact_service_records_same_artifact_idempotently(business_env, tmp_path):
    from business.artifacts.artifact_service import record_artifact
    from business.config.constants import ServiceType
    from business.schema.db import connect

    artifact = tmp_path / "card.png"
    artifact.write_bytes(b"card-bytes")

    record_artifact(
        "request-1",
        str(artifact),
        "signal_card",
        ServiceType.TECHNICAL_ANALYSIS,
        version_tag="sha256:first",
    )
    record_artifact(
        "request-1",
        str(artifact),
        "signal_card",
        ServiceType.TECHNICAL_ANALYSIS,
        version_tag="sha256:second",
    )

    with connect() as conn:
        rows = conn.execute(
            text(
                "select owner_id, file_path, artifact_role, version_tag "
                "from artifacts where owner_id = :owner_id"
            ),
            {"owner_id": "request-1"},
        ).mappings().all()

    assert len(rows) == 1
    assert rows[0]["file_path"] == str(artifact)
    assert rows[0]["artifact_role"] == "signal_card"
    assert rows[0]["version_tag"] == "sha256:second"


def test_ai_and_renderer_failures_record_sanitized_backend_detail(business_env, monkeypatch):
    from business.config import config_service as config_service
    from business.config.config_service import safe_log_value
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, regenerate_content
    from business.records.records import get_content_record

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


def test_ai_generation_uses_global_model_params_and_ignores_legacy_business_rows(business_env, monkeypatch):
    from business.audit.ai_generation import (
        AIGenerationRequest,
        generate_convertible_bond_text,
        generate_rate_text,
        generate_technical_analysis_text,
    )
    from business.config import config_service as config_service
    from business.schema import db as db
    from business.config.config_service import save_configs
    from business.config.constants import ServiceType, Status

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


def test_technical_analysis_default_prompt_matches_signal_card_renderer_contract(business_env, monkeypatch):
    from business.config import config_service as config_service
    from business.audit.ai_generation import build_generation_request
    from business.config.constants import ServiceType

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
        "【系统约束：标的名称】",
        "标的字段必须输出",
        "图片主标题由“📈 标的：”字段渲染而来",
        "股票字典中文名",
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
    from business.config import config_service as config_service
    from business.audit.ai_generation import _global_model_config

    monkeypatch.setattr(config_service, "conf", lambda: global_config)

    assert _global_model_config() == expected


def test_ai_generation_sends_image_source_files_as_multimodal_content(business_env, tmp_path, monkeypatch):
    from business.config import config_service as config_service
    from business.audit.ai_generation import ExistingModelAdapter, generate_rate_text

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

    class FakeBot:
        def __init__(self):
            self.calls = []

        def call_with_tools(self, **kwargs):
            self.calls.append(kwargs)
            return {"choices": [{"message": {"content": "standard rate text"}}]}

    bot = FakeBot()

    result = generate_rate_text("", source_files=[str(image_path)], adapter=ExistingModelAdapter(bot=bot))

    assert result.success is True
    messages = bot.calls[0]["messages"]
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


def test_ai_generation_retries_transient_model_connection_errors(business_env, monkeypatch):
    from business.config import config_service as config_service
    from business.audit.ai_generation import ExistingModelAdapter, generate_rate_text

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

    class FlakyBot:
        def __init__(self):
            self.calls = 0

        def call_with_tools(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {"error": True, "status_code": 0, "message": "Connection error: SSL EOF"}
            return {"choices": [{"message": {"content": "standard rate text"}}]}

    bot = FlakyBot()

    result = generate_rate_text("rate source", adapter=ExistingModelAdapter(bot=bot))

    assert result.success is True
    assert result.text == "standard rate text"
    assert bot.calls == 2


def test_ai_generation_extracts_image_text_before_final_card_prompt(business_env, tmp_path, monkeypatch):
    from business.config import config_service as config_service
    from business.audit.ai_generation import ExistingModelAdapter, generate_rate_text

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

    class FakeBot:
        def __init__(self):
            self.calls = []

        def call_with_tools(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return {"choices": [{"message": {"content": "OCR: 2026-05-25 108.970 入场（3/8）"}}]}
            return {"choices": [{"message": {"content": "standard rate card text"}}]}

    bot = FakeBot()

    result = generate_rate_text("", source_files=[str(image_path)], adapter=ExistingModelAdapter(bot=bot))

    assert result.success is True
    assert result.text == "standard rate card text"
    assert len(bot.calls) == 2
    assert any(block.get("type") == "image_url" for block in bot.calls[0]["messages"][1]["content"])
    assert bot.calls[1]["messages"][1]["content"] == (
        "以下是上传图片的识别结果，请据此生成标准卡片文本。禁止要求用户再提供原文；"
        "缺失字段按系统要求填“——”。\n\nOCR: 2026-05-25 108.970 入场（3/8）"
    )


def test_ai_generation_blank_configured_prompt_falls_back_to_default(business_env):
    from business.audit.ai_generation import AIGenerationRequest, generate_rate_text
    from business.config.config_service import save_config

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


def test_ai_generation_normalizes_semicolon_rate_text_for_renderer(business_env):
    from business.audit.ai_generation import AIGenerationRequest, generate_rate_text

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


def test_ai_generation_normalizes_multiline_inline_rate_text_for_renderer(business_env):
    from business.audit.ai_generation import AIGenerationRequest, generate_rate_text

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


def test_ai_generation_failures_and_health_check_sanitize_model_config(business_env, monkeypatch):
    from business.config import config_service as config_service
    from business.audit.ai_generation import AIGenerationRequest, generate_rate_text
    from business.config.constants import ErrorCode, Status
    from business.health.health import run_health_checks

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


def test_model_health_check_accepts_global_config_fallback(business_env, monkeypatch):
    from business.config import config_service as config_service
    from business.health.health import run_health_checks

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


def test_ai_generation_default_adapter_uses_bridge_bot_call_with_tools(business_env, monkeypatch):
    from business.config import config_service as config_service
    from business.audit import ai_generation as ai_generation
    from business.audit.ai_generation import generate_rate_text
    from business.config.config_service import save_configs

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

    def fail_default_client():
        raise AssertionError("investment AI generation must not bypass Bridge via default HTTP client")

    monkeypatch.setattr("models.openai.openai_http_client.get_default_client", fail_default_client)

    class FakeBot:
        def __init__(self):
            self.calls = []

        def call_with_tools(self, **kwargs):
            self.calls.append(kwargs)
            return {"choices": [{"message": {"content": "standard rate text"}}]}

    bot = FakeBot()

    class FakeBridge:
        def get_bot(self, typename):
            assert typename == "chat"
            return bot

    monkeypatch.setattr(ai_generation, "Bridge", lambda: FakeBridge())

    result = generate_rate_text("rate source")

    assert result.success is True
    assert result.generated_text == "standard rate text"
    assert bot.calls == [
        {
            "model": "configured-model",
            "messages": [
                {"role": "system", "content": "Configured rate prompt"},
                {"role": "user", "content": "rate source"},
            ],
            "tools": None,
            "temperature": 0.33,
            "stream": False,
        }
    ]


def test_technical_analysis_failure_records_sanitized_backend_detail(business_env, monkeypatch):
    from business.config import config_service as config_service
    from business.config.constants import ErrorCode, ServiceType
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.content.technical_analysis import TechnicalAnalysisResult
    from business.accounts.user_service import create_user

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
    assert "skill crashed" in reply.reply_text
    assert api_key not in reply.reply_text
    assert record.error_code == ErrorCode.TECHNICAL_ANALYSIS_FAILED
    assert "skill crashed" in record.error_message
    assert api_key not in record.error_message


def test_technical_analysis_uses_skill_cli_symbol_and_saves_all_outputs(business_env, tmp_path, monkeypatch):
    from business.content import technical_analysis as technical_analysis
    from business.content.technical_analysis import TechnicalAnalysisRequest, run_technical_analysis

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
        calls.append(("skill", symbol, output_dir.parent.name, output_dir.name))
        return report, chart

    def fake_ai(report_text):
        calls.append(("ai", report_text))
        return SimpleNamespace(
            success=True,
            text=(
                "【浙商固收 | 智能投研辅助系统】\n"
                "📈 标的：300502.SZ（300502.SZ）\n"
                "[庆祝] 信号方向：区间观望\n"
                "💰 最新收盘：748.00 元\n"
                "📅 行情日期：2026-05-29  日内涨幅：+1.00%\n"
                "🔧 分析模型：技术分析体系\n\n"
                "📊 趋势研判\n"
                "区间震荡。\n"
                "▪️ 方向确认：趋势中性。\n\n"
                "🎯 核心关键位\n"
                "▪️ 强压力：760.00（前高）\n"
                "▪️ 强支撑：720.00（MA20）\n\n"
                "💡 实操指引\n"
                "观察突破和跌破。\n"
                "⚠️ 本内容仅供研究参考，不构成任何投资建议\n"
                "⏱️ 授权剩余时间：——\n"
                "📚 数据来源：AKShare\n"
                "🤝 业务对接：——"
            ),
        )

    def fake_render(standard_text, output_path):
        calls.append(("render", standard_text, Path(output_path).name))
        Path(output_path).write_bytes(b"card")
        return SimpleNamespace(success=True, image_path=str(output_path), detail="")

    monkeypatch.setattr(technical_analysis, "_run_skill", fake_skill)
    monkeypatch.setattr(technical_analysis, "generate_technical_analysis_text", fake_ai)
    monkeypatch.setattr(technical_analysis, "render_technical_analysis_card", fake_render)

    class FakeResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "300502.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="2026-05-29", known=True, source="fake")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", FakeResolver, raising=False)

    result = run_technical_analysis("ok", "300502.SZ 技术分析")

    assert result.success is True
    assert calls[0][0:3] == ("skill", "300502", "300502_SZ")
    assert len(calls[0][3]) == 32
    assert calls[1][0] == "ai"
    assert "# 技术分析报告\n\n核心观点" in calls[1][1]
    assert "📈 标的：300502.SZ" in calls[2][1]
    assert calls[2][2].startswith("300502_SZ_signal_card_2026-05-29_")
    assert calls[2][2].endswith(".png")
    assert result.report_path == str(report)
    assert result.main_chart_path == str(chart)
    assert Path(result.signal_card_path).name == calls[2][2]
    assert result.output_files == [result.signal_card_path, str(chart), str(report)]
    assert result.market_date == "2026-05-29"
    assert "2026-05-29" in result.cache_key
    assert result.normalized_target == "300502.SZ"
    assert result.stock_code == "300502.SZ"
    assert result.stock_name == ""


@pytest.mark.parametrize(
    ("raw_input", "normalized_target", "skill_symbol"),
    [
        ("AAPL.US 技术分析", "AAPL.US", "AAPL.US"),
        ("US:AAPL 技术分析", "AAPL.US", "AAPL.US"),
        ("hk00700 技术分析", "00700.HK", "HK00700"),
        ("00700.HK 技术分析", "00700.HK", "HK00700"),
        ("GC 技术分析", "GC", "GC"),
        ("COMEX_GOLD 技术分析", "GC", "GC"),
    ],
)
def test_technical_analysis_non_a_share_targets_are_delegated_to_skill(
    business_env, tmp_path, monkeypatch, raw_input, normalized_target, skill_symbol
):
    from business.content import technical_analysis as technical_analysis
    from business.content.technical_analysis import run_technical_analysis

    calls = []
    report = tmp_path / "asset_技术分析报告_2026-05-25.md"
    chart = tmp_path / "asset_TA_2026-05-25.png"
    report.write_text("ta report", encoding="utf-8")
    chart.write_bytes(b"chart")

    def fake_skill(symbol, _output_dir):
        calls.append(("skill", symbol))
        return report, chart

    class FailResolver:
        def resolve(self, *_args, **_kwargs):
            pytest.fail("non-A-share targets should not enter A-share market date resolver")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", FailResolver, raising=False)
    monkeypatch.setattr(technical_analysis, "_run_skill", fake_skill)
    monkeypatch.setattr(
        technical_analysis,
        "generate_technical_analysis_text",
        lambda _report_text: SimpleNamespace(success=True, text="行情日期：2026-05-25\nstandard"),
    )

    def fake_render(_standard_text, output_path):
        Path(output_path).write_bytes(b"card")
        return SimpleNamespace(success=True, image_path=str(output_path), detail="")

    monkeypatch.setattr(technical_analysis, "render_technical_analysis_card", fake_render)

    result = run_technical_analysis("ok", raw_input)

    assert result.success is True
    assert calls == [("skill", skill_symbol)]
    assert result.normalized_target == normalized_target
    assert result.stock_code == normalized_target
    assert result.stock_name == ""


@pytest.mark.parametrize(
    ("raw_input", "dictionary_code", "expected_normalized", "expected_skill_symbol"),
    [
        ("新易盛 技术分析", "300502.SZ", "300502.SZ", "300502"),
        ("腾讯控股 技术分析", "00700.HK", "00700.HK", "HK00700"),
        ("苹果 技术分析", "AAPL.US", "AAPL.US", "AAPL.US"),
    ],
)
def test_technical_analysis_resolves_tushare_dictionary_names_before_skill(
    business_env, tmp_path, monkeypatch, raw_input, dictionary_code, expected_normalized, expected_skill_symbol
):
    from business.content import technical_analysis as technical_analysis
    from business.content.stock_resolver import refresh_stock_symbols
    from business.content.technical_analysis import run_technical_analysis

    name = raw_input.replace(" 技术分析", "")
    market = dictionary_code.rsplit(".", 1)[1]
    source = "tushare_a" if market in {"SZ", "SH"} else f"tushare_{market.lower()}"
    refresh_stock_symbols(
        [{"code": dictionary_code, "name": name, "market": market, "source": source}],
        source=source,
    )
    calls = []
    report = tmp_path / "name_技术分析报告_2026-05-25.md"
    chart = tmp_path / "name_TA_2026-05-25.png"
    report.write_text("ta report", encoding="utf-8")
    chart.write_bytes(b"chart")

    def fake_skill(symbol, _output_dir):
        calls.append(symbol)
        return report, chart

    monkeypatch.setattr(technical_analysis, "_run_skill", fake_skill)
    ai_inputs = []

    def fake_ai(report_text):
        ai_inputs.append(report_text)
        return SimpleNamespace(success=True, text="📈 标的：WRONG\n行情日期：2026-05-25\nstandard")

    monkeypatch.setattr(technical_analysis, "generate_technical_analysis_text", fake_ai)

    rendered_texts = []

    def fake_render(standard_text, output_path):
        rendered_texts.append(standard_text)
        Path(output_path).write_bytes(b"card")
        return SimpleNamespace(success=True, image_path=str(output_path), detail="")

    monkeypatch.setattr(technical_analysis, "render_technical_analysis_card", fake_render)

    result = run_technical_analysis("ok", raw_input)

    assert result.success is True
    assert calls == [expected_skill_symbol]
    assert result.normalized_target == expected_normalized
    assert result.stock_code == expected_normalized
    assert result.stock_name == name
    assert f"- 中文名称：{name}" in ai_inputs[0]
    assert f"- 标的字段必须输出：{name}（{expected_normalized}）" in ai_inputs[0]
    assert f"📈 标的：{name}（{expected_normalized}）" in rendered_texts[0]
    assert "📈 标的：WRONG" not in rendered_texts[0]


def test_technical_analysis_code_input_uses_dictionary_chinese_name_in_signal_card(
    business_env, tmp_path, monkeypatch
):
    from business.content import technical_analysis as technical_analysis
    from business.content.stock_resolver import refresh_stock_symbols
    from business.content.technical_analysis import run_technical_analysis

    refresh_stock_symbols(
        [{"code": "300502.SZ", "name": "新易盛", "market": "SZ", "source": "tushare_a"}],
        source="tushare_a",
    )
    report = tmp_path / "code_技术分析报告_2026-05-25.md"
    chart = tmp_path / "code_TA_2026-05-25.png"
    report.write_text("ta report", encoding="utf-8")
    chart.write_bytes(b"chart")

    monkeypatch.setattr(technical_analysis, "_run_skill", lambda _symbol, _output_dir: (report, chart))
    ai_inputs = []

    def fake_ai(report_text):
        ai_inputs.append(report_text)
        return SimpleNamespace(success=True, text="📈 标的：300502.SZ\n行情日期：2026-05-25\nstandard")

    monkeypatch.setattr(technical_analysis, "generate_technical_analysis_text", fake_ai)
    rendered_texts = []

    def fake_render(standard_text, output_path):
        rendered_texts.append(standard_text)
        Path(output_path).write_bytes(b"card")
        return SimpleNamespace(success=True, image_path=str(output_path), detail="")

    monkeypatch.setattr(technical_analysis, "render_technical_analysis_card", fake_render)

    result = run_technical_analysis("ok", "300502.SZ 技术分析")

    assert result.success is True
    assert result.stock_name == "新易盛"
    assert "- 中文名称：新易盛" in ai_inputs[0]
    assert "- 标的字段必须输出：新易盛（300502.SZ）" in ai_inputs[0]
    assert "📈 标的：新易盛（300502.SZ）" in rendered_texts[0]


@pytest.mark.parametrize(
    ("raw_input", "expected_detail"),
    [
        ("不存在 技术分析", "cannot resolve stock name"),
        ("重名 技术分析", "匹配到多个标的"),
    ],
)
def test_technical_analysis_name_miss_or_ambiguity_fails_with_code_prompt(
    business_env, tmp_path, monkeypatch, raw_input, expected_detail
):
    from business.content import technical_analysis as technical_analysis
    from business.config.constants import ErrorCode
    from business.content.stock_resolver import refresh_stock_symbols
    from business.content.technical_analysis import run_technical_analysis

    refresh_stock_symbols(
        [
            {"code": "000001.SZ", "name": "重名", "market": "SZ", "source": "tushare_a"},
            {"code": "A00001.US", "name": "重名", "market": "US", "source": "tushare_us"},
        ],
        source="pytest",
    )
    monkeypatch.setattr(technical_analysis, "_run_skill", lambda *_args, **_kwargs: pytest.fail("invalid names must not enter skill"))

    result = run_technical_analysis("ok", raw_input)

    assert result.success is False
    assert result.error_code in {ErrorCode.STOCK_NOT_FOUND, ErrorCode.STOCK_AMBIGUOUS}
    assert "股票代码" in result.user_prompt
    assert expected_detail in result.detail


def test_technical_analysis_ambiguous_name_lists_candidate_codes(business_env, monkeypatch):
    from business.content import technical_analysis as technical_analysis
    from business.config.constants import ErrorCode
    from business.content.stock_resolver import refresh_stock_symbols
    from business.content.technical_analysis import run_technical_analysis

    refresh_stock_symbols(
        [
            {"code": "601398.SH", "name": "工商银行", "market": "SH", "source": "tushare_a"},
            {"code": "01398.HK", "name": "工商银行", "market": "HK", "source": "tushare_hk"},
        ],
        source="pytest",
    )
    monkeypatch.setattr(technical_analysis, "_run_skill", lambda *_args, **_kwargs: pytest.fail("ambiguous names must not enter skill"))

    result = run_technical_analysis("ok", "工商银行 技术分析")

    assert result.success is False
    assert result.error_code == ErrorCode.STOCK_AMBIGUOUS
    assert result.detail == (
        "股票名称“工商银行”匹配到多个标的，请改用股票代码重新发送：\n"
        "1. 01398.HK 工商银行（HK）\n"
        "2. 601398.SH 工商银行（SH）\n"
        "例如：601398.SH 技术分析"
    )


def test_technical_analysis_success_records_customer_target_versions_and_artifact_roles(business_env, tmp_path):
    from business.cache.cache_service import find_cache_entry_by_key
    from business.config.constants import ServiceType
    from business.schema.db import connect
    from business.records.records import get_content_record, list_request_records
    from business.routing.router import handle_text_message
    from business.schema.storage import get_storage_dirs
    from business.content.technical_analysis import TechnicalAnalysisResult
    from business.accounts.user_service import create_user

    card = tmp_path / "signal.png"
    chart = tmp_path / "chart.png"
    report = tmp_path / "report.md"
    card.write_bytes(b"card")
    chart.write_bytes(b"chart")
    report.write_text("report", encoding="utf-8")
    create_user("ok", name="Alice", institution="Inst A", enabled=True, allowed_services=[ServiceType.ALL])

    reply = handle_text_message(
        "ok",
        "新易盛 技术分析",
        technical_analysis_handler=lambda _openid, _raw_input, _target: TechnicalAnalysisResult(
            True,
            signal_card_path=str(card),
            main_chart_path=str(chart),
            report_path=str(report),
            output_files=[str(card), str(chart), str(report)],
            normalized_target="300502.SZ",
            stock_code="300502.SZ",
            stock_name="新易盛",
            market_date="2026-05-25",
            program_version="sha256:program12345678",
            ta_version="sha256:ta123456789012",
            renderer_version="sha256:renderer123456",
            template_version="sha256:template123456",
            version_fingerprint="sha256:combined123456",
            cache_key="technical_analysis:300502.SZ:2026-05-25:pytest",
        ),
    )

    record = list_request_records(limit=1)[0]
    cache_entry = find_cache_entry_by_key("technical_analysis:300502.SZ:2026-05-25:pytest")
    files_root = get_storage_dirs()["files"]
    assert reply.success is True
    assert record.customer_name == "Alice"
    assert record.institution == "Inst A"
    assert record.normalized_target == "300502.SZ"
    assert record.stock_code == "300502.SZ"
    assert record.stock_name == "新易盛"
    assert record.market_date == "2026-05-25"
    assert record.program_version.startswith("sha256:")
    assert record.ta_version.startswith("sha256:")
    assert record.renderer_version.startswith("sha256:")
    assert record.template_version.startswith("sha256:")

    with connect() as conn:
        rows = conn.execute(
            text(
                "select file_path, artifact_role, file_size, file_hash, version_tag "
                "from artifacts where owner_id = :owner_id order by id"
            ),
            {"owner_id": record.request_id},
        ).mappings().all()

    artifact_paths = [row["file_path"] for row in rows]
    assert [(Path(row["file_path"]).is_file(), row["artifact_role"]) for row in rows] == [
        (True, "signal_card"),
        (True, "main_chart"),
        (True, "markdown_report"),
    ]
    assert all(Path(path).resolve().is_relative_to(files_root.resolve()) for path in artifact_paths)
    for path in artifact_paths:
        parts = Path(path).parts
        files_index = parts.index("files")
        assert parts[files_index + 1 : files_index + 5] == (
            str(ServiceType.TECHNICAL_ANALYSIS),
            "2026-05-25",
            "request",
            record.request_id,
        )
    assert artifact_paths != [str(card), str(chart), str(report)]
    assert record.output_files == artifact_paths
    assert cache_entry is not None
    assert cache_entry.output_files == artifact_paths
    assert reply.output_files == artifact_paths[:2]
    assert all(row["file_size"] > 0 for row in rows)
    assert all(str(row["file_hash"]).startswith("sha256:") for row in rows)
    assert [row["version_tag"] for row in rows] == [
        "sha256:renderer123456",
        "sha256:ta123456789012",
        "sha256:ta123456789012",
    ]


def _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path, generated_market_date="2026-05-25"):
    from business.content import technical_analysis as technical_analysis
    calls = []

    monkeypatch.setattr(
        technical_analysis,
        "_versions",
        lambda: ("sha256:program-v1", "sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1"),
    )

    def fake_skill(symbol, output_dir):
        calls.append(("skill", symbol, len(calls)))
        report = tmp_path / f"{symbol}_技术分析报告_{generated_market_date}_{len(calls)}.md"
        chart = tmp_path / f"{symbol}_TA_{generated_market_date}_{len(calls)}.png"
        report.write_text(f"报告日期：{generated_market_date}\n核心观点", encoding="utf-8")
        chart.write_bytes(b"chart")
        return report, chart

    def fake_ai(report_text):
        calls.append(("ai", report_text))
        return SimpleNamespace(success=True, text=f"日期：{generated_market_date}\n信号卡标准文本")

    def fake_render(_standard_text, output_path):
        calls.append(("render", Path(output_path).name))
        Path(output_path).write_bytes(b"card")
        return SimpleNamespace(success=True, image_path=str(output_path), detail="")

    monkeypatch.setattr(technical_analysis, "_run_skill", fake_skill)
    monkeypatch.setattr(technical_analysis, "generate_technical_analysis_text", fake_ai)
    monkeypatch.setattr(technical_analysis, "render_technical_analysis_card", fake_render)
    return calls


def _write_legacy_technical_analysis_cache(
    tmp_path,
    *,
    normalized_target,
    market_date,
    version_fingerprint,
    program_version="sha256:old-program",
    ta_version="sha256:ta-v1",
    renderer_version="sha256:renderer-v1",
    template_version="sha256:template-v1",
):
    from business.cache.cache_service import build_cache_key, write_cache_entry
    from business.config.constants import ServiceType
    from business.records.records import create_request_record, succeed_request_record

    cached_card = tmp_path / f"cached-card-{market_date}.png"
    cached_chart = tmp_path / f"cached-chart-{market_date}.png"
    cached_report = tmp_path / f"cached-report-{market_date}.md"
    cached_card.write_bytes(f"cached-card-{market_date}".encode("utf-8"))
    cached_chart.write_bytes(f"cached-chart-{market_date}".encode("utf-8"))
    cached_report.write_text(f"cached report {market_date}", encoding="utf-8")
    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, normalized_target, market_date, version_fingerprint)
    request_id = create_request_record(
        "ok",
        f"{normalized_target} 技术分析",
        ServiceType.TECHNICAL_ANALYSIS,
        normalized_target=normalized_target,
    )
    succeed_request_record(
        request_id,
        output_files=[str(cached_card), str(cached_chart), str(cached_report)],
        elapsed_ms=1,
        normalized_target=normalized_target,
        stock_code=normalized_target,
        stock_name=normalized_target,
        market_date=market_date,
        cache_key=cache_key,
        program_version=program_version,
        ta_version=ta_version,
        renderer_version=renderer_version,
        template_version=template_version,
    )
    write_cache_entry(
        cache_key=cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target=normalized_target,
        market_date=market_date,
        version_fingerprint=version_fingerprint,
        output_files=[str(cached_card), str(cached_chart), str(cached_report)],
        artifact_owner_id=request_id,
    )
    return cache_key, [str(cached_card), str(cached_chart), str(cached_report)]


def test_technical_analysis_compatible_cache_reads_products_not_cache_entries(
    business_env, tmp_path, monkeypatch
):
    from business.cache.cache_service import build_cache_key, version_fingerprint
    from business.config.constants import ServiceType
    from business.content import technical_analysis
    from business.products.product_service import create_product
    from business.records.records import create_request_record, succeed_request_record

    output = tmp_path / "compatible-product-cache.png"
    output.write_text("compatible", encoding="utf-8")
    vf = version_fingerprint("compatible-product-cache")
    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "002354.SZ", "2026-06-25", vf)
    request_id = create_request_record(
        "ok",
        "天娱数科 技术分析",
        ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="002354.SZ",
    )
    succeed_request_record(
        request_id,
        output_files=[str(output)],
        elapsed_ms=1,
        normalized_target="002354.SZ",
        stock_code="002354.SZ",
        stock_name="天娱数科",
        market_date="2026-06-25",
        cache_key=cache_key,
        ta_version="ta-product-compatible",
        renderer_version="renderer-product-compatible",
        template_version="template-product-compatible",
    )
    create_product(
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        target_key="002354.SZ",
        target_label="天娱数科",
        business_date="2026-06-25",
        version_fingerprint=vf,
        status="active",
        source_request_id=request_id,
        source_cache_key=cache_key,
        source_type="cache",
        output_files=[str(output)],
    )
    monkeypatch.setattr(technical_analysis, "technical_analysis_cache_expired_after_close", lambda *args, **kwargs: False)

    cached = technical_analysis._find_compatible_cache_entry_for_market_date(
        symbol="002354.SZ",
        market_date="2026-06-25",
        current_version_fingerprint="different-current-vf",
        ta_version="ta-product-compatible",
        renderer_version="renderer-product-compatible",
        template_version="template-product-compatible",
    )

    assert cached is not None
    assert cached.cache_key == cache_key
    assert cached.normalized_target == "002354.SZ"
    assert cached.market_date == "2026-06-25"
    assert cached.version_fingerprint == vf
    assert cached.output_files == [str(output)]


def test_technical_analysis_reuses_cached_outputs_without_explicit_date_when_resolver_confirms_market_date(
    business_env, tmp_path, monkeypatch
):
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import list_cache_entries
    from business.config.constants import ServiceType
    from business.products.product_service import list_products_page
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    calls = _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path)

    class FakeResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "300502.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="2026-05-25", known=True, source="fake")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", FakeResolver, raising=False)

    first = handle_text_message("ok", "300502.SZ 技术分析")
    second = handle_text_message("ok", "300502.SZ 技术分析")

    assert first.success is True
    assert second.success is True
    assert second.output_files == first.output_files
    assert [call[0] for call in calls] == ["skill", "ai", "render"]

    records = list_request_records(limit=2)
    assert records[0].cache_hit is True
    assert records[1].cache_hit is False
    assert records[0].cache_key == records[1].cache_key
    assert second.source_type == "product"
    assert second.source_id == records[0].cache_key
    products, product_total = list_products_page(business_type=str(ServiceType.TECHNICAL_ANALYSIS))
    assert product_total == 1
    assert products[0]["hit_count"] == 1
    cache_entry = list_cache_entries(service_type=ServiceType.TECHNICAL_ANALYSIS)[0]
    assert cache_entry.hit_count == 1
    assert cache_entry.market_date == "2026-05-25"
    assert cache_entry.artifact_owner_id == records[1].request_id


def test_technical_analysis_reuses_today_cache_before_close_cutoff(
    business_env, tmp_path, monkeypatch
):
    from zoneinfo import ZoneInfo

    from business.cache import cache_policy as cache_policy
    from business.content import technical_analysis as technical_analysis
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.config.constants import ServiceType
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    calls = _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path, generated_market_date="2026-05-29")
    monkeypatch.setattr(
        cache_policy,
        "beijing_now",
        lambda: datetime(2026, 5, 29, 15, 29, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    class FakeResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "300502.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="2026-05-29", known=True, source="fake")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", FakeResolver, raising=False)

    first = handle_text_message("ok", "300502.SZ 技术分析")
    second = handle_text_message("ok", "300502.SZ 技术分析")

    assert first.success is True
    assert second.success is True
    assert second.output_files == first.output_files
    assert [call[0] for call in calls] == ["skill", "ai", "render"]
    records = list_request_records(limit=2)
    assert records[0].cache_hit is True
    assert records[1].cache_hit is False


def test_technical_analysis_invalidates_today_intraday_cache_after_close_and_reruns(
    business_env, tmp_path, monkeypatch
):
    from zoneinfo import ZoneInfo

    from business.cache import cache_policy as cache_policy
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import list_cache_entries
    from business.config.constants import ServiceType
    from business.products.product_service import list_products_page
    from business.schema.db import connect
    from business.config.config_service import save_config
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.schema.tables import investment_products
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    save_config("investment.technical_analysis.cache_close_invalidate_time", "15:30", operator_role="admin")
    calls = _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path, generated_market_date="2026-05-29")
    monkeypatch.setattr(
        cache_policy,
        "beijing_now",
        lambda: datetime(2026, 5, 29, 15, 31, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    class FakeResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "300502.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="2026-05-29", known=True, source="fake")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", FakeResolver, raising=False)

    first = handle_text_message("ok", "300502.SZ 技术分析")
    assert first.success is True
    first_record = list_request_records(limit=1)[0]
    products, product_total = list_products_page(business_type=str(ServiceType.TECHNICAL_ANALYSIS))
    assert product_total == 1
    first_product_id = products[0]["product_id"]
    with connect() as conn:
        conn.execute(
            investment_products.update()
            .where(investment_products.c.source_cache_key == first_record.cache_key)
            .values(updated_at="2026-05-29T07:00:00+00:00")
        )

    second = handle_text_message("ok", "300502.SZ 技术分析")

    assert second.success is True
    assert second.output_files != first.output_files
    assert [call[0] for call in calls] == ["skill", "ai", "render", "skill", "ai", "render"]
    records = list_request_records(limit=2)
    assert records[0].cache_hit is False
    assert records[1].cache_hit is False
    assert records[0].cache_key == records[1].cache_key
    cache_entry = list_cache_entries(service_type=ServiceType.TECHNICAL_ANALYSIS)[0]
    assert cache_entry.hit_count == 0
    assert cache_entry.status == "active"
    products, product_total = list_products_page(
        include_invalidated=True,
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
    )
    assert product_total == 2
    assert [product["status"] for product in products].count("active") == 1
    assert [product["status"] for product in products].count("invalidated") == 1
    assert any(product["product_id"] == first_product_id and product["status"] == "invalidated" for product in products)


def test_technical_analysis_keeps_previous_trading_day_cache_after_close(
    business_env, tmp_path, monkeypatch
):
    from zoneinfo import ZoneInfo

    from business.cache import cache_policy as cache_policy
    from business.content import technical_analysis as technical_analysis
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.config.constants import ServiceType
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    calls = _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path, generated_market_date="2026-05-28")
    monkeypatch.setattr(
        cache_policy,
        "beijing_now",
        lambda: datetime(2026, 5, 29, 15, 31, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    class FakeResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "300502.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="2026-05-28", known=True, source="fake")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", FakeResolver, raising=False)

    first = handle_text_message("ok", "300502.SZ 技术分析")
    second = handle_text_message("ok", "300502.SZ 技术分析")

    assert first.success is True
    assert second.success is True
    assert second.output_files == first.output_files
    assert [call[0] for call in calls] == ["skill", "ai", "render"]
    records = list_request_records(limit=2)
    assert records[0].cache_hit is True
    assert records[1].cache_hit is False
    assert records[0].market_date == "2026-05-28"


def test_technical_analysis_missing_cache_file_invalidates_and_reruns(
    business_env, tmp_path, monkeypatch
):
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import list_cache_entries
    from business.config.constants import ServiceType
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    calls = _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path)

    class FakeResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "300502.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="2026-05-25", known=True, source="fake")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", FakeResolver, raising=False)

    first = handle_text_message("ok", "300502.SZ 技术分析")
    assert first.success is True
    Path(first.output_files[0]).unlink()

    second = handle_text_message("ok", "300502.SZ 技术分析")

    assert second.success is True
    assert second.output_files != first.output_files
    assert [call[0] for call in calls] == ["skill", "ai", "render", "skill", "ai", "render"]
    records = list_request_records(limit=2)
    assert records[0].cache_hit is False
    assert records[1].cache_hit is False
    assert records[0].cache_key == records[1].cache_key
    cache_entry = list_cache_entries(service_type=ServiceType.TECHNICAL_ANALYSIS)[0]
    assert cache_entry.status == "active"
    assert cache_entry.artifact_owner_id == records[0].request_id


def test_technical_analysis_cache_write_failure_does_not_leave_active_cache(business_env, tmp_path, monkeypatch):
    from business.cache import cache_service as cache_service
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import list_cache_entries
    from business.config.constants import ServiceType, Status
    from business.schema.db import connect
    from business.records.records import get_request_record, list_request_records
    from business.routing.router import handle_text_message
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path)

    class FakeResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "300502.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="2026-05-25", known=True, source="fake")

    def fail_router_cache_write(**_kwargs):
        raise RuntimeError("cache write failed after generation")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", FakeResolver, raising=False)
    monkeypatch.setattr(cache_service, "write_cache_entry", fail_router_cache_write)

    reply = handle_text_message("ok", "300502.SZ 技术分析")

    assert reply.success is False
    assert reply.error_code is not None
    assert list_cache_entries(service_type=ServiceType.TECHNICAL_ANALYSIS) == []
    request_record = get_request_record(list_request_records(limit=1)[0].request_id)
    assert request_record.status == Status.FAILED
    assert request_record.output_files == []
    assert request_record.cache_key == ""
    assert request_record.market_date == ""
    assert request_record.cache_hit is False
    with connect() as conn:
        artifact_count = conn.execute(
            text("select count(*) from artifacts where owner_id = :request_id"),
            {"request_id": request_record.request_id},
        ).scalar_one()
    assert artifact_count == 0


def test_router_default_technical_analysis_resolver_once_reuses_preview_resolution(
    business_env, tmp_path, monkeypatch
):
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import list_cache_entries
    from business.config.constants import ServiceType
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path)
    resolver_calls = []

    class CountingResolver:
        def resolve(self, symbol, requested_market_date=""):
            resolver_calls.append((symbol, requested_market_date))
            return SimpleNamespace(market_date="2026-05-25", known=True, source="fake")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", CountingResolver, raising=False)

    reply = handle_text_message("ok", "300502.SZ 技术分析")

    assert reply.success is True
    assert resolver_calls == [("300502.SZ", "")]
    record = list_request_records(limit=1)[0]
    cache_entry = list_cache_entries(service_type=ServiceType.TECHNICAL_ANALYSIS)[0]
    assert record.cache_key == cache_entry.cache_key
    assert record.market_date == "2026-05-25"


def test_technical_analysis_lock_cache_key_uses_resolver_date_over_generated_date(
    business_env, tmp_path, monkeypatch
):
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import list_cache_entries
    from business.config.constants import ServiceType
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path, generated_market_date="2026-05-26")

    class FakeResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "300502.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="2026-05-25", known=True, source="fake")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", FakeResolver, raising=False)

    reply = handle_text_message("ok", "300502.SZ 技术分析")

    assert reply.success is True
    record = list_request_records(limit=1)[0]
    cache_entry = list_cache_entries(service_type=ServiceType.TECHNICAL_ANALYSIS)[0]
    assert record.market_date == "2026-05-25"
    assert "2026-05-25" in record.cache_key
    assert record.cache_key == cache_entry.cache_key
    assert cache_entry.market_date == "2026-05-25"


def test_technical_analysis_explicit_market_date_keeps_specified_cache_date(business_env, tmp_path, monkeypatch):
    from business.content import technical_analysis as technical_analysis
    from business.content.market_date_resolver import MarketDateResolver
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.config.constants import ServiceType
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    calls = _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path)
    monkeypatch.setattr(
        MarketDateResolver,
        "_latest_market_date",
        lambda _self, _symbol: SimpleNamespace(market_date="2026-05-26", known=True, source="latest"),
    )
    monkeypatch.setattr(technical_analysis, "MarketDateResolver", MarketDateResolver, raising=False)

    first = handle_text_message("ok", "300502.SZ 2026-05-25 技术分析")
    second = handle_text_message("ok", "300502.SZ 2026-05-25 技术分析")

    assert first.success is True
    assert second.success is True
    assert second.output_files == first.output_files
    assert [call[0] for call in calls] == ["skill", "ai", "render"]

    records = list_request_records(limit=2)
    assert records[0].cache_hit is True
    assert records[1].cache_hit is False
    assert records[0].cache_key == records[1].cache_key
    assert second.source_type == "product"
    assert second.source_id == records[0].cache_key
    assert records[0].market_date == "2026-05-25"
    assert records[1].market_date == "2026-05-25"


def test_technical_analysis_explicit_market_date_overrides_generated_output_date(
    business_env, tmp_path, monkeypatch
):
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import list_cache_entries
    from business.config.constants import ServiceType
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    calls = _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path, generated_market_date="2026-05-26")

    class FakeResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "300502.SZ"
            assert requested_market_date == "2026-05-25"
            return SimpleNamespace(market_date="2026-05-25", known=True, source="explicit")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", FakeResolver, raising=False)

    first = handle_text_message("ok", "300502.SZ 2026-05-25 技术分析")
    second = handle_text_message("ok", "300502.SZ 2026-05-25 技术分析")

    assert first.success is True
    assert second.success is True
    assert second.output_files == first.output_files
    assert [call[0] for call in calls] == ["skill", "ai", "render"]

    records = list_request_records(limit=2)
    assert records[0].cache_hit is True
    assert records[1].cache_hit is False
    assert records[0].market_date == "2026-05-25"
    assert records[1].market_date == "2026-05-25"
    assert records[0].cache_key == records[1].cache_key
    assert "2026-05-25" in records[0].cache_key
    cache_entry = list_cache_entries(service_type=ServiceType.TECHNICAL_ANALYSIS)[0]
    assert cache_entry.market_date == "2026-05-25"
    assert "2026-05-25" in cache_entry.cache_key


def test_technical_analysis_unknown_market_date_reuses_recent_latest_cache(
    business_env, tmp_path, monkeypatch
):
    from business.cache import cache_service as cache_service
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import build_cache_key, list_cache_entries, version_fingerprint, write_cache_entry
    from business.config.constants import ServiceType
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.content.stock_resolver import refresh_stock_symbols
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    refresh_stock_symbols([{"code": "002354.SZ", "name": "天娱数科", "market": "SZ", "source": "tushare_a"}], source="tushare_a")
    calls = _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path)
    combined_version = version_fingerprint("sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1")
    cached_card = tmp_path / "cached-card.png"
    cached_chart = tmp_path / "cached-chart.png"
    cached_report = tmp_path / "cached-report.md"
    cached_card.write_bytes(b"cached-card")
    cached_chart.write_bytes(b"cached-chart")
    cached_report.write_text("cached report", encoding="utf-8")
    write_cache_entry(
        cache_key=build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "002354.SZ", "2026-05-29", combined_version),
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="002354.SZ",
        market_date="2026-05-29",
        version_fingerprint=combined_version,
        output_files=[str(cached_card), str(cached_chart), str(cached_report)],
    )
    monkeypatch.setattr(cache_service, "_today", lambda: datetime(2026, 5, 29).date(), raising=False)

    class UnknownResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "002354.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="", known=False, source="unknown")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", UnknownResolver, raising=False)

    reply = handle_text_message("ok", "天娱数科 技术分析")

    assert reply.success is True
    assert reply.output_files != [str(cached_card), str(cached_chart)]
    assert [Path(path).read_bytes() for path in reply.output_files] == [b"cached-card", b"cached-chart"]
    assert calls == []
    record = list_request_records(limit=1)[0]
    assert record.cache_hit is True
    assert record.cache_key == build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "002354.SZ", "2026-05-29", combined_version)
    assert record.market_date == "2026-05-29"
    assert record.normalized_target == "002354.SZ"
    cache_entries = list_cache_entries(service_type=ServiceType.TECHNICAL_ANALYSIS, limit=10)
    cached_entry = next(
        entry
        for entry in cache_entries
        if entry.cache_key == build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "002354.SZ", "2026-05-29", combined_version)
    )
    assert cached_entry.hit_count == 1


def test_technical_analysis_unknown_cache_context_reuses_latest_cache_when_only_program_wrapper_changes(
    business_env, tmp_path, monkeypatch
):
    from business.cache import cache_service as cache_service
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import build_cache_key, version_fingerprint, write_cache_entry
    from business.config.constants import ServiceType
    from business.content.stock_resolver import refresh_stock_symbols

    refresh_stock_symbols([{"code": "002354.SZ", "name": "天娱数科", "market": "SZ", "source": "tushare_a"}], source="tushare_a")
    old_cache_version = version_fingerprint("sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1")
    cached_card = tmp_path / "cached-card.png"
    cached_chart = tmp_path / "cached-chart.png"
    cached_report = tmp_path / "cached-report.md"
    cached_card.write_bytes(b"cached-card")
    cached_chart.write_bytes(b"cached-chart")
    cached_report.write_text("cached report", encoding="utf-8")
    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "002354.SZ", "2026-05-29", old_cache_version)
    write_cache_entry(
        cache_key=cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="002354.SZ",
        market_date="2026-05-29",
        version_fingerprint=old_cache_version,
        output_files=[str(cached_card), str(cached_chart), str(cached_report)],
    )
    monkeypatch.setattr(cache_service, "_today", lambda: datetime(2026, 5, 29).date(), raising=False)
    monkeypatch.setattr(
        technical_analysis,
        "_versions",
        lambda: ("sha256:program-v2", "sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1"),
    )

    class UnknownResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "002354.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="", known=False, source="unknown")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", UnknownResolver, raising=False)

    context = technical_analysis.prepare_technical_analysis_cache_context("天娱数科 技术分析")

    assert context.program_version == "sha256:program-v2"
    assert context.version_fingerprint == old_cache_version
    assert context.cache_key == cache_key
    assert context.market_date == "2026-05-29"
    assert context.cache_lookup_version_fingerprint == old_cache_version


def test_technical_analysis_unknown_market_date_does_not_reuse_legacy_program_version_cache(
    business_env, tmp_path, monkeypatch
):
    from business.cache import cache_service as cache_service
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import build_cache_key, version_fingerprint, write_cache_entry
    from business.config.constants import ServiceType
    from business.records.records import create_request_record, succeed_request_record
    from business.content.stock_resolver import refresh_stock_symbols

    refresh_stock_symbols([{"code": "002354.SZ", "name": "天娱数科", "market": "SZ", "source": "tushare_a"}], source="tushare_a")
    legacy_cache_version = version_fingerprint(
        "sha256:old-program",
        "sha256:ta-v1",
        "sha256:renderer-v1",
        "sha256:template-v1",
    )
    cached_card = tmp_path / "cached-card.png"
    cached_chart = tmp_path / "cached-chart.png"
    cached_report = tmp_path / "cached-report.md"
    cached_card.write_bytes(b"cached-card")
    cached_chart.write_bytes(b"cached-chart")
    cached_report.write_text("cached report", encoding="utf-8")
    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "002354.SZ", "2026-05-29", legacy_cache_version)
    request_id = create_request_record(
        "ok",
        "天娱数科 技术分析",
        ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="002354.SZ",
    )
    succeed_request_record(
        request_id,
        output_files=[str(cached_card), str(cached_chart), str(cached_report)],
        elapsed_ms=1,
        normalized_target="002354.SZ",
        stock_code="002354.SZ",
        stock_name="天娱数科",
        market_date="2026-05-29",
        cache_key=cache_key,
        program_version="sha256:old-program",
        ta_version="sha256:ta-v1",
        renderer_version="sha256:renderer-v1",
        template_version="sha256:template-v1",
    )
    write_cache_entry(
        cache_key=cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="002354.SZ",
        market_date="2026-05-29",
        version_fingerprint=legacy_cache_version,
        output_files=[str(cached_card), str(cached_chart), str(cached_report)],
        artifact_owner_id=request_id,
    )
    monkeypatch.setattr(cache_service, "_today", lambda: datetime(2026, 5, 29).date(), raising=False)
    monkeypatch.setattr(
        technical_analysis,
        "_versions",
        lambda: ("sha256:new-program", "sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1"),
    )

    class UnknownResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "002354.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="", known=False, source="unknown")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", UnknownResolver, raising=False)

    context = technical_analysis.prepare_technical_analysis_cache_context("天娱数科 技术分析")

    assert context.program_version == "sha256:new-program"
    assert context.version_fingerprint == version_fingerprint("sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1")
    assert context.cache_key == ""
    assert context.market_date == ""
    assert context.cache_lookup_version_fingerprint == context.version_fingerprint


def test_direct_technical_analysis_unknown_market_date_does_not_reuse_legacy_latest_cache_without_context(
    business_env, tmp_path, monkeypatch
):
    from business.cache import cache_service as cache_service
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import version_fingerprint
    from business.content.stock_resolver import refresh_stock_symbols

    refresh_stock_symbols([{"code": "002354.SZ", "name": "天娱数科", "market": "SZ", "source": "tushare_a"}], source="tushare_a")
    calls = _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path, generated_market_date="2026-05-29")
    legacy_cache_version = version_fingerprint(
        "sha256:old-program",
        "sha256:ta-v1",
        "sha256:renderer-v1",
        "sha256:template-v1",
    )
    cache_key, cached_files = _write_legacy_technical_analysis_cache(
        tmp_path,
        normalized_target="002354.SZ",
        market_date="2026-05-29",
        version_fingerprint=legacy_cache_version,
    )
    monkeypatch.setattr(cache_service, "_today", lambda: datetime(2026, 5, 29).date(), raising=False)
    monkeypatch.setattr(
        technical_analysis,
        "_versions",
        lambda: ("sha256:new-program", "sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1"),
    )

    class UnknownResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "002354.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="", known=False, source="unknown")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", UnknownResolver, raising=False)

    result = technical_analysis.run_technical_analysis("ok", "天娱数科 技术分析")

    assert result.success is True
    assert result.cache_hit is False
    assert result.cache_key != cache_key
    assert result.output_files != cached_files
    assert [call[0] for call in calls] == ["skill", "ai", "render"]


def test_technical_analysis_unknown_market_date_does_not_search_legacy_latest_cache(
    business_env, tmp_path, monkeypatch
):
    from business.cache import cache_service as cache_service
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import build_cache_key, version_fingerprint, write_cache_entry
    from business.config.constants import ServiceType
    from business.content.stock_resolver import refresh_stock_symbols

    refresh_stock_symbols([{"code": "002354.SZ", "name": "天娱数科", "market": "SZ", "source": "tushare_a"}], source="tushare_a")
    legacy_cache_version = version_fingerprint(
        "sha256:old-program",
        "sha256:ta-v1",
        "sha256:renderer-v1",
        "sha256:template-v1",
    )
    compatible_key, _compatible_files = _write_legacy_technical_analysis_cache(
        tmp_path,
        normalized_target="002354.SZ",
        market_date="2026-05-27",
        version_fingerprint=legacy_cache_version,
    )
    _write_legacy_technical_analysis_cache(
        tmp_path,
        normalized_target="002354.SZ",
        market_date="2026-05-28",
        version_fingerprint=legacy_cache_version,
        ta_version="sha256:ta-v2",
    )
    missing_owner_files = []
    for name in ["missing-owner-card.png", "missing-owner-chart.png", "missing-owner-report.md"]:
        path = tmp_path / name
        path.write_text("missing owner", encoding="utf-8")
        missing_owner_files.append(str(path))
    write_cache_entry(
        cache_key=build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "002354.SZ", "2026-05-29", legacy_cache_version),
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="002354.SZ",
        market_date="2026-05-29",
        version_fingerprint=legacy_cache_version,
        output_files=missing_owner_files,
        artifact_owner_id="",
    )
    monkeypatch.setattr(cache_service, "_today", lambda: datetime(2026, 5, 29).date(), raising=False)
    monkeypatch.setattr(
        technical_analysis,
        "_versions",
        lambda: ("sha256:new-program", "sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1"),
    )

    class UnknownResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "002354.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="", known=False, source="unknown")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", UnknownResolver, raising=False)

    context = technical_analysis.prepare_technical_analysis_cache_context("天娱数科 技术分析")

    assert context.cache_key != compatible_key
    assert context.cache_key == ""
    assert context.market_date == ""
    assert context.cache_lookup_version_fingerprint == version_fingerprint(
        "sha256:ta-v1",
        "sha256:renderer-v1",
        "sha256:template-v1",
    )


def test_router_context_uses_specific_compatible_legacy_cache_key_when_plain_lookup_would_find_incompatible_row(
    business_env, tmp_path, monkeypatch
):
    from business.cache import cache_service as cache_service
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import version_fingerprint, write_cache_entry
    from business.config.constants import ServiceType
    from business.records.records import create_request_record, list_request_records, succeed_request_record
    from business.routing.router import handle_text_message
    from business.content.stock_resolver import refresh_stock_symbols
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    refresh_stock_symbols([{"code": "002354.SZ", "name": "天娱数科", "market": "SZ", "source": "tushare_a"}], source="tushare_a")
    calls = _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path, generated_market_date="2026-05-29")
    legacy_cache_version = version_fingerprint(
        "sha256:old-program",
        "sha256:ta-v1",
        "sha256:renderer-v1",
        "sha256:template-v1",
    )
    compatible_key, compatible_files = _write_legacy_technical_analysis_cache(
        tmp_path,
        normalized_target="002354.SZ",
        market_date="2026-05-29",
        version_fingerprint=legacy_cache_version,
    )
    incompatible_card = tmp_path / "incompatible-card.png"
    incompatible_chart = tmp_path / "incompatible-chart.png"
    incompatible_report = tmp_path / "incompatible-report.md"
    incompatible_card.write_bytes(b"incompatible-card")
    incompatible_chart.write_bytes(b"incompatible-chart")
    incompatible_report.write_text("incompatible report", encoding="utf-8")
    incompatible_key = "manual-incompatible-cache-key"
    incompatible_owner_id = create_request_record(
        "ok",
        "天娱数科 技术分析",
        ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="002354.SZ",
    )
    succeed_request_record(
        incompatible_owner_id,
        output_files=[str(incompatible_card), str(incompatible_chart), str(incompatible_report)],
        elapsed_ms=1,
        normalized_target="002354.SZ",
        stock_code="002354.SZ",
        stock_name="天娱数科",
        market_date="2026-05-29",
        cache_key=incompatible_key,
        program_version="sha256:old-program",
        ta_version="sha256:ta-v2",
        renderer_version="sha256:renderer-v1",
        template_version="sha256:template-v1",
    )
    write_cache_entry(
        cache_key=incompatible_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="002354.SZ",
        market_date="2026-05-29",
        version_fingerprint=legacy_cache_version,
        output_files=[str(incompatible_card), str(incompatible_chart), str(incompatible_report)],
        artifact_owner_id=incompatible_owner_id,
    )
    monkeypatch.setattr(cache_service, "_today", lambda: datetime(2026, 5, 29).date(), raising=False)
    monkeypatch.setattr(
        technical_analysis,
        "_versions",
        lambda: ("sha256:new-program", "sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1"),
    )

    class KnownResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "002354.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="2026-05-29", known=True, source="latest")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", KnownResolver, raising=False)

    reply = handle_text_message("ok", "天娱数科 技术分析")

    assert reply.success is True
    assert reply.output_files != compatible_files[:2]
    assert [Path(path).read_bytes() for path in reply.output_files] == [
        Path(compatible_files[0]).read_bytes(),
        Path(compatible_files[1]).read_bytes(),
    ]
    assert calls == []
    record = list_request_records(limit=1)[0]
    assert record.cache_hit is True
    assert record.cache_key == compatible_key
    assert record.cache_key != incompatible_key


def test_technical_analysis_invalidates_compatible_today_intraday_cache_after_close_and_reruns(
    business_env, tmp_path, monkeypatch
):
    from zoneinfo import ZoneInfo

    from business.cache import cache_policy as cache_policy
    from business.cache import cache_service as cache_service
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import list_cache_entries, version_fingerprint
    from business.config.constants import ServiceType
    from business.schema.db import connect
    from business.config.config_service import save_config
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.schema.tables import investment_products
    from business.content.stock_resolver import refresh_stock_symbols
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    save_config("investment.technical_analysis.cache_close_invalidate_time", "15:30", operator_role="admin")
    refresh_stock_symbols([{"code": "002354.SZ", "name": "天娱数科", "market": "SZ", "source": "tushare_a"}], source="tushare_a")
    calls = _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path, generated_market_date="2026-05-29")
    legacy_cache_version = version_fingerprint(
        "sha256:old-program",
        "sha256:ta-v1",
        "sha256:renderer-v1",
        "sha256:template-v1",
    )
    compatible_key, compatible_files = _write_legacy_technical_analysis_cache(
        tmp_path,
        normalized_target="002354.SZ",
        market_date="2026-05-29",
        version_fingerprint=legacy_cache_version,
    )
    monkeypatch.setattr(cache_service, "_today", lambda: datetime(2026, 5, 29).date(), raising=False)
    monkeypatch.setattr(
        cache_policy,
        "beijing_now",
        lambda: datetime(2026, 5, 29, 15, 31, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    monkeypatch.setattr(
        technical_analysis,
        "_versions",
        lambda: ("sha256:new-program", "sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1"),
    )
    with connect() as conn:
        conn.execute(
            investment_products.update()
            .where(investment_products.c.source_cache_key == compatible_key)
            .values(updated_at="2026-05-29T07:00:00+00:00")
        )

    class KnownResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "002354.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="2026-05-29", known=True, source="latest")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", KnownResolver, raising=False)

    reply = handle_text_message("ok", "天娱数科 技术分析")

    assert reply.success is True
    assert reply.output_files != compatible_files[:2]
    assert [call[0] for call in calls] == ["skill", "ai", "render"]
    record = list_request_records(limit=1)[0]
    assert record.cache_hit is False
    assert record.cache_key != compatible_key
    entries = list_cache_entries(service_type=ServiceType.TECHNICAL_ANALYSIS, include_invalidated=True)
    assert {entry.status for entry in entries if entry.cache_key == compatible_key} == {"invalidated"}


def test_technical_analysis_context_cache_key_misses_when_owner_becomes_incompatible(
    business_env, tmp_path, monkeypatch
):
    from business.cache import cache_service as cache_service
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import list_cache_entries, version_fingerprint
    from business.config.constants import ServiceType
    from business.schema.db import connect
    from business.schema.tables import request_records
    from business.content.stock_resolver import refresh_stock_symbols

    refresh_stock_symbols([{"code": "002354.SZ", "name": "天娱数科", "market": "SZ", "source": "tushare_a"}], source="tushare_a")
    calls = _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path, generated_market_date="2026-05-29")
    legacy_cache_version = version_fingerprint(
        "sha256:old-program",
        "sha256:ta-v1",
        "sha256:renderer-v1",
        "sha256:template-v1",
    )
    compatible_key, compatible_files = _write_legacy_technical_analysis_cache(
        tmp_path,
        normalized_target="002354.SZ",
        market_date="2026-05-29",
        version_fingerprint=legacy_cache_version,
    )
    monkeypatch.setattr(cache_service, "_today", lambda: datetime(2026, 5, 29).date(), raising=False)
    monkeypatch.setattr(
        technical_analysis,
        "_versions",
        lambda: ("sha256:new-program", "sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1"),
    )

    class KnownResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "002354.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="2026-05-29", known=True, source="latest")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", KnownResolver, raising=False)
    context = technical_analysis.prepare_technical_analysis_cache_context("天娱数科 技术分析")
    owner_id = list_cache_entries(service_type=ServiceType.TECHNICAL_ANALYSIS)[0].artifact_owner_id
    with connect() as conn:
        conn.execute(
            request_records.update()
            .where(request_records.c.request_id == owner_id)
            .values(ta_version="sha256:ta-v2")
        )

    result = technical_analysis.run_technical_analysis("ok", "天娱数科 技术分析", cache_context=context)

    assert context.cache_key == compatible_key
    assert result.success is True
    assert result.cache_hit is False
    assert result.cache_key == compatible_key
    assert result.output_files != compatible_files
    assert [call[0] for call in calls] == ["skill", "ai", "render"]


def test_technical_analysis_legacy_latest_misses_when_no_compatible_owner_row_in_window(
    business_env, tmp_path, monkeypatch
):
    from business.cache import cache_service as cache_service
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import version_fingerprint
    from business.content.stock_resolver import refresh_stock_symbols

    refresh_stock_symbols([{"code": "002354.SZ", "name": "天娱数科", "market": "SZ", "source": "tushare_a"}], source="tushare_a")
    legacy_cache_version = version_fingerprint(
        "sha256:old-program",
        "sha256:ta-v1",
        "sha256:renderer-v1",
        "sha256:template-v1",
    )
    _write_legacy_technical_analysis_cache(
        tmp_path,
        normalized_target="002354.SZ",
        market_date="2026-05-20",
        version_fingerprint=legacy_cache_version,
    )
    incompatible_key, _incompatible_files = _write_legacy_technical_analysis_cache(
        tmp_path,
        normalized_target="002354.SZ",
        market_date="2026-05-29",
        version_fingerprint=legacy_cache_version,
        ta_version="sha256:ta-v2",
    )
    monkeypatch.setattr(cache_service, "_today", lambda: datetime(2026, 5, 29).date(), raising=False)
    monkeypatch.setattr(
        technical_analysis,
        "_versions",
        lambda: ("sha256:new-program", "sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1"),
    )

    class UnknownResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "002354.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="", known=False, source="unknown")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", UnknownResolver, raising=False)

    context = technical_analysis.prepare_technical_analysis_cache_context("天娱数科 技术分析")

    assert context.cache_key != incompatible_key
    assert context.market_date == ""
    assert context.cache_key == ""
    assert context.cache_lookup_version_fingerprint == version_fingerprint(
        "sha256:ta-v1",
        "sha256:renderer-v1",
        "sha256:template-v1",
    )


def test_technical_analysis_known_market_date_reuses_legacy_program_version_cache(
    business_env, tmp_path, monkeypatch
):
    from business.cache import cache_service as cache_service
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import version_fingerprint
    from business.config.constants import ServiceType
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.content.stock_resolver import refresh_stock_symbols
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    refresh_stock_symbols([{"code": "002354.SZ", "name": "天娱数科", "market": "SZ", "source": "tushare_a"}], source="tushare_a")
    calls = _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path, generated_market_date="2026-05-29")
    legacy_cache_version = version_fingerprint(
        "sha256:old-program",
        "sha256:ta-v1",
        "sha256:renderer-v1",
        "sha256:template-v1",
    )
    cache_key, cached_files = _write_legacy_technical_analysis_cache(
        tmp_path,
        normalized_target="002354.SZ",
        market_date="2026-05-29",
        version_fingerprint=legacy_cache_version,
    )
    monkeypatch.setattr(cache_service, "_today", lambda: datetime(2026, 5, 29).date(), raising=False)
    monkeypatch.setattr(
        technical_analysis,
        "_versions",
        lambda: ("sha256:new-program", "sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1"),
    )

    class KnownResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "002354.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="2026-05-29", known=True, source="latest")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", KnownResolver, raising=False)

    reply = handle_text_message("ok", "天娱数科 技术分析")

    assert reply.success is True
    assert reply.output_files != cached_files[:2]
    assert [Path(path).read_bytes() for path in reply.output_files] == [
        Path(cached_files[0]).read_bytes(),
        Path(cached_files[1]).read_bytes(),
    ]
    assert calls == []
    record = list_request_records(limit=1)[0]
    assert record.cache_hit is True
    assert record.cache_key == cache_key
    assert record.market_date == "2026-05-29"


def test_technical_analysis_explicit_market_date_reuses_legacy_program_version_cache(
    business_env, tmp_path, monkeypatch
):
    from business.cache import cache_service as cache_service
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import version_fingerprint
    from business.config.constants import ServiceType
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    calls = _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path, generated_market_date="2026-05-28")
    legacy_cache_version = version_fingerprint(
        "sha256:old-program",
        "sha256:ta-v1",
        "sha256:renderer-v1",
        "sha256:template-v1",
    )
    cache_key, cached_files = _write_legacy_technical_analysis_cache(
        tmp_path,
        normalized_target="300502.SZ",
        market_date="2026-05-28",
        version_fingerprint=legacy_cache_version,
    )
    monkeypatch.setattr(cache_service, "_today", lambda: datetime(2026, 5, 29).date(), raising=False)
    monkeypatch.setattr(
        technical_analysis,
        "_versions",
        lambda: ("sha256:new-program", "sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1"),
    )

    class ExplicitResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "300502.SZ"
            assert requested_market_date == "2026-05-28"
            return SimpleNamespace(market_date="2026-05-28", known=True, source="explicit")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", ExplicitResolver, raising=False)

    reply = handle_text_message("ok", "300502.SZ 2026-05-28 技术分析")

    assert reply.success is True
    assert reply.output_files != cached_files[:2]
    assert [Path(path).read_bytes() for path in reply.output_files] == [
        Path(cached_files[0]).read_bytes(),
        Path(cached_files[1]).read_bytes(),
    ]
    assert calls == []
    record = list_request_records(limit=1)[0]
    assert record.cache_hit is True
    assert record.cache_key == cache_key
    assert record.market_date == "2026-05-28"


def test_technical_analysis_explicit_market_date_does_not_fallback_to_other_legacy_date(
    business_env, tmp_path, monkeypatch
):
    from business.cache import cache_service as cache_service
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import version_fingerprint
    from business.config.constants import ServiceType
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    calls = _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path, generated_market_date="2026-05-28")
    legacy_cache_version = version_fingerprint(
        "sha256:old-program",
        "sha256:ta-v1",
        "sha256:renderer-v1",
        "sha256:template-v1",
    )
    _cache_key, cached_files = _write_legacy_technical_analysis_cache(
        tmp_path,
        normalized_target="300502.SZ",
        market_date="2026-05-29",
        version_fingerprint=legacy_cache_version,
    )
    monkeypatch.setattr(cache_service, "_today", lambda: datetime(2026, 5, 29).date(), raising=False)
    monkeypatch.setattr(
        technical_analysis,
        "_versions",
        lambda: ("sha256:new-program", "sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1"),
    )

    class ExplicitResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "300502.SZ"
            assert requested_market_date == "2026-05-28"
            return SimpleNamespace(market_date="2026-05-28", known=True, source="explicit")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", ExplicitResolver, raising=False)

    reply = handle_text_message("ok", "300502.SZ 2026-05-28 技术分析")

    assert reply.success is True
    assert reply.output_files != cached_files[:2]
    assert [call[0] for call in calls] == ["skill", "ai", "render"]
    record = list_request_records(limit=1)[0]
    assert record.cache_hit is False
    assert record.market_date == "2026-05-28"


def test_technical_analysis_cache_key_version_changes_when_output_versions_change(
    business_env, monkeypatch
):
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import version_fingerprint
    from business.content.stock_resolver import refresh_stock_symbols

    refresh_stock_symbols([{"code": "002354.SZ", "name": "天娱数科", "market": "SZ", "source": "tushare_a"}], source="tushare_a")

    class UnknownResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "002354.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="", known=False, source="unknown")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", UnknownResolver, raising=False)

    def context_version(ta_version, renderer_version, template_version):
        monkeypatch.setattr(
            technical_analysis,
            "_versions",
            lambda: ("sha256:program-v1", ta_version, renderer_version, template_version),
        )
        return technical_analysis.prepare_technical_analysis_cache_context("天娱数科 技术分析").version_fingerprint

    base = context_version("sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1")

    assert base == version_fingerprint("sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1")
    assert context_version("sha256:ta-v2", "sha256:renderer-v1", "sha256:template-v1") != base
    assert context_version("sha256:ta-v1", "sha256:renderer-v2", "sha256:template-v1") != base
    assert context_version("sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v2") != base


def test_technical_analysis_unknown_market_date_does_not_reuse_cache_outside_fallback_window(
    business_env, tmp_path, monkeypatch
):
    from business.cache import cache_service as cache_service
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import build_cache_key, version_fingerprint, write_cache_entry
    from business.config.constants import ServiceType
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    calls = _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path)
    combined_version = version_fingerprint("sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1")
    old_card = tmp_path / "old-card.png"
    old_chart = tmp_path / "old-chart.png"
    old_report = tmp_path / "old-report.md"
    old_card.write_bytes(b"old-card")
    old_chart.write_bytes(b"old-chart")
    old_report.write_text("old report", encoding="utf-8")
    write_cache_entry(
        cache_key=build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-05-20", combined_version),
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-05-20",
        version_fingerprint=combined_version,
        output_files=[str(old_card), str(old_chart), str(old_report)],
    )
    monkeypatch.setattr(cache_service, "_today", lambda: datetime(2026, 5, 29).date(), raising=False)

    class UnknownResolver:
        def resolve(self, _symbol, requested_market_date=""):
            assert requested_market_date == ""
            return SimpleNamespace(market_date="", known=False, source="unknown")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", UnknownResolver, raising=False)

    reply = handle_text_message("ok", "300502.SZ 技术分析")

    assert reply.success is True
    assert reply.output_files != [str(old_card), str(old_chart)]
    assert [call[0] for call in calls] == ["skill", "ai", "render"]
    record = list_request_records(limit=1)[0]
    assert record.cache_hit is False
    assert record.market_date == "2026-05-25"


def test_technical_analysis_explicit_market_date_does_not_fallback_to_latest_cache(
    business_env, tmp_path, monkeypatch
):
    from business.cache import cache_service as cache_service
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import build_cache_key, version_fingerprint, write_cache_entry
    from business.config.constants import ServiceType
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    calls = _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path, generated_market_date="2026-05-28")
    combined_version = version_fingerprint("sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1")
    cached_card = tmp_path / "cached-card.png"
    cached_chart = tmp_path / "cached-chart.png"
    cached_report = tmp_path / "cached-report.md"
    cached_card.write_bytes(b"cached-card")
    cached_chart.write_bytes(b"cached-chart")
    cached_report.write_text("cached report", encoding="utf-8")
    write_cache_entry(
        cache_key=build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-05-29", combined_version),
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-05-29",
        version_fingerprint=combined_version,
        output_files=[str(cached_card), str(cached_chart), str(cached_report)],
    )
    monkeypatch.setattr(cache_service, "_today", lambda: datetime(2026, 5, 29).date(), raising=False)

    class ExplicitResolver:
        def resolve(self, _symbol, requested_market_date=""):
            assert requested_market_date == "2026-05-28"
            return SimpleNamespace(market_date="2026-05-28", known=True, source="explicit")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", ExplicitResolver, raising=False)

    reply = handle_text_message("ok", "300502.SZ 2026-05-28 技术分析")

    assert reply.success is True
    assert reply.output_files != [str(cached_card), str(cached_chart)]
    assert [call[0] for call in calls] == ["skill", "ai", "render"]
    record = list_request_records(limit=1)[0]
    assert record.cache_hit is False
    assert record.market_date == "2026-05-28"


def test_technical_analysis_stock_name_reuses_same_standard_code_cache(business_env, tmp_path, monkeypatch):
    from business.content import technical_analysis as technical_analysis
    from business.config.constants import ServiceType
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.content.stock_resolver import refresh_stock_symbols
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    refresh_stock_symbols([{"code": "300502.SZ", "name": "新易盛", "market": "SZ", "source": "tushare_a"}], source="tushare_a")
    calls = _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path)

    class FakeResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "300502.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="2026-05-25", known=True, source="fake")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", FakeResolver, raising=False)

    first = handle_text_message("ok", "新易盛 技术分析")
    second = handle_text_message("ok", "新易盛 技术分析")

    assert first.success is True
    assert second.success is True
    assert second.output_files == first.output_files
    assert [call[0] for call in calls] == ["skill", "ai", "render"]
    records = list_request_records(limit=2)
    assert records[0].cache_hit is True
    assert records[1].cache_hit is False
    assert records[0].normalized_target == "300502.SZ"
    assert records[1].normalized_target == "300502.SZ"


def test_technical_analysis_different_market_date_misses_cache(business_env, tmp_path, monkeypatch):
    from business.content import technical_analysis as technical_analysis
    from business.config.constants import ServiceType
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    calls = []
    current_market_date = ""

    monkeypatch.setattr(
        technical_analysis,
        "_versions",
        lambda: ("sha256:program-v1", "sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1"),
    )

    def fake_skill(symbol, output_dir, stock_name=""):
        calls.append(("skill", symbol, current_market_date))
        report = tmp_path / f"{symbol}_技术分析报告_{current_market_date}.md"
        chart = tmp_path / f"{symbol}_TA_{current_market_date}.png"
        report.write_text(f"报告日期：{current_market_date}\n核心观点", encoding="utf-8")
        chart.write_bytes(f"chart-{current_market_date}".encode("utf-8"))
        return report, chart

    def fake_ai(report_text):
        calls.append(("ai", current_market_date))
        return SimpleNamespace(success=True, text=f"日期：{current_market_date}\n信号卡标准文本")

    def fake_render(_standard_text, output_path):
        calls.append(("render", current_market_date))
        Path(output_path).write_bytes(f"card-{current_market_date}".encode("utf-8"))
        return SimpleNamespace(success=True, image_path=str(output_path), detail="")

    monkeypatch.setattr(technical_analysis, "_run_skill", fake_skill)
    monkeypatch.setattr(technical_analysis, "generate_technical_analysis_text", fake_ai)
    monkeypatch.setattr(technical_analysis, "render_technical_analysis_card", fake_render)

    current_market_date = "2026-05-25"
    first = handle_text_message("ok", "300502.SZ 2026-05-25 技术分析")
    current_market_date = "2026-05-26"
    second = handle_text_message("ok", "300502.SZ 2026-05-26 技术分析")

    assert first.success is True
    assert second.success is True
    assert second.output_files != first.output_files
    assert [call[0] for call in calls].count("skill") == 2
    records = list_request_records(limit=2)
    assert records[0].market_date == "2026-05-26"
    assert records[1].market_date == "2026-05-25"
    assert records[0].cache_hit is False
    assert records[1].cache_hit is False

    current_market_date = "2026-05-25"
    third = handle_text_message("ok", "300502.SZ 2026-05-25 技术分析")

    assert third.success is True
    assert third.output_files == first.output_files
    assert [call[0] for call in calls].count("skill") == 2
    assert Path(third.output_files[0]).read_bytes() == b"card-2026-05-25"
    assert list_request_records(limit=1)[0].cache_hit is True


def test_technical_analysis_unknown_generated_market_date_does_not_cache_current_date(
    business_env, tmp_path, monkeypatch
):
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import list_cache_entries
    from business.config.constants import ServiceType
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    report = tmp_path / "report_without_date.md"
    chart = tmp_path / "chart_without_date.png"
    report.write_text("核心观点 without date", encoding="utf-8")
    chart.write_bytes(b"chart")

    monkeypatch.setattr(
        technical_analysis,
        "_versions",
        lambda: ("sha256:program-v1", "sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1"),
    )
    calls = []

    class UnknownResolver:
        def resolve(self, _symbol, requested_market_date=""):
            assert requested_market_date == ""
            return SimpleNamespace(market_date="", known=False, source="unknown")

    def fake_skill(symbol, _output_dir):
        calls.append(("skill", symbol))
        return report, chart

    def fake_ai(_report_text):
        calls.append(("ai", len(calls)))
        return SimpleNamespace(success=True, text="信号卡标准文本 without date")

    def fake_render(_standard_text, output_path):
        calls.append(("render", Path(output_path).name))
        Path(output_path).write_bytes(b"card")
        return SimpleNamespace(success=True, image_path=str(output_path), detail="")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", UnknownResolver, raising=False)
    monkeypatch.setattr(technical_analysis, "_run_skill", fake_skill)
    monkeypatch.setattr(technical_analysis, "generate_technical_analysis_text", fake_ai)
    monkeypatch.setattr(technical_analysis, "render_technical_analysis_card", fake_render)

    first = handle_text_message("ok", "300502.SZ 技术分析")
    second = handle_text_message("ok", "300502.SZ 技术分析")

    assert first.success is True
    assert second.success is True
    assert [call[0] for call in calls] == ["skill", "ai", "render", "skill", "ai", "render"]
    records = list_request_records(limit=2)
    assert records[0].market_date == ""
    assert records[1].market_date == ""
    assert records[0].cache_key == ""
    assert records[1].cache_key == ""
    assert records[0].cache_hit is False
    assert records[1].cache_hit is False
    assert "market_date unknown" in records[0].status_warning
    assert list_cache_entries(service_type=ServiceType.TECHNICAL_ANALYSIS) == []


def test_technical_analysis_invalid_generated_market_date_does_not_cache(
    business_env, tmp_path, monkeypatch
):
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import list_cache_entries
    from business.config.constants import ServiceType
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    invalid_market_date = "2026-02-31"
    report = tmp_path / f"300502_技术分析报告_{invalid_market_date}.md"
    chart = tmp_path / f"300502_TA_{invalid_market_date}.png"
    report.write_text(f"报告日期：{invalid_market_date}\n核心观点", encoding="utf-8")
    chart.write_bytes(b"chart")

    monkeypatch.setattr(
        technical_analysis,
        "_versions",
        lambda: ("sha256:program-v1", "sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1"),
    )

    class UnknownResolver:
        def resolve(self, _symbol, requested_market_date=""):
            assert requested_market_date == ""
            return SimpleNamespace(market_date="", known=False, source="unknown")

    def fake_skill(_symbol, _output_dir, stock_name=""):
        return report, chart

    def fake_ai(_report_text):
        return SimpleNamespace(success=True, text=f"日期：{invalid_market_date}\n信号卡标准文本")

    def fake_render(_standard_text, output_path):
        Path(output_path).write_bytes(b"card")
        return SimpleNamespace(success=True, image_path=str(output_path), detail="")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", UnknownResolver, raising=False)
    monkeypatch.setattr(technical_analysis, "_run_skill", fake_skill)
    monkeypatch.setattr(technical_analysis, "generate_technical_analysis_text", fake_ai)
    monkeypatch.setattr(technical_analysis, "render_technical_analysis_card", fake_render)

    reply = handle_text_message("ok", "300502.SZ 技术分析")

    assert reply.success is True
    record = list_request_records(limit=1)[0]
    assert record.market_date == ""
    assert record.cache_key == ""
    assert list_cache_entries(service_type=ServiceType.TECHNICAL_ANALYSIS) == []


def test_technical_analysis_resolver_market_date_is_used_when_generated_outputs_have_no_date(
    business_env, tmp_path, monkeypatch
):
    from business.content import technical_analysis as technical_analysis
    from business.cache.cache_service import list_cache_entries
    from business.config.constants import ServiceType
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    report = tmp_path / "report_without_date.md"
    chart = tmp_path / "chart_without_date.png"
    report.write_text("核心观点 without date", encoding="utf-8")
    chart.write_bytes(b"chart")

    monkeypatch.setattr(
        technical_analysis,
        "_versions",
        lambda: ("sha256:program-v1", "sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1"),
    )
    calls = []

    class FakeResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "300502.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="2026-05-25", known=True, source="fake")

    def fake_skill(symbol, _output_dir, stock_name=""):
        calls.append(("skill", symbol))
        return report, chart

    def fake_ai(_report_text):
        calls.append(("ai", len(calls)))
        return SimpleNamespace(success=True, text="信号卡标准文本 without date")

    def fake_render(_standard_text, output_path):
        calls.append(("render", Path(output_path).name))
        Path(output_path).write_bytes(b"card")
        return SimpleNamespace(success=True, image_path=str(output_path), detail="")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", FakeResolver, raising=False)
    monkeypatch.setattr(technical_analysis, "_run_skill", fake_skill)
    monkeypatch.setattr(technical_analysis, "generate_technical_analysis_text", fake_ai)
    monkeypatch.setattr(technical_analysis, "render_technical_analysis_card", fake_render)

    first = handle_text_message("ok", "300502.SZ 技术分析")
    second = handle_text_message("ok", "300502.SZ 技术分析")

    assert first.success is True
    assert second.success is True
    assert second.output_files == first.output_files
    assert [call[0] for call in calls] == ["skill", "ai", "render"]
    records = list_request_records(limit=2)
    assert records[0].cache_hit is True
    assert records[1].cache_hit is False
    assert records[0].market_date == "2026-05-25"
    assert records[1].market_date == "2026-05-25"
    assert records[0].cache_key
    assert records[1].cache_key
    assert records[0].cache_key == records[1].cache_key
    assert second.source_type == "product"
    assert second.source_id == records[0].cache_key
    cache_entry = list_cache_entries(service_type=ServiceType.TECHNICAL_ANALYSIS)[0]
    assert cache_entry.hit_count == 1
    assert cache_entry.market_date == "2026-05-25"


def test_market_date_resolver_rejects_invalid_explicit_dates(monkeypatch):
    from business.content.market_date_resolver import MarketDateResolver

    calls = []

    monkeypatch.setattr(
        MarketDateResolver,
        "_latest_market_date",
        lambda _self, _symbol: calls.append(_symbol)
        or SimpleNamespace(market_date="2026-05-26", known=True, source="latest"),
    )

    resolver = MarketDateResolver()

    result = resolver.resolve("300502.SZ", "2026-02-31")

    assert result.market_date == ""
    assert result.known is False
    assert result.source == "unknown"
    assert calls == []


def test_write_cache_entry_rewrites_payload_without_resetting_hit_count(business_env):
    from business.cache.cache_service import build_cache_key, increment_cache_hit, list_cache_entries, write_cache_entry
    from business.config.constants import ServiceType

    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-05-25", "v1")
    write_cache_entry(
        cache_key=cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-05-25",
        version_fingerprint="v1",
        output_files=["/tmp/old-card.png"],
        artifact_owner_id="request-old",
    )
    increment_cache_hit(cache_key)

    rewritten = write_cache_entry(
        cache_key=cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-05-25",
        version_fingerprint="v1",
        output_files=["/tmp/new-card.png", "/tmp/new-chart.png"],
        artifact_owner_id="request-new",
    )

    assert rewritten.hit_count == 1
    assert rewritten.output_files == ["/tmp/new-card.png", "/tmp/new-chart.png"]
    assert rewritten.artifact_owner_id == "request-new"
    assert rewritten.status == "active"
    entries = list_cache_entries(service_type=ServiceType.TECHNICAL_ANALYSIS)
    assert len(entries) == 1
    assert entries[0].hit_count == 1
    assert entries[0].output_files == ["/tmp/new-card.png", "/tmp/new-chart.png"]
    assert entries[0].artifact_owner_id == "request-new"
    assert entries[0].status == "active"


def test_write_cache_entry_creates_product_without_cache_row(business_env, tmp_path):
    from business.cache.cache_service import build_cache_key, find_cache_entry_by_key, write_cache_entry
    from business.config.constants import ServiceType
    from business.products.product_service import list_products_page
    from business.schema.tables import metadata

    output = tmp_path / "product-cache-write.png"
    output.write_text("product-cache-write", encoding="utf-8")
    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-06-25", "vf-write-product")

    written = write_cache_entry(
        cache_key=cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-06-25",
        version_fingerprint="vf-write-product",
        output_files=[str(output)],
        artifact_owner_id="req-product-cache-write",
    )

    found = find_cache_entry_by_key(cache_key)
    products, total = list_products_page(include_invalidated=True, business_type=str(ServiceType.TECHNICAL_ANALYSIS))

    assert written.cache_key == cache_key
    assert found is not None
    assert found.cache_key == cache_key
    assert total == 1
    assert products[0]["source_cache_key"] == cache_key
    assert products[0]["source_request_id"] == "req-product-cache-write"
    assert products[0]["output_files"] == [str(output)]
    assert "cache_entries" not in metadata.tables


def test_beijing_now_returns_beijing_timezone_datetime():
    from business.cache.cache_policy import beijing_now

    now = beijing_now()

    assert now.tzinfo is not None
    assert now.tzname() == "CST"
    assert now.utcoffset() == timedelta(hours=8)


def test_technical_analysis_cache_policy_keeps_cache_before_close_cutoff():
    from business.cache.cache_policy import technical_analysis_cache_expired_after_close

    assert (
        technical_analysis_cache_expired_after_close(
            "2026-05-31",
            datetime(2026, 5, 31, 7, 0, tzinfo=UTC),
            now=datetime(2026, 5, 31, 17, 29),
        )
        is False
    )


def test_technical_analysis_cache_policy_expires_today_cache_written_before_close_cutoff():
    from business.cache.cache_policy import technical_analysis_cache_expired_after_close

    assert (
        technical_analysis_cache_expired_after_close(
            "2026-05-31",
            datetime(2026, 5, 31, 17, 29, 59),
            now=datetime(2026, 5, 31, 17, 30),
        )
        is True
    )


def test_technical_analysis_cache_policy_keeps_non_today_market_date_after_close_cutoff():
    from business.cache.cache_policy import technical_analysis_cache_expired_after_close

    assert (
        technical_analysis_cache_expired_after_close(
            "2026-05-30",
            datetime(2026, 5, 30, 15, 0),
            now=datetime(2026, 5, 31, 17, 30),
        )
        is False
    )


def test_technical_analysis_cache_policy_expires_market_cache_after_fixed_cutoff_even_without_probe_update(monkeypatch):
    import business.cache.cache_policy as cache_policy

    cache_policy.reset_market_update_probe_cache()

    class UnknownResolver:
        def resolve(self, _symbol, requested_market_date=""):
            return SimpleNamespace(market_date="", known=False)

    monkeypatch.setattr(cache_policy, "MarketDateResolver", UnknownResolver)

    assert (
        cache_policy.technical_analysis_cache_expired_after_close(
            "2026-06-14",
            "2026-06-14T18:00:00+08:00",
            now="2026-06-15T17:30:00+08:00",
            normalized_target="600519.SH",
        )
        is True
    )


def test_technical_analysis_cache_policy_keeps_today_cache_written_at_or_after_close_cutoff():
    from business.cache.cache_policy import technical_analysis_cache_expired_after_close

    assert (
        technical_analysis_cache_expired_after_close(
            "2026-05-31",
            datetime(2026, 5, 31, 17, 30),
            now=datetime(2026, 5, 31, 17, 31),
        )
        is False
    )


def test_technical_analysis_cache_policy_compares_utc_and_local_times_as_beijing_time():
    from business.cache.cache_policy import technical_analysis_cache_expired_after_close

    assert (
        technical_analysis_cache_expired_after_close(
            "2026-05-31",
            "2026-05-31T09:29:59+00:00",
            now="2026-05-31T09:30:00+00:00",
        )
        is True
    )
    assert (
        technical_analysis_cache_expired_after_close(
            "2026-05-31",
            "2026-05-31T17:30:00+08:00",
            now="2026-05-31T09:30:00+00:00",
        )
        is False
    )


def test_technical_analysis_cache_policy_uses_default_cutoff_when_config_missing(business_env):
    from business.cache.cache_policy import technical_analysis_cache_expired_after_close

    assert (
        technical_analysis_cache_expired_after_close(
            "2026-05-31",
            datetime(2026, 5, 31, 17, 29, 59),
            now=datetime(2026, 5, 31, 17, 30),
        )
        is True
    )


def test_technical_analysis_cache_policy_uses_configured_cutoff_time(business_env):
    from business.cache.cache_policy import technical_analysis_cache_expired_after_close
    from business.config.config_service import save_config

    save_config("investment.technical_analysis.cache_close_invalidate_time", "14:45", operator_role="admin")

    assert (
        technical_analysis_cache_expired_after_close(
            "2026-05-31",
            datetime(2026, 5, 31, 14, 44, 59),
            now=datetime(2026, 5, 31, 14, 45),
        )
        is True
    )


def test_technical_analysis_cache_policy_falls_back_to_default_for_invalid_cutoff(business_env):
    from business.cache.cache_policy import technical_analysis_cache_expired_after_close
    from business.config.config_service import save_config

    save_config("investment.technical_analysis.cache_close_invalidate_time", "14:45:00", operator_role="admin")

    assert (
        technical_analysis_cache_expired_after_close(
            "2026-05-31",
            datetime(2026, 5, 31, 14, 44, 59),
            now=datetime(2026, 5, 31, 14, 45),
        )
        is False
    )


def test_technical_analysis_cache_policy_requires_strict_hh_mm_cutoff(business_env):
    from business.cache.cache_policy import technical_analysis_cache_expired_after_close
    from business.config.config_service import save_config

    save_config("investment.technical_analysis.cache_close_invalidate_time", "1:02", operator_role="admin")

    assert (
        technical_analysis_cache_expired_after_close(
            "2026-05-31",
            datetime(2026, 5, 31, 1, 1, 59),
            now=datetime(2026, 5, 31, 1, 2),
        )
        is False
    )


def test_technical_analysis_cache_policy_rejects_padded_hh_mm_cutoff(business_env):
    from business.cache.cache_policy import technical_analysis_cache_expired_after_close
    from business.config.config_service import save_config

    save_config("investment.technical_analysis.cache_close_invalidate_time", " 14:45", operator_role="admin")

    assert (
        technical_analysis_cache_expired_after_close(
            "2026-05-31",
            datetime(2026, 5, 31, 14, 44, 59),
            now=datetime(2026, 5, 31, 14, 45),
        )
        is False
    )


def test_technical_analysis_cache_policy_classifies_markets_by_symbol_suffix():
    from business.cache.cache_policy import market_from_symbol

    assert market_from_symbol("600519.SH") == "a_share"
    assert market_from_symbol("000001.SZ") == "a_share"
    assert market_from_symbol("00700.HK") == "hk"
    assert market_from_symbol("AAPL.US") == "us"
    assert market_from_symbol("UNKNOWN") == ""


def test_technical_analysis_cache_policy_expires_market_cache_when_probe_date_updates(monkeypatch):
    import business.cache.cache_policy as cache_policy

    cache_policy.reset_market_update_probe_cache()
    calls = []

    class FakeResolver:
        def resolve(self, symbol, requested_market_date=""):
            calls.append(symbol)
            return SimpleNamespace(market_date="2026-06-15", known=True)

    monkeypatch.setattr(cache_policy, "MarketDateResolver", FakeResolver)

    assert (
        cache_policy.technical_analysis_cache_expired_after_close(
            "2026-06-14",
            "2026-06-14T18:00:00+08:00",
            now="2026-06-15T15:31:00+08:00",
            normalized_target="600519.SH",
        )
        is True
    )
    assert calls == ["600519.SH"]


def test_technical_analysis_cache_policy_keeps_cache_before_probe_window(monkeypatch):
    import business.cache.cache_policy as cache_policy

    cache_policy.reset_market_update_probe_cache()

    class FailResolver:
        def resolve(self, _symbol, requested_market_date=""):
            raise AssertionError("probe should not run before 15:30")

    monkeypatch.setattr(cache_policy, "MarketDateResolver", FailResolver)

    assert (
        cache_policy.technical_analysis_cache_expired_after_close(
            "2026-06-14",
            "2026-06-14T18:00:00+08:00",
            now="2026-06-15T15:29:00+08:00",
            normalized_target="600519.SH",
        )
        is False
    )


def test_technical_analysis_cache_policy_reuses_probe_result_for_15_minutes(monkeypatch):
    import business.cache.cache_policy as cache_policy

    cache_policy.reset_market_update_probe_cache()
    calls = []

    class FakeResolver:
        def resolve(self, symbol, requested_market_date=""):
            calls.append(symbol)
            return SimpleNamespace(market_date="2026-06-15", known=True)

    monkeypatch.setattr(cache_policy, "MarketDateResolver", FakeResolver)

    for minute in (31, 40):
        assert (
            cache_policy.technical_analysis_cache_expired_after_close(
                "2026-06-14",
                "2026-06-14T18:00:00+08:00",
                now=f"2026-06-15T15:{minute}:00+08:00",
                normalized_target="600519.SH",
            )
            is True
        )
    assert calls == ["600519.SH"]


def test_technical_analysis_cache_policy_uses_distinct_market_probe_symbols(monkeypatch):
    import business.cache.cache_policy as cache_policy

    cache_policy.reset_market_update_probe_cache()
    calls = []

    class FakeResolver:
        def resolve(self, symbol, requested_market_date=""):
            calls.append(symbol)
            return SimpleNamespace(market_date="2026-06-15", known=True)

    monkeypatch.setattr(cache_policy, "MarketDateResolver", FakeResolver)

    assert cache_policy.latest_market_date_for_symbol("600519.SH", now="2026-06-15T15:31:00+08:00") == "2026-06-15"
    assert cache_policy.latest_market_date_for_symbol("00700.HK", now="2026-06-15T15:31:00+08:00") == "2026-06-15"
    assert cache_policy.latest_market_date_for_symbol("AAPL.US", now="2026-06-15T15:31:00+08:00") == "2026-06-15"
    assert calls == ["600519.SH", "00700.HK", "AAPL.US"]


def test_product_service_appends_and_invalidates_active_product(business_env, tmp_path):
    from business.products.product_service import (
        PRODUCT_STATUS_ACTIVE,
        PRODUCT_STATUS_INVALIDATED,
        create_product,
        find_active_product,
        invalidate_active_products,
        list_products_page,
    )

    first_card = tmp_path / "first-card.png"
    second_card = tmp_path / "second-card.png"
    first_card.write_bytes(b"first")
    second_card.write_bytes(b"second")

    first = create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="新易盛",
        business_date="2026-06-24",
        version_fingerprint="v1",
        source_request_id="request-1",
        source_type="request",
        output_files=[str(first_card)],
        text_content="first product",
        metadata={"version": 1},
    )

    assert find_active_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        business_date="2026-06-24",
        version_fingerprint="v1",
    )["product_id"] == first["product_id"]

    assert invalidate_active_products(
        business_type="technical_analysis",
        target_key="300502.SZ",
        business_date="2026-06-24",
        version_fingerprint="v1",
    ) == 1

    second = create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="新易盛",
        business_date="2026-06-24",
        version_fingerprint="v1",
        source_request_id="request-2",
        source_type="request",
        output_files=[str(second_card)],
        text_content="second product",
        metadata={"version": 2},
    )

    assert find_active_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        business_date="2026-06-24",
        version_fingerprint="v1",
    )["product_id"] == second["product_id"]

    rows, total = list_products_page(include_invalidated=True, business_type="technical_analysis")

    assert total == 2
    assert [row["product_id"] for row in rows] == [second["product_id"], first["product_id"]]
    assert [row["status"] for row in rows] == [PRODUCT_STATUS_ACTIVE, PRODUCT_STATUS_INVALIDATED]


def test_product_cache_lookup_by_cache_key_returns_active_product(business_env, tmp_path):
    from business.config.constants import ServiceType
    from business.products.product_service import create_product, find_product_cache_entry_by_key

    output = tmp_path / "cache-product.png"
    output.write_text("image", encoding="utf-8")
    product = create_product(
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        target_key="300502.SZ",
        target_label="300502.SZ",
        business_date="2026-06-25",
        version_fingerprint="vf-product-cache",
        status="active",
        source_cache_key="technical_analysis:300502.SZ:2026-06-25:vf-product-cache",
        source_type="cache",
        output_files=[str(output)],
    )

    entry = find_product_cache_entry_by_key("technical_analysis:300502.SZ:2026-06-25:vf-product-cache")

    assert entry is not None
    assert entry["product_id"] == product["product_id"]
    assert entry["cache_key"] == "technical_analysis:300502.SZ:2026-06-25:vf-product-cache"
    assert entry["service_type"] == str(ServiceType.TECHNICAL_ANALYSIS)
    assert entry["normalized_target"] == "300502.SZ"
    assert entry["market_date"] == "2026-06-25"
    assert entry["version_fingerprint"] == "vf-product-cache"
    assert entry["output_files"] == [str(output)]
    assert entry["status"] == "active"


def test_product_cache_lookup_invalidates_missing_files_without_deleting_product(business_env, tmp_path):
    from business.config.constants import ServiceType
    from business.products.product_service import (
        PRODUCT_STATUS_INVALIDATED,
        create_product,
        find_product_cache_entry,
        list_products_page,
    )

    missing = tmp_path / "missing.png"
    create_product(
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        target_key="300502.SZ",
        target_label="300502.SZ",
        business_date="2026-06-25",
        version_fingerprint="vf-missing-product-cache",
        status="active",
        source_cache_key="technical_analysis:300502.SZ:2026-06-25:vf-missing-product-cache",
        source_type="cache",
        output_files=[str(missing)],
    )

    entry = find_product_cache_entry(
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        version_fingerprint="vf-missing-product-cache",
        market_date="2026-06-25",
    )

    assert entry is None
    products, total = list_products_page(include_invalidated=True, business_type=str(ServiceType.TECHNICAL_ANALYSIS))
    assert total == 1
    assert products[0]["status"] == PRODUCT_STATUS_INVALIDATED
    assert products[0]["output_files"] == [str(missing)]


def test_product_service_list_filters_expired_active_products_from_active_views(business_env, tmp_path):
    from business.products import product_service

    card = tmp_path / "expired-card.png"
    card.write_bytes(b"expired")

    expired = product_service.create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="新易盛",
        business_date="2026-06-24",
        version_fingerprint="expired",
        output_files=[str(card)],
        expires_at="2000-01-01T00:00:00+00:00",
    )

    active_rows, active_total = product_service.list_products_page(
        business_type="technical_analysis",
        business_date="2026-06-24",
    )
    all_rows, all_total = product_service.list_products_page(
        include_invalidated=True,
        business_type="technical_analysis",
        business_date="2026-06-24",
    )

    assert active_rows == []
    assert active_total == 0
    assert all_total == 1
    assert all_rows[0]["product_id"] == expired["product_id"]
    assert product_service.list_product_business_dates("technical_analysis") == []
    assert product_service.list_product_business_dates("technical_analysis", include_invalidated=True) == ["2026-06-24"]


def test_product_service_keyword_treats_percent_as_literal(business_env, tmp_path):
    from business.products import product_service

    percent_card = tmp_path / "percent-card.png"
    plain_card = tmp_path / "plain-card.png"
    percent_card.write_bytes(b"percent")
    plain_card.write_bytes(b"plain")

    percent_product = product_service.create_product(
        business_type="technical_analysis",
        target_key="PERCENT.SZ",
        target_label="literal % marker",
        business_date="2026-06-24",
        version_fingerprint="v1",
        output_files=[str(percent_card)],
    )
    product_service.create_product(
        business_type="technical_analysis",
        target_key="PLAIN.SZ",
        target_label="plain marker",
        business_date="2026-06-24",
        version_fingerprint="v1",
        output_files=[str(plain_card)],
    )

    rows, total = product_service.list_products_page(
        business_type="technical_analysis",
        keyword="%",
        include_invalidated=True,
    )

    assert total == 1
    assert [row["product_id"] for row in rows] == [percent_product["product_id"]]


def test_product_service_replace_active_product_rolls_back_when_invalidation_fails(
    business_env, tmp_path, monkeypatch
):
    from business.products import product_service

    old_card = tmp_path / "old-card.png"
    new_card = tmp_path / "new-card.png"
    old_card.write_bytes(b"old")
    new_card.write_bytes(b"new")
    old = product_service.create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="新易盛",
        business_date="2026-06-24",
        version_fingerprint="v1",
        source_request_id="request-1",
        source_type="request",
        output_files=[str(old_card)],
    )

    def fail_invalidation(*_args, **_kwargs):
        raise RuntimeError("forced invalidation failure")

    monkeypatch.setattr(product_service, "_invalidate_prior_active_products_on_connection", fail_invalidation, raising=False)

    with pytest.raises(RuntimeError, match="forced invalidation failure"):
        product_service.replace_active_product(
            business_type="technical_analysis",
            target_key="300502.SZ",
            target_label="新易盛",
            business_date="2026-06-24",
            version_fingerprint="v1",
            source_request_id="request-2",
            source_type="request",
            output_files=[str(new_card)],
        )

    rows, total = product_service.list_products_page(include_invalidated=True, business_type="technical_analysis")

    assert total == 1
    assert rows[0]["product_id"] == old["product_id"]
    assert rows[0]["status"] == product_service.PRODUCT_STATUS_ACTIVE


def test_technical_analysis_product_reuse_invalidates_old_product_without_overwriting(
    business_env, tmp_path
):
    from business.config.constants import ServiceType
    from business.content.technical_analysis import TechnicalAnalysisResult
    from business.content.technical_analysis_handler import handle_technical_analysis
    from business.products.product_service import (
        PRODUCT_STATUS_ACTIVE,
        PRODUCT_STATUS_INVALIDATED,
        invalidate_active_products,
        list_products_page,
    )
    from business.routing.router import RouteResult

    route = RouteResult(True, ServiceType.TECHNICAL_ANALYSIS, "300502.SZ 技术分析", "300502.SZ")
    outputs = []
    for suffix in ("first", "second"):
        card = tmp_path / f"{suffix}-signal.png"
        chart = tmp_path / f"{suffix}-chart.png"
        report = tmp_path / f"{suffix}-report.md"
        card.write_bytes(f"{suffix}-card".encode("utf-8"))
        chart.write_bytes(f"{suffix}-chart".encode("utf-8"))
        report.write_text(f"{suffix} report", encoding="utf-8")
        outputs.append([str(card), str(chart), str(report)])

    def fake_handler(_openid, _raw_input, _target):
        output_files = outputs.pop(0)
        return TechnicalAnalysisResult(
            True,
            signal_card_path=output_files[0],
            main_chart_path=output_files[1],
            report_path=output_files[2],
            output_files=output_files,
            normalized_target="300502.SZ",
            stock_code="300502.SZ",
            stock_name="新易盛",
            market_date="2026-06-24",
            program_version="program-v1",
            ta_version="ta-v1",
            renderer_version="renderer-v1",
            template_version="template-v1",
            version_fingerprint="v1",
            cache_key="technical_analysis:300502.SZ:2026-06-24:v1",
            cache_hit=False,
        )

    first_reply = handle_technical_analysis(
        "ok",
        "300502.SZ 技术分析",
        route,
        technical_analysis_handler=fake_handler,
        cache_context=SimpleNamespace(cache_key="", normalized_target="300502.SZ", market_date="2026-06-24"),
    )

    assert first_reply.success is True
    rows, total = list_products_page(include_invalidated=True, business_type=str(ServiceType.TECHNICAL_ANALYSIS))
    assert total == 1
    assert rows[0]["status"] == PRODUCT_STATUS_ACTIVE
    first_product_id = rows[0]["product_id"]
    first_product_files = rows[0]["output_files"]

    assert invalidate_active_products(
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        target_key="300502.SZ",
        business_date="2026-06-24",
        version_fingerprint="v1",
    ) == 1

    second_reply = handle_technical_analysis(
        "ok",
        "300502.SZ 技术分析",
        route,
        technical_analysis_handler=fake_handler,
        cache_context=SimpleNamespace(cache_key="", normalized_target="300502.SZ", market_date="2026-06-24"),
    )

    assert second_reply.success is True
    rows, total = list_products_page(include_invalidated=True, business_type=str(ServiceType.TECHNICAL_ANALYSIS))

    assert total == 2
    assert [row["status"] for row in rows] == [PRODUCT_STATUS_ACTIVE, PRODUCT_STATUS_INVALIDATED]
    assert rows[0]["product_id"] != first_product_id
    assert rows[1]["product_id"] == first_product_id
    assert rows[0]["output_files"] != first_product_files
    assert rows[1]["output_files"] == first_product_files


def test_technical_analysis_malformed_empty_product_outputs_are_invalidated_and_rerun(
    business_env, tmp_path, monkeypatch
):
    from business.content import technical_analysis as technical_analysis
    from business.config.constants import ServiceType
    from business.products.product_service import (
        PRODUCT_STATUS_ACTIVE,
        PRODUCT_STATUS_INVALIDATED,
        create_product,
        list_products_page,
    )
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    create_product(
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        target_key="300502.SZ",
        target_label="300502.SZ 新易盛",
        business_date="2026-05-25",
        version_fingerprint="sha256:combined-v1",
        output_files=[],
        source_type="request",
    )
    monkeypatch.setattr(
        technical_analysis,
        "_versions",
        lambda: ("sha256:program-v1", "sha256:ta-v1", "sha256:renderer-v1", "sha256:template-v1"),
    )
    monkeypatch.setattr(
        technical_analysis,
        "_cache_version_fingerprint",
        lambda _ta_version, _renderer_version, _template_version: "sha256:combined-v1",
    )
    calls = _patch_fake_technical_analysis_pipeline(monkeypatch, tmp_path)

    class FakeResolver:
        def resolve(self, symbol, requested_market_date=""):
            assert symbol == "300502.SZ"
            assert requested_market_date == ""
            return SimpleNamespace(market_date="2026-05-25", known=True, source="fake")

    monkeypatch.setattr(technical_analysis, "MarketDateResolver", FakeResolver, raising=False)

    reply = handle_text_message("ok", "300502.SZ 技术分析")

    assert reply.success is True
    assert [call[0] for call in calls] == ["skill", "ai", "render"]
    assert list_request_records(limit=1)[0].cache_hit is False
    rows, total = list_products_page(include_invalidated=True, business_type=str(ServiceType.TECHNICAL_ANALYSIS))
    assert total == 2
    assert [row["status"] for row in rows] == [PRODUCT_STATUS_ACTIVE, PRODUCT_STATUS_INVALIDATED]
    assert rows[1]["output_files"] == []


def test_technical_analysis_failed_cache_write_keeps_old_product_active(
    business_env, tmp_path, monkeypatch
):
    from business.config.constants import ServiceType
    from business.content.technical_analysis import TechnicalAnalysisResult
    import business.content.technical_analysis_handler as ta_handler
    from business.products.product_service import PRODUCT_STATUS_ACTIVE, create_product, list_products_page
    from business.routing.router import RouteResult

    old_card = tmp_path / "old-signal.png"
    old_chart = tmp_path / "old-chart.png"
    old_report = tmp_path / "old-report.md"
    old_card.write_bytes(b"old-card")
    old_chart.write_bytes(b"old-chart")
    old_report.write_text("old report", encoding="utf-8")
    old_product = create_product(
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        target_key="300502.SZ",
        target_label="300502.SZ 新易盛",
        business_date="2026-06-24",
        version_fingerprint="v1",
        output_files=[str(old_card), str(old_chart), str(old_report)],
        source_type="request",
    )
    new_card = tmp_path / "new-signal.png"
    new_chart = tmp_path / "new-chart.png"
    new_report = tmp_path / "new-report.md"
    new_card.write_bytes(b"new-card")
    new_chart.write_bytes(b"new-chart")
    new_report.write_text("new report", encoding="utf-8")

    def fail_cache_write(**_kwargs):
        raise RuntimeError("cache write failed")

    monkeypatch.setattr(ta_handler, "write_business_cache", fail_cache_write)
    route = RouteResult(True, ServiceType.TECHNICAL_ANALYSIS, "300502.SZ 技术分析", "300502.SZ")

    reply = ta_handler.handle_technical_analysis(
        "ok",
        "300502.SZ 技术分析",
        route,
        technical_analysis_handler=lambda _openid, _raw_input, _target: TechnicalAnalysisResult(
            True,
            signal_card_path=str(new_card),
            main_chart_path=str(new_chart),
            report_path=str(new_report),
            output_files=[str(new_card), str(new_chart), str(new_report)],
            normalized_target="300502.SZ",
            stock_code="300502.SZ",
            stock_name="新易盛",
            market_date="2026-06-24",
            program_version="program-v1",
            ta_version="ta-v1",
            renderer_version="renderer-v1",
            template_version="template-v1",
            version_fingerprint="v1",
            cache_key="technical_analysis:300502.SZ:2026-06-24:v1",
            cache_hit=False,
        ),
        cache_context=SimpleNamespace(cache_key="", normalized_target="300502.SZ", market_date="2026-06-24"),
    )

    assert reply.success is False
    rows, total = list_products_page(include_invalidated=True, business_type=str(ServiceType.TECHNICAL_ANALYSIS))
    assert total == 1
    assert rows[0]["product_id"] == old_product["product_id"]
    assert rows[0]["status"] == PRODUCT_STATUS_ACTIVE


def test_product_service_expired_offset_expires_at_is_not_active(business_env, tmp_path, monkeypatch):
    import business.products.product_service as product_service

    card = tmp_path / "expired-card.png"
    card.write_bytes(b"expired")
    monkeypatch.setattr(product_service, "_now", lambda: "2026-06-24T00:00:01+00:00")

    product = product_service.create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        business_date="2026-06-24",
        version_fingerprint="v1",
        output_files=[str(card)],
        expires_at="2026-06-24T08:00:00+08:00",
    )

    assert product["expires_at"] == "2026-06-24T00:00:00+00:00"
    assert product_service.find_active_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        business_date="2026-06-24",
        version_fingerprint="v1",
    ) is None


def test_product_service_normalizes_naive_and_date_only_expires_at(business_env, tmp_path):
    from business.products import product_service

    card = tmp_path / "date-card.png"
    card.write_bytes(b"date")

    naive = product_service.create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        business_date="2026-06-24",
        version_fingerprint="naive",
        output_files=[str(card)],
        expires_at="2026-06-24T08:00:00",
    )
    date_only = product_service.create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        business_date="2026-06-24",
        version_fingerprint="date-only",
        output_files=[str(card)],
        expires_at="2026-06-24",
    )

    assert naive["expires_at"] == "2026-06-24T08:00:00+00:00"
    assert date_only["expires_at"] == "2026-06-24T00:00:00+00:00"


def test_product_service_uses_deterministic_order_when_created_timestamps_tie(
    business_env, tmp_path, monkeypatch
):
    from types import SimpleNamespace

    import business.products.product_service as product_service

    card = tmp_path / "tie-card.png"
    card.write_bytes(b"tie")
    product_ids = iter(
        [
            SimpleNamespace(hex="f" * 32),
            SimpleNamespace(hex="0" * 32),
        ]
    )
    monkeypatch.setattr(product_service, "_now", lambda: "2026-06-24T00:00:00+00:00")
    monkeypatch.setattr(product_service, "uuid4", lambda: next(product_ids))

    first = product_service.create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        business_date="2026-06-24",
        version_fingerprint="v1",
        output_files=[str(card)],
    )
    second = product_service.create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        business_date="2026-06-24",
        version_fingerprint="v1",
        output_files=[str(card)],
    )

    assert first["created_at"] == second["created_at"]
    assert product_service.find_active_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        business_date="2026-06-24",
        version_fingerprint="v1",
    )["product_id"] == second["product_id"]


def test_find_cache_entry_missing_cache_file_invalidates_active_entry(business_env, tmp_path):
    from business.cache.cache_service import build_cache_key, find_cache_entry, list_cache_entries, write_cache_entry
    from business.config.constants import ServiceType

    card = tmp_path / "card.png"
    chart = tmp_path / "chart.png"
    report = tmp_path / "report.md"
    card.write_bytes(b"card")
    chart.write_bytes(b"chart")
    report.write_text("report", encoding="utf-8")
    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-05-25", "v1")
    write_cache_entry(
        cache_key=cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-05-25",
        version_fingerprint="v1",
        output_files=[str(card), str(chart), str(report)],
        artifact_owner_id="request-1",
    )
    chart.unlink()

    entry = find_cache_entry(
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-05-25",
        version_fingerprint="v1",
        require_files=True,
    )

    assert entry is None
    assert list_cache_entries(service_type=ServiceType.TECHNICAL_ANALYSIS) == []
    entries = list_cache_entries(service_type=ServiceType.TECHNICAL_ANALYSIS, include_invalidated=True)
    assert len(entries) == 1
    assert entries[0].cache_key == cache_key
    assert entries[0].status == "invalidated"


def test_find_cache_entry_missing_cache_file_does_not_invalidate_rewritten_active_entry(
    business_env, tmp_path, monkeypatch
):
    from business.cache import cache_service as cache_service
    from business.cache.cache_service import build_cache_key, list_cache_entries, write_cache_entry
    from business.config.constants import ServiceType
    from business.products import product_service

    old_card = tmp_path / "old-card.png"
    new_card = tmp_path / "new-card.png"
    new_card.write_bytes(b"new-card")
    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-05-25", "v1")
    write_cache_entry(
        cache_key=cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-05-25",
        version_fingerprint="v1",
        output_files=[str(old_card)],
        artifact_owner_id="request-old",
    )

    def rewrite_entry_before_missing_file_result(paths):
        assert paths == [str(old_card)]
        write_cache_entry(
            cache_key=cache_key,
            service_type=ServiceType.TECHNICAL_ANALYSIS,
            normalized_target="300502.SZ",
            market_date="2026-05-25",
            version_fingerprint="v1",
            output_files=[str(new_card)],
            artifact_owner_id="request-new",
        )
        return False

    monkeypatch.setattr(product_service, "_files_available", rewrite_entry_before_missing_file_result)

    entry = cache_service.find_cache_entry(
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-05-25",
        version_fingerprint="v1",
        require_files=True,
    )

    assert entry is None
    entries = list_cache_entries(service_type=ServiceType.TECHNICAL_ANALYSIS)
    assert len(entries) == 1
    assert entries[0].cache_key == cache_key
    assert entries[0].status == "active"
    assert entries[0].output_files == [str(new_card)]
    assert entries[0].artifact_owner_id == "request-new"


def test_write_cache_entry_concurrent_same_key_uses_single_active_entry(business_env):
    from concurrent.futures import ThreadPoolExecutor

    from business.cache.cache_service import build_cache_key, list_cache_entries, write_cache_entry
    from business.config.constants import ServiceType

    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-05-25", "v1")

    def write(output_file: str):
        return write_cache_entry(
            cache_key=cache_key,
            service_type=ServiceType.TECHNICAL_ANALYSIS,
            normalized_target="300502.SZ",
            market_date="2026-05-25",
            version_fingerprint="v1",
            output_files=[output_file],
            artifact_owner_id=output_file,
        )

    output_files = [f"/tmp/card-{index}.png" for index in range(12)]
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(write, output_files))

    assert {result.cache_key for result in results} == {cache_key}
    entries = list_cache_entries(service_type=ServiceType.TECHNICAL_ANALYSIS)
    assert len(entries) == 1
    assert entries[0].cache_key == cache_key
    assert entries[0].status == "active"
    assert entries[0].hit_count >= 0
    assert entries[0].output_files in [[output_file] for output_file in output_files]
    assert entries[0].artifact_owner_id in set(output_files)


def test_web_business_cache_handlers_list_and_clear_entries(business_env, monkeypatch):
    from business.cache.cache_service import build_cache_key, write_cache_entry
    from business.config.constants import ServiceType
    from business.products import product_service
    from channel.web.web_channel import InvestmentCacheClearHandler, InvestmentCacheEntryInvalidateHandler, InvestmentCacheHandler

    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-05-25", "v1")
    write_cache_entry(
        cache_key=cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-05-25",
        version_fingerprint="v1",
        output_files=["/tmp/card.png", "/tmp/chart.png", "/tmp/report.md"],
        artifact_owner_id="request-1",
    )

    list_payload = _call_investment_json_handler(monkeypatch, InvestmentCacheHandler().GET, params={"limit": "20"})

    assert list_payload["status"] == "success", list_payload
    assert list_payload["pagination"]["total"] == 1
    product_id = list_payload["entries"][0]["product_id"]
    assert list_payload["entries"][0]["source_type"] == "product"
    assert list_payload["entries"][0]["cache_key"] == cache_key
    assert list_payload["entries"][0]["source_cache_key"] == cache_key
    assert list_payload["entries"][0]["output_files"] == ["/tmp/card.png", "/tmp/chart.png", "/tmp/report.md"]
    backfill_result = product_service.backfill_products_from_legacy_sources()
    assert backfill_result["cache_created"] == 0

    invalidate_payload = _call_investment_json_handler(
        monkeypatch,
        lambda: InvestmentCacheEntryInvalidateHandler().POST(cache_key),
        body={"operator": "tester"},
    )

    assert invalidate_payload["status"] == "success"
    assert invalidate_payload["invalidated"] is True

    default_list_payload = _call_investment_json_handler(monkeypatch, InvestmentCacheHandler().GET, params={"limit": "20"})
    assert default_list_payload["status"] == "success"
    assert default_list_payload["entries"] == []
    assert default_list_payload["pagination"]["total"] == 0

    invalidated_list_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={"limit": "20", "include_invalidated": "1"},
    )
    assert invalidated_list_payload["status"] == "success"
    assert invalidated_list_payload["entries"][0]["product_id"] == product_id
    assert invalidated_list_payload["entries"][0]["status"] == "invalidated"

    write_cache_entry(
        cache_key=cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-05-25",
        version_fingerprint="v1",
        output_files=["/tmp/card.png"],
        artifact_owner_id="request-2",
    )
    active_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={"limit": "20", "service_type": "technical_analysis", "market_date": "2026-05-25"},
    )
    active_product_id = active_payload["entries"][0]["product_id"]
    assert active_product_id != product_id
    clear_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheClearHandler().POST,
        body={"service_type": "technical_analysis", "market_date": "2026-05-25", "operator": "tester"},
    )

    assert clear_payload["status"] == "success"
    assert clear_payload["removed"] == 1
    assert clear_payload["legacy_removed"] == 1
    assert clear_payload["products_invalidated"] == 0

    cleared_default_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={"limit": "20", "service_type": "technical_analysis", "market_date": "2026-05-25"},
    )
    assert cleared_default_payload["status"] == "success"
    assert cleared_default_payload["entries"] == []

    cleared_invalidated_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={"limit": "20", "service_type": "technical_analysis", "market_date": "2026-05-25", "include_invalidated": "1"},
    )
    assert cleared_invalidated_payload["status"] == "success"
    assert cleared_invalidated_payload["entries"][0]["source_type"] == "product"
    assert cleared_invalidated_payload["entries"][0]["product_id"] == active_product_id
    assert cleared_invalidated_payload["entries"][0]["status"] == "invalidated"


def test_investment_products_api_lists_and_invalidates_products(business_env, monkeypatch):
    from business.products import product_service
    from channel.web.web_channel import InvestmentProductInvalidateHandler, InvestmentProductsHandler

    product = product_service.create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="新易盛",
        business_date="2026-06-24",
        version_fingerprint="v1",
        source_request_id="request-1",
        source_type="request",
        output_files=["/tmp/card.png"],
    )

    list_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentProductsHandler().GET,
        params={"business_type": "technical_analysis", "include_invalidated": "1"},
    )

    assert list_payload["status"] == "success"
    assert list_payload["entries"][0]["product_id"] == product["product_id"]
    assert list_payload["entries"][0]["status"] == "active"

    invalidate_payload = _call_investment_json_handler(
        monkeypatch,
        lambda: InvestmentProductInvalidateHandler().POST(product["product_id"]),
    )

    assert invalidate_payload["status"] == "success"
    assert invalidate_payload["invalidated"] is True


def test_generated_history_api_reads_backfilled_products_not_legacy_sources(business_env, monkeypatch, tmp_path):
    from business.cache.cache_service import build_cache_key, write_cache_entry
    from business.config.constants import ServiceType
    from business.products.product_service import backfill_products_from_legacy_sources
    from channel.web.web_channel import InvestmentProductsHandler

    output = tmp_path / "legacy.png"
    output.write_text("legacy", encoding="utf-8")
    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-06-20", "v1")
    write_cache_entry(
        cache_key=cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-06-20",
        version_fingerprint="v1",
        output_files=[str(output)],
        artifact_owner_id="req-backfilled",
    )
    backfill_products_from_legacy_sources()

    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentProductsHandler().GET,
        params={"include_invalidated": "1", "page_size": "20"},
    )

    assert payload["status"] == "success"
    assert payload["pagination"]["total"] == 1
    assert payload["entries"][0]["source_type"] == "cache"
    assert payload["entries"][0]["source_cache_key"] == cache_key


def test_generated_history_apis_filter_component_products_by_service_type(business_env, monkeypatch):
    from business.products.product_service import create_product
    from channel.web.web_channel import InvestmentCacheHandler, InvestmentProductsHandler

    service_type = "component:technical-analysis"
    product = create_product(
        business_type=service_type,
        target_key="300502.SZ",
        target_label="新易盛",
        business_date="2026-06-24",
        version_fingerprint="component-v1",
        source_type="request",
        source_request_id="request-component",
        output_files=["/tmp/component-card.png"],
    )

    products_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentProductsHandler().GET,
        params={"service_type": service_type, "include_invalidated": "1"},
    )
    cache_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={"service_type": service_type, "include_invalidated": "1", "limit": "20"},
    )

    assert products_payload["status"] == "success"
    assert products_payload["pagination"]["total"] == 1
    assert products_payload["entries"][0]["product_id"] == product["product_id"]
    assert cache_payload["status"] == "success"
    assert cache_payload["pagination"]["total"] == 1
    assert cache_payload["entries"][0]["product_id"] == product["product_id"]


def test_artifact_browser_includes_invalidated_products_only_when_requested(business_env, monkeypatch):
    from business.products.product_service import (
        PRODUCT_STATUS_ACTIVE,
        PRODUCT_STATUS_ARCHIVED,
        PRODUCT_STATUS_FAILED,
        PRODUCT_STATUS_INVALIDATED,
        create_product,
    )
    from business.records.business_records import list_artifact_folder_nodes, list_artifact_packages_page
    from channel.web.web_channel import InvestmentArtifactFoldersHandler, InvestmentArtifactPackagesHandler

    def make_product(label, status=PRODUCT_STATUS_ACTIVE, expires_at=""):
        return create_product(
            business_type="technical_analysis",
            target_key=f"target-{label}",
            target_label=f"Target {label}",
            business_date="2026-06-24",
            version_fingerprint=f"v-{label}",
            status=status,
            source_type="request",
            source_request_id=f"request-{label}",
            output_files=[f"/tmp/{label}.png"],
            expires_at=expires_at,
        )

    active = make_product("active")
    invalidated = make_product("invalidated", PRODUCT_STATUS_INVALIDATED)
    archived = make_product("archived", PRODUCT_STATUS_ARCHIVED)
    failed = make_product("failed", PRODUCT_STATUS_FAILED)
    expired = make_product("expired", PRODUCT_STATUS_ACTIVE, expires_at="2000-01-01T00:00:00+00:00")

    default_packages, default_total = list_artifact_packages_page(service_type="technical_analysis", page_size=20)
    active_only_packages, active_only_total = list_artifact_packages_page(
        service_type="technical_analysis",
        page_size=20,
        status_category="active",
    )
    default_dates, default_dates_total = list_artifact_folder_nodes(
        level="date",
        service_type="technical_analysis",
        month="2026-06",
        page_size=20,
    )

    assert default_total == 5
    assert {item["product_id"] for item in default_packages} == {
        active["product_id"],
        invalidated["product_id"],
        archived["product_id"],
        failed["product_id"],
        expired["product_id"],
    }
    assert active_only_total == 1
    assert [item["product_id"] for item in active_only_packages] == [active["product_id"]]
    assert default_dates_total == 1
    assert default_dates[0]["count"] == 5

    included_packages, included_total = list_artifact_packages_page(
        service_type="technical_analysis",
        page_size=20,
        include_invalidated=True,
    )
    included_dates, included_dates_total = list_artifact_folder_nodes(
        level="date",
        service_type="technical_analysis",
        month="2026-06",
        page_size=20,
        include_invalidated=True,
    )

    assert included_total == 5
    assert {item["product_id"] for item in included_packages} == {
        active["product_id"],
        invalidated["product_id"],
        archived["product_id"],
        failed["product_id"],
        expired["product_id"],
    }
    assert included_dates_total == 1
    assert included_dates[0]["count"] == 5

    default_handler_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentArtifactPackagesHandler().GET,
        params={"service_type": "technical_analysis", "page_size": "20"},
    )
    included_handler_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentArtifactPackagesHandler().GET,
        params={"service_type": "technical_analysis", "page_size": "20", "include_invalidated": "1"},
    )
    included_folder_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentArtifactFoldersHandler().GET,
        params={"level": "date", "service_type": "technical_analysis", "month": "2026-06", "include_invalidated": "1"},
    )

    assert default_handler_payload["status"] == "success"
    assert default_handler_payload["pagination"]["total"] == 5
    assert included_handler_payload["status"] == "success"
    assert included_handler_payload["pagination"]["total"] == 5
    assert included_folder_payload["status"] == "success"
    assert included_folder_payload["nodes"][0]["count"] == 5


def test_cache_key_invalidation_invalidates_backfilled_product_history(business_env, monkeypatch, tmp_path):
    from business.cache.cache_service import build_cache_key, write_cache_entry
    from business.config.constants import ServiceType
    from business.products.product_service import backfill_products_from_legacy_sources
    from channel.web.web_channel import InvestmentCacheEntryInvalidateHandler, InvestmentCacheHandler

    output = tmp_path / "legacy-cache.png"
    output.write_text("legacy cache output", encoding="utf-8")
    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-06-21", "v1")
    write_cache_entry(
        cache_key=cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-06-21",
        version_fingerprint="v1",
        output_files=[str(output)],
        artifact_owner_id="req-cache-invalidate",
    )
    backfill_result = backfill_products_from_legacy_sources()
    assert backfill_result["cache_created"] == 0

    initial_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={"service_type": "technical_analysis", "market_date": "2026-06-21", "limit": "20"},
    )
    assert initial_payload["status"] == "success"
    assert initial_payload["pagination"]["total"] == 1
    product_id = initial_payload["entries"][0]["product_id"]
    assert initial_payload["entries"][0]["source_cache_key"] == cache_key

    invalidate_payload = _call_investment_json_handler(
        monkeypatch,
        lambda: InvestmentCacheEntryInvalidateHandler().POST(cache_key),
        body={"operator": "tester"},
    )
    assert invalidate_payload["status"] == "success"
    assert invalidate_payload["invalidated"] is True

    default_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={"service_type": "technical_analysis", "market_date": "2026-06-21", "limit": "20"},
    )
    assert default_payload["status"] == "success"
    assert default_payload["entries"] == []
    assert default_payload["pagination"]["total"] == 0

    archived_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={
            "service_type": "technical_analysis",
            "market_date": "2026-06-21",
            "limit": "20",
            "include_invalidated": "1",
        },
    )
    assert archived_payload["status"] == "success"
    assert archived_payload["pagination"]["total"] == 1
    assert archived_payload["entries"][0]["product_id"] == product_id
    assert archived_payload["entries"][0]["source_cache_key"] == cache_key
    assert archived_payload["entries"][0]["status"] == "invalidated"


def test_cache_key_invalidation_preserves_terminal_product_history(business_env):
    from business.cache.cache_service import build_cache_key
    from business.config.constants import ServiceType
    from business.products.product_service import (
        PRODUCT_STATUS_ACTIVE,
        PRODUCT_STATUS_ARCHIVED,
        PRODUCT_STATUS_FAILED,
        PRODUCT_STATUS_INVALIDATED,
        create_product,
        invalidate_products_by_source,
        list_products_page,
    )

    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-06-22", "v1")
    active = create_product(
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        target_key="300502.SZ",
        target_label="新易盛",
        business_date="2026-06-22",
        version_fingerprint="v1",
        source_cache_key=cache_key,
        source_type="cache",
        output_files=["/tmp/active-card.png"],
    )
    archived = create_product(
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        target_key="300502.SZ",
        target_label="新易盛",
        business_date="2026-06-22",
        version_fingerprint="archived-v1",
        status=PRODUCT_STATUS_ARCHIVED,
        source_cache_key=cache_key,
        source_type="cache",
        output_files=["/tmp/archived-card.png"],
    )
    failed = create_product(
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        target_key="300502.SZ",
        target_label="新易盛",
        business_date="2026-06-22",
        version_fingerprint="failed-v1",
        status=PRODUCT_STATUS_FAILED,
        source_cache_key=cache_key,
        source_type="cache",
        output_files=["/tmp/failed-card.png"],
    )

    invalidated_count = invalidate_products_by_source(source_cache_key=cache_key)

    products, total = list_products_page(
        include_invalidated=True,
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        business_date="2026-06-22",
    )
    by_product_id = {product["product_id"]: product for product in products}
    assert invalidated_count == 1
    assert total == 3
    assert by_product_id[active["product_id"]]["status"] == PRODUCT_STATUS_INVALIDATED
    assert by_product_id[archived["product_id"]]["status"] == PRODUCT_STATUS_ARCHIVED
    assert by_product_id[failed["product_id"]]["status"] == PRODUCT_STATUS_FAILED
    assert PRODUCT_STATUS_ACTIVE not in {product["status"] for product in products}


def test_web_business_cache_handler_sanitizes_limit_and_rejects_unmatched_service_type(business_env, monkeypatch):
    from business.cache.cache_service import build_cache_key, write_cache_entry
    from business.config.constants import ServiceType
    from business.products.product_service import backfill_products_from_legacy_sources
    from channel.web.web_channel import InvestmentCacheHandler

    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-05-25", "v1")
    write_cache_entry(
        cache_key=cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-05-25",
        version_fingerprint="v1",
        output_files=["/tmp/card.png"],
        artifact_owner_id="request-1",
    )
    backfill_result = backfill_products_from_legacy_sources()
    assert backfill_result["cache_created"] == 0

    invalid_limit_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={"service_type": "technical_analysis", "limit": "bad"},
    )
    unmatched_service_payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentCacheHandler().GET,
        params={"service_type": "unknown-service", "limit": "20"},
    )

    assert invalid_limit_payload["status"] == "success"
    assert [entry["cache_key"] for entry in invalid_limit_payload["entries"]] == [cache_key]
    assert invalid_limit_payload["market_dates"] == ["2026-05-25"]
    assert unmatched_service_payload["status"] == "success"
    assert unmatched_service_payload["entries"] == []


def test_file_serve_handler_rejects_paths_outside_allowed_storage(business_env, tmp_path, monkeypatch):
    from channel.web import web_channel
    from channel.web.web_channel import FileServeHandler

    _login_default_investment_admin(monkeypatch)
    secret = tmp_path / "outside-secret.txt"
    secret.write_text("secret", encoding="utf-8")
    monkeypatch.setattr(web_channel.web, "input", lambda **_defaults: SimpleNamespace(path=str(secret)))
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)

    with pytest.raises(web_channel.web.HTTPError):
        FileServeHandler().GET()


def test_file_serve_handler_allows_business_storage_file(business_env, monkeypatch):
    from business.schema.storage import get_storage_dirs
    from channel.web import web_channel
    from channel.web.web_channel import FileServeHandler

    _login_default_investment_admin(monkeypatch)
    image = get_storage_dirs()["tmp"] / "allowed.png"
    image.write_bytes(b"png")
    monkeypatch.setattr(web_channel.web, "input", lambda **_defaults: SimpleNamespace(path=str(image)))
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)

    assert FileServeHandler().GET() == b"png"


def test_file_serve_handler_allows_file_id_lookup(business_env, tmp_path, monkeypatch):
    from business.config.constants import ServiceType
    from business.records.records import create_request_record, list_output_files, succeed_request_record
    from channel.web import web_channel
    from channel.web.web_channel import FileServeHandler

    _login_default_investment_admin(monkeypatch)
    image = tmp_path / "id-file.png"
    image.write_bytes(b"file-id-png")
    request_id = create_request_record("openid", "利率", ServiceType.RATE)
    succeed_request_record(
        request_id,
        output_files=[str(image)],
        elapsed_ms=1,
        artifact_roles={str(image): "output_image"},
    )
    file_id = list_output_files(request_id)[0]["file_id"]
    monkeypatch.setattr(web_channel.web, "input", lambda **_defaults: SimpleNamespace(path="", id=file_id))
    headers = {}
    monkeypatch.setattr(web_channel.web, "header", lambda key, value: headers.setdefault(key, value))

    assert FileServeHandler().GET() == b"file-id-png"
    assert headers["Content-Type"] == "image/png"


def test_stock_resolver_resolves_codes_names_and_business_prompts(business_env, monkeypatch):
    from business.content import stock_resolver as stock_resolver
    from business.config.constants import ErrorCode, user_message
    from business.content.stock_resolver import (
        list_stock_symbols,
        refresh_stock_symbols,
        resolve_stock as core_resolve_stock,
        stock_dictionary_stats,
    )

    inserted = refresh_stock_symbols(
        [
            {"code": "300502.SZ", "name": "新易盛", "market": "SZ", "ts_code": "300502.SZ"},
            {"code": "00700.HK", "name": "腾讯控股", "market": "HK", "ts_code": "00700.HK"},
            {"code": "AAPL.US", "name": "苹果", "market": "US", "ts_code": "AAPL"},
            {"code": "000001.SZ", "name": "重名", "market": "SZ"},
            {"code": "A00001.US", "name": "重名", "market": "US", "source": "tushare_us"},
        ],
        source="tushare_a",
    )

    assert inserted == 5
    assert core_resolve_stock("300502") == ("300502.SZ", None)
    assert core_resolve_stock("300502.SZ") == ("300502.SZ", None)
    assert core_resolve_stock("600519.SH") == ("600519.SH", None)
    assert core_resolve_stock("00700.HK") == ("00700.HK", None)
    assert core_resolve_stock("AAPL.US") == ("AAPL.US", None)
    assert core_resolve_stock("新易盛") == ("300502.SZ", None)
    assert core_resolve_stock("腾讯控股") == ("00700.HK", None)
    assert core_resolve_stock("苹果") == ("AAPL.US", None)
    assert core_resolve_stock("不存在的股票") == (None, ErrorCode.STOCK_NOT_FOUND)
    assert core_resolve_stock("重名") == (None, ErrorCode.STOCK_AMBIGUOUS)
    assert [row["code"] for row in list_stock_symbols("新", limit=5)] == ["300502.SZ"]
    assert stock_dictionary_stats()["total"] == 5

    ambiguous_symbol, ambiguous_error = core_resolve_stock("重名")

    assert ambiguous_symbol is None
    assert ambiguous_error == ErrorCode.STOCK_AMBIGUOUS
    assert user_message(ambiguous_error) == "股票名称匹配到多个标的，请改用股票代码。"


def test_stock_resolver_ignores_non_tushare_rows_for_name_resolution(business_env):
    from business.content import stock_resolver as stock_resolver
    from business.config.constants import ErrorCode

    stock_resolver.refresh_stock_symbols(
        [{"code": "AAPL.US", "name": "苹果", "market": "US", "source": "akshare"}],
        source="akshare",
    )

    assert stock_resolver.resolve_stock("苹果") == (None, ErrorCode.STOCK_NOT_FOUND)


def test_stock_resolver_refreshes_all_markets_from_tushare_with_explicit_functions(business_env, monkeypatch):
    from business.content import stock_resolver as stock_resolver
    monkeypatch.setattr(stock_resolver, "get_tushare_token", lambda: "token")
    fake_tushare = SimpleNamespace(
        pro_api=lambda _token: SimpleNamespace(
            stock_basic=lambda **_kwargs: _FakeDataFrame(
                [
                    {"ts_code": "300502.SZ", "symbol": "300502", "name": "新易盛", "exchange": "SZSE"},
                    {"ts_code": "600519.SH", "symbol": "600519", "name": "贵州茅台", "exchange": "SSE"},
                ]
            ),
            hk_basic=lambda **_kwargs: _FakeDataFrame(
                [
                    {"ts_code": "00700.HK", "name": "腾讯控股", "fullname": "腾讯控股有限公司"},
                    {"ts_code": "09988.HK", "name": "阿里巴巴-W", "fullname": "阿里巴巴集团控股有限公司"},
                ]
            ),
            us_basic=lambda **_kwargs: _FakeDataFrame(
                [
                    {"ts_code": "AAPL", "name": "苹果", "enname": "Apple Inc."},
                    {"ts_code": "MSFT", "name": "微软", "enname": "Microsoft Corporation"},
                    {"ts_code": "NOZH", "name": None, "enname": "No Chinese Name"},
                ]
            ),
        )
    )
    monkeypatch.setitem(sys.modules, "tushare", fake_tushare)

    assert stock_resolver.refresh_a_share_symbols_from_tushare() == 2
    assert stock_resolver.refresh_hk_symbols_from_tushare() == 2
    assert stock_resolver.refresh_us_symbols_from_tushare() == 2
    assert stock_resolver.refresh_all_symbols_from_tushare() == {
        "a_share": {"count": 2},
        "hk": {"count": 2},
        "us": {"count": 2},
    }

    rows = {row["code"]: row for row in stock_resolver.list_stock_symbols(limit=20)}
    assert rows["300502.SZ"]["name"] == "新易盛"
    assert rows["300502.SZ"]["market"] == "SZ"
    assert rows["300502.SZ"]["source"] == "tushare_a"
    assert rows["00700.HK"]["name"] == "腾讯控股"
    assert rows["00700.HK"]["market"] == "HK"
    assert rows["00700.HK"]["source"] == "tushare_hk"
    assert rows["AAPL.US"]["name"] == "苹果"
    assert rows["AAPL.US"]["market"] == "US"
    assert rows["AAPL.US"]["source"] == "tushare_us"
    assert "NOZH.US" not in rows


def test_stock_resolver_name_miss_does_not_auto_refresh_or_guess(business_env, monkeypatch):
    from business.content import stock_resolver as stock_resolver
    from business.config.constants import ErrorCode

    monkeypatch.setattr(
        stock_resolver,
        "refresh_all_symbols_from_tushare",
        lambda: pytest.fail("name resolution must not refresh during customer requests"),
        raising=False,
    )

    assert stock_resolver.resolve_stock("新易盛") == (None, ErrorCode.STOCK_NOT_FOUND)
    assert stock_resolver.resolve_stock("300502") == ("300502.SZ", None)
    assert stock_resolver.resolve_stock("300502.SZ") == ("300502.SZ", None)
    assert stock_resolver.resolve_stock("00700.HK") == ("00700.HK", None)
    assert stock_resolver.resolve_stock("AAPL.US") == ("AAPL.US", None)


def test_stock_resolver_reports_ambiguous_tushare_dictionary_names(business_env):
    from business.content import stock_resolver as stock_resolver
    from business.config.constants import ErrorCode

    stock_resolver.refresh_stock_symbols(
        [
            {"code": "000001.SZ", "name": "重名", "market": "SZ", "source": "tushare_a"},
            {"code": "A00001.US", "name": "重名", "market": "US", "source": "tushare_us"},
        ],
        source="tushare-test",
    )

    assert stock_resolver.resolve_stock("重名") == (None, ErrorCode.STOCK_AMBIGUOUS)


class _FakeDataFrame:
    def __init__(self, rows):
        self._rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return self._rows


def test_stock_resolver_refreshes_large_symbol_batch(business_env):
    from business.content import stock_resolver as stock_resolver
    rows = [
        {"code": f"{index:06d}.SZ", "name": f"Test Stock {index}", "market": "SZ"}
        for index in range(6000)
    ]

    assert stock_resolver.refresh_stock_symbols(rows, source="large-batch") == 6000
    assert stock_resolver.stock_dictionary_stats()["total"] == 6000


def test_stock_resolver_tushare_token_priority_and_masking(business_env, tmp_path, monkeypatch):
    from business.content import stock_resolver as stock_resolver
    from business.config.config_service import get_config, save_config

    monkeypatch.setattr(stock_resolver.Path, "home", lambda: tmp_path)
    (tmp_path / ".tushare_token").write_text("file-token-1234567890", encoding="utf-8")
    monkeypatch.setenv("TUSHARE_TOKEN", "env-token-1234567890")

    assert stock_resolver.get_tushare_token() == "env-token-1234567890"

    save_config("tushare.token", "config-token-1234567890", operator_role="admin")

    assert stock_resolver.get_tushare_token() == "config-token-1234567890"
    assert stock_resolver.get_tushare_token(masked=True) == "conf**********7890"
    assert get_config("tushare.token", masked=True) == "conf**********7890"


def test_stock_resolver_tushare_token_falls_back_to_file(business_env, tmp_path, monkeypatch):
    from business.content import stock_resolver as stock_resolver
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.setattr(stock_resolver.Path, "home", lambda: tmp_path)
    (tmp_path / ".tushare_token").write_text("file-token-1234567890\n", encoding="utf-8")

    assert stock_resolver.get_tushare_token() == "file-token-1234567890"


def test_stock_resolver_refresh_from_tushare_requires_token(business_env, tmp_path, monkeypatch):
    from business.content import stock_resolver as stock_resolver
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.setattr(stock_resolver.Path, "home", lambda: tmp_path)

    with pytest.raises(RuntimeError, match="tushare token not configured"):
        stock_resolver.refresh_a_share_symbols_from_tushare()


def test_stock_resolver_refreshes_from_tushare_fake_dataframe(business_env, monkeypatch):
    from business.content import stock_resolver as stock_resolver
    from business.config.config_service import save_config

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

    assert stock_resolver.refresh_a_share_symbols_from_tushare() == 2

    assert calls == [
        {"token": "config-token-1234567890"},
        {"exchange": "", "list_status": "L", "fields": "ts_code,symbol,name,exchange"},
    ]
    rows = {row["code"]: row for row in stock_resolver.list_stock_symbols(limit=10)}
    assert rows["600519.SH"]["ts_code"] == "600519.SH"
    assert rows["600519.SH"]["market"] == "SH"
    assert rows["600519.SH"]["source"] == "tushare_a"
    assert rows["300502.SZ"]["ts_code"] == "300502.SZ"
    assert rows["300502.SZ"]["market"] == "SZ"
    assert rows["300502.SZ"]["source"] == "tushare_a"


def test_stock_resolver_all_tushare_reports_market_counts_and_errors(business_env, monkeypatch):
    from business.content import stock_resolver as stock_resolver
    monkeypatch.setattr(stock_resolver, "refresh_a_share_symbols_from_tushare", lambda: 2)
    monkeypatch.setattr(stock_resolver, "refresh_hk_symbols_from_tushare", lambda: 3)
    monkeypatch.setattr(stock_resolver, "refresh_us_symbols_from_tushare", lambda: 4)

    assert stock_resolver.refresh_all_symbols_from_tushare() == {
        "a_share": {"count": 2},
        "hk": {"count": 3},
        "us": {"count": 4},
    }

    monkeypatch.setattr(stock_resolver, "refresh_a_share_symbols_from_tushare", lambda: (_ for _ in ()).throw(RuntimeError("a failed")))
    monkeypatch.setattr(stock_resolver, "refresh_hk_symbols_from_tushare", lambda: (_ for _ in ()).throw(RuntimeError("hk failed")))
    monkeypatch.setattr(stock_resolver, "refresh_us_symbols_from_tushare", lambda: (_ for _ in ()).throw(RuntimeError("us failed")))

    assert stock_resolver.refresh_all_symbols_from_tushare() == {
        "a_share": {"error": "a failed"},
        "hk": {"error": "hk failed"},
        "us": {"error": "us failed"},
    }


def test_refresh_business_stocks_script_dispatches_sources(business_env, monkeypatch, capsys):
    from scripts import refresh_business_stocks

    calls = []
    monkeypatch.setattr(refresh_business_stocks.storage, "initialize_storage", lambda: calls.append("init"))
    monkeypatch.setattr(refresh_business_stocks.stock_resolver, "refresh_all_symbols_from_tushare", lambda: calls.append("all") or {"a_share": {"count": 2}, "hk": {"count": 3}, "us": {"count": 4}})
    monkeypatch.setattr(refresh_business_stocks.stock_resolver, "refresh_a_share_symbols_from_tushare", lambda: calls.append("a_share") or 3)
    monkeypatch.setattr(refresh_business_stocks.stock_resolver, "refresh_hk_symbols_from_tushare", lambda: calls.append("hk") or 4)
    monkeypatch.setattr(refresh_business_stocks.stock_resolver, "refresh_us_symbols_from_tushare", lambda: calls.append("us") or 5)

    assert refresh_business_stocks.main(["--source", "all", "--json"]) == 0
    assert refresh_business_stocks.main(["--source", "a_share", "--json"]) == 0
    assert refresh_business_stocks.main(["--source", "hk", "--json"]) == 0
    assert refresh_business_stocks.main(["--source", "us", "--json"]) == 0

    assert calls == ["init", "all", "init", "a_share", "init", "hk", "init", "us"]
    payloads = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
    assert [payload["source"] for payload in payloads] == ["all", "a_share", "hk", "us"]
    assert [payload["count"] for payload in payloads] == [9, 3, 4, 5]
    assert all(payload["success"] is True for payload in payloads)
    assert all(payload["database"] == "postgresql" for payload in payloads)


def test_refresh_business_stocks_script_exits_one_when_all_sources_fail(business_env, monkeypatch, capsys):
    from scripts import refresh_business_stocks

    monkeypatch.setattr(refresh_business_stocks.storage, "initialize_storage", lambda: None)
    monkeypatch.setattr(
        refresh_business_stocks.stock_resolver,
        "refresh_all_symbols_from_tushare",
        lambda: {"a_share": {"error": "a failed"}, "hk": {"error": "hk failed"}, "us": {"error": "us failed"}},
    )

    assert refresh_business_stocks.main(["--source", "all", "--json"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["source"] == "all"
    assert payload["success"] is False
    assert payload["count"] == 0
    assert "a_share: a failed" in payload["error"]
    assert "hk: hk failed" in payload["error"]
    assert "us: us failed" in payload["error"]


def test_refresh_business_stocks_script_reports_single_source_exceptions(business_env, monkeypatch, capsys):
    from scripts import refresh_business_stocks

    monkeypatch.setattr(refresh_business_stocks.storage, "initialize_storage", lambda: None)
    monkeypatch.setattr(
        refresh_business_stocks.stock_resolver,
        "refresh_hk_symbols_from_tushare",
        lambda: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
    )

    assert refresh_business_stocks.main(["--source", "hk", "--json"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["source"] == "hk"
    assert payload["success"] is False
    assert payload["count"] == 0
    assert payload["error"] == "provider unavailable"


def test_refresh_business_stocks_script_runs_by_file_path():
    repo_root = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [sys.executable, "scripts/refresh_business_stocks.py", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--source" in result.stdout


def test_tushare_token_config_permission_is_sensitive(business_env):
    from business.config.config_service import can_modify_config, save_config

    assert can_modify_config("tushare.token", "uploader") is False
    assert can_modify_config("tushare.token", "operator") is False
    assert can_modify_config("tushare.token", "technical_admin") is False
    assert can_modify_config("tushare.token", "technical_operator") is True

    with pytest.raises(PermissionError):
        save_config("tushare.token", "blocked-token", operator_role="operator")


def test_technical_analysis_skill_env_uses_shared_tushare_token_reader(tmp_path, monkeypatch):
    from business.content import technical_analysis as technical_analysis
    output_dir = tmp_path / "ta-output"
    output_dir.mkdir()
    report = output_dir / "300502_技术分析报告_2026-05-25.md"
    chart = output_dir / "300502_TA_2026-05-25.png"
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env_token"] = kwargs["env"].get("TUSHARE_TOKEN")
        report.write_text("ta report", encoding="utf-8")
        chart.write_bytes(b"chart")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(technical_analysis, "get_tushare_token", lambda: "shared-token-1234567890")
    monkeypatch.setattr(technical_analysis.subprocess, "run", fake_run)

    result_report, result_chart = technical_analysis._run_skill("300502", output_dir)

    assert captured["env_token"] == "shared-token-1234567890"
    assert captured["command"][-4:] == ["--symbol", "300502", "--output", str(output_dir)]
    assert result_report == report
    assert result_chart == chart


def test_technical_analysis_sh_suffix_enters_skill_and_failures_return_business_prompts(business_env, tmp_path, monkeypatch):
    from business.content import technical_analysis as technical_analysis
    from business.config.constants import ErrorCode, user_message
    from business.content.technical_analysis import run_technical_analysis

    report = tmp_path / "600519_技术分析报告_2026-05-25.md"
    chart = tmp_path / "600519_TA_2026-05-25.png"
    report.write_text("ta report", encoding="utf-8")
    chart.write_bytes(b"chart")
    calls = []

    def fake_skill(symbol, _output_dir, stock_name=""):
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


def test_router_records_technical_analysis_report_chart_and_card_paths(business_env, tmp_path):
    from business.config.constants import ServiceType
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message
    from business.content.technical_analysis import TechnicalAnalysisResult
    from business.accounts.user_service import create_user

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


def test_router_technical_analysis_reply_exposes_cache_source_for_delivery_queue(business_env, tmp_path):
    from business.config.constants import ServiceType
    from business.routing.router import handle_text_message
    from business.content.technical_analysis import TechnicalAnalysisResult
    from business.accounts.user_service import create_user

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
            cache_key="technical_analysis:300502.SZ:2026-06-05:test",
        ),
    )

    assert reply.success is True
    assert reply.source_type == "cache"
    assert reply.source_id == "technical_analysis:300502.SZ:2026-06-05:test"


def test_router_daily_content_reply_exposes_product_source_for_delivery_queue(business_env, tmp_path):
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, set_content_effective
    from business.routing.router import handle_text_message
    from business.accounts.user_service import create_user

    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])
    image = tmp_path / "rate.png"
    image.write_bytes(b"rate")
    content_id = create_content_draft(ServiceType.RATE, source_text="rate")
    set_content_effective(content_id, str(image), operator="admin")

    reply = handle_text_message("ok", "利率")

    assert reply.success is True
    assert reply.source_type == "product"
    assert reply.source_id.startswith("prod_")
    assert reply.source_id != content_id


def test_daily_content_activation_and_query(business_env, tmp_path):
    from business.config.constants import ErrorCode, ServiceType
    from business.content.daily_content import (
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
    assert Path(latest.output_image).read_bytes() == b"png2"


def test_daily_content_expired_effective_content_is_not_returned(business_env, tmp_path):
    from business.config.constants import ErrorCode, ServiceType
    from business.content.daily_content import create_content_draft, get_latest_effective_content, set_content_effective
    from business.records.records import get_content_record

    expired_img = tmp_path / "expired.png"
    persistent_img = tmp_path / "persistent.png"
    expired_img.write_bytes(b"expired")
    persistent_img.write_bytes(b"persistent")

    expired_id = create_content_draft(ServiceType.RATE, source_text="expired")
    set_content_effective(
        expired_id,
        str(expired_img),
        operator="admin",
        expires_at="2000-01-01T00:00",
    )

    expired = get_latest_effective_content(ServiceType.RATE)
    assert expired.success is False
    assert expired.error_code == ErrorCode.NO_CONTENT
    assert get_content_record(expired_id).expires_at

    persistent_id = create_content_draft(ServiceType.RATE, source_text="persistent", expires_at="")
    set_content_effective(persistent_id, str(persistent_img), operator="admin")

    latest = get_latest_effective_content(ServiceType.RATE)
    assert latest.success is True
    assert latest.content_id == persistent_id
    assert get_content_record(persistent_id).expires_at == ""


def test_daily_content_expiration_persists_invalidated_status(business_env, tmp_path):
    from business.config.constants import ServiceType, Status
    from business.content.daily_content import create_content_draft, mark_expired_daily_contents_invalidated, set_content_effective
    from business.products.product_service import PRODUCT_STATUS_ACTIVE, PRODUCT_STATUS_INVALIDATED, list_products_page
    from business.records.records import get_content_record

    expired_image = tmp_path / "expired.png"
    fresh_image = tmp_path / "fresh.png"
    expired_image.write_bytes(b"expired")
    fresh_image.write_bytes(b"fresh")

    expired_id = create_content_draft(ServiceType.RATE, source_text="expired")
    set_content_effective(
        expired_id,
        str(expired_image),
        operator="ops",
        expires_at="2000-01-01T00:00",
    )
    fresh_id = create_content_draft(ServiceType.CONVERTIBLE_BOND, source_text="fresh")
    set_content_effective(
        fresh_id,
        str(fresh_image),
        operator="ops",
        expires_at="2099-01-01T00:00",
    )

    assert mark_expired_daily_contents_invalidated() == 1

    assert get_content_record(expired_id).status == Status.INVALIDATED
    assert get_content_record(fresh_id).status == Status.EFFECTIVE
    products, total = list_products_page(include_invalidated=True)
    by_content_id = {product["source_content_id"]: product for product in products}
    assert total == 2
    assert by_content_id[expired_id]["status"] == PRODUCT_STATUS_INVALIDATED
    assert by_content_id[fresh_id]["status"] == PRODUCT_STATUS_ACTIVE


def test_backfill_products_from_product_cache_sources_is_idempotent(business_env, tmp_path):
    from business.cache.cache_service import build_cache_key, write_cache_entry
    from business.config.constants import ServiceType
    from business.products.product_service import backfill_products_from_legacy_sources, list_products_page

    card = tmp_path / "legacy-card.png"
    report = tmp_path / "legacy-report.md"
    card.write_text("card", encoding="utf-8")
    report.write_text("report", encoding="utf-8")
    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-06-20", "v1")
    write_cache_entry(
        cache_key=cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-06-20",
        version_fingerprint="v1",
        output_files=[str(card), str(report)],
        artifact_owner_id="req-legacy-cache",
    )

    first = backfill_products_from_legacy_sources()
    second = backfill_products_from_legacy_sources()

    rows, total = list_products_page(include_invalidated=True, business_type=str(ServiceType.TECHNICAL_ANALYSIS))
    assert first["cache_created"] == 0
    assert second["cache_created"] == 0
    assert total == 1
    assert rows[0]["source_type"] == "cache"
    assert rows[0]["source_cache_key"] == cache_key
    assert rows[0]["output_files"] == [str(card), str(report)]


def test_product_source_fields_support_request_content_and_legacy_cache_sources(business_env, tmp_path):
    from business.products.product_service import create_product, list_products_page

    output = tmp_path / "source-fields.png"
    output.write_text("source", encoding="utf-8")
    create_product(
        business_type="component:testcomponent",
        target_key="testcomponent",
        target_label="testcomponent",
        business_date="2026-06-25",
        version_fingerprint="vf-source-fields-request",
        status="active",
        source_type="request",
        source_request_id="req-source-fields",
        output_files=[str(output)],
    )
    create_product(
        business_type="rate",
        target_key="利率内容",
        target_label="利率内容",
        business_date="2026-06-25",
        version_fingerprint="vf-source-fields-content",
        status="active",
        source_type="content",
        source_content_id="content-source-fields",
        output_files=[str(output)],
    )
    create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="300502.SZ",
        business_date="2026-06-25",
        version_fingerprint="vf-source-fields-cache",
        status="active",
        source_type="cache",
        source_cache_key="cache-source-fields",
        output_files=[str(output)],
    )

    products, total = list_products_page(include_invalidated=True)

    assert total == 3
    assert {item["source_type"] for item in products} == {"request", "content", "cache"}
    assert any(item["source_request_id"] == "req-source-fields" for item in products)
    assert any(item["source_content_id"] == "content-source-fields" for item in products)
    assert any(item["source_cache_key"] == "cache-source-fields" for item in products)


def test_backfill_products_from_success_request_records_creates_component_products(business_env, tmp_path):
    from business.config.constants import ServiceType
    from business.products.product_service import backfill_products_from_legacy_sources, list_products_page
    from business.records.business_records import create_business_record, mark_business_success

    output = tmp_path / "component-output.png"
    output.write_bytes(b"component")
    request_id = create_business_record(
        "openid",
        "testcomponent",
        ServiceType.UNMATCHED,
        module_key="testcomponent",
    )
    mark_business_success(
        request_id,
        output_files=[str(output)],
        elapsed_ms=10,
        storage_namespace="components/testcomponent",
    )

    first = backfill_products_from_legacy_sources()
    second = backfill_products_from_legacy_sources()

    rows, total = list_products_page(include_invalidated=True, business_type="component:testcomponent")
    assert first["request_created"] == 1
    assert second["request_created"] == 0
    assert total == 1
    assert rows[0]["source_type"] == "request"
    assert rows[0]["source_request_id"] == request_id
    assert rows[0]["target_key"] == "testcomponent"
    assert rows[0]["output_files"]
    assert all(Path(path).is_file() for path in rows[0]["output_files"])


def test_backfill_products_from_request_records_skips_effective_content_delivery_records(business_env, tmp_path):
    from sqlalchemy import update

    from business.accounts.user_service import create_user
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, set_content_effective
    from business.products.product_service import backfill_products_from_legacy_sources, list_products_page
    from business.routing.router import handle_text_message
    from business.schema.db import connect
    from business.schema.tables import investment_request_records

    create_user("openid", enabled=True, allowed_services=[ServiceType.ALL])
    image = tmp_path / "rate.png"
    image.write_bytes(b"rate")
    content_id = create_content_draft(ServiceType.RATE, source_text="rate")
    set_content_effective(content_id, str(image), operator="admin")

    reply = handle_text_message("openid", "利率")
    assert reply.success is True
    with connect() as conn:
        conn.execute(
            update(investment_request_records)
            .where(investment_request_records.c.request_id == reply.request_id)
            .values(action_type="")
        )

    result = backfill_products_from_legacy_sources()

    rows, total = list_products_page(include_invalidated=True, business_type=str(ServiceType.RATE))
    assert result["request_created"] == 0
    assert total == 1
    assert rows[0]["source_type"] == "content"
    assert rows[0]["source_content_id"] == content_id


def test_backfill_products_from_legacy_daily_content_preserves_status_and_text(business_env, tmp_path):
    from sqlalchemy import update

    from business.config.constants import ServiceType, Status
    from business.content.daily_content import create_content_draft
    from business.products.product_service import backfill_products_from_legacy_sources, list_products_page
    from business.schema.db import connect
    from business.schema.tables import investment_daily_contents

    image = tmp_path / "rate.png"
    image.write_text("rate image", encoding="utf-8")
    content_id = create_content_draft(
        ServiceType.RATE,
        source_text="公开市场操作",
        effective_date="2026-06-20",
        operator="ops",
    )
    with connect() as conn:
        conn.execute(
            update(investment_daily_contents)
            .where(investment_daily_contents.c.content_id == content_id)
            .values(
                status=str(Status.EFFECTIVE),
                generated_text="生成后的利率内容",
                output_image=str(image),
                effective_at="2026-06-20T09:30:00+00:00",
            )
        )

    result = backfill_products_from_legacy_sources()

    rows, total = list_products_page(include_invalidated=True, business_type=str(ServiceType.RATE))
    assert result["content_created"] == 1
    assert total == 1
    assert rows[0]["source_type"] == "content"
    assert rows[0]["source_content_id"] == content_id
    assert rows[0]["business_date"] == "2026-06-20"
    assert rows[0]["effective_at"] == "2026-06-20T09:30:00+00:00"
    assert rows[0]["text_content"] == "生成后的利率内容"
    assert rows[0]["output_files"] == [str(image)]
    assert rows[0]["status"] == "active"


def test_backfill_products_from_legacy_daily_content_skips_unproduced_rows_and_maps_statuses(business_env, tmp_path):
    from sqlalchemy import update

    from business.config.constants import ServiceType, Status
    from business.content.daily_content import create_content_draft
    from business.products.product_service import (
        PRODUCT_STATUS_ARCHIVED,
        PRODUCT_STATUS_FAILED,
        PRODUCT_STATUS_INVALIDATED,
        backfill_products_from_legacy_sources,
        list_products_page,
    )
    from business.schema.db import connect
    from business.schema.tables import investment_daily_contents

    archived_image = tmp_path / "archived-rate.png"
    failed_image = tmp_path / "failed-rate.png"
    invalidated_image = tmp_path / "invalidated-rate.png"
    archived_image.write_text("archived image", encoding="utf-8")
    failed_image.write_text("failed image", encoding="utf-8")
    invalidated_image.write_text("invalidated image", encoding="utf-8")

    draft_id = create_content_draft(ServiceType.RATE, source_text="draft", effective_date="2026-06-21")
    generating_id = create_content_draft(ServiceType.RATE, source_text="generating", effective_date="2026-06-22")
    empty_failed_id = create_content_draft(ServiceType.RATE, source_text="failed empty", effective_date="2026-06-23")
    archived_id = create_content_draft(ServiceType.RATE, source_text="archived", effective_date="2026-06-24")
    failed_id = create_content_draft(ServiceType.RATE, source_text="failed output", effective_date="2026-06-25")
    invalidated_id = create_content_draft(ServiceType.RATE, source_text="invalidated output", effective_date="2026-06-26")

    with connect() as conn:
        conn.execute(
            update(investment_daily_contents)
            .where(investment_daily_contents.c.content_id == generating_id)
            .values(status=str(Status.GENERATING))
        )
        conn.execute(
            update(investment_daily_contents)
            .where(investment_daily_contents.c.content_id == empty_failed_id)
            .values(status=str(Status.GENERATE_FAILED))
        )
        conn.execute(
            update(investment_daily_contents)
            .where(investment_daily_contents.c.content_id == archived_id)
            .values(
                status=str(Status.ARCHIVED),
                generated_text="历史归档内容",
                output_image=str(archived_image),
                effective_at="2026-06-24T08:00:00+00:00",
            )
        )
        conn.execute(
            update(investment_daily_contents)
            .where(investment_daily_contents.c.content_id == failed_id)
            .values(
                status=str(Status.GENERATE_FAILED),
                generated_text="失败但已有输出",
                output_image=str(failed_image),
            )
        )
        conn.execute(
            update(investment_daily_contents)
            .where(investment_daily_contents.c.content_id == invalidated_id)
            .values(
                status=str(Status.INVALIDATED),
                generated_text="已失效历史内容",
                output_image=str(invalidated_image),
            )
        )

    result = backfill_products_from_legacy_sources()

    rows, total = list_products_page(include_invalidated=True, business_type=str(ServiceType.RATE))
    by_content_id = {row["source_content_id"]: row for row in rows}
    assert result["content_created"] == 3
    assert total == 3
    assert draft_id not in by_content_id
    assert generating_id not in by_content_id
    assert empty_failed_id not in by_content_id
    assert by_content_id[archived_id]["status"] == PRODUCT_STATUS_ARCHIVED
    assert by_content_id[archived_id]["effective_at"] == "2026-06-24T08:00:00+00:00"
    assert by_content_id[failed_id]["status"] == PRODUCT_STATUS_FAILED
    assert by_content_id[failed_id]["text_content"] == "失败但已有输出"
    assert by_content_id[invalidated_id]["status"] == PRODUCT_STATUS_INVALIDATED


def test_daily_content_publish_creates_active_product_and_archives_previous_product(business_env, tmp_path):
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, set_content_effective
    from business.products.product_service import (
        PRODUCT_STATUS_ACTIVE,
        PRODUCT_STATUS_ARCHIVED,
        list_products_page,
    )

    first_image = tmp_path / "first-rate.png"
    second_image = tmp_path / "second-rate.png"
    first_image.write_bytes(b"first")
    second_image.write_bytes(b"second")

    first_id = create_content_draft(ServiceType.RATE, source_text="first")
    second_id = create_content_draft(ServiceType.RATE, source_text="second")

    set_content_effective(first_id, str(first_image), effective_date="2026-06-24", operator="ops")
    set_content_effective(second_id, str(second_image), effective_date="2026-06-24", operator="ops")

    products, total = list_products_page(include_invalidated=True, business_type=str(ServiceType.RATE))
    by_content_id = {product["source_content_id"]: product for product in products}

    assert total == 2
    assert by_content_id[first_id]["status"] == PRODUCT_STATUS_ARCHIVED
    assert by_content_id[second_id]["status"] == PRODUCT_STATUS_ACTIVE
    assert by_content_id[second_id]["business_date"] == "2026-06-24"
    assert by_content_id[first_id]["version_fingerprint"] == "v1"
    assert by_content_id[second_id]["version_fingerprint"] == "v2"
    assert by_content_id[second_id]["output_files"]


def test_daily_content_regenerate_invalidates_existing_product(business_env, tmp_path):
    from business.config.constants import ServiceType, Status
    from business.content.daily_content import create_content_draft, regenerate_content, set_content_effective
    from business.products.product_service import PRODUCT_STATUS_INVALIDATED, list_products_page
    from business.records.records import get_content_record

    first_image = tmp_path / "published-rate.png"
    second_image = tmp_path / "regenerated-rate.png"
    first_image.write_bytes(b"published")
    second_image.write_bytes(b"regenerated")

    content_id = create_content_draft(ServiceType.RATE, source_text="rate")
    set_content_effective(content_id, str(first_image), effective_date="2026-06-24", operator="ops")

    def fake_ai(service_type, source_text):
        return SimpleNamespace(success=True, text=f"regenerated text: {source_text}", prompt="")

    def fake_renderer(service_type, generated_text):
        second_image.write_bytes(generated_text.encode("utf-8"))
        return SimpleNamespace(success=True, image_path=str(second_image))

    result = regenerate_content(content_id, ai_generator=fake_ai, renderer=fake_renderer)

    content = get_content_record(content_id)
    products, total = list_products_page(include_invalidated=True, business_type=str(ServiceType.RATE))

    assert result.success is True
    assert content.status == Status.GENERATED
    assert total == 1
    assert products[0]["source_content_id"] == content_id
    assert products[0]["status"] == PRODUCT_STATUS_INVALIDATED


def test_daily_content_update_expiry_syncs_product_and_invalidates_past_expiry(business_env, tmp_path):
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, set_content_effective, update_content_expires_at
    from business.products.product_service import PRODUCT_STATUS_ACTIVE, PRODUCT_STATUS_INVALIDATED, list_products_page

    image = tmp_path / "rate.png"
    image.write_bytes(b"rate")

    content_id = create_content_draft(ServiceType.RATE, source_text="rate")
    set_content_effective(content_id, str(image), effective_date="2026-06-24", operator="ops")

    update_content_expires_at(content_id, "2099-01-01T00:00", operator="ops")
    products, total = list_products_page(include_invalidated=True, business_type=str(ServiceType.RATE))
    assert total == 1
    assert products[0]["status"] == PRODUCT_STATUS_ACTIVE
    assert products[0]["expires_at"] == "2098-12-31T16:00:00+00:00"

    update_content_expires_at(content_id, "2000-01-01T00:00", operator="ops")
    products, total = list_products_page(include_invalidated=True, business_type=str(ServiceType.RATE))
    assert total == 1
    assert products[0]["status"] == PRODUCT_STATUS_INVALIDATED
    assert products[0]["expires_at"] == "1999-12-31T16:00:00+00:00"


def test_daily_content_republishing_historical_expired_record_clears_stale_expiry(business_env, tmp_path):
    from business.config.constants import ServiceType, Status
    from business.content.daily_content import create_content_draft, get_latest_effective_content, set_content_effective
    from business.records.records import get_content_record

    current_image = tmp_path / "current.png"
    historical_image = tmp_path / "historical.png"
    current_image.write_bytes(b"current")
    historical_image.write_bytes(b"historical")

    current_id = create_content_draft(ServiceType.RATE, source_text="current")
    set_content_effective(current_id, str(current_image), effective_date="2026-06-10", operator="ops")

    historical_id = create_content_draft(
        ServiceType.RATE,
        source_text="historical",
        effective_date="2026-06-09",
        expires_at="2000-01-01T00:00",
    )
    set_content_effective(historical_id, str(historical_image), effective_date="2026-06-10", operator="ops")

    historical = get_content_record(historical_id)
    current = get_content_record(current_id)
    assert historical.status == Status.EFFECTIVE
    assert historical.effective_date == "2026-06-10"
    assert historical.expires_at == ""
    assert current.status == Status.ARCHIVED
    assert get_latest_effective_content(ServiceType.RATE).content_id == historical_id


def test_daily_content_manual_invalidate_and_expiry_update(business_env, tmp_path):
    from business.audit.audit_service import list_operation_audits
    from business.config.constants import ErrorCode, ServiceType, Status
    from business.content.daily_content import (
        create_content_draft,
        get_latest_effective_content,
        invalidate_content,
        set_content_effective,
        update_content_expires_at,
    )
    from business.products.product_service import PRODUCT_STATUS_INVALIDATED, list_products_page
    from business.records.records import get_content_record

    image = tmp_path / "current.png"
    image.write_bytes(b"current")
    content_id = create_content_draft(ServiceType.RATE, source_text="manual")
    set_content_effective(content_id, str(image), operator="publisher")

    update_content_expires_at(content_id, "2099-01-01T00:00", operator="ops")
    updated = get_content_record(content_id)
    assert updated.status == Status.EFFECTIVE
    assert updated.expires_at == "2098-12-31T16:00:00.000000+00:00"

    update_content_expires_at(content_id, "", operator="ops")
    assert get_content_record(content_id).expires_at == ""

    assert invalidate_content(content_id, operator="ops") is True
    invalidated = get_content_record(content_id)
    assert invalidated.status == Status.INVALIDATED
    assert invalidated.archived_at
    products, total = list_products_page(include_invalidated=True)
    assert total == 1
    assert products[0]["source_content_id"] == content_id
    assert products[0]["status"] == PRODUCT_STATUS_INVALIDATED
    latest = get_latest_effective_content(ServiceType.RATE)
    assert latest.success is False
    assert latest.error_code == ErrorCode.NO_CONTENT

    actions = [audit.action for audit in list_operation_audits(limit=10, target_id=content_id)]
    assert "content.update_expiry" in actions
    assert "content.invalidate" in actions


def test_daily_content_auto_effective_after_generate_publishes_on_backend(business_env, tmp_path):
    from business.config.constants import ServiceType, Status
    from business.content.daily_content import create_content_draft, generate_content
    from business.records.records import get_content_record

    output = tmp_path / "auto-effective.png"

    def fake_ai(service_type, source_text):
        assert service_type == ServiceType.RATE
        return SimpleNamespace(success=True, text=f"generated: {source_text}")

    def fake_renderer(service_type, generated_text):
        output.write_bytes(generated_text.encode("utf-8"))
        return SimpleNamespace(success=True, image_path=str(output))

    content_id = create_content_draft(
        ServiceType.RATE,
        source_text="auto source",
        expires_at="",
        auto_effective_after_generate=True,
    )

    result = generate_content(content_id, ai_generator=fake_ai, renderer=fake_renderer)

    assert result.success is True
    record = get_content_record(content_id)
    assert record.status == Status.EFFECTIVE
    assert record.effective_at
    assert record.output_image
    assert record.auto_effective_after_generate is True


def test_daily_content_keeps_only_one_effective_version_per_service(business_env, tmp_path):
    from datetime import date, timedelta

    from business.config.constants import ServiceType, Status
    from business.content.daily_content import (
        create_content_draft,
        get_latest_effective_content,
        set_content_effective,
    )
    from business.records.records import get_content_record

    today = date.today()
    yesterday = (today - timedelta(days=1)).isoformat()
    tomorrow = (today + timedelta(days=1)).isoformat()

    yesterday_first_img = tmp_path / "yesterday-first.png"
    yesterday_second_img = tmp_path / "yesterday-second.png"
    tomorrow_img = tmp_path / "tomorrow.png"
    for path in (yesterday_first_img, yesterday_second_img, tomorrow_img):
        path.write_bytes(b"png")

    yesterday_first = create_content_draft(ServiceType.RATE, source_text="old")
    tomorrow_content = create_content_draft(ServiceType.RATE, source_text="future")
    yesterday_second = create_content_draft(ServiceType.RATE, source_text="replacement")

    set_content_effective(yesterday_first, str(yesterday_first_img), effective_date=yesterday, operator="operator-a")
    set_content_effective(tomorrow_content, str(tomorrow_img), effective_date=tomorrow, operator="operator-b")
    set_content_effective(yesterday_second, str(yesterday_second_img), effective_date=yesterday, operator="operator-c")

    assert get_content_record(yesterday_first).status == Status.ARCHIVED
    assert get_content_record(yesterday_first).archived_at
    assert get_content_record(yesterday_second).status == Status.EFFECTIVE
    assert get_content_record(yesterday_second).effective_date == yesterday
    assert get_content_record(tomorrow_content).status == Status.ARCHIVED
    assert get_latest_effective_content(ServiceType.RATE).content_id == yesterday_second


def test_daily_content_operation_audits_track_create_generate_effective_and_archive(business_env, tmp_path):
    from business.audit.audit_service import list_operation_audits
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, generate_content, set_content_effective

    first = create_content_draft(ServiceType.RATE, source_text="first", operator="operator-a")
    second = create_content_draft(ServiceType.RATE, source_text="second", operator="operator-b")
    generate_content(
        first,
        ai_generator=lambda _service_type, _source_text: SimpleNamespace(success=True, text="first text"),
        renderer=lambda _service_type, _text: SimpleNamespace(success=True, image_path=str(tmp_path / "first.png")),
    )
    set_content_effective(first, operator="operator-a")
    set_content_effective(second, str(tmp_path / "second.png"), operator="operator-b")

    audits = list_operation_audits(limit=20)
    actions = [audit.action for audit in audits]

    assert "content.create" in actions
    assert "content.generate" in actions
    assert "content.publish" in actions
    assert "content.archive" in actions
    effective = next(audit for audit in audits if audit.action == "content.publish" and audit.target_id == second)
    assert effective.operator == "operator-b"
    assert effective.target_type == "daily_content"
    assert effective.operation_category == "content"
    assert effective.detail["service_type"] == ServiceType.RATE


def test_daily_content_create_upload_generate_and_failure_records(business_env):
    from business.config.constants import ErrorCode, ServiceType, Status
    from business.content.daily_content import (
        create_convertible_bond_content_draft,
        create_rate_content_draft,
        generate_content,
        update_content_source,
    )
    from business.records.records import get_content_record

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


def test_daily_content_default_generation_passes_uploaded_source_files(business_env, tmp_path, monkeypatch):
    from business.config.constants import ServiceType
    from business.content.daily_content import create_rate_content_draft, generate_content

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
        "business.audit.ai_generation.generate_standard_text",
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


def test_daily_content_default_image_generation_renders_png_with_fake_model(business_env, tmp_path, monkeypatch):
    from business.config import config_service as config_service
    from business.config.config_service import save_configs
    from business.config.constants import ServiceType
    from business.content.daily_content import create_rate_content_draft, generate_content
    from business.records.records import get_content_record
    from business.schema.storage import get_storage_dirs

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
    standard_text = Path("builtin/components/signal-card-renderer/examples/bond_sample.txt").read_text(encoding="utf-8")

    class FakeBot:
        def __init__(self):
            self.calls = []

        def call_with_tools(self, **kwargs):
            self.calls.append(kwargs)
            user_content = kwargs["messages"][1]["content"]
            if len(self.calls) == 1:
                assert any(block.get("type") == "image_url" for block in user_content)
                return {"choices": [{"message": {"content": "OCR: 2026-05-25 108.970 入场（3/8）"}}]}
            assert "必须只输出卡片正文" in kwargs["messages"][0]["content"]
            assert "OCR: 2026-05-25 108.970 入场（3/8）" in user_content
            return {"choices": [{"message": {"content": standard_text}}]}

    fake_bot = FakeBot()

    class FakeBridge:
        def get_bot(self, typename):
            assert typename == "chat"
            return fake_bot

    monkeypatch.setattr("business.audit.ai_generation.Bridge", lambda: FakeBridge())

    content_id = create_rate_content_draft(
        source_files=[str(source_image)],
        source_text="",
        operator="operator-a",
        effective_date="2026-05-25",
    )
    result = generate_content(content_id)

    assert result.success is True
    assert Path(result.output_image).is_file()
    assert Path(result.output_image).stat().st_size > 0
    assert Path(result.output_image).resolve().is_relative_to(get_storage_dirs()["files"].resolve())
    output_parts = Path(result.output_image).parts
    files_index = output_parts.index("files")
    assert output_parts[files_index + 1 : files_index + 5] == (
        str(ServiceType.RATE),
        "2026-05-25",
        "content",
        content_id,
    )
    assert Path(result.output_image).name.startswith("output_image_rate_2026-05-25_v1_")
    assert Path(result.output_image).name.endswith(".png")
    assert result.output_image != str(output_dir / f"{ServiceType.RATE}_card.png")
    assert get_content_record(content_id).output_image == result.output_image
    assert fake_bot.calls


def test_daily_content_records_filter_by_service_type_for_console_pages(business_env):
    from business.config.constants import ServiceType
    from business.content.daily_content import create_convertible_bond_content_draft, create_rate_content_draft
    from business.records.records import list_content_records

    rate_id = create_rate_content_draft(source_text="rate")
    cb_id = create_convertible_bond_content_draft(source_text="cb")

    rate_records = list_content_records(service_type=ServiceType.RATE)
    cb_records = list_content_records(service_type=ServiceType.CONVERTIBLE_BOND)

    assert [record.content_id for record in rate_records] == [rate_id]
    assert [record.content_id for record in cb_records] == [cb_id]


def test_daily_content_upload_saves_files_under_business_files_dir(business_env):
    from business.config.constants import ServiceType
    from business.content.daily_content import save_source_file

    saved = save_source_file(ServiceType.RATE, "rates.xlsx", b"rate-data", owner_id="content-123", effective_date="2026-06-07")

    assert Path(saved).read_bytes() == b"rate-data"
    assert business_env / "storage" / "files" in Path(saved).parents
    path_parts = Path(saved).parts
    files_index = path_parts.index("files")
    assert path_parts[files_index + 1 : files_index + 5] == (
        str(ServiceType.RATE),
        "2026-06-07",
        "content",
        "content-123",
    )
    assert "source_image" in Path(saved).parts
    assert "content-123" in Path(saved).parts

    with pytest.raises(ValueError):
        save_source_file(ServiceType.RATE, "../escape.txt", b"bad")


def test_daily_content_api_accepts_module_key_for_content_modules(business_env, tmp_path, monkeypatch):
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, set_content_effective
    from business.records.records import get_content_record
    from channel.web.web_channel import InvestmentDailyContentHandler

    image = tmp_path / "rate-current.png"
    image.write_bytes(b"png")
    content_id = create_content_draft(ServiceType.RATE, source_text="rate", operator="pytest", module_key="rate")
    set_content_effective(content_id, str(image), operator="pytest")

    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentDailyContentHandler().GET,
        params={"module_key": "rate", "limit": "20"},
    )

    assert payload["status"] == "success"
    assert payload["current_effective"]["content_id"] == content_id
    assert payload["current_effective"]["module_key"] == "rate"
    assert payload["current_effective"]["module_label"]
    assert payload["contents"][0]["module_key"] == "rate"
    assert payload["contents"][0]["module_label"]
    assert get_content_record(content_id).module_key == "rate"


def test_custom_daily_content_module_uses_module_key_to_isolate_unmatched_content(business_env, tmp_path):
    from business.components.paths import runtime_component_root
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, get_latest_effective_content, set_content_effective
    from business.records.records import get_content_record

    for module_key, label in (("module-a", "Module A"), ("module-b", "Module B")):
        component_dir = runtime_component_root(module_key)
        component_dir.mkdir(parents=True, exist_ok=True)
        (component_dir / "component.json").write_text(
            json.dumps(
                {
                    "component_key": module_key,
                    "label": label,
                    "description": label,
                    "service_type": "unmatched",
                    "handler_type": "daily_content",
                    "component_type": "active_prompt",
                    "content_enabled": True,
                    "routable": True,
                    "default_triggers": [label],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    module_a_image = tmp_path / "module-a.png"
    module_b_image = tmp_path / "module-b.png"
    module_a_image.write_bytes(b"a")
    module_b_image.write_bytes(b"b")

    module_a_id = create_content_draft(
        ServiceType.UNMATCHED,
        module_key="module-a",
        source_text="module A content",
        effective_date="2026-06-16",
    )
    module_b_id = create_content_draft(
        ServiceType.UNMATCHED,
        module_key="module-b",
        source_text="module B content",
        effective_date="2026-06-16",
    )

    set_content_effective(module_a_id, str(module_a_image), operator="pytest")
    set_content_effective(module_b_id, str(module_b_image), operator="pytest")

    module_a = get_latest_effective_content(ServiceType.UNMATCHED, module_key="module-a")
    module_b = get_latest_effective_content(ServiceType.UNMATCHED, module_key="module-b")

    assert module_a.success is True
    assert module_a.content_id == module_a_id
    assert module_b.success is True
    assert module_b.content_id == module_b_id
    assert get_content_record(module_a_id).module_key == "module-a"
    assert get_content_record(module_b_id).module_key == "module-b"


def test_web_daily_content_multipart_upload_uses_content_scoped_files_dir(business_env, monkeypatch):
    import io

    from business.records.records import get_content_record, list_output_files
    from business.schema.storage import get_storage_dirs
    from channel.web import web_channel
    from channel.web.web_channel import InvestmentDailyContentHandler

    _login_default_investment_admin(monkeypatch)
    upload = SimpleNamespace(filename="rates.png", file=io.BytesIO(b"rate-image"))
    monkeypatch.setattr(web_channel, "_investment_is_multipart_request", lambda: True)
    monkeypatch.setattr(
        web_channel,
        "_raw_web_input",
        lambda: {
            "service_type": "rate",
            "source_text": "rate source",
            "files": [upload],
            "effective_date": "2026-06-07",
        },
    )

    payload = json.loads(InvestmentDailyContentHandler().POST())

    assert payload["status"] == "success"
    content_id = payload["content_id"]
    record = get_content_record(content_id)
    assert len(record.source_files) == 1
    source_path = Path(record.source_files[0])
    assert source_path.read_bytes() == b"rate-image"
    assert source_path.resolve().is_relative_to(get_storage_dirs()["files"].resolve())
    source_parts = source_path.parts
    files_index = source_parts.index("files")
    assert source_parts[files_index + 1 : files_index + 6] == (
        "rate",
        "2026-06-07",
        "content",
        content_id,
        "source_image",
    )
    source_artifacts = [item for item in list_output_files(content_id) if item["artifact_role"] == "source_image"]
    assert len(source_artifacts) == 1
    assert source_artifacts[0]["file_path"] == str(source_path)
    assert source_artifacts[0]["file_url"].startswith("/api/file?id=")


def test_daily_content_regenerate_updates_output_and_only_latest_is_effective(business_env, tmp_path):
    from business.config.constants import ServiceType, Status
    from business.content.daily_content import (
        create_rate_content_draft,
        generate_content,
        get_latest_effective_content,
        regenerate_content,
        set_content_effective,
    )
    from business.records.records import get_content_record

    first_id = create_rate_content_draft(source_text="first")
    second_id = create_rate_content_draft(source_text="second")
    first_image = tmp_path / "first.png"
    second_image = tmp_path / "second.png"
    regenerated_image = tmp_path / "second-v2.png"
    first_image.write_bytes(b"first")
    second_image.write_bytes(b"second")
    regenerated_image.write_bytes(b"second-v2")

    generate_content(
        first_id,
        ai_generator=lambda _service_type, _source_text: SimpleNamespace(success=True, text="first text"),
        renderer=lambda _service_type, _text: SimpleNamespace(success=True, image_path=str(first_image)),
    )
    generate_content(
        second_id,
        ai_generator=lambda _service_type, _source_text: SimpleNamespace(success=True, text="second text"),
        renderer=lambda _service_type, _text: SimpleNamespace(success=True, image_path=str(second_image)),
    )
    set_content_effective(first_id, operator="operator-a")
    set_content_effective(second_id, operator="operator-b")

    assert get_content_record(first_id).status == Status.ARCHIVED
    second_record = get_content_record(second_id)
    assert second_record.status == Status.EFFECTIVE
    assert second_record.output_image != str(second_image)
    assert Path(second_record.output_image).read_bytes() == b"second"
    assert get_latest_effective_content(ServiceType.RATE).output_image == second_record.output_image

    regenerated = regenerate_content(
        second_id,
        ai_generator=lambda _service_type, _source_text: SimpleNamespace(success=True, text="second text regenerated"),
        renderer=lambda _service_type, _text: SimpleNamespace(success=True, image_path=str(regenerated_image)),
    )

    assert regenerated.success is True
    assert regenerated.generated_text == "second text regenerated"
    assert regenerated.output_image != str(regenerated_image)
    assert Path(regenerated.output_image).read_bytes() == b"second-v2"
    updated_record = get_content_record(second_id)
    assert updated_record.generated_text == "second text regenerated"
    assert updated_record.output_image == regenerated.output_image
    assert updated_record.status == Status.GENERATED


def test_daily_content_convertible_bond_no_effective_content_prompt(business_env):
    from business.config.constants import ErrorCode, ServiceType
    from business.content.daily_content import get_latest_effective_content

    empty = get_latest_effective_content(ServiceType.CONVERTIBLE_BOND)
    assert empty.success is False
    assert empty.error_code == ErrorCode.NO_CONTENT
    assert empty.user_prompt == "今日内容尚未更新，请稍后再试。"


@pytest.mark.parametrize("service_type", ["rate", "convertible_bond"])
def test_daily_content_effective_content_image_missing_returns_no_content(business_env, tmp_path, service_type):
    from business.config.constants import ErrorCode, ServiceType
    from business.content.daily_content import create_content_draft, get_latest_effective_content, set_content_effective

    service = ServiceType(service_type)
    missing_image = tmp_path / f"missing-{service_type}.png"
    content_id = create_content_draft(service, source_text="content")
    set_content_effective(content_id, str(missing_image), operator="admin")

    result = get_latest_effective_content(service)

    assert result.success is False
    assert result.error_code == ErrorCode.NO_CONTENT
    assert result.user_prompt == "今日内容尚未更新，请稍后再试。"
    assert "effective content image missing" in result.detail
    assert str(missing_image) in result.detail


def test_render_service_validates_output_files(business_env, tmp_path):
    from business.config.constants import ErrorCode, ServiceType
    from business.content.render_service import RenderRequest, render_card

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


def test_render_service_contract_uses_skill_templates_and_configured_output_dir(business_env, tmp_path):
    from business.config.config_service import save_configs
    from business.config.constants import ServiceType, Status
    from business.content.render_service import DEFAULT_TEMPLATE_CB_PATH, RenderRequest, render_card

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
            DEFAULT_TEMPLATE_CB_PATH,
            result.output_path,
        )
    ]


def test_render_health_check_reports_renderer_template_and_chromium_details(business_env, tmp_path, monkeypatch):
    from business.health import health as health
    from business.config.config_service import save_configs

    missing_renderer = tmp_path / "missing-render-card.py"
    save_configs(
        {
            "render.renderer_path": str(missing_renderer),
            "render.template_ta_path": str(tmp_path / "missing-template-ta.html"),
            "render.template_rate_path": str(tmp_path / "missing-template-bond.html"),
            "render.template_cb_path": str(tmp_path / "missing-template-cb.html"),
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
    assert items["template_ta"].ok is True
    assert items["template_bond"].ok is True
    assert items["template_cb"].ok is True
    assert items["playwright_chromium"].ok is False
    assert "chromium executable missing" in items["playwright_chromium"].detail


def test_health_check_levels_dependencies_and_wechatmp_config(business_env, monkeypatch):
    from business.config import config_service as config_service
    from business.health import health as health
    monkeypatch.setattr(
        config_service,
        "conf",
        lambda: {
            "channel_type": "wechatmp_service",
            "wechatmp_app_id": "",
            "wechatmp_app_secret": "",
            "wechatmp_token": "token-ok",
            "wechatmp_aes_key": "",
        },
    )
    monkeypatch.setattr(
        health,
        "_dependency_available",
        lambda module_name: (module_name in {"pandas", "scipy"}, "" if module_name in {"pandas", "scipy"} else "not installed"),
        raising=False,
    )
    monkeypatch.setattr(health, "_has_chinese_font", lambda: False, raising=False)
    monkeypatch.setattr(
        health,
        "_check_playwright_chromium",
        lambda: health.HealthItem("playwright_chromium", True, "chromium ok", level="ok"),
        raising=False,
    )

    items = {item.name: item for item in health.run_health_checks()}

    assert {item.level for item in items.values()}.issubset({"ok", "warning", "error"})
    assert items["dependency_pandas"].level == "ok"
    assert items["dependency_scipy"].level == "ok"
    assert items["dependency_talib"].level == "error"
    assert items["dependency_akshare"].level == "warning"
    assert items["dependency_tushare"].level == "warning"
    assert items["dependency_baostock"].level == "warning"
    assert items["chinese_font"].level == "warning"
    assert items["wechatmp_channel_enabled"].level == "ok"
    assert items["wechatmp_app_id"].level == "error"
    assert items["wechatmp_app_secret"].level == "error"
    assert items["wechatmp_token"].level == "ok"
    assert items["wechatmp_aes_key"].level == "warning"


def test_health_dependency_import_failure_reports_error_detail(business_env, monkeypatch):
    from business.health import health as health
    def fake_import(module_name):
        if module_name == "talib":
            raise OSError("DLL load failed while importing _ta_lib")
        return object()

    monkeypatch.setattr(health.importlib, "import_module", fake_import)

    item = health._check_dependency("dependency_talib", "talib", required=True)

    assert item.level == "error"
    assert item.ok is False
    assert "talib package import failed" in item.detail
    assert "DLL load failed" in item.detail


def test_run_health_checks_skips_smoke_by_default_and_runs_when_requested(business_env, monkeypatch):
    from business.health import health as health
    calls = []
    monkeypatch.setattr(
        health,
        "_run_technical_analysis_smoke",
        lambda: calls.append("ta") or health.HealthItem("smoke_technical_analysis", True, "ok", level="ok"),
        raising=False,
    )
    monkeypatch.setattr(
        health,
        "_run_renderer_smoke_checks",
        lambda: calls.append("renderer") or [
            health.HealthItem("smoke_renderer_ta", True, "ok", level="ok"),
            health.HealthItem("smoke_renderer_rate", True, "ok", level="ok"),
            health.HealthItem("smoke_renderer_cb", True, "ok", level="ok"),
        ],
        raising=False,
    )

    light_items = {item.name: item for item in health.run_health_checks()}

    assert calls == []
    assert "smoke_technical_analysis" not in light_items
    assert "smoke_renderer_ta" not in light_items

    full_items = {item.name: item for item in health.run_health_checks(run_smoke=True)}

    assert calls == ["ta", "renderer"]
    assert full_items["smoke_technical_analysis"].level == "ok"
    assert full_items["smoke_renderer_ta"].level == "ok"
    assert full_items["smoke_renderer_rate"].level == "ok"
    assert full_items["smoke_renderer_cb"].level == "ok"


def test_health_check_reports_stock_dictionary_and_tushare_token_without_leaking_secret(business_env):
    from business.config.config_service import save_config
    from business.health.health import run_health_checks
    from business.content.stock_resolver import refresh_stock_symbols

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


def test_health_check_reports_missing_and_unwritable_directories(business_env, tmp_path, monkeypatch):
    from business.health import health as health
    from business.config.config_service import save_configs

    missing_files = tmp_path / "missing-files"
    tmp_dir = tmp_path / "tmp"
    tmp_dir.mkdir()
    save_configs(
        {
            "storage.files_dir": str(missing_files),
            "storage.tmp_dir": str(tmp_dir),
        },
        operator_role="admin",
    )

    items = {item.name: item for item in health.run_health_checks()}

    assert items["files_dir"].ok is False
    assert f"directory does not exist: {missing_files}" == items["files_dir"].detail

    def fail_mkstemp(*_args, **_kwargs):
        raise PermissionError("readonly")

    monkeypatch.setattr(health.tempfile, "mkstemp", fail_mkstemp)

    items = {item.name: item for item in health.run_health_checks()}

    assert items["tmp_dir"].ok is False
    assert "directory not writable" in items["tmp_dir"].detail
    assert "readonly" in items["tmp_dir"].detail


def test_health_check_reports_all_dependencies_available(business_env, tmp_path, monkeypatch):
    from business.health import health as health
    from business.config import config_service as config_service
    from business.config.config_service import save_configs
    from business.content.stock_resolver import refresh_stock_symbols

    files = {
        "technical_analysis.skill_path": tmp_path / "analyze_universal.py",
        "render.renderer_path": tmp_path / "render_card.py",
    }
    for path in files.values():
        path.write_text("ok", encoding="utf-8")
    files_dir = tmp_path / "files"
    tmp_dir = tmp_path / "tmp"
    files_dir.mkdir()
    tmp_dir.mkdir()
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
            "storage.files_dir": str(files_dir),
            "storage.tmp_dir": str(tmp_dir),
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


def test_router_handles_rate_success_unauthorized_and_miss(business_env, tmp_path):
    from business.config.constants import ErrorCode
    from business.config.constants import ServiceType
    from business.config.config_service import save_config
    from business.content.daily_content import create_content_draft, set_content_effective
    from business.records.records import get_content_record, list_request_records
    from business.routing.router import DEFAULT_UNMATCHED_PROMPT, handle_text_message, parse_route
    from business.accounts.user_service import create_user

    secret = "sk-secret"
    save_config("tushare.token", secret, operator_role="admin")
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
    effective_record = get_content_record(content_id)
    assert success.success is True
    assert success.output_files == [effective_record.output_image]
    assert "[图片:" in success.reply_text

    denied = handle_text_message("missing", "利率")
    assert denied.success is False
    assert denied.reply_text == "您暂未开通该服务，如需开通请联系服务人员。"

    bypassed = handle_text_message("missing", "利率", skip_permission=True)
    assert bypassed.success is True
    assert bypassed.output_files == [effective_record.output_image]

    missing_image = tmp_path / f"missing-rate-{secret}.png"
    missing_content_id = create_content_draft(ServiceType.RATE, source_text="missing rate")
    set_content_effective(missing_content_id, str(missing_image), operator="admin")

    missing_image_reply = handle_text_message("ok", "利率")
    assert missing_image_reply.success is False
    assert missing_image_reply.reply_text == "今日内容尚未更新，请稍后再试。"
    assert missing_image_reply.output_files == []
    assert str(missing_image) not in missing_image_reply.reply_text
    assert "effective content image missing" in missing_image_reply.detail
    assert secret not in missing_image_reply.detail
    missing_image_record = list_request_records(limit=1)[0]
    assert missing_image_record.service_type == ServiceType.RATE
    assert missing_image_record.raw_input == "利率"
    assert missing_image_record.error_code == ErrorCode.NO_CONTENT
    assert missing_image_record.user_prompt == "今日内容尚未更新，请稍后再试。"
    assert "effective content image missing" in missing_image_record.error_message
    assert secret not in missing_image_record.error_message
    assert missing_image_record.output_files == []

    miss = handle_text_message("ok", "hello")
    assert miss.success is False
    assert miss.handled is True
    assert miss.reply_text == DEFAULT_UNMATCHED_PROMPT
    miss_record = list_request_records(limit=1)[0]
    assert miss_record.service_type == ServiceType.UNMATCHED
    assert miss_record.error_code == ErrorCode.INPUT_ERROR
    assert miss_record.user_prompt == DEFAULT_UNMATCHED_PROMPT


def test_parse_route_uses_configured_business_skill_triggers(business_env):
    from business.config.config_service import save_config
    from business.config.constants import ServiceType
    from business.routing.router import parse_route

    save_config("skill.rate.triggers", ["今日利率"], operator_role="admin", operator="pytest")
    save_config("skill.technical-analysis.triggers", ["走势分析"], operator_role="admin", operator="pytest")

    assert parse_route("利率").matched is False
    assert parse_route("今日利率").service_type == ServiceType.RATE

    route = parse_route("300502.SZ 走势分析")
    assert route.matched is True
    assert route.service_type == ServiceType.TECHNICAL_ANALYSIS
    assert route.target_text == "300502.SZ"


def test_parse_route_rejects_markdown_link_targets(business_env):
    from business.routing.router import parse_route

    route = parse_route("[300502.SZ](http://300502.sz/) 技术分析")

    assert route.matched is False


def test_parse_route_ignores_disabled_business_skill(business_env):
    from business.config.config_service import save_config
    from business.routing.router import parse_route

    save_config("skill.rate.enabled", False, operator_role="admin", operator="pytest")

    assert parse_route("利率").matched is False


def test_parse_route_uses_cowagent_business_registry_not_business_skill_matcher(business_env, monkeypatch):
    from business.config.constants import ServiceType
    from business.routing.router import parse_route
    import business.components.skill_registry as investment_skill_registry

    monkeypatch.setattr(
        investment_skill_registry,
        "match_investment_skill",
        lambda *_args, **_kwargs: pytest.fail("runtime business matching must not use investment skill matcher"),
    )

    assert parse_route("利率").service_type == ServiceType.RATE
    technical = parse_route("300502.SZ 技术分析")
    assert technical.service_type == ServiceType.TECHNICAL_ANALYSIS
    assert technical.target_text == "300502.SZ"


def test_router_can_explicitly_fallback_to_general_agent_for_unmatched_text(business_env):
    from business.config.config_service import save_config
    from business.config.constants import ServiceType
    from business.routing.router import DEFAULT_UNMATCHED_PROMPT, handle_text_message
    from business.accounts.user_service import create_user

    save_config("router.enable_agent_fallback", True, operator_role="admin")
    create_user("ok", enabled=True, allowed_services=[ServiceType.ALL])

    miss = handle_text_message("ok", "hello")

    assert miss.success is False
    assert miss.handled is False
    assert miss.reply_text == DEFAULT_UNMATCHED_PROMPT


def test_router_dispatches_daily_content_by_handler_type(business_env, tmp_path, monkeypatch):
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, set_content_effective
    from business.routing.router import handle_text_message

    image = tmp_path / "rate.png"
    image.write_bytes(b"png")
    content_id = create_content_draft(ServiceType.RATE, source_text="rate source", operator="pytest")
    set_content_effective(content_id, str(image), operator="pytest")

    reply = handle_text_message("openid-rate-generic", "利率", skip_permission=True)

    assert reply.handled is True
    assert reply.success is True
    assert reply.module_key == "rate"
    assert reply.service_type == ServiceType.RATE
    assert len(reply.output_files) == 1
    assert Path(reply.output_files[0]).is_file()
    assert Path(reply.output_files[0]).name.startswith("output_image_rate_")


def test_business_router_sets_module_key_on_reply(monkeypatch):
    from business.config.constants import ServiceType
    from business.routing.router import BusinessReply
    from business.routing.business_router import _reply_from_business

    business_reply = BusinessReply(
        handled=True,
        success=True,
        reply_text="[图片: x.png]",
        output_files=["x.png"],
        service_type=ServiceType.RATE,
        module_key="rate",
        request_id="request-1",
    )

    reply = _reply_from_business(business_reply)

    assert reply.business_module_key == "rate"


def test_prompt_to_image_module_generates_image_from_customer_input(business_env, tmp_path, monkeypatch):
    import json

    from business.components.paths import runtime_component_root
    from business.products.product_service import list_products_page
    from business.records.records import list_request_records
    from business.routing.router import handle_text_message

    component_dir = runtime_component_root("macro-brief")
    component_dir.mkdir(parents=True, exist_ok=True)
    (component_dir / "component.json").write_text(
        json.dumps(
            {
                "component_key": "macro-brief",
                "label": "宏观简报",
                "description": "按客户输入生成宏观简报图。",
                "service_type": "unmatched",
                "match_type": "prefix",
                "default_triggers": ["宏观简报"],
                "handler_type": "prompt_to_image",
                "generation_mode": "on_demand",
                "delivery_mode": "deferred",
                "output_mode": "image",
                "routable": True,
                "component_type": "active_prompt",
                "prompt_key": "prompt.macro_brief",
                "renderer_component_key": "signal-card-renderer",
                "template_key": "rate",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    output = tmp_path / "macro.png"

    def fake_generate_standard_text(service_type, source_text, source_files=None, prompt_key="", module_key="", template_key=""):
        assert "今天流动性偏宽" in source_text
        assert prompt_key == "prompt.macro_brief"
        assert module_key == "macro-brief"
        assert template_key == "rate"
        return type(
            "AIResult",
            (),
            {
                "success": True,
                "text": "标准宏观简报",
                "prompt": "prompt used",
                "detail": "",
                "error_code": None,
            },
        )()

    def fake_render_card(request, renderer=None):
        output.write_bytes(b"png")
        return type(
            "RenderResult",
            (),
            {
                "success": True,
                "image_path": str(output),
                "output_files": [str(output)],
                "detail": "",
                "error_code": None,
                "user_prompt": "",
            },
        )()

    monkeypatch.setattr("business.content.prompt_to_image_handler.generate_standard_text_for_module", fake_generate_standard_text)
    monkeypatch.setattr("business.content.prompt_to_image_handler.render_card", fake_render_card)

    reply = handle_text_message("openid-macro", "宏观简报 今天流动性偏宽", skip_permission=True)

    assert reply.success is True
    assert reply.module_key == "macro-brief"
    assert reply.output_files != [str(output)]
    assert len(reply.output_files) == 1
    assert Path(reply.output_files[0]).is_file()
    record = list_request_records(limit=1)[0]
    assert record.module_key == "macro-brief"
    assert record.output_files == reply.output_files
    products, total = list_products_page(include_invalidated=True, business_type="component:macro-brief")
    assert total == 1
    assert products[0]["source_type"] == "request"
    assert products[0]["source_request_id"] == reply.request_id
    assert products[0]["output_files"] == reply.output_files


def test_request_records_api_returns_module_label_for_custom_prompt_module(business_env, monkeypatch):
    import json

    from business.config.constants import ServiceType
    from business.components.paths import runtime_component_root
    from business.records.records import create_request_record, fail_request_record
    from channel.web import web_channel
    from channel.web.web_channel import InvestmentRequestRecordsHandler

    component_dir = runtime_component_root("macro-brief")
    component_dir.mkdir(parents=True, exist_ok=True)
    (component_dir / "component.json").write_text(
        json.dumps(
            {
                "component_key": "macro-brief",
                "label": "宏观简报",
                "service_type": "unmatched",
                "match_type": "prefix",
                "default_triggers": ["宏观简报"],
                "handler_type": "prompt_to_image",
                "component_type": "active_prompt",
                "prompt_key": "prompt.macro_brief",
                "template_key": "rate",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    request_id = create_request_record(
        "session_d468593",
        "宏观简报 今天重点关注什么",
        ServiceType.UNMATCHED,
        module_key="macro-brief",
    )
    fail_request_record(request_id, "image_generation_failed", "图片生成失败", "render failed", 12)

    _login_default_investment_admin(monkeypatch)
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        web_channel.web,
        "input",
        lambda **kwargs: SimpleNamespace(
            limit="50",
            page="1",
            page_size="",
            service_type="",
            entry_type="",
            status="",
            keyword="",
            customer="",
            start_date="",
            end_date="",
        ),
    )

    payload = json.loads(InvestmentRequestRecordsHandler().GET())

    assert payload["status"] == "success"
    assert payload["records"][0]["module_key"] == "macro-brief"
    assert payload["records"][0]["module_label"] == "宏观简报"


def test_prompt_to_image_default_prompt_matches_rate_template(monkeypatch):
    from business.content.prompt_to_image_handler import _configured_prompt

    monkeypatch.setattr("business.content.prompt_to_image_handler.get_config", lambda key, default=None: default)

    prompt = _configured_prompt("prompt.macro_brief", template_key="rate")

    assert "当日核心信号" in prompt
    assert "周度全景复盘" in prompt
    assert "复合策略信号" in prompt
    assert "只输出" in prompt


def test_business_router_builds_reply_and_allows_unmatched_fallback(business_env, tmp_path):
    from bridge.context import Context, ContextType
    from bridge.reply import ReplyType
    from business.config.config_service import save_config
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, set_content_effective
    from business.accounts.user_service import create_user
    from business.routing.business_router import build_business_reply

    create_user("business-openid", enabled=True, allowed_services=[ServiceType.ALL])
    image = tmp_path / "rate.png"
    image.write_bytes(b"png")
    content_id = create_content_draft(ServiceType.RATE, source_text="rate")
    set_content_effective(content_id, str(image), operator="admin")

    context = Context(ContextType.TEXT, "利率")
    context["session_id"] = "business-openid"

    reply = build_business_reply(context)

    assert reply is not None
    assert reply.type == ReplyType.IMAGE_URL
    assert len(reply.content) == 1
    assert Path(reply.content[0]).is_file()
    assert Path(reply.content[0]).name.startswith("output_image_rate_")
    assert reply.business_service_type == ServiceType.RATE

    save_config("router.enable_agent_fallback", True, operator_role="admin")
    context = Context(ContextType.TEXT, "普通聊天")
    context["session_id"] = "business-openid"

    assert build_business_reply(context) is None


def test_business_router_blocks_unmatched_wechatmp_text_from_ai_fallback(business_env):
    from bridge.context import Context, ContextType
    from bridge.reply import ReplyType
    from business.routing.router import DEFAULT_UNMATCHED_PROMPT
    from business.accounts.user_service import create_user
    from business.config.constants import ServiceType
    from business.routing.business_router import build_business_reply

    create_user("wechatmp-openid", enabled=True, allowed_services=[ServiceType.ALL])
    context = Context(ContextType.TEXT, "普通聊天")
    context["session_id"] = "wechatmp-openid"
    context["channel_type"] = "wechatmp_service"

    reply = build_business_reply(context)

    assert reply is not None
    assert reply.type == ReplyType.TEXT
    assert reply.content == DEFAULT_UNMATCHED_PROMPT


def test_context_kwargs_are_not_shared_between_instances():
    from bridge.context import Context, ContextType

    first = Context(ContextType.TEXT, "first")
    first["channel_type"] = "wechatmp_service"
    second = Context(ContextType.TEXT, "second")

    assert "channel_type" not in second


def test_business_router_ignores_unmatched_text_without_auth_or_handler(business_env, monkeypatch):
    from bridge.context import Context, ContextType
    import business.routing.router as business_route
    import business.routing.business_router as business_router

    monkeypatch.setattr(
        business_route,
        "handle_text_message",
        lambda *_args, **_kwargs: pytest.fail("unmatched text must continue to normal chat"),
    )

    context = Context(ContextType.TEXT, "普通聊天")
    context["session_id"] = "anonymous-user"

    assert business_router.build_business_reply(context) is None


def test_business_router_routes_technical_analysis_without_business_router_handler(business_env, monkeypatch):
    from bridge.context import Context, ContextType
    from bridge.reply import ReplyType
    from business.config.constants import ServiceType
    from business.routing.router import BusinessReply
    from business.accounts.user_service import create_user
    import business.routing.router as business_route
    import business.routing.business_router as business_router
    import business.content.technical_analysis_handler as cowagent_ta_handler

    create_user("openid-ta", enabled=True, allowed_services=[ServiceType.ALL])
    calls = []

    def fake_handler(openid, raw_input, route, **kwargs):
        calls.append((openid, raw_input, route.target_text, kwargs.get("technical_analysis_handler")))
        return BusinessReply(
            True,
            True,
            "[图片: /tmp/signal.png]",
            ["/tmp/signal.png"],
            ServiceType.TECHNICAL_ANALYSIS,
            request_id="ta-request",
        )

    monkeypatch.setattr(cowagent_ta_handler, "handle_technical_analysis", fake_handler)
    context = Context(ContextType.TEXT, "300502.SZ 技术分析")
    context["session_id"] = "openid-ta"

    reply = business_router.build_business_reply(context)

    assert reply is not None
    assert reply.type == ReplyType.IMAGE_URL
    assert reply.content == ["/tmp/signal.png"]
    assert reply.business_service_type == ServiceType.TECHNICAL_ANALYSIS
    assert reply.business_request_id == "ta-request"
    assert calls == [("openid-ta", "300502.SZ 技术分析", "300502.SZ", None)]


def test_business_router_routes_daily_content_through_module_dispatcher(business_env, monkeypatch):
    from bridge.context import Context, ContextType
    from bridge.reply import ReplyType
    from business.config.constants import ServiceType
    from business.routing.router import BusinessReply
    from business.accounts.user_service import create_user
    import business.routing.business_router as business_router
    import business.content.daily_content_handler as cowagent_content_handler

    create_user("openid-rate", enabled=True, allowed_services=[ServiceType.ALL])
    calls = []

    def fake_handler(openid, raw_input, route, **kwargs):
        calls.append((openid, raw_input, route.service_type, bool(kwargs.get("customer_metadata") is not None)))
        return BusinessReply(
            True,
            True,
            "[图片: /tmp/rate.png]",
            ["/tmp/rate.png"],
            ServiceType.RATE,
            request_id="rate-request",
            source_type="content",
            source_id="content-rate",
            module_key="rate",
        )

    monkeypatch.setattr(cowagent_content_handler, "handle_daily_content", fake_handler)
    context = Context(ContextType.TEXT, "利率")
    context["session_id"] = "openid-rate"

    reply = business_router.build_business_reply(context)

    assert reply is not None
    assert reply.type == ReplyType.IMAGE_URL
    assert reply.content == ["/tmp/rate.png"]
    assert reply.business_service_type == ServiceType.RATE
    assert reply.business_request_id == "rate-request"
    assert reply.business_source_type == "content"
    assert reply.business_source_id == "content-rate"
    assert reply.business_module_key == "rate"
    assert calls == [("openid-rate", "利率", ServiceType.RATE, True)]


def test_web_channel_routes_business_commands_from_admin_chat(business_env, tmp_path):
    from bridge.reply import ReplyType
    from business.config.constants import ServiceType
    from business.routing.router import DEFAULT_UNMATCHED_PROMPT
    from business.content.daily_content import create_content_draft, set_content_effective
    from business.accounts.user_service import create_user
    from channel.web.web_channel import WebChannel, _build_investment_web_reply

    create_user("web-session-user", enabled=True, allowed_services=[ServiceType.ALL])
    image = tmp_path / "rate card.png"
    image.write_bytes(b"png")
    content_id = create_content_draft(ServiceType.RATE, source_text="rate")
    set_content_effective(content_id, str(image), operator="admin")

    reply = _build_investment_web_reply("web-session-user", "利率")

    assert reply is not None
    assert reply.type == ReplyType.TEXT
    assert "![output_image_rate_card_" in reply.content
    assert "](/api/file?id=" in reply.content
    assert "/api/file?path=" not in reply.content
    assert "[图片:" not in reply.content
    plain = _build_investment_web_reply("web-session", "普通聊天")
    assert plain is not None
    assert plain.type == ReplyType.TEXT
    assert plain.content == DEFAULT_UNMATCHED_PROMPT
    assert WebChannel().channel_type == "web"


def test_web_channel_uses_configured_business_skill_triggers(business_env, tmp_path):
    from bridge.reply import ReplyType
    from business.config.config_service import save_config
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, set_content_effective
    from business.accounts.user_service import create_user
    from channel.web.web_channel import _build_investment_web_reply

    create_user("web-session", enabled=True, allowed_services=[ServiceType.ALL])
    save_config("skill.rate.triggers", ["今日利率"], operator_role="admin", operator="pytest")
    image = tmp_path / "rate override.png"
    image.write_bytes(b"png")
    content_id = create_content_draft(ServiceType.RATE, source_text="rate")
    set_content_effective(content_id, str(image), operator="admin")

    reply = _build_investment_web_reply("web-session", "今日利率")

    assert reply is not None
    assert reply.type == ReplyType.TEXT
    assert "![output_image_rate_override_" in reply.content
    assert "](/api/file?id=" in reply.content
    assert "/api/file?path=" not in reply.content


def test_web_channel_uses_admin_session_instead_of_customer_permission(business_env, tmp_path):
    from bridge.reply import ReplyType
    from business.config.constants import ActorType, EntryType, ServiceType, Status
    from business.content.daily_content import create_content_draft, set_content_effective
    from business.records.records import list_request_records, list_request_records_page
    from business.accounts.user_service import create_user
    from channel.web.web_channel import _build_investment_web_reply

    create_user("disabled-web", enabled=False, allowed_services=[ServiceType.ALL])
    image = tmp_path / "admin-rate.png"
    image.write_bytes(b"png")
    content_id = create_content_draft(ServiceType.RATE, source_text="rate")
    set_content_effective(content_id, str(image), operator="admin")

    reply = _build_investment_web_reply("disabled-web", "利率")

    assert reply is not None
    assert reply.type == ReplyType.TEXT
    assert "![output_image_admin-rate_" in reply.content
    assert "](/api/file?id=" in reply.content
    assert "/api/file?path=" not in reply.content
    records = list_request_records(limit=10)
    assert len(records) == 1
    assert records[0].raw_input == "利率"
    assert records[0].service_type == ServiceType.RATE
    assert records[0].status == Status.SUCCESS
    assert records[0].entry_type == EntryType.INTERNAL_CALL
    assert records[0].actor_type == ActorType.ADMIN

    public_items, public_total = list_request_records_page(entry_type=EntryType.EXTERNAL_REQUEST, page_size=10)
    backend_items, backend_total = list_request_records_page(entry_type=EntryType.INTERNAL_CALL, page_size=10)
    assert public_total == 0
    assert public_items == []
    assert backend_total == 1
    assert backend_items[0].request_id == records[0].request_id


def test_web_channel_routes_technical_analysis_as_ordinary_business_without_permission(business_env, tmp_path, monkeypatch):
    from bridge.reply import ReplyType
    from business.config.constants import ServiceType, Status
    from business.products.product_service import list_products_page
    from business.records.records import list_request_records
    from business.accounts.user_service import create_user
    from channel.web.web_channel import _build_investment_web_reply
    import business.content.technical_analysis_handler as ta_handler

    create_user("web-admin-session", enabled=False, allowed_services=[])
    signal = tmp_path / "signal.png"
    chart = tmp_path / "chart.png"
    report = tmp_path / "report.md"
    signal.write_bytes(b"signal")
    chart.write_bytes(b"chart")
    report.write_text("report", encoding="utf-8")

    monkeypatch.setattr(
        ta_handler,
        "prepare_technical_analysis_business_context",
        lambda raw_input, target_text: SimpleNamespace(cache_key="", normalized_target=target_text, market_date="2026-06-10"),
    )
    monkeypatch.setattr(
        ta_handler,
        "run_technical_analysis_business",
        lambda openid, raw_input, target_text, cache_context=None: SimpleNamespace(
            success=True,
            signal_card_path=str(signal),
            main_chart_path=str(chart),
            report_path=str(report),
            output_files=[str(signal), str(chart), str(report)],
            normalized_target=target_text,
            stock_code="300502.SZ",
            stock_name="新易盛",
            market_date="2026-06-10",
            cache_key="technical_analysis:300502.SZ:2026-06-10:v",
            cache_hit=False,
            version_fingerprint="v",
            program_version="p",
            ta_version="ta",
            renderer_version="renderer",
            template_version="template",
            detail="",
        ),
    )

    reply = _build_investment_web_reply("web-admin-session", "300502.SZ 技术分析")

    assert reply is not None
    assert reply.type == ReplyType.TEXT
    assert "已生成投资业务图片" in reply.content
    records = list_request_records(limit=10)
    assert len(records) == 1
    assert records[0].raw_input == "300502.SZ 技术分析"
    assert records[0].service_type == ServiceType.TECHNICAL_ANALYSIS
    assert records[0].status == Status.SUCCESS
    products, total = list_products_page(include_invalidated=True, business_type=str(ServiceType.TECHNICAL_ANALYSIS))
    assert total >= 1
    assert any(
        product["source_cache_key"] == "technical_analysis:300502.SZ:2026-06-10:v"
        and product["source_request_id"] == records[0].request_id
        for product in products
    )


def test_web_technical_analysis_without_cache_key_appears_in_request_history(business_env, tmp_path, monkeypatch):
    from bridge.reply import ReplyType
    from business.config.constants import ServiceType, Status
    from business.records.records import list_request_records
    from channel.web.web_channel import _build_investment_web_reply
    import business.content.technical_analysis_handler as ta_handler

    signal = tmp_path / "signal-no-cache.png"
    chart = tmp_path / "chart-no-cache.png"
    report = tmp_path / "report-no-cache.md"
    signal.write_bytes(b"signal")
    chart.write_bytes(b"chart")
    report.write_text("report", encoding="utf-8")

    monkeypatch.setattr(
        ta_handler,
        "prepare_technical_analysis_business_context",
        lambda raw_input, target_text: SimpleNamespace(cache_key="", normalized_target=target_text, market_date=""),
    )
    monkeypatch.setattr(
        ta_handler,
        "run_technical_analysis_business",
        lambda openid, raw_input, target_text, cache_context=None: SimpleNamespace(
            success=True,
            signal_card_path=str(signal),
            main_chart_path=str(chart),
            report_path=str(report),
            output_files=[str(signal), str(chart), str(report)],
            normalized_target=target_text,
            stock_code="300502.SZ",
            stock_name="新易盛",
            market_date="",
            cache_key="",
            cache_hit=False,
            version_fingerprint="v",
            program_version="p",
            ta_version="ta",
            renderer_version="renderer",
            template_version="template",
            detail="",
        ),
    )

    reply = _build_investment_web_reply("web-admin-session", "300502.SZ 技术分析")

    assert reply is not None
    assert reply.type == ReplyType.TEXT
    records = list_request_records(limit=10)
    assert len(records) == 1
    assert records[0].service_type == ServiceType.TECHNICAL_ANALYSIS
    assert records[0].status == Status.SUCCESS


def test_web_open_chat_uses_plain_model_without_agent_bridge(business_env, monkeypatch):
    from bridge.reply import Reply, ReplyType
    from business.config.config_service import save_config
    from bridge.context import Context, ContextType
    from channel.chat_channel import ChatChannel
    from channel.web.web_channel import WebChannel, WebMessage

    save_config("router.enable_web_open_chat", True, operator_role="admin")
    calls = []

    def fake_fetch_reply_content(query, context):
        calls.append((query, context.get("session_id")))
        return Reply(ReplyType.TEXT, "plain model reply")

    import bridge.bridge as bridge_module

    monkeypatch.setattr(bridge_module.Bridge(), "fetch_reply_content", fake_fetch_reply_content)
    monkeypatch.setattr(
        ChatChannel,
        "_generate_reply",
        lambda *_args, **_kwargs: pytest.fail("web open chat must not enter AgentBridge path"),
    )

    context = Context(ContextType.TEXT, "普通聊天", {"msg": WebMessage("msg-1", "普通聊天")})
    context["session_id"] = "web-session"

    reply = WebChannel()._generate_reply(context)

    assert reply.type == ReplyType.TEXT
    assert reply.content == "plain model reply"
    assert calls == [("普通聊天", "web-session")]


def test_web_open_chat_reply_is_persisted_to_session_history(business_env, monkeypatch):
    from bridge.reply import Reply, ReplyType
    from business.config.config_service import save_config
    from bridge.context import Context, ContextType
    from agent.memory import get_conversation_store
    from channel.web.web_channel import WebChannel, WebMessage

    save_config("router.enable_web_open_chat", True, operator_role="admin")

    import bridge.bridge as bridge_module

    monkeypatch.setattr(
        bridge_module.Bridge(),
        "fetch_reply_content",
        lambda query, context: Reply(ReplyType.TEXT, "plain model reply"),
    )

    context = Context(ContextType.TEXT, "普通聊天", {"msg": WebMessage("msg-1", "普通聊天")})
    context["session_id"] = "web-session-persist"

    reply = WebChannel()._generate_reply(context)

    assert reply.type == ReplyType.TEXT
    store = get_conversation_store()
    sessions = store.list_sessions(channel_type="web", page=1, page_size=10)
    assert [item["session_id"] for item in sessions["sessions"]] == ["web-session-persist"]
    history = store.load_history_page("web-session-persist", page=1, page_size=10)
    assert [(item["role"], item["content"]) for item in history["messages"]] == [
        ("user", "普通聊天"),
        ("assistant", "plain model reply"),
    ]


def test_wechatmp_channel_uses_effective_content_and_permission_prompts(business_env, tmp_path, monkeypatch):
    from bridge.context import Context, ContextType
    from bridge.reply import ReplyType
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, set_content_effective
    from business.accounts.user_service import create_user
    import channel.wechatmp.wechatmp_channel as wechatmp_channel

    instances = wechatmp_channel.WechatMPChannel.__closure__[1].cell_contents
    instances.clear()
    monkeypatch.setattr(
        wechatmp_channel,
        "conf",
        lambda: {
            "wechatmp_app_id": "wx-test",
            "wechatmp_app_secret": "secret",
            "wechatmp_token": "token",
            "wechatmp_aes_key": "",
            "single_chat_prefix": [""],
            "concurrency_in_session": 1,
        },
    )
    channel = wechatmp_channel.WechatMPChannel()

    rate_image = tmp_path / "wechat-rate.png"
    cb_image = tmp_path / "wechat-cb.png"
    rate_image.write_bytes(b"rate")
    cb_image.write_bytes(b"cb")
    rate_id = create_content_draft(ServiceType.RATE, source_text="rate", effective_date=_beijing_today())
    cb_id = create_content_draft(ServiceType.CONVERTIBLE_BOND, source_text="cb", effective_date=_beijing_today())
    set_content_effective(rate_id, str(rate_image), operator="tester")
    set_content_effective(cb_id, str(cb_image), operator="tester")

    create_user("openid-ok", enabled=True, allowed_services=[ServiceType.ALL], auth_end_at="2099-12-31T23:59:59")
    create_user("openid-disabled", enabled=False, allowed_services=[ServiceType.ALL])
    create_user("openid-expired", enabled=True, allowed_services=[ServiceType.ALL], auth_end_at="2020-01-01T00:00:00")

    def context(openid, content):
        msg = SimpleNamespace(from_user_id=openid, other_user_id=openid, msg_id=f"{openid}-{content}")
        return Context(
            ContextType.TEXT,
            content,
            {
                "msg": msg,
                "session_id": openid,
                "receiver": openid,
                "channel_type": "wechatmp",
                "isgroup": False,
            },
        )

    rate_reply = channel._generate_reply(context("openid-ok", "利率"))
    cb_reply = channel._generate_reply(context("openid-ok", "转债"))
    missing_reply = channel._generate_reply(context("openid-missing", "利率"))
    disabled_reply = channel._generate_reply(context("openid-disabled", "利率"))
    expired_reply = channel._generate_reply(context("openid-expired", "利率"))

    assert rate_reply.type == ReplyType.IMAGE_URL
    assert rate_reply.content != [str(rate_image)]
    assert all("storage" in path and "files" in path for path in rate_reply.content)
    assert cb_reply.type == ReplyType.IMAGE_URL
    assert cb_reply.content != [str(cb_image)]
    assert all("storage" in path and "files" in path for path in cb_reply.content)
    assert missing_reply.type == ReplyType.TEXT
    assert missing_reply.content == "您暂未开通该服务，如需开通请联系服务人员。"
    assert disabled_reply.type == ReplyType.TEXT
    assert disabled_reply.content == "您的服务已停用，如需恢复请联系服务人员。"
    assert expired_reply.type == ReplyType.TEXT
    assert expired_reply.content == "您的授权已过期，如需续期请联系服务人员。"
