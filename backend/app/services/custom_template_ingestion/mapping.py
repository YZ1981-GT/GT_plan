"""逐 sheet mapping 与 CustomProjectionManifest（Task 8）。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 8.1, 8.4, 8.5, 8.6, 8.7, 8.8

## design §8 三种 projection mode 的硬裁决

* ``editable_grid``：**必须**有非空 ``CustomProjectionManifest`` + 非空
  ``CustomWorkbookAdapter``（支持 extract/apply/validate/diff/rebase/merge），
  且身份来自既有 carrier 或已验证 instrumentation；
* ``read_only_html``：**必须**有 deterministic extractor，mutation endpoint 不可用；
* ``onlyoffice_only``：adapter/projection 可 null，但**不得**建空 Grid / 伪双向对端。

无稳定 carrier + 不能安全 instrument → 动态区域不得选 editable_grid（Requirement 8.3）。

manifest 是**版本化不可变**对象；label/顺序/格式变化不改 stable identity（8.7）。
mapping/adapter/formula boundary 不完整 → ``validate_manifest`` 精确列出缺口并阻断。
"""
from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from app.services.custom_template_ingestion.identity import (
    CarrierResolution,
    InstrumentedCandidate,
    StableFieldIdentity,
    can_support_editable_grid,
)

__all__ = [
    "ProjectionMode",
    "RegionKind",
    "IdentityRule",
    "RegionMapping",
    "FieldMapping",
    "PreservationDecision",
    "CustomProjectionManifest",
    "ManifestGap",
    "ManifestValidation",
    "validate_manifest",
    "downgrade_mode_for_identity",
    "SheetConfirmation",
    "SheetMappingDecision",
    "decide_sheet_mapping",
]


class ProjectionMode(str, Enum):
    EDITABLE_GRID = "editable_grid"
    READ_ONLY_HTML = "read_only_html"
    ONLYOFFICE_ONLY = "onlyoffice_only"


class RegionKind(str, Enum):
    TITLE = "title"
    HEADER = "header"
    DATA = "data"
    FORMULA = "formula"
    READ_ONLY = "read_only"
    DYNAMIC = "dynamic"


@dataclass(frozen=True, slots=True)
class IdentityRule:
    """行/列身份规则：绑定到一个 stable carrier。禁止 label/下标。"""

    carrier_kind: str
    carrier_key: str
    instrumented: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "carrierKind": self.carrier_kind,
            "carrierKey": self.carrier_key,
            "instrumented": self.instrumented,
        }


@dataclass(frozen=True, slots=True)
class RegionMapping:
    region_id: str
    kind: RegionKind
    a1_range: str
    read_only: bool
    dynamic: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "regionId": self.region_id,
            "kind": self.kind.value,
            "a1Range": self.a1_range,
            "readOnly": self.read_only,
            "dynamic": self.dynamic,
        }


@dataclass(frozen=True, slots=True)
class FieldMapping:
    field_id: str
    identity: StableFieldIdentity
    region_id: str
    #: managed = 平台受管字段（可被 Grid 编辑并 typed-validate）；
    #: 非 managed 视为 unmanaged，只保留不双向。
    managed: bool
    value_type: str  # number / string / bool / formula / date

    def to_dict(self) -> dict[str, Any]:
        return {
            "fieldId": self.field_id,
            "identity": self.identity.to_dict(),
            "regionId": self.region_id,
            "managed": self.managed,
            "valueType": self.value_type,
        }


@dataclass(frozen=True, slots=True)
class PreservationDecision:
    """对某 unmanaged OOXML feature 的保留裁决（Requirement 4.7/8.4）。"""

    feature: str
    decision: str  # preserve / block

    def to_dict(self) -> dict[str, Any]:
        return {"feature": self.feature, "decision": self.decision}


