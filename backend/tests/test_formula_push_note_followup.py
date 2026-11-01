"""推送后自动运算附注公式与推送拥有格（spec note-table-structure-formula-pull-closure R4）。SQLite 内存库 + 真 ORM。

判据：①推送提交后对写入的附注章节执行附注公式并落库（合计随推送写入的明细更新）②dry_run / 没写附注不做事 ③存储表上
推送拥有的格（推送状态 auto、当前值 = 推送值）不被预设公式改写、回 kept_push，用户公式照常覆盖 ④推送状态反解到存储表格
⑤来源诊断的推送步骤写明取数口径 ⑥四个推送调用方都接线、刷新链路不重复接。
"""
from __future__ import annotations

import ast
import copy
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite JSONB 兼容
from app.models.base import Base, ProjectStatus
from app.models.core import Project, User
from app.models.report_models import ContentType, DisclosureNote

YEAR = 2025
SECTION = "八、5"
AGING_NAME = "（1）按账龄披露应收账款"
APP = Path(__file__).resolve().parents[1] / "app"


def _aging(total=None):
    return {"name": AGING_NAME, "headers": ["账 龄", "期末数", "期初数"],
            "rows": [{"label": "1年以内（含1年）", "values": [800.0, 600.0]}, {"label": "1至2年", "values": [200.0, 50.0]},
                     {"label": "合 计", "values": [total, None], "is_total": True, "row_type": "total"}]}


def _td(table):
    return {"headers": list(table["headers"]), "rows": copy.deepcopy(table["rows"]), "_tables": [copy.deepcopy(table)]}


@pytest_asyncio.fixture
async def env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(
            c, tables=[User.__table__, Project.__table__, DisclosureNote.__table__]))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    pid = uuid.uuid4()
    async with factory() as s:
        s.add(Project(id=pid, name="甲_2025", client_name="甲公司", template_type="soe",
                      report_scope="standalone", status=ProjectStatus.execution))
        await s.commit()

    async def add(table_data):
        async with factory() as s:
            s.add(DisclosureNote(project_id=pid, year=YEAR, note_section=SECTION, section_title="应收账款",
                                 content_type=ContentType.table, table_data=table_data))
            await s.commit()

    async def stored():
        async with factory() as s:
            return (await s.execute(sa.select(DisclosureNote.table_data).where(
                DisclosureNote.project_id == pid, DisclosureNote.note_section == SECTION))).scalar_one()

    yield SimpleNamespace(pid=pid, factory=factory, add=add, stored=stored)
    await engine.dispose()


def _result(pid, *, sections=(SECTION,), dry_run=False, run_id="r1"):
    return SimpleNamespace(project_id=pid, year=YEAR, note_sections=list(sections), dry_run=dry_run, run_id=run_id)


async def test_recalc_after_push_writes_totals_and_commits(env):
    from app.services.formula_push.note_followup import recalc_pushed_notes

    await env.add(_td(_aging()))
    async with env.factory() as s:
        runs = await recalc_pushed_notes(s, _result(env.pid))
    assert runs[SECTION]["updated"] == 2 and runs[SECTION]["error"] is None
    td = await env.stored()
    assert td["_tables"][0]["rows"][2]["values"] == [1000.0, 650.0], "提交后另开会话读到：合计 = 明细之和"


@pytest.mark.parametrize("kw", [{"dry_run": True}, {"run_id": None}, {"sections": ()}])
async def test_recalc_does_nothing_without_a_committed_note_write(env, kw):
    from app.services.formula_push.note_followup import recalc_pushed_notes

    await env.add(_td(_aging()))
    async with env.factory() as s:
        assert await recalc_pushed_notes(s, _result(env.pid, **kw)) == {}
    assert (await env.stored())["_tables"][0]["rows"][2]["values"] == [None, None]


