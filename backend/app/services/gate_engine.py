"""Phase 14: 统一门禁引擎

对齐 v2 WP-ENT-02 / 5.9.3 A-01
提交复核/签字/导出三入口统一走 GateEngine.evaluate()
"""
import uuid
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase14_models import GateDecision
from app.models.phase14_enums import (
    GateType, GateDecisionResult, GateSeverity, TraceEventType, TraceObjectType
)
from app.services.trace_event_service import trace_event_service, generate_trace_id

logger = logging.getLogger(__name__)


@dataclass
class GateRuleHit:
    """单条规则命中结果"""
    rule_code: str
    error_code: str
    severity: str  # blocking/warning/info
    message: str
    location: dict = field(default_factory=dict)
    suggested_action: str = ""


@dataclass
class GateEvaluateResult:
    """门禁评估结果"""
    decision: str  # allow/warn/block
    hit_rules: list = field(default_factory=list)
    trace_id: str = ""


class GateRule(ABC):
    """门禁规则基类"""
    rule_code: str = ""
    error_code: str = ""
    severity: str = "blocking"

    @abstractmethod
    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        """检查规则，命中返回 GateRuleHit，未命中返回 None"""
        ...


class RuleRegistry:
    """规则注册表"""

    def __init__(self):
        self._rules: dict[str, list[GateRule]] = {
            GateType.submit_review: [],
            GateType.sign_off: [],
            GateType.eqcr_approval: [],
            GateType.export_package: [],
        }

    def register(self, gate_type: str, rule: GateRule):
        if gate_type not in self._rules:
            self._rules[gate_type] = []
        self._rules[gate_type].append(rule)

    def register_all(self, gate_types: list[str], rule: GateRule):
        for gt in gate_types:
            self.register(gt, rule)

    def get_rules(self, gate_type: str) -> list[GateRule]:
        return self._rules.get(gate_type, [])


# 全局规则注册表
rule_registry = RuleRegistry()


class GateEngine:
    """统一门禁引擎"""

    # 幂等缓存（简单内存实现，生产可升级 Redis）
    _cache: dict[str, tuple[GateEvaluateResult, float]] = {}
    _cache_ttl = 5.0  # 秒

    def __init__(self, registry: RuleRegistry = None):
        self.registry = registry or rule_registry

    async def load_rule_config(
        self,
        db: AsyncSession,
        rule_code: str,
        threshold_key: str,
        tenant_id: Optional[uuid.UUID] = None,
    ) -> Optional[str]:
        """加载规则配置：先查租户级，再查平台级

        返回 threshold_value 字符串，由调用方自行解析。
        """
        try:
            import sqlalchemy as sa
            from app.models.phase14_models import GateRuleConfig

            # 先查租户级
            if tenant_id:
                stmt = sa.select(GateRuleConfig.threshold_value).where(
                    GateRuleConfig.rule_code == rule_code,
                    GateRuleConfig.threshold_key == threshold_key,
                    GateRuleConfig.config_level == "tenant",
                    GateRuleConfig.tenant_id == tenant_id,
                )
                result = await db.execute(stmt)
                row = result.scalar_one_or_none()
                if row is not None:
                    return row

            # 再查平台级
            stmt = sa.select(GateRuleConfig.threshold_value).where(
                GateRuleConfig.rule_code == rule_code,
                GateRuleConfig.threshold_key == threshold_key,
                GateRuleConfig.config_level == "platform",
            )
            result = await db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception:
            return None

    async def evaluate(
        self,
        db: AsyncSession,
        gate_type: str,
        project_id: uuid.UUID,
        wp_id: Optional[uuid.UUID],
        actor_id: uuid.UUID,
        context: dict,
    ) -> GateEvaluateResult:
        """统一门禁评估入口

        1. 幂等检查
        2. 加载适用规则
        3. 执行规则并按 severity 排序
        4. 生成 decision
        5. 落库 gate_decisions + trace_events
        """
        trace_id = context.get("trace_id") or generate_trace_id()

        # 幂等检查
        cache_key = f"{project_id}:{gate_type}:{trace_id}"
        now = datetime.utcnow().timestamp()
        if cache_key in self._cache:
            cached_result, cached_at = self._cache[cache_key]
            if now - cached_at < self._cache_ttl:
                return cached_result

        # 构建规则上下文
        rule_context = {
            "project_id": project_id,
            "wp_id": wp_id,
            "actor_id": actor_id,
            "gate_type": gate_type,
            **context,
        }

        # 执行规则
        rules = self.registry.get_rules(gate_type)
        hit_rules: list[GateRuleHit] = []

        for rule in rules:
            try:
                hit = await rule.check(db, rule_context)
                if hit:
                    hit_rules.append(hit)
            except Exception as e:
                logger.error(
                    f"[GATE_RULE_ERROR] rule={rule.rule_code} "
                    f"gate_type={gate_type} wp_id={wp_id} error={e}"
                )

        # 排序：blocking > warning > info
        severity_order = {
            GateSeverity.blocking: 0,
            GateSeverity.warning: 1,
            GateSeverity.info: 2,
        }
        hit_rules.sort(key=lambda h: severity_order.get(h.severity, 99))

        # 决策
        has_blocking = any(h.severity == GateSeverity.blocking for h in hit_rules)
        has_warning = any(h.severity == GateSeverity.warning for h in hit_rules)

        if has_blocking:
            decision = GateDecisionResult.block
        elif has_warning:
            decision = GateDecisionResult.warn
        else:
            decision = GateDecisionResult.allow

        result = GateEvaluateResult(
            decision=decision,
            hit_rules=hit_rules,
            trace_id=trace_id,
        )

        # 落库
        try:
            gate_decision = GateDecision(
                project_id=project_id,
                wp_id=wp_id,
                gate_type=gate_type,
                decision=decision,
                hit_rules=[
                    {
                        "rule_code": h.rule_code,
                        "error_code": h.error_code,
                        "severity": h.severity,
                        "message": h.message,
                        "location": h.location,
                        "suggested_action": h.suggested_action,
                    }
                    for h in hit_rules
                ],
                actor_id=actor_id,
                trace_id=trace_id,
            )
            db.add(gate_decision)
            # flush 以生成 gate_decision.id（trace_event 需要引用）
            await db.flush()

            # 写 trace_events
            await trace_event_service.write(
                db=db,
                project_id=project_id,
                event_type=TraceEventType.gate_evaluated,
                object_type=TraceObjectType.gate_decision,
                object_id=gate_decision.id,
                actor_id=actor_id,
                action=f"gate_evaluate:{gate_type}",
                decision=decision,
                reason_code=hit_rules[0].error_code if hit_rules else None,
                trace_id=trace_id,
            )

            await db.flush()
        except Exception as e:
            logger.error(f"[GATE_PERSIST_ERROR] trace_id={trace_id} error={e}")

        # 缓存
        self._cache[cache_key] = (result, now)

        return result


# 全局单例
gate_engine = GateEngine()
