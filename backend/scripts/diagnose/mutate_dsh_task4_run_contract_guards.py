"""Task 4 typed run contract 守卫变异检验（spec dsh-agent-panel-integration / Task 4）。

## 为什么需要它

「92 条守卫全绿」只证明当前代码没触发断言，**不证明断言有效**。Task 4 交付的是整个
Phase A 的协议底座，最贵的假绿形态集中在这里：

- 事件类型 / 错误码取值悄悄漂移（前端按旧常量分派，运行期才炸）；
- 与消息相关的事件不再要求 ``message_id``（单轮对话看不出问题，只在并发多轮串消息）；
- 终态出边被放开、CAS 的 WHERE 被放宽 ⇒ error/cancel 之后还能发 ``done``，
  或者库里躺着一条本不该存在的 completed assistant 消息；
- 重复请求重新保存 user message / 重新放行 engine（幂等退化，用户看到两遍回答）；
- 请求体重新接受 engine / 权限 scope / 客户端正文（越权提交）；
- ``response_model`` 被摘掉 ⇒ 前端类型不再来自 OpenAPI，只能手抄第二份常量。

唯一可靠的反证是把生产代码**改坏**，看对应守卫是否打红。

## 一条重要边界：import 期契约不适合做变异目标

``run_contract`` 在 import 时校验「run 终态 ↔ terminal event 一一对应」，破坏该映射会让
模块 **import 失败**，pytest 报的是**文件级 collection ERROR**（短摘要里是文件路径而不是
测试名）⇒ 判定会落成 WRONG-TEST 而不是 RED。因此本脚本不去动那对映射，而是变异
``NON_TERMINAL_RUN_STATUSES`` 的派生式（同样是「终态语义被放宽」，但不阻断 import）。

## 四态判定

由 ``_mutation_kit`` 统一给出：RED（新增失败含期望项）/ WRONG-TEST（新增失败不含
期望项）/ GREEN（无新增失败 = 守卫缺陷）/ ANCHOR-MISS（锚点未唯一命中 = 本脚本缺陷）。
退出码不作判据。

用法::

    python backend/scripts/diagnose/mutate_dsh_task4_run_contract_guards.py --list
    python backend/scripts/diagnose/mutate_dsh_task4_run_contract_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_dsh_task4_run_contract_guards.py --run all
    python backend/scripts/diagnose/mutate_dsh_task4_run_contract_guards.py --restore
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _mutation_kit import Mutation as Mut  # noqa: E402
from _mutation_kit import run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

#: 本 Task 创建的守卫文件全集（覆盖面分母）。新增守卫文件必须同时加一条变异。
GUARD_FILES: dict[str, str] = {
    "test_task4_run_contract.py": "Task 4 新建（Property 6/7 + typed contract 契约）",
}

#: 冻结基线（本会话实测 2026-08-22）：93 passed（本文件单独跑）。
#: 首轮变异后由 92 升到 93 —— M06 判 WRONG-TEST 暴露了自证型参数化，补了一条固定期望
#: 集合的判据（``test_message_bound_set_is_exactly_the_three_content_events``）。
#: 改这个数必须同时说明来源。
BASELINE_BE_PASSED = 93

#: 🔴 `-rfE` 而不是 `-rf`：并发判据挂在**模块级 fixture**（`concurrency`）上，变异一旦让
#: 该 fixture 抛异常，pytest 把 3 条判据记为 **ERROR** 而非 FAILED。`-rf` 的 short summary
#: **只列 failed**，于是 `_mutation_kit` 的 `^ERROR\s+(\S+)` 一条都抓不到 ⇒ 明明打红了
#: 却被判 WRONG-TEST（Task 3 的 M07/M08 实测踩过）。
BE_PYTEST_ARGS = [
    "backend/tests/dsh_agent_panel/test_task4_run_contract.py",
    "-q",
    "--tb=no",
    "-rfE",
    "-p",
    "no:randomly",
]

CONTRACT = "backend/app/services/ai_chat/run_contract.py"
SERVICE = "backend/app/services/ai_chat/run_service.py"
CONFIG = "backend/app/core/config.py"
ROUTER = "backend/app/routers/doc_ai_chat.py"

MUTATIONS: list[Mut] = [
    # ── 契约取值域 ↔ design.md 双向（Req 4.3 / 12.5）────────────────────────
    Mut(
        id="M01",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='    context_ready = "context_ready"',
        # 🔴 同 M02：只改**取值**、保留成员名。连成员名一起改会让守卫文件里
        # `ChatEventType.context_ready` 的模块级引用炸在 import 期 ⇒ 文件级 collection
        # ERROR ⇒ 判定落成 WRONG-TEST（本会话首轮实测踩过，第二轮才修）。
        new='    context_ready = "context_prepared"',
        want="test_event_types_equal_design_list",
        wants=("test_openapi_enum_values_equal_python_enum",),
        why=(
            "事件类型取值漂移一个词 ⇒ 前端按 design 写的 context_ready 分支永远命中不到"
            "（Context Manifest 面板恒空），而后端认为已经发出去了。Python 侧成员名没变、"
            "所有引用照旧编译，只统计事件条数或只查「枚举类存在」的判据抓不到。"
        ),
        tags=("req4.3", "contract"),
    ),
    Mut(
        id="M02",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='    local_only_violation = "local_only_violation"',
        # 🔴 只改**取值**、保留成员名：连成员名一起改会让 ERROR_MESSAGE_ZH 里的
        # ChatErrorCode.local_only_violation 引用炸在 import 期 ⇒ 整个文件 collection
        # ERROR，短摘要里是文件路径而不是测试名，判定落成 WRONG-TEST（本会话实测踩过）。
        # 本条要检验的是「取值漂移能否被 design ↔ 代码比对抓到」，不是「能否炸掉 import」。
        new='    local_only_violation = "local_only_violation_v2"',
        want="test_error_codes_equal_design_list",
        wants=("test_openapi_enum_values_equal_python_enum",),
        why=(
            "稳定 error code 的取值漂移。错误码是跨前后端与审计日志的契约，改了值等于让"
            "历史审计记录与新代码对不上号（Req 12.5 明确要求稳定），而 Python 侧的成员名"
            "没变、所有引用照旧编译 —— 只有与 design 清单比对的判据能抓到。"
        ),
        tags=("req12.5", "contract"),
    ),
    Mut(
        id="M03",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='RUN_EVENTS_URL_TEMPLATE = "/api/ai-chat/runs/{run_id}/events"',
        new='RUN_EVENTS_URL_TEMPLATE = "/api/ai-chat/run-events/{run_id}"',
        want="test_run_endpoint_paths_match_design_api_surface",
        why=(
            "创建响应里回给前端的 events_url 与 design／Task 5 将注册的真实路由分叉 ⇒ "
            "前端拿到一个 404 地址，表现是发完消息永远等不到回复。"
        ),
        tags=("req4.1", "contract"),
    ),
    Mut(
        id="M04",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor="MENTION_RESOURCE_TYPES: frozenset[ResourceType] = frozenset(ResourceType) - {",
        new="MENTION_RESOURCE_TYPES: frozenset[ResourceType] = frozenset(ResourceType) | {",
        want="test_mention_types_are_the_seven_design_values",
        wants=("test_mention_rejects_non_mentionable_type_and_label",),
        why=(
            "把宿主模式 global_knowledge 也当成可引用资源 ⇒ 客户端能提交一个没有实例、"
            "没有授权路径的 mention，下游授权层对它 fail-closed，表现为引用了但永远"
            "拿不到内容。"
        ),
        tags=("req4.2", "contract"),
    ),
    # ── 事件形状（Req 4.4）─────────────────────────────────────────────────
    Mut(
        id="M05",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor="        if self.type in MESSAGE_BOUND_EVENT_TYPES and self.message_id is None:",
        new="        if False:",
        want="test_message_bound_events_require_message_id",
        why=(
            "delta／citation／done 不再强制携带服务端签发的 message_id。单轮对话下前端会"
            "把片段挂到当前消息上，看不出问题；并发多轮才串消息 —— 最难复现的一类，"
            "必须由契约层拦住。"
        ),
        tags=("req4.4",),
    ),
    Mut(
        id="M06",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor="    {ChatEventType.delta, ChatEventType.citation, ChatEventType.done}",
        new="    set(ChatEventType)",
        want="test_non_message_events_do_not_require_message_id",
        wants=("test_message_bound_set_is_exactly_the_three_content_events",),
        why=(
            "反向过头：要求**所有**事件都带 message_id ⇒ error／cancelled 只能伪造一个"
            "消息 ID，而 Req 4.5 明确此时没有 completed assistant 消息。"
            "🔴 本条曾判 WRONG-TEST：期望用例原先以「全集减去被测集合」为参数，集合改成"
            "全集后参数集为空、用例静默消失。参数已改为硬编码七类，并补了固定期望集合的"
            "判据 —— 自证型参数化是本仓库一类反复出现的守卫缺陷。"
        ),
        tags=("req4.4", "req4.5"),
    ),
    Mut(
        id="M07",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor="EVENT_ID_WIDTH = 12",
        new="EVENT_ID_WIDTH = 1",
        want="test_event_ids_sort_identically_as_strings_and_numbers",
        why=(
            "去掉零填充 ⇒ event ID 的字典序与数值序不再一致（十 小于 九）。Last-Event-ID "
            "续传按字符串比较时会丢事件或重放事件（Req 4.8／Property 9 的前提），"
            "而单条事件看上去完全正常。"
        ),
        tags=("req4.4", "req4.8"),
    ),
    # ── 状态机与终态语义（Req 4.5 / Property 7）────────────────────────────
    Mut(
        id="M08",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor="    ChatRunStatus.error: frozenset(),",
        new="    ChatRunStatus.error: frozenset({ChatRunStatus.done}),",
        want="test_terminal_states_have_no_outgoing_transitions",
        wants=("test_engine_error_blocks_later_done_and_completed_message",),
        why=(
            "给 error 终态开一条到 done 的出边 ⇒ 失败之后还能改判成功，并连带写出一条 "
            "completed assistant 消息。Property 7 明令终态恰好一个。"
        ),
        tags=("req4.5", "property7"),
    ),
    Mut(
        id="M09",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor="    s for s in ChatRunStatus if s not in CHAT_RUN_TERMINAL_STATUSES",
        new="    s for s in ChatRunStatus",
        want="test_terminal_statuses_and_events_are_bijective",
        wants=("test_engine_error_blocks_later_done_and_completed_message",),
        why=(
            "把终态也算进非终态集合 ⇒ emit() 的终态门失效，run 结束后仍能追加业务事件"
            "（Req 4.5 明令拒绝）。派生式退化一处，两个层面同时塌。"
        ),
        tags=("req4.5", "property7"),
    ),
    Mut(
        id="M10",
        side="be",
        path=SERVICE,
        kind="replace",
        anchor="                AIChatRun.status.in_([s.value for s in allowed_from]),",
        new="                AIChatRun.id == run_id,",
        want="test_engine_error_blocks_later_done_and_completed_message",
        wants=(
            "test_no_late_done_or_assistant_message_after_terminal",
            "test_hundred_concurrent_terminals_yield_exactly_one_terminal_event",
            "test_cancel_blocks_later_done_and_completed_message",
        ),
        why=(
            "把 compare-and-set 的状态条件拿掉 ⇒ UPDATE 变成无条件覆盖，每个并发调用都"
            "自称胜出。这是 Property 7 的**核心**变异：只有真并发＋真 PG 行锁的判据能"
            "抓住，单线程顺序调用下最后一个赢看起来也很正常。"
        ),
        tags=("req4.5", "property7"),
    ),
    Mut(
        id="M11",
        side="be",
        path=SERVICE,
        kind="replace",
        anchor="        if not won:",
        # 该行在 transition / finish_success / finish_error / finish_cancelled 中各一次；
        # 用 finish_success 独有的后随行 `return None, None`（唯一）相对定位。
        scope="            return None, None",
        offset=-1,
        new="        if False:",
        want="test_engine_error_blocks_later_done_and_completed_message",
        wants=(
            "test_cancel_blocks_later_done_and_completed_message",
            "test_hundred_concurrent_terminals_yield_exactly_one_terminal_event",
        ),
        why=(
            "CAS 落空后仍然写 completed assistant 消息 ⇒ run 落库 error／cancelled，库里"
            "却躺着一条成功回复（Property 7 明令不存在）。这正是先写消息再改状态那种"
            "实现的真实后果。"
        ),
        tags=("req4.5", "property7"),
    ),
    Mut(
        id="M12",
        side="be",
        path=SERVICE,
        kind="replace",
        anchor="        if event_type in TERMINAL_EVENT_TYPES:",
        new="        if False:",
        want="test_transition_rejects_illegal_expected_states",
        why=(
            "允许经 emit() 直接签发终态事件 ⇒ 绕过 compare-and-set 发出第二个终态"
            "（库里状态没变，流里已经 done）。这条路径必须被显式堵死。"
        ),
        tags=("req4.5", "property7"),
    ),
    Mut(
        id="M13",
        side="be",
        path=SERVICE,
        kind="replace",
        anchor="        nxt = self._seq.get(run_id, RUN_STARTED_EVENT_SEQ) + 1",
        new="        nxt = RUN_STARTED_EVENT_SEQ + 1",
        want="test_sequencer_is_strictly_monotonic_and_starts_after_run_started",
        wants=("test_engine_error_blocks_later_done_and_completed_message",),
        why=(
            "事件序号不再单调（恒为同一个值）⇒ Last-Event-ID 续传永远回到同一点，重连后"
            "重复接收或整段丢失（Req 4.4 要求单调）。"
        ),
        tags=("req4.4",),
    ),
    # ── 幂等创建（Req 4.6 / Property 6）───────────────────────────────────
    Mut(
        id="M14",
        side="be",
        path=SERVICE,
        kind="replace",
        anchor="        if created:",
        new="        if True:",
        want="test_repeat_requests_return_original_run_without_new_message",
        wants=("test_hundred_concurrent_creates_produce_one_run_one_message",),
        why=(
            "重复提交也保存一遍 user message ⇒ 用户点两下就在历史里看到两条同样的提问，"
            "模型上下文也被污染（Req 4.6 明令不重复保存）。run 行数仍是 1，只查 run "
            "行数的判据抓不到。"
        ),
        tags=("req4.6", "property6"),
    ),
    Mut(
        id="M15",
        side="be",
        path=SERVICE,
        kind="replace",
        anchor="            if existing is None or existing.id != request.session_id:",
        new="            if False:",
        want="test_forged_session_id_is_rejected_before_session_upsert",
        why=(
            "客户端提交的 session_id 不再校验 ⇒ 可以把一次 run 挂到别人的会话上"
            "（跨会话注入）。断言落在连会话都不许创建的真实行数差上。"
        ),
        tags=("req4.2", "req4.6"),
    ),
    Mut(
        id="M16",
        side="be",
        path=SERVICE,
        kind="replace",
        anchor="            timestamp=self.queued_at,",
        new="            timestamp=_now(),",
        want="test_run_started_event_is_deterministic_across_replays",
        why=(
            "run_started 的时间戳改用当前时刻 ⇒ 每次重放都是一条新事件，客户端按 event "
            "去重失效，重复渲染同一个 run 的开始（Req 4.6）。"
        ),
        tags=("req4.4", "req4.6"),
    ),
    Mut(
        id="M17",
        side="be",
        path=SERVICE,
        kind="replace",
        anchor="            review_mode=request.review_mode,",
        new="            review_mode=None,",
        want="test_review_mode_is_persisted_on_server_session",
        why=(
            "复核模式不再落到服务端会话 ⇒ 只能靠前端 localStorage 记住（Req 9.5 明令"
            "禁止），换设备／换标签页即丢，且无作用域隔离。"
        ),
        tags=("req9.5",),
    ),
    Mut(
        id="M18",
        side="be",
        path=SERVICE,
        kind="replace",
        anchor="            capability_snapshot=capabilities.model_dump(),",
        new="            capability_snapshot=None,",
        want="test_capability_snapshot_is_written_to_run_row",
        why=(
            "capability 快照不落库 ⇒ 事后无法回答这次执行当时支不支持工具／附件"
            "（Req 10.3 的可追溯性），排障只能靠猜当时的配置。"
        ),
        tags=("req10.3",),
    ),
    # ── 越权字段与 engine 选择（Req 4.2 / 10.1）───────────────────────────
    Mut(
        id="M19",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='    model_config = ConfigDict(extra="forbid")',
        new='    model_config = ConfigDict(extra="ignore")',
        want="test_unknown_field_is_rejected_by_extra_forbid",
        why=(
            "请求体改为忽略未声明字段 ⇒ 客户端塞进来的任何东西都被静默丢弃（Req 10.4 "
            "明令禁止提交后由后端静默忽略），前端以为生效了。"
        ),
        tags=("req4.2",),
    ),
    Mut(
        id="M20",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor="        found = sorted(_scan_privileged(data))",
        new="        found = []",
        want="test_each_privileged_field_is_rejected_by_name",
        wants=("test_privileged_field_nested_in_host_or_mention_is_rejected",),
        why=(
            "越权字段扫描被短路。extra=forbid 仍会拒绝，但给的是 pydantic 的英文 "
            "Extra inputs are not permitted —— 判据要求**点名的中文原因**（NFR-5），"
            "正是为了让扫描是否真的在跑可判。"
        ),
        tags=("req4.2",),
    ),
    Mut(
        id="M21",
        side="be",
        path=CONTRACT,
        kind="replace",
        anchor='        "extra_scopes",',
        new='        "legacy_extra_scopes",',
        want="test_privileged_list_covers_the_four_req_4_2_categories",
        why=(
            "从越权清单里悄悄摘掉一个字段（extra_scopes 正是 Req 5.8 要删的旧双轨）。"
            "🔴 以清单自身为参数的那条用例**不会**因此变红（少一个用例而已）—— 必须有"
            "固定期望子集的判据才抓得到。"
        ),
        tags=("req4.2", "req5.8"),
    ),
    Mut(
        id="M22",
        side="be",
        path=CONFIG,
        kind="replace",
        anchor='    AI_CHAT_ENGINE: str = "native"',
        new='    AI_CHAT_ENGINE: str = "dsh"',
        want="test_engine_is_resolved_from_server_config_only",
        wants=("test_capability_snapshot_is_written_to_run_row",),
        why=(
            "默认引擎从 native 改成尚未通过运行时安全验收的 dsh（Req 10.1 明确默认 "
            "native，Req 10.6 要求 DSH 只在 feature flag ＋ allowlist 下启用）。这是一次"
            "改一个字面量就能造成的未验收链路全量上线。"
        ),
        tags=("req10.1", "req10.6"),
    ),
    # ── OpenAPI 暴露（NFR-2）──────────────────────────────────────────────
    Mut(
        id="M23",
        side="be",
        path=ROUTER,
        kind="replace",
        anchor="    response_model=ChatRunAccepted,",
        new="    response_model=None,",
        want="test_type_is_present_in_components",
        wants=(
            "test_openapi_enum_values_equal_python_enum",
            "test_capabilities_manifest_declares_all_eight_req_10_3_fields",
        ),
        why=(
            "摘掉 response_model ⇒ ChatRunAccepted／ChatEvent／EngineCapabilities／"
            "ChatErrorCode 全部不再进 OpenAPI components，前端只能手抄第二份常量"
            "（NFR-2 单一真源塌掉）。接口行为完全不变，只有 schema 判据能抓到。"
        ),
        tags=("nfr2",),
    ),
]

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="dsh-agent-panel-integration Task 4 typed run contract 守卫变异检验",
            backend_args=BE_PYTEST_ARGS,
            baseline_backend_passed=BASELINE_BE_PASSED,
        )
    )
