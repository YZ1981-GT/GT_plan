"""Task 13 Phase A 行为守卫变异检验
（spec dsh-agent-panel-integration / Task 13）。

## 为什么需要它

Task 13 是 Phase A 的"门禁"任务：所有 Task 1-12 的守卫在此综合验证。
本脚本的 4 个变异验证以下守卫的有效性：

- **移除前置 gate**：授权异常 fail-open → 无权用户能创建 run（Property 1/3）
- **改坏 terminal CAS**：允许 error 后再 done → 同一 run 两个终态（Property 7）
- **拆断 SSE JSON**：帧尾空行被吃 → 客户端拿到错误事件（Property 9）
- **恢复 localStorage 正文**：composable 直写 localStorage → 缓存泄漏（Property 35）

## 四态判定

RED / GREEN / ANCHOR-MISS / WRONG-TEST 由 ``_mutation_kit`` 统一给出。

用法::

    python backend/scripts/diagnose/mutate_dsh_task13_phase_a_guards.py --list
    python backend/scripts/diagnose/mutate_dsh_task13_phase_a_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_dsh_task13_phase_a_guards.py --run all
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _mutation_kit import Mutation as Mut  # noqa: E402
from _mutation_kit import run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

#: 本 Task 创建的守卫文件全集（覆盖面分母）。
GUARD_FILES: dict[str, str] = {
    "test_task13_phase_a_guards.py": (
        "Task 13 新建（Properties 1-10, 22, 24, 32-33 综合行为守卫）"
    ),
    "PlatformAiChatPhaseA.spec.ts": (
        "Task 13 新建（Properties 34-39 Phase A 前端守卫）"
    ),
}

#: 后端测试的 pytest 参数
BE_PYTEST_ARGS = [
    "backend/tests/dsh_agent_panel/test_task13_phase_a_guards.py",
    "-q",
    "--tb=no",
    "-rfE",
    "-p",
    "no:randomly",
]

#: 前端测试的 vitest 参数
FE_VITEST_ARGS = [
    "npx",
    "vitest",
    "--run",
    "src/components/ai/__tests__/PlatformAiChatPhaseA.spec.ts",
]

# ─── 源码路径 ────────────────────────────────────────────────────────────────

ACCESS = "backend/app/services/ai_chat/access.py"
RUN_SERVICE = "backend/app/services/ai_chat/run_service.py"
RUN_EVENTS = "backend/app/services/ai_chat/run_events.py"
CHAT_COMPOSABLE = "audit-platform/frontend/src/composables/usePlatformAiChat.ts"
CHAT_STORE = "audit-platform/frontend/src/stores/chatRunState.ts"

# ===========================================================================
# 变异定义
# ===========================================================================

MUTATIONS: list[Mut] = [
    # ── M01: 移除前置 gate（Property 1 — 授权拒绝前零读取）────────────────
    Mut(
        id="M01",
        side="be",
        path=ACCESS,
        kind="replace",
        anchor=(
            "        except Exception as exc:  # noqa: BLE001 — Req 2.8 授权服务异常 fail-closed\n"
            "            logger.error(\n"
            '                "AI 授权解析异常（fail-closed）principal=%s host=%s/%s action=%s: %s",'
        ),
        new=(
            "        except Exception as exc:  # noqa: BLE001 — Req 2.8 授权服务异常 fail-closed\n"
            "            # MUTATION M01: fail-open（异常时允许）\n"
            "            return AccessDecision(allowed=True, principal_id=principal_id, project_id=project_hint)\n"
            "            logger.error(\n"
            '                "AI 授权解析异常（fail-closed）principal=%s host=%s/%s action=%s: %s",'
        ),
        want="test_resolver_exception_returns_denial",
        wants=("test_outsider_denied_all_project_resources",),
        why=(
            "授权 except 分支改为 fail-open：任何 gate_wp/权限服务异常都静默允许，"
            "表现为'偶尔无权用户也能看到底稿上下文'。Property 1 的 fail-closed 守卫"
            "必须拦截这个变异。"
        ),
        tags=("req2.8", "property1"),
    ),
    # ── M02: 改坏 terminal CAS（Property 7 — Run 唯一终态）────────────────
    Mut(
        id="M02",
        side="be",
        path=RUN_SERVICE,
        kind="replace",
        anchor="            # 已有终态 → 不变更，返回 False（Property 7）",
        new="            # MUTATION M02: 允许重复终态\n            pass  # Property 7 removed",
        want="test_terminal_race_only_first_wins",
        wants=("test_no_done_event_after_error",),
        why=(
            "终态 CAS 被移除：error 之后还能 finish_success，同一 run 出现两个终态。"
            "用户表现为取消后还收到一段完整回答。Property 7 守卫的终态竞争测试"
            "必须打红。"
        ),
        tags=("req4.5", "property7"),
    ),
    # ── M03: 拆断 SSE 帧（Property 9 — SSE 分片等价）─────────────────────
    Mut(
        id="M03",
        side="be",
        path=RUN_EVENTS,
        kind="replace",
        anchor='    return "".join(f"{line}\\n" for line in lines) + "\\n"',
        new='    return "".join(f"{line}\\n" for line in lines)',
        want="test_arbitrary_splits_produce_same_events",
        wants=("test_last_event_id_replay_no_loss_no_dup",),
        why=(
            "帧尾空行被删除：两条事件被客户端并成一条（后一条 data 追加到前一条的 data buffer），"
            "在服务端日志和库状态里一切正常，只有真正按 SSE 规范逐字节分片解析才能抓到。"
            "Property 9 的 hypothesis 分片测试必须打红。"
        ),
        tags=("req4.8", "property9"),
    ),
    # ── M04: 恢复 localStorage 正文（Property 35 — 浏览器敏感缓存）────────
    Mut(
        id="M04",
        side="fe",
        path=CHAT_STORE,
        kind="insert_after",
        anchor="export const useChatRunStateStore = defineStore('chatRunState', () => {",
        new=(
            "  // MUTATION M04: 写 localStorage（违反 Property 35）\n"
            "  if (typeof localStorage !== 'undefined') {\n"
            "    localStorage.setItem('doc_ai_chat_mutation_test', 'leaked')\n"
            "  }\n"
        ),
        want="chatRunState store 不写 localStorage",
        wants=("运行时不向 localStorage 写入敏感内容",),
        why=(
            "chatRunState 启动时向 localStorage 写入 doc_ai_chat_* key：用户切换账号"
            "后另一用户能在 localStorage 看到上一个用户的消息内容。Property 35 的"
            "'运行时零 localStorage 正文'守卫必须打红。"
        ),
        tags=("req13.3", "property35"),
    ),
]

# ===========================================================================
# CLI 入口
# ===========================================================================

if __name__ == "__main__":
    run_cli(
        mutations=MUTATIONS,
        guard_files=GUARD_FILES,
        repo=REPO,
        be_pytest_args=BE_PYTEST_ARGS,
        fe_vitest_args=FE_VITEST_ARGS,
    )
