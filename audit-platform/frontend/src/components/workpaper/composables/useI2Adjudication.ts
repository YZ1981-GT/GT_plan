/**
 * useI2Adjudication — I2-1 审定表 composable（三角勾稽 + TB取数）
 *
 * 科目：1717开发支出（借方/资产类）
 *
 * 审定表列结构（Req 2.1）：
 * 项目 | 期初余额 | 本期增加-资本化 | 本期减少-转无形资产 | 本期减少-转费用 |
 * 期末余额 | 未审数 | AJE | RJE | 审定数 | 备注 | 三角勾稽差额
 *
 * 公式引擎接入：
 * - 期末余额 = 期初 + 增加(资本化) - 减少(转无形) - 减少(转费用)  [calcAssetEndBalance变体]
 * - 审定数 = 未审 + AJE + RJE                                   [calcAuditedAmount]
 * - 三角勾稽差额 = 期末 - (期初 + 增加 - 减少合计)               [calcTriangleReconciliation]
 * - 合计行 = SUM(各明细行)                                       [calcSubtotal]
 *
 * 数据持久化：以JSON存储到 allResponses，key='I2-1-rows'
 *
 * Spec: .kiro/specs/i2-development-expenditure/
 * Task: 3.3
 * Requirements: 2.1-2.7
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type { I2TbData } from './useI2FormData'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcTriangleReconciliation,
  calcSubtotal,
} from './useI2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** I2-1 审定表行 */
export interface AdjudicationRow {
  /** 项目名称（研发项目） */
  projectName: string
  /** 期初余额 */
  cipBegin: number
  /** 本期增加-资本化 */
  increaseCapitalized: number
  /** 本期减少-转无形资产 */
  decreaseTransfer: number
  /** 本期减少-转费用 */
  decreaseExpense: number
  /** 期末余额（公式列：期初 + 资本化增加 - 转无形 - 转费用） */
  cipEnd: number
  /** 未审数（from TB） */
  unadjusted: number
  /** AJE调整 */
  aje: number
  /** RJE重分类 */
  rje: number
  /** 审定数（公式列：未审 + AJE + RJE） */
  audited: number
  /** 备注 */
  remark: string
  /** 三角勾稽差额（公式列：期末 - (期初 + 增加 - 减少合计)） */
  reconciliationDiff: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'I2-1-rows'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI2Adjudication(params: {
  allResponses: Ref<Map<string, any>>
  tbData: Ref<I2TbData>
  saveResponses: (sheetCode: string, data: Record<string, any>) => Promise<void>
}): {
  rows: Ref<AdjudicationRow[]>
  totalRow: ComputedRef<AdjudicationRow>
  reconciliationErrors: ComputedRef<{ rowIndex: number; diff: number }[]>
  hasErrors: ComputedRef<boolean>
  addRow: (projectName: string) => void
  removeRow: (index: number) => void
  updateRow: (index: number, field: string, value: number | string) => void
  recalcRow: (index: number) => void
  save: () => Promise<void>
} {
  const { allResponses, tbData, saveResponses } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<AdjudicationRow[]>([])

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

  /** 创建空行 */
  function _createEmptyRow(projectName: string): AdjudicationRow {
    return {
      projectName,
      cipBegin: 0,
      increaseCapitalized: 0,
      decreaseTransfer: 0,
      decreaseExpense: 0,
      cipEnd: 0,
      unadjusted: 0,
      aje: 0,
      rje: 0,
      audited: 0,
      remark: '',
      reconciliationDiff: 0,
    }
  }

  /** 重算单行公式列 */
  function _recalcRowFormulas(row: AdjudicationRow): void {
    // 期末余额 = 期初 + 资本化增加 - 转无形 - 转费用
    // 借方/资产类：期末 = 期初 + 借方(增加) - 贷方(减少)
    // 此处 increase = increaseCapitalized; decrease = decreaseTransfer + decreaseExpense
    const totalDecrease = row.decreaseTransfer + row.decreaseExpense
    row.cipEnd = calcAssetEndBalance(row.cipBegin, row.increaseCapitalized, totalDecrease)

    // 审定数 = 未审 + AJE + RJE
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)

    // 三角勾稽差额 = 期末 - (期初 + 增加 - 减少合计)
    row.reconciliationDiff = calcTriangleReconciliation(
      row.cipBegin,
      row.increaseCapitalized,
      totalDecrease,
      row.cipEnd,
    )
  }

  // ─── Init / Load ───────────────────────────────────────────────────────────

