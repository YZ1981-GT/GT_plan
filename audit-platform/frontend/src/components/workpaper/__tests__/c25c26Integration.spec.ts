/**
 * C25/C26 集成测试：挂载组件 mock checklist-responses
 *
 * Spec: .kiro/specs/c25-c26-internal-audit-info-control/
 * Task: 6.1
 *
 * **Validates: Requirements 2.1, 3.3, 3.4**
 *
 * Tests:
 *  C25:
 *  1. 挂载组件 + mock GET 返回 C25 items → 10 步正确渲染
 *  2. 结论区渲染 loaded 值
 *  3. 适用性变更触发即时 PUT
 *  4. 执行说明变更触发 debounced PUT
 *  5. AI 按钮存在且可调用
 *  6. readonly 模式禁用所有输入
 *
 *  C26:
 *  7. 挂载组件 + mock GET 返回 C26 rows → 矩阵表渲染正确行数
 *  8. 四要素 checkbox 渲染 loaded 值
 *  9. 循环筛选显示/隐藏行
 *  10. addRow（ElMessageBox mock）新增行 + PUT
 *  11. removeRow 删除行 + PUT
 *  12. readonly 模式禁用所有控件
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// ─── Mock apiProxy ─────────────────────────────────────────────────────────
const mockGet = vi.fn()
const mockPut = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
    post: vi.fn().mockResolvedValue({}),
  },
}))

// ─── Mock useWpAiSuggest ───────────────────────────────────────────────────
const mockRequestSuggestion = vi.fn().mockResolvedValue(undefined)
const mockAdoptSuggestion = vi.fn().mockReturnValue(null)

vi.mock('@/composables/useWpAiSuggest', () => ({
  useWpAiSuggest: () => ({
    aiEnabled: { value: true },
    aiLoading: { value: false },
    requestSuggestion: mockRequestSuggestion,
    adoptSuggestion: mockAdoptSuggestion,
  }),
}))

// ─── Mock element-plus ─────────────────────────────────────────────────────
const mockElMessageBoxPrompt = vi.fn()

vi.mock('element-plus', async () => {
  const actual = await vi.importActual('element-plus')
  return {
    ...actual,
    ElMessage: {
      error: vi.fn(),
      success: vi.fn(),
      warning: vi.fn(),
    },
    ElMessageBox: {
      prompt: (...args: any[]) => mockElMessageBoxPrompt(...args),
    },
  }
})

// ─── Import components under test (after mocks) ───────────────────────────
import GtC25InternalAudit from '../GtC25InternalAudit.vue'
import GtC26InfoControl from '../GtC26InfoControl.vue'

// ─── Helpers ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000

/** 配置 global，stub element-plus 表格组件避免 slot 渲染错误 */
const elStubs = {
  'el-table': { template: '<div class="el-table-stub"><slot /></div>' },
  'el-table-column': { template: '<div class="el-table-column-stub" />' },
  'el-select': { template: '<div class="el-select-stub" />', props: ['modelValue', 'disabled', 'placeholder'] },
  'el-option': { template: '<div />', props: ['label', 'value'] },
  'el-input': { template: '<div class="el-input-stub" />', props: ['modelValue', 'disabled', 'type', 'autosize', 'placeholder'] },
  'el-button': { template: '<button class="el-button-stub"><slot /></button>', props: ['type', 'size', 'icon', 'link', 'loading', 'disabled'] },
  'el-skeleton': { template: '<div class="el-skeleton-stub" />', props: ['rows', 'animated'] },
  'el-icon': { template: '<span class="el-icon-stub"><slot /></span>' },
  'el-card': { template: '<div class="el-card-stub"><slot name="header" /><slot /></div>', props: ['shadow'] },
  'el-tag': { template: '<span class="el-tag-stub" @click="$emit(\'click\')"><slot /></span>', props: ['type', 'effect'] },
  'el-checkbox-group': { template: '<div class="el-checkbox-group-stub"><slot /></div>', props: ['modelValue', 'disabled', 'size'] },
  'el-checkbox': { template: '<div class="el-checkbox-stub"><slot /></div>', props: ['value'] },
  'el-tooltip': { template: '<div class="el-tooltip-stub"><slot /></div>', props: ['content', 'placement'] },
}

/** 构建 C25 mock 响应数据（10 步 + 结论） */
function buildC25Responses() {
  const items: any[] = []
  for (let n = 1; n <= 10; n++) {
    items.push(
      { item_id: `C25-step-${n}-applicable`, conclusion: n <= 5 ? '是' : '否', remark: null },
      { item_id: `C25-step-${n}-executor`, conclusion: null, remark: `审计员${n}` },
      { item_id: `C25-step-${n}-result`, conclusion: null, remark: `步骤${n}执行结果说明` },
      { item_id: `C25-step-${n}-indexRef`, conclusion: null, remark: n === 1 ? 'B6' : '' },
    )
  }
  items.push(
    { item_id: 'C25-reliance-conclusion', conclusion: '可以利用内部审计工作', remark: null },
    { item_id: 'C25-reliance-remark', conclusion: null, remark: '内审工作质量较高' },
  )
  return items
}

