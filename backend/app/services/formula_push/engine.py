"""公式推送引擎：读当前值 → 三态判定 → 写底稿（CAS）→ 写附注 → 目标状态 / 运行记录。

spec: chain-closure-phase2-formula-push-engine · design §五~§九 · 任务 10

一次运行 = 一个 (项目, 年度, 触发来源)：

1. 规则按触发来源过滤 → 按 wp_code 取 binding → 定位底稿（复核通过 / 已归档跳过）。
2. 读条目快照（remark + updated_at 版本）得叠加层 overlay。
3. 源值阶段 → 派生阶段：逐目标三态判定，决定写入的值落到叠加层；后续规则读叠加层，
   所以「行 → 明细合计 → 审定合计 → 语义槽 → 附注」在同一次运行里逐级生效。
4. 叠加层与快照逐条目比较，CAS 写回（adapter ``@raw`` 原文模式）。任一条目并发修改 ⇒
   整张底稿回滚到保存点、记「并发修改」、附注本次不推 —— 派生值与附注都依赖本底稿已落库
   的值，只写一部分会自相矛盾。
5. 附注阶段：按附注模板类型选章节，F2 / F3 主表逐单元格三态判定，合计按附注实际行重算。
6. 目标状态 upsert（跳过项 / 冲突项不写）+ 运行记录。

在调用方事务内执行、只 flush 不 commit；:func:`run_and_commit` 是路由与事件 handler 共用的提交包装
（成功 commit 后广播 SSE ``formula.pushed``；失败回滚并另记一条 failed 运行记录）。
引擎写入**不发布** ``WORKPAPER_SAVED``（防回环）。
"""
from __future__ import annotations

import asyncio
import copy
import logging
import uuid
import weakref
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm.attributes import flag_modified

from app.models.formula_push_models import FormulaPushRun, FormulaPushState
from app.services.formula_push import note_writer
from app.services.formula_push.bindings import get_binding, supported_wp_codes
from app.services.formula_push.policy import Decision, decide, values_equal
from app.services.formula_push.results import CONFLICT, SKIPPED, PushItem, RunResult, _enum_value, _jsonable
from app.services.formula_push.rules import TRIGGERS, PushRule, load_rules, note_addr_id, rules_for
from app.services.formula_runtime.adapters.workpaper import (
    RAW_CELL,
    VersionConflict,
    WorkpaperMutationAdapter,
    _version_from_timestamp,
)
from app.services.formula_runtime.contracts import CanonicalFormulaTarget, FormulaMutation

logger = logging.getLogger(__name__)

#: SSE 事件名（前端 ``src/types/sse.ts`` 同名登记）
SSE_EVENT = "formula.pushed"
MANUAL = "manual"
#: 冻结底稿：与平台编辑锁同口径（wopi_service / wp_sync_router：review_passed、archived 只读），
#: 另含旧值兼容的两个「复核通过」（working_paper_service.status_map 同样映射为复核通过）。
#: 复核状态 ``levelN_passed`` 是逐级中间态（下一步即 ``pending_level{N+1}``），不是整张底稿通过。
FROZEN_WP_STATUSES: Mapping[str, str] = {
    "review_passed": "复核通过",
    "archived": "已归档",
    "review_level1_passed": "一级复核通过",
    "review_level2_passed": "二级复核通过",
}
FROZEN_NOTE_STATUSES: frozenset[str] = frozenset({"confirmed"})
PERIOD_LABELS: Mapping[str, str] = {"end": "期末", "prior": "期初"}


@dataclass
class _StateWrite:
    """待落库的目标状态（底稿写入成功后才生效；冲突 / 跳过不产生）。"""

    addr_id: str
    rule_id: str
    domain: str
    wp_id: UUID | None
    note_section: str | None
    formula_value: Any
    current_after: Any
    state: str
    record_pushed: bool
    forced: bool


class PushActionError(ValueError):
    """用户操作不合法（采用 / 锁定的目标不存在、策略不允许等；路由转 400）。"""


# ── 规则 / 并发 / 年度 ────────────────────────────────────────────────────────


def known_derivations() -> frozenset[str]:
    names: set[str] = set()
    for code in supported_wp_codes():
        names |= set(get_binding(code).derivations)
    return frozenset(names)


def load_push_rules() -> tuple[PushRule, ...]:
    """规则清单（派生名按已接入 binding 校验，未实现的派生整份拒收）。"""
    return load_rules(known_derivations=known_derivations())


