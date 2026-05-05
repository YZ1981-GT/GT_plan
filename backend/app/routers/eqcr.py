"""EQCR 工作台路由

Refinement Round 5 任务 3 + 任务 5 + 任务 7 — EQCR 工作台 REST API。

访问控制说明（与需求 1 验收标准 2 对齐）：
- 统一用 ``Depends(get_current_user)``，service 层按 user → staff →
  ``ProjectAssignment.role='eqcr'`` 自行过滤，保证"本人作为 EQCR 的项目"
  的隐私边界。不强制检查 ``user.role``（UserRole 是系统级，
  ProjectAssignment.role 是项目级，分层独立）。
- overview 端点在用户不是该项目 EQCR 时仍返回数据，但把
  ``my_role_confirmed=false`` 回传前端，由 UI 决定是否展示"只读模式"
  或跳转；这样更便于跨角色复盘。

任务 5 新增（需求 2）：
- 5 个判断域聚合接口（materiality / estimates / related-parties /
  going-concern / opinion-type），每个接口返回统一 shape::

      {"project_id": str, "domain": str, "data": {...},
       "current_opinion": dict|None, "history_opinions": list[dict]}

- 意见 CRUD 两个接口：``POST /api/eqcr/opinions`` 新建；
  ``PATCH /api/eqcr/opinions/{opinion_id}`` 更新。

任务 7 新增（需求 2.4）：
- 关联方注册 CRUD：POST / PATCH / DELETE
- 关联方交易 CRUD：POST / PATCH / DELETE
- 权限：经理级（manager/signing_partner/partner/admin）可写，EQCR 只读
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.related_party_models import RelatedPartyRegistry, RelatedPartyTransaction
from app.models.staff_models import ProjectAssignment, StaffMember
from app.services.eqcr_service import EqcrService
from app.services.eqcr_shadow_compute_service import (
    ALLOWED_COMPUTATION_TYPES,
    EqcrShadowComputeService,
)


router = APIRouter(prefix="/api/eqcr", tags=["eqcr"])


# ---------------------------------------------------------------------------
# Pydantic 请求模型（任务 5 内联，集中放在路由文件避免 schemas 文件蔓延）
# ---------------------------------------------------------------------------


class EqcrOpinionCreate(BaseModel):
    """POST /api/eqcr/opinions 请求体。"""

    project_id: UUID = Field(..., description="项目 ID")
    domain: str = Field(
        ...,
        description=(
            "判断域；允许值 materiality / estimate / related_party / "
            "going_concern / opinion_type / component_auditor"
        ),
    )
    verdict: str = Field(
        ...,
        description="评议结论；允许值 agree / disagree / need_more_evidence",
    )
    comment: str | None = Field(None, description="意见说明")
    extra_payload: dict[str, Any] | None = Field(
        None,
        description="附加结构化数据；需求 11 组成部分审计师场景可携带 auditor_id/name",
    )


class EqcrOpinionUpdate(BaseModel):
    """PATCH /api/eqcr/opinions/{id} 请求体；所有字段可选。"""

    verdict: str | None = Field(None)
    comment: str | None = Field(None)
    extra_payload: dict[str, Any] | None = Field(None)


# ---------------------------------------------------------------------------
# 任务 8：影子计算 Pydantic 模型
# ---------------------------------------------------------------------------


class ShadowComputeRequest(BaseModel):
    """POST /api/eqcr/shadow-compute 请求体。"""

    project_id: UUID = Field(..., description="项目 ID")
    computation: str = Field(
        ...,
        description=(
            "计算类型；允许值 cfs_supplementary / debit_credit_balance / "
            "tb_vs_report / intercompany_elimination"
        ),
    )
    params: dict[str, Any] | None = Field(None, description="计算参数")


# ---------------------------------------------------------------------------
# 任务 7：关联方 CRUD Pydantic 模型
# ---------------------------------------------------------------------------

# relation_type 允许值
VALID_RELATION_TYPES = frozenset(
    ["parent", "subsidiary", "associate", "joint_venture",
     "key_management", "family_member", "other"]
)

# transaction_type 允许值
VALID_TRANSACTION_TYPES = frozenset(
    ["sales", "purchase", "loan", "guarantee", "service", "asset_transfer", "other"]
)

# 可写角色（经理级）
WRITABLE_PROJECT_ROLES = frozenset(
    ["manager", "signing_partner", "partner", "admin"]
)


class RelatedPartyCreate(BaseModel):
    """POST 关联方注册请求体。"""

    name: str = Field(..., min_length=1, max_length=200, description="关联方名称")
    relation_type: str = Field(..., description="关系类型")
    is_controlled_by_same_party: bool = Field(False, description="是否同一控制")


class RelatedPartyUpdate(BaseModel):
    """PATCH 关联方注册请求体（部分更新）。"""

    name: str | None = Field(None, min_length=1, max_length=200)
    relation_type: str | None = Field(None)
    is_controlled_by_same_party: bool | None = Field(None)


class RelatedPartyTransactionCreate(BaseModel):
    """POST 关联方交易请求体。"""

    related_party_id: UUID = Field(..., description="关联方 ID")
    amount: Decimal | None = Field(None, description="交易金额")
    transaction_type: str = Field(..., description="交易类型")
    is_arms_length: bool | None = Field(None, description="是否公允")
    evidence_refs: Any = Field(None, description="证据引用 JSONB")


class RelatedPartyTransactionUpdate(BaseModel):
    """PATCH 关联方交易请求体（部分更新）。"""

    related_party_id: UUID | None = Field(None)
    amount: Decimal | None = Field(None)
    transaction_type: str | None = Field(None)
    is_arms_length: bool | None = Field(None)
    evidence_refs: Any = Field(None)


# ---------------------------------------------------------------------------
# 任务 3：工作台列表 + 项目总览
# ---------------------------------------------------------------------------


@router.get("/projects")
async def list_my_eqcr_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回本人作为 EQCR 的项目卡片列表（签字日升序）。"""
    svc = EqcrService(db)
    return await svc.list_my_projects(current_user.id)


