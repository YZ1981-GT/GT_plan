/**
 * useI2Analysis — I2-5 实质性分析 composable（31公式）
 *
 * 科目：1717开发支出（借方/资产类）
 *
 * 分析表列结构（Req 4.1）：
 * 项目 | 期初 | 本期增加 | 本期减少 | 期末 | 上期期末 | 同比变动率 | 预期值 | 差异 | 超阈值标记 |
 * 分析结论 | 异常原因 | 审计应对 | 备注
 *
 * 公式引擎接入（Req 4.2）：
 * - 期末 = 期初 + 本期增加 - 本期减少              [calcAssetEndBalance]
 * - 同比变动率 = (期末 - 上期期末) / 上期期末       [calcChangeRate]
 * - 差异 = 期末 - 预期值                           [calcVarianceFromExpected]
 * - 超阈值标记 = |差异| > 重要性水平                [布尔判断]
 *
 * 超重要性水平差异红色标记（Req 4.3）
 * AI辅助分析异常原因（Req 4.4）
 *
 * 数据持久化：JSON-pack 到 'I2-5-rows' key
 *
 * Spec: .kiro/specs/i2-development-expenditure/
 * Task: 3.5
 * Requirements: 4.1-4.4
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcAssetEndBalance,
  calcChangeRate,
  calcVarianceFromExpected,
  calcSubtotal,
} from './useI2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** I2-5 实质性分析行 */
export interface AnalysisRow {
  /** 项目名称（研发项目） */
  projectName: string
  /** 期初金额 */
  beginAmount: number
  /** 本期增加（资本化投入） */
  increaseAmount: number
  /** 本期减少（转无形/转费用） */
  decreaseAmount: number
  /** 期末金额（公式列：期初 + 增加 - 减少） */
  endAmount: number
  /** 上期期末金额（同比基数） */
  priorEndAmount: number
  /** 同比变动率（公式列：(期末 - 上期期末) / 上期期末；上期为0时null） */
  changeRate: number | null
  /** 预期值（审计师预期金额） */
  expectedValue: number
  /** 差异（公式列：期末 - 预期值） */
  variance: number
  /** 超重要性水平标记（公式列：|差异| > materialityLevel） */
  exceedThreshold: boolean
  /** 分析结论 */
  analysisConclusion: string
  /** 异常原因 */
  anomalyReason: string
  /** 审计应对 */
  auditResponse: string
  /** 备注 */
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 持久化 key（JSON打包存1条，铁律：>100行必须JSON打包） */
const ROWS_KEY = 'I2-5-rows'

/** 默认重要性水平金额（元），通常由B15模块传入 */
const DEFAULT_MATERIALITY = 0

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI2Analysis(params: {
  allResponses: Ref<Map<string, any>>
  saveResponses: (sheetCode: string, data: Record<string, any>) => Promise<void>
  materialityLevel?: Ref<number>
}): {
  rows: Ref<AnalysisRow[]>
  totalRow: ComputedRef<AnalysisRow>
  anomalyRows: ComputedRef<{ rowIndex: number; variance: number }[]>
  hasAnomalies: ComputedRef<boolean>
  addRow: (projectName: string) => void
  removeRow: (index: number) => void
  updateField: (rowIndex: number, field: string, value: any) => void
  save: () => Promise<void>
} {
  const { allResponses, saveResponses, materialityLevel } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<AnalysisRow[]>([])

  // ─── Helpers ───────────────────────────────────────────────────────────────

  /** 从 allResponses 获取 JSON 数据 */
  function _getJson(key: string): any {
    const item = allResponses.value.get(key)
    if (!item) return null
    const raw = item.remark ?? item.conclusion ?? item
    if (raw == null) return null
    if (typeof raw === 'object') return raw
    try { return JSON.parse(raw as string) } catch { return null }
  }

  /** 获取当前重要性水平 */
  function _getMateriality(): number {
    return materialityLevel?.value ?? DEFAULT_MATERIALITY
  }

  /** 创建空行 */
  function _createEmptyRow(projectName: string): AnalysisRow {
    return {
      projectName,
      beginAmount: 0,
      increaseAmount: 0,
      decreaseAmount: 0,
      endAmount: 0,
      priorEndAmount: 0,
      changeRate: null,
      expectedValue: 0,
      variance: 0,
      exceedThreshold: false,
      analysisConclusion: '',
      anomalyReason: '',
      auditResponse: '',
      remark: '',
    }
  }

  /** 重算单行公式列 */
  function _recalcRowFormulas(row: AnalysisRow): void {
    // 期末 = 期初 + 增加 - 减少（资产类借方科目1717）
    row.endAmount = calcAssetEndBalance(row.beginAmount, row.increaseAmount, row.decreaseAmount)

    // 同比变动率 = (期末 - 上期期末) / 上期期末
    row.changeRate = calcChangeRate(row.endAmount, row.priorEndAmount)

    // 差异 = 期末 - 预期值
    row.variance = calcVarianceFromExpected(row.endAmount, row.expectedValue)

    // 超阈值标记 = |差异| > 重要性水平
    const matLevel = _getMateriality()
    row.exceedThreshold = matLevel > 0 && Math.abs(row.variance) > matLevel
  }

  // ─── Init / Load ───────────────────────────────────────────────────────────

  function _loadFromResponses(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map((raw: any) => {
        const row: AnalysisRow = {
          projectName: String(raw.projectName ?? ''),
          beginAmount: Number(raw.beginAmount) || 0,
          increaseAmount: Number(raw.increaseAmount) || 0,
          decreaseAmount: Number(raw.decreaseAmount) || 0,
          endAmount: Number(raw.endAmount) || 0,
          priorEndAmount: Number(raw.priorEndAmount) || 0,
          changeRate: null,
          expectedValue: Number(raw.expectedValue) || 0,
          variance: 0,
          exceedThreshold: false,
          analysisConclusion: String(raw.analysisConclusion ?? ''),
          anomalyReason: String(raw.anomalyReason ?? ''),
          auditResponse: String(raw.auditResponse ?? ''),
          remark: String(raw.remark ?? ''),
        }
        // 重算公式列确保一致性
        _recalcRowFormulas(row)
        return row
      })
    } else {
      rows.value = []
    }
  }

