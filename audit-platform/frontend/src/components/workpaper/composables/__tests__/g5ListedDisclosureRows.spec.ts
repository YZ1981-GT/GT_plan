import { describe, it, expect } from 'vitest'
import {
  bookValue,
  safeRate,
  fmtRate,
  recomputeNatureDerived,
  recomputeMethodTotals,
  recomputeMovementClosing,
  recomputeAgingTotals,
  computeNatureMethodTieOut,
  serializeListedDisclosure,
  parseListedDisclosure,
  buildDefaultListedState,
  createEmptyCustomNature,
  syncPortfoliosByNames,
  createEmptyPortfolio,
  createAgingRows,
  classifyNatureFromDetail,
  extractBadDebtForDisclosure,
} from '../g5ListedDisclosureRows'

describe('g5ListedDisclosureRows', () => {
  it('safeRate 分母为 0 时不产生 #DIV/0!', () => {
    expect(safeRate(10, 0)).toBeNull()
    expect(fmtRate(null)).toBe('—')
    expect(safeRate(25, 100)).toBe(25)
    expect(fmtRate(25)).toBe('25.00%')
  })

  it('bookValue = 余额 − 坏账', () => {
    expect(bookValue({ balance: 100, provision: 30 })).toBe(70)
  })

  it('性质表小计/合计与一年内扣除', () => {
    const state = buildDefaultListedState()
    const rows = state.natureRows.map((r) => {
      if (r.rowKey === 'finance-lease') {
        return { ...r, end: { balance: 100, provision: 10 }, prior: { balance: 80, provision: 8 } }
      }
      if (r.rowKey === 'other') {
        return { ...r, end: { balance: 50, provision: 5 }, prior: { balance: 40, provision: 4 } }
      }
      if (r.rowKey === 'one-year') {
        return { ...r, end: { balance: 20, provision: 2 }, prior: { balance: 10, provision: 1 } }
      }
      return r
    })
    const derived = recomputeNatureDerived(rows)
    const sub = derived.find((r) => r.kind === 'subtotal')!
    const total = derived.find((r) => r.kind === 'total')!
    expect(sub.end.balance).toBe(150)
    expect(sub.end.provision).toBe(15)
    expect(total.end.balance).toBe(130)
    expect(total.end.provision).toBe(13)
  })

  it('自定义行参与小计；动态插行后合计联动', () => {
    const state = buildDefaultListedState()
    const custom = createEmptyCustomNature('自定义项目')
    custom.end = { balance: 40, provision: 4 }
    const idx = state.natureRows.findIndex((r) => r.kind === 'subtotal')
    const rows = [...state.natureRows]
    rows.splice(idx, 0, custom)
    rows[0] = { ...rows[0], end: { balance: 60, provision: 6 } }
    const derived = recomputeNatureDerived(rows)
    expect(derived.find((r) => r.kind === 'subtotal')!.end.balance).toBe(100)
  })

  it('方法表合计与性质合计勾稽', () => {
    const nature = buildDefaultListedState().natureRows.map((r) =>
      r.rowKey === 'other'
        ? { ...r, end: { balance: 200, provision: 20 } }
        : r,
    )
    const method = recomputeMethodTotals(
      buildDefaultListedState().methodRows.map((r) => {
        if (r.rowKey === 'individual') return { ...r, end: { balance: 50, provision: 10 } }
        if (r.rowKey === 'collective') return { ...r, end: { balance: 150, provision: 10 } }
        return r
      }),
    )
    const tie = computeNatureMethodTieOut(nature, method)
    expect(tie.matched).toBe(true)
    expect(tie.natureTotalEnd).toBe(200)
    expect(tie.methodTotalEnd).toBe(200)
  })

  it('坏账变动期末公式', () => {
    const rows = recomputeMovementClosing(
      buildDefaultListedState().movementRows.map((r) => {
        if (r.rowKey === 'opening') return { ...r, gross: 100, provision: 10 }
        if (r.rowKey === 'provision') return { ...r, gross: 0, provision: 5 }
        if (r.rowKey === 'recovery') return { ...r, gross: 0, provision: 2 }
        if (r.rowKey === 'write-off') return { ...r, gross: 10, provision: 1 }
        return r
      }),
    )
    const closing = rows.find((r) => r.rowKey === 'closing')!
    expect(closing.gross).toBe(90)
    expect(closing.provision).toBe(12)
  })

  it('组合账龄块合计自动汇总', () => {
    const aging = createAgingRows()
    aging[0].endBalance = 10
    aging[1].endBalance = 20
    aging[2].endBalance = 30
    const next = recomputeAgingTotals(aging)
    expect(next.find((r) => r.kind === 'total')!.endBalance).toBe(60)
  })

  it('同步组合名称保留已有块数据', () => {
    const a = createEmptyPortfolio('账龄组合')
    a.agingRows[0].endBalance = 99
    const b = createEmptyPortfolio('关联方组合')
    const synced = syncPortfoliosByNames([a, b], ['账龄组合', '新组合'], {
      removeMissing: false,
      markFromPolicy: true,
    })
    expect(synced.map((p) => p.name)).toEqual(
      expect.arrayContaining(['账龄组合', '新组合', '关联方组合']),
    )
    expect(synced.find((p) => p.name === '账龄组合')!.agingRows[0].endBalance).toBe(99)
    expect(synced.find((p) => p.name === '账龄组合')!.fromPolicy).toBe(true)
  })

  it('serialize/parse round-trip', () => {
    const state = buildDefaultListedState()
    state.natureRows[0].end.balance = 123
    state.portfolios[0].name = '测试组合'
    const raw = serializeListedDisclosure(state)
    const parsed = parseListedDisclosure(raw)!
    expect(parsed.natureRows[0].end.balance).toBe(123)
    expect(parsed.portfolios[0].name).toBe('测试组合')
  })

  it('从 G5-2 明细按业务类型归集', () => {
    const raw = JSON.stringify([
      { businessType: 'lease', closingBalance: 100, unrealizedIncome: 10, isRelatedParty: false },
      { businessType: 'installment', closingBalance: 50, unrealizedIncome: 5, isRelatedParty: false },
      { businessType: 'other', closingBalance: 20, isRelatedParty: true },
    ])
    const classified = classifyNatureFromDetail(raw)
    expect(classified['finance-lease']!.end.balance).toBe(100)
    expect(classified['finance-lease']!.unrealizedEnd).toBe(10)
    expect(classified['installment-goods']!.end.balance).toBe(50)
    expect(classified['related']!.end.balance).toBe(20)
  })

  it('从 G5-3 提取单项与组合', () => {
    const raw = JSON.stringify([
      { debtorOrGroup: '甲公司', provisionMethod: 'individual', adjustedBalance: 80, adjustedProvision: 40 },
      { debtorOrGroup: '账龄组合', provisionMethod: 'group', adjustedBalance: 200, adjustedProvision: 10 },
    ])
    const bad = extractBadDebtForDisclosure(raw)
    expect(bad.individual).toHaveLength(1)
    expect(bad.groupNames).toEqual(['账龄组合'])
    expect(bad.individualTotals.end.provision).toBe(40)
    expect(bad.groupTotals.end.balance).toBe(200)
  })

  it('从 G5-3 滚动态 leaf 推算期末准备（无 closingAudited）', () => {
    const raw = JSON.stringify([
      {
        category: 'individual',
        item: '债务人甲',
        openingUnadjusted: 80,
        openingAdjustment: 0,
        provisionIncrease: 20,
        otherIncrease: 0,
        reversal: 0,
        writeOff: 0,
        otherDecrease: 0,
        closingAdjustment: 0,
      },
      {
        category: 'portfolio',
        item: '账龄组合',
        openingUnadjusted: 10,
        openingAdjustment: 0,
        provisionIncrease: 5,
        otherIncrease: 0,
        reversal: 0,
        writeOff: 0,
        otherDecrease: 0,
        closingAdjustment: 0,
      },
    ])
    const bad = extractBadDebtForDisclosure(raw)
    expect(bad.individualTotals.end.provision).toBe(100)
    expect(bad.groupTotals.end.provision).toBe(15)
  })
})
