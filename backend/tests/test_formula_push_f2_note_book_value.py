"""F2 存货附注按账面余额 / 跌价准备 / 账面价值写「存货分类」合计行（真推送引擎 + SQLite 真 ORM + 真试算表行）。

spec formula-fetch-followup-defect-closure R6.1。原先 F2 逐码出行（映射表 1401 / 1402 / 1403 / 1405 / 1408 / 1461），
合计行把存货跌价准备按正数加进存货；码也不全（和平 2025 的库存商品在 1406、跌价准备在 1416，都不在那 6 个码里）。
试算表行取和平 2025 真库形态：1406 库存商品 + 1416 存货跌价准备；另加两套变体各自的备抵写法（1461 跌价准备、
1407 商品进销差价）与一个不同变体同码异名的行（1407 发出商品），验证按名称而不是按码归类。
"""
from __future__ import annotations

import copy
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.models.audit_platform_models import AccountCategory, TrialBalance
from tests._formula_push_env import YEAR, make_env

#: (标准码, 科目名, 期末审定数, 年初余额)
_TB_ROWS = (
    ("1406", "库存商品", "121090440.11", "155942513.42"),
    ("1416", "存货跌价准备", "3281478.91", "57777.90"),
    ("1407", "发出商品", "1000.00", "500.00"),
    ("1408", "商品进销差价", "200.00", "100.00"),
    ("1461", "存货跌价准备", "50.00", "40.00"),
    ("1499", "其他存货", "10.00", "0.00"),
    ("1501", "债权投资", "999999.00", "999999.00"),  # 区间外，不得计入
)
_END_GROSS = 121090440.11 + 1000 - 200 + 10
_END_IMPAIRMENT = 3281478.91 + 50
_PRIOR_GROSS = 155942513.42 + 500 - 100
_PRIOR_IMPAIRMENT = 57777.90 + 40

_COLS = [
    {"key": "label", "label": "项目", "is_label": True},
    {"key": "end_gross", "group": "期末数", "label": "账面余额"},
    {"key": "end_impairment", "group": "期末数", "label": "跌价准备/合同履约成本减值准备"},
    {"key": "end_net", "group": "期末数", "label": "账面价值"},
    {"key": "prior_gross", "group": "期初数", "label": "账面余额"},
    {"key": "prior_impairment", "group": "期初数", "label": "跌价准备/合同履约成本减值准备"},
    {"key": "prior_net", "group": "期初数", "label": "账面价值"},
]
_FIELDS = ("end_gross", "end_impairment", "end_net", "prior_gross", "prior_impairment", "prior_net")


def _synced_note() -> dict:
    """重药安徽 2025 形态：底稿同步写入的「存货分类」（业务键行，合计行全 0），另有一张跌价准备变动表。"""
    rows = [{"label": label, **{f: 0.0 for f in _FIELDS}} for label in ("原材料", "库存商品")]
    rows.append({"label": "合计", "is_total": True, **{f: 0.0 for f in _FIELDS}})
    movement = [{"label": "库存商品", "opening": 7.0, "ending": 8.0},
                {"label": "合计", "is_total": True, "opening": 7.0, "ending": 8.0}]
    return {
        "_source": "workpaper",
        "_sub_table_columns": {"存货分类": _COLS,
                               "存货跌价准备及合同履约成本减值准备": [
                                   {"key": "label", "is_label": True}, {"key": "opening"}, {"key": "ending"}]},
        "sub_table_data": {"存货分类": rows, "存货跌价准备及合同履约成本减值准备": movement},
    }


def _legacy_note() -> dict:
    """和平 2025 形态：模板生成的旧格式（``_tables`` + values 列，期末 / 期初两组各三列）。"""
    headers = ["项目", "账面余额", "跌价准备/合同履约成本减值准备", "账面价值",
               "账面余额", "跌价准备/合同履约成本减值准备", "账面价值"]
    rows = [{"label": "原材料", "values": [None] * 6}, {"label": "合计", "values": [None] * 6, "is_total": True}]
    table = {"name": "存货分类", "headers": headers, "rows": rows,
             "_column_groups": [{"group": "期末余额", "start": 1, "span": 3}, {"group": "期初余额", "start": 4, "span": 3}]}
    return {"name": "存货分类", "headers": headers, "rows": copy.deepcopy(rows), "_tables": [table]}


@pytest_asyncio.fixture
async def env(monkeypatch):
    async with make_env(monkeypatch, extra_tables=(TrialBalance.__table__,)) as e:
        idx, wp = uuid.uuid4(), uuid.uuid4()
        async with e.factory() as db:
            await db.execute(sa.text("INSERT INTO wp_index (id, project_id, wp_code) VALUES (:i, :p, 'F2')"),
                             {"i": str(idx), "p": str(e.pid)})
            await db.execute(sa.text("INSERT INTO working_paper (id, project_id, wp_index_id) VALUES (:w, :p, :i)"),
                             {"w": str(wp), "p": str(e.pid), "i": str(idx)})
            for code, name, audited, opening in _TB_ROWS:
                db.add(TrialBalance(project_id=e.pid, year=YEAR, company_code="001", standard_account_code=code,
                                    account_name=name, account_category=AccountCategory.asset,
                                    audited_amount=Decimal(audited), opening_balance=Decimal(opening)))
            await db.commit()

        async def fake_template_type(db, project_id):
            return e.template_type

        e.template_type = "soe"
        monkeypatch.setattr("app.services.formula_push.bindings.note_direct._load_template_type", fake_template_type)
        yield e


