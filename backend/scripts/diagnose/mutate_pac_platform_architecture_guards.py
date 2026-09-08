# -*- coding: utf-8 -*-
"""platform-architecture-convergence Task 21 — 四态变异（走 `_mutation_kit`）。

覆盖渲染 / 启动 / 领域边界 / 事件 / 前端装配关键守卫。每条变异改一处真实产物，
要求**预期那条**判据变红。起手基线门 + pristine 统一快照 + finally 全复原由共享件保证。

用法（仓库根）::

    python backend/scripts/diagnose/mutate_pac_platform_architecture_guards.py --list
    python backend/scripts/diagnose/mutate_pac_platform_architecture_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_pac_platform_architecture_guards.py --run all \\
        --out .kiro/specs/platform-architecture-convergence/basis/T21-mutation-report.json
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

ORCH = "backend/app/routers/wp_render_config.py"
PIPELINE = "backend/app/routers/wp_render_pipeline.py"
TASK_BUS = "backend/app/services/task_event_bus.py"
TASK_EVENTS = "backend/app/routers/task_events.py"
DISPATCH = "backend/app/routers/dispatch_records.py"
STARTUP = "backend/app/core/startup_registry.py"
WF = ".github/workflows/governance-checks.yml"
ROUTER = "audit-platform/frontend/src/router/index.ts"
REG_BARREL = "audit-platform/frontend/src/components/workpaper/registry/index.ts"

GUARD_FILES = {
    "test_render_pipeline_stage_guards.py":
        "七阶段编排顺序锁 + host_policy 非白名单裁决",
    "test_task_event_bus_idempotency_auth.py":
        "TaskEventBus idempotency_key 等值去重与授权",
    "test_event_call_site_guards.py":
        "事件调用点 await/签名/错误 import 守卫",
    "test_startup_registry.py":
        "startup 顺序/criticality 冻结与 report 投影",
    "test_check_domain_boundaries.py":
        "领域边界 checker 自测 + CI job 归因",
    "FrontendReferenceIntegrity.spec.ts":
        "路由域装配 + 单 beforeEach + path 去重",
    "registrySplitEquivalence.pbt.spec.ts":
        "renderer 域数组分区/唯一性(collision)/facade 一致",
    "registryDomainSplit.spec.ts":
        "renderer barrel 无 startsWith/classifyDomain + 字面量 import",
    "routeDomainProjection.spec.ts":
        "路由域投影等价（展开恰好一次）",
}

MUTATIONS: list[Mutation] = [
    Mutation(
        id="M01",
        side="be",
        path=ORCH,
        kind="swap",
        anchor="    scope_resolution = resolve_scope_redirect(",
        anchor2="    common_facts = await load_common_render_facts(",
        block_open="(",
        want="test_swapping_adjacent_stages_would_red",
        why="交换 Stage3 redirect 与 Stage4 facts ⇒ redirect 短路语义被破坏；"
            "阶段顺序锁必须准确 RED",
    ),
    Mutation(
        id="M02",
        side="be",
        path=PIPELINE,
        kind="insert",
        anchor='                winning_source = "manifest_host_policy"',
        new="                _ = _ONLYOFFICE_HTML_WHITELIST  # PAC mutation",
        want="test_planner_source_uses_host_policy_not_whitelist_literals",
        why="在 plan_sheets 内重新引用白名单字面量 ⇒ host_policy 真源守卫必须 RED",
    ),
    Mutation(
        id="M03",
        side="be",
        path=TASK_BUS,
        kind="replace",
        anchor="            .where(TaskEvent.idempotency_key == idem_key)",
        new="            .where(TaskEvent.trace_id.like(idem_key))",
        want="test_publish_source_writes_and_queries_idempotency_key_equality",
        why="把等值幂等查改回 trace_id.like ⇒ 确定缺陷回归；源码守卫必须 RED",
    ),
    Mutation(
        id="M04",
        side="be",
        path=DISPATCH,
        kind="replace",
        anchor="        await event_bus.publish(",
        new="        event_bus.publish(",
        line=158,
        want="test_dispatch_records_awaits_every_event_bus_publish",
        why="去掉 dispatch_records 的 await ⇒ 协程未执行；调用点守卫必须 RED",
    ),
    Mutation(
        id="M05",
        side="be",
        path=STARTUP,
        kind="replace",
        anchor="FROZEN_STARTUP_SEQUENCE_NAMES: tuple[str, ...] = tuple(t.name for t in STARTUP_TASKS)",
        new=(
            "FROZEN_STARTUP_SEQUENCE_NAMES: tuple[str, ...] = "
            "tuple(reversed([t.name for t in STARTUP_TASKS]))"
        ),
        want="test_frozen_sequence_names_match_registry",
        why="把冻结序列反转 ⇒ 与 STARTUP_TASKS 行序不等价；顺序锁必须 RED",
    ),
    Mutation(
        id="M06",
        side="be",
        path=WF,
        kind="replace",
        anchor="  domain-boundary-governance:",
        new="  domain-boundary-governance-renamed:",
        want="TestCiAttributionGuard::test_job_and_file_refs_exist",
        why="改名独立 CI job ⇒ 归因守卫必须 RED（禁止静默消失）",
    ),
    Mutation(
        id="M07",
        side="fe",
        path=ROUTER,
        kind="insert",
        anchor="router.beforeEach(async (to) => {",
        new="router.beforeEach(async () => { /* PAC mutation second guard */ })",
        want="单 beforeEach",
        why="插入第二个 beforeEach ⇒ 拆分不得改成多守卫；完整性守卫必须 RED",
    ),
    Mutation(
        id="M08",
        side="fe",
        path=REG_BARREL,
        kind="insert",
        anchor="assertUniqueRegistryComponentTypes(REGISTRY_LIST)",
        new=(
            "export function classifyDomain(ct: string): RegistryDomain {\n"
            "  if (ct.startsWith('confirmation-')) return 'confirmations'\n"
            "  return 'specialized'\n"
            "}"
        ),
        want="no startsWith classifier remains in registry barrel",
        why="重新引入 startsWith/classifyDomain 运行时分类器 ⇒ Task 20 禁令守卫必须 RED",
    ),
    # ── 复核 §7 补充：给此前只有测试内 reverse-check 的关键守卫加外部锚点 ──
    Mutation(
        id="M09",
        side="be",
        path=TASK_EVENTS,
        kind="replace",
        anchor="        db, req.event_id, current_user.id, req.reason_code",
        new="        db, req.event_id, req.operator_id, req.reason_code",
        want="test_replay_actor_comes_from_current_user_not_request_body",
        why="replay actor 改回信任请求体 operator_id ⇒ 授权缺陷回归（Req 9.6）；"
            "actor 来源守卫必须 RED",
    ),
    Mutation(
        id="M10",
        side="be",
        path=STARTUP,
        kind="replace",
        anchor='            "name": r.name,',
        new='            "renamed": r.name,',
        want="test_startup_report_as_dict_isomorphic_to_injected_results",
        why="startup 运行报告丢弃逐任务 name 字段 ⇒ 报告与 registry 不再同构（Req 6.2）；"
            "同构守卫必须 RED",
    ),
    Mutation(
        id="M11",
        side="fe",
        path=ROUTER,
        kind="insert",
        anchor="  ...workpapersRoutes,",
        new="  ...workpapersRoutes,",
        want="展开恰好一次",
        why="重复展开一个 route 域 ⇒ flatten 不再等价（Req 10.3）；"
            "路由域投影守卫必须 RED",
    ),
    # 注：collision（Req 11.4）由 registrySplitEquivalence 的
    # `[PBT] 对任意重复注入的 componentType，唯一性校验能检测到` 与 registryDomainSplit 的
    # `RED: duplicate componentType fails assertUniqueRegistryComponentTypes` 两条测试内
    # reverse-check 覆盖：barrel 在 Map 前对全量 REGISTRY_LIST 跑 assertUnique，向 entries 文件
    # 注入重复键会在 import 期抛错（suite-level error，非单条 assertion），不适合做单锚点变异；
    # 上述 PBT 每次运行都随机注入重复并断言必被检测，等价于常驻变异。
]


if __name__ == "__main__":
    fe_dir = REPO / "audit-platform" / "frontend"
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="PAC platform-architecture-convergence Task 21 mutations",
            backend_args=[
                "backend/tests/test_render_pipeline_stage_guards.py",
                "backend/tests/test_task_event_bus_idempotency_auth.py",
                "backend/tests/test_event_call_site_guards.py",
                "backend/tests/test_startup_registry.py",
                "backend/tests/scripts/test_check_domain_boundaries.py",
                "-c",
                "backend/pytest.ini",
                "-q",
                "--tb=no",
                "-rfE",
            ],
            frontend_dir=fe_dir,
            vitest_json=fe_dir / ".pac-t21-vitest-mutation.json",
            frontend_filters=[
                "src/__tests__/FrontendReferenceIntegrity.spec.ts",
                "src/router/__tests__/routeDomainProjection.spec.ts",
                "src/components/workpaper/__tests__/registrySplitEquivalence.pbt.spec.ts",
                "src/components/workpaper/__tests__/registryDomainSplit.spec.ts",
            ],
            baseline_backend_passed=None,
            baseline_frontend_passed=None,
        )
    )
