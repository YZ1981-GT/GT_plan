"""Table/JOIN/Operator 白名单属性测试（advanced-query-module Task 6.5 / 6.6）

逐条实现 design.md 的正确性属性：

- Property 19: 白名单强制（R10.4 / R10.5）
- Property 20: 敏感表排除（R10.6 / R10.7）

约定：每条属性一个属性测试，Hypothesis 迭代数收敛为 5（``@settings(max_examples=5)``）。
白名单门禁不构造 SQL，仅校验「对象是否被允许」，故无需编译；断言拒绝在执行前发生
（抛 HTTPException，不返回数据行、不部分执行）、并指明未登记/敏感的具体对象。

Validates: Requirements 10.4, 10.5, 10.6, 10.7
"""

from __future__ import annotations

from fastapi import HTTPException
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.services.custom_query.table_whitelist import (
    AGGREGATE_WHITELIST,
    JOIN_WHITELIST,
    OPERATOR_WHITELIST,
    SENSITIVE_TABLE_TOKENS,
    TABLE_WHITELIST,
    enforce_aggregate_registered,
    enforce_join_registered,
    enforce_not_sensitive,
    enforce_operator_registered,
    enforce_query_plan,
    enforce_table_registered,
    is_sensitive_table,
)

_IDENT = st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=3, max_size=20)


def _is_sensitive_ident(name: str) -> bool:
    tokens = {t for t in name.lower().replace("-", "_").split("_") if t}
    return bool(tokens & SENSITIVE_TABLE_TOKENS)


# ─────────────────────────────────────────────────────────────────────────────
# Feature: advanced-query-module, Property 19: 白名单强制
# For any 引用了未登记表、JOIN 或操作符的查询请求，Whitelist_Query_Builder 在执行前
# 拒绝该请求、指明未登记的具体对象、返回描述性错误，且不返回任何数据行、不部分执行。
# Validates: Requirements 10.4, 10.5
# ─────────────────────────────────────────────────────────────────────────────
@settings(max_examples=5)
@given(table=_IDENT)
def test_p19_unregistered_table_rejected(table):
    # 排除恰好已登记的表与敏感表（敏感表走 P20 路径，另有 error_code）
    assume(table not in TABLE_WHITELIST)
    assume(not _is_sensitive_ident(table))

    try:
        enforce_table_registered(table)
        assert False, "未登记表应在执行前被拒绝"
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail["error_code"] == "NOT_WHITELISTED"
        assert exc.detail["kind"] == "table"
        # 指明未登记的具体对象
        assert exc.detail["object"] == table


@settings(max_examples=5)
@given(op=_IDENT)
def test_p19_unregistered_operator_rejected(op):
    assume(op not in OPERATOR_WHITELIST)
    try:
        enforce_operator_registered(op)
        assert False, "未登记操作符应在执行前被拒绝"
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail["error_code"] == "NOT_WHITELISTED"
        assert exc.detail["kind"] == "operator"
        assert exc.detail["object"] == op


@settings(max_examples=5)
@given(agg=_IDENT)
def test_p19_unregistered_aggregate_rejected(agg):
    assume(agg not in AGGREGATE_WHITELIST)
    try:
        enforce_aggregate_registered(agg)
        assert False, "未登记聚合应在执行前被拒绝"
    except HTTPException as exc:
        assert exc.detail["error_code"] == "NOT_WHITELISTED"
        assert exc.detail["kind"] == "aggregate"


@settings(max_examples=5)
@given(base=st.sampled_from(sorted(TABLE_WHITELIST)), target=st.sampled_from(sorted(TABLE_WHITELIST)))
def test_p19_unregistered_join_rejected(base, target):
    # 两端都是已登记表，但 JOIN 关系本身未登记 → 仍应在执行前拒绝
    assume(target not in JOIN_WHITELIST.get(base, {}))
    try:
        enforce_join_registered(base, target)
        assert False, "未登记 JOIN 应在执行前被拒绝"
    except HTTPException as exc:
        assert exc.detail["error_code"] == "NOT_WHITELISTED"
        assert exc.detail["kind"] == "join"
        # 指明未登记的具体 JOIN 对象
        assert base in exc.detail["object"] and target in exc.detail["object"]


# ─────────────────────────────────────────────────────────────────────────────
# 敏感表生成器：以敏感 token 为核心，用下划线拼接前后缀，保证 token 级命中
# ─────────────────────────────────────────────────────────────────────────────
_AFFIX = st.sampled_from(["", "app", "refresh", "sys", "audit", "old", "tmp", "v2"])


@st.composite
def _sensitive_table(draw):
    token = draw(st.sampled_from(sorted(SENSITIVE_TABLE_TOKENS)))
    prefix = draw(_AFFIX)
    suffix = draw(_AFFIX)
    parts = [p for p in (prefix, token, suffix) if p]
    return "_".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Feature: advanced-query-module, Property 20: 敏感表排除
# For any 试图经任何登记路径或运行时查询计划引用 user/role/auth/token 敏感表的查询，
# 系统都无条件拒绝并返回描述性错误。
# Validates: Requirements 10.6, 10.7
# ─────────────────────────────────────────────────────────────────────────────
@settings(max_examples=5)
@given(table=_sensitive_table())
def test_p20_sensitive_table_unconditionally_denied(table):
    # is_sensitive_table 识别为敏感
    assert is_sensitive_table(table) is True

    # 直接门禁：无条件拒绝
    try:
        enforce_not_sensitive(table)
        assert False, "敏感表应被无条件拒绝"
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail["error_code"] == "SENSITIVE_TABLE_DENIED"
        assert exc.detail["object"] == table

    # 登记路径：敏感表优先于登记校验被拒绝（不会退化为 NOT_WHITELISTED）
    try:
        enforce_table_registered(table)
        assert False, "敏感表经登记校验路径也应被拒绝"
    except HTTPException as exc:
        assert exc.detail["error_code"] == "SENSITIVE_TABLE_DENIED"

    # 运行时查询计划：引用敏感表 → 无条件拒绝
    try:
        enforce_query_plan(tables=[table])
        assert False, "运行时查询计划引用敏感表应被拒绝"
    except HTTPException as exc:
        assert exc.detail["error_code"] == "SENSITIVE_TABLE_DENIED"


@settings(max_examples=5)
@given(base=st.sampled_from(sorted(TABLE_WHITELIST)), sensitive=_sensitive_table())
def test_p20_sensitive_table_in_join_denied(base, sensitive):
    # JOIN 到敏感表 → 无条件拒绝（敏感 token 优先于 JOIN 登记校验）
    try:
        enforce_query_plan(joins=[(base, sensitive)])
        assert False, "JOIN 到敏感表应被拒绝"
    except HTTPException as exc:
        assert exc.detail["error_code"] == "SENSITIVE_TABLE_DENIED"
