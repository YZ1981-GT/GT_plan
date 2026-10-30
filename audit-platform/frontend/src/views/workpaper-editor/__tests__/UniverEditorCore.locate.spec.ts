/**
 * UniverEditorCore 定位：深链 initial-sheet / initial-cell 与 locate-cell 事件
 * （spec wp-deeplink-locate-coverage-closure 需求 4）。
 *
 * Univer 未就绪（引擎未建 / 仍在加载 / 没有活动工作簿）时记为待办、只留最后一个，
 * 就绪后切到目标 sheet 并选中单元格；编辑器不再靠 300ms 定时器碰运气。
 */
import { shallowMount } from '@vue/test-utils'
import { computed, nextTick, ref } from 'vue'
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

function makeWorkbook() {
  const sheets = [
    ['sheet-a', '审定表E1-1'],
    ['sheet-b', '分析程序E1-14'],
  ].map(([id, name]) => ({
    getSheetId: () => id,
    getSheetName: () => name,
    getRange: vi.fn((a1: string) => ({ a1, sheetId: id })),
  }))
  return {
    sheets,
    getSheets: () => sheets,
    getActiveSheet: () => sheets[0],
    setActiveRange: vi.fn(),
  }
}

const univerAPI = ref<any>(null)
const loading = ref(true)
const switchTo = vi.fn()

function apiOf(workbook: ReturnType<typeof makeWorkbook> | null) {
  return { getActiveWorkbook: () => workbook }
}

