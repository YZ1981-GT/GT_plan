"""custom_query_templates 幂等建表 / 列补齐脚本。

用途：旧库或新环境缺 ``custom_query_templates`` 表（或缺 V051 补的 4 列）时，
在不跑全量迁移的前提下把该表补齐到与 ORM 一致。适用场景是「模板功能报表不存在」
这类单点故障的快速自愈，以及 CI 上对 DDL 契约的静态校验。

**单一真源约束（R10.5）**：本脚本的列集与索引集必须与下列三处保持一致，
不构成第二套真源：

- ORM ``app.models.custom_query_models.CustomQueryTemplate``（权威）
- ``backend/migrations/V033__sync_schema_columns.sql``（建表）
- ``backend/migrations/V051__fix_schema_drift_orm_extra.sql``（tags/use_count/creator_id/last_used_at）
- ``backend/migrations/V101__advanced_query_template_sharing.sql``（shared_project_ids + GIN）

配套守卫测试比对本脚本与 V101 / ORM 的列与索引集，任一侧漂移即打红。

**导入无副作用**：模块级只有字符串常量，不连库、不执行 DDL；``main()`` 仅在
``__main__`` 下运行（契约 ``test_script_module_importable``）。

用法::

    python backend/scripts/_ensure_custom_query_tables.py          # 检查并补齐
    python backend/scripts/_ensure_custom_query_tables.py --check  # 只检查不改库

_Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
"""

from __future__ import annotations

import argparse
import asyncio
import sys

# ─────────────────────────────────────────────────────────────────────────────
# 表存在性探测
# ─────────────────────────────────────────────────────────────────────────────
CHECK_SQL = """
SELECT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'custom_query_templates'
) AS table_exists
"""

#: 列存在性探测（用于判断是否需要 ALTER 补列）
COLUMNS_SQL = """
SELECT column_name FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'custom_query_templates'
"""

# ─────────────────────────────────────────────────────────────────────────────
# 建表（幂等）
# ─────────────────────────────────────────────────────────────────────────────
#: scope 合法取值。``global`` 为 ``public`` 的 legacy 别名，读写经
#: ``TemplateScopeAdapter.normalize`` 归一为 canonical 值后再对外呈现（R8.1），
#: 但**约束必须继续接受**它，否则历史行会在写回时违反 CHECK。
SCOPE_VALUES = ("private", "team", "public", "global")

DDL = """
CREATE TABLE IF NOT EXISTS custom_query_templates (
    id                  UUID         NOT NULL DEFAULT gen_random_uuid(),
    name                VARCHAR(255) NOT NULL DEFAULT '',
    description         TEXT,
    data_source         VARCHAR(50),
    config              JSONB        NOT NULL DEFAULT '{}',
    scope               VARCHAR(16)  NOT NULL DEFAULT 'private',
    shared_project_ids  UUID[]       NOT NULL DEFAULT '{}',
    tags                TEXT[]       NOT NULL DEFAULT '{}',
    use_count           INTEGER      NOT NULL DEFAULT 0,
    last_used_at        TIMESTAMPTZ,
    creator_id          UUID         REFERENCES users(id) ON DELETE CASCADE,
    created_by          UUID         NOT NULL REFERENCES users(id),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT pk_custom_query_templates PRIMARY KEY (id),
    CONSTRAINT ck_custom_query_templates_scope
        CHECK (scope IN ('private', 'team', 'public', 'global'))
)
"""

# ─────────────────────────────────────────────────────────────────────────────
# 旧库列补齐（幂等）
# ─────────────────────────────────────────────────────────────────────────────
#: 旧库可能缺失的列 → 补列语句。与 V051 / V101 逐列对齐。
#: 键即列名，供守卫测试直接比对列集（不必解析 SQL）。
ALTER_ADD_COLUMNS: dict[str, str] = {
    "tags": (
        "ALTER TABLE custom_query_templates "
        "ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT '{}'"
    ),
    "use_count": (
        "ALTER TABLE custom_query_templates "
        "ADD COLUMN IF NOT EXISTS use_count INTEGER NOT NULL DEFAULT 0"
    ),
    "creator_id": (
        "ALTER TABLE custom_query_templates "
        "ADD COLUMN IF NOT EXISTS creator_id UUID"
    ),
    "last_used_at": (
        "ALTER TABLE custom_query_templates "
        "ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMPTZ"
    ),
    "shared_project_ids": (
        "ALTER TABLE custom_query_templates "
        "ADD COLUMN IF NOT EXISTS shared_project_ids UUID[] NOT NULL DEFAULT '{}'"
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# 索引（幂等）
# ─────────────────────────────────────────────────────────────────────────────
#: 与 ORM ``__table_args__`` 的 idx_cqt_* 四个索引逐一对应。
#: ``idx_cqt_tags`` / ``idx_cqt_shared_projects`` 用 GIN 支持数组包含查询。
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

#: 索引名清单（供守卫测试与 ORM 交叉比对，避免解析 SQL 文本）
INDEX_NAMES = (
    "idx_cqt_scope_updated",
    "idx_cqt_creator_updated",
    "idx_cqt_tags",
    "idx_cqt_shared_projects",
)

#: DDL 声明的列集（供守卫测试与 ORM 交叉比对）
DDL_COLUMNS = (
    "id",
    "name",
    "description",
    "data_source",
    "config",
    "scope",
    "shared_project_ids",
    "tags",
    "use_count",
    "last_used_at",
    "creator_id",
    "created_by",
    "created_at",
    "updated_at",
)


async def _apply(check_only: bool) -> int:
    """执行探测与（可选）补齐，返回进程退出码。"""
    # 数据库依赖在函数内 import：保证模块导入无副作用（R10.2）
    from sqlalchemy import text

    from app.core.database import engine

    async with engine.begin() as conn:
        exists = bool((await conn.execute(text(CHECK_SQL))).scalar())
        print(f"custom_query_templates 存在: {exists}")

        if not exists:
            if check_only:
                print("[--check] 表缺失，需要建表（未执行）")
                return 1
            await conn.execute(text(DDL))
            print("已建表 custom_query_templates")

        present = {
            r[0]
            for r in (await conn.execute(text(COLUMNS_SQL))).all()
        }
        missing = [c for c in ALTER_ADD_COLUMNS if c not in present]
        if missing:
            if check_only:
                print(f"[--check] 缺失列: {', '.join(missing)}（未执行）")
                return 1
            for col in missing:
                await conn.execute(text(ALTER_ADD_COLUMNS[col]))
                print(f"已补列 {col}")
        else:
            print("列集完整")

        if not check_only:
            # INDEXES_DDL 是多语句串，逐条执行（asyncpg 不接受多语句）
            for stmt in (s.strip() for s in INDEXES_DDL.split(";")):
                if stmt:
                    await conn.execute(text(stmt))
            print(f"已确保 {len(INDEX_NAMES)} 个索引存在")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="custom_query_templates 幂等建表 / 列补齐"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只检查不改库；存在缺口时退出码 1",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_apply(check_only=args.check))


if __name__ == "__main__":
    sys.exit(main())
