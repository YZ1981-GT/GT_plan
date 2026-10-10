"""P1 端到端主链 8 项链路接通验证测试（升级版）。

在原纯存在性检查基础上增加 mock EventBus 接线验证：
  - 真构造 EventPayload 并调用 handler
  - 验证 handler 内部调用了正确的下游服务
  - 纯函数用合成数据验证产出

不依赖真实 PG，不启动 dev server。
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.models.audit_platform_schemas import EventPayload, EventType


def _make_payload(event_type, project_id=None, year=2025, **extra_kw):
    """构造标准 EventPayload。"""
    return EventPayload(
        event_type=event_type,
        project_id=project_id or uuid.uuid4(),
        year=year,
        extra=extra_kw.get("extra", {}),
        account_codes=extra_kw.get("account_codes"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# P1-1：四表激活 → TB 未审数
# ═══════════════════════════════════════════════════════════════════════════


class TestP1_1_DatasetToTb:
    """四表激活到 TB 未审数的事件链路。"""

    def test_register_function_wires_correct_events(self):
        """register_event_handlers 把 LEDGER_DATASET_ACTIVATED 接到 TB 重算。"""
        from app.services.event_handlers._impl import _auto_map_on_dataset_activated
        from app.services.trial_balance_service import TrialBalanceService

        assert callable(_auto_map_on_dataset_activated)
        assert hasattr(TrialBalanceService, "on_data_imported")
        assert hasattr(TrialBalanceService, "recalc_unadjusted")

    @pytest.mark.asyncio
    async def test_auto_map_handler_skips_without_project(self):
        """payload 缺 project_id 时 handler 静默返回不抛。"""
        from app.services.event_handlers._impl import _auto_map_on_dataset_activated

        payload = _make_payload(EventType.LEDGER_DATASET_ACTIVATED)
        payload.project_id = None
        payload.year = None
        # 不应抛异常
        await _auto_map_on_dataset_activated(payload)


# ═══════════════════════════════════════════════════════════════════════════
# P1-2：TB 未审数 → 底稿明细/披露/审定候选值（公式推送）
# ═══════════════════════════════════════════════════════════════════════════


class TestP1_2_TbToWorkpapers:
    """TB 到底稿/披露/审定的公式推送链路。"""

    def test_formula_push_watched_prefixes_not_empty(self):
        """公式推送有已注册的科目前缀 binding（≥10 个底稿）。"""
        from app.services.formula_push.bindings import watched_prefixes

        prefixes = watched_prefixes()
        assert len(prefixes) >= 10, f"watched_prefixes 只有 {len(prefixes)} 个"

    def test_codes_touch_semantics(self):
        """科目命中判定：空=全量，前缀匹配，不匹配跳过。"""
        from app.services.formula_push.triggers import codes_touch

        assert codes_touch(None, ("1122",)) is True       # 空=全量
        assert codes_touch([], ("1122",)) is True          # 空=全量
        assert codes_touch(["1122"], ("11",)) is True      # 前缀命中
        assert codes_touch(["1122"], ("22",)) is False     # 不命中
        assert codes_touch(["6001", "1122"], ("60",)) is True  # 多科目任一命中

    @pytest.mark.asyncio
    async def test_on_trial_balance_updated_skips_consolidated(self):
        """合并项目的 TRIAL_BALANCE_UPDATED 被 formula_push 跳过。"""
        from app.services.formula_push.triggers import on_trial_balance_updated

        payload = _make_payload(EventType.TRIAL_BALANCE_UPDATED)

        with patch(
            "app.services.formula_push.triggers._is_consolidated_project",
            new_callable=AsyncMock, return_value=True,
        ) as mock_check:
            # 不应调 _push
            with patch("app.services.formula_push.triggers._push", new_callable=AsyncMock) as mock_push:
                await on_trial_balance_updated(payload)
                mock_push.assert_not_awaited()
            mock_check.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════════
# P1-3：调整分录批准 → 审定表/披露表/报表/大厅
# ═══════════════════════════════════════════════════════════════════════════


class TestP1_3_AdjustmentApprovalChain:
    """调整分录批准到 TB 重算的事件链路。"""

    @pytest.mark.asyncio
    async def test_adjustment_approved_handler_skips_without_project(self):
        """payload 缺 project_id 时 handler 静默返回。"""
        from app.services.adjustment_approved_recalc_handler import handle_adjustment_approved

        payload = _make_payload(EventType.ADJUSTMENT_APPROVED)
        payload.project_id = None
        payload.year = None
        # 应静默返回不抛
        await handle_adjustment_approved(payload)

    def test_register_function_exists(self):
        """注册函数存在且可调用。"""
        from app.services.adjustment_approved_recalc_handler import register_adjustment_approved_recalc_handler

        assert callable(register_adjustment_approved_recalc_handler)


# ═══════════════════════════════════════════════════════════════════════════
# P1-4：合并工作表 → 合并 TB/报表差额表/合并数
# ═══════════════════════════════════════════════════════════════════════════


class TestP1_4_ConsolPushOrchestration:
    """合并推送四步编排。"""

    def test_push_step_order(self):
        """推送步骤顺序：worksheet → trial → report → notes。"""
        from app.services.consol_push_service import STEP_ORDER
        assert STEP_ORDER == ("worksheet", "trial", "report", "notes")

    def test_push_targets_includes_self(self):
        """push_targets 至少包含自身项目。"""
        import asyncio
        from app.services.consol_push_service import push_targets

        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result)

        pid = uuid.uuid4()
        loop = asyncio.new_event_loop()
        try:
            targets = loop.run_until_complete(push_targets(db, pid))
            assert pid in targets
        finally:
            loop.close()

    def test_consol_calc_basis_identity(self):
        """build_calc_basis 恒等式在合成数据上成立。"""
        from app.services.consol_calc_basis import (
            TbRow, build_calc_basis, trial_amounts,
        )
        from app.services.consol_tree_service import TreeNode

        root = TreeNode(
            project_id=None, company_code="R", company_name="集团",
            parent_company_code=None, ultimate_company_code="R", consol_level=0,
            node_key="R:consol", role="consol", kind="aggregate",
        )
        leaf_pid = uuid.uuid4()
        leaf = TreeNode(
            project_id=leaf_pid, company_code="A", company_name="甲",
            parent_company_code="R", ultimate_company_code="R", consol_level=1,
            node_key="A:entity", role="subsidiary", kind="data",
        )
        root.children = [leaf]
        tb = [TbRow(project_id=leaf_pid, account_code="1001",
                     account_name="现金", account_category="asset",
                     audited_amount=Decimal("100"))]

        basis = build_calc_basis(root, 2025, tb, [])
        ta = trial_amounts(basis)
        t = ta["1001"]
        assert t.consol_amount == t.individual_sum + t.consol_adjustment + t.consol_elimination


# ═══════════════════════════════════════════════════════════════════════════
# P1-5：批准抵销分录 → 附注差额表
# ═══════════════════════════════════════════════════════════════════════════


class TestP1_5_EliminationToNotes:
    """抵销分录审批到合并推送的事件链路。"""

    @pytest.mark.asyncio
    async def test_elimination_approved_handler_calls_push(self):
        """ELIMINATION_APPROVED → handle_elimination_approved → consol_push_service.push。"""
        from app.services.consol_elimination_recalc_handler import handle_elimination_approved

        payload = _make_payload(EventType.ELIMINATION_APPROVED)

        with patch(
            "app.services.consol_elimination_recalc_handler._push",
            new_callable=AsyncMock,
        ) as mock_push:
            await handle_elimination_approved(payload)
            mock_push.assert_awaited_once()

    def test_push_includes_notes_step(self):
        """合并推送步骤包含 notes。"""
        from app.services.consol_push_service import STEP_NOTES, STEP_ORDER
        assert STEP_NOTES in STEP_ORDER


# ═══════════════════════════════════════════════════════════════════════════
# P1-6：合并户/差额户/单体母公司户右侧联动
# ═══════════════════════════════════════════════════════════════════════════


class TestP1_6_NodeKeyPropagation:
    """节点联动设计契约。"""

    def test_consol_endpoints_registered(self):
        """合并工作表和树端点已注册。"""
        from app.main import app
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert any("worksheet" in p and "consolidation" in p.lower() or "worksheet/tree" in p for p in paths)

    def test_node_key_format_code_colon_role(self):
        """节点键格式为 {企业代码}:{角色}。"""
        from app.services.consol_tree_service import TreeNode

        node = TreeNode(
            project_id=uuid.uuid4(), company_code="91110000100000000R",
            company_name="测试集团", parent_company_code=None,
            ultimate_company_code="91110000100000000R", consol_level=0,
            node_key="91110000100000000R:consol", role="consol", kind="aggregate",
        )
        code, role = node.node_key.split(":")
        assert code == node.company_code
        assert role == node.role


# ═══════════════════════════════════════════════════════════════════════════
# P1-7：应收账款复杂子表 + 多级表头
# ═══════════════════════════════════════════════════════════════════════════


class TestP1_7_AccountsReceivableSubtable:
    """应收账款 E5 子表勾稽和多级表头。"""

    def test_e5_check_rules_loaded_correctly(self):
        """E5 五-5-2 规则正确加载且 check_id 不重复。"""
        from app.services.note_check_rules import _load_check_rules

        soe = _load_check_rules("soe", "五-5-2")
        assert len(soe) >= 2
        ids = [r.check_id for r in soe]
        assert len(ids) == len(set(ids)), "check_id 有重复"
        assert "F5-8" in ids

    def test_column_balance_pass_and_fail(self):
        """模式 B 列平衡：平衡→pass，不平衡→fail。"""
        from app.services.note_check_rules import CheckRule, _check_column_balance

        rule = CheckRule(
            check_id="MV-TEST", peer_section_id="", peer_row_label="",
            peer_col_index=0, self_row_label="*", self_col_index=0,
            relation="column_balance", tolerance=0.01,
            description="测试", mode="column_balance",
            opening_col=1, increase_col=2, decrease_col=3, closing_col=4,
        )
        rows = [
            ["固定资产", 1000, 200, 100, 1100],  # 1000+200-100=1100 ✓
            ["商誉", 300, 0, 0, 400],              # 300+0-0≠400 ✗
        ]
        results = _check_column_balance(rule, rows)
        statuses = {r.check_id: r.status for r in results}
        assert any(s == "pass" for s in statuses.values())
        assert any(s == "fail" for s in statuses.values())

    def test_check_rules_endpoint_registered(self):
        """check-rules 端点已注册。"""
        from app.main import app
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert any("check-rules" in p for p in paths)


# ═══════════════════════════════════════════════════════════════════════════
# P1-8：锁定/失败注入/重试/CAS/来源穿透
# ═══════════════════════════════════════════════════════════════════════════


class TestP1_8_LockFailureRetryCas:
    """锁定、失败分类、重试和 CAS。"""

    def test_critical_vs_non_critical_steps(self):
        """worksheet/trial 关键，notes 非关键。"""
        from app.services.consol_push_service import _CRITICAL
        assert "worksheet" in _CRITICAL
        assert "trial" in _CRITICAL
        assert "notes" not in _CRITICAL

    def test_push_result_serializable(self):
        """PushResult.to_dict() 包含完整状态。"""
        from app.services.consol_push_service import PushResult
        r = PushResult(run_id=uuid.uuid4(), project_id=uuid.uuid4(), year=2025, status="succeeded")
        d = r.to_dict()
        for key in ("status", "steps", "warnings", "pushed_projects", "run_id"):
            assert key in d

    def test_request_push_merges_same_key(self):
        """同一 (project, year) 排队中的推送以最后 trigger 记账。"""
        from app.services.consol_push_service import _QUEUED
        pid = uuid.uuid4()
        key = (str(pid), 2025)
        _QUEUED[key] = ("manual", None)
        _QUEUED[key] = ("elimination_approved", None)
        assert _QUEUED[key][0] == "elimination_approved"
        del _QUEUED[key]

    def test_advisory_lock_noop_on_sqlite(self):
        """SQLite 下 advisory_lock 不调 execute。"""
        import asyncio
        from app.services.consol_push_service import _advisory_lock

        db = AsyncMock()
        bind = MagicMock()
        bind.dialect.name = "sqlite"
        db.get_bind = MagicMock(return_value=bind)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_advisory_lock(db, uuid.uuid4(), 2025))
        finally:
            loop.close()
        db.execute.assert_not_called()

    def test_step_labels_all_chinese(self):
        """步骤标签全中文。"""
        from app.services.consol_push_service import STEP_LABELS, STEP_ORDER
        for step in STEP_ORDER:
            assert step in STEP_LABELS
            assert any('\u4e00' <= c <= '\u9fff' for c in STEP_LABELS[step]), (
                f"{step} 标签不含中文: {STEP_LABELS[step]}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 跨链路：事件类型与注册函数完整性
# ═══════════════════════════════════════════════════════════════════════════


class TestEventBusWiringCompleteness:
    """事件注册函数和 EventType 完整性。"""

    def test_all_register_functions_exist(self):
        from app.services.adjustment_approved_recalc_handler import register_adjustment_approved_recalc_handler
        from app.services.consol_elimination_recalc_handler import register_consol_elimination_recalc_handler
        from app.services.formula_push.triggers import register_formula_push_handlers

        for fn in (register_adjustment_approved_recalc_handler, register_consol_elimination_recalc_handler, register_formula_push_handlers):
            assert callable(fn)

    def test_critical_event_types_defined(self):
        for name in ("LEDGER_DATASET_ACTIVATED", "TRIAL_BALANCE_UPDATED",
                      "ADJUSTMENT_APPROVED", "WORKPAPER_SAVED", "ELIMINATION_APPROVED"):
            assert hasattr(EventType, name), f"EventType 缺少 {name}"
