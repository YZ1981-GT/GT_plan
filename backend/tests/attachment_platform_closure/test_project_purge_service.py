"""ProjectPurgeService 的事务、安全预检与 PG 依赖闭包测试。"""
from __future__ import annotations

import ast
import inspect
import uuid
from datetime import timedelta
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_utils import utcnow
from app.models.attachment_lineage_model import AttachmentLineage
from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.models.confirmation_models import ConfirmationAttachmentLink
from app.models.core import Project
from app.models.evidence_governance_models import AttachmentVersion
from app.models.wp_optimization_models import EvidenceLink
from app.services import project_purge_service as purge_module
from app.services.project_purge_service import (
    ProjectPurgeService,
    _ForeignKey,
    _TableMeta,
)
from tests.attachment_security_baseline._world import (
    add_attachment,
    add_confirmation,
    add_wp,
    pg_attachment_world,
)


class _ScalarResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _SessionStub:
    def __init__(self, dialect, result: Any = None) -> None:
        self._bind = type("Bind", (), {"dialect": dialect})()
        self._result = result
        self.execute = AsyncMock(return_value=_ScalarResult(result))

    def get_bind(self):
        return self._bind


def _service(dialect=None, result: Any = None) -> ProjectPurgeService:
    session = _SessionStub(dialect or postgresql.dialect(), result)
    return ProjectPurgeService(cast(AsyncSession, session))


def _project(*, deleted: bool, retention_until=None) -> Project:
    return Project(
        id=uuid.uuid4(),
        name="【测试】永久删除",
        client_name="测试客户",
        is_deleted=deleted,
        retention_until=retention_until,
    )


def test_service_source_uses_only_caller_session_and_never_suppresses_failure():
    source = inspect.getsource(purge_module)
    tree = ast.parse(source)
    forbidden_calls = {"commit", "rollback"}
    assert "create_async_engine" not in source
    assert "driver_connection" not in source
    assert "session_" + "replication_role" not in source
    assert not [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in forbidden_calls
    ]
    assert not [
        handler
        for node in ast.walk(tree)
        if isinstance(node, ast.Try)
        for handler in node.handlers
        if handler.body and all(isinstance(item, ast.Pass) for item in handler.body)
    ]


@pytest.mark.asyncio
async def test_project_must_still_be_soft_deleted_after_lock():
    project = _project(deleted=False)
    service = _service(result=project)
    with pytest.raises(HTTPException) as caught:
        await service._lock_project(project.id)
    assert caught.value.status_code == 409
    assert caught.value.detail["error_code"] == "PROJECT_PURGE_STATE_CHANGED"


def test_retention_until_must_have_expired():
    project = _project(deleted=True, retention_until=utcnow() + timedelta(days=2))
    with pytest.raises(HTTPException) as caught:
        ProjectPurgeService._assert_retention_expired(project)
    assert caught.value.status_code == 403
    assert caught.value.detail["error_code"] == "RETENTION_LOCKED"


@pytest.mark.asyncio
async def test_sqlite_is_explicitly_rejected_before_any_query():
    session = _SessionStub(sqlite.dialect())
    service = ProjectPurgeService(cast(AsyncSession, session))
    with pytest.raises(HTTPException) as caught:
        await service.preflight(uuid.uuid4(), actor_role="admin")
    assert caught.value.status_code == 409
    assert caught.value.detail["error_code"] == "PROJECT_PURGE_POSTGRESQL_REQUIRED"
    session.execute.assert_not_awaited()


