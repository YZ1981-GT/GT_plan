"""函证管理路由"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.deps import get_current_user

router = APIRouter(prefix="/projects/{project_id}/confirmations", tags=["函证管理"])

@router.get("")
async def list_confirmations(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取项目函证列表"""
    return {
        "status": "developing",
        "items": [],
        "note": "Feature not implemented; scheduled for R7+",
    }
