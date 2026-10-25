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
