/**
 * 提交复核弹窗 + 驳回 / 撤回原因弹窗（spec adjustment-hall-entry-review-closure 需求 4.1 / 4.3）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const api = vi.hoisted(() => ({ listAdjustmentReviewers: vi.fn(), submitAdjustmentsForReview: vi.fn() }))
vi.mock('@/services/auditPlatformApi', () => api)

import AdjustmentSubmitReviewDialog from '../AdjustmentSubmitReviewDialog.vue'
import AdjustmentReasonDialog from '../AdjustmentReasonDialog.vue'

const mounted: VueWrapper[] = []
const mountIt = (comp: any, props: Record<string, unknown> = {}) => {
  const w = mount(comp, { props, global: { plugins: [ElementPlus] }, attachTo: document.body })
  mounted.push(w)
  return w
}
const button = (text: string) => [...document.querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent?.trim() === text)!
const ENTRIES = [
  { entry_group_id: 'g1', adjustment_no: 'AJE-001', description: '补提坏账' },
  { entry_group_id: 'g2', adjustment_no: 'AJE-002', description: '补提折旧' },
]

beforeEach(() => vi.clearAllMocks())
afterEach(() => {
  while (mounted.length) mounted.pop()!.unmount()
  document.body.innerHTML = ''
})

describe('提交复核弹窗', () => {
  it('默认通知全部复核人，提交逐笔结果并回传', async () => {
    api.listAdjustmentReviewers.mockResolvedValue([
      { user_id: 'u1', name: '王经理', project_role: 'manager', system_role: 'manager' },
      { user_id: 'u2', name: '赵合伙人', project_role: 'partner', system_role: 'partner' },
    ])
    const result = { succeeded: [{ entry_group_id: 'g1' }, { entry_group_id: 'g2' }], failed: [], notified: [{ user_id: 'u1', name: '王经理', kind: 'reviewer' }] }
    api.submitAdjustmentsForReview.mockResolvedValue(result)
    const w = mountIt(AdjustmentSubmitReviewDialog, { projectId: 'p1' })
    await (w.vm as any).open(ENTRIES)
    await flushPromises()
    expect(document.body.textContent).toContain('将以下 2 笔分录提交复核')
    expect(document.body.textContent).toContain('AJE-002')
    button('提交复核').click()
    await flushPromises()
    expect(api.submitAdjustmentsForReview).toHaveBeenCalledWith('p1', { entry_group_ids: ['g1', 'g2'], reviewer_ids: ['u1', 'u2'], note: undefined })
    expect(w.emitted('done')?.[0]).toEqual([result])
  })

  it('没有可选复核人：提示且不传 reviewer_ids（后端给出未通知的说明）', async () => {
    api.listAdjustmentReviewers.mockResolvedValue([])
    api.submitAdjustmentsForReview.mockResolvedValue({ succeeded: [{ entry_group_id: 'g1' }], failed: [], notified: [], warning: '本项目没有其他有复核权限的成员，未发送通知' })
    const w = mountIt(AdjustmentSubmitReviewDialog, { projectId: 'p1' })
    await (w.vm as any).open(ENTRIES.slice(0, 1))
    await flushPromises()
    expect(document.body.textContent).toContain('本项目没有其他可复核调整分录的成员')
    button('提交复核').click()
    await flushPromises()
    expect(api.submitAdjustmentsForReview.mock.calls[0][1].reviewer_ids).toBeUndefined()
  })
})

describe('驳回 / 撤回原因弹窗', () => {
  it('驳回：原因必填，handler 成功才关闭', async () => {
    const handler = vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true)
    const w = mountIt(AdjustmentReasonDialog)
    ;(w.vm as any).open('reject', ENTRIES, handler)
    await flushPromises()
    const confirm = button('驳回 2 笔')
    expect(confirm.disabled).toBe(true)
    const textarea = document.querySelector('textarea')!
    textarea.value = ' 比例不对 '
    textarea.dispatchEvent(new Event('input'))
    await flushPromises()
    expect(confirm.disabled).toBe(false)
    confirm.click()
    await flushPromises()
    expect(handler).toHaveBeenLastCalledWith({ reason: '比例不对', reasons: undefined })
    expect(document.body.textContent).toContain('驳回后分录退回编制人修改') // 失败（handler=false）不关
    button('驳回 2 笔').click()
    await flushPromises()
    expect(handler).toHaveBeenCalledTimes(2)
  })

  it('撤回复核：原因可选', async () => {
    const handler = vi.fn().mockResolvedValue(true)
    const w = mountIt(AdjustmentReasonDialog)
    ;(w.vm as any).open('revoke', ENTRIES.slice(0, 1), handler)
    await flushPromises()
    expect(document.body.textContent).toContain('试算表审定数、报表与附注随之回退')
    button('撤回 1 笔').click()
    await flushPromises()
    expect(handler).toHaveBeenCalledWith({ reason: '', reasons: undefined })
  })
})
