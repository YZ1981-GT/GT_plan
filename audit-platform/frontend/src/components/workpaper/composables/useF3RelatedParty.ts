/**
 * useF3RelatedParty — F3-6 应付票据关联方及交易检查表
 *
 * 期末余额 = 期初余额 + 贷方发生 - 借方发生。
 */
import { computed, onBeforeUnmount, ref, watch, type ComputedRef } from 'vue'
import { calcConcentration, calcSubtotal, parseNum } from './useF3FormulaEngine'
import type { UseF3BaseOptions } from './useF3Adjudication'

export const F3_RELATED_RELATIONSHIPS = [
  '实际控制人',
  '控股股东',
  '控股股东、实际控制人的附属企业',
  '持有5%以上股份的法人或其他组织',
  '联营企业',
  '合营企业',
  '董高监等关键管理人员',
  '其他关联方',
] as const

export const F3_RELATED_NOTE_TYPES = ['银行承兑汇票', '商业承兑汇票', '供应链票据', '其他'] as const
export const F3_RELATED_AGING_OPTIONS = ['1年以内', '1至2年', '2至3年', '3年以上'] as const
export const F3_PRICING_POLICY_OPTIONS = ['市场定价', '协议定价', '成本加成', '参考第三方价格', '其他'] as const

export interface F3RelatedPartyNoteRow {
  rowId: string
  seq: number
  partyName: string
  relationship: string
  noteType: string
  openingBalance: number
  debitMovement: number
  creditMovement: number
  closingBalance: number
  concentration: number
  aging: string
  pricingPolicy: string
  transactionReason: string
  subsequentPaymentAmount: number
  indexNo: string
  remark: string
  riskFlags: string[]
}

const STORAGE_KEY = 'F3-6-rows'

