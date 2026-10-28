"""附注权威源交接：推送写过的格，底稿披露同步写入后保持推送值（spec note-pull-followup-closure R3 / ADR-3）。

SQLite 真 ORM：先跑生产推送（E1 → 上市 五、1「货币资金」），再调生产的 ``sync_from_workpaper`` / ``sync_from_html``
写入披露 Tab 的（发布前、过时的）数，断言推送拥有的格恢复为推送值、合计按本表重算、差异逐格回报；人工覆盖、规则停用、
没推过的表不动；HTML 入口按表名浅合并（原先整体替换，未推的子表丢失）。
"""
from __future__ import annotations

import copy
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio

from app.services import wp_disclosure_sync_service as sync_mod
from app.services.note_push_ownership import parse_note_addr, reapply_pushed_cells
from tests._formula_push_env import YEAR, base_entries, make_env

E1_NOTE_RULE = "E1.note.main_rows"
COLS = [
    {"key": "label", "flat": True, "label": "项目", "is_label": True},
    {"key": "end_amount", "label": "期末余额", "format": "amount"},
    {"key": "prior_amount", "label": "上年年末余额", "format": "amount"},
]
RESTRICTED = [{"label": "保证金", "end_amount": 9}]


def _note_data() -> dict:
    return {
        "_source": "workpaper", "_last_sync_wp_id": "底稿同步过",
        "_sub_table_columns": {"货币资金": COLS},
        "sub_table_data": {
            "货币资金": [
                {"label": "库存现金", "end_amount": 1, "prior_amount": 1},
                {"label": "银行存款", "end_amount": 0, "prior_amount": 0},
                {"label": "手工加的行", "end_amount": 5, "prior_amount": 0},
                {"label": "合计", "is_total": True, "end_amount": 6, "prior_amount": 1},
            ],
            "受限制的货币资金明细": copy.deepcopy(RESTRICTED),
        },
    }


def _rows(td: dict, table: str = "货币资金") -> dict[str, dict]:
    return {r["label"]: r for r in td["sub_table_data"][table]}


@pytest_asyncio.fixture
async def env(monkeypatch):
    async with make_env(monkeypatch) as e:
        await e.seed_entries(base_entries())
        await e.add_note("五、1", _note_data())
        await e.push()
        e.pushed = _rows((await e.note("五、1")).table_data)
        yield e


async def _sync(env, table_rows: list[dict], **kw) -> dict:
    async with env.factory() as db:
        return await sync_mod.sync_from_workpaper(
            db, env.pid, wp_id=env.wp_id, sheet_name="附注披露信息(上市公司)", section_id="五、1",
            sub_table_data={"货币资金": table_rows}, current_standard="listed_standalone",
            user=SimpleNamespace(id=uuid.uuid4()), year=YEAR, sub_table_columns={"货币资金": COLS}, **kw,
        )


def _stale_disclosure(env) -> list[dict]:
    """底稿披露 Tab 里发布前的数：库存现金期末与推送值不同，银行存款与推送值相同，手工行改了。"""
    return [
        {"label": "库存现金", "end_amount": 999, "prior_amount": env.pushed["库存现金"]["prior_amount"]},
        {"label": "银行存款", "end_amount": env.pushed["银行存款"]["end_amount"],
         "prior_amount": env.pushed["银行存款"]["prior_amount"]},
        {"label": "手工加的行", "end_amount": 7, "prior_amount": 0},
        {"label": "合计", "is_total": True, "end_amount": 1500, "prior_amount": 0},
    ]


def test_parse_note_addr() -> None:
    assert parse_note_addr("note://五、1/货币资金/库存现金.end") == ("五、1", "货币资金", "库存现金", "end")
    assert parse_note_addr("note://八、5/（1）按账龄披露应收账款/合  计.prior") == (
        "八、5", "（1）按账龄披露应收账款", "合  计", "prior")
    assert parse_note_addr("E1/E1-1/x") is None and parse_note_addr("note://五、1/货币资金/x.mid") is None


