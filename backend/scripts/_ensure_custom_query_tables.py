"""Idempotently ensure the existing custom_query_templates schema.

Compatibility repair only: this mirrors V033/V051/V101 and is not a migration.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.core.database import engine

DDL = """
CREATE TABLE IF NOT EXISTS custom_query_templates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) NOT NULL DEFAULT '',
  description TEXT,
  data_source VARCHAR(50),
  config JSONB NOT NULL DEFAULT '{}',
  scope VARCHAR(16) NOT NULL DEFAULT 'private',
  tags TEXT[] NOT NULL DEFAULT '{}',
  use_count INTEGER NOT NULL DEFAULT 0,
  last_used_at TIMESTAMPTZ,
  creator_id UUID REFERENCES users(id),
  created_by UUID NOT NULL REFERENCES users(id),
  shared_project_ids UUID[] NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_custom_query_templates_scope
    CHECK (scope IN ('private', 'team', 'project', 'public', 'global'))
)
"""

ALTER_ADD_COLUMNS = {
    "tags": "TEXT[] NOT NULL DEFAULT '{}'",
    "use_count": "INTEGER NOT NULL DEFAULT 0",
    "last_used_at": "TIMESTAMPTZ",
    "creator_id": "UUID REFERENCES users(id)",
    "shared_project_ids": "UUID[] NOT NULL DEFAULT '{}'",
}

INDEXES_DDL = """
CREATE INDEX IF NOT EXISTS idx_cqt_scope_updated
  ON custom_query_templates (scope, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_cqt_creator_updated
  ON custom_query_templates (creator_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_cqt_tags
  ON custom_query_templates USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_cqt_shared_projects
  ON custom_query_templates USING GIN (shared_project_ids);
"""
CHECK_SQL = """
SELECT EXISTS (
  SELECT 1 FROM information_schema.tables
  WHERE table_schema = 'public' AND table_name = 'custom_query_templates'
)
"""


async def _run() -> None:
    async with engine.begin() as connection:
        await connection.execute(text(DDL))
        for column, definition in ALTER_ADD_COLUMNS.items():
            await connection.execute(text(
                f"ALTER TABLE custom_query_templates "
                f"ADD COLUMN IF NOT EXISTS {column} {definition}"
            ))
        await connection.execute(text(INDEXES_DDL))
        exists = (await connection.execute(text(CHECK_SQL))).scalar_one()
        if not exists:
            raise RuntimeError("custom_query_templates was not created")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
