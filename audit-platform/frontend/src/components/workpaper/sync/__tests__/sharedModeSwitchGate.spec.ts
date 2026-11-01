/**
 * 共享模式切换载体必须**真的采纳**同步能力单源 —— `showModeSwitch` 的行为判据。
 *
 * spec workpaper-html-onlyoffice-bidirectional-writeback-closure（AC 1.4 / task 3.5）。
 *
 * ═══ 为什么必须单独有这一条 ═══════════════════════════════════════════════
 *
 * task 3.5 的迁移走「共享载体 + 每宿主几行」的杠杆：改 `useGRenderModeSwitch` /
 * `useCycleHtmlOoDualMode` 两处，25 个宿主就全接上了。杠杆的另一面是**单点失效** ——
 * 把载体里的 `showModeSwitch` 改成 `return true`，25 个宿主会同时退回「自行决定」，
 * 而当时全部既有判据都看不见这件事：
 *
 *   * 棘轮（`entrySyncModePresentationRatchet.spec.ts`）只看宿主有没有 import 单源；
 *   * 接线闭合（`entrySyncUiHonesty.spec.ts`）只看宿主模板的 `v-if` **文本**绑没绑
 *     `showModeSwitch`；
 *   * `entrySyncPresentation.spec.ts` 测的是 `deriveEntrySyncPresentation` 这个纯函数，
 *     它根本不知道有没有载体在用它。
 *
 * 三者都是**静态/旁路**判据，没有一条会真的调用载体去看它返回什么。本文件补这一环：
 * 载体拿到 `entrySync` 后必须逐值透出单源的结论，不传时必须保持改线前行为。
 *
 * 🔴 并刻意钉住一条设计决定：`showModeSwitch`（**可见性**）不得掺入 `isOoAvailable`
 *    （**可用性** —— OO 服务在不在、这张 sheet 的 OO 侧能否拉起）。两者混在一起会产生
 *    两种相反的错：服务探活抖一下就把真能双向的开关藏掉；或仅能打开 OO 却呈现成双向。
 *    可用性属 `modeOptions` 的 `onlineDisabled`，由那边负责。
 */
import { defineComponent, h, nextTick, ref, type ComputedRef } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useGRenderModeSwitch } from '../useGRenderModeSwitch'
import { useCycleHtmlOoDualMode } from '../../composables/useCycleHtmlOoDualMode'

/** 单源的最小形状（两个载体的 `entrySync` 入参都只要这一个字段）。 */
function fakeEntrySync(showModeSwitch: boolean) {
  return { presentation: { value: { showModeSwitch } } }
}

/** 在真实 setup 作用域里跑 composable（`computed` / `onMounted` 都需要）。 */
function runInSetup<T>(fn: () => T): { result: T; unmount: () => void } {
  let result!: T
  const wrapper = mount(
    defineComponent({
      setup() {
        result = fn()
        return () => h('div')
      },
    }),
  )
  return { result, unmount: () => wrapper.unmount() }
}

function gSwitchWith(entrySync?: { presentation: { value: { showModeSwitch: boolean } } }) {
  // 桥与 legacy 只取本判据用得到的最小子集；本文件不测切换动作，只测可见性取源。
  const bridge = {
    mode: ref('html_idle'),
    descriptor: ref(null),
    busy: ref(false),
  } as unknown as Parameters<typeof useGRenderModeSwitch>[0]['bridge']
  return runInSetup(() =>
    useGRenderModeSwitch({
      bridge,
      legacy: { currentMode: ref<'html' | 'onlyoffice'>('html'), onModeChange: () => {} },
      isManagedSheet: ref(true),
      editorHostRef: ref(null),
      entrySync,
    }),
  )
}

function cycleDualWith(
  entrySync?: { presentation: { value: { showModeSwitch: boolean } } },
) {
  return runInSetup(() =>
    useCycleHtmlOoDualMode({
      wpId: ref('wp-1'),
      storagePrefix: 'test:shared-mode-switch:',
      entrySync,
    }),
  )
}

