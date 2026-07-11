/**
 * CustomQueryFieldPicker.spec.ts — 高级查询「选字段」ACNR 地址树 单元测试
 *
 * spec acnr-consumer-wiring Task 7.2（组件由 Task 7.1 实现）
 *
 * 验证：
 * 1. buildAddressTree 被调用时传入正确 cycle（acnr Req 8.1 / 8.5）
 * 2. template-applied 事件触发 clearCache + reload（acnr Req 8.6）
 * 3. loading=true 时展示 spinner（v-loading，acnr Req 8.7）
 * 4. 空数组时展示 el-empty 占位（acnr Req 8.8）
 * 5. cell 节点 click emit 正确 payload（addrId + formulaRef，acnr Req 8.4）
 *
 * **Validates: Requirements 8.1–8.8**
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'

// ─── ResizeObserver polyfill（jsdom 缺失，Element Plus 部分组件需要） ──────────
if (!(globalThis as any).ResizeObserver) {
  ;(globalThis as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

// ─── Mock useAcnr（受控 buildAddressTree / loadCellNodes / clearCache） ─────────
// 注：vi.mock 工厂被 hoist，引用变量须以 `mock` 前缀命名（vitest 约定）
const mockBuildAddressTree = vi.fn()
const mockLoadCellNodes = vi.fn()
const mockClearCache = vi.fn()

vi.mock('@/services/acnr/useAcnr', () => ({
  useAcnr: () => ({
    buildAddressTree: mockBuildAddressTree,
    loadCellNodes: mockLoadCellNodes,
    clearCache: mockClearCache,
  }),
}))

// ─── Import after mocks ───────────────────────────────────────────────────────
import ElementPlus from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import CustomQueryFieldPicker from '../CustomQueryFieldPicker.vue'

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const SHEET_ENTRY = {
  addr_id: 'D2/D2-2',
  domain: 'wp',
  cycle: 'D',
  parent_wp_code: 'D2',
  sheet_code: 'D2-2',
  sheet_name: '明细表D2-2',
}

const CELL_ENTRY = {
  addr_id: 'D2/D2-2/E100',
  parent_addr_id: 'D2/D2-2',
  domain: 'wp',
  cell_address: 'E100',
  semantic_label: '期末余额',
  formula_ref: "WP('D2','明细表D2-2','E100')",
}

/** buildAddressTree 返回的分组树（group → sheet 子节点） */
function makeTree() {
  return [
    {
      label: 'D2',
      value: 'D2',
      addrId: 'D2',
      type: 'sheet' as const,
      children: [
        {
          label: '明细表D2-2',
          value: SHEET_ENTRY.addr_id,
          addrId: SHEET_ENTRY.addr_id,
          type: 'sheet' as const,
          meta: SHEET_ENTRY,
        },
      ],
    },
  ]
}

/** loadCellNodes 返回的 cell 子节点 */
function makeCellNodes() {
  return [
    {
      label: '期末余额',
      value: CELL_ENTRY.addr_id,
      addrId: CELL_ENTRY.addr_id,
      type: 'cell' as const,
      meta: CELL_ENTRY,
    },
  ]
}

// ─── el-tree stub ─────────────────────────────────────────────────────────────
// 用 stub 精确驱动 lazy load（mounted 自动触发 root load，模拟 el-tree lazy 行为），
// 并暴露 load prop 供测试逐层驱动 + node-click 事件供 cell 点选断言。
const ElTreeStub = defineComponent({
  name: 'ElTree',
  props: {
    load: { type: Function, default: undefined },
    props: { type: Object, default: () => ({}) },
    nodeKey: { type: String, default: '' },
    lazy: { type: Boolean, default: false },
    expandOnClickNode: { type: Boolean, default: false },
    highlightCurrent: { type: Boolean, default: false },
  },
  emits: ['node-click'],
  mounted() {
    // 模拟 el-tree lazy：挂载即加载 root（level 0）
    if (this.load) this.load({ level: 0 }, () => {})
  },
  template: '<div class="gt-eltree-stub"></div>',
})

// ─── Helpers ──────────────────────────────────────────────────────────────────

function mountPicker(props: Record<string, unknown> = {}): VueWrapper {
  return mount(CustomQueryFieldPicker, {
    props,
    global: {
      plugins: [ElementPlus],
      stubs: { ElTree: ElTreeStub },
    },
  })
}

function getTree(wrapper: VueWrapper) {
  return wrapper.findComponent(ElTreeStub)
}

