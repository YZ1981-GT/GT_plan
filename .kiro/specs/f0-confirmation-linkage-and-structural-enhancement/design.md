# Design Document

## Overview

F0 存货循环函证联动增强与结构化改进。核心设计判断：**复用 E0 `importE0ListsToSummary` 的聚合范式**（声明式取数规格 + per-品种 amountKeys + 自动回流矩阵），不新建后端 render 策略（F0 走 `_CONFIRMATION_COMPONENTS` 空载荷路径），全部联动逻辑放**前端 composable**（与 E0 的 `importE0ListsToSummary.ts` 357 行同款）。

本 spec 不新造机制，全部复用平台既有单一真源：

| 能力 | 复用件 | 首建 spec |
|------|--------|-----------|
| 函证元数据 | `cycleConfirmationMeta.ts` | 平台共享 |
| 跨底稿取数 | `fetchWorkpaperHtmlRows` / render-config `tb_amount` | E0 |
| 汇总聚合声明式 | `importE0ListsToSummary.ts` 的 `E0_LIST_SPEC` 范式 | E0 |
| 差异公式引擎 | `useD1FormulaEngine.ts` 范式（纯函数派生） | D1 |
| B50 推送 | EventBus `fraud-risk:push-to-b50`（七枢纽共享） | 平台 |
| A13 错报推送 | EventBus `a13:push-misstatement` | D1 |
| 金额格式 | `stores/displayPrefs.fmtAmount` | 平台 |
| 替代程序导入导出 | `_f0_import_export.py` | 既有 |
| 邮箱域名检测 | 新建纯函数 `isCorpEmailDomain` | 本 spec |

## Architecture

### 联动数据流

```
F1/F3/F4 审定表                     tb_aux_balance（往来维度）
     │ (tb_amount: 期末审定额)           │ (按供应商归集)
     ├──────────────────┐                │
     ▼                  ▼                ▼
F0-1 下区矩阵        F0-1 上区 grid ← 供应商清单+余额
「账面金额」行          │
     │                  │ (品种列 / 金额列 / 是否回函)
     │                  ├─────────────────────────┐
     │                  ▼                         ▼
     │           矩阵「发函金额」          F0-5/F0-6 供应商带入
     │           矩阵「回函确认金额」       (未回函行 → 替代程序)
     │                  │                         │
     │                  │                         ▼
     │                  │                  F0-5/F0-6 四区块合计
     │                  │                         │
     │                  ▼                         │
     └────────────── 矩阵全量指标 ◄────────────────┘
                        │                 「替代测试确认金额」
                        ▼
                  百分比自动派生
```

### F0-4b 差异检查表计算模型

```
┌─────────────────────────────────────────────────┐
│  A: 被询证方回函金额                              │ ← 录入
│  B: 本公司已增 未确认合计 = Σ(明细行.金额)         │ ← 动态行求和
│  C: 本公司已减 未确认合计 = Σ(明细行.金额)         │ ← 动态行求和
│  D = A + B − C                                   │ ← 实时派生
├─────────────────────────────────────────────────┤
│  E: 本公司账面记录余额                            │ ← 录入
│  F: 对方已增 本方未确认合计 = Σ(明细行.金额)       │ ← 动态行求和
│  G: 对方已付 本方未收合计 = Σ(明细行.金额)         │ ← 动态行求和
│  H = E + F − G                                   │ ← 实时派生
├─────────────────────────────────────────────────┤
│  I = H − D                                       │ ← 差异，非零标红
└─────────────────────────────────────────────────┘
```

### F0-7 可靠性自动推导逻辑

```
结论 = f(身份确认, 邮箱域名, 致电确认, 是否原件):
  IF 身份确认=否 OR 邮箱=私人 → 「不可靠，需进一步确认」(danger)
  ELIF 致电确认=否 AND 是否原件=否 → 「可靠性待验证」(warning)
  ELSE → 「可靠」(success)
```

## Components and Interfaces

### 1. `composables/f0SummaryAggregation.ts`（新建）

**职责**：从 F0-1 上区 grid + F0-5/F0-6 合计行聚合矩阵 7 指标 × 4 品种。

```typescript
interface F0MatrixCell {
  value: number
  isManual: boolean  // 手工修改标记
}

interface F0MatrixRow {
  label: string  // 如「抽取样本的发函金额」
  prepayment: F0MatrixCell    // 预付账款
  notePayable: F0MatrixCell   // 应付票据
  accountPayable: F0MatrixCell // 应付账款
  purchase: F0MatrixCell       // 本期采购
}

export function buildF0SummaryMatrix(input: {
  rows: readonly ConfirmationRow[]
  bookAmounts?: Partial<Record<F0Category, number>>
  manualOverrides?: Record<string, number>
}): F0MatrixCell[][]
```

🔴 **2026-08-03 实测更正（Task 20.1）**：账面金额取值路径**每品种独立声明**，
不能统一假设 `project_context.tb_amount`（后端三个循环键名各不相同）：

