import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { useG12Adjustment, G12_AJE_ADJ_OVERLAY_ID } from '../useG12Adjustment'

describe('useG12Adjustment.syncToAdjudication', () => {
  it('writes net overlay to G12-aje-adj-overlay when balanced', () => {
    const allResponses = ref(new Map())
    const saves: Array<{ id: string; data: any }> = []
    const adj = useG12Adjustment({
      allResponses,
      isReadonly: ref(false),
      debouncedSave: (id, data) => { saves.push({ id, data }) },
    })
    adj.rows.value = [
      {
        rowId: 'r1', entryType: 'AJE', date: '', summary: 'test',
        accountCode: '6103', accountName: '净敞口套期', debitAmount: 100, creditAmount: 0,
        preparedBy: '', remark: '',
      },
      {
        rowId: 'r2', entryType: 'AJE', date: '', summary: 'offset',
        accountCode: '2203', accountName: '应付', debitAmount: 0, creditAmount: 100,
        preparedBy: '', remark: '',
      },
    ]
    adj.syncToAdjudication()
    expect(saves.some((s) => s.id === G12_AJE_ADJ_OVERLAY_ID)).toBe(true)
    const overlaySave = saves.find((s) => s.id === G12_AJE_ADJ_OVERLAY_ID)!
    const overlay = JSON.parse(overlaySave.data.remark)
    expect(overlay.net_hedge).toBe(100)
  })

  it('skips sync when unbalanced', () => {
    const saves: Array<{ id: string }> = []
    const adj = useG12Adjustment({
      allResponses: ref(new Map()),
      isReadonly: ref(false),
      debouncedSave: (id) => { saves.push({ id }) },
    })
    adj.rows.value = [{
      rowId: 'r1', entryType: 'AJE', date: '', summary: '',
      accountCode: '6103', accountName: '', debitAmount: 100, creditAmount: 50,
      preparedBy: '', remark: '',
    }]
    adj.syncToAdjudication()
    expect(saves.some((s) => s.id === G12_AJE_ADJ_OVERLAY_ID)).toBe(false)
  })
})
