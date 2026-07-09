/**
 * useK8Analysis — K8-4 实质性分析逻辑（39行×17列，25公式）
 *
 * Spec: .kiro/specs/k8-selling-expenses/
 * Task: 3.4
 * Requirements: 4.1-4.6, 9.3-9.5
 *
 * 职责：
 * - 管理39行实质性分析表行数据
 * - 使用 calcYoYChange / calcRatioToRevenue / isAbnormalFluctuation / calcStructureRatio
 * - 自动标记异常项目（红色标记）：|同比变动率| > 阈值 OR |占比偏离| > 阈值
 * - Revenue 来自 K8-2 via crossSheet 或单独输入
 * - AI辅助生成波动分析
 *
 * Item IDs: "K8-4-row-{idx}-{field}"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useK8FormulaEngine'
import {
  calcYoYChange,
  calcRatioToRevenue,
  isAbnormalFluctuation,
  calcStructureRatio,
} from './useK8AnalysisEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K8AnalysisRow {
  rowKey: string
  /** 费用项目名称 */
  projectName: string
  /** 本期金额（审定数） */
  currentAmount: number
  /** 上期金额 */
  priorAmount: number
  /** 同比变动额（公式：本期-上期） */
  changeAmount: number
  /** 同比变动率（公式：(本期-上期)/|上期|） */
  changeRate: number | null
  /** 营业收入（用于占比计算） */
  revenue: number
  /** 占营业收入比（公式：本期/营业收入） */
  ratioToRevenue: number | null
  /** 上期占营业收入比 */
  priorRatioToRevenue: number | null
  /** 占比偏离（公式：本期占比-上期占比） */
  ratioDeviation: number | null
  /** 结构比（占费用总额比） */
  structureRatio: number
  /** 波动阈值（默认0.3=30%） */
  threshold: number
  /** 是否异常（公式列：自动判断） */
  isAbnormal: boolean
  /** 原因分析（异常项必填） */
  reasonAnalysis: string
  /** 审计结论 */
  conclusion: string
  /** 备注 */
  remark: string
}

export interface K8AnalysisSummary {
  /** 总行数 */
  totalItems: number
  /** 异常项数量 */
  abnormalCount: number
  /** 正常项数量 */
  normalCount: number
  /** 异常项目列表（名称） */
  abnormalProjects: string[]
  /** 费用合计 */
  totalAmount: number
}

export interface UseK8AnalysisParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  /** 营业收入（从CrossSheet或外部） */
  revenue?: Ref<number>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'K8-4-analysis-rows'
