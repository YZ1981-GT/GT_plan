import { describe, test, expect, vi, beforeEach } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import { ref, computed, defineComponent, h, inject } from 'vue'
import { EDITOR_CONTEXT_KEY, type EditorContextData } from '@/composables/useEditorContext'

// ─── Mock 子 SFC 模块（避免 Univer SDK 解析） ────────────────────────────────
vi.mock('@/views/workpaper-editor/UniverEditorCore.vue', () => ({
  default: defineComponent({ name: 'UniverEditorCore', template: '<div class="stub-univer-editor-core" />' }),
}))
vi.mock('@/views/workpaper-editor/EditorBanners.vue', () => ({
  default: defineComponent({ name: 'EditorBanners', template: '<div class="stub-editor-banners" />' }),
}))
vi.mock('@/views/workpaper-editor/CycleDialogHost.vue', () => ({
  default: defineComponent({ name: 'CycleDialogHost', template: '<div class="stub-cycle-dialog-host" />' }),
}))
vi.mock('@/views/workpaper-editor/VersionHistoryDrawer.vue', () => ({
  default: defineComponent({ name: 'VersionHistoryDrawer', template: '<div class="stub-version-history-drawer" />' }),
}))
vi.mock('@/views/workpaper-editor/AuditNavDialog.vue', () => ({
  default: defineComponent({ name: 'AuditNavDialog', template: '<div class="stub-audit-nav-dialog" />' }),
}))
vi.mock('@/views/workpaper-editor/ReviewMarkDialog.vue', () => ({
  default: defineComponent({ name: 'ReviewMarkDialog', template: '<div class="stub-review-mark-dialog" />' }),
}))

/**
 * 🔴 2026-09-28 修：Shell 的主内容区（含 `UniverEditorCore` 及其余子 SFC）整体位于
 * `<WorkpaperCapabilityShell>`（`@/shell/formula/WorkpaperCapabilityShell.vue`）的
 * 默认插槽内，而 `shallowMount` 的**自动桩不渲染插槽** ⇒ 主内容区从未进入渲染树：
 *   · `findComponent({ name: 'UniverEditorCore' })` 恒为 false
 *   · 用 ChildProbe 顶替 UniverEditorCore 去验 inject 的那条恒拿不到 context
 *
 * 🔴 **`vi.mock` 解决不了这个** —— 实测：即便把该模块 mock 成会渲染 `<slot />` 的组件，
 * `shallowMount` 仍会把它再自动打成桩，渲染出的是 `<workpaper-capability-shell-stub>`。
 * 必须走 `global.stubs` 显式给一个渲染插槽的桩（见下方 `SLOT_RENDERING_STUBS`）。
 */
const SLOT_RENDERING_STUBS = {
  // 渲染默认插槽，否则主内容区整体不挂载
  WorkpaperCapabilityShell: { template: '<div class="stub-capability-shell"><slot /></div>' },
} as const

// ─── Mock 其他子组件（避免深层依赖解析） ─────────────────────────────────────
vi.mock('@/components/workpaper/GtWpRenderer.vue', () => ({
  default: defineComponent({ name: 'GtWpRenderer', template: '<div />' }),
}))
vi.mock('@/components/workpaper/WorkpaperSidePanel.vue', () => ({
  default: defineComponent({ name: 'WorkpaperSidePanel', template: '<div />' }),
}))
vi.mock('@/components/workpaper/ReviewLayerBadges.vue', () => ({
  default: defineComponent({ name: 'ReviewLayerBadges', template: '<div />' }),
}))
vi.mock('@/components/CellFormulaDetail.vue', () => ({
  default: defineComponent({ name: 'CellFormulaDetail', template: '<div />' }),
}))
vi.mock('@/components/time_machine/TimeMachineDrawer.vue', () => ({
  default: defineComponent({ name: 'TimeMachineDrawer', template: '<div />' }),
}))

// ─── Mock vue-router ─────────────────────────────────────────────────────────
const mockNext = vi.fn()
let routeLeaveGuard: ((to: any, from: any, next: any) => any) | null = null

vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: { projectId: 'proj-1', wpId: 'wp-1' },
    query: {},
  }),
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn().mockReturnValue(Promise.resolve()),
    back: vi.fn(),
  }),
  onBeforeRouteLeave: (guard: any) => {
    routeLeaveGuard = guard
  },
}))

// ─── Mock confirmLeave ───────────────────────────────────────────────────────
const mockConfirmLeave = vi.fn().mockResolvedValue(undefined)
vi.mock('@/utils/confirm', () => ({
  confirmLeave: (...args: any[]) => mockConfirmLeave(...args),
}))

