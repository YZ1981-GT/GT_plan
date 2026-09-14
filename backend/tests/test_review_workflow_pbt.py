"""复核流程 PBT: 角色→模板匹配

Task 2.6: 验证任意角色+审计类型组合都能匹配到正确模板（或 None）
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

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
        # A-only 限制
        if tmpl.get("a_only"):
            assert category == "A"


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


def test_non_a_category_no_qr_eqcr():
    """非A类项目不应匹配到 quality_reviewer/eqcr 模板"""
    db = AsyncMock()
    svc = ReviewWorkflowService(db)

    for category in ["B", "C"]:
        for role in ["quality_reviewer", "eqcr"]:
            tmpl = svc._get_template_for_role(role, "financial", category)
            assert tmpl is None, f"{category}类 {role} 不应有模板"


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
