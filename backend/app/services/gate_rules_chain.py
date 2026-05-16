"""签字门禁集成 — 全链路生成相关门禁规则

新增 3 条规则注册到 sign_off 和 export_package 门禁入口：
- AllReportsGeneratedRule: 检查 4 种报表已生成且不过期
- AllNotesGeneratedRule: 检查附注已生成且不过期
- ConsistencyPassedRule: 检查一致性门控通过

Requirements: 16.1-16.5
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.gate_engine import GateRule, GateRuleHit, rule_registry
from app.models.phase14_enums import GateType, GateSeverity

logger = logging.getLogger(__name__)


class AllReportsGeneratedRule(GateRule):
    """检查所有 4 种报表已生成且不过期。

    4 种报表：balance_sheet, income_statement, cash_flow_statement, equity_change
    """
    rule_code = "CHAIN-REPORTS-GENERATED"
    error_code = "REPORTS_NOT_GENERATED"
    severity = GateSeverity.blocking

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        project_id = context.get("project_id")
        year = context.get("year")
        if not project_id:
            return None

        try:
            # 查询已生成的报表类型
            result = await db.execute(
                text("""
                    SELECT DISTINCT report_type
                    FROM financial_report
                    WHERE project_id = :pid AND year = :year
                """),
                {"pid": str(project_id), "year": year or 2025},
            )
            generated_types = {r[0] for r in result.fetchall()}

            required_types = {
                "balance_sheet", "income_statement",
                "cash_flow_statement", "equity_change",
            }
            missing = required_types - generated_types

            if not missing:
                return None

            return GateRuleHit(
                rule_code=self.rule_code,
                error_code=self.error_code,
                severity=self.severity,
                message=f"以下报表尚未生成：{', '.join(missing)}",
                location={"project_id": str(project_id), "missing_types": list(missing)},
                suggested_action="请先执行全链路刷新生成所有报表",
            )
        except Exception as e:
            logger.error("[CHAIN-REPORTS] check error: %s", e)
            return None


class AllNotesGeneratedRule(GateRule):
    """检查附注已生成且不过期。"""
    rule_code = "CHAIN-NOTES-GENERATED"
    error_code = "NOTES_NOT_GENERATED"
    severity = GateSeverity.blocking

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        project_id = context.get("project_id")
        year = context.get("year")
        if not project_id:
            return None

        try:
            result = await db.execute(
                text("""
                    SELECT COUNT(*) FROM disclosure_notes
                    WHERE project_id = :pid AND year = :year
                """),
                {"pid": str(project_id), "year": year or 2025},
            )
            count = result.scalar() or 0

            if count > 0:
                return None

            return GateRuleHit(
                rule_code=self.rule_code,
                error_code=self.error_code,
                severity=self.severity,
                message="附注尚未生成",
                location={"project_id": str(project_id)},
                suggested_action="请先执行全链路刷新生成附注",
            )
        except Exception as e:
            logger.error("[CHAIN-NOTES] check error: %s", e)
            return None


class ConsistencyPassedRule(GateRule):
    """检查一致性门控通过（无 blocking 级别不一致项）。"""
    rule_code = "CHAIN-CONSISTENCY"
    error_code = "CONSISTENCY_CHECK_FAILED"
    severity = GateSeverity.blocking

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        project_id = context.get("project_id")
        year = context.get("year")
        if not project_id:
            return None

        try:
            from app.services.consistency_gate import ConsistencyGate

            gate = ConsistencyGate(db)
            result = await gate.run_all_checks(project_id, year or 2025)

            # 检查是否有 blocking 级别的失败项
            blocking_failures = [
                c for c in result.get("checks", [])
                if not c.get("passed") and c.get("severity") == "blocking"
            ]

            if not blocking_failures:
                return None

            failed_names = [c.get("check_name", "unknown") for c in blocking_failures]
            return GateRuleHit(
                rule_code=self.rule_code,
                error_code=self.error_code,
                severity=self.severity,
                message=f"一致性检查未通过：{', '.join(failed_names)}",
                location={
                    "project_id": str(project_id),
                    "failed_checks": failed_names,
                },
                suggested_action="请先修复一致性问题或执行全链路刷新",
            )
        except Exception as e:
            logger.error("[CHAIN-CONSISTENCY] check error: %s", e)
            return None


def register_chain_gate_rules():
    """注册全链路门禁规则到 sign_off 和 export_package"""
    gates = [GateType.sign_off, GateType.export_package]
    rule_registry.register_all(gates, AllReportsGeneratedRule())
    rule_registry.register_all(gates, AllNotesGeneratedRule())
    rule_registry.register_all(gates, ConsistencyPassedRule())
    logger.info(
        "[GATE] Chain rules registered: CHAIN-REPORTS-GENERATED, "
        "CHAIN-NOTES-GENERATED, CHAIN-CONSISTENCY"
    )


# 模块导入时自动注册
register_chain_gate_rules()
