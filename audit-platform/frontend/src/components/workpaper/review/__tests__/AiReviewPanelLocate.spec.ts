/**
 * AI 复核疑点点击来源：带单元格时走平台格定位，只有表名时切表（任务 10）。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { shallowMount } from '@vue/test-utils'

const emitSpy = vi.fn()
vi.mock('@/utils/eventBus', () => ({ eventBus: { emit: (...args: unknown[]) => emitSpy(...args), on: vi.fn(), off: vi.fn() } }))
vi.mock('@/composables/usePermissionMatrix', () => ({ usePermissionMatrix: () => ({ currentRole: ref('manager') }) }))

const card = {
  sheetName: '审定表D2-1',
  wpId: 'wp-1',
  passStatus: 'ai_findings_present',
  findingCount: 2,
  riskDistribution: { high: 1, medium: 1, low: 0 },
  promptSource: 'sheet',
  systemChecks: [],
  findings: [
    { id: 'f1', description: '期初余额待核对', risk_level: 'high', pass_status: false, category: '数据完整性', sheet_location: 'C8', suggestion: null },
    { id: 'f2', description: '附表合计待核对', risk_level: 'medium', pass_status: false, category: '勾稽', sheet_location: '明细表D2-2', suggestion: null },
  ],
}

vi.mock('../useReviewPanel', () => ({
  useReviewPanel: () => ({
    sheets: ref([card]),
    isReviewing: ref(false),
    progress: ref({ current: 0, total: 0, currentSheet: '' }),
    expandedSheet: ref('审定表D2-1'),
    startBatchReview: vi.fn(),
    cancelBatchReview: vi.fn(),
    reviewCurrentSheet: vi.fn(),
    exportReviewExcel: vi.fn(),
    toggleSheet: vi.fn(),
    updateFindingStatus: vi.fn(),
  }),
}))

import AiReviewPanel from '../AiReviewPanel.vue'

describe('AiReviewPanel 疑点来源定位', () => {
  beforeEach(() => { emitSpy.mockReset() })

  it('只写单元格时按疑点所属表发 workpaper:locate-cell', async () => {
    const wrapper = shallowMount(AiReviewPanel, { props: { projectId: 'p1', wpCodePrefix: 'D2', year: 2025 } })
    const locations = wrapper.findAll('.finding-item__location')
    expect(locations).toHaveLength(2)
    await locations[0].trigger('click')
    expect(emitSpy).toHaveBeenCalledWith('workpaper:locate-cell', {
      wpId: 'wp-1', sheetName: '审定表D2-1', cellRef: 'C8', label: '数据完整性',
    })
    expect(wrapper.emitted('navigate-sheet')).toBeUndefined()
  })

  it('只有表名时仍切到该表，不发格定位', async () => {
    const wrapper = shallowMount(AiReviewPanel, { props: { projectId: 'p1', wpCodePrefix: 'D2', year: 2025 } })
    await wrapper.findAll('.finding-item__location')[1].trigger('click')
    expect(emitSpy).not.toHaveBeenCalled()
    expect(wrapper.emitted('navigate-sheet')?.[0]).toEqual(['明细表D2-2'])
  })
})
