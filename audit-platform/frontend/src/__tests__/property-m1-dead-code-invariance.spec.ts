/**
 * M1 / T3 属性测试 — Property 4: 死代码删除行为不变性
 *
 * 背景：frontend-consistency-m1 的 T3 删除了 `AMOUNT_DIVISOR_KEY`
 *   （`src/constants/amountDivisor.ts` 的 Symbol）+ GtAmountCell.vue 内
 *   `inject(AMOUNT_DIVISOR_KEY, 1)` 后的 no-op `_divisor` computed + LedgerPenetration.vue
 *   死 import。该 `_divisor` 是历史双重除法 bug 残骸，**从未参与** `formattedDisplay`
 *   或 `cssClass` 的计算（标 `eslint-disable @typescript-eslint/no-unused-vars`）。
 *
 *   由于"删除前"的代码已实际删除，无法做字面 before/after diff。本测试改为证明
 *   **使删除安全的不变量**：GtAmountCell 的 `formattedDisplay` 与 `cssClass`
 *   是 (value, displayPrefs, priorValue) 的纯函数，**不依赖任何被注入的 divisor 值**。
 *   既然注入是 no-op，移除它必然保留行为 → 等价于"删除前后输出一致"。
 *
 * Property 4 (Task 10.1): 死代码删除行为不变性
 *   ∀ 金额值 v，删除 AMOUNT_DIVISOR_KEY 相关 inject/_divisor 后，GtAmountCell 的
 *   `formattedDisplay` 与 `cssClass` 输出与删除前完全一致（因 _divisor 是 no-op）。
 *   **Validates: Requirements 6.5**
 *
 * 三条子断言：
 *   P4-a（inject 独立性）：以任意 `provide` 上下文（模拟被删 inject 本应读取的值）挂载，
 *     渲染文本 + 金额 CSS 类与"无 provide"挂载完全一致 → 证明注入是 no-op，移除保留行为。
 *   P4-b（formattedDisplay = 纯引用计算）：formattedDisplay 等于仅由 displayPrefs
 *     单位 divisor（1 / 10000 / 1000）派生的纯引用计算（Decimal 除法 + ROUND_HALF_UP +
 *     千分位），从不依赖任何注入 divisor；null/undefined/'' → '-'，0 + showZero=false → '-'。
 *   P4-c（cssClass 确定性）：相同 (value, priorValue, negativeRed, highlightThreshold)
 *     输入下 cssClass 输出确定，仅依赖这些输入（无被删 inject 残留的隐藏状态）；
 *     负数 + negativeRed=true → 含 'gt-amount--negative'。
 *
 * 实施方案：vitest + @vue/test-utils mount + fast-check（numRuns: 15）。
 */
import { describe, it, expect, beforeEach } from 'vitest'
import * as fc from 'fast-check'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import Decimal from 'decimal.js'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { AMOUNT_UNITS } from '@/utils/formatters'
import { toDecimal } from '@/utils/decimal'

// ── 纯引用计算：镜像 GtAmountCell 的 formattedDisplay 内部逻辑 ──────────────
// 仅依赖 (value, displayPrefs)，无任何 inject/divisor 注入参数。这正是 P4-b
// 要证明的"纯函数"形态——若组件输出 == 此引用计算，则证明显示只取决于
// displayPrefs 单位 divisor，与被删的 injectedDivisor 无关。

/** 安全 Decimal 化（镜像组件 safeDecimal）：非法/空值 → null */
function refSafeDecimal(v: unknown): Decimal | null {
  if (v === null || v === undefined) return null
  if (typeof v === 'string' && v.trim() === '') return null
  try {
    return toDecimal(v as any, false, '金额')
  } catch {
    return null
  }
}

/** 千分位格式化（镜像组件 formatWithSeparator） */
function refFormatWithSeparator(d: Decimal, decimals: number): string {
  const fixed = d.toFixed(decimals)
  const negative = fixed.startsWith('-')
  const absStr = negative ? fixed.slice(1) : fixed
  const [intPart, decPart] = absStr.split('.')
  const intWithSep = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  const body = decPart ? `${intWithSep}.${decPart}` : intWithSep
  return negative ? `-${body}` : body
}

/** 纯引用 formattedDisplay（镜像组件 computed，仅取决于 value + displayPrefs） */
function refFormattedDisplay(
  value: unknown,
  prefs: { amountUnit: 'yuan' | 'wan' | 'qian'; decimals: number; showZero: boolean },
): string {
  const d = refSafeDecimal(value)
  if (d === null) return '-'
  if (d.isZero() && !prefs.showZero) return '-'
  const unitCfg = AMOUNT_UNITS[prefs.amountUnit] ?? AMOUNT_UNITS.yuan
  const converted = d.dividedBy(unitCfg.divisor)
  const rounded = converted.toDecimalPlaces(prefs.decimals, Decimal.ROUND_HALF_UP)
  return refFormatWithSeparator(rounded, prefs.decimals)
}

