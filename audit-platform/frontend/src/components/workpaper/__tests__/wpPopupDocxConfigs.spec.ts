/**
 * wpPopupDocxConfigs.spec.ts — docx 弹窗配置完整性测试
 */
import { describe, it, expect } from 'vitest'
import { DOCX_POPUP_CONFIGS, DOCX_POPUP_WP_CODES, INLINE_POPUP_WP_CODES } from '../wpPopupDocxConfigs'

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
    expect(DOCX_POPUP_WP_CODES.size).toBe(Object.keys(DOCX_POPUP_CONFIGS).length)
  })

  it('INLINE_POPUP 包含专用弹窗和 docx 弹窗', () => {
    expect(INLINE_POPUP_WP_CODES.has('A1-11')).toBe(true)
    expect(INLINE_POPUP_WP_CODES.has('A8-1')).toBe(true)
    expect(INLINE_POPUP_WP_CODES.has('A17-3')).toBe(true)
    expect(INLINE_POPUP_WP_CODES.has('A27-1')).toBe(true)
  })
})
