"""迁移幂等 + ORM 一致性测试（advanced-query-module Task 1.4）

覆盖 design.md §Testing Strategy「迁移测试：V101/V102 幂等性、ORM 与 DDL 列一致
（防 schema 漂移）」：

- V101：``custom_query_templates.shared_project_ids`` 列建成，且以幂等守护
  （``DO $$ + information_schema`` + ``ADD COLUMN`` + ``CREATE INDEX IF NOT EXISTS``）
  确保重复执行不报错。
- V102：``advanced_query_writeback`` 表建成（``CREATE TABLE IF NOT EXISTS``），且索引
  以表存在性守护后 ``CREATE INDEX IF NOT EXISTS``。
- ORM 一致性：``CustomQueryTemplate`` 声明含 ``shared_project_ids``；
  ``AdvancedQueryWriteback`` 声明的列集合与 V102 DDL 列集合逐列一致。

本测试为**纯测试**（非 PBT）：无 live DB 时通过解析 V101/V102 SQL 文本 + 对比 ORM
``__table__.columns`` 完成，与既有迁移测试（如 test_migration_v017.py）风格一致。

Requirements: 3.1, 13.3
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.models.custom_query_models import (
    AdvancedQueryWriteback,
    CustomQueryTemplate,
)

_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
_V101 = _MIGRATIONS_DIR / "V101__advanced_query_template_sharing.sql"
_V102 = _MIGRATIONS_DIR / "V102__advanced_query_writeback_addr_id.sql"


# ─── 辅助：从 CREATE TABLE 中解析列名集合 ────────────────────────────────────


def _strip_sql_comments(sql: str) -> str:
    """去除每行 ``--`` 之后的注释（避免注释中的 "CREATE INDEX" / 逗号干扰解析）。"""
    lines = []
    for line in sql.splitlines():
        idx = line.find("--")
        lines.append(line[:idx] if idx >= 0 else line)
    return "\n".join(lines)


def _parse_create_table_columns(sql: str, table_name: str) -> set[str]:
    """从 ``CREATE TABLE ... table_name ( ... )`` 提取顶层列名集合。

    仅解析列定义行的首标识符（跳过 PRIMARY/FOREIGN/CONSTRAINT/CHECK/UNIQUE 约束行）。
    先剥离 ``--`` 注释，避免注释文本被误当列定义。
    """
    sql = _strip_sql_comments(sql)
    m = re.search(
        rf"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+{re.escape(table_name)}\s*\(",
        sql,
        re.IGNORECASE,
    )
    assert m, f"CREATE TABLE {table_name} not found"
    start = m.end()  # 位于开括号之后
    # 匹配到与开括号配对的闭括号
    depth = 1
    i = start
    while i < len(sql) and depth > 0:
        if sql[i] == "(":
            depth += 1
        elif sql[i] == ")":
            depth -= 1
        i += 1
    body = sql[start : i - 1]

    # 顶层逗号切分（本 DDL 无嵌套括号列表，简单切分即可）
    columns: set[str] = set()
    reserved = {
        "primary",
        "foreign",
        "constraint",
        "check",
        "unique",
        "key",
    }
    for part in body.split(","):
        part = part.strip()
        if not part:
            continue
        first = part.split()[0].lower()
        if first in reserved:
            continue
        if re.match(r"^[a-z_][a-z0-9_]*$", first):
            columns.add(first)
    return columns


@pytest.fixture(scope="module")
def v101_sql() -> str:
    return _V101.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def v102_sql() -> str:
    return _V102.read_text(encoding="utf-8")


# ─── V101：模板分享列建成 + 幂等（R13.3）────────────────────────────────────


class TestV101TemplateSharingColumn:
    def test_migration_file_exists(self):
        assert _V101.exists()

    def test_adds_shared_project_ids_column(self, v101_sql):
        assert "shared_project_ids" in v101_sql
        assert "custom_query_templates" in v101_sql
        assert "UUID[]" in v101_sql

    def test_column_add_guarded_by_information_schema(self, v101_sql):
        """列补齐用 DO $$ + information_schema.columns 检测（幂等，不裸 ADD 报错）。"""
        assert "information_schema.columns" in v101_sql
        assert "DO $$" in v101_sql
        assert re.search(r"ALTER TABLE\s+custom_query_templates", v101_sql)

    def test_gin_index_if_not_exists(self, v101_sql):
        """列存在性确认后再 CREATE INDEX IF NOT EXISTS（非裸 CREATE INDEX）。"""
        assert "idx_cqt_shared_projects" in v101_sql
        assert "CREATE INDEX IF NOT EXISTS idx_cqt_shared_projects" in v101_sql
        assert "USING gin" in v101_sql

    def test_all_indexes_idempotent(self, v101_sql):
        src = _strip_sql_comments(v101_sql)
        created = re.findall(r"CREATE INDEX\b", src)
        created_ine = re.findall(r"CREATE INDEX IF NOT EXISTS", src)
        assert len(created) == len(created_ine), "所有 CREATE INDEX 必须 IF NOT EXISTS"


# ─── V102：回写身份表建成 + 幂等（R3.1 / R14.3）─────────────────────────────

# V102 DDL 期望列集合（design Data Models §2）
_V102_EXPECTED_COLUMNS = {
    "id",
    "project_id",
    "addr_id",
    "wp_id",
    "old_value",
    "new_value",
    "operator_id",
    "result",
    "created_at",
}


class TestV102WritebackTable:
    def test_migration_file_exists(self):
        assert _V102.exists()

    def test_creates_advanced_query_writeback_table(self, v102_sql):
        assert "CREATE TABLE IF NOT EXISTS advanced_query_writeback" in v102_sql

    def test_ddl_column_set(self, v102_sql):
        cols = _parse_create_table_columns(v102_sql, "advanced_query_writeback")
        assert cols == _V102_EXPECTED_COLUMNS, (
            f"V102 DDL 列集合与期望不一致：多={cols - _V102_EXPECTED_COLUMNS}, "
            f"少={_V102_EXPECTED_COLUMNS - cols}"
        )

    def test_addr_id_is_text_not_null(self, v102_sql):
        assert re.search(r"addr_id\s+TEXT\s+NOT NULL", v102_sql)

    def test_indexes_guarded_by_table_existence(self, v102_sql):
        """索引在表存在性 information_schema.tables 守护后再 CREATE IF NOT EXISTS。"""
        assert "information_schema.tables" in v102_sql
        assert "CREATE INDEX IF NOT EXISTS idx_aqw_addr_id" in v102_sql
        assert "CREATE INDEX IF NOT EXISTS idx_aqw_project" in v102_sql

    def test_all_creates_idempotent(self, v102_sql):
        src = _strip_sql_comments(v102_sql)
        tables = re.findall(r"CREATE TABLE\b", src)
        tables_ine = re.findall(r"CREATE TABLE IF NOT EXISTS", src)
        assert len(tables) == len(tables_ine), "所有 CREATE TABLE 必须 IF NOT EXISTS"
        idx = re.findall(r"CREATE INDEX\b", src)
        idx_ine = re.findall(r"CREATE INDEX IF NOT EXISTS", src)
        assert len(idx) == len(idx_ine), "所有 CREATE INDEX 必须 IF NOT EXISTS"


# ─── ORM ↔ DDL 一致性（防 schema 漂移）──────────────────────────────────────


class TestOrmDdlConsistency:
    def test_template_orm_has_shared_project_ids(self):
        """CustomQueryTemplate ORM 声明含 V101 新增列（R13.3）。"""
        cols = set(CustomQueryTemplate.__table__.columns.keys())
        assert "shared_project_ids" in cols

    def test_writeback_orm_columns_match_v102_ddl(self, v102_sql):
        """AdvancedQueryWriteback ORM 声明列集合与 V102 DDL 列集合逐列一致（R3.1）。"""
        orm_cols = set(AdvancedQueryWriteback.__table__.columns.keys())
        ddl_cols = _parse_create_table_columns(v102_sql, "advanced_query_writeback")
        assert orm_cols == ddl_cols, (
            f"ORM 与 DDL 列漂移：ORM 多={orm_cols - ddl_cols}, "
            f"DDL 多={ddl_cols - orm_cols}"
        )

    def test_writeback_orm_tablename(self):
        assert AdvancedQueryWriteback.__tablename__ == "advanced_query_writeback"

    def test_writeback_orm_has_expected_columns(self):
        orm_cols = set(AdvancedQueryWriteback.__table__.columns.keys())
        assert orm_cols == _V102_EXPECTED_COLUMNS