/** 构建 C26 mock 响应数据（3 行控制矩阵） */
function buildC26Responses() {
  const items: any[] = []
  const rows = [
    { category: '与销售循环相关的控制', indexNo: 'IT-R&R-01', elements: '完整性,准确性' },
    { category: '与采购循环相关的控制', indexNo: 'IT-R&R-02', elements: '授权,访问限制' },
    { category: '与销售循环相关的控制', indexNo: 'IT-R&R-03', elements: '完整性,准确性,授权,访问限制' },
  ]
  for (let m = 1; m <= rows.length; m++) {
    const r = rows[m - 1]
    items.push(
      { item_id: `C26-ctrl-${m}-category`, conclusion: r.category, remark: null },
      { item_id: `C26-ctrl-${m}-indexNo`, conclusion: null, remark: r.indexNo },
      { item_id: `C26-ctrl-${m}-purpose`, conclusion: null, remark: `测试目的${m}` },
      { item_id: `C26-ctrl-${m}-plannedTest`, conclusion: null, remark: `计划测试${m}` },
      { item_id: `C26-ctrl-${m}-walkthrough`, conclusion: null, remark: `穿行测试${m}` },
      { item_id: `C26-ctrl-${m}-controlTest`, conclusion: null, remark: `控制测试${m}` },
      { item_id: `C26-ctrl-${m}-testResult`, conclusion: '未发现例外', remark: null },
      { item_id: `C26-ctrl-${m}-clientFeedback`, conclusion: null, remark: '' },
      { item_id: `C26-ctrl-${m}-conclusion`, conclusion: '有效', remark: null },
      { item_id: `C26-ctrl-${m}-evidence`, conclusion: null, remark: m === 1 ? 'C22' : '' },
      { item_id: `C26-ctrl-${m}-elements`, conclusion: r.elements, remark: null },
    )
  }
  return items
}

const defaultStubs = {
  ...elStubs,
  GtIndexChip: true,
}

