import { computed, defineComponent, isRef, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { scaffoldSpy, reloadSpy, loadProjectContextSpy, openVersionHistorySpy } = vi.hoisted(() => ({
  scaffoldSpy: vi.fn(),
  reloadSpy: vi.fn(),
  loadProjectContextSpy: vi.fn(),
  openVersionHistorySpy: vi.fn(),
}))

vi.mock('@/components/workpaper/composables/useWorkpaperScaffold', () => ({
  useWorkpaperScaffold: scaffoldSpy,
}))
vi.mock('@/composables/useWpRenderer', () => ({ useWpRenderer: vi.fn() }))
vi.mock('@/composables/useCellLocate', () => ({
  useCellLocate: () => ({ locateCell: vi.fn() }),
}))
vi.mock('@/utils/eventBus', () => ({
  eventBus: { on: vi.fn(), off: vi.fn() },
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
    loadProjectContext: loadProjectContextSpy,
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

function makeConfig(overrides: Record<string, unknown> = {}) {
  return {
    wp_code: 'D2',
    project_id: 'project-1',
    audit_year: 2025,
    template_version: 'v-test',
    sheets: [
      {
        sheet_name: '审定表D2-1',
        componentType: 'test-standard',
        schema: {},
        html_data: {},
      },
    ],
    ...overrides,
  }
}
describe('GtWpRenderer Runtime Boundary', () => {
  let renderConfig: ReturnType<typeof ref<any>>

  beforeEach(() => {
    scaffoldSpy.mockReset()
    reloadSpy.mockReset()
    loadProjectContextSpy.mockReset()
    openVersionHistorySpy.mockReset()
    scaffoldSpy.mockReturnValue({
      version: { openVersionHistory: openVersionHistorySpy },
    })
    renderConfig = ref(makeConfig())
    vi.mocked(useWpRenderer).mockReturnValue({
      renderConfig,
      loading: ref(false),
      error: ref(null),
      reload: reloadSpy,
      activeSheet: computed(() => renderConfig.value.sheets[0]),
      selectSheet: vi.fn(),
    } as any)
  })

  function mountRenderer() {
    return mount(GtWpRenderer, {
      props: { wpId: 'wp-1' },
      global: {
        directives: { tabWheel: {} },
        stubs: {
          GtLoadingOverlay: true,
          GtWpPreparationHeader: true,
          GtWpToolbar: true,
          GtWorkpaperRuntimeHosts: true,
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
        },
      },
    })
  }

  it('只初始化一次 Scaffold，并持续提供响应式运行时上下文', async () => {
    const wrapper = mountRenderer()

    expect(scaffoldSpy).toHaveBeenCalledTimes(1)
    const options = scaffoldSpy.mock.calls[0][0]
    expect(isRef(options.wpId)).toBe(true)
    expect(isRef(options.projectId)).toBe(true)
    expect(isRef(options.wpCode)).toBe(true)
    expect(isRef(options.year)).toBe(true)
    expect(options.wpId.value).toBe('wp-1')
    expect(options.projectId.value).toBe('project-1')
    expect(options.wpCode.value).toBe('D2')
    expect(options.year.value).toBe(2025)

    ;(wrapper.vm as any).openVersionHistory()
    expect(openVersionHistorySpy).toHaveBeenCalledTimes(1)

    await wrapper.setProps({ wpId: 'wp-2' })
    renderConfig.value = makeConfig({
      wp_code: 'K5',
      project_id: 'project-2',
      audit_year: 2026,
    })
    await nextTick()

    expect(options.wpId.value).toBe('wp-2')
    expect(options.projectId.value).toBe('project-2')
    expect(options.wpCode.value).toBe('K5')
    expect(options.year.value).toBe(2026)
    expect(scaffoldSpy).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('保留 standard contextProps 的动态组件 props 与现有单一 toolbar', () => {
    const wrapper = mountRenderer()
    const child = wrapper.getComponent(TestRenderer)

    expect(child.props()).toMatchObject({
      wpId: 'wp-1',
      projectId: 'project-1',
      wpCode: 'D2',
      year: 2025,
      sheetName: '审定表D2-1',
    })
    expect(wrapper.findAllComponents({ name: 'GtWpToolbar' })).toHaveLength(1)
    expect(wrapper.findAll('.gt-wp-renderer')).toHaveLength(1)
    wrapper.unmount()
  })
})