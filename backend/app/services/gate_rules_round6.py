"""Round 6: KAM 确认 + 独立性确认 门禁规则

将原先散落在 partner_service._compute_sign_extra_findings 和
qc_dashboard_service._compute_archive_extra_findings 中的 wizard_state
检查提升为正式 GateRule，注册到 sign_off + export_package 两个门禁入口。
"""
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.gate_engine import GateRule, GateRuleHit, rule_registry
from app.models.phase14_enums import GateType, GateSeverity

logger = logging.getLogger(__name__)


class KamConfirmedRule(GateRule):
    """关键审计事项（KAM）确认检查

    读取 Project.wizard_state.kam_confirmed，未确认则阻断。
    """
    rule_code = "R6-KAM"
    error_code = "KAM_NOT_CONFIRMED"
    severity = GateSeverity.blocking

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        project_id = context.get("project_id")
        if not project_id:
            return None

        try:
            from app.models.core import Project
            result = await db.execute(
                select(Project).where(Project.id == project_id)
            )
            project = result.scalar_one_or_none()
            if project is None:
                return None

            ws = project.wizard_state or {}
            if ws.get("kam_confirmed", False):
                return None

            return GateRuleHit(
                rule_code=self.rule_code,
                error_code=self.error_code,
                severity=self.severity,
                message="关键审计事项尚未确认",
                location={"project_id": str(project_id)},
                suggested_action="请在项目向导确认关键审计事项",
            )
        except Exception as e:
            logger.error(f"[R6-KAM] check error: {e}")
            return None


class IndependenceConfirmedRule(GateRule):
    """独立性确认检查

    读取 Project.wizard_state.independence_confirmed，未确认则阻断。
    """
    rule_code = "R6-INDEPENDENCE"
    error_code = "INDEPENDENCE_NOT_CONFIRMED"
    severity = GateSeverity.blocking

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        project_id = context.get("project_id")
        if not project_id:
            return None

        try:
            from app.models.core import Project
            result = await db.execute(
                select(Project).where(Project.id == project_id)
            )
            project = result.scalar_one_or_none()
            if project is None:
                return None

            ws = project.wizard_state or {}
            if ws.get("independence_confirmed", False):
                return None

            return GateRuleHit(
                rule_code=self.rule_code,
                error_code=self.error_code,
                severity=self.severity,
                message="独立性确认未完成",
                location={"project_id": str(project_id)},
                suggested_action="请完成独立性声明",
            )
        except Exception as e:
            logger.error(f"[R6-INDEPENDENCE] check error: {e}")
            return None


class SubsequentEventsReviewedRule(GateRule):
    """期后事项已复核检查

    读取 Project.wizard_state.subsequent_events_reviewed，未复核则阻断。
    """
    rule_code = "R7-SUBSEQUENT"
    error_code = "SUBSEQUENT_EVENTS_NOT_REVIEWED"
    severity = GateSeverity.blocking

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        project_id = context.get("project_id")
        if not project_id:
            return None

        try:
            from app.models.core import Project
            result = await db.execute(
                select(Project).where(Project.id == project_id)
            )
            project = result.scalar_one_or_none()
            if project is None:
                return None

            ws = project.wizard_state or {}
            if ws.get("subsequent_events_reviewed", False):
                return None

            return GateRuleHit(
                rule_code=self.rule_code,
                error_code=self.error_code,
                severity=self.severity,
                message="期后事项审阅尚未完成",
                location={"project_id": str(project_id)},
                suggested_action="请完成期后事项审阅",
            )
        except Exception as e:
            logger.error(f"[R7-SUBSEQUENT] check error: {e}")
            return None


class GoingConcernEvaluatedRule(GateRule):
    """持续经营已评估检查

    读取 Project.wizard_state.going_concern_evaluated，未评估则阻断。
    """
    rule_code = "R7-GOING-CONCERN"
    error_code = "GOING_CONCERN_NOT_EVALUATED"
    severity = GateSeverity.blocking

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        project_id = context.get("project_id")
        if not project_id:
            return None

        try:
            from app.models.core import Project
            result = await db.execute(
                select(Project).where(Project.id == project_id)
            )
            project = result.scalar_one_or_none()
            if project is None:
                return None

            ws = project.wizard_state or {}
            if ws.get("going_concern_evaluated", False):
                return None

            return GateRuleHit(
                rule_code=self.rule_code,
                error_code=self.error_code,
                severity=self.severity,
                message="持续经营评价尚未完成",
                location={"project_id": str(project_id)},
                suggested_action="请完成持续经营评价",
            )
        except Exception as e:
            logger.error(f"[R7-GOING-CONCERN] check error: {e}")
            return None


