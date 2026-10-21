# 需求：合并附注页请求安全与身份校验（ConsolNoteTab CP-05）

## 背景与问题

`src/components/consolidation/__tests__/ConsolNoteTab.spec.ts`（50 例）是一份**先行写就、
组件从未实现的目标契约测试**（spec-first / 先打红）。本 spec 把这 50 例当验收标准，补齐
`ConsolNoteTab.vue` 的 6 个请求安全 / 身份校验行为域，使 48 个真实红转绿（2 例结构性原本就过）。

### git 实证（推翻「Phase-5 丢失行为」的初判，现算核实，非推测）

- 测试引入提交 `298ff78d8`（2026-10-08，commit msg「全量验证 90/90 通过」= **文件级假绿**）
  首次新增该测试文件。
- 在 `298ff78d8` 当时的组件里 `grep` 不到 `loadedNoteContext` / `autoSync.` / `leaveNoteEdit` /
  `onNoteDragStart` / `template_variant`（**一个都没有**），但同一提交的测试已引用 `loadedNoteContext`
  **8 次**。
- Phase-5 提交 `e29225abe`（2026-10-13）对 `ConsolNoteTab.vue` **只 +8 行、0 删除**（加一个映射弹窗
  import + `showMappingDialog` ref + `onDetailRefreshApplied`），**未触碰任何行为逻辑**。
- ⇒ 这 6 个行为域**从未被实现过**，是测试超前写的目标契约；不是任何重构删除导致的回归。
  这 50 例从诞生起就是红的，「90/90 通过」是没真跑这 50 例的假绿。

### 为什么这些行为是合理需求（而非过度设计）

合并附注允许用户在同一页面切换**模板变体**（国企 soe ↔ 上市 listed）、**树节点**（nodeKey）、
**项目/年度**（scope），并对单元格做未保存编辑。缺少请求安全时会出现真实数据损坏：
- 旧章节的异步响应（章节加载 / 公式填入 / 重汇总 / 批注）晚到，覆盖已切换到的新章节；
- 脏编辑未提示直接被模板切换丢弃；
- 保存期间切走再切回，旧 PUT 成功回调清掉新章节的 dirty（丢失用户新编辑）；
- 后端把错模板 / 错节点 / 错列宽的数据回给当前节点，被静默采用后落库污染。

## 术语

- **variant**：模板变体，`props.standard`（`'soe'` | `'listed'`），是上下文身份的一个维度。
- **loadedNoteContext**：已成功渲染的章节上下文 `{projectId, year, nodeKey, variant, sectionId}`。
- **noteRequestGuard**：章节加载请求守卫（既有）。**noteSubOpGuard**：子操作请求守卫（本 spec 新增，独立）。
- **NoteRefreshResult.status**：`'done' | 'skipped' | 'stale' | 'failed'`（既有枚举）。
- **noteDataRowStart**：章节数据区起始行号 = 前导「仅第 0 列有文本」类别行的数量（拖选 / 导入槽位偏移用）。

## 验收标准（EARS；逐条对应测试用例，50 例全绿为通过）

### 需求 1：loadedNoteContext 暴露（行为域 1）
- R1.1 WHEN `onNoteNodeClick` 成功加载并渲染章节 THEN 组件 SHALL 暴露 `loadedNoteContext` =
  `{projectId, year, nodeKey, variant, sectionId}`，其中 variant = 加载发起时的 `props.standard`。
- R1.2 WHEN 身份校验失败 THEN `loadedNoteContext` SHALL 置为 `null`（见需求 5）。
- R1.3 WHEN scope 变化清空当前章节后又重载新 variant THEN `loadedNoteContext.variant` SHALL 反映新 variant。

### 需求 2：脏状态切换 confirm 门控 + 并发只认最新（行为域 2）
- R2.1 WHEN 当前章节脏且用户切到另一章节 THEN 组件 SHALL 先弹 `ElMessageBox.confirm`，
  标题「切换附注」、确认按钮「放弃修改并切换」、正文含「未保存」。
- R2.2 WHEN 用户取消切章节确认 THEN `onNoteNodeClick` SHALL 返回 `status='skipped'`、恢复原
  `selectedNoteSection`、保留 `noteDirty=true`、不发 PUT。
- R2.3 WHEN 脏状态下模板变体变化且用户取消 THEN 组件 SHALL emit `restore-note-context`
  `{projectId, year, nodeKey, variant:旧, sectionId}`、置空 `selectedNoteSection`（不可保存），
  WHEN 父组件把 variant 改回加载值 THEN SHALL 原样恢复原章节对象且 `noteDirty` 仍 true。
- R2.4 WHEN 脏状态下模板变体变化且用户接受 THEN SHALL `noteDirty=false` 并加载新 variant，不 PUT。
- R2.5 WHEN 并发两次切章节（脏） THEN confirm SHALL 只调用 1 次（共享决策），first 返回 `'stale'`，
  latest 决定最终结果（接受→`loadedNoteContext.sectionId` = 最新；取消→恢复原章节 + dirty）。
