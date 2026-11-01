"""V241/V242 不可变资产与溯源迁移三层契约。"""
from __future__ import annotations

from pathlib import Path

from app.models.asset_blob_models import AiChatRunResource, AssetBlob, KnowledgeEvidencePromotion
from app.models.evidence_governance_models import AttachmentVersion
from app.models.knowledge_models import KnowledgeDocument


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "migrations"


def test_v241_schema_matches_orm_and_has_safe_rollback() -> None:
    up = (MIGRATIONS / "V241__asset_blob_foundation.sql").read_text(encoding="utf-8")
    down = (MIGRATIONS / "R241__asset_blob_foundation.sql").read_text(encoding="utf-8")
    assert {column.name for column in AssetBlob.__table__.c} >= {
        "id", "content_hash", "byte_size", "storage_type", "storage_key",
        "security_status", "actor_type", "actor_user_id", "actor_service_identity_id",
    }
    assert "blob_id" in AttachmentVersion.__table__.c
    assert "blob_id" in KnowledgeDocument.__table__.c
    assert {column.name for column in KnowledgeEvidencePromotion.__table__.c} >= {
        "source_document_id", "source_document_version", "source_blob_id", "source_hash",
        "target_attachment_id", "target_attachment_version_id", "project_id", "audit_year",
    }
    assert {column.name for column in AiChatRunResource.__table__.c} >= {
        "run_id", "session_id", "resource_kind", "resource_id",
        "attachment_version_id", "blob_id", "content_hash", "actor_user_id",
    }
    for required in (
        "gt_asset_blob_immutable", "gt_knowledge_evidence_promotion_append_only",
        "gt_ai_run_resource_immutable", "ck_ai_run_project_attachment_pin",
        "evgov_attachment_version_immutable",
    ):
        assert required in up
    assert "RAISE EXCEPTION" in down and "DROP COLUMN IF EXISTS blob_id" in down
    assert down.index("CREATE OR REPLACE FUNCTION evgov_attachment_version_immutable") < down.index(
        "ALTER TABLE attachment_versions DROP COLUMN IF EXISTS blob_id"
    )


def test_v242_lineage_unique_migration_refuses_silent_deduplication() -> None:
    up = (MIGRATIONS / "V242__attachment_lineage_identity_unique.sql").read_text(encoding="utf-8")
    down = (MIGRATIONS / "R242__attachment_lineage_identity_unique.sql").read_text(encoding="utf-8")
    assert "HAVING COUNT(*) > 1" in up
    assert "RAISE EXCEPTION" in up
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_attachment_lineage_identity" in up
    assert "DELETE FROM attachment_lineage" not in up
    assert "DROP INDEX IF EXISTS uq_attachment_lineage_identity" in down
