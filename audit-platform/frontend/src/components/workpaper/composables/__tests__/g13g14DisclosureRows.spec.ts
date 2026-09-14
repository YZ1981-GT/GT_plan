import { describe, it, expect } from 'vitest'
import {
  G13_DISCLOSURE_LISTED_ROWS,
  G13_DISCLOSURE_SOE_ROWS,
} from '../g13Constants'
import {
  G14_DISCLOSURE_LISTED_ROWS,
  G14_DISCLOSURE_SOE_ROWS,
  G14_SOE_BAD_DEBT_SOURCES,
} from '../g14Constants'

describe('G13/G14 disclosure row counts (xlsx-aligned)', () => {
  it('G13 listed: 9 data rows (+ total in UI)，其中项挂靠 parentKey', () => {
    expect(G13_DISCLOSURE_LISTED_ROWS).toHaveLength(9)
    expect(G13_DISCLOSURE_LISTED_ROWS[0].label).toBe('交易性金融资产')
    expect(G13_DISCLOSURE_LISTED_ROWS.at(-1)?.rowKey).toBe('other')
    expect(G13_DISCLOSURE_LISTED_ROWS.filter((r) => r.ofWhich)).toHaveLength(3)
    expect(G13_DISCLOSURE_LISTED_ROWS.find((r) => r.rowKey === 'designated_fv_assets')?.parentKey)
      .toBe('trading_assets')
  })

  it('G13 SOE: 7 data rows', () => {
    expect(G13_DISCLOSURE_SOE_ROWS).toHaveLength(7)
    expect(G13_DISCLOSURE_SOE_ROWS.map((r) => r.rowKey)).toContain('derivative_assets')
  })

  it('G14 listed: 10 line items matching G14-2（含合同资产）', () => {
    expect(G14_DISCLOSURE_LISTED_ROWS).toHaveLength(10)
    expect(G14_DISCLOSURE_LISTED_ROWS.map((r) => r.rowKey)).toContain('ca')
  })

  it('G14 SOE: 4 aggregated rows + bad debt sources', () => {
    expect(G14_DISCLOSURE_SOE_ROWS).toHaveLength(4)
    expect(G14_DISCLOSURE_SOE_ROWS[0].label).toBe('坏账损失')
    expect(G14_SOE_BAD_DEBT_SOURCES).toEqual(['notes', 'ar', 'rfin', 'othar', 'ltar', 'ca'])
    expect(G14_SOE_BAD_DEBT_SOURCES).not.toContain('guarantee')
  })
})
