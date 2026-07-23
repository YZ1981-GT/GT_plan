/**
 * useF2CrossSheet — F2 跨 Sheet 联动（比照 useD4CrossSheet / useF3CrossSheet）
 *
 * F2-3~13 明细 → F2-2 汇总 → F2-1 审定表交叉验证
 * Spec: .kiro/specs/f2-inventory-main/ Task 4.x
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
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
import {
  buildCostCarryforwardReconcile,
  type CostCarryforwardReconcile,
} from './f2D4CostPull'

export {
  F2_ACCOUNT_TO_ROW_KEY,
  F2_ROW_KEY_ACCOUNT,
  F2_PRICE_DIFF_ACCOUNT,
  F2_IMPAIRMENT_ACCOUNT,
} from './f2AccountModel'

export interface UseF2CrossSheetOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  projectContext: Ref<ProjectContext>
  /** 6401 营业成本审定发生额（外部传入，来自 f2D4CostPull） */
  operatingCost?: Ref<number>
  /** 存货余额（审定期末，供容差计算） */
  inventoryBalance?: Ref<number>
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

  // ─── Task 8: 成本/产销存勾稽 ──────────────────────────────────────────

  /** 产销存恒等式：期初 + 本期购进(增加) - 本期发出(减少) = 期末 */
  const productionSalesIdentity = computed(() => {
    const opening = detailOpeningTotal.value
    const increase = calcSubtotal(categorySummaries.value.map((s) => s.increaseAmt))
    const decrease = calcSubtotal(categorySummaries.value.map((s) => s.decreaseAmt))
    const closing = detailGrandTotal.value
    const expected = opening + increase - decrease
    const diff = closing - expected
    return {
      opening,
      increase,
      decrease,
      closingActual: closing,
      closingExpected: expected,
      diff,
      balanced: Math.abs(diff) <= 0.01,
    }
  })

  /** 出库结转 vs 营业成本勾稽（消费 f2D4CostPull） */
  const operatingCostReconcile: ComputedRef<CostCarryforwardReconcile | null> = computed(() => {
    const oc = options.operatingCost?.value
    if (oc == null || oc === 0) return null
    const outboundTotal = calcSubtotal(categorySummaries.value.map((s) => s.decreaseAmt))
    const invBalance = options.inventoryBalance?.value ?? detailGrandTotal.value
    return buildCostCarryforwardReconcile(outboundTotal, oc, invBalance)
  })

  /** 成本 vs 利润表勾稽（在产品变动 ≈ 营业成本 + 期末存货变动）
   *  简化：成本 ≈ 发出合计 + (期初在产品−期末在产品)
   *  差异来源：制造费用分摊 / 跨期调整
   */
  const costToPlReconcile = computed(() => {
    const oc = options.operatingCost?.value ?? 0
    const decrease = calcSubtotal(categorySummaries.value.map((s) => s.decreaseAmt))
    // 在产品/开发成本变动 = 期初 - 期末（减少在产品 → 转为完工成本）
    const devProductSummary = categorySummaries.value.find((s) => s.sheetCode === 'F2-10')
    const devCostSummary = categorySummaries.value.find((s) => s.sheetCode === 'F2-11')
    const wipOpeningTotal = (devProductSummary?.openingAmt ?? 0) + (devCostSummary?.openingAmt ?? 0)
    const wipClosingTotal = (devProductSummary?.closingAmt ?? 0) + (devCostSummary?.closingAmt ?? 0)
    const wipChange = wipOpeningTotal - wipClosingTotal // 在产品减少 → 成本增加
    const estimatedCost = decrease + wipChange
    const diff = estimatedCost - oc
    const tolerance = Math.max(Math.abs(oc) * 0.05, 1)
    return {
      outboundTotal: decrease,
      wipChange,
      estimatedCost,
      operatingCost: oc,
      diff,
      matched: Math.abs(diff) <= tolerance,
      tolerance,
    }
  })

  // ─── Task 15: 风险信号（呆滞/减值异常/毛利率异常 → B50） ────────────
  const riskSignals = computed(() => {
    const signals: Array<{ type: string; description: string; severity: 'warning' | 'danger' }> = []
    // 产销存恒等式差异 > 0
    const psi = productionSalesIdentity.value
    if (!psi.balanced && psi.diff !== 0) {
      signals.push({
        type: '产销存差异',
        description: `产销存恒等式差异 ${psi.diff.toFixed(2)} 元（期初+入-出≠期末）`,
        severity: Math.abs(psi.diff) > 10000 ? 'danger' : 'warning',
      })
    }
    // 营业成本勾稽不一致
    const costRec = operatingCostReconcile.value
    if (costRec && !costRec.matched) {
      signals.push({
        type: '出库结转差异',
        description: `出库合计 ${costRec.outboundTotal.toFixed(2)} vs 营业成本 ${costRec.operatingCost.toFixed(2)}，差异 ${costRec.diff.toFixed(2)}`,
        severity: 'warning',
      })
    }
    return signals
  })

  /** 发布风险信号到 B50（无异常不发） */
  function publishRiskSignals(): void {
    if (riskSignals.value.length === 0) return
    for (const sig of riskSignals.value) {
      try {
        // Task 15: 同时通过 eventBus 发出风险信号供 B50 消费
        eventBus.emit('risk:identified' as any, {
          wpCode: 'F2',
          riskType: sig.type,
          description: sig.description,
          severity: sig.severity,
        })
        window.dispatchEvent(new CustomEvent('risk:identified', {
          detail: {
            wpCode: 'F2',
            type: sig.type,
            description: sig.description,
            severity: sig.severity,
          },
        }))
      } catch { /* silent */ }
    }
  }

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
    productionSalesIdentity,
    operatingCostReconcile,
    costToPlReconcile,
    riskSignals,
    publishRiskSignals,
  }
}

export default useF2CrossSheet
