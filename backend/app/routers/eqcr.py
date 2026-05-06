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

from datetime import datetime, timezone

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import Project, User
from app.models.eqcr_models import EqcrReviewNote
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
# 任务 12：EQCR 审批（门禁入口）Pydantic 模型
# ---------------------------------------------------------------------------


class EqcrApproveRequest(BaseModel):
    """POST /api/eqcr/projects/{project_id}/approve 请求体。"""

    verdict: str = Field(
        ...,
        description="审批结论；允许值 approve / disagree",
    )
    comment: str = Field(..., min_length=1, description="审批意见说明")
    shadow_comp_refs: list[UUID] | None = Field(
        None, description="引用的影子计算记录 ID 列表"
    )
    attached_opinion_ids: list[UUID] | None = Field(
        None, description="附带的 EQCR 意见 ID 列表"
    )


class EqcrUnlockOpinionRequest(BaseModel):
    """POST /api/eqcr/projects/{project_id}/unlock-opinion 请求体。"""

    reason: str = Field(..., min_length=1, description="回退原因（必填）")


# ---------------------------------------------------------------------------
# 任务 10：EQCR 独立复核笔记 Pydantic 模型
# ---------------------------------------------------------------------------


class EqcrNoteCreate(BaseModel):
    """POST /api/eqcr/projects/{project_id}/notes 请求体。"""

    title: str = Field(..., min_length=1, max_length=200, description="笔记标题")
    content: str | None = Field(None, description="笔记内容")


