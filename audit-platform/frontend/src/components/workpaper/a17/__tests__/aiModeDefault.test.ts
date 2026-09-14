/**
 * Property 11: AI 模式默认值由内容状态决定
 *
 * Feature: a17-summary-enhancement
 * **Validates: Requirements 4.4**
 *
 * For any chapter state, the default generation mode SHALL be "generate" when
 * chapter content is empty (whitespace-only counts as empty) and "polish" when
 * chapter content contains non-whitespace characters.
 */

import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import { getDefaultAiMode } from '../aiModeDefault'

// ─── Generators ───

/** 生成纯空白内容（空字符串或仅含空白字符） */
const emptyContentArb = fc.oneof(
  fc.constant(''),
  fc.array(fc.constantFrom(' ', '\t', '\n', '\r'), { minLength: 0, maxLength: 50 })
    .map((chars) => chars.join('')),
)

/** 生成含有 HTML 标签但去标签后为空白的内容 */
const htmlEmptyContentArb = fc.tuple(
  fc.array(fc.constantFrom(' ', '\n'), { minLength: 0, maxLength: 5 }).map(a => a.join('')),
  fc.constantFrom('<p>', '<br>', '<div>', '<h3>', '<h4>', '<ul>', '<ol>'),
  fc.array(fc.constantFrom(' ', '\n'), { minLength: 0, maxLength: 5 }).map(a => a.join('')),
  fc.constantFrom('</p>', '<br/>', '</div>', '</h3>', '</h4>', '</ul>', '</ol>'),
  fc.array(fc.constantFrom(' ', '\n'), { minLength: 0, maxLength: 5 }).map(a => a.join('')),
).map(([ws1, open, ws2, close, ws3]) => `${ws1}${open}${ws2}${close}${ws3}`)

/** 生成含有实质内容的纯文本字符串（至少 1 个非空白字符） */
const nonEmptyTextArb = fc.string({ minLength: 1, maxLength: 100 })
  .filter((s) => s.replace(/<[^>]*>/g, '').trim().length > 0)

/** 生成含有实质内容的 HTML（标签包裹有意义文字） */
const htmlNonEmptyContentArb = fc.tuple(
  fc.constantFrom('<p>', '<h3>', '<h4>', '<li>', '<strong>', '<em>'),
  fc.string({ minLength: 1, maxLength: 50 }).filter(s => s.trim().length > 0 && !s.includes('<') && !s.includes('>')),
  fc.constantFrom('</p>', '</h3>', '</h4>', '</li>', '</strong>', '</em>'),
).map(([open, text, close]) => `${open}${text}${close}`)

// ─── Property Tests ───

describe('Property 11: AI 模式默认值由内容状态决定', () => {
  it('空字符串或纯空白 → generate', () => {
    fc.assert(
      fc.property(emptyContentArb, (content) => {
        expect(getDefaultAiMode(content)).toBe('generate')
      }),
      { numRuns: 100 }
    )
  })

  it('HTML 标签包裹空白（去标签后空） → generate', () => {
    fc.assert(
      fc.property(htmlEmptyContentArb, (content) => {
        expect(getDefaultAiMode(content)).toBe('generate')
      }),
      { numRuns: 100 }
    )
  })

  it('含实质非空白字符 → polish', () => {
    fc.assert(
      fc.property(nonEmptyTextArb, (content) => {
        expect(getDefaultAiMode(content)).toBe('polish')
      }),
      { numRuns: 100 }
    )
  })

  it('HTML 包裹实质文字 → polish', () => {
    fc.assert(
      fc.property(htmlNonEmptyContentArb, (content) => {
        expect(getDefaultAiMode(content)).toBe('polish')
      }),
      { numRuns: 100 }
    )
  })
})
