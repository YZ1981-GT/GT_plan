/**
 * FixedAssetStocktakeDialog.spec.ts — Sprint 2 Task 2.9 (H-F5)
 *
 * ≥ 8 项测试:
 * 1. visible=true 时组件可挂载
 * 2. 表单字段全部渲染（location/date/counter/reviewer/asset_list/status/attachments/conclusion）
 * 3. 双签字校验：盘点人 + 复核人 都必须签字才能保存
 * 4. 双签字齐全后保存按钮 enabled
 * 5. 盘亏状态强制填写原因 + 责任认定
 * 6. LLM 差异分析按钮调用 stocktake-summary API（wp_code='H1'）
 * 7. 保存调用 PATCH parsed-data
 * 8. 未双签时 onSave 不调 PATCH
 *
 * Spec: workpaper-h-fixed-assets-cycle / Sprint 2 / Task 2.9
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

// Mock api
const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPatch = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
    patch: (...args: any[]) => mockPatch(...args),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

// Mock confirmLeave
vi.mock('@/utils/confirm', () => ({
  confirmLeave: vi.fn().mockResolvedValue(undefined),
}))

import FixedAssetStocktakeDialog from '../FixedAssetStocktakeDialog.vue'

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockPatch.mockReset()
  try {
    localStorage.clear()
  } catch {
    /* ignore */
  }
})

function makeWrapper(props: Partial<{
  visible: boolean
  projectId: string
  wpId: string
  wpCode: string
  stocktakeId: string
}> = {}) {
  mockGet.mockResolvedValue({ parsed_data: {} })
  return mount(FixedAssetStocktakeDialog, {
    props: {
      visible: props.visible ?? true,
      projectId: props.projectId ?? 'proj-1',
      wpId: props.wpId ?? 'wp-1',
      wpCode: props.wpCode ?? 'H1',
      stocktakeId: props.stocktakeId ?? '',
    },
    global: {
      stubs: {
        'el-dialog': { template: '<div class="el-dialog-stub"><slot /><slot name="footer" /></div>' },
        'el-form': { template: '<form class="el-form-stub"><slot /></form>', methods: { validate: () => Promise.resolve(true) } },
        'el-form-item': { template: '<div class="el-form-item-stub"><slot /></div>' },
        'el-input': true,
        'el-date-picker': true,
        'el-select': true,
        'el-option': true,
        'el-upload': true,
        'el-button': { template: '<button class="el-button-stub" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>', props: ['disabled', 'loading', 'type', 'plain', 'size'], emits: ['click'] },
        AuditContextHeader: true,
      },
    },
  })
}