```typescript
export interface F0BookAmountSource {
  wpCode: string
  hint: string
  /** F1 = project_context.prepaid_tb_amount / F3 = tb_values['2201'] / F4 = project_context.tb_amount */
  pick: (htmlData: any) => unknown
}
```

且三者下发的都是**叶子聚合口径**（带 `parent_check.diff == 0` 自证），与 `trial_balance` 可能不等
——实证 `2aa00f57`：F3 叶子 15,029,046.64 vs TB 30,058,093.28、F4 叶子 267,308,976.77 vs
TB 534,617,953.54，均正好 2 倍（旧版 recalc 父子双算）。各循环后端 docstring 已声明取叶子口径是
有意为之，此处照用不做换算。

🔴 **2026-08-03 更正（Task 28）**：入参**不含** `altF05Totals`/`altF06Totals`。
源模板 `R36 = SUMIF(E8:E27, E29, Y8:Y27)` 取的是上区「替代后可确认金额」列（`alt_confirmed`），
从不按替代程序底稿合计反推品种归属。替代程序合计另作勾稽：

```typescript
export function checkAltConsistency(input: {
  rows: readonly ConfirmationRow[]
  altF05Totals?: F0AltTotals
  altF06Totals?: F0AltTotals
}): F0AltConsistency   // { gridAltTotal, procedureTotal, diff, level: 'ok'|'mismatch'|'no-data', message }

/** R37 双算风险行（平台对「积极式+未回函」令 U === Y）—— 只提示不改公式 */
export function detectAltOverlapRows(rows: readonly ConfirmationRow[]): ConfirmationRow[]
```

### 2. ~~`composables/f0AltSupplierSeed.ts`~~（已删，Task 25）

🔴 与既有 `coordination/importFromSummary.ts` 的 `importUnrepliedAsCompanies` +
`defaultUnrepliedFilter` 重复且零消费方。唯一有价值的 `matchAuxBalance` 已并入
`importFromSummary.ts`（六循环共享），F0-5 传 `auxAccountCode='1123'` / F0-6 传 `'2202'`。
下方原设计保留作历史记录：

**职责**：从 F0-1 上区 grid 中「未回函」行提取供应商信息，供 F0-5/F0-6 自动带入。

```typescript
interface F0UnrepliedSupplier {
  confirmIndex: string  // 索引号
  supplierName: string  // 被询证单位名称
  account: string       // 账户/交易（品种）
  amount: number        // 发函金额
}

export function extractUnrepliedSuppliers(gridRows: F0GridRow[]): F0UnrepliedSupplier[]
export function seedAltProcedureFromSummary(supplier: F0UnrepliedSupplier): AltSeedPayload
```

### 3. ~~`composables/f0DiffChecklistEngine.ts`~~（已删，Task 24）

🔴 既有 `diffChecklist/composables/useDiffChecklistData.computeFormula` 已完整实现同一套
A~I 公式 + 动态行 CRUD + 重要性判定，新建件是零消费方重复实现。真正有价值的部分
（`?? 0` 挡不住 NaN/±Infinity → 改 `Number.isFinite` 逐行过滤）已合并进既有实现，
PBT 补在 `useDiffChecklistData.pbt.spec.ts`。下方原设计保留作历史记录：

**职责**：F0-4b 差异检查表九段公式实时计算引擎。

```typescript
interface DiffChecklistModel {
  A: number  // 回函金额
  B_details: DetailRow[]  // 本公司已增明细
  C_details: DetailRow[]  // 本公司已减明细
  E: number  // 本公司账面余额
  F_details: DetailRow[]  // 对方已增明细
  G_details: DetailRow[]  // 对方已付明细
}

interface DiffChecklistDerived {
  B: number  // Σ B_details
  C: number  // Σ C_details
  D: number  // A + B − C
  F: number  // Σ F_details
  G: number  // Σ G_details
  H: number  // E + F − G
  I: number  // H − D
  hasDifference: boolean
}

export function deriveDiffChecklist(model: DiffChecklistModel): DiffChecklistDerived
```

### 4. `composables/f0FraudRiskPush.ts`（新建）

**职责**：F0-8 舞弊迹象汇总 + B50 推送载荷构建。

🔴 **不含迹象文字**（Task 27）：19 条文字的平台唯一真源是
`fraudRisk/fraudRiskPresets.ts` 的 `PRESET_FRAUD_ITEMS`（逐字取自源模板 A6:A24；
`D0-8`/`E0-8`/`F0-8`/`H0-7`/`K0-8`/`L0-7` 六表内容 md5 全等）。
原 `F0_FRAUD_INDICATORS` 与之构成双真源且文字互不相同，已删；
`createDefaultIndicators()` 改从预置派生。

```typescript
interface FraudIndicator {
  index: number        // 1~19
  text: string         // 迹象描述
  exists: 'yes' | 'no' | 'na'
  sourceRef?: string   // 索引号
  response?: string    // 应对措施
}

export function buildFraudPushPayload(
  indicators: FraudIndicator[],
  wpCode: string,
): B50PushPayload
```

### 5. `utils/emailDomainCheck.ts`（新建）

