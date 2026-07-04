/**
 * cycleImportExportRegistry — F2 监盘 f2-st 与后端 _F2_ST_SPECS 对齐
 */
import { describe, it, expect } from 'vitest'
import { CYCLE_IMPORT_EXPORT } from '../cycleImportExportRegistry'

describe('cycleImportExportRegistry f2-st', () => {
  it('f2-st 仅包含 F2-24/25/26（F2-21 文本问卷无 Excel round-trip）', () => {
    const entry = CYCLE_IMPORT_EXPORT['f2-st']
    expect(entry.apiPrefix).toBe('f2-st')
    expect([...entry.sheets]).toEqual(['F2-24', 'F2-25', 'F2-26'])
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
