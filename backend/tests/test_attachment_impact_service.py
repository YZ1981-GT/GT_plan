"""附件影响范围 service 测试 (P0-3).

覆盖：
- P0-3.4 三层一致契约测试（schema/service 对齐）
- P0-3.8 被引用关键附件删除必须确认
"""
import pytest
from backend.app.schemas.attachment_evidence import (
    AttachmentEvidenceMetadata,
    AttachmentImpactItem,
    AttachmentImpactResult,
)
from backend.app.services.attachment_impact_service import (
    get_attachment_impact,
    get_evidence_metadata,
    set_evidence_metadata,
)


class TestAttachmentEvidenceMetadata:
    """P0-3.3: 证据属性元数据 schema 一致性。"""

    def test_default_metadata(self):
        meta = AttachmentEvidenceMetadata()
        assert meta.is_key_evidence is False
        assert meta.reference_count == 0
        assert meta.linked_workpapers == []

    def test_full_metadata(self):
        meta = AttachmentEvidenceMetadata(
            source="客户提供",
            obtained_date="2025-06-01",
            provider="XX公司财务部",
            is_key_evidence=True,
            linked_workpapers=["wp-1", "wp-2"],
            reference_count=3,
        )
        assert meta.source == "客户提供"
        assert meta.is_key_evidence is True
        assert len(meta.linked_workpapers) == 2

    def test_json_roundtrip(self):
        meta = AttachmentEvidenceMetadata(
            source="第三方获取",
            is_key_evidence=True,
            reference_count=5,
        )
        json_str = meta.model_dump_json()
        restored = AttachmentEvidenceMetadata.model_validate_json(json_str)
        assert restored == meta


class TestEvidenceMetadataReadWrite:
    """P0-3.3: metadata JSON 读写一致。"""

    def test_get_from_empty_cache(self):
        meta = get_evidence_metadata(None)
        assert meta.is_key_evidence is False

    def test_get_from_cache_without_evidence_key(self):
        meta = get_evidence_metadata({"ocr_text": "some text"})
        assert meta.is_key_evidence is False

    def test_set_and_get_roundtrip(self):
        original = AttachmentEvidenceMetadata(
            source="自行编制",
            is_key_evidence=True,
            provider="审计团队",
        )
        cache = set_evidence_metadata(None, original)
        assert "evidence" in cache
        restored = get_evidence_metadata(cache)
        assert restored.source == "自行编制"
        assert restored.is_key_evidence is True
        assert restored.provider == "审计团队"

    def test_preserves_other_cache_keys(self):
        existing_cache = {"ocr_text": "hello", "confidence": 0.95}
        meta = AttachmentEvidenceMetadata(is_key_evidence=True)
        result = set_evidence_metadata(existing_cache, meta)
        assert result["ocr_text"] == "hello"
        assert result["confidence"] == 0.95
        assert result["evidence"]["is_key_evidence"] is True


class TestAttachmentImpactService:
    """P0-3.6/3.7: 影响范围查询。"""

    def test_no_references_returns_zero(self):
        result = get_attachment_impact("proj-1", "att-1")
        assert result.references_count == 0
        assert result.referenced_by == []
        assert result.requires_confirmation is False

    def test_with_references(self):
        refs = [
            {"module": "workpaper", "module_id": "wp-1", "module_label": "货币资金底稿"},
            {"module": "report", "module_id": "rp-1", "module_label": "审计报告第三段"},
        ]
        result = get_attachment_impact("proj-1", "att-2", references=refs)
        assert result.references_count == 2
        assert result.referenced_by[0].module == "workpaper"
        assert result.referenced_by[1].module_label == "审计报告第三段"

    def test_preserves_ids(self):
        result = get_attachment_impact("p1", "a1")
        assert result.project_id == "p1"
        assert result.attachment_id == "a1"


class TestKeyEvidenceDeletionConfirmation:
    """P0-3.8: 被引用关键附件删除必须确认。

    Property 1: 关键证据不可无提示删除。
    """

    def test_key_evidence_with_references_requires_confirmation(self):
        """关键证据被引用 → 必须确认。"""
        refs = [{"module": "workpaper", "module_id": "wp-1", "module_label": "底稿"}]
        result = get_attachment_impact(
            "proj-1", "att-key",
            references=refs,
            is_key_evidence=True,
        )
        assert result.requires_confirmation is True

    def test_key_evidence_without_references_no_confirmation(self):
        """关键证据无引用 → 不强制确认。"""
        result = get_attachment_impact(
            "proj-1", "att-key",
            is_key_evidence=True,
        )
        assert result.requires_confirmation is False

    def test_non_key_evidence_with_references_no_confirmation(self):
        """非关键证据有引用 → 不强制确认（可自由删除）。"""
        refs = [{"module": "note", "module_id": "n-1", "module_label": "附注"}]
        result = get_attachment_impact(
            "proj-1", "att-normal",
            references=refs,
            is_key_evidence=False,
        )
        assert result.requires_confirmation is False

    def test_impact_result_schema_contract(self):
        """P0-3.4: 三层一致 — AttachmentImpactResult 字段齐全。"""
        result = get_attachment_impact(
            "proj-1", "att-1",
            file_name="银行对账单.pdf",
            is_key_evidence=True,
            references=[
                {"module": "workpaper", "module_id": "wp-1", "module_label": "E1 货币资金", "route": "/wp/wp-1"},
            ],
        )
        # 验证所有字段存在且类型正确
        data = result.model_dump()
        assert data["project_id"] == "proj-1"
        assert data["attachment_id"] == "att-1"
        assert data["file_name"] == "银行对账单.pdf"
        assert data["is_key_evidence"] is True
        assert data["references_count"] == 1
        assert data["requires_confirmation"] is True
        assert data["referenced_by"][0]["route"] == "/wp/wp-1"
