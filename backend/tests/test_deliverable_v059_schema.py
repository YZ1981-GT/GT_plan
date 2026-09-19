"""V059 deliverable-center 三层一致：ORM 列与迁移 DDL 对齐"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect

from app.models.phase13_models import WordExportTask, WordExportTaskVersion
from app.models.report_models import AuditReport

REPO_ROOT = Path(__file__).resolve().parents[1]
V059_SQL = REPO_ROOT / "migrations" / "V059__deliverable_center.sql"

V059_WET_COLUMNS = {
    "file_size", "html_path", "report_body_json", "opinion_type", "company_type",
    "doc_subtype", "is_pie", "source_snapshot_refs", "selected_sections",
    "report_date", "prior_period_info", "approval_by", "approval_at",
    "reject_reason", "signed_by", "signed_at", "sign_type", "archived_at",
}

V059_WETV_COLUMNS = {
    "html_path", "file_size", "file_hash", "hash_chain_entry_id",
    "source_snapshot_refs", "selected_sections", "created_via",
}

V059_AR_COLUMNS = {"report_body_json", "is_pie", "prior_period_info"}


def _orm_columns(model) -> set[str]:
    return {c.key for c in inspect(model).columns}


def test_v059_migration_file_exists():
    assert V059_SQL.exists(), "V059 迁移文件缺失"


def test_v059_sql_contains_wet_columns():
    sql = V059_SQL.read_text(encoding="utf-8")
    for col in V059_WET_COLUMNS:
        assert col in sql, f"V059 SQL 缺少 word_export_task.{col}"


def test_word_export_task_orm_has_v059_columns():
    orm_cols = _orm_columns(WordExportTask)
    missing = V059_WET_COLUMNS - orm_cols
    assert not missing, f"WordExportTask ORM 缺少列: {missing}"


def test_word_export_task_versions_orm_has_v059_columns():
    orm_cols = _orm_columns(WordExportTaskVersion)
    missing = V059_WETV_COLUMNS - orm_cols
    assert not missing, f"WordExportTaskVersion ORM 缺少列: {missing}"


def test_audit_report_orm_has_v059_columns():
    orm_cols = _orm_columns(AuditReport)
    missing = V059_AR_COLUMNS - orm_cols
    assert not missing, f"AuditReport ORM 缺少列: {missing}"


# ---------------------------------------------------------------------------
# 子任务 1.3：DDL 列集合 == ORM 列集合 双向契约（解析 V059 DDL，而非子串包含）
#
# 说明：`test_raw_sql_column_contract.py` 是 pg_only（sqlglot 解析裸 SQL 引用 +
# 连真实 PG），无 live PG 时被 skip，不适合承载静态 DDL↔ORM 等价契约。故将
# 「DDL 列集合 == ORM 列集合」契约落在本 V059 schema 测试文件（无需 live PG，
# 实际执行），更贴合三层一致铁律的守护目的。
# ---------------------------------------------------------------------------

import re


def _parse_v059_add_columns() -> dict[str, set[str]]:
    """解析 V059 SQL，按表名提取 `ADD COLUMN IF NOT EXISTS <col>` 的列集合。"""
    sql = V059_SQL.read_text(encoding="utf-8")
    pattern = re.compile(
        r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+(\w+)",
        re.IGNORECASE,
    )
    result: dict[str, set[str]] = {}
    for table, col in pattern.findall(sql):
        result.setdefault(table.lower(), set()).add(col.lower())
    return result


def test_v059_ddl_columns_equal_orm_new_columns():
    """三层一致契约：V059 DDL 新增列集合 == ORM 模型对应新增列集合（双向相等）。

    既防 DDL 改了 ORM 没跟（DDL - ORM 非空），也防 ORM 加了 DDL 漏写
    （声明的 V059 列集合 - DDL 非空）。declared 集合为契约锚点。
    """
    ddl = _parse_v059_add_columns()

    cases = [
        ("word_export_task", V059_WET_COLUMNS, WordExportTask),
        ("word_export_task_versions", V059_WETV_COLUMNS, WordExportTaskVersion),
        ("audit_report", V059_AR_COLUMNS, AuditReport),
    ]

    for table_name, declared_cols, model in cases:
        ddl_cols = ddl.get(table_name, set())
        orm_cols = _orm_columns(model)

        # 1) DDL 解析出的新列必须与声明的契约锚点集合严格相等（防 DDL 漂移）
        assert ddl_cols == declared_cols, (
            f"{table_name}: V059 DDL 列集合与契约声明不一致\n"
            f"  仅 DDL 有: {ddl_cols - declared_cols}\n"
            f"  仅声明有: {declared_cols - ddl_cols}"
        )

        # 2) DDL 新列必须全部存在于 ORM（DDL ⊆ ORM，防 ORM 漏跟）
        missing_in_orm = ddl_cols - orm_cols
        assert not missing_in_orm, (
            f"{table_name}: DDL 有列但 ORM 缺失: {missing_in_orm}"
        )
