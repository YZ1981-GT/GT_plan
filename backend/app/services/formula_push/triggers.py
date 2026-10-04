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
from collections.abc import Iterable
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

#: 各已接入底稿关心的试算表科目前缀（由 binding 注册表统一派生）
def _watched_prefixes() -> dict[str, tuple[str, ...]]:
    from app.services.formula_push.bindings import watched_prefixes

    return watched_prefixes()


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


async def _push(project_id: UUID, year: int, trigger: str, *, wp_id: UUID | None = None) -> None:
    from app.core.database import async_session
    from app.services.formula_push.engine import PushActionError, run_and_commit

    try:
        async with async_session() as db:
            result = await run_and_commit(db, project_id=project_id, year=year, trigger=trigger, wp_id=wp_id)
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


async def on_trial_balance_updated(payload: Any) -> None:
    project_id, year = _as_uuid(getattr(payload, "project_id", None)), getattr(payload, "year", None)
    if project_id is None or not year:
        logger.warning("formula_push: TRIAL_BALANCE_UPDATED 缺 project_id / year，未推送")
        return
    prefixes = [p for codes in _watched_prefixes().values() for p in codes]
    if not codes_touch(getattr(payload, "account_codes", None), prefixes):
        return
    await _push(project_id, int(year), "TRIAL_BALANCE_UPDATED")


async def on_workpaper_saved(payload: Any) -> None:
    extra = getattr(payload, "extra", None) or {}
    if extra.get("wp_code") not in _watched_prefixes():
        return
    project_id, year = _as_uuid(getattr(payload, "project_id", None)), getattr(payload, "year", None)
    wp_id = _as_uuid(extra.get("wp_id"))
    if project_id is None or not year or wp_id is None:
        logger.warning("formula_push: WORKPAPER_SAVED(%s) 缺 project_id / year / wp_id，未推送", extra.get("wp_code"))
        return
    await _push(project_id, int(year), "WORKPAPER_SAVED", wp_id=wp_id)


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
