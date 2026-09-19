/**
 * useK1CrossSheet — K1 其他应收款跨Sheet交叉验证 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('K1-{sheet}-{field}')?.remark 存数值。
 *
 * 跨Sheet映射（数据流图）：
 * - K1-1 审定表 total vs K1-2 明细表合计（adjudicationVsDetail）
 * - K1-3 坏账期末 vs K1-8 测算应计提（badDebtVsCalc）
 * - K1-2 账龄合计 vs K1-2 期末余额（agingVsBalance）
 *
 * 科目方向：
 * - 1221 其他应收款（借方/资产类）：期末=期初+借方-贷方
 * - 坏账准备（贷方/资产备抵类）：期末=期初+贷方-借方
 *
 * Spec: .kiro/specs/k1-other-receivables/
 * Task: 3.2
 * Requirements: 2.9, 3.3, 4.4-4.5, 6.5
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { readK14AdjustmentNets } from './useK1Adjustment'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface CrossSheetCheckResult {
  diff: number
  isMatch: boolean
}

export interface K14CrossCheckResult {
  receivableAjeDiff: number
  receivableRjeDiff: number
  badDebtAjeDiff: number
  badDebtRjeDiff: number
  isMatch: boolean
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 从 allResponses Map 中获取指定 item_id 的数值（尝试 remark → conclusion）。
 * NaN/null/undefined → 0
 */
function getNumFromMap(map: Map<string, any>, key: string): number {
  const item = map.get(key)
  if (!item) return 0
  const raw = item.remark ?? item.conclusion
  if (raw == null) return 0
  const n = Number(raw)
  return Number.isFinite(n) ? n : 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK1CrossSheet(allResponses: Ref<Map<string, any>>): {
  adjudicationVsDetail: ComputedRef<CrossSheetCheckResult>
  badDebtVsCalc: ComputedRef<CrossSheetCheckResult>
  agingVsBalance: ComputedRef<CrossSheetCheckResult>
  adjudicationVsK14: ComputedRef<K14CrossCheckResult>
} {
  // 辅助：从 allResponses 提取数值
  function getNum(key: string): number {
    return getNumFromMap(allResponses.value, key)
  }

  // ═══ adjudicationVsDetail: K1-1 审定表 total vs K1-2 明细表合计（Req 2.9, 3.3）═══

  /**
   * K1-1 审定表审定数（其他应收款合计）与 K1-2 明细表期末余额小计交叉验证。
   * diff = K1-1 审定 total - K1-2 明细 subtotal
   * isMatch = |diff| < 0.01（分以内视为一致）
   */
  const adjudicationVsDetail: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const adjTotal = getNum('K1-1-audited-receivable')
    const detailSubtotal = getNum('K1-2-end-subtotal')
    const diff = adjTotal - detailSubtotal
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ═══ badDebtVsCalc: K1-3 坏账期末 vs K1-8 测算应计提（Req 4.4-4.5, 6.5）═══

  /**
   * K1-3 坏账准备明细期末合计 与 K1-8 坏账测算应计提合计交叉验证。
   * diff = K1-3 实际坏账期末 - K1-8 测算应计提
   * isMatch = |diff| < 0.01
   *
   * 差异>0 表示企业多计提；差异<0 表示企业少计提（需提示调整）。
   */
  const badDebtVsCalc: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const badDebtEnd = getNum('K1-3-bad-debt-end')
    const calcProvision = getNum('K1-8-calc-provision-total')
    const diff = badDebtEnd - calcProvision
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ═══ agingVsBalance: K1-2 账龄合计 vs 期末余额（Req 3.3）═══

  /**
   * K1-2 明细表中，各账龄区间之和（1年内+1-2年+2-3年+3年以上）与该行期末余额勾稽。
   * 此处取所有行的聚合合计级别校验。
   * diff = 账龄合计 - 期末余额合计
   * isMatch = |diff| < 0.01
   *
   * 不匹配说明存在账龄划分遗漏或期末数计算偏差。
   */
  const agingVsBalance: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const agingSubtotal = getNum('K1-2-aging-subtotal')
    const endBalance = getNum('K1-2-end-subtotal')
    const diff = agingSubtotal - endBalance
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ═══ adjudicationVsK14: K1-1 AJE/RJE 合计 vs K1-4 1221/1231 净额 ═══

  const adjudicationVsK14: ComputedRef<K14CrossCheckResult> = computed(() => {
    const k14 = readK14AdjustmentNets(allResponses.value)
    let recAje = 0
    let recRje = 0
    let bdAje = 0
    let bdRje = 0
    const recCount = getNum('K1-1-receivable-count') || 5
    const bdCount = getNum('K1-1-baddebt-count') || 5
    for (let i = 0; i < recCount; i++) {
      recAje += getNum(`K1-1-receivable-r${i}-aje`)
      recRje += getNum(`K1-1-receivable-r${i}-rje`)
    }
    for (let i = 0; i < bdCount; i++) {
      bdAje += getNum(`K1-1-baddebt-r${i}-aje`)
      bdRje += getNum(`K1-1-baddebt-r${i}-rje`)
    }
    const receivableAjeDiff = recAje - k14.receivableAjeNet
    const receivableRjeDiff = recRje - k14.receivableRjeNet
    const badDebtAjeDiff = bdAje - k14.badDebtAjeNet
    const badDebtRjeDiff = bdRje - k14.badDebtRjeNet
    const isMatch =
      Math.abs(receivableAjeDiff) < 0.01 &&
      Math.abs(receivableRjeDiff) < 0.01 &&
      Math.abs(badDebtAjeDiff) < 0.01 &&
      Math.abs(badDebtRjeDiff) < 0.01
    return { receivableAjeDiff, receivableRjeDiff, badDebtAjeDiff, badDebtRjeDiff, isMatch }
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    adjudicationVsDetail,
    badDebtVsCalc,
    agingVsBalance,
    adjudicationVsK14,
  }
}

export default useK1CrossSheet