  // 监听 allResponses 变化自动加载
  watch(allResponses, () => _loadFromResponses(), { immediate: true })

  // 监听重要性水平变化，刷新所有行的超阈值标记
  if (materialityLevel) {
    watch(materialityLevel, () => {
      for (const row of rows.value) {
        const matLevel = _getMateriality()
        row.exceedThreshold = matLevel > 0 && Math.abs(row.variance) > matLevel
      }
    })
  }

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  /**
   * 合计行 = SUM(所有明细行各数值列)
   * CP-I2-06: 合计行=SUM(明细行)
   */
  const totalRow: ComputedRef<AnalysisRow> = computed(() => {
    const r = rows.value
    const beginAmount = calcSubtotal(r.map(row => row.beginAmount))
    const increaseAmount = calcSubtotal(r.map(row => row.increaseAmount))
    const decreaseAmount = calcSubtotal(r.map(row => row.decreaseAmount))
    const endAmount = calcAssetEndBalance(beginAmount, increaseAmount, decreaseAmount)
    const priorEndAmount = calcSubtotal(r.map(row => row.priorEndAmount))
    const changeRate = calcChangeRate(endAmount, priorEndAmount)
    const expectedValue = calcSubtotal(r.map(row => row.expectedValue))
    const variance = calcVarianceFromExpected(endAmount, expectedValue)
    const matLevel = _getMateriality()
    const exceedThreshold = matLevel > 0 && Math.abs(variance) > matLevel

    return {
      projectName: '合计',
      beginAmount,
      increaseAmount,
      decreaseAmount,
      endAmount,
      priorEndAmount,
      changeRate,
      expectedValue,
      variance,
      exceedThreshold,
      analysisConclusion: '',
      anomalyReason: '',
      auditResponse: '',
      remark: '',
    }
  })

  // ─── Computed: 异常行列表（超重要性水平差异）────────────────────────────────

