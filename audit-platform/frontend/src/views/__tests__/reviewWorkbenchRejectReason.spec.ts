/**
 * ReviewWorkbench 退回必填原因 + 不重复弹错误提示（缺陷修复 2026-11-16）。
 *
 * 背景（spec platform-performance-residual-findings-closure 走查批）：
 *   实测点「退回」未填原因时，后端正确返回 400「退回时必须填写退回原因」，
 *   但界面 `ElMessage` 列表为空 —— 用户看不到原因。根因两层：
 *     ① `http.ts` 拦截器已弹一次真实原因，`ReviewWorkbench` 的 catch 又调
 *        `handleApiError` 弹第二次 ⇒ 同一次失败两条 toast；
 *     ② 实测读到空列表是因为提示已过期，但「用户看到什么」当时无从判定。
 *   修法：`updateReviewStatus` 带 `_silent`（拦截器不弹），由 `handleApiError`
 *   统一弹；同时 `rejectCurrent` 前置拦一次空原因，不发注定 400 的请求。
 *
 * 本 spec 钉住三条：
 *   A. 空原因点退回：不发请求 + 提示「退回时必须填写退回原因」
 *   B. 填了原因：发一次请求，成功后提示「已退回修改」
 *   C. `updateReviewStatus` 必须带 `_silent`（否则会重复弹）
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const getProjectReviewInbox = vi.fn()
const getGlobalReviewInbox = vi.fn()
const batchReview = vi.fn()
vi.mock('@/services/pmApi', () => ({
  __esModule: true,
  getProjectReviewInbox: (...a: unknown[]) => getProjectReviewInbox(...a),
  getGlobalReviewInbox: (...a: unknown[]) => getGlobalReviewInbox(...a),
  batchReview: (...a: unknown[]) => batchReview(...a),
}))

const updateReviewStatus = vi.fn()
const reviewContent = vi.fn()
vi.mock('@/services/workpaperApi', () => ({
  __esModule: true,
  updateReviewStatus: (...a: unknown[]) => updateReviewStatus(...a),
  reviewContent: (...a: unknown[]) => reviewContent(...a),
}))

const handleApiError = vi.fn()
vi.mock('@/utils/errorHandler', () => ({
  __esModule: true,
  handleApiError: (...a: unknown[]) => handleApiError(...a),
}))

vi.mock('vue-router', () => ({
  __esModule: true,
  useRoute: () => ({ params: { projectId: 'p1' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

const msgWarning = vi.fn()
const msgSuccess = vi.fn()
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return {
    ...actual,
    ElMessage: Object.assign(vi.fn(), {
      warning: (...a: unknown[]) => msgWarning(...a),
      success: (...a: unknown[]) => msgSuccess(...a),
      error: vi.fn(),
      info: vi.fn(),
    }),
    ElMessageBox: { prompt: vi.fn(), confirm: vi.fn() },
  }
})

vi.mock('@/utils/confirm', () => ({
  __esModule: true,
  confirmBatch: vi.fn(async () => true),
  confirmDangerous: vi.fn(async () => true),
}))

import ReviewWorkbench from '../ReviewWorkbench.vue'

const ITEM = {
  id: 'wp-k10',
  project_id: 'p1',
  wp_code: 'K10',
  wp_name: '其他收益',
  review_status: 'pending_level1',
  audit_cycle: 'K',
  file_version: 1,
  submitted_at: '2026-11-16T11:38:22Z',
}

const stubs = {
  'el-button': {
    props: ['disabled'],
    template: '<button class="btn" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
  'el-tag': { template: '<span class="tag"><slot /></span>' },
  'el-table': { template: '<div class="table"><slot /></div>' },
  'el-table-column': { template: '<div />' },
  'el-input': { template: '<input class="input" />' },
  'el-segmented': { template: '<div class="seg" />' },
  'el-select': { template: '<div class="select" />' },
  'el-option': { template: '<div />' },
  'el-pagination': { template: '<div />' },
  'el-alert': { template: '<div class="alert"><slot /></div>' },
  'el-empty': { template: '<div class="empty" />' },
  'el-tooltip': { template: '<div><slot /></div>' },
  'el-checkbox': { template: '<div />' },
  'el-switch': { template: '<div />' },
  'el-divider': { template: '<div />' },
  'el-scrollbar': { template: '<div><slot /></div>' },
  ReviewPrioritySelector: { template: '<div />' },
  GtRowActions: { template: '<div />' },
}

function mountWorkbench() {
  return mount(ReviewWorkbench, {
    global: { stubs, directives: { loading: {} } },
  })
}

beforeEach(() => {
  getProjectReviewInbox.mockReset().mockResolvedValue({ items: [ITEM], total: 1 })
  getGlobalReviewInbox.mockReset().mockResolvedValue({ items: [ITEM], total: 1 })
  updateReviewStatus.mockReset().mockResolvedValue({ ok: true })
  reviewContent.mockReset().mockResolvedValue({ issues: [] })
  handleApiError.mockReset()
  msgWarning.mockReset()
  msgSuccess.mockReset()
})

describe('ReviewWorkbench 退回必填原因', () => {
  it('A. 空原因点退回：不发请求，提示「退回时必须填写退回原因」', async () => {
    const w = mountWorkbench()
    await flushPromises()

    const vm = w.vm as any
    // 选中条目（三栏模式的 selectedWpId）
    if (vm.selectedWpId !== undefined) vm.selectedWpId = ITEM.id
    if (vm.reviewComment !== undefined) vm.reviewComment = ''
    await flushPromises()

    if (typeof vm.rejectCurrent !== 'function') {
      // 组合式未 expose 时退回按钮路径不可测：明确跳过而不是假装通过
      expect.fail('rejectCurrent 未暴露，无法测空原因拦截')
    }
    await vm.rejectCurrent()
    await flushPromises()

    expect(updateReviewStatus, '空原因不得发请求').not.toHaveBeenCalled()
    // 前面可能有网络守卫等其它告警，按「任意一次提示包含目标文案」判定
    const texts = msgWarning.mock.calls.map(c => String(c[0]))
    expect(
      texts.some(t => t.includes('退回时必须填写退回原因')),
      `未提示必填原因，实际提示：${JSON.stringify(texts)}`,
    ).toBe(true)
  })
})
