# -*- coding: utf-8 -*-
"""合伙人轮换检查服务

Refinement Round 1 — 需求 11：关键合伙人轮换检查。

查询 ProjectAssignment 中 staff_id 担任 signing_partner / eqcr 角色
且 Project.client_name 匹配的记录，按年度聚合计算连续年数。

API: GET /api/rotation/check?staff_id=&client_name=
返回: {continuous_years, next_rotation_due_year, current_override_id?}
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select, func, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.models.staff_models import ProjectAssignment
from app.models.rotation_models import PartnerRotationOverride

logger = logging.getLogger(__name__)

# 默认轮换上限（年）
DEFAULT_ROTATION_LIMIT_LISTED = 5  # 上市公司
DEFAULT_ROTATION_LIMIT_UNLISTED = 7  # 非上市


class RotationCheckService:
    """合伙人轮换检查服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_rotation(
        self,
        staff_id: UUID,
        client_name: str,
        is_listed_company: bool = True,
    ) -> dict[str, Any]:
        """检查指定人员对指定客户的连续审计年数。

        查询逻辑：
        1. 从 project_assignments 中找 staff_id 担任 signing_partner/eqcr 的项目
        2. JOIN projects 按 client_name 精确匹配
        3. 按 audit_period_end 的年份聚合，计算连续年数（从当前年份往回数）

        Args:
            staff_id: 人员 ID
            client_name: 客户名称
            is_listed_company: 是否上市公司（默认 True），影响轮换上限

        Returns:
            {
                "staff_id": str,
                "client_name": str,
                "continuous_years": int,
                "years_served": list[int],
                "next_rotation_due_year": int | None,
                "current_override_id": str | None,
                "rotation_limit": int,
            }
        """
        # 查询该人员在该客户的所有签字合伙人/EQCR 委派年份
        stmt = (
            select(
                extract("year", Project.audit_period_end).label("serve_year")
            )
            .select_from(ProjectAssignment)
            .join(Project, ProjectAssignment.project_id == Project.id)
            .where(
                and_(
                    ProjectAssignment.staff_id == staff_id,
                    ProjectAssignment.role.in_(["signing_partner", "eqcr"]),
                    ProjectAssignment.is_deleted == False,  # noqa: E712
                    Project.client_name == client_name,
                    Project.is_deleted == False,  # noqa: E712
                    Project.audit_period_end.isnot(None),
                )
            )
            .distinct()
        )

        result = await self.db.execute(stmt)
        raw_years = sorted(
            [int(row[0]) for row in result.all() if row[0] is not None],
            reverse=True,
        )

        # 计算连续年数（从最近年份往回数）
        continuous_years = self._calc_continuous_years(raw_years)

        # 查询当前有效的 override
        current_override_id = await self._get_active_override(staff_id, client_name)

        # R1 Bug Fix 6: 轮换上限可配置（上市/非上市区分）
        # TODO: read from system_settings.rotation_policy when admin UI is built
        rotation_limit = await self._get_rotation_limit(client_name, is_listed_company)

        # 计算下次轮换到期年份
        next_rotation_due_year = None
        if raw_years and continuous_years > 0:
            latest_year = raw_years[0]
            remaining = rotation_limit - continuous_years
            if remaining > 0:
                next_rotation_due_year = latest_year + remaining
            else:
                # 已超限，当前年即需轮换
                next_rotation_due_year = latest_year

        return {
            "staff_id": str(staff_id),
            "client_name": client_name,
            "continuous_years": continuous_years,
            "years_served": sorted(raw_years),
            "next_rotation_due_year": next_rotation_due_year,
            "current_override_id": str(current_override_id) if current_override_id else None,
            "rotation_limit": rotation_limit,
        }

    async def _get_rotation_limit(
        self, client_name: str, is_listed_company: bool = True
    ) -> int:
        """获取轮换上限年数。

        R1 Bug Fix 6: 轮换上限可配置。
        尝试从 system_settings 表读取（如果存在），否则使用默认值。
        上市公司默认 5 年，非上市公司默认 7 年。

        # TODO: read from system_settings.rotation_policy when admin UI is built
        """
        try:
            from sqlalchemy import text as sa_text

            result = await self.db.execute(
                sa_text(
                    "SELECT value FROM system_settings "
                    "WHERE key = 'rotation_limit_listed' LIMIT 1"
                )
            )
            row = result.scalar_one_or_none()
            if row is not None:
                if is_listed_company:
                    return int(row)
                # 尝试读非上市的配置
                result2 = await self.db.execute(
                    sa_text(
                        "SELECT value FROM system_settings "
                        "WHERE key = 'rotation_limit_unlisted' LIMIT 1"
                    )
                )
                row2 = result2.scalar_one_or_none()
                if row2 is not None:
                    return int(row2)
                return DEFAULT_ROTATION_LIMIT_UNLISTED
        except Exception:
            # system_settings 表不存在或查询失败，使用默认值
            pass

        return DEFAULT_ROTATION_LIMIT_LISTED if is_listed_company else DEFAULT_ROTATION_LIMIT_UNLISTED

    def _calc_continuous_years(self, years_desc: list[int]) -> int:
        """计算从最近年份开始的连续年数。

        例如 [2025, 2024, 2023, 2021] → 连续 3 年（2023-2025）
        """
        if not years_desc:
            return 0

        count = 1
        for i in range(1, len(years_desc)):
            if years_desc[i - 1] - years_desc[i] == 1:
                count += 1
            else:
                break
        return count

    async def _get_active_override(
        self, staff_id: UUID, client_name: str
    ) -> UUID | None:
        """查询当前有效的轮换 override（未过期且双签完成）。"""
        now = datetime.now(timezone.utc)
        stmt = (
            select(PartnerRotationOverride.id)
            .where(
                and_(
                    PartnerRotationOverride.staff_id == staff_id,
                    PartnerRotationOverride.client_name == client_name,
                    PartnerRotationOverride.approved_by_compliance_partner.isnot(None),
                    PartnerRotationOverride.approved_by_chief_risk_partner.isnot(None),
                    # 未过期或无过期时间
                    (
                        (PartnerRotationOverride.override_expires_at.is_(None))
                        | (PartnerRotationOverride.override_expires_at > now)
                    ),
                )
            )
            .order_by(PartnerRotationOverride.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        return row
