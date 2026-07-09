/**
 * useM8RiskTest — M8-4 风险资产计提测试表 composable
 *
 * Spec: .kiro/specs/m8-general-risk-reserve/
 * Task: 3.4
 * Requirements: 3.3-3.7
 *
 * 职责：
 * - 管理一般风险准备按风险资产计提测试（30×11，29公式）
 * - 9 data rows (rows 10-18) + 1 total row (row 19)
 * - 列结构：
 *   A:项目 | B:本期计提 | C:其他 | D:提取标准 | E:基数(风险资产期末余额)
 *   F:比例(1.5%等) | G:应计金额(=E*F) | H:差异(=B-G) | I:差异原因
 *   J:相关依据索引号 | K:相关数据来源索引号
 * - 核心公式：
 *   G = E × F（应计提金额 = 风险资产期末余额 × 计提比例）
 *   H = B - G（差异 = 本期计提 - 应计金额）
 * - |差异|>阈值时红色高亮
 * - Row 19 合计: SUM(B10:B18), SUM(C10:C18), SUM(G10:G18), SUM(H10:H18)
 *
 * 科目：4104 一般风险准备（贷方/权益类）
 * 金融企业按风险资产期末余额1.5%计提（最低标准）
 *
 * 30×11结构，29公式
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { calcRiskProvision, calcProvisionDiff } from './useM8RiskEngine'
import { calcSubtotal } from './useM8FormulaEngine'
import type { useM8FormData } from './useM8FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** M8-4 测试表行数据（11列） */
export interface M8RiskTestRow {
  /** 行唯一标识 */
  key: string
  /** 项目名称（A列） */
  itemName: string
  /** 本期计提（B列，一般风险准备本期计提额） */
  currentProvision: number
  /** 其他（C列） */
  other: number
  /** 提取标准（D列，如"不低于风险资产1.5%"） */
  standard: string
  /** 基数-风险资产期末余额（E列） */
  riskAssetBalance: number
  /** 比例（F列，如0.015=1.5%） */
  rate: number
  /** 应计金额（G列，公式=E×F） */
  estimatedAmount: number
  /** 差异（H列，公式=B-G） */
  diff: number
  /** 差异原因（I列） */
  diffReason: string
  /** 相关依据索引号（J列） */
  basisIndex: string
  /** 相关数据来源索引号（K列） */
  sourceIndex: string
}

/** 合计行 */
export interface M8RiskTestTotal {
  currentProvision: number
  other: number
  estimatedAmount: number
  diff: number
}

