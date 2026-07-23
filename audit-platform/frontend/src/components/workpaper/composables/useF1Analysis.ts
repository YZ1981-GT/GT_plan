/**
 * useF1Analysis — F1-4 实质性分析表核心逻辑
 *
 * 对齐 Excel「实质性分析表 F1-4」：
 * 1. 预付款项余额分析（本期/上期/变动 + 存货占比）
 * 2. 借方发生额分析（性质拆分 + 占存货采购比重）
 * 3. 贷方发生额分析（转销路径拆分）
 * 4. 大额供应商期末余额分析（勾稽 F1-2）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcSubtotal,
  calcChangeAmount,
  calcChangeRate,
  calcPercentage,
  isChangeRateExceeding,
} from './useF1FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import type { useF1CrossSheet } from './useF1CrossSheet'
import { formatAgingAmountHint } from './agingPresets'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 余额/借方分析：按经济实质四段 */
export type AnalysisNatureKey = 'inventory' | 'expense' | 'construction' | 'other'

export interface PeriodAmountRow {
  rowKey: string
  label: string
  indent: boolean
  /** 可编辑；汇总行/比率行为自动 */
  editable: boolean
  rowKind: 'total' | 'nature' | 'anchor' | 'ratio'
  current: number
  prior: number
}

export interface CreditBreakdownRow {
  rowKey: string
  label: string
  indent: boolean
  editable: boolean
  rowKind: 'total' | 'breakdown'
  current: number
  prior: number
}

export interface MajorSupplierRow {
  rowId: string
  supplierName: string
  priorBalance: number
  debit: number
  credit: number
  endBalance: number
  badDebt: number
  bookValue: number
  aging: string
  reason: string
  postSettlement: number
}

export interface AnalysisNotes {
  balance: string
  debit: string
  credit: string
  supplier: string
}

export interface UseF1AnalysisOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useF1CrossSheet>
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_PACK = 'F1-ana-pack'
/** 兼容旧版单项 key */
const LEGACY_NOTE = 'F1-ana-note'
const LEGACY_CONCLUSION = 'F1-analysis-audit-conclusion'

export const BALANCE_NATURE_ROWS: { key: AnalysisNatureKey; label: string }[] = [
  { key: 'inventory', label: '与存货有关的预付款项余额' },
  { key: 'expense', label: '与费用有关的预付款项余额' },
  { key: 'construction', label: '与工程、固定资产有关的预付款项余额' },
  { key: 'other', label: '其他' },
]

export const DEBIT_NATURE_ROWS: { key: AnalysisNatureKey; label: string }[] = [
  { key: 'inventory', label: '与存货有关的' },
  { key: 'expense', label: '与费用有关的' },
  { key: 'construction', label: '与工程、固定资产有关的' },
  { key: 'other', label: '其他' },
]

export const CREDIT_BREAKDOWN_ROWS: { key: string; label: string }[] = [
  { key: 'toInventory', label: '转销计入存货金额' },
  { key: 'toExpense', label: '转销计入费用金额' },
  { key: 'toConstruction', label: '转销工程、固定资产金额' },
  { key: 'refund', label: '收回款项金额' },
  { key: 'other', label: '其他' },
]

/** F1-2 款项性质 → 分析实质分类 */
export const NATURE_TO_ANALYSIS: Record<string, AnalysisNatureKey> = {
  货款: 'inventory',
  服务费: 'expense',
  工程款: 'construction',
  设备款: 'construction',
  其他: 'other',
}

// ─── Pure helpers ────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `ms-${crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)}`
}

export function emptyPeriodPair(): { current: number; prior: number } {
  return { current: 0, prior: 0 }
}

export function createEmptySupplierRow(): MajorSupplierRow {
  return {
    rowId: generateRowId(),
    supplierName: '',
    priorBalance: 0,
    debit: 0,
    credit: 0,
    endBalance: 0,
    badDebt: 0,
    bookValue: 0,
    aging: '',
    reason: '',
    postSettlement: 0,
  }
}

/** 大额供应商行内公式：期末=期初+借−贷；账面价值=期末−坏账 */
export function recalcSupplierRow(row: MajorSupplierRow): MajorSupplierRow {
  const endBalance = parseNum(row.priorBalance) + parseNum(row.debit) - parseNum(row.credit)
  const bookValue = endBalance - parseNum(row.badDebt)
  return { ...row, endBalance, bookValue }
}

