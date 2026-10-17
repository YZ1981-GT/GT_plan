"""整年度附注推倒重建（spec disclosure-note-template-word-realignment Phase 6 Task 25~26，design §7）。

真 SQLite + 真 ORM + 真生成链（取数 / 构表打桩，与 test_note_project_realign 同口径）；备份 / 恢复走 PostgreSQL，
由 test_note_project_realign_backup_pg 守护（本模块复用同一个 ``write_backup``）。
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))

import tests.conftest  # noqa: E402,F401  注册全部模型 + SQLite JSONB 兼容
from app.models.base import Base  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.dataset_models import LedgerDataset  # noqa: E402
from app.models.formula_push_models import FormulaPushState  # noqa: E402
from app.models.note_trim_models import NoteSectionInstance  # noqa: E402
from app.models.phase16_models import VersionLineStamp  # noqa: E402
from app.models.report_models import DisclosureNote, FinancialReport, FinancialReportType  # noqa: E402
from app.services.disclosure_engine import DisclosureEngine  # noqa: E402
from app.services.note_project_realign_apply import LOCKS, RealignError, RealignSkipped  # noqa: E402
from app.services.note_project_rebuild import plan_rebuild, rebuild_project  # noqa: E402

YEAR = 2025
EDITOR = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
WIZARD = {"steps": {"basic_info": {"data": {"template_type": "soe", "report_scope": "standalone"}}}}


@pytest_asyncio.fixture
async def db(monkeypatch):
    async def _no_preload(self, _pid, _yr):
        self._prior_notes_cache = {}

    async def _no_table(self, *_a, **_k):
        return None

    monkeypatch.setattr(DisclosureEngine, "_preload_data_for_notes", _no_preload)
    monkeypatch.setattr(DisclosureEngine, "_build_section_table_data", _no_table)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [User.__table__, Project.__table__, DisclosureNote.__table__, FormulaPushState.__table__,
              NoteSectionInstance.__table__, LedgerDataset.__table__, VersionLineStamp.__table__,
              FinancialReport.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
        await conn.run_sync(LOCKS.create)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


async def _seed(db: AsyncSession, *, report_rows: bool = True, deleted_project: bool = False) -> uuid.UUID:
    pid = uuid.uuid4()
    db.add(Project(id=pid, name="和平_2025", client_name="和平", template_type="soe", report_scope="standalone",
                   wizard_state=WIZARD, is_deleted=deleted_project))
    await db.flush()
    stamp = {"updated_by": EDITOR, "updated_at": datetime(2026, 1, 2, tzinfo=timezone.utc)}
    db.add_all([
        DisclosureNote(project_id=pid, year=YEAR, note_section="五、1", section_title="货币资金",
                       text_content="<p>旧位置编号的正文</p>", **stamp),
        DisclosureNote(project_id=pid, year=YEAR, note_section="八、9", section_title="其他应收款", is_deleted=True),
        DisclosureNote(project_id=pid, year=YEAR, note_section="八、自定义", section_title="自定义",
                       parent_section_id="不存在的上级"),
        DisclosureNote(project_id=pid, year=YEAR - 1, note_section="八、1", section_title="上年", text_content="<p>上年</p>"),
        FormulaPushState(project_id=pid, year=YEAR, addr_id="note://五、1/货币资金/合计.end", rule_id="r",
                         domain="note", note_section="五、1", state="auto"),
        FormulaPushState(project_id=pid, year=YEAR, addr_id="E1/E1/E1-x", rule_id="r", domain="workpaper", state="auto"),
    ])
    if report_rows:
        db.add(FinancialReport(project_id=pid, year=YEAR, report_type=list(FinancialReportType)[0], row_code="BS-001"))
    await db.execute(sa.insert(LOCKS).values(id=uuid.uuid4(), project_id=pid, year=YEAR, section_code="五、1"))
    await db.commit()
    return pid


async def _count(db: AsyncSession, table, *where) -> int:
    return (await db.execute(sa.select(sa.func.count()).select_from(table).where(*where))).scalar_one()


@pytest.mark.asyncio
async def test_plan_reports_current_state_without_writing(db: AsyncSession) -> None:
    pid = await _seed(db)
    plan = await plan_rebuild(db, pid, YEAR)
    before = plan["before"]
    assert (before["rows"], before["active"], before["deleted"], before["edited"]) == (3, 2, 1, 1)
    assert set(before["not_in_template"]) == {"五、1", "八、自定义"}
    assert before["orphans"] == ["八、自定义"] and (before["push_states"], before["locks"]) == (1, 1)
    assert plan["prerequisite"]["ok"] is True and plan["templates"] == len(plan["_codes"]) > 100
    await db.rollback()
    assert await _count(db, DisclosureNote.__table__, DisclosureNote.project_id == pid) == 4


@pytest.mark.asyncio
async def test_rebuild_replaces_the_year_with_current_templates(db: AsyncSession) -> None:
    pid = await _seed(db)
    report = await rebuild_project(db, pid, YEAR)
    await db.commit()
    assert report["deleted"] == {"disclosure_notes": 3, "formula_push_state": 1, "note_section_locks": 1}
    after = report["after"]
    assert after["active"] == report["templates"] and after["deleted"] == 0
    assert after["not_in_template"] == [] and after["orphans"] == []
    rows = (await db.execute(sa.select(DisclosureNote).where(
        DisclosureNote.project_id == pid, DisclosureNote.year == YEAR))).scalars().all()
    assert len(rows) == report["templates"]
    # 国企现行第五章是「会计政策、会计估计变更及差错更正」：「五、N」编号本身合法，旧位置的科目附注（五、1 货币资金）不能再在
    assert ("五、1", "货币资金") not in {(r.note_section, r.section_title) for r in rows}
    assert {r.note_section for r in rows if r.section_title == "货币资金"} == {"八、1"}
    assert all(r.updated_by is None for r in rows), "重建是系统生成，不算任何人的编辑"
    fps = FormulaPushState.__table__
    assert await _count(db, fps, fps.c.project_id == pid, fps.c.domain == "workpaper") == 1, "底稿推送状态不该被删"
    assert await _count(db, DisclosureNote.__table__, DisclosureNote.year == YEAR - 1) == 1, "别的年度不动"


@pytest.mark.asyncio
async def test_missing_reports_refuses_before_deleting(db: AsyncSession) -> None:
    pid = await _seed(db, report_rows=False)
    with pytest.raises(RealignError, match="前置条件"):
        await rebuild_project(db, pid, YEAR)
    await db.rollback()
    assert await _count(db, DisclosureNote.__table__, DisclosureNote.project_id == pid, DisclosureNote.year == YEAR) == 3


@pytest.mark.asyncio
async def test_deleted_project_is_skipped(db: AsyncSession) -> None:
    pid = await _seed(db, deleted_project=True)
    with pytest.raises(RealignSkipped):
        await rebuild_project(db, pid, YEAR)


@pytest.mark.asyncio
async def test_generation_shortfall_raises_so_caller_rolls_back(db: AsyncSession, monkeypatch) -> None:
    """生成少了任何一节（strict 下取数失败会直接抛；这里模拟静默少生成）⇒ 校验报错，调用方回滚，旧数据原样。"""
    pid = await _seed(db)
    real = DisclosureEngine.generate_notes

    async def _short(self, project_id, year, template_type="soe", **kw):
        out = await real(self, project_id, year, template_type, **kw)
        await self.db.execute(sa.delete(DisclosureNote.__table__).where(DisclosureNote.note_section == out[-1]["note_section"]))
        return out[:-1]

    monkeypatch.setattr(DisclosureEngine, "generate_notes", _short)
    with pytest.raises(RealignError, match="缺"):
        await rebuild_project(db, pid, YEAR)
    await db.rollback()
    left = (await db.execute(sa.select(DisclosureNote.note_section).where(
        DisclosureNote.project_id == pid, DisclosureNote.year == YEAR))).scalars().all()
    assert sorted(left) == ["五、1", "八、9", "八、自定义"]
