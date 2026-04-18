"""电子签名 API 路由

- POST /api/signatures/sign                       — 签署文档
- GET  /api/signatures/{object_type}/{object_id}   — 签名记录
- POST /api/signatures/{signature_id}/verify       — 验证签名
- POST /api/signatures/{signature_id}/revoke       — 撤销签名

Validates: Requirements 7.1-7.4
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.sign_service import SignService

router = APIRouter(tags=["signatures"])


class SignRequest(BaseModel):
    object_type: str
    object_id: UUID
    signer_id: UUID
    signature_level: str
    signature_data: dict | None = None
    ip_address: str | None = None


@router.post("/api/signatures/sign")
async def sign_document(body: SignRequest, db: AsyncSession = Depends(get_db)):
    """签署文档"""
    svc = SignService()
    try:
        result = await svc.sign_document(
            db,
            object_type=body.object_type,
            object_id=body.object_id,
            signer_id=body.signer_id,
            level=body.signature_level,
            signature_data=body.signature_data,
            ip_address=body.ip_address,
        )
        await db.commit()
        return result
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/signatures/{object_type}/{object_id}")
async def get_signatures(
    object_type: str, object_id: UUID, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取签名记录"""
    svc = SignService()
    return await svc.get_signatures(db, object_type, object_id)


@router.post("/api/signatures/{signature_id}/verify")
async def verify_signature(
    signature_id: UUID, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """验证签名"""
    svc = SignService()
    try:
        return await svc.verify_signature(db, signature_id)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/signatures/{signature_id}/revoke")
async def revoke_signature(
    signature_id: UUID, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """撤销签名"""
    svc = SignService()
    try:
        result = await svc.revoke_signature(db, signature_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
