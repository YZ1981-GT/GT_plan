/**
 * F1 上市/国企披露表挂载：防止 section1Rows / agingRows spread 崩溃
 */
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { computed } from 'vue'
import F1TabDisclosureListed from '../f1/F1TabDisclosureListed.vue'
import F1TabDisclosureSoe from '../f1/F1TabDisclosureSoe.vue'
import { useF1DisclosureListed } from '../composables/useF1DisclosureListed'
import { ref } from 'vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

vi.mock('@/services/apiProxy', () => ({ api: { post: vi.fn(), get: vi.fn() } }))
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>()
  return { ...actual, ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() } }
})

const tableStub = {
  props: ['data'],
  template: '<div class="el-table-stub" :data-len="(data || []).length" />',
}

const stubs = {
  GtIndexChip: true,
  F1SheetAttachments: true,
  F1DisclosureUsageGuide: true,
  'el-table': tableStub,
  'el-table-column': true,
  'el-button': true,
  'el-alert': true,
  'el-tag': true,
  'el-tooltip': true,
  'el-input': true,
  'el-input-number': true,
  'el-popconfirm': true,
}

function makeCrossSheet() {
  return {
    agingAggregation: computed(() => ({
      within1: 100,
      y1to2: 0,
      y2to3: 0,
      over3: 0,
      prior_within1: 50,
      prior_y1to2: 0,
      prior_y2to3: 0,
      prior_over3: 0,
    })),
    longTermRows: computed(() => []),
    natureAggregation: computed(() => ({})),
    adjudicationForDisclosure: computed(() => ({
      natureAggregation: {},
      agingAggregation: {},
      longTermRows: [],
    })),
  }
}

describe('F1 disclosure mount', () => {
  it('上市披露表可挂载且表格 data 可迭代', async () => {
    const w = mount(F1TabDisclosureListed, {
      props: {
        allResponses: new Map(),
        wpId: 'w1',
        projectId: 'p1',
        isReadonly: false,
        crossSheet: makeCrossSheet(),
        applicableStandards: ['listed_standalone'],
        saveImmediate: vi.fn(),
        debouncedSave: vi.fn(),
      },
      global: { stubs },
    })
    await flushPromises()
    expect(w.find('.f1-disclosure-listed').exists()).toBe(true)
    expect(w.findAll('.el-table-stub').length).toBeGreaterThan(0)
  })

  it('国企披露表可挂载', async () => {
    const w = mount(F1TabDisclosureSoe, {
      props: {
        allResponses: new Map(),
        wpId: 'w1',
        projectId: 'p1',
        isReadonly: false,
        crossSheet: makeCrossSheet(),
        applicableStandards: ['soe_standalone'],
        saveImmediate: vi.fn(),
        debouncedSave: vi.fn(),
      },
      global: { stubs },
    })
    await flushPromises()
    expect(w.find('.f1-disclosure-soe').exists()).toBe(true)
  })

  it('composable 同时导出 section1Rows 别名（兼容旧模板）', () => {
    vi.spyOn(window, 'addEventListener').mockImplementation(() => undefined)
    vi.spyOn(window, 'removeEventListener').mockImplementation(() => undefined)
    const api = useF1DisclosureListed({
      allResponses: ref(new Map<string, ChecklistResponse>()),
      wpId: ref('wp-1'),
      projectId: ref('p1'),
      saveImmediate: vi.fn(),
      debouncedSave: vi.fn(),
      crossSheet: makeCrossSheet() as any,
      isReadonly: ref(false),
      applicableStandards: ref(['listed_standalone']),
    })
    expect(Array.isArray(api.section1Rows.value)).toBe(true)
    expect(api.section1Rows.value).toEqual(api.agingRows.value)
    expect(api.section1Subtotal.value.rowId).toBe('__subtotal__')
  })
})
