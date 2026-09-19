"""Task 8 守卫：逐 sheet mapping、identity carrier、adapter SPI。

Feature: custom-workpaper-template-ingestion-and-sync-closure
Validates: Requirements 7.5, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8

判据一律行为级：mode 不变式、身份解析结果、adapter 六方法真实语义、三方 merge
真实合并/冲突，不做字符串存在性断言。
"""
from __future__ import annotations

import pytest

# G-ID 权威身份（不复制）——直接从上游 import
from app.services.guidance_gid import StableSheetIdentity, sheet_identity_from_authority

from app.services.custom_template_ingestion.identity import (
    CarrierResolution,
    IdentityCarrierKind,
    InstrumentationError,
    InstrumentedCandidate,
    NON_CARRIER_SIGNALS,
    StableFieldIdentity,
    can_support_editable_grid,
    instrument_candidate,
    resolve_field_identity,
    CarrierWriteResult,
    CarrierWriter,
)
from app.services.custom_template_ingestion.mapping import (
    CustomProjectionManifest,
    FieldMapping,
    IdentityRule,
    PreservationDecision,
    ProjectionMode,
    RegionKind,
    RegionMapping,
    SheetConfirmation,
    decide_sheet_mapping,
    downgrade_mode_for_identity,
    validate_manifest,
)
from app.services.custom_template_ingestion.adapters import (
    DeterministicExtractor,
    FieldConflict,
    FieldLevelWorkbookAdapter,
    ManagedMutation,
    encode_workbook_model,
)


# ─────────────────────────────────────────────────────────────────────────────
# fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _sheet() -> StableSheetIdentity:
    return StableSheetIdentity(
        template_lineage_id="lin-1",
        template_version_id="ver-1",
        wp_code="D5",
        sheet_uid="sheet:0:abcd",
        sheet_code="D5",
    )


def _field_identity(carrier_key: str = "rowKey") -> StableFieldIdentity:
    return StableFieldIdentity(
        sheet=_sheet(),
        carrier_kind=IdentityCarrierKind.DEFINED_NAME,
        carrier_key=carrier_key,
        locator="sheet:0:abcd/definedName/rowKey",
        instrumented=False,
    )


def _adapter() -> FieldLevelWorkbookAdapter:
    return FieldLevelWorkbookAdapter(adapter_id="fld-adapter", adapter_version="1.0")


