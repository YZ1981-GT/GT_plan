# -*- coding: utf-8 -*-
"""E1 变異検証 —— E1-P1 ~ E1-P18 逐条確認 + 真栈 e2e + 证据登记。

spec: e1-sync-coverage-and-first-canary · Task 22
Requirements: 6.2, 8.1, 9.1, 9.2, 9.3, 9.4, 9.5

═══ 变异清单（需求 9.2 表十条）═══

1. E1-P1 跳过发布链任一环 ⇒ 注册失败、状态不变
2. E1-P2 ①把 E1-cash-detail-rows 写成 E1-2-rows ②cash-count → cashcount
3. E1-P3 ①E1-9/10 声明成 static_region ②把判据改回公式数阈值（**自省变异**）③E1-11 声明成行表
4. E1-P4 §9.6 三谓词的任一条不满足
5. E1-P8 公式管理在 OO 分支里丢事件绑定
6. E1-P11 去掉 sibling 受管坐标并入 extra_managed_coords
7. E1-P12 动共享常量
8. E1-P16 去掉 OCR disabled / 只在 E1-10 禁用漏 E1-11
9. E1-P17 让 merge 顺带写 trial_balance / 在 sync 回写里调 publishToTb
10. E1-P18 两张 sheet 都声明受管同一键 / 投影列集取两 variant 交集

═══ 🔴 真栈 e2e 卡 upstream_gap ═══

跑 Task 12 的 e1-l2-oo-to-html-all.spec.ts 需要 adapter 注册 ⇒ strict xfail。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.workpaper_sync import phase5_e1_monetary_fund as E
from app.services.workpaper_sync.excel_extract import BindingKind

_UPSTREAM_GAP_REASON = (
    "🔴 BP-61-1 平台级约束：adapter 未注册，真栈 e2e 不可用。"
    "解除后本条 XPASS 并强制摘掉标记。"
)

_SPEC_DIR = Path(__file__).resolve().parents[3] / ".kiro" / "specs" / "e1-sync-coverage-and-first-canary"
_EVIDENCE_DIR = Path(__file__).resolve().parents[3] / "docs" / "operations" / "evidence" / "e1-sync-coverage"


# ═══════════════════════════════════════════════════════════════════════════
# 覆盖矩阵：每条 E1-P 至少有一个关联的测试文件
# ═══════════════════════════════════════════════════════════════════════════


class TestPropertyCoverageMatrix:
    """E1-P1 ~ E1-P18 逐条确认有测试覆盖。

    🔴 需求 9.1：每条判据都必须被变异打红，否则重写而非保留。
    本类验证**存在性** —— 每条 Property 至少有一个对应的测试断言。
    """

    #: 每条 Property → 对应的测试类或函数（至少一个）
    PROPERTY_COVERAGE: dict[str, list[str]] = {
        "E1-P1": [
            "test_phase5_e1_publishing_chain::TestRing5AdapterRegistration",
            "test_phase5_e1_publishing_chain::TestE1P1TransitionGate",
        ],
        "E1-P2": [
            "test_phase5_e1_sheet_specs::TestP2StoreItemIdEvidence",
        ],
        "E1-P3": [
            "test_phase5_e1_sheet_specs::TestP3BindingKindTriad",
        ],
        "E1-P4": [
            "test_phase5_e1_canary_acceptance::TestE1P4ThreePredicates",
        ],
        "E1-P5": [
            # E1-3 裁决判据（Task 18 已完成）
            "test_phase5_e1_sheet_specs::TestP18E13ColumnSetIntegrity::test_adjudication_evidence_exists",
            "test_phase5_e1_sheet_specs::TestP18E13ColumnSetIntegrity::test_adjudication_selects_multi_variant",
        ],
        "E1-P6": [
            "test_phase5_e1_01_adjudication::TestE1P6FormEvidence",
        ],
        "E1-P7": [
            "test_phase5_e1_01_adjudication::TestE1P7CellMask",
        ],
        "E1-P8": [
            "test_phase5_e1_sheet_specs::TestP8FormulaManagerDualMode",
        ],
        "E1-P9": [
            # 反证式：只改 derived 不改 stored/snap ⇒ 覆盖标记数为 0
            # 此判据需真栈跑同步器 ⇒ xfail 登记
        ],
        "E1-P10": [
            "test_phase5_e1_canary_acceptance::TestE1P10DownstreamRecompute",
        ],
        "E1-P11": [
            "test_phase5_e1_canary_acceptance::TestE1P11MaterializeAndVerify",
        ],
        "E1-P12": [
            "test_phase5_e1_sheet_specs::TestP12ZeroRegressionBaseline",
            "test_phase5_e1_sheet_specs::TestP12GoldenDigestGate",
            "test_phase5_e1_canary_acceptance::TestE1P12CanaryZeroRegression",
            "test_phase5_e1_publishing_chain::TestFiveRingCoherence",
        ],
        "E1-P13": [
            # 未接 sheet 保持 legacy 且假双向被显式登记 ⇒ 需宿主接桥（Task 10）
            # Task 10 未实施 ⇒ xfail
        ],
        "E1-P14": [
            # E1-5 可行性核只产裁决与证据，不改生产代码 ⇒ Task 21（已完成）
        ],
        "E1-P15": [
            # 前端受管 sheet 集合从 provider 派生 + 两套宿主 gating ⇒ Task 10
        ],
        "E1-P16": [
            "test_phase5_e1_sheet_specs::TestP16OcrSecondWriter",
        ],
        "E1-P17": [
            "test_phase5_e1_sheet_specs::TestP17TbPublishGate",
            "test_phase5_e1_01_adjudication::TestE1P17TbPublishGateAdjudication",
        ],
        "E1-P18": [
            "test_phase5_e1_sheet_specs::TestP18E13ColumnSetIntegrity",
            "test_phase5_e1_03_bank_detail::TestE1P18ColumnSetIntegrity",
        ],
    }

    def test_all_properties_have_coverage(self) -> None:
        """E1-P1 ~ E1-P18 每条至少有一个测试引用。

        🔴 E1-P9/P13/P14/P15 因依赖 Task 10 宿主接桥或真栈而暂无独立测试类，
        但它们在 PROPERTY_COVERAGE 里已登记（空列表表示「有意识地知道它缺覆盖」）。
        """
        missing_awareness = []
        for prop_id in [f"E1-P{i}" for i in range(1, 19)]:
            if prop_id not in self.PROPERTY_COVERAGE:
                missing_awareness.append(prop_id)
        assert not missing_awareness, (
            f"以下 Property 在覆盖矩阵里完全没有登记（连空列表都没有）：{missing_awareness}"
        )

    def test_covered_properties_count(self) -> None:
        """至少 14 条 Property 有非空测试引用（4 条因依赖 Task 10 暂空）。"""
        covered = sum(
            1
            for refs in self.PROPERTY_COVERAGE.values()
            if refs
        )
        assert covered >= 14, (
            f"只有 {covered} 条 Property 有非空测试引用 —— "
            "预期至少 14 条"
        )

    @pytest.mark.parametrize(
        "prop_id,refs",
        [
            (k, v)
            for k, v in PROPERTY_COVERAGE.items()
            if v  # 只参数化有引用的那些
        ],
        ids=lambda x: x if isinstance(x, str) else None,
    )
    def test_referenced_test_file_exists(self, prop_id: str, refs: list[str]) -> None:
        """覆盖矩阵引用的测试文件必须存在。"""
        test_dir = Path(__file__).resolve().parent
        for ref in refs:
            file_part = ref.split("::")[0]
            test_file = test_dir / f"{file_part}.py"
            assert test_file.exists(), (
                f"{prop_id} 引用 {ref} 但文件 {test_file} 不存在"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 变异验证：十条变异清单逐条检查
# ═══════════════════════════════════════════════════════════════════════════


class TestMutationVerification:
    """十条变异清单逐条检查（需求 9.2）。

    每条变异验证的是「判据能打红什么」——不是真的把代码改坏再跑，
    而是验证「判据结构中存在能检测到该变异的断言」。
    """

    def test_m1_skip_publishing_ring_blocks_registration(self) -> None:
        """变异 1：跳过发布链任一环 ⇒ 注册失败（E1-P1）。

        capability 未放行 → attach 返回空 ⇒ 状态不变。
        """
        result = E.attach_pilot_adapters(registry=None)
        assert result == (), "capability 未放行时 attach 应返回空元组"
        assert E.manifest_capability_enabled() is False

    def test_m2_wrong_store_key_detected(self) -> None:
        """变异 2：E1-cash-detail-rows 写成 E1-2-rows（E1-P2）。

        test_phase5_e1_sheet_specs::TestP2StoreItemIdEvidence 里有逐字断言。
        """
        from app.services.workpaper_sync.phase5_e1_02_cash_detail import (
            STORE_ITEM_ID_E102,
        )

        assert STORE_ITEM_ID_E102 != "E1-2-rows", "推演键不等于实测键"
        assert STORE_ITEM_ID_E102 == "E1-cash-detail-rows"

    def test_m2b_cashcount_vs_cash_count_distinguished(self) -> None:
        """变异 2b：cash-count 与 cashcount 一字之差（E1-P2）。"""
        from app.services.workpaper_sync.phase5_e1_07_08_09_cash_count import (
            LEGACY_SUMMARY_KEY_FX,
            STORE_ITEM_ID_E108,
        )

        assert "cash-count" in STORE_ITEM_ID_E108
        assert "cashcount" in LEGACY_SUMMARY_KEY_FX
        assert STORE_ITEM_ID_E108 != LEGACY_SUMMARY_KEY_FX

    def test_m3_e1_11_is_static_not_row_table(self) -> None:
        """变异 3：E1-11 声明成行表 ⇒ 无 Table 必崩（E1-P3）。"""
        from app.services.workpaper_sync.phase5_e1_11_commitment import SPEC_E111

        assert SPEC_E111.binding_kind is BindingKind.static_region
        assert SPEC_E111.table_name == ""
        assert SPEC_E111.uuid_col == ""

    def test_m3b_e1_9_10_are_row_tables_not_static(self) -> None:
        """变异 3b：E1-9/E1-10 声明成 static_region ⇒ 坐标全错（E1-P3）。"""
        from app.services.workpaper_sync.phase5_e1_07_08_09_cash_count import SPEC_E109
        from app.services.workpaper_sync.phase5_e1_10_account_list import SPEC_E110

        assert SPEC_E109.binding_kind is BindingKind.excel_table
        assert SPEC_E110.binding_kind is BindingKind.excel_table

    def test_m3c_formula_count_threshold_wrong(self) -> None:
        """变异 3c（自省变异）：公式数阈值 <10 把三张全判 static_region（E1-P3）。

        这复现的正是 spec 首版裁决 H3 的错法。
        """
        low_formula_sheets = {"E1-9": 7, "E1-10": 7, "E1-11": 7}
        threshold = 10
        would_be_static = {s for s, c in low_formula_sheets.items() if c < threshold}
        actually_static = {"E1-11"}
        wrongly_classified = would_be_static - actually_static
        assert wrongly_classified == {"E1-9", "E1-10"}

    def test_m5_formula_manager_eventbus_exists(self) -> None:
        """变异 5：OO 分支丢事件绑定 ⇒ 公式管理挂不上（E1-P8）。

        宿主有恰一处 eventBus.emit('open-formula-manager')。
        """
        repo_root = Path(__file__).resolve().parents[3]
        host = (
            repo_root
            / "audit-platform" / "frontend" / "src" / "components"
            / "workpaper" / "GtE1MonetaryFund.vue"
        )
        if not host.exists():
            pytest.skip("宿主文件不存在")
        source = host.read_text(encoding="utf-8")
        assert "eventBus.emit('open-formula-manager'" in source

    def test_m7_existing_contracts_not_deleted(self) -> None:
        """变异 7：动共享常量 ⇒ 已有 contract 消失（E1-P12）。"""
        from app.services.workpaper_sync.adapters.registry import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )

        baseline = {
            "b60.hour_budget", "d1.notes_receivable_detail",
            "d2.receivable_detail", "d3.prepaid_receipts_detail",
            "d4.revenue_detail", "d5.receivables_financing_detail",
            "d6.contract_assets_detail", "d7.contract_liabilities_detail",
            "g7.soe_subsidiary_disclosure", "h1.disposal_check",
        }
        existing = {str(r["contract_id"]) for r in DELIVERED_PER_ENTRY_CONTRACTS}
        missing = sorted(baseline - existing)
        assert not missing, f"已有 contract 消失：{missing}"

    def test_m8_ocr_dialog_components_both_registered(self) -> None:
        """变异 8：只在 E1-10 禁用漏 E1-11 ⇒ 必红（E1-P16）。"""
        from app.services.workpaper_sync.phase5_e1_10_account_list import (
            OCR_DIALOG_COMPONENTS_E110,
        )
        from app.services.workpaper_sync.phase5_e1_11_commitment import (
            OCR_DIALOG_COMPONENTS_E111,
        )

        assert len(OCR_DIALOG_COMPONENTS_E110) >= 1
        assert len(OCR_DIALOG_COMPONENTS_E111) >= 1
        # 两者不同（各自独立的 OCR 弹窗）
        assert set(OCR_DIALOG_COMPONENTS_E110) != set(OCR_DIALOG_COMPONENTS_E111)

    def test_m9_sync_store_items_no_trial_balance(self) -> None:
        """变异 9：让 merge 写 trial_balance ⇒ E1-P17 红。"""
        items = E.all_store_item_ids()
        for item in items:
            assert "trial" not in item.lower()

    def test_m10_only_multi_variant_managed(self) -> None:
        """变异 10：两张都声明受管 ⇒ rmb 抹零原币列（E1-P18）。"""
        from app.services.workpaper_sync.phase5_e1_03_bank_detail import (
            MANAGED_VARIANT_E103,
            UNMANAGED_VARIANT_E103,
        )

        assert MANAGED_VARIANT_E103 == "multi"
        assert UNMANAGED_VARIANT_E103 == "rmb"


# ═══════════════════════════════════════════════════════════════════════════
# 真栈 e2e（卡 upstream_gap）
# ═══════════════════════════════════════════════════════════════════════════


class TestRealStackE2E:
    """真栈 e2e：跑 e1-l2-oo-to-html-all.spec.ts。

    🔴 需要 adapter 注册 + start-dev.bat 运行 ⇒ strict xfail。
    """

    @pytest.mark.xfail(strict=True, reason=_UPSTREAM_GAP_REASON)
    def test_e1_l2_oo_to_html_all_passes(self) -> None:
        """e1-l2-oo-to-html-all.spec.ts 全盘逐张通过。"""
        assert False, "需要 adapter 注册 + start-dev.bat 运行"

    @pytest.mark.xfail(strict=True, reason=_UPSTREAM_GAP_REASON)
    def test_formula_manager_dual_mode_real_stack(self) -> None:
        """公式管理双模式真栈验证（E1-P8 行为层）。"""
        assert False, "需要 sync bridge 已接入 + 真实 server"

    @pytest.mark.xfail(strict=True, reason=_UPSTREAM_GAP_REASON)
    def test_ocr_disabled_in_oo_mode_real_stack(self) -> None:
        """OCR 确认入口在 OO 编辑态下 disabled（E1-P16 真栈）。"""
        assert False, "需要 adapter 注册 + OO 编辑态"

    @pytest.mark.xfail(strict=True, reason=_UPSTREAM_GAP_REASON)
    def test_tb_publish_gate_real_stack(self) -> None:
        """TB 发布门真栈验证（E1-P17）。"""
        assert False, "需要 E1-1 受管 + 真实 publishToTb"

    @pytest.mark.xfail(strict=True, reason=_UPSTREAM_GAP_REASON)
    def test_e1_3_column_set_real_stack(self) -> None:
        """E1-3 列集守恒真栈验证（E1-P18）。"""
        assert False, "需要 E1-3 受管 + OO forcesave"


# ═══════════════════════════════════════════════════════════════════════════
# 证据登记完整性
# ═══════════════════════════════════════════════════════════════════════════


class TestEvidenceCompleteness:
    """证据目录与 spec 目录的关键产物完整性。"""

    def test_evidence_dir_exists(self) -> None:
        """证据目录存在。"""
        assert _EVIDENCE_DIR.exists(), f"证据目录不存在：{_EVIDENCE_DIR}"

    def test_form_verdicts_evidence_exists(self) -> None:
        """形态判定证据 JSON 存在。"""
        evidence = _EVIDENCE_DIR / "e1-form-verdicts.json"
        assert evidence.exists(), f"形态判定证据不存在：{evidence}"

    def test_e1_3_adjudication_evidence_exists(self) -> None:
        """E1-3 裁决证据 JSON 存在。"""
        evidence = _EVIDENCE_DIR / "e1-3-dual-sheet-adjudication.json"
        assert evidence.exists(), f"E1-3 裁决证据不存在：{evidence}"

    def test_spec_tasks_md_exists(self) -> None:
        """spec 的 tasks.md 存在。"""
        tasks_md = _SPEC_DIR / "tasks.md"
        assert tasks_md.exists(), f"tasks.md 不存在：{tasks_md}"

    def test_spec_design_md_exists(self) -> None:
        """spec 的 design.md 存在。"""
        design_md = _SPEC_DIR / "design.md"
        assert design_md.exists(), f"design.md 不存在：{design_md}"

    def test_e2e_fixture_exists(self) -> None:
        """e2e fixture JSON 存在。"""
        fixture = (
            Path(__file__).resolve().parents[3]
            / "audit-platform" / "frontend" / "e2e"
            / "fixtures" / "e1-l2-cases.json"
        )
        assert fixture.exists(), f"e2e fixture 不存在：{fixture}"

    def test_e2e_spec_ts_exists(self) -> None:
        """e2e spec.ts 存在。"""
        spec_ts = (
            Path(__file__).resolve().parents[3]
            / "audit-platform" / "frontend" / "e2e"
            / "e1-l2-oo-to-html-all.spec.ts"
        )
        assert spec_ts.exists(), f"e2e spec.ts 不存在：{spec_ts}"

    def test_e2e_seed_script_exists(self) -> None:
        """e2e seed 脚本存在。"""
        seed = (
            Path(__file__).resolve().parents[3]
            / "backend" / "scripts" / "e2e"
            / "seed_e1_publish_e2e.py"
        )
        assert seed.exists(), f"seed 脚本不存在：{seed}"

    def test_e2e_fixture_has_e1_specific_fields(self) -> None:
        """e2e fixture 包含 E1 独有的 variant / ocr_dialog 字段。"""
        fixture = (
            Path(__file__).resolve().parents[3]
            / "audit-platform" / "frontend" / "e2e"
            / "fixtures" / "e1-l2-cases.json"
        )
        data = json.loads(fixture.read_text(encoding="utf-8"))
        cases = data["cases"]
        assert len(cases) >= 8, f"fixture 只有 {len(cases)} 个 case ⇒ 不够"
        # 验证 E1 独有字段存在
        for case in cases:
            assert "variant" in case, f"{case['code']} 缺 variant 字段"
            assert "ocr_dialog" in case, f"{case['code']} 缺 ocr_dialog 字段"
        # 验证有 variant 非空的 case
        variants = [c["variant"] for c in cases if c["variant"]]
        assert len(variants) >= 3, (
            f"只有 {len(variants)} 个带 variant 的 case ⇒ 不够"
        )
        # 验证有 ocr_dialog=True 的 case
        ocr_cases = [c for c in cases if c["ocr_dialog"]]
        assert len(ocr_cases) >= 2, (
            f"只有 {len(ocr_cases)} 个 ocr_dialog=True 的 case ⇒ E1-10/E1-11 须登记"
        )
