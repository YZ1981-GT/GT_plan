"""GIN index monitoring and degradation control for working_papers.parsed_data.

Requirements: Req 5 (advanced-query-enhancements-p1p2)
Design: D3 — 启动时检查 pg_stat_progress_create_index → 全局 INDEX_BUILDING flag

This module provides:
1. Startup check: queries pg_stat_progress_create_index to detect if the GIN index
   is still being built (CREATE INDEX CONCURRENTLY in progress)
2. Global flag INDEX_BUILDING that controls query path degradation
3. Index size monitoring with 500MB alert threshold
"""
import logging
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ─── Global state ────────────────────────────────────────────────────────────

INDEX_BUILDING: bool = False
"""Global flag: True when the GIN index is still being built.
When True, queries should degrade to sequential scan and add X-Index-Status=building header."""

INDEX_NAME = "idx_wp_parsed_data_gin"
TABLE_NAME = "working_paper"

# Alert threshold for index size (bytes)
INDEX_SIZE_ALERT_THRESHOLD_BYTES = 500 * 1024 * 1024  # 500MB


async def check_index_building_status(db: AsyncSession) -> bool:
    """Check if the GIN index is currently being built via pg_stat_progress_create_index.

    Called at application startup to set the global INDEX_BUILDING flag.
    Also checks if the index exists and is valid.

    Returns:
        True if index is currently building, False otherwise.
    """
    global INDEX_BUILDING

    try:
        # Check if there's an active CREATE INDEX operation for our table
        result = await db.execute(
            sa.text(
                """
                SELECT 1
                FROM pg_stat_progress_create_index p
                JOIN pg_class c ON c.oid = p.relid
                WHERE c.relname = :table_name
                LIMIT 1
                """
            ),
            {"table_name": TABLE_NAME},
        )
        row = result.fetchone()
        if row:
            INDEX_BUILDING = True
            logger.warning(
                "GIN index %s on %s is currently being built (CREATE INDEX CONCURRENTLY in progress). "
                "Queries will degrade to sequential scan.",
                INDEX_NAME,
                TABLE_NAME,
            )
            return True

        # Also check if the index exists but is not yet valid (partially built)
        result = await db.execute(
            sa.text(
                """
                SELECT i.indisvalid
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                WHERE c.relname = :index_name
                """
            ),
            {"index_name": INDEX_NAME},
        )
        row = result.fetchone()
        if row is None:
            # Index doesn't exist at all
            INDEX_BUILDING = True
            logger.warning(
                "GIN index %s does not exist on %s. Queries will degrade to sequential scan.",
                INDEX_NAME,
                TABLE_NAME,
            )
            return True
        elif not row[0]:
            # Index exists but is invalid (failed CONCURRENTLY)
            INDEX_BUILDING = True
            logger.warning(
                "GIN index %s exists but is INVALID. Queries will degrade to sequential scan.",
                INDEX_NAME,
            )
            return True

        # Index exists and is valid
        INDEX_BUILDING = False
        logger.info("GIN index %s is ready and valid.", INDEX_NAME)
        return False

    except Exception as e:
        # If we can't check (e.g., SQLite in tests), assume not building
        logger.debug("Could not check index building status (likely non-PG): %s", e)
        INDEX_BUILDING = False
        return False


async def get_index_size_bytes(db: AsyncSession) -> Optional[int]:
    """Get the current size of the GIN index in bytes.

    Returns:
        Size in bytes, or None if index doesn't exist or query fails.
    """
    try:
        result = await db.execute(
            sa.text("SELECT pg_index_size(:index_name)"),
            {"index_name": INDEX_NAME},
        )
        row = result.fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.debug("Could not get index size: %s", e)
        return None


async def check_index_size_alert(db: AsyncSession) -> Optional[dict]:
    """Check if the GIN index size exceeds the 500MB alert threshold.

    Returns:
        Alert dict with size info if threshold exceeded, None otherwise.
    """
    size_bytes = await get_index_size_bytes(db)
    if size_bytes is None:
        return None

    size_mb = size_bytes / (1024 * 1024)

    if size_bytes > INDEX_SIZE_ALERT_THRESHOLD_BYTES:
        alert = {
            "alert": "gin_index_size_exceeded",
            "index_name": INDEX_NAME,
            "size_bytes": size_bytes,
            "size_mb": round(size_mb, 2),
            "threshold_mb": INDEX_SIZE_ALERT_THRESHOLD_BYTES / (1024 * 1024),
            "recommendation": "Evaluate jsonb_path_ops partitioning or partial index strategy",
        }
        logger.warning(
            "GIN index %s size %.2f MB exceeds threshold %.0f MB. "
            "DBA should evaluate jsonb_path_ops alternatives.",
            INDEX_NAME,
            size_mb,
            INDEX_SIZE_ALERT_THRESHOLD_BYTES / (1024 * 1024),
        )
        return alert

    return None


def is_index_building() -> bool:
    """Thread-safe read of the INDEX_BUILDING flag."""
    return INDEX_BUILDING


def set_index_building(value: bool) -> None:
    """Explicitly set the INDEX_BUILDING flag (for testing or manual override)."""
    global INDEX_BUILDING
    INDEX_BUILDING = value
