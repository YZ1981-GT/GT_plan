# Feature: dsh-agent-panel-integration — Task 1 ResourceAccessResolver 行为守卫
"""公共资源权限策略与 ``ResourceAccessResolver`` 的行为守卫。

Requirements: 2.1, 2.2, 2.4, 2.5, 2.6, 2.7, 2.8
Properties:
  - **Property 1（授权拒绝前零读取）**：对任意无权用户与任意 HostRef，授权拒绝发生后，
    资源 loader、正文 SQL、索引搜索和 label serializer 的调用次数均为 0。
    **Validates: Requirements 2.1, 2.5, 2.8**
  - **Property 3（五角色权限交集）**：五角色 × 跨项目 × ``scope_cycles`` ×
    private/project_group 的生成矩阵，其实际允许集合恒等于已有权限服务决策的交集，
    AI 模块不产生额外允许项。
    **Validates: Requirements 2.2, 2.6, 2.7**
  - **Property 4（全端点授权一致性）**：mention/history/clear/adopt 对同一资源/动作返回
    一致授权结果；直接 ID 不得绕过搜索可见性。
    **Validates: Requirements 2.4**

判据一律落在**真实执行**上：真实 PG 数据、真实 ``gate_wp`` / ``VisibilityQueryService`` /
``KnowledgeAccessPolicy`` 决策、真实路由函数调用、真实 SQL 语句流（``before_cursor_execute``
捕获）与真实 loader 调用计数。不使用"源码里出现某符号"作为能力已接通的证据。
"""

from __future__ import annotations

import re
from dataclasses import fields as dataclass_fields
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.ai_chat.access import AI_ENTRY_FAMILY, ResourceAccessResolver
from app.services.ai_chat.adopt import AdoptOutcome
from app.services.ai_chat.contracts import (
    ACTION_CAPABILITIES,
    GLOBAL_KNOWLEDGE_HOST_ID,
    READ_CLASS_ACTIONS,
    WRITE_CLASS_ACTIONS,
    AccessDecision,
    AiChatAction,
    AiChatDenialCode,
    HostRef,
    HostType,
    ResourceType,
)
from app.services.evidence_governance.role_capability_contract import CAPABILITY_MATRIX
from app.services.knowledge_access_policy import KnowledgeAccessPolicy
from app.services.wp_visibility.denial import (
    EXTERNAL_NOT_FOUND_DETAIL,
    ExternalNotFound,
)
from app.services.wp_visibility.role_classifier import VisibilityRoleClassifier
from app.services.wp_visibility.visibility_query import VisibilityQueryService

from ._fixtures import (
    AUDIT_ROLES,
    IS_PG,
    IN_SCOPE_CYCLE,
    OUT_OF_SCOPE_CYCLE,
    AccessFixture,
    RecordingDenialResponder,
    run_with_fixture,
)

pytestmark = pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (AI 授权矩阵)")


# ---------------------------------------------------------------------------
# 判据辅助：从**底层权限服务**独立重算期望值（不复用 AI 模块的判定函数）
# ---------------------------------------------------------------------------

def _role_dimension(role: str, action: AiChatAction) -> bool:
    """角色动作上界，直接从平台冻结的 ``CAPABILITY_MATRIX`` 重算。

    读类动作（capability 空集）只要求角色是矩阵已登记 actor；写类动作要求映射的每个
    capability 在矩阵中为 allowed/conditional。
    """
    row = CAPABILITY_MATRIX.get(role)
    if row is None:
        return False
    caps = ACTION_CAPABILITIES[action]
    if not caps:
        return True
    return all(row.get(cap, (None, None))[0] is not None
               and row[cap][0].value in ("allowed", "conditional")
               for cap in caps)


async def _wp_visible_via_platform_services(
    session, user, project_id, wp_index_id
) -> bool:
    """底稿资源维度：平台既有角色分类 + AccessGrant 查询（与 AI 模块无关）。"""
    ctx = await VisibilityRoleClassifier(session).classify(user, project_id)
    grants = await VisibilityQueryService(session).grants_for_wp_index(ctx, wp_index_id)
    return bool(grants)


async def _folder_readable_via_policy(session, user, folder_id) -> bool:
    subject = await KnowledgeAccessPolicy.resolve_subject(session, user)
    folder = await KnowledgeAccessPolicy.load_folder_permission(session, folder_id)
    return folder is not None and KnowledgeAccessPolicy.can_read(subject, folder)


async def _document_readable_via_policy(session, user, doc_id) -> bool:
    subject = await KnowledgeAccessPolicy.resolve_subject(session, user)
    loaded = await KnowledgeAccessPolicy.load_document_permission(session, doc_id)
    if loaded is None:
        return False
    document, folder = loaded
    return KnowledgeAccessPolicy.can_read_document(subject, document, folder)


#: 敏感读取的 SQL 指纹：label / 摘要 / 正文 / 索引。命中任一即说明拒绝晚于读取。
_SENSITIVE_SQL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("parsed_data", r"\bparsed_data\b"),
    ("content_text", r"\bcontent_text\b"),
    ("content_summary", r"\bcontent_summary\b"),
    ("knowledge_index", r"\bknowledge_index\b"),
    ("wp_name", r"\bwp_name\b"),
    ("project_label", r"projects\.name|projects\.client_name"),
    ("knowledge_label", r"knowledge_documents\.name|knowledge_folders\.name"),
    ("chat_message_body", r"ai_chat_message\b"),
)


