"""一次性脚本：确保 custom_query_templates 表存在（Req 15 AC1 / advanced-query-enhancements-p1p2）

历史背景：
- 早期 init_tables.py 扫描 app/models/*.py 时会触发 ORM 注册
- 但部分 DB 是早期初始化的，缺这张表 → /api/custom-query/templates 端点 500
- alembic_version 表也未建立，无法走 migration 路径

本脚本：
- 幂等：已存在则跳过
- 含完整字段 + FK + 2 个复合索引（与 ORM 模型一致）
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
DB_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/audit_platform")
DB_URL = DB_URL.replace("+asyncpg", "+psycopg2")

DDL = """
CREATE TABLE IF NOT EXISTS custom_query_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    description TEXT,
    data_source VARCHAR(50) NOT NULL,
    config JSONB NOT NULL,
    scope VARCHAR(20) NOT NULL DEFAULT 'private',
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_custom_query_templates_scope ON custom_query_templates(scope, updated_at);
CREATE INDEX IF NOT EXISTS idx_custom_query_templates_creator ON custom_query_templates(created_by, updated_at);
"""

CHECK_SQL = "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='custom_query_templates')"

engine = create_engine(DB_URL)
with engine.begin() as conn:
    exists = conn.execute(text(CHECK_SQL)).scalar()
    if exists:
        print("✓ custom_query_templates 表已存在，跳过")
    else:
        conn.execute(text(DDL))
        print("✓ custom_query_templates 表已创建（含 2 个复合索引）")

engine.dispose()
