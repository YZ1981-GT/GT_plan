/**
 * useI5TargetedCheck — I5-4 其他非流动资产针对性检查表
 * 样本选取 + 凭证核对 1~5 + 检查比例（可联动 I5-2 本期发生额）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  type I5TargetedCheckRow,
  type I5TargetedSampleMeta,
  type I5TargetedRiskFocus,
  type I5TargetedSummary,
  emptyI5TargetedRow,
  emptyI5TargetedSampleMeta,
  emptyI5TargetedRiskFocus,
  normalizeI5TargetedRow,
  normalizeI5TargetedSampleMeta,
  normalizeI5TargetedRiskFocus,
  summarizeI5Targeted,
  extractI5PeriodMovement,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  buildI5CoverageFooter,
  buildI5TargetedConclusionDraft,
  buildI5TargetedAdjDrafts,
  buildI53LinesFromTargetedDrafts,
  mergeI53LinesSkippingExisting,
  mapSampledToI5TargetedRow,
  suggestAbnormalFromFailedChecks,
  syncSpecificAmountFromRows,
  checkI5SpecificAmountConsistency,
  extractI52ProjectCatalog,
  riskFocusIncomplete,
  isAbnormalFlag,
  hasFailedCheck,
  I5_4_DEFAULT_COVERAGE_THRESHOLD,
} from './i5TargetedCheckModel'

export {
  type I5TargetedCheckRow,
  type I5TargetedSampleMeta,
  type I5TargetedRiskFocus,
  type I5TargetedSummary,
  type I5TargetedAdjDraft,
  type I5SpecificAmountCheck,
  type I52ProjectRef,
  emptyI5TargetedRow,
  I5_4_DEFAULT_COVERAGE_THRESHOLD,
  I5_4_TEST_CONTENT,
  I5_4_TEST_REASONS,
  I5_4_SAMPLE_METHODS,
  I5_4_CHECK_OPTIONS,
  I5_4_ABNORMAL_OPTIONS,
  I5_4_OBJECTIVES,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  isAbnormalFlag,
  hasFailedCheck,
  suggestAbnormalFromFailedChecks,
  syncSpecificAmountFromRows,
  checkI5SpecificAmountConsistency,
  riskFocusIncomplete,
  buildI5TargetedConclusionDraft,
  buildI5TargetedAdjDrafts,
  buildI53LinesFromTargetedDrafts,
  mergeI53LinesSkippingExisting,
  mapSampledToI5TargetedRow,
} from './i5TargetedCheckModel'

const STORAGE_ROWS = 'I5-4-rows'
const STORAGE_SAMPLE = 'I5-4-sample-meta'
const STORAGE_RISK = 'I5-4-risk-focus'
const STORAGE_NOTE = 'I5-4-audit-note'
const STORAGE_CONCLUSION = 'I5-4-audit-conclusion'
const I52_ROWS = 'I5-2-rows'

// 旧段落型分散 key（Task 4.5 段落型实现遗留）
const LEGACY_CHECK_ITEM_KEYS = [
  'I5-4-class-to-ltpa',
  'I5-4-class-to-intangible',
  'I5-4-class-to-current',
  'I5-4-maturity-reclass',
  'I5-4-maturity-verifiable',
  'I5-4-maturity-extended',
  'I5-4-recover-credit',
  'I5-4-recover-long-pending',
  'I5-4-recover-impairment',
] as const
const LEGACY_CLASSIFICATION_ITEMS = LEGACY_CHECK_ITEM_KEYS.slice(0, 3)
const LEGACY_MATURITY_ITEMS = LEGACY_CHECK_ITEM_KEYS.slice(3, 6)
const LEGACY_RECOVERABILITY_ITEMS = LEGACY_CHECK_ITEM_KEYS.slice(6, 9)
const LEGACY_CLASSIFICATION_TEXT = 'I5-4-classification-conclusion'
const LEGACY_MATURITY_TEXT = 'I5-4-maturity-conclusion'
const LEGACY_RECOVERABILITY_TEXT = 'I5-4-recoverability-conclusion'
const LEGACY_OVERALL_CONCLUSION = 'I5-4-conclusion'
const LEGACY_AUDIT_CONCLUSION = 'I5-targeted-check-audit-conclusion'

const CHECK_ITEM_LABELS: Record<string, string> = {
  'I5-4-class-to-ltpa': '应重分类到长期待摊费用',
  'I5-4-class-to-intangible': '应重分类到无形资产',
  'I5-4-class-to-current': '应归入流动资产科目',
  'I5-4-maturity-reclass': '距到期日＜12个月未重分类',
  'I5-4-maturity-verifiable': '到期日信息完整可验证',
  'I5-4-maturity-extended': '期限延长但未重新评估',
  'I5-4-recover-credit': '对方信用恶化/违约',
  'I5-4-recover-long-pending': '长期挂账未清理',
  'I5-4-recover-impairment': '已识别减值迹象已恰当计提减值',
}

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

export function useI5TargetedCheck(
  allResponses: Ref<Map<string, any>> | (() => Map<string, any>),
  options?: {
    /** I5 父组件契约：逐 item_id 持久化 */
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

  const rows = ref<I5TargetedCheckRow[]>([])
  const sampleMeta = ref<I5TargetedSampleMeta>(emptyI5TargetedSampleMeta())
  const riskFocus = ref<I5TargetedRiskFocus>(emptyI5TargetedRiskFocus())
  const auditNote = ref('')
  const auditConclusion = ref('')

  function load() {
    const map = getMap()
    rows.value = _safeParseArray(map.get(STORAGE_ROWS)).map(normalizeI5TargetedRow)

    sampleMeta.value = normalizeI5TargetedSampleMeta(_parseObject(map.get(STORAGE_SAMPLE)))

    const riskRaw = _parseObject(map.get(STORAGE_RISK)) || _legacyRiskFocusRaw(map)
    riskFocus.value = normalizeI5TargetedRiskFocus(riskRaw)

    auditNote.value = _readText(map.get(STORAGE_NOTE))
    auditConclusion.value = _readText(map.get(STORAGE_CONCLUSION))
      || _readText(map.get(LEGACY_OVERALL_CONCLUSION))
      || _readText(map.get(LEGACY_AUDIT_CONCLUSION))

    if (!sampleMeta.value.populationManual) {
      const mv = extractI5PeriodMovement(map.get(I52_ROWS), getYear())
      if (mv.debitTotal > 0) sampleMeta.value.populationAmount = mv.debitTotal
      if (mv.creditTotal > 0) sampleMeta.value.populationCreditAmount = mv.creditTotal
    }
  }

  /** 旧段落型分散 key（9 个 radio + 3 个 textarea 结论）拼装为 riskFocus 迁移对象 */
  function _legacyRiskFocusRaw(map: Map<string, any>): any {
    const _itemsText = (keys: readonly string[]) => keys
      .map((k) => {
        const v = _readText(map.get(k))
        return v && v !== '不适用' ? `${CHECK_ITEM_LABELS[k] || k}：${v}` : ''
      })
      .filter(Boolean)
      .join('\n')

    const classificationItems = _itemsText(LEGACY_CLASSIFICATION_ITEMS)
    const maturityItems = _itemsText(LEGACY_MATURITY_ITEMS)
    const recoverabilityItems = _itemsText(LEGACY_RECOVERABILITY_ITEMS)
    const classificationText = _readText(map.get(LEGACY_CLASSIFICATION_TEXT))
    const maturityText = _readText(map.get(LEGACY_MATURITY_TEXT))
    const recoverabilityText = _readText(map.get(LEGACY_RECOVERABILITY_TEXT))

    if (!classificationItems && !maturityItems && !recoverabilityItems
      && !classificationText && !maturityText && !recoverabilityText) {
      return null
    }
    return {
      classificationItems,
      maturityItems,
      recoverabilityItems,
      classificationText,
      maturityText,
      recoverabilityText,
    }
  }

  watch(() => {
    const m = getMap()
    return [
      m.get(STORAGE_ROWS),
      m.get(STORAGE_SAMPLE),
      m.get(STORAGE_RISK),
      m.get(STORAGE_NOTE),
      m.get(STORAGE_CONCLUSION),
      m.get(I52_ROWS),
      m.get(LEGACY_OVERALL_CONCLUSION),
      m.get(LEGACY_AUDIT_CONCLUSION),
      ...LEGACY_CHECK_ITEM_KEYS.map((k) => m.get(k)),
    ]
  }, () => load(), { immediate: true, deep: false })

  const linkedPeriod: ComputedRef<{
    debitTotal: number
    creditTotal: number
    originalTotal: number
    source: string
  }> = computed(() => {
    const mv = extractI5PeriodMovement(getMap().get(I52_ROWS), getYear())
    return mv.debitTotal > 0 || mv.creditTotal > 0 || mv.originalTotal > 0
      ? mv
      : { debitTotal: 0, creditTotal: 0, originalTotal: 0, source: '' }
  })

  const summary: ComputedRef<I5TargetedSummary> = computed(() =>
    summarizeI5Targeted(
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

  const coverageFooter = computed(() =>
    buildI5CoverageFooter(summary.value, sampleMeta.value.populationCreditAmount),
  )

  const coverageTagType = computed(() => {
    if (summary.value.coverageRate == null) return 'info'
    if (coverageLow.value) return 'danger'
    return 'success'
  })

  const i52DetailRows = computed(() => _safeParseArray(getMap().get(I52_ROWS)))

  const adjDrafts = computed(() => buildI5TargetedAdjDrafts(rows.value, {
    detailRows: i52DetailRows.value,
    auditYear: getYear(),
  }))
  const pushableAdjDrafts = computed(() =>
    adjDrafts.value.filter((d) => d.draftKind !== 'doc_only' && d.amount > 0.005),
  )

  /** 第二节特定样本金额 vs 表内特定借方 */
  const specificAmountCheck = computed(() =>
    checkI5SpecificAmountConsistency(
      sampleMeta.value.specificAmount,
      summary.value.specificDebitTotal,
    ),
  )

  /** I5-2 项目名目录（抽凭挂接 / 下拉） */
  const i52ProjectCatalog = computed(() => extractI52ProjectCatalog(getMap().get(I52_ROWS)))
  const i52ProjectNames = computed(() => i52ProjectCatalog.value.map((p) => p.projectName))

  /** 有抽凭样本但专项风险结论全空 */
  const riskFocusGap = computed(() =>
    riskFocusIncomplete(riskFocus.value, summary.value.sampleCount),
  )

  function addRow(partial?: Partial<I5TargetedCheckRow>) {
    rows.value.push(emptyI5TargetedRow(partial))
  }

  function removeRow(rowId: string) {
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
  }

  function updateRow(rowId: string, field: keyof I5TargetedCheckRow, value: string | number | boolean) {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    if (field === 'selectionReason') {
      const reason = String(value || '')
      row.isSpecific = !!reason
    }
    if (field === 'isSpecific' && !value) {
      row.selectionReason = ''
    }
    if ((field === 'check1' || field === 'check2' || field === 'check3' || field === 'check4' || field === 'check5')
      && value === '×') {
      const cur = (row.isAbnormal || '').trim()
      if (!isAbnormalFlag(cur) || cur === '是') {
        row.isAbnormal = suggestAbnormalFromFailedChecks(row)
      }
    }
  }

  /** 将表内特定样本借方合计回写到第二节「特定样本金额」 */
  function syncSpecificAmount(): { ok: boolean; amount: number; message: string } {
    const amount = syncSpecificAmountFromRows(rows.value)
    sampleMeta.value.specificAmount = amount
    return {
      ok: true,
      amount,
      message: `已同步特定样本金额 ${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}（${summary.value.specificCount} 笔）`,
    }
  }

  function fillFromSampledVouchers(samples: any[]): number {
    if (!Array.isArray(samples) || !samples.length) return 0
    const catalog = i52ProjectCatalog.value
    const existing = new Set(
      rows.value.map((r) => `${r.voucherDate}|${r.voucherNo}`).filter((k) => k !== '|'),
    )
    let n = 0
    for (const s of samples) {
      const mapped = mapSampledToI5TargetedRow(s, catalog)
      if (mapped.selectionReason) mapped.isSpecific = true
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

  function syncPopulationFromI52(mode: 'period' | 'original' = 'period'): { ok: boolean; message: string } {
    const mv = linkedPeriod.value
    if (mode === 'original') {
      if (!(mv.originalTotal > 0)) return { ok: false, message: 'I5-2 无原始金额合计可带入' }
      setPopulationAmount(mv.originalTotal, false)
      sampleMeta.value.populationCreditAmount = mv.creditTotal
      sampleMeta.value.populationDesc = 'I5-2 原始金额合计（存在性测试总体）'
      return {
        ok: true,
        message: `已带入原始金额合计 ${mv.originalTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`,
      }
    }
    if (!(mv.debitTotal > 0) && !(mv.creditTotal > 0)) {
      return { ok: false, message: 'I5-2 无本期发生额可带入（可改用「带入原始金额合计」）' }
    }
    if (mv.debitTotal > 0) setPopulationAmount(mv.debitTotal, false)
    sampleMeta.value.populationCreditAmount = mv.creditTotal
    sampleMeta.value.populationDesc = 'I5-2 本期借方发生额代理（当期新增其他非流动资产）'
    const parts = [
      mv.debitTotal > 0 ? `借方 ${mv.debitTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}` : '',
      mv.creditTotal > 0 ? `贷方(减少) ${mv.creditTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}` : '',
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
      ? `${auditNote.value.trim()}\n\n【I5-4 调整建议草稿】\n${block}`
      : `【I5-4 调整建议草稿】\n${block}`
    return { ok: true, count: drafts.length, message: `已写入 ${drafts.length} 条调整建议到审计说明` }
  }

  /**
   * 将可推送的核对×草稿写入 I5-3-rows（费用化/跨期/减值）
   * 成功后在审计说明追加【已推送 I5-3】时间戳。
   */
  async function pushAdjDraftsToI53(): Promise<{ ok: boolean; added: number; message: string }> {
    const pushable = pushableAdjDrafts.value
    if (!pushable.length) {
      return { ok: false, added: 0, message: '无分类/跨期/减值类核对×可推送（资料类请先补证据）' }
    }
    const lines = buildI53LinesFromTargetedDrafts(pushable)
    if (!lines.length) return { ok: false, added: 0, message: '草稿金额无效，未生成分录' }

    const existing = _safeParseArray(getMap().get('I5-3-rows'))
    const { merged, added } = mergeI53LinesSkippingExisting(existing, lines)
    if (!added) {
      return { ok: false, added: 0, message: '同说明分录已存在于 I5-3，未重复写入' }
    }
    if (options?.onSave) {
      await options.onSave('I5-3-rows', JSON.stringify(merged))
    }
    try {
      getMap().set('I5-3-rows', { item_id: 'I5-3-rows', conclusion: null, remark: JSON.stringify(merged) })
    } catch { /* ignore */ }
    try {
      window.dispatchEvent(new CustomEvent('i5:adjustments-changed', {
        detail: { source: 'I5-4', rowCount: merged.length },
      }))
    } catch { /* silent */ }

    const stamp = new Date().toISOString().slice(0, 19).replace('T', ' ')
    const kinds = [...new Set(pushable.map((d) => d.draftKind))].join('、')
    const pushBlock = `【已推送 I5-3 @ ${stamp}】${added} 行（${kinds}）`
    if (!auditNote.value.includes('【已推送 I5-3')) {
      auditNote.value = auditNote.value
        ? `${auditNote.value.trim()}\n\n${pushBlock}`
        : pushBlock
    } else {
      auditNote.value = auditNote.value.replace(/【已推送 I5-3[^\n]*/, pushBlock)
    }
    if (options?.onSave) await options.onSave(STORAGE_NOTE, auditNote.value)

    return {
      ok: true,
      added,
      message: `已推送 ${added} 行至 I5-3（请打开调整分录复核并同步审定表）`,
    }
  }

  function fillConclusionDraft() {
    auditConclusion.value = buildI5TargetedConclusionDraft({
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

  async function saveRiskFocus() {
    if (options?.onSave) await options.onSave(STORAGE_RISK, JSON.stringify(riskFocus.value))
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
    coverageFooter,
    coverageTagType,
    linkedPeriod,
    adjDrafts,
    pushableAdjDrafts,
    specificAmountCheck,
    i52ProjectNames,
    riskFocusGap,
    addRow,
    removeRow,
    updateRow,
    fillFromSampledVouchers,
    setPopulationAmount,
    syncPopulationFromI52,
    syncSpecificAmount,
    appendAdjDraftsToNote,
    pushAdjDraftsToI53,
    fillConclusionDraft,
    persistAll,
    saveNote,
    saveConclusion,
    saveRiskFocus,
    load,
  }
}

export default useI5TargetedCheck
