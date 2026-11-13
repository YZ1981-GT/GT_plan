"""公式设置域的持久化 outbox 门面（S4 ADR-SDO-01/02/03）。

写入方在同一事务里调 ``record_changes`` 登记变化并就地标过期，路由 ``commit`` 后调
``publish_pending`` 交给后台投递。复用平台已有的 ``DurableEventOutboxService`` 与
``import_event_outbox`` 表，不建第二套事件表。

投递时直接调用 ``propagation.HANDLERS[domain](...)``，不经事件总线（总线会吞异常），
失败可重试、成功只一次。
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_schemas import EventType
from app.services.workpaper_sync.outbox import (
    DurableEventOutboxService,
    PendingPublication,
)

logger = logging.getLogger(__name__)

#: 入队时用的 origin 标记，投递方按此区分旧路径和 outbox 路径
ORIGIN = "formula_settings_outbox"

#: Session.info 上的待发布清单键（与底稿同步域各自独立）
PENDING_SESSION_KEY = "formula_settings.outbox.pending"

#: 回执存于原 outbox payload，必须整体赋回，不能原地修改普通 JSONB。
RECEIPT_KEY = "formula_propagation_receipt_v1"

#: 后台投递的并发信号量（进程内）
_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    """惰性初始化：首次调用时创建。默认并发 4。"""
    global _semaphore
    if _semaphore is None:
        try:
            from app.core.config import settings
            concurrency = getattr(settings, "FORMULA_PROPAGATION_CONCURRENCY", 4) or 4
        except Exception:
            concurrency = 4
        _semaphore = asyncio.Semaphore(int(concurrency))
    return _semaphore


# ── 入队 ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FormulaChangeRecord:
    """一个项目在一个域里的公式变化记录。"""
    project_id: uuid.UUID
    domain: str
    slot_keys: list[str]
    source: str
    publish_id: str | None = None
    row_codes: list[str] | None = None  # report 域用


async def record_changes(
    db: AsyncSession,
    *,
    domain: str,
    events: Iterable[dict[str, Any]],
    source: str,
    publish_id: str | None = None,
) -> list[PendingPublication]:
    """在调用方事务内为每个有变化的项目入队一条耐久事件并就地标过期。

    ``events`` 格式与现有 ``publish_events`` 的参数一致：每个 dict 含
    ``project_id``, ``slot_keys``, 可选 ``domain``。

    只 flush 不 commit。返回待发布句柄列表。
    """
    from app.services.formula_settings.propagation import HANDLERS, mark_in_year

    publications: list[PendingPublication] = []
    events_list = list(events)
    if not events_list:
        return publications

    # 报表域：先失效反向索引（与 publish_events 同行为）
    if domain == "report" or any(ev.get("domain") == "report" for ev in events_list):
        try:
            from app.services.formula_reverse_index import invalidate_reverse_index
            invalidate_reverse_index()
        except Exception as exc:
            logger.warning("[formula_settings.outbox] 反向索引失效失败: %s", exc)

    for ev in events_list:
        slots = [s for s in (ev.get("slot_keys") or []) if s]
        if not slots:
            continue

        d = ev.get("domain") or domain
        project_id_raw = ev.get("project_id")
        if project_id_raw is None:
            continue
        project_id = uuid.UUID(str(project_id_raw))

        if d not in HANDLERS:
            raise ValueError(f"未知公式传播域：{d}")
        # 冻结入队年度；没有年度仍留耐久行，投递失败可见，绝不借用未来的新年度。
        year = await _fetch_project_year(db, project_id)
        marked = await mark_in_year(db, d, project_id, year, slots)

        payload: dict[str, Any] = {
            "origin": ORIGIN,
            "domain": d,
            "slot_keys": slots,
            "source": source,
            "publish_token": publish_id or uuid.uuid4().hex,
            "stale_mark": marked,
        }
        if d == "report":
            payload["row_codes"] = sorted({s.partition(":")[2] for s in slots if ":" in s})

        # 入队（只 flush）
        pub = await DurableEventOutboxService.enqueue(
            db,
            event_type=EventType.FORMULA_CONFIG_CHANGED,
            project_id=project_id,
            year=year,
            payload=payload,
            remember=False,  # 我们用自己的 session key
        )
        publications.append(pub)

        # 挂到自己的 session 清单
        _remember(db, pub)

    return publications


def _remember(db: AsyncSession, pub: PendingPublication) -> None:
    """把句柄挂到 session.info 的公式域清单。"""
    info = getattr(db, "info", None)
    if not isinstance(info, dict):
        return
    bucket = info.setdefault(PENDING_SESSION_KEY, [])
    bucket.append(pub)


def _take_pending(db: AsyncSession) -> list[PendingPublication]:
    """取出并清空 session 上的公式域待发布清单。"""
    info = getattr(db, "info", None)
    if not isinstance(info, dict):
        return []
    bucket = info.pop(PENDING_SESSION_KEY, [])
    return list(bucket) if isinstance(bucket, list) else []


# ── 发布（路由 commit 之后调用）──────────────────────────────────────────────


async def publish_pending(db: AsyncSession) -> dict[str, Any]:
    """路由 commit 之后调用：取本会话登记的行，后台有界并发投递。

    立即返回已登记条数，不等投递完成。每条经 ``ImportEventOutboxService.publish_one``（与 worker 重放同一派发口）
    到 :func:`deliver` 调传播处理器；失败当场记 failed / 次数 / 原因，由 outbox_replay_worker 重放，耗尽进死信。
    """
    pending = _take_pending(db)
    if not pending:
        return {"queued": 0}

    sem = _get_semaphore()
    count = len(pending)

    async def _deliver_one(pub: PendingPublication) -> None:
        async with sem:
            try:
                from app.core.database import async_session
                from app.services.import_event_outbox_service import ImportEventOutboxService

                async with async_session() as session:
                    # 与 outbox_replay_worker 同一派发口（spec formula-management-repair-closure R1.2）：抢消费权 →
                    # deliver → 成功标 published；失败归还消费权并当场记 failed + 尝试次数 + 原因（worker 照常重放）
                    await ImportEventOutboxService.publish_one(session, pub.outbox_id)
                    await session.commit()
            except Exception as exc:  # 连状态都写不进（连库失败等）：行保持 pending，worker 接手
                logger.warning(
                    "[formula_settings.outbox] 投递失败 outbox_id=%s, worker 将重放: %s",
                    pub.outbox_id, exc,
                )

    # 后台并发投递（不阻塞路由响应）
    for pub in pending:
        asyncio.ensure_future(_deliver_one(pub))

    return {"queued": count}


# ── 投递（直接调传播处理器，不经事件总线）──────────────────────────────────


async def deliver(db: AsyncSession, pub: PendingPublication) -> dict[str, Any]:
    """唯一派发口已持有消费权；这里只执行、写回执，不再 claim，不 commit。

    保存点隔离传播和回执的数据库错误，失败回执留在外层事务，随后由唯一派发口
    归还消费权并记录 failed。派发 published 仅表示执行完本次动作，不表示业务完成。
    """
    from app.services.formula_settings.propagation import HANDLERS, PropagationIncomplete, _delivery_event_id
    from app.services.import_event_outbox_service import ImportEventOutboxService

    row = await ImportEventOutboxService.get(db, pub.outbox_id)
    if row is None:
        raise ValueError("公式传播 outbox 行不存在")
    payload = dict(row.payload) if isinstance(row.payload, dict) else {}
    domain = str(payload.get("domain") or "")
    project_id, year = row.project_id, row.year
    result: dict[str, Any] = {}
    token = _delivery_event_id.set(str(pub.outbox_id))
    try:
        try:
            async with db.begin_nested():
                slots = payload.get("slot_keys")
                if not isinstance(slots, list) or not slots or any(not isinstance(s, str) or not s for s in slots):
                    raise ValueError("公式传播载荷缺少完整槽位列表")
                handler = HANDLERS.get(domain)
                if handler is None:
                    raise ValueError(f"未知公式传播域：{domain}")
                if year is None:
                    raise PropagationIncomplete(domain, "公式传播没有冻结审计年度，不能借用项目当前年度")
                result = await handler(project_id, year, slots)
                if not isinstance(result, dict):
                    raise TypeError("公式传播处理器未返回结构化回执")
                row_codes = payload.get("row_codes") or []
                if domain == "report" and row_codes:
                    await _stale_engine_for_formula_change(db, project_id, year, row_codes)
                receipt = _receipt(pub, payload, domain, result)
                row.payload = {**payload, RECEIPT_KEY: receipt}
                await db.flush()
        except Exception as exc:
            # ROLLBACK TO SAVEPOINT 可能使修改过的 ORM 行过期；显式刷新后再写失败回执，
            # 防止外层 abort_fanout 读取 item.id 时触发隐式异步 I/O。
            await db.refresh(row)
            detail = getattr(exc, "detail", None)
            failure_result = result if isinstance(result, dict) and result else detail
            failure_result = failure_result if isinstance(failure_result, dict) else {}
            receipt = _receipt(pub, payload, domain, failure_result, error=str(exc))
            try:
                async with db.begin_nested():
                    row.payload = {**payload, RECEIPT_KEY: receipt}
                    await db.flush()
            except Exception:
                await db.refresh(row)
                raise  # 回执本身写失败也不能吞掉；外层事务仍可记 failed / 归还消费权。
            raise
    finally:
        _delivery_event_id.reset(token)
    return {"delivered": True, "domain": domain, "handler_result": result, "receipt": receipt}


async def _fetch_project_year(db: AsyncSession, project_id: uuid.UUID) -> int | None:
    """取项目审计年度：与 ``event_bus._backfill_year`` 同一解析（``audit_year`` 优先，再期末日 / 期初日 / 向导 / 项目名）。

    🔴 此前只读 ``audit_period_end``：共享库 20 个未删项目里 17 个该列为空（2026-11-03 现查，``audit_year`` 全有）⇒
    投递拿到 None ⇒ 报表只标过期不重算，表间审核 / 合并附注 / 推送规则一律按「无年度」跳过。
    已删除项目返回 None（与旧口径一致）。
    """
    from app.models.core import Project
    from app.services.project_audit_year import resolve_project_audit_year

    project = await db.get(Project, project_id)
    if project is None or project.is_deleted:
        return None
    return resolve_project_audit_year(project)


async def _stale_engine_for_formula_change(
    db: AsyncSession,
    project_id: uuid.UUID,
    year: int | None,
    row_codes: list[str],
) -> None:
    """从 ``event_handlers._stale_engine_on_formula_config_changed`` 抽出的逻辑：
    反向索引失效 + 依赖图按报表行标下游过期（``stale_engine.on_change``，自开会话，不用 ``db``）。

    失败原样上抛 ⇒ 派发口记 failed、worker 重放（守卫 ``test_release_lazy_import_closure``）。
    🔴 2026-11-01 15:15 的合并提交把这里回退成了 ``stale_summary_aggregate.mark_downstream_stale`` —— 全仓不存在的
    函数，延迟导入恒 ImportError 又被 except 吞成告警 ⇒ 依赖图下游过期这一步对每条投递都是空操作；
    这里恢复 release-blocker-closure（bb29a49f6）的实现（spec formula-management-repair-closure R1）。
    """
    try:
        from app.services.formula_reverse_index import invalidate_reverse_index
        invalidate_reverse_index()
    except Exception:
        pass

    if not row_codes or year is None:
        return

    from app.services.formula_settings.propagation import PropagationIncomplete, _matches_project_year
    from app.services.stale_propagation_engine import stale_engine

    # 图内 WP 行没有年度列；项目已经换年度时不能把旧事件作用于当前底稿。
    if not await _matches_project_year(db, project_id, year):
        raise PropagationIncomplete("report", "项目审计年度已变化，未执行项目级依赖图写入")
    for row_code in sorted(set(row_codes)):
        # 执行自身负责拒绝无年度降级，并在实际写事务内重新核验项目年度。
        result = await stale_engine.on_change(f"REPORT:{row_code}::", project_id, year, strict=True)
        if not isinstance(result, dict) or result.get("degraded") or result.get("error"):
            raise PropagationIncomplete("report", "依赖图传播未完成", result if isinstance(result, dict) else {})


def _is_count(value: Any) -> bool:
    return type(value) is int and value >= 0


def action_status(domain: str, result: dict[str, Any]) -> str:
    """只认可结构化证据；坏类型不抛二次异常，也不能被当成业务成功。"""
    if not isinstance(result, dict):
        return "unknown"
    action = "unknown"
    if domain == "report" and isinstance(result.get("recalculated"), dict):
        recalculated = result["recalculated"]
        failed_rows = recalculated.get("failed_rows", [])
        failed_count = recalculated.get("failed_count")
        count = recalculated.get("recalculated_count")
        if isinstance(failed_rows, list) and failed_rows or _is_count(failed_count) and failed_count:
            action = "partial"
        elif isinstance(failed_rows, list) and _is_count(failed_count) and _is_count(count):
            action = "succeeded" if count else "skipped"
    elif domain == "wp" and _is_count(result.get("marked")) and isinstance(result.get("wp_codes"), list):
        action = "marked_stale"
    elif domain == "note" and all(_is_count(result.get(k)) for k in ("materialized", "marked")):
        action = "marked_stale"
    elif domain == "consol_note" and isinstance(result.get("operation_id"), str) and result["operation_id"]:
        status = result.get("status")
        if isinstance(status, str) and status in {"queued", "running", "succeeded", "partial", "failed", "stale", "cancelled"}:
            action = status
    elif domain == "cross_check" and all(_is_count(result.get(k)) for k in ("executed", "passed", "failed", "issues")):
        if result["failed"] or result["issues"]:
            action = "check_failed"
        elif result["executed"] == result["passed"]:
            action = "succeeded" if result["executed"] else "skipped"
    elif domain == "push":
        workpapers, blocked = result.get("workpapers", []), result.get("blocked_writes", [])
        failed = isinstance(workpapers, list) and any(
            isinstance(wp, dict) and wp.get("status") == "failed" for wp in workpapers)
        status = result.get("status")
        if status == "failed":
            action = "failed"
        elif status == "partial" or failed or isinstance(blocked, list) and blocked:
            action = "partial"
        elif (status == "succeeded" and isinstance(result.get("run_id"), str) and result["run_id"]
              and isinstance(workpapers, list) and all(isinstance(wp, dict) for wp in workpapers)
              and isinstance(blocked, list)):
            action = "succeeded"
    # 明确失败证据优先于混入的 skipped；数字 skipped 是计数，不是跳过动作。
    if action in {"failed", "partial", "check_failed"}:
        return action
    skipped = result.get("skipped")
    if skipped is True or isinstance(skipped, str) and skipped:
        return "no_consumer" if skipped == "no_consumer" else "skipped"
    return action


def _receipt(pub: PendingPublication, payload: dict[str, Any], domain: str, result: dict[str, Any],
             *, error: str | None = None) -> dict[str, Any]:
    operation_id = result.get("operation_id") if domain == "consol_note" else None
    return jsonable_encoder({
        "schema_version": 1, "outbox_id": str(pub.outbox_id), "domain": domain,
        "year": pub.year, "publish_token": payload.get("publish_token"),
        "delivery_status": "failed" if error is not None else "published",
        "action_status": "failed" if error is not None else action_status(domain, result),
        "handler_result": result, "operation_id": operation_id,
        "operation_status": result.get("status") if operation_id else None,
        "last_error": error, "recorded_at": datetime.now(timezone.utc).isoformat(),
    })
