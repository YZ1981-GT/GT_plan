/**
 * useD3Analysis — D3-4 分析表核心逻辑 composable
 *
 * Spec: .kiro/specs/d3-prepaid-accounts/
 * Task: 10.1
 *
 * 职责：
 * - 定义 AnalysisSection/AnalysisRow/Top5DebtorRow 类型
 * - 实现 4区块数据（借方分析/贷方分析/Top5/审计说明）
 * - 实现从TB auto_data获取借方/贷方发生额总计
 * - 实现差异行 = TB总计 - 分拆合计
 * - 实现 top5Debtors computed（从crossSheet取D3-2按余额降序前5）
 * - 实现 top5ConcentrationWarning computed（>50%时警告）
 * - 实现 publishSignificantChange（变动>30%时EventBus）
 *
 * Requirements: 8.1-8.8, 18.3, 22.2
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal, calcChangeAmount, calcChangeRate, isChangeRateExceeding } from './useD3FormulaEngine'
import type { ChecklistResponse } from './useD3FormData'
import type { useD3CrossSheet } from './useD3CrossSheet'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AnalysisRow {
  rowKey: string
  label: string
  amount: number
  source: string
  remark: string
}

export interface Top5DebtorRow {
  customerName: string
  endAudited: number
  priorAudited: number
  changeAmount: number
  changeRate: number | '' | 'N/A'
}

export interface AnalysisSection {
  sectionKey: 'debit-analysis' | 'credit-analysis' | 'top5-debtors' | 'audit-note'
  sectionLabel: string
  rows: AnalysisRow[]
  totalRow?: AnalysisRow
  diffRow?: AnalysisRow
}

export interface UseD3AnalysisOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useD3CrossSheet>
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_DEBIT_ROWS = 'D3-ana-debit-rows'
const ITEM_ID_CREDIT_ROWS = 'D3-ana-credit-rows'
const ITEM_ID_NOTE = 'D3-ana-note'
const ITEM_ID_TB_DEBIT = 'D3-ana-tb-debit-total'
const ITEM_ID_TB_CREDIT = 'D3-ana-tb-credit-total'

// ─── Pure Helpers (exported for PBT testability) ─────────────────────────────

/**
 * 计算 Top5 债务人（纯函数，方便 PBT 测试）
 *
 * 从行列表中按 endAudited 降序取前5，同时计算集中度警告。
 */
