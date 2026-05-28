import { describe, test, expect, vi, beforeEach } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import { ref, computed } from 'vue'
import { EDITOR_CONTEXT_KEY, createMockEditorContext } from '@/composables/useEditorContext'

// ─── Mock editorDialogConfig ─────────────────────────────────────────────────
vi.mock('@/composables/editorDialogConfig', () => ({
  TEMPLATE_DIALOGS: [
    {
      key: 'inventoryStocktake',
      title: '存货监盘',
      componentPath: '@/components/workpaper/InventoryStocktakeDialog.vue',
      triggers: ['cycle:F'],
      cycle: 'F',
      dialogStateKey: 'stocktake',
      component: () => Promise.resolve({ default: {} }),
      triggerButton: { icon: '📦', label: '开始监盘', type: 'primary', plain: true },
      triggerVisible: (wpCode: string) => /^F2-(2[1-6])(\b|-|$)/.test(wpCode.toUpperCase()),
      propsFactory: (ctx: any) => ({ projectId: ctx.projectId }),
    },
    {
      key: 'depreciationCalc',
      title: '折旧自动测算',
      componentPath: '@/components/workpaper/DepreciationCalcDialog.vue',
      triggers: ['cycle:H'],
      cycle: 'H',
      dialogStateKey: 'depreciationCalc',
      component: () => Promise.resolve({ default: {} }),
      triggerButton: { icon: '🧮', label: '自动计算', type: 'primary', plain: true },
      triggerVisible: (wpCode: string) => /^H1-12(\b|-|$)/.test(wpCode.toUpperCase()),
      propsFactory: (ctx: any) => ({ projectId: ctx.projectId }),
    },
    {
      key: 'noTrigger',
      title: '无 trigger 配置',
      componentPath: '@/components/workpaper/NoTriggerDialog.vue',
      triggers: ['cycle:K'],
      cycle: 'K',
      dialogStateKey: 'expenseAnalysis',
      component: () => Promise.resolve({ default: {} }),
      // 无 triggerButton / triggerVisible → 不应出现在 trigger panel
    },
  ],
}))

// ─── Import component ────────────────────────────────────────────────────────
import CycleTriggerPanel from '@/views/workpaper-editor/CycleTriggerPanel.vue'

describe('CycleTriggerPanel', () => {
  const noop = () => { /* noop */ }

  function createMockCycleDialogs() {
    const mockEntry = { visible: ref(false), trigger: computed(() => false), onApplied: noop }
    return {
      stocktake: { visible: ref(false), trigger: computed(() => false), onApplied: noop },
      valuation: { visible: ref(false), trigger: computed(() => false), loading: ref(false) },
      impairment: mockEntry,
      hStocktake: mockEntry,
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
    }
  }

  function mountComponent(wpCode = 'F2-21', sheetNavActiveId = 'sheet-1') {
    const ctx = createMockEditorContext()
    const cycleDialogs = createMockCycleDialogs()

    return shallowMount(CycleTriggerPanel, {
      props: {
        wpDetail: { wp_code: wpCode, wp_name: '测试底稿', status: 'draft' } as any,
        cycleType: ctx.cycleType,
        cycleDialogs: cycleDialogs as any,
        sheetNavActiveId,
        iCycle: {},
        gCycle: {},
        kCycle: {},
        lCycle: {},
        mCycle: {},
        nCycle: {},
        fCycle: {},
      },
      global: {
        provide: { [EDITOR_CONTEXT_KEY as symbol]: ctx },
        stubs: {
          ElButton: {
            template: '<button @click="$emit(\'click\')"><slot /></button>',
            props: ['type', 'plain', 'size'],
          },
        },
      },
    })
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('默认渲染：wpCode=F2-21 时显示匹配的 trigger 按钮', async () => {
    const wrapper = mountComponent('F2-21')
    await flushPromises()

    // F2-21 匹配 inventoryStocktake 的 triggerVisible
    expect(wrapper.text()).toContain('开始监盘')
    // H1-12 不匹配当前 wpCode
    expect(wrapper.text()).not.toContain('自动计算')
  })

  test('trigger 按钮点击 emit open-dialog 事件', async () => {
    const wrapper = mountComponent('F2-21')
    await flushPromises()

    // 点击"开始监盘"按钮
    const btn = wrapper.find('button')
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')

    // 应 emit 'open-dialog' 事件，携带 dialog key
    const emitted = wrapper.emitted('open-dialog')
    expect(emitted).toBeTruthy()
    expect(emitted![0]).toEqual(['inventoryStocktake'])
  })
})
