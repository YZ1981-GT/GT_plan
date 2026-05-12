"""分级错误码枚举 + ``ImportError`` 构造工厂。

见 design.md §10 / requirements 需求 8 / Sprint 1 Task 3。

本模块定义账表导入 v2 引擎的错误码体系，分四级：

- ``fatal``    — 无法启动（``FILE_TOO_LARGE`` / ``UNSUPPORTED_FILE_TYPE`` /
  ``CORRUPTED_FILE`` / ``XLS_NOT_SUPPORTED`` / ``ENCODING_DETECTION_FAILED``）
- ``blocking`` — 关键列 / L2 / L3 阻断性业务错误
- ``warning``  — 次关键列或非阻断业务问题
- ``info``     — 仅记录不弹窗（通过 ``INFO_CODES`` 集合区分，severity 仍为 warning）

另外保留 4 个通用码（``MISSING_COLUMN`` / ``AMOUNT_NOT_NUMERIC`` / ``DATE_INVALID``
/ ``EMPTY_VALUE``），对齐 requirements 需求 8 错误码对照表——这些码的 severity
随 ``column_tier`` 变化（关键列 blocking / 次关键列 warning / 非关键列不报），
所以 ``DEFAULT_SEVERITY`` 给它们保守的 ``warning``，调用方应显式传 ``severity``
或通过 ``column_tier`` 由业务层另行决策。

公开接口：

- 枚举 ``ErrorCode``
- 映射 ``DEFAULT_SEVERITY`` / ``DEFAULT_COLUMN_TIER``
- 集合 ``INFO_CODES``
- 工厂函数 ``make_error``
- 辅助判断 ``is_blocking`` / ``is_info``
"""

from enum import Enum
from typing import Optional, Union

from .detection_types import (
    ColumnTier,
    ErrorSeverity,
    ImportError,
)

# ---------------------------------------------------------------------------
# ErrorCode 枚举
# ---------------------------------------------------------------------------


class ErrorCode(str, Enum):
    """账表导入 v2 引擎分级错误码（单一真源，对齐 design §10）。"""

    # ------- fatal -------
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
    CORRUPTED_FILE = "CORRUPTED_FILE"
    XLS_NOT_SUPPORTED = "XLS_NOT_SUPPORTED"
    ENCODING_DETECTION_FAILED = "ENCODING_DETECTION_FAILED"

    # ------- blocking（关键列 / L2 / L3）-------
    NO_VALID_SHEET = "NO_VALID_SHEET"
    MISSING_KEY_COLUMN = "MISSING_KEY_COLUMN"
    AMOUNT_NOT_NUMERIC_KEY = "AMOUNT_NOT_NUMERIC_KEY"
    DATE_INVALID_KEY = "DATE_INVALID_KEY"
    EMPTY_VALUE_KEY = "EMPTY_VALUE_KEY"
    BALANCE_UNBALANCED = "BALANCE_UNBALANCED"
    ACCOUNT_NOT_IN_CHART = "ACCOUNT_NOT_IN_CHART"
    BALANCE_LEDGER_MISMATCH = "BALANCE_LEDGER_MISMATCH"
    L2_LEDGER_YEAR_OUT_OF_RANGE = "L2_LEDGER_YEAR_OUT_OF_RANGE"

    # ------- warning（次关键列 / 非阻断）-------
    MISSING_RECOMMENDED_COLUMN = "MISSING_RECOMMENDED_COLUMN"
    AMOUNT_NOT_NUMERIC_RECOMMENDED = "AMOUNT_NOT_NUMERIC_RECOMMENDED"
    DATE_INVALID_RECOMMENDED = "DATE_INVALID_RECOMMENDED"
    YEAR_MISMATCH = "YEAR_MISMATCH"
    AUX_DIMENSION_PARSE_FAILED = "AUX_DIMENSION_PARSE_FAILED"
    HEADER_ROW_AMBIGUOUS = "HEADER_ROW_AMBIGUOUS"
    SHEET_MERGE_HEURISTIC = "SHEET_MERGE_HEURISTIC"
    AUX_ACCOUNT_MISMATCH = "AUX_ACCOUNT_MISMATCH"
    EXTRA_TRUNCATED = "EXTRA_TRUNCATED"
    CURRENCY_MIX = "CURRENCY_MIX"
    ROW_SKIPPED_KEY_EMPTY = "ROW_SKIPPED_KEY_EMPTY"  # 企业级宽容策略：脏行跳过

    # ------- info（severity=warning + INFO_CODES 标记，前端不弹窗）-------
    RAW_EXTRA_COLUMNS_PRESERVED = "RAW_EXTRA_COLUMNS_PRESERVED"
    AI_FALLBACK_USED = "AI_FALLBACK_USED"
    HISTORY_MAPPING_APPLIED = "HISTORY_MAPPING_APPLIED"

    # ------- 通用码（严格度随 column_tier 变化，见 requirements §需求 8）-------
    MISSING_COLUMN = "MISSING_COLUMN"
    AMOUNT_NOT_NUMERIC = "AMOUNT_NOT_NUMERIC"
    DATE_INVALID = "DATE_INVALID"
    EMPTY_VALUE = "EMPTY_VALUE"


