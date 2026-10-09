"""K1（其他应收款）公式推送引擎集成测试（Task 19 · 需求 1.2~1.4, 9.3）。

SQLite 真 ORM：K1-2 明细 JSON → K1-1 组合未审数 → 审定合计 3 键写入。
覆盖 WORKPAPER_SAVED 事件链、editable 手工值保护、非法来源整批跳过和幂等行为。
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
    # K1 底稿阶段的 3 项 derived 结果应全是 unchanged；明细来源缺失的 source 规则会显式 skip
    k1_wp_items = [
        i for i in result.items
        if i.rule_id.startswith("K1.audited_total.") and i.domain == "workpaper"
    ]
    assert len(k1_wp_items) == 3
    assert all(i.action == "unchanged" for i in k1_wp_items)


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


async def _detail_rows_payload(rows: list[dict]) -> str:
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))


async def _push_k1_workpaper(env: Env):
    return await env.push(trigger="WORKPAPER_SAVED", wp_id=env.k1_wp_id, codes={"K1"})


@pytest.mark.asyncio
async def test_k1_detail_json_updates_combo_unadjusted_and_derived_totals(env):
    """K1-2 明细真实 JSON 经 source overlay 写 K1-1 组合数并驱动同轮审定合计。"""
    rows = [
        {"id": "d1", "endBalance": 120.126, "badDebtProvision": 12.126, "stage": 3, "nature": "往来款"},
        {"id": "d2", "endBalance": 50.12, "badDebtProvision": 5.01, "stage": 1, "nature": "保证金"},
        {"id": "d3", "endBalance": 30, "badDebtProvision": 3, "stage": 2, "nature": "其他"},
    ]
    await _seed_k1_entries(env, {
        "K1-2-detail-rows": await _detail_rows_payload(rows),
        "K1-1-receivable-r0-aje": "10",
        "K1-1-baddebt-r1-rje": "1",
    })

    first = await _push_k1_workpaper(env)
    saved_entries = await _k1_entries(env)

    assert saved_entries["K1-1-receivable-r0-unadj"] == "120.13"
    assert saved_entries["K1-1-receivable-r1-unadj"] == "80.12"
    assert saved_entries["K1-1-receivable-r2-unadj"] == "0"
    assert saved_entries["K1-1-receivable-r3-unadj"] == "0"
    assert saved_entries["K1-1-baddebt-r0-unadj"] == "12.13"
    assert saved_entries["K1-1-baddebt-r1-unadj"] == "8.01"
    assert saved_entries["K1-1-baddebt-r2-unadj"] == "0"
    assert saved_entries["K1-1-baddebt-r3-unadj"] == "0"
    assert saved_entries["K1-1-audited-receivable"] == "210.25"
    assert saved_entries["K1-1-audited-baddebt"] == "21.14"
    assert saved_entries["K1-1-audited-net"] == "189.11"

    second = await _push_k1_workpaper(env)
    assert await _k1_entries(env) == saved_entries
    combo_items = [item for item in second.items if item.rule_id.startswith("K1.detail_combo.")]
    assert len(combo_items) == 8
    assert all(item.action == "unchanged" for item in combo_items)
    assert first.status == "succeeded"


@pytest.mark.asyncio
async def test_k1_detail_push_preserves_existing_manual_combo_values(env):
    """首推时已有非空且来源不明的组合数按 editable 策略保留待确认。"""
    rows = [{"id": "d1", "endBalance": 100, "badDebtProvision": 10, "stage": 3}]
    await _seed_k1_entries(env, {
        "K1-2-detail-rows": await _detail_rows_payload(rows),
        "K1-1-receivable-r0-unadj": "777",
        "K1-1-baddebt-r0-unadj": "77",
    })

    result = await _push_k1_workpaper(env)
    saved_entries = await _k1_entries(env)
    assert saved_entries["K1-1-receivable-r0-unadj"] == "777"
    assert saved_entries["K1-1-baddebt-r0-unadj"] == "77"
    actions = {
        item.addr_id.rsplit("/", 1)[-1]: item.action
        for item in result.items
        if item.rule_id.startswith("K1.detail_combo.")
    }
    assert actions["K1-1-receivable-r0-unadj"] == "keep_pending"
    assert actions["K1-1-baddebt-r0-unadj"] == "keep_pending"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("{bad-json", id="malformed-json"),
        pytest.param("[]", id="empty-array"),
        pytest.param(
            json.dumps([
                {"id": "valid", "endBalance": 100, "badDebtProvision": 10, "stage": 3},
                {"id": "invalid", "endBalance": "oops", "badDebtProvision": 2, "stage": 1},
            ]),
            id="mixed-valid-and-invalid-rows",
        ),
    ],
)
async def test_k1_detail_missing_or_invalid_rows_do_not_zero_existing_targets(env, payload):
    """非法、空或混合来源只跳过 editable 目标，不以零或部分汇总覆盖既有组合数。"""
    await _seed_k1_entries(env, {
        "K1-2-detail-rows": payload,
        "K1-1-receivable-r0-unadj": "321",
        "K1-1-baddebt-r0-unadj": "32",
    })

    result = await _push_k1_workpaper(env)
    saved_entries = await _k1_entries(env)
    assert saved_entries["K1-1-receivable-r0-unadj"] == "321"
    assert saved_entries["K1-1-baddebt-r0-unadj"] == "32"
    skips = [item for item in result.items if item.rule_id.startswith("K1.detail_combo.")]
    assert len(skips) == 8
    assert all(item.action == "skipped" and item.reason for item in skips)


@pytest.mark.asyncio
async def test_k1_workpaper_saved_k1_2_event_runs_real_push_for_its_wp(env, monkeypatch):
    """WORKPAPER_SAVED(K1-2) 走事件 handler、只對事件 wp_id 執行 SQLite 實際推送。"""
    import app.core.database as database
    from app.models.audit_platform_schemas import EventPayload, EventType
    from app.services.formula_push import triggers

    rows = [{"id": "d1", "endBalance": 45, "badDebtProvision": 4.5, "stage": 3}]
    await _seed_k1_entries(env, {"K1-2-detail-rows": await _detail_rows_payload(rows)})
    monkeypatch.setattr(database, "async_session", env.factory)
    payload = EventPayload(
        event_type=EventType.WORKPAPER_SAVED,
        project_id=env.pid,
        year=YEAR,
        extra={"wp_code": "K1-2", "wp_id": str(env.k1_wp_id), "trigger": "checklist_response_save"},
    )

    await triggers.on_workpaper_saved(payload)
    saved_entries = await _k1_entries(env)
    assert saved_entries["K1-1-receivable-r0-unadj"] == "45"
    assert saved_entries["K1-1-baddebt-r0-unadj"] == "4.5"
    assert saved_entries["K1-1-audited-receivable"] == "45"
    assert saved_entries["K1-1-audited-baddebt"] == "4.5"
    assert saved_entries["K1-1-audited-net"] == "40.5"
    runs = await env.runs()
    assert len(runs) == 1 and runs[0].trigger_source == "WORKPAPER_SAVED"
