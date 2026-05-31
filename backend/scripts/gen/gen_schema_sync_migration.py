"""全量 Schema 同步迁移生成器

对比 SQLAlchemy ORM Base.metadata 与实际 PG schema，生成 V033__sync_schema_columns.sql
消除所有 orm_extra 类型漂移（ORM 定义了但 DB 缺失的列/表）。

用法（从仓库根目录）：
    .venv\\Scripts\\python.exe backend/scripts/gen/gen_schema_sync_migration.py

幂等：生成的 SQL 全部使用 IF NOT EXISTS / DO 块守卫，可重复执行。
"""

import asyncio
import sys
from pathlib import Path

# 确保 backend 在 sys.path
backend_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(backend_dir))

# Import 所有 ORM 模型以注册 metadata
import app.models  # noqa: F401

_model_modules = [
    "app.models.extension_models",
    "app.models.ai_models",
    "app.models.phase10_models",
    "app.models.phase12_models",
    "app.models.phase13_models",
    "app.models.phase14_models",
    "app.models.phase15_models",
    "app.models.phase16_models",
    "app.models.report_models",
    "app.models.workpaper_models",
    "app.models.dataset_models",
    "app.models.collaboration_models",
    "app.models.staff_models",
    "app.models.consolidation_models",
    "app.models.knowledge_models",
    "app.models.custom_query_models",
    "app.models.column_mapping_models",
    "app.models.audit_log_models",
    "app.models.chain_execution",
    "app.models.handover_models",
    "app.models.rotation_models",
    "app.models.shared_config_models",
    "app.models.t_account_models",
    "app.models.template_library_models",
    "app.models.v3_refinement_models",
    "app.models.review_template_models",
    "app.models.qc_rule_models",
    "app.models.qc_rating_models",
    "app.models.qc_inspection_models",
    "app.models.qc_case_library_models",
    "app.models.enterprise_linkage_models",
    "app.models.eqcr_models",
    "app.models.related_party_models",
    "app.models.independence_models",
    "app.models.enum_dict_override_models",
    "app.models.note_trim_models",
    "app.models.note_account_mapping",
    "app.models.archive_models",
    "app.models.attachment_models",
    "app.models.procedure_models",
    "app.models.workpaper_editing_lock_models",
    "app.models.workpaper_template_version",
    "app.models.project_wp_sheet_override",
    "app.models.wp_optimization_models",
]

for mod_name in _model_modules:
    try:
        __import__(mod_name)
    except Exception as e:
        print(f"[WARN] 无法导入 {mod_name}: {e}")

# 尝试导入可能不存在的模块
for mod_name in [
    "app.models.workhour_entry_models",
    "app.models.attachment_lineage_model",
]:
    try:
        __import__(mod_name)
    except Exception:
        pass

from app.models.base import Base
from app.core.database import engine

from sqlalchemy import inspect, text
from sqlalchemy.dialects.postgresql import dialect as PGDialect


# schema_drift_detector 的 KNOWN_ALLOWLIST
KNOWN_ALLOWLIST = frozenset({
    "schema_version",
    "schema_migration_failures",
    "schema_drift_log",
    "alembic_version",
    "pg_stat_statements",
})


def _compile_col_type(col) -> str:
    """编译列类型为 PG DDL 字符串。"""
    try:
        return col.type.compile(dialect=PGDialect())
    except Exception:
        # fallback: 用 str 表示
        return str(col.type)


def _safe_default(col, col_type_str: str) -> str:
    """为 NOT NULL 列生成安全默认值。"""
    # 如果 ORM 有 server_default，直接用
    if col.server_default is not None:
        arg = col.server_default.arg
        if hasattr(arg, 'text'):
            return f" DEFAULT {arg.text}"
        return f" DEFAULT {arg}"

    # nullable 列不需要默认值
    if col.nullable:
        return ""

    # NOT NULL 列需要安全默认值
    t = col_type_str.upper()

    if col.primary_key and "UUID" in t:
        return " DEFAULT gen_random_uuid()"
    if "UUID" in t:
        # non-PK UUID NOT NULL — 也用 gen_random_uuid
        return " DEFAULT gen_random_uuid()"
    if "JSONB" in t or "JSON" in t:
        return " DEFAULT '{}'"
    if "BOOLEAN" in t or "BOOL" in t:
        return " DEFAULT false"
    if "INTEGER" in t or "BIGINT" in t or "SMALLINT" in t or "INT" in t:
        return " DEFAULT 0"
    if "FLOAT" in t or "DOUBLE" in t or "NUMERIC" in t or "DECIMAL" in t:
        return " DEFAULT 0"
    if "TIMESTAMP" in t:
        return " DEFAULT NOW()"
    if "TEXT" in t or "VARCHAR" in t or "CHARACTER" in t:
        return " DEFAULT ''"
    if "ARRAY" in t:
        return " DEFAULT '{}'"

    # 未知类型，尝试 nullable 兜底
    return " DEFAULT ''"


def _get_enum_create_sql(col) -> list[str]:
    """如果列类型是 PG ENUM，生成 CREATE TYPE + ADD VALUE 语句。"""
    from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
    from sqlalchemy import Enum as SA_Enum

    stmts = []
    col_type = col.type

    # 检查是否是 PG ENUM 或 SA Enum
    enum_values = None
    enum_name = None

    if isinstance(col_type, PG_ENUM):
        enum_values = col_type.enums
        enum_name = col_type.name
    elif isinstance(col_type, SA_Enum):
        enum_values = col_type.enums
        enum_name = col_type.name

    if enum_values and enum_name:
        # 创建 enum type（如果不存在）
        values_str = ", ".join(f"'{v}'" for v in enum_values)
        stmts.append(
            f"DO $$ BEGIN\n"
            f"    CREATE TYPE {enum_name} AS ENUM ({values_str});\n"
            f"EXCEPTION WHEN duplicate_object THEN NULL;\n"
            f"END $$;"
        )
        # 确保所有值存在
        for val in enum_values:
            stmts.append(
                f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{val}';"
            )

    return stmts


