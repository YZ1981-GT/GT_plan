/**
 * H6 附注披露：模型取数 + 同步 payload
 */
import { describe, expect, it } from 'vitest'
import {
  buildClearingDisplay,
  buildSummaryDisplay,
  pullClearingFromH6Responses,
  sumClearing,
} from '../h6DisclosureModel'
import {
  buildH6ListedSyncPayloads,
  buildH6SoeSyncPayloads,
  buildH6ListedClearingSubTable,
  patchFaSummaryClearingRow,
} from '../h6DisclosureSyncPayload'
import { H6_CLEARING_SUBTABLE, H6_NOTE_SECTION, H6_SUMMARY_SUBTABLE } from '../h6NoteSectionMap'

function respMap(entries: Record<string, unknown>) {
  const m = new Map<string, any>()
  for (const [k, v] of Object.entries(entries)) {
    m.set(k, { item_id: k, remark: typeof v === 'string' ? v : JSON.stringify(v) })
  }
  return m
}

describe('h6DisclosureModel', () => {
  it('pulls clearing from H6-1/H6-2 and flags over-1-year', () => {
    const old = new Date()
    old.setFullYear(old.getFullYear() - 2)
    const map = respMap({
      'H6-1-end-balance-audited': '500',
      'H6-1-rows': [
        { name: '期初余额', category: 'balance', audited: 200 },
        { name: '期末余额', category: 'balance', audited: 500 },
      ],
      'H6-2-rows': [
        {
          rowId: 'a',
          assetName: '旧厂房',
          netBookValue: 500,
          disposalReason: '拆除',
          status: '清理中',
          startDate: old.toISOString().slice(0, 10),
        },
      ],
    })
    const r = pullClearingFromH6Responses(map)
    expect(r.clearingRows).toHaveLength(1)
    expect(r.clearingRows[0].name).toBe('旧厂房')
    expect(r.clearingRows[0].endBalance).toBe(500)
    expect(r.overOneYearCount).toBe(1)
    expect(r.clearingNoteDraft).toContain('旧厂房')
    expect(r.transitZero).toBe(false)
  })

  it('summary display sums FA + clearing', () => {
    const state = {
      faEnd: 1000,
      faPrior: 800,
      clearingRows: [
        { rowId: '1', name: '设备A', endBalance: 50, priorBalance: 30, reason: '报废' },
      ],
      clearingNote: '',
    }
    const rows = buildSummaryDisplay(state)
    expect(rows[2].label).toBe('合计')
    expect(rows[2].endBalance).toBe(1050)
    expect(rows[2].priorBalance).toBe(830)
    expect(buildClearingDisplay(state.clearingRows).at(-1)?.endBalance).toBe(50)
  })
})

describe('h6DisclosureSyncPayload', () => {
  it('builds listed sync to 五、22（与 H1 固定资产同章节）with clearing subtable only', () => {
    const payloads = buildH6ListedSyncPayloads('wp-h6', [], {
      faEnd: 100,
      faPrior: 90,
      clearingRows: [
        { rowId: '1', name: '设备', endBalance: 10, priorBalance: 5, reason: '报废' },
      ],
      clearingNote: '超1年说明',
    })
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe(H6_NOTE_SECTION.listed)
    const sub = payloads[0].sub_table_data
    expect(sub[H6_CLEARING_SUBTABLE]).toBeDefined()
    expect(sub[H6_CLEARING_SUBTABLE][0]).toMatchObject({
      label: '设备',
      end_balance: 10,
      prior_balance: 5,
    })
    expect(sub._note_texts?.[0]).toMatchObject({
      section: 'clearing-over-1y',
      text: '超1年说明',
    })
  })

  it('builds soe sync to 八、22 with carrying fields', () => {
    const payloads = buildH6SoeSyncPayloads('wp-h6', [], {
      faEnd: 0,
      faPrior: 0,
      clearingRows: [
        { rowId: '1', name: '车辆', endBalance: 20, priorBalance: 20, reason: '待处置' },
      ],
      clearingNote: '',
    })
    expect(payloads[0].section_id).toBe(H6_NOTE_SECTION.soe)
    const rows = payloads[0].sub_table_data[H6_CLEARING_SUBTABLE]
    expect(rows[0]).toMatchObject({
      label: '车辆',
      end_carrying: 20,
      begin_carrying: 20,
    })
    expect(sumClearing([{ rowId: '1', name: '车辆', endBalance: 20, priorBalance: 20, reason: '' }]).endBalance).toBe(20)
  })

  it('patches existing FA summary clearing row without dropping other keys', () => {
    const existing = {
      [H6_SUMMARY_SUBTABLE]: [
        { label: '固定资产', end_balance: 1000, prior_balance: 900 },
        { label: '固定资产清理', end_balance: 0, prior_balance: 0 },
        { label: '合计', end_balance: 1000, prior_balance: 900, is_total: true },
      ],
      固定资产情况: [{ label: '房屋', begin: 1 }],
    }
    const patched = patchFaSummaryClearingRow(
      existing,
      {
        faEnd: 1000,
        faPrior: 900,
        clearingRows: [{ rowId: '1', name: 'x', endBalance: 40, priorBalance: 10, reason: '' }],
        clearingNote: '',
      },
      'listed',
    )
    expect(patched['固定资产情况']).toEqual([{ label: '房屋', begin: 1 }])
    const summary = patched[H6_SUMMARY_SUBTABLE] as any[]
    expect(summary.find((r) => r.label === '固定资产清理').end_balance).toBe(40)
    expect(summary.find((r) => r.label === '合计').end_balance).toBe(1040)
  })

  it('listed clearing subtable includes total row', () => {
    const rows = buildH6ListedClearingSubTable([
      { rowId: '1', name: 'a', endBalance: 3, priorBalance: 1, reason: '' },
      { rowId: '2', name: 'b', endBalance: 2, priorBalance: 2, reason: '' },
    ])
    expect(rows.at(-1)).toMatchObject({ label: '合计', end_balance: 5, prior_balance: 3, is_total: true })
  })
})
