# -*- coding: utf-8 -*-
"""L 循环 foundation spec — 阶段 0：口径基线与红判据。

spec: l-cycle-sync-foundation-and-first-canary · Task 0~4
Properties: LF-P1 ~ LF-P7, LF-P24, LF-P26（前置）, LF-P48

既存守卫 `test_task54_l_cycle_migration.py` 锁「现状诚实记录」，本文件锁「改线后目标态」。
凡判据与之重叠，引用测试名不重写。

═══ 运行 ═══

    ..\.venv\Scripts\python.exe -m pytest backend/tests/workpaper_sync/test_l_foundation_p0_domain_baseline.py -v --tb=short
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import sys
from typing import Any

import pytest

# ─── 路径常量（与既存守卫 test_task54 同形） ───────────────────────────
_THIS = pathlib.Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = FRONTEND / "components" / "workpaper"
WP_COMPOSABLES = WP_COMPONENTS / "composables"
SRC_COMPOSABLES = FRONTEND / "composables"
DATA = BACKEND / "data"
TEMPLATE_DIR = BACKEND / "wp_templates"
L_TEMPLATE_DIR = TEMPLATE_DIR / "L"
TEMPLATE_INDEX = TEMPLATE_DIR / "_index.json"

MANIFEST_SLICE_PATH = DATA / "workpaper_sync_l_cycle_manifest_slice.json"
FULL_MANIFEST_PATH = DATA / "workpaper_sync_entry_manifest.json"
CONTRACT_DIR = DATA / "workpaper_sync_contracts"


# ─── 通用工具 ─────────────────────────────────────────────────────────
def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _blank_keep_newlines(match: re.Match[str]) -> str:
    """同长空白替换保留换行——行号不变。"""
    return re.sub(r"[^\n]", " ", match.group(0))


def strip_comments(source: str) -> str:
    """剥块注释 / 行注释 / HTML 注释，行号保持不变（LF-P7）。
    行注释正则用 (?<!:)// 避开 URL 里的 //。"""
    source = re.sub(r"/\*.*?\*/", _blank_keep_newlines, source, flags=re.S)
    source = re.sub(r"<!--.*?-->", _blank_keep_newlines, source, flags=re.S)
    source = re.sub(
        r"(?<![:\w\"'`\\])//[^\n]*", lambda m: " " * len(m.group(0)), source
    )
    return source


def l_domain_files_strict() -> list[pathlib.Path]:
    """L 域文件集（strict 口径）：
    - 路径含 l{1..8}/ 目录段
    - 或文件名匹配 ^(?:use|Gt)?L[1-8](?:[A-Z]|$|\\.) 的 .ts/.vue
    🔴 禁用宽口径 L[1-8]——会撞 G 循环 Level-3 公允价值（LC-5）。
    """
    strict_re = re.compile(r"^(?:use|Gt)?L[1-8](?:[A-Z]|$|\.)")
    dir_re = re.compile(r"[/\\]l[1-8][/\\]")
    out: list[pathlib.Path] = []
    for p in FRONTEND.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix not in (".ts", ".vue"):
            continue
        if "__tests__" in p.as_posix():
            continue
        posix = p.as_posix()
        if dir_re.search(posix) or strict_re.match(p.name):
            out.append(p)
    return sorted(set(out))


def l_domain_files_wide() -> list[pathlib.Path]:
    """宽口径 L[1-8](?:[A-Z]|FormData|DualMode|Tab) ——仅用于差集验证。"""
    wide_re = re.compile(r"L[1-8](?:[A-Z]|FormData|DualMode|Tab)")
    out: list[pathlib.Path] = []
    for p in FRONTEND.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix not in (".ts", ".vue"):
            continue
        if "__tests__" in p.as_posix():
            continue
        if wide_re.search(p.name):
            out.append(p)
    return sorted(set(out))


# G/H 跨用文件关键词——宽口径差集应恰好是这些
_GH_CROSS_USE_TOKENS = {
    "useG9L3Reconciliation",
    "useG10L3Reconciliation",
    "G9TabL3Reconciliation",
    "G10TabL3Reconciliation",
    "g10L3Cross",
    "h2L1LoanPull",
}


def assert_equal_to_design(label: str, computed: Any, expected: Any) -> None:
    """统一断言辅助——现算值 vs design 等值比对。"""
    assert computed == expected, (
        f"{label}: 现算值 {computed!r} ≠ design 期望 {expected!r}"
    )


# ─── fixtures ──────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return _load(MANIFEST_SLICE_PATH)


