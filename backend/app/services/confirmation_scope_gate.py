"""函证路由的项目隔离门（spec attachment-security-baseline 需求 2.1、2.2，ADR-ASB-03）。

挂在 ``routers/confirmations.py`` 的 ``APIRouter(dependencies=[Depends(confirmation_project_gate)])`` 上，
对该路由全部端点生效：

1. 成员级别按请求方法定：GET 只读，其余 edit（归档项目写 ⇒ 423）。判定与 ``require_project_access``
   同一实现（``assert_project_permission``），admin 照常放行。
2. 路径与请求体里的对象必须属于路径项目：函证、附件、挂载记录不属于 ⇒ 404；底稿不属于 ⇒ 422。

改造前：17 个端点只校验登录，函证服务按 id 取数不带项目条件 ⇒ 任意登录用户可读写任意项目的函证与回函附件；
挂载、解绑、识别比对、自动匹配用的角色集不含审计员（``signing_partner`` / ``field_staff`` 也不是系统角色），
审计员挂不了回函。

FastAPI 在解析依赖之前已读过请求体，这里 ``await request.body()`` 取的是同一请求对象上的缓存。
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from typing import Any

import sqlalchemy as sa
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import assert_project_permission, get_current_user
from app.models.attachment_models import Attachment
from app.models.confirmation_models import Confirmation, ConfirmationAttachmentLink
from app.models.core import User
from app.models.workpaper_models import WorkingPaper

_READ_METHODS = frozenset({"GET", "HEAD"})

#: 请求体里指向附件的字段（挂载、回填、自动匹配的回函件，挂载 / 指派时配对的发函件）
BODY_ATTACHMENT_FIELDS = ("attachment_id", "paired_outbound_id")
#: 请求体里指向函证的字段（人工指派）
BODY_CONFIRMATION_FIELDS = ("confirmation_id",)
#: 请求体里指向底稿的字段（创建、更新、批量同步；批量同步另有 ``items[*].wp_id``）
BODY_WORKPAPER_FIELDS = ("wp_id",)


def required_level(method: str) -> str:
    """请求方法 → 项目成员级别：读只要 readonly，其余一律 edit。"""
    return "readonly" if (method or "").upper() in _READ_METHODS else "edit"


async def confirmation_project_gate(
    request: Request,
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """函证路由的路由级依赖：先判项目成员级别，再判路径 / 请求体里的对象归属。"""
    await assert_project_permission(db, current_user, project_id, required_level(request.method))

    params = request.path_params
    confirmation_id = params.get("confirmation_id")
    if confirmation_id is not None:
        await require_confirmations(db, project_id, [confirmation_id])
        link_id = params.get("link_id")
        if link_id is not None:
            await require_link(db, confirmation_id, link_id)
    attachment_id = params.get("attachment_id")
    if attachment_id is not None:
        await require_attachments(db, project_id, [attachment_id])

    body = await _json_body(request)
    if body is None:
        return
    await require_attachments(db, project_id, _texts(body.get(k) for k in BODY_ATTACHMENT_FIELDS))
    await require_confirmations(db, project_id, _texts(body.get(k) for k in BODY_CONFIRMATION_FIELDS))
    workpapers = [body.get(k) for k in BODY_WORKPAPER_FIELDS]
    items = body.get("items")
    if isinstance(items, list):
        workpapers += [item.get("wp_id") for item in items if isinstance(item, dict)]
    await require_workpapers(db, project_id, _texts(workpapers))


# ── 对象归属 ──


async def require_confirmations(db: AsyncSession, project_id: uuid.UUID, raw_ids: Iterable[str]) -> None:
    ids = _uuids(raw_ids, status=404, detail="函证记录不存在")
    if not ids:
        return
    stmt = sa.select(Confirmation.id).where(Confirmation.id.in_(ids), Confirmation.project_id == project_id)
    if set((await db.execute(stmt)).scalars()) != ids:
        raise HTTPException(status_code=404, detail="函证记录不存在")


async def require_attachments(db: AsyncSession, project_id: uuid.UUID, raw_ids: Iterable[str]) -> None:
    ids = _uuids(raw_ids, status=404, detail="附件不存在")
    if not ids:
        return
    stmt = sa.select(Attachment.id).where(
        Attachment.id.in_(ids), Attachment.project_id == project_id, Attachment.is_deleted.is_(False),
    )
    if set((await db.execute(stmt)).scalars()) != ids:
        raise HTTPException(status_code=404, detail="附件不存在")


async def require_link(db: AsyncSession, raw_confirmation_id: str, raw_link_id: str) -> None:
    """挂载记录必须挂在路径里的那笔函证上（函证本身已核对属于路径项目）。"""
    (confirmation_id,) = _uuids([raw_confirmation_id], status=404, detail="函证记录不存在")
    (link_id,) = _uuids([raw_link_id], status=404, detail="附件挂载记录不存在")
    stmt = sa.select(ConfirmationAttachmentLink.confirmation_id).where(ConfirmationAttachmentLink.id == link_id)
    if (await db.execute(stmt)).scalar_one_or_none() != confirmation_id:
        raise HTTPException(status_code=404, detail="附件挂载记录不存在")


async def require_workpapers(db: AsyncSession, project_id: uuid.UUID, raw_ids: Iterable[str]) -> None:
    ids = _uuids(raw_ids, status=422, detail="底稿不属于本项目")
    if not ids:
        return
    stmt = sa.select(WorkingPaper.id).where(
        WorkingPaper.id.in_(ids), WorkingPaper.project_id == project_id, WorkingPaper.is_deleted.is_(False),
    )
    if set((await db.execute(stmt)).scalars()) != ids:
        raise HTTPException(status_code=422, detail="底稿不属于本项目")


# ── 小工具 ──


def _texts(values: Iterable[Any]) -> list[str]:
    """非空字符串才算给了对象 id；空串 / None 表示未指定，类型不对交给请求体校验报 422。"""
    return [v for v in values if isinstance(v, str) and v.strip()]


def _uuids(raw_ids: Iterable[str], *, status: int, detail: str) -> set[uuid.UUID]:
    out: set[uuid.UUID] = set()
    for raw in raw_ids:
        try:
            out.add(uuid.UUID(str(raw).strip()))
        except (ValueError, AttributeError, TypeError):
            raise HTTPException(status_code=status, detail=detail) from None
    return out


async def _json_body(request: Request) -> dict[str, Any] | None:
    if (request.method or "").upper() in _READ_METHODS:
        return None
    raw = await request.body()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None  # 非法 JSON 交给 FastAPI 的请求体校验（422）
    return data if isinstance(data, dict) else None
