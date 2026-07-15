"""Property-based & unit tests for WorkpaperMutationAdapter.

Tests cover:
- P3: prepare→apply round-trip (after apply, read value == after_value)
- P4: version conflict detection (value changed between prepare and apply → reject)
- P13: project isolation (cross-project target rejected)
- Restore with optimistic version check

Uses SQLite in-memory for unit isolation.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.services.formula_runtime.adapters.workpaper import (
    OwnershipViolation,
    VersionConflict,
    WorkpaperMutationAdapter,
    _cell_read,
    _cell_write,
    _version_from_timestamp,
)
from app.services.formula_runtime.contracts import (
    CanonicalFormulaTarget,
    FormulaMutation,
)


# ─── SQLite compat patches ─────────────────────────────────────────────────────
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"


# ─── Test DB setup ─────────────────────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS working_paper (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    file_path TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft'
);

CREATE TABLE IF NOT EXISTS checklist_responses (
    id TEXT PRIMARY KEY,
    wp_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    conclusion TEXT,
    remark TEXT,
    wp_ref TEXT,
    updated_by TEXT,
    updated_at TEXT,
    project_id TEXT,
    UNIQUE(wp_id, item_id)
);
"""


def _run(coro):
    """Run async coroutine synchronously for Hypothesis compatibility."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _create_test_session():
    """Create an in-memory SQLite session with schema."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        for stmt in SCHEMA_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await conn.execute(text(stmt))

    async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = async_session_factory()
    return session, engine


async def _seed_project_and_wp(
    session: AsyncSession,
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
) -> None:
    """Seed a project and working_paper for testing."""
    await session.execute(
        text("INSERT OR IGNORE INTO projects (id) VALUES (:id)"),
        {"id": str(project_id)},
    )
    await session.execute(
        text(
            "INSERT OR IGNORE INTO working_paper (id, project_id, file_path) "
            "VALUES (:id, :project_id, :file_path)"
        ),
        {"id": str(wp_id), "project_id": str(project_id), "file_path": "/test/path.xlsx"},
    )
    await session.flush()


# ─── Constants ─────────────────────────────────────────────────────────────────

PROJECT_A = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
PROJECT_B = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
WP_A = uuid.UUID("11111111-0000-0000-0000-000000000001")
WP_B = uuid.UUID("22222222-0000-0000-0000-000000000002")


def _make_target(
    project_id: uuid.UUID = PROJECT_A,
    wp_id: uuid.UUID = WP_A,
    item_id: str = "test-item",
    cell: str = ".",
    addr_id: str | None = None,
) -> CanonicalFormulaTarget:
    return CanonicalFormulaTarget(
        domain="workpaper",
        project_id=project_id,
        year=2025,
        addr_id=addr_id or f"{wp_id}/{item_id}/{cell}",
        locator={"wp_id": str(wp_id), "item": item_id, "cell": cell},
        wp_id=wp_id,
    )


# ─── Unit Tests ────────────────────────────────────────────────────────────────


class TestCellReadWrite:
    """Unit tests for _cell_read and _cell_write helpers."""

    def test_read_whole(self):
        assert _cell_read('{"a": 1}', ".") == {"a": 1}

    def test_read_key(self):
        assert _cell_read('{"amount": 100}', "amount") == 100

    def test_read_nested(self):
        assert _cell_read('{"data": {"val": 42}}', "data.val") == 42

    def test_read_none(self):
        assert _cell_read(None, "x") is None

    def test_write_whole(self):
        result = _cell_write(None, ".", {"total": 500})
        assert json.loads(result) == {"total": 500}

    def test_write_key(self):
        result = _cell_write('{"a": 1}', "b", 2)
        assert json.loads(result) == {"a": 1, "b": 2}

    def test_write_nested(self):
        result = _cell_write('{"data": {}}', "data.val", 99)
        assert json.loads(result) == {"data": {"val": 99}}


class TestVersionFromTimestamp:
    def test_none(self):
        assert _version_from_timestamp(None) == "__none__"

    def test_datetime(self):
        dt = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        assert _version_from_timestamp(dt) == dt.isoformat()


