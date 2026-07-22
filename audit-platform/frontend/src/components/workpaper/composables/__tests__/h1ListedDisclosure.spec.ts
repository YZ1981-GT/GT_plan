/**
 * H1 上市披露模型 / 同步载荷 — 单元测试
 */
import { describe, expect, it } from 'vitest'
import {
  cellValue,
  createDefaultSummary,
  formatGovSubsidyLine,
  idleBookValue,
  isMovementEmpty,
  seedMovementFromAdjudication,
  setCell,
  summaryTotal,
  totalCellValue,
  sumFullyDep,
  deriveFullyDepreciatedFromDetail,
  H1_LISTED_DEFAULT_CATEGORIES,
  H1_LISTED_MOVEMENT_ROWS,
} from '../h1ListedDisclosureModel'
import {
  buildH1ListedSubTableData,
  buildH1ListedSyncPayloads,
} from '../h1DisclosureSyncPayload'
import { H1_LISTED_SUBTABLE, H1_NOTE_SECTION } from '../h1NoteSectionMap'

describe('h1ListedDisclosureModel — 已提足折旧仍在使用', () => {
  it('sumFullyDep sums original cost', () => {
    expect(sumFullyDep([
      { rowId: 'a', name: '房屋', cost: 100, remark: '' },
      { rowId: 'b', name: '设备', cost: 250, remark: '' },
    ])).toBeCloseTo(350)
  })

  it('deriveFullyDepreciatedFromDetail groups fully-depreciated assets by category', () => {
    const rows = [
      // 已提足：净值0（残值0），在用 → 计入
      { category: '机器设备', originalCostEnd: 500_000, accDepEnd: 500_000, impairmentEnd: 0 },
      // 已提足：净值=残值5%以内 → 计入（同类累加）
      { category: '机器设备', originalCostEnd: 100_000, accDepEnd: 96_000, impairmentEnd: 0 },
      // 未提足：净值远高于残值 → 排除
      { category: '运输设备', originalCostEnd: 800_000, accDepEnd: 200_000, impairmentEnd: 0 },
      // 无累计折旧 → 排除
      { category: '办公设备', originalCostEnd: 10_000, accDepEnd: 0, impairmentEnd: 0 },
    ]
    const res = deriveFullyDepreciatedFromDetail(rows)
    expect(res).toHaveLength(1)
    expect(res[0].name).toBe('机器设备')
    expect(res[0].cost).toBeCloseTo(600_000) // 500k + 100k 账面原值
  })

  it('deriveFullyDepreciatedFromDetail respects residualRate option', () => {
    const rows = [
      { category: '设备', originalCostEnd: 100_000, accDepEnd: 88_000, impairmentEnd: 0 }, // 净值12% 
    ]
    expect(deriveFullyDepreciatedFromDetail(rows)).toHaveLength(0) // 默认5%阈值 → 排除
    expect(deriveFullyDepreciatedFromDetail(rows, { residualRate: 0.15 })).toHaveLength(1) // 15%阈值 → 计入
  })
})

