"""K2（其他流动资产）公式推送批 C 审定表族集成测试。

SQLite 真 ORM：K2 底稿 + 动态行条目 → 推送 → 审定合计 derived 键写入 → 幂等。

spec: formula-push-balance-adj-batch-c · 需求 C1, C3, C4
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.services.formula_push import engine as push
from app.services.formula_push.bindings.balance_adj import (
    BalanceAdjSources,
    BalanceAdjudicationBinding,
    binding_for,
)
from app.services.formula_push.sources import FormulaSources, TbAuditedSnapshot
from tests._formula_push_env import YEAR, Env, make_env


# ── 辅助 ────────────────────────────────────────────────────────────────────


def _dynamic_rows_json(*row_ids: str) -> str:
    """构造 K2-1-rows 存储值（动态行清单 JSON）。"""
    return json.dumps(
        [{"rowId": rid, "label": f"项目{i}", "source": "manual"} for i, rid in enumerate(row_ids, 1)],
        ensure_ascii=False,
        separators=(",", ":"),
    )


# ── Fixture ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def env(monkeypatch):
    async with make_env(monkeypatch) as e:
        # 增加 K2 底稿
        k2_idx, k2_wp = uuid.uuid4(), uuid.uuid4()
        async with e.factory() as db:
            await db.execute(sa.text(
                "INSERT INTO wp_index (id, project_id, wp_code) VALUES (:i, :p, 'K2')"
            ), {"i": str(k2_idx), "p": str(e.pid)})
            await db.execute(sa.text(
                "INSERT INTO working_paper (id, project_id, wp_index_id) VALUES (:w, :p, :i)"
            ), {"w": str(k2_wp), "p": str(e.pid), "i": str(k2_idx)})
            await db.commit()
        e.k2_wp_id = k2_wp

        # Mock K2 取数
        k2_tb = TbAuditedSnapshot(
            tb_data={
                "1901": {
                    "期末余额": Decimal("150000"),
                    "年初余额": Decimal("80000"),
                    "本期发生额": Decimal("70000"),
                },
            },
            available=True,
            company_codes=("001",),
        )

        async def fake_k2_load(self_binding, db, project_id, year, wp_id):
            # 缓存 TB 数据供 note_rows 使用
            self_binding._last_tb_data = k2_tb.tb_data
            return BalanceAdjSources(formula=FormulaSources(
                tb=k2_tb,
                hall_adj={"1901": {"aje_net": Decimal("3500"), "rje_net": Decimal("0")}},
            ))

        monkeypatch.setattr(
            BalanceAdjudicationBinding, "load_sources", fake_k2_load,
        )
        yield e


async def _seed_k2_entries(env: Env, entries: dict[str, str]) -> None:
    """给 K2 底稿种条目。"""
    async with env.factory() as db:
        for item, remark in entries.items():
            await db.execute(sa.text(
                "INSERT INTO checklist_responses (id, project_id, wp_id, item_id, remark, updated_at) "
                "VALUES (:id, :p, :w, :i, :r, :t)"
            ), {
                "id": str(uuid.uuid4()),
                "p": str(env.pid),
                "w": str(env.k2_wp_id),
                "i": item,
                "r": remark,
                "t": "2026-10-01 08:00:00.000000+00:00",
            })
        await db.commit()


async def _k2_entries(env: Env) -> dict[str, str]:
    """读取 K2 底稿全部条目。"""
    async with env.factory() as db:
        rows = (await db.execute(sa.text(
            "SELECT item_id, remark FROM checklist_responses WHERE wp_id = :w"
        ), {"w": str(env.k2_wp_id)})).all()
    return {r[0]: r[1] for r in rows}


# ── 协议校验 ────────────────────────────────────────────────────────────────


class TestBalanceAdjBindingProtocol:
    """C1：BalanceAdjudicationBinding 通过 PushBinding 协议校验。"""

    def test_k2_binding_satisfies_protocol(self) -> None:
        from app.services.formula_push.bindings import PushBinding, get_binding

        b = get_binding("K2")
        assert isinstance(b, PushBinding)
        assert isinstance(b, BalanceAdjudicationBinding)

    def test_k2_binding_attributes(self) -> None:
        b = binding_for("K2")
        assert b.wp_code == "K2"
        assert b.account_prefixes == ("1901",)
        assert "k2_audited_total" in b.derivations
        assert "k2_note_main" in b.derivations
        assert b.four_table_slots == frozenset()
        assert b.paper_codes == ("K2",)

    def test_unknown_code_raises(self) -> None:
        with pytest.raises(KeyError, match="不在审定表族规格中"):
            binding_for("Z99")


# ── 纯计算 ──────────────────────────────────────────────────────────────────


class TestBalanceAdjCalc:
    """C3：审定合计纯函数。"""

    def test_row_audited(self) -> None:
        from app.services.formula_push.bindings.balance_adj_calc import _round2

        from app.services.formula_push.bindings.balance_adj import (
            _dynamic_audited_total,
        )

        entries = {
            "K2-1-row1-unadj": "100.006",
            "K2-1-row1-aje": "10",
            "K2-1-row1-rje": "0",
            "K2-1-row2-unadj": "200",
            "K2-1-row2-aje": "0",
            "K2-1-row2-rje": "5.123",
        }
        total = _dynamic_audited_total(entries, "K2-1", ("row1", "row2"))
        # row1: round(110.006*100)/100 = round(11000.6)/100 = 11001/100 = 110.01
        # row2: round(205.123*100)/100 = round(20512.3)/100 = 20512/100 = 205.12
        # total: round(315.13*100)/100 = 315.13
        assert total == 315.13

    def test_empty_rows_returns_zero(self) -> None:
        from app.services.formula_push.bindings.balance_adj import (
            _dynamic_audited_total,
        )

        assert _dynamic_audited_total({}, "K2-1", ()) == 0.0

    def test_read_dynamic_row_keys(self) -> None:
        from app.services.formula_push.bindings.balance_adj import (
            _read_dynamic_row_keys,
        )

        rows_json = _dynamic_rows_json("contract-cost", "prepayment", "other")
        keys = _read_dynamic_row_keys({"K2-1-rows": rows_json}, "K2-1-rows")
        assert keys == ("contract-cost", "prepayment", "other")

    def test_read_dynamic_row_keys_empty(self) -> None:
        from app.services.formula_push.bindings.balance_adj import (
            _read_dynamic_row_keys,
        )

        assert _read_dynamic_row_keys({}, "K2-1-rows") == ()
        assert _read_dynamic_row_keys({"K2-1-rows": ""}, "K2-1-rows") == ()
        assert _read_dynamic_row_keys({"K2-1-rows": "invalid"}, "K2-1-rows") == ()


# ── 集成测试 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k2_derived_audited_totals_are_pushed(env):
    """C4：K2 推送后审定合计 2 键（receivable + net）被写入。

    K2 has_provision=False → 无 baddebt 键，net = receivable。
    """
    # 种 E1 条目（引擎会推全部已注册 binding）
    from tests._formula_push_env import base_entries

    await env.seed_entries(base_entries())

    # 种 K2-1 动态行条目：3 行
    await _seed_k2_entries(env, {
        "K2-1-rows": _dynamic_rows_json("contract-cost", "prepayment", "other"),
        "K2-1-contract-cost-unadj": "50000",
        "K2-1-contract-cost-aje": "1000",
        "K2-1-contract-cost-rje": "0",
        "K2-1-prepayment-unadj": "30000",
        "K2-1-prepayment-aje": "0",
        "K2-1-prepayment-rje": "500",
        "K2-1-other-unadj": "20000",
        "K2-1-other-aje": "0",
        "K2-1-other-rje": "0",
    })

    result = await env.push()
    k2_saved = await _k2_entries(env)

    # contract-cost: round2(50000+1000+0) = 51000
    # prepayment: round2(30000+0+500) = 30500
    # other: round2(20000+0+0) = 20000
    # receivable = round2(51000+30500+20000) = 101500
    assert k2_saved["K2-1-audited-receivable"] == "101500"
    # net = receivable（无备抵）
    assert k2_saved["K2-1-audited-net"] == "101500"
    # 不应有 baddebt 键
    assert "K2-1-audited-baddebt" not in k2_saved

    # 状态应包含 K2 的 derived 项
    states = await env.states()
    k2_states = {k: v for k, v in states.items() if v.rule_id.startswith("K2.audited")}
    assert len(k2_states) == 2
    assert all(s.state == "auto" for s in k2_states.values())


@pytest.mark.asyncio
async def test_k2_second_push_idempotent(env):
    """C4：K2 第二次推送值不变时不产生写入。"""
    from tests._formula_push_env import base_entries

    await env.seed_entries(base_entries())
    await _seed_k2_entries(env, {
        "K2-1-rows": _dynamic_rows_json("item1"),
        "K2-1-item1-unadj": "100",
        "K2-1-item1-aje": "0",
        "K2-1-item1-rje": "0",
    })

    await env.push()
    before = await _k2_entries(env)
    result = await env.push()
    after = await _k2_entries(env)
    assert before == after

    k2_wp_items = [
        i for i in result.items
        if i.rule_id.startswith("K2.audited") and i.domain == "workpaper"
    ]
    assert all(i.action == "unchanged" for i in k2_wp_items)


@pytest.mark.asyncio
async def test_k2_empty_rows_pushes_zero(env):
    """C4：无动态行时审定合计 = 0。"""
    from tests._formula_push_env import base_entries

    await env.seed_entries(base_entries())
    # K2 底稿存在但无行清单
    await _seed_k2_entries(env, {})

    result = await env.push()
    k2_saved = await _k2_entries(env)
    assert k2_saved.get("K2-1-audited-receivable") == "0"
    assert k2_saved.get("K2-1-audited-net") == "0"


@pytest.mark.asyncio
async def test_k2_frozen_workpaper_is_skipped(env):
    """C4：K2 底稿冻结时不推送。"""
    from tests._formula_push_env import base_entries

    await env.seed_entries(base_entries())
    await _seed_k2_entries(env, {
        "K2-1-rows": _dynamic_rows_json("item1"),
        "K2-1-item1-unadj": "100",
        "K2-1-item1-aje": "0",
        "K2-1-item1-rje": "0",
    })

    # 冻结 K2 底稿
    async with env.factory() as db:
        await db.execute(sa.text(
            "UPDATE working_paper SET status = 'review_passed' WHERE id = :w"
        ), {"w": str(env.k2_wp_id)})
        await db.commit()

    result = await env.push()
    k2_saved = await _k2_entries(env)
    # 审定合计不应被写入
    assert "K2-1-audited-receivable" not in k2_saved
    assert "K2-1-audited-net" not in k2_saved


@pytest.mark.asyncio
async def test_k2_tb_formula_rule_still_works(env):
    """C5：K2 切到 BalanceAdjudicationBinding 后，原有 source/formula 锚点规则仍正常执行。"""
    from tests._formula_push_env import base_entries

    await env.seed_entries(base_entries())
    await _seed_k2_entries(env, {})

    result = await env.push()
    k2_saved = await _k2_entries(env)
    # K2.tb_amount 规则仍应写入 K2-1-tb-amount
    assert "K2-1-tb-amount" in k2_saved


# ── ADJ 联动（C14） ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k2_hall_adj_ending_is_pushed(env):
    """C14：K2 推送后 hall-adj-ending 键被写入 = ADJ('1901','aje_net')。"""
    from tests._formula_push_env import base_entries

    await env.seed_entries(base_entries())
    await _seed_k2_entries(env, {})

    result = await env.push()
    k2_saved = await _k2_entries(env)
    # fixture 中 hall_adj 1901 aje_net = 3500
    assert k2_saved["K2-1-hall-adj-ending"] == "3500"


@pytest.mark.asyncio
async def test_k2_hall_adj_idempotent(env):
    """C14：ADJ 值不变时第二次推送为 unchanged。"""
    from tests._formula_push_env import base_entries

    await env.seed_entries(base_entries())
    await _seed_k2_entries(env, {})

    await env.push()
    result = await env.push()
    adj_items = [
        i for i in result.items
        if i.rule_id == "K2.hall_adj.ending" and i.domain == "workpaper"
    ]
    assert len(adj_items) == 1
    assert adj_items[0].action == "unchanged"
