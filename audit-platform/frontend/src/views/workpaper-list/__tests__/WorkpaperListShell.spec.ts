import { describe, test, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref, computed, defineComponent, h } from 'vue'
import { WP_LIST_CONTEXT_KEY, createMockContext } from '@/composables/useWorkpaperListContext'

// ─── Mock 角色 ─────────────────────────────────────────────────────────────────
let mockRole = 'admin'
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    role: mockRole,
    user: { id: 'u1', role: mockRole, username: 'test' },
    token: 'fake-token',
  }),
}))

// ─── Mock vue-router ─────────────────────────────────────────────────────────
const mockReplace = vi.fn().mockReturnValue(Promise.resolve())
const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: { projectId: 'test-proj' },
    query: { view: 'workbench' },
  }),
  useRouter: () => ({
    replace: mockReplace,
    push: mockPush,
  }),
}))

// ─── Mock useAuditContext ────────────────────────────────────────────────────
vi.mock('@/composables/useAuditContext', () => ({
  useAuditContext: () => ({ onContextChange: vi.fn() }),
}))

// ─── Mock services ───────────────────────────────────────────────────────────
vi.mock('@/services/workpaperApi', () => ({
  listWorkpapers: vi.fn().mockResolvedValue([]),
  getWpIndex: vi.fn().mockResolvedValue([]),
  downloadWorkpaperPack: vi.fn().mockResolvedValue(undefined),
  downloadWorkpaper: vi.fn(),
}))

vi.mock('@/services/commonApi', () => ({
  listUsers: vi.fn().mockResolvedValue([]),
}))

vi.mock('@/services/apiProxy', () => ({
  api: { post: vi.fn().mockResolvedValue({}), put: vi.fn().mockResolvedValue({}) },
}))

vi.mock('@/utils/errorHandler', () => ({
  handleApiError: vi.fn(),
}))

vi.mock('@/utils/eventBus', () => ({
  eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() },
}))

// ─── Stub 子 SFC ─────────────────────────────────────────────────────────────
const WorkbenchStub = defineComponent({
  name: 'WorkpaperWorkbenchView',
  props: { projectId: String, year: Number },
  emits: ['navigate', 'refresh', 'mutate'],
  setup(_, { emit }) { return () => h('div', { class: 'stub-workbench' }, '工作台') },
})

const BoardStub = defineComponent({
  name: 'WorkpaperBoardView',
  props: { projectId: String, year: Number },
  emits: ['navigate', 'refresh', 'mutate'],
  setup() { return () => h('div', { class: 'stub-board' }, '看板') },
})

const LifecycleStub = defineComponent({
  name: 'WorkpaperLifecycleView',
  props: { projectId: String, year: Number },
  emits: ['navigate', 'refresh', 'mutate'],
  setup() { return () => h('div', { class: 'stub-lifecycle' }, '生命周期') },
})

const GraphStub = defineComponent({
  name: 'WorkpaperDependencyGraph',
  props: { projectId: String, year: Number },
  emits: ['navigate', 'refresh', 'mutate'],
  setup() { return () => h('div', { class: 'stub-graph' }, '依赖图') },
})

const MatrixStub = defineComponent({
  name: 'WorkpaperDelegationMatrix',
  props: { projectId: String, year: Number },
  emits: ['navigate', 'refresh', 'mutate'],
  setup() { return () => h('div', { class: 'stub-matrix' }, '委派矩阵') },
})

// ─── Import Shell ────────────────────────────────────────────────────────────
import WorkpaperList from '@/views/WorkpaperList.vue'

