import { shallowMount } from '@vue/test-utils'
import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { handlers } = vi.hoisted(() => ({
  handlers: new Map<string, Set<(payload: any) => void>>(),
}))

vi.mock('@/composables/useEditorUniver', () => ({ useEditorUniver: vi.fn() }))
vi.mock('@/composables/useEditorSave', () => ({ useEditorSave: vi.fn() }))
vi.mock('@/composables/useWorkpaperAutoSave', () => ({ useWorkpaperAutoSave: vi.fn() }))
vi.mock('@/composables/usePrefillMarkers', () => ({ usePrefillMarkers: vi.fn(() => ({})) }))
vi.mock('@/composables/useCrossModuleRefs', () => ({ useCrossModuleRefs: vi.fn(() => ({})) }))
vi.mock('@/composables/useUserOverrides', () => ({ useUserOverrides: vi.fn(() => ({})) }))
vi.mock('@/composables/useStaleImpact', () => ({ useStaleImpact: vi.fn(() => ({})) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    on: vi.fn((name: string, handler: (payload: any) => void) => {
      const set = handlers.get(name) ?? new Set()
      set.add(handler)
      handlers.set(name, set)
    }),
    off: vi.fn((name: string) => handlers.delete(name)),
    emit: vi.fn((name: string, payload: any) => {
      handlers.get(name)?.forEach((handler) => handler(payload))
    }),
  },
}))

import { useEditorUniver } from '@/composables/useEditorUniver'
import { useEditorSave } from '@/composables/useEditorSave'
import { useWorkpaperAutoSave } from '@/composables/useWorkpaperAutoSave'
import { eventBus } from '@/utils/eventBus'
import {
  clearWorkpaperDraftAccessors,
  workpaperDraftAccessorOf,
} from '@/composables/workpaper/workpaperDraftOverlay'
import UniverEditorCore from '../UniverEditorCore.vue'

function makeSheet(id: string, name: string) {
  return {
    getSheetId: () => id,
    getSheetName: () => name,
  }
}

describe('UniverEditorCore — custom nav 与 locate 汇入同一 sheet-switch', () => {
  const switchTo = vi.fn()
  const initUniver = vi.fn()
  const dispose = vi.fn()
  const recordEdit = vi.fn()
  const editorOnSave = vi.fn()
  const sheets = [
    makeSheet('sheet-a', '询证函控制表D0-4b'),
    makeSheet('sheet-b', '附注披露信息（上市公司）D0-8'),
  ]

  beforeEach(() => {
    vi.clearAllMocks()
    handlers.clear()
    vi.mocked(useEditorUniver).mockReturnValue({
      univerAPI: ref({
        getActiveWorkbook: () => ({ getSheets: () => sheets }),
      }),
      loading: ref(false),
      loadingHint: ref(''),
      loadErrorState: ref(null),
      loadErrorMessage: ref(''),
      dirty: ref(false),
      editRevision: ref(0),
      initUniver,
      dispose,
    } as any)
    vi.mocked(useWorkpaperAutoSave).mockReturnValue({
      saving: ref(false),
      lastSavedAt: ref(null),
      markDirty: vi.fn(),
      recordEdit,
    } as any)
    editorOnSave.mockResolvedValue(true)
    vi.mocked(useEditorSave).mockReturnValue({
      saving: ref(false), submitting: ref(false), syncLoading: ref(false),
      prefillLoading: ref(false), exportingPdf: ref(false), markEdited: vi.fn(),
      // onSave 必须就是 editorOnSave：用例靠 editorOnSave.mockResolvedValueOnce(false)
      // 驱动「自动保存回调原样返回 false」。原先这里另建了一个 vi.fn ⇒ 两者没有关联，
      // 回调恒返回 true，断言永远拿不到 false（判据失效）。
      onSave: editorOnSave, onSubmitForReview: vi.fn(),
      onSyncStructure: vi.fn(), onRefreshPrefill: vi.fn(), onDownload: vi.fn(),
      onExportPdf: vi.fn(), onUpload: vi.fn(),
    } as any)
  })

  function mountCore() {
    const groups = computed(() => [{
      category: '测试', icon: '📄', color: '#000',
      sheets: sheets.map((sheet, index) => ({
        id: sheet.getSheetId(), name: sheet.getSheetName(), index, category: '测试',
      })),
    }])
    return shallowMount(UniverEditorCore, {
      props: {
        projectId: 'project-1',
        wpId: 'wp-1',
        wpDetail: { wp_code: 'D0', wp_name: '函证' } as any,
        canEdit: true,
        sheetNavFacade: {
          groups,
          activeSheetId: computed(() => 'sheet-a'),
          totalCount: computed(() => 2),
          flatSheets: computed(() => [
            { id: 'sheet-a', name: '询证函控制表D0-4b' },
            { id: 'sheet-b', name: '附注披露信息（上市公司）D0-8' },
          ]),
          switchTo,
          refresh: vi.fn(),
          bindUniverApi: vi.fn(),
          applyForeignCurrencyVisibility: vi.fn(),
          hCycleNav: {}, iCycleNav: {}, gCycleNav: {},
        } as any,
        cycleType: {} as any,
        cycleDialogs: {} as any,
        iCycle: {}, gCycle: {}, kCycle: {}, lCycle: {}, mCycle: {}, nCycle: {}, fCycle: {},
      },
      global: {
        stubs: {
          UniverSheetNav: { name: 'UniverSheetNav', template: '<div />' },
          SheetTopTabs: { name: 'SheetTopTabs', template: '<div />' },
          GtLoadingOverlay: true,
          CycleTriggerPanel: true,
          EditorStatusBar: true,
          ElButton: true,
        },
      },
    })
  }

  it('逐命令编辑回调推进 auto-save，且自动保存回调原样返回 false', async () => {
    mountCore()
    const univerOptions = vi.mocked(useEditorUniver).mock.calls[0][0] as any
    univerOptions.onEdited()
    univerOptions.onEdited()
    expect(recordEdit).toHaveBeenCalledTimes(2)

    editorOnSave.mockResolvedValueOnce(false)
    const autoSaveCallback = vi.mocked(useWorkpaperAutoSave).mock.calls[0][0]
    expect(await autoSaveCallback()).toBe(false)
  })

  it('custom nav 既操作真实 facade，也向 Shell 发同一 engine id', async () => {
    const wrapper = mountCore()
    wrapper.getComponent({ name: 'SheetTopTabs' }).vm.$emit('switch', 'sheet-b')
    await wrapper.vm.$nextTick()

    expect(switchTo).toHaveBeenCalledWith('sheet-b')
    expect(wrapper.emitted('sheet-switch')).toEqual([['sheet-b']])
    wrapper.unmount()
  })

  it('locate 接受归一化/后缀名称并复用 custom nav 的切换函数，不再发无消费 locate 事件', async () => {
    const wrapper = mountCore()
    eventBus.emit('workpaper:locate-cell', {
      wpId: 'wp-1',
      sheetName: '附注披露信息(上市公司)D0-8',
      cellRef: 'C9',
    })
    await wrapper.vm.$nextTick()

    expect(switchTo).toHaveBeenCalledWith('sheet-b')
    expect(wrapper.emitted('sheet-switch')).toEqual([['sheet-b']])
    expect(wrapper.emitted('locate-cell')).toBeUndefined()
    wrapper.unmount()
  })
})

