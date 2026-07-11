"""ParamSQLBuilder 属性测试（advanced-query-module Task 6.3 / 6.4）

逐条实现 design.md 的正确性属性：

- Property 17: 参数化 SQL 注入安全（R10.1 / R10.2）
- Property 18: IN 集合形态与空集合（R10.3）

约定：每条属性一个属性测试，Hypothesis 迭代数收敛为 5（``@settings(max_examples=5)``），
编译 SQL 一律走 postgresql 方言（与 test_param_sql_builder.py 一致），断言用户值经
bindparam 绑定、在编译 SQL 文本中出现 0 次。

Validates: Requirements 10.1, 10.2, 10.3
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid

from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import Column, Date, DateTime, Integer, Numeric, String, Uuid
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.services.custom_query.param_sql_builder import build_filter


class _Base(DeclarativeBase):
    pass


class _Row(_Base):
    __tablename__ = "_t_pbt_row"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    code: Mapped[str] = mapped_column(String(64))
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2))
    qty: Mapped[int] = mapped_column(Integer)
    day: Mapped[dt.date] = mapped_column(Date)
    ts: Mapped[dt.datetime] = mapped_column(DateTime)


def _compile(clause):
    """编译为 postgresql 方言；返回 (sql_text, params_dict)。

    默认命名占位符（不 inline 用户值），params_dict 携带绑定值——用于断言用户值
    确实作为字面参数被绑定，而非拼接进 SQL 文本。
    """
    compiled = clause.compile(dialect=postgresql.dialect())
    return str(compiled), compiled.params


# ─────────────────────────────────────────────────────────────────────────────
# 注入负载生成器：已知 SQL 注入 payload + 含 SQL 元字符 / Unicode 引号的随机文本
# ─────────────────────────────────────────────────────────────────────────────
_KNOWN_PAYLOADS = [
    "'; DROP TABLE users; --",
    '" OR 1=1 --',
    "1); DELETE FROM projects; --",
    "admin'--",
    "0x27 OR '1'='1",
    "\u2019 OR \u2018a\u2019=\u2018a",  # Unicode 单引号
    "\uff07; DROP TABLE t; \uff07",      # 全角引号
    "') UNION SELECT * FROM staff_members --",
]

_SQL_METACHARS = "'\"`;-#()=*|/\u2018\u2019\uff07"

# 危险前导字符：保证随机 payload 一定以 SQL 元字符/引号开头 —— 既是真正的注入负载，
# 又避免退化为形如 "1" 的裸字母数字串（会与命名占位符 `code_1` 的名字子串误撞，
# 造成 `payload not in sql` 假阳性；bindparam 命名占位符不含用户值，此类子串非泄露）。
_DANGEROUS_LEAD = "'\";-#`\u2018\u2019\uff07"

_injection_strategy = st.one_of(
    st.sampled_from(_KNOWN_PAYLOADS),
    # 拼接：危险前导字符 + 含 SQL 元字符/关键字/Unicode 引号的随机尾串
    st.builds(
        lambda lead, tail: lead + tail,
        st.sampled_from(list(_DANGEROUS_LEAD)),
        st.text(
            alphabet=_SQL_METACHARS + "ORAND SELECTdropDELETE 12=",
            min_size=2,
            max_size=40,
        ),
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Feature: advanced-query-module, Property 17: 参数化 SQL 注入安全
# For any 用户提供的输入值（含 SQL 元字符、关键字、引号等注入负载），最终编译发送到
# 数据库的 SQL 文本中该原始值出现 0 次，输入值均作为字面参数经 bindparam 绑定，不被
# 解释为 SQL 语法。
# Validates: Requirements 10.1, 10.2
# ─────────────────────────────────────────────────────────────────────────────
@settings(max_examples=5)
@given(payload=_injection_strategy, op=st.sampled_from(["eq", "neq", "gt", "gte", "lt", "lte"]))
def test_p17_scalar_injection_value_bound_not_in_sql(payload, op):
    clause = build_filter(_Row.code, op, payload)
    sql, params = _compile(clause)
    # 原始注入值 0 次出现在编译 SQL 文本中
    assert payload not in sql
    # 值作为字面参数经 bindparam 绑定
    assert payload in params.values()
    # SQL 文本仅含命名占位符
    assert ":code" in sql or "%(code" in sql


@settings(max_examples=5)
@given(payload=_injection_strategy)
def test_p17_like_injection_value_bound_not_in_sql(payload):
    clause = build_filter(_Row.code, "like", payload)
    sql, params = _compile(clause)
    # LIKE 把 payload 包进 %...% 后仍作为绑定参数，原文本不出现在 SQL 中
    assert payload not in sql
    assert any(payload in str(v) for v in params.values())
    assert "LIKE" in sql.upper()


# ─────────────────────────────────────────────────────────────────────────────
# IN 集合生成器：随机字符串 / 整数集合，含空集合边界
# ─────────────────────────────────────────────────────────────────────────────
_set_strategy = st.one_of(
    st.lists(st.text(alphabet=_SQL_METACHARS + "abcXYZ012", min_size=1, max_size=12), max_size=6),
    st.lists(st.integers(min_value=-10_000, max_value=10_000), max_size=6),
)


# ─────────────────────────────────────────────────────────────────────────────
# Feature: advanced-query-module, Property 18: IN 集合形态与空集合
# For any IN 集合条件，查询使用 `= ANY(:codes)` + `list(...)` 形态构造；当集合为空时
# 返回空结果集且不抛出错误。
# Validates: Requirements 10.3
# ─────────────────────────────────────────────────────────────────────────────
@settings(max_examples=5)
@given(values=_set_strategy, op=st.sampled_from(["in", "not_in"]))
def test_p18_in_set_form_and_empty_boundary(values, op):
    # 空集合不抛错（R10.3）——直接构造成功
    clause = build_filter(_Row.code, op, values)
    sql, params = _compile(clause)
    upper = sql.upper()

    if not values:
        # 空集合：in → 恒假（空结果集），not_in → 恒真（全部行）；均不报错、不含 IN tuple
        if op == "in":
            assert "false" in sql.lower()
        else:
            assert "true" in sql.lower()
        assert " IN (" not in upper
    else:
        # 非空集合：使用 = ANY(:codes) / != ALL(:codes)，绝不使用 IN tuple 形态
        if op == "in":
            assert "= ANY (" in upper
        else:
            assert "!= ALL (" in upper
        assert " IN (" not in upper
        # 集合中每个字符串值都作为字面参数绑定，不出现在 SQL 文本
        for v in values:
            if isinstance(v, str) and v:
                assert v not in sql
        # 绑定参数即为原集合（list 形态）
        bound = [p for p in params.values() if isinstance(p, list)]
        assert bound and bound[0] == list(values)