class MgmtRepresentationRule(GateRule):
    """管理层声明已获取检查

    读取 A16 主版本 sign_status（field_overrides）对齐 wizard_state：
    - signed → 通过（无 hit）
    - sent → warning（进行中）
    - pending/None → blocking（未开始）

    向后兼容：若 field_overrides 无 A16 数据，仍检查
    Project.wizard_state.mgmt_representation_obtained 布尔标记。
    """
    rule_code = "R7-MGMT-REP"
    error_code = "MGMT_REP_NOT_OBTAINED"
    severity = GateSeverity.blocking

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        project_id = context.get("project_id")
        if not project_id:
            return None

        try:
            from app.models.core import Project
            from app.services.field_override_service import FieldOverrideService
            from sqlalchemy import text

            result = await db.execute(
                select(Project).where(Project.id == project_id)
            )
            project = result.scalar_one_or_none()
            if project is None:
                return None

            # 获取审计年度
            year_val = 0
            if project.audit_period_end:
                year_val = project.audit_period_end.year
            else:
                try:
                    year_q = await db.execute(text(
                        "SELECT EXTRACT(YEAR FROM audit_period_end)::int "
                        "FROM projects WHERE id = :pid"
                    ), {"pid": str(project_id)})
                    year_val = year_q.scalar() or 0
                except Exception:
                    pass

            # 尝试从 field_overrides 读取 A16 主版本 sign_status
            sign_status = None
            if year_val:
                svc = FieldOverrideService(db)

                # 1. 读 selected_version
                selected_version = await svc.get(
                    project_id, year_val,
                    "word_template:A16", "selected_version", "value"
                )

                if selected_version:
                    # 2. 读该版本的 sign_status
                    scope = f"word_template:A16:{selected_version}"
                    sign_status = await svc.get(
                        project_id, year_val, scope, "sign_status", "value"
                    )

            # 若 field_overrides 有数据，按 sign_status 判定
            if sign_status is not None:
                if sign_status == "signed":
                    return None  # 已签署，通过
                elif sign_status == "sent":
                    return GateRuleHit(
                        rule_code=self.rule_code,
                        error_code="MGMT_REP_SENT_NOT_SIGNED",
                        severity=GateSeverity.warning,
                        message="管理层声明书已发出但尚未签回",
                        location={"project_id": str(project_id)},
                        suggested_action="请跟进管理层签署声明书",
                    )
                else:
                    # pending 或其他值
                    return GateRuleHit(
                        rule_code=self.rule_code,
                        error_code=self.error_code,
                        severity=self.severity,
                        message="管理层声明书尚未获取",
                        location={"project_id": str(project_id)},
                        suggested_action="请获取管理层声明书",
                    )

            # 向后兼容：无 field_overrides 数据时读 wizard_state 布尔标记
            ws = project.wizard_state or {}
            if ws.get("mgmt_representation_obtained", False):
                return None

            return GateRuleHit(
                rule_code=self.rule_code,
                error_code=self.error_code,
                severity=self.severity,
                message="管理层声明书尚未获取",
                location={"project_id": str(project_id)},
                suggested_action="请获取管理层声明书",
            )
        except Exception as e:
            logger.error(f"[R7-MGMT-REP] check error: {e}")
            return None


def register_round6_rules():
    """注册 R6 KAM + Independence + R7 期后/持续经营/管理层声明 规则到 sign_off + export_package"""
    gates = [GateType.sign_off, GateType.export_package]
    rule_registry.register_all(gates, KamConfirmedRule())
    rule_registry.register_all(gates, IndependenceConfirmedRule())
    rule_registry.register_all(gates, SubsequentEventsReviewedRule())
    rule_registry.register_all(gates, GoingConcernEvaluatedRule())
    rule_registry.register_all(gates, MgmtRepresentationRule())
    logger.info(
        "[GATE] Round 6/7 rules registered: R6-KAM, R6-INDEPENDENCE, "
        "R7-SUBSEQUENT, R7-GOING-CONCERN, R7-MGMT-REP"
    )


# 模块导入时自动注册
register_round6_rules()
