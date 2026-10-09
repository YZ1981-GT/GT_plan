"""批 C 阶段 2：K3~K7 审定表族推送集成测试。

覆盖四种行模式：
- K3 固定行+前缀（nature r0~r3，负债类）
- K4 固定行（r0~r4，has_account=False）
- K5 固定行（r0~r5，负债类）
- K6 双区块（asset r0~r6 / liab r0~r4）
- K7 动态行（负债类）

spec: formula-push-balance-adj-batch-c · 需求 C2, C4, C5, C6, C7
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.services.formula_push.bindings import PushBinding, get_binding
from app.services.formula_push.bindings.balance_adj import (
    BalanceAdjSources,
    BalanceAdjudicationBinding,
    binding_for,
)
from app.services.formula_push.sources import FormulaSources, TbAuditedSnapshot
from tests._formula_push_env import YEAR, Env, make_env


# ── 辅助 ────────────────────────────────────────────────────────────────────


def _dynamic_rows_json(*row_ids: str) -> str:
    return json.dumps(
        [{"rowId": rid, "label": f"项目{i}", "source": "manual"} for i, rid in enumerate(row_ids, 1)],
        ensure_ascii=False, separators=(",", ":"),
    )


def _make_tb(*codes_and_amounts: tuple[str, float]) -> TbAuditedSnapshot:
    """构造 TB 快照（每个科目期末/年初/发生额全用同一值简化）。"""
    tb_data = {}
    for code, amt in codes_and_amounts:
        d = Decimal(str(amt))
        tb_data[code] = {"期末余额": d, "年初余额": d / 2, "本期发生额": d / 2}
    return TbAuditedSnapshot(tb_data=tb_data, available=True, company_codes=("001",))


# ── Fixture ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def env(monkeypatch):
    async with make_env(monkeypatch) as e:
        # 为 K3~K7 各创建一张底稿
        wp_ids = {}
        for code in ("K3", "K4", "K5", "K6", "K7"):
            idx_id, wp_id = uuid.uuid4(), uuid.uuid4()
            async with e.factory() as db:
                await db.execute(sa.text(
                    "INSERT INTO wp_index (id, project_id, wp_code) VALUES (:i, :p, :c)"
                ), {"i": str(idx_id), "p": str(e.pid), "c": code})
                await db.execute(sa.text(
                    "INSERT INTO working_paper (id, project_id, wp_index_id) VALUES (:w, :p, :i)"
                ), {"w": str(wp_id), "p": str(e.pid), "i": str(idx_id)})
                await db.commit()
            wp_ids[code] = wp_id
        e.batch_c_wp_ids = wp_ids

        # Mock 各 binding 的 load_sources
        tb_map = {
            "K3": _make_tb(("2241", 100000)),
            "K4": _make_tb(("2261", 50000)),
            "K5": _make_tb(("2801", 80000)),
            "K6": _make_tb(("1481", 60000), ("2245", 40000)),
            "K7": _make_tb(("2401", 70000)),
        }

        async def fake_load(self_binding, db, project_id, year, wp_id):
            tb = tb_map.get(self_binding.wp_code, _make_tb())
            self_binding._last_tb_data = tb.tb_data if tb.available else None
            return BalanceAdjSources(formula=FormulaSources(tb=tb))

        monkeypatch.setattr(BalanceAdjudicationBinding, "load_sources", fake_load)
        yield e


async def _seed(env: Env, code: str, entries: dict[str, str]) -> None:
    """给指定科目底稿种条目。"""
    wp_id = env.batch_c_wp_ids[code]
    async with env.factory() as db:
        for item, remark in entries.items():
            await db.execute(sa.text(
                "INSERT INTO checklist_responses (id, project_id, wp_id, item_id, remark, updated_at) "
                "VALUES (:id, :p, :w, :i, :r, :t)"
            ), {"id": str(uuid.uuid4()), "p": str(env.pid), "w": str(wp_id),
                "i": item, "r": remark, "t": "2026-10-01 08:00:00.000000+00:00"})
        await db.commit()


async def _entries(env: Env, code: str) -> dict[str, str]:
    wp_id = env.batch_c_wp_ids[code]
    async with env.factory() as db:
        rows = (await db.execute(sa.text(
            "SELECT item_id, remark FROM checklist_responses WHERE wp_id = :w"
        ), {"w": str(wp_id)})).all()
    return {r[0]: r[1] for r in rows}


# ── 协议校验（参数化） ─────────────────────────────────────────────────────


@pytest.mark.parametrize("code", ["K3", "K4", "K5", "K6", "K7"])
class TestBatchCProtocol:
    """C1：K3~K7 通过 PushBinding 协议校验。"""

    def test_satisfies_protocol(self, code: str) -> None:
        b = get_binding(code)
        assert isinstance(b, PushBinding)
        assert isinstance(b, BalanceAdjudicationBinding)

    def test_has_audited_total_derivation(self, code: str) -> None:
        b = binding_for(code)
        assert f"{code.lower()}_audited_total" in b.derivations


# ── K3 固定行 + 前缀（负债类） ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k3_fixed_nature_rows_audited(env):
    """C6：K3 负债类，按 nature r0~r3 固定行汇总审定合计。"""
    from tests._formula_push_env import base_entries
    await env.seed_entries(base_entries())

    await _seed(env, "K3", {
        "K3-1-nature-r0-unadj": "20000",
        "K3-1-nature-r0-aje": "1000",
        "K3-1-nature-r0-rje": "0",
        "K3-1-nature-r1-unadj": "30000",
        "K3-1-nature-r1-aje": "0",
        "K3-1-nature-r1-rje": "500",
        # r2, r3 = 0（未填）
    })

    await env.push()
    saved = await _entries(env, "K3")
    # r0: 20000+1000+0=21000, r1: 30000+0+500=30500
    # total = 21000+30500 = 51500
    assert saved["K3-1-audited-receivable"] == "51500"
    assert saved["K3-1-audited-net"] == "51500"


# ── K4 无科目（has_account=False） ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_k4_no_account_pushes_derived_only(env):
    """C7：K4 无实体科目，推送只落 derived 合计。"""
    from tests._formula_push_env import base_entries
    await env.seed_entries(base_entries())

    await _seed(env, "K4", {
        "K4-1-r0-unadj": "10000",
        "K4-1-r0-aje": "0",
        "K4-1-r0-rje": "0",
        "K4-1-r1-unadj": "5000",
        "K4-1-r1-aje": "200",
        "K4-1-r1-rje": "0",
    })

    await env.push()
    saved = await _entries(env, "K4")
    # r0: 10000, r1: 5200, r2~r4: 0
    assert saved["K4-1-audited-receivable"] == "15200"
    assert saved["K4-1-audited-net"] == "15200"


# ── K5 固定行（负债类） ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k5_fixed_rows_audited(env):
    """C6：K5 负债类，固定 6 行汇总审定合计。"""
    from tests._formula_push_env import base_entries
    await env.seed_entries(base_entries())

    await _seed(env, "K5", {
        "K5-1-r0-unadj": "100000",
        "K5-1-r0-aje": "5000",
        "K5-1-r0-rje": "0",
        "K5-1-r3-unadj": "20000",
        "K5-1-r3-aje": "0",
        "K5-1-r3-rje": "1000",
    })

    await env.push()
    saved = await _entries(env, "K5")
    # r0: 105000, r3: 21000, rest: 0
    assert saved["K5-1-audited-receivable"] == "126000"
    assert saved["K5-1-audited-net"] == "126000"


# ── K6 双区块（资产+负债） ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k6_dual_section_audited(env):
    """C2：K6 资产侧和负债侧分别计算审定合计。"""
    from tests._formula_push_env import base_entries
    await env.seed_entries(base_entries())

    await _seed(env, "K6", {
        # asset 区块
        "K6-1-asset-r0-unadj": "30000",
        "K6-1-asset-r0-aje": "2000",
        "K6-1-asset-r0-rje": "0",
        "K6-1-asset-r2-unadj": "10000",
        "K6-1-asset-r2-aje": "0",
        "K6-1-asset-r2-rje": "500",
        # liab 区块
        "K6-1-liab-r0-unadj": "15000",
        "K6-1-liab-r0-aje": "0",
        "K6-1-liab-r0-rje": "1000",
    })

    await env.push()
    saved = await _entries(env, "K6")
    # asset: r0=32000 + r2=10500 = 42500
    assert saved["K6-1-audited-asset"] == "42500"
    # liab: r0=16000
    assert saved["K6-1-audited-liab"] == "16000"
    # 不应有 receivable/net 键
    assert "K6-1-audited-receivable" not in saved
    assert "K6-1-audited-net" not in saved


# ── K7 动态行（负债类） ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k7_dynamic_rows_audited(env):
    """C6：K7 负债类动态行汇总审定合计。"""
    from tests._formula_push_env import base_entries
    await env.seed_entries(base_entries())

    await _seed(env, "K7", {
        "K7-1-rows": _dynamic_rows_json("equip-subsidy", "rd-subsidy"),
        "K7-1-equip-subsidy-unadj": "50000",
        "K7-1-equip-subsidy-aje": "0",
        "K7-1-equip-subsidy-rje": "0",
        "K7-1-rd-subsidy-unadj": "20000",
        "K7-1-rd-subsidy-aje": "3000",
        "K7-1-rd-subsidy-rje": "0",
    })

    await env.push()
    saved = await _entries(env, "K7")
    # equip: 50000, rd: 23000
    assert saved["K7-1-audited-receivable"] == "73000"
    assert saved["K7-1-audited-net"] == "73000"


# ── 幂等性 ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k5_second_push_idempotent(env):
    """K5 第二次推送值不变时全为 unchanged。"""
    from tests._formula_push_env import base_entries
    await env.seed_entries(base_entries())

    await _seed(env, "K5", {
        "K5-1-r0-unadj": "100",
        "K5-1-r0-aje": "0",
        "K5-1-r0-rje": "0",
    })

    await env.push()
    before = await _entries(env, "K5")
    result = await env.push()
    after = await _entries(env, "K5")
    assert before == after

    k5_derived = [
        i for i in result.items
        if i.rule_id.startswith("K5.audited") and i.domain == "workpaper"
    ]
    assert all(i.action == "unchanged" for i in k5_derived)


# ── 空行 = 0 ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k4_empty_entries_pushes_zero(env):
    """K4 无条目时审定合计 = 0。"""
    from tests._formula_push_env import base_entries
    await env.seed_entries(base_entries())
    await _seed(env, "K4", {})

    await env.push()
    saved = await _entries(env, "K4")
    assert saved.get("K4-1-audited-receivable") == "0"
    assert saved.get("K4-1-audited-net") == "0"
