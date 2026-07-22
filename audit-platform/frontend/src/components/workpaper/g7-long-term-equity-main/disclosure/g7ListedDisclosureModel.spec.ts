import { describe, expect, it } from 'vitest'
import {
  G7_LISTED_DISCLOSURE_SECTIONS,
  buildG7ListedSyncData,
  createG7ListedDisclosureState,
} from './g7ListedDisclosureModel'

describe('G7 listed disclosure source model', () => {
  it('keeps the real Excel hierarchy instead of the legacy five-section placeholder', () => {
    expect(G7_LISTED_DISCLOSURE_SECTIONS.map(section => section.id)).toEqual([
      'investment-movement',
      'subsidiary-interests',
      'joint-associate-interests',
      'joint-operations',
    ])

    const tables = G7_LISTED_DISCLOSURE_SECTIONS.flatMap(section => section.tables ?? [])
    const narratives = G7_LISTED_DISCLOSURE_SECTIONS.flatMap(section => section.narratives ?? [])
    expect(tables).toHaveLength(15)
    expect(narratives).toHaveLength(11)
    expect(tables.find(table => table.id === 'investment-movement')?.sourceRows).toBe('A8:M23')
    expect(tables.find(table => table.id === 'joint-operations')?.sourceRows).toBe('A235:F240')
  })

  it('preserves source-workpaper lineage and separates note text during sync', () => {
    const state = createG7ListedDisclosureState()
    const composition = state.tables['subsidiary-composition']
    expect(composition[0].source).toContain('被投资单位基本信息G7-4')

    state.texts['impairment-method'] = '按预计未来现金流量现值确定可收回金额。'
    const syncData = buildG7ListedSyncData(state)
    expect(syncData['（1）企业集团的构成']).toHaveLength(3)
    expect(syncData['长期股权投资']).toBeTruthy()
    expect(syncData._note_texts).toEqual([
      {
        section: 'impairment-method',
        title: '长期资产减值测试说明',
        text: '按预计未来现金流量现值确定可收回金额。',
      },
    ])
  })

  it('aligns unimportant aggregate and excess losses to grouped Excel structure', () => {
    const state = createG7ListedDisclosureState()
    const aggregate = state.tables['unimportant-aggregate']
    expect(aggregate.some(row => row.id === 'ua-jv-group')).toBe(true)
    expect(aggregate.some(row => row.id === 'ua-assoc-comprehensive')).toBe(true)

    const excess = state.tables['excess-losses']
    expect(excess.find(row => row.id === 'el-assoc-1')?.source).toContain('第17行')
    expect(excess.find(row => row.id === 'el-total')?.sumRows).toEqual(['el-jv-subtotal', 'el-assoc-subtotal'])

    state.tables['investment-movement'].find(row => row.id === 'joint-venture-1')!.values.closingBook = 10
    state.tables['investment-movement'].find(row => row.id === 'associate-1')!.values.closingBook = 30
    const syncData = buildG7ListedSyncData(state)
    const total = syncData['长期股权投资'].find((row: any) => row._row_id === 'investment-total')
    expect(total?.closingBook).toBe(40)
  })
})
