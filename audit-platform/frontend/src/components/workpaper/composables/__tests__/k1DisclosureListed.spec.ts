import { describe, it, expect } from 'vitest'
import { PRESET_SEGMENTS } from '@/composables/useAgingConfig'
import {
  aggregateAgingFromK1Detail,
  buildAgingDisclosureRows,
  buildTop5FromK1Detail,
  calcAgingTieOut,
  noteAgingLabel,
  parseK1ListedPayload,
} from '../k1DisclosureModel'
import { buildK1ListedSubTableData, buildK1ListedSyncPayloads } from '../k1DisclosureSyncPayload'
import { K1_LISTED_SUBTABLE } from '../k1NoteSectionMap'
import { emptyK1ListedPayload } from '../k1DisclosureModel'

describe('k1DisclosureModel', () => {
  it('noteAgingLabel maps segment keys to 附注标签', () => {
    expect(noteAgingLabel('y1to2')).toBe('1至2年')
    expect(noteAgingLabel('over5')).toBe('5年以上')
  })

  it('aggregateAgingFromK1Detail sums K1-2 aging buckets', () => {
    const agg = aggregateAgingFromK1Detail(
      [
        {
          id: '1',
          counterparty: 'A',
          nature: '押金',
          beginBalance: 0,
          endBalance: 100,
          badDebtProvision: 0,
          stage: 1,
          relatedParty: '否',
          agingPrior: { within1: 0 },
          agingAudited: { within1: 60, y1to2: 40 },
          remark: '',
        },
      ],
      ['within1', 'y1to2', 'y2to3', 'over3'],
    )
    expect(agg.end.within1).toBe(60)
    expect(agg.end.y1to2).toBe(40)
  })

  it('buildAgingDisclosureRows produces subtotal/provision/total', () => {
    const segs = PRESET_SEGMENTS.THREE_YEAR
    const rows = buildAgingDisclosureRows(
      segs,
      { end: { within1: 100, y1to2: 0, y2to3: 0, over3: 0 }, prior: { within1: 80, y1to2: 0, y2to3: 0, over3: 0 } },
      { end: 10, prior: 8 },
    )
    expect(rows.find((r) => r.kind === 'subtotal')?.endAmount).toBe(100)
    expect(rows.find((r) => r.kind === 'provision')?.endAmount).toBe(10)
    expect(rows.find((r) => r.kind === 'total')?.endAmount).toBe(90)
  })

  it('calcAgingTieOut detects mismatch vs K1-1', () => {
    const rows = buildAgingDisclosureRows(
      PRESET_SEGMENTS.THREE_YEAR,
      { end: { within1: 100, y1to2: 0, y2to3: 0, over3: 0 }, prior: {} },
      { end: 0, prior: 0 },
    )
    const tie = calcAgingTieOut(rows, 200)
    expect(tie.matched).toBe(false)
    expect(tie.diff).toBe(-100)
  })

  it('buildTop5FromK1Detail ranks by closing balance', () => {
    const top5 = buildTop5FromK1Detail(
      [
        { id: '1', counterparty: '甲', nature: '押金', beginBalance: 0, endBalance: 500, badDebtProvision: 0, stage: 1, relatedParty: '否', agingPrior: {}, agingAudited: { within1: 500 }, remark: '' },
        { id: '2', counterparty: '乙', nature: '备用金', beginBalance: 0, endBalance: 800, badDebtProvision: 0, stage: 1, relatedParty: '否', agingPrior: {}, agingAudited: { within1: 800 }, remark: '' },
      ],
      5,
    )
    expect(top5[0].unitName).toBe('乙')
    expect(top5[0].endBalance).toBe(800)
  })

  it('parseK1ListedPayload handles V2 JSON', () => {
    const raw = { version: 2, natureRows: [], agingRows: [] }
    const p = parseK1ListedPayload(raw, PRESET_SEGMENTS.FIVE_YEAR)
    expect(p.version).toBe(2)
  })
})

describe('k1DisclosureSyncPayload', () => {
  it('buildK1ListedSubTableData uses note sub-table names', () => {
    const snap = emptyK1ListedPayload()
    snap.agingRows = buildAgingDisclosureRows(
      PRESET_SEGMENTS.THREE_YEAR,
      { end: { within1: 1, y1to2: 0, y2to3: 0, over3: 0 }, prior: {} },
      { end: 0, prior: 0 },
    )
    const data = buildK1ListedSubTableData(snap)
    expect(data[K1_LISTED_SUBTABLE.aging]?.length).toBeGreaterThan(0)
    expect(data[K1_LISTED_SUBTABLE.nature]).toBeDefined()
    expect(data._note_texts).toBeDefined()
  })

  it('buildK1ListedSyncPayloads 附带 columns（源对齐中文列头）', () => {
    const snap = emptyK1ListedPayload()
    const [payload] = buildK1ListedSyncPayloads('wp-k1', null, snap)
    expect(payload).toBeDefined()
    const cols = payload.columns!
    // 键=子表名，与 sub_table_data 一致
    expect(Object.keys(cols)).toContain(K1_LISTED_SUBTABLE.aging)
    const aging = cols[K1_LISTED_SUBTABLE.aging]
    // 首列为标签列，表头取自 note_template 首列语义
    expect(aging[0].is_label).toBe(true)
    expect(aging[0].key).toBe('label')
    expect(aging[0].label).toBe('账龄')
    // value 列 key 与行对象中文键逐字一致，且非英文键当 header
    expect(aging.map((c) => c.label)).toEqual(['账龄', '期末余额', '上年年末余额'])
    // 性质表源对齐六列
    expect(cols[K1_LISTED_SUBTABLE.nature].map((c) => c.label)).toEqual([
      '款项性质', '期末账面余额', '期末坏账准备', '期末账面价值',
      '上年年末账面余额', '上年年末坏账准备', '上年年末账面价值',
    ])
  })
})
