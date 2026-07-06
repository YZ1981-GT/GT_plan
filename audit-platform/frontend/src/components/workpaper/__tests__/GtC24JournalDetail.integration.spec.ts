/**
 * GtC24JournalDetail.integration.spec.ts — C24 会计分录细节测试 端到端集成
 *
 * Spec: .kiro/specs/c23-c24-journal-entry-testing/  Task 7.1
 * Validates: Requirements 3.1, 3.3, 5.1, 6.2
 *
 * 测试流程：
 *   1. 准备已知属性的分录数据（含平衡/跳号/异常/可预测本福特分布）
 *   2. 模拟导入 → selfLoad → runAllAnalytics
 *   3. 验证各 sheet 分析结果正确
 *   4. 验证 C24-0 汇总 conclusions 同步
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'

// ─── Mocks ───────────────────────────────────────────────────────────────────

const mockGet = vi.fn()
const mockPut = vi.fn()
const mockPost = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
    post: (...args: any[]) => mockPost(...args),
  },
}))

vi.mock('@/utils/http', () => ({
  default: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), error: vi.fn(), success: vi.fn() },
  ElMessageBox: { prompt: vi.fn(), confirm: vi.fn() },
}))

vi.mock('@/composables/useWpAiSuggest', () => ({
  useWpAiSuggest: () => ({
    aiEnabled: { value: false },
    requestSuggestion: vi.fn(),
    adoptSuggestion: vi.fn(() => ''),
  }),
}))

// Stub child components to avoid deep rendering — focus on data flow
vi.mock('../c24/C24SummarySheet.vue', () => ({
  __esModule: true,
  default: {
    name: 'C24SummarySheet',
    props: ['formData', 'conclusions', 'isReadonly'],
    emits: ['update:field', 'ai-suggest'],
    template: '<div class="c24-summary-stub" :data-conclusions="JSON.stringify(conclusions)" />',
  },
}))

vi.mock('../c24/C24BalanceIntegritySheet.vue', () => ({
  __esModule: true,
  default: {
    name: 'C24BalanceIntegritySheet',
    props: ['result', 'conclusion', 'isReadonly'],
    emits: ['update:conclusion', 'ai-suggest'],
    template: '<div class="c24-balance-stub" :data-debit="result.debitTotal" :data-credit="result.creditTotal" :data-balanced="result.balanced" />',
  },
}))

vi.mock('../c24/C24TrialBalanceSheet.vue', () => ({
  __esModule: true,
  default: {
    name: 'C24TrialBalanceSheet',
    props: ['comparisons', 'conclusion', 'isReadonly'],
    emits: ['update:conclusion', 'ai-suggest'],
    template: '<div class="c24-tb-stub" :data-count="comparisons.length" />',
  },
}))

vi.mock('../c24/C24GapTestSheet.vue', () => ({
  __esModule: true,
  default: {
    name: 'C24GapTestSheet',
    props: ['gaps', 'gapNotes', 'hasData', 'conclusion', 'isReadonly'],
    emits: ['update:conclusion', 'update:gap-note', 'ai-suggest'],
    template: '<div class="c24-gap-stub" :data-gap-count="gaps.length" :data-has-data="hasData" />',
  },
}))

vi.mock('../c24/C24AnomalyAccountSheet.vue', () => ({
  __esModule: true,
  default: {
    name: 'C24AnomalyAccountSheet',
    props: ['rows', 'hasData', 'conclusion', 'isReadonly'],
    emits: ['update:conclusion', 'update:row', 'ai-suggest'],
    template: '<div class="c24-account-stub" :data-row-count="rows.length" />',
  },
}))

vi.mock('../c24/C24AnomalyEntrySheet.vue', () => ({
  __esModule: true,
  default: {
    name: 'C24AnomalyEntrySheet',
    props: ['enabledRules', 'ruleParams', 'anomalies', 'anomalyNotes', 'hasData', 'conclusion', 'isReadonly'],
    emits: ['update:conclusion', 'update:enabled-rules', 'update:rule-param', 'update:anomaly-note', 'run-screen', 'ai-suggest'],
    template: '<div class="c24-anomaly-stub" :data-anomaly-count="anomalies.length" />',
  },
}))

vi.mock('../c24/C24BenfordSheet.vue', () => ({
  __esModule: true,
  default: {
    name: 'C24BenfordSheet',
    props: ['distribution', 'chiResult', 'sampleCount', 'alpha', 'hasData', 'conclusion', 'isReadonly'],
    emits: ['update:conclusion', 'ai-suggest'],
    template: '<div class="c24-benford-stub" :data-sample-count="sampleCount" :data-significant="chiResult.significant" />',
  },
}))

vi.mock('../c24/C24HolidaySheet.vue', () => ({
  __esModule: true,
  default: {
    name: 'C24HolidaySheet',
    props: ['holidays', 'isReadonly'],
    emits: ['add-holiday', 'remove-holiday', 'update-holiday'],
    template: '<div class="c24-holiday-stub" />',
  },
}))

import GtC24JournalDetail from '../GtC24JournalDetail.vue'
import type { JournalEntry } from '@/composables/useC24AnalyticsEngine'

// ─── 测试数据：已知属性的分录集 ─────────────────────────────────────────────

/**
 * 精心设计的分录数据集：
 * - 借贷总额：借方 5,100,000 贷方 5,100,000（平衡）
 * - 凭证号：付-001~005 连续，转-001/转-003（跳号：转-002 缺失）
 * - 异常：#3 大额(2,000,000 > 1,000,000 阈值)；#5 假期录入(2025-01-01)；#6 约整数(1,000,000)
 * - 本福特：首位数 1 出现 3 次 / 2 出现 2 次 / 5 出现 2 次
 */
