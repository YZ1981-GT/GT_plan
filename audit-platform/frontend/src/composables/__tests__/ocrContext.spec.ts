/**
 * OCR 上下文拼接/截断 + AI context key — 集成契约测试
 *
 * Spec: .kiro/specs/c-control-test-popup-enhance/  Task 13.2
 *
 * 覆盖：
 * - Property 5: OCR 文本拼接与截断
 *     对任意 OCR 文本集合，总拼接长度 L：
 *       · L ≤ 3000 → 结果为以 '\n---\n' 连接的完整拼接
 *       · L > 3000 → 结果为拼接的前 3000 字符 + '…（已截断）'
 *     并且 OCR 文本并入 AI context 时使用固定 key '参考资料（OCR识别）'。
 *   **Validates: Requirements 4.4, 5.3**
 *
 * 被测真实代码（非替身）：
 *   @/composables/useOcrAttachmentCache 导出的 truncateOcrText / OCR_CONTEXT_KEY /
 *   MAX_OCR_CONTEXT_LENGTH。OcrAttachmentPicker.vue 与 GtCControlTest.vue 均复用之，
 *   故此契约与生产链路一致。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

import {
  truncateOcrText,
  OCR_CONTEXT_KEY,
  MAX_OCR_CONTEXT_LENGTH,
} from '@/composables/useOcrAttachmentCache'

const SUFFIX = '…（已截断）'

describe('OCR context key 契约', () => {
  it('OCR_CONTEXT_KEY 固定为「参考资料（OCR识别）」', () => {
    expect(OCR_CONTEXT_KEY).toBe('参考资料（OCR识别）')
  })

  it('MAX_OCR_CONTEXT_LENGTH 为 3000', () => {
    expect(MAX_OCR_CONTEXT_LENGTH).toBe(3000)
  })

  it('OCR 文本并入 context 时落在固定 key 下（模拟父组件装配）', () => {
    const context: Record<string, string> = { 控制点名称: '采购审批' }
    const ocrText = truncateOcrText(['凭证影像识别文本'])
    if (ocrText) context[OCR_CONTEXT_KEY] = ocrText

    expect(context['参考资料（OCR识别）']).toBe('凭证影像识别文本')
    expect(Object.keys(context)).toContain('参考资料（OCR识别）')
  })

  it('空 OCR 文本不写入 context（无附件/全失败等同未选择）', () => {
    const context: Record<string, string> = { 控制点名称: '采购审批' }
    const ocrText = truncateOcrText([])
    if (ocrText) context[OCR_CONTEXT_KEY] = ocrText

    expect(context['参考资料（OCR识别）']).toBeUndefined()
  })
})

describe('Property 5: OCR 文本拼接与截断 (truncateOcrText)', () => {
  // ── 代表性用例 ──
  it('单段短文本原样返回', () => {
    expect(truncateOcrText(['abc'])).toBe('abc')
  })

  it('多段文本以 \\n---\\n 连接', () => {
    expect(truncateOcrText(['a', 'b', 'c'])).toBe('a\n---\nb\n---\nc')
  })

  it('空数组返回空串', () => {
    expect(truncateOcrText([])).toBe('')
  })

  it('恰好 3000 字符不截断', () => {
    const s = 'x'.repeat(3000)
    const out = truncateOcrText([s])
    expect(out).toBe(s)
    expect(out.endsWith(SUFFIX)).toBe(false)
  })

  it('超过 3000 字符截断到前 3000 + 尾标记', () => {
    const s = 'y'.repeat(3500)
    const out = truncateOcrText([s])
    expect(out).toBe('y'.repeat(3000) + SUFFIX)
    expect(out.startsWith('y'.repeat(3000))).toBe(true)
    expect(out.endsWith(SUFFIX)).toBe(true)
  })

  // ── fast-check：对任意文本集合，截断契约恒成立 ──
  it('对任意 OCR 文本集合满足拼接/截断契约', () => {
    fc.assert(
      fc.property(fc.array(fc.string(), { minLength: 0, maxLength: 8 }), (texts) => {
        const joined = texts.join('\n---\n')
        const out = truncateOcrText(texts)
        if (joined.length <= MAX_OCR_CONTEXT_LENGTH) {
          // L ≤ 3000：完整拼接，无尾标记
          expect(out).toBe(joined)
        } else {
          // L > 3000：前 3000 字符 + 尾标记
          expect(out).toBe(joined.slice(0, MAX_OCR_CONTEXT_LENGTH) + SUFFIX)
          expect(out.slice(0, MAX_OCR_CONTEXT_LENGTH)).toBe(
            joined.slice(0, MAX_OCR_CONTEXT_LENGTH),
          )
          expect(out.endsWith(SUFFIX)).toBe(true)
        }
      }),
      { numRuns: 300 },
    )
  })

  // ── fast-check：构造超长输入，确保长路径被覆盖 ──
  it('对超长文本集合始终截断并附尾标记', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 500, maxLength: 1200 }), {
          minLength: 4,
          maxLength: 10,
        }),
        (texts) => {
          const joined = texts.join('\n---\n')
          fc.pre(joined.length > MAX_OCR_CONTEXT_LENGTH)
          const out = truncateOcrText(texts)
          expect(out.length).toBe(MAX_OCR_CONTEXT_LENGTH + SUFFIX.length)
          expect(out.endsWith(SUFFIX)).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })
})