# ─── Integration Tests (async) ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_prepare_apply_roundtrip():
    """P3: After apply, read value == after_value.

    **Validates: Requirements 1.1, 3.1**
    """
    session, engine = await _create_test_session()
    try:
        await _seed_project_and_wp(session, PROJECT_A, WP_A)

        adapter = WorkpaperMutationAdapter(session)
        target = _make_target()

        # Prepare: no existing data → before_value is None
        mutations = await adapter.prepare_many(
            [target],
            {target.addr_id: {"result": 12345}},
        )
        assert len(mutations) == 1
        assert mutations[0].before_value is None
        assert mutations[0].after_value == {"result": 12345}

        # Apply
        applied = await adapter.apply_many(mutations)
        assert len(applied) == 1

        # Read back via prepare to verify round-trip
        mutations2 = await adapter.prepare_many([target], {target.addr_id: "ignored"})
        assert mutations2[0].before_value == {"result": 12345}
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_project_isolation():
    """P13: Cross-project target rejected.

    **Validates: Requirements 12.1, 12.4**
    """
    session, engine = await _create_test_session()
    try:
        # WP_A belongs to PROJECT_A
        await _seed_project_and_wp(session, PROJECT_A, WP_A)

        adapter = WorkpaperMutationAdapter(session)
        # Target claims PROJECT_B but WP_A belongs to PROJECT_A
        target = _make_target(project_id=PROJECT_B, wp_id=WP_A)

        with pytest.raises(OwnershipViolation):
            await adapter.prepare_many([target], {target.addr_id: "val"})
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_version_conflict_detection():
    """P4: If value changed between prepare and apply, reject.

    **Validates: Requirements 4.1, 4.4**
    """
    session, engine = await _create_test_session()
    try:
        await _seed_project_and_wp(session, PROJECT_A, WP_A)

        adapter = WorkpaperMutationAdapter(session)
        target = _make_target()

        # Prepare
        mutations = await adapter.prepare_many([target], {target.addr_id: "new_val"})
        assert len(mutations) == 1

        # Simulate external edit: insert a row with different timestamp
        await session.execute(
            text(
                "INSERT INTO checklist_responses (id, wp_id, item_id, remark, updated_at) "
                "VALUES (:id, :wp_id, :item_id, :remark, :updated_at)"
            ),
            {
                "id": str(uuid.uuid4()),
                "wp_id": str(WP_A),
                "item_id": "test-item",
                "remark": '"external_edit"',
                "updated_at": "2099-12-31T23:59:59+00:00",
            },
        )
        await session.flush()

        # Apply should detect version mismatch
        with pytest.raises(VersionConflict):
            await adapter.apply_many(mutations)
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_restore_optimistic_check():
    """Restore with optimistic version check: current must equal after_version from apply.

    **Validates: Requirements 4.2**
    """
    session, engine = await _create_test_session()
    try:
        await _seed_project_and_wp(session, PROJECT_A, WP_A)

        adapter = WorkpaperMutationAdapter(session)
        target = _make_target()

        # Prepare and apply
        mutations = await adapter.prepare_many([target], {target.addr_id: "applied_val"})
        applied = await adapter.apply_many(mutations)
        applied_version = applied[0].applied_version

        # Build restore snapshot: expected_version = applied_version
        restore_mutation = FormulaMutation(
            target=target,
            before_value=None,  # original value
            after_value="applied_val",
            expected_version=applied_version,
            source_formula_id=None,
        )

        # Restore should succeed (no intervening edit)
        restored = await adapter.restore_many([restore_mutation])
        assert len(restored) == 1
        assert restored[0].conflict is False

        # Verify value is restored to before_value (None → whole remark is null-like)
        mutations2 = await adapter.prepare_many([target], {target.addr_id: "x"})
        assert mutations2[0].before_value is None
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_restore_conflict_on_intervening_edit():
    """Restore fails (conflict=True) when value was edited after apply.

    **Validates: Requirements 4.4**
    """
    session, engine = await _create_test_session()
    try:
        await _seed_project_and_wp(session, PROJECT_A, WP_A)

        adapter = WorkpaperMutationAdapter(session)
        target = _make_target()

        # Prepare and apply
        mutations = await adapter.prepare_many([target], {target.addr_id: "first"})
        applied = await adapter.apply_many(mutations)
        applied_version = applied[0].applied_version

        # Simulate intervening edit (different timestamp)
        await session.execute(
            text(
                "UPDATE checklist_responses "
                "SET remark = :remark, updated_at = :updated_at "
                "WHERE wp_id = :wp_id AND item_id = :item_id"
            ),
            {
                "wp_id": str(WP_A),
                "item_id": "test-item",
                "remark": '"user_edited"',
                "updated_at": "2099-01-01T00:00:00+00:00",
            },
        )
        await session.flush()

        # Restore with applied_version → conflict because current != applied_version
        restore_mutation = FormulaMutation(
            target=target,
            before_value=None,
            after_value="first",
            expected_version=applied_version,
            source_formula_id=None,
        )
        restored = await adapter.restore_many([restore_mutation])
        assert len(restored) == 1
        assert restored[0].conflict is True
        assert "expected=" in (restored[0].conflict_detail or "")
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_read_versions():
    """read_versions returns current version strings."""
    session, engine = await _create_test_session()
    try:
        await _seed_project_and_wp(session, PROJECT_A, WP_A)

        adapter = WorkpaperMutationAdapter(session)
        target = _make_target()

        # No row yet → __none__
        versions = await adapter.read_versions([target])
        assert versions[target.addr_id] == "__none__"

        # After apply, version is a timestamp
        mutations = await adapter.prepare_many([target], {target.addr_id: "v"})
        await adapter.apply_many(mutations)
        versions = await adapter.read_versions([target])
        assert versions[target.addr_id] != "__none__"
    finally:
        await session.close()
        await engine.dispose()


