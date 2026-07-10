# Design Document

## Overview

本设计在**不重写既有抽凭引擎**的前提下，交付两大能力：

- **A. D3-7 预收账款检查表全闭环**：行级附件上传 + OCR 识别 + AI 辅助 + 用户确认 + 回写，并以弹窗方式接入既有抽凭引擎（`GtVoucherSamplingEngine`），抽样结果回填检查表并标注来源。
- **B. 抽凭引擎方法学增强**：在既有 `useSamplingAlgorithms` 纯函数模块与 `useVoucherSampling` 编排 composable 及后端 sampling 路由上做**扩展**，补齐科学样本量推导、MUS 完整方法学（高值必选 + 抽样间隔）、错报推断与总体结论、总体完整性校验、与重要性水平联动、抽样备忘导出、重抽治理与属性抽样（可选）。

核心设计原则：
- **复用优先**：新增能力以纯函数 + 配置字段 + 端点字段扩展形式加入，既有五种抽样方法、覆盖率、CAS 1314 校验、版本 diff/历史/撤销、回填三模式、字段留痕、随机种子全部保留。
- **人工确认为准**：OCR/AI/抽样结论一律"建议 → 人工确认 → 写入"，系统不越权定稿。
- **点选优先**：枚举字段（异常类型、抽样方法、填充模式、结论）用点选控件。
- **跨循环共享单一引擎**：D3-7 与其他循环检查表均以 dialog-mode 接入同一 `GtVoucherSamplingEngine`，方法学增强对所有接入方生效。
- **ref 解包铁律**：D3-7 子 tab 通过 `toRef(props, ...)` 重新包装父级经模板传入的解包值。

## Architecture

### 组件复用与新增映射

| 层 | 既有（复用/扩展） | 新增 |
|----|------------------|------|
| D3-7 视图 | `d3/D3TabVoucherCheck.vue` | 内嵌 `GtVoucherSamplingEngine`(dialog-mode)、📎附件列、AI 按钮 |
| D3-7 逻辑 | `composables/useD3VoucherCheck.ts` | `handleRowOcr`/`OCR_FIELD_MAP`/`mapOcrToVoucherFields`/`fillFromSampling` |
| 抽凭引擎 UI | `voucher-sampling/GtVoucherSamplingEngine.vue` + `SamplingConfigDialog`/`SamplingPreviewDialog`/`SamplingHistoryDrawer`/`SamplingComparePanel` | 参数区(置信度/可容忍/预期错报)、错报推断区、总体校验区、备忘导出、重抽原因 |
| 抽样算法 | `composables/useSamplingAlgorithms.ts`（纯函数） | `computeSampleSize`/`computeMusInterval`/`projectMisstatement`/`computeUpperMisstatementLimit`/`deriveSamplingConclusion`/`reconcilePopulation`/`computeAttributeSampleSize`/`evaluateDeviationRate` |
| 抽样编排 | `composables/useVoucherSampling.ts` | 承接新参数与错报推断状态、重抽原因、备忘导出 |
| 重要性联动 | 重要性/B15 底稿取数 | `loadTolerableMisstatement()` |
| 后端 | `/sampling/voucher-extract`·`/cutoff-fill`·`/voucher-history`·`/voucher-undo`·`/voucher-compare` | 扩展返回 high_value 标记、population_reconcile、resample_reason、seed 展示 |
| OCR/AI/版本链 | `/d4/contract-ocr`、`/ai/generate-text`、`useVersionTrail` | 无需新端点（复用） |

### 数据流（D3-7 抽凭 + 错报评价闭环）

```mermaid
flowchart TD
  A[D3-7 检查表] -->|打开抽凭弹窗 account=2203| B[GtVoucherSamplingEngine dialog]
  B --> C[SamplingConfigDialog 参数: 方法+置信度+可容忍错报+预期错报]
  C -->|computeSampleSize / computeMusInterval| D[triggerSampling POST voucher-extract]
  D -->|items + high_value 标记 + population 合计| E[SamplingPreviewDialog 预览+勾选]
  E -->|reconcilePopulation 总体↔账面| E
  E -->|confirmFill mode=append/replace/merge| F[applyFillMode 回填]
  F -->|@filled samples| A
  A -->|来源=抽凭 标注 + 行级 OCR/AI 补证| G[录入实际错报 actualMisstatement]
  G -->|projectMisstatement → UML| H[deriveSamplingConclusion 接受/扩样]
  H -->|人工确认| A
  F -.版本快照+seed+重抽原因.-> I[useVersionTrail / voucher-history]
```

