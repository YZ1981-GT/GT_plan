"""真实 PostgreSQL 守卫：AI 对话笔记转存 + 项目知识文件夹。

spec: knowledge-base-retrieval-and-authz-closure（Requirement 5.8 / 5.9，Property P13）

═══ 回归背景 ═══

``save_note`` 在 2026-09-29 之前**从未成功过**，五处缺陷全被 ``except Exception →
internal_error`` 吞成「笔记保存失败，请重试」：
  1. 按不存在的 ``KnowledgeFolder.project_id`` 查询 / 构造文件夹
  2. 调用不存在的 ``KnowledgeFolderService.create_document``
  3. 读不存在的 ``AIChatMessage.content`` / ``.text`` —— getattr 默认值把正文吞成空串
  4. 引用标签读 ``label``，而持久化负载的键是 ``source_name``
  5. 并发冲突时 ``db.rollback()`` —— 连已 claim 的幂等收据一起回滚

═══ 为什么必须真库 ═══

* 幂等收据靠 ``ON CONFLICT`` + V147 唯一索引，系统文件夹靠 V170 **部分**唯一索引 ——
  两条索引 DDL 直接取自迁移文件原句（``migration_statement``），不手抄。
* P13 的判据是「并发插入撞唯一索引 → 只回滚 SAVEPOINT，调用方此前 flush 的写仍在」：
  PostgreSQL 锁等待 + 事务语义，mock 测不出。竞态是**真实**制造的（第二个会话的 INSERT
  确认阻塞在锁上之后才提交第一个会话），并带反向对照：旧式 ``db.rollback()`` 必须丢写。
"""
from __future__ import annotations

import asyncio
import dataclasses
import sys
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))

from tests._kb_pg_scratch import migration_statement, scratch_schema  # noqa: E402

TOKEN = "笔记独特词乙"
ME = uuid.UUID("00000000-0000-0000-0000-0000000000c1")
OTHER = uuid.UUID("00000000-0000-0000-0000-0000000000c2")
P = uuid.UUID("00000000-0000-0000-0000-0000000000d1")
Q = uuid.UUID("00000000-0000-0000-0000-0000000000d2")
R = uuid.UUID("00000000-0000-0000-0000-0000000000d3")
SESSION = uuid.UUID("00000000-0000-0000-0000-0000000000e1")
OTHER_SESSION = uuid.UUID("00000000-0000-0000-0000-0000000000e2")


@dataclasses.dataclass
class _User:
    id: uuid.UUID
    role: str = "auditor"


def _extra_tables():
    from app.models.ai_models import AIChatActionReceipt, AIChatMessage, AIChatSession
    from app.models.core import Project

    return [
        Project.__table__,
        AIChatSession.__table__,
        AIChatMessage.__table__,
        AIChatActionReceipt.__table__,
    ]


def _extra_ddl() -> list[str]:
    return [
        migration_statement(
            "V170__knowledge_folder_system_key.sql",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_folders_system_key",
        ),
        migration_statement(
            "V147__ai_chat_persistence_runs_and_session_key.sql",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_chat_action_receipts_idempotency",
        ),
    ]


def _host():
    from app.services.ai_chat.contracts import HostType
    from app.services.ai_chat.host_context import AuthorizedHostContext

    return AuthorizedHostContext(
        principal_id=ME,
        project_id=P,
        year=2025,
        resource_type=HostType.workpaper,
        resource_id=str(uuid.uuid4()),
        display_label="测试底稿",
        permission_binding="test",
        allowed_actions=frozenset({"read", "note-create"}),
    )


