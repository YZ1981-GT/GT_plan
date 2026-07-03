/**
 * D1 sheetName → 子组件路由键
 *
 * GtWpRenderer 传入完整中文 sheet 名（如「附注披露信息（上市公司）」），
 * 主入口 GtD1NotesReceivable 据此分发到 D1Tab* 子组件。
 */
export function resolveD1SheetCode(name: string): string {
  const m = name.match(/(D1(?:A|-\d+))\s*$/)
  if (m) return m[1]

  if (name.includes('附注') && name.includes('国企')) return 'disclosure-soe'
  if (name.includes('附注') && (name.includes('上市') || name.includes('上市公司'))) {
    return 'disclosure-listed'
  }

  if (name.includes('政策检查') || name.includes('D1-14')) return 'D1-14'
  if (name.includes('测算表') || name.includes('D1-15')) return 'D1-15'
  if (name.includes('分析提示')) return ''
  if (name.includes('业务模式') || name.includes('D1-6')) return 'D1-6'
  if (name.includes('备查簿') || name.includes('D1-7')) return 'D1-7'
  if (name.includes('背书') || name.includes('贴现明细') || name.includes('D1-8')) return 'D1-8'
  if (name.includes('贴息') || name.includes('D1-9')) return 'D1-9'
  if (name.includes('监盘') || name.includes('D1-10')) return 'D1-10'
  if (name.includes('关联方') || name.includes('D1-11')) return 'D1-11'
  if (name.includes('质押') || name.includes('D1-12')) return 'D1-12'
  if (name.includes('转回') || name.includes('核销') || name.includes('D1-16')) return 'D1-16'
  if (name.includes('检查表') || name.includes('D1-13')) return 'D1-13'
  if (name.includes('审定表') || name.includes('D1-1')) return 'D1-1'
  if (name.includes('按类别') || name.includes('D1-2')) return 'D1-2'
  if (name.includes('按客户') || name.includes('D1-3')) return 'D1-3'
  if (name.includes('坏账准备') || name.includes('D1-4')) return 'D1-4'
  if (name.includes('调整分录') || name.includes('D1-5')) return 'D1-5'

  return ''
}
