"""从 ACTIVE publication 实例化整册 workbook（V158 两张表）。

Spec: custom-workpaper-template-ingestion-and-sync-closure, Task 10 / 20

## 本模块补的接线

前置状态（实施前现算）：
* `workbook_instance.create_workbook_instance` 纯函数已存在且有测试；
* `project_workbook_instance` / `project_workbook_sheet_entry` 表与 ORM 已存在（V158）；
* `publication_ops.instantiate_from_active` 只返回内存 dataclass，**零生产调用方**。

缺的是「把 publication 的 handoff → sheet 种子 → **落库**」这一段。本模块补它。

## 为什么 sheet 映射由调用方给、服务端只做白名单

`component_type` / `wp_code` / `projection_mode` 是**业务裁决**，preflight 里没有
（`SheetReport` 只有 `sheet_uid` / `sheet_name` / `order` / `state` /
`projection_recommendation`）。让服务端猜 componentType 等于凭空造数据。

所以：调用方提交 `sheets: [{sheetUid, wpCode, componentType, projectionMode, sheetCode}]`，
服务端**只认 preflight 报告里真实存在的 sheetUid**（白名单 + fail-closed），
并强制 `included` 的 sheet 数量 ≥ 1。

## 不变量

* **只允许 ACTIVE publication**（与 `assert_instantiate_allowed` 同判据）；
* **sheetUid 必须出现在该 artifact 的 preflight 报告里** —— 拒绝凭空造的 sheet；
* **一份整册只建一个 instance**：child 共享 `current_artifact_id` /
  `workbook_generation` / `onlyoffice_room_id`（不按 sheet 复制 xlsx）；
* **同一 wp 已实例化则拒绝**（避免重复建册），由调用方显式走 upgrade 路径。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Sequence

import sqlalchemy as sa

from app.models.project_workbook_models import (
    ProjectWorkbookInstanceRow,
    ProjectWorkbookSheetEntryRow,
)
from app.services.custom_template_ingestion.lifecycles import PublicationState
from app.services.custom_template_ingestion.mapping import ProjectionMode
from app.services.custom_template_ingestion.publication_registry_store import (
    PublicationStoreError,
    StoredPublication,
)
from app.services.custom_template_ingestion.workbook_instance import (
    ProjectWorkbookInstance,
    SheetSeed,
    WorkbookInstanceError,
    create_workbook_instance,
)
from app.services.guidance_gid import StableSheetIdentity

__all__ = [
    "InstantiateError",
    "SheetSeedInput",
    "InstantiatedWorkbook",
    "build_sheet_seeds",
    "instantiate_publication",
]

#: 允许的 sheet 状态 —— 只有可见 sheet 才纳入（hidden / veryHidden 明确拒绝纳入）
_INSTANTIABLE_SHEET_STATES = frozenset({"visible"})


class InstantiateError(ValueError):
    """实例化前置条件不满足（状态 / 白名单 / 重复建册）。"""


@dataclass(frozen=True, slots=True)
class SheetSeedInput:
    """调用方提交的单 sheet 映射（业务裁决）。"""

    sheet_uid: str
    wp_code: str
    component_type: str
    projection_mode: str
    sheet_code: str | None = None
    manifest_version: str | None = None

    def to_seed(self, *, lineage_id: str, version_id: str) -> SheetSeed:
        return SheetSeed(
            sheet=StableSheetIdentity(
                template_lineage_id=lineage_id,
                template_version_id=version_id,
                wp_code=self.wp_code,
                sheet_uid=self.sheet_uid,
                sheet_code=self.sheet_code,
            ),
            sheet_code=self.sheet_code,
            wp_code=self.wp_code,
            component_type=self.component_type,
            projection_mode=ProjectionMode(self.projection_mode),
            manifest_version=self.manifest_version,
            guidance_revision="",
        )


@dataclass(frozen=True, slots=True)
class InstantiatedWorkbook:
    instance: ProjectWorkbookInstance
    publication_key: str
    sheet_count: int


def build_sheet_seeds(
    *,
    inputs: Sequence[SheetSeedInput],
    preflight_sheets: Sequence[dict[str, Any]],
    lineage_id: str,
    version_id: str,
) -> list[SheetSeed]:
    """构造 sheet 种子并对 preflight 报告做白名单校验（fail-closed）。

    校验项：
    * 至少一个 sheet；
    * 每个 `sheet_uid` 必须出现在 preflight 报告里；
    * 不得重复 `sheet_uid`；
    * 只接受 `state == visible` 的 sheet（隐藏页纳入会得到空 tab）。
    """
    if not inputs:
        raise InstantiateError("至少需要一个 sheet 映射")

    known = {str(s.get("sheetUid") or s.get("sheet_uid") or "") for s in preflight_sheets}
    known.discard("")
    if not known:
        raise InstantiateError("preflight 报告缺少 sheet 列表，无法校验 sheet 映射")
    visible = {
        str(s.get("sheetUid") or s.get("sheet_uid") or ""): str(s.get("state") or "")
        for s in preflight_sheets
    }

    seen: set[str] = set()
    seeds: list[SheetSeed] = []
    for item in inputs:
        uid = item.sheet_uid.strip()
        if not uid:
            raise InstantiateError("sheetUid 不得为空")
        if uid in seen:
            raise InstantiateError(f"重复 sheetUid: {uid}")
        seen.add(uid)
        if uid not in known:
            raise InstantiateError(f"sheetUid 不在 preflight 报告中: {uid}")
        state = visible.get(uid, "")
        if state and state not in _INSTANTIABLE_SHEET_STATES:
            raise InstantiateError(f"sheet 状态 {state} 不可纳入: {uid}")
        seeds.append(item.to_seed(lineage_id=lineage_id, version_id=version_id))
    return seeds


def instantiate_publication(
    session: Any,
    *,
    publication: StoredPublication,
    organization_id: str,
    project_id: str,
    wp_id: str,
    sheet_inputs: Sequence[SheetSeedInput],
    preflight_sheets: Sequence[dict[str, Any]],
    onlyoffice_room_id: str | None = None,
) -> InstantiatedWorkbook:
    """把 ACTIVE publication 实例化成整册 workbook 并落库。

    失败条件全部 fail-closed：非 ACTIVE、sheet 白名单不符、该 wp 已建册。
    """
    if publication.organization_id != organization_id:
        raise InstantiateError("publication 不属于当前组织")
    if publication.state != PublicationState.ACTIVE:
        raise PublicationStoreError(
            f"instantiate 仅允许 ACTIVE publication，当前={publication.state.value}"
        )

    existing = session.execute(
        sa.select(ProjectWorkbookInstanceRow).where(
            ProjectWorkbookInstanceRow.wp_id == wp_id,
            ProjectWorkbookInstanceRow.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise InstantiateError(
            f"该底稿已建册（workbook_instance_id={existing.workbook_instance_id}），"
            "升级请走 upgrade 路径"
        )

    seeds = build_sheet_seeds(
        inputs=sheet_inputs,
        preflight_sheets=preflight_sheets,
        lineage_id=publication.authority_ref,
        version_id=publication.publication_key,
    )
    instance = create_workbook_instance(
        organization_id=organization_id,
        project_id=project_id,
        wp_id=wp_id,
        workbook_lineage_id=publication.authority_ref,
        pinned_template_version_id=publication.publication_key,
        current_artifact_id=publication.candidate_id,
        content_revision="c0",
        representation_revision="r0",
        sheets=seeds,
        onlyoffice_room_id=onlyoffice_room_id,
    )

    session.add(
        ProjectWorkbookInstanceRow(
            workbook_instance_id=instance.workbook_instance_id,
            organization_id=instance.organization_id,
            project_id=instance.project_id,
            wp_id=instance.wp_id,
            workbook_lineage_id=instance.workbook_lineage_id,
            pinned_template_version_id=instance.pinned_template_version_id,
            current_artifact_id=instance.current_artifact_id,
            content_revision=instance.content_revision,
            representation_revision=instance.representation_revision,
            workbook_generation=instance.workbook_generation,
            onlyoffice_room_id=instance.onlyoffice_room_id,
            context_fingerprint=instance.context_fingerprint,
            authorization_epoch=instance.authorization_epoch,
        )
    )
    for child in instance.children:
        session.add(
            ProjectWorkbookSheetEntryRow(
                entry_id=child.entry_id,
                workbook_instance_id=child.workbook_instance_id,
                sheet_uid=child.sheet_uid,
                sheet_code=child.sheet_code,
                wp_code=child.wp_code,
                component_type=child.component_type,
                projection_mode=child.projection_mode.value,
                manifest_version=child.manifest_version,
                guidance_revision=child.guidance_revision,
                projection_generation=child.projection_generation,
            )
        )
    session.flush()
    return InstantiatedWorkbook(
        instance=instance,
        publication_key=publication.publication_key,
        sheet_count=len(instance.children),
    )
