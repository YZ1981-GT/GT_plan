import { computed, defineComponent, isRef, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  scaffoldSpy,
  reloadSpy,
  loadProjectContextSpy,
  openVersionHistorySpy,
  eventHandlers,
} = vi.hoisted(() => ({
  scaffoldSpy: vi.fn(),
  reloadSpy: vi.fn(),
  loadProjectContextSpy: vi.fn(),
  openVersionHistorySpy: vi.fn(),
  eventHandlers: new Map<string, Set<(payload: any) => void>>(),
}))

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
  eventBus: {
    on: vi.fn((name: string, handler: (payload: any) => void) => {
      const handlers = eventHandlers.get(name) ?? new Set()
      handlers.add(handler)
      eventHandlers.set(name, handlers)
    }),
    off: vi.fn((name: string, handler?: (payload: any) => void) => {
      if (!handler) eventHandlers.delete(name)
      else eventHandlers.get(name)?.delete(handler)
    }),
    emit: vi.fn((name: string, payload: any) => {
      eventHandlers.get(name)?.forEach((handler) => handler(payload))
    }),
  },
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
import { eventBus } from '@/utils/eventBus'
import GtWpRenderer from './GtWpRenderer.vue'

function makeConfig(overrides: Record<string, unknown> = {}) {
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
    eventHandlers.clear()
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

  it('config 初始/deep-link、tab、navigate 与归一化 locate 都进入同一结构化 emitter', async () => {
    renderConfig.value = makeConfig({
      wp_code: 'D0',
      sheets: [
        {
          sheet_name: '底稿目录', sheet_code: null, sheet_code_reason: 'no_canonical_code',
          whole_workbook: false, componentType: 'test-standard', schema: {}, html_data: {}, cross_refs: [],
        },
        {
          sheet_name: '询证函控制表D0-4b', sheet_code: 'D0-4b', sheet_code_reason: 'embedded_code',
          whole_workbook: false, componentType: 'test-standard', schema: {}, html_data: {}, cross_refs: [],
        },
        {
          sheet_name: '附注披露信息（上市公司）D0-8', sheet_code: 'D0-8', sheet_code_reason: 'embedded_code',
          whole_workbook: false, componentType: 'test-standard', schema: {}, html_data: {}, cross_refs: [],
        },
      ],
    })
    const wrapper = mountRenderer({ initialSheet: 'D0-4b' })
    const latestContext = () => {
      const events = wrapper.emitted('sheet-change') ?? []
      return events[events.length - 1]?.[0]
    }

    expect(latestContext()).toMatchObject({
      sheetName: '询证函控制表D0-4b',
      sheetCode: 'D0-4b',
      sheetUid: 'uid:D0:D0-4b',
      sheetUidNullReason: null,
      host: 'html',
      wholeWorkbook: false,
      ownerEpoch: expect.any(Number),
      contextRevision: expect.any(Number),
    })

    const tabs = wrapper.getComponent({ name: 'ElTabs' })
    tabs.vm.$emit('update:modelValue', '底稿目录')
    await nextTick()
    expect(latestContext()).toMatchObject({
      sheetName: '底稿目录',
      sheetCode: null,
      sheetUid: null,
      sheetUidNullReason: 'no_canonical_code',
      host: 'html',
      wholeWorkbook: false,
    })

    wrapper.getComponent(TestRenderer).vm.$emit('navigate-sheet', 'D0-8')
    await nextTick()
    expect(latestContext()).toMatchObject({
      sheetName: '附注披露信息（上市公司）D0-8',
      sheetCode: 'D0-8',
      sheetUid: 'uid:D0:D0-8',
      host: 'html',
      wholeWorkbook: false,
    })

    eventBus.emit('workpaper:locate-cell', {
      wpId: 'wp-1',
      sheetName: 'D0-4b',
      cellRef: 'B12',
    })
    await nextTick()
    expect(latestContext()).toMatchObject({
      sheetName: '询证函控制表D0-4b',
      sheetCode: 'D0-4b',
      sheetUid: 'uid:D0:D0-4b',
      host: 'html',
      wholeWorkbook: false,
    })

    await wrapper.setProps({ initialSheet: '附注披露信息(上市公司)D0-8' })
    expect(latestContext()).toMatchObject({
      sheetName: '附注披露信息（上市公司）D0-8',
      sheetCode: 'D0-8',
      sheetUid: 'uid:D0:D0-8',
      host: 'html',
      wholeWorkbook: false,
    })
    wrapper.unmount()
  })

  it('OnlyOffice 外层与整册 context 诚实区分，identity reload 会重新 emit', async () => {
    renderConfig.value = makeConfig({
      sheets: [
        {
          sheet_name: '底稿目录', sheet_code: null, sheet_code_reason: 'no_canonical_code',
          whole_workbook: false, componentType: 'test-standard', schema: {}, html_data: {}, cross_refs: [],
        },
        {
          sheet_name: '复杂测算D2-9', sheet_code: 'D2-9', sheet_code_reason: 'embedded_code',
          whole_workbook: false, componentType: 'onlyoffice-sheet', schema: {},
          html_data: { onlyoffice: true }, cross_refs: [],
        },
      ],
    })
    const wrapper = mountRenderer()
    const latestContext = () => {
      const events = wrapper.emitted('sheet-change') ?? []
      return events[events.length - 1]?.[0]
    }
    const tabs = wrapper.getComponent({ name: 'ElTabs' })

    tabs.vm.$emit('update:modelValue', '复杂测算D2-9')
    await nextTick()
    expect(latestContext()).toMatchObject({
      sheetName: '复杂测算D2-9',
      sheetCode: 'D2-9',
      sheetUid: 'uid:D2:D2-9',
      host: 'onlyoffice',
      wholeWorkbook: false,
    })

    renderConfig.value = makeConfig({
      template_version: 'v-same',
      sheets: [
        {
          sheet_name: '底稿目录', sheet_code: null, sheet_code_reason: 'no_canonical_code',
          whole_workbook: false, componentType: 'test-standard', schema: {}, html_data: {}, cross_refs: [],
        },
        {
          sheet_name: '复杂测算D2-9', sheet_code: 'D2-9b', sheet_code_reason: 'embedded_code',
          whole_workbook: false, componentType: 'onlyoffice-sheet', schema: {},
          html_data: { onlyoffice: true }, cross_refs: [],
        },
      ],
    })
    await nextTick()
    expect(latestContext()).toMatchObject({ sheetCode: 'D2-9b', sheetUid: 'uid:D2:D2-9b', host: 'onlyoffice' })

    tabs.vm.$emit('update:modelValue', '__whole_excel__')
    await nextTick()
    expect(latestContext()).toMatchObject({
      sheetName: '__whole_excel__',
      sheetCode: null,
      sheetUid: null,
      sheetUidNullReason: 'whole_workbook',
      host: 'onlyoffice',
      wholeWorkbook: true,
    })
    wrapper.unmount()
  })
})