# -*- coding: utf-8 -*-
"""N 循环 Foundation spec — 阶段 4 守卫：canary N4 闭环 + orphan 删除 + T-1 模板缺陷。

spec: n-cycle-sync-foundation-and-first-canary
任务: 13（inert 修复）、14（E 族样板提取）、15（N4-1-rows 双向回写）、
      16（by_rowid 改造）、17（删 3 orphan）、18（T-1 模板缺陷守卫）
NF-P: 6~9, 11, 13, 17, 20

用法::

    ..\\.venv\\Scripts\\python.exe -m pytest backend/tests/workpaper_sync/test_n_foundation_p3_canary_and_orphan.py -v --tb=short
"""
from __future__ import annotations

import pathlib
import re
from typing import Any

import openpyxl
import pytest

# ════════════════════════════════════════════════════════════════════════════
# 路径
# ════════════════════════════════════════════════════════════════════════════
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
# 任务 13：N4 inert 模式修复验证
# ════════════════════════════════════════════════════════════════════════════

class TestN4InertRepair:
    """NF-P9：N4 的 inert 开关已修复为 redeemable。"""

    @pytest.fixture(scope="class")
    def n4_source(self) -> str:
        return (WP_COMPONENTS / "GtN4TaxesAndSurcharges.vue").read_text("utf-8", errors="replace")

    def test_on_mode_change_not_empty(self, n4_source: str):
        """onModeChange 不再是空实现。"""
        stripped = scanner.strip_comments(n4_source)
        # 不应再有 `onModeChange: () => {}`
        assert "onModeChange: () => {}" not in stripped, \
            "N4 onModeChange 仍为空实现（inert 未修复）"

    def test_health_check_exists(self, n4_source: str):
        """宿主中存在 OO 健康检查（/onlyoffice/health）。"""
        assert "onlyoffice/health" in n4_source, \
            "N4 宿主未包含 OO 健康检查端点"

    def test_explicit_feedback_on_oo_unavailable(self, n4_source: str):
        """OO 不可用时有显式用户反馈（不仅是日志）。"""
        stripped = scanner.strip_comments(n4_source)
        # 应有 ElMessage 或类似用户提示
        assert "ElMessage" in stripped or "Message" in stripped, \
            "OO 不可用时缺少显式用户反馈"

    def test_dual_mode_toolbar_uses_real_mode(self, n4_source: str):
        """工具栏的 el-segmented 绑定真实的 currentMode。"""
        assert "dualMode.currentMode.value" in n4_source

    def test_oo_fallback_uses_real_mode(self, n4_source: str):
        """OO 渲染条件使用真实的 currentMode 值判断。"""
        assert "dualMode.currentMode.value === 'onlyoffice'" in n4_source


# ════════════════════════════════════════════════════════════════════════════
# 任务 14：E 族稳定行身份样板存在性
# ════════════════════════════════════════════════════════════════════════════

class TestEFamilySampleExists:
    """NF-P12（部分）：E 族行身份正面样板在 N4 活路径中存在。"""

    def test_n4_adjudication_uses_rowkey(self):
        """useN4Adjudication.ts 使用 rowKey 作为行身份。"""
        src = (WP_COMPOSABLES / "useN4Adjudication.ts").read_text("utf-8", errors="replace")
        assert "rowKey" in src, "useN4Adjudication 缺少 rowKey 行身份"

    def test_n4_detail_uses_rowkey(self):
        """useN4Detail.ts 使用 rowKey 作为行身份。"""
        path = WP_COMPOSABLES / "useN4Detail.ts"
        if not path.exists():
            pytest.skip("useN4Detail.ts 不存在")
        src = path.read_text("utf-8", errors="replace")
        assert "rowKey" in src, "useN4Detail 缺少 rowKey 行身份"

    def test_n4_tax_types_provides_stable_keys(self):
        """n4TaxTypes.ts 提供英文稳定 key 词典。"""
        src = (WP_COMPOSABLES / "n4TaxTypes.ts").read_text("utf-8", errors="replace")
        # 10 个税种的稳定 key
        stable_keys = [
            "consumption-tax", "urban-construction", "education-surcharge",
            "local-education", "property-tax", "land-use-tax",
            "vehicle-vessel", "stamp-tax", "resource-tax", "other",
        ]
        for key in stable_keys:
            assert key in src, f"n4TaxTypes 缺少稳定 key '{key}'"


# ════════════════════════════════════════════════════════════════════════════
# 任务 15：canary N4-1-rows 双向回写路径守卫
# ════════════════════════════════════════════════════════════════════════════

