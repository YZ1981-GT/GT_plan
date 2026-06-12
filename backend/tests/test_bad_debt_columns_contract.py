# Feature: workpaper-bad-debt-nested-structure — Task 1.4 三层一致验收（V070 DDL == ORM）
"""V070 迁移 DDL 列与 ORM（BadDebtDetailRow）一致性契约（部分 Property 9: 层级完整性）。

纯静态：解析 V070__bad_debt_detail_rows.sql 文本，断言 CREATE TABLE 列集合与
ORM Mapped[] 列集合完全一致（含 TimestampMixin 的 created_at/updated_at，零 drift），
并校验 V070/R070 配对存在 + 幂等 IF NOT EXISTS + R070 删表删索引。不依赖 live PG。

Validates: Requirements 8.1
"""

from __future__ import annotations

import re
from pathlib import Path

from app.models.bad_debt_models import BadDebtDetailRow

BACKEND_ROOT = Path(__file__).resolve().parent.parent
V070 = BACKEND_ROOT / "migrations" / "V070__bad_debt_detail_rows.sql"
R070 = BACKEND_ROOT / "migrations" / "R070__bad_debt_detail_rows.sql"


def _parse_create_table_columns(ddl: str, table: str) -> set[str]:
    """解析 CREATE TABLE <table> ( ... ) 块内的列名集合（跳过约束/注释行）。"""
    m = re.search(
        rf"CREATE TABLE IF NOT EXISTS {table}\s*\((.*?)\n\)\s*;",
        ddl,
        re.IGNORECASE | re.DOTALL,
    )
    assert m, f"未能解析 {table} CREATE TABLE 块"
    body = m.group(1)
    cols: set[str] = set()
    for line in body.splitlines():
        line = line.strip().rstrip(",")
        if not line or line.startswith("--"):
            continue
        # 跳过表级约束行
        if re.match(r"(PRIMARY|FOREIGN|UNIQUE|CONSTRAINT|CHECK)\b", line, re.IGNORECASE):
            continue
        cols.add(line.split()[0].lower())
    return cols


def test_v070_r070_migration_pair_exists():
    assert V070.is_file(), "V070 migration missing"
    assert R070.is_file(), "R070 rollback missing"


def test_v070_idempotent_guards():
    """所有 CREATE 必须 IF NOT EXISTS（幂等可重入铁律）。"""
    ddl = V070.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS bad_debt_detail_rows" in ddl
    for stmt in re.findall(r"CREATE (?:UNIQUE )?INDEX[^\n;]*", ddl, re.IGNORECASE):
        assert "IF NOT EXISTS" in stmt.upper(), f"CREATE INDEX 缺 IF NOT EXISTS: {stmt}"


def test_v070_timestamp_columns_explicit():
    """TimestampMixin 铁律：DDL 显式写 created_at/updated_at TIMESTAMPTZ NOT NULL DEFAULT now()。"""
    ddl = V070.read_text(encoding="utf-8").lower()
    assert "created_at timestamptz not null default now()" in ddl
    assert "updated_at timestamptz not null default now()" in ddl


def test_v070_ddl_columns_match_orm():
    """bad_debt_detail_rows DDL 列集合 == ORM Mapped 列集合（无多无漏，零 drift）。"""
    ddl = V070.read_text(encoding="utf-8")
    ddl_cols = _parse_create_table_columns(ddl, "bad_debt_detail_rows")
    orm_cols = set(BadDebtDetailRow.__table__.columns.keys())
    assert ddl_cols == orm_cols, (
        "V070 DDL 列与 ORM 列不一致（schema drift）\n"
        f"  仅 DDL: {ddl_cols - orm_cols}\n"
        f"  仅 ORM: {orm_cols - ddl_cols}"
    )


def test_v070_has_13_amount_columns():
    """13 金额列 amount_b ~ amount_n 全部存在于 ORM。"""
    orm_cols = set(BadDebtDetailRow.__table__.columns.keys())
    expected = {f"amount_{c}" for c in "bcdefghijklmn"}
    assert len(expected) == 13
    assert expected <= orm_cols, f"缺金额列: {expected - orm_cols}"


def test_v070_provision_method_partial_unique_index():
    """同 wp_index 下 provision_method 唯一偏索引（WHERE provision_method IS NOT NULL）。"""
    ddl = V070.read_text(encoding="utf-8")
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_bad_debt_provision_method" in ddl
    assert re.search(
        r"uq_bad_debt_provision_method.*?WHERE provision_method IS NOT NULL",
        ddl,
        re.IGNORECASE | re.DOTALL,
    ), "缺唯一偏索引 WHERE provision_method IS NOT NULL"


def test_r070_drops_table_and_indexes():
    rollback = R070.read_text(encoding="utf-8")
    assert "DROP TABLE IF EXISTS bad_debt_detail_rows" in rollback
    assert "DROP INDEX IF EXISTS uq_bad_debt_provision_method" in rollback
    assert "DROP INDEX IF EXISTS ix_bad_debt_rows_parent" in rollback
    assert "DROP INDEX IF EXISTS ix_bad_debt_rows_wp_index" in rollback
