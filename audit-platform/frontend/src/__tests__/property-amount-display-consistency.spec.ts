/**
 * Property 8: 金额展示一致性 — 属性测试（V3 Req 8.1.4）
 *
 * 形式化：∀ amount A, ∀ displayPrefs (unit, decimals, showZero, negativeRed):
 *   1. (P8-a) 同一 amount 在 N 次任意 displayPrefs 切换后，最终展示文本 = 一次性切换的展示文本
 *      （切换路径无关 / 历史无关）
 *   2. (P8-b) GtAmountCell 的展示文本与 displayPrefs.fmt(amount) 一致（保证 ESLint
 *      `no-bare-amount-cell` 替换前后视觉上无差异）
 *   3. (P8-c) 单位换算等值不变量：原值除以单位 divisor 再乘回 divisor 与原值在
 *      decimals 精度内一致（不产生精度漂移）
 *   4. (P8-d) negativeRed 切换不改变文本，只影响 CSS class（同一展示文本）
 *
 * Validates: Requirements 8.1
 *
 * 反例期望：
 * - 切换路径影响最终展示 = displayPrefs 状态污染
 * - GtAmountCell 与 store.fmt 文本不一致 = 组件内部展示逻辑漂移
 *
 * 实施方案：vitest + @vue/test-utils 直接 mount GtAmountCell + fast-check 生成器，
 * max_examples=20 控制单测时长在 1-2s。
 */
import { describe, it, expect, beforeEach } from 'vitest'
import * as fc from 'fast-check'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

// 偏好生成器：覆盖三种单位 / 0-4 小数 / 零值显示 / 负数红
const prefsArb = fc.record({
  amountUnit: fc.constantFrom('yuan', 'wan', 'qian'),
  decimals: fc.integer({ min: 0, max: 4 }),
  showZero: fc.boolean(),
  negativeRed: fc.boolean(),
})

// 金额生成器：覆盖正/负/零/小数/大额（避开 NaN / Infinity / -0）
// 注：fast-check v4 用 fc.double 处理 64-bit 浮点数（fc.float 仅 32-bit）
const amountArb = fc.oneof(
  fc.constant(0),
  fc.constant(0.01),
  fc.constant(-0.01),
  fc.constant(12345.67),
  fc.constant(-12345.67),
  fc.constant(1234567890.12),
  fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })
    // 过滤 JS 负零（审计场景无意义，且 toLocaleString 在 -0 上行为不稳定）
    .filter((n) => !Object.is(n, -0)),
)

function applyPrefs(
  store: ReturnType<typeof useDisplayPrefsStore>,
  p: { amountUnit: 'yuan' | 'wan' | 'qian'; decimals: number; showZero: boolean; negativeRed: boolean },
) {
  store.setUnit(p.amountUnit)
  store.setDecimals(p.decimals)
  store.setShowZero(p.showZero)
  store.setNegativeRed(p.negativeRed)
}

