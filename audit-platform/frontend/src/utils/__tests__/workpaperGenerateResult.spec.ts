/**
 * 生成底稿回执提示（spec formula-fetch-and-wp-generation-defect-closure R4 / R5）。
 */
import { describe, expect, it } from 'vitest'

import { summarizeWorkpaperGenerateResult } from '../workpaperGenerateResult'

describe('summarizeWorkpaperGenerateResult', () => {
  it('全部生成：成功提示，created 为 0 时不回退 count', () => {
    expect(summarizeWorkpaperGenerateResult({ created: 3, count: 3, ignored_codes: [] })).toEqual({
      level: 'success',
      message: '底稿生成完成，共创建 3 份底稿',
    })
    expect(summarizeWorkpaperGenerateResult({ created: 0, count: 9 }).message).toContain('共创建 0 份')
    expect(summarizeWorkpaperGenerateResult({ count: 4 }).message).toContain('共创建 4 份')
    expect(summarizeWorkpaperGenerateResult(undefined).message).toContain('共创建 0 份')
  })

  it('模板集生成回报未生成的编码：警告并列出', () => {
    const n = summarizeWorkpaperGenerateResult({ created: 2, ignored_codes: ['ZZ1', 'ZZ2'] })
    expect(n.level).toBe('warning')
    expect(n.message).toContain('2 个选中的编码不在所选模板集里，未生成：ZZ1、ZZ2')
  })

  it('按编码生成回报空白底稿与失败：警告并分别列出，超过 10 个截断', () => {
    const blank = Array.from({ length: 12 }, (_, i) => `B${i + 1}`)
    const n = summarizeWorkpaperGenerateResult({
      created: 13,
      blank_codes: blank,
      failures: [{ wp_code: 'H1', error: 'x' }],
    })
    expect(n.level).toBe('warning')
    expect(n.message).toContain('12 个编码没有找到底稿模板，已建空白底稿：B1、B2')
    expect(n.message).toContain('B10 等')
    expect(n.message).not.toContain('B11')
    expect(n.message).toContain('1 个编码生成失败：H1')
  })
})
