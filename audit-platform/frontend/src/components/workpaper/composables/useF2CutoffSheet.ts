/**
 * useF2CutoffSheet — F2-29~F2-32 截止测试通用逻辑
 * （四象限 + 细判 + 分类编制 + 监盘种子）
 */
import { ref, computed, watch, type Ref } from 'vue'
import { calcSubtotal } from './useF2InvMaiFormulaEngine'
import { assessCutoffRow, type CutoffEvidenceGap, type CutoffTimingKind } from './f2CutoffJudgment'
import { readRowJson, type ChecklistResponse } from './useF2FormData'
import type { F2CutoffSheetConfig } from '../f2/inspection/f2CutoffSheetConfigs'
import type { ExtractedVoucher, FillMode } from './useCutoffAutoSampling'
import { buildCutoffCrossHints, readStocktakeMetaSeed } from './useF2CutoffCrossSheet'

export interface F2CutoffRow {
  id: string
  seq: number
  invCategory: 'raw' | 'finished' | ''
  party: string
  voucherNo: string
  bookDate: string
  businessContent: string
  itemName: string
  quantity: number
  amount: number
  /** 单据金额（可选，用于勾稽） */
  docAmount: number
  docNo: string
  docDate: string
  inspectNo: string
  inspectDate: string
  otherDocNo: string
  otherDocDate: string
  isCrossPeriod: boolean
  isCorrect: boolean
  isCorrectOverride: boolean | null
  autoCorrect: boolean
  timingKind: CutoffTimingKind
  evidenceGap: CutoffEvidenceGap
  suggestion: string
  remark: string
  source?: string
  correctPeriod?: string
  bookedPeriod?: string
}

function dataKey(sheetCode: string): string {
  return `${sheetCode}-rows`
}

function conclusionKey(sheetCode: string): string {
  return `${sheetCode}-conclusion`
}

function metaKey(sheetCode: string): string {
  return `${sheetCode}-meta`
}

function emptyRow(id: string, seq: number): F2CutoffRow {
  return {
    id,
    seq,
    invCategory: '',
    party: '',
    voucherNo: '',
    bookDate: '',
    businessContent: '',
    itemName: '',
    quantity: 0,
    amount: 0,
    docAmount: 0,
    docNo: '',
    docDate: '',
    inspectNo: '',
    inspectDate: '',
    otherDocNo: '',
    otherDocDate: '',
    isCrossPeriod: false,
    isCorrect: true,
    isCorrectOverride: null,
    autoCorrect: true,
    timingKind: 'incomplete',
    evidenceGap: '',
    suggestion: '',
    remark: '',
  }
}

