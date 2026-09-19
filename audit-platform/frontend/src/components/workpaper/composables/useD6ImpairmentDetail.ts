/**
 * useD6ImpairmentDetail — D6-3 减值准备明细（14列63公式）
 *
 * 双分类行结构：
 *   - 按单项评估计提（category='single'）
 *   - 按信用风险组合计提（category='group'）
 *
 * 公式链：
 *   - 期初审定 = 期初未审 + AJE + RJE
 *   - 期末未审 = 期初审定 + 计提 + 其他增加 - 转回 - 核销 - 其他减少
 *   - 期末审定 = 期末未审 + AJE + RJE
 *
 * Spec: .kiro/specs/d6-contract-assets/
 * Task: 8.1
 * Requirements: 8.1-8.8, 27.2, 27.5
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAuditedAmount,
  calcImpairmentEndUnadjusted,
  calcEndAudited,
  calcSubtotal,
} from './useD6FormulaEngine'
import type { ChecklistResponse } from './useD6FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ImpairmentDetailRow {
  rowId: string
  itemName: string
  category: 'single' | 'group'
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number       // = 未审 + AJE + RJE（自动）
  provision: number          // 本期增加-计提
  otherIncrease: number      // 本期增加-其他增加
  reversal: number           // 本期减少-转回
  writeOff: number           // 本期减少-核销
  otherDecrease: number      // 本期减少-其他减少
  endUnadjusted: number      // = 期初审定+计提+其他增加-转回-核销-其他减少（自动）
  endAje: number
  endRje: number
  endAudited: number         // = 期末未审 + AJE + RJE（自动）
}

export interface UseD6ImpairmentDetailOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  crossSheet: { blockTotals: ComputedRef<{ block2: { total: number } }> }
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'D6-3-rows'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

function safeParseRows(jsonStr: string | null | undefined): ImpairmentDetailRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

function normalizeRow(raw: any): ImpairmentDetailRow {
  return {
    rowId: raw.rowId || generateRowId(),
    itemName: raw.itemName || '',
    category: raw.category === 'group' ? 'group' : 'single',
    priorUnadjusted: parseNum(raw.priorUnadjusted),
    priorAje: parseNum(raw.priorAje),
    priorRje: parseNum(raw.priorRje),
    priorAudited: parseNum(raw.priorAudited),
    provision: parseNum(raw.provision),
    otherIncrease: parseNum(raw.otherIncrease),
    reversal: parseNum(raw.reversal),
    writeOff: parseNum(raw.writeOff),
    otherDecrease: parseNum(raw.otherDecrease),
    endUnadjusted: parseNum(raw.endUnadjusted),
    endAje: parseNum(raw.endAje),
    endRje: parseNum(raw.endRje),
    endAudited: parseNum(raw.endAudited),
  }
}

/**
 * 重算单行公式链：
 *  priorAudited = priorUnadjusted + priorAje + priorRje
 *  endUnadjusted = priorAudited + provision + otherIncrease - reversal - writeOff - otherDecrease
 *  endAudited = endUnadjusted + endAje + endRje
 */
export function recalcImpairmentRow(row: ImpairmentDetailRow): ImpairmentDetailRow {
  const priorAudited = calcAuditedAmount(row.priorUnadjusted, row.priorAje, row.priorRje)
  const endUnadjusted = calcImpairmentEndUnadjusted(
    priorAudited, row.provision, row.otherIncrease,
    row.reversal, row.writeOff, row.otherDecrease,
  )
  const endAudited = calcEndAudited(endUnadjusted, row.endAje, row.endRje)
  return { ...row, priorAudited, endUnadjusted, endAudited }
}

function createEmptyRow(category: 'single' | 'group'): ImpairmentDetailRow {
  return {
    rowId: generateRowId(),
    itemName: '',
    category,
    priorUnadjusted: 0, priorAje: 0, priorRje: 0, priorAudited: 0,
    provision: 0, otherIncrease: 0,
    reversal: 0, writeOff: 0, otherDecrease: 0,
    endUnadjusted: 0, endAje: 0, endRje: 0, endAudited: 0,
  }
}

