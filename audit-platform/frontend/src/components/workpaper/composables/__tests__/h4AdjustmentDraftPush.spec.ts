/**
 * h4AdjustmentDraftPush + H4-4 推送草稿单测
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  buildBalancedAjePair,
  mergeH43DraftByMarker,
  pushDraftPairsToH43,
  H44_AJE_MARKER,
} from '../h4AdjustmentDraftPush'
import { useH4AdditionCheck } from '../useH4AdditionCheck'

describe('h4AdjustmentDraftPush', () => {
  it('buildBalancedAjePair creates balanced debit/credit lines', () => {
    const pair = buildBalancedAjePair(
      {
        description: '测试',
        amount: 123.456,
        debitCode: '6701',
        debitName: '资产减值损失',
        creditCode: '1605',
        creditName: '工程物资',
        indexRef: 'H4-7',
        marker: 'H4-7-aje-auto',
      },
      1,
    )
    expect(pair).toHaveLength(2)
    expect(pair[0].debitAmount).toBe(123.46)
    expect(pair[1].creditAmount).toBe(123.46)
    expect(pair[0].category).toBe('账项调整')
  })

  it('mergeH43DraftByMarker replaces same marker idempotently', () => {
    const existing = [
      { seq: 1, remark: 'manual', description: '手工' },
      { seq: 2, remark: H44_AJE_MARKER, description: '旧草稿' },
    ]
    const merged = mergeH43DraftByMarker(existing, H44_AJE_MARKER, [
      { seq: 99, remark: H44_AJE_MARKER, description: '新草稿' },
    ])
    expect(merged).toHaveLength(2)
    expect(merged[0].description).toBe('手工')
    expect(merged[1].description).toBe('新草稿')
    expect(merged[1].seq).toBe(2)
  })
})

describe('useH4AdditionCheck.pushAjeDraftToH43', () => {
  it('pushes invoice-diff rows to H4-3', () => {
    const map = new Map()
    map.set('H4-4-rows', {
      remark: JSON.stringify([
        {
          rowId: 'a1',
          name: '钢材',
          amount: 1000,
          invoiceAmount: 800,
          isAbnormal: '',
        },
      ]),
    })
    const allResponses = ref(map)
    const saves: { id: string; val: unknown }[] = []
    const api = useH4AdditionCheck({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses: allResponses as any,
      onSave: (id, val) => {
        saves.push({ id, val })
        allResponses.value.set(id, {
          item_id: id,
          remark: typeof val === 'string' ? val : JSON.stringify(val),
          conclusion: null,
        })
      },
    })
    const res = api.pushAjeDraftToH43()
    expect(res.ok).toBe(true)
    expect(res.added).toBe(2)
    const h43 = JSON.parse(allResponses.value.get('H4-3-rows').remark)
    expect(h43).toHaveLength(2)
    expect(h43.every((r: any) => r.remark === H44_AJE_MARKER)).toBe(true)
    expect(h43[0].creditAmount + h43[1].creditAmount).toBe(200)
  })
})
