"""ParamSQLBuilder 单元测试（advanced-query-module Task 6.1）

覆盖：
- 参数化绑定：用户值（含 SQL 元字符注入负载）在最终编译 SQL 文本出现 0 次（R10.1/R10.2）
- IN 集合用 ``= ANY(:codes)`` + ``list(...)`` 形态（asyncpg 安全）（R10.3）
- NOT IN 用 ``!= ALL(:codes)``
- 空集合：``in`` → 空结果（恒假谓词），``not_in`` → 全部行（恒真谓词），均不报错（R10.3）
- ``coerce_value`` 类型转换（UUID/Decimal/Date/DateTime/Bool/int/float）
- ``coerce_value`` 优雅降级：不支持 ``python_type`` 的列类型原值传回（不抛错）

Validates: Requirements 10.1, 10.2, 10.3
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import Column, Date, DateTime, Integer, Numeric, String, Uuid
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

from app.services.custom_query.param_sql_builder import (
    ParamSQLBuilder,
    build_filter,
    coerce_value,
)


class _Base(DeclarativeBase):
    pass


class _Row(_Base):
    __tablename__ = "_t_row"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    code: Mapped[str] = mapped_column(String(64))
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(18, 2))
    qty: Mapped[int] = mapped_column(Integer)
    day: Mapped[dt.date] = mapped_column(Date)
    ts: Mapped[dt.datetime] = mapped_column(DateTime)


def _compile_sql(clause) -> str:
    """编译为 postgresql 方言 SQL 文本（默认命名占位符，不 inline 用户值）。"""
    return str(clause.compile(dialect=postgresql.dialect()))


# ─────────────────────────────────────────────────────────────────────────────
# 参数化：用户值不出现在 SQL 文本（含注入负载）
# ─────────────────────────────────────────────────────────────────────────────
INJECTION_PAYLOADS = [
    "'; DROP TABLE users; --",
    '" OR 1=1 --',
    "1); DELETE FROM projects; --",
    "admin'--",
    "0x27 OR '1'='1",
]


@pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
def test_eq_user_value_not_in_sql_text(payload):
    clause = build_filter(_Row.code, "eq", payload)
    sql = _compile_sql(clause)
    # 用户原值 0 次出现在编译 SQL 文本中（作为 bindparam 绑定）
    assert payload not in sql
    assert ":code" in sql or "%(code" in sql


@pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
def test_like_user_value_not_in_sql_text(payload):
    clause = build_filter(_Row.code, "like", payload)
    sql = _compile_sql(clause)
    assert payload not in sql
    assert "LIKE" in sql.upper()


# ─────────────────────────────────────────────────────────────────────────────
# IN → = ANY(:codes)；NOT IN → != ALL(:codes)
# ─────────────────────────────────────────────────────────────────────────────
def test_in_uses_any_form():
    clause = build_filter(_Row.code, "in", ["a", "b", "c"])
    sql = _compile_sql(clause).upper()
    assert "= ANY (" in sql
    # 不使用 IN tuple 形态
    assert " IN (" not in sql


def test_not_in_uses_all_form():
    clause = build_filter(_Row.code, "not_in", ["a", "b"])
    sql = _compile_sql(clause).upper()
    assert "!= ALL (" in sql


def test_in_values_not_in_sql_text():
    clause = build_filter(_Row.code, "in", ["secret1", "secret2"])
    sql = _compile_sql(clause)
    assert "secret1" not in sql
    assert "secret2" not in sql


# ─────────────────────────────────────────────────────────────────────────────
# 空集合：in → 空结果（恒假）；not_in → 全部行（恒真）；均不报错
# ─────────────────────────────────────────────────────────────────────────────
def test_empty_in_returns_false_predicate():
    clause = build_filter(_Row.code, "in", [])
    sql = _compile_sql(clause).lower()
    assert "false" in sql  # 恒假 → 空结果集


def test_empty_not_in_returns_true_predicate():
    clause = build_filter(_Row.code, "not_in", [])
    sql = _compile_sql(clause).lower()
    assert "true" in sql  # 恒真 → 全部行


def test_empty_in_does_not_raise():
    # 空集合不报错（R10.3）
    build_filter(_Row.code, "in", [])
    build_filter(_Row.code, "not_in", [])


# ─────────────────────────────────────────────────────────────────────────────
# coerce_value 类型转换
# ─────────────────────────────────────────────────────────────────────────────
def test_coerce_uuid_from_str():
    u = uuid.uuid4()
    assert coerce_value(_Row.id, str(u)) == u


def test_coerce_invalid_uuid_raises_400():
    with pytest.raises(HTTPException) as ei:
        coerce_value(_Row.id, "not-a-uuid")
    assert ei.value.detail["error_code"] == "INVALID_UUID"


def test_coerce_decimal_from_str():
    assert coerce_value(_Row.amount, "123.45") == decimal.Decimal("123.45")


def test_coerce_date_from_iso():
    assert coerce_value(_Row.day, "2025-01-15") == dt.date(2025, 1, 15)


def test_coerce_datetime_from_iso():
    assert coerce_value(_Row.ts, "2025-01-15T08:30:00") == dt.datetime(2025, 1, 15, 8, 30, 0)


def test_coerce_int_from_str():
    assert coerce_value(_Row.qty, "42") == 42


def test_coerce_none_passthrough():
    assert coerce_value(_Row.code, None) is None


# ─────────────────────────────────────────────────────────────────────────────
# 优雅降级：不支持 python_type 的列类型 → 原值传回（不抛错）
# ─────────────────────────────────────────────────────────────────────────────
class _NoPyType(UserDefinedType):
    """模拟 Enum / 复合类型：python_type 抛 NotImplementedError。"""

    def get_col_spec(self, **kw):
        return "CUSTOM"

    @property
    def python_type(self):
        raise NotImplementedError


def test_coerce_unsupported_type_passes_value_through():
    col = Column("weird", _NoPyType())
    sentinel = "'; DROP TABLE x; --"
    # 不抛错，原值传回（优雅降级）
    assert coerce_value(col, sentinel) == sentinel


# ─────────────────────────────────────────────────────────────────────────────
# 操作符白名单 + between + is_null
# ─────────────────────────────────────────────────────────────────────────────
def test_unknown_operator_raises():
    with pytest.raises(HTTPException) as ei:
        build_filter(_Row.code, "regex", "x")
    assert ei.value.detail["error_code"] == "OP_NOT_ALLOWED"


def test_between_requires_pair():
    with pytest.raises(HTTPException) as ei:
        build_filter(_Row.amount, "between", ["1"])
    assert ei.value.detail["error_code"] == "INVALID_BETWEEN_VALUE"


def test_between_ok():
    clause = build_filter(_Row.amount, "between", ["1", "9999"])
    sql = _compile_sql(clause).upper()
    assert "BETWEEN" in sql


def test_is_null_ignores_value():
    clause = build_filter(_Row.code, "is_null", None)
    assert "IS NULL" in _compile_sql(clause).upper()


# ─────────────────────────────────────────────────────────────────────────────
# ParamSQLBuilder.build_where 组合
# ─────────────────────────────────────────────────────────────────────────────
def test_build_where_and():
    clause = ParamSQLBuilder.build_where(
        [(_Row.code, "eq", "x"), (_Row.qty, "gte", "5")], logic="and"
    )
    sql = _compile_sql(clause).upper()
    assert " AND " in sql


def test_build_where_empty_returns_none():
    assert ParamSQLBuilder.build_where([]) is None
