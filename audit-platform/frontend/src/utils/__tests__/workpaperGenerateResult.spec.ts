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

  it('因程序裁剪跳过 / 底稿在回收站：警告并分别列出（spec procedure-trim-generation-delegation-chain 需求 2）', () => {
    const n = summarizeWorkpaperGenerateResult({
      created: 1,
      skipped_trimmed_codes: ['H3', 'H3-1', 'M4A'],
      in_recycle_codes: ['E2'],
    })
    expect(n.level).toBe('warning')
    expect(n.message).toContain('3 个编码已在程序裁剪中标为不执行，未生成：H3、H3-1、M4A')
    expect(n.message).toContain('1 个编码的底稿在回收站中，请从回收站恢复：E2')
    expect(summarizeWorkpaperGenerateResult({ created: 2, skipped_trimmed_codes: [], in_recycle_codes: [] }).level)
      .toBe('success')
  })

  it('按编码生成回报表头未填上：警告并列出编码与原因（原先只记服务日志、界面照报生成完成）', () => {
    const n = summarizeWorkpaperGenerateResult({
      created: 3,
      header_failures: [
        { wp_code: 'J2A', reason: '打开底稿文件失败' },
        { wp_code: 'K11-4' },
      ],
    })
    expect(n.level).toBe('warning')
    expect(n.message).toContain('共创建 3 份底稿')
    expect(n.message).toContain('2 个底稿表头未填上：J2A（打开底稿文件失败）、K11-4')
    expect(summarizeWorkpaperGenerateResult({ created: 3, header_failures: [] })).toEqual({
      level: 'success',
      message: '底稿生成完成，共创建 3 份底稿',
    })
  })

  it('统一回执（spec procedure-chain-hardening-and-java-contracts R11）：已有底稿与请求内未填表头只作说明，失败带原因', () => {
    const info = summarizeWorkpaperGenerateResult({
      created: 2,
      existing_codes: ['E1', 'H1'],
      header_unfilled: 2,
    })
    expect(info.level).toBe('success')
    expect(info.message).toContain('2 个编码已有底稿，未重复生成：E1、H1')
    expect(info.message).toContain('2 份底稿生成时未写入表头（编制单位、审计期间等），需在底稿文件中另行填写')
    const failed = summarizeWorkpaperGenerateResult({
      created: 1,
      failures: [{ wp_code: 'A1', error: '模板文件被占用' }, { wp_code: 'B60A' }],
    })
    expect(failed.level).toBe('warning')
    expect(failed.message).toContain('2 个编码生成失败：A1（模板文件被占用）、B60A')
    expect(summarizeWorkpaperGenerateResult({ created: 1, header_unfilled: 0 }).message).not.toContain('表头')
  })
})
