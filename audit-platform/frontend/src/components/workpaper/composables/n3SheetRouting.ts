/**
 * N3 递延所得税负债底稿 sheet 分发（纯函数，可单测）
 *
 * 判定逻辑收敛在 `shared/cycleSheetRouting.ts`（披露判定前置于 wp_code 正则 +
 * 国企多写法全认）。
 *
 * 🔴 N3 无附注披露（空分母）：源模板 `N3 递延所得税负债.xlsx` 无「附注披露信息」sheet。
 * 递延所得税负债的附注披露与 N1 共节（五、30 / 八、31），由 N1 的披露 Tab 推送。
 * 含「表的{码}」脏形态：`递延所得税负债审计程序表的N3A`
 *
 * spec: `.kiro/specs/n1-n3-host-inline-router-and-shared-adoption/` Task 2
 */
import {
  SHEET_DISCLOSURE_LISTED,
  SHEET_DISCLOSURE_SOE,
  SHEET_INDEX,
  makeCycleSheetRouter,
} from './shared/cycleSheetRouting'

export const N3_SHEET_DISCLOSURE_LISTED = SHEET_DISCLOSURE_LISTED
export const N3_SHEET_DISCLOSURE_SOE = SHEET_DISCLOSURE_SOE
export const N3_SHEET_INDEX = SHEET_INDEX

const router = makeCycleSheetRouter({
  // N3A 程序表 + N3-1~N3-3 子表 + N3 目录
  codeRe: /(N3A|N3-[1-3]|N3)/,
  htmlCodeRe: /^N3-[1-3]$/,
  bareCodes: ['N3'],
})

/**
 * 把原始 sheetName 归一为分发键。
 *
 * @param sheetName 原始 tab 名
 * @param wpCode    sheetName 缺失时的回退
 */
export function normalizeN3SheetName(
  sheetName: string | null | undefined,
  wpCode?: string | null,
): string {
  return router.normalize(sheetName, wpCode)
}

/**
 * 是否走 HTML 专属组件（其余走 OnlyOffice 兜底）。
 * N3A 走 OnlyOffice 兜底（Phase 6 前暂不做 HTML 组件化）。
 * 🔴 N3 无附注 → 披露常量导出但从不命中（空分母）。
 */
export function isN3HtmlSheet(normalized: string): boolean {
  // N3A 走 OnlyOffice 兜底
  if (normalized === 'N3A') return false
  return router.isHtmlSheet(normalized)
}
