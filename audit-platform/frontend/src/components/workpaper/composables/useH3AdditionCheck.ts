/**
 * useH3AdditionCheck — H3-5 增减检查表 composable
 *
 * 对齐致同模板：双模式（成本/公允）+ 样本选取 + 核对内容五列 + 检查比例
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import { calcSubtotal } from './useH3FormulaEngine'
import {
  type H3AdditionCostRow,
  type H3AdditionFairRow,
  type H3AdditionMode,
  type H3SamplingParams,
  type H3AdditionSummary,
  type H3LinkedMovement,
  type H3TestReason,
  type H3VerificationChecks,
  type H3TraceRow,
  normalizeCostRow,
  normalizeFairRow,
  normalizeTraceRow,
  calcCostNetValue,
  calcCoverageRate,
  calcCostSummary,
  calcFairSummary,
  enrichSummaryWithTrace,
  calcTraceDiff,
  isIncreaseChangeType,
} from './h3AdditionCheckModel'
import {
  matchTraceToTitleRow,
  parseTitleRows,
  type TraceTitleLink,
} from './h3AdditionTitleLink'

export type {
  H3AdditionCostRow,
  H3AdditionFairRow,
  H3AdditionMode,
  H3SamplingParams,
  H3AdditionSummary,
  H3LinkedMovement,
  H3TestReason,
  H3VerificationChecks,
  H3TraceRow,
}
export {
  H3_CHANGE_TYPE_OPTS,
  H3_CATEGORY_OPTS,
  H3_TEST_CONTENT_ITEMS,
  H3_TRACE_SOURCE_OPTS,
  SAMPLING_METHOD_OPTS,
  getEvidenceHint,
} from './h3AdditionCheckModel'

const ITEM_COST = 'H3-5-cost-rows'
const ITEM_FAIR = 'H3-5-fair-rows'
const ITEM_TRACE_COST = 'H3-5-cost-trace-rows'
const ITEM_TRACE_FAIR = 'H3-5-fair-trace-rows'
const PREFIX_COST = 'H3-5-cost'
const PREFIX_FAIR = 'H3-5-fair'

function _prefix(mode: H3AdditionMode): string {
  return mode === 'cost' ? PREFIX_COST : PREFIX_FAIR
}

function _rowsKey(mode: H3AdditionMode): string {
  return mode === 'cost' ? ITEM_COST : ITEM_FAIR
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _traceKey(mode: H3AdditionMode): string {
  return mode === 'cost' ? ITEM_TRACE_COST : ITEM_TRACE_FAIR
}

function _flattenCostRow(row: H3AdditionCostRow): Record<string, unknown> {
  return {
    ...row,
    check1: row.checks.check1,
    check2: row.checks.check2,
    check3: row.checks.check3,
    check4: row.checks.check4,
    check5: row.checks.check5,
  }
}

function _flattenFairRow(row: H3AdditionFairRow): Record<string, unknown> {
  return {
    ...row,
    check1: row.checks.check1,
    check2: row.checks.check2,
    check3: row.checks.check3,
    check4: row.checks.check4,
    check5: row.checks.check5,
  }
}

export function useH3AdditionCheck(params: {
  allResponses: Ref<Map<string, ChecklistItem>> | ComputedRef<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
  measurementModel: Ref<H3AdditionMode | string>
}) {
  const { allResponses, getValue, setValue, saveImmediate, measurementModel } = params

  function _persistCostRows(): void {
    setValue(ITEM_COST, costRows.value.map(_flattenCostRow))
  }

  function _persistFairRows(): void {
    setValue(ITEM_FAIR, fairRows.value.map(_flattenFairRow))
  }

  const costRows = ref<H3AdditionCostRow[]>([])
  const fairRows = ref<H3AdditionFairRow[]>([])
  const traceRowsCost = ref<H3TraceRow[]>([])
  const traceRowsFair = ref<H3TraceRow[]>([])
  const titleRows = ref<import('./h3TitleRowModel').TitleRow[]>([])
  const samplingParamsCost = ref<H3SamplingParams>({ totalPopulation: 0, samplingMethod: '货币单元抽样', sampleSize: 0 })
  const samplingParamsFair = ref<H3SamplingParams>({ totalPopulation: 0, samplingMethod: '货币单元抽样', sampleSize: 0 })
  const populationManualCost = ref(false)
  const populationManualFair = ref(false)
  const testReasonsCost = ref<H3TestReason[]>([])
  const testReasonsFair = ref<H3TestReason[]>([])
  const testReasonOtherCost = ref('')
  const testReasonOtherFair = ref('')
  const auditNoteCost = ref('')
  const auditNoteFair = ref('')
  const auditConclusionCost = ref('')
  const auditConclusionFair = ref('')

  const mode = computed<H3AdditionMode>(() =>
    measurementModel.value === 'fair_value' ? 'fair_value' : 'cost',
  )

  const activeRows = computed(() => (mode.value === 'cost' ? costRows.value : fairRows.value))
  const traceRows = computed(() => (mode.value === 'cost' ? traceRowsCost.value : traceRowsFair.value))
  const samplingParams = computed(() => (mode.value === 'cost' ? samplingParamsCost.value : samplingParamsFair.value))
  const populationManual = computed(() => (mode.value === 'cost' ? populationManualCost.value : populationManualFair.value))
  const testReasons = computed(() => (mode.value === 'cost' ? testReasonsCost.value : testReasonsFair.value))
  const testReasonOther = computed(() => (mode.value === 'cost' ? testReasonOtherCost.value : testReasonOtherFair.value))
  const auditNote = computed(() => (mode.value === 'cost' ? auditNoteCost.value : auditNoteFair.value))
  const auditConclusion = computed(() => (mode.value === 'cost' ? auditConclusionCost.value : auditConclusionFair.value))

  function _loadMeta(prefix: string, target: Ref<H3SamplingParams>, manual: Ref<boolean>, reasons: Ref<H3TestReason[]>, other: Ref<string>, note: Ref<string>, conclusion: Ref<string>): void {
    const sp = getValue(`${prefix}-sampling`)
    if (sp && typeof sp === 'object') {
      target.value = {
        totalPopulation: _num(sp.totalPopulation),
        samplingMethod: String(sp.samplingMethod || '货币单元抽样'),
        sampleSize: _num(sp.sampleSize),
      }
    }
    manual.value = getValue(`${prefix}-population-manual`) === true
    const tr = getValue(`${prefix}-test-reasons`)
    reasons.value = Array.isArray(tr) ? tr : []
    other.value = String(getValue(`${prefix}-test-reason-other`) ?? '')
    note.value = String(getValue(`${prefix}-audit-note`) ?? '')
    conclusion.value = String(getValue(`${prefix}-audit-conclusion`) ?? '')
  }

  function loadRows(): void {
    const rawCost = getValue(ITEM_COST)
    costRows.value = Array.isArray(rawCost) ? rawCost.map((r, i) => normalizeCostRow(r, i)) : []
    const rawFair = getValue(ITEM_FAIR)
    fairRows.value = Array.isArray(rawFair) ? rawFair.map((r, i) => normalizeFairRow(r, i)) : []
    const rawTraceCost = getValue(ITEM_TRACE_COST)
    traceRowsCost.value = Array.isArray(rawTraceCost) ? rawTraceCost.map((r, i) => normalizeTraceRow(r, i)) : []
    const rawTraceFair = getValue(ITEM_TRACE_FAIR)
    traceRowsFair.value = Array.isArray(rawTraceFair) ? rawTraceFair.map((r, i) => normalizeTraceRow(r, i)) : []
    const rawTitle = getValue('H3-12-title-rows')
    titleRows.value = parseTitleRows(rawTitle).map((r: any, i: number) => ({
      ...r,
      rowId: r.rowId ?? `title-${i}`,
    }))
    _loadMeta(PREFIX_COST, samplingParamsCost, populationManualCost, testReasonsCost, testReasonOtherCost, auditNoteCost, auditConclusionCost)
    _loadMeta(PREFIX_FAIR, samplingParamsFair, populationManualFair, testReasonsFair, testReasonOtherFair, auditNoteFair, auditConclusionFair)
  }

  function _persist(prefix: string, id: string, value: any): void {
    setValue(`${prefix}-${id}`, value)
    void saveImmediate(`${prefix}-${id}`, value)
  }

  function _readLinkedMovement(m: H3AdditionMode): H3LinkedMovement {
    const increaseKey = m === 'cost' ? 'H3-1-cost-increase-total' : 'H3-1-fair-increase-total'
    const decreaseKey = m === 'cost' ? 'H3-1-cost-decrease-total' : 'H3-1-fair-decrease-total'
    const h2IncreaseKey = m === 'cost' ? 'H3-2-cost-increase-total' : 'H3-2-fair-increase-total'
    const h2DecreaseKey = m === 'cost' ? 'H3-2-cost-decrease-total' : 'H3-2-fair-decrease-total'

    const h1Inc = _num(getValue(increaseKey))
    const h2Inc = _num(getValue(h2IncreaseKey))
    const h1Dec = _num(getValue(decreaseKey))
    const h2Dec = _num(getValue(h2DecreaseKey))

    if (h2Inc > 0 || h2Dec > 0) {
      return { increaseAmount: h2Inc, decreaseAmount: h2Dec, source: 'H3-2' }
    }
    if (h1Inc > 0 || h1Dec > 0) {
      return { increaseAmount: h1Inc, decreaseAmount: h1Dec, source: 'H3-1' }
    }
    return { increaseAmount: 0, decreaseAmount: 0, source: '' }
  }

  const linkedMovementCost = computed(() => _readLinkedMovement('cost'))
  const linkedMovementFair = computed(() => _readLinkedMovement('fair_value'))
  const linkedMovement = computed(() => (mode.value === 'cost' ? linkedMovementCost.value : linkedMovementFair.value))

  const summaryCost = computed<H3AdditionSummary>(() => {
    const base = calcCostSummary(costRows.value)
    const pop = samplingParamsCost.value.totalPopulation || linkedMovementCost.value.increaseAmount
    return enrichSummaryWithTrace(base, traceRowsCost.value, pop)
  })

  const summaryFair = computed<H3AdditionSummary>(() => {
    const base = calcFairSummary(fairRows.value)
    const pop = samplingParamsFair.value.totalPopulation || linkedMovementFair.value.increaseAmount
    return enrichSummaryWithTrace(base, traceRowsFair.value, pop)
  })

  const summary = computed(() => (mode.value === 'cost' ? summaryCost.value : summaryFair.value))

  const totalOriginalCost = computed(() => calcSubtotal(costRows.value.map((r) => r.originalCost)))
  const totalNetValue = computed(() => calcSubtotal(costRows.value.map((r) => calcCostNetValue(r))))
  const totalImpairment = computed(() => calcSubtotal(costRows.value.map((r) => r.impairment)))
  const totalFairValue = computed(() => calcSubtotal(fairRows.value.map((r) => r.fairValue)))
  const totalFairChange = computed(() => calcSubtotal(fairRows.value.map((r) => r.fairValueChange)))
  const totalEndBalance = computed(() => calcSubtotal(fairRows.value.map((r) => r.endBalance || r.fairValue)))
  const totalPlImpact = computed(() =>
    mode.value === 'cost'
      ? calcSubtotal(costRows.value.map((r) => r.plImpact))
      : calcSubtotal(fairRows.value.map((r) => r.plImpact)),
  )

  function addRow(): void {
    if (mode.value === 'cost') {
      costRows.value.push(normalizeCostRow({ seq: costRows.value.length + 1 }))
      _persistCostRows()
    } else {
      fairRows.value.push(normalizeFairRow({ seq: fairRows.value.length + 1 }))
      _persistFairRows()
    }
  }

  function removeRow(rowId: string): void {
    if (mode.value === 'cost') {
      costRows.value = costRows.value.filter((r) => r.rowId !== rowId)
      costRows.value.forEach((r, i) => { r.seq = i + 1 })
      _persistCostRows()
    } else {
      fairRows.value = fairRows.value.filter((r) => r.rowId !== rowId)
      fairRows.value.forEach((r, i) => { r.seq = i + 1 })
      _persistFairRows()
    }
  }

  function updateCell(index: number, field: string, value: any): void {
    if (mode.value === 'cost') {
      const row = costRows.value[index]
      if (!row) return
      if (field.startsWith('checks.')) {
        const key = field.split('.')[1] as keyof H3VerificationChecks
        row.checks[key] = Boolean(value)
      } else {
        (row as any)[field] = value
      }
      if (field === 'originalCost' || field === 'accDep' || field === 'impairment') {
        row.netValue = calcCostNetValue(row)
      }
      _persistCostRows()
    } else {
      const row = fairRows.value[index]
      if (!row) return
      if (field.startsWith('checks.')) {
        const key = field.split('.')[1] as keyof H3VerificationChecks
        row.checks[key] = Boolean(value)
      } else {
        (row as any)[field] = value
      }
      if (field === 'fairValue') {
        row.endBalance = _num(value)
      }
      _persistFairRows()
    }
  }

  /**
   * 抽凭引擎回填：把 GtVoucherSamplingEngine 的样本映射为当前计量模式的增减检查行。
   * 增加方对资产科目=借方；按凭证号去重追加，返回新增行数。
   */
  function fillFromSampledVouchers(samples: any[]): number {
    if (!Array.isArray(samples) || !samples.length) return 0
    if (mode.value === 'cost') {
      const existing = new Set(costRows.value.map((r) => r.voucherNo).filter(Boolean))
      let added = 0
      for (const s of samples) {
        const vno = String(s.voucherNo ?? '')
        if (vno && existing.has(vno)) continue
        const amt = _num(s.debitAmount) || _num(s.creditAmount)
        const row = normalizeCostRow({
          seq: costRows.value.length + 1,
          assetName: s.counterpartName ?? s.debtorName ?? '',
          date: s.voucherDate ?? '',
          voucherNo: vno,
          creditAccount: s.counterpartAccount ?? '',
          originalCost: amt,
          isAbnormal: s.abnormal ? 'Y' : 'N',
          remark: s.selectionReason ?? '来源:抽凭',
        }, costRows.value.length)
        row.netValue = calcCostNetValue(row)
        costRows.value.push(row)
        if (vno) existing.add(vno)
        added++
      }
      if (added) _persistCostRows()
      return added
    }
    const existing = new Set(fairRows.value.map((r) => r.voucherNo).filter(Boolean))
    let added = 0
    for (const s of samples) {
      const vno = String(s.voucherNo ?? '')
      if (vno && existing.has(vno)) continue
      const amt = _num(s.debitAmount) || _num(s.creditAmount)
      const row = normalizeFairRow({
        seq: fairRows.value.length + 1,
        assetName: s.counterpartName ?? s.debtorName ?? '',
        date: s.voucherDate ?? '',
        voucherNo: vno,
        creditAccount: s.counterpartAccount ?? '',
        fairValue: amt,
        isAbnormal: s.abnormal ? 'Y' : 'N',
        remark: s.selectionReason ?? '来源:抽凭',
      }, fairRows.value.length)
      row.endBalance = amt
      fairRows.value.push(row)
      if (vno) existing.add(vno)
      added++
    }
    if (added) _persistFairRows()
    return added
  }

  function updateSamplingParams(patch: Partial<H3SamplingParams>): void {
    const prefix = _prefix(mode.value)
    const target = mode.value === 'cost' ? samplingParamsCost : samplingParamsFair
    const manual = mode.value === 'cost' ? populationManualCost : populationManualFair
    target.value = { ...target.value, ...patch }
    if (patch.totalPopulation != null) manual.value = true
    _persist(prefix, 'sampling', target.value)
    if (patch.totalPopulation != null) _persist(prefix, 'population-manual', manual.value)
  }

  function syncPopulationFromLinked(): void {
    const linked = linkedMovement.value
    if (linked.increaseAmount <= 0) return
    updateSamplingParams({ totalPopulation: linked.increaseAmount })
    const manual = mode.value === 'cost' ? populationManualCost : populationManualFair
    manual.value = false
    _persist(_prefix(mode.value), 'population-manual', false)
  }

  function updateTestReasons(reasons: H3TestReason[]): void {
    const prefix = _prefix(mode.value)
    if (mode.value === 'cost') testReasonsCost.value = reasons
    else testReasonsFair.value = reasons
    _persist(prefix, 'test-reasons', reasons)
  }

  function updateTestReasonOther(val: string): void {
    const prefix = _prefix(mode.value)
    if (mode.value === 'cost') testReasonOtherCost.value = val
    else testReasonOtherFair.value = val
    _persist(prefix, 'test-reason-other', val)
  }

  function saveAuditNote(val: string): void {
    const prefix = _prefix(mode.value)
    if (mode.value === 'cost') auditNoteCost.value = val
    else auditNoteFair.value = val
    _persist(prefix, 'audit-note', val)
  }

  function saveAuditConclusion(val: string): void {
    const prefix = _prefix(mode.value)
    if (mode.value === 'cost') auditConclusionCost.value = val
    else auditConclusionFair.value = val
    _persist(prefix, 'audit-conclusion', val)
  }

  function _persistTraceRows(): void {
    if (mode.value === 'cost') {
      setValue(ITEM_TRACE_COST, traceRowsCost.value)
    } else {
      setValue(ITEM_TRACE_FAIR, traceRowsFair.value)
    }
  }

  function addTraceRow(sourceRef = ''): void {
    const target = mode.value === 'cost' ? traceRowsCost : traceRowsFair
    target.value.push(normalizeTraceRow({ seq: target.value.length + 1, sourceRef }))
    _persistTraceRows()
  }

  function removeTraceRow(rowId: string): void {
    const target = mode.value === 'cost' ? traceRowsCost : traceRowsFair
    target.value = target.value.filter((r) => r.rowId !== rowId)
    target.value.forEach((r, i) => { r.seq = i + 1 })
    _persistTraceRows()
  }

  function updateTraceCell(rowId: string, field: keyof H3TraceRow, value: any): void {
    const target = mode.value === 'cost' ? traceRowsCost : traceRowsFair
    const row = target.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    if (field === 'recordedInBooks' && value === 'N' && !row.checkResult) row.checkResult = 'ERR'
    if (field === 'recordedInBooks' && value === 'Y' && row.checkResult === 'ERR') row.checkResult = 'OK'
    row.amountDiff = calcTraceDiff(row)
    _persistTraceRows()
  }

  /** 从账→证样本生成证→账追查线索 */
  function seedTraceFromVouchRows(): number {
    let n = 0
    const vouchRows = mode.value === 'cost' ? costRows.value : fairRows.value
    const target = mode.value === 'cost' ? traceRowsCost : traceRowsFair
    for (const r of vouchRows) {
      const docs = String(r.supportingDocs || '').trim()
      const hasSrc = docs || r.voucherNo
      if (!hasSrc) continue
      const sourceRef = docs.split(/[,，;；]/)[0]?.trim() || r.voucherNo
      const already = target.value.some((t) => t.sourceRef === sourceRef && sourceRef)
      if (already) continue
      const bookAmount = mode.value === 'cost'
        ? (r as H3AdditionCostRow).originalCost
        : (r as H3AdditionFairRow).fairValue
      const tr = normalizeTraceRow({
        rowId: `h3tr-${Date.now()}-${Math.random().toString(36).slice(2, 6)}-${n}`,
        seq: target.value.length + 1,
        sourceType: docs.includes('发票') ? '发票' : docs.includes('合同') ? '合同' : docs.includes('验收') ? '验收报告' : '其他',
        sourceRef,
        sourceDate: r.date,
        sourceParty: r.assetName,
        sourceAmount: bookAmount,
        recordedInBooks: (r.voucherNo || bookAmount > 0) ? 'Y' : '',
        bookVoucherNo: r.voucherNo,
        bookAssetName: r.assetName,
        bookAmount,
        remark: `自账→证样本带入(${r.rowId})`,
        indexRef: r.indexRef || '',
      })
      target.value.push(tr)
      n++
    }
    if (n) _persistTraceRows()
    return n
  }

  function traceRowClassName({ row }: { row: H3TraceRow }): string {
    if (row.recordedInBooks === 'N' || row.checkResult === 'ERR') return 'row-anomaly'
    if (Math.abs(row.amountDiff) > 1) return 'row-warn'
    return ''
  }

  function resolveTitleForTrace(traceRowId: string): import('./h3TitleRowModel').TitleRow | undefined {
    const tr = traceRows.value.find((r) => r.rowId === traceRowId)
    if (!tr) return undefined
    return matchTraceToTitleRow(tr, titleRows.value)
  }

  function linkTraceToTitle(traceRowId: string, titleRowId: string): void {
    const target = mode.value === 'cost' ? traceRowsCost : traceRowsFair
    const row = target.value.find((r) => r.rowId === traceRowId)
    if (!row) return
    row.linkedTitleRowId = titleRowId
    _persistTraceRows()
  }

  function traceTitleLinks(): TraceTitleLink[] {
    const links: TraceTitleLink[] = []
    for (const tr of traceRows.value) {
      const title = matchTraceToTitleRow(tr, titleRows.value)
      if (!title) continue
      links.push({
        traceRowId: tr.rowId,
        titleRowId: title.rowId,
        matchScore: tr.linkedTitleRowId === title.rowId ? 1 : 0.8,
        matchReason: tr.linkedTitleRowId ? '已关联' : '自动匹配',
      })
    }
    return links
  }

  function populationDrift(): boolean {
    const linked = linkedMovement.value
    const pop = samplingParams.value.totalPopulation
    return linked.source !== '' && linked.increaseAmount > 0 && Math.abs(pop - linked.increaseAmount) > 1
  }

  function rowClassName({ row }: { row: H3AdditionCostRow | H3AdditionFairRow }): string {
    if (row.isAbnormal === 'Y') return 'row-anomaly'
    return ''
  }

  watch(allResponses, () => loadRows(), { immediate: true })

  return {
    mode,
    costRows,
    fairRows,
    traceRows,
    traceRowsCost,
    traceRowsFair,
    titleRows,
    activeRows,
    samplingParams,
    samplingParamsCost,
    samplingParamsFair,
    populationManual,
    testReasons,
    testReasonOther,
    auditNote,
    auditConclusion,
    linkedMovement,
    linkedMovementCost,
    linkedMovementFair,
    summary,
    summaryCost,
    summaryFair,
    addRow,
    removeRow,
    updateCell,
    fillFromSampledVouchers,
    addTraceRow,
    removeTraceRow,
    updateTraceCell,
    seedTraceFromVouchRows,
    traceRowClassName,
    resolveTitleForTrace,
    linkTraceToTitle,
    traceTitleLinks,
    updateSamplingParams,
    syncPopulationFromLinked,
    updateTestReasons,
    updateTestReasonOther,
    saveAuditNote,
    saveAuditConclusion,
    populationDrift,
    rowClassName,
    loadRows,
    isIncreaseChangeType,
    // 组件 API 别名
    addCostRow: addRow,
    addFairRow: addRow,
    updateCostCell: updateCell,
    updateFairCell: updateCell,
    totalOriginalCost,
    totalNetValue,
    totalImpairment,
    totalFairValue,
    totalFairChange,
    totalEndBalance,
    totalPlImpact,
  }
}

export default useH3AdditionCheck
