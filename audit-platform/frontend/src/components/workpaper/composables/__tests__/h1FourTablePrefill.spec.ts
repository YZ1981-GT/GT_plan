/**
 * h1FourTablePrefill 单测 — H1 四表取数映射 + 增减核对
 * Properties: 1(分类聚合不双算) 3(归一自洽) 4(空数据) 8(只读核对) 12(Card_Level 不编造)
 */
import { describe, it, expect } from 'vitest'
import {
  buildDetailSeedRows,
  buildMovementReconcile,
  shouldSeedDetailRows,
  mergeSeedRows,
  isFourTableSeededRow,
  H1_FOUR_TABLE_REMARK_PREFIX,
  type H1FourTablePrefill,
} from '../h1FourTablePrefill'

function amt(begin = 0, debit = 0, credit = 0, end = 0) {
  return { begin, debit, credit, end }
}

const payload: H1FourTablePrefill = {
  enabled: true,
  detail: {
    source: 'tb_balance',
    totals: { cost: 1200, dep: 300, impair: 50 },
    rows: [
      {
        category: '房屋及建筑物',
        source_codes: ['1601.01', '1602.01'],
        cost: amt(1000, 200, 0, 1200),
        dep: amt(200, 0, 100, 300),
        impair: amt(50, 0, 0, 50),
      },
      {
        category: '其他设备',
        source_codes: ['1601.99'],
        cost: amt(500, 0, 100, 400),
        dep: amt(0, 0, 0, 0),
        impair: amt(0, 0, 0, 0),
        needs_review: true,
      },
    ],
  },
  ledger_movement: { available: true, lines: 12, debit_total: 200, credit_total: 100 },
  counterpart: { available: false, fill_rate: 0.09, reason: '序时账未完整记录对方科目' },
}

describe('buildDetailSeedRows', () => {
  it('按分类映射行并保留来源科目码（Property 1）', () => {
    const rows = buildDetailSeedRows(payload)
    expect(rows).toHaveLength(2)
    expect(rows[0].category).toBe('房屋及建筑物')
    expect(rows[0].name).toBe('房屋及建筑物')
    expect(rows[0].remark).toContain('1601.01/1602.01')
    expect(rows[0].remark.startsWith(H1_FOUR_TABLE_REMARK_PREFIX)).toBe(true)
  })

  it('原值/备抵方向映射正确且公式列自洽（Property 3）', () => {
    const [house] = buildDetailSeedRows(payload)
    expect(house.costBeginUnadj).toBe(1000)
    expect(house.costIncUnadj).toBe(200)
    expect(house.costDecUnadj).toBe(0)
    // 期末由 recalcDetailRow 派生：1000+200-0
    expect(house.costEndUnadj).toBe(1200)
    // 备抵：贷方=计提 / 借方=处置；期末=期初+计提-处置
    expect(house.depProvUnadj).toBe(100)
    expect(house.depDispUnadj).toBe(0)
    expect(house.depEndUnadj).toBe(300)
    expect(house.impairEndUnadj).toBe(50)
    // 净值 = 原值 - 折旧 - 减值
    expect(house.netEndUnadj).toBe(1200 - 300 - 50)
  })

  it('减少映射到贷方（原值处置）', () => {
    const rows = buildDetailSeedRows(payload)
    const other = rows[1]
    expect(other.costDecUnadj).toBe(100)
    expect(other.costEndUnadj).toBe(400)
    expect(other.remark).toContain('分类待复核')
  })

  it('绝不编造 Card_Level 字段（Property 12 / Req8.1）', () => {
    for (const row of buildDetailSeedRows(payload)) {
      expect(row.assetNo).toBe('')
      expect(row.acquisitionDate).toBe('')
      expect(row.location).toBe('')
      expect(row.department).toBe('')
      expect(row.spec).toBe('')
      expect(row.supplier).toBe('')
      expect(row.usefulLife).toBe(0)
      expect(row.salvageRate).toBe(0)
      expect(row.annualDep).toBe(0)
    }
  })

  it('空载荷/缺字段返回空数组（Property 4）', () => {
    expect(buildDetailSeedRows(null)).toEqual([])
    expect(buildDetailSeedRows(undefined)).toEqual([])
    expect(buildDetailSeedRows({})).toEqual([])
    expect(buildDetailSeedRows({ detail: { rows: [], totals: { cost: 0, dep: 0, impair: 0 } } })).toEqual([])
  })

  it('跳过无分类名的脏行', () => {
    const rows = buildDetailSeedRows({
      detail: {
        rows: [{ category: '  ', source_codes: [], cost: amt(), dep: amt(), impair: amt() }],
        totals: { cost: 0, dep: 0, impair: 0 },
      },
    })
    expect(rows).toEqual([])
  })

  it('isFourTableSeededRow 区分取数行与手工行', () => {
    const [seed] = buildDetailSeedRows(payload)
    expect(isFourTableSeededRow(seed)).toBe(true)
    expect(isFourTableSeededRow({ remark: '审计师手工补录' })).toBe(false)
    expect(isFourTableSeededRow(null)).toBe(false)
  })
})

