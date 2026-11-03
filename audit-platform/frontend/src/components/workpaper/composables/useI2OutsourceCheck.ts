/**
 * useI2OutsourceCheck — I2-11 委外研发检查表
 * 测试原因 + 合同/受托方/凭证/验收核对 + 检查比例（可联动 I2-7 委外金额）
 */
import { ref, computed, watch, toValue, type MaybeRefOrGetter, type Ref, type ComputedRef } from 'vue'
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
import {
  useVoucherCheckFill, withRowMeta,
  type EngineFilledPayload, type FillSample, type PreparedItem, type UndoRequestPayload,
} from './shared/voucherCheckFill'
import { assetAmount, assetLegacyKey, sampleOf, type AssetSample } from './assetVoucherFill'
import { partyNameForColumn } from './shared/samplingPartyTarget'

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

/** 行上已填核对内容（替换与撤销抽凭时据此先确认）：委外原因、合同与受托方资料、验收、异常、索引号、结论、备注 */
export function hasI2OutsourceContent(r: I2OutsourceCheckRow): boolean {
  return [r.outsourceReason, r.contractDate, r.contractNo, r.rdContent, r.ipOwnership, r.qualification,
    r.registeredCapital, r.insuredCount, r.acceptanceDate, r.acceptanceResult, r.isAbnormal, r.indexRef,
    r.conclusion, r.remark].some(v => String(v ?? '').trim() !== '')
    || Number(r.acceptanceAmount) !== 0
}

/**
 * 共享回填函数的待写入项 → 委外研发检查行（spec voucher-identity-writeback-and-audit-phase 任务 12）：凭证号与日期、
 * 业务内容、记账金额（样本自己那一栏，红字带符号照记）、研发项目（样本科目名，与原实现相同）、受托方取辅助核算往来单位
 * （唯一命中才填，`partyNameForColumn`）。原实现把对方科目编码写进「受托方」
 */
function rowFromPrepared(item: PreparedItem): I2OutsourceCheckRow {
  const s = sampleOf(item) as AssetSample & { accountName?: string | null }
  return emptyI2OutsourceRow({
    entrustedParty: partyNameForColumn(item.sample, 'supplier'),
    amount: assetAmount(item, 'debit'),
    voucherNo: String(s.voucherNo ?? ''),
    voucherDate: String(s.voucherDate ?? ''),
    businessDesc: String(s.summary ?? ''),
    projectName: String(s.accountName ?? ''),
  })
}

export function useI2OutsourceCheck(
  allResponses: Ref<Map<string, any>> | (() => Map<string, any>),
  options?: {
    saveResponse?: (sheetCode: string, data: Record<string, any>) => Promise<void>
    projectId?: MaybeRefOrGetter<string | null | undefined>
    /** 整张底稿只读：抽凭回填 / 挂凭导入 / 撤销一律不改行 */
    isReadonly?: MaybeRefOrGetter<boolean | undefined>
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
    rows.value = _safeParseArray(map.get(STORAGE_ROWS)).map(r => withRowMeta(normalizeI2OutsourceRow(r), r))
    voucherFill.markLoaded()

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

  /**
   * 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读：共享回填函数（一个样本一行）。改完整页保存（与「保存」同一次写入）：
   * 父组件存一项就改一项 allResponses、本函数的 watch 随即整页重读，只存行会把未保存的抽样说明读回旧值。
   * 原实现回填只改内存，不点保存就丢（抽凭登记里却记着本底稿抽了这些凭证），也不去重
   */
  const voucherFill = useVoucherCheckFill<I2OutsourceCheckRow>({
    projectId: () => toValue(options?.projectId),
    tables: rows,
    policy: 'join',
    mapSampleToRow: item => rowFromPrepared(item),
    persist: () => persistAll(),
    hasUserContent: hasI2OutsourceContent,
    // 旧行（没有 `_gt`）身份：凭证号 + 凭证日期 + 记账金额
    legacy: r => assetLegacyKey(r.voucherNo, r.voucherDate, r.amount),
    readonly: () => toValue(options?.isReadonly) === true,
  })

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
    rows.value = rows.value.filter((r) => r.rowId !== rowId || voucherFill.isRowLocked(r))
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
      [STORAGE_ROWS]: JSON.stringify(voucherFill.guardPersist(rows.value)),
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
    onEngineFilled: (payload: EngineFilledPayload) => voucherFill.onEngineFilled(payload),
    onAttachImported: (samples: FillSample[]) => voucherFill.onAttachImported(samples),
    onUndoRequest: (payload: UndoRequestPayload) => voucherFill.onUndoRequest(payload),
    voucherRowClass: voucherFill.rowClass,
    isVoucherRowLocked: voucherFill.isRowLocked,
    voucherFillReady: voucherFill.ready,
  }
}
