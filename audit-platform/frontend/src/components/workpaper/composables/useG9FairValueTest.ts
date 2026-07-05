/**
 * useG9FairValueTest — G9-4 公允价值测试
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { G9_FV_LEVEL_OPTIONS, G9_VALUATION_METHOD_OPTIONS } from './g9Constants'
import { parseNum, calcFairValueDiff } from './useG9FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface G9FairValueRow {
  rowId: string
  seq: number
  assetName: string
  initialInvestDate: string
  closingUnadjustedQty: number
  closingUnadjustedPrice: number
  closingUnadjustedFV: number
  closingAuditedQty: number
  closingAuditedPrice: number
  closingAuditedFV: number
  fairValueLevel: string
  valuationMethod: string
  methodConsistentWithPrior: string
  valuationSource: string
  inputSourceAndAdjustment: string
  valuationTechnique: string
  unobservableInputDesc: string
  unobservableInputValue: string
  nonLiquidityDiscount: number
  valuationDocIndex: string
}

const ITEM_ID_ROWS = 'G9-fv-test-rows'
const ITEM_ID_CONCLUSION = 'G9-fv-conclusion'

function genId(): string {
  return `g9fv-${Date.now().toString(36)}`
}

function enrichRow(raw: G9FairValueRow): G9FairValueRow & { fairValueDiff: number } {
  return {
    ...raw,
    fairValueDiff: calcFairValueDiff(raw.closingAuditedFV, raw.closingUnadjustedFV),
  }
}

function parseRows(json: string | null | undefined): ReturnType<typeof enrichRow>[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    if (!Array.isArray(arr)) return []
    return arr.map((r: any, i: number) => enrichRow({
      rowId: r.rowId || genId(),
      seq: i + 1,
      assetName: r.assetName ?? '',
      initialInvestDate: r.initialInvestDate ?? '',
      closingUnadjustedQty: parseNum(r.closingUnadjustedQty),
      closingUnadjustedPrice: parseNum(r.closingUnadjustedPrice),
      closingUnadjustedFV: parseNum(r.closingUnadjustedFV),
      closingAuditedQty: parseNum(r.closingAuditedQty),
      closingAuditedPrice: parseNum(r.closingAuditedPrice),
      closingAuditedFV: parseNum(r.closingAuditedFV),
      fairValueLevel: r.fairValueLevel ?? 'Level2',
      valuationMethod: r.valuationMethod ?? '',
      methodConsistentWithPrior: r.methodConsistentWithPrior ?? 'yes',
      valuationSource: r.valuationSource ?? '',
      inputSourceAndAdjustment: r.inputSourceAndAdjustment ?? '',
      valuationTechnique: r.valuationTechnique ?? '',
      unobservableInputDesc: r.unobservableInputDesc ?? '',
      unobservableInputValue: r.unobservableInputValue ?? '',
      nonLiquidityDiscount: parseNum(r.nonLiquidityDiscount),
      valuationDocIndex: r.valuationDocIndex ?? '',
    }))
  } catch {
    return []
  }
}

export function validateG9Level3(row: G9FairValueRow): string[] {
  if (row.fairValueLevel !== 'Level3') return []
  const errs: string[] = []
  if (!row.valuationTechnique?.trim()) errs.push('估值技术')
  if (!row.unobservableInputDesc?.trim()) errs.push('不可观察输入值')
  return errs
}

export function useG9FairValueTest(opts: {
  wpId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const activeTab = ref('basic')
  const activeRowIndex = ref(0)
  const aiLoading = ref(false)
  const conclusion = ref('')

  watch(() => opts.allResponses.value.get(ITEM_ID_CONCLUSION)?.conclusion, (v) => {
    conclusion.value = v ?? ''
  }, { immediate: true })

  const rows = computed(() => parseRows(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark))

  function persist(list: G9FairValueRow[]): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(list) })
  }

  function updateRow(rowId: string, patch: Partial<G9FairValueRow>): void {
    if (opts.isReadonly.value) return
    const list = rows.value.map((r) => {
      if (r.rowId !== rowId) return r
      const merged = { ...r, ...patch }
      const errs = validateG9Level3(merged)
      if (errs.length && merged.fairValueLevel === 'Level3') {
        ElMessage.warning(`Level3 必填：${errs.join('、')}`)
      }
      return merged
    })
    persist(list)
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入资产名称', '新增公允价值测试行')
      const name = (value ?? '').trim()
      if (!name) return
      persist([
        ...rows.value,
        {
          rowId: genId(),
          seq: rows.value.length + 1,
          assetName: name,
          initialInvestDate: '',
          closingUnadjustedQty: 0,
          closingUnadjustedPrice: 0,
          closingUnadjustedFV: 0,
          closingAuditedQty: 0,
          closingAuditedPrice: 0,
          closingAuditedFV: 0,
          fairValueLevel: 'Level2',
          valuationMethod: G9_VALUATION_METHOD_OPTIONS[0],
          methodConsistentWithPrior: 'yes',
          valuationSource: '',
          inputSourceAndAdjustment: '',
          valuationTechnique: '',
          unobservableInputDesc: '',
          unobservableInputValue: '',
          nonLiquidityDiscount: 0,
          valuationDocIndex: '',
        },
      ])
    } catch { /* cancelled */ }
  }

  function updateConclusion(value: string): void {
    if (opts.isReadonly.value) return
    conclusion.value = value
    opts.debouncedSave(ITEM_ID_CONCLUSION, { conclusion: value })
  }

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value || !opts.wpId.value) return
    aiLoading.value = true
    try {
      const { api } = await import('@/services/apiProxy')
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g9/ai/fair-value-conclusion`,
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
    activeRowIndex,
    conclusion,
    aiLoading,
    updateRow,
    addRow,
    updateConclusion,
    generateAiConclusion,
    fvLevelOptions: G9_FV_LEVEL_OPTIONS,
    valuationMethodOptions: G9_VALUATION_METHOD_OPTIONS,
    validateLevel3: validateG9Level3,
  }
}
