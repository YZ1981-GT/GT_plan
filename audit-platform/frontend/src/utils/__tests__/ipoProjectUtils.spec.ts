import { describe, it, expect } from 'vitest'
import { isIpoProject, IPO_BIZ_KEYWORDS } from '../ipoProjectUtils'

describe('isIpoProject', () => {
  it('returns true for each default keyword', () => {
    for (const kw of IPO_BIZ_KEYWORDS) {
      expect(isIpoProject(kw)).toBe(true)
    }
  })

  it('matches keyword as substring', () => {
    expect(isIpoProject('ipo_audit')).toBe(true)
    expect(isIpoProject('listed_company')).toBe(true)
    expect(isIpoProject('neeq_annual')).toBe(true)
    expect(isIpoProject('major_restructuring')).toBe(true)
    expect(isIpoProject('bond_refinancing')).toBe(true)
  })

  it('is case insensitive', () => {
    expect(isIpoProject('IPO')).toBe(true)
    expect(isIpoProject('Listed')).toBe(true)
    expect(isIpoProject('NEEQ')).toBe(true)
    expect(isIpoProject('RESTRUCTURING')).toBe(true)
  })

  it('returns false for empty string', () => {
    expect(isIpoProject('')).toBe(false)
  })

  it('returns false for non-matching string', () => {
    expect(isIpoProject('normal')).toBe(false)
    expect(isIpoProject('general_audit')).toBe(false)
    expect(isIpoProject('annual')).toBe(false)
  })

  it('supports D4 fraud_risk without changing base behavior', () => {
    const d4AllowedCats = [...IPO_BIZ_KEYWORDS, 'fraud_risk']
    expect(isIpoProject('fraud_risk_high', d4AllowedCats)).toBe(true)
    expect(isIpoProject('normal', d4AllowedCats)).toBe(false)
    expect(isIpoProject('', d4AllowedCats)).toBe(false)
    expect(isIpoProject('refinancing')).toBe(true)
    expect(isIpoProject('refinancing', ['fraud_risk'])).toBe(false)
  })

  it('uses allowedCats override when provided', () => {
    // 自定义关键词列表覆盖默认
    expect(isIpoProject('fraud_risk_high', ['fraud_risk'])).toBe(true)
    expect(isIpoProject('normal', ['fraud_risk'])).toBe(false)
  })

  it('allowedCats is case insensitive', () => {
    expect(isIpoProject('FRAUD_RISK', ['fraud_risk'])).toBe(true)
    expect(isIpoProject('fraud_risk', ['FRAUD_RISK'])).toBe(true)
  })

  it('empty allowedCats array falls back to defaults', () => {
    // 空数组 length=0 → 走默认路径
    expect(isIpoProject('ipo', [])).toBe(true)
    expect(isIpoProject('normal', [])).toBe(false)
  })
})

describe('isIpoProject — 后端 project_classification（R4）', () => {
  it('按适用性标签精确匹配，不做子串', () => {
    expect(isIpoProject({ tags: ['ipo'] })).toBe(true)
    expect(isIpoProject({ tags: ['neeq', 'restructuring'] })).toBe(true)
    expect(isIpoProject({ tags: [] })).toBe(false)
    expect(isIpoProject({ tags: ['fraud_risk'] })).toBe(false)
    expect(isIpoProject({ tags: ['ipo_extra'] })).toBe(false)
    expect(isIpoProject({ tags: null })).toBe(false)
    expect(isIpoProject({})).toBe(false)
  })

  it('allowedCats 同样对标签生效（D4 扩展 fraud_risk、A 程序表按模板声明）', () => {
    expect(isIpoProject({ tags: ['fraud_risk'] }, [...IPO_BIZ_KEYWORDS, 'fraud_risk'])).toBe(true)
    expect(isIpoProject({ tags: ['listed'] }, ['ipo'])).toBe(false)
    expect(isIpoProject({ tags: ['IPO'] }, ['ipo'])).toBe(true)
  })

  it('分类原值只剩质控分类码时不会被当成 IPO（迁移后分类列与场景已拆开）', () => {
    for (const code of ['A1', 'A2', 'B1', 'C']) {
      expect(isIpoProject(code)).toBe(false)
    }
    expect(isIpoProject(null)).toBe(false)
    expect(isIpoProject(undefined)).toBe(false)
  })
})
