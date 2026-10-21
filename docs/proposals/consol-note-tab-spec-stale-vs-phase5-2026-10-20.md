# ConsolNoteTab.spec.ts 50 例全红：根因诊断与处置建议（2026-10-20，二轮深挖定稿）

## ✅ 最终结论（2026-10-20 收尾，已实现，50/50 全绿）
**方向 = 补齐组件实现（把测试当先行验收 spec），已完成。ConsolNoteTab.spec.ts 50/50 全绿，
无假绿（3 处变异抽验证明断言 load-bearing）。**

### 关键 git 实证（推翻初版「Phase-5 丢失」判断）
初版标题说「Phase-5 全面过期 / 丢失行为」——**经 git 实证为误判，已纠正**：
- Phase-5 提交 `e29225abe` 对 `ConsolNoteTab.vue` **只 +8 行 0 删除**（加 mapping dialog import +
  `showMappingDialog` + `onDetailRefreshApplied`），**没碰任何行为逻辑**。
- 测试引入提交 `298ff78d8`（commit msg「90/90 通过」= **文件级假绿**）当时，组件里 grep 不到
  `loadedNoteContext` / `autoSync.` / `leaveNoteEdit` / `onNoteDragStart` / `template_variant`
  （一个都没有），但测试已引用 `loadedNoteContext` 8 次。
- ⇒ 这 6 个行为域**从未被实现过，是测试超前写的目标契约**（spec-first / 先打红），不是任何重构
  删除导致的回归。这 50 例从诞生起就是红的。

### 已实现的 6 个行为域（均对准测试精确契约）
1. **loadedNoteContext 暴露** `{projectId,year,nodeKey,variant,sectionId}`；成功加载赋值、身份校验失败置 null。
2. **脏状态切章节/模板 confirm 门控**（`confirmDiscardDirty` 共享确认，文案「切换附注 / 放弃修改并切换」）
   + 并发 latest-wins（`noteNavEpoch` + `navDirtyOriginal`）+ 取消 emit `restore-note-context`。
3. **scope 变化清空**（watch 从单 `standard` 扩到 `{projectId,year,nodeKey,variant}` 对象 getter）：
   variant 变脏时确认、scope 变直接清空 + 关弹窗；等价 node（nodeKey 不变）不触发。
4. **子操作 AbortController**（新增独立 `noteSubOpGuard`）：breakdown / audit / fillAll / fillCurrent /
   aggregate / jump-ACNR / fileSelected / batchImport / exportFormulas / formulaImport / deleteNoteRows /
   reaggregate / cell-comments 全部接 signal + 过期判定；`consolRequestGuard.isStale` 增 `signal.aborted`。
5. **status 契约 + 身份校验**（template/section/node/variant/width 不符 → `rejectNoteIdentity('failed')`）；
   `saveNoteData` 保存前身份校验 + 冻结快照 + A-B-A 保护 + `noteDirtyEpoch` 守卫（PUT 期间新编辑不被清）。
6. **缺失方法补齐**：`leaveNoteEdit`（晚到确认按 `sameNoteContext` 作废）、`onNoteDragStart/Move`
   （DOM 行列→存储行映射，`noteDataRowStart` 偏移）；叶子列全部绑定 `:prop=colIndex`（真实改进，
   使 `@cell-click` 的 `column.property` 可用）。

### 测试侧两处「fixture 漂移」校准（非假绿，已 git 实证）
- **render 2 例**：恢复自定义 `Table/Column` stub（从 `298ff78d8` 还原 + 加固：无 prop 展示列也传
  `{row:{},$index:0}` 作用域，避免差额弹窗 `#default="{row}"` 解构崩溃）。组件绑定 `:prop` 后 stub
  才能渲染 `data-prop`/`.fixture-cell`。
- **projected cells copy/export 索引 `[1]→[3]`**：测试引入时 listed 五-5-2 有 **11 行**（前 2 行 col0=
  `类  别` 表头重复行），后续 fixture 清理（`5914e315b` 等）删掉那 2 行 → 现 **9 行**，`editRows[2]` 对应
  输出行从 1 变 3。断言随 fixture 校准，行为意图（第 5 列金额经复制/导出在原列位保留）不变。

### 相邻回归（git stash 实证归因）
- `consolRefreshWiring.spec.ts :: onNoteNodeClick 对持久化 GET 也检查 hasApiFailure`：本轮一度打红，
  根因 = 该测试用**固定 3000 字窗口**切 `onNoteNodeClick`，我在函数顶部加的确认门控/身份校验把第二个
  `hasApiFailure(saved)` 挤出窗口（两个检查其实都在）。已把窗口改为按函数边界切（robust，仍断言 ≥2）。已绿。
- `consolNoteHeaders.spec.ts :: listed 五-5-2/五-5-3 hides...`（2 例）：`git stash` 隔离证明**本轮改动前
  就红**（同一 fixture 漂移：`noteBodyRows` 期望 `rows.slice(2)` 得 9，现 fixture 仅 9 行 slice→7）。
  **非本轮引入**，且在 `consolNoteHeaders.ts` composable（本任务范围外），**未改**，如实标注待 fixture owner 处理。