  /**
   * 超重要性水平差异的行列表（Req 4.3: 红色标记）
   * 返回超阈值行的 index 和 variance 供 UI 红色高亮
   */
  const anomalyRows: ComputedRef<{ rowIndex: number; variance: number }[]> = computed(() => {
    const anomalies: { rowIndex: number; variance: number }[] = []
    for (let i = 0; i < rows.value.length; i++) {
      if (rows.value[i].exceedThreshold) {
        anomalies.push({ rowIndex: i, variance: rows.value[i].variance })
      }
    }
    return anomalies
  })

  /** 是否存在超阈值异常 */
  const hasAnomalies: ComputedRef<boolean> = computed(() => anomalyRows.value.length > 0)

  // ─── Actions: addRow ───────────────────────────────────────────────────────

  /**
   * 新增分析行。
   * 交互规范：需先弹 ElMessageBox.prompt 输入项目名称确认后再创建（由Vue组件层处理）。
   */
  function addRow(projectName: string): void {
    if (!projectName || !projectName.trim()) return
    const newRow = _createEmptyRow(projectName.trim())
    rows.value.push(newRow)
  }

  // ─── Actions: removeRow ────────────────────────────────────────────────────

  /** 删除指定索引的行 */
  function removeRow(index: number): void {
    if (index < 0 || index >= rows.value.length) return
    rows.value.splice(index, 1)
  }

  // ─── Actions: updateField ──────────────────────────────────────────────────

  /**
   * 更新指定行指定字段的值，自动重算公式列。
   *
   * 可编辑字段：projectName / beginAmount / increaseAmount / decreaseAmount /
   *   priorEndAmount / expectedValue / analysisConclusion / anomalyReason / auditResponse / remark
   *
   * 公式列（endAmount / changeRate / variance / exceedThreshold）不可直接编辑。
   */
  function updateField(rowIndex: number, field: string, value: any): void {
    if (rowIndex < 0 || rowIndex >= rows.value.length) return
    const row = rows.value[rowIndex]

    switch (field) {
      case 'projectName':
        row.projectName = String(value ?? '')
        break
      case 'beginAmount':
        row.beginAmount = Number(value) || 0
        break
      case 'increaseAmount':
        row.increaseAmount = Number(value) || 0
        break
      case 'decreaseAmount':
        row.decreaseAmount = Number(value) || 0
        break
      case 'priorEndAmount':
        row.priorEndAmount = Number(value) || 0
        break
      case 'expectedValue':
        row.expectedValue = Number(value) || 0
        break
      case 'analysisConclusion':
        row.analysisConclusion = String(value ?? '')
        return // 文本字段不需要重算公式
      case 'anomalyReason':
        row.anomalyReason = String(value ?? '')
        return
      case 'auditResponse':
        row.auditResponse = String(value ?? '')
        return
      case 'remark':
        row.remark = String(value ?? '')
        return
      default:
        // 公式列不可直接编辑，忽略
        return
    }

    // 重算公式列
    _recalcRowFormulas(row)
  }

  // ─── Actions: save ─────────────────────────────────────────────────────────

  /**
   * 持久化实质性分析行数据到 allResponses。
   * key = 'I2-5-rows'（JSON打包存1条）
   * 铁律：>100行的动态数据必须JSON打包存1条
   */
  async function save(): Promise<void> {
    // 序列化仅保存输入字段（公式列运行时重算）
    const toPersist = rows.value.map(row => ({
      projectName: row.projectName,
      beginAmount: row.beginAmount,
      increaseAmount: row.increaseAmount,
      decreaseAmount: row.decreaseAmount,
      priorEndAmount: row.priorEndAmount,
      expectedValue: row.expectedValue,
      analysisConclusion: row.analysisConclusion,
      anomalyReason: row.anomalyReason,
      auditResponse: row.auditResponse,
      remark: row.remark,
    }))

    // 使用 saveResponses 存储：sheetCode='5' → item_id = 'I2-5-rows'
    await saveResponses('5', { [ROWS_KEY]: toPersist })
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    totalRow,
    anomalyRows,
    hasAnomalies,
    addRow,
    removeRow,
    updateField,
    save,
  }
}

export default useI2Analysis
