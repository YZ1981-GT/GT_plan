"""G7 长期股权投资(main组) — 业务逻辑服务.

核心职责：
1. TB取数（account_code LIKE '1511%'）
2. 审定数据保存 + 公式验证 + EventBus publish substantive:adjudicated
3. 公式验证 helpers（借方余额/审定数/期末成本/权益法调整/账面价值/借贷平衡）

科目属性：
- 科目代码：1511 长期股权投资
- 方向：借方（资产类）
- 借方科目公式：期末未审 = 期初审定 + 借方发生额 - 贷方发生额
- 控制类型决定计量：子公司→成本法 / 合营联营→权益法

Pattern follows _g6_other_bond_investment_main_service.py / _g8_other_equity_instruments_service.py
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TbBalance, TrialBalance
from app.models.audit_platform_schemas import EventPayload, EventType
from app.services.dataset_query import get_active_filter
from app.services.event_bus import event_bus
from app.services.four_table.g_cycle_specs import G7_SPEC
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

#: 科目定位单一真源 = `four_table/g_cycle_specs.G7_SPEC`（按科目名逐项目解析）。
#: 原写死 ``_ACCOUNT_PREFIX = "1511"`` —— 码本身是对的，但①违反「科目单一真源」铁律
#: （main 策略与 service 层两处各写一份，改一处漏一处）②``code.startswith("1511")``
#: 缺点号边界会误命中 ``15110``（不同科目）且父子双算。
_G7_FALLBACK_PREFIX = "1511"

# EventBus 审定值持久化的独立 item_id
_ADJUDICATED_ITEM_ID = "G7-1-adjudicated-amount"

# 公式验证容差
_TOLERANCE = 0.01


@dataclass
class FormulaError:
    """公式验证错误."""

    row_key: str
    field: str
    message: str
    variance: float


class G7LongTermEquityMainService:
    """G7 长期股权投资(main组) 业务逻辑服务.

    Methods:
        get_trial_balance_data: 科目1511试算表取数
        save_adjudication: 保存审定数据 + EventBus publish
        validate_formulas: 后端公式校验（对齐前端 useG7FormulaEngine）
    """

    TOLERANCE = _TOLERANCE

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    # ─── 纯函数：parseNum ─────────────────────────────────────────────────────

    @staticmethod
    def parse_num(v: object) -> float:
        """安全数值转换：null/undefined/NaN/空字符串/'  '/'abc' → 0."""
        if v is None or v == "":
            return 0.0
        if isinstance(v, (int, float)):
            n = float(v)
            return n if n == n else 0.0  # noqa: PLR0124 — NaN check
        try:
            n = float(str(v).strip())
            return n if n == n else 0.0  # noqa: PLR0124
        except (TypeError, ValueError):
            return 0.0

    # ─── 纯函数：6大公式 ──────────────────────────────────────────────────────

    @staticmethod
    def calc_debit_balance(opening: float, debit: float, credit: float) -> float:
        """借方余额: 期末未审 = 期初审定 + 借方 - 贷方."""
        return float(opening or 0) + float(debit or 0) - float(credit or 0)

    @staticmethod
    def calc_adjusted_amount(unadjusted: float, aje: float, rje: float) -> float:
        """审定数 = 未审数 + AJE + RJE."""
        return float(unadjusted or 0) + float(aje or 0) + float(rje or 0)

    @staticmethod
    def calc_ending_cost(opening: float, increase: float, decrease: float) -> float:
        """期末投资成本 = 期初 + 新增 - 处置."""
        return float(opening or 0) + float(increase or 0) - float(decrease or 0)

    @staticmethod
    def calc_ending_equity_adj(
        opening: float, eq_increase: float, eq_decrease: float
    ) -> float:
        """期末权益法调整 = 期初 + 权益法增加 - 权益法减少."""
        return float(opening or 0) + float(eq_increase or 0) - float(eq_decrease or 0)

    @staticmethod
    def calc_book_value(subtotal: float, impairment: float) -> float:
        """账面价值 = 期末小计 - 减值准备."""
        return float(subtotal or 0) - float(impairment or 0)

    @staticmethod
    def calc_change_rate(prior: float, current: float) -> float | None:
        """变动率 = (current - prior) / prior. prior=0时返回None."""
        if prior == 0:
            return None
        return (float(current or 0) - float(prior or 0)) / abs(float(prior))

    @staticmethod
    def is_debit_credit_balanced(debits: list[float], credits: list[float]) -> bool:
        """借贷平衡: |SUM(debits) - SUM(credits)| < 0.01."""
        d = sum(float(x or 0) for x in debits)
        c = sum(float(x or 0) for x in credits)
        return abs(d - c) < _TOLERANCE

    # ─── 科目定位（语义驱动，逐项目）───────────────────────────────────────────

    async def _resolve_codes(
        self, project_id: UUID, year: int | None = None
    ) -> tuple[list[str], list[str]]:
        """解析本项目「长期股权投资」科目。

        Returns:
            ``(原始码前缀集, 标准码集)``；本项目无该科目时返回 ``([], [])``。
            科目表整体不可用时由解析器降级为兜底码（见 `semantic_account_resolver`）。
        """
        try:
            result = await resolve_semantic_accounts(
                ResolverContext(db=self.db, project_id=project_id, year=year),
                G7_SPEC,
            )
        except Exception as e:  # noqa: BLE001 — fail-open，取数失败不阻断 render
            logger.warning("G7 service: 科目语义定位失败: %s", e)
            return [], []
        slot = result.slots.get("gross")
        if slot is None or not slot.found:
            return [], []
        return list(slot.codes), list(slot.standard_codes)

    # ─── TB 取数（trial_balance 审定相关字段） ─────────────────────────────────

    async def get_trial_balance_data(
        self, project_id: UUID, year: int | None
    ) -> dict[str, Any]:
        """查 trial_balance 里「长期股权投资」的审定相关字段.

        科目由 :meth:`_resolve_codes` 按科目名逐项目解析（原写死 ``LIKE '1511%'``）。

        返回 {
            "rows": [{"standard_account_code", "unadjusted_amount", "aje_adjustment", "audited_amount"}],
            "summary": {"total_unadjusted", "total_aje_adjustment", "total_audited"},
            "balance": {"opening": float, "closing": float}
        }
        """
        assert self.db is not None, "db session required for async operations"
        rows: list[dict] = []
        balance: dict[str, float] = {}
        originals, standard_codes = await self._resolve_codes(project_id, year)

        # 1. 从 trial_balance 取审定相关字段（本项目无该科目则跳过，不退化为宽前缀）
        if standard_codes:
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
                logger.warning("G7 service: trial_balance取数失败: %s", e)

        # 2. 从 tb_balance 取期初/期末余额（叶子口径）
        if not originals:
            return {
                "rows": rows,
                "summary": {
                    "total_unadjusted": sum(r["unadjusted_amount"] for r in rows),
                    "total_aje_adjustment": sum(r["aje_adjustment"] for r in rows),
                    "total_audited": sum(r["audited_amount"] for r in rows),
                },
                "balance": {},
            }
        try:
            active_filter_tb = await get_active_filter(
                self.db, TbBalance.__table__, project_id, year
            )
            result_tb = await self.db.execute(
                sa.select(
                    TbBalance.account_code,
                    TbBalance.account_name,
                    TbBalance.opening_balance,
                    TbBalance.closing_balance,
                    TbBalance.debit_amount,
                    TbBalance.credit_amount,
                    TbBalance.closing_direction,
                    TbBalance.dataset_id,
                ).where(active_filter_tb)
            )
            # 🔴 叶子口径 + 点号边界（共享件）：原 `code.startswith("1511")` 既父子双算
            #    又会误命中 `15110`（不同科目）
            leaves = select_leaves(to_leaf_rows(result_tb.fetchall()))
            picked = filter_by_prefixes(leaves, originals)
            if picked:
                balance = {
                    "opening": sum(r.opening for r in picked),
                    "closing": sum(r.closing for r in picked),
                }
        except Exception as e:  # noqa: BLE001
            logger.warning("G7 service: tb_balance取数失败: %s", e)

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
            "balance": balance,
        }

    # ─── 审定数据保存 + EventBus publish ──────────────────────────────────────

    async def save_adjudication(
        self, wp_id: UUID, data: dict[str, Any]
    ) -> dict[str, Any]:
        """保存G7-1审定表数据到 checklist_responses + 公式验证 + EventBus.

        data 结构:
        {
            "groups": [...],          # 审定表各组数据
            "total_adjudicated": float,
            "by_control_type": {
                "subsidiary": float,
                "joint_venture": float,
                "associate": float,
            },
            "project_id": str,
            "year": int | None,
        }

        Returns: {"success": bool, "errors": list, "item_id": str}
        """
        assert self.db is not None, "db session required for async operations"

        # 1. 公式验证
        errors = self.validate_formulas(data)

        # 2. 持久化到 checklist_responses（不管有无公式错误都保存，错误只做warning）
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
                    "item_id": _ADJUDICATED_ITEM_ID,
                    "conclusion": conclusion_val,
                },
            )
            await self.db.flush()
        except Exception as e:  # noqa: BLE001
            logger.error("G7 service: 审定数据保存失败: %s", e)
            return {"success": False, "errors": [{"field": "save", "message": str(e)}]}

        # 3. EventBus publish substantive:adjudicated
        total_adjudicated = self.parse_num(data.get("total_adjudicated"))
        by_control_type = data.get("by_control_type", {})
        project_id_str = data.get("project_id", "")
        year = data.get("year")

        try:
            project_id = UUID(project_id_str) if project_id_str else wp_id
            # 事件载荷里的科目码也走语义解析（下游联动按科目匹配，写死会串味）
            _orig, _std = await self._resolve_codes(project_id, year)
            event_codes = _orig or [_G7_FALLBACK_PREFIX]
            payload = EventPayload(
                event_type=EventType.WORKPAPER_SAVED,
                project_id=project_id,
                year=year,
                account_codes=event_codes,
                extra={
                    "event_name": "substantive:adjudicated",
                    "account_code": event_codes[0],
                    "adjudicated_amount": total_adjudicated,
                    "by_control_type": {
                        "subsidiary": self.parse_num(by_control_type.get("subsidiary")),
                        "joint_venture": self.parse_num(by_control_type.get("joint_venture")),
                        "associate": self.parse_num(by_control_type.get("associate")),
                    },
                    "wp_id": str(wp_id),
                },
            )
            await event_bus.publish(payload)
        except Exception as e:  # noqa: BLE001
            logger.warning("G7 service: EventBus publish失败: %s", e)

        error_dicts = [
            {"row_key": e.row_key, "field": e.field, "message": e.message, "variance": e.variance}
            for e in errors
        ]
        return {
            "success": True,
            "errors": error_dicts,
            "item_id": _ADJUDICATED_ITEM_ID,
        }

    # ─── 公式验证 ─────────────────────────────────────────────────────────────

    def validate_formulas(self, data: dict[str, Any]) -> list[FormulaError]:
        """后端公式校验（对齐前端 useG7FormulaEngine 8纯函数）.

        验证项：
        1. calcDebitBalance(opening, debit, credit) == opening + debit - credit
        2. calcAdjustedAmount(unadjusted, aje, rje) == unadjusted + aje + rje
        3. calcEndingCost(opening, increase, decrease) == opening + increase - decrease
        4. calcEndingEquityAdj(opening, eqInc, eqDec) == opening + eqInc - eqDec
        5. calcBookValue(subtotal, impairment) == subtotal - impairment
        6. isDebitCreditBalanced(debits, credits): |sum(debits) - sum(credits)| < 0.01

        返回 FormulaError 列表
        """
        errors: list[FormulaError] = []

        # 1. 借方余额验证
        if "debit_balance_check" in data:
            check = data["debit_balance_check"]
            opening = self.parse_num(check.get("opening"))
            debit = self.parse_num(check.get("debit"))
            credit = self.parse_num(check.get("credit"))
            balance = self.parse_num(check.get("balance"))
            expected = self.calc_debit_balance(opening, debit, credit)
            if abs(expected - balance) > _TOLERANCE:
                errors.append(FormulaError(
                    row_key=str(check.get("row_key", "")),
                    field="debit_balance",
                    message=f"借方余额公式不平: 期初({opening})+借方({debit})-贷方({credit})={expected}, 实际={balance}",
                    variance=expected - balance,
                ))

        # 2. 审定数验证（支持批量行）
        if "adjusted_checks" in data:
            for check in data["adjusted_checks"]:
                unadjusted = self.parse_num(check.get("unadjusted"))
                aje = self.parse_num(check.get("aje"))
                rje = self.parse_num(check.get("rje"))
                adjusted = self.parse_num(check.get("adjusted"))
                expected = self.calc_adjusted_amount(unadjusted, aje, rje)
                if abs(expected - adjusted) > _TOLERANCE:
                    errors.append(FormulaError(
                        row_key=str(check.get("row_key", "")),
                        field="adjusted_amount",
                        message=f"审定数公式不平: 未审({unadjusted})+AJE({aje})+RJE({rje})={expected}, 实际={adjusted}",
                        variance=expected - adjusted,
                    ))

        # 3. 期末投资成本验证
        if "ending_cost_checks" in data:
            for check in data["ending_cost_checks"]:
                opening = self.parse_num(check.get("opening"))
                increase = self.parse_num(check.get("increase"))
                decrease = self.parse_num(check.get("decrease"))
                ending = self.parse_num(check.get("ending"))
                expected = self.calc_ending_cost(opening, increase, decrease)
                if abs(expected - ending) > _TOLERANCE:
                    errors.append(FormulaError(
                        row_key=str(check.get("row_key", "")),
                        field="ending_cost",
                        message=f"期末成本公式不平: 期初({opening})+增加({increase})-减少({decrease})={expected}, 实际={ending}",
                        variance=expected - ending,
                    ))

        # 4. 期末权益法调整验证
        if "ending_equity_adj_checks" in data:
            for check in data["ending_equity_adj_checks"]:
                opening = self.parse_num(check.get("opening"))
                eq_increase = self.parse_num(check.get("eq_increase"))
                eq_decrease = self.parse_num(check.get("eq_decrease"))
                ending = self.parse_num(check.get("ending"))
                expected = self.calc_ending_equity_adj(opening, eq_increase, eq_decrease)
                if abs(expected - ending) > _TOLERANCE:
                    errors.append(FormulaError(
                        row_key=str(check.get("row_key", "")),
                        field="ending_equity_adj",
                        message=f"权益法调整公式不平: 期初({opening})+增({eq_increase})-减({eq_decrease})={expected}, 实际={ending}",
                        variance=expected - ending,
                    ))

        # 5. 账面价值验证
        if "book_value_checks" in data:
            for check in data["book_value_checks"]:
                subtotal = self.parse_num(check.get("subtotal"))
                impairment = self.parse_num(check.get("impairment"))
                book_value = self.parse_num(check.get("book_value"))
                expected = self.calc_book_value(subtotal, impairment)
                if abs(expected - book_value) > _TOLERANCE:
                    errors.append(FormulaError(
                        row_key=str(check.get("row_key", "")),
                        field="book_value",
                        message=f"账面价值公式不平: 小计({subtotal})-减值({impairment})={expected}, 实际={book_value}",
                        variance=expected - book_value,
                    ))

        # 6. 借贷平衡验证
        if "debit_credit_balance" in data:
            check = data["debit_credit_balance"]
            debits = [self.parse_num(x) for x in (check.get("debits") or [])]
            credits = [self.parse_num(x) for x in (check.get("credits") or [])]
            if not self.is_debit_credit_balanced(debits, credits):
                total_d = sum(debits)
                total_c = sum(credits)
                errors.append(FormulaError(
                    row_key="adjustment",
                    field="debit_credit_balance",
                    message=f"借贷不平衡: 借方合计({total_d}) ≠ 贷方合计({total_c}), 差额={total_d - total_c}",
                    variance=total_d - total_c,
                ))

        return errors

    # ─── 审定表行级验证 ───────────────────────────────────────────────────────

    def validate_adjudication_rows(self, rows: list[dict]) -> list[FormulaError]:
        """验证G7-1审定表各行公式：期初审定/期末审定/变动额.

        对齐前端公式：
        - openingAdjusted = calcAdjustedAmount(openingUnadjusted, openingAJE, openingRJE)
        - closingAdjusted = calcAdjustedAmount(closingUnadjusted, closingAJE, closingRJE)
        - changeAmount = closingAdjusted - openingAdjusted
        """
        errors: list[FormulaError] = []
        for row in rows:
            key = str(row.get("row_key") or row.get("id") or row.get("item") or "")

            # 期初审定 = 未审 + AJE + RJE
            opening_unadj = self.parse_num(row.get("openingUnadjusted"))
            opening_aje = self.parse_num(row.get("openingAJE"))
            opening_rje = self.parse_num(row.get("openingRJE"))
            opening_adjusted = self.parse_num(row.get("openingAdjusted"))
            opening_expected = self.calc_adjusted_amount(opening_unadj, opening_aje, opening_rje)
            if opening_adjusted and abs(opening_expected - opening_adjusted) > _TOLERANCE:
                errors.append(FormulaError(
                    key, "openingAdjusted", "期初审定数公式不平衡", opening_expected - opening_adjusted
                ))

            # 期末审定 = 未审 + AJE + RJE
            closing_unadj = self.parse_num(row.get("closingUnadjusted"))
            closing_aje = self.parse_num(row.get("closingAJE"))
            closing_rje = self.parse_num(row.get("closingRJE"))
            closing_adjusted = self.parse_num(row.get("closingAdjusted"))
            closing_expected = self.calc_adjusted_amount(closing_unadj, closing_aje, closing_rje)
            if closing_adjusted and abs(closing_expected - closing_adjusted) > _TOLERANCE:
                errors.append(FormulaError(
                    key, "closingAdjusted", "期末审定数公式不平衡", closing_expected - closing_adjusted
                ))

            # 变动额 = 期末审定 - 期初审定
            change_amount = self.parse_num(row.get("changeAmount"))
            expected_change = closing_expected - opening_expected
            if change_amount and abs(expected_change - change_amount) > _TOLERANCE:
                errors.append(FormulaError(
                    key, "changeAmount", "变动额公式不平衡", expected_change - change_amount
                ))

        return errors

    # ─── G7-2 明细表行级验证 ──────────────────────────────────────────────────

    def validate_detail_rows(self, rows: list[dict]) -> list[FormulaError]:
        """验证G7-2明细表各行公式.

        对齐前端公式：
        - closingInvestCost = calcEndingCost(openingInvestCost, increaseNewInvest, decreaseDisposal)
        - closingEquityAdj = calcEndingEquityAdj(openingEquityAdj, increaseEquityMethod, decreaseEquityAdj)
        - closingSubtotal = closingInvestCost + closingEquityAdj
        - closingBookValue = calcBookValue(closingSubtotal, closingImpairment)
        """
        errors: list[FormulaError] = []
        for row in rows:
            key = str(row.get("row_key") or row.get("investeeName") or row.get("id") or "")

            # 期末投资成本
            opening_cost = self.parse_num(row.get("openingInvestCost"))
            increase = self.parse_num(row.get("increaseNewInvest"))
            decrease = self.parse_num(row.get("decreaseDisposal"))
            closing_cost = self.parse_num(row.get("closingInvestCost"))
            expected_cost = self.calc_ending_cost(opening_cost, increase, decrease)
            if closing_cost and abs(expected_cost - closing_cost) > _TOLERANCE:
                errors.append(FormulaError(
                    key, "closingInvestCost", "期末投资成本公式不平衡", expected_cost - closing_cost
                ))

            # 期末权益法调整
            opening_eq = self.parse_num(row.get("openingEquityAdj"))
            eq_increase = self.parse_num(row.get("increaseEquityMethod"))
            eq_decrease = self.parse_num(row.get("decreaseEquityAdj"))
            closing_eq = self.parse_num(row.get("closingEquityAdj"))
            expected_eq = self.calc_ending_equity_adj(opening_eq, eq_increase, eq_decrease)
            if closing_eq and abs(expected_eq - closing_eq) > _TOLERANCE:
                errors.append(FormulaError(
                    key, "closingEquityAdj", "期末权益法调整公式不平衡", expected_eq - closing_eq
                ))

            # 期末小计 = 成本 + 权益法调整
            closing_subtotal = self.parse_num(row.get("closingSubtotal"))
            expected_subtotal = expected_cost + expected_eq
            if closing_subtotal and abs(expected_subtotal - closing_subtotal) > _TOLERANCE:
                errors.append(FormulaError(
                    key, "closingSubtotal", "期末小计公式不平衡", expected_subtotal - closing_subtotal
                ))

            # 账面价值 = 小计 - 减值
            closing_impairment = self.parse_num(row.get("closingImpairment"))
            closing_book = self.parse_num(row.get("closingBookValue"))
            expected_book = self.calc_book_value(expected_subtotal, closing_impairment)
            if closing_book and abs(expected_book - closing_book) > _TOLERANCE:
                errors.append(FormulaError(
                    key, "closingBookValue", "期末账面价值公式不平衡", expected_book - closing_book
                ))

        return errors

    # ─── 调整分录借贷平衡验证 ─────────────────────────────────────────────────

    def validate_adjustment_balance(
        self, debits: list[float], credits: list[float]
    ) -> list[FormulaError]:
        """验证G7-3调整分录借贷平衡."""
        if self.is_debit_credit_balanced(debits, credits):
            return []
        d = sum(float(x or 0) for x in debits)
        c = sum(float(x or 0) for x in credits)
        return [
            FormulaError("adjustment", "balance", "调整分录借贷不平衡", d - c),
        ]
