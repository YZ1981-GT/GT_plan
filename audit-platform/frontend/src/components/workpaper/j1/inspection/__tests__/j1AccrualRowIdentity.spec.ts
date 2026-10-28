import { describe, expect, it } from 'vitest'
import {
  bindShortTermTemplateIds,
  calculateAccrualAmounts,
  isExpectedTemplateRowId,
  roundHalfAwayFromZero2,
  SHORT_TERM_SKELETON_ROWS,
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
    expect(ids.every((id, i) => isExpectedTemplateRowId(id, i))).toBe(true)
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

  it('已是逐位置正确的模板身份时原样返回（幂等）', () => {
    const rows = Array.from({ length: 19 }, (_, i) => ({ id: shortTermTemplateRowId(i) }))
    expect(bindShortTermTemplateIds(rows, 19)).toBe(rows)
    expect(bindShortTermTemplateIds(bindShortTermTemplateIds(rows, 19), 19)).toBe(rows)
  })

  it('错 namespace、错行号和错序都重新绑定，业务值不动', () => {
    const rows = Array.from({ length: 19 }, (_, i) => ({ id: shortTermTemplateRowId(i), value: i }))
    rows[0].id = 'GTROW-OTHER-0017'
    rows[1].id = 'GTROW-J16S-0099'
    ;[rows[2].id, rows[3].id] = [rows[3].id, rows[2].id]
    const bound = bindShortTermTemplateIds(rows, 19)
    expect(bound.map(r => r.id)).toEqual(Array.from({ length: 19 }, (_, i) => shortTermTemplateRowId(i)))
    expect(bound.map(r => r.value)).toEqual(Array.from({ length: 19 }, (_, i) => i))
  })
})

describe('前端骨架与模板金额语义', () => {
  it('标签保留全角分隔符、缩进和单元格换行原字节', () => {
    expect(SHORT_TERM_SKELETON_ROWS).toHaveLength(19)
    expect(SHORT_TERM_SKELETON_ROWS[1].label).toBe('其中：1．工资')
    expect(SHORT_TERM_SKELETON_ROWS[2].label).toBe('　　　2．奖金')
    expect(SHORT_TERM_SKELETON_ROWS[15].label).toBe('八、辞退福利\n（因解除劳动关系给予的补偿）')
  })

  it('差异方向严格为应提减实际（G-H），覆盖正负零', () => {
    expect(calculateAccrualAmounts(1000, 0.1, 80)).toEqual({ estimated: 100, diff: 20 })
    expect(calculateAccrualAmounts(1000, 0.1, 120)).toEqual({ estimated: 100, diff: -20 })
    expect(calculateAccrualAmounts(1000, 0.1, 100)).toEqual({ estimated: 100, diff: 0 })
  })
})
