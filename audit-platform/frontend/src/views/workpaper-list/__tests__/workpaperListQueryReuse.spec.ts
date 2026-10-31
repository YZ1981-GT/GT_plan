/**
 * 底稿列表按路径复用（spec platform-perf-hotspots R6 / R7）。
 *
 * 路由改成只在路径 / ?year= 变化时重挂后，同页只改 query（切视图、浏览器前进后退、联动横条跳 ?filter=stale）
 * 由页面自己同步：与挂载时同一规则、不重取清单、与「状态 → 地址栏」不来回触发。
 * 另钉 R7：两张清单浅层响应式，合并按 wp_index_id 取第一个匹配（与原先 find 一致）。
 */
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { computed, defineComponent, h, isReactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createMockContext } from '@/composables/useWorkpaperListContext'

const hoisted = vi.hoisted(() => ({
  route: null as any,
  replace: null as any,
  listWorkpapers: null as any,
  getWpIndex: null as any,
  mapping: null as any,
}))

vi.mock('vue-router', async () => {
  const { reactive } = await import('vue')
  hoisted.route = reactive({ params: { projectId: 'test-proj' }, query: {} as Record<string, any> })
  hoisted.replace = vi.fn(async (to: { query: Record<string, any> }) => { hoisted.route.query = { ...to.query } })
  return { useRoute: () => hoisted.route, useRouter: () => ({ replace: hoisted.replace, push: vi.fn() }) }
})
vi.mock('@/services/workpaperApi', () => {
  hoisted.listWorkpapers = vi.fn().mockResolvedValue([])
  hoisted.getWpIndex = vi.fn().mockResolvedValue([])
  hoisted.mapping = vi.fn().mockResolvedValue([])
  return {
    listWorkpapers: hoisted.listWorkpapers,
    getWpIndex: hoisted.getWpIndex,
    getWpMappingByAccount: hoisted.mapping,
    downloadWorkpaperPack: vi.fn().mockResolvedValue(undefined),
    downloadWorkpaper: vi.fn(),
  }
})
vi.mock('@/utils/http', () => ({ default: { get: vi.fn().mockResolvedValue({ data: { name: '项目', audit_year: 2025 } }), post: vi.fn() } }))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ role: 'admin', user: { id: 'u1', role: 'admin', username: 'test' }, token: 't' }),
}))
vi.mock('@/composables/useAuditContext', () => ({ useAuditContext: () => ({ onContextChange: vi.fn() }) }))
vi.mock('@/stores/project', () => ({
  useProjectStore: () => ({ projectId: 'test-proj', year: 2025, currentProjectContext: { projectId: 'test-proj' } }),
}))
vi.mock('@/composables/usePermissionMatrix', () => ({
  usePermissionMatrix: () => ({
    can: () => true, whyCannot: () => null, currentRole: computed(() => 'admin'),
    allowedOperations: computed(() => new Set()), canRole: () => true,
  }),
}))
vi.mock('@/stores/roleContext', () => ({ useRoleContextStore: () => ({ canEditInProject: true }) }))
vi.mock('@/services/commonApi', () => ({ listUsers: vi.fn().mockResolvedValue([]) }))
vi.mock('@/services/apiProxy', () => ({ api: { post: vi.fn().mockResolvedValue({}), put: vi.fn().mockResolvedValue({}) } }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() } }))
const viewStub = (name: string) => ({
  __esModule: true,
  default: defineComponent({ name, props: { projectId: String, year: Number }, setup() { return () => h('div') } }),
})
vi.mock('@/views/workpaper-list/WorkpaperWorkbenchView.vue', () => viewStub('WorkpaperWorkbenchView'))
vi.mock('@/views/workpaper-list/WorkpaperBoardView.vue', () => viewStub('WorkpaperBoardView'))
vi.mock('@/views/workpaper-list/WorkpaperLifecycleView.vue', () => viewStub('WorkpaperLifecycleView'))
vi.mock('@/views/workpaper-list/WorkpaperDependencyGraph.vue', () => viewStub('WorkpaperDependencyGraph'))
vi.mock('@/views/workpaper-list/WorkpaperDelegationMatrix.vue', () => viewStub('WorkpaperDelegationMatrix'))

import WorkpaperList from '@/views/WorkpaperList.vue'

