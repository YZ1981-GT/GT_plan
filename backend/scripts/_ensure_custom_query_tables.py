"""一次性脚本：确保 custom_query_templates 表存在（Req 15 AC1 / advanced-query-enhancements-p1p2）

历史背景：
- 早期 init_tables.py 扫描 app/models/*.py 时会触发 ORM 注册
- 但部分 DB 是早期初始化的，缺这张表 → /api/custom-query/templates 端点 500
- alembic_version 表也未建立，无法走 migration 路径

本脚本：
- 幂等：已存在则跳过
- 含完整字段 + FK + 3 个索引（scope+updated_at / creator+updated_at / tags GIN）
- 用完即可删（一次性脚本，下划线前缀标识）

使用：
    python backend/scripts/_ensure_custom_query_tables.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/audit_platform",
)
DB_URL = DB_URL.replace("+asyncpg", "+psycopg2")


DDL = """\
CREATE TABLE IF NOT EXISTS custom_query_templates (
    id           UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    name         VARCHAR(255)   NOT NULL,
    description  TEXT,
    scope        VARCHAR(16)    NOT NULL DEFAULT 'private',
    creator_id   UUID           NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    data_source  VARCHAR(50),
    config       JSONB          NOT NULL DEFAULT '{}'::jsonb,
    tags         TEXT[]         NOT NULL DEFAULT '{}',
    use_count    INTEGER        NOT NULL DEFAULT 0,
    last_used_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ    NOT NULL DEFAULT now(),
    created_by   UUID           REFERENCES users(id),
    CONSTRAINT ck_custom_query_templates_scope
        CHECK (scope IN ('private','team','public','global'))
);
"""

INDEXES_DDL = """\
CREATE INDEX IF NOT EXISTS idx_cqt_scope_updated
    ON custom_query_templates(scope, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_cqt_creator_updated
    ON custom_query_templates(creator_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_cqt_tags
    ON custom_query_templates USING GIN (tags);
"""

LEGACY_INDEXES_DDL = """\
CREATE INDEX IF NOT EXISTS idx_custom_query_templates_scope
    ON custom_query_templates(scope, updated_at);
CREATE INDEX IF NOT EXISTS idx_custom_query_templates_creator
    ON custom_query_templates(created_by, updated_at);
"""

CHECK_SQL = (
    "SELECT EXISTS ("
    "SELECT 1 FROM information_schema.tables "
    "WHERE table_schema='public' AND table_name='custom_query_templates'"
    ")"
)

CHECK_COLUMNS_SQL = (
    "SELECT column_name FROM information_schema.columns "
    "WHERE table_schema='public' AND table_name='custom_query_templates'"
)

ALTER_ADD_COLUMNS = {
    "tags": (
        "ALTER TABLE custom_query_templates "
        "ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT '{}'"
    ),
    "use_count": (
        "ALTER TABLE custom_query_templates "
        "ADD COLUMN IF NOT EXISTS use_count INTEGER NOT NULL DEFAULT 0"
    ),
    "last_used_at": (
        "ALTER TABLE custom_query_templates "
        "ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMPTZ"
    ),
    "creator_id": (
        "ALTER TABLE custom_query_templates "
        "ADD COLUMN IF NOT EXISTS creator_id UUID REFERENCES users(id) ON DELETE CASCADE"
    ),
}


def main():
    engine = create_engine(DB_URL)
    with engine.begin() as conn:
        exists = conn.execute(text(CHECK_SQL)).scalar()
        if not exists:
            conn.execute(text(DDL))
            conn.execute(text(INDEXES_DDL))
            conn.execute(text(LEGACY_INDEXES_DDL))
            print(
                "\u2713 custom_query_templates \u8868\u5df2\u521b\u5efa"
                "\uff08\u542b 3 \u4e2a\u7d22\u5f15 + scope CHECK \u7ea6\u675f\uff09"
            )
        else:
            result = conn.execute(text(CHECK_COLUMNS_SQL))
            existing_cols = {row[0] for row in result}

            added = []
            for col, ddl in ALTER_ADD_COLUMNS.items():
                if col not in existing_cols and ddl:
                    conn.execute(text(ddl))
                    added.append(col)

            if "creator_id" in added and "created_by" in existing_cols:
                conn.execute(text(
                    "UPDATE custom_query_templates "
                    "SET creator_id = created_by "
                    "WHERE creator_id IS NULL AND created_by IS NOT NULL"
                ))

            conn.execute(text(INDEXES_DDL))

            if added:
                print(
                    f"\u2713 custom_query_templates \u8868\u5df2\u5b58\u5728\uff0c"
                    f"\u8865\u5145\u5217: {', '.join(added)} + \u7d22\u5f15"
                )
            else:
                print(
                    "\u2713 custom_query_templates \u8868\u5df2\u5b58\u5728"
                    "\u4e14\u5b57\u6bb5\u5b8c\u6574\uff0c\u8df3\u8fc7"
                )

    engine.dispose()


if __name__ == "__main__":
    main()
