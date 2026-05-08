"""探测/识别结果 Pydantic schemas（单一真源）。

见 design.md §3 / Sprint 1 Task 2。

本模块定义账表导入 v2 引擎识别阶段的所有数据结构和列分层常量。
作为 identifier / detector / adapter / validator / writer 之间的契约，
属于模块级单一真源，不依赖其他 ledger_import 内部模块（避免循环依赖）。

主要导出：

- 类型别名：``TableType`` / ``ConfidenceLevel`` / ``ErrorSeverity`` / ``ColumnTier``
- 模型：``ColumnMatch`` / ``SheetDetection`` / ``FileDetection``
  / ``LedgerDetectionResult`` / ``ImportError``
- 列分层常量：``KEY_COLUMNS`` / ``RECOMMENDED_COLUMNS``
- 辅助函数：``classify_column_tier``

注意 ``ImportError`` 与 Python builtin ``ImportError`` 同名（设计 spec 有意为之，
表示"导入阶段分级错误"领域模型）。如调用方需要 Python builtin，可在 import
本模块时改名：

    from backend.app.services.ledger_import.detection_types import (
        ImportError as LedgerImportError,
    )

本文件不使用 ``from __future__ import annotations``：类内字段引用 ``ImportError``
时必须解析到本模块定义的类而非 Python builtin，使用运行时类型注解可避免歧义。
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 类型别名
# ---------------------------------------------------------------------------

TableType = Literal[
    "balance",
    "ledger",
    "aux_balance",
    "aux_ledger",
    "account_chart",
    "unknown",
]

ConfidenceLevel = Literal["high", "medium", "low", "manual_required"]

ErrorSeverity = Literal["fatal", "blocking", "warning"]

ColumnTier = Literal["key", "recommended", "extra"]


# ---------------------------------------------------------------------------
# 列分层常量（识别/校验共用单一真源，见 design §4.2 + §27.6 / requirements 需求 2）
# ---------------------------------------------------------------------------

KEY_COLUMNS: dict[TableType, set[str]] = {
    "balance": {
        "account_code",
        "opening_balance",
        "closing_balance",
        "debit_amount",
        "credit_amount",
    },
    "ledger": {
        "voucher_date",
        "voucher_no",
        "account_code",
        "debit_amount",
        "credit_amount",
    },
    "aux_balance": {
        "account_code",
        "opening_balance",
        "closing_balance",
        "debit_amount",
        "credit_amount",
        "aux_type",
        "aux_code",
    },
    "aux_ledger": {
        "voucher_date",
        "voucher_no",
        "account_code",
        "debit_amount",
        "credit_amount",
        "aux_type",
        "aux_code",
    },
    "account_chart": {"account_code", "account_name"},
    "unknown": set(),
}

RECOMMENDED_COLUMNS: dict[TableType, set[str]] = {
    "balance": {
        "account_name",
        "level",
        "company_code",
        "currency_code",
        "accounting_period",
        "opening_debit",
        "opening_credit",
        "closing_debit",
        "closing_credit",
        "aux_dimensions",
    },
    "ledger": {
        "summary",
        "preparer",
        "currency_code",
        "voucher_type",
        "entry_seq",
        "company_code",
        "accounting_period",
        "account_name",
        "aux_dimensions",
    },
    "aux_balance": {
        "aux_name",
        "account_name",
        "level",
        "currency_code",
    },
    "aux_ledger": {
        "aux_name",
        "summary",
        "preparer",
        "currency_code",
        "voucher_type",
        "entry_seq",
        "account_name",
    },
    "account_chart": {"level", "category", "direction"},
    "unknown": set(),
}


def classify_column_tier(
    standard_field: Optional[str],
    table_type: TableType,
) -> ColumnTier:
    """根据 ``standard_field`` 和 ``table_type`` 判定列分层。

    规则（对齐 requirements 需求 2 列分层表）：

    - ``standard_field is None`` → ``"extra"``（未能映射到标准字段，进 raw_extra）
    - 属于 ``KEY_COLUMNS[table_type]`` → ``"key"``
    - 属于 ``RECOMMENDED_COLUMNS[table_type]`` → ``"recommended"``
    - 其余 → ``"extra"``
    """

    if standard_field is None:
        return "extra"
    if standard_field in KEY_COLUMNS.get(table_type, set()):
        return "key"
    if standard_field in RECOMMENDED_COLUMNS.get(table_type, set()):
        return "recommended"
    return "extra"


# ---------------------------------------------------------------------------
# Pydantic 模型（v2 语法）
#
# 注意：``ImportError`` 必须定义在 ``FileDetection`` / ``LedgerDetectionResult``
# 之前；否则 Pydantic 解析 ``list[ImportError]`` 时会命中 Python builtin
# ``ImportError``（exception 类型，无法生成 core schema）。
# ---------------------------------------------------------------------------


class ColumnMatch(BaseModel):
    """单列识别结果。

    对应 design §3 ``ColumnMatch``。识别器（identifier.py）为每个数据列产出一条，
    前端映射编辑器（ColumnMappingEditor.vue）按 ``column_tier`` 分三区展示。
    """

    model_config = ConfigDict(extra="forbid")

    column_index: int
    column_header: str
    standard_field: Optional[str] = None
    column_tier: ColumnTier
    confidence: int = Field(ge=0, le=100)
    source: Literal[
        "header_exact",
        "header_fuzzy",
        "content_pattern",
        "manual",
        "ai_fallback",
    ]
    sample_values: list[str] = Field(default_factory=list)

    @property
    def is_key_column(self) -> bool:
        """是否为关键列（用于前端分区展示和强制人工确认逻辑）。"""

        return self.column_tier == "key"

    @property
    def passes_threshold(self) -> bool:
        """按分层判定是否达到自动映射门槛（对齐 requirements 需求 2）。

        - ``key``        ：``confidence >= 80``
        - ``recommended``：``confidence >= 50``
        - ``extra``      ：始终为真（非关键列无门槛，原样进 raw_extra）
        """

        if self.column_tier == "key":
            return self.confidence >= 80
        if self.column_tier == "recommended":
            return self.confidence >= 50
        return True


class ImportError(BaseModel):  # noqa: A001 - 故意与 Python builtin 同名（spec 约定）
    """分级错误模型（对应 design §3 ``ImportError``）。

    注意：此类与 Python builtin ``ImportError`` 同名，设计规格有意为之，
    表示"导入阶段分级错误领域模型"；如调用方需要 Python builtin，请使用

        from backend.app.services.ledger_import.detection_types import (
            ImportError as LedgerImportError,
        )

    字段：

    - ``code``        ：错误码，如 ``MISSING_KEY_COLUMN`` /
      ``AMOUNT_NOT_NUMERIC_KEY`` 等（枚举集中在 errors.py）
    - ``severity``    ：fatal / blocking / warning 三级
    - ``column_tier`` ：key / recommended / extra，便于前端按列分层筛选错误
    - ``file`` / ``sheet`` / ``row`` / ``column``：精确定位
    - ``suggestion``  ：修复建议（人类可读）
    """

    model_config = ConfigDict(extra="forbid")

    code: str
    severity: ErrorSeverity
    message: str
    file: Optional[str] = None
    sheet: Optional[str] = None
    row: Optional[int] = None
    column: Optional[str] = None
    suggestion: Optional[str] = None
    column_tier: Optional[ColumnTier] = None


class SheetDetection(BaseModel):
    """单 sheet 识别结果。

    对应 design §3 ``SheetDetection``。``detection_evidence`` 是识别决策树的
    结构化记录，供前端"识别决策树可读化面板"翻译为人类可读日志。
    """

    model_config = ConfigDict(extra="forbid")

    file_name: str
    sheet_name: str
    row_count_estimate: int
    header_row_index: int
    data_start_row: int

    table_type: TableType
    table_type_confidence: int = Field(ge=0, le=100)
    confidence_level: ConfidenceLevel

    adapter_id: Optional[str] = None
    column_mappings: list[ColumnMatch] = Field(default_factory=list)

    has_aux_dimension: bool = False
    aux_dimension_columns: list[int] = Field(default_factory=list)

    preview_rows: list[list[str]] = Field(default_factory=list)

    detection_evidence: dict = Field(default_factory=dict)

    warnings: list[str] = Field(default_factory=list)


class FileDetection(BaseModel):
    """单文件识别结果。

    对应 design §3 ``FileDetection``。一个上传文件内若含多个 sheet，
    展开为多条 ``SheetDetection``；文件级错误（如编码无法识别、ZIP 解压失败）
    收敛到 ``errors`` 字段。
    """

    model_config = ConfigDict(extra="forbid")

    file_name: str
    file_size_bytes: int
    file_type: Literal["xlsx", "xls", "csv", "zip"]
    encoding: Optional[str] = None
    sheets: list[SheetDetection] = Field(default_factory=list)
    errors: list[ImportError] = Field(default_factory=list)


class LedgerDetectionResult(BaseModel):
    """总探测结果（前端预检弹窗消费）。

    对应 design §3 ``LedgerDetectionResult``。一次 detect 调用产出一份，
    通过 ``upload_token`` 关联到后续 submit 阶段的 staged 数据和 ImportJob。
    """

    model_config = ConfigDict(extra="forbid")

    upload_token: str
    files: list[FileDetection] = Field(default_factory=list)

    detected_year: Optional[int] = None
    year_confidence: int = 0
    year_evidence: dict = Field(default_factory=dict)

    # 合并后哪些 (file, sheet) 合为同一张表
    merged_tables: dict[TableType, list[tuple[str, str]]] = Field(default_factory=dict)

    # 4 张表中缺哪几张（+ 科目表）
    missing_tables: list[TableType] = Field(default_factory=list)
    # 缺失的是否可从其他表派生（如辅助表从主表派生）
    can_derive: dict[TableType, bool] = Field(default_factory=dict)

    errors: list[ImportError] = Field(default_factory=list)
    requires_manual_confirm: bool = False


__all__ = [
    # 类型别名
    "TableType",
    "ConfidenceLevel",
    "ErrorSeverity",
    "ColumnTier",
    # 模型
    "ColumnMatch",
    "SheetDetection",
    "FileDetection",
    "LedgerDetectionResult",
    "ImportError",
    # 列分层常量
    "KEY_COLUMNS",
    "RECOMMENDED_COLUMNS",
    # 辅助函数
    "classify_column_tier",
]
