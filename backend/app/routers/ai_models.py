"""AI 模型配置管理 API

- GET    /api/ai-models              — 模型列表
- POST   /api/ai-models              — 新增模型
- PUT    /api/ai-models/{id}         — 更新模型
- DELETE /api/ai-models/{id}         — 删除模型（软删除）
- POST   /api/ai-models/{id}/activate — 激活模型
- GET    /api/ai-models/health       — AI 引擎健康检查
- POST   /api/ai-models/seed         — 初始化默认模型
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.ai_models import AIModelConfig, AIModelType, AIProvider
from app.services.ai_service import AIService, ModelNotFoundError

router = APIRouter(prefix="/api/ai-models", tags=["ai-models"])


# ── Request / Response ──


class ModelCreate(BaseModel):
    model_name: str = Field(..., min_length=1, max_length=100)
    model_type: AIModelType
    provider: AIProvider
    endpoint_url: str | None = None
    is_active: bool = False
    context_window: int | None = None
    performance_notes: str | None = None


class ModelUpdate(BaseModel):
    model_name: str | None = None
    endpoint_url: str | None = None
    is_active: bool | None = None
    context_window: int | None = None
    performance_notes: str | None = None


class ActivateRequest(BaseModel):
    model_type: AIModelType


# ── Endpoints ──


@router.get("")
async def list_models(
    model_type: AIModelType | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """模型列表（可按类型筛选）"""
    svc = AIService(db)
    models = await svc.get_all_models()
    if model_type:
        models = [m for m in models if m.model_type == model_type]
    return [_to_dict(m) for m in models]


@router.post("")
async def create_model(body: ModelCreate, db: AsyncSession = Depends(get_db)):
    """新增模型配置"""
    # 检查重复
    result = await db.execute(
        select(AIModelConfig).where(
            AIModelConfig.model_name == body.model_name,
            AIModelConfig.model_type == body.model_type,
            AIModelConfig.is_deleted == False,  # noqa: E712
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(400, f"模型已存在: {body.model_name} ({body.model_type.value})")

    model = AIModelConfig(**body.model_dump())
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return _to_dict(model)


@router.put("/{model_id}")
async def update_model(
    model_id: UUID,
    body: ModelUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新模型配置"""
    model = await _get_model(db, model_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(model, k, v)
    await db.commit()
    await db.refresh(model)
    return _to_dict(model)


@router.delete("/{model_id}")
async def delete_model(model_id: UUID, db: AsyncSession = Depends(get_db)):
    """软删除模型"""
    model = await _get_model(db, model_id)
    model.is_deleted = True
    model.is_active = False
    await db.commit()
    return {"message": "已删除"}


@router.post("/{model_id}/activate")
async def activate_model(model_id: UUID, db: AsyncSession = Depends(get_db)):
    """激活模型（同类型其他模型自动停用）"""
    model = await _get_model(db, model_id)
    svc = AIService(db)
    try:
        ok = await svc.switch_model(model.model_name, model.model_type)
    except ModelNotFoundError as e:
        raise HTTPException(404, str(e))
    if not ok:
        raise HTTPException(400, "模型验证失败，请检查服务是否可用")
    return {"message": "已激活", "model_name": model.model_name}


@router.get("/health")
async def ai_health(db: AsyncSession = Depends(get_db)):
    """AI 引擎健康检查"""
    svc = AIService(db)
    return await svc.health_check()


@router.post("/seed")
async def seed_models(db: AsyncSession = Depends(get_db)):
    """初始化默认模型（幂等）"""
    await AIService.init_default_models(db)
    return {"message": "默认模型已初始化"}


# ── Helpers ──


async def _get_model(db: AsyncSession, model_id: UUID) -> AIModelConfig:
    result = await db.execute(
        select(AIModelConfig).where(
            AIModelConfig.id == model_id,
            AIModelConfig.is_deleted == False,  # noqa: E712
        )
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, "模型不存在")
    return model


def _to_dict(m: AIModelConfig) -> dict:
    return {
        "id": str(m.id),
        "model_name": m.model_name,
        "model_type": m.model_type.value if m.model_type else None,
        "provider": m.provider.value if m.provider else None,
        "endpoint_url": m.endpoint_url,
        "is_active": m.is_active,
        "context_window": m.context_window,
        "performance_notes": m.performance_notes,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }
