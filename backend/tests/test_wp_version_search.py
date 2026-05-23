"""底稿历史版本搜索 — 单元测试 + 集成测试

proposal-remaining-18 task 5.4 (S-4)。

涵盖：
- 纯函数 search_in_snapshot_data：formula_values + audited_amounts 字典模糊匹配
- 纯函数 search_in_parsed_data：扁平 / 嵌套两种 cells 结构
- 边界：空输入 / 大小写不敏感 / 数字字符串 / max_results 截断
- 集成：mock 多版本快照，搜索特定值验证返回正确版本列表 + cell 信息
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.wp_version_search_service import (
    _split_cell_key,
    _value_matches,
    search_in_parsed_data,
    search_in_snapshot_data,
    search_versions,
)


# ---------------------------------------------------------------------------
# _split_cell_key / _value_matches
# ---------------------------------------------------------------------------


class TestSplitCellKey:
    def test_with_separator(self):
        assert _split_cell_key("Sheet1!A1") == ("Sheet1", "A1")

    def test_with_chinese_sheet(self):
        assert _split_cell_key("审定表D2-1!B5") == ("审定表D2-1", "B5")

    def test_without_separator(self):
        assert _split_cell_key("A1") == ("", "A1")

    def test_with_multiple_bangs_takes_first(self):
        # ``A!B!C`` → ("A", "B!C")，用首个 ``!`` 切分
        assert _split_cell_key("A!B!C") == ("A", "B!C")


class TestValueMatches:
    def test_str_substring_match(self):
        assert _value_matches("应收账款 1,234.56", "应收账款") is True

    def test_case_insensitive(self):
        assert _value_matches("Hello World", "WORLD") is True

    def test_number_to_str(self):
        assert _value_matches(1234.56, "234") is True

    def test_no_match(self):
        assert _value_matches("foo", "bar") is False

    def test_none(self):
        assert _value_matches(None, "anything") is False

    def test_empty_str_value(self):
        assert _value_matches("", "k") is False


# ---------------------------------------------------------------------------
# search_in_snapshot_data
# ---------------------------------------------------------------------------


class TestSearchInSnapshotData:
    def test_match_formula_values(self):
        snap = {
            "formula_values": {
                "Sheet1!A1": "100",
                "Sheet1!B2": "应收账款 1234",
                "审定表!C3": "其他",
            }
        }
        hits = search_in_snapshot_data(snap, "应收账款")
        assert len(hits) == 1
        assert hits[0] == {
            "field": "formula_value",
            "sheet": "Sheet1",
            "cell_ref": "B2",
            "value": "应收账款 1234",
        }

    def test_match_audited_amounts(self):
        snap = {
            "audited_amounts": {
                "1001": 12345.67,
                "1002": 99999.99,
            }
        }
        hits = search_in_snapshot_data(snap, "12345")
        assert len(hits) == 1
        assert hits[0]["field"] == "audited_amount"
        assert hits[0]["cell_ref"] == "1001"
        assert hits[0]["value"] == 12345.67

    def test_match_both_dicts(self):
        snap = {
            "formula_values": {"S!A1": "abc-key"},
            "audited_amounts": {"1001": "key-value"},
        }
        hits = search_in_snapshot_data(snap, "key")
        # 顺序：formula_values 在前
        assert len(hits) == 2
        assert hits[0]["field"] == "formula_value"
        assert hits[1]["field"] == "audited_amount"

    def test_empty_snapshot(self):
        assert search_in_snapshot_data(None, "x") == []
        assert search_in_snapshot_data({}, "x") == []

    def test_empty_keyword(self):
        snap = {"formula_values": {"S!A1": "100"}}
        assert search_in_snapshot_data(snap, "") == []

    def test_max_results_truncation(self):
        snap = {
            "formula_values": {f"S!A{i}": "match" for i in range(50)},
        }
        hits = search_in_snapshot_data(snap, "match", max_results=10)
        assert len(hits) == 10

    def test_non_dict_formula_values_safe(self):
        # 防御：异常 schema 不 crash
        snap = {"formula_values": "not-a-dict"}
        assert search_in_snapshot_data(snap, "x") == []


# ---------------------------------------------------------------------------
# search_in_parsed_data
# ---------------------------------------------------------------------------


class TestSearchInParsedData:
    def test_flat_cells_with_dict_value(self):
        parsed = {
            "cells": {
                "Sheet1!A1": {"v": "应收账款", "f": None},
                "Sheet1!A2": {"v": 100, "f": None},
            }
        }
        hits = search_in_parsed_data(parsed, "应收")
        assert len(hits) == 1
        assert hits[0]["sheet"] == "Sheet1"
        assert hits[0]["cell_ref"] == "A1"
        assert hits[0]["value"] == "应收账款"

    def test_flat_cells_with_scalar_value(self):
        parsed = {
            "cells": {
                "Sheet1!A1": "scalar-value",
            }
        }
        hits = search_in_parsed_data(parsed, "scalar")
        assert len(hits) == 1
        assert hits[0]["value"] == "scalar-value"

    def test_nested_cells_structure(self):
        parsed = {
            "cells": {
                "Sheet1": {
                    "A1": {"v": "目标值"},
                    "A2": {"v": "其他"},
                },
                "Sheet2": {
                    "B1": {"v": "目标"},
                },
            }
        }
        hits = search_in_parsed_data(parsed, "目标")
        assert len(hits) == 2
        sheets = {h["sheet"] for h in hits}
        assert sheets == {"Sheet1", "Sheet2"}

    def test_empty_parsed_data(self):
        assert search_in_parsed_data(None, "x") == []
        assert search_in_parsed_data({}, "x") == []
        assert search_in_parsed_data({"cells": None}, "x") == []
        assert search_in_parsed_data({"cells": "wrong"}, "x") == []

    def test_value_field_alternative(self):
        parsed = {
            "cells": {
                "S!A1": {"value": "alt"},
                "S!A2": {"val": "alt2"},
            }
        }
        hits = search_in_parsed_data(parsed, "alt")
        assert len(hits) == 2

    def test_case_insensitive(self):
        parsed = {"cells": {"S!A1": {"v": "Hello"}}}
        hits = search_in_parsed_data(parsed, "HELLO")
        assert len(hits) == 1


# ---------------------------------------------------------------------------
# search_versions（DB 集成，使用 stub session 验证编排）
# ---------------------------------------------------------------------------


class _StubResult:
    """模拟 SQLAlchemy execute 返回的 Result 对象"""

    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _StubSession:
    """模拟 AsyncSession，按 SQL 文本派发预设结果"""

    def __init__(self, snapshots: list, current_row=None):
        self._snapshots = snapshots
        self._current_row = current_row
        self.executed_queries: list[str] = []

    async def execute(self, stmt, params=None):  # noqa: ARG002
        sql_text = str(stmt).strip()
        self.executed_queries.append(sql_text)
        if "workpaper_snapshots" in sql_text:
            return _StubResult(self._snapshots)
        if "working_paper" in sql_text:
            return _StubResult([self._current_row] if self._current_row else [])
        return _StubResult([])


@pytest.mark.asyncio
async def test_search_versions_returns_hits_from_multiple_snapshots():
    """核心场景：多版本快照搜索，返回正确 version_id 关联"""
    wp_id = "11111111-1111-1111-1111-111111111111"

    snapshots = [
        SimpleNamespace(
            id="aaa-1",
            trigger_event="sign",
            created_at=datetime(2026, 5, 15, 10, 0, 0, tzinfo=timezone.utc),
            snapshot_data={
                "formula_values": {"Sheet1!B12": "应收账款 1,234.56"},
            },
        ),
        SimpleNamespace(
            id="bbb-2",
            trigger_event="review",
            created_at=datetime(2026, 5, 10, 9, 0, 0, tzinfo=timezone.utc),
            snapshot_data={
                "formula_values": {"Sheet1!B12": "应收账款 1,000.00"},
                "audited_amounts": {"1122": 1000.0},
            },
        ),
        SimpleNamespace(
            id="ccc-3",
            trigger_event="prefill",
            created_at=datetime(2026, 5, 1, 8, 0, 0, tzinfo=timezone.utc),
            snapshot_data={
                "formula_values": {"Sheet1!A1": "其他无关"},
            },
        ),
    ]
    current = SimpleNamespace(
        parsed_data={
            "cells": {
                "Sheet1!B12": {"v": "应收账款 当前值"},
            }
        },
        file_version=4,
        updated_at=datetime(2026, 5, 20, 15, 0, 0, tzinfo=timezone.utc),
    )

    session = _StubSession(snapshots, current_row=current)
    results = await search_versions(session, wp_id, "应收账款")

    # 应命中 sign(1) + review(1) + current(1) = 3 条；prefill 版本无关键词不命中
    assert len(results) == 3
    version_ids = [r["version_id"] for r in results]
    # 顺序：snapshot 按 created_at DESC（已由 SQL ORDER BY），current 在末尾
    assert version_ids[0] == "aaa-1"
    assert version_ids[1] == "bbb-2"
    assert version_ids[2] == "current"

    # 返回字段完整
    first = results[0]
    assert first["trigger_event"] == "sign"
    assert first["sheet"] == "Sheet1"
    assert first["cell_ref"] == "B12"
    assert "应收账款" in str(first["value"])
    assert first["snapshot_at"].startswith("2026-05-15")
    assert first["field"] == "formula_value"

    # current 版本的 trigger_event 标记为 "current"
    assert results[2]["trigger_event"] == "current"


@pytest.mark.asyncio
async def test_search_versions_empty_keyword_returns_empty():
    session = _StubSession([], current_row=None)
    results = await search_versions(
        session, "11111111-1111-1111-1111-111111111111", ""
    )
    assert results == []
    # 空关键字应短路，不查 DB
    assert session.executed_queries == []


@pytest.mark.asyncio
async def test_search_versions_respects_limit():
    """limit=2 时应在历史快照返回 2 条后停止扫描当前版本"""
    snapshots = [
        SimpleNamespace(
            id=f"snap-{i}",
            trigger_event="prefill",
            created_at=datetime(2026, 5, i + 1, tzinfo=timezone.utc),
            snapshot_data={
                "formula_values": {f"S!A{i}": f"keyword-{i}"},
            },
        )
        for i in range(5)
    ]
    current = SimpleNamespace(
        parsed_data={"cells": {"S!Z9": {"v": "keyword-extra"}}},
        file_version=1,
        updated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
    )

    session = _StubSession(snapshots, current_row=current)
    results = await search_versions(session, "wid", "keyword", limit=2)
    assert len(results) == 2
    # 都来自历史快照（current 应未触达）
    assert all(r["version_id"] != "current" for r in results)


@pytest.mark.asyncio
async def test_search_versions_no_snapshot_falls_back_to_current_only():
    current = SimpleNamespace(
        parsed_data={"cells": {"Sheet1!A1": {"v": "目标值"}}},
        file_version=1,
        updated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
    )
    session = _StubSession([], current_row=current)
    results = await search_versions(session, "wid", "目标值")
    assert len(results) == 1
    assert results[0]["version_id"] == "current"
    assert results[0]["sheet"] == "Sheet1"
    assert results[0]["cell_ref"] == "A1"


@pytest.mark.asyncio
async def test_search_versions_no_data_returns_empty():
    session = _StubSession([], current_row=None)
    results = await search_versions(session, "wid", "anything")
    assert results == []
