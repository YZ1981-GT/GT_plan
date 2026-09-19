# -*- coding: utf-8 -*-
"""B50-3 确定审计范围 — 从试算表预填重要财务报表项目。

GET /api/b50/scope-accounts?project_id=...&year=... —
    返回项目试算表中的重要科目（按报表项目名聚合），并按科目名启发式映射业务循环，
    供 B50-3 认定层次风险矩阵一键导入。解决"空表无从下手"的 scoping 缺口，对齐源模板
    B50-3 从全部财报项目逐行 scoping 的编制逻辑。
"""
from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.b50_risk_reader import cycle_for_account

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/b50", tags=["b50-scope"])


@router.get("/scope-accounts")
async def get_scope_accounts(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """返回试算表重要科目（报表项目级聚合）+ 建议业务循环。

    返回: {"summary": str, "accounts": [{"name", "amount", "cycle"}]}
    - 按 account_name 聚合（同名多子科目合并），金额取审定优先、否则未审
    - 过滤金额为 0 的项目，按金额绝对值降序
    - cycle 由 cycle_for_account 启发式映射（审计师可在矩阵中调整）
    """
    try:
        from app.models.audit_platform_models import TrialBalance
        from app.services.dataset_query import get_active_filter

        tb = TrialBalance.__table__
        active = await get_active_filter(db, tb, project_id, year)
        stmt = sa.select(
            tb.c.account_name,
            tb.c.standard_account_code,
            tb.c.unadjusted_amount,
            tb.c.audited_amount,
        ).where(active)
        rows = (await db.execute(stmt)).fetchall()
    except Exception as e:  # noqa: BLE001
        logger.warning("B50 scope-accounts 查询失败 project=%s year=%s: %s", project_id, year, e)
        return {"summary": "试算表未导入或查询失败", "accounts": []}

    # 按报表项目名聚合金额
    agg: dict[str, dict] = {}
    for r in rows:
        name = (r.account_name or "").strip()
        if not name:
            continue
        amt = r.audited_amount if r.audited_amount is not None else r.unadjusted_amount
        try:
            amt = float(amt or 0)
        except (TypeError, ValueError):
            amt = 0.0
        entry = agg.setdefault(name, {"name": name, "amount": 0.0, "code": r.standard_account_code or ""})
        entry["amount"] += amt

    accounts = []
    for entry in agg.values():
        if abs(entry["amount"]) < 1e-6:
            continue
        accounts.append({
            "name": entry["name"],
            "amount": round(entry["amount"], 2),
            "cycle": cycle_for_account(entry["name"], entry["code"]),
        })
    accounts.sort(key=lambda a: abs(a["amount"]), reverse=True)

    if not accounts:
        return {"summary": "试算表无重要科目（金额均为 0 或未导入）", "accounts": []}
    return {
        "summary": f"试算表共 {len(accounts)} 个重要报表项目",
        "accounts": accounts,
    }
