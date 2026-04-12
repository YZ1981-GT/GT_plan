"""现金流量表工作底稿引擎 — 工作底稿法编制现金流量表

核心功能：
- generate_worksheet: 从试算表获取科目期初期末余额，计算变动额
- auto_generate_adjustments: 自动识别折旧/摊销/减值等常见调整项
- CFS 调整分录 CRUD: 创建/修改/删除，借贷平衡校验
- get_reconciliation_status: 计算每个科目的变动额、已分配额、未分配余额
- generate_cfs_main_table: 按 cash_flow_category 和 cash_flow_line_item 汇总
- generate_indirect_method: 间接法补充资料
- verify_reconciliation: 勾稽校验

Validates: Requirements 3.1-3.12
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance, AccountCategory
from app.models.report_models import (
    CashFlowCategory,
    CfsAdjustment,
    FinancialReport,
    FinancialReportType,
)

logger = logging.getLogger(__name__)

# Cash and cash equivalents account codes
CASH_ACCOUNT_CODES = ["1001", "1002", "1012"]

# Auto-adjustment rules: (description, account_code_pattern, account_name_keywords,
#                          cash_flow_category, cash_flow_line_item, is_debit_side)
# is_debit_side: True means the adjustment debits the CFS line item
AUTO_ADJUSTMENT_RULES = [
    {
        "description": "固定资产折旧",
        "account_code": "1602",
        "keywords": ["累计折旧"],
        "category": CashFlowCategory.supplementary,
        "line_item": "固定资产折旧",
        "cf_row_code": "CF-S05",
    },
    {
        "description": "无形资产摊销",
        "account_code": "1702",
        "keywords": ["累计摊销"],
        "category": CashFlowCategory.supplementary,
        "line_item": "无形资产摊销",
        "cf_row_code": "CF-S06",
    },
    {
        "description": "长期待摊费用摊销",
        "account_code": "1801",
        "keywords": ["长期待摊费用"],
        "category": CashFlowCategory.supplementary,
        "line_item": "长期待摊费用摊销",
        "cf_row_code": "CF-S07",
    },
    {
        "description": "投资收益",
        "account_code": "6111",
        "keywords": ["投资收益"],
        "category": CashFlowCategory.supplementary,
        "line_item": "投资损失",
        "cf_row_code": "CF-S09",
    },
    {
        "description": "财务费用",
        "account_code": "6603",
        "keywords": ["财务费用"],
        "category": CashFlowCategory.supplementary,
        "line_item": "财务费用",
        "cf_row_code": "CF-S08",
    },
    {
        "description": "递延所得税资产变动",
        "account_code": "1811",
        "keywords": ["递延所得税资产"],
        "category": CashFlowCategory.supplementary,
        "line_item": "递延所得税资产减少",
        "cf_row_code": "CF-S10",
    },
]


class CFSWorksheetEngine:
    """现金流量表工作底稿引擎"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # 8.1 generate_worksheet
    # ------------------------------------------------------------------
    async def generate_worksheet(
        self,
        project_id: UUID,
        year: int,
    ) -> dict:
        """生成工作底稿：从 trial_balance 获取所有科目期初期末余额，计算变动额。

        Validates: Requirements 3.1, 3.2
        """
        result = await self.db.execute(
            sa.select(TrialBalance)
            .where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.is_deleted == sa.false(),
            )
            .order_by(TrialBalance.standard_account_code)
        )
        tb_rows = result.scalars().all()

        worksheet_rows = []
        for row in tb_rows:
            opening = row.opening_balance or Decimal("0")
            closing = row.audited_amount or Decimal("0")
            period_change = closing - opening
            worksheet_rows.append({
                "account_code": row.standard_account_code,
                "account_name": row.account_name,
                "account_category": row.account_category.value if row.account_category else None,
                "opening_balance": str(opening),
                "closing_balance": str(closing),
                "period_change": str(period_change),
            })

        return {
            "project_id": str(project_id),
            "year": year,
            "rows": worksheet_rows,
        }

    # ------------------------------------------------------------------
    # 8.2 auto_generate_adjustments
    # ------------------------------------------------------------------
    async def auto_generate_adjustments(
        self,
        project_id: UUID,
        year: int,
    ) -> list[dict]:
        """自动识别常见调整项，生成草稿 CFS 调整分录。

        Validates: Requirements 3.8
        """
        # Delete existing auto-generated adjustments first
        await self.db.execute(
            sa.update(CfsAdjustment)
            .where(
                CfsAdjustment.project_id == project_id,
                CfsAdjustment.year == year,
                CfsAdjustment.is_auto_generated == sa.true(),
                CfsAdjustment.is_deleted == sa.false(),
            )
            .values(is_deleted=True)
        )
        await self.db.flush()

        # Get trial balance data
        result = await self.db.execute(
            sa.select(TrialBalance)
            .where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.is_deleted == sa.false(),
            )
        )
        tb_map = {r.standard_account_code: r for r in result.scalars().all()}

        # Get next adjustment number
        count_result = await self.db.execute(
            sa.select(sa.func.count()).select_from(CfsAdjustment).where(
                CfsAdjustment.project_id == project_id,
                CfsAdjustment.year == year,
                CfsAdjustment.is_deleted == sa.false(),
            )
        )
        existing_count = count_result.scalar() or 0
        adj_no = existing_count + 1

        created = []
        for rule in AUTO_ADJUSTMENT_RULES:
            tb_row = tb_map.get(rule["account_code"])
            if tb_row is None:
                continue

            opening = tb_row.opening_balance or Decimal("0")
            closing = tb_row.audited_amount or Decimal("0")
            change = closing - opening

            if change == Decimal("0"):
                continue

            amount = abs(change)
            # For supplementary items, debit is the CFS line, credit is the account
            debit_account = rule["cf_row_code"]
            credit_account = rule["account_code"]

            adjustment = CfsAdjustment(
                project_id=project_id,
                year=year,
                adjustment_no=f"CFS-{adj_no:03d}",
                description=rule["description"],
                debit_account=debit_account,
                credit_account=credit_account,
                amount=amount,
                cash_flow_category=rule["category"],
                cash_flow_line_item=rule["line_item"],
                is_auto_generated=True,
            )
            self.db.add(adjustment)
            adj_no += 1
            created.append({
                "adjustment_no": adjustment.adjustment_no,
                "description": rule["description"],
                "debit_account": debit_account,
                "credit_account": credit_account,
                "amount": str(amount),
                "cash_flow_category": rule["category"].value,
                "cash_flow_line_item": rule["line_item"],
            })

        await self.db.flush()
        return created

    # ------------------------------------------------------------------
    # 8.3 CFS Adjustment CRUD
    # ------------------------------------------------------------------
    async def create_adjustment(
        self,
        project_id: UUID,
        year: int,
        description: str | None,
        debit_account: str,
        credit_account: str,
        amount: Decimal,
        cash_flow_category: CashFlowCategory | None = None,
        cash_flow_line_item: str | None = None,
    ) -> CfsAdjustment:
        """创建 CFS 调整分录，借贷平衡校验。

        Validates: Requirements 3.3, 3.4
        """
        if amount <= Decimal("0"):
            raise ValueError("调整金额必须大于零")

        # Generate adjustment number
        count_result = await self.db.execute(
            sa.select(sa.func.count()).select_from(CfsAdjustment).where(
                CfsAdjustment.project_id == project_id,
                CfsAdjustment.year == year,
                CfsAdjustment.is_deleted == sa.false(),
            )
        )
        existing_count = count_result.scalar() or 0

        adjustment = CfsAdjustment(
            project_id=project_id,
            year=year,
            adjustment_no=f"CFS-{existing_count + 1:03d}",
            description=description,
            debit_account=debit_account,
            credit_account=credit_account,
            amount=amount,
            cash_flow_category=cash_flow_category,
            cash_flow_line_item=cash_flow_line_item,
            is_auto_generated=False,
        )
        self.db.add(adjustment)
        await self.db.flush()
        return adjustment

    async def update_adjustment(
        self,
        adjustment_id: UUID,
        **kwargs,
    ) -> CfsAdjustment:
        """修改 CFS 调整分录。"""
        result = await self.db.execute(
            sa.select(CfsAdjustment).where(
                CfsAdjustment.id == adjustment_id,
                CfsAdjustment.is_deleted == sa.false(),
            )
        )
        adj = result.scalar_one_or_none()
        if adj is None:
            raise ValueError("调整分录不存在")

        if "amount" in kwargs and kwargs["amount"] is not None:
            if kwargs["amount"] <= Decimal("0"):
                raise ValueError("调整金额必须大于零")

        for key, value in kwargs.items():
            if value is not None and hasattr(adj, key):
                setattr(adj, key, value)

        await self.db.flush()
        return adj

    async def delete_adjustment(self, adjustment_id: UUID) -> bool:
        """软删除 CFS 调整分录。"""
        result = await self.db.execute(
            sa.select(CfsAdjustment).where(
                CfsAdjustment.id == adjustment_id,
                CfsAdjustment.is_deleted == sa.false(),
            )
        )
        adj = result.scalar_one_or_none()
        if adj is None:
            return False
        adj.is_deleted = True
        await self.db.flush()
        return True

    async def list_adjustments(
        self,
        project_id: UUID,
        year: int,
    ) -> list[CfsAdjustment]:
        """列出所有 CFS 调整分录。"""
        result = await self.db.execute(
            sa.select(CfsAdjustment)
            .where(
                CfsAdjustment.project_id == project_id,
                CfsAdjustment.year == year,
                CfsAdjustment.is_deleted == sa.false(),
            )
            .order_by(CfsAdjustment.adjustment_no)
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # 8.4 get_reconciliation_status
    # ------------------------------------------------------------------
    async def get_reconciliation_status(
        self,
        project_id: UUID,
        year: int,
    ) -> dict:
        """计算每个科目的变动额、已分配额、未分配余额。

        Validates: Requirements 3.5, 3.6
        """
        # Get trial balance
        result = await self.db.execute(
            sa.select(TrialBalance)
            .where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.is_deleted == sa.false(),
            )
            .order_by(TrialBalance.standard_account_code)
        )
        tb_rows = result.scalars().all()

        # Get all adjustments
        adj_result = await self.db.execute(
            sa.select(CfsAdjustment)
            .where(
                CfsAdjustment.project_id == project_id,
                CfsAdjustment.year == year,
                CfsAdjustment.is_deleted == sa.false(),
            )
        )
        adjustments = adj_result.scalars().all()

        # Calculate allocated amounts per account
        allocated_map: dict[str, Decimal] = {}
        for adj in adjustments:
            # Debit side increases the account's allocated amount
            allocated_map.setdefault(adj.debit_account, Decimal("0"))
            allocated_map[adj.debit_account] += adj.amount
            # Credit side also increases the account's allocated amount
            allocated_map.setdefault(adj.credit_account, Decimal("0"))
            allocated_map[adj.credit_account] += adj.amount

        rows = []
        all_balanced = True
        for tb_row in tb_rows:
            code = tb_row.standard_account_code
            opening = tb_row.opening_balance or Decimal("0")
            closing = tb_row.audited_amount or Decimal("0")
            period_change = closing - opening
            allocated = allocated_map.get(code, Decimal("0"))
            unallocated = period_change - allocated

            if period_change != Decimal("0") and unallocated != Decimal("0"):
                all_balanced = False

            rows.append({
                "account_code": code,
                "account_name": tb_row.account_name,
                "period_change": str(period_change),
                "allocated_total": str(allocated),
                "unallocated": str(unallocated),
            })

        return {
            "rows": rows,
            "all_balanced": all_balanced,
        }

    # ------------------------------------------------------------------
    # 8.5 generate_cfs_main_table
    # ------------------------------------------------------------------
    async def generate_cfs_main_table(
        self,
        project_id: UUID,
        year: int,
    ) -> dict:
        """按 cash_flow_category 和 cash_flow_line_item 汇总 CFS 调整分录。

        Validates: Requirements 3.7
        """
        result = await self.db.execute(
            sa.select(CfsAdjustment)
            .where(
                CfsAdjustment.project_id == project_id,
                CfsAdjustment.year == year,
                CfsAdjustment.is_deleted == sa.false(),
                CfsAdjustment.cash_flow_category.isnot(None),
            )
        )
        adjustments = result.scalars().all()

        # Group by category and line item
        summary: dict[str, dict[str, Decimal]] = {}
        for adj in adjustments:
            cat = adj.cash_flow_category.value
            line = adj.cash_flow_line_item or "未分类"
            summary.setdefault(cat, {})
            summary[cat].setdefault(line, Decimal("0"))
            summary[cat][line] += adj.amount

        # Calculate category totals
        category_totals = {}
        for cat, lines in summary.items():
            category_totals[cat] = str(sum(lines.values()))
            summary[cat] = {k: str(v) for k, v in lines.items()}

        return {
            "project_id": str(project_id),
            "year": year,
            "categories": summary,
            "category_totals": category_totals,
        }

    # ------------------------------------------------------------------
    # 8.6 generate_indirect_method
    # ------------------------------------------------------------------
    async def generate_indirect_method(
        self,
        project_id: UUID,
        year: int,
    ) -> dict:
        """生成间接法补充资料：从净利润出发，逐项调整非现金项目和营运资本变动。

        Validates: Requirements 3.9
        """
        # Get trial balance
        result = await self.db.execute(
            sa.select(TrialBalance)
            .where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.is_deleted == sa.false(),
            )
        )
        tb_map = {r.standard_account_code: r for r in result.scalars().all()}

        def _get_change(code: str) -> Decimal:
            row = tb_map.get(code)
            if row is None:
                return Decimal("0")
            return (row.audited_amount or Decimal("0")) - (row.opening_balance or Decimal("0"))

        def _get_period_amount(code: str) -> Decimal:
            """本期发生额 = audited - opening"""
            row = tb_map.get(code)
            if row is None:
                return Decimal("0")
            return (row.audited_amount or Decimal("0")) - (row.opening_balance or Decimal("0"))

        # Get net profit from financial_report (IS-019)
        fr_result = await self.db.execute(
            sa.select(FinancialReport.current_period_amount).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.report_type == FinancialReportType.income_statement,
                FinancialReport.row_code == "IS-019",
                FinancialReport.is_deleted == sa.false(),
            )
        )
        net_profit = fr_result.scalar_one_or_none() or Decimal("0")

        # Non-cash adjustments
        depreciation = _get_change("1602")  # 累计折旧增加
        amortization_intangible = _get_change("1702")  # 累计摊销增加
        amortization_ltp = -_get_change("1801")  # 长期待摊费用减少 (asset decrease = positive)
        # For 1801, decrease in asset = amortization expense, so negate the change
        # If 1801 closing < opening, change is negative, -change is positive (amortization)

        investment_loss = -_get_period_amount("6111")  # 投资损失（收益取反）
        finance_expense = _get_period_amount("6603")  # 财务费用
        deferred_tax_asset_decrease = -_get_change("1811")  # 递延所得税资产减少

        # Working capital changes
        inventory_decrease = -_get_change("1401")  # 存货减少
        # Operating receivables: 应收票据 + 应收账款 + 预付款项 + 其他应收款
        operating_receivables_decrease = -(
            _get_change("1121") + _get_change("1122")
            + _get_change("1123") + _get_change("1221")
        )
        # Operating payables: 应付票据 + 应付账款 + 预收款项 + 应付职工薪酬 + 应交税费 + 其他应付款
        operating_payables_increase = (
            _get_change("2201") + _get_change("2202")
            + _get_change("2203") + _get_change("2211")
            + _get_change("2221") + _get_change("2241")
        )

        # Calculate operating cash flow via indirect method
        operating_cash_flow = (
            net_profit
            + depreciation
            + amortization_intangible
            + amortization_ltp
            + investment_loss
            + finance_expense
            + deferred_tax_asset_decrease
            + inventory_decrease
            + operating_receivables_decrease
            + operating_payables_increase
        )

        items = [
            {"code": "CF-S03", "name": "净利润", "amount": str(net_profit)},
            {"code": "CF-S05", "name": "固定资产折旧", "amount": str(depreciation)},
            {"code": "CF-S06", "name": "无形资产摊销", "amount": str(amortization_intangible)},
            {"code": "CF-S07", "name": "长期待摊费用摊销", "amount": str(amortization_ltp)},
            {"code": "CF-S08", "name": "财务费用", "amount": str(finance_expense)},
            {"code": "CF-S09", "name": "投资损失", "amount": str(investment_loss)},
            {"code": "CF-S10", "name": "递延所得税资产减少", "amount": str(deferred_tax_asset_decrease)},
            {"code": "CF-S12", "name": "存货的减少", "amount": str(inventory_decrease)},
            {"code": "CF-S13", "name": "经营性应收项目的减少", "amount": str(operating_receivables_decrease)},
            {"code": "CF-S14", "name": "经营性应付项目的增加", "amount": str(operating_payables_increase)},
        ]

        return {
            "project_id": str(project_id),
            "year": year,
            "items": items,
            "operating_cash_flow_indirect": str(operating_cash_flow),
        }

    # ------------------------------------------------------------------
    # 8.7 verify_reconciliation
    # ------------------------------------------------------------------
    async def verify_reconciliation(
        self,
        project_id: UUID,
        year: int,
    ) -> dict:
        """勾稽校验：间接法经营活动=主表经营活动, 现金净增加额=期末-期初。

        Validates: Requirements 3.10, 3.11, 3.12
        """
        checks = []

        # 1. Get indirect method operating cash flow
        indirect = await self.generate_indirect_method(project_id, year)
        indirect_operating = Decimal(indirect["operating_cash_flow_indirect"])

        # 2. Get main table operating cash flow (CF-011)
        fr_result = await self.db.execute(
            sa.select(FinancialReport.current_period_amount).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.report_type == FinancialReportType.cash_flow_statement,
                FinancialReport.row_code == "CF-011",
                FinancialReport.is_deleted == sa.false(),
            )
        )
        main_operating = fr_result.scalar_one_or_none() or Decimal("0")

        diff1 = indirect_operating - main_operating
        checks.append({
            "check_name": "间接法经营活动现金流=主表经营活动现金流",
            "passed": diff1 == Decimal("0"),
            "indirect_value": str(indirect_operating),
            "main_table_value": str(main_operating),
            "difference": str(diff1),
        })

        # 3. Cash reconciliation: net_increase = closing_cash - opening_cash
        # Get trial balance cash accounts
        tb_result = await self.db.execute(
            sa.select(TrialBalance)
            .where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code.in_(CASH_ACCOUNT_CODES),
                TrialBalance.is_deleted == sa.false(),
            )
        )
        cash_rows = tb_result.scalars().all()

        closing_cash = sum(
            (r.audited_amount or Decimal("0")) for r in cash_rows
        )
        opening_cash = sum(
            (r.opening_balance or Decimal("0")) for r in cash_rows
        )
        expected_increase = closing_cash - opening_cash

        # Get net increase from CFS (CF-040)
        fr_result2 = await self.db.execute(
            sa.select(FinancialReport.current_period_amount).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.report_type == FinancialReportType.cash_flow_statement,
                FinancialReport.row_code == "CF-040",
                FinancialReport.is_deleted == sa.false(),
            )
        )
        net_increase = fr_result2.scalar_one_or_none() or Decimal("0")

        diff2 = net_increase - expected_increase
        checks.append({
            "check_name": "现金净增加额=期末现金-期初现金",
            "passed": diff2 == Decimal("0"),
            "net_increase": str(net_increase),
            "closing_cash": str(closing_cash),
            "opening_cash": str(opening_cash),
            "expected_increase": str(expected_increase),
            "difference": str(diff2),
        })

        return {
            "project_id": str(project_id),
            "year": year,
            "checks": checks,
            "all_passed": all(c["passed"] for c in checks),
        }
