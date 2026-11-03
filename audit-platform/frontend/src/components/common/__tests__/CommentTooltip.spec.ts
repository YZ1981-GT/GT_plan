/**
 * CommentTooltip（spec note-chain-followup-optimizations R5）。
 *
 * 原状（可打红）：没批注时渲染 `<slot />` 片段根 —— 外层 el-tooltip 的触发属性与定位指令挂到本组件上接不住，
 * 每格一条 Vue 告警、外层提示（附注校验提示、报表公式提示）永远不出现；有批注时多个子节点只渲染第一个；
 * 气泡默认把 Enter / 空格当开合键并 preventDefault，单元格里编辑时会吃掉提交键。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createCommentVNode, defineComponent, h, nextTick } from 'vue'
import { ElTooltip } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import CommentTooltip from '../CommentTooltip.vue'
import GtAmountCell from '../GtAmountCell.vue'
import type { CellComment } from '@/composables/useCellComments'

const COMMENT = { comment: '请核对期末余额', comment_type: 'review', status: 'reviewed' } as unknown as CellComment

let warn: ReturnType<typeof vi.spyOn>
beforeEach(() => { warn = vi.spyOn(console, 'warn').mockImplementation(() => {}) })
afterEach(() => { warn.mockRestore(); document.body.innerHTML = '' })
const vueWarnings = () => warn.mock.calls.map((c: unknown[]) => String(c[0])).filter((m: string) => m.includes('[Vue warn]'))

const enter = () => new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true })

describe('CommentTooltip', () => {
  it('没批注：唯一子节点作根，父级 class / 属性 / 原生事件落到元素上，不告警', async () => {
    const onClick = vi.fn()
    const w = mount(CommentTooltip, {
      attrs: { class: 'outer', 'data-k': 'v', onClick },
      slots: { default: () => h('span', { class: 'cell' }, '100') },
    })
    expect(w.element.tagName).toBe('SPAN')
    expect(w.classes()).toEqual(expect.arrayContaining(['cell', 'outer']))
    expect(w.attributes('data-k')).toBe('v')
    await w.trigger('click')
    expect(onClick).toHaveBeenCalledTimes(1)
    expect(w.findComponent(ElTooltip).exists()).toBe(false)
    expect(vueWarnings()).toEqual([])
  })

  it('没批注、唯一子元素旁边只有 v-if 占位注释：仍以子元素作根（试算表「未审数」格的写法）', () => {
    const w = mount(CommentTooltip, {
      attrs: { class: 'outer' },
      slots: { default: () => [h('span', { class: 'cell' }, '100'), createCommentVNode('v-if')] },
    })
    expect(w.element.tagName).toBe('SPAN')
    expect(w.classes()).toEqual(expect.arrayContaining(['cell', 'outer']))
    expect(vueWarnings()).toEqual([])
  })

  it('没批注、放进 el-tooltip：外层提示的触发器挂到子元素上，悬停能显示（附注校验提示的场景）', async () => {
    const Host = defineComponent({
      setup: () => () => h(ElTooltip, { content: '期末余额与试算表不一致', placement: 'top' }, {
        default: () => h(CommentTooltip, { comment: null }, { default: () => h('div', { class: 'cell' }, '100') }),
      }),
    })
    const w = mount(Host, { attachTo: document.body })
    await nextTick()
    const cell = w.find('.cell')
    expect(cell.classes()).toContain('el-tooltip__trigger')
    await cell.trigger('mouseenter')
    await new Promise((r) => setTimeout(r, 30))
    await nextTick()
    expect(document.body.textContent).toContain('期末余额与试算表不一致')
    expect(vueWarnings()).toEqual([])
    w.unmount()
  })

  it('有批注：气泡显示批注文本，父级属性转给触发元素；Enter 不被气泡 preventDefault', () => {
    const w = mount(CommentTooltip, {
      props: { comment: COMMENT },
      attrs: { class: 'outer' },
      slots: { default: () => h('span', { class: 'cell' }, '100') },
      attachTo: document.body,
    })
    expect(w.findComponent(ElTooltip).props('content')).toBe('请核对期末余额 · ✓ 已复核')
    const cell = w.find('.cell')
    expect(cell.classes()).toEqual(expect.arrayContaining(['outer', 'el-tooltip__trigger']))
    const ev = enter()
    cell.element.dispatchEvent(ev)
    expect(ev.defaultPrevented).toBe(false)
    expect(vueWarnings()).toEqual([])
    w.unmount()
  })

  it('有批注、多个子节点：包一层 span 作触发元素，子节点都在（原先只渲染第一个）', () => {
    const w = mount(CommentTooltip, {
      props: { comment: COMMENT },
      slots: { default: () => [h('span', { class: 'a' }, '1'), h('span', { class: 'b' }, '⚠')] },
    })
    expect(w.find('.a').exists() && w.find('.b').exists()).toBe(true)
    const trigger = w.find('.a').element.parentElement!
    expect(trigger.tagName).toBe('SPAN')
    expect(trigger.classList.contains('el-tooltip__trigger')).toBe(true)
    expect(trigger.contains(w.find('.b').element)).toBe(true)
  })

  it('报表页写法：公式提示包 span、里面是带批注的金额格 ⇒ 两层触发器各在各的元素上；直接嵌套则外层挂不上', async () => {
    setActivePinia(createPinia())
    const cell = (wrapped: boolean) => defineComponent({
      setup: () => () => {
        const amount = h(GtAmountCell, { value: 100, comment: COMMENT })
        return h(ElTooltip, { content: '公式：A+B', placement: 'bottom' }, { default: () => (wrapped ? h('span', { class: 'host' }, [amount]) : amount) })
      },
    })
    const ok = mount(cell(true), { attachTo: document.body })
    await nextTick()
    expect(ok.find('.host').classes()).toContain('el-tooltip__trigger')
    expect(ok.find('.gt-amount-cell').classes()).toContain('el-tooltip__trigger')
    expect(vueWarnings()).toEqual([])
    ok.unmount()
    // 反例：直接嵌套时外层触发器没有落到任何元素上（nestedCommentTooltipGuard 就是防这个）
    const bad = mount(cell(false), { attachTo: document.body })
    await nextTick()
    expect(vueWarnings().length).toBeGreaterThan(0)
    bad.unmount()
  })

  it('没批注、多个子节点：原样渲染，不加包装', () => {
    const Host = defineComponent({
      setup: () => () => h('div', { class: 'host' }, [
        h(CommentTooltip, null, { default: () => [h('span', { class: 'a' }, '1'), h('span', { class: 'b' }, '2')] }),
      ]),
    })
    const w = mount(Host)
    expect([...w.find('.host').element.children].map((e) => e.className)).toEqual(['a', 'b'])
  })
})