// ── 工具：从渲染节点提取金额条件 CSS 类（gt-amount--*）────────────────────
// cssClass computed 只产出 'gt-amount--negative' / 'gt-amount--highlight'；
// 结构类（gt-amount-cell / gt-amount-cell--clickable）不属于行为不变量的比较范围。
function amountClasses(wrapper: ReturnType<typeof mount>): string[] {
  const span = wrapper.find('.gt-amount-cell')
  if (!span.exists()) return []
  return span
    .classes()
    .filter((c) => c.startsWith('gt-amount--'))
    .sort()
}

// ── 生成器 ──────────────────────────────────────────────────────────────
// 金额值：覆盖 number / 数值字符串 / null / undefined / 0 / 负数 / 大数（>1e9）
const numberArb = fc.oneof(
  fc.constant(0),
  fc.constant(0.01),
  fc.constant(-0.01),
  fc.constant(12345.67),
  fc.constant(-12345.67),
  fc.constant(1234567890.12),
  fc.constant(-9876543210.5),
  fc.double({ min: -1e12, max: 1e12, noNaN: true, noDefaultInfinity: true })
    .filter((n) => !Object.is(n, -0)),
)
const valueArb = fc.oneof(
  numberArb,
  numberArb.map((n) => String(n)),
  fc.constant(null),
  fc.constant(undefined),
  fc.constant(''),
)

// displayPrefs：三单位 / 0-4 小数 / 零值 / 负数红 / 变动阈值
const prefsArb = fc.record({
  amountUnit: fc.constantFrom<'yuan' | 'wan' | 'qian'>('yuan', 'wan', 'qian'),
  decimals: fc.integer({ min: 0, max: 4 }),
  showZero: fc.boolean(),
  negativeRed: fc.boolean(),
  highlightThreshold: fc.constantFrom(0, 0.1, 0.2, 0.5),
})

// 任意 provide 值：模拟被删 inject 本应读取的"divisor"（数字 / 函数 / 字符串）
const arbitraryDivisorArb = fc.oneof(
  fc.integer({ min: -1000, max: 1000 }),
  fc.double({ min: 0.001, max: 1e6, noNaN: true, noDefaultInfinity: true }),
  fc.constant(10000),
  fc.constant(1000),
  fc.constant(() => 10000),
  fc.constant(() => 0),
  fc.string(),
)

function applyPrefs(
  store: ReturnType<typeof useDisplayPrefsStore>,
  p: {
    amountUnit: 'yuan' | 'wan' | 'qian'
    decimals: number
    showZero: boolean
    negativeRed: boolean
    highlightThreshold: number
  },
) {
  store.setUnit(p.amountUnit)
  store.setDecimals(p.decimals)
  store.setShowZero(p.showZero)
  store.setNegativeRed(p.negativeRed)
  store.setHighlightThreshold(p.highlightThreshold)
}

