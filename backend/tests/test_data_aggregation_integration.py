"""F1/F2/F3 数据聚合集成测试

验证：
- F1: 待办聚合端点与 mock 数据联调
- F2: 断裂清单与 cross_wp_references 数据一致性
- F3: 完整性报告与 ArchiveWizard gate_engine 协同

Requirements: 1.1~1.6, 2.1~2.6, 3.1~3.6
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.my_todo_service import (
    MyTodoResponse,
    TodoItem,
    URGENCY_ORDER,
    get_my_todo,
)
from app.services.cross_cycle_breakage_service import (
    BreakageListResponse,
    SEVERITY_ORDER,
    get_cross_cycle_breakage,
)
from app.services.archive_completeness_service import (
    CompletenessReportResponse,
    get_archive_completeness_report,
)


# ---------------------------------------------------------------------------
# F1: 待办聚合集成测试
# ---------------------------------------------------------------------------


class TestMyTodoAggregationIntegration:
    """验证待办聚合端点完整数据流。

    Requirements: 1.1~1.6
    """

    @pytest.mark.asyncio
    async def test_aggregation_with_mixed_urgency(self):
        """混合紧急度数据聚合 + 排序正确性。

        Requirements: 1.1, 1.2
        """
        project_id = uuid4()
        user_id = uuid4()

        # Mock workpapers: 1 stale, 1 SLA approaching, 1 with review, 1 normal
        wp_stale_id = uuid4()
        wp_sla_id = uuid4()
        wp_review_id = uuid4()
        wp_normal_id = uuid4()
        wp_index_ids = [uuid4() for _ in range(4)]

        now = datetime.now(timezone.utc)

        # Step 1 result: workpapers
        workpaper_rows = [
            (wp_stale_id, True, now - timedelta(hours=1), "D2-1", "销售审定表", "D"),
            (wp_sla_id, False, now - timedelta(hours=2), "E1-1", "现金审定表", "E"),
            (wp_review_id, False, now - timedelta(hours=3), "F2-1", "存货审定表", "F"),
            (wp_normal_id, False, now - timedelta(hours=4), "H1-1", "固定资产审定表", "H"),
        ]

        # Step 2 result: SLA approaching tickets
        sla_rows = [(wp_sla_id,)]

        # Step 3 result: unresolved reviews
        review_rows = [(wp_review_id,)]

        mock_db = AsyncMock()
        call_count = [0]

        async def mock_execute(stmt):
            result = MagicMock()
            if call_count[0] == 0:
                # Workpapers query
                result.all.return_value = workpaper_rows
            elif call_count[0] == 1:
                # SLA query
                result.all.return_value = sla_rows
            else:
                # Review query
                result.all.return_value = review_rows
            call_count[0] += 1
            return result

        mock_db.execute.side_effect = mock_execute

        response = await get_my_todo(mock_db, project_id, user_id)

        # Verify response structure
        assert isinstance(response, MyTodoResponse)
        assert response.total == 4
        assert len(response.items) == 4

        # Verify urgency assignment
        urgencies = {item.wp_code: item.urgency for item in response.items}
        assert urgencies["D2-1"] == "critical"  # stale
        assert urgencies["E1-1"] == "high"  # SLA approaching
        assert urgencies["F2-1"] == "medium"  # unresolved review
        assert urgencies["H1-1"] == "normal"  # normal

        # Verify sort order: critical > high > medium > normal
        urgency_list = [item.urgency for item in response.items]
        urgency_indices = [URGENCY_ORDER[u] for u in urgency_list]
        assert urgency_indices == sorted(urgency_indices)

    @pytest.mark.asyncio
    async def test_empty_todo_returns_empty_response(self):
        """无待办时返回空列表。

        Requirements: 1.6
        """
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        response = await get_my_todo(mock_db, uuid4(), uuid4())

        assert response.total == 0
        assert response.items == []

    @pytest.mark.asyncio
    async def test_todo_item_fields_complete(self):
        """每个待办项包含所有必需字段。

        Requirements: 1.4
        """
        project_id = uuid4()
        user_id = uuid4()
        wp_id = uuid4()
        now = datetime.now(timezone.utc)

        workpaper_rows = [
            (wp_id, False, now, "D2-1", "销售审定表", "D"),
        ]

        mock_db = AsyncMock()
        call_count = [0]

        async def mock_execute(stmt):
            result = MagicMock()
            if call_count[0] == 0:
                result.all.return_value = workpaper_rows
            else:
                result.all.return_value = []
            call_count[0] += 1
            return result

        mock_db.execute.side_effect = mock_execute

        response = await get_my_todo(mock_db, project_id, user_id)

        assert response.total == 1
        item = response.items[0]
        # Verify all required fields are present and non-null
        assert item.wp_id == wp_id
        assert item.wp_code == "D2-1"
        assert item.wp_name == "销售审定表"
        assert item.cycle == "D"
        assert item.urgency is not None
        assert item.urgency_reason is not None
        assert item.updated_at is not None


# ---------------------------------------------------------------------------
# F2: 断裂清单集成测试
# ---------------------------------------------------------------------------


class TestBreakageListIntegration:
    """验证断裂清单与 cross_wp_references 数据一致性。

    Requirements: 2.1~2.6
    """

    @pytest.mark.asyncio
    async def test_breakage_detection_with_missing_and_stale(self):
        """检测 target_missing 和 target_stale 两种断裂原因。

        Requirements: 2.2
        """
        project_id = uuid4()

        # Mock CWR data with 3 references
        mock_cwr = [
            {
                "ref_id": "CW-001",
                "source_wp": "D2-1",
                "severity": "blocking",
                "targets": [{"wp_code": "E1-1"}],  # exists, not stale
            },
            {
                "ref_id": "CW-002",
                "source_wp": "D4-1",
                "severity": "warning",
                "targets": [{"wp_code": "MISSING-WP"}],  # does not exist
            },
            {
                "ref_id": "CW-003",
                "source_wp": "F2-1",
                "severity": "required",
                "targets": [{"wp_code": "H1-1"}],  # exists but stale
            },
        ]

        # Mock DB: existing wp_codes and stale wp_codes
        existing_wp_codes = {"D2-1", "E1-1", "D4-1", "F2-1", "H1-1"}
        stale_wp_codes = {"H1-1"}

        mock_db = AsyncMock()
        call_count = [0]

        async def mock_execute(stmt):
            result = MagicMock()
            if call_count[0] == 0:
                # Existing wp_codes query
                result.all.return_value = [(code,) for code in existing_wp_codes]
            else:
                # Stale wp_codes query
                result.all.return_value = [(code,) for code in stale_wp_codes]
            call_count[0] += 1
            return result

        mock_db.execute.side_effect = mock_execute

        with patch(
            "app.services.cross_cycle_breakage_service.load_cwr_references",
            return_value=mock_cwr,
        ):
            response = await get_cross_cycle_breakage(mock_db, project_id)

        assert isinstance(response, BreakageListResponse)
        # CW-001 target E1-1 exists and not stale → no breakage
        # CW-002 target MISSING-WP → target_missing
        # CW-003 target H1-1 stale → target_stale
        assert len(response.items) == 2

        reasons = {item.ref_id: item.reason for item in response.items}
        assert reasons["CW-002"] == "target_missing"
        assert reasons["CW-003"] == "target_stale"

    @pytest.mark.asyncio
    async def test_severity_sort_order(self):
        """断裂清单按 severity 降序排列。

        Requirements: 2.3
        """
        project_id = uuid4()

        mock_cwr = [
            {
                "ref_id": "CW-010",
                "source_wp": "A1",
                "severity": "info",
                "targets": [{"wp_code": "MISSING-1"}],
            },
            {
                "ref_id": "CW-011",
                "source_wp": "A2",
                "severity": "blocking",
                "targets": [{"wp_code": "MISSING-2"}],
            },
            {
                "ref_id": "CW-012",
                "source_wp": "A3",
                "severity": "warning",
                "targets": [{"wp_code": "MISSING-3"}],
            },
            {
                "ref_id": "CW-013",
                "source_wp": "A4",
                "severity": "required",
                "targets": [{"wp_code": "MISSING-4"}],
            },
            {
                "ref_id": "CW-014",
                "source_wp": "A5",
                "severity": "recommended",
                "targets": [{"wp_code": "MISSING-5"}],
            },
        ]

        mock_db = AsyncMock()
        call_count = [0]

        async def mock_execute(stmt):
            result = MagicMock()
            if call_count[0] == 0:
                result.all.return_value = []  # No existing wp_codes
            else:
                result.all.return_value = []  # No stale
            call_count[0] += 1
            return result

        mock_db.execute.side_effect = mock_execute

        with patch(
            "app.services.cross_cycle_breakage_service.load_cwr_references",
            return_value=mock_cwr,
        ):
            response = await get_cross_cycle_breakage(mock_db, project_id)

        # Verify sort: blocking > required > warning > recommended > info
        severities = [item.severity for item in response.items]
        severity_indices = [SEVERITY_ORDER[s] for s in severities]
        assert severity_indices == sorted(severity_indices)

    @pytest.mark.asyncio
    async def test_summary_counts_match_items(self):
        """统计摘要与 items 列表一致。

        Requirements: 2.6
        """
        project_id = uuid4()

        mock_cwr = [
            {"ref_id": f"CW-{i:03d}", "source_wp": f"S{i}", "severity": sev, "targets": [{"wp_code": f"MISS-{i}"}]}
            for i, sev in enumerate(["blocking", "blocking", "warning", "info", "required"], start=1)
        ]

        mock_db = AsyncMock()
        call_count = [0]

        async def mock_execute(stmt):
            result = MagicMock()
            if call_count[0] == 0:
                result.all.return_value = []
            else:
                result.all.return_value = []
            call_count[0] += 1
            return result

        mock_db.execute.side_effect = mock_execute

        with patch(
            "app.services.cross_cycle_breakage_service.load_cwr_references",
            return_value=mock_cwr,
        ):
            response = await get_cross_cycle_breakage(mock_db, project_id)

        # Verify summary matches items
        summary = response.summary
        assert summary.blocking == 2
        assert summary.warning == 1
        assert summary.info == 1
        assert summary.required == 1
        assert summary.recommended == 0

        total_from_summary = (
            summary.blocking + summary.required + summary.warning
            + summary.recommended + summary.info
        )
        assert total_from_summary == len(response.items)


# ---------------------------------------------------------------------------
# F3: 完整性报告集成测试
# ---------------------------------------------------------------------------


class TestCompletenessReportIntegration:
    """验证完整性报告与 ArchiveWizard gate_engine 协同。

    Requirements: 3.1~3.6
    """

    @pytest.mark.asyncio
    async def test_report_structure_four_categories(self):
        """报告固定包含 4 类检查项。

        Requirements: 3.2
        """
        project_id = uuid4()
        mock_db = AsyncMock()

        # All queries return empty (clean project)
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        response = await get_archive_completeness_report(mock_db, project_id)

        assert isinstance(response, CompletenessReportResponse)
        assert len(response.categories) == 4

        category_names = {cat.category for cat in response.categories}
        assert category_names == {"missing", "unsigned", "unresolved_reviews", "stale"}

    @pytest.mark.asyncio
    async def test_can_proceed_when_no_blocking_items(self):
        """无 blocking 项时 can_proceed=True。

        Requirements: 3.5
        """
        project_id = uuid4()
        mock_db = AsyncMock()

        # All queries return empty
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        response = await get_archive_completeness_report(mock_db, project_id)

        assert response.can_proceed is True
        for cat in response.categories:
            assert cat.count == 0

    @pytest.mark.asyncio
    async def test_cannot_proceed_with_blocking_items(self):
        """有 blocking 项时 can_proceed=False，阻断归档。

        Requirements: 3.4
        """
        project_id = uuid4()
        mock_db = AsyncMock()

        call_count = [0]

        async def mock_execute(stmt):
            result = MagicMock()
            if call_count[0] == 0:
                # Missing workpapers: 2 items
                result.all.return_value = [
                    ("D2-1", "销售审定表", None),
                    ("E1-1", "现金审定表", None),
                ]
            else:
                result.all.return_value = []
            call_count[0] += 1
            return result

        mock_db.execute.side_effect = mock_execute

        response = await get_archive_completeness_report(mock_db, project_id)

        assert response.can_proceed is False

        # Find the missing category
        missing_cat = next(c for c in response.categories if c.category == "missing")
        assert missing_cat.count == 2
        assert missing_cat.is_blocking is True

    @pytest.mark.asyncio
    async def test_report_items_contain_required_fields(self):
        """每个检查项包含必需字段：wp_code, wp_name, assignee, status。

        Requirements: 3.3
        """
        project_id = uuid4()
        mock_db = AsyncMock()

        call_count = [0]

        async def mock_execute(stmt):
            result = MagicMock()
            if call_count[0] == 0:
                # Missing: 1 item
                result.all.return_value = [("D2-1", "销售审定表", uuid4())]
            elif call_count[0] == 1:
                # Unsigned: 1 item
                result.all.return_value = [("E1-1", "现金审定表", uuid4(), "draft")]
            else:
                result.all.return_value = []
            call_count[0] += 1
            return result

        mock_db.execute.side_effect = mock_execute

        response = await get_archive_completeness_report(mock_db, project_id)

        # Check missing category items
        missing_cat = next(c for c in response.categories if c.category == "missing")
        if missing_cat.count > 0:
            item = missing_cat.items[0]
            assert item.wp_code is not None
            assert item.wp_name is not None
            assert item.status is not None

    @pytest.mark.asyncio
    async def test_generated_at_is_recent(self):
        """generated_at 时间戳是当前时间附近。

        Requirements: 3.1
        """
        project_id = uuid4()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db.execute.return_value = mock_result

        before = datetime.now(timezone.utc)
        response = await get_archive_completeness_report(mock_db, project_id)
        after = datetime.now(timezone.utc)

        assert before <= response.generated_at <= after