export function computeTop5(
  rows: { customerName: string; endAudited: number; priorAudited?: number }[],
): { top5: Top5DebtorRow[]; concentrationWarning: string | null } {
  if (rows.length === 0) {
    return { top5: [], concentrationWarning: null }
  }

  // Sort by endAudited descending
  const sorted = [...rows].sort((a, b) => b.endAudited - a.endAudited)
  const top5Raw = sorted.slice(0, 5)

  const top5: Top5DebtorRow[] = top5Raw.map(r => {
    const prior = r.priorAudited ?? 0
    const changeAmount = calcChangeAmount(r.endAudited, prior)
    const changeRate = calcChangeRate(prior, r.endAudited)
    return {
      customerName: r.customerName,
      endAudited: r.endAudited,
      priorAudited: prior,
      changeAmount,
      changeRate,
    }
  })

  // Calculate concentration
  const totalEndAudited = calcSubtotal(rows.map(r => r.endAudited))
  const top5Total = calcSubtotal(top5.map(r => r.endAudited))

  let concentrationWarning: string | null = null
  if (totalEndAudited > 0 && top5Total / totalEndAudited > 0.5) {
    const pct = ((top5Total / totalEndAudited) * 100).toFixed(1)
    concentrationWarning = `前五大客户集中度较高（${pct}%），请关注客户集中风险`
  }

  return { top5, concentrationWarning }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function safeParseRows(jsonStr: string | null | undefined): AnalysisRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD3Analysis(options: UseD3AnalysisOptions) {
  const { allResponses, debouncedSave, crossSheet, isReadonly } = options

  // ─── TB Amounts ──────────────────────────────────────────────────────

  const tbDebitTotal = ref(0)
  const tbCreditTotal = ref(0)

  watch(
    () => allResponses.value.get(ITEM_ID_TB_DEBIT)?.remark,
    (val) => { tbDebitTotal.value = parseNum(val) },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(ITEM_ID_TB_CREDIT)?.remark,
    (val) => { tbCreditTotal.value = parseNum(val) },
    { immediate: true },
  )

  // ─── Debit/Credit Analysis Rows ──────────────────────────────────────

  const debitRows = ref<AnalysisRow[]>([])
  const creditRows = ref<AnalysisRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_ID_DEBIT_ROWS)?.remark,
    (jsonStr) => { debitRows.value = safeParseRows(jsonStr) },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(ITEM_ID_CREDIT_ROWS)?.remark,
    (jsonStr) => { creditRows.value = safeParseRows(jsonStr) },
    { immediate: true },
  )

  // ─── Top5 Debtors computed ───────────────────────────────────────────

  const top5Debtors: ComputedRef<Top5DebtorRow[]> = computed(() => {
    // Get D3-2 rows from crossSheet detailRows
    const resp = allResponses.value.get('D3-det-rows')
    if (!resp?.remark) return []
    let detailRows: any[] = []
    try {
      detailRows = JSON.parse(resp.remark)
      if (!Array.isArray(detailRows)) detailRows = []
    } catch {
      detailRows = []
    }

    const rows = detailRows.map(r => ({
      customerName: r.customerName || '',
      endAudited: parseNum(r.endAudited),
      priorAudited: parseNum(r.priorAudited),
    }))

    return computeTop5(rows).top5
  })

  const top5ConcentrationWarning: ComputedRef<string | null> = computed(() => {
    const resp = allResponses.value.get('D3-det-rows')
    if (!resp?.remark) return null
    let detailRows: any[] = []
    try {
      detailRows = JSON.parse(resp.remark)
      if (!Array.isArray(detailRows)) detailRows = []
    } catch {
      detailRows = []
    }

    const rows = detailRows.map(r => ({
      customerName: r.customerName || '',
      endAudited: parseNum(r.endAudited),
      priorAudited: parseNum(r.priorAudited),
    }))

    return computeTop5(rows).concentrationWarning
  })

  // ─── Sections computed ───────────────────────────────────────────────

  const sections: ComputedRef<AnalysisSection[]> = computed(() => {
    // Debit analysis section
    const debitTotal: AnalysisRow = {
      rowKey: 'debit-total',
      label: '合计',
      amount: calcSubtotal(debitRows.value.map(r => r.amount)),
      source: '',
      remark: '',
    }
    const debitDiff: AnalysisRow = {
      rowKey: 'debit-diff',
      label: '差异',
      amount: tbDebitTotal.value - debitTotal.amount,
      source: '=TB总计-分拆合计',
      remark: '',
    }

    // Credit analysis section
    const creditTotal: AnalysisRow = {
      rowKey: 'credit-total',
      label: '合计',
      amount: calcSubtotal(creditRows.value.map(r => r.amount)),
      source: '',
      remark: '',
    }
    const creditDiff: AnalysisRow = {
      rowKey: 'credit-diff',
      label: '差异',
      amount: tbCreditTotal.value - creditTotal.amount,
      source: '=TB总计-分拆合计',
      remark: '',
    }

    return [
      {
        sectionKey: 'debit-analysis' as const,
        sectionLabel: '(一) 借方发生额分析',
        rows: debitRows.value,
        totalRow: debitTotal,
        diffRow: debitDiff,
      },
      {
        sectionKey: 'credit-analysis' as const,
        sectionLabel: '(二) 贷方发生额分析',
        rows: creditRows.value,
        totalRow: creditTotal,
        diffRow: creditDiff,
      },
      {
        sectionKey: 'top5-debtors' as const,
        sectionLabel: '(三) 期末主要预收客户分析',
        rows: [],
        totalRow: undefined,
        diffRow: undefined,
      },
      {
        sectionKey: 'audit-note' as const,
        sectionLabel: '三、审计说明',
        rows: [],
        totalRow: undefined,
        diffRow: undefined,
      },
    ]
  })

  // ─── Audit Note ──────────────────────────────────────────────────────

  const auditNote = ref('')

  watch(
    () => allResponses.value.get(ITEM_ID_NOTE)?.remark,
    (val) => { auditNote.value = val || '' },
    { immediate: true },
  )

  watch(
    () => auditNote.value,
    (val) => { debouncedSave(ITEM_ID_NOTE, { remark: val }) },
  )

  // ─── publishSignificantChange ────────────────────────────────────────

  function publishSignificantChange(): void {
    // Check if any top5 debtor has >30% change
    for (const debtor of top5Debtors.value) {
      if (isChangeRateExceeding(debtor.changeRate, 0.3)) {
        const event = new CustomEvent('analytical:significant-change', {
          detail: {
            wpCode: 'D3',
            changeRate: debtor.changeRate,
            item: debtor.customerName,
          },
        })
        window.dispatchEvent(event)
        break
      }
    }
  }

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    sections,
    top5Debtors,
    top5ConcentrationWarning,
    auditNote,
    tbDebitTotal,
    tbCreditTotal,
    debitRows,
    creditRows,
    publishSignificantChange,
  }
}

export default useD3Analysis
