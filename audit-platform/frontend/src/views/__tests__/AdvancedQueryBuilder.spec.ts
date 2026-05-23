/**
 * AdvancedQueryBuilder.spec.ts — proposal-remaining-18 task 5.1
 *
 * 验证 AdvancedQueryBuilder.vue 视图：
 * - 挂载时调用 /api/query/schema 加载白名单
 * - 添加/删除过滤行
 * - buildPayload 正确序列化 in / between / 数字字段
 * - SQL 预览调用 /api/query/preview
 * - 执行查询调用 /api/query/execute 并渲染结果表
 *
 * Validates: requirements §三 · S-3 高级查询构建器
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mockGet = vi.fn()
const mockPost = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  default: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
  },
  api: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
  },
}))

const mockHttpPost = vi.fn()
vi.mock('@/utils/http', () => ({
  default: {
    post: (...args: any[]) => mockHttpPost(...args),
  },
}))

vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return {
    ...actual,
    ElMessage: {
      success: vi.fn(),
      warning: vi.fn(),
      error: vi.fn(),
    },
  }
})

import AdvancedQueryBuilder from '@/views/AdvancedQueryBuilder.vue'

const FIXTURE_SCHEMA = {
  tables: [
    {
      name: 'trial_balance',
      label: '试算表',
      fields: [
        'id', 'project_id', 'year', 'standard_account_code',
        'account_name', 'audited_amount', 'is_deleted',
      ],
    },
    {
      name: 'adjustments',
      label: '调整分录（AJE/RJE）',
      fields: ['id', 'project_id', 'adjustment_no', 'description'],
    },
  ],
  operators: [
    'eq', 'neq', 'gt', 'gte', 'lt', 'lte',
    'like', 'not_like', 'in', 'not_in',
    'is_null', 'is_not_null', 'between',
  ],
  aggregates: ['count', 'sum', 'avg', 'min', 'max'],
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockHttpPost.mockReset()
})


describe('AdvancedQueryBuilder — schema 加载', () => {
  it('mount 时调用 /api/query/schema 并渲染表选项', async () => {
    mockGet.mockResolvedValue(FIXTURE_SCHEMA)
    const wrapper = mount(AdvancedQueryBuilder, {
      global: {
        stubs: {
          'el-select': true,
          'el-option': true,
          'el-form': { template: '<form><slot /></form>' },
          'el-form-item': { template: '<div><slot /></div>' },
          'el-checkbox-group': true,
          'el-checkbox': true,
          'el-radio-group': true,
          'el-radio-button': true,
          'el-button': { template: '<button><slot /></button>' },
          'el-input': true,
          'el-input-number': true,
          'el-table': true,
          'el-table-column': true,
        },
      },
    })
    await flushPromises()
    expect(mockGet).toHaveBeenCalledWith('/api/query/schema')
    expect(wrapper.text()).toContain('高级查询构建器')
    expect(wrapper.text()).toContain('admin / manager')
  })
})


describe('AdvancedQueryBuilder — buildPayload 序列化', () => {
  /**
   * 直接测试 vm 内部的 buildPayload 逻辑：
   * - in 操作符：逗号字符串拆数组
   * - between 操作符：[lo, hi]
   * - 纯数字字段：转为 number
   * - is_null 操作符：value=null
   */
  it('正确序列化 in / between / 数字字段 / is_null', async () => {
    mockGet.mockResolvedValue(FIXTURE_SCHEMA)
    mockPost.mockResolvedValue({ sql: 'SELECT 1', columns: [] })

    const wrapper = mount(AdvancedQueryBuilder, {
      global: {
        stubs: {
          'el-select': true,
          'el-option': true,
          'el-form': { template: '<form><slot /></form>' },
          'el-form-item': { template: '<div><slot /></div>' },
          'el-checkbox-group': true,
          'el-checkbox': true,
          'el-radio-group': true,
          'el-radio-button': true,
          'el-button': { template: '<button><slot /></button>' },
          'el-input': true,
          'el-input-number': true,
          'el-table': true,
          'el-table-column': true,
        },
      },
    })
    await flushPromises()

    // 设置查询 DSL
    const vm: any = wrapper.vm
    vm.dsl.table = 'trial_balance'
    vm.dsl.fields = ['standard_account_code', 'audited_amount']
    vm.dsl.filters = [
      { field: 'standard_account_code', op: 'in', value: '1001,1002,2001' },
      { field: 'audited_amount', op: 'between', value: '100,5000.50' },
      { field: 'year', op: 'eq', value: '2025' },
      { field: 'description', op: 'is_null', value: '' },
      { field: 'account_name', op: 'like', value: '存款' },
    ]
    vm.dsl.filter_logic = 'and'
    vm.dsl.order_by = [{ field: 'audited_amount', direction: 'desc' }]
    vm.dsl.limit = 50

    // 调用 doPreview 触发 buildPayload + post
    await vm.doPreview()
    await flushPromises()

    expect(mockPost).toHaveBeenCalledWith('/api/query/preview', expect.any(Object))
    const sentPayload = mockPost.mock.calls[0][1]

    expect(sentPayload.table).toBe('trial_balance')
    expect(sentPayload.fields).toEqual(['standard_account_code', 'audited_amount'])
    expect(sentPayload.filter_logic).toBe('and')
    expect(sentPayload.limit).toBe(50)

    // in: 字符串拆为数组
    const inFilter = sentPayload.filters.find((f: any) => f.op === 'in')
    expect(inFilter.value).toEqual(['1001', '1002', '2001'])

    // between: [lo, hi] 数字
    const betweenFilter = sentPayload.filters.find((f: any) => f.op === 'between')
    expect(betweenFilter.value).toEqual([100, 5000.5])

    // eq + 数字字符串：转为 number
    const eqFilter = sentPayload.filters.find((f: any) => f.op === 'eq')
    expect(eqFilter.value).toBe(2025)

    // is_null: value=null
    const isNullFilter = sentPayload.filters.find((f: any) => f.op === 'is_null')
    expect(isNullFilter.value).toBeNull()

    // like: 保留字符串
    const likeFilter = sentPayload.filters.find((f: any) => f.op === 'like')
    expect(likeFilter.value).toBe('存款')
  })
})


