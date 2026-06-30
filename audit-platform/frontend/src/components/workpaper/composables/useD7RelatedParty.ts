/**
 * useD7RelatedParty — D7-6 关联方检查（11列，贷方科目公式）
 *
 * 公式：期末余额 = 期初余额 + 贷方发生 - 借方发生（贷方科目）
 *
 * Spec: .kiro/specs/d7-contract-liabilities/
 * Task: 11.1
 * Requirements: 11.1-11.9
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { parseNum, calcCreditEndBalance, calcSubtotal } from './useD7FormulaEngine'
import type { ChecklistResponse } from './useD7FormData'
import type { DetailRow } from './useD7Detail'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface RelatedPartyRow {
  rowId: string
  partyName: string          // 关联方名称
  relationship: string       // 关联关系
  openingBalance: number     // 期初余额
  debitAmount: number        // 借方发生
  creditAmount: number       // 贷方发生
  endBalance: number         // 期末余额（自动：期初+贷方-借方）
  agingTime: string          // 发生时间及账龄
  reason: string             // 未结转或未偿还的原因
  auditDateTransfer: number  // 至审计日结转或偿还金额
  plan: string               // 处理计划
  remark: string             // 备注
}

export interface RelatedPartyTotalRow {
  openingBalance: number
  debitAmount: number
  creditAmount: number
  endBalance: number
  auditDateTransfer: number
}

export interface UseD7RelatedPartyOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'D7-6-rows'

export const RELATIONSHIP_OPTIONS = [
  '实际控制人',
  '控股股东',
  '控股股东附属企业',
  '持有5%以上表决权股份的股东',
  '联营企业',
  '合营企业',
  '董事/监事/高管',
  '其他关联方',
] as const

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `rp-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

function safeParseRows(jsonStr: string | null | undefined): RelatedPartyRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

function normalizeRow(raw: any): RelatedPartyRow {
  return {
    rowId: raw.rowId || generateRowId(),
    partyName: raw.partyName || '',
    relationship: raw.relationship || '',
    openingBalance: parseNum(raw.openingBalance),
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    endBalance: parseNum(raw.endBalance),
    agingTime: raw.agingTime || '',
    reason: raw.reason || '',
    auditDateTransfer: parseNum(raw.auditDateTransfer),
    plan: raw.plan || '',
    remark: raw.remark || '',
  }
}

/**
 * 贷方科目公式：期末余额 = 期初 + 贷方 - 借方
 */
function recalcRow(row: RelatedPartyRow): RelatedPartyRow {
  const endBalance = calcCreditEndBalance(row.openingBalance, row.creditAmount, row.debitAmount)
  return { ...row, endBalance }
}

function createEmptyRow(): RelatedPartyRow {
  return {
    rowId: generateRowId(),
    partyName: '', relationship: '',
    openingBalance: 0, debitAmount: 0, creditAmount: 0, endBalance: 0,
    agingTime: '', reason: '', auditDateTransfer: 0, plan: '', remark: '',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD7RelatedParty(options: UseD7RelatedPartyOptions) {
  const { allResponses, debouncedSave } = options

  // ─── Reactive rows ───────────────────────────────────────────────────

  const rows = ref<RelatedPartyRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (jsonStr) => { rows.value = safeParseRows(jsonStr).map(recalcRow) },
    { immediate: true },
  )

  // ─── Persist ─────────────────────────────────────────────────────────

  function persistRows(): void {
    debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  // ─── Total Row ───────────────────────────────────────────────────────

  const totalRow: ComputedRef<RelatedPartyTotalRow> = computed(() => ({
    openingBalance: calcSubtotal(rows.value.map(r => r.openingBalance)),
    debitAmount: calcSubtotal(rows.value.map(r => r.debitAmount)),
    creditAmount: calcSubtotal(rows.value.map(r => r.creditAmount)),
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

  const NUMERIC_FIELDS = ['openingBalance', 'debitAmount', 'creditAmount', 'auditDateTransfer']

  function updateCell(rowId: string, field: string, value: any): void {
    rows.value = rows.value.map(r => {
      if (r.rowId !== rowId) return r
      const updated = { ...r }
      if (NUMERIC_FIELDS.includes(field)) {
        ;(updated as any)[field] = parseNum(value)
      } else {
        ;(updated as any)[field] = value
      }
      return recalcRow(updated)
    })
    persistRows()
  }

  // ─── Import from D7-2 (filter 关联关系≠非关联方) ─────────────────────

  function importFromD72(): void {
    const d7DetailJson = allResponses.value.get('D7-2-rows')?.remark
    if (!d7DetailJson) {
      ElMessage.info('D7-2明细表暂无数据')
      return
    }

    let detailRows: DetailRow[] = []
    try { detailRows = JSON.parse(d7DetailJson) } catch { return }

    const relatedRows = (detailRows as any[]).filter(
      r => r.relatedPartyType && r.relatedPartyType !== '非关联方',
    )

    if (relatedRows.length === 0) {
      ElMessage.info('未找到关联方客户')
      return
    }

    // Dedup by party name
    const existingNames = new Set(rows.value.map(r => r.partyName))
    const newRows: RelatedPartyRow[] = relatedRows
      .filter(r => !existingNames.has(r.companyName))
      .map(r => recalcRow(normalizeRow({
        rowId: generateRowId(),
        partyName: r.companyName || '',
        relationship: r.relatedPartyType || '',
        openingBalance: parseNum(r.priorAudited),
        debitAmount: parseNum(r.debitAmount),
        creditAmount: parseNum(r.creditAmount),
        auditDateTransfer: parseNum(r.postTransfer),
      })))

    if (newRows.length > 0) {
      rows.value = [...rows.value, ...newRows]
      persistRows()
      ElMessage.success(`从D7-2导入${newRows.length}个关联方客户`)
    } else {
      ElMessage.info('所有关联方客户已存在')
    }
  }

  // ─── Audit Notes ─────────────────────────────────────────────────────

  const auditNotes = ref<{ explanation: string; conclusion: string }>({
    explanation: '',
    conclusion: '',
  })

  watch(allResponses, (map) => {
    auditNotes.value.explanation = map.get('D7-6-note-explanation')?.remark || ''
    auditNotes.value.conclusion = map.get('D7-6-note-conclusion')?.remark || ''
  }, { immediate: true })

  watch(() => auditNotes.value.explanation, (v) => debouncedSave('D7-6-note-explanation', { remark: v }))
  watch(() => auditNotes.value.conclusion, (v) => debouncedSave('D7-6-note-conclusion', { remark: v }))

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

export default useD7RelatedParty
