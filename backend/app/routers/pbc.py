"""PBC 清单路由"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.deps import get_current_user

router = APIRouter(prefix="/projects/{project_id}/pbc", tags=["PBC清单"])

@router.get("")
async def list_pbc(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取项目 PBC 清单"""
    return []