describe('AdvancedQueryBuilder — execute & emit', () => {
  it('执行查询后渲染结果计数', async () => {
    mockGet.mockResolvedValue(FIXTURE_SCHEMA)
    mockPost.mockResolvedValue({
      rows: [
        { standard_account_code: '1001', audited_amount: 100000 },
        { standard_account_code: '1002', audited_amount: 500000 },
      ],
      columns: ['standard_account_code', 'audited_amount'],
      total: 2,
      table: 'trial_balance',
      sql: 'SELECT ... FROM trial_balance LIMIT :param_1',
    })

    const wrapper = mount(AdvancedQueryBuilder, {
      global: {
        stubs: {
          'el-select': true,
          'el-option': true,
          'el-form': { template: '<form><slot /></form>' },
          'el-form-item': { template: '<div><slot /></div>' },
          'el-checkbox-group': true,
          'el-checkbox': true,
          'el-radio-group': true,
          'el-radio-button': true,
          'el-button': { template: '<button><slot /></button>' },
          'el-input': true,
          'el-input-number': true,
          'el-table': { template: '<div class="mock-table"><slot /></div>' },
          'el-table-column': true,
        },
      },
    })
    await flushPromises()

    const vm: any = wrapper.vm
    vm.dsl.table = 'trial_balance'
    vm.dsl.fields = ['standard_account_code', 'audited_amount']
    await vm.doExecute()
    await flushPromises()

    expect(mockPost).toHaveBeenCalledWith('/api/query/execute', expect.any(Object))
    expect(vm.result.total).toBe(2)
    expect(vm.result.columns).toEqual(['standard_account_code', 'audited_amount'])
    // SQL 预览同步更新
    expect(vm.sqlPreview).toContain('FROM trial_balance')
    // 文本中显示行数
    expect(wrapper.text()).toContain('共 2 行')
  })
})


