/**
 * useH1Analysis — H1-6 固定资产分析表 composable
 *
 * 对齐致同模板「分析表H1-6」三层逻辑：
 * 1) 比例分析：程序表规定的 8 项比率（本期 vs 上期 + 变动解释）
 * 2) 结构分析：按分类占比/成新率/平均年限
 * 3) 变动分析：按分类增减率/净变动率 + 异常追踪
 *
 * 取数：H1-2 明细自动聚合；总资产/产量/租入/维修等外部指标可手填；
 * 租金收入优先取 H1-19 经营租出合计。
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import {
  calcChangeRate,
  calcProportion,
  calcSubtotal,
  calcNewRate,
  calcAvgUsefulLife,
  calcRemainingLife,
  calcRatioPct,
  calcRatioMultiple,
} from './useH1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface StructureRow {
  category: string
  costEnd: number
  netValue: number
  proportion: number | null
  newRate: number | null
  avgUsefulLife: number | null
  remainingLife: number | null
}

export interface ChangeRow {
  category: string
  priorEnd: number
  currentEnd: number
  changeAmount: number
  changeRate: number | null
  increase: number
  decrease: number
  increaseRate: number | null
  decreaseRate: number | null
  depCoverageRate: number | null
  explanation: string
}

export type RatioUnit = 'pct' | 'multiple'

export interface RatioRow {
  id: string
  seq: number
  name: string
  unit: RatioUnit
  formulaHint: string
  riskHint: string
  current: number | null
  prior: number | null
  change: number | null
  explanation: string
  autoCurrent: boolean
  autoPrior: boolean
}

/** 外部/上期补充输入（持久化） */
export interface RatioInputs {
  totalAssetsCurrent: number | null
  totalAssetsPrior: number | null
  productionVolumeCurrent: number | null
  productionVolumePrior: number | null
  leasedInCostCurrent: number | null
  leasedInCostPrior: number | null
  rentalIncomeCurrent: number | null
  rentalIncomePrior: number | null
  maintenanceExpenseCurrent: number | null
  maintenanceExpensePrior: number | null
  periodDepPrior: number | null
}

export interface AnomalyFlag {
  category: string
  type: 'low_new_rate' | 'high_increase' | 'high_decrease' | 'ratio_change'
  value: number
  threshold: number
  message: string
}

/** 折旧税会差异 → 递延所得税（暂时性差异=账面价值−计税基础） */
export interface DeferredTaxRecalc {
  /** 期末账面价值 = 原值 − 账面累计折旧 − 减值 */
  bookCarrying: number
  /** 期末计税基础 = 原值 − 税法累计折旧（税法不认减值） */
  taxBase: number | null
  /** 暂时性差异 = 账面价值 − 计税基础（负=可抵扣，正=应纳税） */
  temporaryDiff: number | null
  /** 可抵扣暂时性差异（账面<计税基础）→ 递延所得税资产 N1 */
  deductibleTD: number
  /** 应纳税暂时性差异（账面>计税基础）→ 递延所得税负债 N3 */
  taxableTD: number
  /** 适用税率(%) */
  taxRate: number
  /** 递延所得税资产 = 可抵扣暂时性差异 × 税率 */
  deferredTaxAsset: number
  /** 递延所得税负债 = 应纳税暂时性差异 × 税率 */
  deferredTaxLiability: number
  /** 差异性质 */
  nature: 'deductible' | 'taxable' | 'none'
  /** 本期折旧税会差异 = 账面本期折旧 − 税法本期折旧（差异变动驱动，信息性） */
  periodDepDiff: number | null
  /** 是否具备计税基础依据 */
  hasBasis: boolean
}