@pytest.mark.asyncio
async def test_sync_keeps_pushed_cells_and_recomputes_total(env) -> None:
    pushed_cash = env.pushed["库存现金"]["end_amount"]
    assert pushed_cash not in (999, 1), "推送确实写了库存现金期末（夹具不空转）"
    result = await _sync(env, _stale_disclosure(env))

    rows = _rows((await env.note("五、1")).table_data)
    assert rows["库存现金"]["end_amount"] == pushed_cash, "推送写过的格保持试算表审定数"
    assert rows["手工加的行"]["end_amount"] == 7, "推送没写过的行跟随披露同步"
    expected_total = pushed_cash + env.pushed["银行存款"]["end_amount"] + 7
    assert rows["合计"]["end_amount"] == expected_total and rows["合计"]["prior_amount"] == (
        env.pushed["库存现金"]["prior_amount"] + env.pushed["银行存款"]["prior_amount"]), "合计按本表重算"
    kept = {(k["row"], k["period"], k["kind"]): k for k in result["push_kept"]}
    assert kept[("库存现金", "end", "cell")]["incoming"] == 999
    assert kept[("库存现金", "end", "cell")]["pushed"] == pushed_cash
    assert kept[("合计", "end", "total")]["incoming"] == 1500
    assert ("银行存款", "end", "cell") not in kept, "与推送值相同的格不报"
    assert (await env.note("五、1")).table_data["sub_table_data"]["受限制的货币资金明细"] == RESTRICTED


@pytest.mark.asyncio
async def test_sync_that_agrees_with_push_reports_nothing(env) -> None:
    rows = [dict(r) for r in env.pushed.values()]
    result = await _sync(env, rows)
    assert result["push_kept"] == []
    assert _rows((await env.note("五、1")).table_data) == env.pushed


@pytest.mark.asyncio
async def test_manual_override_section_is_left_alone(env) -> None:
    """整节人工覆盖：推送也不写（keep_locked），交接同样不动（同步是否写入由人工覆盖守卫裁决）。"""
    td = {"_manual_override": True, "sub_table_data": {"货币资金": _stale_disclosure(env)},
          "_sub_table_columns": {"货币资金": COLS}}
    before = copy.deepcopy(td)
    async with env.factory() as db:
        kept = await reapply_pushed_cells(db, project_id=env.pid, year=YEAR, section="五、1", table_data=td,
                                          touched=["货币资金"])
    assert kept == [] and td == before
    del td["_manual_override"]
    async with env.factory() as db:
        kept = await reapply_pushed_cells(db, project_id=env.pid, year=YEAR, section="五、1", table_data=td,
                                          touched=["货币资金"])
    assert kept, "去掉人工覆盖后恢复推送值（判据不空转）"


@pytest.mark.asyncio
async def test_deleted_rule_no_longer_owns_cells(env, monkeypatch) -> None:
    """推送状态还在、规则已从清单删除 ⇒ 不认（2026-10-27 删除的子表规则在真库留有状态）。"""
    from app.services.formula_settings import push_settings

    real = push_settings.effective_push_rules

    async def without_e1(db, project_id):
        rules, issues = await real(db, project_id)
        return [r for r in rules if r.rule_id != E1_NOTE_RULE], issues

    monkeypatch.setattr(push_settings, "effective_push_rules", without_e1)
    result = await _sync(env, _stale_disclosure(env))
    assert result["push_kept"] == []
    assert _rows((await env.note("五、1")).table_data)["库存现金"]["end_amount"] == 999


async def _write_push_setting(env, definition: dict) -> None:
    from app.services.formula_settings.stores import get_store

    async with env.factory() as db:
        await get_store("push").write_project(
            db, env.pid, E1_NOTE_RULE, definition=definition, base_definition=None, base_version=None,
            pinned=False, base_origin=None, base_template_id=None, user_id=None)
        await db.commit()


@pytest.mark.asyncio
async def test_rule_disabled_for_project_no_longer_owns_cells(env) -> None:
    """本项目停用规则（公式治理内核写停用定义）：有效规则清单仍列出该规则但 status=disabled ⇒ 不认；启用后恢复。"""
    await _write_push_setting(env, {"disabled": True})
    result = await _sync(env, _stale_disclosure(env))
    assert result["push_kept"] == []
    assert _rows((await env.note("五、1")).table_data)["库存现金"]["end_amount"] == 999

    await _write_push_setting(env, {"disabled": False})
    result = await _sync(env, _stale_disclosure(env))
    assert any(k["row"] == "库存现金" and k["kind"] == "cell" for k in result["push_kept"]), "启用后照常交接（判据不空转）"
    assert _rows((await env.note("五、1")).table_data)["库存现金"]["end_amount"] == env.pushed["库存现金"]["end_amount"]