/**
 * AI 面板的未保存草稿访问器（spec chat-host-draft-overlay Task 4）。
 *
 * 这一组盯的是**接线真的跑到了**：`useWorkpaperDraftAccessor` 写在 `setup` 里，
 * 只测 `workpaperDraftOverlay.ts` 的纯函数证明不了 Univer 编辑器调用了它。
 * 所以这里真挂 `UniverEditorCore`，再从注册表按 wpId 读回访问器。
 */
describe('UniverEditorCore — 向 AI 面板登记未保存草稿访问器', () => {
  const WP = '11111111-1111-4111-8111-111111111111'
  const OPENED_AT = '2026-11-15T10:00:00+00:00'

  function mountWithDetail(wpDetail: Record<string, unknown>) {
    const groups = computed(() => [{
      category: '测试', icon: '📄', color: '#000',
      sheets: [{ id: 'sheet-a', name: '明细表', index: 0, category: '测试' }],
    }])
    return shallowMount(UniverEditorCore, {
      props: {
        projectId: 'project-1',
        wpId: WP,
        wpDetail: wpDetail as any,
        canEdit: true,
        sheetNavFacade: {
          groups,
          activeSheetId: computed(() => 'sheet-a'),
          totalCount: computed(() => 1),
          flatSheets: computed(() => [{ id: 'sheet-a', name: '明细表' }]),
          switchTo: vi.fn(),
          refresh: vi.fn(),
          bindUniverApi: vi.fn(),
          applyForeignCurrencyVisibility: vi.fn(),
          hCycleNav: {}, iCycleNav: {}, gCycleNav: {},
        } as any,
        cycleType: {} as any,
        cycleDialogs: {} as any,
        iCycle: {}, gCycle: {}, kCycle: {}, lCycle: {}, mCycle: {}, nCycle: {}, fCycle: {},
      },
      global: {
        stubs: {
          UniverSheetNav: { name: 'UniverSheetNav', template: '<div />' },
          SheetTopTabs: { name: 'SheetTopTabs', template: '<div />' },
          GtLoadingOverlay: true,
          CycleTriggerPanel: true,
          EditorStatusBar: true,
          ElButton: true,
        },
      },
    })
  }

  beforeEach(() => {
    clearWorkpaperDraftAccessors()
    vi.clearAllMocks()
    vi.mocked(useWorkpaperAutoSave).mockReturnValue({
      saving: ref(false),
      lastSavedAt: ref(null),
      markDirty: vi.fn(),
      recordEdit: vi.fn(),
    } as any)
    vi.mocked(useEditorSave).mockReturnValue({
      saving: ref(false), submitting: ref(false), syncLoading: ref(false),
      prefillLoading: ref(false), exportingPdf: ref(false), markEdited: vi.fn(),
      onSave: vi.fn(async () => true), onSubmitForReview: vi.fn(),
      onSyncStructure: vi.fn(), onRefreshPrefill: vi.fn(), onDownload: vi.fn(),
      onExportPdf: vi.fn(), onUpload: vi.fn(),
    } as any)
  })

  it('挂载即登记；基线取 wpDetail.updated_at', () => {
    vi.mocked(useEditorUniver).mockReturnValue({
      univerAPI: ref({ getActiveWorkbook: () => ({ getSnapshot: () => null }) }),
      loading: ref(false), loadingHint: ref(''), loadErrorState: ref(null), loadErrorMessage: ref(''),
      dirty: ref(false), editRevision: ref(0), initUniver: vi.fn(), dispose: vi.fn(),
    } as any)
    const wrapper = mountWithDetail({ wp_code: 'K1', wp_name: '其他应收款', updated_at: OPENED_AT })

    const accessor = workpaperDraftAccessorOf(WP)
    expect(accessor, 'UniverEditorCore 没有登记草稿访问器').not.toBeNull()
    expect(accessor!.openedBaselineVersion()).toBe(OPENED_AT)
    // 干净态：没有未保存修改 ⇒ 不提供正文
    expect(accessor!.hasUnsaved()).toBe(false)
    expect(accessor!.currentDraftContent()).toBeNull()

    wrapper.unmount()
    expect(workpaperDraftAccessorOf(WP)).toBeNull()
  })

  it('dirty 时把工作簿摊成正文；dirty 为假时返回 null', async () => {
    const dirtyRef = ref(false)
    const snapshot = {
      sheets: { s1: { name: '明细表', cellData: { 0: { 0: { v: '未保存值' } } } } },
    }
    vi.mocked(useEditorUniver).mockReturnValue({
      univerAPI: ref({ getActiveWorkbook: () => ({ getSnapshot: () => snapshot }) }),
      loading: ref(false), loadingHint: ref(''), loadErrorState: ref(null), loadErrorMessage: ref(''),
      dirty: dirtyRef, editRevision: ref(0), initUniver: vi.fn(), dispose: vi.fn(),
    } as any)
    const wrapper = mountWithDetail({ wp_code: 'K1', wp_name: '其他应收款', updated_at: OPENED_AT })

    const accessor = workpaperDraftAccessorOf(WP)!
    expect(accessor.currentDraftContent()).toBeNull()

    // 改一处（不保存）
    dirtyRef.value = true
    await wrapper.vm.$nextTick()
    expect(accessor.hasUnsaved()).toBe(true)
    expect(accessor.currentDraftContent()).toBe('【明细表】\nA1=未保存值')

    // 保存成功 ⇒ dirty 归零
    dirtyRef.value = false
    await wrapper.vm.$nextTick()
    expect(accessor.hasUnsaved()).toBe(false)
    expect(accessor.currentDraftContent()).toBeNull()
    wrapper.unmount()
  })

  it('保存后 wpDetail.updated_at 前进，基线仍停在打开时（过期检测不失效）', async () => {
    vi.mocked(useEditorUniver).mockReturnValue({
      univerAPI: ref({ getActiveWorkbook: () => ({ getSnapshot: () => null }) }),
      loading: ref(false), loadingHint: ref(''), loadErrorState: ref(null), loadErrorMessage: ref(''),
      dirty: ref(false), editRevision: ref(0), initUniver: vi.fn(), dispose: vi.fn(),
    } as any)
    const wrapper = mountWithDetail({ wp_code: 'K1', updated_at: OPENED_AT })
    const accessor = workpaperDraftAccessorOf(WP)!
    expect(accessor.openedBaselineVersion()).toBe(OPENED_AT)

    // useEditorSave 的 refreshDetail() 会把新详情交回 Shell（这里模拟同一动作）
    await wrapper.setProps({ wpDetail: { wp_code: 'K1', updated_at: '2026-11-15T12:00:00+00:00' } } as any)
    expect(accessor.openedBaselineVersion()).toBe(OPENED_AT)
    wrapper.unmount()
  })
})