/** 折旧合理性整体重算（实质性分析程序：独立预期 vs 账面） */
export interface DepreciationRecalc {
  /** 平均原值 = (期初原值 + 期末原值) / 2 */
  avgCost: number
  /** 账面本期计提折旧（取自 H1-2 聚合） */
  bookedDep: number
  /** 上期计提折旧（外部输入，用于推导综合率） */
  priorDep: number | null
  /** 综合年折旧率(%)：手工覆盖优先，否则取上期计提÷期初原值 */
  compositeRate: number | null
  /** 综合率来源说明 */
  compositeRateSource: string
  /** 预期本期折旧 = 平均原值 × 综合年折旧率 */
  expectedDep: number | null
  /** 差异 = 账面 − 预期 */
  diff: number | null
  /** 差异率(%) = 差异 ÷ 预期 */
  diffRate: number | null
  /** 差异率阈值(%) */
  threshold: number
  /** 是否超阈值 */
  flagged: boolean
  /** 是否具备测算依据（有综合率且平均原值>0） */
  hasBasis: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H1-6'
const THRESHOLD_NEW_RATE = 20
const THRESHOLD_CHANGE_RATE = 50
const THRESHOLD_RATIO_PP = 5 // 比率百分点变动绝对值超 5pp 提示
const THRESHOLD_RATIO_REL = 20 // 倍数类相对变动超 20% 提示
const THRESHOLD_DEP_RECALC = 10 // 折旧整体重算差异率超 10% 须说明
const DEFAULT_TAX_RATE = 25 // 默认企业所得税率(%)

const DEFAULT_RATIO_INPUTS: RatioInputs = {
  totalAssetsCurrent: null,
  totalAssetsPrior: null,
  productionVolumeCurrent: null,
  productionVolumePrior: null,
  leasedInCostCurrent: null,
  leasedInCostPrior: null,
  rentalIncomeCurrent: null,
  rentalIncomePrior: null,
  maintenanceExpenseCurrent: null,
  maintenanceExpensePrior: null,
  periodDepPrior: null,
}

const RATIO_DEFS: Array<{
  id: string
  seq: number
  name: string
  unit: RatioUnit
  formulaHint: string
  riskHint: string
}> = [
  {
    id: 'net_to_assets',
    seq: 1,
    name: '固定资产净值 / 资产总额',
    unit: 'pct',
    formulaHint: '净值÷资产总额×100%',
    riskHint: '资产结构：固定资产占比异常升高/下降需关注资本性支出或处置',
  },
  {
    id: 'period_dep_rate',
    seq: 2,
    name: '本期计提折旧 / 固定资产原值',
    unit: 'pct',
    formulaHint: '本期计提÷期末原值×100%',
    riskHint: '折旧政策一致性：与会计政策及上期比较，识别少提/多提',
  },
  {
    id: 'acc_dep_rate',
    seq: 3,
    name: '累计折旧 / 固定资产原值',
    unit: 'pct',
    formulaHint: '累计折旧÷期末原值×100%',
    riskHint: '资产老化：比率过高提示成新率偏低、更新改造或减值风险',
  },
  {
    id: 'impairment_rate',
    seq: 4,
    name: '减值准备余额 / 固定资产原值',
    unit: 'pct',
    formulaHint: '减值准备÷期末原值×100%',
    riskHint: '减值充分性：与闲置/迹象判断及 H1-14 勾稽',
  },
  {
    id: 'cost_to_output',
    seq: 5,
    name: '固定资产原值 / 本期产品产量',
    unit: 'multiple',
    formulaHint: '期末原值÷本期产量',
    riskHint: '产能匹配：原值与产量背离提示闲置产能或产量统计异常',
  },
  {
    id: 'leased_in_ratio',
    seq: 6,
    name: '租入固定资产原值 / 固定资产原值',
    unit: 'pct',
    formulaHint: '租入原值÷期末原值×100%',
    riskHint: '租赁依赖：融资/经营租入占比及分类（CAS21）',
  },
  {
    id: 'rental_yield',
    seq: 7,
    name: '租金收入 / 固定资产原值',
    unit: 'pct',
    formulaHint: '租金收入÷期末原值×100%',
    riskHint: '租出收益：与 H1-19 勾稽，判断对租赁收益的依赖',
  },
  {
    id: 'maintenance_ratio',
    seq: 8,
    name: '维修费用 / 固定资产原值',
    unit: 'pct',
    formulaHint: '维修费用÷期末原值×100%',
    riskHint: '后续支出：维修费异常升高关注应资本化支出是否费用化',
  },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _num(v: unknown): number {
  const n = Number(v)
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

function _ppChange(current: number | null, prior: number | null): number | null {
  if (current == null || prior == null) return null
  return current - prior
}

function _relChangePct(current: number | null, prior: number | null): number | null {
  return calcChangeRate(current ?? 0, prior ?? 0)
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1Analysis(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    crossSheetDetailRows?: Ref<any[]>
    onSave?: (itemId: string, value: any) => void
  },
) {
  const auditNote = ref('')
  const auditConclusion = ref('')
  const ratioInputs = ref<RatioInputs>({ ...DEFAULT_RATIO_INPUTS })
  const ratioExplanations = ref<Record<string, string>>({})
  const changeExplanations = ref<Record<string, string>>({})
  /** 折旧整体重算：综合年折旧率手工覆盖(%)（null=自动取上期率） */
  const depRecalcRate = ref<number | null>(null)
  const depRecalcExplanation = ref('')
  /** 折旧税会差异输入：税法累计折旧 / 本期税法折旧 / 适用税率(%) / 说明 */
  const taxAccumDep = ref<number | null>(null)
  const taxPeriodDep = ref<number | null>(null)
  const taxRate = ref<number | null>(null)
  const taxDiffExplanation = ref('')

  function _getItem(itemId: string): ChecklistItem | undefined {
    return allResponses.value.get(itemId)
  }

  function _getString(itemId: string): string {
    const item = _getItem(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _persist(itemId: string, value: unknown): void {
    const payload = typeof value === 'string' ? value : JSON.stringify(value)
    options?.onSave?.(itemId, payload)
  }

  function _loadData(): void {
    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)
    const inputs = _safeParseJson<Partial<RatioInputs>>(
      _getItem(`${ITEM_PREFIX}-ratio-inputs`)?.remark,
      {},
    )
    ratioInputs.value = { ...DEFAULT_RATIO_INPUTS, ...inputs }
    ratioExplanations.value = _safeParseJson(
      _getItem(`${ITEM_PREFIX}-ratio-explanations`)?.remark,
      {},
    )
    changeExplanations.value = _safeParseJson(
      _getItem(`${ITEM_PREFIX}-change-explanations`)?.remark,
      {},
    )
    const recalc = _safeParseJson<{ rate?: number | null; explanation?: string }>(
      _getItem(`${ITEM_PREFIX}-dep-recalc`)?.remark,
      {},
    )
    depRecalcRate.value = recalc.rate == null || recalc.rate === ('' as unknown as number)
      ? null
      : Number(recalc.rate)
    depRecalcExplanation.value = recalc.explanation ?? ''
    const taxDiff = _safeParseJson<{
      taxAccumDep?: number | null
      taxPeriodDep?: number | null
      taxRate?: number | null
      explanation?: string
    }>(_getItem(`${ITEM_PREFIX}-tax-diff`)?.remark, {})
    taxAccumDep.value = taxDiff.taxAccumDep == null ? null : Number(taxDiff.taxAccumDep)
    taxPeriodDep.value = taxDiff.taxPeriodDep == null ? null : Number(taxDiff.taxPeriodDep)
    taxRate.value = taxDiff.taxRate == null ? null : Number(taxDiff.taxRate)
    taxDiffExplanation.value = taxDiff.explanation ?? ''
  }

  // ─── H1-2 / H1-19 取数 ─────────────────────────────────────────────────────

  const _detailRows = computed(() => {
    if (options?.crossSheetDetailRows?.value?.length) {
      return options.crossSheetDetailRows.value
    }
    const raw = _getItem('H1-2-rows')?.remark
    return _safeParseJson<any[]>(raw, [])
  })

  const _leaseRows = computed(() => {
    const raw = _getItem('H1-19-rows')?.remark
    return _safeParseJson<any[]>(raw, [])
  })

  const faTotals = computed(() => {
    let costBegin = 0
    let costEnd = 0
    let increase = 0
    let decrease = 0
    let accDepBegin = 0
    let accDepEnd = 0
    let periodDep = 0
    let impairmentBegin = 0
    let impairmentEnd = 0
    let netEnd = 0

    for (const row of _detailRows.value) {
      costBegin += _num(row.originalCostBegin)
      costEnd += _num(row.originalCostEnd)
      increase += _num(row.originalCostIncrease)
      decrease += _num(row.originalCostDecrease)
      accDepBegin += _num(row.accDepBegin)
      accDepEnd += _num(row.accDepEnd)
      periodDep += _num(row.accDepProvision)
      impairmentBegin += _num(row.impairmentBegin)
      impairmentEnd += _num(row.impairmentEnd)
      const nv = row.netValue != null
        ? _num(row.netValue)
        : _num(row.originalCostEnd) - _num(row.accDepEnd) - _num(row.impairmentEnd)
      netEnd += nv
    }

    const netBegin = costBegin - accDepBegin - impairmentBegin
    return {
      costBegin, costEnd, increase, decrease,
      accDepBegin, accDepEnd, periodDep,
      impairmentBegin, impairmentEnd,
      netBegin, netEnd,
    }
  })

  const leaseRentAuto = computed(() =>
    calcSubtotal(_leaseRows.value.map((r) => _num(r.bookedRent ?? r.annualRent ?? r.expectedRent))),
  )

  const leaseCostAuto = computed(() =>
    calcSubtotal(_leaseRows.value.map((r) => _num(r.originalCost))),
  )

  // ─── 按分类聚合 ────────────────────────────────────────────────────────────

  const _byCategoryMap = computed(() => {
    const map = new Map<string, {
      originalCostBegin: number
      originalCostEnd: number
      increase: number
      decrease: number
      accDep: number
      periodDep: number
      netValue: number
      originalCost: number
    }>()

    for (const row of _detailRows.value) {
      const cat = row.category || '未分类'
      const existing = map.get(cat) ?? {
        originalCostBegin: 0, originalCostEnd: 0, increase: 0,
        decrease: 0, accDep: 0, periodDep: 0, netValue: 0, originalCost: 0,
      }
      existing.originalCostBegin += _num(row.originalCostBegin)
      existing.originalCostEnd += _num(row.originalCostEnd)
      existing.increase += _num(row.originalCostIncrease)
      existing.decrease += _num(row.originalCostDecrease)
      existing.accDep += _num(row.accDepEnd)
      existing.periodDep += _num(row.accDepProvision)
      const nv = row.netValue != null
        ? _num(row.netValue)
        : _num(row.originalCostEnd) - _num(row.accDepEnd) - _num(row.impairmentEnd)
      existing.netValue += nv
      existing.originalCost += _num(row.originalCostEnd)
      map.set(cat, existing)
    }
    return map
  })

  // ─── 比例分析（致同 H1-6 核心）────────────────────────────────────────────

  const ratioRows = computed<RatioRow[]>(() => {
    const t = faTotals.value
    const inp = ratioInputs.value
    const rentCurrent = inp.rentalIncomeCurrent ?? (leaseRentAuto.value > 0 ? leaseRentAuto.value : null)
    const leasedCurrent = inp.leasedInCostCurrent

    const currentMap: Record<string, { value: number | null; auto: boolean }> = {
      net_to_assets: {
        value: calcRatioPct(t.netEnd, inp.totalAssetsCurrent ?? 0),
        auto: inp.totalAssetsCurrent != null && t.netEnd !== 0,
      },
      period_dep_rate: {
        value: calcRatioPct(t.periodDep, t.costEnd),
        auto: t.costEnd > 0,
      },
      acc_dep_rate: {
        value: calcRatioPct(t.accDepEnd, t.costEnd),
        auto: t.costEnd > 0,
      },
      impairment_rate: {
        value: calcRatioPct(t.impairmentEnd, t.costEnd),
        auto: t.costEnd > 0,
      },
      cost_to_output: {
        value: calcRatioMultiple(t.costEnd, inp.productionVolumeCurrent ?? 0),
        auto: inp.productionVolumeCurrent != null && t.costEnd > 0,
      },
      leased_in_ratio: {
        value: calcRatioPct(leasedCurrent ?? 0, t.costEnd),
        auto: leasedCurrent != null && t.costEnd > 0,
      },
      rental_yield: {
        value: calcRatioPct(rentCurrent ?? 0, t.costEnd),
        auto: rentCurrent != null && t.costEnd > 0,
      },
      maintenance_ratio: {
        value: calcRatioPct(inp.maintenanceExpenseCurrent ?? 0, t.costEnd),
        auto: inp.maintenanceExpenseCurrent != null && t.costEnd > 0,
      },
    }

    const priorRent = inp.rentalIncomePrior
    const priorMap: Record<string, { value: number | null; auto: boolean }> = {
      net_to_assets: {
        value: calcRatioPct(t.netBegin, inp.totalAssetsPrior ?? 0),
        auto: inp.totalAssetsPrior != null && t.netBegin !== 0,
      },
      period_dep_rate: {
        value: calcRatioPct(inp.periodDepPrior ?? 0, t.costBegin),
        auto: inp.periodDepPrior != null && t.costBegin > 0,
      },
      acc_dep_rate: {
        value: calcRatioPct(t.accDepBegin, t.costBegin),
        auto: t.costBegin > 0,
      },
      impairment_rate: {
        value: calcRatioPct(t.impairmentBegin, t.costBegin),
        auto: t.costBegin > 0,
      },
      cost_to_output: {
        value: calcRatioMultiple(t.costBegin, inp.productionVolumePrior ?? 0),
        auto: inp.productionVolumePrior != null && t.costBegin > 0,
      },
      leased_in_ratio: {
        value: calcRatioPct(inp.leasedInCostPrior ?? 0, t.costBegin),
        auto: inp.leasedInCostPrior != null && t.costBegin > 0,
      },
      rental_yield: {
        value: calcRatioPct(priorRent ?? 0, t.costBegin),
        auto: priorRent != null && t.costBegin > 0,
      },
      maintenance_ratio: {
        value: calcRatioPct(inp.maintenanceExpensePrior ?? 0, t.costBegin),
        auto: inp.maintenanceExpensePrior != null && t.costBegin > 0,
      },
    }

    return RATIO_DEFS.map((def) => {
      const cur = currentMap[def.id]
      const pri = priorMap[def.id]
      const change = def.unit === 'pct'
        ? _ppChange(cur.value, pri.value)
        : _relChangePct(cur.value, pri.value)
      return {
        ...def,
        current: cur.value,
        prior: pri.value,
        change,
        explanation: ratioExplanations.value[def.id] || '',
        autoCurrent: cur.auto,
        autoPrior: pri.auto,
      }
    })
  })

  // ─── 结构分析 ──────────────────────────────────────────────────────────────

  const structureRows = computed<StructureRow[]>(() => {
    const totalNet = calcSubtotal(
      Array.from(_byCategoryMap.value.values()).map((v) => v.netValue),
    )
    return Array.from(_byCategoryMap.value.entries()).map(([cat, data]) => ({
      category: cat,
      costEnd: data.originalCost,
      netValue: data.netValue,
      proportion: calcProportion(data.netValue, totalNet),
      newRate: calcNewRate(data.netValue, data.originalCost),
      avgUsefulLife: calcAvgUsefulLife(data.originalCost, data.periodDep),
      remainingLife: calcRemainingLife(data.netValue, data.periodDep),
    }))
  })

  // ─── 变动分析 ──────────────────────────────────────────────────────────────

  const changeRows = computed<ChangeRow[]>(() => {
    return Array.from(_byCategoryMap.value.entries()).map(([cat, data]) => {
      const changeAmount = data.originalCostEnd - data.originalCostBegin
      return {
        category: cat,
        priorEnd: data.originalCostBegin,
        currentEnd: data.originalCostEnd,
        changeAmount,
        changeRate: calcChangeRate(data.originalCostEnd, data.originalCostBegin),
        increase: data.increase,
        decrease: data.decrease,
        increaseRate: data.originalCostBegin > 0
          ? (data.increase / data.originalCostBegin * 100) : null,
        decreaseRate: data.originalCostBegin > 0
          ? (data.decrease / data.originalCostBegin * 100) : null,
        depCoverageRate: data.originalCost > 0
          ? (data.accDep / data.originalCost * 100) : null,
        explanation: changeExplanations.value[cat] || '',
      }
    })
  })

  // ─── 异常标记 ──────────────────────────────────────────────────────────────

  const anomalies = computed<AnomalyFlag[]>(() => {
    const flags: AnomalyFlag[] = []

    for (const row of structureRows.value) {
      if (row.newRate != null && row.newRate < THRESHOLD_NEW_RATE) {
        flags.push({
          category: row.category,
          type: 'low_new_rate',
          value: row.newRate,
          threshold: THRESHOLD_NEW_RATE,
          message: `${row.category}成新率${row.newRate.toFixed(1)}%，老旧资产占比过高`,
        })
      }
    }

    for (const row of changeRows.value) {
      if (row.increaseRate != null && row.increaseRate > THRESHOLD_CHANGE_RATE) {
        flags.push({
          category: row.category,
          type: 'high_increase',
          value: row.increaseRate,
          threshold: THRESHOLD_CHANGE_RATE,
          message: `${row.category}增加率${row.increaseRate.toFixed(1)}%，变动幅度较大`,
        })
      }
      if (row.decreaseRate != null && row.decreaseRate > THRESHOLD_CHANGE_RATE) {
        flags.push({
          category: row.category,
          type: 'high_decrease',
          value: row.decreaseRate,
          threshold: THRESHOLD_CHANGE_RATE,
          message: `${row.category}减少率${row.decreaseRate.toFixed(1)}%，变动幅度较大`,
        })
      }
    }

    for (const row of ratioRows.value) {
      if (row.change == null) continue
      const abs = Math.abs(row.change)
      const hit = row.unit === 'pct' ? abs > THRESHOLD_RATIO_PP : abs > THRESHOLD_RATIO_REL
      if (hit) {
        flags.push({
          category: row.name,
          type: 'ratio_change',
          value: row.change,
          threshold: row.unit === 'pct' ? THRESHOLD_RATIO_PP : THRESHOLD_RATIO_REL,
          message: row.unit === 'pct'
            ? `${row.name}变动${row.change.toFixed(2)}个百分点，请解释合理性`
            : `${row.name}相对变动${row.change.toFixed(1)}%，请解释合理性`,
        })
      }
    }

    return flags
  })

  // ─── 折旧合理性整体重算（实质性分析程序）────────────────────────────────────

  const depreciationRecalc = computed<DepreciationRecalc>(() => {
    const t = faTotals.value
    const avgCost = (t.costBegin + t.costEnd) / 2
    const bookedDep = t.periodDep
    const priorDep = ratioInputs.value.periodDepPrior
    let compositeRate: number | null = null
    let source = ''
    if (depRecalcRate.value != null && depRecalcRate.value > 0) {
      compositeRate = depRecalcRate.value
      source = '手工输入综合年折旧率'
    } else if (priorDep != null && t.costBegin > 0) {
      compositeRate = (priorDep / t.costBegin) * 100
      source = '上期综合折旧率（上期计提÷期初原值）'
    }
    const hasBasis = compositeRate != null && avgCost > 0
    const expectedDep = hasBasis ? avgCost * (compositeRate! / 100) : null
    const diff = expectedDep != null ? bookedDep - expectedDep : null
    const diffRate = expectedDep != null && Math.abs(expectedDep) > 0.005
      ? (diff! / expectedDep) * 100
      : null
    const flagged = diffRate != null && Math.abs(diffRate) > THRESHOLD_DEP_RECALC
    return {
      avgCost,
      bookedDep,
      priorDep,
      compositeRate,
      compositeRateSource: source,
      expectedDep,
      diff,
      diffRate,
      threshold: THRESHOLD_DEP_RECALC,
      flagged,
      hasBasis,
    }
  })

  function _persistDepRecalc(): void {
    _persist(`${ITEM_PREFIX}-dep-recalc`, {
      rate: depRecalcRate.value,
      explanation: depRecalcExplanation.value,
    })
  }

  function setDepRecalcRate(v: number | null): void {
    depRecalcRate.value = v == null || (v as unknown as string) === '' ? null : Number(v)
    _persistDepRecalc()
  }

  function setDepRecalcExplanation(text: string): void {
    depRecalcExplanation.value = text
    _persistDepRecalc()
  }

  // ─── 折旧税会差异 → 递延所得税 ───────────────────────────────────────────────

  const deferredTaxRecalc = computed<DeferredTaxRecalc>(() => {
    const t = faTotals.value
    const bookCarrying = t.costEnd - t.accDepEnd - t.impairmentEnd
    const rate = taxRate.value != null && taxRate.value > 0 ? taxRate.value : DEFAULT_TAX_RATE
    const hasBasis = taxAccumDep.value != null
    const taxBase = hasBasis ? t.costEnd - (taxAccumDep.value as number) : null
    const temporaryDiff = taxBase != null ? bookCarrying - taxBase : null
    const deductibleTD = temporaryDiff != null ? Math.max(-temporaryDiff, 0) : 0
    const taxableTD = temporaryDiff != null ? Math.max(temporaryDiff, 0) : 0
    const periodDepDiff = taxPeriodDep.value != null ? t.periodDep - taxPeriodDep.value : null
    let nature: 'deductible' | 'taxable' | 'none' = 'none'
    if (temporaryDiff != null) {
      if (deductibleTD > 0.005) nature = 'deductible'
      else if (taxableTD > 0.005) nature = 'taxable'
    }
    return {
      bookCarrying,
      taxBase,
      temporaryDiff,
      deductibleTD,
      taxableTD,
      taxRate: rate,
      deferredTaxAsset: deductibleTD * (rate / 100),
      deferredTaxLiability: taxableTD * (rate / 100),
      nature,
      periodDepDiff,
      hasBasis,
    }
  })

  function _persistTaxDiff(): void {
    _persist(`${ITEM_PREFIX}-tax-diff`, {
      taxAccumDep: taxAccumDep.value,
      taxPeriodDep: taxPeriodDep.value,
      taxRate: taxRate.value,
      explanation: taxDiffExplanation.value,
    })
  }

  function setTaxAccumDep(v: number | null): void {
    taxAccumDep.value = v == null || (v as unknown as string) === '' ? null : Number(v)
    _persistTaxDiff()
  }

  function setTaxPeriodDep(v: number | null): void {
    taxPeriodDep.value = v == null || (v as unknown as string) === '' ? null : Number(v)
    _persistTaxDiff()
  }

  function setTaxRate(v: number | null): void {
    taxRate.value = v == null || (v as unknown as string) === '' ? null : Number(v)
    _persistTaxDiff()
  }

  function setTaxDiffExplanation(text: string): void {
    taxDiffExplanation.value = text
    _persistTaxDiff()
  }

  // ─── Save API ──────────────────────────────────────────────────────────────

  function saveNote(note: string): void {
    auditNote.value = note
    _persist(`${ITEM_PREFIX}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    _persist(`${ITEM_PREFIX}-audit-conclusion`, conclusion)
  }

  function updateRatioInput<K extends keyof RatioInputs>(key: K, value: RatioInputs[K]): void {
    ratioInputs.value = { ...ratioInputs.value, [key]: _nullableNum(value) as RatioInputs[K] }
    _persist(`${ITEM_PREFIX}-ratio-inputs`, ratioInputs.value)
  }

  function setRatioExplanation(id: string, text: string): void {
    ratioExplanations.value = { ...ratioExplanations.value, [id]: text }
    _persist(`${ITEM_PREFIX}-ratio-explanations`, ratioExplanations.value)
  }

  function setChangeExplanation(category: string, text: string): void {
    changeExplanations.value = { ...changeExplanations.value, [category]: text }
    _persist(`${ITEM_PREFIX}-change-explanations`, changeExplanations.value)
  }

  watch(allResponses, () => _loadData(), { immediate: true })

  return {
    auditNote,
    auditConclusion,
    ratioInputs,
    ratioRows,
    structureRows,
    changeRows,
    anomalies,
    faTotals,
    leaseRentAuto,
    leaseCostAuto,
    depreciationRecalc,
    depRecalcRate,
    depRecalcExplanation,
    setDepRecalcRate,
    setDepRecalcExplanation,
    deferredTaxRecalc,
    taxAccumDep,
    taxPeriodDep,
    taxRate,
    taxDiffExplanation,
    setTaxAccumDep,
    setTaxPeriodDep,
    setTaxRate,
    setTaxDiffExplanation,
    saveNote,
    saveConclusion,
    updateRatioInput,
    setRatioExplanation,
    setChangeExplanation,
    THRESHOLD_NEW_RATE,
    THRESHOLD_CHANGE_RATE,
    THRESHOLD_RATIO_PP,
    THRESHOLD_RATIO_REL,
    THRESHOLD_DEP_RECALC,
  }
}

export default useH1Analysis
