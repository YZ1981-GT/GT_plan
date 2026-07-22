import { useWorkpaperAuditYear } from './workpaperAuditYear'
/**
 * useG9Adjudication — G9-1 审定表：分组行 / 试算勾稽 / AJE+RJE 公式
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  G9_ACCOUNT_CODE,
  G9_ADJUDICATION_ITEMS,
  G9_CHANGE_RATE_THRESHOLD,
  G9_GROUP_LABELS,
} from './g9Constants'
import { resolveG9TbRow, g9TbRowBalance, g9TbResolvedCode } from './g9TbResolve'
import type { G9MeasurementCategory } from './g9AdjudicationItems'
import { parseG9AdjStore, patchG9AdjRow, applyG9AdjustmentWriteback, type G9AdjustmentWriteback } from './g9AdjStorage'
import {
  parseNum,
  calcAdjustedAmount,
  calcChangeAmount,
  calcChangeRate,
  isChangeRateExceeding,
  calcSubtotal,
} from './useG9FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'
import { publishGCycleSourceFv, sumFvFromChecklistRemark } from './gCycleSourceFv'

export interface G9AdjudicationRow {
  rowKey: string
  label: string
  category: G9MeasurementCategory
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  openingAdjusted: number
  closingUnadjusted: number
  closingAJE: number
  closingRJE: number
  closingAdjusted: number
  changeAmount: number
  changeRate: number | null
  reasonAnalysis: string
  indexRef: string
  changeRateHighlight: boolean
  reasonRequired: boolean
}

const ITEM_ID_ROWS = 'G9-adj-rows'
const ITEM_ID_TB = 'G9-adj-tb'
const ITEM_ID_NOTE = 'G9-adj-note'
const ITEM_ID_CONCLUSION = 'G9-adj-conclusion'

type RowStore = ReturnType<typeof parseG9AdjStore>

export function useG9Adjudication(opts: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const _auditYearRef = useWorkpaperAuditYear()
  const rowStore = ref<RowStore>(parseG9AdjStore(undefined))
  const trialBalanceAmount = ref(0)
  const tbFetchStatus = ref<'idle' | 'found' | 'missing'>('idle')
  const tbResolvedCode = ref<string | null>(null)
  const auditNote = ref('')
  const auditConclusion = ref('')
  const aiLoading = ref(false)
  const collapsedGroups = ref<Record<string, boolean>>({})

  watch(() => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark, (j) => {
    rowStore.value = parseG9AdjStore(j)
  }, { immediate: true })
  watch(() => opts.allResponses.value.get(ITEM_ID_TB)?.remark, (v) => {
    trialBalanceAmount.value = parseNum(v)
  }, { immediate: true })
  watch(() => opts.allResponses.value.get(ITEM_ID_NOTE)?.conclusion, (v) => {
    auditNote.value = v ?? ''
  }, { immediate: true })
  watch(() => opts.allResponses.value.get(ITEM_ID_CONCLUSION)?.conclusion, (v) => {
    auditConclusion.value = v ?? ''
  }, { immediate: true })

  function buildRow(def: (typeof G9_ADJUDICATION_ITEMS)[number]): G9AdjudicationRow {
    const raw = rowStore.value[def.rowKey] ?? {}
    const openingUnadjusted = parseNum(raw.openingUnadjusted)
    const openingAJE = parseNum(raw.openingAJE)
    const openingRJE = parseNum(raw.openingRJE)
    const openingAdjusted = calcAdjustedAmount(openingUnadjusted, openingAJE, openingRJE)
    const closingUnadjusted = parseNum(raw.closingUnadjusted)
    const closingAJE = parseNum(raw.closingAJE)
    const closingRJE = parseNum(raw.closingRJE)
    const closingAdjusted = calcAdjustedAmount(closingUnadjusted, closingAJE, closingRJE)
    const changeRate = calcChangeRate(openingAdjusted, closingAdjusted)
    return {
      rowKey: def.rowKey,
      label: def.label,
      category: def.category,
      openingUnadjusted,
      openingAJE,
      openingRJE,
      openingAdjusted,
      closingUnadjusted,
      closingAJE,
      closingRJE,
      closingAdjusted,
      changeAmount: calcChangeAmount(closingAdjusted, openingAdjusted),
      changeRate,
      reasonAnalysis: raw.reasonAnalysis ?? '',
      indexRef: raw.indexRef ?? '',
      changeRateHighlight: isChangeRateExceeding(changeRate, G9_CHANGE_RATE_THRESHOLD),
      reasonRequired: isChangeRateExceeding(changeRate, G9_CHANGE_RATE_THRESHOLD),
    }
  }

  const dataRows = computed(() => G9_ADJUDICATION_ITEMS.map(buildRow))

  const missingReasonCount = computed(() =>
    dataRows.value.filter((r) => r.reasonRequired && !r.reasonAnalysis?.trim()).length,
  )
  const hasMissingReasons = computed(() => missingReasonCount.value > 0)

  /**
   * 分组小计：优先取组首行（isGroupTotal，承接 G9-2/G9-3 回写）；
   * 若组首行为空则回退为明细行之和，避免「合计+明细」双计。
   */
  function subtotalForCategory(category: G9MeasurementCategory) {
    const rows = dataRows.value.filter((r) => r.category === category)
    const defs = G9_ADJUDICATION_ITEMS.filter((d) => d.category === category)
    const totalKeys = new Set(defs.filter((d) => d.isGroupTotal).map((d) => d.rowKey))
    const totalRows = rows.filter((r) => totalKeys.has(r.rowKey))
    const detailRows = rows.filter((r) => !totalKeys.has(r.rowKey))
    const totalClosing = calcSubtotal(totalRows.map((r) => r.closingAdjusted))
    const totalOpening = calcSubtotal(totalRows.map((r) => r.openingAdjusted))
    const useDetails = Math.abs(totalClosing) < 0.005 && Math.abs(totalOpening) < 0.005
    const src = useDetails ? detailRows : totalRows
    const openingAdjusted = calcSubtotal(src.map((r) => r.openingAdjusted))
    const closingAdjusted = calcSubtotal(src.map((r) => r.closingAdjusted))
    const changeRate = calcChangeRate(openingAdjusted, closingAdjusted)
    return {
      rowKey: `${category}_subtotal`,
      label: '小计',
      category,
      openingUnadjusted: calcSubtotal(src.map((r) => r.openingUnadjusted)),
      openingAJE: calcSubtotal(src.map((r) => r.openingAJE)),
      openingRJE: calcSubtotal(src.map((r) => r.openingRJE)),
      openingAdjusted,
      closingUnadjusted: calcSubtotal(src.map((r) => r.closingUnadjusted)),
      closingAJE: calcSubtotal(src.map((r) => r.closingAJE)),
      closingRJE: calcSubtotal(src.map((r) => r.closingRJE)),
      closingAdjusted,
      changeAmount: calcChangeAmount(closingAdjusted, openingAdjusted),
      changeRate,
      reasonAnalysis: '',
      indexRef: '',
      changeRateHighlight: isChangeRateExceeding(changeRate, G9_CHANGE_RATE_THRESHOLD),
      reasonRequired: false,
    }
  }

  const groupedRows = computed(() => {
    const categories: G9MeasurementCategory[] = ['FVTPL', 'FVOCI', 'AmortizedCost']
    return categories.map((cat) => ({
      groupKey: cat,
      groupName: G9_GROUP_LABELS[cat],
      collapsed: !!collapsedGroups.value[cat],
      rows: dataRows.value.filter((r) => r.category === cat),
      subtotal: subtotalForCategory(cat),
    }))
  })

  const totalRow = computed(() => {
    const subs = groupedRows.value.map((g) => g.subtotal)
    const openingAdjusted = calcSubtotal(subs.map((r) => r.openingAdjusted))
    const closingAdjusted = calcSubtotal(subs.map((r) => r.closingAdjusted))
    const changeRate = calcChangeRate(openingAdjusted, closingAdjusted)
    return {
      rowKey: 'total',
      label: '合计',
      openingAdjusted,
      closingAdjusted,
      changeAmount: calcChangeAmount(closingAdjusted, openingAdjusted),
      changeRate,
      changeRateHighlight: isChangeRateExceeding(changeRate, G9_CHANGE_RATE_THRESHOLD),
    }
  })

  const groupTotals = computed(() => ({
    fvtpl: groupedRows.value.find((g) => g.groupKey === 'FVTPL')?.subtotal.closingAdjusted ?? 0,
    fvoci: groupedRows.value.find((g) => g.groupKey === 'FVOCI')?.subtotal.closingAdjusted ?? 0,
    amortizedCost: groupedRows.value.find((g) => g.groupKey === 'AmortizedCost')?.subtotal.closingAdjusted ?? 0,
  }))

  const variance = computed(() => totalRow.value.closingAdjusted - trialBalanceAmount.value)
  const hasTbMissing = computed(() => tbFetchStatus.value === 'missing')
  const hasVarianceHighlight = computed(() =>
    tbFetchStatus.value === 'found' && Math.abs(variance.value) > 0.01,
  )

  const detailTotalClosing = computed(() => {
    const json = opts.allResponses.value.get('G9-detail-rows')?.remark
    if (!json) return null
    try {
      const arr = JSON.parse(json)
      if (!Array.isArray(arr)) return null
      return calcSubtotal(arr.map((r: any) => parseNum(r.closingAdjusted ?? r.closingBalance)))
    } catch {
      return null
    }
  })

  const detailCrossVariance = computed(() => {
    if (detailTotalClosing.value == null) return null
    return totalRow.value.closingAdjusted - detailTotalClosing.value
  })

  const hasDetailCrossMismatch = computed(() =>
    detailCrossVariance.value != null && Math.abs(detailCrossVariance.value) > 0.01,
  )

  /** 组内：组首行合计 vs 明细分项合计（填了分项时校验） */
  const groupBreakdownMismatches = computed(() => {
    const out: Array<{ category: G9MeasurementCategory; groupTotal: number; detailSum: number; diff: number }> = []
    for (const cat of ['FVTPL', 'FVOCI', 'AmortizedCost'] as G9MeasurementCategory[]) {
      const defs = G9_ADJUDICATION_ITEMS.filter((d) => d.category === cat)
      const totalKeys = new Set(defs.filter((d) => d.isGroupTotal).map((d) => d.rowKey))
      const rows = dataRows.value.filter((r) => r.category === cat)
      const groupTotal = calcSubtotal(rows.filter((r) => totalKeys.has(r.rowKey)).map((r) => r.closingAdjusted))
      const detailSum = calcSubtotal(rows.filter((r) => !totalKeys.has(r.rowKey)).map((r) => r.closingAdjusted))
      if (Math.abs(detailSum) < 0.01) continue
      const diff = groupTotal - detailSum
      if (Math.abs(diff) > 0.01) out.push({ category: cat, groupTotal, detailSum, diff })
    }
    return out
  })
  const hasGroupBreakdownMismatch = computed(() => groupBreakdownMismatches.value.length > 0)

  function persistRows(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rowStore.value) })
  }

  function updateField(
    rowKey: string,
    field: keyof RowStore[string],
    value: unknown,
  ): void {
    if (opts.isReadonly.value) return
    const patch: Partial<RowStore[string]> = {}
    if (field === 'reasonAnalysis' || field === 'indexRef') {
      patch[field] = String(value ?? '')
    } else {
      patch[field] = parseNum(value) as never
    }
    rowStore.value = patchG9AdjRow(rowStore.value, rowKey, patch)
    persistRows()
    publishAdjudicatedDebounced()
  }

  function updateTrialBalance(v: number): void {
    if (opts.isReadonly.value) return
    trialBalanceAmount.value = v
    if (tbFetchStatus.value === 'idle') tbFetchStatus.value = 'found'
    opts.debouncedSave(ITEM_ID_TB, { remark: String(v) })
  }

  function updateAuditNote(value: string): void {
    if (opts.isReadonly.value) return
    auditNote.value = value
    opts.debouncedSave(ITEM_ID_NOTE, { conclusion: value })
  }

  function toggleGroup(key: string): void {
    collapsedGroups.value = { ...collapsedGroups.value, [key]: !collapsedGroups.value[key] }
  }

  let _pubTimer: ReturnType<typeof setTimeout> | null = null
  /** 防抖：仅同步附注/落盘审定数，不回写试算表（避免编辑过程反复 404） */
  function publishAdjudicatedDebounced(): void {
    if (_pubTimer) clearTimeout(_pubTimer)
    _pubTimer = setTimeout(() => {
      _pubTimer = null
      notifyAdjudicated()
    }, 1500)
  }

  /** 同步审定数到 checklist + EventBus（附注联动），不回写 TB */
  function notifyAdjudicated(): void {
    const amount = totalRow.value.closingAdjusted
    const groups = groupTotals.value
    opts.debouncedSave('G9-1-adjudicated-amount', { conclusion: String(amount) })
    try {
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
        detail: { accountCode: G9_ACCOUNT_CODE, adjudicatedAmount: amount, groups },
      }))
    } catch { /* silent */ }
    publishFvChangeForCross()
  }

  /** 发布 G9 明细 FV 变动合计，供 G13 跨底稿勾稽 */
  function publishFvChangeForCross(): void {
    const fv = sumFvFromChecklistRemark(
      opts.allResponses.value.get('G9-detail-rows')?.remark,
      'G9',
    )
    publishGCycleSourceFv('G9', fv)
  }

  watch(
    () => opts.allResponses.value.get('G9-detail-rows')?.remark,
    () => { publishFvChangeForCross() },
  )

  /** 显式发布：附注联动 + 回写试算表 */
  function publishAdjudicated(): void {
    notifyAdjudicated()
    const amount = totalRow.value.closingAdjusted
    try {
      window.dispatchEvent(new CustomEvent('g9:writeback-trial-balance', {
        detail: { accountCode: G9_ACCOUNT_CODE, auditedAmount: amount, forceToast: true },
      }))
    } catch { /* silent */ }
  }

  async function loadTrialBalanceFromApi(): Promise<boolean> {
    const _year = _auditYearRef.value
    if (_year == null) return false
    if (!opts.projectId.value) return false
    try {
      const res = await api.get(`/api/projects/${opts.projectId.value}/trial-balance`, {
        params: { year: _year },
        _silent: true,
      } as any)
      const list = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])
      const hit = resolveG9TbRow(list)
      if (hit) {
        tbFetchStatus.value = 'found'
        tbResolvedCode.value = g9TbResolvedCode(hit)
        updateTrialBalance(g9TbRowBalance(hit))
        return true
      }
      tbFetchStatus.value = 'missing'
      tbResolvedCode.value = null
      return false
    } catch {
      return false
    }
  }

  async function generateAiAnalysis(): Promise<void> {
    if (opts.isReadonly.value) return
    aiLoading.value = true
    try {
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g9/ai/adjudication-analysis`,
        { rows: dataRows.value.slice(0, 20), relatedContext: { total: totalRow.value } },
        { _silent: true } as any,
      )
      const content = res?.data?.data?.content ?? res?.data?.content ?? res?.content ?? ''
      if (content) {
        auditConclusion.value = content
        opts.debouncedSave(ITEM_ID_CONCLUSION, { conclusion: content })
      }
    } catch { /* optional */ }
    finally { aiLoading.value = false }
  }

  async function validateFormulasRemote(): Promise<{ ok: boolean; errors: { field: string; message: string }[] }> {
    try {
      const adjJson = opts.allResponses.value.get('G9-adjustment-rows')?.remark
      let debits: number[] = []
      let credits: number[] = []
      if (adjJson) {
        try {
          const arr = JSON.parse(adjJson)
          if (Array.isArray(arr)) {
            debits = arr.map((r: any) => parseNum(r.debitAmount))
            credits = arr.map((r: any) => parseNum(r.creditAmount))
          }
        } catch { /* ignore */ }
      }
      const l3Json = opts.allResponses.value.get('G9-l3-rows')?.remark
      let l3Rows: unknown[] = []
      if (l3Json) {
        try {
          const arr = JSON.parse(l3Json)
          if (Array.isArray(arr)) l3Rows = arr
        } catch { /* ignore */ }
      }
      const res = await api.post(`/api/workpapers/${opts.wpId.value}/g9/validate-formulas`, {
        adjudication_rows: dataRows.value.map((r) => ({
          rowKey: r.rowKey,
          openingUnadjusted: r.openingUnadjusted,
          openingAJE: r.openingAJE,
          openingRJE: r.openingRJE,
          openingAdjusted: r.openingAdjusted,
          closingUnadjusted: r.closingUnadjusted,
          closingAJE: r.closingAJE,
          closingRJE: r.closingRJE,
          closingAdjusted: r.closingAdjusted,
        })),
        l3_rows: l3Rows,
        adjustment_debits: debits,
        adjustment_credits: credits,
      }, { _silent: true } as any)
      const data = res?.data ?? res
      return { ok: !!data.ok, errors: data.errors ?? [] }
    } catch {
      return { ok: true, errors: [] }
    }
  }

  function applyAdjustmentWriteback(aje: number, rje: number, rowKey = 'fvtpl_1'): void {
    if (opts.isReadonly.value) return
    rowStore.value = applyG9AdjustmentWriteback(rowStore.value, { rowKey, closingAje: aje, closingRje: rje })
    persistRows()
    publishAdjudicatedDebounced()
  }

  function onAdjustmentWriteback(ev: Event): void {
    const detail = (ev as CustomEvent<G9AdjustmentWriteback>).detail
    if (!detail) return
    applyAdjustmentWriteback(detail.closingAje, detail.closingRje, detail.rowKey)
  }

  function syncWritebackFromOverlay(): void {
    const json = opts.allResponses.value.get('G9-aje-adj-overlay')?.remark
    if (!json) return
    try {
      const wb = JSON.parse(json) as G9AdjustmentWriteback
      if (wb && typeof wb.closingAje === 'number') {
        rowStore.value = applyG9AdjustmentWriteback(rowStore.value, wb)
      }
    } catch { /* ignore */ }
  }

  onMounted(() => {
    if (!trialBalanceAmount.value) void loadTrialBalanceFromApi()
    syncWritebackFromOverlay()
    // 不在 mount 时 publish/writebackTB（对齐 G7）：避免打开页面就改写试算表并弹出「未找到科目」
    publishFvChangeForCross()
    window.addEventListener('g9:adjustment-writeback', onAdjustmentWriteback)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('g9:adjustment-writeback', onAdjustmentWriteback)
  })

  return {
    groupedRows,
    totalRow,
    variance,
    hasVarianceHighlight,
    hasDetailCrossMismatch,
    detailTotalClosing,
    detailCrossVariance,
    groupBreakdownMismatches,
    hasGroupBreakdownMismatch,
    tbFetchStatus,
    tbResolvedCode,
    hasTbMissing,
    trialBalanceAmount,
    auditNote,
    auditConclusion,
    aiLoading,
    updateField,
    updateTrialBalance,
    updateAuditNote,
    toggleGroup,
    loadTrialBalanceFromApi,
    generateAiAnalysis,
    publishAdjudicated,
    validateFormulasRemote,
    applyAdjustmentWriteback,
    dataRows,
    missingReasonCount,
    hasMissingReasons,
    accountCode: G9_ACCOUNT_CODE,
  }
}