def _sensitive_hits(sql_log: list[str]) -> list[str]:
    hits: list[str] = []
    for statement in sql_log:
        for name, pattern in _SENSITIVE_SQL_PATTERNS:
            if re.search(pattern, statement, re.IGNORECASE):
                hits.append(f"{name} :: {statement[:160]}")
    return hits


def _resolver(fx: AccessFixture) -> ResourceAccessResolver:
    return ResourceAccessResolver(fx.session, responder=fx.responder)


# ===========================================================================
# Property 1 — 授权拒绝前零读取
# ===========================================================================

class TestProperty1DenyBeforeRead:
    """**Validates: Requirements 2.1, 2.5, 2.8**"""

    def test_denied_host_emits_no_sensitive_sql(self):
        """五角色对跨项目 / 越出 scope 的底稿被拒时，SQL 流中不含 label/摘要/正文/索引读取。"""

        async def scenario(fx: AccessFixture, sql_log: list[str]):
            resolver = _resolver(fx)
            for actor in fx.all_actors:
                for wp, why in ((fx.wp_other, "跨项目"), (fx.wp_e, "跨循环")):
                    sql_log.clear()
                    decision = await resolver.authorize_host(
                        actor.user,
                        HostRef(type=HostType.workpaper, id=str(wp.id)),
                        AiChatAction.read,
                    )
                    assert decision.allowed is False, (
                        f"{actor.label} 竟然可以访问{why}底稿 {wp.wp_code}"
                    )
                    hits = _sensitive_hits(sql_log)
                    assert not hits, (
                        f"{actor.label} 被拒（{why}）却已读取敏感字段：{hits}"
                    )

        run_with_fixture(scenario, capture_sql=True)

    def test_denied_knowledge_emits_no_label_or_body_sql(self):
        """无权知识文档/文件夹被拒时，不读 name / content_text / content_summary。"""

        async def scenario(fx: AccessFixture, sql_log: list[str]):
            resolver = _resolver(fx)
            host = await resolver.authorize_host(
                fx.actor("manager").user,
                HostRef(type=HostType.global_knowledge, id=GLOBAL_KNOWLEDGE_HOST_ID),
            )
            assert host.allowed is True

            denied_targets = (
                (ResourceType.knowledge_folder, fx.folder_private_auditor.id),
                (ResourceType.knowledge_folder, fx.folder_group_b.id),
                (ResourceType.knowledge_doc, fx.doc_private_auditor.id),
                (ResourceType.knowledge_doc, fx.doc_group_b.id),
                (ResourceType.knowledge_doc, uuid4()),  # 不存在
            )
            for resource_type, rid in denied_targets:
                sql_log.clear()
                decision = await resolver.authorize_resource(
                    fx.actor("manager").user, host, resource_type, str(rid),
                    AiChatAction.read,
                )
                assert decision.allowed is False, f"{resource_type.value}/{rid} 竟被放行"
                hits = _sensitive_hits(sql_log)
                assert not hits, f"{resource_type.value}/{rid} 被拒却已读敏感字段：{hits}"

        run_with_fixture(scenario, capture_sql=True)

    def test_denied_decision_and_external_response_are_non_enumerable(self):
        """拒绝决策结构上不含 label/名称/摘要；对外响应恒为不可枚举 404。"""
        field_names = {f.name for f in dataclass_fields(AccessDecision)}
        leaky = {
            n for n in field_names
            if any(tok in n for tok in ("label", "name", "excerpt", "summary", "content"))
        }
        assert not leaky, f"AccessDecision 含可泄露字段: {leaky}"

        async def scenario(fx: AccessFixture, _sql):
            resolver = _resolver(fx)
            with pytest.raises(ExternalNotFound) as exc:
                await resolver.enforce_host(
                    fx.actor("qc").user,
                    HostRef(type=HostType.workpaper, id=str(fx.wp_other_file.id)),
                    AiChatAction.read,
                )
            assert exc.value.status_code == 404
            assert exc.value.detail == EXTERNAL_NOT_FOUND_DETAIL
            body = str(exc.value.detail)
            assert fx.wp_other.wp_code not in body
            assert fx.project_b.name not in body

        run_with_fixture(scenario)

    def test_denial_audit_records_internal_reason_without_label(self):
        """内部写 denial audit：真实拒绝码可追溯，detail 不含 label / 项目名 / 正文摘要。"""

        async def scenario(fx: AccessFixture, _sql):
            responder = RecordingDenialResponder()
            resolver = ResourceAccessResolver(fx.session, responder=responder)
            with pytest.raises(ExternalNotFound):
                await resolver.enforce_host(
                    fx.actor("auditor").user,
                    HostRef(type=HostType.workpaper, id=str(fx.wp_other_file.id)),
                    AiChatAction.read,
                    entrypoint="ai_chat.doc_chat",
                )
            assert len(responder.records) == 1, "拒绝必须且只能写一条 denial audit"
            record = responder.records[0]
            assert record["entry_family"] == AI_ENTRY_FAMILY
            assert record["entrypoint"] == "ai_chat.doc_chat"
            assert record["actor_user_id"] == fx.actor("auditor").id
            assert record["detail"]["ai_denial_code"] == (
                AiChatDenialCode.access_denied.value
            )
            assert record["detail"]["resource_type"] == ResourceType.workpaper.value
            serialized = str(record)
            for secret in (fx.wp_other.wp_code, fx.wp_other.wp_name, fx.project_b.name):
                assert secret not in serialized, f"denial audit 泄露了 {secret!r}"

        run_with_fixture(scenario)

    def test_endpoint_denies_before_any_context_loader_runs(self):
        """真实端点：拒绝时 ContextBuilder 的 loader 调用计数恒为 0；允许时必 > 0。

        允许路径的正向断言是本用例的反假绿控制：若把 gate 移到 build 之后，拒绝路径的
        计数就会 > 0 而变红；若 loader 从未被调用过，允许路径断言会先变红。
        """
        from app.routers import doc_ai_chat as route_mod
        from app.services.doc_ai_context_builder import ContextBuilder

        async def scenario(fx: AccessFixture, sql_log: list[str]):
            calls: dict[str, int] = {"doc": 0, "knowledge": 0, "summary": 0}
            real_doc = ContextBuilder._get_doc_content
            real_summary = ContextBuilder._get_project_summary

            # Task 2 起 loader 只接受已授权的 AuthorizedHostContext（Req 3.6）。
            async def spy_doc(self, host):
                calls["doc"] += 1
                return await real_doc(self, host)

            async def spy_knowledge(self, **kwargs):
                calls["knowledge"] += 1
                return []

            async def spy_summary(self, project_id):
                calls["summary"] += 1
                return await real_summary(self, project_id)

            outbox_writes: list[dict] = []

            async def fake_write_outbox(_self, **fields):
                outbox_writes.append(fields)

            with patch.object(ContextBuilder, "_get_doc_content", spy_doc), \
                 patch.object(ContextBuilder, "_search_related_knowledge", spy_knowledge), \
                 patch.object(ContextBuilder, "_get_project_summary", spy_summary), \
                 patch(
                     "app.services.wp_visibility.denial.DenialResponder._write_outbox",
                     fake_write_outbox,
                 ):
                # ── 拒绝路径：跨项目底稿 ──
                req_denied = route_mod.DocChatRequest(
                    query="这份底稿有什么风险？",
                    year=2025,
                    project_id=str(fx.project_b.id),
                )
                sql_log.clear()
                with pytest.raises(ExternalNotFound):
                    await route_mod.doc_ai_chat(
                        "workpaper",
                        str(fx.wp_other_file.id),
                        req_denied,
                        fx.session,
                        fx.actor("auditor").user,
                    )
                assert calls == {"doc": 0, "knowledge": 0, "summary": 0}, (
                    f"拒绝后仍调用了上下文 loader: {calls}"
                )
                assert not _sensitive_hits(sql_log), (
                    f"拒绝后仍发出敏感 SQL: {_sensitive_hits(sql_log)}"
                )
                assert outbox_writes, "拒绝必须写内部 denial audit"

                # ── 允许路径：本项目、scope 内、已委派底稿 ──
                req_allowed = route_mod.DocChatRequest(
                    query="这份底稿有什么风险？",
                    year=2025,
                    project_id=str(fx.project_a.id),
                )
                response = await route_mod.doc_ai_chat(
                    "workpaper",
                    str(fx.wp_d_file.id),
                    req_allowed,
                    fx.session,
                    fx.actor("auditor").user,
                )
                assert response is not None
                assert calls["doc"] == 1 and calls["knowledge"] == 1 and calls["summary"] == 1, (
                    f"允许路径未真正读取上下文，零读取断言将失去意义: {calls}"
                )

        run_with_fixture(scenario, capture_sql=True)

    def test_context_build_failure_fails_closed_without_model_call(self):
        """ContextBuilder 异常 → typed error 终止，绝不降级为空上下文继续调用模型（Req 2.8）。"""
        from fastapi import HTTPException

        from app.routers import doc_ai_chat as route_mod
        from app.services.doc_ai_context_builder import ContextBuilder

        async def scenario(fx: AccessFixture, _sql):
            model_calls: list[int] = []

            async def exploding_build(self, **kwargs):
                raise RuntimeError("索引服务不可用")

            async def spy_chat_completion(self, *args, **kwargs):
                model_calls.append(1)
                return []

            with patch.object(ContextBuilder, "build", exploding_build), \
                 patch(
                     "app.services.ai_service.AIService.chat_completion",
                     spy_chat_completion,
                 ):
                with pytest.raises(HTTPException) as exc:
                    await route_mod.doc_ai_chat(
                        "workpaper",
                        str(fx.wp_d_file.id),
                        route_mod.DocChatRequest(
                            query="请复核这份底稿",
                            year=2025,
                            project_id=str(fx.project_a.id),
                        ),
                        fx.session,
                        fx.actor("auditor").user,
                    )
            assert exc.value.status_code == 503
            assert exc.value.detail["code"] == "context_build_failed"
            assert "上下文" in exc.value.detail["message"]
            assert model_calls == [], "上下文构建失败后仍调用了模型"

        run_with_fixture(scenario)

    def test_resolver_internal_failure_fails_closed(self):
        """授权服务内部异常 → 拒绝（Req 2.8），不得放行也不得抛 500。"""

        async def scenario(fx: AccessFixture, _sql):
            class ExplodingClassifier(VisibilityRoleClassifier):
                async def classify(self, current_user, project_id):  # noqa: D401
                    raise RuntimeError("角色分类服务不可用")

            resolver = ResourceAccessResolver(
                fx.session,
                responder=fx.responder,
                classifier=ExplodingClassifier(fx.session),
            )
            decision = await resolver.authorize_host(
                fx.actor("auditor").user,
                HostRef(type=HostType.workpaper, id=str(fx.wp_d_file.id)),
                AiChatAction.read,
            )
            assert decision.allowed is False
            assert decision.denial_code == AiChatDenialCode.resolver_error.value

        run_with_fixture(scenario)

    def test_malformed_and_unsupported_identifiers_fail_closed(self):
        """非法 ID / 未登记宿主 / 未接入资源域一律 fail-closed，且不触发 loader。"""

        async def scenario(fx: AccessFixture, sql_log: list[str]):
            resolver = _resolver(fx)
            user = fx.actor("partner").user

            sql_log.clear()
            bad_id = await resolver.authorize_host(
                user, HostRef(type=HostType.workpaper, id="not-a-uuid")
            )
            assert bad_id.allowed is False
            assert bad_id.denial_code == AiChatDenialCode.invalid_resource_id.value
            assert not sql_log, f"非法 ID 竟触发了查询: {sql_log}"

            host = await resolver.authorize_host(
                user, HostRef(type=HostType.global_knowledge, id=GLOBAL_KNOWLEDGE_HOST_ID)
            )
            for resource_type in (ResourceType.address, ResourceType.attachment):
                decision = await resolver.authorize_resource(
                    user, host, resource_type, str(uuid4()), AiChatAction.read
                )
                assert decision.allowed is False, f"{resource_type.value} 未接入却被放行"
                # address 已接入（Task 23）但无项目绑定 → access_denied；
                # attachment 尚未接入 → unsupported_resource。
                if resource_type is ResourceType.address:
                    assert decision.denial_code == (
                        AiChatDenialCode.access_denied.value
                    )
                else:
                    assert decision.denial_code == (
                        AiChatDenialCode.unsupported_resource.value
                    )

            # 全局知识 sentinel 必须精确匹配，不接受空串/任意串伪装
            for fake in ("", "null", str(uuid4())):
                decision = await resolver.authorize_host(
                    user, HostRef(type=HostType.global_knowledge, id=fake)
                )
                assert decision.allowed is False

        run_with_fixture(scenario, capture_sql=True)

    def test_resource_authorization_requires_authorized_host(self):
        """未授权宿主 / 他人宿主决策不得复用（防"先拿资源、后补宿主"旁路）。"""

        async def scenario(fx: AccessFixture, _sql):
            resolver = _resolver(fx)
            denied_host = await resolver.authorize_host(
                fx.actor("qc").user,
                HostRef(type=HostType.workpaper, id=str(fx.wp_other_file.id)),
            )
            assert denied_host.allowed is False
            leaked = await resolver.authorize_resource(
                fx.actor("qc").user,
                denied_host,
                ResourceType.knowledge_doc,
                str(fx.doc_public.id),
                AiChatAction.read,
            )
            assert leaked.allowed is False

            manager_host = await resolver.authorize_host(
                fx.actor("manager").user,
                HostRef(type=HostType.global_knowledge, id=GLOBAL_KNOWLEDGE_HOST_ID),
            )
            assert manager_host.allowed is True
            # 用 manager 的宿主决策去替 auditor 授权 → 必须拒绝
            cross = await resolver.authorize_resource(
                fx.actor("auditor").user,
                manager_host,
                ResourceType.knowledge_doc,
                str(fx.doc_public.id),
                AiChatAction.read,
            )
            assert cross.allowed is False

        run_with_fixture(scenario)


