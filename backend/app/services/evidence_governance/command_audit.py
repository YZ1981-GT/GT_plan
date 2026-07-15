"""Command-root 审计 + transition + 脱敏 + 有界退避（Task 3.1, Wave 2）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R12
Design: §7.1 Command-root 唯一与 transition 多条
Properties: P25 (审计事件覆盖：每敏感命令 + 幂等键恰一个脱敏 command-root，零到多条 transition)

- 每个敏感命令用 ``(command_type, idempotency_key, project_id, audit_year)`` upsert **恰一个**
  ``EvidenceAuditCommandRoot``（``ON CONFLICT DO NOTHING`` + 回读）；命令成功、拒绝或重放都
  不多建 root（P25）。
- ``record_transition`` 写零到多条 ``EvidenceAuditTransition``（append-only），关联同一 root。
- 审计脱敏（``redact_audit_metadata``）：剥离凭据、绝对路径、附件/OCR 原文、完整 prompt/answer。
- 有界抖动退避（``compute_backoff`` / ``next_attempt_at``）供 outbox/inbox worker 复用。

不 commit：本 service 只 ``flush``（facade 管理短事务边界，design §3.2）。
"""

from __future__ import annotations

import random
import re
import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence_governance_models import (
    EvidenceAuditCommandRoot,
    EvidenceAuditTransition,
)
from app.services.evidence_governance.frozen_contracts import ActorContext

# ---------------------------------------------------------------------------
# 脱敏（design §7.1：日志仅含 ID/scope/版本/hash/动作/结果/原因码/trace）
# ---------------------------------------------------------------------------

#: 键名子串命中即整体丢弃（凭据/原文/绝对路径类）。
_REDACT_KEY_SUBSTRINGS: tuple[str, ...] = (
    "password", "passwd", "secret", "token", "credential", "authorization",
    "api_key", "apikey", "cookie", "session_id",
    "file_path", "filepath", "abs_path", "absolute_path", "storage_key",
    "raw_text", "raw_content", "content_bytes", "file_bytes", "payload_bytes",
    "prompt", "answer", "excerpt",
)

#: 绝对路径样式（POSIX / Windows 盘符）。
_ABS_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|[\\/]{1,2}[^\s])")

_REDACTED = "[redacted]"
_MAX_STR = 200


def redact_audit_metadata(meta: dict | None) -> dict:
    """返回脱敏后的审计元数据（不修改入参）。

    - 键名命中 ``_REDACT_KEY_SUBSTRINGS`` → 丢弃。
    - 字符串值形似绝对路径 → 替换为 ``[redacted]``；超长截断。
    - 递归处理嵌套 dict/list。
    """
    if not meta:
        return {}
    return _redact_value(meta)  # type: ignore[return-value]


def _redact_value(value):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            key = str(k)
            if any(sub in key.lower() for sub in _REDACT_KEY_SUBSTRINGS):
                out[key] = _REDACTED
            else:
                out[key] = _redact_value(v)
        return out
    if isinstance(value, (list, tuple)):
        return [_redact_value(v) for v in value]
    if isinstance(value, str):
        if _ABS_PATH_RE.match(value):
            return _REDACTED
        return value if len(value) <= _MAX_STR else value[:_MAX_STR] + "…"
    return value


# ---------------------------------------------------------------------------
# 有界抖动退避（design §5.4/§7.1；R15）
# ---------------------------------------------------------------------------

def compute_backoff(
    attempt: int,
    *,
    base_seconds: float = 1.0,
    cap_seconds: float = 300.0,
    jitter_ratio: float = 0.25,
    rng: random.Random | None = None,
) -> float:
    """指数退避 + 有界 + 抖动，返回秒数（≥0，≤cap）。

    ``attempt`` 从 1 起计。``delay = min(cap, base*2^(attempt-1))``，叠加
    ``±jitter_ratio`` 均匀抖动，结果夹在 ``[0, cap]``。
    """
    if attempt < 1:
        attempt = 1
    raw = base_seconds * (2 ** (attempt - 1))
    delay = min(cap_seconds, raw)
    r = rng or random
    jitter = delay * jitter_ratio * (2 * r.random() - 1)
    return max(0.0, min(cap_seconds, delay + jitter))