_PROCESS_LOCKS: weakref.WeakValueDictionary = weakref.WeakValueDictionary()


def _process_lock(project_id: UUID, year: int) -> asyncio.Lock:
    """同进程按 (项目, 年度) 串行。asyncio 锁绑定事件循环，故键里带循环 id。"""
    key = (id(asyncio.get_running_loop()), str(project_id), int(year))
    lock = _PROCESS_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _PROCESS_LOCKS[key] = lock
    return lock


def _dialect(db) -> str:
    return db.get_bind().dialect.name


async def _advisory_lock(db, project_id: UUID, year: int) -> None:
    """跨进程串行：PG 事务级咨询锁（随调用方事务提交 / 回滚释放）。SQLite 无此能力，跳过。"""
    if _dialect(db) != "postgresql":
        return
    await db.execute(
        sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": f"formula_push:{project_id}:{year}"},
    )


async def _project_audit_year(db, project_id: UUID) -> tuple[bool, int | None]:
    """(项目存在且未删除, 审计年度)。年度口径与全平台一致（project_audit_year 5 级兜底）。"""
    from app.models.core import Project
    from app.services.project_audit_year import resolve_project_audit_year

    project = await db.get(Project, project_id)
    if project is None or getattr(project, "is_deleted", False):
        return False, None
    return True, resolve_project_audit_year(project)


# ── 读 ────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Paper:
    id: UUID
    status: str | None


def frozen_reason(status: Any) -> str | None:
    label = FROZEN_WP_STATUSES.get(str(_enum_value(status) or ""))
    return f"底稿已{label}，公式推送不改写（重新打开编辑后下次推送纳入）" if label else None


async def _find_workpapers(db, project_id: UUID, wp_code: str) -> list[_Paper]:
    """裸 SQL，与写入适配器（``_verify_ownership`` / UPSERT）同一 uuid 传参口径。

    真库唯一索引 ``uq_wp_index_project_code (project_id, wp_code)`` 与
    ``uq_working_paper_project_index (project_id, wp_index_id)`` 都不带 ``is_deleted`` 条件 ⇒
    一个项目一个编码至多一张底稿。多于一张 = 约束被破坏，推送地址（不含 wp_id）会串，直接报错。
    """
    rows = (await db.execute(
        sa.text(
            "SELECT wp.id, wp.status FROM working_paper wp "
            "JOIN wp_index wi ON wi.id = wp.wp_index_id "
            "WHERE wp.project_id = :pid AND wi.project_id = :pid AND wi.wp_code = :code "
            "AND wp.is_deleted = false AND wi.is_deleted = false "
            "ORDER BY wp.id"
        ),
        {"pid": str(project_id), "code": wp_code},
    )).all()
    if len(rows) > 1:
        raise RuntimeError(f"项目 {project_id} 有 {len(rows)} 张 {wp_code} 底稿，违反唯一约束，公式推送中止")
    return [_Paper(id=UUID(str(r[0])), status=_enum_value(r[1])) for r in rows]


async def _read_entries(db, wp_id: UUID, wp_code: str) -> dict[str, tuple[Any, str]]:
    """条目快照 ``item_id → (remark, CAS 版本)``；版本口径与适配器 ``apply_many`` 的校验一致。"""
    rows = (await db.execute(
        sa.text(
            "SELECT item_id, remark, updated_at FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id LIKE :prefix"
        ),
        {"wp_id": str(wp_id), "prefix": f"{wp_code}-%"},
    )).all()
    return {r[0]: (r[1], _version_from_timestamp(r[2])) for r in rows}


async def _load_states(db, project_id: UUID, year: int) -> dict[str, FormulaPushState]:
    rows = (await db.execute(
        sa.select(FormulaPushState).where(
            FormulaPushState.project_id == project_id, FormulaPushState.year == year,
        )
    )).scalars().all()
    return {r.addr_id: r for r in rows}


