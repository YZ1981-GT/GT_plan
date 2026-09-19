"""整册 ProjectWorkbookInstance + child entries（Task 10）。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7

## 不变量

* 一份纳入的 Excel 只建 **一份** ``ProjectWorkbookInstance``；
* 每个纳入 sheet 建稳定 child ``ProjectWorkbookSheetEntry``（G-ID ``sheet_uid``）；
* **禁止**按 sheet 复制 xlsx / pointer / room —— 整册共享
  ``current_artifact_id`` / ``workbook_generation`` / ``onlyoffice_room_id``；
* rename / reorder 不改 ``entry_id`` / ``sheet_uid``；
* 任一写入先 ``advance_generation``，再刷新 affected child 的 ``projection_generation``。

SYNC-MULTI-RESOLVER / SYNC-ENTRY-NAMESPACE 的平台归零仍属上游 gate；
本模块对新实例使用统一 ``pwi-…`` entry namespace，并对 legacy 分裂做 fail-closed 探测
（见 ``namespace_migration``）。
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping, Sequence

from app.services.guidance_gid import StableSheetIdentity
from app.services.custom_template_ingestion.mapping import ProjectionMode
from app.services.custom_template_ingestion.namespace_migration import (
    unified_child_entry_id,
)

__all__ = [
    "SheetSeed",
    "ProjectWorkbookInstance",
    "ProjectWorkbookSheetEntry",
    "WorkbookInstanceError",
    "create_workbook_instance",
    "advance_generation",
    "rename_sheet_code",
    "reorder_sheets",
]


class WorkbookInstanceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SheetSeed:
    """创建 child 所需的最小输入（G-ID sheet + mapping 裁决）。"""

    sheet: StableSheetIdentity
    sheet_code: str | None
    wp_code: str
    component_type: str
    projection_mode: ProjectionMode
    manifest_version: str | None = None
    guidance_revision: str = ""


@dataclass(frozen=True, slots=True)
class ProjectWorkbookSheetEntry:
    entry_id: str
    workbook_instance_id: str
    sheet_uid: str
    sheet_code: str | None
    wp_code: str
    component_type: str
    projection_mode: ProjectionMode
    manifest_version: str | None
    guidance_revision: str
    projection_generation: int
    #: 展示顺序；reorder 只动这个，不动 entry_id
    display_order: int


@dataclass(frozen=True, slots=True)
class ProjectWorkbookInstance:
    workbook_instance_id: str
    organization_id: str
    project_id: str
    wp_id: str
    workbook_lineage_id: str
    pinned_template_version_id: str
    current_artifact_id: str
    content_revision: str
    representation_revision: str
    workbook_generation: int
    onlyoffice_room_id: str | None
    context_fingerprint: str
    authorization_epoch: int
    children: tuple[ProjectWorkbookSheetEntry, ...]

    @property
    def child_count(self) -> int:
        return len(self.children)

    def child_by_sheet_uid(self, sheet_uid: str) -> ProjectWorkbookSheetEntry | None:
        for c in self.children:
            if c.sheet_uid == sheet_uid:
                return c
        return None

    def child_by_entry_id(self, entry_id: str) -> ProjectWorkbookSheetEntry | None:
        for c in self.children:
            if c.entry_id == entry_id:
                return c
        return None


def _context_fingerprint(
    *,
    organization_id: str,
    project_id: str,
    workbook_lineage_id: str,
    pinned_template_version_id: str,
    artifact_id: str,
) -> str:
    raw = "|".join(
        [
            organization_id,
            project_id,
            workbook_lineage_id,
            pinned_template_version_id,
            artifact_id,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_workbook_instance(
    *,
    organization_id: str,
    project_id: str,
    wp_id: str,
    workbook_lineage_id: str,
    pinned_template_version_id: str,
    current_artifact_id: str,
    content_revision: str,
    representation_revision: str,
    sheets: Sequence[SheetSeed],
    authorization_epoch: int = 1,
    onlyoffice_room_id: str | None = None,
    workbook_instance_id: str | None = None,
) -> ProjectWorkbookInstance:
    """从一份整册 artifact + 已裁决 sheet 列表创建唯一 instance。

    结构性保证：
    * ``len(sheets) >= 1``；
    * ``sheet_uid`` 唯一；
    * 所有 child 共享同一 ``workbook_instance_id`` / artifact / generation / room；
    * child ``entry_id`` 走统一 namespace，不调用 ``opaque_entry_id(wp_code=…)``。
    """
    if not sheets:
        raise WorkbookInstanceError("至少纳入一个 sheet")
    seen_uids: set[str] = set()
    for seed in sheets:
        uid = seed.sheet.sheet_uid
        if not uid:
            raise WorkbookInstanceError("sheet_uid 不得为空（须来自 G-ID）")
        if uid in seen_uids:
            raise WorkbookInstanceError(f"重复 sheet_uid: {uid}")
        seen_uids.add(uid)

    wid = workbook_instance_id or f"pwi-{uuid.uuid4()}"
    children: list[ProjectWorkbookSheetEntry] = []
    for idx, seed in enumerate(sheets):
        entry_id = unified_child_entry_id(
            workbook_instance_id=wid,
            sheet_uid=seed.sheet.sheet_uid,
        )
        children.append(
            ProjectWorkbookSheetEntry(
                entry_id=entry_id,
                workbook_instance_id=wid,
                sheet_uid=seed.sheet.sheet_uid,
                sheet_code=seed.sheet_code,
                wp_code=seed.wp_code,
                component_type=seed.component_type,
                projection_mode=seed.projection_mode,
                manifest_version=seed.manifest_version,
                guidance_revision=seed.guidance_revision,
                projection_generation=1,
                display_order=idx,
            )
        )

    # 整册只允许一个 room 槽位（可为 None，由 SYNC-UNIFIED-ROOM 后续绑定）
    return ProjectWorkbookInstance(
        workbook_instance_id=wid,
        organization_id=organization_id,
        project_id=project_id,
        wp_id=wp_id,
        workbook_lineage_id=workbook_lineage_id,
        pinned_template_version_id=pinned_template_version_id,
        current_artifact_id=current_artifact_id,
        content_revision=content_revision,
        representation_revision=representation_revision,
        workbook_generation=1,
        onlyoffice_room_id=onlyoffice_room_id,
        context_fingerprint=_context_fingerprint(
            organization_id=organization_id,
            project_id=project_id,
            workbook_lineage_id=workbook_lineage_id,
            pinned_template_version_id=pinned_template_version_id,
            artifact_id=current_artifact_id,
        ),
        authorization_epoch=authorization_epoch,
        children=tuple(children),
    )


def advance_generation(
    instance: ProjectWorkbookInstance,
    *,
    affected_sheet_uids: Iterable[str] | None = None,
    new_content_revision: str | None = None,
    new_representation_revision: str | None = None,
    new_artifact_id: str | None = None,
) -> ProjectWorkbookInstance:
    """任一写入推进 workbook_generation，并刷新 affected child projections。

    ``affected_sheet_uids is None`` ⇒ 全部 child 刷新。
    """
    next_gen = instance.workbook_generation + 1
    affected = (
        set(affected_sheet_uids)
        if affected_sheet_uids is not None
        else {c.sheet_uid for c in instance.children}
    )
    new_children: list[ProjectWorkbookSheetEntry] = []
    for c in instance.children:
        if c.sheet_uid in affected:
            new_children.append(replace(c, projection_generation=next_gen))
        else:
            new_children.append(c)
    return replace(
        instance,
        workbook_generation=next_gen,
        content_revision=new_content_revision or instance.content_revision,
        representation_revision=new_representation_revision
        or instance.representation_revision,
        current_artifact_id=new_artifact_id or instance.current_artifact_id,
        children=tuple(new_children),
    )


def rename_sheet_code(
    instance: ProjectWorkbookInstance,
    *,
    sheet_uid: str,
    new_sheet_code: str | None,
    new_wp_code: str | None = None,
) -> ProjectWorkbookInstance:
    """改展示码 / wp_code，**不得**改 entry_id / sheet_uid。"""
    child = instance.child_by_sheet_uid(sheet_uid)
    if child is None:
        raise WorkbookInstanceError(f"未知 sheet_uid: {sheet_uid}")
    old_entry_id = child.entry_id
    updated = replace(
        child,
        sheet_code=new_sheet_code,
        wp_code=new_wp_code if new_wp_code is not None else child.wp_code,
    )
    if updated.entry_id != old_entry_id:
        raise WorkbookInstanceError("rename 不得改变 entry_id")
    new_children = tuple(
        updated if c.sheet_uid == sheet_uid else c for c in instance.children
    )
    return replace(instance, children=new_children)


def reorder_sheets(
    instance: ProjectWorkbookInstance,
    *,
    ordered_sheet_uids: Sequence[str],
) -> ProjectWorkbookInstance:
    """只重排 display_order；entry_id / sheet_uid 不变。"""
    by_uid = {c.sheet_uid: c for c in instance.children}
    if set(ordered_sheet_uids) != set(by_uid):
        raise WorkbookInstanceError("reorder 必须覆盖且仅覆盖全部 sheet_uid")
    new_children = []
    for idx, uid in enumerate(ordered_sheet_uids):
        c = by_uid[uid]
        new_children.append(replace(c, display_order=idx))
    # 稳定性：entry_id 集合不变
    if {c.entry_id for c in new_children} != {c.entry_id for c in instance.children}:
        raise WorkbookInstanceError("reorder 不得改变 entry_id 集合")
    return replace(instance, children=tuple(new_children))
