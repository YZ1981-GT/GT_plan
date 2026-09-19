"""Tests for GET /api/projects/{project_id}/a16/recommended-version endpoint.

Validates: Requirements 5.4, 5.5, 5.6
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.template_selector import (
    A16_ALL_VERSIONS,
    A16_ALWAYS_REQUIRED,
    A16_LABELS,
    get_a16_label,
    recommend_a16_version,
)


# ---------------------------------------------------------------------------
# Unit tests for template_selector integration (logic layer)
# ---------------------------------------------------------------------------


class TestRecommendedVersionLogic:
    """测试 recommended-version 端点的核心逻辑。"""

    def test_default_no_category(self):
        """无 business_category → A16-1"""
        assert recommend_a16_version(None) == "A16-1"
        assert recommend_a16_version("") == "A16-1"

    def test_ipo_category(self):
        """含 IPO → A16-3"""
        assert recommend_a16_version("IPO审计") == "A16-3"
        assert recommend_a16_version("IPO") == "A16-3"

    def test_listed_category(self):
        """含 '上市' 或 'listed' → A16-2"""
        assert recommend_a16_version("上市公司年审") == "A16-2"
        assert recommend_a16_version("listed company") == "A16-2"

    def test_neeq_category(self):
        """含 '新三板' → A16-5"""
        assert recommend_a16_version("新三板审计") == "A16-5"

    def test_bond_category(self):
        """含 '企业债' 或 '债券' → A16-6"""
        assert recommend_a16_version("企业债审计") == "A16-6"
        assert recommend_a16_version("债券发行") == "A16-6"

    def test_generic_category(self):
        """其他类型 → A16-1"""
        assert recommend_a16_version("普通企业") == "A16-1"
        assert recommend_a16_version("年度审计") == "A16-1"

    def test_labels_complete(self):
        """所有 A16 变体都有中文标签。"""
        for code in A16_ALL_VERSIONS:
            label = get_a16_label(code)
            assert label, f"{code} 缺少标签"
            assert len(label) > 0

    def test_always_required_contains_a16_7(self):
        """always_required 始终包含 A16-7。"""
        assert "A16-7" in A16_ALWAYS_REQUIRED


# ---------------------------------------------------------------------------
# Integration test: endpoint handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_returns_correct_structure():
    """端点返回完整结构：recommended_code, recommended_label, all_versions, always_required。"""
    from app.routers.wp_editor_router import get_a16_recommended_version

    project_id = uuid.uuid4()

    # Mock db session
    db = AsyncMock()

    # Mock business_category query result
    biz_row = MagicMock()
    biz_row.__getitem__ = lambda self, i: "IPO审计" if i == 0 else None
    biz_result = MagicMock()
    biz_result.first.return_value = biz_row

    # Mock wp_index query result (A16-3 and A16-7 exist)
    wp_row_1 = MagicMock()
    wp_row_1.__getitem__ = lambda self, i: "A16-3" if i == 0 else None
    wp_row_2 = MagicMock()
    wp_row_2.__getitem__ = lambda self, i: "A16-7" if i == 0 else None
    wp_result = MagicMock()
    wp_result.all.return_value = [wp_row_1, wp_row_2]

    db.execute = AsyncMock(side_effect=[biz_result, wp_result])

    # Mock user
    user = MagicMock()
    user.id = uuid.uuid4()

    # Call endpoint directly
    result = await get_a16_recommended_version(
        project_id=project_id,
        db=db,
        _user=user,
    )

    assert result["recommended_code"] == "A16-3"
    assert result["recommended_label"] == "IPO申报报表审计"
    assert result["always_required"] == ["A16-7"]
    assert len(result["all_versions"]) == 7

    # Verify all_versions structure
    for v in result["all_versions"]:
        assert "code" in v
        assert "label" in v
        assert "exists_in_project" in v
        assert isinstance(v["exists_in_project"], bool)

    # A16-3 and A16-7 exist
    exists_map = {v["code"]: v["exists_in_project"] for v in result["all_versions"]}
    assert exists_map["A16-3"] is True
    assert exists_map["A16-7"] is True
    assert exists_map["A16-1"] is False
    assert exists_map["A16-2"] is False


@pytest.mark.asyncio
async def test_endpoint_no_business_category():
    """business_category 为 None 时返回默认 A16-1。"""
    from app.routers.wp_editor_router import get_a16_recommended_version

    project_id = uuid.uuid4()
    db = AsyncMock()

    # business_category = None
    none_row = MagicMock()
    none_row.__getitem__ = lambda self, i: None
    biz_result = MagicMock()
    biz_result.first.return_value = none_row

    # No existing A16 workpapers
    wp_result = MagicMock()
    wp_result.all.return_value = []

    db.execute = AsyncMock(side_effect=[biz_result, wp_result])
    user = MagicMock()

    result = await get_a16_recommended_version(project_id=project_id, db=db, _user=user)

    assert result["recommended_code"] == "A16-1"
    assert result["recommended_label"] == "一般财报（企业会计准则）"
    assert result["always_required"] == ["A16-7"]

    # No versions exist
    for v in result["all_versions"]:
        assert v["exists_in_project"] is False


@pytest.mark.asyncio
async def test_endpoint_all_versions_exist():
    """项目中已创建所有 A16 变体时全部标记 exists_in_project=True。"""
    from app.routers.wp_editor_router import get_a16_recommended_version

    project_id = uuid.uuid4()
    db = AsyncMock()

    biz_row = MagicMock()
    biz_row.__getitem__ = lambda self, i: "上市" if i == 0 else None
    biz_result = MagicMock()
    biz_result.first.return_value = biz_row

    # All A16-x codes exist
    wp_rows = []
    for code in A16_ALL_VERSIONS:
        row = MagicMock()
        row.__getitem__ = lambda self, i, c=code: c if i == 0 else None
        wp_rows.append(row)
    wp_result = MagicMock()
    wp_result.all.return_value = wp_rows

    db.execute = AsyncMock(side_effect=[biz_result, wp_result])
    user = MagicMock()

    result = await get_a16_recommended_version(project_id=project_id, db=db, _user=user)

    assert result["recommended_code"] == "A16-2"  # 上市 → A16-2
    for v in result["all_versions"]:
        assert v["exists_in_project"] is True


@pytest.mark.asyncio
async def test_endpoint_project_not_found():
    """项目不存在时 business_category 查询返回 None，仍返回默认推荐。"""
    from app.routers.wp_editor_router import get_a16_recommended_version

    project_id = uuid.uuid4()
    db = AsyncMock()

    # No project found
    biz_result = MagicMock()
    biz_result.first.return_value = None

    wp_result = MagicMock()
    wp_result.all.return_value = []

    db.execute = AsyncMock(side_effect=[biz_result, wp_result])
    user = MagicMock()

    result = await get_a16_recommended_version(project_id=project_id, db=db, _user=user)

    # Should still return defaults when project row is None
    assert result["recommended_code"] == "A16-1"
    assert result["recommended_label"] == "一般财报（企业会计准则）"
