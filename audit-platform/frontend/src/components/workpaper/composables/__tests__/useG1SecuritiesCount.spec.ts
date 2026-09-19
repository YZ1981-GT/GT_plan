import { describe, it, expect } from 'vitest'
import {
  buildCountNarrative,
  calcCountTotal,
  migrateCountRow,
  headerCompleteness,
  emptyHeader,
  checkDiffReasonGaps,
  groupCountRowsByLocation,
  G1_SECURITIES_COUNT_COLUMNS,
} from '../useG1SecuritiesCount'
import { calcCountDiff } from '../useG1TraFinFormulaEngine'

describe('G1-11 监盘公式与叙述', () => {
  it('总计 = 面值 × 数量', () => {
    expect(calcCountTotal(100, 10)).toBe(1000)
    expect(calcCountTotal(12.5, 4)).toBe(50)
  })

  it('差异 = 盘点 − 账面', () => {
    expect(calcCountDiff(100, 98)).toBe(2)
    expect(calcCountDiff(90, 100)).toBe(-10)
  })

  it('由盘点头生成监盘叙述', () => {
    const text = buildCountNarrative({
      ...emptyHeader(),
      company: '甲公司',
      countDate: '2025-12-31',
      location: '财务室',
      participantCount: '3',
      observer: '张三',
      counter: '李四',
      accountingSupervisor: '王五',
      cashier: '赵六',
    })
    expect(text).toContain('3人于2025-12-31')
    expect(text).toContain('在财务室对有价证券进行盘点')
    expect(text).toContain('监盘人：张三')
  })

  it('基础信息完整度统计', () => {
    const incomplete = headerCompleteness(emptyHeader())
    expect(incomplete.filled).toBe(0)
    const ok = headerCompleteness({
      ...emptyHeader(),
      company: '甲',
      countDate: '2025-12-31',
      location: 'A',
      observer: '监',
      counter: '盘',
    })
    expect(ok.filled).toBe(5)
  })
})

describe('差异原因闸门与地点分组', () => {
  it('|差异|>0 未填原因 → 闸门命中', () => {
    const gap = migrateCountRow(
      { securityName: 'A', countedQuantity: 10, bookedQuantity: 8 },
      1,
    )
    const ok = migrateCountRow(
      { securityName: 'B', countedQuantity: 10, bookedQuantity: 8, diffReason: '在途' },
      2,
    )
    const zero = migrateCountRow(
      { securityName: 'C', countedQuantity: 5, bookedQuantity: 5 },
      3,
    )
    expect(checkDiffReasonGaps([gap, ok, zero])).toHaveLength(1)
    expect(checkDiffReasonGaps([gap, ok, zero])[0].securityName).toBe('A')
  })

  it('按盘点地点分组', () => {
    const a = migrateCountRow({ securityName: '债1', location: '财务室', countedQuantity: 1 }, 1)
    const b = migrateCountRow({ securityName: '债2', location: '托管行', countedQuantity: 2 }, 2)
    const c = migrateCountRow({ securityName: '债3', countedQuantity: 3 }, 3)
    const groups = groupCountRowsByLocation([a, b, c])
    expect(groups).toHaveLength(3)
    expect(groups.find((g) => g.location === '财务室')?.rows).toHaveLength(1)
    expect(groups.find((g) => g.location === '未指定地点')?.rows[0].securityName).toBe('债3')
  })
})

describe('migrateCountRow', () => {
  it('兼容旧版；新字段含地点并重算', () => {
    const withFace = migrateCountRow(
      {
        securityName: '企业债',
        faceValue: 100,
        countedQuantity: 10,
        bookedQuantity: 10,
        location: '托管行A',
      },
      2,
    )
    expect(withFace.total).toBe(1000)
    expect(withFace.location).toBe('托管行A')
  })
})

describe('列定义', () => {
  it('含地点与纸质盘点列', () => {
    const props = G1_SECURITIES_COUNT_COLUMNS.map((c) => c.prop)
    expect(props).toContain('location')
    expect(props).toContain('faceValue')
    expect(props).toContain('diffReason')
  })
})
