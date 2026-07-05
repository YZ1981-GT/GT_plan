/**
 * useG8DesignationCheck — G8-5 指定适当性检查（CAS22 4-section 问卷）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { G8_DESIGNATION_SEED } from './g8DesignationSeed'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export interface G8DesignationRow {
  rowId: string
  seq: number
  sectionNo: string
  sectionTitle: string
  checkItem: string
  auditRequirement: string
  evidenceOrReply: string
  compliance: '' | 'compliant' | 'non_compliant' | 'not_applicable'
  auditConclusion: string
  indexRef: string
}

const ITEM_ID_ROWS = 'G8-designation-rows'
const ITEM_ID_CONCLUSION = 'G8-designation-conclusion'

function genId(): string {
  return `g8dc-${Date.now().toString(36)}`
}

function defaultRows(): G8DesignationRow[] {
  return G8_DESIGNATION_SEED.map((s, i) => ({
    rowId: genId() + i,
    seq: i + 1,
    sectionNo: s.sectionNo,
    sectionTitle: s.sectionTitle,
    checkItem: s.checkItem,
    auditRequirement: s.auditRequirement,
    evidenceOrReply: '',
    compliance: '' as const,
    auditConclusion: '',
    indexRef: '',
  }))
}

export function useG8DesignationCheck(opts: {
  wpId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rows = ref<G8DesignationRow[]>(defaultRows())
  const overallConclusion = ref('')
  const aiLoading = ref(false)

  watch(() => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark, (j) => {
    if (!j) { rows.value = defaultRows(); return }
    try {
      const parsed = JSON.parse(j)
      rows.value = Array.isArray(parsed) && parsed.length ? parsed : defaultRows()
    } catch { rows.value = defaultRows() }
  }, { immediate: true })

  watch(() => opts.allResponses.value.get(ITEM_ID_CONCLUSION)?.conclusion, (v) => {
    overallConclusion.value = v ?? ''
  }, { immediate: true })

  const sections = computed(() => {
    const map = new Map<string, G8DesignationRow[]>()
    for (const r of rows.value) {
      const key = `${r.sectionNo} ${r.sectionTitle}`
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(r)
    }
    return [...map.entries()].map(([title, sectionRows]) => ({ title, rows: sectionRows }))
  })

  const missingCompliance = computed(() => rows.value.filter((r) => !r.compliance))

  function persist(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  function updateCell(rowId: string, field: keyof G8DesignationRow, value: unknown): void {
    if (opts.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const next = [...rows.value]
    next[idx] = { ...next[idx], [field]: value }
    rows.value = next
    persist()
  }

  function updateOverallConclusion(v: string): void {
    if (opts.isReadonly.value) return
    overallConclusion.value = v
    opts.debouncedSave(ITEM_ID_CONCLUSION, { conclusion: v })
  }

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value || !opts.wpId.value) return
    aiLoading.value = true
    try {
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g8/ai/designation-conclusion`,
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
  }
}
