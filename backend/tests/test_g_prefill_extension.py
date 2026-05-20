"""Tests for G-cycle prefill_formula_mapping.json extension (Sprint 2 Task 2.27)

Validates: Requirements G-F10
- G-cycle 总 cells ≥ 134（baseline 74 + 新增 ≥ 60，Sprint 0.X 降级目标 ≥ 60）
- 4-arg AUX 校验：=AUX 公式必须有 4 个参数（account, aux_type, aux_code, column）
- 真实 sheet 名校验：明细表G7-2 / 明细表G1-2 / 明细表G6-2 等（design.md ADR-G4 实测）
- G7 唯一保留 =AUX 4-arg 真实链路（1511.01 客户 ≥ 5 个 aux_code）
- G6 (1531.02) 部分 =AUX（含 1-2 个示例）
- G1/G4/G8/G11/G13/G14 全部使用 =TB / =LEDGER / =WP / =ADJ / =PREV（无 =AUX）

Spec: workpaper-g-investment-cycle / Sprint 2 / Task 2.27
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


DATA_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "prefill_formula_mapping.json"
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def mappings() -> list[dict]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))["mappings"]


@pytest.fixture(scope="module")
def g_entries(mappings) -> list[dict]:
    """所有 wp_code 以 G 开头的 entry"""
    return [e for e in mappings if (e.get("wp_code") or "").startswith("G")]


@pytest.fixture(scope="module")
def g_cells(g_entries) -> list[dict]:
    """所有 G entry 的 cells 平铺"""
    out = []
    for entry in g_entries:
        for c in entry.get("cells", []):
            out.append({
                "wp_code": entry["wp_code"],
                "sheet": entry["sheet"],
                **c,
            })
    return out


# ─── Test 1: G cycle 总 cell 数 ≥ 134 (74 baseline + ≥ 60 new) ───────────────


class TestGCycleCellCounts:
    def test_total_g_cells_at_least_134(self, g_cells):
        """G 循环总 cell 数 ≥ 134（Sprint 0.X 降级目标：74 + ≥ 60）"""
        assert len(g_cells) >= 134, (
            f"Expected ≥134 G cells, got {len(g_cells)}"
        )

    def test_g_entries_at_least_24(self, g_entries):
        """G entry 数 ≥ 24（baseline 16 + 至少 8 个新 (wp_code, sheet) 组合）"""
        assert len(g_entries) >= 24, (
            f"Expected ≥24 G entries, got {len(g_entries)}"
        )


# ─── Test 2: 真实 sheet 名验证（design.md ADR-G4 openpyxl 实测）──────────────


class TestRealSheetNames:
    """sheet 名必须用 openpyxl 实测的真实名称（铁律：禁止臆造）"""

    EXPECTED_SHEETS = {
        # design.md ADR-G4 实测真实 sheet 名（task 0x.2 落地）
        "明细表G1-2",
        "明细表G4-2",
        "明细表G6-2",
        "明细表G7-2",
        "明细表G8-2",
        # G11/G13/G14 明细分析 (Sprint 2 Task 2.25 创建)
        "明细分析表G11-2",
        "明细分析表G13-2",
        "明细分析表G14-2",
    }

    def test_real_sheet_names_present(self, g_entries):
        """新增 entry 的 sheet 名应在 design.md ADR-G4 实测清单内"""
        actual_sheets = {e["sheet"] for e in g_entries}
        missing = self.EXPECTED_SHEETS - actual_sheets
        assert not missing, (
            f"design.md ADR-G4 实测 sheet 名缺失: {missing}"
        )

    def test_no_invented_sheet_names(self, g_entries):
        """sheet 名不应含臆造 placeholder（如 'TBD' / 'placeholder'）"""
        for e in g_entries:
            sheet = e["sheet"].lower()
            assert "tbd" not in sheet, f"placeholder sheet 名: {e['sheet']}"
            assert "placeholder" not in sheet, f"placeholder sheet 名: {e['sheet']}"


# ─── Test 3: 4-arg =AUX 校验（强制铁律）───────────────────────────────────────


class TestAuxFormulaArgCount:
    """=AUX 公式必须严格 4-arg（account_code, aux_type, aux_code, column）"""

    def test_aux_formulas_have_exactly_4_args(self, g_cells):
        """=AUX(arg1,arg2,arg3,arg4) — 逗号数必须 == 3 → 4 个参数"""
        aux_cells = [c for c in g_cells if c["formula"] and c["formula"].startswith("=AUX(")]
        for c in aux_cells:
            formula = c["formula"]
            # 提取 () 内部字符串，按逗号计数
            inner = formula[len("=AUX("):].rsplit(")", 1)[0]
            arg_count = len([a.strip() for a in inner.split(",") if a.strip()])
            assert arg_count == 4, (
                f"=AUX 必须 4 args, 实际 {arg_count} args: "
                f"wp_code={c['wp_code']}, sheet={c['sheet']}, "
                f"cell_ref={c['cell_ref']}, formula={formula}"
            )

    def test_aux_args_quoted_strings(self, g_cells):
        """=AUX 各参数必须用单引号包裹（与现有 D2 客户明细表风格一致）"""
        aux_cells = [c for c in g_cells if c["formula"] and c["formula"].startswith("=AUX(")]
        for c in aux_cells:
            formula = c["formula"]
            inner = formula[len("=AUX("):].rsplit(")", 1)[0]
            args = [a.strip() for a in inner.split(",")]
            for arg in args:
                assert arg.startswith("'") and arg.endswith("'"), (
                    f"=AUX 参数应单引号包裹: {formula}"
                )


# ─── Test 4: G7 唯一保留 =AUX 真实链路（≥ 5 个 1511.01 客户 aux_code）────────


class TestG7AuxLinkage:
    """G7 (1511.01) 是 G 循环唯一保留 =AUX 4-arg 真实链路的子循环"""

    REAL_AUX_CODES_1511_01 = {
        "007960", "014127", "014747", "019378", "050645",
    }

    def test_g7_has_aux_cells(self, g_cells):
        g7_aux = [
            c for c in g_cells
            if c["wp_code"] == "G7"
            and c["formula"]
            and c["formula"].startswith("=AUX(")
        ]
        assert len(g7_aux) >= 5, (
            f"G7 应至少含 5 个 =AUX 4-arg cells (Sprint 0.X 实测客户), 实际 {len(g7_aux)}"
        )

    def test_g7_aux_uses_1511_01(self, g_cells):
        """G7 =AUX 必须使用 account_code='1511.01'"""
        g7_aux = [
            c for c in g_cells
            if c["wp_code"] == "G7"
            and c["formula"]
            and c["formula"].startswith("=AUX(")
        ]
        for c in g7_aux:
            assert "'1511.01'" in c["formula"], (
                f"G7 =AUX 应使用 '1511.01' account_code: {c['formula']}"
            )

    def test_g7_aux_uses_kehu_aux_type(self, g_cells):
        """G7 =AUX 必须使用 aux_type='客户'（Sprint 0.X 实测唯一可用维度）"""
        g7_aux = [
            c for c in g_cells
            if c["wp_code"] == "G7"
            and c["formula"]
            and c["formula"].startswith("=AUX(")
        ]
        for c in g7_aux:
            assert "'客户'" in c["formula"], (
                f"G7 =AUX 应使用 '客户' aux_type: {c['formula']}"
            )

    def test_g7_aux_codes_are_real_samples(self, g_cells):
        """G7 =AUX 的 aux_code 应为 Sprint 0.X 实测真实客户码（不能臆造）"""
        g7_aux = [
            c for c in g_cells
            if c["wp_code"] == "G7"
            and c["formula"]
            and c["formula"].startswith("=AUX(")
        ]
        # 提取 aux_code（第三参数）
        used_codes = set()
        for c in g7_aux:
            inner = c["formula"][len("=AUX("):].rsplit(")", 1)[0]
            args = [a.strip().strip("'") for a in inner.split(",")]
            if len(args) >= 3:
                used_codes.add(args[2])
        # 至少 5 个使用的 aux_code 应在实测样本集内
        in_samples = used_codes & self.REAL_AUX_CODES_1511_01
        assert len(in_samples) >= 5, (
            f"G7 =AUX 至少需 5 个 aux_code 来自 Sprint 0.X 实测 1511.01 客户样本, "
            f"实际重叠 {in_samples}"
        )


# ─── Test 5: G6 (1531.02) 部分 =AUX 示例 ──────────────────────────────────


class TestG6PartialAux:
    """G6 (1531.02) 含 1-2 个 =AUX 示例（Sprint 0.X 实测）"""

    def test_g6_has_at_least_one_aux(self, g_cells):
        g6_aux = [
            c for c in g_cells
            if c["wp_code"] == "G6"
            and c["formula"]
            and c["formula"].startswith("=AUX(")
        ]
        assert len(g6_aux) >= 1, (
            f"G6 应至少含 1 个 =AUX cell（1531.02 实测）, 实际 {len(g6_aux)}"
        )

    def test_g6_aux_uses_1531_02(self, g_cells):
        g6_aux = [
            c for c in g_cells
            if c["wp_code"] == "G6"
            and c["formula"]
            and c["formula"].startswith("=AUX(")
        ]
        for c in g6_aux:
            assert "'1531.02'" in c["formula"], (
                f"G6 =AUX 应使用 '1531.02' account_code: {c['formula']}"
            )


# ─── Test 6: G1/G4/G8/G11/G13/G14 不含 =AUX（仅 =TB/=LEDGER/=WP/=ADJ/=PREV）─


class TestNonG7G6CyclesNoAux:
    """G1/G4/G8/G11/G13/G14 子循环（无 aux 数据）不应含 =AUX 公式"""

    NO_AUX_WP_CODES = {"G1", "G4", "G8", "G11", "G13", "G14"}

    def test_no_aux_in_other_g_cycles(self, g_cells):
        """1101/1501/1521-1527 均无 tb_aux_balance 数据，prefill 必须降级为 =TB/=LEDGER/=WP"""
        for c in g_cells:
            if c["wp_code"] in self.NO_AUX_WP_CODES:
                if c["formula"] is not None:
                    assert not c["formula"].startswith("=AUX("), (
                        f"{c['wp_code']} 不应含 =AUX cell（Sprint 0.X 实测无 aux 数据）: "
                        f"sheet={c['sheet']}, cell_ref={c['cell_ref']}, formula={c['formula']}"
                    )


# ─── Test 7: 各 sheet 最低 cell 数（task 2.25 子任务声明）────────────────────


class TestPerSheetMinimums:
    """task 2.25 子任务声明的各 sheet 最低 cell 数"""

    @pytest.mark.parametrize("sheet,min_cells,description", [
        ("明细表G1-2", 10, "G1 交易性金融资产明细表 ≥ 10 cell"),
        ("明细表G4-2", 6, "G4 债权投资明细表 + ECL 测试参数 ≥ 6 cell"),
        ("明细表G6-2", 10, "G6 其他债权投资明细表 ≥ 10 cell"),
        ("明细表G7-2", 15, "G7 长期股权投资明细表 ≥ 15 cell（含 =AUX 客户链路）"),
        ("明细表G8-2", 6, "G8 其他权益工具投资明细表 ≥ 6 cell"),
    ])
    def test_sheet_meets_minimum(self, g_cells, sheet, min_cells, description):
        actual = sum(1 for c in g_cells if c["sheet"] == sheet)
        assert actual >= min_cells, (
            f"{description}: 实际 {actual} < 期望 ≥ {min_cells}"
        )

    def test_g11_aggregation_meets_minimum(self, g_cells):
        """G11 投资收益汇总（=WP 跨 sheet）≥ 6 cell"""
        actual = sum(1 for c in g_cells if c["sheet"] == "明细分析表G11-2")
        assert actual >= 6, (
            f"G11 投资收益汇总 ≥ 6 cell: 实际 {actual}"
        )

    def test_g13_g14_aggregation_meets_minimum(self, g_cells):
        """G13 公允价值变动 + G14 信用减值汇总（=WP 跨 sheet）≥ 7 cell 合计"""
        g13 = sum(1 for c in g_cells if c["sheet"] == "明细分析表G13-2")
        g14 = sum(1 for c in g_cells if c["sheet"] == "明细分析表G14-2")
        assert g13 + g14 >= 7, (
            f"G13+G14 汇总 ≥ 7 cell 合计: 实际 G13={g13} + G14={g14} = {g13+g14}"
        )


# ─── Test 8: formula_type 枚举合法性 ────────────────────────────────────────


class TestFormulaTypeValidity:
    VALID_FORMULA_TYPES = {
        "TB", "TB_SUM", "TB_AUX", "AUX",
        "ADJ", "PREV", "WP",
        "LEDGER", "PLACEHOLDER",
    }

    def test_formula_types_in_enum(self, g_cells):
        for c in g_cells:
            ft = c.get("formula_type") or ""
            assert ft in self.VALID_FORMULA_TYPES, (
                f"非法 formula_type {ft!r} in "
                f"{c['wp_code']}/{c['sheet']}/{c['cell_ref']}"
            )

    def test_formula_matches_type(self, g_cells):
        """formula 前缀应与 formula_type 匹配"""
        for c in g_cells:
            ft = c.get("formula_type")
            f = c.get("formula")
            if f is None:
                continue
            if ft == "TB":
                assert f.startswith("=TB("), f"{c['cell_ref']}: {f}"
            elif ft == "TB_SUM":
                assert f.startswith("=TB_SUM("), f"{c['cell_ref']}: {f}"
            elif ft == "TB_AUX":
                assert f.startswith("=TB_AUX("), f"{c['cell_ref']}: {f}"
            elif ft == "AUX":
                assert f.startswith("=AUX("), f"{c['cell_ref']}: {f}"
            elif ft == "ADJ":
                assert f.startswith("=ADJ("), f"{c['cell_ref']}: {f}"
            elif ft == "PREV":
                assert f.startswith("=PREV("), f"{c['cell_ref']}: {f}"
            elif ft == "WP":
                assert f.startswith("=WP("), f"{c['cell_ref']}: {f}"
            elif ft == "LEDGER":
                assert f.startswith("=LEDGER("), f"{c['cell_ref']}: {f}"
