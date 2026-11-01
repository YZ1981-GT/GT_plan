/**
 * 首次打开才挂载（spec platform-performance-residual-findings-closure R5.3）。
 *
 * 公式管理约 264 KB：四个宿主原先无条件渲染它（`defineAsyncComponent` 也照样在宿主挂载时下载、实例化）。
 * 判据：组合式函数本身的语义；挂载那一刻 modelValue 已是 true；四个宿主都按「v-if = 首开标记、标记跟随 v-model」接线。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, ref } from 'vue'
import { parse as parseSfc } from '@vue/compiler-sfc'
import { useMountOnFirstOpen } from '../useMountOnFirstOpen'

describe('useMountOnFirstOpen', () => {
  it('第一次打开前为 false；打开后为 true；再关闭仍为 true', async () => {
    const open = ref(false)
    const mounted = useMountOnFirstOpen(open)
    expect(mounted.value).toBe(false)
    open.value = true
    await nextTick()
    expect(mounted.value).toBe(true)
    open.value = false
    await nextTick()
    expect(mounted.value).toBe(true)
  })

  it('创建时已打开 ⇒ 立即为 true（getter 来源同样生效）', () => {
    const state = { open: true }
    expect(useMountOnFirstOpen(() => state.open).value).toBe(true)
  })

  it('宿主里 v-if：打开前子组件不创建；创建那一刻 modelValue 已是 true；关闭后不卸载', async () => {
    const seenAtSetup: boolean[] = []
    let unmounts = 0
    const Child = defineComponent({
      props: { modelValue: Boolean },
      setup(props) {
        seenAtSetup.push(props.modelValue)
        return () => h('div', { class: 'child' })
      },
      unmounted() { unmounts += 1 },
    })
    const Host = defineComponent({
      setup() {
        const show = ref(false)
        const mounted = useMountOnFirstOpen(show)
        return { show, mounted }
      },
      render() {
        return h('div', [this.mounted ? h(Child, { modelValue: this.show }) : null])
      },
    })
    const w = mount(Host)
    expect(w.find('.child').exists()).toBe(false)
    ;(w.vm as any).show = true
    await nextTick()
    expect(w.find('.child').exists()).toBe(true)
    expect(seenAtSetup).toEqual([true])
    ;(w.vm as any).show = false
    await nextTick()
    expect(w.find('.child').exists()).toBe(true)
    expect(unmounts).toBe(0)
  })
})

/** 四个宿主：`<FormulaManagerDialog v-if="X" v-model="Y">` 且脚本里 `const X = useMountOnFirstOpen(Y)` */
const HOSTS = [
  'layouts/ThreeColumnLayout.vue',
  'views/TrialBalance.vue',
  'views/ReportView.vue',
  'views/DisclosureEditor.vue',
]

describe('公式管理四个宿主首次打开才挂载', () => {
  it.each(HOSTS)('%s', (file) => {
    const path = resolve(__dirname, '../..', file)
    const { descriptor } = parseSfc(readFileSync(path, 'utf8'), { filename: path })
    const template = descriptor.template?.content ?? ''
    const tags = [...template.matchAll(/<FormulaManagerDialog\b([^>]*?)\/?>/g)]
    expect(tags, '应恰有一处公式管理弹窗').toHaveLength(1)
    const attrs = tags[0][1]
    const vIf = /\bv-if="([A-Za-z_$][\w$]*)"/.exec(attrs)?.[1]
    const vModel = /\bv-model="([A-Za-z_$][\w$]*)"/.exec(attrs)?.[1]
    expect(vIf, 'v-if 必须是一个首开标记').toBeTruthy()
    expect(vModel).toBeTruthy()
    const script = descriptor.scriptSetup?.content ?? ''
    expect(script).toMatch(new RegExp(`const ${vIf} = useMountOnFirstOpen\\(${vModel}\\)`))
  })

  it('反向自检：没有 v-if 的写法会被判据抓到', () => {
    const attrs = '\n      v-model="showFormulaManager"\n      scope="tb"\n'
    expect(/\bv-if="([A-Za-z_$][\w$]*)"/.exec(attrs)).toBeNull()
  })
})
