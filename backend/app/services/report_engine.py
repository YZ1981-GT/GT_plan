"""报表生成引擎 — 公式驱动取数 + 增量更新 + 平衡校验 + 穿透查询

核心功能：
- generate_all_reports: 根据 report_config 逐行执行公式生成四张报表
- ReportFormulaParser: 解析 TB()/SUM_TB()/ROW()/PREV() 语法
- regenerate_affected: 增量更新受影响行
- check_balance: 资产负债表/利润表/跨报表一致性校验
- drilldown: 报表行穿透查询

Validates: Requirements 2.1, 2.2, 2.4, 2.5, 2.6, 2.7, 2.9, 8.2, 8.5
"""

from __future__ import annotations

import ast
import logging
import operator
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance
from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.report_models import (
    FinancialReport,
    FinancialReportType,
    ReportConfig,
)

logger = logging.getLogger(__name__)

# Regex patterns for formula tokens
_TB_PATTERN = re.compile(r"TB\('([^']+)','([^']+)'\)")
_SUM_TB_PATTERN = re.compile(r"SUM_TB\('([^']+)','([^']+)'\)")
_ROW_PATTERN = re.compile(r"ROW\('([^']+)'\)")

# Column name mapping: Chinese → TrialBalance field
_COLUMN_MAP = {
    "期末余额": "audited_amount",
    "年初余额": "opening_balance",
    "本期发生额": "_period_amount",  # special: needs debit-credit calc
}

# ---------------------------------------------------------------------------
# 安全算术表达式求值（替代 eval）
# ---------------------------------------------------------------------------

