import { describe, it, expect } from 'vitest'
import { getF2CutoffSamplingParams, F2_INVENTORY_ACCOUNT_CODES } from '../../f2/inspection/f2CutoffSheetConfigs'

describe('f2CutoffSheetConfigs', () => {
  it('inventory accounts cover 1401~1411', () => {
    expect(F2_INVENTORY_ACCOUNT_CODES).toContain('1401')
    expect(F2_INVENTORY_ACCOUNT_CODES).toContain('1411')
    expect(F2_INVENTORY_ACCOUNT_CODES).not.toContain('1412')
  })

  it('F2-29 inbound forward → post_cutoff + debit', () => {
    const p = getF2CutoffSamplingParams({
      sheetCode: 'F2-29', title: '', direction: 'inbound', testType: 'forward',
    })
    expect(p.cutoffDirection).toBe('post_cutoff')
    expect(p.directionFilter).toBe('debit')
  })

  it('F2-31 outbound forward → post_cutoff + credit', () => {
    const p = getF2CutoffSamplingParams({
      sheetCode: 'F2-31', title: '', direction: 'outbound', testType: 'forward',
    })
    expect(p.cutoffDirection).toBe('post_cutoff')
    expect(p.directionFilter).toBe('credit')
  })

  it('F2-30 inbound backward → pre_cutoff', () => {
    const p = getF2CutoffSamplingParams({
      sheetCode: 'F2-30', title: '', direction: 'inbound', testType: 'backward',
    })
    expect(p.cutoffDirection).toBe('pre_cutoff')
  })
})
