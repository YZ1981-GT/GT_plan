/**
 * G7 四表库预填纯函数测试。
 *
 * 覆盖：手工优先幂等 / overwrite 语义 / 空 prefill 零改动 / roll-forward 警告 /
 * 变动性质落第4行 / 披露主表 seed 列映射。
 *
 * spec: g7-four-table-extraction-and-disclosure-alignment R2.1~2.5 / R3.1~3.2，Property 5 / 6
 */
import { describe, it, expect } from 'vitest'
import {
  seedG7AdjudicationFromPrefill,
  previewSeedG7Adjudication,
  seedG7MovementFromLeafCategories,
  type G7AdjudicationPrefill,
  type AdjRowLike,
  type G7LeafBucketSlot,
} from '../g7FourTableSeed'
import type { G7DisclosureRow } from '../../g7-long-term-equity-main/disclosure/g7ListedDisclosureModel'

function row(id: string, item = '', opening = 0, closing = 0): AdjRowLike {
  return { id, item, openingUnadjusted: opening, closingUnadjusted: closing }
}

function groups(rows: AdjRowLike[]) {
  return [
    { id: 'subsidiary', rows: [rows[0]] },
    { id: 'joint_venture', rows: [rows[1]] },
    { id: 'associate', rows: [rows[2]] },
    { id: 'impairment', rows: [rows[3]] },
  ]
}

const PREFILL: G7AdjudicationPrefill = {
  gross: {
    subsidiary: { label: '对子公司投资', opening: 100, increase: 10, decrease: 5, closing: 105, codes: ['1511.01'], roll_forward_ok: true },
    jv: { label: '对合营企业投资', opening: 50, increase: 0, decrease: 0, closing: 50, codes: ['1511.02'], roll_forward_ok: true },
    other: { label: '四、其他', opening: 30, increase: 5, decrease: 2, closing: 33, codes: ['1511.03', '1511.04.01'], roll_forward_ok: true, from_buckets: ['equity_profit', 'oci'] },
  },
  impairment: {
    total: { label: '长期股权投资减值准备', opening: 20, increase: 3, decrease: 0, closing: 23, codes: ['1512'], roll_forward_ok: true },
  },
}

describe('seedG7AdjudicationFromPrefill', () => {
  it('空 prefill 零改动', () => {
    const g = groups([row('1'), row('2'), row('3'), row('4')])
    const r = seedG7AdjudicationFromPrefill(g, null)
    expect(r).toEqual({ filled: 0, skipped: 0, warnings: [] })
  })

  it('正常填充：类别行 + 减值行', () => {
    const g = groups([row('s'), row('jv'), row('a'), row('imp')])
    const r = seedG7AdjudicationFromPrefill(g, PREFILL)
    expect(r.filled).toBeGreaterThanOrEqual(3) // subsidiary + jv + impairment
    expect(g[0].rows[0].openingUnadjusted).toBe(100)
    expect(g[0].rows[0].closingUnadjusted).toBe(105)
    expect(g[1].rows[0].openingUnadjusted).toBe(50)
    expect(g[3].rows[0].openingUnadjusted).toBe(20)
    expect(g[3].rows[0].closingUnadjusted).toBe(23)
  })

  it('手工优先：已有值不覆盖', () => {
    const g = groups([row('s', '', 999, 888), row('jv'), row('a'), row('imp')])
    seedG7AdjudicationFromPrefill(g, PREFILL)
    // 已有值保留
    expect(g[0].rows[0].openingUnadjusted).toBe(999)
    expect(g[0].rows[0].closingUnadjusted).toBe(888)
  })

  it('overwrite=true 覆盖已有值', () => {
    const g = groups([row('s', '', 999, 888), row('jv'), row('a'), row('imp')])
    seedG7AdjudicationFromPrefill(g, PREFILL, { overwrite: true })
    expect(g[0].rows[0].openingUnadjusted).toBe(100)
    expect(g[0].rows[0].closingUnadjusted).toBe(105)
  })

  it('roll-forward 不平产生 warnings', () => {
    const bad: G7AdjudicationPrefill = {
      gross: {
        subsidiary: { label: '对子公司投资', opening: 100, increase: 1, decrease: 0, closing: 999, codes: ['x'], roll_forward_ok: false },
      },
    }
    const g = groups([row('s'), row('jv'), row('a'), row('imp')])
    const r = seedG7AdjudicationFromPrefill(g, bad)
    expect(r.warnings.length).toBeGreaterThan(0)
    expect(r.warnings[0]).toContain('roll-forward')
  })

  it('预填为空桶 → 对应行不出现', () => {
    const partial: G7AdjudicationPrefill = {
      gross: { subsidiary: PREFILL.gross!.subsidiary },
    }
    const g = groups([row('s'), row('jv'), row('a'), row('imp')])
    seedG7AdjudicationFromPrefill(g, partial)
    expect(g[1].rows[0].openingUnadjusted).toBe(0) // jv 无数据，不动
  })
})