describe('FixedAssetStocktakeDialog — H-F5 烟测', () => {
  it('1. visible=true 时组件可挂载', () => {
    const wrapper = makeWrapper({ visible: true })
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.find('.el-dialog-stub').exists()).toBe(true)
  })

  it('2. 表单字段全部渲染: location/date/counter/reviewer/asset_list/status/attachments/conclusion', () => {
    const wrapper = makeWrapper({ visible: true })
    // 基础字段: 盘点地点/日期/盘点人/复核人/资产编号清单/盘点状态/照片视频附件/结论 = 8
    const items = wrapper.findAll('.el-form-item-stub')
    expect(items.length).toBeGreaterThanOrEqual(8)
  })

  it('3. 双签字校验：缺签字时保存按钮 disabled', async () => {
    const wrapper = makeWrapper({ visible: true })
    await nextTick()
    const buttons = wrapper.findAll('button.el-button-stub')
    const saveBtn = buttons.find((b) => b.text().includes('保存'))
    expect(saveBtn).toBeTruthy()
    expect(saveBtn!.attributes('disabled')).toBeDefined()
  })

  it('4. 双签字齐全后保存按钮 enabled', async () => {
    const wrapper = makeWrapper({ visible: true })
    await nextTick()
    const vm: any = wrapper.vm
    vm.form.counter = '张三'
    vm.form.reviewer = '李四'
    await nextTick()

    const buttons = wrapper.findAll('button.el-button-stub')
    const saveBtn = buttons.find((b) => b.text().includes('保存'))
    expect(saveBtn).toBeTruthy()
    expect(saveBtn!.attributes('disabled')).toBeUndefined()
  })

  it('5. 盘亏状态强制填写原因+责任认定字段出现', async () => {
    const wrapper = makeWrapper({ visible: true })
    await nextTick()
    const vm: any = wrapper.vm

    // 非盘亏状态时不显示原因/责任字段
    vm.form.status = 'in_use'
    await nextTick()
    let items = wrapper.findAll('.el-form-item-stub')
    // 基础 8 个字段（不含盘亏原因/责任认定）
    expect(items.length).toBe(8)

    // 切换到盘亏状态
    vm.form.status = 'shortage'
    await nextTick()
    items = wrapper.findAll('.el-form-item-stub')
    // 应多出 2 个字段（盘亏原因 + 责任认定）
    expect(items.length).toBe(10)
  })

  it('6. LLM 差异分析按钮调用 API（wp_code=H1）', async () => {
    mockPost.mockResolvedValueOnce({
      summary: '本次固定资产盘点共涉及 3 项资产，盘亏 1 项。',
      risk_alerts: ['资产台账管理需加强'],
    })

    const wrapper = makeWrapper({ visible: true, wpCode: 'H1' })
    await nextTick()
    const vm: any = wrapper.vm
    vm.form.asset_list = 'FA-001\nFA-002\nFA-003'
    vm.form.status = 'shortage'
    vm.form.shortage_reason = '已报废未销账'
    vm.form.conclusion = ''
    await nextTick()

    await vm.onLlmSummary()

    expect(mockPost).toHaveBeenCalledTimes(1)
    const [url, body] = mockPost.mock.calls[0]
    expect(url).toBe('/api/projects/proj-1/workpapers/wp-1/ai/stocktake-summary')
    expect(body.wp_code).toBe('H1')
    expect(body.differences.length).toBe(3)
    // LLM 摘要应回填到 conclusion
    expect(vm.form.conclusion).toContain('固定资产盘点')
  })

  it('7. 保存调用 PATCH parsed-data + 写入 h_stocktake key', async () => {
    mockPatch.mockResolvedValueOnce({ ok: true })

    const wrapper = makeWrapper({ visible: true, wpCode: 'H1', stocktakeId: '' })
    await nextTick()
    const vm: any = wrapper.vm
    vm.form.location = '厂房A区 (GPS: 31.230416, 121.473701)'
    vm.form.date = '2026-01-15'
    vm.form.counter = '张三'
    vm.form.reviewer = '李四'
    vm.form.asset_list = 'FA-001'
    vm.form.status = 'in_use'
    vm.form.conclusion = '资产状态良好'
    await nextTick()

    await vm.onSave()

    expect(mockPatch).toHaveBeenCalledTimes(1)
    const [url, body] = mockPatch.mock.calls[0]
    expect(url).toBe('/api/projects/proj-1/working-papers/wp-1/parsed-data')
    expect(body.sheet_key).toBe('h_stocktake_H1')
    expect(body.data.counter).toBe('张三')
    expect(body.data.reviewer).toBe('李四')
    expect(body.data.asset_list).toBe('FA-001')
    expect(body.data.status).toBe('in_use')
    expect(body.data.counter_signed_at).toBeTruthy()
    expect(body.data.reviewer_signed_at).toBeTruthy()
  })

  it('8. 未双签时 onSave 不调 PATCH', async () => {
    const wrapper = makeWrapper({ visible: true })
    await nextTick()
    const vm: any = wrapper.vm
    vm.form.location = '厂房A区'
    vm.form.date = '2026-01-15'
    vm.form.counter = '张三'
    vm.form.reviewer = '' // 复核人为空
    vm.form.asset_list = 'FA-001'
    vm.form.status = 'in_use'
    vm.form.conclusion = '资产状态良好'
    await nextTick()

    await vm.onSave()

    expect(mockPatch).not.toHaveBeenCalled()
  })
})
