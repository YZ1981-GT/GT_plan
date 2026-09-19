/** GT_Custom 等占位 sheet，HTML 渲染器应跳过 */
export const SKIP_WORKPAPER_SHEET_NAMES = new Set(['GT_Custom', 'gt_custom'])

export function isSkipWorkpaperSheet(name: string | undefined | null): boolean {
  if (!name) return false
  const trimmed = name.trim()
  if (SKIP_WORKPAPER_SHEET_NAMES.has(trimmed)) return true
  return trimmed.toUpperCase() === 'GT_CUSTOM'
}
