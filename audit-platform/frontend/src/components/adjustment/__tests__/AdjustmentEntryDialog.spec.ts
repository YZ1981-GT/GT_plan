/**
 * 调整分录录入弹窗（spec adjustment-hall-entry-review-closure 需求 1）：
 * 保存带编号 / 只提交非空行；不平衡不发请求并列出原因；编辑已驳回的分录提示原因并原样带回二级科目码；
 * 后端拒绝时原因留在弹窗；表格里粘贴 Excel 多行追加为明细。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const api = vi.hoisted(() => ({ createAdjustment: vi.fn(), updateAdjustment: vi.fn() }))
vi.mock('@/services/auditPlatformApi', () => api)

import AdjustmentEntryDialog from '../AdjustmentEntryDialog.vue'

const OPTIONS = [
  { code: '1122', name: '应收账款', level: 1, balance: '1000.00', report_line: '应收账款' },
  { code: '1231', name: '坏账准备', level: 1 },
  { code: '6702', name: '信用减值损失', level: 1 },
]
const mounted: VueWrapper[] = []

function mountDialog(props: Record<string, unknown> = {}) {
  const w = mount(AdjustmentEntryDialog, {
    props: { projectId: 'p1', year: 2025, accountOptions: OPTIONS, ...props },
    global: { plugins: [ElementPlus], stubs: { AdjustmentImpactPreview: true } },
    attachTo: document.body,
  })
  mounted.push(w)
  return w
}

const vm = (w: VueWrapper) => w.vm as unknown as {
  openCreate: (p?: unknown) => void
  openEdit: (row: unknown) => void
}
const button = (text: string) =>
  [...document.querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent?.trim() === text)!

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
})
afterEach(() => {
  while (mounted.length) mounted.pop()!.unmount()
  document.body.innerHTML = ''
})

describe('AdjustmentEntryDialog', () => {
  it('保存草稿：带自定义编号、丢空行、金额按分；回传 saved', async () => {
    api.createAdjustment.mockResolvedValue({ entry_group_id: 'g1', adjustment_no: 'Z-1' })
    const w = mountDialog()
    vm(w).openCreate({
      description: '补提坏账',
      lines: [
        { standard_account_code: '6702', account_name: '信用减值损失', debit_amount: 100.005 },
        { standard_account_code: '', account_name: '' },
        { standard_account_code: '1231', account_name: '坏账准备', credit_amount: 100.01 },
      ],
    })
    await flushPromises()
    const no = document.querySelector<HTMLInputElement>('input[placeholder="留空自动编号"]')!
    no.value = ' Z-1 '
    no.dispatchEvent(new Event('input'))
    await flushPromises()
    button('保存草稿').click()
    await flushPromises()
    expect(api.createAdjustment).toHaveBeenCalledWith('p1', {
      adjustment_type: 'aje', year: 2025, description: '补提坏账', adjustment_no: 'Z-1',
      line_items: [
        { standard_account_code: '6702', account_name: '信用减值损失', debit_amount: 100.01, credit_amount: 0 },
        { standard_account_code: '1231', account_name: '坏账准备', debit_amount: 0, credit_amount: 100.01 },
      ],
    })
    expect(w.emitted('saved')?.[0]).toEqual([{ entryGroupId: 'g1', adjustmentNo: 'Z-1', mode: 'create', submit: false }])
    expect(document.body.textContent).toContain('已保存为草稿 Z-1')
    expect(document.body.textContent).toContain('草稿不计入试算表，提交复核并批准后才计入审定数')
  })

  it('不平衡：不发请求，列出与后端同口径的原因', async () => {
    const w = mountDialog()
    vm(w).openCreate({ description: '试', lines: [{ standard_account_code: '6702', debit_amount: 100 }, { standard_account_code: '1231', credit_amount: 60 }] })
    await flushPromises()
    button('保存并提交复核').click()
    await flushPromises()
    expect(api.createAdjustment).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('借贷不平衡：借方合计 100.00，贷方合计 60.00，差额 40.00')
  })

  it('编辑已驳回：提示驳回原因与「保存后回到草稿」，原样带回二级科目码', async () => {
    api.updateAdjustment.mockResolvedValue({ entry_group_id: 'g9', adjustment_no: 'AJE-009' })
    const w = mountDialog()
    vm(w).openEdit({
      entry_group_id: 'g9', adjustment_no: 'AJE-009', adjustment_type: 'aje', description: '原摘要',
      review_status: 'rejected', rejection_reason: '比例不对',
      line_items: [
        { standard_account_code: '6702', account_name: '信用减值损失', debit_amount: '50.00', credit_amount: '0' },
        { standard_account_code: '1122', account_name: '应收账款', detail_account_code: '112201', debit_amount: '0', credit_amount: '50.00' },
      ],
    })
    await flushPromises()
    expect(document.body.textContent).toContain('复核人驳回：比例不对')
    expect(document.body.textContent).toContain('修改保存后分录回到草稿')
    button('保存').click()
    await flushPromises()
    expect(api.updateAdjustment).toHaveBeenCalledWith('p1', 'g9', {
      expected_revision: 1,
      description: '原摘要',
      audit_phase: 'final',
      line_items: [
        { standard_account_code: '6702', account_name: '信用减值损失', debit_amount: 50, credit_amount: 0 },
        { standard_account_code: '1122', account_name: '应收账款', debit_amount: 0, credit_amount: 50, detail_account_code: '112201' },
      ],
    })
    expect(w.emitted('saved')?.[0]?.[0]).toMatchObject({ entryGroupId: 'g9', mode: 'edit' })
  })

  it('后端拒绝：原因留在弹窗里，弹窗不关', async () => {
    api.createAdjustment.mockRejectedValue({ response: { status: 400, data: { detail: '编号「Z-1」已被本年度其他调整分录使用' } } })
    const w = mountDialog()
    vm(w).openCreate({ description: '试', lines: [{ standard_account_code: '6702', debit_amount: 1 }, { standard_account_code: '1231', credit_amount: 1 }] })
    await flushPromises()
    button('保存草稿').click()
    await flushPromises()
    expect(document.body.textContent).toContain('保存失败：编号「Z-1」已被本年度其他调整分录使用')
    expect(w.emitted('saved')).toBeUndefined()
  })

  it('明细表里粘贴 Excel 多行：追加为明细行并按编码 / 名称匹配科目', async () => {
    const w = mountDialog()
    vm(w).openCreate()
    await flushPromises()
    const zone = document.querySelector('.gt-adj-entry-lines')!
    const evt = new Event('paste', { bubbles: true, cancelable: true })
    Object.defineProperty(evt, 'clipboardData', { value: { getData: () => '6702\t\t80\t\t粘贴摘要\n\t坏账准备\t\t80' } })
    zone.dispatchEvent(evt)
    await flushPromises()
    expect(evt.defaultPrevented).toBe(true)
    button('保存草稿').click()
    await flushPromises()
    expect(api.createAdjustment.mock.calls[0][1]).toMatchObject({
      description: '粘贴摘要',
      line_items: [
        { standard_account_code: '6702', debit_amount: 80, credit_amount: 0 },
        { standard_account_code: '1231', debit_amount: 0, credit_amount: 80 },
      ],
    })
  })

  it('本项目没有标准科目：提示先做科目映射', async () => {
    const w = mountDialog({ accountOptions: [] })
    vm(w).openCreate()
    await flushPromises()
    expect(document.body.textContent).toContain('本项目还没有标准科目')
  })
})


describe('AdjustmentEntryDialog 草稿隔离与关闭决策', () => {
  it('本地草稿 key 包含项目、年度、模式和分录组，并可在同一上下文恢复', async () => {
    const w = mountDialog()
    vm(w).openCreate()
    await flushPromises()
    const description = document.querySelector<HTMLInputElement>('input[placeholder^="说明调整原因"]')!
    description.value = '未保存的现金流调整'
    description.dispatchEvent(new Event('input'))
    await flushPromises()

    button('取消').click()
    await flushPromises()
    button('保存草稿后关闭').click()
    await flushPromises()

    const key = 'autosave_adjustment_form_p1_2025_create_new'
    const raw = sessionStorage.getItem(key)
    expect(raw).toBeTruthy()
    expect(JSON.parse(raw!).context).toEqual({
      project_id: 'p1', year: 2025, section: 'adjustment:create:new',
    })

    vm(w).openCreate()
    await flushPromises()
    expect(document.body.textContent).toContain('检测到此新建分录的未保存草稿')
    button('恢复草稿').click()
    await flushPromises()
    expect(document.querySelector<HTMLInputElement>('input[placeholder^="说明调整原因"]')?.value)
      .toBe('未保存的现金流调整')
  })

  it('编辑草稿按分录组隔离，明确放弃后不留本地草稿', async () => {
    const w = mountDialog()
    vm(w).openEdit({
      entry_group_id: 'g-edit', adjustment_no: 'AJE-008', adjustment_type: 'aje',
      description: '原摘要', review_status: 'draft', line_items: [
        { standard_account_code: '6702', account_name: '信用减值损失', debit_amount: 1, credit_amount: 0 },
        { standard_account_code: '1122', account_name: '应收账款', debit_amount: 0, credit_amount: 1 },
      ],
    })
    await flushPromises()
    const description = document.querySelector<HTMLInputElement>('input[placeholder^="说明调整原因"]')!
    description.value = '修改后未保存'
    description.dispatchEvent(new Event('input'))
    await flushPromises()

    button('取消').click()
    await flushPromises()
    button('放弃并关闭').click()
    await flushPromises()

    expect(sessionStorage.getItem('autosave_adjustment_form_p1_2025_edit_g-edit')).toBeNull()
  })
})
