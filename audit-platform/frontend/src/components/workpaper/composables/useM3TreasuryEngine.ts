/**
 * useM3TreasuryEngine — M3 库存股回购/注销引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：4002 库存股（**借方/权益备抵类！**）
 *
 * ─── 回购与注销业务逻辑 ───
 * 1. 回购：公司以自有资金回购已发行股份
 *    借：库存股（回购金额 = 股数 × 单价）
 *    贷：银行存款
 *
 * 2. 注销：将库存股注销，冲减所有者权益
 *    借：实收资本（按面值，联动 M2）
 *    借：资本公积（差额，联动 M4）
 *    贷：库存股
 *    ⚠️ 当注销金额 > 冲减实收资本 + 冲减资本公积时，
 *       差额需进一步冲减盈余公积(M5)或未分配利润(M6)
 * ──────────────────────────
 *
 * 本引擎覆盖：
 * - P3: 回购金额（股数 × 单价）
 * - P4: 注销冲减差额（注销金额 - 冲减实收资本 - 冲减资本公积）
 *
 * Spec: .kiro/specs/m3-treasury-stock/ Task 2.2
 * Requirements: 5.2, 5.4, 7.3-7.4
 */

// ─── helpers ────────────────────────────────────────────────

/** 将 NaN / undefined / null 视为 0 */
function safe(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── P3: 回购金额 ──────────────────────────────────────────

/**
 * 计算回购金额（Property P3）
 * 回购金额 = 回购股数 × 回购单价
 *
 * 来源：M3-5 检查表回购核对区
 * 审计目标：验证回购价格真实性（与董事会决议/市价比较）
 *
 * @param shares - 回购股数（股）
 * @param price - 回购单价（元/股）
 * @returns 回购金额（元）
 */
export function calcRepurchaseAmount(shares: number, price: number): number {
  return safe(shares) * safe(price)
}

// ─── P4: 注销冲减差额 ──────────────────────────────────────

/**
 * 计算注销冲减差额（Property P4）
 * 注销冲减差额 = 注销金额 - 冲减实收资本(M2) - 冲减资本公积(M4)
 *
 * 来源：M3-5 检查表注销核对区
 * 业务规则：
 * - 冲减实收资本 = 注销股数 × 每股面值（联动 M2）
 * - 冲减资本公积 = 注销金额 - 冲减实收资本（优先冲减，联动 M4）
 * - 当差额 ≠ 0 时，表示资本公积不足以冲减，
 *   剩余部分需进一步冲减盈余公积(M5)或未分配利润(M6)
 *
 * @param cancelAmount - 注销金额（库存股账面金额）
 * @param deductCapital - 冲减实收资本金额（按面值，联动 M2）
 * @param deductReserve - 冲减资本公积金额（联动 M4）
 * @returns 冲减差额（0=完全冲减，>0=需进一步冲减M5/M6）
 */
export function calcCancelDiff(cancelAmount: number, deductCapital: number, deductReserve: number): number {
  return safe(cancelAmount) - safe(deductCapital) - safe(deductReserve)
}
