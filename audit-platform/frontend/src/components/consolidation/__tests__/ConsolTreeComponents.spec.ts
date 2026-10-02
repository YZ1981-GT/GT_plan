/**
 * 合并页企业树组件（spec consol-tree-three-code-autobuild 任务 10.7 / 需求 9.1 / 9.2）
 *
 * - OrgNode：以 node_key 作键与选中态（同一企业的合并户与母公司户各自独立）、展示名带角色后缀、
 *   关系标签、「进入项目」只对有项目的节点；
 * - ConsolMiddleNav：只渲染后端树（不再自造「差额表」节点、没有「添加」「同步」入口）；
 *   点击节点经事件总线发出 nodeKey / role / kind。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import type { ConsolTreeNode, ConsolTreeResponse } from '@/services/consolidationApi'

const mockGetTree = vi.fn()
vi.mock('@/services/consolidationApi', () => ({
  getWorksheetTree: (...args: any[]) => mockGetTree(...args),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'p-g' }, query: {} }),
}))
const emitted: Array<[string, any]> = []
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: (name: string, payload: any) => emitted.push([name, payload]),
    on: vi.fn(),
    off: vi.fn(),
  },
}))

import OrgNode from '../OrgNode.vue'
import ConsolMiddleNav from '../ConsolMiddleNav.vue'

function n(key: string, name: string, extra: Partial<ConsolTreeNode> = {}, children: ConsolTreeNode[] = []): ConsolTreeNode {
  const [code, role] = key.split(':') as [string, ConsolTreeNode['role']]
  const kind = extra.kind ?? (role.endsWith('_elim') ? 'elim' : children.length ? 'aggregate' : 'data')
  return {
    project_id: null, company_code: code, company_name: name.replace(/（.*）$/, ''), parent_company_code: null,
    ultimate_company_code: null, consol_level: 1, children, node_key: key, role, kind, display_name: name,
    relation: null, host_project_id: null, flags: [], via: [], mode: null, ...extra,
  }
}

const TREE = n('G:consol', '某集团（合并）', { project_id: 'p-g', kind: 'aggregate', mode: 'mixed' }, [
  n('G:consol_elim', '某集团（合并差额）', { host_project_id: 'p-g' }),
  n('G:parent', '某集团（母公司）', { kind: 'aggregate' }, [
    n('G:branch_elim', '某集团（母分差额）', { host_project_id: 'p-g' }),
    n('G:hq', '某集团（本部）', { project_id: 'p-gs' }),
    n('GB:branch', '北京分公司', { project_id: 'p-gb', relation: 'branch' }),
  ]),
  n('A:subsidiary', '甲公司', { project_id: 'p-a', relation: 'subsidiary', flags: ['relation_defaulted'] }),
])

const passthrough = (tag: string, cls = '') => defineComponent({
  inheritAttrs: false,
  setup(_, { slots, attrs }) {
    return () => h(tag, { class: cls, 'data-testid': (attrs as any)['data-testid'] }, slots.default?.())
  },
})

const OrgStubs = {
  'el-tag': passthrough('span', 'tag'),
  'el-tooltip': passthrough('span'),
  'el-link': defineComponent({
    emits: ['click'],
    setup(_, { slots, emit }) {
      return () => h('a', { class: 'enter', onClick: (e: Event) => emit('click', e) }, slots.default?.())
    },
  }),
}

describe('OrgNode', () => {
  it('节点键与选中态用 node_key；展示名带角色后缀；进入项目只对有项目的节点', async () => {
    const wrapper = mount(OrgNode, {
      props: { node: TREE, depth: 0, selectedKey: 'G:parent' },
      global: { stubs: OrgStubs },
    })
    const cards = wrapper.findAll('.org-card')
    expect(cards.map((c) => c.attributes('data-node-key'))).toEqual([
      'G:consol', 'G:consol_elim', 'G:parent', 'G:branch_elim', 'G:hq', 'GB:branch', 'A:subsidiary',
    ])
    const byKey = (k: string) => cards.find((c) => c.attributes('data-node-key') === k)!
    // 同一企业 G 的五个节点里只有母公司户被选中（旧实现按企业代码选中会点亮全部 G 节点）
    expect(cards.filter((c) => c.classes('org-card--selected')).map((c) => c.attributes('data-node-key'))).toEqual(['G:parent'])
    expect(byKey('G:consol_elim').text()).toContain('某集团（合并差额）')
    expect(byKey('G:consol_elim').classes()).toContain('org-card--elim')
    expect(byKey('G:consol_elim').find('.enter').exists()).toBe(false)
    expect(byKey('G:parent').find('.enter').exists()).toBe(false)
    expect(byKey('G:hq').find('.enter').exists()).toBe(true)
    expect(byKey('GB:branch').text()).toContain('分公司')
    expect(byKey('A:subsidiary').text()).toContain('关系未填')

    await byKey('G:hq').find('.enter').trigger('click')
    const enter = wrapper.emitted('enter-project')!
    expect(enter[0][0].node_key).toBe('G:hq')
    await byKey('G:branch_elim').trigger('click')
    const selects = wrapper.emitted('select')!
    expect(selects[selects.length - 1][0].node_key).toBe('G:branch_elim')
  })
})

const TreeStub = defineComponent({
  name: 'ElTreeStub',
  props: ['data'],
  emits: ['node-click', 'node-contextmenu'],
  setup(props, { slots, emit }) {
    const render = (nodes: any[]): any[] => nodes.flatMap((d: any) => [
      h('div', { class: 'tree-item', 'data-key': d.key, onClick: () => emit('node-click', d) }, slots.default?.({ data: d })),
      ...render(d.children || []),
    ])
    return () => h('div', { class: 'tree' }, render(props.data || []))
  },
})

const NavStubs = {
  'el-tree': TreeStub,
  'el-button': passthrough('button', 'btn'),
  'el-tooltip': passthrough('span'),
  'el-tag': passthrough('span', 'tag'),
  'el-empty': defineComponent({ props: ['description'], setup: (p) => () => h('div', { class: 'empty' }, p.description) }),
  'el-dialog': true,
  'el-checkbox': true,
  Teleport: true,
  Transition: true,
}

describe('ConsolMiddleNav', () => {
  beforeEach(() => {
    emitted.length = 0
    mockGetTree.mockReset()
  })

  it('只渲染后端企业树：键为 node_key，没有自造差额表节点与添加/同步入口；显示合并方式', async () => {
    const res: ConsolTreeResponse = { tree: TREE, mode: 'mixed', mode_label: '母子合并＋总分汇总', diagnostics: [], year: 2025 }
    mockGetTree.mockResolvedValue(res)
    const wrapper = mount(ConsolMiddleNav, { global: { stubs: NavStubs } })
    await flushPromises()

    expect(mockGetTree).toHaveBeenCalledWith('p-g')
    const keys = wrapper.findAll('.tree-item').map((x) => x.attributes('data-key'))
    expect(keys).toEqual(['G:consol', 'G:consol_elim', 'G:parent', 'G:branch_elim', 'G:hq', 'GB:branch', 'A:subsidiary'])
    expect(wrapper.text()).not.toContain('差额表')
    expect(wrapper.text()).not.toContain('添加')
    expect(wrapper.text()).not.toContain('同步')
    expect(wrapper.find('[data-testid="cm-mode"]').text()).toBe('合并方式：母子合并＋总分汇总')

    await wrapper.find('[data-key="G:branch_elim"]').trigger('click')
    expect(emitted.at(-1)).toEqual(['consol-tree-select', {
      companyCode: 'G', label: '某集团（母分差额）', nodeKey: 'G:branch_elim', role: 'branch_elim', kind: 'elim',
    }])
  })

  it('项目不存在 / 取数失败给中文提示，不再从合并范围或基本信息表拼树', async () => {
    mockGetTree.mockResolvedValueOnce({ tree: null, mode: null, mode_label: null, diagnostics: [], year: null, message: '项目不存在或已删除' })
    const w1 = mount(ConsolMiddleNav, { global: { stubs: NavStubs } })
    await flushPromises()
    expect(w1.find('.empty').text()).toBe('项目不存在或已删除')
    expect(w1.findAll('.tree-item')).toHaveLength(0)

    mockGetTree.mockRejectedValueOnce(new Error('boom'))
    const w2 = mount(ConsolMiddleNav, { global: { stubs: NavStubs } })
    await flushPromises()
    expect(w2.find('.empty').text()).toBe('加载企业树失败，请稍后重试')
  })
})