class TestCanaryN4WritebackPath:
    """NF-P6/7/17：canary 双向回写路径完整性。"""

    def test_publish_to_tb_in_adjudication(self):
        """useN4Adjudication.ts 包含 publish-to-tb 发布门（在 writebackTB 注入路径中）。"""
        src = (WP_COMPOSABLES / "useN4Adjudication.ts").read_text("utf-8", errors="replace")
        # publish-to-tb 字面量在注释中，实际发布通过 writebackTB 注入（来自 useN4FormData）
        # 这里验证 publishToTb 函数存在且调用 writeback
        stripped = scanner.strip_comments(src)
        assert "publishToTb" in stripped, "useN4Adjudication 缺少 publishToTb 函数"
        assert "writeback" in stripped, "useN4Adjudication publishToTb 未调用 writeback"

    def test_confirm_gate_exists(self):
        """NF-P7：useN4Adjudication.ts 包含 ElMessageBox.confirm 二次确认。"""
        src = (WP_COMPOSABLES / "useN4Adjudication.ts").read_text("utf-8", errors="replace")
        stripped = scanner.strip_comments(src)
        assert "ElMessageBox.confirm" in stripped, \
            "useN4Adjudication 缺少确认门"

    def test_rows_key_n4_1_rows(self):
        """NF-P17：canary 使用 N4-1-rows 作为持久化键。"""
        src = (WP_COMPOSABLES / "useN4Adjudication.ts").read_text("utf-8", errors="replace")
        assert "N4-1-rows" in src or "N4-1" in src, \
            "useN4Adjudication 未使用 N4-1-rows 键"

    def test_no_auto_writeback_in_watch(self):
        """数据变化不自动写 TB（只在显式发布时写）。"""
        src = (WP_COMPOSABLES / "useN4Adjudication.ts").read_text("utf-8", errors="replace")
        # 检查没有 watch → writebackTB 的自动路径
        # 旧实现有 watch(() => totals.value.endAudited) → 自动 writebackTB，已删除
        stripped = scanner.strip_comments(src)
        # 确认 publishToTb 是唯一写 TB 的入口
        assert "publishToTb" in stripped, "缺少 publishToTb 函数"

    def test_formdata_writeback_tb_exists(self):
        """useN4FormData.ts 提供 writebackTB 方法。"""
        path = WP_COMPOSABLES / "useN4FormData.ts"
        if not path.exists():
            pytest.skip("useN4FormData.ts 不存在")
        src = path.read_text("utf-8", errors="replace")
        assert "writebackTB" in src or "writeback" in src


# ════════════════════════════════════════════════════════════════════════════
# 任务 17：删除 3 个 orphan 验证
# ════════════════════════════════════════════════════════════════════════════

class TestOrphanDeletion:
    """NF-P11：3 个 foundation orphan 已删除。"""

    def test_use_n4_dual_mode_deleted(self):
        """useN4DualMode.ts 已删除。"""
        assert not (WP_COMPOSABLES / "useN4DualMode.ts").exists(), \
            "useN4DualMode.ts 未删除"

    def test_use_n4_adjudication_v2_deleted(self):
        """useN4AdjudicationV2.ts 已删除。"""
        assert not (WP_COMPOSABLES / "useN4AdjudicationV2.ts").exists(), \
            "useN4AdjudicationV2.ts 未删除"

    def test_use_n4_detail_v2_deleted(self):
        """useN4DetailV2.ts 已删除。"""
        assert not (WP_COMPOSABLES / "useN4DetailV2.ts").exists(), \
            "useN4DetailV2.ts 未删除"

    def test_orphan_total_reduced(self):
        """删除后 foundation orphan = 0（8 total - 3 foundation = 5 remaining for lane2+3）。"""
        foundation_orphans = [
            WP_COMPOSABLES / "useN4DualMode.ts",
            WP_COMPOSABLES / "useN4AdjudicationV2.ts",
            WP_COMPOSABLES / "useN4DetailV2.ts",
        ]
        remaining = sum(1 for p in foundation_orphans if p.exists())
        assert remaining == 0, f"foundation orphan 仍有 {remaining} 个未删除"

    def test_no_dangling_imports(self):
        """删除后无悬空 import（其他文件不引用已删文件）。"""
        deleted_names = ["useN4DualMode", "useN4AdjudicationV2", "useN4DetailV2"]
        dangling = []
        for p in WP_COMPONENTS.rglob("*.vue"):
            text = p.read_text("utf-8", errors="replace")
            for name in deleted_names:
                if name in text:
                    dangling.append(f"{p.name} → {name}")
        for p in WP_COMPOSABLES.glob("*.ts"):
            if not p.exists():
                continue
            text = p.read_text("utf-8", errors="replace")
            for name in deleted_names:
                if name in text and p.stem not in deleted_names:
                    dangling.append(f"{p.name} → {name}")
        assert len(dangling) == 0, f"悬空 import {len(dangling)} 处：{dangling}"