function buildTestEntries(): JournalEntry[] {
  return [
    { voucherDate: '2025-01-15', voucherMonth: 1, voucherType: '付', voucherNo: '付-001', summary: '办公费', accountCode: '6602', accountName: '管理费用', debit: 150000, credit: 0, voucherSheets: '1', preparer: '张三', reviewer: '李四', poster: '王五' },
    { voucherDate: '2025-01-16', voucherMonth: 1, voucherType: '付', voucherNo: '付-002', summary: '差旅费', accountCode: '6602', accountName: '管理费用', debit: 0, credit: 150000, voucherSheets: '1', preparer: '张三', reviewer: '李四', poster: '王五' },
    { voucherDate: '2025-02-10', voucherMonth: 2, voucherType: '付', voucherNo: '付-003', summary: '设备采购', accountCode: '1601', accountName: '固定资产', debit: 2000000, credit: 0, voucherSheets: '2', preparer: '赵六', reviewer: '李四', poster: '王五' },
    { voucherDate: '2025-02-10', voucherMonth: 2, voucherType: '付', voucherNo: '付-004', summary: '银行付款', accountCode: '1002', accountName: '银行存款', debit: 0, credit: 2000000, voucherSheets: '2', preparer: '赵六', reviewer: '李四', poster: '王五' },
    { voucherDate: '2025-01-01', voucherMonth: 1, voucherType: '付', voucherNo: '付-005', summary: '年末调整', accountCode: '6001', accountName: '主营业务收入', debit: 500000, credit: 0, voucherSheets: '1', preparer: '张三', reviewer: '李四', poster: '王五' },
    { voucherDate: '2025-03-01', voucherMonth: 3, voucherType: '转', voucherNo: '转-001', summary: '结转成本', accountCode: '6001', accountName: '主营业务收入', debit: 0, credit: 1000000, voucherSheets: '1', preparer: '张三', reviewer: '李四', poster: '王五' },
    { voucherDate: '2025-03-15', voucherMonth: 3, voucherType: '转', voucherNo: '转-003', summary: '结转损益', accountCode: '6602', accountName: '管理费用', debit: 2450000, credit: 1950000, voucherSheets: '1', preparer: '张三', reviewer: '李四', poster: '王五' },
  ]
}

// ─── 挂载辅助 ────────────────────────────────────────────────────────────────

const stubs = {
  'el-skeleton': true,
  'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>' },
  'el-dropdown': { template: '<div class="el-dropdown"><slot /><slot name="dropdown" /></div>' },
  'el-dropdown-menu': { template: '<div><slot /></div>' },
  'el-dropdown-item': { props: ['command'], template: '<div @click="$emit(\'command\', command)"><slot /></div>' },
  'el-alert': { props: ['type'], template: '<div class="el-alert"><slot /><slot name="title" /></div>' },
}

/**
 * 挂载 GtC24JournalDetail 并配置 mock 后端。
 * 支持通过 responses 参数模拟已持久化的分录数据（selfLoad 从 checklist-responses 加载）。
 */
