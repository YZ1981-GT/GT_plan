"""坏账准备明细表 D2-3 嵌套子表 API 路由（bad_debt_rows）

对应 design.md「Components and Interfaces #5 Router」与 requirements Req 8。

前缀：/api/workpapers/{wp_id}/bad-debt-rows
路径参数 wp_id 同时接受 working_paper.id 与 wp_index_id：
  各端点入口调用 resolve_wp_index_id(db, wp_id) 归一为 wp_index_id 再传给 service。
  - 前端 GtBadDebtSheet 经 GtWpRenderer 传来的是 working_paper.id → 解析为 wp_index_id；
  - 直接调 API / 现有测试传 wp_index_id → 解析查不到 working_paper 时回退原值。

铁律：
- service 只 flush 不 commit；本 router 在写操作成功后统一 await db.commit()。
- 路由顺序：静态路径段端点（provision-methods/prefill/aje-suggestion/serialize/
  deserialize/parents）必须声明在 `/{row_id}` 通配端点之前，否则通配截获静态路径
  导致 422 UUID parse error。`/{parent_id}/children` 同理放在 `/{row_id}` 之前。
- 错误映射：
    DuplicateProvisionMethodError → 409
    OptimisticLockError           → 409
    HierarchyError                → 400
    RowNotFoundError              → 404
    deserialize 校验错误列表       → 422
    prefill no-op                 → 200

Requirements: 1.4, 8.2, 8.3, 8.5, 10.5
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.bad_debt_models import PROVISION_METHOD_LABELS, ProvisionMethod
from app.models.core import User
from app.schemas.bad_debt_schemas import (
    BadDebtTreeResponse,
    ChildRowResponse,
    CreateChildRowDTO,
    CreateParentRowDTO,
    ParentRowResponse,
    RowAmounts,
    UpdateRowDTO,
)
from app.services.bad_debt_aje_generator import AjeSuggestion, BadDebtAjeGenerator
from app.services.bad_debt_nested_table_service import (
    DuplicateProvisionMethodError,
    HierarchyError,
    NestedTableService,
    OptimisticLockError,
    RowNotFoundError,
    resolve_wp_index_id,
)
from app.services.bad_debt_prefill_service import BadDebtPrefillService, PrefillResult

router = APIRouter(
    prefix="/api/workpapers/{wp_id}/bad-debt-rows",
    tags=["bad-debt-rows"],
)


# ─── 辅助请求/响应模型 ───────────────────────────────────────────────────────


class ProvisionMethodItem(BaseModel):
    """枚举值 + 中文显示名。"""

    value: str
    label: str


class PrefillRequest(BaseModel):
    """预填请求体：project_id + year（也可经 query 传入）。"""

    project_id: UUID
    year: int


# ─────────────────────────────────────────────────────────────────────────────
# 静态路径端点（必须在 /{row_id} 通配之前声明）
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/provision-methods", response_model=list[ProvisionMethodItem])
async def list_provision_methods(
    wp_id: UUID,
    _user: User = Depends(get_current_user),
) -> list[ProvisionMethodItem]:
    """查可用坏账计提方法枚举列表及中文显示名（Req 1.4）。"""
    return [
        ProvisionMethodItem(value=m.value, label=PROVISION_METHOD_LABELS[m])
        for m in ProvisionMethod
    ]


@router.get("", response_model=BadDebtTreeResponse)
async def get_tree(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> BadDebtTreeResponse:
    """获取完整嵌套树（父行嵌套 children + Summary 合计）。"""
    wp_index_id = await resolve_wp_index_id(db, wp_id)
    return await NestedTableService(db).get_tree(wp_index_id)


@router.post("/parents", response_model=ParentRowResponse, status_code=status.HTTP_201_CREATED)
async def create_parent_row(
    wp_id: UUID,
    data: CreateParentRowDTO,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ParentRowResponse:
    """新增父行（计提类别）。同一底稿 provision_method 重复 → 409。"""
    wp_index_id = await resolve_wp_index_id(db, wp_id)
    svc = NestedTableService(db)
    try:
        result = await svc.create_parent_row(wp_index_id, data)
    except DuplicateProvisionMethodError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    return result


@router.post(
    "/{parent_id}/children",
    response_model=ChildRowResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_child_row(
    wp_id: UUID,
    parent_id: UUID,
    data: CreateChildRowDTO,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ChildRowResponse:
    """在指定父行下新增子行（明细行）。父行不存在 → 404。"""
    svc = NestedTableService(db)
    try:
        result = await svc.create_child_row(parent_id, data)
    except RowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except HierarchyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await db.commit()
    return result


@router.post("/prefill", response_model=PrefillResult)
async def prefill_summary(
    wp_id: UUID,
    body: PrefillRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> PrefillResult:
    """从试算表科目 1231 预填 Summary 期初/期末未审数（no-op 时仍 200）。"""
    wp_index_id = await resolve_wp_index_id(db, wp_id)
    result = await BadDebtPrefillService(db).prefill_summary(
        wp_index_id, body.project_id, body.year
    )
    # 只读查询，无写操作；保持一致性 commit 无副作用
    await db.commit()
    return result


@router.get("/aje-suggestion", response_model=AjeSuggestion | None)
async def get_aje_suggestion(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> AjeSuggestion | None:
    """获取坏账准备调整分录建议（零差额返回 null）。"""
    wp_index_id = await resolve_wp_index_id(db, wp_id)
    return await BadDebtAjeGenerator(db).generate_suggestion(wp_index_id)


@router.post("/serialize")
async def serialize_tree(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    """导出完整嵌套结构为 JSON。"""
    wp_index_id = await resolve_wp_index_id(db, wp_id)
    return await NestedTableService(db).serialize(wp_index_id)


@router.post("/deserialize")
async def deserialize_tree(
    wp_id: UUID,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    """从 JSON 恢复完整嵌套结构。校验失败 → 422（返回详细错误列表）。"""
    wp_index_id = await resolve_wp_index_id(db, wp_id)
    svc = NestedTableService(db)
    errors = await svc.deserialize(wp_index_id, payload)
    if errors:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "DESERIALIZE_VALIDATION_FAILED", "errors": errors},
        )
    await db.commit()
    return {"restored": True}


# ─────────────────────────────────────────────────────────────────────────────
# 通配 /{row_id} 端点（必须在静态路径之后声明）
# ─────────────────────────────────────────────────────────────────────────────


@router.put("/{row_id}", response_model=RowAmounts)
async def update_row(
    wp_id: UUID,
    row_id: UUID,
    data: UpdateRowDTO,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> RowAmounts:
    """更新单行金额/标签（乐观锁）。version 冲突 → 409；父行有子行编辑金额 → 400。"""
    svc = NestedTableService(db)
    try:
        result = await svc.update_row(row_id, data)
    except RowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OptimisticLockError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except HierarchyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await db.commit()
    return result


@router.delete("/{row_id}", status_code=status.HTTP_200_OK)
async def delete_row(
    wp_id: UUID,
    row_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    """删除行。删父行级联删子行；拒删最后一个父行 → 400；行不存在 → 404。"""
    svc = NestedTableService(db)
    try:
        await svc.delete_row(row_id)
    except RowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except HierarchyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await db.commit()
    return {"deleted": str(row_id)}
