"""H1 固定资产 / I1 无形资产附注主表按账面价值推送（真推送引擎 + SQLite 真 ORM）。

spec formula-fetch-followup-defect-closure R6.3。和平 2025 现场（2026-10-24 dry-run 实测）：
* 八、22「固定资产」表：H1 逐码出三行（固定资产_1601 / _1602 / _1603）全撞「固定资产」行 ⇒ 都不写，
  合计按上方各行重算成 74,301,896.81（「固定资产」行是生成链写的 1601 + 1602）。
* 八、27「无形资产情况」表（国企四段合计）：三行都对不上 ⇒ 兜底把 1701 + 1702 + 1703 写进首个合计行
  「一、原价合计」= 8,471,537.70。
改后：H1 出「固定资产」= 1601 − 1602 − 1603，合计按上方各行重算；I1 按行名写四段合计，不再按「合计 = 上方各行」重算。
金额取和平 2025 真库试算表（1601 / 1602 / 1701 / 1702；1603 / 1703 无科目 = 0）。
"""
from __future__ import annotations

import copy
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.models.audit_platform_models import Adjustment, AdjustmentEntry
from app.services.formula_push.sources import TbAuditedSnapshot
from tests._formula_push_env import make_env

_TB = {
    "1601": (Decimal("46545578.07"), Decimal("46545578.07")),
    "1602": (Decimal("27722432.06"), Decimal("26260629.62")),
    "1701": (Decimal("5445065.12"), Decimal("5445065.12")),
    "1702": (Decimal("3026472.58"), Decimal("2870275.43")),
}


def _fixed_assets_note() -> dict:
    """和平 2025 八、22 原样结构（顶层表 + values 列，「固定资产」行是生成链写的 1601 + 1602）。"""
    return {
        "name": "固定资产",
        "headers": ["项目", "期末账面价值", "期初账面价值"],
        "rows": [
            {"label": "固定资产", "values": [74268010.13, 72806207.69], "is_total": False, "row_type": "data",
             "_cell_modes": {"0": "auto", "1": "auto"}},
            {"label": "固定资产清理", "values": [33886.68, 0.0], "is_total": False, "row_type": "data",
             "_cell_modes": {"0": "auto", "1": "auto"}},
            {"label": "合计", "values": [74301896.81, 72806207.69], "is_total": True, "row_type": "total"},
        ],
    }


def _block(label: str, closing: float | None, opening: float | None) -> list[dict]:
    return [
        {"label": label, "values": [opening, None, None, closing], "is_total": True, "row_type": "total"},
        {"label": "其中：土地使用权", "values": [None, None, None, None], "is_total": False, "row_type": "data",
         "_cell_modes": {"0": "manual", "1": "manual", "2": "manual", "3": "manual"}},
        {"label": "软件", "values": [None, None, None, None], "is_total": False, "row_type": "data",
         "_cell_modes": {"0": "manual", "1": "manual", "2": "manual", "3": "manual"}},
    ]


def _intangible_note() -> dict:
    """和平 2025 八、27「无形资产情况」（国企模板四段合计；首段合计被旧推送写成 1701 + 1702）。"""
    rows = (_block("一、原价合计", 8471537.7, 8315340.55) + _block("二、累计摊销合计", None, None)
            + _block("三、无形资产减值准备合计", None, None) + _block("四、账面价值合计", None, None))
    return {"name": "无形资产情况", "headers": ["项  目", "期初余额", "本期增加", "本期减少", "期末余额"],
            "rows": rows, "_source": "workpaper"}


