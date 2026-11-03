"""项目附件加入 AI run：授权、确定版本 pin 与可信正文消费。"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.core.config import settings  # noqa: E402
from app.models.asset_blob_models import AiChatRunResource, AssetBlob  # noqa: E402
from app.models.attachment_models import Attachment  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole  # noqa: E402
from app.models.evidence_governance_models import AttachmentVersion, LegacyAttachmentAlias  # noqa: E402
from app.services.asset_blob_service import AssetBlobService  # noqa: E402
from app.services.ai_chat.run_resource_service import AiRunResourceService  # noqa: E402


_TABLES = [
    User.__table__, Project.__table__, AssetBlob.__table__, Attachment.__table__,
    AttachmentVersion.__table__, LegacyAttachmentAlias.__table__, AiChatRunResource.__table__,
]


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[dict]:
    monkeypatch.setenv("AI_PROJECT_ATTACHMENT_INPUT", "true")
    root = tmp_path / "attachments"
    monkeypatch.setattr(settings, "ATTACHMENT_LOCAL_STORAGE_ROOT", str(root))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        user = User(
            id=uuid.uuid4(), username="ai-asset", email="ai-asset@example.test",
            hashed_password="x", role=UserRole.auditor, is_active=True,
        )
        project = Project(
            id=uuid.uuid4(), name="【测试】AI附件_2025", client_name="测试",
            audit_year=2025, status=ProjectStatus.execution,
            project_type=ProjectType.annual, created_by=user.id,
        )
        path = root / str(project.id) / "evidence" / "证据.txt"
        path.parent.mkdir(parents=True)
        content = "项目附件唯一哨兵：收入截止测试。".encode("utf-8")
        path.write_bytes(content)
        attachment = Attachment(
            id=uuid.uuid4(), project_id=project.id, audit_year=2025,
            file_name="证据.txt", file_path=str(path), file_type="txt", file_size=len(content),
            attachment_type="evidence", storage_type="local", state="available",
            ocr_status="completed", ocr_text="错误的可变 OCR 镜像",
            actor_type="user", actor_user_id=user.id, created_by=user.id,
        )
        db.add_all((user, project, attachment))
        await db.flush()
        blob = await AssetBlobService(db).register_bytes(
            storage_type="local", storage_key=str(path), content=content,
            media_type="text/plain", actor_user_id=user.id,
        )
        version = AttachmentVersion(
            id=uuid.uuid4(), attachment_id=attachment.id, project_id=project.id,
            audit_year=2025, version_no=1, storage_type="local", storage_key=str(path),
            media_type="text/plain", byte_size=len(content), content_hash=blob.content_hash,
            blob_id=blob.id, availability="available", actor_type="user", actor_user_id=user.id,
        )
        db.add(version)
        await db.flush()
        attachment.current_version_id = version.id
        db.add(LegacyAttachmentAlias(
            old_attachment_id=attachment.id, attachment_id=attachment.id,
            attachment_version_id=version.id, project_id=project.id, audit_year=2025,
            resolution_kind="root",
        ))
        await db.commit()
        yield {
            "db": db, "user": user, "project": project, "attachment": attachment,
            "version": version, "blob": blob, "content": content,
        }
    await engine.dispose()


@pytest.mark.asyncio
async def test_authorize_pin_persist_and_load_exact_blob_text(
    world: dict, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.attachment_access as attachment_access
    import app.services.wp_visibility.entry_integration as entry_integration

    async def _require(db, user, attachment_id, _permission):
        return await db.get(Attachment, attachment_id)

    gate_calls: list[uuid.UUID] = []

    async def _visible(_db, _user, *, attachment_id, **_kwargs):
        gate_calls.append(attachment_id)
        return None

    monkeypatch.setattr(attachment_access, "require_attachment_permission", _require)
    monkeypatch.setattr(entry_integration, "enforce_attachment_wp_visibility", _visible)
    service = AiRunResourceService(world["db"])
    host = SimpleNamespace(project_id=world["project"].id)
    pins = await service.authorize_project_attachments(
        user=world["user"], host=host, attachment_ids=[world["attachment"].id],
    )
    assert gate_calls == [world["attachment"].id]
    assert pins[0].asset.attachment_version_id == world["version"].id
    assert pins[0].asset.content_hash == world["blob"].content_hash

    run_id, session_id = uuid.uuid4(), uuid.uuid4()
    await service.persist_project_attachments(
        run_id=run_id, session_id=session_id, actor_user_id=world["user"].id, pins=pins,
    )
    await world["db"].commit()
    row = (await world["db"].execute(sa.select(AiChatRunResource))).scalar_one()
    assert (row.attachment_version_id, row.blob_id, row.content_hash) == (
        world["version"].id, world["blob"].id, world["blob"].content_hash,
    )

    items = await service.load_project_attachment_context(
        run_id=run_id, session_id=session_id, actor_user_id=world["user"].id,
        project_id=world["project"].id, requested_ids=[world["attachment"].id],
    )
    assert items[0].content == world["content"].decode("utf-8")
    assert "错误的可变 OCR 镜像" not in items[0].content


@pytest.mark.asyncio
async def test_cross_project_is_rejected_before_version_pin(
    world: dict, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.attachment_access as attachment_access
    import app.services.wp_visibility.entry_integration as entry_integration

    async def _require(db, user, attachment_id, _permission):
        return await db.get(Attachment, attachment_id)

    gate = pytest.fail
    monkeypatch.setattr(attachment_access, "require_attachment_permission", _require)
    monkeypatch.setattr(entry_integration, "enforce_attachment_wp_visibility", gate)
    service = AiRunResourceService(world["db"])
    with pytest.raises(HTTPException) as exc:
        await service.authorize_project_attachments(
            user=world["user"],
            host=SimpleNamespace(project_id=uuid.uuid4()),
            attachment_ids=[world["attachment"].id],
        )
    assert exc.value.status_code == 404
    assert (await world["db"].execute(sa.select(sa.func.count()).select_from(AiChatRunResource))).scalar_one() == 0


@pytest.mark.asyncio
async def test_missing_pin_or_tampered_blob_fails_closed(
    world: dict,
) -> None:
    service = AiRunResourceService(world["db"])
    with pytest.raises(RuntimeError, match="钉住记录不完整"):
        await service.load_project_attachment_context(
            run_id=uuid.uuid4(), session_id=uuid.uuid4(), actor_user_id=world["user"].id,
            project_id=world["project"].id, requested_ids=[world["attachment"].id],
        )

    row = AiChatRunResource(
        run_id=uuid.uuid4(), session_id=uuid.uuid4(), resource_kind="project_attachment",
        resource_id=world["attachment"].id, attachment_version_id=world["version"].id,
        blob_id=world["blob"].id, content_hash=world["blob"].content_hash,
        actor_user_id=world["user"].id,
    )
    world["db"].add(row)
    await world["db"].commit()
    Path(world["blob"].storage_key).write_text("tampered", encoding="utf-8")
    from app.services.asset_blob_service import AssetBlobReadRejected

    with pytest.raises(AssetBlobReadRejected, match="integrity_mismatch"):
        await service.load_project_attachment_context(
            run_id=row.run_id, session_id=row.session_id, actor_user_id=world["user"].id,
            project_id=world["project"].id, requested_ids=[world["attachment"].id],
        )


def test_chat_run_request_accepts_only_stable_project_attachment_ids() -> None:
    from app.services.ai_chat.run_contract import ChatRunRequest, MAX_ATTACHMENTS_PER_RUN

    aid = uuid.uuid4()
    request = ChatRunRequest.model_validate({
        "host": {"type": "workpaper", "id": str(uuid.uuid4())},
        "query": "分析附件",
        "idempotency_key": str(uuid.uuid4()),
        "project_attachment_ids": [str(aid), str(aid)],
    })
    assert request.project_attachment_ids == [aid]
    assert request.context_snapshot()["project_attachment_ids"] == [str(aid)]

    payload = {
        "host": {"type": "workpaper", "id": str(uuid.uuid4())},
        "query": "分析附件",
        "idempotency_key": str(uuid.uuid4()),
        "attachment_ids": [str(uuid.uuid4()) for _ in range(MAX_ATTACHMENTS_PER_RUN)],
        "project_attachment_ids": [str(uuid.uuid4())],
    }
    with pytest.raises(ValueError, match="最多引用"):
        ChatRunRequest.model_validate(payload)
    for forbidden in ("resources", "blob_id", "attachment_version_id", "content_hash", "storage_key"):
        bad = dict(payload)
        bad["attachment_ids"] = []
        bad["project_attachment_ids"] = []
        bad[forbidden] = "client-controlled"
        with pytest.raises(ValueError, match=forbidden):
            ChatRunRequest.model_validate(bad)


@pytest.mark.asyncio
async def test_run_service_authorizes_before_writes_and_persists_after_run(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock, MagicMock

    import app.services.ai_chat.run_service as run_service
    import app.services.ai_chat.run_resource_service as resource_module
    from app.models.ai_models import ChatEngineName, ChatRunStatus
    from app.services.ai_chat.contracts import ResourceType
    from app.services.ai_chat.run_contract import ChatRunRequest

    actor_id, project_id, session_id, run_id = (uuid.uuid4() for _ in range(4))
    host = SimpleNamespace(
        principal_id=actor_id, project_id=project_id, year=2025,
        resource_type=ResourceType.workpaper, resource_id=str(uuid.uuid4()),
        display_label="D2", project_tools_enabled=True,
    )
    request = ChatRunRequest.model_validate({
        "host": {"type": "workpaper", "id": host.resource_id},
        "query": "分析项目附件",
        "idempotency_key": str(uuid.uuid4()),
        "project_attachment_ids": [str(uuid.uuid4())],
    })
    events: list[str] = []
    resource = MagicMock()
    resource.authorize_project_attachments = AsyncMock(side_effect=lambda **_kw: events.append("authorize") or ["pin"])
    resource.persist_chat_attachments = AsyncMock()
    resource.persist_project_attachments = AsyncMock(side_effect=lambda **_kw: events.append("persist"))
    monkeypatch.setattr(resource_module, "AiRunResourceService", lambda _db: resource)
    monkeypatch.setattr(run_service, "resolve_engine", lambda **_kw: (ChatEngineName.native, None))

    async def _session(*_args, **_kwargs):
        events.append("session")
        return SimpleNamespace(id=session_id), True

    async def _run(*_args, **_kwargs):
        events.append("run")
        return SimpleNamespace(
            id=run_id, request_id=uuid.uuid4(), status=ChatRunStatus.queued.value,
            error_code=None, engine=ChatEngineName.native.value,
            queued_at=datetime.now(timezone.utc),
        ), True

    monkeypatch.setattr(run_service, "upsert_session", _session)
    monkeypatch.setattr(run_service, "upsert_run", _run)
    monkeypatch.setattr(run_service, "append_message", AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())))
    service = run_service.ChatRunService(MagicMock())
    service._hosts.enforce = AsyncMock(return_value=host)
    creation = await service.create_run(SimpleNamespace(id=actor_id), request)

    assert creation.run_id == run_id
    assert events == ["authorize", "session", "run", "persist"]
    resource.persist_project_attachments.assert_awaited_once_with(
        run_id=run_id, session_id=session_id, actor_user_id=actor_id, pins=["pin"],
    )


@pytest.mark.asyncio
async def test_run_service_writes_nothing_when_project_attachment_authorization_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import AsyncMock, MagicMock

    import app.services.ai_chat.run_service as run_service
    import app.services.ai_chat.run_resource_service as resource_module
    from app.models.ai_models import ChatEngineName
    from app.services.ai_chat.contracts import ResourceType
    from app.services.ai_chat.run_contract import ChatRunRequest

    host = SimpleNamespace(
        principal_id=uuid.uuid4(), project_id=uuid.uuid4(), year=2025,
        resource_type=ResourceType.workpaper, resource_id=str(uuid.uuid4()),
        display_label="D2", project_tools_enabled=True,
    )
    request = ChatRunRequest.model_validate({
        "host": {"type": "workpaper", "id": host.resource_id},
        "query": "分析项目附件", "idempotency_key": str(uuid.uuid4()),
        "project_attachment_ids": [str(uuid.uuid4())],
    })
    resource = MagicMock()
    resource.authorize_project_attachments = AsyncMock(side_effect=HTTPException(404, "无权访问"))
    resource.persist_chat_attachments = AsyncMock()
    resource.persist_project_attachments = AsyncMock()
    monkeypatch.setattr(resource_module, "AiRunResourceService", lambda _db: resource)
    monkeypatch.setattr(run_service, "resolve_engine", lambda **_kw: (ChatEngineName.native, None))
    upsert = AsyncMock()
    monkeypatch.setattr(run_service, "upsert_session", upsert)
    service = run_service.ChatRunService(MagicMock())
    service._hosts.enforce = AsyncMock(return_value=host)

    with pytest.raises(HTTPException) as exc:
        await service.create_run(SimpleNamespace(id=host.principal_id), request)
    assert exc.value.status_code == 404
    upsert.assert_not_awaited()
