"""合并附注重新汇总的 platform durable job executor（B4）。"""
from __future__ import annotations

import sqlalchemy as sa
from fastapi import HTTPException

from app.core.database import async_session
from app.deps import assert_project_permission, check_consol_lock
from app.models.core import User
from app.services import platform_job_service as jobs
from app.services.consol_note_subtree_reaggregate import (
    ReaggregateCancelled,
    reaggregate_subtree,
)
from app.services.platform_job_registry import (
    ExecutorOutcome,
    ProgressReporter,
    register_executor,
)

OPERATION = "consol_note_reaggregate"
MAX_SECTION_IDS = 500


class ConsolReaggregateJobError(RuntimeError):
    retryable = False


class ConsolReaggregateLeaseLost(ConsolReaggregateJobError):
    pass


async def execute_consol_note_reaggregate(
    claim: jobs.PlatformJobClaim,
    report: ProgressReporter,
) -> ExecutorOutcome:
    """重新校验项目/合并锁/节点范围，按章节进度执行，租约丢失时外层事务整体回滚。"""
    payload = claim.payload_ref
    try:
        year = int(payload.get("year"))
    except (TypeError, ValueError) as exc:
        raise ConsolReaggregateJobError("重新汇总任务缺少有效年度") from exc
    if not 2000 <= year <= 2100:
        raise ConsolReaggregateJobError("重新汇总任务年度超出 2000..2100")
    raw_sections = payload.get("section_ids")
    if raw_sections is not None and not isinstance(raw_sections, list):
        raise ConsolReaggregateJobError("重新汇总任务 section_ids 形态无效")
    if isinstance(raw_sections, list) and len(raw_sections) > MAX_SECTION_IDS:
        raise ConsolReaggregateJobError("重新汇总任务 section_ids 超过 500 项上限")
    section_ids = None if raw_sections is None else [str(item) for item in raw_sections]
    node_key = payload.get("node_key")
    node_key = str(node_key) if node_key else None
    template_type = payload.get("template_type") or payload.get("standard")
    template_type = str(template_type) if template_type else None

    if not await report(0, None, "校验项目权限、合并锁和企业树", "authorizing"):
        raise ConsolReaggregateLeaseLost("重新汇总任务租约已失效")

    try:
        async with async_session() as db:
            user = (
                await db.execute(sa.select(User).where(User.id == claim.actor_id))
            ).scalar_one_or_none()
            if user is None:
                raise ConsolReaggregateJobError("重新汇总任务发起人已不存在")
            await assert_project_permission(db, user, claim.project_id, "edit")
            await check_consol_lock(project_id=claim.project_id, db=db)

            from app.services.consol_node_scope import resolve_node_scope, resolve_requested_node_key
            from app.services.consol_note_aggregation_service import validate_lineage_dag
            from app.services.consol_note_formula_service import note_template_type

            requested = {
                key: value for key, value in {
                    "node_key": node_key,
                    "section_ids": section_ids,
                    "template_type": template_type,
                }.items() if value is not None
            }
            resolved_node_key = resolve_requested_node_key(node_key, requested)
            scope = await resolve_node_scope(db, claim.project_id, year, resolved_node_key)
            if not await validate_lineage_dag(claim.project_id, db):
                raise ConsolReaggregateJobError("合并层级链存在循环引用，无法汇总")
            if payload.get("standard") and payload.get("template_type") and (
                note_template_type(str(payload["standard"])) != note_template_type(str(payload["template_type"]))
            ):
                raise ConsolReaggregateJobError("standard 与 template_type 指向不同附注模板")

            async def progress(current: int, total: int, message: str) -> bool:
                return await report(current, total, message, "reaggregating")

            result = await reaggregate_subtree(
                db,
                claim.project_id,
                scope.year,
                node_key=scope.node_key,
                section_ids=section_ids,
                template_type=template_type,
                tree=scope.tree,
                progress=progress,
            )
            await db.commit()
    except ReaggregateCancelled as exc:
        # 未 commit 的外层 session 在 context exit 时回滚，保证取消没有半套章节副作用。
        raise ConsolReaggregateLeaseLost(str(exc)) from exc
    except HTTPException as exc:
        raise ConsolReaggregateJobError(str(exc.detail)) from exc
    except Exception:
        raise

    total = int(result.get("sections_processed") or 0)
    if not await report(total, total, "重新汇总完成，正在保存结果", "finalizing"):
        raise ConsolReaggregateLeaseLost("重新汇总任务租约已失效")
    return ExecutorOutcome(result_ref={"result": result})


register_executor(OPERATION, execute_consol_note_reaggregate)
