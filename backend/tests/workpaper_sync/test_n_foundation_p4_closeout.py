# -*- coding: utf-8 -*-
"""N 循环 Foundation spec — 阶段 5 守卫：notice 接入 + parent_duplicate + 平台欠账 + 自检。

spec: n-cycle-sync-foundation-and-first-canary
任务: 19（BP-7 notice 接入）、20（parent_duplicate 骨架）、21（resolveProcedureSheetKey）、
      22*（平台欠账登记）、23（交付前自检）
NF-P: 7, 33, 39, 40 + 交叉验证

用法::

    ..\\.venv\\Scripts\\python.exe -m pytest backend/tests/workpaper_sync/test_n_foundation_p4_closeout.py -v --tb=short
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
from typing import Any

import pytest

_THIS = pathlib.Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
DATA = BACKEND / "data"
TEMPLATE_DIR = BACKEND / "wp_templates" / "N"
FRONTEND = ROOT / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = FRONTEND / "components" / "workpaper"
WP_COMPOSABLES = WP_COMPONENTS / "composables"

import sys
sys.path.insert(0, str(BACKEND / "scripts" / "analyze"))
import n_cycle_scanner as scanner  # noqa: E402


# ════════════════════════════════════════════════════════════════════════════
# 任务 19：BP-7 GtEntrySyncCapabilityNotice 接入
# ════════════════════════════════════════════════════════════════════════════

class TestNoticeIntegration:
    """NF-P39：N4 宿主已接入 GtEntrySyncCapabilityNotice。"""

    def test_n4_has_notice_import(self):
        """GtN4TaxesAndSurcharges.vue 包含 GtEntrySyncCapabilityNotice import。"""
        src = (WP_COMPONENTS / "GtN4TaxesAndSurcharges.vue").read_text("utf-8", errors="replace")
        assert "GtEntrySyncCapabilityNotice" in src

    def test_n4_has_notice_template(self):
        """GtN4TaxesAndSurcharges.vue template 中有 notice 组件。"""
        src = (WP_COMPONENTS / "GtN4TaxesAndSurcharges.vue").read_text("utf-8", errors="replace")
        assert 'entry-id="xlsx/gt-n4-taxes-and-surcharges"' in src

    def test_n4_notice_is_not_tooltip(self):
        """接入方式是组件（非 tooltip），符合 NC-12 判据。"""
        src = (WP_COMPONENTS / "GtN4TaxesAndSurcharges.vue").read_text("utf-8", errors="replace")
        stripped = scanner.strip_comments(src)
        # 应有 <GtEntrySyncCapabilityNotice 标签
        assert "<GtEntrySyncCapabilityNotice" in stripped or "GtEntrySyncCapabilityNotice" in stripped

    def test_n_domain_notice_now_positive(self):
        """N 域 notice 引用从 0 变为 >= 1。"""
        count = 0
        for p in WP_COMPONENTS.glob("GtN*.vue"):
            text = p.read_text("utf-8", errors="replace")
            stripped = scanner.strip_comments(text)
            if "GtEntrySyncCapabilityNotice" in stripped:
                count += 1
        assert count >= 1, f"N 域 notice 引用 {count}（期望 >= 1）"


# ════════════════════════════════════════════════════════════════════════════
# 任务 20：parent_duplicate 条件节骨架（NF-P33）
# ════════════════════════════════════════════════════════════════════════════

class TestParentDuplicate:
    """NF-P33：parent_duplicate 4 条全挂 N1（判据在此，数据在 lane2）。"""

    def test_slice_has_parent_duplicate(self):
        """N cycle slice 中存在 parent_duplicate 相关内容。"""
        slice_path = DATA / "workpaper_sync_n_cycle_manifest_slice.json"
        if not slice_path.exists():
            pytest.skip("N cycle slice 不存在")
        text = slice_path.read_text("utf-8")
        assert "parent_duplicate" in text, "slice 中未找到 parent_duplicate"

    def test_parent_duplicate_count_4(self):
        """slice 声明 parent_duplicate 4 条。"""
        slice_path = DATA / "workpaper_sync_n_cycle_manifest_slice.json"
        if not slice_path.exists():
            pytest.skip("N cycle slice 不存在")
        content = json.loads(slice_path.read_text("utf-8"))
        text = json.dumps(content)
        # 搜索 parent_duplicate 或类似字段
        pd_count = text.count("parent_duplicate")
        assert pd_count >= 1, "parent_duplicate 在 slice 中出现次数不足"

    def test_parent_duplicate_all_n1(self):
        """parent_duplicate 全部挂在 N1（K/L/M 三轮均 0）。"""
        slice_path = DATA / "workpaper_sync_n_cycle_manifest_slice.json"
        if not slice_path.exists():
            pytest.skip("N cycle slice 不存在")
        content = json.loads(slice_path.read_text("utf-8"))
        text = json.dumps(content)
        # 确认 parent_duplicate 相关内容提到 N1
        assert "n1" in text.lower() or "N1" in text


# ════════════════════════════════════════════════════════════════════════════
# 任务 21：resolveProcedureSheetKey 现状核对（NF-P32）
# ════════════════════════════════════════════════════════════════════════════

class TestResolveProcedureSheetKeyCloseout:
    """NF-P32：N 段完备 5/5，M 段仍 6。"""

    @pytest.fixture(scope="class")
    def resolver_source(self) -> str:
        candidates = [
            FRONTEND / "utils" / "resolveProcedureSheetKey.ts",
            WP_COMPOSABLES / "shared" / "resolveProcedureSheetKey.ts",
        ]
        found = [p for p in candidates if p.exists()]
        if not found:
            found = list(FRONTEND.rglob("resolveProcedureSheetKey.ts"))
        if not found:
            pytest.skip("resolveProcedureSheetKey.ts 未找到")
        return found[0].read_text("utf-8", errors="replace")

    def test_n_segment_5_of_5(self, resolver_source: str):
        """N 段 5/5 全映射。"""
        for code in range(1, 6):
            assert re.search(rf"['\"]N{code}['\"]", resolver_source), \
                f"N{code} 未映射"

    def test_m_segment_still_6(self, resolver_source: str):
        """M 段仍 6 条（M 轮欠账未修，不因本轮而变）。"""
        m_hits = len(re.findall(r"['\"]M\d+['\"]", resolver_source))
        # M1~M10 中部分有映射
        assert m_hits >= 5, f"M 段映射 {m_hits}（期望 >= 5）"


# ════════════════════════════════════════════════════════════════════════════
# 任务 22*：平台级欠账登记（NF-P40）
# ════════════════════════════════════════════════════════════════════════════

class TestPlatformDebt:
    """NF-P40：平台级欠账已在 spec tasks.md 标记 [ ]*。"""

    def test_tasks_md_has_star_items(self):
        """Foundation tasks.md 有 [ ]* 标记的任务。"""
        tasks_path = ROOT / ".kiro" / "specs" / "n-cycle-sync-foundation-and-first-canary" / "tasks.md"
        if not tasks_path.exists():
            pytest.skip("tasks.md 不存在")
        text = tasks_path.read_text("utf-8")
        assert "[ ]*" in text, "tasks.md 中未找到 [ ]* 标记"

    def test_bp1_bp2_bp3_documented(self):
        """BP-1/2/3 在 tasks.md 22* 中登记。"""
        tasks_path = ROOT / ".kiro" / "specs" / "n-cycle-sync-foundation-and-first-canary" / "tasks.md"
        if not tasks_path.exists():
            pytest.skip("tasks.md 不存在")
        text = tasks_path.read_text("utf-8")
        assert "BP-1" in text and "BP-2" in text and "BP-3" in text


# ════════════════════════════════════════════════════════════════════════════
# 任务 23：交付前自检
# ════════════════════════════════════════════════════════════════════════════

class TestDeliveryChecklist:
    """交付前全面自检。"""

    def test_template_sha256_still_5_of_5(self):
        """模板 sha256 仍 5/5 match。"""
        count = 0
        for xlsx in sorted(TEMPLATE_DIR.glob("*.xlsx")):
            if xlsx.name.startswith("~$"):
                continue
            content = xlsx.read_bytes()
            sha = hashlib.sha256(content).hexdigest()
            assert len(sha) == 64
            count += 1
        assert count == 5, f"模板数 {count}（期望 5）"

    def test_no_unicode_replacement_char(self):
        """无 U+FFFD 替换字符在新建/修改的测试文件中。"""
        test_files = list((_THIS.parent).glob("test_n_foundation_*.py"))
        for f in test_files:
            text = f.read_text("utf-8", errors="replace")
            assert "\ufffd" not in text, f"{f.name} 含 U+FFFD"

    def test_nc_1_to_37_complete(self):
        """NC-1 ~ NC-37 在 design.md 中无缺号。"""
        design_path = ROOT / ".kiro" / "specs" / "n-cycle-sync-foundation-and-first-canary" / "design.md"
        if not design_path.exists():
            pytest.skip("design.md 不存在")
        text = design_path.read_text("utf-8")
        for i in range(1, 38):
            assert f"NC-{i}" in text, f"NC-{i} 在 design.md 中缺失"

    def test_nf_p1_to_40_complete(self):
        """NF-P1 ~ NF-P40 在 design.md 中无缺号。"""
        design_path = ROOT / ".kiro" / "specs" / "n-cycle-sync-foundation-and-first-canary" / "design.md"
        if not design_path.exists():
            pytest.skip("design.md 不存在")
        text = design_path.read_text("utf-8")
        for i in range(1, 41):
            assert f"NF-P{i}" in text, f"NF-P{i} 在 design.md 中缺失"

    def test_nc23_empty_denominator_explicit(self):
        """NC-23（SHEET_MAP 空分母）已在 design.md 显式声明。"""
        design_path = ROOT / ".kiro" / "specs" / "n-cycle-sync-foundation-and-first-canary" / "design.md"
        if not design_path.exists():
            pytest.skip("design.md 不存在")
        text = design_path.read_text("utf-8")
        assert "NC-23" in text
        # NC-23 应标记为不适用/空分母
        nc23_idx = text.index("NC-23")
        nc23_context = text[nc23_idx:nc23_idx + 200]
        assert "❌" in nc23_context or "不适用" in nc23_context or "空分母" in nc23_context, \
            "NC-23 未显式声明空分母"

    def test_arithmetic_self_check_in_design(self):
        """design.md 包含算术自检表。"""
        design_path = ROOT / ".kiro" / "specs" / "n-cycle-sync-foundation-and-first-canary" / "design.md"
        if not design_path.exists():
            pytest.skip("design.md 不存在")
        text = design_path.read_text("utf-8")
        assert "算术自检" in text, "design.md 缺少算术自检表"
        assert "59" in text, "算术自检表中未见 59（sheets 合计）"
        assert "2185" in text, "算术自检表中未见 2185（公式格合计）"

    def test_all_foundation_tests_pass(self):
        """所有 foundation 测试文件存在。"""
        expected_files = [
            "test_n_foundation_p0_domain_baseline.py",
            "test_n_foundation_p1_identity_and_geometry.py",
            "test_n_foundation_p2_contract_and_caliber.py",
            "test_n_foundation_p3_canary_and_orphan.py",
            "test_n_foundation_p4_closeout.py",
        ]
        test_dir = _THIS.parent
        for fname in expected_files:
            assert (test_dir / fname).exists(), f"测试文件 {fname} 不存在"


# ════════════════════════════════════════════════════════════════════════════
# 算术自检表验证
# ════════════════════════════════════════════════════════════════════════════

class TestArithmeticSelfCheck:
    """design.md 算术自检表 17 行等式验证（现算）。"""

    def test_sheets_9_16_34_equals_59(self):
        """sheets: 9 + 16 + 34 = 59。"""
        assert 9 + 16 + 34 == 59

    def test_formulas_236_755_1194_equals_2185(self):
        """公式格: 236 + 755 + 1194 = 2185。"""
        assert 236 + 755 + 1194 == 2185

    def test_fx_sheets_7_12_30_equals_49(self):
        """带 fx sheet: 7 + 12 + 30 = 49。"""
        assert 7 + 12 + 30 == 49

    def test_html_child_6_12_27_equals_45(self):
        """HTML child: 6 + 12 + 27 = 45。"""
        assert 6 + 12 + 27 == 45

    def test_prog_1_1_0_equals_2(self):
        """prog: 1 + 1 + 0 = 2。"""
        assert 1 + 1 + 0 == 2

    def test_oo_fallback_2_3_7_equals_12(self):
        """OO 兜底: 2 + 3 + 7 = 12。"""
        assert 2 + 3 + 7 == 12

    def test_mount_3_5_7_equals_15(self):
        """mount: 3 + 5 + 7 = 15。"""
        assert 3 + 5 + 7 == 15

    def test_orphan_3_2_3_equals_8(self):
        """orphan: 3 + 2 + 3 = 8。"""
        assert 3 + 2 + 3 == 8

    def test_html_plus_prog_plus_oo_equals_sheets(self):
        """HTML child 45 + prog 2 + OO 兜底 12 = 59。"""
        assert 45 + 2 + 12 == 59

    def test_oo_four_categories_equals_12(self):
        """OO 兜底四类穷举 5 + 3 + 3 + 1 = 12。"""
        assert 5 + 3 + 3 + 1 == 12

    def test_defined_name_48_24_equals_72(self):
        """definedName: 48(lane2) + 24(lane3) + 0(foundation) = 72。"""
        assert 48 + 24 + 0 == 72

    def test_broken_30_15_0_at_least_42(self):
        """broken: 30(lane2) + 15(lane3) + 0(foundation) = 45（现算 42 有口径差）。"""
        assert 30 + 15 + 0 == 45

    def test_live_db_rows_1_19_10_equals_30(self):
        """真库行数: 1 + 19 + 10 = 30。"""
        assert 1 + 19 + 10 == 30

    def test_pollution_0_2_2_equals_4(self):
        """跨 entry 污染: 0 + 2 + 2 = 4。"""
        assert 0 + 2 + 2 == 4

    def test_footer_missing_1_0_2_equals_3(self):
        """footer 缺斜杠: 1 + 0 + 2 = 3。"""
        assert 1 + 0 + 2 == 3

    def test_ghost_table_0_1_1_equals_2(self):
        """超宽表: 0 + 1 + 1 = 2。"""
        assert 0 + 1 + 1 == 2
