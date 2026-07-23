/**
 * useI4TargetedCheck — I4-5 长期待摊费用针对性检查表
 * 样本选取 + 凭证核对 1~5 + 检查比例（可联动 I4-2 本期发生额）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  type I4TargetedCheckRow,
  type I4TargetedSampleMeta,
  type I4TargetedRiskFocus,
  type I4TargetedSummary,
  emptyI4TargetedRow,
  emptyI4TargetedSampleMeta,
  emptyI4TargetedRiskFocus,
  normalizeI4TargetedRow,
  normalizeI4TargetedSampleMeta,
  normalizeI4TargetedRiskFocus,
  summarizeI4Targeted,
  extractI4PeriodMovement,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  buildI4CoverageFooter,
  buildI4TargetedConclusionDraft,
  buildI4TargetedAdjDrafts,
  buildI4CoverageExpansionAdvice,
  buildI4CreditCoverageExpansionAdvice,
  isCoverageNoteSatisfied,
  checkI4SpecificAmountConsistency,
  buildI4SamplingPresetFromTestReasons,
  applyI4SelectionReasonsToSamples,
  crossCheckI45WithI44,
  buildI44CrossNoteBlock,
  parseI44PolicySnapshot,
  mapSampledToI4TargetedRow,
  suggestAbnormalFromFailedChecks,
  syncSpecificAmountFromRows,
  extractI42ProjectCatalog,
  enrichRowsWithI42Projects,
  buildI43LinesFromTargetedDrafts,
  mergeI43LinesSkippingExisting,
  isAbnormalFlag,
  hasFailedCheck,
  I4_5_DEFAULT_COVERAGE_THRESHOLD,
} from './i4TargetedCheckModel'

export {
  type I4TargetedCheckRow,
  type I4TargetedSampleMeta,
  type I4TargetedRiskFocus,
  type I4TargetedSummary,
  type I4TargetedAdjDraft,
  type I4CoverageFooter,
  type I4CoverageExpansionAdvice,
  type I4SpecificAmountCheck,
  type I4SamplingPreset,
  type I45I44CrossResult,
  type I42ProjectRef,
  emptyI4TargetedRow,
  I4_5_DEFAULT_COVERAGE_THRESHOLD,
  I4_5_TEST_CONTENT,
  I4_5_TEST_REASONS,
  I4_5_SAMPLE_METHODS,
  I4_5_CHECK_OPTIONS,
  I4_5_ABNORMAL_OPTIONS,
  I4_5_OBJECTIVES,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  buildI4CoverageFooter,
  buildI4CoverageExpansionAdvice,
  buildI4CreditCoverageExpansionAdvice,
  isCoverageNoteSatisfied,
  checkI4SpecificAmountConsistency,
  buildI4SamplingPresetFromTestReasons,
  applyI4SelectionReasonsToSamples,
  crossCheckI45WithI44,
  buildI44CrossNoteBlock,
  parseI44PolicySnapshot,
  suggestAbnormalFromFailedChecks,
  syncSpecificAmountFromRows,
  extractI42ProjectCatalog,
  enrichRowsWithI42Projects,
  matchI42ProjectName,
  buildI43LinesFromTargetedDrafts,
  mergeI43LinesSkippingExisting,
  isAbnormalFlag,
  hasFailedCheck,
  buildI4TargetedConclusionDraft,
  buildI4TargetedAdjDrafts,
  mapSampledToI4TargetedRow,
} from './i4TargetedCheckModel'

const STORAGE_ROWS = 'I4-5-rows'
const STORAGE_SAMPLE = 'I4-5-sample-meta'
const STORAGE_RISK = 'I4-5-risk-focus'
const STORAGE_NOTE = 'I4-5-audit-note'
const STORAGE_CONCLUSION = 'I4-5-audit-conclusion'
const I42_ROWS = 'I4-2-rows'

// 旧段落型分散 key（Task 4.6 遗留）—— load() 时一次性迁入 I4-5-risk-focus，勿再写入。
// LEGACY keys: I4-5-major-addition(-conclusion) / benefit-change(-conclusion) / early-termination(-conclusion) / conclusion
const LEGACY_MAJOR_ADDITION = 'I4-5-major-addition'
const LEGACY_MAJOR_ADDITION_CONCLUSION = 'I4-5-major-addition-conclusion'
const LEGACY_BENEFIT_CHANGE = 'I4-5-benefit-change'
const LEGACY_BENEFIT_CHANGE_CONCLUSION = 'I4-5-benefit-change-conclusion'
const LEGACY_EARLY_TERMINATION = 'I4-5-early-termination'
const LEGACY_EARLY_TERMINATION_CONCLUSION = 'I4-5-early-termination-conclusion'
const LEGACY_OVERALL_CONCLUSION = 'I4-5-conclusion'

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

export function useI4TargetedCheck(
  allResponses: Ref<Map<string, any>> | (() => Map<string, any>),
  options?: {
    /** I4 父组件契约：逐 item_id 持久化 */
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

  const rows = ref<I4TargetedCheckRow[]>([])
  const sampleMeta = ref<I4TargetedSampleMeta>(emptyI4TargetedSampleMeta())
  const riskFocus = ref<I4TargetedRiskFocus>(emptyI4TargetedRiskFocus())
  const auditNote = ref('')
  const auditConclusion = ref('')

  function load() {
    const map = getMap()
    rows.value = _safeParseArray(map.get(STORAGE_ROWS)).map(normalizeI4TargetedRow)

    sampleMeta.value = normalizeI4TargetedSampleMeta(_parseObject(map.get(STORAGE_SAMPLE)))

    const riskRaw = _parseObject(map.get(STORAGE_RISK)) || _legacyRiskFocusRaw(map)
    riskFocus.value = normalizeI4TargetedRiskFocus(riskRaw)

    auditNote.value = _readText(map.get(STORAGE_NOTE))
    auditConclusion.value = _readText(map.get(STORAGE_CONCLUSION))
      || _readText(map.get(LEGACY_OVERALL_CONCLUSION))

    if (!sampleMeta.value.populationManual) {
      const mv = extractI4PeriodMovement(map.get(I42_ROWS), getYear())
      if (mv.debitTotal > 0) sampleMeta.value.populationAmount = mv.debitTotal
      if (mv.creditTotal > 0) sampleMeta.value.populationCreditAmount = mv.creditTotal
    }
  }

  /** 旧段落型 6 个分散 key 拼装为 riskFocus 迁移对象（无新 STORAGE_RISK 时兜底） */
  function _legacyRiskFocusRaw(map: Map<string, any>): any {
    const majorAddition = _readText(map.get(LEGACY_MAJOR_ADDITION))
    const benefitChange = _readText(map.get(LEGACY_BENEFIT_CHANGE))
    const earlyTermination = _readText(map.get(LEGACY_EARLY_TERMINATION))
    const majorAdditionConclusion = _readText(map.get(LEGACY_MAJOR_ADDITION_CONCLUSION))
    const benefitChangeConclusion = _readText(map.get(LEGACY_BENEFIT_CHANGE_CONCLUSION))
    const earlyTerminationConclusion = _readText(map.get(LEGACY_EARLY_TERMINATION_CONCLUSION))
    if (!majorAddition && !benefitChange && !earlyTermination
      && !majorAdditionConclusion && !benefitChangeConclusion && !earlyTerminationConclusion) {
      return null
    }
    return {
      majorAddition,
      benefitChange,
      earlyTermination,
      majorAdditionConclusion,
      benefitChangeConclusion,
      earlyTerminationConclusion,
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
      m.get(I42_ROWS),
      m.get(LEGACY_MAJOR_ADDITION),
      m.get(LEGACY_BENEFIT_CHANGE),
      m.get(LEGACY_EARLY_TERMINATION),
      m.get(LEGACY_OVERALL_CONCLUSION),
    ]
  }, () => load(), { immediate: true, deep: false })

  const linkedPeriod: ComputedRef<{
    debitTotal: number
    creditTotal: number
    originalTotal: number
    source: string
  }> = computed(() => {
    const mv = extractI4PeriodMovement(getMap().get(I42_ROWS), getYear())
    return mv.debitTotal > 0 || mv.creditTotal > 0 || mv.originalTotal > 0
      ? mv
      : { debitTotal: 0, creditTotal: 0, originalTotal: 0, source: '' }
  })

  const summary: ComputedRef<I4TargetedSummary> = computed(() =>
    summarizeI4Targeted(
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

  const creditCoverageLow = computed(() =>
    summary.value.creditCoverageRate != null
    && summary.value.creditCoverageRate < sampleMeta.value.coverageThreshold
    && sampleMeta.value.populationCreditAmount > 0,
  )

  /** 借方检查比例偏低 → 强制扩样建议 */
  const expansionAdvice = computed(() =>
    buildI4CoverageExpansionAdvice(summary.value, sampleMeta.value.coverageThreshold),
  )

  /** 贷方检查比例偏低 → 对称扩样建议 */
  const creditExpansionAdvice = computed(() => {
    const creditRowCount = rows.value.filter((r) => Number(r.creditAmount) > 0).length
    return buildI4CreditCoverageExpansionAdvice(
      summary.value,
      sampleMeta.value.populationCreditAmount,
      sampleMeta.value.coverageThreshold,
      creditRowCount,
    )
  })

  const coverageNoteOk = computed(() =>
    isCoverageNoteSatisfied(auditNote.value, expansionAdvice.value, creditExpansionAdvice.value),
  )

  /** 第二节特定样本金额 vs 表内特定借方 */
  const specificAmountCheck = computed(() =>
    checkI4SpecificAmountConsistency(
      sampleMeta.value.specificAmount,
      summary.value.specificDebitTotal,
    ),
  )

  /** 测试原因 → 抽凭引擎预填 */
  const samplingPreset = computed(() =>
    buildI4SamplingPresetFromTestReasons(sampleMeta.value.testReasons),
  )

  /** I4-4 摊销政策交叉印证 */
  const i44Cross = computed(() =>
    crossCheckI45WithI44({
      rows: rows.value,
      testReasons: sampleMeta.value.testReasons,
      riskFocus: riskFocus.value,
      i44: parseI44PolicySnapshot(getMap()),
    }),
  )

  const coverageLabel = computed(() => formatLayeredCoverageLabel(summary.value))
  const creditCoverageLabel = computed(() => formatCoverageLabel(summary.value.creditCoverageRate))

  /** Excel 表尾：合计 / 本期发生额 / 检查比例 */
  const coverageFooter = computed(() =>
    buildI4CoverageFooter(summary.value, sampleMeta.value.populationCreditAmount),
  )

  const coverageTagType = computed(() => {
    if (summary.value.coverageRate == null) return 'info'
    if (coverageLow.value) return 'danger'
    return 'success'
  })

  const adjDrafts = computed(() => buildI4TargetedAdjDrafts(rows.value))

  /** I4-2 项目名目录（抽凭挂接 / 下拉） */
  const i42ProjectCatalog = computed(() => extractI42ProjectCatalog(getMap().get(I42_ROWS)))
  const i42ProjectNames = computed(() => i42ProjectCatalog.value.map((p) => p.projectName))

  const pushableAdjDrafts = computed(() =>
    adjDrafts.value.filter((d) => d.draftKind !== 'doc_only' && d.amount > 0.005),
  )

  function addRow(partial?: Partial<I4TargetedCheckRow>) {
    rows.value.push(emptyI4TargetedRow(partial))
  }

  function removeRow(rowId: string) {
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
  }

  function updateRow(rowId: string, field: keyof I4TargetedCheckRow, value: string | number | boolean) {
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
    const catalog = i42ProjectCatalog.value
    const existing = new Set(
      rows.value.map((r) => `${r.voucherDate}|${r.voucherNo}`).filter((k) => k !== '|'),
    )
    const mappedBatch: Array<ReturnType<typeof mapSampledToI4TargetedRow> & {
      isHighValue?: boolean
      summary?: string
    }> = []
    for (const s of samples) {
      const mapped = mapSampledToI4TargetedRow(s, catalog)
      const key = `${mapped.voucherDate}|${mapped.voucherNo}`
      if (key !== '|' && existing.has(key)) continue
      // 允许测试原因高值规则覆盖引擎默认的「高值必选」
      if (mapped.selectionReason === '高值必选') mapped.selectionReason = ''
      mappedBatch.push({
        ...mapped,
        isHighValue: !!s.isHighValue,
        summary: mapped.businessDesc || s.summary || '',
      })
      if (key !== '|') existing.add(key)
    }
    applyI4SelectionReasonsToSamples(mappedBatch, sampleMeta.value.testReasons)
    for (const mapped of mappedBatch) {
      if (!mapped.selectionReason && mapped.isHighValue) mapped.selectionReason = '高值必选'
      if (mapped.selectionReason) mapped.isSpecific = true
      const { isHighValue: _hv, summary: _sum, ...row } = mapped as any
      rows.value.push(row)
    }
    const n = mappedBatch.length
    if (n > 0 && !sampleMeta.value.sampleSize) {
      sampleMeta.value.sampleSize = rows.value.length
    }
    return n
  }

  /** 为空项目名按摘要模糊挂接 I4-2 */
  function linkProjectsFromI42(overwrite = false): { ok: boolean; linked: number; message: string } {
    const catalog = i42ProjectCatalog.value
    if (!catalog.length) return { ok: false, linked: 0, message: 'I4-2 无项目可挂接，请先编制明细表' }
    const { rows: next, linked } = enrichRowsWithI42Projects(rows.value, catalog, overwrite)
    rows.value = next
    return {
      ok: linked > 0,
      linked,
      message: linked > 0
        ? `已挂接 ${linked} 行项目名（来自 I4-2）`
        : '没有可挂接的空项目名（或摘要无法匹配）',
    }
  }

  /**
   * 将可推送的核对×草稿写入 I4-3-rows（按 description 去重）
   * 成功后在审计说明追加【已推送 I4-3】时间戳，便于追溯。
   */
  async function pushAdjDraftsToI43(): Promise<{ ok: boolean; added: number; message: string }> {
    const pushable = pushableAdjDrafts.value
    if (!pushable.length) {
      return { ok: false, added: 0, message: '无资本化/跨期类核对×可推送（资料类请先补证据）' }
    }
    const lines = buildI43LinesFromTargetedDrafts(pushable)
    if (!lines.length) return { ok: false, added: 0, message: '草稿金额无效，未生成分录' }

    const existing = _safeParseArray(getMap().get('I4-3-rows'))
    const { merged, added } = mergeI43LinesSkippingExisting(existing, lines)
    if (!added) {
      return { ok: false, added: 0, message: '同说明分录已存在于 I4-3，未重复写入' }
    }
    if (options?.onSave) {
      await options.onSave('I4-3-rows', JSON.stringify(merged))
    }
    try {
      getMap().set('I4-3-rows', { item_id: 'I4-3-rows', conclusion: null, remark: JSON.stringify(merged) })
    } catch { /* ignore */ }

    const stamp = new Date().toISOString().slice(0, 19).replace('T', ' ')
    const kinds = [...new Set(pushable.map((d) => d.draftKind))].join('、')
    const pushBlock = `【已推送 I4-3 @ ${stamp}】${added} 行（${kinds}）`
    if (!auditNote.value.includes('【已推送 I4-3')) {
      auditNote.value = auditNote.value
        ? `${auditNote.value.trim()}\n\n${pushBlock}`
        : pushBlock
    } else {
      auditNote.value = auditNote.value.replace(
        /【已推送 I4-3[^\n]*/,
        pushBlock,
      )
    }
    if (options?.onSave) await options.onSave(STORAGE_NOTE, auditNote.value)

    return {
      ok: true,
      added,
      message: `已推送 ${added} 行至 I4-3（费用化/跨期草稿，请打开调整分录复核）`,
    }
  }

  function setPopulationAmount(amount: number, manual: boolean) {
    sampleMeta.value.populationAmount = amount
    sampleMeta.value.populationManual = manual
  }

  function syncPopulationFromI42(mode: 'period' | 'original' = 'period'): { ok: boolean; message: string } {
    const mv = linkedPeriod.value
    if (mode === 'original') {
      if (!(mv.originalTotal > 0)) return { ok: false, message: 'I4-2 无原始金额合计可带入' }
      setPopulationAmount(mv.originalTotal, false)
      sampleMeta.value.populationCreditAmount = mv.creditTotal
      sampleMeta.value.populationDesc = 'I4-2 原始金额合计（存在性测试总体）'
      return {
        ok: true,
        message: `已带入原始金额合计 ${mv.originalTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`,
      }
    }
    if (!(mv.debitTotal > 0) && !(mv.creditTotal > 0)) {
      return { ok: false, message: 'I4-2 无本期发生额可带入（可改用「带入原始金额合计」）' }
    }
    if (mv.debitTotal > 0) setPopulationAmount(mv.debitTotal, false)
    sampleMeta.value.populationCreditAmount = mv.creditTotal
    sampleMeta.value.populationDesc = 'I4-2 本期借方发生额代理（当期新增长期待摊费用）'
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
      ? `${auditNote.value.trim()}\n\n【I4-5 调整建议草稿】\n${block}`
      : `【I4-5 调整建议草稿】\n${block}`
    return { ok: true, count: drafts.length, message: `已写入 ${drafts.length} 条调整建议到审计说明` }
  }

  /** 将借/贷扩样建议模板写入审计说明（满足保存闸门） */
  function appendExpansionAdviceToNote(): { ok: boolean; message: string } {
    const debit = expansionAdvice.value
    const credit = creditExpansionAdvice.value
    if (!debit.needed && !credit.needed) {
      return { ok: false, message: '借/贷检查比例均已达标，无需扩样说明' }
    }
    const blocks: string[] = []
    if (debit.needed && !auditNote.value.includes('【检查比例偏低—扩样说明】')) {
      blocks.push(debit.noteTemplate)
    }
    if (credit.needed && !auditNote.value.includes('【贷方检查比例偏低—扩样说明】')) {
      blocks.push(credit.noteTemplate)
    }
    if (!blocks.length) {
      return { ok: true, message: '审计说明中已有扩样说明模板' }
    }
    const joined = blocks.join('\n\n')
    auditNote.value = auditNote.value
      ? `${auditNote.value.trim()}\n\n${joined}`
      : joined
    return { ok: true, message: '已写入扩样说明模板，请勾选拟采取的措施或补充理由' }
  }

  /** 将 I4-4 交叉印证结果写入审计说明 */
  function appendI44CrossToNote(): { ok: boolean; message: string } {
    const block = buildI44CrossNoteBlock(i44Cross.value)
    if (auditNote.value.includes('【I4-5×I4-4 交叉印证】')) {
      // 替换旧块
      auditNote.value = auditNote.value.replace(
        /【I4-5×I4-4 交叉印证】[\s\S]*?(?=\n【|$)/,
        `${block}\n`,
      ).trim()
    } else {
      auditNote.value = auditNote.value
        ? `${auditNote.value.trim()}\n\n${block}`
        : block
    }
    return {
      ok: true,
      message: i44Cross.value.hasWarning
        ? `已写入交叉印证（含 ${i44Cross.value.findings.filter((f) => f.severity === 'warning').length} 条待跟进）`
        : '已写入交叉印证结果',
    }
  }

  function fillConclusionDraft() {
    auditConclusion.value = buildI4TargetedConclusionDraft({
      sampleCount: summary.value.sampleCount,
      coverageLabel: coverageLabel.value,
      creditCoverageLabel: creditCoverageLabel.value,
      anomalyCount: summary.value.anomalyCount,
      failCheckCount: summary.value.failCheckCount,
      testReasons: sampleMeta.value.testReasons,
      riskFocus: riskFocus.value,
      expansionAdvice: expansionAdvice.value,
      creditExpansionAdvice: creditExpansionAdvice.value,
      i44CrossSummary: i44Cross.value.empty ? undefined : i44Cross.value.summaryText,
    })
  }

  /**
   * 保存闸门：
   * - 借/贷覆盖率偏低且说明未回应扩样 → 阻断
   * - 特定样本金额与表内不一致 → 警告
   * - I4-4 交叉有 warning 且说明未含交叉印证 → 仅警告（由 UI 提示，不硬阻断以免卡死）
   */
  function canPersist(): { ok: boolean; message: string; level: 'ok' | 'block' | 'warn' } {
    if ((expansionAdvice.value.needed || creditExpansionAdvice.value.needed) && !coverageNoteOk.value) {
      return {
        ok: false,
        level: 'block',
        message: '借/贷检查比例偏低：请先扩样，或点击「写入扩样说明」并在审计说明中回应后再保存',
      }
    }
    if (specificAmountCheck.value.severity === 'warning' && !specificAmountCheck.value.ok) {
      return {
        ok: false,
        level: 'block',
        message: `${specificAmountCheck.value.message} 请先「从表内特定样本同步」或修正第二节金额后再保存`,
      }
    }
    if (i44Cross.value.hasWarning && !auditNote.value.includes('【I4-5×I4-4 交叉印证】')) {
      return {
        ok: true,
        level: 'warn',
        message: '与 I4-4 存在待跟进交叉印证项，尚未写入说明。仍要保存吗？可先点「写入交叉印证到说明」。',
      }
    }
    return { ok: true, level: 'ok', message: '' }
  }

  async function persistAll(opts?: { skipGate?: boolean }): Promise<{ ok: boolean; message: string; level: 'ok' | 'block' | 'warn' }> {
    const gate = canPersist()
    if (!opts?.skipGate && gate.level === 'block') return gate
    if (!options?.onSave) return gate
    if (!sampleMeta.value.sampleSize && rows.value.length) {
      sampleMeta.value.sampleSize = rows.value.length
    }
    await options.onSave(STORAGE_ROWS, JSON.stringify(rows.value))
    await options.onSave(STORAGE_SAMPLE, JSON.stringify(sampleMeta.value))
    await options.onSave(STORAGE_RISK, JSON.stringify(riskFocus.value))
    await options.onSave(STORAGE_NOTE, auditNote.value)
    await options.onSave(STORAGE_CONCLUSION, auditConclusion.value)
    return opts?.skipGate ? { ok: true, level: 'ok', message: '' } : gate
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
    creditCoverageLow,
    expansionAdvice,
    creditExpansionAdvice,
    coverageNoteOk,
    specificAmountCheck,
    samplingPreset,
    i44Cross,
    coverageLabel,
    creditCoverageLabel,
    coverageFooter,
    coverageTagType,
    linkedPeriod,
    adjDrafts,
    pushableAdjDrafts,
    i42ProjectCatalog,
    i42ProjectNames,
    addRow,
    removeRow,
    updateRow,
    fillFromSampledVouchers,
    linkProjectsFromI42,
    pushAdjDraftsToI43,
    setPopulationAmount,
    syncPopulationFromI42,
    syncSpecificAmount,
    appendAdjDraftsToNote,
    appendExpansionAdviceToNote,
    appendI44CrossToNote,
    fillConclusionDraft,
    canPersist,
    persistAll,
    saveNote,
    saveConclusion,
    saveRiskFocus,
    load,
  }
}

export default useI4TargetedCheck
