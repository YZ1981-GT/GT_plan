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
  it('G13 listed: 9 data rows (+ total in UI)', () => {
    expect(G13_DISCLOSURE_LISTED_ROWS).toHaveLength(9)
    expect(G13_DISCLOSURE_LISTED_ROWS[0].label).toBe('交易性金融资产')
    expect(G13_DISCLOSURE_LISTED_ROWS.at(-1)?.rowKey).toBe('other')
  })

  it('G13 SOE: 7 data rows', () => {
    expect(G13_DISCLOSURE_SOE_ROWS).toHaveLength(7)
    expect(G13_DISCLOSURE_SOE_ROWS.map((r) => r.rowKey)).toContain('derivative_assets')
  })

  it('G14 listed: 9 line items matching G14-2', () => {
    expect(G14_DISCLOSURE_LISTED_ROWS).toHaveLength(9)
  })

  it('G14 SOE: 4 aggregated rows + bad debt sources', () => {
    expect(G14_DISCLOSURE_SOE_ROWS).toHaveLength(4)
    expect(G14_DISCLOSURE_SOE_ROWS[0].label).toBe('坏账损失')
    expect(G14_SOE_BAD_DEBT_SOURCES.length).toBeGreaterThan(3)
  })
})
