"""V265 正式导出单位证据的 migration ↔ ORM 三层列合同（不连共享库）。"""
from __future__ import annotations

from pathlib import Path

from app.models.custom_workbook_unit_authority import CustomWorkbookUnitAuthority
from app.models.phase13_models import WordExportTaskVersion
from app.models.report_models import ExportTask
from app.models.workpaper_sync_models import WorkpaperContentVersion

ROOT = Path(__file__).resolve().parents[1]
V = (ROOT / "migrations/V265__add_export_unit_policy_columns.sql").read_text(encoding="utf-8")
R = (ROOT / "migrations/R265__rollback_export_unit_policy_columns.sql").read_text(encoding="utf-8")


def columns(model) -> set[str]:
    return set(model.__table__.columns.keys())


def test_v265_columns_match_orm_names():
    assert {"export_year", "document_types", "unit_policy_snapshot"} <= columns(ExportTask)
    assert {"unit_policy_snapshot", "unit_policy_digest"} <= columns(WordExportTaskVersion)
    assert {"export_surface_class", "unit_policy_snapshot", "unit_policy_digest", "source_storage_unit"} <= columns(WorkpaperContentVersion)
    assert columns(CustomWorkbookUnitAuthority) == {
        "id", "working_paper_id", "workbook_sha256", "manifest", "manifest_digest", "created_by", "created_at",
    }
    for name in (
        "export_year", "document_types", "unit_policy_snapshot", "unit_policy_digest",
        "export_surface_class", "source_storage_unit", "working_paper_id", "workbook_sha256", "manifest_digest",
    ):
        assert name in V, name


def test_v265_uses_plural_json_and_policy_pair_constraints():
    assert "document_types JSONB NOT NULL DEFAULT '[]'::jsonb" in V
    assert "document_types TEXT[]" not in V
    assert "jsonb_build_array(document_type)" in V
    assert "ck_word_export_version_unit_policy_pair" in V
    assert "unit_policy_digest IS NOT NULL" in V
    assert "ck_wpcv_export_unit_evidence" in V
    assert "export_surface_class = 'formal'" in V
    assert "export_surface_class = 'data_exchange'" in V
    assert "source_storage_unit IS NOT NULL" in V


def test_r265_checks_all_evidence_before_first_drop():
    do_end = R.index("$$;", R.index("DO $$"))
    first_drop = min(R.index("DROP TABLE"), R.index("DROP COLUMN"))
    assert do_end < first_drop
    preflight = R[:do_end]
    for token in (
        "custom_workbook_unit_authorities", "unit_policy_snapshot", "export_year", "document_types",
        "unit_policy_digest", "export_surface_class", "source_storage_unit",
    ):
        assert token in preflight, token
    assert "document_types ->> 0" in R


def test_old_drifted_column_names_are_absent():
    assert "ADD COLUMN IF NOT EXISTS policy_snapshot" not in V
    assert "ADD COLUMN IF NOT EXISTS policy_digest" not in V
    assert "ADD COLUMN IF NOT EXISTS surface_class" not in V