@dataclass
class _Ctx:
    """一次运行的共享状态。"""

    db: Any
    project_id: UUID
    year: int
    triggered_by: UUID | None
    force: frozenset[str]
    now: datetime
    states: dict[str, FormulaPushState]
    result: RunResult
    state_writes: list[_StateWrite] = field(default_factory=list)

    def skip(self, rule_id: str, stage: str, domain: str, addr_id: str | None, reason: str) -> None:
        self.result.items.append(PushItem(rule_id, stage, domain, addr_id, SKIPPED, reason=reason))

    def decide(
        self, policy: str, *, addr_id: str, formula_value: Any, current_value: Any,
    ) -> Decision:
        """底稿目标三态判定；「采用公式值」（force）对可编辑目标直接写入并转 auto。"""
        if addr_id in self.force and policy == "editable":
            if values_equal(current_value, formula_value):
                return Decision("unchanged", "auto", differs=False, record_pushed=True)
            return Decision("write", "auto", differs=True, record_pushed=True)
        row = self.states.get(addr_id)
        return decide(
            policy,
            formula_value=formula_value,
            current_value=current_value,
            last_pushed_value=row.last_pushed_value if row is not None else None,
            prior_state=row.state if row is not None else None,
        )


def decide_note(*, formula_value: Any, current_value: Any, cell_mode: str | None) -> Decision:
    """附注单元格判定：以附注自身标记为准（需求 3.5），其余跟随公式值。

    底稿来源章节（``_source=workpaper``）的数值只有「同步到附注」类写入方：附注编辑器的保存落在
    ``_tables``，而读时投影每次都从 ``sub_table_data`` 重建 ``_tables``（``get_note_detail``）——
    ``sub_table_data`` 里不存在未带标记的人工值，推送与点「同步到附注」同效。保留的只有单元格
    ``_cell_modes`` manual / locked 与整节 ``_manual_override``（已折算进 ``cell_mode``）。
    推送状态表不参与附注判定（面板对附注目标不提供采用 / 锁定，见 :func:`_checked_targets`）：
    否则上次因附注标记记下的 locked，会在用户去掉标记后冒充面板锁定继续挡住推送。
    """
    if cell_mode is not None:
        return decide("editable", formula_value=formula_value, current_value=current_value, external_mode=cell_mode)
    return decide("derived", formula_value=formula_value, current_value=current_value)


# ── 运行 ──────────────────────────────────────────────────────────────────────


async def run(
    db,
    *,
    project_id: UUID,
    year: int,
    trigger: str,
    triggered_by: UUID | None = None,
    wp_id: UUID | None = None,
    dry_run: bool = False,
    force_addr_ids: Iterable[str] = (),
) -> RunResult:
    """执行一次推送（调用方事务内，只 flush 不 commit）。

    :param trigger: ``TRIAL_BALANCE_UPDATED`` / ``WORKPAPER_SAVED`` / ``manual``（决定跑哪些规则）
    :param wp_id: 只推这张底稿（``WORKPAPER_SAVED`` 用）
    :param dry_run: 在保存点内执行后整体回滚（含运行记录），返回「将写入 / 保留 / 待确认」
    :param force_addr_ids: 「采用公式值」的目标 —— 可编辑目标直接写入当前公式值并转 auto
    """
    if trigger not in TRIGGERS:
        raise ValueError(f"未知触发来源 {trigger!r}（可选 {TRIGGERS}）")
    force = frozenset(str(a) for a in force_addr_ids)
    async with _process_lock(project_id, year):
        await _advisory_lock(db, project_id, year)
        if not dry_run:
            return await _execute(
                db, project_id=project_id, year=year, trigger=trigger,
                triggered_by=triggered_by, wp_id=wp_id, force=force,
            )
        savepoint = await db.begin_nested()
        try:
            result = await _execute(
                db, project_id=project_id, year=year, trigger=trigger,
                triggered_by=triggered_by, wp_id=wp_id, force=force,
            )
        finally:
            await savepoint.rollback()
        result.dry_run = True
        result.run_id = None
        return result


