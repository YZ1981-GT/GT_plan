"""K1 / I3 附注推送 SQLite 真 ORM 集成测试。

spec: formula-push-note-rollout-batch-c · Task 6

验证推送引擎 ``run_and_commit`` 全链路：
- K1：seed DisclosureNote(五、8) + TB + entries → push → 附注表 end_amount / prior_amount 正确
- I3：seed DisclosureNote(五、28) + TB → push → 附注表 end_amount / prior_amount 正确
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.models.report_models import ContentType, DisclosureNote, NoteStatus
from app.services.formula_push import engine as push
from app.services.formula_push.bindings.k1 import K1Binding, K1Sources
from app.services.formula_push.sources import FormulaSources, TbAuditedSnapshot
from tests._formula_push_env import YEAR, Env, base_entries, make_env

# ── 附注 table_data 骨架 ──────────────────────────────────────────────────

NOTE_COLS_K1 = [
    {"key": "label", "flat": True, "label": "项目", "is_label": True},
    {"key": "end_amount", "label": "期末余额", "format": "amount"},
    {"key": "prior_amount", "label": "上年年末余额", "format": "amount"},
]

NOTE_COLS_I3 = [
    {"key": "label", "flat": True, "label": "项目", "is_label": True},
    {"key": "end_amount", "label": "期末余额", "format": "amount"},
    {"key": "prior_amount", "label": "期初余额", "format": "amount"},
]


def _k1_note_data() -> dict:
    """上市 五、8 "其他应收款"主表：4 行（其他应收款 / 应收利息 / 应收股利 / 合计）。"""
    rows = [
        {"label": "其他应收款", "end_amount": 0, "prior_amount": 0},
        {"label": "应收利息", "end_amount": 0, "prior_amount": 0},
        {"label": "应收股利", "end_amount": 0, "prior_amount": 0},
        {"label": "合计", "is_total": True, "end_amount": 0, "prior_amount": 0},
    ]
    return {
        "_source": "workpaper",
        "_sub_table_columns": {"其他应收款": NOTE_COLS_K1},
        "sub_table_data": {"其他应收款": rows},
    }


def _i3_note_data() -> dict:
    """上市 五、28 "商誉账面原值"主表：1 行数据 + 合计。"""
    rows = [
        {"label": "商誉", "end_amount": 0, "prior_amount": 0},
        {"label": "合计", "is_total": True, "end_amount": 0, "prior_amount": 0},
    ]
    return {
        "_source": "workpaper",
        "_sub_table_columns": {"商誉账面原值": NOTE_COLS_I3},
        "sub_table_data": {"商誉账面原值": rows},
    }


# ── TB 快照 ────────────────────────────────────────────────────────────────

K1_TB = TbAuditedSnapshot(
    tb_data={
        "1221": {
            "期末余额": Decimal("500000"),
            "年初余额": Decimal("300000"),
            "本期发生额": Decimal("200000"),
        },
        "1231": {
            "期末余额": Decimal("-50000"),
            "年初余额": Decimal("-30000"),
            "本期发生额": Decimal("-20000"),
        },
    },
    available=True,
    company_codes=("001",),
)

I3_TB = TbAuditedSnapshot(
    tb_data={
        "1711": {
            "期末余额": Decimal("800000"),
            "年初余额": Decimal("600000"),
            "本期发生额": Decimal("200000"),
        },
    },
    available=True,
    company_codes=("001",),
)


# ── fixture ────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def env(monkeypatch):
    """SQLite 真 ORM 环境：E1 + K1 + I3 三张底稿 + mock 取数。"""
    async with make_env(monkeypatch) as e:
        # ── 追加 K1 底稿 ──
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

        # ── 追加 I3 底稿 ──
        i3_idx, i3_wp = uuid.uuid4(), uuid.uuid4()
        async with e.factory() as db:
            await db.execute(sa.text(
                "INSERT INTO wp_index (id, project_id, wp_code) VALUES (:i, :p, 'I3')"
            ), {"i": str(i3_idx), "p": str(e.pid)})
            await db.execute(sa.text(
                "INSERT INTO working_paper (id, project_id, wp_index_id) VALUES (:w, :p, :i)"
            ), {"w": str(i3_wp), "p": str(e.pid), "i": str(i3_idx)})
            await db.commit()
        e.i3_wp_id = i3_wp

        # ── Mock K1 取数 ──
        async def fake_k1_load(self, db, project_id, year, wp_id):
            # 必须缓存 TB 数据（与真实 load_sources 同行为），note_rows 从 _last_tb_data 读 opening
            self._last_tb_data = K1_TB.tb_data if K1_TB.available else None
            return K1Sources(formula=FormulaSources(tb=K1_TB), template_type="listed")

        monkeypatch.setattr(K1Binding, "load_sources", fake_k1_load)

        # ── Mock load_tb_audited: 统一拦截所有 binding 的 TB 取数 ──
        _MOCK_TB = {
            "1221": K1_TB.tb_data["1221"],
            "1231": K1_TB.tb_data["1231"],
            "1711": I3_TB.tb_data["1711"],
        }

        async def fake_load_tb(db, project_id, year, codes):
            merged = {}
            for c in codes:
                for known_code, data in _MOCK_TB.items():
                    if known_code.startswith(str(c)):
                        merged[known_code] = data
            return TbAuditedSnapshot(
                tb_data=merged, available=bool(merged), company_codes=("001",),
            )

        monkeypatch.setattr(
            "app.services.formula_push.sources.load_tb_audited", fake_load_tb
        )
        # balance_adj 和 k1 在模块顶层 from-import 了 load_tb_audited，
        # 必须在调用方也打补丁（否则它们持有的是旧引用）
        monkeypatch.setattr(
            "app.services.formula_push.bindings.balance_adj.load_tb_audited", fake_load_tb
        )
        monkeypatch.setattr(
            "app.services.formula_push.bindings.k1.load_tb_audited", fake_load_tb
        )

        # ── Mock _load_template_type: 所有 binding 统一返回 listed ──
        async def fake_template_type(db, project_id):
            return "listed"

        for mod in ("tier_a", "k1", "balance_adj"):
            try:
                monkeypatch.setattr(
                    f"app.services.formula_push.bindings.{mod}._load_template_type",
                    fake_template_type,
                )
            except AttributeError:
                pass

        yield e


async def _seed_k1_entries(env: Env, entries: dict[str, str]) -> None:
    """给 K1 底稿种条目。"""
    async with env.factory() as db:
        for item, remark in entries.items():
            await db.execute(sa.text(
                "INSERT INTO checklist_responses (id, project_id, wp_id, item_id, remark, updated_at) "
                "VALUES (:id, :p, :w, :i, :r, :t)"
            ), {
                "id": str(uuid.uuid4()), "p": str(env.pid), "w": str(env.k1_wp_id),
                "i": item, "r": remark, "t": "2026-09-01 08:00:00.000000+00:00",
            })
        await db.commit()


def _main_rows(note: DisclosureNote, table_name: str) -> dict[str, dict]:
    """从附注 table_data 取主表行字典 {label: row}。"""
    return {r["label"]: r for r in note.table_data["sub_table_data"][table_name]}


# ── K1 附注推送测试 ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k1_note_push_writes_end_and_prior_amount(env):
    """K1 推送后附注"其他应收款"行的 end_amount / prior_amount 等于 TB 取数。

    ending = audited_net(entries) = receivable − baddebt = (100+10) − 30 = 80
    opening = TB 年初余额合计 = 300000 + (−30000) = 270000
    """
    # 种 K1 条目
    await _seed_k1_entries(env, {
        "K1-1-receivable-r0-unadj": "100",
        "K1-1-receivable-r0-aje": "10",
        "K1-1-receivable-r0-rje": "0",
        "K1-1-baddebt-r0-unadj": "30",
        "K1-1-baddebt-r0-aje": "0",
        "K1-1-baddebt-r0-rje": "0",
    })
    # 种 E1 条目（引擎会推 E1 + K1 + I3，E1 需要条目避免空跑）
    await env.seed_entries(base_entries())
    # 种附注章节
    await env.add_note("五、8", _k1_note_data(), title="其他应收款")
    # 种 I3 附注（避免 I3 推送时找不到章节报 skip 影响结果判读）
    await env.add_note("五、28", _i3_note_data(), title="商誉")

    result = await env.push()

    # 验证 K1 附注写入
    note = await env.note("五、8")
    rows = _main_rows(note, "其他应收款")

    # ending = audited_net = (100+10+0) − (30+0+0) = 80
    assert rows["其他应收款"]["end_amount"] == 80
    # opening = TB 年初余额(1221) + TB 年初余额(1231) = 300000 + (-30000) = 270000
    assert rows["其他应收款"]["prior_amount"] == 270000

    # 合计行应该被引擎重算
    assert rows["合计"]["end_amount"] == 80
    assert rows["合计"]["prior_amount"] == 270000

    # 同步指纹
    assert note.table_data["_last_sync_wp_id"] == str(env.k1_wp_id)
    assert note.last_sync_source == "formula_push"
    assert note.last_sync_wp_id == env.k1_wp_id

    # 运行结果应包含附注章节
    assert "五、8" in result.note_sections


# ── I3 附注推送测试 ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_i3_note_push_writes_end_and_prior_from_tb(env):
    """I3 推送后附注"商誉账面原值"行的 end_amount / prior_amount 等于 TB(1711) 取数。

    ending = TB('1711', '期末余额') = 800000
    opening = TB('1711', '年初余额') = 600000
    """
    await env.seed_entries(base_entries())
    # 种 K1 条目（K1 附注推送需要条目）
    await _seed_k1_entries(env, {"K1-1-receivable-r0-unadj": "100"})
    # 种附注章节
    await env.add_note("五、8", _k1_note_data(), title="其他应收款")
    await env.add_note("五、28", _i3_note_data(), title="商誉")

    result = await env.push()

    # 验证 I3 附注写入
    note = await env.note("五、28")
    rows = _main_rows(note, "商誉账面原值")

    # ending = TB('1711', '期末余额') = 800000
    assert rows["商誉"]["end_amount"] == 800000
    # opening = TB('1711', '年初余额') = 600000
    assert rows["商誉"]["prior_amount"] == 600000

    # 合计行应被重算
    assert rows["合计"]["end_amount"] == 800000
    assert rows["合计"]["prior_amount"] == 600000

    # 同步指纹
    assert note.table_data["_last_sync_wp_id"] == str(env.i3_wp_id)
    assert note.last_sync_source == "formula_push"
    assert note.last_sync_wp_id == env.i3_wp_id

    # 运行结果
    assert "五、28" in result.note_sections


@pytest.mark.asyncio
async def test_i3_note_push_second_run_idempotent(env):
    """I3 第二次推送值不变时附注不产生写入（idempotent）。"""
    await env.seed_entries(base_entries())
    await _seed_k1_entries(env, {"K1-1-receivable-r0-unadj": "100"})
    await env.add_note("五、8", _k1_note_data(), title="其他应收款")
    await env.add_note("五、28", _i3_note_data(), title="商誉")

    await env.push()
    note_before = await env.note("五、28")
    td_before = note_before.table_data.copy()

    result2 = await env.push()

    note_after = await env.note("五、28")
    rows_after = _main_rows(note_after, "商誉账面原值")
    # 值不变
    assert rows_after["商誉"]["end_amount"] == 800000
    assert rows_after["商誉"]["prior_amount"] == 600000
    # I3 附注项应全是 unchanged
    i3_note_items = [i for i in result2.items if i.rule_id == "I3.note.main" and i.stage == "note"]
    assert all(i.action == "unchanged" for i in i3_note_items)


@pytest.mark.asyncio
async def test_k1_note_missing_section_is_skipped(env):
    """K1 附注章节不存在时推送 skip，不报错。"""
    await env.seed_entries(base_entries())
    await _seed_k1_entries(env, {"K1-1-receivable-r0-unadj": "100"})
    # 不种 K1 附注章节 → push 应 skip
    await env.add_note("五、28", _i3_note_data(), title="商誉")

    result = await env.push()

    # K1 附注应被跳过（章节不存在）
    assert "五、8" not in result.note_sections
    k1_note_skips = [i for i in result.items if i.rule_id == "K1.note.main" and i.action == "skipped"]
    assert len(k1_note_skips) > 0
    assert "尚未生成" in k1_note_skips[0].reason


# ── SOE 版附注数据 ─────────────────────────────────────────────────────────


def _i3_note_data_soe() -> dict:
    """SOE 八、29 "（1）商誉账面价值"主表。"""
    rows = [
        {"label": "商誉", "end_amount": 0, "prior_amount": 0},
        {"label": "合计", "is_total": True, "end_amount": 0, "prior_amount": 0},
    ]
    return {
        "_source": "workpaper",
        "_sub_table_columns": {"（1）商誉账面价值": NOTE_COLS_I3},
        "sub_table_data": {"（1）商誉账面价值": rows},
    }


# ── SOE fixture ────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def env_soe(monkeypatch):
    """与 env 相同但 template_type=soe。"""
    async with make_env(monkeypatch) as e:
        # ── 追加 K1 底稿 ──
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

        # ── 追加 I3 底稿 ──
        i3_idx, i3_wp = uuid.uuid4(), uuid.uuid4()
        async with e.factory() as db:
            await db.execute(sa.text(
                "INSERT INTO wp_index (id, project_id, wp_code) VALUES (:i, :p, 'I3')"
            ), {"i": str(i3_idx), "p": str(e.pid)})
            await db.execute(sa.text(
                "INSERT INTO working_paper (id, project_id, wp_index_id) VALUES (:w, :p, :i)"
            ), {"w": str(i3_wp), "p": str(e.pid), "i": str(i3_idx)})
            await db.commit()
        e.i3_wp_id = i3_wp

        # ── Mock K1 取数 ──
        async def fake_k1_load(self, db, project_id, year, wp_id):
            self._last_tb_data = K1_TB.tb_data if K1_TB.available else None
            return K1Sources(formula=FormulaSources(tb=K1_TB), template_type="soe")

        monkeypatch.setattr(K1Binding, "load_sources", fake_k1_load)

        # ── Mock load_tb_audited ──
        _MOCK_TB = {
            "1221": K1_TB.tb_data["1221"],
            "1231": K1_TB.tb_data["1231"],
            "1711": I3_TB.tb_data["1711"],
        }

        async def fake_load_tb(db, project_id, year, codes):
            merged = {}
            for c in codes:
                for known_code, data in _MOCK_TB.items():
                    if known_code.startswith(str(c)):
                        merged[known_code] = data
            return TbAuditedSnapshot(
                tb_data=merged, available=bool(merged), company_codes=("001",),
            )

        monkeypatch.setattr(
            "app.services.formula_push.sources.load_tb_audited", fake_load_tb
        )
        # balance_adj 和 k1 在模块顶层 from-import 了 load_tb_audited，
        # 必须在调用方也打补丁（否则它们持有的是旧引用）
        monkeypatch.setattr(
            "app.services.formula_push.bindings.balance_adj.load_tb_audited", fake_load_tb
        )
        monkeypatch.setattr(
            "app.services.formula_push.bindings.k1.load_tb_audited", fake_load_tb
        )

        # ── Mock _load_template_type: 返回 soe ──
        async def fake_template_type(db, project_id):
            return "soe"

        for mod in ("tier_a", "k1", "balance_adj"):
            try:
                monkeypatch.setattr(
                    f"app.services.formula_push.bindings.{mod}._load_template_type",
                    fake_template_type,
                )
            except AttributeError:
                pass

        yield e


# ── SOE 版 I3 附注推送测试 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_i3_note_push_soe_version(env_soe):
    """SOE 版 I3 推送用「（1）商誉账面价值」子表（P0 守卫：table_by_template 缺失即红）。"""
    await env_soe.seed_entries(base_entries())
    await _seed_k1_entries(env_soe, {"K1-1-receivable-r0-unadj": "100"})
    await env_soe.add_note("八、9", _k1_note_data(), title="其他应收款")
    await env_soe.add_note("八、29", _i3_note_data_soe(), title="商誉")

    result = await env_soe.push()

    note = await env_soe.note("八、29")
    rows = _main_rows(note, "（1）商誉账面价值")
    assert rows["商誉"]["end_amount"] == 800000
    assert rows["商誉"]["prior_amount"] == 600000
    assert "八、29" in result.note_sections