@dataclass(frozen=True, slots=True)
class CustomProjectionManifest:
    """design §8 CustomProjectionManifest。版本化 + 不可变（frozen）。"""

    manifest_version: str
    workbook_lineage_id: str
    sheet_uid: str
    projection_mode: ProjectionMode
    regions: tuple[RegionMapping, ...]
    fields: tuple[FieldMapping, ...]
    row_identity: IdentityRule | None
    column_identity: IdentityRule | None
    formula_boundary_version: str
    preservation_decisions: tuple[PreservationDecision, ...]
    adapter_id: str | None
    adapter_version: str | None

    @property
    def managed_field_ids(self) -> frozenset[str]:
        return frozenset(f.field_id for f in self.fields if f.managed)

    @property
    def unmanaged_field_ids(self) -> frozenset[str]:
        return frozenset(f.field_id for f in self.fields if not f.managed)

    @property
    def digest(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifestVersion": self.manifest_version,
            "workbookLineageId": self.workbook_lineage_id,
            "sheetUid": self.sheet_uid,
            "projectionMode": self.projection_mode.value,
            "regions": [r.to_dict() for r in self.regions],
            "fields": [f.to_dict() for f in self.fields],
            "rowIdentity": self.row_identity.to_dict() if self.row_identity else None,
            "columnIdentity": self.column_identity.to_dict() if self.column_identity else None,
            "formulaBoundaryVersion": self.formula_boundary_version,
            "preservationDecisions": [p.to_dict() for p in self.preservation_decisions],
            "adapterId": self.adapter_id,
            "adapterVersion": self.adapter_version,
        }


@dataclass(frozen=True, slots=True)
class ManifestGap:
    code: str
    locator: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "locator": self.locator, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class ManifestValidation:
    ok: bool
    gaps: tuple[ManifestGap, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "gaps": [g.to_dict() for g in self.gaps]}


def validate_manifest(
    manifest: CustomProjectionManifest,
    *,
    adapter: "Any | None",
) -> ManifestValidation:
    """按 mode 校验 manifest+adapter 能力一致性；不完整精确列缺口并阻断。

    ``adapter`` 期望是 ``adapters.CustomWorkbookAdapter``；此处只做鸭子类型
    能力检查（避免循环 import）。
    """
    gaps: list[ManifestGap] = []
    mode = manifest.projection_mode

    if mode is ProjectionMode.EDITABLE_GRID:
        # 8.4：manifest + 非空 adapter 必填，且六个 SPI 方法齐全。
        if adapter is None:
            gaps.append(ManifestGap(
                code="editable_grid_missing_adapter",
                locator=manifest.sheet_uid,
                detail="editable_grid 必须有非空 CustomWorkbookAdapter",
            ))
        else:
            missing = _missing_adapter_methods(adapter)
            if missing:
                gaps.append(ManifestGap(
                    code="adapter_spi_incomplete",
                    locator=manifest.sheet_uid,
                    detail=f"adapter 缺少 SPI: {sorted(missing)}",
                ))
            if not (manifest.adapter_id and manifest.adapter_version):
                gaps.append(ManifestGap(
                    code="adapter_binding_missing",
                    locator=manifest.sheet_uid,
                    detail="editable_grid manifest 必须声明 adapterId+adapterVersion",
                ))
        if not manifest.managed_field_ids:
            gaps.append(ManifestGap(
                code="editable_grid_no_managed_field",
                locator=manifest.sheet_uid,
                detail="editable_grid 至少要有一个 managed field",
            ))
        # 动态受管区域必须有行身份规则（不得靠行下标）。
        if _has_managed_dynamic_region(manifest) and manifest.row_identity is None:
            gaps.append(ManifestGap(
                code="dynamic_region_missing_row_identity",
                locator=manifest.sheet_uid,
                detail="managed 动态区域必须声明 rowIdentity（禁止行下标）",
            ))
        if manifest.formula_boundary_version.strip() == "":
            gaps.append(ManifestGap(
                code="formula_boundary_undeclared",
                locator=manifest.sheet_uid,
                detail="editable_grid 必须声明 formulaBoundaryVersion",
            ))

    elif mode is ProjectionMode.READ_ONLY_HTML:
        # 8.5：至少 deterministic extractor；mutation endpoint 不可用（无 managed）。
        if adapter is None or "extract" in _missing_adapter_methods(adapter):
            gaps.append(ManifestGap(
                code="read_only_missing_extractor",
                locator=manifest.sheet_uid,
                detail="read_only_html 必须有 deterministic extractor",
            ))
        if manifest.managed_field_ids:
            gaps.append(ManifestGap(
                code="read_only_declares_managed_field",
                locator=manifest.sheet_uid,
                detail="read_only_html 不得声明 managed field（无 mutation endpoint）",
            ))

    elif mode is ProjectionMode.ONLYOFFICE_ONLY:
        # 8.6：adapter/projection 可 null，但不得伪造空 Grid / 双向对端。
        if manifest.managed_field_ids:
            gaps.append(ManifestGap(
                code="oo_only_declares_managed_field",
                locator=manifest.sheet_uid,
                detail="onlyoffice_only 不得声明 managed field（无 HTML 对端）",
            ))
        if manifest.fields:
            gaps.append(ManifestGap(
                code="oo_only_declares_projection_fields",
                locator=manifest.sheet_uid,
                detail="onlyoffice_only 不得建投影字段（会形成空 Grid 对端）",
            ))
        if adapter is not None:
            gaps.append(ManifestGap(
                code="oo_only_declares_adapter",
                locator=manifest.sheet_uid,
                detail="onlyoffice_only 不应绑定 adapter（伪双向）",
            ))

    # 全 mode 通用：字段引用的 region 必须存在。
    region_ids = {r.region_id for r in manifest.regions}
    for fm in manifest.fields:
        if fm.region_id not in region_ids:
            gaps.append(ManifestGap(
                code="field_region_dangling",
                locator=fm.field_id,
                detail=f"field 引用不存在的 region {fm.region_id!r}",
            ))

    return ManifestValidation(ok=not gaps, gaps=tuple(gaps))


