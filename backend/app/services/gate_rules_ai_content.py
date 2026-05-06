"""R3 Sprint 4: AI 内容统一结构化门禁规则

AIContentMustBeConfirmedRule — 检查项目底稿中是否存在未确认的 AI 生成内容。
注册到 sign_off 门禁入口，阻断含未确认 AI 内容的签字操作。

模块导入时自动注册（同 gate_rules_round6.py 模式）。
"""
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.gate_engine import GateRule, GateRuleHit, rule_registry
from app.models.phase14_enums import GateType, GateSeverity

logger = logging.getLogger(__name__)


class AIContentMustBeConfirmedRule(GateRule):
    """AI 内容确认检查

    扫描项目所有底稿的 parsed_data，查找 type='ai_generated' 且
    confirmed_by=null 的单元格/字段。存在未确认内容则阻断 sign_off。
    """

    rule_code = "R3-AI-UNCONFIRMED"
    error_code = "AI_CONTENT_NOT_CONFIRMED"
    severity = GateSeverity.blocking

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        project_id = context.get("project_id")
        if not project_id:
            return None

        try:
            from app.models.workpaper_models import WorkingPaper

            stmt = select(WorkingPaper).where(
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == False,  # noqa: E712
                WorkingPaper.parsed_data.isnot(None),
            )
            result = await db.execute(stmt)
            workpapers = result.scalars().all()

            unconfirmed_wps: list[str] = []

            for wp in workpapers:
                if self._has_unconfirmed_ai_content(wp.parsed_data):
                    unconfirmed_wps.append(str(wp.id))

            if not unconfirmed_wps:
                return None

            return GateRuleHit(
                rule_code=self.rule_code,
                error_code=self.error_code,
                severity=self.severity,
                message="存在未确认的AI生成内容",
                location={
                    "project_id": str(project_id),
                    "section": "ai_content",
                    "unconfirmed_wp_count": len(unconfirmed_wps),
                    "sample_wp_ids": unconfirmed_wps[:5],
                },
                suggested_action="请逐一确认或拒绝底稿中的 AI 生成内容后再签字",
            )
        except Exception as e:
            logger.error(f"[R3-AI-UNCONFIRMED] check error: {e}")
            return None

    def _has_unconfirmed_ai_content(self, parsed_data: dict) -> bool:
        """递归检查 parsed_data 中是否存在未确认的 AI 生成内容。

        检查逻辑：
        1. 顶层字段如果是 dict 且 type='ai_generated' + confirmed_by=None → 命中
        2. cells 列表中的每个 cell 如果是 dict 且 type='ai_generated' + confirmed_by=None → 命中
        3. 递归检查所有嵌套 dict/list 结构
        """
        if not isinstance(parsed_data, dict):
            return False
        return self._scan_value(parsed_data)

    def _scan_value(self, value) -> bool:
        """递归扫描值，查找未确认的 AI 内容节点。"""
        if isinstance(value, dict):
            # 检查当前 dict 是否是 ai_generated 节点
            if value.get("type") == "ai_generated":
                if value.get("confirmed_by") is None:
                    return True
            # 递归检查所有子值
            for v in value.values():
                if self._scan_value(v):
                    return True
        elif isinstance(value, list):
            for item in value:
                if self._scan_value(item):
                    return True
        return False


def register_ai_content_rules():
    """注册 AI 内容确认规则到 sign_off 门禁"""
    rule_registry.register_all([GateType.sign_off], AIContentMustBeConfirmedRule())
    logger.info("[GATE] R3 AI content rule R3-AI-UNCONFIRMED registered to sign_off")


# 模块导入时自动注册
register_ai_content_rules()
