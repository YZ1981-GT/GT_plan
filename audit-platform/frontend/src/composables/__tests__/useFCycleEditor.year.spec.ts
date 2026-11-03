/**
 * F2 计价测试自动抽样的年度（spec post-push-residual-defect-closure 6.5.3）：
 * 原先恒用今年（`new Date().getFullYear()`）⇒ 2025 年度项目在 2026 年抽的是 2026 的序时账；
 * 现在按项目审计年度，项目没填 ⇒ 提示后不发。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, ref } from 'vue'

const post = vi.fn()
const warning = vi.fn()
vi.mock('@/services/apiProxy', () => ({ api: { post: (...a: unknown[]) => post(...a) } }))
vi.mock('element-plus', () => ({ ElMessage: { warning: (...a: unknown[]) => warning(...a), success: vi.fn() } }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { emit: vi.fn() } }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

import { useFCycleEditor } from '../useFCycleEditor'
import { MISSING_AUDIT_YEAR_MESSAGE } from '@/composables/useProjectAuditYear'

function make(year?: number | null) {
  const flag = { visible: ref(false), trigger: computed(() => true), onApplied: vi.fn() }
  const cycleDialogs = { stocktake: flag, impairment: flag, valuation: { ...flag, loading: ref(false) } } as any
  return useFCycleEditor(
    ref({ wp_code: 'F2' }), ref('p1'), ref('wp1'), { activeSheetId: ref('F2-38') } as any, cycleDialogs,
    year === undefined ? undefined : ref(year),
  )
}

beforeEach(() => {
  post.mockReset().mockResolvedValue({ total_samples: 3, applied_to_sheet: 'F2-38' })
  warning.mockReset()
})

describe('useFCycleEditor.onTriggerValuationSample 年度', () => {
  it('按项目审计年度抽样', async () => {
    await make(2025).handlers.onTriggerValuationSample()
    expect(post).toHaveBeenCalledTimes(1)
    expect(post.mock.calls[0][1]).toMatchObject({ year: 2025, account_code: '1403' })
  })

  it.each([[null], [undefined]])('项目年度缺失（%s）：提示后不发', async (y) => {
    const f = make(y as number | null | undefined)
    await f.handlers.onTriggerValuationSample()
    expect(post).not.toHaveBeenCalled()
    expect(warning).toHaveBeenCalledWith(expect.stringContaining(MISSING_AUDIT_YEAR_MESSAGE))
    expect(f.valuationLoading.value).toBe(false)
  })
})
