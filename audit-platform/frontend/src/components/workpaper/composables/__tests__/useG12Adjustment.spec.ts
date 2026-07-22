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
        rowId: 'r1', seq: 1, adjustmentDesc: 'test', category: 'account',
        fsItem: '净敞口套期收益', accountCode: '6103', accountName: '净敞口套期收益',
        noteItem: '净敞口套期收益', debitAmount: 100, creditAmount: 0, indexRef: '', remark: '',
      },
      {
        rowId: 'r2', seq: 2, adjustmentDesc: 'offset', category: 'account',
        fsItem: '未分配利润', accountCode: '4104', accountName: '利润分配',
        noteItem: '', debitAmount: 0, creditAmount: 100, indexRef: '', remark: '',
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
      rowId: 'r1', seq: 1, adjustmentDesc: '', category: 'account',
      fsItem: '', accountCode: '6103', accountName: '', noteItem: '',
      debitAmount: 100, creditAmount: 50, indexRef: '', remark: '',
    }]
    adj.syncToAdjudication()
    expect(saves.some((s) => s.id === G12_AJE_ADJ_OVERLAY_ID)).toBe(false)
  })

  it('migrates legacy AJE rows with summary field', () => {
    const allResponses = ref(new Map([
      ['G12-aje-rows', {
        remark: JSON.stringify([{
          rowId: 'legacy', entryType: 'AJE', summary: '旧格式', accountCode: '6103',
          debitAmount: 50, creditAmount: 0,
        }]),
      }],
    ]))
    const adj = useG12Adjustment({
      allResponses,
      isReadonly: ref(false),
      debouncedSave: vi.fn(),
    })
    expect(adj.rows.value[0].adjustmentDesc).toBe('旧格式')
    expect(adj.rows.value[0].category).toBe('account')
  })
})
