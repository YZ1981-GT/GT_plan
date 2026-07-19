/**
 * G7TabAdjudication.spec.ts — G7-1 审定表单元测试
 *
 * 覆盖：
 * 1. 分组折叠/展开切换 + localStorage持久化
 * 2. 净值计算: netValue = investmentTotal - impairment
 * 3. 投资合计自动汇总: total = subsidiary + JV + associate
 * 4. 变动率>20%高亮判断: isRateWarning
 * 5. CalcGroupSubtotal / RecalcRow（含借贷推算期末未审）
 * 6. TB 勾稽三口径: 1511原值 / 1512减值 / 净值
 *
 * Requirements: 3.1, 3.4, 3.5
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  parseNum,
  calcAdjustedAmount,
  calcChangeRate,
  calcDebitBalance,
} from '../../../composables/useG7FormulaEngine'

/** isRateWarning — 变动率>20%判断 */
function isRateWarning(rate: number | null): boolean {
  if (rate == null) return false
  return Math.abs(rate) > 0.2
}

interface AdjRow {
  id: string
  item: string
  controlType: string
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  openingAdjusted: number
  debitAmount: number
  creditAmount: number
  closingUnadjusted: number
  closingAJE: number
  closingRJE: number
  closingAdjusted: number
  changeAmount: number
  changeRate: number | null
  varianceNote: string
  _autoClosing?: boolean
  _isSubtotal?: boolean
  _idx: number
}

function recalcRow(row: AdjRow): void {
  row.openingAdjusted = calcAdjustedAmount(
    parseNum(row.openingUnadjusted), parseNum(row.openingAJE), parseNum(row.openingRJE),
  )
  const debit = parseNum(row.debitAmount)
  const credit = parseNum(row.creditAmount)
  if (debit !== 0 || credit !== 0) {
    row.closingUnadjusted = calcDebitBalance(row.openingAdjusted, debit, credit)
    row._autoClosing = true
  } else {
    row._autoClosing = false
  }
  row.closingAdjusted = calcAdjustedAmount(
    parseNum(row.closingUnadjusted), parseNum(row.closingAJE), parseNum(row.closingRJE),
  )
  row.changeAmount = Math.round((row.closingAdjusted - row.openingAdjusted) * 100) / 100
  row.changeRate = calcChangeRate(row.openingAdjusted, row.closingAdjusted)
}

function calcGroupSubtotal(rows: AdjRow[]): AdjRow {
  const dataRows = rows.filter(r => !r._isSubtotal)
  const sum = (field: keyof AdjRow) =>
    dataRows.reduce((s, r) => s + parseNum(r[field] as number), 0)
  const openUnadj = sum('openingUnadjusted')
  const openAJE = sum('openingAJE')
  const openRJE = sum('openingRJE')
  const openAdj = calcAdjustedAmount(openUnadj, openAJE, openRJE)
  const debit = sum('debitAmount')
  const credit = sum('creditAmount')
  const closeUnadj = sum('closingUnadjusted')
  const closeAJE = sum('closingAJE')
  const closeRJE = sum('closingRJE')
  const closeAdj = calcAdjustedAmount(closeUnadj, closeAJE, closeRJE)
  const change = Math.round((closeAdj - openAdj) * 100) / 100
  return {
    id: 'subtotal', item: '小计',
    controlType: '',
    openingUnadjusted: openUnadj, openingAJE: openAJE, openingRJE: openRJE,
    openingAdjusted: openAdj,
    debitAmount: debit, creditAmount: credit,
    closingUnadjusted: closeUnadj, closingAJE: closeAJE, closingRJE: closeRJE,
    closingAdjusted: closeAdj,
    changeAmount: change, changeRate: calcChangeRate(openAdj, closeAdj),
    varianceNote: '',
    _isSubtotal: true, _idx: -1,
  }
}

