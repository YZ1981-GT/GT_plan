"""DraftArtifact：附注 diff、CAS、重复确认与安全撤销。"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

from app.models.ai_models import AIChatMessage, AIChatSession
from app.models.audit_log_models import AuditLogEntry
from app.models.base import Base, ProjectStatus, UserRole
from app.models.core import Project, User
from app.models.report_models import DisclosureNote, NoteStatus
from app.models.v3_refinement_models import AiContentLog
from app.services import draft_artifact_facade as facade
from app.services.ai_content_log_service import AiContentLogAlreadyProcessedError


@pytest_asyncio.fixture
async def world():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        User.__table__, Project.__table__, AuditLogEntry.__table__,
        AIChatSession.__table__, AIChatMessage.__table__,
        DisclosureNote.__table__, AiContentLog.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=tables))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_chat_session_user_key "
            "ON ai_chat_session(user_id, session_key) "
            "WHERE user_id IS NOT NULL AND session_key IS NOT NULL"
        ))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        user = User(
            id=uuid4(), username="draft-reviewer", email="draft@test.local",
            hashed_password="x", role=UserRole.manager, is_active=True,
        )
        project = Project(
            id=uuid4(), name="【测试】DraftArtifact", client_name="测试客户",
            status=ProjectStatus.execution,
        )
        note = DisclosureNote(
            id=uuid4(), project_id=project.id, year=2025,
            note_section="五、1", section_title="货币资金",
            text_content="原正文", status=NoteStatus.draft, is_deleted=False,
            is_local_override=False,
        )
        db.add_all([user, project, note])
        await db.commit()
        yield factory, user.id, project.id, note.id
    await engine.dispose()


@pytest.fixture(autouse=True)
def gates(monkeypatch):
    async def allow(*_args, **_kwargs):
        return None

    async def no_lock(*_args, **_kwargs):
        return None

    monkeypatch.setattr(facade, "assert_project_permission", allow)
    monkeypatch.setattr(facade, "check_consol_lock", allow)
    monkeypatch.setattr("app.services.editing_lock_service.find_blocking_lock", no_lock)


@pytest.mark.asyncio
async def test_prepare_apply_and_undo_use_exact_versions(world) -> None:
    factory, user_id, project_id, note_id = world
    async with factory() as db:
        artifact = await facade.prepare_note_artifact(
            db, project_id=project_id, user_id=user_id, note_id=note_id,
            content="AI 建议段落", model="fake", task_code="note.policy_draft",
        )
        artifact_id = artifact.id
        preview = facade.serialize_artifact(artifact)
        await db.commit()
    assert preview["before_content"] == "原正文"
    assert preview["proposed_content"] == "原正文\n\n---\n\nAI 建议段落"
    assert preview["writeback_status"] == "pending"

    async with factory() as db:
        user = await db.get(User, user_id)
        applied = await facade.apply_note_artifact(db, log_id=artifact_id, user=user)
        await db.commit()
        note = await db.get(DisclosureNote, note_id)
    assert note.text_content == preview["proposed_content"]
    assert applied["artifact"]["writeback_status"] == "applied"
    assert applied["artifact"]["can_undo"] is True

    async with factory() as db:
        user = await db.get(User, user_id)
        with pytest.raises(AiContentLogAlreadyProcessedError):
            await facade.apply_note_artifact(db, log_id=artifact_id, user=user)
        await db.rollback()

    async with factory() as db:
        user = await db.get(User, user_id)
        restored = await facade.undo_note_artifact(db, log_id=artifact_id, user=user)
        await db.commit()
        note = await db.get(DisclosureNote, note_id)
    assert note.text_content == "原正文"
    assert restored["artifact"]["writeback_status"] == "undone"
    assert restored["artifact"]["can_undo"] is False


@pytest.mark.asyncio
async def test_stale_target_never_receives_old_preview(world) -> None:
    factory, user_id, project_id, note_id = world
    async with factory() as db:
        artifact = await facade.prepare_note_artifact(
            db, project_id=project_id, user_id=user_id, note_id=note_id,
            content="旧预览", model="fake",
        )
        artifact_id = artifact.id
        await db.commit()
    async with factory() as db:
        note = await db.get(DisclosureNote, note_id)
        note.text_content = "人工新正文"
        note.updated_at = datetime.now(timezone.utc)
        await db.commit()
    async with factory() as db:
        user = await db.get(User, user_id)
        with pytest.raises(facade.DraftArtifactStale, match="预览后已被修改"):
            await facade.apply_note_artifact(db, log_id=artifact_id, user=user)
        # router 对 stale 的约定：提交治理状态，业务正文保持不动。
        await db.commit()
    async with factory() as db:
        note = await db.get(DisclosureNote, note_id)
        artifact = await db.get(AiContentLog, artifact_id)
    assert note.text_content == "人工新正文"
    assert artifact.confirm_action == "pending"
    assert artifact.writeback_status == "stale"
    assert artifact.is_stale is True


@pytest.mark.asyncio
async def test_undo_refuses_to_overwrite_later_manual_edit(world) -> None:
    factory, user_id, project_id, note_id = world
    async with factory() as db:
        artifact = await facade.prepare_note_artifact(
            db, project_id=project_id, user_id=user_id, note_id=note_id,
            content="AI 段落", model="fake",
        )
        artifact_id = artifact.id
        user = await db.get(User, user_id)
        await facade.apply_note_artifact(db, log_id=artifact_id, user=user)
        await db.commit()
    async with factory() as db:
        note = await db.get(DisclosureNote, note_id)
        note.text_content += "\n人工后续修改"
        note.updated_at = datetime.now(timezone.utc)
        await db.commit()
    async with factory() as db:
        user = await db.get(User, user_id)
        with pytest.raises(facade.DraftArtifactConflict, match="已再次修改"):
            await facade.undo_note_artifact(db, log_id=artifact_id, user=user)
        await db.rollback()


@pytest.mark.asyncio
async def test_note_ai_success_creates_authoritative_message_and_pending_artifact(world) -> None:
    from app.routers.note_ai import _persist_note_draft
    from app.services.ai_task_executor import AiTaskInvocation
    from app.services.ai_task_registry import get_ai_task_spec, get_prompt
    from app.services.llm_client import LLMInvocationResult, LLMInvocationStatus

    factory, user_id, project_id, _note_id = world
    spec = get_ai_task_spec("note.policy_draft")
    prompt = get_prompt(spec.prompt_id, spec.prompt_version)
    invocation = AiTaskInvocation(
        spec,
        prompt.version,
        prompt.sha256,
        LLMInvocationResult(
            status=LLMInvocationStatus.success,
            text="新的政策草稿",
            model_name="fake-model",
            deployment="local",
            total_tokens=12,
        ),
    )
    async with factory() as db:
        user = await db.get(User, user_id)
        result = await _persist_note_draft(
            db,
            project_id=project_id,
            year=2025,
            section_number="五、1",
            user=user,
            invocation=invocation,
            content="新的政策草稿",
            operation="replace",
        )
        message = await db.get(AIChatMessage, UUID(result["message_id"]))
        artifact = await db.get(AiContentLog, UUID(result["artifact_id"]))
    assert message.message_text == "新的政策草稿"
    assert message.content_hash == artifact.content_hash
    assert artifact.source_message_id == message.id
    assert artifact.task_code == "note.policy_draft"
    assert artifact.before_content == "原正文"
    assert artifact.writeback_status == "pending"


def test_v239_migration_and_orm_cover_draft_artifact_fields() -> None:
    from pathlib import Path

    fields = {
        "generation_id", "task_code", "source_message_id", "prompt_version",
        "context_manifest", "target_locator", "baseline_version", "before_hash",
        "before_content", "proposed_hash", "preview_diff", "artifact_version",
        "writeback_status", "applied_version", "applied_hash", "writeback_receipt",
        "undone_by", "undone_at",
    }
    assert fields <= set(AiContentLog.__table__.c.keys())
    root = Path(__file__).resolve().parents[1]
    up = (root / "migrations" / "V239__ai_content_draft_artifact.sql").read_text(encoding="utf-8")
    down = (root / "migrations" / "R239__ai_content_draft_artifact.sql").read_text(encoding="utf-8")
    for field in fields:
        assert f"ADD COLUMN IF NOT EXISTS {field}" in up
        assert f"DROP COLUMN IF EXISTS {field}" in down
    assert "uq_ai_content_log_source_target" in up
    assert "uq_ai_content_log_source_target" in down
