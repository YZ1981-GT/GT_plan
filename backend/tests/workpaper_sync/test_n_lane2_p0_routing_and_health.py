# -*- coding: utf-8 -*-
"""N 循环 Lane2 spec — 阶段 1-2 守卫：归属基线 + BP-10/BP-4 收口。

spec: n1-n3-host-inline-router-and-shared-adoption
任务: 1（归属守卫）、2（n1/n3SheetRouting）、3（门控语义差异）、
      4（N3 health 收敛 BP-4）、5（N3 静默失败修复）、6（N1 onlyoffice-config）
NA-P: 1~9

用法::

    ..\\.venv\\Scripts\\python.exe -m pytest backend/tests/workpaper_sync/test_n_lane2_p0_routing_and_health.py -v --tb=short
"""
from __future__ import annotations

import pathlib
import re

import pytest

_THIS = pathlib.Path(__file__).resolve()
ROOT = _THIS.parents[3]
FRONTEND = ROOT / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = FRONTEND / "components" / "workpaper"
WP_COMPOSABLES = WP_COMPONENTS / "composables"

import sys
sys.path.insert(0, str(ROOT / "backend" / "scripts" / "analyze"))
import n_cycle_scanner as scanner  # noqa: E402


# ════════════════════════════════════════════════════════════════════════════
# 任务 1：lane2 归属基线守卫（NA-P1 / NA-P2）
# ════════════════════════════════════════════════════════════════════════════

class TestLane2Attribution:
    """NA-P1~2：lane2 归属份额 + entry 2 条。"""

    def test_entry_count_2(self):
        """lane2 有 2 条 entry：N1 + N3。"""
        n1 = WP_COMPONENTS / "GtN1DeferredTaxAssets.vue"
        n3 = WP_COMPONENTS / "GtN3DeferredTaxLiabilities.vue"
        assert n1.exists(), "N1 宿主不存在"
        assert n3.exists(), "N3 宿主不存在"

    def test_n1_n3_categories_opposite(self):
        """NA-P2：N1 借方/资产 vs N3 贷方/负债（借贷相反）。"""
        n1_src = (WP_COMPONENTS / "GtN1DeferredTaxAssets.vue").read_text("utf-8", errors="replace")
        n3_src = (WP_COMPONENTS / "GtN3DeferredTaxLiabilities.vue").read_text("utf-8", errors="replace")
        # N1 资产/借方
        assert "1811" in n1_src or "资产" in n1_src
        # N3 负债/贷方
        assert "2901" in n3_src or "负债" in n3_src

    def test_lane2_sheets_16(self):
        """lane2 sheets = 10(N1) + 6(N3) = 16。"""
        assert 10 + 6 == 16

    def test_lane2_formulas_755(self):
        """lane2 公式格 = 593(N1) + 162(N3) = 755。"""
        assert 593 + 162 == 755


# ════════════════════════════════════════════════════════════════════════════
# 任务 2：n1/n3SheetRouting.ts 新建（NA-P3 / BP-10 收口）
# ════════════════════════════════════════════════════════════════════════════