// ─── Mock useAuditContext ────────────────────────────────────────────────────
vi.mock('@/composables/useAuditContext', () => ({
  useAuditContext: () => ({
    canEdit: computed(() => true),
    onContextChange: vi.fn(),
  }),
}))

// ─── Mock useProjectStore (P0-6.1) ──────────────────────────────────────────
vi.mock('@/stores/project', () => ({
  useProjectStore: () => ({
    projectId: 'proj-1',
    year: 2025,
    clientName: 'Test Corp',
    projectStatus: 'active',
    auditScope: 'standalone',
    roleInProject: null,
    currentProjectContext: {
      projectId: 'proj-1',
      projectName: 'Test Corp',
      year: 2025,
      applicableStandard: 'soe',
      auditScope: 'standalone',
      projectStatus: 'active',
      roleInProject: null,
    },
  }),
}))

// ─── Mock usePermissionMatrix (P0-6.1) ──────────────────────────────────────
vi.mock('@/composables/usePermissionMatrix', () => ({
  usePermissionMatrix: () => ({
    can: () => true,
    whyCannot: () => null,
    currentRole: computed(() => 'admin'),
    allowedOperations: computed(() => new Set()),
    canRole: () => true,
  }),
}))

// ─── Mock useCycleType ───────────────────────────────────────────────────────
vi.mock('@/composables/useCycleType', () => ({
  useCycleType: () => ({
    code: computed(() => ''),
    isBCycle: computed(() => false),
    isCCycle: computed(() => false),
    isDCycle: computed(() => false),
    isFCycle: computed(() => false),
    isGCycle: computed(() => false),
    isHCycle: computed(() => false),
    isICycle: computed(() => false),
    isKCycle: computed(() => false),
    isLCycle: computed(() => false),
    isMCycle: computed(() => false),
    isNCycle: computed(() => false),
  }),
}))

// ─── Mock useEditorMode ──────────────────────────────────────────────────────
vi.mock('@/composables/useEditorMode', () => ({
  useEditorMode: () => ({
    componentType: ref('univer'),
    useHtmlRenderer: ref(false),
    wpClassification: {
      load: vi.fn().mockResolvedValue(undefined),
      componentType: ref('skip'),
    },
    fetchComponentType: vi.fn().mockResolvedValue(undefined),
  }),
}))

// ─── Mock useEditorToolbar ───────────────────────────────────────────────────
vi.mock('@/composables/useEditorToolbar', () => ({
  useEditorToolbar: () => ({
    availableButtons: ref([]),
    dropdownItems: ref([]),
    handleAction: vi.fn(),
  }),
}))

// ─── Mock useEditorCycles ────────────────────────────────────────────────────
const noop = () => { /* noop */ }
const mockDialogEntry = { visible: ref(false), trigger: computed(() => false), onApplied: noop }
vi.mock('@/composables/useEditorCycles', () => ({
  useEditorCycles: () => ({
    cycleDialogs: {
      stocktake: { visible: ref(false), trigger: computed(() => false), onApplied: noop },
      valuation: { visible: ref(false), trigger: computed(() => false), loading: ref(false) },
      impairment: { visible: ref(false), trigger: computed(() => false), onApplied: noop },
      hStocktake: { visible: ref(false), trigger: computed(() => false), onApplied: noop },
      depreciationCalc: { visible: ref(false), trigger: computed(() => false), onApplied: noop },
      assetImpairment: { visible: ref(false), trigger: computed(() => false), onApplied: noop },
      goodwillImpairment: { visible: ref(false), trigger: computed(() => false), onApplied: noop },
      capitalizationCheck: { visible: ref(false), trigger: computed(() => false), onApplied: noop },
      amortizationCalc: { visible: ref(false), trigger: computed(() => false), section: computed(() => null), onApplied: noop },
      fairValueTest: { visible: ref(false), trigger: computed(() => false), instrumentType: computed(() => ''), onApplied: noop },
      eclCalc: { visible: ref(false), trigger: computed(() => false), instrumentType: computed(() => ''), onApplied: noop },
      classificationCheck: { visible: ref(false), trigger: computed(() => false), onApplied: noop },
      expenseAnalysis: { visible: ref(false), trigger: computed(() => false), onApplied: noop },
      impairmentSummary: { visible: ref(false), trigger: computed(() => false), onApplied: noop },
      interestCalc: { visible: ref(false), trigger: computed(() => false), onApplied: noop },
      bondAmortization: { visible: ref(false), trigger: computed(() => false), onApplied: noop },
      equityMovement: { visible: ref(false), trigger: computed(() => false), onApplied: noop },
      incomeTaxCalc: { visible: ref(false), trigger: computed(() => false), onApplied: noop },
    },
    fCycle: {},
    iCycle: {},
    gCycle: {},
    kCycle: {},
    lCycle: {},
    mCycle: {},
    nCycle: {},
  }),
}))

