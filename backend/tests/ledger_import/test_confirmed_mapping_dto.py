"""ConfirmedMappingDTO / NormalizedMappingDTO 契约测试。

验证：
- 后端 DTO 序列化输出与前端类型字段名一致
- 枚举值匹配
- generate_sheet_key / generate_canonical_headers 行为正确
- golden JSON fixture 保证前后端字段名不漂移
"""

import json

import pytest
from pydantic import ValidationError

from backend.app.services.ledger_import.confirmed_mapping_dto import (
    ConfirmedMappingDTO,
    MappingEntry,
    NormalizedMappingDTO,
    generate_canonical_headers,
    generate_detection_id,
    generate_sheet_key,
    validate_sheet_key_matches,
)

# ---------------------------------------------------------------------------
# Golden fixture — 前后端字段名对齐的单一真源
# ---------------------------------------------------------------------------

GOLDEN_FIXTURE = {
    "detection_id": "abc-123",
    "sheet_key": "用友余额表.xlsx:Sheet1",
    "file_name": "用友余额表.xlsx",
    "sheet_name": "Sheet1",
    "table_type": "balance",
    "mapping_entries": [
        {
            "column_index": 0,
            "original_header": "科目编码",
            "canonical_header": "科目编码",
            "standard_field": "account_code",
        },
        {
            "column_index": 1,
            "original_header": "科目名称",
            "canonical_header": "科目名称",
            "standard_field": "account_name",
        },
        {
            "column_index": 2,
            "original_header": "借方",
            "canonical_header": "借方#2",
            "standard_field": "debit_amount",
        },
        {
            "column_index": 3,
            "original_header": "借方",
            "canonical_header": "借方#3",
            "standard_field": "opening_debit",
        },
    ],
    "aux_dimension_columns": [5, 6],
    "file_fingerprint": "sha256:abc123",
    "software_fingerprint": "yonyou-u8",
    "confirmed_by_user": True,
}


class TestGoldenFixture:
    """Golden fixture 字段对齐测试。"""

    def test_confirmed_mapping_dto_from_fixture(self):
        """后端 DTO 能够解析 golden fixture JSON。"""
        dto = ConfirmedMappingDTO(**GOLDEN_FIXTURE)
        assert dto.file_name == "用友余额表.xlsx"
        assert dto.sheet_name == "Sheet1"
        assert dto.table_type == "balance"
        assert len(dto.mapping_entries) == 4
        assert dto.mapping_entries[0].column_index == 0
        assert dto.mapping_entries[0].standard_field == "account_code"

    def test_normalized_mapping_dto_from_fixture(self):
        """NormalizedMappingDTO 也能解析相同 fixture（继承）。"""
        dto = NormalizedMappingDTO(**GOLDEN_FIXTURE)
        assert dto.sheet_key == "用友余额表.xlsx:Sheet1"
        assert dto.confirmed_by_user is True

    def test_serialization_field_names_match_frontend(self):
        """序列化输出的字段名必须与前端 TypeScript 类型一致。"""
        dto = ConfirmedMappingDTO(**GOLDEN_FIXTURE)
        serialized = json.loads(dto.model_dump_json())

        # 顶层字段
        expected_top_fields = {
            "detection_id",
            "sheet_key",
            "file_name",
            "sheet_name",
            "table_type",
            "mapping_entries",
            "aux_dimension_columns",
            "file_fingerprint",
            "software_fingerprint",
            "confirmed_by_user",
        }
        assert set(serialized.keys()) == expected_top_fields

        # MappingEntry 字段
        entry = serialized["mapping_entries"][0]
        expected_entry_fields = {
            "column_index",
            "original_header",
            "canonical_header",
            "standard_field",
        }
        assert set(entry.keys()) == expected_entry_fields

    def test_table_type_enum_values(self):
        """所有合法 table_type 值都能通过验证。"""
        valid_types = ["balance", "ledger", "aux_balance", "aux_ledger", "account_chart"]
        for tt in valid_types:
            fixture = {**GOLDEN_FIXTURE, "table_type": tt}
            dto = ConfirmedMappingDTO(**fixture)
            assert dto.table_type == tt

    def test_invalid_table_type_rejected(self):
        """非法 table_type 被拒绝。"""
        fixture = {**GOLDEN_FIXTURE, "table_type": "invalid_type"}
        with pytest.raises(ValidationError):
            ConfirmedMappingDTO(**fixture)


