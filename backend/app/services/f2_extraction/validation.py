"""F2 公式保存校验."""
import re

from app.services.f2_extraction.extract import F2_COLUMN_MAP, parse_tb_formula

#: F2 Tier A 取数公式只认 TB 取数：辅助核算 / 上年 / 序时账一律拒绝（F2 不走通用底稿求值器，
#: 工作底稿可编辑公式补齐 AUX / PREV 后此处仍保持拒绝，spec formula-governance-coverage-closure R6）。
_F2_REJECTED_FUNCTIONS = ("AUX", "PREV", "LEDGER", "COUNT_LEDGER", "LEDGER_DETAIL", "TB_AUX")
_CALL_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def _rejected_functions(expression: str) -> list[str]:
    called = {m.group(1).upper() for m in _CALL_RE.finditer(re.sub(r"'[^']*'", "''", expression))}
    return [name for name in _F2_REJECTED_FUNCTIONS if name in called]


def validate_f2_formula(expression: str) -> str | None:
    """校验 F2 Tier A 公式表达式.

    Returns:
        None 如果合法；否则返回错误描述字符串。
    """
    if not expression or not expression.strip():
        return "表达式不能为空"

    # 不支持函数检查（AUX/PREV/序时账）
    unsupported = _rejected_functions(expression)
    if unsupported:
        return f"F2 取数公式不支持以下函数：{', '.join(unsupported)}"

    # TB 格式 + 列名校验
    parsed = parse_tb_formula(expression)
    if parsed is None:
        return f"F2 取数公式格式非法或列名不支持。支持的列名：{', '.join(F2_COLUMN_MAP.keys())}"

    return None
