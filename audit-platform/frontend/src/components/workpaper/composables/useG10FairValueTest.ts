/**
 * useG10FairValueTest — G10-5 公允价值测试（2区段Tab，Level3必填校验）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { parseNum } from './useG10FormulaEngine'
import { G10_FV_LEVEL_OPTIONS, G10_VALUATION_METHOD_OPTIONS } from './g10Constants'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export interface G10FairValueRow {
  rowId: string
  seq: number
  liabilityName: string
  initialDate: string
  closingUnadjustedQty: number
  closingUnadjustedPrice: number
  closingUnadjustedFV: number
  closingAuditedQty: number
  closingAuditedPrice: number
  closingAuditedFV: number
  fairValueLevel: string
  valuationMethod: string
  methodConsistentWithPrior: 'yes' | 'no' | ''
  valuationSource: string
  inputSourceAndAdjustment: string
  valuationTechnique: string
  unobservableInputDesc: string
  unobservableInputValue: string
  sensitivityAnalysis: string
  valuationDocIndex: string
}

const ITEM_ID = 'G10-fv-test-rows'
const CONCLUSION_ID = 'G10-fv-test-conclusion'
function genId() { return `g10fv-${Date.now().toString(36)}` }

function enrich(raw: Partial<G10FairValueRow> & { rowId: string }): G10FairValueRow {
  const uq = parseNum(raw.closingUnadjustedQty)
  const up = parseNum(raw.closingUnadjustedPrice)
  const aq = parseNum(raw.closingAuditedQty)
  const ap = parseNum(raw.closingAuditedPrice)
  return {
    rowId: raw.rowId,
    seq: parseNum(raw.seq) || 0,
    liabilityName: raw.liabilityName ?? '',
    initialDate: raw.initialDate ?? '',
    closingUnadjustedQty: uq,
    closingUnadjustedPrice: up,
    closingUnadjustedFV: parseNum(raw.closingUnadjustedFV) || uq * up,
    closingAuditedQty: aq,
    closingAuditedPrice: ap,
    closingAuditedFV: parseNum(raw.closingAuditedFV) || aq * ap,
    fairValueLevel: raw.fairValueLevel ?? 'Level2',
    valuationMethod: raw.valuationMethod ?? '',
    methodConsistentWithPrior: (raw.methodConsistentWithPrior as G10FairValueRow['methodConsistentWithPrior']) ?? '',
    valuationSource: raw.valuationSource ?? '',
    inputSourceAndAdjustment: raw.inputSourceAndAdjustment ?? '',
    valuationTechnique: raw.valuationTechnique ?? '',
    unobservableInputDesc: raw.unobservableInputDesc ?? '',
    unobservableInputValue: raw.unobservableInputValue ?? '',
    sensitivityAnalysis: raw.sensitivityAnalysis ?? '',
    valuationDocIndex: raw.valuationDocIndex ?? '',
  }
}

export function validateG10Level3Row(row: G10FairValueRow): string[] {
  if (row.fairValueLevel !== 'Level3') return []
  const missing: string[] = []
  if (!row.valuationTechnique?.trim()) missing.push('估值技术')
  if (!row.unobservableInputDesc?.trim()) missing.push('不可观察输入值描述')
  return missing
}

export function useG10FairValueTest(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  wpId?: Ref<string>
}) {
  const rows = ref<G10FairValueRow[]>([])
  const activeTab = ref<'basic' | 'valuation'>('basic')
  const selectedRowId = ref('')
  const conclusion = ref('')
  const aiLoading = ref(false)

  watch(() => opts.allResponses.value.get(ITEM_ID)?.remark, (j) => {
    try {
      rows.value = j
        ? JSON.parse(j).map((r: any, i: number) => enrich({ ...r, rowId: r.rowId || genId(), seq: r.seq ?? i + 1 }))
        : []
    } catch { rows.value = [] }
  }, { immediate: true })
  watch(() => opts.allResponses.value.get(CONCLUSION_ID)?.conclusion, (v) => {
    conclusion.value = v ?? ''
  }, { immediate: true })

  const level3Violations = computed(() =>
    rows.value.flatMap((r) => {
      const missing = validateG10Level3Row(r)
      return missing.length ? [{ rowId: r.rowId, liabilityName: r.liabilityName, missing }] : []
    }),
  )

  function persist() {
    opts.debouncedSave(ITEM_ID, { remark: JSON.stringify(rows.value) })
  }

  function updateCell(rowId: string, field: keyof G10FairValueRow, value: unknown) {
    if (opts.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const next = [...rows.value]
    next[idx] = enrich({ ...next[idx], [field]: value })
    rows.value = next
    persist()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('负债名称', '新增FV测试行', { inputPattern: /\S+/ })
      const row = enrich({ rowId: genId(), seq: rows.value.length + 1, liabilityName: value ?? '' })
      rows.value = [...rows.value, row]
      selectedRowId.value = row.rowId
      persist()
    } catch { /* cancel */ }
  }

  function removeRow(rowId: string) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId).map((r, i) => enrich({ ...r, seq: i + 1 }))
    persist()
  }

  function updateConclusion(v: string) {
    if (opts.isReadonly.value) return
    conclusion.value = v
    opts.debouncedSave(CONCLUSION_ID, { conclusion: v })
  }

  function validateLevel3(): boolean {
    const v = level3Violations.value
    if (v.length) {
      ElMessage.warning(`Level3 行缺少必填项：${v.map((x) => x.liabilityName).join('、')}`)
      return false
    }
    return true
  }

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value || !opts.wpId?.value) return
    aiLoading.value = true
    try {
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g10/ai/fair-value-conclusion`,
        { existingContent: conclusion.value, rows: rows.value },
        { _silent: true } as any,
      )
      const text = res?.data?.content ?? res?.content ?? ''
      if (text) updateConclusion(text)
    } catch { /* AI optional */ }
    finally { aiLoading.value = false }
  }

  return {
    rows,
    activeTab,
    selectedRowId,
    conclusion,
    aiLoading,
    level3Violations,
    updateCell,
    addRow,
    removeRow,
    updateConclusion,
    validateLevel3,
    generateAiConclusion,
    persist,
    ITEM_ID,
    G10_FV_LEVEL_OPTIONS,
    G10_VALUATION_METHOD_OPTIONS,
  }
}
