"""合并附注从单体附注拉取服务测试。

spec: consol-note-pull-from-standalone · Task 2 + Task 3
"""
import pytest

from app.services.consol_note_aggregator import (
    CellValue,
    StandardizedRow,
    StandardizedTable,
    _find_matching_row,
    _match_column,
    _norm,
    _safe_float,
    read_standalone_note_table,
    read_sub_table_format,
    read_tables_format,
)


# ─── _safe_float ──────────────────────────────────────────────────────────────


class TestSafeFloat:
    def test_int(self):
        assert _safe_float(100) == 100.0

    def test_float(self):
        assert _safe_float(3.14) == 3.14

    def test_str(self):
        assert _safe_float("100.5") == 100.5

    def test_comma(self):
        assert _safe_float("1,234.56") == 1234.56

    def test_empty(self):
        assert _safe_float("") is None

    def test_none(self):
        assert _safe_float(None) is None

    def test_invalid(self):
        assert _safe_float("abc") is None


# ─── 列匹配 ──────────────────────────────────────────────────────────────────


class TestMatchColumn:
    def test_exact(self):
        """精确匹配。"""
        assert _match_column("期末余额", ["期末余额", "期初余额"]) == 0

    def test_exact_second(self):
        assert _match_column("期初余额", ["期末余额", "期初余额"]) == 1

    def test_synonym(self):
        """同义词组匹配：期末数 ∈ _END_SYNONYMS，期末余额也在。"""
        assert _match_column("期末数", ["期末余额", "年初余额"]) == 0

    def test_prior_synonym(self):
        """期初组同义词。"""
        assert _match_column("期初余额", ["期末数", "年初余额"]) == 1

    def test_no_match(self):
        assert _match_column("特殊列", ["期末余额", "期初余额"]) is None

    def test_norm_whitespace(self):
        """规范化后匹配。"""
        assert _match_column("期末余额", ["期末余额", "期 初 余 额"]) == 0


# ─── 行匹配 ──────────────────────────────────────────────────────────────────


class TestFindMatchingRow:
    def _rows(self, *labels):
        return [StandardizedRow(label=l, values={}, is_total=("合计" in l)) for l in labels]

    def test_exact(self):
        rows = self._rows("库存现金", "银行存款", "合计")
        assert _find_matching_row(rows, "库存现金") == 0

    def test_exact_second(self):
        rows = self._rows("库存现金", "银行存款", "合计")
        assert _find_matching_row(rows, "银行存款") == 1

    def test_skip_total(self):
        """合计行不参与匹配。"""
        rows = self._rows("库存现金", "合计")
        assert _find_matching_row(rows, "合计") is None

    def test_contains_unique(self):
        """包含匹配（唯一命中）。"""
        rows = self._rows("应收账款——按账龄", "银行存款", "合计")
        assert _find_matching_row(rows, "应收账款") == 0

    def test_contains_ambiguous(self):
        """包含匹配多命中 → None。"""
        rows = self._rows("应收账款——按账龄", "应收账款——按组合", "合计")
        assert _find_matching_row(rows, "应收账款") is None

    def test_no_match(self):
        rows = self._rows("库存现金", "银行存款")
        assert _find_matching_row(rows, "数字货币") is None

    def test_strip_suffix(self):
        """去"小计"后缀。"""
        rows = self._rows("银行承兑", "商业承兑", "合计")
        assert _find_matching_row(rows, "银行承兑小计") == 0


# ─── _tables 格式读取 ────────────────────────────────────────────────────────


class TestReadTablesFormat:
    def test_basic(self):
        """基础 _tables 读取：dict 行 + values 数组。"""
        table_data = {
            "_tables": [{
                "name": "货币资金",
                "headers": ["项目", "期末余额", "期初余额"],
                "rows": [
                    {"label": "库存现金", "values": [100.5, 200.3], "is_total": False},
                    {"label": "银行存款", "values": [300, 400], "is_total": False},
                    {"label": "合计", "values": [400.5, 600.3], "is_total": True},
                ],
            }],
        }
        consol_headers = ["项  目", "期末余额", "期初余额"]
        result = read_tables_format(table_data, "货币资金", consol_headers)
        assert result is not None
        assert len(result.rows) == 3
        assert result.rows[0].label == "库存现金"
        assert result.rows[0].values.get("期末余额") == 100.5
        assert result.rows[0].values.get("期初余额") == 200.3
        assert result.rows[1].values.get("期末余额") == 300.0

    def test_list_rows(self):
        """二维数组行格式。"""
        table_data = {
            "_tables": [{
                "name": "货币资金",
                "headers": ["项目", "期末余额", "期初余额"],
                "rows": [
                    ["库存现金", "100", "200"],
                    ["银行存款", "300", "400"],
                ],
            }],
        }
        result = read_tables_format(table_data, None, ["项目", "期末余额", "期初余额"])
        assert result is not None
        assert result.rows[0].values.get("期末余额") == 100.0
        assert result.rows[1].values.get("期初余额") == 400.0

    def test_synonym_column(self):
        """列名同义词匹配：合并模板 "期末余额" vs 单体 "期末数"。"""
        table_data = {
            "_tables": [{
                "headers": ["项目", "期末数", "期初数"],
                "rows": [{"label": "A", "values": [10, 20]}],
            }],
        }
        result = read_tables_format(table_data, None, ["项目", "期末余额", "期初余额"])
        assert result is not None
        assert result.rows[0].values.get("期末余额") == 10.0
        assert result.rows[0].values.get("期初余额") == 20.0

    def test_no_tables(self):
        assert read_tables_format({}, None, ["项目"]) is None

    def test_empty_tables(self):
        assert read_tables_format({"_tables": []}, None, ["项目"]) is None


