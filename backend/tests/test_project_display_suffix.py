"""
Property 9: 项目显示后缀规则 PBT 测试

For any project, the display name suffix function SHALL:
- append "（合并）" if report_scope=consolidated
- append "（母公司）" if report_scope=standalone AND a non-deleted consolidated project
  exists with the same company_code and audit_year
- append nothing otherwise

**Validates: Requirements 4.1, 4.2, 4.3, 4.5**
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.project_display import get_project_display_name

# --- Strategies ---

USCC_CHARSET = "0123456789ABCDEFGHJKLMNPQRTUWXY"

project_name_st = st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L", "N")))
company_code_st = st.text(alphabet=USCC_CHARSET, min_size=18, max_size=18)
audit_year_st = st.integers(min_value=2020, max_value=2030)
report_scope_st = st.sampled_from(["standalone", "consolidated"])


def make_project(
    name: str = "测试项目",
    company_code: str = "91110000MA001ABCX1",
    audit_year: int = 2025,
    report_scope: str = "standalone",
    is_deleted: bool = False,
) -> dict:
    return {
        "name": name,
        "client_name": None,
        "company_code": company_code,
        "audit_year": audit_year,
        "report_scope": report_scope,
        "is_deleted": is_deleted,
    }


# --- Property-Based Test ---


# Feature: project-creation-enhancement, Property 9: 项目显示后缀规则
@given(
    name=project_name_st,
    company_code=company_code_st,
    audit_year=audit_year_st,
    report_scope=report_scope_st,
    has_consolidated_peer=st.booleans(),
    peer_deleted=st.booleans(),
)
@settings(max_examples=5)
def test_property9_display_suffix_rules(
    name: str,
    company_code: str,
    audit_year: int,
    report_scope: str,
    has_consolidated_peer: bool,
    peer_deleted: bool,
):
    """
    **Validates: Requirements 4.1, 4.2, 4.3, 4.5**

    Property 9: For any project, verify suffix rules are correctly applied.
    """
    project = make_project(
        name=name,
        company_code=company_code,
        audit_year=audit_year,
        report_scope=report_scope,
    )

    # Build the all_projects list with optional consolidated peer
    all_projects = [project]
    if has_consolidated_peer:
        peer = make_project(
            name="合并项目",
            company_code=company_code,
            audit_year=audit_year,
            report_scope="consolidated",
            is_deleted=peer_deleted,
        )
        all_projects.append(peer)

    result = get_project_display_name(project, all_projects)

    # Verify suffix rules
    if report_scope == "consolidated":
        assert result == name + "（合并）", f"consolidated project should get '（合并）' suffix, got: {result}"
    elif report_scope == "standalone":
        if has_consolidated_peer and not peer_deleted:
            assert result == name + "（母公司）", f"parent standalone should get '（母公司）' suffix, got: {result}"
        else:
            assert result == name, f"regular standalone should have no suffix, got: {result}"
    else:
        assert result == name, f"unknown scope should have no suffix, got: {result}"


# --- Unit Tests ---


class TestConsolidatedSuffix:
    """合并项目 → 追加"（合并）" """

    def test_consolidated_gets_suffix(self):
        project = make_project(report_scope="consolidated")
        result = get_project_display_name(project, [project])
        assert result == "测试项目（合并）"

    def test_consolidated_suffix_regardless_of_peers(self):
        """合并项目始终追加后缀，不管有没有同期 standalone"""
        project = make_project(report_scope="consolidated")
        peer = make_project(report_scope="standalone")
        result = get_project_display_name(project, [project, peer])
        assert result == "测试项目（合并）"


class TestParentStandaloneSuffix:
    """standalone + 同企业同年度存在非删除 consolidated → 追加"（母公司）" """

    def test_parent_standalone_gets_suffix(self):
        standalone = make_project(report_scope="standalone")
        consolidated = make_project(report_scope="consolidated")
        result = get_project_display_name(standalone, [standalone, consolidated])
        assert result == "测试项目（母公司）"

    def test_parent_standalone_peer_deleted_no_suffix(self):
        """同期 consolidated 已删除 → standalone 不追加后缀"""
        standalone = make_project(report_scope="standalone")
        consolidated = make_project(report_scope="consolidated", is_deleted=True)
        result = get_project_display_name(standalone, [standalone, consolidated])
        assert result == "测试项目"

    def test_different_company_code_no_suffix(self):
        """不同 company_code 的 consolidated 不影响"""
        standalone = make_project(company_code="91110000MA001ABCX1", report_scope="standalone")
        consolidated = make_project(company_code="91110000MA002DEFX2", report_scope="consolidated")
        result = get_project_display_name(standalone, [standalone, consolidated])
        assert result == "测试项目"

    def test_different_audit_year_no_suffix(self):
        """不同 audit_year 的 consolidated 不影响"""
        standalone = make_project(audit_year=2024, report_scope="standalone")
        consolidated = make_project(audit_year=2025, report_scope="consolidated")
        result = get_project_display_name(standalone, [standalone, consolidated])
        assert result == "测试项目"


class TestRegularStandaloneNoSuffix:
    """普通 standalone（无同期 consolidated）→ 无后缀"""

    def test_standalone_alone_no_suffix(self):
        project = make_project(report_scope="standalone")
        result = get_project_display_name(project, [project])
        assert result == "测试项目"

    def test_no_report_scope_no_suffix(self):
        """report_scope 为空 → 无后缀"""
        project = make_project()
        project["report_scope"] = None
        result = get_project_display_name(project, [project])
        assert result == "测试项目"


class TestFallbackName:
    """名称回退逻辑"""

    def test_uses_client_name_when_name_empty(self):
        project = {"name": None, "client_name": "客户公司", "company_code": "X", "audit_year": 2025, "report_scope": "consolidated", "is_deleted": False}
        result = get_project_display_name(project, [project])
        assert result == "客户公司（合并）"

    def test_empty_when_both_names_missing(self):
        project = {"name": None, "client_name": None, "company_code": "X", "audit_year": 2025, "report_scope": "consolidated", "is_deleted": False}
        result = get_project_display_name(project, [project])
        assert result == "（合并）"
