#!/usr/bin/env python
"""DSH Agent Panel Integration 守卫的**变异检验**（只读式破坏 + 字节级还原）。

## 为什么需要它

守卫「全绿」有两种可能：判据真的在保护代码，或判据根本抓不到东西（假绿）。
本脚本对每个锚点**故意改坏一处**，跑对应守卫，看它是否**打红且打红的正是预期那条**。

## 🔴 四态判定（只看 exit code 会把后三态误判成 RED）

======  ============================================================
RED     打红，且新增失败里含预期测试名 ⇒ 判据有效
GREEN   没打红 ⇒ **守卫缺陷**（判据抓不到这个改动）
MISS    锚点未命中或命中 >1 ⇒ **本脚本缺陷**（不是代码没问题）
WRONG   打红了但新增失败不含预期测试名 ⇒ 污染残留或锚点错行
======  ============================================================

## 用法

    python backend/scripts/diagnose/mutate_dsh_agent_panel_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_dsh_agent_panel_guards.py --list
    python backend/scripts/diagnose/mutate_dsh_agent_panel_guards.py              # 全跑
    python backend/scripts/diagnose/mutate_dsh_agent_panel_guards.py --only be    # 只跑后端
    python backend/scripts/diagnose/mutate_dsh_agent_panel_guards.py --only fe    # 只跑前端
    python backend/scripts/diagnose/mutate_dsh_agent_panel_guards.py --restore    # 清 .bak

spec: .kiro/specs/dsh-agent-panel-integration/ (Task 33)
Validates: Requirements 14.4
Properties: 1–40
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]
ROOT = _BACKEND.parent
FRONTEND = ROOT / "audit-platform" / "frontend"

_BAK_SUFFIX = ".mutate-dsh.bak"

#: 子进程环境：中文输出必须 UTF-8
ENV = dict(os.environ, PYTHONIOENCODING="utf-8")


# ─────────────────────────── 数据模型 ───────────────────────────


@dataclass(frozen=True)
class Mutation:
    """一个变异锚点。

    Attributes:
        name: 人类可读的变异名（报告用）。
        target: 被改坏的**生产/数据**文件（相对仓库根）。
        anchor: 要替换掉的**单行**文本（须在目标文件里恰好出现 1 次）。
        replacement: 替换成什么（空串 = 删掉该行内容）。
        expect_test: 预期打红的测试名片段（判 RED 用；空 = 只要有新增失败即算 RED）。
        suite: 跑哪个测试套（``be`` 后端 pytest / ``fe`` 前端 vitest）。
        selector: pytest 的路径/nodeid，或 vitest 的文件名过滤词。
    """

    name: str
    target: str
    anchor: str
    replacement: str
    expect_test: str
    suite: str
    selector: str


@dataclass
class Outcome:
    mutation: Mutation
    verdict: str = ""
    detail: str = ""
    new_fails: list[str] = field(default_factory=list)


# ─────────────────────────── 锚点登记 ───────────────────────────

# --- 后端生产代码路径 ---
_ACCESS = "backend/app/services/ai_chat/access.py"
_HOST_CTX = "backend/app/services/ai_chat/host_context.py"
_RUN_CONTRACT = "backend/app/services/ai_chat/run_contract.py"
_RUN_COORD = "backend/app/services/ai_chat/run_coordinator.py"
_NATIVE_ENGINE = "backend/app/services/ai_chat/native_engine.py"
_ADOPT = "backend/app/services/ai_chat/adopt.py"
_CTX_BUDGET = "backend/app/services/ai_chat/context_budget.py"
_ADDR_INDEX = "backend/app/services/ai_chat/address_index_source.py"
_ADDR_MENTION = "backend/app/services/ai_chat/address_mention.py"
_MENTION_SVC = "backend/app/services/ai_chat/mention_service.py"
_ATTACHMENT = "backend/app/services/ai_chat/attachment_service.py"
_NOTE_SVC = "backend/app/services/ai_chat/note_service.py"
_REVIEW_MODE = "backend/app/services/ai_chat/review_mode.py"
_MCP_TOKEN = "backend/app/services/ai_chat/mcp_token.py"
_MCP_ROUTER = "backend/app/routers/ai_chat_mcp.py"
_MCP_TOOLS = "backend/app/services/ai_chat/mcp_tools.py"
_KB_INDEX = "backend/app/services/knowledge_index_service.py"
_DSH_ENGINE = "backend/app/services/ai_chat/dsh_engine.py"
_DSH_MASKING = "backend/app/services/ai_chat/dsh_masking.py"
_CAPABILITY = "backend/app/services/ai_chat/capability_endpoint.py"
_CONTRACTS = "backend/app/services/ai_chat/contracts.py"

# --- 前端生产代码路径 ---
_FE_RUN_STATE = "audit-platform/frontend/src/stores/chatRunState.ts"
_FE_SSE = "audit-platform/frontend/src/utils/sse.ts"
_FE_PANEL = "audit-platform/frontend/src/components/ai/PlatformAiChatPanel.vue"
_FE_CACHE = "audit-platform/frontend/src/utils/aiChatCacheCleanup.ts"
_FE_SANITIZE = "audit-platform/frontend/src/composables/useSanitize.ts"
_FE_NOTE_CAPTURE = "audit-platform/frontend/src/composables/useAiNoteCapture.ts"
_FE_REVIEW_BAR = "audit-platform/frontend/src/components/ai/ChatReviewModeBar.vue"
_FE_CTX_INSPECTOR = "audit-platform/frontend/src/components/ai/ChatContextInspector.vue"
_FE_CHAT = "audit-platform/frontend/src/composables/usePlatformAiChat.ts"
_FE_CTX_MANIFEST = "audit-platform/frontend/src/utils/chatContextManifest.ts"

# --- 测试套选择器 ---
_BE_PHASE_A = "backend/tests/dsh_agent_panel/test_task13_phase_a_guards.py"
_BE_PHASE_B = "backend/tests/dsh_agent_panel/test_task24_phase_b_guards.py"
_BE_PHASE_C = "backend/tests/dsh_agent_panel/test_task31_phase_c_gate.py"
_BE_ACCESS = "backend/tests/dsh_agent_panel/test_task1_resource_access.py"
_BE_HOST = "backend/tests/dsh_agent_panel/test_task2_host_context.py"
_BE_RUN = "backend/tests/dsh_agent_panel/test_task4_run_contract.py"
_BE_COORD = "backend/tests/dsh_agent_panel/test_task5_run_coordinator.py"
_BE_ENGINE = "backend/tests/dsh_agent_panel/test_task6_native_engine.py"
_BE_ADOPT = "backend/tests/dsh_agent_panel/test_task7_adopt_fail_closed.py"
_BE_DSH = "backend/tests/dsh_agent_panel/test_task28_dsh_engine.py"
_BE_MCP = "backend/tests/test_ai_chat_mcp_token.py"
_BE_MCP_DATA = "backend/tests/test_ai_chat_mcp_tools_data.py"
_BE_MASKING = "backend/tests/test_ai_chat_task29_dsh_masking.py"
_FE_PHASE_A = "PlatformAiChatPhaseA"
_FE_REACHABILITY = "AiRenderHostReachability"
_FE_RUN_PAYLOAD = "PlatformAiChatRunPayload"
_FE_RUN_STATE_TEST = "chatRunState"
#: 🔴 `sseEventTypes.spec.ts` 测的是 `@/types/sse` 的 **SSEEventType 联合类型**，
#: 与 `utils/sse.ts` 的解析器无关 —— M06 曾误用它作 selector ⇒ 实跑 GREEN（跑错套）。
#: 跨 chunk buffer 的真实判据在 `utils/__tests__/sse.spec.ts`（任意分片等价 41 例）。
#: `sse.spec` 在 frontend/src 下唯一匹配该文件（已实测：sseEventTypes / useSSEReconnect /
#: useProcedureTaskSse / sseConsolidationGuard 均不匹配）。
_FE_SSE_PARSER_TEST = "sse.spec"
_FE_PHASE_B_GATE = "PhaseBGateGuards"

MUTATIONS: tuple[Mutation, ...] = (
    # ────────────────────── Phase A ──────────────────────

    # ① 移除前置 gate（access.py 的 authorize_host fail-closed 改为 pass）
    #    🔴 ExternalNotFound() 出现 2 次（enforce_host + enforce_resource），
    #    改用 authorize_host 内的唯一 fail-closed 注释行作锚点。
    Mutation(
        name="移除前置 gate（authorize_host 异常不 fail-closed）",
        target=_ACCESS,
        anchor="        except Exception as exc:  # noqa: BLE001 — Req 2.8 授权服务异常 fail-closed",
        replacement="        except Exception:  # MUTATED: fail-open, return allow\n            return AccessDecision(allowed=True, principal_id=principal_id, project_id=None, denial_code=None)",
        expect_test="",
        suite="be",
        selector=_BE_ACCESS,
    ),

    # ② 调换 host loader（note 走 workpaper 的 locator）
    Mutation(
        name="调换 host loader（note 改用 workpaper locator）",
        target=_HOST_CTX,
        anchor="            HostType.note: self._locate_note,",
        replacement="            HostType.note: self._locate_workpaper,  # MUTATED",
        expect_test="",
        suite="be",
        selector=_BE_HOST,
    ),

    # ③ 去掉 unique（run_contract 的 MentionRef.id min_length 校验）
    Mutation(
        name="去掉 MentionRef id min_length 校验",
        target=_RUN_CONTRACT,
        anchor='    id: str = Field(..., min_length=1, max_length=128, description="资源稳定 ID")',
        replacement='    id: str = Field(..., max_length=128, description="资源稳定 ID")  # MUTATED: no min',
        expect_test="non_null_id",
        suite="be",
        selector=_BE_PHASE_B,
    ),

    # ④ error 后发 done（terminal CAS 改为允许所有迁移）
    Mutation(
        name="error 后发 done（破坏终态唯一性）",
        target=_RUN_CONTRACT,
        anchor="    return new in ALLOWED_RUN_TRANSITIONS.get(current, frozenset())",
        replacement="    return True  # MUTATED: allow all transitions",
        expect_test="terminal",
        suite="be",
        selector=_BE_RUN,
    ),

    # ⑤ 取消不传 child（coordinator cancel 不设 remote 标记）
    Mutation(
        name="取消不传 child（cancel 不设跨进程标记）",
        target=_RUN_COORD,
        anchor="        signalled = await self._cancels.request(run_id)",
        replacement="        signalled = False  # MUTATED: cancel not propagated",
        expect_test="cancel",
        suite="be",
        selector=_BE_COORD,
    ),

    # ⑥ SSE 拆包（feedChunk 不处理跨 chunk buffer）
    #    🔴 selector 原为 `sseEventTypes`（类型联合测试，与解析器无关）⇒ 实跑 GREEN。
    #    改指 `utils/__tests__/sse.spec.ts` 的「任意分片等价」组。
    Mutation(
        name="SSE 拆包（feedChunk 清空 buffer 而非累积）",
        target=_FE_SSE,
        anchor="  state.buffer += chunk",
        replacement="  state.buffer = chunk  // MUTATED: no accumulation",
        expect_test="每字节分片结果与基线一致",
        suite="fe",
        selector=_FE_SSE_PARSER_TEST,
    ),

    # ⑦ 放宽 attachment owner（跳过 owner 校验）
    #    attachment_service.py 里 owner 校验行 `if att.owner_id != owner_id:` 出现时
    #    带上下文来唯一化。
    #    🔴 原 expect_test="owner" 对应的 `test_cross_user_attachment_rejected` 是
    #    fail-open 守卫：调用签名写错 ⇒ 恒抛 TypeError，而断言是 `raises(Exception)`
    #    ⇒ 实跑 GREEN。已改为断言**返回列表过滤掉他人附件**的行为判据。
    Mutation(
        name="放宽 attachment owner 校验",
        target=_ATTACHMENT,
        anchor="            if att.owner_id != owner_id:",
        replacement="            if False:  # MUTATED: owner check removed",
        expect_test="test_cross_user_attachment_is_filtered_out_of_run",
        suite="be",
        selector=_BE_PHASE_B,
    ),

    # ⑧ 采纳信任客户端（adopt 不从 DB 读取正文）
    Mutation(
        name="采纳信任客户端正文（不从 DB 读取）",
        target=_ADOPT,
        anchor='    text = row.message_text or ""',
        replacement='    text = "MUTATED CLIENT TEXT"  # MUTATED: trust client',
        expect_test="adopt",
        suite="be",
        selector=_BE_ADOPT,
    ),

    # ⑨ 启用 semantic fallback（地址搜索不返回 semantic_unavailable）
    #    address_index_source.py 没有显式 SearchResult 返回 —— 功能在 fetch_texts 里。
    #    改为删除 EmbeddingUnavailableError 类定义使其被引用方报 ImportError。
    #    🔴 原 Property 16 判据是**源码字符串**且带恒真 `or` 子句，且两个消费方都是
    #    **函数体内惰性 import**（改名只在调用期炸）⇒ Phase B 没触达 ⇒ 实跑 GREEN。
    #    已补：真调 `semantic_search_strict` 断言抛权威类型 + 消费方类对象同一性。
    Mutation(
        name="启用 semantic fallback（EmbeddingUnavailableError 改名使 raise 路径失效）",
        target=_ADDR_INDEX,
        anchor='class EmbeddingUnavailableError(RuntimeError):',
        replacement='class _EmbeddingUnavailableError_DEAD(RuntimeError):  # MUTATED',
        expect_test="canonical_error_not_lexical_fallback",
        suite="be",
        selector=_BE_PHASE_B,
    ),

    # ⑩ 复用跨用户 token（MCP token 不校验 user_id）
    #    🔴 expect_test 曾写 "user_id" —— 该串在测试源正文里确实存在（参数名/断言里），
    #    所以 --check-anchors 静态通过；但**测试名**是 `test_wrong_user_rejected`，
    #    实跑判定成 WRONG-TEST。expect_test 必须是**测试名**片段而非源码任意片段。
    Mutation(
        name="复用跨用户 MCP token（跳过 user_id 校验）",
        target=_MCP_TOKEN,
        anchor="        if expected_user_id is not None and payload.user_id != expected_user_id:",
        replacement="        if False:  # MUTATED: cross-user token reuse",
        expect_test="wrong_user_rejected",
        suite="be",
        selector=_BE_MCP,
    ),

    # ⑪ 移除前端终态 guard（error 后接受 delta）
    Mutation(
        name="移除前端终态 guard（error 后接受 delta）",
        target=_FE_RUN_STATE,
        anchor="    if (isTerminal.value) {",
        replacement="    if (false) { // MUTATED: terminal guard removed",
        expect_test="dispatch",
        suite="fe",
        selector=_FE_PHASE_A,
    ),

    # ⑫ 恢复 localStorage 正文（缓存清理不删除 AI 消息 key）
    #    🔴 原 expect_test="localStorage" + Property 35 的四条 grep 式判据 ⇒ 实跑 GREEN：
    #    改前缀让清理函数一个 key 都不删，而「源码里有 clearLegacyAiChatCache」依旧成立。
    #    已补行为判据（真播种 localStorage → 调真实清理函数 → 断言正文消失）。
    Mutation(
        name="恢复 localStorage 正文（清理函数跳过 legacy 前缀）",
        target=_FE_CACHE,
        anchor="const LEGACY_CACHE_PREFIX = 'doc_ai_chat_'",
        replacement="const LEGACY_CACHE_PREFIX = '__never_match__'  // MUTATED: nothing cleaned",
        expect_test="clearOnLogout 删除全部",
        suite="fe",
        selector=_FE_PHASE_A,
    ),

    # ⑬ DSH 失败降级（DshEngine SDK 不可用时不 raise）
    #    🔴 原判据只看**最终错误码** engine_unavailable —— 而 `_run` 里 SDK 门之后的
    #    上下文创建 / MCP 进程 / handshake 失败**也都**抛 engine_unavailable ⇒ 去掉门
    #    只是换个地方失败，结果码不变 ⇒ 实跑 GREEN。
    #    已补：直调门断言抛/放行 + 断言门后副作用（上下文、MCP 进程）一次都没发生。
    Mutation(
        name="DSH 失败降级到 native（_verify_sdk_available 不 raise）",
        target=_DSH_ENGINE,
        anchor='    def _verify_sdk_available(self) -> None:',
        replacement='    def _verify_sdk_available(self) -> None:\n        return  # MUTATED: skip sdk check',
        expect_test="test_verify_sdk_gate_raises_when_discovery_unavailable",
        suite="be",
        selector=_BE_DSH,
    ),

    # ⑭ 切 cloud model（capability endpoint 不做 local-only 校验）
    #    validate_model_route 出现 2 次（model + embedding），用 docstring 行唯一化
    #    🔴 原判据全在 `startup_health.run_ai_chat_startup_health_check` 上，而
    #    `/capabilities` 的 health 走**另一套实现** `_collect_service_health →
    #    _check_model_health`，此前零取值覆盖（唯一触达者只断言字段存在）⇒ 实跑 GREEN。
    #    已补取值判据 + 两套实现结论一致性判据。
    Mutation(
        name="切 cloud model（_check_model_health 不做 local-only 校验）",
        target=_CAPABILITY,
        anchor='    """检查模型 endpoint 是否为本地（Req 12.1 / 12.2）。"""',
        replacement='    """检查模型 endpoint 是否为本地（Req 12.1 / 12.2）。"""\n    return ServiceHealth(available=True, endpoint="(mutated)", message="MUTATED: skip check")',
        expect_test="test_cloud_model_endpoint_reported_local_only_violation",
        suite="be",
        selector="backend/tests/dsh_agent_panel/test_task30_capabilities.py",
    ),

    # ⑮ 脱敏未知角色不 fail-closed（DSH masking）
    #    raise MaskingDenied(role) 出现 2 次，用其后的 return 行唯一化：
    #    第一次后跟 apply_mask(data,...)，第二次后跟 text 相关。取 apply_mask 行作锚点。
    Mutation(
        name="脱敏未知角色不 fail-closed（mask_for_context 不拒绝）",
        target=_DSH_MASKING,
        anchor="        return await self._mask_service.apply_mask(data, actor_role=role, mask_policy=policy)",
        replacement="        return await self._mask_service.apply_mask(data, actor_role='auditor', mask_policy=McpMaskLevel.STANDARD)  # MUTATED",
        expect_test="",
        suite="be",
        selector=_BE_MASKING,
    ),

    # ─────────────── 假绿守卫修复（Property 12/14/21/23/34 补锚点）───────────────
    # 这批锚点对应三处**已修复的假绿守卫**：
    #   ① 后端 Property 34 恒真断言（`... or True`）
    #   ② 后端 Property 14 零断言测试（算完不 assert）
    #   ③ 前端 PhaseBGateGuards 断言输入字面量 + `toBeDefined()` import 检查
    # 修完必须证明「改坏生产代码 → 对应测试打红」，否则修的只是文本不是判据。

    # ⑯ 后端在 label 上二次转义（净化边界从"唯一在前端"变成两处）
    Mutation(
        name="[假绿修复] as_dict 二次转义 label（P34-A）",
        target=_CTX_BUDGET,
        anchor='            d["label"] = self.label',
        replacement='            d["label"] = self.label.replace("<", "&lt;").replace(">", "&gt;")  # MUTATED',
        expect_test="passes_untrusted_label_through_unmodified",
        suite="be",
        selector=_BE_PHASE_B,
    ),

    # ⑰ 后端静默截断 label（前端 sanitizer 拿到的正文已缺内容）
    Mutation(
        name="[假绿修复] as_dict 静默截断 label（P34-A）",
        target=_CTX_BUDGET,
        anchor='            d["label"] = self.label',
        replacement='            d["label"] = self.label[:12]  # MUTATED: 静默截断',
        expect_test="passes_untrusted_label_through_unmodified",
        suite="be",
        selector=_BE_PHASE_B,
    ),

    # ⑱ 恢复 extra_scopes 旧双轨取值（属性读形态）
    Mutation(
        name="[假绿修复] 恢复 extra_scopes 消费路径（P14-A）",
        target=_MENTION_SVC,
        anchor="logger = logging.getLogger(__name__)",
        replacement=(
            "logger = logging.getLogger(__name__)\n\n\n"
            "def _mutated_legacy_scopes(req):  # MUTATED: 恢复旧双轨取值\n"
            "    return req.extra_scopes"
        ),
        expect_test="test_no_extra_scopes_consumption_in_ai_chat_package",
        suite="be",
        selector=_BE_PHASE_B,
    ),

    # ⑲ 拒绝名单不再点名 extra_scopes（"收敛"退化成悄悄不接受）
    Mutation(
        name="[假绿修复] 拒绝名单移除 extra_scopes（P14-D）",
        target=_RUN_CONTRACT,
        anchor='        "extra_scopes",',
        replacement='        # "extra_scopes",  # MUTATED: 从拒绝名单移除',
        expect_test="test_client_submitted_extra_scopes_is_rejected",
        suite="be",
        selector=_BE_PHASE_B,
    ),

    # ⑳ sanitizer 放宽 on* 事件属性（载体是白名单标签，标签过滤拦不住）
    Mutation(
        name="[假绿修复] useSanitize ALLOWED_ATTR 放宽 on*（FE-P34-A）",
        target=_FE_SANITIZE,
        anchor="  'colspan', 'rowspan', 'class', 'style',",
        replacement=(
            "  'colspan', 'rowspan', 'class', 'style',"
            " 'onclick', 'onmouseover', 'onerror', 'onfocus', // MUTATED"
        ),
        expect_test="事件属性挂在",
        suite="fe",
        selector=_FE_PHASE_B_GATE,
    ),

    # ㉑ 复核模式门控失效（任何宿主都能启用）
    Mutation(
        name="[假绿修复] canEnable 去掉 workpaper 判定（FE-P23-A）",
        target=_FE_REVIEW_BAR,
        anchor="  return props.host.host.type === 'workpaper'",
        replacement="  return true // MUTATED: 任何宿主都可启用复核",
        expect_test="开关 disabled",
        suite="fe",
        selector=_FE_PHASE_B_GATE,
    ),

    # ㉒ 切换不取复核模板（复核模板成为死代码）
    Mutation(
        name="[假绿修复] handleToggle 不触发 fetchPreview（FE-P23-B）",
        target=_FE_REVIEW_BAR,
        anchor="  if (enabled && canEnable.value) {",
        replacement="  if (false) { // MUTATED: 切换不取复核模板",
        expect_test="切换后真的去取复核模板",
        suite="fe",
        selector=_FE_PHASE_B_GATE,
    ),

    # ㉓ 宿主切走后复核模式残留（删掉自动关闭 watcher 的 body）
    Mutation(
        name="[假绿修复] 删除宿主切换自动关闭（FE-P23-C）",
        target=_FE_REVIEW_BAR,
        anchor="watch(canEnable, (val) => {",
        replacement="watch(canEnable, (val) => {\n  if (true) return // MUTATED: 不自动关闭",
        expect_test="自动关闭",
        suite="fe",
        selector=_FE_PHASE_B_GATE,
    ),

    # ㉔ 禁用原因塌缩成兜底文案（用户分不清为什么不能用）
    Mutation(
        name="[假绿修复] disabledReason 塌缩兜底文案（FE-P23-D）",
        target=_FE_REVIEW_BAR,
        anchor="      return '仅在底稿页面可用，当前为附注编辑'",
        replacement="      return '仅在底稿页面可用' // MUTATED: 塌缩为兜底文案",
        expect_test="可区分的中文原因",
        suite="fe",
        selector=_FE_PHASE_B_GATE,
    ),

    # ㉕ 每次保存都新生成 idempotency key（重试产生双文档）
    Mutation(
        name="[假绿修复] 每次 saveAsNote 都换新 key（FE-P21-A）",
        target=_FE_NOTE_CAPTURE,
        anchor="    if (!currentIdempotencyKey) {",
        replacement="    if (true) { // MUTATED: 每次都新生成 key",
        expect_test="复用同一 idempotency_key",
        suite="fe",
        selector=_FE_PHASE_B_GATE,
    ),

    # ㉖ 选择集变化后不重置 key（不同意图复用同一 key，第二篇被幂等吞掉）
    Mutation(
        name="[假绿修复] 选择变化不重置 key（FE-P21-B）",
        target=_FE_NOTE_CAPTURE,
        anchor=(
            "    // 选择变化时重新生成 idempotency key（新的选择集 = 新的保存意图）\n"
            "    currentIdempotencyKey = null"
        ),
        replacement="    // MUTATED: 选择变化不重置 idempotency key",
        expect_test="复用同一 idempotency_key",
        suite="fe",
        selector=_FE_PHASE_B_GATE,
    ),

    # ㉗ manifest 只渲染 included（trimmed/denied 静默丢弃）
    Mutation(
        name="[假绿修复] manifest 只渲染 included（FE-P12-A）",
        target=_FE_CTX_INSPECTOR,
        anchor='v-for="(item, idx) in manifest"',
        replacement=(
            'v-for="(item, idx) in manifest.filter((m) => m.decision === \'included\')"'
        ),
        expect_test="各自渲染并计入中文摘要",
        suite="fe",
        selector=_FE_PHASE_B_GATE,
    ),

    # ─────────────── MCP 取数（补 Task 25/26 责任真空）───────────────
    # 这批锚点对应 **7 个 MCP 工具从空占位换成真实取数**。
    # 原状：`_tool_*` 全是 `return {"items": []}` / `{"status": "placeholder"}`，
    # 三层管道（REST → stdio server → DshEngine）全通、Phase C 207 测试全绿，
    # 因为没有一条测试断言"返回了真实数据"。
    # 守卫落在 `test_ai_chat_mcp_tools_data.py`（真实 PG + 事务回滚）。

    # ㉘ 底稿列表回到空占位
    Mutation(
        name="[MCP取数] wp_list 回到空占位（M28）",
        target=_MCP_ROUTER,
        anchor="    return await tool_wp_list(ctx, arguments)",
        replacement='    return {"items": [], "total": 0}  # MUTATED: 回到空占位',
        expect_test="test_wp_list_returns_real_workpapers",
        suite="be",
        selector=_BE_MCP_DATA,
    ),

    # ㉙ 底稿正文回到空壳（parsed_data 不再读出）
    Mutation(
        name="[MCP取数] wp_read 回到空 content（M29）",
        target=_MCP_ROUTER,
        anchor="    return await tool_wp_read(ctx, arguments)",
        replacement=(
            '    return {"wp_id": arguments.get("wp_id"), "content": {},'
            ' "wp_code": "", "sheets": []}  # MUTATED'
        ),
        expect_test="test_wp_read_returns_real_parsed_data",
        suite="be",
        selector=_BE_MCP_DATA,
    ),

    # ㉚ 试算表回到空 rows（叶子聚合 + 方向定符号全失效）
    Mutation(
        name="[MCP取数] tb_query 回到空 rows（M30）",
        target=_MCP_ROUTER,
        anchor="    return await tool_tb_query(ctx, arguments)",
        replacement=(
            '    return {"rows": [], "totals": {}, "mode": "leaf_aggregate",'
            ' "total": 0}  # MUTATED'
        ),
        expect_test="test_tb_query_leaf_mode_aggregates_only_leaves",
        suite="be",
        selector=_BE_MCP_DATA,
    ),

    # ㉛ 附注回到 placeholder 状态（同时验证"禁占位"源码守卫）
    Mutation(
        name="[MCP取数] note_read 回到 placeholder（M31）",
        target=_MCP_ROUTER,
        anchor="    return await tool_note_read(ctx, arguments)",
        replacement=(
            '    return {"note_id": arguments.get("note_id"), "content": {},'
            ' "status": "placeholder"}  # MUTATED'
        ),
        expect_test="test_note_read_returns_rows_from_table_data",
        suite="be",
        selector=_BE_MCP_DATA,
    ),

    # ㉜ 放宽工具内第二道授权（token 签名通过即取数）
    Mutation(
        name="[MCP取数] 放宽工具内 ResourceAccessResolver 判定（M32）",
        target=_MCP_TOOLS,
        anchor="    if not decision.allowed:",
        replacement="    if False:  # MUTATED: 工具内不再做第二道授权",
        expect_test="test_out_of_scope_cycle_workpaper_is_denied",
        suite="be",
        selector=_BE_MCP_DATA,
    ),

    # ㉝ token cycle_scope 裁剪失效（Req 2.6 共用上界被绕开）
    Mutation(
        name="[MCP取数] token cycle_scope 裁剪恒放行（M33）",
        target=_MCP_TOOLS,
        anchor='    return str(cycle or "") in scope',
        replacement="    return True  # MUTATED: 循环范围裁剪失效",
        expect_test="test_wp_read_denied_when_cycle_outside_token_cycle_scope",
        suite="be",
        selector=_BE_MCP_DATA,
    ),

    # ㉞ 跳过金额脱敏（strict 与 none 两角色结果将逐字节相同）
    Mutation(
        name="[MCP取数] mask_tool_result 跳过金额脱敏（M34）",
        target=_DSH_MASKING,
        anchor="    _mask_amounts_in_place(masked, role)",
        replacement="    pass  # MUTATED: 跳过金额脱敏",
        expect_test="test_strict_and_none_role_results_differ",
        suite="be",
        selector=_BE_MCP_DATA,
    ),

    # ㉟ 恢复语义检索伪降级（embedding down 时用 ILIKE 结果冒充）
    Mutation(
        name="[MCP取数] semantic_search_strict 恢复词法伪降级（M35）",
        target=_KB_INDEX,
        anchor="            raise EmbeddingUnavailableError(",
        replacement=(
            "            return await self._ilike_fallback("
            "project_id, query, top_k, scope)  # MUTATED: 伪降级\n"
            "            raise EmbeddingUnavailableError("
        ),
        expect_test="test_kb_search_embedding_down_returns_semantic_unavailable",
        suite="be",
        selector=_BE_MCP_DATA,
    ),

    # ─────────────── 渲染宿主（Task 15 两个组件从未挂载的补口）───────────────
    # 原状：`ChatMentionPicker.vue` / `ChatContextInspector.vue` 存在、23 条 vitest
    # 全绿、Task 15 标 `[x]`，但**零宿主引用** —— 浏览器里 `@` 打不出、Context
    # Manifest 看不到。23 条守卫直接 `mount(组件)`，从不问「有没有人挂载它」。
    # 与 G7 的「column.group 声明齐全、39 例全绿、零 .vue 引用 ⇒ 两级表头 0/38
    # 从未渲染」同形状。这批锚点锁死三段接线：挂载 → 触发 → 提交。

    # ㊱ 删掉 mention picker 的模板标签，**保留 import**（"import 了不用"）
    Mutation(
        name="[渲染宿主] 删掉 ChatMentionPicker 模板标签保留 import（M36）",
        target=_FE_PANEL,
        anchor="        <ChatMentionPicker",
        replacement='        <div v-if="false" data-mutated-picker-removed',
        expect_test="面板 template 里真的渲染",
        suite="fe",
        selector=_FE_REACHABILITY,
    ),

    # ㊲ 同上，换 Context Inspector（证明判据不是只对某一个组件写死）
    Mutation(
        name="[渲染宿主] 删掉 ChatContextInspector 模板标签保留 import（M37）",
        target=_FE_PANEL,
        anchor="      <ChatContextInspector",
        replacement='      <div v-if="false" data-mutated-inspector-removed',
        expect_test="面板 template 里真的渲染",
        suite="fe",
        selector=_FE_REACHABILITY,
    ),

    # ㊳ `@` 触发链断开（picker 挂着但永远不弹）
    Mutation(
        name="[渲染宿主] @ 触发链断开（watch(draft) 不开 picker）（M38）",
        target=_FE_PANEL,
        anchor="  mentionPickerOpen.value = hasActiveMentionToken(val)",
        replacement="  mentionPickerOpen.value = false // MUTATED: @ 触发链断开",
        expect_test="输入 @ 唤出 mention picker",
        suite="fe",
        selector=_FE_RUN_PAYLOAD,
    ),

    # ㊴ 面板不把已选引用交给 sendMessage（渲染出来了但不提交）
    Mutation(
        name="[渲染宿主] handleSend 丢弃已选 mention（M39）",
        target=_FE_PANEL,
        anchor="    mentions: selectedMentions.value.map((m) => ({ type: m.type, id: m.id })),",
        replacement="    mentions: [], // MUTATED: 选了不提交",
        expect_test="已选引用出现在 mentions 里",
        suite="fe",
        selector=_FE_RUN_PAYLOAD,
    ),

    # ㊵ 请求体构造丢掉 mentions（后端永远收不到引用）
    Mutation(
        name="[渲染宿主] buildExtrasPayload 不写 mentions 键（M40）",
        target=_FE_CHAT,
        anchor="      payload.mentions = mentions.map((m) => ({ type: m.type, id: m.id }))",
        replacement="      void mentions // MUTATED: mentions 不进请求体",
        expect_test="已选引用出现在 mentions 里",
        suite="fe",
        selector=_FE_RUN_PAYLOAD,
    ),

    # ㊶ manifest 投影恒空（检视器挂着但永远显示"暂无上下文信息"）
    Mutation(
        name="[渲染宿主] normalizeContextManifest 投影恒空（M41）",
        target=_FE_CTX_MANIFEST,
        anchor="    if (META_KEYS.has(key) || !Array.isArray(value)) continue",
        replacement="    if (true) continue // MUTATED: 投影恒空",
        expect_test="服务端分组 manifest 被投影后逐条渲染",
        suite="fe",
        selector=_FE_RUN_PAYLOAD,
    ),
)


# ─────────────────────────── 测试执行 ───────────────────────────


def _run_pytest(selector: str) -> set[str]:
    """跑 pytest，返回**失败测试名**集合（不看 exit code）。"""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", selector, "-q", "--tb=no", "-p", "no:cacheprovider"],
        cwd=str(ROOT),
        env=ENV,
        capture_output=True,
        timeout=900,
    )
    text = (proc.stdout + proc.stderr).decode("utf-8", "replace")
    return set(re.findall(r"^FAILED\s+(\S+)", text, re.MULTILINE))


def _run_vitest(selector: str) -> set[str]:
    """跑 vitest，返回**失败测试全名**集合。

    🔴 必须走 ``--reporter=json --outputFile=<绝对路径>``：控制台的 FAIL 行会按
    终端宽度折行，正则解析必漏。
    """
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "vitest.json"
        subprocess.run(
            [
                "cmd", "/c",
                f"npx vitest run {selector} --reporter=json --outputFile={report} > NUL 2>&1",
            ],
            cwd=str(FRONTEND),
            env=ENV,
            timeout=900,
        )
        if not report.exists():
            return {"<vitest-report-missing>"}
        data = json.loads(report.read_text(encoding="utf-8"))
    fails: set[str] = set()
    for file_result in data.get("testResults", []):
        for assertion in file_result.get("assertionResults", []):
            if assertion.get("status") == "failed":
                fails.add(assertion.get("fullName") or assertion.get("title") or "?")
        if file_result.get("status") == "failed" and not file_result.get("assertionResults"):
            fails.add(f"<file-failed>{Path(file_result.get('name', '?')).name}")
    return fails


def run_suite(mutation: Mutation) -> set[str]:
    return _run_vitest(mutation.selector) if mutation.suite == "fe" else _run_pytest(mutation.selector)


# ─────────────────────────── 备份 / 还原 ───────────────────────────


def _bak_path(target: Path) -> Path:
    return target.with_name(target.name + _BAK_SUFFIX)


def backup(target: Path) -> bytes:
    """写 `.bak` 文件（不只放内存）并返回原始字节。"""
    raw = target.read_bytes()
    _bak_path(target).write_bytes(raw)
    return raw


def restore(target: Path) -> bool:
    """从 `.bak` 字节级还原并删除 `.bak`。返回是否做了还原。"""
    bak = _bak_path(target)
    if not bak.exists():
        return False
    target.write_bytes(bak.read_bytes())
    bak.unlink()
    return True


def restore_all() -> list[str]:
    """清理全部残留 `.bak`（`--restore`）。"""
    done: list[str] = []
    for m in MUTATIONS:
        target = ROOT / m.target
        if restore(target):
            done.append(m.target)
    return done


# ─────────────────────────── 主流程 ───────────────────────────


def apply_mutation(target: Path, mutation: Mutation) -> str | None:
    """施加变异。返回 None 表示成功，否则返回 MISS 原因。"""
    text = target.read_text(encoding="utf-8")
    hits = text.count(mutation.anchor)
    if hits != 1:
        return f"锚点命中 {hits} 次（须恰 1）"
    target.write_text(text.replace(mutation.anchor, mutation.replacement), encoding="utf-8")
    return None


def run_one(mutation: Mutation, baselines: dict[str, set[str]]) -> Outcome:
    out = Outcome(mutation=mutation)
    target = ROOT / mutation.target
    if not target.exists():
        out.verdict = "MISS"
        out.detail = f"目标文件不存在：{mutation.target}"
        return out

    raw = backup(target)
    try:
        miss = apply_mutation(target, mutation)
        if miss:
            out.verdict = "MISS"
            out.detail = miss
            return out

        after = run_suite(mutation)
        base = baselines[mutation.suite + "|" + mutation.selector]
        new_fails = sorted(after - base)
        out.new_fails = new_fails

        if not new_fails:
            out.verdict = "GREEN"
            out.detail = "无新增失败 ⇒ 守卫抓不到这个改动"
        elif not mutation.expect_test:
            out.verdict = "RED"
            out.detail = f"新增失败 {len(new_fails)} 条"
        elif any(mutation.expect_test in f for f in new_fails):
            out.verdict = "RED"
            out.detail = f"新增失败 {len(new_fails)} 条，含预期「{mutation.expect_test}」"
        else:
            out.verdict = "WRONG"
            out.detail = f"新增失败不含预期「{mutation.expect_test}」：{new_fails[:3]}"
        return out
    finally:
        target.write_bytes(raw)
        _bak_path(target).unlink(missing_ok=True)


#: 从测试源里抽「测试名/用例标题」的模式。
#: - pytest：``def test_xxx`` / ``async def test_xxx``
#: - vitest：``it('标题'`` / ``test('标题'`` / ``describe('标题'``
_TEST_NAME_PATTERNS = (
    re.compile(r"(?m)^\s*(?:async\s+)?def\s+(test_\w+)"),
    re.compile(r"""(?m)^\s*(?:it|test|describe)(?:\.\w+)?\(\s*['"`](.+?)['"`]"""),
)


