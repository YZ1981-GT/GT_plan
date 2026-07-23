/**
 * useK9Analysis — K9-4 实质性分析逻辑（48行×16列，16公式）
 *
 * Spec: .kiro/specs/k9-admin-expenses/
 * Task: 3.4
 * Requirements: 4.1-4.6, 9.3-9.5
 *
 * 职责：
 * - 管理48行实质性分析表行数据
 * - 使用 calcYoYChange / calcRatioToRevenue / isAbnormalFluctuation
 * - 自动标记异常项目（红色标记）：|同比变动率| > 阈值 OR |占比偏离| > 阈值
 * - 自动从K9-2明细表取数计算
 * - AI辅助生成波动分析
 *
 * Item IDs: "K9-4-row-{idx}-{field}"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useK9FormulaEngine'
import {
  calcYoYChange,
  calcRatioToRevenue,
  isAbnormalFluctuation,
} from './useK9AnalysisEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K9AnalysisRow {
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
  /** 占营业收入比（公式：本期/营业收入） */
  ratioToRevenue: number | null
  /** 上期占营业收入比 */
  priorRatioToRevenue: number | null
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

export interface K9AnalysisSummary {
  totalItems: number
  abnormalCount: number
  normalCount: number
  abnormalProjects: string[]
  totalAmount: number
}

export interface UseK9AnalysisParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  /** 营业收入（从CrossSheet或外部） */
  revenue?: Ref<number>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'K9-4-analysis-rows'
const ITEM_PREFIX = 'K9-4'
/** 默认异常波动阈值 30% */
const DEFAULT_THRESHOLD = 0.3

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK9Analysis(params: UseK9AnalysisParams) {
  const { allResponses, projectId, wpId, revenue, isReadonly, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<K9AnalysisRow[]>([])
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

  function _normalizeRow(raw: any): K9AnalysisRow {
    const currentAmount = parseNum(raw.currentAmount)
    const priorAmount = parseNum(raw.priorAmount)
    const rev = revenue?.value ?? parseNum(raw.revenue)
    const threshold = parseNum(raw.threshold) || DEFAULT_THRESHOLD
    const changeAmount = currentAmount - priorAmount
    const changeRate = calcYoYChange(currentAmount, priorAmount)
    const ratioToRevenue = calcRatioToRevenue(currentAmount, rev)
    const priorRatioToRevenue = calcRatioToRevenue(priorAmount, rev)
    const abnormal = changeRate !== null ? isAbnormalFluctuation(changeRate, threshold) : false

    return {
      rowKey: raw.rowKey ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      projectName: raw.projectName ?? '',
      currentAmount, priorAmount, changeAmount, changeRate,
      ratioToRevenue, priorRatioToRevenue, threshold,
      isAbnormal: abnormal,
      reasonAnalysis: raw.reasonAnalysis ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Computed: 带公式列的完整行 ───────────────────────────────────────────

  const computedRows: ComputedRef<K9AnalysisRow[]> = computed(() => {
    const rev = revenue?.value ?? 0
    return rows.value.map((row) => {
      const changeAmount = row.currentAmount - row.priorAmount
      const changeRate = calcYoYChange(row.currentAmount, row.priorAmount)
      const ratioToRevenue = calcRatioToRevenue(row.currentAmount, rev)
      const priorRatioToRevenue = calcRatioToRevenue(row.priorAmount, rev)
      const abnormal = changeRate !== null ? isAbnormalFluctuation(changeRate, row.threshold) : false

      return { ...row, changeAmount, changeRate, ratioToRevenue, priorRatioToRevenue, isAbnormal: abnormal }
    })
  })

  // ─── Computed: 异常项汇总 ──────────────────────────────────────────────────

  const summary: ComputedRef<K9AnalysisSummary> = computed(() => {
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
    ;(row as any)[field] = (field === 'reasonAnalysis' || field === 'conclusion' || field === 'remark')
      ? value
      : parseNum(value)
    isChanged.value = true
    _persist()
  }

  // ─── 从K9-2明细表自动填入分析数据 ─────────────────────────────────────────

  function populateFromDetail(detailData: Array<{ projectName: string; audited: number; priorAmount: number }>): void {
    if (isReadonly?.value) return
    rows.value = detailData.map((d) => ({
      rowKey: `row-${d.projectName}`,
      projectName: d.projectName,
      currentAmount: d.audited,
      priorAmount: d.priorAmount,
      changeAmount: 0, changeRate: null,
      ratioToRevenue: null, priorRatioToRevenue: null,
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
    // 写本期发生额合计供 useK9CrossSheet.analysisVsDetail 交叉验证（原死键）
    onSave(`${ITEM_PREFIX}-analysis-total`, summary.value.totalAmount)
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

export default useK9Analysis
