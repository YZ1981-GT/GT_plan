/**
 * useI3TargetedCheck — I3-5 商誉针对性检查表
 * 样本选取 + 凭证核对 1~5 + 检查比例（可联动 I3-2 本期发生额）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  type I3TargetedCheckRow,
  type I3TargetedSampleMeta,
  type I3TargetedRiskFocus,
  type I3TargetedSummary,
  emptyI3TargetedRow,
  emptyI3TargetedSampleMeta,
  emptyI3TargetedRiskFocus,
  normalizeI3TargetedRow,
  normalizeI3TargetedSampleMeta,
  normalizeI3TargetedRiskFocus,
  summarizeI3Targeted,
  extractI3PeriodMovement,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  buildI3TargetedConclusionDraft,
  buildI3TargetedAdjDrafts,
  mapSampledToI3TargetedRow,
  isAbnormalFlag,
  hasFailedCheck,
  I3_5_DEFAULT_COVERAGE_THRESHOLD,
} from './i3TargetedCheckModel'

export {
  type I3TargetedCheckRow,
  type I3TargetedSampleMeta,
  type I3TargetedRiskFocus,
  type I3TargetedSummary,
  type I3TargetedAdjDraft,
  emptyI3TargetedRow,
  I3_5_DEFAULT_COVERAGE_THRESHOLD,
  I3_5_TEST_CONTENT,
  I3_5_TEST_REASONS,
  I3_5_SAMPLE_METHODS,
  I3_5_CHECK_OPTIONS,
  I3_5_OBJECTIVES,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  isAbnormalFlag,
  hasFailedCheck,
  buildI3TargetedConclusionDraft,
  buildI3TargetedAdjDrafts,
  mapSampledToI3TargetedRow,
} from './i3TargetedCheckModel'

const STORAGE_ROWS = 'I3-5-rows'
const STORAGE_SAMPLE = 'I3-5-sample-meta'
const STORAGE_RISK = 'I3-5-risk-focus'
const STORAGE_LEGACY = 'I3-5-targeted'
const STORAGE_NOTE = 'I3-5-audit-note'
const STORAGE_CONCLUSION = 'I3-5-audit-conclusion'
const I32_ROWS = 'I3-2-rows'

function _safeParseArray(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string' && raw) {
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch { return [] }
  }
  if (raw && typeof raw === 'object') {
    const obj = raw as any
    const remark = obj.remark ?? obj.conclusion
    if (remark != null) return _safeParseArray(remark)
  }
  return []
}

function _readText(raw: unknown): string {
  if (raw == null) return ''
  if (typeof raw === 'string') return raw
  if (typeof raw === 'object') return String((raw as any).remark ?? (raw as any).conclusion ?? '')
  return ''
}

function _parseObject(raw: unknown): any {
  if (!raw) return null
  if (typeof raw === 'string' && raw) {
    try { return JSON.parse(raw) } catch { return null }
  }
  if (typeof raw === 'object') {
    const remark = (raw as any).remark
    if (typeof remark === 'string' && remark) {
      try { return JSON.parse(remark) } catch { return raw }
    }
    return raw
  }
  return null
}

export function useI3TargetedCheck(
  allResponses: Ref<Map<string, any>> | (() => Map<string, any>),
  options?: {
    /** I3 父组件契约：逐 item_id 持久化 */
    onSave?: (itemId: string, value: any) => void | Promise<void>
    asOfYear?: Ref<number> | (() => number)
  },
) {
  const getMap = typeof allResponses === 'function'
    ? allResponses
    : () => allResponses.value

  const getYear = () => {
    if (!options?.asOfYear) return new Date().getFullYear()
    return typeof options.asOfYear === 'function'
      ? options.asOfYear()
      : options.asOfYear.value
  }

  const rows = ref<I3TargetedCheckRow[]>([])
  const sampleMeta = ref<I3TargetedSampleMeta>(emptyI3TargetedSampleMeta())
  const riskFocus = ref<I3TargetedRiskFocus>(emptyI3TargetedRiskFocus())
  const auditNote = ref('')
  const auditConclusion = ref('')

  function load() {
    const map = getMap()
    rows.value = _safeParseArray(map.get(STORAGE_ROWS)).map(normalizeI3TargetedRow)

    sampleMeta.value = normalizeI3TargetedSampleMeta(_parseObject(map.get(STORAGE_SAMPLE)))

    const riskRaw = _parseObject(map.get(STORAGE_RISK))
      || _parseObject(map.get(STORAGE_LEGACY))
    riskFocus.value = normalizeI3TargetedRiskFocus(riskRaw)

    auditNote.value = _readText(map.get(STORAGE_NOTE))
      || _strFromLegacy(riskRaw, 'auditNote')
    auditConclusion.value = _readText(map.get(STORAGE_CONCLUSION))
      || _strFromLegacy(riskRaw, 'auditConclusion')
      || _strFromLegacy(riskRaw, 'overallConclusion')

    if (!sampleMeta.value.populationManual) {
      const mv = extractI3PeriodMovement(map.get(I32_ROWS), getYear())
      if (mv.debitTotal > 0) sampleMeta.value.populationAmount = mv.debitTotal
      if (mv.creditTotal > 0) sampleMeta.value.populationCreditAmount = mv.creditTotal
    }
  }

  function _strFromLegacy(raw: any, key: string): string {
    if (!raw || typeof raw !== 'object') return ''
    return raw[key] ? String(raw[key]) : ''
  }

  watch(() => {
    const m = getMap()
    return [
      m.get(STORAGE_ROWS),
      m.get(STORAGE_SAMPLE),
      m.get(STORAGE_RISK),
      m.get(STORAGE_LEGACY),
      m.get(STORAGE_NOTE),
      m.get(STORAGE_CONCLUSION),
      m.get(I32_ROWS),
    ]
  }, () => load(), { immediate: true, deep: false })

  const linkedPeriod: ComputedRef<{
    debitTotal: number
    creditTotal: number
    originalTotal: number
    source: string
  }> = computed(() => {
    const mv = extractI3PeriodMovement(getMap().get(I32_ROWS), getYear())
    return mv.debitTotal > 0 || mv.creditTotal > 0 || mv.originalTotal > 0
      ? mv
      : { debitTotal: 0, creditTotal: 0, originalTotal: 0, source: '' }
  })

  const summary: ComputedRef<I3TargetedSummary> = computed(() =>
    summarizeI3Targeted(
      rows.value,
      sampleMeta.value.populationAmount,
      sampleMeta.value.populationCreditAmount,
    ),
  )

  const coverageLow = computed(() =>
    summary.value.coverageRate != null
    && summary.value.coverageRate < sampleMeta.value.coverageThreshold
    && summary.value.periodTotal > 0,
  )

  const coverageLabel = computed(() => formatLayeredCoverageLabel(summary.value))
  const creditCoverageLabel = computed(() => formatCoverageLabel(summary.value.creditCoverageRate))

  const coverageTagType = computed(() => {
    if (summary.value.coverageRate == null) return 'info'
    if (coverageLow.value) return 'danger'
    return 'success'
  })

  const adjDrafts = computed(() => buildI3TargetedAdjDrafts(rows.value))

  function addRow(partial?: Partial<I3TargetedCheckRow>) {
    rows.value.push(emptyI3TargetedRow(partial))
  }

  function removeRow(rowId: string) {
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
  }

  function updateRow(rowId: string, field: keyof I3TargetedCheckRow, value: string | number | boolean) {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    if ((field === 'check1' || field === 'check2' || field === 'check3' || field === 'check4' || field === 'check5')
      && value === '×' && !isAbnormalFlag(row.isAbnormal)) {
      row.isAbnormal = '是'
    }
  }

  function fillFromSampledVouchers(samples: any[]): number {
    if (!Array.isArray(samples) || !samples.length) return 0
    const existing = new Set(
      rows.value.map((r) => `${r.voucherDate}|${r.voucherNo}`).filter((k) => k !== '|'),
    )
    let n = 0
    for (const s of samples) {
      const mapped = mapSampledToI3TargetedRow(s)
      const key = `${mapped.voucherDate}|${mapped.voucherNo}`
      if (key !== '|' && existing.has(key)) continue
      rows.value.push(mapped)
      if (key !== '|') existing.add(key)
      n++
    }
    if (n > 0 && !sampleMeta.value.sampleSize) {
      sampleMeta.value.sampleSize = rows.value.length
    }
    return n
  }

  function setPopulationAmount(amount: number, manual: boolean) {
    sampleMeta.value.populationAmount = amount
    sampleMeta.value.populationManual = manual
  }

  function syncPopulationFromI32(mode: 'period' | 'original' = 'period'): { ok: boolean; message: string } {
    const mv = linkedPeriod.value
    if (mode === 'original') {
      if (!(mv.originalTotal > 0)) return { ok: false, message: 'I3-2 无商誉原值可带入' }
      setPopulationAmount(mv.originalTotal, false)
      sampleMeta.value.populationCreditAmount = mv.creditTotal
      sampleMeta.value.populationDesc = 'I3-2 商誉原值合计（存在性测试总体）'
      return {
        ok: true,
        message: `已带入原值合计 ${mv.originalTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`,
      }
    }
    if (!(mv.debitTotal > 0) && !(mv.creditTotal > 0)) {
      return { ok: false, message: 'I3-2 无本期发生额可带入（可改用「带入原值合计」）' }
    }
    if (mv.debitTotal > 0) setPopulationAmount(mv.debitTotal, false)
    sampleMeta.value.populationCreditAmount = mv.creditTotal
    sampleMeta.value.populationDesc = 'I3-2 本期借方发生额代理（当年新确认商誉原值）'
    const parts = [
      mv.debitTotal > 0 ? `借方 ${mv.debitTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}` : '',
      mv.creditTotal > 0 ? `贷方(减值) ${mv.creditTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}` : '',
    ].filter(Boolean)
    return { ok: true, message: `已带入 ${parts.join(' / ')}` }
  }

  function appendAdjDraftsToNote(): { ok: boolean; message: string; count: number } {
    const drafts = adjDrafts.value
    if (!drafts.length) return { ok: false, count: 0, message: '无核对×可生成调整草稿' }
    const block = drafts.map((d, i) =>
      `${i + 1}. ${d.suggestedNote}\n   ${d.suggestedEntry}`,
    ).join('\n')
    auditNote.value = auditNote.value
      ? `${auditNote.value.trim()}\n\n【I3-5 调整建议草稿】\n${block}`
      : `【I3-5 调整建议草稿】\n${block}`
    return { ok: true, count: drafts.length, message: `已写入 ${drafts.length} 条调整建议到审计说明` }
  }

  function fillConclusionDraft() {
    auditConclusion.value = buildI3TargetedConclusionDraft({
      sampleCount: summary.value.sampleCount,
      coverageLabel: coverageLabel.value,
      creditCoverageLabel: creditCoverageLabel.value,
      anomalyCount: summary.value.anomalyCount,
      failCheckCount: summary.value.failCheckCount,
      testReasons: sampleMeta.value.testReasons,
      riskFocus: riskFocus.value,
    })
  }

  async function persistAll() {
    if (!options?.onSave) return
    if (!sampleMeta.value.sampleSize && rows.value.length) {
      sampleMeta.value.sampleSize = rows.value.length
    }
    await options.onSave(STORAGE_ROWS, JSON.stringify(rows.value))
    await options.onSave(STORAGE_SAMPLE, JSON.stringify(sampleMeta.value))
    await options.onSave(STORAGE_RISK, JSON.stringify(riskFocus.value))
    await options.onSave(STORAGE_NOTE, auditNote.value)
    await options.onSave(STORAGE_CONCLUSION, auditConclusion.value)
  }

  async function saveNote(val: string) {
    auditNote.value = val
    if (options?.onSave) await options.onSave(STORAGE_NOTE, val)
  }

  async function saveConclusion(val: string) {
    auditConclusion.value = val
    if (options?.onSave) await options.onSave(STORAGE_CONCLUSION, val)
  }

  return {
    rows,
    sampleMeta,
    riskFocus,
    auditNote,
    auditConclusion,
    summary,
    coverageLow,
    coverageLabel,
    creditCoverageLabel,
    coverageTagType,
    linkedPeriod,
    adjDrafts,
    addRow,
    removeRow,
    updateRow,
    fillFromSampledVouchers,
    setPopulationAmount,
    syncPopulationFromI32,
    appendAdjDraftsToNote,
    fillConclusionDraft,
    persistAll,
    saveNote,
    saveConclusion,
    load,
  }
}

export default useI3TargetedCheck
