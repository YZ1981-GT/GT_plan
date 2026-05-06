"""Phase 14: 统一门禁评估路由

对齐 v2 5.9.3 A-01: POST /api/gate/evaluate
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.gate_engine import gate_engine, GateRuleHit
from app.models.phase14_enums import GateType, GateDecisionResult

router = APIRouter(prefix="/gate", tags=["GateEngine"])


class GateEvaluateRequest(BaseModel):
    gate_type: str = Field(..., description="submit_review|sign_off|export_package")
    project_id: uuid.UUID
    wp_id: Optional[uuid.UUID] = None
    actor_id: uuid.UUID
    context: dict = Field(default_factory=dict)


class GateRuleHitResponse(BaseModel):
    rule_code: str
    error_code: str
    severity: str
    message: str
    location: dict = {}
    suggested_action: str = ""


class GateEvaluateResponse(BaseModel):
    decision: str
    hit_rules: list[GateRuleHitResponse] = []
    trace_id: str


@router.post("/evaluate", response_model=GateEvaluateResponse)
async def evaluate_gate(
    req: GateEvaluateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """统一门禁评估入口

    三入口（提交复核/签字/导出）统一调用此接口。
    返回 decision=block 时，前端应展开阻断面板。
    """
    if req.gate_type not in [gt.value for gt in GateType]:
        raise HTTPException(status_code=400, detail={
            "error_code": "GATE_CONTEXT_INVALID",
            "message": f"无效的 gate_type: {req.gate_type}",
            "trace_id": "",
        })

    result = await gate_engine.evaluate(
        db=db,
        gate_type=req.gate_type,
        project_id=req.project_id,
        wp_id=req.wp_id,
        actor_id=req.actor_id,
        context=req.context,
    )

    response = GateEvaluateResponse(
        decision=result.decision,
        hit_rules=[
            GateRuleHitResponse(
                rule_code=h.rule_code,
                error_code=h.error_code,
                severity=h.severity,
                message=h.message,
                location=h.location,
                suggested_action=h.suggested_action,
            )
            for h in result.hit_rules
        ],
        trace_id=result.trace_id,
    )

    if result.decision == GateDecisionResult.block:
        raise HTTPException(status_code=409, detail=response.model_dump())

    return response


# ── 规则配置分层 API ──────────────────────────────────────────

class RuleConfigResponse(BaseModel):
    rule_code: str
    config_level: str
    threshold_key: str
    threshold_value: str
    tenant_id: Optional[uuid.UUID] = None
    description: Optional[str] = None


@router.get("/rules")
async def list_gate_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询当前生效的门禁规则配置"""
    from app.models.phase14_models import GateRuleConfig
    import sqlalchemy as sa

    stmt = sa.select(GateRuleConfig).order_by(GateRuleConfig.rule_code, GateRuleConfig.config_level)
    result = await db.execute(stmt)
    configs = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "rule_code": c.rule_code,
            "config_level": c.config_level,
            "threshold_key": c.threshold_key,
            "threshold_value": c.threshold_value,
            "tenant_id": str(c.tenant_id) if c.tenant_id else None,
            "description": c.description,
        }
        for c in configs
    ]


class RuleConfigUpdateRequest(BaseModel):
    threshold_value: str
    description: Optional[str] = None


@router.put("/rules/{rule_code}")
async def update_gate_rule_config(
    rule_code: str,
    req: RuleConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """修改租户级规则阈值（平台级不可修改）"""
    from app.models.phase14_models import GateRuleConfig
    import sqlalchemy as sa

    stmt = sa.select(GateRuleConfig).where(
        GateRuleConfig.rule_code == rule_code,
        GateRuleConfig.config_level == "tenant",
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail=f"租户级配置 {rule_code} 不存在")

    config.threshold_value = req.threshold_value
    if req.description:
        config.description = req.description
    config.updated_by = current_user.id
    from datetime import datetime, timezone
    config.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.commit()
    return {"status": "updated", "rule_code": rule_code}
