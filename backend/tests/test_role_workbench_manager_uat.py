"""
test_role_workbench_manager_uat.py — P1-4: 项目经理经营驾驶舱 UAT

P1-4.1 四象限：进度、质量、预算、风险
P1-4.2 接入工时预算消耗率和人员负荷
P1-4.3 接入复核 Aging 和质量分
P1-4.4 每个红色指标支持下钻
P1-4.6 UAT：经理定位逾期复核意见与责任人
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.role_workbench_facade import RoleWorkbenchFacade


def _make_mock_db():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
    mock_result.scalar.return_value = 0
    mock_result.one.return_value = MagicMock(total=0, completed=0)
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result
    db.get.return_value = None
    return db


class TestManagerFourQuadrants:
    """P1-4.1: 四象限 — 进度、质量、预算、风险。"""

    @pytest.mark.asyncio
    async def test_manager_has_four_quadrants(self):
        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        result = await facade.get_workbench("manager")

        section_ids = [s["id"] for s in result["sections"]]
        # 进度
        assert "completion_rate" in section_ids
        # 质量（复核 Aging 是质量的核心指标）
        assert "review_aging" in section_ids
        # 预算
        assert "budget_consumption" in section_ids
        # 风险
        assert "risk_overview" in section_ids

    @pytest.mark.asyncio
    async def test_manager_sections_count(self):
        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        result = await facade.get_workbench("manager")
        assert len(result["sections"]) == 5  # 含人员负荷


class TestManagerBudgetConsumption:
    """P1-4.2: 工时预算消耗率和人员负荷。"""

    @pytest.mark.asyncio
    async def test_budget_missing_graceful_degradation(self):
        """budget_hours 缺失时返回 missing_reason。"""
        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        result = await facade.get_workbench("manager")

        budget_section = next(s for s in result["sections"] if s["id"] == "budget_consumption")
        assert len(budget_section["items"]) >= 1
        item = budget_section["items"][0]
        # 由于 mock DB 无 budget_hours，应降级
        assert item.get("missing_reason") or item.get("route")

    @pytest.mark.asyncio
    async def test_personnel_load_section_exists(self):
        """人员负荷 section 存在。"""
        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        result = await facade.get_workbench("manager")

        section_ids = [s["id"] for s in result["sections"]]
        assert "personnel_load" in section_ids


class TestManagerReviewAging:
    """P1-4.3: 复核 Aging。"""

    @pytest.mark.asyncio
    async def test_review_aging_section_structure(self):
        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        result = await facade.get_workbench("manager")

        aging_section = next(s for s in result["sections"] if s["id"] == "review_aging")
        assert aging_section["title"] == "复核 Aging"
        # Items list (empty with mock DB is fine)
        assert isinstance(aging_section["items"], list)


class TestManagerDrilldown:
    """P1-4.4: 每个红色指标支持下钻。"""

    @pytest.mark.asyncio
    async def test_all_items_have_route_for_drilldown(self):
        """所有非降级 item 有 route（支持下钻）。"""
        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        result = await facade.get_workbench("manager")

        for section in result["sections"]:
            for item in section["items"]:
                has_route = bool(item.get("route"))
                has_missing = bool(item.get("missing_reason"))
                # 每个 item 必须能跳转或有原因
                assert has_route or has_missing


class TestManagerUAT:
    """P1-4.6: UAT 经理定位逾期复核意见与责任人。"""

    @pytest.mark.asyncio
    async def test_overdue_review_items_have_route_to_reviews(self):
        """逾期复核意见的 route 指向复核对话页面。"""
        from datetime import datetime, timezone, timedelta

        db = _make_mock_db()
        pid = uuid4()

        # Mock: 返回一条超期 review
        mock_rec = MagicMock()
        mock_rec.id = uuid4()
        mock_rec.working_paper_id = uuid4()
        mock_rec.created_at = datetime.now(timezone.utc) - timedelta(days=5)

        mock_result = MagicMock()
        mock_result.all.return_value = [(mock_rec, "D1")]
        db.execute.return_value = mock_result

        facade = RoleWorkbenchFacade(db=db, project_id=pid, user_id=uuid4())
        items = await facade._fetch_review_aging()

        assert len(items) == 1
        item = items[0]
        assert "/review-conversations" in item["route"]
        assert item["priority"] == "high"  # >72h = high
        assert "超期" in item["label"]
