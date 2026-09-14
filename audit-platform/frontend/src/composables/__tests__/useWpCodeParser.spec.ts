/**
 * Property 4: wp_code 正则解析完备性
 *
 * For any text string containing embedded wp_code patterns (matching
 * [A-S]\d{1,2}(?:-\d{1,2})?(?:[A-Z])?), the parser SHALL extract ALL matching
 * patterns from the string, and for any text string containing NO such patterns,
 * the parser SHALL return an empty result set.
 *
 * **Validates: Requirements 2.1**
 *
 * Feature: a17-summary-enhancement, Property 4: wp_code 正则解析完备性
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { extractWpCodes } from '@/composables/useWpCodeParser'

// ─── 生成器 ──────────────────────────────────────────────────────────────────────

/** 生成合法的 wp_code（[A-S]\d{1,2}(?:-\d{1,2})?(?:[A-Z])?） */
const wpCodeArb = fc.tuple(
  fc.constantFrom(...'ABCDEFGHIJKLMNOPQRS'.split('')),
  fc.integer({ min: 1, max: 99 }),
  fc.option(fc.integer({ min: 1, max: 99 }), { nil: undefined }),
  fc.option(fc.constantFrom(...'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')), { nil: undefined }),
).map(([letter, num, subNum, suffix]) => {
  let code = `${letter}${num}`
  if (subNum !== undefined) code += `-${subNum}`
  if (suffix !== undefined) code += suffix
  return code
})

/** 不包含 wp_code 模式的安全分隔文本（不含 A-S 后跟数字的组合） */
const SAFE_CHARS = '这是一段中文描述，不含底稿编码。0123456789 test text!@#$%^&*()'.split('')
const safeTextArb = fc.array(fc.constantFrom(...SAFE_CHARS), { minLength: 1, maxLength: 30 })
  .map((chars) => chars.join(''))

/** 在文本中嵌入 N 个 wp_code 的混合文本 */
const textWithCodesArb = fc.tuple(
  fc.array(wpCodeArb, { minLength: 1, maxLength: 5 }),
  fc.array(safeTextArb, { minLength: 2, maxLength: 6 }),
).map(([codes, separators]) => {
  // 交替插入分隔文本和 wp_code
  let result = ''
  for (let i = 0; i < codes.length; i++) {
    result += (separators[i] || ' ') + ' ' + codes[i] + ' '
  }
  result += separators[separators.length - 1] || ''
  return { text: result, expectedCodes: codes }
})

/** 不含任何 wp_code 的文本 */
const NO_LETTER_CHARS = '这是纯中文文本，没有底稿编码。数字0123456789和符号!@#'.split('')
const textWithoutCodesArb = fc.array(fc.constantFrom(...NO_LETTER_CHARS), { minLength: 1, maxLength: 100 })
  .map((chars) => chars.join(''))
  .filter((s) => {
    // 确保不意外包含 wp_code 模式
    const matches = s.match(/[A-S]\d{1,2}(?:-\d{1,2})?(?:[A-Z])?/g)
    return !matches || matches.length === 0
  })

// ─── Property Tests ──────────────────────────────────────────────────────────

describe('useWpCodeParser — Property 4: wp_code 正则解析完备性', () => {
  it('P4-a: 包含 wp_code 的文本能提取出所有嵌入的 code', () => {
    fc.assert(
      fc.property(textWithCodesArb, ({ text, expectedCodes }) => {
        const result = extractWpCodes(text)
        // 每个嵌入的 wp_code 都应被提取到
        for (const code of expectedCodes) {
          expect(result).toContain(code)
        }
      }),
      { numRuns: 100 },
    )
  })

  it('P4-b: 不含 wp_code 的文本返回空数组', () => {
    fc.assert(
      fc.property(textWithoutCodesArb, (text) => {
        const result = extractWpCodes(text)
        expect(result).toHaveLength(0)
      }),
      { numRuns: 100 },
    )
  })

  it('P4-c: 提取结果中每个元素都匹配 wp_code 正则', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 0, maxLength: 200 }),
        (text) => {
          const result = extractWpCodes(text)
          const wpCodeRe = /^[A-S]\d{1,2}(?:-\d{1,2})?(?:[A-Z])?$/
          for (const code of result) {
            expect(code).toMatch(wpCodeRe)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('P4-d: 空输入返回空数组', () => {
    expect(extractWpCodes('')).toEqual([])
  })

  it('P4-e: 单个 wp_code 被正确提取', () => {
    fc.assert(
      fc.property(wpCodeArb, (code) => {
        const result = extractWpCodes(`参见 ${code} 底稿`)
        expect(result).toContain(code)
      }),
      { numRuns: 50 },
    )
  })
})