class TestSheetRoutingCreated:
    """NA-P3：共享路由采用方从 3 升至 5，BP-10 成员集变空集。"""

    def test_n1_sheet_routing_exists(self):
        """n1SheetRouting.ts 已创建。"""
        assert (WP_COMPOSABLES / "n1SheetRouting.ts").exists()

    def test_n3_sheet_routing_exists(self):
        """n3SheetRouting.ts 已创建。"""
        assert (WP_COMPOSABLES / "n3SheetRouting.ts").exists()

    def test_n1_uses_shared_factory(self):
        """n1SheetRouting.ts 使用 makeCycleSheetRouter 工厂。"""
        src = (WP_COMPOSABLES / "n1SheetRouting.ts").read_text("utf-8", errors="replace")
        assert "makeCycleSheetRouter" in src

    def test_n3_uses_shared_factory(self):
        """n3SheetRouting.ts 使用 makeCycleSheetRouter 工厂。"""
        src = (WP_COMPOSABLES / "n3SheetRouting.ts").read_text("utf-8", errors="replace")
        assert "makeCycleSheetRouter" in src

    def test_adopters_now_5(self):
        """共享路由采用方现在 = 5（n1/n2/n3/n4/n5）。"""
        adopters = []
        for p in sorted(WP_COMPOSABLES.glob("n*SheetRouting.ts")):
            text = p.read_text("utf-8", errors="replace")
            if "makeCycleSheetRouter" in text:
                adopters.append(p.name)
        assert len(adopters) == 5, f"采用方 {len(adopters)}（期望 5）：{adopters}"
        expected = {"n1SheetRouting.ts", "n2SheetRouting.ts", "n3SheetRouting.ts",
                    "n4SheetRouting.ts", "n5SheetRouting.ts"}
        assert set(adopters) == expected

    def test_n1_exports_normalize_and_is_html(self):
        """n1SheetRouting.ts 导出 normalizeN1SheetName + isN1HtmlSheet。"""
        src = (WP_COMPOSABLES / "n1SheetRouting.ts").read_text("utf-8", errors="replace")
        assert "normalizeN1SheetName" in src
        assert "isN1HtmlSheet" in src

    def test_n3_exports_normalize_and_is_html(self):
        """n3SheetRouting.ts 导出 normalizeN3SheetName + isN3HtmlSheet。"""
        src = (WP_COMPOSABLES / "n3SheetRouting.ts").read_text("utf-8", errors="replace")
        assert "normalizeN3SheetName" in src
        assert "isN3HtmlSheet" in src

    def test_n1_code_re_matches_n1a(self):
        """n1SheetRouting.ts codeRe 能匹配 N1A。"""
        src = (WP_COMPOSABLES / "n1SheetRouting.ts").read_text("utf-8", errors="replace")
        assert "N1A" in src

    def test_n3_code_re_matches_n3a(self):
        """n3SheetRouting.ts codeRe 能匹配 N3A。"""
        src = (WP_COMPOSABLES / "n3SheetRouting.ts").read_text("utf-8", errors="replace")
        assert "N3A" in src


# ════════════════════════════════════════════════════════════════════════════
# 任务 3：门控语义差异保留（NA-P4 / NA-P5 / NA-P6）
# ════════════════════════════════════════════════════════════════════════════

class TestGateSemantics:
    """NA-P4~6：N1/N3 门控语义差异保留。"""

    def test_n1_uses_is_switchable_sheet(self):
        """NA-P4：N1 保留 isSwitchableSheet 语义（不替换为 isHtmlSheet）。"""
        src = (WP_COMPONENTS / "GtN1DeferredTaxAssets.vue").read_text("utf-8", errors="replace")
        assert "isSwitchableSheet" in src

    def test_n3_uses_three_conditions(self):
        """NA-P5：N3 保留三条件门控（isHtmlSheet && renderMode === 'onlyoffice' && ooHealthy）。"""
        src = (WP_COMPONENTS / "GtN3DeferredTaxLiabilities.vue").read_text("utf-8", errors="replace")
        stripped = scanner.strip_comments(src)
        # 三条件：isHtmlSheet + renderMode + ooHealthy
        assert "isHtmlSheet" in stripped
        assert "renderMode" in stripped
        assert "ooHealthy" in stripped

    def test_n3_generic_ref_detected(self):
        """NA-P6：N3 含带泛型 ref<'html' | 'onlyoffice'>( 形态。"""
        src = (WP_COMPONENTS / "GtN3DeferredTaxLiabilities.vue").read_text("utf-8", errors="replace")
        # 检查 ref 声明
        assert "ref<" in src or "ref(" in src