async def test_push_owned_total_is_kept_but_user_formula_overrides(env, monkeypatch):
    from app.services import note_formula_push_guard
    from app.services.note_formula_generator import execute_note_formulas

    async def owned(*_a, **_k):
        return {(0, 2, 0)}  # 合计行期末数由推送按审定数写入

    monkeypatch.setattr(note_formula_push_guard, "push_owned_cells", owned)
    await env.add(_td(_aging(total=999.0)))
    async with env.factory() as s:
        res = await execute_note_formulas(s, env.pid, YEAR, SECTION)
        await s.commit()
    kept = [r for r in res["results"] if r["cell"] == "2:0"]
    assert kept and kept[0]["status"] == "kept_push"
    assert (await env.stored())["_tables"][0]["rows"][2]["values"] == [999.0, 650.0], "推送值保留，另一列照算"

    td = await env.stored()
    td["_user_formulas"] = [{"target": "2:0", "formula": "cell(0,0) + cell(1,0)", "category": "auto_calc"}]
    async with env.factory() as s:
        note = (await s.execute(sa.select(DisclosureNote).where(DisclosureNote.project_id == env.pid))).scalar_one()
        note.table_data = td
        await s.commit()
        await execute_note_formulas(s, env.pid, YEAR, SECTION)
        await s.commit()
    assert (await env.stored())["_tables"][0]["rows"][2]["values"][0] == 1000.0, "用户公式照常覆盖"


async def test_push_owned_cells_maps_push_state_to_stored_cell(monkeypatch):
    from app.services import note_push_ownership
    from app.services.formula_settings import push_settings
    from app.services.note_formula_push_guard import push_owned_cells

    state = SimpleNamespace(addr_id=f"note://{SECTION}/{AGING_NAME}/合计.end", rule_id="D2.note.main",
                            last_pushed_value=999.0)
    rule = SimpleNamespace(rule_id="D2.note.main", status="active", target=SimpleNamespace(fields=("end_amount", "prior_amount")))

    async def states(*_a, **_k):
        return [state]

    async def rules(*_a, **_k):
        return [rule], []

    monkeypatch.setattr(note_push_ownership, "_owned_states", states)
    monkeypatch.setattr(push_settings, "effective_push_rules", rules)
    td = _td(_aging(total=999.0))
    assert await push_owned_cells(None, project_id=uuid.uuid4(), year=YEAR, section=SECTION, td=td, view=td) == {(0, 2, 0)}
    td["_tables"][0]["rows"][2]["values"][0] = 5.0  # 推送后被改写过 ⇒ 不再归推送
    assert await push_owned_cells(None, project_id=uuid.uuid4(), year=YEAR, section=SECTION, td=td, view=td) == set()
    assert await push_owned_cells(None, project_id=uuid.uuid4(), year=YEAR, section=SECTION, td=td, view={}) == set(), \
        "底稿投影视图不在这里判"
    rule.status = "disabled"
    td["_tables"][0]["rows"][2]["values"][0] = 999.0
    assert await push_owned_cells(None, project_id=uuid.uuid4(), year=YEAR, section=SECTION, td=td, view=td) == set(), \
        "停用 / 已删除的规则不再拥有这一格"


def test_cell_source_push_step_names_the_tb_formula():
    from app.services.note_cell_sources import _decide

    push = {"rule_id": "D2.note.main", "wp_code": "D2", "rule_status": "active", "last_pushed_value": 1000.0,
            "state": "auto", "ambiguous": False, "matches_current": True,
            "source_formula": "期末 = TB('1122','期末余额')"}
    final, steps, _conflicts = _decide(mode="auto", projected=False, value=1000.0, formula=None, binding=None,
                                       pushes=[push], section_locked=False, sync={})
    assert final["kind"] == "push" and "TB('1122','期末余额')" in final["detail"]
    assert any("TB('1122','期末余额')" in s["detail"] for s in steps if s["kind"] == "push")


def _calls(path: Path, name: str) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sum(1 for n in ast.walk(tree) if isinstance(n, ast.Call)
               and getattr(n.func, "id", getattr(n.func, "attr", None)) == name)


@pytest.mark.parametrize("rel", ["services/formula_push/triggers.py", "services/formula_settings/propagation.py",
                                 "services/formula_push/panel.py", "routers/formula_push.py"])
def test_every_push_caller_recalculates_note_formulas(rel):
    assert _calls(APP / rel, "run_and_commit") >= 1 and _calls(APP / rel, "recalc_pushed_notes") >= 1, rel


def test_refresh_path_does_not_recalculate_twice():
    """刷新链路在 refill 之后自己最后执行公式（ADR-3），不接推送后自动运算。"""
    path = APP / "services/note_workpaper_pull_service.py"
    assert _calls(path, "run_and_commit") >= 1 and _calls(path, "recalc_pushed_notes") == 0
