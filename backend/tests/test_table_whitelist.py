"""白名单单一真源 + 强制登记 + 敏感表排除 单元测试（advanced-query-module Task 6.2）

覆盖：
- 白名单定义收敛到单点：``query_builder`` 复用 ``table_whitelist`` 同一对象（无副本漂移）
- 强制登记：未登记表/JOIN/操作符/聚合 → ``NOT_WHITELISTED``（含对象名、不部分执行）
- 敏感表排除：user/role/auth/token 无条件拒绝 → ``SENSITIVE_TABLE_DENIED``（优先于登记）
- 导入期不变式：白名单内不含任何敏感表
- 运行时计划门禁：``enforce_query_plan`` 一次性校验、任一未通过即抛出

Validates: Requirements 10.4, 10.5, 10.6, 10.7
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services.custom_query import table_whitelist as tw
from app.services.custom_query.table_whitelist import (
    AGGREGATE_WHITELIST,
    JOIN_WHITELIST,
    OPERATOR_WHITELIST,
    TABLE_WHITELIST,
    enforce_aggregate_registered,
    enforce_join_registered,
    enforce_not_sensitive,
    enforce_operator_registered,
    enforce_query_plan,
    enforce_table_registered,
    is_sensitive_table,
)


# ─────────────────────────────────────────────────────────────────────────────
# 单一真源：query_builder 与 param_sql_builder 复用同一对象
# ─────────────────────────────────────────────────────────────────────────────
def test_definitions_are_single_source():
    from app.routers import query_builder as qb
    from app.services.custom_query import param_sql_builder as psb

    # query_builder 从 table_whitelist 导入同一对象（is 身份相同 → 无副本）
    assert qb.TABLE_WHITELIST is TABLE_WHITELIST
    assert qb.JOIN_WHITELIST is JOIN_WHITELIST
    assert qb.OPERATOR_WHITELIST is OPERATOR_WHITELIST
    assert qb.AGGREGATE_WHITELIST is AGGREGATE_WHITELIST
    # param_sql_builder 操作符白名单也来自单点
    assert psb.OPERATOR_WHITELIST is OPERATOR_WHITELIST


def test_whitelist_contains_expected_core_tables():
    # 核心只读 audit/财务表登记齐全
    core = {
        "trial_balance", "adjustments", "unadjusted_misstatements",
        "report_line_mapping", "report_config", "working_paper", "wp_index",
        "tb_balance", "tb_ledger", "account_chart", "materiality",
    }
    assert core <= set(TABLE_WHITELIST.keys())


# ─────────────────────────────────────────────────────────────────────────────
# 导入期不变式：白名单内绝无敏感表（R10.6）
# ─────────────────────────────────────────────────────────────────────────────
def test_no_sensitive_table_in_whitelist():
    offending = [t for t in TABLE_WHITELIST if is_sensitive_table(t)]
    assert offending == [], f"白名单不得含敏感表: {offending}"
    # 显式护栏可重复调用且不抛（幂等）
    tw._assert_no_sensitive_in_whitelist()


# ─────────────────────────────────────────────────────────────────────────────
# is_sensitive_table：token 级匹配，避免误伤
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "name",
    [
        "users", "user", "roles", "role", "auth", "tokens", "token",
        "user_roles", "auth_tokens", "refresh_tokens", "access_tokens",
        "user_sessions", "api_tokens", "role_permissions",
    ],
)
def test_sensitive_tables_detected(name):
    assert is_sensitive_table(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "trial_balance", "unadjusted_misstatements", "work_hours",
        "staff_members", "disclosure_notes", "report_config", "wp_index",
        "account_chart", "materiality",
    ],
)
def test_legit_tables_not_flagged_sensitive(name):
    assert is_sensitive_table(name) is False


# ─────────────────────────────────────────────────────────────────────────────
# enforce_table_registered
# ─────────────────────────────────────────────────────────────────────────────
def test_enforce_table_registered_valid_passes():
    # 登记表不抛
    enforce_table_registered("trial_balance")


def test_enforce_table_registered_unregistered_rejects():
    with pytest.raises(HTTPException) as ei:
        enforce_table_registered("some_unknown_table")
    assert ei.value.status_code == 400
    assert ei.value.detail["error_code"] == "NOT_WHITELISTED"
    assert ei.value.detail["object"] == "some_unknown_table"  # 指明对象


def test_enforce_table_registered_sensitive_takes_precedence():
    # 敏感表优先无条件拒绝（SENSITIVE_TABLE_DENIED），而非 NOT_WHITELISTED
    with pytest.raises(HTTPException) as ei:
        enforce_table_registered("users")
    assert ei.value.status_code == 400
    assert ei.value.detail["error_code"] == "SENSITIVE_TABLE_DENIED"
    assert ei.value.detail["object"] == "users"


def test_enforce_not_sensitive():
    enforce_not_sensitive("trial_balance")  # 不抛
    with pytest.raises(HTTPException) as ei:
        enforce_not_sensitive("auth_tokens")
    assert ei.value.detail["error_code"] == "SENSITIVE_TABLE_DENIED"


# ─────────────────────────────────────────────────────────────────────────────
# enforce_join_registered
# ─────────────────────────────────────────────────────────────────────────────
def test_enforce_join_registered_valid_passes():
    enforce_join_registered("trial_balance", "wp_index")


def test_enforce_join_registered_unregistered_rejects():
    with pytest.raises(HTTPException) as ei:
        enforce_join_registered("materiality", "trial_balance")
    assert ei.value.detail["error_code"] == "NOT_WHITELISTED"
    assert ei.value.detail["kind"] == "join"
    assert "materiality -> trial_balance" == ei.value.detail["object"]


def test_enforce_join_registered_sensitive_target_rejects():
    with pytest.raises(HTTPException) as ei:
        enforce_join_registered("trial_balance", "users")
    assert ei.value.detail["error_code"] == "SENSITIVE_TABLE_DENIED"


# ─────────────────────────────────────────────────────────────────────────────
# enforce_operator_registered / enforce_aggregate_registered
# ─────────────────────────────────────────────────────────────────────────────
def test_enforce_operator_registered():
    enforce_operator_registered("eq")
    with pytest.raises(HTTPException) as ei:
        enforce_operator_registered("regexp")
    assert ei.value.detail["error_code"] == "NOT_WHITELISTED"
    assert ei.value.detail["kind"] == "operator"
    assert ei.value.detail["object"] == "regexp"


def test_enforce_aggregate_registered():
    enforce_aggregate_registered("sum")
    with pytest.raises(HTTPException) as ei:
        enforce_aggregate_registered("median")
    assert ei.value.detail["error_code"] == "NOT_WHITELISTED"
    assert ei.value.detail["kind"] == "aggregate"
    assert ei.value.detail["object"] == "median"


# ─────────────────────────────────────────────────────────────────────────────
# enforce_query_plan：运行时计划门禁（单点、不部分执行、敏感优先）
# ─────────────────────────────────────────────────────────────────────────────
def test_enforce_query_plan_all_valid_passes():
    enforce_query_plan(
        tables=["trial_balance", "wp_index"],
        joins=[("trial_balance", "wp_index")],
        operators=["eq", "in"],
        aggregates=["sum", "count"],
    )


def test_enforce_query_plan_rejects_unregistered_table():
    with pytest.raises(HTTPException) as ei:
        enforce_query_plan(tables=["trial_balance", "ghost_table"])
    assert ei.value.detail["error_code"] == "NOT_WHITELISTED"
    assert ei.value.detail["object"] == "ghost_table"


def test_enforce_query_plan_sensitive_takes_precedence_over_registration():
    # 即使计划里同时有未登记表，敏感表也应优先无条件拒绝
    with pytest.raises(HTTPException) as ei:
        enforce_query_plan(tables=["auth_tokens", "ghost_table"])
    assert ei.value.detail["error_code"] == "SENSITIVE_TABLE_DENIED"
    assert ei.value.detail["object"] == "auth_tokens"


def test_enforce_query_plan_rejects_sensitive_join_target():
    with pytest.raises(HTTPException) as ei:
        enforce_query_plan(
            tables=["trial_balance"],
            joins=[("trial_balance", "roles")],
        )
    assert ei.value.detail["error_code"] == "SENSITIVE_TABLE_DENIED"


def test_enforce_query_plan_rejects_unregistered_operator():
    with pytest.raises(HTTPException) as ei:
        enforce_query_plan(tables=["trial_balance"], operators=["ilike_regex"])
    assert ei.value.detail["error_code"] == "NOT_WHITELISTED"
    assert ei.value.detail["kind"] == "operator"
