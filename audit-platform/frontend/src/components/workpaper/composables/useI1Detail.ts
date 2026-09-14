/**
 * useI1Detail — I1-2 无形资产明细表（对齐 Excel 56 列宽表逻辑）
 *
 * Excel 横向三区块：原值 | 累计摊销 | 减值准备，每块均为
 *   未审数（期初/增加/减少/期末）→ 期初调整+账项调整 → 审定数
 * 右侧：期初/期末净值（未审+审定）+ 权属证明 + 抵押受限
 *
 * UI 仍按区段 Tab 拆分（宽表可读性），字段与公式对齐源表。
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import type { ChecklistItem } from './useI1FormData'
import {
  calcAssetEndBalance,
  calcContraEndBalance,
  calcNetValue,
  calcSubtotal,
} from './useI1FormulaEngine'

export const I1_DETAIL_CATEGORIES = [
  '土地使用权', '房屋使用权', '专利权', '非专利技术', '商标权',
  '著作权', '特许权', '软件', '探矿权/采矿权', '数据资源', '其他',
] as const

export const I1_COST_INCREASE_METHODS = [
  '购置', '内部研发', '企业合并增加', '其他增加',
] as const

export const I1_COST_DECREASE_METHODS = [
  '处置', '失效且终止确认的部分', '其他减少',
] as const

export interface I1DetailRow {
  rowId: string
  // 基础
  category: string
  name: string
  acquisitionDate: string
  usefulLifeMonths: number
  salvageRate: number
  amortizationMethod: string
  /** 寿命不确定 */
  indefiniteLife: 'Y' | 'N' | ''
  /** 尚未达到可使用状态 */
  notReadyForUse: 'Y' | 'N' | ''

  // ── 原值未审 ──
  costBegin: number
  costIncrease: number
  costIncreaseMethod: string
  costDecrease: number
  costDecreaseMethod: string
  costEnd: number
  // 原值调整 → 审定
  costBeginAdj: number
  costAdjInc: number
  costAdjDec: number
  auditedCostBegin: number
  auditedCostIncrease: number
  auditedCostDecrease: number
  auditedCostEnd: number

  // ── 摊销未审 ──
  accAmortBegin: number
  amortProvision: number
  amortOtherIncrease: number
  amortDisposal: number
  amortOtherDecrease: number
  accAmortEnd: number
  /** 兼容旧字段：= amortDisposal + amortOtherDecrease */
  amortTransferOut: number
  accAmortBeginAdj: number
  amortAdjInc: number
  amortAdjDec: number
  auditedAccAmortBegin: number
  auditedAmortIncrease: number
  auditedAmortDecrease: number
  auditedAccAmortEnd: number

  // ── 减值未审 ──
  impairmentBegin: number
  impairmentProvision: number
  impairOtherIncrease: number
  impairDisposal: number
  impairOtherDecrease: number
  impairmentEnd: number
  /** 兼容：处置结转（非转回） */
  impairmentReversal: number
  impairmentBeginAdj: number
  impairAdjInc: number
  impairAdjDec: number
  auditedImpairmentBegin: number
  auditedImpairIncrease: number
  auditedImpairDecrease: number
  auditedImpairmentEnd: number

  // ── 净值 ──
  netBegin: number
  netValue: number
  auditedNetBegin: number
  auditedNetEnd: number

  // ── 合规 ──
  hasTitleEvidence: 'Y' | 'N' | ''
  mortgageRestricted: 'Y' | 'N' | ''
}

export type I1DetailTab = 'basic' | 'cost' | 'amort' | 'impairment' | 'net'

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

const ITEM_ID_ROWS = 'I1-2-rows'
const DEFAULT_AMORTIZATION_METHOD = '直线法'

function _n(v: any): number {
  const x = Number(v)
  return Number.isFinite(x) ? x : 0
}

function _yn(v: any): 'Y' | 'N' | '' {
  const s = String(v ?? '').trim().toUpperCase()
  if (['Y', '是', '√', 'TRUE', '1'].includes(s)) return 'Y'
  if (['N', '否', '×', 'FALSE', '0'].includes(s)) return 'N'
  return ''
}

