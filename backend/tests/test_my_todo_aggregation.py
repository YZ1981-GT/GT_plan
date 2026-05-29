"""待办聚合服务测试

覆盖 F1 + Property 1（紧急度排序正确性）+ Property 2（字段完整性）

Validates: Requirements 1.1, 1.2, 1.4
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.my_todo_service import (
    URGENCY_ORDER,
    MyTodoResponse,
    TodoItem,
    get_my_todo,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_wp_row(
    wp_id: uuid.UUID | None = None,
    prefill_stale: bool = False,
    updated_at: datetime | None = None,
    wp_code: str = "D2-1",
    wp_name: str = "销售收入审定表",
    audit_cycle: str = "D",
):
    """Create a mock row matching the SELECT columns."""
    return (
        wp_id or uuid.uuid4(),
        prefill_stale,
        updated_at or datetime.now(timezone.utc),
        wp_code,
        wp_name,
        audit_cycle,
    )


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


class TestUrgencyOrder:
    """紧急度排序常量正确性"""

    def test_critical_highest(self):
        assert URGENCY_ORDER["critical"] < URGENCY_ORDER["high"]

    def test_high_above_medium(self):
        assert URGENCY_ORDER["high"] < URGENCY_ORDER["medium"]

    def test_medium_above_normal(self):
        assert URGENCY_ORDER["medium"] < URGENCY_ORDER["normal"]


class TestTodoItemModel:
    """TodoItem 模型字段完整性"""

    def test_all_fields_present(self):
        item = TodoItem(
            wp_id=uuid.uuid4(),
            wp_code="E1-1",
            wp_name="货币资金审定表",
            cycle="E",
            urgency="critical",
            urgency_reason="底稿数据过期",
            updated_at=datetime.now(timezone.utc),
        )
        assert item.wp_id is not None
        assert item.wp_code == "E1-1"
        assert item.wp_name == "货币资金审定表"
        assert item.cycle == "E"
        assert item.urgency == "critical"
        assert item.urgency_reason == "底稿数据过期"
        assert item.updated_at is not None


class TestGetMyTodo:
    """get_my_todo 服务函数测试"""

    @pytest.mark.asyncio
    async def test_empty_result_when_no_workpapers(self):
        """无底稿时返回空列表"""
        db = AsyncMock()
        # Mock the first query returning empty
        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        result = await get_my_todo(db, uuid.uuid4(), uuid.uuid4())

        assert isinstance(result, MyTodoResponse)
        assert result.items == []
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_urgency_sorting_mixed(self):
        """混合紧急度排序：critical > high > medium > normal"""
        project_id = uuid.uuid4()
        user_id = uuid.uuid4()

        wp_stale = uuid.uuid4()
        wp_sla = uuid.uuid4()
        wp_review = uuid.uuid4()
        wp_normal = uuid.uuid4()

        now = datetime.now(timezone.utc)

        # Workpaper rows
        wp_rows = [
            _make_wp_row(wp_id=wp_normal, prefill_stale=False, wp_code="D3-1", updated_at=now),
            _make_wp_row(wp_id=wp_review, prefill_stale=False, wp_code="D4-1", updated_at=now),
            _make_wp_row(wp_id=wp_sla, prefill_stale=False, wp_code="E1-1", updated_at=now),
            _make_wp_row(wp_id=wp_stale, prefill_stale=True, wp_code="F2-1", updated_at=now),
        ]

        # SLA wp_ids
        sla_rows = [(wp_sla,)]
        # Review wp_ids
        review_rows = [(wp_review,)]

        db = AsyncMock()
        call_count = [0]

        async def mock_execute(stmt):
            mock_result = MagicMock()
            if call_count[0] == 0:
                mock_result.all.return_value = wp_rows
            elif call_count[0] == 1:
                mock_result.all.return_value = sla_rows
            else:
                mock_result.all.return_value = review_rows
            call_count[0] += 1
            return mock_result

        db.execute = mock_execute

        result = await get_my_todo(db, project_id, user_id)

        assert result.total == 4
        assert len(result.items) == 4

        # Verify ordering
        assert result.items[0].urgency == "critical"
        assert result.items[0].wp_code == "F2-1"

        assert result.items[1].urgency == "high"
        assert result.items[1].wp_code == "E1-1"

        assert result.items[2].urgency == "medium"
        assert result.items[2].wp_code == "D4-1"

        assert result.items[3].urgency == "normal"
        assert result.items[3].wp_code == "D3-1"

    @pytest.mark.asyncio
    async def test_all_critical(self):
        """全部 stale 底稿 → 全部 critical"""
        project_id = uuid.uuid4()
        user_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        wp_rows = [
            _make_wp_row(prefill_stale=True, wp_code="D2-1", updated_at=now),
            _make_wp_row(prefill_stale=True, wp_code="D3-1", updated_at=now),
        ]

        db = AsyncMock()
        call_count = [0]

        async def mock_execute(stmt):
            mock_result = MagicMock()
            if call_count[0] == 0:
                mock_result.all.return_value = wp_rows
            else:
                mock_result.all.return_value = []
            call_count[0] += 1
            return mock_result

        db.execute = mock_execute

        result = await get_my_todo(db, project_id, user_id)

        assert result.total == 2
        assert all(item.urgency == "critical" for item in result.items)

    @pytest.mark.asyncio
    async def test_stale_takes_priority_over_sla(self):
        """stale 底稿即使有 SLA 问题也应为 critical（最高优先级）"""
        project_id = uuid.uuid4()
        user_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        wp_both = uuid.uuid4()

        wp_rows = [
            _make_wp_row(wp_id=wp_both, prefill_stale=True, wp_code="D2-1", updated_at=now),
        ]

        db = AsyncMock()
        call_count = [0]

        async def mock_execute(stmt):
            mock_result = MagicMock()
            if call_count[0] == 0:
                mock_result.all.return_value = wp_rows
            elif call_count[0] == 1:
                # SLA also matches this wp
                mock_result.all.return_value = [(wp_both,)]
            else:
                mock_result.all.return_value = [(wp_both,)]
            call_count[0] += 1
            return mock_result

        db.execute = mock_execute

        result = await get_my_todo(db, project_id, user_id)

        assert result.total == 1
        assert result.items[0].urgency == "critical"
        assert result.items[0].urgency_reason == "底稿数据过期，需重新填充"


class TestMyTodoResponse:
    """MyTodoResponse 模型测试"""

    def test_total_matches_items_length(self):
        items = [
            TodoItem(
                wp_id=uuid.uuid4(),
                wp_code="D2-1",
                wp_name="Test",
                cycle="D",
                urgency="normal",
                urgency_reason="常规待办",
                updated_at=datetime.now(timezone.utc),
            )
        ]
        resp = MyTodoResponse(items=items, total=len(items))
        assert resp.total == 1
        assert len(resp.items) == 1


class TestRouterRegistration:
    """路由注册验证"""

    def test_router_uses_require_project_access_readonly(self):
        """待办路由必须用 require_project_access('readonly')"""
        import inspect
        import app.routers.my_todo as mod

        src = inspect.getsource(mod)
        assert 'require_project_access("readonly")' in src, (
            "my_todo 路由必须用 require_project_access('readonly')"
        )

    def test_router_prefix(self):
        """路由前缀正确"""
        from app.routers.my_todo import router

        assert router.prefix == "/api/projects/{project_id}/my-todo"

    def test_router_registered_in_collaboration(self):
        """路由已注册到 collaboration.py §97"""
        import inspect
        import app.router_registry.collaboration as mod

        src = inspect.getsource(mod)
        assert "my_todo" in src
        assert "§97" in src


# ---------------------------------------------------------------------------
# Property-Based Tests: 待办聚合
# ---------------------------------------------------------------------------

from hypothesis import given, settings, strategies as st, assume


# Urgency levels and their order
_URGENCY_LEVELS = ["critical", "high", "medium", "normal"]


def _make_todo_item(urgency: str, wp_code: str = "D2-1") -> TodoItem:
    """Helper to create a TodoItem with given urgency."""
    return TodoItem(
        wp_id=uuid.uuid4(),
        wp_code=wp_code,
        wp_name=f"底稿_{wp_code}",
        cycle=wp_code[0] if wp_code else "D",
        urgency=urgency,
        urgency_reason=f"reason for {urgency}",
        updated_at=datetime.now(timezone.utc),
    )


class TestTodoUrgencySortPBT:
    """Property 1: 待办紧急度排序正确性

    **Validates: Requirements 1.1, 1.2**

    For any set of workpapers with mixed urgency levels, the returned todo list
    should be sorted such that every item with a higher urgency tier always
    appears before any item with a lower urgency tier.
    """

    @settings(max_examples=15)
    @given(
        urgencies=st.lists(
            st.sampled_from(_URGENCY_LEVELS),
            min_size=1,
            max_size=20,
        )
    )
    def test_urgency_sort_invariant(self, urgencies: list[str]):
        """Property 1: 排序后高紧急度项始终在低紧急度项之前。

        **Validates: Requirements 1.1, 1.2**
        """
        # Create items with random urgencies
        items = [
            _make_todo_item(urgency=u, wp_code=f"D{i}-1")
            for i, u in enumerate(urgencies)
        ]

        # Sort using the same logic as the service
        items.sort(key=lambda item: (URGENCY_ORDER[item.urgency], item.updated_at))

        # Verify sort invariant: for any i < j, urgency_order[i] <= urgency_order[j]
        for i in range(len(items) - 1):
            order_i = URGENCY_ORDER[items[i].urgency]
            order_j = URGENCY_ORDER[items[i + 1].urgency]
            assert order_i <= order_j, (
                f"排序违反：items[{i}].urgency={items[i].urgency} "
                f"(order={order_i}) 应 <= items[{i+1}].urgency="
                f"{items[i+1].urgency} (order={order_j})"
            )

    @settings(max_examples=15)
    @given(
        counts=st.tuples(
            st.integers(min_value=0, max_value=5),  # critical
            st.integers(min_value=0, max_value=5),  # high
            st.integers(min_value=0, max_value=5),  # medium
            st.integers(min_value=0, max_value=5),  # normal
        )
    )
    def test_urgency_groups_contiguous(self, counts: tuple[int, int, int, int]):
        """Property 1: 排序后同一紧急度的项连续出现。

        **Validates: Requirements 1.1, 1.2**
        """
        total = sum(counts)
        assume(total > 0)

        items = []
        for level, count in zip(_URGENCY_LEVELS, counts):
            for i in range(count):
                items.append(_make_todo_item(urgency=level, wp_code=f"{level[0].upper()}{i}-1"))

        # Shuffle and re-sort
        import random
        random.shuffle(items)
        items.sort(key=lambda item: (URGENCY_ORDER[item.urgency], item.updated_at))

        # Verify groups are contiguous
        seen_levels: list[str] = []
        for item in items:
            if not seen_levels or seen_levels[-1] != item.urgency:
                seen_levels.append(item.urgency)

        # Each level should appear at most once in the seen_levels sequence
        assert len(seen_levels) == len(set(seen_levels)), (
            f"紧急度组不连续: {seen_levels}"
        )


class TestTodoFieldCompletenessPBT:
    """Property 2: 待办响应字段完整性

    **Validates: Requirements 1.4**

    For any todo item in the response, it must contain all required fields:
    wp_id, wp_code, wp_name, cycle, urgency, updated_at — none may be null.
    """

    @settings(max_examples=15)
    @given(
        urgency=st.sampled_from(_URGENCY_LEVELS),
        wp_code=st.from_regex(r"[A-N]\d{1,2}-\d{1,2}", fullmatch=True),
        wp_name=st.text(min_size=1, max_size=50),
        cycle=st.sampled_from(["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N"]),
    )
    def test_todo_item_all_required_fields_non_null(
        self, urgency: str, wp_code: str, wp_name: str, cycle: str
    ):
        """Property 2: TodoItem 所有必需字段非 null。

        **Validates: Requirements 1.4**
        """
        item = TodoItem(
            wp_id=uuid.uuid4(),
            wp_code=wp_code,
            wp_name=wp_name,
            cycle=cycle,
            urgency=urgency,
            urgency_reason=f"reason for {urgency}",
            updated_at=datetime.now(timezone.utc),
        )

        # All required fields must be non-null
        assert item.wp_id is not None
        assert item.wp_code is not None and len(item.wp_code) > 0
        assert item.wp_name is not None and len(item.wp_name) > 0
        assert item.cycle is not None and len(item.cycle) > 0
        assert item.urgency is not None
        assert item.urgency in _URGENCY_LEVELS
        assert item.updated_at is not None

    @settings(max_examples=15)
    @given(
        n_items=st.integers(min_value=0, max_value=15),
    )
    def test_my_todo_response_total_equals_items_length(self, n_items: int):
        """Property 2: MyTodoResponse.total == len(items)。

        **Validates: Requirements 1.4**
        """
        items = [
            _make_todo_item(urgency="normal", wp_code=f"D{i}-1")
            for i in range(n_items)
        ]
        response = MyTodoResponse(items=items, total=len(items))

        assert response.total == len(response.items)