export function withPeriodMetrics<T extends { current: number; prior: number }>(
  row: T,
): T & { changeAmount: number; changeRate: number | '' | 'N/A' } {
  return {
    ...row,
    changeAmount: calcChangeAmount(row.current, row.prior),
    changeRate: calcChangeRate(row.prior, row.current),
  }
}

/**
 * 从明细行按实质分类汇总（余额用 endAudited/priorAudited；发生额用 debit）
 */
export function aggregateDetailByAnalysisNature(
  detailRows: { nature?: string; endAudited?: number; priorAudited?: number; debit?: number; credit?: number }[],
  field: 'balance' | 'debit',
): Record<AnalysisNatureKey, { current: number; prior: number }> {
  const result: Record<AnalysisNatureKey, { current: number; prior: number }> = {
    inventory: emptyPeriodPair(),
    expense: emptyPeriodPair(),
    construction: emptyPeriodPair(),
    other: emptyPeriodPair(),
  }
  for (const row of detailRows) {
    const key = NATURE_TO_ANALYSIS[row.nature || ''] || 'other'
    if (field === 'balance') {
      result[key].current += parseNum(row.endAudited)
      result[key].prior += parseNum(row.priorAudited)
    } else {
      result[key].current += parseNum(row.debit)
      // 上期借方无明细字段时保持 0，由用户手工填
    }
  }
  return result
}

/**
 * 计算 Top5 / 大额供应商候选（纯函数）
 */
export function computeTop5(
  rows: { customerName: string; endAudited: number; priorAudited?: number; debit?: number; credit?: number; agingHint?: string; postSettlement?: number }[],
  limit = 5,
): {
  top5: {
    customerName: string
    endAudited: number
    priorAudited: number
    changeAmount: number
    changeRate: number | '' | 'N/A'
  }[]
  concentrationWarning: string | null
  majorCandidates: MajorSupplierRow[]
} {
  if (rows.length === 0) {
    return { top5: [], concentrationWarning: null, majorCandidates: [] }
  }

  const sorted = [...rows].sort((a, b) => b.endAudited - a.endAudited)
  const topRaw = sorted.slice(0, limit)

  const top5 = topRaw.map(r => {
    const prior = r.priorAudited ?? 0
    return {
      customerName: r.customerName,
      endAudited: r.endAudited,
      priorAudited: prior,
      changeAmount: calcChangeAmount(r.endAudited, prior),
      changeRate: calcChangeRate(prior, r.endAudited),
    }
  })

  const totalEndAudited = calcSubtotal(rows.map(r => r.endAudited))
  const top5Total = calcSubtotal(top5.map(r => r.endAudited))

  let concentrationWarning: string | null = null
  if (totalEndAudited > 0 && top5Total / totalEndAudited > 0.5) {
    const pct = ((top5Total / totalEndAudited) * 100).toFixed(1)
    concentrationWarning = `前五大供应商集中度较高（${pct}%），请关注供应商集中与资金占用风险`
  }

  const majorCandidates = topRaw.map(r => {
    const priorBalance = parseNum(r.priorAudited)
    const debit = parseNum(r.debit)
    const credit = parseNum(r.credit)
    // 优先采用明细审定数；无则回退期初+借−贷
    const endBalance = r.endAudited != null
      ? parseNum(r.endAudited)
      : priorBalance + debit - credit
    return {
      ...createEmptySupplierRow(),
      supplierName: r.customerName,
      priorBalance,
      debit,
      credit,
      endBalance,
      badDebt: 0,
      bookValue: endBalance,
      aging: r.agingHint || '',
      postSettlement: parseNum(r.postSettlement),
    }
  })

  return { top5, concentrationWarning, majorCandidates }
}

function fmtAgingHint(agingAudited: Record<string, number> | undefined): string {
  return formatAgingAmountHint(agingAudited)
}

