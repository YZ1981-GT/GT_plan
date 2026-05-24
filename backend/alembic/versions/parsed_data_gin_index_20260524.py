"""Create GIN index on working_papers.parsed_data for JSONB path queries.

Revision ID: parsed_data_gin_index_20260524
Revises: wp_template_registry_20260524
Create Date: 2026-05-24

Requirements: Req 5 (advanced-query-enhancements-p1p2)
Design: D3 — GIN 索引强制 CREATE CONCURRENTLY + _ccnew 残骸清理

Notes:
  - Uses CREATE INDEX CONCURRENTLY to avoid locking the table
  - Uses jsonb_path_ops (not jsonb_ops) — only supports @> but 30-50% smaller
  - On failure, cleans up _ccnew residual index before retrying
  - Must run outside a transaction (CONCURRENTLY requirement)
"""
import logging

from alembic import op
import sqlalchemy as sa

logger = logging.getLogger("alembic.runtime.migration")

# revision identifiers
revision = "parsed_data_gin_index_20260524"
down_revision = "wp_template_registry_20260524"
branch_labels = None
depends_on = None

INDEX_NAME = "idx_wp_parsed_data_gin"
CCNEW_INDEX_NAME = "idx_wp_parsed_data_gin_ccnew"


def upgrade() -> None:
    """Create GIN index CONCURRENTLY on working_papers.parsed_data.

    PG 运维铁律:
    - CONCURRENTLY cannot run inside a transaction block
    - On failure, PG leaves a _ccnew residual index that must be cleaned up
    - SET lock_timeout via set_config (SET doesn't support bind params)
    """
    conn = op.get_bind()

    # ─── Step 1: Clean up any _ccnew residual from previous failed attempts ─
    _cleanup_ccnew_residual(conn)

    # ─── Step 2: Check if index already exists ───────────────────────────────
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_indexes WHERE indexname = :name"
        ),
        {"name": INDEX_NAME},
    )
    if result.fetchone():
        logger.info("GIN index %s already exists, skipping creation", INDEX_NAME)
        return

    # ─── Step 3: Create index CONCURRENTLY ───────────────────────────────────
    # CONCURRENTLY requires autocommit (no transaction wrapper).
    # Alembic's op.execute with postgresql_concurrently handles this,
    # but we use raw SQL for explicit control + lock_timeout.
    try:
        # Set lock_timeout to avoid blocking indefinitely
        conn.execute(sa.text("SELECT set_config('lock_timeout', '3s', false)"))

        # Must commit any open transaction before CONCURRENTLY
        conn.execute(sa.text("COMMIT"))

        conn.execute(
            sa.text(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} "
                f"ON working_papers USING GIN (parsed_data jsonb_path_ops)"
            )
        )
        logger.info("GIN index %s created successfully", INDEX_NAME)
    except Exception as e:
        logger.error("Failed to create GIN index %s: %s", INDEX_NAME, e)
        # Clean up _ccnew residual on failure
        try:
            _cleanup_ccnew_residual(conn)
        except Exception as cleanup_err:
            logger.warning("Failed to cleanup _ccnew residual: %s", cleanup_err)
        raise
    finally:
        # Reset lock_timeout
        try:
            conn.execute(sa.text("SELECT set_config('lock_timeout', '0', false)"))
        except Exception:
            pass


def downgrade() -> None:
    """Drop the GIN index."""
    conn = op.get_bind()

    # Clean up any _ccnew residual first
    _cleanup_ccnew_residual(conn)

    # Drop the main index (CONCURRENTLY to avoid locks)
    result = conn.execute(
        sa.text("SELECT 1 FROM pg_indexes WHERE indexname = :name"),
        {"name": INDEX_NAME},
    )
    if result.fetchone():
        try:
            conn.execute(sa.text("COMMIT"))
            conn.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}"))
            logger.info("GIN index %s dropped", INDEX_NAME)
        except Exception as e:
            logger.error("Failed to drop GIN index %s: %s", INDEX_NAME, e)
            raise


def _cleanup_ccnew_residual(conn) -> None:
    """Remove _ccnew residual index left by a failed CONCURRENTLY operation."""
    result = conn.execute(
        sa.text("SELECT 1 FROM pg_indexes WHERE indexname = :name"),
        {"name": CCNEW_INDEX_NAME},
    )
    if result.fetchone():
        logger.warning("Found _ccnew residual index %s, cleaning up...", CCNEW_INDEX_NAME)
        try:
            conn.execute(sa.text("COMMIT"))
            conn.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {CCNEW_INDEX_NAME}"))
            logger.info("Cleaned up _ccnew residual index %s", CCNEW_INDEX_NAME)
        except Exception as e:
            logger.warning("Could not drop _ccnew residual: %s", e)
