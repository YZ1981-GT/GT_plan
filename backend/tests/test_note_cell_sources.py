"""附注单元格最终来源诊断（spec note-chain-followup-optimizations R2 / ADR-3）。SQLite 真 ORM + 真推送 + 真路由。

判据：①推送写过且未被改的格 ⇒ 最终来源是推送；之后被同步改了 ⇒ 底稿同步 + 冲突 ②整节人工覆盖挡推送与同步 ③用户公式覆盖、
结果对不上报冲突；投影表上预设公式只核对（一致 / 保留底稿值 / 待补空）④存储表：人工 / 锁定 > 预设公式 > 模板取数；第 n 张表
坐标 ⑤位置化来源行的人工标记与推送同口径 ⑥诊断只读（章节数据逐字节不变、会话无改动）⑦端点：成员 200、非成员 403、
章节不存在 404、缺坐标 422。
"""
from __future__ import annotations

import copy
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite JSONB 兼容
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, PermissionLevel, ProjectStatus, ProjectUserRole
from app.models.core import Project, ProjectUser, User
from app.models.formula_push_models import FormulaPushState
from app.models.formula_setting_models import FormulaSetting, FormulaSyncItem
from app.models.report_models import ContentType, DisclosureNote
from app.services.note_cell_sources import diagnose_cell
from tests._formula_push_env import YEAR, base_entries, make_env
from tests.test_note_text_batch_endpoints import _Actor

COLS = [
    {"key": "label", "flat": True, "label": "项目", "is_label": True},
    {"key": "end_amount", "label": "期末余额", "format": "amount"},
    {"key": "prior_amount", "label": "上年年末余额", "format": "amount"},
]


def _cash_note() -> dict:
    return {
        "_source": "workpaper", "_last_sync_wp_id": "底稿同步过", "_last_sync_sheet": "附注披露信息(上市公司)",
        "_last_sync_at": "2026-10-29T10:00:00+00:00",
        "_sub_table_columns": {"货币资金": COLS},
        "sub_table_data": {"货币资金": [
            {"label": "库存现金", "end_amount": 1, "prior_amount": 1},
            {"label": "银行存款", "end_amount": 0, "prior_amount": 0},
            {"label": "手工加的行", "end_amount": 5, "prior_amount": 0},
            {"label": "合计", "is_total": True, "end_amount": 6, "prior_amount": 1},
        ]},
    }


def _kinds(steps: list[dict]) -> dict[str, str]:
    return {s["kind"]: s["status"] for s in steps}


@pytest_asyncio.fixture
async def pushed(monkeypatch):
    """E1 推送到上市 五、1「货币资金」（生产推送引擎）。"""
    async with make_env(monkeypatch) as e:
        await e.seed_entries(base_entries())
        await e.add_note("五、1", _cash_note())
        await e.push()
        yield e


async def _diagnose(env, **kw) -> dict:
    async with env.factory() as db:
        return await diagnose_cell(db, env.pid, YEAR, "五、1", **kw)


async def _set_td(env, mutate) -> None:
    async with env.factory() as db:
        note = (await db.execute(sa.select(DisclosureNote).where(DisclosureNote.project_id == env.pid))).scalar_one()
        td = copy.deepcopy(note.table_data)
        mutate(td)
        note.table_data = td
        await db.commit()


