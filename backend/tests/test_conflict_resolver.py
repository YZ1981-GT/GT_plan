"""单元测试 — ConflictResolver (Task 3.1)

验证三种冲突策略的语义正确性：
- overwrite: 全量替换 item_id 行数据（Req 8.1）
- fill-empty: 仅写空位不覆盖非空（Req 8.2）
- reject: 目标非空则抛 ConflictRejected（Req 8.3）

以及辅助函数 is_field_empty / is_row_empty / has_non_empty_data。

Requirements: 8.1, 8.2, 8.3, 8.4
"""
import pytest

from app.services.bulk_tab.conflict_resolver import (
    ConflictRejected,
    has_non_empty_data,
    is_field_empty,
    is_row_empty,
    resolve_conflict,
)


# ---------------------------------------------------------------------------
# Tests: is_field_empty
# ---------------------------------------------------------------------------


class TestIsFieldEmpty:
    """is_field_empty 判断单字段是否为空。"""

    def test_none_is_empty(self):
        assert is_field_empty(None) is True

    def test_empty_string_is_empty(self):
        assert is_field_empty("") is True

    def test_whitespace_only_is_empty(self):
        assert is_field_empty("   ") is True
        assert is_field_empty("\t\n") is True

    def test_non_empty_string(self):
        assert is_field_empty("已核") is False
        assert is_field_empty("Y") is False

    def test_zero_is_not_empty(self):
        """0 有业务语义（如金额），不视为空。"""
        assert is_field_empty(0) is False

    def test_false_is_not_empty(self):
        """False 有业务语义，不视为空。"""
        assert is_field_empty(False) is False

    def test_list_is_not_empty(self):
        assert is_field_empty([]) is False
        assert is_field_empty([1, 2]) is False


# ---------------------------------------------------------------------------
# Tests: is_row_empty
# ---------------------------------------------------------------------------


class TestIsRowEmpty:
    """is_row_empty 判断整行是否全空。"""

    def test_empty_dict_is_empty(self):
        assert is_row_empty({}) is True

    def test_all_none_is_empty(self):
        assert is_row_empty({"conclusion": None, "remark": None, "wp_ref": None}) is True

    def test_all_empty_strings_is_empty(self):
        assert is_row_empty({"conclusion": "", "remark": "  ", "wp_ref": ""}) is True

    def test_one_non_empty_field(self):
        assert is_row_empty({"conclusion": "Y", "remark": None, "wp_ref": None}) is False

    def test_zero_value_makes_row_non_empty(self):
        assert is_row_empty({"amount": 0, "remark": None}) is False


# ---------------------------------------------------------------------------
# Tests: has_non_empty_data
# ---------------------------------------------------------------------------


class TestHasNonEmptyData:
    """has_non_empty_data 检查哪些 item_id 有非空数据。"""

    def test_all_empty(self):
        data = {
            "item-1": {"conclusion": None, "remark": ""},
            "item-2": {"conclusion": "", "remark": None},
        }
        assert has_non_empty_data(data) == []

    def test_some_non_empty(self):
        data = {
            "item-1": {"conclusion": "Y", "remark": "已核"},
            "item-2": {"conclusion": None, "remark": ""},
            "item-3": {"conclusion": "N", "remark": None},
        }
        result = has_non_empty_data(data)
        assert "item-1" in result
        assert "item-3" in result
        assert "item-2" not in result

    def test_empty_data(self):
        assert has_non_empty_data({}) == []


# ---------------------------------------------------------------------------
# Tests: resolve_conflict — overwrite strategy
# ---------------------------------------------------------------------------


class TestResolveConflictOverwrite:
    """overwrite 策略：全量替换（Req 8.1）。"""

    def test_basic_overwrite(self):
        """incoming 完全替换 existing 中对应 item_id。"""
        existing = {
            "row-1": {"conclusion": "Y", "remark": "旧备注"},
            "row-2": {"conclusion": "N", "remark": "保留"},
        }
        incoming = {
            "row-1": {"conclusion": "N", "remark": "新备注"},
        }
        result = resolve_conflict(existing, incoming, "overwrite")

        # row-1 被完全替换
        assert result["row-1"] == {"conclusion": "N", "remark": "新备注"}
        # row-2 不在 incoming 中 → 不出现在 resolved（不删除由调用方决定）
        assert "row-2" not in result

    def test_overwrite_adds_new_items(self):
        """incoming 中有 existing 不存在的 item_id → 新增。"""
        existing = {"row-1": {"conclusion": "Y"}}
        incoming = {
            "row-1": {"conclusion": "N"},
            "row-new": {"conclusion": "NA", "remark": "新行"},
        }
        result = resolve_conflict(existing, incoming, "overwrite")
        assert result["row-1"] == {"conclusion": "N"}
        assert result["row-new"] == {"conclusion": "NA", "remark": "新行"}

    def test_overwrite_empty_incoming(self):
        """incoming 为空 → resolved 也为空（不删除 existing）。"""
        existing = {"row-1": {"conclusion": "Y"}}
        result = resolve_conflict(existing, {}, "overwrite")
        assert result == {}

    def test_overwrite_replaces_with_empty_values(self):
        """overwrite 允许用空值覆盖非空值。"""
        existing = {"row-1": {"conclusion": "Y", "remark": "有内容"}}
        incoming = {"row-1": {"conclusion": None, "remark": ""}}
        result = resolve_conflict(existing, incoming, "overwrite")
        assert result["row-1"]["conclusion"] is None
        assert result["row-1"]["remark"] == ""