// 共用同一个响应式路由：上一个用例的页面不卸载会跟着本用例的 query 变化一起回写地址栏
const mounted: Array<{ unmount: () => void }> = []
afterEach(() => { while (mounted.length) mounted.pop()!.unmount() })

function mountList() {
  createMockContext({ viewMode: ref('workbench'), wpIndex: ref([]), wpList: ref([]), loading: ref(false) })
  const plain = { template: '<div><slot /><slot name="actions" /><slot name="left" /><slot name="right" /></div>' }
  const wrapper = mount(WorkpaperList, {
    global: {
      stubs: {
        GtPageHeader: plain, GtToolbar: plain, ArchivedBanner: true, ConsolLockedBanner: true, BatchActionBar: true,
        BatchAssignDialog: true, UnifiedImportDialog: true, WpImportDialog: true, WpBatchExportDialog: true, WpBulkDialog: true,
        WpTemplateCopyDialog: true, GenerationPlanDialog: true, GtCustomWpBatchDialog: true,
        ElRadioGroup: plain, ElRadioButton: true, ElButton: plain, ElInput: true, ElSelect: plain, ElOption: true,
        ElProgress: true, ElPagination: true, ElDropdown: plain, ElDropdownMenu: plain, ElDropdownItem: plain,
        ElIcon: plain, ElTooltip: plain, ElAlert: true, ElTag: plain, ElBadge: plain, ElCheckbox: true,
      },
    },
  })
  mounted.push(wrapper)
  return wrapper
}

async function setQuery(query: Record<string, any>) {
  hoisted.route.query = query
  await flushPromises()
}

beforeEach(() => {
  hoisted.route.query = {}
  hoisted.replace.mockClear()
  hoisted.listWorkpapers.mockReset().mockResolvedValue([])
  hoisted.getWpIndex.mockReset().mockResolvedValue([])
  hoisted.mapping.mockReset().mockResolvedValue([])
})

describe('同页只改 query：按挂载时同一规则同步，不重取', () => {
  test('挂载：?filter=stale ⇒ 列表视图 + 仅看待重算（与改动前同一规则）', async () => {
    hoisted.route.query = { view: 'workbench', filter: 'stale' }
    const vm = mountList().vm as any
    await flushPromises()
    expect(vm.viewMode).toBe('list')
    expect(vm.filterStale).toBe(true)
  })

  test('改 ?view= ⇒ 切视图；不重取清单、不回写地址栏', async () => {
    const vm = mountList().vm as any
    await flushPromises()
    expect(hoisted.listWorkpapers).toHaveBeenCalledTimes(1)
    await setQuery({ view: 'list' })
    expect(vm.viewMode).toBe('list')
    await setQuery({ view: 'kanban' })
    expect(vm.viewMode).toBe('kanban')
    await setQuery({ view: 'not-a-view' })
    expect(vm.viewMode).toBe('workbench')
    expect(hoisted.listWorkpapers).toHaveBeenCalledTimes(1)
    expect(hoisted.getWpIndex).toHaveBeenCalledTimes(1)
    // 只有非法 view 回落工作台时状态与地址不一致，回写一次
    expect(hoisted.replace.mock.calls.map((c: any[]) => c[0].query)).toEqual([{ view: 'workbench' }])
  })

  test('站内跳到 ?view=workbench&filter=stale（联动横条「查看详情」）⇒ 列表 + 待重算，地址栏改一次后稳定', async () => {
    const vm = mountList().vm as any
    await flushPromises()
    await setQuery({ view: 'workbench', filter: 'stale' })
    expect(vm.filterStale).toBe(true)
    expect(vm.viewMode).toBe('list')
    expect(hoisted.replace.mock.calls.map((c: any[]) => c[0].query)).toEqual([{ view: 'list', filter: 'stale' }])
    expect(hoisted.route.query).toEqual({ view: 'list', filter: 'stale' })
    expect(hoisted.listWorkpapers).toHaveBeenCalledTimes(1)
  })

  test('已在列表视图时跳到 ?view=workbench&filter=stale ⇒ 地址栏改成 view=list；之后取消勾选仍是列表', async () => {
    // 浏览器实测抓到：状态本来就是列表时「状态 → 地址栏」不触发，地址栏留着 view=workbench，
    // 取消勾选后按它跳回工作台（原先整页重挂，挂载时总会写回 view=list）
    hoisted.route.query = { view: 'list' }
    const vm = mountList().vm as any
    await flushPromises()
    await setQuery({ view: 'workbench', filter: 'stale' })
    expect(vm.viewMode).toBe('list')
    expect(hoisted.route.query).toEqual({ view: 'list', filter: 'stale' })
    expect(hoisted.replace).toHaveBeenCalledTimes(1)
    vm.filterStale = false
    await flushPromises()
    expect(hoisted.route.query).toEqual({ view: 'list' })
    expect(vm.viewMode).toBe('list')
  })

  test('后退到没有 ?filter 的地址 ⇒ 关掉待重算，视图不变', async () => {
    hoisted.route.query = { view: 'list', filter: 'stale' }
    const vm = mountList().vm as any
    await flushPromises()
    hoisted.replace.mockClear()
    await setQuery({ view: 'list' })
    expect(vm.filterStale).toBe(false)
    expect(vm.viewMode).toBe('list')
    expect(hoisted.replace).not.toHaveBeenCalled()
  })

  test('状态 → 地址栏 → 状态往返有界（点页签、勾待重算）', async () => {
    const vm = mountList().vm as any
    await flushPromises()
    vm.viewMode = 'lifecycle'
    await flushPromises()
    expect(hoisted.route.query).toEqual({ view: 'lifecycle' })
    vm.viewMode = 'list'
    await flushPromises()
    vm.filterStale = true
    await flushPromises()
    expect(hoisted.route.query).toEqual({ view: 'list', filter: 'stale' })
    expect(vm.viewMode).toBe('list')
    expect(hoisted.replace).toHaveBeenCalledTimes(3)
  })
})

