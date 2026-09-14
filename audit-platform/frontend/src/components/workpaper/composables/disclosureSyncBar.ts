/**
 * 底稿披露 sheet 判定与变体解析（附注联动复盘 P0-2）
 *
 * 单一真源：`GtWpRenderer`（是否渲染同步状态条）与 `GtWpDisclosureSyncBar`
 * （查哪个变体的章节状态）共用，避免两处正则漂移。
 *
 * 各循环披露 sheet 命名不统一（实测）：
 *   附注披露信息（上市公司） / 附注披露信息(国企) / 附注披露信息（国有企业）
 *   附注上市 / 附注国企 / F1-note-listed / G2-note-soe / 附注披露（上市公司）
 */

export type DisclosureVariantKey = 'listed' | 'soe'

/** 是否为附注披露 sheet（宽判据；最终是否有映射由后端 registry 决定） */
export function isDisclosureSheetName(sheetName: string | null | undefined): boolean {
  const s = (sheetName || '').trim()
  if (!s) return false
  return /附注/.test(s) || /-note-(listed|soe)$/i.test(s)
}

/** 由 sheet 名解析上市/国企变体；无法判定返回 null（单变体科目由调用方兜底） */
export function resolveDisclosureVariantFromSheet(
  sheetName: string | null | undefined,
): DisclosureVariantKey | null {
  const s = (sheetName || '').trim()
  if (!s) return null
  if (/上市|listed/i.test(s)) return 'listed'
  if (/国企|国有|soe/i.test(s)) return 'soe'
  return null
}
