import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const api = vi.hoisted(() => ({
  history: vi.fn(),
  mark: vi.fn(),
  withdraw: vi.fn(),
}))
vi.mock('@/services/auditPlatformApi', () => ({
  getAdjustmentTreatmentHistory: api.history,
  markAdjustmentUnadjusted: api.mark,
  withdrawAdjustmentTreatment: api.withdraw,
}))

import AdjustmentTreatmentDialog from '../AdjustmentTreatmentDialog.vue'

let wrapper: VueWrapper | null = null
const row = {
  entry_group_id: 'g1', adjustment_no: 'AJE-001', adjustment_type: 'aje',
  review_status: 'approved', origin: 'manual',
  treatment: { status: 'include_in_working_tb', effective: true },
}

beforeEach(() => {
  vi.clearAllMocks()
  api.history.mockResolvedValue([])
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  document.body.innerHTML = ''
})

function mountDialog() {
  wrapper = mount(AdjustmentTreatmentDialog, {
    props: { projectId: 'p1', year: 2025 },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  return wrapper
}

function button(text: string): HTMLButtonElement {
  return [...document.querySelectorAll<HTMLButtonElement>('button')]
    .find((item) => item.textContent?.trim() === text)!
}

function setTextarea(value: string): void {
  const textarea = document.querySelector<HTMLTextAreaElement>('textarea')!
  textarea.value = value
  textarea.dispatchEvent(new Event('input'))
}

describe('AdjustmentTreatmentDialog', () => {
  it('纳入工作试算表时要求管理层原因并写正式错报处理', async () => {
    api.mark.mockResolvedValue({})
    const dialog = mountDialog()
    await (dialog.vm as any).open(row)
    await flushPromises()
    expect(document.body.textContent).toContain('当前已纳入工作试算表')
    setTextarea('管理层认为金额不重大')
    await flushPromises()
    button('不予更正并转错报').click()
    await flushPromises()
    expect(api.mark).toHaveBeenCalledTimes(1)
    expect(api.mark.mock.calls[0][0]).toBe('p1')
    expect(api.mark.mock.calls[0][1]).toBe('g1')
    expect(api.mark.mock.calls[0][2]).toMatchObject({
      year: 2025, management_reason: '管理层认为金额不重大',
    })
    expect(dialog.emitted('updated')).toBeTruthy()
  })

  it('不予更正处理只能填写原因后撤销并保留历史', async () => {
    api.history.mockResolvedValue([{ id: 't1', action: 'unadjusted_misstatement', reason: '金额不重大', created_at: '2025-12-31T00:00:00Z' }])
    api.withdraw.mockResolvedValue({})
    const dialog = mountDialog()
    await (dialog.vm as any).open({ ...row, treatment: { status: 'unadjusted_misstatement', effective: true } })
    await flushPromises()
    expect(document.body.textContent).toContain('不予更正并转错报')
    button('撤销当前处理').click()
    await flushPromises()
    expect(api.withdraw).not.toHaveBeenCalled()
    setTextarea('管理层同意调账')
    await flushPromises()
    button('撤销当前处理').click()
    await flushPromises()
    expect(api.withdraw).toHaveBeenCalledWith('p1', 'g1', { year: 2025, reason: '管理层同意调账' })
  })
})
