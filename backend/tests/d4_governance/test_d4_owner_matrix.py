"""D4 owner 矩阵契约测试（governance spec d4-dual-mode-formula-governance Task 1）。

Property 1：36 个且仅 36 个 wp_code 各有一条 owner 记录；物理 sheet/变体/程序表不扩张分母。
**Validates: Requirements 1.1, 1.2, 1.3, 8.1**

本文件既跑真源守卫（check_d4_owner_matrix.main() 返回 0），也直接对矩阵结构断言，
并做变异型反向自检（改坏矩阵副本必须被守卫函数拦下 —— 防守卫是空操作）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]  # backend/
_MATRIX = _ROOT / "data" / "d4_owner_matrix.json"

# 复用守卫的检查函数做变异检验（真源与守卫同源，避免两套判据漂移）
import importlib.util

_GUARD_PATH = _ROOT / "scripts" / "check" / "check_d4_owner_matrix.py"
_spec = importlib.util.spec_from_file_location("_d4_owner_guard", _GUARD_PATH)
assert _spec and _spec.loader
_guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_guard)  # type: ignore[union-attr]


@pytest.fixture(scope="module")
def matrix() -> dict:
    return json.loads(_MATRIX.read_text(encoding="utf-8"))


class TestDenominator:
    """分母恒 36，wp_code 连续无缺无重（Property 1 / Req 1.1）。"""

    def test_exactly_36_rows(self, matrix: dict) -> None:
        assert len(matrix["rows"]) == 36
        assert matrix["denominator"] == 36

    def test_codes_are_d4_1_through_36_no_gap_no_dupe(self, matrix: dict) -> None:
        codes = [r["wp_code"] for r in matrix["rows"]]
        assert sorted(codes, key=lambda c: int(c.split("-")[1])) == [
            f"D4-{i}" for i in range(1, 37)
        ]
        assert len(set(codes)) == 36, "wp_code 有重复"

    def test_no_physical_sheet_variants_in_denominator(self, matrix: dict) -> None:
        """D4-22A / D4A / 程序表等物理证据不得作为分母行。"""
        codes = {r["wp_code"] for r in matrix["rows"]}
        for forbidden in ("D4-22A", "D4A", "D422A", "D4-31T"):
            assert forbidden not in codes, f"{forbidden} 不应进入分母"


class TestOwnerDedup:
    """已有 owner 不重复立项（Req 1.2）；gap 项登记（Req 1.3）；D4-1 专属（own）。"""

    def test_d4_1_owned_by_governance(self, matrix: dict) -> None:
        d41 = next(r for r in matrix["rows"] if r["wp_code"] == "D4-1")
        assert d41["owner"] == "d4-dual-mode-formula-governance"
        assert d41["status"] == "own"

    def test_dedicated_owners_not_reassigned_to_governance(self, matrix: dict) -> None:
        dedicated = {
            "D4-2": "d4-revenue-matrix-bidirectional",
            "D4-3": "d4-revenue-matrix-bidirectional",
            "D4-9": "d4-9-customer-structure-bidirectional-writeback",
            "D4-10": "d4-price-analysis-writeback-linkage",
            "D4-11": "d4-price-analysis-writeback-linkage",
        }
        by_code = {r["wp_code"]: r for r in matrix["rows"]}
        for code, owner in dedicated.items():
            assert by_code[code]["owner"] == owner
            assert by_code[code]["status"] == "dedicated"
            assert by_code[code]["owner"] != "d4-dual-mode-formula-governance"

    def test_gap_codes_registered(self, matrix: dict) -> None:
        by_code = {r["wp_code"]: r for r in matrix["rows"]}
        for code in ("D4-4", "D4-8", "D4-12"):
            assert by_code[code]["status"] == "gap"
            assert by_code[code]["owner"], f"{code} gap owner 不得为空"


class TestGuardGreen:
    """真源守卫整体通过（含模板证据落地 + design.md 锁死）。"""

    def test_guard_main_returns_zero(self) -> None:
        assert _guard.main() == 0


class TestMutationReverseChecks:
    """变异检验：改坏矩阵副本必须被守卫函数拦下（防守卫空操作 → 假绿三源之②）。"""

    def test_37_rows_is_rejected(self) -> None:
        bad = {"denominator": 37, "rows": [{"wp_code": f"D4-{i}"} for i in range(1, 38)]}
        errs: list[str] = []
        _guard._check_denominator(bad, errs)
        assert errs, "37 行未被拦下 —— 守卫失效"

    def test_duplicate_code_is_rejected(self) -> None:
        bad = {
            "denominator": 36,
            "rows": [{"wp_code": f"D4-{i}"} for i in range(1, 36)]
            + [{"wp_code": "D4-1"}],
        }
        errs: list[str] = []
        _guard._check_denominator(bad, errs)
        assert any("重复" in e for e in errs)

    def test_variant_code_in_denominator_is_rejected(self) -> None:
        bad = {
            "denominator": 36,
            "rows": [{"wp_code": f"D4-{i}"} for i in range(1, 36)]
            + [{"wp_code": "D4-22A"}],
        }
        errs: list[str] = []
        _guard._check_denominator(bad, errs)
        assert any("非 D4-1..36" in e for e in errs)

    def test_d4_1_owner_reassignment_is_rejected(self) -> None:
        bad = {"rows": [{"wp_code": "D4-1", "owner": "some-other-spec", "status": "own"}]}
        errs: list[str] = []
        _guard._check_own_row(bad, errs)
        assert errs, "D4-1 owner 被改仍未拦下 —— 守卫失效"

    def test_gap_downgraded_to_blank_owner_is_rejected(self) -> None:
        bad = {"rows": [{"wp_code": "D4-4", "owner": "", "status": "gap"}]}
        errs: list[str] = []
        _guard._check_gaps(bad, errs)
        assert any("owner 为空" in e for e in errs)
