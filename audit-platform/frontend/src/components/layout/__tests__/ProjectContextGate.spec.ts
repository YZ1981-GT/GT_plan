/**
 * 项目页挂载闸门（spec post-push-residual-defect-closure 6.5.2）：
 * 换项目后年度定下来之前不渲染页面；取失败给重试，不当成「没填年度」。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

const route = reactive<{ params: Record<string, string> }>({ params: {} })
vi.mock('vue-router', () => ({ useRoute: () => route }))
vi.mock('@/services/auditPlatformApi', () => ({ getProject: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn().mockResolvedValue({}) } }))

import ProjectContextGate from '../ProjectContextGate.vue'
import { useProjectStore } from '@/stores/project'

function mountGate() {
  return mount(ProjectContextGate, {
    slots: { default: '<div class="page">页面</div>' },
    global: { plugins: [ElementPlus] },
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
  route.params = { projectId: 'p1' }
})

describe('ProjectContextGate', () => {
  it('年度已定（ready）：渲染页面', () => {
    useProjectStore().yearStatus = 'ready'
    const w = mountGate()
    expect(w.find('.page').exists()).toBe(true)
  })

  it('读取中（loading）：不渲染页面，显示读取中', () => {
    useProjectStore().yearStatus = 'loading'
    const w = mountGate()
    expect(w.find('.page').exists()).toBe(false)
    expect(w.text()).toContain('正在读取项目信息')
  })

  it('取失败（failed）：不渲染页面、不说「未设置审计年度」，点重试调 retryProjectContext', async () => {
    const store = useProjectStore()
    store.yearStatus = 'failed'
    const retry = vi.spyOn(store, 'retryProjectContext').mockResolvedValue(undefined)
    const w = mountGate()
    expect(w.find('.page').exists()).toBe(false)
    expect(w.text()).toContain('读取项目信息失败')
    expect(w.text()).not.toContain('未设置审计年度')
    await w.find('button').trigger('click')
    expect(retry).toHaveBeenCalledTimes(1)
  })

  it('年度定下来后自动放行页面', async () => {
    const store = useProjectStore()
    store.yearStatus = 'loading'
    const w = mountGate()
    expect(w.find('.page').exists()).toBe(false)
    store.yearStatus = 'ready'
    await w.vm.$nextTick()
    expect(w.find('.page').exists()).toBe(true)
  })

  it('非项目页不受状态影响', () => {
    route.params = {}
    useProjectStore().yearStatus = 'loading'
    const w = mountGate()
    expect(w.find('.page').exists()).toBe(true)
  })
})
