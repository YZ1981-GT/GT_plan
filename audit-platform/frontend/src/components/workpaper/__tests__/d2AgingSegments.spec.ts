import { describe, expect, it } from 'vitest'
import { agingCellValue, sumAgingBySegments } from '../composables/useD2CrossSheet'
import { PRESET_SEGMENTS } from '@/composables/useAgingConfig'

const THREE = PRESET_SEGMENTS.THREE_YEAR
const FIVE = PRESET_SEGMENTS.FIVE_YEAR

/** nested keyed 行（aging-config 迁移后的 D2-2 存储形态） */
function nestedRow(audited: Record<string, number>): Record<string, unknown> {
  return { customerName: 'A公司', agingAudited: { ...audited } }
}

/** legacy 扁平行（迁移前的 D2-2 存储形态） */
function flatRow(v: Partial<Record<string, number>>): Record<string, unknown> {
  return {
    customerName: 'B公司',
    auditedAging1Year: v.y1 ?? 0,
    auditedAging1to2: v.y1to2 ?? 0,
    auditedAging2to3: v.y2to3 ?? 0,
    auditedAging3to4: v.y3to4 ?? 0,
    auditedAging4to5: v.y4to5 ?? 0,
    auditedAgingOver5: v.over5 ?? 0,
  }
}

describe('D2 账龄枚举聚合（3年段 / 5年段 / 自定义单一口径）', () => {
  it('nested keyed 账龄优先按段 key 取值（旧实现只读扁平字段 → 全 0）', () => {
    const rows = [nestedRow({ within1: 100, y1to2: 50, y2to3: 20, over3: 5 })]
    const agg = sumAgingBySegments(rows, 'audited', THREE)
    expect(agg).toEqual({ within1: 100, y1to2: 50, y2to3: 20, over3: 5 })
  })

  it('legacy 扁平字段回退：3 年段的「3年以上」= 3-4 + 4-5 + 5年以上（旧实现恒 0）', () => {
    const rows = [flatRow({ y1: 100, y1to2: 40, y2to3: 30, y3to4: 7, y4to5: 2, over5: 1 })]
    const agg = sumAgingBySegments(rows, 'audited', THREE)
    expect(agg.within1).toBe(100)
    expect(agg.y1to2).toBe(40)
    expect(agg.y2to3).toBe(30)
    expect(agg.over3).toBe(10)
  })

  it('5 年段：nested 与 legacy 混存时逐行各取各自形态并累加', () => {
    const rows = [
      nestedRow({ within1: 10, y1to2: 0, y2to3: 0, y3to4: 3, y4to5: 0, over5: 1 }),
      flatRow({ y1: 5, y3to4: 2, over5: 4 }),
    ]
    const agg = sumAgingBySegments(rows, 'audited', FIVE)
    expect(agg.within1).toBe(15)
    expect(agg.y3to4).toBe(5)
    expect(agg.over5).toBe(5)
    expect(agg.y1to2).toBe(0)
  })

  it('自定义段：键就是自定义段 key，无对应数据时为 0（不臆造、不落到别的段）', () => {
    const custom = [
      { key: 'within1', label: '1年以内', dayFrom: 0, dayTo: 365 },
      { key: 'm13to18', label: '13-18个月', dayFrom: 366, dayTo: 548 },
    ]
    const agg = sumAgingBySegments([nestedRow({ within1: 80, m13to18: 12 })], 'audited', custom)
    expect(agg).toEqual({ within1: 80, m13to18: 12 })
    const aggNoData = sumAgingBySegments([flatRow({ y1: 80 })], 'audited', custom)
    expect(aggNoData).toEqual({ within1: 80, m13to18: 0 })
  })

  it('三个期间各读自己的容器/前缀（期初 / 期末未审 / 期末审定互不串）', () => {
    const row = {
      agingPrior: { within1: 1 },
      agingCurrent: { within1: 2 },
      agingAudited: { within1: 3 },
    }
    expect(agingCellValue(row, 'prior', 'within1')).toBe(1)
    expect(agingCellValue(row, 'current', 'within1')).toBe(2)
    expect(agingCellValue(row, 'audited', 'within1')).toBe(3)
  })

  it('nested 容器缺该段键时回退 legacy 扁平字段，两者都缺为 0', () => {
    const row = { agingAudited: { y1to2: 9 }, auditedAging1Year: 7 }
    expect(agingCellValue(row, 'audited', 'y1to2')).toBe(9)
    expect(agingCellValue(row, 'audited', 'within1')).toBe(7)
    expect(agingCellValue(row, 'audited', 'y4to5')).toBe(0)
    expect(agingCellValue({}, 'audited', 'unknown-seg')).toBe(0)
  })

  it('空行集返回按段初始化的全零（键齐备，便于表格渲染）', () => {
    expect(sumAgingBySegments([], 'audited', THREE)).toEqual({
      within1: 0, y1to2: 0, y2to3: 0, over3: 0,
    })
  })
})
