"""公式推送旧格式兜底：写编辑器显示的 ``_tables``、按表头认期末 / 期初列（spec disclosure-note-template-word-realignment Task 26）。

附注模板生成的章节没有 ``sub_table_data``：``_tables`` 是真源（编辑器、Word 导出、校验都读它），顶层 ``rows`` 只是首表镜像。
原兜底写顶层 ``rows`` 且按位置认列 ⇒ 2026-10-17 真库实测被推送过的 101 张旧格式表全部写进镜像、编辑器显示「本期无此情形」，
其中 43 张按位置会写错列。单元测试钉认列规则；引擎用例走真 SQLite + 真 ORM + 真规则 / 真 E1 binding（取数层固定源，同
``test_formula_push_engine``），数值与其 F2 用例同源（库存现金 期末 390 / 期初 203，银行存款 120 / 100）。
"""
from __future__ import annotations

import copy

import pytest
import pytest_asyncio

from app.services.formula_push import note_writer as nw
from app.services.formula_push.bindings import e1_calc
from tests._formula_push_env import base_entries, make_env

CASH, BANK = (390, 203), (120, 100)  # (期末, 期初)，与 test_formula_push_engine 的 F2 用例同一组源数据


def _table(headers: list[str], *, groups: list[dict] | None = None, width: int | None = None) -> dict:
    n = width if width is not None else len(headers) - 1
    rows = [{"label": label, "values": [None] * n} for label in ("库存现金", "银行存款")]
    rows.append({"label": "合计", "values": [None] * n, "is_total": True})
    table = {"name": "货币资金", "headers": headers, "rows": rows}
    if groups:
        table["_column_groups"] = groups
    return table


def _note(*tables: dict) -> dict:
    first = copy.deepcopy(tables[0])
    return {"_tables": [copy.deepcopy(t) for t in tables], "rows": first["rows"], "headers": first["headers"],
            "name": first["name"]}


# ── 认列规则 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("headers", "groups", "expected"), [
    (["项目"], None, ["end_amount", "prior_amount"]),                       # 没有数据列表头：沿用按位置
    (["项目", "期末余额", "期初余额"], None, ["end_amount", "prior_amount"]),
    (["项目", "期初余额", "本期增加", "本期减少", "期末余额"], None, ["prior_amount", "_col1", "_col2", "end_amount"]),
    (["项目", "年初余额", "期末余额"], None, ["prior_amount", "end_amount"]),
    (["项目", "本期发生额", "上期发生额", "计入当期非经常性损益的金额"], None, ["end_amount", "prior_amount", "_col2"]),
    (["项  目", "期 末 余 额", "期初<br/>余额"], None, ["end_amount", "prior_amount"]),       # 空白 / 换行标记不算
    (["账龄", "金额", "比例（%）", "金额", "比例（%）"],
     [{"group": "期末数", "start": 1, "span": 2}, {"group": "期初数", "start": 3, "span": 2}],
     ["end_amount", "_col1", "prior_amount", "_col3"]),
    (["借款类别", "余额", "利率区间", "余额", "利率区间"],
     [{"group": "期末余额", "start": 1, "span": 2}, {"group": "期初余额", "start": 3, "span": 2}],
     ["end_amount", "_col1", "prior_amount", "_col3"]),
    (["项目", "期末账面价值", "年初账面价值"], None, ["end_amount", "prior_amount"]),  # 底稿 K2 国企披露表的写法
    # 列名自己写明期间的价值列（上市 五、18 长期股权投资）：「减值准备期初余额」是另一计量，不抢
    (["被投资单位", "期初余额（账面价值）", "减值准备期初余额", "追加投资", "期末余额（账面价值）", "减值准备期末余额"],
     [{"group": "本期增减变动", "start": 3, "span": 1}],
     ["prior_amount", "_col1", "_col2", "end_amount", "_col4"]),
    # 跨全部数据列的分组只是表的主题（国企 八、54 设定受益计划净负债）
    (["项目", "期末数", "期初数"], [{"group": "计划资产的公允价值", "start": 1, "span": 2}],
     ["end_amount", "prior_amount"]),
])
def test_legacy_value_keys_follow_headers(headers, groups, expected):
    keys, note = nw.legacy_value_keys(_table(headers, groups=groups))
    assert (keys, note) == (expected, None)


