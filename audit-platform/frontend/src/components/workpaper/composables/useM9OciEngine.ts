/**
 * useM9OciEngine — M9 其他综合收益 OCI 核对引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：4103 其他综合收益（**贷方/权益类！**）
 *
 * ─── OCI核对引擎职责 ───
 * 其他综合收益汇聚多来源（G8/J2/外币折算/套期/其他债权），
 * 需按"以后不能重分类进损益"和"以后能重分类进损益"两大类核对。
 *
 * 两大类：
 * - 不可重分类(nonReclass)：G8其他权益工具投资公允变动、J2设定受益计划重计量
 * - 可重分类(reclass)：其他债权投资公允变动、现金流量套期损益、外币折算差额
 *
 * 每项OCI按税后净额列示：税前发生 - 所得税影响 = 税后净额
 * 核对差异 = 来源金额（如G8/J2税后净额）- 账面OCI增加
 * ─────────────────────────────────────
 *
 * 本引擎覆盖：
 * - P3: 税后净额 calcAfterTaxNet(preTax, taxEffect) = preTax - taxEffect
 * - P4: 核对差异 calcReconcileDiff(source, booked) = source - booked
 * - P5: OCI两大类汇总 aggregateOci(items) → { nonReclass, reclass, total }
 *
 * Spec: .kiro/specs/m9-other-comprehensive-income/ Task 2.2
 * Requirements: 3.3, 4.5, 6.1-6.3
 */

// ─── types ──────────────────────────────────────────────────

/**
 * OCI 单项明细
 *
 * @property amount - 该项金额（通常为税后净额）
 * @property category - OCI分类
 *   - 'nonReclass': 以后不能重分类进损益（G8公允变动、J2重计量）
 *   - 'reclass': 以后能重分类进损益（其他债权公允变动、套期、外币折算）
 */
export interface OciItem {
  amount: number
  category: 'nonReclass' | 'reclass'
}

// ─── helpers ────────────────────────────────────────────────

/** 将 NaN / undefined / null 视为 0 */
function safe(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── P3: 税后净额 ──────────────────────────────────────────

/**
 * 计算本期税后净额（Property P3）
 * 税后净额 = 本期税前发生 - 所得税影响
 *
 * 来源：M9-2 明细表
 * OCI各项目在报表按税后净额列示。
 * 每个OCI项目（公允变动/重计量/套期/折算）均有对应的
 * 递延所得税影响，列示时扣除税额。
 *
 * 示例：
 *   其他权益工具投资公允价值上升100万（税前）
 *   所得税影响25万（递延所得税负债增加）
 *   税后净额 = 100 - 25 = 75万
 *
 * @param preTax - 本期税前发生额
 * @param taxEffect - 所得税影响额（正数=税额扣减）
 * @returns 本期税后净额
 */
export function calcAfterTaxNet(preTax: number, taxEffect: number): number {
  return safe(preTax) - safe(taxEffect)
}

// ─── P4: 核对差异 ──────────────────────────────────────────

/**
 * 计算核对差异（Property P4）
 * 核对差异 = 来源金额 - 账面OCI增加
 *
 * 来源：M9-4 OCI核对表
 * 多来源核对逻辑：
 *   - G8其他权益工具投资公允价值变动（不可重分类）
 *   - J2设定受益计划重计量（不可重分类）
 *   - 其他债权投资公允变动/现金流量套期/外币折算（可重分类）
 *
 * 核对目的：验证OCI完整性与准确性。
 * 当|差异|>阈值时应红色高亮提示审计人员。
 *
 * @param source - 来源金额（来源底稿的税后净额，如G8/J2计算值）
 * @param booked - 账面OCI增加（M9明细中对应项的贷方发生额）
 * @returns 核对差异（0=一致，非0=需解释）
 */
export function calcReconcileDiff(source: number, booked: number): number {
  return safe(source) - safe(booked)
}

// ─── P5: OCI两大类汇总 ─────────────────────────────────────

/**
 * OCI两大类汇总（Property P5）
 *
 * 将OCI各项按分类汇总：
 * - nonReclass（不可重分类）：G8公允变动 + J2重计量
 * - reclass（可重分类）：其他债权公允变动 + 套期 + 外币折算
 * - total = nonReclass + reclass
 *
 * 来源：M9-1 审定表 / M9-2 明细表 / M9-4 核对表
 * 审定表双区块（不可重分类 + 可重分类）各自有分类合计行，
 * 最终合计 = 两大类之和。
 *
 * @param items - OCI各项明细数组
 * @returns { nonReclass: 不可重分类合计, reclass: 可重分类合计, total: 合计 }
 */
export function aggregateOci(items: OciItem[]): { nonReclass: number; reclass: number; total: number } {
  if (!Array.isArray(items)) {
    return { nonReclass: 0, reclass: 0, total: 0 }
  }

  let nonReclass = 0
  let reclass = 0

  for (const item of items) {
    const amt = safe(item?.amount)
    if (item?.category === 'nonReclass') {
      nonReclass += amt
    } else if (item?.category === 'reclass') {
      reclass += amt
    }
    // 忽略无效 category 的项目
  }

  return {
    nonReclass,
    reclass,
    total: nonReclass + reclass,
  }
}
