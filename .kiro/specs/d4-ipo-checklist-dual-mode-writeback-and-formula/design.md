# Design Document

## 目标与不做的事

四张 IPO 检查表（D4-25/26/27/28）一次收口三件事：**HTML 表格视图 ↔ Excel(OnlyOffice) 双模式数据回写**、
**取数公式单一真源（表间提取 + 表内计算，预设一份 + 用户二次编辑）**、**导入导出闭环**。

| 做 | 不做 |
|---|---|
| 复用 `checklist_responses` 的 `{sheet}-rows` 项作为唯一数据真源 | 不新建 DB 表、不写迁移 |
| 声明式列规格单一真源（含两级表头 `group`） | 不在四个 `.vue` 各写一份列/公式字面量 |
| 表间提取走后端 `auto_data_resolvers` 新 resolver | 不走 Phase 5 `workpaper_sync` OOXML 字节级路径 |
| 表内计算走前端公式引擎 + `source_ref` 指向源 xlsx | 不接附注同步（`no_projection_contract` 判定不变） |
| 用户二次编辑统一走 F-SHELL v2 mutation 的 `expression`/`refs`/`params`，由后端权威执行并投影 HTML/OO；不使用 `field_overrides` 或 checklist remark 作为公式库。默认、custom、删除、恢复默认分开，scope 为 `wp/sheet/row/field`。
| 复用既有 `useD4ImportExport` + `_d4_import_export.py` 端点 | 不新建导入导出端点 |
| 复用 `WpAmountInput` / `displayPrefs.fmtAmount` | 不引入新依赖 |

## 架构总览

```
                        ┌────────────────────────────────────────────┐
                        │  声明式单一真源（本 spec 新建，前端 TS）      │
                        │  ipoChecklistSchema.ts                     │
                        │   ├─ SHEET_COLUMNS[4]  列规格（key/label/   │
                        │   │                     group/type/options │
                        │   │                     width/derived）     │
                        │   ├─ IPO_FORMULA_PRESETS  公式真源           │
                        │   │     (sheet_code,row_key,column_key,    │
                        │   │      category,resolver|expression,      │
                        │   │      depends_on,precision,source_ref)   │
                        │   └─ CHECKBOX_COLUMNS / DERIVED_COLUMNS      │
                        └──────┬──────────────┬──────────────┬───────┘
                               │              │              │
        ┌──────────────────────┘              │              └──────────────────┐
        ▼                                     ▼                                  ▼
 ┌───────────────┐                 ┌───────────────────┐            ┌──────────────────────┐
 │ 表格视图        │  rows 项      │ 统一平台 mutation/sync bridge │◄──────────►│ sheet-name=源 sheet   │      │◄──────────────►│ useIpoChecklist   │◄──────────►│ sheet-name=源 sheet   │
 │ 按列规格渲染    │◄──────────────►│ SyncBridge.ts      │            └──────────────────────┘
 │ 分组表头(两级)  │  checklist_     │  flush → project  │
 └───────┬───────┘  responses       └───────────────────┘
         │              ({sheet}-rows.remark = JSON 数组)
         ▼
 ┌───────────────────────────────────────────────────────────────────────────┐
 │ 导入导出：useD4ImportExport ↔ _d4_import_export.py                         │
 │   _SHEET_HEADERS ←── 列规格摊平后的 label 序列（三向守卫钉死）              │
 │   item_id = f"{sheet}-rows"   ← 与 rows 项同一锚点（已存在，不新建）        │
 └───────────────────────────────────────────────────────────────────────────┘
                               ▲
 ┌─────────────────────────────┴────────────────────────────────────────────┐
 │ 取数公式                                                                  │
 │  表间提取 (inter_sheet)  → auto_data_resolvers 新 resolver（4 个）         │
 │     d4_25_dealer_sales / d4_26_overseas_sales /                           │
 │     d4_27_related_party_sales / d4_28_customer_balances                   │
 │     ← 数据源：D4-2 收入明细、D2-2 客户账龄、境外销售明细、合同负债明细      │
 │  表内计算 (intra_sheet)  → 前端公式引擎（引用本表 $col）                     │
  │ 统一平台协议：ContentMutationService + useWorkpaperSyncBridge + durable callback + 三方合并 │
 └───────────────────────────────────────────────────────────────────────────┘
```

## 数据真源与列规格

**唯一数据真源**：`checklist_responses` 表，`item_id = "{sheet_code}-rows"`，
`remark` 列存 JSON 数组（每元素一行）。**不迁移到 `sub_table_data`** —— 那是附注投影的规范形态，
本 spec 不接附注；后端 `_d4_import_export.py` 的导出（第 532 行）与导入（第 938 行）都已锚定 `item_id`，
换真源会让两侧同时失效。

**列规格**（新建 `ipoChecklistSchema.ts`）是唯一结构真源：

```ts
export interface ChecklistColumnSpec {
  key: string            // 稳定 key，禁 label（会撞键）
  label: string          // 中文 label，与源模板表头单元格逐字一致
  group: string | null   // 父组（两级表头），无父组为 null
  type: 'text' | 'number' | 'amount' | 'percent' | 'select' | 'checkbox'
  options?: readonly string[]   // type='select' 专用
  width?: number
  derived?: boolean      // 表内计算派生列（禁手填）
  seqColumn?: boolean    // 序号列（由 seq 派生，不参与投影）
}
export interface ChecklistSheetSpec {
  sheetCode: 'D4-25' | 'D4-26' | 'D4-27' | 'D4-28'
  sheetName: string          // 源 xlsx tab 全名（OO sheet-name 用）
  headerRows: number[]       // [11] | [11,12] | [14] | [12,13]
  dataStartRow: number       // 数据区首行
  noteAnchor?: string        // 结论/审计说明区锚点单元格
  columns: readonly ChecklistColumnSpec[]
}
```

四张表列规格（实测自源模板，真源 `backend/wp_templates/D/…IPO…xlsx`）：

| sheet | headerRows | 主列 | 二级列（父组） |
|---|---|---|---|
| D4-25 经销商检查 | [11] | 序号/客户名称/经销商/本期销售数量/本期销售金额/占同类交易比例/期末应收账款余额/是否关联方/个人·企业/销售费用承担方式/补贴或返利/终端销售金额/备注（13） | — |
| D4-26 境外销售收入检查 | [11,12] | 客户名称/所在国家地区/产品种类/业务模式/本期销售金额/占同类交易比例/贸易模式/主要贸易条款/出口结算模式/是否存在第三方回款/第三方回款原因/核查程序确认的销售金额/差异/差异原因分析（14） | 实地走访/交易函证/海关函证/核对报关单/电子口岸数据查询（5，父组「核查程序执行情况」） |
| D4-27 识别未披露的关联方 | [14] | 序号/姓名/个人客户/客户法人/合同签订人/高管亲属/财务部门/管理部门/技术部门/生产部门/营销部门/其他/总计/重名(Y·N)/公司股东高管亲属员工/年度销售额/说明/索引号（18） | — |
| D4-28 客户信息核查清单 | [12,13] | 序号/客户名称/选取原因/销售金额/占总交易比重/应收账款期末余额/占期末余额比重/合同负债期末余额/占期末余额比重（9）+ 索引号 | 工商资料查询/互联网信息查询/函证/视频·电话访谈/实地走访（5，父组「核查方式（√）」）→ 全表 15 列 |

**行记录**：`{ rowId: string, ...columns.map(c => c.key) }`。`rowId` 为稳定业务标识，不依赖 seq 排序或列号；列映射使用稳定 key 并校验结构，重复表头使用完整分组路径。

## 双模式回写桥（Requirement 2）

采用平台既有 `ContentMutationService`、`useWorkpaperSyncBridge`、durable callback、三方合并及批准的 contract-bundle representation；不得新增 `useIpoChecklistSyncBridge` 或其他自同步协议。两条投影链由平台 bridge 编排。

```
切「在线编辑」：flushPendingSave()          ← 必须先 flush debounce（防投影旧值）
            → projectRowsToSheet(rows, spec)  ← rows 项 → sheet 数据区
            → notifyDirty()                ← 记录 lastProjectionAt[rows]
            → mount GtOnlyOfficeSheet

切「表格视图」：await forceSave 落盘         ← 等 OO 未落盘内容落库
            → projectSheetToRows(sheet, spec) ← sheet 数据区 → rows 项
            → flushPendingSave() + reload
            → notifyDirty()                ← 记录 lastProjectionAt[sheet]
```

### OO → rows 投影规则（Property 6/7/8）

1. 只读 `dataStartRow` 之后的行（表头行与编制说明区一律跳过）。
**不适用固定列号**：投影按稳定 `columnKey` 与完整 `groupPath` 建立映射，并校验表头结构；禁止按列号或 label 猜测，重复表头必须以分组路径区分。
3. 跳过 `seqColumn`；跳过「全空行」（所有非序号列的值均为空）→ **不产生幽灵空行**（Property 8）。
4. `checkbox` 列：`1` / `true` / `Y` / `是` / 勾选 → `true`，其余 → `false`（D4-27 源模板示例值就是 `1`）。
5. `number|amount|percent` 列：非数字（含百分比文本如 `12.3%`）→ 按数值解析，解析失败 → `null`（不写 `NaN`）。
6. 行内全空则跳过；超过 `_ROW_LIMIT`(500) 停止并提示。

### rows → OO 投影规则

1. 行按 `seq` 升序写入 `dataStartRow` 起的数据区。
2. `checkbox` → `1`（与源模板口径一致）；`null`/`undefined` → 空单元格（**不写 `''` 占位文本**）。
3. `amount` 列写数值不写格式化字符串（`fmtAmount` 只用于显示）。
4. **保留表头行与父组合并**：写入数据区不改 `headerRows` 行，也不拆 `O11:S11` / `J12:N12`。

### 冲突裁决（Property 10，AC 2.5）

维护 `lastProjectionAt: { rows: number, sheet: number }` 与两侧 `dirtyAt`。
切换时若 `dirtyAt[source] > lastProjectionAt[target]` 且目标侧在 `lastProjectionAt` 之后也有改动 →
弹 `ElMessageBox.confirm`，说明「表格视图 / 在线编辑 在切换后都有改动」，由用户选择保留哪侧；
**禁止静默覆盖**。

### fail-visible（Property 9，AC 2.6）

投影包在 `try/catch`，**失败与成功必须分成两段**（不得与收尾共用一个 `try`）：

```ts
try { await project(...) } catch (e) {
  syncState.value = { ok: false, message: '同步失败：' + reason(e) }   // 不 return 成功文案
  return                                                                // 失败即中止收尾
}
syncState.value = { ok: true, message: '已同步' }                       // 独立段落
```

失败时保留源视图编辑不丢失（不清空 `rows`）。

## 取数公式（Requirement 3）

### 公式真源（声明式 dataclass）

`IPO_FORMULA_PRESETS` 是**唯一**公式字面量来源，四张表组件只引用、不定义：

```ts
export interface IpoFormulaPreset {
  sheetCode: 'D4-25' | 'D4-26' | 'D4-27' | 'D4-28'
  rowKey: '*' | string        // '*' = 全部行
  columnKey: string           // 目标列 key（必须在该 sheet 列规格内）
  category: 'inter_sheet' | 'intra_sheet'
  resolver?: string           // category=inter_sheet 时必填，后端 resolver 名
  expression?: string         // category=intra_sheet 时必填，引用 $col 表示本表列
  dependsOn: readonly string[]// 依赖列 key
  precision: number
  sourceRef: string           // 源 xlsx 单元格或审计依据，禁止留空
  reason: string              // 一句中文说明
}
```

预设条目（`source_ref` 全部指向源模板实测单元格）：

| sheet | columnKey | category | resolver / expression | source_ref |
|---|---|---|---|---|
| D4-25 | `本期销售金额` | inter_sheet | `d4_25_dealer_sales` | `经销商检查D4-25!E11` + D4-2 收入明细 |
| D4-25 | `期末应收账款余额` | inter_sheet | `d4_25_dealer_sales` | `经销商检查D4-25!G11` + D2-2 客户账龄 |
| D4-25 | `占同类交易比例` | intra_sheet | `'$本期销售金额' / SUM($本期销售金额)` | `经销商检查D4-25!F11` |
| D4-26 | `本期销售金额` | inter_sheet | `d4_26_overseas_sales` | `境外销售收入检查D4-26!E11` |
| D4-26 | `差异` | intra_sheet | `'$核查程序确认的销售金额' - '$本期销售金额'` | `境外销售收入检查D4-26!M11` |
| D4-26 | `占同类交易比例` | intra_sheet | `'$本期销售金额' / SUM($本期销售金额)` | `境外销售收入检查D4-26!F11` |
| D4-27 | `年度销售额` | inter_sheet | `d4_27_related_party_sales` | `识别未披露的关联方D4-27!P14` |
| D4-27 | `总计` | intra_sheet | `SUM($个人客户,$客户法人,$合同签订人,$高管亲属,$财务部门,$管理部门,$技术部门,$生产部门,$营销部门,$其他)` | `识别未披露的关联方D4-27!M15`=SUM(C15:L15)` |
| D4-28 | `销售金额` | inter_sheet | `d4_28_customer_balances` | `客户信息核查清单D4-28!D12` |
| D4-28 | `应收账款期末余额` | inter_sheet | `d4_28_customer_balances` | `客户信息核查清单D4-28!F12` |
| D4-28 | `合同负债期末余额` | inter_sheet | `d4_28_customer_balances` | `客户信息核查清单D4-28!H12` |
| D4-28 | `占总交易比重` | intra_sheet | `'$销售金额' / SUM($销售金额)` | `客户信息核查清单D4-28!E12` |
| D4-28 | `占期末余额比重` | intra_sheet | `'$应收账款期末余额' / SUM($应收账款期末余额)` | `客户信息核查清单D4-28!G12` |
| D4-28 | `合同负债占比` | intra_sheet | `'$合同负债期末余额' / SUM($合同负债期末余额)` | `客户信息核查清单D4-28!I12` |

### 表间提取（后端 resolver）

在 `backend/app/services/auto_data_resolvers/_d4_revenue.py` 追加（该文件已有
`d4_tb_unadjusted` / `d4_ledger_monthly` / `d4_analysis_indicators` / `d4_ledger_monthly_by_product`，
追加而非新建文件，避免多一个注册面）：

```python
@auto_resolver("d4_25_dealer_sales")
def d4_25_dealer_sales(db, project_id, year, customer_name):
    """按客户名称从 D4-2 收入明细取本期销售金额，从 D2-2 客户账龄取期末应收账款余额。"""
    ...
```

统一约定：
- resolver 入参含 `customer_name`（或 D4-27 的 `person_name`），返回 `{ sales_amount, ar_balance, ... }`。
- **取数走四表统一入口**：`get_active_filter` + `app/services/four_table/` 的
  `ReportLineAccountSpec` / `select_leaves` / `aggregate_leaves`，**禁止裸写 `is_deleted == False`**。
- 匹配不到时返回 `None`（前端显示空），**禁止返回 0** —— 0 会被误解为「已核对为零」。
- `test_auto_data_resolvers.py` 的契约「引用的 auto_data_source 都已注册」自动覆盖新注册。

### 表内计算（前端派生值预览，非 F-SHELL 公式定义）

表内计算（占比 / 差异 / 总计）是**本表算术派生值**，由前端纯函数引擎 `ipoChecklistFormulaEngine.ts`
（`evaluateExpression` / `recalcDerivedColumns`）在行创建与依赖列变更时重算。`$col` 引用统一解析为
**列规格 `key`**（非 label）：

- `$salesAmount` → `row.salesAmount`（本行本列）
- `SUM($col)` → 该列在**当前全部行**上的求和（跨行聚合）；`SUM($a,$b,...)` → 行内多列之和（D4-27 总计）
- 分母为 0 / 空 → `null`（不返回 0、不显示 0%、不抛除零，Property 21/26/33）
- **派生列**（`derived: true`）在表格视图默认只读。

🔴 **与 governance C2（F-SHELL v2）的边界判定**（对照 `c2_formula_contract.md`）：

| 维度 | 本表 intra_sheet 派生值 | C2 治理的公式定义（WpFormula） |
|---|---|---|
| 产物 | **普通数值**，写进 `row[columnKey]` → 序列化进 `checklist_responses.{sheet}-rows.remark` | 持久化公式定义（`expression`/`refs`/`preset`/`custom`） |
| 引用范围 | 仅本表列（本行 / 本表跨行） | 可跨底稿（走 ACNR `full_resolve`） |
| 用户可编辑表达式 | **否**（预设为代码常量 `IPO_FORMULA_PRESETS`） | 是（走 FormulaBar / F-SHELL v2 白名单 DSL） |
| CAS / 留痕 | 由数据层 CAS 兜（P0-4 `checklist_responses.content_version`） | 定义版本 CAS（`baseVersion`） |

**结论**：intra_sheet 派生值属 c2 契约 C.3 明列的「普通值 override 正交域」，**不纳入 F-SHELL v2 治理**；
它不进 `WpFormula`、不进 `remark` 公式库、无 `field_overrides` 覆盖库，不违反 governance 三禁（自建 sync
bridge / field_overrides 公式库 / 前后端重复默认值）。真正的**公式**部分（表间提取 inter_sheet）已走后端
`@auto_resolver` 权威执行，Property 13 跨语言契约守卫钉死。若未来需要**用户可编辑的公式**，才走 F-SHELL v2。

### 派生列手填锁定（非公式覆盖库）

用户在派生列直接手填 → `useIpoChecklistTab.updateCell` 把该 `${rowId}:${columnKey}` 记入 `manualLocks`
（内存 Set），写入的是**普通值**，`recalcDerivedColumns` 遇锁定项跳过、不再重算（Property 15）。
删除该行或清空手填即解锁回落预设重算。**无 `{expression, manualValue}` 覆盖库，无 project 级 field_overrides**
——手填值与其它单元格一样走 `persist` → `d4:save-items` → 平台保存（含 CAS 留痕）。跨项目天然隔离：
另一项目的 rows 项独立，预设公式对其照常生效（AC 3.6）。

## 导入导出闭环（Requirement 4）

后端 `_d4_import_export.py` 的列头与锚点已就位，**不新建端点**。三处对齐：

1. **列头三向守卫**：`_SHEET_HEADERS[sheet]`（1D 摊平）== 列规格摊平后的 `label` 序列 == 源模板表头单元格。
   任一处改动必须同步另一处（守卫在 CI 跑，防漂移）。
2. **导入后 reload**（AC 4.2）：组件 `handleImportFile` 在 `importData` 返回非 null 后
   `await reloadHost()`（宿主 `GtD4OperatingRevenue.vue` `provide('reloadWorkpaperData', selfLoad)`）
   + `emit('imported')`。禁止只弹「导入成功」而视图仍显示旧数据。
3. **导出保留两级表头合并**：导出 xlsx 对 D4-26/D4-28 写入父组合并单元格
   （`O11:S11` / `J12:N12`），禁止压扁成 19/15 个平铺列头。

往返无损（Property 18）由守卫断言：`d4_export_data(sheet)` 输出 → `d4_import_data` 导入 →
rows 项内容 == 导入前（数值容差 0.005，空值归一为 `null`）。

## 前端组件接线

宿主 `GtD4OperatingRevenue.vue`（`KNOWN_HTML_SHEETS` 已含 D4-25~28）不动分发逻辑，
只改四个组件内部。四张表共享三个模块 + 复用平台既有 sync bridge：

| 文件 | 职责 |
|---|---|
| `d4/ipo/ipoChecklistSchema.ts` | 列规格 + 公式真源 + 投影规则纯函数（`rowsToSheet` / `sheetToRows`） |
| `d4/ipo/useIpoChecklistTab.ts` | 四表共享行逻辑（CRUD / 派生列重算 / rows 项持久化 / `flushPendingSave` / `reloadHost`） |
| `d4/ipo/ipoChecklistFormulaEngine.ts` | 前端 intra_sheet 派生值预览纯函数（非 F-SHELL 公式定义，见上「表内计算」判定） |
| **复用** `components/workpaper/sync/useWorkpaperSyncBridge.ts` | 平台既有双模式桥（**非自建**）：组件传 `flushHtml`(先 `flushPendingSave` 再 `readStoreProjection`) + `reloadHtml`(=`reloadHost`)，配 `WorkpaperSyncEditorHost` + `capabilityForEntry`（参照 D4-5 canary）。冲突裁决 / durable ack / 三方合并由平台桥兜（governance C1）。 |

🔴 **不新建 `useIpoChecklistSyncBridge`**（governance 明令禁止自建同步 composable）。双模式回写走平台
`useWorkpaperSyncBridge`（真实路径 `components/workpaper/sync/`），冲突裁决与 fail-visible 由平台桥的
`feedback`/`state` 提供，组件只做 `syncFeedbackErr` 独立 `el-alert` 展示（失败不显示「已同步」）。

四个组件（`D4Tab{Dealer,Overseas,UndisclosedRp,CustomerChecklist}.vue`）改写为：

1. 列规格驱动渲染（禁止硬编码列数组）；两级表头用 `el-table-column` 嵌套分组。
2. 点选优先：`select` 走 `el-select`、`checkbox` 走 `el-checkbox`、`amount` 走 `WpAmountInput`。
3. 金额显示走 `displayPrefs.fmtAmount`（**store 成员，非模块导出**：
   `const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()`，
   写 `import { fmtAmount } from '@/stores/displayPrefs'` 会让整页崩）。
4. 工具栏沿用 `el-segmented`（表格视图 / 在线编辑）+ `el-dropdown「导入导出▾」`。
5. 编制说明（源模板红字方法论）嵌在表格上方作上下文展示（琥珀色左边线 + 浅黄背景）。
6. 审计说明/结论区用 `el-card shadow="never"` 包裹；AI 辅助按钮在 section 标题行右侧。

## 后端改动清单

| 文件 | 改动 |
|---|---|
| `app/services/auto_data_resolvers/_d4_revenue.py` | 追加 4 个 resolver（`d4_25_dealer_sales` / `d4_26_overseas_sales` / `d4_27_related_party_sales` / `d4_28_customer_balances`） |
| `app/routers/wp_render_strategies/_d4_import_export.py` | 无端点改动；仅由守卫锁定 `_SHEET_HEADERS` 与列规格一致 |

**无 DB 迁移**（`V146` 之后不新增）。

## 守卫设计（Requirement 9）

### 三向列结构守卫（Property 35）

`backend/tests/test_ipo_checklist_column_contract.py`：openpyxl 直读源模板 → 与后端
`_SHEET_HEADERS` → 与前端列规格（读 TS 源码的声明区）三方逐列比对。
读 TS 源码前必 `stripComments()`（防注释里的 `//` 字符串骗到花括号配对）。

