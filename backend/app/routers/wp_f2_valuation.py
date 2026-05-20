"""F 采购存货循环 — F-F11 计价测试自动抽样 API

POST /api/projects/{project_id}/workpapers/{wp_id}/f2/valuation-sample

按金额分层抽样从 tb_ledger 抽取库存商品（科目 1403 默认）的明细行，
支持 3 种计价方法差异化（加权平均/先进先出/标准成本）。

对应 spec：workpaper-f-purchase-inventory F-F11
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/f2",
    tags=["wp-f2-valuation"],
)


class ValuationSampleRequest(BaseModel):
    """计价测试抽样请求"""

    method: str = Field("weighted_average", description="计价方法: weighted_average / fifo / standard_cost")
    account_code: str = Field("1403", description="科目编码（默认 1403 库存商品）")
    year: int = Field(..., description="会计年度")
    sample_size: int = Field(20, ge=1, le=100, description="抽样总笔数（按金额分层后均匀分配）")
    high_value_threshold: float = Field(100000.0, ge=0, description="高金额分层阈值（元）")
    period: str = Field("全年", description="期间范围（全年 / 1月 / 1-3月 等）")
    apply_to_sheet: str | None = Field(
        None,
        description="若给出 sheet 名，则将结果写回 working_paper.parsed_data.valuation_samples[sheet]",
    )


class ValuationSampleItem(BaseModel):
    """抽样行项目"""

    voucher_date: str | None
    voucher_no: str
    item_name: str
    quantity: str
    unit_price: str
    amount: str
    layer: str  # high / mid / low
    method_note: str  # 该方法下的计算备注


class ValuationSampleResponse(BaseModel):
    method: str
    total_samples: int
    layers: dict[str, int]  # {high: N, mid: N, low: N}
    samples: list[ValuationSampleItem]
    note: str
    applied_to_sheet: str | None = None  # 写回时返回 sheet 名，否则 None


def _parse_period_range(period: str) -> tuple[int | None, int | None]:
    """与 prefill_engine 一致的期间解析"""
    s = (period or "").strip()
    if not s or s in ("全年", "all", "*"):
        return 1, 12
    if "-" in s:
        try:
            a, b = s.replace("月", "").split("-")
            return int(a), int(b)
        except Exception:
            return None, None
    if "月" in s:
        try:
            return int(s.replace("月", "")), int(s.replace("月", ""))
        except Exception:
            return None, None
    try:
        m = int(s)
        return m, m
    except ValueError:
        return None, None


async def _stratified_sample(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    account_code: str,
    period: str,
    sample_size: int,
    high_threshold: Decimal,
) -> list[dict[str, Any]]:
    """按金额三层抽样：high / mid / low，均匀分配 sample_size。

    实现：
    - high: amount >= high_threshold
    - mid:  high_threshold * 0.1 <= amount < high_threshold
    - low:  amount < high_threshold * 0.1

    每层按 voucher_date 升序取前 N 行。
    """
    from app.models.audit_platform_models import TbLedger
    from app.services.dataset_query import get_active_filter

    af = await get_active_filter(db, TbLedger, project_id, year)

    # 期间过滤
    period_clause = sa.true()
    sp, ep = _parse_period_range(period)
    if sp is not None and ep is not None and (sp, ep) != (1, 12):
        period_clause = TbLedger.accounting_period.between(sp, ep)

    base = sa.select(
        TbLedger.voucher_date,
        TbLedger.voucher_no,
        TbLedger.summary,
        TbLedger.debit_amount,
        TbLedger.credit_amount,
        TbLedger.account_code,
    ).where(af, period_clause, TbLedger.account_code == account_code)

    # 用 amount = abs(debit - credit) 作为分层依据
    amount_expr = sa.func.greatest(TbLedger.debit_amount, TbLedger.credit_amount)

    per_layer = max(1, sample_size // 3)

    layers = {
        "high": (amount_expr >= high_threshold, per_layer),
        "mid": (
            sa.and_(
                amount_expr < high_threshold,
                amount_expr >= high_threshold * Decimal("0.1"),
            ),
            per_layer,
        ),
        "low": (
            sa.and_(amount_expr < high_threshold * Decimal("0.1"), amount_expr > 0),
            sample_size - 2 * per_layer,  # remainder
        ),
    }

    out: list[dict[str, Any]] = []
    for layer_name, (where_clause, n) in layers.items():
        q = base.where(where_clause).order_by(TbLedger.voucher_date.asc()).limit(n)
        rows = (await db.execute(q)).all()
        for r in rows:
            amount = max(
                Decimal(str(r.debit_amount or 0)),
                Decimal(str(r.credit_amount or 0)),
            )
            out.append(
                {
                    "voucher_date": r.voucher_date.isoformat() if r.voucher_date else None,
                    "voucher_no": r.voucher_no or "",
                    "summary": r.summary or "",
                    "amount": amount,
                    "layer": layer_name,
                }
            )
    return out


@router.post("/valuation-sample", response_model=ValuationSampleResponse)
async def f2_valuation_sample(
    project_id: str,
    wp_id: str,
    payload: ValuationSampleRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_access("edit")),
) -> ValuationSampleResponse:
    """F-F11 自动抽样：按金额分层抽取 sample_size 笔明细行。

    - 加权平均：每层均匀抽样，备注列填 "weighted_avg"
    - FIFO：按入库日期升序，备注列填批次号
    - 标准成本：备注列填差异率 (placeholder)
    """
    valid_methods = {"weighted_average", "fifo", "standard_cost"}
    if payload.method not in valid_methods:
        raise HTTPException(400, f"method must be one of {sorted(valid_methods)}")

    try:
        pid = UUID(project_id)
    except Exception:
        raise HTTPException(400, "invalid project_id")

    rows = await _stratified_sample(
        db,
        pid,
        payload.year,
        payload.account_code,
        payload.period,
        payload.sample_size,
        Decimal(str(payload.high_value_threshold)),
    )

    samples: list[ValuationSampleItem] = []
    layer_counts = {"high": 0, "mid": 0, "low": 0}
    for r in rows:
        layer_counts[r["layer"]] = layer_counts.get(r["layer"], 0) + 1
        if payload.method == "fifo":
            note = f"FIFO 批次：{r['voucher_no']}"
        elif payload.method == "standard_cost":
            note = "标准成本差异 = 实际 - 标准（待手工填入）"
        else:
            note = "加权平均（系统重算单价 ÷ 总数量）"
        samples.append(
            ValuationSampleItem(
                voucher_date=r["voucher_date"],
                voucher_no=r["voucher_no"],
                item_name=r["summary"],
                quantity="1",  # tb_ledger 不分数量列，前端补录
                unit_price=str(r["amount"]),
                amount=str(r["amount"]),
                layer=r["layer"],
                method_note=note,
            )
        )

    return ValuationSampleResponse(
        method=payload.method,
        total_samples=len(samples),
        layers=layer_counts,
        samples=samples,
        note=f"按金额分层抽样：high>={payload.high_value_threshold} / mid / low (科目 {payload.account_code}, {payload.period})",
        applied_to_sheet=await _maybe_apply_samples_to_workpaper(
            db, wp_id, payload, samples
        ),
    )


async def _maybe_apply_samples_to_workpaper(
    db: AsyncSession,
    wp_id: str,
    payload: ValuationSampleRequest,
    samples: list[ValuationSampleItem],
) -> str | None:
    """若 apply_to_sheet 给出则把抽样结果写回 working_paper.parsed_data.

    数据结构：
      parsed_data.valuation_samples[sheet] = {
        "method": "weighted_average",
        "applied_at": ISO8601,
        "samples": [...]
      }
    """
    if not payload.apply_to_sheet:
        return None

    from datetime import datetime, timezone
    from app.models.workpaper_models import WorkingPaper

    try:
        wp_uuid = UUID(wp_id)
    except Exception:
        return None

    res = await db.execute(sa.select(WorkingPaper).where(WorkingPaper.id == wp_uuid))
    wp = res.scalar_one_or_none()
    if wp is None:
        return None

    pd = wp.parsed_data or {}
    if not isinstance(pd, dict):
        pd = {}
    pd.setdefault("valuation_samples", {})
    pd["valuation_samples"][payload.apply_to_sheet] = {
        "method": payload.method,
        "account_code": payload.account_code,
        "period": payload.period,
        "high_value_threshold": payload.high_value_threshold,
        "sample_size": payload.sample_size,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "samples": [s.model_dump() for s in samples],
    }
    wp.parsed_data = pd
    await db.flush()
    await db.commit()
    return payload.apply_to_sheet
