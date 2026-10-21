# 设计：合并附注页请求安全与身份校验（ConsolNoteTab CP-05）

> 关联：#[[file:.kiro/specs/consol-note-tab-request-safety-and-identity/requirements.md]]

## 一、整体思路

`ConsolNoteTab.vue`（2816 行）既有一套请求守卫基础设施（`createConsolRequestGuard` +
`captureNoteSnapshot` + `currentRequestedNoteContext` + `sameNoteContext`），但**缺 variant 维度、
缺暴露的 loadedNoteContext、缺 confirm 门控 / 身份校验 / 子操作守卫**。本设计在既有基础上线程化
variant、复用守卫模式，不新造机制。核心是「**上下文身份五元组** `{projectId, year, nodeKey, variant,
sectionId}` 贯穿加载 / 保存 / 子操作 / 晚到判定」。

## 二、关键架构决策（ADR）

### ADR-1：variant 作为上下文身份维度
`NotePageSnapshot` 加 `variant`（= `props.standard`），线程进 `capturePageSnapshot` /
`noteRequestGuard.getContext` / `noteSubOpGuard.getContext` / `isPageSnapshotCurrent` /
`sameNoteContext`。效果：切模板（soe↔listed）即使 project/year/node/section 全同，在飞请求也判过期。
理由：合并附注同一节点可切模板，模板切换必须让旧模板的响应作废，否则列结构 / 数据会错配。

### ADR-2：章节加载守卫与子操作守卫分离（noteRequestGuard + noteSubOpGuard）
两个独立 `createConsolRequestGuard`。子操作（差额 / 审核 / 公式 / 导入导出 / 汇总 / 删行 / 跳转 /
批注）用 `noteSubOpGuard`，章节加载用 `noteRequestGuard`。`watch` 对 scope/variant 变化**同时 abort
两个**，`onUnmounted` 同样。
理由：若共用一个守卫，打开差额弹窗会 `startRequest()` 顶掉正在飞的章节加载请求（误判过期）。
分离后两类请求互不干扰。
⚠️ 已知约束（见 §五 维护建议）：两守卫语义重叠，新增异步子操作须接 `noteSubOpGuard`，无强约束，
后续可考虑收敛为「单 guard + 两类 ticket」。

### ADR-3：isStale 增加 signal.aborted 条件（改 composable）
`consolRequestGuard.isStale` 原本只看 `sequence` + `sameContext`。scope 变化时 `watch` 调
`abort()`（不发新请求 ⇒ sequence 不变、context 可能变回原值），单靠原条件抓不住「只 abort 未重发」
的晚到。故 `isStale` 增 `ticket.signal.aborted ||`。
安全性：与既有 `consolRequestGuard.spec.ts` 17 例一致不回归——那些用例要么 abort 伴随 sequence
变化（仍真），要么无 abort（signal.aborted=false，不影响）。变异抽验证明此条唯一覆盖「unmount 中途」场景。

### ADR-4：共享脏确认 + 导航 epoch（confirm 去重 + latest-wins）
- `confirmDiscardDirty()`：模块级 `pendingDirtyDecision` promise，并发脏切换复用同一弹窗
  （R2.5 / R2.6 要求 confirm 恰 1 次）。
- `noteNavEpoch` + `navDirtyOriginal` / `navDirtyContext`：`onNoteNodeClick` 每次 `++epoch`，确认
  期间若有更新导航进来则本次返回 `'stale'`（latest-wins）；确认期间置空 selection 禁止保存，取消恢复 original。

### ADR-5：脏世代计数（noteDirtyEpoch）保护 PUT 期间编辑
`markNoteDirtyTracked()` 包 `markNoteDirty()` 并 `++noteDirtyEpoch`（替换 5 处 markNoteDirty 调用）。
`saveNoteData` 发起时记 `epochAtStart`，PUT 返回时若 epoch 已变（PUT 期间有新编辑）则**不清 dirty**，
`savedData` 仍用发起时冻结的 data 快照（不含新值），`editRows` 保留新值。覆盖 R5.5 及公式填入 / 批量
填入的「保存期间新编辑不被覆盖」。

