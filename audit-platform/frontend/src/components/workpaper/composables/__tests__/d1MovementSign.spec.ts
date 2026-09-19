/**
 * D1 坏账准备变动表符号守卫
 *
 * Spec: .kiro/specs/d1-extraction-chain-completion/ (Property 9 / Requirement 6.3, 6.4)
 *
 * 源模板两处公式（decisive evidence，`data_only=False` 读出的单元格公式）：
 *   * 披露变动表：上市 `B100 = B94+B95-B96-B97-B98-B99`
 *                国企 `G48 = B48+C48-D48-E48-F48`
 *     → 期初 + 计提 − 收回或转回 − 核销 − 转销 − **其他变动（减项）**
 *   * D1-4 坏账准备明细表：`K12 = B12+SUM(F12:G12)-SUM(H12:J12)`
 *     （本期增加 = 计提 + **其他增加**；本期减少 = 转回 + 核销 + 其他减少）
 *     → 前端 5 列口径下「其他」是**加项**
 *
 * 改造前披露变动表复用了 D1-4 的 `calcBadDebtEndBalance`（其他为加项），与自家勾稽面板
 * 的 F4-7 判定（按 G48 取减项）**符号相反** —— 只要「其他变动」非 0，披露表算出的期末数
 * 就被自己的勾稽面板判为异常。
 */
import { describe, expect, it } from 'vitest'
import * as fc from 'fast-check'
import {
  calcBadDebtEndBalance,
  calcDisclosureBadDebtEnd,
} from '../useD1FormulaEngine'
import { runD1DisclosureChecks } from '../d1DisclosureConsistency'

const amount = () => fc.float({ min: -1e8, max: 1e8, noNaN: true })

describe('Property 9: 变动表符号与源模板一致', () => {
  it('披露变动表：其他变动是减项（源模板 B100 / G48）', () => {
    // 期初 1000 + 计提 200 − 转回 50 − 核销 30 − 转销 10 − 其他 5 = 1105
    expect(calcDisclosureBadDebtEnd(1000, 200, 50, 30, 10, 5)).toBe(1105)
  })

  it('D1-4 明细表：其他是加项（源模板 K=B+SUM(F:G)−SUM(H:J)），语义保持不变', () => {
    // 期初 1000 + 计提 200 − 收回 50 − 转回 30 − 核销 10 + 其他 5 = 1115
    expect(calcBadDebtEndBalance(1000, 200, 50, 30, 10, 5)).toBe(1115)
  })

  it('🔴 两个函数不可互换：其他 ≠ 0 时结果必不同（防有人再合并成一个）', () => {
    fc.assert(
      fc.property(amount(), amount(), (base, other) => {
        fc.pre(Math.abs(other) > 1)
        const a = calcDisclosureBadDebtEnd(base, 0, 0, 0, 0, other)
        const b = calcBadDebtEndBalance(base, 0, 0, 0, 0, other)
        expect(a).not.toBeCloseTo(b, 6)
      }),
      { numRuns: 50 },
    )
  })

  it('披露公式恒满足 期末 = 期初 + 计提 − 转回 − 核销 − 转销 − 其他', () => {
    fc.assert(
      fc.property(
        fc.record({
          prior: amount(),
          prov: amount(),
          rev: amount(),
          wo: amount(),
          tr: amount(),
          other: amount(),
        }),
        (v) => {
          expect(calcDisclosureBadDebtEnd(v.prior, v.prov, v.rev, v.wo, v.tr, v.other)).toBeCloseTo(
            v.prior + v.prov - v.rev - v.wo - v.tr - v.other,
            4,
          )
        },
      ),
      { numRuns: 60 },
    )
  })

  it('🔴 与勾稽面板 F4-7 判定同口径（面板 pass 则公式算出的期末数一致）', () => {
    const prior = 3037132.25
    const provision = 500000
    const reversal = 1874844.22
    const writeOff = 100000
    const transfer = 0
    const other = 25000
    const endBalance = calcDisclosureBadDebtEnd(
      prior, provision, reversal, writeOff, transfer, other,
    )
    const zeroClass = { label: '', balance: 0, ratio: 0, provision: 0, lossRate: 0, bookValue: 0 }
    const zeroAmt = { balance: 0, provision: 0 }
    const result = runD1DisclosureChecks({
      variant: 'soe',
      summaryRows: [],
      summaryTotal: {
        category: '合计',
        endBalance: 0,
        endProvision: 0,
        endBookValue: 0,
        priorBalance: 0,
        priorProvision: 0,
        priorBookValue: 0,
      },
      classEndRows: [],
      classPriorRows: [],
      classEndTotal: zeroClass,
      classPriorTotal: zeroClass,
      individualEndRows: [],
      portfolioEndRows: [],
      classEndIndividual: zeroAmt,
      classEndPortfolio: zeroAmt,
      movementRows: [
        {
          label: '按组合计提预期信用损失的应收票据',
          priorBalance: prior,
          provision,
          reversal,
          writeOff,
          transfer,
          other,
          endBalance,
        },
      ],
      movementDetailRows: [],
      movementEndTotal: endBalance,
      movementWriteOffTotal: writeOff,
      pledgedRows: [],
      pledgedTotal: 0,
      endorsedRows: [],
      endorsedTotal: { derecognized: 0, notDerecognized: 0 },
      transferRows: [],
      transferTotal: 0,
      writeOffAmount: 0,
      writeOffDetailRows: [],
    } as any)
    const f47 = result.checks.filter((c) => c.id.startsWith('F4-7'))
    expect(f47.length).toBeGreaterThan(0)
    for (const c of f47) {
      expect(c.level, `F4-7 判定应通过，实际 ${c.level}：${c.detail ?? ''}`).toBe('ok')
    }
  })
})
