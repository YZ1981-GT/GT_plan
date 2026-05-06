"""EQCR 关联方 CRUD 端点（经理级可写，EQCR 只读）"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.related_party_models import RelatedPartyRegistry, RelatedPartyTransaction
from app.models.staff_models import ProjectAssignment, StaffMember

from .schemas import (
    VALID_RELATION_TYPES,
    VALID_TRANSACTION_TYPES,
    WRITABLE_PROJECT_ROLES,
    RelatedPartyCreate,
    RelatedPartyUpdate,
    RelatedPartyTransactionCreate,
    RelatedPartyTransactionUpdate,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# 权限检查
# ---------------------------------------------------------------------------


async def _check_project_write_permission(
    db: AsyncSession, user: User, project_id: UUID
) -> None:
    """检查用户是否有项目写入权限（经理级角色或系统 admin）。"""
    if user.role and user.role.value == "admin":
        return

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


# ---------------------------------------------------------------------------
# 序列化
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


# ---------------------------------------------------------------------------
# 关联方注册 CRUD
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 关联方交易 CRUD
# ---------------------------------------------------------------------------


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
