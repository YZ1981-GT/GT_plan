# 设计：底稿深链单元格定位收口（wp-deeplink-cell-locate-closure）

## 1. 现状核对（2026-10-30，HEAD c952cd60c）

| 项 | 现状 | 证据 |
|---|---|---|
| 深链事件时机 | `WorkpaperEditor.vue` onMounted：nextTick + 300ms 发 `workpaper:locate-cell` | 文件内唯一一处 `setTimeout(…, 300)` |
| 渲染器挂载时机 | `GtWpRenderer` 由 `v-if="useHtmlRenderer && projectYear != null"` 控制；`useHtmlRenderer` 在 onMounted 的异步块里 await `fetchComponentType()`、`wpClassification.load()` 之后才定 | 浏览器 3 次：渲染器自己的 render-config 请求在进入编辑器后 1.09 / 1.14 / 1.10 秒发出；render-config 立即返回的对照组同样无定位（`tmp_acnr_foundation/out/rv762_control.json`） |
| 渲染器收事件 | `onLocateCell` 在 `!renderConfig.value` 时直接 return；`initialCell` 属性已声明、未使用 | `GtWpRenderer.vue` |
| 单元格锚点 | `[data-cell-ref]` 只在 `useCellLocate.ts` 里出现，没有组件渲染 | `git grep data-cell-ref` |
| 高亮样式 | `gt-locate-highlight` / `gt-locate-blink` 两个类全前端没有样式定义，加上类也看不见 | `git grep` 只命中 `useCellLocate.ts` |
| el-table 行号猜测 | `B5` → 整个 document 第 5 个 `.el-table__row` | `useCellLocate.locateElTable` 策略 2 |
| Univer 路径 | `UniverEditorCore` 在 `univerAPI` 就绪前收到事件即 return；只切 sheet | `UniverEditorCore.vue` `onBusLocateCell` |
| 行数 | `WorkpaperEditor.vue` 1361（棘轮 `line-budget.spec.ts` 1362）；`GtWpRenderer.vue` 1514（白名单 1509，+5% 上限 1584）；`E1TabAnalysis.vue` 155；`GtE1MonetaryFund.vue` 738 | splitlines 口径 |

## 2. 方案

### 2.1 编辑器（需求 1.1 / 1.3 / 1.4）
- 模板给 `GtWpRenderer` 加 `:initial-cell`（取 `route.query.cell` 的字符串值）。
- onMounted 里原「nextTick + 300ms 发事件」移进异步块的 Univer 分支（`if (useHtmlRenderer.value) return` 之后），HTML 路径不再由编辑器发深链事件。注释压缩，文件净行数不增加。

### 2.2 定位调度：新文件 `composables/useRendererCellLocate.ts`（需求 1.2 / 1.4 / 2.3 / 3.2~3.4）
`GtWpRenderer` 以回调注入依赖：`wpId()`、`ready()`（渲染配置已到）、`resolveSheet(locator)`、`activeSheetName()`、`selectSheet(name)`、`root()`（容器根元素）、`component()`（`activeComponentRef`）、`wpCode()`、`componentType()`，可选 `notify(msg)` 与 `waits`（重试间隔）。对外 `request(req)`：
1. `req.wpId` 与本底稿不符 → 忽略。
2. 未就绪 → 记为待办（只留最后一个）；`ready()` 变真时执行。
3. 执行：有 `sheetName` 先解析，解析不到 → 提示 3.2 并结束；与当前页签不同 → **同步** `selectSheet`（保持既有测试「发事件后 nextTick 即切页」的语义）。
4. 有 `cellRef` 时按 `waits`（默认 0 / 100 / 250 / 500 / 1000 ms，累计约 1.85 秒）重试：先调 `component().locateCell?.(target)`，返回真即结束；否则 `useCellLocate().locateCell(target, { root })`。全部失败 → 提示 3.3 一次。
5. 每次执行带序号；新请求到来时旧请求的后续重试作废。

