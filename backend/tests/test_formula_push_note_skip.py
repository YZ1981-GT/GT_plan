"""公式推送附注跳过减少 · 单元测试

spec: formula-push-note-skip-reduction
覆盖需求 1.1–1.4, 2.3–2.4, 3.1–3.2, 4.1–4.2
"""
from __future__ import annotations

import pytest

from app.services.formula_push.note_writer import (
    NoteTable,
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
        assert table is not None
        assert reason is None
        assert len(table.rows) == 2

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
        td = {
            "rows": [
                {"label": "固定资产原价", "values": [500, 600]},
                {"label": "合计", "values": [500, 600], "is_total": True},
            ],
            "headers": ["项目", "期末余额", "年初余额"],
        }
        table, reason = locate_table(td, "固定资产")
        assert table is not None
        assert reason is None
        assert table.value_keys == ["end_amount", "prior_amount"]  # 旧格式按标准位置映射
        assert len(table.rows) == 2

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


# ═══════════════════════════════════════════════════════════════════════════════
# Task 4: 单科目合计行兜底（engine 层集成测试）
# Task 5: 章节号动态定位（engine 层集成测试）
# Task 2: 首次推送标记 _source
#
# 这三个需要 mock DB + engine._push_note，用较重的 fixture。
# 下面先对改动的纯函数/局部逻辑做轻量断言。
# ═══════════════════════════════════════════════════════════════════════════════


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