async def _execute(
    db, *, project_id: UUID, year: int, trigger: str, triggered_by: UUID | None,
    wp_id: UUID | None, force: frozenset[str],
) -> RunResult:
    result = RunResult(project_id=project_id, year=year, trigger=trigger, forced=sorted(force))
    exists, audit_year = await _project_audit_year(db, project_id)
    if not exists:
        raise PushActionError("项目不存在或已删除")
    if audit_year != year:
        # 底稿 / 附注只属于项目审计年度；把上年试算表（比较数导入等）推进本年底稿是错数
        msg = f"公式推送只作用于项目审计年度（{audit_year or '未设置'}），本次为 {year} 年度，未推送"
        if trigger == MANUAL:
            raise PushActionError(msg)
        result.add_warning(msg)
        return result

    rules = load_push_rules()
    plan: list[tuple[str, Any, tuple[PushRule, ...], list[_Paper]]] = []
    for code in supported_wp_codes():
        code_rules = rules_for(rules, wp_code=code, trigger=trigger)
        if not code_rules:
            continue
        papers = await _find_workpapers(db, project_id, code)
        if wp_id is not None and all(p.id != wp_id for p in papers):
            continue  # 事件指向的底稿不是本项目在用的该编码底稿
        if papers:
            plan.append((code, get_binding(code), code_rules, papers))
    if not plan and trigger != MANUAL:
        return result  # 事件触发且无目标底稿：不落运行记录（避免每次重算都记一条空记录）

    now = datetime.now(timezone.utc)
    run_row = FormulaPushRun(
        id=uuid.uuid4(), project_id=project_id, year=year, trigger_source=trigger,
        triggered_by=triggered_by, status="running", detail={}, started_at=now,
    )
    db.add(run_row)
    await db.flush()
    result.run_id = run_row.id
    ctx = _Ctx(
        db=db, project_id=project_id, year=year, triggered_by=triggered_by, force=force,
        now=now, states=await _load_states(db, project_id, year), result=result,
    )
    if not plan:
        result.add_warning("本项目没有已接入公式推送的底稿（当前接入：" + "、".join(supported_wp_codes()) + "）")
    for code, binding, code_rules, papers in plan:
        await _push_workpaper(ctx, wp_code=code, binding=binding, rules=code_rules, paper=papers[0])
    touched = {i.addr_id for i in result.items}
    for addr in sorted(force - touched):
        result.add_warning(f"目标 {addr} 本次没有产生推送（行已删除或来源缺失），未采用")

    await _save_states(ctx, run_row.id)
    run_row.status = result.status
    run_row.written_count = result.written_count
    run_row.unchanged_count = result.unchanged_count
    run_row.kept_count = result.kept_count
    run_row.skipped_count = result.skipped_count
    run_row.detail = result.detail()
    run_row.finished_at = datetime.now(timezone.utc)
    await db.flush()
    return result


async def _push_workpaper(
    ctx: _Ctx, *, wp_code: str, binding: Any, rules: tuple[PushRule, ...], paper: _Paper,
) -> None:
    result = ctx.result
    frozen = frozen_reason(paper.status)
    if frozen:
        ctx.skip("*", "source", "workpaper", wp_code, frozen)
        result.workpapers.append({"wp_id": str(paper.id), "wp_code": wp_code, "status": "frozen", "reason": frozen})
        return
    sources = await binding.load_sources(ctx.db, ctx.project_id, ctx.year, paper.id)
    for text in sources.warnings:
        result.add_warning(text)
    snapshot = await _read_entries(ctx.db, paper.id, wp_code)
    entries = {item: remark for item, (remark, _) in snapshot.items()}
    overlay: dict[str, Any] = dict(entries)
    pending: list[tuple[str, PushItem, _StateWrite]] = []
    effective_items: set[str] = set()
    for stage in ("source", "derived"):
        for rule in (r for r in rules if r.stage == stage):
            targets, skips = binding.workpaper_targets(rule, overlay, sources)
            for s in skips:
                ctx.skip(rule.rule_id, stage, "workpaper", s.addr_id, s.reason)
            for t in targets:
                decision = ctx.decide(
                    rule.policy, addr_id=t.addr_id, formula_value=t.formula_value, current_value=t.current_value,
                )
                action = decision.action
                if decision.writes:
                    if binding.apply(overlay, t, t.formula_value):
                        effective_items.add(t.item_id)
                    else:
                        action = "unchanged"  # 空写（如占位行 0 → 0）：存储值没变，如实记为未变化
                item = PushItem(rule.rule_id, stage, "workpaper", t.addr_id, action, decision.state,
                                formula=t.formula_value, current=t.current_value)
                pending.append((t.item_id, item, _StateWrite(
                    addr_id=t.addr_id, rule_id=rule.rule_id, domain="workpaper", wp_id=paper.id,
                    note_section=None, formula_value=t.formula_value,
                    current_after=t.formula_value if decision.writes else t.current_value,
                    state=decision.state, record_pushed=decision.record_pushed, forced=t.addr_id in ctx.force,
                )))
    for text in binding.entry_warnings(overlay):
        result.add_warning(text)

    changed = sorted(effective_items)
    conflict = await _write_entries(ctx, paper.id, wp_code, changed, overlay, snapshot)
    if conflict is not None:
        reason = f"并发修改：条目「{conflict}」在推送期间被保存，本底稿本次未写入（下次推送重新计算）"
        for _, item, _ in pending:
            item.action, item.state, item.reason = CONFLICT, None, reason
            result.items.append(item)
        for rule in (r for r in rules if r.stage == "note"):
            ctx.skip(rule.rule_id, "note", "note", None, "底稿并发修改，附注本次未推送")
        result.status = "partial"
        result.workpapers.append({"wp_id": str(paper.id), "wp_code": wp_code, "status": "conflict", "reason": reason})
        return

    for _, item, state_write in pending:
        result.items.append(item)
        ctx.state_writes.append(state_write)
    result.changed_items.extend(changed)
    if changed:
        result.wp_ids.append(str(paper.id))

    sections: list[str] = []
    for rule in (r for r in rules if r.stage == "note"):
        section = await _push_note(ctx, rule=rule, binding=binding, overlay=overlay, sources=sources, paper=paper)
        if section:
            sections.append(section)
    result.workpapers.append({
        "wp_id": str(paper.id), "wp_code": wp_code, "status": "pushed",
        "changed_items": changed, "note_sections": sections,
    })


