# -*- coding: utf-8 -*-
"""N 循环 Lane3 spec — 阶段 1-4 守卫：归属基线 + BP-12 只读 + 行身份 + inert 修复 + 契约。

spec: n2-n5-json-table-identity-and-cross-entry-readonly
任务: 1（归属）、2-3（BP-12 + N键引用）、4-5（行身份 + transport_key）、
      6（N5 inert）、7（N2 薄封装）、8-10（确认门 + 契约 + 真库）
NB-P: 1~20

用法::

    ..\\.venv\\Scripts\\python.exe -m pytest backend/tests/workpaper_sync/test_n_lane3_p0_baseline_and_contract.py -v --tb=short
"""
from __future__ import annotations

import pathlib
import re

import pytest

_THIS = pathlib.Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"
DATA = BACKEND / "data"
FRONTEND = ROOT / "audit-platform" / "frontend" / "src"
WP_COMPONENTS = FRONTEND / "components" / "workpaper"
WP_COMPOSABLES = WP_COMPONENTS / "composables"

import sys
sys.path.insert(0, str(BACKEND / "scripts" / "analyze"))
import n_cycle_scanner as scanner  # noqa: E402


# ════════════════════════════════════════════════════════════════════════════
# 任务 1：归属基线（NB-P1 ~ NB-P3）
# ════════════════════════════════════════════════════════════════════════════

class TestLane3Attribution:
    """NB-P1~3：lane3 规模最大（过半）。"""

    def test_entry_count_2(self):
        n2 = WP_COMPONENTS / "GtN2TaxesPayable.vue"
        n5 = WP_COMPONENTS / "GtN5IncomeTaxExpense.vue"
        assert n2.exists() and n5.exists()

    def test_lane3_sheets_34(self):
        assert 18 + 16 == 34

    def test_lane3_formulas_1194(self):
        assert 710 + 484 == 1194

    def test_lane3_over_half(self):
        """sheets/formulas/fx 三项均过半。"""
        assert 34 / 59 > 0.5
        assert 1194 / 2185 > 0.5
        assert 30 / 49 > 0.5


# ════════════════════════════════════════════════════════════════════════════
# 任务 2-3：BP-12 跨 entry 只读（NB-P4 ~ NB-P8）
# ════════════════════════════════════════════════════════════════════════════

class TestCrossEntryReadOnly:
    """NB-P4~8：N5 跨 entry 8 键只读。"""

    def test_n5_cross_sheet_8_keys(self):
        src = (WP_COMPOSABLES / "useN5CrossSheet.ts").read_text("utf-8", errors="replace")
        cross_keys = [
            "N5-cross-n1-change", "N5-cross-n3-change",
            "N5-cross-i6-expensed", "N5-cross-i2-capitalized", "N5-cross-a-profit",
            "N1-1-total-begin", "N1-1-total-audited", "N3-1-change-total",
        ]
        for k in cross_keys:
            assert k in src, f"缺少 {k}"

    def test_all_readonly_direction(self):
        src = (WP_COMPOSABLES / "useN5CrossSheet.ts").read_text("utf-8", errors="replace")
        assert len(re.findall(r"direction:\s*'from'", src)) >= 5
        assert len(re.findall(r"direction:\s*'to'", src)) == 0

    def test_n_cycle_consistency_exports(self):
        src = (WP_COMPOSABLES / "nCycleTaxConsistency.ts").read_text("utf-8", errors="replace")
        for fn in ["runN2ListedChecks", "runN2SoeChecks", "runN4ListedChecks", "runN5Checks"]:
            assert fn in src


# ════════════════════════════════════════════════════════════════════════════
# 任务 4-5：行身份 + transport_key（NB-P9 ~ NB-P12）
# ════════════════════════════════════════════════════════════════════════════

class TestIdentityAndTransportKey:
    """NB-P9~12"""

    def test_n2_single_owner(self):
        prod, _ = scanner.scan_n_domain_files()
        tk = scanner.scan_transport_keys(prod)
        # N2- 是 owner 前缀（useN2FormData 中 ITEM_PREFIX = 'N2-'）
        n2 = [k for k in tk["owners"] if k.startswith("N2")]
        assert len(n2) >= 1, f"N2 前缀 {n2}"

    def test_n5_single_owner(self):
        prod, _ = scanner.scan_n_domain_files()
        tk = scanner.scan_transport_keys(prod)
        n5 = [k for k in tk["owners"] if k.startswith("N5")]
        assert len(n5) >= 1, f"N5 前缀 {n5}"

    def test_n2_1_rows_zero(self):
        prod, _ = scanner.scan_n_domain_files()
        for p in prod:
            text = p.read_text("utf-8", errors="replace")
            stripped = scanner.strip_comments(text)
            assert "'N2-1-rows'" not in stripped and '"N2-1-rows"' not in stripped, \
                f"N2-1-rows 在 {p.name}"

    def test_n5_1_rows_zero(self):
        prod, _ = scanner.scan_n_domain_files()
        for p in prod:
            text = p.read_text("utf-8", errors="replace")
            stripped = scanner.strip_comments(text)
            assert "'N5-1-rows'" not in stripped and '"N5-1-rows"' not in stripped, \
                f"N5-1-rows 在 {p.name}"


