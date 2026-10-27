/**
 * 自定义查询的年度（spec post-push-residual-defect-closure 6.5.3）：
 * 查询端点 year 必填。原先三栏布局把去年当年度传进来；现在项目没填审计年度时传 null，
 * 选了项目却没有年度 ⇒ 提示先填年度、不发查询。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import ElementPlus from 'element-plus'

const { post, warning } = vi.hoisted(() => ({ post: vi.fn(), warning: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/services/apiProxy', () => ({ api: { post: (...a: unknown[]) => post(...a), get: vi.fn().mockResolvedValue([]) } }))
vi.mock('@/utils/http', () => ({ default: { get: vi.fn().mockResolvedValue({ data: [] }), post: vi.fn() } }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { role: 'admin' }, token: 't' }) }))
vi.mock('@/services/commonApi', () => ({
  listProjectsWithProgress: vi.fn().mockResolvedValue([{ id: 'p1', name: '【测试】无年度', audit_year: null }]),
}))
vi.mock('@/views/AdvancedQueryBuilder.vue', () => ({ default: defineComponent({ setup: () => () => h('div') }) }))
vi.mock('@/components/query/SheetCellRangePicker.vue', () => ({ default: defineComponent({ setup: () => () => h('div') }) }))
vi.mock('element-plus', async (orig) => {
  const mod = await orig<typeof import('element-plus')>()
  return { ...mod, ElMessage: Object.assign(vi.fn(), { warning, success: vi.fn(), info: vi.fn(), error: vi.fn() }) }
})

import CustomQueryDialog from '../CustomQueryDialog.vue'

function mountDialog(year: number | null) {
  return mount(CustomQueryDialog, {
    props: { modelValue: true, projectId: 'p1', year },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
}

beforeEach(() => {
  post.mockReset().mockResolvedValue({ rows: [], columns: [] })
  warning.mockReset()
})

describe('CustomQueryDialog 年度', () => {
  it('选了项目、项目没填审计年度：提示先填年度，不发查询', async () => {
    const w = mountDialog(null)
    await flushPromises()
    await (w.vm as any).executeQuery()
    expect(post).not.toHaveBeenCalledWith('/api/custom-query/execute', expect.anything(), expect.anything())
    expect(warning).toHaveBeenCalledWith(expect.stringContaining('未设置审计年度'))
    w.unmount()
  })

  it('有年度：按该年度查', async () => {
    const w = mountDialog(2025)
    await flushPromises()
    await (w.vm as any).executeQuery()
    expect(post).toHaveBeenCalledWith('/api/custom-query/execute', expect.objectContaining({ project_id: 'p1', year: 2025 }), expect.anything())
    w.unmount()
  })
})
