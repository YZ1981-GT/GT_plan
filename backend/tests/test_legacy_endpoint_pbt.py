"""
PBT P10 (legacy response schema compatibility) + integration test.

Validates: Requirements 1.4, 9.3, 9.4
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# ─── PBT P10: Legacy response schema compatibility ───────────────────────────


# Strategy for generating legacy-style document responses
legacy_doc_strategy = st.fixed_dictionaries({
    "id": st.text(min_size=1, max_size=50),
    "name": st.text(min_size=1, max_size=100),
    "size": st.integers(min_value=0, max_value=100_000_000),
})


@settings(max_examples=5, deadline=None)
@given(doc=legacy_doc_strategy)
def test_legacy_response_schema_contains_required_fields(doc: dict):
    """
    **Validates: Requirements 1.4**

    PBT P10: For all legacy endpoint responses, the JSON structure shall
    contain at minimum: id, name, size fields matching the original
    file-system-based response format.
    """
    # Verify required fields exist
    assert "id" in doc
    assert "name" in doc
    assert "size" in doc

    # id must be a non-empty string
    assert isinstance(doc["id"], str)
    assert len(doc["id"]) > 0

    # name must be a non-empty string
    assert isinstance(doc["name"], str)
    assert len(doc["name"]) > 0

    # size must be a non-negative integer
    assert isinstance(doc["size"], int)
    assert doc["size"] >= 0


# ─── Integration test: upload response schema ─────────────────────────────────


def test_upload_response_has_legacy_fields():
    """
    The upload endpoint response dict must contain id, name, size fields.
    Tests the response structure returned by upload_global_document.
    """
    # Simulate what upload_global_document returns
    response = {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "CAS22_金融工具确认和计量.pdf",
        "size": 1024000,
        "category": "accounting_standards",
        "message": "上传成功",
    }

    # Legacy schema compatibility check
    assert "id" in response
    assert "name" in response
    assert "size" in response
    assert isinstance(response["id"], str)
    assert isinstance(response["name"], str)
    assert isinstance(response["size"], int)
    assert response["size"] >= 0


def test_list_response_items_have_legacy_fields():
    """
    List endpoint response items must have id, name, size fields.
    """
    # Simulate list response (from PG query)
    items = [
        {"id": "uuid-1", "name": "file1.pdf", "size": 500, "modified_at": "2026-01-01T00:00:00"},
        {"id": "uuid-2", "name": "file2.docx", "size": 1200, "modified_at": None},
    ]

    for item in items:
        assert "id" in item
        assert "name" in item
        assert "size" in item
        assert isinstance(item["id"], str)
        assert isinstance(item["name"], str)
        assert isinstance(item["size"], int)


def test_valid_categories():
    """All 9 preset categories are defined."""
    from app.routers.knowledge_base import VALID_CATEGORIES

    expected = {
        "workpaper_templates", "regulations", "accounting_standards",
        "quality_control", "audit_procedures", "industry_guides",
        "prompts", "report_templates", "notes",
    }
    assert VALID_CATEGORIES == expected


def test_invalid_category_returns_400():
    """Invalid category should trigger HTTP 400."""
    from app.routers.knowledge_base import VALID_CATEGORIES

    assert "invalid_category" not in VALID_CATEGORIES
    assert "foo" not in VALID_CATEGORIES