describe('R7：浅层响应式 + 按 wp_index_id 合并', () => {
  test('两张清单不深层代理；合并取第一个匹配的底稿（与原先 find 一致）', async () => {
    hoisted.listWorkpapers.mockResolvedValue([
      { id: 'w1', wp_index_id: 'i1', assigned_to: 'u-first' },
      { id: 'w2', wp_index_id: 'i1', assigned_to: 'u-second', reviewer: 'r-second' },
      { id: 'w3', wp_index_id: 'i2', assigned_to: null, reviewer: 'r2' },
    ])
    hoisted.getWpIndex.mockResolvedValue([
      { id: 'i1', wp_code: 'D2', assigned_to: 'u-idx', reviewer: 'r-idx' },
      { id: 'i2', wp_code: 'D3', assigned_to: 'a-idx', reviewer: null },
      { id: 'i3', wp_code: 'D4', assigned_to: 'x', reviewer: 'y' },
    ])
    const vm = mountList().vm as any
    await flushPromises()
    expect(isReactive(vm.wpList)).toBe(false)
    expect(isReactive(vm.wpIndex)).toBe(false)
    expect(vm.wpIndex.map((i: any) => [i.id, i.assigned_to, i.reviewer])).toEqual([
      ['i1', 'u-first', 'r-idx'],
      ['i2', 'a-idx', 'r2'],
      ['i3', 'x', 'y'],
    ])
    expect(vm.wpIndexById.get('i2').wp_code).toBe('D3')
  })
})

