# Agent Messages PostgreSQL Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move regular Agent conversation persistence from SQLite to the existing PostgreSQL business database using an `agent_messages` table, while leaving long-term memory indexing disabled for this deployment.

**Architecture:** Keep the existing `get_conversation_store()` API so Agent code does not change. Replace the SQLite-backed implementation with SQLAlchemy queries against the existing investment PostgreSQL engine and add Alembic-managed tables for agent sessions/messages. Add a config switch that disables long-term memory index initialization so no SQLite memory index is created for normal公众号 Agent conversations.

**Tech Stack:** Python, SQLAlchemy Core, Alembic, PostgreSQL, pytest.

---

### Task 1: Add PostgreSQL Conversation Schema

**Files:**
- Modify: `business/investment/schema.py`
- Create: `migrations/investment/versions/20260612_0021_agent_messages.py`
- Test: `tests/test_agent_messages_postgres.py`

- [ ] Write a failing test that appends and loads messages through `get_conversation_store()` and verifies rows are stored in `agent_messages`.
- [ ] Run `py -m pytest tests/test_agent_messages_postgres.py -q` and verify failure because `agent_messages` does not exist.
- [ ] Add `agent_sessions` and `agent_messages` SQLAlchemy table definitions to `business/investment/schema.py`.
- [ ] Add Alembic revision `20260612_0021_agent_messages.py` creating `agent_sessions`, `agent_messages`, and indexes.
- [ ] Run the focused test and verify it passes.

### Task 2: Replace SQLite Conversation Store With SQLAlchemy

**Files:**
- Modify: `agent/memory/conversation_store.py`
- Test: `tests/test_agent_messages_postgres.py`

- [ ] Add failing tests for `clear_context`, `load_history_page`, `list_sessions`, `rename_session`, `cleanup_old_sessions`, and `prune_scheduled_messages`.
- [ ] Run the focused test and verify expected failures against the SQLite implementation/PG schema.
- [ ] Rework `ConversationStore` internals to use `business.investment.db.connect()` and SQLAlchemy Core while preserving the public method names and return shapes.
- [ ] Keep JSON serialization behavior identical to the current store.
- [ ] Run focused tests and existing investment tests that touch conversation/web history.

### Task 3: Disable Long-Term Memory SQLite Index

**Files:**
- Modify: `config.py`
- Modify: `bridge/agent_initializer.py`
- Test: `tests/test_agent_messages_postgres.py`

- [ ] Add config key `agent_memory_index` defaulting to `False`.
- [ ] Add a failing test showing `_setup_memory_system()` does not create `MemoryManager` when `agent_memory_index` is false.
- [ ] Modify `_setup_memory_system()` to skip `MemoryManager` and memory tools when disabled.
- [ ] Keep conversation persistence independent from this flag.
- [ ] Run focused tests and a smoke import of `bridge.agent_initializer`.

### Task 4: Verify Deployment Shape

**Files:**
- Modify: `docs/deployment/investment-postgresql.md`

- [ ] Update docs to state that Agent conversations now use PostgreSQL `agent_messages`.
- [ ] State that long-term memory indexing is disabled by default and is not migrated.
- [ ] Run `py -m pytest tests/test_agent_messages_postgres.py -q`.
- [ ] Run `py -m pytest tests/test_investment_business.py -q -k "database_url or config"` if local PostgreSQL is available.
