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
        # 已移除 `wp_index`：其 ON 仅 project_id ↔ project_id，两表无业务关系 ⇒
        # N 行试算表 × M 行底稿索引 = 项目内笛卡尔积（真实项目 TB 数千行 ×
        # wp_index 数百行 → 百万行级），且 LIMIT 施加在积之后、PG 仍须物化整个
        # join 结果。见 enforce_join_business_key。
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
        # 已移除 `wp_index`：同为纯 project_id 关联的笛卡尔积（见上）。
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
    # 已移除 `projects` 作为 base 向 8 张业务表的发散登记：以 projects 为 base 时
    # 每条 JOIN 都是「1 项目 × 该项目全部行」，多条叠加即多表笛卡尔积
    # （projects ⋈ trial_balance ⋈ tb_ledger ⋈ work_hours = 三表行数相乘，
    # tb_ledger 实测约 697 万行）。projects 仍在 TABLE_WHITELIST 内可单表查询，
    # 也仍可作为 JOIN **目标**（下方 disclosure_notes / work_hours → projects），
    # 那个方向是 N:1 收敛而非 1:N 发散。
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
# JOIN 业务键约束 + 复杂度预算（advanced-query-hardening-wiring-closure R6）
# ─────────────────────────────────────────────────────────────────────────────
#: 单独出现在 ON 条件里不足以构成业务关联的列 —— 它们只表达「同属一个项目」，
#: 不表达「这两行说的是同一件事」。仅按这些列 JOIN 得到的是项目内笛卡尔积。
NON_BUSINESS_JOIN_KEYS: frozenset[str] = frozenset(
    {"project_id", "year", "company_code", "is_deleted"}
)

#: 单次查询允许的最大 JOIN 条数。每多一条 JOIN 都可能成倍放大中间结果集。
MAX_JOINS_PER_QUERY = 3
#: 单次查询允许的最大分组维度数。维度过多等价于不分组，却要付排序与哈希代价。
MAX_GROUP_DIMS = 5
#: 单次查询允许的最大聚合表达式个数。
MAX_AGGREGATES = 10


def join_business_keys(on_pairs: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """从 ON 条件中筛出**业务键**对（两端列名都不属于 NON_BUSINESS_JOIN_KEYS）。"""
    keys: list[tuple[str, str]] = []
    for pair in on_pairs or ():
        left, right = str(pair[0]), str(pair[1])
        if left in NON_BUSINESS_JOIN_KEYS and right in NON_BUSINESS_JOIN_KEYS:
            continue
        keys.append((left, right))
    return keys


def enforce_join_business_key(
    base_table: str, target_table: str, on_pairs: Iterable[tuple[str, str]]
) -> None:
    """校验 JOIN 的 ON 至少含一个业务键；否则拒绝（R6.1）。

    仅 ``project_id ↔ project_id``（或同类作用域列）构成的 ON 会产出项目内笛卡尔积：
    结果行数是两表行数之积，且 ``LIMIT`` 施加在积之后 —— PG 仍要物化整个 join
    结果，导出路径更会把全部行拉完。这类 JOIN 在语义上也没有意义：它把「同一项目
    的任意两行」两两配对，任何聚合结果都是错的。
    """
    if not join_business_keys(on_pairs):
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "JOIN_MISSING_BUSINESS_KEY",
                "message": (
                    f"JOIN '{base_table} -> {target_table}' 的关联条件只含作用域列"
                    f"（{sorted(NON_BUSINESS_JOIN_KEYS)}），会产生笛卡尔积，已拒绝"
                ),
                "base_table": base_table,
                "target_table": target_table,
                "on": [list(p) for p in (on_pairs or ())],
            },
        )


def enforce_complexity_budget(
    *, joins: int = 0, group_dims: int = 0, aggregates: int = 0
) -> None:
    """校验单次查询的复杂度预算（R6.2 / R6.3）。

    改造前 DSL 对 ``joins`` / ``group_by`` / ``aggregates`` 的条数完全不限：一次
    请求可声明 8 条 JOIN，中间结果集成倍放大而 LIMIT 无法阻止 PG 物化。
    """
    for actual, limit, kind, label in (
        (joins, MAX_JOINS_PER_QUERY, "joins", "JOIN 条数"),
        (group_dims, MAX_GROUP_DIMS, "group_dims", "分组维度数"),
        (aggregates, MAX_AGGREGATES, "aggregates", "聚合表达式个数"),
    ):
        if actual > limit:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "COMPLEXITY_BUDGET_EXCEEDED",
                    "message": f"{label} {actual} 超过上限 {limit}，请拆分查询",
                    "kind": kind,
                    "actual": actual,
                    "limit": limit,
                },
            )


def _assert_all_joins_have_business_key() -> None:
    """导入时不变式：``JOIN_WHITELIST`` 中不得存在纯作用域列的 JOIN 登记（R6.1）。

    与 ``_assert_no_sensitive_in_whitelist`` 同样是**登记期**护栏而非运行期检查 ——
    运行期校验只能拦住「用了这条 JOIN 的请求」，而不变式能拦住「把这条 JOIN 加进
    白名单」这个动作本身，从源头堵死。
    """
    offending: list[str] = []
    for base_table, targets in JOIN_WHITELIST.items():
        for target_table, spec in targets.items():
            if not join_business_keys(spec.get("on") or ()):
                offending.append(f"{base_table} -> {target_table}")
    if offending:
        raise RuntimeError(
            "JOIN_WHITELIST 含仅按作用域列关联的 JOIN（笛卡尔积风险）："
            f"{sorted(offending)}。ON 条件必须至少含一个业务键。"
        )


_assert_all_joins_have_business_key()


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