@pytest.mark.asyncio
async def test_synced_classification_total_gets_book_values(env):
    """底稿同步格式：合计行六列 = 区间内按名称归类的合计；明细行与跌价准备变动表不被推送改写。"""
    await env.add_note("八、10", _synced_note(), title="存货")
    result = await env.push(codes=("F2",))
    assert result.status == "succeeded"
    td = (await env.note("八、10")).table_data
    total = next(r for r in td["sub_table_data"]["存货分类"] if r["label"] == "合计")
    assert total["end_gross"] == pytest.approx(_END_GROSS)
    assert total["end_impairment"] == pytest.approx(_END_IMPAIRMENT)
    assert total["end_net"] == pytest.approx(_END_GROSS - _END_IMPAIRMENT)
    assert total["prior_gross"] == pytest.approx(_PRIOR_GROSS)
    assert total["prior_impairment"] == pytest.approx(_PRIOR_IMPAIRMENT)
    assert total["prior_net"] == pytest.approx(_PRIOR_GROSS - _PRIOR_IMPAIRMENT)
    # 明细行由底稿同步，推送不动；合计也不按「合计 = 上方各行」重算回 0
    assert next(r for r in td["sub_table_data"]["存货分类"] if r["label"] == "库存商品")["end_gross"] == 0.0
    # 跌价准备变动表（子表规则）：binding 不给它取数行 ⇒ 原先逐码行的合计（存货原值合计）被兜底写进它的
    # 合计「期初 / 期末」；现在合计只按上方各行重算（7 / 8 不变），明细行不动
    movement = {r["label"]: r for r in td["sub_table_data"]["存货跌价准备及合同履约成本减值准备"]}
    assert (movement["合计"]["opening"], movement["合计"]["ending"]) == (7.0, 8.0)
    assert movement["库存商品"] == {"label": "库存商品", "opening": 7.0, "ending": 8.0}
    f2 = [i for i in result.items if i.rule_id == "F2.note.main"]
    assert {i.action for i in f2} == {"write"} and len(f2) == 6


@pytest.mark.asyncio
async def test_listed_template_uses_same_table(env):
    env.template_type = "listed"
    await env.add_note("五、9", _synced_note(), title="存货")
    await env.push(codes=("F2",))
    total = next(r for r in (await env.note("五、9")).table_data["sub_table_data"]["存货分类"] if r["label"] == "合计")
    assert total["end_net"] == pytest.approx(_END_GROSS - _END_IMPAIRMENT)


@pytest.mark.asyncio
async def test_legacy_table_without_mapped_columns_is_left_untouched_with_reason(env):
    """旧格式三列分组表：六个字段的列认不出（期末 / 期初各三列，认列由表头库负责，见 design §6）⇒ 一格不写、逐格说明。"""
    note = _legacy_note()
    await env.add_note("八、10", copy.deepcopy(note), title="存货")
    result = await env.push(codes=("F2",))
    td = (await env.note("八、10")).table_data
    assert td["_tables"] == note["_tables"]
    skips = [i for i in result.items if i.rule_id == "F2.note.main"]
    assert len(skips) == 6 and {i.action for i in skips} == {"skipped"}
    # 原因要说清是哪一列、为什么不写（原先只说「附注表缺少「期末」列」，而表里明明有期末列）
    labels = {"期末账面余额", "期末减值准备", "期末账面价值", "期初账面余额", "期初减值准备", "期初账面价值"}
    assert {lb for i in skips for lb in labels if f"「{lb}」" in i.reason} == labels, [i.reason for i in skips]
    assert all(i.reason.startswith("附注表是旧格式（按列序存数）") and "不按位置猜" in i.reason for i in skips)


@pytest.mark.asyncio
async def test_no_inventory_accounts_writes_nothing(env):
    async with env.factory() as db:
        await db.execute(sa.text("DELETE FROM trial_balance WHERE standard_account_code < '1500'"))
        await db.commit()
    note = _synced_note()
    await env.add_note("八、10", copy.deepcopy(note), title="存货")
    result = await env.push(codes=("F2",))
    td = (await env.note("八、10")).table_data
    assert td["sub_table_data"]["存货分类"] == note["sub_table_data"]["存货分类"]
    reasons = {i.reason for i in result.items if i.rule_id == "F2.note.main"}
    assert reasons == {"底稿未取到该行数值（本项目无此科目），附注保持原值"}
