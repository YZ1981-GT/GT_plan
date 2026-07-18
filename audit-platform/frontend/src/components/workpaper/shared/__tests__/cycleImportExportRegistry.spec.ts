/**
 * cycleImportExportRegistry — F2 监盘 f2-st 与后端 _F2_ST_SPECS 对齐
 */
import { describe, it, expect } from 'vitest'
import { CYCLE_IMPORT_EXPORT } from '../cycleImportExportRegistry'

describe('cycleImportExportRegistry f2-st', () => {
  it('f2-st 包含 F2-24/25/26 及双表变体', () => {
    const entry = CYCLE_IMPORT_EXPORT['f2-st']
    expect(entry.apiPrefix).toBe('f2-st')
    expect([...entry.sheets]).toEqual(['F2-24', 'F2-24-count', 'F2-25', 'F2-25-floor', 'F2-26', 'F2-26-after'])
  })

  it('f2-st 不包含 F2-21', () => {
    expect(CYCLE_IMPORT_EXPORT['f2-st'].sheets).not.toContain('F2-21')
  })

  it('f2 main 不包含监盘 sheet', () => {
    const main = CYCLE_IMPORT_EXPORT.f2.sheets
    for (const code of ['F2-21', 'F2-22', 'F2-23', 'F2-24', 'F2-25', 'F2-26']) {
      expect(main).not.toContain(code)
    }
  })
})

describe('cycleImportExportRegistry f4', () => {
  it('f4 F4-7 对齐后端五段 sheet 名', () => {
    const sheets = CYCLE_IMPORT_EXPORT.f4.sheets
    expect(sheets).toContain('F4-7-payment-window')
    expect(sheets).toContain('F4-7-estimated-inbound')
    expect(sheets).toContain('F4-7-unprocessed-invoice')
    expect(sheets).toContain('F4-7-subsequent-payment')
    expect(sheets).toContain('F4-7-subsequent-increase')
    expect(sheets).not.toContain('F4-7-purchase')
    expect(sheets).not.toContain('F4-7-inbound')
    expect(sheets).not.toContain('F4-7-invoice')
  })
})

describe('cycleImportExportRegistry f5', () => {
  it('f5 sheets 与后端 _F5_SPECS 对齐', () => {
    expect([...CYCLE_IMPORT_EXPORT.f5.sheets]).toEqual([
      'F5-2', 'F5-3', 'F5-4', 'F5-5', 'F5-6', 'F5-8',
    ])
    expect(CYCLE_IMPORT_EXPORT.f5.apiPrefix).toBe('f5')
  })
})
