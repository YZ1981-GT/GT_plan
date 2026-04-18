"""功能开关 API"""

from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.services.feature_flags import is_enabled, set_project_flag, get_all_flags, get_feature_maturity
from app.deps import get_current_user
from app.models.core import User

router = APIRouter(prefix="/api/feature-flags", tags=["feature-flags"])


class SetFlagRequest(BaseModel):
    flag: str
    enabled: bool


@router.get("")
async def list_flags(project_id: UUID | None = None):
    """获取所有功能开关状态"""
    return {
        "flags": get_all_flags(project_id),
        "maturity": get_feature_maturity(),
    }


@router.get("/check/{flag}")
async def check_flag(flag: str, project_id: UUID | None = None):
    """检查单个功能是否启用"""
    return {"flag": flag, "enabled": is_enabled(flag, project_id)}


@router.get("/maturity")
async def get_maturity():
    """获取所有功能成熟度分级"""
    return get_feature_maturity()


@router.put("/projects/{project_id}")
async def set_flag(
    project_id: UUID,
    req: SetFlagRequest,
    current_user: User = Depends(get_current_user),
):
    """设置项目级功能开关（仅项目经理/合伙人/管理员）"""
    if current_user.role.value not in ("admin", "partner", "manager"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="权限不足")
    set_project_flag(project_id, req.flag, req.enabled)
    return {"project_id": str(project_id), "flag": req.flag, "enabled": req.enabled}
