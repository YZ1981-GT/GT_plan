/**
 * 质控组别读者挂载测试：A1-11 签发表 / A17-1 签字栏 / A21~A25 复核清单 / A17 合集提示
 * （spec trim-followup-residual-findings-closure R3）。
 *
 * 原状（可打红）：A1-11 签发表按表里存的原值判（旧版按分类原值预填过 A1 ⇒ 6 个槽位全「不适用」、已签 0/0）；
 * A17-1 签字栏、复核清单标签、A17 合集提示按 business_category 首字母（旧场景值 IPO 判成「I 类」）。
 * 现：表里存的码先 categoryGroupOfCode 归组；其余读后端下发的 project_classification（不回退读分类原值）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, shallowMount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import type { ProjectClassification } from '@/types/projectClassification'

const hoisted = vi.hoisted(() => ({
  routes: [] as Array<[string, unknown]>,
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
}))
vi.mock('@/services/apiProxy', () => ({ api: { get: hoisted.get, post: hoisted.post, put: hoisted.put } }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: {}, query: {} }), useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/composables/useProjectRole', async () => {
  const { ref } = await import('vue')
  return { useProjectRole: () => ({ projectRole: ref(null), permissions: ref([]) }) }
})
vi.mock('@/services/workpaperApi', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  getWpIndex: vi.fn().mockResolvedValue([]),
}))
// jsdom 没有 IntersectionObserver（A17-1 左侧导航 scrollspy 用）
vi.stubGlobal('IntersectionObserver', vi.fn().mockImplementation(() => ({
  observe: vi.fn(), unobserve: vi.fn(), disconnect: vi.fn(),
})))
vi.mock('../sync/workpaperSyncApi', () => ({ readStoreProjection: vi.fn() }))
vi.mock('../sync/workpaperSyncCapability', () => ({ capabilityForEntry: () => 'bidirectional' }))
vi.mock('../sync/useWorkpaperSyncBridge', async () => {
  const { ref } = await import('vue')
  return {
    WP_BRIDGE_IN_FLIGHT_STATES: [],
    useWorkpaperSyncBridge: () => ({
      mode: ref('html'), state: ref('html_idle'), descriptor: ref(null), dirty: ref(false), canForcesave: ref(false),
      persistMode: vi.fn(), switchToOnlyOffice: vi.fn(), leaveWithoutSaving: vi.fn(), reloadAfterApplied: vi.fn(),
    }),
  }
})

import GtA111SigningForm from '../GtA111SigningForm.vue'
import GtA171AuditSummary from '../GtA171AuditSummary.vue'
import GtReviewChecklist from '../GtReviewChecklist.vue'
import GtA17Bundle from '../GtA17Bundle.vue'

function pc(code: string | null, group: 'A' | 'B' | 'C', defaulted = false): ProjectClassification {
  return {
    category_code: code, category_group: group, defaulted, scenario: 'normal', scenario_label: '常规年审',
    is_ipo: false, is_refinancing: false, is_capital_market: false, tags: [],
  }
}

/** 按 URL 子串回包（`=` 开头按整串精确匹配）；没登记的返回空对象 */
function route(fragment: string, body: unknown) {
  hoisted.routes.push([fragment, body])
}

beforeEach(() => {
  hoisted.routes = []
  hoisted.get.mockReset()
  hoisted.get.mockImplementation(async (url: string) => {
    const hit = hoisted.routes.find(([f]) => (f.startsWith('=') ? url === f.slice(1) : url.includes(f)))
    return hit ? hit[1] : {}
  })
  hoisted.post.mockReset()
  hoisted.post.mockResolvedValue({})
  hoisted.put.mockReset()
  hoisted.put.mockResolvedValue({})
})

