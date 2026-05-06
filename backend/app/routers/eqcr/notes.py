"""EQCR 独立复核笔记 CRUD + 分享"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import Project, User
from app.models.eqcr_models import EqcrReviewNote

from .schemas import EqcrNoteCreate, EqcrNoteUpdate

router = APIRouter()


def _serialize_note(n: EqcrReviewNote) -> dict:
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


@router.get("/projects/{project_id}/notes")
async def list_eqcr_notes(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出本人在该项目的 EQCR 独立复核笔记。"""
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
    """创建一条 EQCR 独立复核笔记。"""
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
    """分享单条笔记到项目组。"""
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

    if note.shared_to_team:
        return _serialize_note(note)

    now = datetime.now(timezone.utc)
    note.shared_to_team = True
    note.shared_at = now

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
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(project, "wizard_state")

    await db.commit()
    await db.refresh(note)
    return _serialize_note(note)
