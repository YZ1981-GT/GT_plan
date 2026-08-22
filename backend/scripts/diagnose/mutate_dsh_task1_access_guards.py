"""Task 1 授权守卫变异检验（spec dsh-agent-panel-integration / Task 1）。

## 为什么需要它

「22 条守卫全绿」只证明当前代码没触发断言，**不证明断言有效**。Task 1 交付的是整个
Phase A 的安全边界，最贵的假绿形态恰好都在这里：

- 把授权门挪到 ``ContextBuilder.build`` 之后（正文已读，才拒绝）；
- 角色上界写成「已登记角色即全放行」（QC/EQCR 拿到写权限）；
- 搜索可见集与直接 ID 授权分叉（"搜索不可见但直接 ID 可读"）；
- 知识库判定退回"不传 subject 就不过滤"；
- ContextBuilder 异常恢复 fail-open（空上下文继续调模型）。

唯一可靠的反证是把生产代码**改坏**，看对应守卫是否打红。

## 四态判定

由 ``_mutation_kit`` 统一给出：RED（新增失败含期望项）/ WRONG-TEST（新增失败不含期望项）
/ GREEN（无新增失败 = 守卫缺陷）/ ANCHOR-MISS（锚点未唯一命中 = 本脚本缺陷）。
退出码不作判据。

用法::

    python backend/scripts/diagnose/mutate_dsh_task1_access_guards.py --list
    python backend/scripts/diagnose/mutate_dsh_task1_access_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_dsh_task1_access_guards.py --run all
    python backend/scripts/diagnose/mutate_dsh_task1_access_guards.py --restore
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _mutation_kit import Mutation as Mut  # noqa: E402
from _mutation_kit import run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

#: 本 Task 创建的守卫文件全集（覆盖面分母）。新增守卫文件必须同时加一条变异，
#: 否则 ``--run`` 报告末尾会显示未被反证过的文件。
GUARD_FILES: dict[str, str] = {
    "test_task1_resource_access.py": "Task 1 新建（Property 1/3/4 + 知识库四入口）",
}

#: 冻结基线（本会话实测）：22 passed。改这个数必须同时说明来源。
BASELINE_BE_PASSED = 22

BE_PYTEST_ARGS = [
    "backend/tests/dsh_agent_panel",
    "-q",
    "--tb=no",
    "-rf",
    "-p",
    "no:randomly",
]

ROUTE = "backend/app/routers/doc_ai_chat.py"
ACCESS = "backend/app/services/ai_chat/access.py"
CONTRACTS = "backend/app/services/ai_chat/contracts.py"
POLICY = "backend/app/services/knowledge_access_policy.py"
KB_SERVICE = "backend/app/services/knowledge_folder_service.py"
KB_ROUTE = "backend/app/routers/knowledge_folders.py"

MUTATIONS: list[Mut] = [
    Mut(
        id="M01",
        side="be",
        path=ROUTE,
        kind="replace",
        # Task 2（Req 2.3/3.x）把端点前置从 `ResourceAccessResolver.enforce_host` 升级为
        # `HostContextResolver.enforce`（授权 + 服务端反查可信 HostContext）。锚点随之落在
        # 新的单行前置调用上；变异语义不变 —— 依旧是"摘掉端点授权门，直接返回 allow"。
        anchor="    return await resolver.enforce(current_user, host, action, entrypoint=entrypoint)",
        new=(
            "    from app.services.ai_chat.host_context import"
            " AuthorizedHostContext as _AHC\n"
            "    return _AHC(principal_id=current_user.id,"
            " project_id=host.project_id_assertion, year=year,"
            " resource_type=host.type, resource_id=host.id or 'x',"
            " display_label='', permission_binding='mutated',"
            " allowed_actions=frozenset({action.value}))"
        ),
        want="test_endpoint_denies_before_any_context_loader_runs",
        wants=("test_all_ai_endpoints_share_the_same_decision",),
        why=(
            "端点授权门被摘除（直接返回 allow）。若守卫只断言「源码里出现 enforce」"
            "就查不出来；这里必须由「拒绝路径 loader 计数=0」与「四端点决策一致」两条"
            "行为判据打红。"
        ),
        tags=("property1", "property4"),
    ),
    Mut(
        id="M02",
        side="be",
        path=ROUTE,
        kind="replace",
        anchor='        logger.exception("ContextBuilder.build 失败（fail-closed，不降级为空上下文）: %s", e)',
        new=(
            "        from app.services.doc_ai_context_builder import ChatContext as _CC\n"
            "        context = _CC(doc_excerpt='', knowledge_hits=[], project_summary='',"
            " citations=[], token_estimate=0)\n"
            "        return StreamingResponse(\n"
            "            _stream_chat(doc_type, doc_id, req.query, context, current_user, project_id),\n"
            '            media_type="text/event-stream",\n'
            "        )\n"
            "        _unused = e"
        ),
        want="test_context_build_failure_fails_closed_without_model_call",
        why=(
            "恢复 Req 2.8 明令禁止的 fail-open：上下文构建失败后用空上下文继续调用模型。"
            "守卫必须落在「返回 typed error 且模型调用计数为 0」上，而不是看有没有 except。"
        ),
        tags=("req2.8",),
    ),
    Mut(
        id="M03",
        side="be",
        path=CONTRACTS,
        kind="replace",
        anchor="    return all(is_permitted(role, cap) for cap in caps)",
        new="    return role in CAPABILITY_MATRIX",
        want="test_qc_and_eqcr_are_read_only_upper_bound",
        wants=(
            "test_role_upper_bound_table_matches_requirements_role_table",
            "test_workpaper_matrix_equals_platform_service_intersection",
        ),
        why=(
            "角色上界退化为「已登记角色即全放行」→ QC/EQCR 拿到 upload/note-create/adopt/"
            "agent-run。这正是 Requirements §2 角色表禁止的项，三条判据应同时打红。"
        ),
        tags=("property3",),
    ),
    Mut(
        id="M04",
        side="be",
        path=ACCESS,
        kind="replace",
        anchor="                if await visible(rid, None):",
        new="                if True:",
        want="test_search_visibility_equals_direct_id_authorization",
        why=(
            "底稿搜索可见集不再过滤（返回全部候选 ID）→ 出现"
            "「搜索可见但直接 ID 不可读」的反向旁路。Property 4 的集合相等判据必须打红。"
        ),
        tags=("property4",),
    ),
    Mut(
        id="M05",
        side="be",
        path=POLICY,
        kind="replace",
        anchor="            return subject.user_id is not None and resource.created_by == subject.user_id",
        new="            return True",
        want="test_private_and_project_group_boundaries_are_real",
        wants=(
            "test_tree_hides_invisible_folders_per_user",
            "test_anonymous_subject_sees_no_restricted_knowledge",
            "test_denied_knowledge_emits_no_label_or_body_sql",
        ),
        why=(
            "private 资源对所有人可见。因五角色知识矩阵用的期望值来自同一 policy（会同步变化），"
            "锁死这条边界的只能是硬编码期望的 boundary/tree/anonymous 三条判据 —— "
            "本条变异正是用来证明它们不是自我印证。"
        ),
        tags=("property1", "property3"),
    ),
    Mut(
        id="M06",
        side="be",
        path=POLICY,
        kind="replace",
        anchor="            return subject.is_member_of_any(resource.project_ids)",
        new="            return True",
        want="test_private_and_project_group_boundaries_are_real",
        wants=(
            "test_tree_hides_invisible_folders_per_user",
            "test_anonymous_subject_sees_no_restricted_knowledge",
        ),
        why=(
            "project_group 不再校验成员关系 → 他项目知识库对所有人可见（跨项目泄漏）。"
            "验证跨项目边界不是靠夹具恰好为空。"
        ),
        tags=("property3",),
    ),
    Mut(
        id="M07",
        side="be",
        path=ACCESS,
        kind="replace",
        anchor="            return self._deny(principal_id, None, AiChatDenialCode.resolver_error)",
        new=(
            "            return AccessDecision(allowed=True, principal_id=principal_id,"
            " project_id=None, allowed_actions=frozenset({action.value}))"
        ),
        want="test_resolver_internal_failure_fails_closed",
        why=(
            "授权服务内部异常改为 fail-open。Req 2.8 要求 fail-closed；守卫必须在注入"
            "异常分类器后仍断言拒绝，而不是只看有没有 try/except。"
        ),
        tags=("req2.8",),
    ),
    Mut(
        id="M08",
        side="be",
        path=ACCESS,
        kind="replace",
        anchor="        reason = DENIAL_REASON_BY_CODE[code]",
        new="        return",
        want="test_denial_audit_records_internal_reason_without_label",
        wants=("test_endpoint_denies_before_any_context_loader_runs",),
        why=(
            "内部 denial audit 被摘除（对外 404 不变）→ 拒绝事实不可追溯。"
            "只看外部响应的守卫查不出来，必须由 audit 记录断言打红。"
        ),
        tags=("req2.5",),
    ),
    Mut(
        id="M09",
        side="be",
        path=KB_SERVICE,
        kind="replace",
        anchor="        if folder is None or not KnowledgeAccessPolicy.can_read(subject, folder):",
        new="        if False:",
        want="test_list_documents_denies_before_reading_names_or_bodies",
        why=(
            "list_documents 不再前置判定父文件夹 → 无权文件夹下的文档 name/正文被读出来。"
            "这正是旧实现「依赖上层已过滤」的假设，守卫须落在 SQL 流与返回集合上。"
        ),
        tags=("property1",),
    ),
    Mut(
        id="M10",
        side="be",
        path=KB_ROUTE,
        kind="replace",
        anchor="    if folder is None or not KnowledgeAccessPolicy.can_create_in_folder(subject, folder):",
        new="    if False:",
        want="test_create_document_requires_knowledge_write_permission",
        why=(
            "知识资产写权限门被摘除 → 任何登录用户可往他人 private / 他项目 project_group "
            "文件夹写文档。守卫须真实调用 route 并断言不可枚举 404。"
        ),
        tags=("req2.1",),
    ),
    Mut(
        id="M11",
        side="be",
        path=ACCESS,
        kind="replace",
        # 该 _deny 行在 _authorize_workpaper 与 _authorize_project_resource 中逐字相同，
        # 用 scope（上一行的 `if ctx is None:`）+ offset 相对定位到底稿分支那一条。
        scope="        if ctx is None:",
        offset=1,
        anchor="            return self._deny(principal_id, None, AiChatDenialCode.access_denied)",
        new=(
            "            import sqlalchemy as _sa\n"
            "            from types import SimpleNamespace as _NS\n"
            "            from app.models.workpaper_models import WorkingPaper as _WP\n"
            "            _pid = (await self._db.execute("
            "_sa.select(_WP.project_id).where(_WP.id == wp_id))).scalar_one_or_none()\n"
            "            ctx = _NS(project_id=_pid, wp_index_id=wp_id, readonly=False)"
        ),
        want="test_workpaper_matrix_equals_platform_service_intersection",
        wants=("test_denied_host_emits_no_sensitive_sql",),
        why=(
            "底稿资源门（gate_wp 拒绝）被真正绕过：只要底稿存在就伪造 allow 上下文 → "
            "跨项目 / 越出 scope 的底稿全部可读。"
            "注意不能简单写成 `if False:` —— 那样 ctx 仍为 None，后续 AttributeError 会被"
            "fail-closed 分支吞成另一种拒绝码，行为上并没有放宽（= 无效变异，实测判 WRONG-TEST）。"
        ),
        tags=("property1", "property3"),
    ),
    Mut(
        id="M12",
        side="be",
        path=ACCESS,
        kind="replace",
        anchor="        if not unbounded and not await self._is_project_member(principal_id, project_id):",
        new="        if False:",
        want="test_note_and_report_hosts_require_project_membership",
        why=(
            "附注/报表宿主不再校验项目成员关系 → 任何登录用户可就任意项目发起 AI 对话"
            "（这正是重构前 doc_ai_chat 的真实漏洞）。"
        ),
        tags=("property3",),
    ),
    Mut(
        id="M13",
        side="be",
        path=ACCESS,
        kind="replace",
        anchor="        if host.principal_id != principal_id:",
        new="        if False:",
        want="test_resource_authorization_requires_authorized_host",
        why=(
            "宿主决策可跨主体复用 → A 的已授权宿主能替 B 授权资源。"
            "守卫须真实拿 manager 的宿主决策去为 auditor 授权并断言拒绝。"
        ),
        tags=("property4",),
    ),
    Mut(
        id="M14",
        side="be",
        path=ACCESS,
        kind="replace",
        anchor="            if _coerce_uuid(resource_id) is None:",
        new="            if False:",
        want="test_malformed_and_unsupported_identifiers_fail_closed",
        why=(
            "非法资源 ID 不再前置拒绝 → 后续 loader 会因 UUID 解析异常泄露资源形态，"
            "或把非法 ID 当有效资源查询。守卫须断言零查询 + invalid_resource_id。"
        ),
        tags=("property1",),
    ),
]

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="dsh-agent-panel-integration Task 1 授权守卫变异检验",
            backend_args=BE_PYTEST_ARGS,
            baseline_backend_passed=BASELINE_BE_PASSED,
        )
    )
