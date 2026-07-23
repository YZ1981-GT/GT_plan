import { describe, it, expect } from 'vitest'
import { applyK14NetsToK11 } from '../k1AdjK11Writeback'

function seedK11(map: Map<string, any>) {
  map.set('K1-1-receivable-count', { remark: '2' })
  map.set('K1-1-baddebt-count', { remark: '2' })
  for (let i = 0; i < 2; i++) {
    map.set(`K1-1-receivable-r${i}-unadj`, { remark: String((i + 1) * 1000) })
    map.set(`K1-1-baddebt-r${i}-unadj`, { remark: String((i + 1) * 200) })
    map.set(`K1-1-receivable-r${i}-aje`, { remark: '0' })
    map.set(`K1-1-baddebt-r${i}-aje`, { remark: '999' })
  }
}

describe('applyK14NetsToK11', () => {
  it('allocates both blocks when scope=all', () => {
    const map = new Map<string, any>()
    seedK11(map)
    map.set('K1-4-aje-net', { remark: '3000' })
    map.set('K1-4-bd-aje-net', { remark: '-300' })

    const res = applyK14NetsToK11(map, undefined, { scope: 'all' })
    expect(res.applied).toBe(true)
    expect(Number(map.get('K1-1-receivable-r0-aje')?.remark)).toBeCloseTo(1000, 2)
    expect(Number(map.get('K1-1-baddebt-r0-aje')?.remark)).toBeCloseTo(-100, 2)
  })

  it('only updates receivable when scope=receivable', () => {
    const map = new Map<string, any>()
    seedK11(map)
    map.set('K1-4-aje-net', { remark: '2000' })
    map.set('K1-4-bd-aje-net', { remark: '-500' })

    applyK14NetsToK11(map, undefined, { scope: 'receivable' })

    expect(Number(map.get('K1-1-receivable-r1-aje')?.remark)).toBeCloseTo(2000 / 3 * 2, 0)
    expect(Number(map.get('K1-1-baddebt-r0-aje')?.remark)).toBe(999)
  })

  it('only updates bad debt when scope=baddebt', () => {
    const map = new Map<string, any>()
    seedK11(map)
    map.set('K1-4-aje-net', { remark: '2000' })
    map.set('K1-4-bd-aje-net', { remark: '-400' })

    applyK14NetsToK11(map, undefined, { scope: 'baddebt' })

    expect(Number(map.get('K1-1-receivable-r0-aje')?.remark)).toBe(0)
    expect(Number(map.get('K1-1-baddebt-r1-aje')?.remark)).toBeCloseTo(-400 / 3 * 2, 0)
  })
})