// ─── Mock useSheetNavFacade ──────────────────────────────────────────────────
// 🔴 2026-09-28 修：本 mock 原缺 `flatSheets`，而 Shell 有一条 `{ immediate: true }`
// 的 watch getter 直接读 `sheetNavFacade.flatSheets.value.map(...)`
// ⇒ 挂载即 `TypeError: Cannot read properties of undefined (reading 'value')`
// （WorkpaperEditor.vue:1121），本文件 **10 条测试全红**且持续至今。
// 根因是 mock 陈旧（facade 后来新增了 flatSheets），**不是生产代码缺陷**。
// 下方 `mock 与真实 facade 契约一致` 一组断言防它再次漂移。
vi.mock('@/composables/useSheetNavFacade', () => ({
  useSheetNavFacade: () => ({
    activeSheetId: computed(() => 'sheet-1'),
    sheets: ref([]),
    switchSheet: vi.fn(),
    flatSheets: computed(() => [] as Array<{ id: string; name: string }>),
    groups: ref([]),
    refresh: vi.fn(),
    bindUniverApi: vi.fn(),
    applyForeignCurrencyVisibility: vi.fn(),
  }),
}))

// ─── Mock useEditingLock ─────────────────────────────────────────────────────
vi.mock('@/composables/useEditingLock', () => ({
  useEditingLock: () => ({
    locked: ref(false),
    lockedBy: ref(null),
    acquire: vi.fn(),
    release: vi.fn(),
  }),
}))

// ─── Mock useStepMapping ─────────────────────────────────────────────────────
vi.mock('@/composables/useStepMapping', () => ({
  useStepMapping: () => ({
    data: ref({ steps: [] }),
    currentStepIndex: ref(0),
    totalSteps: ref(0),
    currentStep: ref(null),
    currentTargetSheets: ref([]),
    prevStep: vi.fn(),
    nextStep: vi.fn(),
    loadMapping: vi.fn(),
  }),
}))

// ─── Mock useStaleImpact ─────────────────────────────────────────────────────
vi.mock('@/composables/useStaleImpact', () => ({
  useStaleImpact: () => ({
    items: ref([]),
    loading: ref(false),
    hasStale: computed(() => false),
  }),
}))

// ─── Mock usePrerequisiteStatus ──────────────────────────────────────────────
vi.mock('@/composables/usePrerequisiteStatus', () => ({
  usePrerequisiteStatus: () => ({
    banner: ref(null),
  }),
}))

// ─── Mock useWorkpaperRefresh ────────────────────────────────────────────────
vi.mock('@/composables/useWorkpaperRefresh', () => ({
  useWorkpaperRefresh: () => ({}),
}))

// ─── Mock useWorkpaperReviewMarkers ──────────────────────────────────────────
vi.mock('@/composables/useWorkpaperReviewMarkers', () => ({
  useWorkpaperReviewMarkers: () => ({
    markers: ref([]),
    loading: ref(false),
  }),
}))

// ─── Mock services ───────────────────────────────────────────────────────────
vi.mock('@/services/workpaperApi', () => ({
  getWorkpaper: vi.fn().mockResolvedValue(null),
}))

vi.mock('@/services/apiProxy', () => ({
  api: { post: vi.fn().mockResolvedValue({}), get: vi.fn().mockResolvedValue({}) },
}))

// ─── Mock utils ──────────────────────────────────────────────────────────────
vi.mock('@/utils/errorHandler', () => ({
  handleApiError: vi.fn(),
}))

vi.mock('@/utils/eventBus', () => ({
  eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() },
}))

// ─── Mock stores ─────────────────────────────────────────────────────────────
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    role: 'admin',
    user: { id: 'u1', role: 'admin', username: 'test' },
    token: 'fake-token',
  }),
}))

// ─── Import Shell ────────────────────────────────────────────────────────────
import WorkpaperEditor from '@/views/WorkpaperEditor.vue'

