# encoding:utf-8
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url


@pytest.fixture()
def agent_messages_pg_env(tmp_path, monkeypatch):
    if not os.environ.get("COWAGENT_TEST_POSTGRES_URL"):
        pytest.skip("COWAGENT_TEST_POSTGRES_URL not configured")

    from business import db
    from business import storage
    import agent.memory.conversation_store as conversation_store

    base_url = os.environ["COWAGENT_TEST_POSTGRES_URL"]
    schema_name = f"cowagent_agent_messages_{uuid4().hex}"
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
    monkeypatch.setenv("AGENT_MEMORY_INDEX", "false")
    db.reset_engine_for_tests()
    storage._MIGRATED_DATABASE_URL = None
    conversation_store._store_instance = None
    storage.initialize_storage()
    try:
        yield
    finally:
        conversation_store._store_instance = None
        db.reset_engine_for_tests()
        storage._MIGRATED_DATABASE_URL = None
        with admin_engine.begin() as conn:
            conn.execute(text(f'drop schema if exists "{schema_name}" cascade'))
        admin_engine.dispose()


def test_agent_messages_schema_is_declared():
    from business.schema import metadata

    assert "agent_sessions" in metadata.tables
    assert "agent_messages" in metadata.tables
    assert {
        "id",
        "session_id",
        "seq",
        "role",
        "content",
        "created_at",
    }.issubset(metadata.tables["agent_messages"].columns.keys())


def test_conversation_store_persists_agent_messages_to_postgres(agent_messages_pg_env):
    from agent.memory.conversation_store import get_conversation_store
    from business.db import connect
    from business.schema import agent_messages

    store = get_conversation_store()
    store.append_messages(
        "openid-1",
        [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好，有什么可以帮你？"},
        ],
        channel_type="wechatmp",
    )

    assert store.load_messages("openid-1", max_turns=3) == [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好，有什么可以帮你？"},
    ]

    with connect() as conn:
        rows = conn.execute(
            select(agent_messages.c.session_id, agent_messages.c.seq, agent_messages.c.role)
            .where(agent_messages.c.session_id == "openid-1")
            .order_by(agent_messages.c.seq)
        ).fetchall()

    assert [(row.session_id, row.seq, row.role) for row in rows] == [
        ("openid-1", 0, "user"),
        ("openid-1", 1, "assistant"),
    ]


def test_conversation_store_context_and_history_methods_use_postgres(agent_messages_pg_env):
    from agent.memory.conversation_store import get_conversation_store

    store = get_conversation_store()
    store.append_messages(
        "openid-2",
        [
            {"role": "user", "content": "第一问"},
            {"role": "assistant", "content": "第一答"},
        ],
        channel_type="wechatmp",
    )
    assert store.rename_session("openid-2", "公众号用户") is True
    assert store.clear_context("openid-2") == 2
    assert store.get_context_start_seq("openid-2") == 2

    store.append_messages(
        "openid-2",
        [
            {"role": "user", "content": "第二问"},
            {"role": "assistant", "content": "第二答"},
        ],
        channel_type="wechatmp",
    )

    assert store.load_messages("openid-2", max_turns=3) == [
        {"role": "user", "content": "第二问"},
        {"role": "assistant", "content": "第二答"},
    ]
    page = store.load_history_page("openid-2", page=1, page_size=10)
    assert page["context_start_seq"] == 2
    assert page["total"] == 4
    assert [item["content"] for item in page["messages"]] == ["第一问", "第一答", "第二问", "第二答"]

    sessions = store.list_sessions(channel_type="wechatmp")
    assert sessions["total"] == 1
    assert sessions["sessions"][0]["session_id"] == "openid-2"
    assert sessions["sessions"][0]["title"] == "公众号用户"
    assert store.get_stats()["total_messages"] == 4

    store.clear_session("openid-2")
    assert store.load_messages("openid-2") == []


def test_conversation_store_prunes_scheduled_and_old_sessions(agent_messages_pg_env):
    from agent.memory.conversation_store import get_conversation_store
    from business.db import connect

    store = get_conversation_store()
    for idx in range(3):
        store.append_messages(
            "openid-3",
            [
                {"role": "user", "content": f"[SCHEDULED] 第{idx}次"},
                {"role": "assistant", "content": f"结果{idx}"},
            ],
            channel_type="wechatmp",
        )

    assert store.prune_scheduled_messages("openid-3", keep_last_n=1) == 4
    history = store.load_history_page("openid-3", page=1, page_size=10)
    assert [item["content"] for item in history["messages"]] == ["[SCHEDULED] 第2次", "结果2"]

    with connect() as conn:
        conn.execute(
            text("update agent_sessions set last_active = 1 where session_id = 'openid-3'")
        )
    assert store.cleanup_old_sessions(max_age_days=1) == 1
    assert store.list_sessions()["total"] == 0


def test_memory_index_is_disabled_by_default(tmp_path):
    from bridge.agent_initializer import AgentInitializer
    from config import conf

    conf()["agent_memory_index"] = False
    initializer = AgentInitializer(None, None)

    memory_manager, memory_tools = initializer._setup_memory_system(str(tmp_path / "cow"), session_id="openid-4")

    assert memory_manager is None
    assert memory_tools == []
    assert not (tmp_path / "cow" / "memory" / "long-term" / "index.db").exists()
