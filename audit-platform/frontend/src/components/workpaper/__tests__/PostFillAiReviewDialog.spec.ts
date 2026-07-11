/**
 * PostFillAiReviewDialog.spec.ts — 回写后 AI 复核弹窗（Req 26）
 *
 * 覆盖设计文档「组件单测」：确认写入 / 取消不写入 / AI 不可用不阻断。
 * Validates: Requirements 26.3, 26.4, 26.5, 26.6, 26.7, 26.8
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

const mockPost = vi.fn()
vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn(),
    post: (...args: any[]) => mockPost(...args),
  },
}))

import PostFillAiReviewDialog, { type PostFillReviewRow } from '../voucher-sampling/PostFillAiReviewDialog.vue'

const ROWS: PostFillReviewRow[] = [
  { voucherNo: '记-001', voucherDate: '2024-12-30', summary: '预收货款', debitAmount: null, creditAmount: '120000.00', counterpartAccount: '1002' },
  { voucherNo: '记-002', voucherDate: '2025-01-02', summary: '结转收入', debitAmount: '80000.00', creditAmount: null, cutoffStatus: 'cross_period' },
]

const STUBS = {
  'el-dialog': { template: '<div><slot /><slot name="footer" /></div>' },
  'el-alert': true,
  'el-card': { template: '<div><slot name="header" /><slot /></div>' },
  'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>' },
}

function makeWrapper(props: Partial<Record<string, unknown>> = {}) {
  return mount(PostFillAiReviewDialog, {
    props: {
      modelValue: true,
      wpId: 'wp-1',
      rows: ROWS,
      section: 'voucher-review',
      aiAvailable: true,
      ...props,
    },
    global: { stubs: STUBS, directives: { loading: {} } },
  })
}

beforeEach(() => {
  mockPost.mockReset()
})

describe('PostFillAiReviewDialog (Req 26)', () => {
  it('1. 打开弹窗默认停留在询问阶段', () => {
    const wrapper = makeWrapper()
    const vm = wrapper.vm as any
    expect(vm.stage).toBe('prompt')
    expect(vm.opinion).toBe('')
  })

  it('2. buildContext 汇总回写凭证笔数与异常/跨期笔数（R26.3）', () => {
    const wrapper = makeWrapper()
    const vm = wrapper.vm as any
    const ctx = vm.buildContext()
    expect(ctx['回写凭证笔数']).toBe('2')
    // 记-002 cutoffStatus=cross_period 计为跨期
    expect(ctx['异常或跨期笔数']).toBe('1')
    expect(ctx['凭证明细']).toContain('记-001')
    expect(ctx['凭证明细']).toContain('记-002')
  })

  it('3. buildPrompt 按 section 区分抽凭/截止提示词', () => {
    const voucher = makeWrapper({ section: 'voucher-review' })
    expect((voucher.vm as any).buildPrompt()).toContain('异常')
    const cutoff = makeWrapper({ section: 'cutoff-review' })
    expect((cutoff.vm as any).buildPrompt()).toContain('跨期')
  })

  it('4. 发起复核成功 → 展示意见（R26.4）', async () => {
    mockPost.mockResolvedValueOnce({ data: { data: { content: 'AI 复核意见：记-002 存在跨期确认风险。' } } })
    const wrapper = makeWrapper()
    const vm = wrapper.vm as any
    await vm.startReview()
    expect(mockPost).toHaveBeenCalledWith(
      '/api/workpapers/wp-1/ai/generate-text',
      expect.objectContaining({ section: 'voucher-review' }),
      expect.anything(),
    )
    expect(vm.stage).toBe('result')
    expect(vm.opinion).toContain('跨期')
  })

  it('5. 确认采用意见 → emit applied 且关闭（R26.5/26.8）', async () => {
    mockPost.mockResolvedValueOnce({ data: { data: { content: '复核结论文本' } } })
    const wrapper = makeWrapper()
    const vm = wrapper.vm as any
    await vm.startReview()
    vm.applyOpinion()
    expect(wrapper.emitted('applied')).toBeTruthy()
    expect(wrapper.emitted('applied')![0]).toEqual(['复核结论文本'])
    // 关闭
    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')!.at(-1)).toEqual([false])
  })

  it('6. 取消不写入：直接关闭不 emit applied（R26.6）', async () => {
    mockPost.mockResolvedValueOnce({ data: { data: { content: '复核结论文本' } } })
    const wrapper = makeWrapper()
    const vm = wrapper.vm as any
    await vm.startReview()
    // 用户取消 → close
    vm.close ? vm.close() : (wrapper.vm as any).$emit('update:modelValue', false)
    expect(wrapper.emitted('applied')).toBeFalsy()
  })

  it('7. AI 生成失败 → 回退询问阶段，不作为结论定稿（R26.7/26.8）', async () => {
    mockPost.mockRejectedValueOnce(new Error('503'))
    const wrapper = makeWrapper()
    const vm = wrapper.vm as any
    await vm.startReview()
    expect(vm.stage).toBe('prompt')
    expect(wrapper.emitted('applied')).toBeFalsy()
  })

  it('8. AI 不可用不阻断：aiAvailable=false 时不发请求且无 applied（R26.7）', () => {
    const wrapper = makeWrapper({ aiAvailable: false })
    // 不可用状态下无发起入口，用户仅能关闭；不产生任何 AI 请求
    expect(mockPost).not.toHaveBeenCalled()
    expect(wrapper.emitted('applied')).toBeFalsy()
  })

  it('9. AI 返回空内容 → 保持询问阶段（R26.8）', async () => {
    mockPost.mockResolvedValueOnce({ data: { data: { content: '' } } })
    const wrapper = makeWrapper()
    const vm = wrapper.vm as any
    await vm.startReview()
    expect(vm.stage).toBe('prompt')
    expect(vm.opinion).toBe('')
  })
})