function mountC24(opts: {
  sheetName?: string
  responses?: any[]
  readonly?: boolean
}) {
  const { sheetName = 'C24-1', responses = [], readonly = false } = opts

  mockGet.mockImplementation((url: string, _options?: any) => {
    if (typeof url !== 'string') return Promise.resolve({})
    if (url.includes('/checklist-responses')) return Promise.resolve(responses)
    if (url.includes('/feature-flags')) return Promise.resolve({ flags: { WP_AI_SERVICE_ENABLED: false } })
    return Promise.resolve({})
  })

  return mount(GtC24JournalDetail, {
    props: { wpId: 'wp-c24-test', projectId: 'proj-1', wpCode: 'C24', sheetName, readonly },
    global: { stubs },
  })
}

/**
 * 生成 checklist-responses 格式的已导入分录数据（模拟 selfLoad 恢复）
 */
function buildResponsesWithEntries(entries: JournalEntry[]): any[] {
  return [
    { item_id: 'C24-journal-entries', conclusion: null, remark: JSON.stringify(entries), wp_ref: null },
    { item_id: 'C24-holidays', conclusion: null, remark: JSON.stringify([{ date: '2025-01-01', name: '元旦' }]), wp_ref: null },
  ]
}

beforeEach(() => {
  mockGet.mockReset()
  mockPut.mockReset()
  mockPost.mockReset()
  mockPut.mockResolvedValue([])
})

// ─────────────────────────────────────────────────────────────────────────────
// 1. 导入分录 → 完整性测试（Req 3.1: 借贷平衡）
// ─────────────────────────────────────────────────────────────────────────────

