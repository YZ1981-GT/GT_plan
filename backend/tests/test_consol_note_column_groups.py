"""multi_header_to_column_groups 纯函数测试。

spec: consol-note-template-header-unification Task 1
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# seed 脚本不在 app 包里，直接 import 其函数
import importlib.util

_SEED_PATH = Path(__file__).resolve().parents[1] / "scripts" / "seed" / "seed_consol_note_sections.py"
_spec = importlib.util.spec_from_file_location("seed_consol_note_sections", _SEED_PATH)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
multi_header_to_column_groups = _mod.multi_header_to_column_groups

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


class TestMultiHeaderToColumnGroups:
    """纯函数 multi_header_to_column_groups 的正确性。"""

    def test_none_input(self):
        assert multi_header_to_column_groups(None) is None

    def test_empty_list(self):
        assert multi_header_to_column_groups([]) is None

    def test_single_row(self):
        """只有一行表头 ⇒ 不产生分组。"""
        assert multi_header_to_column_groups([["项目", "期末", "期初"]]) is None

    def test_two_row_receivable_aging(self):
        """应收账款账龄（五-5-1）：2 行表头 ⇒ 2 个分组。"""
        mh = [
            ["账  龄", "期末数", "", "期初数", ""],
            ["", "账面余额", "坏账准备", "账面余额", "坏账准备"],
        ]
        result = multi_header_to_column_groups(mh)
        assert result == [
            {"group": "期末数", "start": 1, "span": 2},
            {"group": "期初数", "start": 3, "span": 2},
        ]

    def test_three_row_receivable_classification(self):
        """应收账款分类（五-5-2）：3 行表头 ⇒ 2 个顶层分组。"""
        mh = [
            ["类  别", "期末数", "", "", "", "", "期初数", "", "", "", ""],
            ["", "账面余额", "", "坏账准备", "", "账面价值", "账面余额", "", "坏账准备", "", "账面价值"],
            ["", "金额", "比例(%)", "金额", "预期信用损失率(%)", "", "金额", "比例(%)", "金额", "预期信用损失率(%)", ""],
        ]
        result = multi_header_to_column_groups(mh)
        assert result == [
            {"group": "期末数", "start": 1, "span": 5},
            {"group": "期初数", "start": 6, "span": 5},
        ]

    def test_no_spanning_groups(self):
        """所有列都是独立的且第一行也独立（无多级表头结构）⇒ 每个非空列都有分组 ⇒ 返回非空。"""
        mh = [
            ["项目", "A", "B", "C"],
            ["", "a1", "b1", "c1"],
        ]
        result = multi_header_to_column_groups(mh)
        # span=1 也输出（与单体附注 _column_groups 一致）
        assert result == [
            {"group": "A", "start": 1, "span": 1},
            {"group": "B", "start": 2, "span": 1},
            {"group": "C", "start": 3, "span": 1},
        ]

    def test_mixed_span_and_standalone(self):
        """部分列有分组、部分独立（span=1 也输出）。"""
        mh = [
            ["项目", "期末数", "", "单独列", "期初数", ""],
            ["", "A", "B", "", "C", "D"],
        ]
        result = multi_header_to_column_groups(mh)
        assert result == [
            {"group": "期末数", "start": 1, "span": 2},
            {"group": "单独列", "start": 3, "span": 1},
            {"group": "期初数", "start": 4, "span": 2},
        ]


class TestSeedJsonColumnGroups:
    """验证重生成后的模板 JSON 中 multi_header 表都有正确的 _column_groups。"""

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_multi_header_tables_have_column_groups(self, std: str):
        """multi_header 非 null 且推导出 groups 的表都有 _column_groups。"""
        path = DATA_DIR / f"consol_note_sections_{std}.json"
        if not path.exists():
            pytest.skip(f"模板文件不存在: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        multi_tables = [t for t in data if t.get("multi_header")]
        for t in multi_tables:
            cg = t.get("_column_groups")
            expected = multi_header_to_column_groups(t["multi_header"])
            assert cg == expected, (
                f"{std} {t['section_id']} {t['title']}: "
                f"_column_groups={cg} != expected={expected}"
            )

    @pytest.mark.parametrize("std", ["soe", "listed"])
    def test_no_multi_header_no_column_groups(self, std: str):
        """multi_header 为 null 的表不应有 _column_groups。"""
        path = DATA_DIR / f"consol_note_sections_{std}.json"
        if not path.exists():
            pytest.skip(f"模板文件不存在: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        flat_tables = [t for t in data if not t.get("multi_header")]
        for t in flat_tables:
            assert "_column_groups" not in t, (
                f"{std} {t['section_id']} {t['title']}: "
                f"无 multi_header 却有 _column_groups"
            )


# ─── value_column 改进测试 ─────────────────────────────────────────────────────
from app.services.consol_note_formula_service import value_column


class TestValueColumnWithColumnGroups:
    """value_column 按标题行库逐列语义选列，``_column_groups``（单体附注同结构）与多级表头同口径（R6.7）。

    旧规则按分组名命中「期末…」取组首列：分组表的组首几乎都是账面余额，净额报表行种进去就是错列。
    """

    AGING = {"headers": ["账  龄", "账面余额", "坏账准备", "账面余额", "坏账准备"],
             "_column_groups": [{"group": "期末数", "start": 1, "span": 2}, {"group": "期初数", "start": 3, "span": 2}]}

    def test_gross_line_takes_gross_balance(self):
        """毛额行（应收账款 = TB('1122')）：期末数 下 账面余额 | 坏账准备 取账面余额。"""
        assert value_column(self.AGING, "balance_sheet", net=False) == (1, None)

    def test_net_line_without_book_value_column_is_not_seeded(self):
        """净额行在只有 账面余额 | 坏账准备 的表里没有列可放 ⇒ 不种（旧规则取组首 = 账面余额）。"""
        col, why = value_column(self.AGING, "balance_sheet", net=True)
        assert col is None and "没有唯一的账面价值列" in why and "期末数/账面余额" in why

    def test_measure_columns_that_are_not_balances(self):
        """利润表项目「本期金额」下 收入 | 成本：都不是余额计量 ⇒ 不种并列出候选（旧规则取组首 = 收入）。"""
        table = {"headers": ["项目", "收入", "成本", "收入", "成本"], "_column_groups": [
            {"group": "本期金额", "start": 1, "span": 2}, {"group": "上期金额", "start": 3, "span": 2}]}
        col, why = value_column(table, "income_statement", net=False)
        assert col is None and "候选：本期金额/收入、本期金额/成本" in why

    def test_two_period_groups_without_leaf_names(self):
        """组下叶子没有列名（「期末数 | 空」）：两列都只是「期末数」⇒ 分不出（旧规则取组首）。"""
        table = {"headers": ["账  龄", "期末数", "", "期初数", ""], "_column_groups": self.AGING["_column_groups"]}
        col, why = value_column(table, "balance_sheet", net=False)
        assert col is None and "不止一个" in why

    def test_flat_headers_without_groups(self):
        assert value_column({"headers": ["项目", "期末余额", "期初余额"]}, "balance_sheet", net=True) == (1, None)
        col, why = value_column({"headers": ["项目", "期末数", "", "期初数", ""]}, "balance_sheet", net=False)
        assert col is None and "空列名" in why


# ─── 端到端种子验证（复盘 ⑤） ──────────────────────────────────────────────────
from app.services.consol_note_formula_service import (
    KIND_REPORT_TOTAL,
    consol_note_tables,
    find_table,
    plan_seed,
    single_note_sections,
    total_row,
)
from app.services.consol_report_values import ReportRow

SNAPSHOT_ROWS = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "consol_report_config_snapshot.json"


def _snapshot_rows(tt: str) -> list[ReportRow]:
    snap = json.loads(SNAPSHOT_ROWS.read_text("utf-8"))[f"{tt}_consolidated"]
    return [ReportRow(t, code, name, n, f) for t, code, n, f, name in snap]


class TestMultiHeaderSeedEndToEnd:
    """显式验证 multi_header 表的 _column_groups → value_column → plan_seed 全链路。

    防止 SEED_COUNTS 基线被其他表的增减抵消时，这些表的种子静默丢失。
    """

    @pytest.mark.parametrize(
        ("section_id", "expected_formula_prefix"),
        [
            ("五-5-1", "REPORT('BS-006')"),   # 应收账款账龄表 → 报表行 BS-006
        ],
    )
    def test_soe_multi_header_table_seeds(self, section_id: str, expected_formula_prefix: str):
        """soe 五-5-1：多级表头 期末数(账面余额 | 坏账准备) → 应收账款 BS-006 = TB('1122') 是毛额 → 账面余额列 col=1。"""
        table = find_table("soe", section_id)
        assert table is not None, f"模板中找不到 {section_id}"

        # 1. _column_groups 存在
        cg = table.get("_column_groups")
        assert cg is not None, f"{section_id} 缺少 _column_groups"

        # 2. value_column 按逐列语义定位（毛额行取账面余额）
        col, why = value_column(table, "balance_sheet", net=False)
        assert col is not None, f"value_column 失败: {why}"
        assert col == 1, f"期末账面余额列应为 1，实际 {col}"

        # 3. total_row 定位合计行
        tr, tr_why = total_row(table.get("rows", []))
        assert tr is not None, f"total_row 失败: {tr_why}"

        # 4. plan_seed 产出该表的种子
        plan = plan_seed("soe", consol_note_tables("soe"), single_note_sections("soe"), _snapshot_rows("soe"))
        cells = [c for c in plan.cells if c.section_id == section_id]
        assert len(cells) >= 1, f"{section_id} 无种子（skipped: {[s for s in plan.skipped if s.get('section_id') == section_id]}）"

        # 5. 种子公式正确
        report_cells = [c for c in cells if c.kind == KIND_REPORT_TOTAL]
        assert len(report_cells) == 1, f"期望 1 个 report_total 种子，实际 {len(report_cells)}"
        assert report_cells[0].formula == expected_formula_prefix
        assert report_cells[0].row_index == tr
        assert report_cells[0].col_index == col

    def test_soe_multi_header_tables_not_skipped(self):
        """有多级表头的表都读得懂表头：不因空列名 / 报表行展开不到科目（「列不确定」）被跳过；
        跳过只因报表口径对不上计量列，原因列出候选列（R6.7）。"""
        plan = plan_seed("soe", consol_note_tables("soe"), single_note_sections("soe"), _snapshot_rows("soe"))
        tables = consol_note_tables("soe")
        cg_sections = {t["section_id"] for t in tables if t.get("_column_groups")}
        skipped_for_col = [
            s for s in plan.skipped
            if s.get("section_id") in cg_sections
            and "列不确定" in (s.get("reason") or "")
        ]
        assert skipped_for_col == [], (
            f"有 _column_groups 的表不应因'列不确定'被跳过: {skipped_for_col}"
        )
        measure_skips = [s for s in plan.skipped if s.get("section_id") in cg_sections and "没有唯一的" in s["reason"]]
        assert measure_skips and all("候选：" in s["reason"] for s in measure_skips)
