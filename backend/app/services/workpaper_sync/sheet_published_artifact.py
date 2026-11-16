"""读取 sheet 级当前 published representation 的唯一入口。

spec: `onlyoffice-sheet-open-via-published-artifact` task 2.3

该模块只读 current pointer + published artifact。它不找模板、不复制文件、不隐藏 sheet。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import UUID

from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
from app.services.workpaper_sync.models import ArtifactKind, ArtifactState
from app.services.workpaper_sync.projection_target_resolution import (
    resolve_visible_current_representation_id,
)
from app.models.workpaper_sync_models import WorkpaperArtifact, WorkpaperContentRepresentation


class PublishedSheetArtifactError(RuntimeError):
    """当前 published sheet artifact 不能安全读取。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = code


@dataclass(frozen=True)
class PublishedSheetArtifact:
    project_id: UUID
    wp_id: UUID
    entry_id: str
    representation_id: UUID
    generation: int
    artifact_id: UUID
    artifact_sha256: str
    relative_path: str
    path: Path
    document_type: str
    target_sheet: str | None
    whole_workbook: bool
    sheet_names: tuple[str, ...]
    definition_bundle_id: UUID
    definition_bundle_sha256: str
    adapter_id: str


ResolveRepresentation = Callable[..., Awaitable[Any | None]]


async def read_current_published_sheet_artifact(
    *,
    session: Any,
    artifact_repository: CanonicalArtifactRepository,
    project_id: UUID,
    wp_id: UUID,
    entry_id: str,
    target_sheet: str | None,
    whole_workbook: bool,
    resolve_representation: ResolveRepresentation = resolve_visible_current_representation_id,
) -> PublishedSheetArtifact:
    """按 entry 读取可见 current representation，并验证 artifact 与 target sheet。

    顺序固定：current pointer → representation/artifact row → canonical visibility/path
    → sha256/size → OOXML target sheet。任何一步失败都不回退模板。
    """
    representation_id = await resolve_representation(session, entry_id=entry_id)
    if representation_id is None:
        raise PublishedSheetArtifactError(
            "current_representation_missing",
            f"entry {entry_id!r} 没有可见 current published representation",
        )

    from sqlalchemy import select

    result = await session.execute(
        select(WorkpaperContentRepresentation, WorkpaperArtifact)
        .join(WorkpaperArtifact, WorkpaperArtifact.id == WorkpaperContentRepresentation.artifact_id)
        .where(
            WorkpaperContentRepresentation.id == representation_id,
            WorkpaperContentRepresentation.wp_id == wp_id,
            WorkpaperContentRepresentation.entry_id == entry_id,
        )
    )
    row = result.first()
    if row is None:
        raise PublishedSheetArtifactError(
            "representation_row_missing",
            f"current representation {representation_id} 不属于底稿 {wp_id} / entry {entry_id}",
        )
    representation, artifact = row

    if artifact.kind != ArtifactKind.canonical.value or artifact.state != ArtifactState.published.value:
        raise PublishedSheetArtifactError(
            "artifact_not_published",
            f"artifact {artifact.id} 不可解析：kind={artifact.kind!r} state={artifact.state!r}",
        )

    try:
        path = artifact_repository.resolve_published_artifact(
            project_id=project_id,
            kind=ArtifactKind.canonical,
            state=ArtifactState.published,
            relative_path=artifact.relative_path,
        )
    except Exception as exc:  # noqa: BLE001 — 保留 canonical resolver 的 error_code 在链路日志
        raise PublishedSheetArtifactError(
            "artifact_path_unresolvable", f"published artifact 路径不可解析: {exc}"
        ) from exc

    digest, size = artifact_repository.sha256_of_file(path)
    if digest != artifact.sha256 or size != int(artifact.size_bytes):
        raise PublishedSheetArtifactError(
            "artifact_digest_drift",
            f"artifact {artifact.relative_path} 内容漂移：登记 {artifact.sha256}/{artifact.size_bytes}，"
            f"现读 {digest}/{size}",
        )

    sheet_names: tuple[str, ...] = ()
    if artifact.document_type in {"xlsx", "xlsm"}:
        try:
            from openpyxl import load_workbook

            workbook = load_workbook(path, read_only=True, data_only=False, keep_links=False)
            try:
                sheet_names = tuple(workbook.sheetnames)
            finally:
                workbook.close()
        except Exception as exc:  # noqa: BLE001
            raise PublishedSheetArtifactError(
                "artifact_ooxml_unreadable", f"published workbook 无法读取: {exc}"
            ) from exc
        if not whole_workbook and target_sheet not in sheet_names:
            raise PublishedSheetArtifactError(
                "target_sheet_not_in_published_artifact",
                f"published artifact 没有目标 sheet {target_sheet!r}；实际 sheet={list(sheet_names)!r}",
            )
    elif target_sheet and not whole_workbook:
        raise PublishedSheetArtifactError(
            "target_sheet_document_type_mismatch",
            f"document_type={artifact.document_type!r} 不支持 xlsx target sheet {target_sheet!r}",
        )

    return PublishedSheetArtifact(
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        representation_id=representation.id,
        generation=int(representation.generation),
        artifact_id=artifact.id,
        artifact_sha256=artifact.sha256,
        relative_path=artifact.relative_path,
        path=path,
        document_type=artifact.document_type,
        target_sheet=target_sheet,
        whole_workbook=whole_workbook,
        sheet_names=sheet_names,
        definition_bundle_id=representation.definition_bundle_id,
        definition_bundle_sha256=representation.definition_bundle_sha256,
        adapter_id=representation.adapter_id,
    )


__all__ = [
    "PublishedSheetArtifact",
    "PublishedSheetArtifactError",
    "read_current_published_sheet_artifact",
]
