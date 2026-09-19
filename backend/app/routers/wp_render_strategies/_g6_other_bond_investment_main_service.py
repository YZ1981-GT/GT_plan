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
from app.services.four_table.g_cycle_specs import G6_SPEC
from app.services.four_table.leaf_aggregation import (
    filter_by_prefixes,
    select_leaves,
    to_leaf_rows,
)
from app.services.four_table.semantic_account_resolver import (
    ResolverContext,
    resolve_semantic_accounts,
)

logger = logging.getLogger(__name__)

# 公式验证容差
_TOLERANCE = 0.01


class G6OtherBondInvestmentMainService:
    """G6 其他债权投资(main组) 业务逻辑服务.

    🔴 **2026-08-01 修掉取错科目族**：原 ``_ACCOUNT_PREFIX = "1503"`` 用于
    ``LIKE '1503%'`` 取数，而 ``1503`` 实为「可供出售金融资产」（旧准则，已废止）；
    其他债权投资的科目是 ``1506``（`account_chart` + `trial_balance.account_name` 双证，
    而 `report_config` 的 `BS-022` 写的 ``1505`` 实为「债权投资减值准备」）。

    且不改成写死 ``1506`` —— 标准码在项目间并不一致（详见
    `four_table/semantic_account_resolver` 模块 docstring），一律按科目名逐项目解析。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── 科目定位（语义驱动，逐项目）───────────────────────────────────────────

    async def _resolve_codes(
        self, project_id: UUID, year: int | None = None
    ) -> tuple[list[str], list[str]]:
        """解析本项目「其他债权投资」科目。

        Returns:
            ``(原始码前缀集, 标准码集)``；本项目无该科目时返回 ``([], [])``
            —— 调用方据此返回空结果（**宁缺勿造**，不得退化为宽前缀取错数）。
        """
        try:
            result = await resolve_semantic_accounts(
                ResolverContext(db=self.db, project_id=project_id, year=year),
                G6_SPEC,
            )
        except Exception as e:  # noqa: BLE001 — fail-open，取数失败不阻断 render
            logger.warning("G6 service: 科目语义定位失败: %s", e)
            return [], []
        slot = result.slots.get("gross")
        if slot is None or not slot.found:
            return [], []
        return list(slot.codes), list(slot.standard_codes)

    # ─── TB 取数 ─────────────────────────────────────────────────────────────

    async def get_trial_balance_data(
        self, project_id: UUID, year: int | None
    ) -> dict[str, Any]:
        """查 trial_balance 里「其他债权投资」科目的审定相关字段.

        科目由 :meth:`_resolve_codes` 按科目名逐项目解析（原写死 ``LIKE '1503%'``）。

        返回 {
            "rows": [
                {
                    "standard_account_code": "1506",
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
        _originals, standard_codes = await self._resolve_codes(project_id, year)
        if not standard_codes:
            # 本项目无该科目 → 空结果（不退化为宽前缀，避免把别的科目族算进来）
            return {
                "rows": [],
                "summary": {
                    "total_unadjusted": 0.0,
                    "total_aje_adjustment": 0.0,
                    "total_audited": 0.0,
                },
            }
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
                    TrialBalance.standard_account_code.in_(standard_codes),
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
        """取 tb_balance 里「其他债权投资」的期初/期末余额聚合（**只汇总叶子科目**）.

        🔴 修掉两个缺陷：① 科目族错（原 ``1503`` = 可供出售金融资产）
        ② 原 ``code.startswith(_ACCOUNT_PREFIX)`` **缺点号边界** —— 前缀 ``1506``
        会误命中 ``15060``（不同科目）；且**父子双算**（父科目行与其子科目一起加）。
        现改用共享件 `select_leaves` + `filter_by_prefixes`（与
        `trial_balance_service.recalc` 同语义）。

        返回 {"opening": float, "closing": float}；本项目无该科目或无数据时返回 ``{}``
        （调用方据此区分「无科目」与「余额为 0」）。
        """
        originals, _standard = await self._resolve_codes(project_id, year)
        if not originals:
            return {}
        try:
            active_filter = await get_active_filter(
                self.db, TbBalance.__table__, project_id, year
            )
            result = await self.db.execute(
                sa.select(
                    TbBalance.account_code,
                    TbBalance.account_name,
                    TbBalance.opening_balance,
                    TbBalance.closing_balance,
                    TbBalance.debit_amount,
                    TbBalance.credit_amount,
                    TbBalance.closing_direction,
                    TbBalance.dataset_id,
                ).where(active_filter)
            )
            leaves = select_leaves(to_leaf_rows(result.fetchall()))
            picked = filter_by_prefixes(leaves, originals)
            if picked:
                return {
                    "opening": sum(r.opening for r in picked),
                    "closing": sum(r.closing for r in picked),
                }
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
