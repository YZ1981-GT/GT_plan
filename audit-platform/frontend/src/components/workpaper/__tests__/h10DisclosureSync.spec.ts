/**
 * H10 披露 → 附注 sync payload 契约
 */
import { describe, it, expect } from 'vitest'
import {
  buildH10SyncPayloads,
  buildH10MainSubTableRows,
  buildH10TrialSubTableRows,
  h10DisclosureDefKeys,
  h10TrialDefKeys,
} from '../composables/h10DisclosureSyncPayload'
import { H10_NOTE_SECTION } from '../composables/h10NoteSectionMap'
import type { H10DisclosureRow, H10TrialDetailRow } from '../composables/useH10Disclosure'

function row(partial: Partial<H10DisclosureRow> & { rowKey: string; label: string }): H10DisclosureRow {
  return {
    currentAmount: 0,
    priorAmount: 0,
    changeAmount: 0,
    changeRate: null,
    remark: '',
    ...partial,
  }
}

describe('H10 disclosure sync payload', () => {
  it('defs cover trial + adjudication keys', () => {
    expect(h10DisclosureDefKeys('listed')).toContain('trial_operation_sales')
    expect(h10DisclosureDefKeys('listed')).toContain('fixed_asset_disposal')
    expect(h10TrialDefKeys()).toEqual(['fixed_asset_trial', 'rd_sample_sales'])
  })

  it('main subtable skips empty rows and appends total', () => {
    const rows = [
      row({ rowKey: 'fixed_asset_disposal', label: '固定资产', currentAmount: 100, priorAmount: 40 }),
      row({ rowKey: 'construction_disposal', label: '在建', currentAmount: 0, priorAmount: 0 }),
    ]
    const out = buildH10MainSubTableRows(rows, 'listed')
    expect(out).toHaveLength(2) // 1 data + total
    expect(out[0].row_key).toBe('fixed_asset_disposal')
    expect(out[1].is_total).toBe(true)
    expect(out[1].current_amount).toBe(100)
  })

  it('soe main includes non_recurring_amount', () => {
    const rows = [
      row({
        rowKey: 'fixed_asset_disposal',
        label: '固定资产',
        currentAmount: 50,
        priorAmount: 0,
        nonRecurringAmount: 50,
      }),
    ]
    const out = buildH10MainSubTableRows(rows, 'soe')
    expect(out[0].non_recurring_amount).toBe(50)
    expect(out[1].non_recurring_amount).toBe(50)
  })

  it('trial subtable uses income − cost net', () => {
    const trial: H10TrialDetailRow[] = [
      {
        rowKey: 'fixed_asset_trial',
        label: '固定资产试运行销售',
        currentIncome: 200,
        currentCost: 80,
        priorIncome: 100,
        priorCost: 40,
      },
      {
        rowKey: 'rd_sample_sales',
        label: '研发样品销售',
        currentIncome: 0,
        currentCost: 0,
        priorIncome: 0,
        priorCost: 0,
      },
    ]
    const out = buildH10TrialSubTableRows(trial)
    expect(out).toHaveLength(2)
    expect(out[0].current_amount).toBe(120)
    expect(out[0].prior_amount).toBe(60)
    expect(out[1].is_total).toBe(true)
  })

  it('buildH10SyncPayloads targets correct note section', () => {
    const payloads = buildH10SyncPayloads('wp-1', 'listed', [], {
      rows: [row({ rowKey: 'fixed_asset_disposal', label: 'FA', currentAmount: 10, priorAmount: 0 })],
      trialRows: [],
      noteText: '说明',
      adjudicatedAmount: 10,
    })
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe(H10_NOTE_SECTION.listed)
    expect(payloads[0].sub_table_data._note_texts).toEqual([
      { section: 'disclosure-note', text: '说明' },
    ])
  })

  it('soe section is 八、75', () => {
    const payloads = buildH10SyncPayloads('wp-1', 'soe', ['soe_standalone'], {
      rows: [],
      trialRows: [],
      noteText: '',
    })
    expect(payloads[0].section_id).toBe('八、75')
  })
})
