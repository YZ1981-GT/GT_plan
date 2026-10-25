/**
 * 后台合并期间整张底稿只读（spec oo-return-to-form-dead-end-and-save-speed R4.4）。
 *
 * 判据看真实落点：渲染器把 `effectiveReadonly` 传给动态组件、编制表头与 scaffold；横幅只按 wpId 读登记。
 * 合并中 ⇒ 只读 + 横幅；失败 ⇒ 解除只读、横幅留着；注销 ⇒ 横幅消失；别的底稿的登记不影响本底稿。
 */
import { computed, defineComponent, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { scaffoldSpy } = vi.hoisted(() => ({ scaffoldSpy: vi.fn() }))

vi.mock('@/components/workpaper/composables/useWorkpaperScaffold', () => ({
  useWorkpaperScaffold: scaffoldSpy,
}))
vi.mock('@/composables/useWpRenderer', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/composables/useWpRenderer')>()
  return { ...actual, useWpRenderer: vi.fn() }
})
vi.mock('@/composables/useCellLocate', () => ({
  useCellLocate: () => ({ locateCell: vi.fn() }),
}))
vi.mock('@/utils/eventBus', () => ({
  eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
}))
vi.mock('@/stores/project', () => ({
  useProjectStore: () => ({
    projectId: 'project-1',
    auditYear: 2025,
    year: 2025,
    loadProjectContext: vi.fn(),
  }),
}))

const TestRenderer = defineComponent({
  name: 'TestRenderer',
  props: {
    wpId: String,
    projectId: String,
    wpCode: String,
    year: Number,
    sheetName: String,
    readonly: Boolean,
  },
  template: '<div data-test="dynamic-renderer" />',
})

vi.mock('@/components/workpaper/htmlRendererRegistry', () => ({
  getRendererEntry: (componentType: string) =>
    componentType === 'test-standard'
      ? { component: TestRenderer, contextProps: 'standard' }
      : undefined,
  getSheetIcon: () => '📄',
  getContextPropsStrategy: (componentType: string) =>
    componentType === 'test-standard' ? 'standard' : 'none',
}))

import { useWpRenderer } from '@/composables/useWpRenderer'
import GtWpRenderer from './GtWpRenderer.vue'
import WorkpaperBackgroundMergeBanner from './sync/WorkpaperBackgroundMergeBanner.vue'
import { clearBackgroundMerges, registerBackgroundMerge } from './sync/backgroundMergeRegistry'

function makeConfig() {
  return {
    wp_id: 'wp-1',
    wp_code: 'D2',
    project_id: 'project-1',
    audit_year: 2025,
    template_version: 'v-test',
    sheets: [
      {
        sheet_name: '审定表D2-1',
        sheet_code: 'D2-1',
        sheet_code_reason: 'embedded_code',
        whole_workbook: false,
        componentType: 'test-standard',
        schema: {},
        html_data: {},
        cross_refs: [],
      },
    ],
  }
}

function entry(wpId: string) {
  return {
    wpId,
    status: 'merging' as const,
    message: '正在合并',
    canRetry: false,
    retry: async () => {},
    refresh: async () => {},
    dismiss: async () => {},
  }
}

function mountRenderer(props: Record<string, unknown> = {}) {
  return mount(GtWpRenderer, {
    props: { wpId: 'wp-1', ...props },
    global: {
      directives: { tabWheel: {}, loading: {} },
      stubs: {
        GtLoadingOverlay: true,
        GtWpPreparationHeader: true,
        GtWpToolbar: true,
        GtWorkpaperRuntimeHosts: true,
        WorkpaperAttachmentsDrawer: true,
        GtBArchitectureTree: true,
        GtOnlyOfficeSheet: true,
        GtGridSheet: true,
        ElAlert: true,
        ElResult: true,
        ElButton: true,
        ElPopover: true,
        ElTabs: true,
        ElTabPane: true,
        ElIcon: true,
        ElOption: true,
        ElSelect: true,
        ElTag: true,
        ElSkeleton: true,
        ElEmpty: true,
        ElTooltip: true,
        ElDrawer: true,
        ElDialog: true,
        ElImage: true,
      },
    },
  })
}

describe('GtWpRenderer：后台合并期间只读', () => {
  beforeEach(() => {
    clearBackgroundMerges()
    scaffoldSpy.mockReset()
    scaffoldSpy.mockReturnValue({ version: { openVersionHistory: vi.fn() } })
    const renderConfig = ref(makeConfig())
    vi.mocked(useWpRenderer).mockReturnValue({
      renderConfig,
      loading: ref(false),
      error: ref(null),
      reload: vi.fn(),
      activeSheet: computed(() => renderConfig.value.sheets[0]),
      selectSheet: vi.fn(),
    } as any)
  })

  const childReadonly = (wrapper: ReturnType<typeof mountRenderer>) =>
    wrapper.getComponent(TestRenderer).props('readonly')
  const scaffoldReadonly = () => scaffoldSpy.mock.calls[0][0].readonly.value
  const headerReadonly = (wrapper: ReturnType<typeof mountRenderer>) =>
    wrapper.getComponent({ name: 'GtWpPreparationHeader' }).props('readonly')
  const banner = (wrapper: ReturnType<typeof mountRenderer>) =>
    wrapper.getComponent(WorkpaperBackgroundMergeBanner).find('.gt-wp-background-merge')

  it('合并中 ⇒ 动态组件与 scaffold 只读、横幅出现；失败 ⇒ 解除只读、横幅留着；注销 ⇒ 横幅消失', async () => {
    const wrapper = mountRenderer()
    expect(childReadonly(wrapper)).toBe(false)
    expect(scaffoldReadonly()).toBe(false)
    expect(banner(wrapper).exists()).toBe(false)

    expect(headerReadonly(wrapper)).toBe(false)

    const registration = registerBackgroundMerge(entry('wp-1'))
    await nextTick()
    expect(childReadonly(wrapper)).toBe(true)
    expect(scaffoldReadonly()).toBe(true)
    expect(headerReadonly(wrapper)).toBe(true)
    expect(banner(wrapper).exists()).toBe(true)
    expect(banner(wrapper).attributes('type')).toBe('info')

    registration.entry.status = 'failed'
    await nextTick()
    expect(childReadonly(wrapper), '失败后表单必须能用').toBe(false)
    expect(scaffoldReadonly()).toBe(false)
    expect(banner(wrapper).attributes('type')).toBe('warning')

    registration.unregister()
    await nextTick()
    expect(banner(wrapper).exists()).toBe(false)
    wrapper.unmount()
  })

  it('别的底稿在后台合并不影响本底稿；本来就只读的照旧只读', async () => {
    registerBackgroundMerge(entry('wp-other'))
    const wrapper = mountRenderer()
    await nextTick()
    expect(childReadonly(wrapper)).toBe(false)
    expect(banner(wrapper).exists()).toBe(false)
    wrapper.unmount()

    scaffoldSpy.mockClear()
    const readonlyWrapper = mountRenderer({ readonly: true })
    expect(childReadonly(readonlyWrapper)).toBe(true)
    expect(scaffoldReadonly()).toBe(true)
    readonlyWrapper.unmount()
  })
})
