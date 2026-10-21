# Feature: ai-chat-adopt-and-note-target-picker — 采纳另选目标 / 笔记保存位置（真实 PG）
"""采纳到另选目标、笔记转存到指定位置的允许 / 拒绝 / 零副作用守卫。

Requirements: R2（采纳跨宿主四条规则）、R4（笔记来源会话与保存位置）。

复现背景（2026-10-20 浏览器）：项目列表页全局模式下「采纳」恒 404、「转存笔记」前端拦截且
请求体与后端契约不一致恒 422。本文件只测服务端规则；请求体契约在前端 vitest 对账。

判据落在真实执行上：真实 ``HostContextResolver`` 授权、真实 ``adopt_message`` /
``save_note`` 写 ``ai_content_log`` / ``knowledge_documents`` / 收据 / 哈希链审计，
夹具事务整体回滚（``run_with_fixture``）。``commit`` / ``rollback`` 的替身同 Task 7：
commit → flush（写入留在夹具事务里可查），rollback → 记录型 no-op（撤销靠 SAVEPOINT）。
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import HTTPException

from app.models.ai_models import ActionReceiptType, ChatRole
from app.services.ai_chat import persistence
from app.services.ai_chat.access import ResourceAccessResolver
from app.services.ai_chat.adopt import ADOPT_AUDIT_ACTION, ADOPT_AUDIT_DETAIL_KEYS, adopt_message
from app.services.ai_chat.contracts import (
    GLOBAL_KNOWLEDGE_HOST_ID,
    AiChatAction,
    HostRef,
    HostType,
    role_allows_action,
)
from app.services.ai_chat.host_context import HostContextResolver
from app.services.ai_chat.note_service import NoteSaveFailed, save_note
from app.services.wp_visibility.denial import ExternalNotFound

from ._fixtures import IS_PG, AccessFixture, run_with_fixture

pytestmark = pytest.mark.skipif(not IS_PG, reason="need PostgreSQL（采纳 / 笔记链路真实约束）")

GLOBAL = HostRef(type=HostType.global_knowledge, id=GLOBAL_KNOWLEDGE_HOST_ID)
BODY = "存货监盘应双向抽盘：从账到实验证存在性，从实到账验证完整性。"


class _TxnProbe:
    """commit → flush、rollback → 记录型 no-op（与 test_task7 同形，见模块说明）。"""

    def __init__(self, session: Any) -> None:
        self._session = session
        self._orig = (session.commit, session.rollback)

    async def _commit(self) -> None:
        await self._session.flush()

    async def _rollback(self) -> None:
        return None

    def __enter__(self) -> "_TxnProbe":
        self._session.commit = self._commit  # type: ignore[method-assign]
        self._session.rollback = self._rollback  # type: ignore[method-assign]
        return self

    def __exit__(self, *exc: object) -> None:
        self._session.commit, self._session.rollback = self._orig  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# 夹具助手
# ---------------------------------------------------------------------------


def _resolver(fx: AccessFixture) -> ResourceAccessResolver:
    return ResourceAccessResolver(fx.session, responder=fx.responder)


async def _authorized(fx: AccessFixture, user, ref: HostRef, action: AiChatAction):
    return await HostContextResolver(fx.session, access=_resolver(fx)).enforce(
        user, ref, action, entrypoint="test.explicit_target"
    )


async def _seed(fx, actor_id, *, host_type, host_id, project_id, texts=(BODY,)):
    """用生产原语播种会话 + completed assistant 消息，返回 (session, [msg...])。"""
    session, _ = await persistence.upsert_session(
        fx.session,
        user_id=actor_id,
        project_id=project_id,
        audit_year=fx.project_a.audit_year if project_id else None,
        host_type=host_type,
        host_id=host_id,
    )
    msgs = [
        await persistence.append_message(fx.session, session, role=ChatRole.assistant, text=t)
        for t in texts
    ]
    return session, msgs


async def _seed_global(fx, actor_id, texts=(BODY,)):
    return await _seed(
        fx, actor_id, host_type=HostType.global_knowledge,
        host_id=GLOBAL_KNOWLEDGE_HOST_ID, project_id=None, texts=texts,
    )


async def _pick(fx: AccessFixture, ref: HostRef, action: AiChatAction):
    """挑一个对 ``ref`` 真有 ``action`` 权限的角色（判据不空跑）。

    走 ``HostContextResolver.resolve``（先反查再授权）：附注宿主的项目由行自身给出，
    直接用 ``authorize_host`` 判裸 ref 会因缺项目断言恒拒，挑不出人。
    """
    from app.services.ai_chat.host_context import AuthorizedHostContext

    resolver = HostContextResolver(fx.session, access=_resolver(fx))
    for actor in fx.all_actors:
        outcome = await resolver.resolve(actor.user, ref, action)
        if isinstance(outcome, AuthorizedHostContext):
            return actor
    raise AssertionError(f"夹具里没有角色能对 {ref.type.value} 执行 {action.value}")


def _note_creator(fx: AccessFixture):
    for actor in fx.all_actors:
        if role_allows_action(actor.role, AiChatAction.note_create):
            return actor
    raise AssertionError("夹具里没有角色允许创建笔记")


async def _count(fx: AccessFixture, sql: str, **params: Any) -> int:
    return int((await fx.session.execute(sa.text(sql), params)).scalar_one() or 0)


async def _receipts(fx, session_id, action_type) -> int:
    return await _count(
        fx,
        "SELECT count(*) FROM ai_chat_action_receipts WHERE session_id = :s AND action_type = :a",
        s=session_id, a=action_type.value,
    )


def _denials(fx: AccessFixture, entrypoint: str) -> list[str]:
    return [
        (r.get("detail") or {}).get("ai_denial_code")
        for r in fx.responder.records
        if r.get("entrypoint") == entrypoint
    ]


def _wp_ref(fx) -> HostRef:
    return HostRef(type=HostType.workpaper, id=str(fx.wp_d_file.id))


def _note_ref(fx) -> HostRef:
    return HostRef(type=HostType.note, id=str(fx.note_a.id))


# ===========================================================================
# R2：采纳到另选目标
# ===========================================================================


class TestAdoptExplicitTarget:
    def test_global_reply_adopts_into_selected_workpaper(self):
        """全局知识会话的回复 → 用户选定的底稿：进入确认流，审计记来源宿主。"""

        async def scenario(fx: AccessFixture, _sql):
            actor = await _pick(fx, _wp_ref(fx), AiChatAction.adopt)
            session, (msg,) = await _seed_global(fx, actor.id)
            source = await _authorized(fx, actor.user, GLOBAL, AiChatAction.history)
            target = await _authorized(fx, actor.user, _wp_ref(fx), AiChatAction.adopt)
            with _TxnProbe(fx.session):
                outcome = await adopt_message(
                    fx.session, actor_id=actor.id, host=target, message_id=msg.id,
                    idempotency_key=uuid.uuid4(), target_cell="D12",
                    access=_resolver(fx), source_host=source,
                )
            row = (await fx.session.execute(sa.text(
                "SELECT generated_content, confirm_action, target_cell, project_id "
                "FROM ai_content_log WHERE id = :i"), {"i": outcome.ai_content_log_id})).first()
            assert row is not None
            assert row[0] == BODY and row[1] == "pending"
            assert row[2] == f"workpaper:{fx.wp_d_file.id}:D12"
            assert row[3] == fx.project_a.id
            payload = (await fx.session.execute(sa.text(
                "SELECT payload FROM audit_log_entries WHERE action_type = :a "
                "AND payload->>'ai_content_log_id' = :i"),
                {"a": ADOPT_AUDIT_ACTION, "i": str(outcome.ai_content_log_id)})).scalar_one()
            assert set(payload) == ADOPT_AUDIT_DETAIL_KEYS | {"project_id"}
            assert payload["source_host_type"] == "global_knowledge"
            assert payload["source_host_id"] == GLOBAL_KNOWLEDGE_HOST_ID
            assert payload["host_type"] == "workpaper"
            assert await _receipts(fx, session.id, ActionReceiptType.adopt) == 1

        run_with_fixture(scenario)

    def test_global_reply_adopts_into_selected_note(self):
        async def scenario(fx: AccessFixture, _sql):
            actor = await _pick(fx, _note_ref(fx), AiChatAction.adopt)
            _session, (msg,) = await _seed_global(fx, actor.id)
            source = await _authorized(fx, actor.user, GLOBAL, AiChatAction.history)
            target = await _authorized(fx, actor.user, _note_ref(fx), AiChatAction.adopt)
            with _TxnProbe(fx.session):
                outcome = await adopt_message(
                    fx.session, actor_id=actor.id, host=target, message_id=msg.id,
                    idempotency_key=uuid.uuid4(), access=_resolver(fx), source_host=source,
                )
            cell = (await fx.session.execute(sa.text(
                "SELECT target_cell FROM ai_content_log WHERE id = :i"),
                {"i": outcome.ai_content_log_id})).scalar_one()
            assert cell == f"note:{fx.note_a.id}"

        run_with_fixture(scenario)

    def test_global_reply_without_source_host_is_still_rejected(self):
        """不带 source_host = 现行同宿主绑定：全局会话的消息不能采纳进底稿，零副作用。"""

        async def scenario(fx: AccessFixture, _sql):
            actor = await _pick(fx, _wp_ref(fx), AiChatAction.adopt)
            session, (msg,) = await _seed_global(fx, actor.id)
            target = await _authorized(fx, actor.user, _wp_ref(fx), AiChatAction.adopt)
            with _TxnProbe(fx.session), pytest.raises(ExternalNotFound):
                await adopt_message(
                    fx.session, actor_id=actor.id, host=target, message_id=msg.id,
                    idempotency_key=uuid.uuid4(), access=_resolver(fx),
                )
            assert await _count(fx, "SELECT count(*) FROM ai_content_log WHERE project_id = :p",
                                p=fx.project_a.id) == 0
            assert await _receipts(fx, session.id, ActionReceiptType.adopt) == 0

        run_with_fixture(scenario)

    def test_document_session_cannot_be_redirected(self):
        """底稿会话的回复即使带 source_host 也不能采纳到别的文件（规则②）。"""

        async def scenario(fx: AccessFixture, _sql):
            actor = await _pick(fx, _note_ref(fx), AiChatAction.adopt)
            _session, (msg,) = await _seed(
                fx, actor.id, host_type=HostType.workpaper, host_id=str(fx.wp_d_file.id),
                project_id=fx.project_a.id,
            )
            source = await _authorized(fx, actor.user, _wp_ref(fx), AiChatAction.history)
            target = await _authorized(fx, actor.user, _note_ref(fx), AiChatAction.adopt)
            with _TxnProbe(fx.session), pytest.raises(ExternalNotFound):
                await adopt_message(
                    fx.session, actor_id=actor.id, host=target, message_id=msg.id,
                    idempotency_key=uuid.uuid4(), access=_resolver(fx), source_host=source,
                )
            assert _denials(fx, "ai_chat.adopt.cross_target") == ["host_context_mismatch"]
            assert await _count(fx, "SELECT count(*) FROM ai_content_log WHERE project_id = :p",
                                p=fx.project_a.id) == 0

        run_with_fixture(scenario)

    def test_source_bound_to_another_project_is_rejected(self):
        """来源会话绑定了别的项目 ⇒ cross_project（规则④）。"""

        async def scenario(fx: AccessFixture, _sql):
            actor = await _pick(fx, _wp_ref(fx), AiChatAction.adopt)
            folder_ref = HostRef(
                type=HostType.knowledge_folder, id=str(fx.folder_public.id),
                project_id_assertion=fx.project_b.id,
            )
            _session, (msg,) = await _seed(
                fx, actor.id, host_type=HostType.knowledge_folder,
                host_id=str(fx.folder_public.id), project_id=fx.project_b.id,
            )
            source = await _authorized(fx, actor.user, folder_ref, AiChatAction.history)
            assert source.project_id == fx.project_b.id
            target = await _authorized(fx, actor.user, _wp_ref(fx), AiChatAction.adopt)
            with _TxnProbe(fx.session), pytest.raises(ExternalNotFound):
                await adopt_message(
                    fx.session, actor_id=actor.id, host=target, message_id=msg.id,
                    idempotency_key=uuid.uuid4(), access=_resolver(fx), source_host=source,
                )
            assert _denials(fx, "ai_chat.adopt.cross_target") == ["cross_project"]

        run_with_fixture(scenario)

    def test_target_must_be_workpaper_or_note(self):
        """目标是知识库文档（有项目断言、可写）⇒ host_context_mismatch（规则③）。"""

        async def scenario(fx: AccessFixture, _sql):
            doc_ref = HostRef(
                type=HostType.knowledge_doc, id=str(fx.doc_public.id),
                project_id_assertion=fx.project_a.id,
            )
            actor = await _pick(fx, doc_ref, AiChatAction.adopt)
            _session, (msg,) = await _seed_global(fx, actor.id)
            source = await _authorized(fx, actor.user, GLOBAL, AiChatAction.history)
            target = await _authorized(fx, actor.user, doc_ref, AiChatAction.adopt)
            with _TxnProbe(fx.session), pytest.raises(ExternalNotFound):
                await adopt_message(
                    fx.session, actor_id=actor.id, host=target, message_id=msg.id,
                    idempotency_key=uuid.uuid4(), access=_resolver(fx), source_host=source,
                )
            assert _denials(fx, "ai_chat.adopt.cross_target") == ["host_context_mismatch"]
            assert await _count(fx, "SELECT count(*) FROM ai_content_log WHERE project_id = :p",
                                p=fx.project_a.id) == 0

        run_with_fixture(scenario)

    def test_source_authorized_for_another_user_is_rejected(self):
        """来源宿主上下文属于另一主体 ⇒ access_denied（规则①）。"""

        async def scenario(fx: AccessFixture, _sql):
            actor = await _pick(fx, _wp_ref(fx), AiChatAction.adopt)
            other = next(a for a in fx.all_actors if a.id != actor.id)
            _session, (msg,) = await _seed_global(fx, actor.id)
            foreign_source = await _authorized(fx, other.user, GLOBAL, AiChatAction.history)
            target = await _authorized(fx, actor.user, _wp_ref(fx), AiChatAction.adopt)
            with _TxnProbe(fx.session), pytest.raises(ExternalNotFound):
                await adopt_message(
                    fx.session, actor_id=actor.id, host=target, message_id=msg.id,
                    idempotency_key=uuid.uuid4(), access=_resolver(fx),
                    source_host=foreign_source,
                )
            assert _denials(fx, "ai_chat.adopt.cross_target") == ["access_denied"]

        run_with_fixture(scenario)


# ===========================================================================
# R4：笔记转存的来源会话与保存位置
# ===========================================================================


async def _save(fx, actor, host, message_ids, **kw):
    return await save_note(
        fx.session,
        user=actor.user,
        actor_id=actor.id,
        host=host,
        session_id=kw.pop("session_id", None),
        message_ids=message_ids,
        name=kw.pop("name", "存货监盘要点"),
        idempotency_key=str(uuid.uuid4()),
        access=_resolver(fx),
        **kw,
    )


async def _doc_row(fx, document_id: str):
    return (await fx.session.execute(sa.text(
        "SELECT d.folder_id, d.access_level, d.project_ids, d.created_by, d.content_text, "
        "       f.system_key "
        "FROM knowledge_documents d JOIN knowledge_folders f ON f.id = d.folder_id "
        "WHERE d.id = :i"), {"i": uuid.UUID(document_id)})).first()


async def _assert_no_side_effects(fx, actor, session_id, name="存货监盘要点"):
    """位置 / 来源校验失败必须零副作用：无文档、无收据、无系统文件夹。"""
    assert await _count(
        fx, "SELECT count(*) FROM knowledge_documents WHERE created_by = :u AND name = :n",
        u=actor.id, n=name,
    ) == 0, "校验失败仍写了笔记文档"
    assert await _receipts(fx, session_id, ActionReceiptType.note_create) == 0, (
        "校验必须先于幂等收据"
    )
    for project in (fx.project_a, fx.project_b):
        assert await _count(
            fx, "SELECT count(*) FROM knowledge_folders WHERE system_key = :k",
            k=f"project:{project.id}:ai_notes",
        ) == 0, "校验失败仍创建了项目笔记文件夹"


class TestNoteSaveLocation:
    def test_global_reply_saved_into_selected_project_notes(self):
        async def scenario(fx: AccessFixture, _sql):
            actor = _note_creator(fx)
            session, (msg,) = await _seed_global(fx, actor.id)
            host = await _authorized(fx, actor.user, GLOBAL, AiChatAction.history)
            result = await _save(fx, actor, host, [msg.id], target_project_id=fx.project_a.id)
            out = result.as_dict()
            folder_id, access, pids, created_by, content, key = await _doc_row(
                fx, out["document_id"]
            )
            assert key == f"project:{fx.project_a.id}:ai_notes"
            assert str(access) in ("project_group", "KnowledgeAccessLevel.project_group")
            assert pids == [str(fx.project_a.id)] and created_by == actor.id
            assert BODY in content
            assert out["location"] == f"{fx.project_a.name}（项目资料） / AI 对话笔记"
            assert out["folder_id"] == str(folder_id)
            receipt_session = (await fx.session.execute(sa.text(
                "SELECT session_id FROM ai_chat_action_receipts WHERE result_resource_id = :d"),
                {"d": uuid.UUID(out["document_id"])})).scalar_one()
            assert receipt_session == session.id, "会话应由服务端按消息反查"

        run_with_fixture(scenario)

    def test_global_reply_saved_into_selected_folder_inherits_access(self):
        async def scenario(fx: AccessFixture, _sql):
            actor = _note_creator(fx)
            _session, (msg,) = await _seed_global(fx, actor.id)
            host = await _authorized(fx, actor.user, GLOBAL, AiChatAction.history)
            result = await _save(fx, actor, host, [msg.id], target_folder_id=fx.folder_public.id)
            out = result.as_dict()
            folder_id, access, pids, _by, _content, _key = await _doc_row(fx, out["document_id"])
            assert folder_id == fx.folder_public.id
            assert access is None and pids is None, "文件夹目标的文档应继承文件夹权限"
            assert out["location"] == fx.folder_public.name

        run_with_fixture(scenario)

    def test_default_location_derives_session_from_messages(self):
        """底稿宿主 + 不传 session_id（前端旧缺陷 D3 的根因）⇒ 保存到本项目笔记。"""

        async def scenario(fx: AccessFixture, _sql):
            actor = await _pick(fx, _wp_ref(fx), AiChatAction.note_create)
            _session, msgs = await _seed(
                fx, actor.id, host_type=HostType.workpaper, host_id=str(fx.wp_d_file.id),
                project_id=fx.project_a.id, texts=(BODY, "第二条：截止测试。"),
            )
            host = await _authorized(fx, actor.user, _wp_ref(fx), AiChatAction.note_create)
            out = (await _save(fx, actor, host, [m.id for m in msgs])).as_dict()
            *_rest, content, key = await _doc_row(fx, out["document_id"])
            assert key == f"project:{fx.project_a.id}:ai_notes"
            assert BODY in content and "第二条：截止测试。" in content

        run_with_fixture(scenario)


class TestNoteSaveLocationRejected:
    """每条拒绝都断言错误码 + 零副作用（校验先于收据）。"""

    @staticmethod
    async def _expect(fx, actor, host, message_ids, code, **kw) -> NoteSaveFailed:
        with pytest.raises(NoteSaveFailed) as exc:
            await _save(fx, actor, host, message_ids, **kw)
        assert exc.value.code == code, (exc.value.code, exc.value.message)
        assert exc.value.message, "拒绝必须带中文原因"
        return exc.value

    def test_global_host_without_location(self):
        async def scenario(fx: AccessFixture, _sql):
            actor = _note_creator(fx)
            session, (msg,) = await _seed_global(fx, actor.id)
            host = await _authorized(fx, actor.user, GLOBAL, AiChatAction.history)
            await self._expect(fx, actor, host, [msg.id], "no_target")
            await _assert_no_side_effects(fx, actor, session.id)

        run_with_fixture(scenario)

    def test_both_locations_given(self):
        async def scenario(fx: AccessFixture, _sql):
            actor = _note_creator(fx)
            session, (msg,) = await _seed_global(fx, actor.id)
            host = await _authorized(fx, actor.user, GLOBAL, AiChatAction.history)
            await self._expect(
                fx, actor, host, [msg.id], "ambiguous_target",
                target_project_id=fx.project_a.id, target_folder_id=fx.folder_public.id,
            )
            await _assert_no_side_effects(fx, actor, session.id)

        run_with_fixture(scenario)

    def test_project_session_cannot_leave_its_project(self):
        """项目会话只能存到本项目：别的项目、知识库文件夹都拒绝。"""

        async def scenario(fx: AccessFixture, _sql):
            actor = await _pick(fx, _wp_ref(fx), AiChatAction.note_create)
            session, (msg,) = await _seed(
                fx, actor.id, host_type=HostType.workpaper, host_id=str(fx.wp_d_file.id),
                project_id=fx.project_a.id,
            )
            host = await _authorized(fx, actor.user, _wp_ref(fx), AiChatAction.history)
            for kw in ({"target_project_id": fx.project_b.id},
                       {"target_folder_id": fx.folder_public.id}):
                await self._expect(fx, actor, host, [msg.id], "target_out_of_scope", **kw)
            await _assert_no_side_effects(fx, actor, session.id)

        run_with_fixture(scenario)

    def test_default_location_rejects_session_of_another_project(self):
        """缺陷 D4 回归：A 项目底稿宿主 + B 项目会话的消息 ⇒ 不得存进 A 项目。"""

        async def scenario(fx: AccessFixture, _sql):
            actor = await _pick(fx, _wp_ref(fx), AiChatAction.note_create)
            session_b, (msg,) = await _seed(
                fx, actor.id, host_type=HostType.workpaper, host_id=str(fx.wp_other_file.id),
                project_id=fx.project_b.id,
            )
            host = await _authorized(fx, actor.user, _wp_ref(fx), AiChatAction.note_create)
            await self._expect(fx, actor, host, [msg.id], "target_out_of_scope")
            await _assert_no_side_effects(fx, actor, session_b.id)

        run_with_fixture(scenario)

    def test_knowledge_host_project_assertion_requires_membership(self):
        """知识库宿主的项目是客户端断言（locate 不复核成员）⇒ 默认位置也要补项目判权。

        补口前：非 B 项目成员在知识库页面带 ``project_id=B`` 打开 AI，即可把笔记写进 B 项目。
        """

        async def scenario(fx: AccessFixture, _sql):
            actor = _note_creator(fx)
            ref = HostRef(
                type=HostType.knowledge_folder, id=str(fx.folder_public.id),
                project_id_assertion=fx.project_b.id,
            )
            session, (msg,) = await _seed(
                fx, actor.id, host_type=HostType.knowledge_folder,
                host_id=str(fx.folder_public.id), project_id=fx.project_b.id,
            )
            host = await _authorized(fx, actor.user, ref, AiChatAction.note_create)
            assert host.project_id == fx.project_b.id and host.allows(AiChatAction.note_create)
            await self._expect(fx, actor, host, [msg.id], "target_denied")
            await _assert_no_side_effects(fx, actor, session.id)

        run_with_fixture(scenario)

    def test_project_without_membership_is_denied_and_audited(self):
        async def scenario(fx: AccessFixture, _sql):
            actor = _note_creator(fx)
            session, (msg,) = await _seed_global(fx, actor.id)
            host = await _authorized(fx, actor.user, GLOBAL, AiChatAction.history)
            for pid in (fx.project_b.id, uuid.uuid4()):
                err = await self._expect(
                    fx, actor, host, [msg.id], "target_denied", target_project_id=pid
                )
                assert "不存在或无权访问" in err.message, "不存在与无权必须同一句"
            assert _denials(fx, "ai_chat.note_save.target") == ["access_denied", "access_denied"]
            await _assert_no_side_effects(fx, actor, session.id)

        run_with_fixture(scenario)

    def test_folder_without_create_permission_is_denied(self):
        async def scenario(fx: AccessFixture, _sql):
            actor = _note_creator(fx)
            session, (msg,) = await _seed_global(fx, actor.id)
            host = await _authorized(fx, actor.user, GLOBAL, AiChatAction.history)
            for folder_id in (fx.folder_group_b.id, uuid.uuid4()):
                await self._expect(
                    fx, actor, host, [msg.id], "target_denied", target_folder_id=folder_id
                )
            assert _denials(fx, "ai_chat.note_save.target") == [
                "access_denied", "resource_not_found",
            ]
            await _assert_no_side_effects(fx, actor, session.id)

        run_with_fixture(scenario)

    def test_role_without_note_capability_is_denied(self):
        async def scenario(fx: AccessFixture, _sql):
            reviewer = next(
                (a for a in fx.all_actors
                 if not role_allows_action(a.role, AiChatAction.note_create)), None,
            )
            assert reviewer is not None, "夹具里没有无笔记权限的角色，拒绝判据会空跑"
            session, (msg,) = await _seed_global(fx, reviewer.id)
            host = await _authorized(fx, reviewer.user, GLOBAL, AiChatAction.history)
            for kw in ({"target_project_id": fx.project_a.id},
                       {"target_folder_id": fx.folder_public.id}):
                await self._expect(fx, reviewer, host, [msg.id], "action_denied", **kw)
            await _assert_no_side_effects(fx, reviewer, session.id)

        run_with_fixture(scenario)

    def test_replies_from_two_sessions_are_rejected(self):
        async def scenario(fx: AccessFixture, _sql):
            actor = await _pick(fx, _wp_ref(fx), AiChatAction.note_create)
            g_session, (g_msg,) = await _seed_global(fx, actor.id)
            w_session, (w_msg,) = await _seed(
                fx, actor.id, host_type=HostType.workpaper, host_id=str(fx.wp_d_file.id),
                project_id=fx.project_a.id,
            )
            host = await _authorized(fx, actor.user, GLOBAL, AiChatAction.history)
            await self._expect(
                fx, actor, host, [g_msg.id, w_msg.id], "mixed_sessions",
                target_project_id=fx.project_a.id,
            )
            await _assert_no_side_effects(fx, actor, g_session.id)
            await _assert_no_side_effects(fx, actor, w_session.id)

        run_with_fixture(scenario)

    def test_messages_of_another_user_are_not_found(self):
        async def scenario(fx: AccessFixture, _sql):
            actor = _note_creator(fx)
            other = next(a for a in fx.all_actors if a.id != actor.id)
            _s, (foreign,) = await _seed_global(fx, other.id)
            host = await _authorized(fx, actor.user, GLOBAL, AiChatAction.history)
            await self._expect(
                fx, actor, host, [foreign.id], "messages_not_found",
                target_project_id=fx.project_a.id,
            )

        run_with_fixture(scenario)
