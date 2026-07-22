import { useWorkpaperAuditYear } from './workpaperAuditYear'
/**
 * useG10Adjudication — G10-1 审定表（对齐 Excel：三部分结构 + 期初/期末未审·调整·审定）
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  G10_ACCOUNT_CODE,
  G10_ADJUDICATION_ITEMS,
  G10_CHANGE_RATE_THRESHOLD,
  G10_GROUP_LABELS,
  G10_GROUP_SUBTOTAL_LABELS,
  G10_LIABILITY_LINE_SUFFIXES,
} from './g10Constants'
import { parseG10AdjStore, applyG10AdjustmentWritebacks, type G10AdjustmentWritebackMap } from './g10AdjStorage'
import {
  parseNum,
  calcCreditBalance,
  calcAdjustedAmount,
  calcChangeAmount,
  calcChangeRate,
  isChangeRateExceeding,
  calcSubtotal,
  calcBookFromParts,
} from './useG10FormulaEngine'
import { resolveG10TbRow, g10TbRowBalance, g10TbResolvedCode } from './g10TbResolve'
import {
  buildG10AdjudicationProcedureSummary,
  G10A_ADJUDICATION_MARK_KEY,
  G10A_ADJUDICATION_PROGRAM_NOS,
  markG10AProcedureSteps,
} from './g10FvCrossHelpers'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'
import { publishGCycleSourceFv, sumFvFromChecklistRemark } from './gCycleSourceFv'

export interface G10AdjudicationRow {
  rowKey: string
  label: string
  group?: string
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

const ITEM_ID_ROWS = 'G10-adj-rows'
const ITEM_ID_TB = 'G10-adj-tb'
const ITEM_ID_NOTE = 'G10-adj-note'
const ITEM_ID_CONCLUSION = 'G10-adj-conclusion'

type RowStore = ReturnType<typeof parseG10AdjStore>

function resolveClosingUnadjusted(
  raw: RowStore[string],
  openingAdjusted: number,
): number {
  const direct = parseNum(raw?.closingUnadjusted)
  if (Math.abs(direct) >= 0.005) return direct
  const credit = parseNum(raw?.periodCredit)
  const debit = parseNum(raw?.periodDebit)
  if (Math.abs(credit) >= 0.005 || Math.abs(debit) >= 0.005) {
    return calcCreditBalance(openingAdjusted, credit, debit)
  }
  return direct
}

export function useG10Adjudication(opts: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const _auditYearRef = useWorkpaperAuditYear()
  const rowStore = ref<RowStore>(parseG10AdjStore(undefined))
  const trialBalanceAmount = ref(0)
  const tbFetchStatus = ref<'idle' | 'found' | 'missing'>('idle')
  const tbResolvedCode = ref<string | null>(null)
  const auditNote = ref('')
  const auditConclusion = ref('')
  const aiLoading = ref(false)
  const collapsedGroups = ref<Record<string, boolean>>({})
  const procedureMarking = ref(false)

  watch(() => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark, (j) => {
    rowStore.value = parseG10AdjStore(j)
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

  function buildRow(def: (typeof G10_ADJUDICATION_ITEMS)[number]): G10AdjudicationRow {
    const raw = rowStore.value[def.rowKey] ?? {}
    const openingUnadjusted = parseNum(raw.openingUnadjusted)
    const openingAJE = parseNum(raw.openingAJE)
    const openingRJE = parseNum(raw.openingRJE)
    const openingAdjusted = calcAdjustedAmount(openingUnadjusted, openingAJE, openingRJE)
    const closingUnadjusted = resolveClosingUnadjusted(raw, openingAdjusted)
    const closingAJE = parseNum(raw.closingAJE)
    const closingRJE = parseNum(raw.closingRJE)
    const closingAdjusted = calcAdjustedAmount(closingUnadjusted, closingAJE, closingRJE)
    const changeRate = calcChangeRate(openingAdjusted, closingAdjusted)
    const reasonRequired = isChangeRateExceeding(changeRate, G10_CHANGE_RATE_THRESHOLD)
    return {
      rowKey: def.rowKey,
      label: def.label,
      group: def.group,
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
      changeRateHighlight: reasonRequired,
      reasonRequired,
    }
  }

  const dataRows = computed(() => G10_ADJUDICATION_ITEMS.map(buildRow))

  const missingReasonCount = computed(() =>
    dataRows.value.filter((r) => r.reasonRequired && !r.reasonAnalysis?.trim()).length,
  )
  const hasMissingReasons = computed(() => missingReasonCount.value > 0)

  function subtotalForGroup(group: string) {
    const rows = dataRows.value.filter((r) => r.group === group)
    const openingAdjusted = calcSubtotal(rows.map((r) => r.openingAdjusted))
    const closingAdjusted = calcSubtotal(rows.map((r) => r.closingAdjusted))
    const changeRate = calcChangeRate(openingAdjusted, closingAdjusted)
    return {
      rowKey: `${group}_subtotal`,
      label: G10_GROUP_SUBTOTAL_LABELS[group] ?? '小计',
      group,
      openingUnadjusted: calcSubtotal(rows.map((r) => r.openingUnadjusted)),
      openingAJE: calcSubtotal(rows.map((r) => r.openingAJE)),
      openingRJE: calcSubtotal(rows.map((r) => r.openingRJE)),
      openingAdjusted,
      closingUnadjusted: calcSubtotal(rows.map((r) => r.closingUnadjusted)),
      closingAJE: calcSubtotal(rows.map((r) => r.closingAJE)),
      closingRJE: calcSubtotal(rows.map((r) => r.closingRJE)),
      closingAdjusted,
      changeAmount: calcChangeAmount(closingAdjusted, openingAdjusted),
      changeRate,
      reasonAnalysis: '',
      indexRef: '',
      changeRateHighlight: isChangeRateExceeding(changeRate, G10_CHANGE_RATE_THRESHOLD),
      reasonRequired: false,
    }
  }

  const groupedRows = computed(() => {
    const order = ['initial', 'fv_accum', 'book_fv'] as const
    return order.map((groupKey) => ({
      groupKey,
      groupName: G10_GROUP_LABELS[groupKey] ?? groupKey,
      collapsed: collapsedGroups.value[groupKey] ?? false,
      rows: dataRows.value.filter((r) => r.group === groupKey),
      subtotal: subtotalForGroup(groupKey),
    }))
  })

  /** 试算表勾稽与发布审定数均以 (三)账面余额合计为准 */
  const totalRow = computed(() => {
    const book = groupedRows.value.find((g) => g.groupKey === 'book_fv')?.subtotal
    const openingAdjusted = book?.openingAdjusted ?? 0
    const closingAdjusted = book?.closingAdjusted ?? 0
    const changeRate = calcChangeRate(openingAdjusted, closingAdjusted)
    return {
      rowKey: 'total',
      label: G10_GROUP_SUBTOTAL_LABELS.book_fv,
      openingAdjusted,
      closingAdjusted,
      changeAmount: calcChangeAmount(closingAdjusted, openingAdjusted),
      changeRate,
      changeRateHighlight: isChangeRateExceeding(changeRate, G10_CHANGE_RATE_THRESHOLD),
    }
  })

  const variance = computed(() => totalRow.value.closingAdjusted - trialBalanceAmount.value)
  const hasTbMissing = computed(() => tbFetchStatus.value === 'missing')
  const hasVarianceHighlight = computed(() =>
    tbFetchStatus.value === 'found' && Math.abs(variance.value) > 0.01,
  )

  const detailTotalClosing = computed(() => {
    const json = opts.allResponses.value.get('G10-detail-rows')?.remark
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

  const procedureMarked = computed(() =>
    !!opts.allResponses.value.get(G10A_ADJUDICATION_MARK_KEY)?.remark
    || opts.allResponses.value.get(G10A_ADJUDICATION_MARK_KEY)?.conclusion === 'completed',
  )

  const hasAdjudicationData = computed(() =>
    Math.abs(totalRow.value.closingAdjusted) > 0.005
    || dataRows.value.some((r) => r.group === 'book_fv' && (
      Math.abs(r.closingAdjusted) > 0.005 || Math.abs(r.openingAdjusted) > 0.005
    )),
  )

  /** (三) = (一) + (二) 按分项勾稽（有填数时校验） */
  const threePartMismatches = computed(() => {
    const byKey = new Map(dataRows.value.map((r) => [r.rowKey, r]))
    const out: Array<{ suffix: string; field: 'openingAdjusted' | 'closingAdjusted'; expected: number; actual: number; diff: number }> = []
    for (const suffix of G10_LIABILITY_LINE_SUFFIXES) {
      const init = byKey.get(`init_${suffix}`)
      const fv = byKey.get(`fv_${suffix}`)
      const book = byKey.get(`book_${suffix}`)
      if (!init || !fv || !book) continue
      for (const field of ['openingAdjusted', 'closingAdjusted'] as const) {
        const initVal = init[field]
        const fvVal = fv[field]
        const bookVal = book[field]
        if (Math.abs(initVal) < 0.01 && Math.abs(fvVal) < 0.01 && Math.abs(bookVal) < 0.01) continue
        const expected = calcBookFromParts(initVal, fvVal)
        const diff = expected - bookVal
        if (Math.abs(diff) > 0.01) {
          out.push({ suffix, field, expected, actual: bookVal, diff })
        }
      }
    }
    return out
  })
  const hasThreePartMismatch = computed(() => threePartMismatches.value.length > 0)

  function persistRows(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rowStore.value) })
  }

  type EditableField =
    | 'openingUnadjusted' | 'openingAJE' | 'openingRJE'
    | 'closingUnadjusted' | 'closingAJE' | 'closingRJE'
    | 'reasonAnalysis' | 'indexRef'

  function updateField(rowKey: string, field: EditableField, value: unknown): void {
    if (opts.isReadonly.value || rowKey.endsWith('_subtotal') || rowKey === 'total') return
    const entry = { ...(rowStore.value[rowKey] ?? {}) }
    if (field === 'reasonAnalysis' || field === 'indexRef') entry[field] = String(value ?? '')
    else entry[field] = parseNum(value)
    rowStore.value = { ...rowStore.value, [rowKey]: entry }
    persistRows()
    publishAdjudicatedDebounced()
  }

  function toggleGroup(groupKey: string): void {
    collapsedGroups.value = {
      ...collapsedGroups.value,
      [groupKey]: !collapsedGroups.value[groupKey],
    }
  }

  function updateTrialBalance(value: number): void {
    if (opts.isReadonly.value) return
    trialBalanceAmount.value = value
    opts.debouncedSave(ITEM_ID_TB, { remark: String(value) })
  }

  function updateAuditNote(value: string): void {
    if (opts.isReadonly.value) return
    auditNote.value = value
    opts.debouncedSave(ITEM_ID_NOTE, { conclusion: value })
  }

  function updateAuditConclusion(value: string): void {
    if (opts.isReadonly.value) return
    auditConclusion.value = value
    opts.debouncedSave(ITEM_ID_CONCLUSION, { conclusion: value })
  }

  let publishTimer: ReturnType<typeof setTimeout> | null = null
  function publishAdjudicatedDebounced(): void {
    if (publishTimer) clearTimeout(publishTimer)
    publishTimer = setTimeout(() => {
      publishTimer = null
      notifyAdjudicated()
    }, 1500)
  }

  function applyAdjustmentWritebacks(writeback: G10AdjustmentWritebackMap): void {
    if (opts.isReadonly.value) return
    rowStore.value = applyG10AdjustmentWritebacks(rowStore.value, writeback)
    persistRows()
    publishAdjudicatedDebounced()
  }

  function onAdjustmentWriteback(ev: Event): void {
    const detail = (ev as CustomEvent<G10AdjustmentWritebackMap>).detail
    if (!detail?.byRow) return
    applyAdjustmentWritebacks(detail)
  }

  function syncWritebackFromOverlay(): void {
    const json = opts.allResponses.value.get('G10-adj-writeback')?.remark
    if (!json) return
    try {
      const wb = JSON.parse(json) as G10AdjustmentWritebackMap
      if (wb?.byRow) rowStore.value = applyG10AdjustmentWritebacks(rowStore.value, wb)
    } catch { /* ignore */ }
  }

  function onDetailToAdjudication(): void {
    rowStore.value = parseG10AdjStore(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark)
    publishAdjudicatedDebounced()
  }

  function publishAdjudicated(): void {
    notifyAdjudicated()
    const amount = totalRow.value.closingAdjusted
    try {
      window.dispatchEvent(new CustomEvent('g10:writeback-trial-balance', {
        detail: { accountCode: G10_ACCOUNT_CODE, auditedAmount: amount, forceToast: true },
      }))
    } catch { /* silent */ }
  }

  function notifyAdjudicated(): void {
    const amount = totalRow.value.closingAdjusted
    opts.debouncedSave('G10-1-adjudicated-amount', { conclusion: String(amount) })
    try {
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
        detail: { accountCode: G10_ACCOUNT_CODE, adjudicatedAmount: amount },
      }))
    } catch { /* silent */ }
    publishFvChangeForCross()
  }

  /** 发布 G10 明细 FV 变动合计，供 G13 跨底稿勾稽 */
  function publishFvChangeForCross(): void {
    const fv = sumFvFromChecklistRemark(
      opts.allResponses.value.get('G10-detail-rows')?.remark,
      'G10',
    )
    publishGCycleSourceFv('G10', fv)
  }

  watch(
    () => opts.allResponses.value.get('G10-detail-rows')?.remark,
    () => { publishFvChangeForCross() },
  )

  async function loadTrialBalanceFromApi(): Promise<boolean> {
    const _year = _auditYearRef.value
    if (_year == null || !opts.projectId.value) {
      tbFetchStatus.value = 'idle'
      return false
    }
    try {
      const res = await api.get(`/api/projects/${opts.projectId.value}/trial-balance`, {
        params: { year: _year, account_prefix: G10_ACCOUNT_CODE },
        _silent: true,
      } as any)
      const list = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])
      const hit = resolveG10TbRow(list)
      if (hit) {
        tbResolvedCode.value = g10TbResolvedCode(hit)
        updateTrialBalance(g10TbRowBalance(hit))
        tbFetchStatus.value = 'found'
        return true
      }
      tbFetchStatus.value = 'missing'
      return false
    } catch {
      tbFetchStatus.value = 'idle'
      return false
    }
  }

  async function validateFormulasRemote(): Promise<{ ok: boolean; errors: { field: string; message: string }[] }> {
    try {
      const res = await api.post(`/api/workpapers/${opts.wpId.value}/g10/validate-formulas`, {
        adjudication_rows: dataRows.value.map((r) => ({
          rowKey: r.rowKey,
          openingUnadjusted: r.openingUnadjusted,
          openingAdjustment: r.openingAJE,
          openingRJE: r.openingRJE,
          openingAdjusted: r.openingAdjusted,
          closingUnadjusted: r.closingUnadjusted,
          closingAdjustment: r.closingAJE,
          closingRJE: r.closingRJE,
          closingAdjusted: r.closingAdjusted,
        })),
        three_part_rows: G10_LIABILITY_LINE_SUFFIXES.flatMap((suffix) => {
          const init = dataRows.value.find((r) => r.rowKey === `init_${suffix}`)
          const fv = dataRows.value.find((r) => r.rowKey === `fv_${suffix}`)
          const book = dataRows.value.find((r) => r.rowKey === `book_${suffix}`)
          return [{
            suffix,
            initOpening: init?.openingAdjusted ?? 0,
            fvOpening: fv?.openingAdjusted ?? 0,
            bookOpening: book?.openingAdjusted ?? 0,
            initClosing: init?.closingAdjusted ?? 0,
            fvClosing: fv?.closingAdjusted ?? 0,
            bookClosing: book?.closingAdjusted ?? 0,
          }]
        }),
        l3_rows: [],
        adjustment_debits: [],
        adjustment_credits: [],
      }, { _silent: true } as any)
      const data = res?.data ?? res
      return { ok: !!data.ok, errors: data.errors ?? [] }
    } catch {
      return { ok: true, errors: [] }
    }
  }

  async function generateAiAnalysis(): Promise<void> {
    if (opts.isReadonly.value) return
    aiLoading.value = true
    try {
      const res = await api.post(`/api/workpapers/${opts.wpId.value}/g10/ai/adjudication-analysis`, {
        rows: dataRows.value
          .filter((r) => r.group === 'book_fv')
          .map((r) => ({
            label: r.label,
            openingAdjusted: r.openingAdjusted,
            closingAdjusted: r.closingAdjusted,
            changeRate: r.changeRate,
          })),
      }, { _silent: true } as any)
      const text = res?.data?.content ?? res?.content ?? ''
      if (text) updateAuditNote(text)
    } catch { /* AI optional */ }
    finally { aiLoading.value = false }
  }

  async function markProcedureComplete(): Promise<number> {
    if (opts.isReadonly.value) return -1
    if (!opts.projectId.value) {
      ElMessage.warning('缺少项目 ID，无法回填 G10A')
      return -1
    }
    if (!hasAdjudicationData.value) {
      ElMessage.warning('请先编制 G10-1 审定表')
      return -1
    }

    const warnings: string[] = []
    if (hasVarianceHighlight.value) warnings.push('试算表差异超阈值')
    if (hasDetailCrossMismatch.value) warnings.push('与 G10-2 明细勾稽不一致')
    if (hasThreePartMismatch.value) warnings.push('(一)(二)(三)分解不一致')
    if (hasMissingReasons.value) warnings.push(`${missingReasonCount.value} 行缺原因分析`)

    if (warnings.length) {
      try {
        await ElMessageBox.confirm(
          `${warnings.join('；')}。是否仍标记 G10A 审定/分析程序为已完成？`,
          '回填 G10A',
          { type: 'warning', confirmButtonText: '仍标记完成', cancelButtonText: '取消' },
        )
      } catch {
        return -1
      }
    }

    procedureMarking.value = true
    try {
      const summary = buildG10AdjudicationProcedureSummary({
        closingAdjustedTotal: totalRow.value.closingAdjusted,
        tbVariance: tbFetchStatus.value === 'found' ? variance.value : null,
        detailVariance: detailCrossVariance.value,
        threePartMismatches: threePartMismatches.value.length,
        missingReasons: missingReasonCount.value,
      })
      const n = await markG10AProcedureSteps({
        projectId: opts.projectId.value,
        programNos: [...G10A_ADJUDICATION_PROGRAM_NOS],
        status: 'completed',
        linkedWorkpapers: 'G10-1/G10-2',
        executionSummary: summary,
      })
      opts.debouncedSave(G10A_ADJUDICATION_MARK_KEY, {
        conclusion: 'completed',
        remark: JSON.stringify({
          at: new Date().toISOString(),
          summary,
          programNos: [...G10A_ADJUDICATION_PROGRAM_NOS],
        }),
      })
      ElMessage.success(
        n > 0
          ? `已回填 G10A 程序步骤 ${[...G10A_ADJUDICATION_PROGRAM_NOS].join('/')}（审定/分析）为已完成`
          : '已记录完成标记（程序表字段写入可能需刷新 G10A 查看）',
      )
      return Math.max(n, 1)
    } finally {
      procedureMarking.value = false
    }
  }

  onMounted(() => {
    syncWritebackFromOverlay()
    void loadTrialBalanceFromApi()
    publishFvChangeForCross()
    window.addEventListener('g10:adjustment-writeback', onAdjustmentWriteback)
    window.addEventListener('g10:detail-to-adjudication', onDetailToAdjudication)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('g10:adjustment-writeback', onAdjustmentWriteback)
    window.removeEventListener('g10:detail-to-adjudication', onDetailToAdjudication)
    if (publishTimer) clearTimeout(publishTimer)
  })

  return {
    dataRows,
    totalRow,
    groupedRows,
    trialBalanceAmount,
    tbFetchStatus,
    tbResolvedCode,
    variance,
    hasTbMissing,
    hasVarianceHighlight,
    hasMissingReasons,
    missingReasonCount,
    hasThreePartMismatch,
    threePartMismatches,
    detailTotalClosing,
    detailCrossVariance,
    hasDetailCrossMismatch,
    procedureMarking,
    procedureMarked,
    hasAdjudicationData,
    auditNote,
    auditConclusion,
    aiLoading,
    updateField,
    updateTrialBalance,
    updateAuditNote,
    updateAuditConclusion,
    toggleGroup,
    publishAdjudicated,
    applyAdjustmentWritebacks,
    generateAiAnalysis,
    validateFormulasRemote,
    loadTrialBalanceFromApi,
    markProcedureComplete,
  }
}