/** 投资合计 = 三组小计之和（不可编辑） */
function calcInvestmentTotal(subRows: AdjRow[], jvRows: AdjRow[], assocRows: AdjRow[]): AdjRow {
  const sub = calcGroupSubtotal(subRows)
  const jv = calcGroupSubtotal(jvRows)
  const assoc = calcGroupSubtotal(assocRows)
  const openAdj = sub.openingAdjusted + jv.openingAdjusted + assoc.openingAdjusted
  const closeAdj = sub.closingAdjusted + jv.closingAdjusted + assoc.closingAdjusted
  return {
    id: 'investment-total', item: '投资合计',
    controlType: '',
    openingUnadjusted: sub.openingUnadjusted + jv.openingUnadjusted + assoc.openingUnadjusted,
    openingAJE: sub.openingAJE + jv.openingAJE + assoc.openingAJE,
    openingRJE: sub.openingRJE + jv.openingRJE + assoc.openingRJE,
    openingAdjusted: openAdj,
    debitAmount: 0, creditAmount: 0,
    closingUnadjusted: sub.closingUnadjusted + jv.closingUnadjusted + assoc.closingUnadjusted,
    closingAJE: sub.closingAJE + jv.closingAJE + assoc.closingAJE,
    closingRJE: sub.closingRJE + jv.closingRJE + assoc.closingRJE,
    closingAdjusted: closeAdj,
    changeAmount: Math.round((closeAdj - openAdj) * 100) / 100,
    changeRate: calcChangeRate(openAdj, closeAdj),
    varianceNote: '',
    _isSubtotal: true, _idx: -1,
  }
}

function makeTestRow(overrides: Partial<AdjRow> = {}): AdjRow {
  const row: AdjRow = {
    id: 'test-row',
    item: '测试项目',
    controlType: 'subsidiary',
    openingUnadjusted: 0,
    openingAJE: 0,
    openingRJE: 0,
    openingAdjusted: 0,
    debitAmount: 0,
    creditAmount: 0,
    closingUnadjusted: 0,
    closingAJE: 0,
    closingRJE: 0,
    closingAdjusted: 0,
    changeAmount: 0,
    changeRate: null,
    varianceNote: '',
    _isSubtotal: false,
    _idx: 0,
    ...overrides,
  }
  recalcRow(row)
  return row
}

describe('G7TabAdjudication - 分组折叠/展开切换', () => {
  let localStorageMock: Record<string, string>

  beforeEach(() => {
    localStorageMock = {}
    vi.stubGlobal('localStorage', {
      getItem: vi.fn((key: string) => localStorageMock[key] ?? null),
      setItem: vi.fn((key: string, val: string) => { localStorageMock[key] = val }),
      removeItem: vi.fn((key: string) => { delete localStorageMock[key] }),
    })
  })

  it('toggleGroup 切换 expandedMap 状态（展开→折叠）', () => {
    const expandedMap: Record<string, boolean> = {
      subsidiary: true,
      joint_venture: true,
      associate: true,
      impairment: true,
    }
    const wpId = 'test-wp-123'
    const storageKey = `g7-adjudication-collapse-${wpId}`

    function toggleGroup(groupId: string): void {
      expandedMap[groupId] = !expandedMap[groupId]
      localStorage.setItem(storageKey, JSON.stringify({ ...expandedMap }))
    }

    expect(expandedMap.subsidiary).toBe(true)
    toggleGroup('subsidiary')
    expect(expandedMap.subsidiary).toBe(false)
    expect(localStorage.setItem).toHaveBeenCalledWith(
      storageKey,
      expect.stringContaining('"subsidiary":false'),
    )
    toggleGroup('subsidiary')
    expect(expandedMap.subsidiary).toBe(true)
  })

  it('loadCollapseState 从 localStorage 恢复折叠状态', () => {
    const wpId = 'test-wp-456'
    const storageKey = `g7-adjudication-collapse-${wpId}`
    localStorageMock[storageKey] = JSON.stringify({
      subsidiary: false,
      joint_venture: true,
      associate: false,
      impairment: true,
    })

    const expandedMap: Record<string, boolean> = {
      subsidiary: true,
      joint_venture: true,
      associate: true,
      impairment: true,
    }

    const raw = localStorage.getItem(storageKey)
    if (raw) {
      const saved = JSON.parse(raw)
      for (const key of Object.keys(expandedMap)) {
        if (key in saved) expandedMap[key] = saved[key]
      }
    }

    expect(expandedMap.subsidiary).toBe(false)
    expect(expandedMap.joint_venture).toBe(true)
    expect(expandedMap.associate).toBe(false)
  })
})