describe('previewSeedG7Adjudication', () => {
  it('返回将被改动的格子', () => {
    const g = groups([row('s'), row('jv'), row('a'), row('imp')])
    const p = previewSeedG7Adjudication(g, PREFILL)
    expect(p.length).toBeGreaterThan(0)
    expect(p[0]).toHaveProperty('field')
    expect(p[0]).toHaveProperty('newValue')
  })

  it('已有值时不预览（除 overwrite）', () => {
    const g = groups([row('s', '', 999, 888), row('jv'), row('a'), row('imp')])
    const p = previewSeedG7Adjudication(g, PREFILL)
    const subCells = p.filter(c => c.groupId === 'subsidiary')
    expect(subCells).toHaveLength(0) // 已有值，不在预览里
    const pOver = previewSeedG7Adjudication(g, PREFILL, { overwrite: true })
    expect(pOver.filter(c => c.groupId === 'subsidiary').length).toBeGreaterThan(0)
  })
})

describe('seedG7MovementFromLeafCategories', () => {
  function discRow(id: string, label = '', kind: 'data' | 'total' = 'data'): G7DisclosureRow {
    return { id, label, values: { openingBook: null, closingBook: null, equityProfit: null, oci: null, otherEquity: null, openingImpairment: null, closingImpairment: null }, kind }
  }

  const BUCKETS: Record<string, G7LeafBucketSlot> = {
    subsidiary: { bucket: 'subsidiary', label: '对子公司投资', opening: 100, closing: 120, increase: 30, decrease: 10, codes: ['1511.01'] },
    impairment: { bucket: 'impairment', label: '长期股权投资减值准备', opening: 20, closing: 25, increase: 5, decrease: 0, codes: ['1512'] },
    equity_profit: { bucket: 'equity_profit', label: '权益法下确认的投资损益', opening: 0, closing: 15, increase: 15, decrease: 0, codes: ['1511.03'] },
    oci: { bucket: 'oci', label: '其他综合收益调整', opening: 0, closing: 3, increase: 3, decrease: 0, codes: ['1511.04.01'] },
    other_equity: { bucket: 'other_equity', label: '其他权益变动', opening: 0, closing: 2, increase: 2, decrease: 0, codes: ['1511.04.02'] },
  }

  it('空 buckets 零改动', () => {
    expect(seedG7MovementFromLeafCategories([], null)).toEqual({ filled: 0, skipped: 0 })
  })

  it('减值桶写入合计行的 openingImpairment / closingImpairment', () => {
    const rows = [discRow('d1', '对子公司投资'), discRow('total', '合计', 'total')]
    seedG7MovementFromLeafCategories(rows, BUCKETS)
    expect(rows[1].values.openingImpairment).toBe(20)
    expect(rows[1].values.closingImpairment).toBe(25)
  })

  it('变动性质桶写入合计行的变动列', () => {
    const rows = [discRow('d1', '对子公司投资'), discRow('total', '合计', 'total')]
    seedG7MovementFromLeafCategories(rows, BUCKETS)
    expect(rows[1].values.equityProfit).toBe(15)
    expect(rows[1].values.oci).toBe(3)
    expect(rows[1].values.otherEquity).toBe(2)
  })

  it('手工优先：已有值不覆盖', () => {
    const rows = [discRow('d1', '对子公司投资'), discRow('total', '合计', 'total')]
    rows[1].values.openingImpairment = 999
    seedG7MovementFromLeafCategories(rows, BUCKETS)
    expect(rows[1].values.openingImpairment).toBe(999)
  })
})
