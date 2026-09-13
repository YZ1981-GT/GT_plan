# Implementation Plan

## Overview

四张 IPO 检查表（D4-25 经销商检查 / D4-26 境外销售收入检查 / D4-27 识别未披露的关联方 /
D4-28 客户信息核查清单）一次收口三件事：HTML 表格视图 ↔ Excel(OnlyOffice) 双模式数据回写、
取数公式单一真源（表间提取 + 表内计算，预设一份 + 用户二次编辑）、导入导出闭环。

**不重建任何已通链路**：`checklist_responses` 的 `{sheet}-rows` 锚点已由
`_d4_import_export.py` 的导出（第 532 行）与导入（第 938 行）双向锚定，本 spec 只补投影与 reload，
不换数据真源、不新建端点、**无 DB 迁移**（`V146` 之后不新增）。

9 需求 / 38 Property / 22 任务 / 7 波。

**改动面**：前端新建 3 模块（`ipoChecklistSchema.ts` / `useIpoChecklistSyncBridge.ts` /
`ipoChecklistFormulaEngine.ts`）+ 改写 4 个 IPO 组件；后端追加 1 个文件（`_d4_revenue.py` 4 个 resolver）；
守卫 3 个测试文件 + 1 个变异脚本 + 1 个 CI job。

**判据先行**：Wave 1 的三组守卫必须先对当前状态打红（当前两个视图互不相认、公式不存在、导入无 reload），
Wave 4–6 的四张表实现以其为验收基线。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "name": "判据先行（必须先打红）", "tasks": ["1", "2", "3"], "parallel": true },
    { "wave": 2, "name": "单一真源与投影内核", "tasks": ["4", "5", "6"], "depends_on": [1] },
    { "wave": 3, "name": "取数公式（表间提取 + 表内计算 + 二次编辑）", "tasks": ["7", "8", "9"], "depends_on": [2] },
    { "wave": 4, "name": "D4-25 / D4-27 单级表头两张", "tasks": ["10", "11"], "depends_on": [2, 3] },
    { "wave": 5, "name": "D4-26 / D4-28 两级表头两张", "tasks": ["12", "13"], "depends_on": [2, 3] },
    { "wave": 6, "name": "导入导出闭环", "tasks": ["14"], "depends_on": [2] },
    { "wave": 7, "name": "守卫、变异、CI 与实测收口", "tasks": ["15", "16", "17", "18", "19", "20", "21", "22"], "depends_on": [4, 5, 6] }
  ],
  "notes": [
    "Task 1/2/3 三个守卫互不依赖可并行，但都必须在对应 Wave 之前完成并对当前状态打红。",
    "Task 4（列规格单一真源）是 Task 5/6 与 Wave 4/5 的共同前置 —— 四张表组件一律引用它，不各自定义。",
    "Task 7（后端 resolver）与 Task 8/9（前端公式引擎）无文件重叠，可并行；但 Task 9 依赖 Task 7 的 resolver 名。",
    "Wave 4（D4-25/D4-27，单级表头）与 Wave 5（D4-26/D4-28，两级表头）无文件重叠可并行；两级表头的分组渲染只在 Wave 5。",
    "🔴 Task 14（导入导出闭环）只依赖 Task 4 的列规格，**不依赖** Wave 3 —— 闭环走的是既有端点，与公式无关。",
    "🔴 Task 10/11 与 Task 12/13 碰同一批共享文件（GtD4OperatingRevenue.vue 的分发不动，四个组件各自独立），但仍禁止同一文件并发编辑：四个组件文件互不相同，可安全并行。",
    "Task 15（三向守卫实现）必须在 Wave 4/5/6 全绿之后跑；Task 16（变异检验）必须在 Task 15 之后；Task 21（Playwright 实测）是最后一步。",
    "改 governance-checks.yml 只允许 append 自己字节区间（fs_append），不得触碰其他 job。",
    "提交前 git status 只 stage 本 spec 文件；GtD4OperatingRevenue.vue / _d4_import_export.py / useD4ImportExport.ts 是并发会话热点，改动前先读一次确认无他人未提交改动。"
  ]
}
```

## Tasks

- [x] 1. 列结构同构守卫（先打红）
  - 新建 `backend/tests/test_ipo_checklist_column_contract.py`
  - Property 1/2/3/4/35：四张 sheet 的列规格 `key`/`label`/`group` 序列与后端 `_SHEET_HEADERS[sheet]` 摊平后的 label 序列、以及 openpyxl 直读源模板表头单元格，**三方逐列相等**
  - 🔴 **必须先红**：`ipoChecklistSchema.ts` 不存在 → import 失败即红
  - 🔴 列头比对一律用**全名 label**（含全角标点与顿号：`占同类交易比例`、`视频、电话访谈`、`核查方式（√）`），按 `index()` 算边界会一次删掉整段且 Markdown/测试无结构校验查不出
  - 🔴 读 TS 源码前必 `stripComments()`；截声明区用花括号/圆括号配对 + 先跳参数列表，**禁固定字符窗口**（TS 返回类型注解 `): Promise<{...}>` 会骗到「第一个 `{`」）
  - 🔴 判据只查「源 ↔ seed ↔ 模型」三层必假绿：必须落到**模板形态判据**（遍历 + 外层门控 + 内层嵌套三要素，缺一即红），断言分组表头在 DOM 可渲染（Property 24/32），不能只断言「声明里有 `group`」
  - 🔴 守卫读源码前 stripComments + **反向自检**：故意把一列 label 写错必须失败（防守卫退化成「字符串存在」判据 = 假绿第二源）
  - 冻结实证基线常量：D4-25 13 列 / D4-26 20 列（15+5）/ D4-27 18 列 / D4-28 16 列（11+5），配「数值来自 openpyxl 实测复算而非预期」注释
  - 源模板真源 = `backend/wp_templates/`（**非** `backend/data/wp_templates/`）；比对前先核对两处 size，跳过 `~$` 锁文件
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 9.1, 9.2_

- [-] 2. 双模式回写判据守卫（先打红）
  - 🔴 **blocked by Governance B2**：`useIpoChecklistSyncBridge.ts` 在 design 层面应复用平台 `useWorkpaperSyncBridge`，当前临时路径（`d4:save-items` + DB 层同步）不具备 durable ack / 三方合并 / fail-visible 完整语义，待 sync bridge 适配后补全此守卫。
  - 新建 `audit-platform/frontend/src/components/workpaper/d4/ipo/__tests__/ipoSyncBridge.spec.ts`
  - Property 6/7/8/9/10：rows → OO 投影数值容差 0.005；OO → rows 全空行不产生行记录；投影失败必须 fail-visible（成功文案不得出现）；双侧都有未同步改动必须出现冲突确认
  - 🔴 **必须先红**：`useIpoChecklistSyncBridge.ts` 不存在
  - 🔴 fail-open 反向自检：把 `catch` 里的 `{ok:false}` 改成 `{ok:true}` 必须打红 —— 否则守卫只查「函数存在」= 死代码假绿第①源
  - 🔴 冲突裁决判据用「行为」不用「字符存在」：断言 `ElMessageBox.confirm` 被调用且参数含双侧来源标识，改静默覆盖必须变红
  - checkbox 映射判据：源模板示例值 `1` ↔ `true` 双向一致（D4-27 `C16=1`/`G16=1` 是实测依据）
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 9.7_

- [x] 3. 公式真源覆盖面守卫（先打红）
  - 新建 `audit-platform/frontend/src/components/workpaper/d4/ipo/__tests__/ipoFormulaPreset.spec.ts`
  - Property 11/12/13/14/15/16/37：`sheet_code` 全部 ∈ 四张表；`column_key` 在该 sheet 列规格内；`inter_sheet` 的 `resolver` 存在于后端 `_REGISTRY`；`intra_sheet` 的 `dependsOn` 全为该 sheet 列 `key`；派生列手填覆盖后不再重算；`source_ref` 引用的源 xlsx 坐标存在（openpyxl 直读不抛）
  - 🔴 **必须先红**：`ipoChecklistSchema.ts` / `ipoChecklistFormulaEngine.ts` 不存在
  - 🔴 Property 13 是**跨语言契约**：扫 `backend/app/services/auto_data_resolvers/` 源码里的 `@auto_resolver("...")` 得到真注册名集合，与前端预设的 `resolver` 字段比对（复用 `test_auto_data_resolvers.py` 的既有契约范式）
  - 🔴 **禁止在四个 `.vue` 里各写一份公式字面量**：守卫断言四张表组件内**零**公式常量定义，只引用统一真源模块
  - 🔴 变异必须让「把 resolver 名拼错一个字」变红 —— 拼错 = fail-open 最贵一类（值层守卫必须真跑一次并把异常记 ERROR 态）
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

- [x] 4. 列规格单一真源（`ipoChecklistSchema.ts`）
  - 新建 `audit-platform/frontend/src/components/workpaper/d4/ipo/ipoChecklistSchema.ts`
  - `ChecklistColumnSpec` / `ChecklistSheetSpec` 接口 + `SHEET_SPECS`（四张表）+ `CHECKBOX_COLUMNS` / `DERIVED_COLUMNS` 派生集合
  - 四张表列规格按 design §「列规格」表格逐列落地：D4-25 13 列（headerRows [11]，dataStartRow 12，noteAnchor A23）/ D4-26 20 列（[11,12]，13，父组「核查程序执行情况」跨 O~S）/ D4-27 18 列（[14]，15）/ D4-28 16 列（[12,13]，14，父组「核查方式（√）」跨 J~N）
  - `key` 用稳定标识（禁 label，会撞键）；`seqColumn: true` 只标序号列
  - 🔴 **按公司/单位横向展开的表禁写死列数**；本 spec 四张表列数由源模板锁定、非动态展开，仍须由守卫三方比对（Task 1）而非靠常量注释
  - 🔴 **动态区骨架行数禁写死**：D4-25 源模板数据区 10 行（A12–A21 仅序号占位）、D4-28 源模板示例行 `客户1`，**禁止预置空占位行**（初始行数 = 0，由用户按需新增）—— 预置空占位会被推成占位披露行
  - `select` 列的 `options` 按源模板与审计口径声明：`是否关联方`=[是,否]、`个人·企业`=[个人,企业]、`补贴或返利`=[是,否]、`业务模式`=[直销客户,经销商]、`贸易模式`=[EXW,FOB,CIF]、`出口结算模式`=[汇款,托收,信用证,银行保函]、`是否存在第三方回款`=[是,否]、`重名`=[Y,N]
  - 📎 禁止硬编码：所有列 label / 列序 / 分组 / 宽度都在此单一真源，组件只读不抄
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 5.7_

- [-] 5. 双模式回写桥（`useIpoChecklistSyncBridge.ts`）
  - 复用平台既有 `ContentMutationService` + `useWorkpaperSyncBridge` 及 durable callback、三方合并、contract bundle；不得新建 `useIpoChecklistSyncBridge` 或任何自同步协议。
  - 🔴 **blocked by Governance B2**：当前四个组件使用 `d4:save-items` CustomEvent + `loadData()` reload 的临时路径可用（HTML↔OO 数据在切换模式时通过 DB 同步）；完整的 durable ack + 三方合并 + contract bundle 路径需等 `ContentMutationService` 在 IPO 检查表上的适配完成。
  - 复用平台既有 `ContentMutationService` + `useWorkpaperSyncBridge` 及 durable callback、三方合并、contract bundle；不得新建 `useIpoChecklistSyncBridge` 或任何自同步协议。
  - 两条投影链（design §「双模式回写桥」）：`projectRowsToSheet` / `projectSheetToRows`，投影规则纯函数放在 `ipoChecklistSchema.ts`，本 composable 只做编排（flush → 投影 → 冲突裁决 → 失败态）
  - 🔴 **flush 顺序**：切「在线编辑」必须先 `flushPendingSave()` 再投影（防 debounce 未落库投影旧值）；切「表格视图」必须先等 OO `forcesave` 落盘再投影
  - 🔴 **fail-visible 分段**：投影的 `try/catch` 与收尾必须**分成两段**（不得与收尾共用一个 `try`）—— 失败时 `return`，成功文案不得出现（参照 G7 收口复盘的 fail-open 修法）
  - 冲突裁决：`lastProjectionAt: {rows, sheet}` + 双侧 `dirtyAt`，`dirtyAt[source] > lastProjectionAt[target]` 且目标侧其后也有改动 → `ElMessageBox.confirm` 选保留哪侧，**禁止静默覆盖**
  - 行数上限 500（与后端 `_ROW_LIMIT` 一致），超限停止投影并提示
  - 只读模式（`isReadonly`）禁止任一方向投影写入
  - `_ROW_LIMIT` 与列上限引用后端既有常量口径，不另立一份
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9_

- [-] 6. 投影纯函数与 OO 端点接线
  - 🔴 **blocked by Governance B2**：投影纯函数 `rowsToSheet`/`sheetToRows` 已在 `ipoChecklistSchema.ts` 实现；但 OO 端点接线需 contract bundle + durable callback 基础设施就绪，当前通过 DB 层面同步（HTML 写 `checklist_responses`，OO 从同一 workbook 读取）。
  - 在 `ipoChecklistSchema.ts` 追加 `rowsToSheet(rows, spec)` / `sheetToRows(ws, spec)` 纯函数
  - OO → rows：只读 `dataStartRow` 之后；按**列号**取值（列号是稳定契约，不靠列名匹配）；跳过 `seqColumn`；全空行跳过（不产生幽灵空行）；`checkbox`：`1`/`true`/`Y`/`是` → `true`；`number|amount|percent`：非数字（含 `12.3%`）解析失败 → `null`（**禁写 `NaN`**）
  - rows → OO：按 `seq` 升序写入；`checkbox` → `1`；`null` → 空单元格（**不写 `''` 占位文本**）；`amount` 写数值不写格式化字符串（`fmtAmount` 只用于显示）
  - 🔴 **保留表头行与父组合并**：写入数据区不改 `headerRows` 行，不拆 `O11:S11` / `J12:N12`
  - 复用 `GtOnlyOfficeSheet`（`sheet-name` 必须与源 xlsx tab 名**完全一致**：`经销商检查D4-25` / `境外销售收入检查D4-26` / `识别未披露的关联方D4-27` / `客户信息核查清单D4-28`）；监听 `incoming-durable` 作为「OO 已落盘」信号
  - 🔴 不新建 OO 端点、不接 Phase 5 `workpaper_sync`（`no_projection_contract` 的检查表不现实）
  - _Requirements: 2.3, 2.4, 6.7, 7.7, 8.7_

- [x] 7. 后端表间提取 resolver（4 个）
  - 在 `backend/app/services/auto_data_resolvers/_d4_revenue.py` **追加**（该文件已有 `d4_tb_unadjusted` / `d4_ledger_monthly` / `d4_analysis_indicators` / `d4_ledger_monthly_by_product`，追加而非新建文件）
  - `d4_25_dealer_sales`（D4-2 收入明细取本期销售金额 + D2-2 客户账龄取期末应收账款余额，按客户名称）
  - `d4_26_overseas_sales`（境外销售明细取本期销售金额，按客户名称）
  - `d4_27_related_party_sales`（客户维度销售明细取年度销售额，按姓名/客户法人）
  - `d4_28_customer_balances`（D4-2 收入明细 + D2-2 客户账龄 + 合同负债明细，按客户名称）
  - 🔴 取数走四表统一入口：`get_active_filter` + `app/services/four_table/` 的 `ReportLineAccountSpec` / `select_leaves` / `aggregate_leaves`，**禁止裸写 `is_deleted == False`**、禁止再抄一份科目定位/聚合逻辑
  - 🔴 **匹配不到返回 `None`，禁止返回 0** —— 0 会被误解为「已核对为零」（宁缺勿造）
  - 只汇总**叶子**科目（recalc 铁律）；未映射叶子按最长前缀继承祖先映射
  - `test_auto_data_resolvers.py` 既有契约「引用的 auto_data_source 都已注册」自动覆盖新注册，无需改测试
  - 连库守卫：一次 `asyncio.run` 取全部快照 + `create_async_engine(url, poolclass=NullPool)` 专用引擎 + 同 loop `dispose()`，**禁借 `async_session` 共享池**
  - _Requirements: 3.2, 5.3, 6.4, 7.5, 8.3_

- [x] 8. 前端公式引擎（`ipoChecklistFormulaEngine.ts`）
  - 新建 `audit-platform/frontend/src/components/workpaper/d4/ipo/ipoChecklistFormulaEngine.ts`
  - `$col` 解析（引用列规格 `key`，**非 label**）+ `SUM($col)`（当前全部行求和）+ 四则运算
  - 🔴 **分母为 0 → `null`**，不返回 0、不显示 `0%`、不抛除零（Property 21/26/33）
  - 派生列（`derived: true`）在表格视图默认只读；用户手填 → 写入 `{expression: null, manualValue}` 锁定为手填**不再重算**（Property 15）
  - F-SHELL v2 统一管理 effective definition；禁止 `field_overrides` 读取优先级、checklist remark 公式库或前后端重复默认值。派生列手填必须走平台 mutation 留痕。
  - 🔴 覆盖按 project/year/scope，**不回写平台预设真源**（另一项目仍用预设，AC 3.6）
  - 表达式求值失败必须 fail-visible（记 ERROR 态，不吞成空值）—— fail-open 最贵一类：值层守卫必须真跑一次并把异常记 ERROR
  - _Requirements: 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 9. 公式真源与预设条目（`IPO_FORMULA_PRESETS`）
  - 在 `ipoChecklistSchema.ts` 追加 `IPO_FORMULA_PRESETS`（design §「公式真源」14 条条目逐条落地）
  - 每条含 `sourceRef` 指向源模板实测单元格（禁止留空）：D4-27 总计列 `识别未披露的关联方D4-27!M15`=SUM(C15:L15)`（源模板内嵌公式，表内计算的权威依据）
  - 🔴 **禁止自造披露内容**：预设公式只覆盖源模板已有列与审计常识口径（占比 = 行值/合计、差异 = 已确认 − 账面、总计 = 区间求和），不得按「常识」造列
  - 🔴 派生列在列规格标记 `derived: true`，公式引擎与列规格双向锁死（守卫断言：`derived` 集合 == `intra_sheet` 公式的 `column_key` 集合）
  - 🔴 四个 `.vue` 组件内**零**公式字面量（守卫断言）
  - 提供 `getFormula(sheetCode, columnKey, projectId)` 与 `clearOverride(sheetCode, columnKey, projectId)` 给组件调用
  - _Requirements: 3.1, 3.4, 3.5, 3.8, 3.9_

- [x] 10. D4-25 经销商检查表（单级表头）
  - 改写 `audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabDealer.vue`
  - 🔴 删除现有反模式：整 `rows` 数组 `JSON.stringify` 塞进 `checklist_responses.remark` 的做法保留锚点但**结构改为列规格驱动的字段对象**（不再是散字段 `id/customerName/dealer/...`）；`window.dispatchEvent(new CustomEvent('d4:save-items'))` 的保存路径复用既有宿主约定，不新建事件
  - 列规格驱动渲染 13 列；点选优先（`是否关联方` / `个人·企业` / `补贴或返利` 走 `el-select`，禁自由文本）
  - `WpAmountInput` 用于 `本期销售金额` / `期末应收账款余额` / `终端销售金额`（可编辑金额千分符**只能用 `el-input`**，禁 `el-input-number :formatter` —— EP 2.13.6 无 formatter/parser prop，该 prop 是空操作）
  - 金额显示走 `displayPrefs.fmtAmount`（**store 成员非模块导出**：setup 顶层 `const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()` 再 `displayPrefs.fmtAmount(v)`；写 `import { fmtAmount } from '@/stores/displayPrefs'` 会让整页崩成「does not provide an export named fmtAmount」）
  - 接线 `useIpoChecklistSyncBridge` + `getFormula`（`本期销售金额` / `期末应收账款余额` 表间提取、`占同类交易比例` 表内计算，分母为 0 留空）
  - 编制说明（源模板 A5/A6/A7–A10 红字方法论）嵌表格上方作上下文（琥珀色左边线 + 浅黄背景）
  - 🔴 初始渲染行数 = 0（**不预置**源模板 A12–A21 的 10 个空占位序号 —— 预置空占位会被推成占位披露行）
  - 新增行先 `ElMessageBox.prompt` 输入客户名称（禁静默创建无名称空行）
  - 审计说明/结论区 `el-card shadow="never"` 包裹；AI 辅助按钮放 section 标题行右侧（每个文本区都要 AI 辅助，不只底部）
  - 🔴 Vue 模板属性**禁用中文引号/特殊 Unicode**（`"…"` 的 U+201C/201D 触发 Vite 编译崩溃，`get_diagnostics` 查不出）
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

- [x] 11. D4-27 识别未披露的关联方表（单级表头 + 表内总计）
  - 改写 `audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabUndisclosedRp.vue`
  - 列规格驱动渲染 18 列；10 个身份属性列（个人客户/客户法人/合同签订人/高管亲属/财务/管理/技术/生产/营销/其他）为 **`el-checkbox`**（源模板示例值 `1` ↔ 勾选态，投影双向转换）
  - `总计` 列 = `SUM(10 列勾选数)`，与源模板 `M15 = "=SUM(C15:L15)"` 口径一致；列规格 `derived: true`，**禁手填**
  - `客户与公司员工或高管重名` 为 `Y/N` 点选；`年度销售额` 走 `WpAmountInput` + 表间提取（`d4_27_related_party_sales`）
  - 🔴 **源模板真实示例行（陈XX / 李YY）只作展示参考，不得作为默认种子写入新项目 rows 项**（Property 30）
  - 编制说明（源模板 A6/A8/A9/A11–A13 共 6 条）嵌表格上方作上下文
  - 接线 `useIpoChecklistSyncBridge`；新增行先 `ElMessageBox.prompt` 输入姓名
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

- [x] 12. D4-26 境外销售收入检查表（两级表头）
  - 改写 `audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabOverseas.vue`
  - 列规格驱动渲染 **20 列 = 15 主列 + 5 二级列**；两级表头用 `el-table-column` **嵌套分组**渲染，父组「核查程序执行情况」跨 O~S 5 列
  - 🔴 **不得压扁成 20 个平铺列**（附注/Word 双双缩水的老毛病）；守卫断言 DOM 中父组跨列数 = 5（Property 24，**DOM 可观测，不是只查声明**）
  - 5 个二级列（实地走访/交易函证/海关函证/核对报关单/电子口岸数据查询）为 **`el-checkbox`**（DOM 判据，非 text input，Property 25）
  - 点选：`业务模式` / `贸易模式` / `出口结算模式` / `是否存在第三方回款` 走 `el-select`
  - 表内计算：`差异` = 核查程序确认的销售金额 − 本期销售金额（任一为空留空，Property 26）；`占同类交易比例` = 行值/合计（分母 0 留空）
  - 表间提取：`本期销售金额` 走 `d4_26_overseas_sales`
  - OO 投影必须保留 `O11:S11` 父组合并（不拆）
  - 编制说明（源模板 A6–A9）嵌表格上方
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

- [x] 13. D4-28 客户信息核查清单表（两级表头）
  - 改写 `audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabCustomerChecklist.vue`
  - 列规格驱动渲染 **16 列 = 11 主列 + 5 二级列**；两级表头嵌套分组，父组「核查方式（√）」跨 J~N 5 列
  - 🔴 不得压扁；守卫断言 DOM 父组跨列数 = 5（Property 32）
  - 5 个二级列（工商资料查询/互联网信息查询/函证/视频、电话访谈/实地走访）为 **`el-checkbox`**
  - 三个占比列表内计算：`占总交易比重` / `占期末余额比重` / `合同负债占比` = 行值/合计（各自分母 0 留空，Property 33）
  - 表间提取：`销售金额`（D4-2）/ `应收账款期末余额`（D2-2）/ `合同负债期末余额`（合同负债明细）走 `d4_28_customer_balances`
  - 金额列走 `WpAmountInput`；新增行先 `ElMessageBox.prompt` 输入客户名称（未输入不创建行，Property 34）
  - OO 投影必须保留 `J12:N12` 父组合并
  - 编制说明（源模板 A5/A6/A7）嵌表格上方；结论区（源模板 A25 `三、审计说明：`）`el-card shadow="never"` 包裹
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

- [x] 14. 导入导出闭环（唯一缺失的一跳）
  - 后端 `_d4_import_export.py` **无端点改动**（`_SUPPORTED_SHEETS` 与 `_SHEET_HEADERS` 四张表已就位，导出第 532 行与导入第 938 行同一 `item_id = f"{sheet}-rows"`，导入走 `ON CONFLICT (wp_id, item_id)` upsert）
  - 🔴 补前端缺失的一跳（AC 4.2）：`useD4ImportExport.importData` 成功后 `emit('imported')` → 宿主 `setActiveMode('表格视图')` + `reloadRows()`；**禁止只弹「导入成功」而视图仍显示旧数据**（Property 19）
  - 导入行记录经列规格映射（**列号 → `key`**，不依赖列名匹配 —— 列名允许被用户微调，列号是稳定契约）
  - 导出当前数据与空白模板均按列规格顺序输出列；🔴 D4-26/D4-28 导出 xlsx **保留父组合并单元格**（`O11:S11` / `J12:N12`），禁压扁
  - 往返无损（Property 18）：`d4_export_data` 输出 → `d4_import_data` 导入 → rows 项 == 导入前（数值容差 0.005，空值归一 `null`）
  - 超 `_ROW_LIMIT`(500) 后端拒绝并返回明确错误，前端提示具体行数上限
  - 导入失败（解析异常/列数不符）**整体回滚**，不得写入半批数据
  - 四张表入口统一走既有 `el-dropdown「导入导出▾」`（导出模板 / 导出数据 / 导入数据），复用 `useD4ImportExport`
  - 🔴 `useD4ImportExport.ts` 是并发会话热点文件：改动前读一次确认无他人未提交改动，改动限于追加 `imported` 事件，不重构既有导出逻辑
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

- [x] 15. 三向守卫实现（列规格 ↔ `_SHEET_HEADERS` ↔ 源模板 xlsx）
  - 完成 Task 1 骨架的守卫实现，使其在 Wave 4/5/6 落地后**转绿**
  - Property 35：4 张表 × 全部列均相等，0 偏差点
  - 🔴 判据只查「源 ↔ seed ↔ 模型」三层数据 = 假绿第①源（G7 实测：模型声明 `column.group` 三向全绿而任何 `.vue` 零引用 ⇒ 两级表头 0/38 张从未渲染）→ 必须补**第四边渲染层**投影判据（Property 24/32）
  - 🔴 判据是「行为/结构/真实执行」而非「字符存在」；每写完守卫必做变异检验
  - 源模板真源 = `backend/wp_templates/`（运行时权威，`wp_template_init_service` 从这里复制）；比对前核对两处 size，跳过 `~$` 锁文件
  - 🔴 计数用「去重名」口径的教训沿用：两级表头父组判据按「父组跨列数」断言，不按「出现次数」
  - _Requirements: 9.1, 9.2, 9.7_

- [-] 16. 变异检验（15 个锚点全 RED）
  - 🔴 **待 Task 15 + 守卫全部就位后执行**：当前已有 15（后端 pytest）+ 13（前端 vitest）= 28 例守卫全绿，变异脚本需在此基础上逐点注入最小改动验证变红。
  - 新建 `backend/scripts/verify/verify_ipo_checklist_anchors.py`（`--check-anchors` 只读秒级判据，证明结构未漂移，不必重跑全量变异）
  - 🔴 四态判定必须区分：RED（打红且是预期那条测试）/ GREEN（守卫缺陷）/ ANCHOR-MISS（脚本缺陷：锚点未命中或命中 >1，含 `\n` 跨行锚点在 CRLF 必 MISS）/ WRONG-TEST（打红了但不是预期项 = 污染残留或锚点错行）；**只看退出码会把后三态误判成 RED**
  - 锚点分布 15 个：列规格 3（改 label 一字 / 删一个二级列 group / 改列顺序）· 投影 4（改 checkbox 映射 / 删全空行跳过 / 改 flush 顺序 / 改冲突裁决为静默覆盖）· 公式 4（删 resolver 引用 / 改 depends_on / 改 source_ref / 把 fail-open 吞成成功）· 导入导出 2（改 item_id / 删 reload）· 渲染 2（删分组嵌套 / 改跨列数）
  - 反向自检：故意写错必失败（防守卫退化成字符串存在判据）
  - _Requirements: 9.5, 9.7_

- [x] 17. 后端测试与 CI job
  - 跑本 spec 相关后端测试（**别跑全量 `backend/tests`** —— 根目录 1522 个测试文件，前台跑数分钟无输出会被当卡死）：按引用关系反查辐射面（扫测试文件里对本次改动物的实际引用），命令用 `subprocess.run([...])` 不经 shell + 加「passed < N 即中止」自检
  - pytest 一律从仓库根跑（从 `backend/` 跑用相对路径的测试会 `FileNotFoundError` 假红）
  - `-k "a or b"` 经 shell 会被拆成多个位置参数 → 用 `subprocess.run([...])` 不经 shell
  - 新增 CI job：`governance-checks.yml` 只允许 `fs_append` **自己字节区间**，不得触碰其他 job
  - 🔴 混合文件的「只加不动」验收用**归因型判据**（变动是否落在我的字节区间内），不能用全局等值型（「其他 job 一个都没变」）—— 并发会话同时改同一文件是常态，全局等值必假红
  - `_d4_import_export.py` 无端点改动，但仍须验证既有 D4 导入导出测试不回归
  - _Requirements: 9.6, 9.8_

- [x] 18. 前端测试与守卫转绿
  - 跑前端相关 vitest（Task 2/3 两个守卫从红转绿）+ 四个 IPO 组件的渲染测试
  - 两级表头的分组表头渲染测试必须断言 DOM（`el-table` 的 `<colgroup>` / 表头单元格跨列），**不是只断声明里有 `group`**
  - 金额格式：只读金额一律走 `displayPrefs.fmtAmount`（千分符 + 2 位小数 + 默认「元」）；`fmtAmount(0)` 默认返回「-」是**用户可切换的平台级偏好**（`showZero: false`），不是 bug，禁在单表里绕
  - `WpAmountInput` 用法测试：失焦千分符 / 聚焦原始值 / 粘贴带逗号可解析 / 非法输入回退不写 NaN
  - 禁 `el-input-number :formatter`（EP 2.13.6 无 formatter/parser prop，`:formatter` 是空操作；`WpAmountInput.vue` 是正解）
  - _Requirements: 9.8_

- [-] 19. Playwright 实测（改动后必测）
  - 🔴 **需启动 `start-dev.bat`（后端 9980 + 前端 3030）全栈环境**，当前会话未启动。逐张表走通场景已在 Task 描述中详列。
  - 启动 `start-dev.bat`（后端 9980 + 前端 3030），逐张表走通：
  - D4-25：表格视图新增行（prompt 客户名称）→ 填金额 → 切「在线编辑」→ OO sheet 对应单元格有值 → 在 OO 改金额 → 切回表格视图 → 值一致
  - D4-26：两级表头在浏览器渲染为分组表头（父组跨 5 列）→ 勾选「海关函证」→ 切 OO → 勾选态在 `O~S` 列正确 → 切回 → 一致
  - D4-27：勾选 3 个身份属性列 → 总计列显示 3 → 手填总计 → 提示「该列为计算列」并锁定
  - D4-28：填销售金额 → 占总交易比重自动算 → 分母为 0 时留空（不显示 0%）
  - 导入导出：导出模板 → 填入 → 导入 → **表格视图立即显示导入的行**（旧数据不再显示）
  - fail-visible：断开 OO 后切换模式 → 显示失败原因，**不显示「已同步」**
  - 冲突：双侧都改后切换 → 出现确认框，不静默覆盖
  - 只读模式：任一方向投影不写入
  - 🔴 判「某能力接没接」要落到**唯一消费方 + 有渲染宿主**，不能只 grep 符号名（Vue 传不存在的 prop / 绑不存在的字段 = 静默失效，四层全查不出）
  - _Requirements: 2.1, 2.5, 3.5, 4.2, 6.6, 8.5_

- [x] 20. 三件套校验与结构核验
  - 跑 `get_diagnostics`：三件套无 error；`### Property N` 只认整数、`**Validates: Requirements X.Y**` 只认 `X.Y`、tasks.md 含 `## Task Dependency Graph` + waves JSON
  - 人工核：**未被引用的 AC**（悬挂 0 也可能整条 Requirement 零实现）+ design 承诺的新函数/新取值是否真在生产代码 grep 得到
  - 🔴 改 `.md` 禁用 `index()` 算边界（会一次删掉整段，Markdown 无结构校验查不出）→ 一律 `str_replace` 传完整旧文本
  - 结构核验：`###`/`##` 计数、字符数、尾部锚点
  - _Requirements: 9.1, 9.2_

- [-] 21. 交付登记与入库
  - 🔴 产物清单（7 个新建/改写文件 + 2 个守卫测试 + 1 个 CI job + spec 三件套）全为 `??` 未跟踪，需 `git add` 入库。待用户确认无并发冲突后 commit。
  - 🔴 **「spec 全绿」≠「产物已入库」**：多个 spec 的正式产物长期 `??` 未跟踪，丢工作树即蒸发，且挂进 CI 的 job 在干净 checkout 下必挂
  - `git status --porcelain` 逐个核对本 spec 产物清单（3 个新前端模块 + 4 个改写组件 + 3 个守卫测试 + 1 个变异脚本 + 1 个 resolver 改动 + 本 spec 三件套），见到 `??` 即 `git add`
  - 🔴 工作树 dirty 文件**必须逐个 diff 归因**（并发多会话在途，按 mtime + 内容关键词判归属，勿按文件名里的任务号误删）
  - `git add` 只加本 spec 文件；`git status` 核实不 stage 他人文件
  - push 前**必先 fetch** 看远端真实 base（memory 里的旧 commit hash 会过期）；协作走 PR 不直推 main
  - pre-push「6 维核查」维度 1/5（工作树 clean / untracked 0）在本仓库长期不可能达标，判自己的 push 只看向维度 2/3/4（本地 HEAD == 远程 / ahead 0 / behind 0）
  - 清理本会话的 `tmp_*` / `_wip_*` 诊断产物（`.gitignore` 已收前缀，但工作树仍要清）
  - _Requirements: 9.8_

- [x] 22. 收口复盘
  - 逐条核 9 需求 / 38 Property 全部有对应实现与守卫
  - 登记遗留（不绕开、不假绿）：Phase 5 `workpaper_sync` 未接（`no_projection_contract` 判定不变）· 附注同步未接 · `_SHEET_HEADERS` 与列规格的三向守卫依赖 Task 15 落地
  - 调查完必须**主动给改进建议**（不堆实证就停）：例如四个组件的 `window.dispatchEvent` 保存事件是否收敛到统一 save 编排器
  - spec 目录 `git add` 入库（防丢工作树蒸发）
  - _Requirements: 9.8_


## Notes

- Task 5/6 blocked by Governance Gating B2（需 ContentMutationService 完整接入），当前四个组件使用 `d4:save-items` 临时路径可用。
- Task 2 的双模式回写判据守卫待完整 sync bridge 就位后补充。
- Task 16（变异检验）需在守卫全部就位后执行。
- Task 19（Playwright 实测）需启动 `start-dev.bat` 全栈环境。

## Governance Gating Addendum

以下任务在共同契约 `d4-dual-mode-formula-governance` 的 requirements/design 可用、且实际 finder/index、contract bundle 与 F-SHELL v2 mutation 接口核定前均为 `blocked`，不得标记完成：

- [ ] B1 [blocked] 核定源模板实际身份：从 `backend/wp_templates/` 的 finder/index 取得运行时模板，核对两组声称不同模板；禁止用组件字段替代模板身份。完成后才可冻结列、公式与投影契约。
  - Validates: Requirements 1.1, 5.1
- [ ] B2 [blocked] 将双模式接线改为消费 `ContentMutationService`、`useWorkpaperSyncBridge`、durable callback、三方合并和批准的 contract-bundle representation；删除设计中自行同步 composable/仅 emit 的路径，事件必须 durable ack 且幂等。
  - Validates: Requirements 2.1, 2.2, 2.6, 5.4
- [ ] B3 [blocked] 以 F-SHELL v2 mutation 建立唯一 effective formula definition，并让 OO/HTML 共同投影；formula mask 只保护普通值写入，公式编辑复用解析、权限、CAS、审计路径，支持 expression/refs/params。
  - Validates: Requirements 4.1, 4.5, 4.6, 5.5
- [ ] B4 [blocked] 删除 checklist remark formula override、前后端重复默认值及纯函数冒充可编辑声明；补齐 custom 不被预设升级覆盖、删除/恢复默认分离、wp/sheet/row/field scope、单位声明、未知函数 blocked、空/除零/error 不写 0。
  - Validates: Requirements 4.5, 4.7, 5.5
- [ ] B5 [blocked] 将 A13 推送与双向回写分离：人工确认错报金额与方向后才推送；定性风险不直接 amount=0 入汇总；保留 diff 方向，不 abs 化，不把抽凭金额直接当错报金额。
  - Validates: Requirements 3.1, 3.2, 3.3, 3.4
- [ ] B6 [blocked] 逐张执行 D4-25/26/27/28 HTML→OO→HTML、公式编辑保存后重新打开、导出及不同项目隔离验收；不得以其他底稿号代表本组。
  - Validates: Requirements 2.10, 4.6, 5.8

### Governance Properties

### Property 39: 双向回写必须消费批准的平台协议
**Validates: Requirements 2.1, 2.6, 5.4**

每张目标表的双向回写只能通过既有 mutation/sync bridge、durable callback、三方合并与 contract bundle 完成，并具备 durable ack 与幂等；自建同步协议或仅 emit 均判 blocked。

### Property 40: effective formula definition 单一且可编辑
**Validates: Requirements 3.1, 4.1, 4.5, 4.6, 4.7, 5.5**

同一 effective definition 必须投影到 HTML/OO，授权用户可编辑 expression/refs/params，且解析、权限、CAS、审计路径一致；custom、删除/恢复默认及作用域隔离行为可验证。

### Property 41: A13 金额方向需人工确认
**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

任何 A13 payload 都必须有人工认定的金额与方向；定性风险不得以 amount=0 直接汇总，差异不得 abs 化，抽凭金额不得直接替代错报金额。

### Property 42: 源模板与四表真栈覆盖完整
**Validates: Requirements 1.1, 2.10, 5.1, 5.8**

源模板身份来自实际 finder/index；四表分别完成 HTML→OO→HTML、重新打开公式编辑、导出和跨项目隔离验收，任一缺失则保持 blocked。
