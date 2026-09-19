"""高级查询：值 → 谓词层单一真源守卫（param_sql_builder 接线）。

Feature: advanced-query-hardening-wiring-closure（收口遗留项①）
覆盖 Requirements 10.1 / 10.2 / 10.3 —— 参数化绑定、注入安全、IN 集合与空集合。

背景：``param_sql_builder`` 曾整体零引用 —— 它与 ``routers/query_builder`` 各写了
一份「值 coerce + 算子 → 谓词 + and/or 组合」实现，生产只走后者，前者只有契约测试
在跑（假绿第①源：additive 注入即死代码）。而 design.md §Components 8 本就要求
「构建器经 ParamSQLBuilder 强制」，从未接线。现三处收敛为一处，本文件锁死该接线。

判据全部是**行为型**（替身可观测），不是「字符串是否出现」：把 ``builder_dsl`` 里
绑定的委托名换成哨兵，若有人把实现重新内联回来，哨兵不再被观测 → 打红。另有方言
判据锁死当初真正踩到的坑（SQLite 无 ANY 函数）。

从 ``test_advanced_query_scope_budget_tiers.py`` 拆出（该文件已达 800 行门禁上限），
一个关注点一个文件。
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services.custom_query.table_whitelist import TABLE_WHITELIST

# ─────────────────────────────────────────────────────────────────────────────
# 值 → 谓词层单一真源（param_sql_builder 接线）
#
# 背景：``param_sql_builder`` 曾整体零引用 —— 它与 ``routers/query_builder`` 各写了
# 一份几乎相同的「值 coerce + 算子 → 谓词 + and/or 组合」实现，生产只走后者，前者
# 只有契约测试在跑（假绿第①源：additive 注入即死代码）。现已把三处收敛为一处：
# 构建器（``builder_dsl``）委托 ``param_sql_builder`` 的 ``coerce_value`` /
# ``build_filter`` / ``ParamSQLBuilder.build_where``。
#
# 判据全部是**行为型**（替身可观测），不是「字符串是否出现」：
# 把 builder_dsl 里绑定的委托名换成哨兵，若有人把实现重新内联回来，哨兵不再被观测
# → 打红。另加一条方言判据锁死当初真正踩到的坑（SQLite 无 ANY 函数）。
# ─────────────────────────────────────────────────────────────────────────────
class TestParamSqlBuilderIsSingleSource:
    """构建器的值→谓词层必须委托 param_sql_builder，不得再长出第二份实现。"""

    @staticmethod
    def _col():
        """取 tb_balance 的 account_code 列 —— 经白名单登记表拿 model，不猜导入路径。"""
        return getattr(TABLE_WHITELIST["tb_balance"]["model"], "account_code")

    def test_coerce_value_delegates_to_param_sql_builder(self, monkeypatch):
        """行为判据：换掉委托名后 builder_dsl._coerce_value 必须反映替身。"""
        from app.services.custom_query import builder_dsl as bd

        sentinel = object()
        monkeypatch.setattr(bd, "_psb_coerce_value", lambda col, v: sentinel)
        assert bd._coerce_value(self._col(), "whatever") is sentinel, (
            "builder_dsl._coerce_value 未经 _psb_coerce_value —— 说明又内联了一份"
            "类型 coerce 实现，param_sql_builder 会重新沦为死代码"
        )

    def test_scalar_ops_delegate_to_param_sql_builder(self, monkeypatch):
        """行为判据：除 in / not_in 外的算子必须委托 param_sql_builder.build_filter。"""
        from app.services.custom_query import builder_dsl as bd

        seen: list[tuple[str, object]] = []

        def _fake(col, op, value):
            seen.append((op, value))
            return col.is_(None)

        monkeypatch.setattr(bd, "_psb_build_filter", _fake)
        for op in ("eq", "neq", "gt", "gte", "lt", "lte", "like", "between", "is_null"):
            seen.clear()
            bd._build_filter(self._col(), op, "x" if op != "between" else ["a", "b"])
            assert seen and seen[0][0] == op, f"算子 {op} 未委托 param_sql_builder"

    def test_where_combination_delegates_to_build_where(self, monkeypatch):
        """行为判据：and / or 组合必须走 ParamSQLBuilder.build_where，不得各写一份。"""
        from app.services.custom_query import builder_dsl as bd

        calls: list[dict] = []

        def _fake_build_where(conditions, *, logic="and", filter_builder=None):
            calls.append({"n": len(conditions), "logic": logic, "fb": filter_builder})
            return None

        monkeypatch.setattr(bd, "_psb_build_where", _fake_build_where)
        dsl = bd.QueryDSL(
            table="tb_balance",
            filters=[
                {"field": "account_code", "op": "eq", "value": "1001"},
                {"field": "account_name", "op": "like", "value": "现金"},
            ],
            filter_logic="or",
        )
        bd._build_select(dsl)
        assert calls, "_build_select 未调用 _psb_build_where —— and/or 组合又内联了一份"
        assert calls[0]["n"] == 2 and calls[0]["logic"] == "or"
        assert calls[0]["fb"] is bd._build_filter, (
            "未把构建器自己的方言中立 _build_filter 注入 build_where，"
            "否则构建器会退回 PG 专用的 ANY 形态"
        )

    def test_production_imports_param_sql_builder(self):
        """结构判据：生产代码里必须真有一条 import 指向 param_sql_builder。

        与上面的行为判据互补：行为判据保证「走了委托名」，本条保证「委托名确实
        绑定到 param_sql_builder」而不是本文件内另写的同名函数。
        """
        import ast
        import inspect

        from app.services.custom_query import builder_dsl as bd

        from app.services.custom_query import param_sql_builder as psb

        tree = ast.parse(inspect.getsource(bd))
        targets = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert "app.services.custom_query.param_sql_builder" in targets, (
            "builder_dsl 不再 import param_sql_builder —— 该模块又整体零引用了"
        )
        # 对象同一性：三个委托名必须就是 param_sql_builder 的那三个实现
        assert bd._psb_coerce_value is psb.coerce_value
        assert bd._psb_build_filter is psb.build_filter
        assert bd._psb_build_where is psb.ParamSQLBuilder.build_where

    def test_builder_in_filter_is_dialect_neutral(self):
        """构建器的 in / not_in 必须能在 SQLite 上编译（当初真踩到的坑）。

        ``param_sql_builder`` 的契约是 PG 形态 ``= ANY`` / ``!= ALL``（其自身
        契约测试固定用 postgresql 方言编译）；构建器的端点测试在 SQLite 上**真实
        执行**，SQLite 无 ANY 函数会直接 OperationalError。故构建器这两个算子用
        方言中立的 in_ / notin_。
        """
        from sqlalchemy.dialects import sqlite

        from app.services.custom_query.builder_dsl import _build_filter

        for op in ("in", "not_in"):
            sql = str(
                _build_filter(self._col(), op, ["1001", "1002"]).compile(
                    dialect=sqlite.dialect()
                )
            ).upper()
            # 精确匹配算子形态：不能用裸 "ANY"，列名 COMPANY_CODE 里就含 ANY
            assert "= ANY (" not in sql and "!= ALL (" not in sql, (
                f"构建器 {op} 编译出 PG 专用形态，SQLite 端点测试会崩：{sql}"
            )
            assert " IN (" in sql or " NOT IN (" in sql, f"{op} 未产生 IN 谓词：{sql}"

    def test_builder_empty_set_does_not_raise(self):
        """R10.3 的实质：空集合不报错 —— in → 0 行、not_in → 全部行。"""
        from sqlalchemy.dialects import sqlite

        from app.services.custom_query.builder_dsl import _build_filter

        empty_in = str(
            _build_filter(self._col(), "in", []).compile(dialect=sqlite.dialect())
        ).lower()
        empty_not_in = str(
            _build_filter(self._col(), "not_in", []).compile(dialect=sqlite.dialect())
        ).lower()
        # SQLite 无布尔字面量，false()/true() 渲染为 0 / 1；PG 下才是 false / true。
        assert empty_in.strip() in ("0", "false", "0 = 1"), empty_in
        assert empty_not_in.strip() in ("1", "true", "1 = 1"), empty_not_in

    def test_select_with_in_filter_compiles_on_sqlite(self):
        """端到端：整条 DSL 经 _build_select 后仍须能在 SQLite 编译。

        与上一条互补 —— 上一条只测 ``_build_filter`` 单点，本条覆盖「``build_where``
        忽略了注入的 filter_builder、退回自己的 PG 形态」这种漏法。
        """
        from sqlalchemy.dialects import sqlite

        from app.services.custom_query.builder_dsl import QueryDSL, _build_select

        dsl = QueryDSL(
            table="tb_balance",
            filters=[{"field": "account_code", "op": "in", "value": ["1001", "1002"]}],
        )
        stmt, _cols = _build_select(dsl)
        sql = str(stmt.compile(dialect=sqlite.dialect())).upper()
        assert "= ANY (" not in sql, f"整条 DSL 编译出 PG 专用 ANY 形态：{sql}"
        assert " IN (" in sql, f"in 过滤未产生 IN 谓词：{sql}"

    def test_builder_rejects_non_list_in_value(self):
        """in / not_in 的 value 必须是数组，否则 400（不是静默当标量处理）。"""
        from app.services.custom_query.builder_dsl import _build_filter

        with pytest.raises(HTTPException) as ei:
            _build_filter(self._col(), "in", "1001")
        assert ei.value.detail["error_code"] == "INVALID_IN_VALUE"
