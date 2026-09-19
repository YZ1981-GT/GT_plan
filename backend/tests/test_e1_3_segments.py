"""Tests for backend/app/services/e0_send_list/e1_3_segments.py"""

import pytest
from hypothesis import given, settings, strategies as st

from app.services.e0_send_list.e1_3_segments import (
    EXCLUDED_ROWS,
    INTEREST_SECTION_HEAD,
    SEGMENT_HEADS,
    Segment,
    account_subject_of,
    split_segments,
)


class TestAccountSubjectOf:
    def test_bank(self):
        assert account_subject_of("银行：") == "1002 银行存款"

    def test_finance_co(self):
        assert account_subject_of("其他金融机构（存放财务公司款项）：") == "1002 银行存款"

    def test_other_monetary(self):
        assert account_subject_of("其他货币资金：") == "1012 其他货币资金"

    def test_unknown_raises(self):
        with pytest.raises(ValueError):
            account_subject_of("不存在的段头")


class TestSplitSegments:
    def _make_rows(self, labels: list[str | None]) -> list[dict]:
        """Helper to build rows with labels in column A."""
        return [{"A": label, "B": f"val_{i}"} for i, label in enumerate(labels)]

    def test_basic_single_segment(self):
        rows = self._make_rows([
            "银行：",
            "招商银行",
            "工商银行",
        ])
        result = split_segments(rows)
        assert len(result) == 1
        assert result[0].head == "银行："
        assert result[0].account_subject == "1002 银行存款"
        assert len(result[0].detail_rows) == 2
        assert result[0].detail_rows[0]["A"] == "招商银行"

    def test_multiple_segments(self):
        rows = self._make_rows([
            "银行：",
            "招商银行",
            "其他金融机构（存放财务公司款项）：",
            "XX财务公司",
            "其他货币资金：",
            "支付宝",
            "微信",
        ])
        result = split_segments(rows)
        assert len(result) == 3
        assert result[0].head == "银行："
        assert len(result[0].detail_rows) == 1
        assert result[1].head == "其他金融机构（存放财务公司款项）："
        assert len(result[1].detail_rows) == 1
        assert result[2].head == "其他货币资金："
        assert len(result[2].detail_rows) == 2

    def test_excludes_segment_heads_from_detail(self):
        rows = self._make_rows([
            "银行：",
            "银行A",
        ])
        result = split_segments(rows)
        # The head itself should not appear in detail_rows
        for seg in result:
            for row in seg.detail_rows:
                assert row["A"] not in SEGMENT_HEADS

    def test_excludes_excluded_rows(self):
        rows = self._make_rows([
            "银行：",
            "招商银行",
            "存款本金小计",
            "银行存款小计",
            "工商银行",
        ])
        result = split_segments(rows)
        assert len(result) == 1
        labels = [r["A"] for r in result[0].detail_rows]
        assert "存款本金小计" not in labels
        assert "银行存款小计" not in labels
        assert "招商银行" in labels
        assert "工商银行" in labels

    def test_excludes_everything_after_interest_section(self):
        rows = self._make_rows([
            "银行：",
            "招商银行",
            "（二）应计利息",
            "利息明细A",
            "利息明细B",
        ])
        result = split_segments(rows)
        assert len(result) == 1
        assert len(result[0].detail_rows) == 1
        assert result[0].detail_rows[0]["A"] == "招商银行"

    def test_empty_labels_included(self):
        rows = self._make_rows([
            "银行：",
            "招商银行",
            None,
            "",
            "工商银行",
        ])
        result = split_segments(rows)
        assert len(result[0].detail_rows) == 4

    def test_rows_before_first_segment_are_ignored(self):
        rows = self._make_rows([
            "一些表头信息",
            "银行：",
            "招商银行",
        ])
        result = split_segments(rows)
        assert len(result) == 1
        assert len(result[0].detail_rows) == 1

    def test_custom_label_key(self):
        rows = [{"X": "银行："}, {"X": "招商银行"}]
        result = split_segments(rows, label_key="X")
        assert len(result) == 1
        assert result[0].detail_rows[0]["X"] == "招商银行"

    def test_realistic_e13_structure(self):
        """Test with a realistic E1-3 row structure."""
        rows = self._make_rows([
            "（一）存款本金",  # section header, before any segment
            "银行：",
            "金华招行基本户801",
            "金华招行一般户",
            "存款本金小计",
            "其他金融机构（存放财务公司款项）：",
            "XX财务公司",
            "财务公司存款小计",
            "其他货币资金：",
            "支付宝",
            "微信支付",
            "其他货币资金小计",
            "合 计",
            "（二）应计利息",
            "利息1",
        ])
        result = split_segments(rows)
        assert len(result) == 3

        # Bank segment
        assert result[0].head == "银行："
        assert len(result[0].detail_rows) == 2  # two bank accounts

        # Finance company segment
        assert result[1].head == "其他金融机构（存放财务公司款项）："
        assert len(result[1].detail_rows) == 1

        # Other monetary segment
        assert result[2].head == "其他货币资金："
        assert len(result[2].detail_rows) == 2

    def test_empty_input(self):
        assert split_segments([]) == []

    def test_no_segments_found(self):
        rows = self._make_rows(["随意文字", "其他内容"])
        assert split_segments(rows) == []


class TestSplitSegmentsPBT:
    """Property-based tests for split_segments."""

    @settings(max_examples=5)
    @given(
        excluded_insertions=st.lists(
            st.sampled_from(list(EXCLUDED_ROWS)),
            min_size=0,
            max_size=5,
        ),
        empty_insertions=st.integers(min_value=0, max_value=3),
    )
    def test_excluded_rows_never_in_output(
        self, excluded_insertions: list[str], empty_insertions: int
    ):
        """Randomly insert excluded rows and empty rows into a segment.
        Verify output never contains excluded labels."""
        base_labels: list[str | None] = [
            "银行：",
            "招商银行",
            "工商银行",
        ]
        # Insert excluded rows at random positions within the segment
        for excl in excluded_insertions:
            base_labels.append(excl)
        # Insert empty/None rows
        for _ in range(empty_insertions):
            base_labels.append(None)

        rows = [{"A": label, "B": "x"} for label in base_labels]
        result = split_segments(rows)

        for seg in result:
            for row in seg.detail_rows:
                label = row.get("A")
                label_str = str(label).strip() if label is not None else ""
                assert label_str not in EXCLUDED_ROWS
                assert label_str not in SEGMENT_HEADS
                assert label_str != INTEREST_SECTION_HEAD
