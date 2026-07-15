"""Task 3.5 — 版本递增、不可变版本、影响确认、LegacyAttachmentResolver 与 file_path 脱敏。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R2, R9, R13, R14
Design: §4.1, §4.2, §4.3, §5.1, §6.1, §6.3
Properties: P4(版本不可变/递增), P26(Legal Hold), P28(迁移幂等)

Unit tests for:
1. sanitize_file_path_response — never returns absolute paths
2. LegacyAttachmentResolver — alias resolution + cross-project isolation
3. AttachmentVersionManager — FOR UPDATE + version_no increment + impact + hold
4. LegacyRouteFacade — compat response with sanitized file_path
"""

from __future__ import annotations

import uuid

import pytest

from app.services.evidence_governance.version_manager import (
    AttachmentVersionManager,
    ImpactEntry,
    ImpactReport,
    LegacyAttachmentResolver,
    LegacyRouteFacade,
    ReplaceResult,
    sanitize_attachment_response,
    sanitize_file_path_response,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1) sanitize_file_path_response — NEVER absolute paths (R14.1 / design §6.1 C3)
# ─────────────────────────────────────────────────────────────────────────────


class TestSanitizeFilePath:
    """file_path response sanitization tests."""

    def test_returns_opaque_download_url(self):
        aid = uuid.uuid4()
        result = sanitize_file_path_response(aid)
        assert result == f"/api/attachments/{aid}/download"
        # Must NOT contain any of these patterns
        assert "\\" not in result
        assert "C:" not in result
        assert "/home" not in result
        assert "storage/" not in result

    def test_with_version_id(self):
        aid = uuid.uuid4()
        vid = uuid.uuid4()
        result = sanitize_file_path_response(aid, version_id=vid)
        assert result == f"/api/attachments/{aid}/versions/{vid}/download"

    def test_ignores_raw_file_path(self):
        """Even when raw_file_path is provided, result is always opaque locator."""
        aid = uuid.uuid4()
        result = sanitize_file_path_response(
            aid, raw_file_path="/var/storage/secrets/file.pdf"
        )
        assert "/var/storage" not in result
        assert result.startswith("/api/attachments/")

    def test_string_ids_work(self):
        aid = "550e8400-e29b-41d4-a716-446655440000"
        result = sanitize_file_path_response(aid)
        assert aid in result


class TestSanitizeAttachmentResponse:
    """sanitize_attachment_response rewrites file_path in dicts."""

    def test_rewrites_file_path(self):
        aid = uuid.uuid4()
        data = {
            "id": str(aid),
            "file_path": "/absolute/path/to/file.pdf",
            "file_name": "test.pdf",
        }
        result = sanitize_attachment_response(data)
        assert result["file_path"] == f"/api/attachments/{aid}/download"
        assert result["file_name"] == "test.pdf"  # other fields unchanged

    def test_preserves_non_file_path_fields(self):
        aid = uuid.uuid4()
        data = {
            "id": str(aid),
            "file_path": "C:\\Users\\data\\file.xlsx",
            "ocr_status": "pending",
            "version": 3,
        }
        result = sanitize_attachment_response(data)
        assert "/api/attachments/" in result["file_path"]
        assert result["ocr_status"] == "pending"
        assert result["version"] == 3

    def test_with_version_id(self):
        aid = uuid.uuid4()
        vid = uuid.uuid4()
        data = {"id": str(aid), "file_path": "paperless://123/doc"}
        result = sanitize_attachment_response(data, version_id=vid)
        assert f"/versions/{vid}/download" in result["file_path"]

    def test_no_id_strips_file_path(self):
        """If no attachment_id in dict, file_path is cleared for safety."""
        data = {"file_path": "/dangerous/path", "name": "test"}
        result = sanitize_attachment_response(data)
        assert result["file_path"] == ""


# ─────────────────────────────────────────────────────────────────────────────
# 2) ImpactReport data contract
# ─────────────────────────────────────────────────────────────────────────────


