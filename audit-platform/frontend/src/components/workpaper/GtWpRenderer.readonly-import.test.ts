/**
 * 只读时渲染器不把「导入」转给子组件（spec workpaper-multi-window-lock-gaps R2.1）。
 *
 * 原先工具栏「导入」在只读窗口照样可点，`onImportData` 直接调子组件的 `handleImportClick`，
 * D4 等子组件随即 POST 后端导入接口写库。现在：只读（编辑锁在别的窗口 / 别人手里、后台合并中）⇒
 * 工具栏收到 readonly、导入只提示不转发；可编辑照常转发。
 */
import { computed, defineComponent, h, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { importSpy, warning } = vi.hoisted(() => ({ importSpy: vi.fn(), warning: vi.fn() }))

vi.mock('element-plus', async (orig) => {
  const actual = await orig<typeof import('element-plus')>()
  return { ...actual, ElMessage: Object.assign(vi.fn(), { warning, info: vi.fn(), success: vi.fn(), error: vi.fn() }) }
})
vi.mock('@/components/workpaper/composables/useWorkpaperScaffold', () => ({
  useWorkpaperScaffold: () => ({ version: { openVersionHistory: vi.fn() } }),
}))
vi.mock('@/composables/useWpRenderer', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/composables/useWpRenderer')>()
  return { ...actual, useWpRenderer: vi.fn() }
})
vi.mock('@/composables/useCellLocate', () => ({ useCellLocate: () => ({ locateCell: vi.fn() }) }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() } }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }), useRouter: () => ({ push: vi.fn(), back: vi.fn() }) }))
vi.mock('@/stores/project', () => ({
  useProjectStore: () => ({ projectId: 'project-1', auditYear: 2025, year: 2025, loadProjectContext: vi.fn() }),
}))

const ImportingRenderer = defineComponent({
  name: 'ImportingRenderer',
  props: { wpId: String, projectId: String, wpCode: String, year: Number, sheetName: String, readonly: Boolean },
  setup(_props, { expose }) {
    expose({ handleImportClick: importSpy })
    return () => h('div', { 'data-test': 'dynamic-renderer' })
  },
})

vi.mock('@/components/workpaper/htmlRendererRegistry', () => ({
  getRendererEntry: (t: string) => (t === 'test-standard' ? { component: ImportingRenderer, contextProps: 'standard' } : undefined),
  getSheetIcon: () => '📄',
  getContextPropsStrategy: (t: string) => (t === 'test-standard' ? 'standard' : 'none'),
}))

import { useWpRenderer } from '@/composables/useWpRenderer'
import GtWpRenderer from './GtWpRenderer.vue'

function mountRenderer(readonly: boolean) {
  return mount(GtWpRenderer, {
    props: { wpId: 'wp-1', readonly },
    global: {
      directives: { tabWheel: {}, loading: {} },
      stubs: Object.fromEntries([
        'GtLoadingOverlay', 'GtWpPreparationHeader', 'GtWpToolbar', 'GtWorkpaperRuntimeHosts', 'WorkpaperAttachmentsDrawer',
        'GtBArchitectureTree', 'GtOnlyOfficeSheet', 'GtGridSheet', 'ElAlert', 'ElResult', 'ElButton', 'ElPopover', 'ElTabs',
        'ElTabPane', 'ElIcon', 'ElOption', 'ElSelect', 'ElTag', 'ElSkeleton', 'ElEmpty', 'ElTooltip', 'ElDrawer', 'ElDialog', 'ElImage',
      ].map((name) => [name, true])),
    },
  })
}

describe('GtWpRenderer：只读时不转发导入', () => {
  beforeEach(() => {
    importSpy.mockReset()
    warning.mockReset()
    const renderConfig = ref({
      wp_id: 'wp-1', wp_code: 'D4', project_id: 'project-1', audit_year: 2025, template_version: 'v-test',
      sheets: [{
        sheet_name: '审定表D4-1', sheet_code: 'D4-1', sheet_code_reason: 'embedded_code', whole_workbook: false,
        componentType: 'test-standard', schema: {}, html_data: {}, cross_refs: [],
      }],
    })
    vi.mocked(useWpRenderer).mockReturnValue({
      renderConfig, loading: ref(false), error: ref(null), reload: vi.fn(),
      activeSheet: computed(() => renderConfig.value.sheets[0]), selectSheet: vi.fn(),
    } as any)
  })

  it('只读：工具栏收到 readonly，点导入只提示、不调子组件导入', async () => {
    const wrapper = mountRenderer(true)
    await nextTick()
    const toolbar = wrapper.findComponent({ name: 'GtWpToolbar' })
    expect(toolbar.props('readonly')).toBe(true)
    toolbar.vm.$emit('import-data')
    await nextTick()
    expect(importSpy).not.toHaveBeenCalled()
    expect(warning).toHaveBeenCalledWith('当前为只读，不能导入')
    wrapper.unmount()
  })

  it('可编辑：工具栏 readonly=false，导入转给子组件', async () => {
    const wrapper = mountRenderer(false)
    await nextTick()
    const toolbar = wrapper.findComponent({ name: 'GtWpToolbar' })
    expect(toolbar.props('readonly')).toBe(false)
    toolbar.vm.$emit('import-data')
    await nextTick()
    expect(importSpy).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
})
