# Task 4~18 — IC-1~IC-20 裁决落地现算证据

**日期**：2026-09-27　**方法**：python 脚本批量现算

IC-1/IC-4/IC-5 的数据已在 task1-slice-recompute.md（manifest/owner/CD 源区间）。
本文件覆盖 IC-2 / IC-6~IC-20 的补充现算。

```
============================================================
IC-2: 载体族二分表 — 宿主 grep
============================================================

  I1 (GtI1IntangibleAssets.vue, 520 lines):
    http/api import=1  checklist_get=0  bridge=0
    ocr=0  notice=0  publishToTb=0  adjCentral=0
    localStorage=0  legacyOO=0  allResponses=28

  I2 (GtI2DevelopmentExpenditure.vue, 607 lines):
    http/api import=1  checklist_get=0  bridge=0
    ocr=0  notice=0  publishToTb=0  adjCentral=0
    localStorage=0  legacyOO=0  allResponses=30

  I3 (GtI3Goodwill.vue, 427 lines):
    http/api import=1  checklist_get=0  bridge=0
    ocr=0  notice=0  publishToTb=0  adjCentral=0
    localStorage=0  legacyOO=0  allResponses=22

  I4 (GtI4LongTermPrepaid.vue, 421 lines):
    http/api import=1  checklist_get=0  bridge=0
    ocr=0  notice=0  publishToTb=0  adjCentral=0
    localStorage=0  legacyOO=0  allResponses=19

  I5 (GtI5OtherNoncurrentAssets.vue, 289 lines):
    http/api import=0  checklist_get=0  bridge=0
    ocr=0  notice=0  publishToTb=0  adjCentral=0
    localStorage=0  legacyOO=0  allResponses=11

  I6 (GtI6ResearchDevelopmentExpense.vue, 419 lines):
    http/api import=1  checklist_get=0  bridge=0
    ocr=0  notice=0  publishToTb=0  adjCentral=0
    localStorage=0  legacyOO=0  allResponses=20

============================================================
IC-6: 行身份位置化扫描（形态口径）
============================================================
  扫描文件数: 235
  位置化 site 命中: 19
    composables\i1DisclosureEnhance.ts#L241 [族B fallback i]: rowId: `tc-i18-${r.rowId || i}`,
    composables\i4TargetedCheckModel.ts#L1408 [族A Date.now]: rowId: `i45-i43-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    composables\i5TargetedCheckModel.ts#L956 [族A Date.now]: rowId: `i54-i53-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    composables\useI1Disclosure.ts#L220 [族A Date.now]: { rowId: `tc-${Date.now()}`, name: '', bookValue: 0, reason: '' },
    composables\useI1Disclosure.ts#L233 [族A Date.now]: { rowId: `imp-${Date.now()}`, name: '', bookValue: 0, remainingAmortMonths: 0 },
    composables\useI3Detail.ts#L495 [族A Date.now]: rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    composables\useI3Disclosure.ts#L441 [族B fallback i]: rowId: `bv-${r.rowId || i}`,
    composables\useI3Disclosure.ts#L463 [族B fallback i]: rowId: `imp-${r.rowId || i}`,
    composables\useI3Disclosure.ts#L488 [族B/A' ${i}]: rowId: `cgu-${i}`,
    composables\useI3Disclosure.ts#L503 [族B fallback i]: rowId: `perf-${r.rowId || i}`,
    composables\useI3Disclosure.ts#L521 [族A Date.now]: rowId: `i3disc-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    composables\useI3Disclosure.ts#L570 [族A Date.now]: rowId: `i3disc-m-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    composables\useI3Disclosure.ts#L629 [族A Date.now]: rowId: `perf-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    composables\useI3Disclosure.ts#L665 [族D ${added}]: rowId: `perf-${Date.now()}-${added}`,
    composables\useI3Disclosure.ts#L690 [族A Date.now]: rowId: `ap-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    composables\useI3Disclosure.ts#L725 [族D ${added}]: rowId: `ap-${Date.now()}-${added}`,
    composables\useI6Disclosure.ts#L213 [族A Date.now]: rowId: `i6d-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    i3\impairment\I3TabRecoverableTest.vue#L43 [族B fallback idx]: :key="cgu.rowId || idx"
    i4\amortization\I4TabAmortizationUnits.vue#L498 [族A Date.now]: rowId: `i4u-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,

============================================================
IC-7: removeRow 签名两族
============================================================
  I1 (composables/useI1Detail.ts#L623): function removeRow(rowIndex: number): void {
  I2 (composables/useI2Detail.ts#L505): function removeRow(index: number): void {
  I3 (composables/useI3Detail.ts#L580): function removeRow(rowIndex: number): void {
  I4 (composables/useI4Detail.ts#L672): function removeRow(rowId: string): void {
  I5 (composables/useI5Detail.ts#L821): function removeRow(rowId: string): void {
  I6 (composables/useI6Detail.ts#L779): function removeRow(id: string): void {

============================================================
IC-9: 裸 IF 计数 (per-file)
============================================================
  I1 无形资产、累计摊销及减值准备.xlsx: 202 裸 IF
  I2 开发支出.xlsx: 94 裸 IF
  I3 商誉.xlsx: 54 裸 IF
  I4 长期待摊费用.xlsx: 75 裸 IF
  I5 其他非流动资产.xlsx: 25 裸 IF
  I6 研发费用.xlsx: 34 裸 IF

============================================================
IC-10: definedName 计数 (per-file)
============================================================
  I1 无形资产、累计摊销及减值准备.xlsx: 0 definedName
  I2 开发支出.xlsx: 0 definedName
  I3 商誉.xlsx: 0 definedName
  I4 长期待摊费用.xlsx: 476 definedName
  I5 其他非流动资产.xlsx: 334 definedName
  I6 研发费用.xlsx: 0 definedName

============================================================
IC-10 续: 干净点检查
============================================================
  I1 无形资产、累计摊销及减值准备 / 明细表I1-2: max_row=41 max_column=56
  I2 开发支出 / 明细表I2-2: max_row=51 max_column=61
  I3 商誉 / 明细表I3-2: max_row=29 max_column=30
  I4 长期待摊费用 / 明细表I4-2: max_row=54 max_column=25
  I5 其他非流动资产 / 明细表I5-2: max_row=63 max_column=26
  I6 研发费用 / 明细表I6-2: max_row=44 max_column=65

============================================================
IC-11: 各册 sheet 名列表
============================================================

  I1 无形资产、累计摊销及减值准备 (18 sheets):
    底稿目录
    无形资产实质性程序 I1A
    审定表I1
    附注披露信息（上市公司）
    附注披露信息（国有企业）
    明细表I1-2
    调整分录汇总I1-3
    无形资产摊销减值政策检查表I1-4
    无形资产增加检查表I1-5
    无形资产减少明细表I1-6
    使用寿命检查表I1-7
    无形资产权属检查表I1-8
    摊销分配分析表I1-9
    摊销测算表（不含减值）I1-10（剩余年限法）
    摊销测算表（含减值）I1-11
    减值准备测试表I1-12
    可收回金额测试I1-13
    GT_Custom [HIDDEN]

  I2 开发支出 (21 sheets):
    底稿目录
    开发支出实质性程序I2A
    审定表I2-1
    附注披露（上市公司）
    附注披露（国有企业）
    明细表I2-2
    调整分录汇总I2-3
    会计政策检查I2-4
    实质性分析I2-5
    研发项目资本化时点判断I2-6
    研发项目构成明细表I2-7
    研发材料投入检查表I2-8
    研发人员认定检查表I2-9
    研发人员工时检查表I2-10
    委外研发检查表I2-11
    针对性检查表I2-12
    截止性测试（账到单据）I2-13
    截止性测试（单据到账）I2-14
    减值准备测试表I2-15
    可收回金额测试I2-16
    GT_Custom [HIDDEN]

  I3 商誉 (15 sheets):
    底稿目录
    商誉实质性程序 I3A
    审定表I3-1
    附注披露（上市公司）
    附注披露（国有企业）
    明细表I3-2
    调整分录汇总I3-3
    入账价值测算表I3-4
    针对性检查表I3-5
    商誉减值测试I3-6
    可收回金额测试I3-7
    复核公司减值测试过程及结论I3-8
    市场平均收益率2017 [HIDDEN]
    参考－商誉减值测试示例
    GT_Custom [HIDDEN]

  I4 长期待摊费用 (12 sheets):
    底稿目录
    长期待摊费用实质性程序 I4A
    审定表I4-1
    附注披露（上市公司）
    附注披露（国有企业）
    明细表I4-2
    调整分录汇总I4-3
    摊销政策检查表I4-4
    针对性检查表I4-5
    摊销测算I4-6
    摊销测算表I4-7（工作量法）
    GT_Custom [HIDDEN]

  I5 其他非流动资产 (9 sheets):
    底稿目录
    其他非流动资产实质性程序 I5A
    审定表I5-1
    附注披露（上市公司）
    附注披露（国有企业）
    明细表I5-2
    调整分录汇总I5-3
    针对性检查表I5-4
    GT_Custom [HIDDEN]

  I6 研发费用 (11 sheets):
    底稿目录
    研发费用实质性程序 I6A
    附注披露（上市公司）
    附注披露（国有企业）
    审定表I6-1
    明细表I6-2
    调整分录汇总I6-3
    其他针对性检查表I6-4
    截止性测试（账到单据）I6-5
    截止性测试（单据到账）I6-6
    GT_Custom [HIDDEN]

  Total sheets: 86

============================================================
IC-15/IC-16: notice + 门控 grep
============================================================
  I1: notice=0 toolbar=i1-header-toolbar
    isOoAvailable=2 仅结构化=1 el-segmented=3
  I2: notice=0 toolbar=i2-header-toolbar
    isOoAvailable=0 仅结构化=0 el-segmented=4
  I3: notice=0 toolbar=i3-header-toolbar
    isOoAvailable=2 仅结构化=1 el-segmented=2
  I4: notice=0 toolbar=i4-header-toolbar
    isOoAvailable=2 仅结构化=1 el-segmented=3
  I5: notice=0 toolbar=i5-header-toolbar
    isOoAvailable=2 仅结构化=1 el-segmented=2
  I6: notice=0 toolbar=i6-header-toolbar
    isOoAvailable=2 仅结构化=1 el-segmented=2

============================================================
IC-17: 跨引用 — I6-2-detail-rows 消费方
============================================================
  'I6-2-detail-rows' 消费方 (10 个):
    composables\expenseWpI1AmortPull.ts
    composables\h1DepAllocCounterpartPull.ts
    composables\h8DepAllocCounterpartPull.ts
    composables\i1AmortAllocCounterpartPull.ts
    composables\useI2Analysis.ts
    composables\useI6Adjudication.ts
    composables\useI6CrossSheet.ts
    composables\useI6Detail.ts
    composables\useI6Disclosure.ts
    composables\useI6TargetedCheck.ts

  'I2-2-rows' 跨 entry 消费方:
    composables\useI1AdditionCheck.ts

============================================================
IC-18: derived_total_keys 现算
============================================================
  I1: 150 个
    

/** 分支选择器选项（供 el-segmented 使用） */
export interface AmortBranchOption {
  label: string
  value: AmortBranch
}

/** 摊销矩阵行：I1-10 矩阵 + I1-11 源表分段字段 */
export interface I1AmortizationRow {
  rowId: string
  /** 资产分类（土地使用权/专利权/软件等） */
  category: string
  /** 资产名称（来自 I1-2） */
  name: string
  /** 原值 */
  cost: number
  /** 预计残值 */
  salvage: number
  /** 累计摊销期初 / 账面累计摊销 */
  accAmortBegin: number
  /** 账面累计摊销期末（差异核对用，默认=accAmortBegin） */
  bookAccAmortEnd: number
  /** 减值准备（仅 withImpair 分支使用） */
  impairment: number
  /** 开始使用日期 YYYY-MM-DD */
  startDate: string
  /** 使用寿命（年）— I1-11 源表输入 */
  usefulLifeYears: number
  /** 账面月摊销额 */
  bookMonthly: number
  /** 账面本期摊销额（I1-10 源列 N，优先于 bookMonthly×月数） */
  bookPeriodAmort: number
  /** 减值计提日期 YYYY-MM-DD（行级，优于模板全局日） */
  impairmentDate: string
  /** 使用寿命总月数 */
  usefulLifeMonths: number
  /** 已使用月数 */
  usedMonths: number
  /** 剩余月数 = usefulLifeMonths - usedMonths */
  remainingMonths: number
  /** 期初净值 F = 原值 − 残值 − 累计摊销 − 减值 */
  beginNbv: number
  /** 测算到期日 */
  fullAmortDate: string
  /** 已摊销月份 */
  monthsAmortized: number
  /** 截止减值日累计摊销月份 */
  monthsToImpairment: number
  /** 本期摊销月份 */
  periodMonths: number
  /** 本期减值前月数 */
  monthsBeforeImpairment: number
  /** 本期减值后月数 */
  monthsAfterImpairment: number
  /** 减值前月摊销额 */
  preMonthly: number
  /** 减值时测算累计摊销 */
  accAmortAtImpairment: number
  /** 减值后月摊销额 */
  postMonthly: number
  /** 月摊销额差异 = 账面月摊销 − 减值后月摊销 */
  monthlyDiff: number
  /** 本期摊销额差异 = 测算本期 − 账面本期（I1-10 源列 O） */
  periodDiff: number
  /** 累计摊销(测算) */
  calcAccAmort: number
  /** 累计摊销差异 = 账面 − 测算 */
  accAmortDiff: number
  /** 减值发生月（1-based 月索引，0=无减值）：兼容旧矩阵路径 */
  impairmentMonth: number
  /** 减值发生后新增的减值金额 */
  impairmentAmountAtMonth: number
  /** 月摊销额矩阵（最多28列，对应审计期间月份） */
  monthlyAmort: number[]
  /** 本期摊销合计 = sum(monthlyAmort) 或 T=Q×O+S×P */
  periodAmortization: number
  /** 当前月摊销额（最终计算值） */
  monthlyAmortAmount: number
}

/** 合计行结构 */
export interface I1AmortizationSummary {
  /** 各月合计（28列） */
  monthlyTotals: number[]
  /** 本期摊销总合计 */
  periodTotal: number
}

/** I1-10/11 ↔ I1-1 本期计提 / I1-9 分配合计勾稽 */
export interface I1AmortReconcileResult {
  adjudicatedProvision: number
  periodAmortTotal: number
  allocTotal: number
  vsAdjDiff: number
  vsAllocDiff: number
  matchedAdj: boolean
  matchedAlloc: boolean
}

/** 从 I1-2 提取的资产参数（用于初始化/同步行） */
export interface I1AssetParams {
  rowId: string
  name: string
  category?: string
  cost: number
  salvageRate: number
  usefulLifeMonths: number
  accAmortBegin: number
  /** 账面累计摊销期末（优先用于差异核对） */
  accAmortEnd?: number
  impairmentEnd: number
  acquisitionDate?: string
  /** 本期账面摊销额 → 推算账面月摊销 */
  amortProvision?: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 摊销矩阵列数（月数），28列宽表 */
const MATRIX_COLUMNS = 28

/** 分支选项（供 el-segmented） */
export const AMORT_BRANCH_OPTIONS: AmortBranchOption[] = [
  { label: 
    

/** 审定表行 */
export interface I1AdjudicationRow {
  rowId: string
  category: string            // 项目名称/分类
  beginBalance: number        // 期初余额
  increase: number            // 本期增加
  decrease: number            // 本期减少
  endBalance: number          // 期末余额（公式列）
  unadjusted: number          // 未审数
  aje: number                 // AJE调整
  rje: number                 // RJE重分类
  audited: number             // 审定数（公式列）
  isSubtotal?: boolean        // 小计行标记
  isEditable?: boolean        // 可编辑标记
}

/** 四、净值（按分类 + 变动额/率，对齐 Excel） */
export interface I1NetValueRow {
  rowId: string
  category: string
  beginNet: number
  endNet: number
  changeAmount: number
  changeRate: number | null
  isSignificant: boolean
  explanation: string
  isSubtotal?: boolean
}

/** Excel 审计说明事项(1)(2)(3) */
export interface I1QualitativeNotes {
  /** (1) 净值重大变动原因（变动率≥30%） */
  fluctuation: string
  /** (2) 使用寿命不确定无形资产的判断依据 */
  indefiniteLife: string
  /** (3) 权属、抵押情况说明 */
  ownershipPledge: string
}

/** 三角勾稽校验结果 */
export interface I1ReconciliationResult {
  rowId: string
  layer: string               // 
    

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** I1-2 明细行原始 JSON 结构 */
export interface I1DetailRowRaw {
  rowId?: string
  category?: string            // 资产分类（专利/商标/著作权/土地使用权/软件等）
  name?: string               // 资产名称
  acquisitionDate?: string    // 取得日期
  usefulLifeMonths?: number   // 使用寿命（月）
  salvageRate?: number        // 残值率
  amortizationMethod?: string // 摊销方法

  // 原值变动区段
  costBegin?: number          // 原值期初
  costIncrease?: number       // 原值增加
  costDecrease?: number       // 原值减少
  costEnd?: number            // 原值期末

  // 摊销区段
  accAmortBegin?: number      // 累计摊销期初
  amortProvision?: number     // 本期摊销
  amortTransferOut?: number   // 摊销转出
  accAmortEnd?: number        // 累计摊销期末
  netValue?: number           // 净值=原值-摊销-减值

  // 减值区段
  impairmentBegin?: number    // 减值期初
  impairmentProvision?: number // 本期计提
  impairmentReversal?: number  // 本期转回（无形资产减值不得转回，仅特殊情况）
  impairmentEnd?: number      // 减值期末
}

/** I1-10/I1-11 摊销测算行原始 JSON 结构 */
export interface I1AmortizationRowRaw {
  rowId?: string
  name?: string               // 资产名称
  cost?: number               // 原值
  salvage?: number            // 残值
  accAmort?: number           // 累计摊销
  impairment?: number         // 减值准备（I1-11含减值版本使用）
  remainingMonths?: number    // 剩余月数
  periodAmortization?: number // 本期摊销合计
  monthlyAmort?: number       // 月摊销额
}

/** I1-3 调整分录行原始 JSON 结构 */
export interface I1AdjustmentRowRaw {
  rowId?: string
  description?: string        // 调整事项
  category?: string           // 账项调整 / 报表调整 / 其他
  entryType?: string          // AJE / RJE
  reportItem?: string
  accountCode?: string        // 科目代码
  accountName?: string        // 科目名称
  noteItem?: string
  summary?: string            // 摘要（旧字段）
  debitAmount?: number        // 借方
  creditAmount?: number       // 贷方
  debit?: number              // 兼容旧字段
  credit?: number
  indexRef?: string           // 索引
  remark?: string
  sourceGroupId?: string
}

/** I1-9 摊销分配行原始 JSON 结构 */
export interface I1AmortAllocRowRaw {
  rowId?: string
  name?: string               // 资产名称
  totalAmort?: number         // 摊销总额
  productionCost?: number     // 生产成本（Excel 列）
  managementExpense?: number  // 管理费用
  sellingExpense?: number     // 销售费用
  manufacturingCost?: number  // 制造费用
  rdExpense?: number          // 研发费用
  otherExpense?: number       // 其他
}

// ─── Return Types ────────────────────────────────────────────────────────────

/** I1-2 明细合计 → I1 审定表交叉验证 */
export interface I1DetailTotals {
  cost: number      // 原值期末合计
  accAmort: number  // 累计摊销期末合计
  impairment: number // 减值准备期末合计
}

/** 审定数从明细汇总 */
export interface I1AdjudicationFromDetail {
  costAudited: number   // 原值审定数（=明细原值期末合计）
  amortAudited: number  // 摊销审定数（=明细摊销期末合计）
  impairAudited: number // 减值审定数（=明细减值期末合计）
}

/** 摊销分配按资产结构（I1-10/11 → I1-9） */
export interface I1AmortizationForAlloc {
  byAsset: Record<string, number>  // 按资产名称聚合本期摊销额
  total: number                     // 摊销总额
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 安全解析 JSON 数组字符串，失败回退空数组
 */
function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/**
 * 安全提取数值，NaN/null/undefined → 0
 */
function _getNum(val: any): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI1CrossSheet(allResponses: Ref<Map<string, any>>): {
  detailTotals: ComputedRef<I1DetailTotals>
  adjudicationFromDetail: ComputedRef<I1AdjudicationFromDetail>
  amortizationForAlloc: ComputedRef<I1AmortizationForAlloc>
} {
  // ─── 解析 I1-2 明细行数据 ──────────────────────────────────────────────

  const detailRows = computed<I1DetailRowRaw[]>(() => {
    const resp = allResponses.value.get(
    

// ─── Types ───────────────────────────────────────────────────────────────────

export interface I1AllocRow {
  rowId: string
  name: string
  /** 资产类别（来自 I1-2/I1-10，供类别汇总视图） */
  category?: string
  /** 摊销总额（来自 I1-10/11，只读同步） */
  totalAmort: number
  /** 生产成本（Excel 列；并入营业成本核对 D5） */
  productionCost: number
  manufacturingCost: number
  sellingExpense: number
  managementExpense: number
  rdExpense: number
  otherExpense: number
  remark: string
  _isSummary?: boolean
}

export interface I1AllocCategorySummary {
  category: string
  totalAmort: number
  productionCost: number
  manufacturingCost: number
  sellingExpense: number
  managementExpense: number
  rdExpense: number
  otherExpense: number
  assetCount: number
}

export type I1ExpenseField =
  | 
    

export interface I1AllocColTotals {
  productionCost: number
  manufacturingCost: number
  sellingExpense: number
  managementExpense: number
  rdExpense: number
  otherExpense: number
  allocSum: number
  totalAmort: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

export const I1_ALLOC_ROWS_KEY = 
    

export interface I1DetailSummary {
  costBegin: number
  costIncrease: number
  costDecrease: number
  costEnd: number
  auditedCostBegin: number
  auditedCostIncrease: number
  auditedCostDecrease: number
  auditedCostEnd: number
  accAmortBegin: number
  amortProvision: number
  amortOtherIncrease: number
  amortDisposal: number
  amortOtherDecrease: number
  accAmortEnd: number
  auditedAccAmortBegin: number
  auditedAmortIncrease: number
  auditedAmortDecrease: number
  auditedAccAmortEnd: number
  impairmentBegin: number
  impairmentProvision: number
  impairOtherIncrease: number
  impairDisposal: number
  impairOtherDecrease: number
  impairmentEnd: number
  auditedImpairmentBegin: number
  auditedImpairIncrease: number
  auditedImpairDecrease: number
  auditedImpairmentEnd: number
  netBegin: number
  netValue: number
  auditedNetBegin: number
  auditedNetEnd: number
}

export interface I1DetailCrossValidation {
  costDiff: number
  amortDiff: number
  impairDiff: number
  hasCostWarning: boolean
  hasAmortWarning: boolean
  hasImpairWarning: boolean
  hasAnyWarning: boolean
}

export interface I1DetailCategorySummary {
  category: string
  count: number
  costEnd: number
  accAmortEnd: number
  impairmentEnd: number
  netValue: number
}

const ITEM_ID_ROWS = 
    

export {
  I1_ADDITION_METHODS,
  I1_ADDITION_EXPORT_HEADERS,
  I1_ADDITION_DEFAULT_COVERAGE_THRESHOLD,
  I1_TRACE_SOURCE_OPTS,
  type I1AdditionCheckRow,
  type I1AdditionSummary,
  type I1TraceRow,
  type YnNa,
  type I1MethodColGroup,
  shouldShowColGroup,
  collectActiveColGroups,
}

const ITEM_ROWS = 
    

export {
  calcCostOfEquity,
  calcWaccAfterTax,
  calcPreTaxDiscountRate,
  calcRecoverableAmount,
}

export const DCF_FORECAST_YEARS = 5

/** 公允价值 − 处置费用（对齐 Excel 第一节） */
export interface I1FairValueDisposal {
  salesAgreementPrice: number
  salesAgreementNote: string
  activeMarketPrice: number
  activeMarketNote: string
  estimatedPrice: number
  estimatedNote: string
  legalFees: number
  relatedTaxes: number
  transportCosts: number
  directCosts: number
  otherCosts: number
  auditNote: string
}

/** WACC/CAPM 参数（百分比口径，与 H4/H8 一致：25=25%） */
export interface I1WaccParams {
  taxRate: number
  totalDebt: number
  totalEquity: number
  costOfDebt: number
  riskFreeRate: number
  beta: number
  marketReturn: number
}

export function defaultFvDisposal(): I1FairValueDisposal {
  return {
    salesAgreementPrice: 0,
    salesAgreementNote: 
    
      const cur = map.get(t) || { count: 0, netTotal: 0 }
      cur.count++
      cur.netTotal += r.netBookValue
      map.set(t, cur)
    }
    return [...map.entries()].map(([type, s]) => ({ type, ...s }))
  })

  function addRow(name: string): I1TitleCheckRow {
    const row = emptyI1TitleRow({ name: name.trim() })
    rows.value.push(row)
    _persistRows()
    return row
  }

  function removeRow(rowId: string): void {
    const i = rows.value.findIndex((r) => r.rowId === rowId)
    if (i < 0) return
    rows.value.splice(i, 1)
    _persistRows()
  }

  function updateField(rowId: string, field: keyof I1TitleCheckRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    Object.assign(row, recomputeI1TitleRow(row))
    // 权利人与实体名自动勾稽提示
    if (field === 
    
    const cur = map.get(cat) ?? {
      category: cat,
      count: 0,
      costEnd: 0,
      accAmortEnd: 0,
      impairmentEnd: 0,
      netValue: 0,
    }
    cur.count++
    cur.costEnd += r.costEnd
    cur.accAmortEnd += r.accAmortEnd
    cur.impairmentEnd += r.impairmentEnd
    cur.netValue += r.netValue
    map.set(cat, cur)
  }
  return [...map.values()]
}

export function buildI1DetailConclusionDraft(
  rows: I1DetailRow[],
  summary: I1DetailSummary,
  cross: I1DetailCrossValidation,
): string {
  const indefinite = rows.filter((r) => r.indefiniteLife === 
    
    const rows: I1AdjudicationRow[] = categories.map((cat) => ({
      rowId: `row-${prefix}-${cat}`,
      category: cat,
      beginBalance: 0, increase: 0, decrease: 0, endBalance: 0,
      unadjusted: 0, aje: 0, rje: 0, audited: 0,
      isSubtotal: false, isEditable: true,
    }))
    // 小计行
    const subtotalLabel = block === 
    
    label: string
    begin: number
    increase: number
    decrease: number
    end: number
    allNa: boolean
  }> = []
  for (const block of layers) {
    const meta = I1_SOE_LAYER_META[block.layer]
    const tot = layerTotal(block)
    out.push({
      layer: block.layer,
      kind: 
    
    return buildI1ConclusionDraft({
      assetName: row.name,
      fairValueNet: row.fairValueLessDisposal,
      valueInUse: row.valueInUse,
      recoverableAmount: row.recoverableAmount,
      recoverableSource: row.recoverableSource,
      bookValue: row.bookValue,
      effectiveDiscountRate: row.effectiveDiscountRate,
      growthRate: row.growthRate,
      fromWacc: row.waccAfterTax > 0,
    })
  }

  // ─── Computed: I1-12 合计行 ─────────────────────────────────────────────────

  /** I1-12 合计行 */
  const impairmentSummary: ComputedRef<I1ImpairmentSummary> = computed(() => {
    let totalBookValue = 0
    let totalFairValue = 0
    let totalDcf = 0
    let totalRecoverable = 0
    let totalNetBookValue = 0
    let totalShouldProvision = 0
    let totalAlreadyProvided = 0
    let totalSupplement = 0
    let totalOverProvision = 0
    let totalDifference = 0

    for (const row of impairmentRows.value) {
      totalBookValue += row.bookValue
      totalFairValue += row.fairValueLessDisposal
      totalDcf += row.dcfValue
      totalRecoverable += row.recoverableAmount
      totalNetBookValue += row.netBookValue
      totalShouldProvision += row.shouldProvision
      totalAlreadyProvided += row.alreadyProvided
      totalSupplement += row.supplement
      totalOverProvision += row.overProvision
      totalDifference += row.difference
    }

    return {
      totalBookValue,
      totalFairValue,
      totalDcf,
      totalRecoverable,
      totalNetBookValue,
      totalShouldProvision,
      totalAlreadyProvided,
      totalSupplement,
      totalOverProvision,
      totalDifference,
    }
  })

  const categorySummary: ComputedRef<I1ImpCategorySummary[]> = computed(() => {
    const map = new Map<string, I1ImpCategorySummary>()
    for (const row of impairmentRows.value) {
      const cat = (row.category || 
    
    rows.push({
      rowId: `row-${prefix}-subtotal`,
      category: subtotalLabel,
      beginBalance: 0, increase: 0, decrease: 0, endBalance: 0,
      unadjusted: 0, aje: 0, rje: 0, audited: 0,
      isSubtotal: true, isEditable: false,
    })
    return rows
  }

  // ─── Computed: 小计行（三区块各一） ────────────────────────────────────────

  const costSubtotal = computed<I1AdjudicationRow>(() => {
    const detail = costRows.value.filter((r) => !r.isSubtotal)
    return {
      rowId: 
    
    }
  }

  return {
    terminalValue,
    valueInUse,
    recoverableAmount,
    discountedCashFlows,
    discountedTerminalValue,
    discountFactors,
    pvForecast,
    fairValueLessDisposal,
    fairValueSource,
    disposalTotal,
    recoverableSource,
    costOfEquity: rateInfo.costOfEquity,
    waccAfterTax: rateInfo.waccAfterTax,
    preTaxDiscountRate: rateInfo.preTaxDiscountRate,
    effectiveDiscountRate: r,
    rateInvalid,
  }
}

export function buildI1ConclusionDraft(opts: {
  assetName: string
  fairValueNet: number
  valueInUse: number
  recoverableAmount: number
  recoverableSource: string
  bookValue: number
  effectiveDiscountRate: number
  growthRate: number
  fromWacc: boolean
}): string {
  const impair = Math.max((opts.bookValue || 0) - opts.recoverableAmount, 0)
  return [
    `经测算，无形资产「${opts.assetName || 
    
    }
  }

  watch(
    () => allResponses.value,
    () => {
      loadRows()
      loadCounterpart()
      loadPrior()
    },
    { immediate: true },
  )

  // ─── Upstream sync: I1-10/11 → totalAmort ──────────────────────────────────

  const resolvedByAsset = computed(() => {
    const external = params.amortizationByAsset?.value
    if (external && Object.keys(external).length > 0) {
      return { byAsset: external, total: Object.values(external).reduce((s, n) => s + _getNum(n), 0), sourceSheet: 
    
  /** ① 减值迹象描述 */
  indicationDesc: string
  /** 是否进行减值测试（寿命不确定 OR 有迹象） */
  needTest: boolean
  /** 账面原值（从 I1-2 带入，便于追溯） */
  cost: number
  /** 累计摊销（从 I1-2 带入） */
  accAmort: number
  /** 兼容旧字段：已入账减值（归一化时并入⑦） */
  impairmentProvision: number
  /** 兼容旧字段：原「净值」；现 ② 优先用 bookValue */
  netBookValue: number
  /** ② 账面价值 = 原值 − 累计摊销（不含减值） */
  bookValue: number
  /** ③ 公允价值减去处置费用后的净额 */
  fairValueLessDisposal: number
  /** ④ 预计未来现金流量的现值 */
  dcfValue: number
  /** ⑤ 可收回金额 = MAX(③,④)；无需测试时为 0 */
  recoverableAmount: number
  /** ⑥ 累计应计提减值 = MAX(②−⑤, 0) */
  shouldProvision: number
  /** ⑦ 期末账面已计提的减值准备 */
  alreadyProvided: number
  /** ⑧ 本期应补提 = MAX(⑥−⑦, 0) */
  supplement: number
  /** ⑨ 多提待查 = MAX(⑦−⑥, 0)；禁止转回 */
  overProvision: number
  /** Excel ⑧列差值 ⑥−⑦（可为负）；高亮仍看 ⑧/⑨ */
  difference: number
  /** 工作底稿索引号 */
  indexRef: string
  /** 备注 */
  remark: string
  /** 审计结论（适当/需补提/需关注/无需测试） */
  conclusion: string
  /** 是否关联 I1-13 */
  linkedToDcf: boolean
  /** 来源 I1-2 行 id */
  sourceDetailRowId?: string
}

/** I1-12 编制校验 */
export interface I1ImpPrepValidation {
  ok: boolean
  messages: string[]
}

// ─── Types: I1-13 可收回金额测试 (DCF) ──────────────────────────────────────

/** I1-13 可收回金额测试行（对齐 Excel 一/二/三节） */
export interface I1RecoverableTestRow {
  rowId: string
  /** 资产名称（与 I1-12 对应） */
  name: string
  /** 账面净值（对照用，可从 I1-12 带入） */
  bookValue: number
  /** 预测期现金流数组（5年）(Req 13.1) */
  cashFlows: number[]
  /** 手工折现率（小数，WACC 未就绪时回退；如0.08=8%） */
  discountRate: number
  /** 永续增长率 (如0.02=2%) */
  growthRate: number
  /** 增长率确定依据 */
  growthRateBasis: string
  /** CAS8 默认税前 */
  usePreTaxRate: boolean
  /** 公允/处置费用明细 */
  fvDisposal: I1FairValueDisposal
  /** WACC 参数 */
  waccParams: I1WaccParams
  /** 终值 = perpetuityCF / (r - g) */
  terminalValue: number
  /** DCF 使用价值 = PV(预测期) + PV(终值) (Req 13.2) */
  valueInUse: number
  /** 公允价值减去处置费用后的净额 */
  fairValueLessDisposal: number
  /** 可收回金额 = MAX(公允净额, DCF) (Req 13.3) */
  recoverableAmount: number
  /** 各期折现现金流 */
  discountedCashFlows: number[]
  /** 各期折现系数 1/(1+r)^t */
  discountFactors: number[]
  /** 终值折现值 */
  discountedTerminalValue: number
  /** 预测期现值合计 */
  pvForecast: number
  fairValueSource: string
  disposalTotal: number
  recoverableSource: string
  costOfEquity: number
  waccAfterTax: number
  preTaxDiscountRate: number
  effectiveDiscountRate: number
  rateInvalid: boolean
}

/** 敏感性分析结果 (Req 13.5) */
export interface SensitivityResult {
  /** 场景描述 */
  scenario: string
  /** 折现率 */
  discountRate: number
  /** 增长率 */
  growthRate: number
  /** 该场景下的 DCF 使用价值 */
  valueInUse: number
  /** 该场景下的可收回金额 */
  recoverableAmount: number
  /** 与基准值差额 */
  differenceFromBase: number
}

/** I1-12 合计行 */
export interface I1ImpairmentSummary {
  totalBookValue: number
  totalFairValue: number
  totalDcf: number
  totalRecoverable: number
  totalNetBookValue: number
  totalShouldProvision: number
  totalAlreadyProvided: number
  totalSupplement: number
  totalOverProvision: number
  totalDifference: number
}

/** 按类别汇总（对齐 Excel 底部分类合计） */
export interface I1ImpCategorySummary {
  category: string
  bookValue: number
  shouldProvision: number
  alreadyProvided: number
  supplement: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_12_ROWS = 
    
  > {
    return {
      terminalValue: calc.terminalValue,
      valueInUse: calc.valueInUse,
      fairValueLessDisposal: calc.fairValueLessDisposal,
      recoverableAmount: calc.recoverableAmount,
      discountedCashFlows: calc.discountedCashFlows,
      discountFactors: calc.discountFactors,
      discountedTerminalValue: calc.discountedTerminalValue,
      pvForecast: calc.pvForecast,
      fairValueSource: calc.fairValueSource,
      disposalTotal: calc.disposalTotal,
      recoverableSource: calc.recoverableSource,
      costOfEquity: calc.costOfEquity,
      waccAfterTax: calc.waccAfterTax,
      preTaxDiscountRate: calc.preTaxDiscountRate,
      effectiveDiscountRate: calc.effectiveDiscountRate,
      rateInvalid: calc.rateInvalid,
    }
  }

  // ─── DCF Calculation Core (Req 13.2) ───────────────────────────────────────

  function _calcDcfResult(row: Pick<
    I1RecoverableTestRow,
    
    
  const sum = calcRowAllocSum(row)
  const diff = sum - row.totalAmort
  return `分配合计(${fmtAmt(sum)}) ≠ 摊销总额(${fmtAmt(row.totalAmort)})，差额: ${fmtAmt(diff)}`
}

function getRowClassName({ row }: { row: I1AllocRow }): string {
  if (row._isSummary) return 
    
  return `三角勾稽差额: ${fmtAmount(result.difference)}（期末 ≠ 期初 + 增加 - 减少）`
}

// ─── Row Class ───────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: I1AdjudicationRow }): string {
  const classes: string[] = []
  if (row.isSubtotal) classes.push(
    
 * 8. 合计行：底部 subtotal 联动 I1-9
 *
 * 科目方向：
 * - 1702 累计摊销（贷方/备抵类）：月摊销额为贷方发生
 *
 * Spec: .kiro/specs/i1-intangible-assets/
 * Task: 3.5
 * Requirements: 11.1-11.7
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 
    
export const I1_ALLOC_TOTALS_KEY = 
    
import {
  I1_LISTED_COMPACT_CATEGORIES,
  aggregateI19AmortAlloc,
  buildI1ListedCrossCheck,
  buildI1SoeCrossCheck,
  draftImpairmentNoteFromI112,
  draftMortgageNoteFromI18,
  draftSaleNoteFromI16,
  draftTitleRowsFromI18,
  emptyDataResourceMove,
  fillNoteIfEmpty,
  formatAmortAllocNote,
  preferAuditedAmount,
  pullDataResourceFromListedMovement,
  readI1AdjAudited,
  validateI1ListedPrep,
  validateI1SoePrep,
  type I1AmortAllocSummary,
  type I1DataResourceMove,
  type I1ListedCategoryPreset,
} from 
    
import {
  I1_LISTED_DEFAULT_CATEGORIES,
  I1_LISTED_GUIDANCE,
  I1_LISTED_MOVEMENT_ROWS,
  i1ListedCellValue,
  i1ListedTotalCellValue,
  rawCell,
  type MovementRowDef,
} from 
    
import {
  I1_LISTED_MOVEMENT_ROWS,
  i1ListedCellValue,
  i1ListedTotalCellValue,
  type I1ListedCategory,
  type MovementCellMap,
} from 
    
import {
  I1_LISTED_MOVEMENT_ROWS,
  i1ListedCellValue,
  i1ListedTotalCellValue,
  type I1ListedSyncSnapshot,
} from 
    
import {
  I1_SOE_GUIDANCE,
  I1_SOE_LAYER_META,
  layerTotal,
  resolveCategoryEnd,
  resolveI1SoeCategories,
  type I1SoeLayer,
  type I1SoeLayerBlock,
} from 
    
import {
  I1_SOE_LAYER_META,
  layerTotal,
  type I1SoeLayerBlock,
} from 
    
import {
  type I1AdditionCheckRow,
  type I1AdditionSummary,
  type YnNa,
  type I2CapitalizationTransferItem,
  type I1MethodColGroup,
  type I1TraceRow,
  emptyI1AdditionRow,
  emptyI1TraceRow,
  normalizeI1AdditionRow,
  normalizeI1TraceRow,
  summarizeI1Addition,
  seedI1AdditionFromDetail,
  seedI1AdditionFromI2Transfer,
  seedI1TraceFromCheckRows,
  calcI1TraceAmountDiff,
  rowToExportRecord,
  I1_ADDITION_EXPORT_HEADERS,
  I1_ADDITION_METHODS,
  I1_ADDITION_DEFAULT_COVERAGE_THRESHOLD,
  I1_TRACE_SOURCE_OPTS,
  collectActiveColGroups,
  shouldShowColGroup,
} from 
    
}

export function calcI1AdditionCoverage(checkedTotal: number, periodTotal: number): number | null {
  if (!(periodTotal > 0)) return null
  return Math.round((checkedTotal / periodTotal) * 10000) / 100
}

/** 发票价税合计 = 不含税 + 进项税 */
export function calcInvoiceInclTax(exTax: number, inputVat: number): number {
  return (Number(exTax) || 0) + (Number(inputVat) || 0)
}

/** 外购价税勾稽：入账金额应 ≈ 发票不含税（进项税不进成本） */
export function isI1VatMismatch(row: Pick<I1AdditionCheckRow, 
    
}

function getSummary({ columns, data }: { columns: any[]; data: I1ImpairmentTestRow[] }) {
  const sums: string[] = []
  columns.forEach((col, index) => {
    if (index === 0) {
      sums[index] = 
    
}

function getSummaryRow({ columns, data }: { columns: any[]; data: I1AmortizationRow[] }) {
  const labelToKey: Record<string, keyof I1AmortizationRow> = {
    原值: 
    
}

function getSummaryRow({ columns, data }: { columns: any[]; data: I1AmortizationRow[] }) {
  const sumKeys: Partial<Record<string, keyof I1AmortizationRow>> = {
    cost: 
    
}

function summaryDisplayRow(tabKey: I1DetailTab): Record<string, any> {
  const s = summaryRow.value
  switch (tabKey) {
    case 
    
}
function cellOf(row: MovementRowDef, catKey: string) {
  return i1ListedCellValue(movement.value, row, catKey)
}
function totalOf(row: MovementRowDef) {
  return i1ListedTotalCellValue(movement.value, row, categories.value)
}
function movementRowClass({ row }: { row: MovementRowDef }) {
  if (row.kind === 
    
})
const populationDrift = computed(() =>
  linkedPeriodTotal.value.amount > 0
    && Math.abs(periodTotal.value - linkedPeriodTotal.value.amount) > 0.01,
)

function showCol(group: I1MethodColGroup) {
  return shouldShowColGroup(group, columnViewMode.value, rows.value)
}

function onField(row: I1AdditionCheckRow, field: keyof I1AdditionCheckRow) {
  updateCell(row.rowId, field, (row as any)[field])
}

function onYn(row: I1AdditionCheckRow, field: keyof I1AdditionCheckRow, v: YnNa) {
  updateCell(row.rowId, field, v)
}

function handleSyncPeriod() {
  const r = syncPeriodFromLinked()
  ElMessage({ type: r.ok ? 
    
}, { immediate: true })

const impairmentCount = computed(() =>
  currentRows.value.filter(r => (r.impairment ?? 0) > 0 || !!r.impairmentDate).length,
)

const totalImpairment = computed(() =>
  currentRows.value.reduce((sum, r) => sum + (r.impairment ?? 0), 0),
)

const totalBookMonthly = computed(() =>
  currentRows.value.reduce((sum, r) => sum + (r.bookMonthly ?? 0), 0),
)

const totalAccDiff = computed(() =>
  currentRows.value.reduce((sum, r) => sum + (r.accAmortDiff ?? 0), 0),
)

const significantDiffCount = computed(() =>
  currentRows.value.filter(r => Math.abs(r.accAmortDiff ?? 0) > 0.01 || Math.abs(r.monthlyDiff ?? 0) > 0.01).length,
)

function handleFieldChange(rowIndex: number, field: keyof I1AmortizationRow, value: number | string | null) {
  updateRowField(rowIndex, field, value ?? (typeof value === 
    
}, { immediate: true })

const totalBookPeriod = computed(() =>
  currentRows.value.reduce((s, r) => s + (r.bookPeriodAmort ?? 0), 0),
)
const totalPeriodDiff = computed(() =>
  currentRows.value.reduce((s, r) => s + (r.periodDiff ?? 0), 0),
)
const significantDiffCount = computed(() =>
  currentRows.value.filter(r => Math.abs(r.periodDiff ?? 0) > 0.01 || Math.abs(r.accAmortDiff ?? 0) > 0.01).length,
)

function handleFieldChange(rowIndex: number, field: keyof I1AmortizationRow, value: number | string | null) {
  updateRowField(rowIndex, field, value ?? (typeof value === 
     && raw) {
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch { return [] }
  }
  return []
}

function _getNum(v: any): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _mergeSeededRows(
  current: I1AdditionCheckRow[],
  seeded: I1AdditionCheckRow[],
): { rows: I1AdditionCheckRow[]; count: number } {
  const byName = new Map(current.map((r) => [r.name.trim(), r]))
  let count = 0
  const next = [...current]
  for (const s of seeded) {
    const key = s.name.trim()
    const prev = byName.get(key)
    if (prev) {
      prev.entryAmount = s.entryAmount
      prev.entryDate = s.entryDate || prev.entryDate
      prev.acquisitionMethod = s.acquisitionMethod || prev.acquisitionMethod
      if (s.otherMethod) prev.otherMethod = s.otherMethod
      prev.sourceDetailRowId = s.sourceDetailRowId || prev.sourceDetailRowId
      if (s.remark && !prev.remark) prev.remark = s.remark
      count++
    } else {
      next.push(s)
      byName.set(key, s)
      count++
    }
  }
  return { rows: next, count }
}

export function useI1AdditionCheck(
  wpId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: { onSave?: (itemId: string, value: any) => void },
) {
  const rows = ref<I1AdditionCheckRow[]>([])
  const traceRows = ref<I1TraceRow[]>([])
  /** 本期发生额（总体）— 优先 I1-2 / 审定表联动，可手工覆盖 */
  const periodTotal = ref(0)
  const periodManual = ref(false)
  /** 检查比例告警阈值 %（可配置，默认 20） */
  const coverageThreshold = ref(I1_ADDITION_DEFAULT_COVERAGE_THRESHOLD)
  /** EventBus 最近一次 I2 转入明细（跨底稿未合入 allResponses 时兜底） */
  const pendingI2Transfers = ref<I2CapitalizationTransferItem[]>([])
  const pendingI2Amount = ref(0)

  function _load() {
    const resp = allResponses.value.get(ITEM_ROWS)
    rows.value = _safeParse(resp?.remark ?? resp?.conclusion).map(normalizeI1AdditionRow)

    const tr = allResponses.value.get(ITEM_TRACE)
    traceRows.value = _safeParse(tr?.remark ?? tr?.conclusion).map(normalizeI1TraceRow)

    const pItem = allResponses.value.get(ITEM_PERIOD)
    const rawP = pItem?.remark ?? pItem?.conclusion
    if (rawP != null && rawP !== 
     ? JSON.parse(raw) : raw
      const n = Number(parsed?.allocSum)
      return Number.isFinite(n) ? n : 0
    } catch {
      return 0
    }
  }

  /** 本期测算合计 vs I1-1 摊销本期增加 / I1-9 分配合计 */
  const amortReconcile: ComputedRef<I1AmortReconcileResult> = computed(() => {
    const periodAmortTotal = _round2(summaryRow.value.periodTotal)
    const adjudicatedProvision = _round2(_readNumKey(...I1_ADJ_AMORT_PROVISION_KEYS))
    const allocTotal = _round2(_readAllocSum())
    const vsAdjDiff = _round2(periodAmortTotal - adjudicatedProvision)
    const vsAllocDiff = _round2(allocTotal - periodAmortTotal)
    const matchedAdj =
      adjudicatedProvision === 0
        ? Math.abs(periodAmortTotal) < RECONCILE_TOLERANCE
        : Math.abs(vsAdjDiff) <= RECONCILE_TOLERANCE
    const matchedAlloc =
      allocTotal === 0
        ? true
        : Math.abs(vsAllocDiff) <= RECONCILE_TOLERANCE
    return {
      adjudicatedProvision,
      periodAmortTotal,
      allocTotal,
      vsAdjDiff,
      vsAllocDiff,
      matchedAdj,
      matchedAlloc,
    }
  })

  // ─── Row Management ────────────────────────────────────────────────────────

  /**
   * 从 I1-2 明细数据同步资产行。
   * Req 11.6: 摊销测算表显示每资产每月摊销额横向矩阵。
   *
   * 匹配逻辑：按 rowId 或 name 关联现有行，新增缺少的资产。
   */
  function syncFromDetail(assetParams: I1AssetParams[]): void {
    const targetRows = amortBranch.value === 
     ? JSON.parse(raw) : raw
      if (Array.isArray(parsed) && parsed.length > 0) {
        rows.value = parsed.map(normalizeI1DetailRow)
      } else {
        rows.value = []
      }
    } catch {
      rows.value = []
    }
  }

  function _recalcRow(row: I1DetailRow): void {
    Object.assign(row, recomputeI1DetailRow(row))
  }

  function recalcAll(): void {
    for (const row of rows.value) _recalcRow(row)
  }

  const summaryRow: ComputedRef<I1DetailSummary> = computed(() => {
    const r = rows.value
    return {
      costBegin: calcSubtotal(r.map((x) => x.costBegin)),
      costIncrease: calcSubtotal(r.map((x) => x.costIncrease)),
      costDecrease: calcSubtotal(r.map((x) => x.costDecrease)),
      costEnd: calcSubtotal(r.map((x) => x.costEnd)),
      auditedCostBegin: calcSubtotal(r.map((x) => x.auditedCostBegin)),
      auditedCostIncrease: calcSubtotal(r.map((x) => x.auditedCostIncrease)),
      auditedCostDecrease: calcSubtotal(r.map((x) => x.auditedCostDecrease)),
      auditedCostEnd: calcSubtotal(r.map((x) => x.auditedCostEnd)),
      accAmortBegin: calcSubtotal(r.map((x) => x.accAmortBegin)),
      amortProvision: calcSubtotal(r.map((x) => x.amortProvision)),
      amortOtherIncrease: calcSubtotal(r.map((x) => x.amortOtherIncrease)),
      amortDisposal: calcSubtotal(r.map((x) => x.amortDisposal)),
      amortOtherDecrease: calcSubtotal(r.map((x) => x.amortOtherDecrease)),
      accAmortEnd: calcSubtotal(r.map((x) => x.accAmortEnd)),
      auditedAccAmortBegin: calcSubtotal(r.map((x) => x.auditedAccAmortBegin)),
      auditedAmortIncrease: calcSubtotal(r.map((x) => x.auditedAmortIncrease)),
      auditedAmortDecrease: calcSubtotal(r.map((x) => x.auditedAmortDecrease)),
      auditedAccAmortEnd: calcSubtotal(r.map((x) => x.auditedAccAmortEnd)),
      impairmentBegin: calcSubtotal(r.map((x) => x.impairmentBegin)),
      impairmentProvision: calcSubtotal(r.map((x) => x.impairmentProvision)),
      impairOtherIncrease: calcSubtotal(r.map((x) => x.impairOtherIncrease)),
      impairDisposal: calcSubtotal(r.map((x) => x.impairDisposal)),
      impairOtherDecrease: calcSubtotal(r.map((x) => x.impairOtherDecrease)),
      impairmentEnd: calcSubtotal(r.map((x) => x.impairmentEnd)),
      auditedImpairmentBegin: calcSubtotal(r.map((x) => x.auditedImpairmentBegin)),
      auditedImpairIncrease: calcSubtotal(r.map((x) => x.auditedImpairIncrease)),
      auditedImpairDecrease: calcSubtotal(r.map((x) => x.auditedImpairDecrease)),
      auditedImpairmentEnd: calcSubtotal(r.map((x) => x.auditedImpairmentEnd)),
      netBegin: calcSubtotal(r.map((x) => x.netBegin)),
      netValue: calcSubtotal(r.map((x) => x.netValue)),
      auditedNetBegin: calcSubtotal(r.map((x) => x.auditedNetBegin)),
      auditedNetEnd: calcSubtotal(r.map((x) => x.auditedNetEnd)),
    }
  })

  const crossValidation: ComputedRef<I1DetailCrossValidation> = computed(() => {
    const adjCost = options?.adjCostSubtotal?.value ?? 0
    const adjAmort = options?.adjAmortSubtotal?.value ?? 0
    const adjImpair = options?.adjImpairSubtotal?.value ?? 0
    // 与审定表优先比审定数期末
    const costDiff = summaryRow.value.auditedCostEnd - adjCost
    const amortDiff = summaryRow.value.auditedAccAmortEnd - adjAmort
    const impairDiff = summaryRow.value.auditedImpairmentEnd - adjImpair
    const hasCostWarning = adjCost !== 0 && Math.abs(costDiff) > 0.01
    const hasAmortWarning = adjAmort !== 0 && Math.abs(amortDiff) > 0.01
    const hasImpairWarning = adjImpair !== 0 && Math.abs(impairDiff) > 0.01
    return {
      costDiff,
      amortDiff,
      impairDiff,
      hasCostWarning,
      hasAmortWarning,
      hasImpairWarning,
      hasAnyWarning: hasCostWarning || hasAmortWarning || hasImpairWarning,
    }
  })

  const categorySummary = computed(() => buildI1DetailCategorySummary(rows.value))

  const needAnnualImpairmentCount = computed(() =>
    rows.value.filter((r) => r.indefiniteLife === 
     open>
      <summary>编制提示</summary>
      <ul>
        <li>本表对齐源模板：表A（政策+五维判断）→ 表B（同业寿命/方法）→ 有变更则表C（原估计）。</li>
        <li>优先「从 I1-2 带入」按类别汇总寿命/方法；寿命逐项复核请跳转 I1-7。</li>
        <li>行业模板仅为示意起步数据，引用前须核对手工年报附注并填写信息来源。</li>
        <li>估计变更属 CAS28 未来适用法；重大变更应联动 S3-2 并关注附注披露。</li>
        <li>「否」结论及表A「N」判断须在备注/说明中分析影响，必要时调整。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang=
     open>
      <summary>编制提示</summary>
      <ul>
        <li>本表适用于<strong>已计提减值</strong>的无形资产；无减值请切换「不含减值（I1-10）」。</li>
        <li>减值后月摊销＝(原值−残值−减值时累计摊销−减值准备)÷剩余月数。</li>
        <li>当期摊销＝减值前月数×减值前月摊销＋减值后月数×减值后月摊销。</li>
        <li>源表「本期折旧月份」已统一为「本期摊销月份」；期间起止日驱动月数推算（对齐 DATEDIF）。</li>
        <li>行级「计提减值准备日期」优于源表全局减值日，便于逐项复核。</li>
        <li>点击「同步I1-2参数」导入原值/累计摊销/减值/取得日期/使用寿命。</li>
        <li>「联动I1-12」按名称回写⑦已计提；若有⑧补提则默认减值日=截止日。</li>
        <li>差异列红色高亮时，应分析后决定调整或披露。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang=
     open>
      <summary>编制提示</summary>
      <ul>
        <li>本表适用于<strong>本期无新减值重算</strong>；有减值请切换「含减值（I1-11）」。</li>
        <li>源表 L=DATEDIF(开始,截止)+1 会虚增已使用多年资产的「本期月数」，本表已改为期间四分支。</li>
        <li>K=F/J，M=K×本期月数，O=M−账面本期摊销。</li>
        <li>点击「同步I1-2」导入原值/累计摊销/取得日期/使用寿命/本期摊销。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang=
     open>
      <summary>编制提示与减值迹象清单</summary>
      <ul>
        <li>先「从 I1-2 带入②」，再「从 I1-7 同步寿命」；判定迹象后「建 I1-13」→「回填③④」</li>
        <li>②=原值−累计摊销（不含减值）；⑦取 I1-2 减值期末；保存时⑧自动推送 K11</li>
        <li>有⑧补提时点「切换 I1-11 含减值」并回写减值金额后重算摊销</li>
        <li>⑥=MAX(②−⑤,0)；⑧=MAX(⑥−⑦,0)；⑨&gt;0 只调查不转回；处置结转≠转回</li>
      </ul>
      <p class=
     open>
      <summary>📋 编制提示（对齐 Excel 无形资产调整分录汇总表 I1-3）</summary>
      <div class=
     || Math.abs(Number(t.amountDiff) || 0) > 1,
  ).length
  return {
    checkedTotal,
    periodTotal: Math.max(Number(periodTotal) || 0, 0),
    coverageRate: calcI1AdditionCoverage(checkedTotal, periodTotal),
    financeBookTotal,
    financeCostTotal,
    comboAmountTotal,
    anomalyCount,
    checkedCount: rows.length,
    relatedPartyCount,
    fundRiskCount,
    vatMismatchCount,
    traceCount: (traceRows ?? []).length,
    traceUnrecordedCount,
  }
}

export function emptyI1AdditionRow(partial?: Partial<I1AdditionCheckRow>): I1AdditionCheckRow {
  return {
    rowId: partial?.rowId ?? `i1add-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    name: 
     }
    const hasDr = Math.abs(Number(dr.costBegin) || 0)
      + Math.abs(Number(dr.costIncPurchase) || 0)
      + Math.abs(Number(dr.costIncRd) || 0)
      + Math.abs(Number(dr.costIncOther) || 0) > 0.005
    if (hasDr) {
      out[I1_LISTED_SUBTABLE.dataResource] = buildDataResourceSubTableRows(dr)
    }
  }
  if (state.amortAlloc && Math.abs(state.amortAlloc.total) > 0.005) {
    out[
     }
    }
    const byName = new Map(rows.value.map((r) => [r.name.trim(), r]))
    let count = 0
    for (const s of seeded) {
      const prev = byName.get(s.name.trim())
      if (prev) {
        prev.originalCost = s.originalCost
        prev.accAmort = s.accAmort
        prev.impairment = s.impairment
        if (!prev.disposalMethod) prev.disposalMethod = s.disposalMethod
        prev.sourceDetailRowId = s.sourceDetailRowId
        Object.assign(prev, recomputeI1DisposalRow(prev))
        count++
      } else {
        rows.value.push(s)
        byName.set(s.name.trim(), s)
        count++
      }
    }
    if (count) _persist()
    return { ok: count > 0, count, message: `已从 I1-2 带入/更新 ${count} 行减少` }
  }

  function appendFromSamples(samples: any[]): number {
    let n = 0
    for (const s of samples ?? []) {
      const row = emptyI1DisposalRow({
        name: String(s.summary || s.description || 
     }
    }
    const merged = _mergeSeededRows(rows.value, seeded)
    rows.value = merged.rows
    if (!periodManual.value || !(periodTotal.value > 0)) {
      const linked = linkedPeriodTotal.value
      if (linked.amount > 0) setPeriodTotal(linked.amount, false)
    }
    _persistRows()
    return { ok: true, count: merged.count, message: `已从 I1-2 带入/更新 ${merged.count} 行` }
  }

  /** 解析 I2 转入候选：allResponses 明细 > 审定表 > EventBus 缓存 */
  function _resolveI2TransferItems(): { items: I2CapitalizationTransferItem[]; source: string } {
    const detail = _safeParse(
      allResponses.value.get(
     }
  })

  const summary: ComputedRef<I1AdditionSummary> = computed(() =>
    summarizeI1Addition(rows.value, periodTotal.value, traceRows.value),
  )

  const coverageLow: ComputedRef<boolean> = computed(() =>
    summary.value.coverageRate != null
      && summary.value.coverageRate < coverageThreshold.value
      && summary.value.periodTotal > 0,
  )

  const activeColGroups: ComputedRef<Set<I1MethodColGroup>> = computed(() =>
    collectActiveColGroups(rows.value),
  )

  function setPeriodTotal(amount: number, manual = true) {
    periodTotal.value = Math.max(amount || 0, 0)
    periodManual.value = manual
    _persistPeriod()
  }

  function setCoverageThreshold(n: number) {
    const v = Math.min(100, Math.max(1, Math.round(_getNum(n) || I1_ADDITION_DEFAULT_COVERAGE_THRESHOLD)))
    coverageThreshold.value = v
    _persistCoverageThreshold()
  }

  function syncPeriodFromLinked(): { ok: boolean; message: string } {
    const linked = linkedPeriodTotal.value
    if (!(linked.amount > 0)) {
      return { ok: false, message: 
     },
]

const TOLERANCE = 0.01

type CounterpartSnapshot = Partial<Record<I1ExpenseField, number | null>> & {
  _meta?: Partial<Record<I1ExpenseField, { message?: string; matchedLabel?: string }>>
  _pulledAt?: string
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _genRowId(): string {
  return `i1-alloc-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function _getNum(val: unknown): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

function _blankRow(name: string, totalAmort = 0, category = 
     },
])

// ─── 进度计算 ─────────────────────────────────────────────────────────────────
const totalCount = computed(() => allSheets.value.length)
const completedCount = computed(() => allSheets.value.filter(r => calcSheetProgress(r.prefix, 3) >= 100).length)
const progressPercent = computed(() => {
  if (totalCount.value === 0) return 0
  const avg = allSheets.value.reduce((sum, r) => sum + calcSheetProgress(r.prefix, 3), 0) / totalCount.value
  return Math.round(avg)
})

// ─── 底稿架构泳道（GtBArchitectureTree 数据源） ───────────────────────────────
const COMPONENT_TYPE_MAP: Record<string, string> = {
  I1A: 
     → I1-11 含减值（63 公式）
 * 2. 摊销矩阵：每资产每月摊销额横向矩阵（28列宽表）
 * 3. 月摊销计算：调用 useI1AmortizationEngine 纯函数
 * 4. 减值月重置：含减值版本在减值发生月重新计算剩余摊销基数
 * 5. 期间合计：per-asset period totals 供 I1-9 摊销分配联动
 * 6. 资产行管理：从 I1-2 明细取资产参数（名称/原值/残值/使用寿命）
 * 7. 持久化：rows JSON → checklist_responses 
    )

function toExcel6Row(row: I1AdjudicationRow) {
  const endAdj = (Number(row.aje) || 0) + (Number(row.rje) || 0)
  return {
    category: row.category,
    beginUnadj: row.beginBalance,
    beginAdj: 0,
    beginAudited: row.beginBalance,
    endUnadj: row.unadjusted,
    endAdj,
    endAudited: row.audited,
    isSubtotal: row.isSubtotal,
  }
}

const excel6Blocks = computed(() => [
  {
    key: 
    )
      return
    }

    // 持久化审定明细（普通保存路径，不写 TB）
    await saveAdjudication()

    const auditedCost = costSubtotal.value.audited
    const auditedAmort = amortSubtotal.value.audited
    const auditedImpairment = impairmentSubtotal.value.audited

    publishing.value = true
    try {
      // 多科目单次原子发布：三科目一次 writeback_rows（余额类 balance）
      const resp: any = await api.post(
        `/api/workpapers/${wpId.value}/audit-determination/publish-to-tb`,
        {
          // sheet 名固定含审定表子码 I1-1，后端 extract_determination_wp_code 据此解出 I1-1
          sheet_name: 
    )
    const amount = _getNum(row.periodAmortization)
    byAsset[name] = (byAsset[name] || 0) + amount
    total += amount
  }
  return { byAsset, total, sourceSheet }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI1AmortizationAlloc(params: {
  allResponses: Ref<Map<string, any>>
  /** 外部注入的按资产摊销额（优先）；缺省时从 allResponses 自算 */
  amortizationByAsset?: Ref<Record<string, number> | undefined>
  onSave?: (itemId: string, value: any) => void
  onPublishEvent?: (event: string, payload: any) => void
}) {
  const { allResponses, onSave, onPublishEvent } = params

  const rows = ref<I1AllocRow[]>([])
  const counterpartSnapshot = ref<CounterpartSnapshot>({})
  const counterpartPulledAt = ref(
    )
    const known = I1_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === accountCode)
    const debitAmount = parseAmt(raw.debitAmount ?? raw.debit)
    const creditAmount = parseAmt(raw.creditAmount ?? raw.credit)
    const description = String(raw.description ?? raw.summary ?? 
    )
    } finally {
      publishing.value = false
    }
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    const save = options?.onSave
    if (!save) return
    save(`${ITEM_PREFIX}-cost-rows`, costRows.value.filter((r) => !r.isSubtotal))
    save(`${ITEM_PREFIX}-amort-rows`, amortRows.value.filter((r) => !r.isSubtotal))
    save(`${ITEM_PREFIX}-impair-rows`, impairmentRows.value.filter((r) => !r.isSubtotal))
    // 跨表 seed：原值本期增加合计 → I1-5 检查比例分母（及兼容旧 key）
    const costIncreaseTotal = costSubtotal.value.increase
    save(`${ITEM_PREFIX}-cost-increase-total`, costIncreaseTotal)
    save(
    )
  const amortAlloc = ref<I1AmortAllocSummary>(aggregateI19AmortAlloc([]))
  const auditNote = ref(
    )
  const discCost = cost ? layerTotal(cost).end : 0
  const discAmort = amort ? layerTotal(amort).end : 0
  const discImpair = impair ? layerTotal(impair).end : 0
  const costDiff = discCost - num(adj.cost)
  const amortDiff = discAmort - num(adj.amort)
  const impairDiff = discImpair - num(adj.impair)
  const hasCostWarning = Math.abs(costDiff) > 0.01
  const hasAmortWarning = Math.abs(amortDiff) > 0.01
  const hasImpairWarning = Math.abs(impairDiff) > 0.01
  const adjAny = Math.abs(num(adj.cost)) + Math.abs(num(adj.amort)) + Math.abs(num(adj.impair)) > 0.01
  return {
    costDiff,
    amortDiff,
    impairDiff,
    hasCostWarning: adjAny && hasCostWarning,
    hasAmortWarning: adjAny && hasAmortWarning,
    hasImpairWarning: adjAny && hasImpairWarning,
    hasAnyWarning: adjAny && (hasCostWarning || hasAmortWarning || hasImpairWarning),
    adjCost: num(adj.cost),
    adjAmort: num(adj.amort),
    adjImpair: num(adj.impair),
    discCost,
    discAmort,
    discImpair,
  }
}

export interface I1DisclosurePrepValidation {
  ok: boolean
  blocking: string[]
  warnings: string[]
}

export function validateI1ListedPrep(params: {
  movement: MovementCellMap
  categories: readonly I1ListedCategory[]
  titleCertRows: Array<{ name: string; bookValue: number; reason: string }>
  cross?: I1DisclosureCrossCheck | null
}): I1DisclosurePrepValidation {
  const blocking: string[] = []
  const warnings: string[] = []
  const costIncKeys = [
    )
  const titleCertRows = ref<I1TitleCertRow[]>([])
  const importantRows = ref<I1ImportantItemRow[]>([])
  const dataResource = ref<I1DataResourceMove>(emptyDataResourceMove())
  const amortAlloc = ref<I1AmortAllocSummary>(aggregateI19AmortAlloc([]))
  const auditNote = ref(
    )
  }

  function _persistRows() {
    options.onSave?.(ITEM_ID_ROWS, rows.value)
  }

  watch(options.allResponses, () => _load(), { immediate: true, deep: true })

  const filteredRows: ComputedRef<I1TitleCheckRow[]> = computed(() => {
    if (!filterType.value) return rows.value
    return rows.value.filter((r) => r.type === filterType.value)
  })

  const totalCost = computed(() => rows.value.reduce((s, r) => s + r.cost, 0))
  const totalAccAmort = computed(() => rows.value.reduce((s, r) => s + r.accAmort, 0))
  const totalImpairment = computed(() => rows.value.reduce((s, r) => s + r.impairment, 0))
  const totalNet = computed(() => rows.value.reduce((s, r) => s + r.netBookValue, 0))
  const totalMortgage = computed(() =>
    rows.value.filter((r) => r.mortgageRestricted === 
    )
  } finally {
    pullingCounterpart.value = false
  }
}

async function handlePushToExpense(silent = false): Promise<void> {
  if (!props.projectId || props.isReadonly) return
  pushingExpense.value = true
  try {
    const t = colTotals.value
    const result = await pushI1AmortToExpenseWps(props.projectId, {
      productionManufacturing: t.productionCost + t.manufacturingCost,
      selling: t.sellingExpense,
      management: t.managementExpense,
      rd: t.rdExpense,
    })
    if (!silent) {
      if (result.ok > 0) ElMessage.success(`已回写 ${result.ok} 个对方底稿`)
      else ElMessage.warning(result.messages.slice(0, 2).join(
    )
}

// ─── WACC 口径防呆 / I1-12↔I1-13 一致性 ─────────────────────────────────────

const SYNC_TOLERANCE = 0.01

/** WACC 参数校验警告（百分比口径） */
export function validateWaccParams(wacc: I1WaccParams): string[] {
  const msgs: string[] = []
  const { taxRate, costOfDebt, riskFreeRate, beta, marketReturn, totalDebt, totalEquity } = wacc
  const hasCapital = (totalDebt || 0) + (totalEquity || 0) > 0

  if (taxRate > 0 && (taxRate < 5 || taxRate > 40)) {
    msgs.push(`所得税率 t=${taxRate}% 异常（常见 15%~25%；请确认已按百分比填写）`)
  }
  if (riskFreeRate > 0 && riskFreeRate < 0.5) {
    msgs.push(`无风险利率 Rf=${riskFreeRate} 过小，疑似填成小数（应填百分比，如国债 2.5 表示 2.5%）`)
  } else if (riskFreeRate > 15) {
    msgs.push(`无风险利率 Rf=${riskFreeRate}% 偏高，请复核取值`)
  }
  if (marketReturn > 0 && marketReturn < 1) {
    msgs.push(`市场回报 Rm=${marketReturn} 过小，疑似填成小数（应填如 8 表示 8%，勿填 0.08 或 1.10）`)
  } else if (marketReturn > 0 && marketReturn < 4) {
    msgs.push(`市场回报 Rm=${marketReturn}% 偏低；若误将风险溢价当 Rm，请改为完整市场回报率`)
  } else if (marketReturn > 25) {
    msgs.push(`市场回报 Rm=${marketReturn}% 异常偏高（常见 6%~12%；源表示例 1.10/110% 即为口径错误）`)
  }
  if (costOfDebt > 0 && costOfDebt < 0.5) {
    msgs.push(`债务成本 Kd=${costOfDebt} 过小，疑似填成小数（应填百分比，如 5 表示 5%）`)
  } else if (costOfDebt > 30) {
    msgs.push(`债务成本 Kd=${costOfDebt}% 偏高，请复核`)
  }
  if (beta > 0 && (beta < 0.2 || beta > 3)) {
    msgs.push(`β=${beta} 偏离常见区间(0.5~2.0)，请复核`)
  }
  if (hasCapital && marketReturn > 0 && riskFreeRate > 0 && marketReturn <= riskFreeRate) {
    msgs.push(`市场回报 Rm(${marketReturn}%) ≤ 无风险利率 Rf(${riskFreeRate}%)，权益风险溢价为负，请复核`)
  }
  if (hasCapital && riskFreeRate === 0 && marketReturn === 0 && costOfDebt === 0) {
    msgs.push(
    )
}

export function useI1Detail(
  wpId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    adjCostSubtotal?: Ref<number>
    adjAmortSubtotal?: Ref<number>
    adjImpairSubtotal?: Ref<number>
    onSave?: (itemId: string, value: any) => void
  },
) {
  const rows = ref<I1DetailRow[]>([])
  const activeTab = ref<I1DetailTab>(
    )
}

function netRowClass({ row }: { row: I1NetValueRow }): string {
  if (row.isSubtotal) return 
    ) as string
}

onMounted(loadAuditText)
watch(() => props.allResponses, loadAuditText, { deep: true })

const {
  rows,
  activeTab,
  activeRowIndex,
  summaryRow,
  crossValidation,
  categorySummary,
  needAnnualImpairmentCount,
  tabs,
  switchTab,
  setActiveRow,
  updateCell,
  addRow,
  removeRow,
  fillConclusionDraft,
} = useI1Detail(
  toRef(props, 
    ) as string
}

watch(() => props.allResponses, () => loadAuditText(), { immediate: true })

const {
  rows,
  displayRows,
  sourceAmortTotal,
  sourceSheetLabel,
  vsSourceDiff,
  isBalancedWithSource,
  unbalancedCount,
  reconciliationRows,
  counterpartPulledAt,
  setCounterpartManual,
  applyCounterpartPull,
  categorySummaryRows,
  priorConsistent,
  priorNote,
  savePriorAssessment,
  updateCell,
  addRow,
  removeRow,
  allocateAllRemaindersTo,
  publishAllocated,
  colTotals,
  calcRowAllocSum,
  isRowBalanced,
  calcRowRemainder,
  fmtPercent,
  expenseCols,
} = useI1AmortizationAlloc({
  allResponses: allResponsesRef,
  amortizationByAsset: amortByAssetRef,
  onSave(itemId, value) {
    emit(
    ) continue
      const n = Number(raw)
      if (Number.isFinite(n)) return n
    }
    return 0
  }

  function _readAllocSum(): number {
    const item = allResponses.value.get(I1_ALLOC_TOTALS_KEY)
    const raw = item?.remark ?? item?.conclusion
    if (!raw) return 0
    try {
      const parsed = typeof raw === 
    ) return d
  return {
    taxRate: Number(raw.taxRate) || 0,
    totalDebt: Number(raw.totalDebt) || 0,
    totalEquity: Number(raw.totalEquity) || 0,
    costOfDebt: Number(raw.costOfDebt) || 0,
    riskFreeRate: Number(raw.riskFreeRate) || 0,
    beta: Number(raw.beta) || 0,
    marketReturn: Number(raw.marketReturn) || 0,
  }
}

/**
 * 有效折现率（小数口径，如 0.10）。
 * WACC 就绪时取税前/税后；否则回退手工折现率。
 */
export function calcEffectiveDiscountRate(
  wacc: I1WaccParams,
  manualDiscountRate: number,
  usePreTaxRate: boolean,
): {
  costOfEquity: number
  waccAfterTax: number
  preTaxDiscountRate: number
  effectiveRate: number
  fromWacc: boolean
} {
  const ke = calcCostOfEquity(wacc.riskFreeRate, wacc.beta, wacc.marketReturn)
  const waccAt = calcWaccAfterTax(
    wacc.totalDebt,
    wacc.totalEquity,
    ke,
    wacc.costOfDebt,
    wacc.taxRate,
  )
  const preTax = calcPreTaxDiscountRate(waccAt, wacc.taxRate)
  const fromWacc = waccAt > 0
  const effectivePct = fromWacc
    ? (usePreTaxRate ? preTax : waccAt)
    : manualDiscountRate * 100
  return {
    costOfEquity: ke,
    waccAfterTax: waccAt,
    preTaxDiscountRate: preTax,
    effectiveRate: effectivePct / 100,
    fromWacc,
  }
}

export interface I1DcfCalcResult {
  terminalValue: number
  valueInUse: number
  recoverableAmount: number
  discountedCashFlows: number[]
  discountedTerminalValue: number
  discountFactors: number[]
  pvForecast: number
  fairValueLessDisposal: number
  fairValueSource: string
  disposalTotal: number
  recoverableSource: string
  costOfEquity: number
  waccAfterTax: number
  preTaxDiscountRate: number
  effectiveDiscountRate: number
  rateInvalid: boolean
}

/**
 * 完整 I1-13 测算（对齐 Excel 公式链）
 */
export function calcI1RecoverableResult(opts: {
  cashFlows: number[]
  manualDiscountRate: number
  growthRate: number
  fvDisposal: I1FairValueDisposal
  waccParams: I1WaccParams
  usePreTaxRate: boolean
  /** 旧数据兼容：无公允明细时直接用该净额 */
  legacyFairValueNet?: number
}): I1DcfCalcResult {
  const fvResolved = resolveI1FairValue(opts.fvDisposal)
  const disposalTotal = calcI1DisposalTotal(opts.fvDisposal)
  const hasDetail = hasFvDetail(opts.fvDisposal)
  const fairValueLessDisposal = hasDetail
    ? fvResolved.value - disposalTotal
    : (Number(opts.legacyFairValueNet) || 0)
  const fairValueSource = hasDetail ? fvResolved.source : (fairValueLessDisposal > 0 ? 
    ) return false
  const ex = Number(row.invoiceAmountExTax) || 0
  if (!(ex > 0)) return false
  return Math.abs((Number(row.entryAmount) || 0) - ex) > 1
}

export function calcI1TraceAmountDiff(sourceAmount: number, bookAmount: number): number {
  return Math.round(((Number(sourceAmount) || 0) - (Number(bookAmount) || 0)) * 100) / 100
}

export function summarizeI1Addition(
  rows: I1AdditionCheckRow[],
  periodTotal: number,
  traceRows: I1TraceRow[] = [],
): I1AdditionSummary {
  let checkedTotal = 0
  let financeBookTotal = 0
  let financeCostTotal = 0
  let comboAmountTotal = 0
  let anomalyCount = 0
  let relatedPartyCount = 0
  let fundRiskCount = 0
  let vatMismatchCount = 0
  for (const r of rows) {
    checkedTotal += Number(r.entryAmount) || 0
    financeBookTotal += Number(r.financeBookAmount) || 0
    financeCostTotal += Number(r.financeCost) || 0
    comboAmountTotal += Number(r.comboAmount) || 0
    if (r.checkConclusion === 
    ) {
      _calcMatrixNoImpair(row)
    } else {
      _calcMatrixWithImpair(row)
    }

    _persist()
  }

  // ─── Computed: 合计行（Req 11.7 底部合计联动I1-9）─────────────────────────

  /**
   * 合计行：各月合计 + 本期摊销总合计。
   * Req 11.7: 底部合计行联动 I1-9 摊销分配。
   */
  const summaryRow: ComputedRef<I1AmortizationSummary> = computed(() => {
    const rows = currentRows.value
    const monthlyTotals = new Array(MATRIX_COLUMNS).fill(0)
    let periodTotal = 0

    for (const row of rows) {
      for (let m = 0; m < MATRIX_COLUMNS; m++) {
        monthlyTotals[m] += row.monthlyAmort[m] ?? 0
      }
      periodTotal += row.periodAmortization
    }

    return { monthlyTotals, periodTotal }
  })

  // ─── Computed: per-asset period totals (供 I1-9 摊销分配使用) ───────────────

  /**
   * 按资产名称聚合本期摊销额，供 I1-9 摊销分配表读取。
   * Req 11.7: 合计行联动I1-9摊销分配。
   */
  const assetPeriodTotals: ComputedRef<Record<string, number>> = computed(() => {
    const result: Record<string, number> = {}
    for (const row of currentRows.value) {
      const key = row.name || 
    )!
  const discCost = i1ListedTotalCellValue(movement, costEnd, categories)
  const discAmort = i1ListedTotalCellValue(movement, amortEnd, categories)
  const discImpair = i1ListedTotalCellValue(movement, impEnd, categories)
  const costDiff = discCost - num(adj.cost)
  const amortDiff = discAmort - num(adj.amort)
  const impairDiff = discImpair - num(adj.impair)
  const hasCostWarning = Math.abs(num(adj.cost)) > 0.005 && Math.abs(costDiff) > 0.01
  const hasAmortWarning = Math.abs(num(adj.amort)) > 0.005 && Math.abs(amortDiff) > 0.01
  const hasImpairWarning = Math.abs(num(adj.impair)) > 0.005 && Math.abs(impairDiff) > 0.01
  // 若审定尚未发布，也允许与 0 比：仅当披露侧非零且审定全 0 时不告警
  const adjAny = Math.abs(num(adj.cost)) + Math.abs(num(adj.amort)) + Math.abs(num(adj.impair)) > 0.01
  return {
    costDiff,
    amortDiff,
    impairDiff,
    hasCostWarning: adjAny && hasCostWarning,
    hasAmortWarning: adjAny && hasAmortWarning,
    hasImpairWarning: adjAny && hasImpairWarning,
    hasAnyWarning: adjAny && (hasCostWarning || hasAmortWarning || hasImpairWarning),
    adjCost: num(adj.cost),
    adjAmort: num(adj.amort),
    adjImpair: num(adj.impair),
    discCost,
    discAmort,
    discImpair,
  }
}

export function buildI1SoeCrossCheck(
  layers: I1SoeLayerBlock[],
  adj: { cost: number; amort: number; impair: number },
): I1DisclosureCrossCheck {
  const cost = layers.find((l) => l.layer === 
    ))
        }
      }
    },
    { immediate: true, deep: true },
  )

  /** 按类别折叠汇总（只读，服务附注/Excel 类别披露） */
  const categorySummaryRows = computed<I1AllocCategorySummary[]>(() => {
    const bags = new Map<string, I1AllocCategorySummary>()
    for (const row of rows.value) {
      const cat = (row.category || 
    ))
  return Number.isFinite(x) ? x : 0
}

export function resolveCategoryEnd(m: I1SoeMoveAmounts, movementNa: boolean): number {
  if (movementNa) return num(m.end)
  return num(m.begin) + num(m.increase) - num(m.decrease)
}

export function layerTotal(block: I1SoeLayerBlock): I1SoeMoveAmounts {
  const meta = I1_SOE_LAYER_META[block.layer]
  const begin = block.categories.reduce((s, c) => s + num(c.begin), 0)
  const increase = meta.movementNa ? 0 : block.categories.reduce((s, c) => s + num(c.increase), 0)
  const decrease = meta.movementNa ? 0 : block.categories.reduce((s, c) => s + num(c.decrease), 0)
  const end = block.categories.reduce((s, c) => s + resolveCategoryEnd(c, meta.movementNa), 0)
  return { begin, increase, decrease, end }
}

/** 账面价值 = 原值 − 摊销 − 减值 */
export function recomputeI1SoeDerivedLayers(layers: I1SoeLayerBlock[]): I1SoeLayerBlock[] {
  const byLayer = new Map(layers.map((l) => [l.layer, l]))
  const cost = byLayer.get(
    ))
  })

  // ─── Aggregates ────────────────────────────────────────────────────────────

  const colTotals = computed<I1AllocColTotals>(() => {
    let productionCost = 0
    let manufacturingCost = 0
    let sellingExpense = 0
    let managementExpense = 0
    let rdExpense = 0
    let otherExpense = 0
    let totalAmort = 0

    for (const row of rows.value) {
      productionCost += _getNum(row.productionCost)
      manufacturingCost += _getNum(row.manufacturingCost)
      sellingExpense += _getNum(row.sellingExpense)
      managementExpense += _getNum(row.managementExpense)
      rdExpense += _getNum(row.rdExpense)
      otherExpense += _getNum(row.otherExpense)
      totalAmort += _getNum(row.totalAmort)
    }

    const allocSum =
      productionCost + manufacturingCost + sellingExpense + managementExpense + rdExpense + otherExpense

    return {
      productionCost,
      manufacturingCost,
      sellingExpense,
      managementExpense,
      rdExpense,
      otherExpense,
      allocSum,
      totalAmort,
    }
  })

  const summaryRow = computed<I1AllocRow>(() => {
    const t = colTotals.value
    return {
      rowId: 
    ))
const i13Nets = computed(() => adjustmentNets.value)
const canSyncI13 = computed(() => {
  const n = i13Nets.value
  return (
    Math.abs(n.costAje) + Math.abs(n.costRje) + Math.abs(n.amortAje)
    + Math.abs(n.amortRje) + Math.abs(n.impairAje) + Math.abs(n.impairRje)
  ) >= 0.005
})

function _readPeriodAmortTotal(): number {
  const m = props.allResponses
  for (const key of [
    )) {
        if (isRje) impairRje += net
        else impairAje += net
      }
    }
    return { costAje, costRje, amortAje, amortRje, impairAje, impairRje }
  })

  // ─── detailTotals: I1-2 明细聚合原值/摊销/减值合计（Req 2.4-2.7）──────

  /**
   * 从 I1-2 明细行聚合三科目期末合计：
   * - cost: 所有行 costEnd 之和（科目1701原值期末）
   * - accAmort: 所有行 accAmortEnd 之和（科目1702摊销期末）
   * - impairment: 所有行 impairmentEnd 之和（科目1703减值期末）
   *
   * 用于与 I1 审定表三区块小计交叉验证。
   */
  const detailTotals: ComputedRef<I1DetailTotals> = computed(() => {
    let cost = 0
    let accAmort = 0
    let impairment = 0

    for (const row of detailRows.value) {
      cost += _getNum(row.costEnd)
      accAmort += _getNum(row.accAmortEnd)
      impairment += _getNum(row.impairmentEnd)
    }

    return { cost, accAmort, impairment }
  })

  // ─── adjudicationFromDetail: I1-2 合计 → I1 审定表（Req 2.4-2.9）──────

  /**
   * I1-2 明细合计供 I1 审定表三区块交叉验证：
   * - costAudited: 原值期末合计（= I1 审定表
    ),
      summary: description,
      debit: debitAmount,
      credit: creditAmount,
      sourceGroupId: raw.sourceGroupId ? String(raw.sourceGroupId) : undefined,
    }
  }

  function _toPersistShape(list: I1AdjustmentRow[]) {
    return list.map((r, i) => ({
      ...r,
      seq: i + 1,
      debit: r.debitAmount,
      credit: r.creditAmount,
      summary: r.description,
      entryType: entryTypeFromCategory(String(r.category)),
    }))
  }

  function load(): void {
    const parsed = _getJson(ROWS_KEY)
    if (Array.isArray(parsed)) {
      rows.value = parsed.map((r, i) => _normalizeRow(r, i))
    } else {
      rows.value = []
    }
    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(allResponses, () => load(), { immediate: true })

  const debitTotal = computed(() => rows.value.reduce((s, r) => s + r.debitAmount, 0))
  const creditTotal = computed(() => rows.value.reduce((s, r) => s + r.creditAmount, 0))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() => Math.abs(balanceDiff.value) < BALANCE_TOLERANCE)

  /** 按「调整事项+类型」分组的借贷平衡（与推送分组键一致） */
  const groupBalanceIssues = computed(() => {
    const groups = new Map<string, {
      key: string
      description: string
      entryType: string
      debit: number
      credit: number
      rowCount: number
    }>()
    for (const r of rows.value) {
      const et = r.entryType || entryTypeFromCategory(String(r.category))
      const desc = String(r.description || 
    ),
    costEnd: 0,
    costBeginAdj: _n(raw.costBeginAdj),
    costAdjInc: _n(raw.costAdjInc),
    costAdjDec: _n(raw.costAdjDec),
    auditedCostBegin: 0,
    auditedCostIncrease: 0,
    auditedCostDecrease: 0,
    auditedCostEnd: 0,
    accAmortBegin: _n(raw.accAmortBegin),
    amortProvision: _n(raw.amortProvision),
    amortOtherIncrease: _n(raw.amortOtherIncrease),
    amortDisposal: _n(raw.amortDisposal),
    amortOtherDecrease: _n(raw.amortOtherDecrease),
    amortTransferOut: _n(raw.amortTransferOut),
    accAmortEnd: 0,
    accAmortBeginAdj: _n(raw.accAmortBeginAdj),
    amortAdjInc: _n(raw.amortAdjInc),
    amortAdjDec: _n(raw.amortAdjDec),
    auditedAccAmortBegin: 0,
    auditedAmortIncrease: 0,
    auditedAmortDecrease: 0,
    auditedAccAmortEnd: 0,
    impairmentBegin: _n(raw.impairmentBegin),
    impairmentProvision: _n(raw.impairmentProvision),
    impairOtherIncrease: _n(raw.impairOtherIncrease),
    impairDisposal: _n(raw.impairDisposal),
    impairOtherDecrease: _n(raw.impairOtherDecrease),
    impairmentReversal: _n(raw.impairmentReversal),
    impairmentEnd: 0,
    impairmentBeginAdj: _n(raw.impairmentBeginAdj),
    impairAdjInc: _n(raw.impairAdjInc),
    impairAdjDec: _n(raw.impairAdjDec),
    auditedImpairmentBegin: 0,
    auditedImpairIncrease: 0,
    auditedImpairDecrease: 0,
    auditedImpairmentEnd: 0,
    netBegin: 0,
    netValue: 0,
    auditedNetBegin: 0,
    auditedNetEnd: 0,
    hasTitleEvidence: raw.hasTitleEvidence,
    mortgageRestricted: raw.mortgageRestricted,
  })
}

export function buildI1DetailCategorySummary(rows: I1DetailRow[]): I1DetailCategorySummary[] {
  const map = new Map<string, I1DetailCategorySummary>()
  for (const r of rows) {
    const cat = (r.category || 
    ),
})
const ieBusy = computed(() => exporting.value || importing.value)
const fileInputRef = ref<HTMLInputElement | null>(null)

function colHeaderTip(col: I1ExpenseColMeta): string {
  if (col.targetWpCode) return `计入${col.label}（${col.targetWpCode}）的摊销额`
  return `计入${col.label}的摊销额`
}

function getRowBalanceTooltip(row: I1AllocRow): string {
  if (row._isSummary || isRowBalanced(row)) return 
    ).I1AmortAllocSummary
}

// ── 动态可扩类别（Task 13 / R7.1 国企四层末 `……` 可扩位）───────────────────
//
// 🔴 源模板国企披露 sheet 每层（原价/累计摊销/减值/账面价值）末尾各有一个 `……`
// 可扩位。国企版类别是「跨四层共享」的（同一类别在四层都出现），故自定义类别
// 通过 `I1SoeCategoryMove.label` 随数据携带（default 12 类的 label 仍取自
// `I1_SOE_CATEGORIES` 常量，自定义类别的 label 存在数据里）。
//
// key 用单调计数器 `soe_custom_${seq}`，**不复用已删序号**（撞键会让旧数据串台，
// H7 已踩）；seq = max(现有全部 custom seq, 0) + 1。

const _SOE_DEFAULT_KEYS = new Set(I1_SOE_CATEGORIES.map((c) => c.key))
const _SOE_CUSTOM_KEY_RE = /^soe_custom_(\d+)$/

/** default 类别 key → label（自定义类别不在此表，label 随数据） */
const _SOE_DEFAULT_LABEL = new Map(I1_SOE_CATEGORIES.map((c) => [c.key, c.label]))

/**
 * 从 layers 数据派生「有效类别序列」= 默认 12 类 + 数据里出现的自定义类别（按 seq 升序）。
 *
 * 自定义类别的 label 取自任一层该 key 的 move.label（首个非空）。渲染 / flatten /
 * recompute 全部改用本函数，不再直接遍历 `I1_SOE_CATEGORIES`，这样自定义类别一处新增
 * 即在四层同时出现。
 */
export function resolveI1SoeCategories(
  layers: I1SoeLayerBlock[],
): Array<{ key: string; label: string; removable: boolean }> {
  const out = I1_SOE_CATEGORIES.map((c) => ({ key: c.key, label: c.label, removable: c.key !== 
    ).length,
  )

  const prepValidation = computed(() => validateI1TitlePrep(rows.value))

  const groupStats = computed(() => {
    const map = new Map<string, { count: number; netTotal: number }>()
    for (const r of rows.value) {
      const t = r.type || 
    ).trim()
        if (name && cat && !map[name]) map[name] = cat
      }
    } catch { /* ignore */ }
  }
  return map
}

export function calcI1RowAllocSum(row: I1AllocRow): number {
  return (
    _getNum(row.productionCost) +
    _getNum(row.manufacturingCost) +
    _getNum(row.sellingExpense) +
    _getNum(row.managementExpense) +
    _getNum(row.rdExpense) +
    _getNum(row.otherExpense)
  )
}

export function isI1RowBalanced(row: I1AllocRow): boolean {
  if (row._isSummary) return true
  return Math.abs(calcI1RowAllocSum(row) - _getNum(row.totalAmort)) < TOLERANCE
}

export function calcI1RowRemainder(row: I1AllocRow): number {
  return _getNum(row.totalAmort) - calcI1RowAllocSum(row)
}

function _normalizeRow(raw: any): I1AllocRow {
  return {
    rowId: raw.rowId || _genRowId(),
    name: raw.name || 
    ).trim() === name)
      return !i13 || (r.recoverableAmount <= 0 && (i13?.recoverableAmount ?? 0) <= 0)
    }),
  )

  const needTestGatePending: ComputedRef<boolean> = computed(() =>
    missingRecoverableRows.value.length > 0 || staleSyncCount.value > 0,
  )

  function getWaccWarnings(rowIndex: number): string[] {
    const row = recoverableRows.value[rowIndex]
    if (!row?.waccParams) return []
    return validateWaccParams(row.waccParams)
  }

  function buildImpairmentConclusionDraft(): string {
    const need = impairmentRows.value.filter((r) => r.needTest)
    const noNeed = impairmentRows.value.length - need.length
    const supp = impairmentSummary.value.totalSupplement
    const over = impairmentSummary.value.totalOverProvision
    const indefinite = impairmentRows.value.filter((r) => r.indefiniteLife === 
    ): I1AllocRow {
  return {
    rowId: _genRowId(),
    name,
    category,
    totalAmort,
    productionCost: 0,
    manufacturingCost: 0,
    sellingExpense: 0,
    managementExpense: 0,
    rdExpense: 0,
    otherExpense: 0,
    remark: 
    ,
          impairmentAmount: impairmentSummary.value.totalShouldProvision,
        },
      }))
    } catch { /* silent */ }
  }

  function _persistImpairment(): void {
    const supp = impairmentSummary.value.totalSupplement
    options?.onSave?.(ITEM_ID_12_ROWS, impairmentRows.value)
    options?.onSave?.(ITEM_ID_12_SUPPLEMENT, supp)
    _publishImpairmentToK11(supp)
  }

  function _persistRecoverable(): void {
    options?.onSave?.(ITEM_ID_13_ROWS, recoverableRows.value)
  }

  /**
   * 有⑧补提时切换摊销分支为含减值（I1-11），并可选回写减值金额。
   */
  function switchAmortToWithImpairment(opts?: {
    alsoPushRows?: boolean
  }): { ok: boolean; message: string; push?: ReturnType<typeof pushToAmortWithImpair> } {
    const supp = impairmentSummary.value.totalSupplement
    if (supp < 0.01 && impairmentSummary.value.totalAlreadyProvided < 0.01) {
      return { ok: false, message: 
    ,
        }
        continue
      }
      next[field] = info.amount
      next._meta![field] = {
        message: info.message,
        matchedLabel: info.matchedLabel,
      }
    }
    counterpartSnapshot.value = next
    counterpartPulledAt.value = next._pulledAt!
    onSave?.(I1_ALLOC_COUNTERPART_KEY, next)
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function persistRows(): void {
    onSave?.(I1_ALLOC_ROWS_KEY, rows.value)
    onSave?.(I1_ALLOC_TOTALS_KEY, {
      ...colTotals.value,
      sellingExpenseAmort: colTotals.value.sellingExpense,
      managementExpenseAmort: colTotals.value.managementExpense,
      rdExpenseAmort: colTotals.value.rdExpense,
      productionManufacturingAmort: colTotals.value.productionCost + colTotals.value.manufacturingCost,
      at: new Date().toISOString(),
    })
  }

  function updateCell(row: I1AllocRow, field: keyof I1AllocRow, value: unknown): void {
    if (row._isSummary) return
    ;(row as any)[field] = value
    persistRows()
  }

  function addRow(name: string): I1AllocRow {
    const totalAmort = resolvedByAsset.value.byAsset?.[name] ?? 0
    const row = _blankRow(name, totalAmort)
    rows.value.push(row)
    persistRows()
    return row
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      rows.value.splice(idx, 1)
      persistRows()
    }
  }

  /** 将各行未分配差额一键并入指定费用列 */
  function allocateAllRemaindersTo(field: I1ExpenseField): number {
    let n = 0
    for (const row of rows.value) {
      const rem = calcI1RowRemainder(row)
      if (Math.abs(rem) < TOLERANCE) continue
      ;(row as any)[field] = _getNum((row as any)[field]) + rem
      n++
    }
    if (n) persistRows()
    return n
  }

  function savePriorAssessment(consistent: I1PriorConsistency, note: string): void {
    priorConsistent.value = consistent
    priorNote.value = note
    onSave?.(I1_ALLOC_PRIOR_KEY, { consistent, note })
  }

  function publishAllocated(): void {
    const payload = {
      sheet: 
    ,
      _isSummary: true,
    }
  })

  const displayRows = computed(() => [...rows.value, summaryRow.value])

  const vsSourceDiff = computed(() => colTotals.value.allocSum - sourceAmortTotal.value)
  const isBalancedWithSource = computed(() => Math.abs(vsSourceDiff.value) < TOLERANCE)
  const unbalancedCount = computed(() => rows.value.filter((r) => !isI1RowBalanced(r)).length)

  // ─── Reconciliation ────────────────────────────────────────────────────────

  const reconciliationRows = computed<I1ReconciliationRow[]>(() => {
    const snap = counterpartSnapshot.value
    const t = colTotals.value

    // 生产成本+制造费用合并与 D5 核对（Excel 两列、对方底稿常合计）
    const d5Calculated = t.productionCost + t.manufacturingCost
    const linkedCols: Array<{
      field: I1ExpenseField | 
    ,
      beginBalance: Number(raw.beginBalance) || 0,
      increase: Number(raw.increase) || 0,
      decrease: Number(raw.decrease) || 0,
      endBalance: Number(raw.endBalance) || 0,
      unadjusted: Number(raw.unadjusted) || 0,
      aje: Number(raw.aje) || 0,
      rje: Number(raw.rje) || 0,
      audited: Number(raw.audited) || 0,
      isSubtotal: raw.isSubtotal ?? false,
      isEditable: raw.isEditable ?? true,
    }
  }

  function _buildDefaultRows(categories: string[], block: I1BlockType): I1AdjudicationRow[] {
    const prefix = block === 
    ,
      beginBalance: calcSubtotal(detail.map((r) => r.beginBalance)),
      increase: calcSubtotal(detail.map((r) => r.increase)),
      decrease: calcSubtotal(detail.map((r) => r.decrease)),
      endBalance: calcSubtotal(detail.map((r) => r.endBalance)),
      unadjusted: calcSubtotal(detail.map((r) => r.unadjusted)),
      aje: calcSubtotal(detail.map((r) => r.aje)),
      rje: calcSubtotal(detail.map((r) => r.rje)),
      audited: calcSubtotal(detail.map((r) => r.audited)),
      isSubtotal: true,
      isEditable: false,
    }
  })

  /** 无形资产净值合计 = 原值小计审定 - 摊销小计审定 - 减值小计审定 */
  const netValueAudited = computed(() =>
    calcNetValue(costSubtotal.value.audited, amortSubtotal.value.audited, impairmentSubtotal.value.audited),
  )

  const netValueBegin = computed(() =>
    calcNetValue(
      costSubtotal.value.beginBalance,
      amortSubtotal.value.beginBalance,
      impairmentSubtotal.value.beginBalance,
    ),
  )

  /** 净值行对象（用于渲染合计行） */
  const netValueRow = computed<I1AdjudicationRow>(() => ({
    rowId: 
    ,
      beginBalance: calcSubtotal(detail.map((r) => r.beginBalance)),
      increase: calcSubtotal(detail.map((r) => r.increase)),
      decrease: calcSubtotal(detail.map((r) => r.decrease)),
      endBalance: calcSubtotal(detail.map((r) => r.endBalance)),
      unadjusted: calcSubtotal(detail.map((r) => r.unadjusted)),
      aje: calcSubtotal(detail.map((r) => r.aje)),
      rje: calcSubtotal(detail.map((r) => r.rje)),
      audited: calcSubtotal(detail.map((r) => r.audited)),
      isSubtotal: true,
      isEditable: false,
    }
  })

  const amortSubtotal = computed<I1AdjudicationRow>(() => {
    const detail = amortRows.value.filter((r) => !r.isSubtotal)
    return {
      rowId: 
    ,
      beginBalance: calcSubtotal(detail.map((r) => r.beginBalance)),
      increase: calcSubtotal(detail.map((r) => r.increase)),
      decrease: calcSubtotal(detail.map((r) => r.decrease)),
      endBalance: calcSubtotal(detail.map((r) => r.endBalance)),
      unadjusted: calcSubtotal(detail.map((r) => r.unadjusted)),
      aje: calcSubtotal(detail.map((r) => r.aje)),
      rje: calcSubtotal(detail.map((r) => r.rje)),
      audited: calcSubtotal(detail.map((r) => r.audited)),
      isSubtotal: true,
      isEditable: false,
    }
  })

  const impairmentSubtotal = computed<I1AdjudicationRow>(() => {
    const detail = impairmentRows.value.filter((r) => !r.isSubtotal)
    return {
      rowId: 
    ,
      category: is.category,
      difference: isDiff,
      isBalanced: Math.abs(isDiff) < 0.01,
    })

    return results
  })

  /** 三区块勾稽总体是否平衡 */
  const isAllReconciled = computed(() =>
    reconciliationResults.value.every((r) => r.isBalanced),
  )

  // ─── Computed: TB取数行 + 差异行（Req 2.9）────────────────────────────────

  /** TB取数行：从 tbData 读取各科目未审数/审定数 */
  const tbRow = computed(() => {
    const tb = options?.tbData?.value ?? {
      unadjusted1701: 0, audited1701: 0,
      unadjusted1702: 0, audited1702: 0,
      unadjusted1703: 0, audited1703: 0,
    }
    return {
      cost: { unadjusted: tb.unadjusted1701, audited: tb.audited1701 },
      amort: { unadjusted: tb.unadjusted1702, audited: tb.audited1702 },
      impairment: { unadjusted: tb.unadjusted1703, audited: tb.audited1703 },
    }
  })

  /** 差异行：审定数 vs TB已有审定数 */
  const differenceRows = computed<I1DifferenceRow[]>(() => {
    const tb = options?.tbData?.value ?? {
      unadjusted1701: 0, audited1701: 0,
      unadjusted1702: 0, audited1702: 0,
      unadjusted1703: 0, audited1703: 0,
    }
    const costAudited = costSubtotal.value.audited
    const amortAudited = amortSubtotal.value.audited
    const impairAudited = impairmentSubtotal.value.audited
    return [
      { label: 
    ,
      isSubtotal: true,
    })
    return detail
  })

  const significantNetChanges = computed(() =>
    netRows.value.filter((r) => !r.isSubtotal && r.isSignificant),
  )

  // ─── Computed: 三角勾稽校验（每行+三区块小计） ─────────────────────────────

  /**
   * 三角勾稽校验：
   * - 原值(1701资产类)：期末 = 期初 + 增加 - 减少
   * - 摊销(1702备抵类)：期末 = 期初 + 贷方(增加) - 借方(减少)
   * - 减值(1703备抵类)：期末 = 期初 + 贷方(增加) - 借方(减少)
   *
   * 注意：对备抵类，increase列即贷方发生(计提/增加)，decrease列即借方发生(转回/减少)
   * 因此三角勾稽公式统一为：end - (begin + increase - decrease) === 0
   */
  const reconciliationResults = computed<I1ReconciliationResult[]>(() => {
    const results: I1ReconciliationResult[] = []

    // 原值区块各行校验
    for (const row of costRows.value.filter((r) => !r.isSubtotal)) {
      const diff = calcTriangleReconciliation(row.beginBalance, row.increase, row.decrease, row.endBalance)
      results.push({
        rowId: row.rowId,
        layer: 
    ,
      totals: colTotals.value,
      销售费用摊销: colTotals.value.sellingExpense,
      管理费用摊销: colTotals.value.managementExpense,
      研发费用摊销: colTotals.value.rdExpense,
      生产成本摊销: colTotals.value.productionCost,
      制造费用摊销: colTotals.value.manufacturingCost,
      at: new Date().toISOString(),
    }
    onSave?.(I1_ALLOC_TOTALS_KEY, payload)
    onPublishEvent?.(
    ,
      })
      rows.value.push(newRow)
      activeRowIndex.value = rows.value.length - 1
      _persist()
      return newRow
    } catch {
      return null
    }
  }

  function removeRow(rowIndex: number): void {
    if (rowIndex < 0 || rowIndex >= rows.value.length) return
    rows.value.splice(rowIndex, 1)
    if (activeRowIndex.value >= rows.value.length) {
      activeRowIndex.value = rows.value.length - 1
    }
    _persist()
  }

  function moveRowUp(rowIndex: number): void {
    if (rowIndex <= 0 || rowIndex >= rows.value.length) return
    const t = rows.value[rowIndex]
    rows.value[rowIndex] = rows.value[rowIndex - 1]
    rows.value[rowIndex - 1] = t
    activeRowIndex.value = rowIndex - 1
    _persist()
  }

  function moveRowDown(rowIndex: number): void {
    if (rowIndex < 0 || rowIndex >= rows.value.length - 1) return
    const t = rows.value[rowIndex]
    rows.value[rowIndex] = rows.value[rowIndex + 1]
    rows.value[rowIndex + 1] = t
    activeRowIndex.value = rowIndex + 1
    _persist()
  }

  function importRows(importedRows: Partial<I1DetailRow>[]): void {
    rows.value = importedRows.map((raw) => normalizeI1DetailRow(raw))
    activeRowIndex.value = rows.value.length > 0 ? 0 : -1
    _persist()
  }

  function exportRows(): I1DetailRow[] {
    return [...rows.value]
  }

  function fillConclusionDraft(): string {
    return buildI1DetailConclusionDraft(rows.value, summaryRow.value, crossValidation.value)
  }

  // ─── Tab 列配置（对齐 Excel 分区）──────────────────────────────────────────

  const basicColumns = [
    { key: 
    ,
      生产成本: state.amortAlloc.productionCost,
      制造费用: state.amortAlloc.manufacturing,
      销售费用: state.amortAlloc.selling,
      管理费用: state.amortAlloc.management,
      研发费用: state.amortAlloc.rd,
      其他: state.amortAlloc.other,
      合计: state.amortAlloc.total,
    }]
  }
  return out
}

export function buildI1SoeSubTableData(state: I1SoeSyncSnapshot): Record<string, Record<string, unknown>[]> {
  const movementRows: Record<string, unknown>[] = []
  for (const flat of flattenI1SoeMovement(state.layers)) {
    const meta = I1_SOE_LAYER_META[flat.layer]
    movementRows.push({
      label: flat.label,
      begin: flat.begin,
      increase: meta.movementNa || flat.allNa ? null : flat.increase,
      decrease: meta.movementNa || flat.allNa ? null : flat.decrease,
      end: flat.end,
      is_total: flat.kind === 
    ,
    beginBalance: netValueBegin.value,
    increase: calcNetValue(costSubtotal.value.increase, amortSubtotal.value.increase, impairmentSubtotal.value.increase),
    decrease: calcNetValue(costSubtotal.value.decrease, amortSubtotal.value.decrease, impairmentSubtotal.value.decrease),
    endBalance: calcNetValue(costSubtotal.value.endBalance, amortSubtotal.value.endBalance, impairmentSubtotal.value.endBalance),
    unadjusted: calcNetValue(costSubtotal.value.unadjusted, amortSubtotal.value.unadjusted, impairmentSubtotal.value.unadjusted),
    aje: calcNetValue(costSubtotal.value.aje, amortSubtotal.value.aje, impairmentSubtotal.value.aje),
    rje: calcNetValue(costSubtotal.value.rje, amortSubtotal.value.rje, impairmentSubtotal.value.rje),
    audited: netValueAudited.value,
    isSubtotal: true,
    isEditable: false,
  }))

  /** 四、净值：按分类派生 + 变动额/率（对齐 Excel） */
  const netRows = computed<I1NetValueRow[]>(() => {
    const byCat = (rows: I1AdjudicationRow[]) => {
      const m = new Map<string, I1AdjudicationRow>()
      for (const r of rows.filter((x) => !x.isSubtotal)) m.set(r.category, r)
      return m
    }
    const costs = byCat(costRows.value)
    const amorts = byCat(amortRows.value)
    const impairs = byCat(impairmentRows.value)
    const cats = [
      ...new Set([
        ...costs.keys(),
        ...amorts.keys(),
        ...impairs.keys(),
        ...DEFAULT_COST_CATEGORIES,
      ]),
    ]

    const detail: I1NetValueRow[] = cats.map((cat) => {
      const c = costs.get(cat)
      const a = amorts.get(cat)
      const i = impairs.get(cat)
      const beginNet = calcNetValue(c?.beginBalance ?? 0, a?.beginBalance ?? 0, i?.beginBalance ?? 0)
      const endNet = calcNetValue(c?.audited ?? 0, a?.audited ?? 0, i?.audited ?? 0)
      const changeAmount = endNet - beginNet
      const changeRate = calcChangeRate(endNet, beginNet)
      return {
        rowId: `row-n-${cat}`,
        category: cat,
        beginNet,
        endNet,
        changeAmount,
        changeRate,
        isSignificant: changeRate != null && Math.abs(changeRate) >= I1_CHANGE_RATE_THRESHOLD,
        explanation: changeExplanations.value[cat] || 
    ,
    rows: impairmentDisplayRows.value.map(toExcel6Row),
  },
])

// ─── Display Rows (detail + subtotal) ────────────────────────────────────────

const costDisplayRows = computed<I1AdjudicationRow[]>(() => {
  const detail = costRows.value.filter((r) => !r.isSubtotal)
  return [...detail, costSubtotal.value]
})

const amortDisplayRows = computed<I1AdjudicationRow[]>(() => {
  const detail = amortRows.value.filter((r) => !r.isSubtotal)
  return [...detail, amortSubtotal.value]
})

const impairmentDisplayRows = computed<I1AdjudicationRow[]>(() => {
  const detail = impairmentRows.value.filter((r) => !r.isSubtotal)
  return [...detail, impairmentSubtotal.value]
})

// ─── Cross Validation Warning ────────────────────────────────────────────────

const hasCrossWarning = computed(() => {
  const cv = crossValidation.value
  return cv.hasCostWarning || cv.hasAmortWarning || cv.hasImpairWarning
})

const crossWarningCount = computed(() => {
  const cv = crossValidation.value
  let count = 0
  if (cv.hasCostWarning) count++
  if (cv.hasAmortWarning) count++
  if (cv.hasImpairWarning) count++
  return count
})

// ─── Reconciliation Helpers ──────────────────────────────────────────────────

function isRowBalanced(rowId: string): boolean {
  const result = reconciliationResults.value.find((r) => r.rowId === rowId)
  return result ? result.isBalanced : true
}

function getReconciliationTooltip(rowId: string): string {
  const result = reconciliationResults.value.find((r) => r.rowId === rowId)
  if (!result || result.isBalanced) return 
    ,
    salesAgreementPrice: fv.salesAgreementPrice,
    salesAgreementNote: fv.salesAgreementNote,
    activeMarketPrice: fv.activeMarketPrice,
    activeMarketNote: fv.activeMarketNote,
    estimatedPrice: fv.estimatedPrice,
    estimatedNote: fv.estimatedNote,
    legalFees: fv.legalFees,
    relatedTaxes: fv.relatedTaxes,
    transportCosts: fv.transportCosts,
    directCosts: fv.directCosts,
    otherCosts: fv.otherCosts,
    auditNote: fv.auditNote,
  }
}

export function resolveI1FairValue(fv: I1FairValueDisposal): { value: number; source: string } {
  return resolveFairValue(toH4Fv(fv))
}

export function calcI1DisposalTotal(fv: I1FairValueDisposal): number {
  return calcDisposalTotal(toH4Fv(fv))
}

/** 公允净额 = 选用公允 − 处置费用合计（Excel N11） */
export function calcFairValueNet(fv: I1FairValueDisposal): number {
  const { value } = resolveI1FairValue(fv)
  return value - calcI1DisposalTotal(fv)
}

/**
 * 是否已填写公允明细（用于兼容旧数据：仅有 flat fairValueLessDisposal）
 */
export function hasFvDetail(fv: I1FairValueDisposal | undefined | null): boolean {
  if (!fv) return false
  return (
    fv.salesAgreementPrice > 0
    || fv.activeMarketPrice > 0
    || fv.estimatedPrice > 0
    || calcI1DisposalTotal(fv) > 0
  )
}

export function normalizeFvDisposal(raw: any): I1FairValueDisposal {
  const d = defaultFvDisposal()
  if (!raw || typeof raw !== 
    ,
    }
  }

  // ─── Init: watch allResponses 加载数据 ─────────────────────────────────────

  watch(allResponses, () => {
    _loadImpairmentRows()
    _loadRecoverableRows()
  }, { immediate: true })

  /**
   * 核对 I1-12 ⑧应补提 vs K11 无形资产减值金额（对齐 H8 reconcileWithK11）。
   */
  async function reconcileWithK11(projectId: string): Promise<I1K11ReconcileResult> {
    const i12Supplement = impairmentSummary.value.totalSupplement
    const empty: I1K11ReconcileResult = {
      i12Supplement,
      k11Amount: null,
      diff: null,
      isMatch: true,
      source: 
    ,
    }))
  }
  return out
}

export function buildI1TitleConclusionDraft(rows: I1TitleCheckRow[]): string {
  const total = rows.length
  const checked = rows.filter((r) => r.certNo || r.verifyMethod).length
  const holderDiff = rows.filter((r) => r.holderConsistent === 
    ,
  htmlData: computed(() => props.htmlData),
  rows: i1SeedRows,
  isReadonly: computed(() => Boolean(props.isReadonly)),
  // 读值须按 block 定位 —— 三段行键在各自数组内唯一，但跨段可能重名
  readCell: (cell) => {
    for (const list of Object.values(I1_SEED_BLOCK_ROWS)) {
      const row = list.value.find((r) => r.rowId === cell.rowKey)
      if (!row) continue
      const v = (row as unknown as Record<string, unknown>)[cell.field]
      return v == null || v === 0 ? null : Number(v)
    }
    return null
  },
  applyCell: (cell, block) => {
    if (!block) return // 段键反查失败 ⇒ 不猜 block（宁缺勿造，避免写错段）
    updateCell(block as I1BlockType, cell.rowKey, cell.field as keyof I1AdjudicationRow, cell.amount)
  },
})

// ─── 从集中登记带入调整（三科目：1701原值[资产借方] / 1702累计摊销[备抵credit] / 1703减值准备[备抵credit]；带入期末 AJE/RJE） ───
const bringInCostRows = computed(() =>
  costRows.value.filter((r) => !r.isSubtotal).map((r) => ({ rowKey: r.rowId, name: r.category, aje: r.aje, rje: r.rje })),
)
const bringInAmortRows = computed(() =>
  amortRows.value.filter((r) => !r.isSubtotal).map((r) => ({ rowKey: r.rowId, name: r.category, aje: r.aje, rje: r.rje })),
)
const bringInImpairRows = computed(() =>
  impairmentRows.value.filter((r) => !r.isSubtotal).map((r) => ({ rowKey: r.rowId, name: r.category, aje: r.aje, rje: r.rje })),
)
const {
  adjPull: adjPullCost,
  visible: bringInCostVisible,
  rowOptions: bringInCostRowOptions,
  open: openBringInCost,
  apply: onBringInCostApply,
} = useAdjudicationBringIn({
  projectId: computed(() => props.projectId) as any,
  year: useAuditContext().year as any,
  subjectPrefix: 
    ,
  }
}

/** 从 I1-10 / I1-11 行聚合按资产摊销额 */
export function parseAmortizationByAsset(allResponses: Map<string, any>): {
  byAsset: Record<string, number>
  total: number
  sourceSheet: 
    ,
  }
}

export function defaultWaccParams(): I1WaccParams {
  return {
    taxRate: 25,
    totalDebt: 0,
    totalEquity: 0,
    costOfDebt: 0,
    riskFreeRate: 0,
    beta: 1,
    marketReturn: 0,
  }
}

function toH4Fv(fv: I1FairValueDisposal): H4FairValueDisposal {
  return {
    materialName: 
    ,
] as const

export interface I1AdditionSummary {
  checkedTotal: number
  periodTotal: number
  /** 检查比例 %；periodTotal<=0 时为 null（防 DIV/0） */
  coverageRate: number | null
  financeBookTotal: number
  financeCostTotal: number
  comboAmountTotal: number
  anomalyCount: number
  checkedCount: number
  relatedPartyCount: number
  fundRiskCount: number
  /** 外购：入账金额与发票不含税差 >1 */
  vatMismatchCount: number
  traceCount: number
  traceUnrecordedCount: number
}

/** 检查比例默认告警阈值（%） */
export const I1_ADDITION_DEFAULT_COVERAGE_THRESHOLD = 20

/** 宽表列组（精简视图按取得方式显示） */
export type I1MethodColGroup = 
    ,
] as const
const I1_ALLOC_TOTALS_KEY = 
    ,
} as const

export function i1ListedCellValue(map: MovementCellMap, def: MovementRowDef, catKey: string): number {
  return cellValue(map, def, catKey, I1_LISTED_MOVEMENT_ROWS)
}

export function i1ListedTotalCellValue(
  map: MovementCellMap,
  def: MovementRowDef,
  categories: readonly H1ListedCategory[],
): number {
  if (def.kind === 
    , () => {})

const allResponsesRef = computed(() => props.allResponses)

const {
  currentRows,
  summaryRow,
  periodBegin,
  periodEnd,
  amortReconcile,
  recalcAll,
  syncFromDetail,
  syncFromUsefulLife,
  syncFromImpairment,
  updateRowField,
  setPeriod,
  addRow,
  removeRow,
  switchBranch,
  exportXlsx,
  importXlsx,
} = useI1Amortization(toRef(props, 
    , () => {})

const allResponsesRef = computed(() => props.allResponses)

const {
  impairmentRows,
  impairmentSummary,
  categorySummary,
  prepValidation,
  highlightedRowIds,
  syncChecks,
  staleSyncCount,
  missingRecoverableRows,
  needTestGatePending,
  addImpairmentRow,
  removeImpairmentRow,
  updateImpairmentField,
  seedFromDetail,
  syncFromUsefulLife,
  seedFromImpairment,
  linkRecoverableToImpairment,
  pushToAmortWithImpair,
  switchAmortToWithImpairment,
  publishToK11,
  reconcileWithK11,
  k11Reconcile,
  buildImpairmentConclusionDraft,
  assertCanConclude,
  exportImpairmentXlsx,
  importImpairmentXlsx,
} = useI1Impairment(
  toRef(props, 
    , () => {})
const allResponsesRef = computed(() => props.allResponses)

const {
  currentRows,
  summaryRow,
  periodBegin,
  periodEnd,
  amortReconcile,
  recalcAll,
  syncFromDetail,
  syncFromUsefulLife,
  updateRowField,
  setPeriod,
  addRow,
  removeRow,
  switchBranch,
  exportXlsx,
  importXlsx,
} = useI1Amortization(toRef(props, 
    , () => {})
const allResponsesRef = computed(() => props.allResponses)

const {
  rows,
  traceRows,
  periodTotal,
  periodManual,
  linkedPeriodTotal,
  summary,
  coverageThreshold,
  coverageLow,
  pendingI2Amount,
  setPeriodTotal,
  setCoverageThreshold,
  syncPeriodFromLinked,
  seedFromDetail,
  seedFromI2Transfer,
  addRow,
  removeRow,
  updateCell,
  addTraceRow,
  removeTraceRow,
  updateTraceCell,
  seedTraceFromCheck,
  flushPersist,
  exportXlsx,
  importXlsx,
} = useI1AdditionCheck(toRef(props, 
    , amortIncreaseTotal)
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options?.onSave?.(`${ITEM_PREFIX}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options?.onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion)
  }

  function saveQualitativeNotes(): void {
    options?.onSave?.(QUAL_KEY, { ...qualitativeNotes.value })
  }

  function setNetExplanation(category: string, text: string): void {
    changeExplanations.value = { ...changeExplanations.value, [category]: text }
    options?.onSave?.(NET_EXPLAIN_KEY, { ...changeExplanations.value })
  }

  /** 行级变动额/率（期末审定 vs 期初，对齐 Excel 比较列） */
  function rowChange(row: I1AdjudicationRow): { amount: number; rate: number | null; significant: boolean } {
    const amount = row.audited - row.beginBalance
    const rate = calcChangeRate(row.audited, row.beginBalance)
    return {
      amount,
      rate,
      significant: rate != null && Math.abs(rate) >= I1_CHANGE_RATE_THRESHOLD,
    }
  }

/** 从 I1-2 按分类聚合带入期初/增加/减少/期末/未审 */
  /**
   * 从 I1-2 按分类聚合带入期初/增加/减少/期末/未审。
   * mode=book：写入未审数，保留已有 AJE/RJE（留给 I1-3）。
   * mode=full：写入明细审定数并清零 AJE/RJE。
   */
  function fillFromDetail(mode: I1FillMode = 
    , amortSubtotal.value.increase)

    _emitAdjudicated()
  }

  // ─── 显式发布到试算表（显式确认门，复刻 D2/D4-1 范式） ────────────────────────

  /**
   * 确认发布审定数到试算表（多科目 1701 原值 / 1702 累计摊销 / 1703 减值准备）。
   *
   * spec: tb-writeback-explicit-publish-gate Task 13 / Req 2,5。
   * 二次确认（中文）→ 保存明细 → 单次 `POST /workpapers/{wpId}/audit-determination/publish-to-tb`
   * （审定表 sheet 名 I1-1 + writeback_rows 三科目预算行，balance 口径，单次原子发布）。
   * 后端校验发布权限、发 publish_confirmed=True + token → 回写 handler 幂等回写
   * trial_balance。用户取消 → 无任何副作用（不写 TB、不 emit）。
   */
  async function publishToTb(): Promise<void> {
    if (publishing.value) return

    try {
      await ElMessageBox.confirm(
        
    , audited: impairAudited, tbAmount: tb.unadjusted1703, difference: impairAudited - tb.unadjusted1703 },
    ]
  })

  // ─── Computed: 交叉验证 I1-2 明细表（Req 2.4-2.7）─────────────────────────

  const crossValidation = computed(() => {
    const costFromDetail = options?.crossSheetCostAudited?.value ?? 0
    const amortFromDetail = options?.crossSheetAmortAudited?.value ?? 0
    const impairFromDetail = options?.crossSheetImpairAudited?.value ?? 0
    const costDiff = costSubtotal.value.audited - costFromDetail
    const amortDiff = amortSubtotal.value.audited - amortFromDetail
    const impairDiff = impairmentSubtotal.value.audited - impairFromDetail
    return {
      costDiff,
      amortDiff,
      impairDiff,
      hasCostWarning: Math.abs(costDiff) > 0.01,
      hasAmortWarning: Math.abs(amortDiff) > 0.01,
      hasImpairWarning: Math.abs(impairDiff) > 0.01,
    }
  })

  // ─── updateCell ────────────────────────────────────────────────────────────

  /**
   * 更新审定表某行某列值，自动重算公式列。
   * block: 
    , costIncreaseTotal)
    // 摊销本期增加（贷方计提）→ I1-10/11 / I1-9 勾稽
    const amortIncreaseTotal = amortSubtotal.value.increase
    save(`${ITEM_PREFIX}-amort-increase-total`, amortIncreaseTotal)
    save(
    , costSubtotal.value.increase)
    // 摊销本期增加（贷方计提）合计 → I1-10/11 勾稽
    options?.onSave?.(`${ITEM_PREFIX}-amort-increase-total`, amortSubtotal.value.increase)
    options?.onSave?.(
    , count: 0 }
    }

    const kept = {
      noteRdRatio: noteRdRatio.value,
      noteIndefinite: noteIndefinite.value,
      noteMortgage: noteMortgage.value,
      noteImpairment: noteImpairment.value,
      noteSale: noteSale.value,
      noteImportant: noteImportant.value,
      noteDataResource: noteDataResource.value,
    }

    type Agg = Record<string, number>
    const make = (): Agg => ({})
    const add = (bag: Agg, key: string, v: number) => { bag[key] = (bag[key] || 0) + v }

    const costBegin = make()
    const costInc: Record<string, Agg> = {}
    const costDec: Record<string, Agg> = {}
    const amortBegin = make()
    const amortProv = make()
    const amortOtherInc = make()
    const amortDisp = make()
    const amortOtherDec = make()
    const impBegin = make()
    const impProv = make()
    const impOtherInc = make()
    const impDisp = make()
    const impOtherDec = make()

    let rdCostEnd = 0
    let totalCostEnd = 0
    let mortgaged = 0
    const indefiniteNames: string[] = []
    const titleSeed: I1TitleCertRow[] = []

    for (const r of detail) {
      const cat = mapToI1ListedCategoryKey(String(r.category || r.name || 
    , itemId, value),
  },
)

// ─── 从四表库带入未审数（消费 render 的 adjudication_prefill，按类别名匹配行） ───
//
// 🔴 改造前后端每次 render 都算并下发 `adjudication_prefill`（I1 走 category 模式：
//    三段 × 11 类），而前端**零消费方** —— 与 H 循环踩过的 dead output 同型。
//
// 🔴 I1 是唯一的三段循环，`updateCell(block, rowId, field, value)` 是**四参**：
//    三段的 rowKey+field 完全相同（都是 `unadjusted`），只有 block 能区分 ——
//    漏传 block 会让后两段静默覆盖第一段。block 由 `blockOf` 给出
//    （后端段键 `amortization` → 前端 `amort` 的翻译在 iCycleAdjudicationSeed 里）。
const I1_SEED_BLOCK_ROWS: Record<string, ComputedRef<I1AdjudicationRow[]>> = {
  cost: costRows,
  amort: amortRows,
  impairment: impairmentRows,
}

/** 三段行合并成 seed 的行集；跳过小计行（不该被带入覆盖） */
const i1SeedRows = computed(() => {
  const out: Array<{ rowId: string; label: string }> = []
  for (const list of Object.values(I1_SEED_BLOCK_ROWS)) {
    for (const r of list.value) {
      if (r.isSubtotal) continue
      out.push({ rowId: r.rowId, label: String(r.category ?? 
    , model: noteTitle, placeholder: I1_SOE_GUIDANCE.title },
]

function layerTitle(layer: I1SoeLayer) {
  return I1_SOE_LAYER_META[layer].title
}
function layerMeta(layer: I1SoeLayer) {
  return I1_SOE_LAYER_META[layer]
}

function blockRows(block: I1SoeLayerBlock) {
  const meta = I1_SOE_LAYER_META[block.layer]
  const tot = layerTotal(block)
  const rows: Array<{
    kind: 
    , payload)
  }

  function fmtPercent(row: I1AllocRow): string {
    const totalAll = summaryRow.value.totalAmort
    if (!totalAll) return 
    , rowKey, field, value),
  totalAudited: () => impairmentSubtotal.value.audited,
})

const { adjustmentNets } = useI1CrossSheet(toRef(props, 
    , { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `本期摊销费用合计 ${fmt(a.total)} 元，其中：生产成本 ${fmt(a.productionCost)}、制造费用 ${fmt(a.manufacturing)}、销售费用 ${fmt(a.selling)}、管理费用 ${fmt(a.management)}、研发费用 ${fmt(a.rd)}、其他 ${fmt(a.other)}（来源 I1-9）。`
}

/** 上市分类预设：精简（对齐 note_template 表头）/ 全量（对齐 Excel） */
export const I1_LISTED_COMPACT_CATEGORIES: readonly I1ListedCategory[] = [
  { key: 
    , 合计: bookBegin, is_total: true },
  ]
}

export function readI1AdjAudited(map: Map<string, any>): { cost: number; amort: number; impair: number } {
  const read = (key: string) => {
    const item = map.get(key)
    if (!item) return 0
    const raw = item.remark ?? item.conclusion
    return num(raw)
  }
  return {
    cost: read(
    : 8000, ... }
   * total: 所有资产本期摊销之和
   *
   * I1-9 摊销分配表校验：各行摊销总额应来自此处 byAsset 对应值。
   * I1-9 底部合计行 = total（与摊销测算表合计交叉验证）。
   */
  const amortizationForAlloc: ComputedRef<I1AmortizationForAlloc> = computed(() => {
    const byAsset: Record<string, number> = {}
    let total = 0

    for (const row of amortizationRows.value) {
      const assetName = row.name || 
    : [itemId: string, value: any]
}>()

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  costRows,
  amortRows,
  impairmentRows,
  auditNote,
  auditConclusion,
  qualitativeNotes,
  costSubtotal,
  amortSubtotal,
  impairmentSubtotal,
  netValueRow,
  netValueAudited,
  netValueBegin,
  netRows,
  reconciliationResults,
  differenceRows,
  crossValidation,
  isAllReconciled,
  significantNetChanges,
  updateCell,
  saveAdjudication,
  publishToTb,
  publishing,
  saveNote,
  saveConclusion,
  saveQualitativeNotes,
  setNetExplanation,
  fillFromDetail,
  rowChange,
  applyConclusionTemplate,
  draftFluctuationNote,
  draftIndefiniteLifeNote,
  syncAjeRjeFromI13,
  CHANGE_RATE_THRESHOLD,
} = useI1Adjudication(
  toRef(props, 
    >
        <summary>编制提示</summary>
        <ul>
          <li>三科目三角勾稽：<strong>账面净值 = 原值(1701) − 累计摊销(1702) − 减值准备(1703)</strong>；1701 资产借方(期末=期初+借−贷)，1702/1703 备抵贷方(期末=期初+贷−借)</li>
          <li>推荐工作流：I1A 程序 → I1-2 明细 → I1-4/7/8 政策·寿命·权属 → I1-9 分配 + I1-10/11 摊销测算 → I1-12/13 减值 → I1-5/6 增减 → I1-3 调整回写 I1-1 → 附注披露</li>
          <li>摊销测算双分支：I1-10（不含减值）与 I1-11（含减值）二选一，结果与 I1-9 分配去向配平</li>
          <li>审定合计回写 TB(1701/1702/1703) 并驱动附注披露；各表填妥
    >
      <summary>编制提示</summary>
      <ul>
        <li>优先「从 I1-2 带入」名称/寿命月数/净值，再按 Excel 三路径补齐判定字段</li>
        <li>法定权利适用时填规定年限与已确定寿命；续约适用时填续约计入年限</li>
        <li>无法定年限时勾选是否估计及是否合理；不确定则填管理层判断依据并完成询问表</li>
        <li>原始寿命填 0 或「寿命不确定=是」→ 不摊销，联动 I1-12 减值测试</li>
        <li>本期变更=是须说明原因（CAS28）；发布不确定清单供 I1-12 取数</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang=
    >
      <summary>编制提示</summary>
      <ul>
        <li>摊销总额列来自 I1-10/I1-11 本期摊销合计，按资产名称自动同步，不可手改</li>
        <li>横向：各费用列之和必须等于该行摊销总额，否则红色警示；可用「差额一键计入」快速配平</li>
        <li>纵向：生产成本/制造费用→D5、销售费用→K8、管理费用→K9、研发费用→I6</li>
        <li>点「刷新对方底稿数」从对方明细「无形资产摊销」行反向回填；取不到时可手工覆盖</li>
        <li>点「回写 D5/K8/K9/I6」或「发布摊销分配」时，将列合计写入对方底稿明细（checklist 持久化；EventBus 仅作在线即时通知）</li>
        <li>评估分配方法是否合理且与上期一致；办公软件→管理费用，生产相关专利→生产成本/制造费用，自研→研发费用</li>
        <li>发布后写出 I1-9-alloc-totals，供对方底稿 =WP(
    >
      <summary>编制提示（CAS8 / 对齐 Excel I1-13）</summary>
      <ul>
        <li>「从 I1-12 建组」仅拉取须测试且有账面的行；测算完成后「联动回写 I1-12」写入③公允净额、④DCF 现值并重算⑤⑥⑧⑨</li>
        <li>可收回金额 = MAX(公允净额, 使用价值)；折现率默认税前；现金流与折现率口径须一致</li>
        <li>公允取值优先：销售协议 → 活跃市场 → 估计；处置费用为直接费用合计</li>
        <li>敏感性：折现率±1%、增长率±0.5%；结论草稿可一键填入审计结论</li>
      </ul>
      <ol>
        <li>可收回金额 = MAX(公允价值−处置费用净额, 预计未来现金流量现值)。源模板 N23=MAX(N14,N20)。</li>
        <li>公允净额 N = IF(销售协议&gt;0,协议,IF(活跃市场&gt;0,市场,估计)) − Σ处置费用（法律/税费/搬运/直接/其他）。</li>
        <li>DCF：PV = Σ(CF_t×1/(1+r)^t) + TV/(1+r)^n；TV = CF_n×(1+g)/(r−g)，要求 r&gt;g。</li>
        <li>折现率优先 WACC 税前；未填 D/E 时回退手工折现率。Rm、Kd、Rf 均按百分比填写（如市场回报 8 表示 8%）。</li>
        <li>永续增长率通常为 0 或负；大于 0 须填写依据，且不应超过行业/经济体长期增长率。</li>
        <li>「从 I1-12 建组」按须测试且有账面的行自动建测算项；「联动回写 I1-12」按同名写入③公允净额、④DCF 现值并重算⑤⑥⑧⑨。</li>
        <li>无形资产减值损失一经确认，以后期间不得转回。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang=
    >
      <summary>编制提示（对齐 Excel I1-8）</summary>
      <ol>
        <li>净值公式 J = G − H − I（原值 − 累计摊销 − 减值准备）；源表「累计折旧」按无形资产改为摊销。</li>
        <li>权证记载：编号、权利人、登记日、权利起止、复印件索引；优先查验原件。</li>
        <li>「从 I1-2 带入」自动填原值/摊销/减值；按同名更新已有行。</li>
        <li>填写被审计单位名称后，可自动勾稽权利人是否一致。</li>
        <li>抵押受限=是时须填抵押价值与性质；到期/临期须关注续展。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang=
    >
      <summary>编制说明</summary>
      <ol>
        <li>净值 E = 原值 − 累计摊销 − 减值；清理净损益 I = 清理收入 − 清理费用 − 净值。</li>
        <li>核销/报废重点查审批与结转；出售/转让重点查手续完备与协议公允。</li>
        <li>房地产开发：待售房屋占用的土地使用权应转入存货/开发成本；自建厂房土地与建筑物分别摊销折旧。</li>
        <li>「从 I1-2 带入减少」按原值减少金额识别；抽凭可补凭证号与日期。</li>
        <li>点「发布联动 H10」按行写入 disposal:source-updated（sourceWp=I1 → intangible_disposal）。</li>
        <li>本表将 Excel 上下两区合并为一行，避免资产名称双表不同步。</li>
      </ol>
    </details>

    <el-dialog
      v-model=
    >
      <summary>编制说明（摘自源模板）</summary>
      <ul>
        <li>结构：原值 → 累计摊销 → 减值准备 → 净值（含变动额/率）→ TB 差异 → 说明事项 → 结论</li>
        <li>「从 I1-2 带入」：未审模式保留 AJE/RJE；审定覆盖写入明细审定并清零调整；审定=未审+AJE+RJE</li>
        <li>净值变动率≥{{ CHANGE_RATE_THRESHOLD }}% 须在说明事项(1)或分类说明中解释</li>
        <li>结论模板：A 无异常确认 / B 调整后确认 / C 重大未调整或范围受限不能确认</li>
        <li>「确认审定」回写 TB 1701/1702/1703 并发布 substantive:adjudicated</li>
        <li>「带入调整(原值/摊销/减值)」：从集中登记按科目 1701/1702/1703 拉取调整分录，逐笔分配到各分类行的 AJE/RJE，带入后审定数自动更新并联动附注</li>
      </ul>
    </details>

    <AdjudicationBringInDialog
      v-model=
    I1-10-period-amort-total
    I1-12-supplement-total
    I1-5-period-total
    I1-9-alloc-totals
    I1-adj-amort-increase-total
    I1-adj-cost-increase-total
    ]

  for (const cat of params.categories) {
    const begin = num(params.movement.cost_begin?.[cat.key])
    const incTotal = costIncKeys.reduce((s, k) => s + num(params.movement[k]?.[cat.key]), 0)
    const decTotal = costDecKeys.reduce((s, k) => s + num(params.movement[k]?.[cat.key]), 0)
    if (Math.abs(incTotal) + Math.abs(decTotal) + Math.abs(begin) < 0.005) continue
    // 有增加金额但方式全空（仅靠 ellipsis/other 也不强制）——若 begin+end 有值但无增减细项则跳过
    if (incTotal > 0.005) {
      const named = costIncKeys.slice(0, 4).reduce((s, k) => s + num(params.movement[k]?.[cat.key]), 0)
      if (named < 0.005 && num(params.movement.cost_inc_ellipsis?.[cat.key]) < 0.005) {
        warnings.push(`「${cat.label}」有原值增加但未填购置/研发/合并/其他方式`)
      }
    }
    const bookEndDef = I1_LISTED_MOVEMENT_ROWS.find((r) => r.key === 
    ] = i1ListedTotalCellValue(state.movement, def, cats)
    rows.push(row)
  }

  const importantRows = (state.importantRows || [])
    .filter((r) => r.name || r.bookValue)
    .map((r) => ({
      label: r.name,
      账面价值: r.bookValue,
      剩余摊销期限: r.remainingAmortMonths,
    }))

  const titleRows = (state.titleCertRows || [])
    .filter((r) => r.name || r.bookValue)
    .map((r) => ({
      label: r.name,
      账面价值: r.bookValue,
      未办妥产权证书原因: r.reason,
    }))

  const out: Record<string, Record<string, unknown>[]> = {
    [I1_LISTED_SUBTABLE.movement]: rows,
    _note_texts: [
      { section: 
    ` 的行、
 * 金额取「抵押价值」`mortgageValue`，与 `useI1TitleCheck.totalMortgage` 同口径）。
 * 该表**只有期末口径** → soe 单表本就只有期末账面价值列，天然对齐。
 */
const syncRestrictedAssets = useRestrictedAssetsSync({
  owner: 
    ` 的行、
 * 金额取「抵押价值」`mortgageValue`，与 `useI1TitleCheck.totalMortgage` 同口径）。
 * 该表**只有期末口径** → 只推主表、不推「（续：上年年末）」。
 *
 * 🔴 与本页「未办妥权属证书的土地使用权」是**两种不同披露**：权属证书未办妥 ≠
 * 所有权/使用权受到限制，故 `titleCertRows` 绝不进受限资产表。
 */
const syncRestrictedAssets = useRestrictedAssetsSync({
  owner: 
    `应补提减值准备 ${fmtAmt(impairmentSummary.totalSupplement)} 元；保存时已自动推送 K11。请点「切换 I1-11 含减值」后重算摊销。`
    `测算本期合计 ${fmtAmt(amortReconcile.periodAmortTotal)} 与 I1-1 摊销本期增加 ${fmtAmt(amortReconcile.adjudicatedProvision)} 差异 ${fmtAmt(amortReconcile.vsAdjDiff)}`
    }），抵押相关账面约 ${total.toFixed(2)} 元。`
}

export interface I1AmortAllocSummary {
  productionCost: number
  manufacturing: number
  selling: number
  management: number
  rd: number
  other: number
  total: number
}

export function aggregateI19AmortAlloc(rows: any[]): I1AmortAllocSummary {
  const out: I1AmortAllocSummary = {
    productionCost: 0,
    manufacturing: 0,
    selling: 0,
    management: 0,
    rd: 0,
    other: 0,
    total: 0,
  }
  if (!Array.isArray(rows)) return out
  for (const r of rows) {
    out.productionCost += num(r.productionCost)
    out.manufacturing += num(r.manufacturingExpense ?? r.manufacturing)
    out.selling += num(r.sellingExpense ?? r.selling)
    out.management += num(r.managementExpense ?? r.admin)
    out.rd += num(r.rdExpense ?? r.rd)
    out.other += num(r.otherExpense ?? r.other)
  }
  out.total = out.productionCost + out.manufacturing + out.selling + out.management + out.rd + out.other
  return out
}

export function formatAmortAllocNote(a: I1AmortAllocSummary): string {
  if (Math.abs(a.total) < 0.005) return 
    小计审定数）
   *
   * 当审定表对应小计 ≠ 此合计时显示黄色警告。
   */
  const adjudicationFromDetail: ComputedRef<I1AdjudicationFromDetail> = computed(() => {
    const totals = detailTotals.value
    return {
      costAudited: totals.cost,
      amortAudited: totals.accAmort,
      impairAudited: totals.impairment,
    }
  })

  // ─── amortizationForAlloc: I1-10/11 → I1-9 按资产摊销额（Req 10.2, 11.7）

  /**
   * 从 I1-10 或 I1-11 摊销测算行按资产聚合本期摊销合计，供 I1-9 分配表使用。
   * byAsset: { 
    已发布摊销分配（I1-9-alloc-totals + i1:amortization-allocated）
  I2: 155 个
    

/** I2-16 可收回金额测试行（对齐 Excel 一/二/三节） */
export interface I2RecoverableTestRow {
  rowId: string
  name: string
  bookValue: number
  cashFlows: number[]
  discountRate: number
  growthRate: number
  growthRateBasis: string
  usePreTaxRate: boolean
  fvDisposal: I2FairValueDisposal
  waccParams: I2WaccParams
  terminalValue: number
  valueInUse: number
  fairValueLessDisposal: number
  recoverableAmount: number
  discountedCashFlows: number[]
  discountFactors: number[]
  discountedTerminalValue: number
  pvForecast: number
  fairValueSource: string
  disposalTotal: number
  recoverableSource: string
  costOfEquity: number
  waccAfterTax: number
  preTaxDiscountRate: number
  effectiveDiscountRate: number
  rateInvalid: boolean
  /** 开发支出常无可观察市价：仅测使用价值 */
  preferValueInUse: boolean
  preferValueInUseReason: string
  /** 上期 WACC（对比用，小数） */
  priorWacc: number
  /** 行业参考 WACC（对比用，小数） */
  industryWacc: number
}

export interface SensitivityResult {
  scenario: string
  discountRate: number
  growthRate: number
  valueInUse: number
  recoverableAmount: number
  differenceFromBase: number
}

const ITEM_ID_15_ROWS = 
    

// ---------- 基础公式 ----------

/** 审定数 = 未审数 + AJE调整 + RJE重分类 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return unadj + aje + rje
}

/** 资产类期末余额（借方科目1717开发支出）：期末 = 期初 + 借方发生 - 贷方发生 */
export function calcAssetEndBalance(begin: number, debit: number, credit: number): number {
  return begin + debit - credit
}

/**
 * 三角勾稽校验：差额 = 期末 - (期初 + 增加 - 减少)
 * 返回0表示勾稽平衡，非0表示存在差异
 */
export function calcTriangleReconciliation(begin: number, increase: number, decrease: number, end: number): number {
  return end - (begin + increase - decrease)
}

/** 净值 = 原值 - 减值准备 */
export function calcNetValue(cost: number, impairment: number): number {
  return cost - impairment
}

/** 合计 = SUM(数组)；空数组返回0 */
export function calcSubtotal(arr: number[]): number {
  return arr.reduce((a, b) => a + b, 0)
}

// ---------- 分析公式 ----------

/** 变动率 = (本期 - 上期) / 上期；上期为0时返回null */
export function calcChangeRate(current: number, prior: number): number | null {
  if (prior === 0) return null
  return (current - prior) / prior
}

/** 差异 = 实际值 - 预期值 */
export function calcVarianceFromExpected(actual: number, expected: number): number {
  return actual - expected
}

// ---------- I2 专属公式 ----------

/**
 * 借贷平衡校验
 * 比较借方合计与贷方合计，精度容差1e-6
 */
export function calcDebitCreditBalance(debits: number[], credits: number[]): {
  totalDebit: number
  totalCredit: number
  isBalanced: boolean
} {
  const totalDebit = debits.reduce((s, d) => s + d, 0)
  const totalCredit = credits.reduce((s, c) => s + c, 0)
  const EPSILON = 1e-6
  return {
    totalDebit,
    totalCredit,
    isBalanced: Math.abs(totalDebit - totalCredit) < EPSILON,
  }
}

/**
 * 减值金额有效性校验：减值金额 ∈ [0, 账面价值]
 * impairment >= 0 且 impairment <= bookValue 时有效
 */
export function calcImpairmentValid(impairment: number, bookValue: number): boolean {
  return impairment >= 0 && impairment <= bookValue
}

/**
 * 截止测试日期差（天数）：|记账日 - 单据日|
 * 返回绝对天数差
 */
export function calcDateDiffDays(recordDate: Date, documentDate: Date): number {
  const MS_PER_DAY = 86400000
  const a = recordDate?.getTime?.()
  const b = documentDate?.getTime?.()
  if (!Number.isFinite(a) || !Number.isFinite(b)) return 0
  const diffMs = Math.abs(a - b)
  return Math.floor(diffMs / MS_PER_DAY)
}

/**
 * 滞后天数异常：日期差 > 抽样窗口阈值（用于样本异常提示，非会计跨期判定）
 */
export function isCrossPeriod(recordDate: Date, documentDate: Date, thresholdDays: number): boolean {
  return calcDateDiffDays(recordDate, documentDate) > thresholdDays
}

/**
 * 会计跨期判定（相对资产负债表日）：
 * 单据日与记账日分处截止日两侧即为跨期。
 * - 单据到账：单据≤截止 且 记账>截止 → 本期漏记
 * - 账到单据：记账≤截止 且 单据>截止 → 本期多记
 * 两侧任一方向跨过截止日均视为跨期。
 */
export function isCutoffPeriodCrossing(
  documentDate: Date,
  recordDate: Date,
  cutoffDate: Date,
): boolean {
  // 薄封装：委托 cutoffCanonical.crossesByCutoffBoundary（截止日两侧 XOR 单一真源）。
  // Date → 本地 YYYY-MM-DD（与 canonical parseDate 的本地 0 点口径一致，避免 UTC 偏移）；
  // 非法 Date → 空串 → canonical 解析为 null → false（等价原 finite 校验）。
  const fmt = (dt: Date): string => {
    const t = dt?.getTime?.()
    if (!Number.isFinite(t)) return 
    

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** I2-2 明细行原始 JSON 结构 */
export interface I2DetailRowRaw {
  rowId?: string
  projectName?: string        // 研发项目名称
  projectCode?: string        // 项目编号
  phase?: string              // 研究/开发阶段
  capitalizeDate?: string     // 资本化起点日期
  // 本期投入
  materialInput?: number      // 材料投入
  laborInput?: number         // 人工投入
  depreciationInput?: number  // 折旧投入
  otherInput?: number         // 其他投入
  inputTotal?: number         // 投入合计
  // 资本化金额
  capitalizedBegin?: number   // 资本化期初
  capitalizedIncrease?: number // 本期资本化增加
  capitalizedDecrease?: number // 本期资本化减少
  capitalizedEnd?: number     // 资本化期末
  // 转入I1
  transferToIntangible?: number // 转入无形资产金额
  transferDate?: string        // 转入日期
  transferAssetName?: string   // 转入资产名称
}

/** I2-1 审定表行原始 JSON 结构 */
export interface I2AdjudicationRowRaw {
  rowId?: string
  projectName?: string         // 项目名称
  cipBegin?: number            // 期初余额
  increaseCapitalized?: number // 本期增加(资本化)
  decreaseTransfer?: number    // 本期减少-转无形资产
  decreaseExpense?: number     // 本期减少-转费用
  cipEnd?: number              // 期末余额
  unadjusted?: number          // 未审数
  aje?: number                 // AJE
  rje?: number                 // RJE
  audited?: number             // 审定数
  remark?: string
}

/** I6 incoming event payload */
export interface I6ExpenseEventDetail {
  /** I6 费用化金额 */
  expense: number
  /** 研发总额（费用化+资本化应=此值） */
  total: number
}

// ─── Return Types ────────────────────────────────────────────────────────────

export interface I2DetailTotals {
  /** 资本化金额期末合计（I2-2 所有行 capitalizedEnd 之和） */
  capitalized: number
  /** 转入无形资产合计（I2-2 所有行 transferToIntangible 之和） */
  transferred: number
}

export interface I6LinkageStatus {
  /** I6 费用化金额（从 EventBus 接收） */
  expense: number
  /** 研发总额 */
  total: number
  /** 是否已收到 I6 事件（未收到时勿当作「已核对」） */
  ready: boolean
  /** 是否平衡：I6费用化 + I2资本化 = 研发总额；未就绪时为 false */
  isBalanced: boolean
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 安全解析 JSON 数组字符串，失败回退空数组
 */
function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/**
 * 安全提取数值，NaN/null/undefined → 0
 */
function _getNum(val: any): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI2CrossSheet(allResponses: Ref<Map<string, any>>): {
  detailTotals: ComputedRef<{ capitalized: number; transferred: number }>
  i6LinkageStatus: ComputedRef<I6LinkageStatus>
  i1TransferAmount: ComputedRef<number>
} {
  // ─── I6 incoming state（响应式存储 EventBus 接收的 I6 数据）─────────────

  const _i6Expense = ref(0)
  const _i6Total = ref(0)
  const _i6Ready = ref(false)

  // ─── 解析 I2-2 明细行数据 ──────────────────────────────────────────────

  const detailRows = computed<I2DetailRowRaw[]>(() => {
    const resp = allResponses.value.get(
    

export interface I2CapitalizationProjectRow {
  rowId: string
  /** 项目编号 */
  projectNo: string
  /** 研发项目名称 */
  projectName: string
  /** 研究阶段支出 */
  researchAmount: number
  /** 开发阶段支出 */
  developmentAmount: number
  /** 研发项目具体内容 */
  projectContent: string
  /** 预算：直接材料 */
  budgetMaterial: number
  /** 预算：直接人工 */
  budgetLabor: number
  /** 预算：其他费用 */
  budgetOther: number
  /** 研发人员构成 */
  personnelComposition: string
  /** 资本化开始时点 */
  capStartDate: string
  /** 资本化的具体依据 */
  capBasis: string
  /** CAS6 五条件 */
  conditions: CAS6Condition[]
  /** 确认为无形资产金额 */
  recognizedIaAmount: number
  /** 是否与无形资产明细勾稽一致 */
  ledgerConsistent: I2Yn
  /** 截至期末的研发进度 */
  progress: string
  /** 支持性证据 */
  supportingEvidence: string
  /** 索引 */
  indexRef: string
  /** 立项/计划开始日（时点校验用） */
  projectStartDate: string
  /** 验收/完成日（时点校验用） */
  acceptanceDate: string
  /** 转入无形资产日期（可自 I2-2 带入） */
  transferDate: string
  /** 条件级附件总览（可选） */
  attachments: string[]
  /** 行备注 */
  remark: string
}

export interface I2CapitalizationSummary {
  projectCount: number
  metCount: number
  notMetCount: number
  pendingCount: number
  totalResearch: number
  totalDevelopment: number
  totalRecognizedIa: number
  ledgerInconsistentCount: number
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _str(v: unknown): string {
  return v == null ? 
    

export interface I2ImpairmentTestRow {
  rowId: string
  /** 开发支出项目名称 */
  name: string
  /** 是否存在减值迹象 */
  hasIndication: I2Yn
  /** ① 减值迹象描述 */
  indicationDesc: string
  /** 是否进行减值测试（有迹象则须测；可手工强制） */
  needTest: boolean
  /** ② 账面价值（资本化期末−摊销，不含减值） */
  bookValue: number
  /** ③ 公允价值减去处置费用的净额 */
  fairValueLessDisposal: number
  /** ④ 预计未来现金流量现值 */
  dcfValue: number
  /** ⑤ 可收回金额 = MAX(③,④)；无须测试时为 0 */
  recoverableAmount: number
  /** ⑥ 期末应计提减值 = MAX(②−⑤, 0) */
  shouldProvision: number
  /** ⑦ 期末账面已计提减值 */
  alreadyProvided: number
  /** ⑧ 本期应补提或冲回 = ⑥ − ⑦（正=补提，负=冲回） */
  difference: number
  /** 工作底稿索引号 */
  indexRef: string
  /** 备注 */
  remark: string
  /** 行结论：无需测试/无需计提/需补提/应冲回 */
  conclusion: string
  /** 是否关联 I2-16 */
  linkedToDcf: boolean
  /** 来源 I2-2 行 id */
  sourceDetailRowId?: string
}

export interface I2ImpairmentSummary {
  totalBookValue: number
  totalFairValue: number
  totalDcf: number
  totalRecoverable: number
  totalShouldProvision: number
  totalAlreadyProvided: number
  totalDifference: number
  /** ⑧>0 合计 */
  totalSupplement: number
  /** ⑧<0 合计（绝对值） */
  totalReversal: number
}

export interface I2ImpPrepValidation {
  ok: boolean
  messages: string[]
}

function _getNum(val: unknown): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

function _yn(v: unknown): I2Yn {
  const s = String(v ?? 
    

export interface I2MaterialCheckRow {
  rowId: string
  /** 账面：项目名称 */
  projectName: string
  /** 账面：凭证编号 */
  voucherNo: string
  /** 账面：业务内容 */
  businessDesc: string
  /** 账面：存货名称（品名） */
  inventoryName: string
  /** 账面：单位 */
  unit: string
  /** 账面：数量 */
  quantity: number
  /** 账面：借方金额 */
  debitAmount: number
  /** 账面：对方科目 */
  counterpartAccount: string
  /** 账面：对方明细科目 */
  counterpartDetail: string
  /** 领料单：日期/编号 */
  slipDateNo: string
  /** 领料单：领用人员 */
  recipient: string
  /** 领料单：领用部门 */
  recipientDept: string
  /** 领料单：研发项目 */
  slipProject: string
  /** 领料单：数量 */
  slipQty: number
  /** 索引号 */
  indexRef: string
  /** 是否异常 */
  isAbnormal: I2MaterialAbnormal | string
  /** 审核结论 */
  conclusion: string
  /** 备注 */
  remark: string
}

export interface I2MaterialSampleMeta {
  /** 测试总体说明 */
  populationDesc: string
  /** 本期发生额（总体，优先取 I2-7 材料费合计） */
  populationAmount: number
  /** 是否手工覆盖总体 */
  populationManual: boolean
  /** 特定样本说明（大额/关联方/异常） */
  specificSample: string
  /** 抽样方法 */
  sampleMethod: string
  /** 抽样过程说明 */
  sampleProcess: string
  /** 检查比例告警阈值 % */
  coverageThreshold: number
}

export interface I2MaterialSummary {
  sampleCount: number
  checkedTotal: number
  periodTotal: number
  /** null 表示总体为 0，展示 N/A，避免 #DIV/0! */
  coverageRate: number | null
  anomalyCount: number
  qtyMismatchCount: number
  projectMismatchCount: number
  pendingCount: number
}

export function emptyI2MaterialRow(partial?: Partial<I2MaterialCheckRow>): I2MaterialCheckRow {
  return {
    rowId: partial?.rowId || `i28-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    projectName: 
    

export interface I2OutsourceCheckRow {
  rowId: string
  /** 研发项目 */
  projectName: string
  /** 委外研发原因 */
  outsourceReason: string
  /** 合同日期 */
  contractDate: string
  /** 合同号 */
  contractNo: string
  /** 受托方 */
  entrustedParty: string
  /** 研发内容 */
  rdContent: string
  /** 研发成果知识产权归属 */
  ipOwnership: string
  /** 受托方资质 */
  qualification: string
  /** 注册资本 */
  registeredCapital: string
  /** 参保人数 */
  insuredCount: string
  /** 记账凭证日期 */
  voucherDate: string
  /** 凭证编号 */
  voucherNo: string
  /** 业务内容 */
  businessDesc: string
  /** 记账金额 */
  amount: number
  /** 验收日期 */
  acceptanceDate: string
  /** 验收金额 */
  acceptanceAmount: number
  /** 验收结论/交付物 */
  acceptanceResult: string
  /** 是否异常 */
  isAbnormal: I2OutsourceAbnormal | string
  /** 索引号 */
  indexRef: string
  /** 审核结论 */
  conclusion: string
  /** 备注 */
  remark: string
}

export interface I2OutsourceSampleMeta {
  /** 测试原因勾选 */
  testReasons: string[]
  /** 测试原因-其他说明 */
  testReasonOther: string
  populationDesc: string
  populationAmount: number
  populationManual: boolean
  specificSample: string
  sampleMethod: string
  sampleProcess: string
  coverageThreshold: number
}

export interface I2OutsourceSummary {
  sampleCount: number
  checkedTotal: number
  periodTotal: number
  /** null 表示总体为 0，展示 N/A，避免 #DIV/0! */
  coverageRate: number | null
  anomalyCount: number
  amountMismatchCount: number
  missingAcceptanceCount: number
  pendingCount: number
}

export function emptyI2OutsourceRow(partial?: Partial<I2OutsourceCheckRow>): I2OutsourceCheckRow {
  return {
    rowId: partial?.rowId || `i211-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    projectName: 
    

export interface I2PolicyCasItem {
  key: string
  label: string
  casRef: string
  actualPolicy: string
  evaluation: string
  conclusion: CasConclusion
  explanationIfNo: string
}

export interface I2PolicyProcessItem {
  key: string
  label: string
  /** 检查结果 */
  status: YnNa
  /** 获取/查阅情况说明 */
  evidence: string
  /** 索引号 */
  indexRef: string
}

export interface I2PolicyInterview {
  interviewee: string
  interviewDate: string
  businessTypes: string
  rdProcessSummary: string
  rdModel: string
  consistencyWithPrior: YnNa
  notes: string
}

export interface I2PolicyPeerRow {
  rowId: string
  companyName: string
  source: string
  capitalizationPolicy: string
  costAggregation: string
  staffAllocation: string
  remark: string
}

export interface I2PolicyReasonableness {
  /** 检查的研发项目（可填项目名称/索引） */
  inspectedProjects: string
  /** 政策主题（如资本化时点） */
  policyTopic: string
  /** 是否合理 */
  isReasonable: YnNa
  /** 理由 */
  reasons: string
}

export const I2_POLICY_PROCESS_DEFS: Omit<I2PolicyProcessItem, 
    

export type {
  I2CapitalizationProjectRow,
  I2CapitalizationSummary,
  CAS6Condition,
  I26GateIssue,
  I26AmountReconcile,
} from 
    

export type { I2AdjudicationRow as AdjudicationRow, I2AdjudicationSummary }
export { formatChangeRate }

export function useI2Adjudication(params: {
  allResponses: Ref<Map<string, any>>
  tbData: Ref<I2TbData>
  saveResponses: (sheetCode: string, data: Record<string, any>) => Promise<void>
  onAfterSave?: (summary: I2AdjudicationSummary) => void | Promise<void>
}) {
  const { allResponses, tbData, saveResponses, onAfterSave } = params

  const rows = ref<I2AdjudicationRow[]>([])
  const auditNote = ref(
    

export type { I2ImpairmentTestRow, I2ImpairmentSummary, I2ImpPrepValidation, I2FairValueDisposal, I2WaccParams, I216SyncCheck, I2WaccCompareResult }
export { DCF_FORECAST_YEARS }
export {
  emptyI2ImpairmentRow,
  normalizeI2ImpairmentRow,
  recomputeI2ImpairmentRow,
  summarizeI2Impairment,
  validateI2ImpairmentPrep,
  seedRowsFromI2Detail,
  suggestI2ImpairmentConclusion,
  buildI2ImpairmentAdjustmentHint,
} from 
    

export {
  type I2MaterialCheckRow,
  type I2MaterialSampleMeta,
  type I2MaterialSummary,
  emptyI2MaterialRow,
  I2_MATERIAL_DEFAULT_COVERAGE_THRESHOLD,
  I2_MATERIAL_TEST_CONTENT,
  I2_MATERIAL_SAMPLE_METHODS,
  formatCoverageLabel,
  hasQtyMismatch,
  hasProjectMismatch,
  suggestAbnormal,
} from 
    

export {
  type I2OutsourceCheckRow,
  type I2OutsourceSampleMeta,
  type I2OutsourceSummary,
  emptyI2OutsourceRow,
  I2_OUTSOURCE_DEFAULT_COVERAGE_THRESHOLD,
  I2_OUTSOURCE_TEST_CONTENT,
  I2_OUTSOURCE_TEST_REASONS,
  I2_OUTSOURCE_SAMPLE_METHODS,
  formatCoverageLabel,
  hasAmountMismatch,
  hasMissingAcceptance,
  suggestOutsourceAbnormal,
} from 
    

export {
  type I2ProjectDetailRow,
  type I2ProjectDetailSummary,
  type I2ProjectStageKey,
  type I2ProjectCostKey,
  type I2ProjectCostBlock,
  emptyI2ProjectDetailRow,
  costNatureSum,
  costTreatmentSum,
  hasTreatmentMismatch,
  I2_PROJECT_COST_KEYS,
  I2_PROJECT_COST_LABELS,
  I2_PROJECT_COST_NATURE_KEYS,
  I2_PROJECT_TREATMENT_KEYS,
  I2_PROJECT_STAGE_KEYS,
  I2_PROJECT_STAGE_LABELS,
  I2_PROJECT_EDITABLE_STAGES,
} from 
    

export {
  type I2TargetedCheckRow,
  type I2TargetedSampleMeta,
  type I2TargetedRiskFocus,
  type I2TargetedSummary,
  type I2TargetedAdjDraft,
  emptyI2TargetedRow,
  I2_12_DEFAULT_COVERAGE_THRESHOLD,
  I2_12_TEST_CONTENT,
  I2_12_SAMPLE_METHODS,
  I2_12_CHECK_OPTIONS,
  I2_12_OBJECTIVES,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  isAbnormalFlag,
  hasFailedCheck,
  buildI2TargetedConclusionDraft,
  buildI2TargetedAdjDrafts,
  mapSampledToI2TargetedRow,
} from 
    
   */
  const i6LinkageStatus: ComputedRef<I6LinkageStatus> = computed(() => {
    const expense = _i6Expense.value
    const total = _i6Total.value
    const capitalized = i2Capitalized.value
    const ready = _i6Ready.value

    // 未收到 I6 数据 → 非「已核对」，避免假平衡
    if (!ready) {
      return { expense: 0, total: 0, ready: false, isBalanced: false }
    }

    // VR-I6-01: expense + capitalized = total（允许±0.01精度）
    const diff = Math.abs((expense + capitalized) - total)
    const isBalanced = diff <= 0.01

    return { expense, total, ready: true, isBalanced }
  })

  // ─── EventBus: Subscribe I6 
    
  /** 附件索引号 */
  attachmentIndex: string
  /** 系统建议结论 */
  suggestedConclusion: I2WorkHourConclusion
  /** 人工结论 */
  conclusion: I2WorkHourConclusion
  /** 备注 */
  remark: string
}

export interface I2WorkHourSummary {
  totalCount: number
  totalHours: number
  totalSalary: number
  highRatioCount: number
  lowRatioCount: number
  missingBasisCount: number
  sharePayCount: number
  pendingCount: number
  abnormalCount: number
}

export interface I2WorkHourPrepValidation {
  ok: boolean
  messages: string[]
}

export interface I2WorkHourGateResult {
  ok: boolean
  messages: string[]
}

export interface I2WorkHourReconcileResult {
  ok: boolean
  diff: number
  diffRate: number | null
  message: string
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _genId(): string {
  return `i210-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

export function calcWorkHourRatio(hours: number, totalHours: number): number {
  if (totalHours <= 0) return 0
  return hours / totalHours
}

/** 隐含时薪（复核合理性，非 Excel 列） */
export function calcImpliedHourlyRate(salaryAccrual: number, hours: number): number | null {
  if (hours <= 0) return null
  return salaryAccrual / hours
}

/**
 * 建议结论：
 * - 工时>总工时 → 偏高（硬错误）
 * - 有工时无分配依据 → 待核实
 * - 占比≤20% 且有薪酬 → 偏低（兼职分摊不足关注）
 * - 占比≥95% 无依据 → 待核实；有依据则可为合理（全时研发）
 * - 有核心数据 → 合理
 */
export function suggestWorkHourConclusion(row: Pick<
  I2WorkHourCheckRow,
  
    
  >) {
    return calcI2RecoverableResult({
      cashFlows: row.cashFlows,
      manualDiscountRate: row.discountRate,
      growthRate: row.growthRate,
      fvDisposal: row.fvDisposal,
      waccParams: row.waccParams,
      usePreTaxRate: row.usePreTaxRate,
      legacyFairValueNet: row.fairValueLessDisposal,
    })
  }

  function _applyCalcToRow(row: I2RecoverableTestRow, calc: ReturnType<typeof calcI2RecoverableResult>): void {
    row.terminalValue = calc.terminalValue
    row.valueInUse = calc.valueInUse
    row.discountedCashFlows = calc.discountedCashFlows
    row.discountFactors = calc.discountFactors
    row.discountedTerminalValue = calc.discountedTerminalValue
    row.pvForecast = calc.pvForecast
    row.fairValueLessDisposal = calc.fairValueLessDisposal
    row.fairValueSource = calc.fairValueSource
    row.disposalTotal = calc.disposalTotal
    row.costOfEquity = calc.costOfEquity
    row.waccAfterTax = calc.waccAfterTax
    row.preTaxDiscountRate = calc.preTaxDiscountRate
    row.effectiveDiscountRate = calc.effectiveDiscountRate
    row.rateInvalid = calc.rateInvalid

    const prefer = applyPreferValueInUse(
      calc.fairValueLessDisposal,
      calc.valueInUse,
      !!row.preferValueInUse,
      row.preferValueInUseReason || 
    
  if (row.totalHours > 0 && ratio > 0 && ratio <= I2_WH_LOW_RATIO && row.salaryAccrual > 0.01) {
    return 
    
  return `${rate.toFixed(2)}%`
}

/** 从 I2-2 明细汇总本期资本化增加，作为测试总体金额候选 */
export function extractI2CapIncreaseTotal(raw: unknown): number {
  let rows: any[] = []
  if (Array.isArray(raw)) rows = raw
  else if (typeof raw === 
    
  }
  if (row.totalHours > 0 && ratio >= I2_WH_HIGH_RATIO && !hasBasis) return 
    
  }
  return true
}

/** 必填项完成度：按 sheet 关键字段是否有实质内容 */
export function computeI2SheetCompletion(
  map: Map<string, any> | undefined | null,
  fieldPrefixes: string[],
): { filled: number; total: number; progress: number; status: 
    
  })

  /** 手工锁定总体后，I2-7 源值变化 → 过期提示 */
  const populationStale = computed(() => {
    if (!sampleMeta.value.populationManual) return false
    const linked = linkedMaterialTotal.value.amount
    if (linked <= 0) return false
    return Math.abs(linked - sampleMeta.value.populationAmount) > 0.01
  })

  function addRow(partial?: Partial<I2MaterialCheckRow>) {
    rows.value.push(emptyI2MaterialRow(partial))
  }

  function removeRow(rowId: string) {
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
  }

  function applySuggestAbnormal(row: I2MaterialCheckRow) {
    if (row.isAbnormal && row.isAbnormal !== 
    
  })

  /** 手工锁定总体后，I2-7 源值变化 → 过期提示 */
  const populationStale = computed(() => {
    if (!sampleMeta.value.populationManual) return false
    const linked = linkedOutsourceTotal.value.amount
    if (linked <= 0) return false
    return Math.abs(linked - sampleMeta.value.populationAmount) > 0.01
  })

  function addRow(partial?: Partial<I2OutsourceCheckRow>) {
    rows.value.push(emptyI2OutsourceRow(partial))
  }

  function removeRow(rowId: string) {
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
  }

  function applySuggestAbnormal(row: I2OutsourceCheckRow) {
    if (row.isAbnormal && row.isAbnormal !== 
    
  })
}

function stageSummary(
  { columns }: { columns: { property?: string; label?: string }[] },
  sk: I2ProjectStageKey,
) {
  return columns.map((col, i) => {
    if (i === 0) return 
    
import {
  type I2AdjudicationRow,
  type I2AdjudicationSummary,
  I2_ADJ_ROWS_KEY,
  I2_ADJ_NOTE_KEY,
  I2_ADJ_CONCLUSION_KEY,
  emptyI2AdjudicationRow,
  normalizeI2AdjudicationRow,
  recalcI2AdjudicationRow,
  summarizeI2Adjudication,
  seedAdjudicationFromI22,
  applyAjeFromI23,
  serializeI2AdjudicationRow,
  formatChangeRate,
  safeParseArray,
  readText,
} from 
    
import {
  type I2AnalysisBundle,
  type I2CompositionRow,
  type I2CompositionMeta,
  type I2PeerIndicatorRow,
  type I2PerCapitaYoY,
  type I2PerCapitaPeerRow,
  type I2AnalysisStructuredNotes,
  normalizeBundle,
  createDefaultBundle,
  syncDerivedFromComposition,
  recomputeAllComposition,
  recomputePerCapitaYoY,
  emptyCompositionRow,
  emptyPeerIndicator,
  emptyPerCapitaPeer,
  compositionTotals,
  summarizeAnalysisAnomalies,
  buildAnalysisConclusionDraft,
  seedCompositionFromI6Detail,
  I2_ANALYSIS_GROWTH_THRESHOLD,
  I2_ANALYSIS_REV_RATIO_DELTA_THRESHOLD,
} from 
    
import {
  type I2CapitalizationProjectRow,
  type I2CapitalizationSummary,
  type CAS6Condition,
  type I26GateIssue,
  type I26AmountReconcile,
  emptyI2CapitalizationRow,
  normalizeI2CapitalizationRow,
  migrateLegacyCapitalizationMap,
  summarizeI2Capitalization,
  seedRowsFromI2Detail,
  getRowCapResult,
  buildI26ConclusionDraft,
  evaluateCapitalization,
  validateI26CapGate,
  validateI26CapTiming,
  reconcileI26Amounts,
  suggestCas6ConditionsFromText,
} from 
    
import {
  type I2ImpairmentTestRow,
  type I2ImpairmentSummary,
  type I2ImpPrepValidation,
  emptyI2ImpairmentRow,
  normalizeI2ImpairmentRow,
  recomputeI2ImpairmentRow,
  summarizeI2Impairment,
  validateI2ImpairmentPrep,
  seedRowsFromI2Detail,
  suggestI2ImpairmentConclusion,
  buildI2ImpairmentAdjustmentHint,
  buildI2ImpairmentEventDetail,
} from 
    
import {
  type I2MaterialCheckRow,
  type I2MaterialSampleMeta,
  type I2MaterialSummary,
  emptyI2MaterialRow,
  emptyI2MaterialSampleMeta,
  normalizeI2MaterialRow,
  normalizeI2MaterialSampleMeta,
  summarizeI2Material,
  extractI27MaterialTotal,
  formatCoverageLabel,
  suggestAbnormal,
} from 
    
import {
  type I2OutsourceCheckRow,
  type I2OutsourceSampleMeta,
  type I2OutsourceSummary,
  emptyI2OutsourceRow,
  emptyI2OutsourceSampleMeta,
  normalizeI2OutsourceRow,
  normalizeI2OutsourceSampleMeta,
  summarizeI2Outsource,
  extractI27OutsourceTotal,
  formatCoverageLabel,
  suggestOutsourceAbnormal,
} from 
    
import {
  type I2ProjectDetailRow,
  type I2ProjectDetailSummary,
  type I2ProjectStageKey,
  type I2ProjectCostKey,
  emptyI2ProjectDetailRow,
  normalizeI2ProjectDetailRow,
  recalcI2ProjectDetailRow,
  serializeI2ProjectDetailRow,
  summarizeI2ProjectDetail,
  costNatureSum,
  costTreatmentSum,
  hasTreatmentMismatch,
  I2_PROJECT_COST_KEYS,
  I2_PROJECT_COST_LABELS,
  I2_PROJECT_STAGE_LABELS,
  I2_PROJECT_EDITABLE_STAGES,
} from 
    
import {
  type I2TargetedCheckRow,
  type I2TargetedSampleMeta,
  type I2TargetedRiskFocus,
  type I2TargetedSummary,
  emptyI2TargetedRow,
  emptyI2TargetedSampleMeta,
  emptyI2TargetedRiskFocus,
  normalizeI2TargetedRow,
  normalizeI2TargetedSampleMeta,
  normalizeI2TargetedRiskFocus,
  summarizeI2Targeted,
  extractI2CapIncreaseTotal,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  buildI2TargetedConclusionDraft,
  buildI2TargetedAdjDrafts,
  mapSampledToI2TargetedRow,
  isAbnormalFlag,
  hasFailedCheck,
  I2_12_DEFAULT_COVERAGE_THRESHOLD,
} from 
    
}

export function buildWorkHourConclusionDraft(summary: I2WorkHourSummary): string {
  const parts = [
    `经检查研发人员工时记录共 ${summary.totalCount} 条，研发工时合计 ${summary.totalHours.toFixed(1)} 小时，薪酬计提合计 ${summary.totalSalary.toLocaleString(
    
}

export function recomputeI2WorkHourRow(row: I2WorkHourCheckRow, opts?: { refreshSuggested?: boolean }): I2WorkHourCheckRow {
  const hours = _num(row.hours)
  const totalHours = _num(row.totalHours)
  const salaryAccrual = _num(row.salaryAccrual)
  const ratio = calcWorkHourRatio(hours, totalHours)
  const next = {
    ...row,
    hours,
    totalHours,
    salaryAccrual,
    ratio,
  }
  const suggested = suggestWorkHourConclusion(next)
  next.suggestedConclusion = suggested
  if (opts?.refreshSuggested !== false) {
    if (!row.conclusion || row.conclusion === row.suggestedConclusion) {
      next.conclusion = suggested
    }
  }
  return next
}

export function emptyI2WorkHourRow(partial?: Partial<I2WorkHourCheckRow>): I2WorkHourCheckRow {
  return recomputeI2WorkHourRow({
    rowId: partial?.rowId || _genId(),
    projectName: 
    
}

export function summarizeI2Material(
  rows: I2MaterialCheckRow[],
  periodTotal: number,
): I2MaterialSummary {
  const sampleCount = rows.length
  const checkedTotal = Math.round(rows.reduce((s, r) => s + _num(r.debitAmount), 0) * 100) / 100
  const anomalyCount = rows.filter((r) => {
    const v = (r.isAbnormal || 
    
}

export function summarizeI2Outsource(
  rows: I2OutsourceCheckRow[],
  periodTotal: number,
): I2OutsourceSummary {
  const sampleCount = rows.length
  const checkedTotal = Math.round(rows.reduce((s, r) => s + _num(r.amount), 0) * 100) / 100
  const anomalyCount = rows.filter((r) => {
    const v = (r.isAbnormal || 
    
}

function onCurrentChange(row: I2CapitalizationProjectRow | null) {
  if (row) activeRowId.value = row.rowId
}

function getSummary({ columns }: { columns: any[] }) {
  const s = summary.value
  return columns.map((col, idx) => {
    if (idx === 0) return 
    
})

// ─── 6.2 / 6.3: useI2CrossSheet（I6↔I2 双向 + I2→I1 转入联动）──────────────
const { detailTotals, i6LinkageStatus, i1TransferAmount } = useI2CrossSheet(allResponses)
provide(
     && remark) {
        try { parsedMeta = JSON.parse(remark) } catch { parsedMeta = sampleRaw }
      } else {
        parsedMeta = sampleRaw
      }
    }
    sampleMeta.value = normalizeI2MaterialSampleMeta(parsedMeta)

    auditNote.value = _readText(map.get(STORAGE_NOTE))
    auditConclusion.value = _readText(map.get(STORAGE_CONCLUSION))

    // 非手工总体时，自动跟 I2-7 材料费
    if (!sampleMeta.value.populationManual) {
      const linked = extractI27MaterialTotal(map.get(I27_ROWS))
      if (linked > 0) sampleMeta.value.populationAmount = linked
    }
  }

  watch(() => {
    const m = getMap()
    return [m.get(STORAGE_ROWS), m.get(STORAGE_SAMPLE), m.get(STORAGE_NOTE), m.get(STORAGE_CONCLUSION), m.get(I27_ROWS)]
  }, () => load(), { immediate: true, deep: false })

  const linkedMaterialTotal: ComputedRef<{ amount: number; source: string }> = computed(() => {
    const amt = extractI27MaterialTotal(getMap().get(I27_ROWS))
    return amt > 0 ? { amount: amt, source: 
     && remark) {
        try { parsedMeta = JSON.parse(remark) } catch { parsedMeta = sampleRaw }
      } else {
        parsedMeta = sampleRaw
      }
    }
    sampleMeta.value = normalizeI2OutsourceSampleMeta(parsedMeta)

    auditNote.value = _readText(map.get(STORAGE_NOTE))
    auditConclusion.value = _readText(map.get(STORAGE_CONCLUSION))

    if (!sampleMeta.value.populationManual) {
      const linked = extractI27OutsourceTotal(map.get(I27_ROWS))
      if (linked > 0) sampleMeta.value.populationAmount = linked
    }
  }

  watch(() => {
    const m = getMap()
    return [m.get(STORAGE_ROWS), m.get(STORAGE_SAMPLE), m.get(STORAGE_NOTE), m.get(STORAGE_CONCLUSION), m.get(I27_ROWS)]
  }, () => load(), { immediate: true, deep: false })

  const linkedOutsourceTotal: ComputedRef<{ amount: number; source: string }> = computed(() => {
    const amt = extractI27OutsourceTotal(getMap().get(I27_ROWS))
    return amt > 0 ? { amount: amt, source: 
     // 上期审定合计（可选手工）

export interface I2AdjudicationRow {
  rowId: string
  projectName: string
  /** 期初未审 */
  beginUnadj: number
  /** 期初账项调整 */
  beginAdj: number
  /** 期初审定（公式） */
  beginAudited: number
  /** 期末未审 */
  endUnadj: number
  /** 期末账项调整（含 AJE/RJE 净额） */
  endAdj: number
  /** 期末审定（公式） */
  endAudited: number
  /** 变动额 = 期末审定 − 期初审定 */
  changeAmount: number
  /** 变动率；期初审定为 0 时为 null（N/A） */
  changeRate: number | null
  /** 原因分析 */
  reasonAnalysis: string
  /** 兼容旧版滚动字段（取数/披露用） */
  increaseCapitalized: number
  decreaseTransfer: number
  decreaseExpense: number
  isAutoFilled?: boolean
  /**
   * 期末调整是否来自 I2-3 比例分摊（非按项目精确匹配）。
   * 为 true 时须人工复核，手工改 endAdj 后应清除。
   */
  ajeApprox?: boolean
}

export interface I2AdjudicationSummary {
  beginUnadj: number
  beginAdj: number
  beginAudited: number
  endUnadj: number
  endAdj: number
  endAudited: number
  changeAmount: number
  changeRate: number | null
  increaseCapitalized: number
  decreaseTransfer: number
  decreaseExpense: number
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _str(v: unknown): string {
  return v == null ? 
     ? _num(s.rdHourRatio) : null

    for (const projectName of projects) {
      out.push(emptyI2WorkHourRow({
        staffName: name,
        projectName,
        totalHours: ratioPct != null && ratioPct > 0 ? 100 : 0,
        hours: ratioPct != null && ratioPct > 0 ? ratioPct : 0,
        remark: 
     as const,
    }))
}

export function buildI2ImpairmentSubTable(rows: I2ImpairmentRow[]): Record<string, unknown>[] {
  const data = rows.filter((r) => !r.isTotal && (r.name || r.beginBalance || r.provision || r.decrease))
  const mapped = data.map((r) => {
    const end = Math.round((r.beginBalance + r.provision - r.decrease) * 100) / 100
    return {
      label: r.name,
      期初余额: r.beginBalance,
      本期计提: r.provision,
      本期减少: r.decrease,
      期末余额: end,
      row_type: 
     as const,
    },
  ]
}

/**
 * 研发支出（按费用性质）子表。
 *
 * 🔴 行字段名必须与 `I2_NATURE_COLUMNS[].key` 逐字一致 —— 投影器按
 * `r.get(column.key)` 取值，改一侧不改另一侧 ⇒ 整表值全空（表头在、数据没了）。
 * 标签列键取 `项目`（模板同名），并同时写通用 `label` 供合计/兜底路径使用。
 */
export function buildI2ListedNatureSubTable(rows: I2NatureRow[]): Record<string, unknown>[] {
  const data = rows.filter((r) => !r.isTotal)
  const mapped = data
    .filter((r) => r.name || r.currentExpensed || r.currentCapitalized || r.priorExpensed || r.priorCapitalized)
    .map((r) => ({
      项目: r.name,
      label: r.name,
      cur_expense: r.currentExpensed,
      cur_capitalize: r.currentCapitalized,
      prior_expense: r.priorExpensed,
      prior_capitalize: r.priorCapitalized,
      row_type: 
     as const,
    },
  ]
}

export function buildI2ListedSubTableData(snap: I2ListedSyncSnapshot): Record<string, Record<string, unknown>[]> {
  const out: Record<string, Record<string, unknown>[]> = {
    [I2_LISTED_SUBTABLE.nature]: buildI2ListedNatureSubTable(snap.natureRows),
    [I2_LISTED_SUBTABLE.movement]: buildI2ListedMovementSubTable(snap.movementRows),
  }
  // 续：资本化情况（从 movementRows 提取有资本化信息的项目）
  const capDetailRows = (snap.movementRows || [])
    .filter((r) => !r.isTotal && (r.capStartDate || r.capBasis || r.progress))
    .map((r) => ({
      label: r.name || 
     as const,
    },
  ]
}

export function buildI2SoeMovementSubTable(rows: I2MovementRow[]): Record<string, unknown>[] {
  const data = rows.filter((r) => !r.isTotal && _hasMovementAmount(r))
  data.forEach(recalcMovementEnd)
  const mapped = data.map((r) => ({
    label: r.name,
    期初余额: r.beginBalance,
    本期增加_内部开发支出: r.increaseInternal,
    本期增加_其他: r.increaseOther,
    本期减少_确认为无形资产: r.decreaseToIntangible,
    本期减少_转入当期损益: r.decreaseToExpense,
    本期减少_其他: r.decreaseOther,
    期末余额: r.endBalance,
    资本化开始时点: r.capStartDate,
    资本化的具体依据: r.capBasis,
    截至期末的研发进度: r.progress,
    row_type: 
     in data)) continue
    out.push(emptyI2CapitalizationRow({
      projectName: name,
      capStartDate: _str(data.date),
      conditions: normalizeConditions(data.conditions),
    }))
  }
  return out
}

export function getRowCapResult(row: I2CapitalizationProjectRow): CapitalizationResult {
  return evaluateCapitalization(row.conditions)
}

export function summarizeI2Capitalization(rows: I2CapitalizationProjectRow[]): I2CapitalizationSummary {
  let metCount = 0
  let notMetCount = 0
  let pendingCount = 0
  let totalResearch = 0
  let totalDevelopment = 0
  let totalRecognizedIa = 0
  let ledgerInconsistentCount = 0

  for (const r of rows) {
    if (!r.projectName && !r.developmentAmount && !r.researchAmount) continue
    const result = getRowCapResult(r)
    const filled = r.conditions.some((c) => c.result === 
     open>
      <summary>📋 编制提示（对齐 Excel 开发支出调整分录汇总表 I2-3）</summary>
      <div class=
     }
    }
    auditConclusion.value = buildI26ConclusionDraft(summary.value)
    return { ok: true, message: 
     }
  })

  const summary: ComputedRef<I2MaterialSummary> = computed(() =>
    summarizeI2Material(rows.value, sampleMeta.value.populationAmount),
  )

  const coverageLow = computed(() =>
    summary.value.coverageRate != null
    && summary.value.coverageRate < sampleMeta.value.coverageThreshold
    && summary.value.periodTotal > 0,
  )

  const coverageLabel = computed(() => formatCoverageLabel(summary.value.coverageRate))

  const coverageTagType = computed(() => {
    if (summary.value.coverageRate == null) return 
     }
  })

  const summary: ComputedRef<I2OutsourceSummary> = computed(() =>
    summarizeI2Outsource(rows.value, sampleMeta.value.populationAmount),
  )

  const coverageLow = computed(() =>
    summary.value.coverageRate != null
    && summary.value.coverageRate < sampleMeta.value.coverageThreshold
    && summary.value.periodTotal > 0,
  )

  const coverageLabel = computed(() => formatCoverageLabel(summary.value.coverageRate))

  const coverageTagType = computed(() => {
    if (summary.value.coverageRate == null) return 
     }
  })

  const summary: ComputedRef<I2TargetedSummary> = computed(() =>
    summarizeI2Targeted(rows.value, sampleMeta.value.populationAmount),
  )

  const coverageLow = computed(() =>
    summary.value.coverageRate != null
    && summary.value.coverageRate < sampleMeta.value.coverageThreshold
    && summary.value.periodTotal > 0,
  )

  const coverageLabel = computed(() => formatLayeredCoverageLabel(summary.value))

  const coverageTagType = computed(() => {
    if (summary.value.coverageRate == null) return 
     },
]

export interface I2ListedSyncSnapshot {
  natureRows: I2NatureRow[]
  movementRows: I2MovementRow[]
  importantRows: I2ImportantCapRow[]
  impairmentRows: I2ImpairmentRow[]
  noteText: string
  noteCap: string
  noteImpairTest: string
  notePurchased: string
}

export interface I2SoeSyncSnapshot {
  movementRows: I2MovementRow[]
  noteText: string
}

function _hasMovementAmount(r: I2MovementRow): boolean {
  return Math.abs(r.beginBalance) + Math.abs(r.increaseInternal) + Math.abs(r.increaseOther)
    + Math.abs(r.decreaseToIntangible) + Math.abs(r.decreaseToExpense) + Math.abs(r.decreaseOther)
    + Math.abs(r.endBalance) > 0.005
    || !!(r.name && r.name.trim())
}

export function buildI2ListedMovementSubTable(rows: I2MovementRow[]): Record<string, unknown>[] {
  const data = rows.filter((r) => !r.isTotal && _hasMovementAmount(r))
  data.forEach(recalcMovementEnd)
  const mapped = data.map((r) => ({
    label: r.name,
    期初余额: r.beginBalance,
    本期增加_内部开发支出: r.increaseInternal,
    本期增加_其他: r.increaseOther,
    本期减少_确认为无形资产: r.decreaseToIntangible,
    本期减少_计入当期损益: r.decreaseToExpense,
    期末余额: r.endBalance,
    资本化开始时点: r.capStartDate,
    资本化的具体依据: r.capBasis,
    截至期末的研发进度: r.progress,
    row_type: 
    )

  /** I6 费用化合计（EventBus）；未收到时 ready=false */
  const i6Expense = ref(0)
  const i6Ready = ref(false)

  function load() {
    const map = allResponses.value
    rows.value = _safeParseArray(map.get(STORAGE_ROWS)).map(normalizeI2ProjectDetailRow)
    auditProcess.value = _readText(map.get(STORAGE_PROCESS))
    auditNote.value = _readText(map.get(STORAGE_NOTE))
    auditConclusion.value = _readText(map.get(STORAGE_CONCLUSION))
  }

  watch(
    () => [
      allResponses.value.get(STORAGE_ROWS),
      allResponses.value.get(STORAGE_PROCESS),
      allResponses.value.get(STORAGE_NOTE),
      allResponses.value.get(STORAGE_CONCLUSION),
      allResponses.value.get(I22_ROWS),
    ],
    () => load(),
    { immediate: true },
  )

  const summary: ComputedRef<I2ProjectDetailSummary> = computed(() =>
    summarizeI2ProjectDetail(rows.value),
  )

  /** 与 I2-2 交叉：优先用本期增加资本化合计 vs I2-2 totalInvestment */
  const crossValidateI22Diff = computed(() => {
    const detailRows = _safeParseArray(allResponses.value.get(I22_ROWS))
    if (!detailRows.length) return null
    const i22Total = detailRows.reduce(
      (s, r) => s + _num(r.totalInvestment ?? r.capitalizedAmount ?? r.endingBalance),
      0,
    )
    const local = summary.value.increaseCapitalized || summary.value.increaseTotal
    return Math.round((local - i22Total) * 100) / 100
  })

  /** I6 费用化 vs 本表本期增加「费用化」合计 */
  const i6ExpenseCross = computed(() => {
    const local = summary.value.increaseExpensed
    if (!i6Ready.value) {
      return { ready: false as const, i6: 0, local, diff: null as number | null }
    }
    const diff = Math.round((local - i6Expense.value) * 100) / 100
    return { ready: true as const, i6: i6Expense.value, local, diff }
  })

  function _onI6ExpenseUpdated(event: Event): void {
    const detail = (event as CustomEvent<{ expense?: number }>).detail
    if (detail && typeof detail === 
    )

  function load() {
    const map = allResponses.value
    rows.value = safeParseArray(map.get(I2_ADJ_ROWS_KEY)).map(normalizeI2AdjudicationRow)
    auditNote.value = readText(map.get(I2_ADJ_NOTE_KEY))
    auditConclusion.value = readText(map.get(I2_ADJ_CONCLUSION_KEY))
  }

  watch(allResponses, () => load(), { immediate: true })

  const summary: ComputedRef<I2AdjudicationSummary> = computed(() => summarizeI2Adjudication(rows.value))

  const totalRow = computed(() => emptyI2AdjudicationRow({
    projectName: 
    )

  function load() {
    const map = getMap()
    const fromRows = _safeParseArray(map.get(STORAGE_ROWS)).map(normalizeI2CapitalizationRow)
    if (fromRows.length) {
      rows.value = fromRows
    } else {
      const legacy = migrateLegacyCapitalizationMap(_parseObject(map.get(STORAGE_LEGACY)))
      rows.value = legacy
    }
    auditNote.value = _readText(map.get(STORAGE_NOTE))
    auditConclusion.value = _readText(map.get(STORAGE_CONCLUSION))
  }

  watch(() => {
    const m = getMap()
    return [
      m.get(STORAGE_ROWS),
      m.get(STORAGE_LEGACY),
      m.get(STORAGE_NOTE),
      m.get(STORAGE_CONCLUSION),
      m.get(I22_ROWS),
      m.get(I27_ROWS),
    ]
  }, () => load(), { immediate: true, deep: false })

  const summary: ComputedRef<I2CapitalizationSummary> = computed(() =>
    summarizeI2Capitalization(rows.value),
  )

  const activeRow = computed(() =>
    rows.value.find((r) => r.rowId === activeRowId.value) || null,
  )

  const activeResult = computed(() =>
    activeRow.value ? getRowCapResult(activeRow.value) : null,
  )

  const gateIssues: ComputedRef<I26GateIssue[]> = computed(() =>
    validateI26CapGate(rows.value),
  )

  const gateBlocked = computed(() =>
    gateIssues.value.some((i) => i.level === 
    )

  function load() {
    const map = getMap()
    rows.value = _safeParseArray(map.get(STORAGE_ROWS)).map(normalizeI2TargetedRow)

    sampleMeta.value = normalizeI2TargetedSampleMeta(_parseObject(map.get(STORAGE_SAMPLE)))

    // 风险关注：优先新 key，否则迁移旧 I2-12-targeted
    const riskRaw = _parseObject(map.get(STORAGE_RISK))
      || _parseObject(map.get(STORAGE_LEGACY))
    riskFocus.value = normalizeI2TargetedRiskFocus(riskRaw)

    auditNote.value = _readText(map.get(STORAGE_NOTE))
    auditConclusion.value = _readText(map.get(STORAGE_CONCLUSION))

    // 旧版 overallConclusion 并入审计结论（仅当结论为空）
    if (!auditConclusion.value && riskRaw?.overallConclusion) {
      auditConclusion.value = String(riskRaw.overallConclusion)
    }

    if (!sampleMeta.value.populationManual) {
      const linked = extractI2CapIncreaseTotal(map.get(I22_ROWS))
      if (linked > 0) sampleMeta.value.populationAmount = linked
    }
  }

  watch(() => {
    const m = getMap()
    return [
      m.get(STORAGE_ROWS),
      m.get(STORAGE_SAMPLE),
      m.get(STORAGE_RISK),
      m.get(STORAGE_LEGACY),
      m.get(STORAGE_NOTE),
      m.get(STORAGE_CONCLUSION),
      m.get(I22_ROWS),
    ]
  }, () => load(), { immediate: true, deep: false })

  const linkedCapTotal: ComputedRef<{ amount: number; source: string }> = computed(() => {
    const amt = extractI2CapIncreaseTotal(getMap().get(I22_ROWS))
    return amt > 0 ? { amount: amt, source: 
    )

const {
  rows,
  sampleMeta,
  riskFocus,
  auditNote,
  auditConclusion,
  summary,
  coverageLow,
  coverageLabel,
  coverageTagType,
  linkedCapTotal,
  adjDrafts,
  addRow,
  removeRow,
  updateRow,
  fillFromSampledVouchers,
  setPopulationAmount,
  syncPopulationFromI22,
  appendAdjDraftsToNote,
  fillConclusionDraft,
  persistAll,
  saveNote,
  saveConclusion,
} = useI2TargetedCheck(allResponsesRef, {
  saveResponse: props.saveResponse,
})

function fmtNum(v: number): string {
  return v == null || isNaN(v) ? 
    )
    auditNote.value = auditNote.value
      ? `${auditNote.value.trim()}\n\n【I2-12 调整建议草稿】\n${block}`
      : `【I2-12 调整建议草稿】\n${block}`
    return { ok: true, count: drafts.length, message: `已写入 ${drafts.length} 条调整建议到审计说明` }
  }

  function fillConclusionDraft() {
    auditConclusion.value = buildI2TargetedConclusionDraft({
      sampleCount: summary.value.sampleCount,
      coverageLabel: coverageLabel.value,
      anomalyCount: summary.value.anomalyCount,
      failCheckCount: summary.value.failCheckCount,
      riskFocus: riskFocus.value,
    })
  }

  async function persistAll() {
    if (!options?.saveResponse) return
    // 同步样本量默认值
    if (!sampleMeta.value.sampleSize && rows.value.length) {
      sampleMeta.value.sampleSize = rows.value.length
    }
    await options.saveResponse(
    )
    const row = emptyI2WorkHourRow({
      staffName: summaryText || String(s?.voucherNo ?? 
    )
    return safeParseRows<I2AdjudicationRowRaw>(resp?.remark)
  })

  // ─── detailTotals: I2-2 明细聚合（资本化金额 + 转入金额）─────────────

  /**
   * 从 I2-2 明细表聚合：
   * - capitalized: 所有行 capitalizedEnd 之和（资本化金额期末合计）
   * - transferred: 所有行 transferToIntangible 之和（转入无形资产合计）
   *
   * 用于与 I2-1 审定表交叉验证：
   * - 审定表
    )
    rows.value.push(emptyI2StaffRow({
      staffName: summaryText || String(s?.voucherNo ?? 
    )
  ElMessage.success(r.message)
}

/** 补提金额显著时，将调整分录提示追加进审计说明（若尚未记录过） */
async function maybeAppendAdjustmentHint(): Promise<void> {
  const hint = buildI2ImpairmentAdjustmentHint(impairmentSummary.value.totalSupplement)
  if (!hint) return
  if (auditNote.value.includes(
    )
  }

  function _normalizeRow(raw: any, idx: number): I2AdjustmentRow {
    const category = categoryFromLegacy(raw)
    const entryType = entryTypeFromCategory(category)
    const accountCode = resolveAccountCode(raw)
    const known = I2_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === accountCode)
    const debitAmount = parseAmt(raw.debitAmount ?? raw.debit)
    const creditAmount = parseAmt(raw.creditAmount ?? raw.credit)
    const description = String(raw.description ?? raw.summary ?? 
    )
  } finally {
    isLoadingTb.value = false
  }
}

// ─── 显式发布门（publishToTb，复刻 D2/D4-1 范式） ──────────────────────────────
//
// spec: tb-writeback-explicit-publish-gate Task 13 / Req 1,2。
// 【I2 特例裁定】改造前 I2 靠 useI2Adjudication.onAfterSave **每次保存自动**回写 TB
// （走 per-wp 端点 `POST /api/workpapers/{wpId}/writeback-trial-balance`）。该处理：
//   (a) 不合规：普通保存即写 TB → 违反 Req 1；且 per-wp 端点后端无路由定义
//       （grep backend app 目录零命中），catch 吞 404 ⇒ 运行时实为 no-op（假回写）。
//   (b) 应并入统一显式发布门：现移除 onAfterSave 自动回写，改为用户显式二次确认 →
//       走统一 `POST /workpapers/{wpId}/audit-determination/publish-to-tb`（与其余 I 循环一致）。
// 开发支出为资产类科目（render 下发优先 → 兜底 1704），口径 balance。
const publishing = ref(false)

const {
  rows, auditNote, auditConclusion, summary,
  totalRow, tbRow, diffRow, tbDiff, hasTbDiff, hasAjeApprox,
  addRow, removeRow, updateRow,
  seedFromDetail, syncAjeFromI23, applyTbToUnadj,
  save, saveAuditField,
} = useI2Adjudication({
  allResponses: allResponsesRef,
  tbData: tbDataRef,
  saveResponses: props.saveResponse,
  // 普通保存不再自动回写 TB（Req 1）；TB 回写走显式发布门 publishToTb
})

async function publishToTb() {
  if (publishing.value) return

  try {
    await ElMessageBox.confirm(
      
    )
  } finally {
    publishing.value = false
  }
}

const displayRows = computed(() => [
  ...rows.value.map((r) => ({ ...r, _footer: false })),
  { ...totalRow.value, _footer: true },
  { ...tbRow.value, _footer: true },
  { ...diffRow.value, _footer: true },
])

// ─── 从四表库带入未审数（消费 render 的 adjudication_prefill，按项目名匹配行） ───
//
// 🔴 改造前后端每次 render 都算并下发 `adjudication_prefill`，前端**零消费方**
//    （与 H 循环踩过的 dead output 同型）。I2 是六循环里唯一的**双期**结构：
//    同一行产 `beginUnadj` + `endUnadj` 两格。
const i2SeedLabelField = iCycleSeedSpec(
    )
const isReadonly = computed(() => Boolean(props.isReadonly))
const projectId = computed(() => props.projectId)
const procedureHints = I2_15_PROCEDURE_HINTS

const {
  impairmentRows,
  impairmentSummary,
  prepValidation,
  missingRecoverableRows,
  staleSyncCount,
  highlightedRowIds,
  addImpairmentRow,
  removeImpairmentRow,
  updateImpairmentField,
  seedFromDetail,
  seedRecoverableFromImpairment,
  linkRecoverableToImpairment,
  publishImpairmentToParent,
} = useI2Impairment(wpIdRef, allResponsesRef, {
  onSave: (itemId, value) => {
    props.saveResponse(
    )
const isReadonly = computed(() => Boolean(props.isReadonly))
const samplingVisible = ref(false)
const tb6602 = ref<number | null>(null)
const samplingYear = computed(() => props.year || new Date().getFullYear())

const summary = computed(() => summarizeI2WorkHourRows(rows.value))
const prepValidation = computed(() => validateI2WorkHourPrep(rows.value))

/** I2-9 ↔ I2-10 硬闸门：工时表人员须为 I2-9 已认定研发人员 */
const workHourGate = computed(() => validateWorkHourAgainstStaff(rows.value, parseRows(STAFF_KEY)))

/** I2-5 人工费本期数（人工费 currentAmount），供薪酬勾稽核对 */
const analysisLaborCurrent = computed(() => {
  try {
    const raw = props.allResponses.get(ANALYSIS_BUNDLE_KEY)
    if (!raw) return 0
    const parsed = typeof raw === 
    )
const samplingVisible = ref(false)
const samplingYear = computed(() => props.year || new Date().getFullYear())

const summary = computed(() => summarizeI2StaffRows(rows.value))

const riskHint = computed(() => {
  const parts: string[] = []
  if (summary.value.dispatchCount) parts.push(`劳务派遣 ${summary.value.dispatchCount} 人`)
  if (summary.value.lowRatioCount) parts.push(`工时占比不足50% ${summary.value.lowRatioCount} 人`)
  if (summary.value.nonRdKeywordCount) parts.push(`疑似非研发岗位 ${summary.value.nonRdKeywordCount} 人`)
  return parts.length ? `关注：${parts.join(
    )
const samplingVisible = ref(false)
const samplingYear = computed(() => props.year || new Date().getFullYear())

const {
  rows,
  sampleMeta,
  auditNote,
  auditConclusion,
  summary,
  linkedOutsourceTotal,
  coverageLow,
  coverageLabel,
  coverageTagType,
  populationStale,
  addRow,
  removeRow,
  applySuggestAbnormal,
  syncPopulationFromI27,
  setPopulationAmount,
  persistAll,
  saveAuditNote,
  saveAuditConclusion,
} = useI2OutsourceCheck(toRef(props, 
    )
const {
  rows,
  auditProcess,
  auditNote,
  auditConclusion,
  activeStage,
  summary,
  crossValidateI22Diff,
  i6ExpenseCross,
  addRow,
  removeRow,
  onCostChange,
  isStageEditable,
  persistAll,
  saveField,
  STORAGE_PROCESS,
  STORAGE_NOTE,
  STORAGE_CONCLUSION,
} = useI2ProjectDetail(allResponsesRef, { saveResponse: props.saveResponse })

const stageTabs: I2ProjectStageKey[] = [
  
    )
const {
  rows,
  sampleMeta,
  auditNote,
  auditConclusion,
  summary,
  linkedMaterialTotal,
  coverageLow,
  coverageLabel,
  coverageTagType,
  populationStale,
  addRow,
  removeRow,
  applySuggestAbnormal,
  syncPopulationFromI27,
  setPopulationAmount,
  persistAll,
  saveAuditNote,
  saveAuditConclusion,
} = useI2MaterialCheck(allResponsesRef, { saveResponse: props.saveResponse })

function onRowChange(row: I2MaterialCheckRow) {
  applySuggestAbnormal(row)
}

function handleAddRow() {
  addRow()
}

async function handleSave() {
  await persistAll()
  const rate = summary.value.coverageRate
  const progress = rate == null
    ? (summary.value.sampleCount > 0 ? 40 : 10)
    : Math.max(10, Math.min(100, Math.round(rate)))
  await writeSheetCompletionMarker({
    allResponses: props.allResponses,
    saveResponse: props.saveResponse,
    sheetCode: 
    )
}

/** 抽凭引擎 SampledVoucher → I2-12 行 */
export function mapSampledToI2TargetedRow(s: {
  voucherNo?: string
  voucherDate?: string
  summary?: string | null
  debitAmount?: string | number | null
  creditAmount?: string | number | null
  counterpartAccount?: string | null
  accountName?: string | null
  isHighValue?: boolean
  selectionReason?: string
  abnormal?: boolean
  remark?: string
}): I2TargetedCheckRow {
  const reason = _str(s.selectionReason)
  const isSpecific = !!(s.isHighValue || reason)
  return emptyI2TargetedRow({
    voucherDate: _str(s.voucherDate),
    voucherNo: _str(s.voucherNo),
    businessDesc: _str(s.summary),
    counterpartAccount: _str(s.counterpartAccount),
    projectName: _str(s.accountName),
    debitAmount: _num(s.debitAmount),
    creditAmount: _num(s.creditAmount),
    isSpecific,
    selectionReason: reason || (s.isHighValue ? 
    )
}

export function summarizeI2Targeted(
  rows: I2TargetedCheckRow[],
  periodTotal: number,
): I2TargetedSummary {
  const sampleCount = rows.length
  const checkedDebitTotal = Math.round(rows.reduce((s, r) => s + _num(r.debitAmount), 0) * 100) / 100
  const checkedCreditTotal = Math.round(rows.reduce((s, r) => s + _num(r.creditAmount), 0) * 100) / 100
  const anomalyCount = rows.filter((r) => isAbnormalFlag(r.isAbnormal) || hasFailedCheck(r)).length
  const failCheckCount = rows.filter(hasFailedCheck).length
  const pendingCount = rows.filter((r) => !isRowChecksComplete(r)).length
  const completedCheckCount = rows.filter(isRowChecksComplete).length

  const specificRows = rows.filter((r) => r.isSpecific || !!r.selectionReason)
  const samplingRows = rows.filter((r) => !(r.isSpecific || !!r.selectionReason))
  const specificCount = specificRows.length
  const specificDebitTotal = Math.round(specificRows.reduce((s, r) => s + _num(r.debitAmount), 0) * 100) / 100
  const samplingDebitTotal = Math.round(samplingRows.reduce((s, r) => s + _num(r.debitAmount), 0) * 100) / 100

  let coverageRate: number | null = null
  let specificCoverageRate: number | null = null
  let samplingCoverageRate: number | null = null
  if (periodTotal > 0) {
    coverageRate = Math.round((checkedDebitTotal / periodTotal) * 10000) / 100
    specificCoverageRate = Math.round((specificDebitTotal / periodTotal) * 10000) / 100
    samplingCoverageRate = Math.round((samplingDebitTotal / periodTotal) * 10000) / 100
  }

  return {
    sampleCount,
    checkedDebitTotal,
    checkedCreditTotal,
    periodTotal,
    coverageRate,
    anomalyCount,
    failCheckCount,
    pendingCount,
    completedCheckCount,
    specificCount,
    specificDebitTotal,
    samplingDebitTotal,
    specificCoverageRate,
    samplingCoverageRate,
  }
}

export function formatCoverageLabel(rate: number | null): string {
  if (rate == null) return 
    )
}

function _lineNet(line: any): number {
  return _round2(_num(line?.debitAmount ?? line?.debit) - _num(line?.creditAmount ?? line?.credit))
}

function _lineProjectName(line: any): string {
  return _str(line?.projectName || line?.project || line?.memo || line?.description).trim()
}

/**
 * 从 I2-3 调整净额写入期末调整：
 * 1) 优先按分录行「项目名」精确匹配到审定表行（精确，不标近似）
 * 2) 剩余净额：单行项目直接计入；多行按期末未审占比分摊并标 ajeApprox=true
 */
export function applyAjeFromI23(
  rows: I2AdjudicationRow[],
  adjRows: any[],
): { rows: I2AdjudicationRow[]; applied: number; approx: boolean; totalAje: number; matchedByName: number } {
  let totalAje = 0
  const named: Array<{ name: string; net: number }> = []
  for (const g of adjRows) {
    const lines = Array.isArray(g?.lines) ? g.lines : [g]
    for (const line of lines) {
      if (!_isDevExpAdjLine(line)) continue
      const net = _lineNet(line)
      totalAje = _round2(totalAje + net)
      const pname = _lineProjectName(line)
      if (pname) named.push({ name: pname, net })
    }
  }
  if (Math.abs(totalAje) < 0.005 || !rows.length) {
    return { rows, applied: 0, approx: false, totalAje, matchedByName: 0 }
  }

  const next = rows.map((r) => ({ ...r, ajeApprox: false, endAdj: 0 }))
  const byName = new Map(next.map((r) => [r.projectName.trim(), r]))
  let matchedByName = 0
  let namedAllocated = 0

  for (const { name, net } of named) {
    const row = byName.get(name)
    if (!row) continue
    row.endAdj = _round2(row.endAdj + net)
    row.ajeApprox = false
    matchedByName++
    namedAllocated = _round2(namedAllocated + net)
  }

  const remainder = _round2(totalAje - namedAllocated)
  let approx = false
  let applied = matchedByName

  if (Math.abs(remainder) >= 0.005) {
    const weightSum = next.reduce((s, r) => s + Math.abs(r.endUnadj), 0)
    if (next.length === 1 || weightSum < 0.005) {
      next[0].endAdj = _round2(next[0].endAdj + remainder)
      // 单行全额计入不算近似；若此前已有按名匹配仍有余量，标复核
      if (matchedByName > 0) {
        next[0].ajeApprox = true
        approx = true
      }
      applied = Math.max(applied, 1)
    } else {
      approx = true
      let allocated = 0
      for (let i = 0; i < next.length; i++) {
        const w = Math.abs(next[i].endUnadj) / weightSum
        const amt = i === next.length - 1 ? _round2(remainder - allocated) : _round2(remainder * w)
        next[i].endAdj = _round2(next[i].endAdj + amt)
        next[i].ajeApprox = true
        allocated = _round2(allocated + amt)
      }
      applied = next.length
    }
  }

  for (const r of next) recalcI2AdjudicationRow(r)
  return { rows: next, applied, approx, totalAje, matchedByName }
}

export function serializeI2AdjudicationRow(row: I2AdjudicationRow): Record<string, unknown> {
  return {
    rowId: row.rowId,
    projectName: row.projectName,
    beginUnadj: row.beginUnadj,
    beginAdj: row.beginAdj,
    endUnadj: row.endUnadj,
    endAdj: row.endAdj,
    reasonAnalysis: row.reasonAnalysis,
    increaseCapitalized: row.increaseCapitalized,
    decreaseTransfer: row.decreaseTransfer,
    decreaseExpense: row.decreaseExpense,
    isAutoFilled: row.isAutoFilled,
    ajeApprox: !!row.ajeApprox,
    // 兼容旧消费者
    cipBegin: row.beginAudited,
    unadjusted: row.endUnadj,
    aje: row.endAdj,
    rje: 0,
    audited: row.endAudited,
    remark: row.reasonAnalysis,
  }
}

export function safeParseArray(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 
    ) + 持久化 I2-15-supplement-total
   */
  function publishImpairmentToParent(): { ok: boolean; message: string; supplement: number } {
    const supplement = impairmentSummary.value.totalSupplement
    try {
      if (typeof window !== 
    ) as any
    if (text != null && String(text).trim().length > 0) count++
  }
  if (count === 0) return 0
  if (count >= expectedFields) return 100
  return Math.min(Math.round((count / expectedFields) * 100), 99)
}

const totalCount = computed(() => allSheets.value.length)
const completedCount = computed(() => allSheets.value.filter(r => calcSheetProgress(r.prefix, 3) >= 100).length)
const progressPercent = computed(() => {
  if (totalCount.value === 0) return 0
  const avg = allSheets.value.reduce((sum, r) => sum + calcSheetProgress(r.prefix, 3), 0) / totalCount.value
  return Math.round(avg)
})

// ─── 底稿架构泳道 ─────────────────────────────────────────────────────────────
const COMPONENT_TYPE_MAP: Record<string, string> = {
  I2A: 
    ) continue
        i23AjeNet += _num(line.debitAmount ?? line.debit) - _num(line.creditAmount ?? line.credit)
        i23RowCount++
      }
    }
    const detailAjeNet = calcSubtotal(rows.value.map(rowAjeNet))
    const diff = detailAjeNet - i23AjeNet
    return {
      i23AjeNet,
      detailAjeNet,
      diff,
      hasWarning: i23RowCount > 0 && Math.abs(diff) > TOL,
      i23RowCount,
    }
  })

  function switchSegment(segIndex: number): void {
    if (segIndex >= 0 && segIndex <= 3) activeSegment.value = segIndex
  }

  function setActiveRow(index: number): void {
    activeRowIndex.value = index
  }

  function updateField(rowIndex: number, field: string, value: any): void {
    const row = rows.value[rowIndex]
    if (!row) return
    ;(row as any)[field] = value
    // 旧字段编辑时同步 Excel 列
    if (field === 
    ) continue
    const amt = _num(r.auditedAmount ?? r.yearTotal ?? r.unadjTotal ?? r.amount ?? r.currentAmount)
    const priorAmt = _num(r.priorAudited ?? r.priorUnadj ?? r.priorAmount)
    cur.set(cat, (cur.get(cat) || 0) + amt)
    prior.set(cat, (prior.get(cat) || 0) + priorAmt)
  }
  if (!cur.size) return defaultCompositionRows()

  const used = new Set<string>()
  const rows: I2CompositionRow[] = []
  for (const name of I2_ANALYSIS_DEFAULT_ITEMS) {
    const aliases = I2_ANALYSIS_I6_CATEGORY_ALIASES[name] || []
    const hitKey = [...cur.keys()].find(
      (k) => k.includes(name) || name.includes(k) || k.includes(name.replace(/费|分摊|摊销/g, 
    ) dispatchCount++
    if (r.rdHourRatio != null && r.rdHourRatio < 50) lowRatioCount++
    if (hitNonRdKeyword(r.department, r.position, r.personnelCategory)) nonRdKeywordCount++
  }

  return {
    totalCount: rows.length,
    acceptedCount,
    rejectedCount,
    pendingCount,
    overrideRiskCount,
    dispatchCount,
    lowRatioCount,
    nonRdKeywordCount,
  }
}

/** 行级风险样式标记 */
export function staffRowRiskClass(row: I2StaffCheckRow): string {
  if (row.conclusion === 
    ) existing.add(key)
      n++
    }
    if (n > 0 && !sampleMeta.value.sampleSize) {
      sampleMeta.value.sampleSize = rows.value.length
    }
    return n
  }

  function setPopulationAmount(amount: number, manual: boolean) {
    sampleMeta.value.populationAmount = amount
    sampleMeta.value.populationManual = manual
  }

  function syncPopulationFromI22(): { ok: boolean; message: string } {
    const amt = linkedCapTotal.value.amount
    if (!(amt > 0)) return { ok: false, message: 
    ) ledgerInconsistentCount++
  }

  return {
    projectCount: rows.filter((r) => r.projectName || r.developmentAmount || r.researchAmount).length,
    metCount,
    notMetCount,
    pendingCount,
    totalResearch: Math.round(totalResearch * 100) / 100,
    totalDevelopment: Math.round(totalDevelopment * 100) / 100,
    totalRecognizedIa: Math.round(totalRecognizedIa * 100) / 100,
    ledgerInconsistentCount,
  }
}

/** 从 I2-2 明细带入项目名与资本化起点 */
export function seedRowsFromI2Detail(detailRows: any[]): I2CapitalizationProjectRow[] {
  const out: I2CapitalizationProjectRow[] = []
  for (const r of detailRows ?? []) {
    const name = _str(r?.projectName || r?.name).trim()
    if (!name || name === 
    ) return
    const s = suggestAbnormal(row)
    if (s) row.isAbnormal = s
  }

  function syncPopulationFromI27() {
    const amt = linkedMaterialTotal.value.amount
    sampleMeta.value.populationAmount = amt
    sampleMeta.value.populationManual = false
  }

  function setPopulationAmount(v: number, manual = true) {
    sampleMeta.value.populationAmount = v
    sampleMeta.value.populationManual = manual
  }

  async function persistAll() {
    const save = options?.saveResponse
    if (!save) return
    await save(
    ) return
    const s = suggestOutsourceAbnormal(row)
    if (s) row.isAbnormal = s
  }

  function syncPopulationFromI27() {
    const amt = linkedOutsourceTotal.value.amount
    sampleMeta.value.populationAmount = amt
    sampleMeta.value.populationManual = false
  }

  function setPopulationAmount(v: number, manual = true) {
    sampleMeta.value.populationAmount = v
    sampleMeta.value.populationManual = manual
  }

  async function persistAll() {
    const save = options?.saveResponse
    if (!save) return
    await save(
    ) return emptyCostBlock()
  return emptyCostBlock({
    material: raw.material,
    labor: raw.labor,
    depreciation: raw.depreciation,
    energy: raw.energy,
    outsource: raw.outsource,
    other: raw.other,
    capitalized: raw.capitalized,
    expensed: raw.expensed,
  })
}

/** 旧版扁平费用 → 本期增加块 */
function legacyToIncrease(raw: any): I2ProjectCostBlock {
  const material = _round2(
    _num(raw.materialSubtotal)
    || (_num(raw.materialDirect) + _num(raw.materialAux) + _num(raw.materialFuel)),
  )
  const labor = _round2(
    _num(raw.laborSubtotal)
    || (_num(raw.laborSalary) + _num(raw.laborBonus) + _num(raw.laborInsurance)),
  )
  const depreciation = _round2(
    _num(raw.depSubtotal)
    || (_num(raw.depEquipment) + _num(raw.depBuilding) + _num(raw.depIntangible)),
  )
  const outsource = _num(raw.outsource) || _num(raw.otherOutsource) || 0
  const other = _round2(
    _num(raw.otherSubtotal)
    || (_num(raw.otherDesign) + _num(raw.otherTest) + _num(raw.otherTravel) + _num(raw.otherMisc)),
  )
  // 若旧数据只有费用合计、无资本化拆分，默认全部记入资本化（开发支出底稿语境）
  const nature = _round2(material + labor + depreciation + outsource + other)
  return emptyCostBlock({
    material,
    labor,
    depreciation,
    energy: _num(raw.energy) || _num(raw.materialFuel) || 0,
    outsource,
    other,
    capitalized: _num(raw.capitalized) || nature,
    expensed: _num(raw.expensed) || 0,
  })
}

export function emptyI2ProjectDetailRow(
  partial?: Partial<I2ProjectDetailRow>,
): I2ProjectDetailRow {
  const row: I2ProjectDetailRow = {
    rowId: partial?.rowId || `i27-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    projectCode: 
    ) return null
    return Math.round((natureSummary.value.currentCapitalized - movementSummary.value.increaseInternal) * 100) / 100
  })

  /**
   * 新增费用性质行（源模板 `A15 = ……` 可扩位）。
   * 必须先命名：空名/撞名一律拒绝并返回 false，由组件 prompt 提示（禁产生无名行）。
   */
  function addNatureRow(label: string): boolean {
    const next = addI2NatureRow(natureRows.value, label)
    if (!next) return false
    natureRows.value = next
    return true
  }

  /** 删除自定义费用性质行；源模板固定 6 类不可删（返回 false） */
  function removeNatureRow(rowId: string): boolean {
    const next = removeI2NatureRow(natureRows.value, rowId)
    if (!next) return false
    natureRows.value = next
    return true
  }
  function addMovementRow() { movementRows.value.push(emptyMovementRow()) }
  function addImportantRow() { importantRows.value.push(emptyImportantRow()) }
  function addImpairmentRow() { impairmentRows.value.push(emptyImpairmentRow()) }

  function onMovementChange(row: I2MovementRow) { recalcMovementEnd(row) }

  /**
   * 从 I2-2 明细 / I2-6 资本化时点 / I2-7 项目构成自动取数。
   *
   * 🔴 返回类型曾只声明 `{ ok, message }`，而成功路径实际还返回了
   *    `unmatched` / `fuzzyMatched` 两个清单 ⇒ `tsc` 报 TS2353，
   *    且**消费方在类型上拿不到这两个字段**（只能从拼好的 `message` 里读文本）。
   *    未匹配项目清单是审计师要逐个核对的东西，必须可程序化取用。
   */
  function autoFillFromSources(): {
    ok: boolean
    message: string
    /** 在 I2-6 里找不到资本化时点的项目名（需审计师逐个核对） */
    unmatched?: string[]
    /** 靠模糊匹配对上的项目名（需审计师确认匹配正确） */
    fuzzyMatched?: string[]
  } {
    const map = allResponses.value
    const detail = safeParseArray(map.get(
    ) return raw
    try { return JSON.parse(raw as string) } catch { return null }
  }

  function _loadRows(): void {
    const parsed = _getJson(ITEM_ID_ROWS)
    if (Array.isArray(parsed) && parsed.length > 0) {
      rows.value = parsed.map(normalizeI2DetailRow)
    } else {
      rows.value = []
    }
  }

  function recalcAll(): void {
    for (const row of rows.value) recalcI2DetailRow(row)
  }

  watch(allResponses, () => _loadRows(), { immediate: true })

  const totalRow: ComputedRef<I2DetailRow> = computed(() => {
    const r = rows.value
    const t = emptyRow({
      rowId: 
    ) {
      const natureRaw = safeParseArray(map.get(I2_DISC_KEYS.listedNature))
      natureRows.value = natureRaw.length ? natureRaw.map(normalizeNatureRow) : defaultNatureRows()

      let mov = safeParseArray(map.get(I2_DISC_KEYS.listedMovement)).map(normalizeMovementRow)
      if (!mov.length) {
        mov = safeParseArray(map.get(I2_DISC_KEYS.listedLegacyRows)).map(normalizeMovementRow)
      }
      movementRows.value = mov

      importantRows.value = safeParseArray(map.get(I2_DISC_KEYS.listedImportant)).map(normalizeImportantRow)
      impairmentRows.value = safeParseArray(map.get(I2_DISC_KEYS.listedImpairment)).map(normalizeImpairmentRow)
      noteText.value = readText(map.get(I2_DISC_KEYS.listedNote))
      noteCap.value = readText(map.get(I2_DISC_KEYS.listedNoteCap))
      noteImpairTest.value = readText(map.get(I2_DISC_KEYS.listedNoteImpairTest))
      notePurchased.value = readText(map.get(I2_DISC_KEYS.listedNotePurchased))
      auditNote.value = readText(map.get(I2_DISC_KEYS.listedAuditNote))
      auditConclusion.value = readText(map.get(I2_DISC_KEYS.listedAuditConclusion))
    } else {
      let mov = safeParseArray(map.get(I2_DISC_KEYS.soeMovement)).map(normalizeMovementRow)
      if (!mov.length) {
        mov = safeParseArray(map.get(I2_DISC_KEYS.soeLegacyRows)).map(normalizeMovementRow)
      }
      movementRows.value = mov
      noteText.value = readText(map.get(I2_DISC_KEYS.soeNote))
      auditNote.value = readText(map.get(I2_DISC_KEYS.soeAuditNote))
      auditConclusion.value = readText(map.get(I2_DISC_KEYS.soeAuditConclusion))
    }
  }

  watch(() => allResponses.value, () => load(), { immediate: true })

  const natureSummary = computed(() => summarizeNature(natureRows.value))
  const movementSummary = computed(() => summarizeMovement(movementRows.value))

  /** 性质表资本化合计 vs 滚动内部开发增加 */
  const natureVsMovementDiff = computed(() => {
    if (variant !== 
    ) {
      material += _num(r.increase.material)
      labor += _num(r.increase.labor)
      dep += _num(r.increase.depreciation)
      energy += _num(r.increase.energy)
      outsource += _num(r.increase.outsource)
      other += _num(r.increase.other)
    } else {
      material += _num(r?.materialSubtotal ?? r?.materialDirect)
      labor += _num(r?.laborSubtotal)
      dep += _num(r?.depSubtotal)
      other += _num(r?.otherSubtotal)
    }
  }
  return {
    材料费: _round2(material),
    人工费: _round2(labor),
    折旧费: _round2(dep),
    水电燃气费: _round2(energy),
    外购在研项目: _round2(outsource),
  }
}

export function applyNatureCapitalizedMap(
  rows: I2NatureRow[],
  map: Partial<Record<string, number>>,
): I2NatureRow[] {
  return rows.map((r) => {
    if (r.isTotal) return r
    const v = map[r.name]
    if (v == null) return r
    return { ...r, currentCapitalized: v }
  })
}

export function safeParseArray(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 
    ) {
    const remark = (raw as any).remark ?? (raw as any).conclusion
    if (remark != null) return parseResponseArray(remark)
  }
  return []
}

/** I2-7 本期委外发生额：优先 increase.outsource */
export function sumI27Outsource(raw: unknown): number {
  const rows = parseResponseArray(raw)
  const sum = rows.reduce((s, r) => {
    const staged = _num(r?.increase?.outsource)
      || _num(r?.audited?.outsource)
      || _num(r?.ending?.outsource)
    if (staged) return s + staged
    if (r?.outsourceSubtotal != null) return s + _num(r.outsourceSubtotal)
    if (r?.outsourceAmount != null) return s + _num(r.outsourceAmount)
    if (r?.outsourceFee != null) return s + _num(r.outsourceFee)
    const cat = _str(r?.category || r?.feeType || r?.expenseType)
    if (/委外/.test(cat)) return s + _num(r?.amount ?? r?.debitAmount ?? r?.totalAmount)
    return s
  }, 0)
  return Math.round(sum * 100) / 100
}

/** I2-7 项目名称列表 */
export function listI27ProjectNames(raw: unknown): string[] {
  const rows = parseResponseArray(raw)
  const names = rows.map((r) => _str(r?.projectName).trim()).filter(Boolean)
  return [...new Set(names)]
}

export interface I2DraftAjeInput {
  description: string
  debitAmount?: number
  creditAmount?: number
  indexRef?: string
  remark?: string
  accountCode?: string
  accountName?: string
  reportItem?: string
}

/** 向 I2-3 追加一条账项调整草稿（写入 allResponses + 可选 save） */
export async function appendI23DraftAje(opts: {
  allResponses: Map<string, any>
  saveResponse?: (sheetCode: string, data: Record<string, any>) => Promise<void>
  draft: I2DraftAjeInput
}): Promise<{ rowId: string; total: number }> {
  const KEY = 
    )) continue
      hit = true
      total += Number(item.audited_amount ?? item.unadjusted_amount ?? 0) || 0
    }
    tb6602.value = hit ? Math.abs(total) : null
  } catch {
    tb6602.value = null
  }
}

function handleExportExcel() {
  const data = rows.value.map((r) => ({
    projectName: r.projectName,
    projectCode: r.projectCode,
    projectPeriod: r.projectPeriod,
    staffName: r.staffName,
    hours: r.hours,
    allocationBasis: r.allocationBasis,
    salaryAccrual: r.salaryAccrual,
    customCheck: r.customCheck,
    attachmentIndex: r.attachmentIndex,
    conclusion: r.conclusion,
  }))
  void exportData({
    fileName: `I2-10研发人员工时检查表_${props.projectId || 
    )),
    isTotal: !!raw?.isTotal,
    isAutoFilled: !!raw?.isAutoFilled,
  })
}

export function normalizeImportantRow(raw: any): I2ImportantCapRow {
  return emptyImportantRow({
    rowId: _str(raw?.rowId) || undefined,
    name: _str(raw?.name || raw?.projectName),
    progress: _str(raw?.progress),
    expectedCompletion: _str(raw?.expectedCompletion || raw?.endDate),
    economicBenefit: _str(raw?.economicBenefit),
    capStartDate: _str(raw?.capStartDate),
    capBasis: _str(raw?.capBasis),
  })
}

export function normalizeImpairmentRow(raw: any): I2ImpairmentRow {
  return emptyImpairmentRow({
    rowId: _str(raw?.rowId) || undefined,
    name: _str(raw?.name || raw?.projectName),
    beginBalance: _num(raw?.beginBalance),
    provision: _num(raw?.provision ?? raw?.impairment ?? raw?.capImpairment),
    decrease: _num(raw?.decrease),
    isTotal: !!raw?.isTotal,
  })
}

export function summarizeNature(rows: I2NatureRow[]) {
  const data = rows.filter((r) => !r.isTotal)
  return {
    currentExpensed: _round2(data.reduce((s, r) => s + r.currentExpensed, 0)),
    currentCapitalized: _round2(data.reduce((s, r) => s + r.currentCapitalized, 0)),
    priorExpensed: _round2(data.reduce((s, r) => s + r.priorExpensed, 0)),
    priorCapitalized: _round2(data.reduce((s, r) => s + r.priorCapitalized, 0)),
  }
}

export function summarizeMovement(rows: I2MovementRow[]) {
  const data = rows.filter((r) => !r.isTotal)
  data.forEach(recalcMovementEnd)
  return {
    begin: _round2(data.reduce((s, r) => s + r.beginBalance, 0)),
    increaseInternal: _round2(data.reduce((s, r) => s + r.increaseInternal, 0)),
    increaseOther: _round2(data.reduce((s, r) => s + r.increaseOther, 0)),
    decreaseToIntangible: _round2(data.reduce((s, r) => s + r.decreaseToIntangible, 0)),
    decreaseToExpense: _round2(data.reduce((s, r) => s + r.decreaseToExpense, 0)),
    decreaseOther: _round2(data.reduce((s, r) => s + r.decreaseOther, 0)),
    end: _round2(data.reduce((s, r) => s + r.endBalance, 0)),
  }
}

/** 从 I2-2 明细带入项目滚动 */
export function seedMovementFromI22(detailRows: any[]): I2MovementRow[] {
  return detailRows
    .filter((r) => {
      const name = _str(r?.projectName || r?.name).trim()
      return name && name !== 
    ),
      sourceGroupId: raw.sourceGroupId ? String(raw.sourceGroupId) : undefined,
    }
  }

  function _toPersistShape(list: I2AdjustmentRow[]) {
    return list.map((r, i) => ({
      ...r,
      seq: i + 1,
      debit: r.debitAmount,
      credit: r.creditAmount,
      summary: r.description,
      account: r.accountName,
      entryType: entryTypeFromCategory(String(r.category)),
    }))
  }

  function load(): void {
    let parsed = _getJson(ROWS_KEY)
    if (!Array.isArray(parsed)) parsed = _getJson(LEGACY_ENTRIES_KEY)
    if (Array.isArray(parsed)) {
      rows.value = parsed.map((r, i) => _normalizeRow(r, i))
    } else {
      rows.value = []
    }
    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(allResponses, () => load(), { immediate: true })

  const debitTotal = computed(() => rows.value.reduce((s, r) => s + r.debitAmount, 0))
  const creditTotal = computed(() => rows.value.reduce((s, r) => s + r.creditAmount, 0))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() => Math.abs(balanceDiff.value) < BALANCE_TOLERANCE)

  const groupBalanceIssues = computed(() => {
    const groups = new Map<string, {
      key: string
      description: string
      entryType: string
      debit: number
      credit: number
      rowCount: number
    }>()
    for (const r of rows.value) {
      const et = r.entryType || entryTypeFromCategory(String(r.category))
      const desc = String(r.description || 
    ),
      usePreTaxRate,
      fvDisposal,
      waccParams,
      terminalValue: calc.terminalValue,
      valueInUse: calc.valueInUse,
      fairValueLessDisposal: calc.fairValueLessDisposal,
      recoverableAmount: prefer.recoverableAmount,
      discountedCashFlows: calc.discountedCashFlows,
      discountFactors: calc.discountFactors,
      discountedTerminalValue: calc.discountedTerminalValue,
      pvForecast: calc.pvForecast,
      fairValueSource: calc.fairValueSource,
      disposalTotal: calc.disposalTotal,
      recoverableSource: prefer.recoverableSource,
      costOfEquity: calc.costOfEquity,
      waccAfterTax: calc.waccAfterTax,
      preTaxDiscountRate: calc.preTaxDiscountRate,
      effectiveDiscountRate: calc.effectiveDiscountRate,
      rateInvalid: calc.rateInvalid,
      preferValueInUse,
      preferValueInUseReason,
      priorWacc: _getNum(raw.priorWacc),
      industryWacc: _getNum(raw.industryWacc),
    }
  }

  function _recalcImpairmentRow(row: I2ImpairmentTestRow, refreshConclusion = true): void {
    Object.assign(row, recomputeI2ImpairmentRow(row, { refreshConclusion }))
  }

  function recalcAllImpairment(): void {
    for (const row of impairmentRows.value) _recalcImpairmentRow(row)
    _persistImpairment()
  }

  function _recalcRecoverableRow(row: I2RecoverableTestRow): void {
    _applyCalcToRow(row, _calcRowResult(row))
  }

  function recalcAllRecoverable(): void {
    for (const row of recoverableRows.value) _recalcRecoverableRow(row)
    _persistRecoverable()
    linkRecoverableToImpairment(true)
  }

  function recalcRecoverableRow(rowIndex: number): void {
    const row = recoverableRows.value[rowIndex]
    if (!row) return
    _recalcRecoverableRow(row)
    _persistRecoverable()
  }

  /** I2-16 → I2-15：回填③公允 + ④DCF，重算⑤⑥⑧ */
  function linkRecoverableToImpairment(onlyLinked = false): { ok: boolean; message: string; count: number } {
    const recoverableMap = new Map<string, I2RecoverableTestRow>()
    for (const row of recoverableRows.value) {
      const key = (row.name || 
    ),
    linkedToDcf: Boolean(raw.linkedToDcf),
    sourceDetailRowId: raw.sourceDetailRowId ? String(raw.sourceDetailRowId) : undefined,
  })
}

export function summarizeI2Impairment(rows: I2ImpairmentTestRow[]): I2ImpairmentSummary {
  const s: I2ImpairmentSummary = {
    totalBookValue: 0,
    totalFairValue: 0,
    totalDcf: 0,
    totalRecoverable: 0,
    totalShouldProvision: 0,
    totalAlreadyProvided: 0,
    totalDifference: 0,
    totalSupplement: 0,
    totalReversal: 0,
  }
  for (const r of rows) {
    s.totalBookValue += r.bookValue
    s.totalFairValue += r.fairValueLessDisposal
    s.totalDcf += r.dcfValue
    s.totalRecoverable += r.recoverableAmount
    s.totalShouldProvision += r.shouldProvision
    s.totalAlreadyProvided += r.alreadyProvided
    s.totalDifference += r.difference
    if (r.difference > 0.005) s.totalSupplement += r.difference
    if (r.difference < -0.005) s.totalReversal += -r.difference
  }
  return s
}

export function validateI2ImpairmentPrep(rows: I2ImpairmentTestRow[]): I2ImpPrepValidation {
  const messages: string[] = []
  for (const r of rows) {
    if (!r.name && !r.bookValue && !r.needTest) continue
    if (r.hasIndication === 
    ),
    qualification,
  })
  // emptyI2StaffRow 会写 suggested；若旧数据已有人工结论则保留
  if (raw.conclusion) row.conclusion = String(raw.conclusion)
  row.suggestedConclusion = suggestStaffConclusion(row)
  return row
}

export function persistI2StaffRow(row: I2StaffCheckRow): Record<string, unknown> {
  return {
    rowId: row.rowId,
    staffName: row.staffName,
    gender: row.gender,
    age: row.age,
    education: row.education,
    graduateSchool: row.graduateSchool,
    major: row.major,
    title: row.title,
    position: row.position,
    department: row.department,
    personnelCategory: row.personnelCategory,
    hireDate: row.hireDate,
    employmentForm: row.employmentForm,
    fullTimeRd: row.fullTimeRd,
    rdHourRatio: row.rdHourRatio,
    projects: row.projects,
    attachmentIndex: row.attachmentIndex,
    conclusion: row.conclusion,
    remark: row.remark,
  }
}

export function summarizeI2StaffRows(rows: I2StaffCheckRow[]): I2StaffCheckSummary {
  let acceptedCount = 0
  let rejectedCount = 0
  let pendingCount = 0
  let overrideRiskCount = 0
  let dispatchCount = 0
  let lowRatioCount = 0
  let nonRdKeywordCount = 0

  for (const r of rows) {
    if (r.conclusion === 
    ), { saveResponse: props.saveResponse })

const superDeductionTip = computed(() =>
  buildOutsourceSuperDeductionTip(Number(sampleMeta.value.populationAmount) || 0),
)

function onRowChange(row: I2OutsourceCheckRow) {
  applySuggestAbnormal(row)
}

function handleAddRow() {
  addRow()
}

async function handleSave() {
  await persistAll()
  const rate = summary.value.coverageRate
  const progress = rate == null
    ? (summary.value.sampleCount > 0 ? 40 : 10)
    : Math.max(10, Math.min(100, Math.round(rate)))
  await writeSheetCompletionMarker({
    allResponses: props.allResponses,
    saveResponse: props.saveResponse,
    sheetCode: 
    ).length

  let coverageRate: number | null = null
  if (periodTotal > 0) {
    coverageRate = Math.round((checkedTotal / periodTotal) * 10000) / 100
  }

  return {
    sampleCount,
    checkedTotal,
    periodTotal,
    coverageRate,
    anomalyCount,
    amountMismatchCount,
    missingAcceptanceCount,
    pendingCount,
  }
}

/** 从 I2-7 项目构成明细提取委外相关本期发生额 */
export function extractI27OutsourceTotal(raw: unknown): number {
  return sumI27Outsource(raw)
}

export function formatCoverageLabel(rate: number | null): string {
  if (rate == null) return 
    ).length

  let coverageRate: number | null = null
  if (periodTotal > 0) {
    coverageRate = Math.round((checkedTotal / periodTotal) * 10000) / 100
  }

  return {
    sampleCount,
    checkedTotal,
    periodTotal,
    coverageRate,
    anomalyCount,
    qtyMismatchCount,
    projectMismatchCount,
    pendingCount,
  }
}

/** 从 I2-7 项目构成明细提取材料费合计（优先本期增加.直接材料，兼容旧扁平字段） */
export function extractI27MaterialTotal(raw: unknown): number {
  let rows: any[] = []
  if (Array.isArray(raw)) rows = raw
  else if (typeof raw === 
    ).trim())
        .map((r) => emptyMovementRow({
          name: r.projectName,
          beginBalance: Number(r.begin?.capitalized) || 0,
          increaseInternal: Number(r.increase?.capitalized) || Number(r.totalAmount) || 0,
          isAutoFilled: true,
        }))
    }

    const enriched = enrichFromI26(seeded, importantRows.value, cap)
    movementRows.value = enriched.movement
    if (variant === 
    ).trim(), r]))
    let count = 0
    for (const s of seeded) {
      const key = s.name.trim()
      const prev = byName.get(key)
      if (prev) {
        prev.bookValue = s.bookValue
        prev.alreadyProvided = s.alreadyProvided || prev.alreadyProvided
        prev.sourceDetailRowId = s.sourceDetailRowId
        if (!prev.remark) prev.remark = s.remark
        _recalcImpairmentRow(prev)
        count++
      } else {
        impairmentRows.value.push(s)
        byName.set(key, s)
        count++
      }
    }
    if (count > 0) _persistImpairment()
    return { ok: count > 0, count, message: `已从 I2-2 带入/更新 ${count} 行` }
  }

  const impairmentSummary: ComputedRef<I2ImpairmentSummary> = computed(() =>
    summarizeI2Impairment(impairmentRows.value),
  )

  const prepValidation: ComputedRef<I2ImpPrepValidation> = computed(() =>
    validateI2ImpairmentPrep(impairmentRows.value),
  )

  const syncChecks: ComputedRef<I216SyncCheck[]> = computed(() =>
    buildI216SyncChecks(impairmentRows.value, recoverableRows.value),
  )

  const staleSyncCount = computed(() =>
    syncChecks.value.filter((c) => c.status === 
    )}`,
    })
  }
  return out
}

export function formatLayeredCoverageLabel(summary: I2TargetedSummary): string {
  if (summary.coverageRate == null) return 
    ,
      unadjOpening: calcSubtotal(r.map((x) => x.unadjOpening)),
      unadjIncrease: calcSubtotal(r.map((x) => x.unadjIncrease)),
      unadjDecToIA: calcSubtotal(r.map((x) => x.unadjDecToIA)),
      unadjDecToPL: calcSubtotal(r.map((x) => x.unadjDecToPL)),
      openingAdj: calcSubtotal(r.map((x) => x.openingAdj)),
      ajeIncrease: calcSubtotal(r.map((x) => x.ajeIncrease)),
      ajeDecToIA: calcSubtotal(r.map((x) => x.ajeDecToIA)),
      ajeDecToPL: calcSubtotal(r.map((x) => x.ajeDecToPL)),
      relatedIAAuditedEnd: calcSubtotal(r.map((x) => x.relatedIAAuditedEnd)),
      budget: calcSubtotal(r.map((x) => x.budget)),
      materialCurrent: calcSubtotal(r.map((x) => x.materialCurrent)),
      materialAccum: calcSubtotal(r.map((x) => x.materialAccum)),
      laborCurrent: calcSubtotal(r.map((x) => x.laborCurrent)),
      laborAccum: calcSubtotal(r.map((x) => x.laborAccum)),
      depreciationCurrent: calcSubtotal(r.map((x) => x.depreciationCurrent)),
      depreciationAccum: calcSubtotal(r.map((x) => x.depreciationAccum)),
      amortizationCurrent: calcSubtotal(r.map((x) => x.amortizationCurrent)),
      amortizationAccum: calcSubtotal(r.map((x) => x.amortizationAccum)),
      otherCurrent: calcSubtotal(r.map((x) => x.otherCurrent)),
      otherAccum: calcSubtotal(r.map((x) => x.otherAccum)),
      transferToI1: calcSubtotal(r.map((x) => x.transferToI1)),
      priorEnd: calcSubtotal(r.map((x) => x.priorEnd)),
      expectedValue: calcSubtotal(r.map((x) => x.expectedValue)),
    })
    recalcI2DetailRow(t)
    return t
  })

  const crossValidation = computed(() => {
    const adjEnd = params.adjEndSubtotal?.value ?? 0
    const detailEnd = totalRow.value.auditedEnding
    const diff = detailEnd - adjEnd
    return {
      detailEndTotal: detailEnd,
      adjEndTotal: adjEnd,
      difference: diff,
      hasWarning: adjEnd !== 0 && Math.abs(diff) > TOL,
    }
  })

  /** I2-3 1717 账项净额 vs 明细账项调整合计 */
  const ajeLinkage: ComputedRef<I2AjeLinkage> = computed(() => {
    const i23 = _getJson(I23_ROWS_KEY) || _getJson(LEGACY_I23_KEY)
    let i23AjeNet = 0
    let i23RowCount = 0
    if (Array.isArray(i23)) {
      for (const line of i23) {
        const code = _str(line.accountCode || line.account || 
    ,
    ...partial,
  }
  recalcI2ProjectDetailRow(row)
  return row
}

export function recalcI2ProjectDetailRow(row: I2ProjectDetailRow): void {
  row.ending = calcEndingBlock(row.begin, row.increase, row.decrease)
  row.audited = calcAuditedBlock(row.ending, row.adjustment)
  // 兼容派生字段（供 I2-8 / 旧消费者）
  row.materialSubtotal = row.increase.material
  row.laborSubtotal = row.increase.labor
  row.depSubtotal = row.increase.depreciation
  row.otherSubtotal = _round2(row.increase.energy + row.increase.outsource + row.increase.other)
  row.totalAmount = costTreatmentSum(row.increase) || costNatureSum(row.increase)
}

export function normalizeI2ProjectDetailRow(raw: any): I2ProjectDetailRow {
  const hasNewShape = raw?.begin || raw?.increase || raw?.decrease || raw?.adjustment
  const increase = hasNewShape
    ? normalizeCostBlock(raw.increase)
    : legacyToIncrease(raw)

  const row = emptyI2ProjectDetailRow({
    rowId: _str(raw?.rowId) || undefined,
    projectCode: _str(raw?.projectCode),
    projectName: _str(raw?.projectName),
    periodStart: _str(raw?.periodStart || raw?.startDate),
    periodEnd: _str(raw?.periodEnd || raw?.expectedEnd || raw?.endDate),
    stage: _str(raw?.stage),
    begin: hasNewShape ? normalizeCostBlock(raw.begin) : emptyCostBlock(),
    increase,
    decrease: hasNewShape ? normalizeCostBlock(raw.decrease) : emptyCostBlock(),
    adjustment: hasNewShape ? normalizeCostBlock(raw.adjustment) : emptyCostBlock(),
    remark: _str(raw?.remark),
  })
  return row
}

/** 序列化（只存可编辑字段 + 身份；公式段不存或存亦可被 recalc 覆盖） */
export function serializeI2ProjectDetailRow(row: I2ProjectDetailRow): Record<string, unknown> {
  return {
    rowId: row.rowId,
    projectCode: row.projectCode,
    projectName: row.projectName,
    periodStart: row.periodStart,
    periodEnd: row.periodEnd,
    stage: row.stage,
    begin: { ...row.begin },
    increase: { ...row.increase },
    decrease: { ...row.decrease },
    adjustment: { ...row.adjustment },
    remark: row.remark,
    // 兼容旧消费者 / I2-8 材料总体
    materialSubtotal: row.increase.material,
    materialDirect: row.increase.material,
  }
}

export function summarizeI2ProjectDetail(rows: I2ProjectDetailRow[]): I2ProjectDetailSummary {
  let increaseTotal = 0
  let increaseCapitalized = 0
  let increaseExpensed = 0
  let endingTotal = 0
  let auditedTotal = 0
  let auditedCapitalized = 0
  let auditedExpensed = 0
  let materialIncreaseTotal = 0
  let treatmentMismatchCount = 0
  let rollforwardMismatchCount = 0

  for (const r of rows) {
    const incNature = costNatureSum(r.increase)
    const incTreat = costTreatmentSum(r.increase)
    increaseTotal += incTreat || incNature
    increaseCapitalized += r.increase.capitalized
    increaseExpensed += r.increase.expensed
    endingTotal += costTreatmentSum(r.ending) || costNatureSum(r.ending)
    auditedTotal += costTreatmentSum(r.audited) || costNatureSum(r.audited)
    auditedCapitalized += r.audited.capitalized
    auditedExpensed += r.audited.expensed
    materialIncreaseTotal += r.increase.material

    for (const stage of I2_PROJECT_EDITABLE_STAGES) {
      if (hasTreatmentMismatch(r[stage])) treatmentMismatchCount++
    }
    // 滚动勾稽抽查：期末资本化是否等于期初+增加-减少
    const expectedCap = _round2(r.begin.capitalized + r.increase.capitalized - r.decrease.capitalized)
    if (Math.abs(expectedCap - r.ending.capitalized) > 0.01) rollforwardMismatchCount++
  }

  return {
    rowCount: rows.length,
    increaseTotal: _round2(increaseTotal),
    increaseCapitalized: _round2(increaseCapitalized),
    increaseExpensed: _round2(increaseExpensed),
    endingTotal: _round2(endingTotal),
    auditedTotal: _round2(auditedTotal),
    auditedCapitalized: _round2(auditedCapitalized),
    auditedExpensed: _round2(auditedExpensed),
    materialIncreaseTotal: _round2(materialIncreaseTotal),
    treatmentMismatchCount,
    rollforwardMismatchCount,
  }
}

/** 供 I2-8 提取本期材料增加总体：支持新结构 + 旧扁平字段 */
export function extractMaterialIncreaseTotal(rows: any[]): number {
  const sum = rows.reduce((s, r) => {
    if (r?.increase && typeof r.increase === 
    ,
    ...partial,
  }
}

export function createDefaultCompositionMeta(): I2CompositionMeta {
  return {
    revenueCurrent: 0,
    revenuePrior: 0,
    growthThreshold: I2_ANALYSIS_GROWTH_THRESHOLD,
    revRatioDeltaThreshold: I2_ANALYSIS_REV_RATIO_DELTA_THRESHOLD,
  }
}

export function createDefaultBundle(): I2AnalysisBundle {
  return {
    compositionRows: defaultCompositionRows(),
    compositionMeta: createDefaultCompositionMeta(),
    peerIndicators: [emptyPeerIndicator()],
    perCapitaYoY: emptyPerCapitaYoY(),
    perCapitaPeers: defaultPerCapitaPeers(),
    structuredNotes: emptyStructuredNotes(),
  }
}

/** 从构成合计同步同行指标本期值、人均研发经费 */
export function syncDerivedFromComposition(bundle: I2AnalysisBundle): I2AnalysisBundle {
  const totals = compositionTotals(bundle.compositionRows, bundle.compositionMeta)
  const peerIndicators = bundle.peerIndicators.map((p, i) => {
    if (i === 0 || p.indicator.includes(
    ,
    ...partial,
  })
}

/** 兼容旧版：人员/项目/月份/工时/总工时/结论 */
export function normalizeI2WorkHourRow(raw: any): I2WorkHourCheckRow {
  const hours = _num(raw.hours)
  const totalHours = _num(raw.totalHours)
  return recomputeI2WorkHourRow({
    rowId: raw.rowId || _genId(),
    projectName: String(raw.projectName ?? 
    ,
    beginBalance: 0,
    provision: 0,
    decrease: 0,
    endBalance: 0,
    isTotal: false,
    ...partial,
  }
  row.endBalance = _round2(_num(row.beginBalance) + _num(row.provision) - _num(row.decrease))
  return row
}

export function normalizeNatureRow(raw: any): I2NatureRow {
  return emptyNatureRow({
    rowId: _str(raw?.rowId) || undefined,
    name: _str(raw?.name),
    currentExpensed: _num(raw?.currentExpensed),
    currentCapitalized: _num(raw?.currentCapitalized),
    priorExpensed: _num(raw?.priorExpensed),
    priorCapitalized: _num(raw?.priorCapitalized),
    isTotal: !!raw?.isTotal,
  })
}

export function normalizeMovementRow(raw: any): I2MovementRow {
  // 兼容旧上市单表：increase/decrease
  const increaseInternal = raw?.increaseInternal != null
    ? _num(raw.increaseInternal)
    : _num(raw?.increase ?? raw?.increaseCapitalized ?? raw?.capIncrease)
  const decreaseToIntangible = raw?.decreaseToIntangible != null
    ? _num(raw.decreaseToIntangible)
    : _num(raw?.decrease ?? raw?.transferToI1 ?? raw?.capDecrease)
  return emptyMovementRow({
    rowId: _str(raw?.rowId) || undefined,
    name: _str(raw?.name || raw?.projectName),
    beginBalance: _num(raw?.beginBalance ?? raw?.capBeginAmount ?? raw?.openingBalance),
    increaseInternal,
    increaseOther: _num(raw?.increaseOther),
    decreaseToIntangible,
    decreaseToExpense: _num(raw?.decreaseToExpense ?? raw?.increaseExpensed),
    decreaseOther: _num(raw?.decreaseOther),
    capStartDate: _str(raw?.capStartDate || raw?.capitalizationStart),
    capBasis: _str(raw?.capBasis),
    progress: _str(raw?.progress ?? (raw?.completionRate != null ? `${raw.completionRate}%` : 
    ,
    beginUnadj: 0,
    endUnadj: tbData.value.unadjusted1717 || tbData.value.audited1717 || 0,
    endAdj: (tbData.value.aje1717 || 0) + (tbData.value.rje1717 || 0),
  }))

  /** 差异 = 合计期末审定 − TB期末审定（或未审+调整） */
  const tbDiff = computed(() => {
    const tbAudited = Math.abs(tbData.value.audited1717) > 0.005
      ? tbData.value.audited1717
      : (tbData.value.unadjusted1717 + tbData.value.aje1717 + tbData.value.rje1717)
    return Math.round((summary.value.endAudited - tbAudited) * 100) / 100
  })

  const diffRow = computed(() => emptyI2AdjudicationRow({
    projectName: 
    ,
    beginUnadj: summary.value.beginUnadj,
    beginAdj: summary.value.beginAdj,
    endUnadj: summary.value.endUnadj,
    endAdj: summary.value.endAdj,
    increaseCapitalized: summary.value.increaseCapitalized,
    decreaseTransfer: summary.value.decreaseTransfer,
    decreaseExpense: summary.value.decreaseExpense,
  }))

  const tbRow = computed(() => emptyI2AdjudicationRow({
    projectName: 
    ,
    currentExpensed: 0,
    currentCapitalized: 0,
    priorExpensed: 0,
    priorCapitalized: 0,
    isTotal: false,
    ...partial,
  }
}

export function defaultNatureRows(): I2NatureRow[] {
  return I2_NATURE_DEFAULT_NAMES.map((name) => emptyNatureRow({ name }))
}

/** 行名归一（去首尾空白 + 折叠内部空白），仅用于撞名比较 */
function _normNatureName(name: unknown): string {
  return String(name ?? 
    ,
    currentStructure: null,
    priorStructure: null,
    currentRevRatio: null,
    priorRevRatio: null,
    growthRate: null,
    revRatioChange: null,
    budgetVariance: null,
    budgetVarianceRate: null,
    isAnomaly: false,
    ...partial,
  }, 0, 0, 0, 0)
}

export function defaultCompositionRows(): I2CompositionRow[] {
  return I2_ANALYSIS_DEFAULT_ITEMS.map((name) => emptyCompositionRow({ itemName: name }))
}

export function recomputeAllComposition(
  rows: I2CompositionRow[],
  meta: I2CompositionMeta,
): I2CompositionRow[] {
  const totalCurrent = rows.reduce((s, r) => s + _num(r.currentAmount), 0)
  const totalPrior = rows.reduce((s, r) => s + _num(r.priorAmount), 0)
  const growthThreshold = meta.growthThreshold ?? I2_ANALYSIS_GROWTH_THRESHOLD
  const revDeltaThreshold = meta.revRatioDeltaThreshold ?? I2_ANALYSIS_REV_RATIO_DELTA_THRESHOLD
  return rows.map((r) =>
    recomputeCompositionRow(
      r,
      totalCurrent,
      totalPrior,
      meta.revenueCurrent,
      meta.revenuePrior,
      growthThreshold,
      revDeltaThreshold,
    ),
  )
}

export function compositionTotals(rows: I2CompositionRow[], meta: I2CompositionMeta) {
  const totalCurrent = rows.reduce((s, r) => s + _num(r.currentAmount), 0)
  const totalPrior = rows.reduce((s, r) => s + _num(r.priorAmount), 0)
  const totalBudget = rows.reduce((s, r) => s + _num(r.budgetAmount), 0)
  const growthRate = calcChangeRate(totalCurrent, totalPrior)
  const currentRevRatio = safeRatio(totalCurrent, meta.revenueCurrent)
  const priorRevRatio = safeRatio(totalPrior, meta.revenuePrior)
  const revRatioChange =
    currentRevRatio != null && priorRevRatio != null
      ? currentRevRatio - priorRevRatio
      : null
  const budgetVariance = totalBudget > 0 ? totalCurrent - totalBudget : null
  const budgetVarianceRate = totalBudget > 0 ? safeRatio(budgetVariance ?? 0, totalBudget) : null
  return {
    totalCurrent,
    totalPrior,
    totalBudget,
    growthRate,
    currentRevRatio,
    priorRevRatio,
    revRatioChange,
    budgetVariance,
    budgetVarianceRate,
    /** 研发费用占主营业务收入比（本期） */
    rdToRevenueCurrent: currentRevRatio,
    rdToRevenuePrior: priorRevRatio,
  }
}

export function emptyPeerIndicator(partial?: Partial<I2PeerIndicatorRow>): I2PeerIndicatorRow {
  return {
    rowId: partial?.rowId || _id(
    ,
    endUnadj: Math.round((summary.value.endUnadj - (tbData.value.unadjusted1717 || 0)) * 100) / 100,
    endAdj: 0,
    beginUnadj: 0,
  }))

  // 覆盖 diffRow 的 endAudited 展示用
  const displayDiffEndAudited = computed(() => tbDiff.value)

  const hasTbDiff = computed(() => Math.abs(tbDiff.value) > 0.01)

  function addRow(projectName: string) {
    if (!projectName?.trim()) return
    rows.value.push(emptyI2AdjudicationRow({ projectName: projectName.trim() }))
  }

  function removeRow(rowId: string) {
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
  }

  function updateRow(rowId: string, field: keyof I2AdjudicationRow, value: number | string) {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    const numericFields = [
      
    ,
    impairmentAmount: summary.totalShouldProvision,
  }
}

/** 编制提示（对齐 Excel 底栏 CAS1321 指引） */
export const I2_15_PROCEDURE_HINTS: string[] = [
  
    ,
    increaseCapitalized: 0,
    decreaseTransfer: 0,
    decreaseExpense: 0,
    isAutoFilled: false,
    ...partial,
  }
  recalcI2AdjudicationRow(row)
  return row
}

export function recalcI2AdjudicationRow(row: I2AdjudicationRow): void {
  row.beginAudited = calcBeginAudited(row.beginUnadj, row.beginAdj)
  row.endAudited = calcEndAudited(row.endUnadj, row.endAdj)
  row.changeAmount = calcChangeAmount(row.beginAudited, row.endAudited)
  row.changeRate = calcChangeRate(row.beginAudited, row.changeAmount)
}

/**
 * 兼容旧版：cipBegin/unadjusted/aje/rje/audited/increaseCapitalized…
 */
export function normalizeI2AdjudicationRow(raw: any): I2AdjudicationRow {
  const hasNew = raw?.beginUnadj != null || raw?.endUnadj != null || raw?.beginAudited != null

  let beginUnadj = 0
  let beginAdj = 0
  let endUnadj = 0
  let endAdj = 0

  if (hasNew) {
    beginUnadj = _num(raw.beginUnadj)
    beginAdj = _num(raw.beginAdj)
    endUnadj = _num(raw.endUnadj)
    endAdj = _num(raw.endAdj)
  } else {
    // 旧滚动结构 → 映射到期初/期末审定视图
    beginUnadj = _num(raw.cipBegin ?? raw.beginBalance)
    beginAdj = 0
    endUnadj = _num(raw.unadjusted ?? raw.cipEnd ?? raw.endBalance)
    endAdj = _num(raw.aje) + _num(raw.rje)
    // 若有 audited 且与 unadj+adj 不一致，以 audited 反推 endAdj
    if (raw.audited != null && Math.abs(_num(raw.audited) - (endUnadj + endAdj)) > 0.01) {
      endAdj = _round2(_num(raw.audited) - endUnadj)
    }
  }

  return emptyI2AdjudicationRow({
    rowId: _str(raw?.rowId) || undefined,
    projectName: _str(raw?.projectName || raw?.name),
    beginUnadj,
    beginAdj,
    endUnadj,
    endAdj,
    reasonAnalysis: _str(raw?.reasonAnalysis || raw?.remark),
    increaseCapitalized: _num(raw?.increaseCapitalized),
    decreaseTransfer: _num(raw?.decreaseTransfer ?? raw?.decreaseToIntangible),
    decreaseExpense: _num(raw?.decreaseExpense ?? raw?.decreaseToExpense),
    isAutoFilled: !!raw?.isAutoFilled,
    ajeApprox: !!raw?.ajeApprox,
  })
}

export function summarizeI2Adjudication(rows: I2AdjudicationRow[]): I2AdjudicationSummary {
  const data = rows.filter((r) => r.projectName !== 
    ,
    isTotal: false,
    isAutoFilled: false,
    ...partial,
  }
  recalcMovementEnd(row)
  return row
}

export function recalcMovementEnd(row: I2MovementRow): void {
  row.endBalance = _round2(
    _num(row.beginBalance)
    + _num(row.increaseInternal)
    + _num(row.increaseOther)
    - _num(row.decreaseToIntangible)
    - _num(row.decreaseToExpense)
    - _num(row.decreaseOther),
  )
}

export function emptyImportantRow(partial?: Partial<I2ImportantCapRow>): I2ImportantCapRow {
  return {
    rowId: partial?.rowId || _id(
    ,
    materialCurrent: _num(raw.materialCurrent ?? raw.materialInput),
    materialAccum: _num(raw.materialAccum),
    laborCurrent: _num(raw.laborCurrent ?? raw.laborInput),
    laborAccum: _num(raw.laborAccum),
    depreciationCurrent: _num(raw.depreciationCurrent ?? raw.depreciationInput),
    depreciationAccum: _num(raw.depreciationAccum),
    amortizationCurrent: _num(raw.amortizationCurrent),
    amortizationAccum: _num(raw.amortizationAccum),
    otherCurrent: _num(raw.otherCurrent ?? raw.otherInput),
    otherAccum: _num(raw.otherAccum),
    investmentRemark: _str(raw.investmentRemark),
    validationFlag: _str(raw.validationFlag),
    investmentSource: _str(raw.investmentSource),
    capStartDate: _str(raw.capStartDate || raw.capitalizationStart),
    capBeginAmount: _num(raw.capBeginAmount),
    capIncrease: _num(raw.capIncrease),
    capDecrease: _num(raw.capDecrease ?? raw.capitalizedDecrease),
    transferToI1: _num(raw.transferToI1 ?? raw.transferToIntangible),
    transferDate: _str(raw.transferDate),
    transferAssetName: _str(raw.transferAssetName),
    capAmortization: _num(raw.capAmortization),
    capImpairment: _num(raw.capImpairment),
    completionRate: _num(raw.completionRate),
    acceptanceDate: _str(raw.acceptanceDate),
    expectedValue: _num(raw.expectedValue),
    exceedFlag: _str(raw.exceedFlag),
    conclusion: _str(raw.conclusion),
    priorEnd: _num(raw.priorEnd),
    adjReference: _str(raw.adjReference),
  })
  // 旧数据仅有 capDecrease：拆到转无形后剩余进转损益
  if (!raw.unadjDecToPL && raw.capDecrease != null) {
    const dec = _num(raw.capDecrease)
    if (dec > row.unadjDecToIA) row.unadjDecToPL = dec - row.unadjDecToIA
  }
  recalcI2DetailRow(row)
  return row
}

/** 行级账项调整净额（对 1717：增 - 减） */
export function rowAjeNet(row: I2DetailRow): number {
  return row.ajeIncrease - row.ajeDecToIA - row.ajeDecToPL
}

export function useI2Detail(params: {
  allResponses: Ref<Map<string, any>>
  saveResponses: (sheetCode: string, data: Record<string, any>) => Promise<void>
  adjEndSubtotal?: Ref<number>
}) {
  const { allResponses, saveResponses } = params

  const rows = ref<I2DetailRow[]>([])
  const activeSegment = ref(0)
  const activeRowIndex = ref(-1)

  function _getJson(key: string): any {
    const item = allResponses.value.get(key)
    if (!item) return null
    const raw = item.remark ?? item.conclusion ?? item
    if (raw == null) return null
    if (typeof raw === 
    ,
    }))
    : defaultPerCapitaPeers()

  const structuredNotes = emptyStructuredNotes(raw.structuredNotes || {})

  return syncDerivedFromComposition({
    compositionRows,
    compositionMeta: meta,
    peerIndicators,
    perCapitaYoY,
    perCapitaPeers,
    structuredNotes,
    projectFluctuationRows: Array.isArray(raw.projectFluctuationRows)
      ? raw.projectFluctuationRows
      : undefined,
  })
}

export function summarizeAnalysisAnomalies(bundle: I2AnalysisBundle): {
  compositionAnomalyCount: number
  missingRevenue: boolean
  missingHeadcount: boolean
  peerGapCount: number
} {
  const compositionAnomalyCount = bundle.compositionRows.filter((r) => r.isAnomaly).length
  const missingRevenue = bundle.compositionMeta.revenueCurrent <= 0
  const missingHeadcount = bundle.perCapitaYoY.headcountCurrent <= 0
  const self = bundle.perCapitaPeers.find((r) => r.isSelf)
  let peerGapCount = 0
  if (self && self.avgRdExpense > 0) {
    for (const p of bundle.perCapitaPeers) {
      if (p.isSelf || p.avgRdExpense <= 0) continue
      const gap = Math.abs(p.avgRdExpense - self.avgRdExpense) / self.avgRdExpense
      if (gap > I2_ANALYSIS_GROWTH_THRESHOLD) peerGapCount++
    }
  }
  return { compositionAnomalyCount, missingRevenue, missingHeadcount, peerGapCount }
}

export function buildAnalysisConclusionDraft(bundle: I2AnalysisBundle): string {
  const totals = compositionTotals(bundle.compositionRows, bundle.compositionMeta)
  const anom = summarizeAnalysisAnomalies(bundle)
  const parts = [
    `经对研发费用执行实质性分析：本期研发费用合计 ${fmtMoney(totals.totalCurrent)} 元`,
    totals.rdToRevenueCurrent != null
      ? `，占主营业务收入 ${(totals.rdToRevenueCurrent * 100).toFixed(2)}%`
      : 
    ,
    }))
  }
  return out
}

export function buildI26ConclusionDraft(summary: I2CapitalizationSummary): string {
  const parts = [
    `经检查，共评价研发项目 ${summary.projectCount} 项：`,
    `五条件同时满足可资本化 ${summary.metCount} 项，`,
    `不满足 ${summary.notMetCount} 项，待评价 ${summary.pendingCount} 项。`,
  ]
  if (summary.metCount > 0) {
    parts.push(`可资本化项目开发阶段支出合计 ${summary.totalDevelopment.toFixed(2)} 元；`)
  }
  if (summary.ledgerInconsistentCount > 0) {
    parts.push(`其中 ${summary.ledgerInconsistentCount} 项与无形资产明细勾稽不一致，需跟进。`)
  } else if (summary.notMetCount === 0 && summary.pendingCount === 0 && summary.projectCount > 0) {
    parts.push(
    ,
  saveResponse: props.saveResponse,
  applicableStandards: standardsRef,
})

const {
  natureRows, movementRows, importantRows, impairmentRows,
  noteText, noteCap, noteImpairTest, notePurchased,
  auditNote, auditConclusion,
  natureSummary, movementSummary, natureVsMovementDiff, noteTarget,
  addNatureRow, removeNatureRow, addMovementRow, addImportantRow, addImpairmentRow,
  onMovementChange, autoFillFromSources, getListedSnapshot, persistAll,
} = disc

/**
 * 增行前必先命名（平台底稿交互铁律：动态行新增需命名的必须先 prompt）。
 * 对齐源模板 `附注披露（上市公司）!A15 = ……` 唯一可扩位；撞名由
 * `addI2NatureRow` 纯函数判定并返回 false，此处只负责提示。
 */
async function handleAddNatureRow(): Promise<void> {
  if (props.isReadonly) return
  let name = 
    ,
  }
  Object.assign(row, partial)
  return row
}

/** 导出纯函数供单测 */
export function recalcI2DetailRow(row: I2DetailRow): void {
  // 兼容：若只改了旧字段，回填 Excel 未审列
  if (!row.unadjOpening && row.capBeginAmount) row.unadjOpening = row.capBeginAmount
  if (!row.unadjIncrease && row.capIncrease) row.unadjIncrease = row.capIncrease
  if (!row.unadjDecToIA && row.transferToI1) row.unadjDecToIA = row.transferToI1
  if (!row.unadjDecToPL && row.capDecrease && !row.unadjDecToIA) {
    // 旧版只有合计数：全部视为转损益以外的减少，优先保留 transfer
    row.unadjDecToPL = Math.max(0, row.capDecrease - row.unadjDecToIA)
  }

  row.unadjEnding = calcAssetEndBalance(
    row.unadjOpening,
    row.unadjIncrease,
    row.unadjDecToIA + row.unadjDecToPL,
  )

  row.auditedOpening = row.unadjOpening + row.openingAdj
  row.auditedIncrease = row.unadjIncrease + row.ajeIncrease
  row.auditedDecToIA = row.unadjDecToIA + row.ajeDecToIA
  row.auditedDecToPL = row.unadjDecToPL + row.ajeDecToPL
  row.auditedEnding = calcAssetEndBalance(
    row.auditedOpening,
    row.auditedIncrease,
    row.auditedDecToIA + row.auditedDecToPL,
  )
  row.diffVsIA = row.auditedEnding - row.relatedIAAuditedEnd

  // 回写别名供 I2-6/I2-7/跨 sheet（唯一写回点；新代码请读写 unadj*/audited*）
  syncLegacyAliases(row)

  row.totalCurrent = calcSubtotal([
    row.materialCurrent, row.laborCurrent, row.depreciationCurrent,
    row.amortizationCurrent, row.otherCurrent,
  ])
  row.totalAccum = calcSubtotal([
    row.materialAccum, row.laborAccum, row.depreciationAccum,
    row.amortizationAccum, row.otherAccum,
  ])
  row.capNetValue = calcNetValue(row.capEndAmount, row.capAmortization + row.capImpairment)
  row.yoyChange = calcChangeRate(row.auditedEnd, row.priorEnd)
  row.variance = calcVarianceFromExpected(row.auditedEnd, row.expectedValue)
}

/** 将规范字段同步到遗留别名，避免双轨手工维护 */
export function syncLegacyAliases(row: I2DetailRow): void {
  row.capBeginAmount = row.unadjOpening
  row.capIncrease = row.unadjIncrease
  row.capDecrease = row.unadjDecToIA + row.unadjDecToPL
  row.capEndAmount = row.unadjEnding
  row.transferToI1 = row.auditedDecToIA
  row.auditedEnd = row.auditedEnding
  row.adjustedBalance = row.auditedEnding
  row.progress = row.progress || 0
  if (row.rdProgress && !row.completionRate) {
    const m = String(row.rdProgress).match(/(\d+(?:\.\d+)?)\s*%?/)
    if (m) row.completionRate = Number(m[1])
  }
}

export function normalizeI2DetailRow(raw: any): I2DetailRow {
  const row = emptyRow({
    rowId: _str(raw.rowId) || generateRowId(),
    projectName: _str(raw.projectName),
    projectCode: _str(raw.projectCode || raw.projectNo),
    increaseMethod: _str(raw.increaseMethod) || 
    ,
]

export type I2ProjectCostBlock = Record<I2ProjectCostKey, number>

export interface I2ProjectDetailRow {
  rowId: string
  projectCode: string
  projectName: string
  /** 研发周期起 */
  periodStart: string
  /** 研发周期止 */
  periodEnd: string
  stage: string
  begin: I2ProjectCostBlock
  increase: I2ProjectCostBlock
  decrease: I2ProjectCostBlock
  /** 公式：期初+增加-减少 */
  ending: I2ProjectCostBlock
  adjustment: I2ProjectCostBlock
  /** 公式：期末+调整 */
  audited: I2ProjectCostBlock
  remark: string
  // ── 兼容旧版扁平字段（只读派生，持久化时不依赖）──
  materialSubtotal?: number
  laborSubtotal?: number
  depSubtotal?: number
  otherSubtotal?: number
  totalAmount?: number
}

export interface I2ProjectDetailSummary {
  rowCount: number
  increaseTotal: number
  increaseCapitalized: number
  increaseExpensed: number
  endingTotal: number
  auditedTotal: number
  auditedCapitalized: number
  auditedExpensed: number
  materialIncreaseTotal: number
  treatmentMismatchCount: number
  rollforwardMismatchCount: number
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _str(v: unknown): string {
  return v == null ? 
    ,
]

function blockTotal(block: I2ProjectCostBlock): number {
  const t = costTreatmentSum(block)
  return t || costNatureSum(block)
}

function isTreatmentKey(ck: I2ProjectCostKey): boolean {
  return ck === 
    ,
] as const

/** 占比警戒：≥95% 视为偏高风险；≤20% 且有薪酬视为偏低关注 */
export const I2_WH_HIGH_RATIO = 0.95
export const I2_WH_LOW_RATIO = 0.2

export type I2WorkHourConclusion = (typeof I2_WORKHOUR_CONCLUSION_OPTIONS)[number] | string

export interface I2WorkHourCheckRow {
  rowId: string
  /** 项目名称 */
  projectName: string
  /** 项目号 */
  projectCode: string
  /** 项目起止时间 */
  projectPeriod: string
  /** 研发人员姓名 */
  staffName: string
  /** 月份 YYYY-MM（可选，便于分月抽查） */
  month: string
  /** 研发工时 */
  hours: number
  /** 同期总工时（分功能统计用） */
  totalHours: number
  /** 占比 = 研发工时/总工时（公式） */
  ratio: number
  /** 研发工时分配依据 */
  allocationBasis: string
  /** 研发薪酬计提 */
  salaryAccrual: number
  /** 可增减检查要素（对应 Excel「…」列） */
  customCheck: string
  /** 是否含股份支付 */
  hasShareBasedPay: 
    ,
] as const

export type I2StaffConclusion = (typeof I2_STAFF_CONCLUSION_OPTIONS)[number] | string

export interface I2StaffCheckRow {
  rowId: string
  /** 姓名 */
  staffName: string
  /** 性别 */
  gender: string
  /** 年龄 */
  age: number | null
  /** 学历 */
  education: string
  /** 毕业院校 */
  graduateSchool: string
  /** 所学专业 */
  major: string
  /** 职称 */
  title: string
  /** 职务 */
  position: string
  /** 部门 */
  department: string
  /** 人员类别 */
  personnelCategory: string
  /** 入职日期 YYYY-MM-DD */
  hireDate: string
  /** 聘用形式 */
  employmentForm: string
  /** 是否全时参与该研发项目 */
  fullTimeRd: string
  /** 研发工时占比 %（0-100） */
  rdHourRatio: number | null
  /** 参与研发项目 */
  projects: string
  /** 附件索引号 */
  attachmentIndex: string
  /** 系统建议结论（公式列，可被人工覆盖） */
  suggestedConclusion: I2StaffConclusion
  /** 认定结论（人工） */
  conclusion: I2StaffConclusion
  /** 备注 */
  remark: string
  /** 兼容旧字段：资质合并展示 */
  qualification?: string
}

export interface I2StaffCheckSummary {
  totalCount: number
  acceptedCount: number
  rejectedCount: number
  pendingCount: number
  /** 建议不予认定但人工仍认定为研发人员 */
  overrideRiskCount: number
  /** 劳务派遣人数 */
  dispatchCount: number
  /** 工时占比&lt;50% 人数 */
  lowRatioCount: number
  /** 非研发关键词命中 */
  nonRdKeywordCount: number
}

export function emptyI2StaffRow(partial?: Partial<I2StaffCheckRow>): I2StaffCheckRow {
  const row: I2StaffCheckRow = {
    rowId: partial?.rowId || `i29-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    staffName: 
    ,
] as const

export type I2TargetedCheckMark = (typeof I2_12_CHECK_OPTIONS)[number]

export interface I2TargetedCheckRow {
  rowId: string
  /** 开发支出项目明细 */
  projectName: string
  /** 记账凭证：日期 */
  voucherDate: string
  /** 记账凭证：凭证号 */
  voucherNo: string
  /** 业务内容 */
  businessDesc: string
  /** 对方科目 */
  counterpartAccount: string
  /** 对方明细科目 */
  counterpartDetail: string
  /** 借方金额 */
  debitAmount: number
  /** 贷方金额 */
  creditAmount: number
  /** 支持性文件 */
  supportingDocs: string
  /** 核对内容 1~5 */
  check1: I2TargetedCheckMark | string
  check2: I2TargetedCheckMark | string
  check3: I2TargetedCheckMark | string
  check4: I2TargetedCheckMark | string
  check5: I2TargetedCheckMark | string
  /** 索引号 */
  indexRef: string
  /** 是否异常 */
  isAbnormal: string
  /** 备注说明 */
  remark: string
  /** 是否特定样本（大额/关联方等 100% 检查） */
  isSpecific: boolean
  /** 选取原因（抽凭引擎 selectionReason） */
  selectionReason: string
}

export interface I2TargetedSampleMeta {
  /** 测试总体：凭证笔数 */
  populationCount: number
  /** 测试总体：金额 */
  populationAmount: number
  /** 总体说明 */
  populationDesc: string
  /** 是否手工覆盖总体金额 */
  populationManual: boolean
  /** 特定样本（大额/关联方/异常，100%检查） */
  specificSample: string
  /** 特定样本金额合计（可选） */
  specificAmount: number
  /** 抽样总体说明（剔除特定样本后） */
  samplingPopulationDesc: string
  /** 确定的抽样样本量 */
  sampleSize: number
  /** 抽样方法 */
  sampleMethod: string
  /** 抽样过程 / 索引 */
  sampleProcess: string
  /** 检查比例告警阈值 % */
  coverageThreshold: number
}

/** 原段落型风险关注（Req 13 兼容） */
export interface I2TargetedRiskFocus {
  deductionCompliance: string
  capitalizationRatio: string
  projectProgress: string
  deductionConclusion: string
  capitalizationConclusion: string
  progressConclusion: string
}

export interface I2TargetedSummary {
  sampleCount: number
  checkedDebitTotal: number
  checkedCreditTotal: number
  periodTotal: number
  coverageRate: number | null
  anomalyCount: number
  failCheckCount: number
  pendingCount: number
  completedCheckCount: number
  /** 特定样本行数（selectionReason / isSpecific） */
  specificCount: number
  /** 特定样本借方合计 */
  specificDebitTotal: number
  /** 抽样样本借方合计（非特定） */
  samplingDebitTotal: number
  /** 分层覆盖：特定金额占比% */
  specificCoverageRate: number | null
  /** 分层覆盖：抽样金额占比% */
  samplingCoverageRate: number | null
}

export function emptyI2TargetedRow(partial?: Partial<I2TargetedCheckRow>): I2TargetedCheckRow {
  return {
    rowId: partial?.rowId || `i212-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    projectName: 
    ,
} as const

/** 上市：研发投入按性质（15号文第二十六条） */
export interface I2NatureRow {
  rowId: string
  name: string
  currentExpensed: number
  currentCapitalized: number
  priorExpensed: number
  priorCapitalized: number
  isTotal?: boolean
}

/** 上市/国企共用：开发支出项目滚动 */
export interface I2MovementRow {
  rowId: string
  name: string
  beginBalance: number
  increaseInternal: number
  increaseOther: number
  decreaseToIntangible: number
  decreaseToExpense: number
  /** 国企多一列「其他减少」 */
  decreaseOther: number
  endBalance: number
  /** 续表：资本化时点/依据/进度（修 #REF!） */
  capStartDate: string
  capBasis: string
  progress: string
  isTotal?: boolean
  isAutoFilled?: boolean
}

export interface I2ImportantCapRow {
  rowId: string
  name: string
  progress: string
  expectedCompletion: string
  economicBenefit: string
  capStartDate: string
  capBasis: string
}

export interface I2ImpairmentRow {
  rowId: string
  name: string
  beginBalance: number
  provision: number
  decrease: number
  endBalance: number
  isTotal?: boolean
}

export const I2_NATURE_DEFAULT_NAMES = [
  
    , () => {})

const allResponsesRef = computed(() => props.allResponses)

const {
  rows,
  activeSegment,
  activeRowIndex,
  totalRow,
  crossValidation,
  ajeLinkage,
  activeColumns,
  segments,
  switchSegment,
  setActiveRow,
  updateField,
  addRow,
  removeRow,
  save: saveData,
  syncAjeFromI23,
} = useI2Detail({
  allResponses: allResponsesRef,
  saveResponses: props.saveResponse,
})

const AUDIT_NOTE_KEY = 
    , () => {})

const isReadonly = computed(() => Boolean(props.isReadonly))
const projectId = computed(() => props.projectId)
const showExamples = ref(false)

const {
  rows,
  activeRowId,
  activeRow,
  activeResult,
  summary,
  gateIssues,
  gateBlocked,
  amountReconciles,
  activeTimingIssues,
  auditNote,
  auditConclusion,
  addRow,
  removeRow,
  updateField,
  updateCondition,
  applyAiSuggest,
  seedFromDetail,
  linkCapDateToDetail,
  fillConclusionDraft,
  persistAll,
  saveNote,
  saveConclusion,
} = useI2Capitalization(toRef(props, 
    , () => {})

const {
  backwardRows,
  backwardCriteria,
  backwardBeforeRows,
  backwardAfterRows,
  backwardUnsortedRows,
  backwardCrossPeriodCount,
  backwardCrossPeriodAmount,
  amountMismatchCount,
  lagAnomalyCount,
  crossCheckSummary,
  priorPeriodCutoffDate,
  updateBackwardCriteria,
  addBackwardRow,
  removeBackwardRow,
  updateBackwardRow,
  loadFromAutoSampling,
  importExtractedVouchers,
  save: saveCutoff,
  syncCutoffDateFromProject,
  expandTestWindow,
  draftAjeFromCrossPeriod,
  persistCompletion,
  syncCriteriaToPeer,
  flushAutoSave,
} = useI2Cutoff({
  allResponses: toRef(props, 
    , () => {})

const {
  forwardRows,
  forwardCriteria,
  forwardBeforeRows,
  forwardAfterRows,
  forwardUnsortedRows,
  forwardCrossPeriodCount,
  forwardCrossPeriodAmount,
  amountMismatchCount,
  lagAnomalyCount,
  crossCheckSummary,
  priorPeriodCutoffDate,
  updateForwardCriteria,
  addForwardRow,
  removeForwardRow,
  updateForwardRow,
  loadFromAutoSampling,
  importExtractedVouchers,
  save: saveCutoff,
  syncCutoffDateFromProject,
  expandTestWindow,
  draftAjeFromCrossPeriod,
  persistCompletion,
  syncCriteriaToPeer,
  flushAutoSave,
} = useI2Cutoff({
  allResponses: toRef(props, 
    , () => {})
const isReadonly = computed(() => Boolean(props.isReadonly))

const allResponsesRef = computed(() => props.allResponses)

const {
  bundle,
  compositionSummary,
  anomalySummary,
  updateCompositionMeta,
  updateCompositionField,
  addCompositionRow,
  removeCompositionRow,
  updateThreshold,
  fetchRevenueFromTb,
  updatePeerIndicator,
  addPeerIndicator,
  updatePerCapitaYoY,
  updatePerCapitaPeer,
  addPerCapitaPeer,
  updateStructuredNote,
  seedFromI6,
  buildConclusionDraft,
  rows,
  totalRow,
  anomalyRows,
  hasAnomalies,
  addRow,
  save,
} = useI2Analysis({
  allResponses: allResponsesRef,
  saveResponses: props.saveResponse,
})

const thresholdPct = computed(() => ({
  growth: Math.round((bundle.value.compositionMeta.growthThreshold ?? I2_ANALYSIS_GROWTH_THRESHOLD) * 100),
  revRatioDelta: Math.round((bundle.value.compositionMeta.revRatioDeltaThreshold ?? I2_ANALYSIS_REV_RATIO_DELTA_THRESHOLD) * 1000) / 10,
}))

function onThresholdPctChange(field: 
    , _onI6ExpenseUpdated)
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // I2-2 明细聚合（资本化金额 + 转入金额）
    detailTotals,
    // I6↔I2 联动校验状态
    i6LinkageStatus,
    // I2→I1 转入金额（审定表
    , options: STATUS_OPTIONS },
  ]

  const segmentSummaryColumns: I2DetailColumn[] = [
    { key: 
    , {
          detail: buildI2ImpairmentEventDetail(impairmentSummary.value),
        }))
      }
    } catch { /* silent */ }
    options?.onSave?.(
    , {
      [I2_ADJ_ROWS_KEY]: JSON.stringify(rows.value.map(serializeI2AdjudicationRow)),
      [I2_ADJ_NOTE_KEY]: auditNote.value,
      [I2_ADJ_CONCLUSION_KEY]: auditConclusion.value,
    })
    await onAfterSave?.(summary.value)

    // 发布审定事件 → 附注/跨底稿
    window.dispatchEvent(new CustomEvent(
    , { [KEY]: payload })
  }
  return { rowId, total: next.length }
}

/** 完成度标记：供 I2 目录扫描（多字段抬高进度） */
export async function writeSheetCompletionMarker(opts: {
  allResponses: Map<string, any>
  saveResponse?: (sheetCode: string, data: Record<string, any>) => Promise<void>
  sheetCode: string
  progress: number
  ok: boolean
  detail?: Record<string, any>
}): Promise<void> {
  const prefix = opts.sheetCode
  const keys = [
    `${prefix}-completion`,
    `${prefix}-completion-progress`,
    `${prefix}-completion-ok`,
    `${prefix}-completion-detail`,
  ]
  const progress = Math.max(0, Math.min(100, Math.round(opts.progress)))
  const map = opts.allResponses
  map.set(keys[0], { item_id: keys[0], conclusion: opts.ok ? 
    , { detailTotals, i6LinkageStatus, i1TransferAmount })

// ─── 6.7: useI2DualMode（el-segmented HTML/OO 双模式切换）────────────────────
const dualMode = useI2DualMode({
  wpId: toRef(props, 
    , { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `建议调整分录：借：资产减值损失 ${amt}；贷：开发支出减值准备 ${amt}。`
}

/** 推送给父级（如 K11 资产减值损失汇总）的 `impairment:calculated` CustomEvent detail */
export interface I2ImpairmentEventDetail {
  wpCode: string
  wp_code: string
  sheetCode: string
  totalRequiredProvision: number
  amount: number
  label: string
  impairmentAmount: number
}

/** 构建 impairment:calculated 事件 detail（纯函数，便于单测） */
export function buildI2ImpairmentEventDetail(summary: I2ImpairmentSummary): I2ImpairmentEventDetail {
  return {
    wpCode: 
    >
        <summary>提示（编制审计说明时可参考）</summary>
        <ul>
          <li>记录识别的特别风险、重大异常交易、关联方及会计估计相关事项；</li>
          <li>逐项列示审计调整并交叉索引至 I2-3 / 支持性底稿；</li>
          <li>说明与 TB、明细表、附注披露的勾稽结果。</li>
          <li>「带入调整」：从集中登记按科目 1717 拉取调整分录，逐笔分配到各项目的账项调整列，带入后审定数自动更新并联动附注。</li>
        </ul>
      </details>
    </el-card>

    <el-card shadow=
    >
        <summary>编制提示</summary>
        <ul>
          <li>开发支出（1717）资产借方：期末 = 期初 + 借 − 贷；审定回写 TB(1717)</li>
          <li>I2-6 CAS6 五条件是审计重点：①技术可行性②完成意图③经济利益方式④资源支持⑤可靠计量（须同时满足）</li>
          <li>I6↔I2 双向联动：研发费用（I6 费用化）+ 开发支出（I2 资本化）= 研发总额</li>
          <li>推荐工作流：I2A → I2-2 明细 → I2-6 资本化判断 → I2-8~12 检查 → I2-13/14 截止 → I2-15/16 减值 → I2-3 调整回写 I2-1 → 附注</li>
          <li>各表填妥
    >
      <summary>关于本表与原 Excel 底稿的差异</summary>
      <p>原 Excel I2-2 明细表共 61 列（4 区段：基础信息/本期投入/资本化/期末汇总）；当前 HTML 结构化视图为对齐审计逻辑的分段简化子集，暂未逐列还原全部 61 列。可通过「导入导出」下载模板/数据以核对完整列。</p>
    </details>

    <div class=
    >
      <summary>关于本表与原 Excel 底稿的差异</summary>
      <p>原 Excel I2-7 项目构成表共 73 列（7 个滚动阶段 × 费用性质细分）；当前 HTML 结构化视图按阶段分 Tab 呈现，为对齐审计逻辑的简化子集，暂未逐列还原全部 73 列。可通过「导入导出」下载模板/数据以核对完整列。</p>
    </details>

    <div class=
    >
      <summary>编制提示（CAS8 / 对齐 Excel I2-16）</summary>
      <ul>
        <li>「从 I2-15 建组」拉取有账面的项目；测算完成后「联动回写 I2-15」写入可收回金额并重算应计提/差额</li>
        <li>可收回金额 = MAX(公允净额, 使用价值)；折现率默认税前；现金流与折现率口径须一致</li>
        <li>公允取值优先：销售协议 → 活跃市场 → 估计；开发支出常无可观察市价，可仅测使用价值</li>
        <li>Rm/Kd/Rf 均按<strong>百分比</strong>填写（如市场回报 8 表示 8%，勿填 0.08 或 1.10）</li>
      </ul>
      <ol>
        <li>可收回金额 = MAX(公允价值−处置费用净额, 预计未来现金流量现值)。源模板 N23=MAX(N14,N20)。</li>
        <li>公允净额 N = IF(销售协议&gt;0,协议,IF(活跃市场&gt;0,市场,估计)) − Σ处置费用（法律/税费/搬运/直接/其他）。</li>
        <li>DCF：PV = Σ(CF_t×1/(1+r)^t) + TV/(1+r)^n；TV = CF_n×(1+g)/(r−g)，要求 r&gt;g。</li>
        <li>折现率优先 WACC 税前；未填 D/E 时回退手工折现率。</li>
        <li>永续增长率通常为 0 或负；大于 0 须填写依据，且不应超过行业/经济体长期增长率。</li>
        <li>开发支出减值损失一经确认，以后期间不得转回。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang=
    >
      <summary>编制提示（对齐 Excel I2-12）</summary>
      <ol>
        <li>先填第二节总体与特定样本，再抽样本填入第三节；检查比例=样本借方÷总体（分层：特定+抽样）。</li>
        <li>核对 1~5 对应测试内容说明；选「×」时自动提示异常标记，并可写入调整建议草稿。</li>
        <li>人工/材料/委外细分程序见 I2-9~11；截止见 I2-13/14；资本化条件见 I2-6。</li>
        <li>专项风险关注区保留加计扣除/资本化比例/进度段落结论，可并入结论草稿。</li>
      </ol>
    </details>

    <el-dialog
      v-model=
    > & { ratio?: number } {
  const { ratio: _r, ...rest } = row
  return { ...rest, ratio: row.ratio }
}

export function summarizeI2WorkHourRows(rows: I2WorkHourCheckRow[]): I2WorkHourSummary {
  const s: I2WorkHourSummary = {
    totalCount: rows.length,
    totalHours: 0,
    totalSalary: 0,
    highRatioCount: 0,
    lowRatioCount: 0,
    missingBasisCount: 0,
    sharePayCount: 0,
    pendingCount: 0,
    abnormalCount: 0,
  }
  for (const r of rows) {
    s.totalHours += r.hours
    s.totalSalary += r.salaryAccrual
    if (r.totalHours > 0 && r.ratio >= I2_WH_HIGH_RATIO) s.highRatioCount++
    if (r.totalHours > 0 && r.ratio > 0 && r.ratio <= I2_WH_LOW_RATIO) s.lowRatioCount++
    if (r.hours > 0 && !r.allocationBasis.trim()) s.missingBasisCount++
    if (r.hasShareBasedPay === 
    ]
    if (numFields.includes(field)) {
      ;(row as any)[field] = Number(value) || 0
      _recalcProjectRow(row, _getMateriality())
    }
  }

  const compositionSummary = computed(() =>
    compositionTotals(bundle.value.compositionRows, bundle.value.compositionMeta),
  )
  const anomalySummary = computed(() => summarizeAnalysisAnomalies(bundle.value))

  async function save(): Promise<void> {
    const projectPersist = rows.value.map((row) => ({
      projectName: row.projectName,
      beginAmount: row.beginAmount,
      increaseAmount: row.increaseAmount,
      decreaseAmount: row.decreaseAmount,
      priorEndAmount: row.priorEndAmount,
      expectedValue: row.expectedValue,
      analysisConclusion: row.analysisConclusion,
      anomalyReason: row.anomalyReason,
      auditResponse: row.auditResponse,
      remark: row.remark,
    }))

    const toSave: I2AnalysisBundle = {
      ...bundle.value,
      projectFluctuationRows: projectPersist,
    }

    await saveResponses(
    ] as const

export interface I2DetailRow {
  rowId: string

  // ── Excel 主表：项目 ──
  projectName: string
  projectCode: string
  /** 本期增加方式（内部开发支出/其他增加） */
  increaseMethod: string

  // ── 未审数 B~G ──
  unadjOpening: number
  unadjIncrease: number
  unadjDecToIA: number
  unadjDecToPL: number
  /** 公式 G = B+C-E-F */
  unadjEnding: number

  // ── 期初调整 H + 账项调整 I~K ──
  openingAdj: number
  ajeIncrease: number
  ajeDecToIA: number
  ajeDecToPL: number

  // ── 审定数 L~P（公式）──
  auditedOpening: number
  auditedIncrease: number
  auditedDecToIA: number
  auditedDecToPL: number
  auditedEnding: number

  // ── 核对 Q~T ──
  relatedIAAuditedEnd: number
  /** 公式 R = P-Q */
  diffVsIA: number
  rdProgress: string
  remark: string

  // ── 兼容旧字段 / 跨 sheet ──
  approvalDate: string
  phase: string
  manager: string
  startDate: string
  endDate: string
  budget: number
  progress: number
  capitalizationStart: string
  status: string
  materialCurrent: number
  materialAccum: number
  laborCurrent: number
  laborAccum: number
  depreciationCurrent: number
  depreciationAccum: number
  amortizationCurrent: number
  amortizationAccum: number
  otherCurrent: number
  otherAccum: number
  totalCurrent: number
  totalAccum: number
  investmentRemark: string
  validationFlag: string
  investmentSource: string
  capStartDate: string
  /** @deprecated alias → unadjOpening */
  capBeginAmount: number
  /** @deprecated alias → unadjIncrease */
  capIncrease: number
  /** @deprecated = unadjDecToIA + unadjDecToPL */
  capDecrease: number
  /** @deprecated alias → unadjEnding */
  capEndAmount: number
  /** @deprecated alias → auditedDecToIA / unadjDecToIA */
  transferToI1: number
  transferDate: string
  transferAssetName: string
  capAmortization: number
  capImpairment: number
  capNetValue: number
  completionRate: number
  acceptanceDate: string
  /** @deprecated alias → auditedEnding */
  auditedEnd: number
  adjustedBalance: number
  yoyChange: number | null
  expectedValue: number
  variance: number
  exceedFlag: string
  conclusion: string
  priorEnd: number
  adjReference: string
}

export interface I2AjeLinkage {
  i23AjeNet: number
  detailAjeNet: number
  diff: number
  hasWarning: boolean
  i23RowCount: number
}

export type I2DetailColType = 
    ],
}

// ─── （一）构成分析 ───────────────────────────────────────────────────────────

export interface I2CompositionRow {
  rowId: string
  itemName: string
  currentAmount: number
  priorAmount: number
  /** 预算金额（可选，>0 时纳入预算差异分析） */
  budgetAmount: number
  /** 变动分析（定性） */
  varianceAnalysis: string
  /** 公式：结构比 = 金额 / 合计 */
  currentStructure: number | null
  priorStructure: number | null
  /** 公式：占主营收入比 */
  currentRevRatio: number | null
  priorRevRatio: number | null
  /** 公式：增长比例 */
  growthRate: number | null
  /** 公式：占收入比变动 = 本期占比 − 上期占比 */
  revRatioChange: number | null
  /** 公式：预算差异 = 本期金额 − 预算金额 */
  budgetVariance: number | null
  /** 公式：预算差异率 = 预算差异 / 预算金额（预算≤0 时为 null） */
  budgetVarianceRate: number | null
  /** 是否超阈值 */
  isAnomaly: boolean
}

export interface I2CompositionMeta {
  /** 主营业务收入-本期 */
  revenueCurrent: number
  /** 主营业务收入-上年同期 */
  revenuePrior: number
  /** 同比/结构比变动阈值（可配置，默认 0.3） */
  growthThreshold: number
  /** 占收入比变动阈值（可配置，默认 0.02） */
  revRatioDeltaThreshold: number
}

// ─── （二）同行业费用指标 ─────────────────────────────────────────────────────

export interface I2PeerIndicatorRow {
  rowId: string
  indicator: string
  current: number | null
  peerA: number | null
  peerB: number | null
  peerC: number | null
  analysis: string
}

// ─── （三）人均同期 ───────────────────────────────────────────────────────────

export interface I2PerCapitaYoY {
  /** 研发人员薪酬总额 */
  staffCostCurrent: number
  staffCostPrior: number
  /** 研发人员人数 */
  headcountCurrent: number
  headcountPrior: number
  /** 研发经费总额（通常=构成合计） */
  rdExpenseCurrent: number
  rdExpensePrior: number
  /** 材料费总额 */
  materialCurrent: number
  materialPrior: number
  analysis: string
  /** 公式列 */
  avgSalaryCurrent: number | null
  avgSalaryPrior: number | null
  avgRdCurrent: number | null
  avgRdPrior: number | null
  avgMaterialCurrent: number | null
  avgMaterialPrior: number | null
  avgSalaryGrowth: number | null
  avgRdGrowth: number | null
  avgMaterialGrowth: number | null
}

// ─── （四）人均同行业 ─────────────────────────────────────────────────────────

export interface I2PerCapitaPeerRow {
  rowId: string
  companyName: string
  headcount: number
  avgSalary: number
  avgRdExpense: number
  avgMaterial: number
  analysis: string
  isSelf: boolean
}

// ─── 结构化说明 ───────────────────────────────────────────────────────────────

export interface I2AnalysisStructuredNotes {
  compositionChange: string
  yoyAnomaly: string
  peerAnomaly: string
  budgetAnomaly: string
  perCapitaAnomaly: string
}

export interface I2AnalysisBundle {
  compositionRows: I2CompositionRow[]
  compositionMeta: I2CompositionMeta
  peerIndicators: I2PeerIndicatorRow[]
  perCapitaYoY: I2PerCapitaYoY
  perCapitaPeers: I2PerCapitaPeerRow[]
  structuredNotes: I2AnalysisStructuredNotes
  /** Spec Req4 兼容：开发支出项目波动行（旧 I2-5-rows） */
  projectFluctuationRows?: any[]
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _id(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

/** 安全比率；分母≤0 返回 null（避免 #DIV/0!） */
export function safeRatio(numerator: number, denominator: number): number | null {
  if (!Number.isFinite(numerator) || !Number.isFinite(denominator)) return null
  if (Math.abs(denominator) < 1e-9) return null
  return numerator / denominator
}

export function recomputeCompositionRow(
  row: I2CompositionRow,
  totalCurrent: number,
  totalPrior: number,
  revenueCurrent: number,
  revenuePrior: number,
  growthThreshold = I2_ANALYSIS_GROWTH_THRESHOLD,
  revDeltaThreshold = I2_ANALYSIS_REV_RATIO_DELTA_THRESHOLD,
): I2CompositionRow {
  const currentAmount = _num(row.currentAmount)
  const priorAmount = _num(row.priorAmount)
  const budgetAmount = _num(row.budgetAmount)
  const currentStructure = safeRatio(currentAmount, totalCurrent)
  const priorStructure = safeRatio(priorAmount, totalPrior)
  const currentRevRatio = safeRatio(currentAmount, revenueCurrent)
  const priorRevRatio = safeRatio(priorAmount, revenuePrior)
  const growthRate = calcChangeRate(currentAmount, priorAmount)
  const revRatioChange =
    currentRevRatio != null && priorRevRatio != null
      ? currentRevRatio - priorRevRatio
      : null
  const budgetVariance = budgetAmount > 0 ? currentAmount - budgetAmount : null
  const budgetVarianceRate = budgetAmount > 0 ? safeRatio(budgetVariance ?? 0, budgetAmount) : null

  const isAnomaly =
    (growthRate != null && Math.abs(growthRate) > growthThreshold)
    || (revRatioChange != null && Math.abs(revRatioChange) > revDeltaThreshold)
    || (currentStructure != null && priorStructure != null
      && Math.abs(currentStructure - priorStructure) > growthThreshold)
    || (budgetVarianceRate != null && Math.abs(budgetVarianceRate) > growthThreshold)

  return {
    ...row,
    currentAmount,
    priorAmount,
    budgetAmount,
    currentStructure,
    priorStructure,
    currentRevRatio,
    priorRevRatio,
    growthRate,
    revRatioChange,
    budgetVariance,
    budgetVarianceRate,
    isAnomaly,
  }
}

export function emptyCompositionRow(partial?: Partial<I2CompositionRow>): I2CompositionRow {
  return recomputeCompositionRow({
    rowId: partial?.rowId || _id(
    事件
   * I6 发布时携带 { expense, total }，I2 据此更新联动校验状态。
   */
  function _onI6ExpenseUpdated(event: Event): void {
    const detail = (event as CustomEvent<I6ExpenseEventDetail>).detail
    if (detail && typeof detail === 
    列合计
   */
  /**
   * I2→I1 转入金额：优先 I2-1 审定表「转无形」列合计；
   * 若审定表未填/为 0，兜底用 I2-2 明细转入合计（避免只填明细时事件不发）。
   */
  const i1TransferAmount: ComputedRef<number> = computed(() => {
    let total = 0
    for (const row of adjudicationRows.value) {
      total += _getNum(row.decreaseTransfer)
    }
    if (Math.abs(total) >= 0.005) return total
    return detailTotals.value.transferred
  })

  // ─── i2Capitalized: I2 资本化金额合计（供 I6 联动校验） ────────────────

  /**
   * I2 资本化金额合计：优先从 I2-1 审定表取
    合计应 = detailTotals.transferred
   */
  const detailTotals: ComputedRef<I2DetailTotals> = computed(() => {
    let capitalized = 0
    let transferred = 0

    for (const row of detailRows.value) {
      const r = row as any
      // 优先审定期末 / 审定转无形；兼容旧字段与 Excel 新字段
      capitalized += _getNum(
        r.auditedEnding ?? r.auditedEnd ?? r.capEndAmount ?? r.capitalizedEnd ?? r.unadjEnding,
      )
      transferred += _getNum(
        r.auditedDecToIA ?? r.transferToI1 ?? r.transferToIntangible ?? r.unadjDecToIA,
      )
    }

    return { capitalized, transferred }
  })

  // ─── i1TransferAmount: I2-1 审定表
    合计，
   * 若审定表无数据则 fallback 到 I2-2 明细的 capitalizedEnd 合计。
   */
  const i2Capitalized = computed<number>(() => {
    // 优先从 I2-1 审定表取审定数合计
    let audited = 0
    let hasAdjudication = false
    for (const row of adjudicationRows.value) {
      const val = _getNum(row.audited)
      if (val !== 0) hasAdjudication = true
      audited += val
    }
    if (hasAdjudication) return audited

    // fallback: 从 I2-1 期末余额合计
    let cipEnd = 0
    for (const row of adjudicationRows.value) {
      cipEnd += _getNum(row.cipEnd)
    }
    if (cipEnd !== 0) return cipEnd

    // 最终 fallback: I2-2 明细合计
    return detailTotals.value.capitalized
  })

  // ─── i6LinkageStatus: I6↔I2 校验状态（Req 9.3: VR-I6-01）─────────────

  /**
   * I6↔I2 联动校验状态：
   * - expense: I6 费用化金额（来自 EventBus 
    （I2→I6）───────

  /**
   * 当 I2 资本化金额变化时，发布事件通知 I6 同步校验。
   * I6 订阅此事件后更新自身的联动校验面板。
   */
  watch(i2Capitalized, (newVal) => {
    const total = _i6Total.value > 0
      ? _i6Total.value
      : newVal + _i6Expense.value
    window.dispatchEvent(new CustomEvent(
    ）
   * - total: 研发总额（来自 EventBus or 本地计算 expense + capitalized）
   * - isBalanced: I6费用化 + I2资本化 = 研发总额（允许±0.01精度）
   *
   * Req 9.3: 校验 I6费用化金额 + I2资本化金额 = 研发总额
   * Req 9.4: 校验失败时显示红色警告
  I3: 66 个
    

// ─── Types ───────────────────────────────────────────────────────────────────

/** CGU内其他资产 */
export interface OtherAsset {
  name: string
  bookValue: number
  /** 可选：单项可收回金额，用于第二分摊下限（CAS8 §23） */
  recoverableAmount?: number | null
}

/** 其他资产分摊明细 */
export interface OtherAllocation {
  name: string
  amount: number
}

/**
 * I3-6 CGU行（减值测试）
 * A/B1/B2 对齐 Excel「账面价值(1)」结构
 */
export interface CguRow {
  rowId: string
  /** 资产组(CGU)名称 */
  cguName: string
  /**
   * A：对应资产组账面价值（合并报表层面，不含商誉）
   * 若未单独录入，回退为 Σ(otherAssets.bookValue)
   */
  assetGroupCarrying: number
  /**
   * B1：分摊的商誉账面价值（母公司份额）
   * 兼容旧字段 goodwillAmount
   */
  goodwillB1: number
  /** B2：未确认的少数股东商誉 */
  minorityB2: number
  /**
   * @deprecated 兼容旧 API / 旧持久化：等价于 goodwillB1
   */
  goodwillAmount: number
  /** 其他资产列表（展开明细 & 第二分摊基数） */
  otherAssets: OtherAsset[]
  /** ① 公允价值减处置费用后的净额（可选） */
  fairValueLessCost: number | null
  /** ② 预计未来现金流量现值 / 使用价值（可选） */
  valueInUse: number | null
  /**
   * 可收回金额(2)：优先 = MAX(①,②)；若均未填则用手工值
   * 兼容旧数据直接存此字段
   */
  recoverableAmount: number
  /** 减值原因及说明 */
  impairmentReason: string
  /** computed: 合计(1)=A+B1+B2 */
  cguBookValue: number
  /** computed: 减值金额 = MAX(cguBookValue - recoverableAmount, 0) */
  impairmentAmount: number
  /**
   * computed: 第一分摊—冲减全额商誉(B1+B2)
   * = MIN(impairmentAmount, B1+B2)
   */
  goodwillImpairment: number
  /**
   * computed: 合并报表确认的商誉减值（仅母公司份额）
   * = goodwillImpairment × B1/(B1+B2)；B2=0 时等于 goodwillImpairment
   */
  consolidatedGwImpairment: number
  /** computed: 第二分摊—其他资产按比例 */
  otherAllocations: OtherAllocation[]
}

/** CGU合计行 */
export interface CguSummary {
  totalAssetGroupCarrying: number
  totalGoodwillB1: number
  totalMinorityB2: number
  totalGoodwill: number
  totalOtherAssets: number
  totalCguBookValue: number
  totalRecoverable: number
  totalImpairment: number
  totalGoodwillImpairment: number
  /** 合并报表应确认商誉减值合计 */
  totalConsolidatedGwImpairment: number
  totalOtherImpairment: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_CGU_ROWS = 
    

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** I3-2 明细行（兼容旧字段 + 滚动字段） */
export interface I3DetailRowRaw {
  rowId?: string
  investee?: string
  acquisitionDate?: string
  consideration?: number
  mergerCost?: number
  netAssetFairValue?: number
  goodwillOriginal?: number
  costAudited?: number
  accImpairmentBegin?: number
  currentImpairment?: number
  accImpairmentEnd?: number
  impIncrease?: number
  impAudited?: number
  netValueEnd?: number
  goodwillNetValue?: number
  cguName?: string
  costAje?: number
  impAje?: number
  costIncrease?: number
  entryGoodwillCalc?: number
}

export interface I3AdjustmentRowRaw {
  rowId?: string
  description?: string
  category?: string
  entryType?: string
  reportItem?: string
  accountCode?: string
  accountName?: string
  noteItem?: string
  summary?: string
  debitAmount?: number
  creditAmount?: number
  debit?: number
  credit?: number
  indexRef?: string
  remark?: string
  /** 可选：匹配 I3-2 被投资单位 */
  investee?: string
}

export interface I3ImpairmentTestRowRaw {
  rowId?: string
  cguName?: string
  goodwillAmount?: number
  goodwillB1?: number
  minorityB2?: number
  cguBookValue?: number
  recoverableAmount?: number
  impairmentAmount?: number
  goodwillImpairment?: number
  /** 合并报表确认（母公司份额）— 优先用于 I3-1 / I3-2 */
  consolidatedGwImpairment?: number
  otherAssetImpairment?: number
  otherAllocations?: { name: string; amount: number }[]
}

export interface I3RecoverableResultRaw {
  rowId?: string
  cguName?: string
  name?: string
  fairValueLessDisposal?: number
  fairValueLessCost?: number
  valueInUse?: number
  recoverableAmount?: number
}

/** I3-7 → I3-6 可收回明细（公允净额 + 使用价值） */
export interface I3RecoverableDetail {
  fairValueLessDisposal?: number
  valueInUse?: number
  recoverableAmount: number
}

export interface I3InitialValueRowRaw {
  rowId?: string
  investee?: string
  projectName?: string
  mergerCost?: number
  netAssetFairValue?: number
  netAssetFV?: number
  equityRatio?: number
  goodwillAmount?: number
  bookedAmount?: number
  sameControl?: string
}

export interface I3DetailTotals {
  goodwillOriginalTotal: number
  accImpairmentTotal: number
  netValueTotal: number
  currentImpairmentTotal: number
  byCgu: Record<string, {
    goodwillOriginal: number
    accImpairment: number
    netValue: number
    currentImpairment: number
  }>
}

export interface I3ImpairmentResult {
  totalImpairment: number
  byCgu: Record<string, {
    impairmentAmount: number
    goodwillImpairment: number
    consolidatedGwImpairment: number
    otherImpairment: number
    recoverableAmount: number
  }>
}

export interface I3AdjustmentSync {
  totalAje: number
  totalRje: number
  /** 按被投资单位拆分的商誉科目 AJE 净额（借-贷），供 I3-2 costAje/impAje */
  byInvestee: Record<string, { costAje: number; impAje: number; net: number }>
}

export interface I3DisclosureData {
  [key: string]: number
}

export interface I3EntryVariance {
  investee: string
  entryCalc: number
  costIncrease: number
  costAudited: number
  diffVsIncrease: number
  diffVsAudited: number
}

/** I3-3 与 I3-2 账项调整列差异 */
export interface I3AjeVariance {
  investee: string
  detailCostAje: number
  detailImpAje: number
  adjCostAje: number
  adjImpAje: number
  costDiff: number
  impDiff: number
  /** I3-3 有金额但 I3-2 无该被投资单位行 */
  missingOnDetail: boolean
}

function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function _getNum(val: any): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

function _normName(s: string | undefined | null): string {
  return String(s || 
    

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** 附注子节定义 */
export interface I3DisclosureSection {
  key: string
  title: string
  hasTable: boolean
  hasDynamicRows: boolean
  hasNoteText: boolean
}

/** 附注商誉变动矩阵行（原值/减值）
 * 上市底稿可按 Excel 细列填增减分项；increase/decrease 为汇总，同步附注时用汇总列。
 */
export interface I3DisclosureMatrixRow {
  rowId: string
  investee: string              // 被投资单位(CGU)
  beginBalance: number          // 期初余额
  /** 汇总：本期增加（= 分项之和） */
  increase: number
  /** 汇总：本期减少（= 分项之和） */
  decrease: number
  endBalance: number            // 期末余额
  isAutoFilled: boolean         // 是否跨sheet自动取数
  /** 合计行且无明细拆分时需提示补 I3-2 */
  needsDetailSplit?: boolean
  // ── 上市原值细列（企业合并 / 合营 / 其他）──
  incBusinessCombination?: number
  incJoint?: number
  incOther?: number
  decDisposal?: number
  decOther?: number
  // ── 上市减值细列（计提 / 其他增加 / 处置 / 其他减少）──
  // increase 对应计提；以下为补充分项
  impIncOther?: number
  impDecDisposal?: number
  impDecOther?: number
}

/** 上市：关键假设参数行（毛利率/增长率/折现率） */
export interface I3AssumptionParamRow {
  rowId: string
  /** 资产组 / 业务名称 */
  label: string
  grossMargin: string
  growthRate: string
  discountRate: string
  remark: string
}

/** 原值行：分项汇总 → increase/decrease/endBalance */
export function recalcBookValueRow(row: I3DisclosureMatrixRow): void {
  const incBc = Number(row.incBusinessCombination) || 0
  const incJ = Number(row.incJoint) || 0
  const incO = Number(row.incOther) || 0
  const decD = Number(row.decDisposal) || 0
  const decO = Number(row.decOther) || 0
  const hasDetail = [incBc, incJ, incO, decD, decO].some((x) => Math.abs(x) > 0.0005)
  if (hasDetail) {
    row.increase = Math.round((incBc + incJ + incO) * 100) / 100
    row.decrease = Math.round((decD + decO) * 100) / 100
  }
  row.endBalance = Math.round((Number(row.beginBalance) + Number(row.increase) - Number(row.decrease)) * 100) / 100
}

/** 减值行：increase=计提；细列其他增加/处置/其他减少；期末含细列 */
export function recalcImpairmentRow(row: I3DisclosureMatrixRow): void {
  const provision = Number(row.increase) || 0
  const incO = Number(row.impIncOther) || 0
  const decD = Number(row.impDecDisposal) || 0
  const decO = Number(row.impDecOther) || 0
  const hasDecDetail = [decD, decO].some((x) => Math.abs(x) > 0.0005)
  if (hasDecDetail) {
    row.decrease = Math.round((decD + decO) * 100) / 100
  }
  const totalInc = provision + incO
  const totalDec = Number(row.decrease) || 0
  row.endBalance = Math.round((Number(row.beginBalance) + totalInc - totalDec) * 100) / 100
}

/** 同步用：原值/减值行的汇总增减（含细列） */
export function matrixRowSyncAmounts(
  row: I3DisclosureMatrixRow,
  layer: 
    

export {
  type I3TargetedCheckRow,
  type I3TargetedSampleMeta,
  type I3TargetedRiskFocus,
  type I3TargetedSummary,
  type I3TargetedAdjDraft,
  emptyI3TargetedRow,
  I3_5_DEFAULT_COVERAGE_THRESHOLD,
  I3_5_TEST_CONTENT,
  I3_5_TEST_REASONS,
  I3_5_SAMPLE_METHODS,
  I3_5_CHECK_OPTIONS,
  I3_5_OBJECTIVES,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  isAbnormalFlag,
  hasFailedCheck,
  buildI3TargetedConclusionDraft,
  buildI3TargetedAdjDrafts,
  mapSampledToI3TargetedRow,
} from 
    
      const impairment = _getNum(row.impairmentAmount)
      const gwImpairment = _getNum(row.goodwillImpairment)
      // 优先合并确认；无 B2 时与全额商誉分摊相等
      const consol = row.consolidatedGwImpairment != null
        ? _getNum(row.consolidatedGwImpairment)
        : gwImpairment
      const otherFromAlloc = Array.isArray(row.otherAllocations)
        ? row.otherAllocations.reduce((s, a) => s + _getNum(a.amount), 0)
        : 0
      const otherImpairment = _getNum(row.otherAssetImpairment) || otherFromAlloc
      const recoverable = _getNum(row.recoverableAmount)

      totalImpairment += consol

      byCgu[cgu] = {
        impairmentAmount: impairment,
        goodwillImpairment: gwImpairment,
        consolidatedGwImpairment: consol,
        otherImpairment,
        recoverableAmount: recoverable,
      }
    }

    return { totalImpairment, byCgu }
  })

  /** I3-6 → I3-2：按 CGU 的合并确认商誉减值 */
  const impairmentByCgu: ComputedRef<Record<string, number>> = computed(() => {
    const map: Record<string, number> = {}
    for (const [cgu, v] of Object.entries(impairmentResult.value.byCgu)) {
      map[cgu] = v.consolidatedGwImpairment
    }
    return map
  })

  const recoverableDetailByCgu: ComputedRef<Record<string, I3RecoverableDetail>> = computed(() => {
    const result: Record<string, I3RecoverableDetail> = {}
    for (const row of recoverableRows.value) {
      const cgu = row.cguName || row.name || 
    
      if (!byCgu[cgu]) {
        byCgu[cgu] = { goodwillOriginal: 0, accImpairment: 0, netValue: 0, currentImpairment: 0 }
      }
      byCgu[cgu].goodwillOriginal += original
      byCgu[cgu].accImpairment += accImp
      byCgu[cgu].netValue += netVal
      byCgu[cgu].currentImpairment += curImp
    }

    return { goodwillOriginalTotal, accImpairmentTotal, netValueTotal, currentImpairmentTotal, byCgu }
  })

  const impairmentResult: ComputedRef<I3ImpairmentResult> = computed(() => {
    let totalImpairment = 0
    const byCgu: I3ImpairmentResult[
    
      if (!cgu || byCgu[cgu] == null) return
      if (!groups.has(cgu)) groups.set(cgu, [])
      groups.get(cgu)!.push(idx)
    })

    for (const [cgu, indices] of groups) {
      const total = Math.max(0, byCgu[cgu] || 0)
      const weightSum = indices.reduce((s, i) => s + Math.max(rows.value[i].costAudited, 0), 0)
      indices.forEach((i, n) => {
        const row = rows.value[i]
        let share = 0
        if (weightSum > 0) {
          share = (Math.max(row.costAudited, 0) / weightSum) * total
        } else {
          share = total / indices.length
        }
        // 最后一行吃尾差
        if (n === indices.length - 1) {
          const allocated = indices.slice(0, -1).reduce((s, j) => s + rows.value[j].impIncrease, 0)
          // 先写前面的，最后一行用 residual — 简化：直接按 share
          share = total - indices.slice(0, n).reduce((s, j) => {
            const w = weightSum > 0 ? (Math.max(rows.value[j].costAudited, 0) / weightSum) * total : total / indices.length
            return s + w
          }, 0)
        }
        if (Math.abs(row.impIncrease - share) > 0.01) {
          row.impIncrease = Math.max(0, share)
          if (Math.abs(row.impUnadj - row.impEnding) < 0.01 || row.impUnadj === 0) {
            row.impUnadj = calcRollEnding(row.impOpening, row.impIncrease, row.impDecrease)
          }
          _recalcRow(row)
          updated++
        }
      })
    }
    if (updated > 0) _persist()
    return updated
  }

  /**
   * 从 I3-3 按被投资单位回写账项调整：costAje / impAje
   * 返回更新行数；未匹配项写入 lastSyncMeta 供 UI 提示
   */
  function syncAjeFromI3_3(
    byInvestee: Record<string, { costAje: number; impAje: number; net: number }>,
  ): { updated: number; applied: string[]; unmatched: string[]; unspecified: boolean } {
    let updated = 0
    const applied: string[] = []
    const detailKeys = new Set(rows.value.map((r) => r.investee?.trim()).filter(Boolean) as string[])
    const unmatched: string[] = []
    let unspecified = false

    for (const [key, src] of Object.entries(byInvestee)) {
      if (key === 
    
    >
      <template #title>
        商誉减值不可转回！本期合并报表应确认商誉减值
        <strong>{{ fmtAmt(totalGoodwillImpairment) }}</strong>
        元（已剔除少数股东份额），以后期间不得转回。请同步核对 I3-1 / K11。
      </template>
    </el-alert>

    <!-- 三、可收回金额测试索引 -->
    <el-card shadow=
    
    if (!byInvestee[inv]) byInvestee[inv] = { costAje: 0, impAje: 0, net: 0 }
    byInvestee[inv].net += netAmount
    if (netAmount >= 0) {
      byInvestee[inv].costAje += netAmount
    } else {
      byInvestee[inv].impAje += Math.abs(netAmount)
    }
  }

  return { totalAje, totalRje, byInvestee }
}

export function useI3CrossSheet(allResponses: Ref<Map<string, any>>): {
  detailTotals: ComputedRef<I3DetailTotals>
  impairmentResult: ComputedRef<I3ImpairmentResult>
  adjustmentSync: ComputedRef<I3AdjustmentSync>
  disclosureAutoFill: ComputedRef<I3DisclosureData>
  recoverableByCgu: ComputedRef<Record<string, number>>
  recoverableDetailByCgu: ComputedRef<Record<string, I3RecoverableDetail>>
  initialValueRows: ComputedRef<I3InitialValueRowRaw[]>
  impairmentByCgu: ComputedRef<Record<string, number>>
  cguNameOptions: ComputedRef<string[]>
  entryVariances: ComputedRef<I3EntryVariance[]>
  ajeVariances: ComputedRef<I3AjeVariance[]>
  detailRows: ComputedRef<I3DetailRowRaw[]>
} {
  const detailRows = computed<I3DetailRowRaw[]>(() => {
    const resp = allResponses.value.get(
    
  reportItem: string
  accountCode: string
  accountName: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
  /** 被投资单位（供 I3-1 精确匹配 AJE） */
  investee: string
  /** 兼容旧字段 */
  summary?: string
  debit?: number
  credit?: number
  sourceGroupId?: string
}

const ROWS_KEY = 
    
  return `${rate.toFixed(2)}%`
}

export function formatLayeredCoverageLabel(summary: I3TargetedSummary): string {
  if (summary.coverageRate == null) return 
    
  return `借方 ${summary.coverageRate.toFixed(2)}%（特定 ${sp}% + 抽样 ${sa}%）`
}

function _parseI32Rows(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 
    
  }

  watch(() => {
    const m = getMap()
    return [
      m.get(STORAGE_ROWS),
      m.get(STORAGE_SAMPLE),
      m.get(STORAGE_RISK),
      m.get(STORAGE_LEGACY),
      m.get(STORAGE_NOTE),
      m.get(STORAGE_CONCLUSION),
      m.get(I32_ROWS),
    ]
  }, () => load(), { immediate: true, deep: false })

  const linkedPeriod: ComputedRef<{
    debitTotal: number
    creditTotal: number
    originalTotal: number
    source: string
  }> = computed(() => {
    const mv = extractI3PeriodMovement(getMap().get(I32_ROWS), getYear())
    return mv.debitTotal > 0 || mv.creditTotal > 0 || mv.originalTotal > 0
      ? mv
      : { debitTotal: 0, creditTotal: 0, originalTotal: 0, source: 
    
import {
  type I3AdjudicationRowModel,
  type I3AdjudicationCrossCheck,
  emptyI3AdjudicationRow,
  normalizeI3AdjudicationRow,
  summarizeI3Adjudication,
  seedI3AdjudicationFromDetail,
  allocateI3Adjustments,
  applyAjeFromI33,
  applyI3ImpairmentFromTest,
  buildI3AdjudicationCrossCheck,
  buildI3AdjudicationConclusionDraft,
  buildI3LayerSummary,
  validateI3AdjudicationSave,
  recalcI3AdjudicationRow,
  I3_ADJ_ROWS_KEY,
  I3_ADJ_ROWS_CANDIDATES,
  I3_ADJ_NOTE_KEY,
  I3_ADJ_CONCLUSION_KEY,
} from 
    
import {
  type I3TargetedCheckRow,
  type I3TargetedSampleMeta,
  type I3TargetedRiskFocus,
  type I3TargetedSummary,
  emptyI3TargetedRow,
  emptyI3TargetedSampleMeta,
  emptyI3TargetedRiskFocus,
  normalizeI3TargetedRow,
  normalizeI3TargetedSampleMeta,
  normalizeI3TargetedRiskFocus,
  summarizeI3Targeted,
  extractI3PeriodMovement,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  buildI3TargetedConclusionDraft,
  buildI3TargetedAdjDrafts,
  mapSampledToI3TargetedRow,
  isAbnormalFlag,
  hasFailedCheck,
  I3_5_DEFAULT_COVERAGE_THRESHOLD,
} from 
    
}

/** 从 I3-3 分录汇总商誉科目 AJE（供回写 I3-2） */
export function aggregateGoodwillAjeByInvestee(
  rows: I3AdjustmentRowRaw[],
  knownInvestees: string[],
  cguToInvestees?: Record<string, string[]>,
): I3AdjustmentSync {
  let totalAje = 0
  let totalRje = 0
  const byInvestee: I3AdjustmentSync[
     && remark) {
      try {
        const p = JSON.parse(remark)
        return Array.isArray(p) ? p : []
      } catch { return [] }
    }
    if (Array.isArray(remark)) return remark
  }
  return []
}

/**
 * 从 I3-2 明细推算本期发生额：
 * 优先 costIncrease（原值本期增加=借方）/ currentImpairment|impIncrease（贷方）；
 * 无滚动字段时回退并购日年份代理。
 */
export function extractI3PeriodMovement(raw: unknown, asOfYear?: number): I3PeriodMovement {
  const rows = _parseI32Rows(raw)
  let debitTotal = 0
  let creditTotal = 0
  let originalTotal = 0
  let usedRoll = false
  for (const r of rows) {
    if ((r?.investee || r?.projectName || r?.name) === 
     open>
      <summary>编制提示（对齐 Excel 商誉调整分录汇总表 I3-3）</summary>
      <div class=
     open>
      <summary>编制说明（对齐致同 I3-7 / CAS8）</summary>
      <ol>
        <li>可收回金额应当根据资产的公允价值减去处置费用后的净额与资产预计未来现金流量的现值两者之间较高者确定。</li>
        <li>公允净额：优先公平交易销售协议价格，其次活跃市场报价，再次以可获取的最佳信息估计；仍无法可靠估计时，以预计未来现金流量现值作为可收回金额。</li>
        <li>处置费用包括与资产处置有关的法律费用、相关税费、搬运费以及为使资产达到可销售状态所发生的直接费用等。</li>
        <li>预计未来现金流量现值：按资产持续使用及最终处置所产生的预计未来现金流量，选择恰当折现率折现；预测一般以管理层批准的最近财务预算为基础，通常不超过5年。</li>
        <li>折现率应反映货币时间价值和资产特定风险的当前市场评价；现金流与折现率税前/税后口径须一致。WACC=(D×Kd×(1−t)+E×Ke)/(D+E)；Ke=Rf+β×(Rm−Rf)。</li>
        <li>Rm/Kd/Rf 均按<strong>百分比</strong>填写（如市场回报 8 表示 8%，勿填 0.08）。测算完成后点击「回写 I3-6」同步可收回金额。</li>
        <li>资产组：企业可以认定的最小资产组合，其产生的现金流入基本独立于其他资产或资产组。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang=
     }
      }
      rows.value = allocateI3Adjustments(rows.value, totalAje, totalRje, true)
      _persist()
      return {
        ok: true,
        approx: rows.value.length > 1,
        message: `已按合计分摊 AJE ${totalAje.toFixed(2)} / RJE ${totalRje.toFixed(2)}${rows.value.length > 1 ? 
     }
    }
    rows.value = applyI3ImpairmentFromTest(rows.value, byName, total)
    _persist()
    return {
      ok: true,
      message: `已同步本期商誉减值 ${total.toLocaleString(
     }
  })

  const summary: ComputedRef<I3TargetedSummary> = computed(() =>
    summarizeI3Targeted(
      rows.value,
      sampleMeta.value.populationAmount,
      sampleMeta.value.populationCreditAmount,
    ),
  )

  const coverageLow = computed(() =>
    summary.value.coverageRate != null
    && summary.value.coverageRate < sampleMeta.value.coverageThreshold
    && summary.value.periodTotal > 0,
  )

  const coverageLabel = computed(() => formatLayeredCoverageLabel(summary.value))
  const creditCoverageLabel = computed(() => formatCoverageLabel(summary.value.creditCoverageRate))

  const coverageTagType = computed(() => {
    if (summary.value.coverageRate == null) return 
     },
])

// ─── 进度计算 ─────────────────────────────────────────────────────────────────
const totalCount = computed(() => allSheets.value.length)
const completedCount = computed(() => allSheets.value.filter(r => calcSheetProgress(r.prefix, 3) >= 100).length)
const progressPercent = computed(() => {
  if (totalCount.value === 0) return 0
  const avg = allSheets.value.reduce((sum, r) => sum + calcSheetProgress(r.prefix, 3), 0) / totalCount.value
  return Math.round(avg)
})

// ─── 底稿架构泳道（GtBArchitectureTree 数据源） ───────────────────────────────
const COMPONENT_TYPE_MAP: Record<string, string> = {
  I3A: 
    )

    if (!sampleMeta.value.populationManual) {
      const mv = extractI3PeriodMovement(map.get(I32_ROWS), getYear())
      if (mv.debitTotal > 0) sampleMeta.value.populationAmount = mv.debitTotal
      if (mv.creditTotal > 0) sampleMeta.value.populationCreditAmount = mv.creditTotal
    }
  }

  function _strFromLegacy(raw: any, key: string): string {
    if (!raw || typeof raw !== 
    )

  const {
    detailTotals,
    impairmentResult,
    adjustmentSync,
  } = useI3CrossSheet(allResponses as Ref<Map<string, any>>)

  function getYear(): number {
    if (!options?.asOfYear) return new Date().getFullYear()
    return typeof options.asOfYear === 
    )

const {
  rows,
  auditNote,
  auditConclusion,
  subtotals,
  warnings,
  crossCheck,
  tbDiff,
  differenceRows,
  addRow,
  removeRow,
  updateCell,
  applyTbData,
  seedFromI32,
  syncFromI33,
  syncImpairmentFromI36,
  fillConclusionDraft,
  saveAdjudication,
  publishToTb,
  publishing,
  saveNote,
  saveConclusion,
  layerSummary,
  hasAjeApprox,
} = useI3Adjudication(
  toRef(props, 
    )

const {
  rows,
  sampleMeta,
  riskFocus,
  auditNote,
  auditConclusion,
  summary,
  coverageLow,
  coverageLabel,
  creditCoverageLabel,
  coverageTagType,
  linkedPeriod,
  adjDrafts,
  addRow,
  removeRow,
  updateRow,
  fillFromSampledVouchers,
  setPopulationAmount,
  syncPopulationFromI32,
  appendAdjDraftsToNote,
  fillConclusionDraft,
  persistAll,
  saveNote,
  saveConclusion,
} = useI3TargetedCheck(allResponsesRef, {
  onSave: (itemId, value) => emit(
    )

function newId(): string {
  return emptyI3InitialValueRow().rowId
}

function emptyRow(): InitialValueRow {
  return emptyI3InitialValueRow()
}

function rowShare(row: InitialValueRow): number {
  return calcI34Share(row)
}

function rowGoodwill(row: InitialValueRow): number {
  return calcI34Goodwill(row)
}

const dataRows = computed(() => rows.value)

const totals = computed(() => summarizeI34(rows.value))

const gateWarnings = computed(() => buildI34GateWarnings(rows.value))

function fmt(v: number): string {
  const n = Number(v) || 0
  return n.toLocaleString(
    )
    const known = I3_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === accountCode)
    const debitAmount = parseAmt(raw.debitAmount ?? raw.debit)
    const creditAmount = parseAmt(raw.creditAmount ?? raw.credit)
    const description = String(raw.description ?? raw.summary ?? 
    )
    return safeParseRows<I3InitialValueRowRaw>(resp?.remark)
  })

  const knownInvestees = computed(() =>
    detailRows.value.map(r => _normName(r.investee)).filter(Boolean),
  )

  const cguToInvestees = computed(() => {
    const map: Record<string, string[]> = {}
    for (const r of detailRows.value) {
      const cgu = _normName(r.cguName)
      const inv = _normName(r.investee)
      if (!cgu || !inv) continue
      if (!map[cgu]) map[cgu] = []
      if (!map[cgu].includes(inv)) map[cgu].push(inv)
    }
    return map
  })

  const detailTotals: ComputedRef<I3DetailTotals> = computed(() => {
    let goodwillOriginalTotal = 0
    let accImpairmentTotal = 0
    let netValueTotal = 0
    let currentImpairmentTotal = 0
    const byCgu: I3DetailTotals[
    )
  let i38Filled = 0
  let i38Total = 0
  try {
    const t = _readText(i38Raw)
    const parsed = t ? JSON.parse(t) : (typeof i38Raw === 
    )
const isSyncing = ref(false)
const sections = LISTED_SECTIONS

const {
  bookValueRows,
  impairmentRows,
  sectionRows,
  sectionNotes,
  performanceRows,
  assumptionParamRows,
  bookValueTotal,
  impairmentTotal,
  netValueTotal,
  applyAutoFill,
  needsDetailSplitWarning,
  pullFromDetailRows,
  addDynamicRow,
  removeDynamicRow,
  updateDynamicRow,
  updateMatrixCell,
  addMatrixRow,
  removeMatrixRow,
  addPerformanceRow,
  removePerformanceRow,
  updatePerformanceRow,
  seedPerformanceFromBookValue,
  addAssumptionParamRow,
  removeAssumptionParamRow,
  updateAssumptionParamRow,
  seedAssumptionFromCgu,
  saveSectionNote,
  getSyncSnapshot,
  dispose: disposeDisclosure,
} = useI3Disclosure(
  toRef(props, 
    )
const isSyncing = ref(false)
const sections = SOE_SECTIONS

const {
  bookValueRows,
  impairmentRows,
  sectionRows,
  sectionNotes,
  bookValueTotal,
  impairmentTotal,
  netValueTotal,
  applyAutoFill,
  needsDetailSplitWarning,
  pullFromDetailRows,
  addDynamicRow,
  removeDynamicRow,
  updateDynamicRow,
  updateMatrixCell,
  addMatrixRow,
  removeMatrixRow,
  saveSectionNote,
  getSyncSnapshot,
  dispose: disposeDisclosure,
} = useI3Disclosure(
  toRef(props, 
    )
}

/** 抽凭引擎 SampledVoucher → I3-5 行 */
export function mapSampledToI3TargetedRow(s: {
  voucherNo?: string
  voucherDate?: string
  summary?: string | null
  debitAmount?: string | number | null
  creditAmount?: string | number | null
  counterpartAccount?: string | null
  accountName?: string | null
  isHighValue?: boolean
  selectionReason?: string
  abnormal?: boolean
  remark?: string
}): I3TargetedCheckRow {
  const reason = _str(s.selectionReason)
  const isSpecific = !!(s.isHighValue || reason)
  return emptyI3TargetedRow({
    voucherDate: _str(s.voucherDate),
    voucherNo: _str(s.voucherNo),
    businessDesc: _str(s.summary),
    counterpartAccount: _str(s.counterpartAccount),
    projectName: _str(s.accountName),
    debitAmount: _num(s.debitAmount),
    creditAmount: _num(s.creditAmount),
    isSpecific,
    selectionReason: reason || (s.isHighValue ? 
    )
}

export function summarizeI3Targeted(
  rows: I3TargetedCheckRow[],
  periodDebitTotal: number,
  periodCreditTotal = 0,
): I3TargetedSummary {
  const sampleCount = rows.length
  const checkedDebitTotal = Math.round(rows.reduce((s, r) => s + _num(r.debitAmount), 0) * 100) / 100
  const checkedCreditTotal = Math.round(rows.reduce((s, r) => s + _num(r.creditAmount), 0) * 100) / 100
  const anomalyCount = rows.filter((r) => isAbnormalFlag(r.isAbnormal) || hasFailedCheck(r)).length
  const failCheckCount = rows.filter(hasFailedCheck).length
  const pendingCount = rows.filter((r) => !isRowChecksComplete(r)).length
  const completedCheckCount = rows.filter(isRowChecksComplete).length

  const specificRows = rows.filter((r) => r.isSpecific || !!r.selectionReason)
  const samplingRows = rows.filter((r) => !(r.isSpecific || !!r.selectionReason))
  const specificCount = specificRows.length
  const specificDebitTotal = Math.round(specificRows.reduce((s, r) => s + _num(r.debitAmount), 0) * 100) / 100
  const samplingDebitTotal = Math.round(samplingRows.reduce((s, r) => s + _num(r.debitAmount), 0) * 100) / 100

  let coverageRate: number | null = null
  let creditCoverageRate: number | null = null
  let specificCoverageRate: number | null = null
  let samplingCoverageRate: number | null = null
  if (periodDebitTotal > 0) {
    coverageRate = Math.round((checkedDebitTotal / periodDebitTotal) * 10000) / 100
    specificCoverageRate = Math.round((specificDebitTotal / periodDebitTotal) * 10000) / 100
    samplingCoverageRate = Math.round((samplingDebitTotal / periodDebitTotal) * 10000) / 100
  }
  if (periodCreditTotal > 0) {
    creditCoverageRate = Math.round((checkedCreditTotal / periodCreditTotal) * 10000) / 100
  }

  return {
    sampleCount,
    checkedDebitTotal,
    checkedCreditTotal,
    periodTotal: periodDebitTotal,
    coverageRate,
    creditCoverageRate,
    anomalyCount,
    failCheckCount,
    pendingCount,
    completedCheckCount,
    specificCount,
    specificDebitTotal,
    samplingDebitTotal,
    specificCoverageRate,
    samplingCoverageRate,
  }
}

export function formatCoverageLabel(rate: number | null): string {
  if (rate == null) return 
    ) as string
  }

  const subtotals = computed(() => summarizeI3Adjudication(rows.value))

  const crossCheck = computed<I3AdjudicationCrossCheck>(() =>
    buildI3AdjudicationCrossCheck(rows.value, detailTotals.value),
  )

  const warnings = computed<I3Warning[]>(() => {
    const result: I3Warning[] = []
    for (const row of rows.value) {
      if (row.newAcquisition !== 0) {
        result.push({
          rowId: row.rowId,
          investee: row.investee,
          type: 
    ) return null
  const n = Number(val)
  return Number.isFinite(n) ? n : null
}

function _genRowId(): string {
  return `cgu-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function _safeParseRows<T>(raw: string | null | undefined): T[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/**
 * 可收回金额：有①或②时取孰高；否则用手工 recoverableAmount
 */
export function resolveRecoverableAmount(row: {
  fairValueLessCost?: number | null
  valueInUse?: number | null
  recoverableAmount?: number | null
}): number {
  const fv = row.fairValueLessCost
  const viu = row.valueInUse
  const hasFv = fv != null && Number.isFinite(fv)
  const hasViu = viu != null && Number.isFinite(viu)
  if (hasFv || hasViu) {
    return Math.max(hasFv ? Number(fv) : 0, hasViu ? Number(viu) : 0)
  }
  return Math.max(_getNum(row.recoverableAmount), 0)
}

/**
 * 合并报表确认商誉减值 = 全额商誉减值 × B1/(B1+B2)
 */
export function calcConsolidatedGwImpairment(
  goodwillImpairment: number,
  goodwillB1: number,
  minorityB2: number,
): number {
  const totalGw = goodwillB1 + minorityB2
  if (goodwillImpairment <= 0 || totalGw <= 0) return 0
  if (minorityB2 <= 0) return goodwillImpairment
  return (goodwillImpairment * goodwillB1) / totalGw
}

// ─── Core Calculation ────────────────────────────────────────────────────────

/**
 * 重算单行 CGU：
 * 1. A = assetGroupCarrying（若为0且有 otherAssets，回退 Σother）
 * 2. 合计(1) = A + B1 + B2
 * 3. 可收回(2) = resolveRecoverableAmount
 * 4. 减值 = MAX((1)-(2), 0)
 * 5. 先冲全额商誉(B1+B2)，再分摊其他资产
 * 6. 合并确认 = 商誉减值 × B1/(B1+B2)
 */
function _recalcCguRow(row: CguRow): void {
  // 同步兼容字段
  row.goodwillAmount = row.goodwillB1

  const otherTotal = calcSubtotal(row.otherAssets.map(a => a.bookValue))
  // A：优先显式录入；未录且存在其他资产明细时用明细合计
  const A = row.assetGroupCarrying > 0
    ? row.assetGroupCarrying
    : (otherTotal > 0 ? otherTotal : row.assetGroupCarrying)

  // 若显式 A 与明细合计不一致且明细非空，账面仍以显式 A 为准（明细仅作第二分摊基数）
  const effectiveA = A
  row.cguBookValue = effectiveA + row.goodwillB1 + row.minorityB2

  row.recoverableAmount = resolveRecoverableAmount(row)

  row.impairmentAmount = Math.max(row.cguBookValue - row.recoverableAmount, 0)

  // 第一分摊基数 = 全额商誉 B1+B2（粗化后）
  const fullGoodwill = row.goodwillB1 + row.minorityB2
  const allocation = calcImpairmentAllocation(
    row.impairmentAmount,
    fullGoodwill,
    row.otherAssets,
  )

  row.goodwillImpairment = allocation.goodwillImpairment
  row.otherAllocations = allocation.otherAllocations
  row.consolidatedGwImpairment = calcConsolidatedGwImpairment(
    row.goodwillImpairment,
    row.goodwillB1,
    row.minorityB2,
  )
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI3Impairment(
  wpId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    onSave?: (itemId: string, value: any) => void
    /** I3-7 → 可收回金额合计（兼容） */
    recoverableByCgu?: ComputedRef<Record<string, number>>
    /** I3-7 → 公允净额 + 使用价值明细 */
    recoverableDetailByCgu?: ComputedRef<Record<string, {
      fairValueLessDisposal?: number
      valueInUse?: number
      recoverableAmount?: number
    }>>
  },
) {
  const cguRows = ref<CguRow[]>([])

  function _loadCguRows(): void {
    const resp = allResponses.value.get(ITEM_ID_CGU_ROWS)
    const raw = resp?.remark ?? resp?.conclusion
    cguRows.value = _safeParseRows<any>(raw).map(_normalizeCguRow)
  }

  function _normalizeCguRow(raw: any): CguRow {
    // 兼容：goodwillAmount → B1；assetGroupCarrying 缺省时由 otherAssets 推导
    const goodwillB1 = _getNum(raw.goodwillB1 ?? raw.goodwillAmount)
    const minorityB2 = _getNum(raw.minorityB2)
    const otherAssets: OtherAsset[] = Array.isArray(raw.otherAssets)
      ? raw.otherAssets.map((a: any) => ({
          name: String(a.name ?? 
    ) {
          return Boolean(v.conclusion || v.result || v.evidence || v.remark)
        }
        return String(v).trim().length > 0
      }).length
    }
  } catch { /* ignore */ }
  if (i36.length && i38Total === 0 && !_hasValue(i38Raw)) {
    items.push({
      id: 
    ) {
        try {
          const p = JSON.parse(remark)
          return Array.isArray(p) ? p : []
        } catch { return [] }
      }
      return []
    })()
    const result = applyAjeFromI33(rows.value, adjRows)
    if (Math.abs(result.totalAje) < 0.005 && Math.abs(result.totalRje) < 0.005) {
      // 回退：无行级明细时用 crossSheet 合计分摊
      const { totalAje, totalRje } = adjustmentSync.value
      if (Math.abs(totalAje) < 0.005 && Math.abs(totalRje) < 0.005) {
        return { ok: false, message: 
    ) {
      const vals = Array.isArray(answers) ? answers : Object.values(answers)
      i38Total = vals.length
      i38Filled = vals.filter((v: any) => {
        if (v == null || v === 
    ) {
      row.ajeApprox = false
    }
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) rows.value[idx] = recalcI3AdjudicationRow(row)
    _persist()
  }

  function applyTbData(tbUnadjustedTotal: number): void {
    if (rows.value.length === 1) {
      rows.value[0] = recalcI3AdjudicationRow({
        ...rows.value[0],
        unadjusted: tbUnadjustedTotal,
      })
    } else if (rows.value.length > 1) {
      const totalBegin = rows.value.reduce((s, r) => s + r.beginBalance, 0)
      if (totalBegin > 0) {
        rows.value = rows.value.map((row) => recalcI3AdjudicationRow({
          ...row,
          unadjusted: Math.round((row.beginBalance / totalBegin) * tbUnadjustedTotal * 100) / 100,
        }))
      }
    }
    _persist()
  }

  function applyAdjustments(adjustments: { investee: string; aje: number; rje: number }[]): void {
    for (const adj of adjustments) {
      const row = rows.value.find((r) => r.investee === adj.investee)
      if (row) {
        Object.assign(row, recalcI3AdjudicationRow({ ...row, aje: adj.aje, rje: adj.rje }))
      }
    }
    _persist()
  }

  /** 从 I3-2 带入/更新行（保留已有 AJE/RJE） */
  function seedFromI32(): { ok: boolean; message: string; count: number } {
    const raw = allResponses.value.get(
    ) {
      totalRje = _round2(totalRje + net)
      if (name) namedRje.push({ name, net })
    } else {
      totalAje = _round2(totalAje + net)
      if (name) namedAje.push({ name, net })
    }
  }

  if ((Math.abs(totalAje) < 0.005 && Math.abs(totalRje) < 0.005) || !rows.length) {
    return { rows, applied: 0, approx: false, totalAje, totalRje, matchedByName: 0 }
  }

  const next = rows.map((r) => ({ ...r, aje: 0, rje: 0, ajeApprox: false }))
  const byName = new Map(next.map((r) => [r.investee.trim(), r]))
  let matchedByName = 0
  let ajeNamed = 0
  let rjeNamed = 0

  for (const { name, net } of namedAje) {
    const row = byName.get(name)
    if (!row) continue
    row.aje = _round2(row.aje + net)
    row.ajeApprox = false
    matchedByName++
    ajeNamed = _round2(ajeNamed + net)
  }
  for (const { name, net } of namedRje) {
    const row = byName.get(name)
    if (!row) continue
    row.rje = _round2(row.rje + net)
    row.ajeApprox = false
    matchedByName++
    rjeNamed = _round2(rjeNamed + net)
  }

  const ajeRem = _round2(totalAje - ajeNamed)
  const rjeRem = _round2(totalRje - rjeNamed)
  let approx = false
  let applied = matchedByName

  if (Math.abs(ajeRem) >= 0.005 || Math.abs(rjeRem) >= 0.005) {
    const weightSum = next.reduce((s, r) => s + (Math.abs(r.unadjusted) || Math.abs(r.endBalance)), 0)
    if (next.length === 1 || weightSum < 0.005) {
      next[0].aje = _round2(next[0].aje + ajeRem)
      next[0].rje = _round2(next[0].rje + rjeRem)
      if (matchedByName > 0 && next.length > 1) {
        next[0].ajeApprox = true
        approx = true
      }
      applied = Math.max(applied, 1)
    } else {
      approx = true
      let ajeAlloc = 0
      let rjeAlloc = 0
      for (let i = 0; i < next.length; i++) {
        const w = (Math.abs(next[i].unadjusted) || Math.abs(next[i].endBalance)) / weightSum
        const aAmt = i === next.length - 1 ? _round2(ajeRem - ajeAlloc) : _round2(ajeRem * w)
        const rAmt = i === next.length - 1 ? _round2(rjeRem - rjeAlloc) : _round2(rjeRem * w)
        next[i].aje = _round2(next[i].aje + aAmt)
        next[i].rje = _round2(next[i].rje + rAmt)
        next[i].ajeApprox = true
        ajeAlloc = _round2(ajeAlloc + aAmt)
        rjeAlloc = _round2(rjeAlloc + rAmt)
      }
      applied = next.length
    }
  }

  return {
    rows: next.map(recalcI3AdjudicationRow),
    applied,
    approx,
    totalAje,
    totalRje,
    matchedByName,
  }
}

/** Excel 式三层只读汇总：原始金额 / 减值准备 / 净值 */
export function buildI3LayerSummary(rows: I3AdjudicationRowModel[]): {
  original: { begin: number; increase: number; decrease: number; end: number; audited: number }
  impairment: { begin: number; increase: number; decrease: number; end: number; audited: number }
  net: { begin: number; increase: number; decrease: number; end: number; audited: number }
} {
  const sub = summarizeI3Adjudication(rows)
  const originalEnd = sub.initialRecognition
  const originalBegin = _round2(sub.initialRecognition - sub.newAcquisition)
  const impEnd = sub.accImpairment
  const impBegin = _round2(sub.accImpairment - sub.impairment)
  return {
    original: {
      begin: originalBegin,
      increase: sub.newAcquisition,
      decrease: 0,
      end: originalEnd,
      audited: originalEnd,
    },
    impairment: {
      begin: Math.max(0, impBegin),
      increase: sub.impairment,
      decrease: 0,
      end: impEnd,
      audited: impEnd,
    },
    net: {
      begin: sub.beginBalance,
      increase: sub.newAcquisition,
      decrease: sub.impairment,
      end: sub.endBalance,
      audited: sub.audited,
    },
  }
}

/** 保存前闸门：期末≠净额、TB 差异 */
export function validateI3AdjudicationSave(opts: {
  rows: I3AdjudicationRowModel[]
  tbDiff: number
  force?: boolean
}): { ok: boolean; blockers: string[]; warnings: string[] } {
  const blockers: string[] = []
  const warnings: string[] = []
  if (opts.force) return { ok: true, blockers, warnings }

  for (const r of opts.rows) {
    if (Math.abs(_num(r.endBalance) - _num(r.netValue)) > 0.01) {
      blockers.push(`${r.investee || 
    ),
      cguBookValue: 0,
      impairmentAmount: 0,
      goodwillImpairment: 0,
      consolidatedGwImpairment: 0,
      otherAllocations: [],
    }
    _recalcCguRow(row)
    return row
  }

  const cguSummary: ComputedRef<CguSummary> = computed(() => {
    let totalAssetGroupCarrying = 0
    let totalGoodwillB1 = 0
    let totalMinorityB2 = 0
    let totalOtherAssets = 0
    let totalCguBookValue = 0
    let totalRecoverable = 0
    let totalImpairment = 0
    let totalGoodwillImpairment = 0
    let totalConsolidatedGwImpairment = 0
    let totalOtherImpairment = 0

    for (const row of cguRows.value) {
      const otherTotal = calcSubtotal(row.otherAssets.map(a => a.bookValue))
      const A = row.assetGroupCarrying > 0 ? row.assetGroupCarrying : otherTotal
      totalAssetGroupCarrying += A
      totalGoodwillB1 += row.goodwillB1
      totalMinorityB2 += row.minorityB2
      totalOtherAssets += otherTotal
      totalCguBookValue += row.cguBookValue
      totalRecoverable += row.recoverableAmount
      totalImpairment += row.impairmentAmount
      totalGoodwillImpairment += row.goodwillImpairment
      totalConsolidatedGwImpairment += row.consolidatedGwImpairment
      totalOtherImpairment += calcSubtotal(row.otherAllocations.map(a => a.amount))
    }

    return {
      totalAssetGroupCarrying,
      totalGoodwillB1,
      totalMinorityB2,
      totalGoodwill: totalGoodwillB1,
      totalOtherAssets,
      totalCguBookValue,
      totalRecoverable,
      totalImpairment,
      totalGoodwillImpairment,
      totalConsolidatedGwImpairment,
      totalOtherImpairment,
    }
  })

  /**
   * 供 I3-1 审定表「本期减少(减值)」：合并报表确认的商誉减值（母公司份额）
   */
  const totalGoodwillImpairment: ComputedRef<number> = computed(() => {
    return cguSummary.value.totalConsolidatedGwImpairment
  })

  const impairedRowIds: ComputedRef<Set<string>> = computed(() => {
    const ids = new Set<string>()
    for (const row of cguRows.value) {
      if (row.impairmentAmount > 0) ids.add(row.rowId)
    }
    return ids
  })

  function addCguRow(params: {
    cguName: string
    assetGroupCarrying?: number
    goodwillB1?: number
    goodwillAmount?: number
    minorityB2?: number
    otherAssets?: OtherAsset[]
    fairValueLessCost?: number | null
    valueInUse?: number | null
    recoverableAmount?: number
    impairmentReason?: string
  }): CguRow {
    const goodwillB1 = params.goodwillB1 ?? params.goodwillAmount ?? 0
    const otherAssets = params.otherAssets ?? []
    const otherTotal = calcSubtotal(otherAssets.map(a => a.bookValue))
    const row: CguRow = {
      rowId: _genRowId(),
      cguName: params.cguName,
      assetGroupCarrying: params.assetGroupCarrying ?? otherTotal,
      goodwillB1,
      minorityB2: params.minorityB2 ?? 0,
      goodwillAmount: goodwillB1,
      otherAssets,
      fairValueLessCost: params.fairValueLessCost ?? null,
      valueInUse: params.valueInUse ?? null,
      recoverableAmount: params.recoverableAmount ?? 0,
      impairmentReason: params.impairmentReason ?? 
    ),
      summary: description,
      debit: debitAmount,
      credit: creditAmount,
      sourceGroupId: raw.sourceGroupId ? String(raw.sourceGroupId) : undefined,
    }
  }

  function _toPersistShape(list: I3AdjustmentRow[]) {
    return list.map((r, i) => ({
      ...r,
      seq: i + 1,
      debit: r.debitAmount,
      credit: r.creditAmount,
      debitAmount: r.debitAmount,
      creditAmount: r.creditAmount,
      summary: r.description,
      entryType: entryTypeFromCategory(String(r.category)),
    }))
  }

  function load(): void {
    const parsed = _getJson(ROWS_KEY)
    if (Array.isArray(parsed)) {
      rows.value = parsed.map((r, i) => _normalizeRow(r, i))
    } else {
      rows.value = []
    }
    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(allResponses, () => load(), { immediate: true })

  const debitTotal = computed(() => rows.value.reduce((s, r) => s + r.debitAmount, 0))
  const creditTotal = computed(() => rows.value.reduce((s, r) => s + r.creditAmount, 0))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() => Math.abs(balanceDiff.value) < BALANCE_TOLERANCE)

  const groupBalanceIssues = computed(() => {
    const groups = new Map<string, {
      key: string
      description: string
      entryType: string
      debit: number
      credit: number
      rowCount: number
    }>()
    for (const r of rows.value) {
      const et = r.entryType || entryTypeFromCategory(String(r.category))
      const desc = String(r.description || 
    )}，请回写或核对。`,
      )
    }
  }
  const totalImp = localCross.impairmentResult.value.totalImpairment
  if (totalImp > 0.01) {
    list.push(`I3-6 合并确认商誉减值合计 ${totalImp.toLocaleString(
    ,

      goodwillOriginal: _n(raw.goodwillOriginal),
      accImpairmentBegin: impOpening,
      currentImpairment: impIncrease,
      accImpairmentEnd: 0,
      goodwillNetValue: 0,
      periodDebit: costIncrease,
      periodCredit: costDecrease + impIncrease,
    }
  }

  /**
   * 重算：
   * 1) 原值/减值滚动期末、审定
   * 2) 入账测算商誉
   * 3) 兼容字段回写；净值 = 原值审定 − 减值审定
   * 4) 商誉减值不可转回：impIncrease ≥ 0（处置转出走 decrease）
   */
  function _recalcRow(row: I3DetailRow): void {
    row.impIncrease = Math.max(0, row.impIncrease)

    row.costEnding = calcRollEnding(row.costOpening, row.costIncrease, row.costDecrease)
    row.costAudited = calcAudited(row.costUnadj, row.costAje)

    row.impEnding = calcRollEnding(row.impOpening, row.impIncrease, row.impDecrease)
    row.impAudited = calcAudited(row.impUnadj, row.impAje)

    row.entryGoodwillCalc = calcInitialGoodwill(row.mergerCost, row.netAssetFairValue)

    // 兼容旧字段
    row.goodwillOriginal = row.costAudited
    row.accImpairmentBegin = row.impOpening
    row.currentImpairment = row.impIncrease
    row.accImpairmentEnd = row.impAudited
    row.goodwillNetValue = calcGoodwillNetValue(row.costAudited, row.impAudited)
    // Excel 本期借/贷发生额（供 I3-5 检查比例勾稽）
    row.periodDebit = row.costIncrease
    row.periodCredit = row.costDecrease + row.impIncrease
  }

  function recalcAll(): void {
    for (const row of rows.value) _recalcRow(row)
  }

  const summaryRow: ComputedRef<I3DetailSummary> = computed(() => {
    const r = rows.value
    const sum = (fn: (x: I3DetailRow) => number) => calcSubtotal(r.map(fn))
    return {
      costOpening: sum((x) => x.costOpening),
      costIncrease: sum((x) => x.costIncrease),
      costDecrease: sum((x) => x.costDecrease),
      costEnding: sum((x) => x.costEnding),
      costUnadj: sum((x) => x.costUnadj),
      costAje: sum((x) => x.costAje),
      costAudited: sum((x) => x.costAudited),
      impOpening: sum((x) => x.impOpening),
      impIncrease: sum((x) => x.impIncrease),
      impDecrease: sum((x) => x.impDecrease),
      impEnding: sum((x) => x.impEnding),
      impUnadj: sum((x) => x.impUnadj),
      impAje: sum((x) => x.impAje),
      impAudited: sum((x) => x.impAudited),
      periodDebit: sum((x) => x.periodDebit),
      periodCredit: sum((x) => x.periodCredit),
      mergerCost: sum((x) => x.mergerCost),
      netAssetFairValue: sum((x) => x.netAssetFairValue),
      entryGoodwillCalc: sum((x) => x.entryGoodwillCalc),
      minorityInterest: sum((x) => x.minorityInterest),
      costConsideration: sum((x) => x.costConsideration),
      costContingent: sum((x) => x.costContingent),
      costTransactionFee: sum((x) => x.costTransactionFee),
      consideration: sum((x) => x.consideration),
      counterpartyNetAsset: sum((x) => x.counterpartyNetAsset),
      goodwillOriginal: sum((x) => x.goodwillOriginal),
      accImpairmentBegin: sum((x) => x.accImpairmentBegin),
      currentImpairment: sum((x) => x.currentImpairment),
      accImpairmentEnd: sum((x) => x.accImpairmentEnd),
      goodwillNetValue: sum((x) => x.goodwillNetValue),
      recoverableAmount: sum((x) => x.recoverableAmount),
    }
  })

  const crossValidation: ComputedRef<I3DetailCrossValidation> = computed(() => {
    const adjOriginal = options?.adjGoodwillOriginalSubtotal?.value ?? 0
    const adjImpairment = options?.adjAccImpairmentSubtotal?.value ?? 0
    const adjNetValue = options?.adjNetValueSubtotal?.value ?? 0

    const goodwillOriginalDiff = summaryRow.value.costAudited - adjOriginal
    const accImpairmentDiff = summaryRow.value.impAudited - adjImpairment
    const netValueDiff = summaryRow.value.goodwillNetValue - adjNetValue

    const hasOriginalWarning = Math.abs(goodwillOriginalDiff) > 0.01
    const hasImpairmentWarning = Math.abs(accImpairmentDiff) > 0.01
    const hasNetValueWarning = Math.abs(netValueDiff) > 0.01

    return {
      goodwillOriginalDiff,
      accImpairmentDiff,
      netValueDiff,
      hasOriginalWarning,
      hasImpairmentWarning,
      hasNetValueWarning,
      hasAnyWarning: hasOriginalWarning || hasImpairmentWarning || hasNetValueWarning,
    }
  })

  /** 滚动勾稽：期末=期初+增-减；若未审已填则提示与计算期末差异 */
  const rollForwardChecks: ComputedRef<I3RollForwardCheck[]> = computed(() => {
    return rows.value.map((row) => {
      const costCalc = calcRollEnding(row.costOpening, row.costIncrease, row.costDecrease)
      const impCalc = calcRollEnding(row.impOpening, row.impIncrease, row.impDecrease)
      const costAuditCalc = calcAudited(row.costUnadj, row.costAje)
      const impAuditCalc = calcAudited(row.impUnadj, row.impAje)
      return {
        rowId: row.rowId,
        investee: row.investee,
        costOk: Math.abs(row.costEnding - costCalc) < 0.01,
        costDiff: row.costEnding - costCalc,
        impOk: Math.abs(row.impEnding - impCalc) < 0.01,
        impDiff: row.impEnding - impCalc,
        costAuditOk: Math.abs(row.costAudited - costAuditCalc) < 0.01,
        costAuditDiff: row.costAudited - costAuditCalc,
        impAuditOk: Math.abs(row.impAudited - impAuditCalc) < 0.01,
        impAuditDiff: row.impAudited - impAuditCalc,
      }
    })
  })

  const hasRollForwardWarning = computed(() =>
    rollForwardChecks.value.some((c) => !c.costOk || !c.impOk || !c.costAuditOk || !c.impAuditOk),
  )

  function switchSection(section: I3DetailSection): void {
    activeSection.value = section
  }

  function setActiveRow(index: number): void {
    activeRowIndex.value = index
  }

  function updateCell(
    rowIndex: number,
    field: keyof I3DetailRow,
    value: string | number,
  ): void {
    const row = rows.value[rowIndex]
    if (!row) return
    ;(row as any)[field] = value

    // 编辑未审时：若用户改的是计算期末相关输入，保持未审默认同步（仅当未审此前等于旧期末）
    if (field === 
    ,
            detailCostAje: 0,
            detailImpAje: 0,
            adjCostAje: src.costAje,
            adjImpAje: src.impAje,
            costDiff: src.costAje,
            impDiff: src.impAje,
            missingOnDetail: true,
          })
        }
        continue
      }
      const detail = detailByInv.get(inv)
      const dCost = detail ? _getNum(detail.costAje) : 0
      const dImp = detail ? _getNum(detail.impAje) : 0
      const costDiff = src.costAje - dCost
      const impDiff = src.impAje - dImp
      if (!detail || Math.abs(costDiff) > 0.01 || Math.abs(impDiff) > 0.01) {
        list.push({
          investee: inv,
          detailCostAje: dCost,
          detailImpAje: dImp,
          adjCostAje: src.costAje,
          adjImpAje: src.impAje,
          costDiff,
          impDiff,
          missingOnDetail: !detail,
        })
      }
    }
    return list
  })

  const disclosureAutoFill: ComputedRef<I3DisclosureData> = computed(() => {
    const result: I3DisclosureData = {}
    const totals = detailTotals.value
    result[
    ,
        accountCodes: [ACCOUNT_CODE_1711],
        auditedTotal: subtotals.value.audited,
        netValue: subtotals.value.netValue,
      },
    }))
  }

  /**
   * 保存审定表（普通保存动作，不写 TB）。
   *
   * spec: tb-writeback-explicit-publish-gate Task 13 / Req 1。
   * 此前保存后**自动** PUT 旧端点回写 trial_balance(1711) → 违反 Req 1。现只保存 + emit；
   * TB 回写收敛为用户显式确认动作（publishToTb）。
   */
  async function saveAdjudication(opts?: { force?: boolean }): Promise<{ ok: boolean; message: string }> {
    const gate = validateI3AdjudicationSave({
      rows: rows.value,
      tbDiff: tbDiff.value,
      force: opts?.force,
    })
    if (!gate.ok) {
      return { ok: false, message: gate.blockers.join(
    ,
      isEditable: true,
      fromDetail: true,
    }))
  }
  return out
}

/** 按未审数占比分摊 AJE/RJE 合计到各行（全部分摊均标 ajeApprox） */
export function allocateI3Adjustments(
  rows: I3AdjudicationRowModel[],
  totalAje: number,
  totalRje: number,
  markApprox = true,
): I3AdjudicationRowModel[] {
  if (!rows.length) return rows
  const base = rows.map((r) => Math.abs(_num(r.unadjusted)) || Math.abs(_num(r.endBalance)))
  const sum = calcSubtotal(base)
  if (!(sum > 0)) {
    return rows.map((r, i) => recalcI3AdjudicationRow({
      ...r,
      aje: i === 0 ? totalAje : 0,
      rje: i === 0 ? totalRje : 0,
      ajeApprox: markApprox && i === 0 && rows.length > 1,
    }))
  }
  let ajeLeft = totalAje
  let rjeLeft = totalRje
  return rows.map((r, i) => {
    const ratio = base[i] / sum
    const isLast = i === rows.length - 1
    const aje = isLast ? _round2(ajeLeft) : _round2(totalAje * ratio)
    const rje = isLast ? _round2(rjeLeft) : _round2(totalRje * ratio)
    ajeLeft = _round2(ajeLeft - aje)
    rjeLeft = _round2(rjeLeft - rje)
    return recalcI3AdjudicationRow({
      ...r,
      aje,
      rje,
      ajeApprox: markApprox && rows.length > 1,
    })
  })
}

/**
 * 从 I3-3 调整行写入审定表 AJE/RJE（对齐 I2 applyAjeFromI23）：
 * 1) 优先按 investee / description 精确匹配（不标近似）
 * 2) 剩余净额：单行直接计入；多行按未审占比分摊并标 ajeApprox
 */
export function applyAjeFromI33(
  rows: I3AdjudicationRowModel[],
  adjRows: any[],
): {
  rows: I3AdjudicationRowModel[]
  applied: number
  approx: boolean
  totalAje: number
  totalRje: number
  matchedByName: number
} {
  let totalAje = 0
  let totalRje = 0
  const namedAje: Array<{ name: string; net: number }> = []
  const namedRje: Array<{ name: string; net: number }> = []

  for (const line of adjRows || []) {
    const code = String(line?.accountCode || 
    ,
      message: `I3-8 复核进度 ${i38Filled}/${i38Total}，尚有未填项`,
      sheetHint: 
    ,
    initialRecognition: calcSubtotal(detail.map((r) => r.initialRecognition)),
    beginBalance: calcSubtotal(detail.map((r) => r.beginBalance)),
    newAcquisition: calcSubtotal(detail.map((r) => r.newAcquisition)),
    impairment: calcSubtotal(detail.map((r) => r.impairment)),
    endBalance: calcSubtotal(detail.map((r) => r.endBalance)),
    unadjusted: calcSubtotal(detail.map((r) => r.unadjusted)),
    aje: calcSubtotal(detail.map((r) => r.aje)),
    rje: calcSubtotal(detail.map((r) => r.rje)),
    audited: calcSubtotal(detail.map((r) => r.audited)),
    accImpairment: calcSubtotal(detail.map((r) => r.accImpairment)),
    netValue: calcSubtotal(detail.map((r) => r.netValue)),
    isEditable: false,
  })
}

/** 解析 I3-2 行数组 */
export function parseI32DetailRows(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 
    ,
    })
  } else if (i38Total > 0 && i38Filled < i38Total) {
    items.push({
      id: 
    ,
] as const

export type I3TargetedCheckMark = (typeof I3_5_CHECK_OPTIONS)[number]

export interface I3TargetedCheckRow {
  rowId: string
  /** 商誉项目明细（被投资单位 / CGU） */
  projectName: string
  voucherDate: string
  voucherNo: string
  businessDesc: string
  counterpartAccount: string
  counterpartDetail: string
  debitAmount: number
  creditAmount: number
  supportingDocs: string
  check1: I3TargetedCheckMark | string
  check2: I3TargetedCheckMark | string
  check3: I3TargetedCheckMark | string
  check4: I3TargetedCheckMark | string
  check5: I3TargetedCheckMark | string
  indexRef: string
  isAbnormal: string
  remark: string
  isSpecific: boolean
  selectionReason: string
}

export interface I3TargetedSampleMeta {
  populationCount: number
  /** 测试总体金额（借方口径，用于检查比例） */
  populationAmount: number
  /** 本期贷方发生额（减值等，展示用） */
  populationCreditAmount: number
  populationDesc: string
  populationManual: boolean
  /** Excel「测试原因」多选 */
  testReasons: string[]
  specificSample: string
  specificAmount: number
  samplingPopulationDesc: string
  sampleSize: number
  sampleMethod: string
  sampleProcess: string
  coverageThreshold: number
}

/** 原段落型风险关注（兼容旧 I3-5-targeted） */
export interface I3TargetedRiskFocus {
  externalIndicators: string
  internalIndicators: string
  cguAllocation: string
  cguConsistency: string
  externalConclusion: string
  internalConclusion: string
  allocationConclusion: string
  consistencyConclusion: string
}

export interface I3TargetedSummary {
  sampleCount: number
  checkedDebitTotal: number
  checkedCreditTotal: number
  periodTotal: number
  coverageRate: number | null
  /** 贷方检查比例（样本贷方 ÷ 本期贷方发生额） */
  creditCoverageRate: number | null
  anomalyCount: number
  failCheckCount: number
  pendingCount: number
  completedCheckCount: number
  specificCount: number
  specificDebitTotal: number
  samplingDebitTotal: number
  specificCoverageRate: number | null
  samplingCoverageRate: number | null
}

export interface I3PeriodMovement {
  /** 本期借方代理：当年新确认商誉原值合计 */
  debitTotal: number
  /** 本期贷方：本期减值合计 */
  creditTotal: number
  /** 商誉原值合计（存在性测试备选总体） */
  originalTotal: number
  source: string
}

export function emptyI3TargetedRow(partial?: Partial<I3TargetedCheckRow>): I3TargetedCheckRow {
  return {
    rowId: partial?.rowId || `i35-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    projectName: 
    , () => {})

const allResponsesRef = computed(() => props.allResponses)

const {
  recoverableByCgu,
  recoverableDetailByCgu,
  cguNameOptions,
} = useI3CrossSheet(allResponsesRef as any)

const {
  cguRows,
  cguSummary,
  totalGoodwillImpairment,
  impairedRowIds,
  addCguRow,
  removeCguRow,
  updateGoodwillB1,
  updateMinorityB2,
  updateAssetGroupCarrying,
  updateFairValueLessCost,
  updateValueInUse,
  updateImpairmentReason,
  updateCguName,
  addOtherAsset,
  removeOtherAsset,
  updateOtherAsset,
  syncRecoverableFromI3_7,
  exportCguRows,
} = useI3Impairment(
  toRef(props, 
    , META_KEY, JSON.stringify({
    auditNote: auditNote.value,
    auditConclusion: auditConclusion.value,
  }))
}

function normalizeRow(raw: any): InitialValueRow {
  return normalizeI3InitialValueRow(raw)
}

/** 从旧版「按被投资单位纵表」Map 迁移 */
function migrateLegacyMap(parsed: Record<string, any>): InitialValueRow[] {
  const out: InitialValueRow[] = []
  for (const [name, data] of Object.entries(parsed)) {
    const consideration = Number(data?.consideration) || 0
    const contingent = Number(data?.contingentConsideration) || 0
    // CAS20：交易费用不计入合并成本
    const mergerCost = consideration + contingent
    const assets = Number(data?.totalAssetsFV) || 0
    const liab = Number(data?.totalLiabilitiesFV) || 0
    const netAssetFV = assets - liab
    const equityRatio = Number(data?.equityRatio) || 100
    const share = netAssetFV * (equityRatio / 100)
    const gw = calcInitialGoodwill(mergerCost, share)
    const tx = Number(data?.transactionCost) || 0
    out.push({
      rowId: newId(),
      projectName: name,
      bookedAmount: Number(data?.detailGoodwillAmount) || gw,
      sameControl: 
    , { minimumFractionDigits: 2 })}`,
    }
  }

  function fillConclusionDraft(): void {
    auditConclusion.value = buildI3AdjudicationConclusionDraft({
      rowCount: rows.value.length,
      auditedTotal: subtotals.value.audited,
      netTotal: subtotals.value.netValue,
      newAcquisitionTotal: subtotals.value.newAcquisition,
      impairmentTotal: subtotals.value.impairment,
      tbDiff: tbDiff.value,
      crossCheck: crossCheck.value,
    })
  }

  const layerSummary = computed(() => buildI3LayerSummary(rows.value))

  const hasAjeApprox = computed(() => rows.value.some((r) => r.ajeApprox))

  // ─── 显式发布门状态（防重复提交，供发布按钮 :loading 绑定） ─────────────────
  const publishing = ref(false)

  /** 发布下游联动事件（仅 emit，不写 TB）。 */
  function _emitAdjudicated(): void {
    window.dispatchEvent(new CustomEvent(
    : [itemId: string, value: any]
}>()

const {
  rows,
  activeSection,
  activeRowIndex,
  summaryRow,
  crossValidation,
  hasRollForwardWarning,
  activeColumns,
  costColumns,
  impairmentColumns,
  switchSection,
  setActiveRow,
  updateCell,
  addRow,
  removeRow,
  syncImpIncreaseFromI3_6,
  syncAjeFromI3_3,
  syncFromI3_4,
} = useI3Detail(
  toRef(props, 
    >
        <summary>编制提示</summary>
        <ul>
          <li>商誉核心规则：<strong>不摊销！仅年度减值测试</strong>；1711 资产借方，期末 = 期初 + 新并购增加 − 减值（减值一经确认不可转回，正常年度只减不增）</li>
          <li>推荐工作流：I3A 程序 → I3-4 入账价值测算 → I3-2 明细 → I3-5 针对性检查 → I3-6 减值测试(CGU分摊) → I3-7 可收回金额(DCF/CAPM) → I3-8 复核过程 → I3-3 调整回写 I3-1 → 附注披露</li>
          <li>减值测试以资产组(CGU)/资产组组合为单元：可收回金额 = MAX(公允价值减处置费用后净额, DCF 现值)；减值先冲商誉（至零为止），剩余再按比例分摊至资产组其他资产</li>
          <li>审定合计回写 TB(1711) 并驱动附注披露；各表填妥
    >
      <summary>编制提示</summary>
      <ul>
        <li>（1）~（2）变动矩阵与附注五、28 子表一致，可从 I3-2 取数</li>
        <li>（3）~（8）文字按 15 号文及风险提示第 8 号，即使未减值也须披露测试过程与参数</li>
        <li>点「同步到附注」将原值/减值细列汇总 + 关键假设参数 + 业绩承诺 + 文字写入附注模块</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang=
    >
      <summary>编制提示（对齐 Excel I3-1）</summary>
      <ol>
        <li>优先「从 I3-2 带入」生成被投资单位行；Excel 中审定表金额主要引用明细表。</li>
        <li>账项调整从 I3-3 同步（仅 1711）；本期减值可从 I3-6 同步或沿用明细本期减值。</li>
        <li>期末＝期初＋增加−减少；净额＝原值−累计减值；二者应一致。差异行与 TB 须为 0。</li>
        <li>商誉不摊销、减值不可转回；保存后回写 TB 1711 并通知附注。</li>
        <li>「带入调整」：从集中登记按科目 1711 拉取调整分录，逐笔分配到各被投资单位的 AJE/RJE，带入后审定数自动更新并联动附注。</li>
      </ol>
    </details>

    <AdjudicationBringInDialog
      v-model=
    >
      <summary>编制提示（对齐 Excel I3-5）</summary>
      <ol>
        <li>先勾选测试原因并填第二节总体，再抽样本填入第三节；检查比例=样本借方÷本期借方（总体为 0 显示 N/A）。</li>
        <li>无新并购时本期借方可为 0，可改用「带入原值合计」作存在性测试总体，并在说明中解释。</li>
        <li>核对 1~5 对应测试内容说明；选「×」时自动标记异常，并可写入调整建议草稿。</li>
        <li>入账价值测算见 I3-4；减值测试见 I3-6~8。专项风险关注区可记载迹象/CGU 段落结论。</li>
      </ol>
    </details>

    <el-dialog
      v-model=
    >
      <summary>📋 编制提示</summary>
      <ul>
        <li>「是否属于同一控制」选「是」时，⑤商誉强制为 0，不得确认商誉。</li>
        <li>④应占份额 = ②可辨认净资产公允价值 × ③股权比例；⑤商誉 = ①合并成本 − ④。</li>
        <li>入账金额应与⑤商誉一致（非同一控制）；差异须在备注说明。</li>
        <li>合并成本勿计入中介等购买费用；费用可记在备注或审计说明中复核费用化。</li>
        <li>本表结果写入 I3-4-rows，供 I3-2 明细初始确认勾稽。</li>
      </ul>
    </details>

    <!-- 二、审计过程：测算表 -->
    <div class=
    ] as const

// ─── Pure helpers（导出供测试）───────────────────────────────────────────────

export function calcRollEnding(opening: number, increase: number, decrease: number): number {
  return opening + increase - decrease
}

export function calcAudited(unadj: number, aje: number): number {
  return unadj + aje
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI3Detail(
  wpId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    adjGoodwillOriginalSubtotal?: Ref<number>
    adjAccImpairmentSubtotal?: Ref<number>
    adjNetValueSubtotal?: Ref<number>
    onSave?: (itemId: string, value: any) => void
  },
) {
  const rows = ref<I3DetailRow[]>([])
  const activeSection = ref<I3DetailSection>(0)
  const activeRowIndex = ref<number>(-1)

  function _loadRows(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion
    if (!raw) {
      rows.value = []
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) {
        rows.value = parsed.map((r) => {
          const row = _normalizeRow(r)
          _recalcRow(row)
          return row
        })
      } else {
        rows.value = []
      }
    } catch {
      rows.value = []
    }
  }

  function _n(v: any): number {
    const n = Number(v)
    return Number.isFinite(n) ? n : 0
  }

  function _normalizeRow(raw: any): I3DetailRow {
    // 兼容旧数据：无滚动字段时从 accImpairment*/goodwillOriginal 回填
    const costOpening = raw.costOpening != null ? _n(raw.costOpening) : _n(raw.goodwillOriginal)
    const costIncrease = _n(raw.costIncrease)
    const costDecrease = _n(raw.costDecrease)
    const costEndingRaw = raw.costEnding != null
      ? _n(raw.costEnding)
      : calcRollEnding(costOpening, costIncrease, costDecrease)
    const costUnadj = raw.costUnadj != null ? _n(raw.costUnadj) : costEndingRaw
    const costAje = _n(raw.costAje)

    const impOpening = raw.impOpening != null ? _n(raw.impOpening) : _n(raw.accImpairmentBegin)
    const impIncrease = raw.impIncrease != null ? _n(raw.impIncrease) : _n(raw.currentImpairment)
    const impDecrease = _n(raw.impDecrease)
    const impEndingRaw = raw.impEnding != null
      ? _n(raw.impEnding)
      : calcRollEnding(impOpening, impIncrease, impDecrease)
    const impUnadj = raw.impUnadj != null ? _n(raw.impUnadj) : impEndingRaw
    const impAje = _n(raw.impAje)

    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      investee: raw.investee ?? 
    ] as const

export interface I3DetailSummary {
  costOpening: number
  costIncrease: number
  costDecrease: number
  costEnding: number
  costUnadj: number
  costAje: number
  costAudited: number
  impOpening: number
  impIncrease: number
  impDecrease: number
  impEnding: number
  impUnadj: number
  impAje: number
  impAudited: number
  /** Σ 本期借方发生额（= Σ costIncrease） */
  periodDebit: number
  /** Σ 本期贷方发生额（= Σ costDecrease + Σ impIncrease） */
  periodCredit: number
  mergerCost: number
  netAssetFairValue: number
  entryGoodwillCalc: number
  minorityInterest: number
  costConsideration: number
  costContingent: number
  costTransactionFee: number
  consideration: number
  counterpartyNetAsset: number
  // 兼容
  goodwillOriginal: number
  accImpairmentBegin: number
  currentImpairment: number
  accImpairmentEnd: number
  goodwillNetValue: number
  recoverableAmount: number
}

export interface I3DetailCrossValidation {
  goodwillOriginalDiff: number
  accImpairmentDiff: number
  netValueDiff: number
  hasOriginalWarning: boolean
  hasImpairmentWarning: boolean
  hasNetValueWarning: boolean
  hasAnyWarning: boolean
}

/** 单行滚动勾稽校验 */
export interface I3RollForwardCheck {
  rowId: string
  investee: string
  costOk: boolean
  costDiff: number
  impOk: boolean
  impDiff: number
  costAuditOk: boolean
  costAuditDiff: number
  impAuditOk: boolean
  impAuditDiff: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 
    }：AJE/RJE 为近似分摊，建议复核`)
    }
  }
  if (Math.abs(opts.tbDiff) > 0.01) {
    blockers.push(`与 TB 差异 ${opts.tbDiff.toFixed(2)}，须勾稽为 0 后再回写`)
  }
  return { ok: blockers.length === 0, blockers, warnings }
}

/** 用 I3-6 商誉承担减值覆盖「本期减少」；无法按名称匹配时回退按合计比例 */
export function applyI3ImpairmentFromTest(
  rows: I3AdjudicationRowModel[],
  byCguOrInvestee: Record<string, number>,
  totalGoodwillImpairment: number,
): I3AdjudicationRowModel[] {
  if (!rows.length) return rows
  const keyed = { ...byCguOrInvestee }
  let matched = 0
  const next = rows.map((r) => {
    const hit = keyed[r.investee]
    if (hit != null && Number.isFinite(hit)) {
      matched++
      return recalcI3AdjudicationRow({ ...r, impairment: Math.max(0, _num(hit)) })
    }
    return r
  })
  if (matched > 0) return next
  if (!(totalGoodwillImpairment > 0)) return rows
  // 无名称匹配：按原值占比分摊总减值
  const bases = rows.map((r) => Math.abs(r.initialRecognition) || Math.abs(r.beginBalance))
  const sum = calcSubtotal(bases)
  if (!(sum > 0)) {
    return rows.map((r, i) => recalcI3AdjudicationRow({
      ...r,
      impairment: i === 0 ? totalGoodwillImpairment : r.impairment,
    }))
  }
  let left = totalGoodwillImpairment
  return rows.map((r, i) => {
    const isLast = i === rows.length - 1
    const amt = isLast ? _round2(left) : _round2(totalGoodwillImpairment * (bases[i] / sum))
    left = _round2(left - amt)
    return recalcI3AdjudicationRow({ ...r, impairment: Math.max(0, amt) })
  })
}

export function buildI3AdjudicationCrossCheck(
  rows: I3AdjudicationRowModel[],
  detail: {
    goodwillOriginalTotal: number
    accImpairmentTotal: number
    netValueTotal: number
    currentImpairmentTotal: number
  },
): I3AdjudicationCrossCheck {
  const sub = summarizeI3Adjudication(rows)
  const originalDiff = _round2(sub.initialRecognition - _num(detail.goodwillOriginalTotal))
  const netDiff = _round2(sub.netValue - _num(detail.netValueTotal))
  const impairmentDiff = _round2(sub.impairment - _num(detail.currentImpairmentTotal))
  const endVsNetDiff = _round2(sub.endBalance - sub.netValue)
  return {
    detailOriginal: _num(detail.goodwillOriginalTotal),
    detailAccImpairment: _num(detail.accImpairmentTotal),
    detailNet: _num(detail.netValueTotal),
    detailCurrentImpairment: _num(detail.currentImpairmentTotal),
    adjOriginal: sub.initialRecognition,
    adjAccImpairment: sub.accImpairment,
    adjNet: sub.netValue,
    adjCurrentImpairment: sub.impairment,
    originalDiff,
    netDiff,
    impairmentDiff,
    endVsNetDiff,
    hasWarning:
      Math.abs(originalDiff) > 0.01
      || Math.abs(netDiff) > 0.01
      || Math.abs(impairmentDiff) > 0.01
      || Math.abs(endVsNetDiff) > 0.01,
  }
}

export function buildI3AdjudicationConclusionDraft(opts: {
  rowCount: number
  auditedTotal: number
  netTotal: number
  newAcquisitionTotal: number
  impairmentTotal: number
  tbDiff: number
  crossCheck?: I3AdjudicationCrossCheck | null
}): string {
  const parts = [
    `经审定，商誉(1711)共 ${opts.rowCount} 个被投资单位，审定合计 ${opts.auditedTotal.toLocaleString(
    }：期末余额(${row.endBalance})与净额(${row.netValue})不一致，请核对期初/原值/累计减值`,
        })
      }
    }
    return result
  })

  function getWarnings(): I3Warning[] {
    return warnings.value
  }

  const tbRow = computed(() => ({
    unadjusted: options?.tbUnadjusted1711?.value ?? 0,
    audited: options?.tbAudited1711?.value ?? 0,
  }))

  const differenceRows = computed<I3DifferenceRow[]>(() => {
    const tbUnadj = options?.tbUnadjusted1711?.value ?? 0
    const auditedTotal = subtotals.value.audited
    return [
      {
        label: 
  I4: 85 个
    

  return { findings, summaryText, hasWarning, hasError, empty: false }
}

export function buildI44CrossNoteBlock(result: I45I44CrossResult): string {
  const lines = result.findings.map((f) => {
    const tag = f.severity === 
    

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** I4-2 明细行原始 JSON（滚转字段 + 旧别名） */
export interface I4DetailRowRaw {
  rowId?: string
  name?: string               // 项目名称
  category?: string           // 费用类型
  incurredDate?: string       // 发生日期
  originalAmount?: number     // 原始金额

  // 摊销区段
  amortizationMethod?: string // 摊销方法（直线法/工作量法）
  totalMonths?: number        // 摊销总月数
  elapsedMonths?: number      // 已摊月数
  accAmortization?: number    // 累计摊销
  currentAmortization?: number // 本期摊销

  // 余额区段
  beginBalance?: number       // 期初余额
  increase?: number           // 本期增加
  decrease?: number           // 本期减少（非摊销的减少，如处置）
  endBalance?: number         // 期末余额
  remainingMonths?: number    // 剩余月数
}

/** I4-3 调整分录行原始 JSON 结构（对齐 Excel 列 + 兼容旧 AJE/RJE 字段） */
export interface I4AdjustmentRowRaw {
  rowId?: string
  description?: string        // 调整事项说明
  category?: string           // 账项调整 / 报表调整 / 其他
  entryType?: string          // AJE / RJE（由类别推导，兼容旧数据）
  reportItem?: string         // 报表项目
  accountCode?: string        // 科目代码
  accountName?: string        // 科目名称
  noteItem?: string           // 附注项目
  summary?: string            // 摘要（旧字段，等同 description）
  debitAmount?: number        // 借方调整金额
  creditAmount?: number       // 贷方调整金额
  debit?: number              // 旧字段兼容
  credit?: number             // 旧字段兼容
  indexRef?: string           // 索引
  remark?: string
  projectName?: string        // 明细项目（匹配 I4-2 / I4-1）
}

/** I4-6/I4-7 摊销测算行原始 JSON 结构（源表测算/账面/差异 或旧12月矩阵） */
export interface I4AmortizationRowRaw {
  rowId?: string
  name?: string
  itemName?: string
  originalAmount?: number
  totalMonths?: number
  totalUnits?: number
  workStandard?: number
  monthlyAmorts?: number[]
  monthlyAmort?: number[]
  yearTotal?: number
  calcPeriodAmort?: number
  periodAmortization?: number
  annualTotal?: number
}

// ─── Return Types ────────────────────────────────────────────────────────────

/** I4-2 明细合计 → I4-1 审定表交叉验证 */
export interface I4DetailTotals {
  total: number               // 原始金额合计
  amortization: number        // 本期摊销合计（从明细行累加）
  beginBalance: number        // 期初余额合计
  increase: number            // 本期增加合计
  decrease: number            // 本期减少合计
  endBalance: number          // 期末余额合计
}

/** 审定数从明细聚合 → I4-1 审定表 */
export interface I4AdjudicationFromDetail {
  audited: number             // 期末余额合计（= I4-1 审定表审定数来源）
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 安全解析 JSON 数组字符串，失败回退空数组
 */
function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/**
 * 安全提取数值，NaN/null/undefined → 0
 */
function _getNum(val: any): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI4CrossSheet(allResponses: Ref<Map<string, any>>): {
  detailTotals: ComputedRef<I4DetailTotals>
  adjudicationFromDetail: ComputedRef<{ audited: number }>
  amortizationMatrix: ComputedRef<number[][]>
  detailRowsRaw: ComputedRef<any[]>
  adjustmentRowsRaw: ComputedRef<I4AdjustmentRowRaw[]>
  amortizationRowsRaw: ComputedRef<I4AmortizationRowRaw[]>
} {
  // ─── 解析 I4-2 明细行数据 ──────────────────────────────────────────────

  const detailRowsRaw = computed<any[]>(() => {
    const resp = allResponses.value.get(
    

// ─── Types ───────────────────────────────────────────────────────────────────

export interface I4DetailRow {
  rowId: string

  // ── 项目识别 ──
  projectName: string
  /** Excel「类别」A/B/C */
  category: string
  /** Excel「资产类型」 */
  assetType: string
  projectCode: string
  /** 费用类型（摊销政策/附注用） */
  expenseType: string

  /** 初始入账金额 */
  originalAmount: number

  // ── 未审数 ──
  unadjOpening: number
  unadjIncrease: number
  unadjAmortization: number
  unadjOtherDecrease: number
  /** 公式：期初+增加−摊销−其他 */
  unadjEnding: number

  // ── 期初调整 + 账项调整 ──
  openingAdj: number
  ajeIncrease: number
  ajeAmortization: number
  ajeOtherDecrease: number

  // ── 审定数（公式）──
  auditedOpening: number
  auditedIncrease: number
  auditedAmortization: number
  auditedOtherDecrease: number
  auditedEnding: number

  // ── 摊销政策 ──
  amortizationMethod: string
  totalMonths: number
  elapsedMonths: number
  accAmortization: number
  monthlyAmortization: number
  amortizationStartMonth: string
  remainingMonths: number
  amortizationProgress: number

  // ── 基础 / 索引 ──
  occurDate: string
  accountCategory: string
  contractNo: string
  startDate: string
  endDate: string
  indexNo: string
  remark: string
  status: string

  // ── 旧字段别名（回写，供下游）──
  /** @deprecated → auditedOpening */
  beginBalance: number
  /** @deprecated → auditedIncrease */
  currentIncrease: number
  /** @deprecated → auditedAmortization */
  currentAmortization: number
  /** @deprecated → auditedOtherDecrease */
  currentDecrease: number
  /** @deprecated → auditedEnding */
  endBalance: number
  /** @deprecated → unadjOpening（上期审定代理） */
  priorBalance: number
}

export type I4DetailSection = 0 | 1 | 2 | 3

export const I4_DETAIL_SECTION_LABELS = [
    

export interface I4DisclosureRow {
  rowId: string
  /** 披露项目（类别） */
  item: string
  beginBalance: number
  increase: number
  amortization: number
  otherDecrease: number
  endBalance: number
  /** 国企：其他减少原因 */
  otherDecreaseReason: string
  isAutoFilled: boolean
  remark: string
}

export interface I4DisclosureTotals {
  beginBalance: number
  increase: number
  amortization: number
  otherDecrease: number
  endBalance: number
}

export const I4_DISC_KEYS = {
  listedRows: 
    

export {
  type I4TargetedCheckRow,
  type I4TargetedSampleMeta,
  type I4TargetedRiskFocus,
  type I4TargetedSummary,
  type I4TargetedAdjDraft,
  type I4CoverageFooter,
  type I4CoverageExpansionAdvice,
  type I4SpecificAmountCheck,
  type I4SamplingPreset,
  type I45I44CrossResult,
  type I42ProjectRef,
  emptyI4TargetedRow,
  I4_5_DEFAULT_COVERAGE_THRESHOLD,
  I4_5_TEST_CONTENT,
  I4_5_TEST_REASONS,
  I4_5_SAMPLE_METHODS,
  I4_5_CHECK_OPTIONS,
  I4_5_ABNORMAL_OPTIONS,
  I4_5_OBJECTIVES,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  buildI4CoverageFooter,
  buildI4CoverageExpansionAdvice,
  buildI4CreditCoverageExpansionAdvice,
  isCoverageNoteSatisfied,
  checkI4SpecificAmountConsistency,
  buildI4SamplingPresetFromTestReasons,
  applyI4SelectionReasonsToSamples,
  crossCheckI45WithI44,
  buildI44CrossNoteBlock,
  parseI44PolicySnapshot,
  suggestAbnormalFromFailedChecks,
  syncSpecificAmountFromRows,
  extractI42ProjectCatalog,
  enrichRowsWithI42Projects,
  matchI42ProjectName,
  buildI43LinesFromTargetedDrafts,
  mergeI43LinesSkippingExisting,
  isAbnormalFlag,
  hasFailedCheck,
  buildI4TargetedConclusionDraft,
  buildI4TargetedAdjDrafts,
  mapSampledToI4TargetedRow,
} from 
    
      if (mapped.selectionReason) mapped.isSpecific = true
      const { isHighValue: _hv, summary: _sum, ...row } = mapped as any
      rows.value.push(row)
    }
    const n = mappedBatch.length
    if (n > 0 && !sampleMeta.value.sampleSize) {
      sampleMeta.value.sampleSize = rows.value.length
    }
    return n
  }

  /** 为空项目名按摘要模糊挂接 I4-2 */
  function linkProjectsFromI42(overwrite = false): { ok: boolean; linked: number; message: string } {
    const catalog = i42ProjectCatalog.value
    if (!catalog.length) return { ok: false, linked: 0, message: 
    
  const end = new Date(start.getFullYear(), start.getMonth() + lifeMonths, start.getDate() - 1)
  return fmtDate(end)
}

/**
 * 直线法月摊销 = 原始金额 ÷ 摊销总月数
 */
export function calcStraightLineAmort(originalAmount: number, totalMonths: number): number {
  if (totalMonths <= 0) return 0
  return originalAmount / totalMonths
}

/**
 * 工作量法月摊销 = 原始金额 × (本月工作量 ÷ 总预计工作量)
 */
export function calcUnitsOfProductionAmort(originalAmount: number, currentUnits: number, totalUnits: number): number {
  if (totalUnits <= 0) return 0
  return originalAmount * (currentUnits / totalUnits)
}

/** 摊销标准 = 原值 ÷ 工作标准（I4-7） */
export function calcAmortStandard(originalAmount: number, workStandard: number): number {
  if (workStandard <= 0) return 0
  return originalAmount / workStandard
}

/** 按摊销标准测算 = 工作量 × 摊销标准（I4-7） */
export function calcUnitsAmortByStandard(units: number, amortStandard: number): number {
  return (units || 0) * (amortStandard || 0)
}

/** 摊销额差异 = 测算 − 账面（I4-7） */
export function calcAmortDiff(calculated: number, book: number): number {
  return (calculated || 0) - (book || 0)
}

export function calcRemainingMonths(totalMonths: number, elapsedMonths: number): number {
  return totalMonths - elapsedMonths
}

export function calcAmortizationRate(elapsed: number, total: number): number {
  if (total <= 0) return 0
  return elapsed / total
}

// ─── I4-6 源表对齐：直线法整行测算 ───────────────────────────────────────────

export interface StraightLineAmortTestResult {
  lifeMonths: number
  fullAmortDate: string
  /** 已摊销月份 J（至截止日或到期日孰早） */
  monthsAmortized: number
  remainingMonths: number
  /** 本期摊销月份（期间四分支，修正源表对老资产虚增） */
  periodMonths: number
  /** 测算月摊销额 M = 原值 / 月限 */
  calcMonthlyAmort: number
  /** 当期摊销 N = M × L */
  periodAmortization: number
  /** 月摊销额差异 O = 账面月摊 − 测算月摊（源表方向） */
  monthlyDiff: number
  /** 累计摊销费用(测算) P = M × J */
  calcAccumAmort: number
  /** 累计摊销额差异 Q = 账面累计 − 测算累计（源表方向） */
  accumDiff: number
}

/**
 * I4-6 直线法整行测算（对齐源 xlsx「摊销测算I4-6」C~Q）。
 *
 * 改进点：
 * 1. 开始日为空时不推算到期日（避免源表 1900-1-0）
 * 2. 本期月数用期间四分支，并夹紧至剩余月数/12，避免对期初前已投入使用项目虚增
 */
export function calcStraightLineAmortTest(input: {
  originalAmount: number
  usefulLife: number | string
  startDate?: string | null
  periodBegin?: string | null
  periodEnd?: string | null
  bookMonthlyAmort?: number
  bookAccumAmort?: number
}): StraightLineAmortTestResult {
  const empty: StraightLineAmortTestResult = {
    lifeMonths: 0,
    fullAmortDate: 
    
  expected: number
  actual: number
  diff: number
  message?: string
}

export interface I4CategorySubtotal {
  category: string
  count: number
  auditedEnding: number
  unadjEnding: number
  auditedAmortization: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 
    
  if (!usefulLife && r.totalMonths) {
    const tm = Number(r.totalMonths) || 0
    usefulLife = tm > 0 && tm % 12 === 0 ? `${tm / 12}年` : String(tm)
  }

  const row: StraightAmortRow = {
    rowId: r.rowId || `i4s-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    category: r.category ?? 
    
  reportItem: string
  accountCode: string
  accountName: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
  /** 明细项目名（供 I4-1 / I4-2 精确匹配） */
  projectName: string
  /** 兼容旧字段 */
  summary?: string
  debit?: number
  credit?: number
  sourceGroupId?: string
}

const ROWS_KEY = 
    
  return `${rate.toFixed(2)}%`
}

export function formatLayeredCoverageLabel(summary: I4TargetedSummary): string {
  if (summary.coverageRate == null) return 
    
  return `借方 ${summary.coverageRate.toFixed(2)}%（特定 ${sp}% + 抽样 ${sa}%）`
}

/** Excel 表尾三行：合计 / 本期发生额 / 检查比例（避免 #DIV/0!） */
export interface I4CoverageFooter {
  checkedDebitTotal: number
  checkedCreditTotal: number
  periodDebitTotal: number
  periodCreditTotal: number
  debitCoverageLabel: string
  creditCoverageLabel: string
  layeredCoverageLabel: string
}

export function buildI4CoverageFooter(
  summary: I4TargetedSummary,
  periodCreditTotal = 0,
): I4CoverageFooter {
  return {
    checkedDebitTotal: summary.checkedDebitTotal,
    checkedCreditTotal: summary.checkedCreditTotal,
    periodDebitTotal: summary.periodTotal,
    periodCreditTotal,
    debitCoverageLabel: formatCoverageLabel(summary.coverageRate),
    creditCoverageLabel: formatCoverageLabel(summary.creditCoverageRate),
    layeredCoverageLabel: formatLayeredCoverageLabel(summary),
  }
}

/** 核对× → 建议「是否异常」取值（便于编制人快速标注） */
export function suggestAbnormalFromFailedChecks(row: I4TargetedCheckRow): string {
  if (row.check3 === 
    
  title: string
  detail: string
}

export interface I45I44CrossResult {
  findings: I45I44CrossFinding[]
  summaryText: string
  hasWarning: boolean
  hasError: boolean
  empty: boolean
}

function _casOf(snap: I44PolicySnapshot, key: string) {
  return snap.casItems.find((c) => c.key === key)
}

/**
 * I4-5 抽凭结果 × I4-4 摊销政策结论自动交叉印证
 */
export function crossCheckI45WithI44(opts: {
  rows: I4TargetedCheckRow[]
  testReasons: string[]
  riskFocus: I4TargetedRiskFocus
  i44: I44PolicySnapshot | null
}): I45I44CrossResult {
  const findings: I45I44CrossFinding[] = []
  const i44 = opts.i44
  if (!i44 || (!i44.casItems.length && !i44.overallConclusion && !i44.policyParams.length)) {
    return {
      findings: [{
        id: 
    
const rows = ref<UnitsAmortRow[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)

const importExport = useI4ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  onImported: () => _load(),
})

function _load(): void {
  const item = props.allResponses.get(`${PREFIX}-rows`)
  if (item?.remark) {
    try {
      const parsed = JSON.parse(item.remark)
      rows.value = Array.isArray(parsed) ? parsed.map(_ensureRow) : []
    } catch {
      rows.value = []
    }
  } else {
    rows.value = []
  }
}

/** 兼容旧版 12 月矩阵字段 */
function _ensureRow(r: any): UnitsAmortRow {
  const originalAmount = Number(r.originalAmount ?? 0) || 0
  const workStandard = Number(r.workStandard ?? r.totalUnits ?? 0) || 0
  let periodUnits = Number(r.periodUnits ?? r.currentUnits ?? 0) || 0
  let accumUnits = Number(r.accumUnits ?? r.completedUnits ?? 0) || 0

  // 旧矩阵：monthlyUnits 年合计工作量 → 本期；无累计则用本期
  if ((!periodUnits || !accumUnits) && Array.isArray(r.monthlyUnits)) {
    const yearUnits = (r.monthlyUnits as number[]).reduce((s, u) => s + (Number(u) || 0), 0)
    if (!periodUnits) periodUnits = yearUnits
    if (!accumUnits) accumUnits = yearUnits + (Number(r.priorAccumulatedUnits) || 0)
  }

  const bookPeriodAmort = Number(r.bookPeriodAmort ?? 0) || 0
  let bookAccumAmort = Number(r.bookAccumAmort ?? r.priorAccumulated ?? 0) || 0
  // 旧矩阵累计摊销若仅有 prior+year，可作账面累计初值（仅当未单独录入账面）
  if (!r.bookAccumAmort && Array.isArray(r.monthlyAmort) && r.priorAccumulated != null) {
    const yearAmort = (r.monthlyAmort as number[]).reduce((s, u) => s + (Number(u) || 0), 0)
    bookAccumAmort = (Number(r.priorAccumulated) || 0) + yearAmort
  }

  const row: UnitsAmortRow = {
    rowId: r.rowId || `i4u-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    category: r.category ?? 
    
import {
  type I4AdjudicationRowModel,
  type I4AdjudicationCrossCheck,
  emptyI4AdjudicationRow,
  normalizeI4AdjudicationRow,
  summarizeI4Adjudication,
  seedI4AdjudicationFromDetail,
  applyAjeFromI43,
  applyAmortFromI46,
  buildI4AdjudicationCrossCheck,
  buildI4ExcelLeadSummary,
  buildI4CategorySummary,
  buildI4AdjudicationConclusionDraft,
  validateI4AdjudicationSave,
  recalcI4AdjudicationRow,
  formatI4VarianceRate,
  I4_ADJ_ROWS_KEY,
  I4_ADJ_NOTE_KEY,
  I4_ADJ_CONCLUSION_KEY,
  I4_ADJ_MATTERS_KEY,
  I4_CONCLUSION_OPTIONS,
} from 
    
import {
  type I4TargetedCheckRow,
  type I4TargetedSampleMeta,
  type I4TargetedRiskFocus,
  type I4TargetedSummary,
  emptyI4TargetedRow,
  emptyI4TargetedSampleMeta,
  emptyI4TargetedRiskFocus,
  normalizeI4TargetedRow,
  normalizeI4TargetedSampleMeta,
  normalizeI4TargetedRiskFocus,
  summarizeI4Targeted,
  extractI4PeriodMovement,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  buildI4CoverageFooter,
  buildI4TargetedConclusionDraft,
  buildI4TargetedAdjDrafts,
  buildI4CoverageExpansionAdvice,
  buildI4CreditCoverageExpansionAdvice,
  isCoverageNoteSatisfied,
  checkI4SpecificAmountConsistency,
  buildI4SamplingPresetFromTestReasons,
  applyI4SelectionReasonsToSamples,
  crossCheckI45WithI44,
  buildI44CrossNoteBlock,
  parseI44PolicySnapshot,
  mapSampledToI4TargetedRow,
  suggestAbnormalFromFailedChecks,
  syncSpecificAmountFromRows,
  extractI42ProjectCatalog,
  enrichRowsWithI42Projects,
  buildI43LinesFromTargetedDrafts,
  mergeI43LinesSkippingExisting,
  isAbnormalFlag,
  hasFailedCheck,
  I4_5_DEFAULT_COVERAGE_THRESHOLD,
} from 
     && remark) {
      try {
        const p = JSON.parse(remark)
        return Array.isArray(p) ? p : []
      } catch { return [] }
    }
    if (Array.isArray(remark)) return remark
  }
  return []
}

/**
 * 从 I4-2 明细推算本期发生额：
 * 优先 unadjIncrease/auditedIncrease（滚动字段）或 currentIncrease；
 * 减少优先 unadjOtherDecrease / currentDecrease；
 * 无滚动字段时回退按 occurDate 年份代理 originalAmount。
 */
export function extractI4PeriodMovement(raw: unknown, asOfYear?: number): I4PeriodMovement {
  const rows = _parseI42Rows(raw)
  let debitTotal = 0
  let creditTotal = 0
  let originalTotal = 0
  let usedRoll = false
  for (const r of rows) {
    if ((r?.projectName || r?.name) === 
     ? JSON.parse(raw) : raw
      if (Array.isArray(parsed) && parsed.length > 0) {
        rows.value = parsed.map(normalizeI4DetailRow)
      } else {
        rows.value = []
      }
    } catch {
      rows.value = []
    }
  }

  function _persist(): void {
    options?.onSave?.(ITEM_ID_ROWS, JSON.stringify(rows.value))
  }

  function recalcAll(): void {
    for (const row of rows.value) recalcI4DetailRow(row)
  }

  const subtotals: ComputedRef<I4DetailSubtotals> = computed(() => {
    const r = rows.value
    const auditedOpening = calcSubtotal(r.map((x) => x.auditedOpening))
    const auditedIncrease = calcSubtotal(r.map((x) => x.auditedIncrease))
    const auditedAmortization = calcSubtotal(r.map((x) => x.auditedAmortization))
    const auditedOtherDecrease = calcSubtotal(r.map((x) => x.auditedOtherDecrease))
    const auditedEnding = calcSubtotal(r.map((x) => x.auditedEnding))
    return {
      originalAmount: calcSubtotal(r.map((x) => x.originalAmount)),
      unadjOpening: calcSubtotal(r.map((x) => x.unadjOpening)),
      unadjIncrease: calcSubtotal(r.map((x) => x.unadjIncrease)),
      unadjAmortization: calcSubtotal(r.map((x) => x.unadjAmortization)),
      unadjOtherDecrease: calcSubtotal(r.map((x) => x.unadjOtherDecrease)),
      unadjEnding: calcSubtotal(r.map((x) => x.unadjEnding)),
      openingAdj: calcSubtotal(r.map((x) => x.openingAdj)),
      ajeIncrease: calcSubtotal(r.map((x) => x.ajeIncrease)),
      ajeAmortization: calcSubtotal(r.map((x) => x.ajeAmortization)),
      ajeOtherDecrease: calcSubtotal(r.map((x) => x.ajeOtherDecrease)),
      auditedOpening,
      auditedIncrease,
      auditedAmortization,
      auditedOtherDecrease,
      auditedEnding,
      beginBalance: auditedOpening,
      currentIncrease: auditedIncrease,
      currentAmortization: auditedAmortization,
      currentDecrease: auditedOtherDecrease,
      endBalance: auditedEnding,
      accAmortization: calcSubtotal(r.map((x) => x.accAmortization)),
    }
  })

  const rollWarnings = computed(() => collectI4RollWarnings(rows.value))
  const categorySubtotals = computed(() => summarizeI4ByCategory(rows.value))

  function switchSection(section: I4DetailSection): void {
    activeSection.value = section
  }

  function setActiveRow(index: number): void {
    activeRowIndex.value = index
  }

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    recalcI4DetailRow(row)
    _persist()
  }

  async function addRow(): Promise<void> {
    try {
      const { value: name } = await ElMessageBox.prompt(
        
     open>
      <summary>编制提示</summary>
      <ul>
        <li>本表对齐源模板：表A（政策+五维判断）→ 表B（同业受益期/方法）→ 有变更则表C（原估计）。</li>
        <li>优先「从 I4-2 带入」；可用「从测算回填空白」将 I4-6/7 众数填入表A空字段。</li>
        <li>表A 与 I4-6/7 自动勾稽；「标记关注」写备注，「生成 I4-3 补提草稿」按重大差异落分录。</li>
        <li>「建议同业合理」按表B区间自动填 Y/N；偏离须在备注说明，否则完成度闸门不通过。</li>
        <li>「年报库拉取 / 拉取推荐行业」按项目名称或明细费用结构推荐行业；摘录库须核对手工年报后再作证据。</li>
        <li>装修/租赁改良须满足受益期 ≤ 租赁期孰短（读 I4-2 起止日）；违反则闸门阻断。</li>
        <li>闸门全部通过后方可「标记已完成」，并与目录状态硬绑定；估计变更属 CAS28 未来适用法。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang=
     open>
      <summary>编制提示（对齐 Excel 长期待摊费用调整分录汇总表 I4-3）</summary>
      <div class=
     open>
      <summary>编制说明</summary>
      <ol>
        <li>工作量法适用于受益与产出/使用量直接相关的长期待摊费用（如模具费按产量、矿区权益按采矿量、装修费按特定产出）。</li>
        <li>摊销标准 = 原值 ÷ 工作标准；测算本年摊销 = 本期工作量 × 摊销标准；测算累计 = 累计工作量 × 摊销标准（等价于 原值 × 工作量/工作标准）。</li>
        <li>工作标准与实际工作量须有客观依据（生产台账、产量统计、合同约定等），并与 I4-4 摊销政策检查结论一致。</li>
        <li>差异 = 测算 − 账面；本期或累计差异重大时，追查工作量计量错误、政策误用或需提调整分录（I4-3）。</li>
        <li>累计工作量不得超过工作标准；超额部分应说明是否需变更估计（未来适用法）或转销剩余余额。</li>
        <li>本表仅用于长期待摊费用，不得套用无形资产使用寿命有限/不确定等判断规则（彼属 I1）。</li>
      </ol>
    </details>

    <input ref=
     open>
      <summary>编制说明</summary>
      <ol>
        <li>本表对齐源底稿「附注披露（上市公司）」：项目滚动，非原值+累计摊销双矩阵。</li>
        <li>数据优先自 I4-2 按费用类型/资产类型聚合；手工修改后取消「自动」标记，强制覆盖可重刷。</li>
        <li>同步附注时写入 note_template §五、29「长期待摊费用」子表；本期减少=摊销+其他减少。</li>
        <li>一年内到期金额为信息性披露，不改变列报分类。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang=
     open>
      <summary>编制说明</summary>
      <ol>
        <li>本表对齐源底稿「附注披露（国有企业）」：分列摊销额与其他减少额，并披露减少原因。</li>
        <li>数据优先自 I4-2 聚合；同步写入 note_template §八、30「长期待摊费用」子表。</li>
        <li>其他减少额非零时，原因列应填写（处置、转销、重分类等）。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang=
     open>
      <summary>编制说明</summary>
      <ol>
        <li>直线法：测算月摊销额 = 原值 ÷ 使用月限；当期摊销 = 测算月摊 × 本期摊销月份。</li>
        <li>使用年限填「N年」或月数；系统解析为使用月限。测算到期日 = 开始使用日期 + 月限 − 1 天（开始日为空则不推算，避免 1900-1-0）。</li>
        <li>本期摊销月份按摊销期初/期末与项目起止的四分支重叠计算，并不超过剩余月数，避免对期初前已投入使用的项目虚增本期月数。</li>
        <li>月摊销额差异 = 账面月摊 − 测算月摊；累计摊销额差异 = 账面累计 − 测算累计。差异重大时追查受益期估计或起止时点，必要时提调整（I4-3）。</li>
        <li>受益期限须有依据：装修费不超过租赁期与使用年限孰短；开办费等通常 3~5 年；与 I4-4 政策检查结论一致。</li>
        <li>本表仅用于长期待摊费用直线法，不得套用无形资产使用寿命有限/不确定等判断规则（彼属 I1）。</li>
      </ol>
    </details>

    <input ref=
     }
  })

  const summary: ComputedRef<I4TargetedSummary> = computed(() =>
    summarizeI4Targeted(
      rows.value,
      sampleMeta.value.populationAmount,
      sampleMeta.value.populationCreditAmount,
    ),
  )

  const coverageLow = computed(() =>
    summary.value.coverageRate != null
    && summary.value.coverageRate < sampleMeta.value.coverageThreshold
    && summary.value.periodTotal > 0,
  )

  const creditCoverageLow = computed(() =>
    summary.value.creditCoverageRate != null
    && summary.value.creditCoverageRate < sampleMeta.value.coverageThreshold
    && sampleMeta.value.populationCreditAmount > 0,
  )

  /** 借方检查比例偏低 → 强制扩样建议 */
  const expansionAdvice = computed(() =>
    buildI4CoverageExpansionAdvice(summary.value, sampleMeta.value.coverageThreshold),
  )

  /** 贷方检查比例偏低 → 对称扩样建议 */
  const creditExpansionAdvice = computed(() => {
    const creditRowCount = rows.value.filter((r) => Number(r.creditAmount) > 0).length
    return buildI4CreditCoverageExpansionAdvice(
      summary.value,
      sampleMeta.value.populationCreditAmount,
      sampleMeta.value.coverageThreshold,
      creditRowCount,
    )
  })

  const coverageNoteOk = computed(() =>
    isCoverageNoteSatisfied(auditNote.value, expansionAdvice.value, creditExpansionAdvice.value),
  )

  /** 第二节特定样本金额 vs 表内特定借方 */
  const specificAmountCheck = computed(() =>
    checkI4SpecificAmountConsistency(
      sampleMeta.value.specificAmount,
      summary.value.specificDebitTotal,
    ),
  )

  /** 测试原因 → 抽凭引擎预填 */
  const samplingPreset = computed(() =>
    buildI4SamplingPresetFromTestReasons(sampleMeta.value.testReasons),
  )

  /** I4-4 摊销政策交叉印证 */
  const i44Cross = computed(() =>
    crossCheckI45WithI44({
      rows: rows.value,
      testReasons: sampleMeta.value.testReasons,
      riskFocus: riskFocus.value,
      i44: parseI44PolicySnapshot(getMap()),
    }),
  )

  const coverageLabel = computed(() => formatLayeredCoverageLabel(summary.value))
  const creditCoverageLabel = computed(() => formatCoverageLabel(summary.value.creditCoverageRate))

  /** Excel 表尾：合计 / 本期发生额 / 检查比例 */
  const coverageFooter = computed(() =>
    buildI4CoverageFooter(summary.value, sampleMeta.value.populationCreditAmount),
  )

  const coverageTagType = computed(() => {
    if (summary.value.coverageRate == null) return 
     },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI4Detail(
  allResponses: Ref<Map<string, any>>,
  options?: {
    adjBeginSubtotal?: Ref<number>
    adjEndSubtotal?: Ref<number>
    adjAmortizationSubtotal?: Ref<number>
    onSave?: (itemId: string, value: any) => void
  },
) {
  const rows = ref<I4DetailRow[]>([])
  const activeSection = ref<I4DetailSection>(0)
  const activeRowIndex = ref<number>(-1)

  function _loadRows(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 
     交叉验证来源）
   *
   * 当 I4-1 审定数 ≠ 此值时可能存在未记录调整或分类差异。
   *
   * 审定数最终公式：未审数 + AJE + RJE
   * 此处提供的是从明细侧推导的参考值（应与公式结果一致）。
   */
  const adjudicationFromDetail: ComputedRef<{ audited: number }> = computed(() => {
    // 明细侧推导：期末余额合计即为审定后的科目余额
    const totals = detailTotals.value
    return { audited: totals.endBalance }
  })

  // ═══ amortizationMatrix: I4-6/I4-7 → 12月摊销矩阵（Req 6.4-6.6）═════

  /**
   * 从 I4-6（直线法）或 I4-7（工作量法）摊销测算行提取12月摊销矩阵：
   * 返回 number[][]，每行对应一个项目的12个月摊销额。
   *
   * 结构示例：
   * [
   *   [1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000], // 项目A
   *   [500,  500,  500,  500,  500,  500,  500,  500,  500,  500,  500,  500],  // 项目B
   * ]
   *
   * 用途：
   * - I4-1 审定表
    )

  const totals = computed(() => summarizeI4Disclosure(rows.value))
  const footnote = computed(() =>
    isListed.value ? buildI4ListedFootnote(currentPortion.value) : 
    )

  const {
    detailTotals,
    detailRowsRaw,
    adjustmentRowsRaw,
    amortizationRowsRaw,
  } = useI4CrossSheet(allResponses as Ref<Map<string, any>>)

  function _loadRows(): void {
    const data = _getJson(I4_ADJ_ROWS_KEY) ?? _getJson(`${ITEM_PREFIX}-rows`)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(normalizeI4AdjudicationRow)
    } else {
      rows.value = DEFAULT_CATEGORIES.map((cat) => emptyI4AdjudicationRow({ projectName: cat }))
    }
    auditNote.value = _getString(I4_ADJ_NOTE_KEY) || _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(I4_ADJ_CONCLUSION_KEY) || _getString(`${ITEM_PREFIX}-audit-conclusion`)
    significantMatters.value = _getString(I4_ADJ_MATTERS_KEY) || _getString(`${ITEM_PREFIX}-significant-matters`)
  }

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    if (typeof raw !== 
    )

  function load() {
    const map = getMap()
    rows.value = _safeParseArray(map.get(STORAGE_ROWS)).map(normalizeI4TargetedRow)

    sampleMeta.value = normalizeI4TargetedSampleMeta(_parseObject(map.get(STORAGE_SAMPLE)))

    const riskRaw = _parseObject(map.get(STORAGE_RISK)) || _legacyRiskFocusRaw(map)
    riskFocus.value = normalizeI4TargetedRiskFocus(riskRaw)

    auditNote.value = _readText(map.get(STORAGE_NOTE))
    auditConclusion.value = _readText(map.get(STORAGE_CONCLUSION))
      || _readText(map.get(LEGACY_OVERALL_CONCLUSION))

    if (!sampleMeta.value.populationManual) {
      const mv = extractI4PeriodMovement(map.get(I42_ROWS), getYear())
      if (mv.debitTotal > 0) sampleMeta.value.populationAmount = mv.debitTotal
      if (mv.creditTotal > 0) sampleMeta.value.populationCreditAmount = mv.creditTotal
    }
  }

  /** 旧段落型 6 个分散 key 拼装为 riskFocus 迁移对象（无新 STORAGE_RISK 时兜底） */
  function _legacyRiskFocusRaw(map: Map<string, any>): any {
    const majorAddition = _readText(map.get(LEGACY_MAJOR_ADDITION))
    const benefitChange = _readText(map.get(LEGACY_BENEFIT_CHANGE))
    const earlyTermination = _readText(map.get(LEGACY_EARLY_TERMINATION))
    const majorAdditionConclusion = _readText(map.get(LEGACY_MAJOR_ADDITION_CONCLUSION))
    const benefitChangeConclusion = _readText(map.get(LEGACY_BENEFIT_CHANGE_CONCLUSION))
    const earlyTerminationConclusion = _readText(map.get(LEGACY_EARLY_TERMINATION_CONCLUSION))
    if (!majorAddition && !benefitChange && !earlyTermination
      && !majorAdditionConclusion && !benefitChangeConclusion && !earlyTerminationConclusion) {
      return null
    }
    return {
      majorAddition,
      benefitChange,
      earlyTermination,
      majorAdditionConclusion,
      benefitChangeConclusion,
      earlyTerminationConclusion,
    }
  }

  watch(() => {
    const m = getMap()
    return [
      m.get(STORAGE_ROWS),
      m.get(STORAGE_SAMPLE),
      m.get(STORAGE_RISK),
      m.get(STORAGE_NOTE),
      m.get(STORAGE_CONCLUSION),
      m.get(I42_ROWS),
      m.get(LEGACY_MAJOR_ADDITION),
      m.get(LEGACY_BENEFIT_CHANGE),
      m.get(LEGACY_EARLY_TERMINATION),
      m.get(LEGACY_OVERALL_CONCLUSION),
    ]
  }, () => load(), { immediate: true, deep: false })

  const linkedPeriod: ComputedRef<{
    debitTotal: number
    creditTotal: number
    originalTotal: number
    source: string
  }> = computed(() => {
    const mv = extractI4PeriodMovement(getMap().get(I42_ROWS), getYear())
    return mv.debitTotal > 0 || mv.creditTotal > 0 || mv.originalTotal > 0
      ? mv
      : { debitTotal: 0, creditTotal: 0, originalTotal: 0, source: 
    )

  return {
    needed: true,
    side,
    currentRate: rate,
    threshold: th,
    gapPct,
    checkedAmount,
    periodAmount,
    checkedDebit: checkedAmount,
    periodDebit: periodAmount,
    additionalAmountNeeded,
    additionalDebitNeeded: additionalAmountNeeded,
    suggestedExtraSamples,
    actions,
    noteTemplate,
    title: `${sideLabel}检查比例偏低（${rate.toFixed(2)}% < ${th}%）— 请扩样或说明`,
  }
}

/** 借方检查比例偏低 → 强制扩样建议 */
export function buildI4CoverageExpansionAdvice(
  summary: I4TargetedSummary,
  threshold: number,
): I4CoverageExpansionAdvice {
  return _buildSideExpansionAdvice(
    
    )

const {
  rows,
  sampleMeta,
  riskFocus,
  auditNote,
  auditConclusion,
  summary,
  coverageLow,
  creditCoverageLow,
  expansionAdvice,
  creditExpansionAdvice,
  coverageNoteOk,
  specificAmountCheck,
  samplingPreset,
  i44Cross,
  coverageLabel,
  creditCoverageLabel,
  coverageFooter,
  coverageTagType,
  linkedPeriod,
  adjDrafts,
  pushableAdjDrafts,
  i42ProjectNames,
  addRow,
  removeRow,
  updateRow,
  fillFromSampledVouchers,
  linkProjectsFromI42,
  pushAdjDraftsToI43,
  setPopulationAmount,
  syncPopulationFromI42,
  syncSpecificAmount,
  appendAdjDraftsToNote,
  appendExpansionAdviceToNote,
  appendI44CrossToNote,
  fillConclusionDraft,
  canPersist,
  persistAll,
  saveNote,
  saveConclusion,
  saveRiskFocus,
} = useI4TargetedCheck(allResponsesRef, {
  onSave: (itemId, value) => emit(
    )
      ElMessage.error(msg)
      return { ok: false, message: msg }
    }
    if (gate.warnings.length) {
      ElMessage.warning(gate.warnings[0])
    }

    _persist()
    const auditedTotal = subtotals.value.audited
    options?.onSave?.(`${ITEM_PREFIX}-audited-total`, auditedTotal)

    _emitAdjudicated()
    return { ok: true }
  }

  // ─── 显式发布到试算表（显式确认门，复刻 D2/D4-1 范式） ────────────────────────

  /**
   * 确认发布审定数到试算表（科目 1801 长期待摊费用）。
   *
   * spec: tb-writeback-explicit-publish-gate Task 13 / Req 2。
   * 二次确认（中文）→ 保存明细 → `POST /workpapers/{wpId}/audit-determination/publish-to-tb`
   * （审定表 sheet 名 I4-1 + writeback_rows 预算行 1801 balance）。用户取消 → 无副作用。
   */
  async function publishToTb(): Promise<void> {
    if (publishing.value) return

    try {
      await ElMessageBox.confirm(
        
    )
      return
    }
    ElMessage.success(
      result.approx
        ? `已同步 AJE ${result.totalAje} / RJE ${result.totalRje}（含近似分摊，请复核）`
        : `已同步 AJE ${result.totalAje} / RJE ${result.totalRje}（精确匹配 ${result.matchedByName}）`,
    )
  }

  function syncAmortFromI46(): void {
    const amort = amortizationRowsRaw.value.length
      ? amortizationRowsRaw.value
      : [
          ...safeParseRows(_getJson(
    )
      return
    }
    if (rows.value.length === 1) {
      rows.value[0] = recalcI4AdjudicationRow({ ...rows.value[0], priorAudited: total })
    } else {
      const base = rows.value.map((r) => Math.abs(r.beginBalance) || Math.abs(r.unadjusted) || 0)
      const sum = base.reduce((a, b) => a + b, 0)
      if (sum > 0) {
        let left = total
        rows.value = rows.value.map((r, i) => {
          const isLast = i === rows.value.length - 1
          const amt = isLast ? Math.round(left * 100) / 100 : Math.round((total * base[i] / sum) * 100) / 100
          left = Math.round((left - amt) * 100) / 100
          return recalcI4AdjudicationRow({ ...r, priorAudited: amt })
        })
      } else {
        rows.value[0] = recalcI4AdjudicationRow({ ...rows.value[0], priorAudited: total })
      }
    }
    _persist()
    ElMessage.success(
    )
    const known = I4_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === accountCode)
    const debitAmount = parseAmt(raw.debitAmount ?? raw.debit)
    const creditAmount = parseAmt(raw.creditAmount ?? raw.credit)
    const description = String(raw.description ?? raw.summary ?? 
    )
    return safeParseRows<I4AmortizationRowRaw>(resp7?.remark)
  })

  // ═══ detailTotals: I4-2 明细聚合 → I4-1 审定表（Req 2.2-2.5, 3.1-3.2）══

  /**
   * 从 I4-2 明细行聚合长期待摊费用合计：
   * - total: 所有行原始金额之和
   * - amortization: 所有行本期摊销之和
   * - beginBalance / increase / decrease / endBalance
   *
   * 兼容新旧字段：projectName|name、currentIncrease|increase 等。
   */
  const detailTotals: ComputedRef<I4DetailTotals> = computed(() => {
    let total = 0
    let amortization = 0
    let beginBalance = 0
    let increase = 0
    let decrease = 0
    let endBalance = 0

    for (const row of detailRowsRaw.value) {
      const name = String(row?.projectName || row?.name || 
    )
    } finally {
      isSyncing.value = false
    }
  }

  async function generateNoteText(): Promise<string | null> {
    if (!wpId.value) return null
    isAiGenerating.value = true
    try {
      const t = totals.value
      const res = await api.post(`/api/workpapers/${wpId.value}/ai/generate-text`, {
        section: `i4-disclosure-${variant.value}`,
        prompt: 
    )
  const beginBalance = calcSubtotal(detail.map((r) => r.beginBalance))
  const increase = calcSubtotal(detail.map((r) => r.increase))
  const amortization = calcSubtotal(detail.map((r) => r.amortization))
  const decrease = calcSubtotal(detail.map((r) => r.decrease))
  const unadjusted = calcSubtotal(detail.map((r) => r.unadjusted))
  const aje = calcSubtotal(detail.map((r) => r.aje))
  const rje = calcSubtotal(detail.map((r) => r.rje))
  const priorAudited = calcSubtotal(detail.map((r) => r.priorAudited))
  return recalcI4AdjudicationRow({
    rowId: 
    )
  return emptyI4TargetedRow({
    voucherDate: _str(s.voucherDate),
    voucherNo: _str(s.voucherNo),
    businessDesc: _str(s.summary),
    counterpartAccount: _str(s.counterpartAccount),
    projectName,
    debitAmount: _num(s.debitAmount),
    creditAmount: _num(s.creditAmount),
    isSpecific,
    selectionReason: reason || (s.isHighValue ? 
    )
  }

  function applyTbData(tbUnadjustedTotal?: number): void {
    const total = tbUnadjustedTotal ?? tbUnadjusted.value
    if (!rows.value.length) return
    if (rows.value.length === 1) {
      rows.value[0] = recalcI4AdjudicationRow({ ...rows.value[0], unadjusted: total })
    } else {
      const base = rows.value.map((r) => Math.abs(r.beginBalance) || Math.abs(r.endBalance) || 0)
      const sum = base.reduce((a, b) => a + b, 0)
      if (sum > 0) {
        let left = total
        rows.value = rows.value.map((r, i) => {
          const isLast = i === rows.value.length - 1
          const amt = isLast ? Math.round(left * 100) / 100 : Math.round((total * base[i] / sum) * 100) / 100
          left = Math.round((left - amt) * 100) / 100
          return recalcI4AdjudicationRow({ ...r, unadjusted: amt, ajeApprox: rows.value.length > 1 })
        })
      } else {
        rows.value[0] = recalcI4AdjudicationRow({ ...rows.value[0], unadjusted: total })
      }
    }
    _persist()
    ElMessage.success(
    )
  }

  function fillConclusionDraft(): void {
    auditConclusion.value = buildI4AdjudicationConclusionDraft({
      sampleCount: rows.value.length,
      auditedTotal: subtotals.value.audited,
      tbDiff: tbDifference.value,
      hasAje: rows.value.some((r) => Math.abs(r.aje) + Math.abs(r.rje) > 0.005),
      crossWarning: crossCheck.value.hasWarning,
    })
    saveConclusion(auditConclusion.value)
  }

  function applyConclusionTemplate(key: string): void {
    const t = I4_CONCLUSION_OPTIONS.find((x) => x.key === key)
    if (!t) return
    auditConclusion.value = t.text
    saveConclusion(t.text)
  }

  // ─── 显式发布门状态（防重复提交，供发布按钮 :loading 绑定） ─────────────────
  const publishing = ref(false)

  /** 发布下游联动事件（仅 emit，不写 TB）。 */
  function _emitAdjudicated(): void {
    window.dispatchEvent(new CustomEvent(
    )
}

export function summarizeI4Targeted(
  rows: I4TargetedCheckRow[],
  periodDebitTotal: number,
  periodCreditTotal = 0,
): I4TargetedSummary {
  const sampleCount = rows.length
  const checkedDebitTotal = Math.round(rows.reduce((s, r) => s + _num(r.debitAmount), 0) * 100) / 100
  const checkedCreditTotal = Math.round(rows.reduce((s, r) => s + _num(r.creditAmount), 0) * 100) / 100
  const anomalyCount = rows.filter((r) => isAbnormalFlag(r.isAbnormal) || hasFailedCheck(r)).length
  const failCheckCount = rows.filter(hasFailedCheck).length
  const pendingCount = rows.filter((r) => !isRowChecksComplete(r)).length
  const completedCheckCount = rows.filter(isRowChecksComplete).length

  const specificRows = rows.filter((r) => r.isSpecific || !!r.selectionReason)
  const samplingRows = rows.filter((r) => !(r.isSpecific || !!r.selectionReason))
  const specificCount = specificRows.length
  const specificDebitTotal = Math.round(specificRows.reduce((s, r) => s + _num(r.debitAmount), 0) * 100) / 100
  const samplingDebitTotal = Math.round(samplingRows.reduce((s, r) => s + _num(r.debitAmount), 0) * 100) / 100

  let coverageRate: number | null = null
  let creditCoverageRate: number | null = null
  let specificCoverageRate: number | null = null
  let samplingCoverageRate: number | null = null
  if (periodDebitTotal > 0) {
    coverageRate = Math.round((checkedDebitTotal / periodDebitTotal) * 10000) / 100
    specificCoverageRate = Math.round((specificDebitTotal / periodDebitTotal) * 10000) / 100
    samplingCoverageRate = Math.round((samplingDebitTotal / periodDebitTotal) * 10000) / 100
  }
  if (periodCreditTotal > 0) {
    creditCoverageRate = Math.round((checkedCreditTotal / periodCreditTotal) * 10000) / 100
  }

  return {
    sampleCount,
    checkedDebitTotal,
    checkedCreditTotal,
    periodTotal: periodDebitTotal,
    coverageRate,
    creditCoverageRate,
    anomalyCount,
    failCheckCount,
    pendingCount,
    completedCheckCount,
    specificCount,
    specificDebitTotal,
    samplingDebitTotal,
    specificCoverageRate,
    samplingCoverageRate,
  }
}

export function formatCoverageLabel(rate: number | null): string {
  if (rate == null) return 
    ) as any
    if (text != null && String(text).trim().length > 0) count++
  }
  if (count === 0) return 0
  if (count >= expectedFields) return 100
  return Math.min(Math.round((count / expectedFields) * 100), 99)
}

const totalCount = computed(() => allSheets.value.length)
const completedCount = computed(() => allSheets.value.filter(r => calcSheetProgress(r.prefix, 3) >= 100).length)
const progressPercent = computed(() => {
  if (totalCount.value === 0) return 0
  const avg = allSheets.value.reduce((sum, r) => sum + calcSheetProgress(r.prefix, 3), 0) / totalCount.value
  return Math.round(avg)
})

// ─── 底稿架构泳道 ─────────────────────────────────────────────────────────────
const COMPONENT_TYPE_MAP: Record<string, string> = {
  I4A: 
    ) as string
  }

  const computedRows = computed(() => rows.value.map(recalcI4AdjudicationRow))

  const subtotals = computed(() => summarizeI4Adjudication(computedRows.value))

  const excelLead = computed(() => buildI4ExcelLeadSummary(computedRows.value))

  const categorySummary = computed(() =>
    buildI4CategorySummary(computedRows.value, detailRowsRaw.value),
  )

  const crossCheck = computed<I4AdjudicationCrossCheck>(() =>
    buildI4AdjudicationCrossCheck(computedRows.value, detailTotals.value as any),
  )

  const reconciliationStatus = computed<
    ) continue
      total += _getNum(row.originalAmount)
      amortization += _getNum(
        row.auditedAmortization ?? row.currentAmortization ?? row.unadjAmortization ?? row.amortization,
      )
      beginBalance += _getNum(row.auditedOpening ?? row.beginBalance ?? row.unadjOpening)
      increase += _getNum(row.auditedIncrease ?? row.currentIncrease ?? row.unadjIncrease ?? row.increase)
      decrease += _getNum(row.auditedOtherDecrease ?? row.currentDecrease ?? row.unadjOtherDecrease ?? row.decrease)
      endBalance += _getNum(row.auditedEnding ?? row.endBalance ?? row.unadjEnding)
    }

    return { total, amortization, beginBalance, increase, decrease, endBalance }
  })

  // ═══ adjudicationFromDetail: I4-2 合计 → I4-1 审定表（Req 2.2-2.5）═══

  /**
   * 从 I4-2 明细期末余额合计推导 I4-1 审定数参考值：
   * - audited: 期末余额合计（= I4-1 审定表 
    ) continue
    const original = _num(r?.originalAmount)
    originalTotal += original
    const costInc = _num(
      r?.unadjIncrease ?? r?.auditedIncrease ?? r?.currentIncrease ?? r?.costIncrease ?? r?.increase,
    )
    const costDec = _num(
      r?.unadjOtherDecrease ?? r?.auditedOtherDecrease ?? r?.currentDecrease ?? r?.costDecrease ?? r?.decrease,
    )
    const amort = _num(r?.unadjAmortization ?? r?.auditedAmortization ?? r?.currentAmortization)

    if (costInc > 0 || costDec > 0 || amort > 0) {
      usedRoll = true
      debitTotal += costInc
      // 贷方检查口径：其他减少（终止/转出）；摊销单独在 I4-6 勾稽
      creditTotal += costDec
      continue
    }
    const y = _yearOf(_str(r?.occurDate || r?.date))
    if (asOfYear == null || y === asOfYear) {
      debitTotal += original
    }
  }
  return {
    debitTotal: Math.round(debitTotal * 100) / 100,
    creditTotal: Math.round(creditTotal * 100) / 100,
    originalTotal: Math.round(originalTotal * 100) / 100,
    source: usedRoll ? 
    ) {
      totalRje = _round2(totalRje + net)
      if (name) namedRje.push({ name, net })
    } else {
      totalAje = _round2(totalAje + net)
      if (name) namedAje.push({ name, net })
    }
  }

  if ((Math.abs(totalAje) < 0.005 && Math.abs(totalRje) < 0.005) || !rows.length) {
    return { rows, applied: 0, approx: false, totalAje, totalRje, matchedByName: 0 }
  }

  const next = rows.map((r) => ({ ...r, aje: 0, rje: 0, ajeApprox: false }))
  const byName = new Map(next.map((r) => [r.projectName.trim(), r]))
  let matchedByName = 0
  let ajeNamed = 0
  let rjeNamed = 0

  for (const { name, net } of namedAje) {
    const row = byName.get(name)
    if (!row) continue
    row.aje = _round2(row.aje + net)
    row.ajeApprox = false
    matchedByName++
    ajeNamed = _round2(ajeNamed + net)
  }
  for (const { name, net } of namedRje) {
    const row = byName.get(name)
    if (!row) continue
    row.rje = _round2(row.rje + net)
    row.ajeApprox = false
    matchedByName++
    rjeNamed = _round2(rjeNamed + net)
  }

  const ajeRem = _round2(totalAje - ajeNamed)
  const rjeRem = _round2(totalRje - rjeNamed)
  let approx = false
  let applied = matchedByName

  if (Math.abs(ajeRem) > 0.005 || Math.abs(rjeRem) > 0.005) {
    if (next.length === 1) {
      next[0].aje = _round2(next[0].aje + ajeRem)
      next[0].rje = _round2(next[0].rje + rjeRem)
      applied++
    } else {
      const allocated = allocateI4Adjustments(next, ajeRem, rjeRem, true)
      for (let i = 0; i < next.length; i++) {
        next[i].aje = _round2(next[i].aje + allocated[i].aje)
        next[i].rje = _round2(next[i].rje + allocated[i].rje)
        if (allocated[i].ajeApprox) {
          next[i].ajeApprox = true
          approx = true
        }
      }
      applied += next.length
    }
  }

  return {
    rows: next.map(recalcI4AdjudicationRow),
    applied,
    approx,
    totalAje,
    totalRje,
    matchedByName,
  }
}

/** 用 I4-6/I4-7 测算覆盖「本期摊销」；无法按名称匹配时回退按合计比例 */
export function applyAmortFromI46(
  rows: I4AdjudicationRowModel[],
  amortRows: any[],
  totalAmortFallback = 0,
): I4AdjudicationRowModel[] {
  if (!rows.length) return rows
  const byName: Record<string, number> = {}
  let totalFromCalc = 0
  for (const r of amortRows || []) {
    const name = _str(r?.projectName || r?.name || r?.itemName).trim()
    const annual = _num(r?.yearTotal ?? r?.annualTotal ?? r?.calcPeriodAmort)
    const monthly = Array.isArray(r?.monthlyAmorts)
      ? (r.monthlyAmorts as number[]).reduce((s, v) => s + _num(v), 0)
      : Array.isArray(r?.monthlyAmort)
        ? (r.monthlyAmort as number[]).reduce((s, v) => s + _num(v), 0)
        : 0
    const amt = annual || monthly
    if (!name || !(amt > 0)) continue
    byName[name] = _round2((byName[name] || 0) + amt)
    totalFromCalc = _round2(totalFromCalc + amt)
  }

  let matched = 0
  const next = rows.map((r) => {
    const hit = byName[r.projectName.trim()]
    if (hit != null) {
      matched++
      return recalcI4AdjudicationRow({ ...r, amortization: Math.max(0, hit) })
    }
    return r
  })
  if (matched > 0) return next

  const total = totalFromCalc || totalAmortFallback
  if (!(total > 0)) return rows
  const bases = rows.map((r) => Math.abs(r.beginBalance) || Math.abs(r.unadjusted) || 1)
  const sum = calcSubtotal(bases)
  let left = total
  return rows.map((r, i) => {
    const isLast = i === rows.length - 1
    const amt = isLast ? _round2(left) : _round2(total * (bases[i] / sum))
    left = _round2(left - amt)
    return recalcI4AdjudicationRow({ ...r, amortization: Math.max(0, amt) })
  })
}

export function buildI4AdjudicationCrossCheck(
  rows: I4AdjudicationRowModel[],
  detail: {
    beginBalance?: number
    increase?: number
    amortization?: number
    decrease?: number
    endBalance?: number
    total?: number
  },
): I4AdjudicationCrossCheck {
  const sub = summarizeI4Adjudication(rows)
  const detailBegin = _num(detail.beginBalance)
  const detailIncrease = _num(detail.increase)
  const detailAmortization = _num(detail.amortization)
  const detailDecrease = _num(detail.decrease)
  const detailEnd = _num(detail.endBalance)
  const beginDiff = _round2(sub.beginBalance - detailBegin)
  const endDiff = _round2(sub.endBalance - detailEnd)
  const amortDiff = _round2(sub.amortization - detailAmortization)
  const auditedVsDetailDiff = _round2(sub.audited - detailEnd)
  const hasWarning = [beginDiff, endDiff, amortDiff, auditedVsDetailDiff].some((d) => Math.abs(d) > 0.01)
  return {
    detailBegin,
    detailIncrease,
    detailAmortization,
    detailDecrease,
    detailEnd,
    adjBegin: sub.beginBalance,
    adjIncrease: sub.increase,
    adjAmortization: sub.amortization,
    adjDecrease: sub.decrease,
    adjEnd: sub.endBalance,
    adjAudited: sub.audited,
    beginDiff,
    endDiff,
    amortDiff,
    auditedVsDetailDiff,
    hasWarning,
  }
}

/** Excel 式只读：期初未审/调整/审定 · 期末未审/调整/审定 · 变动 */
export function buildI4ExcelLeadSummary(rows: I4AdjudicationRowModel[]): {
  beginUnadj: number
  beginAdj: number
  beginAudited: number
  endUnadj: number
  endAdj: number
  endAudited: number
  varianceAmount: number
  varianceRate: number | null
} {
  const sub = summarizeI4Adjudication(rows)
  const beginAdj = _round2(sub.aje + sub.rje)
  // 期初审定近似：若无单独期初调整列，用 期初未审（滚动期初）对照；期末用未审/调整/审定
  return {
    beginUnadj: sub.beginBalance,
    beginAdj: 0,
    beginAudited: sub.beginBalance,
    endUnadj: sub.unadjusted,
    endAdj: beginAdj,
    endAudited: sub.audited,
    varianceAmount: sub.varianceAmount,
    varianceRate: sub.varianceRate,
  }
}

/** 按 I4-2 expenseType 聚合只读类别汇总（对齐 Excel 类别 A/B/C） */
export function buildI4CategorySummary(
  adjRows: I4AdjudicationRowModel[],
  detailRows: any[] = [],
): Array<{
  category: string
  begin: number
  increase: number
  amortization: number
  decrease: number
  end: number
  audited: number
}> {
  const typeByName = new Map<string, string>()
  for (const d of detailRows || []) {
    const name = _str(d?.projectName || d?.name).trim()
    if (!name || name === 
    ))
    const result = applyAjeFromI43(rows.value, adj)
    rows.value = result.rows
    _persist()
    if (!result.applied && Math.abs(result.totalAje) < 0.005 && Math.abs(result.totalRje) < 0.005) {
      ElMessage.info(
    ),
      summary: description,
      debit: debitAmount,
      credit: creditAmount,
      sourceGroupId: raw.sourceGroupId ? String(raw.sourceGroupId) : undefined,
    }
  }

  function _toPersistShape(list: I4AdjustmentRow[]) {
    return list.map((r, i) => ({
      ...r,
      seq: i + 1,
      debit: r.debitAmount,
      credit: r.creditAmount,
      debitAmount: r.debitAmount,
      creditAmount: r.creditAmount,
      summary: r.description,
      entryType: entryTypeFromCategory(String(r.category)),
    }))
  }

  function load(): void {
    const parsed = _getJson(ROWS_KEY)
    if (Array.isArray(parsed)) {
      rows.value = parsed.map((r, i) => _normalizeRow(r, i))
    } else {
      rows.value = []
    }
    auditNote.value = _getString(NOTE_KEY) || _getString(LEGACY_NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY) || _getString(LEGACY_CONCLUSION_KEY)
  }

  watch(allResponses, () => load(), { immediate: true })

  const debitTotal = computed(() => rows.value.reduce((s, r) => s + r.debitAmount, 0))
  const creditTotal = computed(() => rows.value.reduce((s, r) => s + r.creditAmount, 0))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() => Math.abs(balanceDiff.value) < BALANCE_TOLERANCE)

  const groupBalanceIssues = computed(() => {
    const groups = new Map<string, {
      key: string
      description: string
      entryType: string
      debit: number
      credit: number
      rowCount: number
    }>()
    for (const r of rows.value) {
      const et = r.entryType || entryTypeFromCategory(String(r.category))
      const desc = String(r.description || 
    ),
    )
    const mappedBatch: Array<ReturnType<typeof mapSampledToI4TargetedRow> & {
      isHighValue?: boolean
      summary?: string
    }> = []
    for (const s of samples) {
      const mapped = mapSampledToI4TargetedRow(s, catalog)
      const key = `${mapped.voucherDate}|${mapped.voucherNo}`
      if (key !== 
    ),
    })
  }
  return out
}

export function buildI4AdjudicationConclusionDraft(opts: {
  sampleCount: number
  auditedTotal: number
  tbDiff: number
  hasAje: boolean
  crossWarning: boolean
}): string {
  const parts = [
    `长期待摊费用审定表共 ${opts.sampleCount} 个项目，审定合计 ${opts.auditedTotal.toFixed(2)}。`,
  ]
  if (opts.hasAje) {
    parts.push(
    ),
    })),
    overallConclusion,
  }
}

/** 抽凭引擎 SampledVoucher → I4-5 行（可挂接 I4-2 项目名） */
export function mapSampledToI4TargetedRow(
  s: {
    voucherNo?: string
    voucherDate?: string
    summary?: string | null
    debitAmount?: string | number | null
    creditAmount?: string | number | null
    counterpartAccount?: string | null
    accountName?: string | null
    isHighValue?: boolean
    selectionReason?: string
    abnormal?: boolean
    remark?: string
  },
  catalog?: I42ProjectRef[],
): I4TargetedCheckRow {
  const reason = _str(s.selectionReason)
  const isSpecific = !!(s.isHighValue || reason)
  const rawName = _str(s.accountName)
  const matched = catalog?.length
    ? matchI42ProjectName(
      { projectName: rawName, businessDesc: _str(s.summary), accountName: rawName, counterpartAccount: _str(s.counterpartAccount) },
      catalog,
    )
    : null
  // 账户名常为「长期待摊费用」总账名，优先用 I4-2 匹配结果
  const projectName = matched?.projectName
    || (rawName && !/长期待摊|1801/.test(rawName) ? rawName : 
    ),
  }
}

/**
 * 回填样本若无选取原因，按测试原因/摘要自动标注（高值规则）
 */
export function applyI4SelectionReasonsToSamples(
  samples: Array<{ selectionReason?: string; isHighValue?: boolean; summary?: string | null; remark?: string }>,
  reasons: string[],
): number {
  const preset = buildI4SamplingPresetFromTestReasons(reasons)
  const hints = preset.selectionReasonHints
  if (!hints.length) return 0
  let n = 0
  for (const s of samples) {
    if ((s.selectionReason || 
    ).map((f) => f.title)
  const summaryText = warnTitles.length
    ? `与 I4-4 交叉印证发现待跟进：${warnTitles.join(
    )}\n${result.summaryText}`
}

export function parseI44PolicySnapshot(map: Map<string, any> | null | undefined): I44PolicySnapshot | null {
  if (!map) return null
  const readText = (raw: unknown): string => {
    if (raw == null) return 
    )}。`)
  }
  if (opts.i44CrossSummary) {
    parts.push(opts.i44CrossSummary)
  }
  parts.push(
    ,
        accountCodes: [ACCOUNT_CODE_1801],
        auditedTotal: subtotals.value.audited,
      },
    }))
  }

  /**
   * 保存审定表（普通保存动作，不写 TB）。
   *
   * spec: tb-writeback-explicit-publish-gate Task 13 / Req 1。
   * 此前保存后**自动** PUT 旧端点回写 trial_balance(1801) → 违反 Req 1。现只保存 + emit；
   * TB 回写收敛为用户显式确认动作（publishToTb）。
   */
  async function writeback(force = false): Promise<{ ok: boolean; message?: string }> {
    const gate = validateI4AdjudicationSave({
      rows: computedRows.value,
      tbDiff: tbDifference.value,
      force,
    })
    if (!gate.ok) {
      const msg = gate.blockers.join(
    ,
        is_total: false,
      }
    })

  const totals = summarizeI4Disclosure(state.rows || [])
  dataRows.push({
    label: 
    ,
        reason: `文本命中「${hit}」`,
      }
    }
  }
  return null
}

/** 从 I4-2 费用类型结构推断（装修/租赁改良占比高→零售/物业） */
export function hintIndustryFromExpenseMix(
  rows: Array<{ expenseType?: string; category?: string; originalAmount?: number }>,
): IndustryHint | null {
  if (!rows?.length) return null
  const totals: Record<string, number> = {}
  let sum = 0
  for (const r of rows) {
    const cat = String(r.expenseType || r.category || 
    ,
        },
      )
    }
  }
  return lines
}

/** 合并进既有 I4-3 行：按 description+accountCode 去重（同一说明可保留借贷两行） */
export function mergeI43LinesSkippingExisting(
  existing: any[],
  incoming: I45ToI43Line[],
): { merged: any[]; added: number } {
  const keys = new Set(
    (existing || []).map((r) => {
      const desc = String(r?.description || r?.summary || 
    ,
        期初余额: _num(r.beginBalance),
        本期增加: _num(r.increase),
        本期摊销: _num(r.amortization),
        其他减少: _num(r.otherDecrease),
        期末余额: end,
        is_total: false,
      }
    })

  const totals = summarizeI4Disclosure(state.rows || [])
  dataRows.push({
    label: 
    ,
      isEditable: true,
      fromDetail: true,
      ajeApprox: prev?.ajeApprox ?? false,
    }))
  }
  return out
}

/** 按未审占比分摊 AJE/RJE（多行标 ajeApprox） */
export function allocateI4Adjustments(
  rows: I4AdjudicationRowModel[],
  totalAje: number,
  totalRje: number,
  markApprox = true,
): I4AdjudicationRowModel[] {
  if (!rows.length) return rows
  const base = rows.map((r) => Math.abs(_num(r.unadjusted)) || Math.abs(_num(r.endBalance)))
  const sum = calcSubtotal(base)
  if (!(sum > 0)) {
    return rows.map((r, i) => recalcI4AdjudicationRow({
      ...r,
      aje: i === 0 ? totalAje : 0,
      rje: i === 0 ? totalRje : 0,
      ajeApprox: markApprox && i === 0 && rows.length > 1,
    }))
  }
  let ajeLeft = totalAje
  let rjeLeft = totalRje
  return rows.map((r, i) => {
    const ratio = base[i] / sum
    const isLast = i === rows.length - 1
    const aje = isLast ? _round2(ajeLeft) : _round2(totalAje * ratio)
    const rje = isLast ? _round2(rjeLeft) : _round2(totalRje * ratio)
    ajeLeft = _round2(ajeLeft - aje)
    rjeLeft = _round2(rjeLeft - rje)
    return recalcI4AdjudicationRow({
      ...r,
      aje,
      rje,
      ajeApprox: markApprox && rows.length > 1,
    })
  })
}

/**
 * 从 I4-3 写入 AJE/RJE：
 * 1) 优先按 projectName / description 精确匹配
 * 2) 剩余净额：单行直接计入；多行按未审占比分摊并标 ajeApprox
 */
export function applyAjeFromI43(
  rows: I4AdjudicationRowModel[],
  adjRows: any[],
): {
  rows: I4AdjudicationRowModel[]
  applied: number
  approx: boolean
  totalAje: number
  totalRje: number
  matchedByName: number
} {
  let totalAje = 0
  let totalRje = 0
  const namedAje: Array<{ name: string; net: number }> = []
  const namedRje: Array<{ name: string; net: number }> = []

  for (const line of adjRows || []) {
    const code = String(line?.accountCode || 
    ,
      })
    }
  }
  return out
}

export function summarizeI4ByCategory(rows: I4DetailRow[]): I4CategorySubtotal[] {
  const map = new Map<string, I4CategorySubtotal>()
  for (const row of rows) {
    if (!row.projectName || row.projectName === 
    ,
    accountCode: ACCOUNT_CODE_1801,
    audited: subtotals.value.audited,
    tbAmount: tbUnadjusted.value,
    difference: tbDifference.value,
  }])

  function _persist(): void {
    const save = options?.onSave
    if (!save) return
    save(I4_ADJ_ROWS_KEY, rows.value)
    save(`${ITEM_PREFIX}-rows`, rows.value)
  }

  async function addRow(): Promise<void> {
    try {
      const { value: projectName } = await ElMessageBox.prompt(
        
    ,
    beginBalance: 0,
    currentIncrease: 0,
    currentAmortization: 0,
    currentDecrease: 0,
    endBalance: 0,
    priorBalance: 0,
  }
  Object.assign(row, partial)
  return row
}

/** 回写旧字段别名（I4-1/I4-5/CrossSheet） */
export function syncI4DetailLegacyAliases(row: I4DetailRow): void {
  row.beginBalance = row.auditedOpening
  row.currentIncrease = row.auditedIncrease
  row.currentAmortization = row.auditedAmortization
  row.currentDecrease = row.auditedOtherDecrease
  row.endBalance = row.auditedEnding
  row.priorBalance = row.unadjOpening
}

/**
 * 滚动公式：
 *   未审期末 = 期初+增−摊销−其他
 *   审定* = 未审* + 调整*
 *   审定期末 = 审定期初+增−摊销−其他
 */
export function recalcI4DetailRow(row: I4DetailRow): void {
  // 旧数据仅有 beginBalance 等时，灌入未审列
  if (!row.unadjOpening && row.beginBalance) row.unadjOpening = row.beginBalance
  if (!row.unadjIncrease && row.currentIncrease) row.unadjIncrease = row.currentIncrease
  if (!row.unadjAmortization && row.currentAmortization) row.unadjAmortization = row.currentAmortization
  if (!row.unadjOtherDecrease && row.currentDecrease) row.unadjOtherDecrease = row.currentDecrease
  if (!row.originalAmount && row.unadjIncrease) row.originalAmount = row.unadjIncrease

  row.unadjEnding = _round2(calcAssetEndBalance(
    row.unadjOpening,
    row.unadjIncrease,
    row.unadjAmortization,
    row.unadjOtherDecrease,
  ))

  row.auditedOpening = _round2(row.unadjOpening + row.openingAdj)
  row.auditedIncrease = _round2(row.unadjIncrease + row.ajeIncrease)
  row.auditedAmortization = _round2(row.unadjAmortization + row.ajeAmortization)
  row.auditedOtherDecrease = _round2(row.unadjOtherDecrease + row.ajeOtherDecrease)
  row.auditedEnding = _round2(calcAssetEndBalance(
    row.auditedOpening,
    row.auditedIncrease,
    row.auditedAmortization,
    row.auditedOtherDecrease,
  ))

  row.monthlyAmortization = calcStraightLineAmort(row.originalAmount, row.totalMonths)
  row.remainingMonths = calcRemainingMonths(row.totalMonths, row.elapsedMonths)
  row.amortizationProgress = calcAmortizationRate(row.elapsedMonths, row.totalMonths)

  // 若累计摊销为空且有已摊月数，可提示性回填（不强制覆盖手工累计）
  if (!row.accAmortization && row.monthlyAmortization > 0 && row.elapsedMonths > 0) {
    row.accAmortization = _round2(row.monthlyAmortization * row.elapsedMonths)
  }

  syncI4DetailLegacyAliases(row)
}

export function normalizeI4DetailRow(raw: any): I4DetailRow {
  const row = emptyI4DetailRow({
    rowId: _str(raw?.rowId) || undefined,
    projectName: _str(raw?.projectName || raw?.name),
    category: _str(raw?.category || raw?.类别),
    assetType: _str(raw?.assetType || raw?.资产类型),
    projectCode: _str(raw?.projectCode || raw?.项目编码),
    expenseType: _str(raw?.expenseType || raw?.accountCategory),
    originalAmount: _num(raw?.originalAmount),
    unadjOpening: _num(raw?.unadjOpening ?? raw?.beginBalance ?? raw?.期初),
    unadjIncrease: _num(raw?.unadjIncrease ?? raw?.currentIncrease ?? raw?.increase),
    unadjAmortization: _num(raw?.unadjAmortization ?? raw?.currentAmortization ?? raw?.amortization),
    unadjOtherDecrease: _num(raw?.unadjOtherDecrease ?? raw?.currentDecrease ?? raw?.decrease),
    unadjEnding: _num(raw?.unadjEnding ?? raw?.endBalance),
    openingAdj: _num(raw?.openingAdj),
    ajeIncrease: _num(raw?.ajeIncrease),
    ajeAmortization: _num(raw?.ajeAmortization),
    ajeOtherDecrease: _num(raw?.ajeOtherDecrease),
    auditedOpening: _num(raw?.auditedOpening),
    auditedIncrease: _num(raw?.auditedIncrease),
    auditedAmortization: _num(raw?.auditedAmortization),
    auditedOtherDecrease: _num(raw?.auditedOtherDecrease),
    auditedEnding: _num(raw?.auditedEnding),
    amortizationMethod: _str(raw?.amortizationMethod) || 
    ,
    beginUnadj: L.beginUnadj,
    beginAdj: L.beginAdj,
    beginAudited: L.beginAudited,
    endUnadj: L.endUnadj,
    endAdj: L.endAdj,
    endAudited: L.endAudited,
    varianceAmount: L.varianceAmount,
    varianceRateLabel: formatI4VarianceRate(L.varianceRate),
  }]
})

function getSummaryMethod({ columns }: { columns: any[] }) {
  const sums: string[] = []
  const sub = subtotals.value
  columns.forEach((col, idx) => {
    if (idx === 0) { sums[idx] = 
    ,
    summary.coverageRate,
    summary.periodTotal,
    summary.checkedDebitTotal,
    summary.sampleCount,
    threshold,
  )
}

/** 贷方检查比例偏低 → 对称扩样建议（终止/转出） */
export function buildI4CreditCoverageExpansionAdvice(
  summary: I4TargetedSummary,
  periodCreditTotal: number,
  threshold: number,
  creditRowCount?: number,
): I4CoverageExpansionAdvice {
  let n = creditRowCount
  if (n == null) {
    // 无行数时按借贷金额占比粗估笔数
    const tot = summary.checkedDebitTotal + summary.checkedCreditTotal
    n = summary.checkedCreditTotal > 0 && tot > 0
      ? Math.max(1, Math.round(summary.sampleCount * summary.checkedCreditTotal / tot))
      : (summary.checkedCreditTotal > 0 ? Math.max(1, summary.sampleCount) : 0)
  }
  return _buildSideExpansionAdvice(
    
    ,
    summary.creditCoverageRate,
    periodCreditTotal,
    summary.checkedCreditTotal,
    n,
    threshold,
  )
}

/** 审计说明是否已回应覆盖率偏低（借/贷任一侧需要时均需回应） */
export function isCoverageNoteSatisfied(
  note: string,
  debitAdvice?: I4CoverageExpansionAdvice | null,
  creditAdvice?: I4CoverageExpansionAdvice | null,
): boolean {
  const s = (note || 
    ,
    }
  }

  function fillConclusionDraft() {
    auditConclusion.value = buildI4TargetedConclusionDraft({
      sampleCount: summary.value.sampleCount,
      coverageLabel: coverageLabel.value,
      creditCoverageLabel: creditCoverageLabel.value,
      anomalyCount: summary.value.anomalyCount,
      failCheckCount: summary.value.failCheckCount,
      testReasons: sampleMeta.value.testReasons,
      riskFocus: riskFocus.value,
      expansionAdvice: expansionAdvice.value,
      creditExpansionAdvice: creditExpansionAdvice.value,
      i44CrossSummary: i44Cross.value.empty ? undefined : i44Cross.value.summaryText,
    })
  }

  /**
   * 保存闸门：
   * - 借/贷覆盖率偏低且说明未回应扩样 → 阻断
   * - 特定样本金额与表内不一致 → 警告
   * - I4-4 交叉有 warning 且说明未含交叉印证 → 仅警告（由 UI 提示，不硬阻断以免卡死）
   */
  function canPersist(): { ok: boolean; message: string; level: 
    ,
    })
  } else if (amortRows.length && i41.length) {
    let calcAmort = 0
    for (const r of amortRows) {
      const annual = _num(r.yearTotal ?? r.annualTotal ?? r.calcPeriodAmort)
      if (annual > 0) {
        calcAmort += annual
        continue
      }
      const monthly = Array.isArray(r.monthlyAmorts)
        ? (r.monthlyAmorts as number[]).reduce((s, v) => s + _num(v), 0)
        : Array.isArray(r.monthlyAmort)
          ? (r.monthlyAmort as number[]).reduce((s, v) => s + _num(v), 0)
          : 0
      calcAmort += monthly
    }
    calcAmort = _round2(calcAmort)
    const amortDiff = _round2(adjAmort - calcAmort)
    if (Math.abs(amortDiff) > 0.01 && calcAmort > 0) {
      items.push({
        id: 
    ,
  )

  const hasAjeApprox = computed(() => computedRows.value.some((r) => r.ajeApprox))

  const tbUnadjusted = computed(() => options?.tbUnadjusted1801?.value ?? 0)

  const tbDifference = computed(() => subtotals.value.audited - tbUnadjusted.value)

  const differenceRows = computed<I4DifferenceRow[]>(() => [{
    label: 
    ,
  )

  const reconcileDiff = computed(() => {
    const detail = _readDetailRows()
    if (!detail.length) return null
    const auto = aggregateI4DetailForDisclosure(detail)
    const autoTotal = summarizeI4Disclosure(auto).endBalance
    return Math.round((totals.value.endBalance - autoTotal) * 100) / 100
  })

  /** 附注期末 vs I4-1 审定合计 */
  const reconcileVsAdj = computed(() => {
    const adjItem = allResponses.value.get(
    ,
  }
}

export function buildI4TargetedConclusionDraft(opts: {
  sampleCount: number
  coverageLabel: string
  creditCoverageLabel?: string
  anomalyCount: number
  failCheckCount: number
  testReasons?: string[]
  riskFocus?: I4TargetedRiskFocus
  expansionAdvice?: I4CoverageExpansionAdvice | null
  creditExpansionAdvice?: I4CoverageExpansionAdvice | null
  i44CrossSummary?: string
}): string {
  const reasonText = opts.testReasons?.length
    ? `测试原因：${opts.testReasons.join(
    ,
  })
}

export function summarizeI4Disclosure(rows: I4DisclosureRow[]): I4DisclosureTotals {
  const t: I4DisclosureTotals = {
    beginBalance: 0,
    increase: 0,
    amortization: 0,
    otherDecrease: 0,
    endBalance: 0,
  }
  for (const r of rows) {
    t.beginBalance += _num(r.beginBalance)
    t.increase += _num(r.increase)
    t.amortization += _num(r.amortization)
    t.otherDecrease += _num(r.otherDecrease)
    t.endBalance += _num(r.endBalance)
  }
  t.beginBalance = _round2(t.beginBalance)
  t.increase = _round2(t.increase)
  t.amortization = _round2(t.amortization)
  t.otherDecrease = _round2(t.otherDecrease)
  t.endBalance = _round2(t.endBalance)
  return t
}

/** 从 I4-2 明细行解析披露标签 */
export function resolveI4DisclosureLabel(detail: any): string {
  const expenseType = String(detail?.expenseType ?? 
    ,
] as const

export interface I4DetailSubtotals {
  originalAmount: number
  unadjOpening: number
  unadjIncrease: number
  unadjAmortization: number
  unadjOtherDecrease: number
  unadjEnding: number
  openingAdj: number
  ajeIncrease: number
  ajeAmortization: number
  ajeOtherDecrease: number
  auditedOpening: number
  auditedIncrease: number
  auditedAmortization: number
  auditedOtherDecrease: number
  auditedEnding: number
  // legacy aliases
  beginBalance: number
  currentIncrease: number
  currentAmortization: number
  currentDecrease: number
  endBalance: number
  accAmortization: number
}

export interface I4DetailColumn {
  key: string
  label: string
  width: number
  editable: boolean
  type: 
    ,
] as const

export type I4TargetedCheckMark = (typeof I4_5_CHECK_OPTIONS)[number]

export interface I4TargetedCheckRow {
  rowId: string
  /** 长期待摊费用项目明细 */
  projectName: string
  voucherDate: string
  voucherNo: string
  businessDesc: string
  counterpartAccount: string
  counterpartDetail: string
  debitAmount: number
  creditAmount: number
  supportingDocs: string
  check1: I4TargetedCheckMark | string
  check2: I4TargetedCheckMark | string
  check3: I4TargetedCheckMark | string
  check4: I4TargetedCheckMark | string
  check5: I4TargetedCheckMark | string
  indexRef: string
  isAbnormal: string
  remark: string
  isSpecific: boolean
  selectionReason: string
}

export interface I4TargetedSampleMeta {
  populationCount: number
  /** 测试总体金额（借方口径，用于检查比例） */
  populationAmount: number
  /** 本期贷方发生额（终止摊销/转出等，展示用） */
  populationCreditAmount: number
  populationDesc: string
  populationManual: boolean
  /** Excel「测试原因」多选 */
  testReasons: string[]
  specificSample: string
  specificAmount: number
  samplingPopulationDesc: string
  sampleSize: number
  sampleMethod: string
  sampleProcess: string
  coverageThreshold: number
}

/** 原段落型风险关注（兼容旧 I4-5-major-addition 等分散字段） */
export interface I4TargetedRiskFocus {
  majorAddition: string
  benefitChange: string
  earlyTermination: string
  majorAdditionConclusion: string
  benefitChangeConclusion: string
  earlyTerminationConclusion: string
}

export interface I4TargetedSummary {
  sampleCount: number
  checkedDebitTotal: number
  checkedCreditTotal: number
  periodTotal: number
  coverageRate: number | null
  /** 贷方检查比例（样本贷方 ÷ 本期贷方发生额） */
  creditCoverageRate: number | null
  anomalyCount: number
  failCheckCount: number
  pendingCount: number
  completedCheckCount: number
  specificCount: number
  specificDebitTotal: number
  samplingDebitTotal: number
  specificCoverageRate: number | null
  samplingCoverageRate: number | null
}

export interface I4PeriodMovement {
  /** 本期借方代理：当期新增长期待摊费用 */
  debitTotal: number
  /** 本期贷方：本期减少（提前终止/转出）合计 */
  creditTotal: number
  /** 原始金额合计（存在性测试总体备选） */
  originalTotal: number
  source: string
}

export function emptyI4TargetedRow(partial?: Partial<I4TargetedCheckRow>): I4TargetedCheckRow {
  return {
    rowId: partial?.rowId || `i45-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    projectName: 
    , () => {})

const {
  rows,
  auditNote,
  auditConclusion,
  significantMatters,
  subtotals,
  excelLead,
  categorySummary,
  crossCheck,
  reconciliationStatus,
  hasAjeApprox,
  tbDifference,
  differenceRows,
  addRow,
  removeRow,
  updateCell,
  seedFromI42,
  syncFromI43,
  syncAmortFromI46,
  applyTbData,
  applyPriorFromTb,
  fillConclusionDraft,
  applyConclusionTemplate,
  writeback,
  publishToTb,
  publishing,
  saveNote,
  saveConclusion,
  saveSignificantMatters,
} = useI4Adjudication(
  toRef(props, 
    , () => {})
const isReadonly = computed(() => Boolean(props.isReadonly))
const projectId = computed(() => props.projectId)

const {
  rows,
  activeSection,
  activeColumns,
  subtotals,
  rollWarnings,
  categorySubtotals,
  sections,
  setActiveRow,
  updateCell,
  addRow,
  removeRow,
} = useI4Detail(
  toRef(props, 
    , CONCLUSION_KEY, val)
}

function handleFillDraft(): void {
  auditConclusion.value = buildI4DetailConclusionDraft({
    rowCount: rows.value.length,
    auditedEnding: subtotals.value.auditedEnding,
    unadjEnding: subtotals.value.unadjEnding,
    warningCount: rollWarnings.value.length,
    categoryCount: categorySubtotals.value.length,
  })
  saveAuditConclusion(auditConclusion.value)
  ElMessage.success(
    , itemId, value),
  asOfYear,
})

const samplingConfigPatch = computed(() => {
  const p = samplingPreset.value
  return {
    samplingMethod: p.defaultMethod,
    summaryKeyword: p.summaryKeyword,
    directionFilter: p.directionFilter,
    ...(p.materialityThreshold ? { materialityThreshold: p.materialityThreshold } : {}),
  }
})

/** I4-4 有估计变更且未勾选「受益期变更」 */
const policyChangeNeedsSample = computed(() => {
  const snap = parseI44PolicySnapshot(props.allResponses)
  const changed = (snap?.policyParams || []).some((p: any) => p.hasChange === 
    , { minimumFractionDigits: 2 })}（${summary.value.specificCount} 笔）`,
    }
  }

  function fillFromSampledVouchers(samples: any[]): number {
    if (!Array.isArray(samples) || !samples.length) return 0
    const catalog = i42ProjectCatalog.value
    const existing = new Set(
      rows.value.map((r) => `${r.voucherDate}|${r.voucherNo}`).filter((k) => k !== 
    >
        <summary>编制提示</summary>
        <ul>
          <li>长期待摊费用（1801）资产借方：期末 = 期初 + 增加 − 摊销 − 减少；审定回写 TB(1801)</li>
          <li>摊销测算 I4-6（直线法）/ I4-7（工作量法）二选一；两表同时有数据时以 I4-6 为准</li>
          <li>推荐工作流：I4A → I4-2 明细 → I4-1 审定带入 → I4-3 调整 → I4-4 政策 → I4-5 抽凭 → I4-6/7 测算 → 附注</li>
          <li>I4-5 抽凭覆盖率达门槛，异常与 I4-4 政策检查交叉；各表填妥
    >
      <summary>操作提示</summary>
      <ul>
        <li>区段：未审滚动 → 调整与审定 → 摊销信息 → 基础信息；行跨区段同步。</li>
        <li>公式：未审/审定期末 = 期初+增加−摊销−其他减少；审定* = 未审* + 对应调整。</li>
        <li>合计勾稽审定表 I4-1；本期摊销可与 I4-6/I4-7 测算交叉；抽凭总体取自本表本期增加（I4-5）。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang=
    >
      <summary>编制提示（对齐 Excel I4-5，已补强模板缺口）</summary>
      <ol>
        <li>先勾选测试原因并填第二节总体，再抽样本填入第三节；检查比例=样本借方÷本期借方（总体为 0 显示 N/A，避免 #DIV/0!）。</li>
        <li>无新增时本期借方可为 0，可改用「带入原始金额合计」作存在性测试总体，并在说明中解释。</li>
        <li>核对 1~5 对应测试内容说明（Excel 第 5 项原为空，已补全为与 I4-2 入账/受益期一致）；选「×」时按核对项自动建议异常类型。</li>
        <li>表内「选取原因」标记特定样本（100%检查层），可用「从表内特定样本同步」回写第二节金额；分层覆盖率见合计区。</li>
        <li>检查比例偏低时系统给出强制扩样建议（借方/贷方对称）；未扩样须写入说明，否则无法保存。</li>
        <li>第二节「特定样本金额」与表内特定借方按容差校验，不一致可一键同步。</li>
        <li>勾选测试原因后，抽凭引擎预填方法/摘要关键词/方向（大额→MUS、提前终止→贷方等）。</li>
        <li>自动读取 I4-4 CAS 五维结论与变更类别，与抽凭核对3/5、测试原因、专项风险交叉印证。</li>
        <li>抽凭回填时按摘要模糊挂接 I4-2 项目名；也可点「挂接 I4-2 项目名」补全空行。</li>
        <li>资本化/跨期类核对× 可「推送至 I4-3」生成费用化或跨期 AJE（按说明去重）。</li>
        <li>与 I4-4 有交叉缺口且未写说明时，保存会二次确认（软闸门）。</li>
      </ol>
    </details>

    <el-dialog
      v-model=
  I5: 66 个
    

// ─── Types ───────────────────────────────────────────────────────────────────

/** 单层滚动金额块（未审 → 调整 → 审定） */
export interface I5RollAmounts {
  unadjOpening: number
  unadjIncrease: number
  unadjDecrease: number
  /** 公式：期初+增加−减少 */
  unadjEnding: number
  /** 期初调整·账项 F */
  openingAje: number
  /** 期初调整·重分类 G */
  openingRje: number
  /** 账项调整·本期增加 H */
  ajeIncrease: number
  /** 账项调整·本期减少 I */
  ajeDecrease: number
  /** 重分类调整·本期增加 J */
  rjeIncrease: number
  /** 重分类调整·本期减少 K */
  rjeDecrease: number
  /** 公式 L=B+F+G */
  auditedOpening: number
  /** 公式 M=C+H+J */
  auditedIncrease: number
  /** 公式 N=D+I+K */
  auditedDecrease: number
  /** 公式 O=L+M−N */
  auditedEnding: number
}

export interface I5DetailRow {
  rowId: string
  /** 项目名称（Excel A 列） */
  projectName: string
  /** @deprecated 别名 → projectName */
  name: string
  /** 模板内置行（可改名但默认骨架） */
  isBuiltin: boolean
  /** 跨底稿索引提示，如 D7 / M12 / G2-13 */
  indexRef: string
  remark: string

  gross: I5RollAmounts
  impairment: I5RollAmounts

  // ── 旧字段别名（回写净值审定，供下游）──
  /** @deprecated → net.auditedOpening */
  beginBalance: number
  /** @deprecated → net.auditedIncrease */
  increase: number
  /** @deprecated → net.auditedDecrease */
  decrease: number
  /** @deprecated → net.auditedEnding */
  endBalance: number
  /** @deprecated → net.unadjEnding */
  unadjusted: number
  category: string
  incurredDate: string
  maturityDate: string
  /** 剩余月数（可选；不填则按 maturityDate 推算） */
  remainingMonths: number | null
  summary: string
  contractNo: string
  counterparty: string
  indexNo: string
  increaseReason: string
  decreaseReason: string
  originalAmount: number
  accumulatedAmount: number
  netValue: number
  voucherRef: string
  voucherDate: string
  checkMethod: string
  checkResult: string
  conclusion: string
  isAbnormal: boolean
  reviewMark: string
  status: string
}

export type I5DetailSection = 0 | 1 | 2 | 3

export const I5_DETAIL_SECTION_LABELS = [
  
    

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** I5-2 明细行原始 JSON（新：gross/impairment；旧：扁平 beginBalance…） */
export interface I5DetailRowRaw {
  rowId?: string
  projectName?: string
  name?: string
  category?: string
  layer?: string
  beginBalance?: number
  increase?: number
  decrease?: number
  endBalance?: number
  unadjusted?: number
  gross?: { auditedOpening?: number; auditedIncrease?: number; auditedDecrease?: number; auditedEnding?: number }
  impairment?: { auditedEnding?: number }
  remark?: string
}

/** I5-3 调整分录行原始 JSON 结构（对齐 Excel 10 列 + 明细项目） */
export interface I5AdjustmentRowRaw {
  rowId?: string
  description?: string        // 调整事项说明
  category?: string           // 账项调整 / 报表调整 / 其他
  entryType?: string          // AJE / RJE
  reportItem?: string         // 报表项目
  accountCode?: string        // 科目代码
  accountName?: string        // 科目名称
  noteItem?: string           // 附注项目
  projectName?: string        // 明细项目（精确匹配 I5-1/I5-2）
  summary?: string            // 摘要（兼容旧字段）
  debitAmount?: number        // 借方
  creditAmount?: number       // 贷方
  debit?: number              // 兼容旧字段
  credit?: number             // 兼容旧字段
  indexRef?: string           // 索引
  remark?: string
}

// ─── Return Types ────────────────────────────────────────────────────────────

/** I5-2 明细合计 → I5-1 审定表交叉验证 */
export interface I5DetailTotals {
  total: number               // 期末余额合计（主合计）
  beginBalance: number        // 期初余额合计
  increase: number            // 本期增加合计
  decrease: number            // 本期减少合计
  endBalance: number          // 期末余额合计
}

/** 审定数从明细聚合 → I5-1 审定表 */
export interface I5AdjudicationFromDetail {
  audited: number             // 期末余额合计（= I5-1 审定表审定数参考来源）
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 安全解析 JSON 数组字符串，失败回退空数组
 */
function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/**
 * 安全提取数值，NaN/null/undefined → 0
 */
function _getNum(val: any): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI5CrossSheet(allResponses: Ref<Map<string, any>>): {
  detailTotals: ComputedRef<I5DetailTotals>
  adjudicationFromDetail: ComputedRef<{ audited: number }>
  detailRowsRaw: ComputedRef<any[]>
  adjustmentRowsRaw: ComputedRef<I5AdjustmentRowRaw[]>
} {
  const detailRowsRaw = computed<any[]>(() => {
    const resp = allResponses.value.get(
    

export interface I5DisclosureRow {
  rowId: string
  item: string
  /** 期末账面余额 */
  endGross: number
  /** 期末减值准备 */
  endImpairment: number
  /** 期末账面价值（公式） */
  endBookValue: number
  /** 上年年末/年初 账面余额 */
  priorGross: number
  /** 上年年末减值准备 */
  priorImpairment: number
  /** 上年年末/年初 账面价值（公式；国企即年初余额） */
  priorBookValue: number
  isAutoFilled: boolean
  remark: string
}

export interface I5DisclosureTotals {
  endGross: number
  endImpairment: number
  endBookValue: number
  priorGross: number
  priorImpairment: number
  priorBookValue: number
}

export const I5_DISC_KEYS = {
  listedRows: 
    

export {
  type I5TargetedCheckRow,
  type I5TargetedSampleMeta,
  type I5TargetedRiskFocus,
  type I5TargetedSummary,
  type I5TargetedAdjDraft,
  type I5SpecificAmountCheck,
  type I52ProjectRef,
  emptyI5TargetedRow,
  I5_4_DEFAULT_COVERAGE_THRESHOLD,
  I5_4_TEST_CONTENT,
  I5_4_TEST_REASONS,
  I5_4_SAMPLE_METHODS,
  I5_4_CHECK_OPTIONS,
  I5_4_ABNORMAL_OPTIONS,
  I5_4_OBJECTIVES,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  isAbnormalFlag,
  hasFailedCheck,
  suggestAbnormalFromFailedChecks,
  syncSpecificAmountFromRows,
  checkI5SpecificAmountConsistency,
  riskFocusIncomplete,
  buildI5TargetedConclusionDraft,
  buildI5TargetedAdjDrafts,
  buildI53LinesFromTargetedDrafts,
  mergeI53LinesSkippingExisting,
  mapSampledToI5TargetedRow,
} from 
    
  reportItem: string
  accountCode: string
  accountName: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
  /** 明细项目名（供 I5-1 / I5-2 精确匹配） */
  projectName: string
  summary?: string
  debit?: number
  credit?: number
  sourceGroupId?: string
}

const ROWS_KEY = 
    
  return `${rate.toFixed(2)}%`
}

export function formatLayeredCoverageLabel(summary: I5TargetedSummary): string {
  if (summary.coverageRate == null) return 
    
  return `借方 ${summary.coverageRate.toFixed(2)}%（特定 ${sp}% + 抽样 ${sa}%）`
}

/** Excel 表尾三行：合计 / 本期发生额 / 检查比例（避免 #DIV/0!） */
export interface I5CoverageFooter {
  checkedDebitTotal: number
  checkedCreditTotal: number
  periodDebitTotal: number
  periodCreditTotal: number
  debitCoverageLabel: string
  creditCoverageLabel: string
  layeredCoverageLabel: string
}

export function buildI5CoverageFooter(
  summary: I5TargetedSummary,
  periodCreditTotal = 0,
): I5CoverageFooter {
  return {
    checkedDebitTotal: summary.checkedDebitTotal,
    checkedCreditTotal: summary.checkedCreditTotal,
    periodDebitTotal: summary.periodTotal,
    periodCreditTotal,
    debitCoverageLabel: formatCoverageLabel(summary.coverageRate),
    creditCoverageLabel: formatCoverageLabel(summary.creditCoverageRate),
    layeredCoverageLabel: formatLayeredCoverageLabel(summary),
  }
}

/** 核对× → 建议「是否异常」取值（便于编制人快速标注） */
export function suggestAbnormalFromFailedChecks(row: I5TargetedCheckRow): string {
  if (row.check3 === 
    
  return emptyI5TargetedRow({
    voucherDate: _str(s.voucherDate),
    voucherNo: _str(s.voucherNo),
    businessDesc: _str(s.summary),
    counterpartAccount: _str(s.counterpartAccount),
    projectName: matched || _str(s.accountName),
    debitAmount: _num(s.debitAmount),
    creditAmount: _num(s.creditAmount),
    isSpecific,
    selectionReason: reason || (s.isHighValue ? 
    
import {
  type I5AdjudicationRowModel,
  type I5AdjudicationCrossCheck,
  emptyI5AdjudicationRow,
  normalizeI5AdjudicationRow,
  summarizeI5Adjudication,
  seedI5AdjudicationFromDetail,
  applyAjeFromI53,
  buildI5AdjudicationCrossCheck,
  buildI5ExcelLeadSummary,
  buildI5LeadMatrixRows,
  buildI5ThreeLayerLeadFromDetail,
  appendI5TbReconciliationToLead,
  buildI5VarianceNoteDraft,
  buildI5AdjudicationConclusionDraft,
  validateI5AdjudicationSave,
  recalcI5AdjudicationRow,
  formatI5VarianceRate,
  I5_ADJ_ROWS_KEY,
  I5_ADJ_NOTE_KEY,
  I5_ADJ_CONCLUSION_KEY,
  I5_ADJ_MATTERS_KEY,
  I5_ADJ_OWNERSHIP_KEY,
  I5_DEFAULT_CATEGORIES,
  I5_CONCLUSION_OPTIONS,
} from 
    
import {
  type I5TargetedCheckRow,
  type I5TargetedSampleMeta,
  type I5TargetedRiskFocus,
  type I5TargetedSummary,
  emptyI5TargetedRow,
  emptyI5TargetedSampleMeta,
  emptyI5TargetedRiskFocus,
  normalizeI5TargetedRow,
  normalizeI5TargetedSampleMeta,
  normalizeI5TargetedRiskFocus,
  summarizeI5Targeted,
  extractI5PeriodMovement,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  buildI5CoverageFooter,
  buildI5TargetedConclusionDraft,
  buildI5TargetedAdjDrafts,
  buildI53LinesFromTargetedDrafts,
  mergeI53LinesSkippingExisting,
  mapSampledToI5TargetedRow,
  suggestAbnormalFromFailedChecks,
  syncSpecificAmountFromRows,
  checkI5SpecificAmountConsistency,
  extractI52ProjectCatalog,
  riskFocusIncomplete,
  isAbnormalFlag,
  hasFailedCheck,
  I5_4_DEFAULT_COVERAGE_THRESHOLD,
} from 
     && d.amount > 0.005),
  )

  /** 第二节特定样本金额 vs 表内特定借方 */
  const specificAmountCheck = computed(() =>
    checkI5SpecificAmountConsistency(
      sampleMeta.value.specificAmount,
      summary.value.specificDebitTotal,
    ),
  )

  /** I5-2 项目名目录（抽凭挂接 / 下拉） */
  const i52ProjectCatalog = computed(() => extractI52ProjectCatalog(getMap().get(I52_ROWS)))
  const i52ProjectNames = computed(() => i52ProjectCatalog.value.map((p) => p.projectName))

  /** 有抽凭样本但专项风险结论全空 */
  const riskFocusGap = computed(() =>
    riskFocusIncomplete(riskFocus.value, summary.value.sampleCount),
  )

  function addRow(partial?: Partial<I5TargetedCheckRow>) {
    rows.value.push(emptyI5TargetedRow(partial))
  }

  function removeRow(rowId: string) {
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
  }

  function updateRow(rowId: string, field: keyof I5TargetedCheckRow, value: string | number | boolean) {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    if (field === 
     && remark) {
      try {
        const p = JSON.parse(remark)
        return Array.isArray(p) ? p : []
      } catch { return [] }
    }
    if (Array.isArray(remark)) return remark
  }
  return []
}

/**
 * 从 I5-2 明细推算本期发生额：
 * 优先 increase（本期增加=借方）/ decrease（本期减少=贷方）；
 * 无滚动字段时回退按 incurredDate 年份代理 originalAmount。
 */
export function extractI5PeriodMovement(raw: unknown, asOfYear?: number): I5PeriodMovement {
  const rows = _parseI52Rows(raw)
  let debitTotal = 0
  let creditTotal = 0
  let originalTotal = 0
  let usedRoll = false
  for (const r of rows) {
    if ((r?.projectName || r?.name) === 
     open>
      <summary>编制提示（对齐 Excel 其他非流动资产调整分录汇总表 I5-3）</summary>
      <div class=
     open>
      <summary>编制说明</summary>
      <ol>
        <li>本表对齐源底稿「附注披露（上市公司）」：分类余额对比（含减值），非增减变动矩阵。</li>
        <li>数据优先自 I5-2 按项目/分类聚合；手工修改后取消「自动」标记。</li>
        <li>同步附注时写入 note_template §五、31「其他非流动资产」子表（期末/上年年末=账面价值）。</li>
        <li>合计应与 I5-1 审定合计及报表「其他非流动资产」勾稽。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang=
     open>
      <summary>编制说明</summary>
      <ol>
        <li>本表对齐源底稿「附注披露（国有企业）」：项目 / 期末余额 / 年初余额。</li>
        <li>数据优先自 I5-2 聚合；同步附注写入 note_template §八、32。</li>
        <li>合计应与 I5-1 审定合计勾稽一致。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang=
     open>
      <summary>编制说明（对齐 Excel I5-1）</summary>
      <ol>
        <li>其他非流动资产核算预计无法在一年（或一个正常营业周期）内变现或耗用的非流动资产，如预付土地出让金、预付工程/房屋设备款、合同资产（非流动部分）等。</li>
        <li>资产类借方科目 1911：期末＝期初＋增加−减少（含到期转出/重分类至流动资产等）。</li>
        <li>审定矩阵分列「账项调整」(AJE) 与「重分类调整」(RJE)；审定数＝未审＋账项＋重分类。</li>
        <li>明细合计(I5-2)、调整分录(I5-3)应与本表勾稽；TB 差异须为 0 后方可回写。</li>
        <li>变动率＝（本期审定−上期审定）/|上期审定|；上期为 0 时显示 N/A（勿出现 #DIV/0!）。变动率超过 30% 的项目须在审计说明中解释原因。</li>
        <li>权属、抵押情况应单独说明；审计结论可选用 A/B/C 模板。</li>
        <li>「带入调整」：从集中登记按科目 1911 拉取调整分录，逐笔分配到各项目的 AJE/RJE，带入后审定数自动更新并联动附注。</li>
      </ol>
    </details>

    <AdjudicationBringInDialog
      v-model=
     }
  })

  const summary: ComputedRef<I5TargetedSummary> = computed(() =>
    summarizeI5Targeted(
      rows.value,
      sampleMeta.value.populationAmount,
      sampleMeta.value.populationCreditAmount,
    ),
  )

  const coverageLow = computed(() =>
    summary.value.coverageRate != null
    && summary.value.coverageRate < sampleMeta.value.coverageThreshold
    && summary.value.periodTotal > 0,
  )

  const coverageLabel = computed(() => formatLayeredCoverageLabel(summary.value))
  const creditCoverageLabel = computed(() => formatCoverageLabel(summary.value.creditCoverageRate))

  const coverageFooter = computed(() =>
    buildI5CoverageFooter(summary.value, sampleMeta.value.populationCreditAmount),
  )

  const coverageTagType = computed(() => {
    if (summary.value.coverageRate == null) return 
     },
])

// ─── 进度计算 ─────────────────────────────────────────────────────────────────
const totalCount = computed(() => allSheets.value.length)
const completedCount = computed(() => allSheets.value.filter(r => calcSheetProgress(r.prefix, 3) >= 100).length)
const progressPercent = computed(() => {
  if (totalCount.value === 0) return 0
  const avg = allSheets.value.reduce((sum, r) => sum + calcSheetProgress(r.prefix, 3), 0) / totalCount.value
  return Math.round(avg)
})

// ─── 底稿架构泳道（GtBArchitectureTree 数据源） ───────────────────────────────
const COMPONENT_TYPE_MAP: Record<string, string> = {
  I5A: 
    )

    const classificationItems = _itemsText(LEGACY_CLASSIFICATION_ITEMS)
    const maturityItems = _itemsText(LEGACY_MATURITY_ITEMS)
    const recoverabilityItems = _itemsText(LEGACY_RECOVERABILITY_ITEMS)
    const classificationText = _readText(map.get(LEGACY_CLASSIFICATION_TEXT))
    const maturityText = _readText(map.get(LEGACY_MATURITY_TEXT))
    const recoverabilityText = _readText(map.get(LEGACY_RECOVERABILITY_TEXT))

    if (!classificationItems && !maturityItems && !recoverabilityItems
      && !classificationText && !maturityText && !recoverabilityText) {
      return null
    }
    return {
      classificationItems,
      maturityItems,
      recoverabilityItems,
      classificationText,
      maturityText,
      recoverabilityText,
    }
  }

  watch(() => {
    const m = getMap()
    return [
      m.get(STORAGE_ROWS),
      m.get(STORAGE_SAMPLE),
      m.get(STORAGE_RISK),
      m.get(STORAGE_NOTE),
      m.get(STORAGE_CONCLUSION),
      m.get(I52_ROWS),
      m.get(LEGACY_OVERALL_CONCLUSION),
      m.get(LEGACY_AUDIT_CONCLUSION),
      ...LEGACY_CHECK_ITEM_KEYS.map((k) => m.get(k)),
    ]
  }, () => load(), { immediate: true, deep: false })

  const linkedPeriod: ComputedRef<{
    debitTotal: number
    creditTotal: number
    originalTotal: number
    source: string
  }> = computed(() => {
    const mv = extractI5PeriodMovement(getMap().get(I52_ROWS), getYear())
    return mv.debitTotal > 0 || mv.creditTotal > 0 || mv.originalTotal > 0
      ? mv
      : { debitTotal: 0, creditTotal: 0, originalTotal: 0, source: 
    )

  const totals = computed(() => summarizeI5Disclosure(rows.value))

  const reconcileDiff = computed(() => {
    const detail = _readDetailRows()
    if (!detail.length) return null
    const auto = aggregateI5DetailForDisclosure(detail)
    const autoTotal = summarizeI5Disclosure(auto).endBookValue
    return Math.round((totals.value.endBookValue - autoTotal) * 100) / 100
  })

  /** 附注期末账面价值 vs I5-1 审定合计 */
  const reconcileVsAdj = computed(() => {
    const adjItem = allResponses.value.get(
    )

  const {
    detailTotals,
    detailRowsRaw,
    adjustmentRowsRaw,
  } = useI5CrossSheet(allResponses as Ref<Map<string, any>>)

  function _loadRows(): void {
    const data = _getJson(I5_ADJ_ROWS_KEY) ?? _getJson(`${ITEM_PREFIX}-rows`)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(normalizeI5AdjudicationRow)
    } else {
      rows.value = DEFAULT_CATEGORIES.map((cat) => emptyI5AdjudicationRow({ projectName: cat }))
    }
    auditNote.value = _getString(I5_ADJ_NOTE_KEY) || _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(I5_ADJ_CONCLUSION_KEY) || _getString(`${ITEM_PREFIX}-audit-conclusion`)
    significantMatters.value = _getString(I5_ADJ_MATTERS_KEY) || _getString(`${ITEM_PREFIX}-significant-matters`)
    ownershipPledge.value = _getString(I5_ADJ_OWNERSHIP_KEY) || _getString(`${ITEM_PREFIX}-ownership-pledge`)
  }

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    if (typeof raw !== 
    )

  function load() {
    const map = getMap()
    rows.value = _safeParseArray(map.get(STORAGE_ROWS)).map(normalizeI5TargetedRow)

    sampleMeta.value = normalizeI5TargetedSampleMeta(_parseObject(map.get(STORAGE_SAMPLE)))

    const riskRaw = _parseObject(map.get(STORAGE_RISK)) || _legacyRiskFocusRaw(map)
    riskFocus.value = normalizeI5TargetedRiskFocus(riskRaw)

    auditNote.value = _readText(map.get(STORAGE_NOTE))
    auditConclusion.value = _readText(map.get(STORAGE_CONCLUSION))
      || _readText(map.get(LEGACY_OVERALL_CONCLUSION))
      || _readText(map.get(LEGACY_AUDIT_CONCLUSION))

    if (!sampleMeta.value.populationManual) {
      const mv = extractI5PeriodMovement(map.get(I52_ROWS), getYear())
      if (mv.debitTotal > 0) sampleMeta.value.populationAmount = mv.debitTotal
      if (mv.creditTotal > 0) sampleMeta.value.populationCreditAmount = mv.creditTotal
    }
  }

  /** 旧段落型分散 key（9 个 radio + 3 个 textarea 结论）拼装为 riskFocus 迁移对象 */
  function _legacyRiskFocusRaw(map: Map<string, any>): any {
    const _itemsText = (keys: readonly string[]) => keys
      .map((k) => {
        const v = _readText(map.get(k))
        return v && v !== 
    )

const {
  rows,
  sampleMeta,
  riskFocus,
  auditNote,
  auditConclusion,
  summary,
  coverageLow,
  coverageLabel,
  creditCoverageLabel,
  coverageFooter,
  coverageTagType,
  linkedPeriod,
  adjDrafts,
  pushableAdjDrafts,
  specificAmountCheck,
  i52ProjectNames,
  riskFocusGap,
  addRow,
  removeRow,
  updateRow,
  fillFromSampledVouchers,
  setPopulationAmount,
  syncPopulationFromI52,
  syncSpecificAmount,
  appendAdjDraftsToNote,
  pushAdjDraftsToI53,
  fillConclusionDraft,
  persistAll,
  saveNote,
  saveConclusion,
  saveRiskFocus,
} = useI5TargetedCheck(allResponsesRef, {
  onSave: (itemId, value) => emit(
    )
        })
        rows.value = list
      } else {
        rows.value = createI5BuiltinRows()
      }
    } catch {
      rows.value = createI5BuiltinRows()
    }
  }

  function _persist(): void {
    for (const r of rows.value) recalcI5DetailRow(r)
    options?.onSave?.(ITEM_ID_ROWS, JSON.stringify(rows.value))
  }

  const subtotals: ComputedRef<I5DetailSubtotals> = computed(() => {
    const list = rows.value
    const grossUnadjEnding = calcSubtotal(list.map((r) => r.gross.unadjEnding))
    const grossAuditedEnding = calcSubtotal(list.map((r) => r.gross.auditedEnding))
    const impAuditedEnding = calcSubtotal(list.map((r) => r.impairment.auditedEnding))
    const nets = list.map(getI5NetRoll)
    const netUnadjEnding = calcSubtotal(nets.map((n) => n.unadjEnding))
    const netAuditedOpening = calcSubtotal(nets.map((n) => n.auditedOpening))
    const netAuditedIncrease = calcSubtotal(nets.map((n) => n.auditedIncrease))
    const netAuditedDecrease = calcSubtotal(nets.map((n) => n.auditedDecrease))
    const netAuditedEnding = calcSubtotal(nets.map((n) => n.auditedEnding))
    return {
      grossUnadjEnding,
      grossAuditedEnding,
      impAuditedEnding,
      netUnadjEnding,
      netAuditedOpening,
      netAuditedIncrease,
      netAuditedDecrease,
      netAuditedEnding,
      beginBalance: netAuditedOpening,
      increase: netAuditedIncrease,
      decrease: netAuditedDecrease,
      endBalance: netAuditedEnding,
      originalAmount: grossAuditedEnding,
      accumulatedAmount: impAuditedEnding,
      netValue: netAuditedEnding,
    }
  })

  const rollWarnings = computed(() => collectI5RollWarnings(rows.value))

  const sections = [
    { key: 0 as I5DetailSection, label: 
    )
      ElMessage.error(msg)
      return { ok: false, message: msg }
    }
    if (gate.warnings.length) ElMessage.warning(gate.warnings[0])

    _persist()
    const auditedTotal = subtotals.value.audited
    options?.onSave?.(`${ITEM_PREFIX}-audited-total`, auditedTotal)

    _emitAdjudicated()
    return { ok: true }
  }

  // ─── 显式发布到试算表（显式确认门，复刻 D2/D4-1 范式） ────────────────────────

  /**
   * 确认发布审定数到试算表（科目 1911 其他非流动资产）。
   *
   * spec: tb-writeback-explicit-publish-gate Task 13 / Req 2。
   * 二次确认（中文）→ 保存明细 → `POST /workpapers/{wpId}/audit-determination/publish-to-tb`
   * （审定表 sheet 名 I5-1 + writeback_rows 预算行 1911 balance）。用户取消 → 无副作用。
   */
  async function publishToTb(): Promise<void> {
    if (publishing.value) return

    try {
      await ElMessageBox.confirm(
        
    )
      return
    }
    ElMessage.success(
      result.approx
        ? `已同步 AJE ${result.totalAje} / RJE ${result.totalRje}（含近似分摊，请复核）`
        : `已同步 AJE ${result.totalAje} / RJE ${result.totalRje}（精确匹配 ${result.matchedByName}）`,
    )
  }

  function applyTbData(tbUnadjustedTotal?: number): void {
    const total = tbUnadjustedTotal ?? tbUnadjusted.value
    if (!rows.value.length) return
    if (rows.value.length === 1) {
      rows.value[0] = recalcI5AdjudicationRow({ ...rows.value[0], unadjusted: total })
    } else {
      const base = rows.value.map((r) => Math.abs(r.beginBalance) || Math.abs(r.endBalance) || 0)
      const sum = base.reduce((a, b) => a + b, 0)
      if (sum > 0) {
        let left = total
        rows.value = rows.value.map((r, i) => {
          const isLast = i === rows.value.length - 1
          const amt = isLast ? Math.round(left * 100) / 100 : Math.round((total * base[i] / sum) * 100) / 100
          left = Math.round((left - amt) * 100) / 100
          return recalcI5AdjudicationRow({ ...r, unadjusted: amt })
        })
      } else {
        rows.value[0] = recalcI5AdjudicationRow({ ...rows.value[0], unadjusted: total })
      }
    }
    _persist()
    ElMessage.success(
    )
      return
    }
    if (rows.value.length === 1) {
      rows.value[0] = recalcI5AdjudicationRow({ ...rows.value[0], priorAudited: total })
    } else {
      const base = rows.value.map((r) => Math.abs(r.beginBalance) || Math.abs(r.unadjusted) || 0)
      const sum = base.reduce((a, b) => a + b, 0)
      if (sum > 0) {
        let left = total
        rows.value = rows.value.map((r, i) => {
          const isLast = i === rows.value.length - 1
          const amt = isLast ? Math.round(left * 100) / 100 : Math.round((total * base[i] / sum) * 100) / 100
          left = Math.round((left - amt) * 100) / 100
          return recalcI5AdjudicationRow({ ...r, priorAudited: amt })
        })
      } else {
        rows.value[0] = recalcI5AdjudicationRow({ ...rows.value[0], priorAudited: total })
      }
    }
    _persist()
    ElMessage.success(
    )
    const known = I5_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === accountCode)
    const debitAmount = parseAmt(raw.debitAmount ?? raw.debit)
    const creditAmount = parseAmt(raw.creditAmount ?? raw.credit)
    const description = String(raw.description ?? raw.summary ?? 
    )
    if (hasNested) {
      const base = buildI5ThreeLayerLeadFromDetail(detail)
      return appendI5TbReconciliationToLead(base, tbUnadjusted.value)
    }
    return leadMatrixRows.value.map((r) => ({ ...r, layer: r.isTotal ? 
    )
    return safeParseRows<I5AdjustmentRowRaw>(resp?.remark)
  })

  const detailTotals: ComputedRef<I5DetailTotals> = computed(() => {
    const beginBalances: number[] = []
    const increases: number[] = []
    const decreases: number[] = []
    const endBalances: number[] = []

    for (const row of detailRowsRaw.value) {
      const name = String(row?.projectName || row?.name || 
    )
    } finally {
      isSyncing.value = false
    }
  }

  async function generateNoteText(): Promise<string | null> {
    if (!wpId.value) return null
    isAiGenerating.value = true
    try {
      const t = totals.value
      const res = await api.post(`/api/workpapers/${wpId.value}/ai/generate-text`, {
        section: `i5-disclosure-${variant.value}`,
        prompt: 
    )
  const sub = summarizeI5Adjudication(detail)
  const beginAje = calcSubtotal(detail.map((r) => _num(r.openingAje)))
  const beginRje = calcSubtotal(detail.map((r) => _num(r.openingRje)))
  const endAje = calcSubtotal(detail.map((r) => (r.endAje != null ? _num(r.endAje) : _num(r.aje))))
  const endRje = calcSubtotal(detail.map((r) => (r.endRje != null ? _num(r.endRje) : _num(r.rje))))
  return {
    beginUnadj: calcSubtotal(detail.map((r) => _num(r.beginBalance) - _num(r.openingAje) - _num(r.openingRje))),
    beginAje,
    beginRje,
    beginAdj: _round2(beginAje + beginRje),
    beginAudited: sub.beginBalance,
    endUnadj: sub.unadjusted,
    endAje,
    endRje,
    endAdj: _round2(endAje + endRje),
    endAudited: sub.audited,
    varianceAmount: sub.varianceAmount,
    varianceRate: sub.varianceRate,
  }
}

/** 按项目展开审定矩阵（末行合计），对齐 Excel 逐项列示 */
export function buildI5LeadMatrixRows(rows: I5AdjudicationRowModel[]): I5LeadMatrixRow[] {
  const detail = rows.filter((r) => r.projectName !== 
    )
  }

  function fillConclusionDraft(): void {
    auditConclusion.value = buildI5AdjudicationConclusionDraft({
      sampleCount: rows.value.length,
      auditedTotal: subtotals.value.audited,
      tbDiff: tbDifference.value,
      hasAje: rows.value.some((r) => Math.abs(r.aje) + Math.abs(r.rje) > 0.005),
      crossWarning: crossCheck.value.hasWarning,
    })
    saveConclusion(auditConclusion.value)
  }

  /** 生成 Excel 式变动说明草稿，写入审计说明（可再编辑） */
  function fillVarianceNoteDraft(append = true): void {
    const draft = buildI5VarianceNoteDraft(computedRows.value)
    auditNote.value = append && auditNote.value.trim()
      ? `${auditNote.value.trim()}\n\n${draft}`
      : draft
    saveNote(auditNote.value)
  }

  function applyConclusionTemplate(key: string): void {
    const t = I5_CONCLUSION_OPTIONS.find((x) => x.key === key)
    if (!t) return
    auditConclusion.value = t.text
    saveConclusion(t.text)
  }

  // ─── 显式发布门状态（防重复提交，供发布按钮 :loading 绑定） ─────────────────
  const publishing = ref(false)

  /** 发布下游联动事件（仅 emit，不写 TB）。 */
  function _emitAdjudicated(): void {
    window.dispatchEvent(new CustomEvent(
    )
const tbSourceCodes = computed(() => extractTbSourceCodes(props.htmlData))

const {
  rows,
  auditNote,
  auditConclusion,
  significantMatters,
  ownershipPledge,
  subtotals,
  leadMatrixRows,
  threeLayerLeadRows,
  hasThreeLayerDetail,
  crossCheck,
  reconciliationStatus,
  hasAjeApprox,
  tbDifference,
  differenceRows,
  addRow,
  removeRow,
  updateCell,
  seedFromI52,
  syncFromI53,
  applyTbData,
  applyPriorFromTb,
  fillConclusionDraft,
  fillVarianceNoteDraft,
  applyConclusionTemplate,
  writeback,
  publishToTb,
  publishing,
  saveNote,
  saveConclusion,
  saveSignificantMatters,
  saveOwnershipPledge,
} = useI5Adjudication(
  toRef(props, 
    )
}

/** 抽凭引擎 SampledVoucher → I5-4 行 */
export function mapSampledToI5TargetedRow(
  s: {
    voucherNo?: string
    voucherDate?: string
    summary?: string | null
    debitAmount?: string | number | null
    creditAmount?: string | number | null
    counterpartAccount?: string | null
    accountName?: string | null
    isHighValue?: boolean
    selectionReason?: string
    abnormal?: boolean
    remark?: string
  },
  catalog?: I52ProjectRef[],
): I5TargetedCheckRow {
  const reason = _str(s.selectionReason)
  const isSpecific = !!(s.isHighValue || reason)
  const matched = catalog?.length
    ? matchI52ProjectName(catalog, {
        summary: _str(s.summary),
        accountName: _str(s.accountName),
      })
    : 
    )
}

export function summarizeI5Targeted(
  rows: I5TargetedCheckRow[],
  periodDebitTotal: number,
  periodCreditTotal = 0,
): I5TargetedSummary {
  const sampleCount = rows.length
  const checkedDebitTotal = Math.round(rows.reduce((s, r) => s + _num(r.debitAmount), 0) * 100) / 100
  const checkedCreditTotal = Math.round(rows.reduce((s, r) => s + _num(r.creditAmount), 0) * 100) / 100
  const anomalyCount = rows.filter((r) => isAbnormalFlag(r.isAbnormal) || hasFailedCheck(r)).length
  const failCheckCount = rows.filter(hasFailedCheck).length
  const pendingCount = rows.filter((r) => !isRowChecksComplete(r)).length
  const completedCheckCount = rows.filter(isRowChecksComplete).length

  const specificRows = rows.filter((r) => r.isSpecific || !!r.selectionReason)
  const samplingRows = rows.filter((r) => !(r.isSpecific || !!r.selectionReason))
  const specificCount = specificRows.length
  const specificDebitTotal = Math.round(specificRows.reduce((s, r) => s + _num(r.debitAmount), 0) * 100) / 100
  const samplingDebitTotal = Math.round(samplingRows.reduce((s, r) => s + _num(r.debitAmount), 0) * 100) / 100

  let coverageRate: number | null = null
  let creditCoverageRate: number | null = null
  let specificCoverageRate: number | null = null
  let samplingCoverageRate: number | null = null
  if (periodDebitTotal > 0) {
    coverageRate = Math.round((checkedDebitTotal / periodDebitTotal) * 10000) / 100
    specificCoverageRate = Math.round((specificDebitTotal / periodDebitTotal) * 10000) / 100
    samplingCoverageRate = Math.round((samplingDebitTotal / periodDebitTotal) * 10000) / 100
  }
  if (periodCreditTotal > 0) {
    creditCoverageRate = Math.round((checkedCreditTotal / periodCreditTotal) * 10000) / 100
  }

  return {
    sampleCount,
    checkedDebitTotal,
    checkedCreditTotal,
    periodTotal: periodDebitTotal,
    coverageRate,
    creditCoverageRate,
    anomalyCount,
    failCheckCount,
    pendingCount,
    completedCheckCount,
    specificCount,
    specificDebitTotal,
    samplingDebitTotal,
    specificCoverageRate,
    samplingCoverageRate,
  }
}

export function formatCoverageLabel(rate: number | null): string {
  if (rate == null) return 
    ) as string
  }

  const computedRows = computed(() => rows.value.map(recalcI5AdjudicationRow))
  const subtotals = computed(() => summarizeI5Adjudication(computedRows.value))
  const excelLead = computed(() => buildI5ExcelLeadSummary(computedRows.value))
  const leadMatrixRows = computed(() => buildI5LeadMatrixRows(computedRows.value))
  /** 有 I5-2 嵌套原值/减值时展示三层矩阵 + TB勾稽；否则回退净值矩阵 */
  const threeLayerLeadRows = computed(() => {
    const detail = detailRowsRaw.value
    const hasNested = detail.some((r: any) => r?.gross && typeof r.gross === 
    ) {
      totalRje = _round2(totalRje + net)
      if (name) namedRje.push({ name, net })
    } else {
      totalAje = _round2(totalAje + net)
      if (name) namedAje.push({ name, net })
    }
  }

  if ((Math.abs(totalAje) < 0.005 && Math.abs(totalRje) < 0.005) || !rows.length) {
    return { rows, applied: 0, approx: false, totalAje, totalRje, matchedByName: 0 }
  }

  const next = rows.map((r) => ({ ...r, aje: 0, rje: 0, ajeApprox: false }))
  const byName = new Map(next.map((r) => [r.projectName.trim(), r]))
  let matchedByName = 0
  let ajeNamed = 0
  let rjeNamed = 0

  for (const { name, net } of namedAje) {
    const row = byName.get(name)
    if (!row) continue
    row.aje = _round2(row.aje + net)
    matchedByName++
    ajeNamed = _round2(ajeNamed + net)
  }
  for (const { name, net } of namedRje) {
    const row = byName.get(name)
    if (!row) continue
    row.rje = _round2(row.rje + net)
    matchedByName++
    rjeNamed = _round2(rjeNamed + net)
  }

  const ajeRem = _round2(totalAje - ajeNamed)
  const rjeRem = _round2(totalRje - rjeNamed)
  let approx = false
  let applied = matchedByName

  if (Math.abs(ajeRem) > 0.005 || Math.abs(rjeRem) > 0.005) {
    if (next.length === 1) {
      next[0].aje = _round2(next[0].aje + ajeRem)
      next[0].rje = _round2(next[0].rje + rjeRem)
      applied++
    } else {
      const allocated = allocateI5Adjustments(next, ajeRem, rjeRem, true)
      for (let i = 0; i < next.length; i++) {
        next[i].aje = _round2(next[i].aje + allocated[i].aje)
        next[i].rje = _round2(next[i].rje + allocated[i].rje)
        if (allocated[i].ajeApprox) {
          next[i].ajeApprox = true
          approx = true
        }
      }
      applied += next.length
    }
  }

  return {
    rows: next.map(recalcI5AdjudicationRow),
    applied,
    approx,
    totalAje,
    totalRje,
    matchedByName,
  }
}

export function buildI5AdjudicationCrossCheck(
  rows: I5AdjudicationRowModel[],
  detail: { beginBalance?: number; increase?: number; decrease?: number; endBalance?: number },
): I5AdjudicationCrossCheck {
  const sub = summarizeI5Adjudication(rows)
  const detailBegin = _num(detail.beginBalance)
  const detailIncrease = _num(detail.increase)
  const detailDecrease = _num(detail.decrease)
  const detailEnd = _num(detail.endBalance)
  const beginDiff = _round2(sub.beginBalance - detailBegin)
  const endDiff = _round2(sub.endBalance - detailEnd)
  const auditedVsDetailDiff = _round2(sub.audited - detailEnd)
  return {
    detailBegin,
    detailIncrease,
    detailDecrease,
    detailEnd,
    adjBegin: sub.beginBalance,
    adjIncrease: sub.increase,
    adjDecrease: sub.decrease,
    adjEnd: sub.endBalance,
    adjAudited: sub.audited,
    beginDiff,
    endDiff,
    auditedVsDetailDiff,
    hasWarning: [beginDiff, endDiff, auditedVsDetailDiff].some((d) => Math.abs(d) > 0.01),
  }
}

export interface I5ExcelLeadSummary {
  beginUnadj: number
  /** 期初账项调整（本期审定表通常为 0，保留列对齐 Excel） */
  beginAje: number
  beginRje: number
  beginAdj: number
  beginAudited: number
  endUnadj: number
  endAje: number
  endRje: number
  endAdj: number
  endAudited: number
  varianceAmount: number
  varianceRate: number | null
}

export interface I5LeadMatrixRow extends I5ExcelLeadSummary {
  label: string
  isTotal?: boolean
}

/** 对齐 Excel：期初/期末 × 未审·账项调整·重分类调整·审定 + 变动 */
export function buildI5ExcelLeadSummary(rows: I5AdjudicationRowModel[]): I5ExcelLeadSummary {
  const detail = rows.filter((r) => r.projectName !== 
    ))
    const resolvedProject = row.projectName
      || matchI52ProjectName(extractI52ProjectCatalog(detailRows), {
        summary: row.businessDesc,
        accountName: row.counterpartAccount,
      })
    let draftKind: I5TargetedAdjDraft[
    ))
    const result = applyAjeFromI53(rows.value, adj)
    rows.value = result.rows
    _persist()
    if (!result.applied && Math.abs(result.totalAje) < 0.005 && Math.abs(result.totalRje) < 0.005) {
      ElMessage.info(
    ))
  const pop = _num(sampleMeta?.populationAmount ?? sampleMeta?.periodDebitTotal)
  const threshold = _num(sampleMeta?.coverageThreshold) || 20
  if (i54Rows.length && pop > 0) {
    const checked = i54Rows.reduce((s: number, r: any) => s + _num(r.debitAmount), 0)
    const rate = Math.round((checked / pop) * 10000) / 100
    const note = _readText(map.get(
    ),
      summary: description,
      debit: debitAmount,
      credit: creditAmount,
      sourceGroupId: raw.sourceGroupId ? String(raw.sourceGroupId) : undefined,
    }
  }

  function _toPersistShape(list: I5AdjustmentRow[]) {
    return list.map((r, i) => ({
      ...r,
      seq: i + 1,
      debit: r.debitAmount,
      credit: r.creditAmount,
      debitAmount: r.debitAmount,
      creditAmount: r.creditAmount,
      summary: r.description,
      entryType: entryTypeFromCategory(String(r.category)),
    }))
  }

  function load(): void {
    const parsed = _getJson(ROWS_KEY)
    if (Array.isArray(parsed)) {
      rows.value = parsed.map((r, i) => _normalizeRow(r, i))
    } else {
      rows.value = []
    }
    auditNote.value = _getString(NOTE_KEY) || _getString(LEGACY_NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY) || _getString(LEGACY_CONCLUSION_KEY)
  }

  watch(allResponses, () => load(), { immediate: true })

  const debitTotal = computed(() => rows.value.reduce((s, r) => s + r.debitAmount, 0))
  const creditTotal = computed(() => rows.value.reduce((s, r) => s + r.creditAmount, 0))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() => Math.abs(balanceDiff.value) < BALANCE_TOLERANCE)

  const groupBalanceIssues = computed(() => {
    const groups = new Map<string, {
      key: string
      description: string
      entryType: string
      debit: number
      credit: number
      rowCount: number
    }>()
    for (const r of rows.value) {
      const et = r.entryType || entryTypeFromCategory(String(r.category))
      const desc = String(r.description || 
    ),
    })
  }
  return out
}

/** 在三层矩阵末追加 TB 勾稽行（对齐 Excel：TB数据 / 差异） */
export function appendI5TbReconciliationToLead(
  matrix: I5ThreeLayerLeadRow[],
  tbUnadjusted: number,
): I5ThreeLayerLeadRow[] {
  if (!matrix.length) return matrix
  const netTotals = matrix.filter((r) => r.isTotal)
  const netTotal = netTotals[netTotals.length - 1]
  if (!netTotal) return matrix
  const audited = _num(netTotal.endAudited)
  const tb = _round2(_num(tbUnadjusted))
  const diff = _round2(audited - tb)
  const blank = {
    beginUnadj: 0, beginAje: 0, beginRje: 0, beginAdj: 0, beginAudited: 0,
    endUnadj: 0, endAje: 0, endRje: 0, endAdj: 0,
    varianceAmount: 0, varianceRate: null as number | null,
  }
  return [
    ...matrix,
    {
      ...blank,
      label: 
    ),
  )
  const crossCheck = computed<I5AdjudicationCrossCheck>(() =>
    buildI5AdjudicationCrossCheck(computedRows.value, detailTotals.value as any),
  )
  const reconciliationStatus = computed<
    ).toLowerCase()
}

/**
 * 用凭证摘要/科目名模糊匹配 I5-2 项目名。
 * 优先：精确 → 摘要包含项目名 → 项目名包含摘要片段。
 */
export function matchI52ProjectName(
  catalog: I52ProjectRef[],
  hints: { summary?: string; accountName?: string },
): string {
  if (!catalog.length) return 
    ,
        },
      )
    }
  }
  return lines
}

/** 合并进既有 I5-3 行：按 description+accountCode 去重 */
export function mergeI53LinesSkippingExisting(
  existing: any[],
  incoming: I54ToI53Line[],
): { merged: any[]; added: number } {
  const keys = new Set(
    (existing || []).map((r) => {
      const desc = String(r?.description || r?.summary || 
    ,
      beginUnadj,
      beginAje,
      beginRje,
      beginAdj: _round2(beginAje + beginRje),
      beginAudited: _num(r.beginBalance),
      endUnadj: _num(r.unadjusted),
      endAje,
      endRje,
      endAdj: _round2(endAje + endRje),
      endAudited: _num(r.audited),
      varianceAmount: _num(r.varianceAmount),
      varianceRate: r.varianceRate,
      isTotal: false,
    }
  })
  const L = buildI5ExcelLeadSummary(detail)
  out.push({ ...L, label: 
    ,
      end_book: _num(r.endGross),
      end_impair: _num(r.endImpairment),
      end_carrying: _num(r.endBookValue),
      prior_book: _num(r.priorGross),
      prior_impair: _num(r.priorImpairment),
      prior_carrying: _num(r.priorBookValue),
      is_total: false,
    }))

  const totals = summarizeI5Disclosure(state.rows || [])
  dataRows.push({
    label: 
    ,
      isEditable: true,
      fromDetail: true,
      ajeApprox: prev?.ajeApprox ?? false,
    }))
  }
  return out
}

export function allocateI5Adjustments(
  rows: I5AdjudicationRowModel[],
  totalAje: number,
  totalRje: number,
  markApprox = true,
): I5AdjudicationRowModel[] {
  if (!rows.length) return rows
  const base = rows.map((r) => Math.abs(_num(r.unadjusted)) || Math.abs(_num(r.endBalance)))
  const sum = calcSubtotal(base)
  if (!(sum > 0)) {
    return rows.map((r, i) => recalcI5AdjudicationRow({
      ...r,
      aje: i === 0 ? totalAje : 0,
      rje: i === 0 ? totalRje : 0,
      ajeApprox: markApprox && i === 0 && rows.length > 1,
    }))
  }
  let ajeLeft = totalAje
  let rjeLeft = totalRje
  return rows.map((r, i) => {
    const ratio = base[i] / sum
    const isLast = i === rows.length - 1
    const aje = isLast ? _round2(ajeLeft) : _round2(totalAje * ratio)
    const rje = isLast ? _round2(rjeLeft) : _round2(totalRje * ratio)
    ajeLeft = _round2(ajeLeft - aje)
    rjeLeft = _round2(rjeLeft - rje)
    return recalcI5AdjudicationRow({
      ...r,
      aje,
      rje,
      ajeApprox: markApprox && rows.length > 1,
    })
  })
}

export function applyAjeFromI53(
  rows: I5AdjudicationRowModel[],
  adjRows: any[],
): {
  rows: I5AdjudicationRowModel[]
  applied: number
  approx: boolean
  totalAje: number
  totalRje: number
  matchedByName: number
} {
  let totalAje = 0
  let totalRje = 0
  const namedAje: Array<{ name: string; net: number }> = []
  const namedRje: Array<{ name: string; net: number }> = []

  for (const line of adjRows || []) {
    const code = String(line?.accountCode || 
    ,
      期末余额: _num(r.endBookValue),
      年初余额: _num(r.priorBookValue),
      is_total: false,
    }))

  const totals = summarizeI5Disclosure(state.rows || [])
  dataRows.push({
    label: 
    ,
    accountCode: ACCOUNT_CODE_1911,
    audited: subtotals.value.audited,
    tbAmount: tbUnadjusted.value,
    difference: tbDifference.value,
  }])

  function _persist(): void {
    const save = options?.onSave
    if (!save) return
    save(I5_ADJ_ROWS_KEY, rows.value)
    save(`${ITEM_PREFIX}-rows`, rows.value)
  }

  async function addRow(): Promise<void> {
    try {
      const { value: projectName } = await ElMessageBox.prompt(
        
    ,
    beginBalance: calcSubtotal(detail.map((r) => r.beginBalance)),
    increase: calcSubtotal(detail.map((r) => r.increase)),
    decrease: calcSubtotal(detail.map((r) => r.decrease)),
    endBalance: 0,
    unadjusted: calcSubtotal(detail.map((r) => r.unadjusted)),
    aje: calcSubtotal(detail.map((r) => r.aje)),
    rje: calcSubtotal(detail.map((r) => r.rje)),
    audited: 0,
    priorAudited: calcSubtotal(detail.map((r) => r.priorAudited)),
    varianceAmount: 0,
    varianceRate: null,
    triangleDiff: 0,
    hasError: false,
    isEditable: false,
  })
}

function _detailName(r: any): string {
  return _str(r?.projectName || r?.name || r?.项目).trim()
}

/** 单层滚动块 → Excel I5-1 期初/期末矩阵字段 */
export function extractI5LeadFromRoll(block: any): {
  beginUnadj: number
  beginAje: number
  beginRje: number
  beginAudited: number
  endUnadj: number
  endAje: number
  endRje: number
  endAudited: number
  auditedOpening: number
  auditedIncrease: number
  auditedDecrease: number
  auditedEnding: number
} {
  const unadjOpening = _num(block?.unadjOpening)
  const unadjIncrease = _num(block?.unadjIncrease)
  const unadjDecrease = _num(block?.unadjDecrease)
  const openingAje = _num(block?.openingAje)
  const openingRje = _num(block?.openingRje)
  const ajeIncrease = _num(block?.ajeIncrease)
  const ajeDecrease = _num(block?.ajeDecrease)
  const rjeIncrease = _num(block?.rjeIncrease)
  const rjeDecrease = _num(block?.rjeDecrease)
  const unadjEnding = block?.unadjEnding != null
    ? _num(block.unadjEnding)
    : _round2(calcAssetEndBalance(unadjOpening, unadjIncrease, unadjDecrease))
  const auditedOpening = block?.auditedOpening != null
    ? _num(block.auditedOpening)
    : _round2(unadjOpening + openingAje + openingRje)
  const auditedIncrease = block?.auditedIncrease != null
    ? _num(block.auditedIncrease)
    : _round2(unadjIncrease + ajeIncrease + rjeIncrease)
  const auditedDecrease = block?.auditedDecrease != null
    ? _num(block.auditedDecrease)
    : _round2(unadjDecrease + ajeDecrease + rjeDecrease)
  const auditedEnding = block?.auditedEnding != null
    ? _num(block.auditedEnding)
    : _round2(calcAssetEndBalance(auditedOpening, auditedIncrease, auditedDecrease))
  // Excel 期末账项/重分类：使 未审期末+账项+重分类=审定期末
  const endAje = _round2(openingAje + ajeIncrease - ajeDecrease)
  const endRje = _round2(openingRje + rjeIncrease - rjeDecrease)
  return {
    beginUnadj: unadjOpening,
    beginAje: openingAje,
    beginRje: openingRje,
    beginAudited: auditedOpening,
    endUnadj: unadjEnding,
    endAje,
    endRje,
    endAudited: auditedEnding,
    auditedOpening,
    auditedIncrease,
    auditedDecrease,
    auditedEnding,
  }
}

function _subtractLead(
  a: ReturnType<typeof extractI5LeadFromRoll>,
  b: ReturnType<typeof extractI5LeadFromRoll>,
): ReturnType<typeof extractI5LeadFromRoll> {
  return {
    beginUnadj: _round2(a.beginUnadj - b.beginUnadj),
    beginAje: _round2(a.beginAje - b.beginAje),
    beginRje: _round2(a.beginRje - b.beginRje),
    beginAudited: _round2(a.beginAudited - b.beginAudited),
    endUnadj: _round2(a.endUnadj - b.endUnadj),
    endAje: _round2(a.endAje - b.endAje),
    endRje: _round2(a.endRje - b.endRje),
    endAudited: _round2(a.endAudited - b.endAudited),
    auditedOpening: _round2(a.auditedOpening - b.auditedOpening),
    auditedIncrease: _round2(a.auditedIncrease - b.auditedIncrease),
    auditedDecrease: _round2(a.auditedDecrease - b.auditedDecrease),
    auditedEnding: _round2(a.auditedEnding - b.auditedEnding),
  }
}

/** 从 I5-2 行提取净值滚动（供审定表带入） */
export function extractI5DetailLead(raw: any): ReturnType<typeof extractI5LeadFromRoll> & {
  projectName: string
} {
  const projectName = _detailName(raw)
  if (raw?.gross && typeof raw.gross === 
    ,
  )
  const hasAjeApprox = computed(() => computedRows.value.some((r) => r.ajeApprox))
  const tbUnadjusted = computed(() => options?.tbUnadjusted1911?.value ?? 0)
  const tbDifference = computed(() => subtotals.value.audited - tbUnadjusted.value)
  const differenceRows = computed<I5DifferenceRow[]>(() => [{
    label: 
    ,
  subjectLabel: i5AccountLabel as any,
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) => updateCell(rowKey, field, value),
  totalAudited: () => subtotals.value.audited,
})

const BROWSE_THRESHOLD = 30
const browseMode = ref(true)
const tableWidth = ref(1200)
const editPage = ref(1)
const editPageSize = 50
const useVirtualScroll = computed(() => rows.value.length > BROWSE_THRESHOLD)

const virtualColumns = computed<VirtualColumn[]>(() => {
  const fmt = (v: unknown) => fmtAmount(Number(v) || 0)
  const numCol = (key: string, title: string, w = 100): VirtualColumn => ({
    key,
    dataKey: key,
    title,
    width: w,
    align: 
    ,
  })
}

export function summarizeI5Disclosure(rows: I5DisclosureRow[]): I5DisclosureTotals {
  const t: I5DisclosureTotals = {
    endGross: 0,
    endImpairment: 0,
    endBookValue: 0,
    priorGross: 0,
    priorImpairment: 0,
    priorBookValue: 0,
  }
  for (const r of rows) {
    t.endGross += _num(r.endGross)
    t.endImpairment += _num(r.endImpairment)
    t.endBookValue += _num(r.endBookValue)
    t.priorGross += _num(r.priorGross)
    t.priorImpairment += _num(r.priorImpairment)
    t.priorBookValue += _num(r.priorBookValue)
  }
  t.endGross = _round2(t.endGross)
  t.endImpairment = _round2(t.endImpairment)
  t.endBookValue = _round2(t.endBookValue)
  t.priorGross = _round2(t.priorGross)
  t.priorImpairment = _round2(t.priorImpairment)
  t.priorBookValue = _round2(t.priorBookValue)
  return t
}

const _KNOWN = new Set<string>(I5_DEFAULT_DISCLOSURE_CATEGORIES)

/** 从 I5-2 明细行解析披露分类标签 */
export function resolveI5DisclosureLabel(detail: any): string {
  const category = String(detail?.category ?? detail?.assetType ?? 
    ,
] as const

export interface I5DetailSubtotals {
  grossUnadjEnding: number
  grossAuditedEnding: number
  impAuditedEnding: number
  netUnadjEnding: number
  netAuditedOpening: number
  netAuditedIncrease: number
  netAuditedDecrease: number
  netAuditedEnding: number
  // legacy
  beginBalance: number
  increase: number
  decrease: number
  endBalance: number
  originalAmount: number
  accumulatedAmount: number
  netValue: number
}

export interface I5DetailColumn {
  key: string
  label: string
  width: number
  editable: boolean
  type: 
    ,
] as const

export type I5TargetedCheckMark = (typeof I5_4_CHECK_OPTIONS)[number]

export interface I5TargetedCheckRow {
  rowId: string
  /** 其他非流动资产项目明细 */
  projectName: string
  voucherDate: string
  voucherNo: string
  businessDesc: string
  counterpartAccount: string
  counterpartDetail: string
  debitAmount: number
  creditAmount: number
  supportingDocs: string
  check1: I5TargetedCheckMark | string
  check2: I5TargetedCheckMark | string
  check3: I5TargetedCheckMark | string
  check4: I5TargetedCheckMark | string
  check5: I5TargetedCheckMark | string
  indexRef: string
  isAbnormal: string
  remark: string
  isSpecific: boolean
  selectionReason: string
}

export interface I5TargetedSampleMeta {
  populationCount: number
  /** 测试总体金额（借方口径，用于检查比例） */
  populationAmount: number
  /** 本期贷方发生额（减少/转出等，展示用） */
  populationCreditAmount: number
  populationDesc: string
  populationManual: boolean
  /** Excel「测试原因」多选 */
  testReasons: string[]
  specificSample: string
  specificAmount: number
  samplingPopulationDesc: string
  sampleSize: number
  sampleMethod: string
  sampleProcess: string
  coverageThreshold: number
}

/** 原段落型风险关注（兼容旧分类正确性/期限适当性/可回收性 radio+textarea） */
export interface I5TargetedRiskFocus {
  classification: string
  maturity: string
  recoverability: string
  classificationConclusion: string
  maturityConclusion: string
  recoverabilityConclusion: string
}

export interface I5TargetedSummary {
  sampleCount: number
  checkedDebitTotal: number
  checkedCreditTotal: number
  periodTotal: number
  coverageRate: number | null
  /** 贷方检查比例（样本贷方 ÷ 本期贷方发生额） */
  creditCoverageRate: number | null
  anomalyCount: number
  failCheckCount: number
  pendingCount: number
  completedCheckCount: number
  specificCount: number
  specificDebitTotal: number
  samplingDebitTotal: number
  specificCoverageRate: number | null
  samplingCoverageRate: number | null
}

export interface I5PeriodMovement {
  /** 本期借方代理：当期新增其他非流动资产 */
  debitTotal: number
  /** 本期贷方：本期减少（转出/重分类/清理）合计 */
  creditTotal: number
  /** 原始金额合计（存在性测试总体备选） */
  originalTotal: number
  source: string
}

export function emptyI5TargetedRow(partial?: Partial<I5TargetedCheckRow>): I5TargetedCheckRow {
  return {
    rowId: partial?.rowId || `i54-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    projectName: 
    , () => {})
const isReadonly = computed(() => Boolean(props.isReadonly))
const projectId = computed(() => props.projectId)

const {
  rows,
  activeSection,
  activeColumns,
  subtotals,
  rollWarnings,
  sections,
  setActiveRow,
  getCellValue,
  updateCell,
  addRow,
  removeRow,
} = useI5Detail(
  toRef(props, 
    , CONCLUSION_KEY, val)
}

function handleFillDraft(): void {
  auditConclusion.value = buildI5DetailConclusionDraft({
    rowCount: rows.value.length,
    netAuditedEnding: subtotals.value.netAuditedEnding,
    grossAuditedEnding: subtotals.value.grossAuditedEnding,
    impAuditedEnding: subtotals.value.impAuditedEnding,
    warningCount: rollWarnings.value.length,
  })
  saveAuditConclusion(auditConclusion.value)
  ElMessage.success(
    , accountCodes: [ACCOUNT_CODE_1911], auditedTotal: subtotals.value.audited },
    }))
  }

  /**
   * 保存审定表（普通保存动作，不写 TB）。
   *
   * spec: tb-writeback-explicit-publish-gate Task 13 / Req 1。
   * 此前保存后**自动** PUT 旧端点回写 trial_balance(1911) → 违反 Req 1。现只保存 + emit；
   * TB 回写收敛为用户显式确认动作（publishToTb）。
   */
  async function writeback(force = false): Promise<{ ok: boolean; message?: string }> {
    const gate = validateI5AdjudicationSave({
      rows: computedRows.value,
      tbDiff: tbDifference.value,
      force,
    })
    if (!gate.ok) {
      const msg = gate.blockers.join(
    , isTotal: true })
  return out
}

export type I5LayerKind = 
    , { minimumFractionDigits: 2 })}（${summary.value.specificCount} 笔）`,
    }
  }

  function fillFromSampledVouchers(samples: any[]): number {
    if (!Array.isArray(samples) || !samples.length) return 0
    const catalog = i52ProjectCatalog.value
    const existing = new Set(
      rows.value.map((r) => `${r.voucherDate}|${r.voucherNo}`).filter((k) => k !== 
    , { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function buildI5AdjudicationConclusionDraft(opts: {
  sampleCount: number
  auditedTotal: number
  tbDiff: number
  hasAje: boolean
  crossWarning: boolean
}): string {
  const parts = [
    `其他非流动资产审定表共 ${opts.sampleCount} 个项目，审定合计 ${opts.auditedTotal.toFixed(2)}。`,
  ]
  if (opts.hasAje) parts.push(
    >
        <summary>编制提示</summary>
        <ul>
          <li>两科目净值勾稽：<strong>账面净值 = 原值 − 减值准备</strong>；1911 其他非流动资产为资产借方，期末 = 期初 + 增加 − 减少（无直线摊销列）</li>
          <li>推荐工作流：I5A 程序 → I5-2 明细（原值/减值/净值三层滚动） → I5-4 针对性检查 → I5-3 调整回写 I5-1 → 附注披露</li>
          <li>I5-2 明细按 原值 / 减值 / 净值 三层滚动（未审 → 调整 → 审定），净值 = 原值审定 − 减值审定</li>
          <li>审定合计回写 TB(1911) 并驱动附注披露；各表填妥
    >
      <summary>操作提示</summary>
      <ul>
        <li>区段：原值未审 → 原值调整与审定 → 减值准备 → 净值与索引；行跨区段同步。</li>
        <li>公式对齐 Excel：L=B+F+G，M=C+H+J，N=D+I+K，O=L+M−N；净值=原值−减值。</li>
        <li>内置 10 类与源模板一致；合同资产/取得成本/履约成本可跳转 D7、M12、G2-13。</li>
        <li>合计勾稽审定表 I5-1（带入净值审定）；导入导出覆盖原值+减值结构。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang=
    >
      <summary>编制说明（对齐 Excel I5-4）</summary>
      <ol>
        <li>先勾选测试原因并填第二节总体；特定样本 100% 检查，其余从抽样总体抽取。</li>
        <li>检查比例=样本借方÷本期借方（总体为 0 显示 N/A）；无新增时可改用「带入原始金额合计」作存在性测试，并在说明中解释。</li>
        <li>表内「选取原因」非空即视为特定层；第二节「特定样本金额」与表内特定借方可一键同步并容差校验。</li>
        <li>核对 1~5 对应测试内容说明；选「×」时自动建议异常类型，可写入说明草稿或推送结构化分录至 I5-3。</li>
        <li>项目明细优先从 I5-2 下拉挂接；专项风险关注记载分类/期限/可回收性段落结论，与抽凭相互印证。</li>
      </ol>
    </details>

    <el-dialog
      v-model=
  I6: 81 个
    

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表行（27行，每行对应一个研发费用类别） */
export interface I6AdjudicationRow {
  rowId: string
  /** A列：类别名称 */
  类别: string
  /** B列：上期未审 */
  上期未审: number
  /** C列：上期AJE */
  上期AJE: number
  /** D列：上期RJE */
  上期RJE: number
  /** E列：上期审定（公式：B+C+D） */
  上期审定: number
  /** F列：本期未审 */
  本期未审: number
  /** G列：本期AJE */
  本期AJE: number
  /** H列：本期RJE */
  本期RJE: number
  /** I列：本期审定（公式：F+G+H） */
  本期审定: number
  /** J列：变动额（公式：I-E） */
  变动额: number
  /** K列：变动率（公式：见calcI6ChangeRate） */
  变动率: number | null
  /** 备注 */
  备注: string
  /** 变动率超阈值高亮 */
  changeRateHighlight: boolean
  /** 可编辑标记 */
  isEditable?: boolean
  /** 合计行标记 */
  isTotal?: boolean
}

/** I2联动面板数据 */
export interface I6LinkagePanel {
  /** 费用化金额（来自审定表合计-本期审定） */
  expenseI6: number
  /** 资本化金额（来自I2 EventBus） */
  capitalizedI2: number
  /** 研发总额（expenseI6 + capitalizedI2） */
  researchTotal: number
  /** VR-I6-01校验结果 */
  vrI601Status: {
    isValid: boolean
    difference: number
  }
  /** I2数据是否可用 */
  i2DataReady: boolean
}

/** ChecklistItem 类型 */
export interface I6ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** 跨sheet接口类型（useI6CrossSheet的返回值子集） */
export interface I6CrossSheetData {
  detailMonthlyTotals: ComputedRef<number[]>
  i2LinkageStatus: ComputedRef<{ capitalized: number; total: number; isBalanced: boolean }>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ROWS = 
    

// ─── Types ───────────────────────────────────────────────────────────────────

/** 明细行存储结构（仅原始输入字段） */
export interface I6DetailStoredRow {
  id: string
  /** A列：项目类别（研发项目/明细行标识，供 I6-1 审定表引用） */
  category: string
  /** X列：费用性质（人工费/材料费等，供附注披露 SUMIF） */
  expenseNature: string
  /** B~M列：1月~12月金额 */
  months: number[]
  /** O列：账项调整 AJE */
  aje: number
  /** P列：重分类调整 RJE */
  rje: number
  /** S列：与相关科目勾稽 */
  reconciliation: string
  /** T列：上期未审 */
  priorUnadj: number
  /** U列：上期AJE */
  priorAje: number
  /** V列：上期RJE */
  priorRje: number
  /** X列：个别报表下的重分类 */
  individualReclass: number
  /** Y列：合并报表下的重分类 */
  consolidatedReclass: number
  /** Z列：备注 */
  remark: string
}

/** 明细行计算完整结构（含公式列） */
export interface I6DetailRow extends I6DetailStoredRow {
  /** N列：本期未审合计 = SUM(1月~12月) */
  unadjTotal: number
  /** Q列：本期审定数 = N + O + P */
  auditedAmount: number
  /** R列：各项目占比 = Q / Q_total × 100 (%) */
  ratio: number | null
  /** W列：上期审定 = T + U + V */
  priorAudited: number
  /** 月度变动率超阈值标记（用于高亮） */
  anomalyHighlight: boolean
}

/** 合计行结构 */
export interface I6DetailTotalRow {
  /** 12个月各月合计 */
  months: number[]
  /** 本期未审合计 */
  unadjTotal: number
  /** AJE合计 */
  aje: number
  /** RJE合计 */
  rje: number
  /** 审定数合计 */
  auditedAmount: number
  /** 上期未审合计 */
  priorUnadj: number
  /** 上期AJE合计 */
  priorAje: number
  /** 上期RJE合计 */
  priorRje: number
  /** 上期审定合计 */
  priorAudited: number
  /** 个别报表重分类合计 */
  individualReclass: number
  /** 合并报表重分类合计 */
  consolidatedReclass: number
}

/** ECharts 趋势图数据结构 */
export interface I6TrendChartData {
  /** X轴：月份标签 */
  xAxis: string[]
  /** 系列数据（每个研发项目一条线 + 合计线） */
  series: Array<{
    name: string
    data: number[]
    type: 
    

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** I6-2 明细行原始 JSON 结构（月度12列横向） */
export interface I6DetailRowRaw {
  rowId?: string
  projectName?: string        // 研发项目名称
  category?: string           // 费用类别
  month1?: number             // 1月
  month2?: number             // 2月
  month3?: number             // 3月
  month4?: number             // 4月
  month5?: number             // 5月
  month6?: number             // 6月
  month7?: number             // 7月
  month8?: number             // 8月
  month9?: number             // 9月
  month10?: number            // 10月
  month11?: number            // 11月
  month12?: number            // 12月
  total?: number              // 年度合计
}

/** I6-5/I6-6 截止测试行原始 JSON 结构（兼容新旧字段） */
export interface I6CutoffRowRaw {
  rowId?: string
  recordDate?: string
  bookingDate?: string
  documentDate?: string
  amount?: number
  documentAmount?: number
  expenseType?: string
  description?: string
  period?: string
  recordPeriod?: string
  belongPeriod?: string
  isCrossPeriod?: boolean
  conclusion?: string
}

/** I2 incoming event payload */
export interface I2CapitalizedEventDetail {
  /** I2 资本化金额 */
  capitalized?: number
  /** 兼容 useI6Adjudication 旧字段名 */
  capitalizedAmount?: number
  /** I2 侧认定的研发总额（优先作为 VR-I6-01 期望值） */
  total?: number
}

// ─── Return Types ────────────────────────────────────────────────────────────

export interface I2LinkageStatus {
  /** I6 费用化金额（审定发生额） */
  expense: number
  /** I2 资本化金额（从 EventBus 接收） */
  capitalized: number
  /** 实际合计（费用化 + 资本化） */
  total: number
  /** VR-I6-01 期望值（手工 / I2 事件 / 回退为 actual） */
  expectedTotal: number
  /** 是否已收到 I2 资本化数据（或从持久化恢复） */
  ready: boolean
  /** 是否平衡：I6费用化 + I2资本化 = 研发总额（允许±0.01精度） */
  isBalanced: boolean
  /** 差额（正=超出，负=不足） */
  difference: number
}

export interface CutoffSample {
  date: string
  amount: number
  isCrossover: boolean
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 安全解析 JSON 数组字符串，失败回退空数组
 */
function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/**
 * 安全提取数值，NaN/null/undefined → 0
 */
function _getNum(val: any): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI6CrossSheet(allResponses: Ref<Map<string, any>>): {
  detailMonthlyTotals: ComputedRef<number[]>
  i2LinkageStatus: ComputedRef<I2LinkageStatus>
  cutoffSamples: ComputedRef<Array<{ date: string; amount: number; isCrossover: boolean }>>
} {
  // ─── I2 incoming state（响应式存储 EventBus 接收的 I2 数据）─────────────

  const _i2Capitalized = ref(0)
  const _i2PublishedTotal = ref(0)
  const _expectedResearchTotal = ref(0)
  const _i2Ready = ref(false)

  // ─── 解析 I6-2 明细行数据 ──────────────────────────────────────────────

  const detailRows = computed<I6DetailRowRaw[]>(() => {
    const resp = allResponses.value.get(
    

export {
  type I6TargetedCheckRow,
  type I6TargetedSampleMeta,
  type I6TargetedRiskFocus,
  type I6TargetedSummary,
  type I6TargetedAdjDraft,
  type I6CoverageFooter,
  type I62ProjectRef,
  emptyI6TargetedRow,
  I6_4_DEFAULT_COVERAGE_THRESHOLD,
  I6_4_TEST_CONTENT,
  I6_4_TEST_REASONS,
  I6_4_SAMPLE_METHODS,
  I6_4_CHECK_OPTIONS,
  I6_4_ABNORMAL_OPTIONS,
  I6_4_OBJECTIVES,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  buildI6CoverageFooter,
  isAbnormalFlag,
  hasFailedCheck,
  buildI6TargetedConclusionDraft,
  buildI6TargetedAdjDrafts,
  buildI63LinesFromTargetedDrafts,
  mergeI63LinesSkippingExisting,
  mapSampledToI6TargetedRow,
  extractI62ProjectCatalog,
  matchI62ProjectName,
  I63_ROWS_KEY,
} from 
    

export { I6_DEFAULT_DISCLOSURE_CATEGORIES as I6_EXPENSE_NATURE_OPTIONS }

export interface I6DisclosureRow {
  rowId: string
  /** 费用性质/项目 */
  item: string
  currentAmount: number
  priorAmount: number
  isAutoFilled: boolean
  remark: string
}

export interface I6DisclosureTotals {
  currentAmount: number
  priorAmount: number
}

export const I6_DISC_KEYS = {
  listedRows: 
    
    /** 合计线加粗 */
    lineStyle?: { width: number }
    /** 异常月份标记点 */
    markPoint?: { data: Array<{ xAxis: number; yAxis: number; symbolSize: number }> }
  }>
  /** 合计线12个月数据（简化访问） */
  totalMonthly: number[]
}

/** 列定义（供Vue组件渲染使用） */
export interface I6DetailColumnDef {
  key: string
  label: string
  editable: boolean
  type: 
    
   * Req 4.7: 底部显示联动状态面板
   */
  const i2LinkageStatus: ComputedRef<I2LinkageStatus> = computed(() => {
    const expense = i6ExpenseAmount.value
    const capitalized = _i2Capitalized.value
    const actualTotal = expense + capitalized

    if (!_i2Ready.value) {
      return {
        expense,
        capitalized,
        total: actualTotal,
        expectedTotal: 0,
        ready: false,
        isBalanced: false,
        difference: 0,
      }
    }

    const expectedTotal = _expectedResearchTotal.value
      || _i2PublishedTotal.value
      || actualTotal
    const validation = validateVRI601(expense, capitalized, expectedTotal)

    return {
      expense,
      capitalized,
      total: actualTotal,
      expectedTotal,
      ready: true,
      isBalanced: validation.isValid,
      difference: validation.difference,
    }
  })

  // ═══ cutoffSamples: I6-5/I6-6 截止测试样本聚合 ════════════════════════

  /**
   * 聚合 I6-5（账→单据）和 I6-6（单据→账）的截止测试样本。
   * 跨期判断：单据日与记账日分处截止日两侧；无截止日则降级为记账期间≠归属期间。
   */
  const cutoffSamples: ComputedRef<CutoffSample[]> = computed(() => {
    const samples: CutoffSample[] = []
    const criteriaRaw = allResponses.value.get(
    
   * 当 I6 费用化金额变化时，发布事件通知 I2 同步校验。
   * I2 订阅此事件后更新自身的联动校验面板。
   */
  watch(i6ExpenseAmount, (newVal) => {
    const total = newVal + _i2Capitalized.value
    window.dispatchEvent(new CustomEvent(
    
  const accountCode = _resolveAccountCode(raw, accountName)
  const debitAmount = _num(raw?.debitAmount ?? raw?.debit)
  const creditAmount = _num(raw?.creditAmount ?? raw?.credit)
  return {
    rowId: _str(raw?.rowId) || `i63-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    description: _str(raw?.description || raw?.summary),
    category,
    entryType,
    reportItem: _str(raw?.reportItem) || (accountCode.startsWith(
    
  return `${rate.toFixed(2)}%`
}

export function formatLayeredCoverageLabel(summary: I6TargetedSummary): string {
  if (summary.coverageRate == null) return 
    
  return `借方 ${summary.coverageRate.toFixed(2)}%（特定 ${sp}% + 抽样 ${sa}%）`
}

export function buildI6CoverageFooter(
  summary: I6TargetedSummary,
  periodCreditTotal = 0,
): I6CoverageFooter {
  return {
    checkedDebitTotal: summary.checkedDebitTotal,
    periodDebitTotal: summary.periodTotal,
    debitCoverageLabel: formatCoverageLabel(summary.coverageRate),
    layeredCoverageLabel: formatLayeredCoverageLabel(summary),
  }
}

function _parseI62Rows(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 
    
import {
  parseNum,
  calcAuditedAmount,
  calcSubtotal,
  calcMonthlyTotal,
  calcResearchTotal,
  validateVRI601,
} from 
    
import {
  type I6TargetedCheckRow,
  type I6TargetedSampleMeta,
  type I6TargetedRiskFocus,
  type I6TargetedSummary,
  emptyI6TargetedRow,
  emptyI6TargetedSampleMeta,
  emptyI6TargetedRiskFocus,
  normalizeI6TargetedRow,
  normalizeI6TargetedSampleMeta,
  normalizeI6TargetedRiskFocus,
  summarizeI6Targeted,
  extractI6PeriodMovement,
  extractI62ProjectCatalog,
  enrichRowsWithI62Projects,
  analyzeI62ProjectConsistency,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  buildI6CoverageFooter,
  buildI6TargetedConclusionDraft,
  buildI6TargetedAdjDrafts,
  buildI63LinesFromTargetedDrafts,
  mergeI63LinesSkippingExisting,
  parseI63Rows,
  mapSampledToI6TargetedRow,
  syncSpecificAmountFromRows,
  suggestAbnormalFromFailedChecks,
  isAbnormalFlag,
  hasFailedCheck,
  I6_4_DEFAULT_COVERAGE_THRESHOLD,
  I63_ROWS_KEY,
} from 
    
import { validateVRI601, calcMonthlyTotal } from 
    
}

/** 附注披露 vs I6-1 / I6-2 勾稽汇总（含分项差异） */
export function buildI6DisclosureReconcileView(
  discRows: I6DisclosureRow[],
  detailRows: any[],
  adjRows: any[],
): I6DisclosureReconcileView {
  const discTotal = summarizeI6Disclosure(discRows.filter((r) => r.item !== 
    
}

function resolveAdjudicationCategory(noteItem: string, adjudicationNames: string[]): string | null {
  const hint = _str(noteItem)
  if (!hint) return null
  for (const name of adjudicationNames) {
    if (hint === name || hint.includes(name) || name.includes(hint)) return name
    const aliases = I6_ADJ_CATEGORY_ALIASES[name] || []
    if (aliases.some((a) => hint.includes(a) || a.includes(hint))) return name
  }
  return null
}

function allocateByUnadj(
  rows: I6AdjudicationRow[],
  ajeRem: number,
  rjeRem: number,
): I6AdjudicationRow[] {
  const base = rows.map((r) => Math.abs(_num(r.本期未审)))
  const sum = base.reduce((a, b) => a + b, 0)
  if (sum <= 0) {
    if (rows.length === 1) {
      return rows.map((r) => ({
        ...r,
        本期AJE: _round2(r.本期AJE + ajeRem),
        本期RJE: _round2(r.本期RJE + rjeRem),
      }))
    }
    return rows
  }
  let ajeLeft = ajeRem
  let rjeLeft = rjeRem
  return rows.map((r, i) => {
    const isLast = i === rows.length - 1
    const ajeAdd = isLast ? ajeLeft : _round2(ajeRem * base[i] / sum)
    const rjeAdd = isLast ? rjeLeft : _round2(rjeRem * base[i] / sum)
    ajeLeft = _round2(ajeLeft - ajeAdd)
    rjeLeft = _round2(rjeLeft - rjeAdd)
    return {
      ...r,
      本期AJE: _round2(r.本期AJE + ajeAdd),
      本期RJE: _round2(r.本期RJE + rjeAdd),
    }
  })
}

/** 从 I6-3 分录行汇总 6602 净额并写入 I6-1 各行 AJE/RJE */
export function applyAjeFromI63(
  rows: I6AdjudicationRow[],
  adjRows: any[],
): {
  rows: I6AdjudicationRow[]
  applied: number
  approx: boolean
  totalAje: number
  totalRje: number
  matchedByName: number
} {
  let totalAje = 0
  let totalRje = 0
  const namedAje = new Map<string, number>()
  const namedRje = new Map<string, number>()
  const adjudicationNames = rows.filter((r) => r.类别 !== 
     />
      </div>
    </div>

    <I6CutoffCrossCheck :summary=
     ? legacyItem : null)
    const legacyParsed = legacyRaw ? safeParse(legacyRaw) : []
    if (legacyParsed.length > 0) {
      storedRows.value = migrateLegacyRows(legacyParsed)
      _persist()
      return
    }
    storedRows.value = makeDefaultRows()
  }

  watch(allResponses, () => _load(), { immediate: true })

  // ─── Computed: 审定总额（用于占比计算）─────────────────────────────────────

  const totalAuditedAmount = computed(() => {
    return calcSubtotal(storedRows.value.map((r) => {
      const unadj = calcMonthlyTotal(r.months)
      return calcAuditedAmount(unadj, r.aje, r.rje)
    }))
  })

  // ─── Computed: 完整行（含公式列）───────────────────────────────────────────

  const rows: ComputedRef<I6DetailRow[]> = computed(() => {
    return storedRows.value.map((stored) => {
      const unadjTotal = calcMonthlyTotal(stored.months)
      const auditedAmount = calcAuditedAmount(unadjTotal, stored.aje, stored.rje)
      const priorAudited = calcAuditedAmount(stored.priorUnadj, stored.priorAje, stored.priorRje)
      const ratio = totalAuditedAmount.value === 0
        ? null
        : (auditedAmount / totalAuditedAmount.value) * 100
      const anomalyIndices = detectAnomalyMonthsForRow(stored.months)

      return {
        ...stored,
        unadjTotal,
        auditedAmount,
        ratio,
        priorAudited,
        anomalyHighlight: anomalyIndices.length > 0,
      }
    })
  })

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const totalRow: ComputedRef<I6DetailTotalRow> = computed(() => {
    const all = storedRows.value
    const monthTotals = new Array(12).fill(0)
    let ajeTotal = 0
    let rjeTotal = 0
    let priorUnadjTotal = 0
    let priorAjeTotal = 0
    let priorRjeTotal = 0
    let individualTotal = 0
    let consolidatedTotal = 0

    for (const r of all) {
      for (let i = 0; i < 12; i++) {
        monthTotals[i] += parseNum(r.months[i])
      }
      ajeTotal += parseNum(r.aje)
      rjeTotal += parseNum(r.rje)
      priorUnadjTotal += parseNum(r.priorUnadj)
      priorAjeTotal += parseNum(r.priorAje)
      priorRjeTotal += parseNum(r.priorRje)
      individualTotal += parseNum(r.individualReclass)
      consolidatedTotal += parseNum(r.consolidatedReclass)
    }

    const unadjTotal = calcMonthlyTotal(monthTotals)
    const auditedAmount = calcAuditedAmount(unadjTotal, ajeTotal, rjeTotal)
    const priorAudited = calcAuditedAmount(priorUnadjTotal, priorAjeTotal, priorRjeTotal)

    return {
      months: monthTotals,
      unadjTotal,
      aje: ajeTotal,
      rje: rjeTotal,
      auditedAmount,
      priorUnadj: priorUnadjTotal,
      priorAje: priorAjeTotal,
      priorRje: priorRjeTotal,
      priorAudited,
      individualReclass: individualTotal,
      consolidatedReclass: consolidatedTotal,
    }
  })

  // ─── Computed: 月度合计数组（12个月，供交叉校验用）─────────────────────────

  const monthlyTotals: ComputedRef<number[]> = computed(() => totalRow.value.months)

  /** 各月比例行：各月合计 / 全年审定合计 × 100（%） */
  const monthlyRatios: ComputedRef<(number | null)[]> = computed(() => {
    const annual = totalRow.value.auditedAmount
    if (annual === 0) return new Array(12).fill(null)
    return totalRow.value.months.map((m) => (m / annual) * 100)
  })

  /** 与 I6-1 审定表合计勾稽（允许 ±0.01） */
  const adjudicationCrossCheck = computed(() => {
    const detailAudited = totalRow.value.auditedAmount
    const adjItem = allResponses.value.get(
     as const,
    }))

  const totals = summarizeI6Disclosure(rows.filter((r) => r.item !== 
     as const,
  width: 100,
}))

/** 汇总/辅助列定义 */
export const SUMMARY_COLUMNS: I6DetailColumnDef[] = [
  { key: 
     open>
      <summary>编制提示（对齐 Excel 研发费用调整分录汇总表 I6-3）</summary>
      <div class=
     open>
      <summary>编制说明</summary>
      <ol>
        <li>对齐源表「附注披露（上市公司）」：项目 | 本期发生额 | 上期发生额。</li>
        <li>公式：SUMIF(I6-2.类别, 项目, 本期审定/上期审定)。</li>
        <li>同步附注写入 note_template §五、66「研发费用（按费用性质列示）」。</li>
        <li>可按需增行说明增减变动因素（源表蓝色提示行）。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang=
     open>
      <summary>编制说明</summary>
      <ol>
        <li>对齐源表「附注披露（国有企业）」：项目 | 本期发生额 | 上期发生额。</li>
        <li>数据自 I6-2 SUMIF 或 I6-1 审定引用，合计须与审定表一致。</li>
        <li>同步附注写入 note_template §八、67「研发费用」。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang=
     open>
      <summary>编制说明</summary>
      <ol>
        <li>类别行数据引用 I6-2 明细（未审/AJE/RJE/审定），公式：审定=未审+AJE+RJE。</li>
        <li>合计行为各类别加总；TB数据行为试算表6602未审发生额；差异=合计本期审定−TB数据。</li>
        <li>回写TB后发布 <code>substantive:adjudicated</code>，驱动附注披露表自动刷新。</li>
        <li>附注同步目标：上市 §五、66 / 国企 §八、67「研发费用（按费用性质列示）」。</li>
        <li>「带入调整」：从集中登记按科目 6602 拉取调整分录，逐笔分配到各费用类别的本期 AJE/RJE，带入后审定数自动更新并联动附注。</li>
      </ol>
    </details>

    <AdjudicationBringInDialog
      v-model=
     { detail: { expense: number, total: number } }
 *
 * 科目方向：
 * - 6602 研发费用（借方/损益类）：取发生额非余额
 * - 净发生额 = 借方发生 - 贷方发生（借方=费用增加，贷方=冲回/结转）
 *
 * Spec: .kiro/specs/i6-research-development-expense/
 * Task: 3.2
 * Requirements: 3.1-3.5 (月度明细), 4.1-4.7 (I6↔I2联动), 5.1-5.4 (截止测试)
 */
import { computed, ref, watch, onScopeDispose, type ComputedRef, type Ref } from 
     || raw?.isTotal || raw?.isSubtotal) continue

    const prior = _num(raw?.上期审定)
    const current = _num(raw?.本期审定)
    const existing = map.get(item) || { current: 0, prior: 0 }
    existing.current += current
    existing.prior += prior
    map.set(item, existing)
  }

  let idx = 0
  return Array.from(map.entries()).map(([item, amounts]) =>
    emptyI6DisclosureRow({
      rowId: `i6adj-auto-${idx++}`,
      item,
      currentAmount: _round2(amounts.current),
      priorAmount: _round2(amounts.prior),
      isAutoFilled: true,
    }),
  )
}

export function mergeAutoFillPreserveManual(
  existing: I6DisclosureRow[],
  autoRows: I6DisclosureRow[],
): I6DisclosureRow[] {
  const manualByItem = new Map(
    existing.filter((r) => !r.isAutoFilled && r.item).map((r) => [r.item, r]),
  )
  const autoByItem = new Map(autoRows.filter((r) => r.item).map((r) => [r.item, r]))
  const allItems = new Set([...manualByItem.keys(), ...autoByItem.keys()])

  const merged: I6DisclosureRow[] = []
  for (const item of allItems) {
    const manual = manualByItem.get(item)
    if (manual) {
      merged.push({ ...manual, isAutoFilled: false })
      continue
    }
    const auto = autoByItem.get(item)
    if (auto) merged.push({ ...auto, isAutoFilled: true })
  }

  for (const r of existing) {
    if (!r.item && !merged.some((m) => m.rowId === r.rowId)) {
      merged.push(r)
    }
  }

  return merged.length ? merged : autoRows
}

export interface I6ReconcileItemDiff {
  item: string
  disclosureAmount: number
  referenceAmount: number
  diff: number
}

export interface I6DisclosureReconcileView {
  vsAdj: {
    disclosureTotal: number
    adjudicatedTotal: number
    diff: number
    matched: boolean
    hasBoth: boolean
  }
  vsDetail: {
    disclosureTotal: number
    detailTotal: number
    diff: number
    matched: boolean
    hasBoth: boolean
  } | null
  itemDiffs: I6ReconcileItemDiff[]
  headline: string
  severity: 
     }
    const result = applyAjeToI62Detail(storedRows.value, source)
    storedRows.value = result.rows as I6DetailStoredRow[]
    _persist()
    if (!result.applied && Math.abs(result.totalAje) < 0.005 && Math.abs(result.totalRje) < 0.005) {
      return { ok: false, message: 
     }
    }
    return {
      ok: true,
      approx: result.approx,
      message: result.approx
        ? `已同步 AJE ${result.totalAje} / RJE ${result.totalRje}（含近似分摊，请复核附注项目）`
        : `已同步 AJE ${result.totalAje} / RJE ${result.totalRje}`,
    }
  }

  /** 将 I6-2 明细 AJE/RJE 推送为 I6-3 平衡分录 */
  function pushAjeToI63(): { ok: boolean; message: string; added: number } {
    if (readonly.value) return { ok: false, message: 
     }
  })

  const summary: ComputedRef<I6TargetedSummary> = computed(() =>
    summarizeI6Targeted(
      rows.value,
      sampleMeta.value.populationAmount,
      sampleMeta.value.populationCreditAmount,
    ),
  )

  const coverageLow = computed(() =>
    summary.value.coverageRate != null
    && summary.value.coverageRate < sampleMeta.value.coverageThreshold
    && summary.value.periodTotal > 0,
  )

  const coverageLabel = computed(() => formatLayeredCoverageLabel(summary.value))
  const creditCoverageLabel = computed(() => formatCoverageLabel(summary.value.creditCoverageRate))
  const coverageFooter = computed(() =>
    buildI6CoverageFooter(summary.value, sampleMeta.value.populationCreditAmount),
  )

  const coverageTagType = computed(() => {
    if (summary.value.coverageRate == null) return 
     },
])

// ─── 进度计算 ─────────────────────────────────────────────────────────────────
const totalCount = computed(() => allSheets.value.length)
const completedCount = computed(() => allSheets.value.filter(r => calcSheetProgress(r.prefix, 3) >= 100).length)
const progressPercent = computed(() => {
  if (totalCount.value === 0) return 0
  const avg = allSheets.value.reduce((sum, r) => sum + calcSheetProgress(r.prefix, 3), 0) / totalCount.value
  return Math.round(avg)
})

// ─── 底稿架构泳道（GtBArchitectureTree 数据源） ───────────────────────────────
const COMPONENT_TYPE_MAP: Record<string, string> = {
  I6A: 
     接收）
   * - total: 研发总额（费用化 + 资本化）
   * - isBalanced: VR-I6-01 校验结果（允许±0.01精度）
   *
   * Req 4.4: VR-I6-01校验: I6费用化金额 + I2资本化金额 = 研发总额
   * Req 4.5: 校验失败时红色警告
    !Q19 审定合计）。
 */
export function extractI6PeriodMovement(raw: unknown): I6PeriodMovement {
  const rows = _parseI62Rows(raw)
  let auditedTotal = 0
  for (const r of rows) {
    const cat = _str(r?.category).trim()
    if (!cat || cat === 
    )

  const totals = computed(() => summarizeI6Disclosure(rows.value.filter((r) => r.item !== 
    )

const {
  rows,
  sampleMeta,
  riskFocus,
  auditNote,
  auditConclusion,
  summary,
  coverageLow,
  coverageLabel,
  creditCoverageLabel,
  coverageFooter,
  coverageTagType,
  linkedPeriod,
  adjDrafts,
  pushableAdjDrafts,
  i62ProjectNames,
  projectConsistency,
  addRow,
  removeRow,
  updateRow,
  fillFromSampledVouchers,
  linkProjectsFromI62,
  setPopulationAmount,
  syncPopulationFromI62,
  syncSpecificAmount,
  appendAdjDraftsToNote,
  pushAdjDraftsToI63,
  fillConclusionDraft,
  persistAll,
  saveNote,
  saveConclusion,
  saveRiskFocus,
} = useI6TargetedCheck(allResponsesRef, {
  onSave: (itemId, value) => emit(
    )
        .reduce((s: number, r: any) => s + parseNum(r.本期审定 ?? r.auditedAmount), 0)
      const diff = detailAudited - adjudicationTotal
      return {
        hasData: adjudicationTotal !== 0 || detailAudited !== 0,
        detailAudited,
        adjudicationTotal,
        diff,
        isBalanced: Math.abs(diff) <= 0.01,
      }
    } catch {
      return { hasData: false, detailAudited, adjudicationTotal: 0, diff: 0, isBalanced: true }
    }
  })

  /** 与 TB 6602 未审发生额勾稽 */
  const tbCrossCheck = computed(() => {
    const tbNet = tbData?.value?.unadjusted6602 ?? 0
    const detailUnadj = totalRow.value.unadjTotal
    const diff = detailUnadj - tbNet
    return {
      hasData: Math.abs(tbNet) > 0.005 || Math.abs(detailUnadj) > 0.005,
      tbNet,
      detailUnadj,
      diff,
      isBalanced: Math.abs(diff) <= 0.01,
    }
  })

  /** 与 I6-3 调整分录 AJE/RJE 勾稽 */
  const i63CrossCheck = computed(() => {
    const item = allResponses.value.get(I63_ROWS_KEY)
    const raw = item?.remark
    let adjRows: any[] = []
    try { adjRows = raw ? JSON.parse(raw) : [] } catch { adjRows = [] }
    if (!Array.isArray(adjRows) || !adjRows.length) {
      return { hasData: false, isBalanced: true, detailAje: totalRow.value.aje, detailRje: totalRow.value.rje, i63Aje: 0, i63Rje: 0, diffAje: 0, diffRje: 0 }
    }
    const nets = aggregateI63Nets(adjRows)
    const diffAje = totalRow.value.aje - nets.ajeNet
    const diffRje = totalRow.value.rje - nets.rjeNet
    return {
      hasData: true,
      isBalanced: Math.abs(diffAje) <= 0.01 && Math.abs(diffRje) <= 0.01,
      detailAje: totalRow.value.aje,
      detailRje: totalRow.value.rje,
      i63Aje: nets.ajeNet,
      i63Rje: nets.rjeNet,
      diffAje,
      diffRje,
    }
  })

  function _parseI63Rows(): any[] {
    const item = allResponses.value.get(I63_ROWS_KEY)
    const raw = item?.remark
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }

  /** 从 I6-3 同步 AJE/RJE 至明细行 */
  function syncAjeFromI63(adjRows?: any[]): {
    ok: boolean
    message: string
    approx?: boolean
  } {
    if (readonly.value) return { ok: false, message: 
    )
      .reduce((s, r) => s + _num(r.本期审定 ?? r.audited), 0),
  )

  const vsAdjDiff = _round2(discTotal - adjTotal)
  const vsDetailDiff = detailRows.length ? _round2(discTotal - detailTotal) : 0
  const vsAdj = {
    disclosureTotal: discTotal,
    adjudicatedTotal: adjTotal,
    diff: vsAdjDiff,
    matched: Math.abs(vsAdjDiff) <= 0.01 || !(Math.abs(discTotal) > 0.005 && Math.abs(adjTotal) > 0.005),
    hasBoth: Math.abs(discTotal) > 0.005 && Math.abs(adjTotal) > 0.005,
  }
  const vsDetail = detailRows.length
    ? {
        disclosureTotal: discTotal,
        detailTotal,
        diff: vsDetailDiff,
        matched: Math.abs(vsDetailDiff) <= 0.01,
        hasBoth: Math.abs(discTotal) > 0.005 && Math.abs(detailTotal) > 0.005,
      }
    : null

  const refMap = new Map<string, number>()
  for (const r of detailAuto) {
    if (r.item) refMap.set(r.item, _round2((refMap.get(r.item) || 0) + r.currentAmount))
  }
  const itemDiffs: I6ReconcileItemDiff[] = []
  for (const row of discRows) {
    if (!row.item || row.item === 
    )
      return
    }

    // 先保存明细（普通保存，不写 TB）
    _persist()
    const auditedTotal = totalRow.value.本期审定
    options.onSave?.(`${ITEM_PREFIX}-audited-total`, auditedTotal)

    publishing.value = true
    try {
      const resp: any = await api.post(
        `/api/workpapers/${options.wpId.value}/audit-determination/publish-to-tb`,
        {
          // sheet 名固定含审定表子码 I6-1，后端 extract_determination_wp_code 据此解出 I6-1
          sheet_name: 
    )
    .map((r) => ({ ...r, 本期AJE: 0, 本期RJE: 0 }))
  let matchedByName = 0
  let ajeNamed = 0
  let rjeNamed = 0

  for (const row of next) {
    const aje = namedAje.get(row.类别)
    if (aje != null && Math.abs(aje) > 0.005) {
      row.本期AJE = aje
      ajeNamed = _round2(ajeNamed + aje)
      matchedByName++
    }
    const rje = namedRje.get(row.类别)
    if (rje != null && Math.abs(rje) > 0.005) {
      row.本期RJE = rje
      rjeNamed = _round2(rjeNamed + rje)
      matchedByName++
    }
  }

  const ajeRem = _round2(totalAje - ajeNamed)
  const rjeRem = _round2(totalRje - rjeNamed)
  let approx = false
  let applied = matchedByName

  if (Math.abs(ajeRem) > 0.005 || Math.abs(rjeRem) > 0.005) {
    approx = true
    const allocated = allocateByUnadj(next, ajeRem, rjeRem)
    return {
      rows: allocated,
      applied: applied || allocated.length,
      approx,
      totalAje,
      totalRje,
      matchedByName,
    }
  }

  return { rows: next, applied, approx, totalAje, totalRje, matchedByName }
}

/** 构建 I6-1 回写用的 adjustments 数组 */
export function buildI63WritebackAdjustments(
  adjudicationRows: I6AdjudicationRow[],
): Array<{ 类别: string; AJE: number; RJE: number }> {
  return adjudicationRows
    .filter((r) => r.类别 && r.类别 !== 
    )
    .map((r) => ({ 类别: r.类别, AJE: _num(r.本期AJE), RJE: _num(r.本期RJE) }))
}

export interface I62DetailAjeRow {
  id: string
  category: string
  expenseNature?: string
  aje: number
  rje: number
  priorUnadj?: number
}

function resolveDetailCategory(
  hint: string,
  detailRows: Array<{ category: string; expenseNature?: string }>,
): string | null {
  const h = _str(hint)
  if (!h) return null
  for (const r of detailRows) {
    const cat = _str(r.expenseNature || r.category)
    if (!cat) continue
    if (h === cat || h.includes(cat) || cat.includes(h)) return cat
    for (const [, aliases] of Object.entries(I6_ADJ_CATEGORY_ALIASES)) {
      const hitAlias = aliases.some((a) => cat.includes(a) || a.includes(cat))
      if (hitAlias && (aliases.some((a) => h.includes(a)) || h.includes(cat))) return cat
    }
  }
  for (const [adjName, aliases] of Object.entries(I6_ADJ_CATEGORY_ALIASES)) {
    if (!h.includes(adjName) && !aliases.some((a) => h.includes(a))) continue
    for (const r of detailRows) {
      const cat = _str(r.expenseNature || r.category)
      if (aliases.some((a) => cat.includes(a) || a.includes(cat))) return cat
    }
  }
  return null
}

/** 从 I6-3 分录汇总 6602 净额并写入 I6-2 各行 AJE/RJE */
export function applyAjeToI62Detail<T extends I62DetailAjeRow>(
  detailRows: T[],
  adjRows: any[],
): {
  rows: T[]
  applied: number
  approx: boolean
  totalAje: number
  totalRje: number
  matchedByName: number
} {
  let totalAje = 0
  let totalRje = 0
  const namedAje = new Map<string, number>()
  const namedRje = new Map<string, number>()

  for (const line of adjRows || []) {
    const code = _str(line?.accountCode)
    const name = _str(line?.accountName)
    if (!isI6ExpenseAccount(code, name)) continue
    const debit = _num(line?.debitAmount ?? line?.debit)
    const credit = _num(line?.creditAmount ?? line?.credit)
    const net = _round2(debit - credit)
    const cat = categoryFromLegacy(line)
    const et = entryTypeFromCategory(cat)
    const matchKey = resolveDetailCategory(
      _str(line?.noteItem || line?.expenseCategory || line?.remark),
      detailRows,
    )
    if (et === 
    )
    const raw = resp?.remark
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) return []
      return parsed.map((r: any) => {
        if (Array.isArray(r.months)) {
          const m = r.months
          return {
            category: r.category ?? r.name ?? r.projectName,
            month1: _getNum(m[0]), month2: _getNum(m[1]), month3: _getNum(m[2]),
            month4: _getNum(m[3]), month5: _getNum(m[4]), month6: _getNum(m[5]),
            month7: _getNum(m[6]), month8: _getNum(m[7]), month9: _getNum(m[8]),
            month10: _getNum(m[9]), month11: _getNum(m[10]), month12: _getNum(m[11]),
            total: _getNum(r.unadjTotal ?? r.total ?? calcMonthlyTotal(m)),
          }
        }
        return r as I6DetailRowRaw
      })
    } catch {
      return []
    }
  })

  // ─── 解析 I6-5 截止测试行（账→单据）────────────────────────────────────

  const cutoffForwardRows = computed<I6CutoffRowRaw[]>(() => {
    const resp = allResponses.value.get(
    )
    const result = applyAjeFromI63(dataRows, source)
    for (const updated of result.rows) {
      const row = rows.value.find((r) => r.类别 === updated.类别)
      if (row) {
        row.本期AJE = updated.本期AJE
        row.本期RJE = updated.本期RJE
        _recalcRow(row)
      }
    }
    isChanged.value = true
    _persist()
    if (!result.applied && Math.abs(result.totalAje) < 0.005 && Math.abs(result.totalRje) < 0.005) {
      ElMessage.info(
    )
    return safeParseRows<I6CutoffRowRaw>(resp?.remark)
  })

  // ═══ detailMonthlyTotals: I6-2 月度聚合（12个月合计）═══════════════════

  /**
   * 从 I6-2 明细表聚合12个月合计：
   * - 对每月列进行 SUM（所有行的同一月份列相加）
   * - 结果为 12 元素数组 [1月合计, 2月合计, ..., 12月合计]
   *
   * 用途：
   * - 供 I6-1 审定表验证净发生额 ≈ SUM(12月)
   * - 供月度趋势图展示
   * - 供月度波动分析（±30% 异常标记）
   *
   * Req 3.3: 合计列=SUM(1月~12月)
   * Req 3.4: 底部合计行=各列SUM
   * Req 3.5: 合计行联动审定表净发生额
   */
  const detailMonthlyTotals: ComputedRef<number[]> = computed(() => {
    const monthlyTotals = new Array(12).fill(0) as number[]

    for (const row of detailRows.value) {
      monthlyTotals[0] += _getNum(row.month1)
      monthlyTotals[1] += _getNum(row.month2)
      monthlyTotals[2] += _getNum(row.month3)
      monthlyTotals[3] += _getNum(row.month4)
      monthlyTotals[4] += _getNum(row.month5)
      monthlyTotals[5] += _getNum(row.month6)
      monthlyTotals[6] += _getNum(row.month7)
      monthlyTotals[7] += _getNum(row.month8)
      monthlyTotals[8] += _getNum(row.month9)
      monthlyTotals[9] += _getNum(row.month10)
      monthlyTotals[10] += _getNum(row.month11)
      monthlyTotals[11] += _getNum(row.month12)
    }

    return monthlyTotals
  })

  // ─── I6 费用化金额合计（供 I2 联动校验）────────────────────────────────

  /**
   * I6 费用化金额合计 = SUM(12月) = 月度合计的总和
   * 即 I6 审定后净发生额（损益类取发生额）
   *
   * 优先从 I6-1 审定表取审定数（若有），fallback 到月度合计。
   */
  const i6ExpenseAmount = computed<number>(() => {
    // 优先从 I6-1 审定表取审定数
    const adjResp = allResponses.value.get(
    )
    }
    if (!completenessConc && !allocationConc && !i2Conc && !legacyDeductionNote) return null
    return {
      completenessConclusion: completenessConc,
      allocationConclusion: allocationConc,
      i2ConsistencyConclusion: i2Conc,
      legacyDeductionNote,
    }
  }

  function load() {
    const map = getMap()
    rows.value = _safeParseArray(map.get(STORAGE_ROWS)).map(normalizeI6TargetedRow)

    sampleMeta.value = normalizeI6TargetedSampleMeta(_parseObject(map.get(STORAGE_SAMPLE)))

    const riskRaw = _parseObject(map.get(STORAGE_RISK)) || _legacyRiskFocusRaw(map)
    riskFocus.value = normalizeI6TargetedRiskFocus(riskRaw)

    auditNote.value = _readText(map.get(STORAGE_NOTE)) || _readText(map.get(LEGACY_AUDIT_NOTE))
    auditConclusion.value = _readText(map.get(STORAGE_CONCLUSION))
      || _readText(map.get(LEGACY_OVERALL_CONCLUSION))

    if (!sampleMeta.value.populationManual) {
      const mv = extractI6PeriodMovement(map.get(I62_ROWS))
      if (mv.debitTotal > 0) sampleMeta.value.populationAmount = mv.debitTotal
    }
  }

  watch(() => {
    const m = getMap()
    return [
      m.get(STORAGE_ROWS),
      m.get(STORAGE_SAMPLE),
      m.get(STORAGE_RISK),
      m.get(STORAGE_NOTE),
      m.get(STORAGE_CONCLUSION),
      m.get(I62_ROWS),
      m.get(LEGACY_COMPLETE_PROJECT),
      m.get(LEGACY_SUPER_DEDUCTION_ROWS),
      m.get(LEGACY_OVERALL_CONCLUSION),
    ]
  }, () => load(), { immediate: true, deep: false })

  const linkedPeriod: ComputedRef<{
    debitTotal: number
    creditTotal: number
    originalTotal: number
    source: string
  }> = computed(() => {
    const mv = extractI6PeriodMovement(getMap().get(I62_ROWS))
    return mv.debitTotal > 0 ? mv : { debitTotal: 0, creditTotal: 0, originalTotal: 0, source: 
    )
  return emptyI6TargetedRow({
    voucherDate: _str(s.voucherDate),
    voucherNo: _str(s.voucherNo),
    businessDesc: _str(s.summary),
    counterpartAccount: _str(s.counterpartAccount),
    counterpartDetail: rawName,
    projectName,
    debitAmount: _num(s.debitAmount),
    creditAmount: _num(s.creditAmount),
    isSpecific,
    selectionReason: reason || (s.isHighValue ? 
    )
  }

  function _normalizeRow(raw: any, idx: number): I6AdjustmentRow {
    const category = categoryFromLegacy(raw) as I6AdjCategory
    const entryType = entryTypeFromCategory(category)
    const accountCode = resolveAccountCode(raw)
    const known = I6_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === accountCode)
    const debitAmount = parseAmt(raw.debitAmount ?? raw.debit)
    const creditAmount = parseAmt(raw.creditAmount ?? raw.credit)
    return {
      rowId: raw.rowId || generateRowId(),
      seq: idx + 1,
      description: String(raw.description ?? raw.summary ?? 
    )
}

export function mapSampledToI6TargetedRow(
  s: {
    voucherNo?: string
    voucherDate?: string
    summary?: string | null
    debitAmount?: string | number | null
    creditAmount?: string | number | null
    counterpartAccount?: string | null
    accountName?: string | null
    isHighValue?: boolean
    selectionReason?: string
    abnormal?: boolean
    remark?: string
  },
  catalog?: I62ProjectRef[],
): I6TargetedCheckRow {
  const reason = _str(s.selectionReason)
  const isSpecific = !!(s.isHighValue || reason)
  const rawName = _str(s.accountName)
  const matched = catalog?.length
    ? matchI62ProjectName(
      { projectName: rawName, businessDesc: _str(s.summary), accountName: rawName },
      catalog,
    )
    : null
  const projectName = matched?.projectName
    || (rawName && !/研发费用|6602/.test(rawName) ? rawName : 
    )
}

export function summarizeI6Targeted(
  rows: I6TargetedCheckRow[],
  periodDebitTotal: number,
  periodCreditTotal = 0,
): I6TargetedSummary {
  const sampleCount = rows.length
  const checkedDebitTotal = Math.round(rows.reduce((s, r) => s + _num(r.debitAmount), 0) * 100) / 100
  const checkedCreditTotal = Math.round(rows.reduce((s, r) => s + _num(r.creditAmount), 0) * 100) / 100
  const anomalyCount = rows.filter((r) => isAbnormalFlag(r.isAbnormal) || hasFailedCheck(r)).length
  const failCheckCount = rows.filter(hasFailedCheck).length
  const pendingCount = rows.filter((r) => !isRowChecksComplete(r)).length
  const completedCheckCount = rows.filter(isRowChecksComplete).length

  const specificRows = rows.filter((r) => r.isSpecific || !!r.selectionReason)
  const samplingRows = rows.filter((r) => !(r.isSpecific || !!r.selectionReason))
  const specificCount = specificRows.length
  const specificDebitTotal = Math.round(specificRows.reduce((s, r) => s + _num(r.debitAmount), 0) * 100) / 100
  const samplingDebitTotal = Math.round(samplingRows.reduce((s, r) => s + _num(r.debitAmount), 0) * 100) / 100

  let coverageRate: number | null = null
  let creditCoverageRate: number | null = null
  let specificCoverageRate: number | null = null
  let samplingCoverageRate: number | null = null
  if (periodDebitTotal > 0) {
    coverageRate = Math.round((checkedDebitTotal / periodDebitTotal) * 10000) / 100
    specificCoverageRate = Math.round((specificDebitTotal / periodDebitTotal) * 10000) / 100
    samplingCoverageRate = Math.round((samplingDebitTotal / periodDebitTotal) * 10000) / 100
  }
  if (periodCreditTotal > 0) {
    creditCoverageRate = Math.round((checkedCreditTotal / periodCreditTotal) * 10000) / 100
  }

  return {
    sampleCount,
    checkedDebitTotal,
    checkedCreditTotal,
    periodTotal: periodDebitTotal,
    coverageRate,
    creditCoverageRate,
    anomalyCount,
    failCheckCount,
    pendingCount,
    completedCheckCount,
    specificCount,
    specificDebitTotal,
    samplingDebitTotal,
    specificCoverageRate,
    samplingCoverageRate,
  }
}

export function formatCoverageLabel(rate: number | null): string {
  if (rate == null) return 
    ) continue

    const months = Array.isArray(raw?.months) ? raw.months : []
    const unadj = months.length ? calcMonthlyTotal(months) : _num(raw?.unadjTotal ?? raw?.col_n)
    const aje = _num(raw?.aje ?? raw?.col_o)
    const rje = _num(raw?.rje ?? raw?.col_p)
    const current = _num(raw?.auditedAmount ?? raw?.col_q) || calcAuditedAmount(unadj, aje, rje)

    const priorUnadj = _num(raw?.priorUnadj ?? raw?.col_t)
    const priorAje = _num(raw?.priorAje ?? raw?.col_u)
    const priorRje = _num(raw?.priorRje ?? raw?.col_v)
    const prior = _num(raw?.priorAudited ?? raw?.col_w)
      || calcAuditedAmount(priorUnadj, priorAje, priorRje)

    const existing = map.get(nature) || { current: 0, prior: 0 }
    existing.current += current
    existing.prior += prior
    map.set(nature, existing)
  }

  let idx = 0
  return Array.from(map.entries()).map(([item, amounts]) =>
    emptyI6DisclosureRow({
      rowId: `i6disc-auto-${idx++}`,
      item,
      currentAmount: _round2(amounts.current),
      priorAmount: _round2(amounts.prior),
      isAutoFilled: true,
    }),
  )
}

/** 从 I6-1 审定表行按项目类别(A列)聚合 */
export function aggregateI6AdjForDisclosure(adjRows: any[]): I6DisclosureRow[] {
  const map = new Map<string, { current: number; prior: number }>()

  for (const raw of adjRows) {
    const item = String(raw?.类别 ?? raw?.项目 ?? raw?.category ?? 
    ) {
      _expectedResearchTotal.value = _getNum(expectedResp.remark)
    }
  }

  watch(allResponses, () => {
    _hydrateLinkageFromResponses()
  }, { immediate: true, deep: true })

  // ═══ i2LinkageStatus: I6↔I2 校验状态（VR-I6-01）════════════════════════

  /**
   * I6↔I2 联动校验状态：
   * - capitalized: I2 资本化金额（从 EventBus 
    ) {
      totalRje = _round2(totalRje + net)
      if (matchKey) namedRje.set(matchKey, _round2((namedRje.get(matchKey) || 0) + net))
    } else {
      totalAje = _round2(totalAje + net)
      if (matchKey) namedAje.set(matchKey, _round2((namedAje.get(matchKey) || 0) + net))
    }
  }

  if ((Math.abs(totalAje) < 0.005 && Math.abs(totalRje) < 0.005) || !detailRows.length) {
    return { rows: detailRows, applied: 0, approx: false, totalAje, totalRje, matchedByName: 0 }
  }

  const next = detailRows.map((r) => ({ ...r, aje: 0, rje: 0 }))
  let matchedByName = 0
  let ajeNamed = 0
  let rjeNamed = 0

  for (const row of next) {
    const key = _str(row.expenseNature || row.category)
    const aje = namedAje.get(key)
    if (aje != null && Math.abs(aje) > 0.005) {
      row.aje = aje
      ajeNamed = _round2(ajeNamed + aje)
      matchedByName++
    }
    const rje = namedRje.get(key)
    if (rje != null && Math.abs(rje) > 0.005) {
      row.rje = rje
      rjeNamed = _round2(rjeNamed + rje)
      matchedByName++
    }
  }

  const ajeRem = _round2(totalAje - ajeNamed)
  const rjeRem = _round2(totalRje - rjeNamed)
  if (Math.abs(ajeRem) > 0.005 || Math.abs(rjeRem) > 0.005) {
    const base = next.map((r) => Math.abs(_num(r.priorUnadj)))
    const sum = base.reduce((a, b) => a + b, 0) || next.reduce((s, r) => s + Math.abs(_num((r as any).unadjTotal)), 0)
    if (sum > 0) {
      let ajeLeft = ajeRem
      let rjeLeft = rjeRem
      for (let i = 0; i < next.length; i++) {
        const isLast = i === next.length - 1
        const weight = sum > 0 ? (Math.abs(_num(next[i].priorUnadj)) || 1) / sum : 1 / next.length
        const ajeAdd = isLast ? ajeLeft : _round2(ajeRem * weight)
        const rjeAdd = isLast ? rjeLeft : _round2(rjeRem * weight)
        next[i].aje = _round2(next[i].aje + ajeAdd)
        next[i].rje = _round2(next[i].rje + rjeAdd)
        ajeLeft = _round2(ajeLeft - ajeAdd)
        rjeLeft = _round2(rjeLeft - rjeAdd)
      }
    } else if (next.length === 1) {
      next[0].aje = _round2(next[0].aje + ajeRem)
      next[0].rje = _round2(next[0].rje + rjeRem)
    }
    return {
      rows: next,
      applied: matchedByName || next.length,
      approx: true,
      totalAje,
      totalRje,
      matchedByName,
    }
  }

  return { rows: next, applied: matchedByName, approx: false, totalAje, totalRje, matchedByName }
}

/** 汇总 I6-3 中 6602 行的 AJE/RJE 净额（用于与 I6-2 勾稽） */
export function aggregateI63Nets(adjRows: any[]): { ajeNet: number; rjeNet: number } {
  let ajeNet = 0
  let rjeNet = 0
  for (const line of adjRows || []) {
    if (!isI6ExpenseAccount(_str(line?.accountCode), _str(line?.accountName))) continue
    const net = _round2(_num(line?.debitAmount ?? line?.debit) - _num(line?.creditAmount ?? line?.credit))
    const et = entryTypeFromCategory(categoryFromLegacy(line))
    if (et === 
    )) as string
}

watch(() => props.allResponses, () => {
  auditNote.value = _str(NOTE_KEY)
  auditConclusion.value = _str(CONCLUSION_KEY)
}, { immediate: true })

const {
  rows,
  totalRow,
  monthlyTotals,
  monthlyRatios,
  anomalyMonths,
  adjudicationCrossCheck,
  tbCrossCheck,
  i63CrossCheck,
  monthLabels,
  updateCell,
  addRow,
  removeRow,
  replaceRows,
  applyI1AmortAmount,
  applyTbData,
  syncAjeFromI63,
  pushAjeToI63,
} = useI6Detail({
  allResponses: allResponsesRef,
  isReadonly: isReadonlyRef,
  tbData: tbDataRef,
  onSave: (itemId, value) => emit(
    )))

  const reconcileVsDetail = computed(() => {
    const detail = _readDetailRows()
    if (!detail.length) return null
    const auto = aggregateI6DetailForDisclosure(detail)
    const autoTotal = summarizeI6Disclosure(auto).currentAmount
    return Math.round((totals.value.currentAmount - autoTotal) * 100) / 100
  })

  const reconcileVsAdj = computed(() => {
    const summary = reconcileSummary.value
    if (!summary.vsAdj.hasBoth && Math.abs(summary.vsAdj.adjudicatedTotal) < 0.005) return null
    return summary.vsAdj.diff
  })

  const reconcileSummary = computed<I6DisclosureReconcileView>(() =>
    buildI6DisclosureReconcileView(rows.value, _readDetailRows(), _readAdjRows()),
  )

  function _standards(): readonly string[] | null | undefined {
    const s = options.applicableStandards
    if (!s) return undefined
    return typeof s === 
    )).currentAmount
  const detailAuto = aggregateI6DetailForDisclosure(detailRows)
  const detailTotal = summarizeI6Disclosure(detailAuto).currentAmount
  const adjTotal = _round2(
    adjRows
      .filter((r) => !r?.isTotal && !r?.isSubtotal && r?.项目 !== 
    ),
      debit: debitAmount,
      credit: creditAmount,
      sourceGroupId: raw.sourceGroupId ? String(raw.sourceGroupId) : undefined,
    }
  }

  function _toPersistShape(list: I6AdjustmentRow[]) {
    return list.map((r, i) => ({
      ...r,
      seq: i + 1,
      debit: r.debitAmount,
      credit: r.creditAmount,
      entryType: entryTypeFromCategory(String(r.category)),
    }))
  }

  function load(): void {
    const parsed = _getJson(ROWS_KEY)
    rows.value = Array.isArray(parsed) ? parsed.map((r, i) => _normalizeRow(r, i)) : []
    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(allResponses, () => load(), { immediate: true })

  const debitTotal = computed(() => rows.value.reduce((s, r) => s + r.debitAmount, 0))
  const creditTotal = computed(() => rows.value.reduce((s, r) => s + r.creditAmount, 0))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() => Math.abs(balanceDiff.value) < BALANCE_TOLERANCE)

  const groupBalanceIssues = computed(() => {
    const groups = new Map<string, { key: string; description: string; entryType: string; debit: number; credit: number }>()
    for (const r of rows.value) {
      const et = r.entryType || entryTypeFromCategory(String(r.category))
      const desc = String(r.description || 
    ),
  }
}

/** 检测月度异常：某月与前月变动率超阈值
 * 返回异常月份索引数组（0-based, 0=1月）
 */
function detectAnomalyMonthsForRow(months: number[]): number[] {
  const anomalies: number[] = []
  for (let i = 1; i < months.length; i++) {
    const prior = months[i - 1]
    const current = months[i]
    const rate = calcChangeRate(current, prior)
    if (rate !== null && Math.abs(rate) > ANOMALY_THRESHOLD) {
      anomalies.push(i)
    }
  }
  return anomalies
}

/**
 * 将 TB 6602 未审发生额分配至各行（写入 12 月列，与 I1-9 摊销回填一致）
 * 多行时按上期审定占比分配；上期为 0 时平均分配
 */
export function allocateTbNetToDetailRows(
  rows: I6DetailStoredRow[],
  tbNet: number,
): { rows: I6DetailStoredRow[]; allocated: number[] } {
  if (!rows.length || !Number.isFinite(tbNet)) return { rows, allocated: [] }

  const priorBases = rows.map((r) => Math.abs(calcAuditedAmount(r.priorUnadj, r.priorAje, r.priorRje)))
  const totalPrior = priorBases.reduce((a, b) => a + b, 0)
  const allocated = new Array<number>(rows.length).fill(0)

  if (rows.length === 1) {
    allocated[0] = Math.round(tbNet * 100) / 100
  } else if (totalPrior > 0.005) {
    let remain = tbNet
    for (let i = 0; i < rows.length; i++) {
      const isLast = i === rows.length - 1
      const amt = isLast
        ? Math.round(remain * 100) / 100
        : Math.round((tbNet * priorBases[i] / totalPrior) * 100) / 100
      allocated[i] = amt
      remain -= amt
    }
  } else {
    const avg = tbNet / rows.length
    let remain = tbNet
    for (let i = 0; i < rows.length; i++) {
      const isLast = i === rows.length - 1
      const amt = isLast ? Math.round(remain * 100) / 100 : Math.round(avg * 100) / 100
      allocated[i] = amt
      remain -= amt
    }
  }

  const next = rows.map((row, i) => {
    const months = new Array(12).fill(0)
    months[11] = allocated[i]
    return { ...row, months }
  })
  return { rows: next, allocated }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI6Detail(options: {
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
  isReadonly?: Ref<boolean>
  tbData?: Ref<{ unadjusted6602: number; audited6602?: number }>
}) {
  const { allResponses, onSave, isReadonly, tbData } = options
  const readonly = isReadonly ?? computed(() => false)

  // ─── Internal State ────────────────────────────────────────────────────────

  const storedRows = ref<I6DetailStoredRow[]>([])

  // ─── Load from allResponses ────────────────────────────────────────────────

  function _load(): void {
    const item = allResponses.value.get(STORAGE_KEY)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 
    ): Promise<string | null> {
    if (!wpId.value) return null
    isAiGenerating.value = true
    try {
      const t = totals.value
      const res = await api.post(`/api/workpapers/${wpId.value}/ai/generate-text`, {
        section: `i6-disclosure-${variant.value}-${section}`,
        prompt: `请为研发费用附注「${section}」生成披露文字描述`,
        context: [
          
    )} vs I6-1 审定 ${adjTotal.toLocaleString(
    ,
        accountCodes: [ACCOUNT_CODE_6602],
        auditedTotal,
        isOccurrence: true, // 损益类标记
      },
    }))
    // I6→I2 联动（费用化研发额 → I2 研发总额面板），改造须保留
    window.dispatchEvent(new CustomEvent(
    ,
      changeRateHighlight: false,
      isEditable: true,
      isTotal: false,
    }))
  }

  // ─── Computed: 带公式列的完整行 ───────────────────────────────────────────

  const computedRows: ComputedRef<I6AdjudicationRow[]> = computed(() => {
    return rows.value.map((row) => {
      const 上期审定 = calcAuditedAmount(row.上期未审, row.上期AJE, row.上期RJE)
      const 本期审定 = calcAuditedAmount(row.本期未审, row.本期AJE, row.本期RJE)
      const 变动额 = 本期审定 - 上期审定
      const 变动率 = calcI6ChangeRate(上期审定, 变动额)
      return {
        ...row,
        上期审定,
        本期审定,
        变动额,
        变动率,
        changeRateHighlight: 变动率 !== null && Math.abs(变动率 * 100) > CHANGE_RATE_THRESHOLD,
      }
    })
  })

  // ─── Computed: 合计行（totalRow）─────────────────────────────────────────

  const totalRow: ComputedRef<I6AdjudicationRow> = computed(() => {
    const detail = computedRows.value.filter((r) => !r.isTotal)
    const 上期未审 = calcSubtotal(detail.map((r) => r.上期未审))
    const 上期AJE = calcSubtotal(detail.map((r) => r.上期AJE))
    const 上期RJE = calcSubtotal(detail.map((r) => r.上期RJE))
    const 上期审定 = calcAuditedAmount(上期未审, 上期AJE, 上期RJE)
    const 本期未审 = calcSubtotal(detail.map((r) => r.本期未审))
    const 本期AJE = calcSubtotal(detail.map((r) => r.本期AJE))
    const 本期RJE = calcSubtotal(detail.map((r) => r.本期RJE))
    const 本期审定 = calcAuditedAmount(本期未审, 本期AJE, 本期RJE)
    const 变动额 = 本期审定 - 上期审定
    const 变动率 = calcI6ChangeRate(上期审定, 变动额)

    return {
      rowId: 
    ,
      changeRateHighlight: 变动率 !== null && Math.abs(变动率 * 100) > CHANGE_RATE_THRESHOLD,
      isEditable: false,
      isTotal: true,
    }
  })

  // ─── Computed: I2联动面板 ──────────────────────────────────────────────────

  const linkagePanel: ComputedRef<I6LinkagePanel> = computed(() => {
    const expenseI6 = totalRow.value.本期审定
    const cap = capitalizedI2.value
    const total = calcResearchTotal(expenseI6, cap)
    const expected = expectedResearchTotal.value || total
    const vr = validateVRI601(expenseI6, cap, expected)

    return {
      expenseI6,
      capitalizedI2: cap,
      researchTotal: total,
      vrI601Status: vr,
      i2DataReady: i2DataReady.value,
    }
  })

  // ─── Computed: TB差异 ─────────────────────────────────────────────────────

  /** TB未审发生额（科目6602） */
  const tbUnadjusted: ComputedRef<number> = computed(() => {
    return options.tbData.value.unadjusted6602
  })

  /** TB差异 = 审定合计(本期) - TB未审 */
  const tbDifference: ComputedRef<number> = computed(() => {
    return totalRow.value.本期审定 - tbUnadjusted.value
  })

  const highChangeRateRows = computed(() =>
    pickI6HighChangeRateRows(computedRows.value.filter((r) => r.isEditable !== false && !r.isTotal)),
  )

  const needsAuditNoteDraft = computed(() => highChangeRateRows.value.length > 0)

  function buildAuditNoteDraft(): string {
    return buildI6AdjudicationAuditNoteDraft(
      computedRows.value.filter((r) => !r.isTotal),
      { existingNote: auditNote.value },
    )
  }

  function applyAuditNoteDraft(): boolean {
    const draft = buildAuditNoteDraft()
    if (!draft) return false
    saveNote(draft)
    return true
  }

  /** 与明细表月度合计的交叉校验 */
  const detailCrossValidation: ComputedRef<string | null> = computed(() => {
    if (!options.crossSheet) return null
    const monthlyTotals = options.crossSheet.detailMonthlyTotals.value
    if (!monthlyTotals || monthlyTotals.length === 0) return null
    const detailTotal = calcSubtotal(monthlyTotals)
    const adjTotal = totalRow.value.本期审定
    if (Math.abs(detailTotal - adjTotal) > 0.01) {
      return `审定表合计 ${adjTotal.toFixed(2)} 与明细表月度合计 ${detailTotal.toFixed(2)} 不一致`
    }
    return null
  })

  // ─── Actions: 更新单元格 ──────────────────────────────────────────────────

  /**
   * 更新审定表某行某列值，自动重算公式列（上期审定/本期审定/变动额/变动率）
   */
  function updateCell(
    rowId: string,
    field: keyof I6AdjudicationRow,
    value: number | string,
  ): void {
    if (options.isReadonly?.value) return
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row || !row.isEditable) return

    ;(row as any)[field] = value

    // 自动重算公式列
    row.上期审定 = calcAuditedAmount(row.上期未审, row.上期AJE, row.上期RJE)
    row.本期审定 = calcAuditedAmount(row.本期未审, row.本期AJE, row.本期RJE)
    row.变动额 = row.本期审定 - row.上期审定
    row.变动率 = calcI6ChangeRate(row.上期审定, row.变动额)
    row.changeRateHighlight = row.变动率 !== null && Math.abs(row.变动率 * 100) > CHANGE_RATE_THRESHOLD

    isChanged.value = true
    _persist()
  }

  function _readDetailRows(): any[] {
    const raw = _getJson(
    ,
      changeRateHighlight: 变动率 !== null && Math.abs(变动率 * 100) > CHANGE_RATE_THRESHOLD,
      isEditable: raw.isEditable ?? true,
      isTotal: raw.isTotal ?? false,
    }
  }

  function _buildDefaultRows(): I6AdjudicationRow[] {
    return DEFAULT_CATEGORIES.map((cat) => ({
      rowId: `row-${cat}`,
      类别: cat,
      上期未审: 0,
      上期AJE: 0,
      上期RJE: 0,
      上期审定: 0,
      本期未审: 0,
      本期AJE: 0,
      本期RJE: 0,
      本期审定: 0,
      变动额: 0,
      变动率: null,
      备注: 
    ,
      },
    }))
  }

  // ─── Actions: 保存审定发生额（普通保存不写 TB，Req 1）────────────────────────

  /**
   * 保存审定发生额到 checklist_responses（普通保存动作，不写 TB）。
   *
   * spec: tb-writeback-explicit-publish-gate Task 13 / Req 1。
   * 此前 writeback 保存后**自动** PUT 旧端点回写 trial_balance(6602 发生额) → 违反 Req 1。
   * 现只保存 + emit（含 I6→I2 联动）；TB 回写收敛为用户显式确认动作（publishToTb）。
   */
  async function writeback(): Promise<void> {
    _persist()

    const auditedTotal = totalRow.value.本期审定
    // 持久化审定合计（独立item_id，供render策略回读seed + 跨session持久化）
    options.onSave?.(`${ITEM_PREFIX}-audited-total`, auditedTotal)

    _emitAdjudicated()
    isChanged.value = false
  }

  // ─── 显式发布到试算表（显式确认门，损益类发生额 6602）────────────────────────

  /**
   * 确认发布审定发生额到试算表（科目 6602 研发费用，**发生额 occurrence**）。
   *
   * spec: tb-writeback-explicit-publish-gate Task 13 / Req 2,6。
   * 二次确认（中文）→ 保存明细 → `POST /workpapers/{wpId}/audit-determination/publish-to-tb`
   * （审定表 sheet 名 I6-1 + writeback_rows 预算行 6602，amount_kind=
    ,
    }
  }

  function setPopulationAmount(amount: number, manual: boolean) {
    sampleMeta.value.populationAmount = amount
    sampleMeta.value.populationManual = manual
  }

  function syncPopulationFromI62(): { ok: boolean; message: string } {
    const mv = linkedPeriod.value
    if (!(mv.debitTotal > 0)) {
      return { ok: false, message: 
    ,
  })
}

export function defaultI6DisclosureRows(): I6DisclosureRow[] {
  return I6_DEFAULT_DISCLOSURE_CATEGORIES.map((name) =>
    emptyI6DisclosureRow({ item: name, isAutoFilled: false }),
  )
}

export function summarizeI6Disclosure(rows: I6DisclosureRow[]): I6DisclosureTotals {
  return {
    currentAmount: _round2(rows.reduce((s, r) => s + _num(r.currentAmount), 0)),
    priorAmount: _round2(rows.reduce((s, r) => s + _num(r.priorAmount), 0)),
  }
}

/** 从 I6-2 明细行按费用性质(X列) SUMIF 聚合 → 附注披露 */
export function aggregateI6DetailForDisclosure(detailRows: any[]): I6DisclosureRow[] {
  const map = new Map<string, { current: number; prior: number }>()

  for (const raw of detailRows) {
    const nature = resolveI6ExpenseNature(raw)
    if (!nature || nature === 
    ,
] as const

export type I6TargetedCheckMark = (typeof I6_4_CHECK_OPTIONS)[number]

export interface I6TargetedCheckRow {
  rowId: string
  /** 研发项目明细 */
  projectName: string
  voucherDate: string
  voucherNo: string
  businessDesc: string
  counterpartAccount: string
  counterpartDetail: string
  debitAmount: number
  creditAmount: number
  supportingDocs: string
  check1: I6TargetedCheckMark | string
  check2: I6TargetedCheckMark | string
  check3: I6TargetedCheckMark | string
  check4: I6TargetedCheckMark | string
  check5: I6TargetedCheckMark | string
  indexRef: string
  isAbnormal: string
  remark: string
  isSpecific: boolean
  selectionReason: string
}

export interface I6TargetedSampleMeta {
  populationCount: number
  populationAmount: number
  populationCreditAmount: number
  populationDesc: string
  populationManual: boolean
  testReasons: string[]
  specificSample: string
  specificAmount: number
  samplingPopulationDesc: string
  sampleSize: number
  sampleMethod: string
  sampleProcess: string
  coverageThreshold: number
}

/** 原段落型风险关注（兼容旧 I6-4 四维度检查） */
export interface I6TargetedRiskFocus {
  completeness: string
  allocation: string
  i2Consistency: string
  completenessConclusion: string
  allocationConclusion: string
  i2ConsistencyConclusion: string
  /** 旧版误入的加计扣除数据迁移提示 */
  legacyDeductionNote: string
}

export interface I6TargetedSummary {
  sampleCount: number
  checkedDebitTotal: number
  checkedCreditTotal: number
  periodTotal: number
  coverageRate: number | null
  creditCoverageRate: number | null
  anomalyCount: number
  failCheckCount: number
  pendingCount: number
  completedCheckCount: number
  specificCount: number
  specificDebitTotal: number
  samplingDebitTotal: number
  specificCoverageRate: number | null
  samplingCoverageRate: number | null
}

export interface I6PeriodMovement {
  /** 本期借方发生额代理：I6-2 审定合计 */
  debitTotal: number
  creditTotal: number
  originalTotal: number
  source: string
}

export interface I6CoverageFooter {
  checkedDebitTotal: number
  periodDebitTotal: number
  debitCoverageLabel: string
  layeredCoverageLabel: string
}

export interface I62ProjectRef {
  projectName: string
  auditedAmount: number
}

export function emptyI6TargetedRow(partial?: Partial<I6TargetedCheckRow>): I6TargetedCheckRow {
  return {
    rowId: partial?.rowId || `i64-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    projectName: 
    , () => {})

const {
  backwardRows, backwardCriteria, backwardBeforeRows, backwardAfterRows, backwardUnsortedRows,
  backwardCrossPeriodCount, backwardCrossPeriodAmount, amountMismatchCount, lagAnomalyCount,
  crossCheckSummary, priorPeriodCutoffDate, updateBackwardCriteria, addBackwardRow, removeBackwardRow,
  updateBackwardRow, loadFromAutoSampling, importExtractedVouchers, save: saveCutoff,
  syncCutoffDateFromProject, expandTestWindow, draftAjeFromCrossPeriod, persistCompletion,
  syncCriteriaToPeer, flushAutoSave,
} = useI6Cutoff({
  allResponses: toRef(props, 
    , () => {})

const {
  forwardRows,
  forwardCriteria,
  forwardBeforeRows,
  forwardAfterRows,
  forwardUnsortedRows,
  forwardCrossPeriodCount,
  forwardCrossPeriodAmount,
  amountMismatchCount,
  lagAnomalyCount,
  crossCheckSummary,
  priorPeriodCutoffDate,
  updateForwardCriteria,
  addForwardRow,
  removeForwardRow,
  updateForwardRow,
  loadFromAutoSampling,
  importExtractedVouchers,
  save: saveCutoff,
  syncCutoffDateFromProject,
  expandTestWindow,
  draftAjeFromCrossPeriod,
  persistCompletion,
  syncCriteriaToPeer,
  flushAutoSave,
} = useI6Cutoff({
  allResponses: toRef(props, 
    , changeRateHighlight: Math.abs(tbDifference.value) > 0.01,
    isEditable: false, isTotal: false, isControl: true,
  }
  return [...detail, total, tbRow, diffRow]
})

function onCellChange(row: I6AdjudicationRow, field: keyof I6AdjudicationRow, value: number): void {
  adj.updateCell(row.rowId, field, value)
}

function getRowClassName({ row }: { row: DisplayRow }): string {
  if (row.isTotal) return 
    , changeRateHighlight: false, isEditable: true, isTotal: false,
    }))

    if (force || !rows.value.some((r) => r.isEditable && (r.本期未审 || r.上期未审))) {
      rows.value = aggregated.map(_normalizeRow)
    } else {
      for (const agg of aggregated) {
        const row = rows.value.find((r) => r.类别 === agg.类别)
        if (row) {
          Object.assign(row, {
            上期未审: agg.上期未审, 上期AJE: agg.上期AJE, 上期RJE: agg.上期RJE,
            本期未审: agg.本期未审, 本期AJE: agg.本期AJE, 本期RJE: agg.本期RJE,
          })
          _recalcRow(row)
        } else {
          rows.value.push(_normalizeRow(agg))
        }
      }
    }

    isChanged.value = true
    _persist()
    ElMessage.success(`已从 I6-2 同步 ${categoryMap.size} 个类别`)
  }

  // ─── Actions: TB取数接入 ──────────────────────────────────────────────────

  /**
   * 接收TB未审发生额数据，写入行的 本期未审 字段
   * 如果只有1行，直接写入该行；多行按上期审定比例分配
   */
  function applyTbData(tbUnadjustedTotal: number): void {
    if (options.isReadonly?.value) return
    if (rows.value.length === 1) {
      rows.value[0].本期未审 = tbUnadjustedTotal
      _recalcRow(rows.value[0])
    } else if (rows.value.length > 1) {
      const totalPrior = calcSubtotal(rows.value.map((r) => r.上期审定))
      if (totalPrior > 0) {
        for (const row of rows.value) {
          const ratio = row.上期审定 / totalPrior
          row.本期未审 = Math.round(ratio * tbUnadjustedTotal * 100) / 100
          _recalcRow(row)
        }
      } else {
        // 上期全为0时平均分配
        const avg = tbUnadjustedTotal / rows.value.length
        for (const row of rows.value) {
          row.本期未审 = Math.round(avg * 100) / 100
          _recalcRow(row)
        }
      }
    }
    isChanged.value = true
    _persist()
  }

  /**
   * 接收 AJE/RJE 调整（来自 I6-3 调整分录表）
   * 按类别名称匹配写入对应行
   */
  function applyAdjustments(adjustments: { 类别: string; AJE: number; RJE: number }[]): void {
    if (options.isReadonly?.value) return
    for (const adj of adjustments) {
      const row = rows.value.find((r) => r.类别 === adj.类别)
      if (row) {
        row.本期AJE = adj.AJE
        row.本期RJE = adj.RJE
        _recalcRow(row)
      }
    }
    isChanged.value = true
    _persist()
  }

  /** 重算行公式列 */
  function _recalcRow(row: I6AdjudicationRow): void {
    row.上期审定 = calcAuditedAmount(row.上期未审, row.上期AJE, row.上期RJE)
    row.本期审定 = calcAuditedAmount(row.本期未审, row.本期AJE, row.本期RJE)
    row.变动额 = row.本期审定 - row.上期审定
    row.变动率 = calcI6ChangeRate(row.上期审定, row.变动额)
    row.changeRateHighlight = row.变动率 !== null && Math.abs(row.变动率 * 100) > CHANGE_RATE_THRESHOLD
  }

  // ─── Actions: I2 EventBus 联动 ────────────────────────────────────────────

  /**
   * 接收I2资本化金额更新（EventBus: development:capitalized-updated）
   */
  function onI2CapitalizedUpdate(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (detail && typeof detail.capitalizedAmount === 
    , itemId, value),
})

const totalRow = adj.totalRow
const linkagePanel = adj.linkagePanel
const tbUnadjusted = adj.tbUnadjusted
const tbDifference = adj.tbDifference
const detailCrossValidation = adj.detailCrossValidation

// ─── 从四表库带入未审数（消费 render 的 adjudication_prefill，按费用类别名匹配行） ───
//
// 🔴 改造前后端每次 render 都算并下发 `adjudication_prefill`，前端**零消费方**。
// 🔴 I6 是损益类：后端按 `mode=
    , onAdjustmentWriteback)
    })
  }

  // ─── Computed: 趋势折线图数据（ECharts）───────────────────────────────────

  const trendChartData: ComputedRef<I6TrendChartData> = computed(() => {
    const totalMonthly = totalRow.value.months
    const anomalyTotalIndices = detectAnomalyMonthsForRow(totalMonthly)

    const series: I6TrendChartData[
    , value),
  totalAudited: () => totalRow.value.本期审定,
})

const discVis = computed(() => resolveI6DisclosureVisibility(props.applicableStandards))

interface DisplayRow extends I6AdjudicationRow {
  isControl?: boolean
}

const displayRows = computed<DisplayRow[]>(() => {
  const detail = adj.rows.value
  const total = totalRow.value
  const tbRow: DisplayRow = {
    rowId: 
    , width: 150 },
]

/** 全部列定义（平铺） */
export const ALL_COLUMNS: I6DetailColumnDef[] = [
  ...FIXED_COLUMNS,
  ...MONTHLY_COLUMNS,
  ...SUMMARY_COLUMNS,
]

// ─── Helper Functions ────────────────────────────────────────────────────────

function safeParse(jsonStr: string | null | undefined): I6DetailStoredRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map(normalizeStoredRow)
  } catch {
    return []
  }
}

function makeDefaultRow(category: string, expenseNature?: string): I6DetailStoredRow {
  const nature = expenseNature || category
  return {
    id: `detail-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    category: category || nature,
    expenseNature: nature,
    months: new Array(12).fill(0),
    aje: 0,
    rje: 0,
    reconciliation: 
    , { minimumFractionDigits: 2 })}（${summary.value.specificCount} 笔）`,
    }
  }

  function fillFromSampledVouchers(samples: any[]): number {
    if (!Array.isArray(samples) || !samples.length) return 0
    const catalog = i62ProjectCatalog.value
    const existing = new Set(
      rows.value.map((r) => `${r.voucherDate}|${r.voucherNo}`).filter((k) => k !== 
    >
        <summary>编制提示</summary>
        <ul>
          <li>科目 <strong>6602 研发费用（损益类，借方）：取本期发生额，非期末余额</strong>；I6-1 期末审定取本期发生额（借方发生额 − 贷方发生额）</li>
          <li>推荐工作流：I6A 程序 → I6-2 明细(月度12列) → I6-4 针对性检查 → I6-5/I6-6 双向截止 → I6-3 调整回写 I6-1 → 附注披露</li>
          <li>I6↔I2 双向联动：<strong>费用化(I6) + 资本化(I2) = 研发总额（VR-I6-01）</strong>；未达资本化条件的研发支出费用化计入 I6</li>
          <li>双向截止：I6-5（账→单据）/ I6-6（单据→账），跨期项目红色高亮；差异汇入 I6-3</li>
          <li>审定发生额回写 TB(6602) 并驱动附注披露与利润表勾稽；各表填妥
    >
      <summary>编制提示</summary>
      <ul>
        <li>行维度：<strong>项目类别(A)</strong>供 I6-1 引用；<strong>费用性质(X)</strong>供附注 SUMIF</li>
        <li>同一费用性质可对应多行项目类别，附注披露按 X 列汇总</li>
        <li>本期未审合计 = SUM(1月~12月)；本期审定 = 未审 + AJE + RJE</li>
        <li>底部合计行应与 I6-1 审定表一致；各月比例 = 各月合计 / 全年审定 × 100%</li>
        <li>月度环比变动超 ±30% 红色标记，需在审计说明中解释</li>
        <li>无形资产摊销可点「从 I1-9 取摊销」自动回填</li>
        <li>AJE/RJE 可与 I6-3 双向联动：「从 I6-3 同步」或「推送至 I6-3」</li>
        <li>构成数据可推送至 I2-5「从 I6-2 带入构成」</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang=
    >
      <summary>编制提示（对齐 Excel I6-4）</summary>
      <ol>
        <li>先勾选测试原因并填第二节总体，再抽样本填入第三节；检查比例=样本借方÷本期发生额（联动 I6-2，总体为 0 显示 N/A）。</li>
        <li>核对 1~5 对应测试内容说明；选「×」时可写入调整建议或一键推送 I6-3（资本化/跨期类）。</li>
        <li>加计扣除测算不属于本表，请编制 N5-6-1 并与 I2 政策检查交叉核对。</li>
        <li>人员认定见 I2-9，工时检查见 I2-10；资本化划分见 I2-6。专项风险关注区可记载段落结论。</li>
      </ol>
    </details>

    <el-dialog
      v-model=
    >
      勾稽一致：披露 {{ fmtAmt(disc.reconcileSummary.value.vsAdj.disclosureTotal) }} = I6-1 审定 {{ fmtAmt(disc.reconcileSummary.value.vsAdj.adjudicatedTotal) }}
    </div>

    <el-card shadow=
    I6-adj-expected-total
    `明细审定合计 ${fmtAmount(adjudicationCrossCheck.detailAudited)} 与 I6-1 审定合计 ${fmtAmount(adjudicationCrossCheck.adjudicationTotal)} 不一致，差额 ${fmtAmount(adjudicationCrossCheck.diff)}`
    （**I6→I2 联动**，费用化研发额驱动 I2 研发总额面板）
   */
  function _emitAdjudicated(): void {
    const auditedTotal = totalRow.value.本期审定
    window.dispatchEvent(new CustomEvent(

============================================================
IC-13: footer 行信息
============================================================
  I6 明细表I6-2 R19 (footer 1):
    A19 = 合计
    B19 = =SUM(B9:B18)
    C19 = =SUM(C9:C18)
    D19 = =SUM(D9:D18)
    E19 = =SUM(E9:E18)
    F19 = =SUM(F9:F18)
    G19 = =SUM(G9:G18)
    H19 = =SUM(H9:H18)
    I19 = =SUM(I9:I18)
    J19 = =SUM(J9:J18)
    K19 = =SUM(K9:K18)
    L19 = =SUM(L9:L18)
    M19 = =SUM(M9:M18)
    N19 = =SUM(N9:N18)
    O19 = =SUM(O9:O18)
    P19 = =SUM(P9:P18)
    Q19 = =SUM(Q9:Q18)
    R19 = =SUM(R9:R18)
    S19 = =SUM(S9:S18)
    T19 = =SUM(T9:T18)
    U19 = =SUM(U9:U18)
    V19 = =SUM(V9:V18)
    W19 = =SUM(W9:W18)
    X19 = =SUM(X9:X18)
    Y19 = =SUM(Y9:Y18)
  I6 明细表I6-2 R20 (footer 2):
    A20 = 各月比例
    B20 = =IF($N$19=0,0,B19/$N$19)
    C20 = =IF($N$19=0,0,C19/$N$19)
    D20 = =IF($N$19=0,0,D19/$N$19)
    E20 = =IF($N$19=0,0,E19/$N$19)
    F20 = =IF($N$19=0,0,F19/$N$19)
    G20 = =IF($N$19=0,0,G19/$N$19)
    H20 = =IF($N$19=0,0,H19/$N$19)
    I20 = =IF($N$19=0,0,I19/$N$19)
    J20 = =IF($N$19=0,0,J19/$N$19)
    K20 = =IF($N$19=0,0,K19/$N$19)
    L20 = =IF($N$19=0,0,L19/$N$19)
    M20 = =IF($N$19=0,0,M19/$N$19)
    N20 = =IF($N$19=0,0,N19/$N$19)

  I3 明细表I3-2 R23 (footer):
    A23 = 合计
    E23 = =SUM(E14:E22)
    G23 = =SUM(G14:G22)
    I23 = =SUM(D23:E23)-G23
    J23 = =SUM(J14:J22)
    K23 = =SUM(K14:K22)
    L23 = =SUM(L14:L22)
    M23 = =D23+J23
    N23 = =E23+K23
    O23 = =G23+L23
    P23 = =M23+N23-O23
    Q23 = 合计
    R23 = =SUM(R14:R22)
    S23 = =SUM(S14:S22)
    T23 = =SUM(T14:T22)
    U23 = =SUM(U14:U22)
    V23 = =SUM(V14:V22)
    W23 = =SUM(W14:W22)
    X23 = =SUM(X14:X22)
    Y23 = =SUM(Y14:Y22)
    Z23 = =SUM(Z14:Z22)
    AA23 = =SUM(AA27:AA30)
    AB23 = =SUM(AB27:AB30)
    AC23 = =SUM(AC27:AC30)
    AD23 = =SUM(AD27:AD30)
  I3 明细表I3-2 R27-R30 验证：
    A27=None, B27=编制说明：, C27=None, D27=None
    A28=None, B28=1、在“备注”中注明非同一控制下企业合并情况。, C28=None, D28=None
    A29=None, B29=2、对于通过非同一控制下企业合并形成的商誉，应列示商誉的计算过程。, C29=None, D29=None
    A30=None, B30=None, C30=None, D30=None
  I3 max_row=29
```

## 裸 IF 计数口径澄清

初次用 `re.search`（每格最多算 1 次）得到 I1=202 等较低数字。
改用 `re.findall`（每格内每次 `IF()` 出现各算一次，含嵌套 IF）后：

| 册 | design 声明 | findall 现算 | 一致 |
|---|---|---|---|
| I1 | 321 | **321** | ✅ |
| I2 | 113 | **113** | ✅ |
| I3 | 63 | **63** | ✅ |
| I4 | 186 | **186** | ✅ |
| I5 | 49 | **49** | ✅ |
| I6 | 45 | **45** | ✅ |
| 总 | 777 | **777** | ✅ |

口径：`re.compile(r'(?<![A-Za-z0-9_.])IF\s*\(').findall(cell.value)`，
即裸 `IF(`（前面不接字母/数字/下划线/点，排除 `SUMIF`/`COUNTIF` 等），
嵌套 `IF(IF(…))` 算 2 次。这与 G7 的 `_BARE_IF_CALL` 正则一致。

## IC-6 位置化 site 差异分析

扫描命中 19 处，design 只列了位置化（需修的）8 处 + 族 A（安全的）12 处。
用形态口径区分：
- **族 A（安全）**：含 `Date.now()` + `Math.random()` 的有 11 处 → 不是缺陷
- **族 A'（纯下标）**：`useI3Disclosure.ts#L488 cgu-${i}` → 1 处 ✅
- **族 B（下标兜底）**：`useI3Disclosure.ts#L441/463/503` + `i1DisclosureEnhance.ts#L241` + `I3TabRecoverableTest.vue#L43` → 5 处 ✅
- **族 D（${added}）**：`useI3Disclosure.ts#L665/725` → 2 处 ✅
- site 合计 = 1+5+2 = **8** ✅

注意：`I3TabRecoverableTest.vue#L43` 是 `:key` 绑定用了 `rowId || idx`，扫描正则
匹配到 `fallback idx` 形态。design 里标的是 `#L686`（该行实际是 `String(r.rowId || cgu-${idx})`），
L43 是模板层 `:key` 绑定。两处都属族 B，无遗漏。

## IC-17 消费方计数

`I6-2-detail-rows` 消费方现算 10 个（含 I6 自己的 5 个内部文件）。
design 只列了 5 个**跨 entry** 消费方（排除了 I6 自己的文件）：
- `expenseWpI1AmortPull.ts` ✅
- `h1DepAllocCounterpartPull.ts` ✅（H1 pilot）
- `h8DepAllocCounterpartPull.ts` ✅
- `i1AmortAllocCounterpartPull.ts` ✅
- `useI2Analysis.ts` ✅

跨 entry 消费方 = 10 - 5（I6 自身的 useI6Adjudication/CrossSheet/Detail/Disclosure/TargetedCheck）= **5** ✅

`I2-2-rows` 跨 entry 消费方 = `useI1AdditionCheck.ts` **1 处** ✅
