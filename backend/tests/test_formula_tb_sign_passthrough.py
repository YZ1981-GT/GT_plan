"""公式取数层 TB 符号透传守护测试（Task 5.1 / 需求 11.1、11.4）。

验证公式求值器从 trial_balance 取数时**按 v2 新约定原样返回符号**，
不做基于旧约定（借正贷负）的隐式翻转。

盘点结论（Task 5.1）：
- `cell_formula_evaluator` / `wp_formula_eval_service` / `module_cell_resolver`
  / data_fetch_custom 的 TB 字段映射只是"中文列名 → DB 列名"的纯取列，
  无任何按 code/category 取负、取绝对值、`-amount` 的旧约定补偿。
- 唯一影响符号的是 `data_fetch_custom` 的 `transform` 显式配置
  （direct/negate/abs），属配置数据（Task 5.2 处理），求值器代码逻辑本身
  对 `direct`（默认）原样透传，不隐式翻转。

本测试守护：求值器代码层在 v2 下不引入隐式符号翻转。

Validates: Requirements 11.1, 11.4
"""
from __future__ import annotations

from decimal import Decimal

from app.services.data_fetch_custom import CustomFetchService, Transform


# ─────────────────────────────────────────────────────────────────────────
# 1. 字段映射纯取列（无符号翻转语义）
# ─────────────────────────────────────────────────────────────────────────

def test_cell_formula_evaluator_tb_field_map_is_pure_column():
    """cell_formula_evaluator 的 TB 跨表引用映射只映列名，不含符号处理。

    审定数→audited_amount / 期末→audited_amount / 未审数→unadjusted_amount
    / 期初→opening_balance —— 全是列名，无翻转。

    Validates: Requirements 11.1
    """
    from app.services.cell_formula_evaluator import _cross_ref_to_source

    src = _cross_ref_to_source({"type": "TB", "args": ["2202", "期末"]})
    assert src == {
        "type": "trial_balance",
        "account_code": "2202",
        "field": "audited_amount",
    }
    # 未审数 / 期初 同样纯列名
    src2 = _cross_ref_to_source({"type": "TB", "args": ["2202", "未审数"]})
    assert src2["field"] == "unadjusted_amount"
    src3 = _cross_ref_to_source({"type": "TB", "args": ["2202", "期初"]})
    assert src3["field"] == "opening_balance"


def test_cell_formula_cache_lookup_no_flip():
    """_try_get_from_cache 直接返回缓存中的字段值，不按科目类别翻符号。

    应付账款（负债）审定数在 v2 下为正数 8000 → 原样返回 8000。

    Validates: Requirements 11.1, 11.4
    """
    from app.services.cell_formula_evaluator import _try_get_from_cache

    tb_context = {"2202": {"audited_amount": 8000.0, "unadjusted_amount": 8000.0}}
    cr = {"type": "TB", "args": ["2202", "期末"]}
    val = _try_get_from_cache(cr, tb_context)
    # 负债审定数正数原样返回，未被翻成 -8000
    assert val == 8000.0


def test_wp_formula_eval_column_map_is_pure_column():
    """wp_formula_eval_service 的 _COLUMN_MAP 只映列名，无符号假设。

    Validates: Requirements 11.1
    """
    from app.services.wp_formula_eval_service import _COLUMN_MAP

    assert _COLUMN_MAP["期末余额"] == "audited_amount"
    assert _COLUMN_MAP["审定数"] == "audited_amount"
    assert _COLUMN_MAP["未审数"] == "unadjusted_amount"
    assert _COLUMN_MAP["年初余额"] == "opening_balance"
    # 不应存在任何 "negate"/"abs"/符号翻转标记的列名映射
    for v in _COLUMN_MAP.values():
        assert v in {
            "audited_amount",
            "opening_balance",
            "unadjusted_amount",
            "rje_adjustment",
            "aje_adjustment",
        }


def test_module_cell_resolver_tb_columns_pure():
    """module_cell_resolver 的 TB 虚拟 sheet 列映射为纯列名（无翻转）。

    Validates: Requirements 11.1
    """
    from app.services.custom_query.module_cell_resolver import _TB_COLUMNS

    assert _TB_COLUMNS == [
        "account_code",
        "account_name",
        "opening_balance",
        "debit_amount",
        "credit_amount",
        "closing_balance",
        "audited_amount",
    ]


# ─────────────────────────────────────────────────────────────────────────
# 2. transform 代码逻辑：direct 默认原样透传（不隐式翻转）
# ─────────────────────────────────────────────────────────────────────────

def _svc() -> CustomFetchService:
    # _apply_transform 不访问 DB，构造时 db/project_id/year 用占位即可
    return CustomFetchService.__new__(CustomFetchService)


def test_apply_transform_direct_passthrough_positive():
    """默认 direct transform 原样返回 v2 正数，不隐式取负。

    应付账款（负债）审定数 v2 为 +8000 → direct 透传 8000。

    Validates: Requirements 11.1, 11.4
    """
    svc = _svc()
    out = svc._apply_transform([Decimal("8000")], Transform.DIRECT)
    assert out == Decimal("8000")


def test_apply_transform_default_is_passthrough():
    """未指定 transform（缺省 direct）时同样原样返回，无符号补偿。

    Validates: Requirements 11.1
    """
    svc = _svc()
    # 任意未知 transform 字符串走 else 分支，返回首个有效值（不翻转）
    out = svc._apply_transform([Decimal("12000")], "direct")
    assert out == Decimal("12000")
    out2 = svc._apply_transform([Decimal("-500")], "direct")
    # 带符号值（如负债出现借方余额的异常）也如实透传，不强制翻正/翻负
    assert out2 == Decimal("-500")


def test_apply_transform_negate_is_explicit_only():
    """negate 翻转仅在显式配置下发生（属 Task 5.2 配置数据范畴），

    代码逻辑本身不对 direct 取数自动施加 negate。

    Validates: Requirements 11.2
    """
    svc = _svc()
    # 显式 negate 才翻转
    assert svc._apply_transform([Decimal("8000")], Transform.NEGATE) == Decimal("-8000")
    # 但默认 direct 不翻
    assert svc._apply_transform([Decimal("8000")], Transform.DIRECT) == Decimal("8000")
