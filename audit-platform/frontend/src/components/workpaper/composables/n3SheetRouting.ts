/**
 * N3 递延所得税负债底稿 sheet 分发（纯函数，可单测）
 *
 * spec: `.kiro/specs/n1-n3-host-inline-router-and-shared-adoption` Task 2（BP-10 收口）
 *
 * 判定逻辑收敛到 `shared/cycleSheetRouting.ts`（与 N2/N4/N5 同形）。
 *
 * 🔴 N3 的唯一例外：源模板**无**附注披露 sheet（披露与 N1 共节 五、30 / 八、31），
 * `N3TabDisclosure.vue` 已删除。共享路由会把含「附注」的 tab 判成披露键并视作 HTML ——
 * 在 N3 上那会渲染出一个空白 Tab。故 `isN3HtmlSheet` 对披露键返回 false，落 OnlyOffice
 * 兜底（至少看得到原始内容），与原宿主实现的有意设计一致。
 */
import {
  SHEET_DISCLOSURE_LISTED,
  SHEET_DISCLOSURE_SOE,
  SHEET_INDEX,
  makeCycleSheetRouter,
} from './shared/cycleSheetRouting'

export const N3_SHEET_INDEX = SHEET_INDEX

const router = makeCycleSheetRouter({
  codeRe: /(N3A|N3-\d+|N3)/,
  htmlCodeRe: /^N3-\d+$/,
  bareCodes: ['N3'],
})

export function normalizeN3SheetName(
  sheetName: string | null | undefined,
  wpCode?: string | null,
): string {
  return router.normalize(sheetName, wpCode)
}

export function isN3HtmlSheet(normalized: string): boolean {
  if (normalized === SHEET_DISCLOSURE_LISTED || normalized === SHEET_DISCLOSURE_SOE) return false
  if (normalized === 'N3A') return false
  return router.isHtmlSheet(normalized)
}
