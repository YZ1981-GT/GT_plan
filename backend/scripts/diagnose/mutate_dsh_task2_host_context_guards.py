"""Task 2 可信 HostContext 守卫变异检验（spec dsh-agent-panel-integration / Task 2）。

## 为什么需要它

Task 2 交付的是「AI 到底在跟哪份文档说话」这件事的可信性。它的假绿形态非常隐蔽，
因为**错了也不会报错，只会静默取空**：

- note/report 回退到 ``WorkingPaper`` loader —— 附注/报表 ID 在 ``working_paper`` 里查不到，
  正文恒空，而 AI 照常给出一段"看起来专业"的回答；
- 客户端 project/year 断言被当权威值用 —— 前端传错年度，服务端跟着错，
  或者干脆用 ``new Date().getFullYear() - 1`` 猜；
- 空串 / project UUID 被当成有效 doc ID（旧 ReportView 的真实写法）；
- 反查阶段的拒绝晚于 session 创建 —— 伪造断言仍然留下会话行。

上述四类的共同点：**类型检查、Volar、vitest、pytest 全绿**，只有把生产代码改坏再看守卫
是否打红，才能证明判据有效。

## 四态判定

由 ``_mutation_kit`` 统一给出：RED（新增失败含期望项）/ WRONG-TEST（新增失败不含期望项）
/ GREEN（无新增失败 = 守卫缺陷）/ ANCHOR-MISS（锚点未唯一命中 = 本脚本缺陷）。
退出码不作判据。

用法::

    python backend/scripts/diagnose/mutate_dsh_task2_host_context_guards.py --list
    python backend/scripts/diagnose/mutate_dsh_task2_host_context_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_dsh_task2_host_context_guards.py --run all
    python backend/scripts/diagnose/mutate_dsh_task2_host_context_guards.py --restore

Task 1 的变异脚本（``mutate_dsh_task1_access_guards.py``）覆盖的是授权边界；本脚本只覆盖
Task 2 新增的宿主反查与宿主契约，两者互不重叠。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _mutation_kit import Mutation as Mut  # noqa: E402
from _mutation_kit import run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "audit-platform" / "frontend"

#: 本 Task 创建的守卫文件全集（覆盖面分母）。
GUARD_FILES: dict[str, str] = {
    "test_task2_host_context.py": "Task 2 新建（Property 2/5 + Req 3.6 后端）",
    "useAiHostContext.spec.ts": "Task 2 新建（六宿主 adapter 行为）",
    "DocAiChatPanel.host.spec.ts": "Task 2 新建（宿主接线：真实 DOM + 模板形态）",
}

#: 冻结基线（本会话实测）。改这两个数必须同时说明来源。
#: 后端 = backend/tests/dsh_agent_panel 全量（含并发 Task 1/Task 3 的守卫）。
BASELINE_BE_PASSED = 66
#: 前端 = 四个 AI 面板相关 spec（含 Task 2 新建两个 + 存量两个）。
BASELINE_FE_PASSED = 65

BE_PYTEST_ARGS = [
    "backend/tests/dsh_agent_panel",
    "-q",
    "--tb=no",
    "-rf",
    "-p",
    "no:randomly",
]

FE_FILTERS = ["useAiHostContext", "DocAiChatPanel"]

HOST_CTX = "backend/app/services/ai_chat/host_context.py"
BUILDER = "backend/app/services/doc_ai_context_builder.py"
ROUTE = "backend/app/routers/doc_ai_chat.py"
ACCESS = "backend/app/services/ai_chat/access.py"
FE_ADAPTER = "audit-platform/frontend/src/composables/useAiHostContext.ts"
FE_CHAT = "audit-platform/frontend/src/composables/useDocAiChat.ts"
FE_REPORT = "audit-platform/frontend/src/views/ReportView.vue"

MUTATIONS: list[Mut] = [
    # ── Property 5：宿主 loader 唯一映射 ──────────────────────────────────────
    Mut(
        id="M01",
        side="be",
        path=BUILDER,
        kind="replace",
        anchor="            HostType.note: self._get_note_content,",
        new="            HostType.note: self._get_workpaper_content,  # MUTATED",
        want="test_note_and_report_never_touch_workpaper_loader",
        wants=("test_loader_dispatch_covers_every_host_without_fallback",),
        why=(
            "恢复旧实现的回退：附注正文改由底稿 loader 取 —— 附注 ID 在 working_paper 里"
            "查不到，正文恒空而 AI 照常作答。守卫必须由「底稿 loader 调用计数 = 0」与"
            "「SQL 流出现 disclosure_notes 且不出现 working_paper」两条行为判据打红，"
            "而不是靠源码里出现过 _get_note_content 这个名字。"
        ),
        tags=("property5", "req3.7"),
    ),
    Mut(
        id="M02",
        side="be",
        path=BUILDER,
        kind="replace",
        anchor="            HostType.report: self._get_report_content,",
        new="            HostType.report: self._get_workpaper_content,  # MUTATED",
        want="test_note_and_report_never_touch_workpaper_loader",
        wants=("test_loader_dispatch_covers_every_host_without_fallback",),
        why=(
            "同 M01，改报表侧：报表宿主的稳定 ID 是 report type（不是 UUID），"
            "交给底稿 loader 会直接 UUID 解析失败或恒空。两条判据必须分别打红。"
        ),
        tags=("property5", "req3.7"),
    ),
    Mut(
        id="M03",
        side="be",
        path=HOST_CTX,
        kind="replace",
        anchor="            HostType.note: self._locate_note,",
        new="            HostType.note: self._locate_workpaper,  # MUTATED",
        want="test_each_host_resolves_via_its_own_business_model",
        wants=("test_note_stable_section_key_resolves_to_instance",),
        why=(
            "把附注**反查**也换成底稿 locate：附注实例 ID 在 working_paper 查不到 ⇒ "
            "宿主直接不可解析。判据是「SQL 流命中的业务表 ⊆ 本宿主自己的表」，"
            "而 HOST_BUSINESS_MODEL[note] 只含 disclosure_notes ⇒ 出现 working_paper 即红。"
        ),
        tags=("property5", "req3.2"),
    ),
    Mut(
        id="M04",
        side="be",
        path=HOST_CTX,
        kind="replace",
        anchor="        if report_type not in REPORT_HOST_IDS:",
        new="        if False:  # MUTATED: 报表稳定 ID 不再校验取值域",
        want="test_report_host_rejects_project_id_as_document_id",
        why=(
            "报表宿主不再校验 report type 取值域 ⇒ project UUID / 'cross_check' / 空串"
            "都会被当成有效报表 ID（旧 ReportView 的真实契约）。守卫须逐个断言这些"
            "非法稳定 ID 被拒。"
        ),
        tags=("property5", "req3.5"),
    ),
    Mut(
        id="M05",
        side="be",
        path=HOST_CTX,
        kind="replace",
        anchor="        if exists is None:",
        # `if exists is None:` 在 _locate_report 与 _locate_knowledge_folder 各出现一次，
        # 用报表查询的 select 行相对定位到报表分支那条。
        scope="                sa.select(FinancialReport.id)",
        offset=10,
        new="        if exists is None and False:  # MUTATED: 未实例化报表也当存在",
        want="test_report_host_rejects_project_id_as_document_id",
        why=(
            "未实例化的报表（该 project/year/type 下零行次）不再判 resource_not_found，"
            "而是伪造出一个空宿主 ⇒ AI 会对着不存在的报表作答。"
            "🔴 只能改条件、不能整行换掉：本条第一版写成两行（先给 exists 赋值再 `if False:`），"
            "缩进与原 8 空格块不符 ⇒ 模块 3 个 collection error、失败名集合为空，"
            "四态判定报 GREEN（实为脚本缺陷）。留此注记提醒 GREEN 必须逐条归因。"
        ),
        tags=("property5",),
    ),
    Mut(
        id="M06",
        side="be",
        path=HOST_CTX,
        kind="replace",
        anchor="        if host.project_id_assertion is not None:",
        scope="        if host.id != GLOBAL_KNOWLEDGE_HOST_ID:",
        offset=2,
        new="        if False:  # MUTATED: 全局模式允许携带 project 断言",
        want="test_global_knowledge_has_no_project_binding",
        wants=("test_forged_project_assertion_returns_mismatch",),
        why=(
            "受限全局知识模式允许带 project 断言 ⇒ 「无项目页面」会被伪装成有项目上下文，"
            "项目工具误开。守卫须断言全局宿主 project_id 恒 None、项目工具关闭，"
            "且带 project 断言时判 host_context_mismatch。"
        ),
        tags=("property5", "req3.4"),
    ),
    Mut(
        id="M07",
        side="be",
        path=BUILDER,
        kind="replace",
        anchor="                WorkingPaper.project_id == host.project_id,",
        new="                WorkingPaper.id == UUID(host.resource_id),  # MUTATED: 去掉 project 绑定",
        want="test_workpaper_content_is_bound_to_authoritative_project",
        why=(
            "底稿正文查询不再绑定权威 project_id（这正是重构前的真实缺陷）⇒ 跨项目宿主"
            "拼装也能读到别的项目的底稿正文。守卫用「project 与底稿不匹配时正文必须为空」"
            "+「正确项目下正文非空」正反两条锁死。"
        ),
        tags=("property5", "req3.6"),
    ),
    Mut(
        id="M08",
        side="be",
        path=BUILDER,
        kind="replace",
        anchor="        if project_id is not None:",
        scope="        raw_results: list[dict] = []",
        offset=1,
        new="        if True:  # MUTATED: 无项目绑定也做项目级语义检索",
        want="test_global_mode_skips_project_scoped_retrieval",
        why=(
            "受限全局知识模式下仍发起项目级语义检索（project_id=None 传进索引）⇒ "
            "要么报错要么用空/猜测项目去查。守卫用 semantic_search 的**真实调用记录**"
            "判红，并有「有项目时确实检索一次」的反向对照防恒真。"
        ),
        tags=("req3.4",),
    ),
    # ── Property 2：断言一致性 ────────────────────────────────────────────────
    Mut(
        id="M09",
        side="be",
        path=HOST_CTX,
        kind="replace",
        anchor="        and host.project_id_assertion != project_id",
        new="        and False  # MUTATED: project 断言不再比对",
        want="test_forged_project_assertion_returns_mismatch",
        wants=("test_forged_doc_assertion_creates_no_session",),
        why=(
            "伪造的 project 断言不再被比对 ⇒ 客户端说是哪个项目就是哪个项目。"
            "守卫须断言「资源真实属于 A 但断言 B」时返回 host_context_mismatch，"
            "并且真实端点在该请求下不创建会话行。"
        ),
        tags=("property2", "req2.3"),
    ),
    Mut(
        id="M10",
        side="be",
        path=HOST_CTX,
        kind="replace",
        anchor="        and host.year_assertion != year",
        new="        and False  # MUTATED: year 断言不再比对",
        want="test_forged_year_assertion_returns_mismatch",
        why=(
            "伪造的 year 断言不再被比对 ⇒ 前端用「当前年份-1」猜的年度会被当权威值，"
            "AI 拿到的是另一年度的附注/报表。守卫须在服务端已反查出权威年度的前提下"
            "断言不一致必拒，同时保留「不传 year 则按 nullable 语义放过」的正向对照。"
        ),
        tags=("property2", "req2.3"),
    ),
    Mut(
        id="M11",
        side="be",
        path=ROUTE,
        kind="replace",
        anchor="    return await resolver.enforce(current_user, host, action, entrypoint=entrypoint)",
        new=(
            "    outcome = await resolver.resolve(current_user, host, action)\n"
            "    from app.services.ai_chat.host_context import (\n"
            "        AuthorizedHostContext as _AHC,\n"
            "        HostContextDenial as _HCD,\n"
            "    )\n"
            "    if isinstance(outcome, _HCD):\n"
            "        # MUTATED: 反查阶段的拒绝被忽略，用客户端断言硬造一个宿主\n"
            "        return _AHC(\n"
            "            principal_id=current_user.id,\n"
            "            project_id=host.project_id_assertion,\n"
            "            year=host.year_assertion,\n"
            "            resource_type=host.type,\n"
            "            resource_id=host.id or 'x',\n"
            "            display_label='',\n"
            "            permission_binding='mutated',\n"
            "            allowed_actions=frozenset({action.value}),\n"
            "        )\n"
            "    return outcome"
        ),
        want="test_forged_doc_assertion_creates_no_session",
        why=(
            "端点忽略反查阶段的拒绝（mismatch / not_found / 非法 ID），改用客户端断言"
            "硬造宿主 ⇒ 伪造请求会继续往下走并创建会话。判据是**真实会话表行数差**，"
            "而不是「路由抛没抛异常」：只要拒绝晚于 session upsert 就会打红。"
        ),
        tags=("property2",),
    ),
    Mut(
        id="M12",
        side="be",
        path=HOST_CTX,
        kind="replace",
        anchor="        if not decision.allowed:",
        # 该行在 resolve()（授权后判定）与 finalize()（label 门控）各一次；
        # 用 finalize 的参数行相对定位到 label 门控那条。
        scope="        self, located: HostLocator, decision: AccessDecision",
        offset=3,
        new="        if False:  # MUTATED: label 不再受授权门控",
        want="test_display_label_is_loaded_only_after_authorization",
        why=(
            "③label 阶段不再校验授权决策 ⇒ 拿一个拒绝决策也能把 display_label 读出来"
            "（Design 固定顺序「授权 → 读 label」被破坏，资源名称在授权前泄露）。"
            "守卫须断言用拒绝决策调 finalize 抛 HostContextContractError。"
        ),
        tags=("property5", "req2.5"),
    ),
    Mut(
        id="M13",
        side="be",
        path=ACCESS,
        kind="replace",
        anchor="        reason = DENIAL_REASON_BY_CODE[code]",
        new="        return  # MUTATED: 反查阶段拒绝不再写内部审计",
        want="test_denied_host_context_is_non_enumerable_and_audited",
        why=(
            "反查阶段的拒绝（跨项目附注等）不再留内部 denial audit ⇒ 拒绝事实不可追溯。"
            "只看外部 404 的守卫查不出来，必须由 audit 记录断言打红。"
            "注意本条与 Task 1 的 M08 命中同一行但期望不同的测试：M08 覆盖授权阶段，"
            "本条覆盖 Task 2 新增的反查阶段（走公共 audit_denial 包装）。"
        ),
        tags=("req2.5",),
    ),
    # ── 前端宿主契约 ──────────────────────────────────────────────────────────
    Mut(
        id="M14",
        side="fe",
        path=FE_ADAPTER,
        kind="replace",
        anchor="  if (!reportType || !(AI_REPORT_HOST_IDS as readonly string[]).includes(reportType)) {",
        new="  if (false) {  // MUTATED: 报表稳定 ID 不再校验",
        want="绝不把项目 ID 当文档 ID",
        wants=("宿主上下文的真实 DOM 与网络行为",),
        why=(
            "前端报表 adapter 不再校验 report type ⇒ 又能把 projectId / 'cross_check' "
            "当 doc ID 提交（旧 ReportView 的真实缺陷）。守卫须断言这些输入返回不可用，"
            "且真实 mount 后发送按钮禁用、零请求。"
        ),
        tags=("req3.5",),
    ),
    Mut(
        id="M15",
        side="fe",
        path=FE_ADAPTER,
        kind="replace",
        anchor="    projectId: isUuid(projectId) ? projectId : null,",
        # 该行在 knowledge_doc 与 knowledge_folder 两个 adapter 各一次；
        # 用文件夹 adapter 的 type 字面量相对定位。
        scope="    type: 'knowledge_folder',",
        offset=2,
        new="    projectId: (input.projectId as string) ?? null,  // MUTATED: 空串直接透传",
        want="空 project ID 不构造有效项目宿主",
        why=(
            "知识库 adapter 把空串当有效 project ID（旧 KnowledgeBase 传的就是 `''`）⇒ "
            "host.projectId 变成 `''` 且 projectToolsEnabled 误开为 true。"
            "🔴 这里必须**绕过 normalizeId 与 isUuid 两道门**直接取原始入参才是真正放宽："
            "前两版分别只改了 `normalizeId(...)`（被后面的 isUuid 兜住）与只删了 isUuid"
            "（被前面的 normalizeId 兜住），行为都没变 ⇒ 两次判定 GREEN（实为脚本缺陷）。"
            "留此注记提醒：GREEN 必须先归因「变异是否真的改变了行为」再怀疑守卫。"
        ),
        tags=("req3.3", "req3.4"),
    ),
    Mut(
        id="M16",
        side="fe",
        path=FE_ADAPTER,
        kind="replace",
        anchor="  if (typeof n !== 'number' || !Number.isInteger(n) || n < 1900 || n > 2999) return null",
        new="  if (typeof n !== 'number' || !Number.isInteger(n)) return new Date().getFullYear() - 1  // MUTATED",
        want="年度断言不猜",
        why=(
            "年度取不到时改用「当前年份-1」兜底（WorkpaperEditor 的旧写法）⇒ 到服务端"
            "就是伪造断言，直接被判 host_context_mismatch。守卫须断言取不到年度时为 null "
            "且不等于猜测值。"
        ),
        tags=("property2", "req2.3"),
    ),
    Mut(
        id="M17",
        side="fe",
        path=FE_CHAT,
        kind="replace",
        # 带 `{` 的形态只在 sendMessage 出现（fetchHistory / adoptContent 是单行 return）。
        anchor="    if (!hostAvailable.value || !host) {",
        new="    if (false) {  // MUTATED: 宿主不可用也照发请求",
        want="宿主上下文的真实 DOM 与网络行为",
        why=(
            "宿主不可用时仍然发起请求 ⇒ 又回到「doc_id='' / project_id='' 必然失败」的旧行为，"
            "且用户看不到中文原因。守卫用真实 mount + fetch 调用计数判红。"
        ),
        tags=("req3.4",),
    ),
    Mut(
        id="M18",
        side="fe",
        path=FE_REPORT,
        kind="replace",
        anchor="    reportType: activeTab.value,",
        new="    reportType: projectId.value,  // MUTATED: 又把项目 ID 当文档 ID",
        want="ReportView.vue",
        why=(
            "把 ReportView 的宿主标识改回 projectId —— 这是 Req 3.5 明令禁止、"
            "且重构前真实存在的写法。守卫的模板形态判据（adapter 入参里文档位字段"
            "不得直接是 projectId）必须打红。"
        ),
        tags=("req3.5",),
    ),
]


_FE_JSON = Path(__file__).parent / "_wip_mut_dsh_task2_fe.json"

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="dsh-agent-panel-integration Task 2 可信 HostContext 守卫变异检验",
            backend_args=BE_PYTEST_ARGS,
            frontend_filters=FE_FILTERS,
            frontend_dir=FRONTEND,
            vitest_json=_FE_JSON,
            baseline_backend_passed=BASELINE_BE_PASSED,
            baseline_frontend_passed=BASELINE_FE_PASSED,
        )
    )
