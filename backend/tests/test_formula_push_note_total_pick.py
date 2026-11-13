"""账龄表多合计行的推送兜底（spec note-table-structure-formula-pull-closure R12 · ADR-8）。

判据：①有「减：…准备」行时，科目余额写它之前的账面余额合计（原先整表拒绝兜底 ⇒ 合计一直空着）
②分段合计表（「一、账面原值合计 / … / 三、账面价值合计」）仍不兜底并给出原因（2026-10-31 真库教训：
按「最终合计」兜底把原值写进了账面价值合计）③只有一个合计行时行为不变 ④端到端：账龄表推送后合计写入、
账面价值合计不写 ⑤变异反证：去掉备抵行判定，账龄表又回到不兜底。
"""
from __future__ import annotations

import pytest

from app.services.formula_push.note_total_push import pick_fallback_total


def _row(label: str, *, total: bool = False) -> dict:
    row: dict = {"label": label, "values": [None, None]}
    if total:
        row.update(is_total=True, row_type="total")
    return row


AGING = [_row("1年以内（含1年）"), _row("1至2年"), _row("小 计", total=True), _row("减：坏账准备"),
         _row("合 计", total=True)]
SEGMENTED = [_row("一、账面原值合计", total=True), _row("房屋、建筑物"), _row("二、累计折旧合计", total=True),
             _row("三、账面价值合计", total=True)]


def test_provision_row_splits_gross_and_net_totals():
    index, reason = pick_fallback_total(AGING)
    assert (index, reason) == (2, None)
    assert AGING[index]["label"] == "小 计", "科目余额是账面余额 ⇒ 写账面余额合计，不写账面价值合计"


@pytest.mark.parametrize("label", ["减：坏账准备", "减：减值准备", "减: 存货跌价准备", "减：信用减值准备"])
def test_provision_row_label_variants(label):
    rows = [_row("明细"), _row("小计", total=True), _row(label), _row("合计", total=True)]
    assert pick_fallback_total(rows)[0] == 1, label


def test_segmented_totals_still_refuse_with_a_reason():
    index, reason = pick_fallback_total(SEGMENTED)
    assert index is None
    assert reason and "3 个合计行" in reason and "账面原值合计" in reason


def test_single_total_and_no_total_unchanged():
    assert pick_fallback_total([_row("明细"), _row("合计", total=True)]) == (1, None)
    assert pick_fallback_total([_row("明细")]) == (None, None)


def test_provision_row_that_is_itself_a_total_does_not_split():
    """备抵行本身被标成合计行（有的模板这么存）⇒ 还是三个合计行，不猜。"""
    rows = [_row("明细"), _row("小计", total=True), _row("减：坏账准备", total=True), _row("合计", total=True)]
    index, reason = pick_fallback_total(rows)
    assert index is None and reason


def test_two_gross_totals_before_provision_refuse():
    rows = [_row("A"), _row("小计1", total=True), _row("B"), _row("小计2", total=True), _row("减：坏账准备"),
            _row("合计", total=True)]
    assert pick_fallback_total(rows)[0] is None, "备抵行之前有两个合计 ⇒ 分不出，不兜底"


def test_mutation_without_provision_rule_falls_back_to_refusal(monkeypatch):
    """变异反证：备抵行正则匹配不上任何行 ⇒ 账龄表回到「不兜底」（判据不是恒命中）。"""
    import re

    from app.services.formula_push import note_total_push

    monkeypatch.setattr(note_total_push, "_PROVISION_RE", re.compile(r"^不会命中$"))
    index, reason = pick_fallback_total(AGING)
    assert index is None and reason and "2 个合计行" in reason


# ── 生产路径：引擎在账龄表上真的写进账面余额合计（不是只测纯函数）──────────────────────────

def _two_total_table(name: str = "货币资金") -> dict:
    """明细行与底稿取数行名对不上（兜底分支会走到）、且有「小计 / 减：…准备 / 合计」三层的表。"""
    rows = [{"label": "与底稿对不上的行", "values": [None, None]},
            {"label": "小 计", "values": [None, None], "is_total": True, "row_type": "total"},
            {"label": "减：坏账准备", "values": [None, None]},
            {"label": "合 计", "values": [None, None], "is_total": True, "row_type": "total"}]
    table = {"name": name, "headers": ["项 目", "期末余额", "期初余额"], "rows": rows}
    return {"headers": list(table["headers"]), "rows": [dict(r) for r in rows],
            "_tables": [{**table, "rows": [dict(r) for r in rows]}]}


@pytest.mark.asyncio
async def test_engine_uses_pick_fallback_total_on_the_real_push_path(monkeypatch):
    """生产路径（引擎跑真实规则 E1.note.main_rows）：明细一个都没命中时，兜底行由 ``pick_fallback_total`` 定。

    用 E1 驱动是因为推送测试环境只给 E1 备了底稿与取数（D2 的 binding 需要真实底稿数据）；本判据要证的是
    「引擎按这个函数的返回写哪一行 / 不写」，与具体 wp_code 无关。
    """
    import sqlalchemy as sa

    from app.models.report_models import DisclosureNote
    from app.services.formula_push import engine, note_total_push
    from tests._formula_push_env import YEAR, make_env

    seen: list[list[str]] = []

    async def stored_rows(env) -> dict[str, list]:
        async with env.factory() as db:
            td = (await db.execute(sa.select(DisclosureNote.table_data).where(
                DisclosureNote.project_id == env.pid, DisclosureNote.note_section == "五、1",
            ).execution_options(populate_existing=True))).scalar_one()
        return {r["label"]: r["values"] for r in td["_tables"][0]["rows"]}

    # ① 返回「账面余额合计」行号 ⇒ 引擎写它
    async with make_env(monkeypatch) as env:
        await env.add_note("五、1", _two_total_table())

        def pick(rows):
            seen.append([note_total_push.note_writer.row_label(r) for r in rows])
            return 1, None

        monkeypatch.setattr(engine.note_total_push, "pick_fallback_total", pick)
        await env.push(skip_note_followup=True)  # 只验引擎落格；提交后的附注公式（R20）会按明细重算合计
        rows = await stored_rows(env)
    assert seen and "减：坏账准备" in seen[0], "引擎在真实推送路径上把本表行交给了 pick_fallback_total"
    assert rows["小 计"][0] is not None, "返回账面余额合计 ⇒ 这一格被写入"
    assert rows["合 计"][0] in (None, ""), "最终合计不写"

    # ② 返回「不兜底 + 原因」⇒ 一格不写，原因进回执
    async with make_env(monkeypatch) as env2:
        await env2.add_note("五、1", _two_total_table())
        monkeypatch.setattr(engine.note_total_push, "pick_fallback_total", lambda rows: (None, "就是不兜底"))
        result = await env2.push(skip_note_followup=True)
        rows2 = await stored_rows(env2)
    assert all(v[0] in (None, "") for v in rows2.values()), "不兜底 ⇒ 这张表一格都不写"
    assert any("就是不兜底" in (i.reason or "") for i in result.items), "原因如实进回执"
    assert YEAR == 2025
