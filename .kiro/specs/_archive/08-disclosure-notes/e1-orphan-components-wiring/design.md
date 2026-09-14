# Design: E1 孤儿组件接线与配套收口

## Overview

本 spec 的主体是**接线**，不是重写。6 个 sheet 组件与 2 个 OCR 弹窗都已按源模板写好，
缺的是宿主 `GtE1MonetaryFund.vue` 的一行分发（以及 OCR 弹窗的父级调用与后端端点）。

设计上要守住三条底线：

1. **数据零丢失** —— 5 个 IPO composable 已内建 legacy 键回退，本 spec 只需**验证并守卫**
   这个行为，不新造迁移脚本（写脚本反而会与内建回退打架）。
2. **不扩大战场** —— 只收口与接线同一批文件强相关的欠账（金额控件 / AI / 门控 / 预设）；
   E1 其余 11 个文件的 `:formatter` 存量继续留在 `E1_LEGACY_FORMATTER_BUDGET` 里冻结。
3. **防止再发生** —— 新增平台级孤儿组件守卫。这是本 spec 唯一的平台级产出，
   收益覆盖全部循环（E1 一次攒 8 个说明没有任何机制拦它）。

## Architecture

```
GtE1MonetaryFund.vue（宿主，唯一改动点）
  currentSheet: computed ← props.sheetName 归一（E26A → E1A → E1-\d+ → 附注）
  │
  ├─ E1-18 → E1TabCreditReport（保留，query 模式）
  ├─ E1-19 → E1TabCreditCheck        ★ 新接（原误指 CreditReport）
  ├─ E1-26 → E1TabCashTxnAnalysis    ★ 新接
  ├─ E1-27 → E1TabIpoSpecial（保留：无专属组件）
  ├─ E1-28 → E1TabIpoSpecial（保留：无专属组件）
  ├─ E1-29 → E1TabBankAccountAnalysis ★ 新接
  ├─ E1-30 → E1TabDepositInterestDaily ★ 新接
  ├─ E1-31 → E1TabBankFlowReconcile   ★ 新接
  └─ E1-32 → E1TabKeyPersonFlow       ★ 新接

ipoSheetCode 判定收窄：/^E1-(27|28)$/（原 /^E1-(2[6-9]|3[0-2])$/）

E1TabCutoffTest  ──uses──> E1CutoffOcrConfirmDialog     ★ 新接
E1TabLargeCheck  ──uses──> E1LargeCheckOcrConfirmDialog ★ 新接
   └── POST /api/workpapers/{wp_id}/e1/cutoff-ocr        ★ 新建
   └── POST /api/workpapers/{wp_id}/e1/large-check-ocr   ★ 新建
```

**持久化键的两套体系（接线后的稳定态）**

```
读：pack 键（新） ?? legacy 键（旧） ?? 空
写：只写 pack 键
共享：E1-ipo-applicable（两套组件同一个键）
```

| sheet | pack 键 | legacy 键 |
|---|---|---|
| E1-26 | `E1-cash-txn-pack` / `-audit-note` / `-audit-conclusion` | `E1-ipo-E1-26-rows` / `E1-ipo-audit-note-E1-26` / `E1-ipo-audit-conclusion-E1-26` |
| E1-29 | `E1-bank-analysis-pack` … | `E1-ipo-E1-29-rows` … |
| E1-30 | `E1-deposit-daily-pack` … | `E1-ipo-E1-30-rows` … |
| E1-31 | `E1-bank-flow-pack` … | `E1-ipo-E1-31-rows` … |
| E1-32 | `E1-keyperson-flow-pack` … | `E1-ipo-E1-32-rows` … |
| E1-19 | `E1-credit-check-pack` / `E1-credit-audit-note-check` / `E1-credit-audit-conclusion-check` | `E1-credit-check-rows`（`E1TabCreditReport` 的 check 模式写的键） |

**跨 sheet 联动（接线后才活起来）**

- `E1-30` ← `E1-15` 利息收入月度分析（`buildGroupsFromE15Accounts` / `E15SyncMode` / `E15SyncPreview`
  / `mapDepositTypeFromE15`，读 `E1-interest-monthly-rows` + `-summary`）
- `E1-32` ← `E1-31` 银行流水池（读 `E1-bank-flow-pack`，`collectE31SuspectCandidates`
  从流水里筛董监高可疑往来）