## Components and Interfaces

### A. D3-7 检查表全闭环

#### A.1 行级附件 + OCR（复用 G4/G6/G10 范式）
`useD3VoucherCheck.ts` 扩展：

```ts
// OCR 字段映射：OCR识别键 → VoucherCheckRow 字段
const OCR_FIELD_MAP: Record<string, keyof VoucherCheckRow> = {
  客户名称: 'customerName', 对方单位: 'customerName',
  日期: 'date', 凭证日期: 'date',
  凭证号: 'voucherNo', 摘要: 'businessContent', 业务内容: 'businessContent',
  金额: 'creditAmount', 贷方金额: 'creditAmount', 借方金额: 'debitAmount',
}
function mapOcrToVoucherFields(fields: Record<string, any>): {
  patch: Partial<VoucherCheckRow>; lowConfidence: string[]
}
async function handleRowOcr(section: 'current'|'postPeriod', rowId: string, file: File): Promise<boolean>
// 流程：上传 → POST /api/workpapers/{wpId}/d4/contract-ocr → mapOcr → ElMessageBox 确认(低置信度标注) → merge 写入行(保留已填值)
```

- 附件列在两区块每行提供 `el-upload`（accept 图片/PDF），`before-upload` 触发 `handleRowOcr` 返回 false 阻止默认上传。
- 只读禁用；文件类型不符拒绝并提示。

#### A.2 AI 辅助
- 检查结论文本区 🤖 按钮 → `useXAiGenerate('voucher-conclusion', ...)` → 展示建议 → 确认写入。AI 不可用时提示、内容不变。

#### A.3 抽凭弹窗联动
```vue
<GtVoucherSamplingEngine
  v-if="showSampling" account-code="2203" :phase="phase"
  :project-id="projectId" :workpaper-id="wpId" :year="year"
  @filled="onSampleFilled" />
```
```ts
function onSampleFilled(payload: { samples: SampledVoucher[]; phase: Phase; fillMode: FillMode; method?: SamplingMethod }) {
  // 映射 samples → VoucherCheckRow(voucherNo/date/amount/summary/counterAccount)，source='抽凭'
  fillFromSampling(payload.samples, payload.fillMode)  // 复用 applyFillMode 语义
}
```
- `VoucherCheckRow` 增字段 `source?: '手工'|'抽凭'`、`actualMisstatement?: number`。

### B. 抽凭引擎方法学增强

#### B.1 数据模型扩展（useSamplingAlgorithms.ts）

```ts
export interface SamplingConfig {
  // ... 既有字段保留 ...
  confidenceLevel?: number          // 置信度 如 0.95（R20）
  tolerableMisstatement?: string    // 可容忍错报（R16 默认取B15，R20必填）
  expectedMisstatement?: string     // 预期错报（R20）
  suggestedSampleSize?: number      // 系统建议样本量（R15 留痕）
  resampleReason?: string           // 重抽原因（R22）
}

export interface SampledVoucher {
  // ... 既有字段保留 ...
  isHighValue?: boolean             // MUS 高值必选项标识（R17）
  actualMisstatement?: string       // 审计师录入的实际错报（R18）
}

export interface MisstatementResult {
  projected: string                 // 推断错报（R18.2）
  knownHighValue: string            // 高值层已知错报
  basicPrecision: string            // 基本抽样风险余量
  incrementalAllowance: string      // 增量准备
  upperLimit: string                // 错报上限 UML（R18.4）
}
export interface SamplingConclusion {
  accepted: boolean
  message: string                   // "总体可接受" / "可能存在重大错报，建议扩大样本/替代程序/提请调整"
}
export interface PopulationReconcile {
  samplingPopulationAmount: string  // 抽样总体金额
  bookAmount: string                // 账面（序时账/明细/审定）
  diff: string
  withinThreshold: boolean
}
```

#### B.2 纯函数签名与算法要点

