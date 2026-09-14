"""
项目显示名称工具函数（后端版）

根据 report_scope 和同企业同年度项目共存情况，为项目名追加后缀。

规则（Property 9）：
- consolidated → 追加"（合并）"
- standalone 且同 company_code+audit_year 下存在非删除的 consolidated 项目 → 追加"（母公司）"
- 其它 → 无后缀
"""

from typing import Any


def get_project_display_name(project: dict[str, Any], all_projects: list[dict[str, Any]]) -> str:
    """
    获取项目显示名称（含后缀）。

    Args:
        project: 当前项目字典，需包含 name/client_name/company_code/audit_year/report_scope 字段
        all_projects: 全部项目列表（用于判断母公司后缀）

    Returns:
        带后缀的项目显示名称
    """
    base_name = project.get("name") or project.get("client_name") or ""

    report_scope = project.get("report_scope")

    if report_scope == "consolidated":
        return base_name + "（合并）"

    if report_scope == "standalone":
        company_code = project.get("company_code")
        audit_year = project.get("audit_year")

        if company_code is not None and audit_year is not None:
            has_consolidated = any(
                p is not project
                and not p.get("is_deleted", False)
                and p.get("report_scope") == "consolidated"
                and p.get("company_code") == company_code
                and p.get("audit_year") == audit_year
                for p in all_projects
            )
            if has_consolidated:
                return base_name + "（母公司）"

    return base_name
