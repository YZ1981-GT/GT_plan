/**
 * 底稿管理页的审计年度：路由 ?year= > 本项目审计年度 > 去年（spec formula-fetch-and-wp-generation-defect-closure，
 * 浏览器实测发现）。
 *
 * 原先缺省取今年：从编辑器「返回」等不带 ?year= 的入口进来，生成底稿 / 刷新全部公式都按今年发请求
 * （2025 年度项目在 2026 年 → 2026：公式推送拒绝「只作用于项目审计年度」，生成的底稿绑不上数据集）。
 * 子视图（工作台 / 看板 …）经 :year 拿到的也是这个年度。
 */
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { computed, defineComponent, h, ref } from 'vue'
import { createMockContext } from '@/composables/useWorkpaperListContext'

const { mockHttpGet } = vi.hoisted(() => ({ mockHttpGet: vi.fn() }))
let mockQuery: Record<string, string> = {}

vi.mock('@/utils/http', () => ({ default: { get: mockHttpGet, post: vi.fn() } }))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ role: 'admin', user: { id: 'u1', role: 'admin', username: 'test' }, token: 't' }),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'test-proj' }, query: mockQuery }),
  useRouter: () => ({ replace: vi.fn().mockResolvedValue(undefined), push: vi.fn() }),
}))
vi.mock('@/composables/useAuditContext', () => ({ useAuditContext: () => ({ onContextChange: vi.fn() }) }))
vi.mock('@/stores/project', () => ({
  useProjectStore: () => ({ projectId: 'test-proj', year: null, currentProjectContext: { projectId: 'test-proj' } }),
}))
vi.mock('@/composables/usePermissionMatrix', () => ({
  usePermissionMatrix: () => ({
    can: () => true, whyCannot: () => null, currentRole: computed(() => 'admin'),
    allowedOperations: computed(() => new Set()), canRole: () => true,
  }),
}))
vi.mock('@/stores/roleContext', () => ({ useRoleContextStore: () => ({ canEditInProject: true }) }))
vi.mock('@/services/workpaperApi', () => ({
  listWorkpapers: vi.fn().mockResolvedValue([]),
  getWpIndex: vi.fn().mockResolvedValue([]),
  downloadWorkpaperPack: vi.fn().mockResolvedValue(undefined),
  downloadWorkpaper: vi.fn(),
}))
vi.mock('@/services/commonApi', () => ({ listUsers: vi.fn().mockResolvedValue([]) }))
vi.mock('@/services/apiProxy', () => ({ api: { post: vi.fn().mockResolvedValue({}), put: vi.fn().mockResolvedValue({}) } }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() } }))

// 子视图是 defineAsyncComponent 动态导入的：按模块替换（按名字 stub 拦不到异步包装）
vi.mock('@/views/workpaper-list/WorkpaperWorkbenchView.vue', () => ({
  __esModule: true,  // defineAsyncComponent 据此取 default（否则把模块对象本身当组件读 name）
  default: defineComponent({
    name: 'WorkpaperWorkbenchView',
    props: { projectId: String, year: Number },
    setup() { return () => h('div', { class: 'stub-workbench' }) },
  }),
}))

import WorkpaperList from '@/views/WorkpaperList.vue'

function mountList() {
  createMockContext({ viewMode: ref('workbench'), wpIndex: ref([]), wpList: ref([]), loading: ref(false) })
  const plain = { template: '<div><slot /><slot name="actions" /><slot name="left" /><slot name="right" /></div>' }
  return mount(WorkpaperList, {
    global: {
      stubs: {
        WorkpaperBoardView: true, WorkpaperLifecycleView: true, WorkpaperDependencyGraph: true, WorkpaperDelegationMatrix: true,
        GtPageHeader: plain, GtToolbar: plain, ArchivedBanner: true, ConsolLockedBanner: true, BatchActionBar: true,
        BatchAssignDialog: true, UnifiedImportDialog: true, WpImportDialog: true, WpBatchExportDialog: true, WpBulkDialog: true,
        WpTemplateCopyDialog: true, WorkpaperTrimDialog: true, GtCustomWpBatchDialog: true,
        ElRadioGroup: plain, ElRadioButton: true, ElButton: plain, ElInput: true, ElSelect: plain, ElOption: true,
        ElProgress: true, ElPagination: true, ElDropdown: plain, ElDropdownMenu: plain, ElDropdownItem: plain,
        ElIcon: plain, ElTooltip: plain, ElAlert: true, ElTag: plain, ElBadge: plain,
      },
    },
  })
}

describe('底稿管理页按项目审计年度发请求', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-23T10:00:00Z'))
    mockHttpGet.mockReset()
    mockQuery = {}
  })
  afterEach(() => { vi.useRealTimers() })

  test('路由没带 ?year=：用本项目的审计年度（不是今年）', async () => {
    mockHttpGet.mockResolvedValue({ data: { name: '某项目_2024', audit_year: 2024 } })
    const wrapper = mountList()
    await flushPromises()
    expect(mockHttpGet).toHaveBeenCalledWith('/api/projects/test-proj')
    expect((wrapper.vm as any).currentYear).toBe(2024)
    expect(wrapper.findComponent({ name: 'WorkpaperWorkbenchView' }).props('year')).toBe(2024)
    wrapper.unmount()
  })

  test('路由带了 ?year=：以路由为准', async () => {
    mockQuery = { year: '2023' }
    mockHttpGet.mockResolvedValue({ data: { name: '某项目_2024', audit_year: 2024 } })
    const wrapper = mountList()
    await flushPromises()
    expect((wrapper.vm as any).currentYear).toBe(2023)
    wrapper.unmount()
  })

  test('项目信息取不到：保持 null，不猜上一日历年', async () => {
    mockHttpGet.mockRejectedValue(new Error('network'))
    const wrapper = mountList()
    await flushPromises()
    expect((wrapper.vm as any).currentYear).toBeNull()
    wrapper.unmount()
  })
})