def _test_names(sources: list[str]) -> list[str]:
    """收集测试源里所有**测试名 / describe 标题**（不含正文）。"""
    names: list[str] = []
    for src in sources:
        for pattern in _TEST_NAME_PATTERNS:
            names.extend(pattern.findall(src))
    return names


def _selector_sources(mutation: Mutation) -> list[str]:
    """把 selector 解析成测试源文件正文列表（供 expect_test 定位）。"""
    texts: list[str] = []
    if mutation.suite == "be":
        for part in mutation.selector.split():
            rel = part.split("::", 1)[0]
            path = ROOT / rel
            files = sorted(path.rglob("test_*.py")) if path.is_dir() else [path]
            for f in files:
                if f.is_file():
                    texts.append(f.read_text(encoding="utf-8", errors="replace"))
    else:
        for f in sorted((FRONTEND / "src").rglob("*.spec.ts")):
            if mutation.selector in f.name:
                texts.append(f.read_text(encoding="utf-8", errors="replace"))
    return texts


def verify_anchors(selected: list[Mutation]) -> list[str]:
    """`--check-anchors` / `--list` 的静态自检。

    拦四类只在手工跑全量变异时才暴露的 stale：
    1. 锚点漂移（命中 != 1）
    2. 变异空操作（replacement == anchor）
    3. 测试名漂移（expect_test 在对应测试源里找不到）
    4. expect_test 不是**测试名**而只是源码里随便一个片段

    🔴 第 4 条是 2026-08-16 实跑全量后补的：M10 的 ``expect_test="user_id"`` 在
    ``test_ai_chat_mcp_token.py`` 正文里确实存在（参数名），所以旧版静态检查放行；
    但实际打红的测试叫 ``test_wrong_user_rejected``，判定成 WRONG-TEST。
    判「预期哪条测试打红」必须拿**测试名**比，不能拿源码任意片段比。
    """
    problems: list[str] = []
    for mutation in selected:
        target = ROOT / mutation.target
        if not target.is_file():
            problems.append(f"{mutation.name}: target 不存在 → {mutation.target}")
            continue
        text = target.read_text(encoding="utf-8", errors="replace")
        hits = text.count(mutation.anchor)
        if hits != 1:
            problems.append(
                f"{mutation.name}: anchor 在 {mutation.target} 命中 {hits} 次"
                f"（须恰好 1 次）→ {mutation.anchor[:64]!r}"
            )
        if mutation.replacement == mutation.anchor:
            problems.append(f"{mutation.name}: replacement 与 anchor 逐字相同 ⇒ 变异是空操作")
        if mutation.expect_test:
            sources = _selector_sources(mutation)
            if not sources:
                problems.append(
                    f"{mutation.name}: selector 找不到任何测试源 → {mutation.selector}"
                )
            elif not any(mutation.expect_test in s for s in sources):
                problems.append(
                    f"{mutation.name}: expect_test「{mutation.expect_test}」"
                    f"在 {mutation.selector} 的测试源里找不到 ⇒ 测试名漂移"
                )
            elif not any(mutation.expect_test in n for n in _test_names(sources)):
                problems.append(
                    f"{mutation.name}: expect_test「{mutation.expect_test}」只出现在源码正文里，"
                    f"不是 {mutation.selector} 的任何**测试名/用例标题** ⇒ 实跑必判 WRONG-TEST"
                )
    leftovers = [m.target for m in selected if _bak_path(ROOT / m.target).exists()]
    if leftovers:
        problems.append(f"残留 .bak（上次变异未复原）：{leftovers} —— 请跑 --restore")
    return problems


