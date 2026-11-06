"""附注章节原子写入内核单测（SQLite）。

本地闭环：不读 PG、不走真实 ``pg_advisory_xact_lock``；只验 ``mutate_note_section``
的四件事：

  1. 不存在的章节 → 返回 ``None``
  2. mutator 改 workspace → ``changed=True`` + ``table_data`` 落到 DB，且
     workspace 是 deepcopy（外部修改不污染内核内部 workspace）
  3. mutator 不改 workspace → ``changed=False``、无 UPDATE flush、hash 相同
  4. mutator 直接改 ``note.text_content``（非 ``table_data`` 字段）→ ``changed``
     只看 ``table_data``；但 flush 后 ``text_content`` 已经 attached

真实 PG advisory lock 的并发 barrier 在 ``[ ]*`` 之下，需要专用 PG。
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import tests.conftest  # noqa: F401  注册全部模型与 SQLite 方言补丁
from app.models.base import Base
from app.models.core import Project
from app.models.report_models import DisclosureNote
from app.services.disclosure.note_section_write_kernel import (
    mutate_note_section,
    stable_hash,
)


_YEAR = 2025
_SECTION = "note-section-五-1"


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db(factory) -> AsyncSession:
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def project(db: AsyncSession) -> Project:
    p = Project(
        id=uuid.uuid4(),
        name="测试项目_2025",
        client_name="测试项目",
        company_code="T",
        parent_company_code=None,
        ultimate_company_code="T",
        relation_to_parent=None,
        report_scope="standalone",
    )
    db.add(p)
    await db.flush()
    return p


async def _seed_note(db: AsyncSession, project_id: uuid.UUID, *, table_data: dict | None = None) -> DisclosureNote:
    note = DisclosureNote(
        id=uuid.uuid4(),
        project_id=project_id,
        year=_YEAR,
        note_section=_SECTION,
        section_title="货币资金",
        content_type=None,
        table_data=table_data if table_data is not None else {"_tables": {}},
        text_content="",
    )
    db.add(note)
    await db.flush()
    return note


@pytest.mark.asyncio
async def test_mutate_returns_none_when_section_missing(db, project):
    result = await mutate_note_section(
        db,
        project_id=project.id,
        year=_YEAR,
        section_id="not-exists",
        mutator=lambda note, ws: None,
    )
    assert result is None


@pytest.mark.asyncio
async def test_mutate_writes_changes_once_and_updates_table_data(db, project):
    seeded = await _seed_note(db, project.id, table_data={"_tables": {"table_a": {"rows": []}}})
    captured_workspace: dict[str, dict] = {}

    def _mutator(note, ws):
        captured_workspace["ref"] = ws
        ws["_tables"]["table_a"]["rows"].append({"name": "A", "value": 1})

    result = await mutate_note_section(
        db,
        project_id=project.id,
        year=_YEAR,
        section_id=_SECTION,
        mutator=_mutator,
    )
    assert result is not None
    assert result.note_id == seeded.id
    assert result.changed is True
    assert result.before_hash != result.after_hash

    # 刷新后 DB 侧应落到新内容
    await db.refresh(seeded)
    assert seeded.table_data["_tables"]["table_a"]["rows"] == [{"name": "A", "value": 1}]

    # workspace 是 deepcopy：事后修改它不应污染 note.table_data 的内存引用
    captured_workspace["ref"]["_tables"]["table_a"]["rows"].append({"name": "B"})
    assert seeded.table_data["_tables"]["table_a"]["rows"] == [{"name": "A", "value": 1}]


@pytest.mark.asyncio
async def test_mutate_nop_when_workspace_unchanged(db, project):
    seeded = await _seed_note(db, project.id, table_data={"_tables": {"table_a": {"rows": [{"name": "A"}]}}})
    before_updated_at = seeded.updated_at if hasattr(seeded, "updated_at") else None

    def _mutator(note, ws):
        # 读 workspace 但不改
        _ = ws["_tables"]["table_a"]["rows"][0]

    result = await mutate_note_section(
        db,
        project_id=project.id,
        year=_YEAR,
        section_id=_SECTION,
        mutator=_mutator,
    )
    assert result is not None
    assert result.changed is False
    assert result.before_hash == result.after_hash

    await db.refresh(seeded)
    assert seeded.table_data == {"_tables": {"table_a": {"rows": [{"name": "A"}]}}}
    # updated_at 未被 flag_modified 触发（SQLite 无 server_default on_update，所以直接看等值）
    if before_updated_at is not None:
        assert seeded.updated_at == before_updated_at


@pytest.mark.asyncio
async def test_mutate_lets_mutator_write_non_table_data_fields(db, project):
    seeded = await _seed_note(db, project.id, table_data={"_tables": {}})

    def _mutator(note, ws):
        note.text_content = "手工文字"

    result = await mutate_note_section(
        db,
        project_id=project.id,
        year=_YEAR,
        section_id=_SECTION,
        mutator=_mutator,
    )
    assert result is not None
    # changed 只看 table_data 变化；text_content 由 mutator 直接写 note
    assert result.changed is False
    await db.refresh(seeded)
    assert seeded.text_content == "手工文字"


@pytest.mark.asyncio
async def test_mutate_isolates_workspace_from_original_table_data(db, project):
    original = {"_tables": {"table_a": {"rows": [{"name": "A"}]}}}
    seeded = await _seed_note(db, project.id, table_data=original)

    def _mutator(note, ws):
        ws["_tables"]["table_a"]["rows"].append({"name": "B"})

    await mutate_note_section(
        db,
        project_id=project.id,
        year=_YEAR,
        section_id=_SECTION,
        mutator=_mutator,
    )
    await db.refresh(seeded)

    # 原始 dict 引用不得被 mutator 污染（workspace 是 deepcopy）
    assert original == {"_tables": {"table_a": {"rows": [{"name": "A"}]}}}
    assert seeded.table_data == {"_tables": {"table_a": {"rows": [{"name": "A"}, {"name": "B"}]}}}


def test_stable_hash_is_canonical_and_order_insensitive():
    a = {"z": 1, "a": 2}
    b = {"a": 2, "z": 1}
    assert stable_hash(a) == stable_hash(b)

    # 对不同形状敏感
    assert stable_hash({"a": 1}) != stable_hash({"a": 2})
    assert stable_hash({"a": 1}) != stable_hash({"a": "1"})
    # 非 JSON 可序列化对象走 default=str
    assert isinstance(stable_hash({"d": object()}), str)
