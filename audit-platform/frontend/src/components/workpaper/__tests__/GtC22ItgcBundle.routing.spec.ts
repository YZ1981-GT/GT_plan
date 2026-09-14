/**
 * GtC22ItgcBundle.routing.spec.ts — sheetName 路由 + readonly 透传（Task 4.3）
 *
 * Spec: .kiro/specs/c22-itgc-bundle/  Task 4.3
 * Validates: Requirements 6.1, 6.2, 6.3, 6.4, 9.1, 9.2, 9.3
 *
 * 覆盖：
 *  - Req 6.1 外部 navigate('C22',{sheet}) → props.sheetName 初始激活对应 Tab
 *  - Req 6.2 URL ?sheet=SA-3 → 初始激活对应 Tab
 *  - Req 6.3 props.sheetName 变更 → 响应切换 Tab
 *  - Req 6.4 非法 sheetName → 保持当前（默认 matrix / 已在子页则保持）
 *  - 路由到子页时顶层分组 section 同步选中所属大类（activeSection 派生）
 *  - Req 9.1/9.2 readonly=true → 透传控制点子页 + 子页测试禁用
 *  - Req 9.1/9.3 readonly=true → 透传 C21/C21-1（OnlyOffice）；matrix/C21-1 仍可浏览跳转
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mockGet = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: { get: (...args: any[]) => mockGet(...args) },
}))

vi.mock('@/services/workpaperApi', () => ({
  getWpIndex: vi.fn(async () => [
    { wp_code: 'C21', wp_id: 'wp-c21', id: 'idx-c21' },
    { wp_code: 'C21-1', wp_id: 'wp-c21-1', id: 'idx-c21-1' },
  ]),
}))

// 可变 route mock（每个用例可通过 routeMock.query 设置 URL ?sheet=）
const routeMock: { params: Record<string, any>; query: Record<string, any> } = {
  params: { projectId: 'proj-1' },
  query: {},
}
vi.mock('vue-router', () => ({
  useRoute: () => routeMock,
}))

// 子页 stub：暴露 data-readonly 便于断言只读透传
vi.mock('../GtOnlyOfficeSheet.vue', () => ({
  __esModule: true,
  default: {
    name: 'GtOnlyOfficeSheet',
    props: ['wpId', 'projectId', 'sheetName', 'readonly'],
    template:
      '<div class="onlyoffice-stub" :data-sheet="sheetName" :data-readonly="String(readonly)" />',
  },
}))
vi.mock('../GtC22ControlSheet.vue', () => ({
  __esModule: true,
  default: {
    name: 'GtC22ControlSheet',
    props: ['wpId', 'projectId', 'tab', 'matrixRow', 'readonly'],
    template:
      '<div class="c22-control-sheet-stub" :data-control="tab?.id" :data-readonly="String(readonly)" />',
  },
}))
vi.mock('../GtC21FindingsSummary.vue', () => ({
  __esModule: true,
  default: {
    name: 'GtC21FindingsSummary',
    props: ['wpId', 'projectId', 'defects', 'readonly'],
    template:
      '<div class="c21-findings-stub" :data-readonly="String(readonly)" />',
  },
}))

import GtC22ItgcBundle from '../GtC22ItgcBundle.vue'

const stubs = {
  'el-tabs': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<div class="el-tabs-stub"><slot /></div>',
  },
  'el-tab-pane': {
    props: ['name', 'label'],
    template:
      '<div class="el-tab-pane-stub" :data-name="name"><slot name="label" /><slot /></div>',
  },
  'el-progress': true,
  'el-tag': { template: '<span class="el-tag-stub"><slot /></span>' },
  'el-tooltip': { props: ['content'], template: '<span :data-tip="content"><slot /></span>' },
}

function mountBundle(props: Record<string, any> = {}) {
  mockGet.mockImplementation((url: string) => {
    if (typeof url === 'string' && url.includes('/render-config')) {
      return Promise.resolve({
        sheets: [
          { sheet_name: 'C22 IT一般控制测试', html_data: { is_matrix: true, matrix: [] } },
        ],
      })
    }
    if (typeof url === 'string' && url.includes('/checklist-responses')) {
      return Promise.resolve([])
    }
    return Promise.resolve({})
  })
  return mount(GtC22ItgcBundle, {
    props: { wpId: 'wp-c22', projectId: 'proj-1', ...props },
    global: {
      stubs,
      directives: { 'tab-wheel': {}, loading: {} },
    },
  })
}

beforeEach(() => {
  mockGet.mockReset()
  routeMock.query = {}
})

// ─── Req 6.1 / 6.3：props.sheetName 激活 + 顶层 section 同步 ───
describe('GtC22ItgcBundle — props.sheetName 路由（Req 6.1/6.3）', () => {
  it('初始 props.sheetName=SA-3 → 激活 SA-3 且顶层 section=信息安全', async () => {
    const wrapper = mountBundle({ sheetName: 'SA-3' })
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.active).toBe('SA-3')
    expect(vm.activeSection).toBe('信息安全')
  })

  it('props.sheetName 变更 → 响应切换 Tab + section（PM-4b → 程序变更）', async () => {
    const wrapper = mountBundle()
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.active).toBe('matrix')

    await wrapper.setProps({ sheetName: 'PM-4b' })
    await flushPromises()
    expect(vm.active).toBe('PM-4b')
    expect(vm.activeSection).toBe('程序变更')

    // 再切到新系统组
    await wrapper.setProps({ sheetName: 'NS-3' })
    await flushPromises()
    expect(vm.active).toBe('NS-3')
    expect(vm.activeSection).toBe('新系统')
  })

  it('sheetName=C21-1 → 激活独立底稿 Tab（section=C21-1）', async () => {
    const wrapper = mountBundle({ sheetName: 'C21-1' })
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.active).toBe('C21-1')
    expect(vm.activeSection).toBe('C21-1')
  })
})

// ─── Req 6.2：URL query ?sheet= 激活 ───
describe('GtC22ItgcBundle — URL query 路由（Req 6.2）', () => {
  it('URL ?sheet=NS-5.2 → 初始激活 NS-5.2 且 section=新系统', async () => {
    routeMock.query = { sheet: 'NS-5.2' }
    const wrapper = mountBundle()
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.active).toBe('NS-5.2')
    expect(vm.activeSection).toBe('新系统')
  })

  it('props.sheetName 优先于 URL query（都提供时取 props）', async () => {
    routeMock.query = { sheet: 'NS-3' }
    const wrapper = mountBundle({ sheetName: 'PE-6' })
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.active).toBe('PE-6')
    expect(vm.activeSection).toBe('运行维护')
  })
})

// ─── Req 6.4：非法 sheetName 保持当前 ───
describe('GtC22ItgcBundle — 非法 sheetName 保持当前（Req 6.4）', () => {
  it('初始非法 sheetName → 保持默认 matrix', async () => {
    const wrapper = mountBundle({ sheetName: '不存在的sheet' })
    await flushPromises()
    expect((wrapper.vm as any).active).toBe('matrix')
  })

  it('已在子页时传入非法 sheetName → 保持当前子页', async () => {
    const wrapper = mountBundle({ sheetName: 'SA-7' })
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.active).toBe('SA-7')

    await wrapper.setProps({ sheetName: 'ZZ-999' })
    await flushPromises()
    expect(vm.active).toBe('SA-7')
    expect(vm.activeSection).toBe('信息安全')
  })

  it('空 / 空白 sheetName → 不改变 active', async () => {
    const wrapper = mountBundle({ sheetName: 'PM-5' })
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.active).toBe('PM-5')

    await wrapper.setProps({ sheetName: '   ' })
    await flushPromises()
    expect(vm.active).toBe('PM-5')
  })
})

// ─── Req 9.1 / 9.2：readonly 透传控制点子页 + 测试禁用 ───
describe('GtC22ItgcBundle — readonly 透传子页（Req 9.1/9.2）', () => {
  it('readonly=true → 控制点子页收到 readonly=true', async () => {
    const wrapper = mountBundle({ sheetName: 'SA-3', readonly: true })
    await flushPromises()
    const sub = wrapper.find('.c22-control-sheet-stub')
    expect(sub.exists()).toBe(true)
    expect(sub.attributes('data-readonly')).toBe('true')
  })

  it('readonly 缺省（默认可编辑）→ 子页 readonly=false', async () => {
    const wrapper = mountBundle({ sheetName: 'SA-3' })
    await flushPromises()
    const sub = wrapper.find('.c22-control-sheet-stub')
    expect(sub.exists()).toBe(true)
    expect(sub.attributes('data-readonly')).toBe('false')
  })
})

// ─── Req 9.1 / 9.3：readonly 透传 C21/C21-1 + matrix 仍可浏览跳转 ───
describe('GtC22ItgcBundle — readonly 透传汇总 + 浏览跳转（Req 9.1/9.3）', () => {
  it('readonly=true → C21-1（GtC21FindingsSummary）收到 readonly=true', async () => {
    const wrapper = mountBundle({ sheetName: 'C21-1', readonly: true })
    await flushPromises()
    const findings = wrapper.find('.c21-findings-stub')
    expect(findings.exists()).toBe(true)
    expect(findings.attributes('data-readonly')).toBe('true')
  })

  it('readonly=true → C21（OnlyOffice）收到 readonly=true', async () => {
    const wrapper = mountBundle({ sheetName: 'C21', readonly: true })
    await flushPromises()
    const oo = wrapper.find('.onlyoffice-stub')
    expect(oo.exists()).toBe(true)
    expect(oo.attributes('data-readonly')).toBe('true')
  })

  it('只读模式下 matrix 仍可点击控制点行跳转子页（Req 9.3）', async () => {
    const wrapper = mountBundle({ readonly: true })
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.active).toBe('matrix')

    const row = wrapper.find('.c22-matrix-row')
    expect(row.exists()).toBe(true)
    await row.trigger('click')
    // 首个控制点 SA-3，section 同步切到信息安全
    expect(vm.active).toBe('SA-3')
    expect(vm.activeSection).toBe('信息安全')
  })
})