describe('WorkpaperEditorShell', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeLeaveGuard = null
  })

  function mountShell() {
    return shallowMount(WorkpaperEditor, {
      global: {
        stubs: {
          // 🔴 必须先放渲染插槽的桩：主内容区在 WorkpaperCapabilityShell 的默认插槽内，
          // 用自动桩会让下面所有子 SFC 的 findComponent 断言恒 false（见文件头说明）。
          ...SLOT_RENDERING_STUBS,

          // 子 SFC stubs
          UniverEditorCore: defineComponent({
            name: 'UniverEditorCore',
            setup() { return () => h('div', { class: 'stub-univer-editor-core' }) },
          }),
          CycleDialogHost: defineComponent({
            name: 'CycleDialogHost',
            setup() { return () => h('div', { class: 'stub-cycle-dialog-host' }) },
          }),
          EditorBanners: defineComponent({
            name: 'EditorBanners',
            setup() { return () => h('div', { class: 'stub-editor-banners' }) },
          }),
          VersionHistoryDrawer: defineComponent({
            name: 'VersionHistoryDrawer',
            setup() { return () => h('div', { class: 'stub-version-history-drawer' }) },
          }),
          AuditNavDialog: defineComponent({
            name: 'AuditNavDialog',
            setup() { return () => h('div', { class: 'stub-audit-nav-dialog' }) },
          }),
          ReviewMarkDialog: defineComponent({
            name: 'ReviewMarkDialog',
            setup() { return () => h('div', { class: 'stub-review-mark-dialog' }) },
          }),
          // 其他组件 stubs
          GtWpRenderer: defineComponent({
            name: 'GtWpRenderer',
            setup() { return () => h('div', { class: 'stub-gt-wp-renderer' }) },
          }),
          WorkpaperSidePanel: defineComponent({
            name: 'WorkpaperSidePanel',
            setup() { return () => h('div') },
          }),
          ReviewLayerBadges: defineComponent({
            name: 'ReviewLayerBadges',
            setup() { return () => h('div') },
          }),
          CellFormulaDetail: defineComponent({
            name: 'CellFormulaDetail',
            setup() { return () => h('div') },
          }),
          TimeMachineDrawer: defineComponent({
            name: 'TimeMachineDrawer',
            setup() { return () => h('div') },
          }),
          ElButton: { template: '<button><slot /></button>' },
          ElButtonGroup: { template: '<div><slot /></div>' },
          ElTag: { template: '<span><slot /></span>' },
          ElTooltip: { template: '<div><slot /></div>' },
          ElDropdown: { template: '<div><slot /></div>' },
          ElDropdownMenu: { template: '<div><slot /></div>' },
          ElDropdownItem: { template: '<div><slot /></div>' },
          ElBadge: { template: '<div><slot /></div>' },
          ElDrawer: { template: '<div><slot /></div>' },
          ElIcon: { template: '<span><slot /></span>' },
          Loading: { template: '<span />' },
        },
        directives: {
          permission: () => { /* noop */ },
        },
      },
    })
  }

  describe('子 SFC 编排正确性', () => {
    test('UniverEditorCore 渲染', async () => {
      const wrapper = mountShell()
      await flushPromises()
      expect(wrapper.findComponent({ name: 'UniverEditorCore' }).exists()).toBe(true)
    })

    test('CycleDialogHost 渲染', async () => {
      const wrapper = mountShell()
      await flushPromises()
      // CycleDialogHost has v-if="wpDetail", which is null by default
      // Set wpDetail to trigger rendering
      const vm = wrapper.vm as any
      vm.wpDetail = { wp_code: 'D2', wp_name: 'Test', status: 'draft' }
      await flushPromises()
      expect(wrapper.findComponent({ name: 'CycleDialogHost' }).exists()).toBe(true)
    })

    test('EditorBanners 渲染', async () => {
      const wrapper = mountShell()
      await flushPromises()
      expect(wrapper.findComponent({ name: 'EditorBanners' }).exists()).toBe(true)
    })

    test('VersionHistoryDrawer 渲染', async () => {
      const wrapper = mountShell()
      await flushPromises()
      expect(wrapper.findComponent({ name: 'VersionHistoryDrawer' }).exists()).toBe(true)
    })

    test('AuditNavDialog 渲染', async () => {
      const wrapper = mountShell()
      await flushPromises()
      expect(wrapper.findComponent({ name: 'AuditNavDialog' }).exists()).toBe(true)
    })

    test('ReviewMarkDialog 渲染', async () => {
      const wrapper = mountShell()
      await flushPromises()
      expect(wrapper.findComponent({ name: 'ReviewMarkDialog' }).exists()).toBe(true)
    })
  })

  describe('provide(EDITOR_CONTEXT_KEY) 注入正确', () => {
    test('子组件可通过 inject 获取 EditorContext', async () => {
      let injectedCtx: EditorContextData | undefined

      const ChildProbe = defineComponent({
        name: 'ChildProbe',
        setup() {
          injectedCtx = inject(EDITOR_CONTEXT_KEY)
          return () => h('div', { class: 'probe' })
        },
      })

      // Mount Shell with a child probe that injects the context
      const wrapper = shallowMount(WorkpaperEditor, {
        global: {
          stubs: {
            // 同上：不渲染插槽则 ChildProbe 永不挂载，inject 断言恒失败
            ...SLOT_RENDERING_STUBS,
            UniverEditorCore: ChildProbe,
            CycleDialogHost: { template: '<div />' },
            EditorBanners: { template: '<div />' },
            VersionHistoryDrawer: { template: '<div />' },
            AuditNavDialog: { template: '<div />' },
            ReviewMarkDialog: { template: '<div />' },
            GtWpRenderer: { template: '<div />' },
            WorkpaperSidePanel: { template: '<div />' },
            ReviewLayerBadges: { template: '<div />' },
            CellFormulaDetail: { template: '<div />' },
            TimeMachineDrawer: { template: '<div />' },
            ElButton: { template: '<button><slot /></button>' },
            ElButtonGroup: { template: '<div><slot /></div>' },
            ElTag: { template: '<span><slot /></span>' },
            ElTooltip: { template: '<div><slot /></div>' },
            ElDropdown: { template: '<div><slot /></div>' },
            ElDropdownMenu: { template: '<div><slot /></div>' },
            ElDropdownItem: { template: '<div><slot /></div>' },
            ElBadge: { template: '<div><slot /></div>' },
            ElDrawer: { template: '<div><slot /></div>' },
            ElIcon: { template: '<span><slot /></span>' },
            Loading: { template: '<span />' },
          },
          directives: {
            permission: () => { /* noop */ },
          },
        },
      })
      await flushPromises()

      // Verify the injected context has the expected shape
      expect(injectedCtx).toBeDefined()
      expect(injectedCtx!.projectId).toBeDefined()
      expect(injectedCtx!.projectId.value).toBe('proj-1')
      expect(injectedCtx!.wpId).toBeDefined()
      expect(injectedCtx!.wpId.value).toBe('wp-1')
      expect(injectedCtx!.wpDetail).toBeDefined()
      expect(injectedCtx!.canEdit).toBeDefined()
      expect(injectedCtx!.componentType).toBeDefined()
      expect(injectedCtx!.cycleType).toBeDefined()
      expect(injectedCtx!.cycleDialogs).toBeDefined()
      expect(injectedCtx!.sheetNavActiveId).toBeDefined()

      wrapper.unmount()
    })
  })

  describe('onBeforeRouteLeave dirty 检查', () => {
    test('dirty=false 时直接放行（不弹 confirm）', async () => {
      mountShell()
      await flushPromises()

      expect(routeLeaveGuard).not.toBeNull()

      // Call the guard with dirty=false (default)
      await routeLeaveGuard!({}, {}, mockNext)
      expect(mockConfirmLeave).not.toHaveBeenCalled()
      expect(mockNext).toHaveBeenCalledWith()
    })

    test('dirty=true 时弹 confirmLeave，用户确认后放行', async () => {
      const wrapper = mountShell()
      await flushPromises()

      // Set dirty=true
      const vm = wrapper.vm as any
      vm.dirty = true
      await flushPromises()

      expect(routeLeaveGuard).not.toBeNull()

      // confirmLeave resolves → user confirmed
      mockConfirmLeave.mockResolvedValueOnce(undefined)
      await routeLeaveGuard!({}, {}, mockNext)

      expect(mockConfirmLeave).toHaveBeenCalledWith('底稿')
      expect(mockNext).toHaveBeenCalledWith()
    })

    test('dirty=true 时弹 confirmLeave，用户取消后阻止离开', async () => {
      const wrapper = mountShell()
      await flushPromises()

      // Set dirty=true
      const vm = wrapper.vm as any
      vm.dirty = true
      await flushPromises()

      expect(routeLeaveGuard).not.toBeNull()

      // confirmLeave rejects → user cancelled
      mockConfirmLeave.mockRejectedValueOnce(new Error('cancelled'))
      await routeLeaveGuard!({}, {}, mockNext)

      expect(mockConfirmLeave).toHaveBeenCalledWith('底稿')
      expect(mockNext).toHaveBeenCalledWith(false)
    })
  })
})