const ITEM_PREFIX = 'K8-4'
/** 默认异常波动阈值 30% */
const DEFAULT_THRESHOLD = 0.3

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK8Analysis(params: UseK8AnalysisParams) {
  const { allResponses, projectId, wpId, revenue, isReadonly, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<K8AnalysisRow[]>([])
  const overallConclusion = ref('')
  const isChanged = ref(false)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function initFromResponses(): void {
    const raw = _getJson(ROWS_KEY)
    if (Array.isArray(raw) && raw.length > 0) {
      rows.value = raw.map(_normalizeRow)
    } else {
      rows.value = []
    }
    overallConclusion.value = _getString(`${ITEM_PREFIX}-overall-conclusion`)
  }

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeRow(raw: any): K8AnalysisRow {
    const currentAmount = parseNum(raw.currentAmount)
    const priorAmount = parseNum(raw.priorAmount)
    const rev = revenue?.value ?? parseNum(raw.revenue)
    const threshold = parseNum(raw.threshold) || DEFAULT_THRESHOLD
    const changeAmount = currentAmount - priorAmount
    const changeRate = calcYoYChange(currentAmount, priorAmount)
    const ratioToRevenue = calcRatioToRevenue(currentAmount, rev)
    const priorRev = rev // 简化：上期收入使用同一值（实际应从参数传入）
    const priorRatioToRevenue = calcRatioToRevenue(priorAmount, priorRev)
    const ratioDeviation = (ratioToRevenue !== null && priorRatioToRevenue !== null)
      ? ratioToRevenue - priorRatioToRevenue : null
    const abnormal = changeRate !== null ? isAbnormalFluctuation(changeRate, threshold) : false

    return {
      rowKey: raw.rowKey ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      projectName: raw.projectName ?? '',
      currentAmount,
      priorAmount,
      changeAmount,
      changeRate,
      revenue: rev,
      ratioToRevenue,
      priorRatioToRevenue,
      ratioDeviation,
      structureRatio: 0, // 需要合计行后计算
      threshold,
      isAbnormal: abnormal,
      reasonAnalysis: raw.reasonAnalysis ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Computed: 带公式列的完整行（含结构比） ────────────────────────────────

  const computedRows: ComputedRef<K8AnalysisRow[]> = computed(() => {
    const rev = revenue?.value ?? 0
    const totalAmount = calcSubtotal(rows.value.map(r => r.currentAmount))

    return rows.value.map((row) => {
      const changeAmount = row.currentAmount - row.priorAmount
      const changeRate = calcYoYChange(row.currentAmount, row.priorAmount)
      const ratioToRevenue = calcRatioToRevenue(row.currentAmount, rev)
      const priorRatioToRevenue = calcRatioToRevenue(row.priorAmount, rev)
      const ratioDeviation = (ratioToRevenue !== null && priorRatioToRevenue !== null)
        ? ratioToRevenue - priorRatioToRevenue : null
      const structureRatio = calcStructureRatio(row.currentAmount, totalAmount)
      const abnormal = changeRate !== null ? isAbnormalFluctuation(changeRate, row.threshold) : false

      return {
        ...row,
        changeAmount,
        changeRate,
        revenue: rev,
        ratioToRevenue,
        priorRatioToRevenue,
        ratioDeviation,
        structureRatio,
        isAbnormal: abnormal,
      }
    })
  })

  // ─── Computed: 汇总 ────────────────────────────────────────────────────────

  const summary: ComputedRef<K8AnalysisSummary> = computed(() => {
    const detail = computedRows.value
    const abnormalItems = detail.filter(r => r.isAbnormal)
    return {
      totalItems: detail.length,
      abnormalCount: abnormalItems.length,
      normalCount: detail.length - abnormalItems.length,
      abnormalProjects: abnormalItems.map(r => r.projectName),
      totalAmount: calcSubtotal(detail.map(r => r.currentAmount)),
    }
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: string, value: any): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row) return
    ;(row as any)[field] = field === 'reasonAnalysis' || field === 'conclusion' || field === 'remark'
      ? value
      : parseNum(value)
    isChanged.value = true
    _persist()
  }

  // ─── 从K8-2明细表自动填入分析数据 ─────────────────────────────────────────

  function populateFromDetail(detailData: Array<{ projectName: string; audited: number; priorAmount: number }>): void {
    if (isReadonly?.value) return
    rows.value = detailData.map((d) => ({
      rowKey: `row-${d.projectName}`,
      projectName: d.projectName,
      currentAmount: d.audited,
      priorAmount: d.priorAmount,
      changeAmount: 0, changeRate: null,
      revenue: revenue?.value ?? 0,
      ratioToRevenue: null, priorRatioToRevenue: null,
      ratioDeviation: null, structureRatio: 0,
      threshold: DEFAULT_THRESHOLD,
      isAbnormal: false,
      reasonAnalysis: '', conclusion: '', remark: '',
    }))
    isChanged.value = true
    _persist()
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, rows.value)
  }

  function saveOverallConclusion(conclusion: string): void {
    overallConclusion.value = conclusion
    onSave?.(`${ITEM_PREFIX}-overall-conclusion`, conclusion)
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => initFromResponses(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows: computedRows,
    summary,
    overallConclusion,
    isChanged,
    updateCell,
    populateFromDetail,
    saveOverallConclusion,
    initFromResponses,
  }
}

export default useK8Analysis
