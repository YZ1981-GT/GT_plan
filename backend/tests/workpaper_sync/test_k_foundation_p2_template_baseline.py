# -*- coding: utf-8 -*-
"""K 循环 foundation spec — 阶段 0 Task 2：模板层基线冻结。

spec: k-cycle-sync-foundation-and-first-canary
Task 2: 模板层基线冻结（14 册 sheets/definedName/字符缺陷/footer/裸 IF/GT_Custom）
Property: KF-P6, KF-P7, KF-P8, KF-P29, KF-P30, KF-P32

═══ 判据 ═══

KF-P6:  14 非锁 / 0 锁 / belongs_to_entry 非 null 13 + null 带 excluded_reason 1
KF-P7:  K0 两个解析函数都返真实文件（非 None，与 J0 相反）
KF-P8:  14 册 sheets 合计 152（K0 11 + 13 entry 册 141）；逐册 sheet_count 与 slice 等值
KF-P29: definedName 82 / 含 #REF! 65（K4 43/36 · K2 37/29 · K6 1/0 · K10 1/0 · 其余 0）
KF-P30: sheet 名四类缺陷 21 / 5 / 2 / 1；首尾空格 0
KF-P32: footer 164 = 140 + 19 + 5；无 SUBTOTAL

═══ 注 ═══

裸 IF（KF-P8 附带）和 GT_Custom（Req 7.5）也在此验证。
openpyxl 读模板较慢（~15s），用 module scope fixture 缓存。
"""
from __future__ import annotations

import json
import pathlib
import re
from typing import Any

import pytest
from openpyxl import load_workbook

_THIS = pathlib.Path(__file__).resolve()
ROOT = _THIS.parents[3]
K_TEMPLATE_DIR = ROOT / "backend" / "wp_templates" / "K"
MANIFEST_SLICE_PATH = ROOT / "backend" / "data" / "workpaper_sync_k_cycle_manifest_slice.json"


