import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { useK1DisclosureTrace } from '../k1DisclosureTrace'
import {
  resolveK11PortfolioRowKey,
  resolveK18GroupFocus,
  createK1RowNavigation,
} from '../useK1RowNavigation'

describe('resolveK11PortfolioRowKey', () => {
  it('maps 账龄组合 to r1', () => {
    expect(resolveK11PortfolioRowKey('账龄组合')).toBe('r1')
  })

  it('maps 单项计提 to r0', () => {
    expect(resolveK11PortfolioRowKey('单项计提')).toBe('r0')
  })
})

describe('resolveK18GroupFocus', () => {
  it('finds aging group by portfolio label', () => {
    const map = new Map<string, any>([
      ['K1-8-bad-debt-calc', {
        remark: JSON.stringify({
          version: 2,
          singleRows: [],
          creditGroups: [],
          agingGroups: [{ groupId: 'grp-aging-1', groupName: '账龄组合', rows: [] }],
        }),
      }],
    ])
    const focus = resolveK18GroupFocus(map, '账龄组合')
    expect(focus?.groupId).toBe('grp-aging-1')
    expect(focus?.calcSection).toBe('aging')
  })
})

describe('K1-1 ↔ K1-8 portfolio navigation', () => {
  it('navigateToRow stores portfolio focus for K1-8', () => {
    const emit = vi.fn()
    const nav = createK1RowNavigation(emit)
    nav.navigateToRow({ sheet: 'K1-8', portfolioLabel: '账龄组合', sourceSheet: 'K1-1' })
    expect(emit).toHaveBeenCalledWith('坏账准备测算K1-8')
    const focus = nav.consumeFocus('K1-8')
    expect(focus?.portfolioLabel).toBe('账龄组合')
    expect(focus?.sourceSheet).toBe('K1-1')
  })

  it('reverse navigation to K1-1', () => {
    const nav = createK1RowNavigation(() => {})
    nav.navigateToRow({ sheet: 'K1-1', portfolioLabel: '其他组合', sourceSheet: 'K1-8' })
    const focus = nav.consumeFocus('K1-1')
    expect(focus?.portfolioLabel).toBe('其他组合')
    const rowKey = resolveK11PortfolioRowKey(focus!.portfolioLabel!)
    expect(rowKey).toBe('r3')
  })
})

describe('useK1DisclosureTrace', () => {
  it('flags aging mismatch vs K1-1', () => {
    const map = ref(new Map<string, any>([
      ['K1-1-audited-receivable', { remark: '1000' }],
      ['K1-note-listed-rows', {
        remark: JSON.stringify({
          agingRows: [
            { kind: 'data', endAmount: 500 },
            { kind: 'subtotal', endAmount: 500 },
          ],
        }),
      }],
    ]))
    const { traceRows } = useK1DisclosureTrace('listed', map)
    const aging = traceRows.value.find((r) => r.id === 'aging')
    expect(aging?.status).toBe('warn')
  })

  it('returns trace rows for SOE variant', () => {
    const map = ref(new Map<string, any>([
      ['K1-1-audited-receivable', { remark: '2000' }],
    ]))
    const { traceRows } = useK1DisclosureTrace('soe', map)
    expect(traceRows.value.length).toBeGreaterThan(5)
  })
})
