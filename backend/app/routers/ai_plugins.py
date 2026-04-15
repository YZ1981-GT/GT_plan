"""AI能力预留接口 API 路由

- GET  /api/ai-plugins                      — 插件列表
- GET  /api/ai-plugins/presets               — 预设插件列表
- GET  /api/ai-plugins/{plugin_id}           — 插件详情
- POST /api/ai-plugins                       — 注册插件
- POST /api/ai-plugins/seed                  — 加载预设插件
- POST /api/ai-plugins/{plugin_id}/enable    — 启用插件
- POST /api/ai-plugins/{plugin_id}/disable   — 禁用插件
- PUT  /api/ai-plugins/{plugin_id}/config    — 更新配置

Validates: Requirements 13.1-13.8
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.ai_plugin_service import AIPluginService
from app.services.unified_ai_service import UnifiedAIService

router = APIRouter(tags=["ai-plugins"])


class RegisterPluginRequest(BaseModel):
    plugin_id: str
    plugin_name: str
    plugin_version: str
    description: str | None = None
    config: dict | None = None


class UpdateConfigRequest(BaseModel):
    config: dict


def _get_unified(db: AsyncSession = Depends(get_db)) -> UnifiedAIService:
    return UnifiedAIService(db)


@router.get("/api/ai-plugins")
async def list_plugins(svc: UnifiedAIService = Depends(_get_unified)):
    """插件列表"""
    return await svc.list_plugins()


@router.get("/api/ai-plugins/presets")
async def get_preset_plugins():
    """预设插件列表"""
    svc = AIPluginService()
    return svc.get_preset_plugins()


@router.get("/api/ai-plugins/{plugin_id}")
async def get_plugin(plugin_id: str, db: AsyncSession = Depends(get_db)):
    """插件详情"""
    svc = AIPluginService()
    result = await svc.get_plugin(db, plugin_id)
    if result is None:
        raise HTTPException(status_code=404, detail="插件不存在")
    return result


@router.post("/api/ai-plugins")
async def register_plugin(
    body: RegisterPluginRequest, db: AsyncSession = Depends(get_db)
):
    """注册插件"""
    svc = AIPluginService()
    try:
        result = await svc.register_plugin(
            db,
            plugin_id=body.plugin_id,
            plugin_name=body.plugin_name,
            plugin_version=body.plugin_version,
            description=body.description,
            config=body.config,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/ai-plugins/seed")
async def load_preset_plugins(db: AsyncSession = Depends(get_db)):
    """加载预设插件（幂等）"""
    svc = AIPluginService()
    result = await svc.load_preset_plugins(db)
    await db.commit()
    return result


@router.post("/api/ai-plugins/{plugin_id}/enable")
async def enable_plugin(plugin_id: str, svc: UnifiedAIService = Depends(_get_unified)):
    """启用插件"""
    try:
        return await svc.enable_plugin(plugin_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/ai-plugins/{plugin_id}/disable")
async def disable_plugin(plugin_id: str, svc: UnifiedAIService = Depends(_get_unified)):
    """禁用插件"""
    try:
        return await svc.disable_plugin(plugin_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/api/ai-plugins/{plugin_id}/config")
async def update_config(
    plugin_id: str,
    body: UpdateConfigRequest,
    db: AsyncSession = Depends(get_db),
):
    """更新插件配置"""
    svc = AIPluginService()
    try:
        result = await svc.update_config(db, plugin_id, body.config)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
