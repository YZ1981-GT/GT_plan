"""列内容验证器 — 验证列数据是否匹配预期模式。

用于 identifier.py 在表头匹配后，对候选列的实际数据做二次验证，
提升/降低置信度。

验证器类型：
- ``date``   ：≥ 50% 非空值可解析为日期
- ``numeric``：≥ 80% 非空值可解析为数字（含千分位）
- ``code``   ：≥ 50% 非空值匹配字母+数字编码模式（如 1001.01、A-001）
- ``text``   ：≥ 50% 非空值为文本（非纯数字）

每个验证器返回 0.0-1.0 的匹配度分数。

见 design.md §28.4。
"""

from __future__ import annotations

import re
from typing import Callable

__all__ = ["validate_column_content", "VALIDATORS"]

# ---------------------------------------------------------------------------
# 日期模式
# ---------------------------------------------------------------------------

_DATE_PATTERNS: list[re.Pattern[str]] = [
    # ISO: 2025-01-15, 2025/01/15
    re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$"),
    # Chinese: 2025年1月15日
    re.compile(r"^\d{4}年\d{1,2}月\d{1,2}日?$"),
    # Compact: 20250115
    re.compile(r"^\d{8}$"),
    # With time: 2025-01-15 10:30:00
    re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}"),
    # ISO datetime: 2025-01-15T10:30:00
    re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}"),
]


def _is_date_value(value: str) -> bool:
    """判断单个值是否可解析为日期。"""
    v = value.strip()
    if not v:
        return False
    return any(p.match(v) for p in _DATE_PATTERNS)


# ---------------------------------------------------------------------------
# 数字模式
# ---------------------------------------------------------------------------

_NUMERIC_RE = re.compile(
    r"^[+-]?\s*[\d,]+\.?\d*$"  # 含千分位逗号、可选小数
)


def _is_numeric_value(value: str) -> bool:
    """判断单个值是否可解析为数字（含千分位）。"""
    v = value.strip()
    if not v:
        return False
    # 去掉千分位逗号后尝试 float
    candidate = v.replace(",", "").replace(" ", "")
    try:
        float(candidate)
        return True
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# 编码模式（科目编码、辅助编码等）
# ---------------------------------------------------------------------------

# 编码特征：字母+数字混合、含点号分隔（如 1001.01.02）、纯数字但有层级结构
_CODE_PATTERNS: list[re.Pattern[str]] = [
    # 纯数字编码（4-20位，如 1001、100101、6001010101）
    re.compile(r"^\d{4,20}$"),
    # 点分层级（如 1001.01.02）
    re.compile(r"^\d+(\.\d+)+$"),
    # 字母+数字混合（如 A001、GL-1001）
    re.compile(r"^[A-Za-z][\w\-\.]*\d+[\w\-\.]*$"),
    # 数字开头含字母（如 1001A）
    re.compile(r"^\d+[A-Za-z][\w\-\.]*$"),
]


def _is_code_value(value: str) -> bool:
    """判断单个值是否匹配编码模式。"""
    v = value.strip()
    if not v:
        return False
    return any(p.match(v) for p in _CODE_PATTERNS)


# ---------------------------------------------------------------------------
# 文本模式（非纯数字）
# ---------------------------------------------------------------------------


def _is_text_value(value: str) -> bool:
    """判断单个值是否为文本（非纯数字、非空）。"""
    v = value.strip()
    if not v:
        return False
    # 纯数字（含千分位）不算文本
    candidate = v.replace(",", "").replace(" ", "")
    try:
        float(candidate)
        return False  # 是数字，不是文本
    except (ValueError, TypeError):
        pass
    return True


# ---------------------------------------------------------------------------
# 验证器注册表
# ---------------------------------------------------------------------------

# 每种验证器的 (判定函数, 最低通过率阈值)
_VALIDATOR_SPECS: dict[str, tuple[Callable[[str], bool], float]] = {
    "date": (_is_date_value, 0.5),
    "numeric": (_is_numeric_value, 0.8),
    "code": (_is_code_value, 0.5),
    "text": (_is_text_value, 0.5),
}

VALIDATORS: set[str] = set(_VALIDATOR_SPECS.keys())


def validate_column_content(values: list[str], validator_type: str) -> float:
    """验证一列数据是否匹配预期模式，返回 0.0-1.0 匹配度。

    Args:
        values: 列中的数据值列表（通常取前 N 行数据）。
        validator_type: 验证器类型（date/numeric/code/text）。

    Returns:
        0.0-1.0 的匹配度分数。
        - 1.0 = 所有非空值都匹配
        - 0.0 = 没有非空值匹配，或无非空值，或未知验证器类型

    算法：
        match_ratio = 匹配值数 / 非空值数
        如果 match_ratio >= threshold → 返回 match_ratio
        如果 match_ratio < threshold → 返回 match_ratio * 0.5（惩罚）
    """
    if validator_type not in _VALIDATOR_SPECS:
        return 0.0

    check_fn, threshold = _VALIDATOR_SPECS[validator_type]

    # 过滤非空值
    non_empty = [v.strip() for v in values if v and v.strip()]
    if not non_empty:
        return 0.0

    # 计算匹配率
    matched = sum(1 for v in non_empty if check_fn(v))
    match_ratio = matched / len(non_empty)

    # 达到阈值返回原始比率，未达到则惩罚
    if match_ratio >= threshold:
        return match_ratio
    else:
        return match_ratio * 0.5