async def _seed(Session) -> dict[str, uuid.UUID]:
    from app.models.ai_models import AIChatMessage, AIChatSession, ChatRole, SessionType
    from app.models.base import ProjectUserRole
    from app.models.core import Project, ProjectUser

    ids: dict[str, uuid.UUID] = {}

    def msg(key, session, role, text, *, status="completed", sources=None):
        ids[key] = uuid.uuid4()
        return AIChatMessage(
            id=ids[key], session_id=session, role=role, message_text=text,
            status=status, referenced_sources=sources,
        )

    async with Session() as s:
        s.add_all([
            Project(id=pid, name=f"项目{tag}", client_name=f"客户{tag}")
            for pid, tag in ((P, "P"), (Q, "Q"), (R, "R"))
        ])
        s.add_all([ProjectUser(project_id=pid, user_id=ME, role=ProjectUserRole.auditor) for pid in (P, Q)])
        s.add_all([
            AIChatSession(id=SESSION, user_id=ME, session_type=SessionType.general,
                          host_type="workpaper", host_id="wp"),
            AIChatSession(id=OTHER_SESSION, user_id=OTHER, session_type=SessionType.general,
                          host_type="workpaper", host_id="wp"),
        ])
        await s.flush()
        s.add_all([
            msg("m1", SESSION, ChatRole.assistant, f"{TOKEN} 第一段回复：函证应由审计师控制",
                sources=[{"source_type": "knowledge_doc", "source_id": "x", "source_name": "参考准则.md"},
                         {"label": "旧格式来源"}]),
            msg("m2", SESSION, ChatRole.assistant, "第二段回复：替代程序"),
            msg("m_user", SESSION, ChatRole.user, "用户提问不得入笔记"),
            msg("m_draft", SESSION, ChatRole.assistant, "草稿不得入笔记", status="draft"),
            msg("m_other", OTHER_SESSION, ChatRole.assistant, "他人会话不得入笔记"),
        ])
        await s.commit()
    return ids


async def _save(Session, message_ids, *, key: str, name: str = "函证笔记"):
    from app.services.ai_chat.note_service import NoteSaveFailed, save_note

    async with Session() as s:
        try:
            result = await save_note(
                s, user=_User(ME), actor_id=ME, host=_host(), session_id=SESSION,
                message_ids=message_ids, name=name, idempotency_key=key,
            )
            await s.commit()
            return {"ok": True, **result.as_dict()}
        except NoteSaveFailed as exc:
            await s.commit()  # 与路由一致：失败收据落库，便于安全重试
            return {"ok": False, "code": exc.code}


async def _note_scenarios(Session, ids, snap) -> None:
    from app.models.ai_models import AIChatActionReceipt
    from app.models.knowledge_models import KnowledgeDocument, KnowledgeFolder
    from app.services.knowledge_index_service import KnowledgeIndexService

    first = await _save(Session, [ids["m1"], ids["m2"], ids["m_user"], ids["m_draft"], ids["m_other"]], key="k1")
    snap["first"] = first
    replay = await _save(Session, [ids["m1"]], key="k1")
    snap["replay"] = replay
    second = await _save(Session, [ids["m2"]], key="k2", name="第二篇")
    snap["second"] = second
    empty = await _save(Session, [ids["m_user"], ids["m_other"]], key="k3", name="无有效消息")
    snap["empty"] = empty

    async with Session() as s:
        doc = (await s.execute(sa.select(KnowledgeDocument).where(
            KnowledgeDocument.id == uuid.UUID(first["document_id"])))).scalar_one()
        snap["doc"] = {
            "content": doc.content_text, "tags": doc.tags, "access": doc.access_level.value,
            "project_ids": doc.project_ids, "created_by": str(doc.created_by), "folder_id": str(doc.folder_id),
        }
        folders = (await s.execute(sa.select(KnowledgeFolder).order_by(KnowledgeFolder.system_key))).scalars().all()
        snap["folders"] = [
            {"key": f.system_key, "name": f.name, "parent": str(f.parent_id) if f.parent_id else None,
             "id": str(f.id), "access": f.access_level.value, "pids": f.project_ids, "created_by": f.created_by}
            for f in folders
        ]
        receipts = (await s.execute(sa.select(AIChatActionReceipt.idempotency_key, AIChatActionReceipt.status,
                                              AIChatActionReceipt.error_code)
                                    .order_by(AIChatActionReceipt.idempotency_key))).all()
        snap["receipts"] = [tuple(r) for r in receipts]

    # 转存的笔记可被文档正文词法检索召回（当前用户 + 当前项目），且不外溢到其它项目
    async with Session() as s:
        svc = KnowledgeIndexService(s)
        with patch.object(svc._ai_svc, "embedding", new=AsyncMock(side_effect=RuntimeError("down"))):
            in_p = await svc.semantic_search(P, TOKEN, top_k=5, user=_User(ME), scope="knowledge_doc")
            in_q = await svc.semantic_search(Q, TOKEN, top_k=5, user=_User(ME), scope="knowledge_doc")
            other_user = await svc.semantic_search(P, TOKEN, top_k=5, user=_User(OTHER), scope="knowledge_doc")
        snap["retrieval_P"] = [(h["source_id"], h.get("folder_path")) for h in in_p]
        snap["retrieval_Q"] = [h["source_id"] for h in in_q]
        snap["retrieval_other_user"] = [h["source_id"] for h in other_user]