**职责**：邮箱域名可靠性判断（F0-7 消费）。

```typescript
const PERSONAL_DOMAINS = ['qq.com', '163.com', '126.com', 'gmail.com', 'hotmail.com', 'outlook.com', 'yahoo.com', 'sina.com', 'sohu.com']

export function isCorpEmailDomain(email: string): 'corp' | 'personal' | 'unknown'
export function extractDomain(email: string): string | null
```

### 6. 前端组件改造清单

| 组件 | 改造内容 |
|------|---------|
| `GtConfirmationSummary.vue` | 注入 `f0SummaryAggregation`（按 `resolveConfirmationCycle` 判是否 F0） |
| `GtConfirmationAlternativeF05.vue` | 顶部加「从F0-1带入供应商」按钮 + 消费 `f0AltSupplierSeed` |
| `GtConfirmationAlternativeF06.vue` | 同上 |
| `GtConfirmationDiffChecklist.vue` | 注入 `f0DiffChecklistEngine`，九段实时派生 + 动态行 |
| `GtConfirmationReliability.vue` | 注入结构化列（下拉/邮箱检测/致电记录）+ 自动推导结论 |
| `GtConfirmationFraudRisk.vue` | 注入三态下拉 + 「推送到B50」按钮 + `f0FraudRiskPush` |

### 7. 后端无新增 render 策略

F0 不在 `RENDERER_DISPATCH`，走 `_CONFIRMATION_COMPONENTS` 空载荷路径。联动全在前端完成（读 render-config / 读 checklist_responses / 写 checklist_responses）。

**唯一后端改动**：`review_dialog._SECTION_PROMPTS` 补 6 条 F0 专属 prompt（F0-1 审计说明 × 4 + F0-4 审计说明 × 1 + F0-7 审计结论 × 1）。

## Data Models

### F0-1 矩阵持久化

存入 `checklist_responses` 的 `F0-1-matrix-{品种}-{指标}` 键，值为 `{value, isManual, lastAutoValue}`。

### F0-4b 差异模型持久化

存入 `checklist_responses` 的 `F0-4b-{supplierIndex}-model` 键，值为完整 `DiffChecklistModel` JSON。

### F0-8 迹象持久化

存入 `checklist_responses` 的 `F0-8-indicators` 键，值为 `FraudIndicator[]` JSON。

## Correctness Properties

### Property 1: 矩阵聚合准确性

**Validates: Requirements 1.1, 1.2, 1.3, 1.4**

矩阵三个金额行逐行对齐源模板 SUMIF 口径：「发函金额」= grid `amount`（F 列）按品种求和；
「回函确认金额」= grid `confirmed_amount`（U 列）按品种求和**且不叠加「相符」过滤**；
「替代测试确认金额」= grid `alt_confirmed`（Y 列）按品种求和。
百分比 = 被除数 / 除数，除数缺失或为 0 时返回 null 渲染 `-`（不返 0，否则「未取到账面数」
与「比例真为 0」不可区分）。PBT 验证：随机 grid 行（品种均匀分布），矩阵行和必等于对应品种全部行之和。
反向自检：旧口径（只取 `match_status='相符'` 行的 `reply_amount`）必须得到不同结果。

🔴 **2026-08-03 更正（Task 28）**：原文写「回函确认 = 相符行 S 列」与「替代金额 = F0-5+F0-6 按品种归属」
两处均与源模板不符，已按 `data_only=False` 直读的公式更正，理由见 requirements R1.2/R1.3。

### Property 2: 供应商带入一致性

**Validates: Requirements 2.1, 2.2, 2.3**

F0-5/F0-6 带入的供应商名称+金额必须在 F0-1 上区 grid 的「未回函」行中存在，且金额一致（容差 0.01）。

### Property 3: 差异公式恒等式

**Validates: Requirements 3.1, 3.2, 3.3**

对任意输入 A/B_details/C_details/E/F_details/G_details，D = A + Σ(B) − Σ(C) 且 H = E + Σ(F) − Σ(G) 且 I = H − D，浮点精度 ≤ 0.01。PBT 验证。

### Property 4: 舞弊推送完整性

**Validates: Requirements 4.3, 4.4**

推送载荷包含所有 `exists='yes'` 的迹象且不包含 `exists='no'|'na'` 的迹象；载荷 `wp_code` 必为 `F0-8`。

### Property 5: 邮箱域名判定准确性

**Validates: Requirements 6.2**

`PERSONAL_DOMAINS` 列表中的域名必判为 `personal`；`.com.cn`/`.cn`/`.com` 非个人域名必判为 `corp`；空/无@/无后缀必判为 `unknown`。PBT 验证。

### Property 6: 手工优先不变式

**Validates: Requirements 1.7, 2.4**

凡 `isManual=true` 的矩阵格，自动聚合值变化时不覆盖该格；供应商带入后手工修改的字段，再次带入时不覆盖。

### Property 7: 动态行求和恒等

**Validates: Requirements 3.4**

B/C/F/G 各段合计 = 该段所有明细行金额列之和（含新增行、删除后重算），空行金额视为 0。