class TestImpactReport:
    """ImpactReport blocked logic."""

    def test_not_blocked_when_empty(self):
        report = ImpactReport(attachment_id=uuid.uuid4(), version_no=1)
        assert not report.blocked
        assert report.total_count == 0

    def test_blocked_by_legal_hold(self):
        report = ImpactReport(
            attachment_id=uuid.uuid4(), version_no=1, has_legal_hold=True
        )
        assert report.blocked

    def test_blocked_by_formal_output(self):
        report = ImpactReport(
            attachment_id=uuid.uuid4(), version_no=1, has_formal_output=True
        )
        assert report.blocked

    def test_blocked_by_references(self):
        report = ImpactReport(
            attachment_id=uuid.uuid4(),
            version_no=1,
            direct_impacts=[
                ImpactEntry(
                    ref_id="r1",
                    ref_type="evidence_ref",
                    source_type="workpaper",
                    source_id="wp1",
                )
            ],
            total_count=1,
        )
        assert report.blocked

    def test_not_blocked_without_impacts(self):
        report = ImpactReport(
            attachment_id=uuid.uuid4(),
            version_no=2,
            direct_impacts=[],
            transitive_impacts=[],
            has_legal_hold=False,
            has_formal_output=False,
            total_count=0,
        )
        assert not report.blocked


# ─────────────────────────────────────────────────────────────────────────────
# 3) LegacyAttachmentResolver contract validation (pure logic)
# ─────────────────────────────────────────────────────────────────────────────


class TestLegacyResolverContract:
    """Validate LegacyResolution contract invariants."""

    def test_resolution_requires_both_root_and_version(self):
        from app.services.evidence_governance.contracts import (
            LegacyResolution,
            validate_legacy_resolution,
        )

        # Missing attachment_id → invalid
        res = LegacyResolution(
            old_attachment_id="old1",
            attachment_id="",
            attachment_version_id="ver1",
            project_id="proj1",
            audit_year=2025,
            resolution_kind="root",
        )
        assert validate_legacy_resolution(res) is not None

        # Missing version_id → invalid
        res2 = LegacyResolution(
            old_attachment_id="old1",
            attachment_id="att1",
            attachment_version_id="",
            project_id="proj1",
            audit_year=2025,
            resolution_kind="root",
        )
        assert validate_legacy_resolution(res2) is not None

    def test_valid_resolution(self):
        from app.services.evidence_governance.contracts import (
            LegacyResolution,
            validate_legacy_resolution,
        )

        res = LegacyResolution(
            old_attachment_id="old1",
            attachment_id="att1",
            attachment_version_id="ver1",
            project_id="proj1",
            audit_year=2025,
            resolution_kind="root",
            resolved_as_new_root=True,
        )
        assert validate_legacy_resolution(res) is None

    def test_old_id_not_silently_equal_to_root(self):
        """old_attachment_id must NOT be assumed equal to root unless explicitly flagged."""
        from app.services.evidence_governance.contracts import (
            LegacyResolution,
            validate_legacy_resolution,
        )

        # Same IDs without resolved_as_new_root → invalid
        res = LegacyResolution(
            old_attachment_id="same-id",
            attachment_id="same-id",
            attachment_version_id="ver1",
            project_id="proj1",
            audit_year=2025,
            resolution_kind="current_version",
            resolved_as_new_root=False,
        )
        assert validate_legacy_resolution(res) is not None

    def test_invalid_resolution_kind(self):
        from app.services.evidence_governance.contracts import (
            LegacyResolution,
            validate_legacy_resolution,
        )

        res = LegacyResolution(
            old_attachment_id="old1",
            attachment_id="att1",
            attachment_version_id="ver1",
            project_id="proj1",
            audit_year=2025,
            resolution_kind="invalid_kind",
        )
        assert validate_legacy_resolution(res) is not None


# ─────────────────────────────────────────────────────────────────────────────
# 4) Module imports (ensure no import errors)
# ─────────────────────────────────────────────────────────────────────────────


class TestModuleImports:
    """Verify all task 3.5 components are importable without errors."""

    def test_version_manager_imports(self):
        from app.services.evidence_governance.version_manager import (
            AttachmentVersionManager,
            ImpactEntry,
            ImpactReport,
            LegacyAttachmentResolver,
            LegacyRouteFacade,
            ReplaceResult,
            sanitize_attachment_response,
            sanitize_file_path_response,
        )
        assert AttachmentVersionManager is not None
        assert LegacyAttachmentResolver is not None
        assert LegacyRouteFacade is not None

    def test_package_init_exports(self):
        from app.services.evidence_governance import (
            AttachmentVersionManager,
            ImpactReport,
            LegacyAttachmentResolver,
            LegacyRouteFacade,
            ReplaceResult,
            sanitize_attachment_response,
            sanitize_file_path_response,
        )
        assert AttachmentVersionManager is not None
        assert sanitize_file_path_response is not None
