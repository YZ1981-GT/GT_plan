"""V3 Req 7.6：未调解跨模块冲突 ≤ 阈值守门规则

V3-CROSS-MODULE-CONFLICT-UNRESOLVED — 检查项目下是否存在 status='pending' 的
跨模块冲突记录。存在即阻断 sign_off。

模块导入时自动注册（同 gate_rules_ai_content.py 模式）。
"""
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.gate_engine import GateRule, GateRuleHit, rule_registry
from app.models.phase14_enums import GateType, GateSeverity

logger = logging.getLogger(__name__)


class CrossModuleConflictUnresolvedRule(GateRule):
    """未调解跨模块冲突守门规则

    pending 冲突数 > threshold 时阻断签字。默认阈值 0（任何 pending 都拦截）。
    后续若需放宽，可通过 context['conflict_threshold'] 注入或调整 threshold 类属性。
    """

    rule_code = "V3-CROSS-MODULE-CONFLICT-UNRESOLVED"
    error_code = "CROSS_MODULE_CONFLICT_UNRESOLVED"
    severity = GateSeverity.blocking
    threshold = 0

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        project_id = context.get("project_id")
        if not project_id:
            return None
        try:
            from app.services import conflict_resolution_service as svc

            count = await svc.count_pending(db=db, project_id=project_id)
            if count > self.threshold:
                pending = await svc.list_pending(
                    db=db, project_id=project_id, limit=5
                )
                return GateRuleHit(
                    rule_code=self.rule_code,
                    error_code=self.error_code,
                    severity=self.severity,
                    message=f"存在 {count} 段未调解的跨模块冲突，需先调解后签字",
                    location={
                        "project_id": str(project_id),
                        "pending_count": count,
                        "sample_conflict_ids": [str(c.id) for c in pending],
                    },
                    suggested_action="请打开冲突调解面板逐一调解后再签字",
                )
            return None
        except Exception as e:
            logger.error(
                f"[V3-CROSS-MODULE-CONFLICT-UNRESOLVED] check error: {e}"
            )
            return None


def register_cross_module_conflict_rules():
    """注册跨模块冲突守门规则到 sign_off 门禁。"""
    rule_registry.register_all(
        [GateType.sign_off], CrossModuleConflictUnresolvedRule()
    )
    logger.info(
        "[GATE] V3 cross_module_conflict rule "
        "V3-CROSS-MODULE-CONFLICT-UNRESOLVED registered to sign_off"
    )


# 模块导入时自动注册
register_cross_module_conflict_rules()
