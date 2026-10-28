/**
 * WpCommitInput 行为守卫 —— 失焦 / 回车才提交的文本框
 *
 * Spec: `.kiro/specs/voucher-identity-writeback-and-audit-phase/`（任务 10 浏览器走查勘误）
 * 🔴 el-input 只绑 `:model-value` + `@change` 时打的字会被立即还原（Element Plus 每次输入后
 * 把原生值重置回 modelValue），失焦时 `@change` 拿到旧值 —— 第一例钉住这个前提，
 * 之后各例钉住 WpCommitInput：输入保留、change 交出草稿、拒收还原、跟随父组件、透传属性 / 插槽。
 *
 * 🔴 不用 VTU 的 `setValue`：它在 input 之后**同步**补发 change，change 读到的是还没被重置的值
 * ⇒ 用它测「:model-value + @change」恒绿（这正是平台上这类框长期输不进字却没有测试打红的原因）。
 * 这里按浏览器顺序：逐次 input、等重置、最后才 change（失焦）。
 */
import { describe, it, expect } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElInput } from 'element-plus'
import { defineComponent, h, ref } from 'vue'
import WpCommitInput from '../WpCommitInput.vue'

const global = { plugins: [ElementPlus] }

/** 像键盘输入那样只发 input，并等 Element Plus 的「重置原生值」跑完 */
async function typeText(w: VueWrapper, text: string, sel = 'input'): Promise<void> {
  const el = w.find(sel).element as HTMLInputElement
  el.value = text
  await w.find(sel).trigger('input')
  await flushPromises()
}

/** 父组件：accept=true 时在 change 里回写，false 时拒收（像只读行那样直接 return） */
function host(initial: string, accept = true) {
  const value = ref(initial)
  const changes: string[] = []
  const Host = defineComponent({
    setup() {
      return () => h(WpCommitInput, {
        modelValue: value.value,
        placeholder: '备注',
        onChange: (v: string) => { changes.push(v); if (accept) value.value = v },
      })
    },
  })
  const w = mount(Host, { global })
  const shown = () => (w.find('input').element as HTMLInputElement).value
  const blurWithChange = async () => { await w.find('input').trigger('change'); await w.find('input').trigger('blur'); await flushPromises() }
  return { value, changes, w, shown, blurWithChange }
}

describe('WpCommitInput', () => {
  it('前提：el-input 只绑 :model-value + @change，打的字被还原、change 拿到旧值', async () => {
    const changes: string[] = []
    const w = mount(defineComponent({ setup: () => () => h(ElInput, { modelValue: '', onChange: (v: string) => changes.push(v) }) }), { global })
    await typeText(w, 'Y')
    expect((w.find('input').element as HTMLInputElement).value).toBe('')
    await w.find('input').trigger('change')
    expect(changes).toEqual([''])
  })

  it('输入中保留草稿，change 时把草稿交给父组件，父组件接收后显示新值', async () => {
    const { w, changes, value, shown, blurWithChange } = host('')
    await typeText(w, '已')
    await typeText(w, '已核对')
    expect(shown()).toBe('已核对')
    await blurWithChange()
    expect(changes).toEqual(['已核对'])
    expect(value.value).toBe('已核对')
    expect(shown()).toBe('已核对')
  })

  it('父组件拒收（值没变）：提交后回到父组件的值', async () => {
    const { w, changes, shown, blurWithChange } = host('原值', false)
    await typeText(w, '改了')
    expect(shown()).toBe('改了')
    await blurWithChange()
    expect(changes).toEqual(['改了'])
    expect(shown()).toBe('原值')
  })

  it('不在输入中时跟随父组件的值；打了又删回原值（不触发 change）失焦后也跟随', async () => {
    const { w, value, shown, changes } = host('a')
    value.value = 'b'
    await flushPromises()
    expect(shown()).toBe('b')
    await typeText(w, 'bx')
    await typeText(w, 'b')
    await w.find('input').trigger('blur')
    value.value = 'c'
    await flushPromises()
    expect(shown()).toBe('c')
    expect(changes).toEqual([])
  })

  it('属性与插槽透传：textarea、disabled、placeholder、append 插槽', () => {
    const w = mount(WpCommitInput, {
      props: { modelValue: 'x' },
      attrs: { type: 'textarea', disabled: true, placeholder: '审计说明' },
      global,
    })
    const ta = w.find('textarea')
    expect(ta.exists()).toBe(true)
    expect((ta.element as HTMLTextAreaElement).value).toBe('x')
    expect(ta.attributes('disabled')).toBeDefined()
    expect(ta.attributes('placeholder')).toBe('审计说明')
    const withSlot = mount(WpCommitInput, { props: { modelValue: '' }, slots: { append: '<span class="unit">元</span>' }, global })
    expect(withSlot.find('.unit').text()).toBe('元')
  })
})