async def _race(Session, *, legacy: bool) -> dict[str, Any]:
    """真实制造「两个会话同时建同一系统文件夹」：B 的 INSERT 阻塞在唯一索引锁上之后才提交 A。

    B 在建文件夹之前先写入一张「调用方自己的」收据（模拟 note_service 已 claim 的写）。
    新实现：B 撞索引 → 只回滚 SAVEPOINT → 拿到 A 的文件夹 → 收据仍在。
    ``legacy=True``：B 用旧式 ``db.rollback()`` 处理冲突 → 收据随之丢失（反向对照）。
    """
    from sqlalchemy.exc import IntegrityError

    from app.models.ai_models import AIChatActionReceipt
    from app.models.knowledge_models import KnowledgeAccessLevel, KnowledgeFolder
    from app.services import knowledge_folder_service as kfs

    key = f"race:{uuid.uuid4()}"
    receipt_key = f"race-receipt-{uuid.uuid4().hex[:8]}"
    out: dict[str, Any] = {}
    async with Session() as a, Session() as b:
        a_folder = KnowledgeFolder(id=uuid.uuid4(), name="A", system_key=key,
                                   access_level=KnowledgeAccessLevel.project_group, project_ids=[str(P)])
        a.add(a_folder)
        await a.flush()  # A 持有该键的索引锁（未提交）

        b.add(AIChatActionReceipt(action_type="note-create", actor_id=ME, session_id=SESSION,
                                  idempotency_key=receipt_key, status="pending"))
        await b.flush()

        async def b_ensure():
            if not legacy:
                return await kfs._ensure_system_folder(
                    b, system_key=key, name="B", parent_id=None, project_id=P
                )
            # 旧 note_service._ensure_notes_folder 的冲突处理：db.rollback() 后重查
            folder = KnowledgeFolder(id=uuid.uuid4(), name="B", system_key=key,
                                     access_level=KnowledgeAccessLevel.project_group, project_ids=[str(P)])
            b.add(folder)
            try:
                await b.flush()
            except IntegrityError:
                await b.rollback()
                return (await b.execute(sa.select(KnowledgeFolder).where(KnowledgeFolder.system_key == key))).scalar_one()
            return folder

        task = asyncio.create_task(b_ensure())
        blocked = False
        for _ in range(100):  # 最多 5s：确认 B 的 INSERT 确实在等锁
            await asyncio.sleep(0.05)
            waiting = (await a.execute(sa.text(
                "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock' "
                "AND datname = current_database() AND query ILIKE '%knowledge_folders%'"
            ))).scalar_one()
            if waiting:
                blocked = True
                break
        out["b_was_blocked_on_lock"] = blocked
        await a.commit()
        folder = await asyncio.wait_for(task, timeout=15)
        out["b_got_a_folder"] = folder.id == a_folder.id
        await b.commit()

    async with Session() as s:
        out["receipt_survived"] = (await s.execute(sa.select(sa.func.count()).select_from(AIChatActionReceipt).where(
            AIChatActionReceipt.idempotency_key == receipt_key))).scalar_one() == 1
        out["folders_with_key"] = (await s.execute(sa.select(sa.func.count()).select_from(KnowledgeFolder).where(
            KnowledgeFolder.system_key == key))).scalar_one()
    return out


async def _collect() -> dict[str, Any]:
    errors: list[str] = []
    snap: dict[str, Any] = {"harness_errors": errors}
    try:
        async with scratch_schema("kbnote", errors, extra_tables=_extra_tables(), extra_ddl=_extra_ddl()) as Session:
            ids = await _seed(Session)
            await _note_scenarios(Session, ids, snap)
            snap["race_new"] = await _race(Session, legacy=False)
            snap["race_legacy"] = await _race(Session, legacy=True)
            from app.services.knowledge_folder_service import ensure_project_folder

            async with Session() as s:
                try:
                    await ensure_project_folder(s, uuid.uuid4(), "ai_notes")
                    snap["missing_project"] = "no error"
                except ValueError as exc:
                    snap["missing_project"] = str(exc)
                try:
                    await ensure_project_folder(s, P, "nope")
                    snap["bad_slot"] = "no error"
                except ValueError as exc:
                    snap["bad_slot"] = str(exc)
    except Exception as exc:  # noqa: BLE001 - 采集失败必须让守卫红
        import traceback

        errors.append(f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-2000:]}")
    return snap


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


