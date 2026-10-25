/**
 * advancedQueryFrontend.spec.ts — advanced-query-module Task 18.6（前端 Vitest 单元测试）
 *
 * Validates: Requirements 2.3, 4.3, 11.6
 *
 * 覆盖三块：
 *  1. R2.3 — CustomQueryFieldPicker 复用 useAcnr 的 buildAddressTree / loadCellNodes
 *            构建选字段树（不自建下拉）。
 *  2. R4.3 — 结果列以 GtIndexChip（prop 名 `value`）渲染可下钻单元格，点击经
 *            useAcnrDrill → useAcnr.resolveIndex 拿 jump_route 跳转（不自拼路由）。
 *  3. R11.6 — 角色不满足时，高级构建器入口显示为禁用（可见不可点）并给出原因提示。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, shallowMount, flushPromises } from '@vue/test-utils'

// ─── 统一 mock：ACNR SDK（buildAddressTree / loadCellNodes / resolveIndex / clearCache） ───
const acnrMocks = vi.hoisted(() => ({
  buildAddressTree: vi.fn(),
  loadCellNodes: vi.fn(),
  resolveIndex: vi.fn(),
  clearCache: vi.fn(),
}))
vi.mock('@/services/acnr/useAcnr', () => ({
  useAcnr: () => acnrMocks,
}))

// http（useAcnrDrill 用 http.get 调 resolve-instance）
const httpMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: httpMocks }))

// eventBus（CustomQueryFieldPicker onMounted 订阅 template-applied）
vi.mock('@/utils/eventBus', () => ({
  eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() },
}))

// element-plus：保留真实组件，仅替换 ElMessage / ElMessageBox 为 spy
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return {
    ...actual,
    ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
    ElMessageBox: { confirm: vi.fn(), alert: vi.fn(), prompt: vi.fn() },
  }
})

// usePermissionMatrix：可变角色（R11.6）——用普通 holder，setup 时读取当前值
const roleHolder = vi.hoisted(() => ({ value: 'auditor' }))
vi.mock('@/composables/usePermissionMatrix', () => ({
  usePermissionMatrix: () => ({ currentRole: { value: roleHolder.value } }),
}))

// apiProxy（CustomQueryTab onMounted 拉指标库/项目列表）
const apiMocks = vi.hoisted(() => ({
  get: vi.fn().mockResolvedValue([]),
  post: vi.fn().mockResolvedValue({}),
  delete: vi.fn().mockResolvedValue({}),
}))
vi.mock('@/services/apiProxy', () => ({ default: apiMocks, api: apiMocks }))

import CustomQueryFieldPicker from '../CustomQueryFieldPicker.vue'
import {
  normalizeColumns,
  cellAddrId,
  addrIdToIndexRef,
  useAcnrDrill,
} from '@/composables/useAcnrDrill'

// ─── el-tree 桩：暴露 :load 供测试驱动懒加载 ─────────────────────────────────────
const ElTreeStub = {
  name: 'ElTreeStub',
  props: ['load', 'props', 'nodeKey', 'lazy'],
  template: '<div class="el-tree-stub"></div>',
}

function driveLoad(loadFn: (node: any, resolve: (d: any) => void) => void, node: any): Promise<any> {
  return new Promise((resolve) => {
    loadFn(node, (data: any) => resolve(data))
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  acnrMocks.buildAddressTree.mockReset()
  acnrMocks.loadCellNodes.mockReset()
  acnrMocks.resolveIndex.mockReset()
  apiMocks.get.mockResolvedValue([])
})

// ════════════════════════════════════════════════════════════════════════════
// R2.3 — 字段树复用 useAcnr
// ════════════════════════════════════════════════════════════════════════════
describe('CustomQueryFieldPicker — 复用 useAcnr 构建选字段树 (R2.3)', () => {
  const sheetEntry = {
    addr_id: 'D2/D2-2',
    parent_wp_code: 'D2',
    sheet_code: 'D2-2',
    sheet_name: '明细表D2-2',
    domain: 'wp',
    cycle: 'D',
  }
  const cellEntry = {
    addr_id: 'D2/D2-2/E100',
    parent_addr_id: 'D2/D2-2',
    domain: 'wp',
    cell_address: 'E100',
    semantic_label: '期末余额',
    formula_ref: "WP('D2','明细表D2-2','E100')",
  }

  function mountPicker() {
    return mount(CustomQueryFieldPicker, {
      global: {
        stubs: {
          'el-tree': ElTreeStub,
          'el-select': true,
          'el-option': true,
          'el-empty': true,
          'el-button': true,
          'el-icon': true,
          'el-tag': true,
        },
        directives: { loading: {} },
      },
    })
  }

  it('根节点加载调用 useAcnr.buildAddressTree（不自建下拉）', async () => {
    acnrMocks.buildAddressTree.mockResolvedValue([
      {
        label: 'D2',
        value: 'D2',
        addrId: 'D2',
        type: 'sheet',
        children: [
          { label: '明细表D2-2', value: 'D2/D2-2', addrId: 'D2/D2-2', type: 'sheet', meta: sheetEntry },
        ],
      },
    ])
    const wrapper = mountPicker()
    const tree = wrapper.findComponent(ElTreeStub)
    const load = tree.props('load') as any

    const groups = await driveLoad(load, { level: 0 })
    await flushPromises()

    expect(acnrMocks.buildAddressTree).toHaveBeenCalledTimes(1)
    expect(groups).toHaveLength(1)
    expect(groups[0].nodeType).toBe('group')
  })

  it('展开 sheet 节点调用 useAcnr.loadCellNodes 懒加载单元格', async () => {
    acnrMocks.buildAddressTree.mockResolvedValue([
      {
        label: 'D2',
        value: 'D2',
        addrId: 'D2',
        type: 'sheet',
        children: [
          { label: '明细表D2-2', value: 'D2/D2-2', addrId: 'D2/D2-2', type: 'sheet', meta: sheetEntry },
        ],
      },
    ])
    acnrMocks.loadCellNodes.mockResolvedValue([
      { label: '期末余额', value: 'D2/D2-2/E100', addrId: 'D2/D2-2/E100', type: 'cell', meta: cellEntry },
    ])
    const wrapper = mountPicker()
    const load = wrapper.findComponent(ElTreeStub).props('load') as any

    // 1) 根 → 分组
    const groups = await driveLoad(load, { level: 0 })
    // 2) 分组 → sheet 子节点
    const sheets = await driveLoad(load, { level: 1, data: groups[0] })
    expect(sheets[0].nodeType).toBe('sheet')
    // 3) sheet → cell 子节点（loadCellNodes）
    const cells = await driveLoad(load, { level: 2, data: sheets[0] })
    await flushPromises()

    expect(acnrMocks.loadCellNodes).toHaveBeenCalledTimes(1)
    expect(acnrMocks.loadCellNodes).toHaveBeenCalledWith(sheetEntry)
    expect(cells[0].nodeType).toBe('cell')
    expect(cells[0].addrId).toBe('D2/D2-2/E100')
  })

  it('域内登记数为 0 → 空态（不渲染分组节点）', async () => {
    acnrMocks.buildAddressTree.mockResolvedValue([])
    const wrapper = mountPicker()
    const load = wrapper.findComponent(ElTreeStub).props('load') as any
    const groups = await driveLoad(load, { level: 0 })
    await flushPromises()
    expect(groups).toEqual([])
    expect(wrapper.vm.loadState).toBe('empty')
  })
})

// ════════════════════════════════════════════════════════════════════════════
// R4.3 — GtIndexChip(value) 渲染 + resolveIndex 下钻
// ════════════════════════════════════════════════════════════════════════════
describe('结果列下钻 useAcnrDrill — resolveIndex 拿 jump_route 跳转 (R4.3)', () => {
  it('normalizeColumns：ColumnMeta 有 addr_id → drillable=true，供 GtIndexChip(value) 渲染', () => {
    const cols = normalizeColumns([
      { key: 'amt', title: '金额', addr_id: 'D2/D2-2/E100', dtype: 'number' },
      { key: 'name', title: '名称', addr_id: null },
      'legacy_col',
    ])
    expect(cols[0]).toMatchObject({ key: 'amt', addrId: 'D2/D2-2/E100', drillable: true })
    expect(cols[1]).toMatchObject({ key: 'name', addrId: null, drillable: false })
    expect(cols[2]).toMatchObject({ key: 'legacy_col', addrId: null, drillable: false })
  })

  it('addrIdToIndexRef：三段 addr_id → GtIndexChip 可解析的 cell 索引语法', () => {
    expect(addrIdToIndexRef('D2/D2-2/E100')).toBe('cell:D2-2!E100')
    expect(addrIdToIndexRef('D2/D2-2')).toBe('wp:D2-2')
    expect(addrIdToIndexRef(null)).toBeNull()
  })

  it('cellAddrId：优先行级 __addr_id，回退列级 addr_id', () => {
    const meta = { key: 'amt', title: '金额', addrId: 'D2/D2-2/E100', drillable: true, dtype: 'number' }
    expect(cellAddrId({ amt: 100 }, meta)).toBe('D2/D2-2/E100')
    expect(cellAddrId({ amt: 100, amt__addr_id: 'D3/D3-1/F9' }, meta)).toBe('D3/D3-1/F9')
  })

  it('drill：命中且有 jump_route → resolveIndex(cell:..) 且用返回路由打开（不自拼路由）', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null as any)
    acnrMocks.resolveIndex.mockResolvedValue({
      found: true,
      jump_route: '/projects/p1/workpapers/wp-1/edit?sheet=D2-2',
    })
    const { drill } = useAcnrDrill(() => 'p1')

    await drill('D2/D2-2/E100')

    expect(acnrMocks.resolveIndex).toHaveBeenCalledWith('cell:D2-2!E100')
    expect(openSpy).toHaveBeenCalledTimes(1)
    const url = openSpy.mock.calls[0][0] as string
    expect(url).toContain('/projects/p1/workpapers/wp-1/edit?sheet=D2-2')
    expect(url).toContain('cell=E100')
    openSpy.mockRestore()
  })

  it('drill：resolveIndex found=false → 提示失效、不跳转（视图不变，R4.6）', async () => {
    const { ElMessage } = await import('element-plus')
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null as any)
    acnrMocks.resolveIndex.mockResolvedValue({ found: false })
    const { drill } = useAcnrDrill(() => 'p1')

    await drill('D2/D2-2/E100')

    expect(acnrMocks.resolveIndex).toHaveBeenCalledWith('cell:D2-2!E100')
    expect(openSpy).not.toHaveBeenCalled()
    expect((ElMessage as any).warning).toHaveBeenCalledWith('目标已失效')
    openSpy.mockRestore()
  })
})

// ════════════════════════════════════════════════════════════════════════════
// R11.6 — 高级构建器入口禁用态
// ════════════════════════════════════════════════════════════════════════════
describe('CustomQueryTab — 高级构建器禁用态 (R11.6)', () => {
  async function mountTab() {
    const CustomQueryTab = (await import('@/components/template-library/CustomQueryTab.vue')).default
    const wrapper = shallowMount(CustomQueryTab, {
      global: {
        directives: { loading: {} },
        // el-dialog 桩不渲染其插槽内容：避免其内嵌 el-table-column 的 #default="{ row }"
        // 被以 undefined 作用域调用而崩（弹窗默认关闭，本就无需渲染内容）。
        stubs: { 'el-dialog': { template: '<div class="el-dialog-stub" />' } },
      },
    })
    await flushPromises()
    return wrapper
  }

  it('非 admin/manager/partner 角色 → canUseBuilder=false，onOpenBuilder 不打开构建器', async () => {
    roleHolder.value = 'auditor'
    const wrapper = await mountTab()
    expect(wrapper.vm.canUseBuilder).toBe(false)
    // 双保险：即便被绕过点击也不打开
    wrapper.vm.onOpenBuilder()
    expect(wrapper.vm.builderDialogVisible).toBe(false)
    // 有原因提示文案
    expect(wrapper.vm.builderDisabledReason).toContain('管理员')
  })

  it('admin/manager/partner 角色 → canUseBuilder=true 且可打开构建器', async () => {
    for (const role of ['admin', 'manager', 'partner']) {
      roleHolder.value = role
      const wrapper = await mountTab()
      expect(wrapper.vm.canUseBuilder).toBe(true)
      wrapper.vm.onOpenBuilder()
      expect(wrapper.vm.builderDialogVisible).toBe(true)
    }
  })
})

// ════════════════════════════════════════════════════════════════════════════
// 年度默认值 — 必须落在「有数据的那一年」
//
// 缺陷：年度输入框固定初始化为 `new Date().getFullYear()`（日历当年），而审计做的是
// 上一年度报表。2026 年打开页面默认查 2026，四表里只有 2025 的数据 ⇒ 任何查询恒
// 返回 0 行，且页面不提示原因，看起来像功能坏了。
//
// 真源 = 后端 `resolve_project_audit_year`（`GET /api/projects` 下发 `audit_year`）。
// 判据用**行为**：让 mock 的项目列表带 audit_year，断言选中后 formCtx.year 跟随；
// 并断言初始值不等于日历当年（否则等于把缺陷当基线锁死）。
// ════════════════════════════════════════════════════════════════════════════
describe('CustomQueryTab — 年度默认值跟随项目审计年度', () => {
  async function mountTabWithProjects(projects: any[]) {
    apiMocks.get.mockImplementation((url: string) => {
      if (String(url).includes('/api/projects')) return Promise.resolve(projects)
      return Promise.resolve([])
    })
    const CustomQueryTab = (await import('@/components/template-library/CustomQueryTab.vue')).default
    const wrapper = shallowMount(CustomQueryTab, {
      global: {
        directives: { loading: {} },
        stubs: {
          'el-dialog': { template: '<div class="el-dialog-stub" />' },
          // 结果表格的 #default="{ row }" 在 shallowMount 下会以 undefined 作用域被
          // 调用（未处理的 rejection 会污染其它用例），本组不关心表格渲染，直接桩掉。
          'el-table': { template: '<div class="el-table-stub" />' },
          'el-table-column': { template: '<div class="el-table-column-stub" />' },
        },
      },
    })
    await flushPromises()
    return wrapper
  }

  it('初始年度不是日历当年（审计做上一年度，当年在四表里没有数据）', async () => {
    const wrapper = await mountTabWithProjects([])
    expect(wrapper.vm.formCtx.year).not.toBe(new Date().getFullYear())
    expect(wrapper.vm.formCtx.year).toBe(new Date().getFullYear() - 1)
  })

  it('选中项目后年度跟随该项目的 audit_year', async () => {
    const wrapper = await mountTabWithProjects([
      { id: 'p-2025', name: '临港店_2025', audit_year: 2025, can_edit: true },
      { id: 'p-2023', name: '旧项目_2023', audit_year: 2023, can_edit: true },
    ])
    wrapper.vm.onProjectChange('p-2025')
    expect(wrapper.vm.formCtx.year).toBe(2025)
    // 切到另一个年度不同的项目要跟着变，不能粘住上一个项目的年度
    wrapper.vm.onProjectChange('p-2023')
    expect(wrapper.vm.formCtx.year).toBe(2023)
  })

  it('项目没有 audit_year 时退回「当年 - 1」，不退回日历当年', async () => {
    const wrapper = await mountTabWithProjects([
      { id: 'p-null', name: '无年度项目', audit_year: null, can_edit: true },
    ])
    wrapper.vm.onProjectChange('p-null')
    expect(wrapper.vm.formCtx.year).toBe(new Date().getFullYear() - 1)
  })

  it('列表加载完成时会把已选项目的年度对齐（模板恢复场景）', async () => {
    const wrapper = await mountTabWithProjects([
      { id: 'p-2024', name: '项目_2024', audit_year: 2024, can_edit: true },
    ])
    // 模拟「先由模板设好 project_id，再重新拉列表」
    wrapper.vm.formCtx.project_id = 'p-2024'
    await wrapper.vm.loadProjects()
    await flushPromises()
    expect(wrapper.vm.formCtx.year).toBe(2024)
  })

  it('0 行结果给出含年度的可诊断提示（不再静默空表）', async () => {
    const wrapper = await mountTabWithProjects([
      { id: 'p-2025', name: '临港店_2025', audit_year: 2025, can_edit: true },
    ])
    wrapper.vm.formCtx.project_id = 'p-2025'
    wrapper.vm.formCtx.source = 'tb_detail'
    wrapper.vm.onProjectChange('p-2025')
    apiMocks.post.mockResolvedValue({ rows: [], columns: [], total: 0 })

    await wrapper.vm.onExecute()
    await flushPromises()

    expect(wrapper.vm.emptyHint).toContain('2025')
    expect(wrapper.vm.emptyHint).toContain('没有匹配数据')
  })

  it('有结果时清空空态提示（不能把上一次的 0 行提示粘住）', async () => {
    const wrapper = await mountTabWithProjects([
      { id: 'p-2025', name: '临港店_2025', audit_year: 2025, can_edit: true },
    ])
    wrapper.vm.formCtx.project_id = 'p-2025'
    wrapper.vm.formCtx.source = 'tb_detail'
    apiMocks.post.mockResolvedValue({ rows: [], columns: [], total: 0 })
    await wrapper.vm.onExecute()
    await flushPromises()
    expect(wrapper.vm.emptyHint).not.toBe('')

    apiMocks.post.mockResolvedValue({ rows: [{ a: 1 }], columns: ['a'], total: 1 })
    await wrapper.vm.onExecute()
    await flushPromises()
    expect(wrapper.vm.emptyHint).toBe('')
  })
})

// ════════════════════════════════════════════════════════════════════════════
// 接线判据：项目下拉必须真的把 change 接到 onProjectChange
//
// 上一组只直调 onProjectChange —— 那只证明「函数对」，不证明「接线在」。模板里漏写
// @change 时函数永远不会被触发，而单测全绿（Vue 不报错、类型检查也查不出）。
// 故这里从下拉组件**发出** change 事件，走真实监听链。
// ════════════════════════════════════════════════════════════════════════════
describe('CustomQueryTab — 项目下拉的 change 接线', () => {
  it('从项目下拉发出 change 后年度跟随（证明模板确实接了 onProjectChange）', async () => {
    apiMocks.get.mockImplementation((url: string) => {
      if (String(url).includes('/api/projects')) {
        return Promise.resolve([
          { id: 'p-2025', name: '临港店_2025', audit_year: 2025, can_edit: true },
        ])
      }
      return Promise.resolve([])
    })
    const CustomQueryTab = (await import('@/components/template-library/CustomQueryTab.vue')).default
    const wrapper = shallowMount(CustomQueryTab, {
      global: {
        directives: { loading: {} },
        stubs: {
          'el-dialog': { template: '<div class="el-dialog-stub" />' },
          // 具名探针 stub：shallowMount 的匿名 stub 无法按组件名检索，
          // 换成有 name 的 stub 才能从它 $emit 走真实监听链。
          'el-select': { name: 'SelectProbe', template: '<div class="select-probe" />' },
        },
      },
    })
    await flushPromises()

    const selects = wrapper.findAllComponents({ name: 'SelectProbe' })
    expect(selects.length, '反向自检：没找到任何 el-select 探针，判据不可靠').toBeGreaterThan(0)

    // 项目下拉是第一个 el-select（与模板顺序一致）
    wrapper.vm.formCtx.year = 1999
    selects[0].vm.$emit('change', 'p-2025')
    await flushPromises()
    expect(wrapper.vm.formCtx.year, '项目下拉的 change 未接到 onProjectChange').toBe(2025)
  })
})
