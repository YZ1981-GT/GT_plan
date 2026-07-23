import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { useI6Adjustment } from '../useI6Adjustment'

describe('useI6Adjustment', () => {
  it('迁移旧 category=AJE 格式', () => {
    const allResponses = ref(new Map<string, any>([
      ['I6-3-rows', {
        remark: JSON.stringify([
          { rowId: 'r1', description: '跨期', category: 'AJE', accountName: '研发费用', debit: 100, credit: 0 },
        ]),
      }],
    ]))
    const onSave = vi.fn()
    const { rows } = useI6Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      onSave,
    })
    expect(rows.value[0].category).toBe('账项调整')
    expect(rows.value[0].debitAmount).toBe(100)
  })

  it('publishAdjustment 触发 i6:adjustment-writeback', () => {
    const allResponses = ref(new Map<string, any>())
    const handler = vi.fn()
    window.addEventListener('i6:adjustment-writeback', handler)
    const { addRow, publishAdjustment } = useI6Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      onSave: vi.fn(),
    })
    addRow({ description: '测试', debitAmount: 50, creditAmount: 0 })
    publishAdjustment()
    expect(handler).toHaveBeenCalled()
    window.removeEventListener('i6:adjustment-writeback', handler)
  })
})
