/**
 * useH2Analysis — H2-4 在建工程分析表 composable
 *
 * 对齐致同模板「分析表H2-4」编制逻辑：
 * 1) 比例/指标分析性程序：本期 vs 上期 + 变动% + 原因解释（可动态插行）
 * 2) 工程深挖：完工进度 / 资本化率 / 工期偏差（从 H2-2 取数，阈值预警）
 *
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Requirements: 5.1-5.8 + Excel 模板对齐
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcCompletionRate,
  calcOverBudgetRate,
  calcOverdueDays,
} from './useH2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type IndicatorUnit = 'pct' | 'amount' | 'rate'

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
  impairment: number
}

export interface ProgressAnalysis {
  name: string
  completionRate: number | null
  overBudgetRate: number | null
  isOverBudget: boolean
}

export interface DurationAnalysis {
  name: string
  plannedEndDate: string
  actualEndDate: string
  overdueDays: number
  isSevereOverdue: boolean
}

export interface CapRateAnalysis {
  name: string
  capRate: number | null
  interestCap: number
  totalInterest: number
  capRatioPercent: number | null
}

/** 外部/上期补充输入（持久化） */
export interface IndicatorInputs {
  totalAssetsCurrent: number | null
  totalAssetsPrior: number | null
  cipEndPrior: number | null
  cipGrossCurrent: number | null
  cipGrossPrior: number | null
  impairmentCurrent: number | null
  impairmentPrior: number | null
  budgetTotalCurrent: number | null
  budgetTotalPrior: number | null
  actualSpendCurrent: number | null
  actualSpendPrior: number | null
  interestCapRateCurrent: number | null
  interestCapRatePrior: number | null
  capacityOutputCurrent: number | null
  capacityOutputPrior: number | null
  designCapacityCurrent: number | null
  designCapacityPrior: number | null
  yearCurrent: string
  yearPrior: string
}

export interface IndicatorRow {
  id: string
  seq: number
  name: string
  unit: IndicatorUnit
  formulaHint: string
  riskHint: string
  current: number | null
  prior: number | null
  /** 变动率 %；金额类=相对变动，比率类=百分点差或相对变动 */
  changePct: number | null
  explanation: string
  /** 是否模板预置（不可改名删除时区分自定义） */
  builtin: boolean
  /** 自定义行：允许手填本期/上期 */
  manualCurrent: number | null
  manualPrior: number | null
  autoCurrent: boolean
  autoPrior: boolean
}

