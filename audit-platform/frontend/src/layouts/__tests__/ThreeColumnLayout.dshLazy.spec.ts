import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

const { route, dshModule, stubModule } = vi.hoisted(() => ({
  route: {
    path: '/projects/p1/workpapers',
    params: { projectId: 'p1' } as Record<string, string>,
    query: {} as Record<string, string>,
  },
  dshModule: { loads: 0 },
  stubModule: async (name: string, props: string[] = []) => {
    const { defineComponent } = await import('vue')
    return { default: defineComponent({ name, props, render: () => null }) }
  },
}))

vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ username: 'admin', logout: vi.fn() }) }))
vi.mock('@/stores/displayPrefs', () => ({
  useDisplayPrefsStore: () => ({
    amountUnit: 'yuan', fontSize: 'md', decimals: 2, unitOptions: [], fontOptions: [],
    gridEditModeOptions: [], gridEditMode: 'excel',
  }),
}))
vi.mock('@/stores/roleContext', () => ({ useRoleContextStore: () => ({ effectiveRole: 'partner' }) }))
vi.mock('@/composables/useTheme', () => ({ useTheme: () => ({ isDark: false, toggle: vi.fn() }) }))
vi.mock('@/composables/useAdaptivePoll', () => ({ useAdaptivePoll: () => ({ start: vi.fn(), poke: vi.fn(), dispose: vi.fn() }) }))
vi.mock('@/services/sse/projectEventStream', () => ({
  subscribeProjectEvent: () => ({ close: vi.fn() }), WILDCARD_EVENT: '*',
}))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn().mockResolvedValue({ trees: [], independents: [] }) } }))
vi.mock('@/services/auditPlatformApi', () => ({ getProject: vi.fn() }))
vi.mock('@/utils/operationHistory', () => ({ operationHistory: { undo: vi.fn() } }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { emit: vi.fn(), on: vi.fn(), off: vi.fn() } }))

vi.mock('@/components/formula/FormulaManagerDialog.vue', () => stubModule('FormulaManagerDialog'))
vi.mock('@/components/formula/GtRefreshScopeDialog.vue', () => stubModule('GtRefreshScopeDialog'))
vi.mock('@/components/query/CustomQueryDialog.vue', () => stubModule('CustomQueryDialog'))
vi.mock('@/components/formula/settings/FormulaPendingSyncDialog.vue', () => stubModule('FormulaPendingSyncDialog'))
vi.mock('@/components/common/ShortcutHelpDialog.vue', () => stubModule('ShortcutHelpDialog'))
vi.mock('@/shell/formula/WorkpaperPrimaryCapabilitiesHost.vue', () => stubModule('WorkpaperPrimaryCapabilitiesHost'))
vi.mock('@/components/DegradedBanner.vue', () => stubModule('DegradedBanner'))

vi.mock('@/components/ai/DshPanel.vue', () => {
  dshModule.loads += 1
  throw new Error('模拟 AI 可选模块加载失败')
})

import ThreeColumnLayout from '../ThreeColumnLayout.vue'

beforeEach(() => {
  setActivePinia(createPinia())
  dshModule.loads = 0
  localStorage.clear()
})

describe('ThreeColumnLayout — AI 可选模块故障隔离', () => {
  it('关闭时不加载；首次打开失败只显示中文局部失败态，主布局仍可用', async () => {
    const errorHandler = vi.fn()
    const wrapper = mount(ThreeColumnLayout, {
      slots: { detail: '<div data-testid="main-detail">底稿主内容</div>' },
      global: {
        plugins: [ElementPlus],
        config: { errorHandler },
        stubs: { 'router-view': true },
      },
    })
    await flushPromises()

    expect(dshModule.loads).toBe(0)
    expect(wrapper.get('[data-testid="main-detail"]').text()).toBe('底稿主内容')
    expect(wrapper.find('.dsh-panel-load-error').exists()).toBe(false)

    await wrapper.get('button[aria-label="打开 AI 助手"]').trigger('click')
    await flushPromises()

    expect(dshModule.loads).toBe(1)
    expect(wrapper.get('.dsh-panel-load-error').text()).toContain('AI 助手加载失败')
    expect(wrapper.get('.dsh-panel-load-error').text()).toContain('项目页面仍可继续使用')
    expect(wrapper.get('[data-testid="main-detail"]').text()).toBe('底稿主内容')

    await wrapper.get('.dsh-panel-load-error__close').trigger('click')
    await flushPromises()
    expect(wrapper.find('.dsh-panel-load-error').exists()).toBe(false)
    expect(wrapper.get('[data-testid="main-detail"]').exists()).toBe(true)
    wrapper.unmount()
  })
})