describe('shouldSeedDetailRows（Persist_First，Property 2）', () => {
  it('缺失/空串/空数组 → 允许 seed', () => {
    expect(shouldSeedDetailRows(null)).toBe(true)
    expect(shouldSeedDetailRows(undefined)).toBe(true)
    expect(shouldSeedDetailRows('')).toBe(true)
    expect(shouldSeedDetailRows('[]')).toBe(true)
  })

  it('已有行 → 绝不 seed（不覆盖手工数据）', () => {
    expect(shouldSeedDetailRows(JSON.stringify([{ rowId: 'r1', name: '厂房' }]))).toBe(false)
  })

  it('解析失败 → 保守视为有数据不 seed', () => {
    expect(shouldSeedDetailRows('{not json')).toBe(false)
    expect(shouldSeedDetailRows('{"a":1}')).toBe(false)
  })
})

describe('mergeSeedRows（重新取数保留手工行，Property 2 / Req7.3）', () => {
  it('覆盖取数行、保留手工新增行', () => {
    const seeds = buildDetailSeedRows(payload)
    const existing = JSON.stringify([
      { rowId: 'h1ft-0-房屋及建筑物', remark: `${H1_FOUR_TABLE_REMARK_PREFIX}：1601.01`, costBeginUnadj: 1 },
      { rowId: 'manual-1', remark: '审计师手工补录', name: '新购设备' },
      { rowId: 'manual-2', name: '无备注手工行' },
    ])
    const merged = mergeSeedRows(seeds, existing)
    expect(merged).toHaveLength(seeds.length + 2)
    expect(merged.filter((r: any) => r.rowId === 'manual-1')).toHaveLength(1)
    expect(merged.filter((r: any) => r.rowId === 'manual-2')).toHaveLength(1)
    // 旧取数行被新取数行替换（不重复）
    expect(merged.filter((r: any) => r.rowId === 'h1ft-0-房屋及建筑物')).toHaveLength(1)
    expect((merged[0] as any).costBeginUnadj).toBe(1000)
  })

  it('无既有数据/解析失败时只写取数行', () => {
    const seeds = buildDetailSeedRows(payload)
    expect(mergeSeedRows(seeds, null)).toHaveLength(seeds.length)
    expect(mergeSeedRows(seeds, 'broken')).toHaveLength(seeds.length)
  })
})

describe('buildMovementReconcile', () => {
  const detailRows = [
    { costIncUnadj: 200, costDecUnadj: 100 },
    { costIncUnadj: 0, costDecUnadj: 0 },
  ]

  it('一致时不告警（Property 8）', () => {
    const r = buildMovementReconcile(detailRows, payload.ledger_movement)
    expect(r.available).toBe(true)
    expect(r.hasDiff).toBe(false)
    expect(r.diffIncrease).toBe(0)
    expect(r.message).toContain('一致')
  })

  it('差异 > 1 元时告警且不改数', () => {
    const r = buildMovementReconcile(
      [{ costIncUnadj: 5000, costDecUnadj: 100 }],
      payload.ledger_movement,
    )
    expect(r.hasDiff).toBe(true)
    expect(r.diffIncrease).toBe(4800)
    expect(r.detailIncrease).toBe(5000)
    expect(r.ledgerIncrease).toBe(200)
  })

  it('1 元以内容差不告警', () => {
    const r = buildMovementReconcile(
      [{ costIncUnadj: 200.5, costDecUnadj: 100 }],
      payload.ledger_movement,
    )
    expect(r.hasDiff).toBe(false)
  })

  it('序时账不可用时显示未取到而非一致（Property 7）', () => {
    const r = buildMovementReconcile(detailRows, { available: false, debit_total: 0, credit_total: 0 })
    expect(r.available).toBe(false)
    expect(r.hasDiff).toBe(false)
    expect(r.message).toContain('未取到序时账发生额')
    // 明细侧合计仍如实展示
    expect(r.detailIncrease).toBe(200)
  })

  it('载荷缺失时安全降级', () => {
    const r = buildMovementReconcile(null, null)
    expect(r.available).toBe(false)
    expect(r.detailIncrease).toBe(0)
  })
})
