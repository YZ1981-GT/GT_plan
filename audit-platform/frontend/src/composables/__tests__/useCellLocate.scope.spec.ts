/**
 * useCellLocate：查找范围限定在 root、不再按行号猜表格行、highlightElement 幂等与淡出
 * （spec wp-deeplink-cell-locate-closure 需求 2.1 / 2.2 / 3.1）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { GT_LOCATE_HIGHLIGHT_CLASS, HIGHLIGHT_DURATION_MS, highlightElement, useCellLocate } from '../useCellLocate'

function el(parent: HTMLElement, html: string): HTMLElement {
  const box = document.createElement('div')
  box.innerHTML = html
  parent.appendChild(box)
  return box
}

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => {
  vi.runOnlyPendingTimers()
  vi.useRealTimers()
  document.body.innerHTML = ''
})

describe('useCellLocate — root 限定', () => {
  it('只在 root 内找 [data-cell-ref]，root 外的同名锚点不高亮', () => {
    const outside = el(document.body, '<span data-cell-ref="B5">外</span>').firstElementChild!
    const root = el(document.body, '<span data-cell-ref="B5">内</span>')
    const inside = root.firstElementChild!
    const ok = useCellLocate().locateCell({ wp_code: 'X', cell_ref: 'B5' }, { root })
    expect(ok).toBe(true)
    expect(inside.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(true)
    expect(outside.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(false)
  })

  it('root 里没有锚点就返回 false（不去整个 document 找）', () => {
    el(document.body, '<span data-cell-ref="B5">外</span>')
    const root = el(document.body, '<p>空</p>')
    expect(useCellLocate().locateCell({ wp_code: 'X', cell_ref: 'B5' }, { root })).toBe(false)
  })

  it('不传 root 时仍按整个 document 找（其他调用方行为不变）', () => {
    const target = el(document.body, '<span data-cell-ref="C3">x</span>').firstElementChild!
    expect(useCellLocate().locateCell({ wp_code: 'X', cell_ref: 'C3' })).toBe(true)
    expect(target.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(true)
  })
})

describe('useCellLocate — 不按单元格行号猜表格行', () => {
  it('el-table 类：只有普通行、没有锚点也没有 value 时不高亮任何行', () => {
    const root = el(document.body, `
      <div class="el-table"><div class="el-table__body"><table><tbody>
        <tr class="el-table__row"><td>1</td></tr>
        <tr class="el-table__row"><td>2</td></tr>
        <tr class="el-table__row"><td>3</td></tr>
      </tbody></table></div></div>`)
    const ok = useCellLocate().locateCell({ wp_code: 'X', cell_ref: 'B2', component_type: 'c-note-table' }, { root })
    expect(ok).toBe(false)
    expect(root.querySelectorAll(`.${GT_LOCATE_HIGHLIGHT_CLASS}`).length).toBe(0)
  })

  it('el-table 类：按 value 内容匹配仍可用', () => {
    const root = el(document.body, `
      <div class="el-table"><div class="el-table__body"><table><tbody>
        <tr class="el-table__row"><td>库存现金</td></tr>
        <tr class="el-table__row"><td>银行存款</td></tr>
      </tbody></table></div></div>`)
    const ok = useCellLocate().locateCell({ wp_code: 'X', cell_ref: 'B9', value: '银行存款', component_type: 'c-note-table' }, { root })
    expect(ok).toBe(true)
    expect(root.querySelectorAll('tr')[1].classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(true)
  })
})

describe('highlightElement', () => {
  it('加高亮、同一目标重复调用幂等、3 秒后移除', () => {
    const a = el(document.body, '<b>a</b>').firstElementChild!
    expect(highlightElement(a, 'k1')).toBe(true)
    expect(a.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(true)
    expect(highlightElement(a, 'k1')).toBe(true)
    vi.advanceTimersByTime(HIGHLIGHT_DURATION_MS - 1)
    expect(a.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(true)
    vi.advanceTimersByTime(1)
    expect(a.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(false)
  })

  it('换目标时清掉上一处高亮', () => {
    const box = el(document.body, '<b>a</b><b>b</b>')
    const [a, b] = Array.from(box.children)
    highlightElement(a, 'k1')
    highlightElement(b, 'k2')
    expect(a.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(false)
    expect(b.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(true)
  })
})
