/**
 * useI2TargetedCheck — I2-12 开（研）发支出针对性检查表
 * 样本选取 + 凭证核对 1~5 + 检查比例（可联动 I2-2 本期资本化增加）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  type I2TargetedCheckRow,
  type I2TargetedSampleMeta,
  type I2TargetedRiskFocus,
  type I2TargetedSummary,
  emptyI2TargetedRow,
  emptyI2TargetedSampleMeta,
  emptyI2TargetedRiskFocus,
  normalizeI2TargetedRow,
  normalizeI2TargetedSampleMeta,
  normalizeI2TargetedRiskFocus,
  summarizeI2Targeted,
  extractI2CapIncreaseTotal,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  buildI2TargetedConclusionDraft,
  buildI2TargetedAdjDrafts,
  mapSampledToI2TargetedRow,
  isAbnormalFlag,
  hasFailedCheck,
  I2_12_DEFAULT_COVERAGE_THRESHOLD,
} from './i2TargetedCheckModel'

export {
  type I2TargetedCheckRow,
  type I2TargetedSampleMeta,
  type I2TargetedRiskFocus,
  type I2TargetedSummary,
  type I2TargetedAdjDraft,
  emptyI2TargetedRow,
  I2_12_DEFAULT_COVERAGE_THRESHOLD,
  I2_12_TEST_CONTENT,
  I2_12_SAMPLE_METHODS,
  I2_12_CHECK_OPTIONS,
  I2_12_OBJECTIVES,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  isAbnormalFlag,
  hasFailedCheck,
  buildI2TargetedConclusionDraft,
  buildI2TargetedAdjDrafts,
  mapSampledToI2TargetedRow,
} from './i2TargetedCheckModel'

const STORAGE_ROWS = 'I2-12-rows'
const STORAGE_SAMPLE = 'I2-12-sample-meta'
const STORAGE_RISK = 'I2-12-risk-focus'
const STORAGE_LEGACY = 'I2-12-targeted'
const STORAGE_NOTE = 'I2-12-audit-note'
const STORAGE_CONCLUSION = 'I2-12-audit-conclusion'
const I22_ROWS = 'I2-2-rows'

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

export function useI2TargetedCheck(
  allResponses: Ref<Map<string, any>> | (() => Map<string, any>),
  options?: {
    saveResponse?: (sheetCode: string, data: Record<string, any>) => Promise<void>
  },
) {
  const getMap = typeof allResponses === 'function'
    ? allResponses
    : () => allResponses.value

  const rows = ref<I2TargetedCheckRow[]>([])
  const sampleMeta = ref<I2TargetedSampleMeta>(emptyI2TargetedSampleMeta())
  const riskFocus = ref<I2TargetedRiskFocus>(emptyI2TargetedRiskFocus())
  const auditNote = ref('')
  const auditConclusion = ref('')

  function load() {
    const map = getMap()
    rows.value = _safeParseArray(map.get(STORAGE_ROWS)).map(normalizeI2TargetedRow)

    sampleMeta.value = normalizeI2TargetedSampleMeta(_parseObject(map.get(STORAGE_SAMPLE)))

    // 风险关注：优先新 key，否则迁移旧 I2-12-targeted
    const riskRaw = _parseObject(map.get(STORAGE_RISK))
      || _parseObject(map.get(STORAGE_LEGACY))
    riskFocus.value = normalizeI2TargetedRiskFocus(riskRaw)

    auditNote.value = _readText(map.get(STORAGE_NOTE))
    auditConclusion.value = _readText(map.get(STORAGE_CONCLUSION))

    // 旧版 overallConclusion 并入审计结论（仅当结论为空）
    if (!auditConclusion.value && riskRaw?.overallConclusion) {
      auditConclusion.value = String(riskRaw.overallConclusion)
    }

    if (!sampleMeta.value.populationManual) {
      const linked = extractI2CapIncreaseTotal(map.get(I22_ROWS))
      if (linked > 0) sampleMeta.value.populationAmount = linked
    }
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
      m.get(I22_ROWS),
    ]
  }, () => load(), { immediate: true, deep: false })

  const linkedCapTotal: ComputedRef<{ amount: number; source: string }> = computed(() => {
    const amt = extractI2CapIncreaseTotal(getMap().get(I22_ROWS))
    return amt > 0 ? { amount: amt, source: 'I2-2本期资本化增加' } : { amount: 0, source: '' }
  })

  const summary: ComputedRef<I2TargetedSummary> = computed(() =>
    summarizeI2Targeted(rows.value, sampleMeta.value.populationAmount),
  )

  const coverageLow = computed(() =>
    summary.value.coverageRate != null
    && summary.value.coverageRate < sampleMeta.value.coverageThreshold
    && summary.value.periodTotal > 0,
  )

  const coverageLabel = computed(() => formatLayeredCoverageLabel(summary.value))

  const coverageTagType = computed(() => {
    if (summary.value.coverageRate == null) return 'info'
    if (coverageLow.value) return 'danger'
    return 'success'
  })

  const adjDrafts = computed(() => buildI2TargetedAdjDrafts(rows.value))

  function addRow(partial?: Partial<I2TargetedCheckRow>) {
    rows.value.push(emptyI2TargetedRow(partial))
  }

  function removeRow(rowId: string) {
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
  }

  function updateRow(rowId: string, field: keyof I2TargetedCheckRow, value: string | number | boolean) {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    if ((field === 'check1' || field === 'check2' || field === 'check3' || field === 'check4' || field === 'check5')
      && value === '×' && !isAbnormalFlag(row.isAbnormal)) {
      row.isAbnormal = '是'
    }
  }

  /** 抽凭引擎回填 */
  function fillFromSampledVouchers(samples: any[]): number {
    if (!Array.isArray(samples) || !samples.length) return 0
    const existing = new Set(
      rows.value.map((r) => `${r.voucherDate}|${r.voucherNo}`).filter((k) => k !== '|'),
    )
    let n = 0
    for (const s of samples) {
      const mapped = mapSampledToI2TargetedRow(s)
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

  function syncPopulationFromI22(): { ok: boolean; message: string } {
    const amt = linkedCapTotal.value.amount
    if (!(amt > 0)) return { ok: false, message: 'I2-2 无本期资本化增加可带入' }
    setPopulationAmount(amt, false)
    sampleMeta.value.populationDesc = 'I2-2 本期资本化增加合计（开发支出借方发生额代理）'
    return { ok: true, message: `已带入总体金额 ${amt.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}` }
  }

  function appendAdjDraftsToNote(): { ok: boolean; message: string; count: number } {
    const drafts = adjDrafts.value
    if (!drafts.length) return { ok: false, count: 0, message: '无核对×可生成调整草稿' }
    const block = drafts.map((d, i) =>
      `${i + 1}. ${d.suggestedNote}\n   ${d.suggestedEntry}`,
    ).join('\n')
    auditNote.value = auditNote.value
      ? `${auditNote.value.trim()}\n\n【I2-12 调整建议草稿】\n${block}`
      : `【I2-12 调整建议草稿】\n${block}`
    return { ok: true, count: drafts.length, message: `已写入 ${drafts.length} 条调整建议到审计说明` }
  }

  function fillConclusionDraft() {
    auditConclusion.value = buildI2TargetedConclusionDraft({
      sampleCount: summary.value.sampleCount,
      coverageLabel: coverageLabel.value,
      anomalyCount: summary.value.anomalyCount,
      failCheckCount: summary.value.failCheckCount,
      riskFocus: riskFocus.value,
    })
  }

  async function persistAll() {
    if (!options?.saveResponse) return
    // 同步样本量默认值
    if (!sampleMeta.value.sampleSize && rows.value.length) {
      sampleMeta.value.sampleSize = rows.value.length
    }
    await options.saveResponse('I2-12', {
      [STORAGE_ROWS]: JSON.stringify(rows.value),
      [STORAGE_SAMPLE]: JSON.stringify(sampleMeta.value),
      [STORAGE_RISK]: JSON.stringify(riskFocus.value),
      [STORAGE_NOTE]: auditNote.value,
      [STORAGE_CONCLUSION]: auditConclusion.value,
    })
  }

  async function saveNote(val: string) {
    auditNote.value = val
    if (options?.saveResponse) {
      await options.saveResponse('I2-12', { [STORAGE_NOTE]: val })
    }
  }

  async function saveConclusion(val: string) {
    auditConclusion.value = val
    if (options?.saveResponse) {
      await options.saveResponse('I2-12', { [STORAGE_CONCLUSION]: val })
    }
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
    coverageTagType,
    linkedCapTotal,
    adjDrafts,
    addRow,
    removeRow,
    updateRow,
    fillFromSampledVouchers,
    setPopulationAmount,
    syncPopulationFromI22,
    appendAdjDraftsToNote,
    fillConclusionDraft,
    persistAll,
    saveNote,
    saveConclusion,
    load,
  }
}

export default useI2TargetedCheck