# ─────────────────────────────────────────────────────────────────────────────
# 列分层：业务默认列 / 技术列 / PII 列（R7）
# ─────────────────────────────────────────────────────────────────────────────
#: 技术列 —— 无业务语义，仅供排查。改造前 15 张表的 ``fields`` 全部含这些列，
#: 而前端 ``dsl.fields = []`` 是**默认值**，用户不选字段即命中「无 fields 默认
#: 全字段」分支 ⇒ 结果表第一列是 UUID，审计师看到的首列是无意义的主键。
TECHNICAL_FIELD_NAMES: frozenset[str] = frozenset(
    {"id", "project_id", "is_deleted", "created_at", "updated_at"}
)

#: 各表的 PII 列（按角色下发，R7.4）。只有 staff_members 含个人可识别信息。
PII_FIELDS_BY_TABLE: dict[str, frozenset[str]] = {
    "staff_members": frozenset({"email", "phone", "user_id"}),
}

#: 可查看 PII 列的角色。其余角色的 schema 中该列被隐去，显式请求 → 403。
#:
#: 🔴 **不含 manager**：构建器本身的准入角色是 admin / manager / partner，若 PII
#: 白名单与之完全重合，这层分层就是空操作（能进构建器的人恰好都有 PII 权限）——
#: 那正是本 spec 要消除的「additive 注入即死代码」。按职责划分：admin 需要维护
#: 账号、partner 需要联系人员，而 manager 是现场项目管理、不需要全体员工的邮箱
#: 与手机号。
PII_ALLOWED_ROLES: frozenset[str] = frozenset({"admin", "partner"})


class FieldTiers(dict):
    """一张表的列分层结果。

    以 dict 子类承载，便于直接展开进 ``TABLE_WHITELIST`` 的表元数据，
    同时保留属性式读取。
    """

    @property
    def default_fields(self) -> list[str]:
        return list(self["default_fields"])

    @property
    def technical_fields(self) -> list[str]:
        return list(self["technical_fields"])

    @property
    def pii_fields(self) -> list[str]:
        return list(self["pii_fields"])


def derive_field_tiers(fields: Iterable[str], *, pii: Iterable[str] = ()) -> FieldTiers:
    """由完整字段清单派生三层列集（单一派生入口，避免 15 张表手写漂移）。

    - ``pii_fields``：显式登记的 PII 列（**优先级最高**）；
    - ``technical_fields``：命中 :data:`TECHNICAL_FIELD_NAMES` 且未登记为 PII 的列；
    - ``default_fields``：其余列（= 业务列），即用户未选字段时的默认列集。

    PII 列**不进** default：默认查询不该带出邮箱手机号，需要时显式选择并经角色校验。

    🔴 三层必须构成严格**划分**（并集=全集、两两不相交），故需要明确优先级：
    一个列名可能同时命中技术列名单与 PII 登记（例如某表把 ``project_id`` 视为敏感），
    此时**按 PII 归类**——安全优先，否则该列会落进 technical 而绕过
    :func:`enforce_pii_field_access` 的角色准入。此边界由属性测试
    ``test_p17_tiers_partition_fields_without_loss_or_overlap`` 随机输入抓出
    （定点守卫用真实表数据，恰好不重叠，覆盖不到）。
    """
    all_fields = [str(f) for f in fields]
    pii_set = {str(p) for p in pii}
    pii_cols = [f for f in all_fields if f in pii_set]
    technical = [
        f for f in all_fields if f in TECHNICAL_FIELD_NAMES and f not in pii_set
    ]
    default = [
        f for f in all_fields if f not in TECHNICAL_FIELD_NAMES and f not in pii_set
    ]
    return FieldTiers(
        default_fields=tuple(default),
        technical_fields=tuple(technical),
        pii_fields=tuple(pii_cols),
    )


def _attach_field_tiers() -> None:
    """把列分层挂到每张表的元数据上（导入期一次性派生）。

    与 ``fields`` 并列声明于同一真源内，前端经 ``GET /api/query/schema`` 消费，
    不在前端复制第二份列名清单（R7.5）。
    """
    for table_name, meta in TABLE_WHITELIST.items():
        tiers = derive_field_tiers(
            meta["fields"], pii=PII_FIELDS_BY_TABLE.get(table_name, ())
        )
        meta["default_fields"] = list(tiers["default_fields"])
        meta["technical_fields"] = list(tiers["technical_fields"])
        meta["pii_fields"] = list(tiers["pii_fields"])


_attach_field_tiers()


def visible_fields_for_role(table_name: str, role: str | None) -> list[str]:
    """该角色在 schema 中可见的字段清单（隐去无权 PII 列，R7.4）。"""
    meta = TABLE_WHITELIST.get(table_name)
    if not meta:
        return []
    if _role_may_see_pii(role):
        return list(meta["fields"])
    pii = set(meta.get("pii_fields") or ())
    return [f for f in meta["fields"] if f not in pii]


def _role_may_see_pii(role: str | None) -> bool:
    return str(role or "") in PII_ALLOWED_ROLES


def enforce_pii_field_access(
    table_name: str, requested_fields: Iterable[str], role: str | None
) -> None:
    """显式请求 PII 列但无权 → 403（R7.4）。"""
    if _role_may_see_pii(role):
        return
    meta = TABLE_WHITELIST.get(table_name) or {}
    pii = set(meta.get("pii_fields") or ())
    if not pii:
        return
    # 支持 `table.field` 双段语法：只比较列名段
    denied = sorted(
        {f for f in (str(x).split(".")[-1] for x in requested_fields) if f in pii}
    )
    if denied:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "PII_FIELD_FORBIDDEN",
                "message": (
                    f"字段 {denied} 属个人可识别信息，当前角色无权查询"
                ),
                "table": table_name,
                "fields": denied,
            },
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
