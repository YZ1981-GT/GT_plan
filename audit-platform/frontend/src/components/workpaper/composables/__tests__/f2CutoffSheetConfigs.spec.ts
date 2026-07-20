import { describe, it, expect } from 'vitest'
import {
  getF2CutoffSamplingParams,
  getF2CutoffAccountCodes,
  F2_INVENTORY_ACCOUNT_CODES,
  F2_CUTOFF_CONFIGS,
} from '../../f2/inspection/f2CutoffSheetConfigs'

describe('f2CutoffSheetConfigs', () => {
  it('inventory accounts cover 1401~1411 (exclude 1412 price-diff / 1471 impairment)', () => {
    expect(F2_INVENTORY_ACCOUNT_CODES).toContain('1401')
    expect(F2_INVENTORY_ACCOUNT_CODES).toContain('1411')
    expect(F2_INVENTORY_ACCOUNT_CODES).not.toContain('1412')
    expect(F2_INVENTORY_ACCOUNT_CODES).not.toContain('1471')
  })

  it('titles cover 原材料/产成品 and dual directions', () => {
    expect(F2_CUTOFF_CONFIGS['F2-29'].fullTitle).toContain('原材料/产成品')
    expect(F2_CUTOFF_CONFIGS['F2-29'].fullTitle).toContain('记账凭证至原始凭证')
    expect(F2_CUTOFF_CONFIGS['F2-30'].fullTitle).toContain('原始凭证至记账凭证')
    expect(F2_CUTOFF_CONFIGS['F2-31'].primaryDocLabel).toContain('出库单')
    expect(F2_CUTOFF_CONFIGS['F2-32'].showInspect).toBe(false)
    expect(F2_CUTOFF_CONFIGS['F2-29'].showInspect).toBe(true)
  })

  it('category account codes split raw vs finished', () => {
    expect(getF2CutoffAccountCodes('raw')).toContain('1403')
    expect(getF2CutoffAccountCodes('finished')).toContain('1405')
    expect(getF2CutoffAccountCodes('')).toBe(F2_INVENTORY_ACCOUNT_CODES)
  })

  it('F2-29 inbound voucher→source → post_cutoff + debit', () => {
    const p = getF2CutoffSamplingParams(F2_CUTOFF_CONFIGS['F2-29'])
    expect(p.cutoffDirection).toBe('post_cutoff')
    expect(p.directionFilter).toBe('debit')
  })

  it('F2-31 outbound voucher→source → post_cutoff + credit', () => {
    const p = getF2CutoffSamplingParams(F2_CUTOFF_CONFIGS['F2-31'])
    expect(p.cutoffDirection).toBe('post_cutoff')
    expect(p.directionFilter).toBe('credit')
  })

  it('F2-30 inbound source→voucher → pre_cutoff', () => {
    const p = getF2CutoffSamplingParams(F2_CUTOFF_CONFIGS['F2-30'])
    expect(p.cutoffDirection).toBe('pre_cutoff')
  })
})
