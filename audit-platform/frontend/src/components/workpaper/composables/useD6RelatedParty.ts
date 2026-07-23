/**
 * useD6RelatedParty — D6-5 关联方检查（14列）
 *
 * 公式：
 *   - 期末余额 = 期初 + 借方 - 贷方（借方科目）
 *   - 账面价值 = 期末余额 - 坏账准备
 *
 * 功能：
 *   - 从D6-2筛选关联方≠非关联方的行导入
 *   - 合计行（期初/借方/贷方/期末/坏账/账面价值各列SUM）
 *
 * Spec: .kiro/specs/d6-contract-assets/
 * Task: 10.1
 * Requirements: 10.1-10.9
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcRelatedPartyEndBalance,
  calcBookValue,
  calcSubtotal,
} from './useD6FormulaEngine'
import type { ChecklistResponse } from './useD6FormData'
import type { DetailRow } from './useD6Detail'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface RelatedPartyRow {
  rowId: string
  partyName: string        // 关联方名称
  relationship: string     // 关联关系
  priorBalance: number     // 期初余额
  debitAmount: number      // 借方发生
  creditAmount: number     // 贷方发生
  endBalance: number       // 期末余额 = 期初+借方-贷方（自动）
  impairment: number       // 坏账准备
  bookValue: number        // 账面价值 = 期末余额-坏账准备（自动）
  agingAndTiming: string   // 发生时间及账龄
  unsettledReason: string  // 未结转原因
  postSettlement: number   // 至审计日结转金额
  plan: string             // 处理计划
  indexRef: string         // 索引号
  remark: string           // 备注
}

export interface RelatedPartyTotalRow {
  priorBalance: number
  debitAmount: number
  creditAmount: number
  endBalance: number
  impairment: number
  bookValue: number
  postSettlement: number
}

export interface UseD6RelatedPartyOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'D6-5-rows'

/** 关联关系下拉选项 */
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
  return `row-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
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
    priorBalance: parseNum(raw.priorBalance),
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    endBalance: parseNum(raw.endBalance),
    impairment: parseNum(raw.impairment),
    bookValue: parseNum(raw.bookValue),
    agingAndTiming: raw.agingAndTiming || '',
    unsettledReason: raw.unsettledReason || '',
    postSettlement: parseNum(raw.postSettlement),
    plan: raw.plan || '',
    indexRef: raw.indexRef || '',
    remark: raw.remark || '',
  }
}

/**
 * 重算单行公式：
 *  endBalance = priorBalance + debitAmount - creditAmount (借方科目)
 *  bookValue = endBalance - impairment
 */
export function recalcRelatedPartyRow(row: RelatedPartyRow): RelatedPartyRow {
  const endBalance = calcRelatedPartyEndBalance(row.priorBalance, row.debitAmount, row.creditAmount)
  const bookValue = calcBookValue(endBalance, row.impairment)
  return { ...row, endBalance, bookValue }
}

function createEmptyRow(): RelatedPartyRow {
  return {
    rowId: generateRowId(),
    partyName: '',
    relationship: '',
    priorBalance: 0,
    debitAmount: 0,
    creditAmount: 0,
    endBalance: 0,
    impairment: 0,
    bookValue: 0,
    agingAndTiming: '',
    unsettledReason: '',
    postSettlement: 0,
    plan: '',
    indexRef: '',
    remark: '',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD6RelatedParty(options: UseD6RelatedPartyOptions) {
  const { allResponses, debouncedSave } = options

  // ─── Reactive rows ───────────────────────────────────────────────────

  const rows = ref<RelatedPartyRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (jsonStr) => {
      rows.value = safeParseRows(jsonStr).map(recalcRelatedPartyRow)
    },
    { immediate: true },
  )

  // ─── Persist ─────────────────────────────────────────────────────────

  function persistRows(): void {
    debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  // ─── Total Row ───────────────────────────────────────────────────────

  const totalRow: ComputedRef<RelatedPartyTotalRow> = computed(() => ({
    priorBalance: calcSubtotal(rows.value.map(r => r.priorBalance)),
    debitAmount: calcSubtotal(rows.value.map(r => r.debitAmount)),
    creditAmount: calcSubtotal(rows.value.map(r => r.creditAmount)),
    endBalance: calcSubtotal(rows.value.map(r => r.endBalance)),
    impairment: calcSubtotal(rows.value.map(r => r.impairment)),
    bookValue: calcSubtotal(rows.value.map(r => r.bookValue)),
    postSettlement: calcSubtotal(rows.value.map(r => r.postSettlement)),
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

  const NUMERIC_FIELDS = ['priorBalance', 'debitAmount', 'creditAmount', 'impairment', 'postSettlement']

  function updateCell(rowId: string, field: string, value: any): void {
    rows.value = rows.value.map(r => {
      if (r.rowId !== rowId) return r
      const updated = { ...r }
      if (NUMERIC_FIELDS.includes(field)) {
        ;(updated as any)[field] = parseNum(value)
      } else {
        ;(updated as any)[field] = value
      }
      return recalcRelatedPartyRow(updated)
    })
    persistRows()
  }

  // ─── Import from D6-2 (filter relatedPartyType ≠ '非关联方') ─────────

  function importFromDetail(): void {
    const d6DetailJson = allResponses.value.get('D6-2-rows')?.remark
    if (!d6DetailJson) return

    let detailRows: DetailRow[] = []
    try {
      detailRows = JSON.parse(d6DetailJson)
    } catch {
      return
    }

    const relatedRows = (detailRows as any[]).filter(
      r => r.relatedPartyType && r.relatedPartyType !== '非关联方',
    )

    if (relatedRows.length === 0) return

    // 去重：已存在同名关联方不重复导入
    const existingNames = new Set(rows.value.map(r => r.partyName))

    const newRows: RelatedPartyRow[] = relatedRows
      .filter(r => !existingNames.has(r.customerName))
      .map(r => {
        const row: RelatedPartyRow = {
          rowId: generateRowId(),
          partyName: r.customerName || '',
          relationship: r.relatedPartyType || '',
          priorBalance: parseNum(r.priorAudited),
          debitAmount: parseNum(r.debitAmount),
          creditAmount: parseNum(r.creditAmount),
          endBalance: 0,
          impairment: 0,
          bookValue: 0,
          agingAndTiming: '',
          unsettledReason: '',
          postSettlement: parseNum(r.postPeriodSettlement),
          plan: '',
          indexRef: '',
          remark: '',
        }
        return recalcRelatedPartyRow(row)
      })

    if (newRows.length > 0) {
      rows.value = [...rows.value, ...newRows]
      persistRows()
    }
  }

  // ─── Audit Notes ─────────────────────────────────────────────────────

  const auditNotes = ref<{ explanation: string; conclusion: string }>({
    explanation: '',
    conclusion: '',
  })

  watch(
    () => allResponses.value.get('D6-5-note-explanation')?.remark,
    (v) => { if (v) auditNotes.value.explanation = v },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get('D6-5-note-conclusion')?.remark,
    (v) => { if (v) auditNotes.value.conclusion = v },
    { immediate: true },
  )
  watch(
    () => auditNotes.value.explanation,
    (v) => debouncedSave('D6-5-note-explanation', { remark: v }),
  )
  watch(
    () => auditNotes.value.conclusion,
    (v) => debouncedSave('D6-5-note-conclusion', { remark: v }),
  )

  /**
   * 关联方完整性检查：related_party_registry中已登记但D6-2未识别的关联方
   */
  const missingRelatedParties: ComputedRef<Array<{ name: string; type: string }>> = computed(() => {
    // 从render-config project_context获取已登记关联方
    const registryRaw = allResponses.value.get('project_context_related_parties')?.remark
    let registry: Array<{ name: string; type: string }> = []
    if (registryRaw) {
      try { registry = JSON.parse(registryRaw) } catch { /* ignore */ }
    }
    if (registry.length === 0) return []

    // D6-2已识别的关联方名称集合
    const identified = new Set(
      rows.value
        .filter(r => r.partyName)
        .map(r => r.partyName.trim().toLowerCase()),
    )

    // 差集
    return registry.filter(rp => {
      const normalized = (rp.name || '').trim().toLowerCase()
      return normalized && !identified.has(normalized)
    })
  })

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    rows,
    totalRow,
    addRow,
    removeRow,
    updateCell,
    importFromDetail,
    auditNotes,
    missingRelatedParties,
  }
}

export default useD6RelatedParty
