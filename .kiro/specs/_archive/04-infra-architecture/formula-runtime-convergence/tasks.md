# Implementation Plan

## Overview

本计划包含 18 个顶层任务。全部初始为 `[ ]`，不得因旧 spec 标记为完成而继承假绿状态。并行开发采用**文件所有权硬隔离**：同一 wave 内任何两个任务都不得修改同一文件；`engine.py`、`draft_refresh_orchestrator.py`、`draft_refresh_service.py`、`routers/draft_refresh.py` 各由一个后续串行任务独占。

执行约束：

- 每个子代理开始前先读取 owner files，并检查当前 git diff，禁止覆盖其他代理变更。
- 不得修改 `forbiddenSharedFiles`；需要共享文件改动时只提交接口需求给后续 integration task。
- service 只 flush，router commit；四表库只读；金额统一 Decimal。
- PBT 使用全局 fast profile（默认 max_examples=5），不得私自提高造成慢测。
- 后端测试命令使用 `rtk python -m pytest ...`；前端使用 `rtk npx vitest --run ...`。
- 迁移任务执行时必须先调用 `migration_status`，以实时最高版本创建 `V{N+1}`。

## File Ownership Matrix

| Task | Owner files | Forbidden shared files | Depends on |
|---|---|---|---|
| 1 | 新建 runtime baseline tests | 全部业务源码 | — |
| 2 | `formula_runtime/contracts.py` + tests | engine/orchestrator/service/router | — |
| 3 | `formula_runtime/value_loader.py` + tests | engine/orchestrator | 2 |
| 4 | `formula_runtime/adapters/workpaper.py` + tests | orchestrator/service | 2 |
| 5 | `formula_runtime/adapters/adjudication.py` + tests | orchestrator/service | 2 |
| 6 | `formula_runtime/adapters/report.py` + tests | orchestrator/service | 2 |
| 7 | `formula_runtime/adapters/note.py` + tests | orchestrator/service | 2 |
| 8 | `formula_management/logic_check.py` + tests | engine/orchestrator | — |
| 9 | `formula_management/reference_resolver.py` + tests | wp_formula_service/engine | — |
| 10 | `wp_formula_service.py` + tests | engine/router | — |
| 11 | migration + ORM + `formula_runtime/outbox.py` | service/orchestrator/router | — |
| 12 | `formula_management/engine.py` + tests | orchestrator/service/router | 2,3 |
| 13 | `draft_refresh_orchestrator.py` + tests | service/router | 3–7,11,12 |
| 14 | `draft_refresh_service.py` + tests | orchestrator/router | 11,13 |
| 15 | `routers/draft_refresh.py` + API contract files/tests | service/orchestrator | 10,14 |
| 16 | `GtRefreshScopeDialog.vue`, `ThreeColumnLayout.vue`, frontend tests/types | backend files | 15 |
| 17 | PostgreSQL integration + Playwright E2E files | production source | 1–16 |
| 18 | completion guard + this spec/INDEX status | production source | 17 |

## Tasks

- [x] 1. 建立运行时缺口基线测试 [Req 1,4,5,13,14]
  - 仅新建 `backend/tests/formula_runtime/test_current_gap_baseline.py` 与契约 fixture。
  - 固化四项失败证据：workpaper scope 无领域 mutation、rollback 不恢复业务值、save 误写 computed time、API 字段漂移。
  - 测试必须明确标注 expected gap，不得用宽泛 catch 或无断言通过。
  - **Validation:** `rtk python -m pytest tests/formula_runtime/test_current_gap_baseline.py -q --tb=short`

- [x] 2. 定义 canonical target 与 mutation contracts [Req 2,3,4｜P1,P3]
  - 新建 `backend/app/services/formula_runtime/contracts.py`、`__init__.py`。
  - 实现 CanonicalFormulaTarget、FormulaMutation、AppliedMutation、ExecutionPlan/Result、DomainMutationAdapter Protocol。
  - 新建 PBT：identity round-trip、mutation before/after 保真、非法 domain/locator 拒绝。
  - **Forbidden:** 不改 engine/orchestrator/service/router。
  - **Validation:** `rtk python -m pytest tests/formula_runtime/test_contracts_pbt.py -q --tb=short`

