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
 * K11 损益类减值损失发生额（6701 资产减值损失，**借方科目**）。
 *
 * 减值损失类发生额 = 借方发生额 - 贷方发生额（转回红冲）。借方=减值增加，贷方=减值转回/冲回。
 * 取**发生额**不是期末余额 —— 损益类期末已结转，余额恒 0。
 *
 * 🔴 参数顺序即方向契约：本科目是借方科目，故 `debitOcc` 在前。改瘦
 * （e4be3f12）把签名擦成 `(a: number, b: number)`，方向契约随之消失，调用点传
 * 反了没有任何判据会拦 —— 这里按 c197b64e 的原文档恢复参数名与方向说明。实现
 * 仍委托共享桥接（后端 build_occurrence_prefill 已把对侧置 0，减法即非零侧）。
 */
export function calcIncomeStatementOccurrence(debitOcc: number, creditOcc: number): number {
  return legacyCalcIncomeStatementOccurrence(debitOcc, creditOcc)
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
