# Feature: dsh-agent-panel-integration — Task 2 HostContextResolver 行为守卫
"""可信 ``HostContextResolver`` 与全部宿主契约的行为守卫。

Requirements: 2.3, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
Properties:
  - **Property 2（HostContext 断言一致性）**：对任意伪造的 client project/year/doc
    assertion，只要与服务端反查结果不一致，请求即返回 ``host_context_mismatch``，
    且不创建 session/run。
    **Validates: Requirements 2.3, 3.3**
  - **Property 5（宿主加载器唯一映射）**：每种 HostType 均调用唯一对应的业务 loader；
    note/report/knowledge_folder 输入不会调用 WorkingPaper loader，空 project ID 不会
    被构造成有效项目 HostContext。
    **Validates: Requirements 3.1, 3.2, 3.4, 3.7**

判据一律落在**真实执行**上：真实 PostgreSQL 数据、真实 ORM 查询、**真实 SQL 语句流**
（``before_cursor_execute`` 捕获）、**真实 loader 调用计数**（对每个宿主 loader 打桩计数）
以及**真实会话表行数差**（伪造断言后 ``ai_chat_session`` 必须零新增）。

不使用"源码里出现某符号"作为能力已接通的证据 —— 例如 Property 5 不检查
``_get_note_content`` 这个名字是否存在，而是断言"note 宿主取正文时，SQL 流里出现
``disclosure_notes`` 且**绝不出现** ``working_paper``"，并同时断言底稿 loader 的调用计数为 0。
"""

from __future__ import annotations

import re
from uuid import uuid4

import pytest
import sqlalchemy as sa

from app.services.ai_chat.access import ResourceAccessResolver
from app.services.ai_chat.contracts import (
    GLOBAL_KNOWLEDGE_HOST_ID,
    REPORT_HOST_IDS,
    AiChatAction,
    AiChatDenialCode,
    HostRef,
    HostType,
)
from app.services.ai_chat.host_context import (
    GLOBAL_KNOWLEDGE_LABEL,
    HOST_BUSINESS_MODEL,
    AuthorizedHostContext,
    HostContextContractError,
    HostContextDenial,
    HostContextResolver,
)
from app.services.doc_ai_context_builder import ContextBuilder
from app.services.wp_visibility.denial import ExternalNotFound

from ._fixtures import (
    FIXTURE_AUDIT_YEAR,
    FIXTURE_REPORT_TYPE,
    IS_PG,
    AccessFixture,
    RecordingDenialResponder,
    run_with_fixture,
)

pytestmark = pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (AI 宿主反查)")


# ---------------------------------------------------------------------------
# 判据辅助
# ---------------------------------------------------------------------------

def _resolver(fx: AccessFixture) -> HostContextResolver:
    return HostContextResolver(
        fx.session, access=ResourceAccessResolver(fx.session, responder=fx.responder)
    )


def _tables_touched(sql_log: list[str]) -> set[str]:
    """SQL 流里出现过的业务表集合（作为"哪个 loader 真的跑了"的独立证据）。"""
    all_tables = {t for tables in HOST_BUSINESS_MODEL.values() for t in tables}
    touched: set[str] = set()
    for statement in sql_log:
        for table in all_tables:
            if re.search(rf"\b{table}\b", statement, re.IGNORECASE):
                touched.add(table)
    return touched


async def _session_count(fx: AccessFixture) -> int:
    """``ai_chat_session`` 行数（Property 2 的"不创建 session"判据）。"""
    from app.models.ai_models import AIChatSession

    return (
        await fx.session.execute(sa.select(sa.func.count()).select_from(AIChatSession))
    ).scalar_one()


def _host_cases(fx: AccessFixture) -> tuple[tuple[HostType, str, str], ...]:
    """(宿主类型, 稳定 ID, 说明) —— 六个宿主各自的合法输入形态。"""
    return (
        (HostType.workpaper, str(fx.wp_d_file.id), "working paper instance ID"),
        (HostType.note, str(fx.note_a.id), "附注 instance ID"),
        (HostType.report, FIXTURE_REPORT_TYPE, "report type"),
        (HostType.knowledge_doc, str(fx.doc_public.id), "知识文档 ID"),
        (HostType.knowledge_folder, str(fx.folder_public.id), "文件夹 ID"),
        (HostType.global_knowledge, GLOBAL_KNOWLEDGE_HOST_ID, "全局知识 sentinel"),
    )


