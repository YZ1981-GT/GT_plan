/** 项目「审计抽样 → 抽凭概览」展示当前账套各底稿存续核对未确认数（任务 17，需求 8.3）。 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

vi.mock('vue-router', () => ({ useRoute: () => ({ params: { projectId: 'project-1' } }) }))
vi.mock('@/services/commonApi', () => ({ cutoffTest: vi.fn(), agingAnalysis: vi.fn(), monthlyDetail: vi.fn() }))
vi.mock('@/composables/useEditMode', () => ({ useEditMode: () => ({
  isEditing: { value: false }, isDirty: { value: false }, enterEdit: vi.fn(), exitEdit: vi.fn(), markDirty: vi.fn(), clearDirty: vi.fn(),
}) }))
vi.mock('@/utils/http', () => ({ default: { get: vi.fn() } }))

import http from '@/utils/http'
import { ElMessage } from 'element-plus'
import { useProjectStore } from '@/stores/project'
import SamplingEnhanced from '../SamplingEnhanced.vue'

const get = (http as unknown as { get: ReturnType<typeof vi.fn> }).get
const messageError = vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as any)

beforeEach(() => {
  vi.clearAllMocks()
  useProjectStore().year = 2025
  get.mockResolvedValue({ data: { data: {
    year: 2025, active_dataset_id: 'dataset-12345678', duplicated: [{ voucher_no: '0012' }],
    by_workpaper: [
      { working_paper_id: 'wp-1', wp_code: 'J1', wp_name: '应付职工薪酬检查', batch_count: 2, sample_count: 5,
        interim_survival_unacked: 2, interim_survival_counts: { unchanged: 1, modified: 1, renumbered: 1, deleted: 0 } },
      { working_paper_id: 'wp-2', wp_code: 'E1', wp_name: '货币资金检查', batch_count: 1, sample_count: 3,
        interim_survival_unacked: 0, interim_survival_counts: { unchanged: 3, modified: 0, renumbered: 0, deleted: 0 } },
    ],
  } } })
})

describe('SamplingEnhanced 抽凭概览', () => {
  async function page() {
    const w = mount(SamplingEnhanced, {
      global: {
        plugins: [ElementPlus],
        stubs: { GtPageHeader: { template: '<div>审计抽样</div>' } },
        directives: { permission: () => undefined },
      },
    })
    await flushPromises()
    return w
  }

  it('挂载即按项目和年度读取，表格显示每张底稿未确认变化与四类计数', async () => {
    const w = await page()
    expect(get).toHaveBeenCalledWith('/api/projects/project-1/sampling/voucher-coverage',
      expect.objectContaining({ params: { year: 2025 }, _silent: true }))
    const tab = w.findAll('.el-tabs__item').find(x => x.text().includes('抽凭概览'))!
    await tab.trigger('click')
    await flushPromises()
    const text = w.text()
    expect(text).toContain('当前账套 dataset-')
    expect(text).toContain('J1')
    expect(text).toContain('2 条变化未确认')
    expect(text).toContain('未变 1 / 已改 1 / 疑似改号 1 / 已删 0')
    expect(text).toContain('已核对，无待确认变化')
    expect(text).toContain('另有 1 张凭证被多张底稿抽取')
  })

  it('读取失败明确提示', async () => {
    get.mockRejectedValueOnce(new Error('network'))
    await page()
    expect(messageError).toHaveBeenCalledWith('抽凭概览读取失败，请重试')
  })
})
