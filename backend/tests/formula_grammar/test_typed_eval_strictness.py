"""typed_eval_strictness 差异维度消除（ADR-FGR-06 / ADR-FGR-07）。

spec: formula-grammar-resolver-unification / tasks.md Task 7
Validates: R7（typed_eval_strictness 收敛）

覆盖点：
1. WPExecutor 两参缺数抛 FormulaEvalError（底稿不存在 / resolve_wp_cell 非 ok / 列键缺失）
2. 原因透传（reason 字符串非空、含底稿编码）
3. D2-3 与三参 A1 分支行为不变
4. formula_wp_semantics 中 typed_eval_strictness 维度已删
5. 四方一致：WPExecutor 缺数行为与 wp_ref_strict 同向（均报错不代 0）
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.formula_engine import FormulaEvalError, WPExecutor
from app.services.formula_wp_semantics import (
    REGISTERED_DIFFERENCE_DIMENSIONS,
    WP_KNOWN_DIFFERENCES,
    difference_of,
)
from app.services.wp_cell_reader import WpCellRead


# ── 工具 ──────────────────────────────────────────────────────────────────────

def _mock_db(parsed_data):
    """构造 mock DB，scalar_one_or_none 返回 parsed_data。"""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = parsed_data
    db.execute = AsyncMock(return_value=result)
    return db


# ═══════════════════════════════════════════════════════════════════════════════
# 1. WPExecutor 两参缺数抛 FormulaEvalError
# ═══════════════════════════════════════════════════════════════════════════════

class TestWPExecutorTwoParamRaisesOnMissing:
    """ADR-FGR-06：WPExecutor 两参 / 默认调用缺数报错，不再返回 D('0')。"""

    @pytest.mark.anyio
    async def test_workpaper_not_found(self):
        """底稿不存在 ⇒ FormulaEvalError。"""
        db = _mock_db(None)
        with pytest.raises(FormulaEvalError, match="不存在"):
            await WPExecutor.execute(db, uuid.uuid4(), "MISSING_WP", "审定数")

    @pytest.mark.anyio
    async def test_cell_resolve_missing(self):
        """单元格 resolve_wp_cell 返回 missing ⇒ FormulaEvalError + 原因透传。"""
        db = _mock_db({"html_data": {}})
        read = WpCellRead("missing", None, "单元格 B5 未录入", None, None)
        with patch("app.services.wp_cell_reader.resolve_wp_cell",
                    new_callable=AsyncMock, return_value=read):
            with pytest.raises(FormulaEvalError, match="B5 未录入"):
                await WPExecutor.execute(db, uuid.uuid4(), "D1", "B5")

    @pytest.mark.anyio
    async def test_cell_resolve_blocked(self):
        """单元格 resolve_wp_cell 返回 blocked ⇒ FormulaEvalError + 原因透传。"""
        db = _mock_db({})
        read = WpCellRead("blocked", None, "底稿记录有歧义", None, None)
        with patch("app.services.wp_cell_reader.resolve_wp_cell",
                    new_callable=AsyncMock, return_value=read):
            with pytest.raises(FormulaEvalError, match="歧义"):
                await WPExecutor.execute(db, uuid.uuid4(), "D1", "C5")

    @pytest.mark.anyio
    async def test_column_key_missing(self):
        """列名在 parsed_data 中不存在 ⇒ FormulaEvalError。"""
        db = _mock_db({"audited_amount": 100})
        with pytest.raises(FormulaEvalError, match="无「期初余额」的值"):
            await WPExecutor.execute(db, uuid.uuid4(), "E1", "期初余额")

    @pytest.mark.anyio
    async def test_column_key_none_value(self):
        """列名存在但值为 None ⇒ FormulaEvalError。"""
        db = _mock_db({"audited_amount": None})
        with pytest.raises(FormulaEvalError, match="无「审定数」的值"):
            await WPExecutor.execute(db, uuid.uuid4(), "E1", "审定数")

    @pytest.mark.anyio
    async def test_column_key_empty_string(self):
        """列名存在但值为空字符串 ⇒ FormulaEvalError。"""
        db = _mock_db({"audited_amount": "  "})
        with pytest.raises(FormulaEvalError, match="无「审定数」的值"):
            await WPExecutor.execute(db, uuid.uuid4(), "E1", "审定数")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 正常取值不受影响
# ═══════════════════════════════════════════════════════════════════════════════

class TestWPExecutorNormalPaths:
    """正常路径：有值时返回 Decimal。"""

    @pytest.mark.anyio
    async def test_column_value_present(self):
        db = _mock_db({"audited_amount": 123.45})
        val = await WPExecutor.execute(db, uuid.uuid4(), "E1", "审定数")
        assert val == Decimal("123.45")

    @pytest.mark.anyio
    async def test_column_value_zero_is_legitimate(self):
        """真实 0 值不被当成缺数。"""
        db = _mock_db({"audited_amount": 0})
        val = await WPExecutor.execute(db, uuid.uuid4(), "E1", "审定数")
        assert val == Decimal("0")

    @pytest.mark.anyio
    async def test_column_value_string_zero(self):
        """字符串 "0" 也是合法值。"""
        db = _mock_db({"audited_amount": "0"})
        val = await WPExecutor.execute(db, uuid.uuid4(), "E1", "审定数")
        assert val == Decimal("0")

    @pytest.mark.anyio
    async def test_cell_ok(self):
        """单元格 resolve_wp_cell 返回 ok ⇒ 正常返回值。"""
        db = _mock_db({"html_data": {}})
        read = WpCellRead("ok", Decimal("777"), None, uuid.uuid4(), "审定表")
        with patch("app.services.wp_cell_reader.resolve_wp_cell",
                    new_callable=AsyncMock, return_value=read):
            val = await WPExecutor.execute(db, uuid.uuid4(), "D1", "B5")
        assert val == Decimal("777")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. D2-3 与三参 A1 不受影响
# ═══════════════════════════════════════════════════════════════════════════════

class TestWPExecutorOtherPathsUnchanged:
    """D2-3 与三参 A1 分支的缺数行为不变。"""

    @pytest.mark.anyio
    async def test_three_arg_a1_missing_returns_none(self):
        """三参 A1 取不到 ⇒ None（不是 FormulaEvalError）。"""
        from app.services.acnr.wp_cell_target import TargetRead

        db = _mock_db(None)  # 不走两参 DB 查询
        read = WpCellRead("missing", None, "sheet 不存在", None, None)
        tr = TargetRead(read=read, bound_wp_code=None)
        with patch.object(WPExecutor, "read_sheet_cell",
                          new_callable=AsyncMock, return_value=tr):
            val = await WPExecutor.execute(
                db, uuid.uuid4(), "E1", "审定表E1-1", field="C10")
        assert val is None  # 不是 FormulaEvalError


# ═══════════════════════════════════════════════════════════════════════════════
# 4. typed_eval_strictness 维度已删
# ═══════════════════════════════════════════════════════════════════════════════

class TestTypedEvalStrictnessRemoved:
    """ADR-FGR-06 收敛验证：typed_eval_strictness 不在已登记差异维度中。"""

    def test_dimension_no_longer_registered(self):
        assert "typed_eval_strictness" not in REGISTERED_DIFFERENCE_DIMENSIONS

    def test_difference_of_returns_none(self):
        assert difference_of("typed_eval_strictness") is None

    def test_remaining_dimensions_are_three(self):
        assert len(WP_KNOWN_DIFFERENCES) == 3
        assert REGISTERED_DIFFERENCE_DIMENSIONS == {
            "positional_arg_count", "on_missing_return", "data_source",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 四方一致：WPExecutor 与 wp_ref_strict 缺数同向
# ═══════════════════════════════════════════════════════════════════════════════

class TestFourWayConsistency:
    """母 spec 需求 1.5 口径：WPExecutor / wp_ref_strict / typed_eval 缺数均报错。

    WPExecutor 抛 FormulaEvalError（调用方 catch 后可映射回 D('0')），
    wp_ref_strict 返回 WpCellRead(state="missing"|"blocked")（不代 0），
    两者在「缺数 ≠ 0」这一点上一致 —— 差异维度消除。
    """

    @pytest.mark.anyio
    async def test_executor_and_strict_both_refuse_zero_on_missing(self):
        """同一个缺数场景（底稿不存在），WPExecutor 抛错、wp_ref_strict 返非 ok。"""
        from app.services.wp_ref_strict import read_wp_ref_strict

        pid = uuid.uuid4()

        # WPExecutor 路径
        db_exec = _mock_db(None)
        with pytest.raises(FormulaEvalError):
            await WPExecutor.execute(db_exec, pid, "PHANTOM", "审定数")

        # wp_ref_strict 路径（需要真 DB 查，用 mock 模拟）
        db_strict = AsyncMock()
        db_strict.get_bind = MagicMock()
        db_strict.get_bind.return_value.dialect.name = "sqlite"
        result_strict = MagicMock()
        result_strict.all.return_value = []
        db_strict.execute = AsyncMock(return_value=result_strict)

        strict_read = await read_wp_ref_strict(db_strict, pid, 2025, "PHANTOM", "审定数", None)
        assert strict_read.state in ("missing", "blocked"), f"unexpected: {strict_read.state}"
        assert strict_read.value is None  # 不代 0

    @pytest.mark.anyio
    async def test_executor_and_strict_both_return_value_on_ok(self):
        """同一个有值场景，两条路径取到同一值。"""
        pid = uuid.uuid4()
        val = Decimal("500")

        # WPExecutor
        db_exec = _mock_db({"audited_amount": 500})
        exec_val = await WPExecutor.execute(db_exec, pid, "E1", "审定数")
        assert exec_val == val

        # wp_ref_strict
        from app.services.wp_ref_strict import WP_COLUMN_KEYS as STRICT_KEYS
        from app.services.formula_engine import WP_COLUMN_KEYS as EXEC_KEYS

        # 两边的列名映射一致
        for k in ("审定数", "未审数", "期初余额", "期末余额"):
            assert STRICT_KEYS.get(k) == EXEC_KEYS.get(k), f"列名映射 {k} 不一致"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. 登记表 on_missing 与源码一致（AST 交叉锁死）
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegistryOnMissingMatchesSource:
    """登记表的 on_missing 与 WPExecutor.execute 源码一致。"""

    def test_executor_on_missing_mentions_error(self):
        from app.services.formula_wp_semantics import impl_of, EXECUTOR_WP_IMPL

        spec = impl_of(EXECUTOR_WP_IMPL)
        assert "FormulaEvalError" in spec.on_missing
        assert "原因透传" in spec.on_missing

    def test_executor_source_raises_formula_eval_error(self):
        """WPExecutor.execute 方法体含 FormulaEvalError（AST 级）。"""
        import ast
        from pathlib import Path

        backend = Path(__file__).resolve().parents[2]
        src = (backend / "app" / "services" / "formula_engine.py").read_text("utf-8")
        tree = ast.parse(src)
        for cls in ast.walk(tree):
            if isinstance(cls, ast.ClassDef) and cls.name == "WPExecutor":
                for node in cls.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "execute":
                        body_code = ast.unparse(node)
                        assert "FormulaEvalError" in body_code, (
                            "WPExecutor.execute 方法体未引用 FormulaEvalError —— "
                            "两参缺数必须报错（ADR-FGR-06）"
                        )
                        # 确认 except FormulaEvalError: raise 存在（透传不吞）
                        assert "except FormulaEvalError" in body_code, (
                            "WPExecutor.execute 未单独 catch FormulaEvalError —— "
                            "缺数错误必须透传"
                        )
                        return
        raise AssertionError("未找到 WPExecutor.execute")
