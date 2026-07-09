"""S 类交易型底稿 — TB 回写 service 层（仅 flush 不 commit）.

职责：
- 将 S4/S5/S6/S8/S9/S10 审定表审定金额回写到 trial_balance.audited_amount
- v2 正数口径：audited_amount 始终存储为正数
- **仅 flush 不 commit**，由上层（router 或调用者）统一 commit
- 支持 auto_data_source resolver 自动取数 + field_overrides 用户覆盖

适用 componentType:
- s4-nonmonetary-exchange（非货币性资产交换）
- s5-debt-restructuring（债务重组）
- s6-fund-occupation（大股东及关联方资金占用）
- a-program-console（S8 租赁 / S9 电子商务 / S10 环境事项）

Requirements: 9.1, 9.2, 9.3, 9.4
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

# S 类交易型支持回写的 componentType
S_TRANSACTION_COMPONENT_TYPES = frozenset({
    "s4-nonmonetary-exchange",
    "s5-debt-restructuring",
    "s6-fund-occupation",
    "a-program-console",  # S8/S9/S10 走 a-program-console，通过 wp_code 区分
})

# 各底稿对应的默认科目编码范围
# S4 取固定资产/无形资产/存货等非货币性资产科目
# S5 取应收/应付/长借/短借等债权债务科目
# S6 取其他应收/预付等关联方资金占用科目
# S8 取使用权资产/租赁负债科目
# S9 取电子商务相关收入/应收科目
# S10 取环境相关负债/费用科目
S_TRANSACTION_ACCOUNT_CODES: dict[str, list[str]] = {
    "s4-nonmonetary-exchange": ["1601", "1701", "1403"],  # 固定资产/无形资产/原材料
    "s5-debt-restructuring": ["1122", "2202", "2501", "2601"],  # 应收/应付/短借/长借
    "s6-fund-occupation": ["1221", "1123"],  # 其他应收/预付
    "S8": ["1901", "2802"],  # 使用权资产/租赁负债
    "S9": ["6001", "1122"],  # 主营收入/应收
    "S10": ["2801", "6601"],  # 预计负债/管理费用（环保）
}


# ═══════════════════════════════════════════════════════════════════════════════
# Service 类
# ═══════════════════════════════════════════════════════════════════════════════


class STransactionTBWritebackService:
    """S 类交易型底稿审定表回写 service.

    核心约束：
    - 仅 flush，不 commit（由上层统一提交）Requirements 9.3
    - audited_amount 存储为 v2 正数口径 Requirements 9.1
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
        wp_code: str | None = None,
    ) -> dict[str, Any]:
        """将审定金额回写到 trial_balance.audited_amount.

        Args:
            project_id: 项目 ID
            year: 审计年度
            account_code: 标准科目编码
            audited_amount: 审定金额（v2 正数口径，前端已转换）
            component_type: 可选，用于验证来源合法性
            wp_code: 可选，底稿编码（区分 a-program-console 中的 S8/S9/S10）

        Returns:
            {"account_code": str, "audited_amount": str, "previous_amount": str|None}

        Raises:
            ValueError: componentType 不合法
            LookupError: 试算表中未找到对应科目
        """
        # 校验 componentType（如果提供了）
        if component_type and component_type not in S_TRANSACTION_COMPONENT_TYPES:
            raise ValueError(
                f"componentType '{component_type}' 不属于 S 类交易型底稿。"
                f"支持: {sorted(S_TRANSACTION_COMPONENT_TYPES)}"
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

        # 仅 flush，不 commit（Requirements 9.3）
        await self.db.flush()

        logger.info(
            "S-transaction TB回写(flush): project=%s year=%s account=%s "
            "amount=%s (prev=%s) component=%s wp_code=%s",
            project_id, year, account_code,
            row.audited_amount, previous_amount, component_type, wp_code,
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
        wp_code: str | None = None,
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
                    wp_code=wp_code,
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
        wp_code: str,
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
            wp_code: S4/S5/S6/S8/S9/S10（用于路由到正确 resolver）
            field_overrides: 前端传入的即时覆盖（优先级最高）

        Returns:
            {"auto_resolved": dict, "overrides_applied": dict, "final": dict}
        """
        from app.services.auto_data_resolvers import resolve_auto_data_source

        # ── Step 1: 调用对应的 resolver ──────────────────────────────────────
        resolver_name = _get_resolver_name(wp_code)
        auto_resolved: dict[str, Any] = {}

        if resolver_name:
            result = await resolve_auto_data_source(
                self.db, project_id, year, resolver_name,
            )
            if result and not result.get("_error"):
                auto_resolved = result

        # ── Step 2: 读取持久化的 field_overrides ─────────────────────────────
        override_svc = FieldOverrideService(self.db)
        scope = f"s_transaction:{wp_code}"
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


def _get_resolver_name(wp_code: str) -> str | None:
    """根据 wp_code 返回对应的 auto_data_source resolver 名称."""
    mapping: dict[str, str] = {
        "S4": "s4_nonmonetary_exchange_data",
        "S5": "s5_debt_restructuring_data",
        "S6": "s6_fund_occupation_data",
        "S8": "s8_lease_data",
        "S9": "s9_ecommerce_data",
        "S10": "s10_environment_data",
    }
    return mapping.get(wp_code.upper())
