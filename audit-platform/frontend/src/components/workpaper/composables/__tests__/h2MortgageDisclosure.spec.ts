/**
 * H2 抵押 → 附注受限披露映射单测
 */
import { describe, it, expect } from 'vitest'
import {
  mapMortgagedDetailToRows,
  buildMortgageNoteText,
} from '../h2ListedDisclosureModel'

describe('H2 mortgage → disclosure', () => {
  it('仅带出 isMortgaged=Y 的工程，金额优先审定净值', () => {
    const rows = mapMortgagedDetailToRows([
      { name: '厂房', isMortgaged: 'Y', netEndAud: 800_000, endAudited: 900_000, cipEnd: 900_000, projectCode: 'P1' },
      { name: '仓库', isMortgaged: 'N', netEndAud: 100_000 },
      { name: '专线', isMortgaged: 'Y', endAudited: 50_000 },
    ])
    expect(rows).toHaveLength(2)
    expect(rows[0].name).toBe('厂房')
    expect(rows[0].amount).toBe(800_000)
    expect(rows[0].description).toContain('P1')
    expect(rows[1].amount).toBe(50_000)
  })

  it('生成披露说明文本', () => {
    const text = buildMortgageNoteText([
      { rowId: '1', name: '码头', amount: 1_000_000, description: '在建工程抵押', remark: '' },
    ])
    expect(text).toContain('码头')
    expect(text).toContain('1,000,000.00')
  })
})