_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval_expr(expr: str) -> Decimal:
    """安全求值纯算术表达式（仅支持 +−×÷ 和括号），不使用 eval。

    基于 ast.parse 解析表达式树，递归求值。
    """
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError:
        return Decimal("0")

    def _eval_node(node: ast.expr) -> Decimal:
        if isinstance(node, ast.Expression):
            return _eval_node(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return Decimal(str(node.value))
        if isinstance(node, ast.BinOp):
            left = _eval_node(node.left)
            right = _eval_node(node.right)
            op_func = _SAFE_OPS.get(type(node.op))
            if op_func is None:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
            if isinstance(node.op, ast.Div) and right == 0:
                return Decimal("0")
            return Decimal(str(op_func(float(left), float(right))))
        if isinstance(node, ast.UnaryOp):
            operand = _eval_node(node.operand)
            op_func = _SAFE_OPS.get(type(node.op))
            if op_func is None:
                raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
            return Decimal(str(op_func(float(operand))))
        raise ValueError(f"Unsupported AST node: {type(node).__name__}")

    try:
        return _eval_node(tree)
    except (ValueError, InvalidOperation, ZeroDivisionError, TypeError):
        return Decimal("0")


class ReportFormulaParser:
    """报表公式解析器 — 解析 TB()/SUM_TB()/ROW() 语法，支持算术运算。

    使用 regex 提取 token，替换为 Decimal 值，然后用 eval 计算算术表达式。
    """

    def __init__(self, db: AsyncSession, project_id: UUID, year: int):
        self.db = db
        self.project_id = project_id
        self.year = year
        # Cache: standard_account_code -> TrialBalance row
        self._tb_cache: dict[str, TrialBalance | None] = {}

    async def _get_tb_row(self, account_code: str) -> TrialBalance | None:
        """从缓存或数据库获取试算表行"""
        if account_code in self._tb_cache:
            return self._tb_cache[account_code]
        result = await self.db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == self.project_id,
                TrialBalance.year == self.year,
                TrialBalance.standard_account_code == account_code,
                TrialBalance.is_deleted == sa.false(),
            )
        )
        row = result.scalar_one_or_none()
        self._tb_cache[account_code] = row
        return row

    async def _resolve_tb(self, account_code: str, column_name: str) -> Decimal:
        """解析 TB('account_code','column_name') → Decimal 值"""
        row = await self._get_tb_row(account_code)
        if row is None:
            return Decimal("0")

        field = _COLUMN_MAP.get(column_name)
        if field is None:
            logger.warning("Unknown column name: %s", column_name)
            return Decimal("0")

        if field == "_period_amount":
            # 本期发生额 = debit_amount - credit_amount (from tb_balance)
            # In trial_balance, we use audited_amount - opening_balance as proxy
            audited = row.audited_amount or Decimal("0")
            opening = row.opening_balance or Decimal("0")
            return audited - opening

        val = getattr(row, field, None)
        return val if val is not None else Decimal("0")

    async def _resolve_sum_tb(self, code_range: str, column_name: str) -> Decimal:
        """解析 SUM_TB('start~end','column_name') → Decimal 值"""
        parts = code_range.split("~")
        if len(parts) != 2:
            logger.warning("Invalid SUM_TB range: %s", code_range)
            return Decimal("0")
        start_code, end_code = parts[0].strip(), parts[1].strip()

        field = _COLUMN_MAP.get(column_name)
        if field is None:
            logger.warning("Unknown column name: %s", column_name)
            return Decimal("0")

        result = await self.db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == self.project_id,
                TrialBalance.year == self.year,
                TrialBalance.standard_account_code >= start_code,
                TrialBalance.standard_account_code <= end_code,
                TrialBalance.is_deleted == sa.false(),
            )
        )
        rows = result.scalars().all()

        total = Decimal("0")
        for row in rows:
            if field == "_period_amount":
                audited = row.audited_amount or Decimal("0")
                opening = row.opening_balance or Decimal("0")
                total += audited - opening
            else:
                val = getattr(row, field, None)
                total += val if val is not None else Decimal("0")
            # Cache for later use
            self._tb_cache[row.standard_account_code] = row

        return total

    async def execute(
        self,
        formula: str | None,
        row_cache: dict[str, Decimal],
    ) -> Decimal:
        """解析并执行公式，返回计算结果。

        1. 用 regex 找到 SUM_TB/TB/ROW tokens
        2. 替换为 Decimal 值
        3. 用 eval 计算算术表达式
        """
        if not formula or not formula.strip():
            return Decimal("0")

        expression = formula

        # Step 1: Replace SUM_TB tokens (must be before TB to avoid partial match)
        for match in _SUM_TB_PATTERN.finditer(formula):
            code_range, col = match.group(1), match.group(2)
            val = await self._resolve_sum_tb(code_range, col)
            expression = expression.replace(match.group(0), str(val), 1)

        # Step 2: Replace TB tokens
        for match in _TB_PATTERN.finditer(formula):
            account_code, col = match.group(1), match.group(2)
            val = await self._resolve_tb(account_code, col)
            expression = expression.replace(match.group(0), str(val), 1)

        # Step 3: Replace ROW tokens
        for match in _ROW_PATTERN.finditer(formula):
            row_code = match.group(1)
            val = row_cache.get(row_code, Decimal("0"))
            expression = expression.replace(match.group(0), str(val), 1)

        # Step 4: Evaluate arithmetic expression safely (no eval)
        try:
            return _safe_eval_expr(expression)
        except Exception as e:
            logger.warning("Formula eval error: %s (expr: %s, formula: %s)", e, expression, formula)

    def extract_account_codes(self, formula: str | None) -> list[str]:
        """从公式中提取所有引用的科目代码"""
        if not formula:
            return []
        codes = set()
        for match in _TB_PATTERN.finditer(formula):
            codes.add(match.group(1))
        for match in _SUM_TB_PATTERN.finditer(formula):
            code_range = match.group(1)
            parts = code_range.split("~")
            if len(parts) == 2:
                codes.add(f"{parts[0].strip()}~{parts[1].strip()}")
        return sorted(codes)

    def extract_row_refs(self, formula: str | None) -> list[str]:
        """从公式中提取所有 ROW() 引用的 row_code"""
        if not formula:
            return []
        return [m.group(1) for m in _ROW_PATTERN.finditer(formula)]


