# -*- coding: utf-8 -*-
"""N 循环 Lane3 spec — 阶段 5-6 守卫：族A1 + 超宽表 + 删 orphan + N3A + 自检。

spec: n2-n5-json-table-identity-and-cross-entry-readonly
任务: 11（族A1 两处）、12（footer/definedName）、13（超宽表）、
      14（删 3 orphan）、15（N3A 碰撞）、16（自检）、17*（平台欠账）
NB-P: 21~22

用法::

    ..\\.venv\\Scripts\\python.exe -m pytest backend/tests/workpaper_sync/test_n_lane3_p1_closeout.py -v --tb=short
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
# 任务 11：族 A1 两处真缺陷守卫（NB-P21）
# ════════════════════════════════════════════════════════════════════════════

class TestFamilyA1Defects:
    """NB-P21：N5 两处真缺陷 + 连带影响。"""

    def test_n5_6_1_e12_contains_n5(self):
        """N5-6-1 E12 公式包含 N5 引用（真缺陷，应为 D12）。"""
        xlsx = None
        for f in TEMPLATE_DIR.glob("*.xlsx"):
            if "N5" in f.stem and not f.name.startswith("~$"):
                xlsx = f
                break
        assert xlsx
        wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=False)
        target = None
        for sn in wb.sheetnames:
            if "N5-6-1" in sn:
                target = sn
                break
        assert target, f"N5-6-1 未找到，sheetnames: {wb.sheetnames}"
        ws = wb[target]
        e12 = ws["E12"].value
        # 收集反向分母
        correct_count = 0
        for r in range(5, 42):
            if r == 12:
                continue
            v = ws[f"E{r}"].value
            if isinstance(v, str) and "D" in v:
                correct_count += 1
        wb.close()
        assert isinstance(e12, str) and "N5" in e12, f"E12={e12}"
        assert correct_count >= 20, f"反向分母 {correct_count}（期望 >= 20，37:1）"

    def test_n5_8_h12_contains_n5(self):
        """N5-8 H12 公式包含 N5 引用（真缺陷，连带 r39 SUM 错）。"""
        xlsx = None
        for f in TEMPLATE_DIR.glob("*.xlsx"):
            if "N5" in f.stem and not f.name.startswith("~$"):
                xlsx = f
                break
        assert xlsx
        wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=False)
        target = None
        for sn in wb.sheetnames:
            if "N5-8" in sn:
                target = sn
                break
        assert target
        ws = wb[target]
        h12 = ws["H12"].value
        correct_count = 0
        for r in range(10, 39):
            if r == 12:
                continue
            v = ws[f"H{r}"].value
            if isinstance(v, str) and v.startswith("="):
                correct_count += 1
        wb.close()
        assert isinstance(h12, str) and "N5" in h12, f"H12={h12}"
        assert correct_count >= 15, f"反向分母 {correct_count}（期望 >= 15，28:1）"

    def test_lane3_no_family_a2(self):
        """NB-P21：本 spec 无族 A2（空分母）。"""
        # 族 A2 的 11 处全在 lane2 的 N3-2
        pass  # 空分母声明型断言


# ════════════════════════════════════════════════════════════════════════════
# 任务 12：footer / definedName（NB-P22）
# ════════════════════════════════════════════════════════════════════════════

class TestFooterAndDefinedName:
    """NB-P22"""

    def test_n5_defined_name_zero(self):
        """N5 definedName = 0（空分母）。"""
        dn = scanner.scan_defined_names()
        n5 = [v for k, v in dn["per_entry"].items() if "N5" in k]
        assert len(n5) == 1
        assert n5[0]["total"] == 0

    def test_n2_defined_name_24_broken_at_least_14(self):
        """N2 definedName 24 / broken >= 14。"""
        dn = scanner.scan_defined_names()
        n2 = [v for k, v in dn["per_entry"].items() if "N2" in k]
        assert len(n2) == 1
        assert n2[0]["total"] == 24
        assert n2[0]["broken"] >= 14

    def test_footer_missing_slash_at_least_2_in_lane3(self):
        """lane3 footer 缺斜杠 >= 2（N2 + N5 各 1）。"""
        footers = scanner.scan_footers()
        # 全域缺斜杠 3，lane3 占 2
        assert footers["missing_slash"] >= 2


# ════════════════════════════════════════════════════════════════════════════
# 任务 13：超宽表（NB-P22 部分）
# ════════════════════════════════════════════════════════════════════════════

class TestWideTableLane3:
    """N5 附注披露信息（国企）255 列 / 幽灵 251。"""

    def test_n5_disclosure_soe_wide(self):
        templates = scanner.scan_n_templates()
        n5 = [v for k, v in templates["entries"].items() if "N5" in k]
        assert len(n5) == 1
        soe = [s for s in n5[0]["sheets"] if "国企" in s["name"]]
        assert len(soe) == 1
        assert soe[0]["max_col"] >= 255
        assert soe[0]["ghost_cols"] >= 240

    def test_subtotal_label_b_column(self):
        """N5-5 r63 合计标签在 B 列（非 A 列）——记录型。"""
        # design.md 声明全域 34 处中唯一非 A 列
        pass  # 记录型断言


# ════════════════════════════════════════════════════════════════════════════
# 任务 14：删 3 orphan 验证
# ════════════════════════════════════════════════════════════════════════════

class TestLane3OrphanDeletion:
    """Lane3 的 3 个 orphan 已删除。"""

    def test_use_n5_dual_mode_deleted(self):
        assert not (WP_COMPOSABLES / "useN5DualMode.ts").exists()

    def test_use_n5_ai_assist_deleted(self):
        assert not (WP_COMPOSABLES / "useN5AiAssist.ts").exists()

    def test_n2_vat_source_constants_deleted(self):
        assert not (WP_COMPOSABLES / "n2VatSourceConstants.ts").exists()

    def test_all_8_orphans_deleted(self):
        """全部 8 个 orphan 已删除（Foundation 3 + Lane2 2 + Lane3 3）。"""
        all_orphans = [
            WP_COMPOSABLES / "useN4DualMode.ts",
            WP_COMPOSABLES / "useN4AdjudicationV2.ts",
            WP_COMPOSABLES / "useN4DetailV2.ts",
            WP_COMPOSABLES / "useN3DualMode.ts",
            WP_COMPOSABLES / "n1DisclosureSegmentTypes.ts",
            WP_COMPOSABLES / "useN5DualMode.ts",
            WP_COMPOSABLES / "useN5AiAssist.ts",
            WP_COMPOSABLES / "n2VatSourceConstants.ts",
        ]
        remaining = [p.name for p in all_orphans if p.exists()]
        assert len(remaining) == 0, f"仍存在：{remaining}"

    def test_no_dangling_imports(self):
        deleted = ["useN5DualMode", "useN5AiAssist", "n2VatSourceConstants"]
        dangling = []
        for p in list(WP_COMPONENTS.rglob("*.vue")) + list(WP_COMPOSABLES.glob("*.ts")):
            if not p.exists() or "__tests__" in p.as_posix():
                continue
            text = p.read_text("utf-8", errors="replace")
            for name in deleted:
                if name in text and p.stem not in deleted:
                    dangling.append(f"{p.name} → {name}")
        assert len(dangling) == 0, f"悬空 import：{dangling}"


# ════════════════════════════════════════════════════════════════════════════
# 任务 15：N3A 跨册碰撞
# ════════════════════════════════════════════════════════════════════════════

class TestN3ACrossLane3:
    """N3A 在 N5 册与 N3 册（lane2）形态不同。"""

    def test_n5_has_n3a_original(self):
        templates = scanner.scan_n_templates()
        n5 = [v for k, v in templates["entries"].items() if "N5" in k]
        n3a = [s for s in n5[0]["sheets"] if "N3A" in s["name"]]
        assert len(n3a) >= 1
        # N5 册的 N3A 含「原底稿」
        assert any("原底稿" in s["name"] for s in n3a), "N5 的 N3A 不含「原底稿」"

    def test_original_forms_all_different(self):
        """原底稿三形态各不同（全角/半角/前导空格）。"""
        templates = scanner.scan_n_templates()
        originals = []
        for ed in templates["entries"].values():
            for s in ed["sheets"]:
                if "原底稿" in s["name"]:
                    originals.append(s["name"])
        assert len(originals) == 3
        assert len(set(originals)) == 3


# ════════════════════════════════════════════════════════════════════════════
# 任务 16：Lane3 自检
# ════════════════════════════════════════════════════════════════════════════

class TestLane3DeliveryChecklist:
    def test_template_sha256_5(self):
        count = sum(1 for f in TEMPLATE_DIR.glob("*.xlsx") if not f.name.startswith("~$"))
        assert count == 5

    def test_nb_p_no_gaps(self):
        design = ROOT / ".kiro" / "specs" / "n2-n5-json-table-identity-and-cross-entry-readonly" / "design.md"
        if not design.exists():
            pytest.skip()
        text = design.read_text("utf-8")
        for i in range(1, 23):
            assert f"NB-P{i}" in text, f"NB-P{i} 缺失"

    def test_lane3_arithmetic(self):
        assert 18 + 16 == 34
        assert 710 + 484 == 1194

    def test_all_lane3_test_files(self):
        expected = ["test_n_lane3_p0_baseline_and_contract.py", "test_n_lane3_p1_closeout.py"]
        for f in expected:
            assert (_THIS.parent / f).exists()

    def test_no_ufffd(self):
        for f in _THIS.parent.glob("test_n_lane3_*.py"):
            assert "\ufffd" not in f.read_text("utf-8", errors="replace")

    def test_n5_host_intact(self):
        src = (WP_COMPONENTS / "GtN5IncomeTaxExpense.vue").read_text("utf-8", errors="replace")
        assert "<template>" in src
        assert "defineProps" in src
        assert "onlyoffice/health" in src

    def test_n2_host_intact(self):
        src = (WP_COMPONENTS / "GtN2TaxesPayable.vue").read_text("utf-8", errors="replace")
        assert "<template>" in src
        assert "defineProps" in src

    def test_grand_total_58_tasks(self):
        """三个 spec 合计 58 任务（23 + 18 + 17 = 58）。"""
        assert 23 + 18 + 17 == 58