  function _loadFromResponses(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map((raw: any) => {
        const row: AdjudicationRow = {
          projectName: String(raw.projectName ?? ''),
          cipBegin: Number(raw.cipBegin) || 0,
          increaseCapitalized: Number(raw.increaseCapitalized) || 0,
          decreaseTransfer: Number(raw.decreaseTransfer) || 0,
          decreaseExpense: Number(raw.decreaseExpense) || 0,
          cipEnd: Number(raw.cipEnd) || 0,
          unadjusted: Number(raw.unadjusted) || 0,
          aje: Number(raw.aje) || 0,
          rje: Number(raw.rje) || 0,
          audited: Number(raw.audited) || 0,
          remark: String(raw.remark ?? ''),
          reconciliationDiff: Number(raw.reconciliationDiff) || 0,
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

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  /** 合计行 = SUM(所有明细行各数值列) */
  const totalRow: ComputedRef<AdjudicationRow> = computed(() => {
    const r = rows.value
    const cipBegin = calcSubtotal(r.map(row => row.cipBegin))
    const increaseCapitalized = calcSubtotal(r.map(row => row.increaseCapitalized))
    const decreaseTransfer = calcSubtotal(r.map(row => row.decreaseTransfer))
    const decreaseExpense = calcSubtotal(r.map(row => row.decreaseExpense))
    const totalDecrease = decreaseTransfer + decreaseExpense
    const cipEnd = calcAssetEndBalance(cipBegin, increaseCapitalized, totalDecrease)
    const unadjusted = calcSubtotal(r.map(row => row.unadjusted))
    const aje = calcSubtotal(r.map(row => row.aje))
    const rje = calcSubtotal(r.map(row => row.rje))
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    const reconciliationDiff = calcTriangleReconciliation(cipBegin, increaseCapitalized, totalDecrease, cipEnd)

    return {
      projectName: '合计',
      cipBegin,
      increaseCapitalized,
      decreaseTransfer,
      decreaseExpense,
      cipEnd,
      unadjusted,
      aje,
      rje,
      audited,
      remark: '',
      reconciliationDiff,
    }
  })

  // ─── Computed: 三角勾稽错误行列表 ─────────────────────────────────────────

  /**
   * 三角勾稽校验错误：diff !== 0 的行
   * 差异行高亮（Req 2.4: 三角勾稽校验+红色高亮）
   */
  const reconciliationErrors: ComputedRef<{ rowIndex: number; diff: number }[]> = computed(() => {
    const errors: { rowIndex: number; diff: number }[] = []
    for (let i = 0; i < rows.value.length; i++) {
      const diff = rows.value[i].reconciliationDiff
      if (Math.abs(diff) > 0.01) {
        errors.push({ rowIndex: i, diff })
      }
    }
    return errors
  })

  /** 是否存在三角勾稽错误 */
  const hasErrors: ComputedRef<boolean> = computed(() => reconciliationErrors.value.length > 0)

  // ─── Actions: addRow ───────────────────────────────────────────────────────

  /**
   * 新增项目行。
   * 交互规范：需先弹 ElMessageBox.prompt 输入名称确认后再创建（由Vue组件层处理）。
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

  // ─── Actions: updateRow ────────────────────────────────────────────────────

  /**
   * 更新指定行指定字段的值，自动重算公式列。
   * 仅允许编辑输入字段：cipBegin / increaseCapitalized / decreaseTransfer / decreaseExpense /
   *   unadjusted / aje / rje / remark / projectName
   * 公式列（cipEnd / audited / reconciliationDiff）不可直接编辑。
   */
  function updateRow(index: number, field: string, value: number | string): void {
    if (index < 0 || index >= rows.value.length) return
    const row = rows.value[index]

    switch (field) {
      case 'projectName':
        row.projectName = String(value ?? '')
        break
      case 'cipBegin':
        row.cipBegin = Number(value) || 0
        break
      case 'increaseCapitalized':
        row.increaseCapitalized = Number(value) || 0
        break
      case 'decreaseTransfer':
        row.decreaseTransfer = Number(value) || 0
        break
      case 'decreaseExpense':
        row.decreaseExpense = Number(value) || 0
        break
      case 'unadjusted':
        row.unadjusted = Number(value) || 0
        break
      case 'aje':
        row.aje = Number(value) || 0
        break
      case 'rje':
        row.rje = Number(value) || 0
        break
      case 'remark':
        row.remark = String(value ?? '')
        break
      default:
        // 公式列不可直接编辑，忽略
        return
    }

    // 重算公式列
    _recalcRowFormulas(row)
  }

  // ─── Actions: recalcRow ────────────────────────────────────────────────────

  /** 对指定行强制重算公式列（外部调用入口） */
  function recalcRow(index: number): void {
    if (index < 0 || index >= rows.value.length) return
    _recalcRowFormulas(rows.value[index])
  }

  // ─── Actions: save ─────────────────────────────────────────────────────────

  /**
   * 持久化审定表行数据到 allResponses。
   * key = 'I2-1-rows'（通过 saveResponses(sheetCode='1', { rows: [...] })）
   * 铁律：>100行的动态数据必须JSON打包存1条
   */
  async function save(): Promise<void> {
    // 序列化仅保存输入字段（公式列运行时重算）
    const toPersist = rows.value.map(row => ({
      projectName: row.projectName,
      cipBegin: row.cipBegin,
      increaseCapitalized: row.increaseCapitalized,
      decreaseTransfer: row.decreaseTransfer,
      decreaseExpense: row.decreaseExpense,
      unadjusted: row.unadjusted,
      aje: row.aje,
      rje: row.rje,
      remark: row.remark,
    }))

    // 使用 saveResponses 存储：sheetCode='1' → item_id = 'I2-1-rows'
    // 直接操作 allResponses Map 并调用 saveResponses
    await saveResponses('1', { rows: toPersist })
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    totalRow,
    reconciliationErrors,
    hasErrors,
    addRow,
    removeRow,
    updateRow,
    recalcRow,
    save,
  }
}

export default useI2Adjudication
