"""公式推送附注找行 ③ 包含匹配只认「同一项目的另一种写法」。

spec disclosure-note-template-word-realignment Task 26（和平药房重建后推送实测）。原规则只要两边互相包含且唯一就命中：2026-10-17
三个有底稿的真实项目（和平 / 安徽 / 宜宾）dry-run 里包含匹配命中 12 / 12 / 10 次，其中 6 类命中的是别的行 —— 长期股权投资 →
「减：长期股权投资减值准备」（安徽下一次推送会把 500,000.00 写进减值准备的期末列）、长期借款 / 应付债券 / 长期应收款 →
「减：一年内到期的…」、其他非流动金融资产 → 「其他」、所得税费用 → 「当期所得税费用」；其余没写进去的只是被单元格人工模式
挡住。现规则：调整 / 构成行（减： / 加： / 其中：）去掉前缀后与取数标签相同才算；其余须一边 = 另一边 + 「项 / 项目 / 净额」或
以分隔符开头的限定说明（应收账款——按账龄、固定资产_1601）。行标签取自真库表结构。
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from app.services.formula_push import note_writer as nw
from tests._formula_push_env import base_entries, make_env

_TOTALS = {"小计", "小  计", "合计", "合  计"}


def _rows(*labels: str) -> list[dict]:
    return [{"label": label, "values": [None, None], **({"is_total": True} if label in _TOTALS else {})}
            for label in labels]


_EQUITY_INVESTMENT = _rows("对子公司投资", "对合营企业投资", "对联营企业投资", "小  计", "减：长期股权投资减值准备", "合  计")
_LONG_BORROWING = _rows("质押借款", "抵押借款", "保证借款", "信用借款", "小计", "减：一年内到期的长期借款", "合计")


@pytest.mark.parametrize(("wanted", "rows"), [
    ("长期股权投资", _EQUITY_INVESTMENT),
    ("长期借款", _LONG_BORROWING),
    ("应付债券", _rows("小计", "减：一年内到期的应付债券", "合计")),
    ("长期应收款", _rows("融资租赁款", "其中：未实现融资收益", "分期收款销售商品", "分期收款提供劳务", "其他", "小计",
                         "减：1年内到期的长期应收款", "合计")),
    ("银行存款", _rows("库存现金", "其中：存放在境外的银行存款", "合计")),
    ("其他非流动金融资产", _rows("债务工具投资", "权益工具投资", "指定为以公允价值计量且其变动计入当期损益的金融资产", "其他", "合计")),
    ("资本公积", _rows("资本（或股本）溢价", "其他资本公积", "合计", "其中：国有独享资本公积")),
    ("所得税费用", _rows("当期所得税费用", "递延所得税调整", "其他", "合计")),
    ("银行存款", _rows("库存现金", "银行存款及其他货币资金", "合计")),
], ids=["equity_investment", "long_borrowing", "bonds_payable", "long_receivable", "memo_row", "other_bucket",
        "capital_reserve", "income_tax_component", "merged_row"])
def test_contains_match_does_not_land_on_another_item(wanted, rows):
    """取数行在附注里没有同名行：调整行、构成行、「其他」、合并列示的行都不是它 ⇒ 不命中（引擎再走合计行兜底或说明跳过）。

    资本公积：原规则下「其他资本公积」「其中：国有独享资本公积」同时命中 ⇒ 碰巧放弃；只排除调整行会让「其他资本公积」变成
    唯一命中、把资本公积合计写进去（本 spec 收窄时的 dry-run 实测），所以包含匹配还须是「同一项目的另一种写法」。
    """
    assert nw.find_row(rows, [wanted, wanted]) is None


@pytest.mark.parametrize(("wanted", "rows", "expected"), [
    ("其他应收款", _rows("应收利息", "应收股利", "其他应收款项", "合计"), "其他应收款项"),
    ("其他应付款", _rows("应付利息", "应付股利", "其他应付款项", "合计"), "其他应付款项"),
    ("租赁负债", _rows("租赁付款额", "减：未确认的融资费用", "重分类至一年内到期的非流动负债", "……", "租赁负债净额"), "租赁负债净额"),
    ("固定资产_1601", _rows("固定资产", "固定资产清理", "合计"), "固定资产"),          # 科目名 + 科目码
    ("应收账款", _rows("应收账款——按账龄", "坏账准备", "合计"), "应收账款——按账龄"),  # 原 spec 的用例
    ("长期股权投资减值准备", _EQUITY_INVESTMENT, "减：长期股权投资减值准备"),          # 取数就是调整项本身
    ("一年内到期的长期借款", _LONG_BORROWING, "减：一年内到期的长期借款"),
], ids=["other_receivable", "other_payable", "lease_net", "account_code_suffix", "qualified_row", "deduction_itself",
        "current_portion_itself"])
def test_contains_match_still_finds_the_same_item(wanted, rows, expected):
    index = nw.find_row(rows, [wanted])
    assert index is not None and nw.row_label(rows[index]) == expected


# ── 引擎：调整行不再被当成取数行的落点 ─────────────────────────────────────────


@pytest_asyncio.fixture
async def env(monkeypatch):
    async with make_env(monkeypatch) as e:
        await e.seed_entries(base_entries())
        yield e


@pytest.mark.asyncio
async def test_push_does_not_write_into_a_deduction_row(env):
    """原规则：「银行存款」包含于「减：使用受限的银行存款」且唯一 ⇒ 银行存款余额写进减项行，合计跟着错。"""
    table = {"name": "货币资金", "headers": ["项目", "期末余额", "期初余额"],
             "rows": _rows("库存现金", "减：使用受限的银行存款", "合计")}
    await env.add_note("五、1", {"_tables": [table], "rows": table["rows"], "headers": table["headers"],
                                 "name": table["name"]})
    result = await env.push()
    values = {r["label"]: r["values"] for r in (await env.note("五、1")).table_data["_tables"][0]["rows"]}
    assert values["减：使用受限的银行存款"] == [None, None]
    assert values["库存现金"] == [390, 203]
    assert values["合计"] == [390, 203]
    reasons = {i.reason for i in result.items if i.addr_id == "note://五、1/货币资金/银行存款.end"}
    assert reasons == {"附注「货币资金」表中没有「银行存款」行（公式推送不新建行）"}
