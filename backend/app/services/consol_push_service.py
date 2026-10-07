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
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

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
    """``[本项目] + 上层合并项目``（自下而上）。

    沿 ``parent_project_id`` 派生链接走（与三码推导一致，由 ``sync_group_links`` 维护；ADR-CTREE-001），
    只收合并项目；遇环、已删项目即停。
    """
    from app.models.core import Project

    targets: list[UUID] = [project_id]
    seen = {project_id}
    cur = project_id
    for _ in range(_MAX_DEPTH):
        parent = (await db.execute(
            sa.select(Project.parent_project_id).where(Project.id == cur, Project.is_deleted == sa.false())
        )).scalar_one_or_none()
        if parent is None or parent in seen:
            break
        scope = (await db.execute(
            sa.select(Project.report_scope).where(Project.id == parent, Project.is_deleted == sa.false())
        )).first()
        if scope is None:
            break
        seen.add(parent)
        if (scope[0] or "").strip().lower() == "consolidated":
            targets.append(parent)
        cur = parent
    return targets


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


@dataclass
class PushResult:
    run_id: UUID
    project_id: UUID
    year: int
    status: str
    pushed_projects: list[str] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_id": str(self.run_id),
            "project_id": str(self.project_id),
            "year": self.year,
            "status": self.status,
            "pushed_projects": list(self.pushed_projects),
            "steps": list(self.steps),
            "warnings": list(self.warnings),
        }


async def _project_name(db: AsyncSession, project_id: UUID) -> str:
    from app.models.core import Project

    row = (await db.execute(
        sa.select(Project.client_name, Project.name).where(Project.id == project_id)
    )).first()
    return (row[0] or row[1]) if row else str(project_id)


async def _mark_notes_stale(db: AsyncSession, project_id: UUID, year: int) -> int:
    from app.models.consol_note_data_models import ConsolNoteData

    result = await db.execute(
        sa.update(ConsolNoteData)
        .where(ConsolNoteData.project_id == project_id, ConsolNoteData.year == year)
        .values(is_stale=True)
    )
    return int(result.rowcount or 0)