describe('WorkpaperListShell', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRole = 'admin'
  })

  function mountShell(options: { viewMode?: string } = {}) {
    const ctx = createMockContext({
      viewMode: ref(options.viewMode || 'workbench'),
      wpIndex: ref([]),
      wpList: ref([]),
      loading: ref(false),
    })

    return mount(WorkpaperList, {
      global: {
        stubs: {
          WorkpaperWorkbenchView: WorkbenchStub,
          WorkpaperBoardView: BoardStub,
          WorkpaperLifecycleView: LifecycleStub,
          WorkpaperDependencyGraph: GraphStub,
          WorkpaperDelegationMatrix: MatrixStub,
          GtPageHeader: { template: '<div><slot name="actions" /></div>' },
          GtToolbar: { template: '<div><slot name="left" /><slot name="right" /></div>' },
          ArchivedBanner: { template: '<div />' },
          BatchActionBar: { template: '<div />' },
          BatchAssignDialog: { template: '<div />' },
          UnifiedImportDialog: { template: '<div />' },
          ElRadioGroup: { template: '<div class="el-radio-group"><slot /></div>', props: ['modelValue'] },
          ElRadioButton: { template: '<button class="el-radio-button">{{ $attrs.value }}</button>', props: ['value'] },
          ElButton: { template: '<button><slot /></button>' },
          ElInput: { template: '<input />' },
          ElSelect: { template: '<select><slot /></select>' },
          ElOption: { template: '<option />' },
          ElProgress: { template: '<div />' },
          ElPagination: { template: '<div />' },
        },
      },
    })
  }

  describe('viewMode 切换', () => {
    test('list/workbench/guide 都映射到 WorkpaperWorkbenchView', async () => {
      const wrapper = mountShell({ viewMode: 'workbench' })
      await flushPromises()

      // Shell 内部 currentViewComponent 对 list/workbench/guide 都指向 WorkbenchView
      const vm = wrapper.vm as any
      expect(vm.currentViewComponent).toBeDefined()

      // 验证 list/workbench/guide 共享同一 key
      vm.viewMode = 'list'
      await flushPromises()
      const keyList = vm.currentViewKey
      vm.viewMode = 'workbench'
      await flushPromises()
      const keyWb = vm.currentViewKey
      vm.viewMode = 'guide'
      await flushPromises()
      const keyGuide = vm.currentViewKey

      expect(keyList).toBe('workbench')
      expect(keyWb).toBe('workbench')
      expect(keyGuide).toBe('workbench')
    })

    test('kanban 映射到 WorkpaperBoardView', async () => {
      const wrapper = mountShell({ viewMode: 'workbench' })
      await flushPromises()
      const vm = wrapper.vm as any
      vm.viewMode = 'kanban'
      await flushPromises()
      expect(vm.currentViewKey).toBe('kanban')
    })

    test('lifecycle 映射到 WorkpaperLifecycleView', async () => {
      const wrapper = mountShell({ viewMode: 'workbench' })
      await flushPromises()
      const vm = wrapper.vm as any
      vm.viewMode = 'lifecycle'
      await flushPromises()
      expect(vm.currentViewKey).toBe('lifecycle')
    })

    test('graph 映射到 WorkpaperDependencyGraph', async () => {
      const wrapper = mountShell({ viewMode: 'workbench' })
      await flushPromises()
      const vm = wrapper.vm as any
      vm.viewMode = 'graph'
      await flushPromises()
      expect(vm.currentViewKey).toBe('graph')
    })

    test('matrix 映射到 WorkpaperDelegationMatrix', async () => {
      const wrapper = mountShell({ viewMode: 'workbench' })
      await flushPromises()
      const vm = wrapper.vm as any
      vm.viewMode = 'matrix'
      await flushPromises()
      expect(vm.currentViewKey).toBe('matrix')
    })
  })

  describe('非法 viewMode 回退', () => {
    test('非法 viewMode 回退到 workbench', async () => {
      const wrapper = mountShell({ viewMode: 'workbench' })
      await flushPromises()
      const vm = wrapper.vm as any
      vm.viewMode = 'invalid-mode'
      await flushPromises()
      expect(vm.viewMode).toBe('workbench')
    })
  })

  describe('keep-alive 实例复用', () => {
    test('切走再切回 mount 次数 = 1', async () => {
      const wrapper = mountShell({ viewMode: 'workbench' })
      await flushPromises()
      const vm = wrapper.vm as any

      // visitedViews 初始包含 WorkpaperWorkbenchView
      expect(vm.visitedViews).toContain('WorkpaperWorkbenchView')

      // 切到 kanban
      vm.viewMode = 'kanban'
      await flushPromises()
      expect(vm.visitedViews).toContain('WorkpaperBoardView')

      // 切回 workbench
      vm.viewMode = 'workbench'
      await flushPromises()

      // visitedViews 中 WorkpaperWorkbenchView 只出现一次
      const wbCount = vm.visitedViews.filter((n: string) => n === 'WorkpaperWorkbenchView').length
      expect(wbCount).toBe(1)
    })
  })

  describe('角色 Tab 可见性', () => {
    test('auditor 隐藏 DelegationMatrix Tab', async () => {
      mockRole = 'auditor'
      const wrapper = mountShell()
      await flushPromises()
      const vm = wrapper.vm as any
      const tabValues = vm.visibleTabs.map((t: any) => t.value)
      expect(tabValues).not.toContain('matrix')
    })

    test('qc 隐藏 DelegationMatrix Tab', async () => {
      mockRole = 'qc'
      const wrapper = mountShell()
      await flushPromises()
      const vm = wrapper.vm as any
      const tabValues = vm.visibleTabs.map((t: any) => t.value)
      expect(tabValues).not.toContain('matrix')
    })

    test('admin 显示全部 Tab（含 matrix）', async () => {
      mockRole = 'admin'
      const wrapper = mountShell()
      await flushPromises()
      const vm = wrapper.vm as any
      const tabValues = vm.visibleTabs.map((t: any) => t.value)
      expect(tabValues).toContain('matrix')
      expect(tabValues.length).toBeGreaterThanOrEqual(5)
    })

    test('partner 显示全部 Tab', async () => {
      mockRole = 'partner'
      const wrapper = mountShell()
      await flushPromises()
      const vm = wrapper.vm as any
      const tabValues = vm.visibleTabs.map((t: any) => t.value)
      expect(tabValues).toContain('matrix')
    })

    test('manager 显示全部 Tab', async () => {
      mockRole = 'manager'
      const wrapper = mountShell()
      await flushPromises()
      const vm = wrapper.vm as any
      const tabValues = vm.visibleTabs.map((t: any) => t.value)
      expect(tabValues).toContain('matrix')
    })
  })
})