这两条联动是接线的**额外收益**：现在通用表下它们完全不可达。

## Components and Interfaces

### 1) 宿主分发（`GtE1MonetaryFund.vue`）

```ts
// 新增 6 个 defineAsyncComponent + 6 个 v-else-if 分支
const E1TabCreditCheck = defineAsyncComponent(() => import('./e1/E1TabCreditCheck.vue'))
// … 其余 5 个同款

// ipoSheetCode 收窄为「无专属组件的两张」
const ipoSheetCode = computed<string | null>(() => {
  const sheet = currentSheet.value
  return /^E1-(27|28)$/.test(sheet) ? sheet : null
})
```

传参与既有分支**逐字相同**（6 个组件的 props 签名已实证一致）：

```
:wp-id :project-id :all-responses :save-immediate :debounced-save :is-readonly
:sheet-name（专属组件用它做 sheetCode 兜底与标题）
:bs-date（E1TabCreditCheck 需要；IPO 五个也接受）
```

### 2) OCR 链路（两条）

弹窗是**纯展示组件**（props = `modelValue` / `fields` / `confidence` / `ocrPreview`
/ `fileName`，零网络调用），故上传与调用在父 Tab：

```ts
// E1TabCutoffTest / E1TabLargeCheck 内
async function onOcrUpload(file: File, side?: 'debit' | 'credit') {
  const form = new FormData()
  form.append('file', file)
  if (side) form.append('side', side)
  const res = await http.post(`/api/workpapers/${props.wpId}/e1/cutoff-ocr`, form)
  const data = res?.data ?? res
  ocrFields.value = data?.fields ?? {}
  ocrConfidence.value = data?.confidence
  ocrDialogVisible.value = true      // 用户确认后才写行
}
```

后端两个新策略文件，形态镜像既有 4 个：

```
backend/app/routers/wp_render_strategies/_e1_cutoff_ocr.py
  POST /api/workpapers/{wp_id}/e1/cutoff-ocr        → { fields, confidence, preview, file_name }
backend/app/routers/wp_render_strategies/_e1_large_check_ocr.py
  POST /api/workpapers/{wp_id}/e1/large-check-ocr   → 同上（多一个 side 入参）
```

字段契约以弹窗里已定义的 `CutoffOcrFields` / `LargeCheckOcrFields` 为**唯一真源**
（它们现在定义在弹窗 SFC 内 → 抽到 composable 供前后端契约测试共同读取）。

### 3) 披露门控（`E1TabDisclosure.vue`）

```ts
/** 变体适用性：准则列表里没有本变体的前缀 → 不适用（空数组 fail-open 放行） */
const variantApplicable = computed<boolean>(() => {
  const list = applicableStandards.value
  if (!list.length) return true                     // 解析不出 → 放行
  const prefix = variant.value === 'listed' ? 'listed' : 'soe'
  return list.some((s) => String(s).toLowerCase().startsWith(prefix))
})
```

不适用时整页替换为提示卡（不渲染录入区），且三个同步入口
（手动按钮 / 自动同步 watch / 外币段 / 受限资产段）全部前置 return。

### 4) 平台级孤儿组件守卫

`src/components/workpaper/__tests__/cycleTabComponentWiring.spec.ts`

```ts
interface WiringNode { file: string; consumers: string[] }

/** 可达性 = 从「非 Tab 宿主」出发的传递闭包 */
function reachable(nodes: Map<string, WiringNode>): Set<string>
```

判定规则：

- 扫描范围：`components/workpaper/*/` 下的 `*Tab*.vue`（各循环 Tab 组件）
- 消费方证据：`<ComponentName` 出现在模板 或 `import('./x/ComponentName.vue')`
- **排除** `components.d.ts`（unplugin 自动注册）与 `__tests__/**`
- **传递性**：消费方本身不可达 → 被消费者同样不可达（`E1IpoSheetChrome` 曾如此）
- allowlist `ORPHAN_ALLOWLIST: Record<string, string>`，每条理由 ≥20 字，
  已接线的必须移出

## Data Models

### `CutoffOcrFields`（从弹窗 SFC 抽出到 `composables/e1OcrFields.ts`）

