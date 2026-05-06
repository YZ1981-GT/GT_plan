"""Round 4 需求 4: 上年底稿对比 API 测试"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.continuous_audit_service import get_prior_year_workpaper


class TestGetPriorYearWorkpaper:
    """测试 get_prior_year_workpaper 服务函数"""

    @pytest.mark.asyncio
    async def test_returns_none_when_current_wp_not_found(self):
        """当前底稿不存在时返回 None"""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.first.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        result = await get_prior_year_workpaper(db, uuid4(), uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_prior_project(self):
        """当前项目无 prior_year_project_id 时返回 None"""
        db = AsyncMock()
        project_id = uuid4()
        wp_id = uuid4()

        # First call: get wp_code from current workpaper
        wp_row = MagicMock()
        wp_row.__getitem__ = lambda self, idx: "D1" if idx == 0 else None
        mock_result1 = MagicMock()
        mock_result1.first.return_value = wp_row

        # Second call: get prior_year_project_id (None)
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

        result = await get_prior_year_workpaper(db, project_id, wp_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_prior_wp_not_found(self):
        """上年项目中无同 wp_code 底稿时返回 None"""
        db = AsyncMock()
        project_id = uuid4()
        wp_id = uuid4()
        prior_project_id = uuid4()

        # First call: get wp_code
        wp_row = MagicMock()
        wp_row.__getitem__ = lambda self, idx: "D1" if idx == 0 else None
        mock_result1 = MagicMock()
        mock_result1.first.return_value = wp_row

        # Second call: get prior_year_project_id
        prior_row = MagicMock()
        prior_row.__getitem__ = lambda self, idx: str(prior_project_id) if idx == 0 else None
        mock_result2 = MagicMock()
        mock_result2.first.return_value = prior_row

        # Third call: no matching workpaper in prior year
        mock_result3 = MagicMock()
        mock_result3.first.return_value = None

        call_count = 0

        async def mock_execute(stmt, params=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_result1
            elif call_count == 2:
                return mock_result2
            return mock_result3

        db.execute = mock_execute

        result = await get_prior_year_workpaper(db, project_id, wp_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_prior_year_workpaper_data(self):
        """成功返回上年底稿元数据"""
        db = AsyncMock()
        project_id = uuid4()
        wp_id = uuid4()
        prior_project_id = uuid4()
        prior_wp_id = uuid4()

        # First call: get wp_code
        wp_row = MagicMock()
        wp_row.__getitem__ = lambda self, idx: "D1" if idx == 0 else None
        mock_result1 = MagicMock()
        mock_result1.first.return_value = wp_row

        # Second call: get prior_year_project_id
        prior_row = MagicMock()
        prior_row.__getitem__ = lambda self, idx: str(prior_project_id) if idx == 0 else None
        mock_result2 = MagicMock()
        mock_result2.first.return_value = prior_row

        # Third call: found prior year workpaper
        prior_wp_row = MagicMock()
        prior_wp_row.id = prior_wp_id
        prior_wp_row.file_path = "/data/workpapers/prior.xlsx"
        prior_wp_row.parsed_data = {
            "conclusion": "收入确认无重大错报",
            "audited_amount": 1500000.0,
        }
        prior_wp_row.project_id = prior_project_id
        prior_wp_row.wp_code = "D1"
        mock_result3 = MagicMock()
        mock_result3.first.return_value = prior_wp_row

        call_count = 0

        async def mock_execute(stmt, params=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_result1
            elif call_count == 2:
                return mock_result2
            return mock_result3

        db.execute = mock_execute

        result = await get_prior_year_workpaper(db, project_id, wp_id)
        assert result is not None
        assert result["wp_id"] == str(prior_wp_id)
        assert result["wp_code"] == "D1"
        assert result["conclusion"] == "收入确认无重大错报"
        assert result["audited_amount"] == 1500000.0
        assert f"/api/projects/{prior_project_id}/workpapers/{prior_wp_id}/download-file" == result["file_url"]

    @pytest.mark.asyncio
    async def test_returns_null_conclusion_and_amount_when_parsed_data_empty(self):
        """parsed_data 为空时 conclusion 和 audited_amount 为 None"""
        db = AsyncMock()
        project_id = uuid4()
        wp_id = uuid4()
        prior_project_id = uuid4()
        prior_wp_id = uuid4()

        # First call: get wp_code
        wp_row = MagicMock()
        wp_row.__getitem__ = lambda self, idx: "K1" if idx == 0 else None
        mock_result1 = MagicMock()
        mock_result1.first.return_value = wp_row

        # Second call: get prior_year_project_id
        prior_row = MagicMock()
        prior_row.__getitem__ = lambda self, idx: str(prior_project_id) if idx == 0 else None
        mock_result2 = MagicMock()
        mock_result2.first.return_value = prior_row

        # Third call: found prior year workpaper with empty parsed_data
        prior_wp_row = MagicMock()
        prior_wp_row.id = prior_wp_id
        prior_wp_row.file_path = "/data/workpapers/prior_k1.xlsx"
        prior_wp_row.parsed_data = None
        prior_wp_row.project_id = prior_project_id
        prior_wp_row.wp_code = "K1"
        mock_result3 = MagicMock()
        mock_result3.first.return_value = prior_wp_row

        call_count = 0

        async def mock_execute(stmt, params=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_result1
            elif call_count == 2:
                return mock_result2
            return mock_result3

        db.execute = mock_execute

        result = await get_prior_year_workpaper(db, project_id, wp_id)
        assert result is not None
        assert result["wp_id"] == str(prior_wp_id)
        assert result["wp_code"] == "K1"
        assert result["conclusion"] is None
        assert result["audited_amount"] is None


class TestPriorYearRouter:
    """测试路由层 404 行为"""

    @pytest.mark.asyncio
    @patch("app.routers.workpaper_prior_year.get_prior_year_workpaper")
    async def test_returns_404_when_no_prior_year(self, mock_service):
        """无上年底稿时返回 404"""
        from fastapi import HTTPException
        from app.routers.workpaper_prior_year import get_prior_year

        mock_service.return_value = None
        db = AsyncMock()
        user = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_prior_year(uuid4(), uuid4(), db=db, _user=user)

        assert exc_info.value.status_code == 404
        assert "未找到对应的上年底稿" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("app.routers.workpaper_prior_year.get_prior_year_workpaper")
    async def test_returns_data_when_found(self, mock_service):
        """找到上年底稿时返回数据"""
        from app.routers.workpaper_prior_year import get_prior_year

        prior_wp_id = uuid4()
        mock_service.return_value = {
            "wp_id": str(prior_wp_id),
            "wp_code": "D1",
            "file_url": f"/api/projects/{uuid4()}/workpapers/{prior_wp_id}/download-file",
            "conclusion": "无异常",
            "audited_amount": 500000.0,
        }
        db = AsyncMock()
        user = MagicMock()

        result = await get_prior_year(uuid4(), uuid4(), db=db, _user=user)

        assert result["wp_id"] == str(prior_wp_id)
        assert result["wp_code"] == "D1"
        assert result["conclusion"] == "无异常"
        assert result["audited_amount"] == 500000.0
