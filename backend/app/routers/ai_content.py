"""AI 内容溯源 API — V3 收官增强 Req 6.5 + 第二轮复盘修复

提供轻量级 AI 内容生命周期端点供前端调用：

- GET  /api/projects/{pid}/ai-content/pending      列出待确认 AI 内容 + 计数
- POST /api/ai-content/{log_id}/confirm            确认 AI 内容
- POST /api/ai-content/{log_id}/revise             修订 AI 内容
- POST /api/ai-content/{log_id}/reject             拒绝 AI 内容

底层调用 ai_content_log_service（6.1 已就位）。

第二轮复盘修复（design §6.6）：
- P0 安全漏洞：confirm/revise/reject 接项目鉴权（review 级）
- 确认后经 DisclosureEngine.update_note 追加写回 + 发 NOTE_SECTION_SAVED
- 合并锁 / edit 无权保持 pending（回滚状态流转）
- revise 与 confirm 共用 _confirm_or_revise（写 revised_content）
- target_label enrich 修 key（str(log.id)）+ savepoint 降级
- 底稿类不自动写入（提示复制）

目标标签修复（spec ai-content-pending-target-label，2026-10-30）：上面 R6 的标签修复没生效 ——
底稿查 ``working_paper.wp_name``（列在 ``wp_index``）、附注把 ``target_cell`` 末段当章节号、两条查询同一保存点。
现按 ``target_cell`` 第二段的实例 id 用 ORM 分类查询，口径与 AI 面板宿主标签一致，并补 ``target_position``。
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import (
    assert_project_permission,
    check_consol_lock,
    get_current_user,
    require_project_access,
)
from app.models.core import User
from app.services import ai_content_log_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AI 内容溯源"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ReviseRequest(BaseModel):
    revised_content: str

    @field_validator("revised_content")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("修订内容不能为空")
        return v


def _parse_target(target_cell: str | None) -> tuple[str | None, str | None, str | None]:
    """拆 ``target_cell`` 为（类型, 实例 id 原文, 位置原文）。

    编码以写入方为准：``ai_content_log_service.create`` 存 ``{instance_type}:{instance_id}[:{位置}]``。
    位置是第二个冒号之后的全部原文（本身还可能含冒号），如 ``E5`` / ``正文第一段``。
    """
    if not target_cell:
        return None, None, None
    parts = target_cell.split(":", 2)
    kind = parts[0] or None
    target_id = parts[1] if len(parts) >= 2 and parts[1] else None
    position = parts[2] if len(parts) == 3 and parts[2] else None
    return kind, target_id, position


def _serialize(log) -> dict:
    """将 AiContentLog ORM 对象序列化为 banner / badge 所需的字典。"""
    instance_type, _target_id, position = _parse_target(log.target_cell)
    return {
        "id": str(log.id),
        "ai_content_log_id": str(log.id),
        "instance_type": instance_type,
        "target_cell": log.target_cell,
        "target_position": position,
        "model": log.model,
        "confidence": float(log.confidence) if log.confidence is not None else None,
        "generated_at": log.generated_at.isoformat() if log.generated_at else None,
        "content": log.generated_content,
        "confirm_action": log.confirm_action,
    }


def _coerce_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


async def _workpaper_labels(db: AsyncSession, project_id: UUID, ids: set[UUID]) -> dict[UUID, str]:
    """底稿 id → ``"{wp_code} {wp_name}"``。先当 ``working_paper.id``（经 ``wp_index`` 取名），没取到的再当 ``wp_index.id``。"""
    from sqlalchemy import select

    from app.models.workpaper_models import WorkingPaper, WpIndex

    labels: dict[UUID, str] = {}
    rows = (await db.execute(
        select(WorkingPaper.id, WpIndex.wp_code, WpIndex.wp_name)
        .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
        .where(WorkingPaper.project_id == project_id, WorkingPaper.id.in_(list(ids)))
    )).all()
    for wp_id, code, name in rows:
        labels[wp_id] = f"{code} {name}".strip()
    rest = ids - labels.keys()
    if rest:
        # 早期写入的记录存的是索引 id（共享库现存一条，2026-10-30 现查）
        rows = (await db.execute(
            select(WpIndex.id, WpIndex.wp_code, WpIndex.wp_name)
            .where(WpIndex.project_id == project_id, WpIndex.id.in_(list(rest)))
        )).all()
        for idx_id, code, name in rows:
            labels[idx_id] = f"{code} {name}".strip()
    return labels


async def _note_labels(db: AsyncSession, project_id: UUID, ids: set[UUID]) -> dict[UUID, str]:
    """附注 id（``disclosure_notes.id``）→ ``"{note_section} {section_title}"``。"""
    from sqlalchemy import select

    from app.models.report_models import DisclosureNote

    rows = (await db.execute(
        select(DisclosureNote.id, DisclosureNote.note_section, DisclosureNote.section_title)
        .where(DisclosureNote.project_id == project_id, DisclosureNote.id.in_(list(ids)))
    )).all()
    return {note_id: f"{section} {title}".strip() for note_id, section, title in rows}


async def _lookup_labels(db: AsyncSession, what: str, fetch, project_id: UUID, ids: set[UUID]) -> dict[UUID, str]:
    """一类标签一个保存点：查询失败只让这一类为空，不影响另一类，也不中止调用方事务。"""
    if not ids:
        return {}
    try:
        async with db.begin_nested():
            return await fetch(db, project_id, ids)
    except Exception:
        logger.warning("待确认 AI 内容：%s标签查询失败，该类标签置空", what, exc_info=True)
        return {}


async def _enrich_target_labels(db: AsyncSession, project_id: UUID, items: list) -> list:
    """给每条待确认日志补 ``target_label``（底稿 / 附注的展示名）。

    - 口径与 AI 面板宿主标签一致（``ai_chat/host_context.py`` 的 ``_label_workpaper`` / ``_label_note``）。
    - 实例 id 取 ``target_cell`` 第二段（附注是 ``disclosure_notes.id``，不是章节号）；不是 UUID 的不查。
    - 只取本项目的行：``target_cell`` 是存下来的字符串，不能凭它读别的项目的名称。
    - 目标已删除时仍显示原名称，便于认出这段 AI 内容原本写给谁。
    - 全部 ORM 绑定参数，不拼 SQL。
    """
    serialized = [_serialize(it) for it in items]
    if not items:
        return serialized

    targets = []
    wp_ids: set[UUID] = set()
    note_ids: set[UUID] = set()
    for raw in items:
        kind, target_id, _position = _parse_target(raw.target_cell)
        uid = _coerce_uuid(target_id)
        targets.append((kind, uid))
        if uid is None:
            continue
        if kind == "workpaper":
            wp_ids.add(uid)
        elif kind == "note":
            note_ids.add(uid)

    wp_labels = await _lookup_labels(db, "底稿", _workpaper_labels, project_id, wp_ids)
    note_labels = await _lookup_labels(db, "附注", _note_labels, project_id, note_ids)

    for it, (kind, uid) in zip(serialized, targets):
        label = None
        if uid is not None and kind == "workpaper":
            label = wp_labels.get(uid)
        elif uid is not None and kind == "note":
            label = note_labels.get(uid)
        it["target_label"] = label
    return serialized


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


async def _load_log_or_404(db: AsyncSession, log_id: UUID):
    """加载 AiContentLog 或抛 404。"""
    try:
        return await ai_content_log_service.get_by_id(db=db, log_id=log_id)
    except ai_content_log_service.AiContentLogNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


def _note_target_id(log) -> UUID | None:
    """从 target_cell 提取附注 note_id（如有）。

    target_cell 格式：
    - "note:<note_id>"  或 "note:<note_id>:<位置描述>"
    - "workpaper:..." → 非附注，返回 None
    """
    tc = log.target_cell or ""
    if not tc.startswith("note:"):
        return None
    parts = tc.split(":")
    if len(parts) >= 2:
        try:
            return UUID(parts[1])
        except ValueError:
            return None
    return None


async def _writeback_note(db: AsyncSession, log, user, note_id: UUID) -> dict:
    """把确认 / 修订后的 AI 文本追加进附注 ``text_content``。

    经 ``DisclosureEngine(db).update_note`` 写入（盖「最近一次编辑」），提交后由调用方发 NOTE_SECTION_SAVED。
    写前检查 edit 权限和合并锁，不满足则抛 HTTPException（由调用方捕获回滚）。
    """
    # edit 无权 → 403
    await assert_project_permission(db, user, log.project_id, "edit")

    # 合并锁 → 423（锁定时 check_consol_lock 抛 HTTPException(423)）
    await check_consol_lock(project_id=log.project_id, db=db)

    content = log.revised_content if log.revised_content else log.generated_content
    if not content or not content.strip():
        return {"written": False, "reason": "AI 内容为空，未写入"}

    from sqlalchemy import select

    from app.models.report_models import DisclosureNote
    from app.services.disclosure_engine import DisclosureEngine

    # 只认本日志所属项目里未删除的附注：上面的 edit 权限与合并锁都按 log.project_id 判，
    # 写入目标必须在同一个项目里（target_cell 里的附注 id 是存下来的字符串，不能单凭它跨项目写）。
    # 用 ORM 比较 UUID：原生 SQL 绑 str(uuid) 在 SQLite（存 32 位十六进制）上恒匹配不到。
    row = (await db.execute(
        select(DisclosureNote.text_content, DisclosureNote.note_section, DisclosureNote.year).where(
            DisclosureNote.id == note_id,
            DisclosureNote.project_id == log.project_id,
            DisclosureNote.is_deleted.is_(False),
        )
    )).first()

    if row is None:
        return {"written": False, "reason": "附注不存在"}

    current_text = row.text_content or ""
    separator = "\n\n---\n\n" if current_text.strip() else ""
    new_text = current_text + separator + content.strip()

    # update_note 是实例方法：盖「最近一次编辑」并走附注写入的统一校验
    note = await DisclosureEngine(db).update_note(
        note_id,
        text_content=new_text,
        user_id=user.id,
    )
    if note is None:
        return {"written": False, "reason": "附注不存在"}
    await db.flush()

    return {
        "written": True,
        "note_section": row.note_section,
        "note_year": row.year,
    }


async def _note_saved_event(note_id, project_id, note_year, note_section):
    """发 NOTE_SECTION_SAVED 事件（附注刷新 / 下游失效）。失败不回滚已提交内容。"""
    try:
        from app.models.audit_platform_schemas import EventPayload, EventType
        from app.services.event_bus import event_bus

        # 与附注编辑端点（disclosure_notes.update_note）同一载荷：订阅方从 extra.section_code 定位章节
        await event_bus.publish(EventPayload(
            event_type=EventType.NOTE_SECTION_SAVED,
            project_id=project_id,
            year=note_year,
            extra={"section_code": note_section or str(note_id), "action": "update"},
        ))
    except Exception:
        logger.warning("AI 确认写附注已提交但 NOTE_SECTION_SAVED 发布失败", exc_info=True)


async def _confirm_or_revise(
    db: AsyncSession,
    user: User,
    log_id: UUID,
    revised_content: str | None = None,
) -> dict:
    """确认或修订 AI 内容的共用逻辑。

    1. 加载日志 → 鉴权（review 级，确认/修订都是复核动作）
    2. 调 service 更新状态
    3. 附注类：尝试写回（edit + 合并锁检查）；失败 → 回滚保持 pending
    4. 底稿类：不自动写，提示复制
    """
    log = await _load_log_or_404(db, log_id)

    # P0 修复：项目鉴权（review 级）
    await assert_project_permission(db, user, log.project_id, "review")

    # 更新状态
    try:
        if revised_content is not None:
            log = await ai_content_log_service.revise(
                db=db, log_id=log_id, user_id=user.id,
                revised_content=revised_content,
            )
        else:
            log = await ai_content_log_service.confirm(
                db=db, log_id=log_id, user_id=user.id,
            )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    note_id = _note_target_id(log)
    result: dict = {"id": str(log.id), "confirm_action": log.confirm_action}

    if note_id is None:
        # 底稿类：不自动写入。
        await db.commit()
        result["writeback"] = {
            "written": False,
            "reason": "底稿内容不自动写入，请在底稿页面复制到目标位置",
        }
        return result

    # 附注类：edit 无权（403）/ 合并锁（423）→ 回滚状态流转、保持 pending。
    try:
        writeback = await _writeback_note(db, log, user, note_id)
    except HTTPException as exc:
        await db.rollback()
        reason = "项目已被合并锁定，内容保持待确认" if exc.status_code == 423 \
            else "当前用户无编辑权限，内容保持待确认"
        return {
            "id": str(log_id),
            "confirm_action": "pending",
            "writeback": {"written": False, "skipped": True, "reason": reason},
        }

    await db.commit()

    # commit 成功后发 NOTE_SECTION_SAVED。失败不回滚已提交内容。
    if writeback.get("written"):
        await _note_saved_event(
            note_id, log.project_id,
            writeback.get("note_year"),
            writeback.get("note_section"),
        )

    result["writeback"] = writeback
    return result


# ---------------------------------------------------------------------------
# GET /api/projects/{project_id}/ai-content/pending
# ---------------------------------------------------------------------------


@router.get("/api/projects/{project_id}/ai-content/pending")
async def list_pending_ai_content(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_project_access("readonly")),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """返回项目下未确认的 AI 内容清单 + 总数（前端 banner / badge 用）。"""
    items = await ai_content_log_service.list_pending_by_project(
        db=db, project_id=project_id, limit=limit
    )
    count = await ai_content_log_service.count_pending_by_project(
        db=db, project_id=project_id
    )
    serialized = await _enrich_target_labels(db, project_id, items)
    return {
        "count": count,
        "items": serialized,
    }


# ---------------------------------------------------------------------------
# POST /api/ai-content/{log_id}/confirm
# ---------------------------------------------------------------------------


@router.post("/api/ai-content/{log_id}/confirm")
async def confirm_ai_content(
    log_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """确认 AI 内容（confirm_action=confirmed）。

    - 鉴权：确认是复核动作，需项目 review 级（含 admin）。
    - 附注类：经 DisclosureEngine.update_note 追加写回 + 发 NOTE_SECTION_SAVED。
    - edit 无权 / 合并锁：回滚保持 pending + 返回 reason。
    - 底稿类：不自动写入，提示复制。
    """
    return await _confirm_or_revise(db, user, log_id)


# ---------------------------------------------------------------------------
# POST /api/ai-content/{log_id}/revise
# ---------------------------------------------------------------------------


@router.post("/api/ai-content/{log_id}/revise")
async def revise_ai_content(
    log_id: UUID,
    payload: ReviseRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """修订 AI 内容（confirm_action=revised + 写 revised_content）。

    鉴权与写回语义同确认；附注类写入 ``revised_content``（修订后的文本）。
    """
    return await _confirm_or_revise(db, user, log_id, revised_content=payload.revised_content)


# ---------------------------------------------------------------------------
# POST /api/ai-content/{log_id}/reject
# ---------------------------------------------------------------------------


@router.post("/api/ai-content/{log_id}/reject")
async def reject_ai_content(
    log_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """拒绝 AI 内容（confirm_action=rejected）。需项目 review 级，不写入任何文档。"""
    log = await _load_log_or_404(db, log_id)
    await assert_project_permission(db, user, log.project_id, "review")
    try:
        log = await ai_content_log_service.reject(
            db=db, log_id=log_id, user_id=user.id
        )
        await db.commit()
        return {"id": str(log.id), "confirm_action": log.confirm_action}
    except ai_content_log_service.AiContentLogNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
