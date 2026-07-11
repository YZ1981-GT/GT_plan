"""Table / JOIN / Operator / Aggregate 白名单单一真源 + 强制登记 + 敏感表排除

Task 6.2（advanced-query-module）：把原先散落在 ``routers/query_builder.py`` 的
四组白名单（``TABLE_WHITELIST`` / ``JOIN_WHITELIST`` / ``OPERATOR_WHITELIST`` /
``AGGREGATE_WHITELIST``）**迁移/收敛到服务层单点**，供 ``ParamSQLBuilder`` /
``QueryOrchestrator`` 与白名单构建器在**执行前**统一强制。

设计要点（design.md §Components 8 ParamSQLBuilder / §Error Handling）：

- 只读 audit/财务表白名单；**显式排除 user / role / auth / token 相关敏感表**，
  不允许经任何登记路径纳入白名单（导入时以 ``_assert_no_sensitive_in_whitelist``
  做不变式校验，一旦有人误加敏感表即启动失败）（R10.6）。
- 未登记的表 / JOIN / 操作符 / 聚合 → **执行前拒绝、指明具体对象、不部分执行**，
  统一 error_code ``NOT_WHITELISTED``（HTTP 400）（R10.4 / R10.5）。
- 运行时查询计划若引用敏感表 → **无条件拒绝**，error_code
  ``SENSITIVE_TABLE_DENIED``（HTTP 400），且优先于登记校验（R10.7）。

本模块**不做**值 → 参数化谓词的绑定（那是 ``param_sql_builder`` 的职责），只负责
「对象是否被允许」这一层的安全门禁。``query_builder`` 从本模块导入定义，实现单点。

Validates: Requirements 10.4, 10.5, 10.6, 10.7
"""

from __future__ import annotations

from typing import Any, Iterable

from fastapi import HTTPException

from app.models.audit_platform_models import (
    AccountChart,
    Adjustment,
    Materiality,
    ReportLineMapping,
    TbBalance,
    TbLedger,
    TrialBalance,
    UnadjustedMisstatement,
)
from app.models.core import Project
from app.models.report_models import DisclosureNote, ReportConfig
from app.models.staff_models import StaffMember, WorkHour
from app.models.workpaper_models import WorkingPaper, WpIndex