class _HoldRecorder:
    def __init__(self, failure: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.failure = failure

    async def authorize_destructive(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)
        if self.failure is not None:
            raise self.failure


@pytest.mark.asyncio
async def test_authoritative_hold_check_covers_project_attachment_and_version():
    project_id, attachment_id, version_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    attachment = Attachment(
        id=attachment_id,
        project_id=project_id,
        file_name="证据.pdf",
        file_path="x.pdf",
        file_type="pdf",
        file_size=1,
    )
    version = AttachmentVersion(
        id=version_id,
        attachment_id=attachment_id,
        project_id=project_id,
        version_no=1,
        actor_type="user",
        actor_user_id=uuid.uuid4(),
    )
    recorder = _HoldRecorder()
    service = ProjectPurgeService(
        cast(AsyncSession, _SessionStub(postgresql.dialect())),
        legal_hold_factory=lambda _db: recorder,
    )
    await service._authorize_legal_holds(
        project_id, [attachment], [version], actor_role="admin"
    )
    assert [item["node_type"] for item in recorder.calls] == [
        "project",
        "attachment",
        "attachment_version",
    ]
    assert all(item["operation"] == "purge" for item in recorder.calls)
    assert all(item["project_id"] == project_id for item in recorder.calls)


@pytest.mark.asyncio
async def test_hold_lookup_failure_is_fail_closed():
    failure = RuntimeError("hold backend unavailable")
    recorder = _HoldRecorder(failure)
    service = ProjectPurgeService(
        cast(AsyncSession, _SessionStub(postgresql.dialect())),
        legal_hold_factory=lambda _db: recorder,
    )
    with pytest.raises(RuntimeError, match="hold backend unavailable"):
        await service._authorize_legal_holds(
            uuid.uuid4(), [], [], actor_role="admin"
        )


def test_non_nullable_fk_cycle_is_rejected_before_deletion():
    service = _service()
    tables = {
        1: _TableMeta(1, "public", "projects", frozenset({"id"}), frozenset()),
        2: _TableMeta(
            2, "public", "cycle_a", frozenset({"id", "project_id", "b_id"}), frozenset()
        ),
        3: _TableMeta(
            3, "public", "cycle_b", frozenset({"id", "project_id", "a_id"}), frozenset()
        ),
    }
    edges = (
        _ForeignKey(10, "fk_a_b", 2, 3, ("b_id",), ("id",), "s"),
        _ForeignKey(11, "fk_b_a", 3, 2, ("a_id",), ("id",), "s"),
    )
    with pytest.raises(HTTPException) as caught:
        service._plan_delete_order(1, tables, {1: 1, 2: 1, 3: 1}, edges)
    assert caught.value.status_code == 409
    assert caught.value.detail["error_code"] == "PROJECT_PURGE_UNSAFE_DEPENDENCY_GRAPH"


@pytest_asyncio.fixture
async def pg_world(monkeypatch):
    async with pg_attachment_world(monkeypatch) as world:
        yield world


async def _mark_deleted(world, *, retention_days: int = -1) -> None:
    world.target.is_deleted = True
    world.target.retention_until = utcnow() + timedelta(days=retention_days)
    await world.db.flush()


async def _add_version(world, attachment: Attachment, **values: Any) -> AttachmentVersion:
    actor = await world.user()
    return await world._add(
        AttachmentVersion(
            attachment_id=attachment.id,
            project_id=attachment.project_id,
            version_no=values.pop("version_no", 1),
            storage_type=values.pop("storage_type", "local"),
            storage_key=values.pop("storage_key", "legacy-version.pdf"),
            config_snapshot=values.pop("config_snapshot", None),
            actor_type="user",
            actor_user_id=actor.id,
            **values,
        )
    )


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_pg_preflight_calls_all_holds_and_collects_finalized_refs(pg_world):
    await _mark_deleted(pg_world)
    attachment = await add_attachment(
        pg_world,
        pg_world.target,
        file_path="legacy-root.pdf",
        storage_type="local",
    )
    version = await _add_version(
        pg_world,
        attachment,
        config_snapshot={
            "finalized_storage": {
                "storage_type": "local",
                "storage_key": "final/version-1.pdf",
            }
        },
    )
    recorder = _HoldRecorder()
    service = ProjectPurgeService(
        pg_world.db, legal_hold_factory=lambda _db: recorder
    )

    result = await service.preflight(pg_world.target.id, actor_role="admin")

    assert result.dry_run is True
    assert result.table_counts["projects"] == 1
    assert {item["node_type"] for item in recorder.calls} == {
        "project",
        "attachment",
        "attachment_version",
    }
    assert {item["node_id"] for item in recorder.calls} == {
        str(pg_world.target.id),
        str(attachment.id),
        str(version.id),
    }
    assert {(item.storage_type, item.storage_key) for item in result.file_refs} == {
        ("local", "legacy-root.pdf"),
        ("local", "final/version-1.pdf"),
    }


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_pg_preflight_rejects_all_named_cross_project_relationships(pg_world):
    await _mark_deleted(pg_world)
    other = await pg_world.other_project()
    target_attachment = await add_attachment(pg_world, pg_world.target)
    other_attachment = await add_attachment(pg_world, other)
    other_wp = await add_wp(pg_world, other, wp_code="D91")
    await pg_world._add(
        AttachmentWorkingPaper(
            attachment_id=target_attachment.id,
            wp_id=other_wp.id,
            association_type="evidence",
        )
    )
    await pg_world._add(
        EvidenceLink(
            wp_id=other_wp.id,
            attachment_id=target_attachment.id,
            created_by=uuid.uuid4(),
        )
    )
    other_confirmation = await add_confirmation(pg_world, other)
    await pg_world._add(
        ConfirmationAttachmentLink(
            confirmation_id=other_confirmation.id,
            attachment_id=target_attachment.id,
            role="outbound",
            match_status="manual",
        )
    )
    await pg_world._add(
        AttachmentLineage(
            attachment_id=other_attachment.id,
            project_id=pg_world.target.id,
            target_type="report_row",
            target_ref="资产负债表:货币资金",
        )
    )

    with pytest.raises(HTTPException) as caught:
        await ProjectPurgeService(pg_world.db).preflight(
            pg_world.target.id, actor_role="admin"
        )

    assert caught.value.status_code == 409
    assert caught.value.detail["error_code"] == "PROJECT_PURGE_CROSS_PROJECT_REFERENCE"
    assert set(caught.value.detail["relations"]) >= {
        "attachment_working_paper",
        "evidence_link",
        "confirmation_attachment_link",
        "attachment_lineage",
    }
    assert (
        await pg_world.db.execute(
            sa.select(Project.id).where(Project.id == pg_world.target.id)
        )
    ).scalar_one() == pg_world.target.id


async def _create_indirect_fk_rows(world) -> tuple[uuid.UUID, uuid.UUID]:
    await world.db.execute(
        sa.text(
            """CREATE TABLE purge_parent (
                   id uuid PRIMARY KEY,
                   project_id uuid NOT NULL REFERENCES projects(id)
               )"""
        )
    )
    await world.db.execute(
        sa.text(
            """CREATE TABLE purge_child (
                   id uuid PRIMARY KEY,
                   parent_id uuid NOT NULL REFERENCES purge_parent(id)
               )"""
        )
    )
    target_parent, other_parent = uuid.uuid4(), uuid.uuid4()
    other = await world.other_project()
    values = {
        "target_parent": str(target_parent),
        "target_project": str(world.target.id),
        "other_parent": str(other_parent),
        "other_project": str(other.id),
        "target_child": str(uuid.uuid4()),
        "other_child": str(uuid.uuid4()),
    }
    await world.db.execute(
        sa.text(
            """INSERT INTO purge_parent (id, project_id)
               VALUES (CAST(:target_parent AS uuid), CAST(:target_project AS uuid)),
                      (CAST(:other_parent AS uuid), CAST(:other_project AS uuid))"""
        ),
        values,
    )
    await world.db.execute(
        sa.text(
            """INSERT INTO purge_child (id, parent_id)
               VALUES (CAST(:target_child AS uuid), CAST(:target_parent AS uuid)),
                      (CAST(:other_child AS uuid), CAST(:other_parent AS uuid))"""
        ),
        values,
    )
    return target_parent, other_parent


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_pg_purge_deletes_indirect_fk_leaf_first_and_returns_counts(pg_world):
    await _mark_deleted(pg_world)
    attachment = await add_attachment(
        pg_world, pg_world.target, file_path="project/evidence.pdf", storage_type="local"
    )
    wp = await add_wp(pg_world, pg_world.target, wp_code="D92")
    await pg_world._add(
        AttachmentWorkingPaper(
            attachment_id=attachment.id,
            wp_id=wp.id,
            association_type="evidence",
        )
    )
    _, other_parent = await _create_indirect_fk_rows(pg_world)

    result = await ProjectPurgeService(pg_world.db).purge(
        pg_world.target.id, actor_role="admin"
    )

    assert result.dry_run is False
    assert result.table_counts["projects"] == 1
    assert result.table_counts["purge_parent"] == 1
    assert result.table_counts["purge_child"] == 1
    assert result.delete_order.index("purge_child") < result.delete_order.index(
        "purge_parent"
    )
    assert result.delete_order[-1] == "projects"
    assert result.file_refs == (
        purge_module.StoredAttachmentRef(
            pg_world.target.id, "local", "project/evidence.pdf"
        ),
    )
    target_left = (
        await pg_world.db.execute(
            sa.text("SELECT count(*) FROM projects WHERE id = :pid"),
            {"pid": pg_world.target.id},
        )
    ).scalar_one()
    other_left = (
        await pg_world.db.execute(
            sa.text("SELECT count(*) FROM purge_parent WHERE id = :pid"),
            {"pid": other_parent},
        )
    ).scalar_one()
    assert target_left == 0
    assert other_left == 1


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_pg_delete_failure_rolls_back_when_caller_rolls_back_transaction(pg_world):
    await _mark_deleted(pg_world)
    attachment = await add_attachment(pg_world, pg_world.target)
    wp = await add_wp(pg_world, pg_world.target, wp_code="D93")
    link = await pg_world._add(
        AttachmentWorkingPaper(
            attachment_id=attachment.id,
            wp_id=wp.id,
            association_type="evidence",
        )
    )
    await pg_world.db.execute(
        sa.text(
            """CREATE FUNCTION reject_attachment_delete() RETURNS trigger
               LANGUAGE plpgsql AS $$
               BEGIN
                   RAISE EXCEPTION 'forced attachment delete failure';
               END
               $$"""
        )
    )
    await pg_world.db.execute(
        sa.text(
            """CREATE TRIGGER reject_attachment_delete_trigger
               BEFORE DELETE ON attachments
               FOR EACH ROW EXECUTE FUNCTION reject_attachment_delete()"""
        )
    )

    with pytest.raises(sa.exc.DBAPIError):
        async with pg_world.db.begin_nested():
            await ProjectPurgeService(pg_world.db).purge(
                pg_world.target.id, actor_role="admin"
            )

    assert (
        await pg_world.db.execute(
            sa.select(Project.id).where(Project.id == pg_world.target.id)
        )
    ).scalar_one() == pg_world.target.id
    assert (
        await pg_world.db.execute(
            sa.select(Attachment.id).where(Attachment.id == attachment.id)
        )
    ).scalar_one() == attachment.id
    assert (
        await pg_world.db.execute(
            sa.select(AttachmentWorkingPaper.id).where(
                AttachmentWorkingPaper.id == link.id
            )
        )
    ).scalar_one() == link.id