- [x] 3. 实现批量 FormulaValueLoader [Req 2,11｜P1,P2]
  - 新建 `formula_runtime/value_loader.py`，批量 ACNR resolve 后按域去重加载。
  - 支持四表只读、workpaper/report/note 批量值；返回 found/miss/ambiguous。
  - 加查询计数测试：查询数随 domain 数增长，不随引用数线性增长。
  - **Forbidden:** 不改 engine/orchestrator。
  - **Validation:** `rtk python -m pytest tests/formula_runtime/test_value_loader.py -q --tb=short`

- [x] 4. 实现 WorkpaperMutationAdapter [Req 3,4,12｜P3,P4,P13]
  - 新建 `formula_runtime/adapters/workpaper.py` 与独立测试。
  - locator 含 wp_id/item/cell；prepare 捕获真实 before/version；apply/restore 校验项目归属与版本。
  - **Forbidden:** 不改 orchestrator/service/checklist 路由。
  - **Validation:** `rtk python -m pytest tests/formula_runtime/test_workpaper_adapter.py -q --tb=short`

- [x] 5. 实现 AdjudicationMutationAdapter [Req 3,4｜P3,P4]
  - 新建 `formula_runtime/adapters/adjudication.py` 与测试。
  - 只接受 standard_account_code locator，只写 audited_amount，不动 unadjusted_amount。
  - B5/单元坐标作为科目码时必须拒绝。
  - **Validation:** `rtk python -m pytest tests/formula_runtime/test_adjudication_adapter.py -q --tb=short`

- [x] 6. 实现 ReportMutationAdapter [Req 3,4｜P3,P4]
  - 新建 `formula_runtime/adapters/report.py` 与测试。
  - 用 report_type/row_code/period 定位，Decimal round-trip，恢复时版本冲突返回 409 语义结果。
  - **Validation:** `rtk python -m pytest tests/formula_runtime/test_report_adapter.py -q --tb=short`

- [x] 7. 实现 NoteMutationAdapter [Req 3,4｜P3,P4]
  - 新建 `formula_runtime/adapters/note.py` 与测试。
  - 仅允许 auto cell；按 section/row/column 批量 prepare/apply/restore。
  - **Validation:** `rtk python -m pytest tests/formula_runtime/test_note_adapter.py -q --tb=short`

- [x] 8. 修复七条 logic_check 的真实失败语义 [Req 6｜P7]
  - 独占修改 `formula_management/logic_check.py`；#2/#5/#7 改为独立来源/真实条件。
  - 每条规则添加 pass + fail 样例；PBT 验证后端与前端降级模型等价。
  - **Forbidden:** 不改 engine/orchestrator。
  - **Validation:** `rtk python -m pytest tests/formula_runtime/test_logic_check_truth.py -q --tb=short`

- [x] 9. 把 reference 改为运行时关系 [Req 7｜P8]
  - 独占修改 `formula_management/reference_resolver.py`。
  - 实现运行时递归解析、visited 环检测、source_version/source_hash；源变更通过 outbox 标 stale。
  - 不在保存时复制 expression 作为权威值。
  - **Validation:** `rtk python -m pytest tests/formula_runtime/test_reference_runtime.py -q --tb=short`

- [x] 10. 修复 WpFormula 生命周期与 service ownership [Req 5,12｜P5,P6,P13]
  - 独占修改 `wp_formula_service.py`：save/list/delete 校验 project ownership。
  - save 不写 `last_computed_at`；定义更新递增 version/hash；reference 仅存关系。
  - 成功执行时间戳留给 runtime integration task。
  - **Validation:** `rtk python -m pytest tests/formula_runtime/test_wp_formula_lifecycle.py -q --tb=short`