# ===========================================================================
# Property 3 — 五角色权限交集
# ===========================================================================

class TestProperty3RoleIntersection:
    """**Validates: Requirements 2.2, 2.6, 2.7**"""

    def test_workpaper_matrix_equals_platform_service_intersection(self):
        """五角色 × {本项目 scope 内 / 越出 scope / 跨项目} × {read, adopt} 全矩阵。

        期望值由平台既有 ``VisibilityRoleClassifier`` + ``VisibilityQueryService`` +
        冻结 capability 矩阵独立重算；resolver 的允许集合必须**恒等**于三者交集。
        """

        async def scenario(fx: AccessFixture, _sql):
            resolver = _resolver(fx)
            targets = (
                ("scope 内本项目", fx.wp_d, fx.wp_d_file, fx.project_a.id),
                ("越出 scope", fx.wp_e, fx.wp_e_file, fx.project_a.id),
                ("跨项目", fx.wp_other, fx.wp_other_file, fx.project_b.id),
            )
            checked = 0
            for actor in fx.all_actors:
                for label, wp, wp_file, owner_project in targets:
                    resource_ok = await _wp_visible_via_platform_services(
                        fx.session, actor.user, owner_project, wp.id
                    )
                    for action in (AiChatAction.read, AiChatAction.adopt):
                        expected = resource_ok and _role_dimension(actor.role, action)
                        decision = await resolver.authorize_host(
                            actor.user,
                            HostRef(type=HostType.workpaper, id=str(wp_file.id)),
                            action,
                        )
                        assert decision.allowed is expected, (
                            f"{actor.label} / {label} / {action.value}: "
                            f"resolver={decision.allowed} 期望={expected} "
                            f"(资源维度={resource_ok}, 角色维度="
                            f"{_role_dimension(actor.role, action)})"
                        )
                        checked += 1
            assert checked == len(AUDIT_ROLES) * len(targets) * 2 == 30

        run_with_fixture(scenario)

    def test_knowledge_matrix_equals_policy_intersection(self):
        """五角色 × {public / project_group(本) / project_group(他) / private} × 文档继承与显式。"""

        async def scenario(fx: AccessFixture, _sql):
            resolver = _resolver(fx)
            folders = (
                ("public", fx.folder_public),
                ("project_group 本项目", fx.folder_group_a),
                ("project_group 他项目", fx.folder_group_b),
                ("private(auditor)", fx.folder_private_auditor),
            )
            docs = (
                ("继承 public", fx.doc_public),
                ("继承 project_group 本项目", fx.doc_group_a),
                ("继承 project_group 他项目", fx.doc_group_b),
                ("继承 private(auditor)", fx.doc_private_auditor),
                ("显式 private(manager)", fx.doc_private_explicit),
            )
            for actor in fx.all_actors:
                host = await resolver.authorize_host(
                    actor.user,
                    HostRef(
                        type=HostType.global_knowledge, id=GLOBAL_KNOWLEDGE_HOST_ID
                    ),
                )
                assert host.allowed is True, f"{actor.label} 无法进入受限全局知识模式"

                for label, folder in folders:
                    expected_read = await _folder_readable_via_policy(
                        fx.session, actor.user, folder.id
                    )
                    decision = await resolver.authorize_resource(
                        actor.user, host, ResourceType.knowledge_folder,
                        str(folder.id), AiChatAction.read,
                    )
                    assert decision.allowed is expected_read, (
                        f"{actor.label} 读 {label} 文件夹: resolver={decision.allowed} "
                        f"policy={expected_read}"
                    )
                    # 写知识资产：资源级创建权 ∩ 角色上界
                    expected_write = expected_read and _role_dimension(
                        actor.role, AiChatAction.note_create
                    )
                    write = await resolver.authorize_resource(
                        actor.user, host, ResourceType.knowledge_folder,
                        str(folder.id), AiChatAction.note_create,
                    )
                    assert write.allowed is expected_write, (
                        f"{actor.label} 在 {label} 文件夹创建笔记: "
                        f"resolver={write.allowed} 期望={expected_write}"
                    )

                for label, doc in docs:
                    expected_read = await _document_readable_via_policy(
                        fx.session, actor.user, doc.id
                    )
                    decision = await resolver.authorize_resource(
                        actor.user, host, ResourceType.knowledge_doc,
                        str(doc.id), AiChatAction.read,
                    )
                    assert decision.allowed is expected_read, (
                        f"{actor.label} 读 {label} 文档: resolver={decision.allowed} "
                        f"policy={expected_read}"
                    )

        run_with_fixture(scenario)

    def test_private_and_project_group_boundaries_are_real(self):
        """矩阵不是全 True / 全 False：private 与 project_group 的差异必须真实存在。"""

        async def scenario(fx: AccessFixture, _sql):
            resolver = _resolver(fx)
            auditor = fx.actor("auditor").user
            manager = fx.actor("manager").user
            host_auditor = await resolver.authorize_host(
                auditor, HostRef(type=HostType.global_knowledge, id=GLOBAL_KNOWLEDGE_HOST_ID)
            )
            host_manager = await resolver.authorize_host(
                manager, HostRef(type=HostType.global_knowledge, id=GLOBAL_KNOWLEDGE_HOST_ID)
            )

            async def can_read(host, user, resource_type, rid) -> bool:
                d = await resolver.authorize_resource(
                    user, host, resource_type, str(rid), AiChatAction.read
                )
                return d.allowed

            # private：仅创建者
            assert await can_read(
                host_auditor, auditor, ResourceType.knowledge_folder,
                fx.folder_private_auditor.id,
            ) is True
            assert await can_read(
                host_manager, manager, ResourceType.knowledge_folder,
                fx.folder_private_auditor.id,
            ) is False
            # 显式 private 文档挂在 public 文件夹下 → 文档级权限优先，非创建者不可见
            assert await can_read(
                host_manager, manager, ResourceType.knowledge_doc,
                fx.doc_private_explicit.id,
            ) is True
            assert await can_read(
                host_auditor, auditor, ResourceType.knowledge_doc,
                fx.doc_private_explicit.id,
            ) is False
            # project_group：本项目成员可见、他项目不可见
            assert await can_read(
                host_auditor, auditor, ResourceType.knowledge_folder,
                fx.folder_group_a.id,
            ) is True
            assert await can_read(
                host_auditor, auditor, ResourceType.knowledge_folder,
                fx.folder_group_b.id,
            ) is False
            # public 对所有人可见
            assert await can_read(
                host_auditor, auditor, ResourceType.knowledge_folder,
                fx.folder_public.id,
            ) is True

        run_with_fixture(scenario)

    def test_qc_and_eqcr_are_read_only_upper_bound(self):
        """QC / EQCR 默认只读：在**有读权限**的资源上，写类动作依然全部被拒。"""

        async def scenario(fx: AccessFixture, _sql):
            resolver = _resolver(fx)
            for role in ("qc", "eqcr"):
                actor = fx.actor(role)
                read_host = await resolver.authorize_host(
                    actor.user,
                    HostRef(type=HostType.workpaper, id=str(fx.wp_d_file.id)),
                    AiChatAction.read,
                )
                assert read_host.allowed is True, f"{actor.label} 应能读 scope 内底稿"
                assert IN_SCOPE_CYCLE in read_host.cycle_scope
                for action in sorted(WRITE_CLASS_ACTIONS, key=lambda a: a.value):
                    decision = await resolver.authorize_host(
                        actor.user,
                        HostRef(type=HostType.workpaper, id=str(fx.wp_d_file.id)),
                        action,
                    )
                    assert decision.allowed is False, (
                        f"{actor.label} 竟可执行写类动作 {action.value}"
                    )
                    assert decision.denial_code == (
                        AiChatDenialCode.role_capability_denied.value
                    )
                assert not (
                    {a.value for a in WRITE_CLASS_ACTIONS} & read_host.allowed_actions
                ), f"{actor.label} 的 allowed_actions 含写类动作"

            # 对照：审计助理 / 现场经理 / 业务合伙人 在同一资源上写类动作被允许
            for role in ("auditor", "manager", "partner"):
                actor = fx.actor(role)
                decision = await resolver.authorize_host(
                    actor.user,
                    HostRef(type=HostType.workpaper, id=str(fx.wp_d_file.id)),
                    AiChatAction.adopt,
                )
                assert decision.allowed is True, f"{actor.label} 应可发起采纳"

        run_with_fixture(scenario)

    def test_scope_cycles_returned_for_downstream_trimming(self):
        """允许决策必须回传 ``scope_cycles`` 上界，供 mention/RAG/MCP 同步裁剪（Req 2.6）。"""

        async def scenario(fx: AccessFixture, _sql):
            resolver = _resolver(fx)
            for actor in fx.all_actors:
                decision = await resolver.authorize_host(
                    actor.user,
                    HostRef(type=HostType.workpaper, id=str(fx.wp_d_file.id)),
                    AiChatAction.read,
                )
                assert decision.allowed is True, f"{actor.label} 应能读 scope 内底稿"
                assert decision.cycle_scope == frozenset({IN_SCOPE_CYCLE})
                assert decision.scope_unbounded is False
                assert decision.project_id == fx.project_a.id
                assert OUT_OF_SCOPE_CYCLE not in decision.cycle_scope

        run_with_fixture(scenario)

    def test_note_and_report_hosts_require_project_membership(self):
        """附注 / 报表宿主：项目成员可用，非成员被拒（跨项目边界）。

        ``host_id`` 按宿主的稳定标识形态取值（Task 2 / Req 3.2）：附注是 instance UUID，
        报表是 report type 字面量（报表实例由 project+year+type 确定，没有 instance UUID）。
        """

        async def scenario(fx: AccessFixture, _sql):
            resolver = _resolver(fx)
            for host_type, host_id_factory in (
                (HostType.note, lambda: str(uuid4())),
                (HostType.report, lambda: "balance_sheet"),
            ):
                for actor in fx.all_actors:
                    ok = await resolver.authorize_host(
                        actor.user,
                        HostRef(
                            type=host_type,
                            id=host_id_factory(),
                            project_id_assertion=fx.project_a.id,
                        ),
                        AiChatAction.read,
                    )
                    assert ok.allowed is True, f"{actor.label} 应能在本项目 {host_type.value} 对话"
                    assert ok.project_id == fx.project_a.id

                denied = await resolver.authorize_host(
                    fx.outsider,
                    HostRef(
                        type=host_type,
                        id=host_id_factory(),
                        project_id_assertion=fx.project_a.id,
                    ),
                    AiChatAction.read,
                )
                assert denied.allowed is False, f"非成员竟可在 {host_type.value} 宿主对话"

                # 无项目绑定 → 拒绝（不猜测最近项目，Req 3.4）
                no_project = await resolver.authorize_host(
                    fx.actor("manager").user,
                    HostRef(type=host_type, id=host_id_factory()),
                    AiChatAction.read,
                )
                assert no_project.allowed is False

        run_with_fixture(scenario)

    def test_role_upper_bound_table_matches_requirements_role_table(self):
        """角色动作上界与 Requirements §2 角色表一致（读类全开、QC/EQCR 写类全禁）。"""
        from app.services.ai_chat.contracts import role_allowed_actions

        write_values = {a.value for a in WRITE_CLASS_ACTIONS}
        read_values = {a.value for a in READ_CLASS_ACTIONS}

        for role in ("auditor", "manager", "partner"):
            actions = {a.value for a in role_allowed_actions(role)}
            assert read_values <= actions, f"{role} 缺少读类动作"
            assert write_values <= actions, f"{role} 缺少写类动作"
        for role in ("qc", "eqcr", "readonly"):
            actions = {a.value for a in role_allowed_actions(role)}
            assert read_values <= actions, f"{role} 缺少读类动作"
            assert not (write_values & actions), f"{role} 不应具备写类动作: {actions}"
        # 未知角色 fail-closed
        assert role_allowed_actions("not-a-role") == frozenset()
        assert role_allowed_actions(None) == frozenset()


