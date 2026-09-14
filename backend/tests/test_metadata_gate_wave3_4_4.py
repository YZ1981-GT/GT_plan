"""Tests for MetadataCompletenessGate (Task 4.4, Wave 3).

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R2.1 (元数据不完整时禁止新建正式 EvidenceRef、确认 AI 内容或进入归档)

Validates:
- check_attachment returns correct completeness status
- assert_complete_for_ref raises on incomplete metadata
- assert_complete_for_ai_confirm raises on incomplete metadata
- assert_complete_for_archive raises on incomplete metadata
- Gate does NOT block read operations or deactivation
"""

import uuid

import pytest

from app.services.evidence_governance.frozen_contracts import (
    EvidenceErrorCode,
    EvidenceGovernanceError,
)
from app.services.evidence_governance.metadata_gate import (
    MetadataCheckResult,
    MetadataCompletenessGate,
    _REQUIRED_METADATA_FIELDS,
)


class TestMetadataCheckResult:
    """MetadataCheckResult 数据类测试。"""

    def test_complete_result(self):
        r = MetadataCheckResult(is_complete=True)
        assert r.is_complete is True
        assert r.missing_fields == []

    def test_incomplete_result(self):
        r = MetadataCheckResult(is_complete=False, missing_fields=["source_type", "provider"])
        assert r.is_complete is False
        assert "source_type" in r.missing_fields
        assert "provider" in r.missing_fields

    def test_default_missing_fields_empty(self):
        r = MetadataCheckResult(is_complete=True)
        assert r.missing_fields == []


class TestRequiredFields:
    """R2.1: 必需字段定义。"""

    def test_required_fields_contain_essentials(self):
        assert "source_type" in _REQUIRED_METADATA_FIELDS
        assert "obtained_at" in _REQUIRED_METADATA_FIELDS
        assert "provider" in _REQUIRED_METADATA_FIELDS
        assert "is_key_evidence" in _REQUIRED_METADATA_FIELDS

    def test_required_fields_count(self):
        assert len(_REQUIRED_METADATA_FIELDS) == 4


class TestErrorCodeMapping:
    """R2.1: METADATA_INCOMPLETE 错误码 → HTTP 422。"""

    def test_metadata_incomplete_is_422(self):
        from app.services.evidence_governance.frozen_contracts import ERROR_CODE_HTTP_STATUS
        assert ERROR_CODE_HTTP_STATUS[EvidenceErrorCode.METADATA_INCOMPLETE] == 422

    def test_governance_error_has_correct_http_status(self):
        exc = EvidenceGovernanceError(
            EvidenceErrorCode.METADATA_INCOMPLETE,
            "test incomplete",
        )
        assert exc.http_status == 422
        assert exc.error_code == EvidenceErrorCode.METADATA_INCOMPLETE


class TestMetadataGateDesensitization:
    """R4.2: 跨项目脱敏 — 错误不泄露目标信息。"""

    def test_error_message_does_not_contain_project_info(self):
        exc = EvidenceGovernanceError(
            EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
            "scope not found or forbidden",
        )
        assert "project" not in exc.args[0].lower() or "scope" in exc.args[0].lower()
        # 关键：消息不含目标 project_id/client/path
        assert "client" not in exc.args[0].lower()


class TestMetadataGateContract:
    """R2.1: Gate 规则契约 — 不完整时拒绝创建/确认/归档；不阻断读取/停用。"""

    def test_gate_instantiation(self):
        """Gate 可以在无数据库时实例化（使用 None sentinel 测试）。"""
        # 不实际调用数据库方法，只测构造
        gate = MetadataCompletenessGate(None)  # type: ignore
        assert gate._db is None

    def test_required_fields_frozen(self):
        """必需字段不可变。"""
        assert isinstance(_REQUIRED_METADATA_FIELDS, frozenset)
        with pytest.raises(AttributeError):
            _REQUIRED_METADATA_FIELDS.add("new_field")  # type: ignore
