/**
 * useF1LongTerm — F1-5 账龄1年及以上大额预付账款检查表
 *
 * 对齐 Excel 13 列：债务人|期末余额|账龄|业务说明|未结转原因|计划供货/退款|
 * 是否诉讼|是否转其他应收|坏账准备|审定余额(自动)|期后供货退款|支持性证据|备注
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useF1FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import type { LongTermImportRow } from './useF1CrossSheet'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface LongTermRow {
  rowId: string
  customerName: string              // A: 债务人名称
  endBalance: number                // B: 期末余额
  aging: string                     // C: 账龄
  businessDescription: string       // D: 经济业务说明
  reason: string                    // E: 未偿还或未结转的原因
  plan: string                      // F: 计划供货还是退款
  isLitigation: string              // G: 是否诉讼 Y/N
  transferToOtherReceivable: string // H: 是否转入其他应收款 Y/N
  badDebtProvision: number          // I: 计提坏账准备金额
  auditedBalance: number            // J: 审定余额 = B − I（自动）
  postSettlementAmount: number      // K: 期后供货或退款金额
  supportingEvidence: string        // L: 支持性证据
  remark: string                    // M: 备注
}

export interface UseD3LongTermOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'F1-lt-rows'
const ITEM_ID_NOTE = 'F1-lt-note'
const ITEM_ID_CONCLUSION = 'F1-lt-conclusion'

const YES_NO = ['Y', 'N'] as const

// ─── Pure helpers ────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)}`
}

/** 审定余额 = 期末余额 − 坏账准备 */
export function calcAuditedBalance(endBalance: number, badDebtProvision: number): number {
  return parseNum(endBalance) - parseNum(badDebtProvision)
}

export function recalcLongTermRow(row: LongTermRow): LongTermRow {
  return {
    ...row,
    auditedBalance: calcAuditedBalance(row.endBalance, row.badDebtProvision),
  }
}

export function normalizeLongTermRow(raw: any): LongTermRow {
  const endBalance = parseNum(raw.endBalance)
  const badDebtProvision = parseNum(raw.badDebtProvision)
  return recalcLongTermRow({
    rowId: raw.rowId || generateRowId(),
    customerName: raw.customerName || '',
    endBalance,
    aging: raw.aging || '',
    businessDescription: raw.businessDescription || '',
    reason: raw.reason || raw.unsettledReason || '',
    plan: raw.plan || '',
    isLitigation: normalizeYn(raw.isLitigation),
    transferToOtherReceivable: normalizeYn(raw.transferToOtherReceivable),
    badDebtProvision,
    auditedBalance: parseNum(raw.auditedBalance),
    postSettlementAmount: parseNum(
      raw.postSettlementAmount ?? raw.settlementAmount ?? raw.settledAmount,
    ),
    supportingEvidence: raw.supportingEvidence || '',
    remark: raw.remark || '',
  })
}

function normalizeYn(val: any): string {
  if (val == null || val === '') return ''
  const s = String(val).trim().toUpperCase()
  if (s === 'Y' || s === '是' || s === 'TRUE' || s === '1') return 'Y'
  if (s === 'N' || s === '否' || s === 'FALSE' || s === '0') return 'N'
  return YES_NO.includes(s as any) ? s : ''
}

export function createEmptyLongTermRow(): LongTermRow {
  return {
    rowId: generateRowId(),
    customerName: '',
    endBalance: 0,
    aging: '',
    businessDescription: '',
    reason: '',
    plan: '',
    isLitigation: '',
    transferToOtherReceivable: '',
    badDebtProvision: 0,
    auditedBalance: 0,
    postSettlementAmount: 0,
    supportingEvidence: '',
    remark: '',
  }
}

function safeParseRows(jsonStr: string | null | undefined): LongTermRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeLongTermRow) : []
  } catch {
    return []
  }
}

/** 从 F1-2 超1年行合并导入（同名更新余额/账龄，保留已填说明） */
export function mergeLongTermFromImport(
  existing: LongTermRow[],
  imported: LongTermImportRow[],
): LongTermRow[] {
  const map = new Map(existing.map(r => [r.customerName, r]))
  for (const src of imported) {
    const name = src.customerName || ''
    if (!name) continue
    const prev = map.get(name)
    if (prev) {
      map.set(
        name,
        recalcLongTermRow({
          ...prev,
          endBalance: src.endAudited,
          aging: src.agingDescription || prev.aging,
        }),
      )
    } else {
      map.set(
        name,
        recalcLongTermRow({
          ...createEmptyLongTermRow(),
          customerName: name,
          endBalance: src.endAudited,
          aging: src.agingDescription || '',
        }),
      )
    }
  }
  return Array.from(map.values())
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useF1LongTerm(options: UseD3LongTermOptions) {
  const { allResponses, debouncedSave, isReadonly } = options

  const rows = ref<LongTermRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (jsonStr) => { rows.value = safeParseRows(jsonStr) },
    { immediate: true },
  )

  function persistRows(): void {
    debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  const subtotalRow = computed(() => ({
    endBalance: calcSubtotal(rows.value.map(r => r.endBalance)),
    badDebtProvision: calcSubtotal(rows.value.map(r => r.badDebtProvision)),
    auditedBalance: calcSubtotal(rows.value.map(r => r.auditedBalance)),
    postSettlementAmount: calcSubtotal(rows.value.map(r => r.postSettlementAmount)),
  }))

  function importFromCrossSheet(longTermRows: LongTermImportRow[]): void {
    if (isReadonly.value) return
    if (longTermRows.length === 0) return
    rows.value = mergeLongTermFromImport(rows.value, longTermRows)
    persistRows()
  }

  function addRow(): void {
    if (isReadonly.value) return
    rows.value = [...rows.value, createEmptyLongTermRow()]
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    rows.value = rows.value.filter(r => r.rowId !== rowId)
    persistRows()
  }

  const NUMERIC_FIELDS = new Set([
    'endBalance',
    'badDebtProvision',
    'postSettlementAmount',
  ])

  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return

    const row = { ...rows.value[idx] }
    if (NUMERIC_FIELDS.has(field)) {
      ;(row as any)[field] = parseNum(value)
    } else if (field === 'isLitigation' || field === 'transferToOtherReceivable') {
      ;(row as any)[field] = normalizeYn(value)
    } else {
      ;(row as any)[field] = value
    }

    const newRows = [...rows.value]
    newRows[idx] = recalcLongTermRow(row)
    rows.value = newRows
    persistRows()
  }

  const auditNote = ref('')
  const conclusion = ref('')

  watch(
    () => allResponses.value.get(ITEM_ID_NOTE)?.remark,
    (val) => { auditNote.value = val || '' },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get(ITEM_ID_CONCLUSION)?.remark,
    (val) => { conclusion.value = val || '' },
    { immediate: true },
  )
  watch(() => auditNote.value, (val) => { if (!isReadonly.value) debouncedSave(ITEM_ID_NOTE, { remark: val }) })
  watch(() => conclusion.value, (val) => { if (!isReadonly.value) debouncedSave(ITEM_ID_CONCLUSION, { remark: val }) })

  return {
    rows,
    subtotalRow,
    auditNote,
    conclusion,
    addRow,
    removeRow,
    updateCell,
    importFromCrossSheet,
  }
}

export default useF1LongTerm
