/**
 * useI5CrossSheet — I5 其他非流动资产跨Sheet联动 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('I5-{sheet}-{field}')?.remark 存 JSON/数值。
 *
 * 跨Sheet映射（数据流图）：
 * - I5-2 明细表 → 聚合 → I5-1 审定表（期初/增加/减少/期末小计）
 * - I5-3 调整分录 → AJE/RJE → I5-1 审定表
 * - I5-1 审定表 → 审定数回写 → TB 1911
 * - I5-1 + I5-2 → 附注披露（审定数 + 明细）
 *
 * 科目方向：
 * - 1911 其他非流动资产（借方/资产类）：期末=期初+增加-减少
 * - 明细对齐 Excel：原值/减值/净值；合计取净值审定（legacy beginBalance/endBalance）
 *
 * Spec: .kiro/specs/i5-other-noncurrent-assets/
 * Task: 3.2
 * Requirements: 2.1-2.5, 3.1-3.2
 */
import { computed, onScopeDispose, type ComputedRef, type Ref } from 'vue'
import { calcSubtotal } from './useI5FormulaEngine'

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
    const resp = allResponses.value.get('I5-2-rows')
    return safeParseRows<any>(resp?.remark)
  })

  const adjustmentRowsRaw = computed<I5AdjustmentRowRaw[]>(() => {
    const resp = allResponses.value.get('I5-3-rows')
    return safeParseRows<I5AdjustmentRowRaw>(resp?.remark)
  })

  const detailTotals: ComputedRef<I5DetailTotals> = computed(() => {
    const beginBalances: number[] = []
    const increases: number[] = []
    const decreases: number[] = []
    const endBalances: number[] = []

    for (const row of detailRowsRaw.value) {
      const name = String(row?.projectName || row?.name || '').trim()
      if (!name || name === '合计' || row?.layer === 'impairment' || row?.layer === 'net') continue
      // 优先净值审定别名；否则原值−减值；再回退旧扁平字段
      const gEnd = _getNum(row.gross?.auditedEnding)
      const iEnd = _getNum(row.impairment?.auditedEnding)
      const gOpen = _getNum(row.gross?.auditedOpening)
      const iOpen = _getNum(row.impairment?.auditedOpening)
      const gInc = _getNum(row.gross?.auditedIncrease)
      const iInc = _getNum(row.impairment?.auditedIncrease)
      const gDec = _getNum(row.gross?.auditedDecrease)
      const iDec = _getNum(row.impairment?.auditedDecrease)
      const hasNested = row.gross != null
      beginBalances.push(hasNested ? gOpen - iOpen : _getNum(row.beginBalance))
      increases.push(hasNested ? gInc - iInc : _getNum(row.increase))
      decreases.push(hasNested ? gDec - iDec : _getNum(row.decrease))
      endBalances.push(hasNested ? gEnd - iEnd : _getNum(row.endBalance))
    }

    const beginBalance = calcSubtotal(beginBalances)
    const increase = calcSubtotal(increases)
    const decrease = calcSubtotal(decreases)
    const endBalance = calcSubtotal(endBalances)

    return { total: endBalance, beginBalance, increase, decrease, endBalance }
  })

  const adjudicationFromDetail: ComputedRef<{ audited: number }> = computed(() => ({
    audited: detailTotals.value.endBalance,
  }))

  function _onSubstantiveAdjudicated(event: Event): void {
    void event
  }

  window.addEventListener('substantive:adjudicated', _onSubstantiveAdjudicated)
  onScopeDispose(() => {
    window.removeEventListener('substantive:adjudicated', _onSubstantiveAdjudicated)
  })

  return {
    detailTotals,
    adjudicationFromDetail,
    detailRowsRaw,
    adjustmentRowsRaw,
  }
}

export default useI5CrossSheet
