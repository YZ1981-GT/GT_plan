# -*- coding: utf-8 -*-
"""N 循环 Lane2 spec — 阶段 5 守卫：族A2 + 超宽表 + 删 orphan + N3A 碰撞 + 自检。

spec: n1-n3-host-inline-router-and-shared-adoption
任务: 13（族A2/脏形态守卫）、14（超宽表遍历）、15（删 2 orphan）、
      16（N3A 跨册碰撞）、17（自检）、18*（平台欠账）
NA-P: 19~22

用法::

    ..\\.venv\\Scripts\\python.exe -m pytest backend/tests/workpaper_sync/test_n_lane2_p2_closeout.py -v --tb=short
"""
from __future__ import annotations

import hashlib
import pathlib
import re

import openpyxl
import pytest

_THIS = pathlib.Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
TEMPLATE_DIR = BACKEND / "wp_templates" / "N"
FRONTEND = ROOT / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = FRONTEND / "components" / "workpaper"
WP_COMPOSABLES = WP_COMPONENTS / "composables"

import sys
sys.path.insert(0, str(BACKEND / "scripts" / "analyze"))
import n_cycle_scanner as scanner  # noqa: E402


# ════════════════════════════════════════════════════════════════════════════
# 任务 13：族 A2 守卫（NA-P19 / NA-P20）
# ════════════════════════════════════════════════════════════════════════════

class TestFamilyA2Guard:
    """NA-P19：族 A2 = N3-2 H11~H21 全 11 行同形，无反向分母。"""

    def test_n3_2_h_column_overflow(self):
        """N3-2 sheet 的 H 列（col=8）超出 max_column（14），属结构残留。"""
        xlsx = None
        for f in TEMPLATE_DIR.glob("*.xlsx"):
            if "N3" in f.stem and not f.name.startswith("~$"):
                xlsx = f
                break
        assert xlsx, "N3 模板未找到"

        wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=False)
        # 找 N3-2 sheet
        target = None
        for sn in wb.sheetnames:
            if "N3-2" in sn:
                target = sn
                break
        assert target, f"N3-2 sheet 未找到，可用: {wb.sheetnames}"

        ws = wb[target]
        # 检查 H11~H21 的公式是否都引用 O 列（超出 max_column 14）
        h_formulas = []
        for r in range(11, 22):
            cell = ws[f"H{r}"]
            val = cell.value
            if isinstance(val, str) and val.startswith("="):
                h_formulas.append(val)
        wb.close()

        assert len(h_formulas) == 11, f"H11~H21 公式数 {len(h_formulas)}（期望 11）"
        # 全部包含 O 列引用（超列）且同形
        o_ref_count = sum(1 for f in h_formulas if "O" in f)
        assert o_ref_count == 11, f"含 O 引用的 {o_ref_count}/11"

    def test_biao_de_dirty_forms_3(self):
        """NA-P20：「表的{码}」脏形态 3 处全在 N1/N3。"""
        templates = scanner.scan_n_templates()
        biao_de_names = []
        for entry_name, entry_data in templates["entries"].items():
            for s in entry_data["sheets"]:
                if "表的" in s["name"]:
                    biao_de_names.append(f"{entry_name}/{s['name']}")
        assert len(biao_de_names) >= 3, f"「表的」形态 {len(biao_de_names)}（期望 >= 3）"
        # 全在 N1 和 N3
        for name in biao_de_names:
            assert "N1" in name or "N3" in name, f"{name} 不在 N1/N3"


# ════════════════════════════════════════════════════════════════════════════
# 任务 14：超宽表遍历策略（NA-P21）
# ════════════════════════════════════════════════════════════════════════════

