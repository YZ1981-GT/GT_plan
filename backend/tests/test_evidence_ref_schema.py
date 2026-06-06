"""EvidenceRef schema 序列化与类型覆盖测试."""
import pytest
from backend.app.schemas.evidence_ref import EvidenceRef, EvidenceType


class TestEvidenceType:
    def test_all_evidence_types_exist(self):
        expected = {
            "attachment", "workpaper_cell", "report_paragraph",
            "note_table", "ai_output", "deliverable",
        }
        assert {e.value for e in EvidenceType} == expected


class TestEvidenceRefSerialization:
    def test_minimal_fields(self):
        ref = EvidenceRef(
            evidence_type=EvidenceType.attachment,
            evidence_id="att-001",
            project_id="proj-001",
        )
        data = ref.model_dump()
        assert data["evidence_type"] == "attachment"
        assert data["evidence_id"] == "att-001"
        assert data["year"] is None

    def test_full_fields(self):
        ref = EvidenceRef(
            evidence_type=EvidenceType.ai_output,
            evidence_id="ai-999",
            project_id="proj-002",
            year=2025,
            label="AI 生成摘要",
            route="/projects/proj-002/ai/ai-999",
            hash="abc123",
            version="v2",
        )
        data = ref.model_dump()
        assert data["year"] == 2025
        assert data["label"] == "AI 生成摘要"
        assert data["hash"] == "abc123"
        assert data["version"] == "v2"

    @pytest.mark.parametrize("etype", list(EvidenceType))
    def test_each_type_serializable(self, etype: EvidenceType):
        ref = EvidenceRef(
            evidence_type=etype,
            evidence_id=f"id-{etype.value}",
            project_id="proj-x",
        )
        data = ref.model_dump()
        assert data["evidence_type"] == etype.value

    def test_json_roundtrip(self):
        ref = EvidenceRef(
            evidence_type=EvidenceType.deliverable,
            evidence_id="del-01",
            project_id="proj-03",
            year=2024,
        )
        json_str = ref.model_dump_json()
        restored = EvidenceRef.model_validate_json(json_str)
        assert restored == ref
