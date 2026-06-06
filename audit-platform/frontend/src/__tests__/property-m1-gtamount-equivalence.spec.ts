/**
 * M1 / T1 属性测试 — GtAmountCell 替换金额等价性 + 单位切换单调联动
 *
 * 背景：frontend-consistency-m1 的 T1 把六大核心数据页的裸金额渲染
 *   `{{ fmt(value) }}`（= displayPrefs.fmt → fmtAmountUnit，Number 路径）
 * 替换为 `<GtAmountCell :value="value" />`（Decimal.js 路径）。本测试证明
 * 该替换满足两条 M1 正确性属性，且不与既有
 * `property-amount-display-consistency.spec.ts`（P8 V3，做精确字符串比对）重复 —
 * 本文件聚焦"数值等价"而非"字符串逐字一致"，因为两条路径在极端精度 /
 * 半进位边界（-0 vs 0、float vs Decimal ROUND_HALF_UP）上可能有格式差异，
 * 但必须表示同一数值。
 *
 * Property 1 (Task 4.1): GtAmountCell 替换金额等价性
 *   ∀ 合法金额 v（number/string/null/undefined/负数/0/大数），∀ displayPrefs，
 *   GtAmountCell 渲染值与 displayPrefs.fmt(v) 表示同一数值（单位换算 + 小数位 +
 *   千分位规则一致，允许格式呈现差异但数值相等）。
 *   **Validates: Requirements 2.7**
 *
 * Property 2 (Task 4.2): 金额单位切换单调联动
 *   ∀ 单位切换序列 ∈ {yuan, wan, qian}，所有已挂载的 GtAmountCell 实例的
 *   显示值都同步按对应 divisor 换算（yuan ÷1 / wan ÷10000 / qian ÷1000），
 *   不存在"切换后某实例不变"的情况。
 *   **Validates: Requirements 2.5**
 *
 * 实施方案：vitest + @vue/test-utils mount + fast-check（numRuns: 15）。
 */
import { describe, it, expect, beforeEach } from 'vitest'
import * as fc from 'fast-check'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { AMOUNT_UNITS } from '@/utils/formatters'

// ── 工具：把展示文本解析回数值 ───────────────────────────────
// GtAmountCell 用手写千分位（','），displayPrefs.fmt 用 toLocaleString
// （locale 下可能是 ',' 或不间断空格 U+00A0）。统一剥离分隔符后 Number()。
// 空值占位 '-' → null；-0 在调用处用 Object.is 归一为 0。
function parseDisplayed(s: string): number | null {
  const t = s.replace(/\u00A0/g, '').replace(/[\s,]/g, '').trim()
  if (t === '' || t === '-') return null
  const n = Number(t)
  return Number.isNaN(n) ? null : n
}

// -0 视作 0（审计场景两者视觉等价）
function normZero(n: number): number {
  return Object.is(n, -0) ? 0 : n
}

// 偏好生成器：三单位 / 0-4 小数 / 零值显示 / 负数红
const prefsArb = fc.record({
  amountUnit: fc.constantFrom<'yuan' | 'wan' | 'qian'>('yuan', 'wan', 'qian'),
  decimals: fc.integer({ min: 0, max: 4 }),
  showZero: fc.boolean(),
  negativeRed: fc.boolean(),
})

// 金额数值生成器：覆盖 0 / 小数 / 负数 / 大数（1e9+）；避开 NaN/Infinity/-0
const numberArb = fc.oneof(
  fc.constant(0),
  fc.constant(-0.01),
  fc.constant(0.01),
  fc.constant(12345.67),
  fc.constant(-12345.67),
  fc.constant(1234567890.12), // 大数 > 1e9
  fc.constant(-9876543210.5),
  fc.double({ min: -1e12, max: 1e12, noNaN: true, noDefaultInfinity: true })
    .filter((n) => !Object.is(n, -0)),
)

// T1 替换的列既有 number（row.x）也有 string；故数值串也要覆盖。
// 仅生成"非空数值字符串"——空串 / 纯空白在 showZero=true 下两路径语义不同
// （fmt → "0.00" vs GtAmountCell → '-'），不属于本等价性属性的断言范围。
const numericStringArb = numberArb.map((n) => String(n))

