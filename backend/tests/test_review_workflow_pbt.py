"""复核流程 PBT: 角色→模板匹配

Task 2.6: 验证任意角色+审计类型组合都能匹配到正确模板（或 None）

适用性以业务分类参考标准 ``business_category_reference.json`` 为单一来源（与底稿清单同一判定）：质量复核合伙人 A24-1 /
EQCR A25-1 在 A、B 类适用、C 类排除（参考标准「B 类需项目质量复核合伙人（A24/A25 保留）」）。模板文件原有的 ``a_only``
与之矛盾（B 类拿不到模板）已删除（spec formula-fetch-followup-defect-closure R8）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.business_category_service import is_template_applicable
from app.services.review_workflow_service import ReviewWorkflowService, _load_templates

ROLES = ["field_lead", "manager", "partner", "quality_reviewer", "eqcr"]
AUDIT_TYPES = ["financial", "internal_control"]
CATEGORIES = ["A", "B", "C"]


@settings(max_examples=5)
@given(
    role=st.sampled_from(ROLES),
    audit_type=st.sampled_from(AUDIT_TYPES),
    category=st.sampled_from(CATEGORIES),
)
def test_role_template_matching_deterministic(role: str, audit_type: str, category: str):
    """每个角色+类型组合匹配结果确定且模板角色正确"""
    db = AsyncMock()
    svc = ReviewWorkflowService(db)
    tmpl = svc._get_template_for_role(role, audit_type, category)

    if tmpl is not None:
        # 匹配到的模板角色必须与请求角色一致
        assert tmpl["role"] == role
        # 审计类型一致
        assert tmpl["audit_type"] == audit_type
        # 适用性与参考标准一致
        assert is_template_applicable({"wp_code": tmpl["code"]}, category)


@settings(max_examples=5)
@given(
    role=st.sampled_from(ROLES),
    audit_type=st.sampled_from(AUDIT_TYPES),
)
def test_a_category_always_matches(role: str, audit_type: str):
    """A类项目所有角色都能匹配到模板"""
    db = AsyncMock()
    svc = ReviewWorkflowService(db)
    tmpl = svc._get_template_for_role(role, audit_type, "A")

    # 对于 financial，所有角色都有模板
    if audit_type == "financial":
        assert tmpl is not None, f"A类 financial {role} 应有模板"


def test_quality_review_templates_follow_reference_standard():
    """质量复核合伙人 / EQCR：A、B 类（含子分类）有模板，C 类没有 —— 期望值为字面量（参考标准原文）。"""
    svc = ReviewWorkflowService(AsyncMock())
    expected = {"quality_reviewer": "A24-1", "eqcr": "A25-1"}
    for role, code in expected.items():
        for category in ("A", "A3", "B", "B1"):
            tmpl = svc._get_template_for_role(role, "financial", category)
            assert tmpl is not None and tmpl["code"] == code, f"{category} 类 {role} 应取 {code}"
        for category in ("C", ""):
            assert svc._get_template_for_role(role, "financial", category) is None, f"{category or '未设'} 类 {role} 不应有模板"


def test_template_config_integrity():
    """模板配置完整性：每个模板都有必要字段"""
    data = _load_templates()
    for code, tmpl in data["templates"].items():
        assert "title" in tmpl, f"{code} missing title"
        assert "code" in tmpl, f"{code} missing code"
        assert "role" in tmpl, f"{code} missing role"
        assert "audit_type" in tmpl, f"{code} missing audit_type"
        assert "items" in tmpl, f"{code} missing items"
        assert len(tmpl["items"]) > 0, f"{code} has no items"
        for item in tmpl["items"]:
            assert "seq" in item
            assert "content" in item


def test_templates_carry_no_second_applicability_source():
    """模板文件不再自带适用性标注（原 a_only 与参考标准矛盾）；三级复核模板在所有分类都适用。"""
    data = _load_templates()
    assert not [code for code, t in data["templates"].items() if "a_only" in t]
    assert not [r for r, meta in data.get("roles", {}).items() if "a_only" in meta]
    svc = ReviewWorkflowService(AsyncMock())
    for role in ("field_lead", "manager", "partner"):
        for category in ("A3", "B1", "C"):
            assert svc._get_template_for_role(role, "financial", category) is not None, (role, category)
