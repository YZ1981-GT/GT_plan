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
async def list_all_functions(redis=Depends(get_redis)):
    """列出所有可用函数（内置 + 自定义）"""
    engine = FormulaEngine(redis_client=redis)
    return engine.list_all_functions()


@router.get("/custom-functions")
async def list_custom_functions(redis=Depends(get_redis)):
    """列出所有自定义函数"""
    engine = FormulaEngine(redis_client=redis)
    return engine.list_custom_functions()


@router.post("/custom-functions")
async def register_custom_function(
    body: RegisterFunctionRequest,
    redis=Depends(get_redis),
):
    """注册自定义公式函数"""
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
async def unregister_custom_function(name: str, redis=Depends(get_redis)):
    """注销自定义函数"""
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
):
    """执行单个取数公式"""
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
