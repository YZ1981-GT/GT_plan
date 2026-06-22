"""
test_confirmation_dicts.py — 验证函证模块枚举完整性
"""
import pytest
from app.routers.system_dicts import _DICTS

CONFIRMATION_DICT_KEYS = [
    "confirmation_account_type",
    "confirmation_method",
    "confirmation_reply_method",
    "yes_no",
    "confirmation_match",
    "sampling_method",
    "confirmation_send_result",
    "consistency_status",
    "confirmation_followup_scenario",
    "yes_no_na",
]

EXPECTED_COUNTS = {
    "confirmation_account_type": 13,
    "confirmation_method": 2,
    "confirmation_reply_method": 4,
    "yes_no": 2,
    "confirmation_match": 3,
    "sampling_method": 4,
    "confirmation_send_result": 2,
    "consistency_status": 3,
    "confirmation_followup_scenario": 2,
    "yes_no_na": 3,
}


class TestConfirmationDicts:
    """函证枚举字典完整性测试"""

    @pytest.mark.parametrize("dict_key", CONFIRMATION_DICT_KEYS)
    def test_dict_key_exists(self, dict_key: str):
        """各 dict_key 在 _DICTS 中存在"""
        assert dict_key in _DICTS, f"Missing dict key: {dict_key}"

    @pytest.mark.parametrize("dict_key", CONFIRMATION_DICT_KEYS)
    def test_dict_entry_count(self, dict_key: str):
        """各 dict_key 的条目数量正确"""
        entries = _DICTS[dict_key]
        expected = EXPECTED_COUNTS[dict_key]
        assert len(entries) == expected, f"{dict_key}: expected {expected}, got {len(entries)}"

    @pytest.mark.parametrize("dict_key", CONFIRMATION_DICT_KEYS)
    def test_dict_entries_have_required_fields(self, dict_key: str):
        """每个条目都有 value/label/color 字段"""
        for entry in _DICTS[dict_key]:
            assert "value" in entry, f"{dict_key}: missing 'value'"
            assert "label" in entry, f"{dict_key}: missing 'label'"
            assert "color" in entry, f"{dict_key}: missing 'color'"

    @pytest.mark.parametrize("dict_key", CONFIRMATION_DICT_KEYS)
    def test_dict_values_unique(self, dict_key: str):
        """各 dict_key 内 value 唯一"""
        values = [e["value"] for e in _DICTS[dict_key]]
        assert len(values) == len(set(values)), f"{dict_key}: duplicate values found"

    def test_all_confirmation_dicts_present(self):
        """所有 10 个函证枚举 key 都存在"""
        for key in CONFIRMATION_DICT_KEYS:
            assert key in _DICTS
