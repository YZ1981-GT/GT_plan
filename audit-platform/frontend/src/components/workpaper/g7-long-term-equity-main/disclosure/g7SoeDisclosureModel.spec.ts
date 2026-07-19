import { describe, expect, it } from 'vitest'
import {
  G7_SOE_DISCLOSURE_SECTIONS,
  buildG7SoeSyncPayloads,
  createG7SoeDisclosureState,
  g7SoeChapterSections,
} from './g7SoeDisclosureModel'

describe('G7 SOE disclosure source model', () => {
  it('splits the sheet into consolidation-scope and long-term-equity chapters', () => {
    const chapterIds = [...new Set(G7_SOE_DISCLOSURE_SECTIONS.map(section => section.chapter))]
    expect(chapterIds).toEqual(['consolidation-scope', 'long-term-equity'])

    const consolidation = g7SoeChapterSections('consolidation-scope')
    const longTerm = g7SoeChapterSections('long-term-equity')
    expect(consolidation.map(section => section.id)).toContain('subsidiary-basic')
    expect(consolidation.map(section => section.id)).toContain('common-control-combination')
    expect(consolidation.map(section => section.id)).toContain('ownership-interest-changes')
    expect(longTerm.map(section => section.id)).toEqual(['long-term-equity-investment'])
  })

  it('keeps heterogeneous tables instead of a uniform 17-column placeholder', () => {
    const tables = G7_SOE_DISCLOSURE_SECTIONS.flatMap(section => section.tables ?? [])
    const narratives = G7_SOE_DISCLOSURE_SECTIONS.flatMap(section => section.narratives ?? [])
    expect(tables.length).toBeGreaterThanOrEqual(20)
    expect(narratives.length).toBeGreaterThanOrEqual(15)

    const subsidiary = tables.find(table => table.id === 'subsidiary-basic')
    expect(subsidiary?.sourceRows).toBe('A9:M19')
    expect(subsidiary?.columns.map(column => column.key)).toContain('level')
    expect(subsidiary?.columns.map(column => column.key)).toContain('acquisitionMethod')

    const classification = tables.find(table => table.id === 'lte-classification')
    expect(classification?.sourceRows).toBe('A201:F208')
    expect(classification?.columns).toHaveLength(4)
  })

  it('routes sync payloads to multiple note sections, not only long-term equity', () => {
    const state = createG7SoeDisclosureState()
    state.texts['holding-voting-diff'] = '持股比例与表决权比例差异说明。'
    state.texts['lte-holding-voting-diff'] = '索引至附注十一、3。'
    state.tables['subsidiary-basic'][0].label = '甲子公司'

    const payloads = buildG7SoeSyncPayloads(state)
    const sectionIds = payloads.map(payload => payload.noteSectionId)
    expect(sectionIds).toContain('七、本期纳入合并报表')
    expect(sectionIds).toContain('七、本期发生的同一控')
    expect(sectionIds).toContain('八、18')
    expect(sectionIds).not.toContain('五、18')

    const consolidationPayload = payloads.find(payload => payload.noteSectionId === '七、本期纳入合并报表')
    expect(consolidationPayload?.subTableData['本期纳入合并报表范围的子公司基本情况'][0].项目).toBe('甲子公司')
    expect(consolidationPayload?.subTableData._note_texts).toEqual([
      {
        section: 'holding-voting-diff',
        title: '持股比例与表决权比例差异说明',
        text: '持股比例与表决权比例差异说明。',
      },
    ])

    const mismatch = payloads.find(payload => payload.noteSectionId === '七')
    expect(mismatch).toBeTruthy()

    const ltePayload = payloads.find(payload => payload.noteSectionId === '八、18')
    expect(ltePayload?.subTableData['长期股权投资分类']).toBeTruthy()
    expect(ltePayload?.subTableData['长期股权投资明细']).toBeTruthy()
    expect(ltePayload?.subTableData._note_texts?.some((item: any) => item.section === 'lte-holding-voting-diff')).toBe(true)
  })

  it('materializes computed totals and keeps G7-16 associate lineage on rows 17-19', () => {
    const state = createG7SoeDisclosureState()
    state.tables['lte-classification'].find(row => row.id === 'lte-sub')!.values.closing = 100
    state.tables['lte-classification'].find(row => row.id === 'lte-jv')!.values.closing = 40
    state.tables['lte-classification'].find(row => row.id === 'lte-assoc')!.values.closing = 20
    state.tables['lte-classification'].find(row => row.id === 'lte-impairment')!.values.closing = 15

    const payloads = buildG7SoeSyncPayloads(state)
    const ltePayload = payloads.find(payload => payload.noteSectionId === '八、18')
    const classification = ltePayload?.subTableData['长期股权投资分类'] ?? []
    const total = classification.find((row: any) => row._row_id === 'lte-total')
    expect(total?.closing).toBe(145)

    expect(state.tables['unrecognized-losses'].find(row => row.id === 'ul-assoc-1')?.source).toContain('第17行')
    expect(state.tables['unrecognized-losses'].find(row => row.id === 'ul-assoc-3')?.source).toContain('第19行')
  })

  it('preserves source-workpaper lineage on formula-driven rows', () => {
    const state = createG7SoeDisclosureState()
    expect(state.tables['subsidiary-basic'][0].source).toContain('被投资单位基本信息G7-4')
    expect(state.tables['former-subsidiary-basic'][0].source).toContain('处置子公司测试表G7-11')
    expect(state.tables['lte-classification'].find(row => row.id === 'lte-jv')?.source).toContain('G7-1')
    expect(state.tables['important-jv-fs'][0].source).toContain('G7-5')
    expect(state.tables['unrecognized-losses'].find(row => row.id === 'ul-jv-1')?.source).toContain('G7-16')
  })
})