class EqcrNoteUpdate(BaseModel):
    """PATCH /api/eqcr/projects/{project_id}/notes/{note_id} 请求体。"""

    title: str | None = Field(None, min_length=1, max_length=200, description="笔记标题")
    content: str | None = Field(None, description="笔记内容")


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
# 任务 10：EQCR 独立复核笔记 CRUD + 分享
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/notes")
async def list_eqcr_notes(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出本人在该项目的 EQCR 独立复核笔记。

    需求 3：EQCR 只看自己的笔记（created_by == current_user.id）。
    admin 可看所有笔记。
    """
    is_admin = current_user.role and current_user.role.value == "admin"
    stmt = select(EqcrReviewNote).where(
        EqcrReviewNote.project_id == project_id,
        EqcrReviewNote.is_deleted == False,  # noqa: E712
    )
    if not is_admin:
        stmt = stmt.where(EqcrReviewNote.created_by == current_user.id)
    stmt = stmt.order_by(EqcrReviewNote.created_at.desc())

    result = await db.execute(stmt)
    notes = result.scalars().all()
    return [_serialize_note(n) for n in notes]


@router.post("/projects/{project_id}/notes", status_code=201)
async def create_eqcr_note(
    project_id: UUID,
    payload: EqcrNoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建一条 EQCR 独立复核笔记。

    需求 3：默认 shared_to_team=false，项目组不可见。
    """
    note = EqcrReviewNote(
        project_id=project_id,
        title=payload.title.strip(),
        content=payload.content,
        shared_to_team=False,
        created_by=current_user.id,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return _serialize_note(note)


@router.patch("/projects/{project_id}/notes/{note_id}")
async def update_eqcr_note(
    project_id: UUID,
    note_id: UUID,
    payload: EqcrNoteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新一条 EQCR 独立复核笔记。只有创建人可改。"""
    note = (
        await db.execute(
            select(EqcrReviewNote).where(
                EqcrReviewNote.id == note_id,
                EqcrReviewNote.project_id == project_id,
                EqcrReviewNote.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if note is None:
        raise HTTPException(status_code=404, detail="笔记不存在")

    is_admin = current_user.role and current_user.role.value == "admin"
    if note.created_by != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="只有创建人可修改笔记")

    if payload.title is not None:
        note.title = payload.title.strip()
    if payload.content is not None:
        note.content = payload.content

    await db.commit()
    await db.refresh(note)
    return _serialize_note(note)


@router.delete("/projects/{project_id}/notes/{note_id}")
async def delete_eqcr_note(
    project_id: UUID,
    note_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """软删除一条 EQCR 独立复核笔记。只有创建人可删。"""
    note = (
        await db.execute(
            select(EqcrReviewNote).where(
                EqcrReviewNote.id == note_id,
                EqcrReviewNote.project_id == project_id,
                EqcrReviewNote.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if note is None:
        raise HTTPException(status_code=404, detail="笔记不存在")

    is_admin = current_user.role and current_user.role.value == "admin"
    if note.created_by != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="只有创建人可删除笔记")

    note.is_deleted = True
    note.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return {"detail": "已删除"}


@router.post("/notes/{note_id}/share-to-team")
async def share_note_to_team(
    note_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """分享单条笔记到项目组。

    需求 3.4：
    - 设置 shared_to_team=True, shared_at=now
    - 同步到 Project.wizard_state.communications（复用 R2 沟通记录体系）
    - 来源字段注明"EQCR 独立复核笔记"
    - 已分享的笔记不能再取消分享（单向操作）
    """
    note = (
        await db.execute(
            select(EqcrReviewNote).where(
                EqcrReviewNote.id == note_id,
                EqcrReviewNote.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if note is None:
        raise HTTPException(status_code=404, detail="笔记不存在")

    is_admin = current_user.role and current_user.role.value == "admin"
    if note.created_by != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="只有创建人可分享笔记")

    # 幂等：已分享的笔记直接返回 200，不报错
    if note.shared_to_team:
        return _serialize_note(note)

    # 标记为已分享
    now = datetime.now(timezone.utc)
    note.shared_to_team = True
    note.shared_at = now

    # 同步到 Project.wizard_state.communications
    project = (
        await db.execute(
            select(Project).where(Project.id == note.project_id)
        )
    ).scalar_one_or_none()
    if project is not None:
        wizard_state = project.wizard_state or {}
        communications = wizard_state.get("communications", [])
        communications.append({
            "source": "EQCR 独立复核笔记",
            "title": note.title,
            "content": note.content or "",
            "shared_at": now.isoformat(),
            "shared_by": str(current_user.id),
            "note_id": str(note.id),
        })
        wizard_state["communications"] = communications
        project.wizard_state = wizard_state
        # 标记 JSONB 字段已变更（SQLAlchemy 需要显式标记）
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(project, "wizard_state")

    await db.commit()
    await db.refresh(note)
    return _serialize_note(note)


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
# 任务 12：EQCR 审批门禁 + 意见解锁
# ---------------------------------------------------------------------------


@router.post("/projects/{project_id}/approve")
async def eqcr_approve(
    project_id: UUID,
    payload: EqcrApproveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """EQCR 审批入口（需求 5）。

    - verdict='approve'：触发 gate_engine.evaluate(eqcr_approval)，
      通过则切 AuditReport.status → eqcr_approved，并创建 SignatureRecord(order=4)。
    - verdict='disagree'：创建 EQCR 异议记录（EqcrDisagreementResolution），
      触发合议流程。
    """
    from app.models.eqcr_models import EqcrDisagreementResolution, EqcrOpinion
    from app.models.extension_models import SignatureRecord
    from app.models.phase14_enums import GateDecisionResult, GateType
    from app.models.report_models import AuditReport, ReportStatus
    from app.services.gate_engine import gate_engine

    if payload.verdict not in ("approve", "disagree"):
        raise HTTPException(
            status_code=400,
            detail="verdict 必须为 'approve' 或 'disagree'",
        )

    # 验证用户是该项目的 EQCR
    svc = EqcrService(db)
    is_eqcr = await svc._is_user_eqcr_on(current_user.id, project_id)
    if not is_eqcr:
        raise HTTPException(
            status_code=403,
            detail="当前用户不是该项目的 EQCR，无权审批",
        )

    # 获取审计报告
    ar_q = (
        select(AuditReport)
        .where(
            AuditReport.project_id == project_id,
            AuditReport.is_deleted == False,  # noqa: E712
        )
        .order_by(AuditReport.year.desc())
        .limit(1)
    )
    audit_report = (await db.execute(ar_q)).scalar_one_or_none()
    if audit_report is None:
        raise HTTPException(status_code=404, detail="该项目无审计报告")

    # 审计报告必须处于 review 状态才能审批
    current_status = (
        audit_report.status.value
        if hasattr(audit_report.status, "value")
        else str(audit_report.status)
    )
    if current_status != ReportStatus.review.value:
        raise HTTPException(
            status_code=400,
            detail=f"审计报告当前状态为 '{current_status}'，只有 'review' 状态才能进行 EQCR 审批",
        )

    if payload.verdict == "approve":
        # 触发 gate_engine 评估
        gate_result = await gate_engine.evaluate(
            db=db,
            gate_type=GateType.eqcr_approval,
            project_id=project_id,
            wp_id=None,
            actor_id=current_user.id,
            context={
                "action": "eqcr_approve",
                "comment": payload.comment,
            },
        )

        if gate_result.decision == GateDecisionResult.block:
            # 门禁阻断，返回阻断原因
            blocking_rules = [
                {
                    "rule_code": h.rule_code,
                    "error_code": h.error_code,
                    "message": h.message,
                    "suggested_action": h.suggested_action,
                }
                for h in gate_result.hit_rules
                if h.severity == "blocking"
            ]
            raise HTTPException(
                status_code=422,
                detail={
                    "error_code": "EQCR_GATE_BLOCKED",
                    "message": "EQCR 审批门禁未通过",
                    "blocking_rules": blocking_rules,
                    "trace_id": gate_result.trace_id,
                },
            )

        # 门禁通过：切状态 review → eqcr_approved
        audit_report.status = ReportStatus.eqcr_approved
        audit_report.updated_by = current_user.id

        # 创建 SignatureRecord（order=4 EQCR 签字）
        sig = SignatureRecord(
            object_type="audit_report",
            object_id=audit_report.id,
            signer_id=current_user.id,
            signature_level="eqcr",
            required_order=4,
            required_role="eqcr",
            signature_data={
                "verdict": "approve",
                "comment": payload.comment,
                "shadow_comp_refs": [str(r) for r in payload.shadow_comp_refs]
                if payload.shadow_comp_refs
                else None,
                "attached_opinion_ids": [str(r) for r in payload.attached_opinion_ids]
                if payload.attached_opinion_ids
                else None,
            },
            signature_timestamp=datetime.now(timezone.utc),
        )
        db.add(sig)
        await db.commit()

        return {
            "status": "approved",
            "report_status": ReportStatus.eqcr_approved.value,
            "gate_decision": gate_result.decision,
            "trace_id": gate_result.trace_id,
            "signature_id": str(sig.id),
        }

    else:
        # verdict='disagree'：创建异议记录
        # 找到最新的 disagree opinion 或创建一条新的
        disagree_opinion = (
            await db.execute(
                select(EqcrOpinion)
                .where(
                    EqcrOpinion.project_id == project_id,
                    EqcrOpinion.verdict == "disagree",
                    EqcrOpinion.is_deleted == False,  # noqa: E712
                )
                .order_by(EqcrOpinion.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        # 如果没有现有的 disagree opinion，创建一条 opinion_type 域的
        if disagree_opinion is None:
            disagree_opinion = EqcrOpinion(
                project_id=project_id,
                domain="opinion_type",
                verdict="disagree",
                comment=payload.comment,
                created_by=current_user.id,
            )
            db.add(disagree_opinion)
            await db.flush()

        # 创建异议合议记录
        resolution = EqcrDisagreementResolution(
            project_id=project_id,
            eqcr_opinion_id=disagree_opinion.id,
            participants=[str(current_user.id)],  # 初始参与人为 EQCR 本人
            resolution=None,
            resolution_verdict=None,
            resolved_at=None,
        )
        db.add(resolution)
        await db.commit()
        await db.refresh(resolution)

        return {
            "status": "disagreed",
            "report_status": current_status,
            "disagreement_resolution_id": str(resolution.id),
            "opinion_id": str(disagree_opinion.id),
            "message": "EQCR 异议已记录，请启动合议流程",
        }


@router.post("/projects/{project_id}/unlock-opinion")
async def eqcr_unlock_opinion(
    project_id: UUID,
    payload: EqcrUnlockOpinionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """EQCR 显式回退审计报告到 review 态（需求 6.4）。

    - 必须附文字说明（reason）
    - 回退操作记 audit_logger_enhanced
    - 只有 EQCR 可操作
    - 只有 eqcr_approved 状态才能回退
    """
    from app.models.report_models import AuditReport, ReportStatus
    from app.services.audit_logger_enhanced import audit_logger

    # 验证用户是该项目的 EQCR
    svc = EqcrService(db)
    is_eqcr = await svc._is_user_eqcr_on(current_user.id, project_id)
    if not is_eqcr:
        raise HTTPException(
            status_code=403,
            detail="当前用户不是该项目的 EQCR，无权解锁",
        )

    # 获取审计报告
    ar_q = (
        select(AuditReport)
        .where(
            AuditReport.project_id == project_id,
            AuditReport.is_deleted == False,  # noqa: E712
        )
        .order_by(AuditReport.year.desc())
        .limit(1)
    )
    audit_report = (await db.execute(ar_q)).scalar_one_or_none()
    if audit_report is None:
        raise HTTPException(status_code=404, detail="该项目无审计报告")

    current_status = (
        audit_report.status.value
        if hasattr(audit_report.status, "value")
        else str(audit_report.status)
    )
    if current_status != ReportStatus.eqcr_approved.value:
        raise HTTPException(
            status_code=400,
            detail=f"审计报告当前状态为 '{current_status}'，只有 'eqcr_approved' 状态才能回退",
        )

    # 回退状态 eqcr_approved → review
    audit_report.status = ReportStatus.review
    audit_report.updated_by = current_user.id

    # 记录审计日志
    await audit_logger.log_action(
        user_id=current_user.id,
        action="eqcr_unlock_opinion",
        object_type="audit_report",
        object_id=audit_report.id,
        project_id=project_id,
        details={
            "reason": payload.reason,
            "previous_status": ReportStatus.eqcr_approved.value,
            "new_status": ReportStatus.review.value,
        },
    )

    await db.commit()

    return {
        "status": "unlocked",
        "report_status": ReportStatus.review.value,
        "reason": payload.reason,
        "message": "审计报告已回退到 review 状态，意见类型和段落已解锁",
    }


# ---------------------------------------------------------------------------
# 年度独立性声明（任务 23 — 需求 12）
# ---------------------------------------------------------------------------


class AnnualDeclarationSubmitRequest(BaseModel):
    """提交年度独立性声明"""
    year: int | None = None
    answers: dict = Field(default_factory=dict)


@router.get("/independence/annual/check")
async def check_annual_declaration(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """检查当前用户是否已提交本年度独立性声明（需求 12）。

    EQCR 工作台登录守卫使用此端点。
    """
    from app.services.eqcr_independence_service import EqcrIndependenceService

    svc = EqcrIndependenceService(db)
    has_declaration = await svc.check_annual_declaration(current_user.id)
    return {
        "has_declaration": has_declaration,
        "year": datetime.now(timezone.utc).year,
    }


@router.get("/independence/annual/questions")
async def get_annual_questions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取年度独立性声明问题集（需求 12）。"""
    from app.services.eqcr_independence_service import EqcrIndependenceService

    svc = EqcrIndependenceService(db)
    questions = svc.get_annual_questions()
    return {"questions": questions, "total": len(questions)}


@router.post("/independence/annual/submit")
async def submit_annual_declaration(
    payload: AnnualDeclarationSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交年度独立性声明（需求 12）。"""
    from app.services.eqcr_independence_service import EqcrIndependenceService

    svc = EqcrIndependenceService(db)
    try:
        result = await svc.submit_annual_declaration(
            current_user.id,
            payload.year,
            payload.answers,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# 组成部分审计师聚合（任务 21 — 需求 11）
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/component-auditors")
async def get_eqcr_component_auditors(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """EQCR 视角的组成部分审计师聚合（需求 11）。

    聚合：组成部分清单、各审计师能力评级、独立性确认状态、
    重大发现反馈摘要、EQCR 已录意见。
    """
    from app.models.consolidation_models import (
        ComponentAuditor,
        ComponentInstruction,
        ComponentResult,
    )
    from app.models.eqcr_models import EqcrOpinion

    # 获取所有组成部分审计师
    auditors_q = (
        select(ComponentAuditor)
        .where(
            ComponentAuditor.project_id == project_id,
            ComponentAuditor.is_deleted == False,  # noqa: E712
        )
        .order_by(ComponentAuditor.company_code)
    )
    auditors = list((await db.execute(auditors_q)).scalars().all())

    # 获取 EQCR 对 component_auditor 域的意见
    opinions_q = select(EqcrOpinion).where(
        EqcrOpinion.project_id == project_id,
        EqcrOpinion.domain == "component_auditor",
        EqcrOpinion.is_deleted == False,  # noqa: E712
    )
    opinions = list((await db.execute(opinions_q)).scalars().all())
    # 按 extra_payload.auditor_id 索引
    opinions_by_auditor: dict[str, list] = {}
    for op in opinions:
        aid = (op.extra_payload or {}).get("auditor_id", "")
        opinions_by_auditor.setdefault(aid, []).append(op)

    result = []
    for a in auditors:
        # 获取指令
        instr_q = select(ComponentInstruction).where(
            ComponentInstruction.component_auditor_id == a.id,
            ComponentInstruction.is_deleted == False,  # noqa: E712
        )
        instructions = list((await db.execute(instr_q)).scalars().all())

        # 获取结果
        res_q = select(ComponentResult).where(
            ComponentResult.component_auditor_id == a.id,
            ComponentResult.is_deleted == False,  # noqa: E712
        )
        results = list((await db.execute(res_q)).scalars().all())

        # EQCR 意见
        auditor_opinions = opinions_by_auditor.get(str(a.id), [])

        result.append({
            "id": str(a.id),
            "company_code": a.company_code,
            "firm_name": a.firm_name,
            "contact_person": a.contact_person,
            "competence_rating": a.competence_rating.value if a.competence_rating else None,
            "rating_basis": a.rating_basis,
            "independence_confirmed": a.independence_confirmed,
            "independence_date": str(a.independence_date) if a.independence_date else None,
            "instruction_count": len(instructions),
            "result_count": len(results),
            "eqcr_opinions": [
                {
                    "id": str(op.id),
                    "verdict": op.verdict,
                    "comment": op.comment,
                    "created_at": op.created_at.isoformat() if op.created_at else None,
                }
                for op in auditor_opinions
            ],
        })

    return {
        "project_id": str(project_id),
        "auditors": result,
        "total_count": len(result),
    }


# ---------------------------------------------------------------------------
# EQCR 指标仪表盘（任务 20 — 需求 10）
# ---------------------------------------------------------------------------


@router.get("/metrics")
async def get_eqcr_metrics(
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """EQCR 年度指标仪表盘（需求 10）。

    返回所有 EQCR 的年度工作量、发现问题数、与项目组意见不一致率。
    权限：仅 admin / partner 可见（合伙人级别以上）。
    """
    # 权限校验（后端真实控制；前端路由 roles 只是粗筛）
    user_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if user_role not in ("admin", "partner"):
        raise HTTPException(
            status_code=403,
            detail="仅 admin 或 partner 可访问 EQCR 指标仪表盘",
        )

    from app.models.eqcr_models import EqcrOpinion, EqcrDisagreementResolution
    from app.models.staff_models import WorkHour
    from sqlalchemy import func, extract, case

    target_year = year or datetime.now(timezone.utc).year

    # 获取所有 EQCR 角色的人员
    eqcr_assignments_q = (
        select(
            ProjectAssignment.staff_id,
            StaffMember.name.label("staff_name"),
            func.count(ProjectAssignment.id).label("project_count"),
        )
        .join(StaffMember, ProjectAssignment.staff_id == StaffMember.id)
        .where(
            ProjectAssignment.role == "eqcr",
            ProjectAssignment.is_deleted == False,  # noqa: E712
        )
        .group_by(ProjectAssignment.staff_id, StaffMember.name)
    )
    eqcr_rows = (await db.execute(eqcr_assignments_q)).all()

    metrics = []
    for row in eqcr_rows:
        staff_id = row.staff_id
        staff_name = row.staff_name
        project_count = row.project_count

        # 总工时（purpose=eqcr，该年度）
        hours_q = select(
            func.coalesce(func.sum(WorkHour.hours), 0)
        ).where(
            WorkHour.staff_id == staff_id,
            WorkHour.purpose == "eqcr",
            WorkHour.status != "tracking",
            WorkHour.is_deleted == False,  # noqa: E712
            extract("year", WorkHour.work_date) == target_year,
        )
        total_hours = float((await db.execute(hours_q)).scalar_one())

        # 获取该 EQCR 负责的项目 IDs
        proj_ids_q = select(ProjectAssignment.project_id).where(
            ProjectAssignment.staff_id == staff_id,
            ProjectAssignment.role == "eqcr",
            ProjectAssignment.is_deleted == False,  # noqa: E712
        )
        proj_ids = list((await db.execute(proj_ids_q)).scalars().all())

        # 异议数
        disagreement_count = 0
        total_opinions = 0
        if proj_ids:
            disagree_q = select(func.count()).where(
                EqcrOpinion.project_id.in_(proj_ids),
                EqcrOpinion.verdict == "disagree",
                EqcrOpinion.is_deleted == False,  # noqa: E712
            )
            disagreement_count = (await db.execute(disagree_q)).scalar_one()

            total_q = select(func.count()).where(
                EqcrOpinion.project_id.in_(proj_ids),
                EqcrOpinion.is_deleted == False,  # noqa: E712
            )
            total_opinions = (await db.execute(total_q)).scalar_one()

        disagreement_rate = (
            round(disagreement_count / total_opinions * 100, 1)
            if total_opinions > 0
            else 0.0
        )

        # 重大发现数（有异议且未解决的）
        material_findings = 0
        if proj_ids:
            findings_q = select(func.count()).where(
                EqcrDisagreementResolution.project_id.in_(proj_ids),
                EqcrDisagreementResolution.resolved_at.is_(None),
            )
            material_findings = (await db.execute(findings_q)).scalar_one()

        metrics.append({
            "eqcr_id": str(staff_id),
            "eqcr_name": staff_name,
            "project_count": project_count,
            "total_hours": round(total_hours, 1),
            "disagreement_count": disagreement_count,
            "disagreement_rate": disagreement_rate,
            "material_findings_count": material_findings,
        })

    return {
        "year": target_year,
        "metrics": metrics,
    }


# ---------------------------------------------------------------------------
# EQCR 备忘录（任务 18 — 需求 9）
# ---------------------------------------------------------------------------


class EqcrMemoSaveRequest(BaseModel):
    """保存备忘录编辑内容"""
    sections: dict[str, str]


@router.post("/projects/{project_id}/memo")
async def generate_eqcr_memo(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """生成 EQCR 备忘录（需求 9）。

    根据 EQCR 各 Tab 录入的意见、独立笔记、影子计算结果，
    自动组装成结构化备忘录。
    """
    from app.services.eqcr_memo_service import EqcrMemoService

    svc = EqcrMemoService(db)
    try:
        memo = await svc.generate_memo(project_id, current_user.id)
        # 自动保存到 wizard_state
        await svc.save_memo(project_id, memo["sections"])
        await db.commit()
        return memo
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}/memo/preview")
async def preview_eqcr_memo(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """预览已保存的 EQCR 备忘录。"""
    proj_q = select(Project).where(
        Project.id == project_id,
        Project.is_deleted == False,  # noqa: E712
    )
    proj = (await db.execute(proj_q)).scalar_one_or_none()
    if proj is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    wizard = proj.wizard_state or {}
    memo = wizard.get("eqcr_memo")
    if not memo:
        raise HTTPException(status_code=404, detail="备忘录尚未生成")

    return {
        "project_id": str(project_id),
        "sections": memo.get("sections", {}),
        "status": memo.get("status", "draft"),
        "updated_at": memo.get("updated_at"),
        "finalized_at": memo.get("finalized_at"),
    }


@router.put("/projects/{project_id}/memo")
async def save_eqcr_memo(
    project_id: UUID,
    payload: EqcrMemoSaveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """保存编辑后的 EQCR 备忘录。"""
    from app.services.eqcr_memo_service import EqcrMemoService

    svc = EqcrMemoService(db)
    try:
        result = await svc.save_memo(project_id, payload.sections)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/projects/{project_id}/memo/finalize")
async def finalize_eqcr_memo(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """定稿 EQCR 备忘录（需求 9）。

    定稿后 PDF 版本将在归档包导出时自动生成。
    """
    from app.services.eqcr_memo_service import EqcrMemoService

    # 验证 EQCR 身份
    svc_eqcr = EqcrService(db)
    is_eqcr = await svc_eqcr._is_user_eqcr_on(current_user.id, project_id)
    if not is_eqcr:
        raise HTTPException(status_code=403, detail="非本项目 EQCR，无权定稿")

    svc = EqcrMemoService(db)
    try:
        result = await svc.finalize_memo(project_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# EQCR 工时追踪（任务 17 — 需求 8）
# ---------------------------------------------------------------------------


class EqcrTimeTrackStartRequest(BaseModel):
    """开始复核计时"""
    pass


class EqcrTimeTrackStopRequest(BaseModel):
    """结束复核计时，生成工时记录"""
    description: str | None = None


@router.post("/projects/{project_id}/time-track/start")
async def eqcr_time_track_start(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """EQCR 开始复核计时（需求 8）。

    记录开始时间到 Redis 或内存（简化实现用 DB 临时记录）。
    """
    from app.models.staff_models import WorkHour, StaffMember

    # 验证 EQCR 身份
    svc = EqcrService(db)
    is_eqcr = await svc._is_user_eqcr_on(current_user.id, project_id)
    if not is_eqcr:
        raise HTTPException(status_code=403, detail="非本项目 EQCR")

    # 获取 staff_id
    staff_q = select(StaffMember.id).where(
        StaffMember.user_id == current_user.id,
        StaffMember.is_deleted == False,  # noqa: E712
    )
    staff_id = (await db.execute(staff_q)).scalar_one_or_none()
    if staff_id is None:
        raise HTTPException(status_code=404, detail="未找到员工记录")

    # 检查是否已有进行中的计时（status='tracking'）
    existing_q = select(WorkHour).where(
        WorkHour.staff_id == staff_id,
        WorkHour.project_id == project_id,
        WorkHour.purpose == "eqcr",
        WorkHour.status == "tracking",
        WorkHour.is_deleted == False,  # noqa: E712
    )
    existing = (await db.execute(existing_q)).scalar_one_or_none()
    if existing:
        return {
            "status": "already_tracking",
            "tracking_id": str(existing.id),
            "started_at": existing.start_time.isoformat() if existing.start_time else existing.created_at.isoformat(),
        }

    # 创建 tracking 记录
    from datetime import date as date_type, time as time_type
    now = datetime.now(timezone.utc)
    wh = WorkHour(
        staff_id=staff_id,
        project_id=project_id,
        work_date=now.date(),
        hours=0,
        start_time=now.time(),
        end_time=None,
        description="EQCR 独立复核",
        status="tracking",
        purpose="eqcr",
    )
    db.add(wh)
    await db.commit()
    await db.refresh(wh)

    return {
        "status": "started",
        "tracking_id": str(wh.id),
        "started_at": now.isoformat(),
    }


@router.post("/projects/{project_id}/time-track/stop")
async def eqcr_time_track_stop(
    project_id: UUID,
    payload: EqcrTimeTrackStopRequest = EqcrTimeTrackStopRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """EQCR 结束复核计时，生成正式工时记录（需求 8）。"""
    from app.models.staff_models import WorkHour, StaffMember
    from decimal import Decimal

    # 验证 EQCR 身份
    svc = EqcrService(db)
    is_eqcr = await svc._is_user_eqcr_on(current_user.id, project_id)
    if not is_eqcr:
        raise HTTPException(status_code=403, detail="非本项目 EQCR")

    # 获取 staff_id
    staff_q = select(StaffMember.id).where(
        StaffMember.user_id == current_user.id,
        StaffMember.is_deleted == False,  # noqa: E712
    )
    staff_id = (await db.execute(staff_q)).scalar_one_or_none()
    if staff_id is None:
        raise HTTPException(status_code=404, detail="未找到员工记录")

    # 查找进行中的计时
    tracking_q = select(WorkHour).where(
        WorkHour.staff_id == staff_id,
        WorkHour.project_id == project_id,
        WorkHour.purpose == "eqcr",
        WorkHour.status == "tracking",
        WorkHour.is_deleted == False,  # noqa: E712
    )
    tracking = (await db.execute(tracking_q)).scalar_one_or_none()
    if tracking is None:
        raise HTTPException(status_code=404, detail="无进行中的 EQCR 计时")

    # 计算时长
    now = datetime.now(timezone.utc)
    start_dt = datetime.combine(tracking.work_date, tracking.start_time, tzinfo=timezone.utc)
    elapsed = (now - start_dt).total_seconds() / 3600.0
    hours = Decimal(str(round(elapsed, 2)))
    if hours <= 0:
        hours = Decimal("0.01")

    # 更新记录
    tracking.end_time = now.time()
    tracking.hours = hours
    tracking.status = "draft"
    if payload.description:
        tracking.description = payload.description

    await db.commit()
    await db.refresh(tracking)

    return {
        "status": "stopped",
        "tracking_id": str(tracking.id),
        "hours": float(tracking.hours),
        "work_date": str(tracking.work_date),
        "description": tracking.description,
    }


@router.get("/projects/{project_id}/time-summary")
async def eqcr_time_summary(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取 EQCR 在该项目的工时汇总（需求 8）。"""
    from app.models.staff_models import WorkHour, StaffMember
    from sqlalchemy import func

    # 获取 staff_id
    staff_q = select(StaffMember.id).where(
        StaffMember.user_id == current_user.id,
        StaffMember.is_deleted == False,  # noqa: E712
    )
    staff_id = (await db.execute(staff_q)).scalar_one_or_none()
    if staff_id is None:
        return {"total_hours": 0, "records": []}

    # 查询所有 purpose=eqcr 的工时
    q = (
        select(WorkHour)
        .where(
            WorkHour.staff_id == staff_id,
            WorkHour.project_id == project_id,
            WorkHour.purpose == "eqcr",
            WorkHour.status != "tracking",
            WorkHour.is_deleted == False,  # noqa: E712
        )
        .order_by(WorkHour.work_date.desc())
    )
    records = list((await db.execute(q)).scalars().all())

    total_hours = sum(float(r.hours) for r in records)

    return {
        "total_hours": round(total_hours, 2),
        "record_count": len(records),
        "records": [
            {
                "id": str(r.id),
                "work_date": str(r.work_date),
                "hours": float(r.hours),
                "start_time": str(r.start_time) if r.start_time else None,
                "end_time": str(r.end_time) if r.end_time else None,
                "description": r.description,
                "status": r.status,
            }
            for r in records
        ],
    }


# ---------------------------------------------------------------------------
# 历年 EQCR 对比（任务 15 — 需求 7）
# ---------------------------------------------------------------------------


class LinkPriorYearRequest(BaseModel):
    """手动关联上年项目"""
    prior_project_id: UUID


@router.get("/projects/{project_id}/prior-year-comparison")
async def get_prior_year_comparison(
    project_id: UUID,
    years: int = 3,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取历年 EQCR 意见对比（需求 7）。

    按 client_name 精确匹配近 N 年项目的 EQCR 意见，
    自动标记差异点。
    """
    from app.models.eqcr_models import EqcrOpinion

    # 获取当前项目
    proj_q = select(Project).where(
        Project.id == project_id,
        Project.is_deleted == False,  # noqa: E712
    )
    project = (await db.execute(proj_q)).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    client_name = project.client_name
    current_year = (
        project.audit_period_end.year if project.audit_period_end else None
    )

    # 查找同客户的历史项目（归一后匹配，兼容"XX集团" vs "XX集团有限公司"等写法变体）
    # 先拉候选（按 client_name 前缀 LIKE 粗筛，再在 Python 侧归一精筛）
    from app.services.client_lookup import normalize_client_name
    normalized_current = normalize_client_name(client_name)

    candidates_q = (
        select(Project)
        .where(
            Project.id != project_id,
            Project.is_deleted == False,  # noqa: E712
        )
        .order_by(Project.audit_period_end.desc())
    )
    all_candidates = list((await db.execute(candidates_q)).scalars().all())

    prior_projects = [
        p for p in all_candidates
        if normalize_client_name(p.client_name) == normalized_current
    ][:years]

    # 获取当前项目的 EQCR 意见
    current_opinions_q = select(EqcrOpinion).where(
        EqcrOpinion.project_id == project_id,
        EqcrOpinion.is_deleted == False,  # noqa: E712
    )
    current_opinions = list((await db.execute(current_opinions_q)).scalars().all())
    current_by_domain = {}
    for op in current_opinions:
        if op.domain not in current_by_domain:
            current_by_domain[op.domain] = {
                "verdict": op.verdict,
                "comment": op.comment,
                "created_at": op.created_at.isoformat() if op.created_at else None,
            }

    # 获取历史项目的 EQCR 意见
    prior_data = []
    for pp in prior_projects:
        pp_opinions_q = select(EqcrOpinion).where(
            EqcrOpinion.project_id == pp.id,
            EqcrOpinion.is_deleted == False,  # noqa: E712
        )
        pp_opinions = list((await db.execute(pp_opinions_q)).scalars().all())
        pp_by_domain = {}
        for op in pp_opinions:
            if op.domain not in pp_by_domain:
                pp_by_domain[op.domain] = {
                    "verdict": op.verdict,
                    "comment": op.comment,
                    "created_at": op.created_at.isoformat() if op.created_at else None,
                }

        pp_year = pp.audit_period_end.year if pp.audit_period_end else None
        prior_data.append({
            "project_id": str(pp.id),
            "project_name": pp.name,
            "year": pp_year,
            "opinions_by_domain": pp_by_domain,
        })

    # 计算差异点
    differences = []
    domains = ["materiality", "estimate", "related_party", "going_concern", "opinion_type"]
    for domain in domains:
        current_verdict = current_by_domain.get(domain, {}).get("verdict")
        for pp_item in prior_data:
            prior_verdict = pp_item["opinions_by_domain"].get(domain, {}).get("verdict")
            if current_verdict and prior_verdict and current_verdict != prior_verdict:
                differences.append({
                    "domain": domain,
                    "current_verdict": current_verdict,
                    "prior_verdict": prior_verdict,
                    "prior_year": pp_item["year"],
                    "prior_project_id": pp_item["project_id"],
                })

    return {
        "project_id": str(project_id),
        "client_name": client_name,
        "current_year": current_year,
        "current_opinions": current_by_domain,
        "prior_years": prior_data,
        "differences": differences,
        "has_differences": len(differences) > 0,
    }


@router.post("/projects/{project_id}/link-prior-year")
async def link_prior_year(
    project_id: UUID,
    payload: LinkPriorYearRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动指定上年项目（兜底，当 client_name 匹配失败时使用）。

    将指定项目的 EQCR 意见作为对比基准返回。
    """
    from app.models.eqcr_models import EqcrOpinion

    # 验证当前项目存在
    proj_q = select(Project).where(
        Project.id == project_id,
        Project.is_deleted == False,  # noqa: E712
    )
    project = (await db.execute(proj_q)).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="当前项目不存在")

    # 验证上年项目存在
    prior_q = select(Project).where(
        Project.id == payload.prior_project_id,
        Project.is_deleted == False,  # noqa: E712
    )
    prior_project = (await db.execute(prior_q)).scalar_one_or_none()
    if prior_project is None:
        raise HTTPException(status_code=404, detail="指定的上年项目不存在")

    # 获取上年项目的 EQCR 意见
    pp_opinions_q = select(EqcrOpinion).where(
        EqcrOpinion.project_id == payload.prior_project_id,
        EqcrOpinion.is_deleted == False,  # noqa: E712
    )
    pp_opinions = list((await db.execute(pp_opinions_q)).scalars().all())
    pp_by_domain = {}
    for op in pp_opinions:
        if op.domain not in pp_by_domain:
            pp_by_domain[op.domain] = {
                "verdict": op.verdict,
                "comment": op.comment,
                "created_at": op.created_at.isoformat() if op.created_at else None,
            }

    pp_year = prior_project.audit_period_end.year if prior_project.audit_period_end else None

    return {
        "linked": True,
        "prior_project_id": str(prior_project.id),
        "prior_project_name": prior_project.name,
        "prior_year": pp_year,
        "opinions_by_domain": pp_by_domain,
    }


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


def _serialize_note(n: EqcrReviewNote) -> dict[str, Any]:
    """序列化 EQCR 独立复核笔记。"""
    return {
        "id": str(n.id),
        "project_id": str(n.project_id),
        "title": n.title,
        "content": n.content,
        "shared_to_team": n.shared_to_team,
        "shared_at": n.shared_at.isoformat() if n.shared_at else None,
        "created_by": str(n.created_by) if n.created_by else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "updated_at": n.updated_at.isoformat() if n.updated_at else None,
    }
