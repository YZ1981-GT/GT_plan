/**
 * useG8FairValueTest — G8-4 公允价值测试
 *
 * 编制逻辑（对齐 Excel《公允价值测试表G8-4》）：
 * 基础区段：未审/审定 数量×单价→公允价值 → 差异 → 层次划分
 * 详情区段：估值方法、技术与不可观察输入值（Level3 必填）
 * 联动：可从 G8-2 明细带入；审定合计应与 G8-2 期末审定勾稽
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { G8_FV_LEVEL_OPTIONS, G8_VALUATION_METHOD_OPTIONS } from './g8Constants'
import {
  parseNum,
  calcFairValueAmount,
  calcFairValueDiff,
  calcFairValueQtyImpact,
  calcFairValuePriceImpact,
  calcSubtotal,
} from './useG8FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import type { G8DetailRow } from './useG8Detail'
import {
  G8_DESIGNATION_KEY,
  G8A_FV_MARK_KEY,
  G8A_FV_PROGRAM_NOS,
  buildG8FvProcedureSummary,
  calcG8FvDiffWarning,
  fetchG8PerformanceMateriality,
  markG8AProcedureSteps,
  matchG8InvesteeKey,
  pushG8FvDiffToAdjustment,
  pushG8FvToDetail,
  pushG8FvToDesignation,
  reconcileG8FvWithDesignation,
  selectG8FvDiffTargets,
} from './g8CrossHelpers'

export interface G8FairValueRow {
  rowId: string
  seq: number
  investeeName: string
  initialInvestDate: string
  closingUnadjustedQty: number
  closingUnadjustedPrice: number
  closingUnadjustedFV: number
  closingAuditedQty: number
  closingAuditedPrice: number
  closingAuditedFV: number
  fairValueLevel: string
  valuationMethod: string
  methodConsistentWithPrior: string
  valuationSource: string
  inputSourceAndAdjustment: string
  valuationTechnique: string
  unobservableInputDesc: string
  unobservableInputValue: string
  valuationDocIndex: string
  /** |差异|>阈值时必填 */
  diffReason: string
}

export type G8FairValueEnrichedRow = G8FairValueRow & {
  fairValueDiff: number
  qtyImpact: number
  priceImpact: number
}

export interface G8FairValueTotals {
  closingUnadjustedFV: number
  closingAuditedFV: number
  fairValueDiff: number
}

const ITEM_ID_ROWS = 'G8-fv-test-rows'
const ITEM_ID_CONCLUSION = 'G8-fv-conclusion'
const ITEM_ID_DETAIL_ROWS = 'G8-detail-rows'
export const G8_FV_DIFF_THRESHOLD = 0.01

const FORMULA_FIELDS = new Set([
  'closingUnadjustedFV',
  'closingAuditedFV',
  'fairValueDiff',
  'qtyImpact',
  'priceImpact',
])

function genId(): string {
  return `g8fv-${Date.now().toString(36)}`
}

function emptyRow(seq: number, name = ''): G8FairValueRow {
  return {
    rowId: genId(),
    seq,
    investeeName: name,
    initialInvestDate: '',
    closingUnadjustedQty: 0,
    closingUnadjustedPrice: 0,
    closingUnadjustedFV: 0,
    closingAuditedQty: 0,
    closingAuditedPrice: 0,
    closingAuditedFV: 0,
    fairValueLevel: 'Level2',
    valuationMethod: G8_VALUATION_METHOD_OPTIONS[0],
    methodConsistentWithPrior: 'yes',
    valuationSource: '',
    inputSourceAndAdjustment: '',
    valuationTechnique: '',
    unobservableInputDesc: '',
    unobservableInputValue: '',
    valuationDocIndex: '',
    diffReason: '',
  }
}