export function recomputeI1DetailRow(row: I1DetailRow): I1DetailRow {
  const costBegin = _n(row.costBegin)
  const costIncrease = _n(row.costIncrease)
  const costDecrease = _n(row.costDecrease)
  const costEnd = calcAssetEndBalance(costBegin, costIncrease, costDecrease)

  const costBeginAdj = _n(row.costBeginAdj)
  const costAdjInc = _n(row.costAdjInc)
  const costAdjDec = _n(row.costAdjDec)
  const auditedCostBegin = costBegin + costBeginAdj
  const auditedCostIncrease = costIncrease + costAdjInc
  const auditedCostDecrease = costDecrease + costAdjDec
  const auditedCostEnd = calcAssetEndBalance(auditedCostBegin, auditedCostIncrease, auditedCostDecrease)

  // 摊销：兼容旧 amortTransferOut
  let amortDisposal = _n(row.amortDisposal)
  let amortOtherDecrease = _n(row.amortOtherDecrease)
  const legacyTransfer = _n(row.amortTransferOut)
  if (amortDisposal === 0 && amortOtherDecrease === 0 && legacyTransfer > 0) {
    amortDisposal = legacyTransfer
  }
  const amortProvision = _n(row.amortProvision)
  const amortOtherIncrease = _n(row.amortOtherIncrease)
  const accAmortBegin = _n(row.accAmortBegin)
  const amortInc = amortProvision + amortOtherIncrease
  const amortDec = amortDisposal + amortOtherDecrease
  const accAmortEnd = calcContraEndBalance(accAmortBegin, amortDec, amortInc)

  const accAmortBeginAdj = _n(row.accAmortBeginAdj)
  const amortAdjInc = _n(row.amortAdjInc)
  const amortAdjDec = _n(row.amortAdjDec)
  const auditedAccAmortBegin = accAmortBegin + accAmortBeginAdj
  const auditedAmortIncrease = amortInc + amortAdjInc
  const auditedAmortDecrease = amortDec + amortAdjDec
  const auditedAccAmortEnd = calcContraEndBalance(
    auditedAccAmortBegin,
    auditedAmortDecrease,
    auditedAmortIncrease,
  )

  // 减值：兼容旧 impairmentReversal → impairDisposal
  let impairDisposal = _n(row.impairDisposal)
  let impairOtherDecrease = _n(row.impairOtherDecrease)
  const legacyRev = _n(row.impairmentReversal)
  if (impairDisposal === 0 && impairOtherDecrease === 0 && legacyRev > 0) {
    impairDisposal = legacyRev
  }
  const impairmentBegin = _n(row.impairmentBegin)
  const impairmentProvision = _n(row.impairmentProvision)
  const impairOtherIncrease = _n(row.impairOtherIncrease)
  const impairInc = impairmentProvision + impairOtherIncrease
  const impairDec = impairDisposal + impairOtherDecrease
  const impairmentEnd = calcContraEndBalance(impairmentBegin, impairDec, impairInc)

  const impairmentBeginAdj = _n(row.impairmentBeginAdj)
  const impairAdjInc = _n(row.impairAdjInc)
  const impairAdjDec = _n(row.impairAdjDec)
  const auditedImpairmentBegin = impairmentBegin + impairmentBeginAdj
  const auditedImpairIncrease = impairInc + impairAdjInc
  const auditedImpairDecrease = impairDec + impairAdjDec
  const auditedImpairmentEnd = calcContraEndBalance(
    auditedImpairmentBegin,
    auditedImpairDecrease,
    auditedImpairIncrease,
  )

  const netBegin = calcNetValue(costBegin, accAmortBegin, impairmentBegin)
  const netValue = calcNetValue(costEnd, accAmortEnd, impairmentEnd)
  const auditedNetBegin = calcNetValue(auditedCostBegin, auditedAccAmortBegin, auditedImpairmentBegin)
  const auditedNetEnd = calcNetValue(auditedCostEnd, auditedAccAmortEnd, auditedImpairmentEnd)

  const indefiniteLife = _yn(row.indefiniteLife)
    || (_n(row.usefulLifeMonths) <= 0 && row.name ? 'Y' : _yn(row.indefiniteLife))

  return {
    ...row,
    costBegin,
    costIncrease,
    costDecrease,
    costEnd,
    costBeginAdj,
    costAdjInc,
    costAdjDec,
    auditedCostBegin,
    auditedCostIncrease,
    auditedCostDecrease,
    auditedCostEnd,
    accAmortBegin,
    amortProvision,
    amortOtherIncrease,
    amortDisposal,
    amortOtherDecrease,
    amortTransferOut: amortDec,
    accAmortEnd,
    accAmortBeginAdj,
    amortAdjInc,
    amortAdjDec,
    auditedAccAmortBegin,
    auditedAmortIncrease,
    auditedAmortDecrease,
    auditedAccAmortEnd,
    impairmentBegin,
    impairmentProvision,
    impairOtherIncrease,
    impairDisposal,
    impairOtherDecrease,
    impairmentReversal: impairDec,
    impairmentEnd,
    impairmentBeginAdj,
    impairAdjInc,
    impairAdjDec,
    auditedImpairmentBegin,
    auditedImpairIncrease,
    auditedImpairDecrease,
    auditedImpairmentEnd,
    netBegin,
    netValue,
    auditedNetBegin,
    auditedNetEnd,
    indefiniteLife: indefiniteLife as 'Y' | 'N' | '',
    notReadyForUse: _yn(row.notReadyForUse) as 'Y' | 'N' | '',
    hasTitleEvidence: _yn(row.hasTitleEvidence) as 'Y' | 'N' | '',
    mortgageRestricted: _yn(row.mortgageRestricted) as 'Y' | 'N' | '',
  }
}

