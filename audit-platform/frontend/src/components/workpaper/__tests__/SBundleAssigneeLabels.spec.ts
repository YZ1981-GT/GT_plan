/** P2.3：四个真实 bundle 从索引 API 接收负责人，页签展示姓名或用户名。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { useBundleAssigneeLabels } from '../composables/useBundleAssigneeLabels'
import type { WpIndexItem } from '@/services/workpaperApi'

const { getIndex, get } = vi.hoisted(() => ({ getIndex: vi.fn(), get: vi.fn() }))
vi.mock('@/services/workpaperApi', () => ({ getWpIndex: getIndex }))
vi.mock('@/services/apiProxy', () => ({ api: { get } }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'test-project' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('../GtAProgramConsole.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../GtGridSheet.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../s34-ipo-bundle/GtS34ChecklistOverview.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../s34-ipo-bundle/GtS34SubCheckTable.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../s35-refinance-bundle/GtS35DetailTable.vue', () => ({ default: { template: '<div />' } }))

import S32 from '../s32-fraud-bundle/GtS32Bundle.vue'
import S33 from '../s33-ann14-bundle/GtS33Bundle.vue'
import S34 from '../s34-ipo-bundle/GtS34Bundle.vue'
import S35 from '../s35-refinance-bundle/GtS35Bundle.vue'
import { useS32BundleState } from '../s32-fraud-bundle/useS32BundleState'
import { useS33BundleState } from '../s33-ann14-bundle/useS33BundleState'
import { useS34BundleState } from '../composables/useS34BundleState'
import { useS35BundleState } from '../composables/useS35BundleState'

const cases = [
  { code: 'S32', component: S32, state: useS32BundleState },
  { code: 'S33', component: S33, state: useS33BundleState },
  { code: 'S34', component: S34, state: useS34BundleState },
  { code: 'S35', component: S35, state: useS35BundleState },
]
const wrappers: ReturnType<typeof mount>[] = []
const stubs = {
  'el-tabs': { template: '<div><slot /></div>' },
  'el-tab-pane': {
    props: ['name', 'label'],
    template: '<div class="tab" :data-name="name">{{ label }}<slot /></div>',
  },
  'el-alert': { template: '<div><slot /></div>' },
  'el-result': { template: '<div />' },
  'el-switch': { template: '<span />' },
  'el-icon': { template: '<i />' },
  'el-radio-group': { template: '<div><slot /></div>' },
  'el-radio-button': { template: '<div><slot /></div>' },
}

function item(code: string, assignee_name?: string | null, assigned_to: string | null = 'user-1'): WpIndexItem {
  return { id: `idx-${code}`, wp_id: `wp-${code}`, wp_code: code, wp_name: '测试底稿',
    audit_cycle: 'S', status: 'not_started', assigned_to, assignee_name, reviewer: null }
}

beforeEach(() => {
  getIndex.mockReset()
  get.mockReset()
  get.mockResolvedValue([])
})
afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount())
})

describe.each(cases)('$code 页签负责人', ({ code, component, state }) => {
  it.each(['张审计', 'auditor_fallback'])('展示接口解析的姓名 %s，未分配不展示', async (name) => {
    getIndex.mockResolvedValue([
      item(`${code}-1`, name), item(`${code}-2`, null, null),
    ])
    const wrapper = mount(component, {
      props: { wpId: 'bundle-id' },
      global: { stubs, directives: { loading: {} } },
    })
    wrappers.push(wrapper)
    await flushPromises()
    expect(wrapper.get(`[data-name="${code}-1"]`).text()).toContain(`（负责人：${name}）`)
    expect(wrapper.get(`[data-name="${code}-2"]`).text()).not.toContain('负责人：')
    expect(getIndex).toHaveBeenCalledOnce()
    expect(getIndex).toHaveBeenCalledWith('test-project')
    if (code === 'S34') expect(wrapper.get('[data-name="overview"]').text()).not.toContain('负责人：')
  })

  it('重新加载清除已撤销的分配，失败时不残留旧姓名', async () => {
    const bundle = state({ projectId: ref('test-project') })
    getIndex.mockResolvedValue([item(`${code}-1`, '张审计')])
    await bundle.loadWpIndex()
    expect(bundle.tabLabel('核查', `${code}-1`)).toContain('张审计')
    getIndex.mockResolvedValue([item(`${code}-1`, null, null)])
    await bundle.loadWpIndex()
    expect(bundle.tabLabel('核查', `${code}-1`)).toBe('核查')
    getIndex.mockResolvedValue([item(`${code}-1`, '李审计')])
    await bundle.loadWpIndex()
    getIndex.mockRejectedValue(new Error('加载失败'))
    await bundle.loadWpIndex()
    expect(bundle.tabLabel('核查', `${code}-1`)).toBe('核查')
  })
})

it('不展示无底稿实体、未分配或空白的姓名', () => {
  const labels = useBundleAssigneeLabels()
  labels.setAssignees([
    { ...item('S32-1', '旧姓名'), wp_id: null },
    item('S32-2', '旧姓名', null), item('S32-3', '   '),
  ])
  for (const code of ['S32-1', 'S32-2', 'S32-3']) {
    expect(labels.tabLabel('核查', code)).toBe('核查')
  }
})
