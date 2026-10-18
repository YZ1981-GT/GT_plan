/**
 * 附注一致性闸门确认框正文 —— deliverable-writeback-and-online-edit-integrity（复盘修复）
 *
 * 确认框开了 dangerouslyUseHTMLString，章节标题 / 底稿编码来自库里的数据 ⇒ 必须转义后再拼 HTML。
 */
import { describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { buildNoteConsistencyMessage, escapeHtml } from '../noteConsistencyMessage'

function repoRoot(): string {
  let dir = resolve(__dirname)
  for (let i = 0; i < 12; i += 1) {
    if (existsSync(join(dir, 'backend', 'app', 'services', 'deliverable_capabilities.py'))) return dir
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error('未能定位仓库根（哨兵 backend/app/services/deliverable_capabilities.py 未找到）')
}

describe('escapeHtml', () => {
  it('转义 & < > " \'', () => {
    expect(escapeHtml(`<a href="x" title='y'>&</a>`)).toBe(
      '&lt;a href=&quot;x&quot; title=&#39;y&#39;&gt;&amp;&lt;/a&gt;',
    )
  })
})

describe('buildNoteConsistencyMessage', () => {
  const payload = '<img src=x onerror=alert(1)>'

  it('章节标题、章节号、底稿编码里的 HTML 都被转义，不会被当成标签', () => {
    const html = buildNoteConsistencyMessage({
      confirmed: false,
      never_synced: [{ note_section: '八、1', section_title: payload, wp_codes: ['E1', '<b>x</b>'] }],
      stale: [{ note_section: `九${payload}`, section_title: '' }],
    })
    expect(html).not.toContain('<img')
    expect(html).not.toContain('<b>x</b>')
    expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;')
    expect(html).toContain('&lt;b&gt;x&lt;/b&gt;')
  })

  it('两组各带章节数；没有标题时回落到章节号', () => {
    const html = buildNoteConsistencyMessage({
      confirmed: false,
      never_synced: [{ note_section: '八、1', section_title: '货币资金', wp_codes: ['E1'] }],
      stale: [
        { note_section: '八、5', section_title: '' },
        { note_section: '八、6', section_title: '' },
      ],
    })
    expect(html).toContain('从未从底稿同步（1 章）')
    expect(html).toContain('货币资金（底稿 E1）')
    expect(html).toContain('底稿已更新、附注陈旧（2 章）')
    expect(html).toContain('• 八、5')
  })

  it('空清单只有提示语，不出现分组标题', () => {
    const html = buildNoteConsistencyMessage(null)
    expect(html).not.toContain('从未从底稿同步')
    expect(html).not.toContain('附注陈旧')
    expect(html).toContain('仍要导出')
  })
})

describe('DeliverableCenter 接线', () => {
  it('确认框正文走 buildNoteConsistencyMessage，不再就地拼未转义的 HTML', () => {
    const src = readFileSync(join(repoRoot(), 'audit-platform/frontend/src/views/DeliverableCenter.vue'), 'utf-8')
    expect(src).toContain('buildNoteConsistencyMessage(res.consistency)')
    expect(src).not.toMatch(/\$\{it\.section_title/)
  })
})