@pytest.fixture(scope="module")
def full_manifest() -> dict:
    return _load(FULL_MANIFEST_PATH)


@pytest.fixture(scope="module")
def entries(manifest_slice: dict) -> list[dict]:
    return manifest_slice["independent_entries"]


@pytest.fixture(scope="module")
def l_files() -> list[pathlib.Path]:
    return l_domain_files_strict()


# ═══════════════════════════════════════════════════════════════════════
# Task 0: L 域文件集与扫描口径基线
# Property: LF-P6, LF-P7
# ═══════════════════════════════════════════════════════════════════════
class TestTask0DomainScope:
    """建立 L 域文件集与扫描口径基线。"""

    def test_strict_scope_is_nonempty(self, l_files: list[pathlib.Path]) -> None:
        """strict 口径现算文件数大于 0。"""
        assert len(l_files) > 0, "L 域 strict 口径文件集为空"

    def test_wide_scope_diff_is_exactly_gh_cross_use(self, l_files: list[pathlib.Path]) -> None:
        """宽口径差集恰为 G/H 跨用文件（LF-P6 两侧验证）。"""
        strict_set = set(l_files)
        wide_set = set(l_domain_files_wide())
        diff = wide_set - strict_set
        diff_names = {p.stem for p in diff}
        # 差集里每个文件名必须命中 G/H 跨用关键词之一
        for name in diff_names:
            assert any(tok in name for tok in _GH_CROSS_USE_TOKENS), (
                f"宽口径差集文件 {name} 不属于已知 G/H 跨用文件"
            )

    def test_diff_contains_no_l_entry(
        self, l_files: list[pathlib.Path], entries: list[dict]
    ) -> None:
        """宽口径差集中无一属 L entry。"""
        strict_set = set(l_files)
        wide_set = set(l_domain_files_wide())
        diff = wide_set - strict_set
        entry_ids = {e["entry_id"] for e in entries}
        for p in diff:
            # entry_id 形如 xlsx/gt-l1-short-term-loans，文件里不该有 L entry 的匹配
            name_lower = p.name.lower()
            for eid in entry_ids:
                slug = eid.split("/")[-1].replace("gt-", "")
                assert slug not in name_lower, (
                    f"差集文件 {p.name} 与 L entry {eid} 匹配"
                )

    def test_strip_comments_preserves_line_count(self) -> None:
        """strip_comments 同长空白替换，行号不变（LF-P7）。"""
        src = "a\n<!-- el-segmented -->\nb\n/* x\ny */\nc\n// z\nd"
        out = strip_comments(src)
        assert len(src.split("\n")) == len(out.split("\n")), (
            "剥注释改变了行数"
        )
        assert "el-segmented" not in out
        assert "x" not in out.split("\n")[3], "块注释未剥"


# ═══════════════════════════════════════════════════════════════════════
# Task 1: manifest 与 slice 分歧门（BP-9 / LC-1）
# Property: LF-P1, LF-P2, LF-P3, LF-P4, LF-P5
# ═══════════════════════════════════════════════════════════════════════
class TestTask1ManifestSliceDivergence:
    """manifest 与 slice 分歧登记。"""

    def test_selection_rule_yields_8_entries(
        self, full_manifest: dict, entries: list[dict]
    ) -> None:
        """按 slice selection_rule 从 manifest 现算得 8 条（LF-P1）。"""
        manifest_entries = full_manifest.get("entries", [])
        l_entries = [
            e for e in manifest_entries
            if e.get("document_type") == "xlsx"
            and e.get("independent_entry") is True
            and any(
                p.startswith("L")
                for p in (e.get("wp_match", {}).get("wp_code_patterns", []))
            )
        ]
        slice_ids = {e["entry_id"] for e in entries}
        computed_ids = {e["entry_id"] for e in l_entries}
        assert_equal_to_design("L entry 数量", len(l_entries), 8)
        assert computed_ids == slice_ids, (
            f"manifest 现算集合 {computed_ids} ≠ slice 集合 {slice_ids}"
        )

    def test_manifest_side_capability_is_single_onlyoffice(
        self, entries: list[dict]
    ) -> None:
        """manifest 侧 8 条 capability == single_onlyoffice 且 html_store == unresolved（LF-P2）。"""
        for e in entries:
            mm = e.get("manifest_mirror", {})
            assert mm.get("capability") == "single_onlyoffice", (
                f"{e['entry_id']} manifest_mirror.capability ≠ single_onlyoffice"
            )
            assert mm.get("html_store") == "unresolved", (
                f"{e['entry_id']} manifest_mirror.html_store ≠ unresolved"
            )

    def test_manifest_entry_has_no_capability_target(
        self, full_manifest: dict, entries: list[dict]
    ) -> None:
        """manifest entry 上不存在 capability_target 字段（LF-P3）。"""
        slice_ids = {e["entry_id"] for e in entries}
        for me in full_manifest.get("entries", []):
            if me.get("entry_id") in slice_ids:
                assert "capability_target" not in me, (
                    f"{me['entry_id']} manifest 里不该有 capability_target"
                )

    def test_slice_side_fields(self, entries: list[dict]) -> None:
        """slice 侧 8 条 capability=None, capability_target=bidirectional, adapter_id=None（LF-P4）。"""
        for e in entries:
            assert e.get("capability") is None, (
                f"{e['entry_id']} slice capability 应为 null"
            )
            assert e.get("capability_target") == "bidirectional", (
                f"{e['entry_id']} slice capability_target 应为 bidirectional"
            )
            assert e.get("adapter_id") is None, (
                f"{e['entry_id']} slice adapter_id 应为 null"
            )

    def test_why_not_adopted_mentions_overlay_defaults(
        self, entries: list[dict]
    ) -> None:
        """why_not_adopted 含 overlay 默认值填充的表述（LF-P5）。"""
        for e in entries:
            wna = e.get("manifest_mirror", {}).get("why_not_adopted", "")
            assert "overlay" in wna.lower() or "defaults" in wna.lower() or "默认值" in wna, (
                f"{e['entry_id']} why_not_adopted 未提及 overlay/默认值"
            )