# ─────────────────────────────────────────────────────────────────────────────
# 表白名单（只读 audit/财务表，绝不暴露 user/role/auth/token 表）
# ─────────────────────────────────────────────────────────────────────────────
TABLE_WHITELIST: dict[str, dict[str, Any]] = {
    "trial_balance": {
        "model": TrialBalance,
        "label": "试算表",
        "fields": [
            "id", "project_id", "year", "company_code",
            "standard_account_code", "account_name", "account_category",
            "unadjusted_amount", "rje_adjustment", "aje_adjustment",
            "audited_amount", "opening_balance", "currency_code",
            "is_deleted", "created_at", "updated_at",
        ],
    },
    "adjustments": {
        "model": Adjustment,
        "label": "调整分录（AJE/RJE）",
        "fields": [
            "id", "project_id", "year", "company_code", "adjustment_no",
            "adjustment_type", "description", "account_code", "account_name",
            "debit_amount", "credit_amount", "review_status",
            "is_deleted", "created_at", "updated_at",
        ],
    },
    "unadjusted_misstatements": {
        "model": UnadjustedMisstatement,
        "label": "未更正错报",
        "fields": [
            "id", "project_id", "year", "misstatement_description",
            "affected_account_code", "affected_account_name",
            "misstatement_amount", "misstatement_type",
            "management_reason", "auditor_evaluation",
            "is_deleted", "created_at", "updated_at",
        ],
    },
    "report_line_mapping": {
        "model": ReportLineMapping,
        "label": "报表行次映射",
        "fields": [
            "id", "project_id", "report_type",
            "standard_account_code", "report_line_code", "report_line_name",
            "report_line_level", "parent_line_code", "mapping_type",
            "is_confirmed", "is_deleted", "created_at", "updated_at",
        ],
    },
    "report_config": {
        "model": ReportConfig,
        "label": "报表行次配置",
        "fields": [
            "id", "report_type", "applicable_standard",
            "row_code", "row_name", "row_number", "indent_level",
            "is_total_row", "parent_row_code", "formula",
            "formula_category", "formula_description", "formula_source",
            "is_deleted", "created_at", "updated_at",
        ],
    },
    "working_paper": {
        "model": WorkingPaper,
        "label": "底稿文件",
        "fields": [
            "id", "project_id", "wp_index_id", "file_path", "source_type",
            "file_version", "status", "review_status",
            "assigned_to", "reviewer", "workflow_status",
            "explanation_status", "consistency_status",
            "is_deleted", "created_at", "updated_at",
        ],
    },
    "wp_index": {
        "model": WpIndex,
        "label": "底稿索引",
        "fields": [
            "id", "project_id", "wp_code", "wp_name", "audit_cycle",
            "assigned_to", "reviewer", "status",
            "is_deleted", "created_at", "updated_at",
        ],
    },
    "tb_balance": {
        "model": TbBalance,
        "label": "科目余额表",
        "fields": [
            "id", "project_id", "year", "company_code",
            "account_code", "account_name", "level",
            "opening_balance", "closing_balance",
            "debit_amount", "credit_amount", "currency_code",
            "is_deleted", "created_at", "updated_at",
        ],
    },
    "tb_ledger": {
        "model": TbLedger,
        "label": "序时账（总账明细）",
        "fields": [
            "id", "project_id", "year", "company_code",
            "voucher_date", "voucher_no", "account_code", "account_name",
            "accounting_period", "voucher_type", "entry_seq",
            "debit_amount", "credit_amount", "summary",
            "currency_code", "is_deleted", "created_at",
        ],
    },
    "account_chart": {
        "model": AccountChart,
        "label": "科目表",
        "fields": [
            "id", "project_id", "account_code", "account_name",
            "direction", "level", "category", "parent_code",
            "source", "is_deleted", "created_at", "updated_at",
        ],
    },
    "materiality": {
        "model": Materiality,
        "label": "重要性水平",
        "fields": [
            "id", "project_id", "year", "benchmark_type",
            "benchmark_amount", "overall_percentage", "overall_materiality",
            "performance_ratio", "performance_materiality",
            "trivial_ratio", "trivial_threshold",
            "is_override", "is_deleted", "created_at", "updated_at",
        ],
    },
    # ── 业务维度扩展（项目 / 单位 / 附注 / 人员 / 工时） ──
    "projects": {
        "model": Project,
        "label": "项目",
        "fields": [
            "id", "name", "client_name",
            "audit_period_start", "audit_period_end",
            "project_type", "status", "scenario",
            "manager_id", "partner_id",
            "company_code", "template_type", "report_scope",
            "parent_company_name", "parent_company_code",
            "ultimate_company_name", "ultimate_company_code",
            "consol_level", "risk_level",
            "budget_hours", "contract_amount",
            "archived_at", "is_deleted", "created_at", "updated_at",
        ],
    },
    "disclosure_notes": {
        "model": DisclosureNote,
        "label": "附注",
        "fields": [
            "id", "project_id", "year",
            "note_section", "section_title", "account_name",
            "content_type", "source_template", "status",
            "sort_order", "is_stale",
            "is_deleted", "created_at", "updated_at",
        ],
    },
    "staff_members": {
        "model": StaffMember,
        "label": "人员",
        "fields": [
            "id", "user_id", "name", "employee_no",
            "department", "title", "partner_name", "partner_id",
            "specialty", "phone", "email", "join_date",
            "source", "role_level",
            "is_deleted", "created_at", "updated_at",
        ],
    },
    "work_hours": {
        "model": WorkHour,
        "label": "工时",
        "fields": [
            "id", "staff_id", "project_id", "work_date",
            "hours", "start_time", "end_time",
            "description", "status", "purpose", "ai_suggested",
            "is_deleted", "created_at", "updated_at",
        ],
    },
}


