/**
 * N5 所得税费用底稿 sheet 分发（纯函数，可单测）
 *
 * 判定逻辑收敛在 `shared/cycleSheetRouting.ts`（披露判定前置于 wp_code 正则 +
 * 国企多写法全认）。
 *
 * 🔴 真实 sheet 名（`workpaper_sheet_classification` wp_code=N5 实测）：
 * `附注披露信息（上市公司）` / **`附注披露信息（国企`（缺右括号）** ——
 * 源模板 tab 名如此。判定用「包含 `国企`」而非全等，故缺括号也命中。
 *
 * spec: `.kiro/specs/n-cycle-tax-disclosure-alignment/`
 */
import {
  SHEET_DISCLOSURE_LISTED,
  SHEET_DISCLOSURE_SOE,
  SHEET_INDEX,
  makeCycleSheetRouter,
} from './shared/cycleSheetRouting'

export const N5_SHEET_DISCLOSURE_LISTED = SHEET_DISCLOSURE_LISTED
export const N5_SHEET_DISCLOSURE_SOE = SHEET_DISCLOSURE_SOE
export const N5_SHEET_INDEX = SHEET_INDEX

const router = makeCycleSheetRouter({
  codeRe: /(N5A|N3A|N5-6-[12]|N5-[1-8]|N5)/,
  htmlCodeRe: /^N5-\d+(-\d+)?$/,
  bareCodes: ['N5'],
})

export function normalizeN5SheetName(
  sheetName: string | null | undefined,
  wpCode?: string | null,
): string {
  return router.normalize(sheetName, wpCode)
}

export function isN5HtmlSheet(normalized: string): boolean {
  // N5A / N3A 走 OnlyOffice 兜底
  if (normalized === 'N5A' || normalized === 'N3A') return false
  return router.isHtmlSheet(normalized)
}
