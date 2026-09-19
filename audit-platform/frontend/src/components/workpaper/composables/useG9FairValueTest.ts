/**
 * useG9FairValueTest — G9-4 公允价值测试
 *
 * 编制逻辑（对齐 Excel《公允价值测试表G9-4》+ G8-4 成熟模式）：
 * 基础区段：未审/审定 数量×单价→公允价值 → 差异（数量/价格分解）→ 层次
 * 详情区段：估值方法、技术与不可观察输入值（Level3 必填）
 * 联动：从 G9-2 带入；回写 G9-2；超阈值差异推送 G9-3；回填 G9A seq8
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { G9_FV_LEVEL_OPTIONS, G9_VALUATION_METHOD_OPTIONS } from './g9Constants'
import {
  parseNum,
  calcFairValueAmount,
  calcFairValueDiff,
  calcFairValueQtyImpact,
  calcFairValuePriceImpact,
  calcSubtotal,
} from './useG9FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import {
  G9_DETAIL_KEY,
  G9_FV_DIFF_THRESHOLD,
  G9A_FV_MARK_KEY,
  G9A_FV_PROGRAM_NOS,
  buildG9FvProcedureSummary,
  calcG9FvDiffWarning,
  fetchG9PerformanceMateriality,
  markG9AProcedureSteps,
  matchG9AssetKey,
  pushG9FvDiffToAdjustment,
  pushG9FvToDetail,
  selectG9FvDiffTargets,
} from './g9FvCrossHelpers'

export interface G9FairValueRow {
  rowId: string
  seq: number
  assetName: string
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
  nonLiquidityDiscount: number
  valuationDocIndex: string
  /** |差异|>阈值时必填 */
  diffReason: string
}

export type G9FairValueEnrichedRow = G9FairValueRow & {
  fairValueDiff: number
  qtyImpact: number
  priceImpact: number
}

export interface G9FairValueTotals {
  closingUnadjustedFV: number
  closingAuditedFV: number
  fairValueDiff: number
}

const ITEM_ID_ROWS = 'G9-fv-test-rows'
const ITEM_ID_CONCLUSION = 'G9-fv-conclusion'

const FORMULA_FIELDS = new Set([
  'closingUnadjustedFV',
  'closingAuditedFV',
  'fairValueDiff',
  'qtyImpact',
  'priceImpact',
])

function genId(): string {
  return `g9fv-${Date.now().toString(36)}`
}

function emptyRow(seq: number, name = ''): G9FairValueRow {
  return {
    rowId: genId(),
    seq,
    assetName: name,
    initialInvestDate: '',
    closingUnadjustedQty: 0,
    closingUnadjustedPrice: 0,
    closingUnadjustedFV: 0,
    closingAuditedQty: 0,
    closingAuditedPrice: 0,
    closingAuditedFV: 0,
    fairValueLevel: 'Level2',
    valuationMethod: G9_VALUATION_METHOD_OPTIONS[0],
    methodConsistentWithPrior: 'yes',
    valuationSource: '',
    inputSourceAndAdjustment: '',
    valuationTechnique: '',
    unobservableInputDesc: '',
    unobservableInputValue: '',
    nonLiquidityDiscount: 0,
    valuationDocIndex: '',
    diffReason: '',
  }
}

export function enrichG9FairValueRow(raw: G9FairValueRow): G9FairValueEnrichedRow {
  const unadjFv = (Math.abs(raw.closingUnadjustedQty) > 0 || Math.abs(raw.closingUnadjustedPrice) > 0)
    ? calcFairValueAmount(raw.closingUnadjustedQty, raw.closingUnadjustedPrice)
    : parseNum(raw.closingUnadjustedFV)
  const auditedFv = (Math.abs(raw.closingAuditedQty) > 0 || Math.abs(raw.closingAuditedPrice) > 0)
    ? calcFairValueAmount(raw.closingAuditedQty, raw.closingAuditedPrice)
    : parseNum(raw.closingAuditedFV)

  const fairValueDiff = calcFairValueDiff(auditedFv, unadjFv)
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
    closingUnadjustedFV: unadjFv,
    closingAuditedFV: auditedFv,
    fairValueDiff,
    qtyImpact,
    priceImpact,
  }
}

