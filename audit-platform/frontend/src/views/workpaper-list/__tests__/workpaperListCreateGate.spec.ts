/**
 * 底稿管理页「生成底稿」「批量自定义底稿」入口按本项目编辑权限显示（spec formula-fetch-followup-defect-closure R4.2）。
 *
 * 后端门禁：两个生成端点与新建自定义底稿三个端点挂 `require_project_access("edit")`（质控 / EQCR 是 review 级，
 * 非成员 403；归档项目 423）。入口原先对所有角色可见 ⇒ 没有编辑权限的人点了必被拒。
 * 现行：`useRoleContextStore().canEditInProject`（/api/role-context/project/{id} 的 permission_level，admin → edit）
 * 且项目未归档才显示；批量自定义底稿另受原有的管理角色门控。
 */
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { computed, defineComponent, h, reactive, ref } from 'vue'
import { createMockContext } from '@/composables/useWorkpaperListContext'

const roleContext = reactive({ canEditInProject: true })
const project = reactive({
  projectId: 'test-proj', year: 2025, projectStatus: 'execution',
  currentProjectContext: { projectId: 'test-proj' },
})

vi.mock('@/utils/http', () => ({ default: { get: vi.fn().mockResolvedValue({ data: { audit_year: 2025 } }), post: vi.fn() } }))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ role: 'manager', user: { id: 'u1', role: 'manager', username: 'test' }, token: 't' }),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'test-proj' }, query: {} }),
  useRouter: () => ({ replace: vi.fn().mockResolvedValue(undefined), push: vi.fn() }),
}))
vi.mock('@/composables/useAuditContext', () => ({ useAuditContext: () => ({ onContextChange: vi.fn() }) }))
vi.mock('@/stores/project', () => ({ useProjectStore: () => project }))
vi.mock('@/stores/roleContext', () => ({ useRoleContextStore: () => roleContext }))
vi.mock('@/composables/usePermissionMatrix', () => ({
  usePermissionMatrix: () => ({
    can: () => true, whyCannot: () => null, currentRole: computed(() => 'manager'),
    allowedOperations: computed(() => new Set()), canRole: () => true,
  }),
}))
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
  __esModule: true,
  default: defineComponent({ name: 'WorkpaperWorkbenchView', props: { projectId: String, year: Number }, setup: () => () => h('div') }),
}))

import WorkpaperList from '@/views/WorkpaperList.vue'

function mountList() {
  createMockContext({ viewMode: ref('workbench'), wpIndex: ref([]), wpList: ref([]), loading: ref(false) })
  const plain = { template: '<div><slot /><slot name="actions" /><slot name="left" /><slot name="right" /></div>' }
  return mount(WorkpaperList, {
    global: {
      stubs: {
        WorkpaperWorkbenchView: true, WorkpaperBoardView: true, WorkpaperLifecycleView: true, WorkpaperDependencyGraph: true,
        WorkpaperDelegationMatrix: true, GtPageHeader: plain, GtToolbar: plain, ArchivedBanner: true, ConsolLockedBanner: true,
        BatchActionBar: true, BatchAssignDialog: true, UnifiedImportDialog: true, WpImportDialog: true, WpBatchExportDialog: true,
        WpBulkDialog: true, WpTemplateCopyDialog: true, WorkpaperTrimDialog: true, GtCustomWpBatchDialog: true,
        ElRadioGroup: plain, ElRadioButton: true, ElButton: plain, ElInput: true, ElSelect: plain, ElOption: true,
        ElProgress: true, ElPagination: true, ElDropdown: plain, ElDropdownMenu: plain, ElDropdownItem: plain,
        ElIcon: plain, ElTooltip: plain, ElAlert: true, ElTag: plain, ElBadge: plain, ElCheckbox: plain,
      },
    },
  })
}

async function entries() {
  const wrapper = mountList()
  await flushPromises()
  const text = wrapper.text()
  const got = { generate: text.includes('生成底稿'), customBatch: text.includes('批量自定义底稿'), copy: text.includes('模板复制') }
  wrapper.unmount()
  return got
}

describe('生成底稿 / 新建自定义底稿入口按本项目编辑权限显示', () => {
  beforeEach(() => {
    roleContext.canEditInProject = true
    project.projectStatus = 'execution'
  })

  test('有编辑权限、项目未归档：两个入口都在', async () => {
    expect(await entries()).toEqual({ generate: true, customBatch: true, copy: true })
  })

  test('没有编辑权限（复核级 / 只读 / 非成员）：两个入口都不显示，其余管理入口不受影响', async () => {
    roleContext.canEditInProject = false
    expect(await entries()).toEqual({ generate: false, customBatch: false, copy: true })
  })

  test('项目已归档：即使有编辑权限也不显示（后端 423）', async () => {
    project.projectStatus = 'archived'
    expect(await entries()).toEqual({ generate: false, customBatch: false, copy: true })
  })
})
