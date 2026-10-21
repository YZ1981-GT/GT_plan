"""变更传播（R8，design §8）：有效定义变化 → 事务提交后每项目一次 ``FORMULA_CONFIG_CHANGED`` → 新 handler 失效 / 重算。

* 报表：变化行 ∪ 经 ROW / SUM_ROW 直接或间接引用它们的行 → ``financial_report.is_stale``（该项目全部年度）；
  有审计年度且未归档时 ``recalculate_stale_rows``，随后发 ``REPORTS_UPDATED``。
* 底稿：用到该底稿编码的底稿标 ``prefill_stale``。
* 附注：对应章节 ``is_stale``。
* 合并附注：对应章节重新填数（``fill_note_sections``）。
* 试算表明细 / 表间审核：事件本身即通知前端刷新（SSE），下次执行即用新定义。

事件 ``extra.row_code`` 置空，旧 handler 只做反向索引失效（不再按单行 BFS）。handler 失败只记降级日志，
不影响已提交的定义（R8.4）。
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Awaitable, Callable, Iterable

import sqlalchemy as sa

from app.services.formula_grammar import ROW_PATTERN, SUM_ROW_PATTERN

logger = logging.getLogger(__name__)
ORIGIN = "formula_settings"
_session_factory: Callable[[], Any] | None = None


def set_session_factory(factory: Callable[[], Any] | None) -> None:
    """测试注入；生产用 ``app.core.database.async_session``。"""
    global _session_factory
    _session_factory = factory


def _factory():
    if _session_factory is not None:
        return _session_factory
    from app.core.database import async_session

    return async_session


async def publish_events(events: Iterable[dict[str, Any]], *, domain: str, source: str,
                         token: str | None = None) -> int:
    """路由 commit 之后调用：每个有效定义变化的项目发一次事件。返回发出的事件数。"""
    from app.models.audit_platform_schemas import EventPayload, EventType
    from app.services.event_bus import event_bus

    events = list(events)
    if domain == "report" or any(ev.get("domain") == "report" for ev in events):
        # 反向索引（「谁引用了该单元格」）按 report_config 全表构建：任何报表公式写入都要失效，
        # 不论是否有项目的有效定义变化（例如全部冲突、只改了全局行）。模板事件按每条事件的域判断。
        try:
            from app.services.formula_reverse_index import invalidate_reverse_index

            invalidate_reverse_index()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[formula_settings] 反向索引失效失败: %s", exc)
    sent = 0
    for ev in events:
        slots = [s for s in (ev.get("slot_keys") or []) if s]
        if not slots:
            continue
        d = ev.get("domain") or domain
        extra: dict[str, Any] = {"origin": ORIGIN, "domain": d, "slot_keys": slots, "source": source,
                                 "row_code": "", "publish_token": token or uuid.uuid4().hex}
        if d == "report":
            extra["row_codes"] = sorted({s.partition(":")[2] for s in slots})
        try:
            await event_bus.publish(EventPayload(event_type=EventType.FORMULA_CONFIG_CHANGED,
                                                 project_id=uuid.UUID(str(ev["project_id"])), extra=extra))
            sent += 1
        except Exception as exc:  # noqa: BLE001 —— 事件失败不影响已提交的定义
            logger.warning("[formula_settings] 变更事件发布失败 project=%s: %s", ev.get("project_id"), exc)
    return sent


def report_closure(configs: Iterable[Any], changed: set[str]) -> set[str]:
    """变化行 ∪ 经 ROW / SUM_ROW（按行次区间）直接或间接引用它们的行。"""
    refs = []
    for c in configs:
        rows: set[str] = set()
        ranges: list[tuple[str, str]] = []
        for text in (c.formula, c.aje_formula, c.rje_formula):
            if text:
                rows.update(ROW_PATTERN.findall(text))
                ranges.extend(SUM_ROW_PATTERN.findall(text))
        refs.append((c.row_code, rows, ranges))
    closure = set(changed)
    grew = True
    while grew:
        grew = False
        for code, rows, ranges in refs:
            if code in closure:
                continue
            if rows & closure or any(a <= x <= b for a, b in ranges for x in closure):
                closure.add(code)
                grew = True
    return closure


async def _is_frozen(db, project_id: uuid.UUID) -> bool | None:
    from app.models.base import ProjectStatus
    from app.models.core import Project

    status = (await db.execute(sa.select(Project.status).where(
        Project.id == project_id, Project.is_deleted == sa.false()))).scalar_one_or_none()
    if status is None:
        return None
    return status == ProjectStatus.archived


async def propagate_report(project_id: uuid.UUID, year: int | None, slot_keys: list[str]) -> dict[str, Any]:
    from app.models.report_models import FinancialReport
    from app.services.formula_settings.effective_report import load_effective_report_configs
    from app.services.report_config_service import ReportConfigService
    from app.services.report_engine import ReportEngine

    changed = {s.partition(":")[2] for s in slot_keys if ":" in s}
    async with _factory()() as db:
        frozen = await _is_frozen(db, project_id)
        if frozen is None or frozen:
            return {"skipped": "frozen" if frozen else "missing"}
        standard = await ReportConfigService.resolve_applicable_standard(db, project_id)
        configs = await load_effective_report_configs(db, standard=standard, project_id=project_id)
        closure = report_closure(configs, changed)
        marked = (await db.execute(sa.update(FinancialReport).where(
            FinancialReport.project_id == project_id,
            FinancialReport.row_code.in_(sorted(closure)),
            FinancialReport.is_deleted == sa.false(),
        ).values(is_stale=True).execution_options(synchronize_session=False))).rowcount or 0
        # 过期标记先单独落库：重算整体失败（抛异常）时不随重算一起回滚，保留可见的过期（R8.2）
        await db.commit()
        recalculated: dict[str, Any] | None = None
        if year is not None and marked:
            try:
                recalculated = await ReportEngine(db).recalculate_stale_rows(project_id, year,
                                                                              applicable_standard=standard)
                await db.commit()
            except Exception as exc:  # noqa: BLE001 —— 定义已提交（R8.4），过期标记已落库，记可见降级
                await db.rollback()
                logger.exception("[formula_settings] 报表重算失败 project=%s year=%s", project_id, year)
                _degraded("report_recalc", project_id, str(exc), {"year": year, "rows": sorted(closure)[:50]})
                return {"closure": sorted(closure), "marked": int(marked), "recalculated": None,
                        "error": str(exc)[:500]}
    if recalculated and recalculated.get("failed_rows"):
        # 单行失败：这些行保留原金额与过期标记（recalculate_stale_rows 只清成功行），另记降级日志可查
        _degraded("report_recalc_rows", project_id, f"{recalculated.get('failed_count')} 行重算失败",
                  {"year": year, "failed_rows": recalculated["failed_rows"][:50]})
    if year is not None and marked:
        from app.models.audit_platform_schemas import EventPayload, EventType
        from app.services.event_bus import event_bus

        await event_bus.publish(EventPayload(event_type=EventType.REPORTS_UPDATED, project_id=project_id,
                                             year=year, extra={"source": ORIGIN, "row_codes": sorted(closure)}))
    return {"closure": sorted(closure), "marked": int(marked), "recalculated": recalculated}


async def propagate_wp(project_id: uuid.UUID, year: int | None, slot_keys: list[str]) -> dict[str, Any]:
    from app.models.workpaper_models import WorkingPaper, WpIndex

    codes = sorted({s.split("|", 1)[0] for s in slot_keys if s})
    async with _factory()() as db:
        if await _is_frozen(db, project_id) is not False:
            return {"skipped": True}
        idx = sa.select(WpIndex.id).where(WpIndex.project_id == project_id, WpIndex.wp_code.in_(codes))
        n = (await db.execute(sa.update(WorkingPaper).where(
            WorkingPaper.project_id == project_id, WorkingPaper.wp_index_id.in_(idx),
        ).values(prefill_stale=True).execution_options(synchronize_session=False))).rowcount or 0
        await db.commit()
    return {"wp_codes": codes, "marked": int(n)}


async def propagate_note(project_id: uuid.UUID, year: int | None, slot_keys: list[str]) -> dict[str, Any]:
    """先把有效集合物化进各年度附注（执行器读 ``_user_formulas``），再标章节过期。"""
    from app.models.report_models import DisclosureNote
    from app.services.formula_settings.note_settings import materialize

    sections = sorted({s.split("|", 1)[0] for s in slot_keys if s})
    async with _factory()() as db:
        if await _is_frozen(db, project_id) is not False:
            return {"skipped": True}
        materialized = await materialize(db, project_id, sections)
        n = (await db.execute(sa.update(DisclosureNote).where(
            DisclosureNote.project_id == project_id, DisclosureNote.note_section.in_(sections),
            DisclosureNote.is_deleted == sa.false(),
        ).values(is_stale=True).execution_options(synchronize_session=False))).rowcount or 0
        await db.commit()
    return {"sections": sections, "materialized": materialized, "marked": int(n)}


async def propagate_consol_note(project_id: uuid.UUID, year: int | None, slot_keys: list[str]) -> dict[str, Any]:
    from app.services.consol_note_formula_service import fill_note_sections

    sections = sorted({s.split("|", 1)[0] for s in slot_keys if s})
    if year is None:
        return {"skipped": "no_year", "sections": sections}
    async with _factory()() as db:
        if await _is_frozen(db, project_id) is not False:
            return {"skipped": True}
        result = await fill_note_sections(db, project_id, year, sections)
        await db.commit()
    return {"sections": sections, "result": result}


async def propagate_cross_check(project_id: uuid.UUID, year: int | None, slot_keys: list[str]) -> dict[str, Any]:
    """表间审核规则变更 → 重新执行全部勾稽（内置 7 条 + 用户规则）并落库结果。

    ``execute_report_cross_checks`` 内部已集成 ``run_user_rules``（R10.2），
    结果 upsert 进 ``cross_check_results`` 表（fail-open）。此处只需按传播约定
    提供独立会话与冻结检查。无审计年度则跳过（勾稽需要报表行做 row_cache）。
    """
    if year is None:
        return {"skipped": "no_year", "slot_keys": slot_keys}
    async with _factory()() as db:
        frozen = await _is_frozen(db, project_id)
        if frozen is None or frozen:
            return {"skipped": "frozen" if frozen else "missing"}
        try:
            from app.services.formula_management.logic_check import execute_report_cross_checks

            async with db.begin_nested():
                result = await execute_report_cross_checks(
                    db, project_id=project_id, year=year, persist=True,
                )
            await db.commit()
            return {
                "slot_keys": slot_keys,
                "executed": len(result.outcomes),
                "passed": sum(1 for o in result.outcomes if o.passed),
                "failed": sum(1 for o in result.outcomes if not o.passed),
                "issues": len(result.issues),
            }
        except Exception as exc:  # noqa: BLE001 —— R8.4：不回滚已提交定义
            await db.rollback()
            logger.warning("[formula_settings] 表间审核重算失败 project=%s year=%s: %s",
                           project_id, year, exc)
            _degraded("cross_check_rerun", project_id, str(exc),
                      {"year": year, "slot_keys": slot_keys[:50]})
            return {"slot_keys": slot_keys, "error": str(exc)[:500]}


async def propagate_tb_detail(project_id: uuid.UUID, year: int | None, slot_keys: list[str]) -> dict[str, Any]:
    """试算表科目明细公式变更 → 标全项目底稿 prefill_stale。

    科目明细公式影响所有依赖 TB 取数的底稿（任何使用 ``TB('科目','字段')`` 的底稿），
    无法按 wp_code 精准缩小范围，故标全部底稿。底稿下次打开时检测 ``prefill_stale``
    并重新预填。
    """
    from app.models.workpaper_models import WorkingPaper

    async with _factory()() as db:
        frozen = await _is_frozen(db, project_id)
        if frozen is None or frozen:
            return {"skipped": "frozen" if frozen else "missing"}
        n = (await db.execute(sa.update(WorkingPaper).where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
        ).values(prefill_stale=True).execution_options(synchronize_session=False))).rowcount or 0
        await db.commit()
    return {"slot_keys": slot_keys, "marked": int(n)}


async def _notify_only(project_id: uuid.UUID, year: int | None, slot_keys: list[str]) -> dict[str, Any]:
    return {"notified": len(slot_keys)}


HANDLERS: dict[str, Callable[[uuid.UUID, int | None, list[str]], Awaitable[dict[str, Any]]]] = {
    "report": propagate_report,
    "wp": propagate_wp,
    "note": propagate_note,
    "consol_note": propagate_consol_note,
    "tb_detail": propagate_tb_detail,
    "cross_check": propagate_cross_check,
}


async def on_formula_config_changed(payload: Any) -> None:
    extra = getattr(payload, "extra", None) or {}
    if extra.get("origin") != ORIGIN:
        return  # 旧发布方的事件由旧 handler 处理
    domain, project_id = extra.get("domain"), getattr(payload, "project_id", None)
    slots = list(extra.get("slot_keys") or [])
    handler = HANDLERS.get(domain or "")
    if handler is None or project_id is None or not slots:
        return
    try:
        await handler(project_id, getattr(payload, "year", None), slots)
    except Exception as exc:  # noqa: BLE001 —— R8.4：不回滚已提交定义，记可见降级
        logger.exception("[formula_settings] 传播失败 domain=%s project=%s", domain, project_id)
        _degraded(domain or "", project_id, str(exc), {"slot_keys": slots[:50], "year": getattr(payload, "year", None)})


def _degraded(kind: str, project_id: Any, error: str, context: dict[str, Any]) -> None:
    """记一条可查的降级日志（``stale_degraded_logger``）；日志本身失败不再外抛。"""
    try:
        from app.services.stale_degraded_logger import log_stale_degraded

        log_stale_degraded(source=f"formula_settings:{kind}", target=f"project={project_id}", error=error,
                           context=context)
    except Exception:  # noqa: BLE001
        logger.warning("[formula_settings] 降级日志写入失败 kind=%s project=%s", kind, project_id)


_REGISTERED: set[int] = set()


def register_formula_settings_handlers(event_bus: Any) -> None:
    """startup_registry 的 register_phase_handlers 启动任务调用；同一总线只注册一次。"""
    from app.models.audit_platform_schemas import EventType

    if id(event_bus) in _REGISTERED:
        return
    event_bus.subscribe(EventType.FORMULA_CONFIG_CHANGED, on_formula_config_changed)
    _REGISTERED.add(id(event_bus))
    logger.info("Registered formula_settings propagation handler for FORMULA_CONFIG_CHANGED")
    # 同一启动步骤：自定义公式预设（数据库）进程内缓存 —— 启动即加载、之后定期对齐（R14.3）
    try:
        from app.services.formula_settings.custom_presets import start_refresher

        start_refresher()
    except Exception as exc:  # noqa: BLE001 —— 缓存起不来不影响启动，预设库按旧文件 + 基线
        logger.warning("自定义公式预设缓存未启动：%s", exc)
