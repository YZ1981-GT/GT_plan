/**
 * useH7TransferEngine — H7 生产性生物资产互转纯函数引擎（三方向）
 *
 * Spec: .kiro/specs/h7-biological-assets/ Task 2.3
 * Requirements: 8.4-8.5
 *
 * 生物资产可在三类间互转：生产性 ↔ 消耗性 ↔ 公益性
 * 互转时账面价值应完整结转，差额应为0。
 * 所有函数为纯函数（无副作用），方便PBT验证。
 */

// ─── Types ───────────────────────────────────────────────────────────────────

export interface TransferResult {
  /** 转出金额 */
  transferOut: number
  /** 转入金额（应等于转出金额） */
  transferIn: number
}

// ─── 生产性→消耗性互转 ──────────────────────────────────────────────────────

/**
 * 生产性生物资产 → 消耗性生物资产
 * 按账面价值转出（转出=转入，差额应为0）
 *
 * @param bookValue 转出时的账面价值
 */
export function calcProdToConsumable(bookValue: number): TransferResult {
  return {
    transferOut: bookValue,
    transferIn: bookValue,
  }
}

// ─── 生产性→公益性互转 ──────────────────────────────────────────────────────

/**
 * 生产性生物资产 → 公益性生物资产
 * 按账面价值转出（转出=转入，差额应为0）
 *
 * @param bookValue 转出时的账面价值
 */
export function calcProdToPublic(bookValue: number): TransferResult {
  return {
    transferOut: bookValue,
    transferIn: bookValue,
  }
}

// ─── 互转差额 ────────────────────────────────────────────────────────────────

/**
 * 互转差额 = 转出金额 - 转入金额（应为0）
 * Property P7: ∀ out,in: calcTransferDiff(out,in) === out - in
 *
 * 差额≠0时表示存在异常，需红色高亮提示。
 *
 * @param transferOut 转出金额
 * @param transferIn 转入金额
 */
export function calcTransferDiff(transferOut: number, transferIn: number): number {
  return transferOut - transferIn
}
