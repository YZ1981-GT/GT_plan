# Wave 3 试点回归报告 · 底稿可维护性收敛

> Task 4.4 — 完成 D2/K5/J2 试点 Round_Trip 与回归报告
> 需求追溯：3.9、8.1、8.2、8.3、8.4
> 生成日期：2026-07-14 · 环境：前端 3030 / 后端 9980 / 项目 `0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49`（admin/admin123）

## 1. 结论摘要

- Wave 3 三类试点（D2 复杂往来款/账龄、K5 历史 persistence 多连环、J2 多 section+AI+披露）已统一迁移到 **Runtime Boundary（`GtWpRenderer` 一次性 `useWorkpaperScaffold`）+ `useChecklistPersistence` 持久化适配器**。
- 三类底稿的 fresh-navigation Round_Trip 全绿：`console 0 error`、`PUT 成功`、`DB/GET 回读一致`、`刷新后 UI 回显一致`。
- 试点回归套件为 **3 个 Playwright 规格 / 6 个用例**，全部可独立复跑（headless），并已修复其中一个规格（`j2-runtime-migration.spec.ts`）因 J2 附注重建产生的**陈旧选择器**根因，无假绿。
- 支撑单测/PBT：**7 个套件 / 32 个用例全绿**（持久化适配器、Scaffold 单实例、Runtime Boundary、K5/J2/D2 迁移单元）。

## 2. Round_Trip 运行结果

### 2.1 试点回归套件（可复跑）

| # | 规格文件 | 用例 | 结果 | 覆盖 |
|---|---|---|---|---|
| 1 | `e2e/d2-maintainability-roundtrip.spec.ts` | 1 | ✅ passed (8.0s) | D2-2 明细编辑→保存→fresh nav 回显 + 真实复核抽屉 + D2-7 版本抽屉 |
| 2 | `e2e/workpaper-maintainability-pilots-roundtrip.spec.ts` | 3 | ✅ passed (20.9s) | D2/K5/J2 fresh nav → PUT → GET/DB 回读 → fresh nav UI 回显 + 版本/复核/AI |
| 3 | `e2e/j2-runtime-migration.spec.ts` | 2 | ✅ passed (9.1s) | J2-1 多 item（main/note/conclusion）+ 目录导航 J2-4 + 上市/国企披露 + 版本 + AI context 全字符串 |

运行命令（headless、复用已运行 dev server，避免抢占浏览器会话）：

```bash
# cwd: audit-platform/frontend
npx playwright test workpaper-maintainability-pilots-roundtrip.spec.ts --reporter=line
npx playwright test d2-maintainability-roundtrip.spec.ts --reporter=line
npx playwright test j2-runtime-migration.spec.ts --reporter=line
```

### 2.2 每类断言链（均为 fresh navigation，非同会话缓存）

对 D2/K5/J2 每类底稿：
1. fresh navigation 打开底稿（`?roundTrip=write-<marker>`）；
2. 用户可见字段写入 `marker` → 监听目标 `item_id` 的 PUT → 断言 `PUT ok` 且 `sent.remark === marker`；
3. `GET /checklist-responses` 回读 `remark === marker`；
4. **独立进程直连 DB**（`backend/scripts/e2e/read_checklist_response.py`）回读 `remark === marker`（证明真正落库，非前端内存）；
5. 二次 fresh navigation（`?roundTrip=read-<marker>`）→ 断言 UI 字段值 `=== marker`；
6. 恢复原值（PUT + GET + DB 三重确认还原），不污染共享测试项目；
7. 全程 `console/pageerror === []`。

### 2.3 支撑单测/PBT（32/32）

```
src/composables/workpaper/useChecklistPersistence.test.ts        5 ✓
src/composables/workpaper/useChecklistPersistence.unit.test.ts   7 ✓   (P3 encode/decode 往返、P4 debounce 隔离、P5 失败不进 saved)
src/components/workpaper/composables/__tests__/useWorkpaperScaffold.spec.ts  4 ✓  (P7/P8 单实例/嵌套幂等)
src/components/workpaper/GtWpRenderer.runtime-boundary.test.ts    2 ✓
src/components/workpaper/__tests__/k5PersistenceMigration.spec.ts 4 ✓
src/components/workpaper/j2/J2RuntimeMigration.unit.test.ts       8 ✓
src/components/workpaper/__tests__/useD2FormData.spec.ts          2 ✓
```

