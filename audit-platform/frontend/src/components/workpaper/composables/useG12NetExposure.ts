/**
 * useG12NetExposure — G12-5 风险净敞口检查（79行5section）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { G12_NET_EXPOSURE_SEED } from './g12NetExposureSeed'
import type { ChecklistResponse } from './useF1FormData'

export interface G12NetExposureRow {
  rowId: string
  seq: number
  sectionNo: string
  sectionTitle: string
  checkArea: string
  checkItem: string
  auditRequirement: string
  checkResult: string
  compliance: '' | 'compliant' | 'non_compliant' | 'not_applicable'
  riskLevel: '' | 'high' | 'medium' | 'low'
  conclusion: string
  indexRef: string
  remark: string
}

const ITEM_ID = 'G12-net-exposure-rows'
const CONCLUSION_ID = 'G12-net-exposure-conclusion'
function genId() { return `g12ne-${Date.now().toString(36)}` }

function defaultRows(): G12NetExposureRow[] {
  return G12_NET_EXPOSURE_SEED.map((s, i) => ({
    rowId: genId() + i,
    seq: i + 1,
    sectionNo: s.sectionNo,
    sectionTitle: s.sectionTitle,
    checkArea: s.checkArea,
    checkItem: s.checkItem,
    auditRequirement: s.auditRequirement,
    checkResult: '',
    compliance: '' as const,
    riskLevel: '' as const,
    conclusion: '',
    indexRef: '',
    remark: '',
  }))
}

export function useG12NetExposure(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rows = ref<G12NetExposureRow[]>(defaultRows())
  const overallConclusion = ref('')
  const useVirtualScroll = computed(() => rows.value.length > 50)

  watch(() => opts.allResponses.value.get(ITEM_ID)?.remark, (j) => {
    if (!j) { rows.value = defaultRows(); return }
    try {
      const parsed = JSON.parse(j)
      rows.value = Array.isArray(parsed) && parsed.length ? parsed : defaultRows()
    } catch { rows.value = defaultRows() }
  }, { immediate: true })
  watch(() => opts.allResponses.value.get(CONCLUSION_ID)?.conclusion, (v) => { overallConclusion.value = v ?? '' }, { immediate: true })

  const sections = computed(() => {
    const map = new Map<string, G12NetExposureRow[]>()
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

  function updateCell(rowId: string, field: keyof G12NetExposureRow, value: unknown) {
    if (opts.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const next = [...rows.value]
    next[idx] = { ...next[idx], [field]: value }
    rows.value = next
    if (!missingCompliance.value.length) {
      persist()
    }
  }

  function updateOverallConclusion(v: string) {
    if (opts.isReadonly.value) return
    overallConclusion.value = v
    opts.debouncedSave(CONCLUSION_ID, { conclusion: v })
  }

  function validateBeforeSave(): boolean {
    const missing = missingCompliance.value
    if (missing.length) {
      ElMessage.warning(`还有 ${missing.length} 行未选择「是否合规」`)
      return false
    }
    return true
  }

  function saveValidated(): boolean {
    if (!validateBeforeSave()) return false
    persist()
    ElMessage.success('校验通过，已保存')
    return true
  }

  return {
    rows,
    sections,
    overallConclusion,
    useVirtualScroll,
    missingCompliance,
    updateCell,
    updateOverallConclusion,
    validateBeforeSave,
    saveValidated,
    persist,
    ITEM_ID,
  }
}