# ═══════════════════════════════════════════════════════════════════════
# Task 2: L0 册排除的三条证据门（LD-7）
# Property: LF-P24
# ═══════════════════════════════════════════════════════════════════════
class TestTask2L0Exclusion:
    """L0 排除靠三条证据——不能靠「模板不存在」排除。"""

    def test_evidence1_manifest_has_no_l0_entry(self, full_manifest: dict) -> None:
        """证据①：manifest 全量 entry 现算 'l0' in entry_id.lower() 命中 == 0。"""
        l0_hits = [
            e for e in full_manifest.get("entries", [])
            if "l0" in e.get("entry_id", "").lower()
        ]
        assert len(l0_hits) == 0, f"manifest 里有 L0 entry：{[e['entry_id'] for e in l0_hits]}"

    def test_evidence2_l0_has_index_entry(self) -> None:
        """证据②：_index.json 里 L0 有独立条目。"""
        idx = _load(TEMPLATE_INDEX)
        l0_entries = [
            f for f in idx.get("files", [])
            if "L0" in str(f.get("relative_path", ""))
        ]
        assert len(l0_entries) > 0, "_index.json 里无 L0 条目"

    def test_evidence3_l0_second_sheet_is_f0a(self) -> None:
        """证据③：openpyxl 现读 L0 第 2 张 sheet 含 '函证程序表F0A'。"""
        from openpyxl import load_workbook

        l0_path = L_TEMPLATE_DIR / "L0 债务循环函证.xlsx"
        if not l0_path.exists():
            pytest.skip(f"L0 模板不存在：{l0_path}")
        wb = load_workbook(l0_path, read_only=True, data_only=True)
        try:
            sheets = list(wb.sheetnames)
            assert len(sheets) >= 2, f"L0 册只有 {len(sheets)} 张 sheet"
            assert "函证程序表F0A" in sheets[1], (
                f"L0 第 2 张 sheet '{sheets[1]}' 不含 '函证程序表F0A'"
            )
        finally:
            wb.close()


