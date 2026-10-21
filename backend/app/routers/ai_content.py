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
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.services import ai_content_log_service
from app.services.project_permission import assert_project_permission

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


def _serialize(log) -> dict:
    """将 AiContentLog ORM 对象序列化为 banner / badge 所需的字典。"""
    target_cell = log.target_cell or ""
    instance_type = target_cell.split(":", 1)[0] if target_cell else None
    return {
        "id": str(log.id),
        "ai_content_log_id": str(log.id),
        "instance_type": instance_type,
        "target_cell": log.target_cell,
        "model": log.model,
        "confidence": float(log.confidence) if log.confidence is not None else None,
        "generated_at": log.generated_at.isoformat() if log.generated_at else None,
        "content": log.generated_content,
        "confirm_action": log.confirm_action,
    }


async def _enrich_target_labels(db: AsyncSession, items: list) -> list:
    """给每条 pending 日志补充 target_label（底稿名 / 附注章节标题）。

    用 str(log.id) 做 dict key（修复原 UUID 对象 key 写 / str 查全 miss）。
    允许多条日志指向同一目标。查询失败降级 None，不毒化外层事务。
    """
    if not items:
        return items

    from sqlalchemy import select, text

    serialized = [_serialize(it) for it in items]

    try:
        async with db.begin_nested():
            # 按 target_cell 前缀分组
            wp_logs = {}  # str(log.id) -> target_cell
            note_logs = {}
            for it, raw in zip(serialized, items):
                lid = str(raw.id)
                tc = raw.target_cell or ""
                if tc.startswith("workpaper:"):
                    wp_logs[lid] = tc
                elif tc.startswith("note:"):
                    note_logs[lid] = tc

            # 底稿标签：从 target_cell 里提取 wp_id，查 working_paper.wp_name
            wp_labels = {}
            if wp_logs:
                wp_ids = set()
                for tc in wp_logs.values():
                    parts = tc.split(":")
                    if len(parts) >= 2:
                        try:
                            wp_ids.add(UUID(parts[1]))
                        except ValueError:
                            pass
                if wp_ids:
                    placeholders = ", ".join(f"'{str(u)}'" for u in wp_ids)
                    rows = (await db.execute(
                        text(f"SELECT id, wp_name FROM working_paper WHERE id IN ({placeholders})")
                    )).fetchall()
                    for row in rows:
                        wp_labels[str(row[0])] = row[1]

            # 附注标签：从 target_cell 里提取 note_section，查 disclosure_notes.section_title
            note_labels = {}
            if note_logs:
                # 提取所有 note_section（target_cell 格式 "note:<note_id>:<section>" 或 "note:<section>"）
                sections = set()
                project_ids = set()
                for raw in items:
                    if raw.project_id:
                        project_ids.add(raw.project_id)
                    tc = raw.target_cell or ""
                    if tc.startswith("note:"):
                        parts = tc.split(":")
                        if len(parts) >= 2:
                            sections.add(parts[-1])
                if sections and project_ids:
                    pid = str(list(project_ids)[0])
                    sec_list = ", ".join(f"'{s}'" for s in sections)
                    rows = (await db.execute(
                        text(f"SELECT note_section, section_title FROM disclosure_notes "
                             f"WHERE project_id = '{pid}' AND note_section IN ({sec_list})")
                    )).fetchall()
                    for row in rows:
                        note_labels[row[0]] = row[1]

            # 回填 target_label
            for it, raw in zip(serialized, items):
                lid = str(raw.id)
                tc = raw.target_cell or ""
                label = None
                if tc.startswith("workpaper:"):
                    parts = tc.split(":")
                    if len(parts) >= 2:
                        label = wp_labels.get(parts[1])
                elif tc.startswith("note:"):
                    parts = tc.split(":")
                    if len(parts) >= 2:
                        label = note_labels.get(parts[-1])
                it["target_label"] = label

    except Exception:
        logger.warning("_enrich_target_labels 查询失败，降级 None", exc_info=True)
        for it in serialized:
            it.setdefault("target_label", None)

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

    走 DisclosureEngine.update_note（盖编辑戳 + 协调器语义）。
    写前检查 edit 权限和合并锁，不满足则抛 HTTPException（由调用方捕获回滚）。
    """
    # edit 无权 → 403
    await assert_project_permission(db, user, log.project_id, "edit")

    # 合并锁 → 423
    from app.services.consol_lock_service import check_consol_lock
    await check_consol_lock(db, log.project_id)

    content = log.revised_content if log.revised_content else log.generated_content
    if not content or not content.strip():
        return {"written": False, "reason": "AI 内容为空，未写入"}

    from app.services.disclosure_engine import DisclosureEngine

    # 读当前附注正文，追加 AI 文本
    from sqlalchemy import select, text as sa_text
    row = (await db.execute(
        sa_text("SELECT text_content, note_section, project_id FROM disclosure_notes WHERE id = :nid"),
        {"nid": str(note_id)},
    )).fetchone()

    if not row:
        return {"written": False, "reason": "附注不存在"}

    current_text = row[0] or ""
    note_section = row[1]
    separator = "\n\n---\n\n" if current_text.strip() else ""
    new_text = current_text + separator + content.strip()

    await DisclosureEngine.update_note(
        db=db,
        note_id=note_id,
        text_content=new_text,
        user_id=user.id,
    )
    await db.flush()

    # 取附注年度（用于 NOTE_SECTION_SAVED 事件）
    note_year = None
    try:
        yr_row = (await db.execute(
            sa_text("SELECT EXTRACT(YEAR FROM audit_period_end)::int FROM projects WHERE id = :pid"),
            {"pid": str(log.project_id)},
        )).scalar()
        note_year = yr_row
    except Exception:
        pass

    return {
        "written": True,
        "note_section": note_section,
        "note_year": note_year,
    }


async def _note_saved_event(note_id, project_id, note_year, note_section):
    """发 NOTE_SECTION_SAVED 事件（附注刷新 / 下游失效）。失败不回滚已提交内容。"""
    try:
        from app.services.event_bus import event_bus, EventPayload
        await event_bus.publish(EventPayload(
            event_type="NOTE_SECTION_SAVED",
            source_id=str(note_id),
            project_id=str(project_id),
            year=note_year,
            detail={"note_section": note_section},
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
    serialized = await _enrich_target_labels(db, items)
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
