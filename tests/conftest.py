# encoding:utf-8
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


@pytest.fixture()
def business_env(tmp_path, monkeypatch):
    from business.schema import db as db
    from business.schema import storage as storage
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
    monkeypatch.setenv("COWAGENT_BUSINESS_STORAGE_ROOT", str(tmp_path / "storage"))
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
