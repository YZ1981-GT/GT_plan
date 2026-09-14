/**
 * N 循环税务类披露勾稽引擎单测 + PBT
 *
 * 不变式：
 * - P1 合计取真和时恒 ok；超容差（>0.01）必 error
 * - P2 任一侧 null → skip（跨底稿取数未就绪时不判定）；明细含 null 不影响求和口径
 * - P3 无明细行时不产出该条（空表的合计可能来自别处，硬校验会误报）
 * - P4 N2 国企逐行恒等式 期末 = 期初 + 应交 − 已交（源模板 =B8+C8-D8）
 * - P5 N5 跨表：表(2) 末行 = 表(1) 合计；两版规则文案不同但结构一致
 * - P6 纯函数：同输入深相等、不改入参
 *
 * spec: `.kiro/specs/n-cycle-tax-disclosure-alignment/` Task 7.3
 */
import fc from 'fast-check'
import { describe, expect, it } from 'vitest'
import {
  runN2ListedChecks,
  runN2SoeChecks,
  runN4ListedChecks,
  runN5Checks,
  type N2SoeRowLike,
} from '../nCycleTaxConsistency'
import { summarizeChecks } from '../shared/disclosureConsistency'

// ─── N2 上市 ─────────────────────────────────────────────────────────────────

describe('N2 上市 合计校验', () => {
  const rows = [
    { item: '增值税', end: 100, prior: 60 },
    { item: '消费税', end: 50, prior: 40 },
  ]

  it('合计取真和 → 两条 ok', () => {
    const r = runN2ListedChecks(rows, { end: 150, prior: 100 })
    expect(r).toHaveLength(2)
    expect(r.every((c) => c.level === 'ok')).toBe(true)
    expect(r[0].refs).toEqual(['N2-1'])
  })

  it('合计不符 → error 且给出差额', () => {
    const r = runN2ListedChecks(rows, { end: 160, prior: 100 })
    expect(r[0].level).toBe('error')
    expect(r[0].diff).toBe(10)
  })

  it('P3 无明细行 → 不产出', () => {
    expect(runN2ListedChecks([], { end: 999, prior: 999 })).toEqual([])
  })

  it('P2 明细全 null → skip（不误判为 0）', () => {
    const r = runN2ListedChecks([{ item: 'X', end: null, prior: null }], { end: null, prior: null })
    expect(r.every((c) => c.level === 'skip')).toBe(true)
  })
})

// ─── N2 国企 ─────────────────────────────────────────────────────────────────

describe('N2 国企 变动口径校验', () => {
  const row = (over: Partial<N2SoeRowLike> = {}): N2SoeRowLike => ({
    item: '增值税', opening: 100, payable: 80, paid: 30, end: 150, ...over,
  })

  it('P4 逐行恒等式成立 → ok', () => {
    const r = runN2SoeChecks([row()], { opening: 100, payable: 80, paid: 30, end: 150 })
    const rowCheck = r.find((c) => c.label === '增值税 期末余额')!
    expect(rowCheck.level).toBe('ok')
    expect(rowCheck.rule).toContain('=B8+C8-D8')
  })

  it('P4 恒等式不成立 → error', () => {
    const r = runN2SoeChecks([row({ end: 140 })], { opening: 100, payable: 80, paid: 30, end: 140 })
    expect(r.find((c) => c.label === '增值税 期末余额')!.level).toBe('error')
  })

  it('P2 任一项缺失 → 该行 skip', () => {
    const r = runN2SoeChecks([row({ paid: null })], { opening: 100, payable: 80, paid: null, end: 150 })
    expect(r.find((c) => c.label === '增值税 期末余额')!.level).toBe('skip')
  })

  it('产出四列合计校验', () => {
    const labels = runN2SoeChecks([row()], { opening: 100, payable: 80, paid: 30, end: 150 })
      .map((c) => c.label)
    expect(labels).toContain('合计（期初余额）')
    expect(labels).toContain('合计（本期应交）')
    expect(labels).toContain('合计（本期已交）')
    expect(labels).toContain('合计（期末余额）')
  })

  it('无明细行时只剩 0 条（四列合计也不产出）', () => {
    expect(runN2SoeChecks([], { opening: 1, payable: 1, paid: 1, end: 1 })).toEqual([])
  })
})

// ─── N4 ──────────────────────────────────────────────────────────────────────

describe('N4 上市 合计校验', () => {
  it('合计取真和 → ok；引用 N4-1', () => {
    const r = runN4ListedChecks(
      [{ item: '印花税', current: 12, prior: 10 }, { item: '房产税', current: 8, prior: 6 }],
      { current: 20, prior: 16 },
    )
    expect(r.every((c) => c.level === 'ok')).toBe(true)
    expect(r[0].refs).toEqual(['N4-1'])
  })

  it('超容差 → error', () => {
    const r = runN4ListedChecks([{ item: 'X', current: 10, prior: 10 }], { current: 10.5, prior: 10 })
    expect(r[0].level).toBe('error')
  })
})

// ─── N5 ──────────────────────────────────────────────────────────────────────