export function enrichG8FairValueRow(raw: G8FairValueRow): G8FairValueEnrichedRow {
  const closingUnadjustedFV = calcFairValueAmount(raw.closingUnadjustedQty, raw.closingUnadjustedPrice)
  const closingAuditedFV = calcFairValueAmount(raw.closingAuditedQty, raw.closingAuditedPrice)
  const fairValueDiff = calcFairValueDiff(closingAuditedFV, closingUnadjustedFV)
  const qtyImpact = calcFairValueQtyImpact(
    raw.closingAuditedQty,
    raw.closingUnadjustedQty,
    raw.closingUnadjustedPrice,
  )
  const priceImpact = calcFairValuePriceImpact(
    raw.closingAuditedQty,
    raw.closingAuditedPrice,
    raw.closingUnadjustedPrice,
  )
  return {
    ...raw,
    closingUnadjustedFV,
    closingAuditedFV,
    fairValueDiff,
    qtyImpact,
    priceImpact,
  }
}

function parseRows(json: string | null | undefined): G8FairValueEnrichedRow[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    if (!Array.isArray(arr)) return []
    return arr.map((r: any, i: number) => enrichG8FairValueRow({
      rowId: r.rowId || genId(),
      seq: i + 1,
      investeeName: r.investeeName ?? r.assetName ?? '',
      initialInvestDate: r.initialInvestDate ?? '',
      closingUnadjustedQty: parseNum(r.closingUnadjustedQty),
      closingUnadjustedPrice: parseNum(r.closingUnadjustedPrice),
      closingUnadjustedFV: parseNum(r.closingUnadjustedFV),
      closingAuditedQty: parseNum(r.closingAuditedQty),
      closingAuditedPrice: parseNum(r.closingAuditedPrice),
      closingAuditedFV: parseNum(r.closingAuditedFV),
      fairValueLevel: r.fairValueLevel ?? 'Level2',
      valuationMethod: r.valuationMethod ?? G8_VALUATION_METHOD_OPTIONS[0],
      methodConsistentWithPrior: r.methodConsistentWithPrior ?? 'yes',
      valuationSource: r.valuationSource ?? '',
      inputSourceAndAdjustment: r.inputSourceAndAdjustment ?? '',
      valuationTechnique: r.valuationTechnique ?? '',
      unobservableInputDesc: r.unobservableInputDesc ?? '',
      unobservableInputValue: r.unobservableInputValue ?? '',
      valuationDocIndex: r.valuationDocIndex ?? '',
      diffReason: r.diffReason ?? '',
    }))
  } catch {
    return []
  }
}

