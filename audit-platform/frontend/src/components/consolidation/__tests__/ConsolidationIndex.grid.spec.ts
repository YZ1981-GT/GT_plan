/**
 * 合并总览接统一表格选区门面（spec excel-style-table-editing 5.6）。
 * 子组件里的试算平衡表必须显式 follow，否则右键值与底部统计会继续读上一张报表的内核。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const source = readFileSync(resolve(__dirname, '../../../views/ConsolidationIndex.vue'), 'utf-8')

function bodyOf(name: string): string {
  const start = source.indexOf(`function ${name}(`)
  if (start < 0) throw new Error(`找不到 ${name}`)
  let depth = 0
  let opened = false
  for (let i = source.indexOf('{', start); i < source.length; i++) {
    if (source[i] === '{') { depth++; opened = true }
    else if (source[i] === '}' && --depth === 0 && opened) return source.slice(start, i + 1)
  }
  throw new Error(`${name} 函数体不完整`)
}

describe('ConsolidationIndex 表格选区接线', () => {
  it('同一 consolCtx 显式跟随 ConsolTrialBalanceTab 内的 ctb-table', () => {
    expect(source).toMatch(/consolCtx\.followTables\(\(\) => \{[\s\S]*?consolTbTabRef\.value[\s\S]*?querySelector\('\[data-testid="ctb-table"\]'\)/)
  })

  it('报表右键落在已有选区内也按本次点击刷新菜单与穿透目标', () => {
    const body = bodyOf('onReportCellContextMenu')
    expect(body).toContain('if (!consolCtx.kernelActive() && !consolCtx.isCellSelected(rowIdx, colIdx))')
    expect(body).toContain("drillDownCell.itemName = row.row_name || ''")
    expect(body).toContain('drillDownCell.colName = column.label')
    expect(body).toContain('consolCtx.openContextMenu(event, drillDownCell.itemName, row)')
  })
})
