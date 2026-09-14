/**
 * useF3InterestCalc — F3-4 应付票据（带息）利息测算表
 *
 * 对齐源表结构：票据类别 | 票据号 | 出票日/到期日/期限 | 票面金额 | 票面利率 |
 * 应计利息(公式) | 账面已计利息 | 差异(公式) | 说明，末尾合计行。
 * 公式：期限 = 到期日 - 出票日；应计利息 = 票面金额 × 票面利率% × 期限 / 360
 * （无日期时退化为 票面金额 × 票面利率%，与源表 ROUND(F*G,2) 一致）；
 * 差异 = 应计利息 - 账面已计利息。
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcInterest, calcTermDays, calcSubtotal } from './useF3FormulaEngine'
import type { UseF3BaseOptions } from './useF3Adjudication'
import { injectF3Adjustments, type F3InjectAdjustmentRow } from './f3AdjustmentInject'

export const F3_INTEREST_NOTE_TYPES = ['银行承兑汇票', '商业承兑汇票', '供应链票据', '其他'] as const

export interface F3InterestCalcRow {
  rowId: string
  seq: number
  /** 票据类别 */
  noteType: string
  /** 票据号 */
  ticketNo: string
  /** 出票日 */
  issueDate: string
  /** 到期日 */
  dueDate: string
  /** 期限（天）＝到期日－出票日（公式列） */
  termDays: number
  /** 票面金额 */
  faceValue: number
  /** 票面利率(%) */
  interestRate: number
  /** 应计利息（公式列） */
  payableInterest: number
  /** 账面已计利息 */
  bookInterest: number
  /** 差异（公式列）＝应计利息－账面已计利息 */
  variance: number
  /** 说明 */
  note: string
}

export interface F3NoteOcrFields {
  noteNo?: string
  noteType?: string
  drawer?: string
  acceptor?: string
  faceValue?: number | string
  interestRate?: number | string
  issueDate?: string
  dueDate?: string
  interestStart?: string
  interestEnd?: string
}

const STORAGE_KEY = 'F3-4-rows'
const VARIANCE_WARN = 100