// ═══════════════════════════════════════════════════════════════════════════════
// C25 — GtC25InternalAudit 集成测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('GtC25InternalAudit 集成', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGet.mockResolvedValue(buildC25Responses())
    mockPut.mockResolvedValue({})
    mockRequestSuggestion.mockClear()
    mockAdoptSuggestion.mockClear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('挂载后 GET 加载数据，10 步评估正确渲染', async () => {
    const wrapper = mount(GtC25InternalAudit, {
      props: { wpId: 'wp-c25-1', projectId: 'proj-1' },
      global: { stubs: defaultStubs },
    })
    await flushPromises()

    // GET 被调用
    expect(mockGet).toHaveBeenCalledWith('/api/workpapers/wp-c25-1/checklist-responses')

    // 10 步均已加载（通过 VM 数据验证）
    const vm = wrapper.vm as any
    expect(vm.stepsData.length).toBe(10)

    // 验证 loaded 适用性：前 5 步 = '是'，后 5 步 = '否'
    const c25State = vm.c25
    expect(c25State.steps.length).toBe(10)
    expect(c25State.steps[0].applicable).toBe('是')
    expect(c25State.steps[4].applicable).toBe('是')
    expect(c25State.steps[5].applicable).toBe('否')
    expect(c25State.steps[9].applicable).toBe('否')

    // 验证执行人已加载
    expect(c25State.steps[0].executor).toBe('审计员1')
    expect(c25State.steps[9].executor).toBe('审计员10')

    // 验证执行结果已加载
    expect(c25State.steps[0].result).toBe('步骤1执行结果说明')

    // 验证索引引用已加载
    expect(c25State.steps[0].indexRef).toBe('B6')
  })

  it('结论区渲染 loaded 值', async () => {
    const wrapper = mount(GtC25InternalAudit, {
      props: { wpId: 'wp-c25-2', projectId: 'proj-1' },
      global: { stubs: defaultStubs },
    })
    await flushPromises()

    const vm = wrapper.vm as any
    expect(vm.c25.conclusion).toBe('可以利用内部审计工作')
    expect(vm.c25.remark).toBe('内审工作质量较高')
  })

  it('适用性变更触发即时 PUT', async () => {
    const wrapper = mount(GtC25InternalAudit, {
      props: { wpId: 'wp-c25-3', projectId: 'proj-1' },
      global: { stubs: defaultStubs },
    })
    await flushPromises()
    mockPut.mockClear()

    // 调用适用性更新方法（枚举字段→即时保存）
    const vm = wrapper.vm as any
    vm.updateC25StepApplicable(0, '否')
    await flushPromises()

    // 即时 PUT（不需等 debounce）
    expect(mockPut).toHaveBeenCalledTimes(1)
    expect(mockPut).toHaveBeenCalledWith(
      '/api/workpapers/wp-c25-3/checklist-responses',
      expect.objectContaining({
        project_id: 'proj-1',
        items: expect.any(Array),
      }),
    )

    // 验证 state 已更新
    expect(vm.c25.steps[0].applicable).toBe('否')
  })

  it('执行说明变更触发 debounced PUT（2s）', async () => {
    const wrapper = mount(GtC25InternalAudit, {
      props: { wpId: 'wp-c25-4', projectId: 'proj-1' },
      global: { stubs: defaultStubs },
    })
    await flushPromises()
    mockPut.mockClear()

    const vm = wrapper.vm as any
    vm.updateC25StepText(0, 'result', '新的执行情况说明')

    // 即刻无 PUT
    expect(mockPut).not.toHaveBeenCalled()

    // 不足 2s 无 PUT
    vi.advanceTimersByTime(1500)
    await flushPromises()
    expect(mockPut).not.toHaveBeenCalled()

    // 超过 2s → PUT
    vi.advanceTimersByTime(600)
    await flushPromises()
    expect(mockPut).toHaveBeenCalledTimes(1)
  })

  it('AI 按钮存在且可调用', async () => {
    const wrapper = mount(GtC25InternalAudit, {
      props: { wpId: 'wp-c25-5', projectId: 'proj-1' },
      global: { stubs: defaultStubs },
    })
    await flushPromises()

    // AI 按钮存在（通过 stub button 查找包含 "AI" 文字的按钮）
    const aiButtons = wrapper.findAll('.el-button-stub').filter(b => b.text().includes('AI'))
    expect(aiButtons.length).toBeGreaterThanOrEqual(1)

    // 调用 AI 辅助方法
    const vm = wrapper.vm as any
    await vm.onAiSuggestAll()
    expect(mockRequestSuggestion).toHaveBeenCalled()
  })

  it('readonly 模式禁用所有输入，不触发 PUT', async () => {
    const wrapper = mount(GtC25InternalAudit, {
      props: { wpId: 'wp-c25-6', projectId: 'proj-1', readonly: true },
      global: { stubs: defaultStubs },
    })
    await flushPromises()
    mockPut.mockClear()

    const vm = wrapper.vm as any
    expect(vm.isReadonly).toBe(true)

    // 尝试更新适用性（即时保存路径）
    vm.updateC25StepApplicable(0, '否')
    await flushPromises()
    expect(mockPut).not.toHaveBeenCalled()
    // state 不应改变
    expect(vm.c25.steps[0].applicable).toBe('是')

    // 尝试更新文本（debounce 路径）
    vm.updateC25StepText(0, 'result', '不应保存')
    vi.advanceTimersByTime(DEBOUNCE_MS + 100)
    await flushPromises()
    expect(mockPut).not.toHaveBeenCalled()
    expect(vm.c25.steps[0].result).toBe('步骤1执行结果说明')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// C26 — GtC26InfoControl 集成测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('GtC26InfoControl 集成', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGet.mockResolvedValue(buildC26Responses())
    mockPut.mockResolvedValue({})
    mockElMessageBoxPrompt.mockClear()
    mockRequestSuggestion.mockClear()
    mockAdoptSuggestion.mockClear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('挂载后 GET 加载数据，矩阵表渲染正确行数', async () => {
    const wrapper = mount(GtC26InfoControl, {
      props: { wpId: 'wp-c26-1', projectId: 'proj-1' },
      global: { stubs: defaultStubs },
    })
    await flushPromises()

    // GET 被调用
    expect(mockGet).toHaveBeenCalledWith('/api/workpapers/wp-c26-1/checklist-responses')

    // 3 行数据
    const vm = wrapper.vm as any
    expect(vm.c26.rows.length).toBe(3)
    expect(vm.filteredRows.length).toBe(3)
  })

  it('四要素 checkbox 渲染 loaded 值', async () => {
    const wrapper = mount(GtC26InfoControl, {
      props: { wpId: 'wp-c26-2', projectId: 'proj-1' },
      global: { stubs: defaultStubs },
    })
    await flushPromises()

    const vm = wrapper.vm as any
    // 第 1 行：完整性、准确性
    expect(vm.c26.rows[0].elements).toEqual(['完整性', '准确性'])
    // 第 2 行：授权、访问限制
    expect(vm.c26.rows[1].elements).toEqual(['授权', '访问限制'])
    // 第 3 行：全部四要素
    expect(vm.c26.rows[2].elements).toEqual(['完整性', '准确性', '授权', '访问限制'])
  })

  it('循环筛选显示/隐藏行', async () => {
    const wrapper = mount(GtC26InfoControl, {
      props: { wpId: 'wp-c26-3', projectId: 'proj-1' },
      global: { stubs: defaultStubs },
    })
    await flushPromises()

    const vm = wrapper.vm as any
    // 初始全部显示
    expect(vm.filteredRows.length).toBe(3)

    // 筛选销售循环（行1和行3）
    vm.toggleCycleFilter('与销售循环相关的控制')
    expect(vm.filteredRows.length).toBe(2)
    expect(vm.filteredRows.every((r: any) => r.category === '与销售循环相关的控制')).toBe(true)

    // 筛选采购循环（仅行2）
    vm.toggleCycleFilter('与采购循环相关的控制')
    expect(vm.filteredRows.length).toBe(1)
    expect(vm.filteredRows[0].category).toBe('与采购循环相关的控制')

    // 清除筛选（点击同一个 = toggle off）
    vm.toggleCycleFilter('与采购循环相关的控制')
    expect(vm.filteredRows.length).toBe(3)
  })

  it('addRow（ElMessageBox.prompt）新增行 + PUT', async () => {
    mockElMessageBoxPrompt.mockResolvedValue({ value: 'IT-R&R-04' })

    const wrapper = mount(GtC26InfoControl, {
      props: { wpId: 'wp-c26-4', projectId: 'proj-1' },
      global: { stubs: defaultStubs },
    })
    await flushPromises()
    mockPut.mockClear()

    const vm = wrapper.vm as any
    const rowsBefore = vm.c26.rows.length
    await vm.onAddRow()
    await flushPromises()

    // 行数增加 1
    expect(vm.c26.rows.length).toBe(rowsBefore + 1)
    // 新行 indexNo 为用户输入值
    expect(vm.c26.rows[rowsBefore].indexNo).toBe('IT-R&R-04')
    // PUT 被调用（即时保存）
    expect(mockPut).toHaveBeenCalledTimes(1)
    expect(mockPut).toHaveBeenCalledWith(
      '/api/workpapers/wp-c26-4/checklist-responses',
      expect.objectContaining({
        project_id: 'proj-1',
        items: expect.any(Array),
      }),
    )
  })

  it('removeRow 删除行 + PUT', async () => {
    const wrapper = mount(GtC26InfoControl, {
      props: { wpId: 'wp-c26-5', projectId: 'proj-1' },
      global: { stubs: defaultStubs },
    })
    await flushPromises()
    mockPut.mockClear()

    const vm = wrapper.vm as any
    const rowsBefore = vm.c26.rows.length
    expect(rowsBefore).toBe(3)

    // 删除第 2 行（index=1）
    vm.onRemoveRow(1)
    await flushPromises()

    // 行数减少 1
    expect(vm.c26.rows.length).toBe(2)
    // 原第 3 行现在变成第 2 行
    expect(vm.c26.rows[1].indexNo).toBe('IT-R&R-03')
    // PUT 被调用（即时保存）
    expect(mockPut).toHaveBeenCalledTimes(1)
  })

  it('readonly 模式禁用所有控件', async () => {
    mockElMessageBoxPrompt.mockResolvedValue({ value: 'IT-R&R-99' })

    const wrapper = mount(GtC26InfoControl, {
      props: { wpId: 'wp-c26-6', projectId: 'proj-1', readonly: true },
      global: { stubs: defaultStubs },
    })
    await flushPromises()
    mockPut.mockClear()

    const vm = wrapper.vm as any
    expect(vm.isReadonly).toBe(true)

    // addRow 被阻止
    const rowsBefore = vm.c26.rows.length
    await vm.onAddRow()
    expect(vm.c26.rows.length).toBe(rowsBefore)

    // removeRow 被阻止
    vm.onRemoveRow(0)
    expect(vm.c26.rows.length).toBe(rowsBefore)

    // 枚举字段更新被阻止
    vm.updateC26RowEnum(0, 'conclusion', '无效')
    await flushPromises()
    expect(mockPut).not.toHaveBeenCalled()
    expect(vm.c26.rows[0].conclusion).toBe('有效')

    // 文本字段更新被阻止
    vm.updateC26RowText(0, 'purpose', '不应保存')
    vi.advanceTimersByTime(DEBOUNCE_MS + 100)
    await flushPromises()
    expect(mockPut).not.toHaveBeenCalled()
    expect(vm.c26.rows[0].purpose).toBe('测试目的1')

    // 四要素更新被阻止
    vm.updateC26RowElements(0, ['完整性'])
    await flushPromises()
    expect(mockPut).not.toHaveBeenCalled()
    expect(vm.c26.rows[0].elements).toEqual(['完整性', '准确性'])
  })
})