function parseRows(json: string | null | undefined): G9FairValueEnrichedRow[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    if (!Array.isArray(arr)) return []
    return arr.map((r: any, i: number) => enrichG9FairValueRow({
      rowId: r.rowId || genId(),
      seq: i + 1,
      assetName: r.assetName ?? '',
      initialInvestDate: r.initialInvestDate ?? '',
      closingUnadjustedQty: parseNum(r.closingUnadjustedQty),
      closingUnadjustedPrice: parseNum(r.closingUnadjustedPrice),
      closingUnadjustedFV: parseNum(r.closingUnadjustedFV),
      closingAuditedQty: parseNum(r.closingAuditedQty),
      closingAuditedPrice: parseNum(r.closingAuditedPrice),
      closingAuditedFV: parseNum(r.closingAuditedFV),
      fairValueLevel: r.fairValueLevel ?? 'Level2',
      valuationMethod: r.valuationMethod ?? G9_VALUATION_METHOD_OPTIONS[0],
      methodConsistentWithPrior: r.methodConsistentWithPrior ?? 'yes',
      valuationSource: r.valuationSource ?? '',
      inputSourceAndAdjustment: r.inputSourceAndAdjustment ?? '',
      valuationTechnique: r.valuationTechnique ?? '',
      unobservableInputDesc: r.unobservableInputDesc ?? '',
      unobservableInputValue: r.unobservableInputValue ?? '',
      nonLiquidityDiscount: parseNum(r.nonLiquidityDiscount),
      valuationDocIndex: r.valuationDocIndex ?? '',
      diffReason: r.diffReason ?? '',
    }))
  } catch {
    return []
  }
}

