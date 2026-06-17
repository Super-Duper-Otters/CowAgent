# encoding:utf-8
import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


@pytest.fixture()
def investment_env(tmp_path, monkeypatch):
    from business import db
    from business import storage

    base_url = os.environ.get("COWAGENT_TEST_POSTGRES_URL") or db.DEFAULT_DATABASE_URL
    schema_name = f"cowagent_sync_test_{uuid4().hex}"
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


def _investment_config_keys():
    from business import db
    from business.schema import investment_configs

    with db.connect() as conn:
        rows = conn.execute(select(investment_configs.c.config_key)).fetchall()
    return {row[0] for row in rows}


def test_investment_config_save_rejects_global_model_keys_and_does_not_touch_project_config(
    investment_env,
    monkeypatch,
):
    cfg_path = investment_env / "config.json"
    original = {
        "bot_type": "custom",
        "model": "old-model",
        "custom_api_base": "https://old.example/v1",
        "custom_api_key": "sk-old",
        "temperature": 0.7,
    }
    cfg_path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("COWAGENT_CONFIG_PATH", str(cfg_path))

    from business import config_service

    runtime_cfg = dict(original)
    monkeypatch.setattr(config_service, "conf", lambda: runtime_cfg)

    with pytest.raises(ValueError, match="model.name"):
        config_service.save_configs(
            {
                "model.provider": "custom",
                "model.name": "new-model",
                "model.api_base": "https://new.example/v1",
                "model.api_key": "sk-new-secret",
                "model.temperature": 0.2,
            },
            operator_role="admin",
            operator="web-console",
            sync_project=True,
        )

    assert json.loads(cfg_path.read_text(encoding="utf-8")) == original
    assert runtime_cfg == original
    assert not any(key.startswith("model.") for key in _investment_config_keys())


def test_global_config_post_does_not_create_investment_model_aliases(investment_env, monkeypatch):
    cfg_path = investment_env / "fake_app" / "config.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(
        json.dumps(
            {
                "bot_type": "custom",
                "model": "old-global",
                "custom_api_base": "https://old-global.example/v1",
                "custom_api_key": "sk-old-global",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    from channel.web import web_channel

    fake_web_file = cfg_path.parent / "channel" / "web" / "web_channel.py"
    fake_web_file.parent.mkdir(parents=True)
    monkeypatch.setattr(web_channel, "__file__", str(fake_web_file))
    runtime_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    monkeypatch.setattr(web_channel, "conf", lambda: runtime_cfg)
    monkeypatch.setattr(web_channel, "_require_auth", lambda: None)
    monkeypatch.setattr(web_channel.web, "header", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        web_channel.web,
        "data",
        lambda: json.dumps(
            {
                "updates": {
                    "bot_type": "custom",
                    "use_linkai": False,
                    "model": "new-global",
                    "custom_api_base": "https://new-global.example/v1",
                    "custom_api_key": "sk-new-global",
                },
            },
            ensure_ascii=False,
        ).encode("utf-8"),
    )

    payload = json.loads(web_channel.ConfigHandler().POST())

    assert payload["status"] == "success"
    saved = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert saved["model"] == "new-global"
    assert saved["custom_api_base"] == "https://new-global.example/v1"
    assert saved["custom_api_key"] == "sk-new-global"
    assert not any(key.startswith("model.") for key in _investment_config_keys())
