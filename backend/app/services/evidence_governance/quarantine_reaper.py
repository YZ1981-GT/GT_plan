"""Quarantine Reaper — 清理未 finalize 的 staged/quarantined 隔离内容（崩溃安全）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R1.2, R2 · Design: §4.0 (UploadAttempt/失败审计/隔离区), §5.1 (异步 finalize)

背景（durable quarantine 收尾）：202 异步 finalize 把 staged 内容交给 worker；若 worker 从未
完成（进程崩溃 / 存储长期降级 / 上传中途夭折），会遗留 ``QuarantineHandle(staged)`` +
orphaned ``Attachment(pending)`` / ``AttachmentVersion(staged)`` 与磁盘上的 durable blob——
永不 finalize、永不 crypto-erase。本 reaper 是 **可被调度器/worker 调用的 callable**（不接管
live cron），周期性：

1. 找 ``handle_state ∈ {staged, quarantined}`` 且 ``created_at`` 早于 TTL、其上传从未到达
   ``available`` 的 ``QuarantineHandle``；
2. **加密擦除** 其 durable blob（``store.purge(key, crypto_erase=True)``——先覆写字节再删除）；
3. 把 handle 标记 ``purged``（``purged_at`` 置位，``is_publicly_readable`` 恒 false）；
4. **对账** 对应的 orphaned staged ``Attachment``/``AttachmentVersion``——按既有模型状态标记
   ``inactive``（不发明新终态；不物理删除治理行）。

铁律：Legal Hold 闭包内 或 被活动依赖/EvidenceRef 引用的 handle **整体跳过**（既不擦除也不对账），
绝不破坏受 hold 或被引用的证据；但这与 "恶意内容绝不成为可访问文件" 不冲突——恶意内容在
quarantine 时已即刻加密擦除，本 reaper 只是补记其终态。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

# 与 gateway / DB CHECK 对齐的状态命名（复用而非另起）。
_HANDLE_STAGED = "staged"
_HANDLE_QUARANTINED = "quarantined"
_HANDLE_PURGED = "purged"

_ATTACHMENT_PENDING = "pending"
_ATTACHMENT_INACTIVE = "inactive"
_VERSION_STAGED = "staged"
_VERSION_INACTIVE = "inactive"

_STAGED_LOCATOR_PREFIX = "staged://"


@dataclass
class QuarantineReapReport:
    """一次 reap 的结果统计（供调度器/告警消费）。"""

    scanned: int = 0
    purged: int = 0
    attachments_inactivated: int = 0
    versions_inactivated: int = 0
    skipped_legal_hold: int = 0
    skipped_referenced: int = 0
    purged_handle_ids: list[uuid.UUID] = field(default_factory=list)
    skipped_handle_ids: list[uuid.UUID] = field(default_factory=list)


async def _is_under_active_hold(
    db: AsyncSession, *, project_id, node_type: str, node_id: str
) -> bool:
    """node 是否落在某个活动 Legal Hold 的固化范围内（对齐 RetentionLegalHoldService）。"""
    row = await db.execute(
        sa.text(
            "SELECT 1 FROM legal_hold_scopes lhs "
            "JOIN legal_holds lh ON lh.id = lhs.legal_hold_id "
            "WHERE lhs.project_id = :pid AND lhs.node_type = :nt "
            "AND lhs.node_id = :nid AND lhs.is_active = true "
            "AND lh.state = 'active' LIMIT 1"
        ),
        {"pid": str(project_id), "nt": node_type, "nid": node_id},
    )
    return row.scalar() is not None


async def _is_referenced(
    db: AsyncSession, *, project_id, attachment_id, version_ids: list[str]
) -> bool:
    """attachment / 其 version 是否被活动依赖边或活动 EvidenceRef 引用（防止误擦被引用证据）。"""
    aid = str(attachment_id)
    dep = await db.execute(
        sa.text(
            "SELECT 1 FROM evidence_dependencies "
            "WHERE project_id = :pid AND status = 'active' AND ("
            "  (source_type = 'attachment' AND source_id = :aid) "
            "  OR (target_type = 'attachment' AND target_id = :aid)"
            ") LIMIT 1"
        ),
        {"pid": str(project_id), "aid": aid},
    )
    if dep.scalar() is not None:
        return True
    ref = await db.execute(
        sa.text(
            "SELECT 1 FROM evidence_refs "
            "WHERE project_id = :pid AND status = 'active' AND ("
            "  (evidence_type = 'attachment' AND evidence_id = :aid)"
            + (" OR attachment_version_id::text = ANY(:vids)" if version_ids else "")
            + ") LIMIT 1"
        ),
        (
            {"pid": str(project_id), "aid": aid, "vids": version_ids}
            if version_ids
            else {"pid": str(project_id), "aid": aid}
        ),
    )
    return ref.scalar() is not None


async def reap_stale_quarantine(
    db: AsyncSession,
    quarantine_store,
    *,
    ttl_seconds: int | None = None,
    now: datetime | None = None,
    project_id: uuid.UUID | None = None,
    limit: int = 500,
    commit: bool = True,
) -> QuarantineReapReport:
    """清理超过 TTL 且从未 finalize 的 staged/quarantined 隔离内容（R1.2/§4.0/§5.1）。

    参数：
      - ``quarantine_store``：durable/内存隔离区（需 ``purge(key, crypto_erase=...)`` / ``exists``）。
      - ``ttl_seconds``：存活上限（默认取 ``settings.ATTACHMENT_QUARANTINE_TTL_SECONDS``）。
      - ``now``：注入当前时刻（测试用；默认 UTC now）。
      - ``project_id``：可选，仅清理指定项目。
      - ``limit``：单次处理上限（避免长事务）。
      - ``commit``：worker 调用默认 True（自持事务）；测试可传 False 由调用方管理。

    对每个过期 handle：
      * Legal Hold 闭包内 或 被活动引用 → **整体跳过**（既不擦除也不对账）；
      * 否则加密擦除 durable blob → handle 置 ``purged``（``purged_at`` 置位）→ 对账 orphaned
        ``Attachment(pending)→inactive`` / ``AttachmentVersion(staged)→inactive``。

    永不物理删除治理行；只用既有模型状态（``inactive``）软化 orphaned staged 行。
    """
    if ttl_seconds is None:
        from app.core.config import settings

        ttl_seconds = int(getattr(settings, "ATTACHMENT_QUARANTINE_TTL_SECONDS", 86400))
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=max(0, ttl_seconds))

    report = QuarantineReapReport()

    params: dict = {"cutoff": cutoff, "lim": limit}
    proj_clause = ""
    if project_id is not None:
        proj_clause = "AND project_id = :pid "
        params["pid"] = str(project_id)

    rows = (
        await db.execute(
            sa.text(
                "SELECT id, project_id, storage_key FROM evidence_quarantine_handles "
                "WHERE handle_state IN ('staged','quarantined') "
                "AND created_at < :cutoff "
                + proj_clause
                + "ORDER BY created_at ASC LIMIT :lim"
            ),
            params,
        )
    ).mappings().all()

    for row in rows:
        report.scanned += 1
        handle_id = row["id"]
        handle_pid = row["project_id"]
        storage_key = row["storage_key"]
        staged_locator = f"{_STAGED_LOCATOR_PREFIX}{handle_id}"

        # 定位 orphaned staged Attachment / AttachmentVersion（经 staged locator 反查）。
        att = (
            await db.execute(
                sa.text("SELECT id, state FROM attachments WHERE file_path = :loc"),
                {"loc": staged_locator},
            )
        ).mappings().first()
        vers = (
            await db.execute(
                sa.text(
                    "SELECT id, availability FROM attachment_versions WHERE storage_key = :loc"
                ),
                {"loc": staged_locator},
            )
        ).mappings().all()

        attachment_id = att["id"] if att else None
        version_ids = [str(v["id"]) for v in vers]

        # Legal Hold / 引用保护：整体跳过（不擦除、不对账）。
        if attachment_id is not None:
            if await _is_under_active_hold(
                db, project_id=handle_pid, node_type="attachment", node_id=str(attachment_id)
            ):
                report.skipped_legal_hold += 1
                report.skipped_handle_ids.append(handle_id)
                continue
            if await _is_referenced(
                db,
                project_id=handle_pid,
                attachment_id=attachment_id,
                version_ids=version_ids,
            ):
                report.skipped_referenced += 1
                report.skipped_handle_ids.append(handle_id)
                continue

        # 1) 加密擦除 durable blob（幂等：quarantined handle 内容早已擦除 → no-op）。
        try:
            quarantine_store.purge(storage_key, crypto_erase=True)
        except Exception:  # noqa: BLE001 — 擦除失败不得阻断标记 purged（内容不可读优先）
            pass

        # 2) handle → purged（purged_at 置位；is_publicly_readable 保持 false）。
        await db.execute(
            sa.text(
                "UPDATE evidence_quarantine_handles "
                "SET handle_state = :purged, purged_at = :now "
                "WHERE id = :id AND handle_state IN ('staged','quarantined')"
            ),
            {"purged": _HANDLE_PURGED, "now": now, "id": str(handle_id)},
        )
        report.purged += 1
        report.purged_handle_ids.append(handle_id)

        # 3) 对账 orphaned staged 行（只软化 pending/staged，绝不动 available/已终态行）。
        if att is not None and att["state"] == _ATTACHMENT_PENDING:
            await db.execute(
                sa.text(
                    "UPDATE attachments SET state = :inactive, updated_at = :now "
                    "WHERE id = :id AND state = :pending"
                ),
                {
                    "inactive": _ATTACHMENT_INACTIVE,
                    "pending": _ATTACHMENT_PENDING,
                    "now": now,
                    "id": str(att["id"]),
                },
            )
            report.attachments_inactivated += 1
        for v in vers:
            if v["availability"] == _VERSION_STAGED:
                await db.execute(
                    sa.text(
                        "UPDATE attachment_versions SET availability = :inactive "
                        "WHERE id = :id AND availability = :staged"
                    ),
                    {
                        "inactive": _VERSION_INACTIVE,
                        "staged": _VERSION_STAGED,
                        "id": str(v["id"]),
                    },
                )
                report.versions_inactivated += 1

    await db.flush()
    if commit:
        await db.commit()
    return report
