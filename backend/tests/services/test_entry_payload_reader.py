"""录入载荷读取层守卫 —— Wave 3 Task 7
spec: workpaper-import-export-lifecycle-closure（R2.1 / R2.4 / R2.7）

## 判据设计要点

1. **形态判定走纯函数 `_classify`** —— 可无 DB 直测三形态 + 解析失败降级。
2. **闸门自检用实测量级构造替身** —— memory 铁律：用 1000 行替身测不出
   103 万行的问题。本文件的替身按真实库量级构造（单行 86 万字符 / 单份 103 万行）。
3. **`ORDER BY item_id` 保证产物稳定** —— 否则同一底稿两次导出的 sheet 行序不同，
   用户无法 diff 对照。
"""

from __future__ import annotations

import json

import pytest

from app.services.wp_export.entry_payload_reader import (
    MAX_ITEMS_PER_WP,
    MAX_ONE_CHARS,
    MAX_TOTAL_CHARS,
    EntryPayload,
    EntryPayloadResult,
    _classify,
    read_entry_payloads,
)


# ═══════════════════════════════════════════════════════════════════════════
# 类 A —— 形态判定（纯函数，无 DB）
# ═══════════════════════════════════════════════════════════════════════════


class TestClassify:
    """R2.1：三形态判定 + 解析失败降级。"""

    def test_json_array_of_objects(self):
        shape, rows, obj, failed = _classify('[{"a": 1}, {"a": 2}]')
        assert shape == "json_array"
        assert rows == [{"a": 1}, {"a": 2}]
        assert obj is None
        assert failed is False

    def test_json_array_of_scalars_is_wrapped(self):
        """标量数组要包装成 dict —— 渲染层按 dict 键集出列头，裸标量会崩。"""
        shape, rows, _obj, failed = _classify('["甲", "乙"]')
        assert shape == "json_array"
        assert rows == [{"值": "甲"}, {"值": "乙"}]
        assert failed is False

    def test_json_object(self):
        shape, rows, obj, failed = _classify('{"k": "v", "n": 3}')
        assert shape == "json_object"
        assert rows is None
        assert obj == {"k": "v", "n": 3}
        assert failed is False

    def test_plain_text(self):
        shape, rows, obj, failed = _classify("已核对无误")
        assert shape == "plain_text"
        assert (rows, obj, failed) == (None, None, False)

    def test_broken_json_degrades_not_raises(self):
        """🔴 解析失败降级 plain_text 且标记 failed —— 不抛、不静默。"""
        shape, rows, obj, failed = _classify('[{"a": 1},')
        assert shape == "plain_text"
        assert (rows, obj) == (None, None)
        assert failed is True, "解析失败必须标记，否则真损坏与纯文本不可区分"

    def test_json_scalar_at_top_level_degrades(self):
        """`[1,2]` 是数组没问题，但 `"abc"` 这种带引号的裸标量不该判成结构化。"""
        shape, _r, _o, _f = _classify('"just a quoted string"')
        assert shape == "plain_text"

    def test_leading_whitespace_tolerated(self):
        shape, rows, _o, failed = _classify('  \n  [{"a": 1}]')
        assert shape == "json_array"
        assert rows == [{"a": 1}]
        assert failed is False


# ═══════════════════════════════════════════════════════════════════════════
# 类 A —— 闸门常量（按真实库量级校准）
# ═══════════════════════════════════════════════════════════════════════════


class TestCapConstants:
    """R2.7：三道闸门的取值必须容得下实测最大值。"""

    def test_one_chars_cap_is_meaningful(self):
        # 实测单行最长 866,845 字符 ⇒ 个体闸必须小于它才会真正触发
        assert MAX_ONE_CHARS < 866_845, (
            "个体闸大于实测最大单行 ⇒ 永不触发，等于没设闸"
        )
        assert MAX_ONE_CHARS >= 100_000, "个体闸过小会把正常大表也截断"

    def test_total_cap_accommodates_largest_single(self):
        assert MAX_TOTAL_CHARS > MAX_ONE_CHARS, (
            "总量闸必须大于个体闸，否则单条就撑满总闸"
        )

    def test_item_cap_above_real_nonblank_max(self):
        # 实测单份底稿非空 item 最多 49 条（be63b3e8 那份）
        assert MAX_ITEMS_PER_WP > 49, "条数闸低于实测最大值会误截正常底稿"


# ═══════════════════════════════════════════════════════════════════════════
# 类 A —— 结果对象语义
# ═══════════════════════════════════════════════════════════════════════════


class TestResultSemantics:
    def test_has_content_reflects_payloads(self):
        empty = EntryPayloadResult([], 10, 0, 0, 0)
        assert empty.has_content is False
        one = EntryPayloadResult(
            [EntryPayload("x", "plain_text", None, None, "v", "remark", 1)],
            0, 0, 1, 0,
        )
        assert one.has_content is True

    def test_truncated_covers_all_three_gates(self):
        """截断标志要覆盖三道闸 —— 只看其中一道会漏报。"""
        by_cap = EntryPayloadResult([], 0, 3, 0, 0)
        assert by_cap.truncated is True, "条数/总量闸丢弃未计入 truncated"

        by_one = EntryPayloadResult(
            [EntryPayload("x", "plain_text", None, None, "v", "remark", 999, True)],
            0, 0, 1, 0,
        )
        assert by_one.truncated is True, "个体闸截断未计入 truncated"

        clean = EntryPayloadResult(
            [EntryPayload("x", "plain_text", None, None, "v", "remark", 1)],
            0, 0, 1, 0,
        )
        assert clean.truncated is False