describe('A1-11 签发表（GtA111SigningForm）：表里存的码先归组别', () => {
  const ROLES = ['项目负责经理', '项目合伙人', '质量控制复核合伙人', '技术复核人(EQCR)', 'IT专家', '税务专家']

  async function mountForm(stored: string | null) {
    route('/checklist-responses', stored === null ? [] : [
      { item_id: 'A1-11-biz-category', conclusion: stored, remark: null, wp_ref: null },
    ])
    const wrapper = mount(GtA111SigningForm, {
      props: { wpId: 'wp-a111', projectId: 'p-a111', wpCode: 'A1-11', year: 2025 },
      global: { plugins: [ElementPlus, createPinia()] },
    })
    await flushPromises()
    return wrapper
  }

  /** 签字流转区（第一张签字表；报告管理 / 修改签字是后面几张） */
  function slotRows(wrapper: Awaited<ReturnType<typeof mountForm>>) {
    return wrapper.findAll('.a111-sign-table')[0].findAll('.a111-sign-row')
  }

  function naRoles(wrapper: Awaited<ReturnType<typeof mountForm>>) {
    return slotRows(wrapper)
      .filter((row) => row.classes().includes('a111-sign-row--na'))
      .map((row) => row.find('.a111-sign-col--role').text())
  }

  it.each([
    ['A1', ['IT专家', '税务专家'], '已签 0/4'], // 旧版按分类原值预填的细分类码
    ['A', ['IT专家', '税务专家'], '已签 0/4'],
    ['B3', ['质量控制复核合伙人', '技术复核人(EQCR)', 'IT专家', '税务专家'], '已签 0/2'],
    [null, [], '已签 0/0'], // 没选分类：不判不适用
  ] as const)('存的是 %s', async (stored, na, progressText) => {
    const wrapper = await mountForm(stored)
    expect(slotRows(wrapper).map((row) => row.find('.a111-sign-col--role').text())).toEqual(ROLES)
    expect(naRoles(wrapper)).toEqual(na)
    expect(wrapper.find('.a111-progress-text').text()).toBe(progressText)
  })
})

describe('A17-1 签字栏（GtA171AuditSummary）：按 project_context.project_classification 组别', () => {
  const ALL = ['编制人（项目现场负责人）', '复核人（项目合伙人）', '质量控制复核合伙人', 'EQCR技术复核人']

  async function roles(projectContext: Record<string, unknown>) {
    const wrapper = shallowMount(GtA171AuditSummary, {
      props: { wpId: 'wp-a171', projectId: 'p-a171', htmlData: { project_context: projectContext } as any },
      global: { plugins: [ElementPlus], renderStubDefaultSlot: true },
    })
    await flushPromises()
    return wrapper.findAll('.gt-a171__sig-role').map((node) => node.text())
  }

  it.each([
    [pc('A1', 'A'), ALL],
    [pc('B', 'B'), [ALL[0], ALL[1], ALL[3]]],
    [pc(null, 'C', true), ALL.slice(0, 2)],
  ])('%j', async (classification, expected) => {
    expect(await roles({ client_name: '客户', project_classification: classification })).toEqual(expected)
  })

  it('只有分类原值、没有 project_classification：不按首字母当 A 类', async () => {
    expect(await roles({ client_name: '客户', business_category: 'A1' })).toEqual(ALL.slice(0, 2))
  })
})

describe('A21~A25 复核清单（GtReviewChecklist）：分类标签读复核上下文的 project_classification', () => {
  async function label(context: Record<string, unknown>) {
    route('/a21/review-definitions', {
      template: { wp_code: 'A21', role_label: '项目经理复核', audit_type_label: '财报审计', items: [] },
      context,
    })
    route('/checklist-responses', [])
    route('/a21/applicable-review-templates', [])
    route('/a21/prefill-suggestions', { hints: [] })
    const wrapper = shallowMount(GtReviewChecklist, {
      props: { projectId: 'p-a21', wpId: 'wp-a21', wpCode: 'A21' },
      global: { plugins: [ElementPlus], renderStubDefaultSlot: true },
    })
    await flushPromises()
    return (wrapper.vm as any).categoryLabel as string
  }

  it.each([
    [{ business_category: 'A1', project_classification: pc('A1', 'A') }, 'A 类（A1）'],
    [{ business_category: 'B', project_classification: pc('B', 'B') }, 'B 类'],
    [{ business_category: 'C', project_classification: pc(null, 'C', true) }, 'C 类（分类未填写）'], // 原：旧值 IPO 显示「I类」
    [{ business_category: 'IPO' }, ''], // 没有分类解释不猜
  ])('%j → 「%s」', async (context, text) => {
    expect(await label(context)).toBe(text)
  })
})

describe('A17 合集（GtA17Bundle）：B / C 类软提示读项目详情的 project_classification', () => {
  async function warning(project: Record<string, unknown>) {
    route('=/api/projects/p-a17', project)
    const wrapper = shallowMount(GtA17Bundle, {
      props: { wpId: 'wp-a17', projectId: 'p-a17' },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    return (wrapper.vm as any).categorySoftWarning as string
  }

  it.each([
    [{ business_category: 'A1', project_classification: pc('A1', 'A') }, ''],
    [{ business_category: 'B2', project_classification: pc('B2', 'B') }, '当前项目为 B 类（B2）：A17 非默认必备'],
    [{ business_category: 'IPO', project_classification: pc(null, 'C', true) }, '当前项目为 C 类（分类未填写）：A17 默认不适用'],
    [{ business_category: 'C' }, ''], // 没有分类解释不猜
  ])('%j', async (project, prefix) => {
    const text = await warning(project)
    if (prefix) expect(text.startsWith(prefix)).toBe(true)
    else expect(text).toBe('')
  })
})
