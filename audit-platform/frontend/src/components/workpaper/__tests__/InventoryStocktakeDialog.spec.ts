/**
 * InventoryStocktakeDialog.spec.ts — Sprint 2 Task 2.10 (F-F5)
 *
 * 烟测目标:
 * 1. visible=true 时组件可挂载
 * 2. 表单字段全部渲染（地点 / 日期 / 方式 / 双签 / 附件 / 差异表 / 结论）
 * 3. 双签字校验：盘点人 + 复核人 都必须签字才能保存
 * 4. LLM 差异分析按钮调用 stocktake-summary API
 *
 * 不挂载真实 element-plus 内部组件树（依赖太重），
 * 而是抽象核心逻辑做单元测试，与 FormulaManagerDialog.spec.ts 模式一致。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref, nextTick } from 'vue'

// Mock api 必须在 import dialog 前完成（vi.mock 顶提升）
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

// Mock confirmLeave 直接 resolve（避免触发 ElMessageBox）
vi.mock('@/utils/confirm', () => ({
  confirmLeave: vi.fn().mockResolvedValue(undefined),
}))

import InventoryStocktakeDialog from '../InventoryStocktakeDialog.vue'

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockPatch.mockReset()
  // jsdom 自带 localStorage，但要确保每个测试隔离
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
  return mount(InventoryStocktakeDialog, {
    props: {
      visible: props.visible ?? true,
      projectId: props.projectId ?? 'proj-1',
      wpId: props.wpId ?? 'wp-1',
      wpCode: props.wpCode ?? 'F2-21A',
      stocktakeId: props.stocktakeId ?? '',
    },
    global: {
      stubs: {
        // 浅 stub 重型 element-plus 组件，关注业务逻辑而非渲染细节
        'el-dialog': { template: '<div class="el-dialog-stub"><slot /><slot name="footer" /></div>' },
        'el-form': { template: '<form class="el-form-stub"><slot /></form>', methods: { validate: () => Promise.resolve(true) } },
        'el-form-item': { template: '<div class="el-form-item-stub"><slot /></div>' },
        'el-input': true,
        'el-input-number': true,
        'el-date-picker': true,
        'el-select': true,
        'el-option': true,
        'el-upload': true,
        'el-button': { template: '<button class="el-button-stub" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>', props: ['disabled', 'loading', 'type', 'plain', 'size'], emits: ['click'] },
        'el-table': { template: '<table class="el-table-stub"><slot /></table>' },
        'el-table-column': true,
        'el-tag': true,
        AuditContextHeader: true,
      },
    },
  })
}

describe('InventoryStocktakeDialog — 烟测', () => {
  it('visible=true 时组件可挂载', () => {
    const wrapper = makeWrapper({ visible: true })
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.find('.el-dialog-stub').exists()).toBe(true)
  })

  it('表单字段全部渲染：地点/日期/方式/双签/附件/差异表/结论', () => {
    const wrapper = makeWrapper({ visible: true })
    // 至少 7 个 form-item（地点/日期/方式/盘点人/复核人/照片/录像/差异表/结论 = 9）
    const items = wrapper.findAll('.el-form-item-stub')
    expect(items.length).toBeGreaterThanOrEqual(7)
  })

  it('双签字校验：缺签字时保存按钮 disabled', async () => {
    const wrapper = makeWrapper({ visible: true })
    await nextTick()
    // 默认 form 未填，counter / reviewer 都为空 → 保存按钮应该 disabled
    const buttons = wrapper.findAll('button.el-button-stub')
    // 找到"保存"按钮（最后一个）
    const saveBtn = buttons.find((b) => b.text().includes('保存'))
    expect(saveBtn).toBeTruthy()
    expect(saveBtn!.attributes('disabled')).toBeDefined()
  })

  it('双签字齐全后保存按钮 enabled', async () => {
    const wrapper = makeWrapper({ visible: true })
    await nextTick()
    // 直接修改组件内 form 状态
    const vm: any = wrapper.vm
    vm.form.location = '上海仓库'
    vm.form.date = '2026-01-15'
    vm.form.method = 'full'
    vm.form.counter = '张三'
    vm.form.reviewer = '李四'
    vm.form.conclusion = '盘点正常，无重大差异'
    await nextTick()

    const buttons = wrapper.findAll('button.el-button-stub')
    const saveBtn = buttons.find((b) => b.text().includes('保存'))
    expect(saveBtn).toBeTruthy()
    expect(saveBtn!.attributes('disabled')).toBeUndefined()
  })

  it('LLM 差异分析按钮调用 stocktake-summary API', async () => {
    mockPost.mockResolvedValueOnce({
      summary: '本次盘点差异共 1 项，金额合计 -5 件，已落实于发料单。',
      risk_alerts: ['仓储管理流程偶发遗漏'],
    })

    const wrapper = makeWrapper({ visible: true })
    await nextTick()
    const vm: any = wrapper.vm
    // 模拟用户填写差异行
    vm.form.differences = [
      { itemName: '原材料A', bookQty: 100, actualQty: 95, reason: '车间领用未入账' },
    ]
    vm.form.conclusion = '差异原因待确认'
    await nextTick()

    // 直接调用业务函数（避免模拟点击 stub 按钮的复杂性）
    await vm.onLlmSummary()

    expect(mockPost).toHaveBeenCalledTimes(1)
    const [url, body] = mockPost.mock.calls[0]
    expect(url).toBe('/api/projects/proj-1/workpapers/wp-1/ai/stocktake-summary')
    expect(body).toEqual({
      differences: vm.form.differences,
      conclusion: '差异原因待确认',
    })
    // LLM 摘要应回填到 conclusion
    expect(vm.form.conclusion).toContain('盘点差异')
  })

  it('保存成功调用 PATCH parsed-data 端点 + 写入 stocktake key', async () => {
    mockPatch.mockResolvedValueOnce({ ok: true })

    const wrapper = makeWrapper({ visible: true, wpCode: 'F2-21A', stocktakeId: '' })
    await nextTick()
    const vm: any = wrapper.vm
    vm.form.location = '上海仓库'
    vm.form.date = '2026-01-15'
    vm.form.method = 'full'
    vm.form.counter = '张三'
    vm.form.reviewer = '李四'
    vm.form.conclusion = '盘点完成'
    await nextTick()

    await vm.onSave()

    expect(mockPatch).toHaveBeenCalledTimes(1)
    const [url, body] = mockPatch.mock.calls[0]
    expect(url).toBe('/api/projects/proj-1/working-papers/wp-1/parsed-data')
    expect(body.sheet_key).toBe('stocktake_F2-21A')
    expect(body.data.counter).toBe('张三')
    expect(body.data.reviewer).toBe('李四')
    expect(body.data.counter_signed_at).toBeTruthy()
    expect(body.data.reviewer_signed_at).toBeTruthy()
  })

  it('未双签时调用 onSave 直接报错不调 PATCH', async () => {
    const wrapper = makeWrapper({ visible: true })
    await nextTick()
    const vm: any = wrapper.vm
    vm.form.location = '上海仓库'
    vm.form.date = '2026-01-15'
    vm.form.method = 'full'
    vm.form.counter = '张三' // 只有盘点人
    vm.form.reviewer = '' // 复核人为空
    vm.form.conclusion = '盘点完成'
    await nextTick()

    await vm.onSave()

    // 不应触发 patch
    expect(mockPatch).not.toHaveBeenCalled()
  })
})