describe('N5 所得税费用 校验', () => {
  const input = {
    detailRows: [
      { item: '当期所得税', current: 300, prior: 200 },
      { item: '递延所得税', current: 100, prior: 50 },
    ],
    detailTotals: { current: 400, prior: 250 },
    reconcileRows: [
      { item: '利润总额', current: 1000, prior: 800 },
      { item: '不可抵扣', current: -600, prior: -550 },
    ],
    reconcileTail: { current: 400, prior: 250 },
  }

  it('P5 三类校验各两条（本期/上期）共 6 条，全 ok', () => {
    const r = runN5Checks('listed', input)
    expect(r).toHaveLength(6)
    expect(r.every((c) => c.level === 'ok')).toBe(true)
  })

  it('P5 跨表不符 → error', () => {
    const r = runN5Checks('listed', {
      ...input,
      reconcileTail: { current: 380, prior: 250 },
    })
    const cross = r.find((c) => c.label.startsWith('跨表') && c.label.includes('本期'))!
    expect(cross.level).toBe('error')
    expect(cross.diff).toBe(-20)
  })

  it('两版规则文案不同（上市引注1 / 国企引合计行）但结构一致', () => {
    const listed = runN5Checks('listed', input)
    const soe = runN5Checks('soe', input)
    expect(listed).toHaveLength(soe.length)
    expect(listed.some((c) => c.rule.includes('源模板注 1'))).toBe(true)
    expect(soe.some((c) => c.rule.includes('合  计'))).toBe(true)
    expect(listed.some((c) => c.label.includes('「所得税费用」行'))).toBe(true)
    expect(soe.some((c) => c.label.includes('表(2) 合计'))).toBe(true)
  })

  it('表(1) 合计规则按变体分化（上市两项 / 国企三项）', () => {
    expect(runN5Checks('listed', input)[0].rule).toContain('=SUM(C9:C10)')
    expect(runN5Checks('soe', input)[0].rule).toContain('=SUM(C8:C10)')
  })

  it('明细为空时不产出该条但跨表仍校验', () => {
    const r = runN5Checks('listed', { ...input, detailRows: [], reconcileRows: [] })
    expect(r).toHaveLength(2)
    expect(r.every((c) => c.label.startsWith('跨表'))).toBe(true)
  })
})

// ─── summarize ───────────────────────────────────────────────────────────────

describe('汇总', () => {
  it('全 ok 且非空 → allPassed', () => {
    const s = summarizeChecks(runN4ListedChecks([{ item: 'X', current: 1, prior: 2 }], { current: 1, prior: 2 }))
    expect(s.allPassed).toBe(true)
    expect(s.error).toBe(0)
  })

  it('空结果不算通过', () => {
    expect(summarizeChecks([]).allPassed).toBe(false)
  })
})

// ─── PBT ─────────────────────────────────────────────────────────────────────

const amount = fc.integer({ min: -1_000_000, max: 1_000_000 })

describe('PBT', () => {
  it('P1 合计取真和恒 ok（N2 上市 / N4）', () => {
    fc.assert(
      fc.property(fc.array(amount, { minLength: 1, maxLength: 8 }), (vals) => {
        const sum = vals.reduce((a, b) => a + b, 0)
        const rows = vals.map((v, i) => ({ item: `t${i}`, end: v, prior: v, current: v }))
        expect(runN2ListedChecks(rows, { end: sum, prior: sum })[0].level).toBe('ok')
        expect(runN4ListedChecks(rows, { current: sum, prior: sum })[0].level).toBe('ok')
      }),
      { numRuns: 20 },
    )
  })

  it('P4 N2 国企恒等式：end 取真值恒 ok', () => {
    fc.assert(
      fc.property(amount, amount, amount, (opening, payable, paid) => {
        const end = Math.round((opening + payable - paid) * 100) / 100
        const r = runN2SoeChecks(
          [{ item: 'X', opening, payable, paid, end }],
          { opening, payable, paid, end },
        )
        expect(r.find((c) => c.label === 'X 期末余额')!.level).toBe('ok')
      }),
      { numRuns: 20 },
    )
  })

  it('P4 N2 国企恒等式：end 偏移必 error', () => {
    fc.assert(
      fc.property(amount, amount, amount, fc.integer({ min: 1, max: 5000 }),
        (opening, payable, paid, delta) => {
          const end = Math.round((opening + payable - paid) * 100) / 100 + delta
          const r = runN2SoeChecks(
            [{ item: 'X', opening, payable, paid, end }],
            { opening, payable, paid, end },
          )
          expect(r.find((c) => c.label === 'X 期末余额')!.level).toBe('error')
        }),
      { numRuns: 20 },
    )
  })

  it('P5 N5 跨表：tail 取 detail 合计恒 ok', () => {
    fc.assert(
      fc.property(fc.array(amount, { minLength: 1, maxLength: 5 }), (vals) => {
        const sum = vals.reduce((a, b) => a + b, 0)
        const detailRows = vals.map((v, i) => ({ item: `d${i}`, current: v, prior: v }))
        const r = runN5Checks('soe', {
          detailRows,
          detailTotals: { current: sum, prior: sum },
          reconcileRows: detailRows,
          reconcileTail: { current: sum, prior: sum },
        })
        expect(r.every((c) => c.level === 'ok')).toBe(true)
      }),
      { numRuns: 20 },
    )
  })

  it('P6 纯函数：同输入深相等且不改入参', () => {
    fc.assert(
      fc.property(fc.array(amount, { minLength: 1, maxLength: 5 }), amount, (vals, total) => {
        const rows = vals.map((v, i) => ({ item: `t${i}`, end: v, prior: v }))
        const frozen = JSON.parse(JSON.stringify(rows))
        const a = runN2ListedChecks(rows, { end: total, prior: total })
        const b = runN2ListedChecks(rows, { end: total, prior: total })
        expect(a).toEqual(b)
        expect(rows).toEqual(frozen)
      }),
      { numRuns: 20 },
    )
  })
})
