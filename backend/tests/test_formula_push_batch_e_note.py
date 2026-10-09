"""D1 附注推送 SQLite 真 ORM 集成测试（batch-e canary）。

spec: formula-push-note-rollout-batch-e · Task 2, 3, 4

验证 ``table_by_template`` 新机制 + 准则变体隔离：
- D1 上市项目 → 推 ``五、4``（表名「应收票据」），不碰 ``八、4``
- D1 国企项目 → 推 ``八、4``（表名「应收票据分类」），不碰 ``五、4``
- 附注无表时建骨架（``build_main_skeleton`` + ``table_by_template``）
- 合计行由引擎重算
- D1 note_rows 从 entries 读分类 + 坏账快照，返回六字段行（Task 2）
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.models.report_models import ContentType, DisclosureNote, NoteStatus
from app.services.formula_push import engine as push
from app.services.formula_push.bindings.balance_adj import BalanceAdjudicationBinding, BalanceAdjSources
from app.services.formula_push.bindings.e1 import E1Binding
from app.services.formula_push.bindings.k1 import K1Binding
from app.services.formula_push.bindings.tier_a import TierAAnchorBinding, TierASources
from app.services.formula_push.bindings.note_direct import NoteDirectBinding, NoteDirectSources
from app.services.formula_push.sources import FormulaSources, TbAuditedSnapshot
from tests._formula_push_env import YEAR, Env, base_entries, make_env

# ── D1 TB 快照（1121 应收票据） ──────────────────────────────────────────

D1_TB = TbAuditedSnapshot(
    tb_data={
        "1121": {
            "期末余额": Decimal("1200000"),
            "年初余额": Decimal("900000"),
            "本期发生额": Decimal("300000"),
        },
    },
    available=True,
    company_codes=("001",),
)

# ── 附注 table_data 骨架 ──────────────────────────────────────────────────

NOTE_COLS_LISTED = [
    {"key": "label", "label": "票据种类", "is_label": True},
    {"key": "end_balance", "label": "账面余额", "group": "期末余额", "format": "amount"},
    {"key": "end_provision", "label": "坏账准备", "group": "期末余额", "format": "amount"},
    {"key": "end_book_value", "label": "账面价值", "group": "期末余额", "format": "amount"},
    {"key": "prior_balance", "label": "账面余额", "group": "上年年末余额", "format": "amount"},
    {"key": "prior_provision", "label": "坏账准备", "group": "上年年末余额", "format": "amount"},
    {"key": "prior_book_value", "label": "账面价值", "group": "上年年末余额", "format": "amount"},
]

NOTE_COLS_SOE = [
    {"key": "label", "label": "票据种类", "is_label": True},
    {"key": "end_balance", "label": "账面余额", "group": "期末数", "format": "amount"},
    {"key": "end_provision", "label": "坏账准备", "group": "期末数", "format": "amount"},
    {"key": "end_book_value", "label": "账面价值", "group": "期末数", "format": "amount"},
    {"key": "prior_balance", "label": "账面余额", "group": "期初数", "format": "amount"},
    {"key": "prior_provision", "label": "坏账准备", "group": "期初数", "format": "amount"},
    {"key": "prior_book_value", "label": "账面价值", "group": "期初数", "format": "amount"},
]


def _d1_listed_note_data() -> dict:
    """上市 五、4 「应收票据」主表：银行承兑汇票 / 商业承兑汇票 / 合计。

    模拟前端已推过数据行（六字段：余额/坏账准备/账面价值 × 期末期初），
    合计行过期（不等于数据行之和）。引擎重算合计行后应写入正确值。
    """
    rows = [
        {"label": "银行承兑汇票",
         "end_balance": 800000, "end_provision": 50000, "end_book_value": 750000,
         "prior_balance": 500000, "prior_provision": 30000, "prior_book_value": 470000},
        {"label": "商业承兑汇票",
         "end_balance": 400000, "end_provision": 20000, "end_book_value": 380000,
         "prior_balance": 400000, "prior_provision": 10000, "prior_book_value": 390000},
        {"label": "合计", "is_total": True,
         "end_balance": 0, "end_provision": 0, "end_book_value": 0,
         "prior_balance": 0, "prior_provision": 0, "prior_book_value": 0},
    ]
    return {
        "_source": "workpaper",
        "_sub_table_columns": {"应收票据": NOTE_COLS_LISTED},
        "sub_table_data": {"应收票据": rows},
    }


def _d1_soe_note_data() -> dict:
    """国企 八、4 「应收票据分类」主表。

    模拟前端已推过数据行（六字段），合计行过期。
    """
    rows = [
        {"label": "银行承兑汇票",
         "end_balance": 600000, "end_provision": 30000, "end_book_value": 570000,
         "prior_balance": 300000, "prior_provision": 15000, "prior_book_value": 285000},
        {"label": "商业承兑汇票",
         "end_balance": 200000, "end_provision": 10000, "end_book_value": 190000,
         "prior_balance": 200000, "prior_provision": 5000, "prior_book_value": 195000},
        {"label": "合计", "is_total": True,
         "end_balance": 0, "end_provision": 0, "end_book_value": 0,
         "prior_balance": 0, "prior_provision": 0, "prior_book_value": 0},
    ]
    return {
        "_source": "workpaper",
        "_sub_table_columns": {"应收票据分类": NOTE_COLS_SOE},
        "sub_table_data": {"应收票据分类": rows},
    }


# ── fixture：上市项目环境 ─────────────────────────────────────────────────

@pytest_asyncio.fixture
async def env_listed(monkeypatch):
    """SQLite 真 ORM 环境：上市项目 + D1 底稿 + mock 取数。"""
    async with make_env(monkeypatch) as e:
        # 追加 D1 底稿
        d1_idx, d1_wp = uuid.uuid4(), uuid.uuid4()
        async with e.factory() as db:
            await db.execute(sa.text(
                "INSERT INTO wp_index (id, project_id, wp_code) VALUES (:i, :p, 'D1')"
            ), {"i": str(d1_idx), "p": str(e.pid)})
            await db.execute(sa.text(
                "INSERT INTO working_paper (id, project_id, wp_index_id) VALUES (:w, :p, :i)"
            ), {"w": str(d1_wp), "p": str(e.pid), "i": str(d1_idx)})
            await db.commit()
        e.d1_wp_id = d1_wp

        # Mock Tier A 取数（D1 是 Tier A）
        async def fake_tier_a_load(self, db, project_id, year, wp_id):
            if self.wp_code == "D1":
                self._last_tb_data = D1_TB.tb_data
                return TierASources(formula=FormulaSources(tb=D1_TB), template_type="listed")
            return TierASources(formula=FormulaSources(), template_type="listed")

        monkeypatch.setattr(TierAAnchorBinding, "load_sources", fake_tier_a_load)

        # Mock NoteDirectBinding 取数（避免真 DB 查询）
        async def fake_note_direct_load(self, db, project_id, year, wp_id):
            return NoteDirectSources(formula=FormulaSources(), template_type="listed")

        monkeypatch.setattr(NoteDirectBinding, "load_sources", fake_note_direct_load)

        # Mock K1 取数
        async def fake_k1_load(self, db, project_id, year, wp_id):
            self._last_tb_data = None
            from app.services.formula_push.bindings.k1 import K1Sources
            return K1Sources(formula=FormulaSources(), template_type="listed")

        monkeypatch.setattr(K1Binding, "load_sources", fake_k1_load)

        yield e


@pytest_asyncio.fixture
async def env_soe(monkeypatch):
    """SQLite 真 ORM 环境：国企项目 + D1 底稿 + mock 取数。"""
    async with make_env(monkeypatch) as e:
        # 把项目改为国企
        async with e.factory() as db:
            await db.execute(
                sa.text("UPDATE projects SET template_type = 'soe' WHERE id = :p"),
                {"p": str(e.pid)},
            )
            await db.commit()

        # 追加 D1 底稿
        d1_idx, d1_wp = uuid.uuid4(), uuid.uuid4()
        async with e.factory() as db:
            await db.execute(sa.text(
                "INSERT INTO wp_index (id, project_id, wp_code) VALUES (:i, :p, 'D1')"
            ), {"i": str(d1_idx), "p": str(e.pid)})
            await db.execute(sa.text(
                "INSERT INTO working_paper (id, project_id, wp_index_id) VALUES (:w, :p, :i)"
            ), {"w": str(d1_wp), "p": str(e.pid), "i": str(d1_idx)})
            await db.commit()
        e.d1_wp_id = d1_wp

        # Mock Tier A 取数（D1 + 国企模板类型）
        async def fake_tier_a_load(self, db, project_id, year, wp_id):
            if self.wp_code == "D1":
                self._last_tb_data = D1_TB.tb_data
                return TierASources(formula=FormulaSources(tb=D1_TB), template_type="soe")
            return TierASources(formula=FormulaSources(), template_type="soe")

        monkeypatch.setattr(TierAAnchorBinding, "load_sources", fake_tier_a_load)

        async def fake_note_direct_load(self, db, project_id, year, wp_id):
            return NoteDirectSources(formula=FormulaSources(), template_type="soe")

        monkeypatch.setattr(NoteDirectBinding, "load_sources", fake_note_direct_load)

        async def fake_k1_load(self, db, project_id, year, wp_id):
            self._last_tb_data = None
            from app.services.formula_push.bindings.k1 import K1Sources
            return K1Sources(formula=FormulaSources(), template_type="soe")

        monkeypatch.setattr(K1Binding, "load_sources", fake_k1_load)

        yield e


def _main_rows(note: DisclosureNote, table_name: str) -> dict[str, dict]:
    return {r["label"]: r for r in note.table_data["sub_table_data"][table_name]}


# ── 上市项目测试 ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_d1_listed_pushes_to_listed_section(env_listed):
    """上市项目：D1 推送写 五、4「应收票据」，合计行被引擎重算。

    D1 Tier A note_rows 返回 label 不匹配附注子项行（银行/商业承兑汇票），
    因此数据行不被写入（skip）。但前端已推过的非零数据行使 _push_note_total
    重算合计行 = 银行 800000 + 商业 400000 = 1200000。
    """
    await env_listed.seed_entries(base_entries())
    await env_listed.add_note("五、4", _d1_listed_note_data(), title="应收票据")

    result = await env_listed.push(codes=["D1"])

    note = await env_listed.note("五、4")
    rows = _main_rows(note, "应收票据")

    # 数据行不被写入（Tier A label 不匹配），保持前端推的值
    assert rows["银行承兑汇票"]["end_balance"] == 800000
    assert rows["商业承兑汇票"]["end_balance"] == 400000

    # 合计行被引擎重算 = 800000 + 400000 = 1200000
    assert rows["合计"]["end_balance"] == 1200000
    assert rows["合计"]["prior_balance"] == 900000

    # 同步指纹（合计行有写入 → wrote=True）
    assert note.last_sync_source == "formula_push"
    assert note.last_sync_wp_id == env_listed.d1_wp_id

    # 运行结果应包含附注章节
    assert "五、4" in result.note_sections


@pytest.mark.asyncio
async def test_d1_listed_does_not_touch_soe_section(env_listed):
    """上市项目推送 D1 时不碰国企章节 八、4。

    验证两个维度：
    1. 同步指纹不变（last_sync_source / last_sync_wp_id）
    2. sub_table_data 内容不变（数据行的值与种入时完全一致）
    """
    await env_listed.seed_entries(base_entries())
    await env_listed.add_note("五、4", _d1_listed_note_data(), title="应收票据")
    soe_data = _d1_soe_note_data()
    await env_listed.add_note("八、4", soe_data, title="应收票据")

    await env_listed.push(codes=["D1"])

    # 同步指纹不变
    soe_note = await env_listed.note("八、4")
    assert soe_note.last_sync_source is None
    assert soe_note.last_sync_wp_id is None

    # sub_table_data 内容不变（与种入时一致）
    soe_rows = soe_note.table_data["sub_table_data"]["应收票据分类"]
    original_rows = soe_data["sub_table_data"]["应收票据分类"]
    for orig, actual in zip(original_rows, soe_rows):
        assert actual["label"] == orig["label"]
        for fk in ("end_balance", "end_provision", "end_book_value",
                    "prior_balance", "prior_provision", "prior_book_value"):
            assert actual[fk] == orig[fk], (
                f"八、4 行「{orig['label']}」的 {fk} 被改动：{orig[fk]} → {actual[fk]}"
            )


# ── 国企项目测试 ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_d1_soe_pushes_to_soe_section(env_soe):
    """国企项目：D1 推送写 八、4「应收票据分类」。

    table_by_template 机制在此生效：
    - rule.target.table = "应收票据"（兼容字段）
    - rule.target.table_by_template = {"listed": "应收票据", "soe": "应收票据分类"}
    - template_type = "soe" → resolve_table("soe") = "应收票据分类"
    → 引擎用"应收票据分类"定位，合计行 = 600000 + 200000 = 800000
    """
    await env_soe.seed_entries(base_entries())
    await env_soe.add_note("八、4", _d1_soe_note_data(), title="应收票据")

    result = await env_soe.push(codes=["D1"])

    note = await env_soe.note("八、4")
    rows = _main_rows(note, "应收票据分类")

    # 合计行被重算
    assert rows["合计"]["end_balance"] == 800000
    assert rows["合计"]["prior_balance"] == 500000

    # 同步指纹
    assert note.last_sync_source == "formula_push"
    assert note.last_sync_wp_id == env_soe.d1_wp_id

    # 运行结果
    assert "八、4" in result.note_sections


@pytest.mark.asyncio
async def test_d1_soe_does_not_touch_listed_section(env_soe):
    """国企项目推送 D1 时不碰上市章节 五、4。

    验证两个维度：
    1. 同步指纹不变
    2. sub_table_data 内容不变
    """
    await env_soe.seed_entries(base_entries())
    listed_data = _d1_listed_note_data()
    await env_soe.add_note("五、4", listed_data, title="应收票据")
    await env_soe.add_note("八、4", _d1_soe_note_data(), title="应收票据")

    await env_soe.push(codes=["D1"])

    # 同步指纹不变
    listed_note = await env_soe.note("五、4")
    assert listed_note.last_sync_source is None
    assert listed_note.last_sync_wp_id is None

    # sub_table_data 内容不变
    listed_rows = listed_note.table_data["sub_table_data"]["应收票据"]
    original_rows = listed_data["sub_table_data"]["应收票据"]
    for orig, actual in zip(original_rows, listed_rows):
        assert actual["label"] == orig["label"]
        for fk in ("end_balance", "end_provision", "end_book_value",
                    "prior_balance", "prior_provision", "prior_book_value"):
            assert actual[fk] == orig[fk], (
                f"五、4 行「{orig['label']}」的 {fk} 被改动：{orig[fk]} → {actual[fk]}"
            )


# ── Task 3：D1 entries 种入 + 六字段 ORM 值验证 ─────────────────────────


async def _seed_d1_entries(env, *, cat_rows: list[dict], bd_rows: list[dict]) -> None:
    """向 D1 底稿的 checklist_responses 种入分类 + 坏账快照。"""
    entries = {
        "D1-cat-rows": _d1_cat_rows_json(cat_rows),
        "D1-bd-notetype-rows": _d1_bd_notetype_rows_json(bd_rows),
    }
    async with env.factory() as db:
        for item, remark in entries.items():
            await db.execute(sa.text(
                "INSERT INTO checklist_responses (id, project_id, wp_id, item_id, remark, updated_at) "
                "VALUES (:id, :p, :w, :i, :r, :t)"
            ), {"id": str(uuid.uuid4()), "p": str(env.pid), "w": str(env.d1_wp_id), "i": item,
                "r": remark, "t": "2026-09-01 08:00:00.000000+00:00"})
        await db.commit()


@pytest.mark.asyncio
async def test_d1_listed_six_fields_from_entries(env_listed):
    """上市项目：D1 entries 种入分类 + 坏账快照 → 推送后附注六字段值正确。

    验证 end_balance / end_provision / end_book_value / prior_balance / prior_provision / prior_book_value
    与 _d1_note_rows_from_entries 计算结果一致，且 book_value = balance - provision。
    """
    # 种 E1 entries（避免 E1 推送报错）
    await env_listed.seed_entries(base_entries())

    # 种 D1 分类 + 坏账快照
    await _seed_d1_entries(env_listed,
        cat_rows=[
            _make_cat_row("fixed-bank", "银行承兑汇票",
                          prior_unadj=500000, cur_increase=300000),
            _make_cat_row("fixed-commercial", "商业承兑汇票",
                          prior_unadj=400000, cur_increase=200000, cur_decrease=100000),
        ],
        bd_rows=[
            _make_bd_notetype_row("fixed-bank", "银行承兑汇票小计",
                                  prior_unadj=30000, cur_unadj=50000),
            _make_bd_notetype_row("fixed-commercial", "商业承兑汇票小计",
                                  prior_unadj=10000, cur_unadj=20000),
        ],
    )

    # 附注种好骨架（银行 / 商业 / 合计三行，值初始全零）
    await env_listed.add_note("五、4", {
        "_source": "workpaper",
        "_sub_table_columns": {"应收票据": NOTE_COLS_LISTED},
        "sub_table_data": {"应收票据": [
            {"label": "银行承兑汇票",
             "end_balance": 0, "end_provision": 0, "end_book_value": 0,
             "prior_balance": 0, "prior_provision": 0, "prior_book_value": 0},
            {"label": "商业承兑汇票",
             "end_balance": 0, "end_provision": 0, "end_book_value": 0,
             "prior_balance": 0, "prior_provision": 0, "prior_book_value": 0},
            {"label": "合计", "is_total": True,
             "end_balance": 0, "end_provision": 0, "end_book_value": 0,
             "prior_balance": 0, "prior_provision": 0, "prior_book_value": 0},
        ]},
    }, title="应收票据")

    result = await env_listed.push(codes=["D1"])

    note = await env_listed.note("五、4")
    rows = _main_rows(note, "应收票据")

    # ── 银行承兑汇票 ────────────────────────────────────────────────
    bank = rows["银行承兑汇票"]
    # 分类：priorAudited=500000, currentUnadj=500000+300000-0=800000, currentAudited=800000
    assert bank["end_balance"] == 800000
    assert bank["prior_balance"] == 500000
    # 坏账：priorAudited=30000, currentAudited=50000
    assert bank["end_provision"] == 50000
    assert bank["prior_provision"] == 30000
    # 账面价值 = 余额 - 坏账
    assert bank["end_book_value"] == 750000
    assert bank["prior_book_value"] == 470000

    # ── 商业承兑汇票 ────────────────────────────────────────────────
    comm = rows["商业承兑汇票"]
    # 分类：priorAudited=400000, currentUnadj=400000+200000-100000=500000
    assert comm["end_balance"] == 500000
    assert comm["prior_balance"] == 400000
    # 坏账：priorAudited=10000, currentAudited=20000
    assert comm["end_provision"] == 20000
    assert comm["prior_provision"] == 10000
    assert comm["end_book_value"] == 480000
    assert comm["prior_book_value"] == 390000

    # ── 合计行（引擎重算） ──────────────────────────────────────────
    total = rows["合计"]
    assert total["end_balance"] == 800000 + 500000   # 1300000
    assert total["prior_balance"] == 500000 + 400000  # 900000
    assert total["end_provision"] == 50000 + 20000    # 70000
    assert total["prior_provision"] == 30000 + 10000  # 40000
    assert total["end_book_value"] == 750000 + 480000  # 1230000
    assert total["prior_book_value"] == 470000 + 390000  # 860000

    # book_value 不变式
    for label, row in rows.items():
        assert row["end_book_value"] == row["end_balance"] - row["end_provision"], (
            f"行「{label}」end_book_value 不等式：{row['end_book_value']} ≠ {row['end_balance']} - {row['end_provision']}"
        )
        assert row["prior_book_value"] == row["prior_balance"] - row["prior_provision"], (
            f"行「{label}」prior_book_value 不等式"
        )

    # 同步指纹
    assert note.last_sync_source == "formula_push"
    assert note.last_sync_wp_id == env_listed.d1_wp_id
    assert "五、4" in result.note_sections


@pytest.mark.asyncio
async def test_d1_soe_six_fields_from_entries(env_soe):
    """国企项目：D1 entries 种入 → 推送后 八、4「应收票据分类」六字段正确。"""
    await env_soe.seed_entries(base_entries())

    await _seed_d1_entries(env_soe,
        cat_rows=[
            _make_cat_row("fixed-bank", "银行承兑汇票",
                          prior_unadj=300000, cur_increase=200000),
            _make_cat_row("fixed-commercial", "商业承兑汇票",
                          prior_unadj=200000, cur_increase=100000),
        ],
        bd_rows=[
            _make_bd_notetype_row("fixed-bank", "银行承兑汇票小计",
                                  prior_unadj=15000, cur_unadj=25000),
            _make_bd_notetype_row("fixed-commercial", "商业承兑汇票小计",
                                  prior_unadj=5000, cur_unadj=10000),
        ],
    )

    await env_soe.add_note("八、4", {
        "_source": "workpaper",
        "_sub_table_columns": {"应收票据分类": NOTE_COLS_SOE},
        "sub_table_data": {"应收票据分类": [
            {"label": "银行承兑汇票",
             "end_balance": 0, "end_provision": 0, "end_book_value": 0,
             "prior_balance": 0, "prior_provision": 0, "prior_book_value": 0},
            {"label": "商业承兑汇票",
             "end_balance": 0, "end_provision": 0, "end_book_value": 0,
             "prior_balance": 0, "prior_provision": 0, "prior_book_value": 0},
            {"label": "合计", "is_total": True,
             "end_balance": 0, "end_provision": 0, "end_book_value": 0,
             "prior_balance": 0, "prior_provision": 0, "prior_book_value": 0},
        ]},
    }, title="应收票据")

    result = await env_soe.push(codes=["D1"])

    note = await env_soe.note("八、4")
    rows = _main_rows(note, "应收票据分类")

    # 银行：priorAudited=300000, currentAudited=500000; 坏账 prior=15000, cur=25000
    assert rows["银行承兑汇票"]["end_balance"] == 500000
    assert rows["银行承兑汇票"]["prior_balance"] == 300000
    assert rows["银行承兑汇票"]["end_provision"] == 25000
    assert rows["银行承兑汇票"]["prior_provision"] == 15000
    assert rows["银行承兑汇票"]["end_book_value"] == 475000
    assert rows["银行承兑汇票"]["prior_book_value"] == 285000

    # 商业：priorAudited=200000, currentAudited=300000; 坏账 prior=5000, cur=10000
    assert rows["商业承兑汇票"]["end_balance"] == 300000
    assert rows["商业承兑汇票"]["prior_balance"] == 200000
    assert rows["商业承兑汇票"]["end_provision"] == 10000
    assert rows["商业承兑汇票"]["prior_provision"] == 5000
    assert rows["商业承兑汇票"]["end_book_value"] == 290000
    assert rows["商业承兑汇票"]["prior_book_value"] == 195000

    # 合计
    assert rows["合计"]["end_balance"] == 800000
    assert rows["合计"]["end_provision"] == 35000
    assert rows["合计"]["end_book_value"] == 765000

    assert note.last_sync_source == "formula_push"
    assert note.last_sync_wp_id == env_soe.d1_wp_id
    assert "八、4" in result.note_sections


@pytest.mark.asyncio
async def test_d1_listed_entries_push_does_not_touch_soe(env_listed):
    """上市项目 + D1 entries 种入 → 推送后 八、4 sub_table_data 不被改动。

    与 test_d1_listed_does_not_touch_soe_section 互补：那个用 base_entries（E1 数据），
    这个真正种了 D1 entries，确认即使 D1 有数据也只推目标变体。
    """
    await env_listed.seed_entries(base_entries())
    await _seed_d1_entries(env_listed,
        cat_rows=[
            _make_cat_row("fixed-bank", "银行承兑汇票", prior_unadj=500000, cur_increase=300000),
        ],
        bd_rows=[
            _make_bd_notetype_row("fixed-bank", "银行承兑汇票小计", prior_unadj=30000, cur_unadj=50000),
        ],
    )

    await env_listed.add_note("五、4", {
        "_source": "workpaper",
        "_sub_table_columns": {"应收票据": NOTE_COLS_LISTED},
        "sub_table_data": {"应收票据": [
            {"label": "银行承兑汇票",
             "end_balance": 0, "end_provision": 0, "end_book_value": 0,
             "prior_balance": 0, "prior_provision": 0, "prior_book_value": 0},
            {"label": "合计", "is_total": True,
             "end_balance": 0, "end_provision": 0, "end_book_value": 0,
             "prior_balance": 0, "prior_provision": 0, "prior_book_value": 0},
        ]},
    }, title="应收票据")

    soe_data = _d1_soe_note_data()
    await env_listed.add_note("八、4", soe_data, title="应收票据")

    await env_listed.push(codes=["D1"])

    # 五、4 有写入
    listed_note = await env_listed.note("五、4")
    assert listed_note.last_sync_source == "formula_push"

    # 八、4 完全不动
    soe_note = await env_listed.note("八、4")
    assert soe_note.last_sync_source is None
    soe_rows = soe_note.table_data["sub_table_data"]["应收票据分类"]
    original_rows = soe_data["sub_table_data"]["应收票据分类"]
    for orig, actual in zip(original_rows, soe_rows):
        for fk in ("end_balance", "end_provision", "end_book_value",
                    "prior_balance", "prior_provision", "prior_book_value"):
            assert actual[fk] == orig[fk]


# ── 骨架构建测试（Task 4） ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_d1_listed_builds_skeleton_when_table_missing(env_listed):
    """附注章节存在、有 sub_table_data 但缺目标表时，引擎建骨架。"""
    await env_listed.seed_entries(base_entries())
    # 种一个有其他子表但缺「应收票据」的附注章节
    await env_listed.add_note("五、4", {
        "_source": "workpaper",
        "sub_table_data": {"期末已质押的应收票据": [{"label": "合计", "is_total": True}]},
        "_sub_table_columns": {"期末已质押的应收票据": [{"key": "label", "is_label": True}]},
    }, title="应收票据")

    result = await env_listed.push(codes=["D1"])

    note = await env_listed.note("五、4")
    sub = note.table_data.get("sub_table_data", {})
    assert "应收票据" in sub, f"应建出「应收票据」骨架，实际 keys={list(sub.keys())}"
    rows = sub["应收票据"]
    labels = [r["label"] for r in rows]
    assert labels == ["银行承兑汇票", "商业承兑汇票", "合计"]


@pytest.mark.asyncio
async def test_d1_soe_builds_skeleton_with_variant_table_name(env_soe):
    """国企项目：缺表时骨架用「应收票据分类」（soe 变体表名）。"""
    await env_soe.seed_entries(base_entries())
    await env_soe.add_note("八、4", {
        "_source": "workpaper",
        "sub_table_data": {"期末已质押的应收票据": [{"label": "合计", "is_total": True}]},
        "_sub_table_columns": {"期末已质押的应收票据": [{"key": "label", "is_label": True}]},
    }, title="应收票据")

    result = await env_soe.push(codes=["D1"])

    note = await env_soe.note("八、4")
    sub = note.table_data.get("sub_table_data", {})
    assert "应收票据分类" in sub, f"国企骨架应用「应收票据分类」表名，实际 keys={list(sub.keys())}"
    rows = sub["应收票据分类"]
    labels = [r["label"] for r in rows]
    assert labels == ["银行承兑汇票", "商业承兑汇票", "合计"]


# ── Task 4：骨架构建 + 缺表跳过 — 六字段数据写入验证 ─────────────────────


@pytest.mark.asyncio
async def test_d1_skeleton_then_six_fields_written(env_listed):
    """骨架构建后引擎继续写入六字段值（不止建空行）。

    场景：附注章节存在但缺「应收票据」表 + D1 entries 有分类/坏账数据
    → 建骨架 → 六字段值写入骨架行 + 合计行重算。
    """
    await env_listed.seed_entries(base_entries())
    await _seed_d1_entries(env_listed,
        cat_rows=[
            _make_cat_row("fixed-bank", "银行承兑汇票",
                          prior_unadj=500000, cur_increase=300000),
            _make_cat_row("fixed-commercial", "商业承兑汇票",
                          prior_unadj=400000, cur_increase=200000, cur_decrease=100000),
        ],
        bd_rows=[
            _make_bd_notetype_row("fixed-bank", "银行承兑汇票小计",
                                  prior_unadj=30000, cur_unadj=50000),
            _make_bd_notetype_row("fixed-commercial", "商业承兑汇票小计",
                                  prior_unadj=10000, cur_unadj=20000),
        ],
    )

    # 附注章节存在，有其他子表但缺「应收票据」
    await env_listed.add_note("五、4", {
        "_source": "workpaper",
        "sub_table_data": {"期末已质押的应收票据": [{"label": "合计", "is_total": True}]},
        "_sub_table_columns": {"期末已质押的应收票据": [{"key": "label", "is_label": True}]},
    }, title="应收票据")

    result = await env_listed.push(codes=["D1"])

    note = await env_listed.note("五、4")
    sub = note.table_data["sub_table_data"]
    assert "应收票据" in sub

    rows = _main_rows(note, "应收票据")
    # 银行承兑汇票
    bank = rows["银行承兑汇票"]
    assert bank["end_balance"] == 800000
    assert bank["prior_balance"] == 500000
    assert bank["end_provision"] == 50000
    assert bank["prior_provision"] == 30000
    assert bank["end_book_value"] == 750000
    assert bank["prior_book_value"] == 470000

    # 商业承兑汇票
    comm = rows["商业承兑汇票"]
    assert comm["end_balance"] == 500000
    assert comm["prior_balance"] == 400000
    assert comm["end_provision"] == 20000
    assert comm["prior_provision"] == 10000
    assert comm["end_book_value"] == 480000
    assert comm["prior_book_value"] == 390000

    # 合计行重算
    total = rows["合计"]
    assert total["end_balance"] == 1300000
    assert total["prior_balance"] == 900000
    assert total["end_provision"] == 70000
    assert total["prior_provision"] == 40000
    assert total["end_book_value"] == 1230000
    assert total["prior_book_value"] == 860000


@pytest.mark.asyncio
async def test_d1_skeleton_columns_include_six_fields(env_listed):
    """骨架构建后 _sub_table_columns 包含六字段列定义。"""
    await env_listed.seed_entries(base_entries())

    # 附注章节有其他子表但缺「应收票据」
    await env_listed.add_note("五、4", {
        "_source": "workpaper",
        "sub_table_data": {"期末已质押的应收票据": [{"label": "合计", "is_total": True}]},
        "_sub_table_columns": {"期末已质押的应收票据": [{"key": "label", "is_label": True}]},
    }, title="应收票据")

    await env_listed.push(codes=["D1"])

    note = await env_listed.note("五、4")
    cols = note.table_data.get("_sub_table_columns", {})
    assert "应收票据" in cols, f"骨架列定义应包含「应收票据」，实际 keys={list(cols.keys())}"
    col_keys = [c["key"] for c in cols["应收票据"] if "key" in c]
    # 必须有标签列 + 六字段列
    assert "label" in col_keys
    for field in ("end_balance", "end_provision", "end_book_value",
                  "prior_balance", "prior_provision", "prior_book_value"):
        assert field in col_keys, f"骨架列定义缺 {field}，实际 keys={col_keys}"


@pytest.mark.asyncio
async def test_d1_note_missing_section_is_skipped(env_listed):
    """D1 附注章节不存在时推送 skip，不报错。"""
    await env_listed.seed_entries(base_entries())
    # 不种 D1 附注章节

    result = await env_listed.push(codes=["D1"])

    d1_note_skips = [
        i for i in result.items
        if i.rule_id == "D1.note.main" and i.action == "skipped"
    ]
    assert len(d1_note_skips) > 0
    assert "尚未生成" in d1_note_skips[0].reason


@pytest.mark.asyncio
async def test_resolve_table_picks_variant(env_listed):
    """PushTarget.resolve_table 按 template_type 选变体表名。"""
    from app.services.formula_push.rules import load_rules

    rules = load_rules()
    d1_rule = next(r for r in rules if r.rule_id == "D1.note.main")

    assert d1_rule.target.resolve_table("listed") == "应收票据"
    assert d1_rule.target.resolve_table("soe") == "应收票据分类"
    # 无 table_by_template 的规则回退到 table
    e1_rule = next(r for r in rules if r.rule_id == "E1.note.main_rows")
    assert e1_rule.target.resolve_table("listed") == "货币资金"
    assert e1_rule.target.resolve_table("soe") == "货币资金"


# ── Task 13：附注同步指纹验证 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_d1_sync_fingerprint_correct(env_listed):
    """推送写入后 _last_sync_wp_id / last_sync_source / last_sync_at 正确。"""
    await env_listed.seed_entries(base_entries())
    await env_listed.add_note("五、4", _d1_listed_note_data(), title="应收票据")

    result = await env_listed.push(codes=["D1"])

    note = await env_listed.note("五、4")

    # ORM 列
    assert note.last_sync_source == "formula_push"
    assert note.last_sync_wp_id == env_listed.d1_wp_id
    assert note.last_sync_at is not None

    # JSON 内指纹
    assert note.table_data["_last_sync_wp_id"] == str(env_listed.d1_wp_id)
    assert "_last_sync_at" in note.table_data


@pytest.mark.asyncio
async def test_push_then_pull_no_duplicate_sync(env_listed):
    """端到端：推送写入附注后，pull-from-workpapers 识别已同步、不重复拉取。

    在同一 SQLite ORM 环境先推送 D1→五、4，再模拟 pull 端点判定逻辑：
    - 推送后的五、4 带 ``_last_sync_wp_id`` → pull 走 synced 路径
    - 推送前的八、1（从未同步）→ pull 走 skipped_never_synced 路径
    """
    await env_listed.seed_entries(base_entries())
    await env_listed.add_note("五、4", _d1_listed_note_data(), title="应收票据")
    # 追加一个从未同步的章节（无 _last_sync_wp_id）
    await env_listed.add_note("八、1", {"rows": [{"label": "测试行"}], "headers": ["项目"]}, title="货币资金")

    # ── 推送 D1 ──
    await env_listed.push(codes=["D1"])

    # ── 模拟 pull-from-workpapers 端点的核心判定 ──
    # 端点逻辑（disclosure_notes.py pull_from_workpapers）:
    #   td = note.table_data
    #   if not td.get("_last_sync_wp_id"):
    #       skipped_never_synced += 1
    #       continue
    #   td["_source"] = "workpaper"; td["_last_sync_at"] = ...; synced += 1

    synced = 0
    skipped_never_synced = 0

    note_pushed = await env_listed.note("五、4")
    td_pushed = note_pushed.table_data or {}
    if not td_pushed.get("_last_sync_wp_id"):
        skipped_never_synced += 1
    else:
        synced += 1

    note_never = await env_listed.note("八、1")
    td_never = note_never.table_data or {}
    if not td_never.get("_last_sync_wp_id"):
        skipped_never_synced += 1
    else:
        synced += 1

    # 推送过的章节被识别为 synced
    assert synced == 1, f"推送后的章节应被 pull 识别为已同步，实际 synced={synced}"
    # 从未同步的章节被跳过
    assert skipped_never_synced == 1, f"从未同步的章节应被跳过，实际 skipped={skipped_never_synced}"

    # 进一步确认：推送后的 table_data 包含完整指纹
    assert td_pushed["_last_sync_wp_id"] == str(env_listed.d1_wp_id)
    assert "_last_sync_at" in td_pushed
    # 从未同步的 table_data 无指纹
    assert "_last_sync_wp_id" not in td_never
    assert "_last_sync_at" not in td_never


@pytest.mark.asyncio
async def test_d1_second_push_idempotent(env_listed):
    """D1 第二次推送值不变时合计行 action=unchanged。"""
    await env_listed.seed_entries(base_entries())
    await env_listed.add_note("五、4", _d1_listed_note_data(), title="应收票据")

    await env_listed.push(codes=["D1"])
    result2 = await env_listed.push(codes=["D1"])

    d1_note_items = [
        i for i in result2.items
        if i.rule_id == "D1.note.main" and i.stage == "note"
    ]
    # 合计行不变 → unchanged
    total_items = [i for i in d1_note_items if "合计" in (i.addr_id or "")]
    assert all(i.action == "unchanged" for i in total_items)


# ── Task 14：附注 stale 与报表联动 ──────────────────────────────────────


@pytest.mark.asyncio
async def test_d1_push_records_note_section_in_result(env_listed):
    """推送写入附注后 result.note_sections 包含该章节号。

    下游报表联动据此标 stale（由引擎调用方处理，这里只验证 result 输出）。
    """
    await env_listed.seed_entries(base_entries())
    await env_listed.add_note("五、4", _d1_listed_note_data(), title="应收票据")

    result = await env_listed.push(codes=["D1"])

    assert "五、4" in result.note_sections


@pytest.mark.asyncio
async def test_d1_push_broadcast_carries_note_sections(env_listed):
    """SSE 广播 formula.pushed 的 payload 包含 note_sections，下游据此标报表 stale。

    验证：result.summary() 传给 broadcast_raw 的载荷含 note_sections == ["五、4"]。
    这是报表 stale 联动的数据契约——前端 useNoteStale 和报表引擎都从此字段读章节列表。
    """
    await env_listed.seed_entries(base_entries())
    await env_listed.add_note("五、4", _d1_listed_note_data(), title="应收票据")

    env_listed.broadcasts.clear()
    await env_listed.push(codes=["D1"])

    assert len(env_listed.broadcasts) == 1, f"应有 1 条广播，实际 {len(env_listed.broadcasts)}"
    event, payload = env_listed.broadcasts[0]
    assert event == "formula.pushed"
    assert "note_sections" in payload, "SSE payload 必须包含 note_sections 字段"
    assert "五、4" in payload["note_sections"], f"payload note_sections={payload['note_sections']}"


@pytest.mark.asyncio
async def test_d1_push_note_sections_in_run_detail(env_listed):
    """运行记录 detail.note_sections 与 result.note_sections 一致。

    formula_push_run.detail 是运行记录 JSON，``note_sections`` 字段供公式管理面板回溯。
    """
    await env_listed.seed_entries(base_entries())
    await env_listed.add_note("五、4", _d1_listed_note_data(), title="应收票据")

    result = await env_listed.push(codes=["D1"])

    runs = await env_listed.runs()
    assert len(runs) >= 1
    latest = runs[-1]
    assert latest.detail["note_sections"] == list(result.note_sections)


@pytest.mark.asyncio
async def test_d1_soe_push_broadcast_carries_soe_section(env_soe):
    """国企项目推送 D1 后 SSE 广播的 note_sections 只含国企章节。"""
    await env_soe.seed_entries(base_entries())
    await env_soe.add_note("八、4", _d1_soe_note_data(), title="应收票据")

    env_soe.broadcasts.clear()
    await env_soe.push(codes=["D1"])

    assert len(env_soe.broadcasts) == 1
    _, payload = env_soe.broadcasts[0]
    assert "八、4" in payload["note_sections"]
    assert "五、4" not in payload.get("note_sections", []), "国企项目不应推上市章节"


# ── Task 15：多科目附注推送不互相覆盖 ──────────────────────────────────


@pytest.mark.asyncio
async def test_multi_code_note_push_no_overwrite(env_listed):
    """同一附注表内各行不被推送覆盖——引擎只写匹配到的行和合计行。

    五、4 有银行承兑汇票（800k）+ 商业承兑汇票（400k）+ 合计（0）。
    D1 推送后只重算合计行，不清零数据行。
    """
    await env_listed.seed_entries(base_entries())
    await env_listed.add_note("五、4", _d1_listed_note_data(), title="应收票据")

    result = await env_listed.push(codes=["D1"])

    note = await env_listed.note("五、4")
    rows = {r["label"]: r for r in note.table_data["sub_table_data"]["应收票据"]}

    # 数据行保持原值（引擎 note_rows 不匹配这些行标签，不会写入）
    assert rows["银行承兑汇票"]["end_balance"] == 800000
    assert rows["银行承兑汇票"]["prior_balance"] == 500000
    assert rows["商业承兑汇票"]["end_balance"] == 400000
    assert rows["商业承兑汇票"]["prior_balance"] == 400000

    # 合计行被重算 = 数据行之和
    assert rows["合计"]["end_balance"] == 1200000
    assert rows["合计"]["prior_balance"] == 900000


# ── Task 15：多科目附注推送不互相覆盖（同一章节，靠 table 名隔离） ────────


H2_TB = TbAuditedSnapshot(
    tb_data={
        "1604": {
            "期末余额": Decimal("5000000"),
            "年初余额": Decimal("3000000"),
            "本期发生额": Decimal("2000000"),
        },
    },
    available=True,
    company_codes=("001",),
)

# 五、23 章节同时容纳「在建工程」（H2）和「工程物资」（H4）两张子表的列定义
_NOTE_COLS_H = [
    {"key": "label", "label": "项目", "is_label": True},
    {"key": "end_amount", "label": "期末余额", "format": "amount"},
    {"key": "prior_amount", "label": "期初余额", "format": "amount"},
]


@pytest_asyncio.fixture
async def env_shared_chapter(monkeypatch):
    """SQLite 真 ORM 环境：上市项目 + H2 底稿 + 五、23 共享章节。

    验证同一附注章节内两张子表（在建工程 / 工程物资）互不覆盖。
    """
    async with make_env(monkeypatch) as e:
        # 追加 H2 底稿
        h2_idx, h2_wp = uuid.uuid4(), uuid.uuid4()
        async with e.factory() as db:
            await db.execute(sa.text(
                "INSERT INTO wp_index (id, project_id, wp_code) VALUES (:i, :p, 'H2')"
            ), {"i": str(h2_idx), "p": str(e.pid)})
            await db.execute(sa.text(
                "INSERT INTO working_paper (id, project_id, wp_index_id) VALUES (:w, :p, :i)"
            ), {"w": str(h2_wp), "p": str(e.pid), "i": str(h2_idx)})
            await db.commit()
        e.h2_wp_id = h2_wp

        # Mock balance_adj 取数
        async def fake_balance_adj_load(self, db, project_id, year, wp_id):
            if self.wp_code == "H2":
                self._last_tb_data = H2_TB.tb_data
                return BalanceAdjSources(
                    formula=FormulaSources(tb=H2_TB),
                    template_type="listed",
                )
            self._last_tb_data = None
            return BalanceAdjSources(formula=FormulaSources(), template_type="listed")

        monkeypatch.setattr(BalanceAdjudicationBinding, "load_sources", fake_balance_adj_load)

        # Mock Tier A 取数（env 默认有 E1）
        async def fake_tier_a_load(self, db, project_id, year, wp_id):
            return TierASources(formula=FormulaSources(), template_type="listed")

        monkeypatch.setattr(TierAAnchorBinding, "load_sources", fake_tier_a_load)

        async def fake_note_direct_load(self, db, project_id, year, wp_id):
            return NoteDirectSources(formula=FormulaSources(), template_type="listed")

        monkeypatch.setattr(NoteDirectBinding, "load_sources", fake_note_direct_load)

        async def fake_k1_load(self, db, project_id, year, wp_id):
            self._last_tb_data = None
            from app.services.formula_push.bindings.k1 import K1Sources
            return K1Sources(formula=FormulaSources(), template_type="listed")

        monkeypatch.setattr(K1Binding, "load_sources", fake_k1_load)

        yield e


@pytest.mark.asyncio
async def test_shared_chapter_multi_code_tables_no_overwrite(env_shared_chapter):
    """同一附注章节（五、23）内多科目各写各表——H2 推送不覆盖工程物资数据。

    需求 E11：同一附注章节被多个科目底稿推送时，各科目只写自己的行。
    引擎按 rule.target.table 定位 sub_table_data[table_name]，不同科目写不同
    table_name，互不覆盖。

    前置：五、23 章节包含「在建工程」（H2 目标）和「工程物资」（H4 预存数据）两张子表。
    动作：推送 H2。
    验证：「在建工程」表被 H2 审定数更新，「工程物资」表数据保持原值。
    """
    e = env_shared_chapter

    # 种五、23 章节：两张子表各有数据行 + 合计行
    note_data = {
        "_source": "workpaper",
        "_sub_table_columns": {
            "在建工程": _NOTE_COLS_H,
            "工程物资": _NOTE_COLS_H,
        },
        "sub_table_data": {
            "在建工程": [
                {"label": "在建工程", "end_amount": 0, "prior_amount": 0},
                {"label": "合计", "is_total": True, "end_amount": 0, "prior_amount": 0},
            ],
            "工程物资": [
                {"label": "工程物资", "end_amount": 888000, "prior_amount": 666000},
                {"label": "合计", "is_total": True, "end_amount": 888000, "prior_amount": 666000},
            ],
        },
    }
    await e.add_note("五、23", note_data, title="在建工程")

    # 推送 H2
    result = await e.push(codes=["H2"])

    note = await e.note("五、23")
    sub = note.table_data["sub_table_data"]

    # ─── 在建工程表：被 H2 推送更新为 TB 审定数 ─────────────────────────
    h2_rows = {r["label"]: r for r in sub["在建工程"]}
    assert h2_rows["在建工程"]["end_amount"] == 5000000, "H2 期末应为 TB 1604 期末余额"
    assert h2_rows["在建工程"]["prior_amount"] == 3000000, "H2 期初应为 TB 1604 年初余额"
    # 合计行被重算
    assert h2_rows["合计"]["end_amount"] == 5000000
    assert h2_rows["合计"]["prior_amount"] == 3000000

    # ─── 工程物资表：H2 推送完全不碰 ──────────────────────────────────
    h4_rows = {r["label"]: r for r in sub["工程物资"]}
    assert h4_rows["工程物资"]["end_amount"] == 888000, "工程物资期末应保持原值"
    assert h4_rows["工程物资"]["prior_amount"] == 666000, "工程物资期初应保持原值"
    assert h4_rows["合计"]["end_amount"] == 888000, "工程物资合计行不受 H2 推送影响"
    assert h4_rows["合计"]["prior_amount"] == 666000

    # 同步指纹只记录 H2 底稿
    assert note.table_data.get("_last_sync_wp_id") == str(e.h2_wp_id)
    assert note.last_sync_source == "formula_push"


@pytest.mark.asyncio
async def test_sequential_push_two_codes_different_sections(env_shared_chapter):
    """两个科目推送到不同章节——D1 推五、4，H2 推五、23，互不干扰。

    需求 E11 补充：验证同一次推送中不同科目写不同章节不交叉。
    """
    e = env_shared_chapter

    # 追加 D1 底稿
    d1_idx, d1_wp = uuid.uuid4(), uuid.uuid4()
    async with e.factory() as db:
        await db.execute(sa.text(
            "INSERT INTO wp_index (id, project_id, wp_code) VALUES (:i, :p, 'D1')"
        ), {"i": str(d1_idx), "p": str(e.pid)})
        await db.execute(sa.text(
            "INSERT INTO working_paper (id, project_id, wp_index_id) VALUES (:w, :p, :i)"
        ), {"w": str(d1_wp), "p": str(e.pid), "i": str(d1_idx)})
        await db.commit()

    # Mock Tier A 让 D1 返回 TB 数据
    original_load = TierAAnchorBinding.load_sources

    async def fake_tier_a_load_d1(self, db, project_id, year, wp_id):
        if self.wp_code == "D1":
            self._last_tb_data = {
                "1121": {
                    "期末余额": Decimal("1200000"),
                    "年初余额": Decimal("900000"),
                    "本期发生额": Decimal("300000"),
                },
            }
            return TierASources(
                formula=FormulaSources(tb=TbAuditedSnapshot(
                    tb_data=self._last_tb_data, available=True, company_codes=("001",)
                )),
                template_type="listed",
            )
        return TierASources(formula=FormulaSources(), template_type="listed")

    # monkeypatch 已经在 fixture 里设了 TierA，这里叠加
    TierAAnchorBinding.load_sources = fake_tier_a_load_d1

    try:
        # 种五、4（D1 目标章节）
        await e.add_note("五、4", _d1_listed_note_data(), title="应收票据")
        # 种五、23（H2 目标章节）
        h_note_data = {
            "_source": "workpaper",
            "_sub_table_columns": {"在建工程": _NOTE_COLS_H},
            "sub_table_data": {
                "在建工程": [
                    {"label": "在建工程", "end_amount": 0, "prior_amount": 0},
                    {"label": "合计", "is_total": True, "end_amount": 0, "prior_amount": 0},
                ],
            },
        }
        await e.add_note("五、23", h_note_data, title="在建工程")

        # 分别推送
        await e.push(codes=["D1"])
        await e.push(codes=["H2"])

        # 验证五、4 只有 D1 的数据
        note_d1 = await e.note("五、4")
        d1_sub = note_d1.table_data["sub_table_data"]["应收票据"]
        d1_rows = {r["label"]: r for r in d1_sub}
        assert d1_rows["银行承兑汇票"]["end_balance"] == 800000
        assert d1_rows["商业承兑汇票"]["end_balance"] == 400000

        # 验证五、23 只有 H2 的数据
        note_h2 = await e.note("五、23")
        h2_sub = note_h2.table_data["sub_table_data"]["在建工程"]
        h2_rows = {r["label"]: r for r in h2_sub}
        assert h2_rows["在建工程"]["end_amount"] == 5000000
        assert h2_rows["在建工程"]["prior_amount"] == 3000000
    finally:
        TierAAnchorBinding.load_sources = original_load


# ── Task 16：推送与前端同步的竞争保护 ──────────────────────────────────


@pytest.mark.asyncio
async def test_manual_cell_mode_preserved_on_push(env_listed):
    """附注中 _cell_modes manual 标记的单元格在推送后保持原值。"""
    await env_listed.seed_entries(base_entries())

    # 种一个有 manual 标记的附注行（业务键形态，六字段）
    note_data = {
        "_source": "workpaper",
        "_sub_table_columns": {"应收票据": NOTE_COLS_LISTED},
        "sub_table_data": {"应收票据": [
            {"label": "银行承兑汇票",
             "end_balance": 999, "end_provision": 99, "end_book_value": 900,
             "prior_balance": 888, "prior_provision": 88, "prior_book_value": 800,
             "_cell_modes": {"0": "manual"}},
            {"label": "商业承兑汇票",
             "end_balance": 400, "end_provision": 40, "end_book_value": 360,
             "prior_balance": 300, "prior_provision": 30, "prior_book_value": 270},
            {"label": "合计", "is_total": True,
             "end_balance": 0, "end_provision": 0, "end_book_value": 0,
             "prior_balance": 0, "prior_provision": 0, "prior_book_value": 0},
        ]},
    }
    await env_listed.add_note("五、4", note_data, title="应收票据")

    result = await env_listed.push(codes=["D1"])

    note = await env_listed.note("五、4")
    rows = {r["label"]: r for r in note.table_data["sub_table_data"]["应收票据"]}

    # 银行承兑汇票行有 manual 标记但 Tier A note_rows 不匹配该行，
    # 所以值保持原样（不被引擎写入）
    assert rows["银行承兑汇票"]["end_balance"] == 999
    assert rows["银行承兑汇票"]["prior_balance"] == 888


@pytest.mark.asyncio
async def test_locked_section_preserved_on_push(env_listed):
    """整节人工覆盖（_manual_override）的附注在推送后保持原值。"""
    await env_listed.seed_entries(base_entries())

    note_data = {
        "_source": "workpaper",
        "_manual_override": True,
        "_sub_table_columns": {"应收票据": NOTE_COLS_LISTED},
        "sub_table_data": {"应收票据": [
            {"label": "银行承兑汇票",
             "end_balance": 999, "end_provision": 99, "end_book_value": 900,
             "prior_balance": 888, "prior_provision": 88, "prior_book_value": 800},
            {"label": "商业承兑汇票",
             "end_balance": 777, "end_provision": 77, "end_book_value": 700,
             "prior_balance": 666, "prior_provision": 66, "prior_book_value": 600},
            {"label": "合计", "is_total": True,
             "end_balance": 1776, "end_provision": 176, "end_book_value": 1600,
             "prior_balance": 1554, "prior_provision": 154, "prior_book_value": 1400},
        ]},
    }
    await env_listed.add_note("五、4", note_data, title="应收票据")

    result = await env_listed.push(codes=["D1"])

    note = await env_listed.note("五、4")
    rows = {r["label"]: r for r in note.table_data["sub_table_data"]["应收票据"]}

    # _manual_override 时所有行都该保持原值（locked 模式）
    assert rows["合计"]["end_balance"] == 1776
    assert rows["合计"]["prior_balance"] == 1554


# ══════════════════════════════════════════════════════════════════════════════
# Task 2：D1 binding note_rows 从 entries 读分类 + 坏账快照
# ══════════════════════════════════════════════════════════════════════════════

import json as _json
from app.services.formula_push.bindings.tier_a import (
    _d1_note_rows_from_entries,
    _d1_category_slug,
    _safe_json_array,
)
from app.services.formula_push.rules import load_rules


# ── D1 entries 快照构造器 ────────────────────────────────────────────────

def _d1_cat_rows_json(rows: list[dict]) -> str:
    """构造 D1-cat-rows JSON 字符串（与前端 useD1DetailCategory serializeRows 同口径）。"""
    return _json.dumps(rows, ensure_ascii=False, separators=(",", ":"))


def _d1_bd_notetype_rows_json(rows: list[dict]) -> str:
    """构造 D1-bd-notetype-rows JSON 字符串（与前端 useD1BadDebt serializeNoteTypeRows 同口径）。"""
    return _json.dumps(rows, ensure_ascii=False, separators=(",", ":"))


def _make_cat_row(row_id: str, category: str, *,
                  prior_unadj=0.0, prior_aje=0.0, prior_rje=0.0,
                  cur_increase=0.0, cur_decrease=0.0,
                  cur_aje=0.0, cur_rje=0.0) -> dict:
    """构造单条分类行（只序列化录入列，与前端 serializeRows 一致）。"""
    return {
        "rowId": row_id,
        "category": category,
        "isFixed": row_id.startswith("fixed-"),
        "priorUnadjusted": prior_unadj,
        "priorAje": prior_aje,
        "priorRje": prior_rje,
        "currentIncrease": cur_increase,
        "currentDecrease": cur_decrease,
        "currentAje": cur_aje,
        "currentRje": cur_rje,
    }


def _make_bd_notetype_row(row_id: str, note_type: str, *,
                          prior_unadj=0.0, prior_aje=0.0, prior_rje=0.0,
                          cur_unadj=0.0, cur_aje=0.0, cur_rje=0.0) -> dict:
    """构造单条坏账按票据种类行（与前端 serializeNoteTypeRows 一致）。"""
    return {
        "rowId": row_id,
        "noteType": note_type,
        "isFixed": row_id.startswith("fixed-"),
        "priorUnadjusted": prior_unadj,
        "priorAje": prior_aje,
        "priorRje": prior_rje,
        "currentUnadjusted": cur_unadj,
        "currentAje": cur_aje,
        "currentRje": cur_rje,
    }


# ── slug 计算测试 ────────────────────────────────────────────────────────


def test_d1_slug_fixed_bank():
    assert _d1_category_slug("fixed-bank") == "bank"


def test_d1_slug_fixed_commercial():
    assert _d1_category_slug("fixed-commercial") == "commercial"


def test_d1_slug_dynamic_row():
    assert _d1_category_slug("dynamic-abc123") == "c-abc123"


def test_d1_slug_empty_fallback_bank():
    assert _d1_category_slug("", "银行承兑汇票") == "bank"


def test_d1_slug_empty_fallback_commercial():
    assert _d1_category_slug("", "商业承兑汇票") == "commercial"


def test_d1_slug_empty_no_match():
    assert _d1_category_slug("") == ""


# ── _safe_json_array 测试 ────────────────────────────────────────────────


def test_safe_json_array_normal():
    assert _safe_json_array('[{"a":1}]') == [{"a": 1}]


def test_safe_json_array_empty_string():
    assert _safe_json_array("") == []


def test_safe_json_array_none():
    assert _safe_json_array(None) == []


def test_safe_json_array_non_array():
    assert _safe_json_array('{"a":1}') == []


def test_safe_json_array_invalid_json():
    assert _safe_json_array("{not json}") == []


def test_safe_json_array_filters_non_dict():
    assert _safe_json_array('[1, "str", {"ok": true}, null]') == [{"ok": True}]


# ── _d1_note_rows_from_entries 单元测试 ──────────────────────────────────


def test_d1_note_rows_both_snapshots():
    """分类 + 坏账都有 → 六字段全 resolved。"""
    entries = {
        "D1-cat-rows": _d1_cat_rows_json([
            _make_cat_row("fixed-bank", "银行承兑汇票",
                          prior_unadj=500000, cur_increase=300000),
            _make_cat_row("fixed-commercial", "商业承兑汇票",
                          prior_unadj=400000, cur_increase=200000, cur_decrease=100000),
        ]),
        "D1-bd-notetype-rows": _d1_bd_notetype_rows_json([
            _make_bd_notetype_row("fixed-bank", "银行承兑汇票小计",
                                  prior_unadj=30000, cur_unadj=50000),
            _make_bd_notetype_row("fixed-commercial", "商业承兑汇票小计",
                                  prior_unadj=10000, cur_unadj=20000),
        ]),
    }
    rows = _d1_note_rows_from_entries(entries)

    assert len(rows) == 2

    bank = rows[0]
    assert bank["note_label"] == "银行承兑汇票"
    assert bank["label"] == "bank"
    assert bank["is_total"] is False
    assert bank["is_memo"] is False
    # 分类公式：priorAudited = 500000+0+0=500000；
    # currentUnadjusted = 500000+300000-0=800000；currentAudited = 800000+0+0=800000
    assert bank["end_balance"] == 800000.0
    assert bank["prior_balance"] == 500000.0
    # 坏账公式：priorAudited = 30000+0+0=30000；currentAudited = 50000+0+0=50000
    assert bank["end_provision"] == 50000.0
    assert bank["prior_provision"] == 30000.0
    # 账面价值 = 余额 - 坏账
    assert bank["end_book_value"] == 750000.0
    assert bank["prior_book_value"] == 470000.0
    assert all(bank[f"{f}_resolved"] for f in
               ("end_balance", "end_provision", "end_book_value",
                "prior_balance", "prior_provision", "prior_book_value"))

    comm = rows[1]
    assert comm["note_label"] == "商业承兑汇票"
    assert comm["label"] == "commercial"
    # 分类：priorAudited=400000，currentUnadjusted=400000+200000-100000=500000
    assert comm["end_balance"] == 500000.0
    assert comm["prior_balance"] == 400000.0
    # 坏账：priorAudited=10000，currentAudited=20000
    assert comm["end_provision"] == 20000.0
    assert comm["prior_provision"] == 10000.0
    assert comm["end_book_value"] == 480000.0
    assert comm["prior_book_value"] == 390000.0


def test_d1_note_rows_cat_only():
    """只有分类快照、无坏账 → provision=None、book_value=None、对应 resolved=False。"""
    entries = {
        "D1-cat-rows": _d1_cat_rows_json([
            _make_cat_row("fixed-bank", "银行承兑汇票", prior_unadj=100000),
        ]),
    }
    rows = _d1_note_rows_from_entries(entries)

    assert len(rows) == 1
    bank = rows[0]
    assert bank["end_balance"] == 100000.0
    assert bank["end_balance_resolved"] is True
    assert bank["prior_balance"] == 100000.0
    assert bank["prior_balance_resolved"] is True
    # 坏账缺失
    assert bank["end_provision"] is None
    assert bank["end_provision_resolved"] is False
    assert bank["prior_provision"] is None
    assert bank["prior_provision_resolved"] is False
    # 账面价值也缺失（不用余额补）
    assert bank["end_book_value"] is None
    assert bank["end_book_value_resolved"] is False
    assert bank["prior_book_value"] is None
    assert bank["prior_book_value_resolved"] is False


def test_d1_note_rows_bd_only():
    """只有坏账快照、无分类 → balance=None、book_value=None。"""
    entries = {
        "D1-bd-notetype-rows": _d1_bd_notetype_rows_json([
            _make_bd_notetype_row("fixed-bank", "银行承兑汇票小计", cur_unadj=50000),
        ]),
    }
    rows = _d1_note_rows_from_entries(entries)

    assert len(rows) == 1
    bank = rows[0]
    assert bank["end_balance"] is None
    assert bank["end_balance_resolved"] is False
    assert bank["end_provision"] == 50000.0
    assert bank["end_provision_resolved"] is True
    assert bank["end_book_value"] is None
    assert bank["end_book_value_resolved"] is False


def test_d1_note_rows_empty_entries():
    """两个快照都缺 → 返回空列表。"""
    assert _d1_note_rows_from_entries({}) == []


def test_d1_note_rows_dynamic_row():
    """动态行 slug 处理：dynamic-{uuid} → c-{uuid}。"""
    entries = {
        "D1-cat-rows": _d1_cat_rows_json([
            _make_cat_row("dynamic-abc123", "供应链票据", prior_unadj=200000),
        ]),
        "D1-bd-notetype-rows": _d1_bd_notetype_rows_json([
            # 坏账侧用相同的 rowId pattern
            _make_bd_notetype_row("dynamic-abc123", "供应链票据", cur_unadj=10000),
        ]),
    }
    rows = _d1_note_rows_from_entries(entries)

    assert len(rows) == 1
    row = rows[0]
    assert row["label"] == "c-abc123"
    assert row["note_label"] == "供应链票据"
    assert row["end_balance"] == 200000.0  # priorAudited=200000, cur all 0 → currentAudited=200000
    assert row["end_provision"] == 10000.0


def test_d1_note_rows_with_aje_rje():
    """审计调整分录参与计算。"""
    entries = {
        "D1-cat-rows": _d1_cat_rows_json([
            _make_cat_row("fixed-bank", "银行承兑汇票",
                          prior_unadj=500000, prior_aje=10000, prior_rje=5000,
                          cur_increase=300000,
                          cur_aje=20000, cur_rje=10000),
        ]),
        "D1-bd-notetype-rows": _d1_bd_notetype_rows_json([
            _make_bd_notetype_row("fixed-bank", "银行承兑汇票小计",
                                  prior_unadj=30000, prior_aje=2000, prior_rje=1000,
                                  cur_unadj=50000, cur_aje=3000, cur_rje=1500),
        ]),
    }
    rows = _d1_note_rows_from_entries(entries)

    bank = rows[0]
    # 分类：priorAudited = 500000+10000+5000 = 515000
    # currentUnadjusted = 515000+300000-0 = 815000
    # currentAudited = 815000+20000+10000 = 845000
    assert bank["prior_balance"] == 515000.0
    assert bank["end_balance"] == 845000.0
    # 坏账：priorAudited = 30000+2000+1000 = 33000
    # currentAudited = 50000+3000+1500 = 54500
    assert bank["prior_provision"] == 33000.0
    assert bank["end_provision"] == 54500.0
    # 账面价值
    assert bank["end_book_value"] == 845000.0 - 54500.0
    assert bank["prior_book_value"] == 515000.0 - 33000.0


def test_d1_note_rows_preserves_slug_order():
    """行顺序由分类快照中首次出现的 slug 决定。"""
    entries = {
        "D1-cat-rows": _d1_cat_rows_json([
            _make_cat_row("fixed-commercial", "商业承兑汇票", prior_unadj=100),
            _make_cat_row("fixed-bank", "银行承兑汇票", prior_unadj=200),
        ]),
    }
    rows = _d1_note_rows_from_entries(entries)

    assert [r["label"] for r in rows] == ["commercial", "bank"]


# ── TierAAnchorBinding.note_rows 代理测试 ────────────────────────────────


def test_d1_binding_note_rows_dispatches_to_entries():
    """D1 binding 的 note_rows 对 D1.note.main 规则走 entries 路径。"""
    rules = load_rules()
    d1_rule = next(r for r in rules if r.rule_id == "D1.note.main")
    binding = TierAAnchorBinding(wp_code="D1", account_prefixes=("1121",))

    entries = {
        "D1-cat-rows": _d1_cat_rows_json([
            _make_cat_row("fixed-bank", "银行承兑汇票", prior_unadj=100000),
        ]),
        "D1-bd-notetype-rows": _d1_bd_notetype_rows_json([
            _make_bd_notetype_row("fixed-bank", "银行承兑汇票小计", cur_unadj=5000),
        ]),
    }

    rows = binding.note_rows(entries, "listed", d1_rule)

    assert len(rows) == 1
    assert rows[0]["note_label"] == "银行承兑汇票"
    assert rows[0]["end_balance"] == 100000.0
    assert rows[0]["end_provision"] == 5000.0


def test_d2_binding_note_rows_still_uses_tb():
    """D2 等其他 Tier A 科目的 note_rows 仍走 TB 路径（不受 D1 改动影响）。"""
    rules = load_rules()
    d2_rules = [r for r in rules if r.rule_id.startswith("D2.note")]
    if not d2_rules:
        pytest.skip("D2 尚无附注规则")

    binding = TierAAnchorBinding(wp_code="D2", account_prefixes=("1122",))
    # 模拟 TB 数据已加载
    binding._last_tb_data = {
        "1122": {"期末余额": Decimal("500000"), "年初余额": Decimal("300000")},
    }
    rows = binding.note_rows({}, "listed", d2_rules[0])

    assert len(rows) >= 1
    assert rows[0].get("ending") is not None  # 旧 2-field 格式
    assert "end_balance" not in rows[0]  # 不是六字段格式


# ── D3~D7 note_rows 覆盖测试（Task 5 · 需求 E1, E2） ──────────────────


def test_d3_note_rows_tb_path():
    """D3 预收款项：单科目 2203，双字段 end_amount/prior_amount，走 TB 路径。"""
    rules = load_rules()
    d3_rule = next(r for r in rules if r.rule_id == "D3.note.main")
    assert d3_rule.target.sections == {"listed": "五、38", "soe": "八、38"}

    binding = TierAAnchorBinding(wp_code="D3", account_prefixes=("2203",))
    binding._last_tb_data = {
        "2203": {"期末余额": Decimal("120000"), "年初余额": Decimal("80000")},
    }
    rows = binding.note_rows({}, "listed", d3_rule)

    assert len(rows) == 1
    assert rows[0]["ending"] == 120000.0
    assert rows[0]["opening"] == 80000.0
    assert rows[0]["ending_resolved"] is True
    assert rows[0]["is_total"] is False


def test_d4_note_rows_pl_dual_code():
    """D4 营业收入+营业成本：损益类双科目 6001+6051，ending 取本期发生额，含合计行。"""
    rules = load_rules()
    d4_rule = next(r for r in rules if r.rule_id == "D4.note.main")
    assert d4_rule.target.sections == {"listed": "五、62", "soe": "八、64"}

    binding = TierAAnchorBinding(wp_code="D4", account_prefixes=("6001", "6051"))
    binding._last_tb_data = {
        "6001": {"本期发生额": Decimal("900000"), "年初余额": Decimal("700000")},
        "6051": {"本期发生额": Decimal("600000"), "年初余额": Decimal("500000")},
    }
    rows = binding.note_rows({}, "listed", d4_rule)

    # 双科目 → 2 行数据 + 1 行合计 = 3 行
    assert len(rows) == 3
    # 损益类：ending 取「本期发生额」
    assert rows[0]["ending"] == 900000.0
    assert rows[0]["opening"] == 700000.0
    assert rows[1]["ending"] == 600000.0
    assert rows[1]["opening"] == 500000.0
    # 合计行
    assert rows[2]["is_total"] is True
    assert rows[2]["ending"] == 1500000.0
    assert rows[2]["opening"] == 1200000.0


def test_d5_note_rows_note_direct():
    """D5 应收款项融资：走 NoteDirectBinding（非 Tier A），单科目 1124。"""
    rules = load_rules()
    d5_rule = next(r for r in rules if r.rule_id == "D5.note.main")
    assert d5_rule.target.sections == {"listed": "五、6", "soe": "八、6"}

    binding = NoteDirectBinding(
        wp_code="D5", account_codes=("1124",), account_name="应收款项融资",
    )
    binding._last_tb_data = {
        "1124": {"期末余额": Decimal("250000"), "年初余额": Decimal("180000")},
    }
    rows = binding.note_rows({}, "soe", d5_rule)

    assert len(rows) == 1
    assert rows[0]["ending"] == 250000.0
    assert rows[0]["opening"] == 180000.0
    assert rows[0]["ending_resolved"] is True


def test_d6_note_rows_tb_path():
    """D6 合同资产：单科目 1141，双字段；有 table_by_template（上市「合同资产」/ 国企「合同资产情况」）。"""
    rules = load_rules()
    d6_rule = next(r for r in rules if r.rule_id == "D6.note.main")
    assert d6_rule.target.sections == {"listed": "五、10", "soe": "八、11"}
    # table_by_template 验证
    assert d6_rule.target.resolve_table("listed") == "合同资产"
    assert d6_rule.target.resolve_table("soe") == "合同资产情况"

    binding = TierAAnchorBinding(wp_code="D6", account_prefixes=("1141",))
    binding._last_tb_data = {
        "1141": {"期末余额": Decimal("350000"), "年初余额": Decimal("200000")},
    }
    rows = binding.note_rows({}, "soe", d6_rule)

    assert len(rows) == 1
    assert rows[0]["ending"] == 350000.0
    assert rows[0]["opening"] == 200000.0


def test_d7_note_rows_tb_path():
    """D7 合同负债：单科目 2205，双字段，上市/国企同表名。"""
    rules = load_rules()
    d7_rule = next(r for r in rules if r.rule_id == "D7.note.main")
    assert d7_rule.target.sections == {"listed": "五、39", "soe": "八、39"}

    binding = TierAAnchorBinding(wp_code="D7", account_prefixes=("2205",))
    binding._last_tb_data = {
        "2205": {"期末余额": Decimal("430000"), "年初余额": Decimal("310000")},
    }
    rows = binding.note_rows({}, "listed", d7_rule)

    assert len(rows) == 1
    assert rows[0]["ending"] == 430000.0
    assert rows[0]["opening"] == 310000.0
    assert rows[0]["is_total"] is False


def test_d3_to_d7_rules_have_correct_fields():
    """D2~D7 全部使用 end_amount / prior_amount 双字段（D1 是六字段）。"""
    rules = load_rules()
    expected_fields = {"end_amount", "prior_amount"}
    for code in ["D2", "D3", "D4", "D5", "D6", "D7"]:
        rule = next(r for r in rules if r.rule_id == f"{code}.note.main")
        actual = set(rule.target.fields)
        assert actual == expected_fields, f"{code} fields mismatch: {actual}"


def test_d4_soe_section_differs_from_listed():
    """D4 上市 五、62 / 国企 八、64 —— 验证非对称章节号的科目选路正确。"""
    rules = load_rules()
    d4_rule = next(r for r in rules if r.rule_id == "D4.note.main")
    assert d4_rule.target.sections.get("listed") == "五、62"
    assert d4_rule.target.sections.get("soe") == "八、64"
    # soe 章节号与 listed 不对称（62 vs 64）
    assert d4_rule.target.sections["listed"][-2:] != d4_rule.target.sections["soe"][-2:]
