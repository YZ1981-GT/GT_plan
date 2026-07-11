# Feature: custom-workpaper-formula-binding — 组①三层一致验收（V052 + ORM）
"""wp_formula 迁移 DDL 列/索引与 ORM WpFormula 一致。"""

from __future__ import annotations

import re
from pathlib import Path

from app.models.workpaper_models import WpFormula

BACKEND_ROOT = Path(__file__).resolve().parent.parent
V052 = BACKEND_ROOT / "migrations" / "V052__wp_formula.sql"
R052 = BACKEND_ROOT / "migrations" / "R052__wp_formula_rollback.sql"
# formula-management-library V100 扩展 wp_formula 的列（三类型治理）
V100 = BACKEND_ROOT / "migrations" / "V100__formula_management_library.sql"

# V052 建表基线列
_V052_BASE_COLUMNS = {
    "id",
    "project_id",
    "wp_id",
    "sheet_name",
    "target_cell",
    "expression",
    "category",
    "description",
    "created_by",
    "created_at",
    "updated_at",
}
# V100 扩展列（formula-management-library：三类型 + 最近计算时间 + 规范化引用 + 来源）
_V100_EXTENSION_COLUMNS = {
    "formula_type",
    "last_computed_at",
    "refs",
    "issue_description",
    "hint_text",
    "formula_source",
    "reference_formula_id",
}


def test_v052_r052_migration_pair_exists():
    assert V052.is_file(), "V052 migration missing"
    assert R052.is_file(), "R052 rollback missing"
    rollback = R052.read_text(encoding="utf-8")
    assert "DROP TABLE IF EXISTS wp_formula" in rollback


def test_wp_formula_orm_matches_v052_columns():
    """三层一致：ORM 列 == V052 基线 ∪ V100 扩展；各列在对应迁移 DDL 中存在。"""
    v052_ddl = V052.read_text(encoding="utf-8").lower()
    orm_cols = {c.name for c in WpFormula.__table__.columns}
    expected = _V052_BASE_COLUMNS | _V100_EXTENSION_COLUMNS
    assert orm_cols == expected, (
        f"ORM 列与 V052∪V100 期望不符，差异: {orm_cols ^ expected}"
    )
    # V052 基线列必须在 V052 DDL 中
    for col in _V052_BASE_COLUMNS:
        assert col in v052_ddl, f"V052 DDL missing column {col}"
    # V100 扩展列必须在 V100 迁移 DDL 中（三层一致：迁移 + ORM + service）
    assert V100.is_file(), "V100 formula-management-library 迁移缺失"
    v100_ddl = V100.read_text(encoding="utf-8").lower()
    for col in _V100_EXTENSION_COLUMNS:
        assert col in v100_ddl, f"V100 DDL missing column {col}"


def test_wp_formula_unique_index_in_orm_and_ddl():
    ddl = V052.read_text(encoding="utf-8")
    index_names = {idx.name for idx in WpFormula.__table__.indexes}
    assert "uq_wp_formula_wp_sheet_cell" in index_names
    assert "idx_wp_formula_project" in index_names
    assert "uq_wp_formula_wp_sheet_cell" in ddl
    assert "idx_wp_formula_project" in ddl
    assert re.search(
        r"uq_wp_formula_wp_sheet_cell[\s\S]*?wp_id\s*,\s*sheet_name\s*,\s*target_cell",
        ddl,
        re.IGNORECASE,
    )
