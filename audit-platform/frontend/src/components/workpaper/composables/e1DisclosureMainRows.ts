/**
 * E1 披露主表取数（纯函数，零 Vue 依赖）—— 披露 Tab 与后端公式推送共用同一算式。
 *
 * spec: chain-closure-phase2-formula-push-engine（design §四「披露主表取数抽成纯函数」）
 *
 * 由 `E1TabDisclosure.vue` 原内联的 effEnding / effOpening / 合计逻辑原样抽出，行为逐字不变：
 * - 期末 = `resolveE1MainRowAmount`（crossKey 优先 → 语义槽 → 扣减单独列示项），取不到按 0 且
 *   `endingResolved=false`（「本项目无此科目」≠「余额为 0」）；
 * - 期初 = 披露表手工覆盖优先（`openingMap` 显式含该 key），否则同口径取期初审定数；
 * - 合计 = 参与合计行（非合计、非「其中：」）之和，恒为已取到。
 *
 * 🔴 后端 `formula_push/bindings/e1_calc.disclosure_main_rows` 复刻本函数，
 *    双侧夹具 `backend/tests/fixtures/formula_push_e1_parity.json` 守卫两侧逐值一致。
 */
import { e1MainRows, e1SummableRows, type E1DisclosureVariantKey } from './e1DisclosureScope'
import {
  isE1MainRowDeducted,
  isE1MainRowSlotPrefilled,
  resolveE1MainRowAmount,
  type E1RemarkGetter,
} from './e1MainRowPrefill'

export interface E1DisclosureMainRowValue {
  key: string
  label: string
  crossKey: string
  endingAmount: number
  openingAmount: number
  /** 期初是否自动预填（无手工覆盖且取到非 0 预填值），供 UI 标注 */
  openingPrefilled: boolean
  /** 期末是否取到值（合计行恒 true） */
  endingResolved: boolean
  /** 期初是否有值来源（手工覆盖或取到预填；合计行恒 true） */
  openingResolved: boolean
  /** 期末是否由语义槽预填 */
  endingSlotPrefilled: boolean
  /** 期末是否已扣除单独列示项 */
  endingDeducted: boolean
}

export function computeE1DisclosureMainRows(
  variant: E1DisclosureVariantKey,
  get: E1RemarkGetter,
  openingMap: Record<string, unknown>,
): E1DisclosureMainRowValue[] {
  const hasOverride = (key: string): boolean => key in openingMap
  const effEnding = (item: { key: string; crossKey: string }): number =>
    resolveE1MainRowAmount(item, get) ?? 0
  const effOpening = (item: { key: string; crossKey: string }): number => {
    if (hasOverride(item.key)) return Number(openingMap[item.key]) || 0
    return resolveE1MainRowAmount(item, get, 'opening') ?? 0
  }

  return e1MainRows(variant).map((item) => {
    let endingAmount = effEnding(item)
    let openingAmount = effOpening(item)
    if (item.isTotal) {
      const subs = e1SummableRows(variant)
      endingAmount = subs.reduce((sum, i) => sum + effEnding(i), 0)
      openingAmount = subs.reduce((sum, i) => sum + effOpening(i), 0)
    }
    const openingFromSource = resolveE1MainRowAmount(item, get, 'opening')
    return {
      key: item.key,
      label: item.label,
      crossKey: item.crossKey,
      endingAmount,
      openingAmount,
      openingPrefilled: item.isTotal
        ? false
        : !hasOverride(item.key) && (openingFromSource ?? 0) !== 0,
      endingResolved: !!item.isTotal || resolveE1MainRowAmount(item, get) !== null,
      openingResolved: !!item.isTotal || hasOverride(item.key) || openingFromSource !== null,
      endingSlotPrefilled: isE1MainRowSlotPrefilled(item, get),
      endingDeducted: isE1MainRowDeducted(item, get),
    }
  })
}