# ---------------------------------------------------------------------------
# 严重级默认映射
# ---------------------------------------------------------------------------

DEFAULT_SEVERITY: dict[ErrorCode, ErrorSeverity] = {
    # fatal
    ErrorCode.FILE_TOO_LARGE: "fatal",
    ErrorCode.UNSUPPORTED_FILE_TYPE: "fatal",
    ErrorCode.CORRUPTED_FILE: "fatal",
    ErrorCode.XLS_NOT_SUPPORTED: "fatal",
    ErrorCode.ENCODING_DETECTION_FAILED: "fatal",
    # blocking
    ErrorCode.NO_VALID_SHEET: "blocking",
    ErrorCode.MISSING_KEY_COLUMN: "blocking",
    ErrorCode.AMOUNT_NOT_NUMERIC_KEY: "blocking",
    ErrorCode.DATE_INVALID_KEY: "blocking",
    ErrorCode.EMPTY_VALUE_KEY: "blocking",
    ErrorCode.BALANCE_UNBALANCED: "blocking",
    ErrorCode.ACCOUNT_NOT_IN_CHART: "blocking",
    ErrorCode.BALANCE_LEDGER_MISMATCH: "blocking",
    ErrorCode.L2_LEDGER_YEAR_OUT_OF_RANGE: "blocking",
    # warning
    ErrorCode.MISSING_RECOMMENDED_COLUMN: "warning",
    ErrorCode.AMOUNT_NOT_NUMERIC_RECOMMENDED: "warning",
    ErrorCode.DATE_INVALID_RECOMMENDED: "warning",
    ErrorCode.YEAR_MISMATCH: "warning",
    ErrorCode.AUX_DIMENSION_PARSE_FAILED: "warning",
    ErrorCode.HEADER_ROW_AMBIGUOUS: "warning",
    ErrorCode.SHEET_MERGE_HEURISTIC: "warning",
    ErrorCode.AUX_ACCOUNT_MISMATCH: "warning",
    ErrorCode.EXTRA_TRUNCATED: "warning",
    ErrorCode.CURRENCY_MIX: "warning",
    ErrorCode.ROW_SKIPPED_KEY_EMPTY: "warning",
    # info（severity=warning，通过 INFO_CODES 与真 warning 区分）
    ErrorCode.RAW_EXTRA_COLUMNS_PRESERVED: "warning",
    ErrorCode.AI_FALLBACK_USED: "warning",
    ErrorCode.HISTORY_MAPPING_APPLIED: "warning",
    # 通用码默认 warning；关键列场景调用方应显式传 severity="blocking"
    ErrorCode.MISSING_COLUMN: "warning",
    ErrorCode.AMOUNT_NOT_NUMERIC: "warning",
    ErrorCode.DATE_INVALID: "warning",
    ErrorCode.EMPTY_VALUE: "warning",
}


# info 分类：severity 仍是 warning，但前端只作为日志条目展示，不弹窗
INFO_CODES: frozenset[ErrorCode] = frozenset(
    {
        ErrorCode.RAW_EXTRA_COLUMNS_PRESERVED,
        ErrorCode.AI_FALLBACK_USED,
        ErrorCode.HISTORY_MAPPING_APPLIED,
    }
)


# ---------------------------------------------------------------------------
# 列分层默认映射
# ---------------------------------------------------------------------------

DEFAULT_COLUMN_TIER: dict[ErrorCode, Optional[ColumnTier]] = {
    # fatal 码与列无关
    ErrorCode.FILE_TOO_LARGE: None,
    ErrorCode.UNSUPPORTED_FILE_TYPE: None,
    ErrorCode.CORRUPTED_FILE: None,
    ErrorCode.XLS_NOT_SUPPORTED: None,
    ErrorCode.ENCODING_DETECTION_FAILED: None,
    # blocking 码：*_KEY / MISSING_KEY_COLUMN 归 key，其余（平衡/跨表类）无 tier
    ErrorCode.NO_VALID_SHEET: None,
    ErrorCode.MISSING_KEY_COLUMN: "key",
    ErrorCode.AMOUNT_NOT_NUMERIC_KEY: "key",
    ErrorCode.DATE_INVALID_KEY: "key",
    ErrorCode.EMPTY_VALUE_KEY: "key",
    ErrorCode.BALANCE_UNBALANCED: None,
    ErrorCode.ACCOUNT_NOT_IN_CHART: None,
    ErrorCode.BALANCE_LEDGER_MISMATCH: None,
    ErrorCode.L2_LEDGER_YEAR_OUT_OF_RANGE: None,
    # warning 码：*_RECOMMENDED 归 recommended，EXTRA_TRUNCATED 归 extra，其余无 tier
    ErrorCode.MISSING_RECOMMENDED_COLUMN: "recommended",
    ErrorCode.AMOUNT_NOT_NUMERIC_RECOMMENDED: "recommended",
    ErrorCode.DATE_INVALID_RECOMMENDED: "recommended",
    ErrorCode.YEAR_MISMATCH: None,
    ErrorCode.AUX_DIMENSION_PARSE_FAILED: None,
    ErrorCode.HEADER_ROW_AMBIGUOUS: None,
    ErrorCode.SHEET_MERGE_HEURISTIC: None,
    ErrorCode.AUX_ACCOUNT_MISMATCH: None,
    ErrorCode.EXTRA_TRUNCATED: "extra",
    ErrorCode.CURRENCY_MIX: None,
    ErrorCode.ROW_SKIPPED_KEY_EMPTY: "key",
    # info
    ErrorCode.RAW_EXTRA_COLUMNS_PRESERVED: "extra",
    ErrorCode.AI_FALLBACK_USED: None,
    ErrorCode.HISTORY_MAPPING_APPLIED: None,
    # 通用码：tier 由调用方按实际列分层提供
    ErrorCode.MISSING_COLUMN: None,
    ErrorCode.AMOUNT_NOT_NUMERIC: None,
    ErrorCode.DATE_INVALID: None,
    ErrorCode.EMPTY_VALUE: None,
}