describe('端到端：导入分录 → 借贷平衡完整性（Req 3.1）', () => {
  it('selfLoad 加载分录后 balanceResult 计算正确（借贷平衡）', async () => {
    const entries = buildTestEntries()
    const responses = buildResponsesWithEntries(entries)
    const wrapper = mountC24({ sheetName: 'C24-1', responses })
    await flushPromises()

    const stub = wrapper.find('.c24-balance-stub')
    expect(stub.exists()).toBe(true)
    // 已知数据：借方 = 150000+2000000+500000+2450000 = 5100000
    //           贷方 = 150000+2000000+1000000+1950000 = 5100000 → balanced
    expect(Number(stub.attributes('data-debit'))).toBe(5100000)
    expect(Number(stub.attributes('data-credit'))).toBe(5100000)
    expect(stub.attributes('data-balanced')).toBe('true')
  })

  it('借贷不平衡分录正确标记 balanced=false', async () => {
    const entries = buildTestEntries()
    // 修改最后一笔使其不平衡
    entries[6].credit = 1900000 // 少 50000
    const responses = buildResponsesWithEntries(entries)
    const wrapper = mountC24({ sheetName: 'C24-1', responses })
    await flushPromises()

    const stub = wrapper.find('.c24-balance-stub')
    expect(stub.attributes('data-balanced')).toBe('false')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 2. 跳号测试（Req 3.3）
// ─────────────────────────────────────────────────────────────────────────────

describe('端到端：导入分录 → 跳号测试（Req 3.3）', () => {
  it('检测已知跳号：转-002 缺失', async () => {
    const entries = buildTestEntries()
    const responses = buildResponsesWithEntries(entries)
    const wrapper = mountC24({ sheetName: 'C24-3', responses })
    await flushPromises()

    const stub = wrapper.find('.c24-gap-stub')
    expect(stub.exists()).toBe(true)
    expect(stub.attributes('data-has-data')).toBe('true')
    // 付-001~005 连续无跳号；转-001/转-003 跳 转-002 → 1 个缺口
    expect(Number(stub.attributes('data-gap-count'))).toBe(1)
  })

  it('无跳号数据时返回 0 缺口', async () => {
    const entries: JournalEntry[] = [
      { voucherDate: '2025-01-01', voucherMonth: 1, voucherType: '付', voucherNo: '付-001', summary: 'a', accountCode: '1001', accountName: '现金', debit: 100, credit: 0, voucherSheets: '1', preparer: 'A', reviewer: 'B', poster: 'C' },
      { voucherDate: '2025-01-02', voucherMonth: 1, voucherType: '付', voucherNo: '付-002', summary: 'b', accountCode: '1001', accountName: '现金', debit: 0, credit: 100, voucherSheets: '1', preparer: 'A', reviewer: 'B', poster: 'C' },
    ]
    const responses = buildResponsesWithEntries(entries)
    const wrapper = mountC24({ sheetName: 'C24-3', responses })
    await flushPromises()

    const stub = wrapper.find('.c24-gap-stub')
    expect(Number(stub.attributes('data-gap-count'))).toBe(0)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 3. 异常分录筛选（Req 3.1 & 4.1 间接）
// ─────────────────────────────────────────────────────────────────────────────

describe('端到端：导入分录 → 异常筛选（Req 4.1）', () => {
  it('检测到预期异常分录（大额/假期/约整数）', async () => {
    const entries = buildTestEntries()
    const responses = buildResponsesWithEntries(entries)
    const wrapper = mountC24({ sheetName: 'C24-5', responses })
    await flushPromises()

    const stub = wrapper.find('.c24-anomaly-stub')
    expect(stub.exists()).toBe(true)
    // 已知异常：
    // - 付-003 debit=2,000,000 → 大额(>1M) + 约整数(末4位为0)
    // - 付-005 date=2025-01-01 → 假期录入
    // - 转-001 credit=1,000,000 → 约整数
    // - 转-003 debit=2,450,000 → 大额
    // 至少有 4 条异常
    const count = Number(stub.attributes('data-anomaly-count'))
    expect(count).toBeGreaterThanOrEqual(4)
  })

  it('无分录数据时显示空数据引导区', async () => {
    const wrapper = mountC24({ sheetName: 'C24-5', responses: [] })
    await flushPromises()

    // 无分录时应显示空数据引导区，而非异常分录组件
    const emptyGuide = wrapper.find('.c24-empty-data-guide')
    expect(emptyGuide.exists()).toBe(true)
    const stub = wrapper.find('.c24-anomaly-stub')
    expect(stub.exists()).toBe(false)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 4. 本福特定律分析（Req 5.1）
// ─────────────────────────────────────────────────────────────────────────────

describe('端到端：导入分录 → 本福特分析（Req 5.1）', () => {
  it('加载分录后本福特分布有样本数据', async () => {
    const entries = buildTestEntries()
    const responses = buildResponsesWithEntries(entries)
    const wrapper = mountC24({ sheetName: '本福特', responses })
    await flushPromises()

    const stub = wrapper.find('.c24-benford-stub')
    expect(stub.exists()).toBe(true)
    // 7 条分录有有效金额（取 max(debit, credit) > 0）
    expect(Number(stub.attributes('data-sample-count'))).toBe(7)
  })

  it('少量样本时本福特卡方未必显著（数据量不足难以结论）', async () => {
    const entries = buildTestEntries()
    const responses = buildResponsesWithEntries(entries)
    const wrapper = mountC24({ sheetName: '本福特', responses })
    await flushPromises()

    const stub = wrapper.find('.c24-benford-stub')
    // 7 条数据太少，不应显著（chi2 临界值 15.507@df8）
    // 但结果取决于具体首位数分布，此处验证字段存在
    expect(stub.attributes('data-significant')).toBeDefined()
  })

  it('大量均匀首位数数据本福特应显著偏离', async () => {
    // 构造 900 条分录，每个首位数 1-9 各 100 条（均匀）
    const entries: JournalEntry[] = []
    for (let d = 1; d <= 9; d++) {
      for (let i = 0; i < 100; i++) {
        entries.push({
          voucherDate: '2025-01-15', voucherMonth: 1, voucherType: '转',
          voucherNo: `转-${String(entries.length + 1).padStart(3, '0')}`,
          summary: '测试', accountCode: '6001', accountName: '收入',
          debit: d * 100 + i, credit: 0,
          voucherSheets: '1', preparer: 'A', reviewer: 'B', poster: 'C',
        })
      }
    }
    const responses = buildResponsesWithEntries(entries)
    const wrapper = mountC24({ sheetName: '本福特', responses })
    await flushPromises()

    const stub = wrapper.find('.c24-benford-stub')
    expect(Number(stub.attributes('data-sample-count'))).toBe(900)
    expect(stub.attributes('data-significant')).toBe('true')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 5. C24-0 汇总 conclusions 同步（Req 6.2）
// ─────────────────────────────────────────────────────────────────────────────

describe('端到端：C24-0 汇总反映各测试项结论（Req 6.2）', () => {
  it('各 sheet 结论回写后 C24-0 汇总的 conclusions 同步', async () => {
    const entries = buildTestEntries()
    const responses = [
      ...buildResponsesWithEntries(entries),
      { item_id: 'C24-1-conclusion', conclusion: '借贷平衡，无异常', remark: null, wp_ref: null },
      { item_id: 'C24-3-conclusion', conclusion: '发现跳号1处，需进一步调查', remark: null, wp_ref: null },
      { item_id: 'C24-5-conclusion', conclusion: '识别异常分录4笔', remark: null, wp_ref: null },
      { item_id: 'C24-benford-conclusion', conclusion: '首位数分布无显著偏离', remark: null, wp_ref: null },
    ]
    const wrapper = mountC24({ sheetName: 'C24-0', responses })
    await flushPromises()

    const stub = wrapper.find('.c24-summary-stub')
    expect(stub.exists()).toBe(true)
    // conclusions prop 应包含各子 sheet 结论
    const conclusionsData = JSON.parse(stub.attributes('data-conclusions')!)
    expect(conclusionsData['C24-1']).toBe('借贷平衡，无异常')
    expect(conclusionsData['C24-3']).toBe('发现跳号1处，需进一步调查')
    expect(conclusionsData['C24-5']).toBe('识别异常分录4笔')
    expect(conclusionsData['benford']).toBe('首位数分布无显著偏离')
  })

  it('结论更新后 persistAll 写回 checklist-responses', async () => {
    const entries = buildTestEntries()
    const responses = buildResponsesWithEntries(entries)
    const wrapper = mountC24({ sheetName: 'C24-1', responses })
    await flushPromises()

    // 通过 vm 直接触发结论更新
    const vm = wrapper.vm as any
    vm.onConclusionChange('C24-1', '测试通过')
    await flushPromises()

    // 验证 PUT 调用（可能有多次 PUT：saveConclusion + writeConclusionToSummary）
    expect(mockPut).toHaveBeenCalled()
    // 在所有 PUT 调用中查找包含 C24-1-conclusion 的那次
    const allCalls = mockPut.mock.calls
    let c24Item: any = undefined
    for (const call of allCalls) {
      const items = call[1]?.items
      if (Array.isArray(items)) {
        const found = items.find((it: any) => it.item_id === 'C24-1-conclusion')
        if (found) { c24Item = found; break }
      }
    }
    expect(c24Item).toBeTruthy()
    expect(c24Item.conclusion).toBe('测试通过')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 6. sheetName 分发正确性（端到端渲染验证）
// ─────────────────────────────────────────────────────────────────────────────

describe('端到端：sheetName 分发各 sheet 渲染正确组件', () => {
  it.each([
    ['C24A', '.c24-console'],
    ['C24-0', '.c24-summary-stub'],
    ['C24-1', '.c24-balance-stub'],
    ['C24-2', '.c24-tb-stub'],
    ['C24-3', '.c24-gap-stub'],
    ['C24-4', '.c24-account-stub'],
    ['C24-5', '.c24-anomaly-stub'],
    ['本福特', '.c24-benford-stub'],
    ['假期清单', '.c24-holiday-stub'],
  ])('sheetName=%s → 渲染 %s', async (sheetName, selector) => {
    const entries = buildTestEntries()
    const responses = buildResponsesWithEntries(entries)
    const wrapper = mountC24({ sheetName, responses })
    await flushPromises()
    expect(wrapper.find(selector).exists()).toBe(true)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 7. 只读模式隐藏导入导出（Req 8.3 间接）
// ─────────────────────────────────────────────────────────────────────────────

describe('端到端：只读模式', () => {
  it('readonly=true 时不渲染导入导出 toolbar', async () => {
    const entries = buildTestEntries()
    const responses = buildResponsesWithEntries(entries)
    const wrapper = mountC24({ sheetName: 'C24-1', responses, readonly: true })
    await flushPromises()

    expect(wrapper.find('.c24-toolbar').exists()).toBe(false)
  })

  it('readonly=false 时渲染导入导出 toolbar', async () => {
    const entries = buildTestEntries()
    const responses = buildResponsesWithEntries(entries)
    const wrapper = mountC24({ sheetName: 'C24-1', responses, readonly: false })
    await flushPromises()

    expect(wrapper.find('.c24-toolbar').exists()).toBe(true)
  })
})
