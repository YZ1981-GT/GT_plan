import {
  calcAuditedAmount,
  legacyCalcIncomeStatementOccurrence,
  parseNum,
} from './shared/plAdjudicationModel'

// 🔴 re-export 而不是各自复制实现。改瘦前（commit c197b64e）6 个引擎各自导出
//    `parseNum` / `calcAuditedAmount` / `calcIncomeStatementOccurrence` / `calcSubtotal`
//    四个名字；2026-08-02 的 e4be3f12 收敛到 shared/plAdjudicationModel 时只保留了
//    `calcIncomeStatementOccurrence`，**删掉了前两个**，而本文件保留下来的
//    `calcSubtotal`（K10~K13 还有 `calcYoYChange` / `calcProportion`）自己仍在调
//    `parseNum` —— 既没 import 也没定义。后果：esbuild 依赖预打包报 34 条
//    "No matching export"，vite dev server 起不来；既有 K 单测/PBT 也一并失效。
export { parseNum, calcAuditedAmount }
/**
 * K10 损益类收益发生额（6117 其他收益，**贷方科目**）。
 *
 * 收益类发生额 = 贷方发生额 - 借方发生额（红冲）。贷方=收益增加（政府补助/资源税返还/即征即退等），借方=收益冲回/红冲。
 * 取**发生额**不是期末余额 —— 损益类期末已结转，余额恒 0。
 *
 * 🔴 参数顺序即方向契约：本科目是贷方科目，故 `creditOcc` 在前。改瘦
 * （e4be3f12）把签名擦成 `(a: number, b: number)`，方向契约随之消失，调用点传
 * 反了没有任何判据会拦 —— 这里按 c197b64e 的原文档恢复参数名与方向说明。实现
 * 仍委托共享桥接（后端 build_occurrence_prefill 已把对侧置 0，减法即非零侧）。
 */
export function calcIncomeStatementOccurrence(creditOcc: number, debitOcc: number): number {
  return legacyCalcIncomeStatementOccurrence(creditOcc, debitOcc)
}

/**
 * CP-K10-05: 同比变动率 = (本期 - 上期) / 上期
 * 上期为0时返回null（除零保护，前端显示"—"）
 *
 * @param current 本期发生额
 * @param prior 上期发生额
 * @returns 变动率（小数形式，如0.5表示50%增长）或null
 *
 * Validates: Requirements 7.6
 */
export function calcYoYChange(current: number, prior: number): number | null {
  const p = parseNum(prior)
  if (p === 0) return null
  return (parseNum(current) - p) / p
}

/**
 * CP-K10-06: 合计行求和 = SUM(数组元素)，忽略NaN/null/undefined
 * 空数组返回0；非数组返回0
 * 适用：审定表合计行、明细表分类小计
 *
 * Validates: Requirements 7.7
 */
export function calcSubtotal(arr: number[]): number {
  if (!Array.isArray(arr) || arr.length === 0) return 0
  return arr.reduce((sum, v) => sum + parseNum(v), 0)
}
