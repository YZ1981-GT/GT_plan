/**
 * useG9L3Reconciliation — G9-5 第三层次调节表（10 因子）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { parseNum, calcL3Reconciliation, calcL3Variance, calcSubtotal } from './useG9FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface G9L3Row {
  rowId: string
  seq: number
  assetName: string
  openingFairValue: number
  purchaseAmount: number
  disposalAmount: number
  transferIn: number
  transferOut: number
  fvChangePL: number
  fvChangeOCI: number
  interestIncome: number
  impairmentLoss: number
  otherChanges: number
  reportedClosing: number
  conclusion?: string
}

const ITEM_ID_ROWS = 'G9-l3-rows'
const ITEM_ID_CONCLUSION = 'G9-l3-conclusion'

function genId(): string {
  return `g9l3-${Date.now().toString(36)}`
}

function enrichRow(raw: G9L3Row): G9L3Row & { closingFairValue: number; variance: number; varianceHighlight: boolean } {
  const closingFairValue = calcL3Reconciliation(
    raw.openingFairValue,
    raw.purchaseAmount,
    raw.disposalAmount,
    raw.transferIn,
    raw.transferOut,
    raw.fvChangePL,
    raw.fvChangeOCI,
    raw.interestIncome,
    raw.impairmentLoss,
    raw.otherChanges,
  )
  const variance = calcL3Variance(closingFairValue, raw.reportedClosing)
  return {
    ...raw,
    closingFairValue,
    variance,
    varianceHighlight: Math.abs(variance) > 0.01,
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
      openingFairValue: parseNum(r.openingFairValue),
      purchaseAmount: parseNum(r.purchaseAmount),
      disposalAmount: parseNum(r.disposalAmount),
      transferIn: parseNum(r.transferIn),
      transferOut: parseNum(r.transferOut),
      fvChangePL: parseNum(r.fvChangePL),
      fvChangeOCI: parseNum(r.fvChangeOCI),
      interestIncome: parseNum(r.interestIncome),
      impairmentLoss: parseNum(r.impairmentLoss),
      otherChanges: parseNum(r.otherChanges),
      reportedClosing: parseNum(r.reportedClosing),
    }))
  } catch {
    return []
  }
}

export function useG9L3Reconciliation(opts: {
  wpId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const aiLoading = ref(false)
  const conclusion = ref('')

  watch(() => opts.allResponses.value.get(ITEM_ID_CONCLUSION)?.conclusion, (v) => {
    conclusion.value = v ?? ''
  }, { immediate: true })

  const rows = computed(() => parseRows(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark))

  const totals = computed(() => ({
    openingFairValue: calcSubtotal(rows.value.map((r) => r.openingFairValue)),
    closingFairValue: calcSubtotal(rows.value.map((r) => r.closingFairValue)),
    reportedClosing: calcSubtotal(rows.value.map((r) => r.reportedClosing)),
    variance: calcSubtotal(rows.value.map((r) => r.variance)),
  }))

  function persistRaw(list: G9L3Row[]): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(list) })
  }

  function updateRow(rowId: string, field: keyof G9L3Row, value: unknown): void {
    if (opts.isReadonly.value) return
    const list = rows.value.map((r) => {
      if (r.rowId !== rowId) return r
      const patch: Partial<G9L3Row> = {}
      if (field === 'assetName') patch.assetName = String(value ?? '')
      else patch[field] = parseNum(value) as never
      return { ...r, ...patch }
    })
    persistRaw(list)
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入资产名称', '新增 L3 调节行')
      const name = (value ?? '').trim()
      if (!name) return
      persistRaw([
        ...rows.value,
        {
          rowId: genId(),
          seq: rows.value.length + 1,
          assetName: name,
          openingFairValue: 0,
          purchaseAmount: 0,
          disposalAmount: 0,
          transferIn: 0,
          transferOut: 0,
          fvChangePL: 0,
          fvChangeOCI: 0,
          interestIncome: 0,
          impairmentLoss: 0,
          otherChanges: 0,
          reportedClosing: 0,
        },
      ])
    } catch { /* cancelled */ }
  }

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value) return
    aiLoading.value = true
    try {
      const res = await apiPost(opts.wpId.value, rows.value, totals.value)
      if (res) {
        conclusion.value = res
        opts.debouncedSave(ITEM_ID_CONCLUSION, { conclusion: res })
      }
    } catch { /* optional */ }
    finally { aiLoading.value = false }
  }

  function updateConclusion(v: string): void {
    if (opts.isReadonly.value) return
    conclusion.value = v
    opts.debouncedSave(ITEM_ID_CONCLUSION, { conclusion: v })
  }

  return { rows, totals, conclusion, aiLoading, updateRow, addRow, generateAiConclusion, updateConclusion }
}

async function apiPost(wpId: string, rows: unknown[], totals: unknown): Promise<string> {
  const { api } = await import('@/services/apiProxy')
  const res = await api.post(
    `/api/workpapers/${wpId}/g9/ai/l3-reconciliation-conclusion`,
    { rows, relatedContext: { totals } },
    { _silent: true } as any,
  )
  return res?.data?.data?.content ?? res?.data?.content ?? res?.content ?? ''
}
