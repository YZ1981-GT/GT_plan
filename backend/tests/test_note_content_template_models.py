"""V187 附注内容模板三层字段与严格 schema 契约。"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.migration_runner import MigrationRunner
from app.models.note_content_template_models import (
    NoteContentTemplate,
    NoteContentTemplateVersion,
    NoteTextBatchApplication,
)
from app.models.note_content_template_schemas import (
    BatchApplyRequest,
    BatchSource,
    BatchSourceKind,
    NoteSectionKind,
    OwnerScope,
    SnapshotPreviewRequest,
)

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"


def test_v187_is_unique_and_has_rollback_pair() -> None:
    runner = MigrationRunner(
        database_url="sqlite+aiosqlite:///:memory:", migrations_dir=MIGRATIONS
    )
    matches = [m for m in runner.scan_migrations() if int(m.version) == 187]
    assert len(matches) == 1
    assert (MIGRATIONS / "R187__rollback_note_content_templates_and_batch_apply.sql").is_file()


def test_v187_declares_all_tables_and_idempotent_guards() -> None:
    ddl = (MIGRATIONS / "V187__note_content_templates_and_batch_apply.sql").read_text(
        encoding="utf-8"
    )
    for table in (
        "note_content_templates",
        "note_content_template_versions",
        "note_text_batch_applications",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in ddl
    assert "IF NOT EXISTS" in ddl
    assert "fk_nct_current_version" in ddl


def test_orm_tables_have_required_columns() -> None:
    assert set(NoteContentTemplate.__table__.columns.keys()) == {
        "id", "name", "description", "owner_scope", "owner_user_id",
        "owner_group_project_id", "current_version_id", "is_deleted", "deleted_at",
        "created_by", "created_at", "updated_at",
    }
    assert set(NoteContentTemplateVersion.__table__.columns.keys()) == {
        "id", "template_id", "version_no", "schema_version", "source_project_id",
        "source_year", "source_project_name", "template_type", "report_scope",
        "sections_data", "quality_summary", "content_hash", "byte_size",
        "created_by", "created_at",
    }
    assert set(NoteTextBatchApplication.__table__.columns.keys()) == {
        "id", "source_kind", "template_version_id", "source_metadata",
        "target_project_id", "target_year", "mutation_id", "request_fingerprint",
        "preview_digest", "applied_count", "mode_summary", "detail", "status",
        "applied_by", "applied_at",
    }


def test_strict_enums_expose_only_designed_values() -> None:
    assert {item.value for item in OwnerScope} == {"personal", "group"}
    assert {item.value for item in BatchSourceKind} == {
        "upload", "knowledge", "content_template"
    }
    assert {item.value for item in NoteSectionKind} == {
        "narrative", "account_explanation", "container"
    }
    with pytest.raises(ValidationError):
        SnapshotPreviewRequest(year=2025, name="模板", owner_scope="public")


def test_batch_source_shape_rejects_client_template_content() -> None:
    with pytest.raises(ValidationError):
        BatchSource(
            source_kind="content_template",
            template_version_id="00000000-0000-0000-0000-000000000001",
            template_content_hash="0" * 64,
            parsed_source={"source_kind": "upload", "sections": []},
        )


def test_apply_schema_rejects_free_mode_before_database() -> None:
    with pytest.raises(ValidationError):
        BatchApplyRequest.model_validate({
            "year": 2025,
            "source": {
                "source_kind": "upload",
                "parsed_source": {"source_kind": "upload", "sections": []},
            },
            "preview_digest": "0" * 64,
            "selections": [{
                "source_id": "s1",
                "target_note_id": "00000000-0000-0000-0000-000000000002",
                "mode": "merge",
                "before_hash": "1" * 64,
                "proposed_hash": "2" * 64,
                "proposed_html": "<p>x</p>",
            }],
        })
