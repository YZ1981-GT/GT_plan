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
      loadedFromXlsx: ref(true),
      fileOpenedAt: ref(Date.now()),
      initUniver,
      dispose,
    } as any)
    vi.mocked(useWorkpaperAutoSave).mockReturnValue({
      saving: ref(false),
      lastSavedAt: ref(null),
      markDirty: vi.fn(),
    } as any)
    vi.mocked(useEditorSave).mockReturnValue({
      saving: ref(false), submitting: ref(false), syncLoading: ref(false),
      prefillLoading: ref(false), exportingPdf: ref(false),
      onSave: vi.fn().mockResolvedValue(true), onSubmitForReview: vi.fn(),
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