describe('M1/T3 Property 4: 死代码删除行为不变性（AMOUNT_DIVISOR_KEY no-op 移除）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    if (typeof localStorage !== 'undefined') localStorage.clear()
  })

  /**
   * P4-a — inject 独立性
   * 以任意 provide 上下文挂载（含模拟"AMOUNT_DIVISOR_KEY" 的 Symbol / 字符串键 →
   * 任意 divisor 数字/函数），渲染文本 + 金额 CSS 类必须与"无 provide"挂载完全一致。
   * 由于 AMOUNT_DIVISOR_KEY 已删除，组件不再 inject 任何 divisor，故任何注入都不影响输出。
   * **Validates: Requirements 6.5**
   */
  it('(P4-a) 任意 provide 上下文下渲染文本 + 金额类与无 provide 完全一致', () => {
    fc.assert(
      fc.property(
        valueArb,
        prefsArb,
        fc.oneof(numberArb, fc.constant(null), fc.constant(undefined)),
        arbitraryDivisorArb,
        arbitraryDivisorArb,
        (value, prefs, priorValue, injA, injB) => {
          // 实例 A：无任何 provide
          const piniaA = createPinia()
          setActivePinia(piniaA)
          applyPrefs(useDisplayPrefsStore(), prefs)
          const wrapperA = mount(GtAmountCell, {
            props: { value: value as any, priorValue: priorValue as any },
            global: { plugins: [piniaA] },
          })
          const textA = wrapperA.text().trim()
          const classA = amountClasses(wrapperA)
          wrapperA.unmount()

          // 实例 B：provide 任意键（模拟被删的 AMOUNT_DIVISOR_KEY）→ 任意 divisor
          const piniaB = createPinia()
          setActivePinia(piniaB)
          applyPrefs(useDisplayPrefsStore(), prefs)
          const fakeDivisorKey = Symbol('AMOUNT_DIVISOR_KEY')
          const wrapperB = mount(GtAmountCell, {
            props: { value: value as any, priorValue: priorValue as any },
            global: {
              plugins: [piniaB],
              provide: {
                [fakeDivisorKey]: injA,
                amountDivisor: injB,
                AMOUNT_DIVISOR_KEY: injA,
                divisor: injB,
              },
            },
          })
          const textB = wrapperB.text().trim()
          const classB = amountClasses(wrapperB)
          wrapperB.unmount()

          expect(textB, `value=${String(value)} 注入后文本应不变`).toBe(textA)
          expect(classB, `value=${String(value)} 注入后金额类应不变`).toEqual(classA)
        },
      ),
      { numRuns: 15 },
    )
  })

  /**
   * P4-b — formattedDisplay = 纯引用计算
   * 组件渲染文本必须等于仅由 displayPrefs（单位 divisor + 小数 + 零值）派生的纯引用计算。
   * 证明显示只取决于 displayPrefs 单位 divisor（1/10000/1000），从不依赖被删的注入 divisor。
   * null/undefined/'' → '-'；0 + showZero=false → '-'。
   * **Validates: Requirements 6.5**
   */
  it('(P4-b) formattedDisplay 等于仅由 displayPrefs 派生的纯引用计算', () => {
    fc.assert(
      fc.property(valueArb, prefsArb, (value, prefs) => {
        const pinia = createPinia()
        setActivePinia(pinia)
        applyPrefs(useDisplayPrefsStore(), prefs)

        const wrapper = mount(GtAmountCell, {
          props: { value: value as any },
          global: { plugins: [pinia] },
        })
        const rendered = wrapper.text().trim()
        wrapper.unmount()

        const expected = refFormattedDisplay(value, {
          amountUnit: prefs.amountUnit,
          decimals: prefs.decimals,
          showZero: prefs.showZero,
        })
        expect(
          rendered,
          `value=${String(value)} unit=${prefs.amountUnit} dec=${prefs.decimals} showZero=${prefs.showZero}`,
        ).toBe(expected)
      }),
      { numRuns: 15 },
    )
  })

  /**
   * P4-c — cssClass 确定性
   * 相同 (value, priorValue, negativeRed, highlightThreshold) 输入下，重复挂载得到的
   * 金额 CSS 类集合必须完全一致（无被删 inject 残留的隐藏状态）；且负数 + negativeRed=true
   * 必含 'gt-amount--negative'。
   * **Validates: Requirements 6.5**
   */
  it('(P4-c) 相同输入下 cssClass 确定，负数+negativeRed 必含 gt-amount--negative', () => {
    const negNumberArb = fc.oneof(
      fc.constant(-0.01),
      fc.constant(-12345.67),
      fc.constant(-9876543210.5),
      fc.double({ min: -1e9, max: -0.001, noNaN: true, noDefaultInfinity: true }),
    )
    const cssValueArb = fc.oneof(numberArb, negNumberArb, numberArb.map((n) => String(n)))
    const priorArb = fc.oneof(
      numberArb,
      fc.constant(0),
      fc.constant(null),
      fc.constant(undefined),
    )

    fc.assert(
      fc.property(
        cssValueArb,
        priorArb,
        fc.boolean(),
        fc.constantFrom(0, 0.1, 0.2, 0.5),
        (value, priorValue, negativeRed, threshold) => {
          const mountOnce = () => {
            const pinia = createPinia()
            setActivePinia(pinia)
            const store = useDisplayPrefsStore()
            store.setNegativeRed(negativeRed)
            store.setHighlightThreshold(threshold)
            store.setShowZero(true)
            store.setDecimals(2)
            const w = mount(GtAmountCell, {
              props: { value: value as any, priorValue: priorValue as any },
              global: { plugins: [pinia] },
            })
            const cls = amountClasses(w)
            w.unmount()
            return cls
          }

          // 确定性：两次独立挂载产出相同金额类集合
          const first = mountOnce()
          const second = mountOnce()
          expect(second, `value=${String(value)} 重复挂载类应一致`).toEqual(first)

          // 负数 + negativeRed=true → 必含 gt-amount--negative
          const d = refSafeDecimal(value)
          if (d !== null && d.isNegative() && negativeRed) {
            expect(
              first,
              `负数 value=${String(value)} negativeRed=true 应含 gt-amount--negative`,
            ).toContain('gt-amount--negative')
          }
        },
      ),
      { numRuns: 15 },
    )
  })
})
