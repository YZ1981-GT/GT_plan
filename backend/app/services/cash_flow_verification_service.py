"""现金流量表核查服务

提供：现金等价物列示、BS-CF 勾稽核对、主表逆算验证、附表间接法验证。
数据源全部来自 trial_balance + financial_report，无需用户手动录入底层数据。
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance
from app.models.cf_verification_models import CfVerificationResult
from app.models.report_models import FinancialReport

_FORMULAS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cf_verification_formulas.json"
_formulas_cache: dict | None = None


def _load_formulas() -> dict:
    global _formulas_cache
    if _formulas_cache is None:
        with open(_FORMULAS_PATH, "r", encoding="utf-8") as f:
            _formulas_cache = json.load(f)
    return _formulas_cache


class CashFlowVerificationService:
    """现金流量表核查服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.formulas = _load_formulas()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_cash_equivalents(self, project_id: UUID, year: int) -> dict[str, Any]:
        """A5-1-1: 现金及现金等价物列示 + BS 货币资金勾稽"""
        cfg = self.formulas["cash_equivalent_accounts"]
        all_accounts = cfg["cash"] + cfg["bank_deposit"] + cfg["other_monetary"]

        rows = await self._get_tb_balances(project_id, year, all_accounts)

        items = []
        total = Decimal("0")
        for acct, begin, end in rows:
            items.append({"account_code": acct, "begin": begin, "end": end})
            total += end

        # BS 货币资金行
        bs_cash = await self._get_report_amount(project_id, year, "balance_sheet", "BS-002")
        diff = total - (bs_cash or Decimal("0"))

        result = {
            "items": items,
            "total": total,
            "bs_cash": bs_cash,
            "difference": diff,
            "pass": abs(diff) < Decimal("0.01"),
            "restricted_note": cfg.get("restricted_note", ""),
        }

        await self._save_result(project_id, year, "cash_equivalents", None, bs_cash, total, diff, result)
        return result

    async def reconcile_bs_cf(self, project_id: UUID, year: int) -> dict[str, Any]:
        """A5-1-3: BS期末-期初 = CF净增加"""
        cfg = self.formulas["reconciliation"]

        bs_end = await self._get_report_amount(project_id, year, "balance_sheet", "BS-002", period="end")
        bs_begin = await self._get_report_amount(project_id, year, "balance_sheet", "BS-002", period="begin")
        cf_net = await self._get_report_amount(project_id, year, "cash_flow_statement", "CFS-061")
        operating = await self._get_report_amount(project_id, year, "cash_flow_statement", "CFS-033")
        investing = await self._get_report_amount(project_id, year, "cash_flow_statement", "CFS-047")
        financing = await self._get_report_amount(project_id, year, "cash_flow_statement", "CFS-059")
        exchange = await self._get_report_amount(project_id, year, "cash_flow_statement", "CFS-060")

        bs_diff = (bs_end - bs_begin) - cf_net
        activity_sum = operating + investing + financing + exchange
        activity_diff = activity_sum - cf_net

        result = {
            "bs_end": bs_end,
            "bs_begin": bs_begin,
            "cf_net": cf_net,
            "bs_diff": bs_diff,
            "bs_pass": abs(bs_diff) < Decimal("0.01"),
            "operating": operating,
            "investing": investing,
            "financing": financing,
            "exchange": exchange,
            "activity_sum": activity_sum,
            "activity_diff": activity_diff,
            "activity_pass": abs(activity_diff) < Decimal("0.01"),
        }

        await self._save_result(project_id, year, "reconciliation", None, cf_net, bs_end - bs_begin, bs_diff, result)
        return result

    async def verify_main_table(self, project_id: UUID, year: int) -> list[dict[str, Any]]:
        """A5-1-4/5: 主表各项逆算验证"""
        items: list[dict[str, Any]] = []
        for section in ("operating", "investing", "financing"):
            for formula_def in self.formulas.get(section, []):
                row_code = formula_def["row_code"]
                reported = await self._get_report_amount(project_id, year, "cash_flow_statement", row_code)
                calculated = await self._calculate_formula(project_id, year, formula_def)
                diff = reported - calculated if calculated is not None else None

                item = {
                    "section": section,
                    "item": formula_def["item"],
                    "row_code": row_code,
                    "reported": reported,
                    "calculated": calculated,
                    "difference": diff,
                    "pass": diff is not None and abs(diff) < Decimal("0.01"),
                    "has_vat_tolerance": formula_def.get("has_vat_tolerance", False),
                    "formula_description": formula_def.get("formula_description", ""),
                }
                items.append(item)

                await self._save_result(project_id, year, "main_table", row_code, reported, calculated, diff, item)
        return items

    async def verify_supplementary(self, project_id: UUID, year: int) -> dict[str, Any]:
        """A5-1-附表: 间接法核对（净利润+调整项=经营CF）"""
        supp = self.formulas["supplementary_indirect"]
        adjustment_items: list[dict[str, Any]] = []
        total = Decimal("0")

        for item_def in supp["items"]:
            value = await self._get_supplementary_value(project_id, year, item_def)
            sign = item_def.get("sign", 1)
            signed_value = value * sign if value is not None else Decimal("0")
            total += signed_value
            adjustment_items.append({
                "item": item_def["item"],
                "row_code": item_def["row_code"],
                "value": value,
                "sign": sign,
                "signed_value": signed_value,
            })

        # 主表经营活动净额
        direct_operating = await self._get_report_amount(project_id, year, "cash_flow_statement", "CFS-033")
        diff = total - direct_operating

        result = {
            "items": adjustment_items,
            "indirect_total": total,
            "direct_operating": direct_operating,
            "difference": diff,
            "pass": abs(diff) < Decimal("0.01"),
        }

        await self._save_result(project_id, year, "supplementary", None, direct_operating, total, diff, result)
        return result

    async def get_saved_results(self, project_id: UUID, year: int) -> list[dict[str, Any]]:
        """获取已缓存的核查结果"""
        stmt = sa.select(CfVerificationResult).where(
            CfVerificationResult.project_id == project_id,
            CfVerificationResult.year == year,
        )
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "check_type": r.check_type,
                "item_code": r.item_code,
                "reported_amount": r.reported_amount,
                "calculated_amount": r.calculated_amount,
                "difference": r.difference,
                "pass": r.pass_,
                "explanation": r.explanation,
                "calculated_at": r.calculated_at.isoformat() if r.calculated_at else None,
            }
            for r in rows
        ]

    async def save_explanation(self, project_id: UUID, year: int, check_type: str, item_code: str | None, explanation: str) -> bool:
        """保存用户差异说明"""
        stmt = sa.select(CfVerificationResult).where(
            CfVerificationResult.project_id == project_id,
            CfVerificationResult.year == year,
            CfVerificationResult.check_type == check_type,
            CfVerificationResult.item_code == item_code if item_code else CfVerificationResult.item_code.is_(None),
        )
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        if row:
            row.explanation = explanation
            await self.db.flush()
            return True
        return False

    async def create_cf_adjustment_from_diff(
        self, project_id: UUID, year: int, item_code: str, difference: Decimal, description: str = ""
    ) -> dict[str, Any]:
        """从 CF 差异一键创建调整分录"""
        from app.models.audit_platform_models import Adjustment, AdjustmentType
        from datetime import datetime, timezone

        # 查找现有同项的 CF 调整，避免重复
        existing_stmt = sa.select(sa.func.count()).select_from(Adjustment).where(
            Adjustment.project_id == project_id,
            Adjustment.year == year,
            Adjustment.adjustment_type == AdjustmentType.cf,
            Adjustment.summary.ilike(f"%{item_code}%"),
            Adjustment.is_deleted == sa.false(),
        )
        result = await self.db.execute(existing_stmt)
        if (result.scalar() or 0) > 0:
            return {"success": False, "error": f"已存在 {item_code} 的 CF 调整分录"}

        # 生成调整编号
        count_stmt = sa.select(sa.func.count()).select_from(Adjustment).where(
            Adjustment.project_id == project_id,
            Adjustment.year == year,
            Adjustment.adjustment_type == AdjustmentType.cf,
        )
        count_result = await self.db.execute(count_stmt)
        seq = (count_result.scalar() or 0) + 1

        adj = Adjustment(
            project_id=project_id,
            year=year,
            company_code="standalone",
            adjustment_no=f"CF-{seq:03d}",
            adjustment_type=AdjustmentType.cf,
            summary=description or f"CF核查差异调整 {item_code}",
            review_status="pending",
        )
        self.db.add(adj)
        await self.db.flush()
        return {"success": True, "adjustment_no": adj.adjustment_no, "id": str(adj.id)}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_tb_balances(self, project_id: UUID, year: int, accounts: list[str]) -> list[tuple]:
        """获取试算表科目余额"""
        stmt = sa.select(
            TrialBalance.standard_account_code,
            TrialBalance.opening_balance,
            TrialBalance.audited_amount,
        ).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.standard_account_code.in_(accounts),
        )
        result = await self.db.execute(stmt)
        return [(code, Decimal(str(ob or 0)), Decimal(str(amt or 0))) for code, ob, amt in result.all()]

    async def _get_report_amount(
        self, project_id: UUID, year: int, report_type: str, row_code: str, period: str = "end"
    ) -> Decimal:
        """获取报表行金额"""
        col = FinancialReport.current_period_amount
        stmt = sa.select(col).where(
            FinancialReport.project_id == project_id,
            FinancialReport.year == year,
            FinancialReport.row_code == row_code,
        )
        result = await self.db.execute(stmt)
        val = result.scalar_one_or_none()
        return Decimal(str(val or 0))

    async def _calculate_formula(self, project_id: UUID, year: int, formula_def: dict) -> Decimal | None:
        """根据公式定义计算逆算值"""
        if formula_def.get("formula") == "manual_or_zero":
            return None  # 无法逆算的项

        components = formula_def.get("components", {})
        values: dict[str, Decimal] = {}

        for key, comp in components.items():
            if isinstance(comp, str):
                continue  # skip notes
            source = comp.get("source")
            if source == "FR":
                values[key] = await self._get_report_amount(
                    project_id, year, comp.get("report_type", ""), comp.get("row_code", comp.get("row_code_ref", ""))
                )
            elif source == "TB":
                accounts = comp.get("accounts", [])
                period = comp.get("period", "end")
                values[key] = await self._get_tb_component(project_id, year, accounts, period)

        # 简单公式求值
        return self._eval_formula(formula_def["formula"], values)

    async def _get_tb_component(self, project_id: UUID, year: int, accounts: list[str], period: str) -> Decimal:
        """获取 TB 组件值（优先从序时账取发生额，降级用余额变动估算）"""
        if period in ("current_debit", "current_credit"):
            # 优先从 tb_ledger 聚合真实发生额
            ledger_val = await self._get_ledger_turnover(project_id, year, accounts, period)
            if ledger_val is not None:
                return ledger_val
            # 降级：用余额变动估算
            rows = await self._get_tb_balances(project_id, year, accounts)
            total = Decimal("0")
            for _, begin, end in rows:
                total += abs(end - begin)
            return total

        rows = await self._get_tb_balances(project_id, year, accounts)
        total = Decimal("0")
        for _, begin, end in rows:
            if period == "begin":
                total += begin
            elif period == "end":
                total += end
            elif period == "decrease":
                total += begin - end
            elif period == "increase":
                total += end - begin
            else:
                total += end
        return total

    async def _get_ledger_turnover(self, project_id: UUID, year: int, accounts: list[str], period: str) -> Decimal | None:
        """从序时账聚合真实借/贷方发生额"""
        from app.models.audit_platform_models import TbLedger

        col = TbLedger.debit_amount if period == "current_debit" else TbLedger.credit_amount
        stmt = sa.select(sa.func.coalesce(sa.func.sum(col), 0)).where(
            TbLedger.project_id == project_id,
            TbLedger.year == year,
            TbLedger.account_code.in_(accounts),
        )
        try:
            result = await self.db.execute(stmt)
            val = result.scalar()
            if val is not None and val != 0:
                return Decimal(str(val))
        except Exception:
            pass  # tb_ledger 可能无数据，降级
        return None

    async def _get_supplementary_value(self, project_id: UUID, year: int, item_def: dict) -> Decimal:
        """获取附表间接法调整项的值"""
        source = item_def.get("source")
        if source == "manual":
            return Decimal("0")
        if source == "FR":
            row_code_ref = item_def.get("row_code_ref", "")
            report_type = item_def.get("report_type", "income_statement")
            return await self._get_report_amount(project_id, year, report_type, row_code_ref)
        if source == "TB":
            accounts = item_def.get("accounts", [])
            period = item_def.get("period", "end")
            return await self._get_tb_component(project_id, year, accounts, period)
        return Decimal("0")

    def _eval_formula(self, formula: str, values: dict[str, Decimal]) -> Decimal:
        """简单公式求值（基于变量名替换）"""
        # 对公式中的变量名替换为数值
        result = Decimal("0")
        try:
            # 安全求值：只允许加减乘除和括号
            expr = formula
            for key, val in values.items():
                expr = expr.replace(key, str(val))
            # 使用 Python eval 的安全子集
            result = Decimal(str(eval(expr, {"__builtins__": {}}, {})))  # noqa: S307
        except Exception:
            # 公式求值失败时用组件值简单求和
            result = sum(values.values(), Decimal("0"))
        return result

    async def _save_result(
        self,
        project_id: UUID,
        year: int,
        check_type: str,
        item_code: str | None,
        reported: Decimal | None,
        calculated: Decimal | None,
        difference: Decimal | None,
        result_data: dict,
    ) -> None:
        """保存/更新核查结果"""
        from datetime import datetime, timezone

        # Convert Decimal values in result_data to float for JSON serialization
        def _serialize(obj: Any) -> Any:
            if isinstance(obj, Decimal):
                return float(obj)
            if isinstance(obj, list):
                return [_serialize(i) for i in obj]
            if isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            return obj

        serializable_data = _serialize(result_data)

        stmt = sa.select(CfVerificationResult).where(
            CfVerificationResult.project_id == project_id,
            CfVerificationResult.year == year,
            CfVerificationResult.check_type == check_type,
            CfVerificationResult.item_code == item_code if item_code else CfVerificationResult.item_code.is_(None),
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if existing:
            existing.reported_amount = reported
            existing.calculated_amount = calculated
            existing.difference = difference
            existing.pass_ = difference is not None and abs(difference) < Decimal("0.01")
            existing.result_data = serializable_data
            existing.calculated_at = now
            existing.updated_at = now
        else:
            new_row = CfVerificationResult(
                project_id=project_id,
                year=year,
                check_type=check_type,
                item_code=item_code,
                reported_amount=reported,
                calculated_amount=calculated,
                difference=difference,
                pass_=difference is not None and abs(difference) < Decimal("0.01"),
                result_data=serializable_data,
                calculated_at=now,
            )
            self.db.add(new_row)
        await self.db.flush()
