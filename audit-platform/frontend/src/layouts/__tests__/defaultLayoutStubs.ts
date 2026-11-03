/** DefaultLayout 用例的子组件桩（vi.mock 工厂里按需动态 import，免得工厂提升后引用未初始化的变量） */
import { defineComponent, h } from 'vue'

/** 原样渲染指定的具名插槽 */
export function slotStub(name: string, slotNames: string[]) {
  return defineComponent({
    name,
    setup: (_props, { slots }) => () => h('div', { class: name }, slotNames.map((k) => slots[k]?.())),
  })
}

/** 只用来 `$emit` 的空组件 */
export function emitterStub(name: string) {
  return defineComponent({ name, emits: ['select', 'recalc', 'detail'], setup: () => () => h('div', { class: name }) })
}

export function blankStub(name: string) {
  return defineComponent({ name, setup: () => () => h('div') })
}
