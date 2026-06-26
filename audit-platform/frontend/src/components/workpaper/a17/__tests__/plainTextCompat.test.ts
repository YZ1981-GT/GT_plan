/**
 * Property 2: 纯文本兼容渲染保留换行
 *
 * Feature: a17-summary-enhancement
 * **Validates: Requirements 1.5**
 *
 * For any plain-text string (containing no HTML tags, only \n line breaks),
 * the legacy content renderer SHALL produce output where every \n is converted
 * to a <br> tag, and the original text content is fully preserved (no characters
 * lost or added beyond the <br> insertions).
 */

import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import { plainTextToHtml } from '../plainTextCompat'

// ─── Generators ───

/**
 * 生成不含换行和 HTML 标签字符的文本行
 * 使用 fc.string + filter 排除 < 和 > 字符
 */
const textLineArb = fc.string({ minLength: 0, maxLength: 50 })
  .map((s) => s.replace(/[<>]/g, '').replace(/\n/g, ''))

/**
 * 生成由 \n 分隔的多行纯文本
 */
const multiLineTextArb = fc.array(textLineArb, { minLength: 1, maxLength: 10 })
  .map((lines) => lines.join('\n'))

// ─── Property Tests ───

describe('Property 2: 纯文本兼容渲染保留换行', () => {
  it('每个 \\n 被转为 <br>，原始文本内容完整保留', () => {
    fc.assert(
      fc.property(
        multiLineTextArb,
        (text) => {
          const result = plainTextToHtml(text)

          // 计算原始换行数
          const newlineCount = (text.match(/\n/g) || []).length

          // 结果中的 <br> 数量应等于原始换行数
          const brCount = (result.match(/<br>/g) || []).length
          expect(brCount).toBe(newlineCount)

          // 去除 <br> 后应还原为原始文本（去除 \n 后）
          const restored = result.replace(/<br>/g, '')
          const original = text.replace(/\n/g, '')
          expect(restored).toBe(original)
        }
      ),
      { numRuns: 100 }
    )
  })

  it('已含 HTML 标签的内容不做转换（原样返回）', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(
          '<p>hello</p>',
          '<h3>title</h3>\ncontent',
          '<ul><li>item</li></ul>',
          '<strong>bold</strong> text\nmore',
        ),
        (htmlContent) => {
          const result = plainTextToHtml(htmlContent)
          // 含 HTML 标签时原样返回，不做 \n → <br> 转换
          expect(result).toBe(htmlContent)
        }
      ),
      { numRuns: 20 }
    )
  })

  it('空字符串返回空字符串', () => {
    expect(plainTextToHtml('')).toBe('')
  })
})
