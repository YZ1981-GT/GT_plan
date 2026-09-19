/**
 * D6 sheetName → 子组件路由键
 */
import { isSkipWorkpaperSheet } from './workpaperSkipSheets'

export function resolveD6SheetCode(name: string): string {
  if (isSkipWorkpaperSheet(name)) return 'skip'
  if (!name) return 'D6'
  if (name.includes('目录') || name.includes('底稿目录')) return 'D6'

  const m = name.match(/(D6(?:A|-\d+))\s*$/)
  if (m) return m[1]

  if (name.includes('附注') && name.includes('国企')) return '附注国企'
  if (name.includes('附注') && (name.includes('上市') || name.includes('上市公司'))) {
    return '附注上市'
  }

  if (name.includes('程序表') || name.includes('D6A')) return 'D6A'
  if (name.includes('审定') || (name.includes('D6') && !name.includes('D6-'))) return 'D6-1'
  if (name.includes('明细') || name.includes('D6-2')) return 'D6-2'
  if (name.includes('减值准备明细') || name.includes('D6-3')) return 'D6-3'
  if (name.includes('调整分录') || name.includes('D6-4')) return 'D6-4'
  if (name.includes('关联') || name.includes('D6-5')) return 'D6-5'
  if (name.includes('检查表') || name.includes('D6-6')) return 'D6-6'
  if (name.includes('减值政策') || name.includes('D6-7')) return 'D6-7'
  if (name.includes('减值准备测算') || name.includes('ECL') || name.includes('D6-8')) return 'D6-8'
  if (name.includes('转回') || name.includes('核销') || name.includes('D6-9')) return 'D6-9'

  return name
}

export default resolveD6SheetCode