- [x] 11. 建运行批次、快照、outbox 与并发约束 [Req 4,8,9｜P4,P9,P10,P11]
  - 先调用 `migration_status`，创建实时 `V{N+1}`，不得硬编码 V103。
  - 扩展 audit/snapshot/wp_formula 字段并建 `formula_runtime_outbox`；同步 ORM。
  - 新建 `formula_runtime/outbox.py`，实现 event_key 幂等 publisher/retry。
  - 加 migration 幂等与 rollback/outbox 同事务测试。
  - **Forbidden:** 不改 service/orchestrator/router。
  - **Validation:** `rtk python -m pytest tests/formula_runtime/test_runtime_persistence.py -q --tb=short`

- [x] 12. 收敛 engine 为 batch runtime 单一入口 [Req 1,2,5,11｜P1,P6,P14]
  - 独占修改 `formula_management/engine.py`。
  - 接收预加载 FormulaContext 与 canonical refs；支持 batch execute，不再逐 ref resolve。
  - apply 回调改为产 mutation intent，成功领域 apply 后才由上层确认 computed time。
  - 新建 legacy evaluator CI guard，禁止新增绕过 single kernel 的消费者。
  - **Validation:** `rtk python -m pytest tests/formula_runtime/test_engine_batch.py tests/formula_runtime/test_single_kernel_guard.py -q --tb=short`

- [x] 13. 接通 DraftRefreshOrchestrator 的真实领域 mutation [Req 1,3,7,8｜P2,P3,P8,P9]
  - 独占修改 `formula_management/draft_refresh_orchestrator.py`。
  - 新建/调用 FormulaRuntimeCoordinator，把 report/workpaper/adjudication/note scope 变为真实 mutation plan。
  - 删除 workpaper/adjudication “只产 page_keys + warning”占位路径。
  - 不 commit；返回 mutations、issues、hints、scope failures。
  - **Validation:** `rtk python -m pytest tests/formula_runtime/test_orchestrator_real_mutations.py -q --tb=short`

- [x] 14. 实现事务 apply、真实 rollback、fingerprint 与锁 [Req 4,8,9,10｜P4,P9,P10,P11,P12]
  - 独占修改 `draft_refresh_service.py`。
  - snapshot→adapter apply→audit→outbox 同事务；affected_count 仅计成功 apply。
  - rollback 逆序 restore 业务值并做 after_version CAS，冲突返回结构化 409。
  - 实现 fingerprint、advisory lock、all-or-nothing 默认、partial-success savepoint。
  - **Validation:** `rtk python -m pytest tests/formula_runtime/test_refresh_transaction.py tests/formula_runtime/test_real_rollback.py -q --tb=short`

- [x] 15. 收敛路由权限与 API 契约 [Req 10,12,13｜P13,P15]
  - 独占修改 `routers/draft_refresh.py`，增加 transaction_mode/idempotency_key 与 rollback endpoint。
  - 保留合伙人角色门禁；显式传 project ownership context；all-or-nothing 失败由 router rollback。
  - 新建后端 Pydantic response model 与 OpenAPI 契约测试，字段严格按 design；不创建或修改前端 contract 文件。
  - 空 scopes 不再隐式全量刷新；返回 422。
  - **Validation:** `rtk python -m pytest tests/formula_runtime/test_draft_refresh_api_contract.py -q --tb=short`

- [x] 16. 挂载生产 UI 并统一响应展示 [Req 13｜P15]
  - 独占修改 `GtRefreshScopeDialog.vue` 与 `layouts/ThreeColumnLayout.vue`；挂载真实入口并传当前 project/year。
  - 独占新建前端 `formulaRuntimeContract.ts`，对齐 Task 15 的 OpenAPI contract；修正 `result_status` 与 preset applied_count/page_count 等漂移字段。
  - success/partial/failed 分态展示；failed/partial 必须列失败目标；刷新后触发宿主数据重载。
  - 新增 Vitest 验证 production host、字段解析、失败不弹 success。
  - **Validation（cwd=audit-platform/frontend）:** `rtk npx vitest --run src/components/formula/__tests__/GtRefreshScopeDialog.spec.ts src/layouts/__tests__/ThreeColumnLayoutFormulaRuntime.spec.ts`