describe('h1ListedDisclosureModel', () => {
  const cats = H1_LISTED_DEFAULT_CATEGORIES.map((c) => ({ ...c }))
  const costEnd = H1_LISTED_MOVEMENT_ROWS.find((d) => d.key === 'cost_end')!
  const bookEnd = H1_LISTED_MOVEMENT_ROWS.find((d) => d.key === 'book_end')!
  const costInc = H1_LISTED_MOVEMENT_ROWS.find((d) => d.key === 'cost_inc')!

  it('期末 = 期初 + 增加 − 减少', () => {
    let map = {}
    map = setCell(map, 'cost_begin', 'buildings', 1000)
    map = setCell(map, 'cost_inc_purchase', 'buildings', 200)
    map = setCell(map, 'cost_inc_cip', 'buildings', 50)
    map = setCell(map, 'cost_dec_dispose', 'buildings', 100)
    expect(cellValue(map, costEnd, 'buildings')).toBe(1150)
    expect(cellValue(map, costInc, 'buildings')).toBe(250)
  })

  it('账面价值 = 原值 − 折旧 − 减值', () => {
    let map = {}
    map = setCell(map, 'cost_begin', 'machinery', 500)
    map = setCell(map, 'dep_begin', 'machinery', 100)
    map = setCell(map, 'imp_begin', 'machinery', 20)
    // book_begin uses begin rows
    const bookBegin = H1_LISTED_MOVEMENT_ROWS.find((d) => d.key === 'book_begin')!
    expect(cellValue(map, bookBegin, 'machinery')).toBe(380)
  })

  it('合计列汇总各类', () => {
    let map = {}
    map = setCell(map, 'cost_begin', 'buildings', 100)
    map = setCell(map, 'cost_begin', 'machinery', 200)
    map = setCell(map, 'cost_begin', 'transport', 50)
    const begin = H1_LISTED_MOVEMENT_ROWS.find((d) => d.key === 'cost_begin')!
    expect(totalCellValue(map, begin, cats)).toBe(350)
  })

  it('idleBookValue / summaryTotal / formatGovSubsidyLine', () => {
    expect(idleBookValue({ cost: 100, dep: 30, impairment: 10 })).toBe(60)
    expect(summaryTotal(createDefaultSummary())).toEqual({ endBalance: 0, priorBalance: 0 })
    expect(formatGovSubsidyLine(1234.5)).toContain('1,234.50')
    expect(formatGovSubsidyLine(0, '自定义文本')).toBe('自定义文本')
  })

  it('seedMovementFromAdjudication 映射分类', () => {
    const { categories, movement } = seedMovementFromAdjudication(
      [{ category: '房屋及建筑物', beginBalance: 10, debit: 2, credit: 1, endBalance: 11 }],
      [{ category: '房屋及建筑物', beginBalance: 3, debit: 0.5, credit: 1, endBalance: 3.5 }],
      cats,
    )
    expect(isMovementEmpty(movement)).toBe(false)
    expect(categories.some((c) => c.label === '房屋及建筑物')).toBe(true)
    expect(cellValue(movement, costEnd, 'buildings')).toBe(11)
  })
})

describe('h1DisclosureSyncPayload', () => {
  it('buildH1ListedSubTableData 含全部子表名', () => {
    const snap = {
      summary: createDefaultSummary(),
      categories: H1_LISTED_DEFAULT_CATEGORIES.map((c) => ({ ...c })),
      movement: setCell({}, 'cost_begin', 'buildings', 100),
      idle: [{ rowId: '1', name: '房屋及建筑物', cost: 10, dep: 2, impairment: 0, bookValue: 8, remark: '' }],
      leaseOut: [{ rowId: '1', name: '机器设备', bookValue: 5 }],
      titleCert: [{ rowId: '1', name: '厂房A', bookValue: 9, reason: '在办' }],
      clearing: [{ rowId: '1', name: '设备报废', endBalance: 1, priorBalance: 0, reason: '报废' }],
      govSubsidy: { amount: 100, text: '' },
      noteImpairment: '已执行减值测试',
      noteMortgage: '',
      noteSale: '',
      noteClearing: '无超1年清理',
    }
    const data = buildH1ListedSubTableData(snap)
    expect(data[H1_LISTED_SUBTABLE.summary]?.length).toBeGreaterThanOrEqual(3)
    expect(data[H1_LISTED_SUBTABLE.movement]?.length).toBeGreaterThan(10)
    expect(data[H1_LISTED_SUBTABLE.idle]?.some((r) => r.is_total)).toBe(true)
    expect(data[H1_LISTED_SUBTABLE.leaseOut]?.[0].book_value).toBe(5)
    expect(data[H1_LISTED_SUBTABLE.titleCert]?.[0].reason).toBe('在办')
    expect(data[H1_LISTED_SUBTABLE.clearing]?.some((r) => r.is_total)).toBe(true)
    expect(data._note_texts?.some((t) => t.section === 'impairment-test')).toBe(true)
    expect(data._note_texts?.some((t) => t.section === 'gov-subsidy')).toBe(true)
  })

  it('buildH1ListedSyncPayloads 目标五、15', () => {
    const payloads = buildH1ListedSyncPayloads('wp-1', ['listed_standalone'], {
      summary: createDefaultSummary(),
      categories: [],
      movement: {},
      idle: [],
      leaseOut: [],
      titleCert: [],
      clearing: [],
      govSubsidy: { amount: 0, text: '' },
      noteImpairment: '',
      noteMortgage: '',
      noteSale: '',
      noteClearing: '',
    })
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe(H1_NOTE_SECTION.listed)
    expect(payloads[0].sheet_name).toBe('附注披露信息（上市公司）')
    expect(payloads[0].section_id).toBe('五、15')
  })
})