# S-3 v2：JOIN 白名单（声明式，不接受任意 ON 条件）
# 格式: {table_name: {target_table: {on: [(left_col, right_col), ...]}, ...}}
# 仅枚举常用业务关联，新增 JOIN 必须显式登记
JOIN_WHITELIST: dict[str, dict[str, dict[str, list[tuple[str, str]]]]] = {
    "trial_balance": {
        "wp_index": {"on": [("project_id", "project_id")]},
        "account_chart": {
            "on": [
                ("project_id", "project_id"),
                ("standard_account_code", "account_code"),
            ]
        },
        "report_line_mapping": {
            "on": [
                ("project_id", "project_id"),
                ("standard_account_code", "standard_account_code"),
            ]
        },
    },
    "adjustments": {
        "wp_index": {"on": [("project_id", "project_id")]},
        "trial_balance": {
            "on": [
                ("project_id", "project_id"),
                ("account_code", "standard_account_code"),
            ]
        },
    },
    "working_paper": {
        "wp_index": {"on": [("wp_index_id", "id")]},
    },
    "wp_index": {
        "working_paper": {"on": [("id", "wp_index_id")]},
    },
    "tb_balance": {
        "account_chart": {
            "on": [("project_id", "project_id"), ("account_code", "account_code")]
        },
    },
    "tb_ledger": {
        "account_chart": {
            "on": [("project_id", "project_id"), ("account_code", "account_code")]
        },
    },
    "report_line_mapping": {
        "report_config": {"on": [("report_line_code", "row_code")]},
    },
    # ── 业务维度 JOIN ──
    "projects": {
        # 项目 → 项目下所有业务对象
        "trial_balance":     {"on": [("id", "project_id")]},
        "working_paper":     {"on": [("id", "project_id")]},
        "wp_index":          {"on": [("id", "project_id")]},
        "tb_balance":        {"on": [("id", "project_id")]},
        "tb_ledger":         {"on": [("id", "project_id")]},
        "adjustments":       {"on": [("id", "project_id")]},
        "disclosure_notes":  {"on": [("id", "project_id")]},
        "work_hours":        {"on": [("id", "project_id")]},
    },
    "disclosure_notes": {
        "projects":          {"on": [("project_id", "id")]},
    },
    "staff_members": {
        "work_hours":        {"on": [("id", "staff_id")]},
    },
    "work_hours": {
        "staff_members":     {"on": [("staff_id", "id")]},
        "projects":          {"on": [("project_id", "id")]},
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 操作符白名单 — 显式分类，禁止任意 SQL 片段
# ─────────────────────────────────────────────────────────────────────────────
OPERATOR_WHITELIST: set[str] = {
    "eq", "neq",            # = / !=
    "gt", "gte", "lt", "lte",  # > / >= / < / <=
    "like", "not_like",     # LIKE / NOT LIKE（自动包裹 %）
    "in", "not_in",         # IN / NOT IN
    "is_null", "is_not_null",  # IS NULL / IS NOT NULL
    "between",              # BETWEEN（[lo, hi]）
}


AGGREGATE_WHITELIST: set[str] = {"count", "sum", "avg", "min", "max"}


# ─────────────────────────────────────────────────────────────────────────────
# 敏感表排除 — user / role / auth / token（R10.6 / R10.7）
# ─────────────────────────────────────────────────────────────────────────────
#: 敏感 token（表名以 ``_`` 或大小写边界切分后，任一 token 命中即视为敏感表）。
#: 覆盖 user/users、role/roles、auth、token/tokens 及其常见组合
#: （auth_tokens / refresh_tokens / user_roles / sessions 等）。
SENSITIVE_TABLE_TOKENS: frozenset[str] = frozenset(
    {
        "user", "users",
        "role", "roles",
        "auth",
        "token", "tokens",
        "session", "sessions",
        "password", "passwords",
        "credential", "credentials",
    }
)


def _tokenize_table_name(table_name: str) -> list[str]:
    """把表名切分为小写 token（按下划线 + 连字符）。"""
    return [t for t in table_name.lower().replace("-", "_").split("_") if t]


def is_sensitive_table(table_name: str) -> bool:
    """判断表名是否属于 user / role / auth / token 敏感范畴（R10.6 / R10.7）。

    以 token 级完整匹配，避免误伤（如 ``unadjusted_misstatements`` /
    ``work_hours`` / ``staff_members`` 中并不含敏感 token）。
    """
    if not table_name:
        return False
    tokens = set(_tokenize_table_name(table_name))
    return bool(tokens & SENSITIVE_TABLE_TOKENS)


def _assert_no_sensitive_in_whitelist() -> None:
    """导入时不变式：任何敏感表都不得出现在 ``TABLE_WHITELIST`` 中（R10.6）。

    这是"不允许经任何登记路径纳入白名单"的编译期护栏——一旦有人把敏感表加入
    白名单，模块导入即失败，从源头堵死登记路径。
    """
    offending = sorted(t for t in TABLE_WHITELIST if is_sensitive_table(t))
    if offending:
        raise RuntimeError(
            "TABLE_WHITELIST 含敏感表（user/role/auth/token），违反安全铁律："
            f"{offending}。敏感表不允许经任何登记路径纳入白名单。"
        )


_assert_no_sensitive_in_whitelist()


# ─────────────────────────────────────────────────────────────────────────────
# 强制登记 + 敏感表排除 — 执行前统一门禁（单点）
# ─────────────────────────────────────────────────────────────────────────────
def _deny_not_whitelisted(kind: str, obj: str, allowed: Iterable[str]) -> None:
    """抛出统一的 ``NOT_WHITELISTED`` 错误（指明未登记对象，不部分执行，R10.5）。"""
    raise HTTPException(
        status_code=400,
        detail={
            "error_code": "NOT_WHITELISTED",
            "message": f"{kind} '{obj}' 未登记，执行前拒绝",
            "kind": kind,
            "object": obj,
            "allowed": sorted(allowed),
        },
    )


def _deny_sensitive(table_name: str) -> None:
    """抛出统一的 ``SENSITIVE_TABLE_DENIED`` 错误（无条件拒绝，R10.7）。"""
    raise HTTPException(
        status_code=400,
        detail={
            "error_code": "SENSITIVE_TABLE_DENIED",
            "message": f"表 '{table_name}' 属敏感表（user/role/auth/token），无条件拒绝",
            "object": table_name,
        },
    )


def enforce_not_sensitive(table_name: str) -> None:
    """敏感表无条件拒绝（优先于任何登记校验，R10.7）。"""
    if is_sensitive_table(table_name):
        _deny_sensitive(table_name)


def enforce_table_registered(table_name: str) -> None:
    """校验表已登记且非敏感表；否则执行前拒绝（R10.4 / R10.5 / R10.7）。

    敏感表优先无条件拒绝（``SENSITIVE_TABLE_DENIED``），其次校验登记
    （``NOT_WHITELISTED``）。
    """
    enforce_not_sensitive(table_name)
    if table_name not in TABLE_WHITELIST:
        _deny_not_whitelisted("table", table_name, TABLE_WHITELIST.keys())


def enforce_join_registered(base_table: str, target_table: str) -> None:
    """校验 ``base_table`` → ``target_table`` 的 JOIN 已显式登记（R10.4 / R10.5）。

    两端表均先过敏感表与登记校验，再校验 JOIN 关系本身已登记。
    """
    enforce_table_registered(base_table)
    enforce_table_registered(target_table)
    allowed = JOIN_WHITELIST.get(base_table, {})
    if target_table not in allowed:
        _deny_not_whitelisted(
            "join", f"{base_table} -> {target_table}", allowed.keys()
        )


def enforce_operator_registered(op: str) -> None:
    """校验操作符已登记；否则执行前拒绝（R10.4 / R10.5）。"""
    if op not in OPERATOR_WHITELIST:
        _deny_not_whitelisted("operator", op, OPERATOR_WHITELIST)


def enforce_aggregate_registered(func_name: str) -> None:
    """校验聚合函数已登记；否则执行前拒绝（R10.4 / R10.5）。"""
    if func_name not in AGGREGATE_WHITELIST:
        _deny_not_whitelisted("aggregate", func_name, AGGREGATE_WHITELIST)


def enforce_query_plan(
    *,
    tables: Iterable[str] = (),
    joins: Iterable[tuple[str, str]] = (),
    operators: Iterable[str] = (),
    aggregates: Iterable[str] = (),
) -> None:
    """运行时查询计划统一门禁：执行前一次性校验计划涉及的全部对象。

    校验顺序保证"敏感表无条件优先拒绝"（R10.7），任一对象未通过即抛出、**不部分
    执行**（R10.5）：

    1. 所有引用表：敏感表 → ``SENSITIVE_TABLE_DENIED``；未登记 → ``NOT_WHITELISTED``。
    2. 所有 JOIN：两端表校验 + JOIN 关系登记校验。
    3. 所有操作符 / 聚合：登记校验。

    QueryOrchestrator / ParamSQLBuilder 在构造并执行 SQL 前调用本函数作为单一门禁。
    """
    # 1) 先无条件排除敏感表（R10.7 优先级最高）——含 JOIN 两端表
    for table_name in tables:
        enforce_not_sensitive(table_name)
    for base_table, target_table in joins:
        enforce_not_sensitive(base_table)
        enforce_not_sensitive(target_table)

    # 2) 登记校验（表 / JOIN / 操作符 / 聚合）
    for table_name in tables:
        enforce_table_registered(table_name)
    for base_table, target_table in joins:
        enforce_join_registered(base_table, target_table)
    for op in operators:
        enforce_operator_registered(op)
    for func_name in aggregates:
        enforce_aggregate_registered(func_name)
