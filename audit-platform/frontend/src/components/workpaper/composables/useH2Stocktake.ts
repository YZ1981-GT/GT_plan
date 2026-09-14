/**
 * useH2Stocktake — H2-12~14 监盘组 composable
 *
 * H2-12 对齐致同「在建工程监盘计划」并参照 H1-9：
 * 风险 → 了解状况/内控/以前年度 → 胜任能力 → 计划安排 → 结论
 * H2-13 对齐致同「在建工程盘点检查表」并参照 H1-10：
 * 目标 → 样本 → 现场过程 → 双向抽盘 + 三数量差异 → 进度/转固/停工 → 说明/结论
 * 停工线索与 H2-15 减值联动；账面金额可从 H2-2 带入
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  applyQtySideEffects,
  calcDirectionCoverage,
  calcRowDiffs,
  createEmptyCheckMeta,
  createEmptyCheckRow,
  draftCheckSheetConclusion,
  draftCheckSheetNote,
  draftMetaFromPlan,
  isStoppedCheckRow,
  mapDetailRowsToCheckRows,
  normalizeCheckMeta,
  normalizeCheckRow,
  sumDetailCipCost,
  type H2StocktakeCheckMeta,
  type H2StocktakeCheckRow,
  type StocktakeDirection,
} from './h2StocktakeCheckModel'
import {
  calcCategoryScopeTotals,
  createEmptyPlanForm,
  draftSampleQtyFromScopes,
  newCategoryScopeRow,
  newMajorProjectRow,
  newSelectedProject,
  normalizePlanForm,
  recalcCategoryScopeRow,
  recalcMajorProjectRow,
  toLegacyPlan,
  type H2LegacyStocktakePlan,
  type H2StocktakePlanForm,
  type PlanCategoryScopeRow,
  type PlanMajorProjectRow,
  type StocktakeProjectSelection,
} from './h2StocktakePlanModel'
import {
  aggregateH22ToCategoryScopes,
  applyRiskSuggestions,
  calcPlanLogicWarningsEnhanced,
  calcPlanVsCheckWarnings,
  draftEndingBalanceNoteFromH22,
  draftLocationScopeFromH22,
  draftMajorProjectsFromH22,
  draftPlanConclusion,
  draftSelectedProjectsFromMajor,
  extractPriorYearPlanHints,
  getPlanGateBlockers,
  isPlanReadyForCheck,
  suggestCoverageByRisk,
} from './h2StocktakePlanEnhance'

export type {
  H2StocktakeCheckMeta,
  H2StocktakeCheckRow,
  StocktakeDirection,
  H2StocktakePlanForm,
  StocktakeProjectSelection,
  H2LegacyStocktakePlan,
}
export { isStoppedCheckRow }

/** @deprecated 兼容旧五字段；新逻辑请用 planForm */
export type H2StocktakePlan = H2LegacyStocktakePlan

export interface H2StocktakeSummary {
  overallSituation: string
  abnormalProjects: StocktakeAbnormalItem[]
  conclusion: string
  preparedBy: string
  preparedDate: string
}

