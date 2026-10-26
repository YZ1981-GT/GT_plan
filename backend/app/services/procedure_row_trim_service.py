"""程序表行级裁剪（细裁，方案一）：按 (底稿, 程序表, 程序号) 定位程序行任务，再走既有裁剪服务。

spec procedure-trim-generation-delegation-chain 需求 6 / ADR-6。控制台的「裁剪 / 恢复」原先只改页面里的行状态
随 ``/save`` 整页保存，到不了程序行任务 ⇒ 委派和可见性都看不到细裁结果。

- 定位：底稿与 wp_index（须属本项目，否则 404）→ ``resolve_program_template_code(sheet_name, wp_code)`` 得程序表码
  → 本底稿这张程序表上程序号相同的全部有效任务。模板改版后同一行可能有新旧两条定义的任务，按程序号一起裁、
  一起恢复（只按当前定义找，旧定义的不适用任务就永远恢复不了）。
- 裁剪时一条任务都没有 ⇒ 按程序模板（``procedure_table_templates.json`` 里 ``seq`` 等于程序号的那一行）算出这一行
  的定义（内容寻址，与导入器同一算法），定义与任务都 ON CONFLICT 插入并绑定本底稿 —— 不整表物化（库里同模板码
  还可能有别的来源的定义，整表物化会把它们一并建成任务）。模板里也没有这一行（自加的行、无模板的程序表）⇒ 422
  ``row_trim_unsupported``：这一行没有任务、本就委派不了，控制台只在页面上标记。恢复时没有不适用的任务 ⇒ 无变化。
- 裁剪 / 恢复：``ProcedureTrimService.set_row_not_applicable / restore_row_execute``，历史、事件、取消委派都走
  同一条路；恢复后任务回到待委派。只恢复不适用的任务（别的原因取消的任务不归细裁管）。

只 flush 不 commit。
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procedure_models import ProcedureRowDefinition, ProcedureRowTask
from app.models.workpaper_models import WorkingPaper, WpIndex

ROW_TRIM_UNSUPPORTED = "row_trim_unsupported"
ROW_DELEGATE_UNSUPPORTED = "row_delegate_unsupported"
ROW_TRIMMED = "row_trimmed"
NOT_APPLICABLE = "not_applicable"
#: 行级适用性决定的历史事件（控制台细裁 / 裁剪方案的行条目），展示投影据最近一次判断是否已恢复。
#: 粗裁级联取消与粗裁恢复执行（scheme_scope_cascade / scheme_scope_restore）是整张底稿的决定，不算：粗裁期间底稿在
#: 回收站、页面没被改过，恢复后页面原有的状态（旧的页面裁剪、模板默认的不适用）照旧。
ROW_TRIM_EVENTS = ("trim_not_applicable", "scheme_not_applicable")
ROW_RESTORE_EVENTS = ("trim_restore", "scheme_restore")


@dataclass(frozen=True)
class RowTarget:
    tasks: tuple[ProcedureRowTask, ...]
    template_code: str
    program_no: str
    created: bool


def normalize_program_no(value) -> str:
    """程序号统一成字符串：``1`` / ``1.0`` / ``"1"`` → ``"1"``（与定义导入同口径）。"""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value if value is not None else "").strip()
    try:
        num = float(text)
    except ValueError:
        return text
    return str(int(num)) if num.is_integer() else text


def _unsupported(message: str) -> HTTPException:
    return HTTPException(status_code=422, detail={"error": ROW_TRIM_UNSUPPORTED, "message": message})


async def _create_task(db: AsyncSession, project_id: UUID, wp: WorkingPaper, wi: WpIndex,
                       template_code: str, definition: dict) -> bool:
    """插入这一行的定义与任务。两人同时裁同一张新表时先查后插会撞唯一键 ⇒ 都 ON CONFLICT DO NOTHING。"""
    await db.execute(pg_insert(ProcedureRowDefinition).values(
        definition_key=definition["definition_key"], template_code=definition["template_code"],
        template_revision_hash=definition["template_revision_hash"], sheet_key=definition["sheet_key"],
        source_locator=definition["source_locator"], program_no=definition.get("program_no"),
        procedure_text=definition["procedure_text"], ref_snapshot=definition["ref_snapshot"],
        legacy_aliases=definition["legacy_aliases"], normalized_content=definition["normalized_content"],
    ).on_conflict_do_nothing(index_elements=[ProcedureRowDefinition.definition_key]))
    stmt = pg_insert(ProcedureRowTask).values(
        project_id=project_id, wp_index_id=wi.id, wp_id=wp.id,
        definition_key=definition["definition_key"], sheet_key=template_code, wp_code=wi.wp_code,
        sheet_name=wi.wp_name or template_code, program_no=normalize_program_no(definition.get("program_no")),
        procedure_text=definition["procedure_text"], ref_snapshot=list(definition.get("ref_snapshot") or []),
        definition_revision_hash=definition["template_revision_hash"], audit_cycle_snapshot=wi.audit_cycle or "A",
        applicability_status="execute", workflow_status="unassigned",
    ).on_conflict_do_nothing(
        index_elements=[ProcedureRowTask.project_id, ProcedureRowTask.wp_index_id,
                        ProcedureRowTask.sheet_key, ProcedureRowTask.definition_key],
        index_where=ProcedureRowTask.is_deleted == sa.false(),
    )
    created = bool((await db.execute(stmt)).rowcount)
    await db.flush()
    return created


async def resolve_row_tasks(
    db: AsyncSession, project_id: UUID, wp_id: UUID, sheet_name: str, program_no, *, create: bool
) -> RowTarget:
    """本底稿这张程序表上这一程序号的全部有效任务（``create`` 时一条都没有就建一条），并绑定到本底稿。"""
    from app.routers.wp_render_strategies._a_program import resolve_program_template_code
    from app.services.procedure_definition_importer import ProcedureDefinitionImporter
    from app.services.procedure_table_auto_service import get_template

    row = (await db.execute(
        sa.select(WorkingPaper, WpIndex).join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id).where(
            WorkingPaper.id == wp_id,
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
            WpIndex.is_deleted == sa.false(),
        )
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="底稿不存在")
    wp, wi = row
    template_code = resolve_program_template_code(sheet_name or "", wi.wp_code)
    no = normalize_program_no(program_no)

    sheet_tasks = sa.select(ProcedureRowTask).where(
        ProcedureRowTask.project_id == project_id,
        ProcedureRowTask.wp_index_id == wi.id,
        ProcedureRowTask.sheet_key == template_code,
        ProcedureRowTask.is_deleted == sa.false(),
    ).order_by(ProcedureRowTask.created_at, ProcedureRowTask.id).with_for_update()

    async def _same_row() -> list[ProcedureRowTask]:
        rows = (await db.execute(sheet_tasks)).scalars().all()
        return [t for t in rows if normalize_program_no(t.program_no) == no]

    tasks = await _same_row()
    created = False
    if not tasks and create:
        template = get_template(template_code)
        items = [it for it in ((template or {}).get("items") or []) if isinstance(it, dict)]
        if not any(normalize_program_no(it.get("seq")) == no for it in items):
            raise _unsupported(f"第 {no} 条没有程序行任务，也不是程序模板 {template_code} 里的程序（如自加的行），"
                               "只能在页面上标记，不影响委派")
        result = ProcedureDefinitionImporter.build_from_json_template(template_code, template_code, template)
        definition = next(d for d in result.definitions if normalize_program_no(d.get("program_no")) == no)
        created = await _create_task(db, project_id, wp, wi, template_code, definition)
        tasks = await _same_row()
        if not tasks:
            raise HTTPException(status_code=409, detail="程序行任务创建失败，请重试")
    unbound = [t for t in tasks if t.wp_id is None]
    for t in unbound:
        t.wp_id = wp.id
    if unbound:
        await db.flush()
    return RowTarget(tuple(tasks), template_code, no, created)


async def trim_row(
    db: AsyncSession, project_id: UUID, wp_id: UUID, sheet_name: str, program_no, *,
    actor_user_id: UUID | None, reason: str, request_id: str | None = None,
) -> dict:
    """这一程序行 → 不适用（已不适用的任务不重复记历史）。"""
    from app.services.procedure_trim_service import ProcedureTrimService

    target = await resolve_row_tasks(db, project_id, wp_id, sheet_name, program_no, create=True)
    svc = ProcedureTrimService(db)
    outs = [
        await svc.set_row_not_applicable(project_id, t.id, actor_user_id=actor_user_id, reason=reason,
                                         request_id=request_id)
        for t in target.tasks
    ]
    return {
        "task_ids": [o["task_id"] for o in outs],
        "changed": any(o["changed"] for o in outs),
        "applicability_status": NOT_APPLICABLE,
        "program_no": target.program_no,
        "template_code": target.template_code,
    }


async def restore_row(
    db: AsyncSession, project_id: UUID, wp_id: UUID, sheet_name: str, program_no, *,
    actor_user_id: UUID | None, reason: str | None = None, request_id: str | None = None,
) -> dict:
    """这一程序行恢复执行：不适用的任务回到待委派（须重新委派）；没有不适用的任务 ⇒ 无变化。"""
    from app.services.procedure_trim_service import ProcedureTrimService

    target = await resolve_row_tasks(db, project_id, wp_id, sheet_name, program_no, create=False)
    svc = ProcedureTrimService(db)
    outs = [
        await svc.restore_row_execute(project_id, t.id, actor_user_id=actor_user_id, request_id=request_id,
                                      reason=reason)
        for t in target.tasks if t.applicability_status == NOT_APPLICABLE
    ]
    # 恢复会清空执行人（Property P9：不自动恢复原执行人）⇒ 回执带原执行人姓名，页面提示「原执行人已清除，请重新委派」
    previous_ids = {o["previous_assignee_staff_id"] for o in outs if o.get("previous_assignee_staff_id")}
    previous = await _staff_names(db, previous_ids)
    return {
        "task_ids": [o["task_id"] for o in outs],
        "changed": any(o["changed"] for o in outs),
        "applicability_status": "execute",
        "requires_reassign": bool(outs),
        "previous_assignees": previous,
        "program_no": target.program_no,
        "template_code": target.template_code,
    }


async def _staff_names(db: AsyncSession, staff_ids: set) -> list[str]:
    if not staff_ids:
        return []
    from app.models.staff_models import StaffMember

    ids = [UUID(str(i)) for i in staff_ids]
    rows = (await db.execute(sa.select(StaffMember.name).where(StaffMember.id.in_(ids)))).scalars()
    return sorted({n for n in rows if n})


async def ensure_row_task_for_delegation(
    db: AsyncSession, project_id: UUID, wp_id: UUID, sheet_name: str, program_no,
) -> dict:
    """逐行委派（spec procedure-chain-followup-closure R2.2）：取 / 建这一程序行的任务并绑定本底稿。

    程序行任务开关关闭时控制台的程序行没有任务字段，管理者点「委派」时按需建（与按行裁剪同一套定位 / 建任务）；
    之后走既有的按任务委派预览 → 应用。自加的行（不是模板程序）422；这一行的任务都已裁剪 409（恢复执行后再委派）。
    """
    try:
        target = await resolve_row_tasks(db, project_id, wp_id, sheet_name, program_no, create=True)
    except HTTPException as exc:
        if isinstance(exc.detail, dict) and exc.detail.get("error") == ROW_TRIM_UNSUPPORTED:
            raise HTTPException(status_code=422, detail={
                "error": ROW_DELEGATE_UNSUPPORTED,
                "message": "这一行不是程序模板里的程序（如自加的行），没有程序行任务，不能单独委派；可直接在页面上填写执行情况",
            }) from exc
        raise
    tasks = [t for t in target.tasks if t.applicability_status != NOT_APPLICABLE]
    if not tasks:
        raise HTTPException(status_code=409, detail={
            "error": ROW_TRIMMED, "message": "这一行已裁剪为不适用，恢复执行后才能委派",
        })
    first = tasks[0]
    return {
        "task_ids": [str(t.id) for t in tasks],
        "created": target.created,
        "template_code": target.template_code,
        "program_no": target.program_no,
        "assignee_staff_id": str(first.assignee_staff_id) if first.assignee_staff_id else None,
        "reviewer_staff_id": str(first.reviewer_staff_id) if first.reviewer_staff_id else None,
    }
