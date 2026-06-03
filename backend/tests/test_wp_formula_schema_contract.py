# Feature: custom-workpaper-formula-binding — 组⑧任务 12.1
"""wp_formula 三层一致 + schema 契约守护（ORM ∪ V052 迁移 ∪ service/router）。"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from tests.test_raw_sql_schema_contract import (
    MIGRATIONS_DIR,
    REPO_ROOT,
    _collect_migration_tables,
    _collect_orm_tables,
)

BACKEND_ROOT = Path(__file__).resolve().parent.parent
V052 = BACKEND_ROOT / "migrations" / "V052__wp_formula.sql"
R052 = BACKEND_ROOT / "migrations" / "R052__wp_formula_rollback.sql"

WP_FORMULA_COLUMNS = {
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


def test_wp_formula_in_orm_and_migration_sets():
    """wp_formula 必须同时出现在 ORM metadata 与 V*.sql 迁移建表集合中。"""
    orm_tables = _collect_orm_tables()
    mig_tables = _collect_migration_tables()
    assert "wp_formula" in orm_tables, "ORM 未注册 WpFormula（import models 失败？）"
    assert "wp_formula" in mig_tables, "V052 迁移未扫描到 CREATE TABLE wp_formula"


def test_v052_migration_pair_unique_version():
    """V052 不撞号；R052 配对回滚。"""
    v052_files = sorted(MIGRATIONS_DIR.glob("V052*.sql"))
    assert len(v052_files) == 1, f"V052 迁移撞号或缺失: {[f.name for f in v052_files]}"
    assert v052_files[0].name == "V052__wp_formula.sql"
    assert R052.is_file()
    assert "DROP TABLE IF EXISTS wp_formula" in R052.read_text(encoding="utf-8")


def test_wp_formula_service_and_router_registered():
    """三层第三层 service + router_registry 注册（缺一即前端 404）。"""
    svc = importlib.import_module("app.services.wp_formula_service")
    assert hasattr(svc, "wp_formula_service")
    assert hasattr(svc.wp_formula_service, "save")
    assert hasattr(svc.wp_formula_service, "list_by_wp")
    assert hasattr(svc.wp_formula_service, "delete")

    reg = importlib.import_module("app.router_registry.workpaper")
    source = Path(reg.__file__).read_text(encoding="utf-8")
    assert "wp_formula" in source


def test_wp_formula_raw_sql_refs_known_if_any():
    """若裸 SQL 引用 wp_formula，必须落在 schema 契约 known 集合内。"""
    from tests.test_raw_sql_schema_contract import _collect_referenced_tables

    known = _collect_orm_tables() | _collect_migration_tables()
    refs = _collect_referenced_tables()
    if "wp_formula" not in refs:
        pytest.skip("当前无裸 SQL 直接引用 wp_formula（ORM 路径为主）")
    assert "wp_formula" in known


@pytest.mark.pg_only
def test_wp_formula_columns_exist_in_live_pg():
    """列级契约（pg_only）：真实 PG 已应用 V052 时 wp_formula 列齐全。"""
    from tests.test_raw_sql_column_contract import _load_pg_schema_sync

    schema = _load_pg_schema_sync()
    assert "wp_formula" in schema, (
        "PG 无 wp_formula 表 — 请在测试库执行 V052__wp_formula.sql"
    )
    missing = WP_FORMULA_COLUMNS - schema["wp_formula"]
    assert not missing, f"wp_formula 缺列: {sorted(missing)}"
