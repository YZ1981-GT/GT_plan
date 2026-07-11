"""ParamSQLBuilder — 参数化 SQL 绑定层（高级查询模块）

Task 6.1（advanced-query-module）：从 ``routers/query_builder.py`` 迁移/复用
参数化绑定逻辑，收敛到服务层单点，供后续 QueryOrchestrator / 白名单构建器复用。

设计要点（design.md §Components 8 ParamSQLBuilder）：
- 全部经 SQLAlchemy core + bindparam 构造，**用户值在最终 SQL 文本出现 0 次**，
  SQL 元字符（引号 / ``--`` / ``;`` / ``OR 1=1`` 等）一律按字面参数值绑定，
  不被解释为 SQL 语法（R10.1 / R10.2）。
- IN 集合用 ``col = ANY(:codes)`` + ``list(...)`` 形态（asyncpg 不支持 IN tuple 参数），
  **空集合返回空结果集且不报错**（R10.3）。
- 保留既有 ``_coerce_value`` 的 ``NotImplementedError`` 优雅降级分支：当列类型
  （Enum / 复合类型）不支持 ``python_type`` 时，把原值传回而非抛错（不改为 raise）。

本模块只负责「值 → 参数化谓词」这一层；表 / JOIN / 敏感表白名单强制属于 Task 6.2
（``query_builder`` 现有实现），本模块不重复实现，也不放开白名单。

Validates: Requirements 10.1, 10.2, 10.3
"""

from __future__ import annotations

import datetime as _dt
import decimal as _dec
import uuid as _uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import all_, and_, any_, false, or_, true
from sqlalchemy import Column
from sqlalchemy.sql.elements import ColumnElement

# ─────────────────────────────────────────────────────────────────────────────
# 操作符白名单 — 单一真源（Task 6.2）：从 table_whitelist 导入，避免 query_builder /
# param_sql_builder / QueryOrchestrator 三处各维护副本导致漂移。
# ─────────────────────────────────────────────────────────────────────────────
from app.services.custom_query.table_whitelist import OPERATOR_WHITELIST


def coerce_value(col: Column, value: Any) -> Any:
    """按列的 SQLAlchemy 类型把 user-supplied value 转为正确 Python 类型。

    修复生产 bug：UUID 列绑定 str value 时 SQLAlchemy 会调 ``value.hex`` 抛
    ``AttributeError: 'str' object has no attribute 'hex'``。同理 Date/DateTime/
    Decimal 列也需要从 ISO 字符串 / 数字 coerce。

    支持类型：UUID / Decimal / Date / DateTime / Bool / int / float。

    优雅降级（保留既有行为，**不改为抛错**）：当列类型（Enum / 复合类型）不支持
    ``python_type`` 时，捕获 ``NotImplementedError`` / ``AttributeError`` 并把
    **原值传回**，交由 SQLAlchemy 自行处理。
    """
    if value is None:
        return None

    # 取列的 Python type（通过 SQLAlchemy type 解析）
    try:
        col_type = col.type
        py_type = col_type.python_type
    except (NotImplementedError, AttributeError):
        # Enum / 复合类型可能不支持 python_type，原值传回（优雅降级，不抛错）
        return value

    # 已是正确类型 → 直接返回
    if isinstance(value, py_type):
        return value

    # UUID
    if py_type is _uuid.UUID:
        if isinstance(value, str):
            try:
                return _uuid.UUID(value)
            except (ValueError, AttributeError) as e:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error_code": "INVALID_UUID",
                        "message": f"无法解析为 UUID: {value!r} ({e})",
                    },
                )
        return value

    # Decimal
    if py_type is _dec.Decimal:
        try:
            return _dec.Decimal(str(value))
        except _dec.InvalidOperation:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "INVALID_DECIMAL",
                    "message": f"无法解析为 Decimal: {value!r}",
                },
            )

    # Date / DateTime
    if py_type is _dt.date:
        if isinstance(value, str):
            try:
                return _dt.date.fromisoformat(value)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail={"error_code": "INVALID_DATE", "message": f"无法解析为 date: {value!r}"},
                )
        return value
    if py_type is _dt.datetime:
        if isinstance(value, str):
            try:
                return _dt.datetime.fromisoformat(value)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error_code": "INVALID_DATETIME",
                        "message": f"无法解析为 datetime: {value!r}",
                    },
                )
        return value

    # Bool 字符串
    if py_type is bool and isinstance(value, str):
        lower = value.lower()
        if lower in ("true", "1", "yes"):
            return True
        if lower in ("false", "0", "no"):
            return False

    # int 字符串
    if py_type is int and isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return value  # 保持原值，让 SQLAlchemy 报更精确的错

    # float 字符串
    if py_type is float and isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return value

    return value


