"""PBT tests for deliverable-center Task 22: doc_type extensibility, required docs, prior period.

Properties 35, 36, 52 with Hypothesis max_examples=5 (iron rule).
"""

from __future__ import annotations

import string

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.base import ProjectType
from app.models.phase13_models import WordExportDocType
from app.services.deliverable_doc_types import (
    DOC_TYPE_LABELS,
    REQUIRED_BY_PROJECT_TYPE,
    STANDARD_TRIO,
    is_extensible_doc_type,
    register_doc_type,
    required_doc_types,
)
from app.services.report_body_service import ReportBodyService


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy: valid doc_type strings (including known + arbitrary extensions)
_known_doc_types = [e.value for e in WordExportDocType] + ["special_report"]
_extended_doc_types = st.text(
    alphabet=string.ascii_lowercase + "_", min_size=3, max_size=30
).filter(lambda s: s.strip() and not s.startswith("_"))

st_any_doc_type = st.one_of(
    st.sampled_from(_known_doc_types),
    _extended_doc_types,
)

# Strategy: valid project types
st_project_type = st.sampled_from([pt.value for pt in ProjectType])

# Strategy: prior_period_info scenarios
st_prior_period = st.sampled_from([
    "continuing_audit",
    "predecessor_auditor",
    "prior_unaudited",
])

# Strategy: base body for prior period test
st_base_body = st.fixed_dictionaries({
    "sections": st.just([
        {
            "section_id": "opinion",
            "section_name": "审计意见段",
            "section_order": 1,
            "content": "我们审计了...",
            "is_required": True,
        },
        {
            "section_id": "basis",
            "section_name": "形成审计意见的基础段",
            "section_order": 2,
            "content": "审计基础...",
            "is_required": True,
        },
    ])
})


# ---------------------------------------------------------------------------
# Property 35: doc_type 可扩展通用管理
# For any doc_type value (including newly added special report types),
# the deliverable center's listing, versioning, preview, and archival
# generic management operations work without type-specific hardcoded branches.
# ---------------------------------------------------------------------------

@settings(max_examples=5, deadline=None)
@given(doc_type=st_any_doc_type)
def test_property_35_doc_type_extensible_generic_management(doc_type: str):
    """Property 35: doc_type 可扩展通用管理 — 任意 doc_type 均可管理，无硬编码分支。

    **Validates: Requirements 20.1, 20.2**

    For any doc_type value (including novel extensible types), the system:
    1. Accepts it as a valid extensible doc_type (is_extensible_doc_type returns True)
    2. Can be registered dynamically without modifying core logic
    3. Generic operations (label lookup, required_doc_types) do not raise for unknown types
    """
    # 1. Any non-empty trimmed string is a valid extensible doc_type
    assert is_extensible_doc_type(doc_type) is True

    # 2. Dynamic registration works — core logic untouched
    original_labels = dict(DOC_TYPE_LABELS)
    register_doc_type(doc_type, f"测试类型_{doc_type}")
    assert DOC_TYPE_LABELS[doc_type] == f"测试类型_{doc_type}"
    # Restore
    if doc_type not in original_labels:
        del DOC_TYPE_LABELS[doc_type]
    else:
        DOC_TYPE_LABELS[doc_type] = original_labels[doc_type]

    # 3. label lookup gracefully returns the type itself for unknown types
    from app.services.deliverable_doc_types import doc_type_label
    label = doc_type_label(doc_type)
    assert isinstance(label, str) and len(label) > 0

    # 4. required_doc_types does not crash for any project_type (returns default)
    for pt in ProjectType:
        result = required_doc_types(pt.value)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Property 36: 必需件清单由项目类型决定
# For any project type, the completeness check's required doc types list
# equals the configured list for that project type.
# ---------------------------------------------------------------------------

@settings(max_examples=5, deadline=None)
@given(project_type=st_project_type)
def test_property_36_required_doc_types_determined_by_project_type(project_type: str):
    """Property 36: 必需件清单由项目类型决定。

    **Validates: Requirements 20.3, 20.4**

    For any project type:
    1. required_doc_types returns the configured list for that project type
    2. Standard annual/ipo audit returns STANDARD_TRIO
    3. Special/internal_control/capital_verification/tax_audit returns their configured list
    4. The returned list is a fresh copy (mutation-safe)
    """
    result = required_doc_types(project_type)

    # Must match the configured registry
    expected = REQUIRED_BY_PROJECT_TYPE.get(
        project_type, REQUIRED_BY_PROJECT_TYPE[ProjectType.annual.value]
    )
    assert result == expected

    # Standard annual/ipo must include the trio
    if project_type in (ProjectType.annual.value, ProjectType.ipo.value):
        assert set(STANDARD_TRIO).issubset(set(result))

    # Mutation-safe: modifying result doesn't affect registry
    result.append("phantom_type")
    assert "phantom_type" not in required_doc_types(project_type)


# ---------------------------------------------------------------------------
# Property 52: 首次委托其他事项段
# For any prior_period_info in {predecessor_auditor, prior_unaudited},
# the report body contains "其他事项段" with appropriate content.
# For continuing_audit, no other_matter section is added.
# ---------------------------------------------------------------------------

@settings(max_examples=5, deadline=None)
@given(
    prior_period=st_prior_period,
    body=st_base_body,
)
def test_property_52_first_engagement_other_matter_section(
    prior_period: str, body: dict
):
    """Property 52: 首次委托其他事项段。

    **Validates: Requirements 26.2**

    For any prior_period_info scenario:
    - predecessor_auditor → body contains 其他事项段 mentioning "前任注册会计师"
    - prior_unaudited → body contains 其他事项段 mentioning "未经审计"
    - continuing_audit → body does NOT add 其他事项段
    """
    rbs = ReportBodyService(db=None)  # type: ignore[arg-type]
    result = rbs.apply_prior_period_section(body, prior_period)

    section_ids = [s.get("section_id") for s in result.get("sections", [])]
    section_names = [s.get("section_name") for s in result.get("sections", [])]

    if prior_period == "continuing_audit":
        # No other_matter section should be added
        assert "other_matter" not in section_ids
        assert "其他事项段" not in section_names
    elif prior_period == "predecessor_auditor":
        # Must contain other_matter section
        assert "other_matter" in section_ids or "其他事项段" in section_names
        other = next(
            s for s in result["sections"]
            if s.get("section_id") == "other_matter"
        )
        assert "前任注册会计师" in other["content"]
    elif prior_period == "prior_unaudited":
        # Must contain other_matter section
        assert "other_matter" in section_ids or "其他事项段" in section_names
        other = next(
            s for s in result["sections"]
            if s.get("section_id") == "other_matter"
        )
        assert "未经审计" in other["content"]

    # Original body should not be mutated for continuing_audit
    if prior_period == "continuing_audit":
        assert len(result["sections"]) == len(body["sections"])