async def main():
    """主流程：对比 ORM vs DB，生成迁移 SQL。"""
    print("[gen_schema_sync] 开始对比 ORM metadata vs PG schema...")

    statements: list[str] = []
    enum_statements: list[str] = []

    async with engine.begin() as conn:
        # 获取 DB 中实际存在的表
        result = await conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        ))
        existing_tables = {row[0] for row in result.fetchall()}

        # 获取 DB 中每个表的列
        result = await conn.execute(text(
            "SELECT table_name, column_name "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public'"
        ))
        db_columns: dict[str, set[str]] = {}
        for row in result.fetchall():
            table = row[0]
            col = row[1]
            if table not in db_columns:
                db_columns[table] = set()
            db_columns[table].add(col)

        # 获取 DB 中已有的 enum 类型
        result = await conn.execute(text(
            "SELECT t.typname, e.enumlabel "
            "FROM pg_type t JOIN pg_enum e ON t.oid = e.enumtypid"
        ))
        db_enums: dict[str, set[str]] = {}
        for row in result.fetchall():
            name = row[0]
            val = row[1]
            if name not in db_enums:
                db_enums[name] = set()
            db_enums[name].add(val)

    # 遍历 ORM metadata
    missing_tables = []
    missing_columns = []

    for table_name, table in sorted(Base.metadata.tables.items()):
        if table_name in KNOWN_ALLOWLIST:
            continue

        if table_name not in existing_tables:
            missing_tables.append(table_name)
            continue

        # 表存在，检查列
        existing_cols = db_columns.get(table_name, set())
        for col in table.columns:
            if col.name not in existing_cols:
                missing_columns.append((table_name, col))

    # 生成缺失表的 CREATE TABLE
    if missing_tables:
        statements.append("-- ============================================")
        statements.append("-- 缺失表（ORM 定义但 DB 不存在）")
        statements.append("-- ============================================")
        statements.append("")

        for table_name in sorted(missing_tables):
            table = Base.metadata.tables[table_name]
            statements.append(f"-- Table: {table_name}")

            # 收集列定义
            col_defs = []
            pk_cols = []
            for col in table.columns:
                # 处理 enum 类型
                enum_stmts = _get_enum_create_sql(col)
                enum_statements.extend(enum_stmts)

                col_type_str = _compile_col_type(col)
                nullable = "" if col.nullable else " NOT NULL"
                default = _safe_default(col, col_type_str)

                col_defs.append(f"    {col.name} {col_type_str}{nullable}{default}")

                if col.primary_key:
                    pk_cols.append(col.name)

            # 构建 CREATE TABLE
            parts = ",\n".join(col_defs)
            pk_clause = ""
            if pk_cols:
                pk_clause = f",\n    PRIMARY KEY ({', '.join(pk_cols)})"

            stmt = (
                f"CREATE TABLE IF NOT EXISTS {table_name} (\n"
                f"{parts}{pk_clause}\n"
                f");"
            )
            statements.append(stmt)
            statements.append("")

    # 生成缺失列的 ALTER TABLE
    if missing_columns:
        statements.append("-- ============================================")
        statements.append("-- 缺失列（ORM 定义但 DB 不存在）")
        statements.append("-- ============================================")
        statements.append("")

        current_table = None
        for table_name, col in sorted(missing_columns, key=lambda x: (x[0], x[1].name)):
            if table_name != current_table:
                if current_table is not None:
                    statements.append("")
                statements.append(f"-- Table: {table_name}")
                current_table = table_name

            # 处理 enum 类型
            enum_stmts = _get_enum_create_sql(col)
            enum_statements.extend(enum_stmts)

            col_type_str = _compile_col_type(col)
            nullable = "" if col.nullable else " NOT NULL"
            default = _safe_default(col, col_type_str)

            stmt = (
                f"ALTER TABLE {table_name} "
                f"ADD COLUMN IF NOT EXISTS {col.name} {col_type_str}{nullable}{default};"
            )
            statements.append(stmt)

    # 组装最终 SQL
    output_lines: list[str] = []
    output_lines.append("-- V033: 全量 schema 同步（消除 ORM-vs-DB 列级漂移）")
    output_lines.append("-- Auto-generated by gen_schema_sync_migration.py")
    output_lines.append("-- 所有语句幂等，可重复执行")
    output_lines.append("")

    # Enum 类型先于表/列创建
    if enum_statements:
        # 去重
        seen = set()
        unique_enum_stmts = []
        for s in enum_statements:
            if s not in seen:
                seen.add(s)
                unique_enum_stmts.append(s)

        output_lines.append("-- ============================================")
        output_lines.append("-- Enum 类型创建/补值")
        output_lines.append("-- ============================================")
        output_lines.append("")
        output_lines.extend(unique_enum_stmts)
        output_lines.append("")

    output_lines.extend(statements)

    # 写入文件
    output_path = backend_dir / "migrations" / "V033__sync_schema_columns.sql"
    output_path.write_text("\n".join(output_lines), encoding="utf-8")

    print(f"[gen_schema_sync] 完成！")
    print(f"  缺失表: {len(missing_tables)}")
    print(f"  缺失列: {len(missing_columns)}")
    print(f"  Enum 语句: {len(enum_statements)}")
    print(f"  输出: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