async def _refresh_notes(
    db: AsyncSession, project_id: UUID, year: int, *, context=None, tree=None,
) -> dict:
    """标记 stale → 真正刷新附注 → 返回分口径统计。

    先标记所有 ``consol_note_data`` 行 stale，再按节点逐章节调用
    ``fill_note_sections`` 执行公式刷新并清除 ``is_stale``。
    返回值区分 section / node_instance / refreshed / failed / skipped 五种计数。
    """
    from app.models.consol_note_data_models import ConsolNoteData
    from app.services.consol_note_formula_service import (
        consol_note_tables,
        fill_note_sections,
        resolve_note_template_type,
    )
    from app.services.consol_tree_service import build_tree, iter_nodes

    # ── 1. 标记 stale ──
    stale_count = await _mark_notes_stale(db, project_id, year)
    await db.commit()

    stats: dict = {
        "stale_marked": stale_count,
        "distinct_section_count": 0,
        "node_count": 0,
        "refreshed_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "note_status": "skipped",  # 附注子状态：persisted / partial / failed / skipped
    }

    # ── 2. 解析模板与章节 ──
    try:
        template_type = await resolve_note_template_type(db, project_id)
    except Exception:
        # 无法解析模板（项目无 consolidation_type 等）⇒ 只标 stale 不刷新
        logger.warning("合并推送附注刷新跳过：无法解析项目模板类型，project=%s", project_id)
        return stats

    tables = [t for t in consol_note_tables(template_type) if t.get("enabled", True) is not False]
    section_ids = list(dict.fromkeys(
        str(t.get("section_id")) for t in tables if t.get("section_id")
    ))
    stats["distinct_section_count"] = len(section_ids)
    if not section_ids:
        return stats

    # ── 3. 构建企业树 ──
    resolved_tree = tree if tree is not None else await build_tree(db, project_id)
    if resolved_tree is None:
        logger.info("合并推送附注刷新跳过：无企业树，project=%s", project_id)
        return stats

    # ── 4. 构建合并计算上下文 ──
    view_ctx = None
    resolved_context = context
    try:
        if resolved_context is None:
            from app.services.consol_context_service import build_consol_context
            resolved_context = await build_consol_context(db, project_id, year, tree=resolved_tree)
        from app.services.consol_report_view_service import load_view_context
        view_ctx = await load_view_context(db, project_id, year, context=resolved_context, tree=resolved_tree)
    except Exception as exc:
        logger.warning("合并推送附注刷新上下文构建失败（降级只标 stale）：%s", exc)
        return stats

    # ── 5. 遍历节点逐章刷新 ──
    seen: set[str] = set()
    nodes = []
    for node in iter_nodes(resolved_tree):
        nk = str(getattr(node, "node_key", "") or "").strip()
        if nk and nk not in seen:
            seen.add(nk)
            nodes.append(node)
    stats["node_count"] = len(nodes)

    total_persisted = 0
    total_failed = 0
    total_skipped = 0

    for node in nodes:
        node_key = str(node.node_key)
        try:
            result = await fill_note_sections(
                db, project_id, year, section_ids,
                node_key=node_key,
                template_type=template_type,
                context=resolved_context,
                tree=resolved_tree,
                view_context=view_ctx,
            )
            if result.get("results"):
                await db.commit()
            persisted = len(result.get("results") or [])
            failed = len(result.get("failures") or [])
            total_persisted += persisted
            total_failed += failed
            total_skipped += max(0, len(section_ids) - persisted - failed)
        except Exception as exc:
            await db.rollback()
            logger.warning("合并推送附注刷新节点 %s 失败：%s", node_key, exc)
            total_failed += len(section_ids)

    stats["refreshed_count"] = total_persisted
    stats["failed_count"] = total_failed
    stats["skipped_count"] = total_skipped

    if total_failed and total_persisted:
        stats["note_status"] = "partial"
    elif total_failed:
        stats["note_status"] = "failed"
    elif total_persisted:
        stats["note_status"] = "persisted"
    else:
        stats["note_status"] = "skipped"

    return stats