describe('AdvancedQueryBuilder — 切表重置', () => {
  it('调用 onTableChange 后清空 fields/filters/order_by/result', async () => {
    mockGet.mockResolvedValue(FIXTURE_SCHEMA)
    const wrapper = mount(AdvancedQueryBuilder, {
      global: {
        stubs: {
          'el-select': true,
          'el-option': true,
          'el-form': { template: '<form><slot /></form>' },
          'el-form-item': { template: '<div><slot /></div>' },
          'el-checkbox-group': true,
          'el-checkbox': true,
          'el-radio-group': true,
          'el-radio-button': true,
          'el-button': { template: '<button><slot /></button>' },
          'el-input': true,
          'el-input-number': true,
          'el-table': true,
          'el-table-column': true,
        },
      },
    })
    await flushPromises()

    const vm: any = wrapper.vm
    vm.dsl.table = 'trial_balance'
    vm.dsl.fields = ['id', 'year']
    vm.dsl.filters = [{ field: 'year', op: 'eq', value: '2025' }]
    vm.dsl.order_by = [{ field: 'year', direction: 'asc' }]
    vm.sqlPreview = 'SELECT 1'

    vm.onTableChange()

    expect(vm.dsl.fields).toEqual([])
    expect(vm.dsl.filters).toEqual([])
    expect(vm.dsl.order_by).toEqual([])
    expect(vm.sqlPreview).toBe('')
  })

  it('addFilter / removeFilter 正常工作', async () => {
    mockGet.mockResolvedValue(FIXTURE_SCHEMA)
    const wrapper = mount(AdvancedQueryBuilder, {
      global: {
        stubs: {
          'el-select': true,
          'el-option': true,
          'el-form': { template: '<form><slot /></form>' },
          'el-form-item': { template: '<div><slot /></div>' },
          'el-checkbox-group': true,
          'el-checkbox': true,
          'el-radio-group': true,
          'el-radio-button': true,
          'el-button': { template: '<button><slot /></button>' },
          'el-input': true,
          'el-input-number': true,
          'el-table': true,
          'el-table-column': true,
        },
      },
    })
    await flushPromises()

    const vm: any = wrapper.vm
    vm.dsl.table = 'trial_balance'
    expect(vm.dsl.filters.length).toBe(0)

    vm.addFilter()
    vm.addFilter()
    expect(vm.dsl.filters.length).toBe(2)
    // 默认 op = eq
    expect(vm.dsl.filters[0].op).toBe('eq')
    // 第一个字段为 currentTable.fields[0]
    expect(vm.dsl.filters[0].field).toBe('id')

    vm.removeFilter(0)
    expect(vm.dsl.filters.length).toBe(1)
  })
})


describe('AdvancedQueryBuilder — 导出 Excel', () => {
  it('调用 http.post 携带 responseType blob', async () => {
    mockGet.mockResolvedValue(FIXTURE_SCHEMA)
    // 模拟 blob 响应
    mockHttpPost.mockResolvedValue({ data: new Blob(['xlsx-binary-content']) })

    const wrapper = mount(AdvancedQueryBuilder, {
      global: {
        stubs: {
          'el-select': true,
          'el-option': true,
          'el-form': { template: '<form><slot /></form>' },
          'el-form-item': { template: '<div><slot /></div>' },
          'el-checkbox-group': true,
          'el-checkbox': true,
          'el-radio-group': true,
          'el-radio-button': true,
          'el-button': { template: '<button><slot /></button>' },
          'el-input': true,
          'el-input-number': true,
          'el-table': true,
          'el-table-column': true,
        },
      },
    })
    await flushPromises()

    // 模拟 URL.createObjectURL（jsdom 没实现）
    const mockCreateUrl = vi.fn(() => 'blob:fake-url')
    const mockRevokeUrl = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { value: mockCreateUrl, configurable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: mockRevokeUrl, configurable: true })

    // 模拟 anchor click
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    const vm: any = wrapper.vm
    vm.dsl.table = 'trial_balance'
    vm.dsl.fields = ['id']
    await vm.doExport()
    await flushPromises()

    expect(mockHttpPost).toHaveBeenCalledWith(
      '/api/query/export-excel',
      expect.any(Object),
      expect.objectContaining({ responseType: 'blob' }),
    )
    expect(clickSpy).toHaveBeenCalled()
    expect(mockCreateUrl).toHaveBeenCalled()
    expect(mockRevokeUrl).toHaveBeenCalled()

    clickSpy.mockRestore()
  })
})