def build_filter(col: Column, op: str, value: Any) -> ColumnElement:
    """把 (列, 操作符, 用户值) 构造为参数化谓词 ``ColumnElement``。

    - 所有用户值经 ``coerce_value`` + bindparam 绑定，**不做字符串拼接**，
      SQL 元字符按字面参数值绑定（R10.1 / R10.2）。
    - ``in`` / ``not_in`` 用 ``col = ANY(:codes)`` / ``col != ALL(:codes)`` +
      ``list(...)`` 形态（asyncpg 不支持 IN tuple 参数）；**空集合返回空结果集
      且不报错**（R10.3）：``in`` 空集合 → 恒假谓词（0 行），``not_in`` 空集合
      → 恒真谓词（全部行）。
    """
    if op not in OPERATOR_WHITELIST:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "OP_NOT_ALLOWED",
                "message": f"操作符 '{op}' 不在白名单中",
                "allowed_ops": sorted(OPERATOR_WHITELIST),
            },
        )

    # ── IN / NOT IN：= ANY / != ALL（asyncpg 安全，空集合不报错）──
    if op in ("in", "not_in"):
        if not isinstance(value, (list, tuple)):
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "INVALID_IN_VALUE",
                    "message": f"{op} 操作符要求 value 为数组",
                },
            )
        coerced_list = [coerce_value(col, v) for v in value]
        # 空集合：返回恒假 / 恒真谓词——空结果不报错（R10.3）
        if not coerced_list:
            return false() if op == "in" else true()
        # asyncpg 不支持 IN tuple → 用 = ANY(:codes) / != ALL(:codes) + list(...)
        if op == "in":
            return col == any_(list(coerced_list))
        return col != all_(list(coerced_list))

    # ── BETWEEN ──
    if op == "between":
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "INVALID_BETWEEN_VALUE",
                    "message": "between 操作符要求 value 为 [lo, hi] 长度=2 数组",
                },
            )
        lo = coerce_value(col, value[0])
        hi = coerce_value(col, value[1])
        return col.between(lo, hi)

    # ── IS NULL / IS NOT NULL（忽略 value）──
    if op == "is_null":
        return col.is_(None)
    if op == "is_not_null":
        return col.isnot(None)

    # ── LIKE / NOT LIKE（强制字符串语义，不 coerce）──
    if op == "like":
        return col.like(f"%{value}%")
    if op == "not_like":
        return col.notlike(f"%{value}%")

    # ── 标量比较：eq / neq / gt / gte / lt / lte ──
    coerced = coerce_value(col, value)
    if op == "eq":
        return col == coerced
    if op == "neq":
        return col != coerced
    if op == "gt":
        return col > coerced
    if op == "gte":
        return col >= coerced
    if op == "lt":
        return col < coerced
    if op == "lte":
        return col <= coerced

    # 不会到此（OPERATOR_WHITELIST 已穷举）
    raise HTTPException(
        status_code=400,
        detail={"error_code": "OP_NOT_IMPLEMENTED", "message": f"操作符 {op} 未实现"},
    )


class ParamSQLBuilder:
    """参数化 SQL 谓词构造器（值绑定层）。

    仅负责把 (列, 操作符, 值) 条件组合为参数化 ``WHERE`` 谓词；表 / JOIN / 敏感表
    白名单强制由 Task 6.2 的白名单层负责，本类不重复实现。所有用户值经 bindparam
    绑定，最终 SQL 文本中用户值出现 0 次。
    """

    #: 供外部复用的操作符白名单
    operator_whitelist: set[str] = OPERATOR_WHITELIST

    @staticmethod
    def coerce_value(col: Column, value: Any) -> Any:
        return coerce_value(col, value)

    @staticmethod
    def build_filter(col: Column, op: str, value: Any) -> ColumnElement:
        return build_filter(col, op, value)

    @staticmethod
    def build_where(
        conditions: list[tuple[Column, str, Any]],
        *,
        logic: str = "and",
    ) -> ColumnElement | None:
        """把多个 (列, 操作符, 值) 条件组合为单个参数化 ``WHERE`` 谓词。

        ``logic`` ∈ {"and", "or"}；无条件时返回 ``None``（调用方不追加 WHERE）。
        """
        clauses = [build_filter(col, op, val) for col, op, val in conditions]
        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return or_(*clauses) if logic == "or" else and_(*clauses)
