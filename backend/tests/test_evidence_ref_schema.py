"""EvidenceRef schema 序列化、类型覆盖与路由解析测试 (P0-2)."""
import pytest
from backend.app.schemas.evidence_ref import (
    EvidenceRef,
    EvidenceType,
    resolve_evidence_route,
)


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


class TestEvidenceRefRouteResolve:
    """P0-2.4: EvidenceRef 可跳转测试。"""

    @pytest.mark.parametrize("etype,expected_pattern", [
        (EvidenceType.attachment, "/projects/p1/attachments/e1"),
        (EvidenceType.workpaper_cell, "/projects/p1/workpapers/e1"),
        (EvidenceType.report_paragraph, "/projects/p1/report/e1"),
        (EvidenceType.note_table, "/projects/p1/notes/e1"),
        (EvidenceType.ai_output, "/projects/p1/ai-content/e1"),
        (EvidenceType.deliverable, "/projects/p1/deliverables/e1"),
    ])
    def test_auto_route_generation(self, etype: EvidenceType, expected_pattern: str):
        """各 evidence_type 自动生成正确路由。"""
        ref = EvidenceRef(
            evidence_type=etype,
            evidence_id="e1",
            project_id="p1",
        )
        assert ref.route == expected_pattern

    def test_explicit_route_preserved(self):
        """显式指定 route 时不被自动生成覆盖。"""
        ref = EvidenceRef(
            evidence_type=EvidenceType.attachment,
            evidence_id="e1",
            project_id="p1",
            route="/custom/path",
        )
        assert ref.route == "/custom/path"

    def test_resolve_route_method(self):
        ref = EvidenceRef(
            evidence_type=EvidenceType.note_table,
            evidence_id="nt-5",
            project_id="proj-99",
        )
        assert ref.resolve_route() == "/projects/proj-99/notes/nt-5"

    def test_resolve_evidence_route_utility(self):
        ref = EvidenceRef(
            evidence_type=EvidenceType.ai_output,
            evidence_id="ai-7",
            project_id="proj-42",
        )
        assert resolve_evidence_route(ref) == "/projects/proj-42/ai-content/ai-7"
