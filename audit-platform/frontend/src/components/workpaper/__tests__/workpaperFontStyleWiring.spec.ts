/**
 * 底稿正文跟随账号表格字号（spec platform-global-display-settings-closure 任务 5 / design A7①）。
 *
 * 两件事分开证：
 * ① 机制：真 `useWorkpaperScaffold` 的 `fontStyle` 在四档偏好下给出 11/12/13/14px，**解构后**绑定才会落成内联
 *    `--wp-font-size`；同一个组件改绑 `runtime.fontStyle`（模板不解包嵌套 ComputedRef）必须拿不到这个变量 ——
 *    这条不是注释声明，而是真跑一遍对照。
 * ② 接线：`GtWpRenderer.vue` 的根元素确实绑了解构出来的 `fontStyle`。
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { computed, defineComponent, h } from 'vue'

vi.mock('@/composables/useAgingConfig', () => ({ useAgingConfig: () => ({}) }))
vi.mock('@/components/workpaper/composables/useWorkpaperVersionToolbar', () => ({
  useWorkpaperVersionToolbar: () => ({ openVersionHistory: vi.fn() }),
}))
vi.mock('@/components/workpaper/composables/useWorkpaperReviewProvide', () => ({
  useWorkpaperReviewProvide: () => ({}),
}))

import { useWorkpaperScaffold } from '../composables/useWorkpaperScaffold'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import type { FontSize } from '@/utils/formatters'

const RENDERER_PATH = resolve(dirname(fileURLToPath(import.meta.url)), '../GtWpRenderer.vue')

/** style 绑定写法二选一：解构出来的 fontStyle，或模板里写嵌套的 runtime.fontStyle。 */
function probe(nested: boolean) {
  return defineComponent({
    setup() {
      const runtime = useWorkpaperScaffold({
        wpCode: computed(() => 'D1'),
        wpId: computed(() => 'wp-1'),
        projectId: computed(() => 'p-1'),
        year: computed(() => 2025),
      } as any)
      const { fontStyle } = runtime
      return () => h('div', { class: 'probe', style: nested ? (runtime as any).fontStyle : fontStyle.value })
    },
  })
}

function fontVar(nested: boolean): string {
  const wrapper = mount(probe(nested))
  return (wrapper.get('.probe').element as HTMLElement).style.getPropertyValue('--wp-font-size')
}

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('底稿字号接线', () => {
  it.each([
    ['xs', '11px'],
    ['sm', '12px'],
    ['md', '13px'],
    ['lg', '14px'],
  ] as [FontSize, string][])('偏好 %s ⇒ 内联 --wp-font-size: %s', (size, expected) => {
    useDisplayPrefsStore().setFontSize(size)
    expect(fontVar(false)).toBe(expected)
  })

  it('同一组件改绑嵌套 runtime.fontStyle ⇒ 拿不到字号（模板不解包）', () => {
    useDisplayPrefsStore().setFontSize('lg')
    expect(fontVar(false)).toBe('14px')
    expect(fontVar(true)).toBe('')
  })

  /**
   * 接线（2026-11-06 起的口径）：218d6e20c / e3593b2cd 把 `--wp-font-size` 收口到全局根变量 ——
   * `useDisplayPreferencesRuntime` 在 `document.documentElement` 上与 `--gt-display-font-size` 同步设置，
   * 由 `DefaultLayout` 安装；底稿路由全在 DefaultLayout 之下（standalone 路由里没有底稿页），
   * GtWpRenderer 根元素不再逐个绑定。这里钉住新接线，并继续禁止「绑嵌套 runtime.fontStyle」这一错误写法。
   */
  it('字号变量由全局显示运行时写到根元素，DefaultLayout 安装；GtWpRenderer 不绑嵌套 runtime.fontStyle', () => {
    const SRC = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
    const runtimeSrc = readFileSync(resolve(SRC, 'composables/useDisplayPreferencesRuntime.ts'), 'utf-8')
    expect(runtimeSrc).toMatch(/root\.style\.setProperty\(\s*'--wp-font-size'\s*,/)
    const layoutSrc = readFileSync(resolve(SRC, 'layouts/DefaultLayout.vue'), 'utf-8')
    expect(layoutSrc).toMatch(/\buseDisplayPreferencesRuntime\s*\(\s*\)/)
    const standaloneSrc = readFileSync(resolve(SRC, 'router/domains/standalone.ts'), 'utf-8')
    expect(standaloneSrc, '底稿页挂到了 DefaultLayout 之外，根变量不再覆盖它').not.toMatch(/[Ww]orkpaper/)

    const source = readFileSync(RENDERER_PATH, 'utf-8')
    const rootTag = /<div\s+class="gt-wp-renderer"[\s\S]*?>/.exec(source)?.[0] ?? ''
    expect(rootTag, '找不到 .gt-wp-renderer 根元素').not.toBe('')
    expect(rootTag).not.toMatch(/:style="runtime\./)
  })
})