class TestMappingEntry:
    """MappingEntry 模型测试。"""

    def test_valid_entry(self):
        entry = MappingEntry(
            column_index=0,
            original_header="借方",
            canonical_header="借方#0",
            standard_field="debit_amount",
        )
        assert entry.column_index == 0
        assert entry.original_header == "借方"

    def test_negative_column_index_rejected(self):
        """column_index 不能为负数。"""
        with pytest.raises(ValidationError):
            MappingEntry(
                column_index=-1,
                original_header="借方",
                canonical_header="借方",
                standard_field="debit_amount",
            )

    def test_extra_fields_rejected(self):
        """extra='forbid' 阻止未知字段。"""
        with pytest.raises(ValidationError):
            MappingEntry(
                column_index=0,
                original_header="借方",
                canonical_header="借方",
                standard_field="debit_amount",
                unknown_field="oops",
            )


class TestGenerateSheetKey:
    """generate_sheet_key 测试。"""

    def test_basic(self):
        assert generate_sheet_key("file.xlsx", "Sheet1") == "file.xlsx:Sheet1"

    def test_chinese_names(self):
        assert generate_sheet_key("用友余额表.xlsx", "余额") == "用友余额表.xlsx:余额"

    def test_empty_sheet_name(self):
        assert generate_sheet_key("file.xlsx", "") == "file.xlsx:"


class TestGenerateCanonicalHeaders:
    """generate_canonical_headers 测试。"""

    def test_no_duplicates(self):
        headers = ["科目编码", "科目名称", "借方", "贷方"]
        result = generate_canonical_headers(headers)
        assert result == ["科目编码", "科目名称", "借方", "贷方"]

    def test_duplicate_headers_get_suffix(self):
        headers = ["借方", "贷方", "借方", "借方"]
        result = generate_canonical_headers(headers)
        assert result == ["借方#0", "贷方", "借方#2", "借方#3"]

    def test_mixed_duplicates(self):
        headers = ["期末余额.借方", "期末余额.贷方", "借方", "借方"]
        result = generate_canonical_headers(headers)
        assert result == ["期末余额.借方", "期末余额.贷方", "借方#2", "借方#3"]

    def test_all_same(self):
        headers = ["金额", "金额", "金额"]
        result = generate_canonical_headers(headers)
        assert result == ["金额#0", "金额#1", "金额#2"]

    def test_empty_list(self):
        assert generate_canonical_headers([]) == []


class TestConfirmedMappingDTOValidation:
    """ConfirmedMappingDTO 校验规则测试。"""

    def test_empty_mapping_entries_rejected(self):
        """mapping_entries 不能为空列表。"""
        fixture = {**GOLDEN_FIXTURE, "mapping_entries": []}
        with pytest.raises(ValidationError):
            ConfirmedMappingDTO(**fixture)

    def test_optional_fields_default(self):
        """可选字段有合理默认值。"""
        minimal = {
            "sheet_key": "f.xlsx:S1",
            "file_name": "f.xlsx",
            "sheet_name": "S1",
            "table_type": "ledger",
            "mapping_entries": [
                {
                    "column_index": 0,
                    "original_header": "日期",
                    "canonical_header": "日期",
                    "standard_field": "voucher_date",
                }
            ],
        }
        dto = ConfirmedMappingDTO(**minimal)
        assert dto.detection_id is None
        assert dto.aux_dimension_columns == []
        assert dto.file_fingerprint is None
        assert dto.software_fingerprint is None
        assert dto.confirmed_by_user is False


class TestGenerateDetectionId:
    """generate_detection_id 测试。"""

    def test_basic(self):
        did = generate_detection_id("tok-123", "file.xlsx", "Sheet1")
        assert did == "tok-123::file.xlsx:Sheet1"

    def test_chinese(self):
        did = generate_detection_id("tok-abc", "用友.xlsx", "余额表")
        assert did == "tok-abc::用友.xlsx:余额表"

    def test_uniqueness(self):
        """不同 upload_token 产生不同 detection_id。"""
        id1 = generate_detection_id("tok-1", "f.xlsx", "S1")
        id2 = generate_detection_id("tok-2", "f.xlsx", "S1")
        assert id1 != id2


class TestValidateSheetKeyMatches:
    """validate_sheet_key_matches 测试。"""

    def test_match(self):
        assert validate_sheet_key_matches("f.xlsx:S1", "f.xlsx", "S1") is True

    def test_mismatch_file(self):
        assert validate_sheet_key_matches("other.xlsx:S1", "f.xlsx", "S1") is False

    def test_mismatch_sheet(self):
        assert validate_sheet_key_matches("f.xlsx:S2", "f.xlsx", "S1") is False

    def test_chinese_match(self):
        assert validate_sheet_key_matches(
            "用友余额表.xlsx:Sheet1", "用友余额表.xlsx", "Sheet1"
        ) is True
