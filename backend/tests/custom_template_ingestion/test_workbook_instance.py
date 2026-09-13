"""Task 10 守卫：整册 instance + child entries + namespace gate 探测。

Feature: custom-workpaper-template-ingestion-and-sync-closure
Validates: Requirements 7.1–7.7
"""
from __future__ import annotations

import uuid

import pytest

from app.services.guidance_gid import StableSheetIdentity
from app.services.custom_template_ingestion.mapping import ProjectionMode
from app.services.custom_template_ingestion.workbook_instance import (
    SheetSeed,
    WorkbookInstanceError,
    advance_generation,
    create_workbook_instance,
    rename_sheet_code,
    reorder_sheets,
)
from app.services.custom_template_ingestion.namespace_migration import (
    MultiResolverDeferredError,
    NamespaceSplitError,
    assert_sync_entry_namespace_unified,
    assert_sync_multi_resolver_cleared,
    migration_plan_for_instance,
    probe_namespace_gates,
    unified_child_entry_id,
)


def _sheet(uid: str, wp: str = "CX-1") -> StableSheetIdentity:
    return StableSheetIdentity(
        template_lineage_id="lin-cx",
        template_version_id="ver-1",
        wp_code=wp,
        sheet_uid=uid,
        sheet_code=f"code-{uid}",
    )


def _seed(uid: str, order_hint: str = "A") -> SheetSeed:
    return SheetSeed(
        sheet=_sheet(uid),
        sheet_code=order_hint,
        wp_code="CX-1",
        component_type="custom_grid",
        projection_mode=ProjectionMode.EDITABLE_GRID,
        manifest_version="m1",
    )


def test_one_xlsx_one_instance_n_children_share_artifact_and_generation():
    inst = create_workbook_instance(
        organization_id="org-1",
        project_id="proj-1",
        wp_id=str(uuid.uuid4()),
        workbook_lineage_id="lin-cx",
        pinned_template_version_id="ver-1",
        current_artifact_id="art-1",
        content_revision="c1",
        representation_revision="r1",
        sheets=[_seed("s1", "A"), _seed("s2", "B"), _seed("s3", "C")],
        onlyoffice_room_id="room-shared",
    )
    assert inst.child_count == 3
    assert len({c.workbook_instance_id for c in inst.children}) == 1
    assert all(c.workbook_instance_id == inst.workbook_instance_id for c in inst.children)
    # 禁止按 sheet 复制 room / artifact
    assert inst.onlyoffice_room_id == "room-shared"
    assert inst.current_artifact_id == "art-1"
    assert inst.workbook_generation == 1
    # 统一 namespace，不是 opaque-
    for c in inst.children:
        assert c.entry_id.startswith("pwi-")
        assert not c.entry_id.startswith("opaque-")
        assert c.sheet_uid in c.entry_id


def test_duplicate_sheet_uid_rejected():
    with pytest.raises(WorkbookInstanceError, match="重复 sheet_uid"):
        create_workbook_instance(
            organization_id="o",
            project_id="p",
            wp_id="w",
            workbook_lineage_id="l",
            pinned_template_version_id="v",
            current_artifact_id="a",
            content_revision="c",
            representation_revision="r",
            sheets=[_seed("same"), _seed("same")],
        )


def test_empty_sheets_rejected():
    with pytest.raises(WorkbookInstanceError):
        create_workbook_instance(
            organization_id="o",
            project_id="p",
            wp_id="w",
            workbook_lineage_id="l",
            pinned_template_version_id="v",
            current_artifact_id="a",
            content_revision="c",
            representation_revision="r",
            sheets=[],
        )


def test_advance_generation_refreshes_only_affected_children():
    inst = create_workbook_instance(
        organization_id="o",
        project_id="p",
        wp_id="w",
        workbook_lineage_id="l",
        pinned_template_version_id="v",
        current_artifact_id="a",
        content_revision="c1",
        representation_revision="r1",
        sheets=[_seed("s1"), _seed("s2")],
    )
    nxt = advance_generation(
        inst,
        affected_sheet_uids={"s1"},
        new_content_revision="c2",
    )
    assert nxt.workbook_generation == 2
    assert nxt.content_revision == "c2"
    assert nxt.child_by_sheet_uid("s1").projection_generation == 2
    assert nxt.child_by_sheet_uid("s2").projection_generation == 1
    # entry_id 不变
    assert nxt.child_by_sheet_uid("s1").entry_id == inst.child_by_sheet_uid("s1").entry_id


def test_rename_and_reorder_preserve_entry_ids():
    inst = create_workbook_instance(
        organization_id="o",
        project_id="p",
        wp_id="w",
        workbook_lineage_id="l",
        pinned_template_version_id="v",
        current_artifact_id="a",
        content_revision="c",
        representation_revision="r",
        sheets=[_seed("s1", "A"), _seed("s2", "B")],
    )
    ids_before = {c.sheet_uid: c.entry_id for c in inst.children}
    renamed = rename_sheet_code(inst, sheet_uid="s1", new_sheet_code="A-renamed", new_wp_code="CX-9")
    assert renamed.child_by_sheet_uid("s1").entry_id == ids_before["s1"]
    assert renamed.child_by_sheet_uid("s1").sheet_code == "A-renamed"
    assert renamed.child_by_sheet_uid("s1").wp_code == "CX-9"

    reordered = reorder_sheets(renamed, ordered_sheet_uids=["s2", "s1"])
    assert {c.sheet_uid: c.entry_id for c in reordered.children} == ids_before
    assert reordered.child_by_sheet_uid("s2").display_order == 0
    assert reordered.child_by_sheet_uid("s1").display_order == 1


def test_unified_entry_id_format():
    eid = unified_child_entry_id(workbook_instance_id="abc", sheet_uid="sheet-1")
    assert eid == "pwi-abc:sheet-1"


def test_migration_plan_shows_legacy_divergence():
    wp_id = uuid.uuid4()
    plan = migration_plan_for_instance(
        workbook_instance_id="wid-1",
        sheet_uid="s1",
        wp_code="CX-1",
        wp_id=wp_id,
    )
    assert plan["legacy_ids_diverge"] is True
    assert plan["unified_entry_id"].startswith("pwi-")
    assert plan["legacy_opaque_ids"]["custom_cells_lane"].startswith("opaque-")
    assert plan["legacy_opaque_ids"]["wopi_or_offline_lane"].startswith("opaque-")


def test_namespace_gates_currently_blocked():
    """诚实锁死：平台 SYNC gate 未归零时不得宣称统一完成。"""
    report = probe_namespace_gates()
    assert report.entry_namespace_unified is False
    assert report.multi_resolver_cleared is False
    assert report.multi_resolver_count == 4
    assert report.blockers

    with pytest.raises(NamespaceSplitError):
        assert_sync_entry_namespace_unified()
    with pytest.raises(MultiResolverDeferredError):
        assert_sync_multi_resolver_cleared()