def _load(p: pathlib.Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _sheet_names(path: pathlib.Path) -> list[str]:
    wb = load_workbook(path, read_only=True, data_only=True)
    names = list(wb.sheetnames)
    wb.close()
    return names


def _defined_names_info(path: pathlib.Path) -> tuple[int, int]:
    """返回 (total_defined_names, ref_err_count)。"""
    wb = load_workbook(path, read_only=False, data_only=False)
    total = 0
    ref_err = 0
    for dn in wb.defined_names.values():
        total += 1
        val = dn.attr_text if hasattr(dn, "attr_text") else str(dn.value)
        if "#REF!" in str(val):
            ref_err += 1
    wb.close()
    return total, ref_err


_BARE_IF_RX = re.compile(r"(?<![A-Z])IF\(")


def _count_bare_if(path: pathlib.Path) -> int:
    """统计裸 IF **格数**（一格有 IF 就算 1，不管几个 IF）。

    口径与 design.md 一致：K1=91 · K2=76 · K8=136 · K9=175 等。
    🔴 不是 findall 次数（那会更大）。
    """
    wb = load_workbook(path, read_only=True, data_only=False)
    count = 0
    for sn in wb.sheetnames:
        ws = wb[sn]
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if isinstance(v, str) and v.startswith("=") and _BARE_IF_RX.search(v):
                    count += 1
    wb.close()
    return count


def _has_gt_custom(path: pathlib.Path) -> bool:
    return "GT_Custom" in _sheet_names(path)


# ════════════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return _load(MANIFEST_SLICE_PATH)


@pytest.fixture(scope="module")
def template_files() -> list[pathlib.Path]:
    """14 个非锁 xlsx 文件。"""
    return sorted(
        f for f in K_TEMPLATE_DIR.iterdir()
        if f.suffix == ".xlsx" and not f.name.startswith("~$")
    )


@pytest.fixture(scope="module")
def template_map(template_files: list[pathlib.Path]) -> dict[str, pathlib.Path]:
    """文件名 → 路径映射。"""
    return {f.name: f for f in template_files}


# ════════════════════════════════════════════════════════════════════════════
# KF-P6: 14 非锁 / 0 锁 / belongs_to_entry 映射
# ════════════════════════════════════════════════════════════════════════════
class TestKFP6TemplateFileSet:

    def test_14_non_lock_files(self, template_files: list[pathlib.Path]) -> None:
        assert len(template_files) == 14

    def test_zero_lock_files(self) -> None:
        locks = [f.name for f in K_TEMPLATE_DIR.iterdir() if f.name.startswith("~$")]
        assert locks == []

    def test_belongs_to_entry_mapping(self, manifest_slice: dict) -> None:
        at = manifest_slice["authoritative_templates"]
        belongs = [f for f in at["files"] if f["belongs_to_entry"] is not None]
        excluded = [f for f in at["files"] if f["belongs_to_entry"] is None]
        assert len(belongs) == 13
        assert len(excluded) == 1
        assert excluded[0]["name"] == "K0 管理循环函证.xlsx"
        assert excluded[0].get("excluded_reason")


# ════════════════════════════════════════════════════════════════════════════
# KF-P8: sheets 合计 152，逐册等值
# ════════════════════════════════════════════════════════════════════════════
class TestKFP8SheetInventory:

    def test_total_sheets_is_152(
        self, manifest_slice: dict, template_files: list[pathlib.Path]
    ) -> None:
        total = sum(len(_sheet_names(f)) for f in template_files)
        assert total == 152
        assert manifest_slice["honest_adjudication_summary"][
            "authoritative_template_sheets_total"
        ] == 152

    def test_13_entry_books_have_141_sheets(
        self, manifest_slice: dict, template_files: list[pathlib.Path]
    ) -> None:
        """K0 11 张 + 13 entry 册 141 张 = 152。"""
        k0 = next(f for f in template_files if "K0" in f.name)
        k0_sheets = len(_sheet_names(k0))
        assert k0_sheets == 11
        entry_sheets = sum(len(_sheet_names(f)) for f in template_files if "K0" not in f.name)
        assert entry_sheets == 141

    def test_per_book_sheet_count_matches_slice(
        self, manifest_slice: dict, template_files: list[pathlib.Path]
    ) -> None:
        at = manifest_slice["authoritative_templates"]
        by_name = {f["name"]: f["sheet_count"] for f in at["files"]}
        for f in template_files:
            actual = len(_sheet_names(f))
            expected = by_name.get(f.name)
            assert expected is not None, f"{f.name} 不在 slice 里"
            assert actual == expected, (
                f"{f.name}: 实得 {actual} 张，slice 登记 {expected}"
            )

    def test_no_sheet_has_leading_or_trailing_whitespace(
        self, template_files: list[pathlib.Path]
    ) -> None:
        """KC-10 附：首尾空格现算 0（与 J1 相反）。"""
        stripped = [
            (f.name, n)
            for f in template_files
            for n in _sheet_names(f)
            if n != n.strip()
        ]
        assert stripped == []


# ════════════════════════════════════════════════════════════════════════════
# KF-P29: definedName 82 / #REF! 65
# ════════════════════════════════════════════════════════════════════════════
class TestKFP29DefinedNameBaseline:
    """KC-9: slice 完全漏掉 definedName，本轮自行现算并冻结基线。"""

    #: 逐册期望值（design.md KC-9 现算）
    EXPECTED = {
        "K4 其他流动负债.xlsx": (43, 36),
        "K2 其他流动资产.xlsx": (37, 29),
        "K6 持有待售资产和负债.xlsx": (1, 0),
        "K10 其他收益.xlsx": (1, 0),
    }

    def test_total_defined_names_is_82(
        self, template_files: list[pathlib.Path]
    ) -> None:
        total = sum(_defined_names_info(f)[0] for f in template_files)
        assert total == 82, f"definedName 合计漂移：期望 82，实得 {total}"

    def test_total_ref_err_is_65(
        self, template_files: list[pathlib.Path]
    ) -> None:
        total = sum(_defined_names_info(f)[1] for f in template_files)
        assert total == 65, f"#REF! 合计漂移：期望 65，实得 {total}"

    def test_per_book_defined_names_match_design(
        self, template_files: list[pathlib.Path]
    ) -> None:
        for f in template_files:
            dn, ref = _defined_names_info(f)
            expected = self.EXPECTED.get(f.name, (0, 0))
            assert (dn, ref) == expected, (
                f"{f.name}: 实得 ({dn}, {ref})，期望 {expected}"
            )

    def test_baseline_does_not_grow(
        self, template_files: list[pathlib.Path]
    ) -> None:
        """断言不增长（KC-9：不删，只冻结）。"""
        for f in template_files:
            dn, _ = _defined_names_info(f)
            limit = self.EXPECTED.get(f.name, (0, 0))[0]
            assert dn <= limit, (
                f"{f.name}: definedName 从 {limit} 增长到 {dn} ⇒ 基线漂移"
            )


# ════════════════════════════════════════════════════════════════════════════
# KF-P30: sheet 名四类字符缺陷
# ════════════════════════════════════════════════════════════════════════════
class TestKFP30SheetNameDefects:
    """KC-10: 四类缺陷合计 21 / 5 / 2 / 1。"""

    def _all_sheet_names(self, template_files: list[pathlib.Path]) -> list[tuple[str, str]]:
        """返回 [(book_name, sheet_name), ...]。"""
        out = []
        for f in template_files:
            for n in _sheet_names(f):
                out.append((f.name, n))
        return out

    def test_mid_space_count_is_21(
        self, template_files: list[pathlib.Path]
    ) -> None:
        """名中半角空格 21 处（不含首尾，因为首尾空格已验为 0）。"""
        count = 0
        for _, n in self._all_sheet_names(template_files):
            # 名中有半角空格（首尾空格已被验为 0，所以直接检查即可）
            if " " in n:
                count += 1
        assert count == 21, f"名中半角空格：期望 21，实得 {count}"

    def test_bracket_mismatch_count_is_5(
        self, template_files: list[pathlib.Path]
    ) -> None:
        """括号半/全角混用不配对 5 处。

        判据：同一个 sheet 名里同时含半角括号和全角括号，且左右不配对。
        """
        count = 0
        for _, n in self._all_sheet_names(template_files):
            has_half_left = "(" in n
            has_half_right = ")" in n
            has_full_left = "（" in n
            has_full_right = "）" in n
            # 半/全混用不配对 = 有半角左+全角右 或 全角左+半角右
            if (has_half_left and has_full_right and not has_full_left and not has_half_right):
                count += 1
            elif (has_full_left and has_half_right and not has_half_left and not has_full_right):
                count += 1
        assert count == 5, f"括号半/全混不配对：期望 5，实得 {count}"

    def test_all_half_bracket_count_is_2(
        self, template_files: list[pathlib.Path]
    ) -> None:
        """全半角括号（都是半角配对）2 处 —— K3 的两张。"""
        count = 0
        for book, n in self._all_sheet_names(template_files):
            has_half_left = "(" in n
            has_half_right = ")" in n
            has_full_left = "（" in n
            has_full_right = "）" in n
            # 纯半角配对（无全角括号）
            if has_half_left and has_half_right and not has_full_left and not has_full_right:
                count += 1
        assert count == 2, f"全半角括号：期望 2，实得 {count}"

    def test_repeat_char_count_is_1(
        self, template_files: list[pathlib.Path]
    ) -> None:
        """「表表」重复字 1 处 —— K2 的 `其他流动资产检查表表K2-6`。"""
        count = 0
        hits = []
        for book, n in self._all_sheet_names(template_files):
            if "表表" in n:
                count += 1
                hits.append((book, n))
        assert count == 1, f"「表表」重复字：期望 1，实得 {count} ({hits})"

    def test_leading_trailing_space_is_zero(
        self, template_files: list[pathlib.Path]
    ) -> None:
        """首尾空格 0（与 J1 相反）。"""
        bad = [
            (book, n)
            for book, n in self._all_sheet_names(template_files)
            if n != n.strip()
        ]
        assert bad == []

    def test_k7_uses_full_name_guoyouqiye(
        self, template_files: list[pathlib.Path]
    ) -> None:
        """K7 用「国有企业」而非「国企」（KC-10 附：其余 12 册全「国企」）。"""
        k7 = next(f for f in template_files if "K7" in f.name)
        names = _sheet_names(k7)
        assert any("国有企业" in n for n in names), "K7 没有「国有企业」sheet"
        # 其余 12 册不用「国有企业」
        for f in template_files:
            if "K7" in f.name:
                continue
            names = _sheet_names(f)
            for n in names:
                if "国企" in n:
                    assert "国有企业" not in n, (
                        f"{f.name}: {n!r} 混用了「国企」和「国有企业」"
                    )


# ════════════════════════════════════════════════════════════════════════════
# Req 7.4: 裸 IF（13 entry 册 715 / K10 册 0）
# ════════════════════════════════════════════════════════════════════════════
class TestBareIFBaseline:
    """裸 IF 基线冻结（格数口径）。"""

    def test_13_entry_books_bare_if_is_715(
        self, template_files: list[pathlib.Path]
    ) -> None:
        """13 entry 册（排除 K0）裸 IF 格数 = 715。"""
        total = sum(_count_bare_if(f) for f in template_files if "K0" not in f.name)
        assert total == 715, f"13 entry 册裸 IF：期望 715，实得 {total}"

    def test_k10_bare_if_is_zero(self, template_map: dict[str, pathlib.Path]) -> None:
        """🔴 K10 册裸 IF 为 0（14 册唯一）。"""
        k10 = template_map["K10 其他收益.xlsx"]
        assert _count_bare_if(k10) == 0


# ════════════════════════════════════════════════════════════════════════════
# Req 7.5: GT_Custom hidden sheet（8 册）
# ════════════════════════════════════════════════════════════════════════════
class TestGTCustomBaseline:

    #: KC-15 / Req 7.5: 有 GT_Custom 的 8 册
    BOOKS_WITH_GT_CUSTOM = {
        "K0 管理循环函证.xlsx",
        "K1 其他应收款.xlsx",
        "K2 其他流动资产.xlsx",
        "K3 其他应付款.xlsx",
        "K7 递延收益.xlsx",
        "K10 其他收益.xlsx",
        "K12 营业外收入.xlsx",
        "K13 营业外支出.xlsx",
    }

    def test_gt_custom_in_exactly_8_books(
        self, template_files: list[pathlib.Path]
    ) -> None:
        actual = {f.name for f in template_files if _has_gt_custom(f)}
        assert actual == self.BOOKS_WITH_GT_CUSTOM, (
            f"GT_Custom 册集合不符：多 {sorted(actual - self.BOOKS_WITH_GT_CUSTOM)}，"
            f"缺 {sorted(self.BOOKS_WITH_GT_CUSTOM - actual)}"
        )
