"""审计类型扩展 API 路由

- GET /api/audit-types                       — 审计类型列表
- GET /api/audit-types/{type}/recommendation — 审计类型推荐配置

Validates: Requirements 5.1-5.2
"""

from __future__ import annotations

from app.deps import get_current_user
from app.models.core import User
from fastapi import APIRouter, HTTPException

from app.services.audit_type_service import AuditTypeService

router = APIRouter(tags=["audit-types"])


@router.get("/api/audit-types")
async def list_audit_types():
    """审计类型列表"""
    svc = AuditTypeService()
    return svc.get_audit_types()


@router.get("/api/audit-types/{audit_type}/recommendation")
async def get_type_recommendation(audit_type: str):
    """审计类型推荐配置"""
    svc = AuditTypeService()
    try:
        return svc.get_type_recommendation(audit_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