@pytest.mark.parametrize(("headers", "groups", "missing", "mapped"), [
    # 期末组下三列金额：不知道推哪列 ⇒ 不猜
    (["项目", "账面余额", "减值准备", "账面价值", "账面余额", "减值准备", "账面价值"],
     [{"group": "期末数", "start": 1, "span": 3}, {"group": "期初数", "start": 4, "span": 3}], "期末 / 期初", {}),
    (["项目", "期末折现率区间", "期初余额"], None, "期末", {"prior_amount": 1}),  # 含「期末」字样不是期末金额列
    (["项目", "本期增加", "上期发生额"], None, "期末", {"prior_amount": 1}),      # 含「本期」字样不是本期金额列
    (["项目", "期末余额", "期末余额"], None, "期末 / 期初", {}),                  # 两个期末列 + 没有期初列
    # 余额与账面价值并列（国企 八、4 应收票据分类旧写法）：推账面余额还是账面价值定不了 ⇒ 不猜
    (["票据种类", "期末余额", "坏账准备", "期末账面价值", "年初余额", "坏账准备", "年初账面价值"],
     [{"group": "期末数", "start": 1, "span": 3}, {"group": "期初数", "start": 4, "span": 3}], "期末 / 期初", {}),
])
def test_legacy_value_keys_refuse_to_guess(headers, groups, missing, mapped):
    keys, note = nw.legacy_value_keys(_table(headers, groups=groups))
    assert {k: i for i, k in enumerate(keys) if not k.startswith("_col")} == mapped
    assert note and f"「{missing}」" in note and "不按位置猜" in note


def test_locate_table_writes_the_displayed_table_not_the_mirror():
    td = _note(_table(["项目", "期初余额", "期末余额"]))
    table, reason = nw.locate_table(td, "货币资金")
    assert reason is None
    assert table.rows is td["_tables"][0]["rows"], "要写编辑器显示的 _tables，不是顶层镜像"
    assert table.value_keys == ["prior_amount", "end_amount"]


def test_locate_table_picks_the_same_named_table():
    other = {**_table(["项目", "期末余额", "期初余额"]), "name": "受限制的货币资金明细"}
    td = _note(other, _table(["项目", "期末余额", "期初余额"]))
    table, _ = nw.locate_table(td, "货币资金")
    assert table.rows is td["_tables"][1]["rows"]
    table, _ = nw.locate_table(td, "表名对不上")
    assert table.rows is td["_tables"][0]["rows"], "对不上名字时沿用首表（原兜底写的就是首表镜像）"


def test_sync_first_table_mirror():
    td = _note(_table(["项目", "期末余额", "期初余额"]))
    td["_tables"][0]["rows"][0]["values"] = [1, 2]
    nw.sync_first_table_mirror(td)
    assert td["rows"] == td["_tables"][0]["rows"] and td["rows"] is not td["_tables"][0]["rows"]
    td["rows"] = [{"label": "不是镜像", "values": [9]}]
    nw.sync_first_table_mirror(td)
    assert td["rows"] == [{"label": "不是镜像", "values": [9]}], "标签对不上就不是镜像关系，不动"
    sub = {**_note(_table(["项目", "期末余额", "期初余额"])), "sub_table_data": {"货币资金": []}}
    before = copy.deepcopy(sub["rows"])
    sub["_tables"][0]["rows"][0]["values"] = [7, 7]
    nw.sync_first_table_mirror(sub)
    assert sub["rows"] == before, "有 sub_table_data 的章节不归旧格式管"


# ── 引擎：真推送 ────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def env(monkeypatch):
    async with make_env(monkeypatch) as e:
        await e.seed_entries(base_entries())
        yield e


def _values(td: dict, index: int = 0) -> dict[str, list]:
    return {r["label"]: r["values"] for r in td["_tables"][index]["rows"]}


@pytest.mark.asyncio
async def test_push_lands_in_displayed_table_by_header(env):
    """表头「期初余额 / 期末余额」（与位置相反）：期末数写进第 2 列，镜像跟着同步。"""
    await env.add_note("五、1", _note(_table(["项目", "期初余额", "期末余额"])))
    result = await env.push()
    td = (await env.note("五、1")).table_data
    assert _values(td) == {"库存现金": [CASH[1], CASH[0]], "银行存款": [BANK[1], BANK[0]],
                           "合计": [CASH[1] + BANK[1], CASH[0] + BANK[0]]}
    assert td["rows"] == td["_tables"][0]["rows"], "顶层镜像要与首表一致"
    assert result.note_sections == ["五、1"]


@pytest.mark.asyncio
async def test_push_heals_a_mirror_written_by_the_old_fallback(env):
    """原兜底把数写进了镜像、显示的表是空的：下一次推送写进显示的表，镜像被同步覆盖。"""
    td = _note(_table(["项目", "期末余额", "期初余额"]))
    td["rows"][0]["values"] = [999, 888]  # 旧兜底留下的、编辑器看不见的数
    await env.add_note("五、1", td)
    await env.push()
    td = (await env.note("五、1")).table_data
    assert _values(td)["库存现金"] == [CASH[0], CASH[1]]
    assert td["rows"] == td["_tables"][0]["rows"]