## 3. 迁移前后指标

### 3.1 Round_Trip 网络调用计数（迁移后·实测）

来自 `ROUND_TRIP_METRICS`（一次完整 Round_Trip = 2 次 fresh navigation：write + read）：

| 底稿 | render-config GET | checklist GET | checklist PUT | AI POST | 说明 |
|---|---|---|---|---|---|
| **D2** | 2 | 0 | 2 | 0 | 每次 fresh nav 1 次 render-config；checklist 从 render-config 内嵌 `responses_snapshot` hydrate（0 次独立 GET）；PUT = 写 + 还原 |
| **K5** | 2 | 0 | 4 | 0 | 同 D2 hydrate 策略；PUT 含审计说明写入/还原 + 版本快照触发链 |
| **J2** | 2 | 2 | 7 | 1 | J2 走独立 `checklist-responses` GET（2 次 fresh nav）；多 section（main/note/conclusion）+ AI 生成入统一持久化链 |

要点：
- **render-config 每次 fresh nav 恰好 1 次**，子组件不再重复 GET render-config（Runtime Boundary 已持有数据，子 composable hydrate 而非再拉取）。
- D2/K5 的 `checklist GET = 0` 是设计收益：主入口通过 render-config 内嵌 `responses_snapshot` 一次性 hydrate 到 `useChecklistPersistence`，省去二次往返；J2 保留直连 checklist GET 以支持其多 section 独立加载。
- 全部 checklist PUT 命中 `/api/workpapers/{wpId}/checklist-responses`，无 404 静默失败。

### 3.2 重复 provider / 保存实现消除情况

| 维度 | 迁移前（每个主入口自行接线） | 迁移后（Runtime Boundary 统一） |
|---|---|---|
| 版本链 | 各主入口 `useWorkpaperVersionToolbar()` + 模板挂 `GtWpVersionTrail` | `GtWpRenderer` 一次 `useWorkpaperScaffold`，`GtWorkpaperRuntimeHosts` 统一挂版本 Host；试点仅消费 `runtime.version.*` |
| 复核 | 各主入口 `useWorkpaperReviewProvide()` + `GtWpReviewDialogHost` | Runtime Boundary provide + Hosts 统一挂载 |
| displayPrefs | D2 主入口硬编码闭包 provide（`DisplayPrefs_Key`） | 收敛到 `useDisplayPrefsStore` 单一真源，由 Scaffold provide |
| 保存 I/O | 各 composable 自建 `saveTimer/pendingSave` + 裸 `http.put` + 静默 catch + `onScopeDispose` flush | 统一 `useChecklistPersistence`（load/hydrate/save/saveDebounced/flush/cancel/stateOf，每 item 独立定时器） |
| selfLoad | 各主入口手写 `_mergeResponses`（兼容 3 种键名）+ 手动 build Map | `hydrate(source)` 统一编解码，`collectK5Responses` 等薄适配 |

代码量净变化（工作树 diff）：

| 文件 | insertions | deletions | 备注 |
|---|---|---|---|
| `useChecklistPersistence.ts`（新增单一适配器） | +315 | 0 | 取代 N 份同构保存实现 |
| `GtWpRenderer.vue` | +29 | 0 | Runtime Boundary 一次性初始化 |
| `useWorkpaperScaffold.ts` | +254 | -~ | 支持祖先实例复用（InjectionKey）+ AI context 字符串化 |
| `GtD2AccountsReceivable.vue` | 少量 | -大量 | 删除本地 version/review/displayPrefs provider + 双 Host |
| `GtK5Provisions.vue` | 少量 | -~70 | 删除 `handleChildSave` 双层包裹逻辑、`_mergeResponses`、console.log 复核桩、本地版本工具条 |
| `useK5FormData.ts` | 少量 | -大量 | 205 行改动，净删除自建定时器/裸 PUT |
| `useD2FormData.ts` | 少量 | -大量 | 113 行改动，删除 `saveTimer/pendingSave/onScopeDispose` |
| D2/K5 一组文件 | 128 | 295 | 净删除 167 行同构代码 |

