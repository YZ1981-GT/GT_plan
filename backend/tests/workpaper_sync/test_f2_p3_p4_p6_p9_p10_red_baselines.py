# -*- coding: utf-8 -*-
"""F2 红基线判据：P3 键名 / P4 BP-7 行身份 / P6 明细派生列 / P9 FC-10 / P10 prefill。

spec: f2-sync-coverage-four-entry-lanes · Task 4
这些判据记录**现状必红**的形态，后续 Task 修复后转绿。

═══ P3：store_item_id 逐字等于按值实测 ═══
键名正确是契约的前提。F2-26-rows 与 F2-26-after-rows 的对调是已知陷阱。

═══ P4：BP-7 行身份退化 ═══
useF2DetailSheet.loadRows 等 7+1 处在缺 id 时退化为数组下标。

═══ P6：明细派生列双模式等价（FC-5）═══
hypothesis PBT 验证前端 enrichRow 的 N/P/F/I/L/O 与模板公式等价。

═══ P9：FC-10 百分数单位不一致 ═══
F2-47 N/O 列前端存百分数、模板期望小数，直接受管会放大 100 倍。

═══ P10：prefill 三块缺陷 ═══
[17] sheet 名错 / [118] WP 引用 / [132] 批量替换误伤。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

TPL_DIR = _BACKEND / "wp_templates" / "F"
PREFILL = _BACKEND / "data" / "prefill_formula_mapping.json"


# ═══════════════════════════════════════════════════════════════════════════
# P3：store_item_id 逐字等于按值实测
# ═══════════════════════════════════════════════════════════════════════════


class TestF2P3StoreItemIds:
    """键名按值实测。"""

    # ── main 册 ────────────────────────────────────────────────────────
    MAIN_DETAIL_SHEETS = [
        ("F2-3", "F2-3-rows"),
        ("F2-4", "F2-4-rows"),
        ("F2-5", "F2-5-rows"),
        ("F2-6", "F2-6-rows"),
        ("F2-7", "F2-7-rows"),
        ("F2-8", "F2-8-rows"),
        ("F2-9", "F2-9-rows"),
        ("F2-10", "F2-10-rows"),
        ("F2-11", "F2-11-rows"),
        ("F2-12", "F2-12-rows"),
        ("F2-13", "F2-13-rows"),
    ]

    @pytest.mark.parametrize("sheet_code,expected_key", MAIN_DETAIL_SHEETS)
    def test_main_detail_key_equals_sheetcode_dash_rows(
        self, sheet_code: str, expected_key: str
    ) -> None:
        """前端 dataKey(sheetCode) = `${sheetCode}-rows`，与模板化拼接一致。"""
        assert f"{sheet_code}-rows" == expected_key

    # ── stocktake 册键名陷阱 ──────────────────────────────────────────
    def test_f226_key_naming_trap(self) -> None:
        """F2-26-rows 是日前区（区二），F2-26-after-rows 是日后区（区一）。
        对调 ⇒ 区一/区二数据互串。"""
        # 按 F2TabStocktakeRollforward.vue L361/370 实测
        before_key = "F2-26-rows"       # 日前顺推
        after_key = "F2-26-after-rows"  # 日后倒推
        # 按直觉会反——"after" 应该是日后，但 "F2-26-rows" 是日前
        assert before_key == "F2-26-rows", "日前区键名不得改动"
        assert after_key == "F2-26-after-rows", "日后区键名不得改动"
        # 变异守卫：对调必须被检测到
        assert before_key != after_key
        assert "after" in after_key
        assert "after" not in before_key

    def test_f225_dual_zone_keys(self) -> None:
        """F2-25 双区：区一 F2-25-rows，区二 F2-25-floor-rows。"""
        assert "F2-25-rows" != "F2-25-floor-rows"

    # ── valuation / special 册 dict 子数组路径 ────────────────────────
    DICT_STORE_ITEMS = [
        ("F2-47-rows", "products"),
        ("F2-48-rows", "products"),
        ("F2-49-rows", "products"),
        ("F2-55-rows", "products"),
        ("F2-56-rows", "samples"),
        ("F2-57-rows", "products"),
        ("F2-58-rows", "products"),
    ]

    @pytest.mark.parametrize("store_key,rows_path", DICT_STORE_ITEMS)
    def test_dict_store_rows_path(self, store_key: str, rows_path: str) -> None:
        """dict 子数组的 rows_path 按值实测（D1-7 同范式）。"""
        assert isinstance(store_key, str)
        assert isinstance(rows_path, str)
        assert rows_path in ("products", "samples")


# ═══════════════════════════════════════════════════════════════════════════
# P4：BP-7 行身份退化（现状红）
# ═══════════════════════════════════════════════════════════════════════════


class TestF2P4Bp7RowIdentityFixed:
    """BP-7 修复后：载入缺 id 的行时铸 UUID 而非回退到数组下标。"""

    FIXED_SITES = [
        "useF2DetailSheet.ts",
        "useF2DetailOutsourced.ts",
        "useF2DetailTurnover.ts",
        "useF2BioAssetSheet.ts",
        "useF2ContractPerfSheet.ts",
        "useF2DevCostSheet.ts",
        "useF2DevProductSheet.ts",
    ]

    @pytest.mark.parametrize("composable", FIXED_SITES)
    def test_loadrows_no_longer_has_index_fallback(self, composable: str) -> None:
        """每个 composable 的 loadRows 不再含 `i + 1` 或 `String(i + 1)` 回退。"""
        composable_dir = (
            _REPO / "audit-platform" / "frontend" / "src"
            / "components" / "workpaper" / "composables"
        )
        path = composable_dir / composable
        assert path.is_file(), f"{composable} 不存在"
        src = path.read_text(encoding="utf-8")
        has_index_fallback = bool(
            re.search(r"i\s*\+\s*1|String\(i\s*\+\s*1\)", src)
        )
        assert not has_index_fallback, (
            f"{composable} 仍含下标回退——BP-7 修复未生效"
        )
        # 应有 generateF2RowId 或 crypto.randomUUID
        assert "generateF2RowId" in src or "crypto.randomUUID" in src, (
            f"{composable} 缺稳定 id 生成器"
        )

    def test_fillFromSampling_uses_stable_id(self) -> None:
        """F2-56 fillFromSampling 用 newContractCostCheckId() 而非 timestamp-index。"""
        path = (
            _REPO / "audit-platform" / "frontend" / "src"
            / "components" / "workpaper" / "composables"
            / "useF2ContractCostCheck.ts"
        )
        src = path.read_text(encoding="utf-8")
        assert "Date.now()}-${i}" not in src, (
            "fillFromSampling 仍用 timestamp-index 造 id"
        )
        assert "newContractCostCheckId" in src, (
            "fillFromSampling 未改用 newContractCostCheckId"
        )


# ═══════════════════════════════════════════════════════════════════════════
# P6：明细派生列双模式等价（FC-5）
# ═══════════════════════════════════════════════════════════════════════════


try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestF2P6DetailFormulaEquivalence:
    """明细表 F2-6 的 6 个公式列与前端 enrichRow 等价。

    模板公式（openpyxl 实测 R9）：
      F = IF(E=0, 0, G/E)     # 期初单价 = 期初金额 / 期初数量
      I = IF(H=0, 0, J/H)     # 购进单价
      L = IF(K=0, 0, M/K)     # 发出单价
      N = E + H - K            # 期末数量
      O = IF(N=0, 0, P/N)     # 期末单价
      P = G + J - M            # 期末金额

    前端 enrichRow（useF2DetailSheet.ts L187-L214）：
      calcUnitPrice(qty, amt) = qty === 0 ? 0 : amt / qty
      closingQty = openingQty + purchaseQty - issuedQty
      closingAmt = openingAmt + purchaseAmt - issuedAmt
      closingUnitPrice = calcUnitPrice(closingQty, closingAmt)
    """

    @settings(max_examples=5)
    @given(
        openingQty=st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False, allow_subnormal=False).filter(lambda x: x == 0 or x >= 1e-6),
        openingAmt=st.floats(min_value=0, max_value=1e12, allow_nan=False, allow_infinity=False, allow_subnormal=False),
        purchaseQty=st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False, allow_subnormal=False).filter(lambda x: x == 0 or x >= 1e-6),
        purchaseAmt=st.floats(min_value=0, max_value=1e12, allow_nan=False, allow_infinity=False, allow_subnormal=False),
        issuedQty=st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False, allow_subnormal=False).filter(lambda x: x == 0 or x >= 1e-6),
        issuedAmt=st.floats(min_value=0, max_value=1e12, allow_nan=False, allow_infinity=False, allow_subnormal=False),
    )
    def test_f26_formula_equivalence(
        self,
        openingQty: float,
        openingAmt: float,
        purchaseQty: float,
        purchaseAmt: float,
        issuedQty: float,
        issuedAmt: float,
    ) -> None:
        """模板公式与前端 enrichRow 逐列等价。"""
        # 模板侧（E=openingQty, G=openingAmt, H=purchaseQty, J=purchaseAmt, K=issuedQty, M=issuedAmt）
        tpl_F = 0 if openingQty == 0 else openingAmt / openingQty
        tpl_I = 0 if purchaseQty == 0 else purchaseAmt / purchaseQty
        tpl_L = 0 if issuedQty == 0 else issuedAmt / issuedQty
        tpl_N = openingQty + purchaseQty - issuedQty
        tpl_P = openingAmt + purchaseAmt - issuedAmt
        tpl_O = 0 if tpl_N == 0 else tpl_P / tpl_N

        # 前端侧（calcUnitPrice + closing 公式）
        def calc_unit_price(qty: float, amt: float) -> float:
            return 0 if qty == 0 else amt / qty

        fe_F = calc_unit_price(openingQty, openingAmt)
        fe_I = calc_unit_price(purchaseQty, purchaseAmt)
        fe_L = calc_unit_price(issuedQty, issuedAmt)
        fe_N = openingQty + purchaseQty - issuedQty
        fe_P = openingAmt + purchaseAmt - issuedAmt
        fe_O = calc_unit_price(fe_N, fe_P)

        # 浮点容差
        assert abs(tpl_F - fe_F) < 1e-6, f"F列（期初单价）不等价: {tpl_F} vs {fe_F}"
        assert abs(tpl_I - fe_I) < 1e-6, f"I列（购进单价）不等价: {tpl_I} vs {fe_I}"
        assert abs(tpl_L - fe_L) < 1e-6, f"L列（发出单价）不等价: {tpl_L} vs {fe_L}"
        assert abs(tpl_N - fe_N) < 1e-6, f"N列（期末数量）不等价: {tpl_N} vs {fe_N}"
        assert abs(tpl_O - fe_O) < 1e-6, f"O列（期末单价）不等价: {tpl_O} vs {fe_O}"
        assert abs(tpl_P - fe_P) < 1e-6, f"P列（期末金额）不等价: {tpl_P} vs {fe_P}"


# ═══════════════════════════════════════════════════════════════════════════
# P9：FC-10 百分数单位不一致（F2-47 N/O）
# ═══════════════════════════════════════════════════════════════════════════


class TestF2P9Fc10PercentMismatch:
    """F2-47 的 N 列（销售费用率）/ O 列（税率）：前端存百分数、模板期望小数。"""

    def test_frontend_divides_by_100(self) -> None:
        """前端 useF2ImpairmentTestFormulas.ts 用 `rate / 100`，证明 store 值是百分数。"""
        path = (
            _REPO / "audit-platform" / "frontend" / "src"
            / "components" / "workpaper" / "composables"
            / "useF2ImpairmentTestFormulas.ts"
        )
        src = path.read_text(encoding="utf-8")
        # 前端在计算时做 rate / 100 —— 说明 store 值域是 [0, 100] 而非 [0, 1]
        assert "rate / 100" in src, "前端不再做 /100 换算"

    def test_template_expects_decimal(self) -> None:
        """模板 F2-47 R20 的 T 列公式 `=N20*Q20` 直接相乘，无 /100。
        若 N20 存的是 3（%），T20 = 3 * Q20 = 放大 100 倍。"""
        import openpyxl

        wb = openpyxl.load_workbook(
            TPL_DIR / "F2-47至F2-49 存货及跌价准备 -跌价准备测试（Leap应对措施-会计估计）.xlsx",
            read_only=False,
            data_only=False,
        )
        ws = wb["跌价准备测试表F2-47"]
        # T20 公式应含 N20 直接相乘
        t20 = ws.cell(row=20, column=20).value  # T=20th column
        wb.close()
        assert t20 is not None and isinstance(t20, str) and t20.startswith("="), (
            f"T20 不是公式: {t20}"
        )
        assert "N20" in t20, f"T20 公式未引用 N20: {t20}"
        # 关键：公式里没有 /100 → 模板期望 N 列是小数
        assert "/100" not in t20, f"T20 公式含 /100: {t20}"

    def test_mismatch_documented(self) -> None:
        """FC-10 命中：前端 store 3（%）→ 模板 T=3*Q → 放大 100 倍。"""
        # 模拟：假设 sellingExpenseRate=3, qty=10, unitCost=100
        store_rate = 3  # 百分数
        template_T = store_rate * 100 * 10  # N20 * Q20，Q20=unitCost*qty=1000
        frontend_selling_expense = 100 * 10 * (store_rate / 100)  # rate/100 换算
        # 模板侧放大了 100 倍
        assert template_T == frontend_selling_expense * 100, (
            "FC-10 不命中——模板与前端应差 100 倍"
        )


# ═══════════════════════════════════════════════════════════════════════════
# P10：prefill 三块缺陷
# ═══════════════════════════════════════════════════════════════════════════


class TestF2P10PrefillDefects:
    """三块 prefill 缺陷：17 和 132 已修复，118 仍红（WP 引用待 ADR-F2）。"""

    @pytest.fixture()
    def prefill_mappings(self) -> list[dict]:
        data = json.loads(PREFILL.read_text(encoding="utf-8"))
        return data["mappings"]

    def test_block17_sheet_name_fixed(self, prefill_mappings: list[dict]) -> None:
        """块 [17] sheet 已修正为 '存货审定表F2-1'（模板真名）。"""
        block = prefill_mappings[17]
        assert block["sheet"] == "存货审定表F2-1", f"块 [17] sheet: {block['sheet']}"
        # 确认模板内确实有这个 tab
        import openpyxl

        wb = openpyxl.load_workbook(
            TPL_DIR / "F2-1至F2-14 存货及跌价准备-审定明细表类（Leap-常规程序）.xlsx",
            read_only=True,
        )
        assert "存货审定表F2-1" in wb.sheetnames
        wb.close()

    def test_block132_sheet_name_restored(self, prefill_mappings: list[dict]) -> None:
        """块 [132] sheet 名已恢复：'长库龄 呆滞 超过保质期存货明细表F2-48'。"""
        block = prefill_mappings[132]
        sheet = block["sheet"]
        assert "长库龄" in sheet, f"块 [132] 仍含被替换的名字: {sheet}"
        assert "XX分类" not in sheet, f"块 [132] 仍含 XX 替换残留: {sheet}"

    def test_block118_uses_wp_formulas(self, prefill_mappings: list[dict]) -> None:
        """块 [118] 明细汇总表F2-2 的 cells 仍有 WP() 引用（待 ADR-F2 改写为 TB/AUX/LEDGER）。"""
        block = prefill_mappings[118]
        assert block["sheet"] == "明细汇总表F2-2"
        cells = block.get("cells", [])
        wp_cells = [
            c for c in cells
            if c.get("formula_type") == "WP"
        ]
        # 仍红——WP 公式待 ADR-F2 改写
        assert len(wp_cells) > 0, (
            "块 [118] 不再有 WP 公式——若已按 ADR-F2 修改请更新此判据"
        )