beforeEach(() => {
  // `useCycleHtmlOoDualMode` 在 onMounted 里探活 OO；本判据不关心探活结果，但必须让它
  // 可预期地失败（isOoAvailable=false），以便验证「可见性不随可用性走」。
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
  try {
    localStorage.clear()
  } catch {
    /* jsdom 下偶发不可用，忽略 */
  }
})

describe('useGRenderModeSwitch 必须采纳同步能力单源', () => {
  it('单源说不该显示 ⇒ showModeSwitch 为 false', () => {
    const { result, unmount } = gSwitchWith(fakeEntrySync(false))
    expect(result.showModeSwitch.value).toBe(false)
    unmount()
  })

  it('单源说该显示 ⇒ showModeSwitch 为 true', () => {
    const { result, unmount } = gSwitchWith(fakeEntrySync(true))
    expect(result.showModeSwitch.value).toBe(true)
    unmount()
  })

  it('没传 entrySync ⇒ 恒 true（保持改线前行为，供渐进迁移）', () => {
    const { result, unmount } = gSwitchWith(undefined)
    expect(result.showModeSwitch.value).toBe(true)
    unmount()
  })

  it('单源结论变化时 showModeSwitch 跟着变（是响应式派生，不是一次性快照）', async () => {
    const live = ref(false)
    const entrySync = { presentation: { get value() { return { showModeSwitch: live.value } } } }
    const { result, unmount } = gSwitchWith(entrySync)
    expect(result.showModeSwitch.value).toBe(false)
    live.value = true
    await nextTick()
    expect(result.showModeSwitch.value).toBe(true)
    unmount()
  })
})

describe('useCycleHtmlOoDualMode 必须采纳同步能力单源', () => {
  it('单源说不该显示 ⇒ showModeSwitch 为 false', () => {
    const { result, unmount } = cycleDualWith(fakeEntrySync(false))
    expect(result.showModeSwitch.value).toBe(false)
    unmount()
  })

  it('单源说该显示 ⇒ showModeSwitch 为 true', () => {
    const { result, unmount } = cycleDualWith(fakeEntrySync(true))
    expect(result.showModeSwitch.value).toBe(true)
    unmount()
  })

  it('没传 entrySync ⇒ 恒 true（保持改线前行为，供渐进迁移）', () => {
    const { result, unmount } = cycleDualWith(undefined)
    expect(result.showModeSwitch.value).toBe(true)
    unmount()
  })

  it('可见性不随 OO 服务可用性走：探活失败但单源说可双向 ⇒ 开关仍该显示', async () => {
    const { result, unmount } = cycleDualWith(fakeEntrySync(true))
    await nextTick()
    await nextTick()
    // 探活被 stub 成 reject ⇒ 可用性为假
    expect(result.isOoAvailable.value).toBe(false)
    // 可见性仍由单源决定
    expect(result.showModeSwitch.value).toBe(true)
    // 可用性走的是 modeOptions 的 disabled（另一层，不是 v-if）
    const online = result.modeOptions.value.find((opt) => opt.value === 'onlyoffice')
    expect(online?.disabled, 'OO 不可用时应在选项上禁用，而不是把开关藏掉').toBe(true)
    unmount()
  })
})

describe('判据可伪证', () => {
  it('两个载体的 showModeSwitch 都是 ComputedRef（否则上面的响应式判据是空转）', () => {
    const g = gSwitchWith(fakeEntrySync(true))
    const c = cycleDualWith(fakeEntrySync(true))
    for (const [name, value] of [
      ['useGRenderModeSwitch', g.result.showModeSwitch],
      ['useCycleHtmlOoDualMode', c.result.showModeSwitch],
    ] as Array<[string, ComputedRef<boolean>]>) {
      expect(typeof value, `${name} 的 showModeSwitch 不是 ref`).toBe('object')
      expect('value' in value, `${name} 的 showModeSwitch 没有 .value`).toBe(true)
    }
    g.unmount()
    c.unmount()
  })
})
