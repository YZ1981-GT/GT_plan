"""签字门禁集成 — 全链路生成相关门禁规则

3 条规则（sign_off 和 export_package 门禁入口）：
- AllReportsGeneratedRule: 检查 4 种报表已生成且不过期
- AllNotesGeneratedRule: 检查附注已生成且不过期
- ConsistencyPassedRule: 检查一致性门控通过（启动时由 startup_registry 注册，见 register_consistency_gate_rule）

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
        if not project_id:
            return None

        from app.services.project_audit_year import fetch_project_audit_year

        year = await fetch_project_audit_year(db, project_id)
        if year is None:
            return GateRuleHit(
                rule_code=self.rule_code,
                error_code=self.error_code,
                severity=GateSeverity.warning,
                message="项目未设置审计年度，未运行报表生成检查",
                location={"project_id": str(project_id)},
                suggested_action="请在项目基本信息中设置审计年度",
            )

        try:
            # 查询已生成的报表类型
            result = await db.execute(
                text("""
                    SELECT DISTINCT report_type
                    FROM financial_report
                    WHERE project_id = :pid AND year = :year
                """),
                {"pid": str(project_id), "year": year},
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
        if not project_id:
            return None

        from app.services.project_audit_year import fetch_project_audit_year

        year = await fetch_project_audit_year(db, project_id)
        if year is None:
            return GateRuleHit(
                rule_code=self.rule_code,
                error_code=self.error_code,
                severity=GateSeverity.warning,
                message="项目未设置审计年度，未运行附注生成检查",
                location={"project_id": str(project_id)},
                suggested_action="请在项目基本信息中设置审计年度",
            )

        try:
            result = await db.execute(
                text("""
                    SELECT COUNT(*) FROM disclosure_notes
                    WHERE project_id = :pid AND year = :year
                """),
                {"pid": str(project_id), "year": year},
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
    """检查一致性门控通过 — 经 gate_decision 统一判定。

    ADR-FHIC-14 第 5 点。observe 下 would_block → warning（提示）；
    enforce 下 would_block → blocking（阻断）。
    """
    rule_code = "CHAIN-CONSISTENCY"
    error_code = "CONSISTENCY_CHECK_FAILED"
    severity = GateSeverity.blocking

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        project_id = context.get("project_id")
        if not project_id:
            return None

        from app.services.project_audit_year import fetch_project_audit_year

        year = await fetch_project_audit_year(db, project_id)
        if year is None:
            return GateRuleHit(
                rule_code=self.rule_code,
                error_code=self.error_code,
                severity=GateSeverity.warning,
                message="项目未设置审计年度，未运行一致性检查",
                location={"project_id": str(project_id)},
                suggested_action="请在项目基本信息中设置审计年度",
            )

        from app.services.consistency_gate import ConsistencyGate, gate_decision

        try:
            gate = ConsistencyGate(db)
            result = await gate.run_all_checks(project_id, year)
        except Exception as exc:
            from app.core.config import settings

            mode = getattr(settings, "CONSISTENCY_GATE_ENFORCEMENT", "observe")
            sev = GateSeverity.blocking if mode == "enforce" else GateSeverity.warning
            return GateRuleHit(
                rule_code=self.rule_code,
                error_code=self.error_code,
                severity=sev,
                message=f"一致性检查未能运行：{type(exc).__name__}：{str(exc)[:200]}",
                location={"project_id": str(project_id)},
                suggested_action="请联系管理员检查系统日志",
            )

        decision = gate_decision(result, consumer="chain_rule")
        if not decision.items:
            return None

        sev = GateSeverity.blocking if decision.blocks else GateSeverity.warning
        failed_names = [c.check_name for c in decision.items]
        location_items = [
            {"check_name": c.check_name, "status": c.status, "reason": c.reason}
            for c in decision.items
        ]
        return GateRuleHit(
            rule_code=self.rule_code,
            error_code=self.error_code,
            severity=sev,
            message=decision.summary,
            location={
                "project_id": str(project_id),
                "failed_checks": failed_names,
                "items": location_items,
            },
            suggested_action="请补齐数据后重新检查" if decision.blocks else "请关注未通过的检查项",
        )


_CHAIN_GATES = (GateType.sign_off, GateType.export_package)


def _register_once(rule: GateRule) -> None:
    """按 rule_code 去重注册（注册表本身不去重，启动任务重跑不得叠出两份）。"""
    for gate in _CHAIN_GATES:
        if not any(r.rule_code == rule.rule_code for r in rule_registry.get_rules(gate)):
            rule_registry.register(gate, rule)


def register_consistency_gate_rule() -> None:
    """启动时只注册一致性门禁规则到 sign_off 和 export_package（需求 16.4，ADR-FHIC-14 第 5 点）。

    observe（默认）下只给 warning 级提示「…（当前为只提示模式）」、不阻断，enforce 下才阻断。
    本模块原先只靠导入时自动注册三条规则，而生产代码从不导入它 ⇒ 三条都不在门禁里。
    另两条（报表 / 附注已生成）是 blocking 级，注册即新增签发 / 导出阻断，不属本 spec 范围，仍不注册。
    """
    _register_once(ConsistencyPassedRule())
    logger.info("[GATE] Chain rule registered: CHAIN-CONSISTENCY")


def register_chain_gate_rules():
    """注册全部三条全链路门禁规则（报表 / 附注已生成为 blocking 级；生产启动不调用，见上）。"""
    for rule in (AllReportsGeneratedRule(), AllNotesGeneratedRule(), ConsistencyPassedRule()):
        _register_once(rule)
    logger.info(
        "[GATE] Chain rules registered: CHAIN-REPORTS-GENERATED, "
        "CHAIN-NOTES-GENERATED, CHAIN-CONSISTENCY"
    )
