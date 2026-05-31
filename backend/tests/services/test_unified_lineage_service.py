"""统一溯源服务单元测试 — wp-traceability-panel Task 1.3

mock 3 个 trace service，断言统一输出格式。
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.locate_target import LocateTarget
from app.services.unified_lineage_service import UnifiedLineageService


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(fetchall=lambda: []))
    return db


@pytest.fixture
def service(mock_db):
    return UnifiedLineageService(mock_db)


class TestUnifiedLineageService:
    """统一溯源服务测试"""

    @pytest.mark.asyncio
    async def test_query_lineage_returns_correct_structure(self, service):
        """返回结构包含 current/upstream/downstream/attachments"""
        project_id = uuid.uuid4()

        with patch("app.services.unified_lineage_service.trace_upstream") as mock_up, \
             patch("app.services.unified_lineage_service.trace_downstream") as mock_down, \
             patch("app.services.unified_lineage_service.version_line_service") as mock_vl:
            mock_up.return_value = MagicMock(items=[])
            mock_down.return_value = MagicMock(items=[])
            mock_vl.query_lineage = AsyncMock(return_value=[])

            result = await service.query_lineage(
                project_id=project_id,
                object_type="wp_cell",
                object_id="D2-1",
                direction="both",
            )

        assert "current" in result
        assert "upstream" in result
        assert "downstream" in result
        assert "attachments" in result
        assert isinstance(result["upstream"], list)
        assert isinstance(result["downstream"], list)
        assert isinstance(result["attachments"], list)

    @pytest.mark.asyncio
    async def test_current_target_has_locate_target_fields(self, service):
        """current 节点包含 LocateTarget 必需字段"""
        project_id = uuid.uuid4()

        with patch("app.services.unified_lineage_service.trace_upstream") as mock_up, \
             patch("app.services.unified_lineage_service.trace_downstream") as mock_down, \
             patch("app.services.unified_lineage_service.version_line_service") as mock_vl:
            mock_up.return_value = MagicMock(items=[])
            mock_down.return_value = MagicMock(items=[])
            mock_vl.query_lineage = AsyncMock(return_value=[])

            result = await service.query_lineage(
                project_id=project_id,
                object_type="wp_cell",
                object_id="D2-1",
                direction="both",
            )

        current = result["current"]
        assert "wp_code" in current
        assert current["wp_code"] == "D2-1"

    @pytest.mark.asyncio
    async def test_upstream_delegates_to_wp_trace(self, service):
        """upstream 方向委托 wp_trace_service"""
        from app.services.wp_trace_service import TraceItem, TraceResult

        project_id = uuid.uuid4()
        mock_item = TraceItem(wp_code="A1", sheet="Sheet1", cell="B2", value=100, label="测试")
        mock_result = TraceResult(source="wp", identifier="D2-1", direction="upstream", items=[mock_item])

        with patch("app.services.unified_lineage_service.trace_upstream", return_value=mock_result) as mock_up, \
             patch("app.services.unified_lineage_service.trace_downstream") as mock_down, \
             patch("app.services.unified_lineage_service.version_line_service") as mock_vl:
            mock_down.return_value = MagicMock(items=[])
            mock_vl.query_lineage = AsyncMock(return_value=[])

            result = await service.query_lineage(
                project_id=project_id,
                object_type="wp_cell",
                object_id="D2-1",
                direction="upstream",
            )

        assert len(result["upstream"]) >= 1
        assert result["upstream"][0]["wp_code"] == "A1"
        assert result["upstream"][0]["sheet_name"] == "Sheet1"
        assert result["upstream"][0]["cell_ref"] == "B2"

    @pytest.mark.asyncio
    async def test_downstream_delegates_to_wp_trace(self, service):
        """downstream 方向委托 wp_trace_service"""
        from app.services.wp_trace_service import TraceItem, TraceResult

        project_id = uuid.uuid4()
        mock_item = TraceItem(wp_code="K8", sheet="汇总", cell="C3", value=200, label="下游")
        mock_result = TraceResult(source="wp", identifier="D2-1", direction="downstream", items=[mock_item])

        with patch("app.services.unified_lineage_service.trace_upstream") as mock_up, \
             patch("app.services.unified_lineage_service.trace_downstream", return_value=mock_result) as mock_down, \
             patch("app.services.unified_lineage_service.version_line_service") as mock_vl:
            mock_up.return_value = MagicMock(items=[])
            mock_vl.query_lineage = AsyncMock(return_value=[])

            result = await service.query_lineage(
                project_id=project_id,
                object_type="wp_cell",
                object_id="D2-1",
                direction="downstream",
            )

        assert len(result["downstream"]) >= 1
        assert result["downstream"][0]["wp_code"] == "K8"

    @pytest.mark.asyncio
    async def test_report_trace_delegates_for_note_cell(self, service):
        """note_cell 类型委托 report_trace_service"""
        project_id = uuid.uuid4()

        with patch("app.services.unified_lineage_service.trace_upstream") as mock_up, \
             patch("app.services.unified_lineage_service.trace_downstream") as mock_down, \
             patch("app.services.unified_lineage_service.version_line_service") as mock_vl, \
             patch("app.services.unified_lineage_service.ReportTraceService") as MockRTS:
            mock_up.return_value = MagicMock(items=[])
            mock_down.return_value = MagicMock(items=[])
            mock_vl.query_lineage = AsyncMock(return_value=[])

            mock_rts_instance = MagicMock()
            mock_rts_instance.trace_section = AsyncMock(return_value={
                "section_number": "5",
                "note_data": {"wp_code": "D2-3", "account_codes": ["1001"], "note_title": "货币资金"},
                "workpaper_data": None,
                "top_ledger_entries": [],
            })
            MockRTS.return_value = mock_rts_instance

            result = await service.query_lineage(
                project_id=project_id,
                object_type="note_cell",
                object_id="5",
                direction="both",
            )

        # report_trace 结果应出现在 upstream 中
        assert len(result["upstream"]) >= 1
        assert result["upstream"][0]["wp_code"] == "D2-3"

    @pytest.mark.asyncio
    async def test_direction_upstream_only(self, service):
        """direction=upstream 时不查 downstream"""
        project_id = uuid.uuid4()

        with patch("app.services.unified_lineage_service.trace_upstream") as mock_up, \
             patch("app.services.unified_lineage_service.trace_downstream") as mock_down, \
             patch("app.services.unified_lineage_service.version_line_service") as mock_vl:
            mock_up.return_value = MagicMock(items=[])
            mock_down.return_value = MagicMock(items=[])
            mock_vl.query_lineage = AsyncMock(return_value=[])

            await service.query_lineage(
                project_id=project_id,
                object_type="wp_cell",
                object_id="D2-1",
                direction="upstream",
            )

        mock_down.assert_not_called()

    @pytest.mark.asyncio
    async def test_direction_downstream_only(self, service):
        """direction=downstream 时不查 upstream"""
        project_id = uuid.uuid4()

        with patch("app.services.unified_lineage_service.trace_upstream") as mock_up, \
             patch("app.services.unified_lineage_service.trace_downstream") as mock_down, \
             patch("app.services.unified_lineage_service.version_line_service") as mock_vl:
            mock_up.return_value = MagicMock(items=[])
            mock_down.return_value = MagicMock(items=[])
            mock_vl.query_lineage = AsyncMock(return_value=[])

            await service.query_lineage(
                project_id=project_id,
                object_type="wp_cell",
                object_id="D2-1",
                direction="downstream",
            )

        mock_up.assert_not_called()

    @pytest.mark.asyncio
    async def test_trace_service_failure_graceful(self, service):
        """单个 trace service 失败不影响整体返回"""
        project_id = uuid.uuid4()

        with patch("app.services.unified_lineage_service.trace_upstream", side_effect=Exception("DB error")), \
             patch("app.services.unified_lineage_service.trace_downstream", side_effect=Exception("DB error")), \
             patch("app.services.unified_lineage_service.version_line_service") as mock_vl:
            mock_vl.query_lineage = AsyncMock(side_effect=Exception("Redis error"))

            result = await service.query_lineage(
                project_id=project_id,
                object_type="wp_cell",
                object_id="D2-1",
                direction="both",
            )

        # 即使所有 trace service 失败，仍返回有效结构
        assert "current" in result
        assert result["upstream"] == []
        assert result["downstream"] == []

    @pytest.mark.asyncio
    async def test_object_id_with_exclamation_parsed(self, service):
        """object_id 含 ! 分隔符时正确解析 wp_code 和 cell_ref"""
        project_id = uuid.uuid4()

        with patch("app.services.unified_lineage_service.trace_upstream") as mock_up, \
             patch("app.services.unified_lineage_service.trace_downstream") as mock_down, \
             patch("app.services.unified_lineage_service.version_line_service") as mock_vl:
            mock_up.return_value = MagicMock(items=[])
            mock_down.return_value = MagicMock(items=[])
            mock_vl.query_lineage = AsyncMock(return_value=[])

            result = await service.query_lineage(
                project_id=project_id,
                object_type="wp_cell",
                object_id="D2-3!B5",
                direction="both",
            )

        current = result["current"]
        assert current["wp_code"] == "D2-3"
        assert current["cell_ref"] == "B5"