describe('入口参数（spec wp-deeplink-locate-residual-closure 需求 2）', () => {
  test('?highlight= 到达：列表视图 + 定位目标；之后用户切视图不被强制回列表；同页换编码再定位一次', async () => {
    hoisted.route.query = { view: 'workbench', highlight: 'D2-1 应收账款' }
    const vm = mountList().vm as any
    await flushPromises()
    expect(vm.viewMode).toBe('list')
    expect(vm.locateTarget).toMatchObject({ code: 'D2-1' })
    const first = vm.locateTarget.seq
    expect(hoisted.route.query).toEqual({ view: 'list', highlight: 'D2-1 应收账款' })
    vm.viewMode = 'kanban'
    await flushPromises()
    expect(vm.viewMode).toBe('kanban')
    expect(hoisted.route.query).toEqual({ view: 'kanban', highlight: 'D2-1 应收账款' })
    expect(vm.locateTarget.seq).toBe(first)
    await setQuery({ view: 'kanban', wp_code: 'E1' })
    expect(vm.viewMode).toBe('list')
    expect(vm.locateTarget).toMatchObject({ code: 'E1' })
    expect(vm.locateTarget.seq).toBeGreaterThan(first)
  })

  test('?search= / ?wp_code= 与 ?highlight= 同样定位（取第一个）', async () => {
    hoisted.route.query = { search: 'G8' }
    const vm = mountList().vm as any
    await flushPromises()
    expect(vm.locateTarget).toMatchObject({ code: 'G8' })
    expect(vm.viewMode).toBe('list')
  })

  test('?cycle= 到达：按循环筛选（按循环取数）并切列表视图；非法值不理', async () => {
    hoisted.route.query = { cycle: 'd' }
    const vm = mountList().vm as any
    await flushPromises()
    expect(vm.filterCycle).toBe('D')
    expect(vm.viewMode).toBe('list')
    expect(hoisted.listWorkpapers.mock.calls.at(-1)[1]).toMatchObject({ audit_cycle: 'D' })
    await setQuery({ view: 'list', cycle: 'ZZ' })
    expect(vm.filterCycle).toBe('D')
  })

  test('?upload= 到达：打开增强导入，并从地址栏去掉 upload（刷新 / 后退不再弹）', async () => {
    hoisted.route.query = { upload: 'wp-1', view: 'list' }
    const vm = mountList().vm as any
    await flushPromises()
    expect(vm.showWpImportEnhanced).toBe(true)
    expect(hoisted.route.query).toEqual({ view: 'list' })
    vm.showWpImportEnhanced = false
    await setQuery({ view: 'list' })
    expect(vm.showWpImportEnhanced).toBe(false)
  })

  test('?assigned=me / unassigned：按编制人筛选（未分配不传给后端）', async () => {
    hoisted.route.query = { assigned: 'me' }
    const vm = mountList().vm as any
    await flushPromises()
    expect(vm.filterAssignee).toBe('u1')
    expect(hoisted.listWorkpapers.mock.calls.at(-1)[1]).toMatchObject({ assigned_to: 'u1' })
    await setQuery({ view: 'list', assigned: 'unassigned' })
    expect(vm.filterAssignee).toBe('__unassigned__')
    expect(hoisted.listWorkpapers.mock.calls.at(-1)[1].assigned_to).toBeUndefined()
  })

  test('?account=：只认本项目已生成的关联底稿（表级编码 / 没生成的跳过，多张时点名）；都没生成按映射第一张；没有关联不设目标', async () => {
    const info = vi.spyOn(ElMessage, 'info')
    hoisted.listWorkpapers.mockResolvedValue([{ id: 'w3', wp_index_id: 'i3' }, { id: 'w2', wp_index_id: 'i2' }])
    hoisted.getWpIndex.mockResolvedValue([{ id: 'i1', wp_code: 'D0' }, { id: 'i2', wp_code: 'D3' }, { id: 'i3', wp_code: 'D2' }])
    // 浏览器实测（【测试】项目，科目 1122）：映射给出 D2、D0、D2-2…D2-6 等 13 个编码，本项目只生成了 D2
    hoisted.mapping.mockResolvedValueOnce([{ wp_code: 'D0' }, { wp_code: 'D2' }, { wp_code: 'D2-2' }, { wp_code: 'D2' }, { wp_code: 'D3' }])
    hoisted.route.query = { account: '1122' }
    const vm = mountList().vm as any
    await flushPromises()
    expect(hoisted.mapping).toHaveBeenCalledWith('test-proj', '1122')
    expect(vm.locateTarget).toMatchObject({ code: 'D2' })
    expect(vm.viewMode).toBe('list')
    expect(info).toHaveBeenCalledWith('科目 1122 关联底稿 D2、D3，已定位到 D2')
    hoisted.mapping.mockResolvedValueOnce([{ wp_code: 'Z1' }, { wp_code: 'Z2' }])
    await setQuery({ view: 'list', account: '5555' })
    expect(vm.locateTarget).toMatchObject({ code: 'Z1' })
    const seq = vm.locateTarget.seq
    hoisted.mapping.mockResolvedValueOnce([])
    await setQuery({ view: 'list', account: '9999' })
    expect(vm.locateTarget.seq).toBe(seq)
    expect(info).toHaveBeenCalledTimes(1)
    info.mockRestore()
  })

  test('没有入口参数时行为不变（不设定位目标）', async () => {
    hoisted.route.query = { view: 'lifecycle' }
    const vm = mountList().vm as any
    await flushPromises()
    expect(vm.viewMode).toBe('lifecycle')
    expect(vm.locateTarget).toBeNull()
    expect(hoisted.replace).not.toHaveBeenCalled()
  })
})
