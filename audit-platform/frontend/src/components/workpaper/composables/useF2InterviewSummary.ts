/**
 * useF2InterviewSummary — F2-71 供应商访谈记录汇总（41行×9列）
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'

export const INTERVIEW_METHODS = ['现场访谈', '视频访谈', '电话访谈', '书面问询'] as const
export const INTERVIEW_CONCLUSIONS = ['无异常', '存在疑点', '需进一步核查', '异常'] as const

export type InterviewMethod = typeof INTERVIEW_METHODS[number]
export type InterviewConclusion = typeof INTERVIEW_CONCLUSIONS[number]

export interface InterviewSummaryRow {
  id: string
  supplierName: string
  interviewDate: string
  method: InterviewMethod | ''
  interviewee: string
  intervieweeTitle: string
  summary: string
  concerns: string
  conclusion: InterviewConclusion | ''
}

export interface EnrichedInterviewSummaryRow extends InterviewSummaryRow {
  isFlagged: boolean
  highlight: boolean
}

const ROWS_KEY = 'F2-71-rows'
const NOTE_KEY = 'F2-71-note'

function emptyRow(id: string): InterviewSummaryRow {
  return {
    id, supplierName: '', interviewDate: '', method: '',
    interviewee: '', intervieweeTitle: '', summary: '', concerns: '', conclusion: '',
  }
}

export function enrichInterviewSummaryRow(r: InterviewSummaryRow): EnrichedInterviewSummaryRow {
  const isFlagged = r.conclusion === '异常' || r.conclusion === '存在疑点'
  return { ...r, isFlagged, highlight: isFlagged }
}

export function useF2InterviewSummary(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const searchQuery = ref('')
  const rows = ref<InterviewSummaryRow[]>([emptyRow('1')])
  const auditNote = ref('')

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as InterviewSummaryRow[]
        if (parsed.length) rows.value = parsed
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const enrichedRows = computed(() => rows.value.map(enrichInterviewSummaryRow))

  const filteredRows = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return enrichedRows.value
    return enrichedRows.value.filter((r) =>
      r.supplierName.toLowerCase().includes(q)
      || r.interviewee.toLowerCase().includes(q),
    )
  })

  const conclusionSummary = computed(() => ({
    total: enrichedRows.value.length,
    normal: enrichedRows.value.filter((r) => r.conclusion === '无异常').length,
    doubt: enrichedRows.value.filter((r) => r.conclusion === '存在疑点').length,
    review: enrichedRows.value.filter((r) => r.conclusion === '需进一步核查').length,
    abnormal: enrichedRows.value.filter((r) => r.conclusion === '异常').length,
  }))

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(ROWS_KEY),
      opts.allResponses.value.get(NOTE_KEY),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items } }))
  }

  function persist(): void {
    opts.allResponses.value.set(ROWS_KEY, {
      item_id: ROWS_KEY, conclusion: null, remark: JSON.stringify(rows.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function updateRow(id: string, patch: Partial<InterviewSummaryRow>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    persist()
  }

  async function addRow(): Promise<void> {
    if (readonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入供应商名称', '新增访谈汇总', {
        confirmButtonText: '确定', cancelButtonText: '取消',
      })
      rows.value = [...rows.value, { ...emptyRow(String(Date.now())), supplierName: value }]
      persist()
    } catch { /* cancelled */ }
  }

  function removeRow(id: string): void {
    if (readonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id)
    persist()
  }

  watch(auditNote, (val) => {
    if (readonly.value) return
    opts.allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  })

  onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushSave() } })

  return {
    searchQuery,
    filteredRows,
    conclusionSummary,
    auditNote,
    updateRow,
    addRow,
    removeRow,
    INTERVIEW_METHODS,
    INTERVIEW_CONCLUSIONS,
  }
}

export default useF2InterviewSummary