/** 差异高亮状态 */
export interface M8RiskTestHighlight {
  rowIndex: number
  diff: number
  isOverThreshold: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 默认计提比例 1.5% */
export const DEFAULT_RISK_RATE = 0.015

/** 差异阈值（绝对值），超过此值红色高亮 */
export const DIFF_THRESHOLD = 0

/** 默认风险资产项目 */
export const M8_RISK_DEFAULT_ITEMS = [
  '一般风险准备',
  '信用风险资产',
  '市场风险资产',
  '操作风险资产',
  '表外风险资产',
  '衍生工具',
  '资产证券化',
  '交易对手信用',
  '其他',
]

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M8-4 风险资产计提测试（13核心公式+合计行）
 *
 * @param formData 由调用方传入的 useM8FormData 实例
 * @param testRows reactive ref of risk test rows
 */
export function useM8RiskTest(
  formData: ReturnType<typeof useM8FormData>,
  testRows: Ref<M8RiskTestRow[]>,
) {
  const { debouncedSave } = formData

  // ─── 1. 计算属性：G=E*F, H=B-G ───────────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<M8RiskTestRow[]> = computed(() => {
    return testRows.value.map(row => {
      // G = E × F（应计金额=风险资产×比例）
      const estimatedAmount = calcRiskProvision(row.riskAssetBalance, row.rate)
      // H = B - G（差异=本期计提-应计金额）
      // 正=超额计提（安全），负=计提不足（风险）
      const diff = row.currentProvision - estimatedAmount
      return { ...row, estimatedAmount, diff }
    })
  })

  // ─── 2. 合计行（Row 19: SUM(B10:B18) 等） ────────────────────────────

  const totalRow: ComputedRef<M8RiskTestTotal> = computed(() => {
    const r = computedRows.value
    const currentProvision = calcSubtotal(r.map(x => x.currentProvision))
    const other = calcSubtotal(r.map(x => x.other))
    const estimatedAmount = calcSubtotal(r.map(x => x.estimatedAmount))
    const diff = currentProvision - estimatedAmount
    return { currentProvision, other, estimatedAmount, diff }
  })

  // ─── 3. 差异高亮判断 ──────────────────────────────────────────────────

  /**
   * 各行差异高亮状态
   * |差异|>阈值时红色高亮（计提不足=风险！）
   */
  const highlightRows: ComputedRef<M8RiskTestHighlight[]> = computed(() => {
    return computedRows.value.map((row, i) => ({
      rowIndex: i,
      diff: row.diff,
      isOverThreshold: Math.abs(row.diff) > DIFF_THRESHOLD,
    }))
  })

  /** 是否存在任何差异高亮行 */
  const hasAnyHighlight: ComputedRef<boolean> = computed(() => {
    return highlightRows.value.some(h => h.isOverThreshold)
  })

  /** 计提不足行（差异为负=账面<应计提，风险！） */
  const insufficientRows: ComputedRef<M8RiskTestHighlight[]> = computed(() => {
    return highlightRows.value.filter(h => h.diff < -DIFF_THRESHOLD)
  })

  // ─── 4. 行操作 ────────────────────────────────────────────────────────

  /** 更新行某字段 */
  function updateRow(
    index: number,
    field: 'itemName' | 'currentProvision' | 'other' | 'standard' | 'riskAssetBalance' | 'rate' | 'diffReason' | 'basisIndex' | 'sourceIndex',
    value: string | number,
  ): void {
    if (index < 0 || index >= testRows.value.length) return
    const row = testRows.value[index] as any
    row[field] = value
    _triggerSave(index)
  }

  // ─── 5. 计提充足性汇总判断 ────────────────────────────────────────────

  /**
   * 计提充足性结论
   * - 合计差异>=0 → 计提充足
   * - 合计差异<0 → 计提不足，需关注
   */
  const provisionAdequacy: ComputedRef<{
    totalDiff: number
    isAdequate: boolean
    conclusion: string
  }> = computed(() => {
    const totalDiff = totalRow.value.diff
    const isAdequate = totalDiff >= 0
    const conclusion = isAdequate
      ? '一般风险准备计提充足，不低于风险资产期末余额的规定比例'
      : `一般风险准备计提不足，差额${Math.abs(totalDiff).toFixed(2)}元，需关注`
    return { totalDiff, isAdequate, conclusion }
  })

  // ─── 6. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = testRows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    debouncedSave(`M8-4-row-${n}-data`, {
      remark: JSON.stringify({
        key: row.key,
        itemName: row.itemName,
        currentProvision: row.currentProvision,
        other: row.other,
        standard: row.standard,
        riskAssetBalance: row.riskAssetBalance,
        rate: row.rate,
        diffReason: row.diffReason,
        basisIndex: row.basisIndex,
        sourceIndex: row.sourceIndex,
      }),
    })
    // 保存合计（供CrossSheet）
    debouncedSave('M8-4-total-diff', {
      remark: String(totalRow.value.diff),
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 计算属性
    computedRows,
    totalRow,

    // 差异高亮
    highlightRows,
    hasAnyHighlight,
    insufficientRows,

    // 行操作
    updateRow,

    // 计提充足性
    provisionAdequacy,
  }
}

export default useM8RiskTest
