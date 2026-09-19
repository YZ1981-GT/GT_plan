"""Submit Gate 校验测试。

覆盖 Task 5.1 ~ 5.7：
- 5.1: sheet_key 不匹配 → SubmitGateError
- 5.2: 旧格式 {header: field} 转换为 mapping_entries[]
- 5.3: 无法转换旧格式 → SubmitGateError
- 5.4: 低置信度未确认 / 关键列缺失 / unknown 未改类型 → BLOCK
- 5.5: NormalizedMappingDTO 输出结构正确
- 5.7: 重复"借方/贷方/金额"表头都能保留并正确映射
"""

import pytest

from app.services.ledger_import.submit_gate import (
    SubmitGate,
    SubmitGateError,
)
from app.services.ledger_import.confirmed_mapping_dto import (
    ConfirmedMappingDTO,
    MappingEntry,
    NormalizedMappingDTO,
    generate_canonical_headers,
)
from app.services.ledger_import.detection_types import (
    ColumnMatch,
    SheetDetection,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sheet_detection(
    file_name: str = "test.xlsx",
    sheet_name: str = "Sheet1",
    table_type: str = "balance",
    confidence_level: str = "high",
    table_type_confidence: int = 90,
    headers: list[str] | None = None,
) -> SheetDetection:
    """Build a SheetDetection fixture."""
    column_mappings = []
    for i, h in enumerate(headers or ["科目编码", "科目名称", "借方", "贷方"]):
        column_mappings.append(
            ColumnMatch(
                column_index=i,
                column_header=h,
                standard_field=None,
                column_tier="extra",
                confidence=50,
                source="header_exact",
            )
        )
    return SheetDetection(
        file_name=file_name,
        sheet_name=sheet_name,
        row_count_estimate=100,
        header_row_index=0,
        data_start_row=1,
        table_type=table_type,
        table_type_confidence=table_type_confidence,
        confidence_level=confidence_level,
        column_mappings=column_mappings,
        preview_rows=[],
        detection_evidence={},
    )


def _make_confirmed_dto(
    file_name: str = "test.xlsx",
    sheet_name: str = "Sheet1",
    table_type: str = "balance",
    confirmed_by_user: bool = True,
    entries: list[MappingEntry] | None = None,
) -> ConfirmedMappingDTO:
    """Build a ConfirmedMappingDTO fixture."""
    if entries is None:
        entries = [
            MappingEntry(column_index=0, original_header="科目编码", canonical_header="科目编码", standard_field="account_code"),
            MappingEntry(column_index=2, original_header="借方", canonical_header="借方", standard_field="debit_amount"),
            MappingEntry(column_index=3, original_header="贷方", canonical_header="贷方", standard_field="credit_amount"),
        ]
    return ConfirmedMappingDTO(
        sheet_key=f"{file_name}:{sheet_name}",
        file_name=file_name,
        sheet_name=sheet_name,
        table_type=table_type,
        mapping_entries=entries,
        confirmed_by_user=confirmed_by_user,
    )


# ---------------------------------------------------------------------------
# 5.1: sheet_key 校验
# ---------------------------------------------------------------------------


class TestSheetKeyValidation:
    """5.1 submit 入口校验 sheet key。"""

    def test_matching_sheet_key_passes(self):
        """sheet_key 匹配时通过。"""
        artifact = _make_sheet_detection()
        dto = _make_confirmed_dto()
        result = SubmitGate.validate(dto, artifact)
        assert isinstance(result, NormalizedMappingDTO)

    def test_mismatched_sheet_key_blocked(self):
        """sheet_key 不匹配时阻断。"""
        artifact = _make_sheet_detection(file_name="real.xlsx")
        dto = _make_confirmed_dto(file_name="fake.xlsx")
        with pytest.raises(SubmitGateError) as exc_info:
            SubmitGate.validate(dto, artifact)
        assert exc_info.value.reason == "sheet_key_mismatch"


# ---------------------------------------------------------------------------
# 5.2: 旧格式转换
# ---------------------------------------------------------------------------


class TestLegacyFormatConversion:
    """5.2 兼容旧 {header: field} 格式。"""

    def test_legacy_format_converts_successfully(self):
        """旧格式能正确转换为 mapping_entries。"""
        artifact = _make_sheet_detection(
            headers=["科目编码", "科目名称", "借方", "贷方"]
        )
        legacy = {"科目编码": "account_code", "借方": "debit_amount", "贷方": "credit_amount"}
        entries = SubmitGate.convert_legacy_format(legacy, artifact)
        assert len(entries) == 3
        assert entries[0].column_index == 0
        assert entries[0].standard_field == "account_code"
        assert entries[1].column_index == 2
        assert entries[1].standard_field == "debit_amount"

    def test_legacy_format_preserves_column_order(self):
        """转换结果按 column_index 排序。"""
        artifact = _make_sheet_detection(headers=["A", "B", "C"])
        legacy = {"C": "field_c", "A": "field_a"}
        entries = SubmitGate.convert_legacy_format(legacy, artifact)
        assert entries[0].column_index == 0  # A
        assert entries[1].column_index == 2  # C


# ---------------------------------------------------------------------------
# 5.3: 无法转换旧格式
# ---------------------------------------------------------------------------


class TestLegacyFormatUnconvertible:
    """5.3 无法转换旧格式时返回 400。"""

    def test_header_not_in_artifact_blocked(self):
        """旧格式中的 header 不在 detect artifact 中 → 阻断。"""
        artifact = _make_sheet_detection(headers=["科目编码", "借方"])
        legacy = {"不存在的列": "account_code"}
        with pytest.raises(SubmitGateError) as exc_info:
            SubmitGate.convert_legacy_format(legacy, artifact)
        assert exc_info.value.reason == "legacy_format_unconvertible"
        assert "不存在的列" in exc_info.value.details["missing_headers"]

    def test_empty_legacy_mapping_blocked(self):
        """空旧格式 → 阻断。"""
        artifact = _make_sheet_detection()
        with pytest.raises(SubmitGateError) as exc_info:
            SubmitGate.convert_legacy_format({}, artifact)
        assert exc_info.value.reason == "legacy_format_empty"


# ---------------------------------------------------------------------------
# 5.4: 阻断条件
# ---------------------------------------------------------------------------


class TestSubmitGateBlocking:
    """5.4 低置信度未确认 / 关键列缺失 / unknown 未改类型。"""

    def test_low_confidence_unconfirmed_blocked(self):
        """低置信度且未人工确认 → 阻断。"""
        artifact = _make_sheet_detection(confidence_level="low")
        dto = _make_confirmed_dto(confirmed_by_user=False)
        with pytest.raises(SubmitGateError) as exc_info:
            SubmitGate.validate(dto, artifact)
        assert exc_info.value.reason == "low_confidence_unconfirmed"

    def test_low_confidence_confirmed_passes(self):
        """低置信度但已人工确认 → 通过。"""
        artifact = _make_sheet_detection(confidence_level="low")
        dto = _make_confirmed_dto(confirmed_by_user=True)
        result = SubmitGate.validate(dto, artifact)
        assert isinstance(result, NormalizedMappingDTO)

    def test_unknown_type_unchanged_blocked(self):
        """unknown 类型未被用户改变 → 阻断。"""
        artifact = _make_sheet_detection(table_type="unknown", confidence_level="high")
        dto = _make_confirmed_dto(table_type="unknown")
        with pytest.raises(SubmitGateError) as exc_info:
            SubmitGate.validate(dto, artifact)
        assert exc_info.value.reason == "unknown_type_unchanged"

    def test_unknown_changed_to_balance_passes(self):
        """unknown 被用户改为 balance → 通过（有关键列时）。"""
        artifact = _make_sheet_detection(table_type="unknown", confidence_level="high")
        dto = _make_confirmed_dto(table_type="balance")
        result = SubmitGate.validate(dto, artifact)
        assert isinstance(result, NormalizedMappingDTO)

    def test_missing_critical_columns_blocked(self):
        """关键列缺失 → 阻断。"""
        artifact = _make_sheet_detection()
        # 只有 account_code，缺少金额列
        entries = [
            MappingEntry(column_index=0, original_header="科目编码", canonical_header="科目编码", standard_field="account_code"),
        ]
        dto = _make_confirmed_dto(entries=entries)
        with pytest.raises(SubmitGateError) as exc_info:
            SubmitGate.validate(dto, artifact)
        assert exc_info.value.reason == "missing_critical_columns"

    def test_balance_with_opening_balance_passes(self):
        """balance 类型有 account_code + opening_balance → 关键列满足。"""
        artifact = _make_sheet_detection()
        entries = [
            MappingEntry(column_index=0, original_header="科目编码", canonical_header="科目编码", standard_field="account_code"),
            MappingEntry(column_index=1, original_header="期初余额", canonical_header="期初余额", standard_field="opening_balance"),
        ]
        dto = _make_confirmed_dto(entries=entries)
        result = SubmitGate.validate(dto, artifact)
        assert isinstance(result, NormalizedMappingDTO)


# ---------------------------------------------------------------------------
# 5.5: NormalizedMappingDTO 结构
# ---------------------------------------------------------------------------


class TestNormalizedOutput:
    """5.5 pipeline 只消费规范化 DTO。"""

    def test_output_is_normalized_dto(self):
        """validate 输出为 NormalizedMappingDTO 实例。"""
        artifact = _make_sheet_detection()
        dto = _make_confirmed_dto()
        result = SubmitGate.validate(dto, artifact)
        assert isinstance(result, NormalizedMappingDTO)
        assert result.file_name == "test.xlsx"
        assert len(result.mapping_entries) == 3

    def test_output_preserves_all_entries(self):
        """所有 mapping_entries 保留。"""
        artifact = _make_sheet_detection()
        dto = _make_confirmed_dto()
        result = SubmitGate.validate(dto, artifact)
        fields = {e.standard_field for e in result.mapping_entries}
        assert "account_code" in fields
        assert "debit_amount" in fields
        assert "credit_amount" in fields


# ---------------------------------------------------------------------------
# 5.7: 重复表头保留
# ---------------------------------------------------------------------------


class TestDuplicateHeadersPreserved:
    """5.7 重复"借方/贷方/金额"表头都能保留并正确映射。"""

    def test_duplicate_debit_headers_all_preserved(self):
        """多个"借方"表头各有独立 canonical_header 和 column_index。"""
        artifact = _make_sheet_detection(
            headers=["科目编码", "借方", "借方", "贷方", "贷方"]
        )
        entries = [
            MappingEntry(column_index=0, original_header="科目编码", canonical_header="科目编码", standard_field="account_code"),
            MappingEntry(column_index=1, original_header="借方", canonical_header="借方#1", standard_field="debit_amount"),
            MappingEntry(column_index=2, original_header="借方", canonical_header="借方#2", standard_field="opening_debit"),
            MappingEntry(column_index=3, original_header="贷方", canonical_header="贷方#3", standard_field="credit_amount"),
            MappingEntry(column_index=4, original_header="贷方", canonical_header="贷方#4", standard_field="opening_credit"),
        ]
        dto = _make_confirmed_dto(entries=entries)
        result = SubmitGate.validate(dto, artifact)

        assert len(result.mapping_entries) == 5
        # 每个 column_index 唯一
        indexes = [e.column_index for e in result.mapping_entries]
        assert len(set(indexes)) == 5
        # 每个 canonical_header 唯一
        canonicals = [e.canonical_header for e in result.mapping_entries]
        assert len(set(canonicals)) == 5

    def test_legacy_duplicate_headers_converted(self):
        """旧格式有重复表头时通过 canonical_header 区分。"""
        # 用 generate_canonical_headers 验证
        headers = ["借方", "贷方", "借方", "金额"]
        canonical = generate_canonical_headers(headers)
        assert canonical == ["借方#0", "贷方", "借方#2", "金额"]
        assert len(set(canonical)) == 4