# ---------------------------------------------------------------------------
# Tests: resolve_conflict — fill-empty strategy
# ---------------------------------------------------------------------------


class TestResolveConflictFillEmpty:
    """fill-empty 策略：仅填空位不覆盖非空（Req 8.2）。"""

    def test_existing_non_empty_preserved(self):
        """existing 非空字段不被覆盖。"""
        existing = {"row-1": {"conclusion": "Y", "remark": "已有内容", "wp_ref": None}}
        incoming = {"row-1": {"conclusion": "N", "remark": "新内容", "wp_ref": "D2-1"}}
        result = resolve_conflict(existing, incoming, "fill-empty")

        # conclusion 和 remark 非空 → 保留 existing
        assert result["row-1"]["conclusion"] == "Y"
        assert result["row-1"]["remark"] == "已有内容"
        # wp_ref 为空 → 填入 incoming
        assert result["row-1"]["wp_ref"] == "D2-1"

    def test_existing_row_all_empty_gets_overwritten(self):
        """existing 行全空 → 全量写入 incoming。"""
        existing = {"row-1": {"conclusion": None, "remark": "", "wp_ref": None}}
        incoming = {"row-1": {"conclusion": "Y", "remark": "填入", "wp_ref": "D1"}}
        result = resolve_conflict(existing, incoming, "fill-empty")
        assert result["row-1"] == {"conclusion": "Y", "remark": "填入", "wp_ref": "D1"}

    def test_new_item_id_fully_written(self):
        """existing 无此 item_id → 全量写入 incoming。"""
        existing = {"row-1": {"conclusion": "Y"}}
        incoming = {"row-new": {"conclusion": "NA", "remark": "新行"}}
        result = resolve_conflict(existing, incoming, "fill-empty")
        assert result["row-new"] == {"conclusion": "NA", "remark": "新行"}

    def test_partial_fill(self):
        """部分字段非空部分空 → 仅空位被填。"""
        existing = {
            "row-1": {"conclusion": "Y", "remark": None, "wp_ref": ""},
            "row-2": {"conclusion": None, "remark": "保留", "wp_ref": None},
        }
        incoming = {
            "row-1": {"conclusion": "N", "remark": "补充", "wp_ref": "新引用"},
            "row-2": {"conclusion": "NA", "remark": "覆盖尝试", "wp_ref": "ref"},
        }
        result = resolve_conflict(existing, incoming, "fill-empty")

        # row-1: conclusion 非空保留, remark/wp_ref 空 → 填入
        assert result["row-1"]["conclusion"] == "Y"
        assert result["row-1"]["remark"] == "补充"
        assert result["row-1"]["wp_ref"] == "新引用"

        # row-2: conclusion 空 → 填入, remark 非空 → 保留, wp_ref 空 → 填入
        assert result["row-2"]["conclusion"] == "NA"
        assert result["row-2"]["remark"] == "保留"
        assert result["row-2"]["wp_ref"] == "ref"

    def test_incoming_adds_new_fields_to_existing_row(self):
        """incoming 包含 existing 没有的字段 → 写入。"""
        existing = {"row-1": {"conclusion": "Y"}}
        incoming = {"row-1": {"conclusion": "N", "remark": "新字段", "extra": "added"}}
        result = resolve_conflict(existing, incoming, "fill-empty")
        assert result["row-1"]["conclusion"] == "Y"  # 非空保留
        assert result["row-1"]["remark"] == "新字段"  # 新字段写入
        assert result["row-1"]["extra"] == "added"  # 新字段写入

    def test_whitespace_only_treated_as_empty(self):
        """仅空白字符的字段视为空，被 incoming 填入。"""
        existing = {"row-1": {"remark": "   "}}
        incoming = {"row-1": {"remark": "有内容"}}
        result = resolve_conflict(existing, incoming, "fill-empty")
        assert result["row-1"]["remark"] == "有内容"


# ---------------------------------------------------------------------------
# Tests: resolve_conflict — reject strategy
# ---------------------------------------------------------------------------