- [x] 17. 真实 PostgreSQL + Playwright 强验收 [Req 1–14｜P3,P4,P9,P11,P12,P16]
  - 新建 PG integration：四领域真写入、all-or-nothing、partial-success、并发单写者、outbox、rollback round-trip。
  - 重写 `tests/e2e/draft-refresh-regression.spec.ts`：移除默认 skip、同 admin 多角色、吞 response/selector 失败。
  - 用显式 fixture 创建/选择不同 partner/assistant/manager/eqcr 身份；核心断言不可条件跳过。
  - Playwright 实测刷新后值变化、结果计数、rollback 后恢复、console error=0。
  - **Validation:** `rtk python -m pytest tests/formula_runtime/integration/ -q --tb=short`；在 `audit-platform/frontend` 执行 `rtk npx playwright test tests/e2e/draft-refresh-regression.spec.ts`

- [x] 18. 完成度真实性守卫与最终收口 [Req 11,14｜P14,P16]
  - 新建 `backend/scripts/check/check_formula_runtime_completion.py`：检查叶子任务、PG/Playwright 证据、禁止默认 skip/吞错、single-kernel consumer drift。
  - 挂 `governance-checks.yml`；运行全量 formula_management + formula_runtime + 前端 formula tests。
  - 仅全部通过后更新本 `tasks.md`、`.kiro/specs/INDEX.md`；失败时保持未完成，不假绿。
  - **Validation:** `rtk python backend/scripts/check/check_formula_runtime_completion.py --strict`

## Task Dependency Graph

