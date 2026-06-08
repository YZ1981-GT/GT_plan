"""PlaceholderRegistry 单元测试."""

from pathlib import Path
from uuid import uuid4

import pytest

from app.services.placeholder_registry import PlaceholderRegistry


@pytest.fixture
def registry() -> PlaceholderRegistry:
    return PlaceholderRegistry()


def test_canonical_to_legacy_loaded(registry: PlaceholderRegistry):
    m = registry.canonical_to_legacy()
    assert m.get("company_full_name") == "entity_name"
    assert m.get("signing_cpa") == "cpa_name_1"


def test_get_opt_defaults_type_a(registry: PlaceholderRegistry):
    opts = registry.get_opt_defaults("type_a")
    assert opts.get("key_audit_matters") is True
    assert opts.get("emphasis") is False


def test_get_opt_defaults_fallback_type_d(registry: PlaceholderRegistry):
    opts = registry.get_opt_defaults("unknown_subtype")
    assert "comparative" in opts


def test_detect_missing_fields(registry: PlaceholderRegistry):
    missing = registry.detect_missing_fields(
        {"company_full_name": "[被审计单位名称]", "audit_year": "2025"}
    )
    assert "company_full_name" in missing
    assert "audit_year" not in missing


@pytest.mark.asyncio
async def test_build_placeholder_map_maps_canonical():
    from unittest.mock import AsyncMock, MagicMock

    registry = PlaceholderRegistry()
    project_id = uuid4()
    mock_db = MagicMock()

    mock_result = MagicMock()
    mock_project = MagicMock()
    mock_project.client_name = "测试公司"
    mock_project.report_scope = "standalone"
    mock_project.wizard_state = {
        "basic_info": {"data": {"audit_year": 2025, "cpa_name_1": "张三"}},
    }
    mock_result.scalar_one_or_none.return_value = mock_project
    mock_db.execute = AsyncMock(return_value=mock_result)

    mapping = await registry.build_placeholder_map(project_id, mock_db)
    assert mapping["company_full_name"] == "测试公司"
    assert mapping["signing_cpa"] == "张三"
    assert mapping["audit_year"] == "2025"