class TestResolveConflictReject:
    """reject 策略：目标非空则整个 sheet 不写入（Req 8.3）。"""

    def test_reject_raises_on_non_empty_existing(self):
        """existing 有非空数据 → 抛 ConflictRejected。"""
        existing = {"row-1": {"conclusion": "Y", "remark": "已有"}}
        incoming = {"row-1": {"conclusion": "N", "remark": "新"}}

        with pytest.raises(ConflictRejected) as exc_info:
            resolve_conflict(existing, incoming, "reject", sheet_code="D2-2")

        assert exc_info.value.sheet_code == "D2-2"
        assert "row-1" in exc_info.value.conflicting_item_ids

    def test_reject_allows_write_when_all_empty(self):
        """existing 全空 → 允许写入（等同 overwrite）。"""
        existing = {"row-1": {"conclusion": None, "remark": ""}}
        incoming = {"row-1": {"conclusion": "Y", "remark": "新内容"}}
        result = resolve_conflict(existing, incoming, "reject", sheet_code="D2-2")
        assert result["row-1"] == {"conclusion": "Y", "remark": "新内容"}

    def test_reject_allows_write_when_no_overlap(self):
        """incoming item_id 在 existing 中不存在 → 允许写入。"""
        existing = {"row-1": {"conclusion": "Y"}}
        incoming = {"row-new": {"conclusion": "NA"}}
        result = resolve_conflict(existing, incoming, "reject", sheet_code="D2-2")
        assert result["row-new"] == {"conclusion": "NA"}

    def test_reject_multiple_conflicting_ids(self):
        """多个 item_id 有非空数据 → 全部列入 conflicting_item_ids。"""
        existing = {
            "row-1": {"conclusion": "Y"},
            "row-2": {"remark": "有"},
            "row-3": {"conclusion": None},
        }
        incoming = {
            "row-1": {"conclusion": "N"},
            "row-2": {"remark": "新"},
            "row-3": {"conclusion": "Y"},
        }

        with pytest.raises(ConflictRejected) as exc_info:
            resolve_conflict(existing, incoming, "reject", sheet_code="D2-3")

        assert "row-1" in exc_info.value.conflicting_item_ids
        assert "row-2" in exc_info.value.conflicting_item_ids
        assert "row-3" not in exc_info.value.conflicting_item_ids

    def test_reject_no_partial_write(self):
        """reject 不部分写入 — 只要有一个冲突就全部拒绝。"""
        existing = {
            "row-1": {"conclusion": "Y"},  # 非空 → 冲突
            "row-2": {"conclusion": None},  # 空 → 本可写入
        }
        incoming = {
            "row-1": {"conclusion": "N"},
            "row-2": {"conclusion": "NA"},
        }

        with pytest.raises(ConflictRejected):
            resolve_conflict(existing, incoming, "reject", sheet_code="D2-4")


# ---------------------------------------------------------------------------
# Tests: ConflictRejected exception
# ---------------------------------------------------------------------------


class TestConflictRejectedException:
    """ConflictRejected 异常属性与消息。"""

    def test_exception_attributes(self):
        exc = ConflictRejected(sheet_code="D2-2", conflicting_item_ids=["a", "b"])
        assert exc.sheet_code == "D2-2"
        assert exc.conflicting_item_ids == ["a", "b"]
        assert "D2-2" in str(exc)
        assert "reject" in str(exc)

    def test_exception_message_truncates_long_list(self):
        """超过 5 个冲突 item_id 时消息截断。"""
        ids = [f"item-{i}" for i in range(10)]
        exc = ConflictRejected(sheet_code="X", conflicting_item_ids=ids)
        assert "共 10 条" in str(exc)

    def test_exception_default_empty_ids(self):
        exc = ConflictRejected(sheet_code="Y")
        assert exc.conflicting_item_ids == []


# ---------------------------------------------------------------------------
# Tests: resolve_conflict — edge cases
# ---------------------------------------------------------------------------


class TestResolveConflictEdgeCases:
    """边界场景。"""

    def test_both_empty(self):
        """existing 和 incoming 都为空 dict → resolved 也为空。"""
        result = resolve_conflict({}, {}, "overwrite")
        assert result == {}

    def test_strategy_applied_uniformly(self):
        """策略对所有 item_id 统一应用（Req 8.4）。"""
        existing = {
            "row-1": {"conclusion": "Y", "remark": None},
            "row-2": {"conclusion": None, "remark": "有"},
        }
        incoming = {
            "row-1": {"conclusion": "N", "remark": "填入"},
            "row-2": {"conclusion": "NA", "remark": "覆盖尝试"},
        }
        result = resolve_conflict(existing, incoming, "fill-empty")

        # 两行都按 fill-empty 逻辑处理
        assert result["row-1"]["conclusion"] == "Y"  # 保留
        assert result["row-1"]["remark"] == "填入"  # 填空
        assert result["row-2"]["conclusion"] == "NA"  # 填空
        assert result["row-2"]["remark"] == "有"  # 保留

    def test_resolved_data_is_independent_copy(self):
        """resolved 数据是独立副本，修改不影响 incoming/existing。"""
        existing = {"row-1": {"a": "x"}}
        incoming = {"row-1": {"a": "y", "b": "z"}}
        result = resolve_conflict(existing, incoming, "overwrite")

        # 修改 result 不影响 incoming
        result["row-1"]["a"] = "modified"
        assert incoming["row-1"]["a"] == "y"
