"""AI 内容采纳 · server-authoritative + 幂等 + fail-closed（Task 7）

Feature: dsh-agent-panel-integration
Requirements:
  - 8.1：assistant 消息使用**服务端签发**的 message ID；采纳引用 message ID，
    绝不把客户端正文当权威来源。
  - 8.6：adopt 依据 message ID 从数据库读取 assistant 正文，并校验该消息属于
    当前用户、会话、项目与 HostContext；篡改 message ID / project ID / host /
    客户端 content 一律被拒。
  - 8.7：``wrap_ai_output_with_log`` 或 ``ai_content_log`` 写入失败 SHALL 回滚并
    返回失败；**只有**获得非空且真实存在的 log ID 才能返回"已进入确认流"。
  - 8.8：采纳属于业务确认流写动作，走既有 write capability 检查（``AiChatAction.adopt``
    在 Task 1 已登记为 HOST WRITE 动作，经 ``workpaper.ai_generate`` 写入口 +
    ``ai_generate``/``ai_confirm`` 两个 capability）；本模块**不**做第二次权限判定。
  - 8.9：写平台哈希链审计，只保存 message/content hash 与引用 ID，不重复存储正文。
Design: "Components and Interfaces → 10. Note Capture and Adopt → 采纳"。
Properties:
  - **Property 22（采纳权威正文与失败回滚）**
  - **Property 32（哈希链事件成对完整；审计不含正文/token）**
  - **Property 33（下游故障不产生假成功）**

## 旧实现的两个真实缺陷（本模块存在的理由）

1. ``AdoptRequest.content`` 是客户端字段，端点把它**原样**写进 ``ai_content_log``。
   于是"AI 生成内容"这条溯源链的起点可以由浏览器任意伪造 —— 确认流门禁
   （``AIContentMustBeConfirmedRule``）拦的是"未确认"，拦不住"根本不是 AI 说的"。
2. ``wrap_ai_output_with_log`` 内部 ``except Exception`` 把 ``ai_content_log.create``
   的异常吞成 **WARNING** 后照常返回 base dict（只是少了 ``ai_content_log_id``），
   而端点不看返回值就 ``commit`` + ``success: True``。结果：日志没写、确认流没建立、
   前端显示"已进入确认流"。这正是本仓库最贵的 fail-open 形态。

本模块对这两点的处置：

- 正文**只**来自 ``ai_chat_message.message_text``（含服务端 ``content_hash`` 复核）；
- log ID 必须**非空且能在同一事务内查得到行**，否则整个 savepoint 回滚并抛
  :class:`AdoptFailed`（``adopt_log_failed``），异常记 **ERROR**（不是 WARNING）。

## 事务形状（为什么用 SAVEPOINT）

``wrap_ai_output_with_log`` 把 DB 异常吞掉后，PG 侧事务已处于 aborted 状态：随后的
任何语句都会报 ``InFailedSQLTransaction``。若不加 SAVEPOINT，就无法在失败路径上
再执行"核验 log 行是否存在""结算收据"这类语句，也无法区分"日志没写"与"会话已废"。
因此全部采纳副作用（收据 + ai_content_log + 审计）都包在一个 ``begin_nested()`` 里：

    ┌ SAVEPOINT ────────────────────────────────────────────────┐
    │ claim_action_receipt → wrap_ai_output_with_log             │
    │ → 核验 log 行真实存在 → settle_action_receipt → 哈希链审计 │
    └───────────────────────────────────────────────────────────┘
      任一步失败 ⇒ ROLLBACK TO SAVEPOINT（收据/日志/审计全部消失）
      随后整事务 rollback ⇒ 幂等键重新空出，重试安全

``commit`` 也在本模块内：Req 8.7 把"commit 失败"与"日志写失败"并列要求同一处置
（回滚 + ``adopt_log_failed``），放在两个层里必然出现"一边回滚一边返回成功"的缝。

## 存量消息为什么可能不可采纳

``ai_chat_message.content_hash`` 由 V147 新增且**未回填**。没有服务端哈希的行无法
证明"正文是本服务端流水线签发的"，因此按 fail-closed 拒绝（``adopt_content_tampered``）。
这是有意的取舍：宁可让 Task 3 之前的历史消息不可采纳，也不放行来源不明的正文。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import (
    ActionReceiptStatus,
    ActionReceiptType,
    AIChatMessage,
    AIChatRun,
    AIChatSession,
    ChatMessageStatus,
    ChatRole,
)
from app.models.v3_refinement_models import AiContentLog
from app.services.ai_chat.access import ResourceAccessResolver
from app.services.ai_chat.contracts import (
    AiChatAction,
    AiChatDenialCode,
    HostType,
    ResourceType,
    coerce_uuid,
)
from app.services.ai_chat.host_context import AuthorizedHostContext
from app.services.ai_chat.persistence import (
    claim_action_receipt,
    content_hash,
    settle_action_receipt,
)
from app.services.ai_chat.run_contract import ChatErrorCode
from app.services.audit_log_helper import append_audit_log
from app.services.wp_visibility.denial import ExternalNotFound

logger = logging.getLogger(__name__)

__all__ = [
    "ADOPT_CONFIRM_FLOW_MESSAGE",
    "ADOPT_ERROR_HTTP_STATUS",
    "ADOPT_ERROR_MESSAGE",
    "ADOPT_AUDIT_ACTION",
    "ADOPT_AUDIT_DETAIL_KEYS",
    "ADOPT_IDEMPOTENCY_CONFLICT",
    "ADOPT_IN_PROGRESS",
    "ADOPT_LOG_FAILED",
    "ADOPT_SOURCE_STATUS",
    "ADOPT_SOURCE_ROLE",
    "AdoptFailed",
    "AdoptOutcome",
    "AuthoritativeMessage",
    "adopt_message",
    "load_authoritative_message",
]

# ---------------------------------------------------------------------------
# 稳定 error code（采纳子域）
# ---------------------------------------------------------------------------

#: 日志创建 / 核验 / 结算 / 审计 / commit 任一步失败（Req 8.7 的唯一失败码）。
#:
#: 🔴 取值**派生自** :class:`~app.services.ai_chat.run_contract.ChatErrorCode`
#: （Task 6 收口）：它同时是 Chat Run 的对外稳定 error code（design 的 error code 清单
#: 里就有 ``adopt_log_failed``）。此前两处各写一份同名字面量 —— 一处改另一处不改时，
#: 前端按 run 的 code 分派而采纳接口回的是旧值，属于"一个错误码两个真源"。
ADOPT_LOG_FAILED = ChatErrorCode.adopt_log_failed.value
#: 同一幂等键被用于**另一条**消息（客户端复用 key，语义冲突，不可静默返回旧结果）。
ADOPT_IDEMPOTENCY_CONFLICT = "adopt_idempotency_conflict"
#: 收据处于 pending（另一请求在途 / 上一次进程级中断），不产生第二条确认流记录。
ADOPT_IN_PROGRESS = "adopt_in_progress"

#: 错误码 → HTTP 状态。日志失败是可重试的服务端故障（503）；幂等冲突是客户端语义冲突（409）。
ADOPT_ERROR_HTTP_STATUS: dict[str, int] = {
    ADOPT_LOG_FAILED: 503,
    ADOPT_IDEMPOTENCY_CONFLICT: 409,
    ADOPT_IN_PROGRESS: 409,
}

#: 错误码 → 中文用户消息（NFR-5：给出可执行下一步；内部异常细节只进日志）。
ADOPT_ERROR_MESSAGE: dict[str, str] = {
    ADOPT_LOG_FAILED: "采纳未生效：AI 内容确认记录写入失败，本次操作已回滚，请稍后重试",
    ADOPT_IDEMPOTENCY_CONFLICT: "采纳未生效：该幂等标识已用于另一条消息，请重新发起采纳",
    ADOPT_IN_PROGRESS: "采纳正在处理中，请稍候再试",
}

#: 成功文案 —— **只有**拿到非空且真实存在的 ``ai_content_log_id`` 才允许返回（Req 8.7）。
ADOPT_CONFIRM_FLOW_MESSAGE = "AI 内容已进入确认流，待审核确认后方可写入文档"

#: 可采纳来源的两个硬条件（Req 8.1：只有 completed 的 assistant 消息）。
ADOPT_SOURCE_ROLE = ChatRole.assistant
ADOPT_SOURCE_STATUS = ChatMessageStatus.completed

# ---------------------------------------------------------------------------
# 哈希链审计
# ---------------------------------------------------------------------------

#: 审计 action_type（复用既有 ``ai_content_lifecycle`` event schema，不新增 event 取值域）。
ADOPT_AUDIT_ACTION = "ai_content_adopt"

#: 审计 details 的**完整**键集合（Req 8.9 / Property 32）。
#:
#: 🔴 这不是注释而是判据：守卫拿它与真实审计行的 payload 键集合比对，
#: 因此"少写一个引用 ID"或"多塞一段正文"都会打红。``project_id`` 由
#: ``append_audit_log`` 注入存储载荷，不在本集合内。
ADOPT_AUDIT_DETAIL_KEYS: frozenset[str] = frozenset(
    {
        "event_type",
        "action",
        "ai_content_log_id",
        "message_id",
        "content_hash",
        "session_id",
        "run_id",
        "receipt_id",
        "host_type",
        "host_id",
        "target",
    }
)


class AdoptFailed(RuntimeError):
    """采纳失败（已回滚，响应**不含** success）。

    ``code`` 取值见 :data:`ADOPT_ERROR_HTTP_STATUS`；路由据此映射 HTTP 状态与中文消息。
    """

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True)
class AuthoritativeMessage:
    """服务端权威消息（正文与哈希均来自数据库，客户端不参与）。"""

    message_id: UUID
    session_id: UUID
    run_id: UUID | None
    text: str
    content_hash: str
    model_used: str | None


@dataclass(frozen=True)
class AdoptOutcome:
    """采纳结果（成功路径唯一出口）。"""

    ai_content_log_id: UUID
    content_hash: str
    message_id: UUID
    receipt_id: UUID
    #: True = 命中既有成功收据的幂等重放（未再写第二条 ai_content_log）。
    idempotent_replay: bool

    def as_response(self) -> dict[str, object]:
        """端点响应体。``success`` 只在本对象存在时为真（Property 33）。"""
        return {
            "success": True,
            "ai_content_log_id": str(self.ai_content_log_id),
            "confirm_action": "pending",
            "content_hash": self.content_hash,
            "message_id": str(self.message_id),
            "receipt_id": str(self.receipt_id),
            "idempotent_replay": self.idempotent_replay,
            "message": ADOPT_CONFIRM_FLOW_MESSAGE,
        }


class _LogWriteFailed(RuntimeError):
    """内部信号：日志创建/核验失败（转 :class:`AdoptFailed` 前不外泄）。"""


# ---------------------------------------------------------------------------
# ① message → run → session → actor → HostContext
# ---------------------------------------------------------------------------


async def load_authoritative_message(
    db: AsyncSession,
    *,
    message_id: UUID,
    actor_id: UUID,
    host: AuthorizedHostContext,
    access: ResourceAccessResolver | None = None,
    request_id: str | None = None,
) -> AuthoritativeMessage:
    """按 message ID 读取服务端权威正文，逐段校验归属链（Req 8.6）。

    校验顺序（任一段不成立即拒绝，且**在读取正文之前**完成归属判定）::

        message 存在 → role/status 可采纳 → session 属于 actor
        → session 项目/宿主 == 已授权 HostContext → run（若有）同属该 actor/session/宿主
        → 正文非空且服务端 content_hash 与重算值一致

    拒绝一律写内部 denial audit 并抛不可枚举 404（Req 2.5）：篡改 message ID、
    换成别人的消息、换一个项目/宿主，对外都是同一句"资源不存在或不可访问"。
    """
    resolver = access if access is not None else ResourceAccessResolver(db)

    async def _deny(code: AiChatDenialCode) -> ExternalNotFound:
        await resolver.audit_denial(
            principal_id=actor_id,
            project_id=host.project_id,
            denial_code=code.value,
            entrypoint="ai_chat.adopt.source",
            action=AiChatAction.adopt,
            resource_type=_RESOURCE_BY_HOST.get(host.resource_type),
            resource_id=str(message_id),
            request_id=request_id,
        )
        return ExternalNotFound()

    row = (
        await db.execute(
            sa.select(
                AIChatMessage.id,
                AIChatMessage.session_id,
                AIChatMessage.run_id,
                AIChatMessage.role,
                AIChatMessage.status,
                AIChatMessage.message_text,
                AIChatMessage.content_hash,
                AIChatMessage.model_used,
                AIChatSession.user_id.label("session_user_id"),
                AIChatSession.project_id.label("session_project_id"),
                AIChatSession.host_type.label("session_host_type"),
                AIChatSession.host_id.label("session_host_id"),
                AIChatRun.actor_id.label("run_actor_id"),
                AIChatRun.session_id.label("run_session_id"),
                AIChatRun.project_id.label("run_project_id"),
                AIChatRun.host_type.label("run_host_type"),
                AIChatRun.host_id.label("run_host_id"),
            )
            .select_from(AIChatMessage)
            .join(AIChatSession, AIChatSession.id == AIChatMessage.session_id)
            .outerjoin(AIChatRun, AIChatRun.id == AIChatMessage.run_id)
            .where(AIChatMessage.id == message_id)
        )
    ).first()
    if row is None:
        raise await _deny(AiChatDenialCode.resource_not_found)

    # ── 可采纳性：只有 completed 的 assistant 消息（Req 8.1）─────────────
    role = row.role.value if hasattr(row.role, "value") else str(row.role)
    if role != ADOPT_SOURCE_ROLE.value:
        raise await _deny(AiChatDenialCode.adopt_source_unusable)
    if str(row.status) != ADOPT_SOURCE_STATUS.value:
        raise await _deny(AiChatDenialCode.adopt_source_unusable)

    # ── actor 绑定：会话必须属于当前用户 ────────────────────────────────
    if row.session_user_id is None or row.session_user_id != actor_id:
        raise await _deny(AiChatDenialCode.access_denied)

    # ── HostContext 绑定：会话的项目/宿主必须与已授权宿主一致（Req 8.6）──
    if row.session_project_id != host.project_id:
        raise await _deny(AiChatDenialCode.host_context_mismatch)
    if row.session_host_type != host.resource_type.value:
        raise await _deny(AiChatDenialCode.host_context_mismatch)
    if row.session_host_id != host.resource_id:
        raise await _deny(AiChatDenialCode.host_context_mismatch)

    # ── run 绑定（Task 4 落地前 run_id 可为 NULL；存在即必须同属同一 actor/会话/宿主）──
    if row.run_id is not None:
        if row.run_actor_id != actor_id or row.run_session_id != row.session_id:
            raise await _deny(AiChatDenialCode.access_denied)
        if (
            row.run_project_id != host.project_id
            or row.run_host_type != host.resource_type.value
            or row.run_host_id != host.resource_id
        ):
            raise await _deny(AiChatDenialCode.host_context_mismatch)

    # ── 正文与服务端哈希 ────────────────────────────────────────────────
    text = row.message_text or ""
    if not text.strip():
        raise await _deny(AiChatDenialCode.adopt_source_unusable)
    stored_hash = row.content_hash or ""
    if stored_hash != content_hash(text):
        # 缺哈希（存量行）与哈希不符（正文被直接改写）都无法证明来源，一律 fail-closed。
        logger.error(
            "采纳被拒：消息 %s 的服务端 content_hash 缺失或与正文不符（stored=%r）",
            message_id, stored_hash[:8],
        )
        raise await _deny(AiChatDenialCode.adopt_content_tampered)

    return AuthoritativeMessage(
        message_id=row.id,
        session_id=row.session_id,
        run_id=row.run_id,
        text=text,
        content_hash=stored_hash,
        model_used=row.model_used,
    )


# ---------------------------------------------------------------------------
# ② 幂等 + 写确认流 + 审计（全部在一个 SAVEPOINT 内）
# ---------------------------------------------------------------------------


async def adopt_message(
    db: AsyncSession,
    *,
    actor_id: UUID,
    host: AuthorizedHostContext,
    message_id: UUID,
    idempotency_key: UUID,
    target_cell: str | None = None,
    target_field: str | None = None,
    access: ResourceAccessResolver | None = None,
    request_id: str | None = None,
) -> AdoptOutcome:
    """把服务端权威 assistant 正文送入确认流。成功返回 :class:`AdoptOutcome`。

    :raises ExternalNotFound: 归属链任一段不成立（不可枚举 404）。
    :raises AdoptFailed: 日志写入 / 核验 / 审计 / commit 失败（已回滚）。
    """
    # 采纳能力已由 HostContextResolver → ResourceAccessResolver 判定过（Task 1 的
    # HOST_WRITE_ACTIONS + ai_generate/ai_confirm capability）。此处只断言"传进来的
    # 上下文确实是按 adopt 授权的"，防止调用方拿 read 上下文来写（不是第二次权限判定）。
    if not host.allows(AiChatAction.adopt):
        raise ExternalNotFound()
    if host.project_id is None:
        # 受限全局知识模式没有可回写的业务实例（项目工具关闭，Req 3.4）。
        raise ExternalNotFound()
    instance_id = coerce_uuid(host.resource_id)
    if instance_id is None:
        # 报表宿主的稳定 ID 是 report type 而非实例 UUID ⇒ 无采纳目标；
        # 绝不用 project_id 顶替 ``ai_content_log.instance_id``（Req 3.5）。
        logger.info("采纳被拒：宿主 %s 无实例 UUID 可作为回写目标", host.resource_type.value)
        raise ExternalNotFound()

    source = await load_authoritative_message(
        db,
        message_id=message_id,
        actor_id=actor_id,
        host=host,
        access=access,
        request_id=request_id,
    )

    savepoint = await db.begin_nested()
    released = False
    try:
        receipt, claimed = await claim_action_receipt(
            db,
            action_type=ActionReceiptType.adopt,
            actor_id=actor_id,
            session_id=source.session_id,
            idempotency_key=str(idempotency_key),
            source_message_hash=source.content_hash,
        )
        replay = _replay_of(receipt, claimed, source)
        if replay is not None:
            await savepoint.commit()
            released = True
            return replay

        result = await _write_content_log(
            db,
            source=source,
            host=host,
            actor_id=actor_id,
            instance_id=instance_id,
            target_cell=target_cell,
            target_field=target_field,
        )
        await settle_action_receipt(
            db,
            receipt,
            status=ActionReceiptStatus.succeeded,
            result_resource_id=result,
        )
        receipt_id = receipt.id
        await _write_adopt_audit(
            db,
            actor_id=actor_id,
            host=host,
            source=source,
            log_id=result,
            receipt_id=receipt_id,
            target_cell=target_cell,
            target_field=target_field,
        )
        await savepoint.commit()
        released = True
    except AdoptFailed:
        # 幂等冲突等已判定的失败：同样撤掉本次副作用后上抛。
        if not released:
            await savepoint.rollback()
        await _safe_rollback(db)
        raise
    except Exception as exc:  # noqa: BLE001 — 下游任一步失败都不得产生成功响应
        if not released:
            await savepoint.rollback()
        await _safe_rollback(db)
        logger.error(
            "采纳失败（已回滚，Req 8.7 fail-closed）message=%s host=%s/%s: %s: %s",
            message_id, host.resource_type.value, host.resource_id,
            type(exc).__name__, exc,
        )
        raise AdoptFailed(ADOPT_LOG_FAILED, str(exc)) from exc

    # commit 失败与日志写失败同处置：回滚 + adopt_log_failed（Req 8.7）。
    try:
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        await _safe_rollback(db)
        logger.error(
            "采纳 commit 失败（已回滚）message=%s: %s: %s",
            message_id, type(exc).__name__, exc,
        )
        raise AdoptFailed(ADOPT_LOG_FAILED, str(exc)) from exc

    return AdoptOutcome(
        ai_content_log_id=result,
        content_hash=source.content_hash,
        message_id=source.message_id,
        receipt_id=receipt_id,
        idempotent_replay=False,
    )


def _replay_of(
    receipt, claimed: bool, source: AuthoritativeMessage
) -> AdoptOutcome | None:
    """已存在收据时的处置：幂等重放 / 冲突 / 在途 / 允许重试。

    - 同一 key 指向**另一条**消息 → ``adopt_idempotency_conflict``（不返回旧结果）；
    - ``succeeded`` + 有 ``result_resource_id`` → 幂等重放同一 log ID；
    - ``pending`` → ``adopt_in_progress``（不写第二条确认流记录）；
    - ``failed`` → 重置为 pending，返回 None 让调用方重新走写入。
    """
    if claimed:
        return None
    if receipt.source_message_hash and receipt.source_message_hash != source.content_hash:
        raise AdoptFailed(
            ADOPT_IDEMPOTENCY_CONFLICT,
            "同一 idempotency key 对应不同的消息正文哈希",
        )
    if receipt.status == ActionReceiptStatus.succeeded.value:
        if receipt.result_resource_id is None:
            # 成功收据却没有 log ID = 数据不一致，绝不能据此返回"已进入确认流"。
            raise AdoptFailed(
                ADOPT_LOG_FAILED, "既有成功收据缺少 ai_content_log 引用"
            )
        return AdoptOutcome(
            ai_content_log_id=receipt.result_resource_id,
            content_hash=source.content_hash,
            message_id=source.message_id,
            receipt_id=receipt.id,
            idempotent_replay=True,
        )
    if receipt.status == ActionReceiptStatus.pending.value:
        raise AdoptFailed(ADOPT_IN_PROGRESS, "收据处于 pending")
    # failed → 允许重试（Req 8.9：失败收据可安全重试）
    receipt.status = ActionReceiptStatus.pending.value
    receipt.error_code = None
    receipt.source_message_hash = source.content_hash
    return None


async def _write_content_log(
    db: AsyncSession,
    *,
    source: AuthoritativeMessage,
    host: AuthorizedHostContext,
    actor_id: UUID,
    instance_id: UUID,
    target_cell: str | None,
    target_field: str | None,
) -> UUID:
    """写 ``ai_content_log``（pending）并核验其**真实存在**，否则抛 :class:`_LogWriteFailed`。

    🔴 ``wrap_ai_output_with_log`` 会把 ``ai_content_log.create`` 的异常吞成 WARNING
    并照常返回 dict（只是缺 ``ai_content_log_id``），所以这里**必须**看返回值：
      ① ``ai_content_log_id`` 非空 —— 不能读 ``id``（那是与数据库无关的临时 uuid4）；
      ② 该 ID 在同一事务内**查得到行** —— 防"返回了 ID 但行没落库"。
    """
    from app.services.wp_ai_service import wrap_ai_output_with_log

    result = await wrap_ai_output_with_log(
        # 权威正文：数据库里的服务端消息，客户端不参与。
        content=source.text,
        # 平台未记录 per-message 模型置信度；客户端提交的置信度不可信 ⇒ 显式留空，
        # 不用 0.85 之类的假值冒充（ai_content_log.confidence 可空）。
        confidence=None,
        # 模型标识同样取服务端记录（None 时由 wrap 回落 settings 默认）。
        source_model=source.model_used,
        target_cell=target_cell,
        target_field=target_field,
        db=db,
        project_id=host.project_id,
        user_id=actor_id,
        instance_type=host.resource_type.value,
        instance_id=instance_id,
    )
    log_id = coerce_uuid(result.get("ai_content_log_id"))
    if log_id is None:
        raise _LogWriteFailed(
            "wrap_ai_output_with_log 未返回 ai_content_log_id（日志写入被内部吞掉）"
        )
    exists = (
        await db.execute(sa.select(AiContentLog.id).where(AiContentLog.id == log_id))
    ).scalar_one_or_none()
    if exists is None:
        raise _LogWriteFailed(f"ai_content_log 行不存在：{log_id}")
    if result.get("confirm_action") != "pending":
        raise _LogWriteFailed(
            f"ai_content_log 未处于 pending：{result.get('confirm_action')!r}"
        )
    if result.get("content_hash") != source.content_hash:
        # wrap 对同一正文重算的 sha256 必须与消息哈希一致；不一致说明送进确认流的
        # 不是这条消息的正文。
        raise _LogWriteFailed("确认流记录的 content_hash 与服务端消息哈希不一致")
    return log_id


async def _write_adopt_audit(
    db: AsyncSession,
    *,
    actor_id: UUID,
    host: AuthorizedHostContext,
    source: AuthoritativeMessage,
    log_id: UUID,
    receipt_id: UUID,
    target_cell: str | None,
    target_field: str | None,
) -> None:
    """写平台哈希链审计：只存 ID 与 hash，不重复存正文（Req 8.9 / Property 32）。"""
    details: dict[str, object] = {
        "event_type": "ai_content_lifecycle",
        "action": "adopt",
        "ai_content_log_id": str(log_id),
        "message_id": str(source.message_id),
        "content_hash": source.content_hash,
        "session_id": str(source.session_id),
        "run_id": str(source.run_id) if source.run_id else None,
        "receipt_id": str(receipt_id),
        "host_type": host.resource_type.value,
        "host_id": host.resource_id,
        "target": target_cell or target_field,
    }
    if set(details) != ADOPT_AUDIT_DETAIL_KEYS:
        # 键集合漂移即视为审计不完整（Req 12.6：审计字段完整）。
        raise _LogWriteFailed(
            "采纳审计字段集合与 ADOPT_AUDIT_DETAIL_KEYS 不一致："
            f"多出 {sorted(set(details) - ADOPT_AUDIT_DETAIL_KEYS)}，"
            f"缺少 {sorted(ADOPT_AUDIT_DETAIL_KEYS - set(details))}"
        )
    serialized = json.dumps(details, ensure_ascii=False, default=str)
    if source.text[:24] and source.text[:24] in serialized:
        raise _LogWriteFailed("采纳审计载荷疑似携带消息正文（Req 12.7 禁止）")
    await append_audit_log(
        db,
        {
            "user_id": actor_id,
            "project_id": host.project_id,
            "action": ADOPT_AUDIT_ACTION,
            "resource_type": "ai_content_log",
            "resource_id": str(log_id),
            "details": details,
        },
    )


async def _safe_rollback(db: AsyncSession) -> None:
    """回滚整事务；回滚本身失败也不改变对外失败语义（只记 ERROR）。"""
    try:
        await db.rollback()
    except Exception as exc:  # noqa: BLE001
        logger.error("采纳失败路径 rollback 异常：%s: %s", type(exc).__name__, exc)


#: 宿主类型 → 资源类型（denial audit 用；与 ``access._RESOURCE_BY_HOST`` 同源语义）。
_RESOURCE_BY_HOST: dict[HostType, ResourceType] = {
    HostType.workpaper: ResourceType.workpaper,
    HostType.note: ResourceType.note,
    HostType.report: ResourceType.report,
    HostType.knowledge_doc: ResourceType.knowledge_doc,
    HostType.knowledge_folder: ResourceType.knowledge_folder,
    HostType.global_knowledge: ResourceType.global_knowledge,
}
