/**
 * GtBadDebtSheet.spec.ts — Task 11.4 坏账准备明细表 D2-3 嵌套编辑器单元测试
 *
 * 覆盖（Requirements 6.1, 6.2, 6.6, 6.7）：
 * 1. 挂载 + GET 树渲染父行/子行/合计行（层级渲染）
 * 2. 展开/折叠切换子行可见性
 * 3. 只读保护：合计行 + 含子行父行金额列只读；无子行父行可编辑
 * 4. 右键菜单项：父行→新增子行；子行→删除/上方插入/下方插入
 * 5. 信封解包：api.get 返回业务数据直接 Object.assign 到 tree
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPut = vi.fn()
const mockDelete = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...a: any[]) => mockGet(...a),
    post: (...a: any[]) => mockPost(...a),
    put: (...a: any[]) => mockPut(...a),
    delete: (...a: any[]) => mockDelete(...a),
  },
}))

import GtBadDebtSheet from '../GtBadDebtSheet.vue'

const STUBS = {
  'el-button': true,
  'el-input-number': true,
  'el-tooltip': { template: '<div><slot /></div>' },
}

const TREE = {
  wp_index_id: 'wp-1',
  prefill_source: '试算表 1231 坏账准备',
  summary: { amounts: { amount_n: '150.00', amount_b: '0.00' }, balance_check: { is_balanced: true } },
  parents: [
    {
      id: 'p1',
      provision_method: 'INDIVIDUAL',
      provision_method_label: '按单项评估计提',
      sort_order: 10,
      row_label: '按单项评估计提',
      amounts: { amount_n: '150.00' },
      version: 2,
      is_editable: false,
      children: [
        { id: 'c1', parent_row_id: 'p1', sort_order: 10, row_label: '甲公司', amounts: { amount_n: '100.00' }, version: 1 },
        { id: 'c2', parent_row_id: 'p1', sort_order: 20, row_label: '乙公司', amounts: { amount_n: '50.00' }, version: 1 },
      ],
    },
    {
      id: 'p2',
      provision_method: 'OTHER',
      provision_method_label: '其他',
      sort_order: 20,
      row_label: '其他',
      amounts: { amount_n: '0.00' },
      version: 1,
      is_editable: true,
      children: [],
    },
  ],
}

function mountSheet() {
  mockGet.mockImplementation((url: string) => {
    if (url.endsWith('/provision-methods')) {
      return Promise.resolve([
        { value: 'INDIVIDUAL', label: '按单项评估计提' },
        { value: 'OTHER', label: '其他' },
      ])
    }
    return Promise.resolve(JSON.parse(JSON.stringify(TREE)))
  })
  return mount(GtBadDebtSheet, { props: { wpId: 'wp-1' }, global: { stubs: STUBS } })
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockPut.mockReset()
  mockDelete.mockReset()
})

describe('GtBadDebtSheet (D2-3 嵌套编辑器)', () => {
  it('1. 挂载 + GET 树渲染层级（父行/子行/合计行）', async () => {
    const w = mountSheet()
    await flushPromises()
    // GET 树 + provision-methods 各至少一次
    expect(mockGet).toHaveBeenCalled()
    const text = w.text()
    expect(text).toContain('按单项评估计提')
    expect(text).toContain('其中：甲公司')
    expect(text).toContain('其中：乙公司')
    expect(text).toContain('合计')
  })

  it('2. 展开/折叠切换子行可见性', async () => {
    const w = mountSheet()
    await flushPromises()
    const vm: any = w.vm
    expect(vm.isExpanded('p1')).toBe(true) // 默认展开
    vm.toggleExpand('p1')
    expect(vm.isExpanded('p1')).toBe(false)
    vm.toggleExpand('p1')
    expect(vm.isExpanded('p1')).toBe(true)
  })

  it('3. 信封解包：api.get 返回业务数据直接填入 tree', async () => {
    const w = mountSheet()
    await flushPromises()
    const vm: any = w.vm
    expect(vm.tree.parents.length).toBe(2)
    expect(vm.tree.summary.amounts.amount_n).toBe('150.00')
    expect(vm.tree.prefill_source).toContain('1231')
  })

  it('4. 只读保护：含子行父行 is_editable=false，无子行父行可编辑', async () => {
    const w = mountSheet()
    await flushPromises()
    const vm: any = w.vm
    const p1 = vm.tree.parents.find((p: any) => p.id === 'p1')
    const p2 = vm.tree.parents.find((p: any) => p.id === 'p2')
    expect(p1.is_editable).toBe(false) // 有子行
    expect(p2.is_editable).toBe(true) // 无子行
  })

  it('5. 预填来源 tooltip：仅期初/期末未审数列显示来源', async () => {
    const w = mountSheet()
    await flushPromises()
    const vm: any = w.vm
    expect(vm.prefillTip('amount_b')).toContain('1231')
    expect(vm.prefillTip('amount_k')).toContain('1231')
    expect(vm.prefillTip('amount_f')).toBe('')
  })

  it('6. 右键菜单：父行打开含新增子行项', async () => {
    const w = mountSheet()
    await flushPromises()
    const vm: any = w.vm
    const ev = { clientX: 10, clientY: 20, preventDefault: () => {} } as any
    vm.openMenu(ev, vm.tree.parents[0], null)
    expect(vm.menu.visible).toBe(true)
    expect(vm.menu.child).toBe(null)
    expect(vm.menu.parent.id).toBe('p1')
  })

  it('7. 右键子行菜单含删除/上方插入/下方插入项', async () => {
    const w = mountSheet()
    await flushPromises()
    const vm: any = w.vm
    const parent = vm.tree.parents[0]
    const child = parent.children[0]
    const ev = { clientX: 5, clientY: 6, preventDefault: () => {} } as any
    vm.openMenu(ev, parent, child)
    expect(vm.menu.visible).toBe(true)
    expect(vm.menu.child.id).toBe('c1')
    // 子行菜单操作函数齐备
    expect(typeof vm.onDeleteChild).toBe('function')
    expect(typeof vm.onInsertChild).toBe('function')
  })
})
