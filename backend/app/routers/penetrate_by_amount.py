"""按金额穿透端点 — Round 4 需求 5

GET /api/projects/{project_id}/ledger/penetrate-by-amount
  四策略匹配（exact / tolerance / code+amount / summary_keyword）
  结果超 200 条截断提示
  独立于 /ledger/penetrate（参数体系完全不同）
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_models import TbLedger
from app.models.core import User

logger = logging.getLogger(__name__)

MAX_RESULTS = 200

router = APIRouter(
    prefix="/api/projects/{project_id}/ledger",
    tags=["按金额穿透"],
)


@router.get("/penetrate-by-amount")
async def penetrate_by_amount(
    project_id: UUID,
    year: int = Query(..., description="会计年度"),
    amount: float = Query(..., description="目标金额"),
    tolerance: float = Query(0.01, description="容差，默认 0.01"),
    account_code: Optional[str] = Query(None, description="科目代码过滤"),
    date_from: Optional[date] = Query(None, description="起始日期"),
    date_to: Optional[date] = Query(None, description="截止日期"),
    summary_keyword: Optional[str] = Query(None, description="摘要关键词"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """按金额穿透序时账

    四策略优先级：
    1. exact — 精确金额匹配
    2. tolerance — ±tolerance 金额范围
    3. code+amount — 指定科目 + 金额
    4. summary — 金额 + 摘要关键词模糊匹配
    """
    target = Decimal(str(amount))
    tol = Decimal(str(tolerance))

    # 基础过滤条件
    base_filters = [
        TbLedger.project_id == project_id,
        TbLedger.year == year,
    ]
    if date_from:
        base_filters.append(TbLedger.voucher_date >= date_from)
    if date_to:
        base_filters.append(TbLedger.voucher_date <= date_to)

    # 金额匹配条件（借方或贷方）
    def amount_match(low: Decimal, high: Decimal):
        return or_(
            and_(TbLedger.debit_amount >= low, TbLedger.debit_amount <= high, TbLedger.debit_amount > 0),
            and_(TbLedger.credit_amount >= low, TbLedger.credit_amount <= high, TbLedger.credit_amount > 0),
        )

    matches = []
    seen_ids = set()
    total_count = 0
    truncated = False

    # --- 策略 1: exact ---
    exact_q = select(TbLedger).where(
        *base_filters,
        amount_match(target, target),
    ).limit(MAX_RESULTS + 1)
    result = await db.execute(exact_q)
    exact_items = result.scalars().all()
    exact_serialized = [_serialize_ledger(e) for e in exact_items[:MAX_RESULTS]]
    for e in exact_items[:MAX_RESULTS]:
        seen_ids.add(e.id)
    if exact_serialized:
        matches.append({"strategy": "exact", "items": exact_serialized})
        total_count += len(exact_serialized)

    # --- 策略 2: tolerance (排除 exact 已有的) ---
    if tol > 0 and total_count < MAX_RESULTS:
        remaining = MAX_RESULTS - total_count
        tol_q = select(TbLedger).where(
            *base_filters,
            amount_match(target - tol, target + tol),
        ).limit(remaining + len(seen_ids) + 1)
        result = await db.execute(tol_q)
        tol_items = [r for r in result.scalars().all() if r.id not in seen_ids]
        tol_serialized = [_serialize_ledger(e) for e in tol_items[:remaining]]
        for e in tol_items[:remaining]:
            seen_ids.add(e.id)
        if tol_serialized:
            matches.append({"strategy": "tolerance", "items": tol_serialized})
            total_count += len(tol_serialized)

    # --- 策略 3: code+amount ---
    if account_code and total_count < MAX_RESULTS:
        remaining = MAX_RESULTS - total_count
        code_q = select(TbLedger).where(
            *base_filters,
            TbLedger.account_code == account_code,
            amount_match(target - tol, target + tol),
        ).limit(remaining + len(seen_ids) + 1)
        result = await db.execute(code_q)
        code_items = [r for r in result.scalars().all() if r.id not in seen_ids]
        code_serialized = [_serialize_ledger(e) for e in code_items[:remaining]]
        for e in code_items[:remaining]:
            seen_ids.add(e.id)
        if code_serialized:
            matches.append({"strategy": "code+amount", "items": code_serialized})
            total_count += len(code_serialized)

    # --- 策略 4: summary keyword ---
    if summary_keyword and total_count < MAX_RESULTS:
        remaining = MAX_RESULTS - total_count
        kw_q = select(TbLedger).where(
            *base_filters,
            amount_match(target - tol, target + tol),
            TbLedger.summary.ilike(f"%{summary_keyword}%"),
        ).limit(remaining + len(seen_ids) + 1)
        result = await db.execute(kw_q)
        kw_items = [r for r in result.scalars().all() if r.id not in seen_ids]
        kw_serialized = [_serialize_ledger(e) for e in kw_items[:remaining]]
        for e in kw_items[:remaining]:
            seen_ids.add(e.id)
        if kw_serialized:
            matches.append({"strategy": "summary", "items": kw_serialized})
            total_count += len(kw_serialized)

    # 截断检测
    if total_count >= MAX_RESULTS:
        truncated = True

    # 构建响应
    if not matches:
        return {
            "matches": [],
            "total_count": 0,
            "truncated": False,
            "message": "未找到匹配凭证，可调整容差或科目范围",
            "params": {
                "year": year,
                "amount": amount,
                "tolerance": tolerance,
                "account_code": account_code,
                "date_from": str(date_from) if date_from else None,
                "date_to": str(date_to) if date_to else None,
                "summary_keyword": summary_keyword,
            },
        }

    resp = {
        "matches": matches,
        "total_count": total_count,
        "truncated": truncated,
    }
    if truncated:
        resp["message"] = "结果过多，请增加过滤条件"
    return resp


def _serialize_ledger(entry: TbLedger) -> dict:
    """序列化序时账条目"""
    return {
        "id": str(entry.id),
        "voucher_date": str(entry.voucher_date) if entry.voucher_date else None,
        "voucher_no": entry.voucher_no,
        "account_code": entry.account_code,
        "account_name": entry.account_name,
        "debit_amount": float(entry.debit_amount) if entry.debit_amount else 0,
        "credit_amount": float(entry.credit_amount) if entry.credit_amount else 0,
        "summary": entry.summary,
    }