def _missing_adapter_methods(adapter: Any) -> set[str]:
    required = {"extract", "validate", "apply", "diff", "rebase", "merge"}
    return {m for m in required if not callable(getattr(adapter, m, None))}


def _has_managed_dynamic_region(manifest: CustomProjectionManifest) -> bool:
    dynamic_regions = {r.region_id for r in manifest.regions if r.dynamic}
    return any(
        f.managed and f.region_id in dynamic_regions for f in manifest.fields
    )


def downgrade_mode_for_identity(
    requested: ProjectionMode,
    *,
    resolution: CarrierResolution,
    instrumented: InstrumentedCandidate | None,
) -> ProjectionMode:
    """按身份能力对请求 mode 做降级（Requirement 8.3）。

    只有 editable_grid 有身份前置；无稳定 carrier 且不能安全 instrument 时降为
    read_only_html。read_only_html / onlyoffice_only 原样返回。
    """
    if requested is not ProjectionMode.EDITABLE_GRID:
        return requested
    if can_support_editable_grid(resolution, instrumented):
        return ProjectionMode.EDITABLE_GRID
    return ProjectionMode.READ_ONLY_HTML


# ─────────────────────────────────────────────────────────────────────────────
# 逐 sheet 确认 → mapping 决策（Requirement 8.1）
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SheetConfirmation:
    """用户逐 sheet 确认输入（Requirement 8.1）。

    确认业务名、wp_code/循环、纳入状态、区域、字段、只读/动态边界、请求
    projection mode 与 preservation decisions。身份能力由 resolution/instrumented
    决定，不由用户单方声明。
    """

    sheet_uid: str
    business_name: str
    wp_code: str
    included: bool
    requested_mode: ProjectionMode
    regions: tuple[RegionMapping, ...]
    fields: tuple[FieldMapping, ...]
    row_identity: IdentityRule | None
    column_identity: IdentityRule | None
    formula_boundary_version: str
    preservation_decisions: tuple[PreservationDecision, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sheetUid": self.sheet_uid,
            "businessName": self.business_name,
            "wpCode": self.wp_code,
            "included": self.included,
            "requestedMode": self.requested_mode.value,
            "regions": [r.to_dict() for r in self.regions],
            "fields": [f.to_dict() for f in self.fields],
            "rowIdentity": self.row_identity.to_dict() if self.row_identity else None,
            "columnIdentity": self.column_identity.to_dict() if self.column_identity else None,
            "formulaBoundaryVersion": self.formula_boundary_version,
            "preservationDecisions": [p.to_dict() for p in self.preservation_decisions],
        }


@dataclass(frozen=True, slots=True)
class SheetMappingDecision:
    """决策结果：最终 mode（可能降级）、manifest（纳入时）、缺口与降级理由。"""

    sheet_uid: str
    included: bool
    requested_mode: ProjectionMode
    effective_mode: ProjectionMode
    downgraded: bool
    downgrade_reason: str | None
    manifest: CustomProjectionManifest | None
    validation: ManifestValidation

    @property
    def blocked(self) -> bool:
        return self.included and not self.validation.ok

    def to_dict(self) -> dict[str, Any]:
        return {
            "sheetUid": self.sheet_uid,
            "included": self.included,
            "requestedMode": self.requested_mode.value,
            "effectiveMode": self.effective_mode.value,
            "downgraded": self.downgraded,
            "downgradeReason": self.downgrade_reason,
            "manifest": self.manifest.to_dict() if self.manifest else None,
            "validation": self.validation.to_dict(),
            "blocked": self.blocked,
        }