# ─── Property-Based Tests (Hypothesis) ────────────────────────────────────────


# Strategies
json_primitives = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-10000, max_value=10000),
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
    st.text(min_size=0, max_size=20),
)

json_values = st.recursive(
    json_primitives,
    lambda children: st.one_of(
        st.lists(children, max_size=3),
        st.dictionaries(st.text(min_size=1, max_size=5), children, max_size=3),
    ),
    max_leaves=5,
)

item_ids = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
    min_size=1,
    max_size=20,
)


@settings(max_examples=5)
@given(after_value=json_values, item_id=item_ids)
def test_pbt_prepare_apply_roundtrip(after_value, item_id):
    """P3: For any legal mutation, after prepare→apply, read value == after_value.

    **Validates: Requirements 1.1, 3.1**
    """

    async def _run_test():
        session, engine = await _create_test_session()
        try:
            await _seed_project_and_wp(session, PROJECT_A, WP_A)
            adapter = WorkpaperMutationAdapter(session)
            target = _make_target(item_id=item_id)

            mutations = await adapter.prepare_many(
                [target], {target.addr_id: after_value}
            )
            assert len(mutations) == 1
            assert mutations[0].after_value == after_value

            await adapter.apply_many(mutations)

            # Re-read
            mutations2 = await adapter.prepare_many(
                [target], {target.addr_id: "ignored"}
            )
            # Read value equals what was written
            read_back = mutations2[0].before_value
            # JSON round-trip: compare via json serialization for float/int equivalence
            assert json.dumps(read_back, sort_keys=True) == json.dumps(
                after_value, sort_keys=True
            )
        finally:
            await session.close()
            await engine.dispose()

    _run(_run_test())


@settings(max_examples=5)
@given(item_id=item_ids)
def test_pbt_project_isolation(item_id):
    """P13: Cross-project target always rejected.

    **Validates: Requirements 12.1, 12.4**
    """

    async def _run_test():
        session, engine = await _create_test_session()
        try:
            await _seed_project_and_wp(session, PROJECT_A, WP_A)
            adapter = WorkpaperMutationAdapter(session)

            # Target claims PROJECT_B, but wp belongs to PROJECT_A
            target = _make_target(project_id=PROJECT_B, wp_id=WP_A, item_id=item_id)

            with pytest.raises(OwnershipViolation):
                await adapter.prepare_many([target], {target.addr_id: "x"})
        finally:
            await session.close()
            await engine.dispose()

    _run(_run_test())


@settings(max_examples=5)
@given(after_value=json_values, item_id=item_ids)
def test_pbt_version_conflict(after_value, item_id):
    """P4: If value changed between prepare and apply, adapter rejects.

    **Validates: Requirements 4.1, 4.4**
    """

    async def _run_test():
        session, engine = await _create_test_session()
        try:
            await _seed_project_and_wp(session, PROJECT_A, WP_A)
            adapter = WorkpaperMutationAdapter(session)
            target = _make_target(item_id=item_id)

            # Prepare
            mutations = await adapter.prepare_many(
                [target], {target.addr_id: after_value}
            )

            # Inject a conflicting row (simulate external edit)
            await session.execute(
                text(
                    "INSERT OR REPLACE INTO checklist_responses "
                    "(id, wp_id, item_id, remark, updated_at) "
                    "VALUES (:id, :wp_id, :item_id, :remark, :updated_at)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "wp_id": str(WP_A),
                    "item_id": item_id,
                    "remark": '"conflict"',
                    "updated_at": "2099-12-31T23:59:59+00:00",
                },
            )
            await session.flush()

            # Apply should fail with VersionConflict
            with pytest.raises(VersionConflict):
                await adapter.apply_many(mutations)
        finally:
            await session.close()
            await engine.dispose()

    _run(_run_test())