/** 计算一组行的各数值列合计 */
function sumImpairmentRows(rows: ImpairmentDetailRow[]): Omit<ImpairmentDetailRow, 'rowId' | 'itemName' | 'category'> {
  return {
    priorUnadjusted: calcSubtotal(rows.map(r => r.priorUnadjusted)),
    priorAje: calcSubtotal(rows.map(r => r.priorAje)),
    priorRje: calcSubtotal(rows.map(r => r.priorRje)),
    priorAudited: calcSubtotal(rows.map(r => r.priorAudited)),
    provision: calcSubtotal(rows.map(r => r.provision)),
    otherIncrease: calcSubtotal(rows.map(r => r.otherIncrease)),
    reversal: calcSubtotal(rows.map(r => r.reversal)),
    writeOff: calcSubtotal(rows.map(r => r.writeOff)),
    otherDecrease: calcSubtotal(rows.map(r => r.otherDecrease)),
    endUnadjusted: calcSubtotal(rows.map(r => r.endUnadjusted)),
    endAje: calcSubtotal(rows.map(r => r.endAje)),
    endRje: calcSubtotal(rows.map(r => r.endRje)),
    endAudited: calcSubtotal(rows.map(r => r.endAudited)),
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD6ImpairmentDetail(options: UseD6ImpairmentDetailOptions) {
  const { allResponses, crossSheet, debouncedSave } = options

  // ─── Reactive rows ───────────────────────────────────────────────────

  const singleRows = ref<ImpairmentDetailRow[]>([])
  const groupRows = ref<ImpairmentDetailRow[]>([])

  // Load from allResponses
  watch(
    () => allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (jsonStr) => {
      const allRows = safeParseRows(jsonStr).map(recalcImpairmentRow)
      singleRows.value = allRows.filter(r => r.category === 'single')
      groupRows.value = allRows.filter(r => r.category === 'group')
    },
    { immediate: true },
  )

  // ─── Persist ─────────────────────────────────────────────────────────

  function persistRows(): void {
    const allRows = [...singleRows.value, ...groupRows.value]
    debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(allRows) })
  }

  // ─── Subtotals & Total ───────────────────────────────────────────────

  const singleSubtotal: ComputedRef<ImpairmentDetailRow> = computed(() => {
    const sums = sumImpairmentRows(singleRows.value)
    return { rowId: '__single_subtotal__', itemName: '按单项评估计提小计', category: 'single' as const, ...sums }
  })

  const groupSubtotal: ComputedRef<ImpairmentDetailRow> = computed(() => {
    const sums = sumImpairmentRows(groupRows.value)
    return { rowId: '__group_subtotal__', itemName: '按组合评估计提小计', category: 'group' as const, ...sums }
  })

  const totalRow: ComputedRef<ImpairmentDetailRow> = computed(() => {
    const allRows = [...singleRows.value, ...groupRows.value]
    const sums = sumImpairmentRows(allRows)
    return { rowId: '__total__', itemName: '合计', category: 'single' as const, ...sums }
  })

  // ─── Reconciliation (D6-3 total vs D6-1 block2 total) ───────────────

  const reconciliation = computed(() => {
    const d63Total = totalRow.value.endAudited
    const d61Total = crossSheet.blockTotals.value.block2.total
    const diff = d63Total - d61Total
    return { d63Total, d61Total, diff }
  })

  // ─── Add/Remove/Update ───────────────────────────────────────────────

  function addRow(category: 'single' | 'group'): void {
    const newRow = createEmptyRow(category)
    if (category === 'single') {
      singleRows.value = [...singleRows.value, newRow]
    } else {
      groupRows.value = [...groupRows.value, newRow]
    }
    persistRows()
  }

  function removeRow(rowId: string): void {
    singleRows.value = singleRows.value.filter(r => r.rowId !== rowId)
    groupRows.value = groupRows.value.filter(r => r.rowId !== rowId)
    persistRows()
  }

  const NUMERIC_FIELDS = [
    'priorUnadjusted', 'priorAje', 'priorRje',
    'provision', 'otherIncrease',
    'reversal', 'writeOff', 'otherDecrease',
    'endAje', 'endRje',
  ]

  function updateCell(rowId: string, field: string, value: any): void {
    const updateInList = (list: ImpairmentDetailRow[]): ImpairmentDetailRow[] => {
      return list.map(r => {
        if (r.rowId !== rowId) return r
        const updated = { ...r }
        if (NUMERIC_FIELDS.includes(field)) {
          ;(updated as any)[field] = parseNum(value)
        } else {
          ;(updated as any)[field] = value
        }
        return recalcImpairmentRow(updated)
      })
    }
    singleRows.value = updateInList(singleRows.value)
    groupRows.value = updateInList(groupRows.value)
    persistRows()
  }

  // ─── Audit Notes ─────────────────────────────────────────────────────

  const auditNotes = ref<{ explanation: string; conclusion: string }>({
    explanation: '',
    conclusion: '',
  })

  watch(
    () => allResponses.value.get('D6-3-note-explanation')?.remark,
    (v) => { if (v) auditNotes.value.explanation = v },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get('D6-3-note-conclusion')?.remark,
    (v) => { if (v) auditNotes.value.conclusion = v },
    { immediate: true },
  )
  watch(
    () => auditNotes.value.explanation,
    (v) => debouncedSave('D6-3-note-explanation', { remark: v }),
  )
  watch(
    () => auditNotes.value.conclusion,
    (v) => debouncedSave('D6-3-note-conclusion', { remark: v }),
  )

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    singleRows,
    groupRows,
    singleSubtotal,
    groupSubtotal,
    totalRow,
    reconciliation,
    addRow,
    removeRow,
    updateCell,
    auditNotes,
  }
}

export default useD6ImpairmentDetail
