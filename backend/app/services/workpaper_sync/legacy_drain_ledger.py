# -*- coding: utf-8 -*-
"""旧式 doc key / callback 的 drain ledger（spec onlyoffice-sheet-open 任务 4.2）。

本模块是 V274 表的**唯一**读写入口。写入侧若散落在 router / gate / callback 三处，
三处对「什么算一次签发」的口径必然漂移，而漂移后的计数无法用于 4.4 的删除判据。

职责边界（刻意不做的事）：

* **不判**「这次能不能签」—— 那是 _wp_onlyoffice_legacy_url_gate 的职责。本模块
  只在已经决定签发之后记账，避免让纯判定函数产生写副作用（gate 被大量单测直接
  调用，写库会把纯函数变成有状态操作）。
* **不改** 已有行。append-only 是这张表的核心语义：签发行永不更新，结算写新行。
* **不存** doc_key 明文（见模型 docstring）。
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_legacy_drain_ledger import WorkpaperLegacyDrainLedger

logger = logging.getLogger(__name__)

#: 签发行的 event_kind。
EVENT_ISSUED = "issued"
#: 结算行的 event_kind。
EVENT_SETTLED = "settled"

#: 终结状态封闭集（与 V274 的 ck_wpldl_terminal_state 逐值一致）。
TERMINAL_SAVED = "saved"
TERMINAL_REJECTED = "rejected"
TERMINAL_EXPIRED = "expired"
TERMINAL_SUPERSEDED = "superseded"
TERMINAL_ABANDONED = "abandoned"
TERMINAL_STATES = frozenset({
    TERMINAL_SAVED, TERMINAL_REJECTED, TERMINAL_EXPIRED,
    TERMINAL_SUPERSEDED, TERMINAL_ABANDONED,
})

#: 旧式会话的默认 TTL。与 OO 侧 sessionidle 同量级（用户回来还能存），
#: 但刻意不复用 OO 的值：OO 的 idle 是客户端行为，本 TTL 是平台自己的结算边界。
DEFAULT_TTL = timedelta(hours=4)

class DrainNotCompleteError(RuntimeError):
    """4.4 删除门未通过：仍有在途签发 / 超时未结算 / 观测窗口不足。

    单独一个类型而不是 ValueError：调用方要能把它与「参数写错」区分开 ——
    前者是「时机未到，过一段时间再来」，后者是「你调错了」。
    """



def doc_key_digest(doc_key: str) -> str:
    """doc_key 到 sha256 hex。表里只存这个，不存明文。"""
    return hashlib.sha256(str(doc_key or "").encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _settled_subq():
    """已结算的签发 id 子查询（open 类判据共用，避免三处各写一遍）。"""
    return select(WorkpaperLegacyDrainLedger.issuance_id).where(
        WorkpaperLegacyDrainLedger.event_kind == EVENT_SETTLED,
        WorkpaperLegacyDrainLedger.issuance_id.is_not(None),
    )


async def record_issuance(
    db: AsyncSession,
    *,
    entry_id: str,
    wp_id: uuid.UUID,
    project_id: uuid.UUID,
    binding_id: str | None = None,
    binding_status: str | None = None,
    source_wp_code: str | None = None,
    sheet_name: str | None = None,
    whole_workbook: bool = False,
    doc_key: str | None = None,
    generation: int | None = None,
    ttl: timedelta | None = None,
    issued_at: datetime | None = None,
) -> WorkpaperLegacyDrainLedger:
    """记一次旧式签发。只 flush，不 commit（跨 service 编排由调用方统一提交）。

    Args:
        doc_key: 旧式 doc key。只有哈希落库；传 None 表示本次签发没有 doc key
            （例如只签了 callback URL），此时 doc_key_sha256 为 NULL。
        ttl: 结算边界。缺省 DEFAULT_TTL。传 timedelta(0) 或负值会被拒 ——
            「签发即过期」没有观测意义，且会让 drain timeout 计数恒为非零。

    Returns:
        新建的 issued 行（已 flush，id 可用）。
    """
    effective_ttl = DEFAULT_TTL if ttl is None else ttl
    if effective_ttl <= timedelta(0):
        raise ValueError(
            "drain ledger 的 TTL 必须为正，实得 " + repr(effective_ttl) + " —— "
            "签发即过期会让 drain timeout 计数恒为非零，失去观测意义"
        )
    issued = issued_at or _now()
    row = WorkpaperLegacyDrainLedger(
        event_kind=EVENT_ISSUED,
        issuance_id=None,
        binding_id=binding_id,
        binding_status=binding_status,
        entry_id=str(entry_id),
        source_wp_code=source_wp_code,
        sheet_name=sheet_name,
        whole_workbook=bool(whole_workbook),
        wp_id=wp_id,
        project_id=project_id,
        doc_key_sha256=doc_key_digest(doc_key) if doc_key else None,
        generation=generation,
        issued_at=issued,
        expires_at=issued + effective_ttl,
        terminal_state=None,
        terminal_reason=None,
        settled_at=None,
        callback_in_flight=None,
    )
    db.add(row)
    await db.flush()
    logger.info(
        "legacy drain ledger: 记签发 entry=%s wp_id=%s binding=%s ttl=%s",
        entry_id, wp_id, binding_id, effective_ttl,
    )
    return row


async def settle_issuance(
    db: AsyncSession,
    *,
    issuance_id: uuid.UUID,
    terminal_state: str,
    reason: str,
    callback_in_flight: bool | None = None,
    settled_at: datetime | None = None,
) -> WorkpaperLegacyDrainLedger:
    """结算一次签发（写新行，不改原行）。

    Raises:
        ValueError: terminal_state 不在封闭集 / reason 为空白 / 该签发已被结算过。

    一行只能结算一次由 V274 的 ux_wpldl_one_settlement_per_issuance 唯一索引在 DB 层
    强制。这里先查一次是为了给出中文原因（否则调用方只能拿到 IntegrityError）。
    """
    state = str(terminal_state or "").strip()
    if state not in TERMINAL_STATES:
        raise ValueError(
            "未知的终结状态 " + repr(terminal_state) + "；封闭集 = " + str(sorted(TERMINAL_STATES))
        )
    text = str(reason or "").strip()
    if not text:
        raise ValueError(
            "结算必须写原因 —— 「结算了但没写理由」在审计上无法与「没结算」区分"
        )

    existing = await db.scalar(
        select(WorkpaperLegacyDrainLedger.id).where(
            WorkpaperLegacyDrainLedger.event_kind == EVENT_SETTLED,
            WorkpaperLegacyDrainLedger.issuance_id == issuance_id,
        )
    )
    if existing is not None:
        raise ValueError("签发 " + str(issuance_id) + " 已被结算过（结算行 " + str(existing) + "）")

    origin = await db.get(WorkpaperLegacyDrainLedger, issuance_id)
    if origin is None or origin.event_kind != EVENT_ISSUED:
        raise ValueError(str(issuance_id) + " 不是一条有效的签发行")

    row = WorkpaperLegacyDrainLedger(
        event_kind=EVENT_SETTLED,
        issuance_id=issuance_id,
        binding_id=origin.binding_id,
        binding_status=origin.binding_status,
        entry_id=origin.entry_id,
        source_wp_code=origin.source_wp_code,
        sheet_name=origin.sheet_name,
        whole_workbook=origin.whole_workbook,
        wp_id=origin.wp_id,
        project_id=origin.project_id,
        doc_key_sha256=origin.doc_key_sha256,
        generation=origin.generation,
        issued_at=origin.issued_at,
        expires_at=origin.expires_at,
        terminal_state=state,
        terminal_reason=text,
        settled_at=settled_at or _now(),
        callback_in_flight=callback_in_flight,
    )
    db.add(row)
    await db.flush()
    logger.info(
        "legacy drain ledger: 结算 issuance=%s state=%s entry=%s",
        issuance_id, state, origin.entry_id,
    )
    return row


async def open_issuances(
    db: AsyncSession, *, entry_id: str | None = None
) -> list[WorkpaperLegacyDrainLedger]:
    """尚未结算的签发行（drain 的「还能存」集合）。

    给 4.3 的 callback 接受判据用：draining 下只接受已签发且未结算的 callback，
    而不是只看 binding 状态就放行。
    """
    stmt = select(WorkpaperLegacyDrainLedger).where(
        WorkpaperLegacyDrainLedger.event_kind == EVENT_ISSUED,
        WorkpaperLegacyDrainLedger.id.not_in(_settled_subq()),
    )
    if entry_id is not None:
        stmt = stmt.where(WorkpaperLegacyDrainLedger.entry_id == str(entry_id))
    return list((await db.scalars(stmt)).all())


async def find_open_by_doc_key(
    db: AsyncSession, *, doc_key: str
) -> WorkpaperLegacyDrainLedger | None:
    """按 doc_key 查未结算的签发行（4.3 的 callback 归属校验）。"""
    return await db.scalar(
        select(WorkpaperLegacyDrainLedger)
        .where(
            WorkpaperLegacyDrainLedger.event_kind == EVENT_ISSUED,
            WorkpaperLegacyDrainLedger.doc_key_sha256 == doc_key_digest(doc_key),
            WorkpaperLegacyDrainLedger.id.not_in(_settled_subq()),
        )
        .order_by(WorkpaperLegacyDrainLedger.issued_at.desc())
        .limit(1)
    )


async def drain_metrics(
    db: AsyncSession, *, project_id: uuid.UUID | None = None
) -> dict[str, Any]:
    """任务 4.4 删除判据要的三个计数（现算，不缓存）。

    Returns:
        {"open_issuances": n, "expired_unsettled": n, "callback_in_flight": n}

        * open_issuances —— 旧签发数（尚未结算）。
        * expired_unsettled —— 已过 TTL 但仍未结算（drain timeout 未收口）。
        * callback_in_flight —— 结算时标记仍在途的条数。

    三个数同时为 0 才允许 4.4 逐 binding 删旧分支。单独看 open_issuances=0 会被
    「刚签发还没到 TTL」蒙混，单独看 expired_unsettled=0 会被「还没到期」蒙混。
    """
    now = _now()
    settled = _settled_subq()
    M = WorkpaperLegacyDrainLedger

    q_open = select(sa.func.count()).select_from(M).where(
        M.event_kind == EVENT_ISSUED,
        M.id.not_in(settled),
    )
    q_expired = select(sa.func.count()).select_from(M).where(
        M.event_kind == EVENT_ISSUED,
        M.id.not_in(settled),
        M.expires_at.is_not(None),
        M.expires_at <= now,
    )
    q_inflight = select(sa.func.count()).select_from(M).where(
        M.event_kind == EVENT_SETTLED,
        M.callback_in_flight.is_(True),
    )

    if project_id is not None:
        q_open = q_open.where(M.project_id == project_id)
        q_expired = q_expired.where(M.project_id == project_id)
        q_inflight = q_inflight.where(M.project_id == project_id)

    return {
        "open_issuances": int(await db.scalar(q_open) or 0),
        "expired_unsettled": int(await db.scalar(q_expired) or 0),
        "callback_in_flight": int(await db.scalar(q_inflight) or 0),
    }


#: 4.4 删除旧 direct-write 分支前的三个前置计数（必须同时为 0）。
DRAIN_DELETE_GATE_KEYS = ("open_issuances", "expired_unsettled", "callback_in_flight")


async def assert_drain_complete_for_delete(
    db: AsyncSession, *, entry_id: str, require_observed_seconds: int = 0
) -> dict[str, Any]:
    """4.4 删除前的唯一门：三个计数必须同时为 0，否则拒绝删除。

    Raises:
        DrainNotCompleteError: 任一计数非 0，或观测窗口不足。

    为什么必须三个一起看：

    * 只看 open_issuances == 0：会被「刚签发、还没到 TTL」蒙混。
    * 只看 expired_unsettled == 0：会被「还没到期」蒙混。
    * 只看 callback_in_flight == 0：它是结算时快照，签发中根本没这个字段。

    三者同时为 0 才意味着既没有在途签发，也没有超时未结算。

    为什么还要 require_observed_seconds：

    三个计数为 0 有两种可能 —— 真的 drain 完了，或从来没有过流量。后者在新建
    binding 上必然成立（空分母恒真）。要求「至少有一条已结算记录且最晚一条距今
    超过 N 秒」把「从未有过流量」排除掉。默认 0 只做计数检查供单测使用；
    真实删除调用方必须传正数（建议 >= 一个完整 TTL）。
    """
    metrics = await drain_metrics(db)
    nonzero = {k: metrics[k] for k in DRAIN_DELETE_GATE_KEYS if metrics.get(k)}
    if nonzero:
        raise DrainNotCompleteError(
            "drain 未完成，拒绝删除 entry=" + str(entry_id) + "：" + str(nonzero)
        )

    if require_observed_seconds > 0:
        settled = await db.scalar(
            select(sa.func.max(WorkpaperLegacyDrainLedger.settled_at)).where(
                WorkpaperLegacyDrainLedger.event_kind == EVENT_SETTLED,
                WorkpaperLegacyDrainLedger.entry_id == str(entry_id),
            )
        )
        if settled is None:
            raise DrainNotCompleteError(
                "entry=" + str(entry_id) + " 从未有过已结算的旧式签发 —— "
                "三个计数为 0 只是没有流量，不是 drain 完成（空分母恒真）"
            )
        # SQLite 的 TIMESTAMP 不保留 tzinfo（读回是 naive）；PG 上是 aware。
        # 统一按 UTC 比，否则两种后端一个崩一个过 —— 这个缺陷只有跑起来才暴露。
        if settled.tzinfo is None:
            settled = settled.replace(tzinfo=timezone.utc)
        age = (_now() - settled).total_seconds()
        if age < require_observed_seconds:
            raise DrainNotCompleteError(
                "entry=" + str(entry_id) + " 最晚一条结算距今仅 " + str(int(age)) +
                " 秒，不足观测窗口 " + str(require_observed_seconds) + " 秒"
            )
    return metrics


async def record_issuance_quietly(
    db: AsyncSession,
    *,
    entry_id: str,
    wp_id: uuid.UUID,
    project_id: uuid.UUID,
    binding_id: str | None = None,
    binding_status: str | None = None,
    source_wp_code: str | None = None,
    sheet_name: str | None = None,
    whole_workbook: bool = False,
    doc_key: str | None = None,
) -> WorkpaperLegacyDrainLedger | None:
    """记签发，但永不抛 —— 供旧式签发端点使用。

    为什么需要这个包装（而不是让调用方 try/except）：

    1. 端点的首要职责是让用户打开编辑器。ledger 坏了就记日志加继续，而不是让
       在线编辑整体不可用（对应本 spec 一贯的「不拒：会让全平台挂；不静默：
       要能抓」中间档）。
    2. 调用方需要的那段 try/except 有 20 余行（含 PG 事务 aborted 的回滚），
       内联进 router 会让该文件越过行数门。抽到这里后 router 只剩一次调用，
       而「记账失败怎么办」的决策只有一份。
    """
    try:
        row = await record_issuance(
            db,
            entry_id=entry_id,
            wp_id=wp_id,
            project_id=project_id,
            binding_id=binding_id,
            binding_status=binding_status,
            source_wp_code=source_wp_code,
            sheet_name=sheet_name,
            whole_workbook=whole_workbook,
            doc_key=doc_key,
        )
        await db.commit()
        return row
    except Exception as exc:
        logger.warning(
            "legacy drain ledger: 记签发失败（不影响本次签发）wp_id=%s entry=%s: %s",
            wp_id, entry_id, exc,
        )
        try:
            await db.rollback()
        except Exception:
            pass
        return None


async def _binding_status_for(
    db: AsyncSession, *, wp_id: uuid.UUID, sheet_name: str
) -> str | None:
    """取该 wp + sheet 的 sheet-open binding 状态。

    复用 `_wp_onlyoffice_legacy_url_gate._binding_verdict`，不另建一套「哪个 binding
    适用」的判定 —— 本仓已有过一次「两侧协商出不同 wp_code」的事故，判定只有一份。

    拿不到（无 binding / 生成物坏 / 抛异常）一律 None ⇒ 调用方视为非 draining 放行。
    理由与 gate 的 fail-open 同源：不能因为读不到 binding 就让已打开的会话存不了。
    """
    try:
        from app.models.workpaper_models import WorkingPaper, WpIndex
        from app.routers._wp_onlyoffice_legacy_url_gate import _binding_verdict

        row = (
            await db.execute(
                sa.select(WpIndex.wp_code, WorkingPaper.project_id)
                .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
                .where(WorkingPaper.id == wp_id)
            )
        ).first()
        if row is None or not row[0]:
            return None
        _verdict, binding = _binding_verdict(
            source_wp_code=str(row[0]), sheet_name=sheet_name, whole_workbook=False,
            project_id=row[1],
        )
        del _verdict
        status = binding.get("status") if binding else None
        return str(status) if status else None
    except Exception as exc:
        logger.info(
            "取 binding 状态失败，按非 draining 放行 wp=%s sheet=%s: %s",
            wp_id, sheet_name, exc,
        )
        return None


async def verify_draining_callback(
    db: AsyncSession,
    *,
    wp_id: uuid.UUID,
    sheet_name: str,
    doc_key: str,
) -> tuple[bool, str]:
    """4.3：draining 下只接受**已签发且未结算**的 callback。

    Returns:
        (accepted, reason)。reason 是中文，供端点记 warning / 回执。

    ═══ 为什么不能只看 binding 状态 ═══

    `draining` 的语义是「不再为新请求造旧 doc key，但**已签发者**按 TTL 结算」。
    只判 binding 状态就放行，等于让任意伪造的 doc_key 都能写回 —— 因为 OO 的
    callback 请求体自带 `key`，而旧式链路从不校验它（历史注释明写「端点从不校验
    doc_key 不可预测性」）。

    所以 draining 下的判据必须是**两段**：
      ① binding 已是 draining（调用方已判，这里只做一致性断言）；
      ② 该 doc_key 在 ledger 里**确有未结算的签发行**。

    ═══ 为什么 non-draining 直接放行 ═══

    其它状态（pending / out_of_scope / 无 binding）下旧式链路仍是**正常**通道，
    它的鉴权由 `_verify_callback_jwt` 负责。在这里额外要求 ledger 记录会让
    升级前已打开的会话在升级后无法保存 —— 那是比 drain 更重的事故。
    """
    binding_status = await _binding_status_for(db, wp_id=wp_id, sheet_name=sheet_name)
    if binding_status != "draining":
        return True, ""
    if not doc_key:
        return False, "draining 下的旧式 callback 必须带 doc key（请求体缺 key）"
    row = await find_open_by_doc_key(db, doc_key=doc_key)
    if row is None:
        logger.warning(
            "legacy drain: 拒绝 draining 下的未签发 callback wp=%s sheet=%s doc_key_sha=%s",
            wp_id, sheet_name, doc_key_digest(doc_key)[:12],
        )
        return False, (
            "draining 下该 doc key 没有未结算的签发记录 —— "
            "旧式链路已停止签发，请改用协同编辑入口重新打开"
        )
    return True, ""


__all__ = [
    "DEFAULT_TTL",
    "DRAIN_DELETE_GATE_KEYS",
    "DrainNotCompleteError",
    "assert_drain_complete_for_delete",
    "EVENT_ISSUED",
    "EVENT_SETTLED",
    "TERMINAL_ABANDONED",
    "TERMINAL_EXPIRED",
    "TERMINAL_REJECTED",
    "TERMINAL_SAVED",
    "TERMINAL_STATES",
    "TERMINAL_SUPERSEDED",
    "doc_key_digest",
    "drain_metrics",
    "find_open_by_doc_key",
    "open_issuances",
    "record_issuance",
    "record_issuance_quietly",
    "settle_issuance",
    "verify_draining_callback",
]