async def _write_entries(
    ctx: _Ctx, wp_id: UUID, wp_code: str, changed: list[str],
    overlay: Mapping[str, Any], snapshot: Mapping[str, tuple[Any, str]],
) -> str | None:
    """逐条目 CAS 写回；整张底稿一个保存点。返回冲突条目 id（None = 全部写入成功）。

    期望版本取**快照读取时**的版本（不经 ``prepare_many`` 重读）：从读快照到写入的整个窗口
    都在并发检测范围内，用户在这期间保存过的条目一定判冲突。
    """
    if not changed:
        return None
    adapter = WorkpaperMutationAdapter(ctx.db)
    savepoint = await ctx.db.begin_nested()
    try:
        for item_id in changed:
            before, version = snapshot.get(item_id, (None, _version_from_timestamp(None)))
            target = CanonicalFormulaTarget(
                domain="workpaper", project_id=ctx.project_id, year=ctx.year,
                addr_id=f"{wp_code}/*/{item_id}",
                locator={"wp_id": str(wp_id), "item": item_id, "cell": RAW_CELL},
                wp_id=wp_id,
            )
            await adapter.apply_many([FormulaMutation(
                target=target, before_value=before, after_value=overlay[item_id], expected_version=version,
            )])
    except VersionConflict as exc:
        await savepoint.rollback()
        return str(exc.target.locator.get("item"))
    except BaseException:
        await savepoint.rollback()
        raise
    await savepoint.commit()
    return None


