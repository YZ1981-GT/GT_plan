"""Tests for backend/app/services/e0_send_list/send_list_specs.py"""

import pytest

from app.services.e0_send_list.send_list_specs import (
    ALL_SHEETS,
    FORMAT_VERSION,
    SHEET_E03,
    SHEET_E04,
    SHEET_E05,
    SHEET_E06,
    column_map,
    fields,
)


class TestFormatVersion:
    def test_has_all_four_entries(self):
        assert len(FORMAT_VERSION) == 4

    def test_keys_are_all_sheets(self):
        assert set(FORMAT_VERSION.keys()) == set(ALL_SHEETS)

    def test_values_follow_pattern(self):
        for sheet, version in FORMAT_VERSION.items():
            assert version.startswith("send-list-e0")
            assert version.endswith("-v1")


class TestColumnMap:
    @pytest.mark.parametrize("sheet", ALL_SHEETS)
    def test_returns_dict(self, sheet: str):
        result = column_map(sheet)
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_e03_has_16_columns(self):
        result = column_map(SHEET_E03)
        assert len(result) == 16

    def test_e03_first_column_is_account_subject(self):
        result = column_map(SHEET_E03)
        assert result["A"] == "account_subject"

    def test_e04_has_16_columns(self):
        result = column_map(SHEET_E04)
        assert len(result) == 16

    def test_e05_has_10_columns(self):
        result = column_map(SHEET_E05)
        assert len(result) == 10

    def test_e06_has_11_columns(self):
        result = column_map(SHEET_E06)
        assert len(result) == 11

    def test_keys_are_uppercase_letters(self):
        for sheet in ALL_SHEETS:
            for key in column_map(sheet):
                assert key.isalpha() and key.isupper()

    def test_values_are_snake_case(self):
        for sheet in ALL_SHEETS:
            for val in column_map(sheet).values():
                assert val == val.lower()
                assert " " not in val


class TestFields:
    @pytest.mark.parametrize("sheet", ALL_SHEETS)
    def test_returns_list(self, sheet: str):
        result = fields(sheet)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_e03_fields_ordered(self):
        result = fields(SHEET_E03)
        assert result[0] == "account_subject"
        assert result[-1] == "remark"

    def test_fields_match_column_map_values(self):
        for sheet in ALL_SHEETS:
            cm = column_map(sheet)
            f = fields(sheet)
            assert f == list(cm.values())

    def test_e04_first_field(self):
        result = fields(SHEET_E04)
        assert result[0] == "account_subject"

    def test_e05_first_field(self):
        result = fields(SHEET_E05)
        assert result[0] == "index_no"

    def test_e06_first_field(self):
        result = fields(SHEET_E06)
        assert result[0] == "index_no"

    @pytest.mark.parametrize("sheet", ALL_SHEETS)
    def test_no_duplicates(self, sheet: str):
        result = fields(sheet)
        assert len(result) == len(set(result))
