"""AI 对话持久化原语（Task 3）

Feature: dsh-agent-panel-integration
Requirements:
  - 4.10：history 倒序取最近 N 条、外层正序返回，并携带真实 message/run metadata。
  - 4.11：会话定位绑定 user/project/year/host type/host ID，有**数据库唯一约束**，
    并发首轮创建使用 upsert 等价原子语义。
  - 7.3：会话附件 metadata（表结构由 V147 + ``AIChatAttachment`` 承载）。
  - 8.2/8.3：note 转存/采纳的幂等收据；目标定位单一规则 + 数据库唯一约束，
    **禁止**"先查后建"。
Design: "Components and Interfaces → 6. Persistence Model"
Properties: 6（会话与 Run 并发幂等）、10（最近历史顺序与元数据完整）、
  21（项目笔记并发幂等）

## 为什么"先查后建"必须被禁止

旧实现（``doc_chat_persistence.get_or_create_session``）是
``SELECT … → 若无则 INSERT``。两个并发首轮请求各自 SELECT 到空、各自 INSERT ⇒
同一会话两行，历史从此分裂。检查—插入之间的窗口在应用层**无法**消除，
唯一可靠手段是数据库唯一约束 + ``INSERT … ON CONFLICT``：

- 冲突时 PG 会**阻塞等待**竞争事务结束，再返回 0 行；
- 随后的 SELECT 在 READ COMMITTED 下取新快照，必然看到已提交的胜者行；
- 竞争事务回滚时 SELECT 会落空 ⇒ 由 :data:`_UPSERT_ATTEMPTS` 次重试兜住。

## 时间列类型（勿"顺手改齐"）

``ai_chat_session.last_message_at`` 与 ``ai_chat_message.created_at`` 都是
**naive TIMESTAMP**（与该表既有列同类型）；四张新表用 **TIMESTAMPTZ**。
🔴 回写 timestamptz 必须在 **Python 侧**传 ``datetime`` 对象 —— asyncpg 在发送前
按目标类型编码，SQL 层 ``CAST(:x AS timestamptz)`` 不起作用。
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import (
    AIChatActionReceipt,
    AIChatMessage,
    AIChatRun,
    AIChatSession,
    ActionReceiptStatus,
    ActionReceiptType,
    ChatEngineName,
    ChatMessageStatus,
    ChatRole,
    ChatRunStatus,
    SessionType,
)
from app.services.ai_chat.contracts import GLOBAL_KNOWLEDGE_HOST_ID, HostType

logger = logging.getLogger(__name__)

__all__ = [
    "SESSION_KEY_VERSION",
    "NO_PROJECT_SENTINEL",
    "NO_YEAR_SENTINEL",
    "DEFAULT_HISTORY_LIMIT",
    "ChatHistoryEntry",
    "build_session_key",
    "content_hash",
    "upsert_session",
    "find_session",
    "append_message",
    "load_recent_history",
    "upsert_run",
    "claim_action_receipt",
    "settle_action_receipt",
]

#: 定位键算法版本。改动 canonical 串组成必须同时升版本，否则新旧 key 静默错位。
SESSION_KEY_VERSION = "v1"

#: 无项目（受限全局知识模式）的显式 sentinel —— 复用 Task 1 冻结的宿主 sentinel，
#: 不新造第二个常量，也绝不用空字符串/空 UUID 伪装项目（Req 3.3）。
NO_PROJECT_SENTINEL = GLOBAL_KNOWLEDGE_HOST_ID

#: 年度缺失时的占位段。存量会话（V147 之前）未记录 audit_year，回填后为该形态。
NO_YEAR_SENTINEL = "-"

#: history 默认条数上限。
DEFAULT_HISTORY_LIMIT = 50

#: upsert 冲突重试次数（竞争事务回滚时需要重新插入）。
_UPSERT_ATTEMPTS = 3

#: ``uq_ai_chat_session_user_key`` 是**部分**唯一索引，ON CONFLICT 推断必须带同样谓词。
_SESSION_CONFLICT_WHERE = sa.and_(
    AIChatSession.user_id.isnot(None), AIChatSession.session_key.isnot(None)
)


def build_session_key(
    *,
    user_id: UUID,
    project_id: UUID | None,
    audit_year: int | None,
    host_type: HostType | str,
    host_id: str,
) -> str:
    """服务端规范化会话定位 hash（Req 4.11 的五要素）。

    canonical 串 = ``v1|{user}|{project|sentinel}|{year|'-'}|{host_type}|{host_id}``，
    取其 UTF-8 字节的 sha256 hex（64 字符，与 ``session_key VARCHAR(64)`` 对齐）。

    🔴 V147 的回填 SQL 逐字复现同一表达式；守卫
    ``test_session_key_sql_backfill_matches_python`` 对同一输入两侧求值比对。
    改这里必须同步改迁移，否则运行时 upsert 与存量行错位 = 同一会话两行。

    :raises ValueError: ``host_id`` 为空（空字符串伪装有效 ID 是明令禁止的形态）。
    """
    ht = host_type.value if isinstance(host_type, HostType) else str(host_type)
    if ht not in {h.value for h in HostType}:
        raise ValueError(f"未登记的 host_type: {ht!r}")
    if not host_id:
        raise ValueError("host_id 不得为空字符串；无项目宿主须用显式 sentinel")
    canonical = "|".join(
        [
            SESSION_KEY_VERSION,
            str(user_id),
            str(project_id) if project_id else NO_PROJECT_SENTINEL,
            str(audit_year) if audit_year is not None else NO_YEAR_SENTINEL,
            ht,
            host_id,
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def content_hash(text: str) -> str:
    """消息正文哈希（采纳/转存以此校验服务端正文未被篡改，Req 8.1/8.6）。"""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChatHistoryEntry:
    """history 单条记录（Req 4.10 的真实元数据）。

    ``role`` / ``content`` 保持旧 ``get_history`` 的键名，前端与既有测试无需改动；
    其余字段是 Task 3 新补的真实元数据（不是客户端可伪造的推断值）。
    """

    role: str
    content: str
    message_id: str
    status: str
    created_at: str | None = None
    run_id: str | None = None
    run_status: str | None = None
    engine: str | None = None
    model: str | None = None
    tokens: int | None = None
    latency_ms: int | None = None
    content_hash: str | None = None
    citations: Any = None
    context_manifest: Any = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# 会话
# ---------------------------------------------------------------------------


async def upsert_session(
    db: AsyncSession,
    *,
    user_id: UUID,
    project_id: UUID | None,
    audit_year: int | None,
    host_type: HostType | str,
    host_id: str,
    title: str | None = None,
    engine_preference: str | None = None,
    review_mode: bool | None = None,
) -> tuple[AIChatSession, bool]:
    """按 ``(user_id, session_key)`` 原子 upsert 会话，返回 ``(session, created)``。

    Property 6 前半：100 个并发相同 session key 的首次请求最终只产生一个 session。
    保证来自 ``uq_ai_chat_session_user_key`` 唯一索引，**不是**先查后建。

    ``created`` 为 True 表示本次调用是插入的胜者；调用方可据此决定"只做一次"的
    副作用（如写欢迎语），但不得用它替代数据库约束。
    """
    ht = host_type.value if isinstance(host_type, HostType) else str(host_type)
    key = build_session_key(
        user_id=user_id,
        project_id=project_id,
        audit_year=audit_year,
        host_type=ht,
        host_id=host_id,
    )

    values: dict[str, Any] = {
        "id": uuid4(),
        "project_id": project_id,
        "session_type": SessionType.general.value,
        "title": title or f"{ht} 对话",
        "user_id": user_id,
        "session_key": key,
        "host_type": ht,
        "host_id": host_id,
        "audit_year": audit_year,
        "engine_preference": engine_preference,
        "review_mode": bool(review_mode) if review_mode is not None else False,
        "total_messages": 0,
        "total_tokens": 0,
    }

    for attempt in range(_UPSERT_ATTEMPTS):
        stmt = (
            pg_insert(AIChatSession)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=[AIChatSession.user_id, AIChatSession.session_key],
                index_where=_SESSION_CONFLICT_WHERE,
            )
            .returning(AIChatSession.id)
        )
        inserted_id = (await db.execute(stmt)).scalar_one_or_none()
        if inserted_id is not None:
            session = (
                await db.execute(
                    sa.select(AIChatSession).where(AIChatSession.id == inserted_id)
                )
            ).scalar_one()
            return session, True

        # 冲突：胜者已提交（PG 在 DO NOTHING 前会等待竞争事务结束）⇒ 读回同一行。
        existing = (
            await db.execute(
                sa.select(AIChatSession).where(
                    AIChatSession.user_id == user_id,
                    AIChatSession.session_key == key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if review_mode is not None and existing.review_mode != bool(review_mode):
                existing.review_mode = bool(review_mode)
            return existing, False
        # 竞争事务回滚 ⇒ 该 key 又空出来了，重试插入。
        values["id"] = uuid4()
        logger.debug("upsert_session 冲突后读空，重试 %d/%d", attempt + 1, _UPSERT_ATTEMPTS)

    raise RuntimeError(f"upsert_session 重试 {_UPSERT_ATTEMPTS} 次仍未取得会话")


async def find_session(
    db: AsyncSession,
    *,
    user_id: UUID,
    project_id: UUID | None,
    audit_year: int | None,
    host_type: HostType | str,
    host_id: str,
) -> AIChatSession | None:
    """只读定位会话（history / clear 用；**不创建**）。

    ``audit_year`` 给定时按精确 session_key 命中；缺省（``None``）时先按
    year-less key 命中，再退回"同 ``(user, host_type, host_id)`` 下最近使用的会话"。

    为什么需要这个 fallback：``GET/DELETE …/history`` 端点历史上不带 year 参数
    （前端契约由 Task 2/9 负责改），而 Req 4.11 要求 **locator 必须含 year**。
    两者的兼容点就是：定位键仍绑定五要素（不放宽约束），只读查询在缺 year 时
    按 ``last_message_at`` 取最近一个 —— 既不伪造 year，也不让存量历史不可见。
    """
    ht = host_type.value if isinstance(host_type, HostType) else str(host_type)
    key = build_session_key(
        user_id=user_id,
        project_id=project_id,
        audit_year=audit_year,
        host_type=ht,
        host_id=host_id,
    )
    exact = (
        await db.execute(
            sa.select(AIChatSession).where(
                AIChatSession.user_id == user_id,
                AIChatSession.session_key == key,
            )
        )
    ).scalar_one_or_none()
    if exact is not None or audit_year is not None:
        return exact

    return (
        await db.execute(
            sa.select(AIChatSession)
            .where(
                AIChatSession.user_id == user_id,
                AIChatSession.host_type == ht,
                AIChatSession.host_id == host_id,
            )
            .order_by(
                AIChatSession.last_message_at.desc().nullslast(),
                AIChatSession.created_at.desc(),
            )
            .limit(1)
        )
    ).scalars().first()


# ---------------------------------------------------------------------------
# 消息
# ---------------------------------------------------------------------------


async def append_message(
    db: AsyncSession,
    session: AIChatSession,
    *,
    role: str | ChatRole,
    text: str,
    status: str | ChatMessageStatus = ChatMessageStatus.completed,
    run_id: UUID | None = None,
    citations: Any = None,
    context_manifest: Any = None,
    model_used: str | None = None,
    tokens_used: int | None = None,
    latency_ms: int | None = None,
) -> AIChatMessage:
    """追加一条消息并同步会话计数 / ``last_message_at``。

    citations 写入既有 ``referenced_sources``（**不新增 citations 列**）。
    ``content_hash`` 由服务端计算 —— 采纳/转存以它校验正文未被客户端篡改。
    """
    msg = AIChatMessage(
        session_id=session.id,
        role=role if isinstance(role, ChatRole) else ChatRole(role),
        message_text=text,
        status=status.value if isinstance(status, ChatMessageStatus) else str(status),
        run_id=run_id,
        content_hash=content_hash(text),
        referenced_sources=citations,
        context_manifest=context_manifest,
        model_used=model_used,
        tokens_used=tokens_used,
        latency_ms=latency_ms,
    )
    db.add(msg)
    session.total_messages = (session.total_messages or 0) + 1
    if tokens_used:
        session.total_tokens = (session.total_tokens or 0) + int(tokens_used)
    # naive：与 ai_chat_session.created_at / ai_chat_message.created_at 同类型。
    session.last_message_at = datetime.now()
    await db.flush()
    return msg


async def load_recent_history(
    db: AsyncSession,
    *,
    session_id: UUID,
    limit: int = DEFAULT_HISTORY_LIMIT,
) -> list[ChatHistoryEntry]:
    """取**最近** N 条消息并按时间**正序**返回，携带真实 message/run metadata。

    Req 4.10 / Property 10。旧实现是 ``ORDER BY created_at LIMIT N`` —— 取的是
    **最早** N 条，会话一旦超过 N 条，用户就再也看不到刚说过的话，模型也拿不到
    近期上下文。正确做法是子查询倒序取 N 条，外层再正序。

    排序键是 ``(created_at, seq)``：``created_at`` 默认 ``now()`` = 事务开始时刻，
    同一事务内追加的多条消息时间完全相同 ⇒ 只按 created_at 排序无确定顺序。
    ``seq``（BIGSERIAL）提供单调兜底。
    """
    if limit <= 0:
        return []

    inner = (
        sa.select(
            AIChatMessage.id.label("id"),
            AIChatMessage.role.label("role"),
            AIChatMessage.message_text.label("message_text"),
            AIChatMessage.status.label("status"),
            AIChatMessage.created_at.label("created_at"),
            AIChatMessage.seq.label("seq"),
            AIChatMessage.run_id.label("run_id"),
            AIChatMessage.content_hash.label("content_hash"),
            AIChatMessage.referenced_sources.label("citations"),
            AIChatMessage.context_manifest.label("context_manifest"),
            AIChatMessage.model_used.label("model_used"),
            AIChatMessage.tokens_used.label("tokens_used"),
            AIChatMessage.latency_ms.label("latency_ms"),
            AIChatRun.status.label("run_status"),
            AIChatRun.engine.label("engine"),
        )
        .select_from(AIChatMessage)
        .outerjoin(AIChatRun, AIChatRun.id == AIChatMessage.run_id)
        .where(AIChatMessage.session_id == session_id)
        .order_by(AIChatMessage.created_at.desc(), AIChatMessage.seq.desc())
        .limit(limit)
        .subquery()
    )
    rows = (
        await db.execute(
            sa.select(inner).order_by(
                inner.c.created_at.asc(), inner.c.seq.asc()
            )
        )
    ).all()

    return [
        ChatHistoryEntry(
            role=r.role.value if hasattr(r.role, "value") else str(r.role),
            content=r.message_text,
            message_id=str(r.id),
            status=r.status,
            created_at=r.created_at.isoformat() if r.created_at else None,
            run_id=str(r.run_id) if r.run_id else None,
            run_status=r.run_status,
            engine=r.engine,
            model=r.model_used,
            tokens=r.tokens_used,
            latency_ms=r.latency_ms,
            content_hash=r.content_hash,
            citations=r.citations,
            context_manifest=r.context_manifest,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


async def upsert_run(
    db: AsyncSession,
    *,
    session_id: UUID,
    actor_id: UUID,
    idempotency_key: str,
    project_id: UUID | None,
    host_type: HostType | str,
    host_id: str,
    engine: str | ChatEngineName = ChatEngineName.native,
    request_id: UUID | None = None,
    capability_snapshot: dict[str, Any] | None = None,
) -> tuple[AIChatRun, bool]:
    """按 ``(actor_id, session_id, idempotency_key)`` 原子 upsert run。

    Property 6 后半：100 个相同 idempotency key 的并发请求只产生一个 run。
    ``created`` 为 True 的调用**恰好一个** —— 调用方以它为唯一闸门决定
    "保存 user message + 调用 engine"，重复请求返回原 run 且 ``created=False``
    （Req 4.6：不重复保存用户消息、不重复调用模型、不重复执行工具）。

    🔴 user message 必须与本次 run 插入在**同一事务**内写入：竞争者的 run 插入
    被唯一索引拒绝时其整个事务回滚，消息也随之消失 ⇒ "一个 run 一条 user message"
    由数据库原子性保证，而不是靠应用层判断。
    """
    if not idempotency_key:
        raise ValueError("idempotency_key 不得为空")
    ht = host_type.value if isinstance(host_type, HostType) else str(host_type)
    eng = engine.value if isinstance(engine, ChatEngineName) else str(engine)

    values: dict[str, Any] = {
        "id": uuid4(),
        "session_id": session_id,
        "request_id": request_id or uuid4(),
        "idempotency_key": idempotency_key,
        "actor_id": actor_id,
        "project_id": project_id,
        "host_type": ht,
        "host_id": host_id,
        "engine": eng,
        "status": ChatRunStatus.queued.value,
        "capability_snapshot": capability_snapshot,
        "retry_count": 0,
    }

    for attempt in range(_UPSERT_ATTEMPTS):
        stmt = (
            pg_insert(AIChatRun)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=[
                    AIChatRun.actor_id,
                    AIChatRun.session_id,
                    AIChatRun.idempotency_key,
                ]
            )
            .returning(AIChatRun.id)
        )
        inserted_id = (await db.execute(stmt)).scalar_one_or_none()
        if inserted_id is not None:
            run = (
                await db.execute(sa.select(AIChatRun).where(AIChatRun.id == inserted_id))
            ).scalar_one()
            return run, True

        existing = (
            await db.execute(
                sa.select(AIChatRun).where(
                    AIChatRun.actor_id == actor_id,
                    AIChatRun.session_id == session_id,
                    AIChatRun.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, False
        values["id"] = uuid4()
        logger.debug("upsert_run 冲突后读空，重试 %d/%d", attempt + 1, _UPSERT_ATTEMPTS)

    raise RuntimeError(f"upsert_run 重试 {_UPSERT_ATTEMPTS} 次仍未取得 run")


# ---------------------------------------------------------------------------
# 幂等收据（note-create / adopt）
# ---------------------------------------------------------------------------


async def claim_action_receipt(
    db: AsyncSession,
    *,
    action_type: str | ActionReceiptType,
    actor_id: UUID,
    session_id: UUID,
    idempotency_key: str,
    source_message_hash: str | None = None,
) -> tuple[AIChatActionReceipt, bool]:
    """抢占一张幂等收据，返回 ``(receipt, claimed)``。

    Property 21：同一 note idempotency key 的并发请求只有一个 ``claimed=True``，
    其余读回同一收据 ⇒ 只创建一个 folder/document/receipt。
    保证来自 ``uq_ai_chat_action_receipts_idempotency``，**禁止**先查后建。

    ``claimed=False`` 且 ``status='succeeded'`` ⇒ 直接返回既有
    ``result_resource_id``（幂等返回同一文档）；``status='failed'`` ⇒ 调用方可
    重置为 pending 后重试（Req 8.9：失败可安全重试）。
    """
    if not idempotency_key:
        raise ValueError("idempotency_key 不得为空")
    at = (
        action_type.value
        if isinstance(action_type, ActionReceiptType)
        else str(action_type)
    )

    for attempt in range(_UPSERT_ATTEMPTS):
        stmt = (
            pg_insert(AIChatActionReceipt)
            .values(
                id=uuid4(),
                action_type=at,
                actor_id=actor_id,
                session_id=session_id,
                idempotency_key=idempotency_key,
                source_message_hash=source_message_hash,
                status=ActionReceiptStatus.pending.value,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    AIChatActionReceipt.action_type,
                    AIChatActionReceipt.actor_id,
                    AIChatActionReceipt.session_id,
                    AIChatActionReceipt.idempotency_key,
                ]
            )
            .returning(AIChatActionReceipt.id)
        )
        inserted_id = (await db.execute(stmt)).scalar_one_or_none()
        if inserted_id is not None:
            receipt = (
                await db.execute(
                    sa.select(AIChatActionReceipt).where(
                        AIChatActionReceipt.id == inserted_id
                    )
                )
            ).scalar_one()
            return receipt, True

        existing = (
            await db.execute(
                sa.select(AIChatActionReceipt).where(
                    AIChatActionReceipt.action_type == at,
                    AIChatActionReceipt.actor_id == actor_id,
                    AIChatActionReceipt.session_id == session_id,
                    AIChatActionReceipt.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, False
        logger.debug(
            "claim_action_receipt 冲突后读空，重试 %d/%d", attempt + 1, _UPSERT_ATTEMPTS
        )

    raise RuntimeError(f"claim_action_receipt 重试 {_UPSERT_ATTEMPTS} 次仍未取得收据")


async def settle_action_receipt(
    db: AsyncSession,
    receipt: AIChatActionReceipt,
    *,
    status: str | ActionReceiptStatus,
    result_resource_id: UUID | None = None,
    error_code: str | None = None,
) -> AIChatActionReceipt:
    """结算收据（成功写 ``result_resource_id``，失败写 ``error_code``）。"""
    receipt.status = (
        status.value if isinstance(status, ActionReceiptStatus) else str(status)
    )
    if result_resource_id is not None:
        receipt.result_resource_id = result_resource_id
    receipt.error_code = error_code
    # timestamptz：Python 侧传 datetime（SQL 层 CAST 在 asyncpg 下无效）。
    receipt.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return receipt