function generateRowId(): string {
  return `f3i-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function round2(v: number): number {
  return Math.round(v * 100) / 100
}

export function emptyInterestRow(seq: number): F3InterestCalcRow {
  return {
    rowId: generateRowId(), seq, noteType: '', ticketNo: '', issueDate: '', dueDate: '',
    termDays: 0, faceValue: 0, interestRate: 0, payableInterest: 0, bookInterest: 0,
    variance: 0, note: '',
  }
}

export function isBlankInterestRow(row: F3InterestCalcRow): boolean {
  return !row.noteType && !row.ticketNo && !row.issueDate && !row.dueDate
    && !row.faceValue && !row.interestRate && !row.bookInterest && !row.note.trim()
}

export function computeInterestRow(stored: F3InterestCalcRow): F3InterestCalcRow {
  const termDays = calcTermDays(stored.issueDate, stored.dueDate)
  const payableInterest = termDays > 0
    ? round2(calcInterest(stored.faceValue, stored.interestRate, termDays))
    : round2(stored.faceValue * stored.interestRate / 100)
  const variance = round2(payableInterest - stored.bookInterest)
  return { ...stored, termDays, payableInterest, variance }
}

/** 旧数据迁移：出票人并入说明，计息起止日兜底推算期限 */
function migrateRow(raw: any, i: number): F3InterestCalcRow {
  const base = emptyInterestRow(i + 1)
  let issueDate = raw.issueDate || ''
  let dueDate = raw.dueDate || ''
  if (!issueDate && !dueDate && (raw.interestStart || raw.interestEnd)) {
    issueDate = raw.interestStart || ''
    dueDate = raw.interestEnd || ''
  }
  let note = String(raw.note ?? raw.remark ?? '')
  if (!note && raw.drawer) note = `出票人：${raw.drawer}`
  return computeInterestRow({
    ...base,
    rowId: raw.rowId || raw.id || generateRowId(),
    seq: raw.seq ?? i + 1,
    noteType: String(raw.noteType ?? ''),
    ticketNo: String(raw.ticketNo ?? raw.noteNo ?? ''),
    issueDate,
    dueDate,
    faceValue: parseNum(raw.faceValue ?? raw.principal),
    interestRate: parseNum(raw.interestRate ?? raw.rate),
    bookInterest: parseNum(raw.bookInterest ?? raw.companyInterest),
    note,
  })
}

export function safeParseInterestRows(jsonStr: string | null | undefined): F3InterestCalcRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    const rows = parsed.map(migrateRow)
    const pruned = rows.filter((r) => !isBlankInterestRow(r))
    return pruned.length ? pruned.map((r, i) => ({ ...r, seq: i + 1 })) : rows.slice(0, 1)
  } catch {
    return []
  }
}

export function useF3InterestCalc(options: UseF3BaseOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const storedData = ref<F3InterestCalcRow[]>([])
  const auditConclusion = ref('')

  function loadRows(): void {
    storedData.value = safeParseInterestRows(allResponses.value.get(STORAGE_KEY)?.remark)
    if (storedData.value.length === 0) storedData.value = [computeInterestRow(emptyInterestRow(1))]
  }

  watch(() => allResponses.value.get(STORAGE_KEY)?.remark, (raw) => {
    // 自回声守卫：persist() 写回的内容与当前状态一致时跳过，避免新增空行被立即修剪
    if (raw && raw === JSON.stringify(storedData.value)) return
    if (storedData.value.length === 0) loadRows()
  }, { immediate: true })

  watch(() => allResponses.value.get('F3-4-conclusion')?.remark, (v) => {
    auditConclusion.value = v || ''
  }, { immediate: true })

  const rows: ComputedRef<F3InterestCalcRow[]> = computed(() => storedData.value)

  const filledCount = computed(() => storedData.value.filter((r) => !isBlankInterestRow(r)).length)
  const abnormalCount = computed(() => storedData.value.filter((r) => Math.abs(r.variance) > VARIANCE_WARN).length)

  const totals = computed(() => ({
    faceValue: calcSubtotal(rows.value.map((r) => r.faceValue)),
    payableInterest: calcSubtotal(rows.value.map((r) => r.payableInterest)),
    bookInterest: calcSubtotal(rows.value.map((r) => r.bookInterest)),
    variance: calcSubtotal(rows.value.map((r) => r.variance)),
  }))

  function addRow(): void {
    if (readonly.value) return
    storedData.value.push(computeInterestRow(emptyInterestRow(storedData.value.length + 1)))
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

  function updateCell(rowId: string, field: string, value: any): void {
    if (readonly.value) return
    const row = storedData.value.find((r) => r.rowId === rowId)
    if (!row) return
    const strFields = ['noteType', 'ticketNo', 'issueDate', 'dueDate', 'note']
    if (strFields.includes(field)) (row as any)[field] = String(value ?? '')
    else (row as any)[field] = parseNum(value)
    const idx = storedData.value.indexOf(row)
    storedData.value[idx] = computeInterestRow(row)
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
    const items = [
      allResponses.value.get(STORAGE_KEY),
      allResponses.value.get('F3-4-conclusion'),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f3:save-items', { detail: { items } }))
  }

  watch(auditConclusion, (val) => {
    allResponses.value.set('F3-4-conclusion', { item_id: 'F3-4-conclusion', conclusion: null, remark: val })
    debounceSave()
  })

  function rowClassName({ row }: { row: F3InterestCalcRow }): string {
    return Math.abs(row.variance) > VARIANCE_WARN ? 'variance-warn' : ''
  }

  function mergeOcrFields(rowId: string, fields: F3NoteOcrFields, overwrite = false): void {
    if (readonly.value) return
    const row = storedData.value.find((r) => r.rowId === rowId)
    if (!row) return

    const setIf = (field: keyof F3InterestCalcRow, val: unknown): void => {
      if (val == null || val === '') return
      const cur = (row as any)[field]
      if (!overwrite && cur && cur !== 0 && cur !== '') return
      if (field === 'faceValue' || field === 'interestRate') (row as any)[field] = parseNum(val)
      else (row as any)[field] = String(val)
    }

    setIf('noteType', fields.noteType)
    setIf('ticketNo', fields.noteNo)
    setIf('faceValue', fields.faceValue)
    setIf('interestRate', fields.interestRate)
    setIf('issueDate', fields.issueDate || fields.interestStart)
    setIf('dueDate', fields.dueDate || fields.interestEnd)
    if (fields.drawer && !row.note) row.note = `出票人：${fields.drawer}`

    const idx = storedData.value.indexOf(row)
    storedData.value[idx] = computeInterestRow(row)
    persistRows()
  }

  /**
   * P1-5：带息应付票据补提/冲回利息。
   * 差异 = 应计利息 − 账面已计利息。
   *   差异 > 阈值：补提 借 财务费用(6603) / 贷 应付利息(2231)，金额 = 差异；
   *   差异 < -阈值：冲回 借 应付利息(2231) / 贷 财务费用(6603)，金额 = |差异|。
   * 幂等写入 F3-3-rows（sourceKind = interest-accrual）。
   */
  const pendingAccrualRows = computed<F3InterestCalcRow[]>(() =>
    storedData.value.filter((r) => Math.abs(r.variance) > VARIANCE_WARN),
  )

  function pushInterestAccrualToAdjustment(): { count: number; total: number } {
    if (readonly.value) return { count: 0, total: 0 }
    const targets = pendingAccrualRows.value
    const injectRows: F3InjectAdjustmentRow[] = []
    let total = 0
    for (const r of targets) {
      const diff = round2(r.variance)
      if (diff === 0) continue
      const amount = Math.abs(diff)
      const label = `${r.noteType || '带息票据'}${r.ticketNo ? `(${r.ticketNo})` : ''}`
      if (diff > 0) {
        // 补提
        injectRows.push({
          entryType: 'AJE', summary: `补提${label}利息`, accountCode: '6603', accountName: '财务费用',
          debitAmount: amount, creditAmount: 0, remark: `应计${r.payableInterest} − 账面${r.bookInterest}`,
        })
        injectRows.push({
          entryType: 'AJE', summary: `补提${label}利息`, accountCode: '2231', accountName: '应付利息',
          debitAmount: 0, creditAmount: amount, remark: '',
        })
      } else {
        // 冲回
        injectRows.push({
          entryType: 'AJE', summary: `冲回${label}多计利息`, accountCode: '2231', accountName: '应付利息',
          debitAmount: amount, creditAmount: 0, remark: `账面${r.bookInterest} − 应计${r.payableInterest}`,
        })
        injectRows.push({
          entryType: 'AJE', summary: `冲回${label}多计利息`, accountCode: '6603', accountName: '财务费用',
          debitAmount: 0, creditAmount: amount, remark: '',
        })
      }
      total += diff
    }
    injectF3Adjustments(allResponses.value, injectRows, 'interest-accrual')
    return { count: targets.length, total: round2(total) }
  }

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; flushSave() }
  })

  return {
    rows, totals, filledCount, abnormalCount, auditConclusion,
    addRow, removeRow, updateCell, rowClassName, mergeOcrFields,
    varianceWarn: VARIANCE_WARN,
    pendingAccrualRows, pushInterestAccrualToAdjustment,
  }
}

export default useF3InterestCalc
