/**
 * N1 递延所得税资产底稿 sheet 分发（纯函数，可单测）
 *
 * 判定逻辑收敛在 `shared/cycleSheetRouting.ts`（披露判定前置于 wp_code 正则 +
 * 国企多写法全认）。
 *
 * 🔴 真实 sheet 名含「表的{码}」多字形态（模板层脏字面量 3 处全在 N1/N3）：
 * `递延所得税资产审计程序表的N1A` / `可用以后年度税前利润弥补的亏损检查表的N1-5`
 * — 正则 codeRe 须匹配含「的」前缀的 N1A/N1-5。
 *
 * spec: `.kiro/specs/n1-n3-host-inline-router-and-shared-adoption/` Task 2
 */
import {
  SHEET_DISCLOSURE_LISTED,
  SHEET_DISCLOSURE_SOE,
  SHEET_INDEX,
  makeCycleSheetRouter,
} from './shared/cycleSheetRouting'

export const N1_SHEET_DISCLOSURE_LISTED = SHEET_DISCLOSURE_LISTED
export const N1_SHEET_DISCLOSURE_SOE = SHEET_DISCLOSURE_SOE
export const N1_SHEET_INDEX = SHEET_INDEX

const router = makeCycleSheetRouter({
  // N1A 程序表 + N1-1~N1-5 子表 + N1 目录
  // 🔴 codeRe 须能从「…表的N1A」形态中提取 N1A
  codeRe: /(N1A|N1-[1-5]|N1)/,
  htmlCodeRe: /^N1-[1-5]$/,
  bareCodes: ['N1'],
})

/**
 * 把原始 sheetName 归一为分发键。
 *
 * @param sheetName 原始 tab 名
 * @param wpCode    sheetName 缺失时的回退
 */
export function normalizeN1SheetName(
  sheetName: string | null | undefined,
  wpCode?: string | null,
): string {
  return router.normalize(sheetName, wpCode)
}

/** 是否走 HTML 专属组件（其余走 OnlyOffice 兜底）；N1A 走程序表路由 */
export function isN1HtmlSheet(normalized: string): boolean {
  // N1A 走程序表（GtAProgramConsole），不是 HTML 专属组件
  if (normalized === 'N1A') return false
  return router.isHtmlSheet(normalized)
}
