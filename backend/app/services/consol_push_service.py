"""合并推送（spec consol-elimination-single-source-push §八，需求 8.1~8.6）。

分录审批 / 撤销审批 / 手动触发后，对分录所在合并项目及其全部上层合并项目**自下而上**依次：

    ① 重算差额表（``recalc_full``，内部 commit）
    ② 重算合并试算（``recalculate_trial``）+ commit
    ③ 生成合并报表（``generate_consol_reports``，按项目口径，全部报表类型）+ commit
    ④ 标记合并附注待更新 + **真正调用 fill_note_sections 刷新附注公式** + commit

- 关键步（①②）失败 ⇒ 该项目后续步骤跳过，**上层照常推送**（上层按库内下层现有结果计算，不会读到半写的数）；
  ③④ 失败记入步骤与警告，不影响其他项目。
- 步骤④的运行摘要区分 stale_marked（行数）/ distinct_section_count（章节数）/ node_count（节点数）/
  refreshed_count（成功刷新数）/ failed_count（失败数），不再用一个"N 章"同时表示行数和章节数。
- 并发：每个目标项目同进程 ``asyncio.Lock`` + PG 事务级咨询锁（跨进程）⇒ 两个下级同时推送时共同的上层
  逐项目串行；同一触发项目的后台推送排队期内再次请求只保留一次（``request_push``）。
- 结果：一行 ``consol_push_run``（``running → succeeded / partial / failed``，逐项目逐步骤 + 警告）；
  SSE ``consol.pushed``（全部或部分成功）/ ``consol.push_failed``（全部失败或编排异常），失败不静默（需求 8.6）。
- 口径与读时计算视图同源：报表生成与试算平衡表页、报表差额表调同一个 ``report_values``（ADR-CSP-002），
  所以推送写入的报表 = 读时计算的合并数（P1）。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
import weakref
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.schemas.consol_context import ConsolContext
    from app.services.consol_calc_basis import CalcBasis
    from app.services.consol_tree_service import TreeNode

from app.models.consol_push_models import ConsolPushRun

logger = logging.getLogger(__name__)

TRIGGER_APPROVED = "elimination_approved"
TRIGGER_REVOKED = "elimination_revoked"
TRIGGER_FORMULA = "formula_changed"
TRIGGER_MANUAL = "manual"
TRIGGER_LABELS = {
    TRIGGER_APPROVED: "分录审批",
    TRIGGER_REVOKED: "撤销审批",
    TRIGGER_FORMULA: "公式变更",
    TRIGGER_MANUAL: "手动推送",
}
TRIGGERS = frozenset(TRIGGER_LABELS)

STEP_WORKSHEET = "worksheet"
STEP_TRIAL = "trial"
STEP_REPORT = "report"
STEP_NOTES = "notes"
STEP_ORDER = (STEP_WORKSHEET, STEP_TRIAL, STEP_REPORT, STEP_NOTES)
STEP_LABELS = {
    STEP_WORKSHEET: "重算差额表",
    STEP_TRIAL: "重算合并试算",
    STEP_REPORT: "生成合并报表",
    STEP_NOTES: "刷新合并附注",
}
_CRITICAL = frozenset({STEP_WORKSHEET, STEP_TRIAL})

SSE_PUSHED = "consol.pushed"
SSE_FAILED = "consol.push_failed"
SSE_STALE = "consol.push_stale"

# 上级合并项目链最多追溯的层数（防御异常数据；真实集团不会超过十几层）
_MAX_DEPTH = 32


# ─────────────────────────────── 目标集合 ───────────────────────────────


async def push_targets(db: AsyncSession, project_id: UUID) -> list[UUID]:
    """``[本项目] + 上层合并项目``（自下而上），整条父链只发一条查询。

    递归项保留所有未删除的中间父项目，最终投影才筛合并口径，因此非合并中间父不会截断
    上溯。路径列防环，深度 0 是本项目，最多纳入 32 层父项目。
    """
    from app.models.core import Project

    projects = Project.__table__
    root_token = sa.cast(
        sa.literal("|") + sa.cast(projects.c.id, sa.String()) + sa.literal("|"),
        sa.Text(),
    )
    ancestors = sa.select(
        projects.c.id.label("id"),
        projects.c.parent_project_id.label("parent_project_id"),
        projects.c.report_scope.label("report_scope"),
        sa.literal(0).label("depth"),
        root_token.label("path"),
    ).where(
        projects.c.id == sa.bindparam("root_project_id"),
        projects.c.is_deleted == sa.false(),
    ).cte("consol_push_ancestors", recursive=True)

    parent = projects.alias("consol_push_parent")
    parent_token = sa.literal("|") + sa.cast(parent.c.id, sa.String()) + sa.literal("|")
    next_path = sa.cast(ancestors.c.path + sa.cast(parent_token, sa.Text()), sa.Text())
    ancestors = ancestors.union_all(
        sa.select(
            parent.c.id,
            parent.c.parent_project_id,
            parent.c.report_scope,
            (ancestors.c.depth + 1).label("depth"),
            next_path.label("path"),
        ).select_from(
            ancestors.join(parent, parent.c.id == ancestors.c.parent_project_id)
        ).where(
            parent.c.is_deleted == sa.false(),
            ancestors.c.depth < _MAX_DEPTH,
            ~ancestors.c.path.like(sa.literal("%") + parent_token + sa.literal("%")),
        )
    )
    normalized_scope = sa.func.lower(sa.func.trim(sa.func.coalesce(ancestors.c.report_scope, "")))
    stmt = (
        sa.select(ancestors.c.id)
        .where(sa.or_(ancestors.c.depth == 0, normalized_scope == "consolidated"))
        .order_by(ancestors.c.depth.asc())
    )
    return list((await db.execute(stmt, {"root_project_id": project_id})).scalars().all())


async def locked_targets(db: AsyncSession, project_ids: list[UUID]) -> list[str]:
    """已合并锁定（``projects.consol_lock``）的目标项目名称；空 ⇒ 都未锁定。"""
    from app.models.core import Project

    if not project_ids:
        return []
    rows = (await db.execute(
        sa.select(Project.id, Project.client_name, Project.name).where(
            Project.id.in_(project_ids), Project.consol_lock == sa.true(),
        )
    )).all()
    order = {pid: i for i, pid in enumerate(project_ids)}
    return [r.client_name or r.name for r in sorted(rows, key=lambda r: order.get(r.id, 0))]


# ─────────────────────────────── 锁 ───────────────────────────────

_PROCESS_LOCKS: weakref.WeakValueDictionary = weakref.WeakValueDictionary()


def _process_lock(kind: str, project_id: UUID, year: int) -> asyncio.Lock:
    """同进程串行。asyncio 锁绑定事件循环，键里带循环 id；``kind`` 区分「目标项目」与「排队运行」两类锁。"""
    key = (id(asyncio.get_running_loop()), kind, str(project_id), int(year))
    lock = _PROCESS_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _PROCESS_LOCKS[key] = lock
    return lock


async def _advisory_lock(db: AsyncSession, project_id: UUID, year: int) -> None:
    """跨进程串行：PG 事务级咨询锁，随本事务 commit / rollback 释放。SQLite 无此能力，跳过。"""
    if db.get_bind().dialect.name != "postgresql":
        return
    await db.execute(
        sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": f"consol_push:{project_id}:{year}"},
    )


# ─────────────────────────────── 执行 ───────────────────────────────

# 附注步骤（_mark_notes_stale / _refresh_notes）已迁出到 consol_push_notes（spec
# consol-status-semantics-closure 任务 1）；保留同名导入：既有测试按
# ``consol_push_service._refresh_notes`` 打补丁的写法照常生效（_push_one 经本模块全局名调用）。
from app.services.consol_push_notes import _mark_notes_stale, _refresh_notes, note_step_verdict  # noqa: F401


@dataclass
class PushResult:
    run_id: UUID
    project_id: UUID
    year: int
    status: str
    pushed_projects: list[str] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    operation_id: UUID | None = None
    report_run_ids: dict[str, str] = field(default_factory=dict)
    report_row_digests: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "run_id": str(self.run_id),
            "operation_id": str(self.operation_id) if self.operation_id else None,
            "project_id": str(self.project_id),
            "year": self.year,
            "status": self.status,
            "pushed_projects": list(self.pushed_projects),
            "steps": list(self.steps),
            "warnings": list(self.warnings),
            "report_run_ids": dict(self.report_run_ids),
            "report_row_digests": dict(self.report_row_digests),
        }


async def _project_name(db: AsyncSession, project_id: UUID) -> str:
    from app.models.core import Project

    row = (await db.execute(
        sa.select(Project.client_name, Project.name).where(Project.id == project_id)
    )).first()
    return (row[0] or row[1]) if row else str(project_id)


async def refresh_notes_exclusive(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    context: "ConsolContext | None" = None,
    tree: "TreeNode | None" = None,
    basis: "CalcBasis | None" = None,
) -> dict:
    """与推送同一附注刷新（``_refresh_notes``），持推送同一把锁（进程锁 + 事务级咨询锁）：
    与合并推送、「🔄 重新汇总」互斥。给合并「一键刷新」（``consol_cascade_refresh_service``）用。"""
    async with _process_lock("target", project_id, year):
        await _advisory_lock(db, project_id, year)
        return await _refresh_notes(
            db, project_id, year, context=context, tree=tree, basis=basis,
        )


async def _record_tree_version(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID | None,
    name: str,
    warnings: list[str],
    *,
    tree: "TreeNode | None" = None,
) -> str:
    """推送前自动记录企业树版本（spec consol-autotree-linkage-closure R1.2）；返回步骤明细前缀。

    放在 SAVEPOINT 里：记录失败只回滚这一步、写进警告，不挡住合并数重算（版本是溯源信息，不是计算前提）。
    """
    from app.services.consol_scope_confirmation_service import record_scope_version

    try:
        async with db.begin_nested():
            info = await record_scope_version(
                db, project_id, recorded_by=user_id, mode="auto", tree=tree,
            )
    except Exception as exc:  # noqa: BLE001 —— 失败留痕，不阻断推送
        logger.warning("合并推送记录树版本失败：项目=%s：%s", project_id, exc)
        warnings.append(f"「{name}」企业树版本记录失败：{exc}")
        return ""
    if info.get("skipped") == "locked":
        return f"树版本第 {info.get('revision', 0)} 版（合并已锁定，不记录新版本）；"
    if not info.get("revision"):
        return ""
    return f"树版本第 {info['revision']} 版{'（本次自动记录）' if info.get('created') else ''}；"


async def _push_one(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    steps: list[dict],
    warnings: list[str],
    *,
    context: "ConsolContext | None" = None,
    tree: "TreeNode | None" = None,
    basis: "CalcBasis | None" = None,
    user_id: UUID | None = None,
    operation_revision: int | None = None,
    report_trigger: str = "push",
    report_version_vector: dict[str, Any] | None = None,
    report_run_ids: dict[str, str] | None = None,
    report_row_digests: dict[str, str] | None = None,
) -> bool:
    """推送一个合并项目的四步；返回是否全部成功。每步独立事务，失败回滚该步并留痕。"""
    from app.services.consol_report_service import ConsolReportService
    from app.services.consol_trial_service import recalculate_trial
    from app.services.consol_worksheet_engine import recalc_full

    name = await _project_name(db, project_id)

    def record(step: str, status: str, detail: str | None = None) -> None:
        steps.append({
            "project_id": str(project_id), "project_name": name, "step": step,
            "step_label": STEP_LABELS[step], "status": status, "detail": detail,
        })

    async def worksheet() -> str:
        version = await _record_tree_version(
            db, project_id, user_id, name, warnings, tree=tree,
        )
        result = await recalc_full(
            db, project_id, year, context=context, tree=tree, basis=basis,
        )
        orphans = result.get("orphan_entries") or []
        if orphans:
            warnings.append(f"「{name}」有 {len(orphans)} 笔已审批分录找不到归属节点，未计入合并")
        return f"{version}节点 {result.get('node_count', 0)} 个，科目 {result.get('account_count', 0)} 个"

    async def trial() -> str:
        return f"试算 {len(await recalculate_trial(db, project_id, year, context=context, tree=tree, basis=basis))} 行"

    async def report() -> str:
        if context is not None and context.run_id is not None and operation_revision is not None:
            from app.services.consol_report_run_service import materialize_consol_report_run

            report_run = await materialize_consol_report_run(
                db,
                project_id,
                year,
                operation_id=context.run_id,
                operation_revision=operation_revision,
                trigger=report_trigger,
                triggered_by=user_id,
                context=context,
                tree=tree,
                basis=basis,
                input_version_vector=report_version_vector,
            )
            results = report_run.rows
            if report_run_ids is not None:
                report_run_ids[str(project_id)] = str(report_run.run_id)
            if report_row_digests is not None:
                report_row_digests[str(project_id)] = report_run.row_digest
        else:
            results = await ConsolReportService(db).generate_consol_reports(
                project_id, year, context=context, tree=tree, basis=basis,
            )
        blank = sum(1 for rows in results.values() for r in rows if r.get("blank_reason"))
        total = sum(len(rows) for rows in results.values())
        if blank:
            warnings.append(f"「{name}」合并报表有 {blank} 行取不到数，已留空并写明原因")
        return f"报表 {len(results)} 张 {total} 行" + (f"，留空 {blank} 行" if blank else "")

    async def notes() -> tuple[str, str]:
        stats = await _refresh_notes(
            db, project_id, year, context=context, tree=tree, basis=basis,
        )
        step_status, detail = note_step_verdict(stats)
        if int(stats.get("failed_count") or 0) or step_status == "failed":
            warnings.append(f"「{name}」附注刷新未完成：{detail}")
        # CP-03/R3：返回 (detail, step_status)，由共享 verdict 决定 skipped / failed。
        return detail, step_status

    bodies = {STEP_WORKSHEET: worksheet, STEP_TRIAL: trial, STEP_REPORT: report, STEP_NOTES: notes}
    all_ok = True
    async with _process_lock("target", project_id, year):
        for i, step in enumerate(STEP_ORDER):
            try:
                await _advisory_lock(db, project_id, year)
                result = await bodies[step]()
                await db.commit()
            except Exception as exc:  # noqa: BLE001 —— 失败留痕，不静默（需求 8.6）
                await db.rollback()
                logger.exception("合并推送 %s 失败：项目=%s 年度=%s", step, project_id, year)
                record(step, "failed", f"{type(exc).__name__}: {exc}")
                warnings.append(f"「{name}」{STEP_LABELS[step]}失败：{exc}")
                all_ok = False
                if step in _CRITICAL:
                    for later in STEP_ORDER[i + 1:]:
                        record(later, "skipped", f"{STEP_LABELS[step]}失败，跳过")
                    break
                continue

            # R3：附注步骤状态由 note_step_verdict 统一决定；合法跳过保留 skipped，
            # context_failed 已被 verdict 映射为 failed，不再伪装成成功。
            if isinstance(result, tuple):
                detail, note_status = result
                if note_status in ("partial", "failed"):
                    record(step, note_status, detail)
                    all_ok = False
                elif note_status == "skipped":
                    record(step, "skipped", detail)
                else:
                    record(step, "succeeded", detail)
            else:
                record(step, "succeeded", result)
    return all_ok


async def _finish_run(db: AsyncSession, run_id: UUID, status: str, steps: list, warnings: list) -> None:
    values = {"status": status, "steps": steps, "warnings": warnings, "finished_at": datetime.now(timezone.utc)}
    for attempt in range(2):
        try:
            await db.execute(sa.update(ConsolPushRun).where(ConsolPushRun.id == run_id).values(**values))
            await db.commit()
            return
        except Exception:  # noqa: BLE001 —— 会话坏了先回滚再试一次；仍失败只能记日志
            await db.rollback()
            if attempt:
                logger.exception("合并推送运行记录收尾失败：run=%s status=%s", run_id, status)


async def push(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    trigger: str = TRIGGER_MANUAL,
    user_id: UUID | None = None,
    operation_id: UUID | None = None,
    operation_revision: int | None = None,
    context: "ConsolContext | None" = None,
    tree: "TreeNode | None" = None,
) -> PushResult:
    """执行一次推送；``operation_id``/预构建上下文为 V240 追加兼容参数。"""
    if trigger not in TRIGGERS:
        raise ValueError(f"未知的推送触发来源：{trigger}")
    run_id = uuid.uuid4()
    # 开始时间显式到微秒：库默认值在 SQLite 只到秒，同一秒内的多次推送按时间排序会不确定
    db.add(ConsolPushRun(
        id=run_id,
        operation_id=operation_id,
        project_id=project_id,
        year=year,
        trigger_source=trigger,
        triggered_by=user_id,
        status="running",
        steps=[],
        warnings=[],
        started_at=datetime.now(timezone.utc),
    ))
    await db.commit()
    steps: list[dict] = []
    warnings: list[str] = []
    pushed: list[str] = []
    report_run_ids: dict[str, str] = {}
    report_row_digests: dict[str, str] = {}
    failed_projects = 0
    aborted = False

    # 同一 run 的上下文种子只承载 run 身份；每个 target 各自解析 tree/context/basis。
    from app.schemas.consol_context import ConsolContext
    from app.services.consol_calc_basis import load_calc_basis, validate_calc_basis
    from app.services.consol_context_service import (
        build_consol_context,
        build_target_consol_context,
        validate_context,
    )
    from app.services.consol_tree_service import build_tree

    source_context = context
    source_tree = tree
    context_seed = context or ConsolContext(run_id=operation_id, project_id=project_id, year=year)

    try:
        for target in await push_targets(db, project_id):
            try:
                # 变量只活在本轮 target 内，禁止跨目标复用树或计算口径。
                if target == project_id:
                    target_tree = source_tree if source_tree is not None else await build_tree(db, target)
                    if target_tree is None:
                        raise ValueError(f"企业树构建失败：找不到合并项目 {target}")
                    target_context = source_context
                    if target_context is None:
                        target_context = await build_consol_context(
                            db, target, year, tree=target_tree, seed=context_seed,
                        )
                    source_context = target_context
                    source_tree = target_tree
                else:
                    target_tree = await build_tree(db, target)
                    if target_tree is None:
                        raise ValueError(f"企业树构建失败：找不到合并项目 {target}")
                    target_context = await build_target_consol_context(
                        db, source_context or context_seed, target, year, tree=target_tree,
                    )
                validate_context(target_context, target, year, tree=target_tree)
                target_basis = await load_calc_basis(db, target, year, tree=target_tree)
                if target_basis is None:
                    raise ValueError(f"企业树计算口径装载失败：项目 {target}")
                validate_calc_basis(target_basis, target, year, tree=target_tree)
                from app.services.consol_version_vector import build_version_vector

                target_report_vector = await build_version_vector(
                    db,
                    context=target_context,
                    tree=target_tree,
                )
            except Exception as exc:  # noqa: BLE001 —— 当前 target 失败不阻断更上层 target
                await db.rollback()
                name = await _project_name(db, target)
                detail = f"{type(exc).__name__}: {exc}"
                steps.append({
                    "project_id": str(target),
                    "project_name": name,
                    "step": STEP_WORKSHEET,
                    "step_label": STEP_LABELS[STEP_WORKSHEET],
                    "status": "failed",
                    "detail": detail,
                })
                for later in STEP_ORDER[1:]:
                    steps.append({
                        "project_id": str(target),
                        "project_name": name,
                        "step": later,
                        "step_label": STEP_LABELS[later],
                        "status": "skipped",
                        "detail": "合并计算运行时构建失败，跳过",
                    })
                warnings.append(f"「{name}」合并计算运行时构建失败：{exc}")
                failed_projects += 1
                continue

            if not await _push_one(
                db,
                target,
                year,
                steps,
                warnings,
                context=target_context,
                tree=target_tree,
                basis=target_basis,
                user_id=user_id,
                operation_revision=operation_revision,
                report_trigger=trigger,
                report_version_vector=target_report_vector.model_dump(mode="json"),
                report_run_ids=report_run_ids,
                report_row_digests=report_row_digests,
            ):
                failed_projects += 1
            # 报表已写入（哪怕附注标记失败）⇒ 该项目的页面需要刷新
            if any(s["project_id"] == str(target) and s["step"] == STEP_REPORT and s["status"] == "succeeded"
                   for s in steps):
                pushed.append(str(target))
    except Exception as exc:  # noqa: BLE001 —— 编排异常也要落失败运行
        await db.rollback()
        logger.exception("合并推送编排异常：项目=%s 年度=%s", project_id, year)
        warnings.append(f"推送中断：{exc}")
        aborted = True
    if aborted or (failed_projects and not pushed):
        status = "failed"
    elif failed_projects:
        status = "partial"
    else:
        status = "succeeded"
    await _finish_run(db, run_id, status, steps, warnings)
    result = PushResult(
        run_id, project_id, year, status, pushed, steps, warnings,
        operation_id=operation_id,
        report_run_ids=report_run_ids,
        report_row_digests=report_row_digests,
    )
    _broadcast(SSE_FAILED if status == "failed" else SSE_PUSHED, result, trigger)
    return result


def _broadcast(event: str, result: PushResult, trigger: str) -> None:
    try:
        from app.services.event_bus import event_bus

        payload = {
            "project_id": str(result.project_id), "year": result.year, "run_id": str(result.run_id),
            "operation_id": str(result.operation_id) if result.operation_id else None,
            "status": result.status, "trigger": trigger, "trigger_label": TRIGGER_LABELS.get(trigger, trigger),
            "pushed_projects": list(result.pushed_projects), "warnings": list(result.warnings[:10]),
            "report_run_ids": dict(result.report_run_ids),
            "report_row_digests": dict(result.report_row_digests),
        }
        event_bus.broadcast_raw(event, payload)
        # 上层合并项目的页面也要刷新（它们的数也变了）；SSE 按 project_id 过滤，所以逐个项目发
        for pid in result.pushed_projects:
            if pid != str(result.project_id):
                event_bus.broadcast_raw(event, {**payload, "project_id": pid, "source_project_id": str(result.project_id)})
    except Exception as exc:  # pragma: no cover - 广播失败不影响推送结果
        logger.debug("广播 %s 失败（不影响推送）：%s", event, exc)


def broadcast_stale(project_ids: list[UUID], year: int, source_project_id: UUID) -> None:
    """子企业试算表变更 ⇒ 所属合并项目推送结果过期（需求 8.3，合并页提示「建议重新推送」）。"""
    try:
        from app.services.event_bus import event_bus

        for pid in project_ids:
            event_bus.broadcast_raw(SSE_STALE, {
                "project_id": str(pid), "year": year, "source_project_id": str(source_project_id),
            })
    except Exception as exc:  # pragma: no cover
        logger.debug("广播 %s 失败：%s", SSE_STALE, exc)


# ─────────────────────────────── 后台排队（事件与「立即推送」共用） ───────────────────────────────

_QUEUED: dict[tuple[str, int], tuple[str, UUID | None]] = {}
_TASKS: set[asyncio.Task] = set()


def request_push(
    project_id: UUID, year: int, *, trigger: str, user_id: UUID | None = None,
) -> asyncio.Task | None:
    """后台推送（需求 8.4）：同一 ``(项目, 年度)`` 已有**排队未开始**的推送 ⇒ 并入它（返回 None），
    否则新建后台任务并返回。正在执行的推送不合并 —— 它可能没读到本次触发之后的数据，新请求排在它后面。

    后台任务用自己的会话（请求会话在响应返回后即关闭）。
    """
    if trigger not in TRIGGERS:
        raise ValueError(f"未知的推送触发来源：{trigger}")
    key = (str(project_id), int(year))
    if key in _QUEUED:
        _QUEUED[key] = (trigger, user_id)  # 以最后一次触发记账
        return None
    _QUEUED[key] = (trigger, user_id)
    task = asyncio.get_running_loop().create_task(_run_queued(project_id, int(year), key))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return task


async def _run_queued(project_id: UUID, year: int, key: tuple[str, int]):
    started = False
    try:
        async with _process_lock("run", project_id, year):
            started = True
            trigger, user_id = _QUEUED.pop(key, (TRIGGER_MANUAL, None))
            from app.core.database import async_session
            from app.services.consol_operation_service import request_operation
            from app.workers.consol_operation_worker import wake

            async with async_session() as db:
                requested = await request_operation(
                    db,
                    project_id=project_id,
                    year=year,
                    operation_type="push",
                    idempotency_key=f"legacy-push:{uuid.uuid4().hex}",
                    trigger_source=trigger,
                    triggered_by=user_id,
                )
                await db.commit()
            wake()
            return requested.operation
    except Exception:  # noqa: BLE001 —— 事件已提交时不能向上反抛；入队失败留日志
        logger.exception("后台合并 operation 入队失败：项目=%s 年度=%s", project_id, year)
        return None
    finally:
        if not started:
            _QUEUED.pop(key, None)


def pending_count() -> int:
    return len(_TASKS)


async def wait_for_pushes() -> None:
    """等待本进程入队完成并 drain 持久 operation（测试与优雅停机兼容）。"""
    while _TASKS:
        await asyncio.gather(*list(_TASKS), return_exceptions=True)
    from app.workers.consol_operation_worker import wait_for_operations

    await wait_for_operations()


# ─────────────────────────────── 查询 ───────────────────────────────


def run_to_dict(run: ConsolPushRun) -> dict:
    return {
        "id": str(run.id),
        "operation_id": str(run.operation_id) if run.operation_id else None,
        "project_id": str(run.project_id),
        "year": run.year,
        "trigger_source": run.trigger_source,
        "trigger_label": TRIGGER_LABELS.get(run.trigger_source, run.trigger_source),
        "triggered_by": str(run.triggered_by) if run.triggered_by else None,
        "status": run.status,
        "steps": list(run.steps or []),
        "warnings": list(run.warnings or []),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


async def list_runs(db: AsyncSession, project_id: UUID, year: int, limit: int = 10) -> list[dict]:
    result = await db.execute(
        sa.select(ConsolPushRun)
        .where(ConsolPushRun.project_id == project_id, ConsolPushRun.year == year)
        .order_by(ConsolPushRun.started_at.desc(), ConsolPushRun.id.desc())
        .limit(max(1, min(int(limit), 50)))
    )
    return [run_to_dict(r) for r in result.scalars().all()]


async def push_status(db: AsyncSession, project_id: UUID, year: int) -> dict[str, Any]:
    """最近一次推送 + 是否过期（合并试算有 is_stale 行 ⇒ 子企业试算表在推送后又变了）。"""
    from app.models.consolidation_models import ConsolTrial

    runs = await list_runs(db, project_id, year, limit=1)
    stale = (await db.execute(
        sa.select(sa.func.count()).select_from(ConsolTrial).where(
            ConsolTrial.project_id == project_id, ConsolTrial.year == year,
            ConsolTrial.is_deleted == sa.false(), ConsolTrial.is_stale == sa.true(),
        )
    )).scalar_one()
    return {"last_run": runs[0] if runs else None, "is_stale": bool(stale), "stale_rows": int(stale)}


__all__ = [
    "SSE_FAILED",
    "SSE_PUSHED",
    "SSE_STALE",
    "STEP_LABELS",
    "STEP_ORDER",
    "TRIGGERS",
    "TRIGGER_APPROVED",
    "TRIGGER_FORMULA",
    "TRIGGER_LABELS",
    "TRIGGER_MANUAL",
    "TRIGGER_REVOKED",
    "PushResult",
    "broadcast_stale",
    "list_runs",
    "locked_targets",
    "pending_count",
    "push",
    "push_status",
    "push_targets",
    "request_push",
    "run_to_dict",
    "wait_for_pushes",
]