@router.get("/projects/{project_id}/overview")
async def get_eqcr_project_overview(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回项目 EQCR 总览数据（用于 EqcrProjectView 详情页壳）。"""
    svc = EqcrService(db)
    data = await svc.get_project_overview(current_user.id, project_id)
    if data is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return data


# ---------------------------------------------------------------------------
# 任务 5：5 个判断域聚合 API
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/materiality")
async def get_eqcr_materiality(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """需求 2.2：重要性 Tab 数据聚合 + 本域意见历史。"""
    svc = EqcrService(db)
    return await svc.get_materiality(project_id)


@router.get("/projects/{project_id}/estimates")
async def get_eqcr_estimates(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """需求 2.3：会计估计 Tab 数据（底稿维度聚合）。"""
    svc = EqcrService(db)
    return await svc.get_estimates(project_id)


@router.get("/projects/{project_id}/related-parties")
async def get_eqcr_related_parties(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """需求 2.4：关联方 Tab 数据（注册表 + 交易明细）。"""
    svc = EqcrService(db)
    return await svc.get_related_parties(project_id)


@router.get("/projects/{project_id}/going-concern")
async def get_eqcr_going_concern(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """需求 2.5：持续经营 Tab 数据（复用 GoingConcernEvaluation 模型）。"""
    svc = EqcrService(db)
    return await svc.get_going_concern(project_id)


@router.get("/projects/{project_id}/opinion-type")
async def get_eqcr_opinion_type(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """需求 2.6：审计意见类型 Tab 数据（AuditReport 视角 + 本域意见历史）。"""
    svc = EqcrService(db)
    return await svc.get_opinion_type(project_id)


# ---------------------------------------------------------------------------
# 任务 5：意见 CRUD
# ---------------------------------------------------------------------------


@router.post("/opinions")
async def create_eqcr_opinion(
    payload: EqcrOpinionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新建一条 EQCR 判断域意见（对应需求 2.7）。"""
    svc = EqcrService(db)
    try:
        result = await svc.create_opinion(
            project_id=payload.project_id,
            domain=payload.domain,
            verdict=payload.verdict,
            comment=payload.comment,
            extra_payload=payload.extra_payload,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return result


@router.patch("/opinions/{opinion_id}")
async def update_eqcr_opinion(
    opinion_id: UUID,
    payload: EqcrOpinionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新一条 EQCR 意见。只有创建人（或 admin）可改。"""
    svc = EqcrService(db)
    # 先查询原 opinion 以校验创建人
    from app.models.eqcr_models import EqcrOpinion

    existing = (
        await db.execute(
            select(EqcrOpinion).where(
                EqcrOpinion.id == opinion_id,
                EqcrOpinion.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        raise HTTPException(status_code=404, detail="意见不存在")
    is_admin = current_user.role.value == "admin" if current_user.role else False
    if existing.created_by != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="只有创建人或管理员可修改")

    try:
        result = await svc.update_opinion(
            opinion_id=opinion_id,
            user_id=current_user.id,
            verdict=payload.verdict,
            comment=payload.comment,
            extra_payload=payload.extra_payload,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="意见不存在")
    await db.commit()
    return result


# ---------------------------------------------------------------------------
# 任务 7：关联方 CRUD 端点（经理级可写，EQCR 只读）
# ---------------------------------------------------------------------------


async def _check_project_write_permission(
    db: AsyncSession, user: User, project_id: UUID
) -> None:
    """检查用户是否有项目写入权限（经理级角色或系统 admin）。

    无权限时抛出 HTTPException(403)。
    """
    # 系统管理员直接放行
    if user.role and user.role.value == "admin":
        return

    # 查询用户在该项目的角色
    staff_sub = select(StaffMember.id).where(
        StaffMember.user_id == user.id,
        StaffMember.is_deleted == False,  # noqa: E712
    ).scalar_subquery()

    assignment = (
        await db.execute(
            select(ProjectAssignment.role).where(
                ProjectAssignment.project_id == project_id,
                ProjectAssignment.staff_id == staff_sub,
                ProjectAssignment.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()

    if assignment is None or assignment not in WRITABLE_PROJECT_ROLES:
        raise HTTPException(
            status_code=403,
            detail="仅经理级角色（manager/partner/admin）可执行写入操作",
        )


# ─── 关联方注册 CRUD ─────────────────────────────────────────────────────────


@router.post("/projects/{project_id}/related-parties", status_code=201)
async def create_related_party(
    project_id: UUID,
    payload: RelatedPartyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新建关联方注册记录（经理级可写）。"""
    await _check_project_write_permission(db, current_user, project_id)

    if payload.relation_type not in VALID_RELATION_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"relation_type 不合法，允许值：{sorted(VALID_RELATION_TYPES)}",
        )

    record = RelatedPartyRegistry(
        project_id=project_id,
        name=payload.name.strip(),
        relation_type=payload.relation_type,
        is_controlled_by_same_party=payload.is_controlled_by_same_party,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return _serialize_registry(record)


@router.patch("/projects/{project_id}/related-parties/{party_id}")
async def update_related_party(
    project_id: UUID,
    party_id: UUID,
    payload: RelatedPartyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新关联方注册记录（经理级可写）。"""
    await _check_project_write_permission(db, current_user, project_id)

    record = (
        await db.execute(
            select(RelatedPartyRegistry).where(
                RelatedPartyRegistry.id == party_id,
                RelatedPartyRegistry.project_id == project_id,
                RelatedPartyRegistry.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="关联方记录不存在")

    if payload.name is not None:
        record.name = payload.name.strip()
    if payload.relation_type is not None:
        if payload.relation_type not in VALID_RELATION_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"relation_type 不合法，允许值：{sorted(VALID_RELATION_TYPES)}",
            )
        record.relation_type = payload.relation_type
    if payload.is_controlled_by_same_party is not None:
        record.is_controlled_by_same_party = payload.is_controlled_by_same_party

    await db.commit()
    await db.refresh(record)
    return _serialize_registry(record)


@router.delete("/projects/{project_id}/related-parties/{party_id}")
async def delete_related_party(
    project_id: UUID,
    party_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """软删除关联方注册记录（经理级可写）。"""
    await _check_project_write_permission(db, current_user, project_id)

    record = (
        await db.execute(
            select(RelatedPartyRegistry).where(
                RelatedPartyRegistry.id == party_id,
                RelatedPartyRegistry.project_id == project_id,
                RelatedPartyRegistry.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="关联方记录不存在")

    record.is_deleted = True
    await db.commit()
    return {"detail": "已删除"}


# ─── 关联方交易 CRUD ─────────────────────────────────────────────────────────


@router.post("/projects/{project_id}/related-party-transactions", status_code=201)
async def create_related_party_transaction(
    project_id: UUID,
    payload: RelatedPartyTransactionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新建关联方交易记录（经理级可写）。"""
    await _check_project_write_permission(db, current_user, project_id)

    if payload.transaction_type not in VALID_TRANSACTION_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"transaction_type 不合法，允许值：{sorted(VALID_TRANSACTION_TYPES)}",
        )

    # 验证 related_party_id 存在且属于该项目
    party_exists = (
        await db.execute(
            select(RelatedPartyRegistry.id).where(
                RelatedPartyRegistry.id == payload.related_party_id,
                RelatedPartyRegistry.project_id == project_id,
                RelatedPartyRegistry.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if party_exists is None:
        raise HTTPException(status_code=400, detail="关联方不存在或不属于该项目")

    record = RelatedPartyTransaction(
        project_id=project_id,
        related_party_id=payload.related_party_id,
        amount=payload.amount,
        transaction_type=payload.transaction_type,
        is_arms_length=payload.is_arms_length,
        evidence_refs=payload.evidence_refs,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return _serialize_transaction(record)


@router.patch("/projects/{project_id}/related-party-transactions/{txn_id}")
async def update_related_party_transaction(
    project_id: UUID,
    txn_id: UUID,
    payload: RelatedPartyTransactionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新关联方交易记录（经理级可写）。"""
    await _check_project_write_permission(db, current_user, project_id)

    record = (
        await db.execute(
            select(RelatedPartyTransaction).where(
                RelatedPartyTransaction.id == txn_id,
                RelatedPartyTransaction.project_id == project_id,
                RelatedPartyTransaction.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="交易记录不存在")

    if payload.related_party_id is not None:
        # 验证新的 related_party_id
        party_exists = (
            await db.execute(
                select(RelatedPartyRegistry.id).where(
                    RelatedPartyRegistry.id == payload.related_party_id,
                    RelatedPartyRegistry.project_id == project_id,
                    RelatedPartyRegistry.is_deleted == False,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        if party_exists is None:
            raise HTTPException(status_code=400, detail="关联方不存在或不属于该项目")
        record.related_party_id = payload.related_party_id

    if payload.amount is not None:
        record.amount = payload.amount
    if payload.transaction_type is not None:
        if payload.transaction_type not in VALID_TRANSACTION_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"transaction_type 不合法，允许值：{sorted(VALID_TRANSACTION_TYPES)}",
            )
        record.transaction_type = payload.transaction_type
    if payload.is_arms_length is not None:
        record.is_arms_length = payload.is_arms_length
    if payload.evidence_refs is not None:
        record.evidence_refs = payload.evidence_refs

    await db.commit()
    await db.refresh(record)
    return _serialize_transaction(record)


@router.delete("/projects/{project_id}/related-party-transactions/{txn_id}")
async def delete_related_party_transaction(
    project_id: UUID,
    txn_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """软删除关联方交易记录（经理级可写）。"""
    await _check_project_write_permission(db, current_user, project_id)

    record = (
        await db.execute(
            select(RelatedPartyTransaction).where(
                RelatedPartyTransaction.id == txn_id,
                RelatedPartyTransaction.project_id == project_id,
                RelatedPartyTransaction.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="交易记录不存在")

    record.is_deleted = True
    await db.commit()
    return {"detail": "已删除"}


# ---------------------------------------------------------------------------
# 任务 8：影子计算端点
# ---------------------------------------------------------------------------


@router.post("/shadow-compute")
async def eqcr_shadow_compute(
    payload: ShadowComputeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """EQCR 影子计算：独立跑一遍勾稽，不依赖项目组结果。

    需求 4：
    - 限流每项目每天 20 次（Redis）
    - 调用 consistency_replay_engine（caller_context='eqcr'）
    - 结果存 eqcr_shadow_computations 表
    - 与项目组结果对比 has_diff 字段
    """
    # 验证 computation_type
    if payload.computation not in ALLOWED_COMPUTATION_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"computation 不合法，允许值：{sorted(ALLOWED_COMPUTATION_TYPES)}",
        )

    # 限流检查（Redis）
    redis_client = None
    try:
        from app.core.redis import redis_client as _redis
        await _redis.ping()
        redis_client = _redis
    except Exception:
        pass  # Redis 不可用，降级放行

    svc = EqcrShadowComputeService(db)
    allowed, remaining = await svc.check_rate_limit(payload.project_id, redis_client)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "message": "影子计算限流：每项目每天最多 20 次",
                "project_id": str(payload.project_id),
                "daily_limit": 20,
                "remaining": 0,
            },
            headers={"Retry-After": "86400"},
        )

    # 执行影子计算
    result = await svc.execute_shadow_compute(
        project_id=payload.project_id,
        computation_type=payload.computation,
        params=payload.params,
        user_id=current_user.id,
    )
    await db.commit()
    return result


@router.get("/projects/{project_id}/shadow-computations")
async def list_shadow_computations(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回该项目所有影子计算记录列表。"""
    svc = EqcrShadowComputeService(db)
    return await svc.list_shadow_computations(project_id)


# ---------------------------------------------------------------------------
# 序列化辅助
# ---------------------------------------------------------------------------


def _serialize_registry(r: RelatedPartyRegistry) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "project_id": str(r.project_id),
        "name": r.name,
        "relation_type": r.relation_type,
        "is_controlled_by_same_party": r.is_controlled_by_same_party,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def _serialize_transaction(t: RelatedPartyTransaction) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "project_id": str(t.project_id),
        "related_party_id": str(t.related_party_id),
        "amount": str(t.amount) if t.amount is not None else None,
        "transaction_type": t.transaction_type,
        "is_arms_length": t.is_arms_length,
        "evidence_refs": t.evidence_refs,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }
