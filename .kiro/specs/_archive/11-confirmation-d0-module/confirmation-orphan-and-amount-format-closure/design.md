# Design: 函证域孤儿收口与替代程序金额格式

## Overview

四条改动彼此独立，可分波交付。共同设计原则：**共享文件只做加法式最小 hunk + 守卫双向锁死**。

**关键实证（改动前，逐条可复核）**

| # | 事实 | 证据 |
|---|---|---|
| 1 | `CrossWorkpaperNav.vue` 全仓零渲染宿主 | 扫 `src/**` 除 `components.d.ts`、自身、两个守卫外，无 `.vue` 出现 `<CrossWorkpaperNav>` / `<cross-workpaper-nav>` |
| 2 | 平台已有 `navigate-sheet` 约定且 `GtWpRenderer` 已接 | `GtWpRenderer.vue:186` `@navigate-sheet="onChildNavigateSheet"` 挂在 `<component :is>` 上；`onChildNavigateSheet` 用 `resolveSheetNameByDeepLink` 三级解析，未命中给 `ElMessage.info` |
| 3 | 六枢纽 `sheetName` 由 code 派生（== wpCode）→ `isSameWorkbookNavTarget` 恒 false | `cycleConfirmationMeta.isSameWorkbookNavTarget` 判据 `!!sheetName && sheetName !== wpCode` |
| 4 | 但六枢纽也是单 wp_code 多 sheet 工作簿，按 wp_code 跳会落到 render 出 `html_data=null` 的遗留单 sheet 记录 | memory 已登记「单 sheet 遗留 wp_code render 出 null」 |
| 5 | `resolveSheetNameByDeepLink` 第 3 级是**归一后缀/包含**匹配 | 传 `H0-1` 能命中 `函证结果汇总表H0-1` |
| 6 | `CheckBlock.vue` 是七枢纽共享列渲染器；可编辑 number 用 `<el-input type="number" v-model.number>` | `alternativeD05/CheckBlock.vue` L81~L92 |
| 7 | `type="number"` 的 HTML input 拒绝逗号 → 千分符结构上不可能出现 | 浏览器实测输 `1234567.5` 显示 `1234567.5` |
| 8 | 只读态 `formatNumber` = `prefs.fmt` = `fmtAmount`（**带金额单位换算**）→ 数量列也被按金额格式化 | `stores/displayPrefs.fmt` 非 `rawUnit` 分支走 `fmtAmountUnit(v, amountUnit, decimals, showZero)` |
| 9 | 9 个区块配置共 125 个 `type:'number'` 列：76 金额 / 17 非金额 / 32 个 `seq` | 勘查脚本按 label 归类 + 逐条人工复核 |
| 10 | `g0DiffSourceManifest.ts` 已声明逐列 `kind`（含 `amount`/`number`/`ratio`）但零生产消费方 | 只有自身守卫 import |
| 11 | `CYCLE_IMPORT_EXPORT.g0.sheets` 含不存在的 `G0-3S` | `wp_index` 实测无 G0-3S；G0 spec 已把 `diffSecuritiesCode` 从 `'G0-3S'` 换成真实 tab 名 |
| 12 | 同族孤儿包装 3 个（H0/K0/L0 ImportExport）不在本 spec 范围 | `GtConfirmationAlternativeK06.vue` / `AlternativeL05.vue` 直接用共享 `useWorkpaperImportExport` |

## Architecture

```
Wave 1  G0 孤儿收口（G0 独占目录 + 一个共享 registry 常量）
        删 3 个 composable · 移 1 个 spec 文件 · 接线 manifest · 修 registry sheet 值

Wave 2  跨表导航接宿主（共享 2 文件）
        CrossWorkpaperNav（放开 exists 门 + 斜杠主码）→ GtConfirmationSummary 挂载
                                                      → GtWpRenderer 既有 navigate-sheet

Wave 3  金额格式（共享 2 文件 + 9 配置）
        BlockColumnDef.render?='amount'  →  CheckBlock 三处分支（编辑/只读/合计）
                                        →  76 列标注 + 17 列非金额登记
                                        →  G0-6 余额卡片 6 输入

Wave 4  守卫 + 回归 + 实测残留复核
        渲染宿主存在性守卫（函证域清零）· composable 孤儿基线（只许缩短）
```

**波次依赖**：Wave 1 与 Wave 3 都改 G0-6 相关文件（`blockColumnConfigsG06.ts` / `GtConfirmationAlternativeG06.vue`）→ 串行。Wave 2 独立。Wave 4 依赖 1~3。

## Components and Interfaces

### `CrossWorkpaperNav.vue`（共享，改 2 处）

```ts
// 1) 点击不再被 exists 门挡住；exists 只驱动视觉
function handleNavigate(item: NavItem) {
  if (item.wpCode === props.currentWpCode) return   // 当前页不跳
  emit('navigate-sheet', locatorOf(item))
}

// 2) 定位值：同工作簿用真实 tab 名；否则用 wpCode 的主码（去掉 `X0-5/X0-6` 的斜杠）
function locatorOf(item: NavItem): string {
  if (item.sameWorkbook && item.sheetName) return item.sheetName
  return item.wpCode.split('/')[0]
}
```

`navigate` 事件保留在 `defineEmits` 里（外部若已监听不破坏），但内部不再触发 —— 单一出口降低宿主接线成本。

### `GtConfirmationSummary.vue`（共享，加 1 个渲染块）

挂在列表视图 `ConfirmationDetail` 之后：

```vue
<CrossWorkpaperNav
  :confirm-index="currentRow?.confirm_index || ''"
  :wp-code="props.wpCode || ''"
  :current-wp-code="summaryWpCode"
  @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
/>
```

- `summaryWpCode` = `getCycleConfirmationMeta(props.wpCode).summaryCode`（当前页高亮）
- 组件已有 `emit('navigate-sheet')`？**没有** → 需在 `defineEmits` 里新增该事件（加法式）
- 不传 `existsMap`（当前无廉价数据源）→ 全部中性可点击；语义登记在 Notes

### `BlockColumnDef`（共享类型，加 1 个可选字段）

```ts
export interface BlockColumnDef {
  // ...既有字段不动
  /** 渲染语义：'amount' = 金额（千分符 + 平台金额格式）；缺省 = 普通数值，不做金额单位换算 */
  render?: 'amount'
}
```

### `CheckBlock.vue`（共享，改 3 处分支）

```
编辑态 number  →  render==='amount' ? <WpAmountInput> : <el-input type="number">
只读态 number  →  render==='amount' ? prefs.fmt(v)   : formatPlainNumber(v)
合计行         →  按 sumField 所属列的 render 选择同一对函数
```

`formatPlainNumber(v)` = `Number(v).toLocaleString('zh-CN')`（无强制小数位、无单位换算）。

### `g0DiffSourceManifest.ts` 接线

新增派生工具（纯函数，供两张差异表消费）：

```ts
export function diffColumnKind(
  table: 'securities' | 'nonSecurities',
  field: string,
): G0DiffColumnSpec['kind'] | undefined
```

两张差异表的**只读派生格**改为按 kind 格式化：`amount` → `prefs.fmt`，`number`/`ratio` → 原样/百分点。可编辑格保持 `el-input-number`（存量替换属另一 spec）。

## Data Models

### 非金额列登记表（单一真源，Wave 3 新建）

`confirmation/alternativeD05/blockColumnAmountRegistry.ts`

```ts
export interface NonAmountNumberCol {
  /** 配置文件名（不含路径） */
  file: string
  field: string
  label: string
  /** 为什么不是金额 —— 必填，≥8 字 */
  reason: string
}
export const NON_AMOUNT_NUMBER_COLUMNS: readonly NonAmountNumberCol[]
```

17 条实测明细：`delivery_qty`/`product_qty`/`transport_qty`（D0-5）· `outbound_qty`/`transport_qty`×2/`product_qty`（D0-6）· `inbound_qty`×2（F0-5）· `inbound_qty`×2（F0-6）· `asset_qty`/`recv_qty`（H0-5）· `sell_qty`/`trade_price`/`holding_qty`/`dividend_per_share`（G0-6）。

### 渲染宿主存在性基线（Wave 4 新建）

`confirmation/__tests__/orphanHostBaseline.ts`

```ts
/** 函证域已知无渲染宿主的组件（目标：空数组）。每条必须带理由与归属 spec。 */
export const KNOWN_ORPHAN_COMPONENTS: readonly { path: string; reason: string; owner: string }[]
/** 已知无消费方的 .ts 模块（只许缩短，新增即打红） */
export const KNOWN_ORPHAN_MODULES: readonly { path: string; reason: string; owner: string }[]
```

## Error Handling

| 场景 | 处置 | 理由 |
|---|---|---|
| 导航目标 sheet 在当前工作簿不存在 | `GtWpRenderer.onChildNavigateSheet` 已有 `ElMessage.info('未找到 sheet「X」')` | 由渲染器兜底，组件侧不重复判断（它拿不到 sheet 列表） |
| 点击当前页 chip | 直接 return，不 emit | 避免无意义切页与闪烁 |
| `wpCode` 为空/未知循环 | `getCycleConfirmationMeta` 回退默认 meta，导航项照常生成 | 与既有行为一致，不新增分支 |
| `WpAmountInput` 收到非法输入 | 组件自身回退不写 NaN（既有能力） | 复用平台既有约定，本 spec 不重造 |
| 非金额 number 列值为 `null`/空 | `formatPlainNumber` 返回空串（不返 `—`） | 数量为空与金额为空语义不同；金额的 `—` 由 `prefs.fmt` 的 `showZero` 偏好统一决定 |
| 区块配置新增 number 列但未表态 | 守卫 Property 9 打红 | 强制作者显式声明金额语义，避免默认值静默错 |
| manifest label 与差异表模板漂移 | 守卫 Property 7 打红并列出差集 | 双向锁死，改一侧另一侧必红 |

**fail-closed 边界**：本 spec 的守卫一律「解析不出内容即打红」（先断言抽取结果非空），不允许因正则失效而静默通过。

## Testing Strategy

| 层 | 内容 | 文件 |
|---|---|---|
| 导航接线（前端，源码 + 挂载） | Property 1/2/3 | `confirmation/__tests__/crossWorkpaperNavWiring.spec.ts` |
| 渲染宿主存在性（前端，扫全仓） | Property 4/5 | `confirmation/__tests__/orphanHostCoverage.spec.ts` |
| G0 孤儿收口（前端，文件存在性 + manifest 消费） | Property 6/7/8 | `g0-confirmation/__tests__/g0OrphanClosure.spec.ts` |
| 金额列语义（前端，扫 9 配置双向锁死） | Property 9/10/11 | `confirmation/__tests__/blockColumnAmountRender.spec.ts` |
| 七枢纽零回归 | Property 12 | 复用既有 `crossWorkpaperNav.spec.ts` 的 `SIX_HUB_BASELINE` |
| 实测残留（只读 DB 查询，人工执行） | Property 13 | tasks.md 记录结论 |

**守卫铁律**：读源码断言先 `stripComments()` 且 `stripComments` 自身用内联 fixture 反向自检；截函数体用花括号配对；每条结构断言配反向自检；断言前先确认抽取结果非空。

**实测（浏览器）**：G0-1 选中一行 → 导航条出现且展示修正后的 G0-4/G0-5/G0-8 → 点击切页成功；G0-6 借方发生额「金额」列输 `1234567.5` → 显示 `1,234,567.50`，同表「数量」列输 `1200` → 显示 `1200` 不带小数与单位换算。

## Correctness Properties

### Property 1: 导航条有渲染宿主且 prop 名合法

源码级断言 `GtConfirmationSummary.vue` 模板出现 `<CrossWorkpaperNav`；从 `CrossWorkpaperNav.vue` 的 `defineProps` 动态抽合法 prop 名（转 kebab-case）比对调用点属性，排除 `v-*`/`@`/`key`/`ref`/`class`/`style`；断言必填 `confirm-index` 已传。反向自检：对内联 fixture 里的 `:bogus-prop` 断言判为非法。

**Validates: Requirements 1.1, 1.6, 1.7**

### Property 2: 点击不再被 exists 门挡住，且定位值取主码

对 `locatorOf` 纯函数断言：同工作簿项返回 `sheetName`；`wpCode='D0-5/D0-6'` 且 `sheetName=null` 时返回 `'D0-5'`；`sameWorkbook=false` 时返回 `wpCode`。源码级断言 `handleNavigate` 体内不含 `!item.exists` 早退。反向自检：复现旧实现（含早退）时对 `exists=false` 项判定为不跳转。

**Validates: Requirements 1.3, 1.4, 1.5**

### Property 3: 完整表格视图与未选中行不渲染导航条

源码级断言导航块位于列表视图 `v-if` 分支内且紧随 `ConfirmationDetail`；组件自身 `v-if="confirmIndex"` 仍在。挂载断言：`currentRow=null` 时 DOM 无 `.cross-workpaper-nav`。

**Validates: Requirements 1.2**

### Property 4: 函证域无无宿主组件

扫 `confirmation/**` ∪ `g0-confirmation/**` 全部 `.vue`，对每个组件在全仓（排除 `__tests__`、`components.d.ts`、自身）搜 `<PascalName` 与 `<kebab-name`，或被 `htmlRendererRegistry.ts` 引用；无命中且不在 `KNOWN_ORPHAN_COMPONENTS` 内即打红。断言基线为空数组。

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

