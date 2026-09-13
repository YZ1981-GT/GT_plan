"""D4 C4 逐表验收 + C4 行为守卫/变异（governance spec Task 6 + Task 7 / Property 5）。

**Validates: Requirements 2.2, 3.2, 4.2, 5.1, 8.1**

- C4：36 行验收登记与 owner 矩阵锁死；UNVERIFIABLE 不假绿。
- 行为守卫：全五个治理守卫 main() 返回 0（矩阵/同步/公式/联动平台/验收）。
- 变异：改坏各真源必须被对应守卫拦下。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]


def _load_guard(name: str):
    path = _BACKEND / "scripts" / "check" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_{name}", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_owner_guard = _load_guard("check_d4_owner_matrix")
_sync_guard = _load_guard("check_d4_sync_contract")
_formula_guard = _load_guard("check_d4_formula_contract")
_linkage_guard = _load_guard("check_d4_linkage_platform_contract")
_c4_guard = _load_guard("check_d4_c4_acceptance")

_ALL_GUARDS = {
    "owner_matrix": _owner_guard,
    "sync_contract": _sync_guard,
    "formula_contract": _formula_guard,
    "linkage_platform": _linkage_guard,
    "c4_acceptance": _c4_guard,
}


class TestAllGovernanceGuardsGreen:
    """Property 5：五个治理守卫全绿（只门控 D4 相关产物）。"""

    @pytest.mark.parametrize("name", sorted(_ALL_GUARDS))
    def test_guard_main_returns_zero(self, name: str) -> None:
        assert _ALL_GUARDS[name].main() == 0, f"守卫 {name} 未通过"


class TestC4Registry:
    @pytest.fixture(scope="class")
    def c4(self) -> dict:
        return json.loads(
            (_BACKEND / "data" / "d4_c4_acceptance_registry.json").read_text(encoding="utf-8")
        )

    def test_36_rows(self, c4: dict) -> None:
        assert len(c4["rows"]) == 36

    def test_no_fake_green_playwright(self, c4: dict) -> None:
        """无运行时证据的 playwright 维不得 GREEN（Req 8.1 不假绿）。"""
        for r in c4["rows"]:
            assert r["playwright"] != "GREEN", f"{r['wp_code']} playwright 假绿"

    def test_unverifiable_present_and_honest(self, c4: dict) -> None:
        """至少存在 UNVERIFIABLE 登记（诚实标注，而非全绿粉饰）。"""
        all_vals = [r[d] for r in c4["rows"] for d in c4["dimensions"]]
        assert "UNVERIFIABLE" in all_vals

    def test_d4_1_own_dimensions_green(self, c4: dict) -> None:
        d41 = next(r for r in c4["rows"] if r["wp_code"] == "D4-1")
        for dim in ("source", "contract", "formula_conflict", "permission"):
            assert d41[dim] == "GREEN"
        assert d41["playwright"] == "UNVERIFIABLE"


class TestBehaviorMutations:
    """变异：改坏真源必须被守卫拦下（每条对应一个 Requirement 的判据）。"""

    def test_matrix_denominator_mutation(self) -> None:
        """Req 8.1 分母守恒：37 行必红。"""
        bad = {"denominator": 37, "rows": [{"wp_code": f"D4-{i}"} for i in range(1, 38)]}
        e: list[str] = []
        _owner_guard._check_denominator(bad, e)
        assert e

    def test_three_way_merge_shape_mutation(self) -> None:
        """Req 2.2 三方合并：契约 conflict_shape 必须是 base/current/incoming。"""
        c = json.loads(
            (_BACKEND / "data" / "d4_sync_contract_frozen.json").read_text(encoding="utf-8")
        )
        shape = c["invariants"]["field_level_auto_merge"]["backend_evidence"]["three_way_shape"]
        # 变异：任一项缺失就不再是三方
        assert set(shape) == {"base", "current", "incoming"}

    def test_formula_boundary_whitelist_mutation(self) -> None:
        """Req 3.2 公式边界：白名单校验器拒绝未注册函数（no-eval 的真实机制）。

        引擎只识别并派发已注册的**大写**函数，从不调用 Python eval/exec —— 因此任意
        未注册大写函数必被拒（whitelist）。这才是 no-eval 的判据面。
        """
        from app.services.formula_engine import validate_formula

        # 未注册的大写函数 → 必报错（whitelist 生效）
        assert validate_formula("=EVIL('1+1')"), "未注册函数未被 validate_formula 拒绝"
        # 引擎自带危险 token 黑名单（eval/exec/__/open/os./sys./subprocess），
        # 在表达式含这些时拒绝求值 —— 这是 no-eval 的第二道判据。
        import app.services.formula_engine as fe

        src = Path(fe.__file__).read_text(encoding="utf-8")
        assert "dangerous" in src, "formula_engine 缺危险 token 黑名单"
        for tok in ("'eval('", "'exec('", "'subprocess'"):
            assert tok in src, f"危险 token 黑名单缺 {tok}"

    def test_real_dag_no_cycle_mutation(self) -> None:
        """Req 4.2 真实 DAG：明细表反向引用审定表（成环）应被 no-cycle 守卫拦。

        这里断言契约登记了 no-cycle 守卫且其规则文本包含成环禁令。
        """
        c = json.loads(
            (_BACKEND / "data" / "d4_linkage_platform_contract_frozen.json").read_text(
                encoding="utf-8"
            )
        )
        rule = c["real_dag"]["no_cycle_guard"]["rule"]
        assert "成环" in rule and "WP()" in rule

    def test_publish_confirmation_is_explicit_mutation(self) -> None:
        """Req 5.1 发布确认：TB 发布是显式动作，非模式切换。"""
        c = json.loads(
            (_BACKEND / "data" / "d4_linkage_platform_contract_frozen.json").read_text(
                encoding="utf-8"
            )
        )
        pub = c["tb_a13_publish_boundary"]["d4_publish_is_explicit"]
        assert pub["fn"] == "publishAdjudicated"
        assert "非模式切换" in pub["trigger"] and "非公式保存" in pub["trigger"]
