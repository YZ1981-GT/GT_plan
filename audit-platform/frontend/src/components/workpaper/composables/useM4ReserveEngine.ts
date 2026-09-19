/**
 * useM4ReserveEngine — M4 资本公积变动引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：4002 资本公积（**贷方/权益类！**）
 *
 * ─── 资本公积变动业务语义 ───
 * 资本公积来源汇聚：
 * - 资本溢价（premium）：出资超面值部分、M2外币出资折算差异
 * - 其他资本公积（other）：J3股份支付权益结算（等待期确认）、外币折算差异等
 *
 * 本引擎接收跨底稿联动数据，计算差异与汇总：
 * - P3: 股份支付确认差异（J3确认金额 vs 账面增加）
 * - P4: 资本公积汇总（aggregateReserve.total === premium + other）
 * - P6: 按分类汇总守恒（Σ 各分类 === Σ details.amount）
 * ─────────────────────────────────────
 *
 * Spec: .kiro/specs/m4-capital-reserve/ Task 2.2
 * Requirements: 4.3, 6.1-6.2
 */

// ─── types ──────────────────────────────────────────────────

/**
 * 资本公积明细条目
 *
 * @property category - 分类：'premium'（资本溢价/股本溢价）| 'other'（其他资本公积）
 * @property amount - 金额
 */
export interface ReserveDetail {
  category: 'premium' | 'other'
  amount: number
}

// ─── helpers ────────────────────────────────────────────────

/** 将 NaN / undefined / null 视为 0 */
function safe(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── P3: 股份支付确认差异 ───────────────────────────────────

/**
 * 计算股份支付确认差异（Property P3）
 *
 * 差异 = J3确认金额 - 账面增加
 *
 * 业务场景：
 * J3股份支付底稿确认的等待期权益结算金额，应等于M4其他资本公积
 * 对应贷方增加。差异不为0表示需要进一步核对或调整。
 *
 * 来源：M4-4 检查表 / useM4CrossSheet
 *
 * @param j3Amount - J3股份支付确认金额（等待期权益结算）
 * @param booked - 账面其他资本公积增加金额
 * @returns 确认差异（正=J3多于账面，负=J3少于账面）
 */
export function calcShareBasedDiff(j3Amount: number, booked: number): number {
  return safe(j3Amount) - safe(booked)
}

// ─── P4 + P6: 资本公积汇总 ──────────────────────────────────

/**
 * 资本溢价 + 其他资本公积汇总（Property P4, P6）
 *
 * 按 category 分类汇总 details：
 * - premium: 资本溢价（股本溢价），出资超面值部分
 * - other: 其他资本公积，股份支付/外币折算差异等
 *
 * 守恒性质：
 * - P4: total === premium + other
 * - P6: premium + other === Σ details[i].amount（分类守恒）
 *
 * 来源：M4-2 明细表 / M4-1 审定表双区块合计
 *
 * @param details - 资本公积明细条目数组
 * @returns { premium, other, total } 分类汇总
 */
export function aggregateReserve(details: ReserveDetail[]): { premium: number; other: number; total: number } {
  if (!Array.isArray(details)) {
    return { premium: 0, other: 0, total: 0 }
  }

  let premium = 0
  let other = 0

  for (const d of details) {
    const amt = safe(d.amount)
    if (d.category === 'premium') {
      premium += amt
    } else {
      other += amt
    }
  }

  return { premium, other, total: premium + other }
}
