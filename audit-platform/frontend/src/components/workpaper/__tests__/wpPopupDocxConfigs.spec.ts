/**
 * wpPopupDocxConfigs.spec.ts — docx 弹窗配置完整性测试
 */
import { describe, it, expect } from 'vitest'
import { DOCX_POPUP_CONFIGS, ALL_DOCX_POPUP_CONFIGS, DOCX_POPUP_WP_CODES, INLINE_POPUP_WP_CODES } from '../wpPopupDocxConfigs'

describe('wpPopupDocxConfigs', () => {
  it('包含全部 A 循环 docx 子底稿', () => {
    const expected = [
      'A8-1', 'A8-2', 'A9-1', 'A9-2', 'A10-1', 'A11-1', 'A12-1',
      'A16-1', 'A16-2', 'A16-3', 'A16-4', 'A16-5', 'A16-6', 'A16-7',
      'A17-1', 'A17-2-1', 'A17-3', 'A17-3-1', 'A17-4', 'A17-6',
      'A18-1', 'A18-2', 'A26-1', 'A26-2', 'A26-3', 'A26-4', 'A27-1',
    ]
    for (const code of expected) {
      expect(DOCX_POPUP_CONFIGS[code], `missing config for ${code}`).toBeDefined()
      expect(DOCX_POPUP_CONFIGS[code].templatePath).toContain('.docx')
    }
    // DOCX_POPUP_WP_CODES now includes both A + B class configs
    expect(DOCX_POPUP_WP_CODES.size).toBe(Object.keys(ALL_DOCX_POPUP_CONFIGS).length)
  })

  it('包含 B 循环 docx 子底稿', () => {
    const bExpected = [
      'B1-3', 'B1-4', 'B1-7', 'B2-1', 'B2-3', 'B2-6', 'B2-8', 'B2-11', 'B2-12',
      'B3-1', 'B5', 'B5-1', 'B5-2', 'B5-3', 'B5-4', 'B5-5', 'B5-6', 'B5-7', 'B5-8', 'B5-9',
      'B18-3-1', 'B18-3-2',
      'B23-1-2', 'B23-2-2', 'B23-3-2', 'B23-4-2', 'B23-5-2', 'B23-6-2', 'B23-7-2',
      'B23-8-2', 'B23-9-2', 'B23-10-2', 'B23-11-2', 'B23-12-2', 'B23-13-2', 'B23-14-2',
      'B30-3', 'B30-4', 'B30-5', 'B30-6', 'B30-7', 'B30-9', 'B30-10', 'B30-11',
      'B30-13', 'B30-14', 'B40-1', 'B40-2',
      'B60', 'B60-2-1', 'B60-2-2', 'B60-2-3', 'B60-3', 'B60A', 'B60B', 'B60C', 'B60D',
    ]
    for (const code of bExpected) {
      expect(ALL_DOCX_POPUP_CONFIGS[code], `missing B-class config for ${code}`).toBeDefined()
      expect(ALL_DOCX_POPUP_CONFIGS[code].templatePath).toContain('.docx')
      expect(INLINE_POPUP_WP_CODES.has(code), `${code} not in INLINE_POPUP`).toBe(true)
    }
  })

  it('INLINE_POPUP 包含专用弹窗和 docx 弹窗', () => {
    expect(INLINE_POPUP_WP_CODES.has('A1-11')).toBe(true)
    expect(INLINE_POPUP_WP_CODES.has('A8-1')).toBe(true)
    expect(INLINE_POPUP_WP_CODES.has('A17-3')).toBe(true)
    expect(INLINE_POPUP_WP_CODES.has('A27-1')).toBe(true)
    // B-class also in INLINE_POPUP
    expect(INLINE_POPUP_WP_CODES.has('B60')).toBe(true)
    expect(INLINE_POPUP_WP_CODES.has('B3-1')).toBe(true)
  })
})
