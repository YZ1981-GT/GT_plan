/**
 * useI2MaterialCheck — I2-8 研发材料投入检查表
 * 样本选取 + 账证双栏 + 检查比例（联动 I2-7 材料费）
 */
import { ref, computed, watch, toValue, type MaybeRefOrGetter, type Ref, type ComputedRef } from 'vue'
import {
  type I2MaterialCheckRow,
  type I2MaterialSampleMeta,
  type I2MaterialSummary,
  emptyI2MaterialRow,
  emptyI2MaterialSampleMeta,
  normalizeI2MaterialRow,
  normalizeI2MaterialSampleMeta,
  summarizeI2Material,
  extractI27MaterialTotal,
  formatCoverageLabel,
  suggestAbnormal,
} from './i2MaterialCheckModel'
import {
  useVoucherCheckFill, withRowMeta,
  type EngineFilledPayload, type FillSample, type PreparedItem, type UndoRequestPayload,
} from './shared/voucherCheckFill'
import { assetAmount, assetLegacyKey, sampleOf } from './assetVoucherFill'

export {
  type I2MaterialCheckRow,
  type I2MaterialSampleMeta,
  type I2MaterialSummary,
  emptyI2MaterialRow,
  I2_MATERIAL_DEFAULT_COVERAGE_THRESHOLD,
  I2_MATERIAL_TEST_CONTENT,
  I2_MATERIAL_SAMPLE_METHODS,
  formatCoverageLabel,
  hasQtyMismatch,
  hasProjectMismatch,
  suggestAbnormal,
} from './i2MaterialCheckModel'

const STORAGE_ROWS = 'I2-8-rows'
const STORAGE_SAMPLE = 'I2-8-sample-meta'
const STORAGE_NOTE = 'I2-8-audit-note'
const STORAGE_CONCLUSION = 'I2-8-audit-conclusion'
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

/** 行上已填核对内容（替换与撤销抽凭时据此先确认）：项目、存货、数量、领料单各栏、索引号、异常与结论 */
export function hasI2MaterialContent(r: I2MaterialCheckRow): boolean {
  return [r.projectName, r.inventoryName, r.unit, r.slipDateNo, r.recipient, r.recipientDept, r.slipProject,
    r.indexRef, r.isAbnormal, r.conclusion].some(v => String(v ?? '').trim() !== '')
    || Number(r.quantity) !== 0 || Number(r.slipQty) !== 0
}

/**
 * 共享回填函数的待写入项 → 材料投入检查行（spec voucher-identity-writeback-and-audit-phase 任务 12）：凭证号、业务内容、
 * 借方金额（样本自己那一栏，红字带符号照记）、对方科目与对方明细（按后端配对，配不上写「多科目」）
 */
function rowFromPrepared(item: PreparedItem): I2MaterialCheckRow {
  const s = sampleOf(item)
  const name = item.counterpartAccountName
  return emptyI2MaterialRow({
    voucherNo: String(s.voucherNo ?? ''),
    debitAmount: assetAmount(item, 'debit'),
    businessDesc: String(s.summary ?? ''),
    counterpartAccount: item.counterpartAccount,
    counterpartDetail: name && name !== item.counterpartAccount ? name : '',
    projectName: '',
  })
}

export function useI2MaterialCheck(
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

  const rows = ref<I2MaterialCheckRow[]>([])
  const sampleMeta = ref<I2MaterialSampleMeta>(emptyI2MaterialSampleMeta())
  const auditNote = ref('')
  const auditConclusion = ref('')

  function load() {
    const map = getMap()
    rows.value = _safeParseArray(map.get(STORAGE_ROWS)).map(r => withRowMeta(normalizeI2MaterialRow(r), r))
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
    sampleMeta.value = normalizeI2MaterialSampleMeta(parsedMeta)

    auditNote.value = _readText(map.get(STORAGE_NOTE))
    auditConclusion.value = _readText(map.get(STORAGE_CONCLUSION))

    // 非手工总体时，自动跟 I2-7 材料费
    if (!sampleMeta.value.populationManual) {
      const linked = extractI27MaterialTotal(map.get(I27_ROWS))
      if (linked > 0) sampleMeta.value.populationAmount = linked
    }
  }

  /**
   * 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读：共享回填函数（一个样本一行）。改完整页保存（与「保存」同一次写入）：
   * 父组件存一项就改一项 allResponses、本函数的 watch 随即整页重读，只存行会把未保存的抽样说明读回旧值。
   * 原实现回填只改内存，不点保存就丢（抽凭登记里却记着本底稿抽了这些凭证），也不去重
   */
  const voucherFill = useVoucherCheckFill<I2MaterialCheckRow>({
    projectId: () => toValue(options?.projectId),
    tables: rows,
    policy: 'join',
    mapSampleToRow: item => rowFromPrepared(item),
    persist: () => persistAll(),
    hasUserContent: hasI2MaterialContent,
    // 旧行（没有 `_gt`）身份：凭证号 + 借方金额（表里没有凭证日期）
    legacy: r => assetLegacyKey(r.voucherNo, '', r.debitAmount),
    readonly: () => toValue(options?.isReadonly) === true,
  })

  watch(() => {
    const m = getMap()
    return [m.get(STORAGE_ROWS), m.get(STORAGE_SAMPLE), m.get(STORAGE_NOTE), m.get(STORAGE_CONCLUSION), m.get(I27_ROWS)]
  }, () => load(), { immediate: true, deep: false })

  const linkedMaterialTotal: ComputedRef<{ amount: number; source: string }> = computed(() => {
    const amt = extractI27MaterialTotal(getMap().get(I27_ROWS))
    return amt > 0 ? { amount: amt, source: 'I2-7材料费' } : { amount: 0, source: '' }
  })

  const summary: ComputedRef<I2MaterialSummary> = computed(() =>
    summarizeI2Material(rows.value, sampleMeta.value.populationAmount),
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
    const linked = linkedMaterialTotal.value.amount
    if (linked <= 0) return false
    return Math.abs(linked - sampleMeta.value.populationAmount) > 0.01
  })

  function addRow(partial?: Partial<I2MaterialCheckRow>) {
    rows.value.push(emptyI2MaterialRow(partial))
  }

  function removeRow(rowId: string) {
    rows.value = rows.value.filter((r) => r.rowId !== rowId || voucherFill.isRowLocked(r))
  }

  function applySuggestAbnormal(row: I2MaterialCheckRow) {
    if (row.isAbnormal && row.isAbnormal !== '否') return
    const s = suggestAbnormal(row)
    if (s) row.isAbnormal = s
  }

  function syncPopulationFromI27() {
    const amt = linkedMaterialTotal.value.amount
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
    await save('I2-8', {
      [STORAGE_ROWS]: JSON.stringify(voucherFill.guardPersist(rows.value)),
      [STORAGE_SAMPLE]: JSON.stringify(sampleMeta.value),
      [STORAGE_NOTE]: auditNote.value,
      [STORAGE_CONCLUSION]: auditConclusion.value,
    })
  }

  async function saveAuditNote(val: string) {
    auditNote.value = val
    await options?.saveResponse?.('I2-8', { [STORAGE_NOTE]: val })
  }

  async function saveAuditConclusion(val: string) {
    auditConclusion.value = val
    await options?.saveResponse?.('I2-8', { [STORAGE_CONCLUSION]: val })
  }

  return {
    rows,
    sampleMeta,
    auditNote,
    auditConclusion,
    summary,
    linkedMaterialTotal,
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