- R2.6 WHEN 同一次 `setProps` 同时改 variant 与等价 node（nodeKey 不变）且脏 THEN confirm SHALL 恰 1 次。
- R2.7 WHEN `currentEntity` 换新对象但 nodeKey 不变 THEN 组件 SHALL NOT invalidate / confirm / 重新加载。

### 需求 3：scope 变化清空（行为域 3）
- R3.1 WHEN `year` / `projectId` / `currentEntity.nodeKey` 任一变化 THEN 组件 SHALL 置空
  `selectedNoteSection`、关闭过程弹窗（fill-result / breakdown / audit / aggregate）、使在飞请求过期，
  且 `saveNoteData()` 返回 false、不 PUT。
- R3.2 WHILE scope 刚变化尚未重载 THE 组件 SHALL 禁止保存（身份校验拦截）。

### 需求 4：子操作 AbortController（行为域 4）
- R4.1 THE 下列子操作 SHALL 接本次请求的 `AbortSignal` 并在响应提交前判过期：差额穿透
  （`getConsolNoteBreakdown` 第 4 参 opts.signal）、单表审核（`api.post` signal）、批量公式
  （`listConsolNoteFormulas` 第 3 参 signal）、公式文件导入 / 导出、ACNR 跳转（`resolveIndex`）、
  汇总确认（`confirmDangerous`）、删行确认（`confirmBatch`）、单文件 / 整簿导入、持久化重读。
- R4.2 WHEN scope / variant 切换后子操作响应晚到 THEN 组件 SHALL 作废：不写回新章节、不重开弹窗、
  不清新 scope 的 loading、不 `message.success`、不 PUT。
- R4.3 WHEN 连续两次 ACNR 跳转 THEN 组件 SHALL 只 `routerPush` 1 次且为最新目标（latest wins）。
- R4.4 WHEN 持久化重读（公式填入 / 重汇总后）晚到且上下文已切 THEN 返回 `'stale'`、不覆盖新 dirty、
  不弹 warning / success。

### 需求 5：status 契约与身份校验（行为域 5）
- R5.1 WHEN `onNoteNodeClick` 载入边界检测到 template_type / section_id / node_key / template_variant /
  列宽任一与请求上下文不符 THEN SHALL 返回 `'failed'`、置空 `selectedNoteSection` 与
  `loadedNoteContext`、`message.error`，且随后 `saveNoteData()` 返回 false、不 PUT。
- R5.2 WHEN `saveNoteData` 发起前 `loadedNoteContext.variant` ≠ 当前 `props.standard` 或
  `loadedNoteContext.sectionId` ≠ 当前章节 THEN SHALL 返回 false、不 PUT。
- R5.3 WHEN PUT 发起前冻结载荷快照 THEN `data.template_variant` SHALL = 加载时 variant；
  `data.rows` / `manual_cells` / `locked_cells` 按当前状态序列化透传。
- R5.4 WHEN PUT 返回时上下文已切（A-B-A）或响应 node_key 不符 THEN SHALL 返回 false、不报成功、不清 dirty。
- R5.5 WHEN PUT 期间产生新编辑（脏世代变化） THEN SHALL 返回 true 但保留 `noteDirty=true`，且落库
  `savedData` 为发起时快照（不含 PUT 期间的新值），`editRows` 保留新值。
- R5.6 WHEN `onNoteNodeClick` 的在飞请求被 abort（含 unmount）且晚到 resolve/reject THEN SHALL
  返回 `'stale'`、不复活旧章节、不 `message.error`。

### 需求 6：缺失方法补齐（行为域 6）
- R6.1 THE 组件 SHALL 提供 `leaveNoteEdit()`：脏时自管确认退出；确认晚到若上下文已切（variant /
  section / node / scope）则作废，不清新章节的 dirty / 编辑态。
- R6.2 THE 组件 SHALL 提供 `onNoteDragStart` / `onNoteDragMove`：从原生鼠标事件解析 td 的
  `cellIndex`（= 原始叶子列下标）与 tbody 行号 + `noteDataRowStart`（= 存储 editRows 下标），
  `onNoteDragStart` 调 `preventDefault()`，范围选区写入 `selectedCells`。
- R6.3 THE 叶子 `el-table-column` SHALL 绑定 `:prop=String(colIndex)`，使 `@cell-click` 的
  `column.property` 可解析原始列身份（`onNoteCellClick` 优先用 `column.property`，回退 label）。

### 需求 7：不假绿 / 不弱化（守卫纪律）
- R7.1 THE 50 例全绿 SHALL 由变异抽验证明 load-bearing（见 design §变异抽验）。
- R7.2 THE 既有 `consolRequestGuard.spec.ts`（17 例）SHALL 不回归。
- R7.3 THE 测试侧的两处 fixture 漂移校准（render stub 恢复、copy/export 索引）SHALL 保留行为意图、
  有 git 实证说明，不弱化断言。