function mountCore(extraProps: Record<string, unknown> = {}) {
  return shallowMount(UniverEditorCore, {
    props: {
      projectId: 'project-1',
      wpId: 'wp-1',
      wpDetail: { id: 'wp-1', wp_code: 'E1', wp_name: '货币资金' } as any,
      canEdit: true,
      sheetNavFacade: {
        groups: computed(() => []), activeSheetId: computed(() => 'sheet-a'), totalCount: computed(() => 2),
        flatSheets: computed(() => []), switchTo, refresh: vi.fn(), bindUniverApi: vi.fn(),
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

/** 模拟 useEditorUniver.initUniver 的就绪顺序：先建引擎（含工作簿），再结束加载 */
async function becomeReady(workbook = makeWorkbook()) {
  univerAPI.value = apiOf(workbook)
  loading.value = false
  await nextTick()
  return workbook
}

describe('UniverEditorCore — 深链与定位事件等 Univer 就绪后执行', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    univerAPI.value = null
    loading.value = true
    vi.mocked(useEditorUniver).mockReturnValue({
      univerAPI, loading, loadingHint: ref(''), loadErrorState: ref(null),
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

  it('深链 initial-sheet / initial-cell：挂载时引擎未建只记待办，就绪后切 sheet 并选中该格，只执行一次', async () => {
    const wrapper = mountCore({ initialSheet: '分析程序E1-14', initialCell: 'c34' })
    await nextTick()
    expect(switchTo).not.toHaveBeenCalled()

    const workbook = await becomeReady()
    expect(switchTo).toHaveBeenCalledTimes(1)
    expect(switchTo).toHaveBeenCalledWith('sheet-b')
    expect(wrapper.emitted('sheet-switch')).toEqual([['sheet-b']])
    expect(workbook.sheets[1].getRange).toHaveBeenCalledWith('C34')
    expect(workbook.setActiveRange).toHaveBeenCalledWith({ a1: 'C34', sheetId: 'sheet-b' })

    // 之后引擎重建（如重试加载）不再重放已执行过的深链
    univerAPI.value = apiOf(makeWorkbook())
    await nextTick()
    expect(switchTo).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('引擎已建但仍在加载：事件记为待办，加载结束才执行', async () => {
    const wrapper = mountCore()
    const workbook = makeWorkbook()
    univerAPI.value = apiOf(workbook)
    await nextTick()

    eventBus.emit('workpaper:locate-cell', { wpId: 'wp-1', sheetName: '分析程序E1-14', cellRef: 'A50' } as any)
    await nextTick()
    expect(switchTo).not.toHaveBeenCalled()
    expect(workbook.setActiveRange).not.toHaveBeenCalled()

    loading.value = false
    await nextTick()
    expect(switchTo).toHaveBeenCalledWith('sheet-b')
    expect(workbook.setActiveRange).toHaveBeenCalledWith({ a1: 'A50', sheetId: 'sheet-b' })
    wrapper.unmount()
  })

  it('没有活动工作簿也算未就绪', async () => {
    const wrapper = mountCore()
    univerAPI.value = apiOf(null)
    loading.value = false
    await nextTick()
    eventBus.emit('workpaper:locate-cell', { wpId: 'wp-1', sheetName: '分析程序E1-14', cellRef: 'A50' } as any)
    await nextTick()
    expect(switchTo).not.toHaveBeenCalled()

    const workbook = await becomeReady()
    expect(switchTo).toHaveBeenCalledWith('sheet-b')
    expect(workbook.setActiveRange).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('未就绪期间收到多个请求只执行最后一个', async () => {
    const wrapper = mountCore({ initialSheet: '审定表E1-1', initialCell: 'B7' })
    eventBus.emit('workpaper:locate-cell', { wpId: 'wp-1', sheetName: '分析程序E1-14', cellRef: 'I18' } as any)
    await nextTick()

    const workbook = await becomeReady()
    expect(switchTo).toHaveBeenCalledTimes(1)
    expect(switchTo).toHaveBeenCalledWith('sheet-b')
    expect(workbook.setActiveRange).toHaveBeenCalledTimes(1)
    expect(workbook.setActiveRange).toHaveBeenCalledWith({ a1: 'I18', sheetId: 'sheet-b' })
    expect(workbook.sheets[0].getRange).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('已就绪时立即执行；只给单元格就在当前 sheet 选中、不切 sheet', async () => {
    const wrapper = mountCore()
    const workbook = await becomeReady()

    eventBus.emit('workpaper:locate-cell', { wpId: 'wp-1', cellRef: 'D9' } as any)
    await nextTick()
    expect(switchTo).not.toHaveBeenCalled()
    expect(workbook.setActiveRange).toHaveBeenCalledWith({ a1: 'D9', sheetId: 'sheet-a' })
    wrapper.unmount()
  })

  it('找不到 sheet 时不切也不选中；单元格不是 A1 形态时只切 sheet', async () => {
    const wrapper = mountCore()
    const workbook = await becomeReady()

    eventBus.emit('workpaper:locate-cell', { wpId: 'wp-1', sheetName: '不存在的表', cellRef: 'A1' } as any)
    await nextTick()
    expect(switchTo).not.toHaveBeenCalled()
    expect(workbook.setActiveRange).not.toHaveBeenCalled()

    eventBus.emit('workpaper:locate-cell', { wpId: 'wp-1', sheetName: '分析程序E1-14', cellRef: 'row:3' } as any)
    await nextTick()
    expect(switchTo).toHaveBeenCalledWith('sheet-b')
    expect(workbook.sheets[1].getRange).not.toHaveBeenCalled()
    expect(workbook.setActiveRange).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('别的底稿的定位事件不处理；深链属性变化（同页再次跳转）立即执行', async () => {
    const wrapper = mountCore()
    const workbook = await becomeReady()

    eventBus.emit('workpaper:locate-cell', { wpId: 'wp-2', sheetName: '分析程序E1-14', cellRef: 'A50' } as any)
    await nextTick()
    expect(switchTo).not.toHaveBeenCalled()

    await wrapper.setProps({ initialSheet: '分析程序E1-14', initialCell: 'C34' } as any)
    await nextTick()
    expect(switchTo).toHaveBeenCalledWith('sheet-b')
    expect(workbook.setActiveRange).toHaveBeenCalledWith({ a1: 'C34', sheetId: 'sheet-b' })
    wrapper.unmount()
  })
})