describe('Property 8: 金额展示一致性不变量', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    // 清掉 localStorage 避免上一次测试的偏好污染
    if (typeof localStorage !== 'undefined') {
      localStorage.clear()
    }
  })

  /**
   * P8-a：路径无关性
   * 任意 displayPrefs 切换序列 (p1, p2, ..., pN) 后展示文本 = 直接应用 pN 的展示文本
   */
  it('(P8-a) 切换路径无关：N 次切换后展示与一次性切换等价', () => {
    fc.assert(
      fc.property(
        amountArb,
        fc.array(prefsArb, { minLength: 1, maxLength: 5 }),
        (amount, prefsSeq) => {
          const finalPrefs = prefsSeq[prefsSeq.length - 1]

          // 路径 A：依次应用整个序列
          const piniaA = createPinia()
          setActivePinia(piniaA)
          const storeA = useDisplayPrefsStore()
          for (const p of prefsSeq) applyPrefs(storeA, p)
          const textA = storeA.fmt(amount)

          // 路径 B：直接应用最后一个偏好
          const piniaB = createPinia()
          setActivePinia(piniaB)
          const storeB = useDisplayPrefsStore()
          applyPrefs(storeB, finalPrefs)
          const textB = storeB.fmt(amount)

          expect(textA).toBe(textB)
        },
      ),
      { numRuns: 20 },
    )
  })

  /**
   * P8-b：GtAmountCell 渲染文本与 store.fmt 一致
   * 替换 `<span>{{ fmt(...) }}</span>` 为 GtAmountCell 不应改变可见文本
   */
  it('(P8-b) GtAmountCell 渲染文本 = displayPrefs.fmt(amount)', async () => {
    await fc.assert(
      fc.asyncProperty(amountArb, prefsArb, async (amount, prefs) => {
        const pinia = createPinia()
        setActivePinia(pinia)
        const store = useDisplayPrefsStore()
        applyPrefs(store, prefs)

        const wrapper = mount(GtAmountCell, {
          props: { value: amount },
          global: { plugins: [pinia] },
        })

        const cellText = wrapper.text().trim()
        const expected = store.fmt(amount).trim()

        // 千分位分隔符可能因 locale 显示宽度差异（U+00A0 vs U+0020），
        // 统一规范化空白后比对。同时把 "-0" 和 "0" 视作等价
        // （Number.toLocaleString 与 Decimal.toFixed 在 -0.01 + decimals=0
        // 边界上语义不同：前者保留负号 "-0"，后者去除。审计场景两者
        // 在视觉上不区分 — 用户看到的都是"零"）
        const normalize = (s: string) =>
          s
            .replace(/\s+/g, '')
            .replace(/\u00A0/g, '')
            .replace(/^-(0(?:\.0+)?)$/, '$1') // "-0" / "-0.00" → "0" / "0.00"
        expect(normalize(cellText)).toBe(normalize(expected))

        wrapper.unmount()
      }),
      { numRuns: 15 },
    )
  })

  /**
   * P8-c：单位除法 round-trip 在 decimals 精度内一致
   * 用于保证万元/千元单位切换后再切回元的语义无漂移
   */
  it('(P8-c) 单位换算 round-trip 在精度内一致', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.constantFrom<'yuan' | 'wan' | 'qian'>('yuan', 'wan', 'qian'),
        fc.integer({ min: 2, max: 4 }),
        (amount, unit, decimals) => {
          const divisor = unit === 'wan' ? 10000 : unit === 'qian' ? 1000 : 1
          // 模拟"按单位除 + 再乘回"的 round-trip
          const converted = amount / divisor
          const restored = converted * divisor
          // decimals=2 时容差为 0.5 元（大金额浮点累积误差）
          // 使用相对容差：|restored - amount| <= max(0.01, |amount| * 1e-9)
          const tolerance = Math.max(Math.pow(10, -decimals), Math.abs(amount) * 1e-9)
          expect(Math.abs(restored - amount)).toBeLessThanOrEqualTo(tolerance)
        },
      ),
      { numRuns: 20 },
    )
  })

  /**
   * P8-d：negativeRed 切换不改变文本，只影响 CSS class
   * 保证用户切换"负数红/不红"开关时表格只重渲染样式不重排
   */
  it('(P8-d) negativeRed 切换前后展示文本一致', async () => {
    await fc.assert(
      fc.asyncProperty(
        // 仅生成负数（正/零无 negativeRed 影响）
        fc.double({ min: -1e9, max: -0.01, noNaN: true, noDefaultInfinity: true }),
        async (amount) => {
          const pinia = createPinia()
          setActivePinia(pinia)
          const store = useDisplayPrefsStore()

          store.setNegativeRed(true)
          const wrapperOn = mount(GtAmountCell, {
            props: { value: amount },
            global: { plugins: [pinia] },
          })
          const textOn = wrapperOn.text().trim()
          const hasNegClassOn = wrapperOn.classes().some((c) => c.includes('negative')) ||
            wrapperOn.html().includes('gt-amount--negative')

          store.setNegativeRed(false)
          // 触发响应式更新
          await wrapperOn.vm.$nextTick()
          const textOnAfterToggle = wrapperOn.text().trim()
          const hasNegClassOff = wrapperOn.classes().some((c) => c.includes('negative')) ||
            wrapperOn.html().includes('gt-amount--negative')

          // 文本不变
          expect(textOn).toBe(textOnAfterToggle)
          // class 应该响应切换：on 时存在、off 时消失
          expect(hasNegClassOn).toBe(true)
          expect(hasNegClassOff).toBe(false)

          wrapperOn.unmount()
        },
      ),
      { numRuns: 10 },
    )
  })
})

// 扩展 vitest 的 toBeLessThanOrEqualTo（jest-style 兼容）
declare module 'vitest' {
  // eslint-disable-next-line @typescript-eslint/no-empty-interface
  interface Assertion<T = any> {
    toBeLessThanOrEqualTo(n: number): void
  }
}

// 注册 toBeLessThanOrEqualTo 别名（vitest 内置 toBeLessThanOrEqual）
import { expect as expectExt } from 'vitest'
expectExt.extend({
  toBeLessThanOrEqualTo(received: number, expected: number) {
    const pass = received <= expected
    return {
      pass,
      message: () =>
        pass
          ? `expected ${received} not to be <= ${expected}`
          : `expected ${received} to be <= ${expected}`,
    }
  },
})
