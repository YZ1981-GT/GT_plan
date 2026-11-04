"""规则已不存在的附注推送状态行：判定 / 回执 / 修复脚本（spec note-table-structure-formula-pull-closure R9 / R10）。

判据：①`list_orphans` 只认「rule_id 不在现行规则清单里」的附注域行，域 / 项目 / 年度过滤有效
②`count_orphans` 与 `list_orphans` 同口径 ③面板统计读不到规则清单时不抛（回 0，不让推送回执 500）
④修复脚本删状态行、不改格里的值，并对受影响章节重跑附注公式 ⑤`--apply` 没给 `--confirm` 直接拒绝
⑥变异反证：判定若不过滤规则清单，正常行也会被当孤儿。
"""
from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.models.formula_push_models import FormulaPushState
from app.services.formula_push.orphan_states import count_orphans, known_rule_ids, list_orphans

from ._formula_push_env import make_env

ROOT = Path(__file__).resolve().parents[1]
YEAR = 2025


async def _add_state(env, *, rule_id: str, addr: str, domain: str = "note", section: str | None = "八、5",
                     pushed=1.0, current=1.0, year: int = YEAR, project_id=None) -> None:
    async with env.factory() as db:
        db.add(FormulaPushState(project_id=project_id or env.pid, year=year, addr_id=addr, rule_id=rule_id,
                                domain=domain, note_section=section, last_pushed_value=pushed,
                                current_value=current, state="auto"))
        await db.commit()


@pytest.mark.asyncio
async def test_only_unknown_rule_ids_in_the_note_domain_are_orphans(monkeypatch):
    known = next(iter(sorted(known_rule_ids())))
    async with make_env(monkeypatch) as env:
        await _add_state(env, rule_id=known, addr="note://八、5/表/合计.end")
        await _add_state(env, rule_id="D2.note.subtable_0", addr="note://八、5/表/合计.prior")
        await _add_state(env, rule_id="D2.note.subtable_0", addr="wp://D2/表/合计.end", domain="workpaper",
                         section=None)
        await _add_state(env, rule_id="D2.note.subtable_0", addr="note://八、5/表/合计.y2024", year=2024)

        async with env.factory() as db:
            orphans = await list_orphans(db)
            assert [(o.rule_id, o.addr_id) for o in orphans] == [
                ("D2.note.subtable_0", "note://八、5/表/合计.prior"),
                ("D2.note.subtable_0", "note://八、5/表/合计.y2024"),
            ], "只认附注域；现行规则的行不算；年度不过滤时两年都在"
            assert await count_orphans(db) == 2
            assert [o.year for o in await list_orphans(db, year=YEAR)] == [YEAR]
            assert await count_orphans(db, year=YEAR) == 1
            assert await list_orphans(db, project_id=uuid.uuid4()) == [], "别的项目没有"
            assert all(o.still_pushed_value for o in orphans), "推送值 == 现值 ⇒ 格里的数就是它留下的"


@pytest.mark.asyncio
async def test_changed_cell_is_reported_but_not_marked_as_still_pushed(monkeypatch):
    async with make_env(monkeypatch) as env:
        await _add_state(env, rule_id="D2.note.subtable_0", addr="note://八、5/表/合计.end", pushed=1.0, current=2.0)
        async with env.factory() as db:
            orphans = await list_orphans(db)
        assert len(orphans) == 1 and orphans[0].still_pushed_value is False


@pytest.mark.asyncio
async def test_panel_count_is_zero_when_rule_catalog_cannot_be_read(monkeypatch):
    from app.services.formula_push import orphan_states, panel

    async with make_env(monkeypatch) as env:
        await _add_state(env, rule_id="D2.note.subtable_0", addr="note://八、5/表/合计.end")
        monkeypatch.setattr(orphan_states, "known_rule_ids", lambda: (_ for _ in ()).throw(OSError("规则清单读不到")))
        async with env.factory() as db:
            assert await panel.orphan_state_count(db, project_id=env.pid, year=YEAR) == 0, "读不到清单不抛、不阻断推送"


@pytest.mark.asyncio
async def test_mutation_without_catalog_filter_would_flag_live_rules(monkeypatch):
    """变异反证：判定不按规则清单过滤 ⇒ 现行规则的行也会被当孤儿（判据不是恒空）。"""
    from app.services.formula_push import orphan_states

    known = next(iter(sorted(known_rule_ids())))
    async with make_env(monkeypatch) as env:
        await _add_state(env, rule_id=known, addr="note://八、5/表/合计.end")
        async with env.factory() as db:
            assert await list_orphans(db) == []
            monkeypatch.setattr(orphan_states, "known_rule_ids", set)
            assert len(await list_orphans(db)) == 1


def test_apply_requires_confirm():
    proc = subprocess.run([sys.executable, str(ROOT / "scripts/fix/purge_orphan_push_states.py"), "--apply"],
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          env={"PYTHONIOENCODING": "utf-8", "PATH": "", "SYSTEMROOT": "C:\\Windows"})
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "--confirm" in (proc.stdout or "")


@pytest.mark.asyncio
async def test_purge_deletes_state_rows_and_leaves_cell_values(monkeypatch):
    """修复脚本的内核：删状态行、不动格里的值；受影响章节重跑附注公式。"""
    from app.services.formula_push.orphan_states import list_orphans

    table = {"name": "（1）按账龄披露应收账款", "headers": ["账 龄", "期末数", "期初数"],
             "rows": [{"label": "1年以内", "values": [10.0, 4.0]},
                      {"label": "合 计", "values": [None, None], "is_total": True, "row_type": "total"}]}
    async with make_env(monkeypatch) as env:
        await env.add_note("八、5", {"headers": table["headers"], "rows": table["rows"], "_tables": [table]},
                           title="应收账款")
        await _add_state(env, rule_id="D2.note.subtable_0", addr="note://八、5/（1）按账龄披露应收账款/合  计.end")

        async with env.factory() as db:
            orphans = await list_orphans(db)
            assert len(orphans) == 1
            for o in orphans:
                await db.execute(sa.text(
                    "DELETE FROM formula_push_state WHERE project_id = :pid AND year = :yr AND addr_id = :addr"
                ), {"pid": str(o.project_id), "yr": o.year, "addr": o.addr_id})
            await db.commit()
            assert await list_orphans(db) == []

        # 状态行没了 ⇒ 合计不再算「推送拥有格」，附注公式能把它按本表构成算出来
        from app.services.note_formula_generator import execute_note_formulas

        async with env.factory() as db:
            await execute_note_formulas(db, env.pid, YEAR, "八、5")
            await db.commit()
        note = await env.note("八、5")
        total = note.table_data["_tables"][0]["rows"][1]["values"]
        assert total[0] == 10.0 and total[1] == 4.0, "重算把合计按明细行算出来（原先被孤儿状态挡着）"
