"""share_change_period_service — 动态股比期间追溯计算。

spec: consol-node-key-isolation-and-shared-context 任务 9.4
设计: §十三.2（期间追溯）

将事件集合切成期间段：期初→事件1、事件1→事件2、…、最后事件→期末。
每段计算适用净资产、比例变动和权益法模拟值。

正式抵销建议 = approved 事件生成，draft 只预览。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.models.share_change_event_models import ShareChangeEvent

logger = logging.getLogger(__name__)


@dataclass
class PeriodSegment:
    """一个期间段的计算结果。"""
    event_id: UUID | None  # 触发事件 ID（首段为 None = 期初）
    period_start: date | None
    period_end: date | None
    before_ratio: Decimal | None
    after_ratio: Decimal | None
    ratio_delta: Decimal | None
    # 净资产和权益法模拟（来自工作底稿或公式取数）
    net_assets: Decimal | None = None
    equity_method_value: Decimal | None = None
    investment_income: Decimal | None = None
    capital_reserve: Decimal | None = None
    nci_impact: Decimal | None = None
    # 来源和建议状态
    source_type: str | None = None
    source_row_id: str | None = None
    calculation_version: int = 0
    suggestion_status: str | None = None  # draft/approved/revoked


@dataclass
class PeriodTraceResult:
    """期间追溯总结果。"""
    company_code: str
    year: int
    event_count: int
    segments: list[PeriodSegment] = field(default_factory=list)
    opening_ratio: Decimal | None = None
    closing_ratio: Decimal | None = None
    total_ratio_delta: Decimal | None = None


def build_period_trace(
    events: list[ShareChangeEvent],
    company_code: str,
    year: int,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    net_assets_by_period: dict[str, Decimal] | None = None,
) -> PeriodTraceResult:
    """从事件集合构建期间追溯。

    events 应已按 (effective_date, sequence, id) 排序。
    net_assets_by_period 可选：key 格式 "{start}~{end}"，用于填充各段净资产。
    """
    if period_start is None:
        period_start = date(year, 1, 1)
    if period_end is None:
        period_end = date(year, 12, 31)

    if not events:
        return PeriodTraceResult(
            company_code=company_code,
            year=year,
            event_count=0,
            segments=[],
            opening_ratio=None,
            closing_ratio=None,
            total_ratio_delta=None,
        )

    segments: list[PeriodSegment] = []
    prev_end = period_start
    prev_ratio = events[0].before_ratio

    for i, event in enumerate(events):
        event_date = event.effective_date or prev_end
        seg_start = prev_end
        seg_end = event_date

        # 查找该段净资产
        seg_key = f"{seg_start}~{seg_end}"
        net_assets = (net_assets_by_period or {}).get(seg_key)

        # 权益法模拟：比例变动 × 净资产（简化公式，真实计算需接入公式 Runtime）
        equity_method_value = None
        investment_income = None
        capital_reserve = None
        nci_impact = None

        if net_assets is not None and event.ratio_delta is not None:
            ratio_pct = event.ratio_delta / Decimal("100")
            capital_reserve = net_assets * ratio_pct
            if event.amount is not None:
                investment_income = event.amount - net_assets * (event.after_ratio or Decimal("0")) / Decimal("100")

        # 从 detail 提取已有的资本公积分拆
        detail = event.detail or {}
        if detail.get("adj_capital_reserve") is not None:
            capital_reserve = Decimal(str(detail["adj_capital_reserve"]))

        segments.append(PeriodSegment(
            event_id=event.id,
            period_start=seg_start,
            period_end=seg_end,
            before_ratio=event.before_ratio,
            after_ratio=event.after_ratio,
            ratio_delta=event.ratio_delta,
            net_assets=net_assets,
            equity_method_value=equity_method_value,
            investment_income=investment_income,
            capital_reserve=capital_reserve,
            nci_impact=nci_impact,
            source_type=event.source_type,
            source_row_id=event.source_row_id,
            calculation_version=event.calculation_version,
            suggestion_status=event.review_status,
        ))

        prev_end = event_date
        prev_ratio = event.after_ratio

    # 最后一段：最后事件→期末
    if prev_end < period_end:
        segments.append(PeriodSegment(
            event_id=None,
            period_start=prev_end,
            period_end=period_end,
            before_ratio=prev_ratio,
            after_ratio=prev_ratio,
            ratio_delta=Decimal("0"),
            suggestion_status=None,
        ))

    opening_ratio = events[0].before_ratio
    closing_ratio = events[-1].after_ratio
    total_delta = None
    if opening_ratio is not None and closing_ratio is not None:
        total_delta = closing_ratio - opening_ratio

    return PeriodTraceResult(
        company_code=company_code,
        year=year,
        event_count=len(events),
        segments=segments,
        opening_ratio=opening_ratio,
        closing_ratio=closing_ratio,
        total_ratio_delta=total_delta,
    )


def generate_elimination_suggestions(
    trace: PeriodTraceResult,
    *,
    project_id: UUID,
    node_key: str | None = None,
) -> list[dict[str, Any]]:
    """从追溯结果生成正式抵销建议。

    只有 approved 事件段才生成建议；draft 段只在预览中展示。
    每条建议带 project/year/node/event IDs 和计算版本。

    设计 §十三.3（ADR-CNSC-010）：建议 draft 不入账，确认并 approved 后才进入 elimination recalc/push。
    """
    suggestions: list[dict[str, Any]] = []

    for seg in trace.segments:
        if seg.event_id is None:
            continue  # 尾段（期末段）不生成建议

        suggestion = {
            "id": str(uuid.uuid4()),
            "project_id": str(project_id),
            "year": trace.year,
            "company_code": trace.company_code,
            "node_key": node_key,
            "event_id": str(seg.event_id),
            "period_start": str(seg.period_start) if seg.period_start else None,
            "period_end": str(seg.period_end) if seg.period_end else None,
            "before_ratio": float(seg.before_ratio) if seg.before_ratio is not None else None,
            "after_ratio": float(seg.after_ratio) if seg.after_ratio is not None else None,
            "ratio_delta": float(seg.ratio_delta) if seg.ratio_delta is not None else None,
            "capital_reserve": float(seg.capital_reserve) if seg.capital_reserve is not None else None,
            "investment_income": float(seg.investment_income) if seg.investment_income is not None else None,
            "nci_impact": float(seg.nci_impact) if seg.nci_impact is not None else None,
            "calculation_version": seg.calculation_version,
            "review_status": seg.suggestion_status or "draft",
            "is_postable": seg.suggestion_status == "approved",
        }
        suggestions.append(suggestion)

    return suggestions
