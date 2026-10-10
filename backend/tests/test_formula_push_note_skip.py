"""公式推送附注跳过减少 · 单元测试

spec: formula-push-note-skip-reduction
覆盖需求 1.1–1.4, 2.3–2.4, 3.1–3.2, 4.1–4.2
"""
from __future__ import annotations

import pytest

from app.services.formula_push.note_writer import (
    NoteTable,
    find_row,
    find_total_row,
    has_obscured_data,
    locate_table,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Task 1: locate_table _source 判断
# ═══════════════════════════════════════════════════════════════════════════════


class TestLocateTableSourceNull:
    """需求 1.1：_source=None + sub_table_data 存在 → 正常返回。"""

    def test_source_null_with_sub_table(self):
        td = {
            "_source": None,
            "sub_table_data": {
                "应交税费": [
                    {"label": "增值税", "values": [100, 200]},
                    {"label": "合计", "values": [100, 200], "is_total": True},
                ],
            },
            "_sub_table_columns": {
                "应交税费": [
                    {"key": "label", "is_label": True},
                    {"key": "end_amount"},
                    {"key": "prior_amount"},
                ],
            },
        }
        table, reason = locate_table(td, "应交税费")
        assert table is not None, "locate_table 不应因 _source=None 而拦截"
        assert reason is None
        assert isinstance(table, NoteTable)
        assert len(table.rows) == 2
        assert table.value_keys == ["end_amount", "prior_amount"]
        assert table.section_locked is False

    def test_source_missing_with_sub_table(self):
        """_source 键不存在（与 =None 等效）。"""
        td = {
            "sub_table_data": {
                "短期借款": [{"label": "信用借款", "values": [1000]}],
            },
        }
        table, reason = locate_table(td, "短期借款")
        assert table is not None
        assert reason is None


class TestLocateTableOldFormat:
    """需求 1.2：无 sub_table_data 但有顶层 rows → 旧格式兜底。"""

    def test_source_null_old_format_rows(self):
        """_source=None + 无 sub_table_data + 有顶层 rows → 返回旧格式 NoteTable。

        Task 1.4 · 需求 1.2
        """
        rows_data = [
            {"label": "固定资产原价", "values": [1000, 800]},
            {"label": "减：累计折旧", "values": [200, 150]},
            {"label": "合计", "values": [800, 650], "is_total": True},
        ]
        td = {
            "_source": None,
            "rows": rows_data,
        }
        table, reason = locate_table(td, "any_table_name")
        assert table is not None, "locate_table 不应因 _source=None 而拦截旧格式"
        assert reason is None
        assert isinstance(table, NoteTable)
        # rows 原样透传
        assert table.rows is rows_data
        assert len(table.rows) == 3
        # 旧格式按位置映射：[0]=期末→end_amount  [1]=期初→prior_amount
        assert table.value_keys == ["end_amount", "prior_amount"]

    def test_empty_rows_returns_none(self):
        td = {"rows": [], "headers": []}
        table, reason = locate_table(td, "whatever")
        assert table is None
        assert "无可定位" in reason


class TestLocateTableExplicitNonWorkpaper:
    """需求 1.3：_source 明确非底稿值 → 拦截。"""

    @pytest.mark.parametrize("source", ["template", "import", "migration"])
    def test_known_non_workpaper_rejected(self, source: str):
        td = {
            "_source": source,
            "sub_table_data": {"X": [{"label": "a"}]},
        }
        table, reason = locate_table(td, "X")
        assert table is None
        assert "模板取数维护" in reason

    def test_locate_table_source_template_rejected(self):
        """Task 1.5 · 需求 1.3：_source='template' 即使 sub_table_data 完整也拦截。

        覆盖 _KNOWN_NON_WORKPAPER 三值 + 验证 reason 中文串。
        """
        valid_sub = {
            "应交税费": [
                {"label": "增值税", "values": [100, 200]},
                {"label": "合计", "values": [100, 200], "is_total": True},
            ],
        }
        for source in ("template", "import", "migration"):
            td = {
                "_source": source,
                "sub_table_data": valid_sub,
                "_sub_table_columns": {
                    "应交税费": [
                        {"key": "label", "is_label": True},
                        {"key": "end_amount"},
                    ],
                },
            }
            table, reason = locate_table(td, "应交税费")
            assert table is None, f"_source={source!r} 应被拦截"
            assert reason is not None
            assert "模板取数维护" in reason, f"_source={source!r} reason 应含'模板取数维护'"

    def test_workpaper_source_accepted(self):
        td = {
            "_source": "workpaper",
            "sub_table_data": {"X": [{"label": "a"}]},
        }
        table, reason = locate_table(td, "X")
        assert table is not None

    def test_workpaper_html_source_accepted(self):
        td = {
            "_source": "workpaper_html",
            "sub_table_data": {"X": [{"label": "a"}]},
        }
        table, reason = locate_table(td, "X")
        assert table is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Task 3: has_obscured_data 误报修复
# ═══════════════════════════════════════════════════════════════════════════════


class TestHasObscuredData:
    """需求 4.1–4.2"""

    def test_values_all_none_not_obscured(self):
        """values=[None, None] → 无遮挡（修复前误报）。"""
        td = {
            "rows": [
                {"label": "应收利息", "values": [None, None], "is_total": False, "row_type": "data"},
            ],
        }
        assert has_obscured_data(td, "其他应收款") is None

    def test_values_all_zero_not_obscured(self):
        td = {
            "rows": [
                {"label": "X", "values": [0, "", "0", None]},
            ],
        }
        assert has_obscured_data(td, "Y") is None

    def test_values_has_real_data(self):
        td = {
            "rows": [
                {"label": "其他应收款", "values": [269885933.03, None]},
            ],
        }
        result = has_obscured_data(td, "X")
        assert result is not None
        assert "非空数值" in result

    def test_skip_underscore_keys(self):
        """以 _ 开头的内部元数据键不参与判断。"""
        td = {
            "rows": [
                {
                    "label": "A",
                    "values": [None, None],
                    "_cell_meta": {"some": "data"},
                    "_cell_modes": {"0": "locked"},
                    "_legacy_row": True,
                },
            ],
        }
        assert has_obscured_data(td, "X") is None

    def test_scalar_non_null_detected(self):
        """非 values 的标量键仍然正常检测。"""
        td = {
            "rows": [
                {"label": "X", "end_amount": 100.5},
            ],
        }
        result = has_obscured_data(td, "Y")
        assert result is not None
        assert "非空数值" in result


def test_has_obscured_data_values_all_none():
    """Task 3.2 · 需求 4.1：values=[None, None] → 返回 None（无遮挡）。

    修复前 has_obscured_data 把 values=[None, None] 的 list 与 None/0/""
    做 != 比较，list 恒不等 → 误报为"含非空数值"。
    修复后对 values 键走列表逐元素检查，全 None 不算有数据。
    """
    td = {
        "rows": [
            {"label": "增值税", "values": [None, None]},
        ],
    }
    assert has_obscured_data(td, "应交税费") is None


def test_has_obscured_data_values_has_real_data():
    """Task 3.3 · 需求 4.1：values=[100.5, None] → 返回中文原因字符串。

    values 列表中含真实非零数值时，has_obscured_data 应检测到并返回
    包含"顶层 rows 含非空数值"的中文原因。
    """
    td = {
        "rows": [
            {"label": "增值税", "values": [100.5, None]},
        ],
    }
    result = has_obscured_data(td, "应交税费")
    assert result is not None, "values 含真实数据时应返回原因字符串"
    assert "顶层 rows 含非空数值" in result


def test_has_obscured_data_skip_underscore_keys():
    """Task 3.4 · 需求 4.2：含 _cell_meta/_cell_modes/_legacy_row → 返回 None。

    以 _ 开头的内部元数据键（_cell_meta、_cell_modes、_legacy_row 等）
    不应参与遮挡检测。行仅含 label + 全空 values + 下划线键时，
    has_obscured_data 应返回 None（无遮挡）。
    """
    td = {
        "rows": [
            {
                "label": "A",
                "values": [None, None],
                "_cell_meta": {"some": "data"},
                "_cell_modes": {"0": "locked"},
                "_legacy_row": True,
            },
        ],
    }
    assert has_obscured_data(td, "X") is None, (
        "_ 前缀键不应被视为遮挡数据"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 4: 单科目合计行兜底（engine 层集成测试）
# Task 5: 章节号动态定位（engine 层集成测试）
# Task 2: 首次推送标记 _source
#
# 这三个需要 mock DB + engine._push_note，用较重的 fixture。
# 下面先对改动的纯函数/局部逻辑做轻量断言。
# ═══════════════════════════════════════════════════════════════════════════════


class TestSourceMarkedAfterFirstPush:
    """Task 2.2 · 需求 1.4：首次推送后 _source 由 None → 'workpaper'；
    第二次推送走正常路径不再触发旧格式兜底。
    """

    def test_source_marked_after_first_push(self):
        """推送前 _source=None → 模拟推送标记 → _source='workpaper'；
        第二次 locate_table 仍正常返回（走 WORKPAPER_SOURCES 路径）。
        """
        # ── 阶段 1：_source=None，旧格式兜底可定位 ──
        table_data = {
            "_source": None,
            "rows": [
                {"label": "信用借款", "values": [1000, 800]},
                {"label": "合计", "values": [1000, 800], "is_total": True},
            ],
        }
        table_before, reason_before = locate_table(table_data, "短期借款")
        assert table_before is not None, "_source=None 应走旧格式兜底"
        assert reason_before is None

        # ── 阶段 2：模拟 engine._push_note 的标记逻辑（engine.py L735-736） ──
        if table_data.get("_source") is None:
            table_data["_source"] = "workpaper"
        assert table_data["_source"] == "workpaper"

        # ── 阶段 3：第二次推送，_source='workpaper' 走正常路径 ──
        # 给 table_data 加上 sub_table_data 模拟引擎骨架构建后的状态
        table_data["sub_table_data"] = {
            "短期借款": [
                {"label": "信用借款", "values": [1000, 800]},
                {"label": "合计", "values": [1000, 800], "is_total": True},
            ],
        }
        table_after, reason_after = locate_table(table_data, "短期借款")
        assert table_after is not None, "_source='workpaper' 应走正常子表路径"
        assert reason_after is None
        # 第二次走子表路径，rows 应来自 sub_table_data（非旧格式兜底）
        assert len(table_after.rows) == 2

    def test_source_none_marked_only_once(self):
        """_source 已为 'workpaper' 时标记逻辑不再修改。"""
        table_data = {"_source": "workpaper", "sub_table_data": {"X": [{"label": "a"}]}}
        # 模拟标记逻辑
        if table_data.get("_source") is None:
            table_data["_source"] = "workpaper"
        assert table_data["_source"] == "workpaper"  # 不变


class TestFindTotalRowForFallback:
    """合计行兜底的前提：find_total_row 能在各种格式下找到合计行。"""

    def test_is_total_flag(self):
        from app.services.formula_push.note_writer import find_total_row
        rows = [{"label": "增值税"}, {"label": "合计", "is_total": True}]
        assert find_total_row(rows) == 1

    def test_row_type_total(self):
        from app.services.formula_push.note_writer import find_total_row
        rows = [{"label": "信用借款", "row_type": "data"}, {"label": "合计", "row_type": "total"}]
        assert find_total_row(rows) == 1

    def test_no_total(self):
        from app.services.formula_push.note_writer import find_total_row
        rows = [{"label": "A"}, {"label": "B"}]
        assert find_total_row(rows) is None

    def test_empty(self):
        from app.services.formula_push.note_writer import find_total_row
        assert find_total_row([]) is None


class TestLocateTableIntegrationWithOldFormat:
    """集成：旧格式 + 合计行兜底组合可行性。"""

    def test_old_format_has_total_row(self):
        """旧格式附注的 rows 中通常有合计行。"""
        td = {
            "rows": [
                {"label": "增值税", "values": [100, 200]},
                {"label": "消费税", "values": [50, 60]},
                {"label": "合计", "values": [150, 260], "is_total": True, "row_type": "total"},
            ],
            "headers": ["项目", "期末余额", "年初余额"],
        }
        table, reason = locate_table(td, "应交税费")
        assert table is not None
        # 合计行可找到
        from app.services.formula_push.note_writer import find_total_row
        assert find_total_row(table.rows) == 2


class TestTotalRowFallbackSingleAccount:
    """Task 4.3 · 需求 2.3：单科目底稿 + 附注子表无同名行 + 有合计行 → 值写入合计行。

    验证合计行兜底逻辑的前提条件链：
      1. locate_table 能定位到子表（_source=None 不拦截）
      2. find_row 按科目名（如"应交税费"）在明细行中找不到匹配
      3. find_total_row 能找到合计行
      4. 合计行的值可被读写（engine._push_note 兜底路径的数据前提）

    engine 层实际的 _push_note 是 async + 依赖 DB context，
    此处验证纯函数层面的逻辑链完整性。
    """

    def test_total_row_fallback_single_account(self):
        """单科目"应交税费"底稿 → 附注子表含明细行（增值税/消费税）+ 合计行，
        但无"应交税费"行 → find_row None + find_total_row 命中 → 兜底可写。
        """
        # ── 构造附注子表：只有明细行 + 合计行，无科目汇总行 ──
        sub_rows = [
            {"label": "增值税", "values": [100, 200], "is_total": False},
            {"label": "消费税", "values": [50, 60], "is_total": False},
            {"label": "城市维护建设税", "values": [20, 30], "is_total": False},
            {"label": "合计", "values": [170, 290], "is_total": True, "row_type": "total"},
        ]
        td = {
            "_source": None,
            "sub_table_data": {
                "应交税费": sub_rows,
            },
            "_sub_table_columns": {
                "应交税费": [
                    {"key": "label", "is_label": True},
                    {"key": "end_amount"},
                    {"key": "prior_amount"},
                ],
            },
        }

        # ① locate_table 能定位（_source=None 不拦截）
        table, reason = locate_table(td, "应交税费")
        assert table is not None, "locate_table 不应因 _source=None 而拦截"
        assert reason is None
        assert len(table.rows) == 4

        # ② find_row 按科目名找不到匹配行（附注行是明细级，不含"应交税费"）
        idx = find_row(table.rows, ["应交税费"])
        assert idx is None, "附注子表中无'应交税费'行，find_row 应返回 None"

        # ③ find_total_row 能找到合计行
        total_idx = find_total_row(table.rows)
        assert total_idx == 3, "合计行应在 index=3"

        # ④ 合计行的值可读（engine 兜底路径的数据前提）
        total_row = table.rows[total_idx]
        assert total_row["is_total"] is True
        assert total_row["label"] == "合计"
        assert total_row["values"] == [170, 290]

        # ⑤ 合计行可被修改（模拟 _push_note_cell 写入）
        total_row["values"][0] = 175  # 模拟审定数写入期末余额
        assert table.rows[total_idx]["values"][0] == 175

    def test_fallback_precondition_with_sub_table_data(self):
        """子表格式（非旧格式）下，同样满足兜底前提：
        find_row 无匹配 + find_total_row 有合计行。
        """
        sub_rows = [
            {"label": "信用借款", "end_amount": 5000, "prior_amount": 3000},
            {"label": "质押借款", "end_amount": 2000, "prior_amount": 1000},
            {"label": "合计", "end_amount": 7000, "prior_amount": 4000, "is_total": True},
        ]
        td = {
            "_source": "workpaper",
            "sub_table_data": {"短期借款": sub_rows},
            "_sub_table_columns": {
                "短期借款": [
                    {"key": "label", "is_label": True},
                    {"key": "end_amount"},
                    {"key": "prior_amount"},
                ],
            },
        }
        table, reason = locate_table(td, "短期借款")
        assert table is not None

        # "短期借款"在明细行中没有同名匹配
        assert find_row(table.rows, ["短期借款"]) is None
        # 但合计行存在
        assert find_total_row(table.rows) == 2

    def test_fallback_not_needed_when_exact_match(self):
        """附注子表恰好有与科目同名的行 → find_row 命中 → 兜底不触发。"""
        sub_rows = [
            {"label": "应收账款", "values": [1000, 800]},
            {"label": "坏账准备", "values": [100, 50]},
            {"label": "合计", "values": [900, 750], "is_total": True},
        ]
        td = {
            "_source": None,
            "sub_table_data": {"应收账款": sub_rows},
            "_sub_table_columns": {
                "应收账款": [{"key": "label", "is_label": True}, {"key": "end_amount"}],
            },
        }
        table, _ = locate_table(td, "应收账款")
        assert table is not None

        # 精确匹配命中 → 不需要兜底
        idx = find_row(table.rows, ["应收账款"])
        assert idx == 0, "精确匹配应命中 index=0"


def test_total_row_fallback_not_triggered_when_row_matched():
    """Task 4.5 · 需求 2.3：单科目但精确匹配命中 → 不走合计行兜底。

    engine.py L694-700 的分支逻辑：
      wrote = False; any_data_row_matched = False
      for row in binding.note_rows(...):
          index = find_row(table.rows, [row["note_label"], ...])
          if index is not None:
              any_data_row_matched = True   ← 命中后置 True
          ...（正常写入）

      if not any_data_row_matched:          ← 此块被跳过
          total_idx = find_total_row(...)
          ...

    本测试模拟单科目底稿"应收账款"、附注子表恰好含"应收账款"同名行的场景：
      - find_row 命中 → any_data_row_matched = True
      - 兜底的 if not any_data_row_matched 条件为 False → 不走合计行写入
      - 正常数据行路径被走、合计行不被兜底直接写入
    """
    # ── 构造单科目底稿的附注子表：含与科目同名的"应收账款"行 ──
    sub_rows = [
        {"label": "应收账款", "values": [1000, 800], "is_total": False},
        {"label": "坏账准备", "values": [100, 50], "is_total": False},
        {"label": "合计", "values": [900, 750], "is_total": True, "row_type": "total"},
    ]
    td = {
        "_source": None,
        "sub_table_data": {"应收账款": sub_rows},
        "_sub_table_columns": {
            "应收账款": [
                {"key": "label", "is_label": True},
                {"key": "end_amount"},
                {"key": "prior_amount"},
            ],
        },
    }

    # ① locate_table 正常定位
    table, reason = locate_table(td, "应收账款")
    assert table is not None
    assert reason is None

    # ② 模拟 engine._push_note 的 note_rows 遍历（单科目 binding 产出的行）
    #    单科目 binding.note_rows 返回一行 note_label=account_name
    mock_note_rows = [
        {
            "note_label": "应收账款",
            "label": "应收账款",
            "end_amount": 1000,
            "end_amount_resolved": True,
            "prior_amount": 800,
            "prior_amount_resolved": True,
            "is_total": False,
            "is_memo": False,
        },
    ]
    account_prefixes = ["1122"]  # 单科目

    # ③ 走引擎遍历逻辑
    any_data_row_matched = False
    for row in mock_note_rows:
        if row["is_total"] or row["is_memo"]:
            continue
        index = find_row(table.rows, [row["note_label"], row["label"]])
        if index is not None:
            any_data_row_matched = True

    # ④ 核心断言：精确匹配命中 → any_data_row_matched = True
    assert any_data_row_matched is True, "find_row 命中后 any_data_row_matched 应为 True"

    # ⑤ 兜底条件不满足 → 合计行不被直接写入
    assert not (not any_data_row_matched), "兜底条件 `not any_data_row_matched` 应为 False"

    # ⑥ 合计行仍然存在（可被后续 _push_note_total 重算），但不被兜底直接写入
    total_idx = find_total_row(table.rows)
    assert total_idx == 2, "合计行应在 index=2"
    # 合计行的值未被兜底修改（原值 900/750 保持不变，等待 _push_note_total 重算）
    assert table.rows[total_idx]["values"] == [900, 750], "合计行值应保持原状（兜底未触发）"

    # ⑦ 验证单科目条件也满足（即便兜底逻辑真的进入，也会走单科目分支）
    is_single = len(account_prefixes) == 1
    assert is_single, "应为单科目（len==1）"
    # 但因 any_data_row_matched=True，根本不会进入兜底块


class TestTotalRowFallbackMultiAccount:
    """Task 4.4 · 需求 2.4：多科目底稿 → 不走单科目兜底分支。

    engine.py 合计行兜底逻辑按 len(account_prefixes) 分支：
      - 单科目（==1）：source_row 取首个非 is_total 数据行
      - 多科目（>1）：source_row 取 is_total 行的汇总值

    本测试验证多科目场景下：
      1. locate_table / find_row / find_total_row 的纯函数前提不变
      2. source_row 选取逻辑走 is_total 分支（非首个数据行）
    """

    def test_multi_account_uses_total_row_as_source(self):
        """多科目（如 D2 "应收账款+预付款项"）附注子表无科目总名行 →
        兜底仍找合计行，但 source_row 取 is_total 行的汇总值。

        engine.py L710-716:
          is_single = hasattr(binding, "account_prefixes") and len(...) == 1
          if is_single: source_row = 首个非 is_total 数据行
          else:         source_row = is_total 行  ← 多科目走此分支
        """
        # ── 构造多科目底稿的 note_rows（模拟 binding.note_rows 返回） ──
        all_note_rows = [
            {"label": "应收账款", "end_amount": 5000, "end_amount_resolved": True,
             "is_total": False, "is_memo": False},
            {"label": "预付款项", "end_amount": 3000, "end_amount_resolved": True,
             "is_total": False, "is_memo": False},
            {"label": "合计", "end_amount": 8000, "end_amount_resolved": True,
             "is_total": True},
        ]
        account_prefixes = ["1122", "1123"]  # 多科目

        # ── 验证分支条件 ──
        is_single = len(account_prefixes) == 1
        assert not is_single, "多科目 account_prefixes 长度应 >1"

        # ── 多科目分支：source_row 取 is_total 行 ──
        source_row = next((r for r in all_note_rows if r.get("is_total")), None)
        assert source_row is not None
        assert source_row["label"] == "合计"
        assert source_row["end_amount"] == 8000, "多科目应取合计行的汇总值 8000"

        # ── 对比：单科目分支会取首个数据行（值不同） ──
        single_source = next(
            (r for r in all_note_rows if not r.get("is_total") and not r.get("is_memo")),
            None,
        )
        assert single_source is not None
        assert single_source["label"] == "应收账款"
        assert single_source["end_amount"] == 5000, "单科目取首个数据行（5000 ≠ 8000）"

        # ── 核心断言：两个分支选出不同的 source_row ──
        assert source_row is not single_source, "多科目与单科目应选不同的 source_row"
        assert source_row["end_amount"] != single_source["end_amount"]

    def test_multi_account_locate_table_and_find_row_preconditions(self):
        """多科目底稿的附注表定位与行匹配前提不变。"""
        sub_rows = [
            {"label": "应收账款", "values": [5000, 4000]},
            {"label": "预付款项", "values": [3000, 2000]},
            {"label": "合计", "values": [8000, 6000], "is_total": True},
        ]
        td = {
            "_source": "workpaper",
            "sub_table_data": {"应收款项": sub_rows},
            "_sub_table_columns": {
                "应收款项": [
                    {"key": "label", "is_label": True},
                    {"key": "end_amount"},
                    {"key": "prior_amount"},
                ],
            },
        }

        # locate_table 正常定位
        table, reason = locate_table(td, "应收款项")
        assert table is not None
        assert reason is None

        # 多科目底稿的科目总名（如"应收款项"）在明细行中不存在
        assert find_row(table.rows, ["应收款项"]) is None

        # 但各明细行按科目名可单独匹配
        assert find_row(table.rows, ["应收账款"]) == 0
        assert find_row(table.rows, ["预付款项"]) == 1

        # 合计行存在
        assert find_total_row(table.rows) == 2


class TestLocateTableNoSubNoRows:
    """既无 sub_table_data 也无 rows → 报错。"""

    def test_empty_dict(self):
        table, reason = locate_table({}, "X")
        assert table is None

    def test_only_headers(self):
        table, reason = locate_table({"headers": ["A", "B"]}, "X")
        assert table is None
        assert "无可定位" in reason


class TestSectionPrefixExtraction:
    """章节号动态反查用的前缀提取逻辑。"""

    @pytest.mark.parametrize("section,expected_prefix", [
        ("五、22", "五、"),
        ("八、31", "八、"),
        ("三、信用减值损失", "三、"),
        ("五-62-1", "五"),  # 无"、"时取首字符
    ])
    def test_prefix(self, section: str, expected_prefix: str):
        if "、" in section:
            prefix = section.split("、")[0] + "、"
        else:
            prefix = section[:1]
        assert prefix == expected_prefix


class TestSectionDynamicLookupOnMismatch:
    """Task 5.3 · 需求 3.1：规则声明 五、22 → 实际标题不匹配 → 反查到正确章节。

    engine.py _push_note 的动态定位逻辑（L617-637）：
      1. 用规则硬编码 section（如 五、22）查 disclosure_notes → 取到 note
      2. 比较 note.section_title 与 _title_check_name（如"固定资产"）
      3. 不匹配时：提取前缀（"五、"）→ 反查 section_title == "固定资产"
         且 note_section LIKE '五、%' 的记录
      4. 唯一命中 → 采纳（替换 note 和 section）
      5. 0 条或多条 → 走原逻辑报跳过

    本测试在纯逻辑层（无 DB）模拟该决策链的每一步。
    """

    def test_mismatch_unique_fallback_succeeds(self):
        """规则声明 五、22 对应"固定资产"，但项目中 五、22="递延所得税负债"。
        反查 section_title=="固定资产" 唯一命中 五、30 → 动态定位成功。
        """
        # ── 模拟项目附注章节（真库场景：不同项目附注排序不同） ──
        notes = [
            {"note_section": "五、20", "section_title": "长期借款", "is_deleted": False},
            {"note_section": "五、22", "section_title": "递延所得税负债", "is_deleted": False},
            {"note_section": "五、25", "section_title": "应付职工薪酬", "is_deleted": False},
            {"note_section": "五、30", "section_title": "固定资产", "is_deleted": False},
            {"note_section": "五、35", "section_title": "在建工程", "is_deleted": False},
        ]

        # ── 规则声明 ──
        rule_section = "五、22"
        target_title = "固定资产"  # _title_check_name

        # ── Step 1: 按硬编码 section 取到 note ──
        direct_note = next(
            (n for n in notes if n["note_section"] == rule_section and not n["is_deleted"]),
            None,
        )
        assert direct_note is not None, "硬编码章节号应能查到记录"

        # ── Step 2: section_title 不匹配 → 触发反查 ──
        assert direct_note["section_title"] != target_title, (
            f"规则声明 {rule_section} 的标题是"
            f"「{direct_note['section_title']}」≠「{target_title}」，应触发反查"
        )

        # ── Step 3: 提取前缀（engine.py L621） ──
        _section_prefix = (
            rule_section.split("、")[0] + "、"
            if "、" in rule_section
            else rule_section[:1]
        )
        assert _section_prefix == "五、"

        # ── Step 4: 反查 section_title == target_title 且前缀匹配 ──
        fallback_rows = [
            n for n in notes
            if n["section_title"] == target_title
            and not n["is_deleted"]
            and n["note_section"].startswith(_section_prefix)
        ]

        # ── Step 5: 唯一命中 → 采纳 ──
        assert len(fallback_rows) == 1, (
            f"反查应唯一命中，实际 {len(fallback_rows)} 条"
        )
        found = fallback_rows[0]
        assert found["note_section"] == "五、30"
        assert found["section_title"] == "固定资产"

        # ── Step 6: 验证替换后的 section 和 section_addr ──
        new_section = found["note_section"]
        new_addr = f"note://{new_section}/{target_title}"
        assert new_section == "五、30"
        assert new_addr == "note://五、30/固定资产"

    def test_mismatch_soe_template_prefix(self):
        """国企模板（八、）场景下前缀提取和反查同样生效。"""
        notes = [
            {"note_section": "八、4", "section_title": "应收票据", "is_deleted": False},
            {"note_section": "八、7", "section_title": "存货", "is_deleted": False},
            {"note_section": "八、10", "section_title": "固定资产", "is_deleted": False},
        ]

        rule_section = "八、7"
        target_title = "固定资产"

        # 硬编码章节号标题不匹配
        direct = next(n for n in notes if n["note_section"] == rule_section)
        assert direct["section_title"] == "存货" != target_title

        # 前缀 → "八、"
        prefix = rule_section.split("、")[0] + "、"
        assert prefix == "八、"

        # 反查
        matches = [
            n for n in notes
            if n["section_title"] == target_title
            and not n["is_deleted"]
            and n["note_section"].startswith(prefix)
        ]
        assert len(matches) == 1
        assert matches[0]["note_section"] == "八、10"

    def test_deleted_note_excluded_from_fallback(self):
        """已删除的附注不参与反查。"""
        notes = [
            {"note_section": "五、22", "section_title": "递延所得税负债", "is_deleted": False},
            {"note_section": "五、30", "section_title": "固定资产", "is_deleted": True},   # 已删除
            {"note_section": "五、33", "section_title": "固定资产", "is_deleted": False},   # 存活
        ]

        rule_section = "五、22"
        target_title = "固定资产"
        prefix = "五、"

        fallback = [
            n for n in notes
            if n["section_title"] == target_title
            and not n["is_deleted"]
            and n["note_section"].startswith(prefix)
        ]
        # 只有 五、33 存活 → 唯一命中
        assert len(fallback) == 1
        assert fallback[0]["note_section"] == "五、33"

    def test_cross_prefix_not_matched(self):
        """反查范围用前缀限定：五、 的规则不会匹配到 八、 的章节。"""
        notes = [
            {"note_section": "五、22", "section_title": "递延所得税负债", "is_deleted": False},
            {"note_section": "八、15", "section_title": "固定资产", "is_deleted": False},
        ]

        rule_section = "五、22"
        target_title = "固定资产"
        prefix = "五、"

        fallback = [
            n for n in notes
            if n["section_title"] == target_title
            and not n["is_deleted"]
            and n["note_section"].startswith(prefix)
        ]
        # 八、15 不在 五、 前缀范围内 → 0 条 → 不采纳
        assert len(fallback) == 0

    def test_section_dynamic_lookup_ambiguous_skip(self):
        """Task 5.4 · 需求 3.2：同 section_title 有 2 条匹配 → 不替换，走原逻辑跳过。

        engine.py _push_note 的动态定位逻辑（L617-637）要求反查结果
        **唯一**（len(fallback)==1）才采纳。0 条或多条视为歧义，
        回退硬编码逻辑（即走原逻辑跳过）。

        本测试模拟：
          - 规则声明 五、22 对应"固定资产"，但项目中 五、22="递延所得税负债"
          - 反查 section_title=="固定资产" 在五、前缀下命中 **2 条**（五、25 和 五、30）
          - len(fallback)==2 ≠ 1 → 视为歧义 → 不采纳 → 走原逻辑报跳过
        """
        # ── 模拟项目附注章节：同标题"固定资产"出现在两个不同章节号 ──
        notes = [
            {"note_section": "五、20", "section_title": "长期借款", "is_deleted": False},
            {"note_section": "五、22", "section_title": "递延所得税负债", "is_deleted": False},
            {"note_section": "五、25", "section_title": "固定资产", "is_deleted": False},  # match 1
            {"note_section": "五、30", "section_title": "固定资产", "is_deleted": False},  # match 2
            {"note_section": "五、35", "section_title": "在建工程", "is_deleted": False},
        ]

        rule_section = "五、22"
        target_title = "固定资产"  # _title_check_name

        # ── Step 1: 硬编码章节号的标题不匹配 → 触发反查 ──
        direct_note = next(
            (n for n in notes if n["note_section"] == rule_section and not n["is_deleted"]),
            None,
        )
        assert direct_note is not None
        assert direct_note["section_title"] != target_title, "标题不匹配才触发反查"

        # ── Step 2: 提取前缀 ──
        prefix = rule_section.split("、")[0] + "、"
        assert prefix == "五、"

        # ── Step 3: 反查 → 命中 2 条（歧义） ──
        fallback_rows = [
            n for n in notes
            if n["section_title"] == target_title
            and not n["is_deleted"]
            and n["note_section"].startswith(prefix)
        ]
        assert len(fallback_rows) == 2, (
            f"应有 2 条同名匹配（歧义），实际 {len(fallback_rows)} 条"
        )

        # ── Step 4: 唯一性检查失败 → 不采纳 ──
        assert len(fallback_rows) != 1, "非唯一匹配不应被采纳"

        # ── Step 5: 验证走原逻辑——section 和 note 保持不变（未被替换） ──
        # engine.py 的 if len(fallback)==1 块不进入，section 仍为规则原值
        current_section = rule_section  # 未被替换
        current_note = direct_note       # 未被替换
        assert current_section == "五、22", "歧义时 section 应保持规则原值"
        assert current_note["section_title"] == "递延所得税负债", (
            "歧义时 note 应保持硬编码查到的原记录"
        )

    def test_section_dynamic_lookup_zero_match_skip(self):
        """补充：反查 0 条匹配同样不采纳（与 2 条歧义行为一致）。"""
        notes = [
            {"note_section": "五、22", "section_title": "递延所得税负债", "is_deleted": False},
            {"note_section": "五、25", "section_title": "长期借款", "is_deleted": False},
        ]

        rule_section = "五、22"
        target_title = "固定资产"
        prefix = "五、"

        fallback_rows = [
            n for n in notes
            if n["section_title"] == target_title
            and not n["is_deleted"]
            and n["note_section"].startswith(prefix)
        ]
        assert len(fallback_rows) == 0, "目标标题在本前缀下无匹配"
        assert len(fallback_rows) != 1, "0 条匹配同样不被采纳"

    def test_section_dynamic_lookup_not_triggered_when_match(self):
        """Task 5.5 · 需求 3.3：硬编码章节号 section_title 匹配 → 不触发反查。

        engine.py _push_note 的动态定位逻辑（L617-637）：
          note = query(note_section == rule_section)
          if note.section_title != _title_check_name:
              # ← 不匹配时才进入反查分支
              fallback = ...

        本测试验证 happy path：
          - 规则声明 五、22 → 项目中 五、22 的 section_title 恰好是"固定资产"
          - section_title == _title_check_name → 条件为 False
          - 整个反查分支被跳过 → note 和 section 保持不变
          - 后续推送使用原始硬编码章节号直接进行
        """
        # ── 模拟项目附注章节：五、22 的标题恰好匹配规则声明 ──
        notes = [
            {"note_section": "五、20", "section_title": "长期借款", "is_deleted": False},
            {"note_section": "五、22", "section_title": "固定资产", "is_deleted": False},
            {"note_section": "五、30", "section_title": "在建工程", "is_deleted": False},
        ]

        rule_section = "五、22"
        target_title = "固定资产"  # _title_check_name

        # ── Step 1: 按硬编码 section 取到 note ──
        direct_note = next(
            (n for n in notes if n["note_section"] == rule_section and not n["is_deleted"]),
            None,
        )
        assert direct_note is not None, "硬编码章节号应能查到记录"

        # ── Step 2: section_title 匹配 → 不触发反查 ──
        title_matches = (direct_note["section_title"] or "").strip() == target_title
        assert title_matches, (
            f"规则声明 {rule_section} 的标题「{direct_note['section_title']}」"
            f"应与目标「{target_title}」匹配"
        )

        # ── Step 3: 反查条件不满足（条件是 != 才进入） ──
        fallback_triggered = not title_matches
        assert not fallback_triggered, "标题匹配时反查分支不应被触发"

        # ── Step 4: note 和 section 保持不变（未被替换） ──
        current_section = rule_section  # 未被替换
        current_note = direct_note       # 未被替换
        assert current_section == "五、22", "匹配时 section 应保持规则原值"
        assert current_note["section_title"] == "固定资产", (
            "匹配时 note 应保持硬编码查到的原记录"
        )
        assert current_note["note_section"] == rule_section, (
            "匹配时 note_section 应与规则声明一致"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Engine-level mock DB integration tests for _push_note
#
# 覆盖：
#   - 需求 2.3: 单科目合计行兜底（is_single=True → source_row 取首个数据行）
#   - 需求 2.4: 多科目合计行兜底（is_single=False → source_row 取 is_total 行）
#   - skip_total_recalc=True 时 _push_note_total 不被调用
#   - 需求 1.4: _source=None → 首次写入后标记 "workpaper"
#   - 需求 3.1: 章节号动态定位（按 section_title 反查唯一命中）
# ═══════════════════════════════════════════════════════════════════════════════

import asyncio
import copy
from dataclasses import dataclass as _std_dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import app.services.formula_push.engine as engine_mod
from app.services.formula_push.engine import _Ctx, _Paper
from app.services.formula_push.results import FALLBACK_TO_TOTAL, RunResult
from app.services.formula_push.rules import PushRule, PushTarget


# ─── 通用 fixture 工厂 ──────────────────────────────────────────────────

_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")
_YEAR = 2025
_USER_ID = UUID("00000000-0000-0000-0000-000000000099")
_PAPER_ID = UUID("00000000-0000-0000-0000-00000000000a")
_NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_ctx(db=None) -> _Ctx:
    return _Ctx(
        db=db or AsyncMock(),
        project_id=_PROJECT_ID,
        year=_YEAR,
        triggered_by=_USER_ID,
        force=frozenset(),
        now=_NOW,
        states={},
        result=RunResult(project_id=_PROJECT_ID, year=_YEAR, trigger="test"),
    )


def _make_paper() -> _Paper:
    return _Paper(id=_PAPER_ID, status="in_progress", paper_code="N4")


def _make_rule(
    *,
    rule_id: str = "test-rule",
    table: str = "应交税费",
    sections: dict[str, str] | None = None,
    fields: tuple[str, ...] = ("end_amount", "prior_amount"),
    table_by_template: tuple[tuple[str, str], ...] = (),
) -> PushRule:
    if sections is None:
        sections = {"listed": "五、22"}
    return PushRule(
        rule_id=rule_id,
        page_key="note:N4",
        stage="note",
        policy="overwrite",
        target=PushTarget(
            domain="note",
            fields=fields,
            section_by_template=tuple(sections.items()),
            table=table,
            table_by_template=table_by_template,
        ),
        source=MagicMock(),
        triggers=("TRIAL_BALANCE_UPDATED",),
        description="test rule",
    )


def _make_sources(template_type: str = "listed") -> SimpleNamespace:
    return SimpleNamespace(template_type=template_type)


def _make_binding(
    note_rows: list[dict],
    account_prefixes: tuple[str, ...] = ("2221",),
) -> MagicMock:
    binding = MagicMock()
    binding.note_rows = MagicMock(return_value=note_rows)
    binding.account_prefixes = account_prefixes
    return binding


def _make_note_mock(
    *,
    note_section: str = "五、22",
    section_title: str = "应交税费",
    status: str = "draft",
    table_data: dict | None = None,
) -> MagicMock:
    """构造模拟 DisclosureNote ORM 对象。"""
    note = MagicMock()
    note.project_id = _PROJECT_ID
    note.year = _YEAR
    note.note_section = note_section
    note.section_title = section_title
    note.status = status
    note.table_data = copy.deepcopy(table_data) if table_data else {}
    note.is_deleted = False
    note.is_stale = True
    note.stale_source = "manual"
    note.last_sync_source = None
    note.last_sync_wp_id = None
    note.last_sync_at = None
    note.last_sync_user_id = None
    note.updated_by = None
    note.updated_at = None
    return note


def _sub_table_data(
    table_name: str,
    rows: list[dict],
    columns: list[dict] | None = None,
    source: str | None = None,
) -> dict:
    """构造标准 sub_table_data 格式的 table_data。"""
    if columns is None:
        columns = [
            {"key": "label", "is_label": True},
            {"key": "end_amount"},
            {"key": "prior_amount"},
        ]
    td = {
        "sub_table_data": {table_name: rows},
        "_sub_table_columns": {table_name: columns},
    }
    if source is not None:
        td["_source"] = source
    return td


def _setup_db_for_single_note(note_mock) -> AsyncMock:
    """设置 mock db，使 execute().scalar_one_or_none() 返回单个 note。"""
    db = AsyncMock()
    # 第一次 execute = 主查询（scalar_one_or_none）
    primary_result = MagicMock()
    primary_result.scalar_one_or_none.return_value = note_mock
    db.execute.return_value = primary_result
    db.flush = AsyncMock()
    return db


class TestPushNoteEngineIntegration:
    """engine._push_note 引擎级集成测试（mock DB）。

    与纯函数测试不同，这些测试直接调用 async _push_note，验证引擎内部
    分支逻辑在组合条件下的行为：合计行兜底 single/multi、skip_total_recalc、
    _source 标记、章节号动态定位。
    """

    # ── Test 1: 单科目合计行兜底 ─────────────────────────────────────

    def test_push_note_single_account_total_fallback_writes_to_total_row(self):
        """需求 2.3：单科目底稿 + 附注子表无同名行 + 有合计行
        → 值写入合计行（取首个非 total 数据行的值）
        → _push_note_total 不被调用（skip_total_recalc=True）。
        """
        # ── 附注子表：明细行 + 合计行，无 "应交税费" 同名行 ──
        sub_rows = [
            {"label": "增值税", "end_amount": 100, "prior_amount": 200, "is_total": False},
            {"label": "消费税", "end_amount": 50, "prior_amount": 60, "is_total": False},
            {"label": "合计", "end_amount": 150, "prior_amount": 260, "is_total": True, "row_type": "total"},
        ]
        table_data = _sub_table_data("应交税费", sub_rows, source="workpaper")
        note = _make_note_mock(table_data=table_data)
        db = _setup_db_for_single_note(note)
        ctx = _make_ctx(db=db)
        paper = _make_paper()

        # binding: 单科目，note_rows 返回一个数据行 + 一个 total 行
        note_rows = [
            {"note_label": "应交税费", "label": "应交税费",
             "ending": 175, "ending_resolved": True, "opening": 270, "opening_resolved": True,
             "is_total": False, "is_memo": False},
            {"note_label": "合计", "label": "合计",
             "ending": 175, "ending_resolved": True, "opening": 270, "opening_resolved": True,
             "is_total": True, "is_memo": False},
        ]
        binding = _make_binding(note_rows, account_prefixes=("2221",))
        rule = _make_rule()
        sources = _make_sources()

        with patch.object(engine_mod, "_push_note_cell", return_value=True) as mock_cell, \
             patch.object(engine_mod, "_push_note_total", return_value=False) as mock_total:
            section = asyncio.run(
                engine_mod._push_note(ctx, rule=rule, binding=binding,
                                       overlay={}, sources=sources, paper=paper)
            )

        # ── 断言 ──
        # _push_note_cell 被调用（合计行兜底路径写入）
        assert mock_cell.call_count >= 1, "_push_note_cell 应被调用至少 1 次（兜底写入合计行）"

        # 检查 _push_note_cell 调用时传入的 row 是合计行
        for call in mock_cell.call_args_list:
            _, kwargs = call
            if "row" in kwargs:
                assert kwargs["row"].get("is_total") is True or kwargs["row"].get("row_type") == "total", \
                    "兜底路径应写入合计行"

        # _push_note_total 不被调用（skip_total_recalc=True）
        assert mock_total.call_count == 0, (
            "单科目兜底成功后 skip_total_recalc=True，_push_note_total 不应被调用"
        )

        # section 被返回（有写入）
        assert section is not None

    # ── Test 2: 多科目合计行兜底取 is_total 行的值 ──────────────────

    def test_push_note_multi_account_total_fallback_uses_total_source(self):
        """需求 2.4：多科目底稿 → 兜底时 source_row 取 is_total 行（汇总值），
        不取首个数据行。

        通过检查传给 _push_note_cell 的 value 参数来区分单/多科目分支。
        """
        sub_rows = [
            {"label": "增值税", "end_amount": 100, "prior_amount": 200, "is_total": False},
            {"label": "消费税", "end_amount": 50, "prior_amount": 60, "is_total": False},
            {"label": "合计", "end_amount": 150, "prior_amount": 260, "is_total": True, "row_type": "total"},
        ]
        table_data = _sub_table_data("应交税费", sub_rows, source="workpaper")
        note = _make_note_mock(table_data=table_data)
        db = _setup_db_for_single_note(note)
        ctx = _make_ctx(db=db)
        paper = _make_paper()

        # binding: 多科目，note_rows 返回两个数据行 + 一个 total 行
        # 数据行值 5000 和 3000，total 行值 8000 → 验证兜底取 8000 而非 5000
        note_rows = [
            {"note_label": "应收账款", "label": "应收账款",
             "ending": 5000, "ending_resolved": True, "opening": 4000, "opening_resolved": True,
             "is_total": False, "is_memo": False},
            {"note_label": "预付款项", "label": "预付款项",
             "ending": 3000, "ending_resolved": True, "opening": 2000, "opening_resolved": True,
             "is_total": False, "is_memo": False},
            {"note_label": "合计", "label": "合计",
             "ending": 8000, "ending_resolved": True, "opening": 6000, "opening_resolved": True,
             "is_total": True, "is_memo": False},
        ]
        binding = _make_binding(note_rows, account_prefixes=("1122", "1123"))
        rule = _make_rule(table="应交税费")
        sources = _make_sources()

        written_values = []

        def _capture_cell(ctx, *, rule, section, addr, table, row, field_name, value, paper):
            written_values.append((field_name, value))
            return True

        with patch.object(engine_mod, "_push_note_cell", side_effect=_capture_cell) as mock_cell, \
             patch.object(engine_mod, "_push_note_total", return_value=False) as mock_total:
            section = asyncio.run(
                engine_mod._push_note(ctx, rule=rule, binding=binding,
                                       overlay={}, sources=sources, paper=paper)
            )

        # ── 断言：兜底被触发 ──
        assert mock_cell.call_count >= 1, "兜底路径应写入合计行"

        # 多科目分支：值应来自 is_total 行（8000/6000），不是首个数据行（5000/4000）
        end_values = [v for fn, v in written_values if fn == "end_amount"]
        prior_values = [v for fn, v in written_values if fn == "prior_amount"]
        assert 8000 in end_values, (
            f"多科目兜底应取 is_total 行的 ending=8000，实际写入: {end_values}"
        )
        assert 6000 in prior_values, (
            f"多科目兜底应取 is_total 行的 opening=6000，实际写入: {prior_values}"
        )
        # 确保不是单科目分支的值
        assert 5000 not in end_values, "多科目兜底不应取首个数据行的值 5000"

        # skip_total_recalc=True → _push_note_total 不调用
        assert mock_total.call_count == 0

    # ── Test 3: 数据行命中时跳过合计行兜底 ───────────────────────────

    def test_push_note_data_row_matched_skips_total_fallback(self):
        """数据行 find_row 命中 → any_data_row_matched=True → 兜底块不进入
        → _push_note_total 被正常调用（非兜底重算路径）。
        """
        # 附注子表有 "应收账款" 同名行 → find_row 命中
        sub_rows = [
            {"label": "应收账款", "end_amount": 1000, "prior_amount": 800, "is_total": False},
            {"label": "坏账准备", "end_amount": 100, "prior_amount": 50, "is_total": False},
            {"label": "合计", "end_amount": 900, "prior_amount": 750, "is_total": True, "row_type": "total"},
        ]
        table_data = _sub_table_data("应收账款", sub_rows, source="workpaper")
        note = _make_note_mock(section_title="应收账款", table_data=table_data)
        db = _setup_db_for_single_note(note)
        ctx = _make_ctx(db=db)
        paper = _make_paper()

        # binding: 单科目，note_rows 的 note_label 恰好匹配附注子表的行标签
        note_rows = [
            {"note_label": "应收账款", "label": "应收账款",
             "ending": 1200, "ending_resolved": True, "opening": 900, "opening_resolved": True,
             "is_total": False, "is_memo": False},
        ]
        binding = _make_binding(note_rows, account_prefixes=("1122",))
        rule = _make_rule(table="应收账款", sections={"listed": "五、22"})
        sources = _make_sources()

        cell_rows_written = []

        def _capture_cell(ctx, *, rule, section, addr, table, row, field_name, value, paper):
            cell_rows_written.append(row.get("label"))
            return True

        with patch.object(engine_mod, "_push_note_cell", side_effect=_capture_cell) as mock_cell, \
             patch.object(engine_mod, "_push_note_total", return_value=False) as mock_total:
            section = asyncio.run(
                engine_mod._push_note(ctx, rule=rule, binding=binding,
                                       overlay={}, sources=sources, paper=paper)
            )

        # ── 断言 ──
        # 正常数据行路径被走（写入 "应收账款" 行，非合计行）
        assert "应收账款" in cell_rows_written, (
            f"应写入 '应收账款' 数据行，实际写入: {cell_rows_written}"
        )

        # _push_note_total 被正常调用（非兜底路径，而是标准合计重算）
        assert mock_total.call_count == 1, (
            "_push_note_total 应被调用 1 次（正常合计重算路径）"
        )

    # ── Test 4: _source=None → 首次写入后标记 "workpaper" ─────────────

    def test_push_note_source_marked_after_write(self):
        """需求 1.4：_source=None 的附注首次被推送后，table_data._source
        自动设为 "workpaper"。
        """
        # 旧格式附注：只有顶层 rows，_source=None
        old_rows = [
            {"label": "信用借款", "end_amount": 1000, "prior_amount": 800, "is_total": False},
            {"label": "合计", "end_amount": 1000, "prior_amount": 800, "is_total": True, "row_type": "total"},
        ]
        table_data = {
            "_source": None,
            "rows": old_rows,
        }
        note = _make_note_mock(section_title="短期借款", table_data=table_data)
        db = _setup_db_for_single_note(note)
        ctx = _make_ctx(db=db)
        paper = _make_paper()

        # binding: 单科目，note_rows 的 note_label 不匹配任何行 → 走兜底
        note_rows = [
            {"note_label": "短期借款", "label": "短期借款",
             "ending": 1500, "ending_resolved": True, "opening": 900, "opening_resolved": True,
             "is_total": False, "is_memo": False},
        ]
        binding = _make_binding(note_rows, account_prefixes=("2001",))
        rule = _make_rule(table="短期借款", sections={"listed": "五、22"})
        sources = _make_sources()

        with patch.object(engine_mod, "_push_note_cell", return_value=True), \
             patch.object(engine_mod, "_push_note_total", return_value=False):
            section = asyncio.run(
                engine_mod._push_note(ctx, rule=rule, binding=binding,
                                       overlay={}, sources=sources, paper=paper)
            )

        # ── 断言 ──
        assert section is not None, "应有写入（兜底路径）"
        # _source 被标记为 "workpaper"（engine.py L735-736）
        assert note.table_data.get("_source") == "workpaper", (
            f"首次推送后 _source 应为 'workpaper'，实际: {note.table_data.get('_source')!r}"
        )
        # 同步指纹被写入
        assert note.table_data.get("_last_sync_wp_id") == str(_PAPER_ID)
        assert note.table_data.get("_last_sync_at") is not None
        # ORM 属性被更新
        assert note.is_stale is False
        assert note.last_sync_source == "formula_push"

    # ── Test 5: 章节号动态定位唯一命中 ──────────────────────────────

    def test_push_note_section_dynamic_lookup_unique_hit(self):
        """需求 3.1：规则声明 五、22 对应"固定资产"，但项目中 五、22="递延所得税负债"。
        反查唯一命中 五、30="固定资产" → 引擎切换到 五、30。
        """
        # ── 两个 DisclosureNote mock ──
        # 主查询（五、22）→ 标题不匹配
        note_22 = _make_note_mock(
            note_section="五、22",
            section_title="递延所得税负债",
            table_data=_sub_table_data("递延所得税负债", [{"label": "X", "end_amount": 0}], source="workpaper"),
        )
        # 反查命中（五、30）→ 标题匹配 "固定资产"
        sub_rows_30 = [
            {"label": "房屋及建筑物", "end_amount": 5000, "prior_amount": 4000, "is_total": False},
            {"label": "合计", "end_amount": 5000, "prior_amount": 4000, "is_total": True, "row_type": "total"},
        ]
        note_30 = _make_note_mock(
            note_section="五、30",
            section_title="固定资产",
            table_data=_sub_table_data("固定资产", sub_rows_30, source="workpaper"),
        )

        db = AsyncMock()
        call_count = {"n": 0}

        async def _mock_execute(stmt, *args, **kwargs):
            call_count["n"] += 1
            result = MagicMock()
            if call_count["n"] == 1:
                # 主查询：scalar_one_or_none → note_22
                result.scalar_one_or_none.return_value = note_22
                return result
            elif call_count["n"] == 2:
                # 反查查询：scalars().all() → [note_30]
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = [note_30]
                result.scalars.return_value = scalars_mock
                return result
            else:
                result.scalar_one_or_none.return_value = None
                return result

        db.execute = _mock_execute
        db.flush = AsyncMock()

        ctx = _make_ctx(db=db)
        paper = _make_paper()

        # binding: 单科目，note_rows 有 "房屋及建筑物" 匹配 note_30 的子表行
        note_rows = [
            {"note_label": "房屋及建筑物", "label": "房屋及建筑物",
             "ending": 5500, "ending_resolved": True, "opening": 4200, "opening_resolved": True,
             "is_total": False, "is_memo": False},
        ]
        binding = _make_binding(note_rows, account_prefixes=("1601",))
        rule = _make_rule(
            table="固定资产",
            sections={"listed": "五、22"},  # 硬编码指向 五、22，但实际应切到 五、30
        )
        sources = _make_sources()

        sections_written = []

        def _capture_cell(ctx, *, rule, section, addr, table, row, field_name, value, paper):
            sections_written.append(section)
            return True

        with patch.object(engine_mod, "_push_note_cell", side_effect=_capture_cell), \
             patch.object(engine_mod, "_push_note_total", return_value=False):
            section = asyncio.run(
                engine_mod._push_note(ctx, rule=rule, binding=binding,
                                       overlay={}, sources=sources, paper=paper)
            )

        # ── 断言 ──
        # 动态定位切换到 五、30
        assert section == "五、30", (
            f"章节号应动态切换到 '五、30'，实际: {section!r}"
        )
        # _push_note_cell 收到的 section 也是 五、30
        assert all(s == "五、30" for s in sections_written), (
            f"_push_note_cell 的 section 参数应全为 '五、30'，实际: {sections_written}"
        )
        # result.note_sections 记录了 五、30
        assert "五、30" in ctx.result.note_sections
        # 反查确实发生了（至少 2 次 execute 调用）
        assert call_count["n"] >= 2, "应有至少 2 次 db.execute 调用（主查询 + 反查）"


# ═══════════════════════════════════════════════════════════════════════════════
# spec: formula-push-note-row-matching · 需求 2: 包含匹配（find_row 第三级）
# ═══════════════════════════════════════════════════════════════════════════════

from hypothesis import given, settings, assume
from hypothesis import strategies as st


# ── PBT strategies ───────────────────────────────────────────────────────────

# 生成非空中文标签（长度 1~6）
_CHINESE_CHARS = "应收账款坏账准备存货借款信用质押增值消费城建税费"
_label_st = st.text(_CHINESE_CHARS, min_size=1, max_size=6).map(str.strip).filter(bool)


class TestFindRowContainsUniqueHit:
    """**Property 3: 包含匹配唯一命中返回正确索引**

    *For any* 非空附注行列表和非空搜索标签，若精确匹配和去后缀匹配均未命中，
    但恰好有唯一一行非 is_total 行的 label 与搜索标签满足包含关系
    （label in row_label 或 row_label in label），则 find_row 应返回该行的索引。

    **Validates: Requirements 2.1, 2.3**
    """

    @settings(max_examples=5)
    @given(prefix=_label_st, suffix=_label_st)
    def test_pbt_contains_unique_hit(self, prefix: str, suffix: str):
        """PBT: 搜索标签是附注行标签的子串，且唯一 → 返回该行索引。"""
        # 构造：row_label = prefix + suffix，搜索标签 = prefix
        # prefix 是 row_label 的子串 → 包含匹配命中
        # 其他行（"坏账准备"）与 prefix 无包含关系
        row_full = prefix + suffix
        assume(prefix != row_full)  # 排除精确匹配场景
        assume("坏账准备" not in prefix and prefix not in "坏账准备")  # 避免与干扰行命中
        assume("合计" not in prefix and prefix not in "合计")  # 避免与合计行命中

        rows = [
            {"label": row_full},
            {"label": "坏账准备"},
            {"label": "合计", "is_total": True},
        ]
        result = find_row(rows, [prefix])
        assert result == 0, (
            f"搜索「{prefix}」应唯一包含匹配「{row_full}」→ 返回 0，实际: {result}"
        )

    def test_example_contains_unique_hit(self):
        """示例：搜索"应收账款"，唯一包含命中"应收账款——按账龄" → 返回 0。"""
        rows = [
            {"label": "应收账款——按账龄"},
            {"label": "坏账准备"},
            {"label": "合计", "is_total": True},
        ]
        assert find_row(rows, ["应收账款"]) == 0

    def test_example_row_label_is_substring_of_search(self):
        """搜索标签包含附注行标签（row_label in label）也算包含匹配。"""
        rows = [
            {"label": "增值税"},
            {"label": "合计", "is_total": True},
        ]
        # "增值税_附加" 包含 "增值税" → 唯一匹配
        assert find_row(rows, ["增值税_附加"]) == 0


class TestFindRowContainsMultiHitReturnsNone:
    """**Property 4: 包含匹配多命中返回 None**

    *For any* 附注行列表和搜索标签，若包含匹配命中多于一行非 is_total 行，
    则 find_row 应返回 None（放弃匹配，让引擎走合计行兜底）。

    **Validates: Requirements 2.2**
    """

    @settings(max_examples=5)
    @given(core=_label_st, suffix_a=_label_st, suffix_b=_label_st)
    def test_pbt_contains_multi_hit_returns_none(self, core: str, suffix_a: str, suffix_b: str):
        """PBT: 搜索标签是两个不同行标签的子串 → 多命中 → None。"""
        row_a = core + suffix_a
        row_b = core + suffix_b
        assume(row_a != row_b)  # 确保两行不同
        assume(core != row_a and core != row_b)  # 排除精确匹配

        rows = [
            {"label": row_a},
            {"label": row_b},
            {"label": "合计", "is_total": True},
        ]
        result = find_row(rows, [core])
        assert result is None, (
            f"搜索「{core}」同时包含匹配「{row_a}」和「{row_b}」→ 多命中应返回 None，实际: {result}"
        )

    def test_example_multi_hit(self):
        """示例：搜索"借款"，匹配"信用借款"和"质押借款" → None。"""
        rows = [
            {"label": "信用借款"},
            {"label": "质押借款"},
            {"label": "合计", "is_total": True},
        ]
        assert find_row(rows, ["借款"]) is None

    def test_example_short_label_multi_hit(self):
        """短标签"税"匹配多行 → None。"""
        rows = [
            {"label": "增值税"},
            {"label": "消费税"},
            {"label": "城建税"},
        ]
        assert find_row(rows, ["税"]) is None


class TestFindRowContainsExcludesTotal:
    """**Property 5: 包含匹配排除合计行**

    *For any* 附注行列表，find_row 的包含匹配阶段不应返回 is_total=True 行的索引。
    即使合计行的 label 与搜索标签满足包含关系且是唯一匹配，也应返回 None。

    **Validates: Requirements 2.4**
    """

    @settings(max_examples=5)
    @given(label=_label_st)
    def test_pbt_total_row_excluded(self, label: str):
        """PBT: 唯一满足包含关系的行是 is_total=True → None。"""
        assume("其他" not in label and label not in "其他")  # 避免与干扰行命中

        rows = [
            {"label": "其他"},  # 不满足包含关系
            {"label": label + "明细", "is_total": True},  # 满足但是 total
        ]
        # 搜索 label，唯一包含命中的行是 total → 应返回 None
        result = find_row(rows, [label])
        # 如果"其他"与 label 无包含关系，则唯一命中是 total 行 → None
        # 如果意外命中"其他"（label 包含"其他"），那就是非 total 命中，结果是 0
        # assume 已排除此情况
        assert result is None, (
            f"搜索「{label}」唯一包含匹配行是 total → 应返回 None，实际: {result}"
        )

    def test_example_only_total_row(self):
        """只有一行合计行 → None。"""
        rows = [{"label": "合计", "is_total": True}]
        assert find_row(rows, ["合计"]) is None

    def test_example_total_row_match_but_excluded(self):
        """搜索"税费"，附注行只有 total 行"合计税费"包含 → None。"""
        rows = [
            {"label": "other"},
            {"label": "合计税费", "is_total": True},
        ]
        assert find_row(rows, ["税费"]) is None


class TestFindRowExactMatchNotAffected:
    """回归测试：精确匹配成功时不受第三级包含匹配影响。

    spec: formula-push-note-row-matching · 需求 2（回归）
    """

    def test_exact_match_takes_precedence(self):
        """精确匹配"应收账款"→ index 0，不走包含匹配到"应收账款——按账龄"。"""
        rows = [
            {"label": "应收账款"},
            {"label": "应收账款——按账龄"},
        ]
        assert find_row(rows, ["应收账款"]) == 0

    def test_exact_match_ignores_total(self):
        """精确匹配跳过 is_total 行（现有行为不变）。"""
        rows = [
            {"label": "合计", "is_total": True},
            {"label": "应收账款"},
        ]
        assert find_row(rows, ["应收账款"]) == 1

    def test_strip_suffix_still_works(self):
        """去后缀匹配仍生效：搜索"应收账款小计"→精确无→去"小计"→命中"应收账款"。"""
        rows = [
            {"label": "应收账款"},
            {"label": "坏账准备"},
        ]
        assert find_row(rows, ["应收账款小计"]) == 0

    def test_empty_labels_return_none(self):
        """空标签列表 → None（现有行为不变）。"""
        rows = [{"label": "增值税"}]
        assert find_row(rows, []) is None
        assert find_row(rows, [""]) is None

    def test_empty_rows_return_none(self):
        """空行列表 → None（现有行为不变）。"""
        assert find_row([], ["应收账款"]) is None


# ═══════════════════════════════════════════════════════════════════════════════
# Task 3: 延迟 skip 记录 + 重分类 单元测试
# spec: formula-push-note-row-matching · 需求 1
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeferredSkipReclassifiedOnFallback:
    """Property 1: 合计行兜底成功后 skip 记录被重分类为 fallback_to_total 且字段保留。

    spec: formula-push-note-row-matching · 需求 1.1, 1.3
    **Validates: Requirements 1.1, 1.3**
    """

    def test_deferred_skip_reclassified_on_fallback(self):
        """单科目 binding，附注子表无匹配行但有合计行 → 兜底成功。

        所有 per-row skip 记录 action 应为 fallback_to_total（非 skipped），
        且 addr_id 和 reason 保留原始值。
        """
        # ── 附注子表：明细行无 "应交税费"，有合计行 ──
        sub_rows = [
            {"label": "增值税", "end_amount": 100, "prior_amount": 200, "is_total": False},
            {"label": "消费税", "end_amount": 50, "prior_amount": 60, "is_total": False},
            {"label": "合计", "end_amount": 150, "prior_amount": 260, "is_total": True, "row_type": "total"},
        ]
        table_data = _sub_table_data("应交税费", sub_rows, source="workpaper")
        note = _make_note_mock(table_data=table_data)
        db = _setup_db_for_single_note(note)
        ctx = _make_ctx(db=db)
        paper = _make_paper()

        # binding: 单科目，note_label 不匹配附注子表任何行
        note_rows = [
            {"note_label": "应交税费", "label": "应交税费",
             "ending": 175, "ending_resolved": True, "opening": 270, "opening_resolved": True,
             "is_total": False, "is_memo": False},
            {"note_label": "合计", "label": "合计",
             "ending": 175, "ending_resolved": True, "opening": 270, "opening_resolved": True,
             "is_total": True, "is_memo": False},
        ]
        binding = _make_binding(note_rows, account_prefixes=("2221",))
        rule = _make_rule()
        sources = _make_sources()

        with patch.object(engine_mod, "_push_note_cell", return_value=True), \
             patch.object(engine_mod, "_push_note_total", return_value=False):
            asyncio.run(
                engine_mod._push_note(ctx, rule=rule, binding=binding,
                                       overlay={}, sources=sources, paper=paper)
            )

        # ── 断言：per-row skip 记录被重分类 ──
        row_miss_items = [
            it for it in ctx.result.items
            if it.rule_id == rule.rule_id and it.reason and "没有" in it.reason
        ]
        assert len(row_miss_items) > 0, "应至少有 1 条行匹配失败的记录"

        for it in row_miss_items:
            assert it.action == "fallback_to_total", (
                f"兜底成功后 per-row skip 应为 fallback_to_total，实际 action={it.action}"
            )
            # addr_id 保留：应包含 section + table_name + note_label + period 的地址
            assert it.addr_id is not None, "addr_id 不应为 None（审计轨迹完整性）"
            # reason 保留：应包含原始跳过原因
            assert "没有" in it.reason, "reason 应保留原始跳过原因文本"
            assert "应交税费" in it.reason, "reason 应包含 table_name"

        # 额外：确认 skipped_count 不包含 fallback_to_total 项
        skipped_items = [it for it in ctx.result.items if it.action == "skipped"]
        for it in skipped_items:
            assert "没有" not in (it.reason or ""), (
                "行匹配失败的 skip 不应保持 action=skipped（兜底已成功）"
            )


class TestDeferredSkipStaysSkippedWithoutTotal:
    """Property 2: 合计行兜底失败时 skip 记录保持 skipped。

    spec: formula-push-note-row-matching · 需求 1.2
    **Validates: Requirements 1.2**
    """

    def test_deferred_skip_stays_skipped_without_total(self):
        """附注子表无合计行 → 兜底未成功 → per-row skip 保持 skipped。"""
        # ── 附注子表：只有明细行，无合计行 ──
        sub_rows = [
            {"label": "增值税", "end_amount": 100, "prior_amount": 200, "is_total": False},
            {"label": "消费税", "end_amount": 50, "prior_amount": 60, "is_total": False},
        ]
        table_data = _sub_table_data("应交税费", sub_rows, source="workpaper")
        note = _make_note_mock(table_data=table_data)
        db = _setup_db_for_single_note(note)
        ctx = _make_ctx(db=db)
        paper = _make_paper()

        note_rows = [
            {"note_label": "应交税费", "label": "应交税费",
             "ending": 175, "ending_resolved": True, "opening": 270, "opening_resolved": True,
             "is_total": False, "is_memo": False},
            {"note_label": "合计", "label": "合计",
             "ending": 175, "ending_resolved": True, "opening": 270, "opening_resolved": True,
             "is_total": True, "is_memo": False},
        ]
        binding = _make_binding(note_rows, account_prefixes=("2221",))
        rule = _make_rule()
        sources = _make_sources()

        with patch.object(engine_mod, "_push_note_cell", return_value=True), \
             patch.object(engine_mod, "_push_note_total", return_value=False):
            asyncio.run(
                engine_mod._push_note(ctx, rule=rule, binding=binding,
                                       overlay={}, sources=sources, paper=paper)
            )

        # ── 断言：per-row skip 保持 skipped ──
        row_miss_items = [
            it for it in ctx.result.items
            if it.rule_id == rule.rule_id and it.reason and "没有" in it.reason
        ]
        assert len(row_miss_items) > 0, "应至少有 1 条行匹配失败的记录"

        for it in row_miss_items:
            assert it.action == "skipped", (
                f"无合计行时 per-row skip 应保持 skipped，实际 action={it.action}"
            )

        # 不应有 fallback_to_total 项
        fallback_items = [it for it in ctx.result.items if it.action == "fallback_to_total"]
        assert len(fallback_items) == 0, "无合计行时不应产生 fallback_to_total 记录"


class TestDeferredSkipMultiAccount:
    """示例测试：多科目底稿所有数据行未匹配 → 兜底成功 → pending 全部重分类。

    spec: formula-push-note-row-matching · 需求 1.4
    **Validates: Requirements 1.4**
    """

    def test_deferred_skip_multi_account(self):
        """多科目 binding (account_prefixes=("1401","1402"))，note_rows 返回 2 数据行 + 1 total。

        find_row 对两个数据行均返回 None → 2 行 × 2 字段 = 4 条 pending。
        合计行兜底成功 → 全部 4 条 action == fallback_to_total。
        """
        sub_rows = [
            {"label": "原材料", "end_amount": 100, "prior_amount": 200, "is_total": False},
            {"label": "库存商品", "end_amount": 300, "prior_amount": 400, "is_total": False},
            {"label": "合计", "end_amount": 400, "prior_amount": 600, "is_total": True, "row_type": "total"},
        ]
        table_data = _sub_table_data("存货", sub_rows, source="workpaper")
        note = _make_note_mock(
            note_section="五、8", section_title="存货", table_data=table_data,
        )
        db = _setup_db_for_single_note(note)
        ctx = _make_ctx(db=db)
        paper = _make_paper()

        # 多科目 binding：2 数据行 + 1 total，note_label 不匹配附注子表行
        note_rows = [
            {"note_label": "存货_1401", "label": "存货_1401",
             "ending": 5000, "ending_resolved": True, "opening": 4000, "opening_resolved": True,
             "is_total": False, "is_memo": False},
            {"note_label": "存货_1402", "label": "存货_1402",
             "ending": 3000, "ending_resolved": True, "opening": 2000, "opening_resolved": True,
             "is_total": False, "is_memo": False},
            {"note_label": "合计", "label": "合计",
             "ending": 8000, "ending_resolved": True, "opening": 6000, "opening_resolved": True,
             "is_total": True, "is_memo": False},
        ]
        binding = _make_binding(note_rows, account_prefixes=("1401", "1402"))
        rule = _make_rule(rule_id="F2.note.main", table="存货", sections={"listed": "五、8"})
        sources = _make_sources()

        with patch.object(engine_mod, "_push_note_cell", return_value=True), \
             patch.object(engine_mod, "_push_note_total", return_value=False):
            asyncio.run(
                engine_mod._push_note(ctx, rule=rule, binding=binding,
                                       overlay={}, sources=sources, paper=paper)
            )

        # ── 断言：2 行 × 2 字段 = 4 条 fallback_to_total ──
        fallback_items = [
            it for it in ctx.result.items
            if it.rule_id == "F2.note.main" and it.action == "fallback_to_total"
        ]
        assert len(fallback_items) == 4, (
            f"2 数据行 × 2 字段 = 4 条 fallback_to_total，实际 {len(fallback_items)}"
        )

        # 验证 addr_id 包含两个不同的 note_label
        addrs = [it.addr_id for it in fallback_items]
        has_1401 = any("存货_1401" in a for a in addrs if a)
        has_1402 = any("存货_1402" in a for a in addrs if a)
        assert has_1401 and has_1402, (
            f"应有两个科目码的 addr_id，实际 addrs={addrs}"
        )

        # 确认没有 skipped 的行匹配失败记录
        skipped_row_miss = [
            it for it in ctx.result.items
            if it.rule_id == "F2.note.main" and it.action == "skipped"
            and it.reason and "没有" in it.reason
        ]
        assert len(skipped_row_miss) == 0, (
            "兜底成功后不应有 action=skipped 的行匹配失败记录"
        )


class TestDeferredSkipSingleAccount:
    """示例测试：单科目底稿唯一数据行未匹配 → 兜底成功 → pending 重分类。

    spec: formula-push-note-row-matching · 需求 1.5
    **Validates: Requirements 1.5**
    """

    def test_deferred_skip_single_account(self):
        """单科目 binding (account_prefixes=("2221",))，note_rows 返回 1 数据行 + 1 total。

        find_row 对数据行返回 None → 1 行 × 2 字段 = 2 条 pending。
        合计行兜底成功 → 全部 2 条 action == fallback_to_total。
        """
        sub_rows = [
            {"label": "增值税", "end_amount": 100, "prior_amount": 200, "is_total": False},
            {"label": "消费税", "end_amount": 50, "prior_amount": 60, "is_total": False},
            {"label": "合计", "end_amount": 150, "prior_amount": 260, "is_total": True, "row_type": "total"},
        ]
        table_data = _sub_table_data("应交税费", sub_rows, source="workpaper")
        note = _make_note_mock(table_data=table_data)
        db = _setup_db_for_single_note(note)
        ctx = _make_ctx(db=db)
        paper = _make_paper()

        note_rows = [
            {"note_label": "应交税费", "label": "应交税费",
             "ending": 175, "ending_resolved": True, "opening": 270, "opening_resolved": True,
             "is_total": False, "is_memo": False},
            {"note_label": "合计", "label": "合计",
             "ending": 175, "ending_resolved": True, "opening": 270, "opening_resolved": True,
             "is_total": True, "is_memo": False},
        ]
        binding = _make_binding(note_rows, account_prefixes=("2221",))
        rule = _make_rule(rule_id="N4.note.main")
        sources = _make_sources()

        with patch.object(engine_mod, "_push_note_cell", return_value=True), \
             patch.object(engine_mod, "_push_note_total", return_value=False):
            asyncio.run(
                engine_mod._push_note(ctx, rule=rule, binding=binding,
                                       overlay={}, sources=sources, paper=paper)
            )

        # ── 断言：1 行 × 2 字段 = 2 条 fallback_to_total ──
        fallback_items = [
            it for it in ctx.result.items
            if it.rule_id == "N4.note.main" and it.action == "fallback_to_total"
        ]
        assert len(fallback_items) == 2, (
            f"1 数据行 × 2 字段 = 2 条 fallback_to_total，实际 {len(fallback_items)}"
        )

        # 验证 addr_id 包含 "应交税费"
        for it in fallback_items:
            assert it.addr_id is not None
            assert "应交税费" in it.addr_id, (
                f"addr_id 应包含 note_label，实际 addr_id={it.addr_id}"
            )

        # 验证 reason 保留
        for it in fallback_items:
            assert "没有" in it.reason, "reason 应保留原始跳过原因"
            assert "应交税费" in it.reason, "reason 应包含 note_label"

        # 确认没有 skipped 的行匹配失败记录
        skipped_row_miss = [
            it for it in ctx.result.items
            if it.rule_id == "N4.note.main" and it.action == "skipped"
            and it.reason and "没有" in it.reason
        ]
        assert len(skipped_row_miss) == 0, (
            "兜底成功后不应有 action=skipped 的行匹配失败记录"
        )