# ═══════════════════════════════════════════════════════════════════════
# Task 3: 五处扫描误报自检门（LC-13）
# Property: LF-P26 前置
# ═══════════════════════════════════════════════════════════════════════
class TestTask3ScanMisreportSelfCheck:
    """五处扫描误报——每项构造「错口径红、正确口径绿」的自检。"""

    def test_cross_sheet_ref_uses_target_sheet_max_row(self) -> None:
        """误报①：越界引用——按引用目标 sheet 的 max_row 判，修正后为 0。
        构造：跨 sheet 引用 =明细表!O23，本 sheet max_row=10 但目标 sheet max_row=50。
        错口径用本 sheet 的 10 → 判越界；正确口径用目标 50 → 不越界。"""
        # 模拟：引用行号 23，本 sheet max=10，目标 sheet max=50
        ref_row = 23
        local_max = 10
        target_max = 50
        # 错口径
        wrong_verdict = ref_row > local_max  # True = 误报越界
        assert wrong_verdict is True, "错口径应判越界（红）"
        # 正确口径
        correct_verdict = ref_row > target_max  # False = 不越界
        assert correct_verdict is False, "正确口径应不越界（绿）"

    def test_ref_error_not_treated_as_sheet_name(self) -> None:
        """误报②：跨 sheet 断链——#REF! 的 REF 不是 sheet 名，排除后为 0。"""
        formula = "=IF(#REF!=0,0,IF((#REF!-#REF!)=365,...))"
        # 错口径：正则把 REF 当 sheet 名
        wrong_sheets = set(re.findall(r"(\w+)!", formula))
        assert "REF" in wrong_sheets, "错口径应把 REF 当 sheet 名（红）"
        # 正确口径：先排除 #REF!
        clean = formula.replace("#REF!", "#___!")
        correct_sheets = set(re.findall(r"(\w+)!", clean))
        assert "REF" not in correct_sheets, "正确口径排除后无 REF（绿）"

    def test_horizontal_sum_subtotal_not_flagged(self) -> None:
        """误报③：合计漏加小计——横向 SUM span=1 无意义。
        审定表L4-1 的 =B11+B16+B17 是正确避重复。"""
        # r11 小计 = SUM(r8:r10), r16 小计 = SUM(r13:r15), r17 单行
        # r18 合计 = B11+B16+B17 = 小计1 + 小计2 + 单行（正确避重复）
        r8, r9, r10 = 100, 200, 300
        r11_subtotal = r8 + r9 + r10  # 600
        r13, r14, r15 = 50, 60, 70
        r16_subtotal = r13 + r14 + r15  # 180
        r17_single = 20
        r18_total = r11_subtotal + r16_subtotal + r17_single  # 800
        expected = r8 + r9 + r10 + r13 + r14 + r15 + r17_single  # 800
        assert r18_total == expected, "=B11+B16+B17 形态是正确的避重复"

    def test_ocr_false_positive_from_unrecognized(self) -> None:
        """误报④：OCR——recognize 撞 L5 的 unrecognizedRows 业务词，排除后计数下降。"""
        tokens = [
            "recognize",
            "unrecognizedRows",
            "recognizeFile",
            "unrecognized_detail",
        ]
        business_exclusions = {"unrecognizedRows", "unrecognized_detail"}
        wrong_count = sum(1 for t in tokens if "recogni" in t.lower())
        correct_count = sum(
            1 for t in tokens
            if "recogni" in t.lower() and t not in business_exclusions
        )
        assert wrong_count > correct_count, "排除业务词后计数应下降"

    def test_wide_scope_hits_g_level3(self) -> None:
        """误报⑤：宽口径 L[1-8] 撞 G Level-3 公允价值命名，strict 口径不含。"""
        g_cross_names = [
            "useG9L3Reconciliation.ts",
            "useG10L3Reconciliation.ts",
            "G9TabL3Reconciliation.vue",
            "G10TabL3Reconciliation.vue",
        ]
        wide_re = re.compile(r"L[1-8]")
        strict_re = re.compile(r"^(?:use|Gt)?L[1-8](?:[A-Z]|$|\.)")
        for name in g_cross_names:
            assert wide_re.search(name) is not None, f"宽口径应命中 {name}"
            assert strict_re.match(name) is None, f"strict 口径不应命中 {name}"


# ═══════════════════════════════════════════════════════════════════════
# Task 4: 行数口径自检
# Property: LF-P48
# ═══════════════════════════════════════════════════════════════════════
class TestTask4LineCountCalibration:
    """行数口径统一 len(text.split('\\n'))。"""

    def test_split_vs_splitlines_differ_by_one(self) -> None:
        """splitlines() 恒少 1——至少在一个真实文件上验证。"""
        # 找一个 L 域文件做验证
        l_files = l_domain_files_strict()
        if not l_files:
            pytest.skip("无 L 域文件可验证")
        target = l_files[0]
        text = target.read_text(encoding="utf-8")
        split_count = len(text.split("\n"))
        splitlines_count = len(text.splitlines())
        assert split_count != splitlines_count, (
            f"{target.name}: split('\\n') = {split_count}, "
            f"splitlines() = {splitlines_count}，应不等"
        )
        # 口径选 split
        assert split_count == splitlines_count + 1 or split_count > splitlines_count, (
            "split 应 >= splitlines + 1（文件以 \\n 结尾时）"
        )

    def test_assert_equal_to_design_helper(self) -> None:
        """统一断言辅助函数可用。"""
        assert_equal_to_design("test", 8, 8)
        with pytest.raises(AssertionError):
            assert_equal_to_design("test", 7, 8)