```ts
export interface CutoffOcrFields {
  voucherNo?: string
  voucherDate?: string
  summary?: string
  amount?: number
  counterparty?: string
  bankAccount?: string
}

export interface LargeCheckOcrFields {
  voucherNo?: string
  voucherDate?: string
  summary?: string
  amount?: number
  counterparty?: string
  approver?: string
}

export interface E1OcrResponse<F> {
  fields: Partial<F>
  confidence?: number
  preview?: string
  file_name?: string
}
```

（字段以弹窗现有 `fields` 消费点为准逐一对齐，本节在 Task 1 读源码后按实际补全，
**不得凭空增删字段** —— 弹窗是已写好的真源。）

### 宿主分发表（守卫用的声明式真源）

```ts
/** sheetCode → 期望组件名。守卫读宿主源码比对，防止再出现「E1-19 指错组件」 */
export const E1_SHEET_COMPONENT: Record<string, string> = {
  'E1-18': 'E1TabCreditReport',
  'E1-19': 'E1TabCreditCheck',
  'E1-26': 'E1TabCashTxnAnalysis',
  'E1-27': 'E1TabIpoSpecial',
  'E1-28': 'E1TabIpoSpecial',
  'E1-29': 'E1TabBankAccountAnalysis',
  'E1-30': 'E1TabDepositInterestDaily',
  'E1-31': 'E1TabBankFlowReconcile',
  'E1-32': 'E1TabKeyPersonFlow',
}
```

## Correctness Properties

### Property 1: 分发表与宿主源码一致

`E1_SHEET_COMPONENT` 的每一项 SHALL 能在宿主源码里找到对应的
`currentSheet === 'E1-X'` → `<期望组件` 分支；反向自检：把 `E1-19` 改回
`E1TabCreditReport` 则本属性必红。

**Validates: Requirements 1.1, 1.2, 1.3**

### Property 2: 宿主传参全部是合法 prop

宿主传给每个专属组件的 kebab-case 属性名（排除 `v-*` / `@` / `key` / `ref` /
`class` / `style`）SHALL 全部存在于该组件 `defineProps` 的键集合；
且该组件的**必填** prop SHALL 全部被传入。

**Validates: Requirements 1.4, 1.5**

### Property 3: 无传递性死代码

接线完成后，`E1IpoSheetChrome` 的消费方集合 SHALL 至少包含一个可达组件。

**Validates: Requirements 1.6, 8.4**

### Property 4: legacy 键回退优先级

对每个 IPO composable：`pack 键有值` → 用 pack；`pack 空 + legacy 有值` → 用 legacy；
`两者皆空` → 空骨架。三种情形 SHALL 各有一条用例；
反向自检：删掉 legacy 回退分支则「pack 空 + legacy 有值」用例必红。

**Validates: Requirements 2.1, 2.2, 2.3**

### Property 5: 写入只落新键

在新组件里编辑后产生的 `saveImmediate` / `debouncedSave` 载荷 item_id 集合
SHALL 不含任何 `E1-ipo-E1-2X-*` legacy 键。

**Validates: Requirements 2.4**

### Property 6: 启用开关跨组件共享

`E1-ipo-applicable` SHALL 是两套组件唯一的启用态键（专属 composable 与
`useE1IpoSpecial` 导出的常量值逐字相同）。

**Validates: Requirements 2.5**

### Property 7: OCR 用户确认值优先

弹窗确认后写入行的值 SHALL 等于用户在弹窗里最终编辑的值，
而非 OCR 返回的原值；OCR 缺字段时 SHALL 保持该格原值（不写 0、不写 undefined）。

**Validates: Requirements 3.3, 3.4**

### Property 8: OCR 失败不阻断

OCR 端点返回非 2xx 或抛异常时，SHALL 提示用户且底稿其余编辑能力不受影响
（无 `throw` 逃逸到宿主、无整页崩溃）。

**Validates: Requirements 3.5**

### Property 9: OCR 端点形态与既有一致

两个新端点的路由前缀、请求形态（`multipart/form-data` + `file`）与响应字段
SHALL 与 `_e1_statement_ocr.py` 逐项对齐。

**Validates: Requirements 3.6**

### Property 10: 金额控件三态

接线文件内：可编辑金额格 SHALL 用 `WpAmountInput`；
`el-input-number :formatter` 计数 SHALL 为 0；
反向边界（利率/汇率/比例/张数/年度）SHALL NOT 出现 `WpAmountInput`。

**Validates: Requirements 4.1, 4.2**

