/**
 * useF2DisclosureListed — Property-Based Test
 *
 * 覆盖 design Property 1（计提比例口径）与 Property 2（占比口径零回归）。
 * 源模板依据「附注披露信息（上市公司）」R52/R54：
 *   C52 = B52/B54  → 账面余额「比例(%)」= 本组合 ÷ 合计（占比）
 *   F52 = D52/B52  → 存货跌价准备「比例(%)」= 本组合跌价 ÷ **本组合账面余额**（计提比例）
 * 两列分母不同，是本 spec 修复的核心。
 *
 * Spec: .kiro/specs/f2-inventory-disclosure-template-alignment/
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import { ref } from 'vue'
import { useF2DisclosureListed, safeRatio } from '../composables/useF2DisclosureListed'
import type { ChecklistResponse } from '../composables/useF2FormData'

/** 金额：非负、两位小数、上限一亿（覆盖 0 与大额，含分位舍入场景） */
const amount = fc
  .integer({ min: 0, max: 10_000_000_000 })
  .map((cents) => Math.round(cents) / 100)

interface Combo {
  balance: number
  impairment: number
}

const comboArb: fc.Arbitrary<Combo> = fc.record({
  balance: amount,
  impairment: amount,
})

function mountWithCombos(combos: readonly Combo[]) {
  const map = new Map<string, ChecklistResponse>()
  const payload = combos.map((c, i) => ({
    rowId: `s3-pbt-${i}`,
    groupName: `组合${i}`,
    balance: c.balance,
    impairment: c.impairment,
    provisionStandard: '',
    netValue: 0,
    balancePct: 0,
    impairmentPct: 0,
  }))
  for (const key of ['F2-note-listed-s3-end', 'F2-note-listed-s3-prior']) {
    map.set(key, { item_id: key, conclusion: null, remark: JSON.stringify(payload) })
  }
  return useF2DisclosureListed({
    allResponses: ref(map),
    isReadonly: ref(false),
    applicableStandards: ref(['listed_standalone']),
  })
}

/** 浮点求和顺序差异容忍：按量级取相对容差 */
function closeEnough(a: number, b: number, scale = 1): boolean {
  return Math.abs(a - b) <= Math.max(1e-9, Math.abs(scale) * 1e-9)
}

describe('safeRatio 性质', () => {
  it('分母为 0 / 非有限 → 恒 0，且结果始终有限', () => {
    fc.assert(
      fc.property(amount, (part) => {
        expect(safeRatio(part, 0)).toBe(0)
        expect(Number.isFinite(safeRatio(part, 0))).toBe(true)
      }),
      { numRuns: 60 },
    )
  })

  it('分母非 0 时等于 part/total', () => {
    fc.assert(
      fc.property(
        amount,
        amount.filter((x) => x > 0),
        (part, total) => {
          expect(safeRatio(part, total)).toBeCloseTo(part / total, 12)
        },
      ),
      { numRuns: 60 },
    )
  })
})

describe('Property 1：计提比例 = 本组合跌价 ÷ 本组合账面余额', () => {
  it('逐行成立；账面余额为 0 时为 0（不产生 NaN/Infinity）', () => {
    fc.assert(
      fc.property(fc.array(comboArb, { minLength: 1, maxLength: 6 }), (combos) => {
        const api = mountWithCombos(combos)
        const rows = api.s3EndRows.value

        expect(rows).toHaveLength(combos.length)
        rows.forEach((r, i) => {
          const expected = combos[i].balance === 0
            ? 0
            : combos[i].impairment / combos[i].balance
          expect(Number.isFinite(r.impairmentPct)).toBe(true)
          expect(closeEnough(r.impairmentPct, expected, expected)).toBe(true)
        })
      }),
      { numRuns: 40 },
    )
  })

  it('合计行计提比例 = 跌价合计 ÷ 账面余额合计', () => {
    fc.assert(
      fc.property(fc.array(comboArb, { minLength: 1, maxLength: 6 }), (combos) => {
        const api = mountWithCombos(combos)
        const total = api.s3EndTotal.value
        const balSum = combos.reduce((s, c) => s + c.balance, 0)
        const impSum = combos.reduce((s, c) => s + c.impairment, 0)

        expect(closeEnough(total.balance, balSum, balSum)).toBe(true)
        expect(closeEnough(total.impairment, impSum, impSum)).toBe(true)

        const expected = balSum === 0 ? 0 : impSum / balSum
        expect(Number.isFinite(total.impairmentPct)).toBe(true)
        expect(closeEnough(total.impairmentPct, expected, expected)).toBe(true)
      }),
      { numRuns: 40 },
    )
  })

  it('反例守卫：计提比例不得等于「占跌价合计的比例」（修复前的错误口径）', () => {
    fc.assert(
      fc.property(
        // 构造能区分两种口径的输入：至少两组、跌价合计 > 0、各组账面余额 ≠ 跌价合计
        fc.tuple(
          fc.record({ balance: fc.constant(1000), impairment: fc.constant(150) }),
          fc.record({ balance: fc.constant(4000), impairment: fc.constant(250) }),
        ),
        ([a, b]) => {
          const api = mountWithCombos([a, b])
          const rows = api.s3EndRows.value
          const impSum = a.impairment + b.impairment

          // 正确口径
          expect(rows[0].impairmentPct).toBeCloseTo(150 / 1000, 12)
          // 错误口径（占跌价合计）应当不成立
          expect(rows[0].impairmentPct).not.toBeCloseTo(150 / impSum, 6)
        },
      ),
      { numRuns: 5 },
    )
  })
})

