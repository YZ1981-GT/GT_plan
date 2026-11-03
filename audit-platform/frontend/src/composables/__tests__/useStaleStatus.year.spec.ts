/**
 * useStaleStatus 重算年度（spec post-push-residual-defect-closure 6.5.3）：
 * 显式年度 > 项目 store；都没有 ⇒ 提示后不发（原先兜底去年 ⇒ 重算了别的年度）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'

const post = vi.fn()
const get = vi.fn()
const warning = vi.fn()
vi.mock('@/services/apiProxy', () => ({ api: { get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a) } }))
vi.mock('@/services/auditPlatformApi', () => ({ getProject: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessage: { warning: (...a: unknown[]) => warning(...a) } }))

import { useStaleStatus } from '../useStaleStatus'
import { useProjectStore } from '@/stores/project'
import { MISSING_AUDIT_YEAR_MESSAGE } from '@/composables/useProjectAuditYear'

function setup(year?: ReturnType<typeof ref<number | null>>) {
  let api!: ReturnType<typeof useStaleStatus>
  mount(defineComponent({ setup() { api = useStaleStatus(ref('p1'), year as any); return () => h('div') } }))
  return api
}

beforeEach(() => {
  setActivePinia(createPinia())
  post.mockReset().mockResolvedValue({ stale_resolution: { cleared: 1, refilled: 0, kept_stale: 0 } })
  get.mockReset().mockResolvedValue({ stale_count: 0 })
  warning.mockReset()
})

describe('useStaleStatus.recalc 年度', () => {
  it('显式年度优先', async () => {
    useProjectStore().year = 2025
    await setup(ref<number | null>(2024)).recalc()
    expect(post).toHaveBeenCalledWith('/api/projects/p1/trial-balance/recalc', {}, { params: { year: 2024 } })
  })

  it('没传年度：用项目 store 的年度', async () => {
    useProjectStore().year = 2025
    await setup().recalc()
    expect(post).toHaveBeenCalledWith('/api/projects/p1/trial-balance/recalc', {}, { params: { year: 2025 } })
  })

  it('都没有：提示「未设置审计年度」，不发重算', async () => {
    const result = await setup(ref<number | null>(null)).recalc()
    expect(result).toBeNull()
    expect(post).not.toHaveBeenCalled()
    expect(warning).toHaveBeenCalledWith(expect.stringContaining(MISSING_AUDIT_YEAR_MESSAGE))
  })
})
