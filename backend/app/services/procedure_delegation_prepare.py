"""委派预览前置：导入当前版本程序行定义 → 物化缺的行任务 → 绑定已生成的底稿 —— spec procedure-chain-followup-closure R2.1。

原先预览只物化「库里已有定义」的行：定义只有裁剪某一行时才顺带写入，新项目恒 0 个目标、也不说为什么；物化出的任务
``wp_id`` 为空（只有程序行任务开关打开时，生成底稿才会绑定），委派后底稿页按任务找不到底稿。

- 在 SAVEPOINT 里做：失败只回滚这一步，预览照常继续，回执 ``materialization.error`` 写明原因。
- 物化只用当前模板版本的定义键（见 ``procedure_row_definitions``），只在有缺的行时才写（已有任务只刷新展示快照，
  没必要每次预览都改一遍）。
- 目标为 0 时给出原因（``empty_target_hint``），前端照着显示，不再只有一个 0。

只 flush 不 commit。
"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WorkingPaper
from app.services.procedure_row_definitions import ensure_current_definitions

logger = logging.getLogger(__name__)


async def prepare_row_tasks(
    db: AsyncSession, materialization, project_id: UUID, wp_index_ids: list[UUID], *, actor_user_id: UUID,
) -> dict:
    out: dict = {
        "definitions_created": 0, "tasks_created": 0, "tasks_bound": 0, "with_program_table": 0, "error": None,
    }
    if not wp_index_ids:
        return out
    try:
        async with db.begin_nested():
            meta = await materialization._load_wp_indexes(project_id, wp_index_ids)
            out["definitions_created"], keys = await ensure_current_definitions(
                db, {m["wp_code"] for m in meta.values()},
            )
            out["with_program_table"] = sum(1 for m in meta.values() if keys.get(m["wp_code"]))
            pending = 0
            for wp_index_id in meta:
                overlay = await materialization.build_row_overlay(
                    project_id, wp_index_id, definition_keys_by_wp_code=keys,
                )
                pending += sum(1 for r in overlay if r.get("materialization_required"))
            if pending:
                result = await materialization.materialize(
                    project_id, list(meta), definition_keys_by_wp_code=keys, actor_user_id=actor_user_id,
                )
                out["tasks_created"] = int(result.get("created") or 0)
            papers = (await db.execute(sa.select(WorkingPaper.wp_index_id, WorkingPaper.id).where(
                WorkingPaper.project_id == project_id,
                WorkingPaper.wp_index_id.in_(list(meta)),
                WorkingPaper.is_deleted == sa.false(),
            ).order_by(WorkingPaper.created_at))).all()
            seen: set[UUID] = set()
            for wp_index_id, wp_id in papers:
                if wp_index_id in seen:  # 同一底稿索引只认最早生成的那份
                    continue
                seen.add(wp_index_id)
                bound = await materialization.bind_working_paper(project_id, wp_index_id, wp_id)
                out["tasks_bound"] += int(bound.get("bound") or 0)
    except Exception as exc:  # noqa: BLE001 — 前置失败不拖垮预览，如实回报
        logger.warning("委派预览前置导入 / 物化失败 project=%s: %s", project_id, exc, exc_info=True)
        out["error"] = f"程序行定义导入或任务生成失败：{type(exc).__name__}"
    return out


def empty_target_hint(
    *, candidate_ids: list[UUID] | None, retained_ids: list[UUID] | None, prep: dict | None,
    trimmed_excluded: int, unassigned_only: bool,
) -> str:
    """目标为 0 的原因（按最可能的先后判断）。"""
    if candidate_ids is None:
        return "所选程序行任务不存在、已删除，或已裁剪为不适用"
    if not candidate_ids:
        return "所选范围内没有底稿"
    if not retained_ids:
        return "所选底稿都已裁剪或在回收站，不能委派"
    if prep and prep.get("error"):
        return str(prep["error"])
    if prep is not None and not prep.get("with_program_table"):
        return "所选底稿没有程序表模板（不在程序表库里），无法按程序行委派"
    if trimmed_excluded:
        return "程序行都已裁剪为不适用，恢复执行后才能委派"
    if unassigned_only:
        return "程序行都已分配（当前只委派未分配的行）"
    return "没有可委派的程序行"