// Property 1 的金额生成器：number / 数值串 / null / undefined
const valueArb = fc.oneof(
  numberArb,
  numericStringArb,
  fc.constant(null),
  fc.constant(undefined),
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

describe('M1/T1 Property 1+2: GtAmountCell 替换等价性 & 单位联动', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    if (typeof localStorage !== 'undefined') {
      localStorage.clear()
    }
  })

  /**
   * Property 1 (Task 4.1) — 替换金额等价性
   * 断言相同 displayPrefs 下 GtAmountCell 渲染数值 == displayPrefs.fmt 数值。
   * 容差 = 末位一个单位（10^-decimals，吸收 float vs Decimal 半进位差异）
   *        ⊕ 相对容差（|value|*1e-9，吸收大数 float 精度退化）。
   * **Validates: Requirements 2.7**
   */
  it('(P1) GtAmountCell 渲染数值 ≈ displayPrefs.fmt 数值（number/string/null/负数/0/大数）', async () => {
    await fc.assert(
      fc.asyncProperty(valueArb, prefsArb, async (value, prefs) => {
        const pinia = createPinia()
        setActivePinia(pinia)
        const store = useDisplayPrefsStore()
        applyPrefs(store, prefs)

        const wrapper = mount(GtAmountCell, {
          props: { value: value as number | string | null | undefined },
          global: { plugins: [pinia] },
        })

        const cellNum = parseDisplayed(wrapper.text().trim())
        const fmtNum = parseDisplayed(store.fmt(value).trim())
        wrapper.unmount()

        // 两路径都判定为"无值"（'-'）→ 等价，通过
        if (cellNum === null && fmtNum === null) return

        // 否则两者都应有值，且数值相等
        expect(cellNum, `GtAmountCell 显示 '-' 但 fmt 显示数值 (value=${String(value)})`).not.toBeNull()
        expect(fmtNum, `fmt 显示 '-' 但 GtAmountCell 显示数值 (value=${String(value)})`).not.toBeNull()

        const a = normZero(cellNum as number)
        const b = normZero(fmtNum as number)
        const tol = Math.max(Math.pow(10, -prefs.decimals), Math.abs(b) * 1e-9)
        expect(Math.abs(a - b)).toBeLessThanOrEqual(tol)
      }),
      { numRuns: 15 },
    )
  })

  /**
   * Property 2 (Task 4.2) — 单位切换单调联动
   * 挂载多个不同金额的 GtAmountCell，依次切换单位序列，断言每次切换后
   * 每个实例的显示值都 ≈ 自身金额 / 当前单位 divisor（即所有实例同步换算，
   * 不存在停留在上一单位的实例）。直接比对 amount/divisor 即蕴含
   * "yuan→wan 显示值 ÷10000" 的单调联动关系。
   * **Validates: Requirements 2.5**
   */
  it('(P2) 切换 {yuan,wan,qian} 序列后所有实例同步按 divisor 换算', async () => {
    const unitArb = fc.constantFrom<'yuan' | 'wan' | 'qian'>('yuan', 'wan', 'qian')
    // 非零金额（showZero=true 兜底零值），覆盖正负 + 大数
    const p2AmountArb = fc.oneof(
      fc.constant(12345.67),
      fc.constant(-98765.43),
      fc.constant(1234567890.12),
      fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true })
        .filter((n) => !Object.is(n, -0)),
    )

    await fc.assert(
      fc.asyncProperty(
        fc.array(p2AmountArb, { minLength: 1, maxLength: 4 }),
        fc.array(unitArb, { minLength: 1, maxLength: 5 }),
        fc.integer({ min: 2, max: 4 }),
        async (amounts, unitSeq, decimals) => {
          const pinia = createPinia()
          setActivePinia(pinia)
          const store = useDisplayPrefsStore()
          store.setShowZero(true)
          store.setDecimals(decimals)
          store.setNegativeRed(false)

          // 挂载多个实例（模拟多个金额单元格跟随同一 displayPrefs）
          const wrappers = amounts.map((a) =>
            mount(GtAmountCell, {
              props: { value: a },
              global: { plugins: [pinia] },
            }),
          )

          try {
            for (const unit of unitSeq) {
              store.setUnit(unit)
              await wrappers[0].vm.$nextTick()

              const divisor = AMOUNT_UNITS[unit].divisor
              for (let i = 0; i < amounts.length; i++) {
                const shown = parseDisplayed(wrappers[i].text().trim())
                expect(
                  shown,
                  `实例 ${i} 在单位 ${unit} 下显示 '-'（金额=${amounts[i]}）`,
                ).not.toBeNull()

                const expected = amounts[i] / divisor
                const a = normZero(shown as number)
                const b = normZero(expected)
                // 显示值是 round(amount/divisor, decimals)，与原值差 ≤ 0.5*10^-d，
                // 容差取 10^-d ⊕ 相对容差 吸收半进位 + 大数 float 误差
                const tol = Math.max(Math.pow(10, -decimals), Math.abs(b) * 1e-9)
                expect(
                  Math.abs(a - b),
                  `实例 ${i} 单位 ${unit}: 显示 ${a} 期望 ≈ ${b}`,
                ).toBeLessThanOrEqual(tol)
              }
            }
          } finally {
            wrappers.forEach((w) => w.unmount())
          }
        },
      ),
      { numRuns: 15 },
    )
  })
})
