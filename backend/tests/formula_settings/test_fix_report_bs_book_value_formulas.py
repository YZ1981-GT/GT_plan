"""报表 BS-028 / BS-032 / BS-037 全局发布脚本（spec formula-fetch-followup-defect-closure R6.4）。

SQLite 真 ORM + 真公式同步内核（preview_global / publish_global）：预览不写库；发布四个准则、来源 seed、版本 +1；
跟随全局的项目副本随之更新、本项目改过的行进待确认；重跑不再发布；行名不符即中止；发布前必须留底；
发布后对有效定义变化的项目按审计年度传播。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

import app.core.database as database
from app.models.formula_setting_models import FormulaPublish
from app.models.report_models import ReportConfig
from app.services.formula_settings import propagation

from ._env import add_global_row, add_project, add_project_row, make_db, pending_items, project_rows

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "fix" / "fix_report_bs_book_value_formulas.py"
_OLD = {
    "BS-028": "TB('1601','期末余额') - TB('1602','期末余额')",
    "BS-032": "TB('1701','期末余额') - TB('1702','期末余额')",
    "BS-037": "TB('1911','期末余额')",
}
_NAMES = {"BS-028": "固定资产", "BS-032": "无形资产", "BS-037": "其他非流动资产"}
#: 判据独立于脚本常量（防「改了脚本目标值、测试拿脚本自己的值比」的空转）
_NEW = {
    "BS-028": "TB('1601','期末余额') - TB('1602','期末余额') - TB('1603','期末余额') + TB('1606','期末余额')",
    "BS-032": "TB('1701','期末余额') - TB('1702','期末余额') - TB('1703','期末余额')",
    "BS-037": None,
}
_MINE = "TB('1601','期末余额')"  # 某上市项目自己改过的固定资产公式


def _load():
    spec = importlib.util.spec_from_file_location("_fix_report_bs_book_value", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class _Engine:
    async def dispose(self):
        return None


@pytest.fixture
async def world(monkeypatch):
    mod = _load()
    async with make_db() as factory:
        async with factory() as db:
            for std in mod.STANDARDS:
                for n, code in enumerate(("BS-028", "BS-032", "BS-037"), start=28):
                    await add_global_row(db, code, _OLD[code], standard=std, row_number=n, row_name=_NAMES[code])
            inherit = await add_project(db, "A国企继承")
            follow = await add_project(db, "B国企跟随副本")
            mine = await add_project(db, "C上市改过", template_type="listed")
            for code in _OLD:
                await add_project_row(db, follow, code, _OLD[code], base_formula=_OLD[code])
            await add_project_row(db, mine, "BS-028", _MINE, base_formula=_OLD["BS-028"])
            await db.commit()
        calls: list[tuple] = []

        async def fake_propagate(pid, year, slot_keys):
            calls.append((pid, year, sorted(slot_keys)))
            return {"marked": 0, "recalculated": None}

        async def fake_backup(path):
            calls.append(("backup", path))

        monkeypatch.setattr(database, "async_session", factory)
        monkeypatch.setattr(database, "engine", _Engine())
        monkeypatch.setattr(propagation, "propagate_report", fake_propagate)
        monkeypatch.setattr(mod, "backup", fake_backup)
        yield mod, factory, calls, {"inherit": inherit, "follow": follow, "mine": mine}


async def _globals(factory) -> dict[tuple[str, str], ReportConfig]:
    async with factory() as db:
        rows = (await db.execute(sa.select(ReportConfig).where(
            ReportConfig.applicable_standard.notlike("project:%")))).scalars().all()
    return {(r.applicable_standard, r.row_code): r for r in rows}


async def test_preview_writes_nothing(world):
    mod, factory, calls, _ = world
    assert await mod.main(False) == 0
    rows = await _globals(factory)
    assert {(r.formula, r.formula_version) for r in rows.values()} == {(_OLD[c], 1) for (_s, c) in rows}
    async with factory() as db:
        assert await db.scalar(sa.select(sa.func.count()).select_from(FormulaPublish)) == 0
    assert calls == []


async def test_apply_requires_backup(world):
    mod, factory, calls, _ = world
    with pytest.raises(SystemExit, match="--backup"):
        await mod.main(True, None)
    assert calls == [] and {r.formula_version for r in (await _globals(factory)).values()} == {1}


async def test_apply_publishes_four_standards_follows_copies_and_is_idempotent(world, tmp_path):
    mod, factory, calls, p = world
    assert await mod.main(True, tmp_path / "b.json") == 0
    rows = await _globals(factory)
    assert set(mod.STANDARDS) == {"soe_consolidated", "soe_standalone", "listed_consolidated", "listed_standalone"}
    for std in mod.STANDARDS:
        for code, formula in _NEW.items():
            row = rows[(std, code)]
            assert (row.formula, row.formula_version) == (formula, 2), (std, code)
            assert row.formula_description == mod.TARGETS[f"balance_sheet:{code}"][1]["formula_description"]
    async with factory() as db:
        pubs = (await db.execute(sa.select(FormulaPublish))).scalars().all()
        follow, mine = await project_rows(db, p["follow"]), await project_rows(db, p["mine"])
        pending = await pending_items(db, p["mine"])
    assert sorted((x.scope, x.source, x.request_id) for x in pubs) == sorted(
        (std, "seed", mod.request_id(std)) for std in mod.STANDARDS)
    # 跟随全局的副本随之更新（BS-037 也置空）；改过的行不覆盖、进待确认
    assert {c: r.formula for c, r in follow.items()} == _NEW
    assert mine["BS-028"].formula == _MINE and [i.slot_key for i in pending] == ["balance_sheet:BS-028"]
    # 留底先于发布；有效定义变化的项目按审计年度传播（改过的那一格不算变化）
    assert calls[0][0] == "backup"
    slots = sorted(mod.TARGETS)
    assert sorted(calls[1:]) == sorted([(p["inherit"], 2025, slots), (p["follow"], 2025, slots),
                                        (p["mine"], 2025, ["balance_sheet:BS-032", "balance_sheet:BS-037"])])
    # 重跑：定义已是目标值 ⇒ 不留底、不发布、不传播
    calls.clear()
    assert await mod.main(True, tmp_path / "b2.json") == 0
    async with factory() as db:
        assert await db.scalar(sa.select(sa.func.count()).select_from(FormulaPublish)) == 4
    assert calls == []
    assert {r.formula_version for r in (await _globals(factory)).values()} == {2}


async def test_row_name_drift_aborts_before_any_write(world):
    """第四个准则的行名漂移：先全部校验再发布 ⇒ 四个准则一个都不发布、不留底。"""
    mod, factory, calls, _ = world
    async with factory() as db:
        await db.execute(sa.update(ReportConfig).where(
            ReportConfig.applicable_standard == "listed_standalone", ReportConfig.row_code == "BS-037",
        ).values(row_name="商誉"))
        await db.commit()
    with pytest.raises(SystemExit, match="行名"):
        await mod.main(True, Path("unused.json"))
    assert {r.formula_version for r in (await _globals(factory)).values()} == {1}
    async with factory() as db:
        assert await db.scalar(sa.select(sa.func.count()).select_from(FormulaPublish)) == 0
    assert calls == []


def test_backup_keeps_row_to_json_originals_on_real_postgres(tmp_path):
    """留底只读：真库三个公式位在各准则 / 项目层的 report_config 原文 + 资产负债表 financial_report 原文。"""
    import asyncio
    import json

    from tests._pg_shared_engine import run_and_dispose

    if database.engine.dialect.name != "postgresql":
        pytest.skip("留底用 PG row_to_json，需要 PostgreSQL")
    mod = _load()
    path = tmp_path / "backup.json"
    asyncio.run(run_and_dispose(mod.backup(path)))
    data = json.loads(path.read_text(encoding="utf-8"))
    codes = {r["row_code"] for r in data["report_config"]}
    assert codes == {"BS-028", "BS-032", "BS-037"}
    assert {r["applicable_standard"] for r in data["report_config"]} >= set(mod.STANDARDS)
    assert all({"formula", "formula_version", "applicable_standard"} <= set(r) for r in data["report_config"])
    assert all(r["report_type"] == "balance_sheet" for r in data["financial_report"])
