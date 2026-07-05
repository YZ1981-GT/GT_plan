import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useG13Detail } from '../useG13Detail'
import type { ChecklistResponse } from '../useF1FormData'

describe('useG13Detail totalRow', () => {
  it('合计行 currentAudited 为明细审定数之和', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G13-detail-rows', {
        remark: JSON.stringify([
          {
            rowId: 'r1',
            seq: 1,
            instrumentName: '工具A',
            belongAccount: 'G1',
            currentUnadjusted: 500,
            adjustment: 20,
          },
          {
            rowId: 'r2',
            seq: 2,
            instrumentName: '工具B',
            belongAccount: 'G9',
            currentUnadjusted: 300,
            adjustment: 0,
          },
        ]),
      } as ChecklistResponse],
    ]))

    const detail = useG13Detail({
      allResponses,
      debouncedSave: () => {},
      isReadonly: ref(false),
    })

    expect(detail.totalRow.value.currentAudited).toBe(820)
    expect(detail.grandTotalAudited.value).toBe(820)
    expect(detail.totalRow.value.instrumentName).toBe('合计')
  })
})
