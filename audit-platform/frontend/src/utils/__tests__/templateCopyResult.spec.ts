import { describe, it, expect } from 'vitest'
import { summarizeTemplateCopy } from '../templateCopyResult'

describe('summarizeTemplateCopy（R3：全部跳过不再提示「复制完成」）', () => {
  it('全部复制成功 ⇒ success', () => {
    expect(summarizeTemplateCopy([{ status: 'copied' }, { status: 'copied' }]))
      .toEqual({ level: 'success', message: '已复制 2 份底稿' })
  })

  it('部分跳过 ⇒ warning 并写明计数', () => {
    expect(summarizeTemplateCopy([{ status: 'copied' }, { status: 'skipped' }]))
      .toEqual({ level: 'warning', message: '已复制 1 份底稿，跳过 1 份（原因见下表）' })
  })

  it('全部跳过 ⇒ warning「没有复制任何底稿」', () => {
    const s = summarizeTemplateCopy([{ status: 'skipped' }])
    expect(s.level).toBe('warning')
    expect(s.message).toBe('没有复制任何底稿：跳过 1 份（原因见下表）')
  })

  it('有失败且没有复制 ⇒ error', () => {
    expect(summarizeTemplateCopy([{ status: 'failed' }, { status: 'skipped' }]).level).toBe('error')
  })

  it('空回执 ⇒ warning', () => {
    expect(summarizeTemplateCopy([]).message).toBe('没有复制任何底稿：没有可复制的底稿（原因见下表）')
  })
})
