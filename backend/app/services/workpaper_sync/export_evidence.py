"""
普通底稿正式导出的单位证据与内容版本读取。

spec: platform-global-display-settings-closure 任务 10 / AC-22。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


class WorkpaperExportEvidenceError(ValueError):
    """普通底稿正式导出/归档缺少可验证 content evidence。"""


@dataclass(frozen=True)
class ContentExportEvidence:
    export_surface_class: str
    unit_policy_snapshot: dict[str, Any] | None
    unit_policy_digest: str | None
    source_storage_unit: str | None
    content_version_id: UUID
    representation_id: UUID | None
    artifact_id: UUID | None
    artifact_sha256: str | None


async def build_formal_content_export_evidence(
    db: AsyncSession,
    *,
    project_id: UUID,
) -> ContentExportEvidence:
    """按项目当前正式单位构造 immutable content version 的 evidence。"""
    from app.services.export_policy_snapshot import resolve_policy_snapshot_for_project

    snapshot_text = await resolve_policy_snapshot_for_project(db, project_id=project_id)
    snapshot = json.loads(snapshot_text)
    digest = snapshot.get("_digest")
    if not isinstance(digest, str) or len(digest) != 64:
        raise WorkpaperExportEvidenceError(
            "formal content version 的 unit policy snapshot 缺少有效 digest"
        )
    return ContentExportEvidence(
        export_surface_class="formal",
        unit_policy_snapshot=snapshot,
        unit_policy_digest=digest,
        source_storage_unit=None,
        content_version_id=UUID(int=0),
        representation_id=None,
        artifact_id=None,
        artifact_sha256=None,
    )


async def resolve_current_content_export_evidence(
    db: AsyncSession,
    *,
    project_id: UUID,
    wp_id: UUID,
) -> ContentExportEvidence | None:
    """解析当前 content version → current representation → published artifact。

    返回 ``None`` 只表示历史底稿没有 current content version；调用方可以按旧
    兼容路径处理并在归档时标记 evidence 缺失。只要 current version 存在，
    任一 policy pair / artifact / pointer 不完整就 fail closed。
    """
    from app.models.workpaper_models import WorkingPaper
    from app.models.workpaper_sync_models import (
        WorkpaperArtifact,
        WorkpaperContentRepresentation,
        WorkpaperContentVersion,
        WorkpaperSyncEntryState,
    )

    wp_row = (
        await db.execute(
            sa.select(WorkingPaper.current_content_version_id).where(
                WorkingPaper.id == wp_id,
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == sa.false(),
            )
        )
    ).scalar_one_or_none()
    if wp_row is None:
        return None

    cv = (
        await db.execute(
            sa.select(WorkpaperContentVersion).where(
                WorkpaperContentVersion.id == wp_row,
                WorkpaperContentVersion.wp_id == wp_id,
            )
        )
    ).scalar_one_or_none()
    if cv is None:
        raise WorkpaperExportEvidenceError("current_content_version_id 指向不存在的内容版本")
    # 历史 SQLite 夹具/离线回归库可能仍在 V265 之前的 schema；
    # 这些库没有单位证据列，保留旧导出行为。真实 PostgreSQL 生产库若
    # current version 存在却缺 evidence，必须走下面的 fail-closed。
    dialect_name = getattr(getattr(db, "bind", None), "dialect", None)
    dialect_name = getattr(dialect_name, "name", None)
    if dialect_name != "postgresql" and cv.export_surface_class is None:
        return None
    if cv.export_surface_class not in {"formal", "data_exchange"}:
        raise WorkpaperExportEvidenceError(
            "当前内容版本缺少 export_surface_class，不能正式导出或归档"
        )
    if cv.export_surface_class == "formal":
        snapshot = cv.unit_policy_snapshot
        if not isinstance(snapshot, dict) or not isinstance(cv.unit_policy_digest, str):
            raise WorkpaperExportEvidenceError(
                "formal 内容版本缺少 unit_policy_snapshot / unit_policy_digest"
            )
        if snapshot.get("_digest") != cv.unit_policy_digest:
            raise WorkpaperExportEvidenceError("内容版本 unit policy digest 不匹配")
        if cv.source_storage_unit is not None:
            raise WorkpaperExportEvidenceError(
                "formal 内容版本不得同时携带 source_storage_unit"
            )
    else:
        if cv.source_storage_unit != "yuan":
            raise WorkpaperExportEvidenceError(
                "data_exchange 内容版本缺少 source_storage_unit=yuan"
            )
        if cv.unit_policy_snapshot is not None or cv.unit_policy_digest is not None:
            raise WorkpaperExportEvidenceError(
                "data_exchange 内容版本不得携带 formal policy pair"
            )
        snapshot = None

    rep_row = (
        await db.execute(
            sa.select(
                WorkpaperSyncEntryState.current_representation_id,
                WorkpaperContentRepresentation.artifact_id,
                WorkpaperContentRepresentation.artifact_sha256,
            )
            .join(
                WorkpaperContentRepresentation,
                WorkpaperContentRepresentation.id
                == WorkpaperSyncEntryState.current_representation_id,
            )
            .where(WorkpaperSyncEntryState.wp_id == wp_id)
            .order_by(WorkpaperSyncEntryState.entry_id)
            .limit(1)
        )
    ).first()
    artifact_id = None
    artifact_sha256 = None
    representation_id = None
    if rep_row is not None:
        representation_id = rep_row[0]
        artifact_id = rep_row[1]
        artifact_sha256 = rep_row[2]
        rep_cv = (
            await db.execute(
                sa.select(WorkpaperContentRepresentation.content_version_id).where(
                    WorkpaperContentRepresentation.id == representation_id
                )
            )
        ).scalar_one()
        if rep_cv != cv.id:
            raise WorkpaperExportEvidenceError(
                "current representation 不属于 current content version"
            )
        artifact = (
            await db.execute(
                sa.select(WorkpaperArtifact).where(WorkpaperArtifact.id == artifact_id)
            )
        ).scalar_one_or_none()
        if artifact is None or artifact.state != "published":
            raise WorkpaperExportEvidenceError("current representation 的 artifact 未发布")
        if artifact.sha256 != artifact_sha256:
            raise WorkpaperExportEvidenceError("representation 与 artifact digest 不匹配")

    return ContentExportEvidence(
        export_surface_class=cv.export_surface_class,
        unit_policy_snapshot=snapshot,
        unit_policy_digest=cv.unit_policy_digest,
        source_storage_unit=cv.source_storage_unit,
        content_version_id=cv.id,
        representation_id=representation_id,
        artifact_id=artifact_id,
        artifact_sha256=artifact_sha256,
    )


__all__ = [
    "ContentExportEvidence",
    "WorkpaperExportEvidenceError",
    "build_formal_content_export_evidence",
    "resolve_current_content_export_evidence",
]
