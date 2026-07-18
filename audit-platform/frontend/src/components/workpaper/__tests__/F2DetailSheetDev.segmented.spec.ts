/**
 * Reproduce F2-10 with real el-segmented + GtIndexChip (no stubs for crash suspects)
 */
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, h, nextTick, ref, computed } from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'
import ElementPlus from 'element-plus'

vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: { data: { status: 'healthy', healthy: true } } }),
    post: vi.fn(),
    put: vi.fn(),
  },
}))

vi.mock('@/services/acnr', () => ({
  useAcnr: () => ({
    resolve: vi.fn().mockResolvedValue({ found: true }),
    resolveInstance: vi.fn(),
  }),
}))

vi.mock('../composables/useF2FormData', () => ({
  useF2FormData: () => ({
    allResponses: ref(new Map()),
    isLoading: ref(false),
    projectContext: ref({ audit_period_end: '2025-12-31', bs_date: '2025-12-31', applicable_standards: [] }),
    sheetCache: ref({}),
    loadAll: vi.fn().mockResolvedValue(undefined),
    getSheet: vi.fn().mockReturnValue({ rows: [] }),
    saveImmediate: vi.fn(),
    saveBatch: vi.fn(),
    saveItemsFromEvent: vi.fn(),
    debouncedSave: vi.fn(),
    writebackTrialBalance: vi.fn(),
  }),
  readRowJson: (r: any) => r?.remark ?? null,
}))

vi.mock('../composables/useF2CrossSheet', () => ({
  useF2CrossSheet: () => ({ categorySummaries: computed(() => []), hasDetailData: computed(() => false) }),
}))

vi.mock('../composables/useF2DualMode', async () => {
  const { ref } = await import('vue')
  return {
    useF2DualMode: () => ({
      currentMode: ref('html'),
      isOoAvailable: ref(false),
      ooConfig: ref(null),
      checking: ref(false),
      modeOptions: [
        { label: '结构化视图', value: 'html' },
        { label: '在线编辑', value: 'onlyoffice' },
      ],
      switchMode: vi.fn(),
      onModeChange: vi.fn(),
      checkOOHealth: vi.fn(),
    }),
  }
})

import ErrorBoundary from '@/components/ErrorBoundary.vue'
import GtF2InventoryMain from '../GtF2InventoryMain.vue'

describe('F2-10 with real ElementPlus segmented', () => {
  it('does not crash ErrorBoundary when rendering F2-10 HTML mode', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div/>' } },
        { path: '/projects/:projectId', component: { template: '<div/>' } },
      ],
    })
    await router.push('/projects/p1')

    const errors: string[] = []
    const wrap = mount(ErrorBoundary, {
      props: { resetKey: '八、开发产品F2-10' },
      slots: {
        default: () =>
          h(GtF2InventoryMain, {
            wpId: 'wp-1',
            projectId: 'p1',
            sheetName: '八、开发产品F2-10',
            readonly: false,
          }),
      },
      global: {
        plugins: [router, ElementPlus],
        stubs: {
          F2TabProcedure: true,
          F2TabAdjudication: true,
          F2TabDetailSummary: true,
          F2TabAdjustment: true,
          F2TabPolicy: true,
          F2TabOverallAnalysis: true,
          F2TabProductionSales: true,
          F2TabCostComparison: true,
          F2DetailSheetTurnover: true,
          F2DetailSheet: true,
          F2CutoffSheet: true,
          F2TabDisclosureListed: true,
          F2TabDisclosureSoe: true,
          GtGridSheet: true,
          GtOnlyOfficeSheet: true,
          // deliberately NOT stubbing: el-segmented, F2DetailSheetDev, GtIndexChip
        },
        config: {
          errorHandler(err: unknown) {
            errors.push(String(err))
          },
        },
      },
    })

    // Force isLoading false path - mocked formData already has isLoading false,
    // but GtF2InventoryMain has its OWN isLoading ref starting true.
    // Wait for onMounted load
    await flushPromises()
    await nextTick()
    await new Promise((r) => setTimeout(r, 50))
    await flushPromises()
    // defineAsyncComponent(F2DetailSheetDev) 需额外等待
    for (let i = 0; i < 20 && !/F2-10|开发产品/.test(wrap.text()); i++) {
      await new Promise((r) => setTimeout(r, 50))
      await flushPromises()
      await nextTick()
    }

    const errMsg = wrap.find('.gt-error-msg')
    if (errMsg.exists()) {
      throw new Error(`ErrorBoundary caught: ${errMsg.text()}; vue errors=${errors.join(' | ')}`)
    }
    expect(wrap.text()).toMatch(/F2-10|开发产品/)
  })
})
