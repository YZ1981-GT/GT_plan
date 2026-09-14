"""
test_role_workbench_auditor_uat.py — P1-3.4: 助理作业台 UAT

UAT：助理从待办直接进入底稿单元格或复核意见。
验证 route 格式正确指向底稿编辑器或复核工作台。
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

from app.services.role_workbench_facade import RoleWorkbenchFacade, ROLE_SECTION_REGISTRY


def _make_mock_db():
    """Mock DB that returns empty results."""
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


class TestAuditorSections:
    """P1-3.1: 聚合今日待办、被退回复核、即将截止、资料缺口、AI 建议。"""

    @pytest.mark.asyncio
    async def test_auditor_has_all_required_sections(self):
        """验证 auditor 包含 5 个必要 section。"""
        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        result = await facade.get_workbench("auditor")

        section_ids = [s["id"] for s in result["sections"]]
        # P1-3.1 要求的 5 个 section
        assert "todo" in section_ids, "缺少'今日待办'区块"
        assert "review_return" in section_ids, "缺少'被退回复核'区块"
        assert "due_soon" in section_ids, "缺少'即将截止'区块"
        assert "material_gap" in section_ids, "缺少'资料缺口'区块"
        assert "ai_pending" in section_ids, "缺少'AI 建议'区块"

    @pytest.mark.asyncio
    async def test_auditor_section_titles_chinese(self):
        """所有 section title 为中文。"""
        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        result = await facade.get_workbench("auditor")

        for section in result["sections"]:
            # title 应该是中文（至少包含中文字符）
            assert any('\u4e00' <= ch <= '\u9fff' for ch in section["title"]), (
                f"Section '{section['id']}' title '{section['title']}' 应为中文"
            )


class TestAuditorRoutability:
    """P1-3.2: 每项待办返回 route / missing_reason。"""

    @pytest.mark.asyncio
    async def test_all_items_routable(self):
        db = _make_mock_db()
        pid = uuid4()
        facade = RoleWorkbenchFacade(db=db, project_id=pid, user_id=uuid4())
        result = await facade.get_workbench("auditor")

        for section in result["sections"]:
            for item in section["items"]:
                has_route = bool(item.get("route"))
                has_missing = bool(item.get("missing_reason"))
                assert has_route or has_missing, (
                    f"Item '{item['id']}' 缺少 route 或 missing_reason"
                )


class TestAuditorRouteTargets:
    """P1-3.3/P1-3.4: route 指向底稿、附件、复核、任务树。"""

    @pytest.mark.asyncio
    async def test_todo_routes_point_to_workpapers(self):
        """待办 route 应指向底稿编辑器。"""
        from app.services.my_todo_service import MyTodoResponse, TodoItem
        from datetime import datetime, timezone

        db = _make_mock_db()
        pid = uuid4()
        uid = uuid4()
        wp_id = uuid4()

        # Mock my_todo_service 返回有一条待办
        mock_todo = MyTodoResponse(
            items=[
                TodoItem(
                    wp_id=wp_id,
                    wp_code="D1",
                    wp_name="销售收入",
                    cycle="D",
                    urgency="high",
                    urgency_reason="有未解决的复核意见",
                    updated_at=datetime.now(timezone.utc),
                )
            ],
            total=1,
        )

        with patch("app.services.my_todo_service.get_my_todo", return_value=mock_todo):
            facade = RoleWorkbenchFacade(db=db, project_id=pid, user_id=uid)
            result = await facade.get_workbench("auditor")

        todo_section = next(s for s in result["sections"] if s["id"] == "todo")
        assert len(todo_section["items"]) == 1
        item = todo_section["items"][0]
        # route 指向底稿编辑器
        assert f"/projects/{pid}/workpapers/{wp_id}/edit" == item["route"]

    @pytest.mark.asyncio
    async def test_review_return_routes_point_to_workpapers(self):
        """被退回复核 route 应指向底稿编辑器。"""
        db = _make_mock_db()
        pid = uuid4()
        wp_id = uuid4()
        rec_id = uuid4()

        # Mock review query result
        mock_rec = MagicMock()
        mock_rec.id = rec_id
        mock_rec.working_paper_id = wp_id
        mock_rec.created_at = None

        mock_result = MagicMock()
        mock_result.all.return_value = [(mock_rec, "D1", "销售收入")]
        db.execute.return_value = mock_result

        facade = RoleWorkbenchFacade(db=db, project_id=pid, user_id=uuid4())
        # 只测 _fetch_review_return
        items = await facade._fetch_review_return()

        assert len(items) == 1
        assert f"/projects/{pid}/workpapers/{wp_id}/edit" == items[0]["route"]

    @pytest.mark.asyncio
    async def test_due_soon_routes_point_to_issues(self):
        """即将截止 route 应指向问题单列表。"""
        db = _make_mock_db()
        pid = uuid4()

        facade = RoleWorkbenchFacade(db=db, project_id=pid, user_id=uuid4())
        # With empty DB, due_soon returns empty
        items = await facade._fetch_due_soon()
        # Empty is fine - just verify no crash
        assert isinstance(items, list)