```ts
// R15 科学样本量（MUS/属性均基于可信赖度系数 Poisson 表）
// 可信赖度系数 R(置信度, 预期错报数)：95%→3.0, 90%→2.3, 均以0预期错报为基准，含 tainting 增量因子表
export function reliabilityFactor(confidenceLevel: number, expectedErrors: number): number
// MUS 抽样间隔 = 可容忍错报 / 可信赖度系数；样本量 = ceil(总体金额 / 间隔)
export function computeMusInterval(tolerable: string, confidenceLevel: number, expected: string): string
export function computeSampleSize(populationAmount: string, tolerable: string, expected: string, confidenceLevel: number): number

// R17 高值层：金额≥间隔者 100% 必选
export function markHighValueItems(vouchers: SampledVoucher[], interval: string): SampledVoucher[]

// R18 错报推断
// MUS：Σ(tainting_i × interval) [tainting=错报/账面, 上限1] + 高值层已知错报之和
// 经典(随机/系统)：比率估计 projected = (Σ样本错报 / Σ样本金额) × 总体金额
export function projectMisstatement(samples: SampledVoucher[], method: SamplingMethod, interval: string, populationAmount: string): MisstatementResult
// UML = projected + basicPrecision + incrementalAllowance（基本准备=R×interval；增量准备按 tainting 排序递增因子）
export function computeUpperMisstatementLimit(r: MisstatementResult): string
// 结论：UML ≤ tolerable → accepted
export function deriveSamplingConclusion(uml: string, tolerable: string): SamplingConclusion

// R19 总体完整性
export function reconcilePopulation(samplingPopAmount: string, bookAmount: string, thresholdPct: number): PopulationReconcile

// R20 参数校验（并入 validateSamplingConfig）：统计法 confidence/tolerable 必填；expected<tolerable

// R23 属性抽样（可选）
export function computeAttributeSampleSize(expectedDevRate: number, tolerableDevRate: number, confidenceLevel: number): number
export function evaluateDeviationRate(sampleSize: number, deviations: number, confidenceLevel: number): { upperDevRate: number; effective: boolean }
```

算法注记：金额一律用 Decimal 字符串运算（沿用既有约定，避免浮点误差）；可信赖度系数与增量准备因子以内置常量表实现（CAS 1314 附录常用泊松因子）。

#### B.3 重要性联动（R16）
```ts
// 从重要性/B15 取实际执行重要性；失败则返回 null 允许手填
async function loadTolerableMisstatement(projectId: string): Promise<string | null>
```
取数来源：优先复用既有重要性模块端点（如 `/api/projects/{pid}/materiality`）；无则手工录入。

## Data Models

见 B.1。既有 `SamplingConfig`/`SampledVoucher`/`CoverageStats`/`ComplianceWarning`/`ExtractionLogEntry` 全部保留，新增字段均为可选（`?`），保证既有五方法与回填/历史向后兼容。

## Backend Endpoint Contracts（扩展，不新增路由）

- `POST /sampling/voucher-extract`（扩展响应）：`items[].high_value: boolean`、`stats.population_amount/population_count`、`stats.book_amount`（用于总体校验，若可得）。
- `POST /sampling/cutoff-fill`（扩展请求）：`extraction_criteria` 增 `confidence_level`/`tolerable_misstatement`/`expected_misstatement`/`suggested_sample_size`/`resample_reason`/`sampling_interval`。
- `GET /sampling/voucher-history`（扩展响应）：回显 `random_seed`、`resample_reason`、`sampling_interval`、`conclusion`。
- 版本快照 `POST /workpapers/{wpId}/versions`：description 增方法学要素（方法/间隔/样本量/seed）。
- 错报推断为**前端纯函数**计算（基于样本 `actualMisstatement`），无需新端点；结论与备忘随 checklist_responses / 版本链持久化。

## Error Handling

- OCR 失败/无可填字段：提示且行字段不变；低置信度字段确认弹窗标注需人工复核。
- AI 不可用：提示"AI 服务暂不可用"，文本不变。
- 抽样参数缺失/不合理（缺可容忍或置信度、expected≥tolerable）：阻止推导并逐项提示。
- 总体校验差异超阈值：黄色告警"总体可能不完整，结论受限"，不阻断但留痕。
- 版本快照 fire-and-forget 失败静默；填充日志失败提示并放弃本次回填（沿用既有）。
- 只读：附件/OCR/AI/抽样回填/行增删编辑全部禁用。

