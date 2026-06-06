"""附件影响范围 service 结构测试 (MVP stub)."""
from backend.app.services.attachment_impact_service import get_attachment_impact


class TestAttachmentImpactService:
    def test_returns_expected_structure(self):
        result = get_attachment_impact("proj-001", "att-123")
        assert "references_count" in result
        assert "referenced_by" in result
        assert isinstance(result["references_count"], int)
        assert isinstance(result["referenced_by"], list)

    def test_mvp_stub_returns_zero(self):
        result = get_attachment_impact("proj-x", "att-y")
        assert result["references_count"] == 0
        assert result["referenced_by"] == []

    def test_preserves_ids(self):
        result = get_attachment_impact("p1", "a1")
        assert result["project_id"] == "p1"
        assert result["attachment_id"] == "a1"
