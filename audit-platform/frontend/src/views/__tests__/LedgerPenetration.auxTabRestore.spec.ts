/**
 * 账簿查询页：从 URL 恢复辅助余额表 + 年度回退项目审计年度（2026-10-31 用户报「辅助余额表没有维度可选了」）。
 *
 * 切页签会写 URL（多窗口现场恢复），DefaultLayout 按 fullPath 给页面加 key ⇒ 每次切页签都整页重挂、
 * 新实例从 URL 恢复。原先恢复到辅助余额表只设页签、不加载 ⇒ 只剩「全部 0」，没有各维度可选。
 * 另：路由不带 ?year= 时原先年度为 null（四张表都缺 year、422），应回退项目 store 的审计年度。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

const { get, route } = vi.hoisted(() => ({
  get: vi.fn(),
  route: {
    params: { projectId: 'p1' } as Record<string, string>,
    query: {} as Record<string, string>,
    path: '/projects/p1/ledger',
  },
}))
vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), resolve: vi.fn(() => ({ href: '' })) }),
}))
vi.mock('@/services/apiProxy', () => {
  const api = { get: (...a: unknown[]) => get(...a), post: vi.fn(), put: vi.fn(), delete: vi.fn() }
  return { api, default: api }
})

import LedgerPenetration from '../LedgerPenetration.vue'
import { useProjectStore } from '@/stores/project'

const SUMMARY = '/api/projects/p1/ledger/aux-balance-summary'
const DIM_TYPES = [
  { type: '成本中心', total_records: 46550, group_count: 24504 },
  { type: '客户', total_records: 30741, group_count: 5298 },
]

function respond(url: string) {
  if (url === '/api/projects') return []
  if (url === '/api/projects/p1/wizard') return { steps: { basic_info: { data: { client_name: '测试客户', audit_year: 2025 } } } }
  if (url === '/api/projects/p1/ledger/years') return { years: [2025], sibling_years: [] }
  if (url === '/api/projects/p1/ledger/balance') {
    return [{ account_code: '1002', account_name: '银行存款', opening_balance: 1, debit_amount: 0, credit_amount: 0, closing_balance: 1 }]
  }
  if (url === SUMMARY) return { dim_types: DIM_TYPES, rows: [], total: 0 }
  if (url === '/api/projects/p1/ledger/aux-balance-paged') {
    return {
      rows: [{ account_code: '1122.01', account_name: '应收账款_应收货款', aux_type: '客户', aux_code: 'C1', aux_name: '某客户', opening_balance: 0, debit_amount: 1, credit_amount: 0, closing_balance: 1 }],
      total: 1, page: 1, page_size: 100,
    }
  }
  if (url === '/api/projects/p1/ledger-import/active-job') return { status: 'idle' }
  return {}
}

let wrapper: VueWrapper | null = null
function mountPage() {
  wrapper = mount(LedgerPenetration, {
    global: {
      plugins: [ElementPlus],
      stubs: {
        LedgerDataManager: true,
        AttachVoucherToWpDialog: true,
        ImportCompletionSummary: true,
        VoucherKeyCandidates: true,
        VoucherLinkTags: true,
        LedgerWindowPager: true,
      },
    },
  })
  return wrapper
}

/** 维度页签的类型名（数字的千分位格式随运行环境区域设置，不比） */
function dimTypeNames(w: VueWrapper): string[] {
  return w.findAll('.gt-dim-tab').map((t) => t.text().replace(/[\d,\s]/g, ''))
}

beforeEach(() => {
  setActivePinia(createPinia())
  route.query = {}
  get.mockReset().mockImplementation(async (url: string) => respond(url))
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
})

describe('LedgerPenetration 辅助余额表从 URL 恢复', () => {
  it('URL 带 balanceTab=aux 挂载（切页签后整页重挂 / F5）：首帧就是辅助余额表，并加载出各维度', async () => {
    route.query = { year: '2025', balanceTab: 'aux' }
    const w = mountPage()
    // 页签在建实例时按 URL 定：不先闪科目余额表
    expect(w.find('.gt-balance-tab--active').text()).toBe('辅助余额表')
    await flushPromises()
    expect(get).toHaveBeenCalledWith(SUMMARY, expect.objectContaining({ params: { year: 2025, dim_type: '__types_only__' } }))
    expect(dimTypeNames(w)).toEqual(['全部', '成本中心', '客户'])
    expect(w.text()).not.toContain('暂无辅助余额数据')
  })

  it('URL 页签是非法值：按科目余额表显示，不取辅助余额', async () => {
    route.query = { year: '2025', balanceTab: 'bogus' }
    const w = mountPage()
    await flushPromises()
    expect(w.find('.gt-balance-tab--active').text()).toBe('科目余额表')
    expect(get.mock.calls.some(([url]) => url === SUMMARY)).toBe(false)
  })
})

describe('LedgerPenetration 年度', () => {
  it('路由不带 ?year=：按项目 store 的审计年度取科目余额表与辅助余额表', async () => {
    useProjectStore().year = 2025
    route.query = { balanceTab: 'aux' }
    mountPage()
    await flushPromises()
    expect(get).toHaveBeenCalledWith('/api/projects/p1/ledger/balance', expect.objectContaining({ params: { year: 2025 } }))
    expect(get).toHaveBeenCalledWith(SUMMARY, expect.objectContaining({ params: { year: 2025, dim_type: '__types_only__' } }))
  })

  it('路由带 ?year= 时以路由为准（看的是哪一年就取哪一年）', async () => {
    useProjectStore().year = 2025
    route.query = { year: '2024' }
    mountPage()
    await flushPromises()
    expect(get).toHaveBeenCalledWith('/api/projects/p1/ledger/balance', expect.objectContaining({ params: { year: 2024 } }))
  })
})