async def _push_one(db: AsyncSession, project_id: UUID, year: int, steps: list[dict], warnings: list[str],
                    *, context=None, tree=None) -> bool:
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
        result = await recalc_full(db, project_id, year)
        orphans = result.get("orphan_entries") or []
        if orphans:
            warnings.append(f"「{name}」有 {len(orphans)} 笔已审批分录找不到归属节点，未计入合并")
        return f"节点 {result.get('node_count', 0)} 个，科目 {result.get('account_count', 0)} 个"

    async def trial() -> str:
        return f"试算 {len(await recalculate_trial(db, project_id, year))} 行"

    async def report() -> str:
        results = await ConsolReportService(db).generate_consol_reports(project_id, year)
        blank = sum(1 for rows in results.values() for r in rows if r.get("blank_reason"))
        total = sum(len(rows) for rows in results.values())
        if blank:
            warnings.append(f"「{name}」合并报表有 {blank} 行取不到数，已留空并写明原因")
        return f"报表 {len(results)} 张 {total} 行" + (f"，留空 {blank} 行" if blank else "")

    async def notes() -> str:
        stats = await _refresh_notes(db, project_id, year, context=context, tree=tree)
        parts = []
        stale = stats.get("stale_marked", 0)
        sections = stats.get("distinct_section_count", 0)
        nodes = stats.get("node_count", 0)
        refreshed = stats.get("refreshed_count", 0)
        failed = stats.get("failed_count", 0)
        note_status = stats.get("note_status", "skipped")

        if stale:
            parts.append(f"标记 {stale} 行待更新")
        parts.append(f"{sections} 个章节 × {nodes} 个节点")
        parts.append(f"刷新 {refreshed}")
        if failed:
            parts.append(f"失败 {failed}")
            warnings.append(f"「{name}」附注刷新有 {failed} 个章节×节点失败")
        parts.append(f"附注状态={note_status}")
        return "，".join(parts)

    bodies = {STEP_WORKSHEET: worksheet, STEP_TRIAL: trial, STEP_REPORT: report, STEP_NOTES: notes}
    all_ok = True
    async with _process_lock("target", project_id, year):
        for i, step in enumerate(STEP_ORDER):
            try:
                await _advisory_lock(db, project_id, year)
                detail = await bodies[step]()
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
            record(step, "succeeded", detail)
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
) -> PushResult:
    """执行一次推送（design §八）。本函数逐步 commit 调用方传入的会话。"""
    if trigger not in TRIGGERS:
        raise ValueError(f"未知的推送触发来源：{trigger}")
    run_id = uuid.uuid4()
    # 开始时间显式到微秒：库默认值在 SQLite 只到秒，同一秒内的多次推送按时间排序会不确定
    db.add(ConsolPushRun(id=run_id, project_id=project_id, year=year, trigger_source=trigger,
                         triggered_by=user_id, status="running", steps=[], warnings=[],
                         started_at=datetime.now(timezone.utc)))
    await db.commit()
    steps: list[dict] = []
    warnings: list[str] = []
    pushed: list[str] = []
    failed_projects = 0
    aborted = False

    # 为 source 项目建一次上下文，每个 target 派生自己的上下文
    from app.services.consol_context_service import build_consol_context
    from app.services.consol_tree_service import build_tree

    source_context = None
    source_tree = None
    try:
        source_tree = await build_tree(db, project_id)
        if source_tree is not None:
            source_context = await build_consol_context(db, project_id, year, tree=source_tree)
    except Exception as exc:  # noqa: BLE001 — context 构建失败不阻断推送
        logger.warning("合并推送 source context 构建失败（降级无 context）：%s", exc)

    try:
        for target in await push_targets(db, project_id):
            # 每个 target 重新解析树和上下文
            target_context = None
            target_tree = None
            if source_context is not None:
                try:
                    from app.services.consol_context_service import build_target_consol_context

                    target_tree = await build_tree(db, target)
                    target_context = await build_target_consol_context(
                        db, source_context, target, year, tree=target_tree,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("合并推送 target=%s context 构建失败（降级无 context）：%s", target, exc)

            if not await _push_one(
                db, target, year, steps, warnings,
                context=target_context, tree=target_tree,
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
    result = PushResult(run_id, project_id, year, status, pushed, steps, warnings)
    _broadcast(SSE_FAILED if status == "failed" else SSE_PUSHED, result, trigger)
    return result


def _broadcast(event: str, result: PushResult, trigger: str) -> None:
    try:
        from app.services.event_bus import event_bus

        payload = {
            "project_id": str(result.project_id), "year": result.year, "run_id": str(result.run_id),
            "status": result.status, "trigger": trigger, "trigger_label": TRIGGER_LABELS.get(trigger, trigger),
            "pushed_projects": list(result.pushed_projects), "warnings": list(result.warnings[:10]),
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


async def _run_queued(project_id: UUID, year: int, key: tuple[str, int]) -> PushResult | None:
    started = False
    try:
        async with _process_lock("run", project_id, year):
            started = True
            trigger, user_id = _QUEUED.pop(key, (TRIGGER_MANUAL, None))
            from app.core.database import async_session

            async with async_session() as db:
                return await push(db, project_id, year, trigger=trigger, user_id=user_id)
    except Exception:  # noqa: BLE001 —— 后台任务异常不外抛（push 内部已留痕；这里兜底记日志）
        logger.exception("后台合并推送失败：项目=%s 年度=%s", project_id, year)
        return None
    finally:
        if not started:
            _QUEUED.pop(key, None)


def pending_count() -> int:
    return len(_TASKS)


async def wait_for_pushes() -> None:
    """等待全部后台推送结束（测试与优雅停机用）。"""
    while _TASKS:
        await asyncio.gather(*list(_TASKS), return_exceptions=True)


# ─────────────────────────────── 查询 ───────────────────────────────


def run_to_dict(run: ConsolPushRun) -> dict:
    return {
        "id": str(run.id),
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
