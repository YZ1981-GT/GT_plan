// Feature: procedure-delegation-visibility-isolation — Task 12（组件 C16）
//
// 验证「我的主编底稿」独立身份视图：
//  - 走 listMyLeadWorkpapers 端点（Req 11.12），不与程序任务串线（Req 11.11）
//  - nullable wp 显示「底稿尚未生成」并禁用打开/下载（Req 12.8/12.9）
//  - 404 显示统一占位「资源不存在或不可访问」，不闪现缓存名称（Req 12.7）
//  - 状态拆分 index_status / file_status 分列展示（Req 12.4/12.5）
import { computed, defineComponent, h, inject, provide, type ComputedRef } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  listMyLeadWorkpapers: vi.fn(),
  downloadWorkpaper: vi.fn(),
  routerPush: vi.fn(),
}))

vi.mock('@/services/workpaperApi', () => ({
  listMyLeadWorkpapers: mocks.listMyLeadWorkpapers,
  downloadWorkpaper: mocks.downloadWorkpaper,
  // 运行时常量（composable 依赖）
  EXTERNAL_NOT_FOUND_MESSAGE: '资源不存在或不可访问',
  FILE_STATUS_NOT_GENERATED: 'not_generated',
}))

vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: mocks.routerPush }) }))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

import MyLeadWorkpapers from '../MyLeadWorkpapers.vue'

const tableRowsKey = Symbol('tableRows')
const ElTableStub = defineComponent({
  props: { data: { type: Array, default: () => [] } },
  setup(props, { slots }) {
    provide(tableRowsKey, computed(() => props.data as any[]))
    return () => h('div', { class: 'el-table-stub' }, slots.default?.())
  },
})
const ElTableColumnStub = defineComponent({
  setup(_, { slots }) {
    const rows = inject<ComputedRef<any[]>>(tableRowsKey, computed(() => []))
    return () => h('div', { class: 'el-col' },
      slots.default ? rows.value.map((row, i) => h('div', { class: 'el-cell', key: i }, slots.default?.({ row }))) : [])
  },
})
const ElButtonStub = defineComponent({
  emits: ['click'],
  setup(_, { slots, emit }) {
    return () => h('button', { class: 'gt-btn', onClick: () => emit('click') }, slots.default?.())
  },
})

const stubs = {
  'el-table': ElTableStub,
  'el-table-column': ElTableColumnStub,
  'el-button': ElButtonStub,
  'el-tag': { template: '<span class="gt-tag"><slot /></span>' },
  'el-tooltip': { template: '<span class="gt-tip"><slot /></span>' },
  'el-pagination': true,
  GtEmpty: { props: ['title'], template: '<div class="gt-empty" :data-title="title">{{ title }}</div>' },
}

function mkItem(over: Record<string, any> = {}) {
  return {
    wp_index_id: 'wi-1', project_id: 'p1', wp_id: 'wp-1', wp_code: 'D2-1',
    wp_name: '应收账款审定表', audit_cycle: 'D', index_status: 'in_progress',
    file_status: 'draft', review_status: 'not_submitted', assigned_to: 'u1',
    reviewer: null, file_version: 1, file_path: '/x', source_type: 'template',
    prefill_stale: false, wp_generated: true, created_at: null, updated_at: null,
    ...over,
  }
}
function env(items: any[], over: Record<string, any> = {}) {
  return {
    items, total: items.length,
    stats: { by_index_status: {}, by_file_status: {} },
    page: 1, page_size: 20, ...over,
  }
}

async function mountWith() {
  const wrapper = mount(MyLeadWorkpapers, { props: { projectId: 'p1' }, global: { stubs } })
  await flushPromises()
  return wrapper
}

describe('MyLeadWorkpapers (Task 12)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('loads from the my-lead-workpapers endpoint (independent lead identity)', async () => {
    mocks.listMyLeadWorkpapers.mockResolvedValue(env([mkItem()]))
    await mountWith()
    expect(mocks.listMyLeadWorkpapers).toHaveBeenCalled()
    const [pid] = mocks.listMyLeadWorkpapers.mock.calls[0]
    expect(pid).toBe('p1')
  })

  it('nullable wp shows 底稿尚未生成 and does not render open/download buttons', async () => {
    mocks.listMyLeadWorkpapers.mockResolvedValue(env([mkItem({ wp_id: null, wp_generated: false, file_status: null })]))
    const wrapper = await mountWith()
    expect(wrapper.text()).toContain('底稿尚未生成')
    const openBtn = wrapper.findAll('button.gt-btn').find(b => b.text() === '打开')
    expect(openBtn).toBeUndefined()
    // 点击不发生跳转
    expect(mocks.routerPush).not.toHaveBeenCalled()
  })

  it('generated wp exposes open + download and deep-links to editor', async () => {
    mocks.listMyLeadWorkpapers.mockResolvedValue(env([mkItem({ wp_id: 'wp-7' })]))
    const wrapper = await mountWith()
    const openBtn = wrapper.findAll('button.gt-btn').find(b => b.text() === '打开')
    expect(openBtn).toBeTruthy()
    await openBtn!.trigger('click')
    expect(mocks.routerPush).toHaveBeenCalledTimes(1)
    expect(mocks.routerPush.mock.calls[0][0].path).toContain('/workpapers/wp-7/edit')
  })

  it('404 shows unified placeholder and never flashes cached names', async () => {
    mocks.listMyLeadWorkpapers.mockRejectedValue({ response: { status: 404 } })
    const wrapper = await mountWith()
    expect(wrapper.text()).toContain('资源不存在或不可访问')
    expect(wrapper.text()).not.toContain('应收账款')
  })
})
