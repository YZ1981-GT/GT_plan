/**
 * useH2Stocktake — H2-12~14 监盘组 composable
 *
 * 计划/检查/小结三阶段共用状态
 * FixedAssetStocktakeDialog集成
 * 停工迹象自动标记 + 与H2-15减值联动
 *
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Task: 3.13
 * Requirements: 11.1-11.6
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H2-12 监盘计划 */
export interface H2StocktakePlan {
  /** 踏勘日期 */
  inspectionDate: string
  /** 工程地点 */
  location: string
  /** 参与人员 */
  participants: string
  /** 踏勘范围 */
  scope: string
  /** 选取的工程列表 */
  selectedProjects: StocktakeProjectSelection[]
  /** 时间安排 */
  schedule: string
}

export interface StocktakeProjectSelection {
  rowId: string
  name: string
  reason: string
  plannedContent: string
}

/** H2-13 盘点检查表 */
export interface H2StocktakeCheckRow {
  rowId: string
  /** 工程名称 */
  name: string
  /** 现场位置 */
  siteLocation: string
  /** 形象进度(%) */
  visibleProgress: number | null
  /** 施工状态 */
  constructionStatus: '施工中' | '停工' | '完工' | ''
  /** 施工人员情况 */
  workers: string
  /** 材料堆存 */
  materialStorage: string
  /** 设备状况 */
  equipmentCondition: string
  /** 安全措施 */
  safetyMeasures: string
  /** 工程质量观感 */
  qualityAppearance: string
  /** 照片附件 */
  photos: string
  /** 与账面进度差异 */
  progressDifference: string
  /** 审计结论 */
  auditConclusion: string
  /** 备注 */
  remark: string
}