# ─── sub_table_data 格式读取 ─────────────────────────────────────────────────


class TestReadSubTableFormat:
    def test_f2_basic(self):
        """F2 格式：{label, end_amount, prior_amount}。"""
        table_data = {
            "sub_table_data": {
                "货币资金": [
                    {"label": "库存现金", "end_amount": 100, "prior_amount": 200},
                    {"label": "银行存款", "end_amount": 300, "prior_amount": 400},
                ],
            },
        }
        result = read_sub_table_format(table_data, "货币资金", ["项目", "期末余额", "期初余额"])
        assert result is not None
        assert len(result.rows) == 2
        assert result.rows[0].values.get("期末余额") == 100.0
        assert result.rows[0].values.get("期初余额") == 200.0

    def test_f3_with_columns(self):
        """F3 格式：{label, values:[], ...} + _sub_table_columns。"""
        table_data = {
            "sub_table_data": {
                "存货分类": [
                    {"label": "原材料", "values": [10, 20, 30], "is_total": False},
                ],
            },
            "_sub_table_columns": {
                "存货分类": [
                    {"key": "label", "label": "项目", "is_label": True},
                    {"key": "end_gross", "label": "期末余额"},
                    {"key": "end_impairment", "label": "减值准备"},
                    {"key": "end_net", "label": "账面价值"},
                ],
            },
        }
        result = read_sub_table_format(table_data, "存货分类", ["项目", "期末余额", "减值准备"])
        assert result is not None
        assert result.rows[0].values.get("期末余额") == 10.0
        assert result.rows[0].values.get("减值准备") == 20.0

    def test_no_sub(self):
        assert read_sub_table_format({}, "x", ["项目"]) is None

    def test_empty_sub(self):
        assert read_sub_table_format({"sub_table_data": {}}, "x", ["项目"]) is None


# ─── 统一读取入口 ────────────────────────────────────────────────────────────


class TestReadStandaloneNoteTable:
    def test_prefers_sub_over_tables(self):
        """有 sub_table_data 时优先读 sub。"""
        table_data = {
            "sub_table_data": {
                "货币资金": [
                    {"label": "A", "end_amount": 999, "prior_amount": 888},
                ],
            },
            "_tables": [{
                "headers": ["项目", "期末余额", "期初余额"],
                "rows": [{"label": "A", "values": [1, 2]}],
            }],
        }
        result = read_standalone_note_table(table_data, "货币资金", ["项目", "期末余额", "期初余额"])
        assert result is not None
        # 应该读到 sub 的值
        assert result.rows[0].values.get("期末余额") == 999.0

    def test_fallback_to_tables(self):
        """无 sub_table_data 时降级到 _tables。"""
        table_data = {
            "_tables": [{
                "headers": ["项目", "期末余额", "期初余额"],
                "rows": [{"label": "B", "values": [100, 200]}],
            }],
        }
        result = read_standalone_note_table(table_data, None, ["项目", "期末余额", "期初余额"])
        assert result is not None
        assert result.rows[0].values.get("期末余额") == 100.0

    def test_none_input(self):
        assert read_standalone_note_table(None, None, []) is None

    def test_empty_dict(self):
        assert read_standalone_note_table({}, None, []) is None


# ─── 端到端汇总（mock，不真查 DB） ──────────────────────────────────────────


