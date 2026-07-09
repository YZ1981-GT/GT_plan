/**
 * K11 资产减值损失 — 公式引擎（纯函数，无副作用）
 * 科目：6701资产减值损失（**损益类/借方科目**）
 * 核心特征：取发生额非余额！减值损失发生额 = 借方发生 - 贷方发生(转回红冲)
 *   - 6701为借方科目：借方=减值增加，贷方=减值转回/冲回
 *   - 与K9(6602管理费用)/K8(6601销售费用)/I6(6602研发费用)/H10(6115资产处置损益)同款损益类处理逻辑
 *   - TB回写发生额而非期末余额
 *   - 注意：损益类没有"期末余额"概念，只有发生额！
 * 减值汇总联动：各来源(F2/H1/I1/I3等)计提金额与K11金额交叉核对
 * Spec: .kiro/specs/k11-asset-impairment-loss/
 */

/**
 * 安全数字解析：NaN/null/undefined/Infinity → 0
 * 所有公式函数内部调用以防御非法输入
 */
export function parseNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  if (typeof v === 'number') return Number.isFinite(v) ? v : 0
  const s = String(v).trim()
  if (!s || s === 'NaN') return 0
  const n = Number(s)
  return Number.isFinite(n) ? n : 0
}

/**
 * 审定数 = 未审数 + AJE调整 + RJE重分类
 * 适用：审定表K11-1各资产减值明细行审定列
 * 公式：audited = unadjusted + AJE + RJE
 * Validates: Requirements 2.3, 6.3
 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return parseNum(unadj) + parseNum(aje) + parseNum(rje)
}

/**
 * 损益类减值损失发生额（6701借方科目）
 * 减值损失发生额 = 借方发生额 - 贷方发生额（转回红冲）
 *   - 借方=减值增加（资产减值损失计提：存货跌价/固定资产减值/无形资产减值/商誉减值等）
 *   - 贷方=减值转回/冲回（仅非商誉类允许转回，商誉减值不可转回CAS8）
 * 重要：取发生额而非期末余额！损益类科目期末余额为0（已结转）
 * 数据来源：tb_ledger明细科目发生额汇总
 * Validates: Requirements 2.4, 5.1-5.3, 6.4
 */
export function calcIncomeStatementOccurrence(debitOcc: number, creditOcc: number): number {
  return parseNum(debitOcc) - parseNum(creditOcc)
}

/**
 * 源底稿核对差异 = K11金额 - 源底稿金额
 * 用于K11-2明细表各行与对应源底稿(F2/H1/I1/I3等)减值计提金额交叉核对
 * 差异为0表示一致；差异非零应红色标记提示
 * Validates: Requirements 3.2, 6.6
 */
export function calcSourceVariance(k11Amount: number, sourceAmount: number): number {
  return parseNum(k11Amount) - parseNum(sourceAmount)
}

/**
 * 合计行求和 = SUM(数组元素)，忽略NaN/null/undefined
 * 空数组返回0；非数组返回0
 * 适用：审定表合计行、明细表分类小计、减值汇总
 * Validates: Requirements 6.7
 */
export function calcSubtotal(arr: number[]): number {
  if (!Array.isArray(arr) || arr.length === 0) return 0
  return arr.reduce((sum, v) => sum + parseNum(v), 0)
}