/** H2-14 监盘小结 */
export interface H2StocktakeSummary {
  /** 踏勘总体情况 */
  overallSituation: string
  /** 异常工程清单 */
  abnormalProjects: StocktakeAbnormalItem[]
  /** 监盘结论 */
  conclusion: string
  /** 编制人 */
  preparedBy: string
  /** 编制日期 */
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
const SUMMARY_KEY = 'H2-14-summary'
const NOTE_KEY = 'H2-stocktake-audit-note'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2Stocktake(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  /** 当前阶段（plan/check/summary），仅用于组件侧标识 */
  phase?: 'plan' | 'check' | 'summary'
  onSave?: (itemId: string, value: any) => void
}) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const plan = ref<H2StocktakePlan>({
    inspectionDate: '',
    location: '',
    participants: '',
    scope: '',
    selectedProjects: [],
    schedule: '',
  })

  const checkRows = ref<H2StocktakeCheckRow[]>([])

  const summary = ref<H2StocktakeSummary>({
    overallSituation: '',
    abnormalProjects: [],
    conclusion: '',
    preparedBy: '',
    preparedDate: '',
  })

  const auditNote = ref('')

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = options.allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = options.allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  function initFromAllResponses(): void {
    // H2-12 计划
    const planData = _getJson(PLAN_KEY)
    if (planData && typeof planData === 'object') {
      plan.value = {
        inspectionDate: planData.inspectionDate ?? '',
        location: planData.location ?? '',
        participants: planData.participants ?? '',
        scope: planData.scope ?? '',
        selectedProjects: Array.isArray(planData.selectedProjects)
          ? planData.selectedProjects.map((p: any) => ({
              rowId: p.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
              name: p.name ?? '',
              reason: p.reason ?? '',
              plannedContent: p.plannedContent ?? '',
            }))
          : [],
        schedule: planData.schedule ?? '',
      }
    }

    // H2-13 检查表
    const checkData = _getJson(CHECK_ROWS_KEY)
    if (Array.isArray(checkData)) {
      checkRows.value = checkData.map((r: any) => ({
        rowId: r.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
        name: r.name ?? '',
        siteLocation: r.siteLocation ?? '',
        visibleProgress: r.visibleProgress != null ? Number(r.visibleProgress) : null,
        constructionStatus: r.constructionStatus ?? '',
        workers: r.workers ?? '',
        materialStorage: r.materialStorage ?? '',
        equipmentCondition: r.equipmentCondition ?? '',
        safetyMeasures: r.safetyMeasures ?? '',
        qualityAppearance: r.qualityAppearance ?? '',
        photos: r.photos ?? '',
        progressDifference: r.progressDifference ?? '',
        auditConclusion: r.auditConclusion ?? '',
        remark: r.remark ?? '',
      }))
    } else {
      checkRows.value = []
    }

    // H2-14 小结
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

  /** 停工工程列表（红色高亮,与H2-15减值联动） */
  const stoppedProjects: ComputedRef<H2StocktakeCheckRow[]> = computed(() =>
    checkRows.value.filter(r => r.constructionStatus === '停工'),
  )

  /** 停工工程名称列表（供H2-15取数） */
  const stoppedProjectNames: ComputedRef<string[]> = computed(() =>
    stoppedProjects.value.map(r => r.name),
  )

  /** 检查完成统计 */
  const checkStats = computed(() => ({
    total: checkRows.value.length,
    inProgress: checkRows.value.filter(r => r.constructionStatus === '施工中').length,
    stopped: stoppedProjects.value.length,
    completed: checkRows.value.filter(r => r.constructionStatus === '完工').length,
  }))

  // ─── Actions: Plan ─────────────────────────────────────────────────────────

  function updatePlan(field: keyof H2StocktakePlan, value: any): void {
    if (options.isReadonly.value) return
    if (field === 'selectedProjects') {
      plan.value.selectedProjects = Array.isArray(value) ? value : []
    } else {
      ;(plan.value as any)[field] = String(value ?? '')
    }
    options.onSave?.(PLAN_KEY, plan.value)
  }

  function addPlanProject(name: string): void {
    if (options.isReadonly.value) return
    plan.value.selectedProjects.push({
      rowId: `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      name: name || '',
      reason: '',
      plannedContent: '',
    })
    options.onSave?.(PLAN_KEY, plan.value)
  }

  function removePlanProject(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = plan.value.selectedProjects.findIndex(p => p.rowId === rowId)
    if (idx !== -1) {
      plan.value.selectedProjects.splice(idx, 1)
      options.onSave?.(PLAN_KEY, plan.value)
    }
  }

  // ─── Actions: Check ────────────────────────────────────────────────────────

  function addCheckRow(name: string): void {
    if (options.isReadonly.value) return
    checkRows.value.push({
      rowId: `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      name: name || '',
      siteLocation: '', visibleProgress: null, constructionStatus: '',
      workers: '', materialStorage: '', equipmentCondition: '',
      safetyMeasures: '', qualityAppearance: '', photos: '',
      progressDifference: '', auditConclusion: '', remark: '',
    })
    _persistCheck()
  }

  function removeCheckRow(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = checkRows.value.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      checkRows.value.splice(idx, 1)
      _persistCheck()
    }
  }

  function updateCheckRow(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const row = checkRows.value.find(r => r.rowId === rowId)
    if (!row) return
    if (field === 'visibleProgress') {
      row.visibleProgress = value != null ? Number(value) : null
    } else {
      ;(row as any)[field] = String(value ?? '')
    }
    _persistCheck()
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
      name, abnormalType: '', description: '', suggestion: '',
    })
    options.onSave?.(SUMMARY_KEY, summary.value)
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  function _persistCheck(): void {
    options.onSave?.(CHECK_ROWS_KEY, checkRows.value.map(r => ({
      rowId: r.rowId, name: r.name, siteLocation: r.siteLocation,
      visibleProgress: r.visibleProgress, constructionStatus: r.constructionStatus,
      workers: r.workers, materialStorage: r.materialStorage,
      equipmentCondition: r.equipmentCondition, safetyMeasures: r.safetyMeasures,
      qualityAppearance: r.qualityAppearance, photos: r.photos,
      progressDifference: r.progressDifference, auditConclusion: r.auditConclusion,
      remark: r.remark,
    })))
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    plan, checkRows, summary, auditNote,
    stoppedProjects, stoppedProjectNames, checkStats,
    updatePlan, addPlanProject, removePlanProject,
    addCheckRow, removeCheckRow, updateCheckRow,
    updateSummary, addAbnormalProject,
    saveNote, initFromAllResponses,
  }
}

export default useH2Stocktake
