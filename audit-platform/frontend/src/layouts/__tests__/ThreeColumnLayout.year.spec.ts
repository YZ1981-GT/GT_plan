/**
 * 三栏布局全局弹窗（公式管理 / 一键刷新 / 自定义查询）的审计年度（spec post-push-residual-defect-closure 6.5.3 补测）。
 *
 * 原先 `Number(route.query.year) || 去年`：路由不带年度时三个全局弹窗一律按去年取数 / 刷新 / 查询。
 * 现在：年度 = 路由 → 项目 store；都没有为 null —— 一键刷新、自定义查询收到 null 自己拦下（各自用例已覆盖），
 * 公式管理不传年度；页面带上下文打开公式管理时，上下文里的年度优先。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

const { route, busOn, stubModule } = vi.hoisted(() => ({
  route: {
    path: '/projects/p1/workpapers',
    params: { projectId: 'p1' } as Record<string, string>,
    query: {} as Record<string, string>,
  },
  busOn: [] as Array<[string, (payload?: unknown) => void]>,
  /** 只声明 props 的空组件：三个弹窗与其余重组件不真挂（依赖很重），只看收到的 props */
  stubModule: async (name: string, props: string[] = []) => {
    const { defineComponent } = await import('vue')
    return { default: defineComponent({ name, props, render: () => null }) }
  },
}))

vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ username: 'admin', logout: vi.fn() }) }))
vi.mock('@/stores/displayPrefs', () => ({
  useDisplayPrefsStore: () => ({ amountUnit: 'yuan', fontSize: 'md', decimals: 2, unitOptions: [], fontOptions: [] }),
}))
vi.mock('@/stores/roleContext', () => ({ useRoleContextStore: () => ({ effectiveRole: 'partner' }) }))
vi.mock('@/composables/useTheme', () => ({ useTheme: () => ({ isDark: false, toggle: vi.fn() }) }))
vi.mock('@/composables/useAdaptivePoll', () => ({
  useAdaptivePoll: () => ({ start: vi.fn(), poke: vi.fn(), dispose: vi.fn() }),
}))
vi.mock('@/services/sse/projectEventStream', () => ({
  subscribeProjectEvent: () => ({ close: vi.fn() }),
  WILDCARD_EVENT: '*',
}))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn().mockResolvedValue({ trees: [], independents: [] }) } }))
vi.mock('@/services/auditPlatformApi', () => ({ getProject: vi.fn() }))
vi.mock('@/utils/operationHistory', () => ({ operationHistory: { undo: vi.fn() } }))
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: vi.fn(),
    on: (name: string, fn: (payload?: unknown) => void) => { busOn.push([name, fn]) },
    off: vi.fn(),
  },
}))
vi.mock('@/components/formula/FormulaManagerDialog.vue', () => stubModule('FormulaManagerDialog', ['modelValue', 'projectId', 'year', 'scope']))
vi.mock('@/components/formula/GtRefreshScopeDialog.vue', () => stubModule('GtRefreshScopeDialog', ['projectId', 'year']))
vi.mock('@/components/query/CustomQueryDialog.vue', () => stubModule('CustomQueryDialog', ['modelValue', 'projectId', 'year']))
vi.mock('@/components/formula/settings/FormulaPendingSyncDialog.vue', () => stubModule('FormulaPendingSyncDialog', ['projectId']))
vi.mock('@/components/common/ShortcutHelpDialog.vue', () => stubModule('ShortcutHelpDialog'))
vi.mock('@/components/ai/DshPanel.vue', () => stubModule('DshPanel'))
vi.mock('@/shell/formula/WorkpaperPrimaryCapabilitiesHost.vue', () => stubModule('WorkpaperPrimaryCapabilitiesHost'))
vi.mock('@/components/DegradedBanner.vue', () => stubModule('DegradedBanner'))

import ThreeColumnLayout from '../ThreeColumnLayout.vue'
import { useProjectStore } from '@/stores/project'

const YEAR_CARRIERS = ['FormulaManagerDialog', 'GtRefreshScopeDialog', 'CustomQueryDialog'] as const

function mountLayout() {
  return shallowMount(ThreeColumnLayout, { global: { plugins: [ElementPlus], stubs: { 'router-view': true } } })
}

/** 三个全局弹窗各自收到的年度 */
function yearsOf(w: ReturnType<typeof mountLayout>) {
  return Object.fromEntries(YEAR_CARRIERS.map((name) => {
    const c = w.findComponent({ name })
    expect(c.exists(), `${name} 没挂在布局上`).toBe(true)
    return [name, c.props('year')]
  })) as Record<(typeof YEAR_CARRIERS)[number], unknown>
}

beforeEach(() => {
  setActivePinia(createPinia())
  route.query = {}
  busOn.length = 0
  localStorage.clear()
})

describe('三栏布局全局弹窗的审计年度', () => {
  it('路由带年度：三个弹窗都按路由年度（store 年度不同也以路由为准）', async () => {
    route.query = { year: '2024' }
    useProjectStore().year = 2023
    const w = mountLayout()
    await flushPromises()
    expect(yearsOf(w)).toEqual({ FormulaManagerDialog: 2024, GtRefreshScopeDialog: 2024, CustomQueryDialog: 2024 })
  })

  it('路由不带年度：取项目 store 的年度', async () => {
    useProjectStore().year = 2023
    const w = mountLayout()
    await flushPromises()
    expect(yearsOf(w)).toEqual({ FormulaManagerDialog: 2023, GtRefreshScopeDialog: 2023, CustomQueryDialog: 2023 })
  })

  it('路由与 store 都没有年度：一键刷新 / 自定义查询收到 null，公式管理不传年度 —— 不再按去年', async () => {
    const w = mountLayout()
    await flushPromises()
    expect(useProjectStore().year).toBeNull()
    expect(yearsOf(w)).toEqual({ FormulaManagerDialog: undefined, GtRefreshScopeDialog: null, CustomQueryDialog: null })
  })

  it('路由带的年度无效（非数字 / 早于 2001）：当作没带，取 store 年度', async () => {
    route.query = { year: 'abc' }
    useProjectStore().year = 2023
    const w = mountLayout()
    await flushPromises()
    expect(yearsOf(w).GtRefreshScopeDialog).toBe(2023)
  })

  it('项目信息后到：store 定下年度后弹窗跟着更新；切到没填年度的项目又回到空', async () => {
    const w = mountLayout()
    await flushPromises()
    const store = useProjectStore()
    store.year = 2025
    await nextTick()
    expect(yearsOf(w)).toEqual({ FormulaManagerDialog: 2025, GtRefreshScopeDialog: 2025, CustomQueryDialog: 2025 })
    store.year = null
    await nextTick()
    expect(yearsOf(w)).toEqual({ FormulaManagerDialog: undefined, GtRefreshScopeDialog: null, CustomQueryDialog: null })
  })

  it('页面带上下文打开公式管理：上下文年度优先；上下文没带年度时用路由 → store', async () => {
    useProjectStore().year = 2023
    const w = mountLayout()
    await flushPromises()
    const open = busOn.find(([name]) => name === 'open-formula-manager')?.[1]
    expect(open, '布局没订阅 open-formula-manager').toBeTypeOf('function')
    open!({ projectId: 'p1', year: 2021, scope: 'report' })
    await nextTick()
    expect(w.findComponent({ name: 'FormulaManagerDialog' }).props('year')).toBe(2021)
    open!({ projectId: 'p1', scope: 'report' })
    await nextTick()
    expect(w.findComponent({ name: 'FormulaManagerDialog' }).props('year')).toBe(2023)
  })
})
