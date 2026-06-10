"""功能开关 API (DEPRECATED — 请迁移到 /api/feature-flags-v2，DB-backed 版本)"""

import logging
from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.services.feature_flags import is_enabled, set_project_flag, get_all_flags, get_feature_maturity
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feature-flags", tags=["feature-flags (deprecated)"])


class SetFlagRequest(BaseModel):
    flag: str
    enabled: bool


@router.get("")
async def list_flags(project_id: UUID | None = None):
    """获取所有功能开关状态（已废弃，请迁移到 /api/feature-flags-v2）"""
    logger.warning("[DEPRECATED] /api/feature-flags called — migrate to /api/feature-flags-v2")
    return {
        "flags": get_all_flags(project_id),
        "maturity": get_feature_maturity(),
    }


@router.get("/check/{flag}")
async def check_flag(flag: str, project_id: UUID | None = None):
    """检查单个功能是否启用（已废弃，请迁移到 /api/feature-flags-v2）"""
    logger.warning("[DEPRECATED] /api/feature-flags/check/%s called — migrate to /api/feature-flags-v2", flag)
    return {"flag": flag, "enabled": is_enabled(flag, project_id)}


@router.get("/maturity")
async def get_maturity():
    """获取所有功能成熟度分级（已废弃，请迁移到 /api/feature-flags-v2）"""
    logger.warning("[DEPRECATED] /api/feature-flags/maturity called — migrate to /api/feature-flags-v2")
    return get_feature_maturity()


@router.put("/projects/{project_id}")
async def set_flag(
    project_id: UUID,
    req: SetFlagRequest,
    current_user: User = Depends(get_current_user),
):
    """设置项目级功能开关（已废弃，请迁移到 /api/feature-flags-v2）"""
    logger.warning("[DEPRECATED] /api/feature-flags/projects/%s called — migrate to /api/feature-flags-v2", project_id)
    if current_user.role.value not in ("admin", "partner", "manager"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="权限不足")
    set_project_flag(project_id, req.flag, req.enabled)
    return {"project_id": str(project_id), "flag": req.flag, "enabled": req.enabled}
