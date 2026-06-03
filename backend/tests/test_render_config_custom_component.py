# Feature: custom-workpaper-formula-binding — render-config 自定义底稿 componentType=custom
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.workpaper_models import WpSourceType, WorkingPaper
from app.routers.wp_render_config import (
    _looks_like_standard_wp_code,
    _maybe_custom_classifications,
)
from app.services.wp_classification_service import derive_component_type


def test_looks_like_standard_wp_code():
    assert _looks_like_standard_wp_code("D1-1")
    assert _looks_like_standard_wp_code("E11")
    assert not _looks_like_standard_wp_code("CUST-01")
    assert not _looks_like_standard_wp_code("MY-WP")


@pytest.mark.anyio
async def test_maybe_custom_for_manual_non_standard_code():
    project_id = uuid.uuid4()
    wp_code = "CUST-99"
    wp = MagicMock(spec=WorkingPaper)
    wp.source_type = WpSourceType.manual

    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar=lambda: 0))

    out = await _maybe_custom_classifications(
        db, project_id, wp_code, "用户自建底稿", [], wp
    )
    assert len(out) == 1
    assert out[0].class_code == "CUSTOM"
    assert derive_component_type(out[0]) == "custom"


@pytest.mark.anyio
async def test_maybe_custom_skips_standard_code_without_procedure():
    project_id = uuid.uuid4()
    wp = MagicMock(spec=WorkingPaper)
    wp.source_type = WpSourceType.manual

    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar=lambda: 0))

    out = await _maybe_custom_classifications(
        db, project_id, "D1-1", "审定表", [], wp
    )
    assert out == []


@pytest.mark.anyio
async def test_maybe_custom_when_custom_procedure_exists():
    project_id = uuid.uuid4()
    wp = MagicMock(spec=WorkingPaper)
    wp.source_type = WpSourceType.template

    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar=lambda: 1))

    out = await _maybe_custom_classifications(
        db, project_id, "D-C01", "自定义程序底稿", [], wp
    )
    assert len(out) == 1
    assert derive_component_type(out[0]) == "custom"


@pytest.mark.anyio
async def test_maybe_custom_preserves_existing_classifications():
    project_id = uuid.uuid4()
    wp = MagicMock(spec=WorkingPaper)
    wp.source_type = WpSourceType.manual
    existing = [MagicMock()]

    db = AsyncMock()
    out = await _maybe_custom_classifications(
        db, project_id, "CUST-01", "x", existing, wp
    )
    assert out is existing
    db.execute.assert_not_called()
