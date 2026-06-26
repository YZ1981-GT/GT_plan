/**
 * Property 1: HTML 消毒保留安全标签并剥离危险标签
 *
 * For any arbitrary HTML string (including strings containing <script>, <iframe>,
 * on* event attributes, or other XSS vectors), after sanitization the output
 * SHALL NOT contain any <script>, <iframe>, <object>, <embed> tags or any on*
 * event handler attributes, while preserving safe tags (h3, h4, ul, ol, li,
 * table, tr, td, th, strong, em, br, p).
 *
 * **Validates: Requirements 1.3, 1.4**
 *
 * Feature: a17-summary-enhancement, Property 1: HTML 消毒保留安全标签并剥离危险标签
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { sanitizeHtml } from '@/composables/useSanitize'

// ─── 危险标签/属性检测正则 ────────────────────────────────────────────────────────

const DANGEROUS_TAG_RE = /<\s*(script|iframe|object|embed)\b/i
const ON_EVENT_ATTR_RE = /\bon\w+\s*=/i

// ─── 安全标签列表 ────────────────────────────────────────────────────────────────

const SAFE_TAGS = ['h3', 'h4', 'ul', 'ol', 'li', 'table', 'tr', 'td', 'th', 'strong', 'em', 'br', 'p']

// ─── 生成器 ──────────────────────────────────────────────────────────────────────

/** 随机安全标签 HTML 片段 */
const safeTagArb = fc.constantFrom(...SAFE_TAGS).map((tag) => {
  if (tag === 'br') return '<br>'
  return `<${tag}>content</${tag}>`
})

/** 随机危险标签 */
const dangerousTagArb = fc.constantFrom(
  '<script>alert("xss")</script>',
  '<iframe src="evil.com"></iframe>',
  '<object data="hack.swf"></object>',
  '<embed src="payload.swf">',
  '<img onerror="alert(1)" src="x">',
  '<div onclick="hack()">click</div>',
  '<a onmouseover="steal()">link</a>',
  '<p onload="exec()">text</p>',
)

/** 随机 on* 事件属性注入 */
const onEventArb = fc.constantFrom(
  'onclick="alert(1)"',
  'onmouseover="hack()"',
  'onerror="steal()"',
  'onload="exec()"',
  'onfocus="pwn()"',
)

/** 混合 HTML：安全标签 + 危险标签 + 随机文本 */
const mixedHtmlArb = fc.tuple(
  fc.array(safeTagArb, { minLength: 0, maxLength: 3 }),
  fc.array(dangerousTagArb, { minLength: 0, maxLength: 3 }),
  fc.string({ minLength: 0, maxLength: 50 }),
).map(([safeParts, dangerParts, text]) => {
  return [...safeParts, ...dangerParts, text].join(' ')
})

// ─── Property Tests ──────────────────────────────────────────────────────────

describe('useSanitize — Property 1: HTML 消毒保留安全标签并剥离危险标签', () => {
  it('P1-a: 输出不包含危险标签（script/iframe/object/embed）', () => {
    fc.assert(
      fc.property(mixedHtmlArb, (html) => {
        const result = sanitizeHtml(html)
        expect(result).not.toMatch(DANGEROUS_TAG_RE)
      }),
      { numRuns: 100 },
    )
  })

  it('P1-b: 输出不包含 on* 事件属性', () => {
    fc.assert(
      fc.property(
        fc.tuple(
          fc.constantFrom(...SAFE_TAGS.filter((t) => t !== 'br')),
          onEventArb,
          fc.string({ minLength: 1, maxLength: 20 }),
        ),
        ([tag, attr, content]) => {
          const html = `<${tag} ${attr}>${content}</${tag}>`
          const result = sanitizeHtml(html)
          expect(result).not.toMatch(ON_EVENT_ATTR_RE)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('P1-c: 安全标签被保留在输出中（仅结构合法的标签）', () => {
    // table 子元素（tr/td/th/thead/tbody）只在 table 上下文中合法
    // 单独测试非表格标签 + 完整表格结构
    const standaloneTagsArb = fc.constantFrom(
      ...SAFE_TAGS.filter((t) => !['tr', 'td', 'th'].includes(t)),
    )
    fc.assert(
      fc.property(standaloneTagsArb, (tag) => {
        let input: string
        if (tag === 'br') {
          input = '<br>'
        } else if (tag === 'table') {
          input = '<table><tr><td>cell</td></tr></table>'
        } else {
          input = `<${tag}>content</${tag}>`
        }
        const result = sanitizeHtml(input)
        expect(result).toContain(`<${tag}`)
      }),
      { numRuns: 100 },
    )
  })

  it('P1-c2: 表格子标签在完整 table 结构中被保留', () => {
    const input = '<table><tr><td>cell1</td><th>header</th></tr></table>'
    const result = sanitizeHtml(input)
    expect(result).toContain('<table>')
    expect(result).toContain('<tr>')
    expect(result).toContain('<td>')
    expect(result).toContain('<th>')
  })

  it('P1-d: 空输入返回空字符串', () => {
    expect(sanitizeHtml('')).toBe('')
  })

  it('P1-e: 纯文本不被修改', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 100 }).filter((s) => !s.includes('<') && !s.includes('>')),
        (text) => {
          const result = sanitizeHtml(text)
          expect(result).toBe(text)
        },
      ),
      { numRuns: 50 },
    )
  })
})
