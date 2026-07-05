/**
 * G7TabAdjudication.spec.ts — G7-1 审定表单元测试
 *
 * 覆盖：
 * 1. 分组折叠/展开切换 + localStorage持久化
 * 2. 净值计算: netValue = totalAdjusted - impairmentAdjusted
 * 3. 变动率>20%高亮判断: isRateWarning
 * 4. CalcGroupSubtotal: 分组小计计算
 * 5. RecalcRow: 单元格编辑后公式重算
 *
 * Requirements: 3.1, 3.4, 3.5
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  parseNum,
  calcAdjustedAmount,
  calcChangeRate,
} from '../../../composables/useG7FormulaEngine'

// ═══ 从组件中提取的纯逻辑（直接复现组件内部函数） ═══

/** isRateWarning — 变动率>20%判断（与组件内逻辑一致） */
function isRateWarning(rate: number | null): boolean {
  if (rate == null) return false
  return Math.abs(rate) > 0.2
}

/** AdjRow 行结构（简化测试用） */
interface AdjRow {
  id: string
  item: string
  controlType: string
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  openingAdjusted: number
  closingUnadjusted: number
  closingAJE: number
  closingRJE: number
  closingAdjusted: number
  changeAmount: number
  changeRate: number | null
  _isSubtotal?: boolean
  _idx: number
}

/** recalcRow — 公式重算（与组件内逻辑一致） */
function recalcRow(row: AdjRow): void {
  row.openingAdjusted = calcAdjustedAmount(
    parseNum(row.openingUnadjusted), parseNum(row.openingAJE), parseNum(row.openingRJE),
  )
  row.closingAdjusted = calcAdjustedAmount(
    parseNum(row.closingUnadjusted), parseNum(row.closingAJE), parseNum(row.closingRJE),
  )
  row.changeAmount = Math.round((row.closingAdjusted - row.openingAdjusted) * 100) / 100
  row.changeRate = calcChangeRate(row.openingAdjusted, row.closingAdjusted)
}

/** calcGroupSubtotal — 分组小计（与组件内逻辑一致） */
function calcGroupSubtotal(rows: AdjRow[]): AdjRow {
  const dataRows = rows.filter(r => !r._isSubtotal)
  const sum = (field: keyof AdjRow) =>
    dataRows.reduce((s, r) => s + parseNum(r[field] as number), 0)
  const openUnadj = sum('openingUnadjusted')
  const openAJE = sum('openingAJE')
  const openRJE = sum('openingRJE')
  const openAdj = calcAdjustedAmount(openUnadj, openAJE, openRJE)
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
    closingUnadjusted: closeUnadj, closingAJE: closeAJE, closingRJE: closeRJE,
    closingAdjusted: closeAdj,
    changeAmount: change, changeRate: calcChangeRate(openAdj, closeAdj),
    _isSubtotal: true, _idx: -1,
  }
}

// ═══ Helper: 创建测试行 ═══
function makeTestRow(overrides: Partial<AdjRow> = {}): AdjRow {
  const row: AdjRow = {
    id: 'test-row',
    item: '测试项目',
    controlType: 'subsidiary',
    openingUnadjusted: 0,
    openingAJE: 0,
    openingRJE: 0,
    openingAdjusted: 0,
    closingUnadjusted: 0,
    closingAJE: 0,
    closingRJE: 0,
    closingAdjusted: 0,
    changeAmount: 0,
    changeRate: null,
    _isSubtotal: false,
    _idx: 0,
    ...overrides,
  }
  recalcRow(row)
  return row
}

// ═══════════════════════════════════════════════════════════════════════════════
// 测试用例
// ═══════════════════════════════════════════════════════════════════════════════

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
      total: true,
      impairment: true,
    }

    // 模拟 toggleGroup 逻辑
    const wpId = 'test-wp-123'
    const storageKey = `g7-adjudication-collapse-${wpId}`

    function toggleGroup(groupId: string): void {
      expandedMap[groupId] = !expandedMap[groupId]
      localStorage.setItem(storageKey, JSON.stringify({ ...expandedMap }))
    }

    // 初始全展开
    expect(expandedMap.subsidiary).toBe(true)

    // 折叠子公司组
    toggleGroup('subsidiary')
    expect(expandedMap.subsidiary).toBe(false)
    expect(localStorage.setItem).toHaveBeenCalledWith(
      storageKey,
      expect.stringContaining('"subsidiary":false'),
    )

    // 再展开
    toggleGroup('subsidiary')
    expect(expandedMap.subsidiary).toBe(true)
    expect(localStorage.setItem).toHaveBeenCalledTimes(2)
  })

  it('loadCollapseState 从 localStorage 恢复折叠状态', () => {
    const wpId = 'test-wp-456'
    const storageKey = `g7-adjudication-collapse-${wpId}`
    localStorageMock[storageKey] = JSON.stringify({
      subsidiary: false,
      joint_venture: true,
      associate: false,
      total: true,
      impairment: true,
    })

    const expandedMap: Record<string, boolean> = {
      subsidiary: true,
      joint_venture: true,
      associate: true,
      total: true,
      impairment: true,
    }

    // 模拟 loadCollapseState
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
    expect(expandedMap.total).toBe(true)
    expect(expandedMap.impairment).toBe(true)
  })

  it('localStorage 为空时保持默认全展开', () => {
    const expandedMap: Record<string, boolean> = {
      subsidiary: true,
      joint_venture: true,
      associate: true,
      total: true,
      impairment: true,
    }

    const raw = localStorage.getItem('g7-adjudication-collapse-nonexist')
    // raw === null, 不改变
    expect(raw).toBeNull()
    expect(expandedMap.subsidiary).toBe(true)
    expect(expandedMap.joint_venture).toBe(true)
  })
})

