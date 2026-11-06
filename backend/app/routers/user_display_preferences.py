"""账号级显示偏好路由。

GET/PATCH /api/users/me/display-preferences
- 无 userId 路径参数，只操作当前登录用户
- service 只 flush，router 是唯一 commit/rollback 层
- 日志只记 user_id、revision 和错误类别

design §2、§15 A4。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.schemas.display_preferences import (
    DisplayPreferencesPatch,
    DisplayPreferencesResponse,
)
from app.services.user_display_preferences_service import (
    DisplayPrefsRevisionConflict,
    get_preferences,
    patch_preferences,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/users/me/display-preferences",
    tags=["display-preferences"],
)


@router.get("", response_model=DisplayPreferencesResponse)
async def get_display_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DisplayPreferencesResponse:
    """获取当前账号的显示偏好。

    无记录时返回平台默认值，不写库。
    """
    return await get_preferences(db, str(current_user.id))


@router.patch("", response_model=DisplayPreferencesResponse)
async def patch_display_preferences(
    body: DisplayPreferencesPatch,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DisplayPreferencesResponse:
    """部分更新当前账号的显示偏好。

    使用 base_revision 乐观锁；409 时返回服务端当前值。
    成功返回完整归一结果。
    """
    try:
        result, changed_fields = await patch_preferences(
            db, str(current_user.id), body,
        )
        # 把 changed_fields 写入 request.state 供审计日志脱敏用
        request.state.audit_changed_fields = changed_fields
        await db.commit()
        return result

    except DisplayPrefsRevisionConflict as e:
        await db.rollback()
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=409,
            content={
                "code": "DISPLAY_PREFS_REVISION_CONFLICT",
                "message": "偏好版本冲突，请使用最新版本重试",
                "current": e.current.model_dump(mode="json"),
            },
        )
    except Exception:
        await db.rollback()
        logger.exception(
            "display-preferences PATCH failed for user=%s",
            current_user.id,
        )
        raise