# ===========================================================================
# Property 5 — 宿主加载器唯一映射
# ===========================================================================

class TestProperty5UniqueHostLoader:
    """**Validates: Requirements 3.1, 3.2, 3.4, 3.7**"""

    def test_each_host_resolves_via_its_own_business_model(self):
        """六个宿主逐一反查：SQL 流只触碰**自己**的业务表，绝不触碰别人的。

        这条判据不看函数名：把 ``HOST_BUSINESS_MODEL`` 当期望值，断言实际 SQL 流命中的
        业务表集合 ⊆ 该宿主自己的表。note/report/knowledge_* 因此不可能悄悄走底稿查询。
        """

        async def scenario(fx: AccessFixture, sql_log: list[str]):
            resolver = _resolver(fx)
            user = fx.actor("manager").user
            checked = 0
            for host_type, host_id, why in _host_cases(fx):
                project_assertion = (
                    None
                    if host_type is HostType.global_knowledge
                    else fx.project_a.id
                )
                sql_log.clear()
                outcome = await resolver.resolve(
                    user,
                    HostRef(
                        type=host_type,
                        id=host_id,
                        project_id_assertion=project_assertion,
                    ),
                    AiChatAction.read,
                )
                assert isinstance(outcome, AuthorizedHostContext), (
                    f"{host_type.value}（{why}）宿主反查失败: {outcome}"
                )
                assert outcome.resource_type is host_type

                touched = _tables_touched(sql_log)
                own = set(HOST_BUSINESS_MODEL[host_type])
                foreign = touched - own
                assert not foreign, (
                    f"{host_type.value} 宿主反查竟触碰了别的业务表: {foreign}"
                    f"（自己的表 = {own or '无'}）"
                )
                if own:
                    assert touched, f"{host_type.value} 宿主反查一条 SQL 都没发（loader 未真跑）"
                checked += 1
            assert checked == len(HostType) == 6

        run_with_fixture(scenario, capture_sql=True)

    def test_note_and_report_never_touch_workpaper_loader(self):
        """附注 / 报表宿主取正文时，底稿 loader 调用计数恒为 0 且 SQL 无 working_paper。

        旧实现把 note/report 转给 ``_get_workpaper_content``（正文恒空而 AI 照常作答）。
        这里用**真实调用计数**反证：note 只命中附注 loader，report 只命中报表 loader。
        """

        async def scenario(fx: AccessFixture, sql_log: list[str]):
            resolver = _resolver(fx)
            user = fx.actor("manager").user
            builder = ContextBuilder(fx.session)

            calls: dict[HostType, int] = {h: 0 for h in HostType}
            originals = dict(builder._doc_loaders)

            def _wrap(host_type: HostType):
                real = originals[host_type]

                async def spy(host):
                    calls[host_type] += 1
                    return await real(host)

                return spy

            for host_type in HostType:
                builder._doc_loaders[host_type] = _wrap(host_type)

            cases = (
                (HostType.note, str(fx.note_a.id), "disclosure_notes"),
                (HostType.report, FIXTURE_REPORT_TYPE, "financial_report"),
            )
            for host_type, host_id, expected_table in cases:
                for h in HostType:
                    calls[h] = 0
                host = await resolver.enforce(
                    user,
                    HostRef(
                        type=host_type,
                        id=host_id,
                        project_id_assertion=fx.project_a.id,
                    ),
                    AiChatAction.read,
                )
                sql_log.clear()
                content = await builder._get_doc_content(host)

                assert calls[host_type] == 1, (
                    f"{host_type.value} 专属 loader 未被调用: {calls}"
                )
                assert calls[HostType.workpaper] == 0, (
                    f"{host_type.value} 竟调用了底稿 loader（Req 3.7 禁止）: {calls}"
                )
                touched = _tables_touched(sql_log)
                assert expected_table in touched, (
                    f"{host_type.value} 正文未从 {expected_table} 读取，实际触碰 {touched}"
                )
                assert "working_paper" not in touched, (
                    f"{host_type.value} 正文竟查了 working_paper: {sql_log}"
                )
                assert content, f"{host_type.value} 正文为空（回退分支的典型症状）"

            # 反向对照：底稿宿主确实走底稿 loader（证明上面的 0 不是"loader 从未被调用"）
            for h in HostType:
                calls[h] = 0
            wp_host = await resolver.enforce(
                user,
                HostRef(
                    type=HostType.workpaper,
                    id=str(fx.wp_d_file.id),
                    project_id_assertion=fx.project_a.id,
                ),
                AiChatAction.read,
            )
            await builder._get_doc_content(wp_host)
            assert calls[HostType.workpaper] == 1, f"底稿宿主未走底稿 loader: {calls}"
            assert calls[HostType.note] == 0 and calls[HostType.report] == 0

        run_with_fixture(scenario, capture_sql=True)

    def test_note_stable_section_key_resolves_to_instance(self):
        """附注稳定 section key（section_id / note_section）被反查成 instance UUID。

        前端在未加载完整实例时只有章节号；服务端必须能把它归一成 canonical instance ID，
        否则会话定位与后续采纳会指向两个不同标识。
        """

        async def scenario(fx: AccessFixture, _sql):
            resolver = _resolver(fx)
            user = fx.actor("manager").user
            for key in (fx.note_a.section_id, fx.note_a.note_section):
                outcome = await resolver.resolve(
                    user,
                    HostRef(
                        type=HostType.note,
                        id=str(key),
                        project_id_assertion=fx.project_a.id,
                        year_assertion=FIXTURE_AUDIT_YEAR,
                    ),
                )
                assert isinstance(outcome, AuthorizedHostContext), f"{key} 反查失败"
                assert outcome.resource_id == str(fx.note_a.id), (
                    f"section key {key} 未归一为 instance UUID: {outcome.resource_id}"
                )
                assert outcome.year == FIXTURE_AUDIT_YEAR
                assert outcome.project_id == fx.project_a.id

            # section key 无项目断言 → 无法唯一定位，拒绝（不猜测最近项目，Req 3.4）
            no_project = await resolver.resolve(
                user, HostRef(type=HostType.note, id=str(fx.note_a.note_section))
            )
            assert isinstance(no_project, HostContextDenial)
            assert no_project.denial_code == AiChatDenialCode.invalid_resource_id.value

        run_with_fixture(scenario)

    def test_report_host_rejects_project_id_as_document_id(self):
        """报表宿主拒绝把 project ID 当 doc ID（旧 ReportView 的真实缺陷，Req 3.5）。"""

        async def scenario(fx: AccessFixture, _sql):
            resolver = _resolver(fx)
            user = fx.actor("manager").user

            bad_ids = (
                str(fx.project_a.id),   # 旧实现传的就是这个
                str(uuid4()),
                "",
                "cross_check",           # 分析类 tab，不是单张报表
                "multi_year_compare",
                "report_analysis",
            )
            for bad in bad_ids:
                outcome = await resolver.resolve(
                    user,
                    HostRef(
                        type=HostType.report,
                        id=bad,
                        project_id_assertion=fx.project_a.id,
                        year_assertion=FIXTURE_AUDIT_YEAR,
                    ),
                )
                assert isinstance(outcome, HostContextDenial), (
                    f"报表宿主竟接受非法稳定 ID {bad!r}"
                )
                assert outcome.denial_code == AiChatDenialCode.invalid_resource_id.value

            # 合法 report type 且已实例化 → 通过
            ok = await resolver.resolve(
                user,
                HostRef(
                    type=HostType.report,
                    id=FIXTURE_REPORT_TYPE,
                    project_id_assertion=fx.project_a.id,
                    year_assertion=FIXTURE_AUDIT_YEAR,
                ),
            )
            assert isinstance(ok, AuthorizedHostContext)
            assert ok.resource_id == FIXTURE_REPORT_TYPE
            assert ok.display_label == "资产负债表"

            # 未实例化的报表（同项目同年度但没有行次）→ resource_not_found，不伪造空宿主
            not_generated = sorted(REPORT_HOST_IDS - {FIXTURE_REPORT_TYPE})[0]
            missing = await resolver.resolve(
                user,
                HostRef(
                    type=HostType.report,
                    id=not_generated,
                    project_id_assertion=fx.project_a.id,
                    year_assertion=FIXTURE_AUDIT_YEAR,
                ),
            )
            assert isinstance(missing, HostContextDenial)
            assert missing.denial_code == AiChatDenialCode.resource_not_found.value

        run_with_fixture(scenario)

    def test_global_knowledge_has_no_project_binding(self):
        """受限全局知识模式：project_id 为 None、项目工具关闭、零业务表查询（Req 3.3/3.4）。"""

        async def scenario(fx: AccessFixture, sql_log: list[str]):
            resolver = _resolver(fx)
            sql_log.clear()
            outcome = await resolver.resolve(
                fx.actor("auditor").user,
                HostRef(type=HostType.global_knowledge, id=GLOBAL_KNOWLEDGE_HOST_ID),
            )
            assert isinstance(outcome, AuthorizedHostContext)
            assert outcome.project_id is None, "全局知识模式竟带上了 project_id"
            assert outcome.year is None
            assert outcome.project_tools_enabled is False
            assert outcome.display_label == GLOBAL_KNOWLEDGE_LABEL
            assert outcome.resource_id == GLOBAL_KNOWLEDGE_HOST_ID
            assert not _tables_touched(sql_log), (
                f"全局知识模式反查竟查了业务表: {_tables_touched(sql_log)}"
            )
            # 写类动作在无项目绑定下全部关闭
            for action in ("upload", "note-create", "adopt", "agent-run"):
                assert action not in outcome.allowed_actions

        run_with_fixture(scenario, capture_sql=True)

    def test_empty_and_fake_ids_never_become_valid_host(self):
        """空串 / 'null' / 非法 UUID 一律不能被构造成有效宿主（Req 3.3）。"""

        async def scenario(fx: AccessFixture, _sql):
            resolver = _resolver(fx)
            user = fx.actor("manager").user
            for host_type in (
                HostType.workpaper,
                HostType.note,
                HostType.knowledge_doc,
                HostType.knowledge_folder,
            ):
                for bad in ("", "null", "undefined", "not-a-uuid"):
                    outcome = await resolver.resolve(
                        user,
                        HostRef(
                            type=host_type,
                            id=bad,
                            project_id_assertion=fx.project_a.id,
                        ),
                    )
                    assert isinstance(outcome, HostContextDenial), (
                        f"{host_type.value} 竟接受了 {bad!r} 作为稳定 ID"
                    )

            # 全局 sentinel 必须精确匹配
            for fake in ("", "global", str(uuid4())):
                outcome = await resolver.resolve(
                    user, HostRef(type=HostType.global_knowledge, id=fake)
                )
                assert isinstance(outcome, HostContextDenial)

            # 数据结构层也拒绝空 resource_id（不给"空串伪装有效 ID"留后门）
            with pytest.raises(ValueError):
                AuthorizedHostContext(
                    principal_id=user.id,
                    project_id=fx.project_a.id,
                    year=None,
                    resource_type=HostType.workpaper,
                    resource_id="",
                    display_label="x",
                    permission_binding="x",
                )
            # 项目类宿主不得无项目绑定
            with pytest.raises(ValueError):
                AuthorizedHostContext(
                    principal_id=user.id,
                    project_id=None,
                    year=None,
                    resource_type=HostType.note,
                    resource_id=str(fx.note_a.id),
                    display_label="x",
                    permission_binding="x",
                )
            # 全局模式不得携带项目绑定
            with pytest.raises(ValueError):
                AuthorizedHostContext(
                    principal_id=user.id,
                    project_id=fx.project_a.id,
                    year=None,
                    resource_type=HostType.global_knowledge,
                    resource_id=GLOBAL_KNOWLEDGE_HOST_ID,
                    display_label="x",
                    permission_binding="x",
                )

        run_with_fixture(scenario)

    def test_display_label_is_loaded_only_after_authorization(self):
        """③label 阶段被授权决策严格门控：拿拒绝决策调 finalize 必抛契约错误。

        同时正向验证 label 真的来自各自业务模型（底稿 = wp_code+wp_name，附注 = 章节号+标题）。
        """

        async def scenario(fx: AccessFixture, _sql):
            resolver = _resolver(fx)
            access = ResourceAccessResolver(fx.session, responder=fx.responder)

            located = await resolver._locate_workpaper(
                HostRef(type=HostType.workpaper, id=str(fx.wp_d_file.id))
            )
            assert not isinstance(located, str), f"底稿反查失败: {located}"

            denied = await access.authorize_host(
                fx.outsider,
                HostRef(type=HostType.workpaper, id=str(fx.wp_d_file.id)),
                AiChatAction.read,
            )
            assert denied.allowed is False
            with pytest.raises(HostContextContractError):
                await resolver.finalize(located, denied)

            allowed = await access.authorize_host(
                fx.actor("manager").user,
                HostRef(type=HostType.workpaper, id=str(fx.wp_d_file.id)),
                AiChatAction.read,
            )
            assert allowed.allowed is True
            host = await resolver.finalize(located, allowed)
            assert fx.wp_d.wp_code in host.display_label
            assert fx.wp_d.wp_name in host.display_label

            note_host = await resolver.enforce(
                fx.actor("manager").user,
                HostRef(
                    type=HostType.note,
                    id=str(fx.note_a.id),
                    project_id_assertion=fx.project_a.id,
                ),
            )
            assert fx.note_a.note_section in note_host.display_label
            assert fx.note_a.section_title in note_host.display_label

        run_with_fixture(scenario)

    def test_denied_host_context_is_non_enumerable_and_audited(self):
        """反查阶段的拒绝同样：对外不可枚举 404、对内留真实拒绝码，且不泄露 label。"""

        async def scenario(fx: AccessFixture, _sql):
            responder = RecordingDenialResponder()
            resolver = HostContextResolver(
                fx.session,
                access=ResourceAccessResolver(fx.session, responder=responder),
            )
            with pytest.raises(ExternalNotFound):
                await resolver.enforce(
                    fx.actor("manager").user,
                    HostRef(
                        type=HostType.note,
                        id=str(fx.note_b.id),  # 跨项目附注
                        project_id_assertion=fx.project_b.id,
                    ),
                    AiChatAction.read,
                    entrypoint="ai_chat.doc_chat",
                )
            assert len(responder.records) == 1
            record = responder.records[0]
            assert record["detail"]["resource_type"] == "note"
            serialized = str(record)
            for secret in (fx.note_b.section_title, fx.project_b.name):
                assert secret not in serialized, f"denial audit 泄露了 {secret!r}"

        run_with_fixture(scenario)


