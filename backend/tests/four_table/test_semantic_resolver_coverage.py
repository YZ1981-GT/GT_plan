"""守卫：所有四表取数 render 策略必须接入 semantic_account_resolver。

覆盖 Task 11（D/F）+ Task 16（H/I）+ Task 19（K）+ Task 23（L/M）+ Task 26（降级守卫）。

验证：
1. 所有有 _fetch_tb_data 或 TbBalance 引用的 render 策略必须含 resolve_semantic_accounts
2. 各 per-cycle _specs.py 文件的 spec 声明互不冲突（兜底码跨循环互斥）
3. 新增文件禁止引入 resolve_report_line_accounts（降级守卫）

spec: semantic-account-resolver-full-rollout Task 11/16/19/23/26
"""
import os
import re
from pathlib import Path

import pytest

RENDER_DIR = Path(__file__).resolve().parents[2] / "app" / "routers" / "wp_render_strategies"
FOUR_TABLE_DIR = Path(__file__).resolve().parents[2] / "app" / "services" / "four_table"

# Patterns that indicate "skip this file" (not a main render strategy)
SKIP_PATTERNS = (
    "_ai", "_import_export", "_service", "_validate", "_ocr", "_engine",
    "_sync", "_export", "_disclosure_io", "_contract_ocr", "_stocktake",
    "_special", "_valuation", "_derecognition", "_peer_policies",
    "_depreciation", "_amortization", "_capitalization", "_dcf",
    "_interest_cap", "_transfer", "_property_ocr", "_plan_sync", "_summary_sync",
)


def _get_render_strategies() -> list[Path]:
    """All main render strategy files for D~N cycles."""
    files = []
    for f in sorted(RENDER_DIR.iterdir()):
        if not f.name.startswith("_") or not f.name.endswith(".py"):
            continue
        if any(x in f.name for x in SKIP_PATTERNS):
            continue
        m = re.match(r"_([a-z]\d+)_", f.name)
        if not m:
            continue
        cycle = m.group(1).upper()
        if cycle[0] not in "DEFGHIJKLMN":
            continue
        content = f.read_text(encoding="utf-8")
        # Only include files with four-table data access
        has_tb = (
            "_fetch_tb" in content
            or "TbBalance" in content
            or "resolve_report_line_accounts" in content
            or "ReportLineAccountSpec" in content
        )
        if has_tb:
            files.append(f)
    return files


class TestSemanticResolverCoverage:
    """Property: 所有四表取数 render 策略都已接入 semantic_account_resolver。"""

    def test_all_strategies_use_semantic_resolver(self):
        """每个有 _fetch_tb/TbBalance 的 render 策略必须含 resolve_semantic_accounts。"""
        strategies = _get_render_strategies()
        assert len(strategies) >= 50, f"策略数不足（预期 ≥50，实际 {len(strategies)}）"

        missing = []
        for f in strategies:
            content = f.read_text(encoding="utf-8")
            if "resolve_semantic_accounts" not in content:
                missing.append(f.name)

        assert missing == [], (
            f"以下 {len(missing)} 个策略未接入 semantic_account_resolver:\n"
            + "\n".join(f"  {m}" for m in missing)
        )

    def test_coverage_count(self):
        """至少 57 个策略已迁移（当前全量）。"""
        strategies = _get_render_strategies()
        migrated = sum(
            1 for f in strategies
            if "resolve_semantic_accounts" in f.read_text(encoding="utf-8")
        )
        assert migrated >= 57, f"已迁移 {migrated}，预期 ≥57"


class TestPerCycleSpecsExist:
    """Property: 每个循环都有对应的 _specs.py 文件。"""

    @pytest.mark.parametrize("module", [
        "g_cycle_specs", "d_cycle_specs", "f_cycle_specs",
        "h_cycle_specs", "i_cycle_specs", "l_cycle_specs",
        "m_cycle_specs", "n_cycle_specs", "k_cycle_specs",
    ])
    def test_specs_module_importable(self, module):
        """每个循环的 specs 模块可以 import。"""
        import importlib
        mod = importlib.import_module(f"app.services.four_table.{module}")
        assert mod is not None

    def test_j_cycle_has_semantic_specs(self):
        """J 循环有 SemanticAccountSpec 声明。"""
        from app.services.four_table.j_cycle_account_scope import j_semantic_spec_of
        assert j_semantic_spec_of("J1") is not None
        assert j_semantic_spec_of("J2") is not None

    def test_k_cycle_has_semantic_bridge(self):
        """K 循环有 KCycleSpec → SemanticAccountSpec 转换。"""
        from app.services.four_table.k_cycle_specs import semantic_spec_of
        assert semantic_spec_of("K3") is not None
        assert semantic_spec_of("K8") is not None


