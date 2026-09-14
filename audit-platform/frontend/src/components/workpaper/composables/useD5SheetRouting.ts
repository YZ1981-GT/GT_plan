/**
 * D5 sheetName → 子组件路由键
 */
import { isSkipWorkpaperSheet } from './workpaperSkipSheets'

export function resolveD5SheetCode(name: string): string {
  if (isSkipWorkpaperSheet(name)) return 'skip'
  if (!name) return 'D5'
  if (name.includes('目录') || name.includes('底稿目录')) return 'D5'

  const m = name.match(/(D5(?:A|-\d+))\s*$/)
  if (m) return m[1]

  if (name.includes('附注') && name.includes('国企')) return '附注国企'
  if (name.includes('附注') && (name.includes('上市') || name.includes('上市公司'))) {
    return '附注上市'
  }

  if (name.includes('程序表') || name.includes('D5A')) return 'D5A'
  if (name.includes('审定') || (name.includes('D5') && !name.includes('D5-'))) return 'D5-1'
  if (name.includes('明细') || name.includes('D5-2')) return 'D5-2'
  if (name.includes('调整分录') || name.includes('D5-3')) return 'D5-3'
  if (name.includes('公允价值') || name.includes('D5-4')) return 'D5-4'

  return name
}

export default resolveD5SheetCode
