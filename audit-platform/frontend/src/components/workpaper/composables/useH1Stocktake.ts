/**
 * useH1Stocktake — H1-9~11 监盘组 composable
 *
 * 计划/检查/小结三阶段共用状态
 * H1-9 对齐致同：风险→了解→胜任能力→计划安排（范围/抽样/推算）
 * H1-10 对齐致同双向抽盘（账面→实物 / 实物→账面）+ 三数量差异自动计算
 * H1-11 了解→执行→分类复盘→统计→结论；可从 H1-9/10 回填
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Task: 3.11
 * Requirements: 10.1-10.10
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import { calcSubtotal } from './useH1FormulaEngine'
import {
  buildSamplingMethodNarrative,
  calcCategoryScopeTotals,
  createEmptyPlanForm,
  draftSampleQtyFromScopes,
  normalizePlanForm,
  newCategoryScopeRow,
  newPlanLocationRow,
  recalcCategoryScopeRow,
  toLegacyPlanInfo,
  type H1StocktakePlanForm,
  type PlanCategoryScopeRow,
  type PlanLocationRow,
} from './h1StocktakePlanModel'
import {
  aggregateH12ToCategoryScopes,
  applyRiskSuggestions,
  calcPlanLogicWarningsEnhanced,
  calcPlanVsCheckWarnings,
  draftIdleNoteFromH4,
  draftLocationScopeFromH12,
  draftPlanConclusion,
  extractPriorYearPlanHints,
  getPlanGateBlockers,
  isPlanReadyForCheck,
  suggestCoverageByRisk,
  type H12DetailLike,
  type H14IdleLike,
} from './h1StocktakePlanEnhance'
import {
  calcRecountRates,
  createEmptySummaryForm,
  draftLocationsFromCheckRows,
  draftRecountFromCheckRows,
  isTimeRangeValid,
  normalizeSummaryForm,
  newAuditorRow,
  newClientPersonnelRow,
  newLocationRow,
  type H1StocktakeSummaryForm,
  type SummaryAuditorRow,
  type SummaryLocationRow,
  type SummaryPersonnelRow,
} from './h1StocktakeSummaryModel'
import {
  applyAutoSyncPatch,
  buildAutoSyncPatch,
  buildDiffEvidence,
  buildExportRows,
  calcSamplePlanGap,
  collectConcernsFromCheck,
  draftConclusionRule,
  evaluateCompleteness,
  fingerprintCheckRows,
  mergeBuildingFromOcr,
  mergeDiffIntoAbnormal,
  mergeIdleRowsFromConcerns,
  type AutoSyncField,
} from './h1StocktakeSummaryEnhance'
import {
  applyQtySideEffects,
  calcDirectionCoverage,
  calcRowDiffs,
  createEmptyCheckMeta,
  createEmptyCheckRow,
  draftCheckSheetConclusion,
  draftMetaFromPlan,
  mapDetailRowsToCheckRows,
  normalizeCheckMeta,
  normalizeCheckRow,
  sumDetailOriginalCost,
  type StocktakeCheckMeta,
  type StocktakeCheckRow,
  type StocktakeDirection,
} from './h1StocktakeCheckModel'

export type {
  StocktakeCheckMeta,
  StocktakeCheckRow,
  StocktakeDirection,
} from './h1StocktakeCheckModel'

export type { H1StocktakePlanForm, PlanCategoryScopeRow, PlanLocationRow } from './h1StocktakePlanModel'

// ─── Types ───────────────────────────────────────────────────────────────────

/** @deprecated 兼容旧五字段；新逻辑请用 planForm */
export interface StocktakePlanInfo {
  stocktakeDate: string
  location: string
  participants: string
  scope: string
  method: string
}

/** @deprecated 已并入 planForm.categoryScopes */
export interface SampleSelectionRow {
  rowId: string
  category: string
  selectionCriteria: string
  sampleSize: number
  coverageAmount: number
  coverageRate: number
}

