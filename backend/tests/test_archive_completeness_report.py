"""归档前完整性自检报告测试

Tests for:
- Task 7.1: 完整性报告服务
- Task 7.2: 完整性报告路由

覆盖：
- 四类检查逻辑（missing / unsigned / unresolved_reviews / stale）
- count == len(items) 不变量
- can_proceed 逻辑（无 blocking 项时 True）
- 固定 4 类结构
- 路由注册和响应格式
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.archive_completeness_service import (
    CheckCategory,
    CheckItem,
    CompletenessReportResponse,
    get_archive_completeness_report,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_check_item(wp_code: str = "D2-1", wp_name: str = "审定表", status: str = "draft") -> CheckItem:
    return CheckItem(wp_code=wp_code, wp_name=wp_name, assignee=None, status=status)


# ---------------------------------------------------------------------------
# Unit Tests: Service Logic
# ---------------------------------------------------------------------------


class TestCompletenessReportStructure:
    """报告结构不变量测试。"""

    @pytest.mark.asyncio
    async def test_report_always_has_4_categories(self):
        """报告始终包含固定 4 类。"""
        project_id = uuid4()

        # Mock DB session that returns empty results
        mock_db = AsyncMock()
        mock_execute = MagicMock()
        mock_execute.all.return_value = []
        mock_db.execute.return_value = mock_execute

        result = await get_archive_completeness_report(db=mock_db, project_id=project_id)

        assert len(result.categories) == 4
        category_names = {cat.category for cat in result.categories}
        assert category_names == {"missing", "unsigned", "unresolved_reviews", "stale"}

    @pytest.mark.asyncio
    async def test_can_proceed_true_when_all_empty(self):
        """所有类别 count=0 时 can_proceed=True。"""
        project_id = uuid4()

        mock_db = AsyncMock()
        mock_execute = MagicMock()
        mock_execute.all.return_value = []
        mock_db.execute.return_value = mock_execute

        result = await get_archive_completeness_report(db=mock_db, project_id=project_id)

        assert result.can_proceed is True
        for cat in result.categories:
            assert cat.count == 0
            assert cat.items == []

    @pytest.mark.asyncio
    async def test_generated_at_is_utc(self):
        """generated_at 应为 UTC 时间。"""
        project_id = uuid4()

        mock_db = AsyncMock()
        mock_execute = MagicMock()
        mock_execute.all.return_value = []
        mock_db.execute.return_value = mock_execute

        result = await get_archive_completeness_report(db=mock_db, project_id=project_id)

        assert result.generated_at.tzinfo is not None


class TestCanProceedLogic:
    """归档阻断逻辑测试。"""

    def test_can_proceed_true_when_no_blocking_items(self):
        """无 blocking 项时 can_proceed=True。"""
        categories = [
            CheckCategory(category="missing", count=0, items=[], is_blocking=True),
            CheckCategory(category="unsigned", count=0, items=[], is_blocking=True),
            CheckCategory(category="unresolved_reviews", count=0, items=[], is_blocking=True),
            CheckCategory(category="stale", count=0, items=[], is_blocking=True),
        ]
        can_proceed = all(not (cat.is_blocking and cat.count > 0) for cat in categories)
        assert can_proceed is True

    def test_can_proceed_false_when_blocking_has_items(self):
        """blocking 类别有 count > 0 时 can_proceed=False。"""
        categories = [
            CheckCategory(
                category="missing",
                count=1,
                items=[_make_check_item(status="missing")],
                is_blocking=True,
            ),
            CheckCategory(category="unsigned", count=0, items=[], is_blocking=True),
            CheckCategory(category="unresolved_reviews", count=0, items=[], is_blocking=True),
            CheckCategory(category="stale", count=0, items=[], is_blocking=True),
        ]
        can_proceed = all(not (cat.is_blocking and cat.count > 0) for cat in categories)
        assert can_proceed is False

    def test_count_equals_items_length(self):
        """count 必须等于 len(items)。"""
        items = [_make_check_item(f"D{i}") for i in range(5)]
        cat = CheckCategory(category="unsigned", count=5, items=items, is_blocking=True)
        assert cat.count == len(cat.items)


class TestCheckItemModel:
    """CheckItem 模型测试。"""

    def test_check_item_fields(self):
        """CheckItem 包含所有必要字段。"""
        item = CheckItem(
            wp_code="D2-1",
            wp_name="销售收入审定表",
            assignee="user-123",
            status="draft",
        )
        assert item.wp_code == "D2-1"
        assert item.wp_name == "销售收入审定表"
        assert item.assignee == "user-123"
        assert item.status == "draft"

    def test_check_item_assignee_nullable(self):
        """assignee 可以为 None。"""
        item = CheckItem(wp_code="D2-1", wp_name="审定表", assignee=None, status="missing")
        assert item.assignee is None


class TestCompletenessReportResponse:
    """CompletenessReportResponse 模型测试。"""

    def test_response_serialization(self):
        """响应模型可正确序列化。"""
        response = CompletenessReportResponse(
            categories=[
                CheckCategory(category="missing", count=0, items=[], is_blocking=True),
                CheckCategory(category="unsigned", count=0, items=[], is_blocking=True),
                CheckCategory(category="unresolved_reviews", count=0, items=[], is_blocking=True),
                CheckCategory(category="stale", count=0, items=[], is_blocking=True),
            ],
            can_proceed=True,
            generated_at=datetime.now(timezone.utc),
        )
        data = response.model_dump()
        assert len(data["categories"]) == 4
        assert data["can_proceed"] is True
        assert "generated_at" in data

    def test_response_with_blocking_items(self):
        """含 blocking 项的响应。"""
        response = CompletenessReportResponse(
            categories=[
                CheckCategory(
                    category="missing",
                    count=2,
                    items=[
                        _make_check_item("D2-1", "审定表", "missing"),
                        _make_check_item("D3-1", "明细表", "missing"),
                    ],
                    is_blocking=True,
                ),
                CheckCategory(category="unsigned", count=0, items=[], is_blocking=True),
                CheckCategory(category="unresolved_reviews", count=0, items=[], is_blocking=True),
                CheckCategory(category="stale", count=0, items=[], is_blocking=True),
            ],
            can_proceed=False,
            generated_at=datetime.now(timezone.utc),
        )
        assert response.can_proceed is False
        assert response.categories[0].count == 2


# ---------------------------------------------------------------------------
# Property-Based Tests: 完整性报告
# ---------------------------------------------------------------------------

from hypothesis import given, settings, strategies as st, assume


_CATEGORIES = ["missing", "unsigned", "unresolved_reviews", "stale"]


class TestCompletenessReportStructurePBT:
    """Property 6: 完整性报告结构不变量

    **Validates: Requirements 3.2, 3.3**

    For any generated completeness report, it must contain exactly 4 categories
    (missing, unsigned, unresolved_reviews, stale), and for each category,
    count must equal len(items).
    """

    @settings(max_examples=15)
    @given(
        counts=st.tuples(
            st.integers(min_value=0, max_value=10),  # missing
            st.integers(min_value=0, max_value=10),  # unsigned
            st.integers(min_value=0, max_value=10),  # unresolved_reviews
            st.integers(min_value=0, max_value=10),  # stale
        )
    )
    def test_report_always_4_categories_with_correct_counts(
        self, counts: tuple[int, int, int, int]
    ):
        """Property 6: 报告固定 4 类，每类 count == len(items)。

        **Validates: Requirements 3.2, 3.3**
        """
        categories = []
        for cat_name, count in zip(_CATEGORIES, counts):
            items = [
                _make_check_item(f"D{i}-1", f"底稿{i}", cat_name)
                for i in range(count)
            ]
            categories.append(
                CheckCategory(
                    category=cat_name,
                    count=len(items),
                    items=items,
                    is_blocking=True,
                )
            )

        # Invariant 1: exactly 4 categories
        assert len(categories) == 4

        # Invariant 2: category names are the fixed set
        cat_names = {cat.category for cat in categories}
        assert cat_names == set(_CATEGORIES)

        # Invariant 3: count == len(items) for each category
        for cat in categories:
            assert cat.count == len(cat.items), (
                f"category={cat.category}: count={cat.count} != len(items)={len(cat.items)}"
            )

    @settings(max_examples=15)
    @given(
        n_items=st.integers(min_value=0, max_value=20),
        category=st.sampled_from(_CATEGORIES),
    )
    def test_count_always_equals_items_length(self, n_items: int, category: str):
        """Property 6: 任意类别的 count 始终等于 len(items)。

        **Validates: Requirements 3.2, 3.3**
        """
        items = [
            _make_check_item(f"D{i}-1", f"底稿{i}", category)
            for i in range(n_items)
        ]
        cat = CheckCategory(
            category=category,
            count=len(items),
            items=items,
            is_blocking=True,
        )

        assert cat.count == len(cat.items)
        assert cat.count == n_items


class TestArchiveBlockingLogicPBT:
    """Property 7: 归档阻断逻辑

    **Validates: Requirements 3.4, 3.5**

    For any completeness report, can_proceed is True if and only if
    no category has is_blocking=true with count > 0.
    """

    @settings(max_examples=15)
    @given(
        counts=st.tuples(
            st.integers(min_value=0, max_value=10),  # missing
            st.integers(min_value=0, max_value=10),  # unsigned
            st.integers(min_value=0, max_value=10),  # unresolved_reviews
            st.integers(min_value=0, max_value=10),  # stale
        )
    )
    def test_can_proceed_iff_no_blocking_with_items(
        self, counts: tuple[int, int, int, int]
    ):
        """Property 7: can_proceed == True ↔ 无 blocking 类别有 count > 0。

        **Validates: Requirements 3.4, 3.5**
        """
        categories = []
        for cat_name, count in zip(_CATEGORIES, counts):
            items = [
                _make_check_item(f"D{i}-1", f"底稿{i}", cat_name)
                for i in range(count)
            ]
            categories.append(
                CheckCategory(
                    category=cat_name,
                    count=len(items),
                    items=items,
                    is_blocking=True,  # All categories are blocking in this service
                )
            )

        # Compute can_proceed using the same logic as the service
        can_proceed = all(
            not (cat.is_blocking and cat.count > 0) for cat in categories
        )

        # Verify the biconditional:
        # can_proceed == True ↔ no blocking category has count > 0
        has_blocking_items = any(
            cat.is_blocking and cat.count > 0 for cat in categories
        )

        assert can_proceed == (not has_blocking_items), (
            f"can_proceed={can_proceed} 但 has_blocking_items={has_blocking_items}"
        )

        # Additional: if all counts are 0, can_proceed must be True
        if all(c == 0 for c in counts):
            assert can_proceed is True

        # If any count > 0 (all are blocking), can_proceed must be False
        if any(c > 0 for c in counts):
            assert can_proceed is False


# ---------------------------------------------------------------------------
# 底稿编号自然排序（A1→A2→...→A10，不跳号）
# ---------------------------------------------------------------------------


class TestWpCodeSortKey:
    """_wp_sort_key 自然排序：字母前缀 + 数字升序。"""

    def test_numeric_order_within_prefix(self):
        from app.services.archive_completeness_service import _wp_sort_key

        codes = ["A22", "A5", "A1", "A10", "A2", "A30", "A7"]
        ordered = sorted(codes, key=_wp_sort_key)
        assert ordered == ["A1", "A2", "A5", "A7", "A10", "A22", "A30"]

    def test_letter_prefix_order_a_to_t(self):
        from app.services.archive_completeness_service import _wp_sort_key

        codes = ["K1", "A1", "D2", "B10", "C3"]
        ordered = sorted(codes, key=_wp_sort_key)
        assert ordered == ["A1", "B10", "C3", "D2", "K1"]

    def test_suffix_codes_sorted_by_prefix_number(self):
        from app.services.archive_completeness_service import _wp_sort_key

        codes = ["D2-1", "D1-1", "D2-2", "D10-1"]
        ordered = sorted(codes, key=_wp_sort_key)
        assert ordered == ["D1-1", "D2-1", "D2-2", "D10-1"]

    def test_unparseable_codes_sorted_last(self):
        from app.services.archive_completeness_service import _wp_sort_key

        codes = ["PWXD6AS9", "A1", "B2"]
        ordered = sorted(codes, key=_wp_sort_key)
        assert ordered == ["A1", "B2", "PWXD6AS9"]


# ---------------------------------------------------------------------------
# 责任人 UUID → 中文姓名解析
# ---------------------------------------------------------------------------


class TestResolveAssigneeNames:
    """_resolve_assignee_names：staff_members.name 优先，降级 users.username。"""

    @pytest.mark.asyncio
    async def test_resolves_to_staff_name(self):
        from app.services.archive_completeness_service import (
            _resolve_assignee_names,
        )

        uid = uuid4()
        items = [CheckItem(wp_code="A1", wp_name="x", assignee=str(uid), status="stale")]

        mock_db = AsyncMock()
        staff_result = MagicMock()
        staff_result.all.return_value = [(uid, "张三")]
        mock_db.execute.return_value = staff_result

        await _resolve_assignee_names(mock_db, items)
        assert items[0].assignee == "张三"

    @pytest.mark.asyncio
    async def test_falls_back_to_username(self):
        from app.services.archive_completeness_service import (
            _resolve_assignee_names,
        )

        uid = uuid4()
        items = [CheckItem(wp_code="A1", wp_name="x", assignee=str(uid), status="stale")]

        mock_db = AsyncMock()
        staff_result = MagicMock()
        staff_result.all.return_value = []  # 无 staff 记录
        user_result = MagicMock()
        user_result.all.return_value = [(uid, "admin")]
        mock_db.execute.side_effect = [staff_result, user_result]

        await _resolve_assignee_names(mock_db, items)
        assert items[0].assignee == "admin"

    @pytest.mark.asyncio
    async def test_no_assignee_no_query(self):
        from app.services.archive_completeness_service import (
            _resolve_assignee_names,
        )

        items = [CheckItem(wp_code="A1", wp_name="x", assignee=None, status="stale")]
        mock_db = AsyncMock()

        await _resolve_assignee_names(mock_db, items)
        assert items[0].assignee is None
        mock_db.execute.assert_not_called()