# ===========================================================================
# Property 2 — HostContext 断言一致性
# ===========================================================================

class TestProperty2AssertionConsistency:
    """**Validates: Requirements 2.3, 3.3**"""

    def test_forged_project_assertion_returns_mismatch(self):
        """伪造 project 断言（与服务端反查值不一致）→ ``host_context_mismatch``。"""

        async def scenario(fx: AccessFixture, _sql):
            resolver = _resolver(fx)
            user = fx.actor("manager").user
            cases = (
                (HostType.workpaper, str(fx.wp_d_file.id)),
                (HostType.note, str(fx.note_a.id)),
            )
            for host_type, host_id in cases:
                outcome = await resolver.resolve(
                    user,
                    HostRef(
                        type=host_type,
                        id=host_id,
                        # 资源真实属于 project_a，客户端断言 project_b
                        project_id_assertion=fx.project_b.id,
                    ),
                    AiChatAction.read,
                )
                assert isinstance(outcome, HostContextDenial), (
                    f"{host_type.value} 接受了伪造的 project 断言"
                )
                assert outcome.denial_code == (
                    AiChatDenialCode.host_context_mismatch.value
                ), f"{host_type.value} 拒绝码应为 host_context_mismatch，实际 {outcome.denial_code}"

            # 全局知识模式携带 project 断言 = 契约错误，同样判 mismatch
            global_with_project = await resolver.resolve(
                user,
                HostRef(
                    type=HostType.global_knowledge,
                    id=GLOBAL_KNOWLEDGE_HOST_ID,
                    project_id_assertion=fx.project_a.id,
                ),
            )
            assert isinstance(global_with_project, HostContextDenial)
            assert global_with_project.denial_code == (
                AiChatDenialCode.host_context_mismatch.value
            )

        run_with_fixture(scenario)

    def test_forged_year_assertion_returns_mismatch(self):
        """伪造 year 断言 → ``host_context_mismatch``；缺省 year 按 nullable 语义放过。"""

        async def scenario(fx: AccessFixture, _sql):
            resolver = _resolver(fx)
            user = fx.actor("manager").user
            wrong_year = FIXTURE_AUDIT_YEAR - 1

            for host_type, host_id in (
                (HostType.workpaper, str(fx.wp_d_file.id)),
                (HostType.note, str(fx.note_a.id)),
            ):
                bad = await resolver.resolve(
                    user,
                    HostRef(
                        type=host_type,
                        id=host_id,
                        project_id_assertion=fx.project_a.id,
                        year_assertion=wrong_year,
                    ),
                )
                assert isinstance(bad, HostContextDenial), (
                    f"{host_type.value} 接受了伪造的 year 断言 {wrong_year}"
                )
                assert bad.denial_code == AiChatDenialCode.host_context_mismatch.value

                # 不传 year → 服务端自行反查，且反查值就是权威年度
                ok = await resolver.resolve(
                    user,
                    HostRef(
                        type=host_type,
                        id=host_id,
                        project_id_assertion=fx.project_a.id,
                    ),
                )
                assert isinstance(ok, AuthorizedHostContext)
                assert ok.year == FIXTURE_AUDIT_YEAR, (
                    f"{host_type.value} 未反查出权威年度: {ok.year}"
                )

        run_with_fixture(scenario)

    def test_forged_doc_assertion_creates_no_session(self):
        """伪造断言经真实端点 → 不可枚举 404，且 ``ai_chat_session`` 零新增（Property 2）。

        判据是**真实行数差**而不是"路由抛了异常"：只要拒绝晚于 session upsert，
        这条断言就会变红。
        """
        from app.routers import doc_ai_chat as route_mod

        async def scenario(fx: AccessFixture, _sql):
            async def fake_write_outbox(_self, **fields):
                return None

            from unittest.mock import patch

            before = await _session_count(fx)
            with patch(
                "app.services.wp_visibility.denial.DenialResponder._write_outbox",
                fake_write_outbox,
            ):
                forged_cases = (
                    # 底稿真实属于 project_a，客户端断言 project_b
                    ("workpaper", str(fx.wp_d_file.id), str(fx.project_b.id), FIXTURE_AUDIT_YEAR),
                    # 附注真实年度 2025，客户端断言 2024
                    ("note", str(fx.note_a.id), str(fx.project_a.id), FIXTURE_AUDIT_YEAR - 1),
                    # 报表宿主被塞进 project ID（旧 ReportView 契约）
                    ("report", str(fx.project_a.id), str(fx.project_a.id), FIXTURE_AUDIT_YEAR),
                    # 不存在的附注实例
                    ("note", str(uuid4()), str(fx.project_a.id), FIXTURE_AUDIT_YEAR),
                )
                for doc_type, doc_id, project_id, year in forged_cases:
                    with pytest.raises(ExternalNotFound):
                        await route_mod.doc_ai_chat(
                            doc_type,
                            doc_id,
                            route_mod.DocChatRequest(
                                query="这份文档有什么风险？",
                                year=year,
                                project_id=project_id,
                            ),
                            fx.session,
                            fx.actor("manager").user,
                        )
                    after = await _session_count(fx)
                    assert after == before, (
                        f"伪造断言（{doc_type}/{doc_id}）竟创建了会话: {before} → {after}"
                    )

        run_with_fixture(scenario)

    def test_matching_assertions_pass_and_canonicalize(self):
        """一致的断言正常通过，且服务端反查值成为下游唯一真源（canonical 化）。

        这是 mismatch 判据的反假绿控制：若把断言比对写成"恒返回 mismatch"，本用例先变红。
        """

        async def scenario(fx: AccessFixture, _sql):
            resolver = _resolver(fx)
            user = fx.actor("manager").user
            for host_type, host_id, _why in _host_cases(fx):
                if host_type is HostType.global_knowledge:
                    continue
                project_assertion = fx.project_a.id
                year_assertion = (
                    FIXTURE_AUDIT_YEAR
                    if host_type in (HostType.workpaper, HostType.note, HostType.report)
                    else None
                )
                outcome = await resolver.resolve(
                    user,
                    HostRef(
                        type=host_type,
                        id=host_id,
                        project_id_assertion=project_assertion,
                        year_assertion=year_assertion,
                    ),
                )
                assert isinstance(outcome, AuthorizedHostContext), (
                    f"{host_type.value} 在断言一致时被误拒: {outcome}"
                )
                assert outcome.project_id == fx.project_a.id
                if year_assertion is not None:
                    assert outcome.year == FIXTURE_AUDIT_YEAR

        run_with_fixture(scenario)


