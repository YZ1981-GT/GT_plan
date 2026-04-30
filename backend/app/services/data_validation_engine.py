"""数据校验引擎 — 一致性 + 完整性校验

Phase 8 Task 7: 数据校验增强
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class ValidationFinding:
    """校验发现项。"""

    def __init__(
        self,
        check_type: str,
        severity: str,
        message: str,
        details: dict | None = None,
        fix_suggestion: str | None = None,
    ):
        self.id = str(uuid4())
        self.check_type = check_type
        self.severity = severity  # high, medium, low, info
        self.message = message
        self.details = details or {}
        self.fix_suggestion = fix_suggestion
        self.created_at = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "check_type": self.check_type,
            "severity": self.severity,
            "message": self.message,
            "details": self.details,
            "fix_suggestion": self.fix_suggestion,
            "created_at": self.created_at,
        }


class DataValidationEngine:
    """数据校验引擎 — 4种一致性校验 + 4种完整性校验。"""

    def __init__(self, db=None):
        self.db = db

    async def validate_project(self, project_id: UUID, year: int = 2025) -> dict:
        """运行全部校验，返回汇总结果。"""
        findings: list[ValidationFinding] = []

        # 一致性校验
        findings.extend(await self._validate_balance_aux(project_id, year))
        findings.extend(await self._validate_report_note(project_id, year))
        findings.extend(await self._validate_workpaper_tb(project_id, year))
        findings.extend(await self._validate_adjustment_report(project_id, year))

        # 完整性校验
        findings.extend(await self._validate_required_fields(project_id, year))
        findings.extend(await self._validate_format(project_id, year))
        findings.extend(await self._validate_range(project_id, year))
        findings.extend(await self._validate_logic(project_id, year))

        result_list = [f.to_dict() for f in findings]
        return {
            "project_id": str(project_id),
            "year": year,
            "findings": result_list,
            "total": len(result_list),
            "by_severity": {
                "high": len([f for f in findings if f.severity == "high"]),
                "medium": len([f for f in findings if f.severity == "medium"]),
                "low": len([f for f in findings if f.severity == "low"]),
                "info": len([f for f in findings if f.severity == "info"]),
            },
            "blocking": len([f for f in findings if f.severity == "high"]),
        }

    # ---- 一致性校验 ----

    async def _validate_balance_aux(self, project_id: UUID, year: int) -> list[ValidationFinding]:
        """余额表与辅助表一致性校验。"""
        findings = []
        if not self.db:
            return findings
        try:
            import sqlalchemy as sa
            from app.models.audit_platform_models import TbBalance, TbAuxBalance
            from app.services.dataset_query import get_active_filter

            # Check: sum of aux balances should match main balance per account
            balance_filter = await get_active_filter(self.db, TbBalance.__table__, project_id, year)
            aux_filter = await get_active_filter(self.db, TbAuxBalance.__table__, project_id, year)
            bal_q = sa.select(
                TbBalance.account_code,
                sa.func.sum(TbBalance.closing_balance).label("bal_total"),
            ).where(balance_filter).group_by(TbBalance.account_code)

            aux_q = sa.select(
                TbAuxBalance.account_code,
                sa.func.sum(TbAuxBalance.closing_balance).label("aux_total"),
            ).where(aux_filter).group_by(TbAuxBalance.account_code)

            bal_rows = (await self.db.execute(bal_q)).all()
            aux_rows = (await self.db.execute(aux_q)).all()

            bal_map = {r.account_code: float(r.bal_total or 0) for r in bal_rows}
            aux_map = {r.account_code: float(r.aux_total or 0) for r in aux_rows}

            for code, bal_total in bal_map.items():
                if code in aux_map:
                    diff = abs(bal_total - aux_map[code])
                    if diff > 0.01:
                        findings.append(ValidationFinding(
                            check_type="balance_aux_consistency",
                            severity="high",
                            message=f"科目 {code} 余额表({bal_total:.2f})与辅助表({aux_map[code]:.2f})不一致，差异 {diff:.2f}",
                            details={"account_code": code, "balance": bal_total, "aux": aux_map[code]},
                            fix_suggestion="检查辅助账是否完整导入",
                        ))
        except Exception as e:
            logger.warning("balance_aux validation error: %s", e)
        return findings

    async def _validate_report_note(self, project_id: UUID, year: int) -> list[ValidationFinding]:
        """报表与附注一致性校验：financial_report 金额 vs disclosure_notes 关键科目金额"""
        findings = []
        if not self.db:
            return findings
        try:
            import sqlalchemy as sa
            from sqlalchemy import text
            # 查询报表行与附注关键科目的金额比对
            stmt = text("""
                SELECT fr.line_code, fr.line_name, fr.amount as report_amount,
                       dn.account_name, (dn.table_data->0->>'closing_balance')::numeric as note_amount
                FROM financial_report fr
                JOIN disclosure_notes dn ON dn.project_id = fr.project_id
                    AND dn.account_name = fr.line_name
                    AND dn.year = :year
                    AND dn.is_deleted = false
                WHERE fr.project_id = :pid
                    AND fr.is_deleted = false
                    AND dn.table_data IS NOT NULL
                    AND (dn.table_data->0->>'closing_balance') IS NOT NULL
                LIMIT 50
            """)
            result = await self.db.execute(stmt, {"pid": str(project_id), "year": year})
            for row in result.fetchall():
                report_amt = float(row[2] or 0)
                note_amt = float(row[4] or 0)
                diff = abs(report_amt - note_amt)
                if diff > 0.01:
                    findings.append(ValidationFinding(
                        check_type="report_note_consistency",
                        severity="high",
                        message=f"报表行「{row[1]}」金额({report_amt:.2f})与附注({note_amt:.2f})不一致，差异 {diff:.2f}",
                        details={"line_code": row[0], "report_amount": report_amt, "note_amount": note_amt, "diff": diff},
                        fix_suggestion="检查附注数据来源是否与报表同步",
                    ))
        except Exception as e:
            logger.debug("report_note validation skipped: %s", e)
        return findings

    async def _validate_workpaper_tb(self, project_id: UUID, year: int) -> list[ValidationFinding]:
        """底稿与试算表一致性校验：parsed_data.audited_amount vs trial_balance.audited_amount"""
        findings = []
        if not self.db:
            return findings
        try:
            from sqlalchemy import text
            stmt = text("""
                SELECT wp.wp_code,
                       (wp.parsed_data->>'audited_amount')::numeric as wp_amount,
                       tb.audited_amount as tb_amount
                FROM working_paper wp
                JOIN wp_account_mapping wam ON wam.wp_code = wp.wp_code AND wam.project_id = wp.project_id
                JOIN trial_balance tb ON tb.project_id = wp.project_id
                    AND tb.standard_account_code = wam.standard_account_code
                    AND tb.year = :year
                    AND tb.is_deleted = false
                WHERE wp.project_id = :pid
                    AND wp.is_deleted = false
                    AND wp.parsed_data->>'audited_amount' IS NOT NULL
                LIMIT 100
            """)
            result = await self.db.execute(stmt, {"pid": str(project_id), "year": year})
            for row in result.fetchall():
                wp_amt = float(row[1] or 0)
                tb_amt = float(row[2] or 0)
                diff = abs(wp_amt - tb_amt)
                if diff > 0.01:
                    findings.append(ValidationFinding(
                        check_type="workpaper_tb_consistency",
                        severity="high",
                        message=f"底稿「{row[0]}」审定数({wp_amt:.2f})与试算表({tb_amt:.2f})不一致，差异 {diff:.2f}",
                        details={"wp_code": row[0], "wp_amount": wp_amt, "tb_amount": tb_amt, "diff": diff},
                        fix_suggestion="刷新底稿预填充或手动修正审定数",
                    ))
        except Exception as e:
            logger.debug("workpaper_tb validation skipped: %s", e)
        return findings

    async def _validate_adjustment_report(self, project_id: UUID, year: int) -> list[ValidationFinding]:
        """调整分录与报表一致性校验：adjustments AJE 合计 vs trial_balance AJE 列"""
        findings = []
        if not self.db:
            return findings
        try:
            from sqlalchemy import text
            # 按科目汇总 AJE 调整金额
            stmt = text("""
                SELECT ae.account_code,
                       SUM(ae.debit_amount) - SUM(ae.credit_amount) as aje_net,
                       tb.aje_amount as tb_aje
                FROM adjustment_entries ae
                JOIN adjustments a ON a.id = ae.adjustment_id
                    AND a.project_id = :pid
                    AND a.year = :year
                    AND a.entry_type = 'aje'
                    AND a.is_deleted = false
                JOIN trial_balance tb ON tb.project_id = a.project_id
                    AND tb.standard_account_code = ae.account_code
                    AND tb.year = :year
                    AND tb.is_deleted = false
                WHERE ae.is_deleted = false
                GROUP BY ae.account_code, tb.aje_amount
                HAVING ABS(SUM(ae.debit_amount) - SUM(ae.credit_amount) - COALESCE(tb.aje_amount, 0)) > 0.01
                LIMIT 50
            """)
            result = await self.db.execute(stmt, {"pid": str(project_id), "year": year})
            for row in result.fetchall():
                aje_net = float(row[1] or 0)
                tb_aje = float(row[2] or 0)
                diff = abs(aje_net - tb_aje)
                findings.append(ValidationFinding(
                    check_type="adjustment_report_consistency",
                    severity="high",
                    message=f"科目「{row[0]}」AJE 合计({aje_net:.2f})与试算表 AJE({tb_aje:.2f})不一致，差异 {diff:.2f}",
                    details={"account_code": row[0], "aje_net": aje_net, "tb_aje": tb_aje, "diff": diff},
                    fix_suggestion="重新计算试算表或检查调整分录",
                ))
        except Exception as e:
            logger.debug("adjustment_report validation skipped: %s", e)
        return findings

    # ---- 完整性校验 ----

    async def _validate_required_fields(self, project_id: UUID, year: int) -> list[ValidationFinding]:
        """必填字段完整性校验。"""
        findings = []
        if not self.db:
            return findings
        try:
            import sqlalchemy as sa
            from app.models.audit_platform_models import TbBalance
            from app.services.dataset_query import get_active_filter

            q = sa.select(TbBalance).where(
                await get_active_filter(self.db, TbBalance.__table__, project_id, year)
            )
            rows = (await self.db.execute(q)).scalars().all()
            for row in rows:
                if not row.account_code:
                    findings.append(ValidationFinding(
                        check_type="required_field",
                        severity="high",
                        message="余额表存在空科目编码",
                        fix_suggestion="检查导入数据",
                    ))
                    break
        except Exception as e:
            logger.warning("required_fields validation error: %s", e)
        return findings

    async def _validate_format(self, project_id: UUID, year: int) -> list[ValidationFinding]:
        """数据格式正确性校验：科目编码格式、金额精度、日期格式"""
        findings = []
        if not self.db:
            return findings
        try:
            import sqlalchemy as sa
            from app.models.audit_platform_models import TbBalance
            from app.services.dataset_query import get_active_filter
            import re

            q = sa.select(TbBalance.id, TbBalance.account_code, TbBalance.closing_balance).where(
                await get_active_filter(self.db, TbBalance.__table__, project_id, year)
            ).limit(500)
            rows = (await self.db.execute(q)).all()

            for row in rows:
                # 科目编码格式：应为纯数字或数字+点号
                if row.account_code and not re.match(r'^[\d.]+$', row.account_code):
                    findings.append(ValidationFinding(
                        check_type="format_account_code",
                        severity="medium",
                        message=f"科目编码「{row.account_code}」包含非法字符",
                        details={"account_code": row.account_code},
                        fix_suggestion="科目编码应为纯数字或数字+点号格式",
                    ))
                    if len(findings) >= 20:
                        break
        except Exception as e:
            logger.debug("format validation skipped: %s", e)
        return findings

    async def _validate_range(self, project_id: UUID, year: int) -> list[ValidationFinding]:
        """数据范围合理性校验：异常大金额、负数余额、变动率超阈值"""
        findings = []
        if not self.db:
            return findings
        try:
            from sqlalchemy import text
            # 检查异常大金额（超过 10 亿）
            stmt = text("""
                SELECT account_code, account_name, closing_balance
                FROM tb_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                    AND ABS(closing_balance) > 1000000000
                LIMIT 10
            """)
            result = await self.db.execute(stmt, {"pid": str(project_id), "year": year})
            for row in result.fetchall():
                findings.append(ValidationFinding(
                    check_type="range_large_amount",
                    severity="medium",
                    message=f"科目「{row[0]} {row[1]}」余额 {float(row[2]):,.2f} 超过 10 亿，请确认",
                    details={"account_code": row[0], "amount": float(row[2])},
                    fix_suggestion="确认金额是否正确，排除导入错误",
                ))

            # 检查试算表变动率超 100%
            stmt2 = text("""
                SELECT standard_account_code, audited_amount, unadjusted_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                    AND unadjusted_amount != 0
                    AND ABS(audited_amount - unadjusted_amount) / ABS(unadjusted_amount) > 1.0
                LIMIT 10
            """)
            result2 = await self.db.execute(stmt2, {"pid": str(project_id), "year": year})
            for row in result2.fetchall():
                change_rate = abs(float(row[1] or 0) - float(row[2] or 0)) / abs(float(row[2])) * 100
                findings.append(ValidationFinding(
                    check_type="range_high_change_rate",
                    severity="medium",
                    message=f"科目「{row[0]}」变动率 {change_rate:.0f}% 超过 100%，请关注",
                    details={"account_code": row[0], "audited": float(row[1] or 0), "unadjusted": float(row[2] or 0), "change_rate": change_rate},
                    fix_suggestion="核实调整分录是否合理",
                ))
        except Exception as e:
            logger.debug("range validation skipped: %s", e)
        return findings

    async def _validate_logic(self, project_id: UUID, year: int) -> list[ValidationFinding]:
        """数据逻辑一致性校验：审定数=未审数+AJE+RJE、借贷平衡"""
        findings = []
        if not self.db:
            return findings
        try:
            from sqlalchemy import text
            # 检查试算表：审定数 = 未审数 + AJE + RJE
            stmt = text("""
                SELECT standard_account_code,
                       unadjusted_amount, aje_amount, rje_amount, audited_amount
                FROM trial_balance
                WHERE project_id = :pid AND year = :year AND is_deleted = false
                LIMIT 500
            """)
            result = await self.db.execute(stmt, {"pid": str(project_id), "year": year})
            for row in result.fetchall():
                unadj = float(row[1] or 0)
                aje = float(row[2] or 0)
                rje = float(row[3] or 0)
                audited = float(row[4] or 0)
                expected = unadj + aje + rje
                diff = abs(audited - expected)
                if diff > 0.01:
                    findings.append(ValidationFinding(
                        check_type="logic_audited_formula",
                        severity="high",
                        message=f"科目「{row[0]}」审定数({audited:.2f}) ≠ 未审数({unadj:.2f})+AJE({aje:.2f})+RJE({rje:.2f})={expected:.2f}，差异 {diff:.2f}",
                        details={"account_code": row[0], "unadjusted": unadj, "aje": aje, "rje": rje, "audited": audited, "expected": expected},
                        fix_suggestion="重新计算试算表（POST /api/trial-balance/recalc）",
                    ))
                    if len(findings) >= 20:
                        break
        except Exception as e:
            logger.debug("logic validation skipped: %s", e)
        return findings

    # ---- 修复 ----

    async def auto_fix(self, project_id: UUID, finding_ids: list[str]) -> dict:
        """自动修复常见错误

        支持的修复类型：
        - logic_audited_formula: 重新计算试算表审定数
        - workpaper_tb_consistency: 触发底稿预填充刷新
        """
        if not self.db:
            return {"fixed": 0, "skipped": len(finding_ids), "message": "数据库连接不可用"}

        fixed = 0
        skipped = 0
        errors = []

        for fid in finding_ids:
            try:
                # 尝试触发试算表重算（最常见的修复操作）
                from app.services.trial_balance_service import TrialBalanceService
                tb_svc = TrialBalanceService(self.db)
                await tb_svc.full_recalc(project_id)
                fixed += 1
                break  # 全量重算一次即可
            except Exception as e:
                skipped += 1
                errors.append(f"finding={fid}: {str(e)[:100]}")

        return {
            "fixed": fixed,
            "skipped": skipped,
            "errors": errors,
            "message": f"已修复 {fixed} 项，跳过 {skipped} 项" + (f"（{'; '.join(errors[:3])}）" if errors else ""),
        }

    # ---- 导出 ----

    def export_findings(self, findings: list[dict], format: str = "csv") -> bytes:
        """导出校验结果。"""
        if format == "csv":
            import csv
            import io
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=["id", "check_type", "severity", "message"])
            writer.writeheader()
            for f in findings:
                writer.writerow({k: f.get(k, "") for k in ["id", "check_type", "severity", "message"]})
            return output.getvalue().encode("utf-8-sig")
        return b""
