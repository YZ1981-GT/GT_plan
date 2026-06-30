/**
 * useD7LongTerm — D7-5 账龄1年以上检查（8列）
 *
 * Spec: .kiro/specs/d7-contract-liabilities/
 * Task: 10.1
 * Requirements: 10.1-10.8
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { parseNum, calcSubtotal } from './useD7FormulaEngine'
import type { ChecklistResponse } from './useD7FormData'
import type { DetailRow } from './useD7Detail'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface LongTermRow {
  rowId: string
  customerName: string       // 客户名称
  endBalance: number         // 期末余额
  aging: string              // 账龄
  businessDescription: string // 经济业务说明
  reason: string             // 未结转或未偿还的原因
  auditDateTransfer: number  // 至审计日结转或偿还金额
  plan: string               // 处理计划
  remark: string             // 备注
}

export interface UseD7LongTermOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'D7-5-rows'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `lt-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

function safeParseRows(jsonStr: string | null | undefined): LongTermRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

function normalizeRow(raw: any): LongTermRow {
  return {
    rowId: raw.rowId || generateRowId(),
    customerName: raw.customerName || '',
    endBalance: parseNum(raw.endBalance),
    aging: raw.aging || '',
    businessDescription: raw.businessDescription || '',
    reason: raw.reason || '',
    auditDateTransfer: parseNum(raw.auditDateTransfer),
    plan: raw.plan || '',
    remark: raw.remark || '',
  }
}

function createEmptyRow(): LongTermRow {
  return {
    rowId: generateRowId(),
    customerName: '', endBalance: 0, aging: '',
    businessDescription: '', reason: '',
    auditDateTransfer: 0, plan: '', remark: '',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD7LongTerm(options: UseD7LongTermOptions) {
  const { allResponses, debouncedSave } = options

  // ─── Reactive rows ───────────────────────────────────────────────────

  const rows = ref<LongTermRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (jsonStr) => { rows.value = safeParseRows(jsonStr) },
    { immediate: true },
  )

  // ─── Persist ─────────────────────────────────────────────────────────

  function persistRows(): void {
    debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  // ─── Total Row ───────────────────────────────────────────────────────

  const totalRow: ComputedRef<{ endBalance: number; auditDateTransfer: number }> = computed(() => ({
    endBalance: calcSubtotal(rows.value.map(r => r.endBalance)),
    auditDateTransfer: calcSubtotal(rows.value.map(r => r.auditDateTransfer)),
  }))

  // ─── Add/Remove/Update ───────────────────────────────────────────────

  function addRow(): void {
    rows.value = [...rows.value, createEmptyRow()]
    persistRows()
  }

  function removeRow(rowId: string): void {
    rows.value = rows.value.filter(r => r.rowId !== rowId)
    persistRows()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    rows.value = rows.value.map(r => {
      if (r.rowId !== rowId) return r
      const updated = { ...r }
      if (field === 'endBalance' || field === 'auditDateTransfer') {
        ;(updated as any)[field] = parseNum(value)
      } else {
        ;(updated as any)[field] = value
      }
      return updated
    })
    persistRows()
  }

  // ─── Import from D7-2 (filter aging > 1 year) ───────────────────────

  function importFromD72(): void {
    const d7DetailJson = allResponses.value.get('D7-2-rows')?.remark
    if (!d7DetailJson) {
      ElMessage.info('D7-2明细表暂无数据')
      return
    }

    let detailRows: DetailRow[] = []
    try { detailRows = JSON.parse(d7DetailJson) } catch { return }

    // Filter rows where aging > 1 year (endAging2 + endAging3 + endAging4 > 0)
    const longTermRows = detailRows.filter((r: any) => {
      const aging2 = parseNum(r.endAging2)
      const aging3 = parseNum(r.endAging3)
      const aging4 = parseNum(r.endAging4)
      return aging2 + aging3 + aging4 > 0
    })

    if (longTermRows.length === 0) {
      ElMessage.info('未找到账龄超过1年的客户')
      return
    }

    // Dedup by customer name
    const existingNames = new Set(rows.value.map(r => r.customerName))
    const newRows: LongTermRow[] = longTermRows
      .filter((r: any) => !existingNames.has(r.companyName || r.contractName))
      .map((r: any) => {
        // Determine primary aging band
        const aging2 = parseNum(r.endAging2)
        const aging3 = parseNum(r.endAging3)
        const aging4 = parseNum(r.endAging4)
        let aging = '1~2年'
        if (aging4 > 0) aging = '3年以上'
        else if (aging3 > 0) aging = '2~3年'

        return normalizeRow({
          rowId: generateRowId(),
          customerName: r.companyName || r.contractName || '',
          endBalance: parseNum(r.endAudited),
          aging,
        })
      })

    if (newRows.length > 0) {
      rows.value = [...rows.value, ...newRows]
      persistRows()
      ElMessage.success(`从D7-2导入${newRows.length}个账龄超过1年的客户`)
    } else {
      ElMessage.info('所有超1年客户已存在')
    }
  }

  // ─── Audit Notes ─────────────────────────────────────────────────────

  const auditNotes = ref<{ explanation: string; conclusion: string }>({
    explanation: '',
    conclusion: '',
  })

  watch(allResponses, (map) => {
    auditNotes.value.explanation = map.get('D7-5-note-explanation')?.remark || ''
    auditNotes.value.conclusion = map.get('D7-5-note-conclusion')?.remark || ''
  }, { immediate: true })

  watch(() => auditNotes.value.explanation, (v) => debouncedSave('D7-5-note-explanation', { remark: v }))
  watch(() => auditNotes.value.conclusion, (v) => debouncedSave('D7-5-note-conclusion', { remark: v }))

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    rows,
    totalRow,
    addRow,
    removeRow,
    updateCell,
    importFromD72,
    auditNotes,
  }
}

export default useD7LongTerm