@pytest.mark.asyncio
async def test_cells_not_in_auto_state_are_not_owned(env) -> None:
    """推送状态不是 auto（附注标了人工 / 锁定、待确认）⇒ 推送自己都不写的格，交接也不认。"""
    from sqlalchemy import update

    from app.models.formula_push_models import FormulaPushState

    async with env.factory() as db:
        await db.execute(update(FormulaPushState).where(
            FormulaPushState.addr_id == "note://五、1/货币资金/库存现金.end").values(state="manual"))
        await db.commit()
    result = await _sync(env, _stale_disclosure(env))
    assert not any(k["row"] == "库存现金" and k["period"] == "end" for k in result["push_kept"])
    assert _rows((await env.note("五、1")).table_data)["库存现金"]["end_amount"] == 999


@pytest.mark.asyncio
async def test_fallback_total_is_restored_like_a_cell(env) -> None:
    """表里只有合计格是推送写的（合计行兜底写入科目合计）⇒ 同步来的合计恢复为推送值；其余行跟随同步。"""
    from app.models.formula_push_models import FormulaPushState

    async with env.factory() as db:
        db.add(FormulaPushState(
            id=uuid.uuid4(), project_id=env.pid, year=YEAR, addr_id="note://五、1/受限制的货币资金明细/合计.end",
            rule_id=E1_NOTE_RULE, domain="note", note_section="五、1", state="auto", last_pushed_value=50.0,
        ))
        await db.commit()
        td = {"sub_table_data": {"受限制的货币资金明细": [
            {"label": "保证金", "end_amount": 30}, {"label": "合  计", "is_total": True, "end_amount": 30},
        ]}}
        kept = await reapply_pushed_cells(db, project_id=env.pid, year=YEAR, section="五、1", table_data=td,
                                          touched=["受限制的货币资金明细"])
    assert kept == [{"table": "受限制的货币资金明细", "row": "合计", "period": "end", "field": "end_amount",
                     "kind": "fallback_total", "pushed": 50.0, "incoming": 30}]
    assert td["sub_table_data"]["受限制的货币资金明细"] == [
        {"label": "保证金", "end_amount": 30}, {"label": "合  计", "is_total": True, "end_amount": 50.0}]


@pytest.mark.asyncio
async def test_untouched_tables_and_unknown_states_are_ignored(env) -> None:
    async with env.factory() as db:
        td = {"sub_table_data": {"货币资金": [{"label": "库存现金", "end_amount": 999}]}}
        assert await reapply_pushed_cells(db, project_id=env.pid, year=YEAR, section="五、1", table_data=td,
                                          touched=["受限制的货币资金明细"]) == []
        assert td["sub_table_data"]["货币资金"][0]["end_amount"] == 999, "没同步的表不动"
        assert await reapply_pushed_cells(db, project_id=env.pid, year=YEAR, section="五、2", table_data=td,
                                          touched=["货币资金"]) == [], "别的章节的推送状态不认"


@pytest.mark.asyncio
async def test_html_entry_merges_tables_and_keeps_pushed_cells(env, monkeypatch) -> None:
    """HTML 入口：按表名浅合并（原先整体替换 sub_table_data，本次没推的「受限制的货币资金明细」丢失），推送格同样保持。"""
    note_id = (await env.note("五、1")).id
    service = sync_mod.WpDisclosureSyncService()

    async def mapping(db, wp_id, sheet):
        return {"section_id": "五、1", "note_id": note_id}

    async def no_audit(*args, **kwargs):
        return None

    monkeypatch.setattr(service, "_get_section_mapping", mapping)
    monkeypatch.setattr(service, "_write_audit_log", no_audit)
    monkeypatch.setattr(service, "_broadcast_synced", lambda *a, **k: None)
    async with env.factory() as db:
        result = await service.sync_from_html(
            db, env.wp_id, "附注披露信息(上市公司)", {"货币资金": _stale_disclosure(env)},
            project_id=env.pid, user=SimpleNamespace(id=uuid.uuid4()), sub_table_columns={"货币资金": COLS},
            force=True,
        )
    td = (await env.note("五、1")).table_data
    assert td["sub_table_data"]["受限制的货币资金明细"] == RESTRICTED, "未推的子表保留"
    assert _rows(td)["库存现金"]["end_amount"] == env.pushed["库存现金"]["end_amount"]
    assert any(k["row"] == "库存现金" for k in result["push_kept"])
