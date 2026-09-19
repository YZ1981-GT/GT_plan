/**
 * d1SharedFormulas — D1 监盘核查组共享纯函数（别名模块）
 *
 * 统一导出所有共享纯函数，供 useD1InventoryCount / useD1RelatedPartyCheck /
 * useD1PledgeCheck / useD1SamplingVouching 四个composable复用。
 *
 * 实际实现位于 d1InspectionFormulas.ts。此文件为架构优化别名。
 *
 * Spec: .kiro/specs/d1-inspection-check/ Task: 19.1
 * Requirements: 20.1
 */

export {
  // 纯函数
  computeClosingBalance,
  computeBookValue,
  sumColumn,
  computePledgeRatio,
  computeExceptionRate,
  formatNegativeAmount,
} from './d1InspectionFormulas'

/** parseNum — 通用数字解析（非有限数降级为0） */
export function parseNum(val: any): number {
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}