/** F1-4 与 F2 存货采购 / F4 应付轻量联动提示（纯函数，便于单测） */
export function buildCrossCycleHints(input: {
  prepaidEndCurrent: number
  prepaidEndPrior: number
  inventoryRelatedDebit: number
  inventoryPurchaseCurrent: number
  inventoryBalanceCurrent: number
  payableBalanceCurrent: number
}): string[] {
  const hints: string[] = []
  const {
    prepaidEndCurrent,
    prepaidEndPrior,
    inventoryRelatedDebit,
    inventoryPurchaseCurrent,
    inventoryBalanceCurrent,
    payableBalanceCurrent,
  } = input

  if (inventoryRelatedDebit > 0 && inventoryPurchaseCurrent <= 0) {
    hints.push('存货相关预付借方已有金额，但「存货采购金额」未填：请从 F2 录入采购数后再解读占比（与 F2 联动）。')
  }

  if (inventoryPurchaseCurrent > 0) {
    const avgPrepaid = (Math.abs(prepaidEndCurrent) + Math.abs(prepaidEndPrior)) / 2
    if (avgPrepaid > 0) {
      const turnoverDays = (avgPrepaid / inventoryPurchaseCurrent) * 365
      if (turnoverDays > 180) {
        hints.push(
          `预付周转约 ${turnoverDays.toFixed(0)} 天（均余÷存货采购×365），高于 180 天：请核长期挂账/合同进度，并对照 F1-5。`,
        )
      }
    }
    const ratio = calcPercentage(inventoryRelatedDebit, inventoryPurchaseCurrent)
    if (ratio != null && ratio > 80) {
      hints.push(`存货相关预付借方占采购 ${ratio.toFixed(1)}%，偏高：关注预付是否超合同比例或跨期。`)
    }
  }

  if (inventoryBalanceCurrent > 0 && prepaidEndCurrent > inventoryBalanceCurrent * 0.5) {
    hints.push('预付期末余额超过存货余额 50%：请在说明中解释业务模式（与 F2 存货余额联动）。')
  }

  if (payableBalanceCurrent > 0 && prepaidEndCurrent > payableBalanceCurrent) {
    hints.push(
      '预付期末余额大于应付账款期末余额：请核对是否与同一供应商并存预付+应付、是否应抵销列报（与 F4 联动）。',
    )
  } else if (prepaidEndCurrent > 0 && payableBalanceCurrent <= 0) {
    hints.push('可录入「应付账款期末余额」（对照 F4）以启用预付/应付并存勾稽提示。')
  }

  return hints
}

interface AnalysisPack {
  balanceNatures: Record<AnalysisNatureKey, { current: number; prior: number }>
  inventoryBalance: { current: number; prior: number }
  debitNatures: Record<AnalysisNatureKey, { current: number; prior: number }>
  inventoryPurchase: { current: number; prior: number }
  /** 应付账款期末余额（手工录入，用于与 F4 轻量联动） */
  payableBalance: { current: number; prior: number }
  creditBreakdown: Record<string, { current: number; prior: number }>
  suppliers: MajorSupplierRow[]
  notes: AnalysisNotes
  conclusion: string
}

function emptyPack(): AnalysisPack {
  const natures = (): Record<AnalysisNatureKey, { current: number; prior: number }> => ({
    inventory: emptyPeriodPair(),
    expense: emptyPeriodPair(),
    construction: emptyPeriodPair(),
    other: emptyPeriodPair(),
  })
  const credit: Record<string, { current: number; prior: number }> = {}
  for (const r of CREDIT_BREAKDOWN_ROWS) credit[r.key] = emptyPeriodPair()
  return {
    balanceNatures: natures(),
    inventoryBalance: emptyPeriodPair(),
    debitNatures: natures(),
    inventoryPurchase: emptyPeriodPair(),
    payableBalance: emptyPeriodPair(),
    creditBreakdown: credit,
    suppliers: [],
    notes: { balance: '', debit: '', credit: '', supplier: '' },
    conclusion: '',
  }
}