### ADR-6：身份校验五维 + rejectNoteIdentity
`onNoteNodeClick` 载入边界校验：detail.template_type≠variant / detail.section_id≠请求（校验①，detail 后），
saved.node_key≠ / saved.content.template_variant≠ / saved.content.headers 列数≠模板（校验②，saved 后）。
任一不符 → `rejectNoteIdentity`（置空 selection + loadedNoteContext、`message.error`、返回 `'failed'`）。
`saveNoteData` 保存前亦校验 variant / sectionId。理由：后端回错数据时严禁静默落库。

### ADR-7：数据区起始行偏移（noteDataRowStart，启发式 + 待后端显式化）
拖选 DOM 行→存储行、批量导入按模板槽位回填，都需知道前导类别行数。当前 `noteDataRowStart(sec)` =
前导「仅第 0 列有文本、其余列空」的行数（启发式）。⚠️ 这是脆点（见 §五）：依赖数据形态，理想方案是
后端在 section 数据给显式 `_header_row_indexes` / `_data_row_start`（fixture 本有 `_header_row_indexes`
字段，现为 undefined）。本 spec 不改后端，用启发式先满足 50 例，维护建议记在 §五。

## 三、服务层改动

- `consolidationApi.ts`：`listConsolNoteFormulas(templateType, sectionId?, signal?)` /
  `getConsolNoteBreakdown(..., opts{..., signal?})` 加 signal 透传（生产正确性，测试 mock 不依赖）。
- `useCellComments.ts`：`loadComments(sheetKey?, signal?)` 加可选 signal，`await` 后 `signal?.aborted`
  则不覆盖 `comments.value`（晚到批注不挂到新章节）。向后兼容（无 signal 的调用方不受影响）。

## 四、测试侧两处 fixture 漂移校准（非假绿，git 实证）

### render 2 例：恢复自定义 Table/Column stub
从 `298ff78d8` 还原自定义 stub（Column 按 `:prop` 渲染 `.fixture-cell` + `data-prop`）。组件叶子列
绑定 `:prop=colIndex` 后 stub 才能渲染。**加固**：无 prop 的展示列（差额弹窗金额列）也传
`{row:{}, $index:0}` 作用域，否则 `#default="{row}"` 解构崩溃（late breakdown 回归根因）。

### projected cells copy/export 索引 [1]→[3]
测试引入时 listed 五-5-2 有 **11 行**（前 2 行 col0=`类  别` 表头重复行 + 9 内容行），后续 fixture
清理（`5914e315b`「mh trailing empty/data rows cleanup」等）删掉那 2 行 → 现 **9 行**。测试
`editRows[2][5]='505'` 对应复制/导出输出行从 1 变 3。断言随 fixture 校准（`toHaveLength(10)` 不变，
索引 `[1]→[3]`），行为意图（第 5 列金额经复制 / 导出在原列位保留）不变。

## 五、维护建议（本 spec 范围外，登记备查）

1. **noteDataRowStart 启发式脆**：推动后端 section 数据补显式 `_data_row_start` / `_header_row_indexes`，
   前端不再按「仅第 0 列有文本」猜类别行。
2. **两守卫语义重叠**：随异步子操作增多可考虑收敛为单 guard + ticket 分类，或 composable 内强约束
   「子操作必用 subOp」。
3. **ConsolNoteTab.vue 2816 行超大**：不在本 spec 拆分（刚大改完风险高），独立立项 + 充分回归再做。
4. **consolNoteHeaders.spec.ts 2 例 pre-existing 红**：同一 fixture 漂移（`noteBodyRows` 期望
   11 行 fixture），在 `consolNoteHeaders.ts` composable，由本 spec 的 task 2 单独判定处置。

## 六、变异抽验（证明 50 例不假绿，load-bearing）

| 变异 | 结果 | 结论 |
|---|---|---|
| 关 `isStale` 的 `signal.aborted`（`false && ...`） | 仅 `unmount aborts pending section load` 红 | 该条唯一覆盖「无 context 变化的 abort」 |
| 关 variant 身份校验（`if (false && ...)`） | 仅 `rejects mismatched variant identity` 红 | 身份校验 variant 维度 load-bearing |
| 关 `noteDirtyEpoch` 守卫（`if (true || ...)`） | `save preserves edits during PUT` 等 3 例红 | PUT 期间编辑保护 load-bearing |

三处均精确、单一来源可归因，证明断言非恒绿。