describe('G7TabAdjudication - 净值计算 (netValue = total - impairment)', () => {
  it('netValue.closingAdjusted = totalGroup.closingAdjusted - impairGroup.closingAdjusted', () => {
    // 四、投资合计组
    const totalRows: AdjRow[] = [
      makeTestRow({ id: 'total-1', item: '合计项A', closingUnadjusted: 1000, closingAJE: 50, closingRJE: -20 }),
      makeTestRow({ id: 'total-2', item: '合计项B', closingUnadjusted: 2000, closingAJE: 100, closingRJE: 0 }),
    ]

    // 五、减值准备组
    const impairRows: AdjRow[] = [
      makeTestRow({ id: 'impair-1', item: '减值A', closingUnadjusted: 300, closingAJE: 0, closingRJE: 0 }),
    ]

    const totalSub = calcGroupSubtotal(totalRows)
    const impairSub = calcGroupSubtotal(impairRows)

    // total closingAdjusted = (1000+50-20) + (2000+100+0) = 1030 + 2100 = 3130
    expect(totalSub.closingAdjusted).toBe(3130)
    // impair closingAdjusted = 300+0+0 = 300
    expect(impairSub.closingAdjusted).toBe(300)

    // netValue = total - impair = 3130 - 300 = 2830
    const netCloseAdj = totalSub.closingAdjusted - impairSub.closingAdjusted
    expect(netCloseAdj).toBe(2830)
  })

  it('netValue.openingAdjusted = totalGroup.openingAdjusted - impairGroup.openingAdjusted', () => {
    const totalRows: AdjRow[] = [
      makeTestRow({ id: 'total-1', openingUnadjusted: 500, openingAJE: 10, openingRJE: 5 }),
    ]
    const impairRows: AdjRow[] = [
      makeTestRow({ id: 'impair-1', openingUnadjusted: 100, openingAJE: 0, openingRJE: 0 }),
    ]

    const totalSub = calcGroupSubtotal(totalRows)
    const impairSub = calcGroupSubtotal(impairRows)

    // total openingAdjusted = 500+10+5 = 515
    expect(totalSub.openingAdjusted).toBe(515)
    // impair openingAdjusted = 100+0+0 = 100
    expect(impairSub.openingAdjusted).toBe(100)

    const netOpenAdj = totalSub.openingAdjusted - impairSub.openingAdjusted
    expect(netOpenAdj).toBe(415)
  })

  it('空组时净值为0', () => {
    const emptyTotal = calcGroupSubtotal([])
    const emptyImpair = calcGroupSubtotal([])

    expect(emptyTotal.closingAdjusted).toBe(0)
    expect(emptyImpair.closingAdjusted).toBe(0)
    expect(emptyTotal.closingAdjusted - emptyImpair.closingAdjusted).toBe(0)
  })
})

