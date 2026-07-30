/**
 * N1 披露内部勾稽引擎单测 + PBT
 *
 * 规则全部来自源模板公式（见 `n1DisclosureConsistency.ts` 头注表）。
 * 关键不变式：
 * - P1 相等（容差 0.01）→ ok；超差 → error
 * - P2 任一侧 null → skip（不误报，跨底稿取数未就绪时不判定）
 * - P3 段内无明细行时不产出该条校验（空段小计可能来自跨底稿取数）
 * - P4 国企多出表（2）双段小计两条；上市不产出（上市表 2 是 2 行形态无段小计）
 * - P5 跨表勾稽：亏损到期合计 = 未确认明细「可抵扣亏损」行（期末 + 上期各一条）
 * - P6 纯函数：同输入结果深相等、不改入参
 *
 * spec: `.kiro/specs/n1-deferred-tax-disclosure-template-alignment/` R3 / Task 4.4
 */
import fc from 'fast-check'
import { describe, expect, it } from 'vitest'
import {
  N1_CHECK_TOLERANCE,
  eqCheck,
  runN1DisclosureChecks,
  summarizeN1Checks,
  type N1ConsistencyInput,
} from '../n1DisclosureConsistency'

// ─── eqCheck ─────────────────────────────────────────────────────────────────

describe('eqCheck（P1 / P2）', () => {
  it('相等 → ok，差额为 0', () => {
    const r = eqCheck('L', 'R', 100, 100)
    expect(r.level).toBe('ok')
    expect(r.diff).toBe(0)
  })

  it('容差内 → ok（源模板金额保留 2 位小数）', () => {
    expect(eqCheck('L', 'R', 100, 100 + N1_CHECK_TOLERANCE).level).toBe('ok')
  })

  it('超容差 → error', () => {
    const r = eqCheck('L', 'R', 100, 100.5)
    expect(r.level).toBe('error')
    expect(r.diff).toBe(-0.5)
  })

  it('任一侧 null → skip 且 diff 为 null（不误报）', () => {
    expect(eqCheck('L', 'R', null, 100).level).toBe('skip')
    expect(eqCheck('L', 'R', 100, null).level).toBe('skip')
    expect(eqCheck('L', 'R', null, null).diff).toBeNull()
  })

  it('refs 原样透传（GtIndexChip 追溯）', () => {
    expect(eqCheck('L', 'R', 1, 1, ['N1-5']).refs).toEqual(['N1-5'])
  })
})

// ─── 段小计 ──────────────────────────────────────────────────────────────────

describe('段小计校验（P1 / P3）', () => {
  const base: N1ConsistencyInput = {
    unoffsetAsset: { details: [100, 50], subtotal: 150 },
    unoffsetLiability: { details: [30], subtotal: 30 },
  }

  it('小计 = 明细之和 → 两条 ok', () => {
    const r = runN1DisclosureChecks('listed', base)
    expect(r).toHaveLength(2)
    expect(r.every((c) => c.level === 'ok')).toBe(true)
  })

  it('小计与明细不符 → error 且给出差额', () => {
    const r = runN1DisclosureChecks('listed', {
      unoffsetAsset: { details: [100, 50], subtotal: 160 },
    })
    expect(r[0].level).toBe('error')
    expect(r[0].diff).toBe(10)
  })

  it('P3 段内无明细行 → 不产出该条', () => {
    expect(runN1DisclosureChecks('listed', {
      unoffsetAsset: { details: [], subtotal: 999 },
    })).toEqual([])
  })

  it('明细全 null → 和为 null → skip（不误判为 0）', () => {
    const r = runN1DisclosureChecks('listed', {
      unoffsetAsset: { details: [null, null], subtotal: null },
    })
    expect(r[0].level).toBe('skip')
  })
})

// ─── 变体差异 ────────────────────────────────────────────────────────────────

describe('P4 — 国企多出表（2）双段小计', () => {
  const input: N1ConsistencyInput = {
    netOffsetAsset: { details: [10, 20], subtotal: 30 },
    netOffsetLiability: { details: [5], subtotal: 5 },
  }

  it('soe 产出两条表(2)校验', () => {
    const labels = runN1DisclosureChecks('soe', input).map((c) => c.label)
    expect(labels).toEqual(['表(2)互抵后资产段小计', '表(2)互抵后负债段小计'])
  })

  it('listed 不产出表(2)校验（上市表 2 是 2 行形态，无段小计）', () => {
    expect(runN1DisclosureChecks('listed', input)).toEqual([])
  })
})

describe('上期列文案随变体（上年年末 / 年初）', () => {
  const input: N1ConsistencyInput = {
    unrecognized: {
      temporaryDiff: 100,
      deductibleLoss: 200,
      total: 300,
      priorTemporaryDiff: 50,
      priorDeductibleLoss: 60,
      priorTotal: 110,
    },
  }

  it('listed 用「上年年末」', () => {
    const labels = runN1DisclosureChecks('listed', input).map((c) => c.label)
    expect(labels).toContain('未确认明细合计（上年年末）')
  })

  it('soe 用「年初」', () => {
    const labels = runN1DisclosureChecks('soe', input).map((c) => c.label)
    expect(labels).toContain('未确认明细合计（年初）')
  })
})