@pytest.mark.asyncio
async def test_pushed_cell_is_final_push_then_overwritten_value_is_a_conflict(pushed) -> None:
    out = await _diagnose(pushed, sub_table_key="货币资金", row=0, value_key="end_amount")
    assert out["projected"] and out["storage"]["kind"] == "sub_table" and out["storage"]["value_key"] == "end_amount"
    assert out["row_label"] == "库存现金" and out["final"]["kind"] == "push", out["final"]
    push = next(p for p in out["pushes"] if p["rule_id"] == "E1.note.main_rows")
    assert push["matches_current"] is True and push["state"] == "auto" and push["ambiguous"] is False
    assert _kinds(out["steps"])["sync"] == "overridden"

    await _set_td(pushed, lambda td: td["sub_table_data"]["货币资金"][0].update(end_amount=999))
    out = await _diagnose(pushed, sub_table_key="货币资金", row=0, value_key="end_amount")
    assert out["value"] == 999 and out["final"]["kind"] == "workpaper_sync"
    assert [c["kind"] for c in out["conflicts"]] == ["push_overwritten"]
    assert "附注披露信息(上市公司)" in out["final"]["detail"] and "2026-10-29 10:00:00" in out["final"]["detail"]


@pytest.mark.asyncio
async def test_push_states_only_match_their_own_column(pushed) -> None:
    """期初列（prior_amount）只认期初地址；手工加的行没有推送状态。"""
    prior = await _diagnose(pushed, sub_table_key="货币资金", row=0, value_key="prior_amount")
    assert prior["pushes"] and all(p["addr_id"].endswith(".prior") for p in prior["pushes"])
    manual_row = await _diagnose(pushed, sub_table_key="货币资金", row=2, value_key="end_amount")
    assert manual_row["pushes"] == [] and manual_row["final"]["kind"] == "workpaper_sync"


@pytest.mark.asyncio
async def test_push_state_of_another_table_is_not_this_cell(pushed) -> None:
    """另一张子表同一行号、同名合计的推送状态不算这一格（按推送同一套找表认表，不按行号）。"""
    def add_table(td):
        td["sub_table_data"]["受限制的货币资金明细"] = [
            {"label": "保证金", "end_amount": 1}, {"label": "冻结", "end_amount": 1}, {"label": "其他", "end_amount": 1},
            {"label": "合计", "is_total": True, "end_amount": 3}]
        td["_sub_table_columns"]["受限制的货币资金明细"] = copy.deepcopy(COLS)

    await _set_td(pushed, add_table)
    async with pushed.factory() as db:
        db.add(FormulaPushState(project_id=pushed.pid, year=YEAR, addr_id="note://五、1/受限制的货币资金明细/合计.end",
                                rule_id="E1.note.main_rows", domain="note", note_section="五、1", state="auto",
                                last_pushed_value=3.0))
        await db.commit()
    out = await _diagnose(pushed, sub_table_key="货币资金", row=3, value_key="end_amount")
    assert "note://五、1/受限制的货币资金明细/合计.end" not in {p["addr_id"] for p in out["pushes"]}
    other = await _diagnose(pushed, sub_table_key="受限制的货币资金明细", row=3, value_key="end_amount")
    assert [p["addr_id"] for p in other["pushes"]] == ["note://五、1/受限制的货币资金明细/合计.end"]


@pytest.mark.asyncio
async def test_source_row_number_maps_past_hidden_expandable_rows(pushed) -> None:
    """来源行号 ≠ 显示行号（空的可扩位行不显示）：按来源行号定位到显示的那一行。"""
    await _set_td(pushed, lambda td: td["sub_table_data"]["货币资金"].insert(1, {"label": "……", "row_type": "expandable"}))
    out = await _diagnose(pushed, sub_table_key="货币资金", row=2, value_key="end_amount")
    assert out["row_label"] == "银行存款" and out["row"] == 1 and out["storage"]["source_row"] == 2


@pytest.mark.asyncio
async def test_section_override_blocks_push_and_sync(pushed) -> None:
    await _set_td(pushed, lambda td: td.update(_manual_override=True))
    out = await _diagnose(pushed, sub_table_key="货币资金", row=0, value_key="end_amount")
    assert out["section_manual_override"] and out["final"]["kind"] == "section_override"
    steps = _kinds(out["steps"])
    assert steps["push"] == "blocked" and steps["sync"] == "blocked"


