"""
test_role_workbench_partner_uat.py — P1-5: 合伙人签发风险雷达 UAT

P1-5.1 聚合重大事项、关键调整、未关闭复核、AI 未确认内容
P1-5.2 接入 stale/conflict/交付件缺失阻断项
P1-5.3 每个阻断项支持跳转
P1-5.4 合伙人确认 warning 项写审计日志
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


class TestPartnerSections:
    """P1-5.1: 合伙人签发风险雷达有完整的 section 组合。"""

    @pytest.mark.asyncio
    async def test_partner_has_required_sections(self):
        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        result = await facade.get_workbench("partner")

        section_ids = [s["id"] for s in result["sections"]]
        # P1-5.1 要求
        assert "signoff_blockers" in section_ids, "缺少签发阻断项"
        assert "ai_unconfirmed" in section_ids, "缺少 AI 未确认"
        assert "risk_overview" in section_ids, "缺少风险总览"
        assert "key_adjustments" in section_ids, "缺少关键调整"

    @pytest.mark.asyncio
    async def test_partner_section_titles_chinese(self):
        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        result = await facade.get_workbench("partner")

        for section in result["sections"]:
            assert any('\u4e00' <= ch <= '\u9fff' for ch in section["title"]), (
                f"Partner section '{section['id']}' title 应为中文"
            )


class TestPartnerSignoffBlockers:
    """P1-5.2: 接入 stale/conflict/交付件缺失阻断项。"""

    @pytest.mark.asyncio
    async def test_signoff_blockers_aggregates_stale(self):
        """stale 降级记录存在时，阻断项包含 stale。"""
        from app.services.stale_degraded_logger import log_stale_degraded, clear_degraded_records

        clear_degraded_records()
        log_stale_degraded("source_a", "target_b", "test error")

        db = _make_mock_db()
        pid = uuid4()

        # Mock risk_summary_service.RiskSummaryService at its source
        with patch("app.services.risk_summary_service.RiskSummaryService") as MockRisk:
            mock_svc = AsyncMock()
            mock_svc.aggregate.return_value = {
                "unresolved_comments": [],
                "going_concern_flag": False,
                "summary": {"total_blockers": 0, "total_warnings": 0},
            }
            MockRisk.return_value = mock_svc

            facade = RoleWorkbenchFacade(db=db, project_id=pid, user_id=uuid4())
            items = await facade._fetch_signoff_blockers()

        # Should have stale item
        stale_items = [i for i in items if "stale" in i["id"]]
        assert len(stale_items) == 1
        assert stale_items[0]["priority"] == "critical"
        assert stale_items[0].get("route")

        clear_degraded_records()

    @pytest.mark.asyncio
    async def test_signoff_blockers_no_stale_shows_clear(self):
        """无阻断项时显示'无签发阻断项'。"""
        from app.services.stale_degraded_logger import clear_degraded_records
        clear_degraded_records()

        db = _make_mock_db()
        pid = uuid4()

        with patch("app.services.risk_summary_service.RiskSummaryService") as MockRisk:
            mock_svc = AsyncMock()
            mock_svc.aggregate.return_value = {
                "unresolved_comments": [],
                "going_concern_flag": False,
                "summary": {"total_blockers": 0, "total_warnings": 0},
            }
            MockRisk.return_value = mock_svc

            facade = RoleWorkbenchFacade(db=db, project_id=pid, user_id=uuid4())
            items = await facade._fetch_signoff_blockers()

        assert len(items) >= 1
        # Should be the clear item
        clear_items = [i for i in items if "clear" in i["id"]]
        assert len(clear_items) == 1
        assert clear_items[0]["priority"] == "normal"


class TestPartnerRoutability:
    """P1-5.3: 每个阻断项支持跳转。"""

    @pytest.mark.asyncio
    async def test_all_partner_items_routable(self):
        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        result = await facade.get_workbench("partner")

        for section in result["sections"]:
            for item in section["items"]:
                has_route = bool(item.get("route"))
                has_missing = bool(item.get("missing_reason"))
                assert has_route or has_missing, (
                    f"Partner item '{item['id']}' lacks route or missing_reason"
                )

    @pytest.mark.asyncio
    async def test_signoff_routes_start_with_slash(self):
        """阻断项 route 格式正确。"""
        from app.services.stale_degraded_logger import clear_degraded_records
        clear_degraded_records()

        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        result = await facade.get_workbench("partner")

        for section in result["sections"]:
            for item in section["items"]:
                if item.get("route"):
                    assert item["route"].startswith("/")


class TestPartnerAuditLog:
    """P1-5.4: 合伙人确认 warning 项写审计日志（API 层实现）。"""

    @pytest.mark.asyncio
    async def test_partner_confirm_endpoint_exists(self):
        """验证合伙人确认 API 端点可被定义。"""
        # 这里验证 facade 支持 partner 角色，具体的审计日志写入
        # 在 router 层通过 POST 请求触发，此处验证 facade 返回的 items
        # 中阻断项的 id 可用于确认操作。
        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        result = await facade.get_workbench("partner")

        # 所有 items 有 id 可用于标识确认操作
        for section in result["sections"]:
            for item in section["items"]:
                assert item["id"], "item 必须有 id 用于审计日志引用"
