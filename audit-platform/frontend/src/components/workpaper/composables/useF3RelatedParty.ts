/**
 * useF3RelatedParty — F3-6 关联方检查（16列）
 * Spec: .kiro/specs/f3-notes-payable/ Task 5.4
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { calcConcentration, calcSubtotal, calcTermDays, parseNum } from './useF3FormulaEngine'
import type { ChecklistResponse } from './useF3FormData'
import type { UseF3BaseOptions } from './useF3Adjudication'

export interface F3RelatedPartyNoteRow {
  rowId: string
  seq: number
  partyName: string
  relationship: string
  noteType: string
  faceValue: number
  issueDate: string
  dueDate: string
  term: number
  rate: number
  purpose: string
  concentration: number
  isNormalSettlement: string
  settlementMethod: string
  fairness: string
  auditEvaluation: string
  remark: string
}

const STORAGE_KEY = 'F3-6-rows'

function generateRowId(): string {
  return `f3rp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function emptyRow(seq: number): F3RelatedPartyNoteRow {
  return {
    rowId: generateRowId(), seq, partyName: '', relationship: '', noteType: '银行承兑',
    faceValue: 0, issueDate: '', dueDate: '', term: 0, rate: 0, purpose: '',
    concentration: 0, isNormalSettlement: '是', settlementMethod: '', fairness: '公允',
    auditEvaluation: '', remark: '',
  }
}

function computeRow(stored: F3RelatedPartyNoteRow, totalFace: number): F3RelatedPartyNoteRow {
  const term = stored.term > 0 ? stored.term : calcTermDays(stored.issueDate, stored.dueDate)
  const concentration = calcConcentration(stored.faceValue, totalFace)
  return { ...stored, term, concentration }
}

function safeParseRows(jsonStr: string | null | undefined): F3RelatedPartyNoteRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    const base = parsed.map((raw: any, i: number) => ({
      ...emptyRow(i + 1),
      rowId: raw.rowId || raw.id || generateRowId(),
      seq: raw.seq ?? i + 1,
      partyName: raw.partyName || '',
      relationship: raw.relationship || '',
      noteType: raw.noteType || '银行承兑',
      faceValue: parseNum(raw.faceValue),
      issueDate: raw.issueDate || '',
      dueDate: raw.dueDate || '',
      term: parseNum(raw.term ?? raw.termDays),
      rate: parseNum(raw.rate),
      purpose: raw.purpose || '',
      isNormalSettlement: raw.isNormalSettlement || '是',
      settlementMethod: raw.settlementMethod || '',
      fairness: raw.fairness || '公允',
      auditEvaluation: raw.auditEvaluation || '',
      remark: raw.remark || '',
    }))
    const total = calcSubtotal(base.map((r) => r.faceValue))
    return base.map((r) => computeRow(r, total))
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

  function loadRows(): void {
    storedData.value = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    if (storedData.value.length === 0) storedData.value = [computeRow(emptyRow(1), 0)]
  }

  watch(() => allResponses.value.get(STORAGE_KEY)?.remark, () => {
    if (storedData.value.length === 0) loadRows()
  }, { immediate: true })

  watch(() => allResponses.value.get('F3-6-note')?.remark, (v) => {
    auditNote.value = v || ''
  }, { immediate: true })

  const totalFace = computed(() => calcSubtotal(storedData.value.map((r) => r.faceValue)))

  const rows: ComputedRef<F3RelatedPartyNoteRow[]> = computed(() => {
    const t = totalFace.value
    return storedData.value.map((r) => computeRow(r, t))
  })

  const summary = computed(() => ({
    totalFace: totalFace.value,
    unfairCount: rows.value.filter((r) => r.fairness === '不公允').length,
  }))

  function recomputeStored(): void {
    const t = calcSubtotal(storedData.value.map((r) => r.faceValue))
    storedData.value = storedData.value.map((r) => computeRow(r, t))
  }

  function addRow(): void {
    if (readonly.value) return
    storedData.value.push(emptyRow(storedData.value.length + 1))
    recomputeStored()
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (readonly.value || storedData.value.length <= 1) return
    const idx = storedData.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    storedData.value.splice(idx, 1)
    storedData.value.forEach((r, i) => { r.seq = i + 1 })
    recomputeStored()
    persistRows()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (readonly.value) return
    const row = storedData.value.find((r) => r.rowId === rowId)
    if (!row) return
    const strFields = ['partyName', 'relationship', 'noteType', 'issueDate', 'dueDate', 'purpose',
      'isNormalSettlement', 'settlementMethod', 'fairness', 'auditEvaluation', 'remark']
    if (strFields.includes(field)) (row as any)[field] = String(value ?? '')
    else (row as any)[field] = parseNum(value)
    recomputeStored()
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
    const items = [allResponses.value.get(STORAGE_KEY), allResponses.value.get('F3-6-note')].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f3:save-items', { detail: { items } }))
  }

  watch(auditNote, (val) => {
    allResponses.value.set('F3-6-note', { item_id: 'F3-6-note', conclusion: null, remark: val })
    debounceSave()
  })

  function rowClassName({ row }: { row: F3RelatedPartyNoteRow }): string {
    return row.concentration > 30 ? 'concentration-warn' : ''
  }

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; flushSave() }
  })

  return { rows, totalFace, summary, auditNote, addRow, removeRow, updateCell, rowClassName }
}

export default useF3RelatedParty
