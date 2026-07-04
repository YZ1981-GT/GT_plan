/**
 * useF2CrossSheet — F2 跨 Sheet 联动（比照 useD4CrossSheet / useF3CrossSheet）
 *
 * F2-3~13 明细 → F2-2 汇总 → F2-1 审定表交叉验证
 * Spec: .kiro/specs/f2-inventory-main/ Task 4.x
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { calcSubtotal, parseNum } from './useF2InvMaiFormulaEngine'
import { readRowJson, type ChecklistResponse, type ProjectContext } from './useF2FormData'
import { F2_DETAIL_SHEET_CONFIGS } from '../f2/detail/f2DetailSheetConfigs'
import { F2_CATEGORIES } from './useF2Adjudication'
import type { F2DetailRow } from './useF2DetailSheet'

import type { F2AdjustmentRow } from './useF2Adjustment'

export interface UseF2CrossSheetOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  projectContext: Ref<ProjectContext>
}

export interface F2CategorySummary {
  rowKey: string
  label: string
  sheetCode: string
  accountCode: string
  openingAmt: number
  increaseAmt: number
  decreaseAmt: number
  closingAmt: number
}

/** 明细 sheet → 审定表 rowKey */
export const F2_SHEET_TO_ROW_KEY: Record<string, string> = {
  'F2-3': 'raw-materials',
  'F2-4': 'material-in-transit',
  'F2-5': 'revolving-materials',
  'F2-6': 'semi-finished',
  'F2-7': 'outsourced-processing',
  'F2-8': 'finished-goods',
  'F2-9': 'goods-in-transit',
  'F2-10': 'dev-products',
  'F2-11': 'dev-costs',
  'F2-12': 'contract-performance',
  'F2-13': 'consumable-bio',
}

export const F2_ROW_KEY_TO_SHEET: Record<string, string> = Object.fromEntries(
  Object.entries(F2_SHEET_TO_ROW_KEY).map(([sheet, key]) => [key, sheet]),
)

export function sheetCodeForRowKey(rowKey: string): string | undefined {
  return F2_ROW_KEY_TO_SHEET[rowKey]
}

export const F2_ROW_KEY_ACCOUNT: Record<string, string> = {
  'raw-materials': '1401',
  'material-in-transit': '1402',
  'revolving-materials': '1403',
  'semi-finished': '1404',
  'outsourced-processing': '1405',
  'finished-goods': '1406',
  'goods-in-transit': '1407',
  'dev-products': '1408',
  'dev-costs': '1409',
  'contract-performance': '1410',
  'consumable-bio': '1411',
  'price-difference': '1406',
  'impairment-provision': '1412',
}

/** 科目编码 → 审定表 rowKey（1406 优先映射 finished-goods） */
export const F2_ACCOUNT_TO_ROW_KEY: Record<string, string> = {
  '1401': 'raw-materials',
  '1402': 'material-in-transit',
  '1403': 'revolving-materials',
  '1404': 'semi-finished',
  '1405': 'outsourced-processing',
  '1406': 'finished-goods',
  '1407': 'goods-in-transit',
  '1408': 'dev-products',
  '1409': 'dev-costs',
  '1410': 'contract-performance',
  '1411': 'consumable-bio',
  '1412': 'impairment-provision',
}

const BALANCE_TOLERANCE = 0.005

function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function loadDetailTotals(map: Map<string, ChecklistResponse>, sheetCode: string) {
  const raw = readRowJson(map.get(`${sheetCode}-rows`))
  const rows = safeParseRows<F2DetailRow>(raw)
  return {
    openingAmt: calcSubtotal(rows.map((r) => r.openingAmt)),
    increaseAmt: calcSubtotal(rows.map((r) => r.increaseAmt)),
    decreaseAmt: calcSubtotal(rows.map((r) => r.decreaseAmt)),
    closingAmt: calcSubtotal(rows.map((r) => r.closingAmt)),
  }
}