### 变异抽验（证明不假绿）
- 关 `isStale` 的 `signal.aborted` → 仅 `unmount aborts pending section load` 红（唯一无 context 变化的 abort 场景）。
- 关 variant 身份校验 → 仅 `rejects mismatched variant identity` 红。
- 关 `noteDirtyEpoch` 守卫 → `save preserves edits during PUT` 等 3 例红。
三处均精确、load-bearing。

### 改动文件
- `ConsolNoteTab.vue`（6 域实现，M-dirty 并发会话的 `openFormulaManagerScope` 行未触碰）
- `composables/consolRequestGuard.ts`（isStale 加 signal.aborted）
- `services/consolidationApi.ts`（listConsolNoteFormulas/getConsolNoteBreakdown 加 signal 透传）
- `composables/useCellComments.ts`（loadComments 加可选 signal，晚到不覆盖）
- `__tests__/ConsolNoteTab.spec.ts`（恢复自定义 stub + copy/export 索引校准）
- `__tests__/consolRefreshWiring.spec.ts`（扫描窗口按函数边界，修我引入的回归）

---
## 以下为初版诊断（2026-10-20 上午，判断已被上方 git 实证纠正，保留作过程记录）

## 结论（一句话，⚠️ 已被上方纠正）
`src/components/consolidation/__tests__/ConsolNoteTab.spec.ts`（50 例）是**对 Phase-5 重构
（commit `e29225abe`）全面过期的测试**——测试编码的是 Phase-5 **之前**（或计划但未建）的、更
丰富的行为契约；Phase-5 重写组件时实现了一个**不同/更简的契约**，但未更新测试。本轮已：
1) **修掉一个真实生产 bug**（见下 §0，HEAD 既有）；
2) 把测试基座崩溃解除，使 **48 个真实契约差异**清晰可见（2 例结构性可过已过）；
3) 判定剩余 46 例需 consol-note Phase-5 spec owner 对「每个行为域是故意移除还是回归」拍板后
   才能正确转绿——本轮**不假绿、不单方面改契约**。

## §0 顺带修掉的真实生产缺陷（已保留在 ConsolNoteTab.vue）
`ConsolNoteTab.vue` 的 `onUnmounted` 里 `autoSync.cancelPending()`：**`autoSync` 从未定义**
（HEAD 既有，非并发会话引入），每次组件卸载抛 `ReferenceError`（Vue warn: Unhandled error
during execution of unmounted hook）——不仅污染测试套件使后续用例 vm 置 null，**生产里每次卸载
ConsolNoteTab 也会抛**。`useAutoSave` 本就在其内部 `onBeforeUnmount` 里 `stopTimer()` 自行取消
待存草稿定时器，无需也无 `cancelPending` 这个 API。已删除该行（保留为生产修复）。

## §1 测试基座过期（已解除崩溃，纯基座可改）
Phase-5 模板叶子列改为 `:label` + 作用域插槽 `row[col.colIndex]`，不再传 `:prop`。原 fixture 的
自定义 `Table/Column` stub 无作用域调用 `slots.default?.()` 把 undefined 传给模板 `#default="{ row }"`
解构抛错 ⇒ null vnode ⇒ @vue/test-utils 2.4.10 `getRootNodes`（库 7372 行对 null component 未守卫）
崩溃。**改用布尔 stub（Vue 默认 stub）即解除崩溃**（已实测：组件实例非 null、getRootNodes 安全、
真实行为照常跑）。本轮已把 `mountTab` 的 el-* stub 全部改为 `true`。

## §2 48 个真实契约差异（实测分桶，2026-10-20）
基座修好后 PASS=2 / FAIL=48，全部是行为断言差异（非崩溃）：

| 类别 | 数 | 差异本质 |
|---|---|---|
| selectedNoteSection / dirty / 身份状态 | 20 | Phase-5 的回滚/身份校验/dirty 语义与测试不同 |
| 调用次数 / confirm 门控 | 10 | 测试期望 `onNoteNodeClick` 脏时弹 `ElMessageBox.confirm`；Phase-5 的 `onNoteNodeClick` **不弹**（只有 `watch(standard)` 弹） |
| status 契约（stale/failed/skipped/done） | 9 | 请求守卫 `noteRequestGuard` 的作废/校验返回语义与测试期望不同 |
| 缺 abort/variant 字段 | 5 | breakdown/formula/aggregate 子操作**未接 AbortController**；`loadedNoteContext.variant` 已删 |
| 渲染断言（boolean stub 无 data-prop DOM） | 2 | 两个 render 测试需改断言到暴露 state（可改） |
| 方法不存在 | 2 | `leaveNoteEdit` / `onNoteDragStart` Phase-5 未实现 |

涉及 **6 个独立行为域**，均为「测试要求 A，Phase-5 实现 B」：
1. **脏状态切章节确认门控**：测试要 `onNoteNodeClick` 脏时弹 confirm + 并发只认最新；Phase-5 的
   `onNoteNodeClick`（2438-2534 行）无 confirm，只 `watch(standard)`（2536 行）有。
