"""
test_role_workbench_facade_p1.py — P1-1.5/P1-1.6: 真实 Facade 集成测试

验证：
1. auditor/manager/partner 返回区块不同
2. 所有 item 必须包含 route 或 missing_reason

使用 in-process ASGI 测试，模拟真实 DB session。
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

from app.services.role_workbench_facade import (
    RoleWorkbenchFacade,
    ROLE_SECTION_REGISTRY,
    _build_item,
)


# ─── Mock DB Session ──────────────────────────────────────────────────────────

def _make_mock_db():
    """Create a mock AsyncSession that returns empty results for all queries."""
    db = AsyncMock()
    # Default: execute returns empty result
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
    mock_result.scalar.return_value = 0
    mock_result.one.return_value = MagicMock(total=0, completed=0)
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result
    db.get.return_value = None
    return db


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestRoleSectionIsolation:
    """P1-1.5: auditor/manager/partner 返回区块不同。"""

    @pytest.mark.asyncio
    async def test_auditor_sections(self):
        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        result = await facade.get_workbench("auditor")

        section_ids = [s["id"] for s in result["sections"]]
        assert section_ids == ["todo", "review_return", "due_soon", "material_gap", "ai_pending"]

    @pytest.mark.asyncio
    async def test_manager_sections(self):
        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        result = await facade.get_workbench("manager")

        section_ids = [s["id"] for s in result["sections"]]
        assert section_ids == ["completion_rate", "review_aging", "budget_consumption", "personnel_load", "risk_overview"]

    @pytest.mark.asyncio
    async def test_partner_sections(self):
        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        result = await facade.get_workbench("partner")

        section_ids = [s["id"] for s in result["sections"]]
        assert section_ids == ["signoff_blockers", "ai_unconfirmed", "risk_overview", "key_adjustments"]

    @pytest.mark.asyncio
    async def test_different_roles_have_different_sections(self):
        """核心 Property: 三类角色的 section 集合互不相同。"""
        db = _make_mock_db()
        pid = uuid4()
        uid = uuid4()

        results = {}
        for role in ["auditor", "manager", "partner"]:
            facade = RoleWorkbenchFacade(db=db, project_id=pid, user_id=uid)
            result = await facade.get_workbench(role)
            results[role] = set(s["id"] for s in result["sections"])

        # 任意两个角色 section 集合不同
        assert results["auditor"] != results["manager"]
        assert results["auditor"] != results["partner"]
        assert results["manager"] != results["partner"]

    @pytest.mark.asyncio
    async def test_unknown_role_raises(self):
        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        with pytest.raises(ValueError, match="Unknown role"):
            await facade.get_workbench("unknown_role")


class TestItemRoutability:
    """P1-1.6: 所有 item 必须包含 route 或 missing_reason。"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", ["auditor", "manager", "partner"])
    async def test_all_items_have_route_or_missing_reason(self, role: str):
        """核心不变量：每个 item 至少有 route 或 missing_reason。"""
        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        result = await facade.get_workbench(role)

        for section in result["sections"]:
            for item in section["items"]:
                has_route = "route" in item and item["route"]
                has_missing = "missing_reason" in item and item["missing_reason"]
                assert has_route or has_missing, (
                    f"Item '{item.get('id')}' in section '{section['id']}' for role '{role}' "
                    f"has neither route nor missing_reason"
                )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", ["auditor", "manager", "partner"])
    async def test_items_have_required_fields(self, role: str):
        """所有 item 包含 id、label、priority。"""
        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        result = await facade.get_workbench(role)

        for section in result["sections"]:
            for item in section["items"]:
                assert "id" in item
                assert "label" in item
                assert "priority" in item

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", ["auditor", "manager", "partner"])
    async def test_route_format(self, role: str):
        """route 以 / 开头。"""
        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        result = await facade.get_workbench(role)

        for section in result["sections"]:
            for item in section["items"]:
                if "route" in item and item["route"]:
                    assert item["route"].startswith("/"), (
                        f"Route should start with /: {item['route']}"
                    )


class TestWorkbenchStructure:
    """作业台响应结构完整性。"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", ["auditor", "manager", "partner"])
    async def test_top_level_fields(self, role: str):
        db = _make_mock_db()
        pid = uuid4()
        facade = RoleWorkbenchFacade(db=db, project_id=pid, user_id=uuid4())
        result = await facade.get_workbench(role)

        assert result["role"] == role
        assert result["project_id"] == str(pid)
        assert "sections" in result
        assert isinstance(result["sections"], list)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", ["auditor", "manager", "partner"])
    async def test_sections_structure(self, role: str):
        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        result = await facade.get_workbench(role)

        for section in result["sections"]:
            assert "id" in section
            assert "title" in section
            assert "items" in section
            assert isinstance(section["items"], list)
            assert section["id"]  # non-empty


class TestBuildItemHelper:
    """_build_item helper 保证不变量。"""

    def test_route_provided(self):
        item = _build_item("test-1", "测试", route="/foo")
        assert item["route"] == "/foo"
        assert "missing_reason" not in item

    def test_missing_reason_provided(self):
        item = _build_item("test-2", "测试", missing_reason="data_missing")
        assert item["missing_reason"] == "data_missing"
        assert "route" not in item

    def test_neither_provided_fallback(self):
        item = _build_item("test-3", "测试")
        assert item["missing_reason"] == "route_not_available"

    def test_both_provided_route_wins(self):
        item = _build_item("test-4", "测试", route="/bar", missing_reason="x")
        assert item["route"] == "/bar"
        assert "missing_reason" not in item
