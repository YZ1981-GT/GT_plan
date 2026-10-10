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
from app.services.formula_push.policy import Decision, decide, decide_note, values_equal
from app.services.formula_push.results import CONFLICT, SKIPPED, PushItem, RunResult, _enum_value, _jsonable
from app.services.formula_push.rules import (
    TRIGGERS,
    BindingSpec,
    PushRule,
    load_rules,
    note_addr_id,
    rules_for,
)
from app.services.formula_runtime.adapters.workpaper import (
    RAW_CELL,
    VersionConflict,
    WorkpaperMutationAdapter,
    _version_from_timestamp,
)
from app.services.formula_runtime.contracts import CanonicalFormulaTarget, FormulaMutation

logger = logging.getLogger(__name__)

#: SSE 事件名
SSE_EVENT = "formula.pushed"
MANUAL = "manual"
#: 冻结底稿状态（复核通过 / 已归档 / 逐级中间态）
FROZEN_WP_STATUSES: Mapping[str, str] = {
    "review_passed": "复核通过", "archived": "已归档",
    "review_level1_passed": "一级复核通过", "review_level2_passed": "二级复核通过",
}
FROZEN_NOTE_STATUSES: frozenset[str] = frozenset({"confirmed"})
PERIOD_LABELS: Mapping[str, str] = {"end": "期末", "prior": "期初"}


@dataclass
class _StateWrite:
    """待落库的目标状态。"""

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

def _binding_specs() -> dict[str, BindingSpec]:
    """构建规则校验所需的注册 binding 元信息快照。"""
    specs: dict[str, BindingSpec] = {}
    for code in supported_wp_codes():
        binding = get_binding(code)
        specs[code] = BindingSpec(
            four_table_slots=frozenset(binding.four_table_slots),
            derivations=frozenset(binding.derivations),
            tb_columns=frozenset(binding.tb_columns),
        )
    return specs


def known_derivations() -> frozenset[str]:
    """兼容旧调用方：返回注册 binding 的派生名并集。"""
    names: set[str] = set()
    for spec in _binding_specs().values():
        names |= set(spec.derivations)
    return frozenset(names)


def load_push_rules() -> tuple[PushRule, ...]:
    """规则清单按每个 binding 自己的槽名、派生名和试算表列校验。"""
    return load_rules(binding_specs=_binding_specs())


_PROCESS_LOCKS: weakref.WeakValueDictionary = weakref.WeakValueDictionary()


def _process_lock(project_id: UUID, year: int) -> asyncio.Lock:
    """同进程按 (项目, 年度) 串行。"""
    key = (id(asyncio.get_running_loop()), str(project_id), int(year))
    lock = _PROCESS_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _PROCESS_LOCKS[key] = lock
    return lock


def _dialect(db) -> str:
    return db.get_bind().dialect.name


async def _advisory_lock(db, project_id: UUID, year: int) -> None:
    """跨进程串行：PG 咨询锁；SQLite 跳过。"""
    if _dialect(db) != "postgresql":
        return
    await db.execute(
        sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": f"formula_push:{project_id}:{year}"},
    )


async def _project_audit_year(db, project_id: UUID) -> tuple[bool, int | None]:
    """(项目存在且未删除, 审计年度)。"""
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
    paper_code: str | None = None


def frozen_reason(status: Any) -> str | None:
    label = FROZEN_WP_STATUSES.get(str(_enum_value(status) or ""))
    return f"底稿已{label}，公式推送不改写（重新打开编辑后下次推送纳入）" if label else None


async def _find_workpapers(db, project_id: UUID, wp_code: str) -> list[_Paper]:
    """裸 SQL 按编码找底稿；一个项目一个编码至多一张（多于一张直接报错）。"""
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
    return [_Paper(id=UUID(str(r[0])), status=_enum_value(r[1]), paper_code=wp_code) for r in rows]


