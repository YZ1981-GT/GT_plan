/**
 * N2 应交税费底稿 sheet 分发（纯函数，可单测）
 *
 * 判定逻辑收敛在 `shared/cycleSheetRouting.ts`（披露判定前置 + 国企多写法），
 * 本模块只声明 N2 的 wp_code 正则与 HTML 编码范围。
 *
 * 修掉的实测缺陷：原实现把国企写成**繁体 `國企`**，而真实 tab 名是简体
 * `附注披露信息（国企）` → **国企披露 Tab 从来没渲染过**（落到 OnlyOffice 兜底）。
 *
 * 真实 sheet 名（`workpaper_sheet_classification` wp_code=N2 实测）：
 * `附注披露信息（上市公司）` / `附注披露信息（国企）`
 *
 * spec: `.kiro/specs/n-cycle-tax-disclosure-alignment/`
 */
import {
  SHEET_DISCLOSURE_LISTED,
  SHEET_DISCLOSURE_SOE,
  SHEET_INDEX,
  makeCycleSheetRouter,
} from './shared/cycleSheetRouting'

export const N2_SHEET_DISCLOSURE_LISTED = SHEET_DISCLOSURE_LISTED
export const N2_SHEET_DISCLOSURE_SOE = SHEET_DISCLOSURE_SOE
export const N2_SHEET_INDEX = SHEET_INDEX

const router = makeCycleSheetRouter({
  codeRe: /(N2A|N2-\d+|N2)/,
  htmlCodeRe: /^N2-\d+$/,
  bareCodes: ['N2'],
})

/**
 * 把原始 sheetName 归一为分发键。
 *
 * @param sheetName 原始 tab 名
 * @param wpCode    sheetName 缺失时的回退
 */
export function normalizeN2SheetName(
  sheetName: string | null | undefined,
  wpCode?: string | null,
): string {
  return router.normalize(sheetName, wpCode)
}

/** 是否走 HTML 专属组件（其余走 OnlyOffice 兜底） */
export function isN2HtmlSheet(normalized: string): boolean {
  return router.isHtmlSheet(normalized)
}
