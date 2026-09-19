"""Task 6 ChatEngine / NativeEngine 守卫变异检验（spec dsh-agent-panel-integration / Task 6）。

## 为什么需要它

「82 条守卫全绿」只证明当前代码没触发断言，**不证明断言有效**。Task 6 的假绿形态很集中：

- **接线错误被吞成 typed error**：Task 5 的 coordinator 用 ``except Exception`` 把 engine
  的任何异常压成 ``engine_unavailable``。因此"取消信号形态不兼容""``build_engine`` 签名
  不匹配""事件负载键名对不上"这三类错误的**表现完全一样**：AI 不回答、或 manifest /
  citations / usage 静默丢失，而 import、类型检查、以及任何只 grep 符号名的判据全绿。
- **capability 两处各写一份**：表里 ``tools=False``、engine 自称 ``tools=True``，
  前端放开一个后端根本没实现的入口。
- **fail-soft 占位串当正文落库**：用户看到一条"AI 回复"，审计留痕记成一次成功 run。
- **fail-closed 降级成 WARNING**：ContextBuilder 失败只记 WARNING ⇒ 表现是"AI 说上下文
  不足"，而链路其实从未跑通（本仓库最贵的失败模式）。
- **配置门失效**：experimental flag / allowlist 任一被短路，未验收的 DSH 链路直接上线。

唯一可靠的反证是把生产代码**改坏**，看对应守卫是否打红。

## 两条边界

1. **不动 import 期契约**。``run_contract`` 在 import 时校验"run 终态 ↔ terminal event
   一一对应"，破坏它会让模块 import 失败 ⇒ pytest 报**文件级 collection ERROR**
   （短摘要里是文件路径而不是测试名）⇒ 判定落成 WRONG-TEST 而不是 RED。
2. **不动 Task 5 的 ``run_coordinator``**。它与本 Task 并发开发；本脚本只变异 Task 6
   拥有的文件（``engine.py`` / ``native_engine.py``）与三处一行接线
   （``run_service`` 的 engine 解析、router 的 SYSTEM_PROMPT、``adopt`` 的错误码派生）。

## 四态判定

由 ``_mutation_kit`` 统一给出：RED（新增失败含期望项）/ WRONG-TEST（新增失败不含期望项）/
GREEN（无新增失败 = 守卫缺陷）/ ANCHOR-MISS（锚点未唯一命中 = 本脚本缺陷）。退出码不作判据。

用法::

    python backend/scripts/diagnose/mutate_dsh_task6_engine_guards.py --list
    python backend/scripts/diagnose/mutate_dsh_task6_engine_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_dsh_task6_engine_guards.py --run all
    python backend/scripts/diagnose/mutate_dsh_task6_engine_guards.py --run M07
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
    "test_task6_native_engine.py": "Task 6 新建（Property 7/24/33 + engine 契约）",
}

#: 冻结基线（本会话实测 2026-08-22）：82 passed（本文件单独跑，真实 PG）。
#: 改这个数必须同时说明来源。
BASELINE_BE_PASSED = 82

#: 🔴 `-rfE` 而不是 `-rf`：Property 33 / Property 7 的判据挂在**模块级 fixture**
#: （`runs`）上，变异一旦让该 fixture 抛异常，pytest 把 30+ 条判据记为 **ERROR** 而非
#: FAILED。`-rf` 的 short summary **只列 failed**，于是 `_mutation_kit` 的
#: `^ERROR\s+(\S+)` 一条都抓不到 ⇒ 明明打红了却被判 WRONG-TEST（Task 3 的 M07/M08 实测踩过）。
BE_PYTEST_ARGS = [
    "backend/tests/dsh_agent_panel/test_task6_native_engine.py",
    "-q",
    "--tb=no",
    "-rfE",
    "-p",
    "no:randomly",
]

ENGINE = "backend/app/services/ai_chat/engine.py"
NATIVE = "backend/app/services/ai_chat/native_engine.py"
SERVICE = "backend/app/services/ai_chat/run_service.py"
ROUTER = "backend/app/routers/doc_ai_chat.py"
ADOPT = "backend/app/services/ai_chat/adopt.py"

MUTATIONS: list[Mut] = [
    # ── capability 单一真源（Req 10.3 / Property 24）────────────────────────
    Mut(
        id="M01",
        side="be",
        path=ENGINE,
        kind="replace",
        anchor="    return capabilities_for(engine_name)",
        new=(
            "    return EngineCapabilities(\n"
            "        **{**capabilities_for(engine_name).model_dump(), \"tools\": True}\n"
            "    )"
        ),
        want="test_capabilities_returns_the_task4_table_entry_itself",
        wants=("test_native_capabilities_match_actual_behaviour",),
        why=(
            "engine 不再返回 Task 4 的表项本身，而是另造一份并自称支持工具 —— 这正是"
            "「声明支持而实际不支持」的标准形态：前端据 capability 放开工具入口，"
            "而 native 根本没有工具实现。相等断言拦不住「复制一份后各自演化」，"
            "所以判据用 is 同一对象。"
        ),
        tags=("req10.3", "property24"),
    ),
    # ── 与 Task 5 的接线（最贵一类：被 except Exception 吞成 engine_unavailable）──
    Mut(
        id="M02",
        side="be",
        path=ENGINE,
        kind="replace",
        anchor='    flag = getattr(cancel, "is_set", None)',
        new="    flag = None",
        want="test_accepts_task5_coordinator_cancel_signal",
        wants=(
            "test_accepts_bare_asyncio_event",
            "test_task5_cancel_signal_stops_before_any_model_call",
        ),
        why=(
            "只认 canonical 的 async is_cancelled()，不再认 Task 5 coordinator 的 is_set。"
            "coordinator 传进来的信号会在第一次检查时 AttributeError，被它的 "
            "except Exception 吞成 engine_unavailable ⇒ 用户点取消没反应、AI 也不回答，"
            "而 import/类型检查/符号 grep 全绿。"
        ),
        tags=("req4.7", "wiring"),
    ),
    Mut(
        id="M03",
        side="be",
        path=ENGINE,
        kind="replace",
        # 🔴 首轮这条判 WRONG-TEST：原来的 raise 跨四行，整行替换后剩下悬空的实参行
        # ⇒ SyntaxError ⇒ 文件级 collection ERROR（短摘要里是文件路径而不是测试名）。
        # 生产代码已把消息抽成常量、raise 收成单行，锚点才是可整行替换的。
        anchor="    raise EngineFailure(ChatErrorCode.engine_unavailable, detail)",
        new="    return False",
        want="test_unknown_shape_is_rejected_not_silently_false",
        why=(
            "认不出的取消信号形态被当成「未取消」⇒ 取消请求静默失效，run 继续跑到底"
            "（Req 4.7 明令取消要传播到 native generator）。这种 fail-open 在日志里"
            "也看不出来。"
        ),
        tags=("req4.7",),
    ),
    Mut(
        id="M04",
        side="be",
        path=ENGINE,
        kind="replace",
        anchor="    if engine_name is ChatEngineName.native:",
        new="    if True:",
        want="test_build_engine_refuses_unregistered_engine_without_native_fallback",
        why=(
            "任何 engine 名都构造出 NativeEngine ⇒ 配置为 dsh 时静默跑 native 并返回"
            "成功内容，正是 Req 10.5 明令禁止的「DSH 不可用时静默回落 native」。"
            "行为上看不出异常，只有 error code 判据能抓到。"
        ),
        tags=("req10.5",),
    ),
    Mut(
        id="M05",
        side="be",
        path=ENGINE,
        kind="replace",
        anchor="    db: Any,",
        new="    engine_name_first: Any,",
        want="test_task5_default_engine_provider_really_builds_native_engine",
        wants=("test_build_engine_uses_server_selected_name",),
        why=(
            "把 build_engine 的第一个位置参数换名 ⇒ 函数体里的 db 变成 NameError。"
            "Task 5 的 _default_engine_provider 用 builder(db, execution) 调用它，"
            "异常被它的 except Exception 吞成 return None ⇒ 每个 run 都以 "
            "engine_unavailable 结束。这条变异模拟的正是「改了签名却没看调用点」。"
        ),
        tags=("req10.2", "wiring"),
    ),
    Mut(
        id="M06",
        side="be",
        path=NATIVE,
        kind="replace",
        anchor="                ChatEventType.error,",
        new="                ChatEventType.quota,",
        want="test_failure_yields_typed_error_and_no_completed_message",
        wants=("test_error_intent_payload_carries_the_typed_code_only",),
        why=(
            "失败不再产出 error 终态意图 ⇒ Task 5 的 coordinator 收不到 typed code，"
            "只能把一切压成 engine_unavailable，context_build_failed 与"
            "「模型不可用」两个完全不同的排障方向被合并（Req 12.5 要求稳定 error code）。"
        ),
        tags=("req12.5", "property33"),
    ),
    Mut(
        id="M07",
        side="be",
        path=NATIVE,
        kind="replace",
        anchor='                payload={"manifest": dict(outcome.context_manifest)},',
        new="                payload=dict(outcome.context_manifest),",
        want="test_context_ready_payload_uses_manifest_key",
        why=(
            "manifest 从 payload['manifest'] 平铺到顶层 ⇒ Task 5 的 "
            "payload.get('manifest') 读不到，context_manifest 静默落库为 NULL。"
            "事件照发、run 照成功，前端的 Context Inspector 恒空 —— 没有任何错误信号。"
        ),
        tags=("req5.7", "wiring"),
    ),
    Mut(
        id="M08",
        side="be",
        path=NATIVE,
        kind="replace",
        anchor='                    payload={"citations": [dict(c) for c in citations]},',
        new='                    payload={"items": [dict(c) for c in citations]},',
        want="test_citation_payload_uses_citations_key",
        why=(
            "citation 负载键名改掉 ⇒ coordinator 的 payload.get('citations') 读不到，"
            "引用来源静默丢失（用户看到回答但点不到出处，Req 4.10 的可追溯性塌掉）。"
        ),
        tags=("req4.10", "wiring"),
    ),
    Mut(
        id="M09",
        side="be",
        path=NATIVE,
        kind="replace",
        anchor='                    "usage": dict(outcome.usage),',
        new='                    "usage": {},',
        want="test_done_intent_payload_carries_usage_for_the_coordinator",
        why=(
            "终态意图不带 usage ⇒ coordinator 的 _finish_from_engine 取到空 usage，"
            "run 与消息上都没有 token/模型记录（Req 4.10 要求 history 带 usage metadata），"
            "事后既无法核对成本也无法定位是哪个模型答的。"
        ),
        tags=("req4.10",),
    ),
    # ── fail-soft 占位串（Req 12.4 / 12.9 / Property 33）───────────────────
    Mut(
        id="M10",
        side="be",
        path=NATIVE,
        kind="replace",
        anchor="    return any(lowered.startswith(p) for p in PLACEHOLDER_PREFIXES)",
        new="    return False",
        want="test_every_llm_client_fail_soft_literal_is_detected",
        wants=(
            "test_placeholder_chunk_never_becomes_assistant_text",
            "test_failure_yields_typed_error_and_no_completed_message",
        ),
        why=(
            "占位串识别失效 ⇒ 「[LLM 服务熔断中，请稍后重试]」被当作 assistant 正文"
            "落库，用户看到一条「AI 回复」，run 记成功、审计留痕也是成功。"
            "这是 Property 33 要防的最典型假成功。"
        ),
        tags=("req12.4", "req12.9", "property33"),
    ),
    Mut(
        id="M11",
        side="be",
        path=NATIVE,
        kind="replace",
        anchor="    if not s:",
        new="    if False:",
        want="test_empty_is_placeholder",
        wants=("test_empty_model_output_is_a_failure_not_an_empty_success",),
        why=(
            "空文本不再算占位 ⇒ AIService 在 content 为 None 时返回的空串会作为 "
            "completed assistant 消息落库（用户看到一条空回复，run 记成功）。"
        ),
        tags=("req12.9", "property33"),
    ),
    Mut(
        id="M12",
        side="be",
        path=NATIVE,
        kind="replace",
        anchor="        if _breaker.is_open:",
        new="        if False:",
        want="test_open_breaker_short_circuits_before_any_model_call",
        wants=("test_failure_yields_typed_error_and_no_completed_message",),
        why=(
            "熔断打开时仍然调模型 ⇒ 熔断器形同不存在（Req 12.4 要求熔断转 typed error），"
            "下游持续被打，且失败会以占位串或异常的形式绕一大圈才被发现。"
        ),
        tags=("req12.4", "req10.7"),
    ),
    Mut(
        id="M13",
        side="be",
        path=NATIVE,
        kind="replace",
        anchor="        async with _llm_semaphore:",
        new="        if True:",
        want="test_shared_llm_semaphore_is_held_during_streaming",
        why=(
            "不再复用 llm_client 的共享并发许可（Req 10.7 明令复用既有并发限制）⇒ "
            "对话流可以无界并发打到单个本地 vLLM 上，平台其他 LLM 调用被挤死。"
            "功能完全正常，只有余量观测判据能抓到。"
        ),
        tags=("req10.7",),
    ),
    # ── fail-closed 与 ERROR 级日志（本仓库最贵的失败模式）──────────────────
    Mut(
        id="M14",
        side="be",
        path=NATIVE,
        kind="replace",
        anchor="            logger.error(",
        # `logger.error(` 在本文件多处；用 _build_context 独有的消息行相对定位。
        scope='                "run %s ContextBuilder.build 失败（fail-closed，不降级空上下文）："',
        offset=-1,
        new="            logger.warning(",
        want="test_context_build_failure_logs_error_and_typed_code",
        why=(
            "把上下文构建失败降级成 WARNING ⇒ 「函数名/参数名改了、传了错的 host 形态」"
            "这类接线错误只留一条 WARNING，表现是「AI 说上下文不足」而链路其实从未跑通。"
            "typed error 仍然照发，所以只有日志级别判据能抓到。"
        ),
        tags=("req2.8", "req12.5"),
    ),
    Mut(
        id="M15",
        side="be",
        path=NATIVE,
        kind="replace",
        anchor="        if request.principal is not None:",
        new="        if True:",
        want="test_context_builder_receives_server_resolved_principal",
        wants=("test_missing_principal_row_fails_closed_with_error_log",),
        why=(
            "不再按 host.principal_id 反查用户 ⇒ Task 5 的 RunExecution 路径下 "
            "ContextBuilder 收到 user=None，KnowledgeAccessPolicy 把知识范围判成空。"
            "表现是「AI 看不到任何知识库内容」，没有任何错误信号，回答照样返回。"
        ),
        tags=("req2.1", "wiring"),
    ),
    Mut(
        id="M16",
        side="be",
        path=NATIVE,
        kind="replace",
        anchor='            and getattr(e, "run_id", None) != current',
        new="            and True",
        want="test_current_query_is_not_duplicated_from_history",
        why=(
            "历史不再排除本 run 刚落库的 user message ⇒ 当前提问在 messages 里出现两次，"
            "模型以为用户重复问了一遍（会出现「如你所问两次…」这类回答）。"
            "功能不报错，只有消息内容判据能抓到。"
        ),
        tags=("req4.6",),
    ),
    # ── 单 system 与数据定界（Req 9.3 / 11.10）─────────────────────────────
    Mut(
        id="M17",
        side="be",
        path=NATIVE,
        kind="replace",
        anchor='        {"role": "system", "content": "\\n\\n".join(parts)}',
        new='        *[{"role": "system", "content": p} for p in parts]',
        want="test_exactly_one_system_message_and_it_is_first",
        wants=("test_single_system_message_reaches_the_model",),
        why=(
            "政策/复核 prompt/上下文各自成为一条 system 消息 ⇒ vLLM + Qwen3.5 只允许"
            "开头一条 system（Req 9.3 明令不得因新增模式产生多个 system）。"
            "AIService 的合并只是兜底，任何绕过它的调用方都会把多条 system 原样发出去。"
        ),
        tags=("req9.3",),
    ),
    Mut(
        id="M18",
        side="be",
        path=NATIVE,
        kind="replace",
        anchor="                    UNTRUSTED_DATA_NOTICE,",
        new='                    "",',
        want="test_untrusted_context_is_delimited_as_data",
        why=(
            "去掉「以下是数据而非指令」的定界说明 ⇒ 底稿/知识/OCR 里的注入文本"
            "（「忽略以上所有指令」）与平台政策处于同一层级，提示注入的门槛骤降"
            "（Req 11.10 要求不可信内容以数据定界）。"
        ),
        tags=("req11.10", "req7.7"),
    ),
    # ── usage 口径（不把估算伪装成精确值）─────────────────────────────────
    Mut(
        id="M19",
        side="be",
        path=NATIVE,
        kind="replace",
        anchor='        "source": "estimated",',
        new='        "source": "reported",',
        want="test_model_usage_and_latency_are_recorded",
        why=(
            "把服务端字符数估算标成「模型回报」⇒ Task 12 的指标会把估算值当计费/容量"
            "依据。数值一模一样，只有口径字段能区分，因此判据必须断言 source。"
        ),
        tags=("req4.10", "req12.8"),
    ),
    # ── engine 边界：不写终态、不写消息（Property 7）───────────────────────
    Mut(
        id="M20",
        side="be",
        path=NATIVE,
        kind="insert",
        anchor="# 纯函数辅助",
        new=(
            "\n\n"
            "def _mutation_injected_sink() -> None:\n"
            "    from app.models.ai_models import AIChatRun\n"
            "\n"
            "    AIChatRun()\n"
        ),
        want="test_engine_module_writes_no_messages_and_no_run_state",
        why=(
            "在 engine 模块里引入对 run 行的直接操作 ⇒ 终态不再只由 "
            "ChatRunService.finish_* 的 compare-and-set 产生（Property 7 的前提塌掉）。"
            "🔴 注入的是一个**从不被调用**的函数：若注入可执行代码，全部 PG 判据会一起"
            "ERROR，判定就分不清「边界判据打红」和「模块炸了」。"
        ),
        tags=("property7",),
    ),
    # ── engine 选择门（Req 10.1 / 10.6 / Property 24）──────────────────────
    Mut(
        id="M21",
        side="be",
        path=ENGINE,
        kind="replace",
        anchor='    if not bool(getattr(settings, "AI_DSH_ENABLED", False)):',
        new="    if False:",
        want="test_dsh_config_without_experimental_flag_stays_native",
        why=(
            "experimental feature flag 被短路 ⇒ 只要配置里写了 dsh，未通过 custom Cordis"
            " smoke / 双用户隔离 / 无出网验证的 DSH 链路就直接上线（Req 10.6 明令不得"
            "对全部项目开放）。改一个判断就是一次未验收链路全量放开。"
        ),
        tags=("req10.6", "property24"),
    ),
    Mut(
        id="M22",
        side="be",
        path=ENGINE,
        kind="replace",
        anchor="    if project_id not in allowlist:",
        new="    if False:",
        want="test_dsh_flag_on_but_project_not_allowlisted_stays_native",
        why=(
            "项目 allowlist 失效 ⇒ flag 一开就是全部项目启用 DSH，"
            "Task 30 的「逐项目放开」变成一次性全放（Req 10.6）。"
        ),
        tags=("req10.6",),
    ),
    Mut(
        id="M23",
        side="be",
        path=ENGINE,
        kind="replace",
        anchor="            allowed.add(UUID(candidate))",
        new="            allowed.add(candidate)",
        want="test_allowlist_skips_illegal_uuid_without_dropping_the_rest",
        why=(
            "allowlist 不再解析成 UUID ⇒ 名单里的字符串永远匹配不上 UUID 类型的 "
            "project_id（已验收项目静默掉回 native），而写错的项也被收进集合。"
            "两种错都不报错。"
        ),
        tags=("req10.6",),
    ),
    Mut(
        id="M24",
        side="be",
        path=SERVICE,
        kind="replace",
        anchor="        engine, gate_reason = resolve_engine(project_id=host.project_id)",
        new="        engine, gate_reason = resolve_engine_name(), None",
        want="test_dsh_config_without_flag_records_native_on_the_run",
        why=(
            "run 创建退回只读 Task 4 的配置解析 ⇒ Task 6 的 feature flag 与 allowlist"
            "两道门变成死代码（本仓库假绿第①源：新加的能力没有消费方）。"
            "run 会记 engine=dsh 且 capability 快照声明支持工具，前端据此放开工具入口，"
            "而实际执行的是 native。"
        ),
        tags=("req10.1", "req10.6", "property24"),
    ),
    # ── 单一真源收敛（顺手做掉的两处双真源）───────────────────────────────
    Mut(
        id="M25",
        side="be",
        path=ROUTER,
        kind="replace",
        anchor="SYSTEM_PROMPT = NATIVE_SYSTEM_POLICY",
        new='SYSTEM_PROMPT = """你是一名审计顾问。"""',
        want="test_router_system_prompt_is_the_engine_single_source",
        why=(
            "旧 POST 流重新拥有一份自己的政策 prompt ⇒ 同一个问题在旧入口与 run 链路"
            "得到风格不同的回答，而「迁移完成」这件事无法验证（Req 1.8/1.9 的单一内核）。"
        ),
        tags=("nfr2",),
    ),
    Mut(
        id="M26",
        side="be",
        path=ADOPT,
        kind="replace",
        anchor="ADOPT_LOG_FAILED = ChatErrorCode.adopt_log_failed.value",
        new='ADOPT_LOG_FAILED = "adopt_log_write_failed"',
        want="test_adopt_error_code_is_derived_from_chat_error_code",
        why=(
            "采纳失败码与 Chat Run 稳定 error code 重新分叉 ⇒ 前端按 run 的 code 分派，"
            "而采纳接口回的是另一个值（Req 12.5 要求稳定 error code 单一真源）。"
            "两处都能编译、都有中文文案，只有同源判据能抓到。"
        ),
        tags=("req12.5", "nfr2"),
    ),
]

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description=(
                "dsh-agent-panel-integration Task 6 ChatEngine / NativeEngine 守卫变异检验"
            ),
            backend_args=BE_PYTEST_ARGS,
            baseline_backend_passed=BASELINE_BE_PASSED,
        )
    )
