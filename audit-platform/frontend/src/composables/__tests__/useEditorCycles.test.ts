/**
 * useEditorCycles 单测 — V3 Req 12.1.2
 *
 * 验证：
 *  - 实例化返回的 8 个 key（cycleDialogs / fCycle / iCycle / gCycle / kCycle / lCycle / mCycle / nCycle）
 *  - 各 cycle composable 被精确调用一次，且签名与 WorkpaperEditor.vue 重构前一致
 *  - cycleDialogs 必须先于其他 cycle 实例化（依赖拓扑），且作为最后一个参数注入下游 cycle
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { computed, ref } from 'vue'

const useCycleDialogsMock = vi.fn()
const useFCycleEditorMock = vi.fn()
const useICycleEditorMock = vi.fn()
const useGCycleEditorMock = vi.fn()
const useKCycleEditorMock = vi.fn()
const useLCycleEditorMock = vi.fn()
const useMCycleEditorMock = vi.fn()
const useNCycleEditorMock = vi.fn()

vi.mock('../useCycleDialogs', () => ({
  useCycleDialogs: (...args: unknown[]) => useCycleDialogsMock(...args),
}))
vi.mock('../useFCycleEditor', () => ({
  useFCycleEditor: (...args: unknown[]) => useFCycleEditorMock(...args),
}))
vi.mock('../useICycleEditor', () => ({
  useICycleEditor: (...args: unknown[]) => useICycleEditorMock(...args),
}))
vi.mock('../useGCycleEditor', () => ({
  useGCycleEditor: (...args: unknown[]) => useGCycleEditorMock(...args),
}))
vi.mock('../useKCycleEditor', () => ({
  useKCycleEditor: (...args: unknown[]) => useKCycleEditorMock(...args),
}))
vi.mock('../useLCycleEditor', () => ({
  useLCycleEditor: (...args: unknown[]) => useLCycleEditorMock(...args),
}))
vi.mock('../useMCycleEditor', () => ({
  useMCycleEditor: (...args: unknown[]) => useMCycleEditorMock(...args),
}))
vi.mock('../useNCycleEditor', () => ({
  useNCycleEditor: (...args: unknown[]) => useNCycleEditorMock(...args),
}))

import { useEditorCycles, type EditorCyclesContext } from '../useEditorCycles'

const cycleDialogsStub = { __tag: 'cycleDialogs' } as any
const fCycleStub = { __tag: 'fCycle', handlers: {} } as any
const iCycleStub = { __tag: 'iCycle', branchSelector: {} } as any
const gCycleStub = { __tag: 'gCycle' } as any
const kCycleStub = { __tag: 'kCycle' } as any
const lCycleStub = { __tag: 'lCycle' } as any
const mCycleStub = { __tag: 'mCycle' } as any
const nCycleStub = { __tag: 'nCycle' } as any

function makeCtx(): EditorCyclesContext {
  return {
    wpDetail: ref({ wp_code: 'F2-21', parsed_data: {} }) as any,
    projectId: computed(() => 'proj-uuid'),
    wpId: computed(() => 'wp-uuid'),
    sheetNavActiveId: computed(() => 'sheet-1'),
    sheetNavFacade: { __tag: 'sheetNavFacade' } as any,
    cycleType: { __tag: 'cycleType' } as any,
  }
}

beforeEach(() => {
  useCycleDialogsMock.mockReset().mockReturnValue(cycleDialogsStub)
  useFCycleEditorMock.mockReset().mockReturnValue(fCycleStub)
  useICycleEditorMock.mockReset().mockReturnValue(iCycleStub)
  useGCycleEditorMock.mockReset().mockReturnValue(gCycleStub)
  useKCycleEditorMock.mockReset().mockReturnValue(kCycleStub)
  useLCycleEditorMock.mockReset().mockReturnValue(lCycleStub)
  useMCycleEditorMock.mockReset().mockReturnValue(mCycleStub)
  useNCycleEditorMock.mockReset().mockReturnValue(nCycleStub)
})

describe('useEditorCycles — 实例化', () => {
  it('返回 8 个 cycle 实例，引用与 mock 返回一致', () => {
    const ctx = makeCtx()
    const api = useEditorCycles(ctx)

    expect(Object.keys(api).sort()).toEqual(
      ['cycleDialogs', 'fCycle', 'gCycle', 'iCycle', 'kCycle', 'lCycle', 'mCycle', 'nCycle'].sort(),
    )
    expect(api.cycleDialogs).toBe(cycleDialogsStub)
    expect(api.fCycle).toBe(fCycleStub)
    expect(api.iCycle).toBe(iCycleStub)
    expect(api.gCycle).toBe(gCycleStub)
    expect(api.kCycle).toBe(kCycleStub)
    expect(api.lCycle).toBe(lCycleStub)
    expect(api.mCycle).toBe(mCycleStub)
    expect(api.nCycle).toBe(nCycleStub)
  })

  it('每个 cycle composable 都恰好调用一次', () => {
    const ctx = makeCtx()
    useEditorCycles(ctx)

    expect(useCycleDialogsMock).toHaveBeenCalledTimes(1)
    expect(useFCycleEditorMock).toHaveBeenCalledTimes(1)
    expect(useICycleEditorMock).toHaveBeenCalledTimes(1)
    expect(useGCycleEditorMock).toHaveBeenCalledTimes(1)
    expect(useKCycleEditorMock).toHaveBeenCalledTimes(1)
    expect(useLCycleEditorMock).toHaveBeenCalledTimes(1)
    expect(useMCycleEditorMock).toHaveBeenCalledTimes(1)
    expect(useNCycleEditorMock).toHaveBeenCalledTimes(1)
  })
})

describe('useEditorCycles — 调用签名', () => {
  it('cycleDialogs 收到 (wpDetail, wpId, sheetNavActiveId, cycleType)', () => {
    const ctx = makeCtx()
    useEditorCycles(ctx)

    expect(useCycleDialogsMock).toHaveBeenCalledWith(
      ctx.wpDetail,
      ctx.wpId,
      ctx.sheetNavActiveId,
      ctx.cycleType,
    )
  })

  it('fCycle 收到 (wpDetail, projectId, wpId, sheetNavFacade, cycleDialogs) — 末位为 cycleDialogs', () => {
    const ctx = makeCtx()
    useEditorCycles(ctx)

    expect(useFCycleEditorMock).toHaveBeenCalledWith(
      ctx.wpDetail,
      ctx.projectId,
      ctx.wpId,
      ctx.sheetNavFacade,
      cycleDialogsStub,
    )
  })

  it('iCycle / gCycle 收到 (wpDetail, sheetNavFacade, cycleDialogs)', () => {
    const ctx = makeCtx()
    useEditorCycles(ctx)

    expect(useICycleEditorMock).toHaveBeenCalledWith(
      ctx.wpDetail,
      ctx.sheetNavFacade,
      cycleDialogsStub,
    )
    expect(useGCycleEditorMock).toHaveBeenCalledWith(
      ctx.wpDetail,
      ctx.sheetNavFacade,
      cycleDialogsStub,
    )
  })

  it('kCycle / lCycle / mCycle / nCycle 收到 (wpDetail, cycleDialogs)', () => {
    const ctx = makeCtx()
    useEditorCycles(ctx)

    for (const m of [
      useKCycleEditorMock,
      useLCycleEditorMock,
      useMCycleEditorMock,
      useNCycleEditorMock,
    ]) {
      expect(m).toHaveBeenCalledWith(ctx.wpDetail, cycleDialogsStub)
    }
  })

  it('cycleDialogs 必须先于其他 cycle 调用（依赖拓扑）', () => {
    const order: string[] = []
    useCycleDialogsMock.mockImplementation(() => {
      order.push('cycleDialogs')
      return cycleDialogsStub
    })
    useFCycleEditorMock.mockImplementation(() => {
      order.push('fCycle')
      return fCycleStub
    })
    useICycleEditorMock.mockImplementation(() => {
      order.push('iCycle')
      return iCycleStub
    })
    useGCycleEditorMock.mockImplementation(() => {
      order.push('gCycle')
      return gCycleStub
    })
    useKCycleEditorMock.mockImplementation(() => {
      order.push('kCycle')
      return kCycleStub
    })
    useLCycleEditorMock.mockImplementation(() => {
      order.push('lCycle')
      return lCycleStub
    })
    useMCycleEditorMock.mockImplementation(() => {
      order.push('mCycle')
      return mCycleStub
    })
    useNCycleEditorMock.mockImplementation(() => {
      order.push('nCycle')
      return nCycleStub
    })

    useEditorCycles(makeCtx())

    expect(order[0]).toBe('cycleDialogs')
    expect(order).toContain('fCycle')
    expect(order).toContain('nCycle')
    expect(order.length).toBe(8)
  })
})
