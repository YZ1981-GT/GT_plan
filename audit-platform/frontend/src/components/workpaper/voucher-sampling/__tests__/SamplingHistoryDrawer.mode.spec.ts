/**
 * 抽凭历史显示年审口径（spec voucher-identity-writeback-and-audit-phase 任务 15，需求 7.4）
 */
import { describe, it, expect } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import SamplingHistoryDrawer from '../SamplingHistoryDrawer.vue'
import type { ExtractionLogEntry } from '../../composables/useVoucherSampling'

function entry(id: string, mode: ExtractionLogEntry['finalPopulationMode']): ExtractionLogEntry {
  return {
    id, createdAt: '2025-12-01T08:00:00', userId: 'u1', samplingMethod: 'random', sampleCount: 3,
    coverageStats: { populationCount: 10, populationAmount: '100', sampleCount: 3, sampleAmount: '30',
      countCoverageRate: '30.00', amountCoverageRate: '30.00' },
    phase: mode ? 'final' : 'preliminary', fillMode: 'append', isUndone: false, batchId: null, extractionCriteria: {},
    finalPopulationMode: mode,
  }
}

describe('SamplingHistoryDrawer 年审口径', () => {
  it('有口径的批次显示口径标签，没有的不显示', async () => {
    const wrapper = mount(SamplingHistoryDrawer, {
      props: { visible: true, historyList: [entry('a', 'remaining'), entry('b', 'full_minus_interim'), entry('c', null)] },
      global: { plugins: [ElementPlus] },
      attachTo: document.body,
    })
    await flushPromises()
    const tags = Array.from(document.body.querySelectorAll('[data-testid="history-final-population-mode"]'))
      .map((el) => el.textContent?.trim())
    expect(tags).toEqual(['口径 a 只抽剩余期间', '口径 b 全年扣除预审已检样本'])
    wrapper.unmount()
  })
})