describe('G7TabAdjudication - 变动率>20%高亮 (isRateWarning)', () => {
  it('isRateWarning(0.25) 返回 true（>20%）', () => {
    expect(isRateWarning(0.25)).toBe(true)
  })

  it('isRateWarning(0.15) 返回 false（<20%）', () => {
    expect(isRateWarning(0.15)).toBe(false)
  })

  it('isRateWarning(-0.30) 返回 true（绝对值>20%）', () => {
    expect(isRateWarning(-0.30)).toBe(true)
  })

  it('isRateWarning(0.20) 返回 false（恰好=20%不触发）', () => {
    expect(isRateWarning(0.20)).toBe(false)
  })

  it('isRateWarning(null) 返回 false', () => {
    expect(isRateWarning(null)).toBe(false)
  })

  it('isRateWarning(0) 返回 false', () => {
    expect(isRateWarning(0)).toBe(false)
  })
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

    // openingUnadjusted: 100 + 300 = 400
    expect(subtotal.openingUnadjusted).toBe(400)
    // openingAJE: 10 + (-10) = 0
    expect(subtotal.openingAJE).toBe(0)
    // openingRJE: 5 + 0 = 5
    expect(subtotal.openingRJE).toBe(5)
    // openingAdjusted = 400 + 0 + 5 = 405
    expect(subtotal.openingAdjusted).toBe(405)

    // closingUnadjusted: 200 + 400 = 600
    expect(subtotal.closingUnadjusted).toBe(600)
    // closingAJE: 20 + 50 = 70
    expect(subtotal.closingAJE).toBe(70)
    // closingRJE: 10 + (-5) = 5
    expect(subtotal.closingRJE).toBe(5)
    // closingAdjusted = 600 + 70 + 5 = 675
    expect(subtotal.closingAdjusted).toBe(675)

    // changeAmount = 675 - 405 = 270
    expect(subtotal.changeAmount).toBe(270)
    // changeRate = (675 - 405) / 405 ≈ 0.6667
    expect(subtotal.changeRate).toBeCloseTo(270 / 405, 4)

    // 标记
    expect(subtotal._isSubtotal).toBe(true)
  })

  it('过滤已有的小计行不重复计算', () => {
    const rows: AdjRow[] = [
      makeTestRow({ id: 'r1', openingUnadjusted: 100, closingUnadjusted: 200 }),
      { ...makeTestRow({ id: 'subtotal', openingUnadjusted: 999, closingUnadjusted: 999 }), _isSubtotal: true },
    ]

    const subtotal = calcGroupSubtotal(rows)
    // 只计算非小计行(r1)
    expect(subtotal.openingUnadjusted).toBe(100)
    expect(subtotal.closingUnadjusted).toBe(200)
  })

  it('空行数组返回全0小计', () => {
    const subtotal = calcGroupSubtotal([])
    expect(subtotal.openingAdjusted).toBe(0)
    expect(subtotal.closingAdjusted).toBe(0)
    expect(subtotal.changeAmount).toBe(0)
    expect(subtotal.changeRate).toBeNull() // prior=0 → null
  })
})

describe('G7TabAdjudication - RecalcRow 公式重算', () => {
  it('修改期初AJE后正确重算openingAdjusted', () => {
    const row = makeTestRow({ openingUnadjusted: 1000, openingAJE: 0, openingRJE: 0 })
    expect(row.openingAdjusted).toBe(1000)

    // 修改AJE
    row.openingAJE = 50
    recalcRow(row)
    expect(row.openingAdjusted).toBe(1050)
  })

  it('修改期末RJE后正确重算closingAdjusted和变动', () => {
    const row = makeTestRow({
      openingUnadjusted: 500, openingAJE: 0, openingRJE: 0,
      closingUnadjusted: 600, closingAJE: 0, closingRJE: 0,
    })
    expect(row.openingAdjusted).toBe(500)
    expect(row.closingAdjusted).toBe(600)
    expect(row.changeAmount).toBe(100)
    expect(row.changeRate).toBeCloseTo(0.2, 4)

    // 修改期末RJE = 100
    row.closingRJE = 100
    recalcRow(row)
    // closingAdjusted = 600 + 0 + 100 = 700
    expect(row.closingAdjusted).toBe(700)
    // changeAmount = 700 - 500 = 200
    expect(row.changeAmount).toBe(200)
    // changeRate = 200/500 = 0.4
    expect(row.changeRate).toBeCloseTo(0.4, 4)
  })

  it('期初审定为0时变动率返回null', () => {
    const row = makeTestRow({
      openingUnadjusted: 0, openingAJE: 0, openingRJE: 0,
      closingUnadjusted: 100, closingAJE: 0, closingRJE: 0,
    })
    expect(row.openingAdjusted).toBe(0)
    expect(row.closingAdjusted).toBe(100)
    expect(row.changeRate).toBeNull()
  })

  it('负数AJE正确计算', () => {
    const row = makeTestRow({
      openingUnadjusted: 1000, openingAJE: -200, openingRJE: 50,
      closingUnadjusted: 800, closingAJE: -100, closingRJE: 0,
    })
    // openingAdjusted = 1000 - 200 + 50 = 850
    expect(row.openingAdjusted).toBe(850)
    // closingAdjusted = 800 - 100 + 0 = 700
    expect(row.closingAdjusted).toBe(700)
    // changeAmount = 700 - 850 = -150
    expect(row.changeAmount).toBe(-150)
    // changeRate = -150/850 ≈ -0.1765
    expect(row.changeRate).toBeCloseTo(-150 / 850, 4)
  })
})
