/**
 * Property 9: 穿透面包屑可逆性 — fast-check PBT
 * **Validates: Requirements 8.3**
 *
 * 形式化：∀ navigation chain v₁ → v₂ → ... → vₙ via usePenetrate:
 *   `Backspace pops to vₙ₋₁` AND `Click breadcrumb[i] returns to vᵢ`
 *
 * 测试策略：
 * - 随机生成 1-5 层穿透链路
 * - 不变量 1：push N 次后 pop N 次 = 回到空栈
 * - 不变量 2：stack.length 始终 ≤ MAX_STACK_DEPTH
 * - 不变量 3：jumpTo(i) 截断 stack 到 i 项
 * - 不变量 4：pop 返回最后 push 的 entry（LIFO）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as fc from 'fast-check'

// Mock vue-router
vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
  }),
  useRoute: () => ({
    fullPath: '/projects/1/trial-balance',
    params: { projectId: '1' },
    query: { year: '2025' },
    meta: { title: '试算表' },
  }),
}))

import { useNavigationStack, MAX_STACK_DEPTH, type NavigationEntry } from '@/composables/useNavigationStack'

// Arbitrary for generating random NavigationEntry
const navigationEntryArb = fc.record({
  source_view: fc.stringMatching(/^\/projects\/[a-z0-9]{1,8}\/[a-z-]{3,15}$/),
  label: fc.option(fc.constantFrom('试算表', '报表', '底稿', '明细账', '调整分录', '附注', '错报', '穿透查询', '辅助余额', '底稿编辑'), { nil: undefined }),
  direction: fc.option(fc.constantFrom('down' as const, 'up' as const), { nil: undefined }),
  scroll_position: fc.option(fc.nat(5000), { nil: undefined }),
}) as fc.Arbitrary<NavigationEntry>

// Generate 1-5 layer penetration chains
const penetrationChainArb = fc.array(navigationEntryArb, { minLength: 1, maxLength: 5 })

describe('Property 9: 穿透面包屑可逆性', () => {
  let navStack: ReturnType<typeof useNavigationStack>

  beforeEach(() => {
    navStack = useNavigationStack()
    navStack.clear()
  })

  it('不变量 1: push N 次后 pop N 次 = 回到空栈', () => {
    fc.assert(
      fc.property(penetrationChainArb, (chain) => {
        navStack.clear()
        // Push all entries
        for (const entry of chain) {
          navStack.push(entry)
        }
        expect(navStack.stack.value.length).toBe(chain.length)

        // Pop all entries
        for (let i = 0; i < chain.length; i++) {
          navStack.pop()
        }
        expect(navStack.stack.value.length).toBe(0)
        expect(navStack.canGoBack.value).toBe(false)
      }),
      { numRuns: 15 }
    )
  })

  it('不变量 2: stack.length 始终 ≤ MAX_STACK_DEPTH', () => {
    // Use larger chains to test overflow
    const largeChainArb = fc.array(navigationEntryArb, { minLength: 1, maxLength: 30 })

    fc.assert(
      fc.property(largeChainArb, (chain) => {
        navStack.clear()
        for (const entry of chain) {
          navStack.push(entry)
          expect(navStack.stack.value.length).toBeLessThanOrEqual(MAX_STACK_DEPTH)
        }
      }),
      { numRuns: 15 }
    )
  })

  it('不变量 3: jumpTo(i) 截断 stack 到 i 项', () => {
    fc.assert(
      fc.property(
        penetrationChainArb.filter(c => c.length >= 2),
        fc.nat(),
        (chain, rawIndex) => {
          navStack.clear()
          for (const entry of chain) {
            navStack.push(entry)
          }
          const jumpIndex = rawIndex % chain.length
          // jumpTo removes the entry at jumpIndex and everything after
          navStack.jumpTo(jumpIndex)
          expect(navStack.stack.value.length).toBe(jumpIndex)
        }
      ),
      { numRuns: 15 }
    )
  })

  it('不变量 4: pop 返回最后 push 的 entry（LIFO 顺序）', () => {
    fc.assert(
      fc.property(penetrationChainArb, (chain) => {
        navStack.clear()
        for (const entry of chain) {
          navStack.push(entry)
        }
        // Pop in reverse order should match push order reversed
        const reversed = [...chain].reverse()
        for (const expected of reversed) {
          const popped = navStack.pop()
          expect(popped?.source_view).toBe(expected.source_view)
          expect(popped?.direction).toBe(expected.direction)
        }
      }),
      { numRuns: 15 }
    )
  })
})
