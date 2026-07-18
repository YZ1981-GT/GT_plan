/**
 * useF3OverdueCheck — F3-5 逾期未付票据检查表
 *
 * 对齐源表15项业务字段，并额外计算期限、逾期天数、未支付金额和风险提示。
 */
import { ref, computed, watch, onBeforeUnmount, type ComputedRef } from 'vue'
import { calcOverdueDays, calcTermDays, calcSubtotal, parseNum } from './useF3FormulaEngine'
import type { UseF3BaseOptions } from './useF3Adjudication'

export const F3_OVERDUE_NOTE_TYPES = ['银行承兑汇票', '商业承兑汇票', '供应链票据', '其他'] as const
export const F3_YES_NO_OPTIONS = ['是', '否', '不适用'] as const

export interface F3OverdueNoteRow {
  rowId: string
  seq: number
  attSlot: number
  noteType: string
  ticketNo: string
  drawer: string
  acceptor: string
  payee: string
  issueDate: string
  dueDate: string
  termDays: number
  overdueDays: number
  interestRate: number
  faceValue: number
  postPaymentAmount: number
  unpaidAmount: number
  loanConditions: string
  isAdjusted: string
  collateralName: string
  collateralAmount: number
  riskFlags: string[]
}

export interface F3OverdueOcrFields {
  noteType?: string
  noteNo?: string
  drawer?: string
  acceptor?: string
  payee?: string
  issueDate?: string
  dueDate?: string
  interestRate?: number | string
  faceValue?: number | string
  postPaymentAmount?: number | string
  loanConditions?: string
  isAdjusted?: string
  collateralName?: string
  collateralAmount?: number | string
}

const STORAGE_KEY = 'F3-5-rows'

