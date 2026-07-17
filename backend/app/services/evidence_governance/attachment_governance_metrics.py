"""附件治理低基数积压指标 — 计算 + 记录到既有 observability 收集器（P2-补）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R8, R12, R15 · Design: §9.3 可观测性(低基数指标)

本模块 **不新建平行指标系统**：它复用 :func:`get_evidence_metrics` 单例，把四项附件治理
积压量写成命名点 gauge（见 ``ATTACHMENT_GOVERNANCE_GAUGES``），经既有
``/api/evidence-governance/metrics`` 的 ``named_gauges`` 段暴露：

- ``attachment_quarantine_buffer_bytes``     —— 隔离/暂存缓冲在途字节（``quarantine_store.buffered_bytes()``）。
- ``attachment_quarantine_handle_count``     —— staged+quarantined 尚未 purged 的 QuarantineHandle 数。
- ``attachment_orphaned_staged_count``       —— 过 TTL 仍未 available 的 staged/quarantined handle 数
  （**与 P1-③ reaper 的扫描口径完全一致**：``handle_state IN ('staged','quarantined') AND created_at < cutoff``，
  故指标与 reaper 会处理的积压相互吻合）。
- ``attachment_version_model_drift_count``   —— 同时拥有 legacy version 链（``attachments.version``）与治理
  ``attachment_versions`` 链、但二者不一致（legacy 版本号 ≠ 治理 ``MAX(version_no)``）的附件数，
  暴露 P1-④ 的双模型分叉。

低基数铁律：全部为进程级 **单一命名点值**，无 per-attachment / 路径 / 项目 ID 标签。可选
``project_id`` 只收窄计算范围，不进入指标标签。计算为纯只读 SQL（不写库），配套 callable
供调度器/worker 周期调用——**不在此接管 live cron**（对齐 reaper 的 callable 约定）。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.evidence_governance.observability import (
    EvidenceGovernanceMetrics,
    get_evidence_metrics,
)

# 与 gateway / reaper / DB CHECK 对齐的状态命名（复用而非另起）。
_ACTIVE_HANDLE_STATES = ("staged", "quarantined")

GAUGE_BUFFER_BYTES = "attachment_quarantine_buffer_bytes"
GAUGE_HANDLE_COUNT = "attachment_quarantine_handle_count"
GAUGE_ORPHANED_STAGED = "attachment_orphaned_staged_count"
GAUGE_VERSION_DRIFT = "attachment_version_model_drift_count"


async def count_active_quarantine_handles(
    db: AsyncSession, *, project_id: uuid.UUID | None = None
) -> int:
    """staged+quarantined 尚未 purged 的 QuarantineHandle 数（无 TTL 门槛）。"""
    sql = (
        "SELECT COUNT(*) FROM evidence_quarantine_handles "
        "WHERE handle_state IN ('staged','quarantined')"
    )
    params: dict = {}
    if project_id is not None:
        sql += " AND project_id = :pid"
        params["pid"] = str(project_id)
    return int((await db.execute(sa.text(sql), params)).scalar() or 0)


async def count_orphaned_staged_handles(
    db: AsyncSession,
    *,
    cutoff: datetime,
    project_id: uuid.UUID | None = None,
) -> int:
    """过 TTL 仍未 finalize 的 staged/quarantined handle 数。

    口径与 :func:`app.services.evidence_governance.quarantine_reaper.reap_stale_quarantine`
    的扫描 SQL 完全一致（``handle_state IN ('staged','quarantined') AND created_at < cutoff``），
    确保「指标显示的积压」正是「reaper 会清理的对象」。
    """
    sql = (
        "SELECT COUNT(*) FROM evidence_quarantine_handles "
        "WHERE handle_state IN ('staged','quarantined') AND created_at < :cutoff"
    )
    params: dict = {"cutoff": cutoff}
    if project_id is not None:
        sql += " AND project_id = :pid"
        params["pid"] = str(project_id)
    return int((await db.execute(sa.text(sql), params)).scalar() or 0)


async def count_version_model_drift(
    db: AsyncSession, *, project_id: uuid.UUID | None = None
) -> int:
    """同时有 legacy version 链与治理 AttachmentVersion 链、但版本号不一致的附件数（P1-④）。

    legacy 链 = ``attachments.version``（AT-3 行式版本，V014）；治理链 = ``attachment_versions``
    独立不可变表。只统计 **两条链都存在** 的附件（存在治理版本行），当 legacy ``version`` 与
    治理 ``MAX(version_no)`` 不一致时计入 —— 即双模型分叉的可观测信号。
    """
    sql = (
        "SELECT COUNT(*) FROM attachments a "
        "JOIN ("
        "  SELECT attachment_id, MAX(version_no) AS max_vn "
        "  FROM attachment_versions GROUP BY attachment_id"
        ") av ON av.attachment_id = a.id "
        "WHERE a.is_deleted = false AND a.version IS NOT NULL "
        "AND a.version <> av.max_vn"
    )
    params: dict = {}
    if project_id is not None:
        sql += " AND a.project_id = :pid"
        params["pid"] = str(project_id)
    return int((await db.execute(sa.text(sql), params)).scalar() or 0)


async def record_attachment_governance_metrics(
    db: AsyncSession,
    *,
    quarantine_store=None,
    ttl_seconds: int | None = None,
    now: datetime | None = None,
    project_id: uuid.UUID | None = None,
    metrics: EvidenceGovernanceMetrics | None = None,
) -> dict[str, float]:
    """计算四项附件治理积压指标并记录为命名点 gauge；返回 ``{name: value}`` 快照。

    参数：
      - ``quarantine_store``：可选，暴露 ``buffered_bytes()`` 的隔离区（durable/内存）。缺省时
        跳过 buffer_bytes gauge（不臆造 0，交由 store 持有方注入）。
      - ``ttl_seconds``：孤儿 staged 判定的 TTL（缺省取 ``settings.ATTACHMENT_QUARANTINE_TTL_SECONDS``，
        与 reaper 一致）。
      - ``now``：注入当前时刻（测试用；默认 UTC now）。
      - ``project_id``：可选，仅统计指定项目（不进入指标标签，保持低基数）。
      - ``metrics``：可选，注入指标收集器（缺省用进程单例 :func:`get_evidence_metrics`）。

    只读 SQL、不写库；供调度器/worker 周期调用（不接管 live cron）。
    """
    if ttl_seconds is None:
        from app.core.config import settings

        ttl_seconds = int(getattr(settings, "ATTACHMENT_QUARANTINE_TTL_SECONDS", 86400))
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=max(0, ttl_seconds))
    collector = metrics or get_evidence_metrics()

    snapshot: dict[str, float] = {}

    handle_count = await count_active_quarantine_handles(db, project_id=project_id)
    collector.set_named_gauge(GAUGE_HANDLE_COUNT, handle_count)
    snapshot[GAUGE_HANDLE_COUNT] = float(handle_count)

    orphaned = await count_orphaned_staged_handles(db, cutoff=cutoff, project_id=project_id)
    collector.set_named_gauge(GAUGE_ORPHANED_STAGED, orphaned)
    snapshot[GAUGE_ORPHANED_STAGED] = float(orphaned)

    drift = await count_version_model_drift(db, project_id=project_id)
    collector.set_named_gauge(GAUGE_VERSION_DRIFT, drift)
    snapshot[GAUGE_VERSION_DRIFT] = float(drift)

    if quarantine_store is not None and hasattr(quarantine_store, "buffered_bytes"):
        buffered = int(quarantine_store.buffered_bytes())
        collector.set_named_gauge(GAUGE_BUFFER_BYTES, buffered)
        snapshot[GAUGE_BUFFER_BYTES] = float(buffered)

    return snapshot


__all__ = [
    "GAUGE_BUFFER_BYTES",
    "GAUGE_HANDLE_COUNT",
    "GAUGE_ORPHANED_STAGED",
    "GAUGE_VERSION_DRIFT",
    "count_active_quarantine_handles",
    "count_orphaned_staged_handles",
    "count_version_model_drift",
    "record_attachment_governance_metrics",
]