// ─── 跨表勾稽 ────────────────────────────────────────────────────────────────

describe('P5 — 跨表勾稽（源模板 B40=B52 / C40=C52）', () => {
  const input: N1ConsistencyInput = {
    unrecognized: {
      temporaryDiff: 100,
      deductibleLoss: 500,
      total: 600,
      priorTemporaryDiff: 40,
      priorDeductibleLoss: 300,
      priorTotal: 340,
    },
    lossExpiry: {
      yearAmounts: [200, 300],
      total: 500,
      priorYearAmounts: [300],
      priorTotal: 300,
    },
  }

  it('亏损到期合计 = 未确认可抵扣亏损 → ok（期末 + 上期两条）', () => {
    const cross = runN1DisclosureChecks('listed', input).filter((c) =>
      c.label.startsWith('亏损到期合计 = 未确认可抵扣亏损'),
    )
    expect(cross).toHaveLength(2)
    expect(cross.every((c) => c.level === 'ok')).toBe(true)
    expect(cross[0].refs).toEqual(['N1-5'])
  })

  it('两者不符 → error', () => {
    const cross = runN1DisclosureChecks('listed', {
      ...input,
      lossExpiry: { ...input.lossExpiry!, total: 480 },
    }).filter((c) => c.label === '亏损到期合计 = 未确认可抵扣亏损（期末）')
    expect(cross[0].level).toBe('error')
    expect(cross[0].diff).toBe(-20)
  })

  it('无 unrecognized 时不产出跨表条目（缺一侧不硬凑）', () => {
    const r = runN1DisclosureChecks('listed', { lossExpiry: input.lossExpiry })
    expect(r.some((c) => c.label.startsWith('亏损到期合计 = '))).toBe(false)
  })
})

// ─── summarize ───────────────────────────────────────────────────────────────

describe('summarizeN1Checks', () => {
  it('统计各级数量；全 ok 且非空 → allPassed', () => {
    const s = summarizeN1Checks(runN1DisclosureChecks('listed', {
      unoffsetAsset: { details: [1, 2], subtotal: 3 },
    }))
    expect(s).toEqual({ total: 1, ok: 1, error: 0, skip: 0, allPassed: true })
  })

  it('空结果不算通过（无可校验项 ≠ 校验通过）', () => {
    expect(summarizeN1Checks([]).allPassed).toBe(false)
  })
})

// ─── PBT ─────────────────────────────────────────────────────────────────────

const amount = fc.integer({ min: -1_000_000, max: 1_000_000 })

describe('PBT', () => {
  it('P1 小计取明细真和时恒 ok', () => {
    fc.assert(
      fc.property(fc.array(amount, { minLength: 1, maxLength: 8 }), (details) => {
        const sum = details.reduce((a, b) => a + b, 0)
        const r = runN1DisclosureChecks('listed', {
          unoffsetAsset: { details, subtotal: sum },
        })
        expect(r[0].level).toBe('ok')
      }),
      { numRuns: 20 },
    )
  })

  it('P2 明细含 null 不影响求和口径（null 视为未填而非 0）', () => {
    fc.assert(
      fc.property(fc.array(amount, { minLength: 1, maxLength: 6 }), (details) => {
        const withNulls = [...details, null, null]
        const sum = details.reduce((a, b) => a + b, 0)
        const r = runN1DisclosureChecks('soe', {
          unoffsetAsset: { details: withNulls, subtotal: sum },
        })
        expect(r[0].level).toBe('ok')
      }),
      { numRuns: 20 },
    )
  })

  it('P6 纯函数：同输入深相等且不改入参', () => {
    fc.assert(
      fc.property(
        fc.array(amount, { minLength: 1, maxLength: 5 }),
        amount,
        (details, subtotal) => {
          const input: N1ConsistencyInput = { unoffsetAsset: { details, subtotal } }
          const frozen = JSON.parse(JSON.stringify(input))
          const a = runN1DisclosureChecks('soe', input)
          const b = runN1DisclosureChecks('soe', input)
          expect(a).toEqual(b)
          expect(input).toEqual(frozen)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('P1 超容差必 error（差额绝对值 > 0.01）', () => {
    fc.assert(
      fc.property(
        fc.array(amount, { minLength: 1, maxLength: 5 }),
        fc.integer({ min: 1, max: 1000 }),
        (details, delta) => {
          const sum = details.reduce((a, b) => a + b, 0)
          const r = runN1DisclosureChecks('listed', {
            unoffsetAsset: { details, subtotal: sum + delta },
          })
          expect(r[0].level).toBe('error')
        },
      ),
      { numRuns: 20 },
    )
  })
})
