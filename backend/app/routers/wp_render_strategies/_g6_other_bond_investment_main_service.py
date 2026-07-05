"""G6 其他债权投资(main组) — 业务逻辑服务.

核心职责：
1. TB取数（account_code LIKE '1503%'）
2. 审定数据保存 + EventBus publish
3. 公式验证 helpers（借方余额/ECL链/借贷平衡）

Pattern follows _g4_bond_investment_main service layer.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.services.dataset_query import get_active_filter

logger = logging.getLogger(__name__)

# 科目前缀：1503 其他债权投资
_ACCOUNT_PREFIX = "1503"

# 公式验证容差
_TOLERANCE = 0.01


class G6OtherBondInvestmentMainService:
    """G6 其他债权投资(main组) 业务逻辑服务."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── TB 取数 ─────────────────────────────────────────────────────────────

    async def get_trial_balance_data(
        self, project_id: UUID, year: int | None
    ) -> dict[str, Any]:
        """查 trial_balance 科目 1503% 的审定相关字段.

        返回 {
            "rows": [
                {
                    "standard_account_code": "1503",
                    "unadjusted_amount": ...,
                    "aje_adjustment": ...,
                    "audited_amount": ...,
                }
            ],
            "summary": {
                "total_unadjusted": ...,
                "total_aje_adjustment": ...,
                "total_audited": ...,
            }
        }
        """
        rows: list[dict] = []
        try:
            active_filter = await get_active_filter(
                self.db, TrialBalance.__table__, project_id, year
            )
            result = await self.db.execute(
                sa.select(
                    TrialBalance.standard_account_code,
                    TrialBalance.unadjusted_amount,
                    TrialBalance.aje_adjustment,
                    TrialBalance.audited_amount,
                ).where(
                    active_filter,
                    TrialBalance.standard_account_code.like(f"{_ACCOUNT_PREFIX}%"),
                )
            )
            for row in result.fetchall():
                rows.append({
                    "standard_account_code": row.standard_account_code or "",
                    "unadjusted_amount": float(row.unadjusted_amount or 0),
                    "aje_adjustment": float(row.aje_adjustment or 0),
                    "audited_amount": float(row.audited_amount or 0),
                })
        except Exception as e:  # noqa: BLE001
            logger.warning("G6 service: TB取数失败: %s", e)

        total_unadjusted = sum(r["unadjusted_amount"] for r in rows)
        total_aje = sum(r["aje_adjustment"] for r in rows)
        total_audited = sum(r["audited_amount"] for r in rows)

        return {
            "rows": rows,
            "summary": {
                "total_unadjusted": total_unadjusted,
                "total_aje_adjustment": total_aje,
                "total_audited": total_audited,
            },
        }

    # ─── TB 期初/期末余额 ────────────────────────────────────────────────────

    async def get_tb_balance_data(
        self, project_id: UUID, year: int | None
    ) -> dict[str, float]:
        """取 tb_balance 1503% 的期初/期末余额聚合.

        返回 {"opening": float, "closing": float}
        """
        try:
            active_filter = await get_active_filter(
                self.db, TbBalance.__table__, project_id, year
            )
            result = await self.db.execute(
                sa.select(
                    TbBalance.account_code,
                    TbBalance.opening_balance,
                    TbBalance.closing_balance,
                ).where(active_filter)
            )
            opening = 0.0
            closing = 0.0
            matched = False
            for row in result.fetchall():
                code = (row.account_code or "").strip()
                if code == _ACCOUNT_PREFIX or code.startswith(_ACCOUNT_PREFIX):
                    opening += float(row.opening_balance or 0)
                    closing += float(row.closing_balance or 0)
                    matched = True
            if matched:
                return {"opening": opening, "closing": closing}
        except Exception as e:  # noqa: BLE001
            logger.warning("G6 service: TB余额取数失败: %s", e)
        return {}

    # ─── 审定数据保存 ─────────────────────────────────────────────────────────

    async def save_adjudication(
        self, wp_id: UUID, data: dict[str, Any]
    ) -> dict[str, Any]:
        """保存G6-1审定表数据到 checklist_responses.

        存储格式：item_id='G6-1-adjudicated-amount', conclusion=审定总额JSON
        """
        item_id = "G6-1-adjudicated-amount"
        import json

        conclusion_val = json.dumps(data, ensure_ascii=False) if data else ""
        try:
            await self.db.execute(
                sa.text("""
                    INSERT INTO checklist_responses (wp_id, item_id, conclusion, remark)
                    VALUES (:wp_id, :item_id, :conclusion, '')
                    ON CONFLICT (wp_id, item_id)
                    DO UPDATE SET conclusion = :conclusion
                """),
                {
                    "wp_id": str(wp_id),
                    "item_id": item_id,
                    "conclusion": conclusion_val,
                },
            )
            await self.db.flush()
            return {"success": True, "item_id": item_id}
        except Exception as e:  # noqa: BLE001
            logger.error("G6 service: 审定数据保存失败: %s", e)
            return {"success": False, "error": str(e)}

    # ─── 公式验证 ─────────────────────────────────────────────────────────────

    @staticmethod
    def validate_formulas(data: dict[str, Any]) -> list[dict[str, str]]:
        """公式验证 helpers.

        验证项：
        1. 借方余额: balance = opening + debit - credit
        2. 审定数: adjusted = unadjusted + adjustment
        3. 小计: subtotal = cost + interestAdj + accruedInterest
        4. ECL链: ⑧=③+⑥ 且 ⑧≈⑦×②A
        5. 借贷平衡: |sum(debits) - sum(credits)| < 0.01

        返回 errors 列表 [{"field": ..., "message": ...}]
        """
        errors: list[dict[str, str]] = []

        # 1. 借方余额验证
        if "debit_balance_check" in data:
            check = data["debit_balance_check"]
            opening = float(check.get("opening", 0) or 0)
            debit = float(check.get("debit", 0) or 0)
            credit = float(check.get("credit", 0) or 0)
            balance = float(check.get("balance", 0) or 0)
            expected = opening + debit - credit
            if abs(expected - balance) > _TOLERANCE:
                errors.append({
                    "field": "debit_balance",
                    "message": f"借方余额公式不平: 期初({opening})+借方({debit})-贷方({credit})={expected}, 实际={balance}",
                })

        # 2. 审定数验证
        if "adjusted_check" in data:
            check = data["adjusted_check"]
            unadjusted = float(check.get("unadjusted", 0) or 0)
            adjustment = float(check.get("adjustment", 0) or 0)
            adjusted = float(check.get("adjusted", 0) or 0)
            expected = unadjusted + adjustment
            if abs(expected - adjusted) > _TOLERANCE:
                errors.append({
                    "field": "adjusted_amount",
                    "message": f"审定数公式不平: 未审({unadjusted})+调整({adjustment})={expected}, 实际={adjusted}",
                })

        # 3. 小计验证
        if "subtotal_check" in data:
            check = data["subtotal_check"]
            cost = float(check.get("cost", 0) or 0)
            interest_adj = float(check.get("interestAdj", 0) or 0)
            accrued_interest = float(check.get("accruedInterest", 0) or 0)
            subtotal = float(check.get("subtotal", 0) or 0)
            expected = cost + interest_adj + accrued_interest
            if abs(expected - subtotal) > _TOLERANCE:
                errors.append({
                    "field": "subtotal",
                    "message": f"小计公式不平: 成本({cost})+利息调整({interest_adj})+应计利息({accrued_interest})={expected}, 实际={subtotal}",
                })

        # 4. ECL链验证: ⑧=③+⑥
        if "ecl_check" in data:
            check = data["ecl_check"]
            provision_3 = float(check.get("provision_3", 0) or 0)
            adjustment_6 = float(check.get("adjustment_6", 0) or 0)
            result_8 = float(check.get("result_8", 0) or 0)
            expected = provision_3 + adjustment_6
            if abs(expected - result_8) > _TOLERANCE:
                errors.append({
                    "field": "ecl_chain",
                    "message": f"ECL公式链不平: ③({provision_3})+⑥({adjustment_6})={expected}, ⑧实际={result_8}",
                })
            # ⑧≈⑦×②A
            balance_7 = float(check.get("balance_7", 0) or 0)
            rate_2a = float(check.get("rate_2a", 0) or 0)
            expected_alt = balance_7 * rate_2a
            if balance_7 != 0 and abs(expected_alt - result_8) > _TOLERANCE:
                errors.append({
                    "field": "ecl_chain_alt",
                    "message": f"ECL交叉验证: ⑦({balance_7})×②A({rate_2a})={expected_alt}, ⑧实际={result_8}",
                })

        # 5. 借贷平衡验证
        if "debit_credit_balance" in data:
            check = data["debit_credit_balance"]
            total_debit = float(check.get("total_debit", 0) or 0)
            total_credit = float(check.get("total_credit", 0) or 0)
            if abs(total_debit - total_credit) > _TOLERANCE:
                errors.append({
                    "field": "debit_credit_balance",
                    "message": f"借贷不平衡: 借方合计({total_debit}) ≠ 贷方合计({total_credit}), 差额={total_debit - total_credit}",
                })

        return errors
