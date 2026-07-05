/**
 * D7 sheetName → 子组件路由键
 */
import { isSkipWorkpaperSheet } from './workpaperSkipSheets'

export function resolveD7SheetCode(name: string): string {
  if (isSkipWorkpaperSheet(name)) return 'skip'
  if (!name) return 'D7'
  if (name.includes('目录') || name.includes('底稿目录')) return 'D7'

  const m = name.match(/(D7(?:A|-\d+))\s*$/)
  if (m) return m[1]

  if (name.includes('附注') && name.includes('国企')) return '附注国企'
  if (name.includes('附注') && (name.includes('上市') || name.includes('上市公司'))) {
    return '附注上市'
  }

  if (name.includes('程序表') || name.includes('D7A')) return 'D7A'
  if (name.includes('审定') || (name.includes('D7') && !name.includes('D7-'))) return 'D7-1'
  if (name.includes('明细') || name.includes('D7-2')) return 'D7-2'
  if (name.includes('调整分录') || name.includes('D7-3')) return 'D7-3'
  if (name.includes('分析') || name.includes('D7-4')) return 'D7-4'
  if (name.includes('账龄') || name.includes('D7-5')) return 'D7-5'
  if (name.includes('关联方') || name.includes('D7-6')) return 'D7-6'
  if (name.includes('凭证') || name.includes('D7-7')) return 'D7-7'

  return name
}

export default resolveD7SheetCode
