/**
 * 合并总览的统一选区与汇总穿透接线守卫。
 * 目标值构造的数值/上下文行为由 consolDrillTarget.spec.ts 验证；本文件钉住页面必须调用该真源，
 * 且请求不得再从 selectedCells[0] 或活动 Tab 反推身份。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { parse } from '@vue/compiler-sfc'
import { describe, expect, it } from 'vitest'

const raw = readFileSync(resolve(__dirname, '../../../views/ConsolidationIndex.vue'), 'utf-8')
const parsed = parse(raw, { filename: 'ConsolidationIndex.vue' })
const source = parsed.descriptor.scriptSetup?.content ?? ''

function bodyOf(name: string): string {
  const match = new RegExp(`(?:async\\s+)?function\\s+${name}\\s*\\(`).exec(source)
  if (!match) throw new Error(`找不到 ${name}`)
  let depth = 0
  let opened = false
  for (let i = source.indexOf('{', match.index); i < source.length; i += 1) {
    if (source[i] === '{') { depth += 1; opened = true }
    else if (source[i] === '}' && --depth === 0 && opened) return source.slice(match.index, i + 1)
  }
  throw new Error(`${name} 函数体不完整`)
}

function withoutComments(value: string): string {
  return value
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

describe('ConsolidationIndex 表格选区接线', () => {
  it('SFC 可解析且同一 consolCtx 跟随子组件真实试算表', () => {
    expect(parsed.errors).toEqual([])
    expect(source.length).toBeGreaterThan(30_000)
    expect(source).toMatch(/consolCtx\.followTables\(\(\) => \{[\s\S]*?consolTbTabRef\.value[\s\S]*?querySelector\('\[data-testid="ctb-table"\]'\)/)
  })

  it('报表右键永远用本次事件构造冻结目标，即使落在已有多选区', () => {
    const body = withoutComments(bodyOf('onReportCellContextMenu'))
    expect(body).toContain('if (!consolCtx.kernelActive() && !consolCtx.isCellSelected(rowIdx, colIdx))')
    expect(body).toContain('const target = reportDrillTarget(row, column)')
    expect(body).toContain('setConsolDrillTarget(target)')
    expect(body).toContain("consolCtx.openContextMenu(event, target?.itemName || row.row_name || '', row)")
    expect(body).not.toContain('selectedCells.value[0]')
    expect(body).not.toContain('drillDownCell.')
  })

  it('TB 右键从子组件真实 reportType/nodeKey 与本次行构造目标', () => {
    const body = bodyOf('onTbCellContextMenu')
    expect(body).toContain('createTbConsolDrillTarget(row')
    expect(body).toContain('reportType: consolTbType.value')
    expect(body).toContain('nodeKey: consolTbNodeKey.value')
    expect(body).toContain('setConsolDrillTarget(target)')
  })

  it('打开弹窗不再依赖报表行数，也不覆盖已建立目标', () => {
    const body = withoutComments(bodyOf('openCellDrillDown'))
    expect(body).toContain('const target = drillDownTarget.value')
    expect(body).toContain('isConsolDrillTargetCurrent(target, currentConsolDrillContext())')
    expect(body).toContain('loadDrillDownData(target)')
    expect(body).not.toContain('consolReportRows.value.length')
    expect(body).not.toContain('请在报表中选择科目')
    expect(body).not.toContain('drillDownCell.')
  })

  it('加载只读目标快照并向后端发送真实行、类型和节点', () => {
    const body = withoutComments(bodyOf('loadDrillDownData'))
    expect(body).toContain('report_type: target.reportType')
    expect(body).toContain('row_code: target.rowCode')
    expect(body).toContain('node_key: target.nodeKey')
    expect(body).toContain('{ signal: ticket.signal }')
    expect(body).not.toContain('selectedCells')
    expect(body).not.toContain('consolReportRows')
    expect(body).not.toContain('consolTbRows')
  })

  it('上期在 POST 前返回，direct/leaf 与 ACNR 响应都受同一请求票据保护', () => {
    const body = withoutComments(bodyOf('loadDrillDownData'))
    const priorGate = body.indexOf("target.period === 'prior'")
    const request = body.indexOf('await api.post(')
    expect(priorGate).toBeGreaterThan(0)
    expect(request).toBeGreaterThan(priorGate)
    expect(body.match(/drillDownRequestGuard\.isStale\(ticket\)/g)?.length).toBeGreaterThanOrEqual(4)
    const responseStart = body.indexOf('const result: any = await api.post(')
    const responseGuard = body.indexOf('if (drillDownRequestGuard.isStale(ticket)) return', responseStart)
    const resultProjection = body.indexOf('const toRow =', responseStart)
    expect(responseGuard).toBeGreaterThan(responseStart)
    expect(resultProjection).toBeGreaterThan(responseGuard)
    expect(body).toContain('resolveAccountJump(target.accountCode)')
  })

  it('项目、年度、Tab、报表类型和节点变化统一 reset，卸载会 abort', () => {
    expect(source).toMatch(/watch\(\[[\s\S]*?projectId\.value[\s\S]*?effectiveConsolYear\(\)[\s\S]*?activeTab\.value[\s\S]*?consolReportType\.value[\s\S]*?currentEntityNodeKey\.value[\s\S]*?consolTbType\.value[\s\S]*?consolTbNodeKey\.value[\s\S]*?\], resetConsolDrillDown\)/)
    expect(bodyOf('resetConsolDrillDown')).toContain('drillDownRequestGuard.abort()')
    expect(source).toMatch(/onUnmounted\(\(\) => \{[\s\S]*?resetConsolDrillDown\(\)/)
  })
})
