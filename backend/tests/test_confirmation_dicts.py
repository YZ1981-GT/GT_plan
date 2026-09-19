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
    # ── 源模板 DV 驱动的三个枚举（h0-confirmation-source-fidelity-and-linkage R7） ──
    "confirmation_send_channel",
    "confirmation_sample_purpose",
    "confirmation_addr_verify",
    "confirmation_subject",
]

EXPECTED_COUNTS = {
    # 13 → 22：追加 H 循环 9 个品种（R1.2，additive，原 13 项一字不动）
    "confirmation_account_type": 22,
    "confirmation_method": 2,
    # 4 → 7：追加源模板 X0-2!P7 的三个取值（R7.6）
    "confirmation_reply_method": 7,
    "yes_no": 2,
    "confirmation_match": 3,
    "sampling_method": 4,
    "confirmation_send_result": 2,
    "consistency_status": 3,
    "confirmation_followup_scenario": 2,
    "yes_no_na": 3,
    "confirmation_send_channel": 4,
    "confirmation_sample_purpose": 5,
    "confirmation_addr_verify": 6,
    # 13 → 22：追加 H 循环 9 个品种（R1.4）
    "confirmation_subject": 22,
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
        """所有函证枚举 key 都存在"""
        for key in CONFIRMATION_DICT_KEYS:
            assert key in _DICTS

    def test_send_channel_is_not_confirmation_method(self):
        """发函渠道与积极式/消极式是两个不同维度，两个枚举都必须存在且取值不重叠。

        源模板 X0-2!C7「函证方式」是发函渠道（邮寄/跟函/电子函证/其他），
        准则 1312 的积极式/消极式是程序层面概念（X0A 程序 1）。
        混用会让 X0-1 的「函证方式」列（VLOOKUP 自 X0-2!C）拿到错误维度的取值。
        """
        channel_labels = {e["label"] for e in _DICTS["confirmation_send_channel"]}
        method_labels = {e["label"] for e in _DICTS["confirmation_method"]}
        assert channel_labels == {"邮寄", "跟函", "电子函证", "其他"}
        assert method_labels == {"积极式", "消极式"}
        assert not (channel_labels & method_labels), "两个维度的取值不得重叠"
