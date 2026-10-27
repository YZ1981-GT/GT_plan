/**
 * 证据链治理中心的审计年度（spec post-push-residual-defect-closure 6.5.4 补测）。
 *
 * 8 个治理页都按项目审计年度取数。项目 store 年度原先初值去年 ⇒ 没填年度的项目照样按去年加载治理页。
 * 现在：年度为空整页提示「未设置审计年度」、一个治理页都不挂；有年度才挂，并随 store 年度变化。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

vi.mock('vue-router', () => ({ useRoute: () => ({ params: { projectId: 'p1' }, query: {} }) }))
vi.mock('@/stores/roleContext', () => ({
  useRoleContextStore: () => ({ currentProjectRole: { role: 'manager' }, effectiveRole: 'manager', loadProjectRole: vi.fn() }),
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { role: 'manager' } }) }))
// 项目 store 用真的（年度初值、可空）；它的取数依赖打桩，本用例不触发取数
vi.mock('@/services/auditPlatformApi', () => ({ getProject: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn().mockResolvedValue({}) } }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { emit: vi.fn(), on: vi.fn(), off: vi.fn() } }))

import EvidenceGovernanceCenter from '../EvidenceGovernanceCenter.vue'
import { useProjectStore } from '@/stores/project'
import { MISSING_AUDIT_YEAR_MESSAGE } from '@/composables/useProjectAuditYear'

const tab = (cls: string, props = ['projectId', 'year']) => ({
  props,
  template: `<div class="${cls}">{{ projectId }}-{{ year }}</div>`,
})
const STUBS = {
  EvidenceRefsTab: tab('stub-refs'),
  OcrGovernanceTab: tab('stub-ocr', ['projectId', 'year', 'role']),
  CitationTab: tab('stub-citation'),
  AiGateTab: tab('stub-ai', ['projectId', 'year', 'role']),
  ReviewEvidenceTab: tab('stub-review'),
  ArchiveManifestTab: tab('stub-archive'),
  LegalHoldTab: tab('stub-hold'),
  MetricsTab: { template: '<div class="stub-metrics" />' },
  EvidenceGovernanceHandbookDialog: true,
}

const mountCenter = () => mount(EvidenceGovernanceCenter, { global: { plugins: [ElementPlus], stubs: STUBS } })
/** 页头的「XXXX 年度」标签 */
const yearTags = (w: ReturnType<typeof mountCenter>) =>
  w.findAll('.header-meta .el-tag').map((t) => t.text()).filter((t) => t.endsWith('年度'))

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('证据链治理中心的审计年度', () => {
  it('项目没填审计年度：整页提示，不挂任何治理页、不显示年度标签', () => {
    expect(useProjectStore().year).toBeNull()
    const w = mountCenter()
    expect(w.find('.el-empty').exists()).toBe(true)
    expect(w.find('.el-empty').text()).toContain(MISSING_AUDIT_YEAR_MESSAGE)
    expect(w.find('.gov-tabs').exists()).toBe(false)
    expect(w.find('.stub-refs').exists()).toBe(false)
    expect(yearTags(w)).toEqual([])
  })

  it('有审计年度：挂治理页并传入该年度，页头显示年度', () => {
    useProjectStore().year = 2025
    const w = mountCenter()
    expect(w.find('.el-empty').exists()).toBe(false)
    expect(w.find('.gov-tabs').exists()).toBe(true)
    expect(w.find('.stub-refs').text()).toBe('p1-2025')
    expect(yearTags(w)).toEqual(['2025 年度'])
  })

  it('年度跟着 store 走：定下年度后挂上治理页；切到没填年度的项目又整页提示', async () => {
    const store = useProjectStore()
    const w = mountCenter()
    expect(w.find('.stub-refs').exists()).toBe(false)
    store.year = 2024
    await nextTick()
    expect(w.find('.stub-refs').text()).toBe('p1-2024')
    expect(w.find('.el-empty').exists()).toBe(false)
    store.year = null
    await nextTick()
    expect(w.find('.stub-refs').exists()).toBe(false)
    expect(w.find('.el-empty').text()).toContain(MISSING_AUDIT_YEAR_MESSAGE)
    expect(yearTags(w)).toEqual([])
  })
})