# ===========================================================================
# Property 4 — 全端点授权一致性
# ===========================================================================

class TestProperty4CrossEndpointConsistency:
    """**Validates: Requirements 2.4**"""

    def test_search_visibility_equals_direct_id_authorization(self):
        """搜索可见集 == 直接 ID 可授权集（不存在"搜索不可见但直接 ID 可读"的旁路）。"""

        async def scenario(fx: AccessFixture, _sql):
            resolver = _resolver(fx)
            wp_ids = [
                str(fx.wp_d_file.id),
                str(fx.wp_e_file.id),
                str(fx.wp_other_file.id),
            ]
            doc_ids = [
                str(fx.doc_public.id),
                str(fx.doc_group_a.id),
                str(fx.doc_group_b.id),
                str(fx.doc_private_auditor.id),
                str(fx.doc_private_explicit.id),
            ]
            for actor in fx.all_actors:
                # 底稿：批量可见集（make_bulk_visible_filter）vs 逐个宿主授权
                host_scope = await resolver.authorize_host(
                    actor.user,
                    HostRef(type=HostType.workpaper, id=str(fx.wp_d_file.id)),
                    AiChatAction.read,
                )
                visible = set(
                    await resolver.filter_visible_resources(
                        actor.user, host_scope, ResourceType.workpaper, wp_ids,
                        AiChatAction.search,
                    )
                )
                direct = set()
                for wid in wp_ids:
                    d = await resolver.authorize_host(
                        actor.user,
                        HostRef(type=HostType.workpaper, id=wid),
                        AiChatAction.search,
                    )
                    if d.allowed:
                        direct.add(wid)
                assert visible == direct, (
                    f"{actor.label} 底稿搜索可见集与直接 ID 授权不一致: "
                    f"搜索={visible} 直接={direct}"
                )

                # 知识文档：搜索过滤 vs 直接 ID
                host_global = await resolver.authorize_host(
                    actor.user,
                    HostRef(type=HostType.global_knowledge, id=GLOBAL_KNOWLEDGE_HOST_ID),
                )
                k_visible = set(
                    await resolver.filter_visible_resources(
                        actor.user, host_global, ResourceType.knowledge_doc, doc_ids,
                        AiChatAction.search,
                    )
                )
                k_direct = {
                    did
                    for did in doc_ids
                    if (
                        await resolver.authorize_resource(
                            actor.user, host_global, ResourceType.knowledge_doc, did,
                            AiChatAction.search,
                        )
                    ).allowed
                }
                assert k_visible == k_direct, (
                    f"{actor.label} 知识搜索可见集与直接 ID 授权不一致: "
                    f"搜索={k_visible} 直接={k_direct}"
                )

        run_with_fixture(scenario)

    def test_all_ai_endpoints_share_the_same_decision(self):
        """chat / history / clear / adopt 四端点与 resolver 决策逐一一致。

        对每个 (角色, 底稿) 组合：先取 resolver 对该端点动作的决策，再真实调用路由函数，
        断言"允许 → 不抛 404""拒绝 → 抛不可枚举 404"。QC/EQCR 在同一底稿上 read/history/
        clear 允许而 adopt 拒绝，正是"同一资源、不同动作、同一决策面"的证据。
        """
        from app.routers import doc_ai_chat as route_mod
        from app.services.doc_ai_context_builder import ContextBuilder

        async def scenario(fx: AccessFixture, _sql):
            resolver = _resolver(fx)

            async def noop_knowledge(self, **kwargs):
                return []

            async def fake_write_outbox(_self, **fields):
                return None

            original_commit = fx.session.commit
            commits: list[int] = []

            async def fake_commit():
                commits.append(1)

            # 本判据只测**授权面**（允许→非 404 / 拒绝→404）。采纳的下游写入（权威正文、
            # 收据幂等、fail-closed 回滚）自 Task 7 起由
            # ``test_task7_adopt_fail_closed.py`` 在真实 PG 上守卫，故此处把服务层整体
            # 替身掉 —— 否则本测试会连带依赖确认流写入细节，一改就假红。
            adopt_service = AsyncMock(
                return_value=AdoptOutcome(
                    ai_content_log_id=uuid4(),
                    content_hash="h" * 64,
                    message_id=uuid4(),
                    receipt_id=uuid4(),
                    idempotent_replay=False,
                )
            )
            with patch.object(ContextBuilder, "_search_related_knowledge", noop_knowledge), \
                 patch(
                     "app.services.wp_visibility.denial.DenialResponder._write_outbox",
                     fake_write_outbox,
                 ), \
                 patch("app.routers.doc_ai_chat.adopt_message", adopt_service):
                fx.session.commit = fake_commit  # type: ignore[method-assign]
                try:
                    for actor in fx.all_actors:
                        for wp, wp_file, project in (
                            (fx.wp_d, fx.wp_d_file, fx.project_a),
                            (fx.wp_e, fx.wp_e_file, fx.project_a),
                            (fx.wp_other, fx.wp_other_file, fx.project_b),
                        ):
                            await _assert_endpoint_matrix(
                                resolver, route_mod, fx, actor, wp, wp_file, project
                            )
                finally:
                    fx.session.commit = original_commit  # type: ignore[method-assign]

        run_with_fixture(scenario)


