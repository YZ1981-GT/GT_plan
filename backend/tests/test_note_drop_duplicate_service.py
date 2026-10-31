"""重复附注行软删服务：四门、原子拒绝、只备份附注域（spec 49 Phase 8 Task 33）。"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册 SQLite JSONB 兼容
from app.models.base import Base, ProjectStatus
from app.models.core import Project
from app.models.report_models import DisclosureNote
from app.services import note_project_realign_apply as svc
from app.services.disclosure_engine import DisclosureEngine

YEAR = 2025


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[tuple[AsyncSession, uuid.UUID], None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[Project.__table__, DisclosureNote.__table__]))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    pid = uuid.uuid4()
    async with factory() as session:
        session.add(Project(
            id=pid, name="【测试】重复附注", client_name="测试公司", template_type="soe",
            report_scope="standalone", status=ProjectStatus.execution,
        ))
        await session.commit()
    async with factory() as session:
        yield session, pid
    await engine.dispose()


def _table(*, value=0, standard="listed_standalone") -> dict:
    return {
        "_source": "workpaper",
        "_current_standard": standard,
        "name": "应收账款",
        "headers": ["项目", "期末余额"],
        "rows": [{"label": "合计", "values": [value], "is_total": True, "ratio": 100}],
    }


async def _seed(session: AsyncSession, pid: uuid.UUID, *, second_text: str | None = None) -> tuple[uuid.UUID, uuid.UUID]:
    old_id, live_id = uuid.uuid4(), uuid.uuid4()
    session.add_all([
        DisclosureNote(
            id=old_id, project_id=pid, year=YEAR, note_section="五、5", section_title="应收账款",
            section_id="legacy-listed-ar", table_data=_table(), text_content=second_text,
        ),
        DisclosureNote(
            id=live_id, project_id=pid, year=YEAR, note_section="八、5", section_title="应 收 账 款",
            section_id="soe-ar", table_data={"rows": [{"label": "合计", "values": [9]}]},
        ),
    ])
    await session.commit()
    return old_id, live_id


@pytest.fixture(autouse=True)
def _stubs(monkeypatch: pytest.MonkeyPatch):
    async def _template(self, project_id):
        return "soe"

    async def _backup(db, project_id, year, path, **kwargs):
        assert kwargs.get("include_workpapers", False) is False, "软删不改底稿，不得备份/恢复整个项目底稿条目"
        return {"path": str(path), "counts": {"disclosure_notes": 2}}

    monkeypatch.setattr(DisclosureEngine, "_get_active_template_type", _template)
    monkeypatch.setattr(svc, "seed_index", lambda _std: {"八、5": {"section_number": "八、5"}})
    monkeypatch.setattr(svc, "write_backup", _backup)


@pytest.mark.asyncio
async def test_apply_soft_deletes_only_legacy_empty_duplicate(db, tmp_path):
    session, pid = db
    old_id, live_id = await _seed(session, pid)
    dry = await svc.drop_duplicate_sections(session, pid, YEAR, ["五、5"], apply=False)
    assert dry["droppable_count"] == 1 and dry["blocked"] == []

    result = await svc.drop_duplicate_sections(
        session, pid, YEAR, ["五、5"], apply=True, backup_dir=tmp_path, stamp="test",
    )
    await session.commit()
    assert result["dropped"] == ["五、5"]
    assert (await session.get(DisclosureNote, old_id)).is_deleted is True
    assert (await session.get(DisclosureNote, live_id)).is_deleted is False


@pytest.mark.asyncio
async def test_text_or_business_value_blocks_delete_and_whole_request_is_atomic(db, tmp_path):
    session, pid = db
    old_id, _ = await _seed(session, pid, second_text="<p>审计师填写的说明</p>")
    session.add_all([
        DisclosureNote(
            id=uuid.uuid4(), project_id=pid, year=YEAR, note_section="五、15", section_title="其他债权投资",
            section_id="legacy-listed-debt", table_data=_table(value=100),
        ),
        DisclosureNote(
            id=uuid.uuid4(), project_id=pid, year=YEAR, note_section="八、16", section_title="其他债权投资",
            section_id="soe-debt", table_data={"rows": []},
        ),
    ])
    await session.commit()

    with pytest.raises(svc.RealignError, match="blocked"):
        await svc.drop_duplicate_sections(
            session, pid, YEAR, ["五、5", "五、15"], apply=True, backup_dir=tmp_path, stamp="test",
        )
    await session.rollback()
    assert (await session.get(DisclosureNote, old_id)).is_deleted is False


@pytest.mark.asyncio
async def test_active_duplicate_section_code_is_rejected_by_database(db):
    """现行唯一索引先拦活动重复码；service 的 ambiguous 分支只防迁移漂移 / 旧 schema。"""
    session, pid = db
    await _seed(session, pid)
    session.add(DisclosureNote(
        id=uuid.uuid4(), project_id=pid, year=YEAR, note_section="五、5", section_title="应收账款",
        section_id="legacy-listed-ar-2", table_data=_table(),
    ))
    with pytest.raises(sa.exc.IntegrityError):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_text_content_alone_blocks_delete(db, tmp_path):
    """只因人工正文而不安全的单一候选必须拒绝，不能被同批其他候选挡住断言。"""
    session, pid = db
    old_id, _ = await _seed(session, pid, second_text="<p>人工说明不能丢</p>")
    with pytest.raises(svc.RealignError, match="blocked"):
        await svc.drop_duplicate_sections(
            session, pid, YEAR, ["五、5"], apply=True, backup_dir=tmp_path, stamp="test",
        )
    await session.rollback()
    assert (await session.get(DisclosureNote, old_id)).is_deleted is False


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["manual_zero", "locked_zero", "top_override", "sub_override", "orphan"])
async def test_protected_empty_looking_payload_blocks_delete(db, tmp_path, monkeypatch, kind):
    session, pid = db
    old_id, _ = await _seed(session, pid)
    old = await session.get(DisclosureNote, old_id)
    td = _table()
    if kind in {"manual_zero", "locked_zero"}:
        td["rows"][0]["_cell_modes"] = {"0": kind.removesuffix("_zero")}
    elif kind == "top_override":
        td["_manual_override"] = True
    elif kind == "sub_override":
        td["sub_table_data"] = {"_manual_override": True}
    else:
        td["_realign_orphans"] = [{"table": "旧表", "label": "A", "values": [0]}]
    old.table_data = td
    await session.commit()

    dry = await svc.drop_duplicate_sections(session, pid, YEAR, ["五、5"], apply=False)
    candidate = dry["candidates"]["五、5"]
    assert candidate["droppable"] is False
    assert candidate["gates"]["无正文指引和业务实值"] is False

    async def unexpected_backup(*args, **kwargs):
        raise AssertionError("安全门未通过时不得先写备份")

    monkeypatch.setattr(svc, "write_backup", unexpected_backup)
    with pytest.raises(svc.RealignError, match="blocked"):
        await svc.drop_duplicate_sections(
            session, pid, YEAR, ["五、5"], apply=True, backup_dir=tmp_path, stamp="test",
        )
    await session.rollback()
    assert (await session.get(DisclosureNote, old_id)).is_deleted is False