2. **scope 变化清空**：测试要 year/projectId/currentEntity 变化时清 selectedNoteSection + 关弹窗；
   Phase-5 只 watch `standard`。
3. **子操作 AbortController**：测试要 breakdown/formula/aggregate 的 service 调用带 `signal`；
   Phase-5 只有 `onNoteNodeClick`/`reloadCurrentSectionAfterRefresh` 用 `noteRequestGuard` 信号。
4. **请求守卫 status 语义**：作废/身份不符返回 'stale' vs 'failed' vs 'skipped' 的具体映射不同。
5. **已删 API**：`loadedNoteContext`（变体/章节上下文载体）整体移除——Phase-5 以 `selectedNoteSection`
   + `captureNoteSnapshot`/`currentRequestedNoteContext`/`sameNoteContext` 表达，无 `variant` 字段；
   PUT 体不含 `template_variant`（仅当 savedData 里带才透传）。
6. **未实现方法**：`leaveNoteEdit` / `onNoteDragStart`。

## §3 为什么本轮不把 46 例转绿（不假绿）
两条路都需 owner 的设计意图拍板，不能由我单方面做：
- **A 补回行为**：在 Phase-5 组件实现上述 6 域——是大行为 spec，且 `ConsolNoteTab.vue` 正被并发
  会话 M-dirty（formula-manager 的 `openFormulaManagerScope` 改动）。
- **B 改断言匹配现状**：把 46 条改成匹配 Phase-5 当前行为——这是**假绿**（用测试背书「当前代码即对」，
  而没人确认每个行为域是 Phase-5 故意简化还是回归）。

必须由 consol-note Phase-5 spec owner 对**每个行为域**裁决「故意移除（→改/删测试）还是回归（→修组件）」。

## §4 本轮交付物
- ✅ 生产 bug 修复：删 `autoSync.cancelPending()`（ConsolNoteTab.vue，保留）。
- ✅ 测试基座：el-* 改布尔 stub 解除 getRootNodes 崩溃（ConsolNoteTab.spec.ts，保留；使 48 真实
  差异可见、2 例已过），并删去因此不再使用的 `vue` import。
- 🔸 剩余 48（46 契约差异 + 2 render 可改）归 consol-note Phase-5 收尾；按本 §2 分桶 + §3 裁决路径执行。
- 诊断证据充分，未假绿、未弱化、未单方面改契约。

---
## 追加（2026-10-20 收尾第二轮）：spec 补办 + consolNoteHeaders pre-existing 红处置

### spec 三件套已补
`.kiro/specs/consol-note-tab-request-safety-and-identity/`（requirements / design / tasks），
把这 50 例当验收标准追认，记录 7 条 ADR（variant 维度 / 双守卫 / isStale signal.aborted /
共享确认+epoch / 脏世代 / 身份校验 / noteDataRowStart 启发式）+ 变异抽验表 + §五维护建议
（noteDataRowStart 启发式脆、两守卫语义重叠、2816 行文件待独立拆分）。已登记 INDEX.md。

### consolNoteHeaders.spec.ts 2 例 pre-existing 红：判定 = 测试硬编码旧 fixture，composable 正确
- `noteBodyRows(rows, headerIndexes)` 只排除**显式配置的**表头行（`_header_row_indexes`）。
- 现 fixture listed 五-5-2/五-5-3 的 `_header_row_indexes` 为 **undefined** ⇒ `noteBodyRows` 正确返回
  全部 9 行（含空白业务行 rows[2]/[3]），正是用例标题「keeps blank business rows」之意。
- 测试原 `expect(body).toEqual(sec.rows.slice(2))` 假设 2 个已被 fixture 清理删除的 `类  别` 表头行
  （测试引入时这些 section 有 11 行 + `_header_row_indexes=[0,1]`）。
- **处置 = 校准测试**（`slice(2)→sec.rows` + 加断言 `_header_row_indexes` 为 undefined 钉住意图），
  **不改 composable**（composable 行为正确）。变异反证：`noteBodyRows` 末尾加 `.slice(1)` → 5 例红
  （含这 2 例），证明校准后断言 load-bearing。
- 结果：consolNoteHeaders 12/12，合并目录 + useCellComments **297/0 全绿**。

### 最终改动文件清单（均未提交）
- `ConsolNoteTab.vue` / `composables/consolRequestGuard.ts` / `services/consolidationApi.ts` /
  `composables/useCellComments.ts`（生产 6 域 + 服务 signal 透传）
- `__tests__/ConsolNoteTab.spec.ts` / `__tests__/consolRefreshWiring.spec.ts` /
  `__tests__/consolNoteHeaders.spec.ts`（测试 fixture 漂移校准 + 回归修复）
- `.kiro/specs/consol-note-tab-request-safety-and-identity/`（新 spec 三件套）
- `.kiro/specs/INDEX.md`（登记）
- 本诊断文档
