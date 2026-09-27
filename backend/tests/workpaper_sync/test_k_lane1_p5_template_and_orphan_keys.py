# -*- coding: utf-8 -*-
"""K 循环 lane 1 — Task 16~20：模板层治理与孤儿键清理。

spec: k1-k7-inlined-iife-hosts-and-orphan-cleanup

Task 16: definedName 基线冻结（🔴 K 循环全部 65 个断链都在本 lane）
Task 17: K1 双变体披露表 70 格 `#REF!` 的覆盖层修复
Task 18: 🔴 双变体账龄分层深度差异登记
Task 19: K2 孤儿 per-row 键清理
Task 20: `审定表K2-1` 纯派生标注

Property: KA-P25, KA-P26, KA-P27, KA-P28, KA-P29, KA-P30, KA-P31,
          KA-P32, KA-P33, KA-P34, KA-P39

═══ 🔴 口径差异（如实登记，不改判据方向）═══

**tasks.md 的 `R130` / `R141` 与 `$B$18` 都是「上市公司变体」口径。** 现算两变体
形态同构但行号与分母都不同名：

| | 子区①（前五名） | 子区①合计 | 子区②（政府补助） | 子区②合计 | 占比分母 |
|---|---|---|---|---|---|
| 上市 | R125:R129 | **R130**（2 个 SUM） | R138:R140 | **R141**（1 个 SUM） | `$B$18` |
| 国企 | R104:R108 | **R109**（2 个 SUM） | R127:R129 | **R130**（1 个 SUM） | `$B$13` |

🔴 `R130` 在两个变体里**指的不是同一个东西**（上市是子区①合计、国企是子区②合计）
⇒ 判据必须按变体分别断言；写成「R130 有两个 SUM」在国企必假红。
分母差 `18 − 13 = 5` 与 Task 18 的账龄分层深度差**同源**（上市多一层内含 3 档 + 小计）。
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re

import pytest
from openpyxl import load_workbook

from tests.workpaper_sync.k_foundation_facts import (  # noqa: E402
    DATA,
    ROOT,
    WP_COMPOSABLES,
    cached_text,
)
from tests.workpaper_sync.k_lane1_facts import (  # noqa: E402
    LANE1_DEFINED_NAMES_BY_ENTRY,
    LANE1_INDEXES,
)

K_TEMPLATE_DIR = ROOT / "backend" / "wp_templates" / "K"
CONTRACT_DIR = DATA / "workpaper_sync_contracts"
K1_CONTRACT = CONTRACT_DIR / "k1.baddebt_reversal_writeoff_check.candidate.json"
K2_CONTRACT = CONTRACT_DIR / "k2.adjudication_derived.candidate.json"

LANE1_BOOKS: dict[int, str] = {
    1: "K1 其他应收款.xlsx",
    2: "K2 其他流动资产.xlsx",
    3: "K3 其他应付款.xlsx",
    4: "K4 其他流动负债.xlsx",
    5: "K5 预计负债.xlsx",
    6: "K6 持有待售资产和负债.xlsx",
    7: "K7 递延收益.xlsx",
}

#: 🔴 foundation 的全 K 基线（KF-P29）—— 本 lane 要证「65 全在这里」
FOUNDATION_DEFINED_NAMES_TOTAL = 82
FOUNDATION_DEFINED_NAMES_REF = 65

#: K1 双变体披露 sheet 名（🔴 上市那张是**半角 `(` + 全角 `）`**，逐字节抄）
K1_LISTED = "附注披露信息(上市公司）"
K1_SOE = "附注披露信息（国企）"

#: 覆盖层影响面（现算校验对象，不作为唯一真源）
REF_CELLS_PER_VARIANT = 35
REF_ROWS_PER_VARIANT = 8
REF_CELLS_TOTAL = 70

#: FC-5 例外序号（前五个 F2-26!J9 / F5-7!G31 / G5-2 45 格 / G5-1!B35 / I3 AA23:AD23）
FC5_EXCEPTION_ORDINAL = 6

_REF_RX = re.compile(r"#REF!")
_RATIO_RX = re.compile(r"^=IF\(C(\d+)=0,0,C\1/\$B\$(\d+)\)$")
_SUM_RX = re.compile(r"=SUM\(([A-Z]+)(\d+):([A-Z]+)(\d+)\)")


# ═══════════════════════════════════════════════════════════════════════════
# fixtures（openpyxl 读模板慢，module scope 缓存）
# ═══════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def k1_book():
    wb = load_workbook(K_TEMPLATE_DIR / LANE1_BOOKS[1], data_only=False)
    yield wb
    wb.close()


@pytest.fixture(scope="module")
def k2_book():
    wb = load_workbook(K_TEMPLATE_DIR / LANE1_BOOKS[2], data_only=False)
    yield wb
    wb.close()


@pytest.fixture(scope="module")
def k1_contract() -> dict:
    return json.loads(K1_CONTRACT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def k2_contract() -> dict:
    return json.loads(K2_CONTRACT.read_text(encoding="utf-8"))


def _defined_names(path: pathlib.Path) -> tuple[int, int]:
    wb = load_workbook(path, read_only=False, data_only=False)
    total = ref = 0
    for dn in wb.defined_names.values():
        total += 1
        val = dn.attr_text if hasattr(dn, "attr_text") else str(dn.value)
        if "#REF!" in str(val):
            ref += 1
    wb.close()
    return total, ref


def _ref_cells(ws) -> dict[int, list[str]]:
    """返回 {行号: [坐标]}，只收公式里含 `#REF!` 的格。"""
    out: dict[int, list[str]] = {}
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, str) and _REF_RX.search(c.value):
                out.setdefault(c.row, []).append(c.coordinate)
    return {r: sorted(v) for r, v in sorted(out.items())}


# ═══════════════════════════════════════════════════════════════════════════
# Task 16 / KA-P39：definedName 基线冻结
# ═══════════════════════════════════════════════════════════════════════════
class TestKAP39DefinedNameBaselineIsFrozen:
    """🔴 基线**不增长、不删**（引用 KC-9）—— definedName 是跨册引用的锚。"""

    @pytest.mark.parametrize("n", LANE1_INDEXES)
    def test_per_book_counts_match_the_baseline(self, n: int) -> None:
        got = _defined_names(K_TEMPLATE_DIR / LANE1_BOOKS[n])
        assert got == LANE1_DEFINED_NAMES_BY_ENTRY[n], (
            f"K{n} 现算 {got} != 基线 {LANE1_DEFINED_NAMES_BY_ENTRY[n]}"
        )

    def test_lane_totals_are_eighty_one_and_sixty_five(self) -> None:
        total = sum(t for t, _ in LANE1_DEFINED_NAMES_BY_ENTRY.values())
        ref = sum(r for _, r in LANE1_DEFINED_NAMES_BY_ENTRY.values())
        assert (total, ref) == (81, 65)

    def test_only_three_books_carry_defined_names(self) -> None:
        """K2 / K4 / K6 有，K1 / K3 / K5 / K7 各 0（两侧都验）。"""
        carriers = {n for n, (t, _) in LANE1_DEFINED_NAMES_BY_ENTRY.items() if t}
        zeros = {n for n, (t, _) in LANE1_DEFINED_NAMES_BY_ENTRY.items() if not t}
        assert carriers == {2, 4, 6}
        assert zeros == {1, 3, 5, 7}
        assert carriers | zeros == set(LANE1_INDEXES)

    def test_every_broken_reference_in_the_k_cycle_lives_in_this_lane(self) -> None:
        """🔴 本 lane 的 65 == 全 K 的 65 ⇒ 断链**一个都不在** lane 2 / foundation。"""
        lane_ref = sum(r for _, r in LANE1_DEFINED_NAMES_BY_ENTRY.values())
        assert lane_ref == FOUNDATION_DEFINED_NAMES_REF == 65
        # 全 K 总数比本 lane 多 1（K10 的那个），但那 1 个**不是**断链
        lane_total = sum(t for t, _ in LANE1_DEFINED_NAMES_BY_ENTRY.values())
        assert FOUNDATION_DEFINED_NAMES_TOTAL - lane_total == 1
        assert FOUNDATION_DEFINED_NAMES_TOTAL - FOUNDATION_DEFINED_NAMES_REF == 17

    def test_k6_has_a_name_but_no_broken_one(self) -> None:
        """🔴 K6 是「有 definedName 但 0 断链」的唯一实证 ⇒ 两个维度不可互推。"""
        total, ref = LANE1_DEFINED_NAMES_BY_ENTRY[6]
        assert (total, ref) == (1, 0)

    def test_healthy_names_are_the_difference_not_a_separate_count(self) -> None:
        """基线自洽：81 − 65 == 16 个健康名（K2 8 + K4 7 + K6 1）。"""
        healthy = {n: t - r for n, (t, r) in LANE1_DEFINED_NAMES_BY_ENTRY.items() if t}
        assert healthy == {2: 8, 4: 7, 6: 1}
        assert sum(healthy.values()) == 81 - 65 == 16


# ═══════════════════════════════════════════════════════════════════════════
# Task 17 / KA-P25~P28：70 格 `#REF!` 的覆盖层修复
# ═══════════════════════════════════════════════════════════════════════════
class TestKAP25RefErrorsAreThirtyFivePerVariant:
    """🔴 算术自检：4 列×5 行 20 + 5 列×3 行 15 == 35；两表 == 70。"""

    @pytest.mark.parametrize("sheet", [K1_LISTED, K1_SOE])
    def test_each_variant_has_thirty_five_cells_over_eight_rows(
        self, k1_book, sheet: str
    ) -> None:
        by_row = _ref_cells(k1_book[sheet])
        assert len(by_row) == REF_ROWS_PER_VARIANT == 8, sorted(by_row)
        assert sum(len(v) for v in by_row.values()) == REF_CELLS_PER_VARIANT == 35

    @pytest.mark.parametrize("sheet", [K1_LISTED, K1_SOE])
    def test_row_shape_is_five_rows_of_four_plus_three_rows_of_five(
        self, k1_book, sheet: str
    ) -> None:
        widths = sorted(len(v) for v in _ref_cells(k1_book[sheet]).values())
        assert widths == [4, 4, 4, 4, 4, 5, 5, 5], widths
        assert 4 * 5 + 5 * 3 == REF_CELLS_PER_VARIANT

    def test_two_variants_sum_to_seventy(self, k1_book) -> None:
        total = sum(
            sum(len(v) for v in _ref_cells(k1_book[s]).values())
            for s in (K1_LISTED, K1_SOE)
        )
        assert total == REF_CELLS_TOTAL == 70

    def test_the_two_subregions_do_not_overlap_and_are_row_contiguous(
        self, k1_book
    ) -> None:
        """两个子区各自行号连续、互不相邻（中间隔着说明文字与合计行）。"""
        for sheet in (K1_LISTED, K1_SOE):
            rows = sorted(_ref_cells(k1_book[sheet]))
            wide = [r for r in rows if len(_ref_cells(k1_book[sheet])[r]) == 4]
            narrow = [r for r in rows if len(_ref_cells(k1_book[sheet])[r]) == 5]
            assert wide == list(range(wide[0], wide[0] + 5))
            assert narrow == list(range(narrow[0], narrow[0] + 3))
            assert narrow[0] - wide[-1] > 1, (sheet, wide, narrow)

    def test_no_other_lane1_book_has_ref_error_cells(self) -> None:
        """🔴 分母收口：70 格全在 K1 一册，其余 6 册 0 格（否则覆盖层漏了）。"""
        for n in LANE1_INDEXES:
            if n == 1:
                continue
            wb = load_workbook(K_TEMPLATE_DIR / LANE1_BOOKS[n], data_only=False)
            hits = {s: _ref_cells(wb[s]) for s in wb.sheetnames}
            wb.close()
            assert all(not v for v in hits.values()), (
                f"K{n} 也有 #REF! 格：{ {k: v for k, v in hits.items() if v} }"
            )


class TestKAP26RatioFormulaStillAlive:
    """🔴 占比列 IF **活着** ⇒ 定性为「部分断链」而非整表失效。"""

    #: 变体 -> (占比列命中数, 账龄小计行)
    EXPECTED = {K1_LISTED: (6, 18), K1_SOE: (6, 13)}

    @pytest.mark.parametrize("sheet", [K1_LISTED, K1_SOE])
    def test_ratio_formulas_are_present_and_use_this_variant_denominator(
        self, k1_book, sheet: str
    ) -> None:
        ws = k1_book[sheet]
        hits: list[tuple[str, str]] = []
        for row in ws.iter_rows():
            for c in row:
                if not isinstance(c.value, str):
                    continue
                m = _RATIO_RX.match(c.value.replace(" ", ""))
                if m:
                    hits.append((c.coordinate, m.group(2)))
        want_count, want_denom = self.EXPECTED[sheet]
        assert len(hits) == want_count, hits
        assert {d for _, d in hits} == {str(want_denom)}, hits

    def test_denominator_is_each_variant_own_aging_subtotal_row(self, k1_book) -> None:
        """🔴 分母**现算**自该变体的账龄小计行，不写死 `$B$18`。

        tasks.md 的 `$B$18` 是上市口径；国企是 `$B$13`。差 5 与 Task 18 的分层深度差同源。
        """
        for sheet, (_, denom_row) in self.EXPECTED.items():
            ws = k1_book[sheet]
            label = ws.cell(row=denom_row, column=1).value
            formula = ws.cell(row=denom_row, column=2).value
            assert isinstance(label, str) and label.replace(" ", "") == "小计", (
                f"{sheet} 的 R{denom_row} 不是小计行：{label!r}"
            )
            assert isinstance(formula, str) and formula.startswith("=SUM("), formula
        assert self.EXPECTED[K1_LISTED][1] - self.EXPECTED[K1_SOE][1] == 5

    @pytest.mark.parametrize("sheet", [K1_LISTED, K1_SOE])
    def test_ratio_cells_are_not_among_the_broken_ones(self, k1_book, sheet: str) -> None:
        """占比格**不在** 70 格里 ⇒ 覆盖层不得碰它们。"""
        broken = {c for v in _ref_cells(k1_book[sheet]).values() for c in v}
        ws = k1_book[sheet]
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and _RATIO_RX.match(c.value.replace(" ", "")):
                    assert c.coordinate not in broken, c.coordinate


class TestKAP27FooterSumsPropagateTheError:
    """🔴 合计行的 SUM **恒传播** `#REF!` ⇒ 不修明细格就修不了合计。"""

    #: 🔴 逐变体登记（`R130` 在两变体指的不是同一个东西）
    FOOTERS = {
        K1_LISTED: {130: 2, 141: 1},
        K1_SOE: {109: 2, 130: 1},
    }

    def test_each_variant_footer_sum_counts_match(self, k1_book) -> None:
        for sheet, rows in self.FOOTERS.items():
            ws = k1_book[sheet]
            for r, want in rows.items():
                sums = [
                    c.coordinate
                    for c in ws[r]
                    if isinstance(c.value, str) and "SUM(" in c.value.upper()
                ]
                assert len(sums) == want, (sheet, r, sums)

    def test_row_130_means_different_things_in_the_two_variants(self, k1_book) -> None:
        """🔴 口径差异判据：同一行号在两变体的 SUM 个数不同 ⇒ 不可共用判据。"""
        assert self.FOOTERS[K1_LISTED][130] == 2
        assert self.FOOTERS[K1_SOE][130] == 1
        assert self.FOOTERS[K1_LISTED][130] != self.FOOTERS[K1_SOE][130]

    def test_every_footer_sum_range_covers_only_broken_cells(self, k1_book) -> None:
        """SUM 区间**整段**落在断链区 ⇒ 传播是必然不是偶然。"""
        for sheet, rows in self.FOOTERS.items():
            broken_rows = set(_ref_cells(k1_book[sheet]))
            ws = k1_book[sheet]
            checked = 0
            for r in rows:
                for c in ws[r]:
                    if not isinstance(c.value, str):
                        continue
                    m = _SUM_RX.search(c.value)
                    if not m:
                        continue
                    lo, hi = int(m.group(2)), int(m.group(4))
                    span = set(range(lo, hi + 1))
                    assert span <= broken_rows, (sheet, c.coordinate, sorted(span))
                    checked += 1
            assert checked == sum(rows.values()), (sheet, checked)


class TestKAP28OverlayIsDeclaredAndTemplateBytesAreUntouched:
    """🔴 走覆盖层（FC-5 第 6 例外），`backend/wp_templates/` 字节一个不动。"""

    def test_contract_declares_the_quirk_with_overlay_handling(
        self, k1_contract: dict
    ) -> None:
        quirks = k1_contract["review"]["known_template_quirks"]
        assert len(quirks) == 1, quirks
        q = quirks[0]
        assert q["handling"] == "overlay_fixed"
        assert q["overlay_action"] == "clear_to_blank_input"
        assert q["severity"] == "partial_break_not_whole_sheet"
        assert str(FC5_EXCEPTION_ORDINAL) in q["handling_note"]
        assert "字节" in q["handling_note"]

    def test_declared_cells_recompute_exactly_against_the_template(
        self, k1_book, k1_contract: dict
    ) -> None:
        """🔴 双向相等：契约声明的格集 == 模板现算的 `#REF!` 格集。"""
        declared = k1_contract["review"]["known_template_quirks"][0]["affected_cells"]
        assert set(declared) == {K1_LISTED, K1_SOE}
        for sheet, regions in declared.items():
            claimed = {c for cells in regions.values() for c in cells}
            actual = {c for v in _ref_cells(k1_book[sheet]).values() for c in v}
            assert claimed == actual, (
                f"{sheet}: 契约多出 {sorted(claimed - actual)} / 漏掉 {sorted(actual - claimed)}"
            )
            assert len(claimed) == REF_CELLS_PER_VARIANT

    def test_must_not_touch_cells_are_all_healthy(
        self, k1_book, k1_contract: dict
    ) -> None:
        """🔴 不误伤：18 个保护格现算都**不是** `#REF!`，且都有公式。"""
        keep = k1_contract["review"]["known_template_quirks"][0]["must_not_touch"]
        assert sum(len(v) for v in keep.values()) == 18, keep
        for sheet, coords in keep.items():
            ws = k1_book[sheet]
            for coord in coords:
                v = ws[coord].value
                assert isinstance(v, str) and v.startswith("="), (sheet, coord, v)
                assert not _REF_RX.search(v), (sheet, coord, v)

    def test_template_sha256_is_unchanged(self, k1_contract: dict) -> None:
        """🔴 模板字节不变的硬判据：契约登记的 sha256 == 现算。"""
        book = K_TEMPLATE_DIR / LANE1_BOOKS[1]
        got = hashlib.sha256(book.read_bytes()).hexdigest()
        assert got == k1_contract["template"]["template_sha256"], (
            "模板字节被改过 ⇒ 覆盖层前提破裂，本册全部 source_ref 失效"
        )
        assert k1_contract["template"]["relative_path"].endswith(book.name)

    def test_overlay_does_not_fabricate_cross_sheet_references(
        self, k1_contract: dict
    ) -> None:
        """🔴 修法是清成空白输入格，**不重建**跨表引用（不编造审计内容）。"""
        q = k1_contract["review"]["known_template_quirks"][0]
        assert q["overlay_formulas"] == {}, q["overlay_formulas"]
        assert "不重建跨表引用" in q["why_clear_not_reconstruct"]

    def test_the_blank_input_shape_has_an_in_sheet_control_group(self, k1_book) -> None:
        """🔴 修法有同 sheet 对照组：同类逐项披露子表本就是空白格 + 合计 SUM。"""
        controls = {K1_LISTED: (range(117, 120), 120), K1_SOE: (range(99, 101), 101)}
        for sheet, (data_rows, footer_row) in controls.items():
            ws = k1_book[sheet]
            for r in data_rows:
                vals = [c.value for c in ws[r] if c.value is not None]
                assert vals == [], (sheet, r, vals)
            sums = [
                c.coordinate for c in ws[footer_row]
                if isinstance(c.value, str) and "SUM(" in c.value.upper()
            ]
            assert sums, (sheet, footer_row)

    def test_payload_requirement_is_declared_to_avoid_false_green(
        self, k1_contract: dict
    ) -> None:
        """🔴 判据载荷要求必须写明「只有这两个子区有数」，否则假绿。"""
        req = k1_contract["review"]["known_template_quirks"][0]["test_payload_requirement"]
        assert "只有这两个子区有数" in req
        assert "假绿" in req and "恒真" in req

    def test_the_writeback_surface_k1_9_is_unaffected(self, k1_contract: dict) -> None:
        """K1-9（本契约的回写面）零 `#REF!`、零裸 IF ⇒ 缺陷不波及。"""
        geom = k1_contract["review"]["sheet_geometry"]
        assert geom["bare_if"] == 0
        note = k1_contract["review"]["known_template_quirks_note"]
        assert "K1-9" in note


# ═══════════════════════════════════════════════════════════════════════════
# Task 18 / KA-P29：双变体账龄分层深度差异登记
# ═══════════════════════════════════════════════════════════════════════════
class TestKAP29AgingDepthDifference:
    """🔴 两变体**不共用同一套行映射**。"""

    #: 上市公司：3 分档 + 内层小计 + 5 分档 + 外层小计 = 3+1+5+1 = **10 行**（两层）
    LISTED_AGING = {
        "inner_bins": (9, 10, 11),      # R9~R11（0-X月 / X-Y月 / 空行）
        "inner_subtotal": 12,            # R12 小计
        "outer_bins": (13, 14, 15, 16, 17),  # R13~R17（1至2年..5年以上）
        "outer_subtotal": 18,            # R18 小计
    }
    #: 国企：6 分档 + 小计 = **7 行**（一层）
    SOE_AGING = {
        "bins": (7, 8, 9, 10, 11, 12),  # R7~R12
        "subtotal": 13,                  # R13 小计
    }

    def test_listed_is_two_tier_and_soe_is_one_tier(self, k1_book) -> None:
        ws_l = k1_book[K1_LISTED]
        ws_s = k1_book[K1_SOE]
        # 上市有「内层小计」行，国企没有
        l_sub = ws_l.cell(row=self.LISTED_AGING["inner_subtotal"], column=2).value
        assert isinstance(l_sub, str) and "SUM(" in l_sub, l_sub
        # 国企的 R12 不是小计而是最后一个分档
        s_r12 = ws_s.cell(row=12, column=1).value
        assert isinstance(s_r12, str) and "5年以上" in s_r12, s_r12

    def test_outer_subtotal_sum_includes_inner_subtotal_correctly(self, k1_book) -> None:
        """🔴 上市 R18 `=SUM(B12:B17)` 外层含内层小计是**正确写法**。

        R12 已经吸收了 R9~R11 的明细 ⇒ `SUM(B12:B17)` 不重不漏。
        把它当缺陷去「改」成 `SUM(B9:B17)` 反而重复计入内层明细 ⇒ **KC-13② 白名单**。
        """
        ws = k1_book[K1_LISTED]
        r18 = ws.cell(row=self.LISTED_AGING["outer_subtotal"], column=2).value
        assert isinstance(r18, str) and r18.startswith("=SUM(")
        m = _SUM_RX.match(r18)
        assert m, r18
        lo, hi = int(m.group(2)), int(m.group(4))
        assert lo == self.LISTED_AGING["inner_subtotal"] == 12
        assert hi == self.LISTED_AGING["outer_bins"][-1] == 17

    def test_the_two_mappings_have_different_row_counts(self) -> None:
        listed_count = (
            len(self.LISTED_AGING["inner_bins"]) + 1
            + len(self.LISTED_AGING["outer_bins"]) + 1
        )
        soe_count = len(self.SOE_AGING["bins"]) + 1
        assert listed_count == 10
        assert soe_count == 7
        assert listed_count != soe_count

    def test_denominator_row_difference_equals_depth_difference(self) -> None:
        """🔴 两变体分母行差 5 与分层深度差**同源**：上市多 3 个内层分档 + 1 内层小计 − 1 行号偏移。"""
        listed_denom = self.LISTED_AGING["outer_subtotal"]  # 18
        soe_denom = self.SOE_AGING["subtotal"]              # 13
        assert listed_denom - soe_denom == 5


# ═══════════════════════════════════════════════════════════════════════════
# Task 19 / KA-P30~P31：K2 孤儿 per-row 键清理（后端侧判据）
# ═══════════════════════════════════════════════════════════════════════════
class TestKAP30OrphanPerRowKeyImplementationExists:
    """🔴 清理逻辑已接线到 K2 的水合路径。"""

    def test_scan_function_is_exported_from_shared_module(self) -> None:
        p = WP_COMPOSABLES / "shared" / "dynamicAdjudicationRows.ts"
        src = cached_text(p)
        assert "export function scanOrphanRowKeys(" in src

    def test_k2_adjudication_calls_prune_on_load(self) -> None:
        p = WP_COMPOSABLES / "useK2Adjudication.ts"
        src = cached_text(p)
        assert "pruneOrphanRowKeys()" in src
        assert "scanOrphanRowKeys" in src

    def test_orphan_keys_with_value_is_exposed(self) -> None:
        p = WP_COMPOSABLES / "useK2Adjudication.ts"
        src = cached_text(p)
        assert "orphanKeysWithValue" in src


# ═══════════════════════════════════════════════════════════════════════════
# Task 20 / KA-P32~P34：审定表K2-1 纯派生标注
# ═══════════════════════════════════════════════════════════════════════════
class TestKAP32AdjudicationK21IsPurelyDerived:
    """🔴 R7:R13 连 A 列都是公式 ⇒ **0 个手工输入位**。"""

    def test_a_column_rows_are_all_formulas_referencing_detail_sheet(
        self, k2_book
    ) -> None:
        ws = k2_book["审定表K2-1"]
        for r in range(7, 14):
            v = ws.cell(row=r, column=1).value
            assert isinstance(v, str) and v.startswith("="), (
                f"A{r} = {v!r} 不是公式 ⇒ 非纯派生"
            )
            assert "明细表K2-2" in v, f"A{r} = {v!r} 不引用明细表 ⇒ 来源可疑"

    def test_contract_marks_derived_and_labels_not_editable(
        self, k2_contract: dict
    ) -> None:
        d = k2_contract["review"]["derivation"]
        assert d["mode"] == "derived"
        assert d["editable_labels"] is False

    def test_contract_marks_writeback_as_noop(self, k2_contract: dict) -> None:
        assert k2_contract["review"]["writeback_direction_is_noop"] is True

    def test_contract_marks_must_not_be_canary(self, k2_contract: dict) -> None:
        assert k2_contract["review"]["must_not_be_canary"] is True


class TestKAP33NewlineCellsAreRegistered:
    """🔴 J5/L5 含单元格内换行符 ⇒ 三边比对逐格字节，禁 strip。"""

    def test_template_really_has_newline_in_j5_and_l5(self, k2_book) -> None:
        ws = k2_book["审定表K2-1"]
        for coord in ("J5", "L5"):
            v = ws[coord].value
            assert isinstance(v, str) and "\n" in v, (
                f"{coord} = {v!r} 不含换行符 ⇒ 契约登记失实"
            )

    def test_contract_registers_the_newline_cells(self, k2_contract: dict) -> None:
        nl = k2_contract["review"]["newline_cells"]
        assert "J5" in nl and "L5" in nl
        assert len(nl) == 2
        for v in nl.values():
            assert "\n" in v

    def test_byte_exact_comparison_is_required(self, k2_contract: dict) -> None:
        assert k2_contract["review"]["byte_exact_comparison_required"] is True


class TestKAP34FooterShapeIsNormalNotDefect:
    """🔴 R14 空行 + R15 `=SUM(B7:B14)` 属 KC-12 正常形态不是缺陷。"""

    def test_row_14_is_blank_in_the_template(self, k2_book) -> None:
        ws = k2_book["审定表K2-1"]
        vals = [c.value for c in ws[14] if c.value is not None]
        assert vals == [], vals

    def test_row_15_has_sum_including_the_blank_row(self, k2_book) -> None:
        ws = k2_book["审定表K2-1"]
        b15 = ws["B15"].value
        assert isinstance(b15, str) and "SUM(B7:B14)" in b15, b15

    def test_contract_marks_the_verdict_as_normal(self, k2_contract: dict) -> None:
        fs = k2_contract["review"]["footer_shape"]
        assert fs["row_14_is_blank"] is True
        assert fs["kc12_verdict"] == "normal_not_defect"

    def test_geometry_is_twenty_three_by_sixteen_merged_nine(
        self, k2_contract: dict
    ) -> None:
        """🔴 现算 `r=23 c=16 merged=9` 与 design 等值。"""
        s = k2_contract["sheets"][0]["sheet_geometry"]
        assert s["max_row"] == 23
        assert s["max_column"] == 16
        assert len(s["merged_ranges"]) == 9
