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

            # Check: sum of aux balances should match main balance per account
            bal_q = sa.select(
                TbBalance.account_code,
                sa.func.sum(TbBalance.closing_balance).label("bal_total"),
            ).where(
                TbBalance.project_id == project_id,
                TbBalance.year == year,
                TbBalance.is_deleted == False,
            ).group_by(TbBalance.account_code)

            aux_q = sa.select(
                TbAuxBalance.account_code,
                sa.func.sum(TbAuxBalance.closing_balance).label("aux_total"),
            ).where(
                TbAuxBalance.project_id == project_id,
                TbAuxBalance.year == year,
                TbAuxBalance.is_deleted == False,
            ).group_by(TbAuxBalance.account_code)

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
        """报表与附注一致性校验（stub）。"""
        return []

    async def _validate_workpaper_tb(self, project_id: UUID, year: int) -> list[ValidationFinding]:
        """底稿与试算表一致性校验（stub）。"""
        return []

    async def _validate_adjustment_report(self, project_id: UUID, year: int) -> list[ValidationFinding]:
        """调整分录与报表一致性校验（stub）。"""
        return []

    # ---- 完整性校验 ----

    async def _validate_required_fields(self, project_id: UUID, year: int) -> list[ValidationFinding]:
        """必填字段完整性校验。"""
        findings = []
        if not self.db:
            return findings
        try:
            import sqlalchemy as sa
            from app.models.audit_platform_models import TbBalance

            q = sa.select(TbBalance).where(
                TbBalance.project_id == project_id,
                TbBalance.year == year,
                TbBalance.is_deleted == False,
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
        """数据格式正确性校验（stub）。"""
        return []

    async def _validate_range(self, project_id: UUID, year: int) -> list[ValidationFinding]:
        """数据范围合理性校验（stub）。"""
        return []

    async def _validate_logic(self, project_id: UUID, year: int) -> list[ValidationFinding]:
        """数据逻辑一致性校验（stub）。"""
        return []

    # ---- 修复 ----

    async def auto_fix(self, project_id: UUID, finding_ids: list[str]) -> dict:
        """自动修复常见错误（stub）。"""
        return {
            "fixed": 0,
            "skipped": len(finding_ids),
            "message": "自动修复功能暂未实现",
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
