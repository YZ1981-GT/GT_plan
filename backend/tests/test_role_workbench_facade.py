"""
test_role_workbench_facade.py — MVP-4: RoleWorkbenchFacade fixture 测试

验证核心 Property：
1. 角色区块隔离性：不同角色返回不同 section IDs
2. 待办可定位性：所有 item 必须包含 route 或 missing_reason

使用 fixture 数据，不依赖真实 DB。

Validates: Requirements 1.1, 2.1, 3.1, 4.1, 5.1
"""
import pytest
from typing import Any


# ─── Fixture Data ─────────────────────────────────────────────────────────────

ROLE_SECTION_REGISTRY: dict[str, list[str]] = {
    "auditor": ["todo", "review_return", "ai_pending", "material_gap", "recent_edit"],
    "manager": ["completion_rate", "review_aging", "budget_consumption", "personnel_load", "risk_overview"],
    "qc": ["quality_score", "qc_rule_hits", "review_aging", "issue_lifecycle"],
    "partner": ["signoff_blockers", "ai_unconfirmed", "risk_overview", "key_judgments"],
    "eqcr": ["key_judgments", "kam", "major_estimates", "going_concern", "related_parties"],
}


def _build_section(section_id: str, items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """构造一个标准 section。"""
    return {
        "id": section_id,
        "title": f"Section: {section_id}",
        "items": items or [],
    }


def _build_item(
    item_id: str,
    label: str,
    route: str | None = None,
    missing_reason: str | None = None,
    priority: str = "normal",
    due_date: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """构造一个标准 item。"""
    item: dict[str, Any] = {
        "id": item_id,
        "label": label,
        "priority": priority,
    }
    if route is not None:
        item["route"] = route
    if missing_reason is not None:
        item["missing_reason"] = missing_reason
    if due_date is not None:
        item["due_date"] = due_date
    if source is not None:
        item["source"] = source
    return item


# ─── Facade Mock ──────────────────────────────────────────────────────────────

class RoleWorkbenchFacade:
    """
    Mock facade that simulates the real role_workbench_facade behavior.
    Production version will aggregate from real services.
    """

    def __init__(self, project_id: str):
        self.project_id = project_id

    def get_workbench(self, role: str) -> dict[str, Any]:
        """按角色返回作业台数据。"""
        if role not in ROLE_SECTION_REGISTRY:
            raise ValueError(f"Unknown role: {role}")

        section_ids = ROLE_SECTION_REGISTRY[role]
        sections = []

        for sid in section_ids:
            items = self._get_fixture_items(role, sid)
            sections.append(_build_section(sid, items))

        return {
            "role": role,
            "project_id": self.project_id,
            "sections": sections,
        }

    def _get_fixture_items(self, role: str, section_id: str) -> list[dict[str, Any]]:
        """Return fixture items for a given role/section."""
        fixtures: dict[str, list[dict[str, Any]]] = {
            "todo": [
                _build_item("todo-1", "D1 底稿待编", route="/projects/proj-001/workpapers/wp-001", priority="high", due_date="2025-12-15", source="review_return"),
                _build_item("todo-2", "E1 货币资金复核", route="/projects/proj-001/workpapers/wp-002", priority="normal", due_date="2025-12-20"),
            ],
            "review_return": [
                _build_item("rr-1", "D2 收入确认被退回", route="/projects/proj-001/reviews/rv-001"),
            ],
            "ai_pending": [
                _build_item("ai-1", "D1 AI 生成内容待确认", route="/projects/proj-001/workpapers/wp-001#ai-content-1"),
            ],
            "material_gap": [
                _build_item("mg-1", "银行询证函未回收", missing_reason="material_not_received"),
            ],
            "recent_edit": [
                _build_item("re-1", "E1 最近编辑", route="/projects/proj-001/workpapers/wp-003"),
            ],
            "completion_rate": [
                _build_item("cr-1", "底稿完成率 75%", route="/projects/proj-001/dashboard#completion"),
            ],
            "review_aging": [
                _build_item("ra-1", "复核超期 3 天", route="/projects/proj-001/reviews/rv-002"),
            ],
            "budget_consumption": [
                _build_item("bc-1", "工时预算消耗 85%", missing_reason="budget_hours_field_missing"),
            ],
            "personnel_load": [
                _build_item("pl-1", "张三负荷 120%", route="/projects/proj-001/workhours#staff-001"),
            ],
            "risk_overview": [
                _build_item("ro-1", "重大风险 2 项", route="/projects/proj-001/risks"),
            ],
            "quality_score": [
                _build_item("qs-1", "质量分 82", route="/projects/proj-001/qc#score"),
            ],
            "qc_rule_hits": [
                _build_item("qr-1", "底稿说明不足 x3", route="/projects/proj-001/qc/rules/r-001"),
            ],
            "issue_lifecycle": [
                _build_item("il-1", "问题 #12 待验证", route="/projects/proj-001/qc/issues/12"),
            ],
            "signoff_blockers": [
                _build_item("sb-1", "stale 数据阻断", route="/projects/proj-001/signoff#stale"),
                _build_item("sb-2", "AI 未确认内容", route="/projects/proj-001/signoff#ai-unconfirmed"),
            ],
            "ai_unconfirmed": [
                _build_item("au-1", "D1 AI 内容未确认", route="/projects/proj-001/workpapers/wp-001#ai-content-1"),
            ],
            "key_judgments": [
                _build_item("kj-1", "重大估计判断", route="/projects/proj-001/eqcr/judgments/j-001"),
            ],
            "kam": [
                _build_item("kam-1", "关键审计事项: 收入确认", route="/projects/proj-001/eqcr/kam/001"),
            ],
            "major_estimates": [
                _build_item("me-1", "坏账准备估计", route="/projects/proj-001/eqcr/estimates/001"),
            ],
            "going_concern": [
                _build_item("gc-1", "持续经营评估", route="/projects/proj-001/eqcr/going-concern"),
            ],
            "related_parties": [
                _build_item("rp-1", "关联方交易审查", route="/projects/proj-001/eqcr/related-parties"),
            ],
        }
        return fixtures.get(section_id, [])


# ─── Tests ────────────────────────────────────────────────────────────────────

@pytest.fixture
def facade() -> RoleWorkbenchFacade:
    return RoleWorkbenchFacade(project_id="proj-001")


class TestRoleSectionIsolation:
    """角色区块隔离性：不同角色返回不同 section IDs。"""

    def test_auditor_sections(self, facade: RoleWorkbenchFacade):
        result = facade.get_workbench("auditor")
        section_ids = [s["id"] for s in result["sections"]]
        assert section_ids == ["todo", "review_return", "ai_pending", "material_gap", "recent_edit"]

    def test_manager_sections(self, facade: RoleWorkbenchFacade):
        result = facade.get_workbench("manager")
        section_ids = [s["id"] for s in result["sections"]]
        assert section_ids == ["completion_rate", "review_aging", "budget_consumption", "personnel_load", "risk_overview"]

    def test_qc_sections(self, facade: RoleWorkbenchFacade):
        result = facade.get_workbench("qc")
        section_ids = [s["id"] for s in result["sections"]]
        assert section_ids == ["quality_score", "qc_rule_hits", "review_aging", "issue_lifecycle"]

    def test_partner_sections(self, facade: RoleWorkbenchFacade):
        result = facade.get_workbench("partner")
        section_ids = [s["id"] for s in result["sections"]]
        assert section_ids == ["signoff_blockers", "ai_unconfirmed", "risk_overview", "key_judgments"]

    def test_eqcr_sections(self, facade: RoleWorkbenchFacade):
        result = facade.get_workbench("eqcr")
        section_ids = [s["id"] for s in result["sections"]]
        assert section_ids == ["key_judgments", "kam", "major_estimates", "going_concern", "related_parties"]

    def test_different_roles_have_different_sections(self, facade: RoleWorkbenchFacade):
        """核心 Property: 任意两个不同角色的 section 集合不完全相同。"""
        roles = list(ROLE_SECTION_REGISTRY.keys())
        for i, role_a in enumerate(roles):
            for role_b in roles[i + 1:]:
                sections_a = set(s["id"] for s in facade.get_workbench(role_a)["sections"])
                sections_b = set(s["id"] for s in facade.get_workbench(role_b)["sections"])
                assert sections_a != sections_b, f"{role_a} and {role_b} should have different sections"

    def test_unknown_role_raises(self, facade: RoleWorkbenchFacade):
        with pytest.raises(ValueError, match="Unknown role"):
            facade.get_workbench("unknown_role")


class TestItemRoutability:
    """待办可定位性：所有 item 必须包含 route 或 missing_reason。"""

    @pytest.mark.parametrize("role", list(ROLE_SECTION_REGISTRY.keys()))
    def test_all_items_have_route_or_missing_reason(self, facade: RoleWorkbenchFacade, role: str):
        """核心 Property: 每个 item 必须有 route 或 missing_reason，确保可定位。"""
        result = facade.get_workbench(role)
        for section in result["sections"]:
            for item in section["items"]:
                has_route = "route" in item and item["route"]
                has_missing_reason = "missing_reason" in item and item["missing_reason"]
                assert has_route or has_missing_reason, (
                    f"Item {item['id']} in section {section['id']} for role {role} "
                    f"has neither route nor missing_reason"
                )

    @pytest.mark.parametrize("role", list(ROLE_SECTION_REGISTRY.keys()))
    def test_items_have_required_fields(self, facade: RoleWorkbenchFacade, role: str):
        """所有 item 必须包含 id、label、priority 基础字段。"""
        result = facade.get_workbench(role)
        for section in result["sections"]:
            for item in section["items"]:
                assert "id" in item, f"Item missing 'id' in {section['id']}"
                assert "label" in item, f"Item missing 'label' in {section['id']}"
                assert "priority" in item, f"Item missing 'priority' in {section['id']}"

    def test_route_format_valid(self, facade: RoleWorkbenchFacade):
        """route 必须以 / 开头（相对路径格式）。"""
        for role in ROLE_SECTION_REGISTRY:
            result = facade.get_workbench(role)
            for section in result["sections"]:
                for item in section["items"]:
                    if "route" in item and item["route"]:
                        assert item["route"].startswith("/"), (
                            f"Item {item['id']} route should start with /, got: {item['route']}"
                        )


class TestWorkbenchStructure:
    """作业台结构完整性。"""

    @pytest.mark.parametrize("role", list(ROLE_SECTION_REGISTRY.keys()))
    def test_response_has_required_top_level_fields(self, facade: RoleWorkbenchFacade, role: str):
        result = facade.get_workbench(role)
        assert "role" in result
        assert "project_id" in result
        assert "sections" in result
        assert result["role"] == role
        assert result["project_id"] == "proj-001"

    @pytest.mark.parametrize("role", list(ROLE_SECTION_REGISTRY.keys()))
    def test_sections_have_required_fields(self, facade: RoleWorkbenchFacade, role: str):
        result = facade.get_workbench(role)
        for section in result["sections"]:
            assert "id" in section
            assert "title" in section
            assert "items" in section
            assert isinstance(section["items"], list)

    def test_no_empty_section_ids(self, facade: RoleWorkbenchFacade):
        """section id 不能为空字符串。"""
        for role in ROLE_SECTION_REGISTRY:
            result = facade.get_workbench(role)
            for section in result["sections"]:
                assert section["id"], f"Empty section id found for role {role}"