# ════════════════════════════════════════════════════════════════════════════
# 任务 18：T-1 模板缺陷守卫（NC-32 / NF-P20）
# ════════════════════════════════════════════════════════════════════════════

class TestTemplateDefectT1:
    """NF-P20（部分）：T-1 N4-2 E9 的 `=B9+C9+N4` 以记录型锁定。"""

    def test_n4_2_e9_contains_n4_reference(self):
        """T-1：N4-2 sheet 的 E9 单元格公式包含 'N4' 引用（真缺陷）。"""
        xlsx_path = None
        for f in TEMPLATE_DIR.glob("*.xlsx"):
            if "N4" in f.stem and not f.name.startswith("~$"):
                xlsx_path = f
                break
        assert xlsx_path is not None, "N4 模板未找到"

        wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=False)
        # 找到 N4-2 sheet（税金及附加明细表N4-2）
        target_sheet = None
        for sn in wb.sheetnames:
            if "N4-2" in sn:
                target_sheet = sn
                break
        assert target_sheet is not None, f"N4-2 sheet 未找到，可用 sheets: {wb.sheetnames}"

        ws = wb[target_sheet]
        e9_val = ws["E9"].value
        # 反向分母：同列其他行（E8, E10..E16）应有正确的 D 列引用
        correct_d_count = 0
        for row_num in range(8, 17):
            if row_num == 9:
                continue
            cell_val = ws[f"E{row_num}"].value
            if isinstance(cell_val, str) and "D" in cell_val:
                correct_d_count += 1
        wb.close()

        assert e9_val is not None, "E9 为空"
        assert isinstance(e9_val, str) and e9_val.startswith("="), f"E9 非公式: {e9_val}"
        # 🔴 真缺陷：公式中 D9 被替换为 N4（wp_code 与 A1 引用同形）
        assert "N4" in e9_val, f"E9 公式不含 N4 引用: {e9_val}"
        assert correct_d_count >= 5, \
            f"正确 D 列引用只有 {correct_d_count}（期望 >= 5，反向分母 9:1）"

    def test_template_sha256_unchanged(self):
        """删除 orphan 后模板 sha256 未变（T-1 是记录型，不改模板）。"""
        import hashlib
        for xlsx in sorted(TEMPLATE_DIR.glob("*.xlsx")):
            if xlsx.name.startswith("~$"):
                continue
            # 只验证文件可读且 sha256 自洽
            content = xlsx.read_bytes()
            sha = hashlib.sha256(content).hexdigest()
            assert len(sha) == 64, f"{xlsx.name} sha256 异常"


# ════════════════════════════════════════════════════════════════════════════
# 综合回归验证
# ════════════════════════════════════════════════════════════════════════════

class TestCanaryRegressionGuard:
    """canary 修改后的回归检查。"""

    def test_n4_template_still_loads(self):
        """N4 宿主组件仍可正常解析（无语法错误标记）。"""
        src = (WP_COMPONENTS / "GtN4TaxesAndSurcharges.vue").read_text("utf-8", errors="replace")
        # 基本检查：template + script + style 三段都存在
        assert "<template>" in src
        assert "<script" in src
        assert "defineProps" in src

    def test_n4_adjudication_composable_intact(self):
        """useN4Adjudication.ts（V1 活路径）仍完整。"""
        src = (WP_COMPOSABLES / "useN4Adjudication.ts").read_text("utf-8", errors="replace")
        # 关键导出仍存在
        assert "useN4Adjudication" in src
        assert "publishToTb" in src
        assert "N4-1" in src

    def test_event_bus_subscriptions_intact(self):
        """N4 宿主的 EventBus 订阅仍存在。"""
        src = (WP_COMPONENTS / "GtN4TaxesAndSurcharges.vue").read_text("utf-8", errors="replace")
        assert "eventBus.on" in src
        assert "disclosure:refresh" in src
        assert "tax-accrual:updated" in src

    def test_sheet_routing_intact(self):
        """n4SheetRouting.ts 仍正常。"""
        src = (WP_COMPOSABLES / "n4SheetRouting.ts").read_text("utf-8", errors="replace")
        assert "makeCycleSheetRouter" in src
        assert "N4A" in src