@pytest_asyncio.fixture
async def env(monkeypatch):
    async with make_env(monkeypatch, extra_tables=(Adjustment.__table__, AdjustmentEntry.__table__)) as e:
        for code in ("H1", "I1"):
            idx, wp = uuid.uuid4(), uuid.uuid4()
            async with e.factory() as db:
                await db.execute(sa.text("INSERT INTO wp_index (id, project_id, wp_code) VALUES (:i, :p, :c)"),
                                 {"i": str(idx), "p": str(e.pid), "c": code})
                await db.execute(sa.text("INSERT INTO working_paper (id, project_id, wp_index_id) VALUES (:w, :p, :i)"),
                                 {"w": str(wp), "p": str(e.pid), "i": str(idx)})
                await db.commit()

        async def fake_load_tb(db, project_id, year, codes):
            # 与真实 load_tb_audited 同形：所求每个前缀都有键，缺科目 = 诚实的 0
            data = {}
            for c in codes:
                closing, opening = _TB.get(str(c), (Decimal("0"), Decimal("0")))
                data[str(c)] = {"期末余额": closing, "年初余额": opening, "本期发生额": closing - opening}
            return TbAuditedSnapshot(tb_data=data, available=True, company_codes=("001",))

        async def fake_template_type(db, project_id):
            return e.template_type

        e.template_type = "soe"
        monkeypatch.setattr("app.services.formula_push.bindings.balance_adj.load_tb_audited", fake_load_tb)
        monkeypatch.setattr("app.services.formula_push.bindings.balance_adj._load_template_type", fake_template_type)
        yield e


def _values(note, label: str, which: int = 0):
    rows = [r for r in note.table_data["rows"] if r["label"] == label]
    return rows[which]["values"]


@pytest.mark.asyncio
async def test_h1_note_writes_book_value_and_recomputes_total(env):
    """「固定资产」= 1601 − 1602 − 1603；「合计」= 固定资产 + 固定资产清理（按上方各行重算）。"""
    await env.add_note("八、22", _fixed_assets_note(), title="固定资产")
    result = await env.push(codes=("H1",))
    assert result.status == "succeeded"
    note = await env.note("八、22")
    assert _values(note, "固定资产") == [pytest.approx(18823146.01), pytest.approx(20284948.45)]
    assert _values(note, "固定资产清理") == [33886.68, 0.0]
    assert _values(note, "合计") == [pytest.approx(18857032.69), pytest.approx(20284948.45)]
    skipped = [i for i in result.items if i.rule_id == "H1.note.main" and i.action == "skipped"]
    assert not skipped, [i.reason for i in skipped]


@pytest.mark.asyncio
async def test_i1_note_writes_block_totals_without_total_recalc(env):
    """四段合计按行名写入；首段「一、原价合计」不被兜底写成三科目之和，也不被「合计 = 上方各行」重算成 0。"""
    await env.add_note("八、27", _intangible_note(), title="无形资产")
    result = await env.push(codes=("I1",))
    assert result.status == "succeeded"
    note = await env.note("八、27")
    # values = [期初, 本期增加, 本期减少, 期末]
    assert _values(note, "一、原价合计") == [pytest.approx(5445065.12), None, None, pytest.approx(5445065.12)]
    assert _values(note, "二、累计摊销合计") == [pytest.approx(2870275.43), None, None, pytest.approx(3026472.58)]
    assert _values(note, "三、无形资产减值准备合计") == [0.0, None, None, 0.0]
    assert _values(note, "四、账面价值合计") == [pytest.approx(2574789.69), None, None, pytest.approx(2418592.54)]
    # 分段下的「其中」明细行是人工行，不由推送写
    assert _values(note, "软件", 0) == [None, None, None, None]
    actions = [i.action for i in result.items if i.rule_id == "I1.note.main"]
    assert "fallback_to_total" not in actions


@pytest.mark.asyncio
async def test_i1_listed_matrix_table_is_left_untouched(env):
    """上市「无形资产情况」是列 = 类别、行 = 期初 / 增减 / 期末的矩阵：四段合计行名对不上 ⇒ 一格不写（不兜底写合计）。"""
    env.template_type = "listed"
    matrix = {
        "name": "无形资产情况",
        "headers": ["项目", "土地使用权", "软件", "合计"],
        "rows": [
            {"label": "一、账面原值", "values": [None, None, None]},
            {"label": "1.期初余额", "values": [None, None, None]},
            {"label": "4.期末余额", "values": [None, None, None]},
            {"label": "二、累计摊销", "values": [None, None, None]},
            {"label": "合计", "values": [None, None, None], "is_total": True},
        ],
        "_source": "workpaper",
    }
    await env.add_note("五、26", copy.deepcopy(matrix), title="无形资产")
    await env.push(codes=("I1",))
    note = await env.note("五、26")
    assert note.table_data["rows"] == matrix["rows"]