function generateRowId(): string {
  return `f3o-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function nextAttSlot(rows: F3OverdueNoteRow[]): number {
  return Math.max(0, ...rows.map((r) => Number(r.attSlot) || 0)) + 1
}

export function emptyOverdueRow(seq: number, attSlot = seq): F3OverdueNoteRow {
  return {
    rowId: generateRowId(), seq, attSlot, noteType: '', ticketNo: '', drawer: '', acceptor: '',
    payee: '', issueDate: '', dueDate: '', termDays: 0, overdueDays: 0, interestRate: 0,
    faceValue: 0, postPaymentAmount: 0, unpaidAmount: 0, loanConditions: '', isAdjusted: '',
    collateralName: '', collateralAmount: 0, riskFlags: [],
  }
}

export function isBlankOverdueRow(row: F3OverdueNoteRow): boolean {
  return !row.noteType && !row.ticketNo && !row.drawer && !row.acceptor && !row.payee
    && !row.issueDate && !row.dueDate && !row.interestRate && !row.faceValue
    && !row.postPaymentAmount && !row.loanConditions && !row.isAdjusted
    && !row.collateralName && !row.collateralAmount
}

export function computeOverdueRow(stored: F3OverdueNoteRow, asOf = new Date()): F3OverdueNoteRow {
  const termDays = calcTermDays(stored.issueDate, stored.dueDate)
  const overdueDays = calcOverdueDays(stored.dueDate, asOf)
  const unpaidAmount = Math.max(0, stored.faceValue - stored.postPaymentAmount)
  const riskFlags: string[] = []
  if (overdueDays > 90) riskFlags.push('逾期超过90天')
  else if (overdueDays > 30) riskFlags.push('逾期超过30天')
  else if (overdueDays > 0) riskFlags.push('已逾期未付')
  if (stored.faceValue > 0 && unpaidAmount > 0) riskFlags.push('期后尚未付清')
  if (overdueDays > 0 && stored.isAdjusted !== '是') riskFlags.push('调整处理待确认')
  if (stored.collateralAmount > 0 || stored.collateralName) riskFlags.push('存在抵押担保')
  if (!isBlankOverdueRow(stored) && (!stored.drawer || !stored.acceptor || !stored.payee)) {
    riskFlags.push('关系人信息不完整')
  }
  return { ...stored, termDays, overdueDays, unpaidAmount, riskFlags }
}

function migrateRow(raw: any, i: number): F3OverdueNoteRow {
  const base = emptyOverdueRow(i + 1, Number(raw.attSlot) || i + 1)
  const legacyNote = [raw.overdueReason, raw.collectionStatus, raw.auditAdvice, raw.remark]
    .filter(Boolean).join('；')
  return computeOverdueRow({
    ...base,
    rowId: raw.rowId || raw.id || generateRowId(),
    seq: raw.seq ?? i + 1,
    noteType: String(raw.noteType || ''),
    ticketNo: String(raw.ticketNo ?? raw.noteNo ?? ''),
    drawer: String(raw.drawer || ''),
    acceptor: String(raw.acceptor || ''),
    payee: String(raw.payee || ''),
    issueDate: String(raw.issueDate || ''),
    dueDate: String(raw.dueDate || ''),
    interestRate: parseNum(raw.interestRate ?? raw.rate),
    faceValue: parseNum(raw.faceValue ?? raw.amount),
    postPaymentAmount: parseNum(raw.postPaymentAmount ?? raw.subsequentPayment),
    loanConditions: String(raw.loanConditions || legacyNote),
    isAdjusted: String(raw.isAdjusted ?? raw.transferredToAp ?? raw.convertedToAP ?? ''),
    collateralName: String(raw.collateralName ?? ''),
    collateralAmount: parseNum(raw.collateralAmount),
  })
}

export function safeParseOverdueRows(jsonStr: string | null | undefined): F3OverdueNoteRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    const rows = parsed.map(migrateRow)
    const pruned = rows.filter((r) => !isBlankOverdueRow(r))
    const kept = pruned.length ? pruned : rows.slice(0, 1)
    return kept.map((r, i) => ({ ...r, seq: i + 1 }))
  } catch {
    return []
  }
}

export function useF3OverdueCheck(options: UseF3BaseOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const storedData = ref<F3OverdueNoteRow[]>([])
  const auditConclusion = ref('')

  function loadRows(): void {
    storedData.value = safeParseOverdueRows(allResponses.value.get(STORAGE_KEY)?.remark)
    if (storedData.value.length === 0) storedData.value = [computeOverdueRow(emptyOverdueRow(1))]
  }

  watch(() => allResponses.value.get(STORAGE_KEY)?.remark, (raw) => {
    if (raw && raw === JSON.stringify(storedData.value)) return
    if (storedData.value.length === 0) loadRows()
  }, { immediate: true })

  watch(() => allResponses.value.get('F3-5-conclusion')?.remark, (v) => {
    auditConclusion.value = v || ''
  }, { immediate: true })

  const rows: ComputedRef<F3OverdueNoteRow[]> = computed(() => storedData.value)
  const filledCount = computed(() => rows.value.filter((r) => !isBlankOverdueRow(r)).length)

  const summary = computed(() => ({
    count: filledCount.value,
    totalAmount: calcSubtotal(rows.value.map((r) => r.faceValue)),
    postPaymentAmount: calcSubtotal(rows.value.map((r) => r.postPaymentAmount)),
    unpaidAmount: calcSubtotal(rows.value.map((r) => r.unpaidAmount)),
    collateralAmount: calcSubtotal(rows.value.map((r) => r.collateralAmount)),
    highRisk: rows.value.filter((r) => r.overdueDays > 90 || r.riskFlags.length >= 3).length,
    adjusted: rows.value.filter((r) => r.isAdjusted === '是').length,
  }))

  function addRow(): void {
    if (readonly.value) return
    storedData.value.push(computeOverdueRow(emptyOverdueRow(storedData.value.length + 1, nextAttSlot(storedData.value))))
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (readonly.value || storedData.value.length <= 1) return
    const idx = storedData.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    storedData.value.splice(idx, 1)
    storedData.value.forEach((r, i) => { r.seq = i + 1 })
    persistRows()
  }

  function updateCell(rowId: string, field: string, value: unknown): void {
    if (readonly.value) return
    const row = storedData.value.find((r) => r.rowId === rowId)
    if (!row) return
    const numericFields = ['interestRate', 'faceValue', 'postPaymentAmount', 'collateralAmount']
    ;(row as any)[field] = numericFields.includes(field)
      ? parseNum(value as string | number | null | undefined)
      : String(value ?? '')
    const idx = storedData.value.indexOf(row)
    storedData.value[idx] = computeOverdueRow(row)
    persistRows()
  }

  function mergeOcrFields(rowId: string, fields: F3OverdueOcrFields, overwrite = false): void {
    if (readonly.value) return
    const row = storedData.value.find((r) => r.rowId === rowId)
    if (!row) return
    const mapping: Array<[keyof F3OverdueNoteRow, unknown]> = [
      ['noteType', fields.noteType], ['ticketNo', fields.noteNo], ['drawer', fields.drawer],
      ['acceptor', fields.acceptor], ['payee', fields.payee], ['issueDate', fields.issueDate],
      ['dueDate', fields.dueDate], ['interestRate', fields.interestRate],
      ['faceValue', fields.faceValue], ['postPaymentAmount', fields.postPaymentAmount],
      ['loanConditions', fields.loanConditions], ['isAdjusted', fields.isAdjusted],
      ['collateralName', fields.collateralName], ['collateralAmount', fields.collateralAmount],
    ]
    const numeric = new Set<keyof F3OverdueNoteRow>(['interestRate', 'faceValue', 'postPaymentAmount', 'collateralAmount'])
    for (const [field, value] of mapping) {
      if (value == null || value === '') continue
      const current = row[field]
      if (!overwrite && current !== '' && current !== 0) continue
      ;(row as any)[field] = numeric.has(field)
        ? parseNum(value as string | number | null | undefined)
        : String(value)
    }
    const idx = storedData.value.indexOf(row)
    storedData.value[idx] = computeOverdueRow(row)
    persistRows()
  }

  function persistRows(): void {
    allResponses.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: JSON.stringify(storedData.value) })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function flushSave(): void {
    const items = [allResponses.value.get(STORAGE_KEY), allResponses.value.get('F3-5-conclusion')].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f3:save-items', { detail: { items } }))
  }

  watch(auditConclusion, (val) => {
    allResponses.value.set('F3-5-conclusion', { item_id: 'F3-5-conclusion', conclusion: null, remark: val })
    debounceSave()
  })

  function rowClassName({ row }: { row: F3OverdueNoteRow }): string {
    if (row.overdueDays > 90 || row.riskFlags.length >= 3) return 'risk-high'
    if (row.overdueDays > 30 || row.riskFlags.length > 0) return 'risk-medium'
    return ''
  }

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; flushSave() }
  })

  return {
    rows, summary, filledCount, auditConclusion, addRow, removeRow, updateCell,
    mergeOcrFields, rowClassName,
  }
}

export default useF3OverdueCheck