/** AI / 插行候选指标目录 */
export interface IndicatorSuggestion {
  id: string
  name: string
  unit: IndicatorUnit
  formulaHint: string
  riskHint: string
  scenario: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H2-4-projects'
const NOTE_KEY = 'H2-4-audit-note'
const CONCLUSION_KEY = 'H2-4-audit-conclusion'
const INPUTS_KEY = 'H2-4-indicator-inputs'
const EXPL_KEY = 'H2-4-indicator-explanations'
const CUSTOM_KEY = 'H2-4-custom-indicators'
const OVERDUE_SEVERE_DAYS = 180
const OVER_BUDGET_THRESHOLD = 20
/** 变动率绝对值超此阈值须说明（%） */
export const CHANGE_THRESHOLD_PCT = 20

const DEFAULT_INPUTS: IndicatorInputs = {
  totalAssetsCurrent: null,
  totalAssetsPrior: null,
  cipEndPrior: null,
  cipGrossCurrent: null,
  cipGrossPrior: null,
  impairmentCurrent: null,
  impairmentPrior: null,
  budgetTotalCurrent: null,
  budgetTotalPrior: null,
  actualSpendCurrent: null,
  actualSpendPrior: null,
  interestCapRateCurrent: null,
  interestCapRatePrior: null,
  capacityOutputCurrent: null,
  capacityOutputPrior: null,
  designCapacityCurrent: null,
  designCapacityPrior: null,
  yearCurrent: '',
  yearPrior: '',
}

/** 致同模板预置 6 项 + 扩展候选（动态插行 / AI 建议） */
export const BUILTIN_INDICATOR_DEFS: Array<{
  id: string
  seq: number
  name: string
  unit: IndicatorUnit
  formulaHint: string
  riskHint: string
}> = [
  {
    id: 'cip_to_assets',
    seq: 1,
    name: '在建工程 / 资产总额',
    unit: 'pct',
    formulaHint: '在建工程期末÷资产总额×100%',
    riskHint: '资产结构：占比异常升高关注资本性支出规模与资金压力',
  },
  {
    id: 'cip_end_balance',
    seq: 2,
    name: '在建工程期末余额',
    unit: 'amount',
    formulaHint: 'H2-1/H2-2 期末在建工程合计',
    riskHint: '余额变动：大幅增减需说明新增工程、转固或停工清理',
  },
  {
    id: 'impairment_ratio',
    seq: 3,
    name: '在建工程减值准备 ÷ 在建工程原值',
    unit: 'pct',
    formulaHint: '减值准备÷在建工程账面原值×100%',
    riskHint: '减值充分性：与停工/超期项目及 H2-15/16 勾稽',
  },
  {
    id: 'spend_vs_budget',
    seq: 4,
    name: '实际支出与预算的差异',
    unit: 'pct',
    formulaHint: '(累计投入−预算)/预算×100%',
    riskHint: '预算执行：超支提示成本控制或预算不实，关联 H2-7 造价比较',
  },
  {
    id: 'interest_cap_rate',
    seq: 5,
    name: '利息资本化率',
    unit: 'pct',
    formulaHint: '资本化利息/加权平均支出或专门借款利率',
    riskHint: 'CAS17：偏离市场利率或基准过多需解释，关联 H2-10/11',
  },
  {
    id: 'capacity_util',
    seq: 6,
    name: '实际产出 ÷ 生产能力（产能利用率）',
    unit: 'pct',
    formulaHint: '实际产出÷设计生产能力×100%',
    riskHint: '产能匹配：达产率偏低提示闲置或减值迹象',
  },
]

/** 可新增的扩展指标（AI 建议 / 一键添加） */
export const SUGGESTED_INDICATOR_CATALOG: IndicatorSuggestion[] = [
  {
    id: 'transfer_ratio',
    name: '本期转固金额 ÷ 期初在建工程',
    unit: 'pct',
    formulaHint: '本期转固÷期初余额×100%',
    riskHint: '转固节奏：过低关注长期挂账，过高关注提前转固',
    scenario: '有多个在建项目、转固时点风险较高时建议增加',
  },
  {
    id: 'increase_to_cip',
    name: '本期增加 ÷ 期末在建工程',
    unit: 'pct',
    formulaHint: '本期增加÷期末余额×100%',
    riskHint: '投入强度：异常增高关注虚构工程或关联方虚增',
    scenario: '本期资本性支出大幅波动时建议增加',
  },
  {
    id: 'overdue_project_ratio',
    name: '超期项目数 ÷ 在建项目总数',
    unit: 'pct',
    formulaHint: '超期项目数÷项目总数×100%',
    riskHint: '工期风险：超期占比高需评估停工减值（→H2-15）',
    scenario: '存在较多预计竣工日已过仍未转固的项目时建议增加',
  },
  {
    id: 'interest_to_increase',
    name: '资本化利息 ÷ 本期增加额',
    unit: 'pct',
    formulaHint: '资本化利息÷本期增加×100%',
    riskHint: '利息占比：过高关注过度资本化或专门借款闲置',
    scenario: '有专门借款或利息资本化金额较大时建议增加',
  },
  {
    id: 'cip_growth_vs_fa',
    name: '在建工程净增加 ÷ 固定资产原值增加',
    unit: 'pct',
    formulaHint: 'CIP净增加÷固定资产原值增加×100%',
    riskHint: '投资闭环：与转固/固定资产增加勾稽是否闭环',
    scenario: '制造业/基建类、固定资产与在建工程联动明显时建议增加',
  },
  {
    id: 'suspended_balance_ratio',
    name: '停工/缓建余额 ÷ 在建工程期末',
    unit: 'pct',
    formulaHint: '停工缓建项目余额÷期末余额×100%',
    riskHint: '停工减值：停工占比高须执行减值测试',
    scenario: '存在停工、缓建或长期无进展项目时建议增加',
  },
  {
    id: 'related_party_cip_ratio',
    name: '关联方工程款 ÷ 本期增加',
    unit: 'pct',
    formulaHint: '关联方相关增加÷本期增加×100%',
    riskHint: '关联交易：关注定价公允与资金闭环（→H2-17）',
    scenario: '存在关联方承包/ equip 供应时建议增加',
  },
  {
    id: 'avg_completion_rate',
    name: '加权平均完工率',
    unit: 'pct',
    formulaHint: 'Σ(累计投入)/Σ(预算)×100%',
    riskHint: '整体进度：与披露完工进度、转固计划是否一致',
    scenario: '项目较多、需从整体层面评价进度时建议增加',
  },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _getNum(val: any): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

function _nullableNum(v: unknown): number | null {
  if (v == null || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

function _safeParseJson<T>(raw: unknown, fallback: T): T {
  if (raw == null || raw === '') return fallback
  if (typeof raw === 'object') return raw as T
  try {
    return JSON.parse(String(raw)) as T
  } catch {
    return fallback
  }
}

function _pct(numer: number | null, denom: number | null): number | null {
  if (numer == null || denom == null || denom === 0) return null
  return (numer / denom) * 100
}

function _changePct(current: number | null, prior: number | null, unit: IndicatorUnit): number | null {
  if (current == null || prior == null) return null
  if (unit === 'amount') {
    if (prior === 0) return current === 0 ? 0 : null
    return ((current - prior) / Math.abs(prior)) * 100
  }
  // 比率类：用相对变动%；若上期为0则仅当本期也为0
  if (prior === 0) return current === 0 ? 0 : null
  return ((current - prior) / Math.abs(prior)) * 100
}

function _uid(prefix = 'ind'): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2Analysis(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  analysisFromDetail?: ComputedRef<Record<string, number>>
  onSave?: (itemId: string, value: any) => void
}) {
  const projects = ref<H2AnalysisProject[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const indicatorInputs = ref<IndicatorInputs>({ ...DEFAULT_INPUTS })
  const explanations = ref<Record<string, string>>({})
  /** 用户动态新增的自定义指标定义 */
  const customDefs = ref<Array<{
    id: string
    name: string
    unit: IndicatorUnit
    formulaHint: string
    riskHint: string
    manualCurrent?: number | null
    manualPrior?: number | null
  }>>([])

  function _getJson(itemId: string): any {
    const item = options.allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return typeof raw === 'object' ? raw : JSON.parse(raw) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = options.allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _persist(itemId: string, value: unknown): void {
    const payload = typeof value === 'string' ? value : JSON.stringify(value)
    options.onSave?.(itemId, payload)
  }

  // ─── 从 H2-1 / H2-2 聚合自动取数 ─────────────────────────────────────────

  const autoAggregates = computed(() => {
    const cs = options.analysisFromDetail?.value
    let cipEnd = cs?.total_cip_end ?? 0
    let cipBegin = cs?.total_cip_begin ?? 0
    let budget = cs?.total_budget ?? 0
    let accumulated = cs?.total_accumulated ?? 0
    let increase = cs?.total_increase ?? 0
    let transfer = cs?.total_transfer ?? 0
    let interestCap = 0
    let impairment = 0
    let projectCount = cs?.project_count ?? 0
    let overdueCount = cs?.overdue_count ?? 0

    if (projects.value.length) {
      if (!cipEnd) cipEnd = projects.value.reduce((s, p) => s + p.cipEnd, 0)
      if (!cipBegin) cipBegin = projects.value.reduce((s, p) => s + p.cipBegin, 0)
      if (!budget) budget = projects.value.reduce((s, p) => s + p.budget, 0)
      if (!accumulated) accumulated = projects.value.reduce((s, p) => s + p.accumulatedInput, 0)
      if (!increase) increase = projects.value.reduce((s, p) => s + p.increaseTotal, 0)
      if (!transfer) transfer = projects.value.reduce((s, p) => s + p.transferAmount, 0)
      interestCap = projects.value.reduce((s, p) => s + p.interestCap, 0)
      impairment = projects.value.reduce((s, p) => s + p.impairment, 0)
      if (!projectCount) projectCount = projects.value.length
    }

    // H2-1 审定表补充减值
    const h2_1 = _getJson('H2-1-rows')
    if (Array.isArray(h2_1) && h2_1.length) {
      const imp = h2_1.reduce((s: number, r: any) => s + _getNum(r.impairment), 0)
      if (imp && !impairment) impairment = imp
      const end = h2_1.reduce((s: number, r: any) => s + _getNum(r.cipEnd ?? r.audited), 0)
      if (end && !cipEnd) cipEnd = end
    }

    return {
      cipEnd, cipBegin, budget, accumulated, increase, transfer,
      interestCap, impairment, projectCount, overdueCount,
    }
  })

  // ─── Init ──────────────────────────────────────────────────────────────────

  function initFromAllResponses(): void {
    const h2_2_resp = options.allResponses.value.get('H2-2-rows')
    const h2_2_raw = h2_2_resp?.remark ?? h2_2_resp?.conclusion
    let h2Rows: any[] = []
    if (h2_2_raw) {
      try { h2Rows = typeof h2_2_raw === 'object' ? (h2_2_raw as any[]) : (JSON.parse(h2_2_raw) ?? []) } catch { /* empty */ }
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
        impairment: _getNum(r.impairment),
      }))
    } else {
      projects.value = []
    }

    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)

    const savedInputs = _getJson(INPUTS_KEY)
    if (savedInputs && typeof savedInputs === 'object') {
      indicatorInputs.value = { ...DEFAULT_INPUTS, ...savedInputs }
    }

    const savedExpl = _getJson(EXPL_KEY)
    if (savedExpl && typeof savedExpl === 'object') {
      explanations.value = savedExpl as Record<string, string>
    }

    const savedCustom = _getJson(CUSTOM_KEY)
    if (Array.isArray(savedCustom)) {
      customDefs.value = savedCustom
    }
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  // ─── 指标行（模板6项 + 自定义） ────────────────────────────────────────────

  const indicatorRows: ComputedRef<IndicatorRow[]> = computed(() => {
    const inp = indicatorInputs.value
    const agg = autoAggregates.value

    const cipCurrent = agg.cipEnd || null
    const cipPrior = inp.cipEndPrior
    const assetsCur = inp.totalAssetsCurrent
    const assetsPri = inp.totalAssetsPrior
    const grossCur = inp.cipGrossCurrent ?? (cipCurrent != null ? cipCurrent + (inp.impairmentCurrent ?? agg.impairment) : null)
    const grossPri = inp.cipGrossPrior
    const impCur = inp.impairmentCurrent ?? (agg.impairment || null)
    const impPri = inp.impairmentPrior

    const budgetCur = inp.budgetTotalCurrent ?? (agg.budget || null)
    const budgetPri = inp.budgetTotalPrior
    const spendCur = inp.actualSpendCurrent ?? (agg.accumulated || null)
    const spendPri = inp.actualSpendPrior

    const builtinValues: Record<string, { current: number | null; prior: number | null; autoC: boolean; autoP: boolean }> = {
      cip_to_assets: {
        current: _pct(cipCurrent, assetsCur),
        prior: _pct(cipPrior, assetsPri),
        autoC: cipCurrent != null && assetsCur != null,
        autoP: cipPrior != null && assetsPri != null,
      },
      cip_end_balance: {
        current: cipCurrent,
        prior: cipPrior,
        autoC: cipCurrent != null,
        autoP: cipPrior != null,
      },
      impairment_ratio: {
        current: _pct(impCur, grossCur),
        prior: _pct(impPri, grossPri),
        autoC: impCur != null && grossCur != null,
        autoP: impPri != null && grossPri != null,
      },
      spend_vs_budget: {
        current: budgetCur && spendCur != null ? ((spendCur - budgetCur) / budgetCur) * 100 : null,
        prior: budgetPri && spendPri != null ? ((spendPri - budgetPri) / budgetPri) * 100 : null,
        autoC: spendCur != null && budgetCur != null,
        autoP: spendPri != null && budgetPri != null,
      },
      interest_cap_rate: {
        current: inp.interestCapRateCurrent,
        prior: inp.interestCapRatePrior,
        autoC: false,
        autoP: false,
      },
      capacity_util: {
        current: _pct(inp.capacityOutputCurrent, inp.designCapacityCurrent),
        prior: _pct(inp.capacityOutputPrior, inp.designCapacityPrior),
        autoC: inp.capacityOutputCurrent != null && inp.designCapacityCurrent != null,
        autoP: inp.capacityOutputPrior != null && inp.designCapacityPrior != null,
      },
    }

    // 扩展内置计算（若用户从目录添加）
    const extValues: Record<string, { current: number | null; prior: number | null; autoC: boolean; autoP: boolean }> = {
      transfer_ratio: {
        current: _pct(agg.transfer || null, agg.cipBegin || null),
        prior: null,
        autoC: !!agg.cipBegin,
        autoP: false,
      },
      increase_to_cip: {
        current: _pct(agg.increase || null, agg.cipEnd || null),
        prior: null,
        autoC: !!agg.cipEnd,
        autoP: false,
      },
      overdue_project_ratio: {
        current: _pct(agg.overdueCount || null, agg.projectCount || null),
        prior: null,
        autoC: !!agg.projectCount,
        autoP: false,
      },
      interest_to_increase: {
        current: _pct(agg.interestCap || null, agg.increase || null),
        prior: null,
        autoC: !!agg.increase,
        autoP: false,
      },
      avg_completion_rate: {
        current: _pct(agg.accumulated || null, agg.budget || null),
        prior: null,
        autoC: !!agg.budget,
        autoP: false,
      },
      suspended_balance_ratio: { current: null, prior: null, autoC: false, autoP: false },
      related_party_cip_ratio: { current: null, prior: null, autoC: false, autoP: false },
      cip_growth_vs_fa: { current: null, prior: null, autoC: false, autoP: false },
    }

    const rows: IndicatorRow[] = BUILTIN_INDICATOR_DEFS.map((d) => {
      const v = builtinValues[d.id] ?? { current: null, prior: null, autoC: false, autoP: false }
      return {
        id: d.id,
        seq: d.seq,
        name: d.name,
        unit: d.unit,
        formulaHint: d.formulaHint,
        riskHint: d.riskHint,
        current: v.current,
        prior: v.prior,
        changePct: _changePct(v.current, v.prior, d.unit),
        explanation: explanations.value[d.id] ?? '',
        builtin: true,
        manualCurrent: null,
        manualPrior: null,
        autoCurrent: v.autoC,
        autoPrior: v.autoP,
      }
    })

    let seq = rows.length
    for (const c of customDefs.value) {
      seq += 1
      const catalog = SUGGESTED_INDICATOR_CATALOG.find((s) => s.id === c.id)
      const ext = extValues[c.id]
      const useAuto = !!ext && (ext.autoC || ext.current != null)
      const manualC = _nullableNum(c.manualCurrent)
      const manualP = _nullableNum(c.manualPrior)
      const cur = manualC ?? (useAuto ? ext!.current : null)
      const pri = manualP ?? (useAuto ? ext!.prior : null)
      rows.push({
        id: c.id,
        seq,
        name: c.name,
        unit: c.unit,
        formulaHint: c.formulaHint || catalog?.formulaHint || '',
        riskHint: c.riskHint || catalog?.riskHint || '',
        current: cur,
        prior: pri,
        changePct: _changePct(cur, pri, c.unit),
        explanation: explanations.value[c.id] ?? '',
        builtin: false,
        manualCurrent: manualC,
        manualPrior: manualP,
        autoCurrent: useAuto && manualC == null,
        autoPrior: useAuto && manualP == null && pri != null,
      })
    }

    return rows
  })

  const abnormalIndicators = computed(() =>
    indicatorRows.value.filter((r) => r.changePct != null && Math.abs(r.changePct) > CHANGE_THRESHOLD_PCT),
  )

  /** 尚未添加的候选指标（供 UI / AI 提示） */
  const availableSuggestions = computed(() => {
    const used = new Set([
      ...BUILTIN_INDICATOR_DEFS.map((d) => d.id),
      ...customDefs.value.map((c) => c.id),
    ])
    return SUGGESTED_INDICATOR_CATALOG.filter((s) => !used.has(s.id))
  })

  // ─── 工程进度 / 资本化 / 工期（保留） ─────────────────────────────────────

  const progressAnalysis: ComputedRef<ProgressAnalysis[]> = computed(() =>
    projects.value.map((p) => {
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

  const durationAnalysis: ComputedRef<DurationAnalysis[]> = computed(() =>
    projects.value
      .filter((p) => p.plannedEndDate)
      .map((p) => {
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

  const capRateAnalysis: ComputedRef<CapRateAnalysis[]> = computed(() =>
    projects.value.map((p) => ({
      name: p.name,
      capRate: p.capRate,
      interestCap: p.interestCap,
      totalInterest: p.totalInterest,
      capRatioPercent: p.totalInterest > 0 ? (p.interestCap / p.totalInterest) * 100 : null,
    })),
  )

  const summaryStats = computed(() => {
    const cs = options.analysisFromDetail?.value
    return {
      totalBudget: cs?.total_budget ?? projects.value.reduce((s, p) => s + p.budget, 0),
      totalAccumulated: cs?.total_accumulated ?? projects.value.reduce((s, p) => s + p.accumulatedInput, 0),
      projectCount: cs?.project_count ?? projects.value.length,
      completedCount: cs?.completed_count ?? progressAnalysis.value.filter((p) => (p.completionRate ?? 0) >= 100).length,
      overdueCount: cs?.overdue_count ?? durationAnalysis.value.filter((d) => d.overdueDays > 0).length,
      severeOverdueCount: durationAnalysis.value.filter((d) => d.isSevereOverdue).length,
      overBudgetCount: progressAnalysis.value.filter((p) => p.isOverBudget).length,
    }
  })

  const severeOverdueProjects: ComputedRef<string[]> = computed(() =>
    durationAnalysis.value.filter((d) => d.isSevereOverdue).map((d) => d.name),
  )

  const overBudgetProjects: ComputedRef<string[]> = computed(() =>
    progressAnalysis.value.filter((p) => p.isOverBudget).map((p) => p.name),
  )

  const progressRows = computed(() =>
    projects.value.map((p) => ({
      name: p.name,
      budget: p.budget,
      accumulated: p.accumulatedInput,
      completionRate: calcCompletionRate(p.accumulatedInput, p.budget),
      overBudgetRate: calcOverBudgetRate(p.accumulatedInput, p.budget),
    })),
  )

  const capRateRows = computed(() =>
    projects.value.map((p) => ({
      name: p.name,
      interestAmount: p.interestCap,
      cipBalance: p.cipEnd,
      actualCapRate: p.cipEnd > 0 ? (p.interestCap / p.cipEnd) * 100 : null,
      benchmarkRate: p.capRate,
    })),
  )

  const durationRows = computed(() =>
    projects.value
      .filter((p) => p.plannedEndDate)
      .map((p) => {
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

  function updateInput<K extends keyof IndicatorInputs>(key: K, val: IndicatorInputs[K]): void {
    indicatorInputs.value = { ...indicatorInputs.value, [key]: val }
    _persist(INPUTS_KEY, indicatorInputs.value)
  }

  function setExplanation(id: string, text: string): void {
    explanations.value = { ...explanations.value, [id]: text }
    _persist(EXPL_KEY, explanations.value)
  }

  function setExplanationsBulk(map: Record<string, string>): void {
    explanations.value = { ...explanations.value, ...map }
    _persist(EXPL_KEY, explanations.value)
  }

  /** 从候选目录添加指标 */
  function addIndicatorFromCatalog(suggestionId: string): boolean {
    const sug = SUGGESTED_INDICATOR_CATALOG.find((s) => s.id === suggestionId)
    if (!sug) return false
    if (customDefs.value.some((c) => c.id === sug.id)) return false
    if (BUILTIN_INDICATOR_DEFS.some((d) => d.id === sug.id)) return false
    customDefs.value = [
      ...customDefs.value,
      {
        id: sug.id,
        name: sug.name,
        unit: sug.unit,
        formulaHint: sug.formulaHint,
        riskHint: sug.riskHint,
      },
    ]
    _persist(CUSTOM_KEY, customDefs.value)
    return true
  }

  /** 自由新增空白指标行 */
  function addCustomIndicator(partial?: {
    name?: string
    unit?: IndicatorUnit
    formulaHint?: string
    riskHint?: string
  }): string {
    const id = _uid('custom')
    customDefs.value = [
      ...customDefs.value,
      {
        id,
        name: partial?.name || '（自定义指标）',
        unit: partial?.unit || 'pct',
        formulaHint: partial?.formulaHint || '手填本期/上期',
        riskHint: partial?.riskHint || '请说明分析目的与异常关注点',
      },
    ]
    _persist(CUSTOM_KEY, customDefs.value)
    return id
  }

  function removeCustomIndicator(id: string): void {
    customDefs.value = customDefs.value.filter((c) => c.id !== id)
    const next = { ...explanations.value }
    delete next[id]
    explanations.value = next
    _persist(CUSTOM_KEY, customDefs.value)
    _persist(EXPL_KEY, explanations.value)
  }

  function updateCustomManual(id: string, field: 'manualCurrent' | 'manualPrior' | 'name', val: number | string | null): void {
    customDefs.value = customDefs.value.map((c) => {
      if (c.id !== id) return c
      return { ...c, [field]: val }
    })
    _persist(CUSTOM_KEY, customDefs.value)
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options.onSave?.(CONCLUSION_KEY, conclusion)
  }

  /** 供 AI 上下文：已有指标 + 可建议项 + 异常 */
  function buildAiContext(): Record<string, unknown> {
    return {
      yearCurrent: indicatorInputs.value.yearCurrent,
      yearPrior: indicatorInputs.value.yearPrior,
      indicators: indicatorRows.value.map((r) => ({
        name: r.name,
        current: r.current,
        prior: r.prior,
        changePct: r.changePct,
        explanation: r.explanation,
        abnormal: r.changePct != null && Math.abs(r.changePct) > CHANGE_THRESHOLD_PCT,
        formula: r.formulaHint,
      })),
      availableSuggestions: availableSuggestions.value,
      aggregates: autoAggregates.value,
      summaryStats: summaryStats.value,
      severeOverdueProjects: severeOverdueProjects.value,
      overBudgetProjects: overBudgetProjects.value,
    }
  }

  return {
    projects,
    auditNote,
    auditConclusion,
    conclusion: auditConclusion,
    // 指标分析
    indicatorInputs,
    indicatorRows,
    abnormalIndicators,
    availableSuggestions,
    autoAggregates,
    updateInput,
    setExplanation,
    setExplanationsBulk,
    addIndicatorFromCatalog,
    addCustomIndicator,
    removeCustomIndicator,
    updateCustomManual,
    buildAiContext,
    // 工程深挖
    progressAnalysis,
    durationAnalysis,
    capRateAnalysis,
    progressRows,
    capRateRows,
    durationRows,
    summaryStats,
    severeOverdueProjects,
    overBudgetProjects,
    saveNote,
    saveConclusion,
    initFromAllResponses,
    CHANGE_THRESHOLD_PCT,
    SUGGESTED_INDICATOR_CATALOG,
    ROWS_KEY,
  }
}

export default useH2Analysis
