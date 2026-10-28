"""程序表行「状态」覆盖值与行级适用性对齐（spec procedure-chain-hardening-and-java-contracts R4）。

程序表一行的状态有两个来源：

- 程序行任务的适用性（细裁的权威记录，``procedure_row_tasks.applicability_status``）；
- 字段覆盖值（控制台里点的「执行中 / 已完成」，``workpaper_field_overrides``，
  scope = ``procedure_table:{程序表码}``、item_key = 程序号、field = ``status``）。

渲染时先合并覆盖值、再叠加任务投影：不适用的任务一律显示不适用；但恢复后投影只把「不适用」改回待执行，
覆盖值里裁剪前点过的「执行中」会原样露出来 ⇒ 无人执行却显示执行中。A 循环进度统计（``wp_progress_service``）
也直接读覆盖值。

规则：行级适用性变化（控制台细裁、任务级裁剪 / 恢复端点、裁剪方案的行条目）之后，**已有的**状态覆盖值在同一事务里
改成：裁剪 ⇒ ``not_applicable``，恢复 ⇒ ``pending``。没有覆盖值的不新建（页面状态由任务投影给出，进度统计的分母不变）。
年度 = 项目审计年度（前端写覆盖值同一口径；取不到年度时前端也写不了覆盖值 ⇒ 跳过）。程序号按
``normalize_program_no`` 比较（覆盖值的 item_key 是页面上的原样程序号）。只 flush 不 commit。
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

STATUS_FIELD = "status"
#: 裁剪 / 恢复后写入的状态值（与控制台下拉、渲染投影同一组取值）
TRIMMED_STATUS = "not_applicable"
RESTORED_STATUS = "pending"
ALIGNABLE = frozenset({TRIMMED_STATUS, RESTORED_STATUS})


async def align_program_row_status(
    db: AsyncSession,
    project_id: UUID,
    template_code: str | None,
    program_no,
    status: str,
    *,
    actor_user_id: UUID | None,
) -> int:
    """把这一程序行已有的状态覆盖值改成 ``status``；返回改写的条数（0 = 没有覆盖值 / 已一致 / 取不到年度）。"""
    if status not in ALIGNABLE:
        raise ValueError(f"程序行状态只能对齐为 {sorted(ALIGNABLE)}：{status!r}")
    if not template_code:
        return 0
    from app.routers.wp_render_strategies._a_program import program_override_scope
    from app.services.field_override_service import FieldOverrideService
    from app.services.procedure_row_trim_service import normalize_program_no
    from app.services.project_audit_year import resolve_project_audit_year_for_request

    year = await resolve_project_audit_year_for_request(db, project_id, None)
    if year is None:
        return 0
    svc = FieldOverrideService(db)
    scope = program_override_scope(template_code)
    want = normalize_program_no(program_no)
    changed = 0
    for item_key, fields in (await svc.get_batch(project_id, year, scope)).items():
        if normalize_program_no(item_key) != want or STATUS_FIELD not in fields:
            continue
        current = fields[STATUS_FIELD]
        if current in (None, "") or current == status:
            continue
        await svc.set(project_id, year, scope, item_key, STATUS_FIELD, status, user_id=actor_user_id)
        changed += 1
    return changed


async def align_task_row_status(
    db: AsyncSession, project_id: UUID, task, applicability: str, *, actor_user_id: UUID | None,
) -> int:
    """按任务的程序表码 / 程序号对齐：适用性 ``not_applicable`` ⇒ 不适用，其余（恢复执行）⇒ 待执行。"""
    status = TRIMMED_STATUS if applicability == "not_applicable" else RESTORED_STATUS
    return await align_program_row_status(db, project_id, task.sheet_key, task.program_no, status,
                                          actor_user_id=actor_user_id)
