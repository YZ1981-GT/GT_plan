import { describe, expect, it } from 'vitest'
import {
  buildI3ListedSyncPayloads,
  buildI3MovementSubTable,
  buildI3SoeSyncPayloads,
} from '../i3DisclosureSyncPayload'
import { I3_NOTE_SECTION, I3_LISTED_SUBTABLE, I3_SOE_SUBTABLE } from '../i3NoteSectionMap'
import {
  matrixRowSyncAmounts,
  recalcBookValueRow,
  recalcImpairmentRow,
  type I3DisclosureMatrixRow,
} from '../useI3Disclosure'

describe('i3DisclosureSyncPayload', () => {
  const snap = {
    bookValueRows: [
      { rowId: '1', investee: 'AAA公司', beginBalance: 1000, increase: 0, decrease: 0, endBalance: 1000, isAutoFilled: false },
    ],
    impairmentRows: [
      { rowId: '2', investee: 'AAA公司', beginBalance: 0, increase: 160, decrease: 0, endBalance: 160, isAutoFilled: false },
    ],
    noteProcess: '采用预计未来现金流量现值。',
    noteAssumptions: '增长率5%，折现率12%。',
    noteResult: '本期无需计提减值。',
  }

  it('builds movement subtable with total', () => {
    const rows = buildI3MovementSubTable(snap.bookValueRows)
    expect(rows).toHaveLength(2)
    expect(rows[0].label).toBe('AAA公司')
    expect(rows[0].期末余额).toBe(1000)
    expect(rows[1].label).toBe('合计')
    expect(rows[1].is_total).toBe(true)
  })

  it('rolls up listed book-value fine columns into sync amounts', () => {
    const row: I3DisclosureMatrixRow = {
      rowId: 'bv1',
      investee: 'BBB公司',
      beginBalance: 100,
      increase: 0,
      decrease: 0,
      endBalance: 0,
      isAutoFilled: false,
      incBusinessCombination: 50,
      incJoint: 10,
      incOther: 5,
      decDisposal: 20,
      decOther: 3,
    }
    recalcBookValueRow(row)
    expect(row.increase).toBe(65)
    expect(row.decrease).toBe(23)
    expect(row.endBalance).toBe(142)
    const syncRows = buildI3MovementSubTable([row], 'bookValue')
    expect(syncRows[0].本期增加).toBe(65)
    expect(syncRows[0].本期减少).toBe(23)
    expect(syncRows[0].期末余额).toBe(142)
  })

  it('rolls up impairment provision + other increase for sync', () => {
    const row: I3DisclosureMatrixRow = {
      rowId: 'imp1',
      investee: 'BBB公司',
      beginBalance: 10,
      increase: 40,
      decrease: 0,
      endBalance: 0,
      isAutoFilled: false,
      impIncOther: 5,
      impDecDisposal: 8,
      impDecOther: 2,
    }
    const a = matrixRowSyncAmounts(row, 'impairment')
    expect(a.increase).toBe(45)
    expect(a.decrease).toBe(10)
    expect(a.endBalance).toBe(45)
    recalcImpairmentRow(row)
    expect(row.endBalance).toBe(45)
  })

  it('builds listed sync payload for 五、28', () => {
    const payloads = buildI3ListedSyncPayloads('wp-1', ['listed_standalone'], {
      ...snap,
      performanceRows: [
        { name: 'AAA公司', commitmentStatus: '已完成', impairmentAmount: 0 },
      ],
      assumptionParams: [
        { label: 'AAA资产组', grossMargin: '28%', growthRate: '5%', discountRate: '12%' },
      ],
    })
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe(I3_NOTE_SECTION.listed)
    expect(payloads[0].sub_table_data[I3_LISTED_SUBTABLE.bookValue]).toBeTruthy()
    expect(payloads[0].sub_table_data[I3_LISTED_SUBTABLE.impairment]).toBeTruthy()
    expect(payloads[0].sub_table_data[I3_LISTED_SUBTABLE.performance]).toHaveLength(1)
    expect(payloads[0].sub_table_data[I3_LISTED_SUBTABLE.performance]![0].业绩承诺完成情况).toBe('已完成')
    expect(payloads[0].sub_table_data[I3_LISTED_SUBTABLE.assumptions]).toHaveLength(1)
    expect(payloads[0].sub_table_data[I3_LISTED_SUBTABLE.assumptions]![0].折现率).toBe('12%')
    expect(payloads[0].sub_table_data._note_texts?.length).toBeGreaterThan(0)
  })

  it('builds soe sync payload for 八、29', () => {
    const payloads = buildI3SoeSyncPayloads('wp-1', ['soe_standalone'], snap)
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe(I3_NOTE_SECTION.soe)
    expect(payloads[0].sub_table_data[I3_SOE_SUBTABLE.bookValue]).toBeTruthy()
  })

  it('skips listed when only soe standard applies', () => {
    expect(buildI3ListedSyncPayloads('wp-1', ['soe_standalone'], snap)).toHaveLength(0)
  })
})