剩余 Wave 4 迁移规模（截至本报告，试点已从计数中移除）：

- `useWorkpaperVersionToolbar(` 直连主入口：**102** 个
- `useWorkpaperReviewProvide(` 直连主入口：**17** 个
- `console.log` 复核桩（💬 失效）：**46** 处
- 已接入 `useChecklistPersistence` 的文件：**5** 个（D2/K5/J2 试点 + 适配器 + K5 helper）

### 3.3 发现并修复的失败模式

| # | 失败模式 | 根因 | 修复 | 证据 |
|---|---|---|---|---|
| 1 | **D2 冷编译**（首屏导航偶发超时/白屏） | Vite dev 首次导航需冷编译 D2 大量 async 子组件 + loading overlay 叠加 | Round_Trip 以「目标卡片/根节点可见」为完成信号 + 30s 可见性等待，不做重复串行等待；不属产品缺陷 | `d2-maintainability-roundtrip.spec.ts` `openSheet` 30s 等待，warm/cold 均通过 |
| 2 | **K5 律师函 OCR `/api` 缺失** | `K5TabLitigationCheck` 调 `http.post('/d4/contract-ocr')` 缺 `/api` 前缀 → dev proxy 不转发 → 404 静默失败；且 OCR 结果字段路径过时 | 改为 `/api/workpapers/{wpId}/d4/contract-ocr`（`_silent`）+ 结果优先取 `extracted_fields.full_text` | `K5TabLitigationCheck.vue` diff |
| 3 | **K5 保存双层包裹 + 静默失败** | 旧 `handleChildSave` 对 `{remark}` 再 `JSON.stringify` 造成双层，reload 解析成 object 丢数据；catch 静默 | `toK5PersistencePatch` 解包一次；失败 `ElMessage.error` + 保留 dirty，不发保存事件/快照 | `GtK5Provisions.vue` diff（Round_Trip 回读一致证明单层落库） |
| 4 | **J2 named-export 运行时崩溃** | 5 个 J2 composable `import { http } from '@/utils/http'`（default-only 模块）→ Vite transform 200 但运行时 ESM 加载报错 | 统一 `import http from '@/utils/http'` | `useJ2FormData/CrossSheet/Disclosure/ImportExport/Integration` diff |
| 5 | **J2 展示字段被持久化污染** | 明细/审定表派生列（合计、审定数、期末等 auto-calc）此前随行序列化进 `remark` | 仅序列化 leaf/base 业务字段（AdjRow leaf/agg 模型派生列不入 remark）；J2-3 `entries` 只含业务列 | `J2TabAdjustment.vue` `scheduleSave`（`JSON.stringify(entries)`，合计为 computed 不入库） |
| 6 | **J2 附注 Round_Trip 陈旧选择器**（本任务修复） | 2026-07-14 J2 披露重建把根 class `.j2-tab-disclosure-*` 改为 `.j2-disclosure-*`；且版本抽屉关闭用全局 `.el-drawer__close-btn` first() 命中隐藏元素 | `j2-runtime-migration.spec.ts` 更新为 `.j2-disclosure-listed/soe`、版本抽屉关闭 scope 到 `.version-trail-drawer`、移除 J2 不适用的复核断言（J2 主入口不渲染复核 rail，与 pilots 规格一致） | 修复后 2/2 passed |

## 4. Wave 4 可复用迁移配方

对每个专属底稿主入口（`GtX*.vue`）按下述配方迁移，一次覆盖同循环全部 sheet：

### 4.1 迁移配方（8 步）

