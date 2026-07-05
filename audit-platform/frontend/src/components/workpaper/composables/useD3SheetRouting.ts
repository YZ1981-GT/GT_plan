/**
 * D3 sheetName → 子组件路由键
 */
import { isSkipWorkpaperSheet } from './workpaperSkipSheets'

export function resolveD3SheetCode(name: string): string {
  if (isSkipWorkpaperSheet(name)) return 'skip'
  if (!name) return 'D3'
  if (name.includes('目录') || name.includes('底稿目录')) return 'directory'
  if (name === 'D3' || /^D3\s/.test(name.trim()) || /D3$/.test(name.trim())) return 'D3'

  const m = name.match(/(D3(?:A|-\d+))\s*$/)
  if (m) return m[1]

  if (name.includes('附注') && name.includes('国企')) return '附注国企'
  if (name.includes('附注') && (name.includes('上市') || name.includes('上市公司'))) {
    return '附注上市'
  }

  if (name.includes('审定表') || name.includes('D3-1')) return 'D3-1'
  if (name.includes('明细表') || name.includes('D3-2')) return 'D3-2'
  if (name.includes('调整分录') || name.includes('D3-3')) return 'D3-3'
  if (name.includes('分析表') || name.includes('D3-4')) return 'D3-4'
  if (name.includes('账龄') || name.includes('长期') || name.includes('D3-5')) return 'D3-5'
  if (name.includes('关联方') || name.includes('关联关系') || name.includes('D3-6')) return 'D3-6'
  if (name.includes('检查表') || name.includes('凭证') || name.includes('D3-7')) return 'D3-7'

  return name
}

export default resolveD3SheetCode
