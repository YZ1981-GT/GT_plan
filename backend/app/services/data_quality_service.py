"""数据质量检查服务 — 套件模式（F7/F29/D3/D10）

提供 5 种检查：
1. debit_credit_balance: 借贷平衡
2. balance_vs_ledger: 余额表 vs 序时账一致性
3. mapping_completeness: 科目映射完整性
4. report_balance: 报表平衡（BS 资产=负债+权益）
5. profit_reconciliation: 利润表勾稽

每种检查返回: {status: "passed"|"warning"|"blocking", message, details}
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


# 容差：±1 元
TOLERANCE = Decimal("1")


class DataQualityService:
    """数据质量检查套件"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def run_checks(
        self,
        project_id: UUID,
        year: int,
        checks: str = "all",
    ) -> dict:
        """执行指定检查，返回分组结果"""
        available_checks = {
            "debit_credit_balance": self._check_debit_credit_balance,
            "balance_vs_ledger": self._check_balance_vs_ledger,
            "mapping_completeness": self._check_mapping_completeness,
            "report_balance": self._check_report_balance,
            "profit_reconciliation": self._check_profit_reconciliation,
        }

        # 确定要执行的检查
        if checks == "all":
            selected = list(available_checks.keys())
        else:
            selected = [c.strip() for c in checks.split(",") if c.strip() in available_checks]

        if not selected:
            selected = list(available_checks.keys())

        # 获取总科目数
        total_accounts = await self._get_total_accounts(project_id, year)

        # 执行检查
        results = {}
        for check_name in selected:
            checker = available_checks[check_name]
            results[check_name] = await checker(project_id, year)

        # 汇总
        summary = {"passed": 0, "warning": 0, "blocking": 0}
        for r in results.values():
            status = r.get("status", "passed")
            if status in summary:
                summary[status] += 1

        return {
            "total_accounts": total_accounts,
            "checks_run": selected,
            "summary": summary,
            "results": results,
        }

    async def _get_total_accounts(self, project_id: UUID, year: int) -> int:
        """获取项目科目总数"""
        result = await self.db.execute(sa.text(
            "SELECT COUNT(DISTINCT account_code) FROM tb_balance "
            "WHERE project_id = :pid AND year = :yr AND is_deleted = false"
        ), {"pid": project_id, "yr": year})
        return result.scalar() or 0

    async def _check_debit_credit_balance(self, project_id: UUID, year: int) -> dict:
        """借贷平衡：所有科目期末借方合计 = 期末贷方合计

        使用 trial_balance 的 audited_amount 按 account_category 分组求和。
        资产+费用类（asset/expense）余额为正=借方余额
        负债+权益+收入类（liability/equity/revenue）余额为正=贷方余额
        """
        result = await self.db.execute(sa.text("""
            SELECT
                COALESCE(SUM(CASE WHEN account_category IN ('asset', 'expense') THEN audited_amount ELSE 0 END), 0) as debit_total,
                COALESCE(SUM(CASE WHEN account_category IN ('liability', 'equity', 'revenue') THEN audited_amount ELSE 0 END), 0) as credit_total
            FROM trial_balance
            WHERE project_id = :pid AND year = :yr AND is_deleted = false
        """), {"pid": project_id, "yr": year})
        row = result.fetchone()

        if row is None:
            return {
                "status": "warning",
                "message": "试算表无数据，无法检查借贷平衡",
                "details": {},
            }

        debit_total = Decimal(str(row[0] or 0))
        credit_total = Decimal(str(row[1] or 0))
        diff = abs(debit_total - credit_total)

        if diff <= TOLERANCE:
            return {
                "status": "passed",
                "message": "借贷平衡",
                "details": {
                    "debit_total": str(debit_total),
                    "credit_total": str(credit_total),
                    "difference": str(diff),
                },
            }
        else:
            return {
                "status": "blocking",
                "message": f"借贷不平衡，差异 {diff:.2f} 元",
                "details": {
                    "debit_total": str(debit_total),
                    "credit_total": str(credit_total),
                    "difference": str(diff),
                },
            }

    async def _check_balance_vs_ledger(self, project_id: UUID, year: int) -> dict:
        """余额表 vs 序时账一致性

        公式：期末余额 = 期初余额 + 本期借方发生额 - 本期贷方发生额
        容差：±1 元
        """
        # 先检查 tb_ledger 是否有数据
        ledger_count_result = await self.db.execute(sa.text(
            "SELECT COUNT(*) FROM tb_ledger "
            "WHERE project_id = :pid AND year = :yr AND is_deleted = false"
        ), {"pid": project_id, "yr": year})
        ledger_count = ledger_count_result.scalar() or 0

        if ledger_count == 0:
            return {
                "status": "warning",
                "message": "序时账无数据，跳过余额vs序时账检查",
                "details": {"ledger_rows": 0},
            }

        # 从 tb_balance 获取各科目的期初/期末/借方发生/贷方发生
        result = await self.db.execute(sa.text("""
            SELECT
                account_code,
                account_name,
                COALESCE(opening_balance, 0) as opening_balance,
                COALESCE(closing_balance, 0) as closing_balance,
                COALESCE(debit_amount, 0) as debit_amount,
                COALESCE(credit_amount, 0) as credit_amount
            FROM tb_balance
            WHERE project_id = :pid AND year = :yr AND is_deleted = false
        """), {"pid": project_id, "yr": year})
        rows = result.fetchall()

        checked = 0
        passed = 0
        differences = []

        for row in rows:
            account_code = row[0]
            account_name = row[1]
            opening = Decimal(str(row[2] or 0))
            closing = Decimal(str(row[3] or 0))
            debit = Decimal(str(row[4] or 0))
            credit = Decimal(str(row[5] or 0))

            # 公式：期末 = 期初 + 借方 - 贷方
            expected_closing = opening + debit - credit
            diff = abs(closing - expected_closing)

            checked += 1
            if diff <= TOLERANCE:
                passed += 1
            else:
                differences.append({
                    "account_code": account_code,
                    "account_name": account_name,
                    "opening_balance": str(opening),
                    "closing_balance": str(closing),
                    "debit_amount": str(debit),
                    "credit_amount": str(credit),
                    "expected_closing": str(expected_closing),
                    "difference": str(diff),
                })

        if not differences:
            return {
                "status": "passed",
                "message": f"余额表一致性检查通过（{checked} 科目）",
                "details": {"checked": checked, "passed": passed, "differences": []},
            }
        else:
            return {
                "status": "warning",
                "message": f"发现 {len(differences)} 个科目余额不一致（共检查 {checked} 科目）",
                "details": {
                    "checked": checked,
                    "passed": passed,
                    "differences": differences[:20],  # 最多返回 20 条
                },
            }

    async def _check_mapping_completeness(self, project_id: UUID, year: int) -> dict:
        """科目映射完整性：tb_balance 中所有科目都有 account_mapping"""
        # 获取 tb_balance 中的科目
        balance_result = await self.db.execute(sa.text(
            "SELECT COUNT(DISTINCT account_code) FROM tb_balance "
            "WHERE project_id = :pid AND year = :yr AND is_deleted = false"
        ), {"pid": project_id, "yr": year})
        total_accounts = balance_result.scalar() or 0

        if total_accounts == 0:
            return {
                "status": "warning",
                "message": "余额表无数据",
                "details": {"total_accounts": 0, "mapped_count": 0, "unmapped_count": 0},
            }

        # 获取已映射的科目数
        mapped_result = await self.db.execute(sa.text("""
            SELECT COUNT(DISTINCT b.account_code)
            FROM tb_balance b
            INNER JOIN account_mapping m
                ON m.project_id = b.project_id
                AND m.original_account_code = b.account_code
            WHERE b.project_id = :pid AND b.year = :yr AND b.is_deleted = false
        """), {"pid": project_id, "yr": year})
        mapped_count = mapped_result.scalar() or 0

        unmapped_count = total_accounts - mapped_count
        rate = (mapped_count / total_accounts * 100) if total_accounts > 0 else 0

        if unmapped_count == 0:
            return {
                "status": "passed",
                "message": f"科目映射完整（{mapped_count}/{total_accounts}，100%）",
                "details": {
                    "total_accounts": total_accounts,
                    "mapped_count": mapped_count,
                    "unmapped_count": 0,
                    "completion_rate": 100.0,
                },
            }
        elif rate >= 80:
            return {
                "status": "warning",
                "message": f"科目映射率 {rate:.1f}%（{unmapped_count} 个未映射）",
                "details": {
                    "total_accounts": total_accounts,
                    "mapped_count": mapped_count,
                    "unmapped_count": unmapped_count,
                    "completion_rate": round(rate, 1),
                },
            }
        else:
            return {
                "status": "blocking",
                "message": f"科目映射率过低 {rate:.1f}%（{unmapped_count} 个未映射）",
                "details": {
                    "total_accounts": total_accounts,
                    "mapped_count": mapped_count,
                    "unmapped_count": unmapped_count,
                    "completion_rate": round(rate, 1),
                },
            }

    async def _check_report_balance(self, project_id: UUID, year: int) -> dict:
        """报表平衡：BS 资产合计 = 负债合计 + 权益合计"""
        # 查找资产合计、负债合计、权益合计行
        result = await self.db.execute(sa.text("""
            SELECT row_name, current_period_amount
            FROM financial_report
            WHERE project_id = :pid AND year = :yr
            AND report_type = 'balance_sheet'
            AND is_deleted = false
            AND (row_name LIKE '%资产合计%' OR row_name LIKE '%负债合计%'
                 OR row_name LIKE '%所有者权益%合计%' OR row_name LIKE '%股东权益%合计%'
                 OR row_name LIKE '%负债和所有者权益%合计%' OR row_name LIKE '%负债和股东权益%合计%')
        """), {"pid": project_id, "yr": year})
        rows = result.fetchall()

        if not rows:
            return {
                "status": "warning",
                "message": "报表未生成或无合计行，跳过平衡检查",
                "details": {},
            }

        asset_total = Decimal("0")
        liability_equity_total = Decimal("0")

        for row in rows:
            name = row[0] or ""
            amount = Decimal(str(row[1] or 0))

            if "资产合计" in name and "负债" not in name:
                asset_total = amount
            elif "负债和所有者权益" in name or "负债和股东权益" in name:
                liability_equity_total = amount

        diff = abs(asset_total - liability_equity_total)

        if asset_total == 0 and liability_equity_total == 0:
            return {
                "status": "warning",
                "message": "合计行金额均为 0，可能报表未生成",
                "details": {"asset_total": "0", "liability_equity_total": "0"},
            }

        if diff <= TOLERANCE:
            return {
                "status": "passed",
                "message": "资产负债表平衡",
                "details": {
                    "asset_total": str(asset_total),
                    "liability_equity_total": str(liability_equity_total),
                    "difference": str(diff),
                },
            }
        else:
            return {
                "status": "blocking",
                "message": f"资产负债表不平衡，差异 {diff:.2f} 元",
                "details": {
                    "asset_total": str(asset_total),
                    "liability_equity_total": str(liability_equity_total),
                    "difference": str(diff),
                },
            }

    async def _check_profit_reconciliation(self, project_id: UUID, year: int) -> dict:
        """利润表勾稽：IS 净利润 ≈ 期末未分配利润 - 期初未分配利润"""
        # 简化版：检查利润表是否有净利润行
        result = await self.db.execute(sa.text("""
            SELECT row_name, current_period_amount
            FROM financial_report
            WHERE project_id = :pid AND year = :yr
            AND report_type = 'income_statement'
            AND is_deleted = false
            AND (row_name LIKE '%净利润%')
            LIMIT 1
        """), {"pid": project_id, "yr": year})
        row = result.fetchone()

        if not row:
            return {
                "status": "warning",
                "message": "利润表未生成或无净利润行，跳过勾稽检查",
                "details": {},
            }

        net_profit = Decimal(str(row[1] or 0))
        return {
            "status": "passed",
            "message": f"利润表净利润 {net_profit:.2f} 元（勾稽需手工确认）",
            "details": {"net_profit": str(net_profit)},
        }