async def _push_note(
    ctx: _Ctx, *, rule: PushRule, binding: Any, overlay: Mapping[str, Any], sources: Any, paper: _Paper,
) -> str | None:
    """附注主表推送（按附注模块同一模板类型权威选章节）；返回有写入的章节号。"""
    from app.models.report_models import DisclosureNote

    table_name = rule.target.table
    template_type = sources.template_type
    section = rule.target.sections.get(template_type) if template_type else None
    if section is None:
        ctx.skip(rule.rule_id, "note", "note", None,
                 f"附注模板类型「{template_type or '未设置'}」没有对应的附注章节，未推送附注")
        return None
    section_addr = f"note://{section}/{table_name}"
    note = (await ctx.db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.project_id == ctx.project_id,
            DisclosureNote.year == ctx.year,
            DisclosureNote.note_section == section,
            DisclosureNote.is_deleted == sa.false(),
        ).with_for_update()
    )).scalar_one_or_none()
    reason = None
    if note is None:
        reason = f"附注尚未生成「{section} {table_name}」章节（在附注模块生成后下次推送纳入）"
    elif (note.section_title or "").strip() != table_name:
        reason = f"附注 {section} 是「{note.section_title}」章节，不是「{table_name}」，未推送"
    elif str(_enum_value(note.status)) in FROZEN_NOTE_STATUSES:
        reason = "附注章节已确认，公式推送不改写"
    table_data = copy.deepcopy(note.table_data) if note is not None else None
    table = None
    if reason is None:
        table, reason = note_writer.locate_table(table_data, table_name)
    if table is None:
        ctx.skip(rule.rule_id, "note", "note", section_addr, reason or "附注表格无法定位")
        return None

    wrote = False
    for row in binding.note_rows(overlay, template_type):
        if row["is_total"] or row["is_memo"]:
            continue  # 合计按附注实际行重算（见 _push_note_total）；「其中：」备注行不由底稿取数
        index = note_writer.find_row(table.rows, [row["note_label"], row["label"]])
        for field_name, (value_key, period) in note_writer.NOTE_FIELDS.items():
            addr = note_addr_id(section, table_name, row["note_label"], period)
            if index is None:
                ctx.skip(rule.rule_id, "note", "note", addr,
                         f"附注「{table_name}」表中没有「{row['note_label']}」行（公式推送不新建行）")
            elif not row[f"{value_key}_resolved"]:
                ctx.skip(rule.rule_id, "note", "note", addr, "底稿未取到该行数值（本项目无此科目），附注保持原值")
            else:
                wrote |= _push_note_cell(ctx, rule=rule, section=section, addr=addr, table=table,
                                         row=table.rows[index], field_name=field_name,
                                         value=row[value_key], paper=paper)
    wrote |= _push_note_total(ctx, rule=rule, section=section, table_name=table_name, table=table, paper=paper)

    if not wrote:
        return None
    # 同步指纹：与 sync-from-workpaper 同写，pull-from-workpapers 据此认定「真正同步过」（需求 5）
    table_data["_last_sync_wp_id"] = str(paper.id)
    table_data["_last_sync_at"] = ctx.now.isoformat()
    note.table_data = table_data
    flag_modified(note, "table_data")
    note.last_sync_source = "formula_push"
    note.last_sync_wp_id = paper.id
    note.last_sync_at = ctx.now
    note.last_sync_user_id = ctx.triggered_by
    note.updated_by = ctx.triggered_by
    note.updated_at = ctx.now
    await ctx.db.flush()
    ctx.result.note_sections.append(section)
    return section


def _push_note_cell(
    ctx: _Ctx, *, rule: PushRule, section: str, addr: str, table: note_writer.NoteTable,
    row: dict, field_name: str, value: float, paper: _Paper,
) -> bool:
    ok, current, cell_mode = note_writer.read_cell(row, field_name, table.value_keys)
    if not ok:
        period = note_writer.NOTE_FIELDS[field_name][1]
        ctx.skip(rule.rule_id, "note", "note", addr, f"附注表缺少「{PERIOD_LABELS[period]}」列")
        return False
    mode = note_writer.external_mode(table.section_locked, cell_mode)
    decision = decide_note(formula_value=value, current_value=current, cell_mode=mode)
    if decision.writes:
        note_writer.write_cell(row, field_name, value, table.value_keys)
    _record_note(ctx, rule, section, addr, decision, value, current, paper, _note_keep_reason(mode, decision))
    return decision.writes


def _note_keep_reason(mode: str | None, decision: Decision) -> str | None:
    if not decision.kept:
        return None
    return "附注中该单元格被标记为锁定（或整节人工覆盖），保留原值" if mode == "locked" else \
        "附注中该单元格被标记为人工填写，保留原值"


def _push_note_total(
    ctx: _Ctx, *, rule: PushRule, section: str, table_name: str, table: note_writer.NoteTable, paper: _Paper,
) -> bool:
    """合计 = 合计行之前各非合计行之和（按附注实际行，人工行一并计入）；单元格自身人工 / 锁定则保留。"""
    index = note_writer.find_total_row(table.rows)
    if index is None:
        return False
    total_row = table.rows[index]
    label = note_writer.row_label(total_row) or "合计"
    wrote = False
    for field_name, (_, period) in note_writer.NOTE_FIELDS.items():
        ok, current, cell_mode = note_writer.read_cell(total_row, field_name, table.value_keys)
        if not ok:
            continue
        value = note_writer.total_formula(table.rows, index, field_name, table.value_keys)
        addr = note_addr_id(section, table_name, label, period)
        mode = note_writer.external_mode(table.section_locked, cell_mode)
        decision = decide_note(formula_value=value, current_value=current, cell_mode=mode)
        if decision.writes:
            note_writer.write_cell(total_row, field_name, value, table.value_keys)
            wrote = True
        _record_note(ctx, rule, section, addr, decision, value, current, paper, _note_keep_reason(mode, decision))
    return wrote