def test_harness_ran_without_errors(snap):
    assert snap["harness_errors"] == []


def test_note_saved_with_real_message_text_and_citations(snap):
    first = snap["first"]
    assert first["ok"] is True, first
    content = snap["doc"]["content"]
    assert content.startswith("# 函证笔记")
    assert f"{TOKEN} 第一段回复" in content and "第二段回复：替代程序" in content
    # 只收当前用户会话里的 completed assistant 消息
    assert "用户提问不得入笔记" not in content
    assert "草稿不得入笔记" not in content and "他人会话不得入笔记" not in content
    # 引用标签：source_name（新）与 label（旧）都能显示
    assert "- 参考准则.md" in content and "- 旧格式来源" in content


def test_note_document_is_project_group_and_owned_by_actor(snap):
    doc = snap["doc"]
    assert doc["access"] == "project_group" and doc["project_ids"] == [str(P)]
    assert doc["created_by"] == str(ME)
    assert set(doc["tags"]) == {"ai-note", "auto-generated"}


def test_project_folder_hierarchy_is_system_owned(snap):
    by_key = {f["key"]: f for f in snap["folders"]}
    root, slot = by_key[f"project:{P}"], by_key[f"project:{P}:ai_notes"]
    assert root["name"] == "项目P（项目资料）" and root["parent"] is None
    assert slot["name"] == "AI 对话笔记" and slot["parent"] == root["id"]
    for f in (root, slot):
        assert f["access"] == "project_group" and f["pids"] == [str(P)]
        assert f["created_by"] is None, "系统文件夹不应归任何个人所有"
    assert snap["doc"]["folder_id"] == slot["id"]


def test_second_note_reuses_the_same_folder(snap):
    assert snap["second"]["ok"] and snap["second"]["folder_id"] == snap["first"]["folder_id"]
    assert sum(1 for f in snap["folders"] if f["key"] == f"project:{P}:ai_notes") == 1


def test_replay_returns_same_document_with_real_folder_and_jump_route(snap):
    first, replay = snap["first"], snap["replay"]
    assert replay["ok"] and replay["replayed"] is True
    assert replay["document_id"] == first["document_id"]
    assert replay["folder_id"] == first["folder_id"], "重放时 folder_id 不得再用 document ID 冒充"
    assert first["jump_route"] == f"/knowledge?folder_id={first['folder_id']}&doc_id={first['document_id']}"
    assert replay["jump_route"] == first["jump_route"]


def test_no_valid_messages_fails_and_receipt_marked_failed(snap):
    assert snap["empty"] == {"ok": False, "code": "messages_not_found"}
    receipts = {k: (status, err) for k, status, err in snap["receipts"] if not k.startswith("race-")}
    assert receipts["k1"][0] == "succeeded" and receipts["k2"][0] == "succeeded"
    assert receipts["k3"] == ("failed", "note_save_failed")


def test_saved_note_is_retrievable_in_its_project_only(snap):
    hits = snap["retrieval_P"]
    assert [h[0] for h in hits] == [snap["first"]["document_id"]]
    assert hits[0][1] == "/项目P（项目资料）/AI 对话笔记"
    assert snap["retrieval_Q"] == [], "项目组笔记被注入到了其它项目"
    assert snap["retrieval_other_user"] == [], "非项目成员检索到了项目组笔记"


def test_p13_concurrent_creation_keeps_callers_prior_writes(snap):
    race = snap["race_new"]
    assert race["b_was_blocked_on_lock"], "夹具没制造出真实锁等待，竞态断言会空转"
    assert race["b_got_a_folder"] and race["folders_with_key"] == 1
    assert race["receipt_survived"], "撞唯一索引后回滚了调用方已 flush 的写"


def test_p13_negative_control_legacy_rollback_loses_prior_writes(snap):
    race = snap["race_legacy"]
    assert race["b_was_blocked_on_lock"] and race["b_got_a_folder"]
    assert race["receipt_survived"] is False, "反向对照未复现：旧式 db.rollback() 应丢掉收据"


def test_ensure_project_folder_rejects_unknown_project_and_slot(snap):
    assert snap["missing_project"].startswith("项目不存在")
    assert snap["bad_slot"].startswith("未知的项目知识文件夹槽位")
