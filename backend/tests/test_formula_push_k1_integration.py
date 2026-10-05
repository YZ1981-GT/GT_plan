"""K1（其他应收款）公式推送引擎集成测试（Task 19 · 需求 1.2~1.4, 9.3）。

SQLite 真 ORM：K1 底稿 + 条目 → 推送 → 审定合计 3 键写入。
当前 K1 只有 3 条 derived 规则（审定合计），editable 规则待后续补充。
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.services.formula_push import engine as push
from app.services.formula_push.bindings.k1 import K1Binding, K1Sources, load_k1_sources
from app.services.formula_push.sources import FormulaSources, TbAuditedSnapshot
from tests._formula_push_env import YEAR, Env, by_addr, make_env


@pytest_asyncio.fixture
async def env(monkeypatch):
    async with make_env(monkeypatch) as e:
        # 增加 K1 底稿
        k1_idx, k1_wp = uuid.uuid4(), uuid.uuid4()
        async with e.factory() as db:
            await db.execute(sa.text(
                "INSERT INTO wp_index (id, project_id, wp_code) VALUES (:i, :p, 'K1')"
            ), {"i": str(k1_idx), "p": str(e.pid)})
            await db.execute(sa.text(
                "INSERT INTO working_paper (id, project_id, wp_index_id) VALUES (:w, :p, :i)"
            ), {"w": str(k1_wp), "p": str(e.pid), "i": str(k1_idx)})
            await db.commit()
        e.k1_wp_id = k1_wp

        # Mock K1 取数
        k1_tb = TbAuditedSnapshot(
            tb_data={
                "1221": {"期末余额": Decimal("500000"), "年初余额": Decimal("300000"),
                         "本期发生额": Decimal("200000")},
                "1231": {"期末余额": Decimal("-50000"), "年初余额": Decimal("-30000"),
                         "本期发生额": Decimal("-20000")},
            },
            available=True, company_codes=("001",),
        )

        async def fake_k1_load(db, project_id, year, wp_id):
            return K1Sources(formula=FormulaSources(tb=k1_tb))

        monkeypatch.setattr(K1Binding, "load_sources", staticmethod(fake_k1_load))
        yield e


async def _seed_k1_entries(env: Env, entries: dict[str, str]) -> None:
    """给 K1 底稿种条目。"""
    async with env.factory() as db:
        for item, remark in entries.items():
            await db.execute(sa.text(
                "INSERT INTO checklist_responses (id, project_id, wp_id, item_id, remark, updated_at) "
                "VALUES (:id, :p, :w, :i, :r, :t)"
            ), {"id": str(uuid.uuid4()), "p": str(env.pid), "w": str(env.k1_wp_id), "i": item,
                "r": remark, "t": "2026-09-01 08:00:00.000000+00:00"})
        await db.commit()


async def _k1_entries(env: Env) -> dict[str, str]:
    async with env.factory() as db:
        rows = (await db.execute(sa.text(
            "SELECT item_id, remark FROM checklist_responses WHERE wp_id = :w"
        ), {"w": str(env.k1_wp_id)})).all()
    return {r[0]: r[1] for r in rows}


@pytest.mark.asyncio
async def test_k1_derived_audited_totals_are_pushed(env):
    """K1 推送后审定合计 3 键被写入，值 = Σ r0~r3 各行 (unadj+aje+rje)。"""
    # 种 K1-1 组合行条目：r0 单项计提 + r1 账龄组合
    await _seed_k1_entries(env, {
        "K1-1-receivable-r0-unadj": "100",
        "K1-1-receivable-r0-aje": "10",
        "K1-1-receivable-r0-rje": "0",
        "K1-1-receivable-r1-unadj": "200",
        "K1-1-receivable-r1-aje": "0",
        "K1-1-receivable-r1-rje": "5",
        "K1-1-baddebt-r0-unadj": "30",
        "K1-1-baddebt-r0-aje": "0",
        "K1-1-baddebt-r0-rje": "0",
        "K1-1-baddebt-r1-unadj": "20",
        "K1-1-baddebt-r1-aje": "5",
        "K1-1-baddebt-r1-rje": "0",
    })
    # 同时种 E1 条目（引擎会推 E1 + K1）
    from tests._formula_push_env import base_entries
    await env.seed_entries(base_entries())

    result = await env.push()
    k1_saved = await _k1_entries(env)

    # receivable = (100+10+0) + (200+0+5) + 0 + 0 = 315
    assert k1_saved["K1-1-audited-receivable"] == "315"
    # baddebt = (30+0+0) + (20+5+0) + 0 + 0 = 55
    assert k1_saved["K1-1-audited-baddebt"] == "55"
    # net = 315 - 55 = 260
    assert k1_saved["K1-1-audited-net"] == "260"

    # 运行状态应包含 K1 的 3 个状态
    states = await env.states()
    k1_states = {k: v for k, v in states.items() if v.rule_id.startswith("K1.")}
    assert len(k1_states) == 3
    assert all(s.state == "auto" for s in k1_states.values())


@pytest.mark.asyncio
async def test_k1_second_push_idempotent(env):
    """K1 第二次推送值不变时不产生写入。"""
    await _seed_k1_entries(env, {
        "K1-1-receivable-r0-unadj": "100",
        "K1-1-receivable-r0-aje": "0",
        "K1-1-receivable-r0-rje": "0",
    })
    from tests._formula_push_env import base_entries
    await env.seed_entries(base_entries())

    await env.push()
    before = await _k1_entries(env)
    result = await env.push()
    after = await _k1_entries(env)
    assert before == after
    # K1 的 3 项应全是 unchanged
    k1_items = [i for i in result.items if i.rule_id.startswith("K1.")]
    assert all(i.action == "unchanged" for i in k1_items)


@pytest.mark.asyncio
async def test_k1_frozen_workpaper_is_skipped(env):
    """K1 底稿冻结时不推送。"""
    await _seed_k1_entries(env, {"K1-1-receivable-r0-unadj": "100"})
    from tests._formula_push_env import base_entries
    await env.seed_entries(base_entries())

    async with env.factory() as db:
        await db.execute(sa.text(
            "UPDATE working_paper SET status = 'review_passed' WHERE id = :w"
        ), {"w": str(env.k1_wp_id)})
        await db.commit()

    result = await env.push()
    k1_saved = await _k1_entries(env)
    # 审定合计不应被写入
    assert "K1-1-audited-receivable" not in k1_saved