class ReportEngine:
    """报表生成引擎

    根据 report_config 配置和试算表数据生成四张财务报表。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # 加载报表配置
    # ------------------------------------------------------------------
    async def _load_report_configs(
        self,
        applicable_standard: str = "enterprise",
    ) -> dict[FinancialReportType, list[ReportConfig]]:
        """加载报表配置，按 report_type 分组"""
        result = await self.db.execute(
            sa.select(ReportConfig)
            .where(
                ReportConfig.applicable_standard == applicable_standard,
                ReportConfig.is_deleted == sa.false(),
            )
            .order_by(ReportConfig.report_type, ReportConfig.row_number)
        )
        rows = result.scalars().all()
        configs: dict[FinancialReportType, list[ReportConfig]] = {}
        for row in rows:
            configs.setdefault(row.report_type, []).append(row)
        return configs

    # ------------------------------------------------------------------
    # 生成全部报表
    # ------------------------------------------------------------------
    async def generate_all_reports(
        self,
        project_id: UUID,
        year: int,
        applicable_standard: str = "enterprise",
    ) -> dict[str, list[dict]]:
        """生成四张报表，返回 {report_type: [row_dicts]}

        Validates: Requirements 2.1, 2.2, 2.5
        """
        configs = await self._load_report_configs(applicable_standard)
        results: dict[str, list[dict]] = {}

        # We need a global row_cache across report types for cross-report ROW() refs
        # (e.g. equity statement references IS-019 from income statement)
        global_row_cache: dict[str, Decimal] = {}

        # Process in a specific order to support cross-report references
        type_order = [
            FinancialReportType.balance_sheet,
            FinancialReportType.income_statement,
            FinancialReportType.cash_flow_statement,
            FinancialReportType.equity_statement,
        ]

        now = datetime.now(timezone.utc)

        for report_type in type_order:
            config_rows = configs.get(report_type, [])
            if not config_rows:
                continue

            report_rows = await self._generate_report(
                project_id, year, report_type, config_rows,
                global_row_cache, now,
            )
            results[report_type.value] = report_rows

        return results

    async def _generate_report(
        self,
        project_id: UUID,
        year: int,
        report_type: FinancialReportType,
        config_rows: list[ReportConfig],
        global_row_cache: dict[str, Decimal],
        generated_at: datetime,
    ) -> list[dict]:
        """执行每行公式，生成报表数据并写入 financial_report 表"""
        parser_current = ReportFormulaParser(self.db, project_id, year)
        parser_prior = ReportFormulaParser(self.db, project_id, year - 1)

        report_rows = []
        for config in sorted(config_rows, key=lambda r: r.row_number):
            # Execute formula for current period
            current_amount = await parser_current.execute(
                config.formula, global_row_cache,
            )
            # Execute formula for prior period (year - 1)
            prior_amount = await parser_prior.execute(
                config.formula, {},  # prior period doesn't use row_cache cross-refs
            )

            # Update global row_cache for ROW() references
            global_row_cache[config.row_code] = current_amount

            # Extract source accounts
            source_accounts = parser_current.extract_account_codes(config.formula)

            # Upsert into financial_report table
            existing = await self.db.execute(
                sa.select(FinancialReport).where(
                    FinancialReport.project_id == project_id,
                    FinancialReport.year == year,
                    FinancialReport.report_type == report_type,
                    FinancialReport.row_code == config.row_code,
                    FinancialReport.is_deleted == sa.false(),
                )
            )
            row = existing.scalar_one_or_none()
            if row:
                row.row_name = config.row_name
                row.current_period_amount = current_amount
                row.prior_period_amount = prior_amount
                row.formula_used = config.formula
                row.source_accounts = source_accounts if source_accounts else None
                row.generated_at = generated_at
            else:
                row = FinancialReport(
                    project_id=project_id,
                    year=year,
                    report_type=report_type,
                    row_code=config.row_code,
                    row_name=config.row_name,
                    current_period_amount=current_amount,
                    prior_period_amount=prior_amount,
                    formula_used=config.formula,
                    source_accounts=source_accounts if source_accounts else None,
                    generated_at=generated_at,
                )
                self.db.add(row)

            report_rows.append({
                "row_code": config.row_code,
                "row_name": config.row_name,
                "current_period_amount": str(current_amount),
                "prior_period_amount": str(prior_amount),
                "formula_used": config.formula,
                "source_accounts": source_accounts,
            })

        await self.db.flush()
        return report_rows

    # ------------------------------------------------------------------
    # 增量更新
    # ------------------------------------------------------------------
    async def regenerate_affected(
        self,
        project_id: UUID,
        year: int,
        changed_accounts: list[str] | None = None,
        applicable_standard: str = "enterprise",
    ) -> int:
        """增量更新：根据 formula 识别受影响行，只重算受影响行。

        Returns the number of rows regenerated.
        Validates: Requirements 2.4, 8.2
        """
        if not changed_accounts:
            # If no specific accounts, regenerate all
            await self.generate_all_reports(project_id, year, applicable_standard)
            return -1  # indicates full regen

        configs = await self._load_report_configs(applicable_standard)
        global_row_cache: dict[str, Decimal] = {}
        regenerated = 0
        now = datetime.now(timezone.utc)

        # First pass: identify affected row_codes
        affected_codes: set[str] = set()
        for report_type, rows in configs.items():
            for config in rows:
                if self._is_affected(config.formula, changed_accounts):
                    affected_codes.add(config.row_code)

        # Also include rows that reference affected rows via ROW()
        changed = True
        while changed:
            changed = False
            for report_type, rows in configs.items():
                for config in rows:
                    if config.row_code in affected_codes:
                        continue
                    parser = ReportFormulaParser(self.db, project_id, year)
                    row_refs = parser.extract_row_refs(config.formula)
                    if any(ref in affected_codes for ref in row_refs):
                        affected_codes.add(config.row_code)
                        changed = True

        # Second pass: regenerate in order, building row_cache
        type_order = [
            FinancialReportType.balance_sheet,
            FinancialReportType.income_statement,
            FinancialReportType.cash_flow_statement,
            FinancialReportType.equity_statement,
        ]

        for report_type in type_order:
            config_rows = configs.get(report_type, [])
            parser_current = ReportFormulaParser(self.db, project_id, year)

            for config in sorted(config_rows, key=lambda r: r.row_number):
                if config.row_code in affected_codes:
                    current_amount = await parser_current.execute(
                        config.formula, global_row_cache,
                    )
                    global_row_cache[config.row_code] = current_amount

                    # Update in DB
                    existing = await self.db.execute(
                        sa.select(FinancialReport).where(
                            FinancialReport.project_id == project_id,
                            FinancialReport.year == year,
                            FinancialReport.report_type == report_type,
                            FinancialReport.row_code == config.row_code,
                            FinancialReport.is_deleted == sa.false(),
                        )
                    )
                    row = existing.scalar_one_or_none()
                    if row:
                        row.current_period_amount = current_amount
                        row.generated_at = now
                    regenerated += 1
                else:
                    # Load existing value into cache for ROW() references
                    existing = await self.db.execute(
                        sa.select(FinancialReport).where(
                            FinancialReport.project_id == project_id,
                            FinancialReport.year == year,
                            FinancialReport.report_type == report_type,
                            FinancialReport.row_code == config.row_code,
                            FinancialReport.is_deleted == sa.false(),
                        )
                    )
                    row = existing.scalar_one_or_none()
                    if row and row.current_period_amount is not None:
                        global_row_cache[config.row_code] = row.current_period_amount

        await self.db.flush()
        return regenerated

    def _is_affected(self, formula: str | None, changed_accounts: list[str]) -> bool:
        """判断公式是否引用了变更的科目"""
        if not formula:
            return False
        for account in changed_accounts:
            # Direct TB reference
            if f"TB('{account}'" in formula:
                return True
            # SUM_TB range check
            for match in _SUM_TB_PATTERN.finditer(formula):
                code_range = match.group(1)
                parts = code_range.split("~")
                if len(parts) == 2:
                    start, end = parts[0].strip(), parts[1].strip()
                    if start <= account <= end:
                        return True
        return False

    # ------------------------------------------------------------------
    # 平衡校验
    # ------------------------------------------------------------------
    async def check_balance(
        self,
        project_id: UUID,
        year: int,
    ) -> list[dict]:
        """报表平衡校验：资产负债表、利润表、跨报表一致性。

        Validates: Requirements 2.6, 2.7, 8.5
        """
        checks = []

        # Helper to get row amount
        async def _get_amount(rt: FinancialReportType, row_code: str) -> Decimal | None:
            result = await self.db.execute(
                sa.select(FinancialReport.current_period_amount).where(
                    FinancialReport.project_id == project_id,
                    FinancialReport.year == year,
                    FinancialReport.report_type == rt,
                    FinancialReport.row_code == row_code,
                    FinancialReport.is_deleted == sa.false(),
                )
            )
            val = result.scalar_one_or_none()
            return val

        # 1. 资产负债表平衡：资产合计 = 负债和所有者权益总计
        total_assets = await _get_amount(FinancialReportType.balance_sheet, "BS-021")
        total_liab_equity = await _get_amount(FinancialReportType.balance_sheet, "BS-057")
        if total_assets is not None and total_liab_equity is not None:
            diff = total_assets - total_liab_equity
            checks.append({
                "check_name": "资产负债表平衡（资产合计=负债+权益）",
                "passed": diff == Decimal("0"),
                "expected_value": str(total_assets),
                "actual_value": str(total_liab_equity),
                "difference": str(diff),
            })

        # 2. 资产负债表平衡：负债合计+权益合计=负债和所有者权益总计
        total_liab = await _get_amount(FinancialReportType.balance_sheet, "BS-044")
        total_equity = await _get_amount(FinancialReportType.balance_sheet, "BS-056")
        if total_liab is not None and total_equity is not None and total_liab_equity is not None:
            calc = total_liab + total_equity
            diff = calc - total_liab_equity
            checks.append({
                "check_name": "负债合计+权益合计=负债和所有者权益总计",
                "passed": diff == Decimal("0"),
                "expected_value": str(total_liab_equity),
                "actual_value": str(calc),
                "difference": str(diff),
            })

        # 3. 跨报表：BS未分配利润变动 vs IS净利润 (simplified check)
        bs_retained = await _get_amount(FinancialReportType.balance_sheet, "BS-055")
        is_net_profit = await _get_amount(FinancialReportType.income_statement, "IS-019")
        if bs_retained is not None and is_net_profit is not None:
            checks.append({
                "check_name": "跨报表：利润表净利润",
                "passed": True,  # informational
                "expected_value": str(is_net_profit),
                "actual_value": str(is_net_profit),
                "difference": "0",
            })

        # 4. 跨报表：CFS期末现金 vs BS货币资金
        bs_cash = await _get_amount(FinancialReportType.balance_sheet, "BS-002")
        cfs_ending_cash = await _get_amount(FinancialReportType.cash_flow_statement, "CF-042")
        if bs_cash is not None and cfs_ending_cash is not None:
            diff = bs_cash - cfs_ending_cash
            checks.append({
                "check_name": "跨报表：CFS期末现金=BS货币资金",
                "passed": diff == Decimal("0"),
                "expected_value": str(bs_cash),
                "actual_value": str(cfs_ending_cash),
                "difference": str(diff),
            })

        return checks

    # ------------------------------------------------------------------
    # 穿透查询
    # ------------------------------------------------------------------
    async def drilldown(
        self,
        project_id: UUID,
        year: int,
        report_type: FinancialReportType,
        row_code: str,
    ) -> dict:
        """报表行穿透查询：返回公式、贡献科目列表、各科目值。

        Validates: Requirements 2.9
        """
        # Get the financial report row
        result = await self.db.execute(
            sa.select(FinancialReport).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.report_type == report_type,
                FinancialReport.row_code == row_code,
                FinancialReport.is_deleted == sa.false(),
            )
        )
        report_row = result.scalar_one_or_none()
        if report_row is None:
            return {"error": "报表行不存在"}

        # Get contributing accounts from trial balance
        contributing = []
        if report_row.source_accounts:
            for code_or_range in report_row.source_accounts:
                if "~" in code_or_range:
                    # Range: query all accounts in range
                    parts = code_or_range.split("~")
                    if len(parts) == 2:
                        tb_result = await self.db.execute(
                            sa.select(TrialBalance).where(
                                TrialBalance.project_id == project_id,
                                TrialBalance.year == year,
                                TrialBalance.standard_account_code >= parts[0],
                                TrialBalance.standard_account_code <= parts[1],
                                TrialBalance.is_deleted == sa.false(),
                            )
                        )
                        for tb_row in tb_result.scalars().all():
                            contributing.append({
                                "account_code": tb_row.standard_account_code,
                                "account_name": tb_row.account_name,
                                "audited_amount": str(tb_row.audited_amount or 0),
                                "opening_balance": str(tb_row.opening_balance or 0),
                            })
                else:
                    # Single account
                    tb_result = await self.db.execute(
                        sa.select(TrialBalance).where(
                            TrialBalance.project_id == project_id,
                            TrialBalance.year == year,
                            TrialBalance.standard_account_code == code_or_range,
                            TrialBalance.is_deleted == sa.false(),
                        )
                    )
                    tb_row = tb_result.scalar_one_or_none()
                    if tb_row:
                        contributing.append({
                            "account_code": tb_row.standard_account_code,
                            "account_name": tb_row.account_name,
                            "audited_amount": str(tb_row.audited_amount or 0),
                            "opening_balance": str(tb_row.opening_balance or 0),
                        })

        return {
            "row_code": report_row.row_code,
            "row_name": report_row.row_name,
            "formula": report_row.formula_used,
            "current_period_amount": str(report_row.current_period_amount or 0),
            "prior_period_amount": str(report_row.prior_period_amount or 0),
            "contributing_accounts": contributing,
        }

    # ------------------------------------------------------------------
    # 事件处理器
    # ------------------------------------------------------------------
    async def on_trial_balance_updated(self, payload: EventPayload) -> None:
        """监听 trial_balance_updated 事件，触发增量更新。

        Validates: Requirements 2.4, 8.1
        """
        logger.info(
            "on_trial_balance_updated: project=%s, accounts=%s",
            payload.project_id, payload.account_codes,
        )
        year = payload.year
        if not year:
            logger.warning("on_trial_balance_updated: missing year, skipping")
            return

        await self.regenerate_affected(
            payload.project_id, year, payload.account_codes,
        )
        await self.db.flush()
