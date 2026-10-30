/**
 * useRendererCellLocate：定位请求不丢、只在本渲染器内找、结果可见（spec wp-deeplink-cell-locate-closure 需求 1~3）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import {
  SHEET_MISSING_MESSAGE,
  cellMissingMessage,
  useRendererCellLocate,
  type RendererCellLocateDeps,
} from '../useRendererCellLocate'
import { GT_LOCATE_HIGHLIGHT_CLASS } from '../useCellLocate'

const SHEETS: Record<string, { sheet_name: string; componentType: string }> = {
  S1: { sheet_name: '第一页S1', componentType: 'test-html' },
  S2: { sheet_name: '第二页S2', componentType: 'test-html' },
}

function setup(overrides: Partial<RendererCellLocateDeps> = {}) {
  const ready = ref(true)
  const active = ref('第一页S1')
  const root = document.createElement('div')
  document.body.appendChild(root)
  const notify = vi.fn()
  const selectSheet = vi.fn((name: string) => { active.value = name })
  const component = ref<any>(null)
  const scope = effectScope()
  const api = scope.run(() => useRendererCellLocate({
    wpId: () => 'wp-1',
    ready: () => ready.value,
    resolveSheet: (locator) => Object.values(SHEETS).find((s) => s.sheet_name === locator || s.sheet_name.endsWith(locator)) ?? null,
    activeSheet: () => Object.values(SHEETS).find((s) => s.sheet_name === active.value) ?? null,
    selectSheet,
    root: () => root,
    component: () => component.value,
    wpCode: () => 'E1',
    componentType: () => 'test-html',
    notify,
    ...overrides,
  }))!
  return { api, ready, active, root, notify, selectSheet, component, scope }
}

function anchor(parent: HTMLElement, cell: string): HTMLElement {
  const el = document.createElement('div')
  el.setAttribute('data-cell-ref', cell)
  parent.appendChild(el)
  return el
}

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => {
  vi.runOnlyPendingTimers()
  vi.useRealTimers()
  document.body.innerHTML = ''
})

describe('useRendererCellLocate — 请求不丢', () => {
  it('渲染配置未到时排队，到达后执行（切页 + 定位）', async () => {
    const t = setup()
    t.ready.value = false
    const target = anchor(t.root, 'B5')
    t.api.request({ wpId: 'wp-1', sheetName: 'S2', cellRef: 'B5' })
    await vi.advanceTimersByTimeAsync(2000)
    expect(t.selectSheet).not.toHaveBeenCalled()
    expect(target.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(false)
    expect(t.api.pending.value).toMatchObject({ cellRef: 'B5' })

    t.ready.value = true
    await nextTick()
    expect(t.selectSheet).toHaveBeenCalledWith('第二页S2')
    await vi.advanceTimersByTimeAsync(0)
    expect(target.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(true)
    expect(t.notify).not.toHaveBeenCalled()
    t.scope.stop()
  })

  it('排队只留最后一个请求（同一 tick 内先未就绪再就绪也接得住）', async () => {
    const t = setup()
    t.ready.value = false
    t.api.request({ wpId: 'wp-1', sheetName: 'S1', cellRef: 'A1' })
    t.api.request({ wpId: 'wp-1', sheetName: 'S2', cellRef: 'B5' })
    t.ready.value = true
    await nextTick()
    expect(t.selectSheet).toHaveBeenCalledTimes(1)
    expect(t.selectSheet).toHaveBeenCalledWith('第二页S2')
    expect(t.api.pending.value).toBeNull()
    t.scope.stop()
  })

  it('就绪时同步切页（发出请求当下即切，不等定位）', () => {
    const t = setup()
    t.api.request({ wpId: 'wp-1', sheetName: 'S2', cellRef: 'B5' })
    expect(t.selectSheet).toHaveBeenCalledWith('第二页S2')
    t.scope.stop()
  })

  it('wpId 不是本底稿的请求忽略', async () => {
    const t = setup()
    anchor(t.root, 'B5')
    t.api.request({ wpId: 'wp-other', sheetName: 'S2', cellRef: 'B5' })
    await vi.advanceTimersByTimeAsync(3000)
    expect(t.selectSheet).not.toHaveBeenCalled()
    expect(t.notify).not.toHaveBeenCalled()
    t.scope.stop()
  })
})

describe('useRendererCellLocate — 定位顺序与范围', () => {
  it('组件钩子定位成功：不再找 DOM、不提示', async () => {
    const t = setup()
    const hook = vi.fn().mockResolvedValue(true)
    t.component.value = { locateCell: hook }
    const domAnchor = anchor(t.root, 'C16')
    t.api.request({ wpId: 'wp-1', sheetName: 'S1', cellRef: 'C16' })
    await vi.advanceTimersByTimeAsync(0)
    expect(hook).toHaveBeenCalledTimes(1)
    expect(hook.mock.calls[0][0]).toMatchObject({ wp_code: 'E1', sheet_name: '第一页S1', cell_ref: 'C16' })
    expect(domAnchor.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(false)
    await vi.advanceTimersByTimeAsync(3000)
    expect(t.notify).not.toHaveBeenCalled()
    t.scope.stop()
  })

  it('钩子返回 false 时在本渲染器根元素内找 [data-cell-ref]', async () => {
    const t = setup()
    t.component.value = { locateCell: () => false }
    const inside = anchor(t.root, 'C16')
    t.api.request({ wpId: 'wp-1', cellRef: 'C16' })
    await vi.advanceTimersByTimeAsync(0)
    expect(inside.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(true)
    t.scope.stop()
  })

  it('根元素外的同名锚点不认，重试完只提示一次', async () => {
    const t = setup()
    const outside = anchor(document.body, 'C10')
    t.api.request({ wpId: 'wp-1', sheetName: 'S1', cellRef: 'C10' })
    await vi.advanceTimersByTimeAsync(5000)
    expect(outside.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(false)
    expect(t.notify).toHaveBeenCalledTimes(1)
    expect(t.notify).toHaveBeenCalledWith(cellMissingMessage('第一页S1', 'C10'))
    t.scope.stop()
  })

  it('根元素为空时不退回整个 document', async () => {
    const t = setup({ root: () => null })
    const outside = anchor(document.body, 'C10')
    t.api.request({ wpId: 'wp-1', cellRef: 'C10' })
    await vi.advanceTimersByTimeAsync(5000)
    expect(outside.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(false)
    expect(t.notify).toHaveBeenCalledTimes(1)
    t.scope.stop()
  })
})

describe('useRendererCellLocate — 结果与重试', () => {
  it('sheet 解析不到：提示「未能定位」且不切页', async () => {
    const t = setup()
    t.api.request({ wpId: 'wp-1', sheetName: '不存在', cellRef: 'B5' })
    await vi.advanceTimersByTimeAsync(3000)
    expect(t.selectSheet).not.toHaveBeenCalled()
    expect(t.notify).toHaveBeenCalledTimes(1)
    expect(t.notify).toHaveBeenCalledWith(SHEET_MISSING_MESSAGE)
    t.scope.stop()
  })

  it('内容晚到（200ms 后才渲染出锚点）：后续重试命中、不提示', async () => {
    const t = setup()
    t.api.request({ wpId: 'wp-1', cellRef: 'B5' })
    await vi.advanceTimersByTimeAsync(200)
    const late = anchor(t.root, 'B5')
    await vi.advanceTimersByTimeAsync(200)
    expect(late.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(true)
    await vi.advanceTimersByTimeAsync(5000)
    expect(t.notify).not.toHaveBeenCalled()
    t.scope.stop()
  })

  it('只有 sheet、没有单元格：只切页，不找、不提示', async () => {
    const t = setup()
    t.api.request({ wpId: 'wp-1', sheetName: 'S2' })
    await vi.advanceTimersByTimeAsync(3000)
    expect(t.selectSheet).toHaveBeenCalledWith('第二页S2')
    expect(t.notify).not.toHaveBeenCalled()
    t.scope.stop()
  })

  it('新请求作废旧请求的剩余重试（旧请求不再提示）', async () => {
    const t = setup()
    t.api.request({ wpId: 'wp-1', cellRef: 'Z1' })
    await vi.advanceTimersByTimeAsync(120)
    const b = anchor(t.root, 'B5')
    t.api.request({ wpId: 'wp-1', cellRef: 'B5' })
    await vi.advanceTimersByTimeAsync(0)
    expect(b.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(true)
    await vi.advanceTimersByTimeAsync(5000)
    expect(t.notify).not.toHaveBeenCalled()
    t.scope.stop()
  })

  it('卸载后不再提示', async () => {
    const t = setup()
    t.api.request({ wpId: 'wp-1', cellRef: 'Z1' })
    await vi.advanceTimersByTimeAsync(120)
    t.scope.stop()
    await vi.advanceTimersByTimeAsync(5000)
    expect(t.notify).not.toHaveBeenCalled()
  })
})
