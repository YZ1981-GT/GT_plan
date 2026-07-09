/**
 * C24 序时账导入年度解析 — 修复 audit_year 与日历年度错位
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'

const mockGet = vi.fn()
const mockPut = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
    post: vi.fn().mockResolvedValue({}),
  },
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
}))

const auditYear = ref<number | null>(null)
const storeYear = ref<number | null>(null)

vi.mock('@/stores/project', () => ({
  useProjectStore: () => ({
    auditYear,
    year: storeYear,
    projectId: ref('proj-1'),
    loadProjectContext: vi.fn(),
  }),
}))

vi.mock('@/composables/useWpAiSuggest', () => ({
  useWpAiSuggest: () => ({
    aiEnabled: { value: false },
    requestSuggestion: vi.fn(),
    adoptSuggestion: vi.fn().mockReturnValue(null),
  }),
}))

vi.mock('@/composables/useC24ImportExport', () => ({
  useC24ImportExport: () => ({
    exportTemplate: vi.fn(),
    exportData: vi.fn(),
    importData: vi.fn().mockResolvedValue(null),
  }),
}))

vi.mock('element-plus', async () => {
  const actual = await vi.importActual('element-plus')
  const elMessageFn = vi.fn().mockReturnValue({ close: vi.fn() })
  return {
    ...actual,
    ElMessage: Object.assign(elMessageFn, {
      error: vi.fn(),
      success: vi.fn(),
      warning: vi.fn(),
      info: vi.fn().mockReturnValue({ close: vi.fn() }),
    }),
    ElMessageBox: {
      confirm: vi.fn().mockResolvedValue(true),
    },
  }
})

import GtC24JournalDetail from '../GtC24JournalDetail.vue'

const stubs = {
  C24SummarySheet: true,
  C24BalanceIntegritySheet: true,
  C24TrialBalanceSheet: true,
  C24GapTestSheet: true,
  C24AnomalyAccountSheet: true,
  C24AnomalyEntrySheet: true,
  C24BenfordSheet: true,
  C24HolidaySheet: true,
  GtIndexChip: true,
  ElSkeleton: true,
  ElCard: true,
  ElButton: true,
  ElTag: true,
  ElAlert: true,
  ElDialog: true,
  ElIcon: true,
}

function ledgerEntry() {
  return {
    voucher_date: '2025-03-01',
    voucher_no: '记-001',
    account_code: '1001',
    account_name: '库存现金',
    debit_amount: 1000,
    credit_amount: 0,
    summary: '测试',
  }
}

beforeEach(() => {
  mockGet.mockReset()
  mockPut.mockReset()
  mockPut.mockResolvedValue({})
  auditYear.value = null
  storeYear.value = null
})

describe('C24 loadFromLedger 年度解析', () => {
  it('props.year=2026 但 projectStore.auditYear=2025 时优先用 props', async () => {
    auditYear.value = 2025
    mockGet.mockImplementation((url: string, opts?: any) => {
      if (url.includes('/checklist-responses')) return Promise.resolve([])
      if (url.includes('/entries-all')) {
        return Promise.resolve({ items: [ledgerEntry()], total: 1, page: 1, page_size: 5000 })
      }
      return Promise.resolve({})
    })

    const wrapper = mount(GtC24JournalDetail, {
      props: {
        wpId: 'wp-c24',
        projectId: 'proj-1',
        sheetName: 'C24A',
        year: '2026',
      },
      global: { stubs },
    })
    await flushPromises()

    const vm = wrapper.vm as any
    await vm.loadFromLedger(false)
    await flushPromises()

    const ledgerCall = mockGet.mock.calls.find((c) => String(c[0]).includes('/entries-all'))
    expect(ledgerCall).toBeTruthy()
    expect(ledgerCall![1]?.params?.year).toBe(2026)
  })

  it('无 props.year 时使用 projectStore.auditYear=2025 查询序时账', async () => {
    auditYear.value = 2025
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/checklist-responses')) return Promise.resolve([])
      if (url.includes('/entries-all')) {
        return Promise.resolve({ items: [ledgerEntry()], total: 1, page: 1, page_size: 5000 })
      }
      return Promise.resolve({})
    })

    const wrapper = mount(GtC24JournalDetail, {
      props: {
        wpId: 'wp-c24',
        projectId: 'proj-1',
        sheetName: 'C24A',
      },
      global: { stubs },
    })
    await flushPromises()
    // selfLoad 后 C24A 会自动 silent loadFromLedger
    await flushPromises()

    const ledgerCall = mockGet.mock.calls.find((c) => String(c[0]).includes('/entries-all'))
    expect(ledgerCall).toBeTruthy()
    expect(ledgerCall![1]?.params?.year).toBe(2025)
    const ledgerCalls = mockGet.mock.calls.filter((c) => String(c[0]).includes('/entries-all'))
    expect(ledgerCalls.length).toBeGreaterThan(0)
  })

  it('分页拉取直至 total，不受 50000 条上限', async () => {
    vi.useFakeTimers()
    auditYear.value = 2025
    let page = 0
    mockGet.mockImplementation((url: string, opts?: any) => {
      if (url.includes('/checklist-responses')) return Promise.resolve([])
      if (url.includes('/entries-all')) {
        page++
        const pageSize = opts?.params?.page_size ?? 5000
        const total = 12000
        const start = (page - 1) * pageSize
        const count = Math.min(pageSize, Math.max(0, total - start))
        const items = Array.from({ length: count }, () => ledgerEntry())
        return Promise.resolve({ items, total, page, page_size: pageSize })
      }
      return Promise.resolve({})
    })
    mockPut.mockResolvedValue({})

    const wrapper = mount(GtC24JournalDetail, {
      props: { wpId: 'wp-c24', projectId: 'proj-1', sheetName: 'C24-0' },
      global: { stubs },
    })
    await flushPromises()
    page = 0
    await (wrapper.vm as any).loadFromLedger(false)
    await vi.advanceTimersByTimeAsync(2500)
    await flushPromises()

    expect((wrapper.vm as any).journalEntries.length).toBe(12000)
    expect(page).toBe(3)
    const putBody = mockPut.mock.calls.find((c) => String(c[0]).includes('/checklist-responses'))?.[1]
    expect(putBody?.items?.some((i: any) => i.item_id === 'C24-journal-source')).toBe(true)
    const sourceItem = putBody?.items?.find((i: any) => i.item_id === 'C24-journal-source')
    expect(JSON.parse(sourceItem.remark).source).toBe('ledger')
    expect(JSON.parse(sourceItem.remark).count).toBe(12000)
    vi.useRealTimers()
  })

  it('年度与数据均空时返回空 items 不崩溃', async () => {
    auditYear.value = 2025
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/checklist-responses')) return Promise.resolve([])
      if (url.includes('/entries-all')) {
        return Promise.resolve({ items: [], total: 0, page: 1, page_size: 5000 })
      }
      return Promise.resolve({})
    })

    const wrapper = mount(GtC24JournalDetail, {
      props: { wpId: 'wp-c24', projectId: 'proj-1', sheetName: 'C24A' },
      global: { stubs },
    })
    await flushPromises()
    await flushPromises()

    expect((wrapper.vm as any).journalEntries.length).toBe(0)
  })
})
