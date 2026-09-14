"""变异检验：值 → 谓词层单一真源（param_sql_builder 接线）。

用法::

    python backend/scripts/check/mutate_advanced_query_param_sql_builder.py
    python backend/scripts/check/mutate_advanced_query_param_sql_builder.py --check-anchors

背景：``param_sql_builder`` 曾整体零引用 —— 与 ``routers/query_builder`` 各写一份
「值 coerce + 算子 → 谓词 + and/or 组合」，生产只走后者。现由 ``builder_dsl`` 委托，
本组锚定两件事：委托不得被重新内联；构建器的 in / not_in 须保持方言中立。

从 ``mutate_advanced_query_scope_budget.py`` 拆出（该脚本已达 800 行门禁上限），
harness 共用 ``mutate_common``。
"""

from __future__ import annotations

import argparse
import sys

from mutate_common import Mutation, check_group_anchors, run_group

GUARD = "backend/tests/test_advanced_query_param_sql_builder_wiring.py"
PSB_DSL = "backend/app/services/custom_query/builder_dsl.py"
PSB_MOD = "backend/app/services/custom_query/param_sql_builder.py"

PSB_MUTATIONS: tuple[tuple[Mutation, str], ...] = (
    (
        Mutation(
            "N01",
            PSB_DSL,
            "    return _psb_coerce_value(col, value)",
            "    return value  # 变异：不再委托，原样返回",
            "test_coerce_value_delegates_to_param_sql_builder",
            "coerce 不再委托（param_sql_builder 重新沦为死代码）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "N02",
            PSB_DSL,
            "    return _psb_build_filter(col, op, value)",
            "    return col == value  # 变异：内联一份标量比较",
            "test_scalar_ops_delegate_to_param_sql_builder",
            "标量算子内联一份实现（又变两处重复）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "N03",
            PSB_DSL,
            """    where_clause = _psb_build_where(
        conditions, logic=dsl.filter_logic, filter_builder=_build_filter
    )
    if where_clause is not None:
        stmt = stmt.where(where_clause)""",
            """    _mut = [_build_filter(c, o, v) for c, o, v in conditions]
    if _mut:
        stmt = stmt.where(and_(*_mut))  # 变异：and/or 组合内联""",
            "test_where_combination_delegates_to_build_where",
            "and/or 组合内联回 builder_dsl（第三处重复复活）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "N04",
            PSB_DSL,
            "        conditions, logic=dsl.filter_logic, filter_builder=_build_filter\n",
            "        conditions, logic=dsl.filter_logic\n",
            "test_where_combination_delegates_to_build_where",
            "不注入方言中立 filter_builder（构建器退回 PG 形态）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "N05",
            PSB_DSL,
            '        return col.in_(coerced) if op == "in" else col.notin_(coerced)',
            "        return _psb_build_filter(col, op, value)  # 变异：全量委托→ANY 形态",
            "test_builder_in_filter_is_dialect_neutral",
            "构建器 in/not_in 改回 PG 专用 ANY 形态（SQLite 必崩）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "N06",
            PSB_DSL,
            """        if not coerced:
            # R10.3：空集合返回空结果集 / 全部行，不报错
            return false() if op == "in" else true()""",
            """        if not coerced:
            raise HTTPException(  # 变异：空集合抛 400
                status_code=400,
                detail={"error_code": "EMPTY_IN", "message": "要求非空数组"},
            )""",
            "test_builder_empty_set_does_not_raise",
            "空集合抛 400（违反 R10.3）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "N07",
            PSB_DSL,
            "_psb_build_where = _ParamSQLBuilder.build_where",
            "_psb_build_where = lambda *a, **kw: _ParamSQLBuilder.build_where(*a, **kw)",
            "test_production_imports_param_sql_builder",
            "委托名不再是 param_sql_builder 的那个实现（行为同、身份断）",
        ),
        GUARD,
    ),
    (
        Mutation(
            "N08",
            PSB_MOD,
            "        clauses = [filter_builder(col, op, val) for col, op, val in conditions]",
            "        clauses = [build_filter(col, op, val) for col, op, val in conditions]",
            "test_select_with_in_filter_compiles_on_sqlite",
            "build_where 忽略注入的 filter_builder（构建器静默退回 ANY 形态）",
        ),
        GUARD,
    ),
)

LABEL = "值→谓词层"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-anchors", action="store_true", help="只校验锚点，不改文件")
    args = parser.parse_args()
    if args.check_anchors:
        return check_group_anchors(PSB_MUTATIONS, LABEL)
    return run_group(PSB_MUTATIONS, LABEL)


if __name__ == "__main__":
    sys.exit(main())