export function useF2CrossSheet(options: UseF2CrossSheetOptions) {
  const { allResponses } = options

  const categorySummaries: ComputedRef<F2CategorySummary[]> = computed(() =>
    Object.values(F2_DETAIL_SHEET_CONFIGS).map((cfg) => {
      const totals = loadDetailTotals(allResponses.value, cfg.sheetCode)
      return {
        rowKey: F2_SHEET_TO_ROW_KEY[cfg.sheetCode] || cfg.sheetCode,
        label: cfg.categoryLabel,
        sheetCode: cfg.sheetCode,
        accountCode: cfg.accountCode,
        ...totals,
      }
    }),
  )

  const hasDetailData = computed(() =>
    categorySummaries.value.some((s) => s.closingAmt !== 0 || s.openingAmt !== 0),
  )

  const detailGrandTotal = computed(() =>
    calcSubtotal(categorySummaries.value.map((s) => s.closingAmt)),
  )

  const detailOpeningTotal = computed(() =>
    calcSubtotal(categorySummaries.value.map((s) => s.openingAmt)),
  )

  const adjustmentRows = computed((): F2AdjustmentRow[] =>
    safeParseRows<F2AdjustmentRow>(readRowJson(allResponses.value.get('F2-14-rows'))),
  )

  const hasAdjustmentData = computed(() =>
    adjustmentRows.value.some((r) => r.debitAmount !== 0 || r.creditAmount !== 0),
  )

  /** F2-14 AJE → F2-1 账项调整（按科目汇总） */
  const grossAdjustmentByRowKey = computed((): Record<string, number> => {
    const result: Record<string, number> = {}
    for (const row of adjustmentRows.value) {
      if (row.entryType !== 'AJE') continue
      const rowKey = F2_ACCOUNT_TO_ROW_KEY[row.accountCode]
      if (!rowKey || rowKey === 'impairment-provision') continue
      const delta = row.debitAmount - row.creditAmount
      result[rowKey] = (result[rowKey] || 0) + delta
    }
    return result
  })

  const impairmentAdjustmentByRowKey = computed((): Record<string, number> => {
    const result: Record<string, number> = {}
    for (const row of adjustmentRows.value) {
      if (row.entryType !== 'AJE') continue
      if (row.accountCode !== '1412') continue
      const delta = row.creditAmount - row.debitAmount
      result['impairment-provision'] = (result['impairment-provision'] || 0) + delta
    }
    return result
  })

  function summaryForRowKey(rowKey: string): F2CategorySummary | undefined {
    return categorySummaries.value.find((s) => s.rowKey === rowKey)
  }

  /** F2-1 原值区与明细汇总交叉验证消息 */
  function grossCrossValidation(
    grossEndUnadjustedTotal: number,
  ): string | null {
    if (!hasDetailData.value) return null
    const diff = grossEndUnadjustedTotal - detailGrandTotal.value
    if (Math.abs(diff) > BALANCE_TOLERANCE) {
      return `F2-1原值合计(${grossEndUnadjustedTotal.toFixed(2)}) 与 F2-3~13明细合计(${detailGrandTotal.value.toFixed(2)}) 差异${diff.toFixed(2)}`
    }
    return null
  }

  /** 附注取数：各类别净值审定数（需外部传入 net endAudited） */
  const inventoryAccountCodes = computed(() =>
    F2_CATEGORIES.map((c) => F2_ROW_KEY_ACCOUNT[c.rowKey]).filter(Boolean),
  )

  return {
    categorySummaries,
    hasDetailData,
    detailGrandTotal,
    detailOpeningTotal,
    summaryForRowKey,
    grossCrossValidation,
    inventoryAccountCodes,
    adjustmentRows,
    hasAdjustmentData,
    grossAdjustmentByRowKey,
    impairmentAdjustmentByRowKey,
  }
}

export default useF2CrossSheet
