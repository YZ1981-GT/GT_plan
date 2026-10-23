"""合并附注已保存数据随章节号重对齐迁移（``scripts/migrate/remap_consol_note_section_ids.py``，R7.6 / design §16.6）。

真实 SQLite 全表 + 真实对照文件 ``consol_note_section_realign_r7.json``：链式改号不撞唯一索引、并掉的重复条目留有数的那行、
种子公式删（ensure_seeded 重种）而人工公式 / 人工删除记录随迁、公式位前缀改号、上市项目只用上市对照、
演练只读、迁完再算无动作、备份可原样恢复、公式模板里有引用就拒绝执行。
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import tests.conftest  # noqa: F401  注册全部模型与 SQLite 方言补丁
from app.models.base import Base
from app.models.consol_note_data_models import ConsolNoteData
from app.models.consol_push_models import ConsolNoteFormula
from app.models.core import Project
from app.models.formula_setting_models import FormulaSetting, FormulaTemplate
from scripts.migrate import remap_consol_note_section_ids as R

Y = 2025
NODE = "G:consol"


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def projects(db) -> dict[str, Project]:
    out = {k: Project(id=uuid.uuid4(), name=f"【测试】{k}", client_name=f"【测试】{k}", report_scope="consolidated",
                      audit_year=Y, audit_period_end=date(Y, 12, 31)) for k in ("soe", "listed")}
    db.add_all(out.values())
    await db.flush()
    return out


def _std(projects):
    by = {p.id: std for std, p in projects.items()}

    async def resolve(_db, pid):
        return by.get(pid)
    return resolve


def _data(project, sid, label, amount="", node=NODE, n=None):
    return ConsolNoteData(id=uuid.UUID(int=n) if n else uuid.uuid4(), project_id=project.id, year=Y, section_id=sid,
                          node_key=node, data={"headers": ["项目", "期末余额"], "rows": [[label, amount]]})


async def _state(db) -> dict:
    rows = (await db.execute(sa.select(ConsolNoteData))).scalars().all()
    formulas = (await db.execute(sa.select(ConsolNoteFormula))).scalars().all()
    settings = (await db.execute(sa.select(FormulaSetting))).scalars().all()
    return {
        "data": sorted((str(r.project_id), r.section_id, r.node_key, r.data["rows"][0][0], r.data["rows"][0][1]) for r in rows),
        "formula": sorted((f.section_id, f.row_index, f.col_index, f.formula, f.source, f.is_deleted) for f in formulas),
        "setting": sorted((s.layer, s.scope, s.slot_key, s.slot_label or "") for s in settings),
    }


async def _plan(db, fixtures, only=None):
    return await R.build_plan(db, R.load_record(), projects=only, resolve_std=_std(fixtures))


@pytest.mark.asyncio
async def test_chain_merge_formula_and_slot_remap(db, projects):
    soe, listed = projects["soe"], projects["listed"]
    db.add_all([
        # 链式：五-21-1 → 五-20-1、五-22-1 → 五-21-1、五-23-1 → 五-22-1（同一节点）。主键小的先 UPDATE：
        # 五-23-1 那行先改成 五-22-1 时原 五-22-1 还在 —— 一步改必撞唯一索引
        _data(soe, "五-21-1", "其他非流动金融资产", "1", n=3), _data(soe, "五-22-1", "投资性房地产", "2", n=2),
        _data(soe, "五-23-1", "固定资产", "3", n=1),
        # 并：五-21-2 ← [五-22-2（留下的条目）, 五-21-2]；两行都空 ⇒ 留排在前面的 五-22-2；只有后者有数 ⇒ 留后者
        _data(soe, "五-22-2", "公允价值", ""), _data(soe, "五-21-2", "公允价值", ""),
        _data(soe, "五-22-2", "公允价值", "", node="A:consol"), _data(soe, "五-21-2", "公允价值", "9", node="A:consol"),
        # 上市项目：只按上市对照（并掉 五-71-3），国企章节号不动
        _data(listed, "五-71-3", "处置子公司", "5"), _data(listed, "五-22-1", "固定资产", "6"),
        ConsolNoteFormula(template_type="soe", section_id="五-23-1", row_index=2, col_index=3,
                          formula="REPORT('BS-028')", source="seed"),
        ConsolNoteFormula(template_type="soe", section_id="五-23-1", row_index=1, col_index=1,
                          formula="TB('1601','期末余额')", source="manual"),
        ConsolNoteFormula(template_type="soe", section_id="五-22-1", row_index=1, col_index=1,
                          formula="TB('1521','期末余额')", source="seed", is_deleted=True),
        FormulaSetting(domain="consol_note", layer="global", scope="soe", slot_key="五-23-1|1|1", slot_label="五-23-1|1|1"),
        FormulaSetting(domain="consol_note", layer="project", project_id=soe.id, slot_key="五-22-1|0|1"),
        FormulaSetting(domain="report", layer="global", scope="soe", slot_key="五-22-1|0|1"),
    ])
    await db.flush()
    before = await _state(db)

    actions, notes = await _plan(db, projects)
    assert await _state(db) == before, "演练只读"
    assert not [n for n in notes if n.startswith("BLOCK")]
    kinds = sorted((a.spec, a.kind, a.old, a.new) for a in actions)
    assert ("consol_note_formula", "derived_drop", "五-23-1", None) in kinds
    backup = await R.apply_plan(db, actions)
    await R.mark(db, "apply", None, {"actions": len(actions)})
    await db.commit()

    after = await _state(db)
    sid = {(p, n, label): (s, amount) for p, s, n, label, amount in after["data"]}
    s, li = str(soe.id), str(listed.id)
    assert (sid[(s, NODE, "其他非流动金融资产")], sid[(s, NODE, "投资性房地产")], sid[(s, NODE, "固定资产")]) == (
        ("五-20-1", "1"), ("五-21-1", "2"), ("五-22-1", "3"))
    assert [r for r in after["data"] if r[0] == s and r[1] == "五-21-2"] == [
        (s, "五-21-2", "A:consol", "公允价值", "9"), (s, "五-21-2", NODE, "公允价值", "")]
    assert len([r for r in after["data"] if r[0] == s]) == 5, "两组并掉的各删一行"
    assert sorted((p, s_, a) for p, s_, _n, _l, a in after["data"] if p == li) == [(li, "五-22-1", "6"), (li, "五-79-3", "5")]
    assert after["formula"] == [("五-21-1", 1, 1, "TB('1521','期末余额')", "seed", True),
                                ("五-22-1", 1, 1, "TB('1601','期末余额')", "manual", False)]
    assert after["setting"] == [("global", "soe", "五-22-1|0|1", ""), ("global", "soe", "五-22-1|1|1", "五-22-1|1|1"),
                                ("project", "", "五-21-1|0|1", "")]

    # 新旧号同一区间：迁过的再按对照算会再错一节（五-21-1 的投资性房地产会被挪去 五-20-1），所以按迁移记录跳过
    again, again_notes = await _plan(db, projects)
    assert again == [] and again_notes == ["已全量迁过（logs 有记录），无需再迁"]
    await R.restore(db, {"actions": backup, "projects": None})
    await db.commit()
    assert await _state(db) == before
    redo, _ = await _plan(db, projects)
    assert sorted((a.spec, a.kind, a.old, a.new) for a in redo) == kinds, "恢复后再算与第一次相同"


@pytest.mark.asyncio
async def test_project_marker_skips_only_that_project(db, projects):
    soe, listed = projects["soe"], projects["listed"]
    db.add_all([_data(soe, "五-23-1", "固定资产", "3"), _data(listed, "五-71-3", "处置子公司", "5")])
    await db.flush()
    actions, _ = await _plan(db, projects, only=[soe.id])
    await R.apply_plan(db, actions)
    await R.mark(db, "apply", [soe.id], {})
    await db.commit()
    rest, notes = await _plan(db, projects)
    assert [(a.spec, a.old, a.new) for a in rest] == [("consol_note_data", "五-71-3", "五-79-3")]
    assert f"项目 {soe.id} 已迁过（logs 有记录），跳过" in notes


@pytest.mark.asyncio
async def test_project_filter_and_template_block(db, projects):
    soe = projects["soe"]
    tpl = FormulaTemplate(id=uuid.uuid4(), name="【测试】模板")
    db.add_all([tpl, _data(soe, "五-23-1", "固定资产", "3"),
                ConsolNoteFormula(template_type="soe", section_id="五-23-1", row_index=1, col_index=1,
                                  formula="TB('1601','期末余额')", source="manual")])
    await db.flush()
    db.add(FormulaSetting(domain="consol_note", layer="template", template_id=tpl.id, slot_key="五-23-1|1|1"))
    await db.flush()
    actions, notes = await _plan(db, projects, only=[soe.id])
    assert [(a.spec, a.kind, a.new) for a in actions] == [("consol_note_data", "move", "五-22-1")], "只迁项目级表"
    assert any("consol_note_formula 是模板级的表" in n for n in notes)
    assert any(n.startswith("BLOCK 公式模板里有 1 个") for n in notes), "模板层引用只报告并拒绝执行"


def test_record_maps_each_old_section_once():
    record = R.load_record()
    assert record["soe"]["五-23-1"] == ("五-22-1", 0) and record["soe"]["五-10-5"] == ("五-9-12", 1)
    assert record["listed"]["五-71-3"] == ("五-79-3", 1) and "五-22-1" not in record["listed"]
