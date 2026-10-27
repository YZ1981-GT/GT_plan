/**
 * 附注编辑路由壳（spec post-push-residual-defect-closure 6.5）：
 * 年度 = 路由 → 项目 store；项目没填审计年度时不挂附注编辑页（它全程按年度取数），只提示。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

const { route } = vi.hoisted(() => ({ route: { params: { projectId: 'p1' }, query: {} as Record<string, string> } }))
vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => ({ back: vi.fn(), push: vi.fn() }) }))
vi.mock('@/services/auditPlatformApi', () => ({ getProject: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn().mockResolvedValue({}) } }))
vi.mock('../DisclosureEditor.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    default: defineComponent({
      name: 'DisclosureEditor',
      props: { auditYear: { type: Number, required: true } },
      setup: (p) => () => h('div', { class: 'editor' }, String(p.auditYear)),
    }),
  }
})

import DisclosureEditorRoute from '../DisclosureEditorRoute.vue'
import { useProjectStore } from '@/stores/project'
import { MISSING_AUDIT_YEAR_MESSAGE } from '@/composables/useProjectAuditYear'

const mountRoute = () => mount(DisclosureEditorRoute, { global: { plugins: [ElementPlus] } })

beforeEach(() => {
  setActivePinia(createPinia())
  route.query = {}
})

describe('DisclosureEditorRoute', () => {
  it('项目没填审计年度：不挂附注编辑页，提示先填年度', () => {
    const w = mountRoute()
    expect(w.find('.editor').exists()).toBe(false)
    expect(w.text()).toContain(MISSING_AUDIT_YEAR_MESSAGE)
  })

  it('项目 store 有年度：挂编辑页并传年度', () => {
    useProjectStore().year = 2025
    const w = mountRoute()
    expect(w.find('.editor').text()).toBe('2025')
  })

  it('路由显式年度优先于 store', () => {
    useProjectStore().year = 2025
    route.query = { year: '2024' }
    const w = mountRoute()
    expect(w.find('.editor').text()).toBe('2024')
  })

  it('年度变成 null（离开项目）：直接卸载编辑页，不把 null 传进去', async () => {
    const store = useProjectStore()
    store.year = 2025
    const w = mountRoute()
    expect(w.find('.editor').exists()).toBe(true)
    store.year = null
    await w.vm.$nextTick()
    expect(w.find('.editor').exists()).toBe(false)
  })
})
