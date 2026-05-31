"""合并模块 Phase 2 S3 自动抵销 PBT：自动生成仅 draft + 不触发重算（hypothesis）

`consol_auto_elimination_service.auto_generate_draft_eliminations` 把孤立的 4 类抵销
规则引擎接通，从子公司内部交易/往来自动生成 `EliminationEntry` 草稿。铁律（S3/ADR-CONSOL-203）：

- 自动生成的所有 EliminationEntry 强制 review_status == ReviewStatusEnum.draft（绝不 APPROVED）。
- 本服务只持久化草稿，**不调用任何重算函数**（不 import/call recalculate_trial）。
- 无匹配数据时 calculate_elimination_amount 返回 0 → 不生成该规则的 entry（EH4）。

测试分两层：
1. 纯函数：`_build_child_projects_for_rule` 形状正确；amount==0 → 无 entry（EH4 纯逻辑）。
2. mock-DB 集成：patch get_trades/get_arap_list 返回合成内部交易，AsyncMock db 记录
   db.add(entry) 调用，断言每个 entry review_status==draft（S3）。hypothesis 变化金额，
   amount==0 的规则不生成 entry（EH4）。

Validates: Requirements 4.1, 4.2, 4.3 (Property S3); Error scenario EH4
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from hypothesis import given, settings, strategies as st

from app.models.consolidation_models import ReviewStatusEnum
from app.services.consol_auto_elimination_service import (
    ZERO,
    _RULE_TYPES,
    _build_child_projects_for_rule,
    auto_generate_draft_eliminations,
)

_MODULE = "app.services.consol_auto_elimination_service"

# 金额 strategy：含 0 / 正数（抵销金额业务上非负），Decimal places=2
_amount = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("9999999.99"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)
_positive_amount = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("9999999.99"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


def _fake_trade(*, seller="SUB001", buyer="SUB002", trade_amount=None, unrealized_profit=None):
    """构造 InternalTrade 替身（仅含 _build_child_projects_for_rule 读取的字段）。"""
    return SimpleNamespace(
        seller_company_code=seller,
        buyer_company_code=buyer,
        trade_amount=trade_amount,
        unrealized_profit=unrealized_profit,
    )


def _fake_arap(*, debtor="SUB001", creditor="SUB002", debtor_amount=None, creditor_amount=None):
    """构造 InternalArAp 替身。"""
    return SimpleNamespace(
        debtor_company_code=debtor,
        creditor_company_code=creditor,
        debtor_amount=debtor_amount,
        creditor_amount=creditor_amount,
    )


# ===========================================================================
# 纯函数：_build_child_projects_for_rule 形状
# ===========================================================================


class TestBuildChildProjectsShape:
    """_build_child_projects_for_rule 对 4 类规则返回正确形状。"""

    @given(amt=_positive_amount, other=_positive_amount)
    @settings(max_examples=15)
    def test_internal_ar_uses_min_offset(self, amt, other):
        """internal_ar：每对取 min(debtor, creditor) 作为可抵销 internal_balance。"""
        arap = [_fake_arap(debtor_amount=amt, creditor_amount=other)]
        result = _build_child_projects_for_rule("internal_ar", [], arap)
        offset = min(amt, other)
        if offset > ZERO:
            assert result == [{"internal_balance": offset}]
        else:
            assert result == []

    @given(amt=_positive_amount)
    @settings(max_examples=10)
    def test_internal_revenue_uses_trade_amount(self, amt):
        """internal_revenue：取 trade_amount 作为 internal_balance。"""
        trades = [_fake_trade(trade_amount=amt)]
        result = _build_child_projects_for_rule("internal_revenue", trades, [])
        assert result == [{"internal_balance": amt}]

    @given(amt=_positive_amount)
    @settings(max_examples=10)
    def test_internal_inventory_uses_unrealized_profit(self, amt):
        """internal_inventory_unrealized：取 unrealized_profit。"""
        trades = [_fake_trade(unrealized_profit=amt)]
        result = _build_child_projects_for_rule("internal_inventory_unrealized", trades, [])
        assert result == [{"unrealized_profit": amt}]

    def test_internal_dividend_returns_empty(self):
        """internal_dividend：无数据源，返回空 → 引擎算 0（EH4）。"""
        assert _build_child_projects_for_rule("internal_dividend", [], []) == []

    def test_zero_amount_trades_filtered(self):
        """金额为 0/None 的交易被过滤（不构造入参）。"""
        trades = [
            _fake_trade(trade_amount=ZERO),
            _fake_trade(trade_amount=None),
        ]
        assert _build_child_projects_for_rule("internal_revenue", trades, []) == []


# ===========================================================================
# mock-DB 集成：S3 所有 entry 均 draft + 不触发重算
# ===========================================================================


class _RecordingDB:
    """记录 db.add(entry) 调用的 AsyncMock db 替身。"""

    def __init__(self):
        self.added: list = []
        self.commit = AsyncMock(return_value=None)
        self.refresh = AsyncMock(return_value=None)

    def add(self, entry):
        self.added.append(entry)


class TestS3AutoEliminationDraftOnly:
    """S3：自动生成的所有 EliminationEntry 强制 draft，不触发重算。

    **Validates: Requirements 4.1, 4.2**
    """

    @given(
        ar_debtor=_amount,
        ar_creditor=_amount,
        rev_amt=_amount,
        inv_profit=_amount,
    )
    @settings(max_examples=15)
    @pytest.mark.asyncio
    async def test_all_generated_entries_are_draft(
        self, ar_debtor, ar_creditor, rev_amt, inv_profit
    ):
        """随机金额下，所有生成的 entry review_status 恒为 draft（S3）。"""
        trades = [_fake_trade(trade_amount=rev_amt, unrealized_profit=inv_profit)]
        arap = [_fake_arap(debtor_amount=ar_debtor, creditor_amount=ar_creditor)]

        db = _RecordingDB()
        with patch(f"{_MODULE}.get_trades", new=AsyncMock(return_value=trades)), \
                patch(f"{_MODULE}.get_arap_list", new=AsyncMock(return_value=arap)):
            created = await auto_generate_draft_eliminations(db, uuid4(), 2025)

        # S3 核心：每个生成的 entry 都是 draft
        for entry in created:
            assert entry.review_status == ReviewStatusEnum.draft
        # db.add 的所有 entry 同样是 draft（与返回列表一致）
        for entry in db.added:
            assert entry.review_status == ReviewStatusEnum.draft
        assert db.added == created

    @pytest.mark.asyncio
    async def test_does_not_import_or_call_recalculate_trial(self):
        """服务不 import/call recalculate_trial（S3：自动生成不触发重算）。"""
        import sys

        mod = sys.modules[_MODULE]
        # 模块命名空间中不应有 recalculate_trial 符号（未 import）
        assert not hasattr(mod, "recalculate_trial"), (
            "auto_elimination_service 不应 import recalculate_trial（S3 不触发重算）"
        )

        # 即便生成了草稿，也只调 commit/refresh，绝不触发任何重算
        trades = [_fake_trade(trade_amount=Decimal("1000.00"))]
        db = _RecordingDB()
        with patch(f"{_MODULE}.get_trades", new=AsyncMock(return_value=trades)), \
                patch(f"{_MODULE}.get_arap_list", new=AsyncMock(return_value=[])):
            created = await auto_generate_draft_eliminations(db, uuid4(), 2025)

        assert len(created) >= 1
        db.commit.assert_awaited()

    @given(rev_amt=_amount)
    @settings(max_examples=15)
    @pytest.mark.asyncio
    async def test_zero_amount_rule_generates_no_entry(self, rev_amt):
        """EH4：某规则金额为 0 → 不为该规则生成 entry。

        仅提供 internal_revenue 数据；当 rev_amt==0 时不生成任何 entry，
        其他无数据源规则（ar/inventory/dividend）也都算 0 → 全程无 entry。
        当 rev_amt>0 时恰好生成 1 个 internal_revenue entry。
        """
        trades = [_fake_trade(trade_amount=rev_amt)]
        db = _RecordingDB()
        with patch(f"{_MODULE}.get_trades", new=AsyncMock(return_value=trades)), \
                patch(f"{_MODULE}.get_arap_list", new=AsyncMock(return_value=[])):
            created = await auto_generate_draft_eliminations(db, uuid4(), 2025)

        if rev_amt == ZERO:
            assert created == []
        else:
            # 仅 internal_revenue 有数据 → 恰 1 个 entry
            assert len(created) == 1
            assert created[0].entry_no.startswith("AUTO-internal_revenue")
            assert created[0].review_status == ReviewStatusEnum.draft

    @pytest.mark.asyncio
    async def test_no_data_generates_nothing(self):
        """完全无内部交易/往来 → 不生成任何 entry，不报错（EH4）。"""
        db = _RecordingDB()
        with patch(f"{_MODULE}.get_trades", new=AsyncMock(return_value=[])), \
                patch(f"{_MODULE}.get_arap_list", new=AsyncMock(return_value=[])):
            created = await auto_generate_draft_eliminations(db, uuid4(), 2025)

        assert created == []
        assert db.added == []
        # 无草稿时不应 commit（服务仅在 created 非空时 commit）
        db.commit.assert_not_awaited()


class TestRuleTypesConstant:
    """_RULE_TYPES 常量契约。"""

    def test_four_preset_rule_types(self):
        assert _RULE_TYPES == (
            "internal_ar",
            "internal_revenue",
            "internal_inventory_unrealized",
            "internal_dividend",
        )
