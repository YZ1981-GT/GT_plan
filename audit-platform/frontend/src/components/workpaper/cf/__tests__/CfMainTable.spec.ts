import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  getAccountDropdown: vi.fn(),
}))

vi.mock('@/utils/apiProxy', () => ({
  apiProxy: { get: api.get, post: api.post },
}))
vi.mock('@/services/auditPlatformApi', () => ({
  getAccountDropdown: api.getAccountDropdown,
}))

import CfMainTable from '../CfMainTable.vue'

const openCreate = vi.fn()
const AdjustmentEntryDialogStub = defineComponent({
  name: 'AdjustmentEntryDialog',
  props: {
    projectId: { type: String, required: true },
    year: { type: Number, required: true },
    accountOptions: { type: Array, required: true },
    accountsReady: { type: Boolean, required: true },
  },
  setup(_props, { expose }) {
    expose({ openCreate })
    return () => h('div', { class: 'adjustment-entry-dialog-stub' })
  },
})

const ACCOUNTS = [
  { code: '1001', name: '库存现金', level: 1 },
  { code: '6603', name: '财务费用', level: 1 },
]
const ITEMS = [
  {
    section: 'operating', item: '销售商品、提供劳务收到的现金', row_code: 'CFS-001',
    reported: 120, calculated: 100, difference: 20, pass: false, has_vat_tolerance: true,
  },
  {
    section: 'investing', item: '购建长期资产支付的现金', row_code: 'CFS-040',
    reported: 80, calculated: 100, difference: -20, pass: false, has_vat_tolerance: false,
  },
]

const mounted: VueWrapper[] = []

async function mountTable() {
  const wrapper = mount(CfMainTable, {
    props: { projectId: 'project-1', year: 2025 },
    global: {
      plugins: [ElementPlus],
      stubs: { AdjustmentEntryDialog: AdjustmentEntryDialogStub },
    },
    attachTo: document.body,
  })
  mounted.push(wrapper)
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.clearAllMocks()
  api.get.mockResolvedValue(ITEMS.map((item) => ({ ...item })))
  api.getAccountDropdown.mockResolvedValue(ACCOUNTS)
})

afterEach(() => {
  while (mounted.length) mounted.pop()!.unmount()
  document.body.innerHTML = ''
})

describe('CfMainTable 创建调整', () => {
  it('加载当前项目年度科目并传给标准调整分录弹窗', async () => {
    const wrapper = await mountTable()

    expect(api.getAccountDropdown).toHaveBeenCalledWith('project-1', undefined, 2025)
    const dialog = wrapper.findComponent(AdjustmentEntryDialogStub)
    expect(dialog.props()).toMatchObject({
      projectId: 'project-1',
      year: 2025,
      accountOptions: ACCOUNTS,
      accountsReady: true,
    })
  })

  it('正负差异都只预填摘要和提示，不调用旧端点或猜借贷方向', async () => {
    const wrapper = await mountTable()
    const buttons = wrapper.findAll('button').filter((button) => button.text().trim() === '创建调整')
    expect(buttons).toHaveLength(2)

    for (const button of buttons) await button.trigger('click')

    expect(openCreate).toHaveBeenCalledTimes(2)
    const prefills = openCreate.mock.calls.map(([prefill]) => prefill as Record<string, unknown>)
    expect(prefills[0].description).toContain('CFS-001')
    expect(prefills[1].description).toContain('CFS-040')
    expect(prefills[0].problems).toEqual([
      expect.stringContaining('差异金额 20 仅供核查'),
    ])
    expect(prefills[1].problems).toEqual([
      expect.stringContaining('差异金额 -20 仅供核查'),
    ])
    for (const prefill of prefills) {
      expect(prefill).not.toHaveProperty('lines')
      expect(JSON.stringify(prefill)).not.toContain('debit_amount')
      expect(JSON.stringify(prefill)).not.toContain('credit_amount')
      expect(JSON.stringify(prefill)).not.toContain('side')
    }
    expect(api.post).not.toHaveBeenCalled()
  })
})