function parseDetailRows(json: string | null | undefined): Record<string, unknown>[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

export function validateG9Level3(row: G9FairValueRow): string[] {
  if (row.fairValueLevel !== 'Level3') return []
  const errs: string[] = []
  if (!row.valuationTechnique?.trim()) errs.push('估值技术')
  if (!row.unobservableInputDesc?.trim()) errs.push('不可观察输入值描述')
  if (!row.unobservableInputValue?.trim()) errs.push('不可观察输入值')
  if (!row.valuationDocIndex?.trim()) errs.push('估值文件索引')
  return errs
}

export function validateG9FairValueRow(row: G9FairValueRow): string[] {
  const errs = [...validateG9Level3(row)]
  if (row.fairValueLevel === 'Level2' && !row.valuationSource?.trim()) {
    errs.push('公允价值来源机构')
  }
  if (row.methodConsistentWithPrior === 'no' && !row.inputSourceAndAdjustment?.trim()) {
    errs.push('方法变更说明（输入值来源及调整）')
  }
  return errs
}

export function hasG9FairValueDifference(row: G9FairValueEnrichedRow): boolean {
  return Math.abs(row.fairValueDiff) > G9_FV_DIFF_THRESHOLD
}

export { G9_FV_DIFF_THRESHOLD }

export function useG9FairValueTest(opts: {
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
    parseDetailRows(opts.allResponses.value.get(G9_DETAIL_KEY)?.remark),
  )

  const totals = computed<G9FairValueTotals>(() => ({
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
    && Math.abs(crossRefVariance.value) > G9_FV_DIFF_THRESHOLD,
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

  const diffCount = computed(() => rows.value.filter(hasG9FairValueDifference).length)

  const missingDiffReasonCount = computed(() =>
    rows.value.filter((r) => hasG9FairValueDifference(r) && !r.diffReason?.trim()).length,
  )

  const l3ValidationSummary = computed(() => {
    const issues: Array<{ row: G9FairValueEnrichedRow; errors: string[] }> = []
    for (const row of rows.value) {
      const errors = validateG9FairValueRow(row)
      if (errors.length) issues.push({ row, errors })
    }
    return issues
  })

  const diffWarningLevel = computed(() =>
    calcG9FvDiffWarning(totals.value.fairValueDiff, totals.value.closingUnadjustedFV, {
      hardAbs: performanceMateriality.value,
    }),
  )

  const diffRatioPct = computed(() => {
    const base = Math.abs(totals.value.closingUnadjustedFV)
    if (base <= G9_FV_DIFF_THRESHOLD) {
      return Math.abs(totals.value.fairValueDiff) > G9_FV_DIFF_THRESHOLD ? 100 : 0
    }
    return Math.round((Math.abs(totals.value.fairValueDiff) / base) * 1000) / 10
  })

  const exceedsB15 = computed(() => {
    const pm = performanceMateriality.value
    if (pm <= 0) return false
    return Math.abs(totals.value.fairValueDiff) > pm
  })

  const materialDiffCount = computed(() => {
    const { targets } = selectG9FvDiffTargets({
      rows: rows.value,
      performanceMateriality: performanceMateriality.value,
      onlyMaterial: true,
    })
    return targets.length
  })

  const procedureMarked = computed(() =>
    !!opts.allResponses.value.get(G9A_FV_MARK_KEY)?.remark
    || opts.allResponses.value.get(G9A_FV_MARK_KEY)?.conclusion === 'completed',
  )

  async function loadPerformanceMateriality(): Promise<number> {
    const pid = opts.projectId?.value || ''
    if (!pid) return 0
    pmLoading.value = true
    try {
      const pm = await fetchG9PerformanceMateriality(pid)
      performanceMateriality.value = pm
      return pm
    } finally {
      pmLoading.value = false
    }
  }

  watch(
    () => opts.projectId?.value,
    (pid) => {
      if (pid && !performanceMateriality.value) void loadPerformanceMateriality()
    },
    { immediate: true },
  )

  function persist(list: G9FairValueRow[]): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(list) })
  }

  function stripFormulaFields(row: G9FairValueEnrichedRow): G9FairValueRow {
    const { fairValueDiff, qtyImpact, priceImpact, ...rest } = row
    void fairValueDiff
    void qtyImpact
    void priceImpact
    return rest
  }

  function updateRow(rowId: string, patch: Partial<G9FairValueRow>): void {
    if (opts.isReadonly.value) return
    if ([...Object.keys(patch)].some((k) => FORMULA_FIELDS.has(k))) return

    const list = rows.value.map((r) => {
      if (r.rowId !== rowId) return stripFormulaFields(r)
      const merged = enrichG9FairValueRow({ ...stripFormulaFields(r), ...patch })
      const errs = validateG9FairValueRow(merged)
      if (errs.length && merged.fairValueLevel === 'Level3') {
        ElMessage.warning(`Level3 必填：${errs.join('、')}`)
      }
      return merged
    })
    persist(list.map(stripFormulaFields))
  }

  function getDiffCellStyle(row: G9FairValueEnrichedRow): Record<string, string> {
    if (!hasG9FairValueDifference(row)) return {}
    return { color: '#f56c6c', fontWeight: '600' }
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入资产名称', '新增公允价值测试行')
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
    const details = detailRows.value.filter((r) => String(r.assetName ?? '').trim())
    if (!details.length) {
      ElMessage.warning('G9-2 明细表暂无数据，请先编制明细')
      return
    }

    const existing = new Map(
      rows.value.map((r) => [matchG9AssetKey(r.assetName), stripFormulaFields(r)]),
    )
    let added = 0
    let updated = 0

    for (const d of details) {
      const name = String(d.assetName ?? '')
      const key = matchG9AssetKey(name)
      const qty = parseNum(d.holdingQuantity)
      const audited = parseNum(d.closingAdjusted ?? d.closingBalance)
      const unadj = parseNum(d.closingBalance ?? d.closingAdjusted)
      const price = qty > 0 ? audited / qty : 0
      const patch: Partial<G9FairValueRow> = {
        assetName: name,
        initialInvestDate: String(d.initialInvestDate ?? ''),
        closingUnadjustedQty: qty,
        closingUnadjustedPrice: price,
        closingAuditedQty: qty,
        closingAuditedPrice: price,
        fairValueLevel: String(d.fairValueLevel || 'Level2'),
        valuationMethod: String(d.valuationMethod || G9_VALUATION_METHOD_OPTIONS[0]),
      }
      if (qty <= 0) {
        patch.closingUnadjustedFV = unadj
        patch.closingAuditedFV = audited
        patch.closingUnadjustedPrice = 0
        patch.closingAuditedPrice = 0
      }

      if (existing.has(key)) {
        const prev = existing.get(key)!
        existing.set(key, enrichG9FairValueRow({ ...prev, ...patch }))
        updated += 1
      } else {
        existing.set(key, enrichG9FairValueRow({ ...emptyRow(existing.size + 1, name), ...patch }))
        added += 1
      }
    }

    const list = [...existing.values()].map((r, i) => ({ ...stripFormulaFields(r), seq: i + 1 }))
    persist(list)
    ElMessage.success(`已从 G9-2 同步：新增 ${added} 行，更新 ${updated} 行`)
  }

  function pushToDetail(): number {
    if (opts.isReadonly.value) return 0
    if (!rows.value.length) {
      ElMessage.warning('G9-4 暂无数据可回写')
      return 0
    }
    const n = pushG9FvToDetail(opts.allResponses.value, opts.debouncedSave, rows.value)
    if (!n) {
      ElMessage.warning('未匹配到 G9-2 行，请先编制明细或核对资产名称')
      return 0
    }
    ElMessage.success(`已回写 G9-2 ${n} 行（层次/估值方法/持有数量）`)
    return n
  }

  async function pushDiffToAdjustment(_forceAll = false): Promise<number> {
    if (opts.isReadonly.value) return 0
    if (!performanceMateriality.value && opts.projectId?.value) {
      await loadPerformanceMateriality()
    }

    let { targets, skipped, threshold } = selectG9FvDiffTargets({
      rows: rows.value,
      performanceMateriality: performanceMateriality.value,
      onlyMaterial: !_forceAll,
    })

    if (!targets.length) {
      if (!skipped.length && !rows.value.some(hasG9FairValueDifference)) {
        ElMessage.info('无超阈值差异，无需推送调整分录')
        return 0
      }
      try {
        await ElMessageBox.confirm(
          skipped.length
            ? `无超过 B15（阈值 ${threshold.toFixed(2)}）的差异（跳过 ${skipped.length} 项）。是否按全部可识别差异（>|0.01|）推送？`
            : '无超过 B15 的差异。是否按全部可识别差异推送？',
          '推送差异至 G9-3',
          { type: 'warning', confirmButtonText: '全部推送', cancelButtonText: '取消' },
        )
      } catch {
        return 0
      }
      ;({ targets, skipped, threshold } = selectG9FvDiffTargets({
        rows: rows.value,
        performanceMateriality: performanceMateriality.value,
        onlyMaterial: false,
      }))
    }

    if (!targets.length) {
      ElMessage.info('无可推送差异')
      return 0
    }

    const n = pushG9FvDiffToAdjustment(
      opts.allResponses.value,
      opts.debouncedSave,
      targets.map((r) => ({
        summary: `G9-4 公允测试差异：${r.assetName || '未命名'}`,
        amount: r.fairValueDiff,
        indexRef: 'G9-4',
        remark: [
          `审定 ${r.closingAuditedFV} − 未审 ${r.closingUnadjustedFV}`,
          performanceMateriality.value > 0 ? `B15=${performanceMateriality.value}` : '',
          r.diffReason ? `原因：${r.diffReason}` : '',
        ].filter(Boolean).join('；'),
      })),
      'G9-4',
    )
    const skipHint = skipped.length ? `（另跳过 ${skipped.length} 项未超 B15）` : ''
    ElMessage.success(`已推送 ${n} 笔差异至 G9-3，并回写 G9-1 期末账项调整${skipHint}`)
    return n
  }

  async function markProcedureComplete(): Promise<number> {
    if (opts.isReadonly.value) return -1
    const pid = opts.projectId?.value || ''
    if (!pid) {
      ElMessage.warning('缺少项目 ID，无法回填 G9A')
      return -1
    }
    if (!rows.value.length) {
      ElMessage.warning('请先编制 G9-4 后再回填程序表')
      return -1
    }
    if (l3ValidationSummary.value.length) {
      try {
        await ElMessageBox.confirm(
          `仍有 ${l3ValidationSummary.value.length} 项校验未通过，是否仍标记 G9A 公允测试程序为已完成？`,
          '回填 G9A',
          { type: 'warning', confirmButtonText: '仍标记完成', cancelButtonText: '取消' },
        )
      } catch {
        return -1
      }
    }

    procedureMarking.value = true
    try {
      const summary = buildG9FvProcedureSummary({
        rowCount: rows.value.length,
        diffCount: diffCount.value,
        level3Count: levelSummary.value.Level3,
        auditedTotal: totals.value.closingAuditedFV,
        validationErrors: l3ValidationSummary.value.length,
      })
      const n = await markG9AProcedureSteps({
        projectId: pid,
        programNos: [...G9A_FV_PROGRAM_NOS],
        status: 'completed',
        linkedWorkpapers: 'G9-4/G9-5',
        executionSummary: summary,
      })
      opts.debouncedSave(G9A_FV_MARK_KEY, {
        conclusion: 'completed',
        remark: JSON.stringify({
          at: new Date().toISOString(),
          summary,
          programNos: [...G9A_FV_PROGRAM_NOS],
        }),
      })
      ElMessage.success(
        n > 0
          ? `已回填 G9A 程序步骤 ${[...G9A_FV_PROGRAM_NOS].join('/')}（公允价值测试）为已完成`
          : '已记录完成标记（程序表字段写入可能需刷新 G9A 查看）',
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
        `/api/workpapers/${opts.wpId.value}/g9/ai/fair-value-conclusion`,
        { existingContent: conclusion.value, rows: rows.value },
        { _silent: true } as any,
      )
      const text = res?.data?.data?.content ?? res?.data?.content ?? res?.content ?? ''
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
    hasDifference: hasG9FairValueDifference,
    fvLevelOptions: G9_FV_LEVEL_OPTIONS,
    valuationMethodOptions: G9_VALUATION_METHOD_OPTIONS,
    validateLevel3: validateG9Level3,
    validateRow: validateG9FairValueRow,
  }
}
