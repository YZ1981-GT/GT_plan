"""取数公式 API 路由

- POST /api/formula/execute — 执行单个公式
- POST /api/formula/batch-execute — 批量执行公式

Validates: Requirements 2.9
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formula_management.function_support_matrix import FormulaSupportViolation

from app.core.database import get_db
from app.core.redis import get_redis
from app.deps import assert_project_permission, get_current_user, require_role
from app.models.core import User
from app.models.workpaper_schemas import FormulaRequest, FormulaResult
from app.services.formula_budget import (
    batch_seconds,
    execute_seconds,
    require_batch_size,
    run_with_deadline,
)
from app.services.formula_central_execute import (
    EXECUTOR,
    UNSUPPORTED_ERROR_CODE,
    issues_message,
    precheck,
    precheck_issues,
    unsupported_detail,
)
from app.services.formula_engine import FormulaEngine

#: ``/batch-execute`` 单次上限（需求 12.3；超过 ⇒ 422，整批不求值）
BATCH_LIMIT = 200

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
    """执行单个取数公式（中央执行合同，ADR-FHIC-19：失败 ``ok=false`` / ``value=null`` / ``errors`` 非空）"""
    # Task 5.2 / ADR-FMC-06：按 body.project_id 做项目级鉴权（此前仅 get_current_user =
    # 任意登录用户可对任意项目执行取数，坐实 IDOR）。execute 为只读取数 → readonly。
    await assert_project_permission(db, current_user, data.project_id, "readonly")
    # 预检按表达式内全部函数调用名分类（原先只查 formula_type ⇒ formula_type=TB + EVIL() 照样放行）
    try:
        precheck(_formula_of(data))
    except FormulaSupportViolation as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=unsupported_detail(exc)) from exc
    engine = FormulaEngine(redis_client=redis)
    # 执行预算（需求 12.3）：每请求一个时限，语句超时 / 整体超时 ⇒ 504 FORMULA_TIMEOUT
    result = await run_with_deadline(db, lambda: engine.execute(
        db=db,
        project_id=data.project_id,
        year=data.year,
        formula_type=data.formula_type,
        params=data.params,
    ), seconds=execute_seconds())
    return FormulaResult(**result)


@router.post("/batch-execute", response_model=list[FormulaResult])
async def batch_execute_formulas(
    data: list[FormulaRequest],
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    current_user: User = Depends(get_current_user),
):
    """批量执行取数公式（同一项目与年度、至多 ``BATCH_LIMIT`` 条，整批一个时限）"""
    if not data:
        return []

    project_id = data[0].project_id
    year = data[0].year
    await assert_project_permission(db, current_user, project_id, "readonly")
    require_batch_size(len(data), BATCH_LIMIT)

    mixed = [
        index
        for index, item in enumerate(data)
        if item.project_id != project_id or item.year != year
    ]
    if mixed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "FORMULA_BATCH_CONTEXT_MISMATCH",
                "message": "同一批公式必须属于同一项目和年度",
                "mismatched_indexes": mixed,
            },
        )

    # 预检全部条目通过才开始求值（任一条不放行 ⇒ 整批 422，逐条点名）
    support_errors = [
        {"index": index, "issues": issues}
        for index, item in enumerate(data)
        if (issues := precheck_issues(_formula_of(item)))
    ]
    if support_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": UNSUPPORTED_ERROR_CODE,
                "executor": EXECUTOR.value,
                "items": support_errors,
                "message": "；".join(f"第 {e['index'] + 1} 条{issues_message(e['issues'])}" for e in support_errors),
            },
        )

    engine = FormulaEngine(redis_client=redis)
    formulas = [
        {"formula_type": f.formula_type, "params": f.params}
        for f in data
    ]
    # 整批一个时限（FORMULA_BATCH_TIMEOUT）；超时 ⇒ 504，不返回部分结果
    results = await run_with_deadline(db, lambda: engine.batch_execute(
        db=db,
        project_id=project_id,
        year=year,
        formulas=formulas,
    ), seconds=batch_seconds())
    return [FormulaResult(**r) for r in results]


def _formula_of(item: FormulaRequest) -> str:
    """请求里的公式文本（``params.formula``，与 ``FormulaEngine.execute`` 取同一个键）。"""
    value = (item.params or {}).get("formula")
    return "" if value is None else str(value)
