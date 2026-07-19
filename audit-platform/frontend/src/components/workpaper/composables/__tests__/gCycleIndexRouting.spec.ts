import { describe, it, expect } from 'vitest'
import {
  isCycleDelegatedIndexSheet,
  resolveCycleIndexComponentType,
  buildCycleArchitectureHtmlData,
} from '../gCycleIndexRouting'

describe('gCycleIndexRouting', () => {
  it('G12/G13/G14/H10 b-index 委托到循环 HTML 目录组件', () => {
    expect(isCycleDelegatedIndexSheet('b-index', 'G12')).toBe(true)
    expect(resolveCycleIndexComponentType('b-index', 'G12')).toBe('g12-net-hedge-gains')
    expect(resolveCycleIndexComponentType('b-index', 'G13')).toBe('g13-fair-value-changes')
    expect(resolveCycleIndexComponentType('b-index', 'G14')).toBe('g14-credit-impairment-loss')
    expect(isCycleDelegatedIndexSheet('b-index', 'H10')).toBe(true)
    expect(resolveCycleIndexComponentType('b-index', 'H10')).toBe('h10-asset-disposal-income')
  })

  it('其他底稿 b-index 保持 GtBIndex', () => {
    expect(isCycleDelegatedIndexSheet('b-index', 'D4')).toBe(false)
    expect(resolveCycleIndexComponentType('b-index', 'D4')).toBe('b-index')
  })

  it('非 b-index sheet 不受影响', () => {
    expect(resolveCycleIndexComponentType('g12-net-hedge-gains', 'G12')).toBe('g12-net-hedge-gains')
  })

  it('buildCycleArchitectureHtmlData 从 sheets 构造 navigation_rows', () => {
    const data = buildCycleArchitectureHtmlData(
      {},
      [
        { sheet_name: '底稿目录', componentType: 'b-index' },
        { sheet_name: '审定表G12-1', componentType: 'g12-net-hedge-gains' },
      ],
      'G12',
    )
    const rows = data.navigation_rows as Array<{ content: string }>
    expect(rows).toHaveLength(1)
    expect(rows[0].content).toBe('审定表G12-1')
  })

  it('buildCycleArchitectureHtmlData 也按名称跳过底稿目录', () => {
    const data = buildCycleArchitectureHtmlData(
      {},
      [
        { sheet_name: '底稿目录', componentType: 'g2-interest-receivable' },
        { sheet_name: '审定表G2-1', componentType: 'g2-interest-receivable' },
      ],
      'G2',
    )
    const rows = data.navigation_rows as Array<{ content: string }>
    expect(rows).toHaveLength(1)
    expect(rows[0].content).toBe('审定表G2-1')
  })
})
