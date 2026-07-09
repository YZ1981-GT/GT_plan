"""S 类计算型专项底稿 — TB 回写 service 层（仅 flush 不 commit）.

职责：
- 将 S3/S15/S20/S21 审定表审定金额回写到 trial_balance.audited_amount
- v2 正数口径：audited_amount 始终存储为正数（资产=借方正/负债权益=贷方正）
- **仅 flush 不 commit**，由上层（router 或调用者）统一 commit
- 支持 auto_data_source resolver 自动取数 + field_overrides 用户覆盖

适用 componentType:
- s3-policy-change（会计政策变更/前期差错/估计变更）
- s15-eps-roe（每股收益/净资产收益率）
- s20-revenue-deduction（营业收入扣除）
- s21-data-asset（数据资产）

Requirements: 7.1, 7.2, 7.4
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance
from app.services.field_override_service import FieldOverrideService

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════════════════

# S 类支持的 componentType
S_ESTIMATE_COMPONENT_TYPES = frozenset({
    "s3-policy-change",
    "s15-eps-roe",
    "s20-revenue-deduction",
    "s21-data-asset",
})

# 各 componentType 对应的默认科目编码范围
# S15 需要取 归母净利润、期末净资产
# S20 需要取 营业收入
# S3 需要取 各类调整涉及的期初/期末余额
# S21 独立（无默认自动取数科目）
S_ACCOUNT_CODES: dict[str, list[str]] = {
    "s15-eps-roe": ["4001", "4101", "4103", "4104"],  # 实收资本/盈余公积/OCI/未分配利润
    "s20-revenue-deduction": ["6001", "6051"],  # 主营+其他业务收入
    "s3-policy-change": [],  # S3 按具体变更项目动态取，不固定
    "s21-data-asset": [],  # 独立计算，无默认取数
}


# ═══════════════════════════════════════════════════════════════════════════════
# Service 类
# ═══════════════════════════════════════════════════════════════════════════════


class SEstimateTBWritebackService:
    """S 类计算型底稿审定表回写 service.

    核心约束：
    - 仅 flush，不 commit（由上层统一提交）
    - audited_amount 存储为 v2 正数口径
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── 主入口：审定金额回写 ────────────────────────────────────────────────

    async def writeback_audited_amount(
        self,
        project_id: UUID,
        year: int,
        account_code: str,
        audited_amount: float,
        *,
        component_type: str | None = None,
    ) -> dict[str, Any]:
        """将审定金额回写到 trial_balance.audited_amount.

        Args:
            project_id: 项目 ID
            year: 审计年度
            account_code: 标准科目编码
            audited_amount: 审定金额（v2 正数口径，前端已转换）
            component_type: 可选，用于验证来源合法性

        Returns:
            {"account_code": str, "audited_amount": str, "previous_amount": str|None}

        Raises:
            ValueError: componentType 不合法
            LookupError: 试算表中未找到对应科目
        """
        # 校验 componentType（如果提供了）
        if component_type and component_type not in S_ESTIMATE_COMPONENT_TYPES:
            raise ValueError(
                f"componentType '{component_type}' 不属于 S 类计算型底稿。"
                f"支持: {sorted(S_ESTIMATE_COMPONENT_TYPES)}"
            )

        # 查找匹配的 trial_balance 行
        stmt = (
            sa.select(TrialBalance)
            .where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code == account_code,
                TrialBalance.is_deleted == sa.false(),
            )
            .limit(1)
        )
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()

        if not row:
            raise LookupError(
                f"试算表中未找到科目 {account_code}（project={project_id}, year={year}），"
                f"请先导入试算表数据"
            )

        # 保存旧值
        previous_amount = str(row.audited_amount) if row.audited_amount is not None else None

        # v2 正数口径：audited_amount 始终为正数（绝对值存储）
        row.audited_amount = Decimal(str(abs(audited_amount)))

        # 仅 flush，不 commit（Requirements 7.4）
        await self.db.flush()

        logger.info(
            "S-estimate TB回写(flush): project=%s year=%s account=%s "
            "amount=%s (prev=%s) component=%s",
            project_id, year, account_code,
            row.audited_amount, previous_amount, component_type,
        )

        return {
            "account_code": account_code,
            "audited_amount": str(row.audited_amount),
            "previous_amount": previous_amount,
        }

    # ─── 批量回写 ────────────────────────────────────────────────────────────

    async def writeback_batch(
        self,
        project_id: UUID,
        year: int,
        rows: list[dict[str, Any]],
        *,
        component_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """批量回写多个科目的审定金额.

        Args:
            rows: [{"account_code": str, "audited_amount": float}, ...]

        Returns:
            结果列表，每项含 account_code/audited_amount/previous_amount/error（如有）
        """
        results = []
        for item in rows:
            account_code = item.get("account_code", "")
            amount = item.get("audited_amount", 0)
            try:
                result = await self.writeback_audited_amount(
                    project_id=project_id,
                    year=year,
                    account_code=account_code,
                    audited_amount=float(amount),
                    component_type=component_type,
                )
                results.append(result)
            except (ValueError, LookupError) as e:
                results.append({
                    "account_code": account_code,
                    "error": str(e),
                })

        return results

    # ─── auto_data_source + field_overrides 取数 ─────────────────────────────

    async def resolve_auto_data(
        self,
        project_id: UUID,
        year: int,
        component_type: str,
        *,
        field_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """通过 auto_data_source resolver 自动取数，用户可 field_overrides 覆盖.

        1. 调用对应的 auto_data_source resolver 获取未审数 + 调整分录
        2. 从 field_override_service 读取用户覆盖值
        3. 合并：field_overrides > resolver 返回值

        Args:
            project_id: 项目 ID
            year: 审计年度
            component_type: s3-policy-change / s15-eps-roe / s20-revenue-deduction / s21-data-asset
            field_overrides: 前端传入的即时覆盖（优先级最高）

        Returns:
            {"auto_resolved": dict, "overrides_applied": dict, "final": dict}
        """
        from app.services.auto_data_resolvers import resolve_auto_data_source

        if component_type not in S_ESTIMATE_COMPONENT_TYPES:
            raise ValueError(f"不支持的 componentType: {component_type}")

        # ── Step 1: 调用对应的 resolver ──────────────────────────────────────
        resolver_name = _get_resolver_name(component_type)
        auto_resolved: dict[str, Any] = {}

        if resolver_name:
            result = await resolve_auto_data_source(
                self.db, project_id, year, resolver_name,
            )
            if result and not result.get("_error"):
                auto_resolved = result

        # ── Step 2: 读取持久化的 field_overrides ─────────────────────────────
        override_svc = FieldOverrideService(self.db)
        scope = f"s_estimate:{component_type}"
        persisted_overrides = await override_svc.get_batch(project_id, year, scope=scope)

        # 将持久化覆盖展平为 {field: value}
        flat_persisted: dict[str, Any] = {}
        for _item_key, fields in persisted_overrides.items():
            flat_persisted.update(fields)

        # ── Step 3: 合并（优先级：即时传入 > 持久化 > resolver） ───────────────
        final = dict(auto_resolved)
        overrides_applied: dict[str, Any] = {}

        # 应用持久化覆盖
        for key, val in flat_persisted.items():
            if val is not None:
                final[key] = val
                overrides_applied[key] = val

        # 应用即时传入覆盖（最高优先级）
        if field_overrides:
            for key, val in field_overrides.items():
                if val is not None:
                    final[key] = val
                    overrides_applied[key] = val

        return {
            "auto_resolved": auto_resolved,
            "overrides_applied": overrides_applied,
            "final": final,
        }

    # ─── 便捷方法：获取未审数 + 调整分录 ─────────────────────────────────────

    async def get_unadjusted_and_adjustments(
        self,
        project_id: UUID,
        year: int,
        account_codes: list[str],
    ) -> dict[str, dict[str, Any]]:
        """读取指定科目的未审数 + AJE/RJE 调整金额.

        Returns:
            {account_code: {"unadjusted": float, "aje_adjustment": float, "audited": float}}
        """
        if not account_codes:
            return {}

        stmt = (
            sa.select(
                TrialBalance.standard_account_code,
                TrialBalance.unadjusted_amount,
                TrialBalance.aje_adjustment,
                TrialBalance.audited_amount,
            )
            .where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code.in_(account_codes),
                TrialBalance.is_deleted == sa.false(),
            )
        )
        result = await self.db.execute(stmt)
        rows = result.fetchall()

        data: dict[str, dict[str, Any]] = {}
        for row in rows:
            data[row.standard_account_code] = {
                "unadjusted": float(row.unadjusted_amount or 0),
                "aje_adjustment": float(row.aje_adjustment or 0),
                "audited": float(row.audited_amount or 0),
            }

        return data


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


def _get_resolver_name(component_type: str) -> str | None:
    """根据 componentType 返回对应的 auto_data_source resolver 名称."""
    mapping = {
        "s15-eps-roe": "eps_data_from_tb",
        "s20-revenue-deduction": "revenue_audited_for_s20",
        "s3-policy-change": "s3_policy_change_data",
        "s21-data-asset": None,  # S21 独立计算，无自动取数
    }
    return mapping.get(component_type)