def _editable_manifest(*, managed: bool = True, adapter_bound: bool = True) -> CustomProjectionManifest:
    region = RegionMapping(
        region_id="r1", kind=RegionKind.DATA, a1_range="A1:B10",
        read_only=False, dynamic=False,
    )
    fld = FieldMapping(
        field_id="f1", identity=_field_identity(), region_id="r1",
        managed=managed, value_type="number",
    )
    return CustomProjectionManifest(
        manifest_version="m1",
        workbook_lineage_id="lin-1",
        sheet_uid="sheet:0:abcd",
        projection_mode=ProjectionMode.EDITABLE_GRID,
        regions=(region,),
        fields=(fld,),
        row_identity=IdentityRule("defined_name", "rowKey", False),
        column_identity=None,
        formula_boundary_version="fb-1",
        preservation_decisions=(PreservationDecision("merge", "preserve"),),
        adapter_id="fld-adapter" if adapter_bound else None,
        adapter_version="1.0" if adapter_bound else None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# G-ID 消费 (7.5) —— 身份来自上游，不复制
# ─────────────────────────────────────────────────────────────────────────────


def test_stable_sheet_identity_comes_from_gid_module() -> None:
    # StableSheetIdentity 与 sheet_identity_from_authority 必须是 G-ID 的对象
    from app.services import guidance_gid
    from app.services.custom_template_ingestion import identity as ident_mod
    assert ident_mod.StableSheetIdentity is guidance_gid.StableSheetIdentity
    assert ident_mod.sheet_identity_from_authority is guidance_gid.sheet_identity_from_authority


def test_field_identity_binds_to_gid_sheet_catalog_key() -> None:
    fi = _field_identity()
    # identity_key 派生自 G-ID catalog_key，sheet rename 不改（catalog_key 用 uid）
    assert _sheet().catalog_key in fi.identity_key
    assert "sheet:0:abcd" in fi.identity_key


# ─────────────────────────────────────────────────────────────────────────────
# label / order / row index 不是身份载体 (7.5 / design §7)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad_key", sorted(NON_CARRIER_SIGNALS))
def test_label_and_index_are_never_identity_carriers(bad_key: str) -> None:
    with pytest.raises(ValueError):
        StableFieldIdentity(
            sheet=_sheet(),
            carrier_kind=IdentityCarrierKind.DEFINED_NAME,
            carrier_key=bad_key,
            locator="x",
            instrumented=False,
        )


def test_resolve_rejects_label_like_carrier_key() -> None:
    res = resolve_field_identity(
        sheet=_sheet(),
        requested_carrier_kind="defined_name",
        requested_carrier_key="row_index",
        existing_carrier_keys={"row_index": "loc"},
    )
    assert res.resolved is False
    assert res.downgrade_reason == "carrier_key_is_label_or_index"


# ─────────────────────────────────────────────────────────────────────────────
# 优先既有 carrier；否则 instrument 或降级 (8.2 / 8.3)
# ─────────────────────────────────────────────────────────────────────────────


def test_existing_carrier_resolves_without_instrumentation() -> None:
    res = resolve_field_identity(
        sheet=_sheet(),
        requested_carrier_kind="defined_name",
        requested_carrier_key="rowKey",
        existing_carrier_keys={"rowKey": "sheet:0:abcd/definedName/rowKey"},
    )
    assert res.resolved is True
    assert res.identity is not None
    assert res.identity.instrumented is False
    assert res.requires_instrumentation is False


def test_missing_instrumentable_carrier_requires_instrumentation() -> None:
    res = resolve_field_identity(
        sheet=_sheet(),
        requested_carrier_kind="platform_defined_name",
        requested_carrier_key="platKey",
        existing_carrier_keys={},
    )
    assert res.resolved is False
    assert res.requires_instrumentation is True
    assert res.downgrade_reason is None


def test_missing_noninstrumentable_carrier_downgrades() -> None:
    # table_column 不在 INSTRUMENTABLE_CARRIER_KINDS
    res = resolve_field_identity(
        sheet=_sheet(),
        requested_carrier_kind="table_column",
        requested_carrier_key="tblCol",
        existing_carrier_keys={},
    )
    assert res.resolved is False
    assert res.requires_instrumentation is False
    assert res.downgrade_reason == "no_existing_carrier_and_not_instrumentable"


# ─────────────────────────────────────────────────────────────────────────────
# instrumentation：新 immutable candidate + reopen/roundtrip/diff (8.2)
# ─────────────────────────────────────────────────────────────────────────────


class _OkWriter(CarrierWriter):
    """写入后字节变化，reopen/roundtrip/diff 全过。"""

    def write_carrier(self, *, base_bytes, carrier_kind, carrier_key):
        return CarrierWriteResult(
            new_bytes=base_bytes + b"\x00platform-carrier:" + carrier_key.encode(),
            locator=f"sheet/definedName/{carrier_key}",
            reopen_ok=True,
            roundtrip_ok=True,
            preservation_diff_ok=True,
        )


class _NoopWriter(CarrierWriter):
    """故意不改字节 —— instrumentation 必须判无效。"""

    def write_carrier(self, *, base_bytes, carrier_kind, carrier_key):
        return CarrierWriteResult(
            new_bytes=base_bytes,
            locator="x",
            reopen_ok=True,
            roundtrip_ok=True,
            preservation_diff_ok=True,
        )


def test_instrumentation_creates_new_immutable_candidate_and_verifies() -> None:
    base = b"original-xlsx-bytes"
    instr = instrument_candidate(
        sheet=_sheet(),
        base_candidate_revision="r1-aaaa",
        base_artifact_bytes=base,
        carrier_kind="platform_defined_name",
        carrier_key="platKey",
        writer=_OkWriter(),
    )
    # 新 revision + 新 digest，原始未改（对照 base sha）
    assert instr.new_candidate_revision != "r1-aaaa"
    assert instr.new_artifact_sha256 != instr.base_artifact_sha256
    assert instr.identity.instrumented is True
    assert instr.verified is True


def test_instrument_candidate_rejects_writer_that_does_not_change_bytes() -> None:
    """M3 目标：instrument_candidate 早期字节变化校验（new_sha == base_sha）。"""
    with pytest.raises(InstrumentationError):
        instrument_candidate(
            sheet=_sheet(),
            base_candidate_revision="r1-aaaa",
            base_artifact_bytes=b"x",
            carrier_kind="platform_defined_name",
            carrier_key="platKey",
            writer=_NoopWriter(),
        )


def test_instrumented_candidate_rejects_equal_revision_directly() -> None:
    """M2 目标：InstrumentedCandidate.__post_init__ 的 revision 相等校验。

    直接构造相等 revision（但 digest 不同）——只有 __post_init__ 的 revision
    分支能拦，instrument_candidate 的字节校验不参与。
    """
    with pytest.raises(InstrumentationError):
        InstrumentedCandidate(
            base_candidate_revision="r1",
            new_candidate_revision="r1",  # 相等 revision
            base_artifact_sha256="a" * 64,
            new_artifact_sha256="b" * 64,  # digest 不同，绕过 digest 分支
            identity=_field_identity(),
            reopen_ok=True,
            roundtrip_ok=True,
            preservation_diff_ok=True,
        )


def test_instrumented_candidate_rejects_equal_digest_directly() -> None:
    """M3 的 __post_init__ 兄弟分支：digest 相等（revision 不同）必须拒绝。"""
    with pytest.raises(InstrumentationError):
        InstrumentedCandidate(
            base_candidate_revision="r1",
            new_candidate_revision="r1+x",  # revision 不同，绕过 revision 分支
            base_artifact_sha256="a" * 64,
            new_artifact_sha256="a" * 64,  # digest 相等
            identity=_field_identity(),
            reopen_ok=True,
            roundtrip_ok=True,
            preservation_diff_ok=True,
        )


def test_instrumentation_rejects_noninstrumentable_kind() -> None:
    with pytest.raises(InstrumentationError):
        instrument_candidate(
            sheet=_sheet(),
            base_candidate_revision="r1",
            base_artifact_bytes=b"x",
            carrier_kind="table_column",
            carrier_key="c",
            writer=_OkWriter(),
        )


def test_unverified_instrumentation_cannot_support_editable_grid() -> None:
    res = CarrierResolution(identity=None, requires_instrumentation=True, downgrade_reason=None)
    unverified = InstrumentedCandidate(
        base_candidate_revision="r1",
        new_candidate_revision="r1+x",
        base_artifact_sha256="a" * 64,
        new_artifact_sha256="b" * 64,
        identity=_field_identity(),
        reopen_ok=True,
        roundtrip_ok=False,  # roundtrip 失败
        preservation_diff_ok=True,
    )
    assert can_support_editable_grid(res, unverified) is False


# ─────────────────────────────────────────────────────────────────────────────
# mode 降级 (8.3)
# ─────────────────────────────────────────────────────────────────────────────


def test_no_carrier_downgrades_editable_to_read_only() -> None:
    res = CarrierResolution(
        identity=None, requires_instrumentation=False,
        downgrade_reason="no_existing_carrier_and_not_instrumentable",
    )
    mode = downgrade_mode_for_identity(
        ProjectionMode.EDITABLE_GRID, resolution=res, instrumented=None,
    )
    assert mode is ProjectionMode.READ_ONLY_HTML


def test_resolved_carrier_keeps_editable() -> None:
    res = CarrierResolution(identity=_field_identity(), requires_instrumentation=False, downgrade_reason=None)
    mode = downgrade_mode_for_identity(ProjectionMode.EDITABLE_GRID, resolution=res, instrumented=None)
    assert mode is ProjectionMode.EDITABLE_GRID


def test_read_only_and_oo_only_never_upgraded() -> None:
    res = CarrierResolution(identity=None, requires_instrumentation=False, downgrade_reason="x")
    assert downgrade_mode_for_identity(ProjectionMode.READ_ONLY_HTML, resolution=res, instrumented=None) is ProjectionMode.READ_ONLY_HTML
    assert downgrade_mode_for_identity(ProjectionMode.ONLYOFFICE_ONLY, resolution=res, instrumented=None) is ProjectionMode.ONLYOFFICE_ONLY


# ─────────────────────────────────────────────────────────────────────────────
# manifest 校验：editable 强制 manifest+adapter，read-only 强制 extractor，
# oo-only 不建空对端 (8.4 / 8.5 / 8.6 / 8.8)
# ─────────────────────────────────────────────────────────────────────────────


def test_editable_grid_requires_nonnull_adapter() -> None:
    m = _editable_manifest()
    v = validate_manifest(m, adapter=None)
    assert v.ok is False
    assert any(g.code == "editable_grid_missing_adapter" for g in v.gaps)


def test_editable_grid_with_full_adapter_passes() -> None:
    m = _editable_manifest()
    v = validate_manifest(m, adapter=_adapter())
    assert v.ok is True, v.to_dict()


def test_editable_grid_rejects_partial_adapter() -> None:
    class _Partial:
        adapter_id = "p"
        adapter_version = "1"
        def extract(self, *a, **k): ...
        def validate(self, *a, **k): ...
        # 缺 apply/diff/rebase/merge
    v = validate_manifest(_editable_manifest(), adapter=_Partial())
    assert v.ok is False
    assert any(g.code == "adapter_spi_incomplete" for g in v.gaps)


def test_editable_grid_requires_adapter_binding_in_manifest() -> None:
    m = _editable_manifest(adapter_bound=False)
    v = validate_manifest(m, adapter=_adapter())
    assert v.ok is False
    assert any(g.code == "adapter_binding_missing" for g in v.gaps)


def test_read_only_requires_extractor() -> None:
    ro = CustomProjectionManifest(
        manifest_version="m1", workbook_lineage_id="lin-1", sheet_uid="sheet:0:abcd",
        projection_mode=ProjectionMode.READ_ONLY_HTML,
        regions=(RegionMapping("r1", RegionKind.DATA, "A1:B10", True, False),),
        fields=(), row_identity=None, column_identity=None,
        formula_boundary_version="fb-1", preservation_decisions=(),
        adapter_id=None, adapter_version=None,
    )
    # 无 adapter → 无 extractor → 阻断
    v_none = validate_manifest(ro, adapter=None)
    assert v_none.ok is False
    assert any(g.code == "read_only_missing_extractor" for g in v_none.gaps)
    # 有 extractor → 通过
    v_ok = validate_manifest(ro, adapter=DeterministicExtractor())
    assert v_ok.ok is True, v_ok.to_dict()


def test_read_only_must_not_declare_managed_field() -> None:
    ro = CustomProjectionManifest(
        manifest_version="m1", workbook_lineage_id="lin-1", sheet_uid="s",
        projection_mode=ProjectionMode.READ_ONLY_HTML,
        regions=(RegionMapping("r1", RegionKind.DATA, "A1", False, False),),
        fields=(FieldMapping("f1", _field_identity(), "r1", True, "number"),),
        row_identity=None, column_identity=None,
        formula_boundary_version="fb", preservation_decisions=(),
        adapter_id=None, adapter_version=None,
    )
    v = validate_manifest(ro, adapter=DeterministicExtractor())
    assert v.ok is False
    assert any(g.code == "read_only_declares_managed_field" for g in v.gaps)


def test_onlyoffice_only_must_not_create_empty_grid_peer() -> None:
    oo = CustomProjectionManifest(
        manifest_version="m1", workbook_lineage_id="lin-1", sheet_uid="s",
        projection_mode=ProjectionMode.ONLYOFFICE_ONLY,
        regions=(),
        fields=(FieldMapping("f1", _field_identity(), "r1", False, "number"),),
        row_identity=None, column_identity=None,
        formula_boundary_version="fb", preservation_decisions=(),
        adapter_id=None, adapter_version=None,
    )
    v = validate_manifest(oo, adapter=None)
    assert v.ok is False
    assert any(g.code == "oo_only_declares_projection_fields" for g in v.gaps)


def test_onlyoffice_only_with_adapter_is_pseudo_bidirectional() -> None:
    oo = CustomProjectionManifest(
        manifest_version="m1", workbook_lineage_id="lin-1", sheet_uid="s",
        projection_mode=ProjectionMode.ONLYOFFICE_ONLY,
        regions=(), fields=(), row_identity=None, column_identity=None,
        formula_boundary_version="fb", preservation_decisions=(),
        adapter_id=None, adapter_version=None,
    )
    v = validate_manifest(oo, adapter=_adapter())
    assert v.ok is False
    assert any(g.code == "oo_only_declares_adapter" for g in v.gaps)


def test_dynamic_managed_region_requires_row_identity() -> None:
    region = RegionMapping("r1", RegionKind.DYNAMIC, "A1:B99", False, True)
    fld = FieldMapping("f1", _field_identity(), "r1", True, "number")
    m = CustomProjectionManifest(
        manifest_version="m1", workbook_lineage_id="lin-1", sheet_uid="s",
        projection_mode=ProjectionMode.EDITABLE_GRID,
        regions=(region,), fields=(fld,),
        row_identity=None,  # 动态受管却无行身份
        column_identity=None,
        formula_boundary_version="fb", preservation_decisions=(),
        adapter_id="fld-adapter", adapter_version="1.0",
    )
    v = validate_manifest(m, adapter=_adapter())
    assert v.ok is False
    assert any(g.code == "dynamic_region_missing_row_identity" for g in v.gaps)


def test_field_referencing_missing_region_is_flagged() -> None:
    fld = FieldMapping("f1", _field_identity(), "nope", True, "number")
    m = CustomProjectionManifest(
        manifest_version="m1", workbook_lineage_id="lin-1", sheet_uid="s",
        projection_mode=ProjectionMode.EDITABLE_GRID,
        regions=(RegionMapping("r1", RegionKind.DATA, "A1", False, False),),
        fields=(fld,), row_identity=IdentityRule("defined_name", "rowKey", False),
        column_identity=None, formula_boundary_version="fb",
        preservation_decisions=(), adapter_id="fld-adapter", adapter_version="1.0",
    )
    v = validate_manifest(m, adapter=_adapter())
    assert any(g.code == "field_region_dangling" for g in v.gaps)


# ─────────────────────────────────────────────────────────────────────────────
# 逐 sheet 确认 → 决策 (8.1 / 8.3)
# ─────────────────────────────────────────────────────────────────────────────


def _confirmation(mode: ProjectionMode, *, managed: bool = True, included: bool = True) -> SheetConfirmation:
    return SheetConfirmation(
        sheet_uid="sheet:0:abcd",
        business_name="应收账款检查表",
        wp_code="D5",
        included=included,
        requested_mode=mode,
        regions=(RegionMapping("r1", RegionKind.DATA, "A1:B10", False, False),),
        fields=(FieldMapping("f1", _field_identity(), "r1", managed, "number"),),
        row_identity=IdentityRule("defined_name", "rowKey", False),
        column_identity=None,
        formula_boundary_version="fb-1",
        preservation_decisions=(PreservationDecision("merge", "preserve"),),
    )


def test_excluded_sheet_produces_no_manifest() -> None:
    conf = _confirmation(ProjectionMode.EDITABLE_GRID, included=False)
    res = CarrierResolution(identity=_field_identity(), requires_instrumentation=False, downgrade_reason=None)
    decision = decide_sheet_mapping(
        conf, workbook_lineage_id="lin-1", manifest_version="m1",
        resolution=res, instrumented=None, adapter=_adapter(),
        adapter_id="fld-adapter", adapter_version="1.0",
    )
    assert decision.included is False
    assert decision.manifest is None
    assert decision.validation.ok is True


def test_included_editable_sheet_with_carrier_builds_valid_manifest() -> None:
    conf = _confirmation(ProjectionMode.EDITABLE_GRID)
    res = CarrierResolution(identity=_field_identity(), requires_instrumentation=False, downgrade_reason=None)
    decision = decide_sheet_mapping(
        conf, workbook_lineage_id="lin-1", manifest_version="m1",
        resolution=res, instrumented=None, adapter=_adapter(),
        adapter_id="fld-adapter", adapter_version="1.0",
    )
    assert decision.effective_mode is ProjectionMode.EDITABLE_GRID
    assert decision.downgraded is False
    assert decision.manifest is not None
    assert decision.blocked is False
    assert "f1" in decision.manifest.managed_field_ids


def test_included_editable_without_carrier_downgrades_and_drops_managed() -> None:
    conf = _confirmation(ProjectionMode.EDITABLE_GRID)
    res = CarrierResolution(
        identity=None, requires_instrumentation=False,
        downgrade_reason="no_existing_carrier_and_not_instrumentable",
    )
    decision = decide_sheet_mapping(
        conf, workbook_lineage_id="lin-1", manifest_version="m1",
        resolution=res, instrumented=None, adapter=DeterministicExtractor(),
    )
    assert decision.downgraded is True
    assert decision.effective_mode is ProjectionMode.READ_ONLY_HTML
    # 降级后无 managed field（不留隐藏空 Grid）
    assert decision.manifest is not None
    assert not decision.manifest.managed_field_ids
    assert decision.blocked is False
    assert decision.downgrade_reason == "no_existing_carrier_and_not_instrumentable"


# ─────────────────────────────────────────────────────────────────────────────
# adapter 六方法真实语义 (8.4)
# ─────────────────────────────────────────────────────────────────────────────


def test_adapter_conforms_to_spi_protocol() -> None:
    from app.services.custom_template_ingestion.adapters import CustomWorkbookAdapter
    assert isinstance(_adapter(), CustomWorkbookAdapter)


def test_extract_only_exposes_managed_fields() -> None:
    a = _adapter()
    m = _editable_manifest()
    data = encode_workbook_model({
        "managed": {"f1": 10, "hidden": 99},
        "unmanaged": {"chart1": "xml"},
    })
    snap = a.extract(data, m)
    assert snap.managed_values == {"f1": 10}  # hidden 非 managed 不暴露
    assert snap.unmanaged_parts == ("chart1",)


def test_validate_rejects_type_mismatch_and_unmanaged() -> None:
    a = _adapter()
    m = _editable_manifest()
    data = encode_workbook_model({"managed": {"f1": 1}, "unmanaged": {}})
    base = a.extract(data, m)
    res = a.validate(
        (ManagedMutation("f1", "not-a-number", "number"),
         ManagedMutation("ghost", 5, "number")),
        base,
    )
    assert res.ok is False
    assert any(e.startswith("type_mismatch:f1") for e in res.errors)
    assert any(e.startswith("unmanaged_or_unknown_field:ghost") for e in res.errors)


def test_apply_writes_managed_and_preserves_unmanaged() -> None:
    a = _adapter()
    m = _editable_manifest()
    staging = encode_workbook_model({"managed": {"f1": 1}, "unmanaged": {"chart": "x"}})
    result = a.apply(staging, (ManagedMutation("f1", 42, "number"),), m)
    assert result.ok is True and result.new_bytes is not None
    from app.services.custom_template_ingestion.adapters import decode_workbook_model
    model = decode_workbook_model(result.new_bytes)
    assert model["managed"]["f1"] == 42
    assert model["unmanaged"]["chart"] == "x"  # unmanaged 保留


def test_apply_rejects_unmanaged_field_mutation() -> None:
    a = _adapter()
    m = _editable_manifest()
    staging = encode_workbook_model({"managed": {"f1": 1}, "unmanaged": {}})
    result = a.apply(staging, (ManagedMutation("ghost", 1, "number"),), m)
    assert result.ok is False
    assert result.new_bytes is None


def test_diff_detects_lost_unmanaged_part() -> None:
    a = _adapter()
    m = _editable_manifest()
    before = encode_workbook_model({"managed": {"f1": 1}, "unmanaged": {"chart": "x", "img": "y"}})
    after = encode_workbook_model({"managed": {"f1": 2}, "unmanaged": {"chart": "x"}})  # img 丢了
    d = a.diff(before, after, m)
    assert "img" in d.lost_unmanaged
    assert "chart" in d.preserved_unmanaged
    assert "f1" in d.changed_managed
    assert d.unmanaged_preserved is False


# ─────────────────────────────────────────────────────────────────────────────
# three-way merge：不同字段自动合并；同字段冲突可见（禁 LWW）(8.4 基座)
# ─────────────────────────────────────────────────────────────────────────────


def _two_field_manifest() -> CustomProjectionManifest:
    region = RegionMapping("r1", RegionKind.DATA, "A1:B10", False, False)
    return CustomProjectionManifest(
        manifest_version="m1", workbook_lineage_id="lin-1", sheet_uid="s",
        projection_mode=ProjectionMode.EDITABLE_GRID,
        regions=(region,),
        fields=(
            FieldMapping("f1", _field_identity("k1"), "r1", True, "number"),
            FieldMapping("f2", _field_identity("k2"), "r1", True, "number"),
        ),
        row_identity=IdentityRule("defined_name", "k1", False),
        column_identity=None, formula_boundary_version="fb",
        preservation_decisions=(), adapter_id="fld-adapter", adapter_version="1.0",
    )


def test_merge_different_fields_auto_merges() -> None:
    a = _adapter()
    m = _two_field_manifest()
    base = encode_workbook_model({"managed": {"f1": 1, "f2": 1}, "unmanaged": {"chart": "x"}})
    current = encode_workbook_model({"managed": {"f1": 2, "f2": 1}, "unmanaged": {"chart": "x"}})  # 改 f1
    incoming = encode_workbook_model({"managed": {"f1": 1, "f2": 3}, "unmanaged": {"chart": "x"}})  # 改 f2
    res = a.merge(base, current, incoming, m)
    assert res.ok is True and not res.conflicts
    from app.services.custom_template_ingestion.adapters import decode_workbook_model
    merged = decode_workbook_model(res.merged_bytes)["managed"]
    assert merged["f1"] == 2  # current 改动
    assert merged["f2"] == 3  # incoming 改动


def test_merge_same_field_conflict_is_visible_not_lww() -> None:
    a = _adapter()
    m = _two_field_manifest()
    base = encode_workbook_model({"managed": {"f1": 1, "f2": 1}, "unmanaged": {}})
    current = encode_workbook_model({"managed": {"f1": 2, "f2": 1}, "unmanaged": {}})
    incoming = encode_workbook_model({"managed": {"f1": 9, "f2": 1}, "unmanaged": {}})  # f1 冲突
    res = a.merge(base, current, incoming, m)
    assert res.ok is False
    assert res.merged_bytes is None  # 冲突不产出静默合并结果
    assert len(res.conflicts) == 1
    c = res.conflicts[0]
    assert c.field_id == "f1"
    assert c.current_value == 2 and c.incoming_value == 9


def test_merge_preserves_unmanaged_parts() -> None:
    a = _adapter()
    m = _two_field_manifest()
    base = encode_workbook_model({"managed": {"f1": 1, "f2": 1}, "unmanaged": {"chart": "x"}})
    current = encode_workbook_model({"managed": {"f1": 2, "f2": 1}, "unmanaged": {"chart": "x"}})
    incoming = encode_workbook_model({"managed": {"f1": 2, "f2": 5}, "unmanaged": {"chart": "x"}})
    res = a.merge(base, current, incoming, m)
    assert res.ok is True
    assert res.preservation.unmanaged_preserved is True


def test_rebase_reports_conflict_when_current_moved_same_field() -> None:
    a = _adapter()
    base = encode_workbook_model({"managed": {"f1": 1}, "unmanaged": {}})
    current = encode_workbook_model({"managed": {"f1": 5}, "unmanaged": {}})  # current 改了 f1
    incoming = (ManagedMutation("f1", 9, "number"),)  # incoming 也改 f1 为不同值
    res = a.rebase(base, current, incoming)
    assert res.ok is False
    assert res.conflicts and res.conflicts[0].field_id == "f1"


def test_manifest_is_immutable_and_versioned() -> None:
    m = _editable_manifest()
    with pytest.raises(Exception):
        m.manifest_version = "m2"  # frozen dataclass
    # digest 稳定可复现
    assert m.digest == _editable_manifest().digest
