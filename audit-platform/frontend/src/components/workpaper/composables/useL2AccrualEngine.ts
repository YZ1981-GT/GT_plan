/**
 * useL2AccrualEngine — L2 应付利息计提核对引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 * 科目：2231 应付利息（贷方/负债类）
 *
 * ─── 核心用途 ───
 * 1. 核对 L1/L3 利息测算与账面实际计提的差异
 * 2. 按借款来源汇总应付利息明细
 *
 * L2 应付利息是 L1 短期借款、L3 长期借款、L4 应付债券利息计提的汇聚点。
 * 通过 EventBus 订阅 'l1:interest-calculated' / 'l3:interest-calculated'
 * 获取测算利息，与账面计提对比验证准确性。
 * ─────────────────
 */

// ─── 类型定义 ────────────────────────────────────────────────

/**
 * 应付利息明细行
 */
export interface InterestDetail {
  /** 借款来源类别（如"短期借款利息","长期借款利息","应付债券利息"） */
  source: string
  /** 金额 */
  amount: number
}

// ─── 1. 计提差异 ────────────────────────────────────────────

/**
 * 计算计提差异
 * 计提差异 = 测算利息 - 账面计提
 *
 * 正值表示账面少计提（应补提），负值表示账面多计提（应冲回）。
 * 核对 L1/L3 利息测算与账面实际计提的差异。
 *
 * Property P3: ∀ est,booked: calcAccrualDiff = est - booked
 * **Validates: Requirements 4.4, 6.1**
 *
 * @param estimated - 测算利息金额（来自 L1/L3 利息测算）
 * @param booked - 账面计提金额（实际入账）
 * @returns 计提差异（正=少提，负=多提）
 */
export function calcAccrualDiff(estimated: number, booked: number): number {
  return estimated - booked
}

// ─── 2. 按来源汇总 ──────────────────────────────────────────

/**
 * 按借款来源汇总应付利息
 * 将明细表中各行按 source 字段分组求和
 *
 * 守恒性质：Σ aggregateBySource(details).values === Σ details.amount
 * 即分组汇总后各组之和必须等于全部明细之和（无遗漏无重复）。
 *
 * Property P5: Σ aggregateBySource(details).values === Σ details.amount
 * **Validates: Requirements 6.2**
 *
 * @param details - 应付利息明细行数组
 * @returns 以来源为 key、汇总金额为 value 的记录
 */
export function aggregateBySource(details: InterestDetail[]): Record<string, number> {
  const result: Record<string, number> = {}
  for (const item of details) {
    if (item.source in result) {
      result[item.source] += item.amount
    } else {
      result[item.source] = item.amount
    }
  }
  return result
}

// ─── Composable 导出 ────────────────────────────────────────

/**
 * L2 应付利息计提核对引擎 composable 包装
 * 提供纯函数分组导出，方便 Vue 组件中统一引用
 */
export function useL2AccrualEngine() {
  return {
    calcAccrualDiff,
    aggregateBySource,
  }
}
