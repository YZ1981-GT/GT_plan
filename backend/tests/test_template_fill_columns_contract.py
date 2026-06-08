# Feature: audit-report-template-integration — Task 5.3 三层一致验收（V066 DDL == ORM）
"""V066 迁移 DDL 列与 ORM（Project / AuditReport / FillPreviewSession）一致性契约。

纯静态：解析 V066__template_fill_columns.sql 文本，断言新增列与 ORM Mapped[] 列吻合，
并校验 V066/R066 配对存在 + R066 删表/删列。不依赖 live PG。
"""

from __future__ import annotations

import re
from pathlib import Path

from app.models.core import Project
from app.models.report_models import AuditReport, FillPreviewSession

BACKEND_ROOT = Path(__file__).resolve().parent.parent
V066 = BACKEND_ROOT / "migrations" / "V066__template_fill_columns.sql"
R066 = BACKEND_ROOT / "migrations" / "R066__rollback.sql"


def test_v066_r066_migration_pair_exists():
    assert V066.is_file(), "V066 migration missing"
    assert R066.is_file(), "R066 rollback missing"


def test_v066_idempotent_guards():
    """所有 CREATE/ALTER 必须 IF NOT EXISTS（幂等可重入铁律）。"""
    ddl = V066.read_text(encoding="utf-8")
    for stmt in re.findall(r"ADD COLUMN[^\n;]*", ddl, re.IGNORECASE):
        assert "IF NOT EXISTS" in stmt.upper(), f"ADD COLUMN 缺 IF NOT EXISTS: {stmt}"
    assert "CREATE TABLE IF NOT EXISTS fill_preview_sessions" in ddl
    for stmt in re.findall(r"CREATE INDEX[^\n;]*", ddl, re.IGNORECASE):
        assert "IF NOT EXISTS" in stmt.upper(), f"CREATE INDEX 缺 IF NOT EXISTS: {stmt}"


def test_projects_company_subtype_in_ddl_and_orm():
    ddl = V066.read_text(encoding="utf-8").lower()
    assert "alter table projects add column if not exists company_subtype" in ddl
    assert "company_subtype" in Project.__table__.columns


def test_audit_report_new_columns_in_ddl_and_orm():
    ddl = V066.read_text(encoding="utf-8").lower()
    orm_cols = set(AuditReport.__table__.columns.keys())
    for col in ("company_subtype", "template_variant", "template_version"):
        assert f"audit_report add column if not exists {col}" in ddl, (
            f"V066 DDL 缺 audit_report.{col}"
        )
        assert col in orm_cols, f"AuditReport ORM 缺 {col}"
    # template_variant 默认 'simple'
    assert "template_variant varchar(10) default 'simple'" in ddl


def test_fill_preview_sessions_ddl_matches_orm():
    """fill_preview_sessions DDL 列集合 == ORM 列集合（无多无漏）。"""
    ddl = V066.read_text(encoding="utf-8")
    # 提取 CREATE TABLE fill_preview_sessions ( ... ) 内的列定义
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS fill_preview_sessions\s*\((.*?)\n\)\s*;",
        ddl,
        re.IGNORECASE | re.DOTALL,
    )
    assert m, "未能解析 fill_preview_sessions CREATE TABLE 块"
    body = m.group(1)
    ddl_cols: set[str] = set()
    for line in body.splitlines():
        line = line.strip().rstrip(",")
        if not line or line.startswith("--"):
            continue
        # 跳过表级约束行
        if re.match(r"(PRIMARY|FOREIGN|UNIQUE|CONSTRAINT|CHECK)\b", line, re.IGNORECASE):
            continue
        col = line.split()[0].lower()
        ddl_cols.add(col)

    orm_cols = set(FillPreviewSession.__table__.columns.keys())
    assert ddl_cols == orm_cols, (
        f"DDL 列与 ORM 列不一致\n  仅 DDL: {ddl_cols - orm_cols}\n  仅 ORM: {orm_cols - ddl_cols}"
    )


def test_fill_preview_sessions_timestamp_columns_explicit():
    """TimestampMixin 风格列必须在 DDL 显式写 TIMESTAMPTZ NOT NULL DEFAULT now()。"""
    ddl = V066.read_text(encoding="utf-8").lower()
    assert "created_at timestamptz not null default now()" in ddl
    assert "updated_at timestamptz not null default now()" in ddl


def test_r066_drops_table_and_columns():
    rollback = R066.read_text(encoding="utf-8")
    assert "DROP TABLE IF EXISTS fill_preview_sessions" in rollback
    assert "DROP COLUMN IF EXISTS company_subtype" in rollback
    assert "DROP COLUMN IF EXISTS template_variant" in rollback
    assert "DROP COLUMN IF EXISTS template_version" in rollback