```json
{
  "version": 2,
  "policy": {
    "sameWaveSharedFiles": 0,
    "sharedIntegrationFiles": [
      "backend/app/services/formula_management/engine.py",
      "backend/app/services/formula_management/draft_refresh_orchestrator.py",
      "backend/app/services/draft_refresh_service.py",
      "backend/app/routers/draft_refresh.py"
    ],
    "rule": "共享集成文件各由一个串行 task 独占；同 wave 子代理不得触碰彼此 ownerFiles、generatedFiles 或 forbiddenSharedFiles"
  },
  "tasks": {
    "1": {"dependsOn": [], "ownerFiles": [], "generatedFiles": ["backend/tests/formula_runtime/test_current_gap_baseline.py", "backend/tests/formula_runtime/fixtures.py"], "forbiddenSharedFiles": ["backend/app/**"]},
    "2": {"dependsOn": [], "ownerFiles": [], "generatedFiles": ["backend/app/services/formula_runtime/__init__.py", "backend/app/services/formula_runtime/contracts.py", "backend/app/services/formula_runtime/adapters/__init__.py", "backend/tests/formula_runtime/test_contracts_pbt.py"], "forbiddenSharedFiles": ["**/engine.py", "**/draft_refresh_orchestrator.py", "**/draft_refresh_service.py", "**/routers/draft_refresh.py"]},
    "3": {"dependsOn": [2], "ownerFiles": [], "generatedFiles": ["backend/app/services/formula_runtime/value_loader.py", "backend/tests/formula_runtime/test_value_loader.py"], "forbiddenSharedFiles": ["**/engine.py", "**/draft_refresh_orchestrator.py", "**/formula_runtime/__init__.py"]},
    "4": {"dependsOn": [2], "ownerFiles": [], "generatedFiles": ["backend/app/services/formula_runtime/adapters/workpaper.py", "backend/tests/formula_runtime/test_workpaper_adapter.py"], "forbiddenSharedFiles": ["**/draft_refresh_orchestrator.py", "**/draft_refresh_service.py", "**/formula_runtime/adapters/__init__.py"]},
    "5": {"dependsOn": [2], "ownerFiles": [], "generatedFiles": ["backend/app/services/formula_runtime/adapters/adjudication.py", "backend/tests/formula_runtime/test_adjudication_adapter.py"], "forbiddenSharedFiles": ["**/draft_refresh_orchestrator.py", "**/draft_refresh_service.py", "**/formula_runtime/adapters/__init__.py"]},
    "6": {"dependsOn": [2], "ownerFiles": [], "generatedFiles": ["backend/app/services/formula_runtime/adapters/report.py", "backend/tests/formula_runtime/test_report_adapter.py"], "forbiddenSharedFiles": ["**/draft_refresh_orchestrator.py", "**/draft_refresh_service.py", "**/formula_runtime/adapters/__init__.py"]},
    "7": {"dependsOn": [2], "ownerFiles": [], "generatedFiles": ["backend/app/services/formula_runtime/adapters/note.py", "backend/tests/formula_runtime/test_note_adapter.py"], "forbiddenSharedFiles": ["**/draft_refresh_orchestrator.py", "**/draft_refresh_service.py", "**/formula_runtime/adapters/__init__.py"]},
    "8": {"dependsOn": [], "ownerFiles": ["backend/app/services/formula_management/logic_check.py"], "generatedFiles": ["backend/tests/formula_runtime/test_logic_check_truth.py"], "forbiddenSharedFiles": ["**/engine.py", "**/draft_refresh_orchestrator.py"]},
    "9": {"dependsOn": [], "ownerFiles": ["backend/app/services/formula_management/reference_resolver.py"], "generatedFiles": ["backend/tests/formula_runtime/test_reference_runtime.py"], "forbiddenSharedFiles": ["**/wp_formula_service.py", "**/engine.py"]},
    "10": {"dependsOn": [], "ownerFiles": ["backend/app/services/wp_formula_service.py"], "generatedFiles": ["backend/tests/formula_runtime/test_wp_formula_lifecycle.py"], "forbiddenSharedFiles": ["**/reference_resolver.py", "**/engine.py", "**/routers/draft_refresh.py"]},
    "11": {"dependsOn": [], "ownerFiles": ["backend/app/models/workpaper_models.py"], "generatedFiles": ["backend/app/services/formula_runtime/outbox.py", "backend/migrations/V{N+1}.sql", "backend/tests/formula_runtime/test_runtime_persistence.py"], "forbiddenSharedFiles": ["**/draft_refresh_service.py", "**/draft_refresh_orchestrator.py", "**/routers/draft_refresh.py"]},
    "12": {"dependsOn": [2, 3], "ownerFiles": ["backend/app/services/formula_management/engine.py"], "generatedFiles": ["backend/tests/formula_runtime/test_engine_batch.py", "backend/tests/formula_runtime/test_single_kernel_guard.py"], "forbiddenSharedFiles": ["**/draft_refresh_orchestrator.py", "**/draft_refresh_service.py", "**/routers/draft_refresh.py"]},
    "13": {"dependsOn": [3, 4, 5, 6, 7, 9, 11, 12], "ownerFiles": ["backend/app/services/formula_management/draft_refresh_orchestrator.py"], "generatedFiles": ["backend/app/services/formula_runtime/coordinator.py", "backend/tests/formula_runtime/test_orchestrator_real_mutations.py"], "forbiddenSharedFiles": ["**/engine.py", "**/draft_refresh_service.py", "**/routers/draft_refresh.py"]},
    "14": {"dependsOn": [11, 13], "ownerFiles": ["backend/app/services/draft_refresh_service.py"], "generatedFiles": ["backend/tests/formula_runtime/test_refresh_transaction.py", "backend/tests/formula_runtime/test_real_rollback.py"], "forbiddenSharedFiles": ["**/engine.py", "**/draft_refresh_orchestrator.py", "**/routers/draft_refresh.py"]},
    "15": {"dependsOn": [10, 14], "ownerFiles": ["backend/app/routers/draft_refresh.py"], "generatedFiles": ["backend/app/schemas/formula_runtime.py", "backend/tests/formula_runtime/test_draft_refresh_api_contract.py"], "forbiddenSharedFiles": ["**/engine.py", "**/draft_refresh_orchestrator.py", "**/draft_refresh_service.py", "audit-platform/frontend/**"]},
    "16": {"dependsOn": [15], "ownerFiles": ["audit-platform/frontend/src/components/formula/GtRefreshScopeDialog.vue", "audit-platform/frontend/src/layouts/ThreeColumnLayout.vue"], "generatedFiles": ["audit-platform/frontend/src/components/formula/formulaRuntimeContract.ts", "audit-platform/frontend/src/components/formula/__tests__/GtRefreshScopeDialog.spec.ts", "audit-platform/frontend/src/layouts/__tests__/ThreeColumnLayoutFormulaRuntime.spec.ts"], "forbiddenSharedFiles": ["backend/**"]},
    "17": {"dependsOn": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16], "ownerFiles": ["audit-platform/frontend/tests/e2e/draft-refresh-regression.spec.ts"], "generatedFiles": ["backend/tests/formula_runtime/integration/conftest.py", "backend/tests/formula_runtime/integration/test_formula_runtime_roundtrip.py"], "forbiddenSharedFiles": ["backend/app/**", "audit-platform/frontend/src/**"]},
    "18": {"dependsOn": [17], "ownerFiles": [".github/workflows/governance-checks.yml", ".kiro/specs/formula-runtime-convergence/tasks.md", ".kiro/specs/INDEX.md"], "generatedFiles": ["backend/scripts/check/check_formula_runtime_completion.py"], "forbiddenSharedFiles": ["backend/app/**", "audit-platform/frontend/src/**"]}
  },
  "waves": [
    {"id": "wave-0", "name": "并行基线与独立修复", "tasks": [1, 2, 8, 9, 10, 11], "dependsOn": [], "maxParallel": 6},
    {"id": "wave-1", "name": "并行批量加载与四领域适配器", "tasks": [3, 4, 5, 6, 7], "dependsOn": ["wave-0"], "maxParallel": 5},
    {"id": "wave-2", "name": "串行单一引擎集成", "tasks": [12], "dependsOn": ["wave-1"], "maxParallel": 1},
    {"id": "wave-3", "name": "串行生成编排接线", "tasks": [13], "dependsOn": ["wave-2"], "maxParallel": 1},
    {"id": "wave-4", "name": "串行事务与回滚", "tasks": [14], "dependsOn": ["wave-3"], "maxParallel": 1},
    {"id": "wave-5", "name": "串行路由契约", "tasks": [15], "dependsOn": ["wave-4"], "maxParallel": 1},
    {"id": "wave-6", "name": "生产 UI 接线", "tasks": [16], "dependsOn": ["wave-5"], "maxParallel": 1},
    {"id": "wave-7", "name": "真实 PG 与 Playwright 验收", "tasks": [17], "dependsOn": ["wave-6"], "maxParallel": 1},
    {"id": "wave-8", "name": "真实性守卫与状态收口", "tasks": [18], "dependsOn": ["wave-7"], "maxParallel": 1}
  ]
}
```

## Notes

- `Task Dependency Graph` 是子代理调度与文件所有权的机器可读真源；18 个任务均显式声明 depends/owner/generated/forbidden。
- Wave 0 最大并行度 6；Wave 1 最大并行度 5。同一 Wave 的 `ownerFiles ∪ generatedFiles` 两两不相交。
- `formula_runtime/adapters/__init__.py` 由 Task 2 独占创建；Tasks 4–7 禁止触碰，避免四个 adapter 子代理竞态。
- Tasks 12–15 分别独占 engine/orchestrator/service/router，必须串行；Task 15 不触碰前端，Task 16 独占前端 contract。
- Tasks 17–18 只修改验收/治理文件，不修改生产业务源码。
- 子代理退出前必须执行任务内 Validation；失败时保持 `[ ]`，不得假绿。

## Traceability

- Req 1–4：Tasks 2–7, 12–14, 17
- Req 5：Tasks 10, 12, 17
- Req 6：Task 8
- Req 7：Tasks 9, 13
- Req 8–10：Tasks 11, 13–15, 17
- Req 11：Tasks 3, 12, 18
- Req 12：Tasks 4, 10, 15
- Req 13：Tasks 15–16
- Req 14：Tasks 1, 17–18