`GtWpRenderer`：`onLocateCell` 改为 `request(payload)`；`watch([initialSheet, initialCell])`（immediate）在有 cell 时 `request`；就绪判定用 `!!renderConfig.value`。原 `onLocateCell` 内的切页与提示逻辑移入新文件，`GtWpRenderer.vue` 净行数减少。

### 2.3 `useCellLocate.ts`（需求 2.1 / 2.2 / 3.1）
- `locateCell(target, opts?: { root?: ParentNode })`：所有 `document.querySelector*` 改为在 `root ?? document` 内查（其他调用方不传 `root`，行为不变）。
- 删去 el-table「行号 = 第 N 行」策略。
- 导出 `highlightElement(el, key, className?)`：滚到可见 + 沿用原幂等与 3 秒淡出，供组件钩子复用。
- `styles/global.css` 补两个类的样式（单元格与块元素都可见；`gt-locate-blink` 为闪烁）。

### 2.4 E1-14 试点（需求 4）
- 新文件 `components/workpaper/e1/e1AnalysisCellAnchors.ts`：按模板登记三张表的行（行号 + 模板行标签 + 网页行序号）、列（模板列 → 网页列标题）与三个块（30 行 F3-2 提示、43~48 行审计说明、50 行审计结论）；`resolveE1AnalysisAnchor(cellRef)` 返回 `{ section, table?, rowIndex?, columnLabel?, block? }` 或 `null`。

| 区段 | 模板行 | 网页行 | 单元格级列（模板 → 网页列标题） | 其余列 |
|---|---|---|---|---|
| 构成 composition | 15 库存现金 / 16 银行存款 / 17 其他货币资金 | 0 / 1 / 2 | C 本期金额、D 本期结构比、E 上期金额、G 前期金额、I 本期变动率 | 整行 |
| 其他 other | 22~28 七类（与 `OTHER_FUND_ITEMS` 同序） | 0~6 | C 本期金额、E 上期金额、G 前期金额 | 整行 |
| 比例 ratios | 34~40 七项 + 41 占位（网页第 8 项「银行存款÷货币资金（集中度）」） | 0~7 | C 本期、D 上期、E 前期、F 本期变动、H~K 差异原因及合理性 | 整行 |
| 块 | 30 → F3-2 提示（other）；43~48 → 审计说明；50 → 审计结论 | — | — | — |

18、29 合计行与表外位置返回 `null` → 提示 3.3。
- `E1TabAnalysis.vue`：表格加 `data-e1-table`、两张卡片与 F3-2 提示加 `data-e1-anchor`；`defineExpose({ locateCell })`：解析锚点 → 切 `activeSection` → nextTick → 在本组件根元素内找表头文字对应列序号、第 `rowIndex` 个数据行的单元格（或整行 / 块）→ `highlightElement`。
- `GtE1MonetaryFund.vue`：给 E1TabAnalysis 加 ref，`defineExpose({ locateCell })`：当前 sheet 为 E1-14 时转给它，否则返回 false。
- 模板契约：`backend/tests/test_e1_analysis_anchor_template_contract.py` 解析锚点文件里的「行号 + 模板行标签」，用 openpyxl 读模板 B 列逐行比对；另核对三个块所在行的 A 列文字前缀。

### 2.5 提示文案
- sheet 找不到：「已打开底稿但未能定位到目标位置（可能已变更）」（不变）。
- 单元格找不到：「「{sheet_name}」的网页视图里没有单元格 {cell} 的对应位置」。

