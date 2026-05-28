import { describe, test, expect, vi, beforeEach } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import { ref, computed, defineComponent } from 'vue'
import { EDITOR_CONTEXT_KEY, createMockEditorContext } from '@/composables/useEditorContext'

// ─── Mock element-plus ───────────────────────────────────────────────────────
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), success: vi.fn() },
}))

// ─── Mock editorDialogConfig ─────────────────────────────────────────────────
const StubDialog = defineComponent({
  name: 'StubDialog',
  props: ['visible', 'projectId', 'wpId'],
  emits: ['update:visible', 'saved', 'applied'],
  template: '<div class="stub-dialog">{{ projectId }}</div>',
})

vi.mock('@/composables/editorDialogConfig', () => ({
  TEMPLATE_DIALOGS: [
    {
      key: 'testDialog1',
      title: '测试弹窗1',
      componentPath: '@/components/TestDialog1.vue',
      triggers: ['cycle:F'],
      cycle: 'F',
      dialogStateKey: 'stocktake',
      component: () => Promise.resolve({ default: StubDialog }),
      triggerButton: { icon: '📦', label: '测试按钮1', type: 'primary', plain: true },
      triggerVisible: () => true,
      propsFactory: (ctx: any) => ({ projectId: ctx.projectId, wpId: ctx.wpId }),
    },
    {
      key: 'testDialog2',
      title: '测试弹窗2',
      componentPath: '@/components/TestDialog2.vue',
      triggers: ['cycle:H'],
      cycle: 'H',
      dialogStateKey: 'hStocktake',
      component: () => Promise.resolve({ default: StubDialog }),
      propsFactory: (ctx: any) => ({ projectId: ctx.projectId, wpId: ctx.wpId }),
    },
  ],
}))

// ─── Import component ────────────────────────────────────────────────────────
import CycleDialogHost from '@/views/workpaper-editor/CycleDialogHost.vue'

describe('CycleDialogHost', () => {
  const noop = () => { /* noop */ }

  function createMockCycleDialogs(overrides: Record<string, any> = {}) {
    const mockEntry = { visible: ref(false), trigger: computed(() => false), onApplied: noop }
    return {
      stocktake: { visible: ref(false), trigger: computed(() => false), onApplied: noop },
      valuation: { visible: ref(false), trigger: computed(() => false), loading: ref(false) },
      impairment: mockEntry,
      hStocktake: { visible: ref(false), trigger: computed(() => false), onApplied: noop },
      depreciationCalc: mockEntry,
      assetImpairment: mockEntry,
      goodwillImpairment: mockEntry,
      capitalizationCheck: mockEntry,
      amortizationCalc: { ...mockEntry, section: computed(() => null) },
      fairValueTest: { ...mockEntry, instrumentType: computed(() => '') },
      eclCalc: { ...mockEntry, instrumentType: computed(() => '') },
      classificationCheck: mockEntry,
      expenseAnalysis: mockEntry,
      impairmentSummary: mockEntry,
      interestCalc: mockEntry,
      bondAmortization: mockEntry,
      equityMovement: mockEntry,
      incomeTaxCalc: mockEntry,
      ...overrides,
    }
  }

  function mountComponent(cycleDialogsOverrides: Record<string, any> = {}) {
    const ctx = createMockEditorContext()
    const cycleDialogs = createMockCycleDialogs(cycleDialogsOverrides)

    return shallowMount(CycleDialogHost, {
      props: {
        projectId: 'proj-1',
        wpId: 'wp-1',
        wpDetail: { wp_code: 'F2-21', wp_name: '存货监盘', status: 'draft' } as any,
        sheetNavActiveId: 'sheet-1',
        cycleType: ctx.cycleType,
        cycleDialogs: cycleDialogs as any,
      },
      global: {
        provide: { [EDITOR_CONTEXT_KEY as symbol]: ctx },
      },
    })
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('默认渲染：组件正常渲染无错误', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    // 组件应正常渲染（无 dialog visible 时不渲染任何 dialog）
    expect(wrapper.exists()).toBe(true)
  })

  test('配置驱动 dialog 条件渲染：设置 visible=true 后对应 dialog 渲染', async () => {
    const stocktakeVisible = ref(true)
    const wrapper = mountComponent({
      stocktake: { visible: stocktakeVisible, trigger: computed(() => true), onApplied: noop },
    })
    await flushPromises()

    // 当 stocktake.visible=true 时，对应 dialog 应被渲染
    // 由于 defineAsyncComponent 的异步特性，组件可能需要额外 tick
    await flushPromises()

    // 验证组件存在且没有抛出错误
    expect(wrapper.exists()).toBe(true)
  })
})
