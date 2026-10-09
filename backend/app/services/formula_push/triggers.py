"""公式推送事件触发：TRIAL_BALANCE_UPDATED / WORKPAPER_SAVED(E1) → 引擎 run。

spec: chain-closure-phase2-formula-push-engine · design §八 · 任务 11 · 需求 2.1 / 2.2

* ``TRIAL_BALANCE_UPDATED``（四表入库重算、调整分录审批重算、审定表发布门都发它）：
  ``account_codes`` 为空（全量重算）或与已接入底稿的科目前缀相交才跑。
* ``WORKPAPER_SAVED``：``extra.wp_code`` 是已接入底稿才跑，且只跑 ``extra.wp_id`` 那张。
* 防回环：引擎写入只 ``broadcast_raw('formula.pushed')``，**不**发布 ``WORKPAPER_SAVED``。

handler 独立会话、失败不冒泡（事件是上游提交后的副作用，推送失败不能反向打断重算 / 保存）；
失败由 ``run_and_commit`` 记 failed 运行记录，并推 ``sync.failed`` SSE（顶栏同步状态变红，带重试端点）。
"""
from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from typing import Any
from uuid import UUID

import sqlalchemy as sa

logger = logging.getLogger(__name__)

#: 各已接入底稿关心的试算表科目前缀（由 binding 注册表统一派生）
def _watched_prefixes() -> dict[str, tuple[str, ...]]:
    from app.services.formula_push.bindings import watched_prefixes

    return watched_prefixes()


_MAIN_WP_CODE_RE = re.compile(r"^([A-Z]\d+)")


def _main_wp_code(wp_code: Any) -> str | None:
    """将主册或分册编码归一为 binding 主编码。"""
    match = _MAIN_WP_CODE_RE.match(str(wp_code or "").strip())
    return match.group(1) if match else None


def _matching_codes(account_codes: Iterable[str] | None) -> set[str] | None:
    """返回事件科目命中的 binding 主编码；空科目表示兼容旧约定的全量。"""
    watched = _watched_prefixes()
    codes = tuple(str(c).strip() for c in (account_codes or []) if str(c or "").strip())
    if not codes:
        return None
    return {
        wp_code
        for wp_code, prefixes in watched.items()
        if any(account_code.startswith(tuple(prefixes)) for account_code in codes)
    }


def codes_touch(account_codes: Iterable[str] | None, prefixes: Iterable[str]) -> bool:
    """事件科目是否与底稿相关：未给科目 = 全量重算 ⇒ 相关；否则任一科目以某前缀开头。"""
    codes = [str(c).strip() for c in (account_codes or []) if str(c or "").strip()]
    if not codes:
        return True
    wanted = tuple(prefixes)
    return any(code.startswith(wanted) for code in codes)


def _as_uuid(value: Any) -> UUID | None:
    if value is None or value == "":
        return None
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError):
        return None


async def _push(
    project_id: UUID,
    year: int,
    trigger: str,
    *,
    wp_id: UUID | None = None,
    codes: Iterable[str] | None = None,
) -> None:
    from app.core.database import async_session
    from app.services.formula_push.engine import PushActionError, run_and_commit

    try:
        async with async_session() as db:
            result = await run_and_commit(
                db,
                project_id=project_id,
                year=year,
                trigger=trigger,
                wp_id=wp_id,
                codes=codes,
            )
        logger.info(
            "formula_push[%s] project=%s year=%s run=%s written=%s kept=%s skipped=%s",
            trigger, project_id, year, result.run_id, result.written_count, result.kept_count, result.skipped_count,
        )
    except PushActionError as exc:  # 项目已删除等：业务上不可推，不算故障
        logger.info("formula_push[%s] 未推送 project=%s year=%s：%s", trigger, project_id, year, exc)
    except Exception as exc:  # noqa: BLE001 — 事件副作用失败不冒泡；run_and_commit 已记 failed 运行记录
        logger.exception("formula_push[%s] 失败 project=%s year=%s", trigger, project_id, year)
        await _notify_failed(project_id, year, trigger, exc)


async def _notify_failed(project_id: UUID, year: int, trigger: str, exc: BaseException) -> None:
    """推 sync.failed（与自动科目映射失败同一通道）：顶栏同步状态变红，带「立即推送」重试端点。"""
    try:
        from app.models.audit_platform_schemas import EventPayload, EventType
        from app.services.event_bus import event_bus

        await event_bus._notify_sse(EventPayload(
            event_type=EventType.SYNC_FAILED,
            project_id=project_id,
            year=year,
            extra={
                "source_event": trigger,
                "handler": "公式推送",
                "error": f"{type(exc).__name__}: {exc}"[:500],
                "retry_endpoint": f"/api/projects/{project_id}/formula-push/run",
            },
        ))
    except Exception:  # noqa: BLE001
        logger.warning("formula_push: sync.failed 推送失败 project=%s", project_id, exc_info=True)