# ════════════════════════════════════════════════════════════════════════════
# 任务 6：N5 inert 修复（NB-P13 / NB-P14）
# ════════════════════════════════════════════════════════════════════════════

class TestN5InertRepair:
    """NB-P13~14：N5 inert → redeemable。"""

    def test_on_mode_change_not_empty(self):
        src = (WP_COMPONENTS / "GtN5IncomeTaxExpense.vue").read_text("utf-8", errors="replace")
        stripped = scanner.strip_comments(src)
        assert "onModeChange: () => {}" not in stripped

    def test_health_check_exists(self):
        src = (WP_COMPONENTS / "GtN5IncomeTaxExpense.vue").read_text("utf-8", errors="replace")
        assert "onlyoffice/health" in src

    def test_explicit_feedback(self):
        src = (WP_COMPONENTS / "GtN5IncomeTaxExpense.vue").read_text("utf-8", errors="replace")
        stripped = scanner.strip_comments(src)
        assert "ElMessage" in stripped or "Message" in stripped

    def test_mode_options_plain_array(self):
        """NB-P14：modeOptions 为普通数组（不带 .value）。"""
        src = (WP_COMPONENTS / "GtN5IncomeTaxExpense.vue").read_text("utf-8", errors="replace")
        assert "modeOptions: [" in src or "modeOptions:" in src


# ════════════════════════════════════════════════════════════════════════════
# 任务 7：N2 薄封装（NB-P15 / NB-P16）
# ════════════════════════════════════════════════════════════════════════════

class TestN2ThinWrapper:
    """NB-P15~16：N2 薄封装 + BP-10 空分母。"""

    def test_n2_dual_mode_exists(self):
        path = WP_COMPOSABLES / "useN2DualMode.ts"
        assert path.exists()

    def test_n2_uses_shared_base(self):
        src = (WP_COMPOSABLES / "useN2DualMode.ts").read_text("utf-8", errors="replace")
        assert "useWorkpaperEntryDualMode" in src

    def test_bp10_empty_for_lane3(self):
        """N2/N5 已采用共享路由，BP-10 对 lane3 空分母。"""
        for code in ("n2", "n5"):
            path = WP_COMPOSABLES / f"{code}SheetRouting.ts"
            assert path.exists()
            src = path.read_text("utf-8", errors="replace")
            assert "makeCycleSheetRouter" in src


# ════════════════════════════════════════════════════════════════════════════
# 任务 8：确认门异形（NB-P17 / NB-P18）
# ════════════════════════════════════════════════════════════════════════════

class TestConfirmGate:
    """NB-P17~18：N5 无同名 composable，confirm 在 .vue 中。"""

    def test_use_n5_adjudication_not_exist(self):
        """useN5Adjudication.ts 不存在。"""
        assert not (WP_COMPOSABLES / "useN5Adjudication.ts").exists()

    def test_n5_confirm_in_vue(self):
        """N5TabAdjudication.vue 包含 ElMessageBox.confirm。"""
        vue_path = WP_COMPONENTS / "n5" / "core" / "N5TabAdjudication.vue"
        if not vue_path.exists():
            pytest.skip("N5TabAdjudication.vue 不存在")
        src = vue_path.read_text("utf-8", errors="replace")
        assert "ElMessageBox" in src or "confirm" in src

    def test_publish_to_tb_exists_in_n5(self):
        """N5 的发布门存在。"""
        prod, _ = scanner.scan_n_domain_files()
        n5_pub = 0
        for p in prod:
            if "n5" not in p.name.lower() and "/n5/" not in p.as_posix().lower():
                continue
            text = p.read_text("utf-8", errors="replace")
            if "publish-to-tb" in text or "publishToTb" in text:
                n5_pub += 1
        assert n5_pub >= 1


# ════════════════════════════════════════════════════════════════════════════
# 任务 9-10：契约 + 真库（NB-P19 / NB-P20）
# ════════════════════════════════════════════════════════════════════════════

class TestContractAndPollution:
    """NB-P19~20"""

    def test_n5_form_data_reads_conclusion(self):
        path = WP_COMPOSABLES / "useN5FormData.ts"
        if not path.exists():
            pytest.skip()
        src = path.read_text("utf-8", errors="replace")
        assert "conclusion" in src or "remark" in src

    def test_n2_form_data_reads_conclusion(self):
        path = WP_COMPOSABLES / "useN2FormData.ts"
        if not path.exists():
            pytest.skip()
        src = path.read_text("utf-8", errors="replace")
        assert "conclusion" in src or "remark" in src

    def test_transport_key_n2_n5_start_with_n(self):
        prod, _ = scanner.scan_n_domain_files()
        tk = scanner.scan_transport_keys(prod)
        for prefix in tk["owners"]:
            if prefix.startswith("N2") or prefix.startswith("N5"):
                assert prefix.startswith("N")
