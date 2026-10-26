"""前置底稿横幅（spec procedure-chain-hardening-and-java-contracts R9）。

- 各循环前置清单（``prerequisites_for``）与前端 ``usePrerequisiteStatus`` 的回退清单逐项对拍：同一份口径，任一侧改了另一侧打红；
  原先后端只认 E1 / D / F / M，其余循环回空清单 ⇒ 横幅显示「所有前置底稿已完成」。
- ``WpFileStatus`` 每个值都有显式归类（复核通过 = 已完成；原先只认 completed / reviewed / approved）。
- 粗裁掉的前置底稿记不适用、不阻断；删掉的底稿不算。
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.procedure_models import ProcedureInstance
from app.models.workpaper_models import WorkingPaper, WpFileStatus, WpIndex, WpSourceType, WpStatus
from app.routers import wp_prerequisite_status as mod

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TS = Path(__file__).resolve().parents[2] / "audit-platform" / "frontend" / "src" / "composables" / "usePrerequisiteStatus.ts"


def _codes(items: list[dict]) -> list[str]:
    return [i["wp_code"] for i in items]


@pytest.mark.parametrize("wp_code, expected", [
    ("E1", ["B23-2", "C3", "B51-3"]), ("E1-2", ["B23-2", "C3", "B51-3"]), ("e1", ["B23-2", "C3", "B51-3"]),
    ("E10", []), ("D2-1", ["B23-1", "C2", "B51-5"]), ("F2", ["B23-3", "C4", "B51-4"]),
    ("G7-3", ["C5"]), ("H1", ["C6"]), ("H2-5", ["C6", "C7"]), ("H8", ["C6", "C14"]), ("H9-1", ["C6", "C14"]),
    ("I1", ["C8"]), ("I2", ["C8", "C9"]), ("I6-1", ["C8", "C9"]), ("J1", ["C10"]), ("K8", ["C11"]),
    ("L5", ["C13"]), ("M2", []), ("N3", ["C12"]),
    ("A1", []), ("B60", []), ("C5", []), ("S1", []), ("", []), (None, []), ("审计程序", []),
])
def test_prerequisites_for(wp_code, expected):
    assert _codes(mod.prerequisites_for(wp_code)) == expected


def _ts_lists() -> dict[str, list[tuple[str, str]]]:
    src = TS.read_text(encoding="utf-8")
    found = re.findall(r"const (\w+_PREREQUISITES)\b[^=]*=\s*\[(.*?)\]", src, re.S)
    return {name: re.findall(r"wp_code: '([^']+)', wp_name: '([^']+)'", body) for name, body in found}


def _pairs(*wp_codes: str) -> list[tuple[str, str]]:
    seen: list[tuple[str, str]] = []
    for code in wp_codes:
        for p in mod.prerequisites_for(code):
            if (p["wp_code"], p["wp_name"]) not in seen:
                seen.append((p["wp_code"], p["wp_name"]))
    return seen


def test_backend_lists_match_frontend_fallback_lists():
    ts = _ts_lists()
    expected = {
        "E1_PREREQUISITES": ("E1",), "D_CYCLE_PREREQUISITES": ("D2",), "F_CYCLE_PREREQUISITES": ("F2",),
        "G_CYCLE_PREREQUISITES": ("G1",), "H_CYCLE_PREREQUISITES": ("H1", "H2", "H8"),
        "I_CYCLE_PREREQUISITES": ("I1", "I2"), "J_CYCLE_PREREQUISITES": ("J1",), "K_CYCLE_PREREQUISITES": ("K1",),
        "L_CYCLE_PREREQUISITES": ("L1",), "M_CYCLE_PREREQUISITES": ("M1",), "N_CYCLE_PREREQUISITES": ("N1",),
    }
    assert set(ts) == set(expected), f"前端清单变了：{sorted(ts)}"
    for name, probes in expected.items():
        assert ts[name] == _pairs(*probes), f"{name} 与后端 prerequisites_for{probes} 不一致"


def test_every_file_status_is_classified():
    missing = [m.name for m in WpFileStatus if m.value not in mod._FILE_STATUS_STATE]
    assert not missing, f"WpFileStatus 新值没有归类：{missing}"
    assert mod._wp_status_to_state(WpFileStatus.review_passed) == "completed"
    assert mod._wp_status_to_state("review_level2_passed") == "completed"
    assert mod._wp_status_to_state(WpFileStatus.edit_complete) == "in_progress"
    assert mod._wp_status_to_state(None) == "pending"
    assert mod._wp_status_to_state("某个新状态") == "in_progress", "认不出的值不当成已完成"


@pytest.mark.parametrize("states, overall", [
    ([], "ready"), (["not_applicable"], "ready"), (["completed", "not_applicable"], "ready"),
    (["completed", "in_progress"], "partial"), (["pending", "in_progress"], "blocked"),
    (["not_applicable", "pending"], "blocked"),
])
def test_overall(states, overall):
    assert mod.overall_of(states) == overall


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(
            c, tables=[WpIndex.__table__, WorkingPaper.__table__, ProcedureInstance.__table__]))
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


async def _paper(s, pid, code, status=None, *, wp_deleted=False, index_deleted=False):
    wi = WpIndex(id=uuid.uuid4(), project_id=pid, wp_code=code, wp_name=code, audit_cycle=code[0],
                 status=WpStatus.not_started)
    wi.is_deleted = index_deleted
    s.add(wi)
    if status is not None:
        wp = WorkingPaper(id=uuid.uuid4(), project_id=pid, wp_index_id=wi.id, file_path=f"/tmp/{code}.xlsx",
                          source_type=WpSourceType.template, file_version=1, parsed_data={"conclusion": "有效"},
                          status=status)
        wp.is_deleted = wp_deleted
        s.add(wp)
    await s.flush()


@pytest.mark.asyncio
async def test_endpoint_states_from_real_rows(db):
    pid = uuid.uuid4()
    await _paper(db, pid, "C6", WpFileStatus.review_passed)
    await _paper(db, pid, "C7", WpFileStatus.draft, wp_deleted=True)  # 底稿删了 ⇒ 未开始
    await _paper(db, pid, "C14")
    db.add(ProcedureInstance(project_id=pid, audit_cycle="C", procedure_code="C14", procedure_name="租赁循环控制测试",
                             wp_code="C14", status="not_applicable"))
    await _paper(db, pid, "C5", WpFileStatus.edit_complete, index_deleted=True)
    await db.flush()

    h8 = await mod.get_prerequisite_status(str(pid), "H8", db=db)
    assert [(i["wp_code"], i["state"]) for i in h8["items"]] == [("C6", "completed"), ("C14", "not_applicable")]
    assert h8["items"][0]["conclusion"] == "有效"
    assert h8["overall"] == "ready", "复核通过的算完成、裁剪掉的不阻断"
    h2 = await mod.get_prerequisite_status(str(pid), "H2", db=db)
    assert [(i["wp_code"], i["state"]) for i in h2["items"]] == [("C6", "completed"), ("C7", "pending")]
    assert h2["overall"] == "blocked"
    g = await mod.get_prerequisite_status(str(pid), "G1", db=db)
    assert (g["items"][0]["state"], g["overall"]) == ("pending", "blocked"), "删掉的底稿索引不算"
    a = await mod.get_prerequisite_status(str(pid), "A1", db=db)
    assert (a["items"], a["overall"]) == ([], "ready")
