/**
 * useG10ClassificationCheck — G10-4 分类适当性检查（28行4section问卷）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { G10_CLASSIFICATION_SEED } from './g10ClassificationSeed'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export interface G10ClassificationRow {
  rowId: string
  seq: number
  sectionNo: string
  sectionTitle: string
  checkItem: string
  auditRequirement: string
  managementReply: string
  compliance: '' | 'compliant' | 'non_compliant' | 'not_applicable'
  conclusion: string
  indexRef: string
}

const ITEM_ID = 'G10-classification-rows'
const CONCLUSION_ID = 'G10-classification-conclusion'
function genId() { return `g10cl-${Date.now().toString(36)}` }

function defaultRows(): G10ClassificationRow[] {
  return G10_CLASSIFICATION_SEED.map((s, i) => ({
    rowId: genId() + i,
    seq: i + 1,
    sectionNo: s.sectionNo,
    sectionTitle: s.sectionTitle,
    checkItem: s.checkItem,
    auditRequirement: s.auditRequirement,
    managementReply: '',
    compliance: '' as const,
    conclusion: '',
    indexRef: '',
  }))
}

export function useG10ClassificationCheck(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  wpId?: Ref<string>
}) {
  const rows = ref<G10ClassificationRow[]>(defaultRows())
  const overallConclusion = ref('')
  const aiLoading = ref(false)

  watch(() => opts.allResponses.value.get(ITEM_ID)?.remark, (j) => {
    if (!j) { rows.value = defaultRows(); return }
    try {
      const parsed = JSON.parse(j)
      rows.value = Array.isArray(parsed) && parsed.length ? parsed : defaultRows()
    } catch { rows.value = defaultRows() }
  }, { immediate: true })
  watch(() => opts.allResponses.value.get(CONCLUSION_ID)?.conclusion, (v) => {
    overallConclusion.value = v ?? ''
  }, { immediate: true })

  const sections = computed(() => {
    const map = new Map<string, G10ClassificationRow[]>()
    for (const r of rows.value) {
      const key = `${r.sectionNo} ${r.sectionTitle}`
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(r)
    }
    return [...map.entries()].map(([title, sectionRows]) => ({ title, rows: sectionRows }))
  })

  const missingCompliance = computed(() => rows.value.filter((r) => !r.compliance))

  function persist() {
    opts.debouncedSave(ITEM_ID, { remark: JSON.stringify(rows.value) })
  }

  function updateCell(rowId: string, field: keyof G10ClassificationRow, value: unknown) {
    if (opts.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const next = [...rows.value]
    next[idx] = { ...next[idx], [field]: value }
    rows.value = next
    persist()
  }

  function updateOverallConclusion(v: string) {
    if (opts.isReadonly.value) return
    overallConclusion.value = v
    opts.debouncedSave(CONCLUSION_ID, { conclusion: v })
  }

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value || !opts.wpId?.value) return
    aiLoading.value = true
    try {
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g10/ai/classification-conclusion`,
        { existingContent: overallConclusion.value, rows: rows.value },
        { _silent: true } as any,
      )
      const text = res?.data?.content ?? res?.content ?? ''
      if (text) updateOverallConclusion(text)
    } catch { /* AI optional */ }
    finally { aiLoading.value = false }
  }

  function validateBeforeSave(): boolean {
    const missing = missingCompliance.value
    if (missing.length) {
      ElMessage.warning(`还有 ${missing.length} 行未选择「是否合规」`)
      return false
    }
    return true
  }

  return {
    rows,
    sections,
    overallConclusion,
    aiLoading,
    missingCompliance,
    updateCell,
    updateOverallConclusion,
    generateAiConclusion,
    validateBeforeSave,
    persist,
    ITEM_ID,
  }
}
