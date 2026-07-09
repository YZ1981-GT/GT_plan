/**
 * GtS35Bundle.routing.spec.ts — sheetName 路由 + readonly 透传（Task 4.3）
 *
 * Spec: .kiro/specs/s35-refinancing-bundle/  Task 4.3
 * Validates: Requirements 5.1, 5.2, 5.3, 5.4, 8.4, 8.5
 *
 * 覆盖：
 *  - Req 5.1 外部 navigate('S35',{sheet:'S35-3'}) → props.sheetName 初始激活对应 Tab
 *  - Req 5.2 URL ?sheet=S35-3 → 初始激活对应 Tab
 *  - Req 5.3 props.sheetName 变更 → 响应切换 Tab
 *  - Req 5.4 非法 sheetName → 保持当前 Tab 不变
 *  - Req 8.4 readonly=true → 透传 GtAProgramConsole + GtS35DetailTable
 *  - Req 8.5 readonly=true → 子表禁止编辑
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// ─── Mocks ───

const mockGet = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: { get: (...args: any[]) => mockGet(...args) },
}))

vi.mock('@/services/workpaperApi', () => ({
  getWpIndex: vi.fn(async () => [
    { wp_code: 'S35-1', wp_id: 'wp-s35-1', id: 'idx-1' },
    { wp_code: 'S35-1-1', wp_id: 'wp-s35-1-1', id: 'idx-1-1' },
    { wp_code: 'S35-2', wp_id: 'wp-s35-2', id: 'idx-2' },
    { wp_code: 'S35-2-1', wp_id: 'wp-s35-2-1', id: 'idx-2-1' },
    { wp_code: 'S35-3', wp_id: 'wp-s35-3', id: 'idx-3' },
    { wp_code: 'S35-3-1', wp_id: 'wp-s35-3-1', id: 'idx-3-1' },
    { wp_code: 'S35-4', wp_id: 'wp-s35-4', id: 'idx-4' },
    { wp_code: 'S35-5', wp_id: 'wp-s35-5', id: 'idx-5' },
  ]),
}))

// 可变 route mock
const routeMock: { params: Record<string, any>; query: Record<string, any> } = {
  params: { projectId: 'proj-1' },
  query: {},
}
vi.mock('vue-router', () => ({
  useRoute: () => routeMock,
  useRouter: () => ({ push: vi.fn() }),
}))

// 子组件 stub：暴露 data-readonly 便于断言只读透传
vi.mock('../../GtAProgramConsole.vue', () => ({
  __esModule: true,
  default: {
    name: 'GtAProgramConsole',
    props: ['wpId', 'sheetName', 'readonly'],
    template:
      '<div class="program-console-stub" :data-wp-id="wpId" :data-sheet="sheetName" :data-readonly="String(readonly)" />',
  },
}))
vi.mock('../GtS35DetailTable.vue', () => ({
  __esModule: true,
  default: {
    name: 'GtS35DetailTable',
    props: ['wpId', 'sheetCode', 'readonly'],
    emits: ['data-changed'],
    template:
      '<div class="detail-table-stub" :data-wp-id="wpId" :data-sheet-code="sheetCode" :data-readonly="String(readonly)" />',
  },
}))

import GtS35Bundle from '../GtS35Bundle.vue'

// ─── el-* stubs ───

const stubs = {
  'el-tabs': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<div class="el-tabs-stub"><slot /></div>',
  },
  'el-tab-pane': {
    props: ['name', 'label', 'lazy'],
    template: '<div class="el-tab-pane-stub" :data-name="name"><slot /></div>',
  },
  'el-radio-group': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<div class="el-radio-group-stub"><slot /></div>',
  },
  'el-radio-button': {
    props: ['value'],
    template: '<span class="el-radio-button-stub">{{ value }}</span>',
  },
  'el-result': { template: '<div class="el-result-stub"><slot /></div>' },
  'el-icon': { template: '<i class="el-icon-stub" />' },
}

function mountBundle(props: Record<string, any> = {}) {
  mockGet.mockImplementation((url: string) => {
    if (typeof url === 'string' && url.includes('/checklist-responses')) {
      return Promise.resolve([])
    }
    return Promise.resolve({})
  })
  return mount(GtS35Bundle, {
    props: { wpId: 'wp-s35', ...props },
    global: {
      stubs,
      directives: { loading: {} },
    },
  })
}

beforeEach(() => {
  mockGet.mockReset()
  routeMock.query = {}
})

// ─── Req 5.1：外部 navigate → props.sheetName 初始激活 ───
describe('GtS35Bundle — props.sheetName 初始激活（Req 5.1）', () => {
  it('初始 props.sheetName=S35-3 → 激活 S35-3 Tab', async () => {
    const wrapper = mountBundle({ sheetName: 'S35-3' })
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.activeTab).toBe('S35-3')
  })

  it('初始 props.sheetName=S35-5 → 激活 S35-5 Tab', async () => {
    const wrapper = mountBundle({ sheetName: 'S35-5' })
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.activeTab).toBe('S35-5')
  })
})

// ─── Req 5.2：URL query ?sheet= 激活 ───
describe('GtS35Bundle — URL query 路由（Req 5.2）', () => {
  it('URL ?sheet=S35-4 → 初始激活 S35-4 Tab', async () => {
    routeMock.query = { sheet: 'S35-4' }
    const wrapper = mountBundle()
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.activeTab).toBe('S35-4')
  })

  it('props.sheetName 优先于 URL query', async () => {
    routeMock.query = { sheet: 'S35-4' }
    const wrapper = mountBundle({ sheetName: 'S35-2' })
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.activeTab).toBe('S35-2')
  })
})

// ─── Req 5.3：props.sheetName 变更 → 响应切换 Tab ───
describe('GtS35Bundle — props.sheetName 变更（Req 5.3）', () => {
  it('sheetName 从 S35-1 切换到 S35-4 → activeTab 响应变化', async () => {
    const wrapper = mountBundle({ sheetName: 'S35-1' })
    await flushPromises()
    expect((wrapper.vm as any).activeTab).toBe('S35-1')

    await wrapper.setProps({ sheetName: 'S35-4' })
    await flushPromises()
    expect((wrapper.vm as any).activeTab).toBe('S35-4')
  })

  it('连续变更 sheetName → 每次都响应', async () => {
    const wrapper = mountBundle({ sheetName: 'S35-1' })
    await flushPromises()

    await wrapper.setProps({ sheetName: 'S35-2' })
    await flushPromises()
    expect((wrapper.vm as any).activeTab).toBe('S35-2')

    await wrapper.setProps({ sheetName: 'S35-5' })
    await flushPromises()
    expect((wrapper.vm as any).activeTab).toBe('S35-5')
  })
})

// ─── Req 5.4：非法 sheetName → 保持当前 Tab ───
describe('GtS35Bundle — 非法 sheetName 保持当前（Req 5.4）', () => {
  it('初始非法 sheetName → 保持默认第一个可见 Tab', async () => {
    const wrapper = mountBundle({ sheetName: 'INVALID-SHEET' })
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.activeTab).toBe('S35-1')
  })

  it('已在某 Tab 时传入非法 sheetName → 保持当前 Tab', async () => {
    const wrapper = mountBundle({ sheetName: 'S35-3' })
    await flushPromises()
    expect((wrapper.vm as any).activeTab).toBe('S35-3')

    await wrapper.setProps({ sheetName: 'ZZ-999' })
    await flushPromises()
    expect((wrapper.vm as any).activeTab).toBe('S35-3')
  })

  it('空字符串 sheetName → 不改变 active', async () => {
    const wrapper = mountBundle({ sheetName: 'S35-2' })
    await flushPromises()
    expect((wrapper.vm as any).activeTab).toBe('S35-2')

    await wrapper.setProps({ sheetName: '' })
    await flushPromises()
    expect((wrapper.vm as any).activeTab).toBe('S35-2')
  })
})

// ─── Req 8.4：readonly 透传 GtAProgramConsole ───
describe('GtS35Bundle — readonly 透传 GtAProgramConsole（Req 8.4）', () => {
  it('readonly=true → 无子表 Tab（S35-4）中 GtAProgramConsole 收到 readonly=true', async () => {
    const wrapper = mountBundle({ sheetName: 'S35-4', readonly: true })
    await flushPromises()
    const consoles = wrapper.findAll('.program-console-stub')
    // S35-4 Tab should have a program console with readonly=true
    const s35_4_console = consoles.find(c => c.attributes('data-wp-id') === 'wp-s35-4')
    expect(s35_4_console).toBeDefined()
    expect(s35_4_console!.attributes('data-readonly')).toBe('true')
  })

  it('readonly 缺省（默认可编辑）→ GtAProgramConsole 收到 readonly=false', async () => {
    const wrapper = mountBundle({ sheetName: 'S35-4' })
    await flushPromises()
    const consoles = wrapper.findAll('.program-console-stub')
    const s35_4_console = consoles.find(c => c.attributes('data-wp-id') === 'wp-s35-4')
    expect(s35_4_console).toBeDefined()
    expect(s35_4_console!.attributes('data-readonly')).toBe('false')
  })

  it('readonly=true → 含子表 Tab（S35-1）中"核查程序表"视图的 GtAProgramConsole 收到 readonly=true', async () => {
    const wrapper = mountBundle({ sheetName: 'S35-1', readonly: true })
    await flushPromises()
    // S35-1 默认视图是"program"子 sheet
    const consoles = wrapper.findAll('.program-console-stub')
    const s35_1_console = consoles.find(c => c.attributes('data-wp-id') === 'wp-s35-1')
    expect(s35_1_console).toBeDefined()
    expect(s35_1_console!.attributes('data-readonly')).toBe('true')
  })
})

// ─── Req 8.4 / 8.5：readonly 透传 GtS35DetailTable ───
describe('GtS35Bundle — readonly 透传 GtS35DetailTable（Req 8.4/8.5）', () => {
  it('readonly=true → 明细子表收到 readonly=true（禁止编辑）', async () => {
    const wrapper = mountBundle({ sheetName: 'S35-1', readonly: true })
    await flushPromises()
    // 切换到 detail 视图
    const vm = wrapper.vm as any
    vm.subSheetView['S35-1'] = 'detail'
    await flushPromises()

    const detailTable = wrapper.find('.detail-table-stub')
    expect(detailTable.exists()).toBe(true)
    expect(detailTable.attributes('data-readonly')).toBe('true')
  })

  it('readonly=false → 明细子表收到 readonly=false', async () => {
    const wrapper = mountBundle({ sheetName: 'S35-1', readonly: false })
    await flushPromises()
    const vm = wrapper.vm as any
    vm.subSheetView['S35-1'] = 'detail'
    await flushPromises()

    const detailTable = wrapper.find('.detail-table-stub')
    expect(detailTable.exists()).toBe(true)
    expect(detailTable.attributes('data-readonly')).toBe('false')
  })
})