## 3. 测试与变异
- `composables/__tests__/useRendererCellLocate.spec.ts`：未就绪排队、就绪后执行；排队只留最后一个；sheet 解析失败提示；同步切页；组件钩子成功不再找 DOM；钩子失败找本渲染器内 `[data-cell-ref]`、不认根外元素；内容晚到时重试成功；全部失败只提示一次；新请求作废旧重试；wpId 不符忽略。
- `composables/__tests__/useCellLocate.scope.spec.ts`：`root` 限定；行号猜测已删（只有表格行时不高亮）；`highlightElement` 幂等与 3 秒移除。
- `components/workpaper/e1/__tests__/e1AnalysisCellAnchors.spec.ts`：锚点表逐格（C16、I15、D17、F15 整行、C22、G28、C34、F40、H34、K41、B30、A44、A50、C10、C18、C29、Z99）。
- `components/workpaper/e1/__tests__/E1TabAnalysis.locate.spec.ts`：真实 Element Plus 挂载，C16 切到构成页签并高亮「银行存款 / 本期金额」单元格；C34 切到比例页签并高亮比例表第 1 行「本期」列；A50 高亮审计结论卡片；C10 返回 false。
- `views/workpaper-editor/__tests__/deepLinkInitialCell.spec.ts`：读 `WorkpaperEditor.vue` 源码，断言 `GtWpRenderer` 带 `:initial-cell`、深链发事件只出现在 Univer 分支（`if (useHtmlRenderer.value)` 的 return 之后）。
- 后端：`test_e1_analysis_anchor_template_contract.py`。
- 既有回归：`GtWpRenderer.*.test.ts`、`line-budget.spec.ts`、`UniverEditorCore.*.spec.ts`、`WorkpaperShortLink.spec.ts`、`SideStandardsTab.spec.ts`、`LineageGraphPanel.spec.ts`、E1 相关测试。
- 变异（磁盘注入、sha256 还原）：M1 未就绪直接丢弃；M2 去掉根元素限定；M3 恢复行号猜测；M4 只试一次不重试；M5 锚点表行标签改错一行（后端契约红）；M6 HTML 路径恢复 300ms 发事件；M7 钩子返回值被忽略（总去找 DOM）；M8 E1 锚点命中后不切区段页签（C34 / B30 前端红）。

## 4. 浏览器验证
沿用 RV7.6-02 的隔离做法：候选提交的分离头 worktree 起后端 127.0.0.1:9987（`--lifespan off`、跳过启动迁移）与 Vite 3037；【测试】ACNR下钻走查_2025 经平台回收站恢复、结束经平台删除放回；无头 Chromium 每次新建上下文；C16 / B30 / C10 各 3 次独立运行，每次运行结束释放编辑锁；记录目标元素文字、提示文案、截图；对账覆盖本次走查的全部写请求（含不挂项目 id 的 `logs` 行）。

## 5. 不在范围的发现（转交）
- ACNR 目录单元格坐标：审计脚本 `tmp_wp_cell_locate` 下的探针（原 `tmp_acnr_foundation/probes/locfix_cell_audit.py`）现算 435 个未停用单元格：合并区域内 25、文字格 41、空格 356、数值 / 公式 11、找不到模板 2。空格多为录入格，不能据此判错；合并区域内与文字格两类需逐条复核。E1-14 三条来自 `backend/data/e_address_registry_seed.json`。纠错需重新发布目录，交 acnr-foundation-defect-closure。
- 其余组件接入锚点：机制就绪后按组件逐个接入（钩子或 `data-cell-ref`），本 spec 不做。
- 溯源弹窗把 `wp_code` 当 `wpId` 发事件：`TrialBalance.vue`、`Misstatements.vue`、`ConsolidationIndex.vue`、`useReportTrace.ts` 四处，所在页面无渲染器，事件无人接收。

## 6. 归档 spec 勘误（wp-locate-foundation，只登记不改归档文件）
- Task 4.2：深链定位用固定 300ms 延时发事件，早于渲染器挂载，事件丢失（本 spec 需求 1）。
- 「9 类 HTML componentType 全覆盖」：首选判据 `[data-cell-ref]` 无组件渲染、高亮类无样式、el-table 行号猜测会错位（本 spec 需求 2 / 3）。
