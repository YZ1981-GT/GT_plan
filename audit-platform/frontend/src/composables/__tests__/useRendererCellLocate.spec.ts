/**
 * useRendererCellLocate：定位请求不丢、只在本渲染器内找、结果可见（spec wp-deeplink-cell-locate-closure 需求 1~3）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import {
  DEFAULT_LOCATE_WAITS,
  SHEET_MISSING_MESSAGE,
  TEXT_ANCHOR_EXTRA_WAITS,
  cellMissingMessage,
  locateSheetCode,
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

describe('useRendererCellLocate — 目录文字锚点（spec wp-deeplink-locate-coverage-closure 需求 2）', () => {
  const CODED: Record<string, { sheet_name: string; sheet_code: string; componentType: string }> = {
    S1: { sheet_name: '第一页S1', sheet_code: 'S1', componentType: 'test-html' },
    S2: { sheet_name: '第二页S2', sheet_code: 'S2', componentType: 'test-html' },
  }
  const coded = {
    resolveSheet: (locator: string) => Object.values(CODED).find((s) => s.sheet_name === locator || s.sheet_code === locator) ?? null,
    activeSheet: () => CODED.S1,
  }

  it('钩子与 [data-cell-ref] 都找不到时，按目标 sheet 编码查对照并高亮唯一同名标题', async () => {
    const textAnchor = vi.fn((code: string | null, cell: string) => (code === 'S2' && cell === 'A50' ? '审计结论' : null))
    const t = setup({ ...coded, textAnchor })
    t.root.innerHTML = '<div class="el-card" id="c"><span>四、审计结论：</span></div>'
    t.api.request({ wpId: 'wp-1', sheetName: 'S2', cellRef: 'A50' })
    await vi.advanceTimersByTimeAsync(0)
    expect(textAnchor).toHaveBeenCalledWith('S2', 'A50')
    expect(t.root.querySelector('#c')!.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(true)
    await vi.advanceTimersByTimeAsync(5000)
    expect(t.notify).not.toHaveBeenCalled()
    t.scope.stop()
  })

  it('[data-cell-ref] 命中时不再用文字锚点（同名标题不高亮），每个请求只查一次对照', async () => {
    const textAnchor = vi.fn(() => '审计结论')
    const t = setup({ ...coded, textAnchor })
    t.root.innerHTML = '<div class="el-card" id="c"><span>审计结论</span></div>'
    const a = anchor(t.root, 'A50')
    t.api.request({ wpId: 'wp-1', cellRef: 'A50' })
    await vi.advanceTimersByTimeAsync(0)
    expect(a.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(true)
    expect(t.root.querySelector('#c')!.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(false)
    expect(textAnchor).toHaveBeenCalledTimes(1)
    t.scope.stop()
  })

  it('有文字锚点：标题晚于默认重试窗口才渲染（重组件取完数才出结论区）也能定位，不误报', async () => {
    const t = setup({ ...coded, textAnchor: () => '审计结论' })
    t.api.request({ wpId: 'wp-1', cellRef: 'A28' })
    await vi.advanceTimersByTimeAsync(DEFAULT_LOCATE_WAITS.reduce((s, w) => s + w, 0) + 1200)
    expect(t.notify).not.toHaveBeenCalled()
    t.root.innerHTML = '<h4 class="sec-title" id="h">审计结论</h4>'
    await vi.advanceTimersByTimeAsync(2500)
    expect(t.root.querySelector('#h')!.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(true)
    await vi.advanceTimersByTimeAsync(10000)
    expect(t.notify).not.toHaveBeenCalled()
    t.scope.stop()
  })

  it('没有文字锚点的格照旧在默认窗口后提示（不因追加等待变慢）', async () => {
    const t = setup({ ...coded, textAnchor: () => null })
    t.api.request({ wpId: 'wp-1', cellRef: 'I18' })
    await vi.advanceTimersByTimeAsync(DEFAULT_LOCATE_WAITS.reduce((s, w) => s + w, 0) + 50)
    expect(t.notify).toHaveBeenCalledTimes(1)
    t.scope.stop()
  })

  it('模板页签（渲染配置不给 sheet_code）按页签名末尾的编码查对照', async () => {
    const TPL = { sheet_name: '银行存单盘点表E1-9', sheet_code: null, componentType: 'test-html' }
    const textAnchor = vi.fn((code: string | null, cell: string) => (code === 'E1-9' && cell === 'A26' ? '审计结论' : null))
    const t = setup({ resolveSheet: (l) => (l === 'E1-9' || l === TPL.sheet_name ? TPL : null), activeSheet: () => TPL, textAnchor })
    t.root.innerHTML = '<div class="el-card" id="c"><span>审计说明</span></div><div class="el-card" id="d"><span>审计结论</span></div>'
    t.api.request({ wpId: 'wp-1', sheetName: 'E1-9', cellRef: 'A26' })
    await vi.advanceTimersByTimeAsync(0)
    expect(textAnchor).toHaveBeenCalledWith('E1-9', 'A26')
    expect(t.root.querySelector('#d')!.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(true)
    expect(t.root.querySelector('#c')!.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(false)
    t.scope.stop()
  })

  it('locateSheetCode：先用 sheet_code，否则取页签名末尾的结构化编码（不把 E1-10 当 E1-1）', () => {
    expect(locateSheetCode({ sheet_name: '货币资金分析表E1-14', sheet_code: 'e1-14' })).toBe('E1-14')
    expect(locateSheetCode({ sheet_name: '银行存单盘点表E1-9', sheet_code: null })).toBe('E1-9')
    expect(locateSheetCode({ sheet_name: '销售退货检查表 D4-20', sheet_code: '' })).toBe('D4-20')
    expect(locateSheetCode({ sheet_name: '已开立银行账户清单核对表E1-10' })).toBe('E1-10')
    expect(locateSheetCode({ sheet_name: '附注披露信息(上市公司)' })).toBeNull()
    expect(locateSheetCode(null)).toBeNull()
  })

  it('标题不唯一：追加等待用完后只提示一次', async () => {
    const t = setup({ ...coded, textAnchor: () => '审计结论' })
    t.root.innerHTML = '<div class="el-card"><span>审计结论</span></div><div class="el-card"><span>审计结论</span></div>'
    t.api.request({ wpId: 'wp-1', cellRef: 'A50' })
    const windowMs = [...DEFAULT_LOCATE_WAITS, ...TEXT_ANCHOR_EXTRA_WAITS].reduce((s, w) => s + w, 0)
    await vi.advanceTimersByTimeAsync(windowMs - 100)
    expect(t.notify).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(5000)
    expect(t.notify).toHaveBeenCalledTimes(1)
    expect(t.notify).toHaveBeenCalledWith(cellMissingMessage('第一页S1', 'A50'))
    t.scope.stop()
  })
})

describe('useRendererCellLocate — 调整分录组（spec wp-deeplink-locate-residual-closure 需求 1.2）', () => {
  const PLAN = [...DEFAULT_LOCATE_WAITS, ...TEXT_ANCHOR_EXTRA_WAITS]
  const planMs = PLAN.reduce((a, b) => a + b, 0)

  it('切到表后按计划重试，页签登记后认领即停；不按单元格找、不提示', async () => {
    let registered = false
    const entryGroup = vi.fn((wpId: string, itemId: string) => registered && wpId === 'wp-1' && itemId === 'L1-adj-RJE')
    const t = setup({ entryGroup })
    t.api.request({ wpId: 'wp-1', sheetName: 'S2', entryGroup: 'L1-adj-RJE', cellRef: 'B5' })
    expect(t.selectSheet).toHaveBeenCalledWith('第二页S2')
    await vi.advanceTimersByTimeAsync(400)
    const calls = entryGroup.mock.calls.length
    expect(calls).toBeGreaterThan(0)
    registered = true
    await vi.advanceTimersByTimeAsync(planMs)
    expect(entryGroup.mock.calls.length).toBe(calls + 1)
    expect(t.notify).not.toHaveBeenCalled()
    t.scope.stop()
  })

  it('一直没有页签认领：按完整计划（含追加等待）问完后提示一次', async () => {
    const entryGroup = vi.fn(() => false)
    const t = setup({ entryGroup })
    t.api.request({ wpId: 'wp-1', sheetName: 'S2', entryGroup: 'D4-4-rows' })
    await vi.advanceTimersByTimeAsync(planMs - 1)
    expect(t.notify).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(10)
    expect(entryGroup).toHaveBeenCalledTimes(PLAN.length)
    expect(t.notify).toHaveBeenCalledTimes(1)
    expect(t.notify).toHaveBeenCalledWith('「第二页S2」里没有找到这组调整分录（可能已删除或改了类型）')
    t.scope.stop()
  })

  it('新请求到来时旧分录组请求的剩余重试作废', async () => {
    const entryGroup = vi.fn(() => false)
    const t = setup({ entryGroup })
    t.api.request({ wpId: 'wp-1', sheetName: 'S2', entryGroup: 'D4-4-rows' })
    await vi.advanceTimersByTimeAsync(300)
    t.api.request({ wpId: 'wp-1', sheetName: 'S1' })
    await vi.advanceTimersByTimeAsync(planMs + 100)
    expect(t.notify).not.toHaveBeenCalled()
    t.scope.stop()
  })

  it('没给认领函数时照旧按单元格定位（分录组参数不生效）', async () => {
    const t = setup()
    const target = anchor(t.root, 'B5')
    t.api.request({ wpId: 'wp-1', sheetName: 'S1', entryGroup: 'D4-4-rows', cellRef: 'B5' })
    await vi.advanceTimersByTimeAsync(0)
    expect(target.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(true)
    t.scope.stop()
  })
})
