# Feature: custom-workpaper-formula-binding — 组①三层一致验收（V052 + ORM）
"""wp_formula 迁移 DDL 列/索引与 ORM WpFormula 一致。"""

from __future__ import annotations

import re
from pathlib import Path

from app.models.workpaper_models import WpFormula

BACKEND_ROOT = Path(__file__).resolve().parent.parent
V052 = BACKEND_ROOT / "migrations" / "V052__wp_formula.sql"
R052 = BACKEND_ROOT / "migrations" / "R052__wp_formula_rollback.sql"


def test_v052_r052_migration_pair_exists():
    assert V052.is_file(), "V052 migration missing"
    assert R052.is_file(), "R052 rollback missing"
    rollback = R052.read_text(encoding="utf-8")
    assert "DROP TABLE IF EXISTS wp_formula" in rollback


def test_wp_formula_orm_matches_v052_columns():
    ddl = V052.read_text(encoding="utf-8").lower()
    orm_cols = {c.name for c in WpFormula.__table__.columns}
    expected = {
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
    assert orm_cols == expected
    for col in expected:
        assert col in ddl, f"V052 DDL missing column {col}"


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
