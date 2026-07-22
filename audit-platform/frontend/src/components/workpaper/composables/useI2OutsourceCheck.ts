/**
 * useI2OutsourceCheck — I2-11 委外研发检查表
 * 测试原因 + 合同/受托方/凭证/验收核对 + 检查比例（可联动 I2-7 委外金额）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  type I2OutsourceCheckRow,
  type I2OutsourceSampleMeta,
  type I2OutsourceSummary,
  emptyI2OutsourceRow,
  emptyI2OutsourceSampleMeta,
  normalizeI2OutsourceRow,
  normalizeI2OutsourceSampleMeta,
  summarizeI2Outsource,
  extractI27OutsourceTotal,
  formatCoverageLabel,
  suggestOutsourceAbnormal,
} from './i2OutsourceCheckModel'

export {
  type I2OutsourceCheckRow,
  type I2OutsourceSampleMeta,
  type I2OutsourceSummary,
  emptyI2OutsourceRow,
  I2_OUTSOURCE_DEFAULT_COVERAGE_THRESHOLD,
  I2_OUTSOURCE_TEST_CONTENT,
  I2_OUTSOURCE_TEST_REASONS,
  I2_OUTSOURCE_SAMPLE_METHODS,
  formatCoverageLabel,
  hasAmountMismatch,
  hasMissingAcceptance,
  suggestOutsourceAbnormal,
} from './i2OutsourceCheckModel'

const STORAGE_ROWS = 'I2-11-rows'
const STORAGE_SAMPLE = 'I2-11-sample-meta'
const STORAGE_NOTE = 'I2-11-audit-note'
const STORAGE_CONCLUSION = 'I2-11-audit-conclusion'
const I27_ROWS = 'I2-7-rows'

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

export function useI2OutsourceCheck(
  allResponses: Ref<Map<string, any>> | (() => Map<string, any>),
  options?: {
    saveResponse?: (sheetCode: string, data: Record<string, any>) => Promise<void>
  },
) {
  const getMap = typeof allResponses === 'function'
    ? allResponses
    : () => allResponses.value

  const rows = ref<I2OutsourceCheckRow[]>([])
  const sampleMeta = ref<I2OutsourceSampleMeta>(emptyI2OutsourceSampleMeta())
  const auditNote = ref('')
  const auditConclusion = ref('')

  function load() {
    const map = getMap()
    rows.value = _safeParseArray(map.get(STORAGE_ROWS)).map(normalizeI2OutsourceRow)

    const sampleRaw = map.get(STORAGE_SAMPLE)
    let parsedMeta: any = null
    if (typeof sampleRaw === 'string' && sampleRaw) {
      try { parsedMeta = JSON.parse(sampleRaw) } catch { parsedMeta = null }
    } else if (sampleRaw && typeof sampleRaw === 'object') {
      const remark = (sampleRaw as any).remark
      if (typeof remark === 'string' && remark) {
        try { parsedMeta = JSON.parse(remark) } catch { parsedMeta = sampleRaw }
      } else {
        parsedMeta = sampleRaw
      }
    }
    sampleMeta.value = normalizeI2OutsourceSampleMeta(parsedMeta)

    auditNote.value = _readText(map.get(STORAGE_NOTE))
    auditConclusion.value = _readText(map.get(STORAGE_CONCLUSION))

    if (!sampleMeta.value.populationManual) {
      const linked = extractI27OutsourceTotal(map.get(I27_ROWS))
      if (linked > 0) sampleMeta.value.populationAmount = linked
    }
  }

  watch(() => {
    const m = getMap()
    return [m.get(STORAGE_ROWS), m.get(STORAGE_SAMPLE), m.get(STORAGE_NOTE), m.get(STORAGE_CONCLUSION), m.get(I27_ROWS)]
  }, () => load(), { immediate: true, deep: false })

  const linkedOutsourceTotal: ComputedRef<{ amount: number; source: string }> = computed(() => {
    const amt = extractI27OutsourceTotal(getMap().get(I27_ROWS))
    return amt > 0 ? { amount: amt, source: 'I2-7委外' } : { amount: 0, source: '' }
  })

  const summary: ComputedRef<I2OutsourceSummary> = computed(() =>
    summarizeI2Outsource(rows.value, sampleMeta.value.populationAmount),
  )

  const coverageLow = computed(() =>
    summary.value.coverageRate != null
    && summary.value.coverageRate < sampleMeta.value.coverageThreshold
    && summary.value.periodTotal > 0,
  )

  const coverageLabel = computed(() => formatCoverageLabel(summary.value.coverageRate))

  const coverageTagType = computed(() => {
    if (summary.value.coverageRate == null) return 'info'
    if (coverageLow.value) return 'danger'
    return 'success'
  })

  /** 手工锁定总体后，I2-7 源值变化 → 过期提示 */
  const populationStale = computed(() => {
    if (!sampleMeta.value.populationManual) return false
    const linked = linkedOutsourceTotal.value.amount
    if (linked <= 0) return false
    return Math.abs(linked - sampleMeta.value.populationAmount) > 0.01
  })

  function addRow(partial?: Partial<I2OutsourceCheckRow>) {
    rows.value.push(emptyI2OutsourceRow(partial))
  }

  function removeRow(rowId: string) {
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
  }

  function applySuggestAbnormal(row: I2OutsourceCheckRow) {
    if (row.isAbnormal && row.isAbnormal !== '否') return
    const s = suggestOutsourceAbnormal(row)
    if (s) row.isAbnormal = s
  }

  function syncPopulationFromI27() {
    const amt = linkedOutsourceTotal.value.amount
    sampleMeta.value.populationAmount = amt
    sampleMeta.value.populationManual = false
  }

  function setPopulationAmount(v: number, manual = true) {
    sampleMeta.value.populationAmount = v
    sampleMeta.value.populationManual = manual
  }

  async function persistAll() {
    const save = options?.saveResponse
    if (!save) return
    await save('I2-11', {
      [STORAGE_ROWS]: JSON.stringify(rows.value),
      [STORAGE_SAMPLE]: JSON.stringify(sampleMeta.value),
      [STORAGE_NOTE]: auditNote.value,
      [STORAGE_CONCLUSION]: auditConclusion.value,
    })
  }

  async function saveAuditNote(val: string) {
    auditNote.value = val
    await options?.saveResponse?.('I2-11', { [STORAGE_NOTE]: val })
  }

  async function saveAuditConclusion(val: string) {
    auditConclusion.value = val
    await options?.saveResponse?.('I2-11', { [STORAGE_CONCLUSION]: val })
  }

  return {
    rows,
    sampleMeta,
    auditNote,
    auditConclusion,
    summary,
    linkedOutsourceTotal,
    coverageLow,
    coverageLabel,
    coverageTagType,
    populationStale,
    load,
    addRow,
    removeRow,
    applySuggestAbnormal,
    syncPopulationFromI27,
    setPopulationAmount,
    persistAll,
    saveAuditNote,
    saveAuditConclusion,
  }
}
