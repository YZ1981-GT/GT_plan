"""成本看板服务 — Round 2 需求 9

纯函数 compute：按项目内 WorkHour.status='approved' 分组 role 乘以 rate 得成本。
burn_rate_per_day = 近 14 天已批准工时 / 14
projected_overrun_date = remaining_hours / burn_rate_per_day（天数后的日期）
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.models.staff_models import ProjectAssignment, StaffMember, WorkHour

logger = logging.getLogger(__name__)

# 默认费率（与 migration 一致），当 system_settings 不可用时回退
DEFAULT_HOURLY_RATES: dict[str, int] = {
    "partner": 3000,
    "manager": 1500,
    "senior": 900,
    "auditor": 500,
    "intern": 200,
}

# StaffMember.title → rate key 映射（Batch 1 Fix 1.9: 增加模糊匹配）
_TITLE_TO_RATE_KEY: dict[str, str] = {
    "合伙人": "partner",
    "签字合伙人": "partner",
    "总监": "manager",
    "高级经理": "manager",
    "经理": "manager",
    "项目经理": "manager",
    "主管会计师": "manager",
    "SM": "manager",
    "高级审计员": "senior",
    "高审": "senior",
    "SA": "senior",
    "审计员": "auditor",
    "助理": "auditor",
    "A1": "auditor",
    "A2": "auditor",
    "实习生": "intern",
    "实习": "intern",
}

# 模糊匹配关键词 → rate key（当精确匹配失败时使用）
_FUZZY_KEYWORDS: list[tuple[str, str]] = [
    ("合伙", "partner"),
    ("总监", "manager"),
    ("经理", "manager"),
    ("高级", "senior"),
    ("审计", "auditor"),
    ("实习", "intern"),
]


async def _get_hourly_rates(db: AsyncSession) -> dict[str, int]:
    """从 system_settings 表读取 hourly_rates 配置，失败回退默认值。"""
    try:
        result = await db.execute(
            sa_text("SELECT value FROM system_settings WHERE key = 'hourly_rates' LIMIT 1")
        )
        row = result.fetchone()
        if row and row[0]:
            rates = json.loads(row[0])
            return {k: int(v) for k, v in rates.items()}
    except Exception as exc:
        logger.warning("[COST] failed to read hourly_rates from system_settings: %s", exc)
    return DEFAULT_HOURLY_RATES.copy()


def _resolve_rate_key(title: str | None, role_level: str | None = None) -> str:
    """将 StaffMember.title 映射到费率 key。

    Batch 3 Fix 1: 优先使用 role_level 枚举字段（如果有效），否则回退 title 匹配。
    Batch 1 Fix 1.9: 精确匹配失败时走模糊关键词匹配，仍失败则 warning + 兜底 auditor。
    """
    # Batch 3 Fix 1: role_level 优先
    if role_level and role_level in DEFAULT_HOURLY_RATES:
        return role_level

    if not title:
        return "auditor"
    # 精确匹配
    if title in _TITLE_TO_RATE_KEY:
        return _TITLE_TO_RATE_KEY[title]
    # 模糊匹配
    title_lower = title.lower()
    for keyword, rate_key in _FUZZY_KEYWORDS:
        if keyword in title_lower:
            return rate_key
    # 兜底 + warning
    logger.warning("[COST] 无法映射职级 '%s' 到费率 key，兜底为 auditor", title)
    return "auditor"


async def compute(
    db: AsyncSession,
    project_id: uuid.UUID,
) -> dict[str, Any]:
    """计算项目成本概览。

    Returns:
        {
            budget_hours: int | None,
            actual_hours: float,
            remaining_hours: float,
            burn_rate_per_day: float,
            projected_overrun_date: str | None,  # ISO date
            contract_amount: float | None,
            cost_by_role: [{role, hours, rate, cost}],
        }
    """
    # 1. 获取项目预算信息
    project_result = await db.execute(
        select(Project.budget_hours, Project.contract_amount).where(
            Project.id == project_id
        )
    )
    project_row = project_result.first()
    if not project_row:
        return {
            "budget_hours": None,
            "actual_hours": 0,
            "remaining_hours": 0,
            "burn_rate_per_day": 0,
            "projected_overrun_date": None,
            "contract_amount": None,
            "cost_by_role": [],
        }

    budget_hours = project_row.budget_hours
    contract_amount = (
        float(project_row.contract_amount)
        if project_row.contract_amount is not None
        else None
    )

    # 2. 获取费率配置
    hourly_rates = await _get_hourly_rates(db)

    # 3. 查询已批准工时，按 staff 分组
    # 联合 StaffMember 获取 title + role_level 以确定 role
    # Batch 3 Fix 1: 同时 select role_level 用于优先匹配
    stmt = (
        select(
            StaffMember.title,
            StaffMember.role_level,
            func.sum(WorkHour.hours).label("total_hours"),
        )
        .join(StaffMember, StaffMember.id == WorkHour.staff_id)
        .where(
            WorkHour.project_id == project_id,
            WorkHour.status == "approved",
            WorkHour.is_deleted == False,  # noqa: E712
        )
        .group_by(StaffMember.title, StaffMember.role_level)
    )
    result = await db.execute(stmt)
    rows = result.all()

    # 4. 按 role 聚合成本
    role_aggregation: dict[str, dict[str, Any]] = {}
    total_hours = Decimal("0")

    for row in rows:
        role_level_val = getattr(row, 'role_level', None)
        rate_key = _resolve_rate_key(row.title, role_level=role_level_val)
        hours = Decimal(str(row.total_hours)) if row.total_hours else Decimal("0")
        total_hours += hours

        if rate_key not in role_aggregation:
            role_aggregation[rate_key] = {
                "role": rate_key,
                "hours": Decimal("0"),
                "rate": hourly_rates.get(rate_key, 500),
                "cost": Decimal("0"),
            }
        role_aggregation[rate_key]["hours"] += hours
        role_aggregation[rate_key]["cost"] += hours * Decimal(
            str(hourly_rates.get(rate_key, 500))
        )

    cost_by_role = [
        {
            "role": v["role"],
            "hours": float(v["hours"]),
            "rate": v["rate"],
            "cost": float(v["cost"]),
        }
        for v in role_aggregation.values()
    ]

    # 5. 计算 burn rate（近 14 天已批准工时 / 14）
    fourteen_days_ago = date.today() - timedelta(days=14)
    burn_stmt = select(func.sum(WorkHour.hours)).where(
        WorkHour.project_id == project_id,
        WorkHour.status == "approved",
        WorkHour.is_deleted == False,  # noqa: E712
        WorkHour.work_date >= fourteen_days_ago,
    )
    burn_result = await db.execute(burn_stmt)
    recent_hours = burn_result.scalar() or Decimal("0")
    burn_rate_per_day = float(Decimal(str(recent_hours)) / Decimal("14"))

    # 6. 计算剩余工时和预计超支日期
    actual_hours_float = float(total_hours)
    remaining_hours = (
        float(budget_hours - total_hours) if budget_hours is not None else 0
    )

    projected_overrun_date: str | None = None
    if budget_hours is not None and burn_rate_per_day > 0 and remaining_hours > 0:
        days_until_overrun = remaining_hours / burn_rate_per_day
        overrun_date = date.today() + timedelta(days=int(days_until_overrun))
        projected_overrun_date = overrun_date.isoformat()
    elif budget_hours is not None and remaining_hours <= 0:
        # 已超支
        projected_overrun_date = date.today().isoformat()

    return {
        "budget_hours": budget_hours,
        "actual_hours": actual_hours_float,
        "remaining_hours": remaining_hours,
        "burn_rate_per_day": burn_rate_per_day,
        "projected_overrun_date": projected_overrun_date,
        "contract_amount": contract_amount,
        "cost_by_role": cost_by_role,
    }