1. **注入 Runtime**：`const runtime = inject(WorkpaperRuntimeContextKey, null)`（`from './composables/useWorkpaperScaffold'`）。
2. **删除本地版本链**：移除 `useWorkpaperVersionToolbar(...)` 与模板中的 `<GtWpVersionTrail>`；改 `openVersionHistory = runtime?.version.openVersionHistory`、`scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot`。
3. **删除本地复核**：移除 `useWorkpaperReviewProvide(...)` 与 `<GtWpReviewDialogHost>`；复核 Host 由 `GtWorkpaperRuntimeHosts` 统一挂载。**console.log 复核桩必须删除**（46 处待清），复核 rail 仅在适用底稿保留。
4. **删除 displayPrefs 闭包**：移除硬编码 `provide(DisplayPrefs_Key, {...})`，收敛到 Scaffold 提供的 `useDisplayPrefsStore`。
5. **保存改用适配器**：`const persistence = useChecklistPersistence({ wpId, projectId, debounceMs })`；`handleChildSave` 改 `await persistence.save(itemId, patch)` + `runtime?.version.scheduleAutoSnapshot()`；失败 `ElMessage.error(persistence.stateOf(itemId).lastError)`，**不发保存事件/快照**。
6. **hydrate 替代手写 merge**：`selfLoad` 用 `persistence.hydrate(source)`（兼容 `responses_snapshot/allResponses/checklist_responses` 三键名与历史双层包裹），无 snapshot 时 `await persistence.load()`。
7. **卸载 flush**：`onBeforeUnmount(() => void persistence.flush().catch(() => undefined))`（禁止静默丢弃）。
8. **保留业务差异**：抽凭引擎、OCR、EventBus、TB 回写、公式引擎、行模型不动；仅收敛 I/O/缓存/debounce/错误/快照/横切能力。

### 4.2 每批次验证清单（必须全绿，缺一不可）

- [ ] **API 前缀**：所有 checklist / TB / OCR / render-config `http` 调用带 `/api` 前缀（缺失 → dev proxy 静默 404）。
- [ ] **default-only import**：`@/utils/http` 一律 `import http`（禁 `import { http }`，运行时才崩，get_diagnostics/Vite 200 查不出）。
- [ ] **单层序列化**：`remark` 仅编码一次；派生/展示列不入 `remark`；历史双层包裹仅读兼容。
- [ ] **project_id**：不得把 `wpId` 当 `project_id`；未显式提供则由后端从 `wp_id` 推导。
- [ ] **get_diagnostics**：改动文件全清。
- [ ] **Vite transform 冒烟**：全树 `.vue/.ts` 0 failure（transform 层）。
- [ ] **Runtime Import Smoke**：目标 componentType 动态 import 成功（抓 named-export/模块初始化错误）。
- [ ] **单测/PBT**：目标 composable 单测 + P3/P4/P5 持久化属性。
- [ ] **Playwright fresh-navigation Round_Trip**（每循环至少 1 条）：`console 0 error` + `PUT ok` + `GET 回读` + **DB 回读** + 二次 fresh nav `UI 回显一致` + 恢复原值。
- [ ] **横切能力用户可见**（按适用性）：版本历史抽屉可开/可关；复核对话绑定 wpId/sectionId（非桩）；AI context 值全字符串且失败不覆盖已有文本；目录/索引跳转精确匹配（`J1-1` 不误配 `J1-10`）。

### 4.3 复跑与取证工具

- DB 直连回读（只读）：`python backend/scripts/e2e/read_checklist_response.py <wp_id> <item_id>` → 输出 `CHECKLIST_DB_RESULT=<json>`。
- 网络计数：Round_Trip 用例内 `page.on('request')` 统计 render-config GET / checklist GET/PUT / AI POST，末尾打印 `ROUND_TRIP_METRICS`。
- 陈旧选择器排查：底稿重建（源模板对齐）后根 class 常变（如 `.j2-tab-disclosure-*` → `.j2-disclosure-*`），迁移前 `grep_search` 组件真实 `<div class=` 校对 e2e 选择器；**长开页面 HMR 会累积旧态，须 fresh navigation 取证**。

## 5. 附：试点 wp_id 与 item_id

| 底稿 | wp_id | sheet | 校验 item_id |
|---|---|---|---|
| D2 | `e2c95d10-181d-4549-8910-d5ab5bc5edd1` | D2-2 / D2-7 | `D2-detail-rows` / `D2-vc-conclusion` |
| K5 | `26acda99-1409-42de-883a-47adc9769c1a` | K5-1 / K5-3 | `K5-1-audit-conclusion` |
| J2 | `eb3cbf2d-394c-43e8-9296-a93ff41339ea` | J2-1 / J2-3 / J2-4 | `J2-1-main/note/conclusion` / `J2-3-note` |

三者同属项目 `0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49`，均已实例化并经 DB 校验。