def next_attempt_at(
    attempt: int,
    *,
    now: datetime | None = None,
    **backoff_kwargs,
) -> datetime:
    """下一次尝试时间戳（timezone-aware UTC）。"""
    base = now or datetime.now(timezone.utc)
    return base + timedelta(seconds=compute_backoff(attempt, **backoff_kwargs))


# ---------------------------------------------------------------------------
# CommandAuditService（root upsert + transition；只 flush）
# ---------------------------------------------------------------------------

def _actor_columns(actor: ActorContext) -> dict:
    return {
        "actor_type": actor.actor_type.value,
        "actor_user_id": actor.actor_user_id,
        "actor_service_identity_id": actor.actor_service_identity_id,
    }


class CommandAuditService:
    """command-root 唯一 upsert + transition 追加（P25）。只 flush，不 commit。"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def upsert_command_root(
        self,
        *,
        command_type: str,
        idempotency_key: str,
        project_id: uuid.UUID,
        audit_year: int | None,
        actor: ActorContext,
        trace_id: str | None = None,
    ) -> tuple[EvidenceAuditCommandRoot, bool]:
        """按 ``(command_type, idempotency_key, project_id, audit_year)`` 幂等 upsert。

        返回 ``(root, created)``；``created=False`` 表示命中既有 root（重放/并发）。
        执行/拒绝/重放都不多建 root（P25）。
        """
        vals = {
            "id": uuid.uuid4(),
            "command_type": command_type,
            "idempotency_key": idempotency_key,
            "project_id": project_id,
            "audit_year": audit_year,
            "trace_id": trace_id,
            **_actor_columns(actor),
        }
        # ON CONFLICT DO NOTHING（非 NULL year 由 uq_audit_command_root 兜底并发）。
        ins = (
            pg_insert(EvidenceAuditCommandRoot.__table__)
            .values(**vals)
            .on_conflict_do_nothing(
                index_elements=["command_type", "idempotency_key", "project_id", "audit_year"]
            )
            .returning(EvidenceAuditCommandRoot.__table__.c.id)
        )
        res = await self._db.execute(ins)
        inserted_id = res.scalar()
        await self._db.flush()

        if inserted_id is not None:
            root = await self._db.get(EvidenceAuditCommandRoot, inserted_id)
            return root, True  # type: ignore[return-value]

        # 命中既有（含 NULL year：ON CONFLICT 不触发，回读用 IS NOT DISTINCT FROM）。
        existing = await self._find_existing(
            command_type, idempotency_key, project_id, audit_year
        )
        if existing is None:
            # 极小概率：NULL-year 并发下两行都插入。回退再次 insert 命中的第一条。
            existing = await self._find_existing(
                command_type, idempotency_key, project_id, audit_year
            )
        return existing, False  # type: ignore[return-value]

    async def _find_existing(
        self,
        command_type: str,
        idempotency_key: str,
        project_id: uuid.UUID,
        audit_year: int | None,
    ) -> EvidenceAuditCommandRoot | None:
        t = EvidenceAuditCommandRoot
        stmt = (
            sa.select(t)
            .where(
                t.command_type == command_type,
                t.idempotency_key == idempotency_key,
                t.project_id == project_id,
                t.audit_year.is_not_distinct_from(audit_year),
            )
            .order_by(t.created_at.asc())
            .limit(1)
        )
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def finalize_root(
        self,
        root: EvidenceAuditCommandRoot,
        *,
        result: str,
        reason_code: str | None = None,
    ) -> None:
        """设置 root 的 result/reason_code（success/rejected/replayed）。只 flush。"""
        root.result = result
        if reason_code is not None:
            root.reason_code = reason_code
        await self._db.flush()

    async def record_transition(
        self,
        *,
        command_root_id: uuid.UUID,
        transition_type: str,
        actor: ActorContext,
        from_state: str | None = None,
        to_state: str | None = None,
        metadata: dict | None = None,
    ) -> EvidenceAuditTransition:
        """追加一条脱敏 transition（append-only）。只 flush。"""
        row = EvidenceAuditTransition(
            command_root_id=command_root_id,
            transition_type=transition_type,
            from_state=from_state,
            to_state=to_state,
            metadata_redacted=redact_audit_metadata(metadata),
            **_actor_columns(actor),
        )
        self._db.add(row)
        await self._db.flush()
        return row
