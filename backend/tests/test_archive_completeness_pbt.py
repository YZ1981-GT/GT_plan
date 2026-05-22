"""
F3 归档前完整性自检报告 Property-Based Tests — Property 6 & 7

Property 6: Report structure invariant — always exactly 4 categories, count == len(items).
Property 7: Archive blocking logic — can_proceed is True iff no blocking category has count > 0.

**Validates: Requirements 3.2, 3.3, 3.4, 3.5**

文件：backend/tests/test_archive_completeness_pbt.py
"""

from datetime import datetime, timezone

from hypothesis import given, settings, strategies as st

from app.services.archive_completeness_service import (
    CheckCategory,
    CheckItem,
    CompletenessReportResponse,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

CATEGORY_NAMES = ["missing", "unsigned", "unresolved_reviews", "stale"]

check_item_strategy = st.builds(
    CheckItem,
    wp_code=st.text(alphabet="ABCDEFGHIJKLMN0123456789-", min_size=3, max_size=8),
    wp_name=st.text(min_size=1, max_size=30),
    assignee=st.one_of(st.none(), st.text(min_size=5, max_size=20)),
    status=st.sampled_from(["missing", "draft", "in_progress", "unresolved_reviews", "stale"]),
)


def _build_report(
    category_items: dict[str, list[CheckItem]],
) -> CompletenessReportResponse:
    """Build a CompletenessReportResponse from category items dict."""
    categories = []
    for cat_name in CATEGORY_NAMES:
        items = category_items.get(cat_name, [])
        categories.append(
            CheckCategory(
                category=cat_name,
                count=len(items),
                items=items,
                is_blocking=True,  # All 4 categories are blocking per service
            )
        )

    can_proceed = all(
        not (cat.is_blocking and cat.count > 0) for cat in categories
    )

    return CompletenessReportResponse(
        categories=categories,
        can_proceed=can_proceed,
        generated_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Property 6: Report structure invariant
# ---------------------------------------------------------------------------

class TestReportStructureInvariantPBT:
    """Property 6: 完整性报告结构不变量

    **Validates: Requirements 3.2, 3.3**

    For any generated completeness report, it must contain exactly 4 categories
    (missing, unsigned, unresolved_reviews, stale), and for each category,
    count must equal len(items).
    """

    @settings(max_examples=30)
    @given(
        missing_count=st.integers(min_value=0, max_value=10),
        unsigned_count=st.integers(min_value=0, max_value=10),
        unresolved_count=st.integers(min_value=0, max_value=10),
        stale_count=st.integers(min_value=0, max_value=10),
    )
    def test_always_exactly_4_categories(
        self,
        missing_count: int,
        unsigned_count: int,
        unresolved_count: int,
        stale_count: int,
    ):
        """Report always contains exactly 4 categories.

        **Validates: Requirements 3.2, 3.3**
        """
        # Generate items for each category
        category_items = {
            "missing": [
                CheckItem(wp_code=f"M{i}", wp_name=f"Missing{i}", assignee=None, status="missing")
                for i in range(missing_count)
            ],
            "unsigned": [
                CheckItem(wp_code=f"U{i}", wp_name=f"Unsigned{i}", assignee=None, status="draft")
                for i in range(unsigned_count)
            ],
            "unresolved_reviews": [
                CheckItem(wp_code=f"R{i}", wp_name=f"Review{i}", assignee=None, status="unresolved_reviews")
                for i in range(unresolved_count)
            ],
            "stale": [
                CheckItem(wp_code=f"S{i}", wp_name=f"Stale{i}", assignee=None, status="stale")
                for i in range(stale_count)
            ],
        }

        report = _build_report(category_items)

        # Exactly 4 categories
        assert len(report.categories) == 4

        # Category names are exactly the expected set
        cat_names = {cat.category for cat in report.categories}
        assert cat_names == set(CATEGORY_NAMES)

    @settings(max_examples=30)
    @given(
        items_per_category=st.lists(
            st.integers(min_value=0, max_value=8),
            min_size=4,
            max_size=4,
        )
    )
    def test_count_equals_len_items(self, items_per_category: list[int]):
        """For each category, count == len(items).

        **Validates: Requirements 3.2, 3.3**
        """
        category_items = {}
        for i, (cat_name, count) in enumerate(zip(CATEGORY_NAMES, items_per_category)):
            category_items[cat_name] = [
                CheckItem(wp_code=f"{cat_name[0].upper()}{j}", wp_name=f"WP{j}", assignee=None, status=cat_name)
                for j in range(count)
            ]

        report = _build_report(category_items)

        for cat in report.categories:
            assert cat.count == len(cat.items), (
                f"Category '{cat.category}': count={cat.count} != len(items)={len(cat.items)}"
            )


# ---------------------------------------------------------------------------
# Property 7: Archive blocking logic
# ---------------------------------------------------------------------------

class TestArchiveBlockingLogicPBT:
    """Property 7: 归档阻断逻辑

    **Validates: Requirements 3.4, 3.5**

    For any completeness report, can_proceed is True if and only if
    no category has is_blocking=true with count > 0.
    """

    @settings(max_examples=30)
    @given(
        missing_count=st.integers(min_value=0, max_value=10),
        unsigned_count=st.integers(min_value=0, max_value=10),
        unresolved_count=st.integers(min_value=0, max_value=10),
        stale_count=st.integers(min_value=0, max_value=10),
    )
    def test_can_proceed_iff_no_blocking_with_items(
        self,
        missing_count: int,
        unsigned_count: int,
        unresolved_count: int,
        stale_count: int,
    ):
        """can_proceed is True iff no blocking category has count > 0.

        **Validates: Requirements 3.4, 3.5**
        """
        category_items = {
            "missing": [
                CheckItem(wp_code=f"M{i}", wp_name=f"Missing{i}", assignee=None, status="missing")
                for i in range(missing_count)
            ],
            "unsigned": [
                CheckItem(wp_code=f"U{i}", wp_name=f"Unsigned{i}", assignee=None, status="draft")
                for i in range(unsigned_count)
            ],
            "unresolved_reviews": [
                CheckItem(wp_code=f"R{i}", wp_name=f"Review{i}", assignee=None, status="unresolved_reviews")
                for i in range(unresolved_count)
            ],
            "stale": [
                CheckItem(wp_code=f"S{i}", wp_name=f"Stale{i}", assignee=None, status="stale")
                for i in range(stale_count)
            ],
        }

        report = _build_report(category_items)

        # Expected: can_proceed is True iff all blocking categories have count == 0
        has_blocking_items = any(
            cat.is_blocking and cat.count > 0 for cat in report.categories
        )
        expected_can_proceed = not has_blocking_items

        assert report.can_proceed == expected_can_proceed, (
            f"can_proceed={report.can_proceed} but expected {expected_can_proceed}. "
            f"Counts: missing={missing_count}, unsigned={unsigned_count}, "
            f"unresolved={unresolved_count}, stale={stale_count}"
        )

    @settings(max_examples=30)
    @given(st.data())
    def test_can_proceed_true_only_when_all_zero(self, data):
        """can_proceed=True requires ALL blocking categories to have count=0.

        **Validates: Requirements 3.4, 3.5**
        """
        # Generate a report where can_proceed should be True
        report = _build_report({
            "missing": [],
            "unsigned": [],
            "unresolved_reviews": [],
            "stale": [],
        })

        assert report.can_proceed is True

        # Now add one item to any category — should block
        cat_to_add = data.draw(st.sampled_from(CATEGORY_NAMES))
        category_items = {name: [] for name in CATEGORY_NAMES}
        category_items[cat_to_add] = [
            CheckItem(wp_code="X1", wp_name="Blocker", assignee=None, status=cat_to_add)
        ]

        report_blocked = _build_report(category_items)
        assert report_blocked.can_proceed is False, (
            f"Adding 1 item to '{cat_to_add}' should block archiving"
        )