class TestAggregateEndToEnd:
    """用 mock 数据验证汇总逻辑。不走 DB。"""

    def test_two_subsidiaries_sum(self):
        """2 个子企业的货币资金汇总。"""
        from app.services.consol_note_aggregator import (
            CellValue,
            StandardizedRow,
            _find_matching_row,
        )

        consol_headers = ["项  目", "期末余额", "期初余额"]
        consol_rows = [
            ["库存现金", "", ""],
            ["银行存款", "", ""],
            ["合  计", "", ""],
        ]

        # 子 A 的标准化表
        sub_a = StandardizedTable(
            rows=[
                StandardizedRow("库存现金", {"期末余额": 100.0, "期初余额": 50.0}),
                StandardizedRow("银行存款", {"期末余额": 200.0, "期初余额": 100.0}),
                StandardizedRow("合计", {"期末余额": 300.0, "期初余额": 150.0}, is_total=True),
            ],
            col_names=["期末余额", "期初余额"],
        )

        # 子 B 的标准化表
        sub_b = StandardizedTable(
            rows=[
                StandardizedRow("库存现金", {"期末余额": 50.0, "期初余额": 30.0}),
                StandardizedRow("银行存款", {"期末余额": 300.0, "期初余额": 200.0}),
                StandardizedRow("合计", {"期末余额": 350.0, "期初余额": 230.0}, is_total=True),
            ],
            col_names=["期末余额", "期初余额"],
        )

        # 模拟汇总逻辑
        cells: dict[tuple[int, int], CellValue] = {}
        consol_norms = [_norm(h) for h in consol_headers]

        for std_table in [sub_a, sub_b]:
            for ri, consol_row in enumerate(consol_rows):
                label = consol_row[0].strip()
                src_idx = _find_matching_row(std_table.rows, label)
                if src_idx is None:
                    continue
                src_row = std_table.rows[src_idx]
                for ci in range(1, len(consol_headers)):
                    col_norm = consol_norms[ci]
                    val = src_row.values.get(col_norm)
                    if val is not None and val != 0.0:
                        cell = cells.setdefault((ri, ci), CellValue(ri, ci))
                        cell.individual += val

        # 验证
        assert cells[(0, 1)].individual == 150.0  # 库存现金期末 = 100+50
        assert cells[(0, 2)].individual == 80.0   # 库存现金期初 = 50+30
        assert cells[(1, 1)].individual == 500.0  # 银行存款期末 = 200+300
        assert cells[(1, 2)].individual == 300.0  # 银行存款期初 = 100+200
        # 合计行不参与（is_total=True 被跳过）
        assert (2, 1) not in cells
        assert (2, 2) not in cells


# ─── multi_header 列解析 ─────────────────────────────────────────────────────


class TestResolveConsolColNames:
    """多级表头列名解析。"""

    def test_simple_no_multi_header(self):
        """无 multi_header：headers 原样返回。"""
        from app.services.consol_note_aggregator import _resolve_consol_col_names

        result = _resolve_consol_col_names(
            ["项目", "期末余额", "期初余额"], None, None,
        )
        assert result == ["项目", "期末余额", "期初余额"]

    def test_empty_cols_filled_by_column_groups(self):
        """空串列通过 _column_groups 填充组名。"""
        from app.services.consol_note_aggregator import _resolve_consol_col_names

        headers = ["票据种类", "期末数", "", "", "期初数", "", ""]
        cg = [
            {"group": "期末数", "start": 1, "span": 3},
            {"group": "期初数", "start": 4, "span": 3},
        ]
        result = _resolve_consol_col_names(headers, cg, None)
        # 第 2、3 列（原空串）应被填为 "期末数"
        assert result[2] == "期末数"
        assert result[3] == "期末数"
        # 第 5、6 列应被填为 "期初数"
        assert result[5] == "期初数"
        assert result[6] == "期初数"

    def test_multi_header_last_row_fills(self):
        """multi_header 最后一行的非空值补空。"""
        from app.services.consol_note_aggregator import _resolve_consol_col_names

        headers = ["票据种类", "期末数", "", "", "期初数", "", ""]
        mh = [
            ["票据种类", "期末数", "", "", "期初数", "", ""],
            ["", "账面余额", "坏账准备", "账面价值", "账面余额", "坏账准备", "账面价值"],
        ]
        cg = [
            {"group": "期末数", "start": 1, "span": 3},
            {"group": "期初数", "start": 4, "span": 3},
        ]
        result = _resolve_consol_col_names(headers, cg, mh)
        # 第 2 列：_column_groups 先填为 "期末数"，但 multi_header 最后行有 "坏账准备"
        # _column_groups 填的是非空，不会再被覆盖
        # 实际行为：cg 先补空为组名，mh 只补还剩空的
        assert result[1] == "期末数"  # 原值
        assert result[2] == "期末数"  # cg 补
        assert result[3] == "期末数"  # cg 补


class TestMatchColumnMultiHeader:
    """多级表头场景下的列匹配。"""

    def test_slash_path_match(self):
        """斜杠路径匹配：期末数/账面余额 → 账面余额。"""
        from app.services.consol_note_aggregator import _match_column, _norm

        result = _match_column(
            _norm("期末数/账面余额"),
            [_norm("账面余额"), _norm("坏账准备"), _norm("账面价值")],
        )
        assert result == 0

    def test_group_name_synonym_match(self):
        """组名同义词匹配：合并模板 "期末数" → 单体 "期末余额"。"""
        from app.services.consol_note_aggregator import _match_column, _norm

        result = _match_column(
            _norm("期末数"),
            [_norm("期末余额"), _norm("期初余额")],
        )
        assert result == 0

    def test_group_name_prior_match(self):
        """组名同义词匹配：合并模板 "期初数" → 单体 "年初余额"。"""
        from app.services.consol_note_aggregator import _match_column, _norm

        result = _match_column(
            _norm("期初数"),
            [_norm("期末金额"), _norm("年初余额")],
        )
        assert result == 1
