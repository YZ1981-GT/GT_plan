/**
 * Property-Based Tests for AI Context & Generate Flow
 *
 * Feature: platform-global-hardening, Property 11, Property 12
 * Requirements: 9.1, 9.2, 9.5, 9.6
 *
 * Uses vitest + fast-check with { numRuns: 100 }
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import * as fc from 'fast-check'
import { buildAiContext } from '../buildAiContext'
import { useAiGenerateFlow } from '../useAiGenerateFlow'

// ─── Generators ─────────────────────────────────────────────────────────────────

/** Valid wpCode patterns: D2, F3A, K10-6, E1, G5-9, H7, etc. */
const arbWpCode = fc.tuple(
  fc.constantFrom('A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N'),
  fc.integer({ min: 1, max: 15 }),
  fc.option(fc.oneof(
    fc.integer({ min: 1, max: 9 }).map(n => `-${n}`),
    fc.constantFrom('A', 'B', 'C').map(s => s),
  ), { nil: undefined }),
).map(([prefix, num, suffix]) => `${prefix}${num}${suffix ?? ''}`)

/** Arbitrary sheet name (Chinese, English, or empty) */
const arbSheetName = fc.oneof(
  fc.constant(''),
  fc.constantFrom('账龄分析', '审定表', '明细表', '坏账计提', '减值测试', '期后回款'),
  fc.string({ minLength: 1, maxLength: 30 }),
)

/** Required keys that every AiContext must contain */
const REQUIRED_KEYS = ['wpCode', 'sheet', 'linkedData', 'auditedAmounts', 'agingData', 'anomalies', 'methodology', 'extra'] as const

// ─── Property 11: AiContext 工厂产出非空且含约定键集 ────────────────────────────
// Feature: platform-global-hardening, Property 11
// **Validates: Requirements 9.1, 9.2**

describe('Property 11: AiContext 工厂产出非空且含约定键集', () => {
  it('对任意 (wpCode, sheet)，buildAiContext 返回非空 context 含全部约定键', () => {
    fc.assert(
      fc.property(arbWpCode, arbSheetName, (wpCode, sheet) => {
        const ctx = buildAiContext(wpCode, sheet || undefined)

        // 返回值非空
        expect(ctx).not.toBeNull()
        expect(ctx).not.toBeUndefined()

        // 含全部约定键集
        for (const key of REQUIRED_KEYS) {
          expect(ctx).toHaveProperty(key)
        }

        // wpCode 正确回填
        expect(ctx.wpCode).toBe(wpCode)

        // sheet 正确回填（空时为空字符串）
        expect(ctx.sheet).toBe(sheet || '')

        // methodology 非空字符串
        expect(typeof ctx.methodology).toBe('string')
        expect(ctx.methodology.length).toBeGreaterThan(0)

        // linkedData 是对象
        expect(typeof ctx.linkedData).toBe('object')
        expect(ctx.linkedData).not.toBeNull()

        // auditedAmounts 是对象
        expect(typeof ctx.auditedAmounts).toBe('object')

        // agingData 是数组
        expect(Array.isArray(ctx.agingData)).toBe(true)

        // anomalies 是数组
        expect(Array.isArray(ctx.anomalies)).toBe(true)

        // extra 是对象
        expect(typeof ctx.extra).toBe('object')
      }),
      { numRuns: 100 },
    )
  })
})

// ─── Property 12: AI 确认前不覆盖已有内容 ────────────────────────────────────────
// Feature: platform-global-hardening, Property 12
// **Validates: Requirements 9.5, 9.6**

describe('Property 12: AI 确认前不覆盖已有内容', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('对任意已有内容 c0 与生成输出 g，确认前 targetModel 恒等于 c0；confirm 后变为 g', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 0, maxLength: 200 }),
        fc.string({ minLength: 1, maxLength: 200 }),
        async (c0, g) => {
          // Mock httpPost resolves with generated content g
          const mockHttpPost = vi.fn().mockResolvedValue({
            data: { data: { content: g } },
          })

          const wpId = ref('wp-test-001')
          const targetModel = ref(c0)

          const { phase, generate, confirm } = useAiGenerateFlow({
            wpId,
            targetModel,
            section: 'pbt-section',
            httpPost: mockHttpPost,
          })

          // Before generate: targetModel === c0
          expect(targetModel.value).toBe(c0)

          // Call generate
          await generate({ wpCode: 'D2', sheet: '测试' })

          // After generate (PREVIEWING phase): targetModel still === c0
          expect(targetModel.value).toBe(c0)
          expect(phase.value).toBe('PREVIEWING')

          // Call confirm: targetModel now changes to g
          confirm()
          expect(targetModel.value).toBe(g)
        },
      ),
      { numRuns: 100 },
    )
  })
})