### 渲染层守卫（Property 24/32）

两级表头**不能只断言声明里有 `group`** —— 必须落到模板形态判据（遍历 + 外层门控 + 内层嵌套三要素，
缺一即红），否则「声明对齐而 DOM 从未渲染」的死代码会假绿（这是渲染层死代码的结构性不可见）。

### 变异检验（Property 36）

至少 15 个锚点，每锚点一处最小改动（改一字 / 删一处引用 / 把失败吞成成功），必须全部 RED。
四态判定（RED / GREEN / ANCHOR-MISS / WRONG-TEST），只看退出码不算数。
锚点分布：列规格 3（改 label / 删二级列 group / 改列顺序）、投影 4（改 checkbox 映射 / 改空行跳过 /
改 flush 顺序 / 改冲突裁决为静默覆盖）、公式 4（删 resolver 引用 / 改 depends_on / 改 source_ref /
把 fail-open 吞掉）、导入导出 2（改 item_id / 删 reload）、渲染 2（删分组嵌套 / 改跨列数）。

### fail-open 反向自检（Property 37）

投影失败分支的守卫必须「故意写错必失败」：把 `catch` 里的 `syncState = {ok:false}` 改成 `{ok:true}`
必须打红；否则守卫只查「字符串存在」= 假绿第二源。