export function emptyI1DetailRow(partial?: Partial<I1DetailRow>): I1DetailRow {
  return recomputeI1DetailRow({
    rowId: partial?.rowId ?? `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    category: '',
    name: '',
    acquisitionDate: '',
    usefulLifeMonths: 0,
    salvageRate: 0,
    amortizationMethod: DEFAULT_AMORTIZATION_METHOD,
    indefiniteLife: '',
    notReadyForUse: '',
    costBegin: 0,
    costIncrease: 0,
    costIncreaseMethod: '',
    costDecrease: 0,
    costDecreaseMethod: '',
    costEnd: 0,
    costBeginAdj: 0,
    costAdjInc: 0,
    costAdjDec: 0,
    auditedCostBegin: 0,
    auditedCostIncrease: 0,
    auditedCostDecrease: 0,
    auditedCostEnd: 0,
    accAmortBegin: 0,
    amortProvision: 0,
    amortOtherIncrease: 0,
    amortDisposal: 0,
    amortOtherDecrease: 0,
    amortTransferOut: 0,
    accAmortEnd: 0,
    accAmortBeginAdj: 0,
    amortAdjInc: 0,
    amortAdjDec: 0,
    auditedAccAmortBegin: 0,
    auditedAmortIncrease: 0,
    auditedAmortDecrease: 0,
    auditedAccAmortEnd: 0,
    impairmentBegin: 0,
    impairmentProvision: 0,
    impairOtherIncrease: 0,
    impairDisposal: 0,
    impairOtherDecrease: 0,
    impairmentReversal: 0,
    impairmentEnd: 0,
    impairmentBeginAdj: 0,
    impairAdjInc: 0,
    impairAdjDec: 0,
    auditedImpairmentBegin: 0,
    auditedImpairIncrease: 0,
    auditedImpairDecrease: 0,
    auditedImpairmentEnd: 0,
    netBegin: 0,
    netValue: 0,
    auditedNetBegin: 0,
    auditedNetEnd: 0,
    hasTitleEvidence: '',
    mortgageRestricted: '',
    ...partial,
  })
}

export function normalizeI1DetailRow(raw: any): I1DetailRow {
  return recomputeI1DetailRow({
    rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
    category: String(raw.category ?? ''),
    name: String(raw.name ?? ''),
    acquisitionDate: String(raw.acquisitionDate ?? ''),
    usefulLifeMonths: _n(raw.usefulLifeMonths),
    salvageRate: _n(raw.salvageRate),
    amortizationMethod: String(raw.amortizationMethod ?? DEFAULT_AMORTIZATION_METHOD),
    indefiniteLife: raw.indefiniteLife,
    notReadyForUse: raw.notReadyForUse,
    costBegin: _n(raw.costBegin),
    costIncrease: _n(raw.costIncrease),
    costIncreaseMethod: String(raw.costIncreaseMethod ?? ''),
    costDecrease: _n(raw.costDecrease),
    costDecreaseMethod: String(raw.costDecreaseMethod ?? ''),
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
    const cat = (r.category || '其他').trim() || '其他'
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
  const indefinite = rows.filter((r) => r.indefiniteLife === 'Y' || r.usefulLifeMonths <= 0).length
  const notReady = rows.filter((r) => r.notReadyForUse === 'Y').length
  const noTitle = rows.filter((r) => r.hasTitleEvidence === 'N').length
  const mortgaged = rows.filter((r) => r.mortgageRestricted === 'Y').length
  return [
    `经核对明细账与报表，无形资产明细共 ${rows.length} 项；`,
    `未审期末原值 ${summary.costEnd.toFixed(2)} / 摊销 ${summary.accAmortEnd.toFixed(2)} / 减值 ${summary.impairmentEnd.toFixed(2)}，`,
    `期末净值 ${summary.netValue.toFixed(2)}（审定净值 ${summary.auditedNetEnd.toFixed(2)}）；`,
    `寿命不确定 ${indefinite} 项、尚未达可使用状态 ${notReady} 项（须每年减值测试）；`,
    `无权属证明 ${noTitle} 项、抵押受限 ${mortgaged} 项；`,
    cross.hasAnyWarning
      ? `与审定表小计存在差异（原值${cross.costDiff.toFixed(2)}/摊销${cross.amortDiff.toFixed(2)}/减值${cross.impairDiff.toFixed(2)}），须进一步核对。`
      : `与审定表小计勾稽一致，明细在重大方面未见异常。`,
  ].join('')
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
  const activeTab = ref<I1DetailTab>('basic')
  const activeRowIndex = ref<number>(-1)

  function _loadRows(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion
    if (!raw) {
      rows.value = []
      return
    }
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
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
    rows.value.filter((r) => r.indefiniteLife === 'Y' || r.notReadyForUse === 'Y' || r.usefulLifeMonths <= 0).length,
  )

  function switchTab(tab: I1DetailTab): void {
    activeTab.value = tab
  }

  function setActiveRow(index: number): void {
    activeRowIndex.value = index
  }

  function updateCell(rowIndex: number, field: keyof I1DetailRow, value: string | number): void {
    const row = rows.value[rowIndex]
    if (!row) return
    ;(row as any)[field] = value
    if (field === 'usefulLifeMonths' && _n(value) <= 0) {
      row.indefiniteLife = 'Y'
    }
    _recalcRow(row)
    _persist()
  }

  async function addRow(defaultCategory?: string): Promise<I1DetailRow | null> {
    try {
      const { value: name } = await ElMessageBox.prompt(
        '请输入无形资产名称',
        '新增明细行',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '例如：XXX专利权',
          inputValidator: (val) => (!val || !val.trim() ? '名称不能为空' : true),
        },
      )
      if (!name?.trim()) return null
      const newRow = emptyI1DetailRow({
        name: name.trim(),
        category: defaultCategory ?? '',
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
    { key: 'category', label: '资产分类', width: 120, editable: true, type: 'select' as const, options: [...I1_DETAIL_CATEGORIES] },
    { key: 'name', label: '资产名称', width: 160, editable: true, type: 'text' as const },
    { key: 'acquisitionDate', label: '取得日期', width: 120, editable: true, type: 'date' as const },
    { key: 'usefulLifeMonths', label: '使用寿命(月)', width: 110, editable: true, type: 'number' as const },
    { key: 'indefiniteLife', label: '寿命不确定', width: 100, editable: true, type: 'select' as const, options: ['', 'Y', 'N'] },
    { key: 'notReadyForUse', label: '未达可使用', width: 100, editable: true, type: 'select' as const, options: ['', 'Y', 'N'] },
    { key: 'salvageRate', label: '残值率', width: 90, editable: true, type: 'number' as const },
    { key: 'amortizationMethod', label: '摊销方法', width: 110, editable: true, type: 'select' as const, options: ['直线法', '剩余年限法', '产量法'] },
    { key: 'hasTitleEvidence', label: '权属证明', width: 90, editable: true, type: 'select' as const, options: ['', 'Y', 'N'] },
    { key: 'mortgageRestricted', label: '抵押受限', width: 90, editable: true, type: 'select' as const, options: ['', 'Y', 'N'] },
  ]

  const costColumns = [
    { key: 'name', label: '资产名称', width: 140, editable: false, type: 'text' as const },
    { key: 'costBegin', label: '未审期初', width: 110, editable: true, type: 'number' as const },
    { key: 'costIncrease', label: '未审增加', width: 110, editable: true, type: 'number' as const },
    { key: 'costIncreaseMethod', label: '增加方式', width: 120, editable: true, type: 'select' as const, options: [...I1_COST_INCREASE_METHODS] },
    { key: 'costDecrease', label: '未审减少', width: 110, editable: true, type: 'number' as const },
    { key: 'costDecreaseMethod', label: '减少方式', width: 140, editable: true, type: 'select' as const, options: [...I1_COST_DECREASE_METHODS] },
    { key: 'costEnd', label: '未审期末', width: 110, editable: false, type: 'formula' as const, tooltip: '期末=期初+增加-减少' },
    { key: 'costBeginAdj', label: '期初调整', width: 100, editable: true, type: 'number' as const },
    { key: 'costAdjInc', label: '账调增加', width: 100, editable: true, type: 'number' as const },
    { key: 'costAdjDec', label: '账调减少', width: 100, editable: true, type: 'number' as const },
    { key: 'auditedCostBegin', label: '审定期初', width: 110, editable: false, type: 'formula' as const, tooltip: '未审期初+期初调整' },
    { key: 'auditedCostIncrease', label: '审定增加', width: 110, editable: false, type: 'formula' as const, tooltip: '未审增加+账调增加' },
    { key: 'auditedCostDecrease', label: '审定减少', width: 110, editable: false, type: 'formula' as const, tooltip: '未审减少+账调减少' },
    { key: 'auditedCostEnd', label: '审定期末', width: 110, editable: false, type: 'formula' as const, tooltip: '审定期初+审定增加-审定减少' },
  ]

  const amortColumns = [
    { key: 'name', label: '资产名称', width: 140, editable: false, type: 'text' as const },
    { key: 'accAmortBegin', label: '未审期初', width: 110, editable: true, type: 'number' as const },
    { key: 'amortProvision', label: '本期摊销', width: 110, editable: true, type: 'number' as const },
    { key: 'amortOtherIncrease', label: '其他增加', width: 100, editable: true, type: 'number' as const },
    { key: 'amortDisposal', label: '处置转出', width: 100, editable: true, type: 'number' as const },
    { key: 'amortOtherDecrease', label: '其他减少', width: 100, editable: true, type: 'number' as const },
    { key: 'accAmortEnd', label: '未审期末', width: 110, editable: false, type: 'formula' as const, tooltip: '期初+本期摊销+其他增加-处置-其他减少' },
    { key: 'accAmortBeginAdj', label: '期初调整', width: 100, editable: true, type: 'number' as const },
    { key: 'amortAdjInc', label: '账调增加', width: 100, editable: true, type: 'number' as const },
    { key: 'amortAdjDec', label: '账调减少', width: 100, editable: true, type: 'number' as const },
    { key: 'auditedAccAmortBegin', label: '审定期初', width: 110, editable: false, type: 'formula' as const, tooltip: '未审期初+期初调整' },
    { key: 'auditedAmortIncrease', label: '审定增加', width: 110, editable: false, type: 'formula' as const, tooltip: '（本期摊销+其他增加）+账调增加' },
    { key: 'auditedAmortDecrease', label: '审定减少', width: 110, editable: false, type: 'formula' as const, tooltip: '（处置+其他减少）+账调减少' },
    { key: 'auditedAccAmortEnd', label: '审定期末', width: 110, editable: false, type: 'formula' as const, tooltip: '审定期初+审定增加-审定减少' },
  ]

  const impairmentColumns = [
    { key: 'name', label: '资产名称', width: 140, editable: false, type: 'text' as const },
    { key: 'impairmentBegin', label: '未审期初', width: 110, editable: true, type: 'number' as const },
    { key: 'impairmentProvision', label: '本期计提', width: 110, editable: true, type: 'number' as const },
    { key: 'impairOtherIncrease', label: '其他增加', width: 100, editable: true, type: 'number' as const },
    { key: 'impairDisposal', label: '处置结转', width: 100, editable: true, type: 'number' as const },
    { key: 'impairOtherDecrease', label: '其他减少', width: 100, editable: true, type: 'number' as const },
    { key: 'impairmentEnd', label: '未审期末', width: 110, editable: false, type: 'formula' as const, tooltip: '期初+计提+其他增加-处置-其他减少（无形资产减值不得转回）' },
    { key: 'impairmentBeginAdj', label: '期初调整', width: 100, editable: true, type: 'number' as const },
    { key: 'impairAdjInc', label: '账调增加', width: 100, editable: true, type: 'number' as const },
    { key: 'impairAdjDec', label: '账调减少', width: 100, editable: true, type: 'number' as const },
    { key: 'auditedImpairmentBegin', label: '审定期初', width: 110, editable: false, type: 'formula' as const, tooltip: '未审期初+期初调整' },
    { key: 'auditedImpairIncrease', label: '审定增加', width: 110, editable: false, type: 'formula' as const, tooltip: '（计提+其他增加）+账调增加' },
    { key: 'auditedImpairDecrease', label: '审定减少', width: 110, editable: false, type: 'formula' as const, tooltip: '（处置结转+其他减少）+账调减少；无形资产减值不得转回' },
    { key: 'auditedImpairmentEnd', label: '审定期末', width: 110, editable: false, type: 'formula' as const, tooltip: '审定期初+审定增加-审定减少' },
  ]

  const netColumns = [
    { key: 'name', label: '资产名称', width: 140, editable: false, type: 'text' as const },
    { key: 'netBegin', label: '未审期初净值', width: 120, editable: false, type: 'formula' as const, tooltip: '原值期初−摊销期初−减值期初' },
    { key: 'netValue', label: '未审期末净值', width: 120, editable: false, type: 'formula' as const, tooltip: '原值期末−摊销期末−减值期末' },
    { key: 'auditedNetBegin', label: '审定期初净值', width: 120, editable: false, type: 'formula' as const, tooltip: '审定原值期初−审定摊销期初−审定减值期初' },
    { key: 'auditedNetEnd', label: '审定期末净值', width: 120, editable: false, type: 'formula' as const, tooltip: '审定原值期末−审定摊销期末−审定减值期末' },
    { key: 'hasTitleEvidence', label: '权属证明', width: 90, editable: true, type: 'select' as const, options: ['', 'Y', 'N'] },
    { key: 'mortgageRestricted', label: '抵押受限', width: 90, editable: true, type: 'select' as const, options: ['', 'Y', 'N'] },
  ]

  const tabs = [
    { key: 'basic' as I1DetailTab, label: '①基础/权属', columns: basicColumns },
    { key: 'cost' as I1DetailTab, label: '②原值(未审→审定)', columns: costColumns },
    { key: 'amort' as I1DetailTab, label: '③累计摊销', columns: amortColumns },
    { key: 'impairment' as I1DetailTab, label: '④减值准备', columns: impairmentColumns },
    { key: 'net' as I1DetailTab, label: '⑤净值汇总', columns: netColumns },
  ]

  const activeColumns = computed(() =>
    tabs.find((t) => t.key === activeTab.value)?.columns ?? basicColumns,
  )

  function _persist(): void {
    options?.onSave?.(ITEM_ID_ROWS, rows.value)
  }

  watch(allResponses, () => _loadRows(), { immediate: true })

  return {
    rows,
    activeTab,
    activeRowIndex,
    summaryRow,
    crossValidation,
    categorySummary,
    needAnnualImpairmentCount,
    activeColumns,
    tabs,
    basicColumns,
    costColumns,
    amortColumns,
    impairmentColumns,
    netColumns,
    switchTab,
    setActiveRow,
    updateCell,
    recalcAll,
    addRow,
    removeRow,
    moveRowUp,
    moveRowDown,
    importRows,
    exportRows,
    fillConclusionDraft,
  }
}

export default useI1Detail
