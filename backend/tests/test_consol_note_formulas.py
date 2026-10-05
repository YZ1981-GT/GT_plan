"""合并附注公式、差额与「按公式填入」（spec consol-elimination-single-source-push 任务 7，design §七 / §十二）。

- 种子（纯函数 + 真模板）：两类公式的判定规则逐条；真库口径覆盖数钉死（``SEED_COUNTS``，与探针一致）；
- 种子落库幂等：重复种子化 0 变化；人工公式不被覆盖；人工删除的不补回；规则不再产出的种子删除；
- 求值：附注单元格与合并报表同一求值（``REPORT('BS-006')`` == 报表行），四度量之和 == 合并数，子节点贡献之和 == 合并数；
- P10：按公式填入不改手工单元格，清除待更新标记，已保存数据插删过行时按项目名定位；
- 端点：真发请求；公式增删改只允许 admin / partner / manager；附注差额与填入按项目权限（非成员 403、只读不能填入）。
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa

import tests.conftest  # noqa: F401  注册全部模型 + SQLite 方言补丁
from app.models.base import PermissionLevel, UserRole
from app.models.consol_note_data_models import ConsolNoteData
from app.models.consol_push_models import ConsolNoteFormula
from app.models.consolidation_models import EliminationEntryType
from app.services.consol_note_formula_service import (
    KIND_ACCOUNT_CODES,
    KIND_REPORT_TOTAL,
    consol_note_tables,
    fill_rows,
    note_cell_values,
    plan_seed,
    seed_note_formulas,
    single_note_sections,
    total_row,
    value_column,
)
from app.services.consol_report_values import ReportRow
from tests.test_consol_push import (  # noqa: F401  复用同一套集团与端点夹具
    Y,
    _entry,
    _persist,
    _User,
    client_for,
    db,
    factory,
    group,
)

D = Decimal
SNAPSHOT_ROWS = "tests/fixtures/consol_report_config_snapshot.json"


# ─────────────────────────────── 种子规则（纯函数） ───────────────────────────────


class TestSeedRules:
    @pytest.mark.parametrize(("headers", "rt", "col", "why"), [
        (["项  目", "期末余额", "期初余额"], "balance_sheet", 1, None),
        (["项  目", "期初余额", "本期增加", "本期减少", "期末余额"], "balance_sheet", 4, None),  # 变动表取期末，不取本期增加
        (["项  目", "本期发生额", "上期发生额"], "income_statement", 1, None),
        (["项  目", "本期<br/>增加额", "期末余额"], "balance_sheet", 2, None),
        (["票据种类", "期末数", "期初数", "", ""], "balance_sheet", None, "空列名"),  # 多级表头未展开
        (["项  目", "期末账面价值", "期末公允价值"], "balance_sheet", None, "不止一个"),
        (["项  目", "本期金额", "上期金额"], "balance_sheet", None, "没有期末列"),  # 未分配利润变动表
        (["项  目", "期末余额", "期初余额"], "income_statement", None, "没有本期列"),
    ])
    def test_value_column(self, headers, rt, col, why):
        got, reason = value_column(headers, rt)
        assert got == col and (why is None) == (reason is None) and (why is None or why in reason)

    def test_total_row(self):
        assert total_row([["库存现金"], ["合  计"], ["其中：境外"]]) == (1, None)
        assert total_row([["甲"], ["小计"], ["乙"]])[0] is None, "小计不是整表合计"
        assert "不止一个" in total_row([["合计"], ["合计"]])[1]

    def _rows(self):
        return [
            ReportRow("balance_sheet", "BS-002", "货币资金", 1, "TB('1001','期末余额') + TB('1002','期末余额') + TB('1012','期末余额')"),
            ReportRow("balance_sheet", "BS-028", "固定资产", 2, "TB('1601','期末余额') - TB('1602','期末余额')"),
            ReportRow("balance_sheet", "BS-018", "存货", 3, "SUM_TB('1400~1499','期末余额')"),
            ReportRow("balance_sheet", "BS-010", "存货", 4, "SUM_TB('1401~1499','期末余额')"),
            ReportRow("income_statement", "IS-011", "（一）投资收益", 5, "TB('6111','本期发生额')"),
            ReportRow("cash_flow_supplement", "CFSS-002", "货币资金", 6, "TB('9999','期末余额')"),  # 只认两张主表
        ]

    def test_plan_two_kinds_and_skips(self):
        tables = [
            {"section_id": "五-1-1", "parent_section": "货币资金", "title": "货币资金", "headers": ["项目", "期末余额", "期初余额"],
             "rows": [["库存现金", "", ""], ["银行存款", "", ""], ["数字货币", "", ""], ["合  计", "", ""]]},
            {"section_id": "五-2-1", "parent_section": "固定资产", "title": "固定资产", "headers": ["项目", "期末账面价值", "期初账面价值"],
             "rows": [["固定资产", "", ""], ["固定资产清理", "", ""], ["合计", "", ""]]},
            {"section_id": "五-3-1", "parent_section": "存货", "title": "存货", "headers": ["项目", "期末余额"], "rows": [["合计", ""]]},
            {"section_id": "五-4-1", "parent_section": "投资收益", "title": "投资收益", "headers": ["项目", "本期发生额"],
             "rows": [["权益法", ""], ["合计", ""]]},
            {"section_id": "五-5-1", "parent_section": "研发支出", "title": "x", "headers": ["项目", "期末余额"], "rows": [["合计", ""]]},
        ]
        single = [
            {"section_title": "货币资金", "tables": [{"name": "货币资金", "rows": [
                {"label": "库存现金", "account_codes": ["1001"]}, {"label": "银行存款", "account_codes": ["1002"]},
                {"label": "数字货币", "account_codes": ["1099"]}]}]},
            {"section_title": "固定资产", "tables": [{"name": "固定资产", "rows": [
                {"label": "固定资产", "account_codes": ["1601", "1602"]}, {"label": "固定资产清理", "account_codes": ["1606"]}]}]},
        ]
        plan = plan_seed("soe", tables, single, self._rows())
        got = {(c.section_id, c.row_index, c.col_index): (c.kind, c.formula) for c in plan.cells}
        assert got == {
            ("五-1-1", 3, 1): (KIND_REPORT_TOTAL, "REPORT('BS-002')"),
            ("五-1-1", 0, 1): (KIND_ACCOUNT_CODES, "TB('1001','期末余额')"),
            ("五-1-1", 1, 1): (KIND_ACCOUNT_CODES, "TB('1002','期末余额')"),
            ("五-2-1", 2, 1): (KIND_REPORT_TOTAL, "REPORT('BS-028')"),
            # 备抵科目按报表公式的系数取（单体模板只写了科目码）
            ("五-2-1", 0, 1): (KIND_ACCOUNT_CODES, "TB('1601','期末余额') - TB('1602','期末余额')"),
            ("五-4-1", 1, 1): (KIND_REPORT_TOTAL, "REPORT('IS-011')"),  # 行名去序号后对上；利润表项目取本期列
        }
        reasons = {s["section_id"]: s["reason"] for s in plan.skipped}
        assert "1099 不在该章报表行的取数范围内" in reasons["五-1-1"], "数字货币的科目不在报表行 ⇒ 不种"
        assert "1606 不在该章报表行的取数范围内" in reasons["五-2-1"]
        assert "同名报表行公式不一致" in reasons["五-3-1"] and "BS-018" in reasons["五-3-1"]
        assert "五-5-1" not in reasons, "没有同名报表行的章节不种、也不算跳过"


# 真模板 × 真库公式快照（2026-09-30）：两类种子的覆盖数（与真库探针 seed_plan_probe 同值）
SEED_COUNTS = {
    "soe": {"report_total": 45, "account_codes_tables": 3, "account_codes_cells": 5},
    "listed": {"report_total": 32, "account_codes_tables": 5, "account_codes_cells": 7},
}


def _snapshot_rows(template_type: str) -> list[ReportRow]:
    """真库公式快照（含行名）。不用 ``report_config_seed.json``：seed 文件的行次编码与真库错位（真库 BS-003 是
    「交易性金融资产」，seed 里是「△结算备付金」），拿 seed 的名配快照的码会种错行。"""
    import json
    from pathlib import Path

    base = Path(__file__).resolve().parents[1]
    snap = json.loads((base / SNAPSHOT_ROWS).read_text(encoding="utf-8"))[f"{template_type}_consolidated"]
    return [ReportRow(t, code, name, n, f) for t, code, n, f, name in snap]


@pytest.mark.parametrize("tt", ["soe", "listed"])
def test_seed_counts_on_real_templates(tt):
    plan = plan_seed(tt, consol_note_tables(tt), single_note_sections(tt), _snapshot_rows(tt))
    want = SEED_COUNTS[tt]
    assert plan.count(KIND_REPORT_TOTAL) == plan.tables(KIND_REPORT_TOTAL) == want["report_total"], "每章至多一个合计单元格"
    assert (plan.tables(KIND_ACCOUNT_CODES), plan.count(KIND_ACCOUNT_CODES)) == (
        want["account_codes_tables"], want["account_codes_cells"])
    cells = {(c.section_id, c.row_index, c.col_index) for c in plan.cells}
    assert len(cells) == len(plan.cells), "同一单元格不重复种"
    if tt == "soe":
        by = {(c.section_id, c.row_index): c.formula for c in plan.cells}
        assert by[("五-1-1", 4)] == "REPORT('BS-002')" and by[("五-1-1", 0)] == "TB('1001','期末余额')"
        assert by[("五-23-1", 0)] == "TB('1601','期末余额') - TB('1602','期末余额')"
        # 变动表（期初 / 本期增加 / 本期减少 / 期末）取期末列
        assert any(c.section_id.startswith("五-") and c.col_index == 4 and c.kind == KIND_REPORT_TOTAL for c in plan.cells)


# ─────────────────────────────── 种子落库（幂等 / 不覆盖人工） ───────────────────────────────


def _mini_rows():
    return [ReportRow("balance_sheet", "BS-002", "货币资金", 1,
                      "TB('1001','期末余额') + TB('1002','期末余额') + TB('1012','期末余额')")]


async def _formulas(db, tt="soe"):
    rows = (await db.execute(sa.select(ConsolNoteFormula).where(ConsolNoteFormula.template_type == tt))).scalars().all()
    return {(f.section_id, f.row_index, f.col_index): f for f in rows}


class TestSeedPersistence:
    @pytest.mark.asyncio
    async def test_idempotent_manual_kept_deleted_suppressed_stale_removed(self, db):
        first = await seed_note_formulas(db, "soe", report_rows=_mini_rows())
        await db.commit()
        # 真模板「货币资金」：合计（第 5 行）+ 库存现金 / 银行存款 / 其他货币资金三行
        assert (first.created, first.updated, first.removed) == (4, 0, 0)
        got = await _formulas(db)
        assert got[("五-1-1", 4, 1)].formula == "REPORT('BS-002')" and got[("五-1-1", 4, 1)].source == "seed"
        again = await seed_note_formulas(db, "soe", report_rows=_mini_rows())
        await db.commit()
        assert (again.created, again.updated, again.unchanged) == (0, 0, 4), "重复种子化 0 变化"

        got[("五-1-1", 0, 1)].formula, got[("五-1-1", 0, 1)].source = "TB('1001','期末余额') * 1", "manual"
        got[("五-1-1", 1, 1)].is_deleted = True   # 人工删除
        await db.commit()
        third = await seed_note_formulas(db, "soe", report_rows=_mini_rows())
        await db.commit()
        assert (third.kept_manual, third.suppressed, third.created) == (1, 1, 0)
        got = await _formulas(db)
        assert got[("五-1-1", 0, 1)].formula == "TB('1001','期末余额') * 1", "人工公式不被覆盖"
        assert got[("五-1-1", 1, 1)].is_deleted is True, "人工删除的不补回"

        # 报表配置去掉 1012 ⇒ 其他货币资金行不再满足规则 ⇒ 该种子删除；合计行的 REPORT 不受影响
        rows = [ReportRow("balance_sheet", "BS-002", "货币资金", 1, "TB('1001','期末余额') + TB('1002','期末余额')")]
        fourth = await seed_note_formulas(db, "soe", report_rows=rows)
        await db.commit()
        assert fourth.removed == 1 and ("五-1-1", 2, 1) not in await _formulas(db)
        assert any("1012 不在该章报表行的取数范围内" in s["reason"] for s in fourth.skipped)


# ─────────────────────────────── 求值（与合并报表同一口径） ───────────────────────────────


class _F:
    def __init__(self, r, c, formula, source="seed"):
        self.row_index, self.col_index, self.formula, self.source = r, c, formula, source


class TestNoteValues:
    @pytest.mark.asyncio
    async def test_report_ref_equals_report_row_and_measures_sum(self):
        # 报表行号 50 > 附注第 0 行：附注单元格必须排在全部报表行之后求值，否则 REPORT 取不到
        rows = [ReportRow("balance_sheet", "BS-006", "应收账款", 50, "TB('1122','期末余额')")]
        measures = {
            "individual": {"1122": D("400")}, "adjustment": {"1122": D("15")},
            "elim_equity": {"1122": D("-7")}, "elim_trade": {"1122": D("-50")}, "consolidated": {"1122": D("358")},
        }
        cells = await note_cell_values(rows, [
            _F(0, 1, "REPORT('BS-006')"), _F(3, 1, "TB('1122','期末余额')"), _F(1, 1, "TB('1122','年初余额')"),
            _F(2, 1, "ROW('BS-999')"),
        ], measures, children=[("A", {"1122": D("300")}), ("B", {"1122": D("58")})])
        by = {(c["row_index"], c["col_index"]): c for c in cells}
        total = by[(0, 1)]
        assert (total["individual"], total["adjustment"], total["elimination"], total["consolidated"]) == (
            "400.00", "15.00", "-57.00", "358.00")
        assert D(total["individual"]) + D(total["adjustment"]) + D(total["elimination"]) == D(total["consolidated"])
        assert total["children"] == {"A": "300.00", "B": "58.00"}
        assert sum(D(v) for v in total["children"].values()) == D(total["consolidated"]), "子节点贡献之和 = 合并数"
        assert by[(3, 1)]["consolidated"] == "358.00"
        assert by[(1, 1)]["consolidated"] is None and "年初余额" in by[(1, 1)]["note"], "口径外的列留空给原因"
        assert by[(2, 1)]["consolidated"] is None and "不存在" in by[(2, 1)]["note"]


# ─────────────────────────────── P10：按公式填入不改手工单元格 ───────────────────────────────


class TestFillRows:
    TEMPLATE = [["库存现金", "", ""], ["银行存款", "", ""], ["合  计", "", ""]]
    CELLS = [
        {"row_index": 0, "col_index": 1, "consolidated": "10.00"},
        {"row_index": 1, "col_index": 1, "consolidated": "20.00"},
        {"row_index": 2, "col_index": 1, "consolidated": "30.00"},
        {"row_index": 2, "col_index": 2, "consolidated": None, "note": "取数列「年初余额」不在合并口径内"},
    ]

    def test_p10_manual_kept_blank_reported(self):
        saved = [["库存现金", "手填", "1"], ["银行存款", "", "2"], ["合  计", "", "3"]]
        rows, summary = fill_rows(["项目", "期末", "期初"], saved, self.CELLS, {(0, 1)}, self.TEMPLATE)
        assert rows == [["库存现金", "手填", "1"], ["银行存款", "20.00", "2"], ["合  计", "30.00", "3"]]
        assert [k["row_index"] for k in summary["kept_manual"]] == [0] and summary["kept_manual"][0]["current"] == "手填"
        assert [b["col_index"] for b in summary["blank"]] == [2] and "年初余额" in summary["blank"][0]["reason"]
        assert rows[2][2] == "3", "留空的公式不覆盖原值"

    def test_rows_located_by_label_after_insert(self):
        saved = [["库存现金", "", ""], ["数字人民币", "5", ""], ["银行存款", "", ""], ["合  计", "", ""]]
        rows, summary = fill_rows(["项目", "期末", "期初"], saved, self.CELLS[:3], set(), self.TEMPLATE)
        assert [r[1] for r in rows] == ["10.00", "5", "20.00", "30.00"], "插入行后按项目名定位，不写错行"
        # 同号同名 ⇒ 直接用；同号不同名且全表同名不止一行 ⇒ 不写
        same_slot = [["库存现金", "", ""], ["银行存款", "", ""], ["银行存款", "", ""], ["合  计", "", ""]]
        rows2, _s = fill_rows(["项目", "期末", "期初"], same_slot, self.CELLS[:3], set(), self.TEMPLATE)
        assert [r[1] for r in rows2] == ["10.00", "20.00", "", "30.00"]
        shifted = [["库存现金", "", ""], ["数字人民币", "", ""], ["银行存款", "", ""], ["银行存款", "", ""], ["合  计", "", ""]]
        rows3, s3 = fill_rows(["项目", "期末", "期初"], shifted, self.CELLS[:3], set(), self.TEMPLATE)
        assert [r[1] for r in rows3] == ["10.00", "", "", "", "30.00"]
        assert [b["row_index"] for b in s3["blank"]] == [1] and "不止一个" in s3["blank"][0]["reason"]

    def test_dict_rows_preserve_shape(self):
        """对象行（dict）填入后保持 dict 形状，不被转成 list（设计 §四）。"""
        dict_rows = [
            {"label": "库存现金", "values": {"1": "", "2": "1"}},
            {"label": "银行存款", "values": {"1": "", "2": "2"}},
            {"label": "合  计", "values": {"1": "", "2": "3"}},
        ]
        rows, summary = fill_rows(["项目", "期末", "期初"], dict_rows, self.CELLS, set(), self.TEMPLATE)
        assert all(isinstance(r, dict) for r in rows), "对象行填入后仍是 dict"
        assert rows[0]["values"]["1"] == "10.00"
        assert rows[1]["values"]["1"] == "20.00"
        assert rows[2]["values"]["1"] == "30.00"
        assert rows[0]["values"]["2"] == "1", "未被公式覆盖的列保留原值"
        assert rows[0]["label"] == "库存现金", "label 键保留"

    def test_dict_rows_manual_cells_preserved(self):
        """对象行的手工保护格不被覆盖（需求 2.4）。"""
        dict_rows = [
            {"label": "库存现金", "values": {"1": "手填", "2": "1"}},
            {"label": "银行存款", "values": {"1": "", "2": "2"}},
            {"label": "合  计", "values": {"1": "", "2": "3"}},
        ]
        rows, summary = fill_rows(["项目", "期末", "期初"], dict_rows, self.CELLS, {(0, 1)}, self.TEMPLATE)
        assert rows[0]["values"]["1"] == "手填", "手工保护格原值不变"
        assert summary["kept_manual_count"] == 1
        assert len(summary["kept_manual"]) == 1
        assert summary["kept_manual"][0]["current"] == "手填"

    def test_mixed_list_and_dict_rows(self):
        """混合 list/dict 行各自保持原形状。"""
        mixed = [
            ["库存现金", "", "1"],
            {"label": "银行存款", "values": {"1": "", "2": "2"}},
            ["合  计", "", "3"],
        ]
        rows, summary = fill_rows(["项目", "期末", "期初"], mixed, self.CELLS, set(), self.TEMPLATE)
        assert isinstance(rows[0], list), "list 行保持 list"
        assert isinstance(rows[1], dict), "dict 行保持 dict"
        assert isinstance(rows[2], list), "list 行保持 list"
        assert rows[0][1] == "10.00"
        assert rows[1]["values"]["1"] == "20.00"
        assert rows[2][1] == "30.00"

    def test_kept_manual_count_in_summary(self):
        """summary 包含准确的 kept_manual_count 数量（设计 §四 需求 2.4）。"""
        saved = [["库存现金", "手填", "1"], ["银行存款", "手填2", "2"], ["合  计", "", "3"]]
        _rows, summary = fill_rows(
            ["项目", "期末", "期初"], saved, self.CELLS, {(0, 1), (1, 1)}, self.TEMPLATE,
        )
        assert summary["kept_manual_count"] == 2
        assert len(summary["kept_manual"]) == 2


# ─────────────────────────────── 真库 + 端点 ───────────────────────────────

_NF = "/api/consol-note-formulas"
_NS = "/api/consol-note-sections"


@pytest_asyncio.fixture
async def note_client(client_for):
    """在推送测试的应用上再挂合并附注两个路由。"""
    from app.routers.consol_note_formulas import router as nf_router
    from app.routers.consol_note_sections import router as ns_router

    def make(user):
        client = client_for(user)
        app = client._transport.app  # noqa: SLF001
        if not any(getattr(r, "path", "").startswith(_NF) for r in app.routes):
            app.include_router(nf_router)
            app.include_router(ns_router)
        return client

    return make


class TestEndpoints:
    @pytest.mark.asyncio
    async def test_breakdown_fill_and_crud(self, db, group, note_client):
        from app.services.consol_report_service import generate_consol_reports_sync

        admin = _User(UserRole.admin)
        g_id = group["G"].id  # 端点在同一会话里提交 ⇒ ORM 对象过期，异步会话不能懒加载 ⇒ 先取 id
        gid = str(g_id)
        db.add(_entry(group["G"], "IA-1", EliminationEntryType.internal_ar_ap,
                      [("2202", "应付账款", "50", "0"), ("1122", "应收账款", "0", "50")]))
        db.add(_entry(group["A"], "IA-A", EliminationEntryType.internal_ar_ap,
                      [("2202", "应付账款", "7", "0"), ("1122", "应收账款", "0", "7")]))
        await db.commit()
        await generate_consol_reports_sync(db, g_id, Y)
        await db.commit()
        async with note_client(admin) as c:
            # 附注公式：公式管理「合并附注」节点
            made = await c.post(_NF, json={"template_type": "soe", "section_id": "五-1-1", "row_index": 5,
                                           "col_index": 1, "formula": "TB('1122','期末余额')", "description": "试"})
            assert made.status_code == 201, made.text
            body = made.json()
            assert (body["source"], body["source_label"], body["col_name"]) == ("manual", "人工", "期末余额")
            assert body["position"].startswith("第 6 行 · 期末余额")
            dup = await c.post(_NF, json={"template_type": "soe", "section_id": "五-1-1", "row_index": 5,
                                          "col_index": 1, "formula": "TB('1001','期末余额')"})
            assert dup.status_code == 409
            for bad, why in (({"col_index": 0}, 422), ({"section_id": "不存在"}, 404),
                             ({"col_index": 9}, 400), ({"formula": "AUX('1001','客户','期末余额')"}, 400)):
                payload = {"template_type": "soe", "section_id": "五-1-1", "row_index": 6, "col_index": 1,
                           "formula": "TB('1001','期末余额')", **bad}
                assert (await c.post(_NF, json=payload)).status_code == why, bad

            listed = (await c.get(_NF, params={"template_type": "soe", "section_id": "五-1-1"})).json()
            formulas = listed["sections"][0]["formulas"]
            # 夹具的 BS-002 只取 1001 ⇒ 只有库存现金一行满足第二类（银行存款 1002 不在报表行取数范围内）
            assert [(f["row_index"], f["source"]) for f in formulas] == [
                (0, "seed"), (4, "seed"), (5, "manual")], "首次读取按需种子化"

            # 附注差额：合计 = 合并报表 BS-002；人工公式 TB('1122') 四度量
            bd = await c.get(f"{_NS}/breakdown/{gid}/{Y}/五-1-1")
            assert bd.status_code == 200, bd.text
            cells = {(x["row_index"], x["col_index"]): x for x in bd.json()["cells"]}
            report = {r["row_code"]: r for r in (await c.get(f"/api/consolidation/reports/{gid}/{Y}",
                                                              params={"report_type": "balance_sheet"})).json()}
            assert D(cells[(4, 1)]["consolidated"]) == D(report["BS-002"]["current_period_amount"]), "与合并报表同一求值"
            ar = cells[(5, 1)]
            assert (ar["individual"], ar["elimination"], ar["consolidated"]) == ("400.00", "-57.00", "343.00")
            assert D(ar["consolidated"]) == D(report["BS-006"]["current_period_amount"])
            assert sum(D(v) for v in ar["children"].values()) == D(ar["consolidated"])
            assert bd.json()["columns"][2] == {"key": "elimination", "label": "抵销"}
            sub = (await c.get(f"{_NS}/breakdown/{gid}/{Y}/五-1-1", params={"node_key": "A:consol"})).json()
            assert {(x["row_index"], x["col_index"]): x for x in sub["cells"]}[(5, 1)]["elimination"] == "-7.00"
            wrong = await c.get(f"{_NS}/breakdown/{gid}/{Y}/五-1-1", params={"standard": "listed"})
            assert wrong.status_code == 400 and "国企版" in wrong.json()["detail"]

            # P10：按公式填入 —— 手工单元格保留、清除待更新标记
            saved = [["库存现金", "手填", ""], ["银行存款", "", ""], ["其他货币资金", "", ""], ["数字货币", "", ""],
                     ["合  计", "", ""], ["其中：存放在境外的款项总额", "", ""]]
            db.add(ConsolNoteData(project_id=g_id, year=Y, section_id="五-1-1", is_stale=True,
                                  data={"headers": ["项  目", "期末余额", "期初余额"], "rows": saved,
                                        "manual_cells": [{"row": 0, "col": 1}]}))
            await db.commit()
            filled = await c.post(f"{_NS}/fill-by-formula/{gid}/{Y}/五-1-1")
            assert filled.status_code == 200, filled.text
            out = filled.json()
            assert [k["row_index"] for k in out["kept_manual"]] == [0] and out["is_stale"] is False
            # 先回滚再读：内存 SQLite 所有会话共用一个连接（StaticPool），「另开会话」看得见未提交写入，
            # 只有回滚后还在的才是已提交的
            await db.rollback()
            note = (await db.execute(sa.select(ConsolNoteData).where(
                ConsolNoteData.project_id == g_id, ConsolNoteData.section_id == "五-1-1"))).scalar_one()
            assert note.is_stale is False and note.data["rows"][0][1] == "手填", "P10：手工单元格不改（且已提交）"
            assert note.data["rows"][4][1] == cells[(4, 1)]["consolidated"]
            assert note.data["rows"][5][1] == "343.00" and note.data["manual_cells"] == [{"row": 0, "col": 1}]

            # 改 / 删
            fid = formulas[0]["id"]
            edited = (await c.put(f"{_NF}/{fid}", json={"formula": " TB('1001', '期末余额') "})).json()
            assert (edited["formula"], edited["source"]) == ("TB('1001','期末余额')", "seed"), "只差空白 ⇒ 不算改，仍是种子"
            edited = (await c.put(f"{_NF}/{fid}", json={"formula": "TB('1001','期末余额') + TB('1002','期末余额')"})).json()
            assert edited["source"] == "manual", "改公式 ⇒ 人工"
            assert (await c.delete(f"{_NF}/{fid}")).status_code == 200
            assert (await c.delete(f"{_NF}/{fid}")).status_code == 404
            reseed = (await c.post(f"{_NF}/seed", params={"template_type": "soe"})).json()
            assert reseed["suppressed"] == 1 and reseed["kept_manual"] == 0, "人工删的不补回（改过的已删）"

    @pytest.mark.asyncio
    async def test_auth(self, db, group, note_client):
        outsider = await _persist(db, _User(UserRole.auditor))
        reader = await _persist(db, _User(UserRole.auditor), [(group["G"], PermissionLevel.readonly)])
        manager = await _persist(db, _User(UserRole.manager))
        g_id = group["G"].id
        gid = str(g_id)
        body = {"template_type": "soe", "section_id": "五-1-1", "row_index": 5, "col_index": 1,
                "formula": "TB('1122','期末余额')"}
        async with note_client(outsider) as c:
            assert (await c.get(_NF, params={"template_type": "soe"})).status_code == 200, "模板级配置：登录即可读"
            assert (await c.post(_NF, json=body)).status_code == 403, "审计员不能改模板级公式"
            assert (await c.post(f"{_NF}/seed", params={"template_type": "soe"})).status_code == 403
            assert (await c.get(f"{_NS}/breakdown/{gid}/{Y}/五-1-1")).status_code == 403
            assert (await c.post(f"{_NS}/fill-by-formula/{gid}/{Y}/五-1-1")).status_code == 403
        async with note_client(reader) as c:
            assert (await c.get(f"{_NS}/breakdown/{gid}/{Y}/五-1-1")).status_code == 200
            assert (await c.post(f"{_NS}/fill-by-formula/{gid}/{Y}/五-1-1")).status_code == 403, "只读不能填入"
        async with note_client(manager) as c:
            made = await c.post(_NF, json=body)
            assert made.status_code == 201, "经理可以改公式"
            fid = made.json()["id"]
        async with note_client(outsider) as c:
            assert (await c.put(f"{_NF}/{fid}", json={"formula": "TB('1001','期末余额')"})).status_code == 403
            assert (await c.delete(f"{_NF}/{fid}")).status_code == 403
        from app.models.core import Project

        project = await db.get(Project, g_id)
        project.consol_lock = True
        await db.commit()
        admin = _User(UserRole.admin)
        async with note_client(admin) as c:
            locked = await c.post(f"{_NS}/fill-by-formula/{gid}/{Y}/五-1-1")
            assert locked.status_code == 423, "合并锁定后不能改附注数据"
