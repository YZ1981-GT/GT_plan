"""敏感操作一次性预览凭证 helper（Task 5，Design D4）

Feature: procedure-delegation-notification
需求：4.2-4.6（安全预览与一次消费）、3.7（applied 真实）
Design：D4（ProcedureOperationPreview 是敏感操作的一次性凭证）
Properties：P12（token 防篡改与越权）、P13（最多一次消费 + request_id 重试幂等）

本模块是 **裁剪 / reconcile / 委派 / 转派** 共用的 server-side 一次性预览凭证核心：

- ``create_preview``：显式写命令。绑定 actor user、project、operation、**规范化 request hash**、
  target lock/assignment versions、active membership snapshot（含 hash）、scheme revision、TTL。
- ``consume_and_apply``：apply 在事务内 ``SELECT ... FOR UPDATE`` preview，逐项校验后
  才调用领域 ``apply_fn`` 并写入 result；置 ``consumed_at/consumed_request_id``。
  - 任意 request hash / actor / project / operation / scheme revision / membership snapshot /
    TTL 的单点变化 → 409 且零副作用（P12）。
  - 并发消费者对同一 preview 最多一个成功执行领域变更；其余 409（P13）。
  - 相同 ``request_id`` 的网络重试只返回已保存 result，**不再次执行** 领域变更（P13）。

约定：service 只 flush 不 commit；router 显式 commit。canonical JSON + SHA-256 复用 importer 的
规范化原语，保证跨机器稳定。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procedure_models import ProcedureOperationPreview
from app.services.procedure_definition_importer import canonical_json, sha256_hex

logger = logging.getLogger(__name__)

# 默认 TTL：10 分钟（Design D4 preview 短生命周期）
DEFAULT_PREVIEW_TTL_SECONDS = 600


def canonical_request_hash(payload: dict) -> str:
    """规范化 request payload 的 SHA-256（canonical JSON，跨机器稳定）。"""
    return sha256_hex(canonical_json(payload or {}))


def membership_snapshot_hash(snapshot: dict | list) -> str:
    """active membership 快照的 SHA-256（canonical JSON）。"""
    return sha256_hex(canonical_json(snapshot if snapshot is not None else {}))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime) -> datetime:
    """把可能 naive 的 timestamptz 归一为 aware（UTC），便于比较。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def create_preview(
    db: AsyncSession,
    *,
    actor_user_id: UUID,
    project_id: UUID,
    operation: str,
    request_payload: dict,
    target_versions: dict,
    membership_snapshot: dict | list,
    scheme_revision: str | None = None,
    ttl_seconds: int = DEFAULT_PREVIEW_TTL_SECONDS,
) -> ProcedureOperationPreview:
    """创建 server-side 一次性预览凭证（显式写命令，只 flush）。

    - ``request_payload``：规范化后计算 request_hash；apply 时以同一 payload 重算比对（防篡改）。
    - ``target_versions``：如 ``{task_id: lock_version}``；apply 时由 ``apply_fn`` 复核（版本变化 409）。
    - ``membership_snapshot``：active 成员/委派资格快照；apply 时重算比对（成员变化 409）。
    - ``scheme_revision``：方案/目标 revision（如 reconcile 的目标 definition revision）。
    """
    preview = ProcedureOperationPreview(
        actor_user_id=actor_user_id,
        project_id=project_id,
        operation=operation,
        request_hash=canonical_request_hash(request_payload),
        request_payload_snapshot=request_payload or {},
        target_versions=target_versions or {},
        membership_snapshot=membership_snapshot if membership_snapshot is not None else {},
        membership_snapshot_hash=membership_snapshot_hash(membership_snapshot),
        scheme_revision=scheme_revision,
        expires_at=_utcnow() + timedelta(seconds=ttl_seconds),
    )
    db.add(preview)
    await db.flush()
    return preview


async def consume_and_apply(
    db: AsyncSession,
    *,
    preview_id: UUID,
    actor_user_id: UUID,
    project_id: UUID,
    operation: str,
    request_payload: dict,
    request_id: str,
    current_membership_snapshot: dict | list,
    apply_fn: Callable[[AsyncSession, ProcedureOperationPreview], Awaitable[dict]],
) -> dict:
    """一次性消费 preview 并执行领域变更（事务内 SELECT FOR UPDATE + 逐项校验）。

    校验顺序（任一失败 → 409 且零副作用；相同 request_id 重试 → 幂等返回已存 result）：
      1. preview 存在。
      2. 已消费：若 ``consumed_request_id == request_id`` → 幂等返回旧 result；否则 409。
      3. actor / project / operation 匹配。
      4. 未过期（TTL）。
      5. request payload 重算 hash == 存储 hash（防篡改）。
      6. current membership snapshot hash == 存储 hash（成员变化 409）。
      7. 通过后调用 ``apply_fn(db, preview)``；其内部复核 target_versions（版本变化 409）。
      8. 置 consumed_at / consumed_request_id / result。

    调用方需在成功后 commit；抛 HTTPException 时不应 commit（保证零副作用）。
    """
    if not request_id:
        raise HTTPException(status_code=422, detail="缺少 request_id")

    # 行锁：并发消费最多一个成功
    preview = (
        await db.execute(
            sa.select(ProcedureOperationPreview)
            .where(ProcedureOperationPreview.id == preview_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if preview is None:
        raise HTTPException(status_code=404, detail="预览凭证不存在")

    # 已消费：request_id 相同 → 幂等；否则 409
    if preview.consumed_at is not None:
        if preview.consumed_request_id == request_id:
            return preview.result or {}
        raise HTTPException(status_code=409, detail="预览凭证已被消费")

    # actor / project / operation 越权或错配
    if (
        preview.actor_user_id != actor_user_id
        or preview.project_id != project_id
        or preview.operation != operation
    ):
        raise HTTPException(status_code=409, detail="预览凭证与当前操作不匹配")

    # TTL
    if _as_aware(preview.expires_at) <= _utcnow():
        raise HTTPException(status_code=409, detail="预览凭证已过期")

    # 防篡改：request payload 重算 hash
    if canonical_request_hash(request_payload) != preview.request_hash:
        raise HTTPException(status_code=409, detail="预览请求已被篡改")

    # 成员资格变化
    if membership_snapshot_hash(current_membership_snapshot) != preview.membership_snapshot_hash:
        raise HTTPException(status_code=409, detail="项目成员资格已变化，请重新预览")

    # 领域变更（apply_fn 内部复核 target_versions；抛 409 时保持零副作用）
    result = await apply_fn(db, preview)

    preview.consumed_at = _utcnow()
    preview.consumed_request_id = request_id
    preview.result = result
    await db.flush()
    return result