function generateRowId(): string {
  return `f3rp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function round2(value: number): number {
  return Math.round(value * 100) / 100
}

export function emptyRelatedPartyRow(seq: number): F3RelatedPartyNoteRow {
  return {
    rowId: generateRowId(), seq, partyName: '', relationship: '', noteType: '',
    openingBalance: 0, debitMovement: 0, creditMovement: 0, closingBalance: 0,
    concentration: 0, aging: '', pricingPolicy: '', transactionReason: '',
    subsequentPaymentAmount: 0, indexNo: '', remark: '', riskFlags: [],
  }
}

export function isBlankRelatedPartyRow(row: F3RelatedPartyNoteRow): boolean {
  return !row.partyName && !row.relationship && !row.noteType && !row.openingBalance
    && !row.debitMovement && !row.creditMovement && !row.aging && !row.pricingPolicy
    && !row.transactionReason && !row.subsequentPaymentAmount && !row.indexNo && !row.remark
}

export function computeRelatedPartyRow(
  stored: F3RelatedPartyNoteRow,
  totalClosing = 0,
): F3RelatedPartyNoteRow {
  const closingBalance = round2(stored.openingBalance + stored.creditMovement - stored.debitMovement)
  const concentration = calcConcentration(closingBalance, totalClosing)
  const riskFlags: string[] = []
  if (!isBlankRelatedPartyRow(stored)) {
    if (!stored.relationship) riskFlags.push('关联关系待核实')
    if (!stored.pricingPolicy) riskFlags.push('定价政策未说明')
    if (!stored.transactionReason) riskFlags.push('款项性质未说明')
    if (closingBalance < 0) riskFlags.push('期末余额为负')
    if (closingBalance > 0 && stored.subsequentPaymentAmount <= 0) riskFlags.push('无期后付款记录')
    if (stored.subsequentPaymentAmount > closingBalance && closingBalance >= 0) riskFlags.push('期后付款超过期末余额')
    if (concentration > 30) riskFlags.push('关联方余额集中度较高')
  }
  return { ...stored, closingBalance, concentration, riskFlags }
}

function migrateRow(raw: any, i: number): F3RelatedPartyNoteRow {
  const legacyFaceValue = parseNum(raw.faceValue)
  const legacyNotes = [
    raw.settlementMethod ? `结算方式：${raw.settlementMethod}` : '',
    raw.fairness ? `原公允性评价：${raw.fairness}` : '',
    raw.auditEvaluation,
    raw.remark,
  ].filter(Boolean).join('；')
  return {
    ...emptyRelatedPartyRow(i + 1),
    rowId: raw.rowId || raw.id || generateRowId(),
    seq: raw.seq ?? i + 1,
    partyName: String(raw.partyName || ''),
    relationship: String(raw.relationship || ''),
    noteType: String(raw.noteType || ''),
    openingBalance: parseNum(raw.openingBalance),
    debitMovement: parseNum(raw.debitMovement ?? raw.debit),
    creditMovement: parseNum(raw.creditMovement ?? raw.credit) || legacyFaceValue,
    aging: String(raw.aging || ''),
    pricingPolicy: String(raw.pricingPolicy || raw.fairness || ''),
    transactionReason: String(raw.transactionReason || raw.purpose || ''),
    subsequentPaymentAmount: parseNum(raw.subsequentPaymentAmount ?? raw.postPaymentAmount),
    indexNo: String(raw.indexNo || ''),
    remark: legacyNotes,
  }
}

export function safeParseRelatedPartyRows(jsonStr: string | null | undefined): F3RelatedPartyNoteRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    const base = parsed.map(migrateRow)
    const pruned = base.filter((row) => !isBlankRelatedPartyRow(row))
    const kept = pruned.length ? pruned : base.slice(0, 1)
    const total = calcSubtotal(kept.map((row) => row.openingBalance + row.creditMovement - row.debitMovement))
    return kept.map((row, i) => computeRelatedPartyRow({ ...row, seq: i + 1 }, total))
  } catch {
    return []
  }
}

export function useF3RelatedParty(options: UseF3BaseOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const storedData = ref<F3RelatedPartyNoteRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  function loadRows(): void {
    storedData.value = safeParseRelatedPartyRows(allResponses.value.get(STORAGE_KEY)?.remark)
    if (storedData.value.length === 0) storedData.value = [computeRelatedPartyRow(emptyRelatedPartyRow(1))]
  }

  watch(() => allResponses.value.get(STORAGE_KEY)?.remark, (raw) => {
    if (raw && raw === JSON.stringify(storedData.value)) return
    if (storedData.value.length === 0) loadRows()
  }, { immediate: true })

  watch(() => allResponses.value.get('F3-6-note')?.remark, (value) => {
    auditNote.value = value || ''
  }, { immediate: true })
  watch(() => allResponses.value.get('F3-6-conclusion')?.remark, (value) => {
    auditConclusion.value = value || ''
  }, { immediate: true })

  const totalClosing = computed(() => calcSubtotal(
    storedData.value.map((row) => row.openingBalance + row.creditMovement - row.debitMovement),
  ))

  const rows: ComputedRef<F3RelatedPartyNoteRow[]> = computed(() => {
    const total = totalClosing.value
    return storedData.value.map((row) => computeRelatedPartyRow(row, total))
  })

  const filledCount = computed(() => rows.value.filter((row) => !isBlankRelatedPartyRow(row)).length)
  const summary = computed(() => ({
    count: filledCount.value,
    openingBalance: calcSubtotal(rows.value.map((row) => row.openingBalance)),
    debitMovement: calcSubtotal(rows.value.map((row) => row.debitMovement)),
    creditMovement: calcSubtotal(rows.value.map((row) => row.creditMovement)),
    closingBalance: calcSubtotal(rows.value.map((row) => row.closingBalance)),
    subsequentPaymentAmount: calcSubtotal(rows.value.map((row) => row.subsequentPaymentAmount)),
    riskCount: rows.value.filter((row) => row.riskFlags.length > 0).length,
  }))

  function recomputeStored(): void {
    const total = calcSubtotal(
      storedData.value.map((row) => row.openingBalance + row.creditMovement - row.debitMovement),
    )
    storedData.value = storedData.value.map((row) => computeRelatedPartyRow(row, total))
  }

  function addRow(): void {
    if (readonly.value) return
    storedData.value.push(emptyRelatedPartyRow(storedData.value.length + 1))
    recomputeStored()
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (readonly.value || storedData.value.length <= 1) return
    const index = storedData.value.findIndex((row) => row.rowId === rowId)
    if (index === -1) return
    storedData.value.splice(index, 1)
    storedData.value.forEach((row, i) => { row.seq = i + 1 })
    recomputeStored()
    persistRows()
  }

  function updateCell(rowId: string, field: string, value: unknown): void {
    if (readonly.value) return
    const row = storedData.value.find((item) => item.rowId === rowId)
    if (!row) return
    const numericFields = ['openingBalance', 'debitMovement', 'creditMovement', 'subsequentPaymentAmount']
    ;(row as any)[field] = numericFields.includes(field)
      ? parseNum(value as string | number | null | undefined)
      : String(value ?? '')
    recomputeStored()
    persistRows()
  }

  function persistRows(): void {
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY, conclusion: null, remark: JSON.stringify(storedData.value),
    })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function flushSave(): void {
    const items = [
      allResponses.value.get(STORAGE_KEY),
      allResponses.value.get('F3-6-note'),
      allResponses.value.get('F3-6-conclusion'),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f3:save-items', { detail: { items } }))
  }

  watch(auditNote, (value) => {
    allResponses.value.set('F3-6-note', { item_id: 'F3-6-note', conclusion: null, remark: value })
    debounceSave()
  })
  watch(auditConclusion, (value) => {
    allResponses.value.set('F3-6-conclusion', {
      item_id: 'F3-6-conclusion', conclusion: null, remark: value,
    })
    debounceSave()
  })

  function rowClassName({ row }: { row: F3RelatedPartyNoteRow }): string {
    return row.riskFlags.length > 0 ? 'related-risk' : ''
  }

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; flushSave() }
  })

  return {
    rows, summary, filledCount, auditNote, auditConclusion,
    addRow, removeRow, updateCell, rowClassName,
  }
}

export default useF3RelatedParty