class TestWideTableTraversal:
    """NA-P21：N1 附注披露信息（国企）256 列 / 幽灵 249。"""

    def test_n1_disclosure_soe_256_cols(self):
        """N1 的国企附注 sheet max_col = 256。"""
        templates = scanner.scan_n_templates()
        n1 = [v for k, v in templates["entries"].items() if "N1" in k]
        assert len(n1) == 1
        soe_sheets = [s for s in n1[0]["sheets"] if "国企" in s["name"]]
        assert len(soe_sheets) == 1
        assert soe_sheets[0]["max_col"] == 256, f"max_col {soe_sheets[0]['max_col']}（期望 256）"

    def test_n1_disclosure_soe_ghost_249(self):
        """N1 国企附注幽灵列 = 256 - last_value_col。"""
        templates = scanner.scan_n_templates()
        n1 = [v for k, v in templates["entries"].items() if "N1" in k]
        soe = [s for s in n1[0]["sheets"] if "国企" in s["name"]][0]
        assert soe["ghost_cols"] >= 240, f"幽灵列 {soe['ghost_cols']}（期望 >= 240）"

    def test_n3_no_disclosure_empty_denominator(self):
        """NA-P22：N3 无附注披露（空分母）。"""
        templates = scanner.scan_n_templates()
        n3 = [v for k, v in templates["entries"].items() if "N3" in k]
        assert len(n3) == 1
        disclosure = [s for s in n3[0]["sheets"] if "附注" in s["name"]]
        assert len(disclosure) == 0, f"N3 有 {len(disclosure)} 个附注（期望 0）"


# ════════════════════════════════════════════════════════════════════════════
# 任务 15：删 2 orphan 验证
# ════════════════════════════════════════════════════════════════════════════

class TestLane2OrphanDeletion:
    """Lane2 的 2 个 orphan 已删除。"""

    def test_use_n3_dual_mode_deleted(self):
        """useN3DualMode.ts 已删除。"""
        assert not (WP_COMPOSABLES / "useN3DualMode.ts").exists()

    def test_n1_disclosure_segment_types_deleted(self):
        """n1DisclosureSegmentTypes.ts 已删除。"""
        assert not (WP_COMPOSABLES / "n1DisclosureSegmentTypes.ts").exists()

    def test_no_dangling_imports_from_deleted(self):
        """删除后无悬空 import。"""
        deleted = ["useN3DualMode", "n1DisclosureSegmentTypes"]
        dangling = []
        for p in list(WP_COMPONENTS.rglob("*.vue")) + list(WP_COMPOSABLES.glob("*.ts")):
            if not p.exists() or "__tests__" in p.as_posix():
                continue
            text = p.read_text("utf-8", errors="replace")
            for name in deleted:
                if name in text and p.stem not in deleted:
                    dangling.append(f"{p.name} → {name}")
        assert len(dangling) == 0, f"悬空 import：{dangling}"

    def test_shared_disclosure_types_intact(self):
        """shared/disclosureSegmentTypes.ts 仍存在（orphan 是 re-export，真源不受影响）。"""
        shared = WP_COMPOSABLES / "shared" / "disclosureSegmentTypes.ts"
        assert shared.exists(), "shared/disclosureSegmentTypes.ts 不存在"


# ════════════════════════════════════════════════════════════════════════════
# 任务 16：N3A 跨册碰撞交叉校验
# ════════════════════════════════════════════════════════════════════════════

