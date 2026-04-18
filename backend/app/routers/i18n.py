"""多语言支持 API 路由

- GET /api/i18n/languages              — 支持的语言列表
- GET /api/i18n/translations/{lang}    — 翻译字典
- GET /api/i18n/audit-terms/{lang}     — 审计术语翻译
- PUT /api/users/{user_id}/language    — 设置用户语言

Validates: Requirements 4.1-4.4
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.i18n_service import I18nService

router = APIRouter(tags=["i18n"])


class SetLanguageRequest(BaseModel):
    language: str


@router.get("/api/i18n/languages")
async def get_languages():
    """支持的语言列表"""
    svc = I18nService()
    return svc.get_languages()


@router.get("/api/i18n/translations/{lang}")
async def get_translations(lang: str):
    """翻译字典"""
    svc = I18nService()
    try:
        return svc.get_translations(lang)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/i18n/audit-terms/{lang}")
async def get_audit_terms(lang: str):
    """审计术语翻译"""
    svc = I18nService()
    try:
        return svc.get_audit_terms(lang)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/api/users/{user_id}/language")
async def set_user_language(
    user_id: UUID,
    body: SetLanguageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """设置用户语言偏好"""
    svc = I18nService()
    try:
        result = await svc.set_user_language(db, user_id, body.language)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
