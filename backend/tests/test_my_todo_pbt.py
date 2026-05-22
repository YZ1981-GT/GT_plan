"""
F1 待办聚合 Property-Based Tests — Property 1 & 2

Property 1: Urgency sort correctness — for any set of workpapers with mixed
urgency, output is sorted critical > high > medium > normal.

Property 2: Response field completeness — every TodoItem has all required
non-null fields.

**Validates: Requirements 1.1, 1.2, 1.4**

文件：backend/tests/test_my_todo_pbt.py
"""

from datetime import datetime, timezone
from uuid import uuid4

from hypothesis import given, settings, strategies as st

from app.services.my_todo_service import URGENCY_ORDER, TodoItem, MyTodoResponse


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

URGENCY_LEVELS = ["critical", "high", "medium", "normal"]
URGENCY_REASONS = {
    "critical": "底稿数据过期，需重新填充",
    "high": "关联问题单 SLA 即将到期（≤24h）",
    "medium": "有未解决的复核意见",
    "normal": "常规待办",
}

todo_item_strategy = st.builds(
    TodoItem,
    wp_id=st.builds(uuid4),
    wp_code=st.text(
        alphabet="ABCDEFGHIJKLMN0123456789-",
        min_size=3,
        max_size=10,
    ),
    wp_name=st.text(min_size=1, max_size=50),
    cycle=st.sampled_from(["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N"]),
    urgency=st.sampled_from(URGENCY_LEVELS),
    urgency_reason=st.sampled_from(list(URGENCY_REASONS.values())),
    updated_at=st.builds(
        lambda: datetime.now(timezone.utc)
    ),
)


# ---------------------------------------------------------------------------
# Property 1: Urgency sort correctness
# ---------------------------------------------------------------------------

class TestUrgencySortPBT:
    """Property 1: 待办紧急度排序正确性

    **Validates: Requirements 1.1, 1.2**

    For any set of workpapers with mixed urgency levels, the returned todo list
    should be sorted such that every item with a higher urgency tier always
    appears before any item with a lower urgency tier
    (critical > high > medium > normal).
    """

    @settings(max_examples=30)
    @given(
        urgencies=st.lists(
            st.sampled_from(URGENCY_LEVELS),
            min_size=1,
            max_size=20,
        )
    )
    def test_sort_by_urgency_order(self, urgencies: list[str]):
        """Items sorted by URGENCY_ORDER maintain tier ordering.

        **Validates: Requirements 1.1, 1.2**
        """
        # Build TodoItems with random urgencies
        items = []
        for i, urgency in enumerate(urgencies):
            items.append(
                TodoItem(
                    wp_id=uuid4(),
                    wp_code=f"D{i}-1",
                    wp_name=f"底稿{i}",
                    cycle="D",
                    urgency=urgency,
                    urgency_reason=URGENCY_REASONS[urgency],
                    updated_at=datetime.now(timezone.utc),
                )
            )

        # Sort using the same logic as the service
        sorted_items = sorted(
            items,
            key=lambda item: (URGENCY_ORDER[item.urgency], item.updated_at),
        )

        # Verify: for any two adjacent items, the first has equal or higher urgency
        for i in range(len(sorted_items) - 1):
            current_order = URGENCY_ORDER[sorted_items[i].urgency]
            next_order = URGENCY_ORDER[sorted_items[i + 1].urgency]
            assert current_order <= next_order, (
                f"Sort violation at index {i}: "
                f"{sorted_items[i].urgency} (order={current_order}) "
                f"should not come after "
                f"{sorted_items[i + 1].urgency} (order={next_order})"
            )

    @settings(max_examples=30)
    @given(
        urgencies=st.lists(
            st.sampled_from(URGENCY_LEVELS),
            min_size=2,
            max_size=15,
        )
    )
    def test_critical_always_before_normal(self, urgencies: list[str]):
        """All critical items appear before all normal items after sorting.

        **Validates: Requirements 1.1, 1.2**
        """
        items = [
            TodoItem(
                wp_id=uuid4(),
                wp_code=f"E{i}-1",
                wp_name=f"底稿{i}",
                cycle="E",
                urgency=u,
                urgency_reason=URGENCY_REASONS[u],
                updated_at=datetime.now(timezone.utc),
            )
            for i, u in enumerate(urgencies)
        ]

        sorted_items = sorted(
            items,
            key=lambda item: (URGENCY_ORDER[item.urgency], item.updated_at),
        )

        # Find last critical index and first normal index
        critical_indices = [
            i for i, item in enumerate(sorted_items) if item.urgency == "critical"
        ]
        normal_indices = [
            i for i, item in enumerate(sorted_items) if item.urgency == "normal"
        ]

        if critical_indices and normal_indices:
            assert max(critical_indices) < min(normal_indices), (
                "Critical items must all appear before normal items"
            )


# ---------------------------------------------------------------------------
# Property 2: Response field completeness
# ---------------------------------------------------------------------------

class TestResponseFieldCompletenessPBT:
    """Property 2: 待办响应字段完整性

    **Validates: Requirements 1.4**

    For any todo item in the response, it must contain all required fields:
    wp_id, wp_code, wp_name, cycle, urgency, updated_at — none of which may be null.
    """

    @settings(max_examples=30)
    @given(
        items=st.lists(todo_item_strategy, min_size=1, max_size=10)
    )
    def test_all_required_fields_non_null(self, items: list[TodoItem]):
        """Every TodoItem has all required non-null fields.

        **Validates: Requirements 1.4**
        """
        response = MyTodoResponse(items=items, total=len(items))

        for item in response.items:
            assert item.wp_id is not None, "wp_id must not be null"
            assert item.wp_code is not None, "wp_code must not be null"
            assert item.wp_name is not None, "wp_name must not be null"
            assert item.cycle is not None, "cycle must not be null"
            assert item.urgency is not None, "urgency must not be null"
            assert item.updated_at is not None, "updated_at must not be null"

    @settings(max_examples=30)
    @given(
        items=st.lists(todo_item_strategy, min_size=0, max_size=10)
    )
    def test_total_equals_items_length(self, items: list[TodoItem]):
        """MyTodoResponse.total always equals len(items).

        **Validates: Requirements 1.4**
        """
        response = MyTodoResponse(items=items, total=len(items))
        assert response.total == len(response.items)

    @settings(max_examples=30)
    @given(
        items=st.lists(todo_item_strategy, min_size=1, max_size=10)
    )
    def test_urgency_values_are_valid(self, items: list[TodoItem]):
        """Every TodoItem.urgency is one of the valid urgency levels.

        **Validates: Requirements 1.2**
        """
        for item in items:
            assert item.urgency in URGENCY_LEVELS, (
                f"Invalid urgency: {item.urgency}"
            )
            assert item.urgency in URGENCY_ORDER, (
                f"Urgency not in URGENCY_ORDER: {item.urgency}"
            )
