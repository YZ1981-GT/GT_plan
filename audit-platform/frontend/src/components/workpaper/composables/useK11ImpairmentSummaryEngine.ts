/**
 * K11 资产减值损失 — 减值汇总引擎（纯函数，无副作用）
 * 独立composable：汇总各类资产减值损失来源金额
 * 来源：F2存货跌价 / H1固定资产减值 / I1无形资产减值 / I3商誉减值 / 在建工程 / 长期股权投资 / 其他
 * 用途：K11-1审定表合计验证、K11-2明细表汇总、源底稿交叉核对
 * Spec: .kiro/specs/k11-asset-impairment-loss/
 */

import { parseNum } from './useK11FormulaEngine'

/**
 * 减值汇总 = Σ各来源计提金额
 * 将各类资产减值损失来源金额求和
 * 空数组返回0；NaN/null/undefined元素视为0
 * Validates: Requirements 4.1, 4.3, 6.5
 */
export function calcImpairmentSummary(sources: number[]): number {
  if (!Array.isArray(sources) || sources.length === 0) return 0
  return sources.reduce((sum, v) => sum + parseNum(v), 0)
}