class TestFallbackCodeMutualExclusion:
    """Property: 跨循环兜底码不得重复（同一标准码不出现在两个循环的 gross 槽）。"""

    def test_no_duplicate_fallback_across_cycles(self):
        """所有 _specs.py 的 gross 兜底码无交集。"""
        from app.services.four_table.d_cycle_specs import D_CYCLE_SPECS
        from app.services.four_table.f_cycle_specs import F_CYCLE_SPECS
        from app.services.four_table.g_cycle_specs import G_CYCLE_SPECS
        from app.services.four_table.i_cycle_specs import I_CYCLE_SPECS
        from app.services.four_table.l_cycle_specs import L_CYCLE_SPECS
        from app.services.four_table.m_cycle_specs import M_CYCLE_SPECS
        from app.services.four_table.n_cycle_specs import N_CYCLE_SPECS

        all_specs = {}
        for name, specs_dict in [
            ("D", D_CYCLE_SPECS), ("F", F_CYCLE_SPECS), ("G", G_CYCLE_SPECS),
            ("I", I_CYCLE_SPECS), ("L", L_CYCLE_SPECS), ("M", M_CYCLE_SPECS),
            ("N", N_CYCLE_SPECS),
        ]:
            for wp_code, spec in specs_dict.items():
                for slot in spec.slots:
                    if slot.key == "gross" and slot.fallback_standard_codes:
                        for code in slot.fallback_standard_codes:
                            if code in all_specs:
                                pytest.fail(
                                    f"兜底码 {code} 被 {all_specs[code]} 与 {wp_code} 同时认领"
                                )
                            all_specs[code] = wp_code


class TestNoNewReportLineAccountsImport:
    """降级守卫：新增 render 文件不得引入 report_line_accounts。

    存量文件（迁移前已用 RLA 的）保留在白名单内，但新文件不许新增。
    白名单随存量文件逐步清零（每清一个都须跑测试确认无回归）。
    """

    # 白名单：迁移前已存在 RLA 引用的文件（允许保留，不要求一步到位全删）
    LEGACY_RLA_WHITELIST = frozenset({
        "_d2_accounts_receivable.py",
        "_f1_prepayment.py",
        "_f3_notes_payable.py",
        "_f4_accounts_payable.py",
        "_f5_cost_of_sales.py",
        "_g7_long_term_equity_main.py",
        "_h1_fixed_assets.py",
        "_j1_employee_compensation.py",
        "_j2_defined_benefit_plan.py",
        "_k1_other_receivables.py",
        "_k1_import_export.py",
        "_k2_other_current_assets.py",
        "_k3_other_payables.py",
        "_k4_other_current_liabilities.py",
        "_k5_provisions.py",
        "_k6_held_for_sale.py",
        "_k7_deferred_income.py",
        "_m4_capital_reserve.py",
        "_m5_surplus_reserve.py",
        "_m7_special_reserve.py",
        "_m9_other_comprehensive_income.py",
        "_n1_deferred_tax_assets.py",
        "_n3_deferred_tax_liabilities.py",
        "_n4_taxes_and_surcharges.py",
        "_n5_income_tax_expense.py",
    })

    def test_no_new_rla_imports(self):
        """白名单外的文件不得含 `from app.services.four_table.report_line_accounts import`。"""
        violations = []
        for f in RENDER_DIR.iterdir():
            if not f.name.endswith(".py") or not f.name.startswith("_"):
                continue
            if f.name in self.LEGACY_RLA_WHITELIST:
                continue
            content = f.read_text(encoding="utf-8")
            if "from app.services.four_table.report_line_accounts import" in content:
                violations.append(f.name)

        assert violations == [], (
            f"以下文件不在白名单内却引入了 report_line_accounts（新文件禁止引入）:\n"
            + "\n".join(f"  {v}" for v in violations)
        )
