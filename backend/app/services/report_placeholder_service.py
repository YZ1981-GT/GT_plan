"""报告占位符替换服务

功能：
- get_placeholders: 从 project.wizard_state.basic_info 构建占位符映射
- replace_in_text: 替换文本中的占位符
- apply_scope_replacements: 根据报表口径替换文本
"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project

logger = logging.getLogger(__name__)

# 事务所信息：平台常量默认（无租户级配置时的模板内容）。
FIRM_NAME_DEFAULT = "致同会计师事务所（特殊普通合伙）"
FIRM_ADDRESS_DEFAULT = "中国·北京"

# 需人工录入且无自动数据源时的模板占位（用 [] 包裹，供 detect_missing_fields 识别为待补充，
# 但不阻断生成——生成后审计师在 Word 中直接改）。
_MANUAL_PLACEHOLDERS = {
    "signing_partner": "[签字合伙人]",
    "cpa_name_1": "[签字注册会计师]",
    "cpa_name_2": "[签字注册会计师]",
    "report_date": "[报告日期]",
    "report_number": "[报告文号]",
}


# ---------------------------------------------------------------------------
# 报表口径替换字典（design.md §4.2）
# ---------------------------------------------------------------------------

SCOPE_REPLACEMENTS: dict[str, dict[str, str]] = {
    "consolidated": {
        "财务报表": "合并及母公司财务报表",
        "资产负债表": "合并及母公司资产负债表",
        "利润表": "合并及母公司利润表",
        "现金流量表": "合并及母公司现金流量表",
        "所有者权益变动表": "合并及母公司所有者权益变动表",
        "财务报表附注": "合并及母公司财务报表附注",
    },
    "standalone": {
        # 单体报表不需要替换，保持原文
    },
}


class ReportPlaceholderService:
    """报告占位符替换服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_placeholders(self, project_id: UUID) -> dict[str, str]:
        """构建占位符映射。

        取数优先级（"能从项目模块拿就拿，拿不到用模板默认内容"）：
        1. 项目向导 basic_info（创建/编辑项目时填的）
        2. projects 表专属字段（audit_period_start/end、partner_id、audit_year）
        3. audit_report 表（report_date、signing_partner —— 报告编制时填的）
        4. 派生（prior_year = audit_year - 1）/ 事务所常量 / 模板占位
        """
        result = await self.db.execute(
            sa.select(Project).where(
                Project.id == project_id,
                Project.is_deleted == sa.false(),
            )
        )
        project = result.scalar_one_or_none()

        basic_info: dict = {}
        if project and project.wizard_state:
            state = project.wizard_state
            basic_info = (
                state.get("steps", {}).get("basic_info", {}).get("data")
                or state.get("basic_info", {}).get("data")
                or {}
            )

        entity_name = basic_info.get("client_name") or (project.client_name if project else "[被审计单位名称]")
        entity_short_name = basic_info.get("entity_short_name") or basic_info.get("short_name") or ""
        report_scope = basic_info.get("report_scope") or (project.report_scope if project else "standalone") or "standalone"

        # --- 审计年度（项目模块创建时选定，派生上年）------------------------
        audit_year_raw = basic_info.get("audit_year") or (getattr(project, "audit_year", None) if project else None)
        audit_year = str(audit_year_raw) if audit_year_raw else ""
        prior_year = str(int(audit_year_raw) - 1) if str(audit_year_raw).isdigit() else ""

        # --- 审计期间：projects 表字段有值用值，否则按年度推导（年审口径）-----
        audit_period, audit_period_start = self._resolve_audit_period(basic_info, project, audit_year)

        # --- 报告编制字段：优先 audit_report 表，回退 basic_info -------------
        report_row = await self._load_report_row(project_id, audit_year_raw)

        signing_partner = (
            basic_info.get("signing_partner_name")
            or (report_row.get("signing_partner") if report_row else None)
            or await self._resolve_partner_name(project)
            or _MANUAL_PLACEHOLDERS["signing_partner"]
        )
        report_date = (
            basic_info.get("report_date")
            or (report_row.get("report_date") if report_row else None)
            or _MANUAL_PLACEHOLDERS["report_date"]
        )

        return {
            "entity_name": entity_name,
            "entity_short_name": entity_short_name if entity_short_name else f'"{entity_name}"',
            "report_scope": "合并及母公司" if report_scope == "consolidated" else "",
            "audit_period": audit_period,
            "audit_period_start": audit_period_start,
            "audit_year": audit_year or "[审计年度]",
            "prior_year": prior_year or "[上年度]",
            "signing_partner": signing_partner,
            "report_date": str(report_date),
            "report_number": basic_info.get("report_number") or _MANUAL_PLACEHOLDERS["report_number"],
            "firm_name": basic_info.get("firm_name") or FIRM_NAME_DEFAULT,
            "firm_address": basic_info.get("firm_address") or FIRM_ADDRESS_DEFAULT,
            "cpa_name_1": basic_info.get("cpa_name_1") or _MANUAL_PLACEHOLDERS["cpa_name_1"],
            "cpa_name_2": basic_info.get("cpa_name_2") or _MANUAL_PLACEHOLDERS["cpa_name_2"],
            "responsibility_organ": self._resolve_responsibility_organ(basic_info, project),
        }

    @staticmethod
    def _resolve_audit_period(basic_info: dict, project, audit_year: str) -> tuple[str, str]:
        """返回 (审计期间末日文本, 期间起始日文本)。

        projects.audit_period_start/end 有值用值；否则按年审口径由年度推导
        （起始={year}-01-01，末日={year}年12月31日）。期中/首年项目请在项目模块补填
        期间字段，此处不臆造非年审区间。
        """
        def _fmt(d) -> str:
            return d.isoformat() if d is not None else ""

        start = _fmt(getattr(project, "audit_period_start", None) if project else None)
        end_d = getattr(project, "audit_period_end", None) if project else None
        if end_d is not None:
            period = f"{end_d.year}年{end_d.month}月{end_d.day}日"
        elif audit_year:
            period = f"{audit_year}年12月31日"
        else:
            period = "[审计期间]"
        if not start and audit_year:
            start = f"{audit_year}-01-01"
        return period, (start or "[审计期间起始]")

    async def _load_report_row(self, project_id: UUID, audit_year_raw) -> dict | None:
        """读 audit_report 表的报告编制字段（report_date / signing_partner）。"""
        try:
            params: dict = {"pid": str(project_id)}
            where = "project_id = :pid AND is_deleted = false"
            if audit_year_raw:
                where += " AND year = :yr"
                params["yr"] = int(audit_year_raw)
            stmt = sa.text(
                "SELECT report_date, signing_partner FROM audit_report "
                f"WHERE {where} ORDER BY year DESC LIMIT 1"
            )
            res = await self.db.execute(stmt, params)
            row = res.mappings().first()
            return dict(row) if row else None
        except Exception as exc:  # fail-open：报告表不可用不阻断占位构建
            logger.warning("load audit_report row failed: %s", exc)
            return None

    async def _resolve_partner_name(self, project) -> str | None:
        """项目模块兜底签字合伙人：projects.partner_id / project_assignments(partner)。"""
        if project is None:
            return None
        try:
            partner_id = getattr(project, "partner_id", None)
            if partner_id:
                res = await self.db.execute(
                    sa.text(
                        "SELECT COALESCE(partner_name, name) AS nm FROM staff_members "
                        "WHERE user_id = :uid AND is_deleted = false LIMIT 1"
                    ),
                    {"uid": str(partner_id)},
                )
                nm = res.scalar_one_or_none()
                if nm:
                    return str(nm)
            res = await self.db.execute(
                sa.text(
                    "SELECT COALESCE(s.partner_name, s.name) AS nm "
                    "FROM project_assignments pa JOIN staff_members s ON s.id = pa.staff_id "
                    "WHERE pa.project_id = :pid AND pa.is_deleted = false "
                    "AND pa.role = 'partner' LIMIT 1"
                ),
                {"pid": str(project.id)},
            )
            nm = res.scalar_one_or_none()
            return str(nm) if nm else None
        except Exception as exc:  # fail-open
            logger.warning("resolve partner name failed: %s", exc)
            return None

    @staticmethod
    def _resolve_responsibility_organ(basic_info: dict, project) -> str:
        """根据企业子类型推导治理层抬头（董事会/全体股东）。

        - 上市/三板/非公众（type_a/b/d）→ "全体股东"
        - 其他公众利益（type_c）→ "董事会"
        - 用户手动指定时优先
        """
        organ = basic_info.get("responsibility_organ")
        if organ:
            return organ
        subtype = basic_info.get("company_subtype") or (getattr(project, "company_subtype", None) if project else None) or ""
        if subtype in ("type_c",):
            return "董事会"
        return "全体股东"

    @staticmethod
    def replace_in_text(text: str, placeholders: dict[str, str]) -> str:
        """替换文本中的 {xxx} 占位符"""
        result = text
        for key, value in placeholders.items():
            result = result.replace(f"{{{key}}}", value)
        return result

    @staticmethod
    def apply_scope_replacements(text: str, report_scope: str) -> str:
        """根据报表口径替换文本

        consolidated → "财务报表" 替换为 "合并及母公司财务报表" 等
        standalone → 不替换
        """
        replacements = SCOPE_REPLACEMENTS.get(report_scope, {})
        result = text
        for old, new in replacements.items():
            result = result.replace(old, new)
        return result