/** 逐层驱动 lazy load：root → group → sheet → cell，返回各层 PickerNode */
async function driveToCell(wrapper: VueWrapper) {
  const load = getTree(wrapper).props('load') as (n: any, r: (d: any) => void) => Promise<void>
  let groups: any
  await load({ level: 0 }, (d) => (groups = d))
  await flushPromises()
  let sheets: any
  await load({ level: 1, data: groups[0] }, (d) => (sheets = d))
  let cells: any
  await load({ level: 2, data: sheets[0] }, (d) => (cells = d))
  await flushPromises()
  return { groups, sheets, cells }
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('CustomQueryFieldPicker — 单元测试', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockBuildAddressTree.mockResolvedValue(makeTree())
    mockLoadCellNodes.mockResolvedValue(makeCellNodes())
  })

  afterEach(() => {
    // 真 eventBus 为单例，清理以免跨用例串扰
    eventBus.all.clear()
  })

  it('挂载时以正确 cycle 调用 buildAddressTree（cycle="D"）', async () => {
    const wrapper = mountPicker({ cycle: 'D' })
    await flushPromises()
    expect(mockBuildAddressTree).toHaveBeenCalledWith('D')
    wrapper.unmount()
  })

  it('未传 cycle 时以 undefined 调用 buildAddressTree', async () => {
    const wrapper = mountPicker()
    await flushPromises()
    expect(mockBuildAddressTree).toHaveBeenCalledWith(undefined)
    wrapper.unmount()
  })

  it('template-applied 事件触发 clearCache + reload（重新加载树）', async () => {
    const wrapper = mountPicker({ cycle: 'D' })
    await flushPromises()

    mockClearCache.mockClear()
    mockBuildAddressTree.mockClear()

    eventBus.emit('template-applied', { configType: 'report_config' })
    await nextTick()
    await flushPromises()

    // clearCache 直接调用
    expect(mockClearCache).toHaveBeenCalledTimes(1)
    // reload → treeKey++ → el-tree 重挂 → lazy 重新加载 → buildAddressTree 再次被调
    expect(mockBuildAddressTree).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('loading 态展示 spinner（v-loading mask）', async () => {
    // buildAddressTree 挂起 → loadState 停留在 loading
    let resolveTree: (v: unknown) => void = () => {}
    mockBuildAddressTree.mockReturnValue(
      new Promise((res) => {
        resolveTree = res
      }),
    )
    const wrapper = mountPicker({ cycle: 'D' })
    await nextTick()
    await nextTick()

    // el-empty / error 均未展示，树容器渲染且 v-loading 生效
    expect(wrapper.find('.gt-cqfp-tree-wrap').exists()).toBe(true)
    expect(wrapper.find('.el-empty').exists()).toBe(false)
    expect(wrapper.find('.el-loading-mask').exists()).toBe(true)

    // 收尾：释放挂起 promise
    resolveTree(makeTree())
    await flushPromises()
    wrapper.unmount()
  })

  it('空数组时展示 el-empty 占位', async () => {
    mockBuildAddressTree.mockResolvedValue([])
    const wrapper = mountPicker({ cycle: 'D' })
    await flushPromises()
    await nextTick()

    expect(wrapper.find('.el-empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('该域暂无已登记内容')
    // 空态下不渲染地址树容器
    expect(wrapper.find('.gt-cqfp-tree-wrap').exists()).toBe(false)
    wrapper.unmount()
  })

  it('点击 cell 节点 emit select 正确 payload（addrId + formulaRef）', async () => {
    const wrapper = mountPicker({ cycle: 'D' })
    await flushPromises()

    const { cells } = await driveToCell(wrapper)
    expect(cells).toHaveLength(1)
    // loadCellNodes 以 sheet meta 调用
    expect(mockLoadCellNodes).toHaveBeenCalledWith(SHEET_ENTRY)

    // 触发 cell 节点点击
    getTree(wrapper).vm.$emit('node-click', cells[0])
    await nextTick()

    const selectEvents = wrapper.emitted('select')
    expect(selectEvents).toBeTruthy()
    expect(selectEvents![0][0]).toMatchObject({
      addrId: 'D2/D2-2/E100',
      formulaRef: "WP('D2','明细表D2-2','E100')",
      label: '期末余额',
    })

    // 同时更新 v-model（已选字段列表）
    const modelEvents = wrapper.emitted('update:modelValue')
    expect(modelEvents).toBeTruthy()
    expect(modelEvents![modelEvents!.length - 1][0]).toEqual(['D2/D2-2/E100'])
    wrapper.unmount()
  })

  it('点击非 cell 节点（group/sheet）不 emit select', async () => {
    const wrapper = mountPicker({ cycle: 'D' })
    await flushPromises()

    const { groups, sheets } = await driveToCell(wrapper)
    getTree(wrapper).vm.$emit('node-click', groups[0]) // group
    getTree(wrapper).vm.$emit('node-click', sheets[0]) // sheet
    await nextTick()

    expect(wrapper.emitted('select')).toBeFalsy()
    wrapper.unmount()
  })
})