# ═══════════════════════════════════════════════════════════════════════════
# 类 B —— 读取行为（替身 DB，按实测量级）
# ═══════════════════════════════════════════════════════════════════════════


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeDb:
    """最小替身：只实现 `execute`，返回预置行。"""

    def __init__(self, rows, *, raise_exc: Exception | None = None):
        self._rows = rows
        self._raise = raise_exc
        self.executed_sql: str | None = None

    async def execute(self, stmt, params=None):
        if self._raise:
            raise self._raise
        self.executed_sql = str(stmt)
        return _FakeResult(self._rows)


@pytest.mark.asyncio
class TestReadEntryPayloads:
    async def test_blank_rows_are_skipped(self):
        """R2.4：双空行剔除 —— 真实库 99.93% 的行走这条。"""
        rows = [
            ("a", None, None),
            ("b", "", "   "),
            ("c", None, "有内容"),
        ]
        res = await read_entry_payloads(_FakeDb(rows), "wp1")
        assert res.skipped_blank == 2
        assert [p.item_id for p in res.payloads] == ["c"]

    async def test_reads_both_columns_with_source_field(self):
        """🔴 R2.1：两列都读，且标注来源列（只读一列会丢数据）。"""
        rows = [
            ("only_remark", None, '[{"x":1}]'),
            ("only_conclusion", "结论文本", None),
        ]
        res = await read_entry_payloads(_FakeDb(rows), "wp1")
        by_id = {p.item_id: p for p in res.payloads}
        assert by_id["only_remark"].source_field == "remark"
        assert by_id["only_remark"].shape == "json_array"
        assert by_id["only_conclusion"].source_field == "conclusion"
        assert by_id["only_conclusion"].shape == "plain_text"

    async def test_remark_wins_when_both_present(self):
        """两列都非空时以 `remark` 为准（实测它承载 598/696 条）。"""
        rows = [("both", "来自结论", "来自备注")]
        res = await read_entry_payloads(_FakeDb(rows), "wp1")
        p = res.payloads[0]
        assert p.source_field == "remark"
        assert p.text == "来自备注"

    async def test_item_cap_enforced(self):
        """R2.7 条数闸。"""
        rows = [(f"i{n:04d}", None, "v") for n in range(MAX_ITEMS_PER_WP + 25)]
        res = await read_entry_payloads(_FakeDb(rows), "wp1")
        assert len(res.payloads) == MAX_ITEMS_PER_WP
        assert res.dropped_by_cap == 25
        assert res.truncated is True

    async def test_one_chars_cap_truncates_and_flags(self):
        """R2.7 个体闸 —— 按实测最大单行（866,845 字符）构造替身。"""
        huge = json.dumps([{"c": "x" * 40} for _ in range(20_000)])
        assert len(huge) > 800_000, f"替身未达实测量级: {len(huge)}"
        res = await read_entry_payloads(_FakeDb([("big", None, huge)]), "wp1")
        p = res.payloads[0]
        assert p.truncated is True
        assert p.raw_len == len(huge), "raw_len 须记截断前原长，供产物标注"
        assert p.shape == "plain_text", "超限后不保留结构化解析（防 OOM）"
        assert len(p.text or "") == MAX_ONE_CHARS

    async def test_million_row_blank_skeleton_does_not_explode(self):
        """🔴 按实测最坏形态构造：103 万行空骨架 + 10 行非空（C24 那份）。

        用 1000 行替身测不出这个问题 —— memory 铁律。
        """
        rows = [(f"blank{n}", None, None) for n in range(1_000_000)]
        rows += [(f"real{n}", None, f"值{n}") for n in range(10)]
        res = await read_entry_payloads(_FakeDb(rows), "wp1")
        assert res.skipped_blank == 1_000_000
        assert len(res.payloads) == 10, "非空行必须全部保留，不被空行挤掉"
        assert res.dropped_by_cap == 0

    async def test_parse_failure_counted(self):
        res = await read_entry_payloads(_FakeDb([("x", None, '[{"a":1},')]), "wp1")
        assert res.parse_failures == 1
        assert res.payloads[0].shape == "plain_text"

    async def test_query_failure_returns_empty_not_raises(self, caplog):
        """取值层异常不得让导出崩掉，但必须留 **ERROR** 痕。

        memory 铁律：fail-open 掩盖接线错误是最贵的一类缺陷 ——
        「本项目无此数据」与「SQL 列名写错」表现完全一致，只能靠日志级别区分。
        """
        import logging

        db = _FakeDb([], raise_exc=RuntimeError("column does not exist"))
        with caplog.at_level(logging.ERROR):
            res = await read_entry_payloads(db, "wp1")
        assert res.payloads == []
        assert res.has_content is False
        assert any(r.levelno >= logging.ERROR for r in caplog.records), (
            "查询失败必须记 ERROR（WARNING 会被当噪声忽略）"
        )

    async def test_sql_uses_wp_id_column(self):
        """🔴 列名必须是 `wp_id` 而非 `workpaper_id`。

        平台已因写错这个列名踩过一次 P0：整条取值链被 `except` 吞成 WARNING，
        而源码守卫/纯函数单测/characterization 三层全绿（memory 已记）。
        """
        db = _FakeDb([("x", None, "v")])
        await read_entry_payloads(db, "wp1")
        sql = (db.executed_sql or "").lower()
        assert "wp_id" in sql
        assert "workpaper_id" not in sql
        assert "order by item_id" in sql, "缺 ORDER BY ⇒ 两次导出行序不同，无法 diff"
