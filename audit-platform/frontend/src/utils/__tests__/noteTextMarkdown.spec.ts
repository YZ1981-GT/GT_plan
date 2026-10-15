/**
 * 附注正文加载口径 —— 与后端 test_note_text_markdown_parity.py 逐条跑同一份共享夹具（第 22 组）。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { isHtmlNoteText, renderNoteMarkdown, renderNoteTextToHtml } from '../noteTextMarkdown'

interface DetectCase { text: string; is_html: boolean; note: string }
interface RenderCase { text: string; expected: string; note: string }

const CASES_PATH = resolve(__dirname, '../../../../../backend/data/note_text_markdown_cases.json')
const FIXTURE = JSON.parse(readFileSync(CASES_PATH, 'utf-8'))
const DETECT: DetectCase[] = FIXTURE.detect_cases
const RENDER: RenderCase[] = FIXTURE.render_cases

describe('是否按 HTML 对待（共享夹具）', () => {
  it('夹具非空转：两类判定都有', () => {
    expect(new Set(DETECT.map((c) => c.is_html))).toEqual(new Set([true, false]))
  })

  it.each(DETECT.map((c) => [c.note, c] as const))('%s', (_note, c) => {
    expect(isHtmlNoteText(c.text)).toBe(c.is_html)
  })
})

describe('纯文字按 markdown 渲染（共享夹具，与后端逐字一致）', () => {
  it('夹具非空转：表格 / 段内换行 / 分段都有', () => {
    const expected = RENDER.map((c) => c.expected)
    expect(new Set(expected).size).toBe(expected.length)
    expect(expected.some((e) => e.includes('<table>'))).toBe(true)
    expect(expected.some((e) => e.includes('<br />'))).toBe(true)
    expect(expected.some((e) => (e.match(/<p>/g) ?? []).length >= 2)).toBe(true)
  })

  it.each(RENDER.map((c) => [c.note, c] as const))('%s', (_note, c) => {
    expect(renderNoteMarkdown(c.text)).toBe(c.expected)
  })
})

describe('renderNoteTextToHtml（编辑器加载）', () => {
  it('空值与纯空白返回空串', () => {
    expect(renderNoteTextToHtml(null)).toBe('')
    expect(renderNoteTextToHtml(undefined)).toBe('')
    expect(renderNoteTextToHtml('  \n ')).toBe('')
  })

  it('已是 HTML 不二次转换（幂等）', () => {
    const html = '<p>1. 第一项</p><p>前言<br>第二行</p><table><tbody><tr><td>1</td></tr></tbody></table>'
    expect(renderNoteTextToHtml(html)).toBe(html)
    expect(renderNoteTextToHtml(renderNoteTextToHtml('第一行\n第二行'))).toBe(renderNoteTextToHtml('第一行\n第二行'))
  })

  it('已是 HTML 也消毒（富文本框以 innerHTML 显示，首版靠隐藏 TipTap 编辑器顺带清洗）', () => {
    const html = renderNoteTextToHtml('<p onclick="alert(1)">正文</p><img src="x" onerror="alert(1)"><script>alert(1)</script>')
    expect(html).not.toMatch(/onclick|onerror|<script/)
    expect(html).toContain('<p>正文</p>')
  })

  it('书写的编号原样、同段换行，不成列表', () => {
    const html = renderNoteTextToHtml('说明如下：\n1. 第一项\n2. 第二项\n\n1. 丙\n2. 丁')
    expect(html).not.toMatch(/<(ol|ul|li)\b/)
    const div = document.createElement('div')
    div.innerHTML = html
    const paragraphs = div.querySelectorAll('p')
    expect(paragraphs.length).toBe(2)
    expect(paragraphs[0].querySelectorAll('br').length).toBe(2)
    expect(div.textContent).toBe('说明如下：1. 第一项2. 第二项1. 丙2. 丁')
  })

  it('以中文尖括号开头的纯文字按文字渲染（首版以「<」开头即当 HTML，换行被并掉）', () => {
    const html = renderNoteTextToHtml('<公司名称>的会计政策\n第二行')
    expect(html).toBe('<p>&lt;公司名称&gt;的会计政策<br>第二行</p>')
  })

  it('markdown 表格渲染成表格，尖括号与危险链接不成标签', () => {
    const html = renderNoteTextToHtml('| 项目 | 金额 |\n| --- | --- |\n| 甲 | 1 |\n\n<img src=x onerror=alert(1)> [点我](javascript:alert(1))')
    expect(html).toContain('<table>')
    expect(html).not.toContain('<img')
    expect(html).toContain('&lt;img')
    // markdown-it 拒绝 javascript: 链接，原样按文字显示
    expect(html).not.toMatch(/<a\b/)
    expect(html).toContain('[点我](javascript:alert(1))')
  })
})

describe('附注编辑器只用这一份加载口径', () => {
  it('DisclosureEditor 从 utils/noteTextMarkdown 引入，不再自带 marked 渲染', () => {
    const src = readFileSync(resolve(__dirname, '../../views/DisclosureEditor.vue'), 'utf-8')
    expect(src).toMatch(/import\s*\{\s*renderNoteTextToHtml\s*\}\s*from\s*'@\/utils\/noteTextMarkdown'/)
    expect(src).not.toMatch(/from\s*'marked'/)
    expect(src).not.toMatch(/function\s+renderNoteTextToHtml\b/)
    expect(src).toContain('renderNoteTextToHtml(currentNote.value.text_content)')
  })
})
