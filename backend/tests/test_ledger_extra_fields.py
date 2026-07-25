"""Task 1.2: `_attach_extra_fields` 纯函数单测

覆盖 Correctness Properties（design.md）：
- Property 1: 系统标记（_ 前缀键）被过滤
- Property 2: 业务键值原样保序透出
- Property 3: None / 空 dict / 非 dict / 仅含 _ 前缀键 → extra_fields == {}，且不抛
- Property 4: 处理后行内不含 raw_extra 键
- Property 5: 既有固定字段名与取值不变

纯函数单测，直接 import `_attach_extra_fields`。
Validates: Requirements 6.1, 2.1, 1.5, 5.1
"""

from decimal import Decimal

from app.services.ledger_penetration_service import _attach_extra_fields


class TestProperty1SystemMarkersFiltered:
    """Property 1: 以 _ 开头的系统标记键必须被过滤。"""

    def test_discarded_mappings_filtered(self):
        rows = [{"id": 1, "raw_extra": {"经办人": "张三", "_discarded_mappings": {"x": 1}}}]
        out = _attach_extra_fields(rows)
        assert out[0]["extra_fields"] == {"经办人": "张三"}

    def test_all_known_system_markers_filtered(self):
        rows = [{
            "id": 1,
            "raw_extra": {
                "内部编号": "A-001",
                "_discarded_mappings": {"a": 1},
                "_aggregated_from_aux": True,
                "_aux_row_count": 5,
            },
        }]
        out = _attach_extra_fields(rows)
        assert out[0]["extra_fields"] == {"内部编号": "A-001"}
        for k in out[0]["extra_fields"]:
            assert not k.startswith("_")

    def test_future_underscore_marker_filtered(self):
        rows = [{"id": 1, "raw_extra": {"备注": "x", "_future_flag": "any"}}]
        out = _attach_extra_fields(rows)
        assert "_future_flag" not in out[0]["extra_fields"]
        assert out[0]["extra_fields"] == {"备注": "x"}


class TestProperty2BusinessKeysPreservedInOrder:
    """Property 2: 业务键值原样保留、保持 dict 迭代顺序。"""

    def test_values_preserved_verbatim(self):
        rows = [{
            "id": 1,
            "raw_extra": {"备注": "现金收讫", "金额备注": Decimal("100.50"), "数量": 3},
        }]
        out = _attach_extra_fields(rows)
        ef = out[0]["extra_fields"]
        assert ef["备注"] == "现金收讫"
        assert ef["金额备注"] == Decimal("100.50")
        assert ef["数量"] == 3

    def test_iteration_order_preserved(self):
        raw = {"列C": 3, "列A": 1, "_sys": "x", "列B": 2}
        rows = [{"id": 1, "raw_extra": raw}]
        out = _attach_extra_fields(rows)
        # 过滤 _sys 后保持 raw_extra 原插入序：C, A, B
        assert list(out[0]["extra_fields"].keys()) == ["列C", "列A", "列B"]


class TestProperty3EmptyAndNullSafe:
    """Property 3: None / 空 dict / 非 dict / 仅系统键 → {}，不抛。"""

    def test_none_raw_extra(self):
        rows = [{"id": 1, "raw_extra": None}]
        out = _attach_extra_fields(rows)
        assert out[0]["extra_fields"] == {}

    def test_missing_raw_extra_key(self):
        rows = [{"id": 1}]  # 无 raw_extra 键
        out = _attach_extra_fields(rows)
        assert out[0]["extra_fields"] == {}

    def test_empty_dict(self):
        rows = [{"id": 1, "raw_extra": {}}]
        out = _attach_extra_fields(rows)
        assert out[0]["extra_fields"] == {}

    def test_non_dict_string(self):
        rows = [{"id": 1, "raw_extra": "some string"}]
        out = _attach_extra_fields(rows)
        assert out[0]["extra_fields"] == {}

    def test_non_dict_list(self):
        rows = [{"id": 1, "raw_extra": ["a", "b"]}]
        out = _attach_extra_fields(rows)
        assert out[0]["extra_fields"] == {}

    def test_only_system_keys(self):
        rows = [{"id": 1, "raw_extra": {"_discarded_mappings": {}, "_aux_row_count": 2}}]
        out = _attach_extra_fields(rows)
        assert out[0]["extra_fields"] == {}


class TestProperty4RawExtraKeyRemoved:
    """Property 4: 处理后行内不含原始 raw_extra 键。"""

    def test_raw_extra_removed_when_present(self):
        rows = [{"id": 1, "raw_extra": {"备注": "x"}}]
        out = _attach_extra_fields(rows)
        assert "raw_extra" not in out[0]

    def test_raw_extra_removed_when_none(self):
        rows = [{"id": 1, "raw_extra": None}]
        out = _attach_extra_fields(rows)
        assert "raw_extra" not in out[0]

    def test_no_raw_extra_key_stays_absent(self):
        rows = [{"id": 1}]
        out = _attach_extra_fields(rows)
        assert "raw_extra" not in out[0]


class TestProperty5FixedFieldsUnchanged:
    """Property 5: 既有固定字段名与取值完全不变。"""

    def test_fixed_fields_preserved(self):
        rows = [{
            "id": 42,
            "voucher_no": "记-0001",
            "account_code": "1002",
            "account_name": "银行存款",
            "debit_amount": Decimal("40000"),
            "credit_amount": Decimal("0"),
            "summary": "收款",
            "counterpart_account": "1122",
            "preparer": "李四",
            "raw_extra": {"经办人": "王五", "_discarded_mappings": {}},
        }]
        out = _attach_extra_fields(rows)
        row = out[0]
        assert row["id"] == 42
        assert row["voucher_no"] == "记-0001"
        assert row["account_code"] == "1002"
        assert row["account_name"] == "银行存款"
        assert row["debit_amount"] == Decimal("40000")
        assert row["credit_amount"] == Decimal("0")
        assert row["summary"] == "收款"
        assert row["counterpart_account"] == "1122"
        assert row["preparer"] == "李四"
        assert row["extra_fields"] == {"经办人": "王五"}


class TestHelperContract:
    """辅助契约：就地修改并返回同一列表；同输入同输出（Property 7 口径）。"""

    def test_returns_same_list_object(self):
        rows = [{"id": 1, "raw_extra": {"a": 1}}]
        out = _attach_extra_fields(rows)
        assert out is rows  # 就地修改，返回同一对象

    def test_empty_list(self):
        assert _attach_extra_fields([]) == []

    def test_multiple_rows(self):
        rows = [
            {"id": 1, "raw_extra": {"备注": "a", "_x": 1}},
            {"id": 2, "raw_extra": None},
            {"id": 3, "raw_extra": {"_only": 1}},
        ]
        out = _attach_extra_fields(rows)
        assert out[0]["extra_fields"] == {"备注": "a"}
        assert out[1]["extra_fields"] == {}
        assert out[2]["extra_fields"] == {}

    def test_deterministic_same_input_same_output(self):
        def make():
            return [{"id": 1, "raw_extra": {"k": "v", "_s": 1}}]
        out1 = _attach_extra_fields(make())
        out2 = _attach_extra_fields(make())
        assert out1 == out2
