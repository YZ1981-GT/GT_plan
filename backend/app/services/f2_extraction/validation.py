"""F2 公式保存校验."""
from app.services.f2_extraction.extract import F2_COLUMN_MAP, parse_tb_formula
from app.services.wp_formula_eval_service import find_unsupported_formula_functions


def validate_f2_formula(expression: str) -> str | None:
    """校验 F2 Tier A 公式表达式.

    Returns:
        None 如果合法；否则返回错误描述字符串。
    """
    if not expression or not expression.strip():
        return "表达式不能为空"

    # 不支持函数检查（AUX/PREV/LEDGER）
    unsupported = find_unsupported_formula_functions(expression)
    if unsupported:
        return f"F2 取数公式不支持以下函数：{', '.join(unsupported)}"

    # TB 格式 + 列名校验
    parsed = parse_tb_formula(expression)
    if parsed is None:
        return f"F2 取数公式格式非法或列名不支持。支持的列名：{', '.join(F2_COLUMN_MAP.keys())}"

    return None