def _record_note(
    ctx: _Ctx, rule: PushRule, section: str, addr: str, decision: Decision,
    value: Any, current: Any, paper: _Paper, reason: str | None,
) -> None:
    ctx.result.items.append(PushItem(
        rule.rule_id, "note", "note", addr, decision.action, decision.state,
        formula=value, current=current, reason=reason,
    ))
    ctx.state_writes.append(_StateWrite(
        addr_id=addr, rule_id=rule.rule_id, domain="note", wp_id=paper.id, note_section=section,
        formula_value=value, current_after=value if decision.writes else current,
        state=decision.state, record_pushed=decision.record_pushed, forced=addr in ctx.force,
    ))


async def _save_states(ctx: _Ctx, run_id: UUID) -> None:
    """目标状态 upsert：公式值 / 当前值每次都更新；上次推送值只在写入或一致时更新。"""
    for w in ctx.state_writes:
        row = ctx.states.get(w.addr_id)
        if row is None:
            row = FormulaPushState(
                id=uuid.uuid4(), project_id=ctx.project_id, year=ctx.year, addr_id=w.addr_id,
                rule_id=w.rule_id, domain=w.domain, state=w.state,
            )
            ctx.db.add(row)
            ctx.states[w.addr_id] = row
        row.rule_id = w.rule_id
        row.domain = w.domain
        row.wp_id = w.wp_id
        row.note_section = w.note_section
        row.last_formula_value = _jsonable(w.formula_value)
        row.current_value = _jsonable(w.current_after)
        if w.record_pushed:
            row.last_pushed_value = _jsonable(w.formula_value)
        row.state = w.state
        row.last_run_id = run_id
        row.updated_at = ctx.now
        if w.forced:
            row.updated_by = ctx.triggered_by
    await ctx.db.flush()


# ── 提交包装（路由与事件 handler 共用）────────────────────────────────────────


async def run_and_commit(
    db,
    *,
    project_id: UUID,
    year: int,
    trigger: str,
    triggered_by: UUID | None = None,
    wp_id: UUID | None = None,
    dry_run: bool = False,
    force_addr_ids: Iterable[str] = (),
) -> RunResult:
    """执行并提交；成功后广播 ``formula.pushed``。失败回滚、另记一条 failed 运行记录后上抛。

    ``dry_run`` 只回滚不提交、不记失败、不广播（试跑不留任何痕迹）。
    """
    try:
        result = await run(
            db, project_id=project_id, year=year, trigger=trigger, triggered_by=triggered_by,
            wp_id=wp_id, dry_run=dry_run, force_addr_ids=force_addr_ids,
        )
        if dry_run:
            await db.rollback()
        else:
            await db.commit()
    except Exception as exc:
        await db.rollback()
        if not dry_run and not isinstance(exc, PushActionError):
            await _record_failure(db, project_id=project_id, year=year, trigger=trigger,
                                  triggered_by=triggered_by, error=exc)
        raise
    if not dry_run and result.run_id is not None:
        _broadcast(result)
    return result


async def _record_failure(
    db, *, project_id: UUID, year: int, trigger: str, triggered_by: UUID | None, error: BaseException,
) -> None:
    """失败也要在「最近推送」里看得见（否则面板显示的是上一次成功，掩盖了失败）。"""
    now = datetime.now(timezone.utc)
    try:
        db.add(FormulaPushRun(
            id=uuid.uuid4(), project_id=project_id, year=year, trigger_source=trigger,
            triggered_by=triggered_by, status="failed", started_at=now, finished_at=now,
            detail={"error": f"{type(error).__name__}: {error}"[:2000]},
        ))
        await db.commit()
    except Exception:  # noqa: BLE001 — 记录失败本身不能掩盖原始异常
        logger.exception("formula_push: 失败运行记录写入失败 project=%s year=%s", project_id, year)
        await db.rollback()


def _broadcast(result: RunResult) -> None:
    try:
        from app.services.event_bus import event_bus

        event_bus.broadcast_raw(SSE_EVENT, result.summary())
    except Exception:  # noqa: BLE001 — SSE 是提交后的通知，失败不影响已落库数据
        logger.warning("formula_push: SSE 广播失败 project=%s", result.project_id, exc_info=True)
