/**
 * useD7Analysis — D7-4 分析表（4区块：借方/贷方发生额分析 + Top10债务人）
 *
 * Spec: .kiro/specs/d7-contract-liabilities/
 * Task: 9.1
 * Requirements: 9.1-9.10, 18.3, 23.2
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcSubtotal,
  calcChangeAmount,
  calcChangeRate,
  topNByField,
} from './useD7FormulaEngine'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from './useD7FormData'
import type { DetailRow } from './useD7Detail'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AnalysisRow {
  rowId: string
  item: string            // 科目/对方科目
  amount: number          // 金额
  dataSource: string      // 数据来源
  remark: string
}

export interface Top10Row {
  customerName: string
  endBalance: number
  priorBalance: number
  changeAmount: number
  changeRate: number | '' | 'N/A'
  aging: string
  postTransfer: number
}

export interface UseD7AnalysisOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function safeParseArray(jsonStr: string | null | undefined): any[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function generateRowId(): string {
  return `ana-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD7Analysis(options: UseD7AnalysisOptions) {
  const { allResponses, debouncedSave } = options

  // ─── (一) 借方发生额分析 ────────────────────────────────────────────

  const debitRows = ref<AnalysisRow[]>([])

  watch(
    () => allResponses.value.get('D7-4-debit-rows')?.remark,
    (jsonStr) => {
      debitRows.value = safeParseArray(jsonStr).map((r: any) => ({
        rowId: r.rowId || generateRowId(),
        item: r.item || '',
        amount: parseNum(r.amount),
        dataSource: r.dataSource || '',
        remark: r.remark || '',
      }))
    },
    { immediate: true },
  )

  const debitTotal: ComputedRef<number> = computed(() => {
    // From TB (trial_balance debit total for account 2205)
    return parseNum(allResponses.value.get('D7-4-debit-total')?.remark)
  })

  const debitDiff: ComputedRef<number> = computed(() => {
    const rowsSum = calcSubtotal(debitRows.value.map(r => r.amount))
    return debitTotal.value - rowsSum
  })

  // ─── (三) 贷方发生额分析 ────────────────────────────────────────────

  const creditRows = ref<AnalysisRow[]>([])

  watch(
    () => allResponses.value.get('D7-4-credit-rows')?.remark,
    (jsonStr) => {
      creditRows.value = safeParseArray(jsonStr).map((r: any) => ({
        rowId: r.rowId || generateRowId(),
        item: r.item || '',
        amount: parseNum(r.amount),
        dataSource: r.dataSource || '',
        remark: r.remark || '',
      }))
    },
    { immediate: true },
  )

  const creditTotal: ComputedRef<number> = computed(() => {
    return parseNum(allResponses.value.get('D7-4-credit-total')?.remark)
  })

  const creditDiff: ComputedRef<number> = computed(() => {
    const rowsSum = calcSubtotal(creditRows.value.map(r => r.amount))
    return creditTotal.value - rowsSum
  })

  // ─── (四) Top10 债务人 ──────────────────────────────────────────────

  const top10Rows: ComputedRef<Top10Row[]> = computed(() => {
    const d7DetailJson = allResponses.value.get('D7-2-rows')?.remark
    const detailRows: DetailRow[] = safeParseArray(d7DetailJson) as DetailRow[]

    if (detailRows.length === 0) return []

    // Sort by endAudited desc, take top 10
    const sorted = topNByField(detailRows, 'endAudited', 10)

    return sorted.map(r => {
      const endBalance = parseNum(r.endAudited)
      const priorBalance = parseNum(r.priorAudited)
      // Aging description from aging fields
      const agingParts: string[] = []
      if (parseNum(r.endAging1) > 0) agingParts.push('1年以内')
      if (parseNum(r.endAging2) > 0) agingParts.push('1~2年')
      if (parseNum(r.endAging3) > 0) agingParts.push('2~3年')
      if (parseNum(r.endAging4) > 0) agingParts.push('3年以上')

      return {
        customerName: r.companyName || r.contractName || '',
        endBalance,
        priorBalance,
        changeAmount: calcChangeAmount(priorBalance, endBalance),
        changeRate: calcChangeRate(priorBalance, endBalance),
        aging: agingParts.join('、') || '-',
        postTransfer: parseNum(r.postTransfer),
      }
    })
  })

  // Top10 集中度
  const top10Concentration: ComputedRef<number> = computed(() => {
    if (top10Rows.value.length === 0) return 0
    const top10Sum = calcSubtotal(top10Rows.value.map(r => r.endBalance))
    const d7DetailJson = allResponses.value.get('D7-2-rows')?.remark
    const detailRows: DetailRow[] = safeParseArray(d7DetailJson) as DetailRow[]
    const totalEndAudited = calcSubtotal(detailRows.map(r => parseNum(r.endAudited)))
    if (totalEndAudited === 0) return 0
    return top10Sum / totalEndAudited
  })

  const isHighConcentration: ComputedRef<boolean> = computed(() => {
    return top10Concentration.value > 0.5
  })

  // ─── publishSignificantChange ──────────────────────────────────────

  function publishSignificantChange(): void {
    // Check if any top10 row has change rate > 30%
    for (const row of top10Rows.value) {
      if (typeof row.changeRate === 'number' && Math.abs(row.changeRate) > 0.3) {
        try {
          eventBus.emit('analytical:significant-change', {
            wpCode: 'D7',
            changeRate: row.changeRate,
            item: row.customerName,
            timestamp: Date.now(),
          })
        } catch { /* non-blocking */ }
        break
      }
    }
  }

  // ─── Audit Notes ─────────────────────────────────────────────────────

  const auditNotes = ref<{ explanation: string; conclusion: string }>({
    explanation: '',
    conclusion: '',
  })

  watch(allResponses, (map) => {
    auditNotes.value.explanation = map.get('D7-4-note-explanation')?.remark || ''
    auditNotes.value.conclusion = map.get('D7-4-note-conclusion')?.remark || ''
  }, { immediate: true })

  watch(() => auditNotes.value.explanation, (v) => debouncedSave('D7-4-note-explanation', { remark: v }))
  watch(() => auditNotes.value.conclusion, (v) => debouncedSave('D7-4-note-conclusion', { remark: v }))

  // ─── Persist helpers for debit/credit rows ───────────────────────────

  function persistDebitRows(): void {
    debouncedSave('D7-4-debit-rows', { remark: JSON.stringify(debitRows.value) })
  }

  function persistCreditRows(): void {
    debouncedSave('D7-4-credit-rows', { remark: JSON.stringify(creditRows.value) })
  }

  function addDebitRow(): void {
    debitRows.value = [...debitRows.value, { rowId: generateRowId(), item: '', amount: 0, dataSource: '', remark: '' }]
    persistDebitRows()
  }

  function addCreditRow(): void {
    creditRows.value = [...creditRows.value, { rowId: generateRowId(), item: '', amount: 0, dataSource: '', remark: '' }]
    persistCreditRows()
  }

  function removeDebitRow(rowId: string): void {
    debitRows.value = debitRows.value.filter(r => r.rowId !== rowId)
    persistDebitRows()
  }

  function removeCreditRow(rowId: string): void {
    creditRows.value = creditRows.value.filter(r => r.rowId !== rowId)
    persistCreditRows()
  }

  function updateDebitCell(rowId: string, field: string, value: any): void {
    debitRows.value = debitRows.value.map(r => {
      if (r.rowId !== rowId) return r
      const updated = { ...r }
      if (field === 'amount') updated.amount = parseNum(value)
      else (updated as any)[field] = value
      return updated
    })
    persistDebitRows()
  }

  function updateCreditCell(rowId: string, field: string, value: any): void {
    creditRows.value = creditRows.value.map(r => {
      if (r.rowId !== rowId) return r
      const updated = { ...r }
      if (field === 'amount') updated.amount = parseNum(value)
      else (updated as any)[field] = value
      return updated
    })
    persistCreditRows()
  }

  // ─── 从序时账导入（调用后端 d7_ledger_analysis resolver） ──────────

  async function importFromLedger(): Promise<void> {
    try {
      const http = (await import('@/utils/http')).default
      const year = parseInt(allResponses.value.get('D7-4-audit-year')?.remark || '0') ||
        new Date().getFullYear() - 1
      const res = await http.get('/api/auto-data/d7_ledger_analysis', {
        params: { project_id: options.projectId.value, year },
      })
      const data = res.data?.data || res.data || {}

      // Fill debit rows
      const debitByCounter: Array<{ counter_account: string; amount: number }> = data.debit_by_counter || []
      if (debitByCounter.length > 0) {
        debitRows.value = debitByCounter.map((r: any) => ({
          rowId: generateRowId(),
          item: r.counter_account || '未知',
          amount: r.amount || 0,
          dataSource: '序时账导入',
          remark: '',
        }))
        persistDebitRows()
      }

      // Fill credit rows
      const creditByCounter: Array<{ counter_account: string; amount: number }> = data.credit_by_counter || []
      if (creditByCounter.length > 0) {
        creditRows.value = creditByCounter.map((r: any) => ({
          rowId: generateRowId(),
          item: r.counter_account || '未知',
          amount: r.amount || 0,
          dataSource: '序时账导入',
          remark: '',
        }))
        persistCreditRows()
      }

      // Update TB totals for cross-check
      if (data.debit_total) {
        debouncedSave('D7-4-debit-total', { remark: String(data.debit_total) })
      }
      if (data.credit_total) {
        debouncedSave('D7-4-credit-total', { remark: String(data.credit_total) })
      }

      const { ElMessage } = await import('element-plus')
      ElMessage.success(`已从序时账导入：借方${debitByCounter.length}项，贷方${creditByCounter.length}项`)
    } catch {
      const { ElMessage } = await import('element-plus')
      ElMessage.error('从序时账导入失败，请稍后重试')
    }
  }

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    debitRows,
    debitTotal,
    debitDiff,
    creditRows,
    creditTotal,
    creditDiff,
    top10Rows,
    top10Concentration,
    isHighConcentration,
    auditNotes,
    publishSignificantChange,
    importFromLedger,
    addDebitRow,
    addCreditRow,
    removeDebitRow,
    removeCreditRow,
    updateDebitCell,
    updateCreditCell,
  }
}

export default useD7Analysis