### Property 11: 预算表只许变短

`E1_LEGACY_FORMATTER_BUDGET` 中被本 spec 接线的文件 SHALL 已移出，
且剩余条目的计数 SHALL 不大于改动前。

**Validates: Requirements 4.3**

### Property 12: AI 四处登记齐备

每个新增 AI section SHALL 同时出现在：前端 section 联合类型、Tab 的 `AI_TARGETS`、
后端 `_SUPPORTED_SECTIONS`、后端 `_SECTION_PROMPTS`；缺一即红。
每条 prompt SHALL ≥20 字且含「不得虚构」。

**Validates: Requirements 5.1, 5.3**

### Property 13: AI 请求体形态

AI 调用的 `context` SHALL 是对象（非字符串），且每个值 SHALL 为字符串
（传字符串会 422 且被 catch 静默吞，四层验证查不出）。

**Validates: Requirements 5.2**

### Property 14: 门控三态 + fail-open

准则含本变体 → 渲染录入区；不含 → 渲染「不适用」且三个同步入口全部不写入；
准则为空数组 → **放行**（fail-open）。

**Validates: Requirements 6.1, 6.2, 6.3, 6.4**

### Property 15: 门控与服务端同口径

前端门控判定 SHALL 只依据 entity 维度（`listed*` / `soe*` 前缀），
scope 差异（`standalone` vs `consolidated`）SHALL NOT 触发不适用。

**Validates: Requirements 6.5**

### Property 16: 预设科目属本循环

新增预设条目引用的科目码 SHALL ∈ `BS-002` 解析出的科目集合（`1001`/`1002`/`1012`），
或显式为 `PLACEHOLDER`；`sheet` 字段 SHALL 逐字命中源 xlsx tab 名。

**Validates: Requirements 7.1, 7.3, 7.4**

### Property 17: 明细表不反引审定表

新增预设块中，明细类 sheet SHALL NOT 出现 `WP('E1','货币资金审定表E1-1',…)`。

**Validates: Requirements 7.5**

### Property 18: 孤儿守卫不空转

守卫 SHALL 含反向自检：构造一个替身「无消费方的 Tab 组件」必被识别为孤儿；
且 `ORPHAN_ALLOWLIST` 每条理由 ≥20 字、已接线条目必须移出。

**Validates: Requirements 8.3, 8.5, 8.6**

### Property 19: 守卫排除自动注册与测试

`components.d.ts` 与 `__tests__/**` 中的引用 SHALL NOT 被计为消费方
（否则本 spec 修的 8 个孤儿在守卫下会全部「通过」）。

**Validates: Requirements 8.2**

## Error Handling

- **OCR 端点不可用**：前端 `catch` → `ElMessage.warning` + 保留手工录入；
  绝不 `throw` 到宿主（宿主无 error boundary 会整页白）
- **legacy 键 JSON 损坏**：composable 已有 `JSON.parse` try/catch + 空骨架回退，
  本 spec 只补用例覆盖，不改行为
- **门控误判**：准则解析为空时一律放行（宁可多渲染也不误锁用户）
- **分发表漂移**：Property 1 是源码级比对，改宿主忘改表（或反之）立刻红

## Testing Strategy

| 层 | 文件 | 覆盖 |
|---|---|---|
| 宿主接线 | `__tests__/e1SheetDispatch.spec.ts` | Property 1/2/3 |
| legacy 迁移 | `composables/__tests__/e1IpoLegacyMigration.spec.ts` | Property 4/5/6 |
| OCR 链路 | `composables/__tests__/e1OcrWiring.spec.ts` + 后端 `test_e1_ocr_endpoints.py` | Property 7/8/9 |
| 金额控件 | 扩 `e1AmountControlIronLaw.spec.ts` | Property 10/11 |
| AI | `__tests__/e1AiWiring.spec.ts` + 后端 `test_e1_ai_sections.py` | Property 12/13 |
| 门控 | `composables/__tests__/e1DisclosureGating.spec.ts` | Property 14/15 |
| 预设 | 后端 `test_e1_formula_presets.py` | Property 16/17 |
| 平台守卫 | `__tests__/cycleTabComponentWiring.spec.ts` | Property 18/19 |

守卫读源码前一律 `stripComments()` + 反向自检（踩坑说明里会写反例，
不剥注释会把说明文字数成真实用法）。
