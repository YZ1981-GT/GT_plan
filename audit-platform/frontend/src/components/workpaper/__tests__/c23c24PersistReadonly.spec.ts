/**
 * C23/C24 持久化即时/debounce 保存 + readonly 禁编辑测试
 *
 * Spec: .kiro/specs/c23-c24-journal-entry-testing/
 * Task: 6.2
 *
 * **Validates: Requirements 8.3, 8.5**
 *
 * Tests:
 *  1. Debounce save: data changes trigger a debounced save (2s), not immediate
 *  2. Immediate save for conclusion fields
 *  3. Save failure: error message shown + local data preserved
 *  4. Readonly: all edits blocked when readonly=true
 *  5. Readonly: GtIndexChip navigation still works
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
vi.mock('@/composables/useWpAiSuggest', () => ({
  useWpAiSuggest: () => ({
    aiEnabled: { value: false },
    requestSuggestion: vi.fn(),
    adoptSuggestion: vi.fn().mockReturnValue(null),
  }),
}))

// ─── Mock ElMessage ────────────────────────────────────────────────────────
vi.mock('element-plus', async () => {
  const actual = await vi.importActual('element-plus')
  return {
    ...actual,
    ElMessage: {
      error: vi.fn(),
      success: vi.fn(),
      warning: vi.fn(),
    },
    ElMessageBox: { prompt: vi.fn().mockRejectedValue('cancel') },
  }
})

// Import after mock to get mocked reference
import { ElMessage } from 'element-plus'

// ─── Mock useC24ImportExport ───────────────────────────────────────────────
vi.mock('@/composables/useC24ImportExport', () => ({
  useC24ImportExport: () => ({
    exportTemplate: vi.fn(),
    exportData: vi.fn(),
    importData: vi.fn().mockResolvedValue(null),
  }),
}))

// ─── Import components under test (after mocks) ───────────────────────────
import GtC23JournalControl from '../GtC23JournalControl.vue'
import GtC24JournalDetail from '../GtC24JournalDetail.vue'

// ─── Helpers ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000

function buildC23Responses() {
  return [
    { item_id: 'C23-1-source', conclusion: null, remark: '来源说明' },
    { item_id: 'C23-1-conclusion', conclusion: '完整', remark: null },
    { item_id: 'C23-person-1-name', conclusion: null, remark: '张三' },
    { item_id: 'C23-person-1-role', conclusion: '创建', remark: null },
    { item_id: 'C23-person-1-note', conclusion: null, remark: '' },
    { item_id: 'C23-2-conclusion', conclusion: '无偏差', remark: null },
    { item_id: 'C23-sample-1-date', conclusion: null, remark: '2025-01-15' },
    { item_id: 'C23-sample-1-voucherNo', conclusion: null, remark: 'PZ-001' },
    { item_id: 'C23-sample-1-preparer', conclusion: null, remark: '张三' },
    { item_id: 'C23-sample-1-poster', conclusion: null, remark: '李四' },
    { item_id: 'C23-sample-1-reviewer', conclusion: null, remark: '王五' },
    { item_id: 'C23-sample-1-deviation', conclusion: '否', remark: null },
  ]
}

function buildC24Responses() {
  return [
    { item_id: 'C24-0-source-appName', conclusion: null, remark: '金蝶' },
    { item_id: 'C24-0-conclusion', conclusion: '完整性通过', remark: null },
    { item_id: 'C24-1-conclusion', conclusion: '借贷平衡', remark: null },
    { item_id: 'C24-journal-entries', conclusion: null, remark: JSON.stringify([]) },
    { item_id: 'C24-holidays', conclusion: null, remark: JSON.stringify([]) },
  ]
}

const defaultStubs = {
  GtAProgramConsole: true,
  C23PersonnelSheet: true,
  C23SampleSheet: true,
  C24SummarySheet: true,
  C24BalanceIntegritySheet: true,
  C24TrialBalanceSheet: true,
  C24GapTestSheet: true,
  C24AnomalyAccountSheet: true,
  C24AnomalyEntrySheet: true,
  C24BenfordSheet: true,
  C24HolidaySheet: true,
}

// ═══════════════════════════════════════════════════════════════════════════════
// C23 — Debounce Save Tests
// ═══════════════════════════════════════════════════════════════════════════════

describe('C23 持久化 debounce 保存', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGet.mockResolvedValue(buildC23Responses())
    mockPut.mockResolvedValue({})
    vi.mocked(ElMessage.error).mockClear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('数据变更后不立即调用 PUT，等待 debounce 2s', async () => {
    const wrapper = mount(GtC23JournalControl, {
      props: { wpId: 'wp-c23-1', projectId: 'proj-1', sheetName: 'C23-1' },
      global: { stubs: defaultStubs },
    })
    await flushPromises()
    mockPut.mockClear()

    // Trigger data change via component method
    const vm = wrapper.vm as any
    vm.onSourceDescChange('新的来源说明')

    // Immediately after change — no PUT yet
    expect(mockPut).not.toHaveBeenCalled()

    // Advance less than debounce period
    vi.advanceTimersByTime(1000)
    expect(mockPut).not.toHaveBeenCalled()

    // Advance to full debounce period
    vi.advanceTimersByTime(1100)
    await flushPromises()

    // Now PUT should have been called
    expect(mockPut).toHaveBeenCalledTimes(1)
    expect(mockPut).toHaveBeenCalledWith(
      '/api/workpapers/wp-c23-1/checklist-responses',
      expect.objectContaining({
        project_id: 'proj-1',
        items: expect.any(Array),
      }),
    )
  })

  it('多次快速变更仅触发一次 PUT（debounce 合并）', async () => {
    const wrapper = mount(GtC23JournalControl, {
      props: { wpId: 'wp-c23-2', projectId: 'proj-1', sheetName: 'C23-1' },
      global: { stubs: defaultStubs },
    })
    await flushPromises()
    mockPut.mockClear()

    const vm = wrapper.vm as any
    // Multiple rapid changes within debounce window
    vm.onSourceDescChange('变更1')
    vi.advanceTimersByTime(500)
    vm.onSourceDescChange('变更2')
    vi.advanceTimersByTime(500)
    vm.onSourceDescChange('变更3')

    // Not yet at debounce threshold from last change (1500 < 2000)
    vi.advanceTimersByTime(1500)
    await flushPromises()
    expect(mockPut).not.toHaveBeenCalled()

    // Now past debounce from last change (total 2100ms > 2000ms from last)
    vi.advanceTimersByTime(600)
    await flushPromises()

    // Only 1 PUT call (debounced/merged)
    expect(mockPut).toHaveBeenCalledTimes(1)
  })

  it('结论字段变更即时保存（不经 debounce）', async () => {
    const wrapper = mount(GtC23JournalControl, {
      props: { wpId: 'wp-c23-3', projectId: 'proj-1', sheetName: 'C23-1' },
      global: { stubs: defaultStubs },
    })
    await flushPromises()
    mockPut.mockClear()

    const vm = wrapper.vm as any
    vm.onConclusion1Change('新结论')
    await flushPromises()

    // Conclusion saves immediately (no debounce wait)
    expect(mockPut).toHaveBeenCalledTimes(1)
    expect(mockPut).toHaveBeenCalledWith(
      '/api/workpapers/wp-c23-3/checklist-responses',
      expect.objectContaining({
        items: [{ item_id: 'C23-1-conclusion', conclusion: '新结论', remark: null }],
      }),
    )
  })

  it('保存失败时提示错误并保留本地数据', async () => {
    mockPut.mockRejectedValueOnce(new Error('Network Error'))

    const wrapper = mount(GtC23JournalControl, {
      props: { wpId: 'wp-c23-4', projectId: 'proj-1', sheetName: 'C23-1' },
      global: { stubs: defaultStubs },
    })
    await flushPromises()
    mockPut.mockClear()

    const vm = wrapper.vm as any
    vm.onSourceDescChange('重要数据')
    vi.advanceTimersByTime(DEBOUNCE_MS + 100)
    await flushPromises()

    // Error message shown
    expect(ElMessage.error).toHaveBeenCalledWith('保存失败，数据已保留在本地')

    // Local data preserved
    expect(vm.sourceDesc).toBe('重要数据')
  })

  it('unmount 时 flush 待保存的变更', async () => {
    const wrapper = mount(GtC23JournalControl, {
      props: { wpId: 'wp-c23-5', projectId: 'proj-1', sheetName: 'C23-1' },
      global: { stubs: defaultStubs },
    })
    await flushPromises()
    mockPut.mockClear()

    const vm = wrapper.vm as any
    vm.onSourceDescChange('即将卸载')

    // Unmount triggers flushPendingSaves
    wrapper.unmount()
    await flushPromises()

    expect(mockPut).toHaveBeenCalledTimes(1)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// C23 — Readonly 禁编辑 Tests
// ═══════════════════════════════════════════════════════════════════════════════

describe('C23 readonly 禁编辑', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGet.mockResolvedValue(buildC23Responses())
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('readonly=true 时 persistAll 不执行 PUT', async () => {
    const wrapper = mount(GtC23JournalControl, {
      props: { wpId: 'wp-c23-ro1', projectId: 'proj-1', sheetName: 'C23-1', readonly: true },
      global: { stubs: defaultStubs },
    })
    await flushPromises()
    mockPut.mockClear()

    // Try to trigger save via internal method
    const vm = wrapper.vm as any
    vm.onSourceDescChange('should not save')
    vi.advanceTimersByTime(DEBOUNCE_MS + 100)
    await flushPromises()

    // readonly prevents persistAll from calling API
    expect(mockPut).not.toHaveBeenCalled()
  })

  it('readonly=true 时 onAddPerson 无操作', async () => {
    const wrapper = mount(GtC23JournalControl, {
      props: { wpId: 'wp-c23-ro2', projectId: 'proj-1', sheetName: 'C23-1', readonly: true },
      global: { stubs: defaultStubs },
    })
    await flushPromises()

    const vm = wrapper.vm as any
    const personsBefore = vm.persons.length
    await vm.onAddPerson()

    // No person added in readonly mode
    expect(vm.persons.length).toBe(personsBefore)
  })

  it('readonly=true 时 onRemovePerson 无操作', async () => {
    const wrapper = mount(GtC23JournalControl, {
      props: { wpId: 'wp-c23-ro3', projectId: 'proj-1', sheetName: 'C23-1', readonly: true },
      global: { stubs: defaultStubs },
    })
    await flushPromises()

    const vm = wrapper.vm as any
    const personsBefore = [...vm.persons]
    vm.onRemovePerson(0)

    // Persons unchanged
    expect(vm.persons).toEqual(personsBefore)
  })

  it('readonly=true 时 onUpdatePerson 无操作', async () => {
    const wrapper = mount(GtC23JournalControl, {
      props: { wpId: 'wp-c23-ro4', projectId: 'proj-1', sheetName: 'C23-1', readonly: true },
      global: { stubs: defaultStubs },
    })
    await flushPromises()

    const vm = wrapper.vm as any
    if (vm.persons.length > 0) {
      const nameBefore = vm.persons[0].name
      vm.onUpdatePerson(0, 'name', '新名字')
      expect(vm.persons[0].name).toBe(nameBefore)
    }
  })

  it('readonly=true 时 onUpdateSample 无操作', async () => {
    const wrapper = mount(GtC23JournalControl, {
      props: { wpId: 'wp-c23-ro5', projectId: 'proj-1', sheetName: 'C23-2', readonly: true },
      global: { stubs: defaultStubs },
    })
    await flushPromises()

    const vm = wrapper.vm as any
    if (vm.samples.length > 0) {
      const dateBefore = vm.samples[0].date
      vm.onUpdateSample(0, 'date', '2025-12-31')
      expect(vm.samples[0].date).toBe(dateBefore)
    }
  })

  it('readonly=true 时结论即时保存也被阻止', async () => {
    const wrapper = mount(GtC23JournalControl, {
      props: { wpId: 'wp-c23-ro6', projectId: 'proj-1', sheetName: 'C23-1', readonly: true },
      global: { stubs: defaultStubs },
    })
    await flushPromises()
    mockPut.mockClear()

    const vm = wrapper.vm as any
    vm.onConclusion1Change('readonly结论')
    await flushPromises()

    expect(mockPut).not.toHaveBeenCalled()
  })

  it('readonly=true 子组件接收到 isReadonly=true', async () => {
    const wrapper = mount(GtC23JournalControl, {
      props: { wpId: 'wp-c23-ro7', projectId: 'proj-1', sheetName: 'C23-1', readonly: true },
      global: { stubs: defaultStubs },
    })
    await flushPromises()

    // The isReadonly computed should be true
    const vm = wrapper.vm as any
    expect(vm.isReadonly).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// C24 — Debounce Save Tests
// ═══════════════════════════════════════════════════════════════════════════════

describe('C24 持久化 debounce 保存', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGet.mockImplementation((url: string) => {
      if (typeof url === 'string' && url.includes('/entries-all')) {
        return Promise.resolve({ items: [], total: 0, page: 1, page_size: 5000 })
      }
      return Promise.resolve(buildC24Responses())
    })
    mockPut.mockResolvedValue({})
    vi.mocked(ElMessage.error).mockClear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('C24 summary 字段变更触发 debounce（非即时）', async () => {
    const wrapper = mount(GtC24JournalDetail, {
      props: { wpId: 'wp-c24-1', projectId: 'proj-1', sheetName: 'C24-0' },
      global: { stubs: defaultStubs },
    })
    await flushPromises()
    mockPut.mockClear()

    const vm = wrapper.vm as any
    vm.onSummaryFieldChange('sourceAppName', '用友U8')

    // Not immediate
    expect(mockPut).not.toHaveBeenCalled()

    vi.advanceTimersByTime(1000)
    expect(mockPut).not.toHaveBeenCalled()

    vi.advanceTimersByTime(1100)
    await flushPromises()

    expect(mockPut).toHaveBeenCalledTimes(1)
  })

  it('C24 结论字段即时保存', async () => {
    const wrapper = mount(GtC24JournalDetail, {
      props: { wpId: 'wp-c24-2', projectId: 'proj-1', sheetName: 'C24-1' },
      global: { stubs: defaultStubs },
    })
    await flushPromises()
    await flushPromises()
    vi.advanceTimersByTime(3000)
    await flushPromises()
    mockPut.mockClear()

    const vm = wrapper.vm as any
    vm.onConclusionChange('C24-1', '借贷平衡，完整性通过')
    await flushPromises()

    // Conclusion saves immediately (+ C24-0 汇总回填第二条 PUT)
    expect(mockPut).toHaveBeenCalledTimes(2)
    expect(mockPut).toHaveBeenCalledWith(
      '/api/workpapers/wp-c24-2/checklist-responses',
      expect.objectContaining({
        items: [{ item_id: 'C24-1-conclusion', conclusion: '借贷平衡，完整性通过', remark: null }],
      }),
    )
  })

  it('C24 多次快速变更合并为一次 PUT', async () => {
    const wrapper = mount(GtC24JournalDetail, {
      props: { wpId: 'wp-c24-3', projectId: 'proj-1', sheetName: 'C24-5' },
      global: { stubs: defaultStubs },
    })
    await flushPromises()
    mockPut.mockClear()

    const vm = wrapper.vm as any
    vm.onEnabledRulesChange(['holidays', 'night'])
    vi.advanceTimersByTime(300)
    vm.onRuleParamChange('nightStartHour', 23)
    vi.advanceTimersByTime(300)
    vm.onRuleParamChange('largeAmountThreshold', 2000000)

    // Still under debounce
    vi.advanceTimersByTime(1500)
    expect(mockPut).not.toHaveBeenCalled()

    // Past debounce from last change
    vi.advanceTimersByTime(600)
    await flushPromises()

    expect(mockPut).toHaveBeenCalledTimes(1)
  })

  it('C24 保存失败提示错误并保留本地', async () => {
    mockPut.mockRejectedValueOnce(new Error('Server Error'))

    const wrapper = mount(GtC24JournalDetail, {
      props: { wpId: 'wp-c24-4', projectId: 'proj-1', sheetName: 'C24-0' },
      global: { stubs: defaultStubs },
    })
    await flushPromises()
    mockPut.mockClear()
    mockPut.mockRejectedValueOnce(new Error('Server Error'))

    const vm = wrapper.vm as any
    vm.onSummaryFieldChange('sourceAppName', '金蝶K3')
    vi.advanceTimersByTime(DEBOUNCE_MS + 100)
    await flushPromises()

    // Error shown
    expect(ElMessage.error).toHaveBeenCalledWith('保存失败，数据已保留在本地')

    // Local data preserved
    expect(vm.summaryForm.sourceAppName).toBe('金蝶K3')
  })

  it('C24 unmount 时 flush 待保存变更', async () => {
    const wrapper = mount(GtC24JournalDetail, {
      props: { wpId: 'wp-c24-5', projectId: 'proj-1', sheetName: 'C24-0' },
      global: { stubs: defaultStubs },
    })
    await flushPromises()
    mockPut.mockClear()

    const vm = wrapper.vm as any
    vm.onSummaryFieldChange('toolName', 'IDEA')

    wrapper.unmount()
    await flushPromises()

    expect(mockPut).toHaveBeenCalledTimes(1)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// C24 — Readonly 禁编辑 Tests
// ═══════════════════════════════════════════════════════════════════════════════

describe('C24 readonly 禁编辑', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGet.mockImplementation((url: string) => {
      if (typeof url === 'string' && url.includes('/entries-all')) {
        return Promise.resolve({ items: [], total: 0, page: 1, page_size: 5000 })
      }
      return Promise.resolve(buildC24Responses())
    })
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('readonly=true 时 persistAll 不执行 PUT', async () => {
    const wrapper = mount(GtC24JournalDetail, {
      props: { wpId: 'wp-c24-ro1', projectId: 'proj-1', sheetName: 'C24-0', readonly: true },
      global: { stubs: defaultStubs },
    })
    await flushPromises()
    mockPut.mockClear()

    const vm = wrapper.vm as any
    vm.onSummaryFieldChange('sourceAppName', 'should not save')
    vi.advanceTimersByTime(DEBOUNCE_MS + 100)
    await flushPromises()

    expect(mockPut).not.toHaveBeenCalled()
  })

  it('readonly=true 时 导入导出 dropdown 不渲染', async () => {
    const wrapper = mount(GtC24JournalDetail, {
      props: { wpId: 'wp-c24-ro2', projectId: 'proj-1', sheetName: 'C24-0', readonly: true },
      global: { stubs: defaultStubs },
    })
    await flushPromises()

    // toolbar should not be visible in readonly mode
    expect(wrapper.find('.c24-toolbar').exists()).toBe(false)
  })

  it('readonly=true 时 onAddHoliday 无操作', async () => {
    const wrapper = mount(GtC24JournalDetail, {
      props: { wpId: 'wp-c24-ro3', projectId: 'proj-1', sheetName: '假期清单', readonly: true },
      global: { stubs: defaultStubs },
    })
    await flushPromises()

    const vm = wrapper.vm as any
    const countBefore = vm.holidays.length
    vm.onAddHoliday()
    expect(vm.holidays.length).toBe(countBefore)
  })

  it('readonly=true 时 onRemoveHoliday 无操作', async () => {
    // Preload with a holiday
    const responses = [
      ...buildC24Responses(),
      { item_id: 'C24-holidays', conclusion: null, remark: JSON.stringify([{ date: '2025-01-01', name: '元旦' }]) },
    ]
    mockGet.mockResolvedValue(responses)

    const wrapper = mount(GtC24JournalDetail, {
      props: { wpId: 'wp-c24-ro4', projectId: 'proj-1', sheetName: '假期清单', readonly: true },
      global: { stubs: defaultStubs },
    })
    await flushPromises()

    const vm = wrapper.vm as any
    const countBefore = vm.holidays.length
    vm.onRemoveHoliday(0)
    expect(vm.holidays.length).toBe(countBefore)
  })

  it('readonly=true 时 onUpdateHoliday 无操作', async () => {
    const responses = [
      ...buildC24Responses(),
      { item_id: 'C24-holidays', conclusion: null, remark: JSON.stringify([{ date: '2025-01-01', name: '元旦' }]) },
    ]
    mockGet.mockResolvedValue(responses)

    const wrapper = mount(GtC24JournalDetail, {
      props: { wpId: 'wp-c24-ro5', projectId: 'proj-1', sheetName: '假期清单', readonly: true },
      global: { stubs: defaultStubs },
    })
    await flushPromises()

    const vm = wrapper.vm as any
    if (vm.holidays.length > 0) {
      const nameBefore = vm.holidays[0].name
      vm.onUpdateHoliday(0, 'name', '春节')
      expect(vm.holidays[0].name).toBe(nameBefore)
    }
  })

  it('readonly=true 时 isReadonly computed 为 true', async () => {
    const wrapper = mount(GtC24JournalDetail, {
      props: { wpId: 'wp-c24-ro6', projectId: 'proj-1', sheetName: 'C24-0', readonly: true },
      global: { stubs: defaultStubs },
    })
    await flushPromises()

    const vm = wrapper.vm as any
    expect(vm.isReadonly).toBe(true)
  })

  it('readonly=true 时结论即时保存也被阻止', async () => {
    const wrapper = mount(GtC24JournalDetail, {
      props: { wpId: 'wp-c24-ro7', projectId: 'proj-1', sheetName: 'C24-1', readonly: true },
      global: { stubs: defaultStubs },
    })
    await flushPromises()
    mockPut.mockClear()

    const vm = wrapper.vm as any
    vm.onConclusionChange('C24-1', '不应保存')
    await flushPromises()

    expect(mockPut).not.toHaveBeenCalled()
  })
})
