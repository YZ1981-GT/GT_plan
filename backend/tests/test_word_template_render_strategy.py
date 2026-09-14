"""Unit tests for word-template render strategy.

Tests:
- Template file not found → returns None
- Parse failure (ValueError) → returns None
- No responses → returns structure with empty filled_responses
- Normal: responses merged correctly
- Cold cache behavior
- DB query failure graceful handling

**Validates: Requirements 3.4, 3.5, 10.1, 10.2, 10.4**
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.wp_render_strategies._context import RenderContext
from app.routers.wp_render_strategies._word_template import render

# Correct patch target: the service module where get_cached_structure is defined.
# render() uses a deferred import inside the function body, so we patch the source.
_PATCH_GET_CACHED = "app.services.wp_docx_template_parser.get_cached_structure"


# ─── Fake dataclasses ─────────────────────────────────────────────────────────


@dataclass
class FakePlaceholder:
    field_id: str
    label: str
    data_type: str
    default_value: str
    position: dict
    pattern: str


@dataclass
class FakeParagraph:
    index: int
    text: str
    style: str
    heading_level: int
    placeholder_ids: list = field(default_factory=list)


@dataclass
class FakeTable:
    index: int
    rows: list = field(default_factory=list)
    placeholder_ids: list = field(default_factory=list)


@dataclass
class FakeStructure:
    paragraphs: list = field(default_factory=list)
    tables: list = field(default_factory=list)
    placeholders: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


def _make_structure(field_ids: list[str] | None = None) -> FakeStructure:
    """Build a FakeStructure with given field_ids."""
    if field_ids is None:
        field_ids = ["entity_name", "audit_period"]

    placeholders = [
        FakePlaceholder(
            field_id=fid,
            label=f"标签_{fid}",
            data_type="text",
            default_value=f"默认_{fid}",
            position={"paragraph_index": i},
            pattern=f"${{{fid}}}",
        )
        for i, fid in enumerate(field_ids)
    ]
    paragraphs = [
        FakeParagraph(
            index=i,
            text=f"段落含 ${{{fid}}}",
            style="Normal",
            heading_level=0,
            placeholder_ids=[fid],
        )
        for i, fid in enumerate(field_ids)
    ]
    return FakeStructure(
        paragraphs=paragraphs,
        tables=[],
        placeholders=placeholders,
        metadata={"template_name": "A8-1 测试", "wp_code": "A8-1", "last_parsed_at": "2026-01-01T00:00:00Z"},
    )


def _make_ctx(
    wp_code: str = "A8-1",
    template_file_path: str | None = "/fake/template.docx",
    db_rows: list | None = None,
) -> RenderContext:
    """Build a mock RenderContext."""
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.fetchall.return_value = db_rows or []
    db.execute = AsyncMock(return_value=result_mock)

    ctx = MagicMock(spec=RenderContext)
    ctx.wp_id = "wp-test-001"
    ctx.wp_code = wp_code
    ctx.db = db
    ctx.template_file_path = template_file_path
    return ctx


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestWordTemplateRenderStrategy:
    """Unit tests for _word_template.render()."""

    @pytest.mark.asyncio
    async def test_returns_none_when_template_file_not_found(self):
        """When get_cached_structure raises FileNotFoundError, render returns None."""
        ctx = _make_ctx()

        with patch(_PATCH_GET_CACHED, side_effect=FileNotFoundError("模板文件不存在")):
            result = await render(ctx)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_parse_fails_with_value_error(self):
        """When get_cached_structure raises ValueError, render returns None."""
        ctx = _make_ctx()

        with patch(_PATCH_GET_CACHED, side_effect=ValueError("Invalid docx format")):
            result = await render(ctx)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_template_file_path_is_none(self):
        """When template_file_path is None (empty), render returns None."""
        ctx = _make_ctx(template_file_path=None)

        result = await render(ctx)

        assert result is None

    @pytest.mark.asyncio
    async def test_no_responses_returns_empty_filled_responses(self):
        """When no checklist_responses exist, filled_responses is empty dict."""
        structure = _make_structure(["entity_name", "audit_period"])
        ctx = _make_ctx(db_rows=[])

        with patch(_PATCH_GET_CACHED, return_value=structure):
            result = await render(ctx)

        assert result is not None
        assert result["filled_responses"] == {}
        # placeholders should have empty current_value
        for p in result["template_structure"]["placeholders"]:
            assert p["current_value"] == ""

    @pytest.mark.asyncio
    async def test_responses_merged_correctly(self):
        """Stored checklist_responses values appear as current_value on placeholders."""
        structure = _make_structure(["entity_name", "audit_period"])

        row1 = MagicMock()
        row1.item_id = "wt-A8-1-entity_name"
        row1.conclusion = "示例公司"
        row1.remark = ""

        row2 = MagicMock()
        row2.item_id = "wt-A8-1-audit_period"
        row2.conclusion = ""
        row2.remark = "2024年1月1日至2024年12月31日"

        ctx = _make_ctx(db_rows=[row1, row2])

        with patch(_PATCH_GET_CACHED, return_value=structure):
            result = await render(ctx)

        assert result is not None
        assert result["filled_responses"]["entity_name"] == "示例公司"
        assert result["filled_responses"]["audit_period"] == "2024年1月1日至2024年12月31日"

        # Verify current_value on placeholders
        p_map = {p["field_id"]: p for p in result["template_structure"]["placeholders"]}
        assert p_map["entity_name"]["current_value"] == "示例公司"
        assert p_map["audit_period"]["current_value"] == "2024年1月1日至2024年12月31日"

    @pytest.mark.asyncio
    async def test_conclusion_takes_priority_over_remark(self):
        """When both conclusion and remark have values, conclusion wins."""
        structure = _make_structure(["entity_name"])

        row = MagicMock()
        row.item_id = "wt-A8-1-entity_name"
        row.conclusion = "结论值"
        row.remark = "备注值"

        ctx = _make_ctx(db_rows=[row])

        with patch(_PATCH_GET_CACHED, return_value=structure):
            result = await render(ctx)

        assert result is not None
        assert result["filled_responses"]["entity_name"] == "结论值"

    @pytest.mark.asyncio
    async def test_response_structure_keys(self):
        """Render returns dict with template_structure, filled_responses, sign_status."""
        structure = _make_structure()
        ctx = _make_ctx(db_rows=[])

        with patch(_PATCH_GET_CACHED, return_value=structure):
            result = await render(ctx)

        assert result is not None
        assert set(result.keys()) == {"template_structure", "filled_responses", "sign_status"}
        assert isinstance(result["template_structure"], dict)
        assert isinstance(result["filled_responses"], dict)

    @pytest.mark.asyncio
    async def test_template_structure_contains_subkeys(self):
        """template_structure has placeholders, paragraphs, tables, metadata."""
        structure = _make_structure()
        ctx = _make_ctx(db_rows=[])

        with patch(_PATCH_GET_CACHED, return_value=structure):
            result = await render(ctx)

        ts = result["template_structure"]
        assert "placeholders" in ts
        assert "paragraphs" in ts
        assert "tables" in ts
        assert "metadata" in ts
        assert ts["metadata"]["wp_code"] == "A8-1"

    @pytest.mark.asyncio
    async def test_cold_cache_still_works(self):
        """First request (cold cache) calls get_cached_structure and returns structure."""
        structure = _make_structure(["field_a"])
        ctx = _make_ctx(db_rows=[])

        with patch(_PATCH_GET_CACHED, return_value=structure) as mock_get:
            result = await render(ctx)

        # get_cached_structure was called with correct args
        mock_get.assert_called_once_with("/fake/template.docx", "A8-1")
        assert result is not None
        assert len(result["template_structure"]["placeholders"]) == 1

    @pytest.mark.asyncio
    async def test_db_query_failure_returns_empty_responses(self):
        """When DB query fails, filled_responses is empty but structure still returned."""
        structure = _make_structure(["entity_name"])

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=Exception("DB connection error"))

        ctx = MagicMock(spec=RenderContext)
        ctx.wp_id = "wp-test-001"
        ctx.wp_code = "A8-1"
        ctx.db = db
        ctx.template_file_path = "/fake/template.docx"

        with patch(_PATCH_GET_CACHED, return_value=structure):
            result = await render(ctx)

        assert result is not None
        assert result["filled_responses"] == {}
        # Structure still returned despite DB failure
        assert len(result["template_structure"]["placeholders"]) == 1
