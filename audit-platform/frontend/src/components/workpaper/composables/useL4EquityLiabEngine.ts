/**
 * useL4EquityLiabEngine — L4 应付债券 权益负债划分引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。支持 fast-check PBT 验证。
 *
 * ─── CAS 37 权益与负债分类（复合金融工具分拆）──────────────
 *
 * 依据 CAS 37 金融工具列报 + CAS 22 金融工具确认和计量：
 *
 * 可转换公司债券等复合金融工具，包含负债成分和权益成分。
 * 发行方应当在初始确认时将两者分拆：
 *
 * 1. 负债成分 = 未来现金流量按同期限同条件不含转换权的市场利率折现的现值
 *    即 NPV = Σ cashFlows[i] / (1 + marketRate)^(i+1)
 *
 * 2. 权益成分 = 发行总额 - 负债成分
 *    （剩余法，权益成分不再重新计量）
 *
 * 会计处理：
 * - 负债成分 → 应付债券（后续按实际利率法摊销）
 * - 权益成分 → 其他权益工具（不再变动）
 *
 * 关键判断：
 * - 权益成分 > 0：正常复合工具分拆
 * - 权益成分 ≤ 0：分拆异常，可能不含转换权或市场利率低于票面利率
 *   （此情况由调用方处理警告，引擎仍返回负值，符合 Req 10.3）
 * ────────────────────────────────────────────────────────────
 *
 * 本引擎覆盖：
 * - calcLiabilityComponent: 负债成分（未来现金流现值）
 * - calcEquityComponent: 权益成分（发行总额 - 负债成分）
 *
 * Spec: .kiro/specs/l4-bonds-payable/ Requirements 7.2-7.3, 10.1-10.3
 */

// ─── 1. 负债成分（未来现金流现值） ──────────────────────────

/**
 * 计算负债成分（复合金融工具分拆）
 *
 * 负债成分 = 未来各期现金流按市场利率折现的现值之和
 * NPV = Σ cashFlows[i] / (1 + marketRate)^(i+1)
 *
 * 其中 marketRate 为同期限同条件、不含转换权（权益成分）的
 * 类似债务工具的市场利率。
 *
 * 来源：L4-5 权益与负债划分检查表
 * 与 solveEIR 使用相同的现值公式，但此处用已知市场利率计算，
 * 而非反向求解利率。
 *
 * 边界处理：
 * - marketRate = 0 → 不折现，负债成分 = 现金流总和
 * - cashFlows 为空 → 负债成分 = 0
 *
 * @param cashFlows - 未来各期现金流数组（正值，按期排列，最后一期含本金偿还）
 * @param marketRate - 市场利率（年利率，小数形式，如 0.06 表示 6%）
 * @returns 负债成分（现值）
 */
export function calcLiabilityComponent(cashFlows: number[], marketRate: number): number {
  if (cashFlows.length === 0) return 0

  // marketRate = 0 时不折现，直接返回现金流总和
  if (marketRate === 0) {
    let sum = 0
    for (const cf of cashFlows) {
      sum += cf
    }
    return sum
  }

  let pv = 0
  for (let i = 0; i < cashFlows.length; i++) {
    pv += cashFlows[i] / Math.pow(1 + marketRate, i + 1)
  }
  return pv
}

// ─── 2. 权益成分（剩余法） ──────────────────────────────────

/**
 * 计算权益成分（复合金融工具分拆）
 *
 * 权益成分 = 发行总额 - 负债成分
 *
 * 依据 CAS 37 "剩余法"：先确定负债成分公允价值（折现），
 * 发行总对价减去负债成分即为权益成分。
 *
 * 来源：L4-5 权益与负债划分检查表
 *
 * 边界处理：
 * - 权益成分 < 0 时返回负值（不做截断）
 *   调用方根据 Req 10.3 显示红色警告"分拆异常"
 *   可能原因：市场利率极低导致负债成分现值 > 发行总额
 *
 * @param totalProceeds - 发行总额（实际收到的全部对价）
 * @param liabilityComponent - 负债成分（由 calcLiabilityComponent 计算）
 * @returns 权益成分（正常为正值，异常可为负值）
 */
export function calcEquityComponent(totalProceeds: number, liabilityComponent: number): number {
  return totalProceeds - liabilityComponent
}
