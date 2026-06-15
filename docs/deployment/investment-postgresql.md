# Investment PostgreSQL Deployment Runbook

This runbook covers deployment, migration, rollback, and Navicat connection notes for the shared PostgreSQL database used by investment data and Agent conversation history.

## Deployment Modes

Investment data and Agent conversation history use PostgreSQL. The legacy local SQLite investment database at `investment/investment.db` is only a migration source for older deployments.

To use PostgreSQL, set `COWAGENT_INVESTMENT_DATABASE_URL` in the runtime environment:

```powershell
$env:COWAGENT_INVESTMENT_DATABASE_URL = "postgresql+psycopg://cowagent_user:example-password@localhost:5432/cowagent_investment"
```

If the environment variable is not set, the application may read `investment_database_url` from `config.json`. The environment variable has priority over the config file key. Do not store the database URL in `investment_configs`, because that table lives inside the selected database and cannot reliably select the database connection itself.

Use placeholder credentials in examples, local scripts, and shared docs. Do not commit real database secrets.

## Schema Upgrade

After selecting PostgreSQL, run the Alembic migrations. These create the investment tables plus `agent_sessions` and `agent_messages` for normal Agent conversation persistence:

```powershell
alembic -c migrations/investment/alembic.ini upgrade head
```

Run the normal quality gates after configuration changes. For PostgreSQL-specific integration tests, set the optional PostgreSQL test environment variable expected by the test suite before running those tests.

## SQLite To PostgreSQL Migration

Keep the SQLite database file until the migration has been verified. Migrate existing investment data with:

```powershell
py scripts/migrate_investment_sqlite_to_pg.py --sqlite investment/investment.db --pg postgresql+psycopg://cowagent_user:example-password@localhost:5432/cowagent_investment
```

After migration, run the application against PostgreSQL and verify the expected investment records are present before changing operational traffic.

Agent conversation history is intentionally not migrated from the old SQLite memory index. New conversations are written to PostgreSQL table `agent_messages` through the existing Agent conversation store API.

Long-term memory indexing is disabled by default with:

```json
"agent_memory_index": false
```

When disabled, the application does not initialize the SQLite-backed long-term memory index. This does not affect recent per-user conversation context, which is restored from PostgreSQL `agent_messages`.

## Optional Local PostgreSQL

For local integration testing, a disposable Docker PostgreSQL instance is sufficient:

```powershell
docker run --name cowagent-investment-pg -e POSTGRES_DB=cowagent_investment -e POSTGRES_USER=cowagent_user -e POSTGRES_PASSWORD=example-password -p 5432:5432 -d postgres:16
```

Then set `COWAGENT_INVESTMENT_DATABASE_URL` to:

```text
postgresql+psycopg://cowagent_user:example-password@localhost:5432/cowagent_investment
```

## Navicat Connection

Create a new Navicat PostgreSQL connection with non-secret environment-specific values:

| Field | Example |
| --- | --- |
| Host | `localhost` |
| Port | `5432` |
| Database | `cowagent_investment` |
| User | `cowagent_user` |
| Password | Use the deployment secret, not a value from this document |
| SSL mode | Use `prefer` or the mode required by the PostgreSQL provider |

For hosted PostgreSQL, use the provider hostname, port, database name, username, password, and SSL mode. Do not paste production secrets into documentation, tickets, or screenshots.

## Rollback

To rollback from PostgreSQL to SQLite, unset `COWAGENT_INVESTMENT_DATABASE_URL` and remove `investment_database_url` from `config.json`. The application will return to the default SQLite deployment path.

```powershell
Remove-Item Env:COWAGENT_INVESTMENT_DATABASE_URL
```

Keep `investment/investment.db` unchanged unless you intentionally migrated writes away from it and have a separate data reconciliation plan. PostgreSQL migration does not automatically copy later PostgreSQL writes back into SQLite.

## Operational Warnings

Generated image and file paths stored by investment features are local paths, not shared storage. Moving metadata to PostgreSQL does not make generated images or files available across machines. Use shared object storage or another explicit file distribution mechanism if multiple machines need to read the same generated assets.

The long-term memory index is not part of this migration. Do not migrate `agent/memory` index data unless you explicitly plan a separate PostgreSQL memory-index implementation.
