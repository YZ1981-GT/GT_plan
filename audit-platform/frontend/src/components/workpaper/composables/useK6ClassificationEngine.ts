/**
 * K6 持有待售 — CAS42 五条件分类判断引擎（纯函数）
 *
 * CAS42 持有待售分类条件（全部满足才可分类）：
 *   条件① 可立即出售（在当前状况下仅根据惯例条款即可立即出售）
 *   条件② 已就出售作出决议
 *   条件③ 已与购买方签订不可撤销转让协议
 *   条件④ 出售预计一年内完成
 *   条件⑤ 售价合理，不太可能变更/撤销
 *
 * 判断逻辑：
 *   全部 5 条件满足 → 'classified'（分类为持有待售）
 *   任一条件不满足 → 'not_classified'（不得分类为持有待售）
 *
 * 设计原则：纯函数，无Vue响应式，无副作用，可PBT验证
 * classifyHeldForSale 必须是确定性映射（相同输入永远得到相同输出）
 *
 * Spec: .kiro/specs/k6-held-for-sale/ Requirements 4.2, 9.3
 */

// ─── Types ──────────────────────────────────────────────────────────────────

/** 分类判断结果 */
export type ClassificationResult = 'classified' | 'not_classified'

// ─── 判断函数 ───────────────────────────────────────────────────────────────

/**
 * CAS42 五条件分类判断
 *
 * 全部条件为 true → 'classified'（满足持有待售分类）
 * 任一条件为 false / 空数组 / 非布尔值 → 'not_classified'
 *
 * 边界处理：
 * - 空数组 → 'not_classified'（没有条件意味着未评估）
 * - 数组中含非 boolean 值 → 该元素视为 false
 * - null/undefined 输入 → 'not_classified'
 *
 * @param conditions CAS42 五条件布尔数组（[①可立即出售, ②已作决议, ③已签协议, ④一年内完成, ⑤售价合理]）
 * @returns 分类结果：'classified' 或 'not_classified'
 *
 * Requirements 4.2, 9.3
 */
export function classifyHeldForSale(conditions: boolean[]): ClassificationResult {
  if (!conditions || !Array.isArray(conditions) || conditions.length === 0) {
    return 'not_classified'
  }
  // 逐条检查：非严格 boolean true 视为不满足
  for (const c of conditions) {
    if (c !== true) {
      return 'not_classified'
    }
  }
  return 'classified'
}
