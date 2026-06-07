"""Submit Gate — 提交前校验与 mapping 规范化。

见 design.md §5 / requirements 需求 4、5。

核心职责：
1. 校验 sheet_key 与 detect artifact 对齐
2. 兼容旧 {header: standard_field} 格式并转换为 mapping_entries[]
3. 阻断低置信度未确认 / 关键列缺失 / unknown 未改类型的提交
4. 输出 NormalizedMappingDTO 供 pipeline 唯一消费

SubmitGateError 表示校验失败（HTTP 400），调用方捕获后直接返回 blocking error。
"""

from __future__ import annotations

from typing import Optional

from .confirmed_mapping_dto import (
    ConfirmedMappingDTO,
    MappingEntry,
    NormalizedMappingDTO,
    generate_canonical_headers,
    generate_sheet_key,
)
from .detection_types import SheetDetection

__all__ = [
    "SubmitGate",
    "SubmitGateError",
]


# ---------------------------------------------------------------------------
# 关键列定义（按 table_type，对齐 design §5 submit gate）
# ---------------------------------------------------------------------------

CRITICAL_COLUMNS: dict[str, list[set[str]]] = {
    "balance": [
        # account_code 必须，加上以下任一组合：
        # opening_balance OR closing_balance OR (debit_amount + credit_amount)
        {"account_code", "opening_balance"},
        {"account_code", "closing_balance"},
        {"account_code", "debit_amount", "credit_amount"},
    ],
    "ledger": [
        # voucher_date + account_code + (debit_amount OR credit_amount OR amount)
        {"voucher_date", "account_code", "debit_amount"},
        {"voucher_date", "account_code", "credit_amount"},
        {"voucher_date", "account_code", "amount"},
    ],
    "aux_balance": [
        # account_code + aux_dimension (至少 1)
        {"account_code", "aux_type"},
        {"account_code", "aux_code"},
        {"account_code", "aux_dimensions"},
    ],
    "aux_ledger": [
        # voucher_date + account_code + aux_dimension (至少 1)
        {"voucher_date", "account_code", "aux_type"},
        {"voucher_date", "account_code", "aux_code"},
        {"voucher_date", "account_code", "aux_dimensions"},
    ],
}


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class SubmitGateError(Exception):
    """Submit gate 校验失败，应返回 HTTP 400。"""

    def __init__(self, reason: str, details: Optional[dict] = None):
        self.reason = reason
        self.details = details or {}
        super().__init__(reason)


# ---------------------------------------------------------------------------
# SubmitGate
# ---------------------------------------------------------------------------