function parseDetailRows(json: string | null | undefined): G8DetailRow[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

export function validateG8Level3(row: G8FairValueRow): string[] {
  if (row.fairValueLevel !== 'Level3') return []
  const errs: string[] = []
  if (!row.valuationTechnique?.trim()) errs.push('估值技术')
  if (!row.unobservableInputDesc?.trim()) errs.push('不可观察输入值描述')
  if (!row.unobservableInputValue?.trim()) errs.push('不可观察输入值')
  if (!row.valuationDocIndex?.trim()) errs.push('估值文件索引号')
  return errs
}

export function validateG8FairValueRow(row: G8FairValueRow): string[] {
  const errs = [...validateG8Level3(row)]
  if (row.fairValueLevel === 'Level2' && !row.valuationSource?.trim()) {
    errs.push('公允价值来源机构')
  }
  if (row.methodConsistentWithPrior === 'no' && !row.inputSourceAndAdjustment?.trim()) {
    errs.push('方法变更说明（输入值来源及调整）')
  }
  return errs
}

export function hasG8FairValueDifference(row: G8FairValueEnrichedRow): boolean {
  return Math.abs(row.fairValueDiff) > G8_FV_DIFF_THRESHOLD
}

export function useG8FairValueTest(opts: {
  wpId: Ref<string>
  projectId?: Ref<string> | ComputedRef<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const activeTab = ref<'basic' | 'detail'>('basic')
  const activeRowIndex = ref(0)
  const aiLoading = ref(false)
  const conclusion = ref('')
  const performanceMateriality = ref(0)
  const pmLoading = ref(false)
  const procedureMarking = ref(false)

  watch(() => opts.allResponses.value.get(ITEM_ID_CONCLUSION)?.conclusion, (v) => {
    conclusion.value = v ?? ''
  }, { immediate: true })

  const rows = computed(() => parseRows(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark))

  const detailRows = computed(() =>
    parseDetailRows(opts.allResponses.value.get(ITEM_ID_DETAIL_ROWS)?.remark),
  )

  const totals = computed<G8FairValueTotals>(() => ({
    closingUnadjustedFV: calcSubtotal(rows.value.map((r) => r.closingUnadjustedFV)),
    closingAuditedFV: calcSubtotal(rows.value.map((r) => r.closingAuditedFV)),
    fairValueDiff: calcSubtotal(rows.value.map((r) => r.fairValueDiff)),
  }))

  const detailClosingAdjustedTotal = computed(() =>
    calcSubtotal(detailRows.value.map((r) => parseNum(r.closingAdjusted ?? r.closingBalance))),
  )

  const crossRefVariance = computed(() =>
    totals.value.closingAuditedFV - detailClosingAdjustedTotal.value,
  )

  const hasCrossRefIssue = computed(() =>
    rows.value.length > 0
    && detailRows.value.length > 0
    && Math.abs(crossRefVariance.value) > G8_FV_DIFF_THRESHOLD,
  )

  const levelSummary = computed(() => {
    const summary = { Level1: 0, Level2: 0, Level3: 0, unset: 0 }
    for (const row of rows.value) {
      const lv = row.fairValueLevel
      if (lv === 'Level1') summary.Level1 += 1
      else if (lv === 'Level2') summary.Level2 += 1
      else if (lv === 'Level3') summary.Level3 += 1
      else summary.unset += 1
    }
    return summary
  })

  const diffCount = computed(() => rows.value.filter(hasG8FairValueDifference).length)

  const missingDiffReasonCount = computed(() =>
    rows.value.filter((r) => hasG8FairValueDifference(r) && !r.diffReason?.trim()).length,
  )

  const l3ValidationSummary = computed(() => {
    const issues: Array<{ row: G8FairValueEnrichedRow; errors: string[] }> = []
    for (const row of rows.value) {
      const errors = validateG8FairValueRow(row)
      if (errors.length) issues.push({ row, errors })
    }
    return issues
  })

  const designationRows = computed(() => {
    const raw = opts.allResponses.value.get(G8_DESIGNATION_KEY)?.remark
    if (!raw) return [] as Array<{ investeeName: string; fairValueLevel?: string; other?: string; fvReliable?: string }>
    try {
      const arr = JSON.parse(raw)
      return Array.isArray(arr) ? arr : []
    } catch {
      return []
    }
  })

  const levelReconcile = computed(() =>
    reconcileG8FvWithDesignation(rows.value, designationRows.value),
  )

  const hasLevelMismatch = computed(() =>
    levelReconcile.value.mismatches.length > 0
    || levelReconcile.value.missingInDesignation.length > 0,
  )

  const diffWarningLevel = computed(() =>
    calcG8FvDiffWarning(totals.value.fairValueDiff, totals.value.closingUnadjustedFV, {
      hardAbs: performanceMateriality.value,
    }),
  )

  const diffRatioPct = computed(() => {
    const base = Math.abs(totals.value.closingUnadjustedFV)
    if (base <= 0.01) return Math.abs(totals.value.fairValueDiff) > 0.01 ? 100 : 0
    return Math.round((Math.abs(totals.value.fairValueDiff) / base) * 1000) / 10
  })

  const exceedsB15 = computed(() => {
    const pm = performanceMateriality.value
    if (pm <= 0) return false
    return Math.abs(totals.value.fairValueDiff) > pm
  })

  const materialDiffCount = computed(() => {
    const { targets } = selectG8FvDiffTargets({
      rows: rows.value,
      performanceMateriality: performanceMateriality.value,
      onlyMaterial: true,
    })
    return targets.length
  })

  const procedureMarked = computed(() =>
    !!opts.allResponses.value.get(G8A_FV_MARK_KEY)?.remark
    || opts.allResponses.value.get(G8A_FV_MARK_KEY)?.conclusion === 'completed',
  )

  async function loadPerformanceMateriality(): Promise<number> {
    const pid = opts.projectId?.value || ''
    if (!pid) return 0
    pmLoading.value = true
    try {
      const pm = await fetchG8PerformanceMateriality(pid)
      performanceMateriality.value = pm
      return pm
    } finally {
      pmLoading.value = false
    }
  }

  // 首次有 projectId 时自动取 B15
  watch(
    () => opts.projectId?.value,
    (pid) => {
      if (pid && !performanceMateriality.value) void loadPerformanceMateriality()
    },
    { immediate: true },
  )

  function persist(list: G8FairValueRow[]): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(list) })
  }

  function stripFormulaFields(row: G8FairValueEnrichedRow): G8FairValueRow {
    const { fairValueDiff, qtyImpact, priceImpact, ...rest } = row
    void fairValueDiff
    void qtyImpact
    void priceImpact
    return rest
  }

  function updateRow(rowId: string, patch: Partial<G8FairValueRow>): void {
    if (opts.isReadonly.value) return
    if ([...Object.keys(patch)].some((k) => FORMULA_FIELDS.has(k))) return

    const list = rows.value.map((r) => {
      if (r.rowId !== rowId) return stripFormulaFields(r)
      const merged = enrichG8FairValueRow({ ...stripFormulaFields(r), ...patch })
      const errs = validateG8FairValueRow(merged)
      if (errs.length && merged.fairValueLevel === 'Level3') {
        ElMessage.warning(`Level3 必填：${errs.join('、')}`)
      }
      return merged
    })
    persist(list.map(stripFormulaFields))
  }

  function getDiffCellStyle(row: G8FairValueEnrichedRow): Record<string, string> {
    if (!hasG8FairValueDifference(row)) return {}
    return { color: '#f56c6c', fontWeight: '600' }
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入被投资单位名称', '新增公允价值测试行')
      const name = (value ?? '').trim()
      if (!name) return
      persist([...rows.value.map(stripFormulaFields), emptyRow(rows.value.length + 1, name)])
    } catch { /* cancelled */ }
  }

  function removeRow(rowId: string): void {
    if (opts.isReadonly.value) return
    const list = rows.value
      .filter((r) => r.rowId !== rowId)
      .map((r, i) => ({ ...stripFormulaFields(r), seq: i + 1 }))
    persist(list)
    if (activeRowIndex.value >= list.length) {
      activeRowIndex.value = Math.max(0, list.length - 1)
    }
  }

  function syncFromDetail(): void {
    if (opts.isReadonly.value) return
    const details = detailRows.value.filter((r) => r.investeeName?.trim())
    if (!details.length) {
      ElMessage.warning('G8-2 明细表暂无数据，请先编制明细')
      return
    }

    const existing = new Map(rows.value.map((r) => [matchG8InvesteeKey(r.investeeName), stripFormulaFields(r)]))
    let added = 0
    let updated = 0

    for (const d of details) {
      const key = matchG8InvesteeKey(d.investeeName)
      const qty = parseNum(d.shareCount)
      const price = parseNum(d.pricePerShare)
      const fv = parseNum(d.fairValueTotal) || calcFairValueAmount(qty, price) || parseNum(d.closingAdjusted)
      const patch: Partial<G8FairValueRow> = {
        investeeName: d.investeeName,
        closingUnadjustedQty: qty,
        closingUnadjustedPrice: price || (qty ? fv / qty : 0),
        closingAuditedQty: qty,
        closingAuditedPrice: price || (qty ? fv / qty : 0),
        fairValueLevel: d.fairValueLevel || 'Level2',
        valuationMethod: d.valuationMethod || G8_VALUATION_METHOD_OPTIONS[0],
      }

      if (existing.has(key)) {
        const prev = existing.get(key)!
        existing.set(key, enrichG8FairValueRow({ ...prev, ...patch }))
        updated += 1
      } else {
        existing.set(key, enrichG8FairValueRow({ ...emptyRow(existing.size + 1, d.investeeName), ...patch }))
        added += 1
      }
    }

    const list = [...existing.values()].map((r, i) => ({ ...stripFormulaFields(r), seq: i + 1 }))
    persist(list)
    ElMessage.success(`已从 G8-2 同步：新增 ${added} 行，更新 ${updated} 行`)
  }

  /** 将审定层次/数量/单价/FV 回写 G8-2，并同步 G8-5 层次 */
  function pushToDetail(): number {
    if (opts.isReadonly.value) return 0
    if (!rows.value.length) {
      ElMessage.warning('G8-4 暂无数据可回写')
      return 0
    }
    const nDetail = pushG8FvToDetail(opts.allResponses.value, opts.debouncedSave, rows.value)
    const nDesig = pushG8FvToDesignation(opts.allResponses.value, opts.debouncedSave, rows.value)
    if (!nDetail && !nDesig) {
      ElMessage.warning('未匹配到 G8-2/G8-5 行，请先编制明细或核对被投资单位名称')
      return 0
    }
    const parts: string[] = []
    if (nDetail) parts.push(`G8-2 ${nDetail} 行`)
    if (nDesig) parts.push(`G8-5 ${nDesig} 行`)
    ElMessage.success(`已回写：${parts.join('，')}（层次/审定FV）`)
    return nDetail + nDesig
  }

  /** 将超 B15（或阈值）公允差异推送 G8-3 → 回写 G8-1 期末账项调整 */
  async function pushDiffToAdjustment(forceAll = false): Promise<number> {
    if (opts.isReadonly.value) return 0
    if (!performanceMateriality.value && opts.projectId?.value) {
      await loadPerformanceMateriality()
    }

    let { targets, skipped, threshold } = selectG8FvDiffTargets({
      rows: rows.value,
      performanceMateriality: performanceMateriality.value,
      onlyMaterial: !forceAll,
    })

    if (!targets.length) {
      if (!skipped.length && !rows.value.some(hasG8FairValueDifference)) {
        ElMessage.info('无超阈值差异，无需推送调整分录')
        return 0
      }
      try {
        await ElMessageBox.confirm(
          skipped.length
            ? `无超过 B15（阈值 ${threshold.toFixed(2)}）的差异（跳过 ${skipped.length} 项）。是否按全部可识别差异（>|0.01|）推送？`
            : '无超过 B15 的差异。是否按全部可识别差异推送？',
          '推送差异至 G8-3',
          { type: 'warning', confirmButtonText: '全部推送', cancelButtonText: '取消' },
        )
      } catch {
        return 0
      }
      ;({ targets, skipped, threshold } = selectG8FvDiffTargets({
        rows: rows.value,
        performanceMateriality: performanceMateriality.value,
        onlyMaterial: false,
      }))
    }

    if (!targets.length) {
      ElMessage.info('无可推送差异')
      return 0
    }

    const n = pushG8FvDiffToAdjustment(
      opts.allResponses.value,
      opts.debouncedSave,
      targets.map((r) => ({
        summary: `G8-4 公允测试差异：${r.investeeName || '未命名'}`,
        amount: r.fairValueDiff,
        indexRef: 'G8-4',
        remark: [
          `审定 ${r.closingAuditedFV} − 未审 ${r.closingUnadjustedFV}`,
          performanceMateriality.value > 0
            ? `B15=${performanceMateriality.value}`
            : '',
          r.diffReason ? `原因：${r.diffReason}` : '',
        ].filter(Boolean).join('；'),
      })),
      'G8-4',
    )
    const skipHint = skipped.length ? `（另跳过 ${skipped.length} 项未超 B15）` : ''
    ElMessage.success(`已推送 ${n} 笔差异至 G8-3，并回写 G8-1 期末账项调整${skipHint}`)
    return n
  }

  /** 回填 G8A 公允测试程序步骤为已完成 */
  async function markProcedureComplete(): Promise<number> {
    if (opts.isReadonly.value) return -1
    const pid = opts.projectId?.value || ''
    if (!pid) {
      ElMessage.warning('缺少项目 ID，无法回填 G8A')
      return -1
    }
    if (!rows.value.length) {
      ElMessage.warning('请先编制 G8-4 后再回填程序表')
      return -1
    }
    if (l3ValidationSummary.value.length) {
      try {
        await ElMessageBox.confirm(
          `仍有 ${l3ValidationSummary.value.length} 项校验未通过，是否仍标记 G8A 公允测试程序为已完成？`,
          '回填 G8A',
          { type: 'warning', confirmButtonText: '仍标记完成', cancelButtonText: '取消' },
        )
      } catch {
        return -1
      }
    }

    procedureMarking.value = true
    try {
      const summary = buildG8FvProcedureSummary({
        rowCount: rows.value.length,
        diffCount: diffCount.value,
        level3Count: levelSummary.value.Level3,
        auditedTotal: totals.value.closingAuditedFV,
        validationErrors: l3ValidationSummary.value.length,
      })
      const n = await markG8AProcedureSteps({
        projectId: pid,
        programNos: [...G8A_FV_PROGRAM_NOS],
        status: 'completed',
        linkedWorkpapers: 'G8-4',
        executionSummary: summary,
      })
      opts.debouncedSave(G8A_FV_MARK_KEY, {
        conclusion: 'completed',
        remark: JSON.stringify({
          at: new Date().toISOString(),
          summary,
          programNos: [...G8A_FV_PROGRAM_NOS],
        }),
      })
      ElMessage.success(
        n > 0
          ? `已回填 G8A 程序步骤 ${[...G8A_FV_PROGRAM_NOS].join('/')}（公允价值测试）为已完成`
          : '已记录完成标记（程序表字段写入可能需刷新 G8A 查看）',
      )
      return Math.max(n, 1)
    } finally {
      procedureMarking.value = false
    }
  }

  function updateConclusion(value: string): void {
    if (opts.isReadonly.value) return
    conclusion.value = value
    opts.debouncedSave(ITEM_ID_CONCLUSION, { conclusion: value })
  }

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value || !opts.wpId.value) return
    aiLoading.value = true
    try {
      const { api } = await import('@/services/apiProxy')
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g8/ai/fair-value-conclusion`,
        { existingContent: conclusion.value, rows: rows.value },
        { _silent: true } as any,
      )
      const text = res?.data?.content ?? res?.content ?? ''
      if (text) updateConclusion(text)
    } catch { /* AI optional */ }
    finally { aiLoading.value = false }
  }

  return {
    rows,
    activeTab,
    activeRowIndex,
    conclusion,
    aiLoading,
    totals,
    levelSummary,
    diffCount,
    missingDiffReasonCount,
    l3ValidationSummary,
    crossRefVariance,
    hasCrossRefIssue,
    detailClosingAdjustedTotal,
    levelReconcile,
    hasLevelMismatch,
    diffWarningLevel,
    diffRatioPct,
    performanceMateriality,
    pmLoading,
    exceedsB15,
    materialDiffCount,
    procedureMarked,
    procedureMarking,
    loadPerformanceMateriality,
    updateRow,
    addRow,
    removeRow,
    syncFromDetail,
    pushToDetail,
    pushDiffToAdjustment,
    markProcedureComplete,
    updateConclusion,
    generateAiConclusion,
    getDiffCellStyle,
    hasDifference: hasG8FairValueDifference,
    fvLevelOptions: G8_FV_LEVEL_OPTIONS,
    valuationMethodOptions: G8_VALUATION_METHOD_OPTIONS,
    validateLevel3: validateG8Level3,
    validateRow: validateG8FairValueRow,
  }
}
