"""EvidenceGovernanceFacade — 治理层唯一写入入口（Task 3.1, Wave 2）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R1, R3, R4, R5, R8, R12
Design: §3.1 信任边界, §3.2 统一 Facade 与服务职责, §7.1 command-root/transition
Properties: P1 (项目隔离), P25 (command-root 唯一 + 同事务)

``EvidenceGovernanceFacade`` 是所有新写入与兼容旧路由委托的 **唯一入口**，负责：
ActorContext、scope（``ProjectYearScopeGuard``）、capability（``CapabilityGuard``）、
幂等键、**短事务**、command-root 审计与 outbox。

事务边界铁律（design §3.1 第 6 条 / §3.2）：**业务变化、command-root 审计和 outbox 同事务**。
facade 管理短事务并 ``commit``；底层服务只 ``flush``；router **不提交** 业务事务。外部 I/O
（Paperless/OCR/检索/发布）不占长事务——发布经 outbox 由 worker 异步完成。

命令语义（P25）：
- 幂等键决定 command-root 唯一；成功、拒绝、重放都恰好一个 root。
- 成功：业务写 + success transition + outbox 原子提交。
- 拒绝（业务抛 ``EvidenceGovernanceError``）：回滚业务写（savepoint），保留 root + reject
  transition 并提交（目标零变化，脱敏原因码）。
- 重放（root 已 finalize）：不重跑业务、不重复 root/outbox，返回 replayed 标记。
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.evidence_governance.capability_guard import CapabilityGuard
from app.services.evidence_governance.command_audit import CommandAuditService
from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    EvidenceErrorCode,
    EvidenceGovernanceError,
)
from app.services.evidence_governance.outbox import (
    InboxService,
    OutboxService,
    derive_event_id,
)
from app.services.evidence_governance.scope_guard import ObjectScope, ProjectYearScopeGuard


@dataclass
class OutboxEvent:
    """待入队的 outbox 事件。``event_id`` 缺省时由 (root, type, seq) 确定性派生。"""

    event_type: str
    payload: dict
    event_id: str | None = None


@dataclass
class CommandRequest:
    """一次敏感命令的输入。客户端提供的 scope 仅作请求意图，权威 scope 以 DB 为准。"""

    command_type: str
    idempotency_key: str
    actor: ActorContext
    actor_role: str
    project_id: uuid.UUID | None = None
    audit_year: int | None = None
    capability: str | None = None
    # 当命令作用于既有对象时，提供 object_type/object_id 触发权威归属重新解析（P1）。
    object_type: str | None = None
    object_id: uuid.UUID | str | None = None
    trace_id: str | None = None


@dataclass
class CommandResult:
    command_root_id: uuid.UUID
    replayed: bool
    result: Any = None
    object_scope: ObjectScope | None = None


@dataclass
class CommandTxn:
    """交给业务回调的短事务上下文。业务只 ``flush``，绝不 ``commit``。"""

    db: AsyncSession
    command_root_id: uuid.UUID
    actor: ActorContext
    project_id: uuid.UUID
    audit_year: int | None
    object_scope: ObjectScope | None
    _outbox: OutboxService
    _audit: CommandAuditService
    _events: list[OutboxEvent] = field(default_factory=list)
    _seq: int = 0

    async def enqueue_outbox(
        self, event_type: str, payload: dict, *, event_id: str | None = None
    ) -> bool:
        """在同一事务内幂等入队 outbox 事件（发布由 worker 异步完成）。"""
        eid = event_id or derive_event_id(
            command_root_id=self.command_root_id, event_type=event_type, seq=self._seq
        )
        self._seq += 1
        return await self._outbox.enqueue(
            project_id=self.project_id,
            audit_year=self.audit_year,
            event_id=eid,
            event_type=event_type,
            payload=payload,
            actor=self.actor,
            command_root_id=self.command_root_id,
        )

    async def record_transition(
        self,
        *,
        transition_type: str,
        from_state: str | None = None,
        to_state: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """追加业务状态迁移审计（脱敏；同事务）。"""
        await self._audit.record_transition(
            command_root_id=self.command_root_id,
            transition_type=transition_type,
            actor=self.actor,
            from_state=from_state,
            to_state=to_state,
            metadata=metadata,
        )


class EvidenceGovernanceFacade:
    """治理层唯一写入入口（scope + capability + 短事务 + command-root + outbox）。"""

    def __init__(
        self,
        db: AsyncSession,
        *,
        scope_guard: ProjectYearScopeGuard | None = None,
        capability_guard: CapabilityGuard | None = None,
    ) -> None:
        self._db = db
        self.scope_guard = scope_guard or ProjectYearScopeGuard(db)
        self.capability_guard = capability_guard or CapabilityGuard()
        self.audit = CommandAuditService(db)
        self.outbox = OutboxService(db)
        self.inbox = InboxService(db)

    async def execute(
        self,
        request: CommandRequest,
        business_fn: Callable[[CommandTxn], Awaitable[Any]],
    ) -> CommandResult:
        """执行一次敏感命令（业务变化 + command-root + outbox 同事务提交）。

        guard（capability + scope）在任何业务写/字节 IO 之前完成；拒绝与不存在使用同一
        脱敏错误。commit 由本方法负责，业务回调只 flush，router 不 commit。
        """
        # 1) capability（后端权威；admin 不特权跳过）
        if request.capability:
            self.capability_guard.authorize(
                request.actor_role, request.capability, actor=request.actor
            )

        # 2) scope（权威归属从 DB 重新解析；scope-first，先于业务 IO）
        object_scope: ObjectScope | None = None
        if request.object_type and request.object_id is not None:
            object_scope = await self.scope_guard.authorize_object(
                actor_role=request.actor_role,
                actor=request.actor,
                object_type=request.object_type,
                object_id=request.object_id,
                requested_project_id=request.project_id,
                requested_year=request.audit_year,
            )
            project_id = object_scope.project_id
            audit_year = (
                object_scope.audit_year
                if object_scope.audit_year is not None
                else request.audit_year
            )
        else:
            if request.project_id is None:
                raise EvidenceGovernanceError(
                    EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                    "project scope required",
                )
            await self.scope_guard.authorize_scope(
                actor_role=request.actor_role,
                actor=request.actor,
                project_id=request.project_id,
                audit_year=request.audit_year,
            )
            project_id = request.project_id
            audit_year = request.audit_year

        # 3) command-root 幂等 upsert（P25）
        root, created = await self.audit.upsert_command_root(
            command_type=request.command_type,
            idempotency_key=request.idempotency_key,
            project_id=project_id,
            audit_year=audit_year,
            actor=request.actor,
            trace_id=request.trace_id,
        )

        # 捕获 root.id 到本地：commit/rollback 会 expire ORM 属性，之后再访问 root.id 会触发
        # 同步惰性加载（异步上下文 MissingGreenlet）。此处 root 刚 upsert/回读，id 已就绪无 IO。
        root_id = root.id

        # 重放：root 已 finalize → 不重跑业务、不重复 root/outbox
        if not created and root.result is not None:
            await self._db.rollback()
            return CommandResult(
                command_root_id=root_id, replayed=True, object_scope=object_scope
            )

        txn = CommandTxn(
            db=self._db,
            command_root_id=root_id,
            actor=request.actor,
            project_id=project_id,
            audit_year=audit_year,
            object_scope=object_scope,
            _outbox=self.outbox,
            _audit=self.audit,
        )

        # 4) 业务（savepoint 隔离；只 flush）
        sp = await self._db.begin_nested()
        try:
            result = await business_fn(txn)
            await sp.commit()
        except EvidenceGovernanceError as exc:
            # 拒绝：回滚业务写，保留 root + reject transition 并提交（目标零变化）
            await sp.rollback()
            await self.audit.record_transition(
                command_root_id=root.id,
                transition_type="reject",
                actor=request.actor,
                to_state="rejected",
                metadata={"reason_code": exc.error_code.value},
            )
            await self.audit.finalize_root(
                root, result="rejected", reason_code=exc.error_code.value
            )
            await self._db.commit()  # root.id 已捕获为 root_id，commit 后不再访问 root 属性
            raise
        except Exception:
            await sp.rollback()
            await self._db.rollback()
            raise

        # 5) success transition + finalize + commit（业务 + 审计 + outbox 同事务）
        await self.audit.record_transition(
            command_root_id=root.id,
            transition_type="complete",
            actor=request.actor,
            to_state="success",
        )
        await self.audit.finalize_root(root, result="success")
        await self._db.commit()

        return CommandResult(
            command_root_id=root_id,
            replayed=False,
            result=result,
            object_scope=object_scope,
        )
