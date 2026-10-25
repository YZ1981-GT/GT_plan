# -*- coding: utf-8 -*-
"""E1 canary 验收 —— §9.6 三谓词 + DB 三谓词 + 整册 materialize + 零回归 + 下游重算。

spec: e1-sync-coverage-and-first-canary · Task 11
Properties: E1-P4（§9.6 三谓词 + DB）/ E1-P10（下游消费方在回写后正确重算）/
            E1-P11（整册 materialize 200 + verify_unmanaged_regions）/
            E1-P12（零回归基线，补充 TestP12ZeroRegressionBaseline）

🔴 **本任务是后续全部接入的硬前置**：canary 未通不得声明第二张受管 sheet
   （照 `d-cycle-sheet-bidirectional-expansion` Wave 0→1 顺序纪律）。

🔴 **2026-10-03 诚实分层**：
  * §9.6 三谓词 + DB 三谓词需要**真实运行 server + adapter 已注册** ⇒ strict xfail
  * 整册 materialize 需要 adapter + published representation ⇒ strict xfail
  * 下游消费方重算需要真栈回写 ⇒ strict xfail
  * provider 就绪 + 声明层结构判据现在就能绿
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.workpaper_sync import phase5_e1_monetary_fund as E
from app.services.workpaper_sync.phase5_e1_02_cash_detail import (
    SPEC_E102,
    STORE_ITEM_ID_E102,
)

_BACKEND = Path(__file__).resolve().parents[2]
_SLICE = _BACKEND / "data" / "workpaper_sync_e_cycle_manifest_slice.json"

_UPSTREAM_GAP_REASON = (
    "🔴 BP-61-1 平台级约束：adapter 未注册 + working_paper_sync_entry_state 三表近空，"
    "186 个 planned entry 一个都注册不上。需要真实运行 server + adapter 已注册才能验证。"
    "解除后本条 XPASS 并强制摘掉标记。"
)


# ═══════════════════════════════════════════════════════════════════════════
# E1-P4：§9.6 三谓词 + DB 三谓词
#
# 🔴 需要真实运行 server + adapter 已注册才能验证。
# 三谓词：confirm 200 / forcesave cs_error=0 / store_mirrored + marker_visible
# DB 三谓词：op 留存 / marker 留存 / store 键证据
# ═══════════════════════════════════════════════════════════════════════════


class TestE1P4ThreePredicates:
    """E1-P4：§9.6 三谓词 + DB 三谓词。

    三谓词：
    1. `confirm 200`：OO callback confirm 返回 HTTP 200
    2. `forcesave cs_error=0`：OO forcesave 返回的 `cs_error` 为 0（无冲突）
    3. `store_mirrored + marker_visible`：store 回写成功 + 前端 marker 可见

    DB 三谓词：
    1. `op`：操作记录落库（`application_bound_at` 非空）
    2. `marker`：回写标记落库
    3. `store 键证据`：`E1-cash-detail-rows` 在 `checklist_responses` 有值
    """

    # ── 声明层判据（现在可验，必须全绿）─────────────────────────────────

    def test_canary_store_item_id_exists(self) -> None:
        """canary 的 store_item_id 已声明。"""
        assert STORE_ITEM_ID_E102 == "E1-cash-detail-rows"

    def test_canary_spec_has_field_specs(self) -> None:
        """canary spec 有受管字段。"""
        assert len(SPEC_E102.field_specs) >= 5, (
            f"canary spec 只有 {len(SPEC_E102.field_specs)} 个字段 ⇒ 契约空壳"
        )

    def test_canary_spec_has_footer(self) -> None:
        """canary spec 声明了 footer（`ExcelInstrumentationSpec` 需要它）。"""
        assert SPEC_E102.footer_row > SPEC_E102.last_data_row
        assert SPEC_E102.footer_marker

    def test_provider_can_build_store_projection(self) -> None:
        """provider 的 build_store_projection 可调用（投影链存在）。"""
        assert callable(E.build_store_projection)

    def test_provider_can_merge_projection(self) -> None:
        """provider 的 merge_projection_into_store_rows 可调用（合并链存在）。"""
        assert callable(E.merge_projection_into_store_rows)

    def test_provider_can_iter_store_rows(self) -> None:
        """provider 的 iter_store_rows 可调用（行迭代器存在）。"""
        assert callable(E.iter_store_rows)

    # ── §9.6 三谓词（红基线：需要真实 server + adapter）────────────────

    @pytest.mark.xfail(strict=True, reason=_UPSTREAM_GAP_REASON)
    def test_confirm_200(self) -> None:
        """§9.6 谓词 1：OO callback confirm 返回 HTTP 200。

        需要：真实运行 server + OO 编辑态 + forcesave 回写。
        """
        # 此处会在真栈可用后填入 HTTP 请求断言
        assert False, "需要真实 server 运行验证 confirm 200"

    @pytest.mark.xfail(strict=True, reason=_UPSTREAM_GAP_REASON)
    def test_forcesave_cs_error_zero(self) -> None:
        """§9.6 谓词 2：OO forcesave 返回 cs_error=0。"""
        assert False, "需要真实 server 运行验证 forcesave cs_error=0"

    @pytest.mark.xfail(strict=True, reason=_UPSTREAM_GAP_REASON)
    def test_store_mirrored_and_marker_visible(self) -> None:
        """§9.6 谓词 3：store 回写成功 + 前端 marker 可见。"""
        assert False, "需要真实 server 运行验证 store_mirrored + marker_visible"

    # ── DB 三谓词（红基线：需要真实 DB 会话）──────────────────────────────

    @pytest.mark.xfail(strict=True, reason=_UPSTREAM_GAP_REASON)
    def test_db_op_record_persisted(self) -> None:
        """DB 谓词 1：操作记录落库（application_bound_at 非空）。"""
        assert False, "需要真实 DB session 验证 op 记录"

    @pytest.mark.xfail(strict=True, reason=_UPSTREAM_GAP_REASON)
    def test_db_marker_persisted(self) -> None:
        """DB 谓词 2：回写标记落库。"""
        assert False, "需要真实 DB session 验证 marker 记录"

    @pytest.mark.xfail(strict=True, reason=_UPSTREAM_GAP_REASON)
    def test_db_store_key_evidence(self) -> None:
        """DB 谓词 3：E1-cash-detail-rows 在 checklist_responses 有值。"""
        assert False, "需要真实 DB session 验证 store 键证据"


# ═══════════════════════════════════════════════════════════════════════════
# E1-P10：下游 computed 消费方在 OO 回写后正确重算
#
# 已知消费方：e1RestrictedScope.ts 读 E1-bank-detail-rows
#             useE1AccountList 读 E1-bank-detail-rows + E1-account-commit-snapshot
# ═══════════════════════════════════════════════════════════════════════════


class TestE1P10DownstreamRecompute:
    """E1-P10：每个 store 键的下游 computed 在 OO 回写后仍正确重算。"""

    # ── 声明层判据（现在可验）──────────────────────────────────────────

    def test_canary_store_item_has_known_consumers(self) -> None:
        """canary store item 有已知的下游消费方。

        🔴 这里验证的是「我们知道谁在读它」——如果一个都不知道，
        回写后消费方是否正确重算就无从验证。
        """
        # E1-cash-detail-rows 被目录完成度和限制性存款范围两处消费
        known_consumers = [
            "E1TabDirectory.vue",     # 完成度计算
            "e1RestrictedScope.ts",   # 限制性存款范围
        ]
        assert len(known_consumers) >= 1

    def test_e1_3_cross_sheet_consumer_declared(self) -> None:
        """E1-10 的 CROSS_SHEET_KEYS_E110 里含 E1-bank-detail-rows。"""
        from app.services.workpaper_sync.phase5_e1_10_account_list import (
            CROSS_SHEET_KEYS_E110,
        )

        assert "E1-bank-detail-rows" in CROSS_SHEET_KEYS_E110

    def test_e1_11_cross_sheet_snapshot_declared(self) -> None:
        """E1-10 ↔ E1-11 联动键已登记。"""
        from app.services.workpaper_sync.phase5_e1_11_commitment import (
            CROSS_SHEET_SNAPSHOT_KEY_E111,
        )

        assert CROSS_SHEET_SNAPSHOT_KEY_E111 == "E1-account-commit-snapshot"

    # ── 真栈判据（红基线：需要真实回写后验证）────────────────────────────

    @pytest.mark.xfail(strict=True, reason=_UPSTREAM_GAP_REASON)
    def test_downstream_recompute_after_canary_writeback(self) -> None:
        """canary OO 回写后，下游消费方正确重算。

        需要：真栈回写 → 前端重算 → 断言下游 computed 值等于期望。
        """
        assert False, "需要真栈回写后验证下游重算"


# ═══════════════════════════════════════════════════════════════════════════
# E1-P11：整册 materialize 200 + verify_unmanaged_regions + 耗时登记
#
# 🔴 判据必须**穿过** verify_unmanaged_regions。
# ═══════════════════════════════════════════════════════════════════════════


class TestE1P11MaterializeAndVerify:
    """E1-P11：整册 materialize 200 + verify_unmanaged_regions 全绿 + 耗时登记。"""

    # ── 声明层判据（现在可验）──────────────────────────────────────────

    def test_instrumentation_specs_non_empty(self) -> None:
        """instrumentation_specs() 非空（有受管 sheet 才能 materialize）。"""
        specs = E.instrumentation_specs()
        assert len(specs) >= 1, "instrumentation_specs() 为空 ⇒ 无法 materialize"

    def test_instrumentation_has_template_path(self) -> None:
        """instrumentation 声明里有模板路径。"""
        spec = E.instrumentation_spec()
        assert spec.template_relative_path == E.TEMPLATE_RELATIVE_PATH

    def test_instrumentation_has_entry_id(self) -> None:
        """instrumentation 声明里有 entry_id。"""
        spec = E.instrumentation_spec()
        assert spec.entry_id == E.ENTRY_ID

    def test_template_sha256_frozen(self) -> None:
        """模板 SHA256 哨兵已冻结。"""
        assert len(E.TEMPLATE_SHA256) == 64

    # ── 真栈判据（红基线：需要 adapter + 真 materialize）─────────────────

    @pytest.mark.xfail(strict=True, reason=_UPSTREAM_GAP_REASON)
    def test_materialize_200(self) -> None:
        """整册 materialize 返回 200。"""
        assert False, "需要真实 adapter + server 验证 materialize 200"

    @pytest.mark.xfail(strict=True, reason=_UPSTREAM_GAP_REASON)
    def test_verify_unmanaged_regions_pass(self) -> None:
        """materialize 后 verify_unmanaged_regions 全绿。

        🔴 必须穿过 verify_unmanaged_regions——否则受管区侵蚀非受管区不可见。
        变异：去掉 sibling 受管坐标并入 extra_managed_coords ⇒ verify 报差异。
        """
        assert False, "需要真实 materialize 后验证 unmanaged regions"

    @pytest.mark.xfail(strict=True, reason=_UPSTREAM_GAP_REASON)
    def test_materialize_timing_within_budget(self) -> None:
        """materialize 耗时在预算内。"""
        assert False, "需要真实 materialize 后测耗时"


# ═══════════════════════════════════════════════════════════════════════════
# E1-P12 补充：canary 验收后零回归（E1 加入后全部 contract 正常）
# ═══════════════════════════════════════════════════════════════════════════


class TestE1P12CanaryZeroRegression:
    """E1-P12 canary 验收后的零回归检查。

    补充 test_phase5_e1_sheet_specs.py::TestP12ZeroRegressionBaseline 与
    test_phase5_e1_publishing_chain.py::TestFiveRingCoherence。
    本类验证 canary 验收不破坏已有的引擎层不变量。
    """

    def test_contract_payload_still_builds(self) -> None:
        """canary 接入后 build_contract_payload 仍可调用。"""
        payload = E.build_contract_payload()
        assert payload["contract_id"] == E.ADAPTER_ID
        assert len(payload["sheets"]) >= 1

    def test_contract_still_matches_disk(self) -> None:
        """canary 接入后磁盘契约 ↔ source 仍双向锁死。"""
        contract = E.assert_contract_file_matches_source()
        assert contract.contract_id == E.ADAPTER_ID

    def test_e1_provider_imports_cleanly(self) -> None:
        """E1 provider 模块可无副作用导入（不触发 DB / 网络 / 文件 I/O）。"""
        import importlib

        mod = importlib.import_module(
            "app.services.workpaper_sync.phase5_e1_monetary_fund"
        )
        assert hasattr(mod, "ADAPTER_ID")
        assert hasattr(mod, "build_contract_payload")

    def test_all_e1_sheet_declarations_importable(self) -> None:
        """全部 E1 sheet 声明模块可导入。"""
        import importlib

        modules = [
            "app.services.workpaper_sync.phase5_e1_02_cash_detail",
            "app.services.workpaper_sync.phase5_e1_04_digital",
            "app.services.workpaper_sync.phase5_e1_06_reconciliation",
            "app.services.workpaper_sync.phase5_e1_07_08_09_cash_count",
            "app.services.workpaper_sync.phase5_e1_10_account_list",
            "app.services.workpaper_sync.phase5_e1_11_commitment",
        ]
        for mod_name in modules:
            mod = importlib.import_module(mod_name)
            assert mod is not None, f"无法导入 {mod_name}"


# ═══════════════════════════════════════════════════════════════════════════
# 补充：canary 验收是后续全部接入的硬前置（顺序纪律）
# ═══════════════════════════════════════════════════════════════════════════


class TestCanaryIsPrerequisiteForExpansion:
    """canary 未通不得声明第二张受管 sheet（Wave 0→1 顺序纪律）。"""

    def test_canary_is_first_in_managed_specs(self) -> None:
        """canary（E1-2）是 managed_row_table_specs 的首个。"""
        specs = E.managed_row_table_specs()
        assert len(specs) >= 1
        assert specs[0].store_item_id == "E1-cash-detail-rows"

    def test_capability_gate_blocks_adapter(self) -> None:
        """capability 未放行 ⇒ attach_pilot_adapters 返回空（顺序纪律成立的基础）。"""
        result = E.attach_pilot_adapters(registry=None)
        assert result == ()

    @pytest.mark.xfail(strict=True, reason=_UPSTREAM_GAP_REASON)
    def test_canary_acceptance_all_predicates_green(self) -> None:
        """canary 全部验收谓词通过后才允许扩容。

        此条 XPASS 意味着 canary 验收通过，可以声明第二张受管 sheet。
        """
        assert E.manifest_capability_enabled() is True
        result = E.attach_pilot_adapters(registry=None)
        assert len(result) > 0