function genRowId(): string {
  return `f2ct-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

function loadRows(map: Map<string, ChecklistResponse>, sheetCode: string): F2CutoffRow[] {
  const raw = readRowJson(map.get(dataKey(sheetCode)))
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw) as Partial<F2CutoffRow>[]
    if (!parsed.length) return []
    return parsed.map((r) => {
      const base = emptyRow(r.id || genRowId(), r.seq || 1)
      const merged = { ...base, ...r }
      if (!merged.businessContent && (r as { summary?: string }).summary) {
        merged.businessContent = String((r as { summary?: string }).summary)
      }
      return {
        ...merged,
        isCorrectOverride: r.isCorrectOverride ?? null,
        autoCorrect: r.autoCorrect ?? (r.isCorrect ?? true),
        docAmount: Number(r.docAmount || 0) || 0,
        inspectNo: r.inspectNo || '',
        inspectDate: r.inspectDate || '',
        otherDocNo: r.otherDocNo || '',
        otherDocDate: r.otherDocDate || '',
        businessContent: merged.businessContent || '',
        invCategory: (r.invCategory as F2CutoffRow['invCategory']) || '',
        timingKind: (r.timingKind as CutoffTimingKind) || 'incomplete',
        evidenceGap: (r.evidenceGap as CutoffEvidenceGap) || '',
      }
    }) as F2CutoffRow[]
  } catch {
    return []
  }
}

function mapVoucherToRow(v: ExtractedVoucher, seq: number, invCategory: F2CutoffRow['invCategory']): F2CutoffRow {
  const debit = v.debitAmount ? parseFloat(v.debitAmount) : 0
  const credit = v.creditAmount ? parseFloat(v.creditAmount) : 0
  const amount = debit > 0 ? debit : credit
  const isCross = v.cutoffStatus === '可能跨期'
  return {
    ...emptyRow(genRowId(), seq),
    invCategory,
    party: v.accountName || v.counterpartAccount || '',
    voucherNo: v.voucherNo || '',
    bookDate: v.voucherDate || '',
    businessContent: v.summary || '',
    itemName: v.summary || '',
    amount,
    docDate: '',
    isCrossPeriod: isCross,
    isCorrect: !isCross,
    autoCorrect: !isCross,
    suggestion: isCross ? '可能跨期，请补全单据日期并核查' : '请补全入库/出库单号与日期',
    evidenceGap: 'missing_doc',
    timingKind: 'incomplete',
    remark: v.remark || '',
    source: '自动提取',
  }
}

function segmentKeyDate(r: F2CutoffRow, preferDoc: boolean): string {
  return preferDoc ? (r.docDate || r.bookDate) : (r.bookDate || r.docDate)
}

export function useF2CutoffSheet(opts: {
  config: Ref<F2CutoffSheetConfig>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly: Ref<boolean>
  periodEnd?: Ref<string>
}) {
  const sheetCode = computed(() => opts.config.value.sheetCode)
  const periodEndDate = computed(() => opts.periodEnd?.value || '')

  const meta = ref<Record<string, string>>({
    entityName: '',
    cutoffDate: '',
    sampleDaysBefore: '5',
    sampleDaysAfter: '5',
    amountThreshold: '',
    processNote: '',
    /** 编制焦点：''=分类双段展示 | raw | finished */
    invCategory: '',
    /** 抽样策略：primary=主窗(按追查方向) | symmetric=前后对称 */
    sampleWindowMode: 'primary',
  })

  const effectiveCutoff = computed(() => meta.value.cutoffDate || periodEndDate.value || '')

  function enrichCutoffRow(r: F2CutoffRow): F2CutoffRow {
    const pe = effectiveCutoff.value
    const judge = assessCutoffRow({
      docDate: r.docDate,
      bookDate: r.bookDate,
      periodEnd: pe,
      voucherNo: r.voucherNo,
      docNo: r.docNo,
      amount: r.amount,
      docAmount: r.docAmount,
      overrideCorrect: r.isCorrectOverride,
    })
    const hasDates = !!(r.docDate && r.bookDate && pe)
    const autoOk = hasDates ? judge.timing === 'ok' && !judge.evidenceGap : !judge.evidenceGap
    return {
      ...r,
      autoCorrect: autoOk,
      isCorrect: judge.isCorrect,
      isCrossPeriod: judge.isCrossPeriod,
      timingKind: judge.timing,
      evidenceGap: judge.evidenceGap,
      suggestion: judge.suggestion || r.suggestion,
    }
  }

  const rows = ref<F2CutoffRow[]>(
    loadRows(opts.allResponses.value, sheetCode.value).map(enrichCutoffRow),
  )
  const cutoffConclusion = ref('')
  /** 首屏 hydrate 期间禁止写库，避免打开底稿就触发保存/回声重载 */
  let hydrateDepth = 0
  const isHydrating = () => hydrateDepth > 0
  function beginHydrate(): void { hydrateDepth += 1 }
  function endHydrate(): void { hydrateDepth = Math.max(0, hydrateDepth - 1) }

  function applyStocktakeSeed(): void {
    const seed = readStocktakeMetaSeed(opts.allResponses.value)
    const patch: Record<string, string> = {}
    if (seed.entityName && !meta.value.entityName) patch.entityName = seed.entityName
    if (seed.bsDate && !meta.value.cutoffDate) patch.cutoffDate = seed.bsDate
    if (Object.keys(patch).length) {
      meta.value = { ...meta.value, ...patch }
      if (!opts.isReadonly.value && !isHydrating()) persistMeta()
    }
  }

  function loadMeta(): void {
    const raw = opts.allResponses.value.get(metaKey(sheetCode.value))?.remark
    if (!raw) {
      if (periodEndDate.value && !meta.value.cutoffDate) {
        meta.value = { ...meta.value, cutoffDate: periodEndDate.value }
      }
      applyStocktakeSeed()
      return
    }
    try {
      const parsed = JSON.parse(raw) as Record<string, string>
      meta.value = { ...meta.value, ...parsed }
    } catch { /* ignore */ }
    applyStocktakeSeed()
  }

  watch(
    () => opts.allResponses.value.get(conclusionKey(sheetCode.value))?.remark,
    (v) => { cutoffConclusion.value = v || '' },
    { immediate: true },
  )
  watch(
    () => opts.allResponses.value.get(metaKey(sheetCode.value))?.remark,
    () => {
      beginHydrate()
      try { loadMeta() } finally { endHydrate() }
    },
    { immediate: true },
  )
  watch(periodEndDate, (d) => {
    if (d && !meta.value.cutoffDate) {
      meta.value = { ...meta.value, cutoffDate: d }
      if (!isHydrating()) persistMeta()
    }
  })

  watch(effectiveCutoff, () => {
    if (isHydrating()) return
    rows.value = rows.value.map(enrichCutoffRow)
  })

  function matchCategory(r: F2CutoffRow): boolean {
    const cat = meta.value.invCategory
    if (!cat) return true
    return r.invCategory === cat
  }

  const visibleRows = computed(() => rows.value.filter(matchCategory))

  const crossHints = computed(() =>
    buildCutoffCrossHints(rows.value, opts.allResponses.value),
  )

  const cutoffSummary = computed(() => {
    const list = visibleRows.value
    const incorrect = list.filter((r) => !r.isCorrect)
    return {
      total: list.length,
      correctCount: list.length - incorrect.length,
      errorCount: incorrect.length,
      errorAmount: calcSubtotal(incorrect.map((r) => r.amount)),
      crossCount: list.filter((r) => r.isCrossPeriod).length,
      earlyCount: list.filter((r) => r.timingKind === 'early_book').length,
      lateCount: list.filter((r) => r.timingKind === 'late_book').length,
      missingDocCount: list.filter((r) => r.evidenceGap === 'missing_doc').length,
      missingBookCount: list.filter((r) => r.evidenceGap === 'missing_book').length,
      amountMismatchCount: list.filter((r) => r.evidenceGap === 'amount_mismatch').length,
      rawCount: list.filter((r) => r.invCategory === 'raw').length,
      finishedCount: list.filter((r) => r.invCategory === 'finished').length,
      uncategorizedCount: list.filter((r) => !r.invCategory).length,
    }
  })

  function filterBySegment(
    list: F2CutoffRow[],
    segment: 'before' | 'after' | 'unsorted',
  ): F2CutoffRow[] {
    const pe = effectiveCutoff.value
    const preferDoc = opts.config.value.trace === 'source_to_voucher'
    if (!pe) return segment === 'before' ? list : []
    return list.filter((r) => {
      const d = segmentKeyDate(r, preferDoc)
      if (segment === 'unsorted') return !d
      if (!d) return false
      return segment === 'before' ? d <= pe : d > pe
    })
  }

  /** 分类编制：原材料 / 产成品 / 未分类 各含截止前中后 */
  const categoryBlocks = computed(() => {
    const focus = meta.value.invCategory
    const cats: Array<{ key: 'raw' | 'finished' | ''; label: string }> = focus
      ? [{ key: focus as 'raw' | 'finished', label: focus === 'raw' ? '原材料' : '产成品' }]
      : [
          { key: 'raw', label: '原材料' },
          { key: 'finished', label: '产成品' },
          { key: '', label: '未分类' },
        ]

    return cats.map((c) => {
      const list = rows.value.filter((r) =>
        c.key ? r.invCategory === c.key : !r.invCategory,
      )
      return {
        ...c,
        before: filterBySegment(list, 'before'),
        after: filterBySegment(list, 'after'),
        unsorted: filterBySegment(list, 'unsorted'),
        total: list.length,
      }
    }).filter((b) => focus || b.total > 0 || b.key !== '')
  })

  const rowsBeforeCutoff = computed(() => filterBySegment(visibleRows.value, 'before'))
  const rowsAfterCutoff = computed(() => filterBySegment(visibleRows.value, 'after'))
  const rowsUnsorted = computed(() => filterBySegment(visibleRows.value, 'unsorted'))

  /** 自动提取窗口：主窗 or 对称 */
  const samplingDays = computed(() => {
    const before = Number(meta.value.sampleDaysBefore) || 5
    const after = Number(meta.value.sampleDaysAfter) || 5
    if (meta.value.sampleWindowMode === 'symmetric') {
      const n = Math.max(before, after)
      return { daysBefore: n, daysAfter: n }
    }
    // primary：账→单侧重日后；单→账侧重日前（对照窗保留较小一侧）
    if (opts.config.value.trace === 'voucher_to_source') {
      return { daysBefore: Math.min(before, 2), daysAfter: after }
    }
    return { daysBefore: before, daysAfter: Math.min(after, 2) }
  })

  function expandSymmetricWindow() {
    if (opts.isReadonly.value) return
    const before = Number(meta.value.sampleDaysBefore) || 5
    const after = Number(meta.value.sampleDaysAfter) || 5
    const n = Math.max(before, after, 5)
    updateMeta({
      sampleDaysBefore: String(n),
      sampleDaysAfter: String(n),
      sampleWindowMode: 'symmetric',
    })
  }

  function persistRows() {
    if (opts.isReadonly.value) return
    const key = dataKey(sheetCode.value)
    const item: ChecklistResponse = {
      item_id: key,
      conclusion: null,
      remark: JSON.stringify(rows.value),
    }
    opts.allResponses.value.set(key, item)
    window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
  }

  function persistConclusion() {
    if (opts.isReadonly.value) return
    const key = conclusionKey(sheetCode.value)
    const item: ChecklistResponse = {
      item_id: key,
      conclusion: null,
      remark: cutoffConclusion.value,
    }
    opts.allResponses.value.set(key, item)
    window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
  }

  function persistMeta() {
    if (opts.isReadonly.value) return
    const key = metaKey(sheetCode.value)
    const item: ChecklistResponse = {
      item_id: key,
      conclusion: null,
      remark: JSON.stringify(meta.value),
    }
    opts.allResponses.value.set(key, item)
    window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
  }

  function updateMeta(patch: Record<string, string>) {
    if (opts.isReadonly.value) return
    meta.value = { ...meta.value, ...patch }
    persistMeta()
  }

  function updateRow(id: string, patch: Partial<F2CutoffRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => {
      if (r.id !== id) return r
      const merged = { ...r, ...patch }
      if (
        'docDate' in patch
        || 'bookDate' in patch
        || 'docNo' in patch
        || 'voucherNo' in patch
        || 'amount' in patch
        || 'docAmount' in patch
        || 'isCorrectOverride' in patch
      ) {
        return enrichCutoffRow(merged)
      }
      return merged
    })
    persistRows()
  }

  function addRow(invCategory?: F2CutoffRow['invCategory']) {
    if (opts.isReadonly.value) return
    const cat = invCategory
      || ((meta.value.invCategory === 'raw' || meta.value.invCategory === 'finished')
        ? meta.value.invCategory
        : '')
    rows.value = [
      ...rows.value,
      { ...emptyRow(genRowId(), rows.value.length + 1), invCategory: cat as F2CutoffRow['invCategory'] },
    ]
    persistRows()
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.id !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    persistRows()
  }

  function fillFromExtracted(extracted: ExtractedVoucher[], fillMode: FillMode) {
    if (opts.isReadonly.value) return
    const cat = (meta.value.invCategory === 'raw' || meta.value.invCategory === 'finished')
      ? meta.value.invCategory
      : ''
    const mapped = extracted.map((v, i) =>
      enrichCutoffRow(mapVoucherToRow(v, i + 1, cat as F2CutoffRow['invCategory'])),
    )

    if (fillMode === 'replace') {
      rows.value = mapped.map((r, i) => ({ ...r, seq: i + 1 }))
    } else if (fillMode === 'merge') {
      const existingNos = new Set(rows.value.map((r) => r.voucherNo).filter(Boolean))
      const newRows = mapped.filter((r) => !r.voucherNo || !existingNos.has(r.voucherNo))
      const startSeq = rows.value.length
      newRows.forEach((r, i) => { r.seq = startSeq + i + 1 })
      rows.value = [...rows.value, ...newRows]
    } else {
      const startSeq = rows.value.length
      mapped.forEach((r, i) => { r.seq = startSeq + i + 1 })
      rows.value = [...rows.value, ...mapped]
    }
    persistRows()
  }

  watch(cutoffConclusion, () => {
    if (isHydrating()) return
    persistConclusion()
  })

  watch(sheetCode, () => {
    beginHydrate()
    try {
      rows.value = loadRows(opts.allResponses.value, sheetCode.value).map(enrichCutoffRow)
      loadMeta()
    } finally {
      endHydrate()
    }
  })

  function reloadRows(): void {
    beginHydrate()
    try {
      rows.value = loadRows(opts.allResponses.value, sheetCode.value).map(enrichCutoffRow)
      loadMeta()
    } finally {
      endHydrate()
    }
  }

  // 导入 Excel 后父级会替换 allResponses Map；同步刷新当前结构化表格。
  watch(
    () => opts.allResponses.value,
    () => reloadRows(),
  )

  /** 三流日期差异 > N 天的行（Task 12: 截止三流日期 + 跨期勾稽面板）
   *  三日期 = bookDate / docDate / inspectDate
   *  差异超阈值行应 row-class 标红
   */
  const dateGapThresholdDays = computed(() => Number(meta.value.sampleDaysAfter) || 5)

  const dateGapFlaggedRows = computed(() => {
    const thDays = dateGapThresholdDays.value
    return visibleRows.value.filter((r) => {
      const dates = [r.bookDate, r.docDate, r.inspectDate].filter(Boolean)
      if (dates.length < 2) return false
      const timestamps = dates.map((d) => new Date(d).getTime()).filter((t) => !isNaN(t))
      if (timestamps.length < 2) return false
      const maxGap = Math.max(...timestamps) - Math.min(...timestamps)
      const gapDays = maxGap / (24 * 60 * 60 * 1000)
      return gapDays > thDays
    })
  })

  /** 跨期勾稽面板数据（笔数/金额汇总） */
  const crossPeriodPanel = computed(() => {
    const crossRows = visibleRows.value.filter((r) => r.isCrossPeriod)
    return {
      count: crossRows.length,
      amount: calcSubtotal(crossRows.map((r) => r.amount)),
      flaggedCount: dateGapFlaggedRows.value.length,
      flaggedAmount: calcSubtotal(dateGapFlaggedRows.value.map((r) => r.amount)),
    }
  })

  return {
    rows,
    visibleRows,
    categoryBlocks,
    rowsBeforeCutoff,
    rowsAfterCutoff,
    rowsUnsorted,
    meta,
    updateMeta,
    cutoffSummary,
    crossHints,
    samplingDays,
    expandSymmetricWindow,
    cutoffConclusion,
    updateRow,
    addRow,
    removeRow,
    fillFromExtracted,
    effectiveCutoff,
    reloadRows,
    dateGapThresholdDays,
    dateGapFlaggedRows,
    crossPeriodPanel,
  }
}
