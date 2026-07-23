/**
 * useI6TargetedCheck — I6-4 研发费用针对性检查表
 * 样本选取 + 凭证核对 1~5 + 检查比例（可联动 I6-2 本期审定合计）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  type I6TargetedCheckRow,
  type I6TargetedSampleMeta,
  type I6TargetedRiskFocus,
  type I6TargetedSummary,
  emptyI6TargetedRow,
  emptyI6TargetedSampleMeta,
  emptyI6TargetedRiskFocus,
  normalizeI6TargetedRow,
  normalizeI6TargetedSampleMeta,
  normalizeI6TargetedRiskFocus,
  summarizeI6Targeted,
  extractI6PeriodMovement,
  extractI62ProjectCatalog,
  enrichRowsWithI62Projects,
  analyzeI62ProjectConsistency,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  buildI6CoverageFooter,
  buildI6TargetedConclusionDraft,
  buildI6TargetedAdjDrafts,
  buildI63LinesFromTargetedDrafts,
  mergeI63LinesSkippingExisting,
  parseI63Rows,
  mapSampledToI6TargetedRow,
  syncSpecificAmountFromRows,
  suggestAbnormalFromFailedChecks,
  isAbnormalFlag,
  hasFailedCheck,
  I6_4_DEFAULT_COVERAGE_THRESHOLD,
  I63_ROWS_KEY,
} from './i6TargetedCheckModel'

export {
  type I6TargetedCheckRow,
  type I6TargetedSampleMeta,
  type I6TargetedRiskFocus,
  type I6TargetedSummary,
  type I6TargetedAdjDraft,
  type I6CoverageFooter,
  type I62ProjectRef,
  emptyI6TargetedRow,
  I6_4_DEFAULT_COVERAGE_THRESHOLD,
  I6_4_TEST_CONTENT,
  I6_4_TEST_REASONS,
  I6_4_SAMPLE_METHODS,
  I6_4_CHECK_OPTIONS,
  I6_4_ABNORMAL_OPTIONS,
  I6_4_OBJECTIVES,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  buildI6CoverageFooter,
  isAbnormalFlag,
  hasFailedCheck,
  buildI6TargetedConclusionDraft,
  buildI6TargetedAdjDrafts,
  buildI63LinesFromTargetedDrafts,
  mergeI63LinesSkippingExisting,
  mapSampledToI6TargetedRow,
  extractI62ProjectCatalog,
  matchI62ProjectName,
  I63_ROWS_KEY,
} from './i6TargetedCheckModel'

const STORAGE_ROWS = 'I6-4-rows'
const STORAGE_SAMPLE = 'I6-4-sample-meta'
const STORAGE_RISK = 'I6-4-risk-focus'
const STORAGE_NOTE = 'I6-4-audit-note'
const STORAGE_CONCLUSION = 'I6-4-audit-conclusion'
const I62_ROWS = 'I6-2-detail-rows'

// 旧段落型分散 key（误将 I6-4 做成四维度问卷 + 加计扣除）—— load 时迁入 risk-focus
const LEGACY_COMPLETE_PROJECT = 'I6-4-complete-project'
const LEGACY_COMPLETE_MISCLASS = 'I6-4-complete-misclass'
const LEGACY_ALLOC_STAFF = 'I6-4-alloc-staff'
const LEGACY_ALLOC_BASIS = 'I6-4-alloc-basis'
const LEGACY_I2_PHASE = 'I6-4-i2-phase-div'
const LEGACY_I2_VR = 'I6-4-i2-vr-balance'
const LEGACY_COMPLETENESS_CONC = 'I6-4-completeness-conclusion'
const LEGACY_ALLOCATION_CONC = 'I6-4-allocation-conclusion'
const LEGACY_I2_CONC = 'I6-4-i2consistency-conclusion'
const LEGACY_SUPER_DEDUCTION_CONC = 'I6-4-superDeduction-conclusion'
const LEGACY_SUPER_DEDUCTION_ROWS = 'I6-4-super-deduction-rows'
const LEGACY_OVERALL_CONCLUSION = 'I6-4-conclusion'
const LEGACY_AUDIT_NOTE = 'I6-4-audit-note'

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

function _radioToConclusion(v: string): string {
  const s = (v || '').trim()
  if (!s) return ''
  if (s === '正常') return '未见异常'
  if (s === '异常') return '存在异常需跟进'
  if (s === '不适用') return '不适用'
  return s
}

export function useI6TargetedCheck(
  allResponses: Ref<Map<string, any>> | (() => Map<string, any>),
  options?: {
    onSave?: (itemId: string, value: any) => void | Promise<void>
    asOfYear?: Ref<number> | (() => number)
  },
) {
  const getMap = typeof allResponses === 'function'
    ? allResponses
    : () => allResponses.value

  const rows = ref<I6TargetedCheckRow[]>([])
  const sampleMeta = ref<I6TargetedSampleMeta>(emptyI6TargetedSampleMeta())
  const riskFocus = ref<I6TargetedRiskFocus>(emptyI6TargetedRiskFocus())
  const auditNote = ref('')
  const auditConclusion = ref('')

  function _legacyRiskFocusRaw(map: Map<string, any>): any {
    const completenessConc = _readText(map.get(LEGACY_COMPLETENESS_CONC))
      || _radioToConclusion(_readText(map.get(LEGACY_COMPLETE_PROJECT)))
      || _radioToConclusion(_readText(map.get(LEGACY_COMPLETE_MISCLASS)))
    const allocationConc = _readText(map.get(LEGACY_ALLOCATION_CONC))
      || _radioToConclusion(_readText(map.get(LEGACY_ALLOC_STAFF)))
      || _radioToConclusion(_readText(map.get(LEGACY_ALLOC_BASIS)))
    const i2Conc = _readText(map.get(LEGACY_I2_CONC))
      || _radioToConclusion(_readText(map.get(LEGACY_I2_PHASE)))
      || _radioToConclusion(_readText(map.get(LEGACY_I2_VR)))
    const superDedConc = _readText(map.get(LEGACY_SUPER_DEDUCTION_CONC))
    const superRows = _safeParseArray(map.get(LEGACY_SUPER_DEDUCTION_ROWS))
    let legacyDeductionNote = ''
    if (superDedConc || superRows.length) {
      legacyDeductionNote = [
        '【迁移提示】原 I6-4 加计扣除测算数据已归档；加计扣除请编制 N5-6-1，并与 I2 政策检查交叉核对。',
        superDedConc && `原结论：${superDedConc}`,
        superRows.length ? `原测算行数：${superRows.length}` : '',
      ].filter(Boolean).join('\n')
    }
    if (!completenessConc && !allocationConc && !i2Conc && !legacyDeductionNote) return null
    return {
      completenessConclusion: completenessConc,
      allocationConclusion: allocationConc,
      i2ConsistencyConclusion: i2Conc,
      legacyDeductionNote,
    }
  }

  function load() {
    const map = getMap()
    rows.value = _safeParseArray(map.get(STORAGE_ROWS)).map(normalizeI6TargetedRow)

    sampleMeta.value = normalizeI6TargetedSampleMeta(_parseObject(map.get(STORAGE_SAMPLE)))

    const riskRaw = _parseObject(map.get(STORAGE_RISK)) || _legacyRiskFocusRaw(map)
    riskFocus.value = normalizeI6TargetedRiskFocus(riskRaw)

    auditNote.value = _readText(map.get(STORAGE_NOTE)) || _readText(map.get(LEGACY_AUDIT_NOTE))
    auditConclusion.value = _readText(map.get(STORAGE_CONCLUSION))
      || _readText(map.get(LEGACY_OVERALL_CONCLUSION))

    if (!sampleMeta.value.populationManual) {
      const mv = extractI6PeriodMovement(map.get(I62_ROWS))
      if (mv.debitTotal > 0) sampleMeta.value.populationAmount = mv.debitTotal
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
      m.get(I62_ROWS),
      m.get(LEGACY_COMPLETE_PROJECT),
      m.get(LEGACY_SUPER_DEDUCTION_ROWS),
      m.get(LEGACY_OVERALL_CONCLUSION),
    ]
  }, () => load(), { immediate: true, deep: false })

  const linkedPeriod: ComputedRef<{
    debitTotal: number
    creditTotal: number
    originalTotal: number
    source: string
  }> = computed(() => {
    const mv = extractI6PeriodMovement(getMap().get(I62_ROWS))
    return mv.debitTotal > 0 ? mv : { debitTotal: 0, creditTotal: 0, originalTotal: 0, source: '' }
  })

  const summary: ComputedRef<I6TargetedSummary> = computed(() =>
    summarizeI6Targeted(
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
    buildI6CoverageFooter(summary.value, sampleMeta.value.populationCreditAmount),
  )

  const coverageTagType = computed(() => {
    if (summary.value.coverageRate == null) return 'info'
    if (coverageLow.value) return 'danger'
    return 'success'
  })

  const adjDrafts = computed(() => buildI6TargetedAdjDrafts(rows.value))
  const pushableAdjDrafts = computed(() =>
    adjDrafts.value.filter((d) => d.draftKind !== 'doc_only' && d.amount > 0.005),
  )
  const i62ProjectCatalog = computed(() => extractI62ProjectCatalog(getMap().get(I62_ROWS)))
  const i62ProjectNames = computed(() => i62ProjectCatalog.value.map((p) => p.projectName))
  const projectConsistency = computed(() =>
    analyzeI62ProjectConsistency(rows.value, i62ProjectCatalog.value),
  )

  function addRow(partial?: Partial<I6TargetedCheckRow>) {
    rows.value.push(emptyI6TargetedRow(partial))
  }

  function removeRow(rowId: string) {
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
  }

  function updateRow(rowId: string, field: keyof I6TargetedCheckRow, value: string | number | boolean) {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    if (field === 'selectionReason') {
      row.isSpecific = !!String(value || '')
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
    const catalog = i62ProjectCatalog.value
    const existing = new Set(
      rows.value.map((r) => `${r.voucherDate}|${r.voucherNo}`).filter((k) => k !== '|'),
    )
    let n = 0
    for (const s of samples) {
      const mapped = mapSampledToI6TargetedRow(s, catalog)
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

  function linkProjectsFromI62(overwrite = false): { ok: boolean; linked: number; message: string } {
    const catalog = i62ProjectCatalog.value
    if (!catalog.length) return { ok: false, linked: 0, message: 'I6-2 无研发项目可挂接，请先编制明细表' }
    const { rows: next, linked } = enrichRowsWithI62Projects(rows.value, catalog, overwrite)
    rows.value = next
    return {
      ok: linked > 0,
      linked,
      message: linked > 0
        ? `已挂接 ${linked} 行研发项目（来自 I6-2）`
        : '没有可挂接的空项目名（或摘要无法匹配）',
    }
  }

  function setPopulationAmount(amount: number, manual: boolean) {
    sampleMeta.value.populationAmount = amount
    sampleMeta.value.populationManual = manual
  }

  function syncPopulationFromI62(): { ok: boolean; message: string } {
    const mv = linkedPeriod.value
    if (!(mv.debitTotal > 0)) {
      return { ok: false, message: 'I6-2 无本期审定合计可带入，请先编制明细表' }
    }
    setPopulationAmount(mv.debitTotal, false)
    sampleMeta.value.populationDesc = 'I6-2 本期审定合计（=明细表 Q 列合计，对齐 Excel G32）'
    return {
      ok: true,
      message: `已带入本期发生额 ${mv.debitTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`,
    }
  }

  function appendAdjDraftsToNote(): { ok: boolean; message: string; count: number } {
    const drafts = adjDrafts.value
    if (!drafts.length) return { ok: false, count: 0, message: '无核对×可生成调整草稿' }
    const block = drafts.map((d, i) =>
      `${i + 1}. ${d.suggestedNote}\n   ${d.suggestedEntry}`,
    ).join('\n')
    auditNote.value = auditNote.value
      ? `${auditNote.value.trim()}\n\n【I6-4 调整建议草稿】\n${block}`
      : `【I6-4 调整建议草稿】\n${block}`
    return { ok: true, count: drafts.length, message: `已写入 ${drafts.length} 条调整建议到审计说明` }
  }

  /**
   * 将可推送的核对×草稿写入 I6-3-rows（按 description+科目+借贷方向去重）
   */
  async function pushAdjDraftsToI63(): Promise<{ ok: boolean; added: number; message: string }> {
    const pushable = pushableAdjDrafts.value
    if (!pushable.length) {
      return { ok: false, added: 0, message: '无资本化/跨期类核对×可推送（资料类请先补证据）' }
    }
    const lines = buildI63LinesFromTargetedDrafts(pushable)
    if (!lines.length) return { ok: false, added: 0, message: '草稿金额无效，未生成分录' }

    const existing = parseI63Rows(getMap().get(I63_ROWS_KEY))
    const { merged, added } = mergeI63LinesSkippingExisting(existing, lines)
    if (!added) {
      return { ok: false, added: 0, message: '同说明分录已存在于 I6-3，未重复写入' }
    }
    const payload = JSON.stringify(merged)
    if (options?.onSave) {
      await options.onSave(I63_ROWS_KEY, payload)
    }
    try {
      getMap().set(I63_ROWS_KEY, { item_id: I63_ROWS_KEY, conclusion: null, remark: payload })
    } catch { /* ignore */ }

    const stamp = new Date().toISOString().slice(0, 19).replace('T', ' ')
    const kinds = [...new Set(pushable.map((d) => d.draftKind))].join('、')
    const pushBlock = `【已推送 I6-3 @ ${stamp}】${added} 行（${kinds}）`
    if (!auditNote.value.includes('【已推送 I6-3')) {
      auditNote.value = auditNote.value
        ? `${auditNote.value.trim()}\n\n${pushBlock}`
        : pushBlock
    } else {
      auditNote.value = auditNote.value.replace(
        /【已推送 I6-3[^\n]*/,
        pushBlock,
      )
    }
    if (options?.onSave) await options.onSave(STORAGE_NOTE, auditNote.value)

    try {
      window.dispatchEvent(new CustomEvent('i6:adjustment-writeback', {
        detail: {
          source: 'I6-4',
          rows: merged,
          entries: merged,
        },
      }))
    } catch { /* ignore */ }

    return {
      ok: true,
      added,
      message: `已推送 ${added} 行至 I6-3（资本化/跨期草稿，请打开调整分录复核借贷平衡）`,
    }
  }

  function fillConclusionDraft() {
    auditConclusion.value = buildI6TargetedConclusionDraft({
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
    i62ProjectNames,
    projectConsistency,
    addRow,
    removeRow,
    updateRow,
    fillFromSampledVouchers,
    linkProjectsFromI62,
    setPopulationAmount,
    syncPopulationFromI62,
    syncSpecificAmount,
    appendAdjDraftsToNote,
    pushAdjDraftsToI63,
    fillConclusionDraft,
    persistAll,
    saveNote,
    saveConclusion,
    saveRiskFocus,
    load,
  }
}

export default useI6TargetedCheck
