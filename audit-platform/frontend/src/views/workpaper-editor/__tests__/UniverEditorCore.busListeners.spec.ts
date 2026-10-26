/**
 * UniverEditorCore 事件监听与详情回传（spec procedure-chain-hardening-and-java-contracts R1）
 *
 * 用真实 eventBus（mitt，同步派发）：
 *  - Shell 收到 saved 后会再广播一次 workpaper:saved，Core 转发不得无限递归；
 *  - 卸载只摘自己的监听（mitt 的 off(type) 不带 handler 会清掉其他组件的监听）；
 *  - 取到 / 保存后重取的详情经 update:wpDetail 交回 Shell，Core 不写只读的 props。
 */
import { shallowMount } from '@vue/test-utils'
import { computed, isReadonly, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/composables/useEditorUniver', () => ({ useEditorUniver: vi.fn() }))
vi.mock('@/composables/useEditorSave', () => ({ useEditorSave: vi.fn() }))
vi.mock('@/composables/useWorkpaperAutoSave', () => ({ useWorkpaperAutoSave: vi.fn() }))
vi.mock('@/composables/usePrefillMarkers', () => ({ usePrefillMarkers: vi.fn(() => ({})) }))
vi.mock('@/composables/useCrossModuleRefs', () => ({ useCrossModuleRefs: vi.fn(() => ({})) }))
vi.mock('@/composables/useUserOverrides', () => ({ useUserOverrides: vi.fn(() => ({})) }))
vi.mock('@/composables/useStaleImpact', () => ({ useStaleImpact: vi.fn(() => ({})) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

import { useEditorUniver } from '@/composables/useEditorUniver'
import { useEditorSave } from '@/composables/useEditorSave'
import { useWorkpaperAutoSave } from '@/composables/useWorkpaperAutoSave'
import { eventBus } from '@/utils/eventBus'
import UniverEditorCore from '../UniverEditorCore.vue'

function mountCore(extraProps: Record<string, unknown> = {}) {
  return shallowMount(UniverEditorCore, {
    props: {
      projectId: 'project-1',
      wpId: 'wp-1',
      wpDetail: { id: 'wp-1', wp_code: 'D2', wp_name: '应收账款' } as any,
      canEdit: true,
      sheetNavFacade: {
        groups: computed(() => []), activeSheetId: computed(() => ''), totalCount: computed(() => 0),
        flatSheets: computed(() => []), switchTo: vi.fn(), refresh: vi.fn(), bindUniverApi: vi.fn(),
      } as any,
      cycleType: {} as any,
      cycleDialogs: {} as any,
      iCycle: {}, gCycle: {}, kCycle: {}, lCycle: {}, mCycle: {}, nCycle: {}, fCycle: {},
      ...extraProps,
    } as any,
    global: {
      stubs: {
        UniverSheetNav: true, SheetTopTabs: true, GtLoadingOverlay: true,
        CycleTriggerPanel: true, EditorStatusBar: true, ElButton: true,
      },
    },
  })
}

describe('UniverEditorCore — 事件监听与详情回传', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useEditorUniver).mockReturnValue({
      univerAPI: ref(null), loading: ref(false), loadingHint: ref(''), loadErrorState: ref(null),
      loadErrorMessage: ref(''), dirty: ref(false), initUniver: vi.fn(), dispose: vi.fn(),
    } as any)
    vi.mocked(useWorkpaperAutoSave).mockReturnValue({
      saving: ref(false), lastSavedAt: ref(null), markDirty: vi.fn(),
    } as any)
    vi.mocked(useEditorSave).mockReturnValue({
      saving: ref(false), submitting: ref(false), syncLoading: ref(false), prefillLoading: ref(false),
      exportingPdf: ref(false), onSave: vi.fn(), onSubmitForReview: vi.fn(), onSyncStructure: vi.fn(),
      onRefreshPrefill: vi.fn(), onDownload: vi.fn(), onExportPdf: vi.fn(), onUpload: vi.fn(),
    } as any)
  })

  it('Shell 收到 saved 后同步再广播：Core 只转发一次（不递归）', () => {
    const onSaved = vi.fn(() => {
      eventBus.emit('workpaper:saved', { projectId: 'project-1', wpId: 'wp-1' } as any)
    })
    const wrapper = mountCore({ onSaved })

    eventBus.emit('workpaper:saved', { projectId: 'project-1', wpId: 'wp-1' } as any)

    expect(onSaved).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('卸载只摘自己的监听，其他组件的 workpaper:saved / locate-cell 监听仍在', () => {
    const foreign = vi.fn()
    eventBus.on('workpaper:saved', foreign)
    eventBus.on('workpaper:locate-cell', foreign)
    try {
      mountCore().unmount()
      eventBus.emit('workpaper:saved', { projectId: 'project-1', wpId: 'wp-1' } as any)
      eventBus.emit('workpaper:locate-cell', { wpId: 'wp-1', sheetName: 'x', cellRef: 'A1' } as any)
      expect(foreign).toHaveBeenCalledTimes(2)
    } finally {
      eventBus.off('workpaper:saved', foreign)
      eventBus.off('workpaper:locate-cell', foreign)
    }
  })

  it('打不开底稿时不显示左侧页签导航，只留中性提示（R10）', () => {
    const open = mountCore()
    expect(open.find('.gt-wp-editor-left-col').attributes('style') ?? '').not.toContain('display: none')
    open.unmount()
    vi.mocked(useEditorUniver).mockReturnValue({
      univerAPI: ref(null), loading: ref(false), loadingHint: ref(''), loadErrorState: ref('no_index'),
      loadErrorMessage: ref('无法打开这张底稿'), dirty: ref(false), initUniver: vi.fn(), dispose: vi.fn(),
    } as any)
    const denied = mountCore()
    expect(denied.find('.gt-wp-editor-left-col').attributes('style') ?? '').toContain('display: none')
    expect(denied.find('.gt-wp-editor-error-overlay').exists()).toBe(true)
    denied.unmount()
  })

  it('取到 / 保存后重取的详情经 update:wpDetail 交回，传给两个组合式函数的详情是只读的', () => {
    const wrapper = mountCore()
    const uniOpts = vi.mocked(useEditorUniver).mock.calls[0][0] as any
    const saveOpts = vi.mocked(useEditorSave).mock.calls[0][0] as any

    expect(isReadonly(uniOpts.wpDetail)).toBe(true)
    expect(isReadonly(saveOpts.wpDetail)).toBe(true)
    uniOpts.onDetailLoaded({ id: 'wp-1', wp_code: 'H1A' })
    saveOpts.setWpDetail({ id: 'wp-1', wp_code: 'H1A', file_version: 2 })

    expect(wrapper.emitted('update:wpDetail')).toEqual([
      [{ id: 'wp-1', wp_code: 'H1A' }],
      [{ id: 'wp-1', wp_code: 'H1A', file_version: 2 }],
    ])
    wrapper.unmount()
  })
})
