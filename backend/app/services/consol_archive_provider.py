"""合并归档 provider：把一次成功合并运行应归档的全部产物汇成清单（批 6 / ADR-CRW-006、R8.4、R9.2）。

被 `archive_inventory` 按 provider 模式调用，返回合并项目应归入归档包的文件/数据清单。
缺件时写明原因并 **fail-closed**（清单项标 `missing`，`archive_items_complete` 据此拦截，
归档编排器据此阻断，不降级为成功）。

清单覆盖（任务 6.5）：
1. 成功 operation（批 2 `consol_operation`，status=succeeded）
2. 正式报表运行（批 4 `report_generation_run`，operation.result_refs.report_run_id）
3. 不可变 artifact（批 4 `consol_artifact`：report_excel + consol_workpaper，status=ready 带 sha256）
4. 签字快照（批 7 `consol_snapshot` sign/lock 快照 + 哈希可还原校验；sign/lock 场景缺快照即 fail-closed）
5. 附件证据（批 6 薄壳 wp_id 上的 `EvidenceLink` / `AttachmentWorkingPaper`；引用到已删除/缺失附件即 fail-closed）
6. 审计清单（`audit_log_entries` 本项目合并生命周期留痕 + 链尾 hash；成功运行却零留痕即 fail-closed）
7. 薄底稿壳（批 6 `working_paper` wp_code='A3-CONSOL'）

不新增事实表；全部只读。snapshot v2 manifest 仍在批 7 构建，本 provider 读取既有
`ConsolSnapshot.snapshot_data`（v1 gzip+base64 或 v2 manifest 均可），并对 sign/lock 场景
把「required 但缺失/损坏」的快照视为缺件而非静默跳过（R9.1）。
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consol_operation_models import ConsolOperation
from app.models.report_generation_models import ConsolArtifact, ReportGenerationRun
from app.services.consol_workpaper_shell import WP_CODE, get_consol_workpaper_shell

# 签字/锁定类快照的 trigger_reason（与 consol_snapshot_service._LOCK_REASONS 同口径）。
# sign/lock 归档场景下，这类 required 快照缺失或哈希损坏一律 fail-closed。
_SIGN_LOCK_REASONS = {"sign", "signed", "lock", "locked", "signature"}

# 本项目合并生命周期审计 action 前缀（consol_audit_helper / append_audit_log 写入）。
_CONSOL_AUDIT_PREFIX = "consol."


async def collect_consol_archive_items(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    require_snapshot: bool = True,
) -> list[dict[str, Any]]:
    """返回合并模块应归入归档包的清单项。

    每项包含 ``{kind, label, status, ...}``，``status`` = ready / missing / not_applicable。

    参数:
        require_snapshot: True（归档/签字口径）时，缺少 sign/lock 快照记 ``missing`` 并 fail-closed；
            False（诊断口径）时记 ``not_applicable``。
    """
    items: list[dict[str, Any]] = []

    # 1. succeeded operation ---------------------------------------------------
    operation = (await db.execute(
        sa.select(ConsolOperation).where(
            ConsolOperation.project_id == project_id,
            ConsolOperation.year == year,
            ConsolOperation.status == "succeeded",
        ).order_by(ConsolOperation.finished_at.desc()).limit(1)
    )).scalar_one_or_none()

    if operation is None:
        items.append({
            "kind": "consol_operation",
            "label": "合并运行",
            "status": "missing",
            "reason": "没有已成功的合并运行",
        })
        # operation 是其余产物的根；缺它直接 fail-closed，不再继续收集（避免误导性 ready 项）
        return items

    items.append({
        "kind": "consol_operation",
        "label": "合并运行",
        "status": "ready",
        "operation_id": str(operation.id),
        "operation_revision": operation.revision,
    })

    # 2. report run ------------------------------------------------------------
    run = await _resolve_report_run(db, operation)
    run_id = (operation.result_refs or {}).get("report_run_id")
    if run is None or run.status != "succeeded":
        items.append({
            "kind": "report_run",
            "label": "正式报表运行",
            "status": "missing",
            "reason": "合并运行未引用已成功的报表运行" if not run_id else "报表运行状态异常",
        })
    else:
        items.append({
            "kind": "report_run",
            "label": "正式报表运行",
            "status": "ready",
            "report_run_id": str(run.id),
            "row_digest": run.row_digest,
            "row_count": run.row_count,
        })

    # 3. artifacts (report_excel + consol_workpaper) ---------------------------
    for kind in ("report_excel", "consol_workpaper"):
        label = "正式报表 Excel" if kind == "report_excel" else "合并工作底稿包"
        artifact = (await db.execute(
            sa.select(ConsolArtifact).where(
                ConsolArtifact.project_id == project_id,
                ConsolArtifact.year == year,
                ConsolArtifact.kind == kind,
                ConsolArtifact.status == "ready",
            ).order_by(ConsolArtifact.ready_at.desc()).limit(1)
        )).scalar_one_or_none()
        if artifact is None:
            items.append({
                "kind": kind,
                "label": label,
                "status": "missing",
                "reason": f"没有已生成的{label}",
            })
        elif not artifact.sha256:
            # ready 却无 hash ⇒ 不可验证完整性，fail-closed（R5.4 下载不得再临时重算，必须有 hash）
            items.append({
                "kind": kind,
                "label": label,
                "status": "missing",
                "reason": f"{label}缺少 SHA-256，无法校验完整性",
                "artifact_id": str(artifact.id),
            })
        else:
            items.append({
                "kind": kind,
                "label": label,
                "status": "ready",
                "artifact_id": str(artifact.id),
                "file_name": artifact.file_name,
                "storage_path": artifact.storage_path,
                "sha256": artifact.sha256,
                "size_bytes": artifact.size_bytes,
            })

    # 4. 签字快照（required source；sign/lock 场景缺失或损坏 ⇒ fail-closed，R9.1/R9.2）--------
    items.append(await _snapshot_item(db, project_id, year, require_snapshot=require_snapshot))

    # 5. 薄底稿壳（附件证据 / 审计清单都挂在壳的 wp_id 上，先解析壳）--------------------------
    shell = await get_consol_workpaper_shell(db, project_id)
    if shell is None:
        items.append({
            "kind": "workpaper_shell",
            "label": "合并底稿壳",
            "status": "not_applicable",
            "reason": "未创建 A3-CONSOL 底稿壳",
        })
    else:
        items.append({
            "kind": "workpaper_shell",
            "label": "合并底稿壳",
            "status": "ready",
            "working_paper_id": shell["working_paper_id"],
            "wp_code": WP_CODE,
            "review_status": shell.get("review_status"),
        })

    # 6. 附件证据（壳 wp_id 上的整稿关联 + 行级证据链接；引用到已删除/缺失附件 ⇒ fail-closed）----
    items.append(await _attachments_item(db, shell))

    # 7. 审计清单（本项目合并生命周期留痕 + 链尾 hash；成功运行却零留痕 ⇒ fail-closed）-----------
    items.append(await _audit_manifest_item(db, project_id))

    return items


async def _resolve_report_run(
    db: AsyncSession, operation: ConsolOperation
) -> ReportGenerationRun | None:
    """从 operation.result_refs.report_run_id 取报表运行；id 无效/不存在返回 None。"""
    run_id = (operation.result_refs or {}).get("report_run_id")
    if not run_id:
        return None
    try:
        return await db.get(ReportGenerationRun, UUID(str(run_id)))
    except (ValueError, TypeError):
        return None


async def _snapshot_item(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    require_snapshot: bool,
) -> dict[str, Any]:
    """签字快照清单项：取最近一个 sign/lock 快照并校验哈希可还原。

    - 存在且哈希有效 ⇒ ready（带 snapshot_id / hash / locked）
    - 存在但哈希损坏/不可还原 ⇒ missing（R9.3：恢复须校验全部 hash）
    - 不存在：require_snapshot ⇒ missing（fail-closed）；否则 not_applicable（诊断口径）
    """
    from app.models.phase10_models import ConsolSnapshot
    from app.services.consol_snapshot_service import restore_consol_snapshot

    # 只认 sign/lock 快照作为归档 required source；手工诊断快照不算（R9.1 可 partial）。
    # 按创建时间倒序取最近一个 sign/lock 快照（trigger_reason 命中或 snapshot_data._locked 为真）。
    all_rows = (await db.execute(
        sa.select(ConsolSnapshot).where(
            ConsolSnapshot.project_id == project_id,
            ConsolSnapshot.year == year,
        ).order_by(ConsolSnapshot.created_at.desc())
    )).scalars().all()
    sign_snapshot = None
    for row in all_rows:
        reason = (row.trigger_reason or "").lower()
        data = row.snapshot_data or {}
        if reason in _SIGN_LOCK_REASONS or bool(data.get("_locked")):
            sign_snapshot = row
            break

    if sign_snapshot is None:
        if require_snapshot:
            return {
                "kind": "sign_snapshot",
                "label": "签字快照",
                "status": "missing",
                "reason": "没有已签字/锁定的合并快照（归档要求完整签字快照）",
            }
        return {
            "kind": "sign_snapshot",
            "label": "签字快照",
            "status": "not_applicable",
            "reason": "无签字快照（诊断口径不要求）",
        }

    restored = restore_consol_snapshot(sign_snapshot)
    if not restored.get("hash_valid"):
        return {
            "kind": "sign_snapshot",
            "label": "签字快照",
            "status": "missing",
            "reason": "签字快照哈希校验失败或不可还原（完整性受损）",
            "snapshot_id": str(sign_snapshot.id),
        }

    return {
        "kind": "sign_snapshot",
        "label": "签字快照",
        "status": "ready",
        "snapshot_id": str(sign_snapshot.id),
        "trigger_reason": sign_snapshot.trigger_reason,
        "hash": restored.get("hash"),
        "locked": bool(restored.get("locked")),
    }


async def _attachments_item(
    db: AsyncSession, shell: dict[str, Any] | None
) -> dict[str, Any]:
    """附件证据清单项：壳 wp_id 上的整稿关联（AttachmentWorkingPaper）+ 行级证据（EvidenceLink）。

    - 无壳 ⇒ not_applicable（证据挂不上，不构成缺件）
    - 有壳：枚举关联的全部 attachment_id，逐个确认未删除；
      任一证据链接指向已删除/不存在的附件 ⇒ missing（fail-closed，R8.4 清单与文件 hash 必须闭合）
    """
    if shell is None:
        return {
            "kind": "attachments",
            "label": "附件证据",
            "status": "not_applicable",
            "reason": "未创建合并底稿壳，无附件证据挂载点",
        }

    from app.models.attachment_models import Attachment, AttachmentWorkingPaper
    from app.models.wp_optimization_models import EvidenceLink

    wp_id = UUID(str(shell["working_paper_id"]))

    # 全部关联到壳的附件 id（整稿关联 ∪ 证据链接）
    referenced: set[UUID] = set()
    link_ids = (await db.execute(
        sa.select(AttachmentWorkingPaper.attachment_id).where(
            AttachmentWorkingPaper.wp_id == wp_id
        )
    )).scalars().all()
    referenced.update(aid for aid in link_ids if aid is not None)
    ev_ids = (await db.execute(
        sa.select(EvidenceLink.attachment_id).where(EvidenceLink.wp_id == wp_id)
    )).scalars().all()
    referenced.update(aid for aid in ev_ids if aid is not None)

    if not referenced:
        # 合并底稿允许没有附件证据（空集合不是缺件），但要如实记录 0 并闭合清单
        return {
            "kind": "attachments",
            "label": "附件证据",
            "status": "ready",
            "attachment_count": 0,
            "working_paper_id": str(wp_id),
        }

    # 存活附件（未删除）
    alive = set((await db.execute(
        sa.select(Attachment.id).where(
            Attachment.id.in_(list(referenced)),
            Attachment.is_deleted == sa.false(),
        )
    )).scalars().all())
    dangling = sorted(str(aid) for aid in (referenced - alive))
    if dangling:
        return {
            "kind": "attachments",
            "label": "附件证据",
            "status": "missing",
            "reason": f"{len(dangling)} 个证据引用指向已删除或不存在的附件",
            "dangling_attachment_ids": dangling,
            "working_paper_id": str(wp_id),
        }

    return {
        "kind": "attachments",
        "label": "附件证据",
        "status": "ready",
        "attachment_count": len(alive),
        "attachment_ids": sorted(str(aid) for aid in alive),
        "working_paper_id": str(wp_id),
    }


async def _audit_manifest_item(
    db: AsyncSession, project_id: UUID
) -> dict[str, Any]:
    """审计清单项：本项目合并生命周期留痕条数 + 链尾 hash。

    成功合并运行必然至少留下 recalc/push/snapshot 等 ``consol.*`` 留痕；零留痕 ⇒ fail-closed
    （留痕缺失意味着不可追溯，不得归档）。

    只按 ``action_type``（普通 String 列，跨 PG/SQLite 一致）过滤合并生命周期 action
    （``consol.*``：lock/unlock/elimination.approve/recalc/scope.change/snapshot.create），
    并按项目隔离（``AuditLogEntry.project_id`` 存于 payload JSONB，经
    ``audit_chain.head._chain_filter`` 与 ``chain_key_of`` 过滤）——只统计本项目留痕，
    不把其他项目的 ``consol.*`` 留痕算成本项目（否则本项目零留痕会被他项目误判为 ready）。
    """
    from app.models.audit_log_models import AuditLogEntry
    from app.services.audit_chain.head import _chain_filter, chain_key_of

    rows = (await db.execute(
        sa.select(AuditLogEntry.id, AuditLogEntry.action_type, AuditLogEntry.entry_hash, AuditLogEntry.ts)
        .where(
            _chain_filter(db, chain_key_of(str(project_id))),
            AuditLogEntry.action_type.like(f"{_CONSOL_AUDIT_PREFIX}%"),
        )
        .order_by(AuditLogEntry.ts)
    )).all()

    if not rows:
        return {
            "kind": "audit_manifest",
            "label": "审计清单",
            "status": "missing",
            "reason": "没有合并生命周期审计留痕（不可追溯，不得归档）",
        }

    return {
        "kind": "audit_manifest",
        "label": "审计清单",
        "status": "ready",
        "entry_count": len(rows),
        "actions": sorted({r.action_type for r in rows}),
        "tail_hash": rows[-1].entry_hash,
    }


def archive_items_complete(items: list[dict[str, Any]]) -> bool:
    """所有非 not_applicable 项必须是 ready；任一 missing 即 fail-closed。"""
    return all(
        item["status"] in ("ready", "not_applicable")
        for item in items
    )


def archive_missing_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """清单中缺件（status=missing）的项，供归档编排器列出阻断原因。"""
    return [item for item in items if item["status"] == "missing"]


__all__ = [
    "archive_items_complete",
    "archive_missing_items",
    "collect_consol_archive_items",
]
