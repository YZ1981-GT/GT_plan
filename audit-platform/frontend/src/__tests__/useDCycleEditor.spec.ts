/**
 * useDCycleEditor — 单元测试
 *
 * 锚定 spec workpaper-editor-refactor Phase 2 Task 2.2
 *
 * 覆盖：
 * ① dialogs 初始值全 false
 * ② triggers 基于 wpCode 正确判定
 * ③ onCrossRefUpdated 匹配时调用 refresh + prefill
 * ④ onCrossRefUpdated 不匹配时不调用
 * ⑤ onSSECrossRefUpdated 正确转发事件
 * ⑥ onSSECrossRefUpdated 忽略非 cross_ref.updated 事件
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed, nextTick } from 'vue'
import { useDCycleEditor } from '@/composables/useDCycleEditor'
import { eventBus } from '@/utils/eventBus'
import type { SheetNavFacadeAPI } from '@/composables/useSheetNavFacade'

// Mock eventBus
vi.mock('@/utils/eventBus', () => {
  const handlers: Record<string, Function[]> = {}
  return {
    eventBus: {
      on: vi.fn((event: string, handler: Function) => {
        if (!handlers[event]) handlers[event] = []
        handlers[event].push(handler)
      }),
      off: vi.fn((event: string, handler: Function) => {
        if (handlers[event]) {
          handlers[event] = handlers[event].filter(h => h !== handler)
        }
      }),
      emit: vi.fn((event: string, payload: any) => {
        if (handlers[event]) {
          handlers[event].forEach(h => h(payload))
        }
      }),
      _handlers: handlers,
    },
  }
})

function makeSheetNavMock(): SheetNavFacadeAPI {
  return {
    groups: computed(() => []),
    activeSheetId: computed(() => ''),
    totalCount: computed(() => 0),
    switchTo: vi.fn(),
    refresh: vi.fn(),
    applyForeignCurrencyVisibility: vi.fn(),
    flatSheets: computed(() => []),
    hCycleNav: {} as any,
    iCycleNav: {} as any,
    gCycleNav: {} as any,
  }
}

describe('useDCycleEditor', () => {
  let wpDetail: ReturnType<typeof ref>
  let projectId: ReturnType<typeof ref>
  let sheetNav: SheetNavFacadeAPI
  let onRefreshPrefill: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.clearAllMocks()
    wpDetail = ref({ wp_code: 'D2' })
    projectId = ref('proj-001')
    sheetNav = makeSheetNavMock()
    onRefreshPrefill = vi.fn()
  })

  it('① dialogs 初始值全 false', () => {
    const { dialogs } = useDCycleEditor(wpDetail, projectId, sheetNav, onRefreshPrefill)
    expect(dialogs.salesIPEDialog.value).toBe(false)
    expect(dialogs.salesPenetrationDialog.value).toBe(false)
    expect(dialogs.confirmationDialog.value).toBe(false)
  })

  it('② triggers — D2 底稿 showSalesIPE=true, showPenetration=true, showConfirmation=false', () => {
    wpDetail.value = { wp_code: 'D2' }
    const { triggers } = useDCycleEditor(wpDetail, projectId, sheetNav, onRefreshPrefill)
    expect(triggers.showSalesIPE.value).toBe(true)
    expect(triggers.showPenetration.value).toBe(true)
    expect(triggers.showConfirmation.value).toBe(false)
  })

  it('③ triggers — D0 底稿 showConfirmation=true, showSalesIPE=false', () => {
    wpDetail.value = { wp_code: 'D0' }
    const { triggers } = useDCycleEditor(wpDetail, projectId, sheetNav, onRefreshPrefill)
    expect(triggers.showConfirmation.value).toBe(true)
    expect(triggers.showSalesIPE.value).toBe(false)
    expect(triggers.showPenetration.value).toBe(true)
  })

  it('④ triggers — 非 D 循环底稿全 false', () => {
    wpDetail.value = { wp_code: 'F2' }
    const { triggers } = useDCycleEditor(wpDetail, projectId, sheetNav, onRefreshPrefill)
    expect(triggers.showSalesIPE.value).toBe(false)
    expect(triggers.showPenetration.value).toBe(false)
    expect(triggers.showConfirmation.value).toBe(false)
  })

  it('⑤ onCrossRefUpdated — 匹配时调用 refresh + prefill', () => {
    const { handlers } = useDCycleEditor(wpDetail, projectId, sheetNav, onRefreshPrefill)
    handlers.onCrossRefUpdated({
      projectId: 'proj-001',
      targetWpCode: 'D2',
    })
    expect(sheetNav.refresh).toHaveBeenCalledTimes(1)
    expect(onRefreshPrefill).toHaveBeenCalledTimes(1)
  })

  it('⑥ onCrossRefUpdated — projectId 不匹配时不调用', () => {
    const { handlers } = useDCycleEditor(wpDetail, projectId, sheetNav, onRefreshPrefill)
    handlers.onCrossRefUpdated({
      projectId: 'other-project',
      targetWpCode: 'D2',
    })
    expect(sheetNav.refresh).not.toHaveBeenCalled()
    expect(onRefreshPrefill).not.toHaveBeenCalled()
  })

  it('⑦ onCrossRefUpdated — targetWpCode 不匹配时不调用', () => {
    const { handlers } = useDCycleEditor(wpDetail, projectId, sheetNav, onRefreshPrefill)
    handlers.onCrossRefUpdated({
      projectId: 'proj-001',
      targetWpCode: 'F2',
    })
    expect(sheetNav.refresh).not.toHaveBeenCalled()
    expect(onRefreshPrefill).not.toHaveBeenCalled()
  })

  it('⑧ onSSECrossRefUpdated — 正确转发 cross_ref.updated 事件', () => {
    const { handlers } = useDCycleEditor(wpDetail, projectId, sheetNav, onRefreshPrefill)
    handlers.onSSECrossRefUpdated({
      event_type: 'cross_ref.updated' as any,
      project_id: 'proj-001',
      extra: {
        target_wp_code: 'D2',
        source_wp_code: 'D0',
        ref_id: 'ref-123',
      },
    })
    expect(eventBus.emit).toHaveBeenCalledWith('cross-ref:updated', {
      projectId: 'proj-001',
      targetWpCode: 'D2',
      sourceWpCode: 'D0',
      refId: 'ref-123',
    })
  })

  it('⑨ onSSECrossRefUpdated — 忽略非 cross_ref.updated 事件', () => {
    const { handlers } = useDCycleEditor(wpDetail, projectId, sheetNav, onRefreshPrefill)
    handlers.onSSECrossRefUpdated({
      event_type: 'import.completed' as any,
      project_id: 'proj-001',
    })
    // emit 不应被调用（除了 mock 内部的 on/off 调用）
    expect(eventBus.emit).not.toHaveBeenCalledWith('cross-ref:updated', expect.anything())
  })

  it('⑩ triggers 响应 wpDetail 变化', async () => {
    const { triggers } = useDCycleEditor(wpDetail, projectId, sheetNav, onRefreshPrefill)
    expect(triggers.showSalesIPE.value).toBe(true) // D2
    wpDetail.value = { wp_code: 'D0' }
    await nextTick()
    expect(triggers.showSalesIPE.value).toBe(false)
    expect(triggers.showConfirmation.value).toBe(true)
  })
})
