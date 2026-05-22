"""Tests for review_templates router — Phase 7 F4

Validates: Requirements F4.2, F4.3, F4.5, F4.6, F4.7
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.review_templates import (
    SEED_TEMPLATES,
    ReviewTemplateCreate,
    router,
)


class TestReviewTemplatesRouter:
    """Test review_templates CRUD endpoints."""

    def test_router_prefix(self):
        """Router has correct prefix."""
        assert router.prefix == "/api/review-templates"

    def test_router_tags(self):
        """Router has correct tags."""
        assert "review-templates" in router.tags

    def test_seed_templates_count(self):
        """At least 10 seed templates defined."""
        assert len(SEED_TEMPLATES) >= 10

    def test_seed_templates_structure(self):
        """Each seed template has required fields."""
        for tpl in SEED_TEMPLATES:
            assert "title" in tpl
            assert "content" in tpl
            assert "applicable_cycles" in tpl
            assert "priority_tag" in tpl
            assert tpl["priority_tag"] in ("must_fix", "suggest", "info")
            assert isinstance(tpl["applicable_cycles"], list)

    def test_create_schema_validation(self):
        """ReviewTemplateCreate validates correctly."""
        body = ReviewTemplateCreate(
            title="Test",
            content="Test content",
            applicable_cycles=["D", "E"],
            priority_tag="must_fix",
        )
        assert body.title == "Test"
        assert body.priority_tag == "must_fix"

    def test_create_schema_default_tag(self):
        """Default priority_tag is 'suggest'."""
        body = ReviewTemplateCreate(title="T", content="C")
        assert body.priority_tag == "suggest"
        assert body.applicable_cycles == []

    def test_create_schema_invalid_tag(self):
        """Invalid priority_tag raises validation error."""
        with pytest.raises(Exception):
            ReviewTemplateCreate(
                title="T", content="C", priority_tag="invalid"
            )

    def test_seed_templates_cycles_valid(self):
        """All seed template cycles are valid audit cycle letters."""
        valid_cycles = set("ABCDEFGHIJKLMN")
        for tpl in SEED_TEMPLATES:
            for c in tpl["applicable_cycles"]:
                assert c in valid_cycles, f"Invalid cycle '{c}' in template '{tpl['title']}'"

    def test_seed_templates_priority_distribution(self):
        """Seed templates have a mix of priority tags."""
        tags = [t["priority_tag"] for t in SEED_TEMPLATES]
        assert "must_fix" in tags
        assert "suggest" in tags
        assert "info" in tags

    def test_router_has_crud_endpoints(self):
        """Router has all expected CRUD routes."""
        methods = {}
        for r in router.routes:
            for method in r.methods:
                methods[f"{method} {r.path}"] = True

        # Check all CRUD methods exist
        assert any("GET" in m for m in methods)
        assert any("POST" in m and "/use" not in m and "{template_id}" not in m for m in methods)
        assert any("PUT" in m for m in methods)
        assert any("DELETE" in m for m in methods)
        # POST /{template_id}/use
        assert any("/use" in m for m in methods)