@pytest.mark.asyncio
async def test_push_writes_amount_columns_inside_period_groups(env):
    groups = [{"group": "期末数", "start": 1, "span": 2}, {"group": "期初数", "start": 3, "span": 2}]
    await env.add_note("五、1", _note(_table(["项目", "金额", "比例（%）", "金额", "比例（%）"], groups=groups)))
    await env.push()
    values = _values((await env.note("五、1")).table_data)
    assert values["库存现金"] == [CASH[0], None, CASH[1], None], "比例列不该被写进期初数"


@pytest.mark.asyncio
async def test_push_skips_with_reason_when_columns_are_ambiguous(env):
    groups = [{"group": "期末数", "start": 1, "span": 3}, {"group": "期初数", "start": 4, "span": 3}]
    headers = ["项目", "账面余额", "减值准备", "账面价值", "账面余额", "减值准备", "账面价值"]
    td = _note(_table(headers, groups=groups))
    await env.add_note("五、1", copy.deepcopy(td))
    result = await env.push()
    after = (await env.note("五、1")).table_data
    assert after["_tables"] == td["_tables"] and after["rows"] == td["rows"], "认不出列就一格不写"
    reasons = {i.reason for i in result.items if i.domain == "note" and i.action == "skipped"}
    assert any("找不到唯一" in (r or "") and "账面余额" in (r or "") for r in reasons), reasons
    assert result.note_sections == []


# ── 撞行：多条取数行对上附注同一行（两种形态都管）──────────────────────────────

_SPLIT = "银行存款_1002.02"  # 与真库 H1 的 固定资产_1601 / _1602 / _1603 同形（科目名 + 科目码），按限定词对上「银行存款」行


@pytest.fixture
def split_bank(monkeypatch):
    """E1 取数行里再加一条「银行存款_1002.02」：它与「银行存款」都对上附注「银行存款」行。"""
    rows = list(e1_calc.MAIN_ROWS["listed"])
    at = next(i for i, r in enumerate(rows) if r["key"] == "bank") + 1
    rows.insert(at, {"key": "bank_split", "label": _SPLIT, "note_label": None, "cross_key": "E1-adj-total-1002"})
    monkeypatch.setitem(e1_calc.MAIN_ROWS, "listed", tuple(rows))


def _bank_rows(values=(5, 6)) -> list[dict]:
    return [{"label": "库存现金", "values": [None, None]}, {"label": "银行存款", "values": list(values)},
            {"label": "合计", "values": [None, None], "is_total": True}]


def _collision_reasons(result) -> set[str]:
    return {i.addr_id for i in result.items
            if i.domain == "note" and i.action == "skipped" and "同一格不能由多条取数" in (i.reason or "")}


@pytest.mark.asyncio
async def test_rows_claimed_by_several_sources_are_not_overwritten(env, split_bank):
    """原来逐条覆盖写、后写的留下；现在撞行的格都不写，其余照推，合计按实际行重算。"""
    table = {**_table(["项目", "期末余额", "期初余额"]), "rows": _bank_rows()}
    await env.add_note("五、1", _note(table))
    result = await env.push()
    values = _values((await env.note("五、1")).table_data)
    assert values["银行存款"] == [5, 6], "撞行的格保持原值"
    assert values["库存现金"] == [CASH[0], CASH[1]]
    assert values["合计"] == [CASH[0] + 5, CASH[1] + 6]
    assert _collision_reasons(result) == {f"note://五、1/货币资金/{label}.{period}"
                                          for label in ("银行存款", _SPLIT) for period in ("end", "prior")}
    reasons = {i.reason for i in result.items if i.addr_id in _collision_reasons(result)}
    assert reasons == {f"取数行「银行存款」「{_SPLIT}」都对上附注「银行存款」行，同一格不能由多条取数覆盖写，附注保持原值"}


@pytest.mark.asyncio
async def test_collision_guard_also_covers_workpaper_shaped_notes(env, split_bank):
    rows = [{"label": "库存现金", "end_amount": 1, "prior_amount": 1},
            {"label": "银行存款", "end_amount": 5, "prior_amount": 6},
            {"label": "合计", "is_total": True, "end_amount": 0, "prior_amount": 0}]
    cols = [{"key": "label", "is_label": True}, {"key": "end_amount"}, {"key": "prior_amount"}]
    await env.add_note("五、1", {"_source": "workpaper", "_sub_table_columns": {"货币资金": cols},
                                 "sub_table_data": {"货币资金": rows}})
    result = await env.push()
    after = {r["label"]: r for r in (await env.note("五、1")).table_data["sub_table_data"]["货币资金"]}
    assert (after["银行存款"]["end_amount"], after["银行存款"]["prior_amount"]) == (5, 6)
    assert (after["库存现金"]["end_amount"], after["库存现金"]["prior_amount"]) == CASH
    assert len(_collision_reasons(result)) == 4
