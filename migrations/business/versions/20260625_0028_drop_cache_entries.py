# encoding:utf-8
"""Drop legacy cache entries after product cache migration."""

from datetime import UTC, datetime
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "20260625_0028"
down_revision = "20260624_0027"
branch_labels = None
depends_on = None


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _cache_entries_exists(bind) -> bool:
    return sa.inspect(bind).has_table("cache_entries")


def _backfill_missing_cache_products(bind) -> None:
    rows = bind.execute(
        sa.text(
            """
            select cache_key, service, normalized_target, market_date,
                   version_fingerprint, outputs, artifact_owner_id,
                   status, hit_count, created_at, updated_at
            from cache_entries
            """
        )
    ).mappings()
    insert_product = sa.text(
        """
        insert into products (
            product_id, business_type, target_key, target_label,
            business_date, logical_key, version_fingerprint, status,
            source_request_id, source_content_id, source_cache_key,
            source_type, source_files, output_files, text_content,
            metadata, hit_count, expires_at, effective_at,
            invalidated_at, archived_at, created_at, updated_at
        ) values (
            :product_id, :business_type, :target_key, :target_label,
            :business_date, :logical_key, :version_fingerprint, :status,
            :source_request_id, '', :source_cache_key,
            'cache', '[]', :output_files, '',
            '{}', :hit_count, '', :effective_at,
            '', '', :created_at, :updated_at
        )
        """
    )
    for row in rows:
        cache_key = str(row.get("cache_key") or "")
        if not cache_key:
            continue
        exists = bind.execute(
            sa.text("select 1 from products where source_cache_key = :cache_key limit 1"),
            {"cache_key": cache_key},
        ).first()
        if exists:
            continue
        created_at = str(row.get("created_at") or _now())
        updated_at = str(row.get("updated_at") or created_at)
        business_type = str(row.get("service") or "")
        target_key = str(row.get("normalized_target") or "")
        business_date = str(row.get("market_date") or "")
        bind.execute(
            insert_product,
            {
                "product_id": f"prod_legacy_cache_{uuid4().hex}",
                "business_type": business_type,
                "target_key": target_key,
                "target_label": target_key,
                "business_date": business_date,
                "logical_key": f"{business_type}:{target_key}:{business_date}:{cache_key}",
                "version_fingerprint": str(row.get("version_fingerprint") or ""),
                "status": str(row.get("status") or "active"),
                "source_request_id": str(row.get("artifact_owner_id") or ""),
                "source_cache_key": cache_key,
                "output_files": str(row.get("outputs") or "[]"),
                "hit_count": int(row.get("hit_count") or 0),
                "effective_at": created_at,
                "created_at": created_at,
                "updated_at": updated_at,
            },
        )


def _assert_cache_products_backfilled(bind) -> None:
    missing = bind.execute(
        sa.text(
            """
            select count(*)
            from cache_entries c
            where c.cache_key <> ''
              and not exists (
                select 1
                from products p
                where p.source_cache_key = c.cache_key
              )
            """
        )
    ).scalar_one()
    if missing:
        raise RuntimeError(f"refusing to drop cache_entries with {missing} unbackfilled cache rows")


def upgrade() -> None:
    bind = op.get_bind()
    if not _cache_entries_exists(bind):
        return
    _backfill_missing_cache_products(bind)
    _assert_cache_products_backfilled(bind)
    op.drop_table("cache_entries")


def downgrade() -> None:
    op.create_table(
        "cache_entries",
        sa.Column("cache_key", sa.Text(), primary_key=True),
        sa.Column("service", sa.Text(), nullable=False),
        sa.Column("normalized_target", sa.Text(), nullable=False),
        sa.Column("market_date", sa.Text(), nullable=False),
        sa.Column("version_fingerprint", sa.Text(), nullable=False),
        sa.Column("outputs", sa.Text(), nullable=False),
        sa.Column("artifact_owner_id", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "idx_cache_entries_lookup",
        "cache_entries",
        ["service", "normalized_target", "market_date", "version_fingerprint", "status"],
    )
    op.create_index("idx_cache_entries_service_date", "cache_entries", ["service", "market_date", "status"])
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            insert into cache_entries (
                cache_key, service, normalized_target, market_date,
                version_fingerprint, outputs, artifact_owner_id,
                status, hit_count, created_at, updated_at
            )
            select source_cache_key, business_type, target_key, business_date,
                   version_fingerprint, output_files, source_request_id,
                   status, hit_count, created_at, updated_at
            from (
                select source_cache_key, business_type, target_key, business_date,
                       version_fingerprint, output_files, source_request_id,
                       status, hit_count, created_at, updated_at,
                       row_number() over (
                           partition by source_cache_key
                           order by updated_at desc, created_at desc, product_id desc
                       ) as row_number
                from products
                where coalesce(source_cache_key, '') <> ''
            ) product_cache_rows
            where row_number = 1
            """
        )
    )