describe('Property 2：占比口径零回归（分母为合计账面余额）', () => {
  it('逐行 = 本组合账面余额 ÷ 合计账面余额；合计行恒 1（合计>0 时）', () => {
    fc.assert(
      fc.property(fc.array(comboArb, { minLength: 1, maxLength: 6 }), (combos) => {
        const api = mountWithCombos(combos)
        const rows = api.s3EndRows.value
        const balSum = combos.reduce((s, c) => s + c.balance, 0)

        rows.forEach((r, i) => {
          const expected = balSum === 0 ? 0 : combos[i].balance / balSum
          expect(Number.isFinite(r.balancePct)).toBe(true)
          expect(closeEnough(r.balancePct, expected, expected)).toBe(true)
        })

        expect(api.s3EndTotal.value.balancePct).toBe(balSum > 0 ? 1 : 0)
      }),
      { numRuns: 40 },
    )
  })

  it('占比之和为 1（合计 > 0 时），即口径自洽', () => {
    fc.assert(
      fc.property(
        fc.array(comboArb, { minLength: 1, maxLength: 6 })
          .filter((cs) => cs.reduce((s, c) => s + c.balance, 0) > 0),
        (combos) => {
          const api = mountWithCombos(combos)
          const sum = api.s3EndRows.value.reduce((s, r) => s + r.balancePct, 0)
          expect(sum).toBeCloseTo(1, 9)
        },
      ),
      { numRuns: 40 },
    )
  })
})

describe('Property 1/2：期末表与上年年末表同算法', () => {
  it('两表在相同输入下逐行比例一致', () => {
    fc.assert(
      fc.property(fc.array(comboArb, { minLength: 1, maxLength: 5 }), (combos) => {
        const api = mountWithCombos(combos)
        const end = api.s3EndRows.value
        const prior = api.s3PriorRows.value
        expect(prior).toHaveLength(end.length)
        end.forEach((e, i) => {
          expect(prior[i].impairmentPct).toBeCloseTo(e.impairmentPct, 12)
          expect(prior[i].balancePct).toBeCloseTo(e.balancePct, 12)
        })
        expect(api.s3PriorTotal.value.impairmentPct)
          .toBeCloseTo(api.s3EndTotal.value.impairmentPct, 12)
      }),
      { numRuns: 30 },
    )
  })
})

describe('净值派生自洽', () => {
  it('账面价值 = 账面余额 − 跌价准备（逐行与合计）', () => {
    fc.assert(
      fc.property(fc.array(comboArb, { minLength: 1, maxLength: 6 }), (combos) => {
        const api = mountWithCombos(combos)
        api.s3EndRows.value.forEach((r, i) => {
          const expected = combos[i].balance - combos[i].impairment
          expect(closeEnough(r.netValue, expected, expected)).toBe(true)
        })
        const t = api.s3EndTotal.value
        expect(closeEnough(t.netValue, t.balance - t.impairment, t.balance)).toBe(true)
      }),
      { numRuns: 40 },
    )
  })
})
