"""底稿依赖关系 API

GET /api/projects/{id}/workpapers/{wp_id}/dependencies — 检查前置依赖状态
GET /api/wp-dependencies/cycle/{cycle}                  — 获取循环依赖图
GET /api/wp-dependencies/generation-order                — 获取生成顺序
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.wp_dependency_service import (
    check_dependencies, get_cycle_dependency_graph,
    get_generation_order, CYCLE_DEPENDENCIES, CONTROL_EFFECTIVENESS_IMPACT,
)

router = APIRouter(tags=["底稿依赖"])


@router.get("/api/projects/{project_id}/workpapers/{wp_id}/dependencies")
async def get_wp_dependencies(
    project_id: UUID,
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    """检查底稿的前置依赖是否已完成

    返回B类/C类依赖状态、控制测试结论、对实质性程序范围的影响建议。
    """
    # 获取底稿编号
    result = await db.execute(
        sa.select(WpIndex.wp_code)
        .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
        .where(WorkingPaper.id == wp_id, WorkingPaper.is_deleted == sa.false())
    )
    wp_code = result.scalar_one_or_none()
    if not wp_code:
        return {"wp_code": "", "dependencies": [], "all_satisfied": True, "warnings": []}

    return await check_dependencies(db, project_id, wp_code)


@router.get("/api/wp-dependencies/cycle/{cycle}")
async def get_cycle_graph(
    cycle: str,
    _user=Depends(get_current_user),
):
    """获取循环的B→C→D依赖关系图（供前端可视化）"""
    return get_cycle_dependency_graph(cycle)


@router.get("/api/wp-dependencies/cycles")
async def list_all_cycles(_user=Depends(get_current_user)):
    """列出所有循环的依赖定义"""
    return {
        cycle: {
            "description": dep.get("description", ""),
            "b_controls": dep.get("b_controls", []),
            "c_tests": dep.get("c_tests", []),
        }
        for cycle, dep in CYCLE_DEPENDENCIES.items()
    }


@router.get("/api/wp-dependencies/effectiveness-impact")
async def get_effectiveness_impact(_user=Depends(get_current_user)):
    """获取控制测试结论对实质性程序的影响定义"""
    return CONTROL_EFFECTIVENESS_IMPACT


@router.post("/api/wp-dependencies/generation-order")
async def get_order(
    body: dict,
    _user=Depends(get_current_user),
):
    """按B→C→D-N→A顺序排列底稿编码"""
    codes = body.get("wp_codes", [])
    return {"ordered": get_generation_order(codes)}
