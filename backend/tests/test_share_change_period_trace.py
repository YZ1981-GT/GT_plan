"""Tests for share_change_period_service — 期间追溯 + 正式抵销建议。

覆盖：
- 零事件
- 1/2/3/4 事件期间切分
- 排序稳定性
- 净资产注入
- 建议仅 approved 才 is_postable
- 三次事件追溯完整链路

spec: consol-node-key-isolation-and-shared-context 任务 9.4~9.6
设计: §十三.2~§十三.3、P12~P13
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models.share_change_event_models import ShareChangeEvent
from app.services.share_change_period_service import (
    build_period_trace,
    generate_elimination_suggestions,
)

PROJECT_ID = uuid.UUID("30000000-0000-0000-0000-000000000001")


def _event(
    *,
    effective_date: date | None = None,
    sequence: int = 0,
    before_ratio: Decimal | None = None,
    after_ratio: Decimal | None = None,
    review_status: str = "draft",
    source_type: str = "g7-10",
    source_row_id: str = "",
    amount: Decimal | None = None,
    detail: dict | None = None,
) -> ShareChangeEvent:
    """构造最小 ShareChangeEvent 实例（正常构造函数，不走 DB）。"""
    ratio_delta = (after_ratio - before_ratio) if before_ratio is not None and after_ratio is not None else None
    return ShareChangeEvent(
        id=uuid.uuid4(),
        project_id=PROJECT_ID,
        year=2025,
        company_code="A001",
        node_key="A001:subsidiary",
        effective_date=effective_date,
        sequence=sequence,
        before_ratio=before_ratio,
        after_ratio=after_ratio,
        ratio_delta=ratio_delta,
        change_type="购买少数股权",
        amount=amount,
        equity_adjustment=None,
        source_type=source_type,
        source_row_id=source_row_id,
        source_sheet_key="G7-10",
        review_status=review_status,
        calculation_version=0,
        detail=detail,
    )


class TestBuildPeriodTrace:

    def test_zero_events(self):
        trace = build_period_trace([], "A001", 2025)
        assert trace.event_count == 0
        assert trace.segments == []
        assert trace.opening_ratio is None

    def test_one_event(self):
        events = [_event(effective_date=date(2025, 6, 1), before_ratio=Decimal("80"), after_ratio=Decimal("90"))]
        trace = build_period_trace(events, "A001", 2025)

        assert trace.event_count == 1
        assert trace.opening_ratio == Decimal("80")
        assert trace.closing_ratio == Decimal("90")
        assert trace.total_ratio_delta == Decimal("10")
        # 1 事件段 + 1 尾段
        assert len(trace.segments) == 2
        assert trace.segments[0].before_ratio == Decimal("80")
        assert trace.segments[0].after_ratio == Decimal("90")
        assert trace.segments[1].ratio_delta == Decimal("0")  # 尾段

    def test_two_events(self):
        events = [
            _event(effective_date=date(2025, 3, 1), before_ratio=Decimal("80"), after_ratio=Decimal("90")),
            _event(effective_date=date(2025, 9, 1), before_ratio=Decimal("90"), after_ratio=Decimal("70")),
        ]
        trace = build_period_trace(events, "A001", 2025)

        assert trace.event_count == 2
        assert trace.opening_ratio == Decimal("80")
        assert trace.closing_ratio == Decimal("70")
        assert trace.total_ratio_delta == Decimal("-10")
        # 2 事件段 + 1 尾段
        assert len(trace.segments) == 3

    def test_three_events_full_trace(self):
        """P13: 三次事件追溯。"""
        events = [
            _event(effective_date=date(2025, 2, 1), before_ratio=Decimal("80"), after_ratio=Decimal("85"), review_status="approved"),
            _event(effective_date=date(2025, 5, 1), before_ratio=Decimal("85"), after_ratio=Decimal("75"), review_status="approved"),
            _event(effective_date=date(2025, 10, 1), before_ratio=Decimal("75"), after_ratio=Decimal("60"), review_status="draft"),
        ]
        trace = build_period_trace(events, "A001", 2025)

        assert trace.event_count == 3
        assert len(trace.segments) == 4  # 3 事件段 + 1 尾段
        # 首段：期初→事件1
        assert trace.segments[0].period_start == date(2025, 1, 1)
        assert trace.segments[0].period_end == date(2025, 2, 1)
        assert trace.segments[0].suggestion_status == "approved"
        # 第二段：事件1→事件2
        assert trace.segments[1].period_start == date(2025, 2, 1)
        assert trace.segments[1].period_end == date(2025, 5, 1)
        assert trace.segments[1].suggestion_status == "approved"
        # 第三段：事件2→事件3
        assert trace.segments[2].period_start == date(2025, 5, 1)
        assert trace.segments[2].period_end == date(2025, 10, 1)
        assert trace.segments[2].suggestion_status == "draft"
        # 尾段
        assert trace.segments[3].event_id is None

    def test_four_events_not_truncated(self):
        """P12: 4 次事件不被固定三列截断。"""
        events = [
            _event(effective_date=date(2025, 2, 1), before_ratio=Decimal("80"), after_ratio=Decimal("85")),
            _event(effective_date=date(2025, 4, 1), before_ratio=Decimal("85"), after_ratio=Decimal("75")),
            _event(effective_date=date(2025, 7, 1), before_ratio=Decimal("75"), after_ratio=Decimal("65")),
            _event(effective_date=date(2025, 11, 1), before_ratio=Decimal("65"), after_ratio=Decimal("50")),
        ]
        trace = build_period_trace(events, "A001", 2025)

        assert trace.event_count == 4
        assert len(trace.segments) == 5  # 4 事件段 + 1 尾段
        assert trace.closing_ratio == Decimal("50")

    def test_net_assets_injection(self):
        events = [_event(effective_date=date(2025, 6, 1), before_ratio=Decimal("80"), after_ratio=Decimal("90"))]
        net_assets = {"2025-01-01~2025-06-01": Decimal("1000000")}
        trace = build_period_trace(events, "A001", 2025, net_assets_by_period=net_assets)

        seg = trace.segments[0]
        assert seg.net_assets == Decimal("1000000")
        # 资本公积 = 净资产 × 比例变动 / 100
        assert seg.capital_reserve == Decimal("100000")  # 1000000 × 10%

    def test_detail_capital_reserve_override(self):
        """detail 中的资本公积分拆覆盖自动计算值。"""
        events = [_event(
            effective_date=date(2025, 6, 1),
            before_ratio=Decimal("80"), after_ratio=Decimal("90"),
            detail={"adj_capital_reserve": 50000},
        )]
        trace = build_period_trace(events, "A001", 2025, net_assets_by_period={"2025-01-01~2025-06-01": Decimal("1000000")})

        # detail 中的值应覆盖
        assert trace.segments[0].capital_reserve == Decimal("50000")


class TestEliminationSuggestions:

    def test_only_approved_is_postable(self):
        """ADR-CNSC-010: draft 不入账。"""
        events = [
            _event(effective_date=date(2025, 3, 1), before_ratio=Decimal("80"), after_ratio=Decimal("90"), review_status="approved"),
            _event(effective_date=date(2025, 9, 1), before_ratio=Decimal("90"), after_ratio=Decimal("70"), review_status="draft"),
        ]
        trace = build_period_trace(events, "A001", 2025)
        suggestions = generate_elimination_suggestions(trace, project_id=PROJECT_ID, node_key="A001:subsidiary")

        # 2 个事件段产生 2 条建议
        assert len(suggestions) == 2
        assert suggestions[0]["is_postable"] is True
        assert suggestions[0]["review_status"] == "approved"
        assert suggestions[1]["is_postable"] is False
        assert suggestions[1]["review_status"] == "draft"

    def test_suggestion_carries_identity(self):
        events = [_event(effective_date=date(2025, 6, 1), before_ratio=Decimal("80"), after_ratio=Decimal("90"), review_status="approved")]
        trace = build_period_trace(events, "A001", 2025)
        suggestions = generate_elimination_suggestions(trace, project_id=PROJECT_ID, node_key="ROOT:consol")

        assert len(suggestions) == 1
        s = suggestions[0]
        assert s["project_id"] == str(PROJECT_ID)
        assert s["year"] == 2025
        assert s["company_code"] == "A001"
        assert s["node_key"] == "ROOT:consol"
        assert s["event_id"] is not None
        assert s["before_ratio"] == 80.0
        assert s["after_ratio"] == 90.0

    def test_zero_events_no_suggestions(self):
        trace = build_period_trace([], "A001", 2025)
        suggestions = generate_elimination_suggestions(trace, project_id=PROJECT_ID)
        assert suggestions == []

    def test_three_event_trace_suggestions(self):
        """P13: 三次变动的每段均可追溯。"""
        events = [
            _event(effective_date=date(2025, 2, 1), before_ratio=Decimal("80"), after_ratio=Decimal("85"), review_status="approved"),
            _event(effective_date=date(2025, 5, 1), before_ratio=Decimal("85"), after_ratio=Decimal("75"), review_status="approved"),
            _event(effective_date=date(2025, 10, 1), before_ratio=Decimal("75"), after_ratio=Decimal("60"), review_status="approved"),
        ]
        trace = build_period_trace(events, "A001", 2025)
        suggestions = generate_elimination_suggestions(trace, project_id=PROJECT_ID)

        assert len(suggestions) == 3
        for s in suggestions:
            assert s["is_postable"] is True
            assert s["event_id"] is not None
        # 每段比例可追溯
        assert suggestions[0]["before_ratio"] == 80.0
        assert suggestions[0]["after_ratio"] == 85.0
        assert suggestions[1]["before_ratio"] == 85.0
        assert suggestions[1]["after_ratio"] == 75.0
        assert suggestions[2]["before_ratio"] == 75.0
        assert suggestions[2]["after_ratio"] == 60.0