class SubmitGate:
    """Submit 阶段入口校验器。

    validate() 方法接收前端提交的 ConfirmedMappingDTO 和 detect artifact，
    校验通过后返回 NormalizedMappingDTO 供 pipeline 消费。
    """

    @staticmethod
    def validate(
        confirmed: ConfirmedMappingDTO,
        detect_artifact: SheetDetection,
    ) -> NormalizedMappingDTO:
        """校验并规范化前端提交的映射。

        校验规则（顺序执行，首个失败即返回）：
        1. sheet_key 与 detect artifact 匹配
        2. 低置信度且未人工确认 → BLOCK
        3. table_type="unknown" 且未被人工改类型 → BLOCK
        4. 关键列缺失 → BLOCK

        Returns:
            NormalizedMappingDTO — pipeline 唯一消费格式

        Raises:
            SubmitGateError — 校验失败，reason 和 details 描述具体原因
        """
        # --- 5.1: sheet_key 校验 ---
        expected_key = generate_sheet_key(
            detect_artifact.file_name, detect_artifact.sheet_name
        )
        if confirmed.sheet_key != expected_key:
            raise SubmitGateError(
                reason="sheet_key_mismatch",
                details={
                    "submitted": confirmed.sheet_key,
                    "expected": expected_key,
                },
            )

        # --- 5.4a: 低置信度未确认 ---
        if (
            detect_artifact.confidence_level in ("low", "manual_required")
            and not confirmed.confirmed_by_user
        ):
            raise SubmitGateError(
                reason="low_confidence_unconfirmed",
                details={
                    "confidence_level": detect_artifact.confidence_level,
                    "confirmed_by_user": False,
                },
            )

        # --- 5.4c: unknown 未改类型 ---
        if (
            confirmed.table_type == "unknown"
            and detect_artifact.table_type == "unknown"
        ):
            raise SubmitGateError(
                reason="unknown_type_unchanged",
                details={
                    "table_type": "unknown",
                    "message": "sheet 识别为 unknown 且用户未手动指定表类型",
                },
            )

        # --- 5.4b: 关键列缺失 ---
        mapped_fields = {
            entry.standard_field for entry in confirmed.mapping_entries
        }
        if not SubmitGate._has_critical_columns(confirmed.table_type, mapped_fields):
            required_alternatives = CRITICAL_COLUMNS.get(confirmed.table_type, [])
            raise SubmitGateError(
                reason="missing_critical_columns",
                details={
                    "table_type": confirmed.table_type,
                    "mapped_fields": sorted(mapped_fields),
                    "required_alternatives": [
                        sorted(alt) for alt in required_alternatives
                    ],
                },
            )

        # --- 全部通过，输出规范化 DTO ---
        return NormalizedMappingDTO(**confirmed.model_dump())

    @staticmethod
    def convert_legacy_format(
        legacy_mapping: dict[str, str],
        detect_artifact: SheetDetection,
    ) -> list[MappingEntry]:
        """兼容旧 {header: standard_field} 格式，转换为 mapping_entries[]。

        旧格式：{"科目编码": "account_code", "借方": "debit_amount", ...}
        需要从 detect artifact 的 column_mappings 获取原始列顺序（column_index）。

        Args:
            legacy_mapping: 旧格式 {original_header: standard_field}
            detect_artifact: detect 阶段产出的 SheetDetection

        Returns:
            list[MappingEntry] — 规范化的映射条目列表

        Raises:
            SubmitGateError — 无法转换（header 在 detect artifact 中找不到 column_index）
        """
        if not legacy_mapping:
            raise SubmitGateError(
                reason="legacy_format_empty",
                details={"message": "旧格式 mapping 为空"},
            )

        # 从 detect artifact 的 column_mappings 建 header→column_index 索引
        header_to_index: dict[str, int] = {}
        for cm in detect_artifact.column_mappings:
            header_to_index[cm.column_header] = cm.column_index

        # 收集原始表头列表用于 canonical header 生成
        # 只取 legacy_mapping 中涉及的表头（按 column_index 排序）
        entries_raw: list[tuple[int, str, str]] = []
        unconvertible: list[str] = []

        for header, std_field in legacy_mapping.items():
            if header in header_to_index:
                col_idx = header_to_index[header]
                entries_raw.append((col_idx, header, std_field))
            else:
                unconvertible.append(header)

        if unconvertible:
            raise SubmitGateError(
                reason="legacy_format_unconvertible",
                details={
                    "missing_headers": unconvertible,
                    "message": "旧格式中的表头在 detect artifact 中找不到对应 column_index",
                },
            )

        # 按 column_index 排序
        entries_raw.sort(key=lambda x: x[0])

        # 生成 canonical headers（处理重复）
        original_headers = [header for _, header, _ in entries_raw]
        canonical_headers = generate_canonical_headers(original_headers)

        # 构建 MappingEntry 列表
        result: list[MappingEntry] = []
        for i, (col_idx, header, std_field) in enumerate(entries_raw):
            result.append(
                MappingEntry(
                    column_index=col_idx,
                    original_header=header,
                    canonical_header=canonical_headers[i],
                    standard_field=std_field,
                )
            )

        return result

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _has_critical_columns(table_type: str, mapped_fields: set[str]) -> bool:
        """检查已映射字段是否满足该表类型的关键列要求。

        关键列要求为"或"关系：只要满足任一组合即可。
        account_chart 和 unknown 不做关键列校验。
        """
        alternatives = CRITICAL_COLUMNS.get(table_type, [])
        if not alternatives:
            # account_chart / unknown 不做关键列校验
            return True
        return any(alt.issubset(mapped_fields) for alt in alternatives)
