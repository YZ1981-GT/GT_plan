import { describe, expect, it } from 'vitest'
import {
  buildCrossRefRules,
  buildCrossWorkpaperNavDefs,
  exampleConfirmIndex,
  getCycleConfirmationMeta,
  resolveConfirmationCycle,
} from '../cycleConfirmationMeta'

describe('cycleConfirmationMeta', () => {
  it('resolves cycle from sheet codes', () => {
    expect(resolveConfirmationCycle('F0-5')).toBe('F0')
    expect(resolveConfirmationCycle('H0-1')).toBe('H0')
    expect(resolveConfirmationCycle('G0-6')).toBe('G0')
    expect(resolveConfirmationCycle(undefined)).toBe('D0')
  })

  it('F0 meta uses F0 sheet codes', () => {
    const m = getCycleConfirmationMeta('F0-1')
    expect(m.summaryCode).toBe('F0-1')
    expect(m.altPrimaryCode).toBe('F0-5')
    expect(m.altSecondaryCode).toBe('F0-6')
    expect(m.reliabilityCode).toBe('F0-7')
  })

  it('H0 shifts reliability/fraud sheet numbers', () => {
    const m = getCycleConfirmationMeta('H0-5')
    expect(m.altPrimaryCode).toBe('H0-5')
    expect(m.reliabilityCode).toBe('H0-6')
    expect(m.fraudCode).toBe('H0-7')
  })

  it('crossRefRules replace D0 hardcoding', () => {
    const rules = buildCrossRefRules('F0-1')
    expect(rules.some(r => r.target.includes('F0-4'))).toBe(true)
    expect(rules.some(r => r.target.includes('F0-5'))).toBe(true)
    expect(rules.every(r => !r.target.includes('D0-'))).toBe(true)
  })

  it('nav defs follow cycle', () => {
    const defs = buildCrossWorkpaperNavDefs('K0-1')
    expect(defs.map(d => d.wpCode)).toContain('K0-1')
    expect(defs.map(d => d.wpCode)).toContain('K0-5/K0-6')
  })

  it('E0 meta uses real sheet meanings (followup=E0-7)', () => {
    const m = getCycleConfirmationMeta('E0-1')
    expect(m.summaryCode).toBe('E0-1')
    expect(m.entityVerifyCode).toBe('E0-2')
    expect(m.followupCode).toBe('E0-7')
    expect(m.fraudCode).toBe('E0-8')
  })

  it('E0 has no independent diff/reliability/alternative sheet (null, not D0-mirrored)', () => {
    const m = getCycleConfirmationMeta('E0-1')
    expect(m.diffCode).toBeNull()
    expect(m.reliabilityCode).toBeNull()
    expect(m.diffChecklistCode).toBeNull()
    expect(m.altPrimaryCode).toBeNull()
    expect(m.altSecondaryCode).toBeNull()
  })

  it('E0 nav/rules omit non-existent diff/reliability/alternative entries', () => {
    const defs = buildCrossWorkpaperNavDefs('E0-1')
    // 不应生成指向 E0-7 的"差异调节表/回函可靠性验证"或不存在的"替代程序"错误入口
    expect(defs.some(d => d.tooltip === '差异调节表')).toBe(false)
    expect(defs.some(d => d.tooltip === '回函可靠性验证')).toBe(false)
    expect(defs.some(d => d.tooltip === '替代程序')).toBe(false)
    const rules = buildCrossRefRules('E0-1')
    expect(rules.some(r => r.field === '差异金额')).toBe(false)
    expect(rules.some(r => r.field === '回函可靠性')).toBe(false)
    expect(rules.some(r => r.field === '替代确认')).toBe(false)
  })

  it('G0 models securities diff专表 (G0-3S) in meta/nav/rules', () => {
    const m = getCycleConfirmationMeta('G0-1')
    expect(m.diffSecuritiesCode).toBe('G0-3S')
    const defs = buildCrossWorkpaperNavDefs('G0-1')
    expect(defs.map(d => d.wpCode)).toContain('G0-3S')
    const rules = buildCrossRefRules('G0-1')
    expect(rules.some(r => r.field === '证券差异')).toBe(true)
  })
})