function normalizePack(raw: any): AnalysisPack {
  const base = emptyPack()
  if (!raw || typeof raw !== 'object') return base

  for (const k of Object.keys(base.balanceNatures) as AnalysisNatureKey[]) {
    const src = raw.balanceNatures?.[k]
    if (src) {
      base.balanceNatures[k] = { current: parseNum(src.current), prior: parseNum(src.prior) }
    }
  }
  if (raw.inventoryBalance) {
    base.inventoryBalance = {
      current: parseNum(raw.inventoryBalance.current),
      prior: parseNum(raw.inventoryBalance.prior),
    }
  }
  for (const k of Object.keys(base.debitNatures) as AnalysisNatureKey[]) {
    const src = raw.debitNatures?.[k]
    if (src) {
      base.debitNatures[k] = { current: parseNum(src.current), prior: parseNum(src.prior) }
    }
  }
  if (raw.inventoryPurchase) {
    base.inventoryPurchase = {
      current: parseNum(raw.inventoryPurchase.current),
      prior: parseNum(raw.inventoryPurchase.prior),
    }
  }
  if (raw.payableBalance) {
    base.payableBalance = {
      current: parseNum(raw.payableBalance.current),
      prior: parseNum(raw.payableBalance.prior),
    }
  }
  for (const r of CREDIT_BREAKDOWN_ROWS) {
    const src = raw.creditBreakdown?.[r.key]
    if (src) {
      base.creditBreakdown[r.key] = { current: parseNum(src.current), prior: parseNum(src.prior) }
    }
  }
  if (Array.isArray(raw.suppliers)) {
    base.suppliers = raw.suppliers.map((s: any) =>
      recalcSupplierRow({
        rowId: s.rowId || generateRowId(),
        supplierName: s.supplierName || '',
        priorBalance: parseNum(s.priorBalance),
        debit: parseNum(s.debit),
        credit: parseNum(s.credit),
        endBalance: parseNum(s.endBalance),
        badDebt: parseNum(s.badDebt),
        bookValue: parseNum(s.bookValue),
        aging: s.aging || '',
        reason: s.reason || '',
        postSettlement: parseNum(s.postSettlement),
      }),
    )
  }
  if (raw.notes && typeof raw.notes === 'object') {
    base.notes = {
      balance: raw.notes.balance || '',
      debit: raw.notes.debit || '',
      credit: raw.notes.credit || '',
      supplier: raw.notes.supplier || '',
    }
  }
  base.conclusion = raw.conclusion || ''
  return base
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useF1Analysis(options: UseF1AnalysisOptions) {
  const { allResponses, debouncedSave, isReadonly } = options

  const pack = ref<AnalysisPack>(emptyPack())
  let hydrating = false

  function persist(): void {
    if (hydrating || isReadonly.value) return
    debouncedSave(ITEM_ID_PACK, { remark: JSON.stringify(pack.value) })
  }

  watch(
    () => allResponses.value.get(ITEM_ID_PACK)?.remark,
    (jsonStr) => {
      hydrating = true
      try {
        if (jsonStr) {
          try {
            pack.value = normalizePack(JSON.parse(jsonStr))
          } catch {
            pack.value = emptyPack()
          }
        } else {
          // 兼容旧版：仅有审计说明/结论
          const next = emptyPack()
          next.notes.balance = allResponses.value.get(LEGACY_NOTE)?.remark || ''
          next.conclusion = allResponses.value.get(LEGACY_CONCLUSION)?.remark || ''
          pack.value = next
        }
      } finally {
        hydrating = false
      }
    },
    { immediate: true },
  )

  // ─── 余额分析展示行 ──────────────────────────────────────────────────

  const balanceRows: ComputedRef<(PeriodAmountRow & { changeAmount: number; changeRate: number | '' | 'N/A'; ratioDisplay?: string })[]> = computed(() => {
    const natures = BALANCE_NATURE_ROWS.map(n => {
      const pair = pack.value.balanceNatures[n.key]
      return withPeriodMetrics({
        rowKey: n.key,
        label: n.label,
        indent: true,
        editable: true,
        rowKind: 'nature' as const,
        current: pair.current,
        prior: pair.prior,
      })
    })
    const totalCurrent = calcSubtotal(natures.map(r => r.current))
    const totalPrior = calcSubtotal(natures.map(r => r.prior))
    const total = withPeriodMetrics({
      rowKey: 'total',
      label: '预付款项余额',
      indent: false,
      editable: false,
      rowKind: 'total' as const,
      current: totalCurrent,
      prior: totalPrior,
    })
    const inv = withPeriodMetrics({
      rowKey: 'inventoryBalance',
      label: '存货余额',
      indent: false,
      editable: true,
      rowKind: 'anchor' as const,
      current: pack.value.inventoryBalance.current,
      prior: pack.value.inventoryBalance.prior,
    })
    const invRelated = pack.value.balanceNatures.inventory
    const ratioCurrent = pack.value.inventoryBalance.current
      ? calcPercentage(invRelated.current, pack.value.inventoryBalance.current)
      : null
    const ratioPrior = pack.value.inventoryBalance.prior
      ? calcPercentage(invRelated.prior, pack.value.inventoryBalance.prior)
      : null
    const ratioRow = {
      rowKey: 'inventoryRatio',
      label: '期末与存货有关预付款项余额占存货比重',
      indent: false,
      editable: false,
      rowKind: 'ratio' as const,
      current: ratioCurrent ?? 0,
      prior: ratioPrior ?? 0,
      changeAmount: 0,
      changeRate: '' as const,
      ratioDisplay: `${ratioCurrent == null ? '#DIV/0!' : ratioCurrent.toFixed(2) + '%'} / ${ratioPrior == null ? '#DIV/0!' : ratioPrior.toFixed(2) + '%'}`,
    }
    return [total, ...natures, inv, ratioRow]
  })

  // ─── 借方分析展示行 ──────────────────────────────────────────────────

  const debitRows: ComputedRef<(PeriodAmountRow & { changeAmount: number; changeRate: number | '' | 'N/A'; ratioDisplay?: string })[]> = computed(() => {
    const natures = DEBIT_NATURE_ROWS.map(n => {
      const pair = pack.value.debitNatures[n.key]
      return withPeriodMetrics({
        rowKey: n.key,
        label: n.label,
        indent: true,
        editable: true,
        rowKind: 'nature' as const,
        current: pair.current,
        prior: pair.prior,
      })
    })
    const total = withPeriodMetrics({
      rowKey: 'total',
      label: '预付账款借方发生额',
      indent: false,
      editable: false,
      rowKind: 'total' as const,
      current: calcSubtotal(natures.map(r => r.current)),
      prior: calcSubtotal(natures.map(r => r.prior)),
    })
    const purchase = withPeriodMetrics({
      rowKey: 'inventoryPurchase',
      label: '存货采购金额',
      indent: false,
      editable: true,
      rowKind: 'anchor' as const,
      current: pack.value.inventoryPurchase.current,
      prior: pack.value.inventoryPurchase.prior,
    })
    const invDebit = pack.value.debitNatures.inventory
    const ratioCurrent = pack.value.inventoryPurchase.current
      ? calcPercentage(invDebit.current, pack.value.inventoryPurchase.current)
      : null
    const ratioPrior = pack.value.inventoryPurchase.prior
      ? calcPercentage(invDebit.prior, pack.value.inventoryPurchase.prior)
      : null
    const ratioRow = {
      rowKey: 'purchaseRatio',
      label: '与存货有关的预付款项借方发生额占存货采购金额比重',
      indent: false,
      editable: false,
      rowKind: 'ratio' as const,
      current: ratioCurrent ?? 0,
      prior: ratioPrior ?? 0,
      changeAmount: 0,
      changeRate: '' as const,
      ratioDisplay: `${ratioCurrent == null ? '#DIV/0!' : ratioCurrent.toFixed(2) + '%'} / ${ratioPrior == null ? '#DIV/0!' : ratioPrior.toFixed(2) + '%'}`,
    }
    return [total, ...natures, purchase, ratioRow]
  })

  // ─── 贷方分析展示行 ──────────────────────────────────────────────────

  const creditRows: ComputedRef<(CreditBreakdownRow & { changeAmount: number; changeRate: number | '' | 'N/A' })[]> = computed(() => {
    const breakdown = CREDIT_BREAKDOWN_ROWS.map(r => {
      const pair = pack.value.creditBreakdown[r.key] || emptyPeriodPair()
      return withPeriodMetrics({
        rowKey: r.key,
        label: r.label,
        indent: true,
        editable: true,
        rowKind: 'breakdown' as const,
        current: pair.current,
        prior: pair.prior,
      })
    })
    const total = withPeriodMetrics({
      rowKey: 'total',
      label: '预付账款贷方发生额',
      indent: false,
      editable: false,
      rowKind: 'total' as const,
      current: calcSubtotal(breakdown.map(r => r.current)),
      prior: calcSubtotal(breakdown.map(r => r.prior)),
    })
    return [total, ...breakdown]
  })

  // ─── 大额供应商 ──────────────────────────────────────────────────────

  const supplierRows = computed(() => pack.value.suppliers)

  const supplierSubtotal = computed(() => {
    const rows = pack.value.suppliers
    return {
      priorBalance: calcSubtotal(rows.map(r => r.priorBalance)),
      debit: calcSubtotal(rows.map(r => r.debit)),
      credit: calcSubtotal(rows.map(r => r.credit)),
      endBalance: calcSubtotal(rows.map(r => r.endBalance)),
      badDebt: calcSubtotal(rows.map(r => r.badDebt)),
      bookValue: calcSubtotal(rows.map(r => r.bookValue)),
      postSettlement: calcSubtotal(rows.map(r => r.postSettlement)),
    }
  })

  const detailSourceRows = computed(() => {
    const resp = allResponses.value.get('F1-det-rows')
    if (!resp?.remark) return []
    try {
      const parsed = JSON.parse(resp.remark)
      if (!Array.isArray(parsed)) return []
      return parsed.map((r: any) => ({
        customerName: r.customerName || '',
        nature: r.nature || '',
        endAudited: parseNum(r.endAudited),
        priorAudited: parseNum(r.priorAudited),
        debit: parseNum(r.debit),
        credit: parseNum(r.credit),
        agingHint: fmtAgingHint(r.agingAudited),
        postSettlement: parseNum(r.postPeriodSettlement),
      }))
    } catch {
      return []
    }
  })

  const top5Result = computed(() => computeTop5(detailSourceRows.value, 5))
  const top5ConcentrationWarning = computed(() => top5Result.value.concentrationWarning)

  const prepaidEndCurrent = computed(() =>
    calcSubtotal(Object.values(pack.value.balanceNatures).map(p => p.current)),
  )
  const prepaidEndPrior = computed(() =>
    calcSubtotal(Object.values(pack.value.balanceNatures).map(p => p.prior)),
  )

  const crossCycleHints = computed(() =>
    buildCrossCycleHints({
      prepaidEndCurrent: prepaidEndCurrent.value,
      prepaidEndPrior: prepaidEndPrior.value,
      inventoryRelatedDebit: pack.value.debitNatures.inventory.current,
      inventoryPurchaseCurrent: pack.value.inventoryPurchase.current,
      inventoryBalanceCurrent: pack.value.inventoryBalance.current,
      payableBalanceCurrent: pack.value.payableBalance.current,
    }),
  )

  // ─── Mutations ───────────────────────────────────────────────────────

  function updateBalanceNature(key: AnalysisNatureKey, field: 'current' | 'prior', value: number): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      balanceNatures: {
        ...pack.value.balanceNatures,
        [key]: { ...pack.value.balanceNatures[key], [field]: parseNum(value) },
      },
    }
    persist()
  }

  function updateInventoryBalance(field: 'current' | 'prior', value: number): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      inventoryBalance: { ...pack.value.inventoryBalance, [field]: parseNum(value) },
    }
    persist()
  }

  function updateDebitNature(key: AnalysisNatureKey, field: 'current' | 'prior', value: number): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      debitNatures: {
        ...pack.value.debitNatures,
        [key]: { ...pack.value.debitNatures[key], [field]: parseNum(value) },
      },
    }
    persist()
  }

  function updateInventoryPurchase(field: 'current' | 'prior', value: number): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      inventoryPurchase: { ...pack.value.inventoryPurchase, [field]: parseNum(value) },
    }
    persist()
  }

  function updatePayableBalance(field: 'current' | 'prior', value: number): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      payableBalance: { ...pack.value.payableBalance, [field]: parseNum(value) },
    }
    persist()
  }

  function updateCreditBreakdown(key: string, field: 'current' | 'prior', value: number): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      creditBreakdown: {
        ...pack.value.creditBreakdown,
        [key]: { ...(pack.value.creditBreakdown[key] || emptyPeriodPair()), [field]: parseNum(value) },
      },
    }
    persist()
  }

  function updateNote(section: keyof AnalysisNotes, value: string): void {
    if (isReadonly.value) return
    pack.value = { ...pack.value, notes: { ...pack.value.notes, [section]: value } }
    persist()
  }

  function updateConclusion(value: string): void {
    if (isReadonly.value) return
    pack.value = { ...pack.value, conclusion: value }
    persist()
  }

  function addSupplierRow(): void {
    if (isReadonly.value) return
    pack.value = { ...pack.value, suppliers: [...pack.value.suppliers, createEmptySupplierRow()] }
    persist()
  }

  function removeSupplierRow(rowId: string): void {
    if (isReadonly.value) return
    pack.value = { ...pack.value, suppliers: pack.value.suppliers.filter(r => r.rowId !== rowId) }
    persist()
  }

  function updateSupplierCell(rowId: string, field: keyof MajorSupplierRow, value: any): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      suppliers: pack.value.suppliers.map(r => {
        if (r.rowId !== rowId) return r
        const next = { ...r, [field]: ['supplierName', 'aging', 'reason'].includes(field) ? value : parseNum(value) }
        return recalcSupplierRow(next as MajorSupplierRow)
      }),
    }
    persist()
  }

  /** 从 F1-2 按性质汇总填入余额/借方本期（上期余额同步；借方上期不覆盖） */
  function fillFromDetail(): void {
    if (isReadonly.value) return
    const bal = aggregateDetailByAnalysisNature(detailSourceRows.value, 'balance')
    const deb = aggregateDetailByAnalysisNature(detailSourceRows.value, 'debit')
    pack.value = {
      ...pack.value,
      balanceNatures: bal,
      debitNatures: {
        inventory: { current: deb.inventory.current, prior: pack.value.debitNatures.inventory.prior },
        expense: { current: deb.expense.current, prior: pack.value.debitNatures.expense.prior },
        construction: { current: deb.construction.current, prior: pack.value.debitNatures.construction.prior },
        other: { current: deb.other.current, prior: pack.value.debitNatures.other.prior },
      },
    }
    persist()
  }

  /**
   * 从试算表带入跨循环锚点余额（本期）：
   * - 存货余额 1401（对照 F2）
   * - 应付账款期末余额 2202（对照 F4，后端已取绝对值正数）
   * 仅在锚点当前为空时填入，不覆盖已录入值；采购额仍需手工/从 F2 录入。
   */
  function fillCrossCycleFromTb(ctx: { inventoryBalance?: number; payableBalance?: number }): {
    inventoryFilled: boolean
    payableFilled: boolean
  } {
    if (isReadonly.value) return { inventoryFilled: false, payableFilled: false }
    const inv = parseNum(ctx.inventoryBalance)
    const pay = parseNum(ctx.payableBalance)
    let inventoryFilled = false
    let payableFilled = false
    const next = { ...pack.value }
    if (inv !== 0 && pack.value.inventoryBalance.current === 0) {
      next.inventoryBalance = { ...next.inventoryBalance, current: inv }
      inventoryFilled = true
    }
    if (pay !== 0 && pack.value.payableBalance.current === 0) {
      next.payableBalance = { ...next.payableBalance, current: pay }
      payableFilled = true
    }
    if (inventoryFilled || payableFilled) {
      pack.value = next
      persist()
    }
    return { inventoryFilled, payableFilled }
  }

  /** 从 F1-2 取期末余额前 N 名填入大额供应商表（覆盖） */
  function fillMajorSuppliersFromDetail(limit = 10): void {
    if (isReadonly.value) return
    const { majorCandidates } = computeTop5(detailSourceRows.value, limit)
    pack.value = { ...pack.value, suppliers: majorCandidates }
    persist()
  }

  function publishSignificantChange(): void {
    for (const debtor of top5Result.value.top5) {
      if (isChangeRateExceeding(debtor.changeRate, 0.3)) {
        window.dispatchEvent(
          new CustomEvent('analytical:significant-change', {
            detail: { wpCode: 'F1', changeRate: debtor.changeRate, item: debtor.customerName },
          }),
        )
        break
      }
    }
  }

  const notes = computed(() => pack.value.notes)
  const conclusion = computed(() => pack.value.conclusion)

  return {
    balanceRows,
    debitRows,
    creditRows,
    supplierRows,
    supplierSubtotal,
    top5ConcentrationWarning,
    crossCycleHints,
    payableBalance: computed(() => pack.value.payableBalance),
    notes,
    conclusion,
    updateBalanceNature,
    updateInventoryBalance,
    updateDebitNature,
    updateInventoryPurchase,
    updatePayableBalance,
    updateCreditBreakdown,
    updateNote,
    updateConclusion,
    addSupplierRow,
    removeSupplierRow,
    updateSupplierCell,
    fillFromDetail,
    fillMajorSuppliersFromDetail,
    fillCrossCycleFromTb,
    publishSignificantChange,
    // 兼容旧测试/调用
    top5Debtors: computed(() => top5Result.value.top5),
    auditNote: computed({
      get: () => pack.value.notes.balance,
      set: (v: string) => updateNote('balance', v),
    }),
  }
}

export default useF1Analysis
