/**
 * 中栏企业树联动（spec consol-autotree-linkage-closure R1.4~R1.6 / R7.1 / R7.2）
 *
 * - 合并页只保留这一棵树：搜索（名称 / 代码）过滤；合并页广播 consol-current-node 时同步高亮（只认本项目）；
 *   首次加载向合并页要一次当前节点；
 * - 树版本标签；与已记录版本有结构变化时提示（不拦截），「重新推送」交给合并页统一排队；只改名不提示；
 * - 差额户右键菜单只有「📝 差额分录 / 查看调整与抵销」，打开分录面板经 consol-open-elim-panel 交给合并页。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import type { ConsolTreeNode, ConsolTreeResponse } from '@/services/consolidationApi'

const mockGetTree = vi.fn()
vi.mock('@/services/consolidationApi', () => ({
  getWorksheetTree: (...args: any[]) => mockGetTree(...args),
}))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { projectId: 'p-g' }, query: {} }) }))
const handlers = new Map<string, (payload: any) => void>()
const emitted: Array<[string, any]> = []
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: (name: string, payload: any) => emitted.push([name, payload]),
    on: (name: string, fn: any) => handlers.set(name, fn),
    off: (name: string) => handlers.delete(name),
  },
}))

import ConsolMiddleNav from '../ConsolMiddleNav.vue'

function n(key: string, name: string, extra: Partial<ConsolTreeNode> = {}, children: ConsolTreeNode[] = []): ConsolTreeNode {
  const [code, role] = key.split(':') as [string, ConsolTreeNode['role']]
  const kind = extra.kind ?? (role.endsWith('_elim') ? 'elim' : children.length ? 'aggregate' : 'data')
  return {
    project_id: null, company_code: code, company_name: name, parent_company_code: null, ultimate_company_code: null,
    consol_level: 1, children, node_key: key, role, kind, display_name: name, relation: null, host_project_id: null,
    flags: [], via: [], mode: null, ...extra,
  }
}

const TREE = n('G:consol', '某集团（合并户）', { project_id: 'p-g', kind: 'aggregate' }, [
  n('G:consol_elim', '某集团（差额户）'),
  n('G:parent', '某集团（母公司户）', { kind: 'aggregate' }, [
    n('G:branch_elim', '某集团（母分差额户）'),
    n('G:hq', '某集团（本部单体户）', { project_id: 'p-gs' }),
    n('GB:branch', '北京分公司', { project_id: 'p-gb' }),
  ]),
])

const treeApi = { filter: vi.fn(), setCurrentKey: vi.fn() }
const TreeStub = defineComponent({
  props: ['data', 'filterNodeMethod'],
  emits: ['node-click', 'node-contextmenu'],
  setup(props, { slots, emit, expose }) {
    expose(treeApi)
    const render = (nodes: any[]): any[] => nodes.flatMap((d: any) => [
      h('div', {
        class: 'tree-item', 'data-key': d.key,
        onClick: () => emit('node-click', d),
        onContextmenu: (e: MouseEvent) => emit('node-contextmenu', e, d),
      }, slots.default?.({ data: d })),
      ...render(d.children || []),
    ])
    return () => h('div', { class: 'tree' }, render(props.data || []))
  },
})
const pass = (tag: string) => defineComponent({
  inheritAttrs: false,
  setup(_, { slots, attrs }) {
    return () => h(tag, { 'data-testid': (attrs as any)['data-testid'], onClick: (attrs as any).onClick }, slots.default?.())
  },
})
const InputStub = defineComponent({
  props: ['modelValue'],
  emits: ['update:modelValue'],
  setup(_, { attrs }) { return () => h('input', { 'data-testid': (attrs as any)['data-testid'] }) },
})
const STUBS = {
  'el-tree': TreeStub, 'el-button': pass('button'), 'el-tooltip': pass('span'), 'el-tag': pass('span'),
  'el-input': InputStub, 'el-empty': true, 'el-dialog': true, 'el-checkbox': true, teleport: true,
}

function response(scopeVersion: ConsolTreeResponse['scope_version'] = null): ConsolTreeResponse {
  return { tree: TREE, mode: 'mixed', mode_label: '母子合并＋总分汇总', diagnostics: [], year: 2025, scope_version: scopeVersion }
}

const VERSION = {
  revision: 3, latest_revision: 3, mode: 'auto' as const, recorded_at: '2026-10-26T02:00:00Z', matches: false,
  structural_change: true, fingerprint: 'f', can_record: true,
  diff: {
    added: [{ node_key: 'GB:branch', label: '北京分公司' }], removed: [],
    moved: [{ node_key: 'G:hq', label: '某集团', from: 'G:consol', from_label: '某集团', to: 'G:parent', to_label: '某集团' }],
    changed: [], renamed: [], structural: true,
  },
}

async function mounted(res: ConsolTreeResponse) {
  mockGetTree.mockResolvedValue(res)
  const wrapper = mount(ConsolMiddleNav, { global: { stubs: STUBS } })
  await flushPromises()
  return wrapper
}

describe('ConsolMiddleNav 联动', () => {
  beforeEach(() => {
    emitted.length = 0
    handlers.clear()
    mockGetTree.mockReset()
    treeApi.filter.mockClear()
    treeApi.setCurrentKey.mockClear()
  })

  it('树版本标签；结构变化只提示不拦截，「重新推送」交给合并页；只改名称不提示', async () => {
    const wrapper = await mounted(response(VERSION))
    expect(wrapper.find('[data-testid="cm-version"]').text()).toBe('树版本 v3')
    const alert = wrapper.find('[data-testid="cm-tree-changed"]')
    expect(alert.text()).toContain('新增 1 个节点、上级变化 1 个')
    expect(alert.text()).toContain('重新推送后更新已生成的合并报表与附注')
    await wrapper.find('[data-testid="cm-repush"]').trigger('click')
    expect(emitted.some(([name]) => name === 'consol-request-push')).toBe(true)
    // 「树版本」按钮打开企业树版本弹窗（由合并页处理）
    await wrapper.find('[data-testid="cm-scope-confirm"]').trigger('click')
    expect(emitted.at(-1)?.[0]).toBe('consol-open-scope-confirm')

    const renamed = await mounted(response({ ...VERSION, structural_change: false, diff: { ...VERSION.diff, added: [], moved: [], structural: false } }))
    expect(renamed.find('[data-testid="cm-tree-changed"]').exists()).toBe(false)
    const fresh = await mounted(response({ ...VERSION, revision: 0, matches: false, diff: null }))
    expect(fresh.find('[data-testid="cm-version"]').text()).toBe('树版本：尚未记录')
    expect(fresh.find('[data-testid="cm-tree-changed"]').exists()).toBe(false)
  })

  it('合并页广播当前节点 ⇒ 同步高亮（只认本项目）；首次加载向合并页要当前节点；搜索按名称或代码过滤', async () => {
    const wrapper = await mounted(response())
    expect(emitted.some(([name]) => name === 'consol-current-node-request')).toBe(true)
    handlers.get('consol-current-node')!({ projectId: 'other', nodeKey: 'G:hq' })
    await nextTick()
    expect(treeApi.setCurrentKey).not.toHaveBeenCalled()
    handlers.get('consol-current-node')!({ projectId: 'p-g', nodeKey: 'G:hq' })
    await nextTick()
    await nextTick()
    expect(treeApi.setCurrentKey).toHaveBeenLastCalledWith('G:hq')

    wrapper.findComponent(InputStub).vm.$emit('update:modelValue', 'GB')
    await nextTick()
    expect(treeApi.filter).toHaveBeenLastCalledWith('GB')
    const filterNode = wrapper.findComponent(TreeStub).props('filterNodeMethod') as (v: string, d: any) => boolean
    expect(filterNode('北京', { label: '北京分公司', companyCode: 'GB' })).toBe(true)
    expect(filterNode('gb', { label: '北京分公司', companyCode: 'GB' })).toBe(true)
    expect(filterNode('甲', { label: '北京分公司', companyCode: 'GB' })).toBe(false)
    expect(filterNode('', { label: '北京分公司', companyCode: 'GB' })).toBe(true)
  })

  it('差额户右键：只有「差额分录 / 查看调整与抵销」，打开分录面板交给合并页；企业节点右键不出现差额分录', async () => {
    const wrapper = await mounted(response())
    await wrapper.find('[data-key="G:branch_elim"]').trigger('contextmenu')
    await new Promise((r) => setTimeout(r, 0))
    await nextTick()
    const menu = wrapper.find('.cm-context-menu')
    expect(menu.exists()).toBe(true)
    expect(menu.text()).toContain('差额分录')
    expect(menu.text()).not.toContain('直接下级汇总')
    await wrapper.find('[data-testid="cm-ctx-elim-entries"]').trigger('click')
    expect(emitted.at(-1)).toEqual(['consol-open-elim-panel', { nodeKey: 'G:branch_elim' }])

    await wrapper.find('[data-key="G:hq"]').trigger('contextmenu')
    await new Promise((r) => setTimeout(r, 0))
    await nextTick()
    expect(wrapper.find('.cm-context-menu').text()).toContain('直接下级汇总')
    expect(wrapper.find('[data-testid="cm-ctx-elim-entries"]').exists()).toBe(false)
  })
})