# ===========================================================================
# Req 3.6 — ContextBuilder 只接受 AuthorizedHostContext
# ===========================================================================

class TestContextBuilderConsumesAuthorizedHost:
    """**Validates: Requirements 3.6**"""

    def test_build_signature_rejects_untrusted_scalars(self):
        """``build`` 不再接受 doc_type/doc_id/project_id 自由字符串（Req 3.6）。"""
        import inspect

        params = inspect.signature(ContextBuilder.build).parameters
        assert "host" in params, "build 必须接受已授权 HostContext"
        for legacy in ("doc_type", "doc_id", "project_id", "year"):
            assert legacy not in params, (
                f"build 仍接受未经验证的 {legacy} —— 会再次自行猜测资源类型"
            )

    def test_workpaper_content_is_bound_to_authoritative_project(self):
        """底稿正文查询绑定权威 project_id：跨项目宿主拼装拿不到别的项目的正文。"""

        async def scenario(fx: AccessFixture, _sql):
            builder = ContextBuilder(fx.session)
            # 手工拼一个"project 与底稿不匹配"的上下文（模拟绕过 resolver 的调用方）
            forged = AuthorizedHostContext(
                principal_id=fx.actor("manager").id,
                project_id=fx.project_b.id,
                year=FIXTURE_AUDIT_YEAR,
                resource_type=HostType.workpaper,
                resource_id=str(fx.wp_d_file.id),  # 实际属于 project_a
                display_label="x",
                permission_binding="x",
            )
            content = await builder._get_doc_content(forged)
            assert content == "", "底稿正文查询未绑定 project_id（跨项目可读）"

            real = AuthorizedHostContext(
                principal_id=fx.actor("manager").id,
                project_id=fx.project_a.id,
                year=FIXTURE_AUDIT_YEAR,
                resource_type=HostType.workpaper,
                resource_id=str(fx.wp_d_file.id),
                display_label="x",
                permission_binding="x",
            )
            assert await builder._get_doc_content(real) != "", (
                "同一底稿在正确项目下也读不到内容（上面的空值断言失去意义）"
            )

        run_with_fixture(scenario)

    def test_global_mode_skips_project_scoped_retrieval(self):
        """受限全局知识模式：不做项目级语义检索、不生成项目摘要（不猜测最近项目）。"""

        async def scenario(fx: AccessFixture, _sql):
            builder = ContextBuilder(fx.session)
            semantic_calls: list[dict] = []

            async def spy_semantic(**kwargs):
                semantic_calls.append(kwargs)
                return []

            from unittest.mock import patch

            with patch.object(
                builder._knowledge_svc, "semantic_search", spy_semantic
            ):
                ctx = await builder.build(
                    host=AuthorizedHostContext(
                        principal_id=fx.actor("manager").id,
                        project_id=None,
                        year=None,
                        resource_type=HostType.global_knowledge,
                        resource_id=GLOBAL_KNOWLEDGE_HOST_ID,
                        display_label=GLOBAL_KNOWLEDGE_LABEL,
                        permission_binding="global:knowledge_readonly",
                    ),
                    query="什么是审计抽样？",
                    user=fx.actor("manager").user,
                )
            assert semantic_calls == [], (
                f"全局模式竟发起了项目级语义检索: {semantic_calls}"
            )
            assert ctx.project_summary == "", "全局模式竟生成了项目摘要"
            assert ctx.doc_excerpt == ""

            # 反向对照：有项目绑定时确实会检索（证明上面的空断言不是恒真）
            with patch.object(
                builder._knowledge_svc, "semantic_search", spy_semantic
            ):
                ctx2 = await builder.build(
                    host=AuthorizedHostContext(
                        principal_id=fx.actor("manager").id,
                        project_id=fx.project_a.id,
                        year=FIXTURE_AUDIT_YEAR,
                        resource_type=HostType.note,
                        resource_id=str(fx.note_a.id),
                        display_label="x",
                        permission_binding="x",
                    ),
                    query="什么是审计抽样？",
                    user=fx.actor("manager").user,
                )
            assert len(semantic_calls) == 1
            assert semantic_calls[0]["project_id"] == fx.project_a.id
            assert ctx2.project_summary, "项目宿主未生成项目摘要"
            assert fx.note_a.section_title in ctx2.doc_excerpt

        run_with_fixture(scenario)