## Correctness Properties

以下不变量作为纯函数属性测试（PBT）的断言基准（hypothesis / fast-check）：

### Property 1: 样本量单调性
固定其他参数，`computeSampleSize` 随可容忍错报增大而不增（样本量↓），随置信度提高而不减（样本量↑）。
**Validates: Requirements 15.1, 15.2**

### Property 2: MUS 间隔一致性
`computeMusInterval = tolerable / reliabilityFactor`，且 `样本量 = ceil(总体金额 / 间隔)`，间隔恒 > 0。
**Validates: Requirements 15.2, 17.1**

### Property 3: 高值全选
`markHighValueItems` 后，所有 `金额 ≥ interval` 的凭证 `isHighValue = true 且 selected = true`；`金额 < interval` 的不被强制选中。
**Validates: Requirements 17.2, 17.3**

### Property 4: 污染率有界
`projectMisstatement` 中每笔 `tainting = clamp(错报/账面, 0, 1)`；`projected ≥ 0`，且样本错报全为 0 时 `projected = 0`。
**Validates: Requirements 18.2, 18.3**

### Property 5: 错报上限下界
`computeUpperMisstatementLimit` 结果 `UML ≥ projected ≥ 0`（抽样风险余量非负）。
**Validates: Requirements 18.4**

### Property 6: 结论边界
`deriveSamplingConclusion` 当 `UML ≤ tolerable` 判定 accepted=true，`UML > tolerable` 判定 accepted=false；边界 `UML == tolerable` 视为可接受。
**Validates: Requirements 18.5, 18.6**

### Property 7: 总体校验对称性
`reconcilePopulation` 的 `diff = |samplingPop − book|`，`withinThreshold = diff ≤ book × thresholdPct`。
**Validates: Requirements 19.2, 19.3**

### Property 8: 填充模式守恒（既有 applyFillMode 回归）
append 结果长度 = 原 + 新；merge 后同 phase 内 voucherNo 唯一；replace 仅替换当前 phase 行、不动其他 phase。
**Validates: Requirements 7.3, 7.4, 7.5**

### Property 9: 版本 diff 互斥完备（既有 computeVersionDiff 回归）
added / removed / retained 三集合互斥且并集 = A ∪ B。
**Validates: Requirements 9.3**

### Property 10: 参数校验
`expectedMisstatement ≥ tolerableMisstatement` 时校验必失败；统计法缺 confidence/tolerable 时校验必失败。
**Validates: Requirements 20.2, 20.3**

## Testing Strategy

- **纯函数 PBT**（hypothesis/fast-check，max_examples≈5）：`computeMusInterval`/`computeSampleSize`（样本量随可容忍↓而↑、随置信度↑而↑）、`projectMisstatement`（污染率∈[0,1]、非负单调）、`computeUpperMisstatementLimit`（UML≥projected）、`deriveSamplingConclusion`（边界 UML=tolerable）、`markHighValueItems`（≥间隔全选）、`reconcilePopulation`（差异符号/阈值）、`computeAttributeSampleSize`/`evaluateDeviationRate`、既有 `applyFillMode`/`computeVersionDiff` 回归。
- **组件单测**：D3-7 OCR 映射 merge 保留已填值、抽样回填三模式、来源标注、只读禁用。
- **Playwright 实测**（铁律，diagnostics/单测查不出的交互）：D3-7 打开抽凭弹窗→配置方法学参数→抽样→勾选→回填→行级📎OCR确认→录入错报→查看结论→保存落库；0 console error；postgres 校验落库。

## 实现边界

- **必做**：A（Req 1~12，D3-7 样板全闭环）+ B 核心（R15 样本量、R16 重要性联动、R17 MUS 完整、R18 错报推断与结论、R19 总体校验、R20 参数、R22 重抽治理/可复现）。
- **可选/后续**：R21 备忘导出（次优先）、R23 属性抽样、Req 13~14 横向推广其他循环检查表（D2-7/G4-13/G5-12/G6/G7-18/G8-6/G9-6/G10-7/G12-6/G2/G3/F2）。
- 明确排除 `ui-pattern-unification` 负责的通用工具栏迁移与全局 collapse→dialog。