async def _assert_endpoint_matrix(
    resolver, route_mod, fx, actor, wp, wp_file, project
) -> None:
    """对单个 (角色, 底稿) 组合逐端点比对 resolver 决策与真实路由行为。"""
    host_id = str(wp_file.id)
    project_id = str(project.id)

    cases = (
        (
            AiChatAction.read,
            lambda: route_mod.doc_ai_chat(
                "workpaper",
                host_id,
                route_mod.DocChatRequest(
                    query="请复核这份底稿", year=2025, project_id=project_id
                ),
                fx.session,
                actor.user,
            ),
        ),
        (
            AiChatAction.history,
            lambda: route_mod.get_chat_history(
                "workpaper", host_id, project_id, fx.session, actor.user
            ),
        ),
        (
            AiChatAction.clear,
            lambda: route_mod.clear_chat_history(
                "workpaper", host_id, project_id, fx.session, actor.user
            ),
        ),
        (
            AiChatAction.adopt,
            lambda: route_mod.adopt_ai_content(
                # Task 7 契约：只提交服务端消息 ID + 宿主 + 幂等键，**没有** content 字段
                route_mod.AdoptRequest(
                    message_id=uuid4(),
                    host=route_mod.AdoptHostRef(
                        type="workpaper", id=host_id, project_id=project_id
                    ),
                    idempotency_key=uuid4(),
                ),
                fx.session,
                actor.user,
            ),
        ),
    )

    for action, invoke in cases:
        decision = await resolver.authorize_host(
            actor.user, HostRef(type=HostType.workpaper, id=host_id), action
        )
        if decision.allowed:
            result = await invoke()
            assert result is not None, (
                f"{actor.label} / {wp.wp_code} / {action.value}: 决策允许但端点无返回"
            )
        else:
            with pytest.raises(ExternalNotFound):
                await invoke()


