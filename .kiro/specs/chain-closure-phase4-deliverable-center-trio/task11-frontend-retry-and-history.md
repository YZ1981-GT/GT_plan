# Task 11 — 前端失败项重试与历史

Spec: `.kiro/specs/chain-closure-phase4-deliverable-center-trio`（需求 5.6 / 6.3 / 6.5）

状态：**代码已改并已通过 Vitest 真挂载**（含变异哨兵红证据 + 单区域 vue-tsc 类型检查）。
真实浏览器（Playwright）与真实出具写库仍属 Task 15/16 外部依赖，未在本任务内执行。

## 一、交付边界

Task 10 虽在 tasks.md 预先标 `[x]`，但现读确认其 **trio 前端基础并未落到 HEAD**：
`deliverableApi.ts` 无任何 trio 类型/端点，`DeliverableCenter.vue` 仍走旧
`createFullDeliverables`（`/word-exports/full-deliverables`，仅登录态）。因此 Task 11
在搭建自身重试能力的同时，补齐了 trio 的前端接口契约（Task 10 描述的 readiness/trio/
item/attempt 类型与真实端点），全部对齐 Task 9 已登记的后端路由
`backend/app/routers/deliverable_trio.py`（prefix `/api/projects/{pid}/deliverables/trio`，
已在 `router_registry/report.py` 注册）。未改动任何后端端点。

## 二、改动文件

| 文件 | 改动 |
|---|---|
| `src/services/apiPaths/report.ts` | 新增 `deliverableTrio` 路径块（readiness/create/job/attempts/retry/itemDownload） |
| `src/services/deliverableApi.ts` | 新增 trio 类型（`TrioStepKey`/`ReadinessResult`/`ExportJobTrioItem`/`ExportJobTrioResult`/`ExportJobAttempt` 等）+ 状态常量（`TRIO_STATUS`/`TRIO_TERMINAL_STATUSES`/`TRIO_STEP_LABELS`）+ 方法（`fetchTrioReadiness`/`createTrio`/`fetchTrioJob`/`fetchTrioJobAttempts`/`retryTrioJob`/`trioItemDownloadUrl`） |
| `src/components/deliverable/TrioRetryPanel.vue` | **新建**：失败项重试入口 + append-only 尝试历史面板 |
| `src/components/deliverable/__tests__/TrioRetryPanel.spec.ts` | **新建**：6 个 Vitest 真挂载用例（含变异哨兵） |
| `src/views/DeliverableCenter.vue` | 接线 `TrioRetryPanel`（权限 `report:edit` 门控 + 快照有效性 + onMounted 载入 readiness/历史） |
| `tsconfig._phase4-trio.json` | **新建**：单区域类型检查配置（全量 vue-tsc 本仓 OOM，铁律㉔） |

## 三、关键行为（对齐需求）

- **重试入口仅失败项展示**（需求 6.3）：`v-if="isFailed(step.key)"`；成功/阻断项无重试按钮。
- **三条件齐备才可点**（需求 5.6）：`canRetry = canEdit && !serverDeniedPermission && snapshotValid`。
  否则按钮 `disabled` 并旁注中文原因（无权限 → "无编辑权限，无法重试"；快照失效 →
  "数据快照已变化，请重新检查前置链"）。快照失效时额外顶部全局提示。
- **点击调用真实 retry API**（需求 5.2 前端侧）：`onRetry` 调 `retryTrioJob(POST /jobs/{id}/retry)`，
  再 `pollUntilTerminal` 轮询 `fetchTrioJob` + `fetchTrioJobAttempts` 直到终态。
- **保留旧 attempt 错误 / 刷新不清空**（需求 5.4 / 6.5）：`mergeAttempts` 按 `id` 去重合并，
  incoming 可更新同 id 状态但**绝不删除**旧 id；轮询每轮上抛合并后的历史。
- **后端 403/409 以服务端为准**：retry 收到 409 → `emit('snapshot-stale')` + 置灰（不继续轮询）；
  收到 403 → 置 `serverDeniedPermission` → 置灰 + 中文提示。
- **全中文文案**；技术字段（SHA-256 / snapshot_id）保留英文标识。

## 四、测试与证据

命令（Windows / `rtk` 前缀 / `python` / `;` 连接）：

```
rtk npx vitest run src/components/deliverable/__tests__/TrioRetryPanel.spec.ts
npx vue-tsc --noEmit -p tsconfig._phase4-trio.json
npx eslint <changed files>
```

### 4.1 修复后绿

- Vitest：`6 passed (6)`。
- 单区域 vue-tsc：新建/改动文件 **0 error**（注入 `const TRIO_TOTAL: number = 'three'`
  确认类型检查真生效 → TS2322，随即还原）。
- ESLint：新建 trio 文件 **0 problem**（`no-status-string-literal` 已用 `TRIO_STATUS`
  常量消除）。

### 4.2 变异哨兵必须红（需求 7.1 反向变异）

把 `onRetry` 改为"仅改本地状态、不发真实请求"（删掉 `retryTrioJob(...)` + `pollUntilTerminal()`）：

```
❯ TrioRetryPanel.spec.ts (6 tests | 3 failed)
  × 点击重试调用真实 retry API 并继续轮询到成功，旧 attempt 保留
    → expected "spy" to be called 1 times, but got 0 times   (mockRetry)
  × 后端 409 时置为快照失效并上抛 snapshot-stale（旧原因不丢）
    → expected "spy" to be called 1 times, but got 0 times
  × 轮询刷新返回不含旧 attempt id 时，旧失败原因仍保留
    → attempts-updated 未上抛
```

断言 `expect(mockRetry).toHaveBeenCalledTimes(1)` / `toHaveBeenCalledWith('p1','job-1')`
正是"按钮必须发真实请求"的护栏；"只改状态"的实现无法通过。变异后已还原。

### 4.3 归因（铁律㉔ 脏树红归属）

`DeliverableCenter.vue` 经单区域 vue-tsc 带出 8 个 tsc error（DeliverableGroupList/
DeliverablePreview/OnlyOfficeEditor/stores.project）与 7 个 lint warning
（5 个 report-type 英文 + 2 个 `summarizeFullJob` 的 `=== 'failed'`）。
用 `git stash push -- DeliverableCenter.vue` 回到 HEAD 复跑，**同样 8 error / 7 warning
逐条一致**（仅行号因新增代码下移），确认全部为**预存**问题，均在本任务未触碰的文件/
旧代码段；Task 11 新增代码引入 **0** 新 error / 0 新 warning。已 `git stash pop` 还原。

## 五、未覆盖（如实标注）

- Task 15 Playwright 真浏览器 / Task 16 真实出具写库：外部依赖，需用户明确授权，未执行。
- `DeliverableCenter.vue` 中既存的 8 个 tsc error 与英文 UI 文案告警属历史债，不在本任务
  范围内修改（会越界触碰并行文件）。
