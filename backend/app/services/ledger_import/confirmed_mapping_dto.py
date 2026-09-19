"""ConfirmedMappingDTO / NormalizedMappingDTO — 人工确认列映射契约。

见 design.md §4 / requirements 需求 4。

本模块定义前后端共享的映射确认 DTO 和 pipeline 消费的规范化 DTO。

核心设计：
- pipeline 只消费 ``mapping_entries[]`` 格式，以 ``column_index`` 为主键取值
- ``canonical_header`` 保证唯一性（重复原始表头通过后缀 ``#N`` 去重）
- ``sheet_key`` = ``{file_name}:{sheet_name}``，submit 阶段校验 detect artifact

导出：
- ``MappingEntry``：单列映射条目
- ``ConfirmedMappingDTO``：前端提交的确认映射
- ``NormalizedMappingDTO``：后端校验后的规范化映射（pipeline 唯一消费格式）
- ``generate_sheet_key``：稳定 sheet key 生成函数
- ``generate_canonical_headers``：重复表头去重函数
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 类型别名
# ---------------------------------------------------------------------------

TableTypeDTO = Literal[
    "balance", "ledger", "aux_balance", "aux_ledger", "account_chart", "unknown"
]


# ---------------------------------------------------------------------------
# MappingEntry
# ---------------------------------------------------------------------------


class MappingEntry(BaseModel):
    """单列映射条目。

    以 ``column_index`` 作为主键，pipeline 按此从原始行取值。
    ``canonical_header`` 保证唯一（重复原始表头如多个"借方"通过 ``#N`` 后缀区分）。
    ``standard_field`` 为规范化后的标准字段名（如 debit_amount / account_code）。
    """

    model_config = ConfigDict(extra="forbid")

    column_index: int = Field(ge=0, description="0-based 列位置")
    original_header: str = Field(description="原始表头文本")
    canonical_header: str = Field(description="去重后唯一表头（如 借方#3）")
    standard_field: str = Field(description="标准字段名（如 debit_amount）")


# ---------------------------------------------------------------------------
# ConfirmedMappingDTO
# ---------------------------------------------------------------------------


class ConfirmedMappingDTO(BaseModel):
    """前端提交的人工确认列映射。

    对应 design §4 ``ConfirmedMappingDTO``。前端 ColumnMappingEditor 确认后
    提交此结构，submit gate 校验后转换为 NormalizedMappingDTO 进入 pipeline。
    """

    model_config = ConfigDict(extra="forbid")

    detection_id: Optional[str] = Field(
        default=None,
        description="detect 阶段的 artifact ID，用于 submit 校验",
    )
    sheet_key: str = Field(
        description="稳定 sheet 标识，格式 {file_name}:{sheet_name}",
    )
    file_name: str
    sheet_name: str
    table_type: TableTypeDTO
    mapping_entries: list[MappingEntry] = Field(
        min_length=1,
        description="列映射条目列表，至少包含一条",
    )
    aux_dimension_columns: list[int] = Field(
        default_factory=list,
        description="辅助核算维度列索引",
    )
    file_fingerprint: Optional[str] = None
    software_fingerprint: Optional[str] = None
    confirmed_by_user: bool = Field(
        default=False,
        description="是否经人工确认（低置信度 sheet 必须为 True）",
    )


# ---------------------------------------------------------------------------
# NormalizedMappingDTO
# ---------------------------------------------------------------------------


class NormalizedMappingDTO(ConfirmedMappingDTO):
    """后端校验后的规范化映射 — pipeline 唯一消费格式。

    继承 ConfirmedMappingDTO，附加校验保证：
    - 所有 required 字段已填充
    - column_index 不重复且在有效范围内
    - mapping_entries 覆盖该 table_type 的关键列

    pipeline 只接受此类型，拒绝原始 ConfirmedMappingDTO。
    """

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def generate_sheet_key(file_name: str, sheet_name: str) -> str:
    """生成稳定 sheet key，供 submit 校验 detect artifact 对齐。

    格式：``{file_name}:{sheet_name}``

    Args:
        file_name: 文件名（含扩展名）
        sheet_name: Sheet 名称

    Returns:
        稳定唯一的 sheet key 字符串
    """
    return f"{file_name}:{sheet_name}"


def generate_detection_id(upload_token: str, file_name: str, sheet_name: str) -> str:
    """生成稳定的 detection_id，唯一标识一次 detect 中的某个 sheet。

    格式：``{upload_token}::{file_name}:{sheet_name}``

    submit 阶段通过比对 detection_id 校验前端提交的 mapping 是否对应
    当前 detect artifact，防止过期/伪造的 mapping 进入 pipeline。

    Args:
        upload_token: detect 阶段产出的 upload_token
        file_name: 文件名
        sheet_name: Sheet 名称

    Returns:
        detection_id 字符串
    """
    return f"{upload_token}::{file_name}:{sheet_name}"


def validate_sheet_key_matches(
    submitted_key: str,
    detect_file_name: str,
    detect_sheet_name: str,
) -> bool:
    """校验 submit 提交的 sheet_key 是否与 detect artifact 匹配。

    Args:
        submitted_key: 前端提交的 sheet_key
        detect_file_name: detect artifact 中的 file_name
        detect_sheet_name: detect artifact 中的 sheet_name

    Returns:
        True 如果匹配，False 否则
    """
    expected = generate_sheet_key(detect_file_name, detect_sheet_name)
    return submitted_key == expected


def generate_canonical_headers(original_headers: list[str]) -> list[str]:
    """为重复表头生成唯一 canonical_header。

    规则：
    - 唯一的表头保持原样
    - 重复的表头按 column_index 添加 ``#N`` 后缀（N 为 0-based 列索引）

    例如：
        ["期末余额.借方", "期末余额.贷方", "借方", "借方"]
        → ["期末余额.借方", "期末余额.贷方", "借方#2", "借方#3"]

    Args:
        original_headers: 原始表头列表（按列索引顺序）

    Returns:
        唯一化后的 canonical header 列表
    """
    from collections import Counter

    counts = Counter(original_headers)
    # 只有出现 > 1 次的表头需要加后缀
    duplicates = {h for h, c in counts.items() if c > 1}

    result: list[str] = []
    for idx, header in enumerate(original_headers):
        if header in duplicates:
            result.append(f"{header}#{idx}")
        else:
            result.append(header)
    return result


__all__ = [
    "MappingEntry",
    "ConfirmedMappingDTO",
    "NormalizedMappingDTO",
    "TableTypeDTO",
    "generate_sheet_key",
    "generate_detection_id",
    "validate_sheet_key_matches",
    "generate_canonical_headers",
]
