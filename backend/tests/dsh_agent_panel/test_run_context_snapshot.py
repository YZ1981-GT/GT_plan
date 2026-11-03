"""Chat Run 重启恢复的上下文请求快照契约。"""

from uuid import uuid4

from app.services.ai_chat.run_contract import ChatRunRequest


def test_context_snapshot_contains_only_ids_and_review_options() -> None:
    attachment_id = uuid4()
    project_attachment_id = uuid4()
    request = ChatRunRequest.model_validate(
        {
            "host": {"type": "workpaper", "id": str(uuid4())},
            "query": "请复核",
            "idempotency_key": str(uuid4()),
            "mentions": [{"type": "knowledge_doc", "id": str(uuid4())}],
            "attachment_ids": [str(attachment_id)],
            "project_attachment_ids": [str(project_attachment_id)],
            "review_mode": True,
            "sheet_name": "审定表",
        }
    )

    snapshot = request.context_snapshot()
    assert snapshot == {
        "mentions": [
            {"type": "knowledge_doc", "id": request.mentions[0].id}
        ],
        "attachment_ids": [str(attachment_id)],
        "project_attachment_ids": [str(project_attachment_id)],
        "review_mode": True,
        "sheet_name": "审定表",
    }
    forbidden = {"query", "host", "project_id", "content", "label", "scope"}
    assert forbidden.isdisjoint(snapshot)


def test_context_snapshot_roundtrips_through_request_validation() -> None:
    original = ChatRunRequest.model_validate(
        {
            "host": {"type": "note", "id": str(uuid4())},
            "query": "分析",
            "idempotency_key": str(uuid4()),
            "mentions": [{"type": "report", "id": "balance_sheet"}],
            "attachment_ids": [str(uuid4())],
            "project_attachment_ids": [str(uuid4())],
            "review_mode": False,
        }
    )
    restored = ChatRunRequest.model_validate(
        {
            "host": {"type": "note", "id": original.host.id},
            "query": original.query,
            "idempotency_key": str(uuid4()),
            **original.context_snapshot(),
        }
    )
    assert restored.mention_pairs() == original.mention_pairs()
    assert restored.attachment_ids == original.attachment_ids
    assert restored.project_attachment_ids == original.project_attachment_ids
    assert restored.review_mode == original.review_mode
    assert restored.sheet_name == original.sheet_name


def test_orm_and_migrations_declare_context_snapshot() -> None:
    from pathlib import Path

    from app.models.ai_models import AIChatRun

    assert "context_request_snapshot" in AIChatRun.__table__.c
    root = Path(__file__).resolve().parents[2]
    up = (root / "migrations" / "V236__ai_chat_run_context_request_snapshot.sql").read_text(encoding="utf-8")
    down = (root / "migrations" / "R236__ai_chat_run_context_request_snapshot.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS context_request_snapshot JSONB" in up
    assert "DROP COLUMN IF EXISTS context_request_snapshot" in down