def decide_sheet_mapping(
    confirmation: SheetConfirmation,
    *,
    workbook_lineage_id: str,
    manifest_version: str,
    resolution: CarrierResolution,
    instrumented: InstrumentedCandidate | None,
    adapter: "Any | None",
    adapter_id: str | None = None,
    adapter_version: str | None = None,
) -> SheetMappingDecision:
    """把逐 sheet 确认收敛为最终 mapping 决策。

    * 未纳入 → 不建 manifest，直接返回（validation ok）。
    * 请求 editable_grid 但身份不足 → 降级 read_only_html（Requirement 8.3）。
    * 降级到 read_only_html 后，managed field 会导致 validate_manifest 阻断，
      调用方必须清理 managed 标记 —— 我们在降级时把 fields 全部转 unmanaged，
      避免「声明了 editable 却降级」的隐藏空 Grid。
    """
    if not confirmation.included:
        empty = _empty_manifest(confirmation, workbook_lineage_id, manifest_version)
        return SheetMappingDecision(
            sheet_uid=confirmation.sheet_uid,
            included=False,
            requested_mode=confirmation.requested_mode,
            effective_mode=confirmation.requested_mode,
            downgraded=False,
            downgrade_reason=None,
            manifest=None,
            validation=ManifestValidation(ok=True, gaps=()),
        )

    effective = downgrade_mode_for_identity(
        confirmation.requested_mode,
        resolution=resolution,
        instrumented=instrumented,
    )
    downgraded = effective is not confirmation.requested_mode
    downgrade_reason = None
    fields = confirmation.fields
    used_adapter = adapter
    if downgraded:
        downgrade_reason = (
            resolution.downgrade_reason
            or "editable_grid_identity_unavailable"
        )
        # 降级后无 mutation endpoint：字段全转 unmanaged，adapter 只当 extractor。
        fields = tuple(
            replace_field_unmanaged(f) for f in confirmation.fields
        )

    manifest = CustomProjectionManifest(
        manifest_version=manifest_version,
        workbook_lineage_id=workbook_lineage_id,
        sheet_uid=confirmation.sheet_uid,
        projection_mode=effective,
        regions=confirmation.regions,
        fields=fields if effective is not ProjectionMode.ONLYOFFICE_ONLY else (),
        row_identity=confirmation.row_identity if effective is ProjectionMode.EDITABLE_GRID else None,
        column_identity=confirmation.column_identity if effective is ProjectionMode.EDITABLE_GRID else None,
        formula_boundary_version=confirmation.formula_boundary_version,
        preservation_decisions=confirmation.preservation_decisions,
        adapter_id=adapter_id if effective is ProjectionMode.EDITABLE_GRID else None,
        adapter_version=adapter_version if effective is ProjectionMode.EDITABLE_GRID else None,
    )
    # onlyoffice_only 不绑 adapter；editable/read-only 传入 adapter 供能力检查。
    check_adapter = used_adapter if effective is not ProjectionMode.ONLYOFFICE_ONLY else None
    validation = validate_manifest(manifest, adapter=check_adapter)
    return SheetMappingDecision(
        sheet_uid=confirmation.sheet_uid,
        included=True,
        requested_mode=confirmation.requested_mode,
        effective_mode=effective,
        downgraded=downgraded,
        downgrade_reason=downgrade_reason,
        manifest=manifest,
        validation=validation,
    )


def replace_field_unmanaged(fm: FieldMapping) -> FieldMapping:
    return FieldMapping(
        field_id=fm.field_id,
        identity=fm.identity,
        region_id=fm.region_id,
        managed=False,
        value_type=fm.value_type,
    )


def _empty_manifest(
    confirmation: SheetConfirmation,
    workbook_lineage_id: str,
    manifest_version: str,
) -> CustomProjectionManifest:
    return CustomProjectionManifest(
        manifest_version=manifest_version,
        workbook_lineage_id=workbook_lineage_id,
        sheet_uid=confirmation.sheet_uid,
        projection_mode=ProjectionMode.ONLYOFFICE_ONLY,
        regions=(),
        fields=(),
        row_identity=None,
        column_identity=None,
        formula_boundary_version=confirmation.formula_boundary_version,
        preservation_decisions=(),
        adapter_id=None,
        adapter_version=None,
    )
