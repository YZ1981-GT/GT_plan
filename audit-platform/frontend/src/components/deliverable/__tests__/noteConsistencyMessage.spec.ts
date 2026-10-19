/**
 * 附注一致性闸门确认框正文 —— deliverable-writeback-and-online-edit-integrity（复盘修复）
 *
 * 确认框开了 dangerouslyUseHTMLString，章节标题 / 底稿编码来自库里的数据 ⇒ 必须转义后再拼 HTML。
 */
import { describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { buildNoteConsistencyMessage, escapeHtml, notesInconsistencyFromError } from '../noteConsistencyMessage'

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

/** 剥行注释与块注释（源码级断言只看代码，注释里的字样不算） */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

function readSrc(rel: string): string {
  return readFileSync(join(repoRoot(), rel), 'utf-8')
}

/** 取函数体：从 `async function <name>(` 到下一个顶层 `function` / `async function` */
function functionBody(src: string, name: string): string {
  const start = src.indexOf(`async function ${name}(`)
  expect(start, `未找到 ${name}`).toBeGreaterThan(-1)
  const rest = src.slice(start + 1)
  const next = rest.search(/\n(?:async )?function /)
  return next === -1 ? rest : rest.slice(0, next)
}

describe('notesInconsistencyFromError（一键全套闸门的 409）', () => {
  const item = { note_section: '八、1', section_title: '货币资金', wp_codes: ['E1'] }

  it('409 notes_inconsistent（拦截器已回填 detail）⇒ 待确认清单', () => {
    const err = { response: { status: 409, data: { detail: { code: 'notes_inconsistent', never_synced: [item], stale: [] } } } }
    expect(notesInconsistencyFromError(err)).toEqual({ confirmed: false, never_synced: [item], stale: [] })
  })

  it('detail 缺失时读 message（全局处理器原始形状）', () => {
    const err = { response: { status: 409, data: { message: { code: 'notes_inconsistent', never_synced: [], stale: [item] } } } }
    expect(notesInconsistencyFromError(err)?.stale).toEqual([item])
  })

  it('其他 409、其他状态、非对象 detail、空错误 ⇒ null（交给原有错误提示）', () => {
    expect(notesInconsistencyFromError({ response: { status: 409, data: { detail: { code: 'snapshot_changed' } } } })).toBeNull()
    expect(notesInconsistencyFromError({ response: { status: 409, data: { detail: '数据冲突' } } })).toBeNull()
    expect(notesInconsistencyFromError({ response: { status: 500, data: { detail: { code: 'notes_inconsistent' } } } })).toBeNull()
    expect(notesInconsistencyFromError(null)).toBeNull()
  })
})

describe('DeliverableCenter：一键全套接闸门 + 附注预检去重', () => {
  const CENTER = stripComments(readSrc('audit-platform/frontend/src/views/DeliverableCenter.vue'))
  const API = stripComments(readSrc('audit-platform/frontend/src/services/deliverableApi.ts'))

  it('一键全套命中闸门弹确认框，确认后带 confirm_inconsistent=true 重发', () => {
    const run = functionBody(CENTER, 'runGenerateFull')
    expect(run).toContain('buildNoteConsistencyMessage(pending)')
    expect(run).toContain('await startFullDeliverables(true)')
    const start = functionBody(CENTER, 'startFullDeliverables')
    expect(start).toMatch(/confirm_inconsistent:\s*confirmInconsistent/)
    expect(start).toContain('notesInconsistencyFromError(e)')
  })

  it('一键全套请求静默全局拦截器（否则 409 先弹通用提示，5xx 重跑整套）', () => {
    const fn = API.slice(API.indexOf('export async function createFullDeliverables('))
    expect(fn.slice(0, fn.indexOf('\n}'))).toContain('_silent: true')
  })

  it('附注预检只保留校验错误 / 无数据，未同步与过期交给导出闸门', () => {
    const fn = functionBody(CENTER, 'onNotesSelectionConfirm')
    expect(fn).toContain('s.error_sections')
    expect(fn).toContain('s.empty')
    expect(fn).not.toContain('s.never_synced')
    expect(fn).not.toContain('s.stale')
  })
})