### Property 5: 宿主扫描非恒真且模块孤儿基线只许缩短

反向自检：对一个内联的必然不存在的组件名断言判为孤儿。断言 `KNOWN_ORPHAN_MODULES` 每条 `reason` ≥8 字且 `owner` 非空；断言当前实际孤儿模块集合 ⊆ 基线（新增即红）。

**Validates: Requirements 2.5, 2.6**

### Property 6: 三个 G0 孤儿 composable 已删除且无残留引用

断言三个文件不存在；全仓（含 `components.d.ts`）无 `useG0DualMode` / `useG0ImportExport` / `useG0ReviewDialogProvide` 引用；`useG0FormulaEngine.spec.ts` 不在 `composables/` 而在 `composables/__tests__/`。

**Validates: Requirements 3.1, 3.2, 3.3, 3.7**

### Property 7: manifest 有生产消费方且列标签与两张差异表一致

断言 `g0DiffSourceManifest` 被至少一个非测试 `.vue`/`.ts` 引用；两张差异表模板抽出的 `el-table-column label="..."` 集合与 manifest `label` 集合在归一（全/半角括号、空格）后相等，双侧无剩余。反向自检：把 manifest 某 label 改一字则打红（用内联替身集合验证判据）。

**Validates: Requirements 3.4, 3.5, 3.6**

### Property 8: 导入导出 registry 的 G0 sheet 值与后端 API 键集双向锁死

从后端 `_g0_confirmation_import_export.py` 的 `_SHEET_NAME_MAP` 抽键集（读 py 源码），断言 `CYCLE_IMPORT_EXPORT.g0.sheets` 与之**逐字节相等**（当前 `['G0-3S','G0-6']`）。同时断言 `_SHEET_NAME_MAP['G0-3S']` 的值是源模板真实 tab 名（含全角括号），以此把「`G0-3S` 是 API key 而非 wp_code」变成机器可验事实。反向自检：对一个必然不存在的 sheet 值断言不在键集内，且抽出的键集非空（防正则失效空转）。

**为什么不是「删掉 G0-3S」**：立项时按「`wp_index` 实测无 G0-3S」判它为错值，勘查后推翻 —— 它是后端 API 参数名。这条 Property 的价值就是把该结论钉死。

**Validates: Requirements 3.8**

### Property 9: 每个 number 列的金额语义已表态

扫 9 个区块配置文件全部 `type:'number'` 列（排除 `field==='seq'`），断言每列**要么** `render:'amount'`**要么**在 `NON_AMOUNT_NUMBER_COLUMNS` 里；断言两侧数量之和等于总列数、集合无交集；断言非金额登记表恰 17 条且每条 `reason` ≥8 字。反向自检：删掉登记表任一条则该列判为未表态。

**Validates: Requirements 4.6, 4.7, 4.8**

### Property 10: CheckBlock 按 render 分流三处渲染

源码级断言 `CheckBlock.vue`：存在 `render === 'amount'` 判定；金额分支用 `WpAmountInput`；非金额分支仍是 `el-input` + `type="number"`；只读与合计两处都按 render 分流；断言不再出现「无条件对全部 number 列调 `prefs.fmt`」。反向自检：内联 fixture 复现旧无条件写法时判红。

**Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**

### Property 11: G0-6 余额卡片金额输入已换 WpAmountInput

断言 `GtConfirmationAlternativeG06.vue` 出现 `WpAmountInput` 且「余额数据」6 个字段（`opening_balance`/`increase_amount`/`decrease_amount`/`closing_balance`/`investment_income`/`fv_change`）不再与 `type="number"` 同现。反向自检：内联 fixture 复现旧写法时判红。

**Validates: Requirements 4.9, 4.10**

### Property 12: 七枢纽零回归

断言 `buildCrossWorkpaperNavDefs` 对 D0/E0/F0/H0/K0/L0 的输出与 `SIX_HUB_BASELINE` 逐字节相等（复用既有守卫）；断言未标 `render` 的列在 `CheckBlock` 走的是与改动前同一模板分支（源码级：非金额分支的属性集合与旧版一致）。

**Validates: Requirements 6.1, 6.2, 6.3**

### Property 13: 实测残留复原判据

只读查询确认七枢纽函证底稿（`wp_code` 以 `D0/E0/F0/G0/H0/K0/L0` 开头）无含「实测」标记的 `checklist_responses` 与 `parsed_data` 残留；把查询与结论写进 tasks.md。

**Validates: Requirements 5.1, 5.2, 5.3, 5.4**