### 连库范式

resolver 守卫若连库：一次 `asyncio.run` 取全部快照 + `create_async_engine(url, poolclass=NullPool)`
专用引擎 + 同 loop 内 `dispose()`，**禁借 `async_session` 共享池**（第二个起会
`NoneType has no attribute send`）。

## 不做与已知风险

- **不接附注同步**：`no_projection_contract` 判定不变，本 spec 不改变 reachability 记录。
- **不做 trial_balance 回写**：四张表是检查表不是审定表。
- **D4-27 源模板示例行不作默认种子**：陈XX / 李YY 只作展示参考，写入会污染新项目（Property 30）。
- **`tmp_*`/`_wip_*` 诊断产物不入 git**：会话结束前清理，`.gitignore` 已收前缀。
- **并发会话热点文件**：`GtD4OperatingRevenue.vue` / `_d4_import_export.py` /
  `useD4ImportExport.ts` 可能被其他会话编辑；本 spec 的改动限于四个 IPO 组件 + 三个新模块 +
  一个 resolver 文件追加，提交前 `git status` 只 stage 本 spec 文件。


## Cross-Spec Governance Constraints

- 双向回写统一消费平台既有 `ContentMutationService` + `useWorkpaperSyncBridge`、durable callback、三方合并及 contract-bundle；禁止自建同步 composable。公式统一 F-SHELL v2 mutation，后端权威执行，前端仅预览。

公式唯一入口为 F-SHELL v2 mutation。一个 effective definition 同时投影 OO/HTML；formula mask 仅保护普通值写入，授权公式编辑仍走统一解析、权限、CAS、审计链路。定义允许编辑 `expression`/`refs`/`params`，不得把 checklist remark 当 override，不得在前后端各维护默认值，也不得把纯函数当可编辑声明。预设升级不覆盖 custom，删除与恢复默认分开，scope 固定为 `wp/sheet/row/field`，声明单位；空/除零/error 不写 0，未知函数显式 blocked。

A13 推送独立于双向同步：人工认定金额方向后才可推送；定性风险不得直接以 amount=0 进入错报汇总；差异不得 abs 化，抽凭金额不得直接等同错报。事件需 durable ack、幂等及批准 contract bundle。源模板必须经实际 finder/index 核定；两组模板身份未核定前为 blocked。验收逐张覆盖 HTML→OO→HTML、重新打开后的公式编辑、导出及项目隔离，不能用 D4-35 代表四表。
