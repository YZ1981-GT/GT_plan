/**
 * 项目设置中心「年度准则」页的审计年度下拉（spec post-push-residual-defect-closure 6.5.4 补测）。
 *
 * 原先表单年度初值是 0、项目 store 年度初值去年：没填审计年度的项目打开设置页，年度下拉先显示 0、再显示去年。
 * 现在：取到项目上下文之前为空（显示「选择年度」）；项目没填年度保持为空；填了年度显示该年度。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

const { getProject, apiGet } = vi.hoisted(() => ({ getProject: vi.fn(), apiGet: vi.fn() }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'p1' }, query: { tab: 'standard' } }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/composables/usePermissionMatrix', async () => {
  const { ref } = await import('vue')
  return { usePermissionMatrix: () => ({ can: () => true, whyCannot: () => '', currentRole: ref('manager') }) }
})
vi.mock('@/services/auditPlatformApi', () => ({ getProject: (...a: unknown[]) => getProject(...a) }))
vi.mock('@/services/apiProxy', () => ({ api: { get: (...a: unknown[]) => apiGet(...a), put: vi.fn() } }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { emit: vi.fn(), on: vi.fn(), off: vi.fn() } }))

import ProjectSettingsCenter from '../ProjectSettingsCenter.vue'
import { useProjectStore } from '@/stores/project'

const STUBS = {
  GtPageShell: { template: '<div class="shell"><slot name="context" /><slot /></div>' },
  ProjectContextBar: true,
  AgingConfigDialog: true,
}

function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((res) => { resolve = res })
  return { promise, resolve }
}

const mountCenter = () => mount(ProjectSettingsCenter, { global: { plugins: [ElementPlus], stubs: STUBS } })

/** 「审计年度」那一项下拉当前显示的文字，以及是否处于占位状态（没有值） */
function yearSelect(w: ReturnType<typeof mountCenter>) {
  const item = w.findAll('.el-form-item').find((fi) => fi.find('.el-form-item__label').text() === '审计年度')
  expect(item, '找不到「审计年度」表单项').toBeTruthy()
  const shown = item!.find('.el-select__placeholder')
  return { text: shown.text(), placeholder: shown.classes().includes('is-transparent') }
}

beforeEach(() => {
  setActivePinia(createPinia())
  getProject.mockReset()
  apiGet.mockReset()
  apiGet.mockResolvedValue({}) // 年份列表 / 我的角色 / 成员列表：空
})

describe('项目设置中心的审计年度下拉', () => {
  it('取到项目上下文之前：年度为空，显示「选择年度」（原先先显示 0）', async () => {
    const d = deferred<any>()
    getProject.mockReturnValue(d.promise)
    const w = mountCenter()
    await flushPromises()
    expect(yearSelect(w)).toEqual({ text: '选择年度', placeholder: true })
    d.resolve({ id: 'p1', client_name: '【测试】甲', audit_year: 2025 })
    await flushPromises()
    expect(yearSelect(w)).toEqual({ text: '2025 年度', placeholder: false })
  })

  it('项目没填审计年度：保持为空，不显示去年', async () => {
    getProject.mockResolvedValue({ id: 'p1', client_name: '【测试】甲', name: '测试客户' })
    const w = mountCenter()
    await flushPromises()
    expect(getProject).toHaveBeenCalled()
    expect(useProjectStore().year).toBeNull()
    expect(yearSelect(w)).toEqual({ text: '选择年度', placeholder: true })
  })

  it('项目上下文已在 store 里：不再重取，直接显示 store 的年度', async () => {
    const store = useProjectStore()
    store.projectId = 'p1'
    store.year = 2024
    const w = mountCenter()
    await flushPromises()
    expect(getProject).not.toHaveBeenCalled()
    expect(yearSelect(w)).toEqual({ text: '2024 年度', placeholder: false })
  })
})