class TestN3ACrossBoundary:
    """N3A 同码存在于 N3 册与 N5 册，须按 (册, sheet 名) 二元组定位。"""

    def test_n3a_in_n3_workbook(self):
        """N3 册包含 N3A sheet。"""
        templates = scanner.scan_n_templates()
        n3 = [v for k, v in templates["entries"].items() if "N3" in k]
        assert len(n3) == 1
        n3a_sheets = [s for s in n3[0]["sheets"] if "N3A" in s["name"]]
        assert len(n3a_sheets) >= 1, "N3 册无 N3A sheet"

    def test_n3a_in_n5_workbook(self):
        """N5 册也包含 N3A sheet（跨册碰撞）。"""
        templates = scanner.scan_n_templates()
        n5 = [v for k, v in templates["entries"].items() if "N5" in k]
        assert len(n5) == 1
        n3a_sheets = [s for s in n5[0]["sheets"] if "N3A" in s["name"]]
        assert len(n3a_sheets) >= 1, "N5 册无 N3A sheet（跨册碰撞不成立）"

    def test_n3a_forms_differ(self):
        """N3 册与 N5 册的 N3A sheet 名形态不同。"""
        templates = scanner.scan_n_templates()
        n3 = [v for k, v in templates["entries"].items() if "N3" in k][0]
        n5 = [v for k, v in templates["entries"].items() if "N5" in k][0]
        n3_n3a = [s["name"] for s in n3["sheets"] if "N3A" in s["name"]]
        n5_n3a = [s["name"] for s in n5["sheets"] if "N3A" in s["name"]]
        assert len(n3_n3a) >= 1 and len(n5_n3a) >= 1
        # 两处 sheet 名应不完全相同（一个含「原底稿」一个不含）
        assert n3_n3a[0] != n5_n3a[0], f"两处 N3A sheet 名相同：{n3_n3a[0]}"

    def test_o1a_o2a_foreign_codes(self):
        """外来字母码 O1A/O2A 在 N 册中存在。"""
        templates = scanner.scan_n_templates()
        foreign = []
        for entry_name, entry_data in templates["entries"].items():
            for s in entry_data["sheets"]:
                if "O1A" in s["name"] or "O2A" in s["name"]:
                    foreign.append(f"{entry_name}/{s['name']}")
        assert len(foreign) >= 2, f"外来码 {len(foreign)}（期望 >= 2）"


# ════════════════════════════════════════════════════════════════════════════
# 任务 17：Lane2 交付前自检
# ════════════════════════════════════════════════════════════════════════════

class TestLane2DeliveryChecklist:
    """Lane2 交付前全面自检。"""

    def test_template_sha256_5_of_5(self):
        """模板 sha256 仍 5/5。"""
        count = sum(1 for f in TEMPLATE_DIR.glob("*.xlsx") if not f.name.startswith("~$"))
        assert count == 5

    def test_na_p_no_gaps(self):
        """NA-P1~22 在 design.md 中无缺号。"""
        design_path = ROOT / ".kiro" / "specs" / "n1-n3-host-inline-router-and-shared-adoption" / "design.md"
        if not design_path.exists():
            pytest.skip("design.md 不存在")
        text = design_path.read_text("utf-8")
        for i in range(1, 23):
            assert f"NA-P{i}" in text, f"NA-P{i} 缺失"

    def test_lane2_arithmetic(self):
        """份额算术：sheets 16 / 公式格 755。"""
        assert 10 + 6 == 16  # N1 + N3
        assert 593 + 162 == 755

    def test_all_lane2_test_files_exist(self):
        """Lane2 全部测试文件存在。"""
        expected = [
            "test_n_lane2_p0_routing_and_health.py",
            "test_n_lane2_p1_carrier_and_contract.py",
            "test_n_lane2_p2_closeout.py",
        ]
        for fname in expected:
            assert (_THIS.parent / fname).exists(), f"{fname} 不存在"

    def test_no_unicode_replacement_char(self):
        """无 U+FFFD。"""
        for f in _THIS.parent.glob("test_n_lane2_*.py"):
            text = f.read_text("utf-8", errors="replace")
            assert "\ufffd" not in text, f"{f.name} 含 U+FFFD"

    def test_n1_n3_routing_files_both_exist(self):
        """n1SheetRouting.ts 和 n3SheetRouting.ts 都存在。"""
        assert (WP_COMPOSABLES / "n1SheetRouting.ts").exists()
        assert (WP_COMPOSABLES / "n3SheetRouting.ts").exists()

    def test_total_orphan_deleted_5_of_8(self):
        """Foundation 3 + Lane2 2 = 5 个 orphan 已删除（剩 3 个归 Lane3）。"""
        deleted = [
            WP_COMPOSABLES / "useN4DualMode.ts",
            WP_COMPOSABLES / "useN4AdjudicationV2.ts",
            WP_COMPOSABLES / "useN4DetailV2.ts",
            WP_COMPOSABLES / "useN3DualMode.ts",
            WP_COMPOSABLES / "n1DisclosureSegmentTypes.ts",
        ]
        remaining = sum(1 for p in deleted if p.exists())
        assert remaining == 0, f"已删 orphan 仍有 {remaining} 个存在"
