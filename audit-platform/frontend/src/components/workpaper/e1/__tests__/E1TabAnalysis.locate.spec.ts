/**
 * E1TabAnalysis 定位钩子：真实 Element Plus 挂载，按模板单元格切区段页签并高亮对应单元格 / 卡片
 * （spec wp-deeplink-cell-locate-closure 需求 4.1 / 4.2）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import { GT_LOCATE_HIGHLIGHT_CLASS } from '@/composables/useCellLocate'

vi.mock('@/components/workpaper/GtIndexChip.vue', () => ({
  default: defineComponent({ name: 'GtIndexChip', render: () => h('span', { class: 'gt-index-chip-stub' }) }),
}))

import E1TabAnalysis from '../E1TabAnalysis.vue'

let wrapper: VueWrapper<any> | null = null

async function mountTab() {
  wrapper = mount(E1TabAnalysis, {
    attachTo: document.body,
    props: {
      wpId: 'wp-1', projectId: 'p-1', allResponses: new Map(),
      saveImmediate: vi.fn().mockResolvedValue(undefined), debouncedSave: vi.fn().mockResolvedValue(undefined),
      isReadonly: true,
    },
    global: { plugins: [ElementPlus, createPinia()] },
  })
  await flushPromises()
  await nextTick()
  return wrapper
}

function highlighted(): Element[] {
  return Array.from(document.querySelectorAll(`.${GT_LOCATE_HIGHLIGHT_CLASS}`))
}

function activeTabText(): string {
  return (document.querySelector('.el-tabs__item.is-active')?.textContent || '').trim()
}

function columnLabelOf(td: Element): string {
  const table = td.closest('.el-table')!
  const index = Array.from(td.parentElement!.children).indexOf(td)
  return (table.querySelectorAll('.el-table__header thead th')[index]?.textContent || '').trim()
}

beforeEach(() => { vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] }) })
afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  vi.runOnlyPendingTimers()
  vi.useRealTimers()
  document.body.innerHTML = ''
})

describe('E1TabAnalysis.locateCell', () => {
  it('C16 → 构成表「银行存款 / 本期金额」单元格', async () => {
    const w = await mountTab()
    expect(await w.vm.locateCell({ wp_code: 'E1', cell_ref: 'C16' })).toBe(true)
    const [cell] = highlighted()
    expect(cell?.tagName).toBe('TD')
    expect(cell.closest('[data-e1-table]')?.getAttribute('data-e1-table')).toBe('composition')
    expect((cell.parentElement!.children[0].textContent || '').trim()).toBe('银行存款')
    expect(columnLabelOf(cell)).toBe('本期金额')
  })

  it('C34 → 切到「八项比例」并高亮比例表第 1 行「本期」', async () => {
    const w = await mountTab()
    expect(await w.vm.locateCell({ wp_code: 'E1', cell_ref: 'C34' })).toBe(true)
    await nextTick()
    expect(activeTabText()).toBe('八项比例')
    const [cell] = highlighted()
    expect(cell.closest('[data-e1-table]')?.getAttribute('data-e1-table')).toBe('ratios')
    expect((cell.parentElement!.children[0].textContent || '').trim()).toBe('银行存款÷资产总额')
    expect(columnLabelOf(cell)).toBe('本期')
  })

  it('F15 → 整行（网页没有上期结构比列）', async () => {
    const w = await mountTab()
    expect(await w.vm.locateCell({ wp_code: 'E1', cell_ref: 'F15' })).toBe(true)
    const [row] = highlighted()
    expect(row.tagName).toBe('TR')
    expect((row.children[0].textContent || '').trim()).toBe('库存现金')
  })

  it('B30 → 切到「其他货币资金七类」并高亮 F3-2 交叉索引提示', async () => {
    const w = await mountTab()
    expect(await w.vm.locateCell({ wp_code: 'E1', cell_ref: 'B30' })).toBe(true)
    await nextTick()
    expect(activeTabText()).toBe('其他货币资金七类')
    const [alert] = highlighted()
    expect(alert.getAttribute('data-e1-anchor')).toBe('f3-2')
  })

  it('A50 → 审计结论卡片', async () => {
    const w = await mountTab()
    expect(await w.vm.locateCell({ wp_code: 'E1', cell_ref: 'A50' })).toBe(true)
    expect(highlighted()[0]?.getAttribute('data-e1-anchor')).toBe('conclusion')
  })

  it('C10（模板程序说明行）与 C18（合计行）→ false、不高亮', async () => {
    const w = await mountTab()
    expect(await w.vm.locateCell({ wp_code: 'E1', cell_ref: 'C10' })).toBe(false)
    expect(await w.vm.locateCell({ wp_code: 'E1', cell_ref: 'C18' })).toBe(false)
    expect(highlighted()).toHaveLength(0)
  })
})
