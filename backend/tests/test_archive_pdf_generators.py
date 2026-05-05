"""R1 Task 15 单元测试：archive_pdf_generators

覆盖：
1. generate_project_cover_pdf 正常生成（mock LibreOffice）
2. generate_signature_ledger_pdf 正常生成（mock LibreOffice）
3. 项目不存在时返回 None
4. LibreOffice 不可用时返回 None
5. 水印文本包含版本号和时间
6. 签字流水支持 N 级签字（预留 EQCR 扩展）

Validates: Requirements 6 (refinement-round1-review-closure)
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.archive_pdf_generators import (
    APP_VERSION,
    OPINION_TYPE_LABELS,
    _build_watermark,
    _escape_html,
    _html_to_pdf_bytes,
    generate_project_cover_pdf,
    generate_signature_ledger_pdf,
)


FAKE_PROJECT_ID = uuid.uuid4()
FAKE_USER_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_project(
    project_id=None,
    name="测试项目",
    client_name="测试客户",
    audit_period_start=date(2025, 1, 1),
    audit_period_end=date(2025, 12, 31),
):
    """创建 mock Project 对象。"""
    p = MagicMock()
    p.id = project_id or FAKE_PROJECT_ID
    p.name = name
    p.client_name = client_name
    p.audit_period_start = audit_period_start
    p.audit_period_end = audit_period_end
    return p


def _make_audit_report(
    project_id=None,
    year=2025,
    opinion_type_value="unqualified",
    report_date=date(2025, 3, 15),
    signing_partner="张三",
    paragraphs=None,
):
    """创建 mock AuditReport 对象。"""
    r = MagicMock()
    r.project_id = project_id or FAKE_PROJECT_ID
    r.year = year
    r.opinion_type = MagicMock()
    r.opinion_type.value = opinion_type_value
    r.report_date = report_date
    r.signing_partner = signing_partner
    r.paragraphs = paragraphs or {"report_number": "致审字[2025]第001号"}
    return r


def _make_signature_record(
    signer_id=None,
    signature_level="level1",
    required_order=1,
    required_role="project_manager",
    signature_timestamp=None,
    signature_data=None,
):
    """创建 mock SignatureRecord 对象。"""
    s = MagicMock()
    s.signer_id = signer_id or FAKE_USER_ID
    s.signature_level = signature_level
    s.required_order = required_order
    s.required_role = required_role
    s.signature_timestamp = signature_timestamp or datetime(2025, 3, 10, 10, 0, 0)
    s.signature_data = signature_data or {
        "method": "electronic",
        "gate_eval_id": "eval-001",
        "verification_hash": "abc123def456",
    }
    s.is_deleted = False
    s.created_at = datetime(2025, 3, 10, 10, 0, 0)
    return s


# ---------------------------------------------------------------------------
# Tests: _build_watermark
# ---------------------------------------------------------------------------


class TestBuildWatermark:
    """水印生成测试。"""

    def test_contains_version(self):
        """水印包含应用版本号。"""
        wm = _build_watermark()
        assert APP_VERSION in wm

    def test_contains_platform_name(self):
        """水印包含平台名称。"""
        wm = _build_watermark()
        assert "审计平台" in wm

    def test_contains_hash_placeholder(self):
        """水印包含 SHA-256 占位符。"""
        wm = _build_watermark()
        assert "待归档完成后填入" in wm

    def test_custom_hash(self):
        """可传入自定义 hash 值。"""
        wm = _build_watermark(hash_placeholder="deadbeef1234")
        assert "deadbeef1234" in wm


# ---------------------------------------------------------------------------
# Tests: _escape_html
# ---------------------------------------------------------------------------


class TestEscapeHtml:
    """HTML 转义测试。"""

    def test_escapes_angle_brackets(self):
        assert "&lt;" in _escape_html("<script>")
        assert "&gt;" in _escape_html("</script>")

    def test_escapes_ampersand(self):
        assert "&amp;" in _escape_html("A & B")

    def test_escapes_quotes(self):
        assert "&quot;" in _escape_html('"hello"')


# ---------------------------------------------------------------------------
# Tests: generate_project_cover_pdf
# ---------------------------------------------------------------------------


class TestGenerateProjectCoverPdf:
    """项目封面 PDF 生成测试。"""

    @pytest.mark.asyncio
    async def test_returns_none_when_project_not_found(self):
        """项目不存在时返回 None。"""
        db = AsyncMock()
        # Mock execute to return no result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        result = await generate_project_cover_pdf(FAKE_PROJECT_ID, db)
        assert result is None

    @pytest.mark.asyncio
    @patch("app.services.archive_pdf_generators._html_to_pdf_bytes")
    @patch("app.services.archive_pdf_generators._get_audit_report")
    @patch("app.services.archive_pdf_generators._get_project")
    async def test_generates_pdf_bytes(
        self, mock_get_project, mock_get_report, mock_html_to_pdf
    ):
        """正常情况下生成 PDF bytes。"""
        mock_get_project.return_value = _make_project()
        mock_get_report.return_value = _make_audit_report()
        mock_html_to_pdf.return_value = b"%PDF-1.4 fake pdf content"

        result = await generate_project_cover_pdf(FAKE_PROJECT_ID, AsyncMock())

        assert result is not None
        assert result == b"%PDF-1.4 fake pdf content"
        mock_html_to_pdf.assert_called_once()

        # 验证 HTML 内容包含关键信息
        html_arg = mock_html_to_pdf.call_args[0][0]
        assert "测试客户" in html_arg
        assert "测试项目" in html_arg
        assert "无保留意见" in html_arg
        assert "张三" in html_arg
        assert "致审字[2025]第001号" in html_arg

    @pytest.mark.asyncio
    @patch("app.services.archive_pdf_generators._html_to_pdf_bytes")
    @patch("app.services.archive_pdf_generators._get_audit_report")
    @patch("app.services.archive_pdf_generators._get_project")
    async def test_returns_none_when_libreoffice_unavailable(
        self, mock_get_project, mock_get_report, mock_html_to_pdf
    ):
        """LibreOffice 不可用时返回 None。"""
        mock_get_project.return_value = _make_project()
        mock_get_report.return_value = _make_audit_report()
        mock_html_to_pdf.return_value = None  # LibreOffice 不可用

        result = await generate_project_cover_pdf(FAKE_PROJECT_ID, AsyncMock())
        assert result is None

    @pytest.mark.asyncio
    @patch("app.services.archive_pdf_generators._html_to_pdf_bytes")
    @patch("app.services.archive_pdf_generators._get_audit_report")
    @patch("app.services.archive_pdf_generators._get_project")
    async def test_cover_without_report(
        self, mock_get_project, mock_get_report, mock_html_to_pdf
    ):
        """没有 AuditReport 时仍能生成封面（字段用默认值）。"""
        mock_get_project.return_value = _make_project()
        mock_get_report.return_value = None
        mock_html_to_pdf.return_value = b"%PDF-1.4 minimal cover"

        result = await generate_project_cover_pdf(FAKE_PROJECT_ID, AsyncMock())
        assert result is not None

        html_arg = mock_html_to_pdf.call_args[0][0]
        assert "测试客户" in html_arg
        assert "测试项目" in html_arg


# ---------------------------------------------------------------------------
# Tests: generate_signature_ledger_pdf
# ---------------------------------------------------------------------------


class TestGenerateSignatureLedgerPdf:
    """签字流水 PDF 生成测试。"""

    @pytest.mark.asyncio
    async def test_returns_none_when_project_not_found(self):
        """项目不存在时返回 None。"""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        result = await generate_signature_ledger_pdf(FAKE_PROJECT_ID, db)
        assert result is None

    @pytest.mark.asyncio
    @patch("app.services.archive_pdf_generators._get_user_display_name")
    @patch("app.services.archive_pdf_generators._html_to_pdf_bytes")
    @patch("app.services.archive_pdf_generators._get_signature_records")
    @patch("app.services.archive_pdf_generators._get_project")
    async def test_generates_pdf_with_signatures(
        self, mock_get_project, mock_get_sigs, mock_html_to_pdf, mock_get_name
    ):
        """有签字记录时生成包含流水表格的 PDF。"""
        mock_get_project.return_value = _make_project()
        mock_get_sigs.return_value = [
            _make_signature_record(
                signature_level="level1",
                required_order=1,
                required_role="project_manager",
            ),
            _make_signature_record(
                signature_level="level2",
                required_order=2,
                required_role="qc_reviewer",
            ),
            _make_signature_record(
                signature_level="level3",
                required_order=3,
                required_role="partner",
            ),
        ]
        mock_html_to_pdf.return_value = b"%PDF-1.4 ledger content"
        mock_get_name.return_value = "李四"

        result = await generate_signature_ledger_pdf(FAKE_PROJECT_ID, AsyncMock())

        assert result is not None
        assert result == b"%PDF-1.4 ledger content"

        # 验证 HTML 包含签字信息
        html_arg = mock_html_to_pdf.call_args[0][0]
        assert "level1" in html_arg
        assert "level2" in html_arg
        assert "level3" in html_arg
        assert "project_manager" in html_arg
        assert "qc_reviewer" in html_arg
        assert "partner" in html_arg
        assert "李四" in html_arg
        assert "eval-001" in html_arg

    @pytest.mark.asyncio
    @patch("app.services.archive_pdf_generators._html_to_pdf_bytes")
    @patch("app.services.archive_pdf_generators._get_signature_records")
    @patch("app.services.archive_pdf_generators._get_project")
    async def test_generates_pdf_without_signatures(
        self, mock_get_project, mock_get_sigs, mock_html_to_pdf
    ):
        """无签字记录时生成包含"暂无签字记录"的 PDF。"""
        mock_get_project.return_value = _make_project()
        mock_get_sigs.return_value = []
        mock_html_to_pdf.return_value = b"%PDF-1.4 empty ledger"

        result = await generate_signature_ledger_pdf(FAKE_PROJECT_ID, AsyncMock())

        assert result is not None
        html_arg = mock_html_to_pdf.call_args[0][0]
        assert "暂无签字记录" in html_arg

    @pytest.mark.asyncio
    @patch("app.services.archive_pdf_generators._get_user_display_name")
    @patch("app.services.archive_pdf_generators._html_to_pdf_bytes")
    @patch("app.services.archive_pdf_generators._get_signature_records")
    @patch("app.services.archive_pdf_generators._get_project")
    async def test_supports_n_level_signatures_eqcr_extension(
        self, mock_get_project, mock_get_sigs, mock_html_to_pdf, mock_get_name
    ):
        """支持 N 级签字（预留 EQCR 扩展到 order=4/5）。"""
        mock_get_project.return_value = _make_project()
        mock_get_sigs.return_value = [
            _make_signature_record(required_order=1, required_role="project_manager", signature_level="level1"),
            _make_signature_record(required_order=2, required_role="qc_reviewer", signature_level="level2"),
            _make_signature_record(required_order=3, required_role="partner", signature_level="level3"),
            _make_signature_record(required_order=4, required_role="eqcr", signature_level="level4"),
            _make_signature_record(required_order=5, required_role="archive_signer", signature_level="level5"),
        ]
        mock_html_to_pdf.return_value = b"%PDF-1.4 5-level ledger"
        mock_get_name.return_value = "王五"

        result = await generate_signature_ledger_pdf(FAKE_PROJECT_ID, AsyncMock())

        assert result is not None
        html_arg = mock_html_to_pdf.call_args[0][0]
        # 验证 5 级签字都在
        assert "level4" in html_arg
        assert "level5" in html_arg
        assert "eqcr" in html_arg
        assert "archive_signer" in html_arg

    @pytest.mark.asyncio
    @patch("app.services.archive_pdf_generators._html_to_pdf_bytes")
    @patch("app.services.archive_pdf_generators._get_signature_records")
    @patch("app.services.archive_pdf_generators._get_project")
    async def test_watermark_in_ledger(
        self, mock_get_project, mock_get_sigs, mock_html_to_pdf
    ):
        """签字流水 PDF 包含水印。"""
        mock_get_project.return_value = _make_project()
        mock_get_sigs.return_value = []
        mock_html_to_pdf.return_value = b"%PDF-1.4 with watermark"

        await generate_signature_ledger_pdf(FAKE_PROJECT_ID, AsyncMock())

        html_arg = mock_html_to_pdf.call_args[0][0]
        assert "审计平台" in html_arg
        assert APP_VERSION in html_arg
        assert "SHA-256" in html_arg


# ---------------------------------------------------------------------------
# Tests: _html_to_pdf_bytes (LibreOffice integration)
# ---------------------------------------------------------------------------


class TestHtmlToPdfBytes:
    """LibreOffice 转换测试（mock subprocess）。"""

    @patch("app.services.archive_pdf_generators._find_libreoffice")
    def test_returns_none_when_libreoffice_not_found(self, mock_find):
        """LibreOffice 不可用时返回 None。"""
        mock_find.return_value = None
        result = _html_to_pdf_bytes("<html><body>test</body></html>")
        assert result is None

    @patch("app.services.archive_pdf_generators.subprocess.run")
    @patch("app.services.archive_pdf_generators._find_libreoffice")
    def test_returns_none_on_conversion_error(self, mock_find, mock_run):
        """转换失败时返回 None。"""
        import subprocess

        mock_find.return_value = "/usr/bin/libreoffice"
        mock_run.side_effect = subprocess.CalledProcessError(1, "libreoffice")

        result = _html_to_pdf_bytes("<html><body>test</body></html>")
        assert result is None


# ---------------------------------------------------------------------------
# Tests: Integration with archive_section_registry
# ---------------------------------------------------------------------------


class TestRegistryIntegration:
    """验证 archive_section_registry 中的 generator 函数签名正确。"""

    def test_cover_generator_is_callable(self):
        """封面 generator 可调用。"""
        from app.services.archive_section_registry import generate_project_cover_pdf

        assert callable(generate_project_cover_pdf)

    def test_ledger_generator_is_callable(self):
        """签字流水 generator 可调用。"""
        from app.services.archive_section_registry import generate_signature_ledger_pdf

        assert callable(generate_signature_ledger_pdf)

    @pytest.mark.asyncio
    @patch("app.services.archive_pdf_generators._html_to_pdf_bytes")
    @patch("app.services.archive_pdf_generators._get_audit_report")
    @patch("app.services.archive_pdf_generators._get_project")
    async def test_registry_cover_delegates_to_impl(
        self, mock_get_project, mock_get_report, mock_html_to_pdf
    ):
        """registry 中的封面 generator 委托到真实实现。"""
        from app.services.archive_section_registry import generate_project_cover_pdf

        mock_get_project.return_value = _make_project()
        mock_get_report.return_value = _make_audit_report()
        mock_html_to_pdf.return_value = b"%PDF-cover"

        result = await generate_project_cover_pdf(FAKE_PROJECT_ID, AsyncMock())
        assert result == b"%PDF-cover"

    @pytest.mark.asyncio
    @patch("app.services.archive_pdf_generators._html_to_pdf_bytes")
    @patch("app.services.archive_pdf_generators._get_signature_records")
    @patch("app.services.archive_pdf_generators._get_project")
    async def test_registry_ledger_delegates_to_impl(
        self, mock_get_project, mock_get_sigs, mock_html_to_pdf
    ):
        """registry 中的签字流水 generator 委托到真实实现。"""
        from app.services.archive_section_registry import generate_signature_ledger_pdf

        mock_get_project.return_value = _make_project()
        mock_get_sigs.return_value = []
        mock_html_to_pdf.return_value = b"%PDF-ledger"

        result = await generate_signature_ledger_pdf(FAKE_PROJECT_ID, AsyncMock())
        assert result == b"%PDF-ledger"
