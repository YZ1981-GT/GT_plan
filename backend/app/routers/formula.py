"""取数公式 API 路由

- POST /api/formula/execute — 执行单个公式
- POST /api/formula/batch-execute — 批量执行公式

Validates: Requirements 2.9
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.deps import assert_project_permission, get_current_user, require_role
from app.models.core import User
from app.models.workpaper_schemas import FormulaRequest, FormulaResult
from app.services.formula_engine import FormulaEngine

router = APIRouter(
    prefix="/api/formula",
    tags=["formula"],
)


# ── 自定义函数管理（Task 6.4） ──

from pydantic import BaseModel


class RegisterFunctionRequest(BaseModel):
    name: str
    expression: str
    description: str = ""
    param_names: list[str] = []


@router.get("/functions")
async def list_all_functions(redis=Depends(get_redis), current_user: User = Depends(get_current_user)):
    """列出所有可用函数（内置 + 自定义）"""
    engine = FormulaEngine(redis_client=redis)
    return engine.list_all_functions()


@router.get("/custom-functions")
async def list_custom_functions(redis=Depends(get_redis), current_user: User = Depends(get_current_user)):
    """列出所有自定义函数"""
    engine = FormulaEngine(redis_client=redis)
    return engine.list_custom_functions()


@router.post("/custom-functions")
async def register_custom_function(
    body: RegisterFunctionRequest,
    redis=Depends(get_redis),
    # Task 5.3 / ADR-FMC-06：自定义函数是**全局**能力（注册后对所有项目/用户生效，
    # FormulaEngine 的自定义函数表无项目维度）。此前仅 `get_current_user` =
    # 任意登录用户可注册/篡改全局函数、污染所有项目取数 → 坐实「全局写无 admin 门控」。
    # 收紧为 admin-only：非 admin 注册返回 403（require_role 内层 get_current_user 判角色）。
    current_user: User = Depends(require_role(["admin"])),
):
    """注册自定义公式函数（全局能力，限 admin）"""
    engine = FormulaEngine(redis_client=redis)
    try:
        return engine.register_custom_function(
            name=body.name,
            expression=body.expression,
            description=body.description,
            param_names=body.param_names,
        )
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/custom-functions/{name}")
async def unregister_custom_function(
    name: str,
    redis=Depends(get_redis),
    # Task 5.3 / ADR-FMC-06：注销同注册，全局写操作限 admin（见上）。
    current_user: User = Depends(require_role(["admin"])),
):
    """注销自定义函数（全局能力，限 admin）"""
    engine = FormulaEngine(redis_client=redis)
    removed = engine.unregister_custom_function(name)
    if not removed:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"自定义函数 '{name}' 不存在")
    return {"name": name, "removed": True}


@router.post("/execute", response_model=FormulaResult)
async def execute_formula(
    data: FormulaRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    current_user: User = Depends(get_current_user),
):
    """执行单个取数公式"""
    # Task 5.2 / ADR-FMC-06：按 body.project_id 做项目级鉴权（此前仅 get_current_user =
    # 任意登录用户可对任意项目执行取数，坐实 IDOR）。execute 为只读取数 → readonly。
    await assert_project_permission(db, current_user, data.project_id, "readonly")
    engine = FormulaEngine(redis_client=redis)
    result = await engine.execute(
        db=db,
        project_id=data.project_id,
        year=data.year,
        formula_type=data.formula_type,
        params=data.params,
    )
    return FormulaResult(**result)


@router.post("/batch-execute", response_model=list[FormulaResult])
async def batch_execute_formulas(
    data: list[FormulaRequest],
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    current_user: User = Depends(get_current_user),
):
    """批量执行取数公式"""
    if not data:
        return []

    # All formulas in a batch should share project_id and year
    # Use the first item's project_id and year
    project_id = data[0].project_id
    year = data[0].year

    engine = FormulaEngine(redis_client=redis)
    formulas = [
        {"formula_type": f.formula_type, "params": f.params}
        for f in data
    ]
    results = await engine.batch_execute(
        db=db,
        project_id=project_id,
        year=year,
        formulas=formulas,
    )
    return [FormulaResult(**r) for r in results]