describe('G7TabAdjudication - 投资合计自动汇总', () => {
  it('investmentTotal = subsidiary + JV + associate', () => {
    const sub = [makeTestRow({ closingUnadjusted: 1000, closingAJE: 0, closingRJE: 0 })]
    const jv = [makeTestRow({ closingUnadjusted: 200, closingAJE: 10, closingRJE: 0 })]
    const assoc = [makeTestRow({ closingUnadjusted: 300, closingAJE: 0, closingRJE: -5 })]
    const total = calcInvestmentTotal(sub, jv, assoc)
    // 1000 + (200+10) + (300-5) = 1000+210+295 = 1505
    expect(total.closingAdjusted).toBe(1505)
  })

  it('空组时投资合计为0', () => {
    expect(calcInvestmentTotal([], [], []).closingAdjusted).toBe(0)
  })
})

describe('G7TabAdjudication - 净值计算 (netValue = total - impairment)', () => {
  it('netValue.closingAdjusted = investmentTotal - impair', () => {
    const sub = [makeTestRow({ closingUnadjusted: 1000, closingAJE: 50, closingRJE: -20 })]
    const jv = [makeTestRow({ closingUnadjusted: 2000, closingAJE: 100, closingRJE: 0 })]
    const total = calcInvestmentTotal(sub, jv, [])
    const impair = calcGroupSubtotal([
      makeTestRow({ closingUnadjusted: 300, closingAJE: 0, closingRJE: 0 }),
    ])
    // total = (1000+50-20) + (2000+100) = 1030+2100 = 3130
    expect(total.closingAdjusted).toBe(3130)
    expect(impair.closingAdjusted).toBe(300)
    expect(total.closingAdjusted - impair.closingAdjusted).toBe(2830)
  })

  it('netValue.openingAdjusted = total - impair', () => {
    const total = calcInvestmentTotal(
      [makeTestRow({ openingUnadjusted: 500, openingAJE: 10, openingRJE: 5 })],
      [],
      [],
    )
    const impair = calcGroupSubtotal([
      makeTestRow({ openingUnadjusted: 100, openingAJE: 0, openingRJE: 0 }),
    ])
    expect(total.openingAdjusted).toBe(515)
    expect(impair.openingAdjusted).toBe(100)
    expect(total.openingAdjusted - impair.openingAdjusted).toBe(415)
  })
})

describe('G7TabAdjudication - TB 勾稽三口径', () => {
  it('varianceGross = investmentTotal - TB1511', () => {
    const total = calcInvestmentTotal(
      [makeTestRow({ closingUnadjusted: 1000 })],
      [],
      [],
    )
    const tb1511 = 1000
    expect(Math.round((total.closingAdjusted - tb1511) * 100) / 100).toBe(0)
  })

  it('varianceNet = netValue - (TB1511 - TB1512)', () => {
    const total = calcInvestmentTotal(
      [makeTestRow({ closingUnadjusted: 1000 })],
      [],
      [],
    )
    const impair = calcGroupSubtotal([makeTestRow({ closingUnadjusted: 100 })])
    const net = total.closingAdjusted - impair.closingAdjusted
    const tbNet = 1000 - 100
    expect(net - tbNet).toBe(0)
  })

  it('回写口径：1511=投资合计原值（非净值）', () => {
    const total = calcInvestmentTotal(
      [makeTestRow({ closingUnadjusted: 1000 })],
      [],
      [],
    )
    const impair = calcGroupSubtotal([makeTestRow({ closingUnadjusted: 100 })])
    const writeback1511 = total.closingAdjusted
    const writeback1512 = impair.closingAdjusted
    expect(writeback1511).toBe(1000)
    expect(writeback1512).toBe(100)
    expect(writeback1511).not.toBe(total.closingAdjusted - impair.closingAdjusted)
  })
})

describe('G7TabAdjudication - 变动率>20%高亮 (isRateWarning)', () => {
  it('isRateWarning(0.25) 返回 true', () => expect(isRateWarning(0.25)).toBe(true))
  it('isRateWarning(0.15) 返回 false', () => expect(isRateWarning(0.15)).toBe(false))
  it('isRateWarning(-0.30) 返回 true', () => expect(isRateWarning(-0.30)).toBe(true))
  it('isRateWarning(0.20) 返回 false', () => expect(isRateWarning(0.20)).toBe(false))
  it('isRateWarning(null) 返回 false', () => expect(isRateWarning(null)).toBe(false))
})

