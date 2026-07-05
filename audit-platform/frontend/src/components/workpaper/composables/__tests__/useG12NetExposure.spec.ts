import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useG12NetExposure } from '../useG12NetExposure'
import type { ChecklistResponse } from '../useF1FormData'

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), success: vi.fn() },
}))

describe('useG12NetExposure', () => {
  let allResponses: ReturnType<typeof ref<Map<string, ChecklistResponse>>>
  let saved: Array<{ id: string; data: Partial<ChecklistResponse> }>
  let ne: ReturnType<typeof useG12NetExposure>

  beforeEach(() => {
    saved = []
    allResponses = ref(new Map())
    ne = useG12NetExposure({
      allResponses,
      isReadonly: ref(false),
      debouncedSave: (id, data) => { saved.push({ id, data }) },
    })
  })

  it('未选合规时不 persist，saveValidated 阻断', () => {
    const rowId = ne.rows.value[0].rowId
    ne.updateCell(rowId, 'checkResult', '测试')
    expect(saved).toHaveLength(0)

    expect(ne.saveValidated()).toBe(false)
    expect(saved).toHaveLength(0)
  })

  it('全部合规后 updateCell 可 persist', () => {
    for (const row of ne.rows.value) {
      ne.updateCell(row.rowId, 'compliance', 'compliant')
    }
    expect(saved.length).toBeGreaterThan(0)

    saved.length = 0
    expect(ne.saveValidated()).toBe(true)
    expect(saved.length).toBeGreaterThan(0)
  })
})
