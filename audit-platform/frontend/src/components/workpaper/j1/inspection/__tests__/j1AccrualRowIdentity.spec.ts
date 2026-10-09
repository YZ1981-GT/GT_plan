import { describe, expect, it } from 'vitest'
import {
  bindShortTermTemplateIds,
  isTemplateRowId,
  roundHalfAwayFromZero2,
  shortTermTemplateRowId,
} from '../j1AccrualRowIdentity'

describe('应提金额与模板 ROUND(D*F,2) 同口径', () => {
  it('四舍五入远离零，且修正二进制误差', () => {
    expect(roundHalfAwayFromZero2(1.005)).toBe(1.01)
    expect(roundHalfAwayFromZero2(-1.005)).toBe(-1.01)
    expect(roundHalfAwayFromZero2(101234.5 * 0.02)).toBe(2024.69)
    expect(roundHalfAwayFromZero2(2.344)).toBe(2.34)
    expect(roundHalfAwayFromZero2(Number.NaN)).toBe(0)
  })
})

describe('J1-6 短期薪酬区行身份 = 模板行身份', () => {
  it('骨架第 0 / 18 行对应模板 R17 / R35', () => {
    expect(shortTermTemplateRowId(0)).toBe('GTROW-J16S-0017')
    expect(shortTermTemplateRowId(18)).toBe('GTROW-J16S-0035')
  })

  it('19 个身份互不相同且全是模板身份', () => {
    const ids = Array.from({ length: 19 }, (_, i) => shortTermTemplateRowId(i))
    expect(new Set(ids).size).toBe(19)
    expect(ids.every(isTemplateRowId)).toBe(true)
  })

  it('非法下标拒绝', () => {
    expect(() => shortTermTemplateRowId(-1)).toThrow(RangeError)
    expect(() => shortTermTemplateRowId(1.5)).toThrow(RangeError)
  })

  it('历史 acr-* 载荷（恰 19 行）一次性换绑，业务值不动', () => {
    const legacy = Array.from({ length: 19 }, (_, i) => ({ id: `acr-1700000000000-${i}-abc`, actual: i * 10 }))
    const bound = bindShortTermTemplateIds(legacy, 19)
    expect(bound.map(r => r.id)).toEqual(Array.from({ length: 19 }, (_, i) => shortTermTemplateRowId(i)))
    expect(bound.map(r => r.actual)).toEqual(legacy.map(r => r.actual))
    expect(legacy[0].id).toBe('acr-1700000000000-0-abc') // 不改入参
  })

  it('行数不等于骨架行数时原样返回（不猜）', () => {
    const odd = Array.from({ length: 18 }, (_, i) => ({ id: `acr-${i}` }))
    expect(bindShortTermTemplateIds(odd, 19)).toBe(odd)
  })

  it('已是模板身份时原样返回（幂等）', () => {
    const rows = Array.from({ length: 19 }, (_, i) => ({ id: shortTermTemplateRowId(i) }))
    expect(bindShortTermTemplateIds(rows, 19)).toBe(rows)
    expect(bindShortTermTemplateIds(bindShortTermTemplateIds(rows, 19), 19)).toBe(rows)
  })
})