async def _lookup_wp_code(project_id: UUID, wp_id: UUID) -> str | None:
    """按项目安全反查底稿编码；不信任跨项目或已删除底稿的 id。"""
    from app.core.database import async_session

    try:
        async with async_session() as db:
            row = (await db.execute(
                sa.text(
                    "SELECT wi.wp_code "
                    "FROM working_paper wp "
                    "JOIN wp_index wi ON wi.id = wp.wp_index_id "
                    "WHERE wp.id = :wp_id AND wp.project_id = :project_id "
                    "AND wi.project_id = :project_id "
                    "AND wp.is_deleted = false AND wi.is_deleted = false"
                ),
                {"wp_id": str(wp_id), "project_id": str(project_id)},
            )).first()
            return str(row[0]) if row and row[0] else None
    except Exception:  # noqa: BLE001 — 事件副作用失败不应阻断保存链
        logger.exception("formula_push: WORKPAPER_SAVED 反查底稿编码失败 project=%s wp=%s", project_id, wp_id)
        return None


async def _is_consolidated_project(project_id: UUID, *, _session_factory=None) -> bool:
    """快捷判断：合并项目（report_scope='consolidated'）的 TB 变更由 consol_push 处理，
    formula_push 只服务单体项目，合并项目跳过避免空转。

    ``_session_factory`` 仅供测试注入；生产代码不传。
    """
    from app.models.core import Project

    session_factory = _session_factory
    if session_factory is None:
        from app.core.database import async_session
        session_factory = async_session

    try:
        async with session_factory() as db:
            row = (await db.execute(
                sa.select(Project.report_scope).where(
                    Project.id == project_id,
                    Project.is_deleted == sa.false(),
                )
            )).first()
            return row is not None and (row[0] or "").strip().lower() == "consolidated"
    except Exception:  # noqa: BLE001
        return False  # 查不到 → 不跳过，让引擎正常判断


async def on_trial_balance_updated(payload: Any) -> None:
    project_id, year = _as_uuid(getattr(payload, "project_id", None)), getattr(payload, "year", None)
    if project_id is None or not year:
        logger.warning("formula_push: TRIAL_BALANCE_UPDATED 缺 project_id / year，未推送")
        return
    # 合并项目的 TB 变更由 consol_push 处理，formula_push 跳过
    if await _is_consolidated_project(project_id):
        logger.debug("formula_push: 跳过合并项目 %s 的 TRIAL_BALANCE_UPDATED", project_id)
        return
    account_codes = getattr(payload, "account_codes", None)
    account_codes = tuple(account_codes or ())
    codes = _matching_codes(account_codes)
    if account_codes and any(str(c).strip() for c in account_codes if c is not None) and not codes:
        return
    await _push(project_id, int(year), "TRIAL_BALANCE_UPDATED", codes=codes)


async def on_workpaper_saved(payload: Any) -> None:
    extra = getattr(payload, "extra", None) or {}
    project_id, year = _as_uuid(getattr(payload, "project_id", None)), getattr(payload, "year", None)
    wp_id = _as_uuid(extra.get("wp_id"))
    if project_id is None or not year or wp_id is None:
        logger.warning("formula_push: WORKPAPER_SAVED(%s) 缺 project_id / year / wp_id，未推送", extra.get("wp_code"))
        return
    # 合并项目的底稿保存由 consol_push 处理
    if await _is_consolidated_project(project_id):
        logger.debug("formula_push: 跳过合并项目 %s 的 WORKPAPER_SAVED", project_id)
        return

    raw_code = extra.get("wp_code")
    main_code = _main_wp_code(raw_code)
    if main_code is None:
        raw_code = await _lookup_wp_code(project_id, wp_id)
        main_code = _main_wp_code(raw_code)
    if main_code not in _watched_prefixes():
        return
    await _push(project_id, int(year), "WORKPAPER_SAVED", wp_id=wp_id, codes={main_code})


_REGISTERED: set[int] = set()


def register_formula_push_handlers(event_bus: Any) -> None:
    """注册到 EventBus（main._register_phase_handlers 调用）。subscribe 不去重 ⇒ 同一总线只注册一次。"""
    from app.models.audit_platform_schemas import EventType

    if id(event_bus) in _REGISTERED:
        return
    event_bus.subscribe(EventType.TRIAL_BALANCE_UPDATED, on_trial_balance_updated)
    event_bus.subscribe(EventType.WORKPAPER_SAVED, on_workpaper_saved)
    _REGISTERED.add(id(event_bus))
    logger.info("Registered formula_push handlers for TRIAL_BALANCE_UPDATED / WORKPAPER_SAVED")
