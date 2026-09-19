/**
 * g13FvCrossHelpers — G1/G10→G13-3 推送 + 调整数勾稽
 */
import { describe, it, expect } from 'vitest'
import {
  buildG13FvAdjFingerprint,
  mergeFvDiffIntoG13AdjRows,
  findG13AdjustmentWritebackMismatches,
  formatG13AdjWritebackMismatchMessage,
  aggregateDetailAdjustmentByBelong,
} from '../g13FvCrossHelpers'

describe('mergeFvDiffIntoG13AdjRows', () => {
  it('G1 资产正差：贷 6101 / 借 1501，并写入 belongAccount=G1', () => {
    const { rows, addedCount } = mergeFvDiffIntoG13AdjRows([], [{
      description: 'G1-6 公允测试差异：股票A',
      amount: 100,
      belongAccount: 'G1',
      nameKey: '股票A',
      indexRef: 'G1-6',
    }], 'G1-6')
    expect(addedCount).toBe(1)
    expect(rows).toHaveLength(2)
    const pl = rows.find((r) => r.accountCode === '6101')!
    const bs = rows.find((r) => r.accountCode === '1501')!
    expect(pl.creditAmount).toBe(100)
    expect(pl.debitAmount).toBe(0)
    expect(bs.debitAmount).toBe(100)
    expect(pl.belongAccount).toBe('G1')
    expect(String(pl.remark)).toContain('fvfp:G1-6:')
  })

  it('G10 负债正差：借 6101 / 贷 2101', () => {
    const { rows } = mergeFvDiffIntoG13AdjRows([], [{
      description: 'G10-5 公允测试差异：负债B',
      amount: 80,
      belongAccount: 'G10',
      nameKey: '负债B',
    }], 'G10-5')
    const pl = rows.find((r) => r.accountCode === '6101')!
    const bs = rows.find((r) => r.accountCode === '2101')!
    expect(pl.debitAmount).toBe(80)
    expect(pl.creditAmount).toBe(0)
    expect(bs.creditAmount).toBe(80)
    expect(pl.belongAccount).toBe('G10')
  })

  it('同指纹重复推送覆盖旧组', () => {
    const first = mergeFvDiffIntoG13AdjRows([], [{
      description: '差异：X',
      amount: 50,
      belongAccount: 'G1',
      nameKey: 'X',
    }], 'G1-6')
    const second = mergeFvDiffIntoG13AdjRows(first.rows, [{
      description: '差异：X',
      amount: 50,
      belongAccount: 'G1',
      nameKey: 'X',
    }], 'G1-6')
    expect(second.rows).toHaveLength(2)
    expect(second.addedCount).toBe(1)
  })

  it('指纹随金额变化，不同金额并存', () => {
    const a = mergeFvDiffIntoG13AdjRows([], [{
      description: '差异：X', amount: 50, belongAccount: 'G1', nameKey: 'X',
    }], 'G1-6')
    const b = mergeFvDiffIntoG13AdjRows(a.rows, [{
      description: '差异：X', amount: 60, belongAccount: 'G1', nameKey: 'X',
    }], 'G1-6')
    expect(b.rows).toHaveLength(4)
  })
})

describe('findG13AdjustmentWritebackMismatches', () => {
  it('明细与 G13-3 回写一致时无差异', () => {
    const mismatches = findG13AdjustmentWritebackMismatches(
      [{ belongAccount: 'G1', adjustment: 100 }],
      [
        { category: '账项调整', accountCode: '6101', belongAccount: 'G1', debitAmount: 0, creditAmount: 100 },
        { category: '账项调整', accountCode: '1501', belongAccount: 'G1', debitAmount: 100, creditAmount: 0 },
      ],
    )
    expect(mismatches).toHaveLength(0)
  })

  it('不一致时返回差额并格式化消息', () => {
    const mismatches = findG13AdjustmentWritebackMismatches(
      [{ belongAccount: 'G1', adjustment: 100 }],
      [{ category: '账项调整', accountCode: '6101', belongAccount: 'G1', debitAmount: 0, creditAmount: 40 }],
    )
    expect(mismatches).toHaveLength(1)
    expect(mismatches[0].diff).toBeCloseTo(60, 5)
    expect(formatG13AdjWritebackMismatchMessage(mismatches)).toContain('G1')
  })

  it('报表调整不计入 G13-3 回写净额', () => {
    const mismatches = findG13AdjustmentWritebackMismatches(
      [{ belongAccount: 'G1', adjustment: 0 }],
      [{ category: '报表调整', accountCode: '6101', belongAccount: 'G1', debitAmount: 0, creditAmount: 50 }],
    )
    expect(mismatches).toHaveLength(0)
  })
})

describe('buildG13FvAdjFingerprint / aggregateDetailAdjustmentByBelong', () => {
  it('指纹稳定', () => {
    expect(buildG13FvAdjFingerprint('股票 A', 12.34, 'G1-6'))
      .toBe(buildG13FvAdjFingerprint('股票A', 12.34, 'G1-6'))
  })

  it('明细按所属科目汇总', () => {
    const by = aggregateDetailAdjustmentByBelong([
      { belongAccount: 'G1', adjustment: 10 },
      { belongAccount: 'G1', adjustment: 5 },
      { belongAccount: '', adjustment: 3 },
    ])
    expect(by.G1).toBe(15)
    expect(by.other).toBe(3)
  })
})