@pytest.mark.asyncio
async def test_user_formula_overrides_and_differing_result_is_reported(pushed) -> None:
    await _set_td(pushed, lambda td: td.update(_user_formulas=[
        {"target": "0:0", "formula": "cell(2,0) + 1", "category": "auto_calc", "layer": "project"}]))
    out = await _diagnose(pushed, sub_table_key="货币资金", row=0, value_key="end_amount")
    assert out["final"]["kind"] == "user_formula" and out["formula"]["layer_label"] == "本项目"
    assert out["formula"]["check"]["value"] == 6.0
    assert "formula_differs" in [c["kind"] for c in out["conflicts"]]
    assert _kinds(out["steps"])["push"] == "overridden"


@pytest.mark.asyncio
async def test_presets_on_projection_only_check_keep_or_fill(pushed) -> None:
    """投影表上的预设合计：一致 ⇒ 核对一致；底稿值不同 ⇒ 保留底稿值并报差异；为空 ⇒ 待补。"""
    total = await _diagnose(pushed, sub_table_key="货币资金", row=3, value_key="end_amount")
    assert total["formula"]["kind"] == "preset_formula" and _kinds(total["steps"])["formula"] == "consistent"

    await _set_td(pushed, lambda td: td["sub_table_data"]["货币资金"][3].update(end_amount=12345))
    total = await _diagnose(pushed, sub_table_key="货币资金", row=3, value_key="end_amount")
    assert _kinds(total["steps"])["formula"] == "kept"
    assert "workpaper_differs" in [c["kind"] for c in total["conflicts"]]

    await _set_td(pushed, lambda td: td["sub_table_data"]["货币资金"][3].update(end_amount=None))
    total = await _diagnose(pushed, sub_table_key="货币资金", row=3, value_key="end_amount")
    assert _kinds(total["steps"])["formula"] == "pending" and total["final"]["kind"] != "preset_formula"


@pytest.mark.asyncio
async def test_positional_source_row_manual_mark_is_final(pushed) -> None:
    def positional(td):
        td["sub_table_data"]["货币资金"][2] = {"label": "手工加的行", "values": [5, 0], "_cell_modes": {"0": "manual"}}

    await _set_td(pushed, positional)
    out = await _diagnose(pushed, sub_table_key="货币资金", row=2, value_key="end_amount")
    assert out["mode"] == "manual" and out["final"]["kind"] == "manual"


@pytest.mark.asyncio
async def test_diagnosis_is_read_only(pushed) -> None:
    before = copy.deepcopy((await pushed.note("五、1")).table_data)
    async with pushed.factory() as db:
        await diagnose_cell(db, pushed.pid, YEAR, "五、1", sub_table_key="货币资金", row=3, value_key="end_amount")
        assert not db.dirty and not db.new and not db.deleted
    assert (await pushed.note("五、1")).table_data == before


@pytest.mark.asyncio
async def test_bad_coordinates_and_missing_section(pushed) -> None:
    assert (await _diagnose(pushed, sub_table_key="没有这张表", row=0))["error"] == "cell_not_found"
    assert "第 9 行" in (await _diagnose(pushed, sub_table_key="货币资金", row=8))["message"]
    assert (await _diagnose(pushed, sub_table_key="货币资金", row=0, value_key="nope"))["error"] == "cell_not_found"
    with pytest.raises(LookupError):
        async with pushed.factory() as db:
            await diagnose_cell(db, pushed.pid, YEAR, "九、99", row=0)


# ─── 存储表（模板生成的附注）+ 端点 ────────────────────────────────────────────

HEADERS = ["项目", "期末余额", "期初余额"]