def export_manifest(selected: list[Mutation]) -> list[dict]:
    """导出 JSON manifest（供 CI/工具链消费）。"""
    return [
        {
            "name": m.name,
            "target": m.target,
            "anchor_preview": m.anchor[:80],
            "replacement_preview": m.replacement[:80],
            "expect_test": m.expect_test,
            "suite": m.suite,
            "selector": m.selector,
        }
        for m in selected
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="DSH Agent Panel 守卫变异检验（四态判定）"
    )
    parser.add_argument("--only", choices=["be", "fe"], help="只跑后端或前端锚点")
    parser.add_argument(
        "--pick", action="append", default=None,
        help="只跑名字含该子串的锚点（可重复），例如 --pick 假绿修复",
    )
    parser.add_argument(
        "--out", default=None,
        help="结果 JSON 输出路径（默认 spec 目录下 mutation_results.json；"
             "跑子集时务必另指定，避免覆盖全量记录）",
    )
    parser.add_argument("--list", action="store_true", help="列锚点 + 静态自检")
    parser.add_argument(
        "--check-anchors", action="store_true",
        help="只做静态自检（不执行变异），退出码 0=全通 / 2=有问题"
    )
    parser.add_argument("--restore", action="store_true", help="清理残留 .bak 后退出")
    parser.add_argument(
        "--manifest", action="store_true", help="以 JSON 格式导出 manifest 到 stdout"
    )
    args = parser.parse_args(argv)

    if args.restore:
        done = restore_all()
        print(f"[restore] 还原 {len(done)} 个文件：{done}" if done else "[restore] 无残留 .bak")
        return 0

    selected = [m for m in MUTATIONS if not args.only or m.suite == args.only]
    if args.pick:
        selected = [m for m in selected if any(p in m.name for p in args.pick)]
        if not selected:
            print(f"🔴 --pick {args.pick} 未匹配任何锚点")
            return 2

    if args.manifest:
        print(json.dumps(export_manifest(selected), indent=2, ensure_ascii=False))
        return 0

    if args.list or args.check_anchors:
        if args.list:
            print(f"变异锚点 {len(selected)} 条：")
            for i, m in enumerate(selected, 1):
                print(f"  [{i:>2}] ({m.suite}) {m.name}")
                print(f"        target = {m.target}")
                print(f"        anchor = {m.anchor[:78]!r}")
        problems = verify_anchors(selected)
        print()
        if problems:
            print(f"🔴 静态自检 {len(problems)} 项不通过：")
            for msg in problems:
                print(f"  ✗ {msg}")
            return 2
        print(
            f"✅ 静态自检通过：{len(selected)} 条锚点均命中恰好 1 次、"
            f"replacement 非空操作"
            + ("、expect_test 在测试源里可定位" if any(m.expect_test for m in selected) else "")
        )
        return 0

    # ─── 全量运行 ───
    # 先跑各套基线（预存在失败要从判定里扣掉）
    baselines: dict[str, set[str]] = {}
    for m in selected:
        key = m.suite + "|" + m.selector
        if key not in baselines:
            print(f"[baseline] {key} ...", flush=True)
            baselines[key] = run_suite(m)
            n = len(baselines[key])
            print(
                f"[baseline] {key} 预存在失败 {n} 条"
                + (f"：{sorted(baselines[key])[:3]}" if n else "（干净）"),
                flush=True,
            )

    results: list[Outcome] = []
    for i, m in enumerate(selected, 1):
        print(f"[{i}/{len(selected)}] {m.name} ...", flush=True)
        outcome = run_one(m, baselines)
        results.append(outcome)
        print(f"        {outcome.verdict}: {outcome.detail}", flush=True)

    print()
    print("=" * 88)
    print("变异检验结果（RED=判据有效 / GREEN=守卫缺陷 / MISS=脚本缺陷 / WRONG=污染或锚点错行）")
    print("=" * 88)
    tally = {"RED": 0, "GREEN": 0, "MISS": 0, "WRONG": 0}
    for outcome in results:
        tally[outcome.verdict] += 1
        print(f"[{outcome.verdict:<5}] ({outcome.mutation.suite}) {outcome.mutation.name}")
        print(f"         {outcome.detail}")
        for f in outcome.new_fails[:4]:
            print(f"         + {f}")
    print()
    print(f"合计 {len(results)} 条：" + "  ".join(f"{k}={v}" for k, v in tally.items()))

    # 导出结果 JSON 到临时文件
    result_data = [
        {
            "name": o.mutation.name,
            "verdict": o.verdict,
            "detail": o.detail,
            "new_fails": o.new_fails[:10],
        }
        for o in results
    ]
    result_path = (
        Path(args.out)
        if args.out
        else ROOT / ".kiro" / "specs" / "dsh-agent-panel-integration" / "mutation_results.json"
    )
    if not result_path.is_absolute():
        result_path = ROOT / result_path
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result_data, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        shown = result_path.relative_to(ROOT)
    except ValueError:  # --out 指到仓库外
        shown = result_path
    print(f"\n结果已写入 {shown}")

    bad = tally["GREEN"] + tally["MISS"] + tally["WRONG"]
    if bad:
        print(f"\n🔴 有 {bad} 条非 RED 结果，须修复后才可进入 Task 34")
        return 1
    print(f"\n✅ 全部 {len(results)} 条变异均为 RED —— 守卫有效")
    return 0


if __name__ == "__main__":
    sys.exit(main())
