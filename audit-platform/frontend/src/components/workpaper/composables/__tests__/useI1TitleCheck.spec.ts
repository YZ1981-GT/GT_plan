/**
 * useI1TitleCheck / i1 title helpers — 对齐 Excel I1-8
 */
import { describe, it, expect } from 'vitest'
import {
  calcI1TitleNetBook,
  classifyI1TitleExpiry,
  normalizeI1TitleRow,
  validateI1TitlePrep,
  seedI1TitleFromDetail,
  buildI1TitleConclusionDraft,
  emptyI1TitleRow,
} from '../useI1TitleCheck'

describe('calcI1TitleNetBook', () => {
  it('净值 = 原值 − 摊销 − 减值（Excel J=G−H−I）', () => {
    expect(calcI1TitleNetBook(1000, 200, 50)).toBe(750)
    expect(calcI1TitleNetBook(0, 0, 0)).toBe(0)
  })
})

describe('classifyI1TitleExpiry', () => {
  it('无日期 / 已到期 / 临期 / 正常', () => {
    expect(classifyI1TitleExpiry('')).toBe('none')
    expect(classifyI1TitleExpiry('2020-01-01', new Date('2026-07-22'))).toBe('expired')
    expect(classifyI1TitleExpiry('2026-12-01', new Date('2026-07-22'))).toBe('near')
    expect(classifyI1TitleExpiry('2028-12-01', new Date('2026-07-22'))).toBe('ok')
  })
})

describe('normalizeI1TitleRow', () => {
  it('兼容旧 bookValue / validUntil / pledgeStatus', () => {
    const row = normalizeI1TitleRow({
      name: '专利A',
      bookValue: 800,
      validUntil: '2027-01-01',
      pledgeStatus: '质押',
    })
    expect(row.cost).toBe(800)
    expect(row.rightEndDate).toBe('2027-01-01')
    expect(row.mortgageRestricted).toBe('Y')
    expect(row.mortgageNature).toBe('质押')
    expect(row.netBookValue).toBe(800)
  })
})

describe('validateI1TitlePrep', () => {
  it('抵押受限缺价值时告警', () => {
    const row = emptyI1TitleRow({
      name: '土地A',
      certNo: 'X1',
      rightHolder: '甲公司',
      mortgageRestricted: 'Y',
      mortgageValue: 0,
    })
    const v = validateI1TitlePrep([row])
    expect(v.ok).toBe(false)
    expect(v.messages.some((m) => m.includes('抵押价值'))).toBe(true)
  })
})

describe('seedI1TitleFromDetail', () => {
  it('从 I1-2 字段映射账面三要素', () => {
    const rows = seedI1TitleFromDetail([
      { name: '软件B', costEnd: 1000, accAmortEnd: 100, impairmentEnd: 50, category: '软件著作权' },
    ])
    expect(rows).toHaveLength(1)
    expect(rows[0].cost).toBe(1000)
    expect(rows[0].accAmort).toBe(100)
    expect(rows[0].impairment).toBe(50)
    expect(rows[0].netBookValue).toBe(850)
    expect(rows[0].type).toBe('软件著作权')
  })
})

describe('buildI1TitleConclusionDraft', () => {
  it('汇总关键计数', () => {
    const text = buildI1TitleConclusionDraft([
      emptyI1TitleRow({ name: 'A', certNo: '1', holderConsistent: 'N' }),
      emptyI1TitleRow({
        name: 'B',
        mortgageRestricted: 'Y',
        mortgageValue: 100,
        rightEndDate: '2020-01-01',
      }),
    ])
    expect(text).toContain('不一致 1 项')
    expect(text).toContain('抵押/受限 1 项')
    expect(text).toContain('权利到期 1 项')
  })
})