export interface StocktakeStatistics {
  totalChecked: number
  matchCount: number
  surplusCount: number
  deficitCount: number
  matchRate: number
  surplusAmount: number
  deficitAmount: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX_PLAN = 'H1-9'
const ITEM_PREFIX_CHECK = 'H1-10'
const ITEM_PREFIX_SUMMARY = 'H1-11'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1Stocktake(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    onSave?: (itemId: string, value: any) => void
  },
) {
  const planForm = ref<H1StocktakePlanForm>(createEmptyPlanForm())
  const planInfo = computed<StocktakePlanInfo>(() => toLegacyPlanInfo(planForm.value))
  const sampleSelections = computed<SampleSelectionRow[]>(() =>
    planForm.value.categoryScopes.map((r) => ({
      rowId: r.rowId,
      category: r.category,
      selectionCriteria: r.unit || '',
      sampleSize: r.planQty,
      coverageAmount: r.planAmount,
      coverageRate: r.coverageRate,
    })),
  )

  const checkRows = ref<StocktakeCheckRow[]>([])
  const checkMeta = ref<StocktakeCheckMeta>(createEmptyCheckMeta())

  const summaryNote = ref('')
  const summaryConclusion = ref('')
  const summaryForm = ref<H1StocktakeSummaryForm>(createEmptySummaryForm())

  function _loadData(): void {
    // Plan：优先完整 form；否则从旧 info + selections 迁移
    const planFormItem = allResponses.value.get(`${ITEM_PREFIX_PLAN}-form`)
    let parsedPlan: any = null
    if (planFormItem?.remark) {
      try { parsedPlan = JSON.parse(planFormItem.remark) } catch { parsedPlan = null }
    }
    let legacyInfo: Partial<StocktakePlanInfo> | undefined
    const planItem = allResponses.value.get(`${ITEM_PREFIX_PLAN}-info`)
    if (planItem?.remark) {
      try { legacyInfo = JSON.parse(planItem.remark) } catch { /* */ }
    }
    planForm.value = normalizePlanForm(parsedPlan, legacyInfo as any)

    const selectItem = allResponses.value.get(`${ITEM_PREFIX_PLAN}-selections`)
    if (selectItem?.remark && !parsedPlan?.categoryScopes) {
      try {
        const parsed = JSON.parse(selectItem.remark)
        if (Array.isArray(parsed) && parsed.length) {
          planForm.value.categoryScopes = parsed.map((r: any, i: number) =>
            recalcCategoryScopeRow(newCategoryScopeRow({
              rowId: r.rowId,
              seq: i + 1,
              category: r.category ?? '',
              planQty: Number(r.sampleSize) || 0,
              planAmount: Number(r.coverageAmount) || 0,
              coverageRate: Number(r.coverageRate) || 0,
              unit: r.selectionCriteria || '台/套',
            })),
          )
        }
      } catch { /* */ }
    }

    const checkItem = allResponses.value.get(`${ITEM_PREFIX_CHECK}-rows`)
    if (checkItem?.remark) {
      try {
        const parsed = JSON.parse(checkItem.remark)
        checkRows.value = Array.isArray(parsed) ? parsed.map(normalizeCheckRow) : []
      } catch { checkRows.value = [] }
    }

    const metaItem = allResponses.value.get(`${ITEM_PREFIX_CHECK}-meta`)
    if (metaItem?.remark) {
      try {
        const parsed = typeof metaItem.remark === 'string'
          ? JSON.parse(metaItem.remark)
          : metaItem.remark
        checkMeta.value = normalizeCheckMeta(parsed)
      } catch { checkMeta.value = createEmptyCheckMeta() }
    }

    summaryNote.value = _getString(`${ITEM_PREFIX_SUMMARY}-note`)
    summaryConclusion.value = _getString(`${ITEM_PREFIX_SUMMARY}-conclusion`)
    if (!summaryConclusion.value) {
      summaryConclusion.value = _getString(`${ITEM_PREFIX_SUMMARY}-audit-conclusion`)
    }
    const formItem = allResponses.value.get(`${ITEM_PREFIX_SUMMARY}-form`)
    let parsedForm: any = null
    if (formItem?.remark) {
      try { parsedForm = JSON.parse(formItem.remark) } catch { parsedForm = null }
    }
    summaryForm.value = normalizeSummaryForm(parsedForm, summaryConclusion.value)
    if (summaryForm.value.conclusion && !summaryConclusion.value) {
      summaryConclusion.value = summaryForm.value.conclusion
    }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  const bookToFloorRows = computed(() =>
    checkRows.value.filter((r) => r.direction !== 'floorToBook'),
  )
  const floorToBookRows = computed(() =>
    checkRows.value.filter((r) => r.direction === 'floorToBook'),
  )

  const statistics = computed<StocktakeStatistics>(() => {
    const total = checkRows.value.length
    const matchCount = checkRows.value.filter((r) => r.result === '账实相符').length
    const surplusList = checkRows.value.filter((r) => r.result === '盘盈')
    const deficitList = checkRows.value.filter((r) => r.result === '盘亏')
    return {
      totalChecked: total,
      matchCount,
      surplusCount: surplusList.length,
      deficitCount: deficitList.length,
      matchRate: total > 0 ? (matchCount / total * 100) : 0,
      surplusAmount: calcSubtotal(surplusList.map((r) => Math.abs(r.diffAmount))),
      deficitAmount: calcSubtotal(deficitList.map((r) => Math.abs(r.diffAmount))),
    }
  })

  const bookToFloorCoverage = computed(() =>
    calcDirectionCoverage(bookToFloorRows.value, checkMeta.value.totalBookCost),
  )
  const floorToBookCoverage = computed(() =>
    calcDirectionCoverage(floorToBookRows.value, checkMeta.value.totalBookCost),
  )

  const surplusRows = computed(() =>
    checkRows.value.filter((r) => r.result === '盘盈'),
  )
  const deficitRows = computed(() =>
    checkRows.value.filter((r) => r.result === '盘亏'),
  )

  const planScopeTotals = computed(() => calcCategoryScopeTotals(planForm.value.categoryScopes))
  const planLogicWarnings = computed(() => calcPlanLogicWarningsEnhanced(planForm.value))
  const planGateBlockers = computed(() => getPlanGateBlockers(planForm.value))
  const planReadyForCheck = computed(() => isPlanReadyForCheck(planForm.value))
  const riskSuggestion = computed(() => suggestCoverageByRisk(planForm.value.existenceRiskLevel))

  const planVsCheckWarnings = computed(() => {
    const checkedAmount = checkRows.value.reduce(
      (s, r) => s + (Number(r.bookNetValue) || Number(r.bookAmount) || Number(r.bookCost) || 0),
      0,
    )
    return calcPlanVsCheckWarnings(planForm.value, {
      bookToFloorCount: bookToFloorRows.value.length,
      floorToBookCount: floorToBookRows.value.length,
      checkedAmount,
    })
  })

  function addCheckRow(name = '', direction: StocktakeDirection = 'bookToFloor'): void {
    const seq = checkRows.value.length + 1
    checkRows.value.push(createEmptyCheckRow(direction, seq, name))
    _persistCheck()
  }

  function removeCheckRow(rowId: string): void {
    const idx = checkRows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      checkRows.value.splice(idx, 1)
      checkRows.value.forEach((r, i) => { r.seq = i + 1 })
      _persistCheck()
    }
  }

  function updateCheckCell(rowId: string, field: keyof StocktakeCheckRow, value: any): void {
    const row = checkRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    const qtyFields: (keyof StocktakeCheckRow)[] = [
      'bookQty', 'sampleQty', 'clientCountQty', 'unitPrice', 'bookAmount',
    ]
    if (qtyFields.includes(field)) {
      applyQtySideEffects(row)
    }
    if (field === 'qualityStatus') {
      row.actualStatus = String(value || row.actualStatus)
    }
    _persistCheck()
  }

  function updateCheckRow(rowId: string, patch: Partial<StocktakeCheckRow>): void {
    const row = checkRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    Object.assign(row, patch)
    if (
      'bookQty' in patch || 'sampleQty' in patch || 'clientCountQty' in patch
      || 'unitPrice' in patch || 'bookAmount' in patch
    ) {
      applyQtySideEffects(row)
    }
    if (patch.qualityStatus != null) {
      row.actualStatus = patch.qualityStatus || row.actualStatus
    }
    _persistCheck()
  }

  function updateCheckMeta<K extends keyof StocktakeCheckMeta>(
    field: K,
    value: StocktakeCheckMeta[K],
  ): void {
    checkMeta.value[field] = value
    _persistMeta()
  }

  function persistCheckMeta(): void {
    _persistMeta()
  }

  /** 从 H1-9 回填现场过程空字段 */
  function syncCheckMetaFromPlan(opts?: { overwrite?: boolean }): void {
    const legacy = toLegacyPlanInfo(planForm.value)
    if (opts?.overwrite) {
      checkMeta.value = draftMetaFromPlan(createEmptyCheckMeta(), legacy)
    } else {
      checkMeta.value = draftMetaFromPlan(checkMeta.value, legacy)
    }
    _persistMeta()
  }

  function _parseDetailRows(): any[] {
    const item = allResponses.value.get('H1-2-rows')
    if (!item?.remark) return []
    try {
      const parsed = typeof item.remark === 'string' ? JSON.parse(item.remark) : item.remark
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }

  /** 从 H1-2 明细带入抽盘样本（默认账面→实物，大额优先） */
  function importCheckRowsFromDetail(opts?: {
    direction?: StocktakeDirection
    maxRows?: number
    minAmount?: number
    replace?: boolean
  }): { imported: number } {
    const detail = _parseDetailRows()
    const mapped = mapDetailRowsToCheckRows(detail, {
      direction: opts?.direction ?? 'bookToFloor',
      maxRows: opts?.maxRows ?? 50,
      minAmount: opts?.minAmount ?? 0,
    })
    if (opts?.replace) {
      checkRows.value = mapped
    } else {
      const existingKeys = new Set(
        checkRows.value.map((r) => `${r.assetNo}|${r.name}|${r.direction}`),
      )
      for (const r of mapped) {
        const key = `${r.assetNo}|${r.name}|${r.direction}`
        if (existingKeys.has(key)) continue
        checkRows.value.push({ ...r, seq: checkRows.value.length + 1 })
        existingKeys.add(key)
      }
    }
    checkRows.value.forEach((r, i) => { r.seq = i + 1 })
    _persistCheck()
    syncTotalBookCostFromDetail({ onlyIfEmpty: true })
    return { imported: mapped.length }
  }

  /** 按 H1-9 类别样本量，从 H1-2 按类别截取带入 */
  function importCheckRowsFromPlanSamples(): { imported: number } {
    const detail = _parseDetailRows()
    const scopes = planForm.value.categoryScopes || []
    if (!scopes.length) {
      return importCheckRowsFromDetail({ maxRows: 30 })
    }
    const picked: StocktakeCheckRow[] = []
    for (const sc of scopes) {
      const cat = (sc.category || '').trim()
      const qty = Number(sc.planQty) || 0
      if (!cat || qty <= 0) continue
      const inCat = detail.filter((d) => {
        const c = String(d.category ?? d.assetCategory ?? '')
        return c.includes(cat) || cat.includes(c)
      })
      const rows = mapDetailRowsToCheckRows(inCat, { maxRows: qty })
      picked.push(...rows)
    }
    if (!picked.length) return importCheckRowsFromDetail({ maxRows: 30 })
    const existingKeys = new Set(
      checkRows.value.map((r) => `${r.assetNo}|${r.name}|${r.direction}`),
    )
    let added = 0
    for (const r of picked) {
      const key = `${r.assetNo}|${r.name}|${r.direction}`
      if (existingKeys.has(key)) continue
      checkRows.value.push({ ...r, seq: checkRows.value.length + 1 })
      existingKeys.add(key)
      added++
    }
    _persistCheck()
    syncTotalBookCostFromDetail({ onlyIfEmpty: true })
    return { imported: added }
  }

  /** 原值合计从 H1-2 回填（覆盖率分母） */
  function syncTotalBookCostFromDetail(opts?: { onlyIfEmpty?: boolean }): number {
    const detail = _parseDetailRows()
    const total = sumDetailOriginalCost(detail)
    if (total <= 0) return 0
    if (opts?.onlyIfEmpty && checkMeta.value.totalBookCost != null && checkMeta.value.totalBookCost > 0) {
      return checkMeta.value.totalBookCost
    }
    checkMeta.value.totalBookCost = total
    if (!checkMeta.value.testPopulation) {
      checkMeta.value.testPopulation = `期末固定资产共 ${detail.length} 项，原值合计 ${total.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 元（来源 H1-2）`
    }
    _persistMeta()
    return total
  }

  function draftCheckConclusionLocal(): string {
    const cov = bookToFloorCoverage.value.ratioPct ?? floorToBookCoverage.value.ratioPct
    return draftCheckSheetConclusion({
      total: statistics.value.totalChecked,
      matchCount: statistics.value.matchCount,
      matchRate: statistics.value.matchRate,
      surplusCount: statistics.value.surplusCount,
      deficitCount: statistics.value.deficitCount,
      surplusAmount: statistics.value.surplusAmount,
      deficitAmount: statistics.value.deficitAmount,
      bookToFloorCount: bookToFloorRows.value.length,
      floorToBookCount: floorToBookRows.value.length,
      coveragePct: cov,
      location: checkMeta.value.location,
      countTime: checkMeta.value.countTime,
    })
  }

  function draftCheckNoteLocal(): string {
    const diffs = checkRows.value.filter((r) => calcRowDiffs(r).hasVariance)
    const concerns = collectConcernsFromCheck(checkRows.value)
    const lines = [
      `监盘地点：${checkMeta.value.location || '____'}；时间：${checkMeta.value.countTime || '____'}。`,
      `抽样方法：${checkMeta.value.samplingMethod || '____'}；特定样本：${checkMeta.value.specificSample || '无'}。`,
      `差异行 ${diffs.length} 项；品质/盘亏关注项 ${concerns.length} 项。`,
    ]
    if (diffs.length) {
      lines.push(
        '主要差异：'
        + diffs.slice(0, 5).map((r) => `${r.name || r.assetNo}（${r.result || '差异'}：${r.diffReason || '待分析'}）`).join('；'),
      )
    }
    if (concerns.length) {
      lines.push('减值/闲置线索可推送至 H1-4 / H1-14。')
    }
    return lines.join('\n')
  }

  function _persistPlanForm(): void {
    options?.onSave?.(`${ITEM_PREFIX_PLAN}-form`, planForm.value)
    const legacy = toLegacyPlanInfo(planForm.value)
    options?.onSave?.(`${ITEM_PREFIX_PLAN}-info`, legacy)
    options?.onSave?.(`${ITEM_PREFIX_PLAN}-selections`, sampleSelections.value)
  }

  function updatePlanField<K extends keyof H1StocktakePlanForm>(
    field: K,
    value: H1StocktakePlanForm[K],
  ): void {
    planForm.value[field] = value
    _persistPlanForm()
  }

  function persistPlanForm(): void {
    _persistPlanForm()
  }

  /** @deprecated 使用 updatePlanField / planForm */
  function updatePlanInfo(field: keyof StocktakePlanInfo, value: string): void {
    const map: Record<keyof StocktakePlanInfo, keyof H1StocktakePlanForm> = {
      stocktakeDate: 'plannedDate',
      location: 'locationScopeNote',
      participants: 'plannedLead',
      scope: 'methodDetail',
      method: 'method',
    }
    const k = map[field]
    if (k) (planForm.value as any)[k] = value
    _persistPlanForm()
  }

  function addSampleRow(category = ''): void {
    planForm.value.categoryScopes.push(
      newCategoryScopeRow({
        category,
        seq: planForm.value.categoryScopes.length + 1,
      }),
    )
    _persistPlanForm()
  }

  function removeSampleRow(rowId: string): void {
    planForm.value.categoryScopes = planForm.value.categoryScopes
      .filter((r) => r.rowId !== rowId)
      .map((r, i) => ({ ...r, seq: i + 1 }))
    _persistPlanForm()
  }

  function updateCategoryScope(rowId: string, patch: Partial<PlanCategoryScopeRow>): void {
    const row = planForm.value.categoryScopes.find((r) => r.rowId === rowId)
    if (!row) return
    Object.assign(row, patch)
    Object.assign(row, recalcCategoryScopeRow(row))
    _persistPlanForm()
  }

  function addPlanLocation(partial?: Partial<PlanLocationRow>): void {
    planForm.value.locations.push(
      newPlanLocationRow({ ...partial, seq: planForm.value.locations.length + 1 }),
    )
    _persistPlanForm()
  }

  function removePlanLocation(rowId: string): void {
    planForm.value.locations = planForm.value.locations
      .filter((r) => r.rowId !== rowId)
      .map((r, i) => ({ ...r, seq: i + 1 }))
    _persistPlanForm()
  }

  function draftPlanSampleQty(): void {
    const d = draftSampleQtyFromScopes(planForm.value.categoryScopes)
    if (planForm.value.sampleBookToFloorQty == null) {
      planForm.value.sampleBookToFloorQty = d.sampleBookToFloorQty
    }
    if (planForm.value.sampleFloorToBookQty == null) {
      planForm.value.sampleFloorToBookQty = d.sampleFloorToBookQty
    }
    _persistPlanForm()
  }

  /** 从 H1-2 带入类别余额（保留已有计划监盘量） */
  function importCategoryScopesFromH12(): { categories: number; locations: number } {
    const item = allResponses.value.get('H1-2-rows')
    let rows: H12DetailLike[] = []
    if (item?.remark) {
      try {
        const parsed = JSON.parse(item.remark)
        rows = Array.isArray(parsed) ? parsed : []
      } catch { rows = [] }
    }
    planForm.value.categoryScopes = aggregateH12ToCategoryScopes(rows, planForm.value.categoryScopes)
    const locNote = draftLocationScopeFromH12(rows)
    if (locNote && !planForm.value.locationScopeNote) {
      planForm.value.locationScopeNote = locNote
    }
    _persistPlanForm()
    return { categories: planForm.value.categoryScopes.length, locations: locNote ? locNote.split('、').length : 0 }
  }

  /** 从 H1-4 回填闲置说明 */
  function importIdleNoteFromH4(opts?: { overwrite?: boolean }): boolean {
    const item = allResponses.value.get('H1-4-rows')
    let rows: H14IdleLike[] = []
    if (item?.remark) {
      try {
        const parsed = JSON.parse(item.remark)
        rows = Array.isArray(parsed) ? parsed : []
      } catch { rows = [] }
    }
    const note = draftIdleNoteFromH4(rows)
    if (opts?.overwrite || !planForm.value.idleAssetsNote) {
      planForm.value.idleAssetsNote = note
      _persistPlanForm()
      return true
    }
    return false
  }

  /** 按风险档套用样本量建议 */
  function applyRiskSampleSuggestions(opts?: { overwrite?: boolean }): void {
    planForm.value = applyRiskSuggestions(planForm.value, opts)
    _persistPlanForm()
  }

  /** 本地规则生成计划结论草稿 */
  function fillPlanConclusionDraft(opts?: { overwrite?: boolean }): string {
    const draft = draftPlanConclusion(planForm.value)
    if (opts?.overwrite || !planForm.value.planConclusion) {
      planForm.value.planConclusion = draft
      _persistPlanForm()
    }
    return draft
  }

  /** 合并上年计划提示到「以前年度」分区（仅填空） */
  function mergePriorYearHints(priorForm: Partial<H1StocktakePlanForm> | null | undefined): number {
    const hints = extractPriorYearPlanHints(priorForm)
    let n = 0
    for (const [k, v] of Object.entries(hints)) {
      if (!v) continue
      const key = k as keyof H1StocktakePlanForm
      if (!planForm.value[key]) {
        ;(planForm.value as any)[key] = v
        n++
      }
    }
    if (n) _persistPlanForm()
    return n
  }

  function _persistCheck(): void {
    options?.onSave?.(`${ITEM_PREFIX_CHECK}-rows`, checkRows.value)
  }

  function _persistMeta(): void {
    options?.onSave?.(`${ITEM_PREFIX_CHECK}-meta`, checkMeta.value)
  }

  function saveSummaryNote(note: string): void {
    summaryNote.value = note
    options?.onSave?.(`${ITEM_PREFIX_SUMMARY}-note`, note)
  }

  function saveSummaryConclusion(conclusion: string): void {
    summaryConclusion.value = conclusion
    summaryForm.value.conclusion = conclusion
    options?.onSave?.(`${ITEM_PREFIX_SUMMARY}-conclusion`, conclusion)
    _persistSummaryForm()
  }

  function _persistSummaryForm(): void {
    options?.onSave?.(`${ITEM_PREFIX_SUMMARY}-form`, summaryForm.value)
  }

  function updateSummaryField<K extends keyof H1StocktakeSummaryForm>(
    field: K,
    value: H1StocktakeSummaryForm[K],
  ): void {
    summaryForm.value[field] = value
    if (field === 'conclusion') summaryConclusion.value = String(value ?? '')
    _persistSummaryForm()
  }

  function persistSummaryForm(): void {
    _persistSummaryForm()
  }

  /** 从 H1-9/H1-10 回填空字段（不覆盖已填 / 尊重 manualOverrides） */
  function syncFromUpstream(opts?: { overwrite?: boolean }): void {
    const overwrite = opts?.overwrite === true
    const f = summaryForm.value
    const p = planForm.value
    const legacy = toLegacyPlanInfo(p)
    const overrides = overwrite ? [] : (f.manualOverrides || [])

    const setIf = (key: keyof H1StocktakeSummaryForm, val: any) => {
      if (val == null || val === '') return
      if (!overwrite && overrides.includes(key as string)) return
      if (overwrite || f[key] == null || f[key] === '' || f[key] === 0) {
        ;(f as any)[key] = val
      }
    }

    setIf('actualDate', p.plannedDate || legacy.stocktakeDate)
    if (p.rollForwardMethod) setIf('bsDateNote', `监盘日与资产负债表日关系及推算：${p.rollForwardMethod}`)
    setIf('samplingMethod', buildSamplingMethodNarrative(p))
    if (p.methodDetail || p.method) {
      setIf('observationMethod', [p.method, p.methodDetail].filter(Boolean).join('：'))
    }
    if (p.specialRequirements) setIf('companySpecialNote', p.specialRequirements)
    if (!overrides.includes('companyPersonnelNote') && (overwrite || !f.companyPersonnelNote)) {
      const bits = [
        p.clientHeadcountEstimate ? `预计人数：${p.clientHeadcountEstimate}` : '',
        p.clientPlanArrange || '',
        p.icResponsible ? `负责部门/人员：${p.icResponsible}` : '',
      ].filter(Boolean)
      if (bits.length) f.companyPersonnelNote = bits.join('；')
    }

    if ((overwrite || !f.auditorPersonnel.length) && (p.plannedLead || p.mgmtCommAuditors || legacy.participants)) {
      f.auditorPersonnel = [
        newAuditorRow({
          names: p.plannedLead || p.mgmtCommAuditors || legacy.participants,
          responsibleArea: p.locationScopeNote || legacy.location || '全面',
        }),
      ]
    }

    if (!overrides.includes('locations') && (overwrite || !f.locations.length)) {
      if (p.locations.length) {
        f.locations = p.locations.map((l, i) =>
          newLocationRow({
            seq: i + 1,
            assetCategory: l.category,
            assetName: l.warehouse,
            storageLocation: l.place || l.warehouse,
          }),
        )
      } else {
        const drafted = draftLocationsFromCheckRows(checkRows.value)
        if (drafted.length) f.locations = drafted
      }
    }

    const draft = draftRecountFromCheckRows(checkRows.value)
    applyAutoSyncPatch(f, overwrite ? { ...draft } : draft, overrides)
    if (overwrite) {
      for (const [k, v] of Object.entries(draft)) (f as any)[k] = v
    }
    setIf('recountIndex', 'H1-10')
    if (!overrides.includes('recountSampleUnits') && (overwrite || f.recountSampleUnits == null) && p.sampleBookToFloorQty != null) {
      f.recountSampleUnits = p.sampleBookToFloorQty
    }
    f.lastCheckFingerprint = fingerprintCheckRows(checkRows.value)
    f.lastAutoSyncAt = new Date().toISOString()
    _persistSummaryForm()
  }

  /** H1-10 变更实时回填复盘统计等（尊重 manualOverrides） */
  function autoSyncFromCheckRows(): void {
    const fp = fingerprintCheckRows(checkRows.value)
    if (fp === summaryForm.value.lastCheckFingerprint) return
    const f = summaryForm.value
    const overrides = f.manualOverrides || []
    const patch = buildAutoSyncPatch({
      planDate: planForm.value.plannedDate || planInfo.value.stocktakeDate,
      planMethod: planForm.value.method || planInfo.value.method,
      planParticipants: planInfo.value.participants,
      planLocation: planInfo.value.location,
      checkRows: checkRows.value,
    })
    const recountOnly: Partial<H1StocktakeSummaryForm> = {}
    for (const k of [
      'recountTotalUnits', 'recountSampleUnits', 'recountCorrectUnits',
      'recountTotalAmount', 'recountSampleAmount', 'recountCorrectAmount',
    ] as const) {
      if (!overrides.includes(k) && patch[k] !== undefined) (recountOnly as any)[k] = patch[k]
    }
    applyAutoSyncPatch(f, {
      ...recountOnly,
      locations: overrides.includes('locations') ? undefined : patch.locations,
      actualDate: patch.actualDate,
    }, overrides)
    if (!overrides.includes('recountIndex')) f.recountIndex = f.recountIndex || 'H1-10'
    f.lastCheckFingerprint = fp
    f.lastAutoSyncAt = new Date().toISOString()
    _persistSummaryForm()
  }

  function markManualOverride(field: AutoSyncField | string): void {
    const list = summaryForm.value.manualOverrides || []
    if (!list.includes(field)) {
      summaryForm.value.manualOverrides = [...list, field]
      _persistSummaryForm()
    }
  }

  function clearManualOverride(field: string): void {
    summaryForm.value.manualOverrides = (summaryForm.value.manualOverrides || []).filter((x) => x !== field)
    _persistSummaryForm()
  }

  function mergeAbnormalFromCheck(): void {
    summaryForm.value.abnormalNote = mergeDiffIntoAbnormal(
      summaryForm.value.abnormalNote,
      buildDiffEvidence(checkRows.value),
    )
    _persistSummaryForm()
  }

  function draftConclusionLocal(): string {
    return draftConclusionRule({
      total: statistics.value.totalChecked,
      matchCount: statistics.value.matchCount,
      matchRate: statistics.value.matchRate,
      surplusCount: statistics.value.surplusCount,
      deficitCount: statistics.value.deficitCount,
      surplusAmount: statistics.value.surplusAmount,
      deficitAmount: statistics.value.deficitAmount,
      form: summaryForm.value,
      sampleGap: samplePlanGap.value,
    })
  }

  function applyConclusionDraft(text: string): void {
    summaryForm.value.conclusion = text
    summaryConclusion.value = text
    _persistSummaryForm()
    options?.onSave?.(`${ITEM_PREFIX_SUMMARY}-conclusion`, text)
  }

  function pushConcernsToH4H14(): { idleAdded: number; concernCount: number } {
    const concerns = collectConcernsFromCheck(checkRows.value)
    const idleItem = allResponses.value.get('H1-4-rows')
    let existingIdle: any[] = []
    if (idleItem?.remark) {
      try { existingIdle = JSON.parse(idleItem.remark) } catch { existingIdle = [] }
    }
    const { rows, added } = mergeIdleRowsFromConcerns(existingIdle, concerns, checkRows.value)
    if (added > 0 || concerns.some((c) => c.suggest === 'idle' || c.suggest === 'both')) {
      options?.onSave?.('H1-4-rows', rows)
    }
    options?.onSave?.('H1-14-stocktake-concerns', {
      updatedAt: new Date().toISOString(),
      items: concerns.filter((c) => c.suggest === 'impairment' || c.suggest === 'both'),
    })
    options?.onSave?.(`${ITEM_PREFIX_SUMMARY}-pushed-concerns`, {
      updatedAt: new Date().toISOString(),
      items: concerns,
    })
    return { idleAdded: added, concernCount: concerns.length }
  }

  function syncOcrToH116(ocrData: Record<string, any>): { mode: 'update' | 'add' } {
    const item = allResponses.value.get('H1-16-rows')
    let existing: any[] = []
    if (item?.remark) {
      try { existing = JSON.parse(item.remark) } catch { existing = [] }
    }
    const { rows, mode } = mergeBuildingFromOcr(existing, ocrData)
    options?.onSave?.('H1-16-rows', rows)
    return { mode }
  }

  function getExportSnapshot(): Record<string, string | number>[] {
    return buildExportRows(summaryForm.value, {
      totalCount: statistics.value.totalChecked,
      matchCount: statistics.value.matchCount,
      surplusCount: statistics.value.surplusCount,
      shortageCount: statistics.value.deficitCount,
      matchRate: Math.round(statistics.value.matchRate),
    })
  }

  function addLocation(partial?: Partial<SummaryLocationRow>): void {
    const row = newLocationRow({ ...partial, seq: summaryForm.value.locations.length + 1 })
    summaryForm.value.locations.push(row)
    _persistSummaryForm()
  }

  function removeLocation(rowId: string): void {
    summaryForm.value.locations = summaryForm.value.locations
      .filter((r) => r.rowId !== rowId)
      .map((r, i) => ({ ...r, seq: i + 1 }))
    _persistSummaryForm()
  }

  function addClientPersonnel(partial?: Partial<SummaryPersonnelRow>): void {
    summaryForm.value.clientPersonnel.push(
      newClientPersonnelRow({ ...partial, seq: summaryForm.value.clientPersonnel.length + 1 }),
    )
    _persistSummaryForm()
  }

  function removeClientPersonnel(rowId: string): void {
    summaryForm.value.clientPersonnel = summaryForm.value.clientPersonnel
      .filter((r) => r.rowId !== rowId)
      .map((r, i) => ({ ...r, seq: i + 1 }))
    _persistSummaryForm()
  }

  function addAuditorPersonnel(partial?: Partial<SummaryAuditorRow>): void {
    summaryForm.value.auditorPersonnel.push(
      newAuditorRow({ ...partial, seq: summaryForm.value.auditorPersonnel.length + 1 }),
    )
    _persistSummaryForm()
  }

  function removeAuditorPersonnel(rowId: string): void {
    summaryForm.value.auditorPersonnel = summaryForm.value.auditorPersonnel
      .filter((r) => r.rowId !== rowId)
      .map((r, i) => ({ ...r, seq: i + 1 }))
    _persistSummaryForm()
  }

  const recountRates = computed(() => calcRecountRates(summaryForm.value))

  const timeRangeOk = computed(() =>
    isTimeRangeValid(summaryForm.value.startTime, summaryForm.value.endTime),
  )

  const samplePlanGap = computed(() => {
    const plannedDirect =
      (Number(planForm.value.sampleBookToFloorQty) || 0)
      + (Number(planForm.value.sampleFloorToBookQty) || 0)
    const fromScopes = sampleSelections.value.reduce((s, r) => s + (Number(r.sampleSize) || 0), 0)
    const planned = plannedDirect > 0 ? plannedDirect : fromScopes
    return calcSamplePlanGap(
      planned > 0 ? [{ sampleSize: planned }] : sampleSelections.value,
      statistics.value.totalChecked,
    )
  })

  const diffEvidence = computed(() => buildDiffEvidence(checkRows.value))

  const completeness = computed(() =>
    evaluateCompleteness({
      form: summaryForm.value,
      matchRate: statistics.value.matchRate,
      deficitRows: deficitRows.value,
      checkTotal: statistics.value.totalChecked,
    }),
  )

  const completenessOk = computed(() => completeness.value.every((c) => c.ok))

  const logicWarnings = computed(() => {
    const warnings: string[] = []
    const s = statistics.value
    if (s.totalChecked === 0) warnings.push('H1-10 尚无盘点检查记录，小结统计为空')
    if (s.totalChecked > 0 && s.matchRate < 95) {
      warnings.push(`账实相符率 ${s.matchRate.toFixed(1)}% 低于 95%，需追查差异原因并在异常说明中披露`)
    }
    if (s.deficitCount > 0) warnings.push(`存在盘亏 ${s.deficitCount} 项，评估对固定资产余额真实性的影响`)
    if (!timeRangeOk.value) warnings.push('实际盘点结束时间须晚于开始时间')
    const rates = recountRates.value
    if (rates.unitCoverage != null && rates.unitCoverage < 5) {
      warnings.push('复盘数量覆盖率偏低，请按审计准则评估样本量是否充分')
    }
    const unfinishedPre = summaryForm.value.precheckItems.filter((p) => !p.obtained)
    if (unfinishedPre.length) warnings.push(`盘点前检查程序尚有 ${unfinishedPre.length} 项未勾选`)
    if (!samplePlanGap.value.ok) warnings.push(samplePlanGap.value.message)
    for (const w of planVsCheckWarnings.value) warnings.push(w)
    if (bookToFloorRows.value.length === 0) {
      warnings.push('尚未填写「账面→实物」抽盘明细（存在性）')
    }
    if (floorToBookRows.value.length === 0) {
      warnings.push('尚未填写「实物→账面」抽盘明细（完整性）')
    }
    if (checkMeta.value.totalBookCost == null || checkMeta.value.totalBookCost <= 0) {
      warnings.push('未填写固定资产原值合计，无法计算抽盘覆盖率')
    }
    return warnings
  })

  watch(allResponses, () => _loadData(), { immediate: true })
  watch(checkRows, () => { autoSyncFromCheckRows() }, { deep: true })

  return {
    // Plan (H1-9)
    planForm,
    planInfo,
    sampleSelections,
    planScopeTotals,
    planLogicWarnings,
    planGateBlockers,
    planReadyForCheck,
    riskSuggestion,
    planVsCheckWarnings,
    updatePlanField,
    persistPlanForm,
    updatePlanInfo,
    addSampleRow,
    removeSampleRow,
    updateCategoryScope,
    addPlanLocation,
    removePlanLocation,
    draftPlanSampleQty,
    importCategoryScopesFromH12,
    importIdleNoteFromH4,
    applyRiskSampleSuggestions,
    fillPlanConclusionDraft,
    mergePriorYearHints,
    // Check (H1-10)
    checkRows,
    checkMeta,
    bookToFloorRows,
    floorToBookRows,
    bookToFloorCoverage,
    floorToBookCoverage,
    addCheckRow,
    removeCheckRow,
    updateCheckCell,
    updateCheckRow,
    updateCheckMeta,
    persistCheckMeta,
    syncCheckMetaFromPlan,
    importCheckRowsFromDetail,
    importCheckRowsFromPlanSamples,
    syncTotalBookCostFromDetail,
    draftCheckConclusionLocal,
    draftCheckNoteLocal,
    rowDiffs: calcRowDiffs,
    // Summary (H1-11)
    summaryNote,
    summaryConclusion,
    summaryForm,
    saveSummaryNote,
    saveSummaryConclusion,
    updateSummaryField,
    persistSummaryForm,
    syncFromUpstream,
    autoSyncFromCheckRows,
    markManualOverride,
    clearManualOverride,
    mergeAbnormalFromCheck,
    draftConclusionLocal,
    applyConclusionDraft,
    pushConcernsToH4H14,
    syncOcrToH116,
    getExportSnapshot,
    addLocation,
    removeLocation,
    addClientPersonnel,
    removeClientPersonnel,
    addAuditorPersonnel,
    removeAuditorPersonnel,
    recountRates,
    timeRangeOk,
    logicWarnings,
    samplePlanGap,
    diffEvidence,
    completeness,
    completenessOk,
    statistics,
    surplusRows,
    deficitRows,
  }
}

export default useH1Stocktake
