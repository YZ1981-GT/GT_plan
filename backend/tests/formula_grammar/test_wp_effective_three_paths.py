"""三路径同表达式 + 直写守卫 + 旧保存路径同步跟踪（ADR-FGR-08）。

Validates: Requirements 5 — 底稿公式全轨读有效定义。
"""
from __future__ import annotations

import ast
import re
import uuid
from pathlib import Path

import pytest

BACKEND_APP = Path(__file__).resolve().parents[2] / "app"

# ═══════════════════════════════════════════════════════════════════════════════
# 1. 三路径同表达式：coordinator / prefill / Tier A 读同一有效定义
# ═══════════════════════════════════════════════════════════════════════════════


class TestCoordinatorReadsEffective:
    """coordinator._load_formulas 经 effective_project_formulas 读有效定义（ADR-FGR-08）。"""

    def test_coordinator_calls_effective_project_formulas(self) -> None:
        """_load_formulas 的源码必须包含 effective_project_formulas 调用。"""
        src = (BACKEND_APP / "services" / "formula_runtime" / "coordinator.py").read_text("utf-8")
        tree = ast.parse(src)
        fn = next(
            (n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "_load_formulas"),
            None,
        )
        assert fn is not None, "_load_formulas 不存在"
        calls = {
            node.func.id
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        } | {
            node.func.attr
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "effective_project_formulas" in calls, (
            "_load_formulas 没有调用 effective_project_formulas —— coordinator 仍在直接查 WpFormula"
        )

    def test_coordinator_does_not_directly_query_wp_formula(self) -> None:
        """_load_formulas 不得直接 select(WpFormula)。"""
        src = (BACKEND_APP / "services" / "formula_runtime" / "coordinator.py").read_text("utf-8")
        tree = ast.parse(src)
        fn = next(
            (n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "_load_formulas"),
            None,
        )
        assert fn is not None
        names = {node.id for node in ast.walk(fn) if isinstance(node, ast.Name)}
        assert "WpFormula" not in names, (
            "_load_formulas 仍引用 WpFormula —— 应改为 effective_project_formulas"
        )


class TestTierAReadsEffective:
    """Tier A resolve_effective 经 effective_cell_formulas 读有效定义。"""

    def test_resolve_effective_calls_effective_cell_formulas(self) -> None:
        src = (BACKEND_APP / "services" / "d_cycle_extraction" / "presets.py").read_text("utf-8")
        tree = ast.parse(src)
        fn = next(
            (n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "resolve_effective"),
            None,
        )
        assert fn is not None, "resolve_effective 不存在"
        calls = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
        assert "effective_cell_formulas" in calls, (
            "resolve_effective 没有调用 effective_cell_formulas —— Tier A 仍在直接查 WpFormula"
        )

    def test_resolve_effective_does_not_directly_query_wp_formula(self) -> None:
        src = (BACKEND_APP / "services" / "d_cycle_extraction" / "presets.py").read_text("utf-8")
        tree = ast.parse(src)
        fn = next(
            (n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "resolve_effective"),
            None,
        )
        assert fn is not None
        # resolve_effective 不应直接引用 WpFormula 或 sa.select(WpFormula)
        names = {node.id for node in ast.walk(fn) if isinstance(node, ast.Name)}
        assert "WpFormula" not in names, "resolve_effective 仍直接引用 WpFormula"


class TestPrefillReadsEffective:
    """prefill（wp_effective.effective_cell_formulas）本身即读有效定义。"""

    def test_effective_cell_formulas_reads_three_layers(self) -> None:
        """effective_cell_formulas 读项目 / 全局 / 预设三层。"""
        src = (BACKEND_APP / "services" / "formula_settings" / "wp_effective.py").read_text("utf-8")
        tree = ast.parse(src)
        fn = next(
            (n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "_load"),
            None,
        )
        assert fn is not None, "_load 不存在"
        body = ast.dump(fn)
        # 三层标志：FormulaSetting（全局）、WpFormula（项目）、_mapping_records（预设）
        assert "FormulaSetting" in body, "_load 不读全局层 FormulaSetting"
        assert "WpFormula" in body, "_load 不读项目层 WpFormula"
        assert "_mapping_records" in body, "_load 不读预设层 _mapping_records"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. SyntheticWpFormula 属性兼容性
# ═══════════════════════════════════════════════════════════════════════════════


class TestSyntheticWpFormula:
    def test_has_coordinator_attributes(self) -> None:
        """SyntheticWpFormula 具有 coordinator 需要的全部属性。"""
        from app.services.formula_settings.wp_effective import SyntheticWpFormula

        required = [
            "id", "project_id", "wp_id", "sheet_name", "target_cell", "expression",
            "formula_type", "formula_source", "category", "description", "source_scope",
            "refs", "issue_description", "hint_text", "stable_sheet_key", "row_key",
            "field_key", "definition_version",
        ]
        pid = uuid.uuid4()
        wid = uuid.uuid4()
        sf = SyntheticWpFormula(
            id=uuid.uuid4(), project_id=pid, wp_id=wid,
            sheet_name="Sheet1", target_cell="A1",
            expression="TB('1001','期末余额')", formula_type="auto_calc",
            formula_source="global",
        )
        for attr in required:
            assert hasattr(sf, attr), f"SyntheticWpFormula 缺少属性 {attr}"

    def test_deterministic_id(self) -> None:
        from app.services.formula_settings.wp_effective import _synthetic_id

        wid = uuid.UUID("12345678-1234-5678-1234-567812345678")
        id1 = _synthetic_id(wid, "Sheet1", "A1")
        id2 = _synthetic_id(wid, "Sheet1", "A1")
        assert id1 == id2, "同一公式位的 id 不稳定"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 直写 wp_formula 守卫
# ═══════════════════════════════════════════════════════════════════════════════


# 允许直写的白名单（WpStore、迁移脚本、wp_formula_service 本身、运行时元数据更新）
_ALLOWED_DIRECT_WRITE = {
    # WpStore 是同步内核的写入通道
    "domain_stores.py",
    # wp_formula_service 经 sync tracking（ADR-FGR-08）
    "wp_formula_service.py",
    # draft_refresh_service 只更新运行时元数据（last_computed_at / lifecycle_state），不改公式定义
    "draft_refresh_service.py",
    # 迁移脚本
}
_MIGRATION_PATTERN = re.compile(r"(V\d+__|R\d+__|migration)", re.IGNORECASE)


def _is_migration_file(path: Path) -> bool:
    return _MIGRATION_PATTERN.search(path.name) is not None or "migrations" in path.parts


class TestNoDirectWpFormulaWrite:
    """backend/app 内除白名单外不得直接 INSERT / UPDATE wp_formula（ADR-FGR-08）。"""

    def test_no_raw_sql_insert_update_wp_formula(self) -> None:
        """原生 SQL 中不得出现 INSERT/UPDATE wp_formula。"""
        _RAW_SQL = re.compile(
            r"""(?:INSERT\s+INTO|UPDATE)\s+(?:['"]?)wp_formula""",
            re.IGNORECASE,
        )
        violations: list[str] = []
        for py in BACKEND_APP.rglob("*.py"):
            if _is_migration_file(py) or py.name in _ALLOWED_DIRECT_WRITE:
                continue
            text = py.read_text("utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                if _RAW_SQL.search(line) and not line.lstrip().startswith("#"):
                    violations.append(f"{py.relative_to(BACKEND_APP)}:{i}")
        assert violations == [], f"以下文件直接写 wp_formula（应经 WpStore 或 wp_formula_service）: {violations}"

    def test_no_orm_bulk_update_wp_formula_outside_whitelist(self) -> None:
        """ORM sa.update(WpFormula) / sa.insert(WpFormula) 只在白名单文件中出现。"""
        _ORM_WRITE = re.compile(
            r"""(?:sa\.update|sa\.insert|update|insert)\s*\(\s*WpFormula""",
        )
        violations: list[str] = []
        for py in BACKEND_APP.rglob("*.py"):
            if _is_migration_file(py) or py.name in _ALLOWED_DIRECT_WRITE:
                continue
            text = py.read_text("utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                if _ORM_WRITE.search(line) and not line.lstrip().startswith("#"):
                    violations.append(f"{py.relative_to(BACKEND_APP)}:{i}")
        assert violations == [], f"以下文件 ORM 直接写 WpFormula: {violations}"

    def test_no_db_add_wp_formula_outside_whitelist(self) -> None:
        """db.add(WpFormula(...)) 只在白名单文件中出现。"""
        violations: list[str] = []
        for py in BACKEND_APP.rglob("*.py"):
            if _is_migration_file(py) or py.name in _ALLOWED_DIRECT_WRITE:
                continue
            text = py.read_text("utf-8", errors="replace")
            # 查找创建 WpFormula 实例并 add 的模式
            if "WpFormula(" in text and "db.add" in text:
                tree = ast.parse(text)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "WpFormula":
                        violations.append(str(py.relative_to(BACKEND_APP)))
                        break
        assert violations == [], f"以下文件直接创建 WpFormula 实例: {violations}"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 旧保存路径同步跟踪
# ═══════════════════════════════════════════════════════════════════════════════


class TestSaveSyncTracking:
    """wp_formula_service.save 写入后更新同步跟踪字段（ADR-FGR-08）。"""

    def test_save_calls_update_sync_tracking(self) -> None:
        """save 方法的源码必须包含 _update_sync_tracking 调用。"""
        src = (BACKEND_APP / "services" / "wp_formula_service.py").read_text("utf-8")
        tree = ast.parse(src)
        cls = next(
            (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "WpFormulaService"),
            None,
        )
        assert cls is not None
        save_fn = next(
            (n for n in ast.walk(cls) if isinstance(n, ast.AsyncFunctionDef) and n.name == "save"),
            None,
        )
        assert save_fn is not None
        calls = set()
        for node in ast.walk(save_fn):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
        assert "_update_sync_tracking" in calls, (
            "save 没有调用 _update_sync_tracking —— 旧保存路径不经同步跟踪"
        )

    def test_update_sync_tracking_exists(self) -> None:
        """WpFormulaService 具有 _update_sync_tracking 方法。"""
        from app.services.wp_formula_service import WpFormulaService

        assert hasattr(WpFormulaService, "_update_sync_tracking"), "缺少 _update_sync_tracking 方法"