# ---------------------------------------------------------------------------
# 构造工厂
# ---------------------------------------------------------------------------


def _coerce_code(code: Union[ErrorCode, str]) -> tuple[str, Optional[ErrorCode]]:
    """将 code 参数规范化为 (string_value, optional_enum)。

    - 传入 ``ErrorCode`` → 直接拆出字符串和枚举
    - 传入已知枚举值字符串 → 尝试反查为 ``ErrorCode``
    - 传入未知字符串 → 视为自定义码，``enum`` 部分为 ``None``
    """

    if isinstance(code, ErrorCode):
        return code.value, code
    if isinstance(code, str):
        try:
            enum_val = ErrorCode(code)
            return enum_val.value, enum_val
        except ValueError:
            return code, None
    raise TypeError(f"code 必须是 ErrorCode 或 str，收到 {type(code)!r}")


def make_error(
    code: Union[ErrorCode, str],
    *,
    message: str,
    severity: Optional[ErrorSeverity] = None,
    column_tier: Optional[ColumnTier] = None,
    file: Optional[str] = None,
    sheet: Optional[str] = None,
    row: Optional[int] = None,
    column: Optional[str] = None,
    suggestion: Optional[str] = None,
) -> ImportError:
    """构造一个 ``ImportError`` 实例，自动补默认 severity / column_tier。

    参数：

    - ``code``        ：``ErrorCode`` 枚举或字符串；后者若匹配到已知枚举值会自动
      反查补默认，否则视为自定义码，此时 ``severity`` 必须显式传入
    - ``message``     ：人类可读描述
    - ``severity``    ：不传则从 ``DEFAULT_SEVERITY`` 解析
    - ``column_tier`` ：不传则从 ``DEFAULT_COLUMN_TIER`` 解析；两处都没有则保持 None
    - ``file``/``sheet``/``row``/``column``/``suggestion``：定位与建议信息

    异常：

    - 当 ``code`` 是字符串且未登记为 ``ErrorCode`` 成员、且调用方没有显式传
      ``severity`` 时，抛 ``ValueError``
    """

    code_str, enum_val = _coerce_code(code)

    resolved_severity = severity
    if resolved_severity is None:
        if enum_val is None:
            raise ValueError(
                f"自定义错误码 {code_str!r} 必须显式传入 severity（未登记到 ErrorCode）"
            )
        resolved_severity = DEFAULT_SEVERITY[enum_val]

    resolved_tier = column_tier
    if resolved_tier is None and enum_val is not None:
        resolved_tier = DEFAULT_COLUMN_TIER.get(enum_val)

    return ImportError(
        code=code_str,
        severity=resolved_severity,
        message=message,
        file=file,
        sheet=sheet,
        row=row,
        column=column,
        suggestion=suggestion,
        column_tier=resolved_tier,
    )


# ---------------------------------------------------------------------------
# 辅助判断
# ---------------------------------------------------------------------------


def is_blocking(err: ImportError) -> bool:
    """错误是否阻断流程（fatal 或 blocking）。

    对齐 design §10 分级：fatal = 无法启动，blocking = 关键列/L2/L3 阻断。
    前端据此判断是否禁用 submit 按钮、是否红色弹窗拦截。
    """

    return err.severity in ("fatal", "blocking")


def is_info(err: ImportError) -> bool:
    """错误是否属于 info 分类（仅记录不弹窗）。

    严重级为 warning，但 code 在 ``INFO_CODES`` 集合中 → 前端只作为日志条目展示。
    """

    try:
        code_enum = ErrorCode(err.code)
    except ValueError:
        return False
    return code_enum in INFO_CODES


__all__ = [
    "ErrorCode",
    "DEFAULT_SEVERITY",
    "DEFAULT_COLUMN_TIER",
    "INFO_CODES",
    "make_error",
    "is_blocking",
    "is_info",
]
