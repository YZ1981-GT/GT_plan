"""项目级账龄配置路由（AgingConfigService 增强版）

端点:
  GET  /api/projects/{project_id}/aging/config  — 获取项目账龄配置
  PUT  /api/projects/{project_id}/aging/config  — 保存项目账龄配置（含校验→422）
  GET  /api/aging/presets                       — 获取预定义账龄段列表

Requirements: 2.1, 2.2, 2.3, 2.4
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.aging_config_service import (
    PRESET_SEGMENTS,
    AgingConfigPayload,
    AgingConfigResponse,
    AgingPreset,
    get_config,
    save_config,
    validate_config,
)

router = APIRouter(prefix="/api", tags=["aging-config"])


@router.get("/projects/{project_id}/aging/config")
async def get_aging_config(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AgingConfigResponse:
    """获取项目级账龄配置。

    若项目无配置，返回默认值（FIVE_YEAR preset）。

    Requirements: 2.1, 2.5
    """
    return await get_config(project_id, db)


@router.put("/projects/{project_id}/aging/config")
async def put_aging_config(
    project_id: UUID,
    payload: AgingConfigPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AgingConfigResponse:
    """保存项目级账龄配置。

    校验规则（任一失败→HTTP 422）：
    - CUSTOM 预设时段数必须在 2-10 之间
    - 所有段名不可为空
    - 所有段名不可重复

    Requirements: 2.2, 2.3
    """
    errors = validate_config(payload)
    if errors:
        # 取第一个错误解析 error_code 和 detail
        first = errors[0]
        if ":" in first:
            error_code, detail = first.split(":", 1)
        else:
            error_code, detail = "VALIDATION_ERROR", first
        raise HTTPException(
            status_code=422,
            detail={"error_code": error_code, "detail": detail},
        )

    result = await save_config(project_id, payload, db)
    await db.commit()

    # 配置变更后广播轻量 SSE 通知，让在线客户端刷新账龄列定义。
    # 走 broadcast_raw（纯 SSE，不触发 _handlers / 不入 debounce），
    # 与 annotations/attachments/consol 等通知链路保持一致。
    # 无 event_bus / 无 event loop 时静默回退，不阻断保存。
    try:
        from app.services.event_bus import event_bus

        event_bus.broadcast_raw(
            "aging-config:changed",
            {
                "project_id": str(project_id),
                "preset": result.preset.value,
            },
        )
    except Exception:
        pass

    return result


@router.get("/aging/presets")
async def get_aging_presets(
    current_user: User = Depends(get_current_user),
) -> dict:
    """获取预定义账龄段列表。

    返回 THREE_YEAR 和 FIVE_YEAR 的段定义。

    Requirements: 2.4
    """
    return {
        "presets": {
            preset.value: [seg.model_dump() for seg in segments]
            for preset, segments in PRESET_SEGMENTS.items()
        }
    }