export interface StocktakeAbnormalItem {
  rowId: string
  name: string
  abnormalType: string
  description: string
  suggestion: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const PLAN_KEY = 'H2-12-plan'
const CHECK_ROWS_KEY = 'H2-13-rows'
const CHECK_META_KEY = 'H2-13-meta'
const SUMMARY_KEY = 'H2-14-summary'
const NOTE_KEY = 'H2-stocktake-audit-note'
const DETAIL_ROWS_KEY = 'H2-2-rows'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2Stocktake(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  phase?: 'plan' | 'check' | 'summary'
  onSave?: (itemId: string, value: any) => void
}) {
  const planForm = ref<H2StocktakePlanForm>(createEmptyPlanForm())
  /** 兼容旧 UI / H2-13：由完整计划表推导 */
  const plan = computed<H2LegacyStocktakePlan>(() => toLegacyPlan(planForm.value))

  const checkRows = ref<H2StocktakeCheckRow[]>([])
  const checkMeta = ref<H2StocktakeCheckMeta>(createEmptyCheckMeta())

  const summary = ref<H2StocktakeSummary>({
    overallSituation: '',
    abnormalProjects: [],
    conclusion: '',
    preparedBy: '',
    preparedDate: '',
  })

  const auditNote = ref('')

  function _getJson(itemId: string): any {
    const item = options.allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    if (typeof raw === 'object') return raw
    try { return JSON.parse(raw) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = options.allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _getDetailRows(): any[] {
    const data = _getJson(DETAIL_ROWS_KEY)
    return Array.isArray(data) ? data : []
  }

  function initFromAllResponses(): void {
    const planData = _getJson(PLAN_KEY)
    if (planData && typeof planData === 'object') {
      planForm.value = normalizePlanForm(planData)
    }

    const checkData = _getJson(CHECK_ROWS_KEY)
    if (Array.isArray(checkData)) {
      checkRows.value = checkData.map((r: any, i: number) => normalizeCheckRow(r, i))
    } else {
      checkRows.value = []
    }

    const metaData = _getJson(CHECK_META_KEY)
    checkMeta.value = normalizeCheckMeta(metaData)

    const summaryData = _getJson(SUMMARY_KEY)
    if (summaryData && typeof summaryData === 'object') {
      summary.value = {
        overallSituation: summaryData.overallSituation ?? '',
        abnormalProjects: Array.isArray(summaryData.abnormalProjects)
          ? summaryData.abnormalProjects.map((a: any) => ({
              rowId: a.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
              name: a.name ?? '',
              abnormalType: a.abnormalType ?? '',
              description: a.description ?? '',
              suggestion: a.suggestion ?? '',
            }))
          : [],
        conclusion: summaryData.conclusion ?? '',
        preparedBy: summaryData.preparedBy ?? '',
        preparedDate: summaryData.preparedDate ?? '',
      }
    }

    auditNote.value = _getString(NOTE_KEY)
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  // ─── Computed ──────────────────────────────────────────────────────────────

  const bookToFloorRows = computed(() =>
    checkRows.value.filter((r) => r.direction === 'bookToFloor'),
  )
  const floorToBookRows = computed(() =>
    checkRows.value.filter((r) => r.direction === 'floorToBook'),
  )

  const bookToFloorCoverage = computed(() =>
    calcDirectionCoverage(bookToFloorRows.value, checkMeta.value.totalBookCost),
  )
  const floorToBookCoverage = computed(() =>
    calcDirectionCoverage(floorToBookRows.value, checkMeta.value.totalBookCost),
  )

  const stoppedProjects: ComputedRef<H2StocktakeCheckRow[]> = computed(() =>
    checkRows.value.filter(isStoppedCheckRow),
  )
  const stoppedProjectNames: ComputedRef<string[]> = computed(() =>
    stoppedProjects.value.map((r) => r.name).filter(Boolean),
  )

  const readyForUseProjects = computed(() =>
    checkRows.value.filter((r) => r.readyForUse === '是'),
  )

  const checkStats = computed(() => {
    const total = checkRows.value.length
    const matchCount = checkRows.value.filter((r) => r.result === '账实相符').length
    const surplusCount = checkRows.value.filter((r) => r.result === '盘盈').length
    const deficitCount = checkRows.value.filter((r) => r.result === '盘亏').length
    const varianceCount = checkRows.value.filter((r) => calcRowDiffs(r).hasVariance).length
    return {
      total,
      inProgress: checkRows.value.filter((r) => r.constructionStatus === '施工中').length,
      stopped: stoppedProjects.value.length,
      completed: checkRows.value.filter((r) => r.constructionStatus === '完工' || r.readyForUse === '是').length,
      matchCount,
      surplusCount,
      deficitCount,
      varianceCount,
      matchRate: total > 0 ? (matchCount / total) * 100 : 0,
      readyForUseCount: readyForUseProjects.value.length,
    }
  })

  const planScopeTotals = computed(() => calcCategoryScopeTotals(planForm.value.categoryScopes))
  const planLogicWarnings = computed(() => calcPlanLogicWarningsEnhanced(planForm.value))
  const planGateBlockers = computed(() => getPlanGateBlockers(planForm.value))
  const planReadyForCheck = computed(() => isPlanReadyForCheck(planForm.value))
  const riskSuggestion = computed(() => suggestCoverageByRisk(planForm.value.existenceRiskLevel))
  const planVsCheckWarnings = computed(() => {
    const checkedAmount = checkRows.value.reduce((s, r) => s + (Number(r.bookAmount) || 0), 0)
    return calcPlanVsCheckWarnings(planForm.value, {
      bookToFloorCount: bookToFloorRows.value.length,
      floorToBookCount: floorToBookRows.value.length,
      checkedAmount,
    })
  })

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistPlanForm(): void {
    options.onSave?.(PLAN_KEY, planForm.value)
  }

  function _persistCheck(): void {
    options.onSave?.(CHECK_ROWS_KEY, checkRows.value.map((r) => ({
      rowId: r.rowId,
      seq: r.seq,
      direction: r.direction,
      name: r.name,
      projectName: r.name, // 兼容导入导出 / 减值旧键
      assetNo: r.assetNo,
      projectCode: r.assetNo,
      location: r.location,
      siteLocation: r.location,
      unit: r.unit,
      unitPrice: r.unitPrice,
      bookQty: r.bookQty,
      bookAmount: r.bookAmount,
      bookValue: r.bookAmount,
      clientCountQty: r.clientCountQty,
      sampleQty: r.sampleQty,
      result: r.result,
      stocktakeResult: r.result,
      diffReason: r.diffReason,
      diffAmount: r.diffAmount,
      progressDesc: r.progressDesc,
      readyForUse: r.readyForUse,
      stopDuration: r.stopDuration,
      stopReason: r.stopReason,
      constructionStatus: r.constructionStatus,
      isStopped: isStoppedCheckRow(r) ? '是' : '否',
      visibleProgress: r.visibleProgress,
      remark: r.remark,
      checker: r.checker,
      photoUrl: r.photoUrl,
      photos: r.photoUrl,
      // 兼容旧 UI 残留字段（读时已归一，写回空串避免丢键）
      progressDifference: r.progressDesc,
      auditConclusion: r.result,
    })))
  }

  function _persistMeta(): void {
    options.onSave?.(CHECK_META_KEY, checkMeta.value)
  }

  // ─── Actions: Plan ─────────────────────────────────────────────────────────

  function persistPlanForm(): void {
    if (options.isReadonly.value) return
    _persistPlanForm()
  }

  /** @deprecated 兼容旧调用；优先 persistPlanForm / 直接改 planForm */
  function updatePlan(field: keyof H2LegacyStocktakePlan | keyof H2StocktakePlanForm, value: any): void {
    if (options.isReadonly.value) return
    const legacyMap: Record<string, keyof H2StocktakePlanForm> = {
      inspectionDate: 'plannedDate',
      location: 'locationScopeNote',
      participants: 'plannedLead',
      scope: 'methodDetail',
      schedule: 'plannedTimeNote',
    }
    const key = (legacyMap[field as string] || field) as keyof H2StocktakePlanForm
    if (key === 'selectedProjects') {
      planForm.value.selectedProjects = Array.isArray(value) ? value : []
    } else {
      ;(planForm.value as any)[key] = value
    }
    _persistPlanForm()
  }

  function addPlanProject(name: string): void {
    if (options.isReadonly.value) return
    planForm.value.selectedProjects.push(newSelectedProject({
      name: name || '',
    }))
    _persistPlanForm()
  }

  function removePlanProject(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = planForm.value.selectedProjects.findIndex((p) => p.rowId === rowId)
    if (idx !== -1) {
      planForm.value.selectedProjects.splice(idx, 1)
      _persistPlanForm()
    }
  }

  function addCategoryScope(partial?: Partial<PlanCategoryScopeRow>): void {
    if (options.isReadonly.value) return
    planForm.value.categoryScopes.push(
      newCategoryScopeRow({ ...partial, seq: planForm.value.categoryScopes.length + 1 }),
    )
    _persistPlanForm()
  }

  function removeCategoryScope(rowId: string): void {
    if (options.isReadonly.value) return
    planForm.value.categoryScopes = planForm.value.categoryScopes
      .filter((r) => r.rowId !== rowId)
      .map((r, i) => ({ ...r, seq: i + 1 }))
    _persistPlanForm()
  }

  function updateCategoryScope(rowId: string, patch: Partial<PlanCategoryScopeRow>): void {
    if (options.isReadonly.value) return
    const row = planForm.value.categoryScopes.find((r) => r.rowId === rowId)
    if (!row) return
    Object.assign(row, recalcCategoryScopeRow({ ...row, ...patch }))
    _persistPlanForm()
  }

  function addMajorProject(partial?: Partial<PlanMajorProjectRow>): void {
    if (options.isReadonly.value) return
    planForm.value.majorProjects.push(
      newMajorProjectRow({ ...partial, seq: planForm.value.majorProjects.length + 1 }),
    )
    _persistPlanForm()
  }

  function removeMajorProject(rowId: string): void {
    if (options.isReadonly.value) return
    planForm.value.majorProjects = planForm.value.majorProjects
      .filter((r) => r.rowId !== rowId)
      .map((r, i) => ({ ...r, seq: i + 1 }))
    _persistPlanForm()
  }

  function updateMajorProject(rowId: string, patch: Partial<PlanMajorProjectRow>): void {
    if (options.isReadonly.value) return
    const row = planForm.value.majorProjects.find((r) => r.rowId === rowId)
    if (!row) return
    Object.assign(row, recalcMajorProjectRow({ ...row, ...patch }))
    _persistPlanForm()
  }

  function draftPlanSampleQty(): void {
    if (options.isReadonly.value) return
    const d = draftSampleQtyFromScopes(planForm.value.categoryScopes)
    if (planForm.value.sampleBookToFloorQty == null) {
      planForm.value.sampleBookToFloorQty = d.sampleBookToFloorQty
    }
    if (planForm.value.sampleFloorToBookQty == null) {
      planForm.value.sampleFloorToBookQty = d.sampleFloorToBookQty
    }
    _persistPlanForm()
  }

  function importFromH22(opts?: { seedSelected?: boolean }): {
    categories: number
    majors: number
    locations: number
  } {
    if (options.isReadonly.value) return { categories: 0, majors: 0, locations: 0 }
    const detail = _getDetailRows()
    if (!detail.length) return { categories: 0, majors: 0, locations: 0 }

    planForm.value.categoryScopes = aggregateH22ToCategoryScopes(detail, planForm.value.categoryScopes)
    const majors = draftMajorProjectsFromH22(detail)
    if (majors.length) planForm.value.majorProjects = majors

    const note = draftEndingBalanceNoteFromH22(detail)
    if (note && !planForm.value.endingBalanceNote) planForm.value.endingBalanceNote = note

    const locNote = draftLocationScopeFromH22(detail)
    if (locNote && !planForm.value.locationScopeNote) planForm.value.locationScopeNote = locNote

    if (opts?.seedSelected !== false && !planForm.value.selectedProjects.length && majors.length) {
      planForm.value.selectedProjects = draftSelectedProjectsFromMajor(majors)
    }

    _persistPlanForm()
    return {
      categories: planForm.value.categoryScopes.length,
      majors: planForm.value.majorProjects.length,
      locations: locNote ? locNote.split('、').length : 0,
    }
  }

  function applyRiskSampleSuggestions(opts?: { overwrite?: boolean }): void {
    if (options.isReadonly.value) return
    planForm.value = applyRiskSuggestions(planForm.value, opts)
    _persistPlanForm()
  }

  function fillPlanConclusionDraft(opts?: { overwrite?: boolean }): void {
    if (options.isReadonly.value) return
    const draft = draftPlanConclusion(planForm.value)
    if (opts?.overwrite || !planForm.value.planConclusion) {
      planForm.value.planConclusion = draft
      _persistPlanForm()
    }
  }

  function mergePriorYearHints(priorForm: Partial<H2StocktakePlanForm> | null | undefined): number {
    if (options.isReadonly.value) return 0
    const hints = extractPriorYearPlanHints(priorForm)
    let n = 0
    for (const [key, v] of Object.entries(hints) as [keyof H2StocktakePlanForm, any][]) {
      if (v && !planForm.value[key]) {
        ;(planForm.value as any)[key] = v
        n++
      }
    }
    if (n) _persistPlanForm()
    return n
  }

  // ─── Actions: Check meta / rows ────────────────────────────────────────────

  function updateCheckMeta(field: keyof H2StocktakeCheckMeta, value: any): void {
    if (options.isReadonly.value) return
    if (field === 'totalBookCost') {
      checkMeta.value.totalBookCost = value == null || value === '' ? null : Number(value) || 0
    } else {
      ;(checkMeta.value as any)[field] = String(value ?? '')
    }
    _persistMeta()
  }

  function syncCheckMetaFromPlan(): void {
    if (options.isReadonly.value) return
    checkMeta.value = draftMetaFromPlan(checkMeta.value, plan.value)
    _persistMeta()
  }

  function addCheckRow(name: string, direction: StocktakeDirection = 'bookToFloor'): void {
    if (options.isReadonly.value) return
    const seq = checkRows.value.filter((r) => r.direction === direction).length + 1
    checkRows.value.push(createEmptyCheckRow(direction, seq, name || ''))
    _persistCheck()
  }

  function removeCheckRow(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = checkRows.value.findIndex((r) => r.rowId === rowId)
    if (idx !== -1) {
      checkRows.value.splice(idx, 1)
      _persistCheck()
    }
  }

  function updateCheckRow(rowId: string, patch: Partial<H2StocktakeCheckRow> | string, value?: any): void {
    if (options.isReadonly.value) return
    const row = checkRows.value.find((r) => r.rowId === rowId)
    if (!row) return

    // 兼容旧签名 updateCheckRow(rowId, field, value)
    if (typeof patch === 'string') {
      const field = patch
      if (field === 'visibleProgress') {
        row.visibleProgress = value != null && value !== '' ? Number(value) : null
      } else if (['unitPrice', 'bookQty', 'bookAmount', 'clientCountQty', 'sampleQty', 'diffAmount'].includes(field)) {
        ;(row as any)[field] = value != null && value !== '' ? Number(value) : 0
      } else {
        ;(row as any)[field] = value ?? ''
      }
    } else {
      Object.assign(row, patch)
    }

    applyQtySideEffects(row)
    _persistCheck()
  }

  function importCheckRowsFromDetail(opts?: { maxRows?: number }): { imported: number } {
    if (options.isReadonly.value) return { imported: 0 }
    const detail = _getDetailRows().filter((d) => d && !String(d.name ?? '').includes('合计'))
    const mapped = mapDetailRowsToCheckRows(detail, {
      direction: 'bookToFloor',
      maxRows: opts?.maxRows ?? 50,
    })
    const existing = new Set(checkRows.value.map((r) => r.name.trim()).filter(Boolean))
    let imported = 0
    for (const row of mapped) {
      if (existing.has(row.name.trim())) continue
      checkRows.value.push(row)
      existing.add(row.name.trim())
      imported++
    }
    if (imported) _persistCheck()
    return { imported }
  }

  function importCheckRowsFromPlan(): { imported: number } {
    if (options.isReadonly.value) return { imported: 0 }
    const detail = _getDetailRows()
    const detailByName = new Map(
      detail.map((d) => [String(d.name ?? '').trim(), d]),
    )
    const existing = new Set(checkRows.value.map((r) => r.name.trim()).filter(Boolean))
    let imported = 0
    let seq = bookToFloorRows.value.length
    for (const p of planForm.value.selectedProjects) {
      const name = String(p.name ?? '').trim()
      if (!name || existing.has(name)) continue
      seq++
      const row = createEmptyCheckRow('bookToFloor', seq, name)
      const d = detailByName.get(name)
      if (d) {
        row.bookAmount = Number(d.cipEnd ?? d.endAudited ?? d.netValue ?? 0) || 0
        row.bookQty = 1
        row.unitPrice = row.bookAmount
        row.assetNo = String(d.contractNo ?? '')
        row.visibleProgress = d.completionRate != null ? Number(d.completionRate) : null
        if (row.visibleProgress != null) {
          row.progressDesc = `账面完工进度约 ${row.visibleProgress}%`
        }
        row.remark = `来源:H2-12；选取原因:${p.reason || '—'}`
      } else {
        row.remark = `来源:H2-12；选取原因:${p.reason || '—'}`
      }
      checkRows.value.push(row)
      existing.add(name)
      imported++
    }
    if (imported) _persistCheck()
    return { imported }
  }

  function syncTotalBookCostFromDetail(): number {
    if (options.isReadonly.value) return checkMeta.value.totalBookCost ?? 0
    const detail = _getDetailRows().filter((d) => d && !String(d.name ?? '').includes('合计'))
    const total = sumDetailCipCost(detail)
    if (total <= 0) return checkMeta.value.totalBookCost ?? 0
    checkMeta.value.totalBookCost = total
    if (!checkMeta.value.testPopulation) {
      checkMeta.value.testPopulation =
        `期末在建工程共 ${detail.length} 项，成本合计 ${total.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 元（来源 H2-2）`
    }
    _persistMeta()
    return total
  }

  function draftCheckNoteLocal(): string {
    return draftCheckSheetNote({
      location: checkMeta.value.location,
      countTime: checkMeta.value.countTime,
      samplingMethod: checkMeta.value.samplingMethod,
      specificSample: checkMeta.value.specificSample,
      varianceCount: checkStats.value.varianceCount,
      stoppedCount: checkStats.value.stopped,
      readyForUseCount: checkStats.value.readyForUseCount,
    })
  }

  function draftCheckConclusionLocal(): string {
    const cov = bookToFloorCoverage.value.ratioPct ?? floorToBookCoverage.value.ratioPct
    return draftCheckSheetConclusion({
      total: checkStats.value.total,
      matchCount: checkStats.value.matchCount,
      matchRate: checkStats.value.matchRate,
      surplusCount: checkStats.value.surplusCount,
      deficitCount: checkStats.value.deficitCount,
      stoppedCount: checkStats.value.stopped,
      readyForUseCount: checkStats.value.readyForUseCount,
      bookToFloorCount: bookToFloorRows.value.length,
      floorToBookCount: floorToBookRows.value.length,
      coveragePct: cov,
      location: checkMeta.value.location,
      countTime: checkMeta.value.countTime,
    })
  }

  // ─── Actions: Summary ──────────────────────────────────────────────────────

  function updateSummary(field: keyof H2StocktakeSummary, value: any): void {
    if (options.isReadonly.value) return
    if (field === 'abnormalProjects') {
      summary.value.abnormalProjects = Array.isArray(value) ? value : []
    } else {
      ;(summary.value as any)[field] = String(value ?? '')
    }
    options.onSave?.(SUMMARY_KEY, summary.value)
  }

  function addAbnormalProject(name: string): void {
    if (options.isReadonly.value) return
    summary.value.abnormalProjects.push({
      rowId: `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      name,
      abnormalType: '',
      description: '',
      suggestion: '',
    })
    options.onSave?.(SUMMARY_KEY, summary.value)
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  return {
    plan,
    planForm,
    planScopeTotals,
    planLogicWarnings,
    planGateBlockers,
    planReadyForCheck,
    riskSuggestion,
    planVsCheckWarnings,
    checkRows,
    checkMeta,
    summary,
    auditNote,
    bookToFloorRows,
    floorToBookRows,
    bookToFloorCoverage,
    floorToBookCoverage,
    stoppedProjects,
    stoppedProjectNames,
    readyForUseProjects,
    checkStats,
    updatePlan,
    persistPlanForm,
    addPlanProject,
    removePlanProject,
    addCategoryScope,
    removeCategoryScope,
    updateCategoryScope,
    addMajorProject,
    removeMajorProject,
    updateMajorProject,
    draftPlanSampleQty,
    importFromH22,
    applyRiskSampleSuggestions,
    fillPlanConclusionDraft,
    mergePriorYearHints,
    updateCheckMeta,
    syncCheckMetaFromPlan,
    addCheckRow,
    removeCheckRow,
    updateCheckRow,
    importCheckRowsFromDetail,
    importCheckRowsFromPlan,
    syncTotalBookCostFromDetail,
    draftCheckNoteLocal,
    draftCheckConclusionLocal,
    updateSummary,
    addAbnormalProject,
    saveNote,
    initFromAllResponses,
  }
}

export default useH2Stocktake
