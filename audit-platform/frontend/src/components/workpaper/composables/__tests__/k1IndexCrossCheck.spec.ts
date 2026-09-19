import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useK1IndexCrossCheck } from '../k1IndexCrossCheck'

describe('useK1IndexCrossCheck', () => {
  it('flags K1-1 vs K1-2 mismatch', () => {
    const map = ref(new Map<string, any>([
      ['K1-1-audited-receivable', { remark: '1000' }],
      ['K1-2-end-subtotal', { remark: '900' }],
    ]))
    const { alerts } = useK1IndexCrossCheck(map)
    expect(alerts.value.some((a) => a.id === 'adj-vs-detail')).toBe(true)
  })

  it('flags K1-3 vs K1-8 bad debt mismatch', () => {
    const map = ref(new Map<string, any>([
      ['K1-3-bad-debt-end', { remark: '500' }],
      ['K1-8-calc-provision-total', { remark: '400' }],
    ]))
    const { alerts } = useK1IndexCrossCheck(map)
    expect(alerts.value.some((a) => a.id === 'k13-vs-k18')).toBe(true)
  })

  it('counts open alerts excluding info severity', () => {
    const map = ref(new Map<string, any>([
      ['K1-1-audited-receivable', { remark: '1000' }],
      ['K1-2-end-subtotal', { remark: '900' }],
    ]))
    const { openCount } = useK1IndexCrossCheck(map)
    expect(openCount.value).toBeGreaterThan(0)
  })
})
