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
import { sumDevProductMovement } from './useF2DevProductSheet'
import { sumDevCostMovement } from './useF2DevCostSheet'
import { sumContractPerfMovement } from './useF2ContractPerfSheet'
import { sumBioAssetMovement } from './useF2BioAssetSheet'

import type { F2AdjustmentRow } from './useF2Adjustment'
import {
  F2_ACCOUNT_TO_ROW_KEY,
  F2_ROW_KEY_ACCOUNT,
  sumGrossAjeByRowKey,
  sumImpairmentAjeByRowKey,
} from './f2AccountModel'

export {
  F2_ACCOUNT_TO_ROW_KEY,
  F2_ROW_KEY_ACCOUNT,
  F2_PRICE_DIFF_ACCOUNT,
  F2_IMPAIRMENT_ACCOUNT,
} from './f2AccountModel'

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
  if (sheetCode === 'F2-10') {
    const raw = readRowJson(map.get('F2-10-rows'))
    const mv = sumDevProductMovement(safeParseRows(raw))
    return {
      openingAmt: mv.opening,
      increaseAmt: mv.increase,
      decreaseAmt: mv.decrease,
      closingAmt: mv.closing,
    }
  }
  if (sheetCode === 'F2-11') {
    const raw = readRowJson(map.get('F2-11-rows'))
    const mv = sumDevCostMovement(safeParseRows(raw))
    return {
      openingAmt: mv.opening,
      increaseAmt: mv.increase,
      decreaseAmt: mv.decrease,
      closingAmt: mv.closing,
    }
  }
  if (sheetCode === 'F2-12') {
    const raw = readRowJson(map.get('F2-12-rows'))
    const mv = sumContractPerfMovement(safeParseRows(raw))
    return {
      openingAmt: mv.opening,
      increaseAmt: mv.increase,
      decreaseAmt: mv.decrease,
      closingAmt: mv.closing,
    }
  }
  if (sheetCode === 'F2-13') {
    const raw = readRowJson(map.get('F2-13-rows'))
    const mv = sumBioAssetMovement(safeParseRows(raw))
    return {
      openingAmt: mv.opening,
      increaseAmt: mv.increase,
      decreaseAmt: mv.decrease,
      closingAmt: mv.closing,
    }
  }
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

  /** F2-14 AJE → F2-1 账项调整（按科目汇总；进销差价 1412 / 跌价 1471） */
  const grossAdjustmentByRowKey = computed((): Record<string, number> =>
    sumGrossAjeByRowKey(adjustmentRows.value),
  )

  const impairmentAdjustmentByRowKey = computed((): Record<string, number> =>
    sumImpairmentAjeByRowKey(adjustmentRows.value),
  )

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