# ===========================================================================
# 知识库 tree / list / read / create 四类入口共用公共 policy
# ===========================================================================

class TestKnowledgeRoutesConsumePublicPolicy:
    """**Validates: Requirements 2.1, 2.2, 2.5**

    Task 1 要求"tree/list/read/create 都显式接收 current user 与 project scope"。
    此处不检查源码里是否出现某个符号，而是真实调用四个 route 函数，断言可见集与写权限
    确实随当前用户变化 —— 旧实现"不传 subject 就不过滤"会让本类多条断言立刻变红。
    """

    def test_tree_hides_invisible_folders_per_user(self):
        async def scenario(fx: AccessFixture, _sql):
            from app.routers import knowledge_folders as kb_routes

            auditor_tree = await kb_routes.get_folder_tree(fx.session, fx.actor("auditor").user)
            manager_tree = await kb_routes.get_folder_tree(fx.session, fx.actor("manager").user)
            outsider_tree = await kb_routes.get_folder_tree(fx.session, fx.outsider)

            def ids(tree) -> set[str]:
                return {node["id"] for node in tree}

            auditor_ids, manager_ids, outsider_ids = (
                ids(auditor_tree), ids(manager_tree), ids(outsider_tree)
            )

            public_id = str(fx.folder_public.id)
            group_a_id = str(fx.folder_group_a.id)
            group_b_id = str(fx.folder_group_b.id)
            private_id = str(fx.folder_private_auditor.id)

            for who, seen in (
                ("auditor", auditor_ids), ("manager", manager_ids), ("outsider", outsider_ids)
            ):
                assert public_id in seen, f"{who} 看不到 public 文件夹"

            # private：只有创建者（auditor）看得到
            assert private_id in auditor_ids
            assert private_id not in manager_ids
            assert private_id not in outsider_ids
            # project_group：按成员关系裁剪
            assert group_a_id in auditor_ids and group_a_id in manager_ids
            assert group_a_id not in outsider_ids
            assert group_b_id in outsider_ids
            assert group_b_id not in auditor_ids and group_b_id not in manager_ids

        run_with_fixture(scenario)

    def test_list_documents_denies_before_reading_names_or_bodies(self):
        async def scenario(fx: AccessFixture, sql_log: list[str]):
            from app.routers import knowledge_folders as kb_routes

            # 无权文件夹：返回空列表，且不读取任何文档 name / content_text
            sql_log.clear()
            docs = await kb_routes.list_documents(
                fx.folder_private_auditor.id, fx.session, fx.actor("manager").user
            )
            assert docs == []
            hits = [h for h in _sensitive_hits(sql_log) if "knowledge" in h or "content" in h]
            assert not hits, f"无权 list_documents 竟读取了 label/正文: {hits}"

            # 有权文件夹：创建者可见自己的私有文件夹内容（证明上面不是恒空）
            owner_docs = await kb_routes.list_documents(
                fx.folder_private_auditor.id, fx.session, fx.actor("auditor").user
            )
            assert len(owner_docs) == 1
            assert owner_docs[0]["id"] == str(fx.doc_private_auditor.id)

        run_with_fixture(scenario, capture_sql=True)

    def test_create_document_requires_knowledge_write_permission(self):
        async def scenario(fx: AccessFixture, _sql):
            from app.routers import knowledge_folders as kb_routes

            payload = kb_routes.DocumentCreateRequest(name="ai-note.md", content_text="正文")

            # 无权文件夹（他人 private）→ 不可枚举 404
            with pytest.raises(ExternalNotFound):
                await kb_routes.create_document(
                    fx.folder_private_auditor.id,
                    payload,
                    fx.session,
                    fx.actor("manager").user,
                )
            # 不存在的文件夹 → 同构 404（不泄露存在性）
            with pytest.raises(ExternalNotFound):
                await kb_routes.create_document(
                    uuid4(), payload, fx.session, fx.actor("manager").user
                )
            # 他项目 project_group 文件夹 → 404
            with pytest.raises(ExternalNotFound):
                await kb_routes.create_document(
                    fx.folder_group_b.id, payload, fx.session, fx.actor("manager").user
                )

        run_with_fixture(scenario)

    def test_anonymous_subject_sees_no_restricted_knowledge(self):
        """匿名主体（无有效身份）：private / project_group 恒不可见，创建权恒被拒。"""

        async def scenario(fx: AccessFixture, _sql):
            from app.services.knowledge_access_policy import ANONYMOUS_SUBJECT
            from app.services.knowledge_folder_service import KnowledgeFolderService

            folders = await KnowledgeFolderService(fx.session).list_folders(
                ANONYMOUS_SUBJECT, parent_id=None
            )
            visible = {f.id for f in folders}
            assert fx.folder_public.id in visible
            assert fx.folder_private_auditor.id not in visible
            assert fx.folder_group_a.id not in visible
            assert fx.folder_group_b.id not in visible

            private_folder = await KnowledgeAccessPolicy.load_folder_permission(
                fx.session, fx.folder_private_auditor.id
            )
            assert private_folder is not None
            assert KnowledgeAccessPolicy.can_create_in_folder(
                ANONYMOUS_SUBJECT, private_folder
            ) is False
            public_folder = await KnowledgeAccessPolicy.load_folder_permission(
                fx.session, fx.folder_public.id
            )
            assert public_folder is not None
            assert KnowledgeAccessPolicy.can_create_in_folder(
                ANONYMOUS_SUBJECT, public_folder
            ) is False

        run_with_fixture(scenario)
