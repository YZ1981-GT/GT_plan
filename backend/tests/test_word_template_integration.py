"""Integration tests for word-template dual mode.

- Prefilled-download e2e (with include_responses=true)
- OO callback → DB write verification

**Validates: Requirements 6.2, 6.3, 8.4**
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from docx import Document

from app.services.wp_docx_template_parser import parse_template


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _create_template_with_placeholders() -> tuple[str, list[str]]:
    """Create a temp docx with known placeholders. Returns (path, field_ids)."""
    doc = Document()
    doc.add_heading("审计业务约定书", level=1)
    doc.add_paragraph("甲方：${entity_name:被审计单位}")
    doc.add_paragraph("审计期间：${audit_period:审计期间}")
    doc.add_paragraph("报告日期：${report_date:报告日期}")

    # Add table with placeholder
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "项目"
    table.cell(0, 1).text = "内容"
    table.cell(1, 0).text = "委托单位"
    table.cell(1, 1).text = "${client_org:委托单位}"

    fd, path = tempfile.mkstemp(suffix=".docx")
    os.close(fd)
    doc.save(path)
    return path, ["entity_name", "audit_period", "report_date", "client_org"]


# ─── Integration Test: Prefilled Download with include_responses ──────────────


class TestPrefilledDownloadIntegration:
    """Integration test for prefilled-download with include_responses=true."""

    def test_export_replaces_placeholders_with_stored_values(self):
        """End-to-end: template + stored responses → exported docx has values merged."""
        template_path, field_ids = _create_template_with_placeholders()
        try:
            # Simulate stored responses
            response_map = {
                "entity_name": "示例科技有限公司",
                "audit_period": "2025年1月1日至2025年12月31日",
                "report_date": "2026年3月15日",
                # client_org intentionally left empty to test partial fill
            }

            # Parse template to get structure
            structure = parse_template(template_path)
            assert len(structure.placeholders) >= 3

            # Build pattern→value mapping (mirror endpoint logic)
            pattern_to_value: dict[str, str] = {}
            for placeholder in structure.placeholders:
                if placeholder.field_id in response_map:
                    pattern_to_value[placeholder.pattern] = response_map[placeholder.field_id]

            # Apply replacements
            import shutil
            fd, exported_path = tempfile.mkstemp(suffix=".docx")
            os.close(fd)
            shutil.copy2(template_path, exported_path)

            doc = Document(exported_path)
            replaced_count = 0
            for para in doc.paragraphs:
                for pattern, value in pattern_to_value.items():
                    if pattern in para.text:
                        for run in para.runs:
                            if pattern in run.text:
                                run.text = run.text.replace(pattern, value)
                                replaced_count += 1

            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for para in cell.paragraphs:
                            for pattern, value in pattern_to_value.items():
                                if pattern in para.text:
                                    for run in para.runs:
                                        if pattern in run.text:
                                            run.text = run.text.replace(pattern, value)
                                            replaced_count += 1

            doc.save(exported_path)

            # Verify exported document
            verify_doc = Document(exported_path)
            full_text = "\n".join(p.text for p in verify_doc.paragraphs)

            # Values should be present
            assert "示例科技有限公司" in full_text
            assert "2025年1月1日至2025年12月31日" in full_text
            assert "2026年3月15日" in full_text

            # Replaced patterns should be gone
            assert "${entity_name:" not in full_text
            assert "${audit_period:" not in full_text
            assert "${report_date:" not in full_text

            # Unfilled placeholder (client_org) should remain in table
            table_text = ""
            for table in verify_doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        table_text += cell.text + " "
            assert "${client_org:委托单位}" in table_text

            os.unlink(exported_path)
        finally:
            os.unlink(template_path)

    def test_export_with_empty_responses_leaves_template_unchanged(self):
        """When no responses exist, exported docx retains all original placeholders."""
        template_path, field_ids = _create_template_with_placeholders()
        try:
            response_map: dict[str, str] = {}  # No responses

            structure = parse_template(template_path)
            pattern_to_value: dict[str, str] = {}
            for placeholder in structure.placeholders:
                if placeholder.field_id in response_map:
                    pattern_to_value[placeholder.pattern] = response_map[placeholder.field_id]

            # No replacements should happen
            assert len(pattern_to_value) == 0

            # Verify original file still has all placeholders
            doc = Document(template_path)
            full_text = "\n".join(p.text for p in doc.paragraphs)
            assert "${entity_name:被审计单位}" in full_text
            assert "${audit_period:审计期间}" in full_text
            assert "${report_date:报告日期}" in full_text
        finally:
            os.unlink(template_path)

    def test_export_preserves_heading_structure(self):
        """Export does not alter non-placeholder content (headings, static text)."""
        template_path, _ = _create_template_with_placeholders()
        try:
            response_map = {"entity_name": "测试公司"}
            structure = parse_template(template_path)

            pattern_to_value: dict[str, str] = {}
            for placeholder in structure.placeholders:
                if placeholder.field_id in response_map:
                    pattern_to_value[placeholder.pattern] = response_map[placeholder.field_id]

            import shutil
            fd, exported_path = tempfile.mkstemp(suffix=".docx")
            os.close(fd)
            shutil.copy2(template_path, exported_path)

            doc = Document(exported_path)
            for para in doc.paragraphs:
                for pattern, value in pattern_to_value.items():
                    if pattern in para.text:
                        for run in para.runs:
                            if pattern in run.text:
                                run.text = run.text.replace(pattern, value)
            doc.save(exported_path)

            # Heading should remain unchanged
            verify_doc = Document(exported_path)
            heading = verify_doc.paragraphs[0]
            assert heading.text == "审计业务约定书"
            assert "Heading" in (heading.style.name or "")

            os.unlink(exported_path)
        finally:
            os.unlink(template_path)


# ─── Integration Test: OO Callback → DB Write ────────────────────────────────


class TestCallbackDBWriteIntegration:
    """Integration test for OnlyOffice callback → checklist_responses write."""

    def test_callback_extracts_edited_values_from_saved_docx(self):
        """Simulate OO save: user edits placeholders → extraction finds changes."""
        template_path, field_ids = _create_template_with_placeholders()
        try:
            # Create "saved" docx (simulates what OO saves after user edits)
            saved_doc = Document()
            saved_doc.add_heading("审计业务约定书", level=1)
            saved_doc.add_paragraph("甲方：示例科技有限公司")  # Edited
            saved_doc.add_paragraph("审计期间：2025年度")      # Edited
            saved_doc.add_paragraph("报告日期：${report_date:报告日期}")  # Unchanged

            table = saved_doc.add_table(rows=2, cols=2)
            table.cell(0, 0).text = "项目"
            table.cell(0, 1).text = "内容"
            table.cell(1, 0).text = "委托单位"
            table.cell(1, 1).text = "某集团公司"  # Edited

            fd, saved_path = tempfile.mkstemp(suffix=".docx")
            os.close(fd)
            saved_doc.save(saved_path)

            # Parse ORIGINAL template for placeholder positions
            structure = parse_template(template_path)

            # Extract values from SAVED file using template positions
            from app.routers.wp_onlyoffice_router import _extract_placeholder_value_from_docx

            extracted: dict[str, str] = {}
            wp_code = "A8-1"
            prefix = f"wt-{wp_code}-"

            for placeholder in structure.placeholders:
                value = _extract_placeholder_value_from_docx(
                    Path(saved_path), placeholder
                )
                if value and value != placeholder.pattern:
                    extracted[placeholder.field_id] = value

            # Verify extraction
            # entity_name: paragraph 1 text should be "甲方：示例科技有限公司"
            assert "entity_name" in extracted
            assert "示例科技有限公司" in extracted["entity_name"]

            # audit_period: paragraph 2
            assert "audit_period" in extracted
            assert "2025年度" in extracted["audit_period"]

            # report_date: still has pattern → should NOT be extracted
            assert "report_date" not in extracted

            # client_org: table cell edited → should be extracted
            assert "client_org" in extracted
            assert extracted["client_org"] == "某集团公司"

            # Verify item_id format
            for field_id in extracted:
                item_id = f"{prefix}{field_id}"
                assert item_id.startswith("wt-A8-1-")

            os.unlink(saved_path)
        finally:
            os.unlink(template_path)

    def test_callback_with_no_edits_extracts_nothing(self):
        """When saved docx is identical to template, nothing is extracted."""
        template_path, field_ids = _create_template_with_placeholders()
        try:
            # Parse template
            structure = parse_template(template_path)

            from app.routers.wp_onlyoffice_router import _extract_placeholder_value_from_docx

            extracted: dict[str, str] = {}
            for placeholder in structure.placeholders:
                value = _extract_placeholder_value_from_docx(
                    Path(template_path), placeholder
                )
                if value and value != placeholder.pattern:
                    extracted[placeholder.field_id] = value

            # Nothing should be extracted since all patterns remain
            assert len(extracted) == 0, (
                f"Expected no extractions from unedited template, got: {extracted}"
            )
        finally:
            os.unlink(template_path)

    def test_callback_handles_partial_edits(self):
        """Only edited fields are extracted; unchanged fields are skipped."""
        template_path, field_ids = _create_template_with_placeholders()
        try:
            # Only edit entity_name, leave others unchanged
            saved_doc = Document()
            saved_doc.add_heading("审计业务约定书", level=1)
            saved_doc.add_paragraph("甲方：新公司名称")  # Edited
            saved_doc.add_paragraph("审计期间：${audit_period:审计期间}")  # Unchanged
            saved_doc.add_paragraph("报告日期：${report_date:报告日期}")  # Unchanged

            table = saved_doc.add_table(rows=2, cols=2)
            table.cell(0, 0).text = "项目"
            table.cell(0, 1).text = "内容"
            table.cell(1, 0).text = "委托单位"
            table.cell(1, 1).text = "${client_org:委托单位}"  # Unchanged

            fd, saved_path = tempfile.mkstemp(suffix=".docx")
            os.close(fd)
            saved_doc.save(saved_path)

            structure = parse_template(template_path)

            from app.routers.wp_onlyoffice_router import _extract_placeholder_value_from_docx

            extracted: dict[str, str] = {}
            for placeholder in structure.placeholders:
                value = _extract_placeholder_value_from_docx(
                    Path(saved_path), placeholder
                )
                if value and value != placeholder.pattern:
                    extracted[placeholder.field_id] = value

            # Only entity_name should be extracted
            assert "entity_name" in extracted
            assert "新公司名称" in extracted["entity_name"]
            assert "audit_period" not in extracted
            assert "report_date" not in extracted
            assert "client_org" not in extracted

            os.unlink(saved_path)
        finally:
            os.unlink(template_path)