describe('G7TabAdjudication - CalcGroupSubtotal 分组小计', () => {
  it('正确汇总多行数据', () => {
    const rows: AdjRow[] = [
      makeTestRow({
        id: 'r1', openingUnadjusted: 100, openingAJE: 10, openingRJE: 5,
        closingUnadjusted: 200, closingAJE: 20, closingRJE: 10,
      }),
      makeTestRow({
        id: 'r2', openingUnadjusted: 300, openingAJE: -10, openingRJE: 0,
        closingUnadjusted: 400, closingAJE: 50, closingRJE: -5,
      }),
    ]
    const subtotal = calcGroupSubtotal(rows)
    expect(subtotal.openingUnadjusted).toBe(400)
    expect(subtotal.openingAJE).toBe(0)
    expect(subtotal.openingRJE).toBe(5)
    expect(subtotal.openingAdjusted).toBe(405)
    expect(subtotal.closingUnadjusted).toBe(600)
    expect(subtotal.closingAJE).toBe(70)
    expect(subtotal.closingRJE).toBe(5)
    expect(subtotal.closingAdjusted).toBe(675)
    expect(subtotal.changeAmount).toBe(270)
    expect(subtotal.changeRate).toBeCloseTo(270 / 405, 4)
    expect(subtotal._isSubtotal).toBe(true)
  })

  it('过滤已有的小计行不重复计算', () => {
    const rows: AdjRow[] = [
      makeTestRow({ id: 'r1', openingUnadjusted: 100, closingUnadjusted: 200 }),
      { ...makeTestRow({ id: 'subtotal', openingUnadjusted: 999, closingUnadjusted: 999 }), _isSubtotal: true },
    ]
    const subtotal = calcGroupSubtotal(rows)
    expect(subtotal.openingUnadjusted).toBe(100)
    expect(subtotal.closingUnadjusted).toBe(200)
  })
})

describe('G7TabAdjudication - RecalcRow 公式重算', () => {
  it('修改期初AJE后正确重算openingAdjusted', () => {
    const row = makeTestRow({ openingUnadjusted: 1000, openingAJE: 0, openingRJE: 0 })
    expect(row.openingAdjusted).toBe(1000)
    row.openingAJE = 50
    recalcRow(row)
    expect(row.openingAdjusted).toBe(1050)
  })

  it('填写借贷后自动推算期末未审', () => {
    const row = makeTestRow({
      openingUnadjusted: 500, openingAJE: 0, openingRJE: 0,
      debitAmount: 200, creditAmount: 50,
    })
    // 期末未审 = 500 + 200 - 50 = 650
    expect(row._autoClosing).toBe(true)
    expect(row.closingUnadjusted).toBe(650)
    expect(row.closingAdjusted).toBe(650)
  })

  it('无借贷时可手填期末未审', () => {
    const row = makeTestRow({
      openingUnadjusted: 500,
      closingUnadjusted: 600,
    })
    expect(row._autoClosing).toBe(false)
    expect(row.closingUnadjusted).toBe(600)
  })

  it('修改期末RJE后正确重算closingAdjusted和变动', () => {
    const row = makeTestRow({
      openingUnadjusted: 500, openingAJE: 0, openingRJE: 0,
      closingUnadjusted: 600, closingAJE: 0, closingRJE: 0,
    })
    row.closingRJE = 100
    recalcRow(row)
    expect(row.closingAdjusted).toBe(700)
    expect(row.changeAmount).toBe(200)
    expect(row.changeRate).toBeCloseTo(0.4, 4)
  })

  it('期初审定为0时变动率返回null', () => {
    const row = makeTestRow({
      openingUnadjusted: 0,
      closingUnadjusted: 100,
    })
    expect(row.changeRate).toBeNull()
  })

  it('负数AJE正确计算', () => {
    const row = makeTestRow({
      openingUnadjusted: 1000, openingAJE: -200, openingRJE: 50,
      closingUnadjusted: 800, closingAJE: -100, closingRJE: 0,
    })
    expect(row.openingAdjusted).toBe(850)
    expect(row.closingAdjusted).toBe(700)
    expect(row.changeAmount).toBe(-150)
    expect(row.changeRate).toBeCloseTo(-150 / 850, 4)
  })
})