async def _read_entries(
    db, wp_id: UUID, wp_code: str, storage_field: str = "remark",
) -> dict[str, tuple[Any, str]]:
    """条目快照 ``item_id → (column_value, CAS 版本)``。

    ``storage_field`` 选择从 ``remark`` 或 ``conclusion`` 列读取。
    """
    if storage_field == "conclusion":
        sql = (
            "SELECT item_id, conclusion, updated_at FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id LIKE :prefix"
        )
    else:
        sql = (
            "SELECT item_id, remark, updated_at FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id LIKE :prefix"
        )
    rows = (await db.execute(
        sa.text(sql),
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
        """底稿目标三态判定；「采用公式值」（force）直接写入并转 auto。"""
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


# ── 运行 ──────────────────────────────────────────────────────────────────────


async def run(
    db,
    *,
    project_id: UUID,
    year: int,
    trigger: str,
    triggered_by: UUID | None = None,
    wp_id: UUID | None = None,
    codes: Iterable[str] | None = None,
    dry_run: bool = False,
    force_addr_ids: Iterable[str] = (),
) -> RunResult:
    """执行一次推送（调用方事务内，只 flush 不 commit）。"""
    if trigger not in TRIGGERS:
        raise ValueError(f"未知触发来源 {trigger!r}（可选 {TRIGGERS}）")
    force = frozenset(str(a) for a in force_addr_ids)
    selected_codes = frozenset(str(code).strip() for code in codes or () if str(code).strip()) if codes is not None else None
    async with _process_lock(project_id, year):
        await _advisory_lock(db, project_id, year)
        if not dry_run:
            return await _execute(
                db, project_id=project_id, year=year, trigger=trigger,
                triggered_by=triggered_by, wp_id=wp_id, codes=selected_codes, force=force,
            )
        savepoint = await db.begin_nested()
        try:
            result = await _execute(
                db, project_id=project_id, year=year, trigger=trigger,
                triggered_by=triggered_by, wp_id=wp_id, codes=selected_codes, force=force,
            )
        finally:
            await savepoint.rollback()
        result.dry_run = True
        result.run_id = None
        return result


async def _execute(
    db, *, project_id: UUID, year: int, trigger: str, triggered_by: UUID | None,
    wp_id: UUID | None, codes: frozenset[str] | None, force: frozenset[str],
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
    plan: list[tuple[str, Any, tuple[PushRule, ...], list[_Paper], list[str]]] = []
    for code in supported_wp_codes():
        if codes is not None and code not in codes:
            continue
        code_rules = rules_for(rules, wp_code=code, trigger=trigger)
        if not code_rules:
            continue
        binding = get_binding(code)
        paper_codes = tuple(getattr(binding, "paper_codes", None) or (code,))
        papers: list[_Paper] = []
        missing: list[str] = []
        for pc in paper_codes:
            found = await _find_workpapers(db, project_id, pc)
            if found:
                papers.extend(found)
            else:
                missing.append(pc)
        if wp_id is not None:
            # 事件指向具体底稿：只推命中的那一张（分册也算命中），其余册本次不动
            papers = [p for p in papers if p.id == wp_id]
            missing = []
            if not papers:
                continue  # 事件指向的底稿不是本 binding 在用的任一底稿
        if papers or missing:
            plan.append((code, binding, code_rules, papers, missing))
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
    for code, binding, code_rules, papers, missing_codes in plan:
        # 声明了分册但该分册不存在 ⇒ 跳过并说明（ADR-FPA-008），不建保存点、不报错
        for mc in missing_codes:
            ctx.skip("*", "source", "workpaper", None,
                     f"binding 声明的分册 {mc} 在本项目不存在，未推送（项目创建该底稿后下次推送纳入）")
        # 附注 owner = 声明顺序首张实际底稿；frozen 则附注本次不推（真多册附注留给分册 canary 验证）
        note_owner_id: UUID | None = papers[0].id if papers else None
        for paper in papers:
            is_note_owner = paper.id == note_owner_id
            checkpoint = _workpaper_checkpoint(ctx)
            savepoint = await db.begin_nested()
            try:
                await _push_workpaper(
                    ctx, wp_code=code, binding=binding, rules=code_rules,
                    paper=paper, push_note=is_note_owner,
                )
            except Exception as exc:  # noqa: BLE001 — 单张底稿隔离
                await savepoint.rollback()
                _restore_workpaper_checkpoint(ctx, checkpoint)
                paper_label = paper.paper_code or code
                reason = _workpaper_failure_reason(paper_label, exc)
                result.status = "partial"
                result.add_warning(reason)
                result.workpapers.append({
                    "wp_id": str(paper.id), "wp_code": code,
                    "paper_code": paper.paper_code or code,
                    "status": "failed", "reason": reason,
                })
                logger.warning(
                    "formula_push: 底稿失败，已回滚保存点并继续 project=%s year=%s wp=%s paper=%s",
                    ctx.project_id, ctx.year, code, paper.paper_code, exc_info=True,
                )
            else:
                await savepoint.commit()
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


@dataclass(frozen=True)
class _WorkpaperCheckpoint:
    """底稿保存点外的共享结果快照。"""

    item_count: int
    warning_count: int
    workpaper_count: int
    changed_item_count: int
    note_section_count: int
    wp_id_count: int
    state_write_count: int


def _workpaper_checkpoint(ctx: _Ctx) -> _WorkpaperCheckpoint:
    result = ctx.result
    return _WorkpaperCheckpoint(
        item_count=len(result.items),
        warning_count=len(result.warnings),
        workpaper_count=len(result.workpapers),
        changed_item_count=len(result.changed_items),
        note_section_count=len(result.note_sections),
        wp_id_count=len(result.wp_ids),
        state_write_count=len(ctx.state_writes),
    )


def _restore_workpaper_checkpoint(ctx: _Ctx, checkpoint: _WorkpaperCheckpoint) -> None:
    result = ctx.result
    del result.items[checkpoint.item_count:]
    del result.warnings[checkpoint.warning_count:]
    del result.workpapers[checkpoint.workpaper_count:]
    del result.changed_items[checkpoint.changed_item_count:]
    del result.note_sections[checkpoint.note_section_count:]
    del result.wp_ids[checkpoint.wp_id_count:]
    del ctx.state_writes[checkpoint.state_write_count:]


def _workpaper_failure_reason(wp_code: str, error: BaseException) -> str:
    detail = str(error).strip() or type(error).__name__
    return f"底稿 {wp_code} 公式推送失败，已回滚本底稿写入：{detail}"[:2000]


async def _push_workpaper(
    ctx: _Ctx, *, wp_code: str, binding: Any, rules: tuple[PushRule, ...], paper: _Paper,
    push_note: bool = True,
) -> None:
    result = ctx.result
    paper_code = paper.paper_code or wp_code

    def _remap(addr: str | None) -> str | None:
        """将 binding 返回地址的首段从主编码替换为实际册编码（单册时恒等）。"""
        if addr is None or paper_code == wp_code:
            return addr
        # 地址格式 "{wp_code}/..." → "{paper_code}/..."
        if addr.startswith(f"{wp_code}/"):
            return paper_code + addr[len(wp_code):]
        return addr

    frozen = frozen_reason(paper.status)
    if frozen:
        ctx.skip("*", "source", "workpaper", _remap(wp_code), frozen)
        result.workpapers.append({
            "wp_id": str(paper.id), "wp_code": wp_code, "paper_code": paper_code,
            "status": "frozen", "reason": frozen,
        })
        return
    sources = await binding.load_sources(ctx.db, ctx.project_id, ctx.year, paper.id)
    for text in sources.warnings:
        result.add_warning(text)
    # 从 binding 获取存储列（默认 remark，N3 等使用 conclusion）
    storage_field = getattr(binding, "storage_field", "remark")
    snapshot = await _read_entries(ctx.db, paper.id, wp_code, storage_field=storage_field)
    entries = {item: col_val for item, (col_val, _) in snapshot.items()}
    overlay: dict[str, Any] = dict(entries)
    pending: list[tuple[str, PushItem, _StateWrite]] = []
    effective_items: set[str] = set()
    for stage in ("source", "derived"):
        for rule in (r for r in rules if r.stage == stage):
            targets, skips = binding.workpaper_targets(rule, overlay, sources)
            for s in skips:
                ctx.skip(rule.rule_id, stage, "workpaper", _remap(s.addr_id), s.reason)
            for t in targets:
                addr = _remap(t.addr_id)
                decision = ctx.decide(
                    rule.policy, addr_id=addr, formula_value=t.formula_value, current_value=t.current_value,
                )
                action = decision.action
                if decision.writes:
                    if binding.apply(overlay, t, t.formula_value):
                        effective_items.add(t.item_id)
                    else:
                        action = "unchanged"
                item = PushItem(rule.rule_id, stage, "workpaper", addr, action, decision.state,
                                formula=t.formula_value, current=t.current_value)
                pending.append((t.item_id, item, _StateWrite(
                    addr_id=addr, rule_id=rule.rule_id, domain="workpaper", wp_id=paper.id,
                    note_section=None, formula_value=t.formula_value,
                    current_after=t.formula_value if decision.writes else t.current_value,
                    state=decision.state, record_pushed=decision.record_pushed, forced=addr in ctx.force,
                )))
    for text in binding.entry_warnings(overlay):
        result.add_warning(text)

    changed = sorted(effective_items)
    conflict = await _write_entries(
        ctx, paper.id, paper_code, changed, overlay, snapshot,
        storage_field=storage_field,
    )
    if conflict is not None:
        reason = f"并发修改：条目「{conflict}」在推送期间被保存，本底稿本次未写入（下次推送重新计算）"
        for _, item, _ in pending:
            item.action, item.state, item.reason = CONFLICT, None, reason
            result.items.append(item)
        if push_note:
            for rule in (r for r in rules if r.stage == "note"):
                ctx.skip(rule.rule_id, "note", "note", None, "底稿并发修改，附注本次未推送")
        result.status = "partial"
        result.workpapers.append({
            "wp_id": str(paper.id), "wp_code": wp_code, "paper_code": paper_code,
            "status": "conflict", "reason": reason,
        })
        return

    for _, item, state_write in pending:
        result.items.append(item)
        ctx.state_writes.append(state_write)
    result.changed_items.extend(changed)
    if changed:
        result.wp_ids.append(str(paper.id))

    sections: list[str] = []
    if push_note:
        for rule in (r for r in rules if r.stage == "note"):
            section = await _push_note(ctx, rule=rule, binding=binding, overlay=overlay, sources=sources, paper=paper)
            if section:
                sections.append(section)
    result.workpapers.append({
        "wp_id": str(paper.id), "wp_code": wp_code, "paper_code": paper_code,
        "status": "pushed", "changed_items": changed, "note_sections": sections,
    })


async def _write_entries(
    ctx: _Ctx, wp_id: UUID, paper_code: str, changed: list[str],
    overlay: Mapping[str, Any], snapshot: Mapping[str, tuple[Any, str]],
    storage_field: str = "remark",
) -> str | None:
    """逐条目 CAS 写回；返回冲突条目 id（None = 全部成功）。``paper_code`` 用于地址首段。"""
    if not changed:
        return None
    adapter = WorkpaperMutationAdapter(ctx.db)
    savepoint = await ctx.db.begin_nested()
    try:
        for item_id in changed:
            before, version = snapshot.get(item_id, (None, _version_from_timestamp(None)))
            target = CanonicalFormulaTarget(
                domain="workpaper", project_id=ctx.project_id, year=ctx.year,
                addr_id=f"{paper_code}/*/{item_id}",
                locator={
                    "wp_id": str(wp_id), "item": item_id, "cell": RAW_CELL,
                    "storage_field": storage_field,
                },
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
    """附注主表推送；返回有写入的章节号。"""
    from app.models.report_models import DisclosureNote

    table_name = rule.target.resolve_table(sources.template_type) or rule.target.table
    # section_title 校验用的名称：table_by_template 场景下子表名可能不等于章节标题
    # （如国企 八、4 章节标题"应收票据"、子表名"应收票据分类"），此时用 rule.target.table（章节级）比较
    _title_check_name = rule.target.table if rule.target.table_by_template else table_name
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
    elif (note.section_title or "").strip() != _title_check_name:
        # ── 章节号不匹配：尝试按 section_title 反查（spec: formula-push-note-skip-reduction · 需求 3.1） ──
        _section_prefix = section.split("、")[0] + "、" if "、" in section else section[:1]
        fallback_rows = (await ctx.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == ctx.project_id,
                DisclosureNote.year == ctx.year,
                DisclosureNote.section_title == _title_check_name,
                DisclosureNote.is_deleted == sa.false(),
                DisclosureNote.note_section.like(f"{_section_prefix}%"),
            ).with_for_update()
        )).scalars().all()
        if len(fallback_rows) == 1:
            logger.info(
                "formula_push: 章节号动态定位 %s → %s（规则声明 %s）",
                _title_check_name, fallback_rows[0].note_section, section,
            )
            note = fallback_rows[0]
            section = fallback_rows[0].note_section
            section_addr = f"note://{section}/{table_name}"
        else:
            reason = f"附注 {section} 是「{note.section_title}」章节，不是「{table_name}」，未推送"
    elif str(_enum_value(note.status)) in FROZEN_NOTE_STATUSES:
        reason = "附注章节已确认，公式推送不改写"
    table_data = copy.deepcopy(note.table_data) if note is not None else None
    table = None
    if reason is None:
        table, reason = note_writer.locate_table(table_data, table_name)

    # ── 缺表时尝试建骨架（需求 5.1）──────────────────────────────────
    skeleton_built = False
    if table is None and reason and "没有" in reason and table_data is not None:
        # _source 为 workpaper/workpaper_html 或 None（旧格式未标记）都允许建骨架
        source = table_data.get("_source")
        if source in note_writer.WORKPAPER_SOURCES or source is None:
            # 遮挡数据检查（需求 5.2）：原表格有非空非零数值或人工/锁定单元格 → 跳过
            blocked = note_writer.has_obscured_data(table_data, table_name)
            if blocked:
                ctx.skip(rule.rule_id, "note", "note", section_addr,
                         f"附注 {section} 章节已有自定义数据（{blocked}），建骨架会遮挡原数据，跳过")
                return None
            skeleton = note_writer.build_main_skeleton(template_type, section, table_name,
                                                       fields=rule.target.fields)
            if skeleton is None:
                ctx.skip(rule.rule_id, "note", "note", section_addr,
                         f"附注模板「{template_type}」中没有「{table_name}」表定义，无法建骨架")
                return None
            # 浅合并：保留其余子表、叙述、原有 rows/_tables（需求 5.3）
            sub = table_data.setdefault("sub_table_data", {})
            sub[table_name] = skeleton.rows
            cols = table_data.setdefault("_sub_table_columns", {})
            cols[table_name] = skeleton.columns
            table_data["_source"] = "workpaper"
            # 缺省 _current_standard（引擎按项目模板类型选章节，此时该字段可能未设）
            if "_current_standard" not in table_data:
                table_data["_current_standard"] = template_type
            # 重新定位
            table, reason = note_writer.locate_table(table_data, table_name)
            if table is not None:
                skeleton_built = True
                logger.info(
                    "formula_push: 为附注 %s 建「%s」主表骨架（%d 行），template_type=%s",
                    section, table_name, len(skeleton.rows), template_type,
                )

    if table is None:
        ctx.skip(rule.rule_id, "note", "note", section_addr, reason or "附注表格无法定位")
        return None

    wrote = False
    any_data_row_matched = False
    for row in binding.note_rows(overlay, template_type, rule):
        if row["is_total"] or row["is_memo"]:
            continue  # 合计按附注实际行重算（见 _push_note_total）；「其中：」备注行不由底稿取数
        index = note_writer.find_row(table.rows, [row["note_label"], row["label"]])
        if index is not None:
            any_data_row_matched = True
        for field_name in rule.target.fields:
            value_key, period = note_writer.NOTE_FIELDS[field_name]
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

    # ── 合计行兜底（spec: formula-push-note-skip-reduction · 需求 2.3） ──
    # 所有数据行都未命中附注行 → 把审定数写入合计行
    skip_total_recalc = False
    if not any_data_row_matched:
        total_idx = note_writer.find_total_row(table.rows)
        if total_idx is not None:
            # 单科目：用唯一数据行（is_total=False）的值
            # 多科目：用 is_total 行的汇总值
            all_note_rows = binding.note_rows(overlay, template_type, rule)
            is_single = hasattr(binding, "account_prefixes") and len(binding.account_prefixes) == 1
            if is_single:
                source_row = next((r for r in all_note_rows if not r.get("is_total") and not r.get("is_memo")), None)
            else:
                source_row = next((r for r in all_note_rows if r.get("is_total")), None)
            if source_row is not None:
                total_row = table.rows[total_idx]
                total_label = note_writer.row_label(total_row) or "合计"
                for field_name in rule.target.fields:
                    value_key, period = note_writer.NOTE_FIELDS[field_name]
                    if source_row.get(f"{value_key}_resolved"):
                        addr = note_addr_id(section, table_name, total_label, period)
                        wrote |= _push_note_cell(ctx, rule=rule, section=section, addr=addr, table=table,
                                                 row=total_row, field_name=field_name,
                                                 value=source_row[value_key], paper=paper)
                skip_total_recalc = True  # 已直接写入合计行，跳过后续重算

    if not skip_total_recalc:
        wrote |= _push_note_total(ctx, rule=rule, section=section, table_name=table_name, table=table, paper=paper)

    if not wrote:
        return None
    # spec: formula-push-note-skip-reduction · 需求 1.4
    # 首次推送后标记 _source，下次推送走正常路径不再触发旧格式兜底
    if table_data.get("_source") is None:
        table_data["_source"] = "workpaper"
    # 同步指纹：与 sync-from-workpaper 同写，pull-from-workpapers 据此认定「真正同步过」（需求 5）
    table_data["_last_sync_wp_id"] = str(paper.id)
    table_data["_last_sync_at"] = ctx.now.isoformat()
    note.table_data = table_data
    flag_modified(note, "table_data")
    note.last_sync_source = "formula_push"
    note.last_sync_wp_id = paper.id
    note.last_sync_at = ctx.now
    note.last_sync_user_id = ctx.triggered_by
    note.is_stale = False  # 推送成功 → 清除 stale（与 sync-from-workpaper 同语义）
    note.stale_source = None
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
    """合计 = 合计行之前各行之和（人工行一并计入）。"""
    index = note_writer.find_total_row(table.rows)
    if index is None:
        return False
    total_row = table.rows[index]
    label = note_writer.row_label(total_row) or "合计"
    wrote = False
    for field_name in rule.target.fields:
        _, period = note_writer.NOTE_FIELDS[field_name]
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
    """``(project_id, year, addr_id)`` 唯一的推送状态 upsert。"""
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
    codes: Iterable[str] | None = None,
    dry_run: bool = False,
    force_addr_ids: Iterable[str] = (),
) -> RunResult:
    """执行并提交；dry_run 只回滚不提交。"""
    try:
        result = await run(
            db, project_id=project_id, year=year, trigger=trigger, triggered_by=triggered_by,
            wp_id=wp_id, codes=codes, dry_run=dry_run, force_addr_ids=force_addr_ids,
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
    """失败运行记录（面板可见降级）。"""
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