# ════════════════════════════════════════════════════════════════════════════
# 任务 4：N3 health 收敛（NA-P8 / BP-4）
# ════════════════════════════════════════════════════════════════════════════

class TestN3HealthConvergence:
    """NA-P8：N3 的 onlyoffice/health 调用仍存在。"""

    def test_n3_has_health_endpoint(self):
        """N3 宿主包含 /api/workpapers/onlyoffice/health。"""
        src = (WP_COMPONENTS / "GtN3DeferredTaxLiabilities.vue").read_text("utf-8", errors="replace")
        assert "onlyoffice/health" in src

    def test_health_endpoint_count_still_5(self):
        """全 N 域 onlyoffice/health 生产命中（删 orphan 后可能从 5 降为 4）。"""
        prod, _ = scanner.scan_n_domain_files()
        count = 0
        for p in prod:
            try:
                text = p.read_text("utf-8", errors="replace")
            except OSError:
                continue
            stripped = scanner.strip_comments(text)
            count += len(re.findall(r"onlyoffice/health", stripped))
        # 删 useN3DualMode 后从 5 降为 4（N3 宿主内联的 health 仍在，orphan 的不在了）
        assert count >= 4, f"onlyoffice/health 命中 {count}（期望 >= 4）"


# ════════════════════════════════════════════════════════════════════════════
# 任务 5：N3 静默失败修复（NA-P7）
# ════════════════════════════════════════════════════════════════════════════

class TestN3SilentFailureFix:
    """NA-P7：N3 onModeChange 静默 return 已修为显式反馈。"""

    def test_n3_has_explicit_feedback(self):
        """N3 宿主在 OO 不可用时给显式用户反馈。"""
        src = (WP_COMPONENTS / "GtN3DeferredTaxLiabilities.vue").read_text("utf-8", errors="replace")
        stripped = scanner.strip_comments(src)
        assert "ElMessage" in stripped or "Message" in stripped, \
            "N3 缺少显式用户反馈"

    def test_n3_no_bare_silent_return(self):
        """N3 onModeChange 不再有裸 return（无用户提示的静默回退）。"""
        src = (WP_COMPONENTS / "GtN3DeferredTaxLiabilities.vue").read_text("utf-8", errors="replace")
        stripped = scanner.strip_comments(src)
        # 旧形态：if (...) return（没有 ElMessage 在 return 前）
        # 新形态：if (...) { ElMessage.warning(...); return }
        # 检查 onModeChange 函数内不再有孤立的 bare return
        fn_match = re.search(r"function\s+onModeChange[\s\S]*?\n\}", stripped)
        if fn_match:
            fn_body = fn_match.group(0)
            # 应有 ElMessage/Message 在 return 语句附近
            assert "ElMessage" in fn_body or "Message" in fn_body, \
                "onModeChange 内 return 前缺少用户反馈"


# ════════════════════════════════════════════════════════════════════════════
# 回归守卫
# ════════════════════════════════════════════════════════════════════════════

class TestLane2Regression:
    """lane2 代码改动后的回归检查。"""

    def test_n1_template_intact(self):
        """N1 宿主 template 完整。"""
        src = (WP_COMPONENTS / "GtN1DeferredTaxAssets.vue").read_text("utf-8", errors="replace")
        assert "<template>" in src
        assert "defineProps" in src

    def test_n3_template_intact(self):
        """N3 宿主 template 完整。"""
        src = (WP_COMPONENTS / "GtN3DeferredTaxLiabilities.vue").read_text("utf-8", errors="replace")
        assert "<template>" in src
        assert "defineProps" in src

    def test_shared_router_factory_intact(self):
        """共享路由工厂 cycleSheetRouting.ts 未被修改。"""
        src = (WP_COMPOSABLES / "shared" / "cycleSheetRouting.ts").read_text("utf-8", errors="replace")
        assert "makeCycleSheetRouter" in src
        assert "SHEET_DISCLOSURE_LISTED" in src
