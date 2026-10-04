/**
 * E1 审定表「账项调整」取数（纯函数）—— E1-5 本地调整 + 调整分录大厅已确认调整。
 *
 * spec: chain-closure-phase2-formula-push-engine · ADR-PUSH-001
 *
 * - 本地：`E1-adjustment-by-item-{itemKey}-{period}`（E1-5 调整分录只归集 `category=账项调整`）
 * - 大厅：`E1-hall-adj-{itemKey}-ending`（后端公式推送写入 = 大厅**已批准**且
 *   `origin≠workpaper` 的 AJE 净额）。只进库存现金 / 银行存款本金 / 其他货币资金三行的**期末**。
 *
 * 🔴 两者相加而非替换：底稿来源的分录（E1-5 汇入大厅的）已在本地调整里，大厅侧排除了它们，
 *    相加不重计；若改成「用大厅分录替换本地」，E1-5 录的分录会被计两次或丢失。
 * 🔴 后端 `formula_push/bindings/e1_calc.adjustment_for` 复刻本函数（双侧夹具守卫）。
 */
import { parseNum } from './useE1FormulaEngine'

/** 大厅已确认调整进入的审定表行（与后端 HALL_ADJ_ITEM_KEYS 同源） */
export const E1_HALL_ADJ_ITEM_KEYS: readonly string[] = Object.freeze(['cash', 'bank_principal', 'other_mf'])

export function e1HallAdjKey(itemKey: string): string {
  return `E1-hall-adj-${itemKey}-ending`
}

export type E1AdjustmentGetter = (key: string) => string | null | undefined

export function e1AdjustmentFor(
  get: E1AdjustmentGetter,
  itemKey: string,
  period: 'opening' | 'ending',
): number {
  const local = parseNum(get(`E1-adjustment-by-item-${itemKey}-${period}`))
  const hall =
    period === 'ending' && E1_HALL_ADJ_ITEM_KEYS.includes(itemKey)
      ? parseNum(get(e1HallAdjKey(itemKey)))
      : 0
  return local + hall
}
