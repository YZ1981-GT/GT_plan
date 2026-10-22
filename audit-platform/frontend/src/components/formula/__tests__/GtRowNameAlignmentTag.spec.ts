/**
 * GtRowNameAlignmentTag：行内用法点击直达对齐弹窗；弹窗内用法不再发打开事件（spec formula-governance-coverage-closure R4）。
 */
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import GtRowNameAlignmentTag from '../GtRowNameAlignmentTag.vue'
import { eventBus } from '@/utils/eventBus'

const row = (state: string) => ({
  row_key: 'r1', row_label: '预收销售款', match_state: state, candidates: [], target_identity: [],
  amount: null, similarity: null, source_kind: null, confirmed_by: null, confirmed_at: null,
  mapping_version: null, stale_reason: null,
}) as any
const ctx = { wpId: 'wp-1', projectId: 'p-1', year: 2025, wpCode: 'K1-1', sheetCode: 'K1-1', allRows: [row('unmatched')] }
// 不桩 transition：默认桩会把透传属性挂在桩元素上，点它到不了 el-tag 自己的点击处理
const mountTag = (props: Record<string, unknown>) =>
  mount(GtRowNameAlignmentTag, { props: props as any, global: { plugins: [ElementPlus], stubs: { transition: false } } })

describe('GtRowNameAlignmentTag', () => {
  it('行内用法：未匹配显示「去对齐」，点击带整表打开对齐弹窗', async () => {
    const spy = vi.spyOn(eventBus, 'emit')
    const w = mountTag({ row: row('unmatched'), ...ctx })
    expect(w.text()).toBe('未匹配 · 去对齐')
    await w.find('[data-state="unmatched"]').trigger('click')
    expect(spy).toHaveBeenCalledWith('open-row-name-alignment', expect.objectContaining({
      wpId: 'wp-1', sheetCode: 'K1-1', rows: ctx.allRows }))
    spy.mockRestore()
  })

  it('行内用法缺上下文：不发事件（打开的会是空弹窗）', async () => {
    const spy = vi.spyOn(eventBus, 'emit')
    const w = mountTag({ row: row('ambiguous') })
    await w.find('[data-state="ambiguous"]').trigger('click')
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
  })

  it('弹窗内用法：文案不带「去对齐」，点击不发打开事件；「重新确认」改为 select', async () => {
    const spy = vi.spyOn(eventBus, 'emit')
    const w = mountTag({ row: row('unmatched'), inDialog: true, ...ctx })
    expect(w.text()).toBe('未匹配')
    await w.find('[data-state="unmatched"]').trigger('click')
    const c = mountTag({ row: row('user_confirmed'), inDialog: true })
    ;(c.vm as any).$.setupState.onReconfirm()
    expect(c.emitted('select')).toEqual([['r1']])
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
  })

  it('未知状态照实显示，不藏', () => {
    expect(mountTag({ row: row('stale_x'), inDialog: true }).text()).toBe('stale_x')
  })
})