def _stored_note() -> dict:
    first = {"name": "货币资金", "headers": HEADERS, "rows": [
        {"label": "库存现金", "values": [100.0, 80.0],
         "_cell_meta": {"0": {"binding_id": "五、1.库存现金.closing_balance", "semantic": "closing_balance"}}},
        {"label": "银行存款", "values": [50.0, 20.0], "_cell_modes": {"0": "manual", "1": "locked"}},
        {"label": "合计", "is_total": True, "values": [150.0, 999.0]},
    ]}
    second = {"name": "受限制的货币资金", "headers": ["项目", "期末余额"], "rows": [
        {"label": "保证金", "values": [7.0]}, {"label": "合计", "is_total": True, "values": [7.0]}]}
    return {"_source": "template", "_tables": [first, second], "rows": copy.deepcopy(first["rows"])}


@pytest_asyncio.fixture
async def api() -> AsyncGenerator[dict, None]:
    from app.routers import disclosure_notes

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[
            User.__table__, Project.__table__, ProjectUser.__table__, DisclosureNote.__table__,
            FormulaPushState.__table__, FormulaSetting.__table__, FormulaSyncItem.__table__]))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {k: uuid.uuid4() for k in ("me", "outsider", "p")}
    async with factory() as s:
        s.add(Project(id=ids["p"], name="甲_2025", client_name="甲公司", template_type="listed",
                      report_scope="standalone", status=ProjectStatus.execution))
        await s.flush()
        s.add_all([
            ProjectUser(project_id=ids["p"], user_id=ids["me"], role=ProjectUserRole.auditor,
                        permission_level=PermissionLevel.readonly),
            DisclosureNote(project_id=ids["p"], year=YEAR, note_section="五、1", section_title="货币资金",
                           content_type=ContentType.table, table_data=_stored_note()),
        ])
        await s.commit()
    app = FastAPI()
    app.include_router(disclosure_notes.router)

    async def _db():
        async with factory() as session:
            yield session

    actor = {"user": _Actor(ids["me"])}
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: actor["user"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield {"client": client, "ids": ids, "actor": actor, "factory": factory,
               "url": f"/api/disclosure-notes/{ids['p']}/{YEAR}/五、1/cell-sources"}
    await engine.dispose()


@pytest.mark.asyncio
async def test_stored_tables_manual_binding_and_preset_order(api) -> None:
    async with api["factory"]() as db:
        bound = await diagnose_cell(db, api["ids"]["p"], YEAR, "五、1", row=0, col=0)
        manual = await diagnose_cell(db, api["ids"]["p"], YEAR, "五、1", row=1, col=1)
        total = await diagnose_cell(db, api["ids"]["p"], YEAR, "五、1", row=2, col=1)
        second = await diagnose_cell(db, api["ids"]["p"], YEAR, "五、1", table_index=1, row=1, col=0)
    assert bound["final"]["kind"] == "binding" and bound["binding"]["binding_id"] == "五、1.库存现金.closing_balance"
    assert not bound["projected"] and bound["storage"]["kind"] == "table"
    assert manual["mode"] == "locked" and manual["final"]["kind"] == "locked"
    assert total["final"]["kind"] == "preset_formula" and total["formula"]["check"]["value"] == 100.0
    assert [c["kind"] for c in total["conflicts"]] == ["formula_differs"]
    assert second["target"] == "t1:1:0" and second["table_name"] == "受限制的货币资金"
    assert second["final"]["kind"] == "preset_formula" and second["conflicts"] == []


@pytest.mark.asyncio
async def test_endpoint_member_outsider_missing_and_validation(api) -> None:
    client, url = api["client"], api["url"]
    resp = await client.get(url, params={"row": 2, "col": 1})
    assert resp.status_code == 200, resp.text
    assert resp.json()["final"]["kind"] == "preset_formula"
    assert (await client.get(url, params={"col": 0})).status_code == 422, "缺行号"
    missing = await client.get(f"/api/disclosure-notes/{api['ids']['p']}/{YEAR}/九、99/cell-sources", params={"row": 0})
    assert missing.status_code == 404 and missing.json()["detail"] == "附注章节不存在"
    api["actor"]["user"] = _Actor(api["ids"]["outsider"])
    assert (await client.get(url, params={"row": 0})).status_code == 403, "非本项目成员不能读"
