"""已生成又被裁掉的底稿收口（spec procedure-trim-generation-delegation-chain 需求 8 / 任务 19）。

批 2 之前生成不看子表 / 程序表、粗裁也不联动已生成的底稿 ⇒ 存量项目留着已裁的底稿（重药安徽 138 张）；程序行任务的
级联取消按循环快照匹配也漏了一些（安徽 I2 / I3）。本模块对一个项目做三件事，都走平台既有路径：

1. 复核误裁（``restore_misjudged``）：系统按「无数据」自动裁剪的（理由码 ``no_data`` 且理由以「自动裁剪」开头），按新判定
   （需求 1，``resolve_subject_data_availability``，按科目映射后的标准科目）该科目有数据 ⇒ 恢复执行，并把那条系统建议记为
   「已驳回」，理由「系统误判更正：…」（``reject_suggestions``；执行状态不带裁剪理由，驳回记录就是更正留痕，决策内核此后
   不再重复建议）。用户自己填理由裁的不动，有数据也只列出来请人工看。
2. 其余粗裁原样重放（状态、理由都不变）：与「配置裁剪」页同一条 preview → apply —— 覆盖范围内已生成的底稿移入回收站
   （``kind=trim``，可恢复），范围内未终结的程序行任务按底稿归属级联取消。
3. 有编制内容的底稿默认不动（apply 409），须显式确认。

``reconcile`` 对账（不变式：在用的底稿没有一张是已裁的；回收站里因裁剪移入的底稿下没有未终结任务）；``regenerate`` 按项目
用过的模板集重新生成（与生成弹窗同一入口，已裁 / 在回收站的不新建）。只 flush 不 commit，事务、备份与提交归调用方。
可重跑：处理过的项目再算计划为空。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procedure_models import ProcedureInstance, ProcedureRowTask
from app.models.workpaper_models import WorkingPaper, WpIndex, WpTemplateSet
from app.services.procedure_scope_retention import load_trimmed_scope, normalize_code, plan_generation
from app.services.procedure_task_transition_service import SCOPE_TRIMMED_STATUSES, TERMINAL_WORKFLOW_STATES
from app.services.procedure_trim_recycle import load_scope_coverage
from app.services.workpaper_recycle_service import KIND_TRIM, last_recycle_kind

AUTO_REASON_CODE = "no_data"
AUTO_REASON_PREFIX = "自动裁剪"
CORRECTION_PREFIX = "系统误判更正"


class CleanupError(RuntimeError):
    """计划无法给出（审计年度不明、试算表读不到 …）：不做任何改动。"""


@dataclass
class CleanupPlan:
    project_id: UUID
    year: int
    misjudged: list[dict] = field(default_factory=list)       # 恢复执行：{cycle, code, correction, evidence}
    kept: list[dict] = field(default_factory=list)            # 原样重放：{cycle, code, status}
    data_but_manual: list[dict] = field(default_factory=list)  # 有数据但不是系统自动裁的：只列出
    manual_review: list[dict] = field(default_factory=list)   # 缺编码 / 同码多行状态不一：跳过
    entries: list[dict] = field(default_factory=list)
    preview_id: UUID | None = None
    summary: dict = field(default_factory=dict)
    recycle_preview: dict = field(default_factory=dict)
    cascade_tasks: list[dict] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        rp = self.recycle_preview
        return not (self.misjudged or rp.get("to_recycle") or rp.get("to_restore") or rp.get("to_reopen_tasks")
                    or self.summary.get("would_change"))

    def to_dict(self) -> dict:
        out = asdict(self)
        out["project_id"] = str(self.project_id)
        out["preview_id"] = str(self.preview_id) if self.preview_id else None
        out["is_empty"] = self.is_empty
        return out


def is_auto_no_data(inst: ProcedureInstance) -> bool:
    """系统按「无数据」自动裁剪的（不是用户自己填理由裁的）。"""
    state = inst.suggestion_state if isinstance(inst.suggestion_state, dict) else {}
    return state.get("reason_code") == AUTO_REASON_CODE and (inst.skip_reason or "").startswith(AUTO_REASON_PREFIX)


def correction_text(code: str, evidence: dict | None) -> str:
    ev = evidence or {}
    amounts = "，".join(f"{label} {float(ev.get(key) or 0):,.2f}" for key, label in (
        ("closing", "期末"), ("opening", "期初"), ("debit", "本期借方"), ("credit", "本期贷方")))
    return f"{CORRECTION_PREFIX}：{ev.get('label') or code}有数据（{amounts}），原为系统按无数据自动裁剪"


async def _trimmed_groups(db: AsyncSession, project_id: UUID) -> dict[tuple[str, str], list[ProcedureInstance]]:
    rows = (await db.execute(sa.select(ProcedureInstance).where(
        ProcedureInstance.project_id == project_id,
        ProcedureInstance.is_deleted == sa.false(),
        ProcedureInstance.status.in_(SCOPE_TRIMMED_STATUSES),
    ).order_by(ProcedureInstance.audit_cycle, ProcedureInstance.wp_code, ProcedureInstance.id))).scalars().all()
    groups: dict[tuple[str, str], list[ProcedureInstance]] = {}
    for inst in rows:
        groups.setdefault((inst.audit_cycle or "", normalize_code(inst.wp_code)), []).append(inst)
    return groups


async def _cascade_candidates(db: AsyncSession, project_id: UUID, codes: list[str]) -> list[dict]:
    """重放粗裁时会被级联取消的任务（与 ``ProcedureTrimService._resolve_scope`` 同一归属判定，去掉已终结的）。"""
    if not codes:
        return []
    coverage = await load_scope_coverage(db, project_id)
    index_ids = {row.id for code in codes for row in coverage.covered(code)}
    belongs = ProcedureRowTask.wp_code.in_(codes)
    if index_ids:
        belongs = sa.or_(belongs, ProcedureRowTask.wp_index_id.in_(index_ids))
    tasks = (await db.execute(sa.select(ProcedureRowTask).where(
        ProcedureRowTask.project_id == project_id, ProcedureRowTask.is_deleted == sa.false(), belongs,
        ProcedureRowTask.workflow_status.notin_(TERMINAL_WORKFLOW_STATES),
    ).order_by(ProcedureRowTask.wp_code, ProcedureRowTask.id))).scalars().all()
    return [{"task_id": str(t.id), "wp_code": t.wp_code, "sheet_key": t.sheet_key, "program_no": t.program_no,
             "workflow_status": t.workflow_status, "applicability_status": t.applicability_status,
             "assignee_staff_id": str(t.assignee_staff_id) if t.assignee_staff_id else None,
             "lock_version": t.lock_version} for t in tasks]


async def plan_cleanup(
    db: AsyncSession, project_id: UUID, *, actor_user_id: UUID, restore_misjudged: bool = False,
    availability: dict | None = None,
) -> CleanupPlan:
    """算出收口计划并建一个裁剪预览凭证（只 flush；dry-run 由调用方回滚）。"""
    from app.services.procedure_trim_scope import resolve_subject_data_availability
    from app.services.procedure_trim_service import ProcedureTrimService
    from app.services.sampling_registry_service import resolve_project_year

    year = await resolve_project_year(db, project_id)
    if year is None:
        raise CleanupError("项目没有审计年度，无法判定")
    plan = CleanupPlan(project_id, year)
    with_data: set[str] = set()
    evidence: dict = {}
    if restore_misjudged:
        availability = availability or await resolve_subject_data_availability(db, project_id, year)
        if availability.get("error"):
            raise CleanupError(f"无法复核误裁：{availability['error']}")
        with_data = {normalize_code(c) for c in availability.get("subject_with_data") or []}
        evidence = availability.get("evidence") or {}

    for (cycle, code), group in (await _trimmed_groups(db, project_id)).items():
        states = {(i.status, i.skip_reason or None) for i in group}
        if not code or len(states) > 1:
            plan.manual_review.append({"cycle": cycle, "code": code, "states": sorted(map(str, states)),
                                       "reason": "缺底稿编码" if not code else "同码多行状态不一"})
            continue
        status, skip_reason = next(iter(states))
        if code in with_data and all(is_auto_no_data(i) for i in group):
            correction = correction_text(code, evidence.get(code))
            plan.misjudged.append({"cycle": cycle, "code": code, "old_reason": skip_reason, "correction": correction,
                                   "evidence": evidence.get(code)})
            plan.entries.append({"kind": "scope", "cycle": cycle, "wp_index_code": code, "target_status": "execute"})
            continue
        if code in with_data:
            plan.data_but_manual.append({"cycle": cycle, "code": code, "status": status, "reason": skip_reason})
        plan.kept.append({"cycle": cycle, "code": code, "status": status})
        plan.entries.append({"kind": "scope", "cycle": cycle, "wp_index_code": code, "target_status": status,
                             "skip_reason": skip_reason})

    if plan.entries:
        preview = await ProcedureTrimService(db).preview_scheme(
            project_id, actor_user_id=actor_user_id, entries=plan.entries)
        plan.preview_id = UUID(preview["preview_id"])
        plan.summary = preview["summary"]
        plan.recycle_preview = preview["recycle_preview"]
    plan.cascade_tasks = await _cascade_candidates(db, project_id, [k["code"] for k in plan.kept])
    return plan


async def apply_cleanup(
    db: AsyncSession, plan: CleanupPlan, *, actor_user_id: UUID, request_id: str, confirm_substantive: bool = False,
) -> dict:
    """消费计划的预览凭证执行，再核对不变式（只 flush；调用方据异常回滚）。

    有编制内容的底稿未确认 ⇒ HTTPException 409（写库前拦）；执行后在用底稿仍有已裁的、或回收站里因裁剪移入的底稿下
    仍有未终结任务 ⇒ :class:`CleanupError`。
    """
    from app.services.procedure_trim_service import ProcedureTrimService

    if plan.preview_id is None:
        result: dict = {"applied": 0, "recycled_codes": [], "restored_codes": []}
    else:
        svc = ProcedureTrimService(db)
        result = await svc.apply_scheme(
            plan.project_id, actor_user_id=actor_user_id, preview_id=plan.preview_id, request_id=request_id,
            entries=plan.entries, confirm_substantive_recycle=confirm_substantive,
        )
        for item in plan.misjudged:
            await svc.reject_suggestions(plan.project_id, cycle=item["cycle"], wp_index_codes=[item["code"]],
                                         actor_user_id=actor_user_id, reason=item["correction"])
    after = await reconcile(db, plan.project_id)
    skipped = {m["code"] for m in plan.manual_review}  # 跳过人工处理的裁剪行，它们管的底稿本次不动
    scope = await load_trimmed_scope(db, plan.project_id)
    left = [c for c in after["live_trimmed"] if not any(d in skipped for d in scope.deciders(c))]
    if left or after["open_tasks_under_recycled"]:
        raise CleanupError(f"对账不变式不成立：在用的已裁底稿 {left}，"
                           f"回收站底稿下未终结任务 {after['open_tasks_under_recycled']} 条")
    return {**result, "corrected": [m["code"] for m in plan.misjudged], "after": after}


async def snapshot(db: AsyncSession, plan: CleanupPlan) -> dict:
    """执行前现状（写备份用）：裁剪行、将移入 / 恢复的底稿两层、将级联取消的任务。"""
    pid = plan.project_id
    instances = [
        {"id": str(i.id), "cycle": i.audit_cycle, "wp_code": i.wp_code, "status": i.status,
         "skip_reason": i.skip_reason, "suggestion_state": i.suggestion_state}
        for group in (await _trimmed_groups(db, pid)).values() for i in group
    ]
    codes = sorted(set(plan.recycle_preview.get("to_recycle") or []) | set(plan.recycle_preview.get("to_restore") or []))
    indexes = (await db.execute(sa.select(WpIndex).where(
        WpIndex.project_id == pid, WpIndex.wp_code.in_(codes)))).scalars().all() if codes else []
    papers = (await db.execute(sa.select(WorkingPaper).where(
        WorkingPaper.project_id == pid, WorkingPaper.wp_index_id.in_([x.id for x in indexes])))).scalars().all() \
        if indexes else []
    return {
        "project_id": str(pid), "year": plan.year, "plan": plan.to_dict(), "procedure_instances": instances,
        "wp_index": [{"id": str(x.id), "wp_code": x.wp_code, "wp_name": x.wp_name, "is_deleted": bool(x.is_deleted),
                      "cross_ref_codes": x.cross_ref_codes} for x in indexes],
        "working_paper": [{"id": str(w.id), "wp_index_id": str(w.wp_index_id), "is_deleted": bool(w.is_deleted),
                           "status": getattr(w.status, "value", w.status),
                           "review_status": getattr(w.review_status, "value", w.review_status),
                           "content_revision": w.content_revision, "file_version": w.file_version} for w in papers],
        "tasks": plan.cascade_tasks,
    }


async def reconcile(db: AsyncSession, project_id: UUID, *, template_codes: list[str] | None = None) -> dict:
    """对账（只读）。``live_trimmed`` 与 ``open_tasks_under_recycled`` 必须为空 / 0。"""
    scope = await load_trimmed_scope(db, project_id)
    rows = (await db.execute(sa.select(WpIndex.id, WpIndex.wp_code, WpIndex.is_deleted, WpIndex.cross_ref_codes)
                             .where(WpIndex.project_id == project_id))).all()
    live = [r for r in rows if not r.is_deleted]
    deleted = [r for r in rows if r.is_deleted]
    trim_recycled = [r for r in deleted if last_recycle_kind(r.cross_ref_codes) == KIND_TRIM]
    papers = dict((await db.execute(sa.select(WorkingPaper.is_deleted, sa.func.count()).where(
        WorkingPaper.project_id == project_id).group_by(WorkingPaper.is_deleted))).all())
    open_under = (await db.execute(sa.select(sa.func.count()).select_from(ProcedureRowTask).where(
        ProcedureRowTask.project_id == project_id, ProcedureRowTask.is_deleted == sa.false(),
        ProcedureRowTask.wp_index_id.in_([r.id for r in trim_recycled]),
        ProcedureRowTask.workflow_status.notin_(TERMINAL_WORKFLOW_STATES),
    ))).scalar_one() if trim_recycled else 0
    task_states = Counter(f"{a}/{w}" for a, w in (await db.execute(sa.select(
        ProcedureRowTask.applicability_status, ProcedureRowTask.workflow_status).where(
        ProcedureRowTask.project_id == project_id, ProcedureRowTask.is_deleted == sa.false()))).all())
    out = {
        "wp_index_live": len(live),
        "wp_index_in_recycle": len(deleted),
        "in_recycle_by_kind": dict(Counter(last_recycle_kind(r.cross_ref_codes) or "unknown" for r in deleted)),
        "working_paper_live": int(papers.get(False, 0)),
        "working_paper_in_recycle": int(papers.get(True, 0)),
        "trimmed_rows": sorted(scope.trimmed_codes),
        "live_trimmed": sorted(r.wp_code for r in live if scope.is_trimmed(r.wp_code)),
        "open_tasks_under_recycled": int(open_under),
        "task_states": dict(sorted(task_states.items())),
    }
    if template_codes is not None:
        gp = await plan_generation(db, project_id, list(template_codes), scope=scope)
        out["generation"] = {"would_create": gp.to_create, "skipped_trimmed": len(gp.skipped_trimmed_codes),
                             "in_recycle": len(gp.in_recycle_codes), "existing": len(gp.existing_codes)}
    return out


async def pick_template_set(db: AsyncSession, project_id: UUID, template_set_id: UUID | None = None):
    """项目用过的模板集：指定的，或与本项目底稿编码重合最多的那一个（并列 / 都不重合 ⇒ 须指定）。"""
    sets = (await db.execute(sa.select(WpTemplateSet).where(WpTemplateSet.is_deleted == sa.false()))).scalars().all()
    if template_set_id is not None:
        hit = next((s for s in sets if s.id == template_set_id), None)
        if hit is None:
            raise CleanupError(f"模板集 {template_set_id} 不存在")
        return hit
    codes = set((await db.execute(sa.select(WpIndex.wp_code).where(WpIndex.project_id == project_id))).scalars())
    ranked = sorted(((len(codes & set(s.template_codes or [])), s) for s in sets), key=lambda x: -x[0])
    if not ranked or ranked[0][0] == 0:
        raise CleanupError("没有与本项目底稿重合的模板集，请用 --template-set-id 指定")
    if len(ranked) > 1 and ranked[1][0] == ranked[0][0]:
        raise CleanupError("多个模板集与本项目底稿重合一样多，请用 --template-set-id 指定")
    return ranked[0][1]


async def regenerate(db: AsyncSession, project_id: UUID, *, template_set_id: UUID, year: int,
                     actor_user_id: UUID) -> dict:
    """按模板集重新生成（生成弹窗同一入口；已裁 / 在回收站 / 已存在的都不新建）。只 flush。"""
    from app.services.template_engine import TemplateEngine

    outcome = await TemplateEngine().generate_project_workpapers_detailed(
        db=db, project_id=project_id, template_set_id=template_set_id, year=year, created_by=actor_user_id)
    ids = [w.wp_index_id for w in outcome.workpapers]
    created = sorted((await db.execute(sa.select(WpIndex.wp_code).where(WpIndex.id.in_(ids)))).scalars()) if ids else []
    return {"created": created, "skipped_trimmed_codes": outcome.skipped_trimmed_codes,
            "in_recycle_codes": outcome.in_recycle_codes, "ignored_codes": outcome.ignored_codes}
