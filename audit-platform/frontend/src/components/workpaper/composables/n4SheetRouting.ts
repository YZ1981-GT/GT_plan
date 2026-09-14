/**
 * N4 税金及附加底稿 sheet 分发（纯函数，可单测）
 *
 * 判定逻辑收敛在 `shared/cycleSheetRouting.ts`（披露判定前置于 wp_code 正则 +
 * 国企多写法全认）。原宿主实现是「wp_code 正则前置」的形态 —— 与 D2 实测中招的
 * 缺陷同形（披露 tab 名尾部带 wp_code 时披露组件永远挂不上）。
 *
 * 真实 sheet 名（`workpaper_sheet_classification` wp_code=N4 实测）：
 * `附注披露信息（上市公司）` / `附注披露信息（国企）`
 * （国企 tab 存在，但内容是「附注披露信息：无」→ Tab 渲染「本版不适用」说明页）
 *
 * spec: `.kiro/specs/n-cycle-tax-disclosure-alignment/`
 */
import {
  SHEET_DISCLOSURE_LISTED,
  SHEET_DISCLOSURE_SOE,
  SHEET_INDEX,
  makeCycleSheetRouter,
} from './shared/cycleSheetRouting'

export const N4_SHEET_DISCLOSURE_LISTED = SHEET_DISCLOSURE_LISTED
export const N4_SHEET_DISCLOSURE_SOE = SHEET_DISCLOSURE_SOE
export const N4_SHEET_INDEX = SHEET_INDEX

const router = makeCycleSheetRouter({
  codeRe: /(N4A|O2A|N4-[1-3]|N4)/,
  htmlCodeRe: /^N4-[1-3]$/,
  bareCodes: ['N4'],
})

export function normalizeN4SheetName(
  sheetName: string | null | undefined,
  wpCode?: string | null,
): string {
  return router.normalize(sheetName, wpCode)
}

export function isN4HtmlSheet(normalized: string): boolean {
  // N4A 走程序表路由、O2A 走 OnlyOffice 兜底 —— 都不是 HTML 专属组件
  if (normalized === 'N4A' || normalized === 'O2A') return false
  return router.isHtmlSheet(normalized)
}
