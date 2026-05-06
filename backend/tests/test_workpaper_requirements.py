"""Round 4 需求 1: 底稿程序要求聚合 API 测试"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.workpaper_requirements_service import (
    get_workpaper_requirements,
    _get_workpaper_info,
    _get_related_procedures,
    _get_prior_year_summary,
    _get_manual_for_cycle,
)


class TestGetManualForCycle:
    """测试操作手册获取"""

    def test_returns_none_for_empty_cycle(self):
        assert _get_manual_for_cycle(None) is None
        assert _get_manual_for_cycle("") is None

    @patch("app.services.workpaper_requirements_service.get_operation_manual")
    def test_returns_manual_content(self, mock_get_manual):
        mock_get_manual.return_value = "# D循环操作手册\n步骤1..."
        result = _get_manual_for_cycle("D")
        assert result == "# D循环操作手册\n步骤1..."
        mock_get_manual.assert_called_once_with("D", max_chars=8000)

    @patch("app.services.workpaper_requirements_service.get_operation_manual")
    def test_returns_none_when_manual_not_found(self, mock_get_manual):
        mock_get_manual.return_value = None
        result = _get_manual_for_cycle("Z")
        assert result is None

    @patch("app.services.workpaper_requirements_service.get_operation_manual")
    def test_returns_none_on_exception(self, mock_get_manual):
        mock_get_manual.side_effect = Exception("file not found")
        result = _get_manual_for_cycle("D")
        assert result is None


class TestGetWorkpaperInfo:
    """测试底稿信息获取"""

    @pytest.mark.asyncio
    async def test_returns_none_when_wp_not_found(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.first.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        result = await _get_workpaper_info(db, uuid4(), uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_wp_info(self):
        db = AsyncMock()
        wp_id = uuid4()
        wp_index_id = uuid4()

        mock_row = MagicMock()
        mock_row.id = wp_id
        mock_row.wp_index_id = wp_index_id
        mock_row.parsed_data = {"conclusion": "无异常"}
        mock_row.status = "draft"
        mock_row.wp_code = "D1"
        mock_row.wp_name = "收入确认底稿"
        mock_row.audit_cycle = "D"

        mock_result = MagicMock()
        mock_result.first.return_value = mock_row
        db.execute = AsyncMock(return_value=mock_result)

        result = await _get_workpaper_info(db, uuid4(), wp_id)
        assert result is not None
        assert result["wp_code"] == "D1"
        assert result["audit_cycle"] == "D"
        assert result["wp_name"] == "收入确认底稿"


class TestGetRelatedProcedures:
    """测试关联程序获取"""

    @pytest.mark.asyncio
    async def test_returns_procedures_by_wp_id(self):
        db = AsyncMock()
        wp_id = uuid4()
        project_id = uuid4()

        proc = MagicMock()
        proc.id = uuid4()
        proc.procedure_code = "D-01"
        proc.procedure_name = "收入确认测试"
        proc.status = "execute"
        proc.execution_status = "not_started"
        proc.sort_order = 1
        proc.assigned_to = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [proc]
        db.execute = AsyncMock(return_value=mock_result)

        result = await _get_related_procedures(db, project_id, wp_id, "D1", "D")
        assert len(result) == 1
        assert result[0]["procedure_code"] == "D-01"
        assert result[0]["procedure_name"] == "收入确认测试"
        assert result[0]["status"] == "execute"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_procedures(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        result = await _get_related_procedures(db, uuid4(), uuid4(), None, None)
        assert result == []


class TestGetPriorYearSummary:
    """测试上年结论摘要获取"""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_prior_project(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.first.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        wp_info = {"wp_code": "D1", "wp_name": "收入确认底稿"}
        result = await _get_prior_year_summary(db, uuid4(), wp_info)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_wp_code(self):
        db = AsyncMock()
        # First call returns prior_year_project_id
        prior_row = MagicMock()
        prior_row.__getitem__ = lambda self, idx: str(uuid4()) if idx == 0 else None
        mock_result = MagicMock()
        mock_result.first.return_value = prior_row
        db.execute = AsyncMock(return_value=mock_result)

        wp_info = {"wp_code": None, "wp_name": "底稿"}
        result = await _get_prior_year_summary(db, uuid4(), wp_info)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_prior_year_summary(self):
        db = AsyncMock()
        prior_project_id = uuid4()
        prior_wp_id = uuid4()

        # First call: get prior_year_project_id
        prior_row = MagicMock()
        prior_row.__getitem__ = lambda self, idx: str(prior_project_id) if idx == 0 else None
        mock_result1 = MagicMock()
        mock_result1.first.return_value = prior_row

        # Second call: get prior year workpaper
        prior_wp_row = MagicMock()
        prior_wp_row.id = prior_wp_id
        prior_wp_row.wp_code = "D1"
        prior_wp_row.wp_name = "收入确认底稿"
        prior_wp_row.status = "review_passed"
        prior_wp_row.parsed_data = {"conclusion": "收入确认无重大错报"}
        mock_result2 = MagicMock()
        mock_result2.first.return_value = prior_wp_row

        call_count = 0

        async def mock_execute(stmt, params=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_result1
            return mock_result2

        db.execute = mock_execute

        wp_info = {"wp_code": "D1", "wp_name": "收入确认底稿"}
        result = await _get_prior_year_summary(db, uuid4(), wp_info)
        assert result is not None
        assert result["wp_code"] == "D1"
        assert result["conclusion"] == "收入确认无重大错报"
        assert result["status"] == "review_passed"

    @pytest.mark.asyncio
    async def test_returns_none_when_prior_wp_not_found(self):
        db = AsyncMock()
        prior_project_id = uuid4()

        # First call: get prior_year_project_id
        prior_row = MagicMock()
        prior_row.__getitem__ = lambda self, idx: str(prior_project_id) if idx == 0 else None
        mock_result1 = MagicMock()
        mock_result1.first.return_value = prior_row

        # Second call: no matching workpaper
        mock_result2 = MagicMock()
        mock_result2.first.return_value = None

        call_count = 0

        async def mock_execute(stmt, params=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_result1
            return mock_result2

        db.execute = mock_execute

        wp_info = {"wp_code": "D1", "wp_name": "收入确认底稿"}
        result = await _get_prior_year_summary(db, uuid4(), wp_info)
        assert result is None


class TestGetWorkpaperRequirements:
    """测试聚合接口"""

    @pytest.mark.asyncio
    @patch("app.services.workpaper_requirements_service._get_prior_year_summary")
    @patch("app.services.workpaper_requirements_service._get_related_procedures")
    @patch("app.services.workpaper_requirements_service._get_manual_for_cycle")
    @patch("app.services.workpaper_requirements_service._get_workpaper_info")
    async def test_returns_all_sources(
        self, mock_wp_info, mock_manual, mock_procedures, mock_prior
    ):
        project_id = uuid4()
        wp_id = uuid4()
        db = AsyncMock()

        mock_wp_info.return_value = {
            "id": wp_id,
            "wp_index_id": uuid4(),
            "parsed_data": None,
            "status": "draft",
            "wp_code": "D1",
            "wp_name": "收入确认底稿",
            "audit_cycle": "D",
        }
        mock_manual.return_value = "# D循环操作手册"
        mock_procedures.return_value = [
            {
                "id": str(uuid4()),
                "procedure_code": "D-01",
                "procedure_name": "收入确认测试",
                "status": "execute",
                "execution_status": "not_started",
                "sort_order": 1,
                "assigned_to": None,
            }
        ]
        mock_prior.return_value = {
            "wp_id": str(uuid4()),
            "wp_code": "D1",
            "wp_name": "收入确认底稿",
            "conclusion": "无异常",
            "status": "review_passed",
        }

        result = await get_workpaper_requirements(db, project_id, wp_id)

        assert result["manual"] == "# D循环操作手册"
        assert len(result["procedures"]) == 1
        assert result["procedures"][0]["procedure_code"] == "D-01"
        assert result["prior_year_summary"]["conclusion"] == "无异常"

    @pytest.mark.asyncio
    @patch("app.services.workpaper_requirements_service._get_workpaper_info")
    async def test_returns_empty_when_wp_not_found(self, mock_wp_info):
        db = AsyncMock()
        mock_wp_info.return_value = None

        result = await get_workpaper_requirements(db, uuid4(), uuid4())

        assert result["manual"] is None
        assert result["procedures"] == []
        assert result["prior_year_summary"] is None
