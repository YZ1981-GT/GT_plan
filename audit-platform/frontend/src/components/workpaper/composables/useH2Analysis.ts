/**
 * useH2Analysis — H2-4 分析表 composable
 *
 * 三区域（工程进度+资本化率+工期分析）+ 10公式自动计算
 * 从H2-2 crossSheet取数 + 超期/超预算异常判定
 *
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Task: 3.6
 * Requirements: 5.1-5.8
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcCompletionRate,
  calcOverBudgetRate,
  calcOverdueDays,
  calcCostDiffRate,
} from './useH2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H2AnalysisProject {
  rowId: string
  name: string
  budget: number
  accumulatedInput: number
  cipBegin: number
  cipEnd: number
  increaseTotal: number
  decrease: number
  transferAmount: number
  startDate: string
  plannedEndDate: string
  actualEndDate: string
  capRate: number | null
  interestCap: number
  totalInterest: number
}

export interface ProgressAnalysis {
  name: string
  completionRate: number | null
  overBudgetRate: number | null
  isOverBudget: boolean  // >20%
}

export interface DurationAnalysis {
  name: string
  plannedEndDate: string
  actualEndDate: string
  overdueDays: number
  isSevereOverdue: boolean  // >180天
}

export interface CapRateAnalysis {
  name: string
  capRate: number | null
  interestCap: number
  totalInterest: number
  capRatioPercent: number | null  // 资本化利息/总利息×100
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H2-4-projects'
const NOTE_KEY = 'H2-4-audit-note'
const CONCLUSION_KEY = 'H2-4-audit-conclusion'
const OVERDUE_SEVERE_DAYS = 180
const OVER_BUDGET_THRESHOLD = 20  // %

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2Analysis(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  /** 从useH2CrossSheet.analysisFromDetail取数 */
  analysisFromDetail?: ComputedRef<Record<string, number>>
  onSave?: (itemId: string, value: any) => void
}) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const projects = ref<H2AnalysisProject[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

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

  function _getNum(val: any): number {
    if (val == null) return 0
    const n = Number(val)
    return Number.isFinite(n) ? n : 0
  }

  // ─── Init: 从H2-2跨sheet取数构建分析项目列表 ──────────────────────────────

  function initFromAllResponses(): void {
    // 从H2-2 rows取数构建分析数据
    const h2_2_resp = options.allResponses.value.get('H2-2-rows')
    const h2_2_raw = h2_2_resp?.remark ?? h2_2_resp?.conclusion
    let h2Rows: any[] = []
    if (h2_2_raw) {
      try { h2Rows = JSON.parse(h2_2_raw) ?? [] } catch { /* empty */ }
    }

    if (Array.isArray(h2Rows) && h2Rows.length > 0) {
      projects.value = h2Rows.map((r: any) => ({
        rowId: r.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
        name: r.name ?? '',
        budget: _getNum(r.budget),
        accumulatedInput: _getNum(r.accumulatedInput),
        cipBegin: _getNum(r.cipBegin),
        cipEnd: _getNum(r.cipEnd),
        increaseTotal: _getNum(r.increaseTotal) ||
          (_getNum(r.increaseMaterial) + _getNum(r.increaseLabor) +
           _getNum(r.increaseMachinery) + _getNum(r.increaseInterest) +
           _getNum(r.increaseOther)),
        decrease: _getNum(r.decrease),
        transferAmount: _getNum(r.transferAmount),
        startDate: r.startDate ?? '',
        plannedEndDate: r.plannedEndDate ?? '',
        actualEndDate: r.actualEndDate ?? '',
        capRate: r.capRate != null ? Number(r.capRate) : null,
        interestCap: _getNum(r.increaseInterest),
        totalInterest: _getNum(r.increaseInterest),
      }))
    } else {
      projects.value = []
    }

    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  // ─── Computed: 工程进度分析 ────────────────────────────────────────────────

  const progressAnalysis: ComputedRef<ProgressAnalysis[]> = computed(() =>
    projects.value.map(p => {
      const cr = calcCompletionRate(p.accumulatedInput, p.budget)
      const obr = calcOverBudgetRate(p.accumulatedInput, p.budget)
      return {
        name: p.name,
        completionRate: cr,
        overBudgetRate: obr,
        isOverBudget: obr != null && obr > OVER_BUDGET_THRESHOLD,
      }
    }),
  )

  // ─── Computed: 工期分析 ────────────────────────────────────────────────────

  const durationAnalysis: ComputedRef<DurationAnalysis[]> = computed(() =>
    projects.value
      .filter(p => p.plannedEndDate)
      .map(p => {
        const checkDate = p.actualEndDate || new Date().toISOString().slice(0, 10)
        const days = calcOverdueDays(checkDate, p.plannedEndDate)
        return {
          name: p.name,
          plannedEndDate: p.plannedEndDate,
          actualEndDate: p.actualEndDate,
          overdueDays: days,
          isSevereOverdue: days > OVERDUE_SEVERE_DAYS,
        }
      }),
  )

  // ─── Computed: 资本化率分析 ────────────────────────────────────────────────

  const capRateAnalysis: ComputedRef<CapRateAnalysis[]> = computed(() =>
    projects.value.map(p => ({
      name: p.name,
      capRate: p.capRate,
      interestCap: p.interestCap,
      totalInterest: p.totalInterest,
      capRatioPercent: p.totalInterest > 0
        ? (p.interestCap / p.totalInterest) * 100
        : null,
    })),
  )

  // ─── Computed: 汇总统计（从crossSheet或本地） ──────────────────────────────

  const summaryStats = computed(() => {
    const cs = options.analysisFromDetail?.value
    return {
      totalBudget: cs?.total_budget ?? projects.value.reduce((s, p) => s + p.budget, 0),
      totalAccumulated: cs?.total_accumulated ?? projects.value.reduce((s, p) => s + p.accumulatedInput, 0),
      projectCount: cs?.project_count ?? projects.value.length,
      completedCount: cs?.completed_count ?? progressAnalysis.value.filter(p => (p.completionRate ?? 0) >= 100).length,
      overdueCount: cs?.overdue_count ?? durationAnalysis.value.filter(d => d.overdueDays > 0).length,
      severeOverdueCount: durationAnalysis.value.filter(d => d.isSevereOverdue).length,
      overBudgetCount: progressAnalysis.value.filter(p => p.isOverBudget).length,
    }
  })

  // ─── Computed: 异常项 (高亮规则) ───────────────────────────────────────────

  /** 超期>180天的工程名称列表 */
  const severeOverdueProjects: ComputedRef<string[]> = computed(() =>
    durationAnalysis.value.filter(d => d.isSevereOverdue).map(d => d.name),
  )

  /** 超预算>20%的工程名称列表 */
  const overBudgetProjects: ComputedRef<string[]> = computed(() =>
    progressAnalysis.value.filter(p => p.isOverBudget).map(p => p.name),
  )

  // ─── Computed: 展示行（对齐 H2TabAnalysis 模板列结构） ─────────────────────

  /** 工程进度分析展示行（含预算/累计投入/完工率/超预算率） */
  const progressRows: ComputedRef<Array<{
    name: string; budget: number; accumulated: number
    completionRate: number | null; overBudgetRate: number | null
  }>> = computed(() =>
    projects.value.map(p => ({
      name: p.name,
      budget: p.budget,
      accumulated: p.accumulatedInput,
      completionRate: calcCompletionRate(p.accumulatedInput, p.budget),
      overBudgetRate: calcOverBudgetRate(p.accumulatedInput, p.budget),
    })),
  )

  /** 资本化率分析展示行（资本化利息/在建余额/实际资本化率/基准利率） */
  const capRateRows: ComputedRef<Array<{
    name: string; interestAmount: number; cipBalance: number
    actualCapRate: number | null; benchmarkRate: number | null
  }>> = computed(() =>
    projects.value.map(p => ({
      name: p.name,
      interestAmount: p.interestCap,
      cipBalance: p.cipEnd,
      actualCapRate: p.cipEnd > 0 ? (p.interestCap / p.cipEnd) * 100 : null,
      benchmarkRate: p.capRate,
    })),
  )

  /** 工期分析展示行（开工/预计竣工/实际竣工/超期天数） */
  const durationRows: ComputedRef<Array<{
    name: string; startDate: string; plannedEnd: string
    actualEnd: string; overdueDays: number
  }>> = computed(() =>
    projects.value
      .filter(p => p.plannedEndDate)
      .map(p => {
        const checkDate = p.actualEndDate || new Date().toISOString().slice(0, 10)
        return {
          name: p.name,
          startDate: p.startDate,
          plannedEnd: p.plannedEndDate,
          actualEnd: p.actualEndDate,
          overdueDays: calcOverdueDays(checkDate, p.plannedEndDate),
        }
      }),
  )

  // ─── Actions ───────────────────────────────────────────────────────────────

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options.onSave?.(CONCLUSION_KEY, conclusion)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    projects,
    auditNote,
    auditConclusion,
    /** 别名：H2TabAnalysis 模板使用 state.conclusion.value */
    conclusion: auditConclusion,
    progressAnalysis,
    durationAnalysis,
    capRateAnalysis,
    // 展示行（对齐模板列结构）
    progressRows,
    capRateRows,
    durationRows,
    summaryStats,
    severeOverdueProjects,
    overBudgetProjects,
    saveNote,
    saveConclusion,
    initFromAllResponses,
  }
}

export default useH2Analysis
